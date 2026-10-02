"""An ad unit's requests / matched requests (so its match rate and show rate) come from the MEDIATION report
WITHOUT AD_SOURCE — the ad unit's own totals, the numbers the AdMob UI shows.

  * the network report counts only the "AdMob Network" source: its requests / matched are that one source's
    share (a much lower match rate), so they must not stand for the ad unit;
  * the mediation report WITH AD_SOURCE has one request row per source and the sources OVERLAP (one ad-unit
    request is offered to several sources), so per-source requests are never summed — except where a view is
    genuinely per source (the Mediation tab's rows), which keeps them;
  * the network numbers are a FALLBACK only for an ad-unit day the ad-unit report has no row for, marked
    req_src="network", and never mixed into an alert series;
  * the old 100% show-rate cap is gone (it only hid the old cross-source ratio).

Plus the one-time, chunked, resumable history backfill of that report (marker + progress file), its pull
wiring (dimensions, the safe-fetch splitter, run_once, the per-app backfill) and the repo / wrapper plumbing.
Synthetic fixtures only."""

import json
import os
from datetime import date, timedelta

import pytest

from admob_iq import build_static
from admob_iq.api import dataservice
from admob_iq.api.dataservice import REQ_SRC_NETWORK, REQ_SRC_UNIT, _revenue_rows, build_from_db
from admob_iq.db import FileRepo, InMemoryRepo
from admob_iq.engine.baseline_report import build_daily_series
from admob_iq.fetch import fetcher
from admob_iq.fetch.admob_client import (AdMobClient, MEDIATION_UNIT_DIMENSIONS, MEDIATION_UNIT_METRICS,
                                         MockAdMobClient)

ACC, APP, UNIT = "pub-test", "app~demo", "unit~banner"


def _ids(day=None):
    return dict(account_id=ACC, app_id=APP, app_name="Demo App", ad_unit_id=UNIT, unit_name="Banner_Main",
                format="banner", platform="Android", currency_code="USD",
                **({"report_date": day} if day else {}))


def _net(repo, day, req, matched, impr, earn):
    """network report: the AdMob Network source's share only"""
    repo.upsert_network(dict(_ids(day), country="All", ad_requests=req, matched_requests=matched,
                             impressions=impr, clicks=impr // 100, estimated_earnings_micros=earn))


def _med(repo, day, src, req, matched, impr, earn):
    """mediation report WITH AD_SOURCE: one row per source (requests overlap across sources)"""
    repo.upsert_mediation(dict(_ids(day), ad_source=src, source_name=src, country="All", ad_requests=req,
                               matched_requests=matched, impressions=impr, clicks=impr // 100,
                               estimated_earnings_micros=earn, observed_ecpm_micros=0))


def _unit(repo, day, req, matched, impr, earn):
    """mediation report WITHOUT AD_SOURCE: the ad unit's own totals"""
    repo.upsert_mediation_unit(dict(_ids(day), ad_requests=req, matched_requests=matched, impressions=impr,
                                    clicks=impr // 100, estimated_earnings_micros=earn))


def _two_source_day(repo, day, *, unit=True, scale=1):
    """One ad unit, three sources. AdMob's own source sees a fraction of the unit's requests and fills ~65%;
    a second network and a waterfall line see overlapping requests. The ad unit itself: 11,500 requests,
    10,900 matched (94.8%), 9,800 impressions (89.9% show)."""
    k = scale
    _net(repo, day, 10_000 * k, 6_500 * k, 6_400 * k, 64_000_000 * k)
    _med(repo, day, "admob", 10_000 * k, 6_500 * k, 6_400 * k, 64_000_000 * k)
    _med(repo, day, "othernet", 9_000 * k, 3_000 * k, 2_900 * k, 30_000_000 * k)
    _med(repo, day, "admob_wf", 2_000 * k, 1_200 * k, 500 * k, 1_000_000 * k)
    if unit:
        _unit(repo, day, 11_500 * k, 10_900 * k, 9_800 * k, 95_000_000 * k)


# ── the source of truth ─────────────────────────────────────────────────────────────────────────────────────────

def test_two_source_unit_shows_the_ad_unit_totals_not_the_network_share():
    repo = InMemoryRepo()
    _two_source_day(repo, "2026-07-22")
    rows = _revenue_rows(repo)
    assert len(rows) == 1
    r = rows[0]
    assert r["ad_requests"] == 11_500 and r["matched_requests"] == 10_900     # the ad unit's own totals
    assert r["req_src"] == REQ_SRC_UNIT
    assert r["ad_requests"] != 10_000                                         # not the AdMob Network share
    assert r["ad_requests"] != 10_000 + 9_000 + 2_000                         # never the overlapping per-source sum
    assert r["impressions"] == 6_400 + 2_900 + 500                            # impressions / revenue still every source
    assert r["estimated_earnings_micros"] == 95_000_000
    d = build_from_db(repo, today=date(2026, 7, 23))
    p = d["placements"][0]
    assert p["match"] == round(10_900 / 11_500, 3)                            # 94.8%, not AdMob's own 65%
    assert p["show"] == round(9_800 / 10_900, 3)
    assert p["daily"][-1][3:5] == [11_500, 10_900]                            # what the Ad-units table sums
    assert d["kpis"]["match_rate"] == round(10_900 / 11_500, 3)
    assert d["kpis_by_range"]["yesterday"]["match_rate"] == round(10_900 / 11_500, 3)


def test_mediation_tab_keeps_per_source_requests():
    """The per-source rows are genuinely per source: each source's fill is ITS matched / ITS requests."""
    repo = InMemoryRepo()
    _two_source_day(repo, "2026-07-22")
    d = build_from_db(repo, today=date(2026, 7, 23))
    fill = {r["ad_source"]: r["fill"] for r in d["mediation"]["rows"]}
    assert fill == {"admob": round(6_500 / 10_000, 2), "othernet": round(3_000 / 9_000, 2),
                    "admob_wf": round(1_200 / 2_000, 2)}
    md = dataservice.build_mediation_daily(repo)
    cells = {k: v[0] for k, v in md["by_app"]["Demo App"].items()}
    assert cells["othernet"][3:5] == [3_000, 9_000]                           # [.., matched, req] of that source


def test_fallback_to_network_only_where_the_ad_unit_report_has_no_row():
    repo = InMemoryRepo()
    _two_source_day(repo, "2026-07-20")                                       # ad-unit row present
    _two_source_day(repo, "2026-07-21", unit=False)                           # no ad-unit row → network fallback
    _med(repo, "2026-07-22", "othernet", 9_000, 3_000, 2_900, 30_000_000)     # neither report has requests
    by_day = {str(r["report_date"]): r for r in _revenue_rows(repo)}
    assert (by_day["2026-07-20"]["ad_requests"], by_day["2026-07-20"]["req_src"]) == (11_500, REQ_SRC_UNIT)
    assert (by_day["2026-07-21"]["ad_requests"], by_day["2026-07-21"]["req_src"]) == (10_000, REQ_SRC_NETWORK)
    assert by_day["2026-07-21"]["matched_requests"] == 6_500
    assert (by_day["2026-07-22"]["ad_requests"], by_day["2026-07-22"]["req_src"]) == (0, None)


def test_repo_without_the_table_falls_back_to_network():
    """An older store / repo double without fetch_mediation_unit: the network numbers, as before."""
    class OldRepo(InMemoryRepo):
        fetch_mediation_unit = None
    repo = OldRepo()
    _two_source_day(repo, "2026-07-22", unit=False)
    r = _revenue_rows(repo)[0]
    assert (r["ad_requests"], r["matched_requests"], r["req_src"]) == (10_000, 6_500, REQ_SRC_NETWORK)


def test_requests_counted_once_when_a_unit_day_has_two_format_keys():
    repo = InMemoryRepo()
    _two_source_day(repo, "2026-07-22")
    repo.upsert_mediation(dict(_ids("2026-07-22"), format="native", ad_source="othernet", source_name="othernet",
                               country="All", ad_requests=5, matched_requests=5, impressions=5, clicks=0,
                               estimated_earnings_micros=1_000, observed_ecpm_micros=0))
    rows = _revenue_rows(repo)
    assert len(rows) == 2
    assert sum(r["ad_requests"] for r in rows) == 11_500                      # once, not per (format, platform) key
    assert {r["req_src"] for r in rows} == {REQ_SRC_UNIT}


# ── alerts: one series, one source; no cap ───────────────────────────────────────────────────────────────────

def _history(repo, days, last, *, unit_days, match_last=None, show_by_day=None):
    """`days` finished days ending at `last` (plus a partial today). Revenue steady (> the alert floor).
    unit_days: which days have an ad-unit row. match_last: the latest day's ad-unit match rate."""
    out = []
    for i in range(days):
        d = (last - timedelta(days=days - 1 - i)).isoformat()
        out.append(d)
        _net(repo, d, 10_000, 6_500, 6_400, 64_000_000)
        _med(repo, d, "admob", 10_000, 6_500, 6_400, 64_000_000)
        _med(repo, d, "othernet", 9_000, 3_000, 2_900, 30_000_000)
        if d in unit_days:
            req, matched = 11_500, 10_900
            impr = 9_300
            if show_by_day and d in show_by_day:
                matched = int(impr / show_by_day[d])
            if match_last is not None and i == days - 1:
                matched = int(req * match_last)
            _unit(repo, d, req, matched, impr, 94_000_000)
    return out


def _metrics(d):
    return {m["metric"]: m for a in d["alerts"]["items"] for m in a["metrics"]}


def test_a_fallback_latest_day_never_raises_a_false_match_or_show_alert():
    """The switch / failed-pull case: the history is from the ad-unit report (match ~95%) and the latest day
    fell back to the network share (match 65%). Mixing them would read as a 30-point match drop."""
    repo = InMemoryRepo()
    last = date(2026, 7, 22)
    days = _history(repo, 12, last, unit_days=set())
    for d in days[:-1]:
        _unit(repo, d, 11_500, 10_900, 9_300, 94_000_000)
    dash = build_from_db(repo, today=last + timedelta(days=1))
    assert dash["placements"][0]["daily"][-1][3:5] == [10_000, 6_500]        # the shown fallback numbers
    m = _metrics(dash)
    assert "match_rate" not in m and "show_rate" not in m and "requests" not in m


def test_old_network_history_before_the_switch_never_mixes_into_the_baseline():
    """Older days hold only network numbers, the recent days the ad-unit report: the request-based series uses
    the ad-unit days only, so a steady unit raises nothing on the switch."""
    repo = InMemoryRepo()
    last = date(2026, 7, 22)
    days = _history(repo, 20, last, unit_days=set())
    for d in days[-9:]:
        _unit(repo, d, 11_500, 10_900, 9_300, 94_000_000)
    m = _metrics(build_from_db(repo, today=last + timedelta(days=1)))
    assert not ({"match_rate", "show_rate", "requests"} & set(m))


def test_a_real_match_drop_inside_the_ad_unit_series_still_alerts():
    repo = InMemoryRepo()
    last = date(2026, 7, 22)
    days = _history(repo, 12, last, unit_days=set(), match_last=None)
    for d in days[:-1]:
        _unit(repo, d, 11_500, 10_900, 9_300, 94_000_000)
    _unit(repo, days[-1], 11_500, 6_900, 6_800, 70_000_000)                  # 95% → 60%
    m = _metrics(build_from_db(repo, today=last + timedelta(days=1)))
    assert "match_rate" in m and m["match_rate"]["message"] == "match_rate 95% → 60%"
    assert m["match_rate"]["started"] == days[-1]


def test_show_rate_is_not_capped_at_100_percent():
    """The old min(1.0, …) only hid the cross-source ratio. With one source a real show rate above 100% (an ad
    matched one day and shown the next) is AdMob's own number — and judged as such: 110% → 90% is a 20-point
    drop (the capped series read 100% → 90%, under the 15-point rule)."""
    repo = InMemoryRepo()
    last = date(2026, 7, 22)
    names = [(last - timedelta(days=11 - i)).isoformat() for i in range(12)]
    show = {d: 1.10 for d in names[:-1]}
    show[names[-1]] = 0.90
    _history(repo, 12, last, unit_days=set(names), show_by_day=show)
    dash = build_from_db(repo, today=last + timedelta(days=1))
    m = _metrics(dash)
    assert "show_rate" in m and m["show_rate"]["message"] == "show_rate 110% → 90%"
    one = build_from_db(_one_day_over_100(), today=date(2026, 7, 23))
    assert one["placements"][0]["show"] == round(1_100 / 1_000, 3)            # 110%, not 100%


def _one_day_over_100():
    repo = InMemoryRepo()
    _med(repo, "2026-07-22", "admob", 2_000, 1_000, 1_100, 5_000_000)
    _unit(repo, "2026-07-22", 1_200, 1_000, 1_100, 5_000_000)
    return repo


def test_the_cap_line_is_gone_from_the_engine():
    import inspect
    src = inspect.getsource(dataservice.build_from_db)
    assert "min(1.0, metrics.show_rate" not in src


# ── placement daily chart (baseline_daily.json) ──────────────────────────────────────────────────────────────

def test_daily_chart_uses_the_ad_unit_numbers_and_leaves_fallback_days_blank():
    repo = InMemoryRepo()
    _two_source_day(repo, "2026-07-20")
    _two_source_day(repo, "2026-07-21", unit=False)
    rec = build_daily_series(_revenue_rows(repo))[UNIT]
    assert rec["d"] == ["2026-07-20", "2026-07-21"]
    assert rec["req"] == [11_500, None]                                      # fallback day: a gap, not the share
    assert rec["match"] == [round(10_900 / 11_500, 4), None]
    assert rec["show"] == [round(9_800 / 10_900, 4), None]
    assert rec["rev"] == [95.0, 95.0]                                         # revenue: every source, both days


def test_daily_chart_reads_plain_network_rows_as_before():
    repo = InMemoryRepo()
    _net(repo, "2026-07-20", 1_000, 900, 800, 2_000_000)
    rec = build_daily_series(repo.fetch_network())[UNIT]
    assert rec["req"] == [1_000] and rec["match"] == [0.9] and rec["show"] == [round(800 / 900, 4)]


# ── the pull ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_ad_unit_report_spec_has_no_ad_source_and_no_country():
    assert MEDIATION_UNIT_DIMENSIONS == ["DATE", "APP", "AD_UNIT", "FORMAT", "PLATFORM"]
    assert set(MEDIATION_UNIT_METRICS) == {"AD_REQUESTS", "MATCHED_REQUESTS", "IMPRESSIONS", "CLICKS",
                                           "ESTIMATED_EARNINGS"}
    c = AdMobClient("pub-x", "cid", "csec", "rtok")
    c.MAX_ROWS = 50
    seen = []

    def fake_run_report(method, spec):
        rs = spec["reportSpec"]
        seen.append((method, rs["dimensions"], rs["metrics"], rs.get("dimensionFilters")))
        s, e = rs["dateRange"]["startDate"], rs["dateRange"]["endDate"]
        start, end = date(s["year"], s["month"], s["day"]), date(e["year"], e["month"], e["day"])
        true = [{"report_date": start + timedelta(days=i), "app_id": "a", "ad_unit_id": f"u{j}",
                 "ad_requests": 10, "matched_requests": 9, "impressions": 8, "clicks": 0,
                 "estimated_earnings_micros": 1} for i in range((end - start).days + 1) for j in range(20)]
        return true[:c.MAX_ROWS], min(c.MAX_ROWS, len(true))

    c._run_report = fake_run_report
    got = list(c.mediation_unit_report(date(2026, 7, 1), date(2026, 7, 6)))
    assert len(got) == 6 * 20 and not c.truncations                           # split by date: nothing lost
    assert {m for m, *_ in seen} == {"mediationReport"}
    assert all(dims == MEDIATION_UNIT_DIMENSIONS and "AD_SOURCE" not in dims and "COUNTRY" not in dims
               for _, dims, _, _ in seen)
    assert all(r["account_id"] == "pub-x" for r in got)
    seen.clear()
    list(c.mediation_unit_report(date(2026, 7, 1), date(2026, 7, 1),
                                 dim_filters=[{"dimension": "APP", "matchesAny": {"values": ["a"]}}]))
    assert seen[0][3] == [{"dimension": "APP", "matchesAny": {"values": ["a"]}}]


def test_run_once_pulls_the_ad_unit_report_and_the_dashboard_reads_it():
    repo = InMemoryRepo()
    totals = fetcher.run_once([{"account_id": "pub-mock"}], repo, today=date(2026, 7, 23), mode="mock",
                              rolling_days=5)
    mu = repo.fetch_mediation_unit()
    n_units = sum(len(v) for v in MockAdMobClient.UNITS.values())
    assert totals["mediation_unit"] == len(mu) == 6 * n_units                 # every unit-day of the window
    med_req = {}
    for r in repo.fetch_mediation():
        k = (str(r["report_date"]), r["ad_unit_id"])
        med_req[k] = med_req.get(k, 0) + r["ad_requests"]
    want = {(str(r["report_date"]), r["ad_unit_id"]): (r["ad_requests"], r["matched_requests"]) for r in mu}
    assert all(want[k][0] < med_req[k] for k in want)                         # per-source requests overlap
    d = build_from_db(repo, today=date(2026, 7, 23))
    for p in d["placements"]:
        for day, _e, _i, req, matched, _c in p["daily"]:
            assert (req, matched) == want[(day, p["id"])]


def test_a_failing_ad_unit_pull_costs_only_its_rows(monkeypatch):
    def boom(self, start, end, dim_filters=None):
        raise RuntimeError("report error")
        yield                                                                  # pragma: no cover
    monkeypatch.setattr(MockAdMobClient, "mediation_unit_report", boom)
    repo = InMemoryRepo()
    totals = fetcher.run_once([{"account_id": "pub-mock"}], repo, today=date(2026, 7, 23), mode="mock",
                              rolling_days=3)
    assert repo.fetch_network() and repo.fetch_mediation() and repo.fetch_country()
    assert not repo.fetch_mediation_unit() and totals["mediation_unit_errors"] == ["pub-mock"]
    assert {r["req_src"] for r in _revenue_rows(repo)} == {REQ_SRC_NETWORK}   # the marked fallback


def test_filerepo_persists_the_ad_unit_table(tmp_path):
    d = str(tmp_path / "data")
    repo = FileRepo(d)
    repo.init_schema()
    row = dict(_ids(date(2026, 7, 22)), ad_requests=100, matched_requests=90, impressions=80, clicks=1,
               estimated_earnings_micros=1_000)
    repo.upsert_mediation_unit(dict(row))
    repo.upsert_mediation_unit(dict(row, ad_requests=120))                    # same key → refreshed, not added
    assert len(repo.fetch_mediation_unit()) == 1 and repo.fetch_mediation_unit()[0]["ad_requests"] == 120
    repo.flush()
    assert os.path.exists(os.path.join(d, "mediation_unit.json.gz"))
    back = FileRepo(d).fetch_mediation_unit()
    assert len(back) == 1 and back[0]["report_date"] == "2026-07-22" and back[0]["ad_requests"] == 120


def test_wrappers_filter_and_rename_the_ad_unit_table():
    repo = InMemoryRepo()
    _two_source_day(repo, "2026-07-22")
    repo.upsert_mediation_unit(dict(_ids("2026-07-22"), app_id="app~hidden", ad_unit_id="unit~x",
                                    ad_requests=1, matched_requests=1, impressions=1, clicks=0,
                                    estimated_earnings_micros=1))
    hid = build_static._AppFilteredRepo(repo, {"app~hidden"})
    assert {r["app_id"] for r in hid.fetch_mediation_unit()} == {APP}
    ren = build_static._DisambiguatedRepo(repo, app_names={APP: "My Own Name"})
    assert {r["app_name"] for r in ren.fetch_mediation_unit() if r["app_id"] == APP} == {"My Own Name"}


def test_per_app_backfill_pulls_the_ad_unit_report_for_a_ticked_app(tmp_path):
    data, cfg = tmp_path / "data", tmp_path / "config"
    data.mkdir(); cfg.mkdir()
    (cfg / "selected_apps.json").write_text(json.dumps(
        {"accounts": {"pub-mock": {"decided": True, "selected": ["app~puzzle"]}}}))
    repo = InMemoryRepo()
    build_static._backfill_network_selected_apps(
        [{"account_id": "pub-mock"}], repo, date(2026, 7, 23), mode="mock", client_id=None, client_secret=None,
        currency="USD", max_lookback=400, data_dir=str(data))
    mu = repo.fetch_mediation_unit()
    assert mu and {r["app_id"] for r in mu} == {"app~puzzle"}
    assert min(str(r["report_date"]) for r in mu) == min(str(r["report_date"]) for r in repo.fetch_network())


# ── the one-time history backfill: marker, chunks, budget, resume ───────────────────────────────────────────

class _FakeClient:
    """Records every (start, end) the backfill asks for; yields one row per unit-day."""

    def __init__(self, account_id, log, fail_on=None):
        self.account_id, self.log, self.fail_on, self.truncations = account_id, log, fail_on or set(), []

    def mediation_unit_report(self, start, end, dim_filters=None):
        self.log.append((self.account_id, start, end))
        if (self.account_id, start, end) in self.fail_on:
            raise RuntimeError("report error")
        d = start
        while d <= end:
            yield {"report_date": d, "account_id": self.account_id, "app_id": self.account_id + "~app",
                   "ad_unit_id": self.account_id + "/u1", "format": "banner", "platform": "Android",
                   "ad_requests": 10, "matched_requests": 9, "impressions": 8, "clicks": 0,
                   "estimated_earnings_micros": 5}
            d += timedelta(days=1)


TODAY = date(2026, 7, 23)
STARTS = {"pub-a": date(2026, 1, 5), "pub-b": date(2026, 5, 20)}


def _stored_history_repo():
    repo = InMemoryRepo()
    for acc, st in STARTS.items():
        for d in (st, TODAY - timedelta(days=2)):
            repo.upsert_network(dict(account_id=acc, app_id=acc + "~app", ad_unit_id=acc + "/u1",
                                     report_date=d.isoformat(), ad_requests=1, matched_requests=1,
                                     impressions=1, clicks=0, estimated_earnings_micros=1))
    return repo


@pytest.fixture
def fake_clients(monkeypatch):
    log, fail = [], set()
    monkeypatch.setattr(fetcher, "make_client",
                        lambda acct, mode="mock", *a, **k: _FakeClient(acct["account_id"], log, fail))
    return log, fail


def _bf(repo, data_dir, budget=1e9, clock=None, accounts=None):
    accounts = accounts if accounts is not None else [{"account_id": a} for a in STARTS]
    return build_static._backfill_mediation_unit_history(
        accounts, repo, TODAY, mode="mock", client_id=None, client_secret=None, currency="USD",
        data_dir=str(data_dir), budget_sec=budget, clock=clock)


def test_backfill_covers_the_whole_history_in_contiguous_chunks(tmp_path, fake_clients):
    log, _ = fake_clients
    repo = _stored_history_repo()
    state, done, info = _bf(repo, tmp_path)
    assert done and info["chunks"] == len(log)
    for acc, st in STARTS.items():
        chunks = [(s, e) for a, s, e in log if a == acc]
        assert chunks[0][1] == TODAY - timedelta(days=1)                       # newest first, from yesterday
        assert chunks[-1][0] == st                                              # down to the history start
        for (s, e), (s2, e2) in zip(chunks, chunks[1:]):
            assert e2 == s - timedelta(days=1)                                  # contiguous: no gap, no overlap
        assert all((e - s).days + 1 <= build_static.MU_CHUNK_DAYS for s, e in chunks)
        got = {str(r["report_date"]) for r in repo.fetch_mediation_unit() if r["account_id"] == acc}
        assert len(got) == (TODAY - st).days                                    # every day start … yesterday
    build_static._save_mu_backfill(str(tmp_path), state, done)
    assert os.path.exists(tmp_path / build_static.MU_MARKER)
    log.clear()
    assert _bf(repo, tmp_path)[1] and not log                                   # marked: never runs again


def test_backfill_stops_at_the_budget_and_resumes_where_it_stopped(tmp_path, fake_clients):
    log, _ = fake_clients
    repo = _stored_history_repo()
    tick = {"t": 0.0}

    def clock():
        tick["t"] += 1.0                                                        # each check = one second
        return tick["t"]

    runs = 0
    while True:
        runs += 1
        state, done, info = _bf(repo, tmp_path, budget=4, clock=clock)
        assert info["chunks"] <= 4
        build_static._save_mu_backfill(str(tmp_path), state, done)
        if done:
            break
        assert not os.path.exists(tmp_path / build_static.MU_MARKER)
        assert runs < 50
    assert runs > 1                                                             # it really took several runs
    for acc, st in STARTS.items():
        spans = sorted((s, e) for a, s, e in log if a == acc)
        assert spans[0][0] == st and spans[-1][1] == TODAY - timedelta(days=1)
        for (s, e), (s2, e2) in zip(spans, spans[1:]):
            assert s2 == e + timedelta(days=1)                                  # resumed exactly, no repeats
    saved = json.load(open(tmp_path / build_static.MU_STATE_FILE))
    assert all(v["done"] for v in saved["accounts"].values())


def test_a_failed_chunk_is_retried_next_run_and_the_others_go_on(tmp_path, fake_clients):
    log, fail = fake_clients
    repo = _stored_history_repo()
    first = (TODAY - timedelta(days=build_static.MU_CHUNK_DAYS), TODAY - timedelta(days=1))
    fail.add(("pub-a",) + first)
    state, done, _ = _bf(repo, tmp_path)
    assert not done
    assert state["accounts"]["pub-a"]["next_end"] == first[1].isoformat()       # not advanced
    assert state["accounts"]["pub-b"]["done"]                                   # the other account finished
    build_static._save_mu_backfill(str(tmp_path), state, done)
    fail.clear(); log.clear()
    state, done, _ = _bf(repo, tmp_path)
    assert done and log[0] == ("pub-a",) + first                                # the same chunk, retried
    assert all(a == "pub-a" for a, _s, _e in log)


def test_backfill_skips_an_account_no_longer_configured(tmp_path, fake_clients):
    log, _ = fake_clients
    repo = _stored_history_repo()
    state, done, _ = _bf(repo, tmp_path, budget=0)                              # both accounts enter the state
    build_static._save_mu_backfill(str(tmp_path), state, done)
    assert set(state["accounts"]) == {"pub-a", "pub-b"} and not done
    log.clear()
    state, done, _ = _bf(repo, tmp_path, accounts=[{"account_id": "pub-a"}])    # pub-b's token removed since
    assert done and state["accounts"]["pub-b"]["done"] and state["accounts"]["pub-b"]["note"]
    assert {a for a, _s, _e in log} == {"pub-a"}


def test_backfill_only_tracks_accounts_with_stored_history(tmp_path, fake_clients):
    """An account with no stored rows yet is not part of the one-time pull — its apps' whole history comes
    through the per-app backfill (which pulls this report too)."""
    log, _ = fake_clients
    accounts = [{"account_id": a} for a in list(STARTS) + ["pub-new"]]
    state, done, _ = _bf(_stored_history_repo(), tmp_path, accounts=accounts)
    assert done and set(state["accounts"]) == set(STARTS)
    assert "pub-new" not in {a for a, _s, _e in log}


def test_backfill_progress_is_saved_only_with_the_data(tmp_path, fake_clients, monkeypatch):
    """build() saves the progress file AFTER repo.flush(): a run that dies before the flush records nothing,
    so its chunks are simply pulled again."""
    import inspect
    src = inspect.getsource(build_static.build)
    assert src.index("_backfill_mediation_unit_history(") < src.index("repo.flush()") \
        < src.index("_save_mu_backfill(")
    state, done, _ = _bf(_stored_history_repo(), tmp_path, budget=0)
    assert not done and not os.listdir(tmp_path)                               # the function itself writes nothing
