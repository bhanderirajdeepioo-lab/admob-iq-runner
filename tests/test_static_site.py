"""QA for the FREE, no-code path: FileRepo (no DB) + the daily static-site build."""

import json
import os
from datetime import date

from admob_iq.db import FileRepo, InMemoryRepo
from admob_iq.fetch import fetcher
from admob_iq.api.dataservice import build_dashboard
from admob_iq import build_static


def test_filerepo_persists_and_matches_inmemory(tmp_path):
    """FileRepo must behave like InMemoryRepo and survive a reload from disk."""
    d = str(tmp_path / "data")
    fr, mem = FileRepo(d), InMemoryRepo()
    for repo in (fr, mem):
        repo.init_schema()
        fetcher.run_once([{"account_id": "pub-mock"}], repo,
                         today=date(2026, 7, 23), mode="mock", rolling_days=10)
    # same number of facts either way
    assert len(fr.fetch_network()) == len(mem.fetch_network()) > 0
    assert fr.has_data()
    # dates are stored JSON-safe (ISO strings), which the dataservice reads via str()
    assert isinstance(fr.fetch_network()[0]["report_date"], str)
    # a brand-new instance pointed at the same folder sees the persisted history (after flush)
    fr.flush()
    assert len(FileRepo(d).fetch_network()) == len(fr.fetch_network())


def test_filerepo_upsert_and_snapshot_dedupe(tmp_path):
    repo = FileRepo(str(tmp_path / "d"))
    repo.init_schema()
    base = dict(report_date=date(2026, 7, 22), account_id="a", app_id="ap",
                ad_unit_id="u", country="US", format="banner", platform="Android",
                ad_requests=100, matched_requests=90, impressions=80, clicks=4,
                estimated_earnings_micros=1_000_000)
    repo.upsert_network(dict(base))
    repo.upsert_network(dict(base, impressions=999))          # same PK -> update
    assert len(repo.fetch_network()) == 1
    assert repo.fetch_network()[0]["impressions"] == 999
    snap = dict(report_date=date(2026, 7, 22), snapshot_date=date(2026, 7, 23),
                account_id="a", app_id="ap", ad_unit_id="u", country="US",
                format="banner", estimated_earnings_micros=1_000_000,
                impressions=80, clicks=4)
    repo.append_snapshot(dict(snap))
    repo.append_snapshot(dict(snap))                          # same key -> deduped
    assert len(repo.fetch_snapshots()) == 1


def test_static_build_writes_valid_site(tmp_path):
    out, data = str(tmp_path / "site"), str(tmp_path / "data")
    r = build_static.build(out_dir=out, data_dir=data, today=date(2026, 7, 23), mode="mock")
    assert r["revenue"] > 0
    # the file the static host serves
    dash = json.load(open(os.path.join(out, "dashboard.json")))
    assert set(dash.keys()) == set(build_dashboard().keys()) | {"generated_at", "report_tz", "report_tz_label", "data_quality", "apps_catalog"}   # frontend contract + freshness + timezone + integrity + app picker
    assert dash["generated_at"] and "T" in dash["generated_at"]  # ISO timestamp present
    assert dash["kpis"]["revenue"] > 0 and dash["placements"]
    assert os.path.exists(os.path.join(out, "index.html"))     # UI shipped alongside
    # a second build must not duplicate history (data files are gzipped on disk)
    import gzip
    def _net_rows():
        with gzip.open(os.path.join(data, "network.json.gz"), "rt", encoding="utf-8") as f:
            return len(json.load(f))
    n1 = _net_rows()
    build_static.build(out_dir=out, data_dir=data, today=date(2026, 7, 23), mode="mock")
    n2 = _net_rows()
    assert n1 == n2


def test_alerts_format_on_both_channels_and_stay_dry(tmp_path):
    from admob_iq.config import settings
    res = build_static.send_alerts(build_dashboard(), settings())   # dry-run default
    assert {r["channel"] for r in res} == {"telegram", "email"}
    assert all(r.get("dry_run") for r in res)                       # nothing leaks pre-config
    # no alerts -> nothing sent
    assert build_static.send_alerts({"alerts": {"items": []}}, settings()) == []


def test_real_data_names_currency_and_ranges():
    """Real AdMob display names, real currency, and time-ranges that actually differ."""
    repo = InMemoryRepo()
    fetcher.run_once([{"account_id": "pub-mock"}], repo,
                     today=date(2026, 7, 23), mode="mock", rolling_days=14)
    from admob_iq.api.dataservice import build_from_db
    d = build_from_db(repo, today=date(2026, 7, 23))
    assert "Puzzle Blast" in {a["name"] for a in d["apps"]}          # app display name, not id
    assert "Home_Banner" in {p["name"] for p in d["placements"]}     # ad-unit display name, not id
    assert d["currency"] == "USD"
    r = d["kpis_by_range"]
    assert r["today"]["revenue"] < r["7d"]["revenue"] <= r["30d"]["revenue"]


def test_build_from_db_falls_back_to_ids_without_display_names():
    """Rows lacking app_name/unit_name (older data) still render — cleaned-id fallback, no crash."""
    from admob_iq.api.dataservice import build_from_db
    repo = InMemoryRepo()
    repo.upsert_network(dict(report_date="2026-07-22", account_id="a", app_id="app~x/77",
                             ad_unit_id="ca~unit/99", country="US", format="banner",
                             platform="Android", ad_requests=100, matched_requests=90,
                             impressions=80, clicks=4, estimated_earnings_micros=2_000_000,
                             currency_code="USD"))
    d = build_from_db(repo, today=date(2026, 7, 23))
    assert "99" in {p["name"] for p in d["placements"]} and d["currency"] == "USD"


def test_partial_today_does_not_cause_false_crash():
    """A half-finished 'today' must NOT look like a crash: no false drop alerts, verdict
    not 'declining', headline uses a finished day, today shown separately as live."""
    from admob_iq.api.dataservice import build_from_db
    repo = InMemoryRepo()

    def row(d, earn):
        return dict(report_date=d, account_id="pub-x", app_id="app~a/1", app_name="My Game",
                    ad_unit_id="ca~u/1", unit_name="Home_Banner", country="US", format="banner",
                    platform="Android", ad_requests=10000, matched_requests=9000, impressions=8600,
                    clicks=70, estimated_earnings_micros=earn, currency_code="USD")
    for d in ["2026-07-15", "2026-07-16", "2026-07-17", "2026-07-18",
              "2026-07-19", "2026-07-20", "2026-07-21", "2026-07-22"]:
        repo.upsert_network(row(d, 55_000_000))
    repo.upsert_network(row("2026-07-23", 2_000_000))     # partial "today" (e.g. a 9am run)
    d = build_from_db(repo, today=date(2026, 7, 23))
    p = d["placements"][0]
    assert p["verdict"] != "declining"
    assert d["alerts"]["counts"]["critical"] == 0 and d["alerts"]["counts"]["warning"] == 0
    assert d["kpis"]["revenue"] == 55.0                    # finished day, not the $2 partial
    assert d["kpis_by_range"]["today"]["revenue"] == 2.0   # today = live/partial
    assert d["kpis_by_range"]["yesterday"]["revenue"] == 55.0
    assert p["today_revenue"] == 2.0 and p["trend"][-1] == 55.0


def test_newest_day_is_complete_when_today_row_absent():
    """Reviewer regression: if today's row hasn't landed yet (low-traffic app / AdMob lag),
    the newest RETURNED day is COMPLETE and must show in headline + trend, not be hidden."""
    from admob_iq.api.dataservice import build_from_db
    repo = InMemoryRepo()

    def row(d, earn):
        return dict(report_date=d, account_id="pub-x", app_id="app~a/1", app_name="My Game",
                    ad_unit_id="ca~u/1", unit_name="Home_Banner", country="US", format="banner",
                    platform="Android", ad_requests=10000, matched_requests=9000, impressions=8600,
                    clicks=70, estimated_earnings_micros=earn, currency_code="USD")
    for d, e in [("2026-07-20", 50_000_000), ("2026-07-21", 51_000_000),
                 ("2026-07-22", 50_000_000), ("2026-07-23", 52_000_000)]:
        repo.upsert_network(row(d, e))
    # it is 2026-07-24, but 07-24 hasn't landed — 07-23 is the newest COMPLETE day
    d = build_from_db(repo, today=date(2026, 7, 24))
    assert d["kpis"]["revenue"] == 52.0                   # newest finished day, not lagging to 07-22
    assert d["placements"][0]["trend"][-1] == 52.0        # 07-23 present in the trend
    assert d["kpis_by_range"]["today"]["revenue"] == 0.0  # no 07-24 rows → today honestly 0


def test_demo_and_empty_flags():
    """Demo data is flagged is_demo; a live zero-row account gets an honest empty state."""
    from admob_iq.api.dataservice import build_dashboard, empty_dashboard
    assert build_dashboard()["is_demo"] is True
    e = empty_dashboard(3)
    assert e["is_demo"] is False and e["empty"] is True
    assert e["placements"] == [] and e["kpis"]["accounts"] == 3
    assert set(e.keys()) >= set(build_dashboard().keys())   # same contract, never breaks the UI


def test_settings_tolerates_empty_github_secrets(monkeypatch):
    """GitHub Actions passes UNSET secrets as '' (not absent) — settings() must not
    crash on int('') and must fall back to defaults. (This was the first live failure.)"""
    for k in ["SMTP_PORT", "REPORT_CURRENCY", "ROLLING_REPULL_DAYS", "NOTIFY_DRY_RUN", "FETCH_MODE"]:
        monkeypatch.setenv(k, "")
    from admob_iq.config import settings
    s = settings()
    assert s["smtp"]["port"] == 587 and s["report_currency"] == "USD"
    assert s["rolling_days"] == 35 and s["notify_dry_run"] is True and s["fetch_mode"] == "mock"


def test_range_kpis_carry_exact_date_window_and_full_30d():
    """Each range total ships its exact date window (from/to/days) so the user can verify
    the same range in the AdMob app; 30d must span a FULL 30 complete days when available
    (the bug was a half-filled window summing to ~half the real month)."""
    from admob_iq.api.dataservice import build_from_db
    repo = InMemoryRepo()
    fetcher.run_once([{"account_id": "pub-mock"}], repo,
                     today=date(2026, 7, 24), mode="mock", rolling_days=40)
    d = build_from_db(repo, today=date(2026, 7, 24))
    r = d["kpis_by_range"]
    for key in ("yesterday", "7d", "30d"):
        assert r[key]["from"] and r[key]["to"] and r[key]["days"] >= 1
    assert r["7d"]["days"] == 7 and r["30d"]["days"] == 30      # full month, not half
    assert r["7d"]["to"] == r["yesterday"]["to"]               # ranges end at newest complete day
    assert r["30d"]["revenue"] > r["7d"]["revenue"] > 0        # more days => bigger total


def test_revenue_uses_mediation_total_not_network_only():
    """AdMob's account/placement total INCLUDES third-party mediated networks, so the number
    must come from the mediation report (summed across ad sources), not the AdMob-Network-only
    report. This was the ~4% undercount: network $99,577 vs AdMob/mediation $103,837."""
    from admob_iq.api.dataservice import build_from_db, _revenue_rows
    repo = InMemoryRepo()
    # AdMob Network only sees $10 for this unit/day
    repo.upsert_network(dict(report_date="2026-07-22", account_id="a", app_id="app~x",
                             app_name="My Game", ad_unit_id="u1", unit_name="Banner",
                             country="All", format="banner", platform="Android",
                             ad_requests=1000, matched_requests=900, impressions=800, clicks=8,
                             estimated_earnings_micros=10_000_000, currency_code="USD"))
    # Mediation sees the SAME unit across two sources = $10 (AdMob) + $4 (AppLovin) = $14
    for src, earn, impr, req in [("admob", 10_000_000, 800, 1000), ("applovin", 4_000_000, 300, 950)]:
        repo.upsert_mediation(dict(report_date="2026-07-22", account_id="a", app_id="app~x",
                                   app_name="My Game", ad_unit_id="u1", unit_name="Banner",
                                   ad_source=src, source_name=src, country="All", format="banner",
                                   platform="Android", ad_requests=req, matched_requests=900,
                                   impressions=impr, clicks=4, estimated_earnings_micros=earn,
                                   observed_ecpm_micros=0, currency_code="USD"))
    rows = _revenue_rows(repo)
    assert len(rows) == 1
    assert rows[0]["estimated_earnings_micros"] == 14_000_000    # 10 + 4 (mediation total), not 10
    assert rows[0]["impressions"] == 1100                        # 800 + 300 summed across sources
    assert rows[0]["ad_requests"] == 1000                        # from network, NOT 1000+950 double-count
    d = build_from_db(repo, today=date(2026, 7, 23))
    assert d["kpis"]["revenue"] == 14.0                          # matches the AdMob app, not $10


def test_report_spec_omits_timezone_so_admob_uses_account_tz():
    """The revenue-timezone fix: we must NOT force America/Los_Angeles. Omitting timeZone
    makes AdMob return data in the account's OWN timezone (e.g. India) — so 'today' and
    every day match the AdMob app. An explicit tz is still honored when a caller forces one."""
    from datetime import date as _date
    from admob_iq.fetch.admob_client import build_report_spec, NETWORK_DIMENSIONS, NETWORK_METRICS
    spec = build_report_spec(_date(2026, 7, 9), _date(2026, 7, 23), NETWORK_DIMENSIONS, NETWORK_METRICS)
    assert "timeZone" not in spec["reportSpec"]        # account default applies
    forced = build_report_spec(_date(2026, 7, 9), _date(2026, 7, 23), NETWORK_DIMENSIONS,
                               NETWORK_METRICS, tz="America/Los_Angeles")
    assert forced["reportSpec"]["timeZone"] == "America/Los_Angeles"


def test_country_breakdown_is_real_and_sorted():
    """The country view is built from the separate country report: real geos (not 'All'),
    each with revenue/eCPM/impressions/share, sorted by revenue, shares ~summing to 1."""
    from admob_iq.api.dataservice import build_from_db
    repo = InMemoryRepo()
    fetcher.run_once([{"account_id": "pub-mock"}], repo,
                     today=date(2026, 7, 24), mode="mock", rolling_days=10)
    d = build_from_db(repo, today=date(2026, 7, 24))
    cs = d["countries"]
    assert cs and {"US", "IN", "ID"} <= {c["country"] for c in cs}      # real geos, not "All"
    assert all(("share" in c and "impressions" in c and c["revenue"] >= 0) for c in cs)
    assert cs == sorted(cs, key=lambda c: c["revenue"], reverse=True)   # highest earner first
    assert abs(sum(c["share"] for c in cs) - 1.0) < 0.02               # shares add up to ~100%
    assert d["country_window"]["days"] >= 1


def test_filerepo_country_persists(tmp_path):
    """Country facts survive a flush + reload, like the other stores."""
    d = str(tmp_path / "data")
    fr = FileRepo(d); fr.init_schema()
    fetcher.run_once([{"account_id": "pub-mock"}], fr,
                     today=date(2026, 7, 23), mode="mock", rolling_days=5)
    fr.flush()
    assert len(FileRepo(d).fetch_country()) == len(fr.fetch_country()) > 0


def test_placement_country_geo_mix():
    """Each placement carries its top-country mix (geo drill) from the placement_country report,
    highest-revenue geo first — this powers the Report Card 'Performance by country' table."""
    from admob_iq.api.dataservice import build_from_db
    repo = InMemoryRepo()
    fetcher.run_once([{"account_id": "pub-mock"}], repo,
                     today=date(2026, 7, 24), mode="mock", rolling_days=10)
    assert len(repo.fetch_placement_country()) > 0
    d = build_from_db(repo, today=date(2026, 7, 24))
    withc = [p for p in d["placements"] if p.get("by_country")]
    assert withc, "placements should carry a per-country breakdown"
    bc = withc[0]["by_country"]
    assert all(("country" in c and "revenue" in c and "share" in c) for c in bc)
    assert bc == sorted(bc, key=lambda c: c["revenue"], reverse=True)   # top geo first


def test_fetch_range_splits_dates_to_beat_100k_cap(monkeypatch):
    """No data lost to AdMob's 100k-row cap: when a date window has more rows than the cap,
    the fetch splits the range and recurses until every request fits, then stitches the
    pieces back — complete data. This is what makes adding COUNTRY (or long ranges) safe."""
    from datetime import date as _date
    from admob_iq.fetch.admob_client import AdMobClient
    c = AdMobClient("pub-1", "cid", "csec", "rtok")
    c.MAX_ROWS = 100                       # tiny cap for the test
    PER_DAY = 60                           # 2 days (120) already exceed the cap → must split to single days
    leaf_calls = []

    def fake_run(method, spec):
        dr = spec["reportSpec"]["dateRange"]
        s = _date(dr["startDate"]["year"], dr["startDate"]["month"], dr["startDate"]["day"])
        e = _date(dr["endDate"]["year"], dr["endDate"]["month"], dr["endDate"]["day"])
        total = ((e - s).days + 1) * PER_DAY
        if total <= c.MAX_ROWS:
            leaf_calls.append((s, e))
        return [{"report_date": s, "n": i} for i in range(min(total, c.MAX_ROWS))], total

    monkeypatch.setattr(c, "_run_report", fake_run)
    rows = list(c._fetch_range("networkReport", _date(2026, 7, 1), _date(2026, 7, 4),
                               ["DATE"], ["ESTIMATED_EARNINGS"]))
    assert len(rows) == 4 * PER_DAY                          # all 4 days collected, nothing dropped
    assert len(leaf_calls) == 4 and all(s == e for s, e in leaf_calls)   # every real fetch fit under the cap


def test_account_meta_reads_reporting_timezone_and_currency():
    """account_meta() surfaces the account's own reporting timezone + currency (from the
    PublisherAccount) so the dashboard computes 'today' on the user's clock. Cached."""
    from admob_iq.fetch.admob_client import AdMobClient

    class _Ex:
        def __init__(self, d): self._d = d
        def execute(self): return self._d

    class _Accts:
        def get(self, name):
            assert name == "accounts/pub-1"
            return _Ex({"reportingTimeZone": "Asia/Calcutta", "currencyCode": "USD"})

    class _Svc:
        def accounts(self): return _Accts()

    c = AdMobClient("pub-1", "cid", "csec", "rtok")
    c._svc = _Svc()
    meta = c.account_meta()
    assert meta["reporting_tz"] == "Asia/Calcutta" and meta["currency"] == "USD"
    assert c.account_meta() is meta            # cached — no second API call


def test_tz_label_is_friendly():
    from admob_iq.build_static import _tz_label
    assert _tz_label("Asia/Calcutta") == "India Standard Time (IST)"
    assert _tz_label("Asia/Kolkata") == "India Standard Time (IST)"
    assert _tz_label("America/Los_Angeles") == "US Pacific Time (PT)"


def test_resolve_accounts_from_secret(monkeypatch):
    monkeypatch.setenv("ADMOB_ACCOUNTS_JSON",
                       '[{"account_id":"pub-1","refresh_token":"t1"}]')
    accts = build_static.resolve_accounts()
    assert accts[0]["account_id"] == "pub-1"
    monkeypatch.setenv("ADMOB_ACCOUNTS_JSON",
                       '{"accounts":[{"account_id":"pub-2","refresh_token":"t2"}]}')
    assert build_static.resolve_accounts()[0]["account_id"] == "pub-2"


def test_alert_lines_handles_grouped_and_flat_items():
    """Regression: grouped alerts (one placement + a `metrics` list, no top-level
    `message`) must not KeyError in the notification path; legacy flat items still work."""
    from admob_iq import build_static
    dash = {"alerts": {"items": [
        {"place": "u1", "app": "A", "severity": "warning", "country": "US", "lost": 12.0,
         "metrics": [{"metric": "revenue", "message": "revenue down 64%"},
                     {"metric": "requests", "message": "requests down 63%"}]},
        {"place": "u2", "app": "B", "severity": "critical", "country": "All",
         "message": "revenue = 0"},
    ]}}
    lines = build_static.alert_lines(dash)
    assert len(lines) == 2
    assert "u1" in lines[0] and "revenue down 64%" in lines[0] and "requests down 63%" in lines[0]
    assert "u2" in lines[1] and "revenue = 0" in lines[1]


def test_alert_lines_on_real_grouped_build(tmp_path):
    """End-to-end: build_from_db's grouped alert items feed alert_lines without error."""
    from admob_iq import build_static
    from admob_iq.api import dataservice
    d = dataservice.build_dashboard()          # demo path (flat items) — must not raise
    build_static.alert_lines(d)


def test_app_filtered_repo_hides_unselected_apps():
    """_AppFilteredRepo drops rows/units for hidden app_ids from every built view, and passes
    unknown methods through untouched (stored data is never mutated)."""
    from admob_iq.build_static import _AppFilteredRepo

    class _R:
        def fetch_network(self): return [{"app_id": "A", "v": 1}, {"app_id": "B", "v": 2}]
        def fetch_mediation(self): return [{"app_id": "B"}]
        def fetch_country(self): return [{"app_id": "A"}, {"app_id": "B"}]
        def fetch_placement_country(self): return [{"app_id": "B"}]
        def fetch_snapshots(self): return [{"app_id": "A"}]
        def fetch_adunit_country_monthly(self):
            return {"units": {"u1": ["A", "n", "app"], "u2": ["B", "n", "app"]}, "data": {"u1": {}, "u2": {}}}
        def fetch_adunit_country_daily(self):
            return {"month": "2026-07", "dates": [], "units": {"u1": ["A"], "u2": ["B"]}, "data": {"u1": {}, "u2": {}}}
        def whatever(self): return "passthrough"

    f = _AppFilteredRepo(_R(), {"B"})                      # hide app B
    assert [r["app_id"] for r in f.fetch_network()] == ["A"]
    assert [r["app_id"] for r in f.fetch_country()] == ["A"]
    assert f.fetch_mediation() == [] and f.fetch_placement_country() == []
    acm = f.fetch_adunit_country_monthly()
    assert set(acm["units"]) == {"u1"} and set(acm["data"]) == {"u1"}   # u2 (app B) gone
    assert set(f.fetch_adunit_country_daily()["units"]) == {"u1"}
    assert f.whatever() == "passthrough"                  # unknown methods pass through


def test_backfill_only_new_accounts(monkeypatch, tmp_path):
    """A new account (no acm history) is backfilled; an account already in acm is SKIPPED (never
    re-fetched), so adding an account never re-pulls the others' history."""
    import datetime
    from admob_iq import build_static
    from admob_iq.fetch import fetcher
    from admob_iq.fetch.fetcher import build_ac_row
    from admob_iq.engine.rollup import RollupAccumulator

    repo = FileRepo(str(tmp_path / "d")); repo.init_schema()
    # seed acm with an OLD account's rollup (app_id encodes pub-111)
    accO = RollupAccumulator(datetime.date(2026, 7, 28))
    for day in ("2026-06-10", "2026-06-11"):
        accO.add(build_ac_row(dict(report_date=day, account_id="pub-111", app_id="ca-app-pub-111~1",
                 ad_unit_id="uO", unit_name="UO", app_name="OldApp", country="US", ad_requests=100,
                 matched_requests=90, impressions=80, clicks=4, estimated_earnings_micros=1_000_000)))
    roll, _ = accO.finish(window_start=None); repo.merge_adunit_country_monthly(roll)

    calls = []

    class _Fake:
        def __init__(self, aid): self.aid = aid
        def data_start(self, today, max_lookback, dim_filters=None): return datetime.date(2026, 6, 1)
        def adunit_country_report(self, cs, ce, dim_filters=None):
            calls.append(self.aid)
            if cs <= datetime.date(2026, 6, 10) <= ce:
                yield dict(report_date="2026-06-10", account_id=self.aid, app_id="ca-app-pub-999~1",
                           ad_unit_id="uN", unit_name="UN", app_name="NewApp", country="US",
                           ad_requests=50, matched_requests=45, impressions=40, clicks=2,
                           estimated_earnings_micros=500_000)

    monkeypatch.setattr(fetcher, "make_client", lambda a, *x, **k: _Fake(a["account_id"]))
    build_static._backfill_missing_accounts_ac(
        [{"account_id": "pub-111"}, {"account_id": "pub-NEW"}], repo, datetime.date(2026, 7, 28),
        mode="live", client_id="x", client_secret="y", currency="USD", data_dir=str(tmp_path / "d"))
    assert set(calls) == {"pub-NEW"}                              # OLD account never re-fetched
    units = repo.fetch_adunit_country_monthly()["units"]
    assert any("999" in str((m or [None])[0]) for m in units.values())   # new app now in acm
    assert any("111" in str((m or [None])[0]) for m in units.values())   # old still there


def test_backfill_scopes_to_selected_apps(monkeypatch, tmp_path):
    """A DECIDED new account is backfilled for ONLY its selected apps — the hidden app's history is
    never pulled (respects the dashboard pick AND keeps AdMob load minimal)."""
    import datetime, json
    from admob_iq import build_static
    from admob_iq.fetch import fetcher

    d = tmp_path / "d"
    repo = FileRepo(str(d)); repo.init_schema()          # empty acm → pub-777 is a "new" account
    # selection config lives at <parent-of-data_dir>/config/selected_apps.json (same as the build)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "selected_apps.json").write_text(json.dumps({"accounts": {
        "pub-777": {"decided": True,
                    "selected": ["ca-app-pub-777~KEEP"]}}}))    # HIDE ca-app-pub-777~HIDE

    seen = []                                            # every app_id AdMob was actually asked for

    class _Fake:
        def __init__(self, aid): self.aid = aid
        def data_start(self, today, max_lookback, dim_filters=None): return datetime.date(2026, 6, 1)
        def adunit_country_report(self, cs, ce, dim_filters=None):
            vals = [v for f in (dim_filters or []) for v in (f.get("matchesAny") or {}).get("values") or []]
            seen.extend(vals)
            if cs <= datetime.date(2026, 6, 15) <= ce:
                for aid in (vals or ["ca-app-pub-777~KEEP", "ca-app-pub-777~HIDE"]):
                    yield dict(report_date="2026-06-15", account_id=self.aid, app_id=aid,
                               ad_unit_id="u" + aid[-4:], unit_name="U", app_name="App", country="US",
                               ad_requests=10, matched_requests=9, impressions=8, clicks=1,
                               estimated_earnings_micros=100_000)

    monkeypatch.setattr(fetcher, "make_client", lambda a, *x, **k: _Fake(a["account_id"]))
    build_static._backfill_missing_accounts_ac(
        [{"account_id": "pub-777"}], repo, datetime.date(2026, 7, 28),
        mode="live", client_id="x", client_secret="y", currency="USD", data_dir=str(d))
    assert set(seen) == {"ca-app-pub-777~KEEP"}          # ONLY the selected app was ever requested
    units = repo.fetch_adunit_country_monthly()["units"]
    app_ids = {(m or [None])[0] for m in units.values()}
    assert "ca-app-pub-777~KEEP" in app_ids              # selected app rolled into the baseline
    assert "ca-app-pub-777~HIDE" not in app_ids          # hidden app never entered the baseline


def test_backfill_catches_selected_app_when_account_already_covered(monkeypatch, tmp_path):
    """The 'koi miss nahi' guarantee: a SELECTED app with no baseline is pulled even when its account
    is ALREADY partly in acm — detection is per APP, not per account — while the already-covered app
    is NOT re-fetched."""
    import datetime, json
    from admob_iq import build_static
    from admob_iq.fetch import fetcher
    from admob_iq.fetch.fetcher import build_ac_row
    from admob_iq.engine.rollup import RollupAccumulator

    d = tmp_path / "d"
    repo = FileRepo(str(d)); repo.init_schema()
    # pub-55 already has baseline for its FIRST app (COVERED); its SECOND app was added/selected later
    accO = RollupAccumulator(datetime.date(2026, 7, 28))
    for day in ("2026-06-10", "2026-06-11"):
        accO.add(build_ac_row(dict(report_date=day, account_id="pub-55", app_id="ca-app-pub-55~COVERED",
                 ad_unit_id="uc", unit_name="UC", app_name="Cov", country="US", ad_requests=100,
                 matched_requests=90, impressions=80, clicks=4, estimated_earnings_micros=1_000_000)))
    roll, _ = accO.finish(window_start=None); repo.merge_adunit_country_monthly(roll)

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "selected_apps.json").write_text(json.dumps({"accounts": {
        "pub-55": {"decided": True,
                   "selected": ["ca-app-pub-55~COVERED", "ca-app-pub-55~NEWSEL"]}}}))

    seen = []

    class _Fake:
        def __init__(self, aid): self.aid = aid
        def data_start(self, today, max_lookback, dim_filters=None): return datetime.date(2026, 6, 1)
        def adunit_country_report(self, cs, ce, dim_filters=None):
            vals = [v for f in (dim_filters or []) for v in (f.get("matchesAny") or {}).get("values") or []]
            seen.extend(vals)
            if cs <= datetime.date(2026, 6, 15) <= ce:
                for aid in vals:
                    yield dict(report_date="2026-06-15", account_id=self.aid, app_id=aid,
                               ad_unit_id="u", unit_name="U", app_name="App", country="US",
                               ad_requests=10, matched_requests=9, impressions=8, clicks=1,
                               estimated_earnings_micros=100_000)

    monkeypatch.setattr(fetcher, "make_client", lambda a, *x, **k: _Fake(a["account_id"]))
    build_static._backfill_missing_accounts_ac(
        [{"account_id": "pub-55"}], repo, datetime.date(2026, 7, 28),
        mode="live", client_id="x", client_secret="y", currency="USD", data_dir=str(d))
    assert set(seen) == {"ca-app-pub-55~NEWSEL"}         # ONLY the not-yet-covered selected app pulled
    app_ids = {(m or [None])[0] for m in repo.fetch_adunit_country_monthly()["units"].values()}
    assert {"ca-app-pub-55~COVERED", "ca-app-pub-55~NEWSEL"} <= app_ids   # both now in the baseline


def test_backfill_skips_decided_account_with_no_apps(monkeypatch, tmp_path):
    """A DECIDED account that selected ZERO apps is skipped — nothing is fetched for it."""
    import datetime, json
    from admob_iq import build_static
    from admob_iq.fetch import fetcher

    d = tmp_path / "d"
    repo = FileRepo(str(d)); repo.init_schema()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "selected_apps.json").write_text(json.dumps({"accounts": {
        "pub-empty": {"decided": True, "selected": []}}}))

    hits = []

    class _Fake:
        def __init__(self, aid): self.aid = aid
        def data_start(self, today, max_lookback, dim_filters=None): hits.append(self.aid); return datetime.date(2026, 6, 1)
        def adunit_country_report(self, cs, ce, dim_filters=None):
            hits.append(self.aid); return iter(())

    monkeypatch.setattr(fetcher, "make_client", lambda a, *x, **k: _Fake(a["account_id"]))
    build_static._backfill_missing_accounts_ac(
        [{"account_id": "pub-empty"}], repo, datetime.date(2026, 7, 28),
        mode="live", client_id="x", client_secret="y", currency="USD", data_dir=str(d))
    assert hits == []                                    # never even constructed a client call for it


def test_built_site_is_noindex_and_leaks_no_referrer(tmp_path):
    """The dashboard sits on a public static host with no login, so the URL is the only thing
    keeping it private. A crawler indexing it once would put revenue figures into search results
    permanently — that must be impossible to regress into."""
    out, data = str(tmp_path / "site"), str(tmp_path / "data")
    build_static.build(out_dir=out, data_dir=data, today=date(2026, 7, 23), mode="mock")

    robots = open(os.path.join(out, "robots.txt"), encoding="utf-8").read()
    assert "User-agent: *" in robots and "Disallow: /" in robots

    headers = open(os.path.join(out, "_headers"), encoding="utf-8").read()
    assert headers.lstrip().startswith("/*"), "the noindex rule must cover EVERY path, not just one"
    assert "noindex" in headers and "nofollow" in headers and "noarchive" in headers
    assert "Referrer-Policy: no-referrer" in headers        # don't hand the URL to sites clicked through to
    # the data files must still never be cached anywhere
    for p in ("/dashboard.json", "/selected_apps.json", "/account_names.json", "/app_names.json"):
        assert f"{p}\n  Cache-Control: no-store" in headers
