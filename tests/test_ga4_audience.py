"""GA4 → Audience store (admob_iq.fetch.ga4_audience) — offline, against a fake Data API (requests mocked; synthetic
users only): the windows and the request shape (≤ 4 named ranges ending on the final day, one dimension, TOTAL), paging
to the last row, "(other)" re-asked by install-day slices and flagged, thresholding / sampling / a refused TOTAL /
coverage flagged, the store, the once-a-day plan, the build's run (budget, quota, failures, the old store kept), the
switch, the build hook's one counts-only line, and the one-off workflow + probe."""

import copy
import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest
import yaml

from admob_iq.engine import audience as eng
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_audience as ga
from admob_iq.fetch import ga4_uninstall as gu
from tests.audience_synth import (E, EMAIL_A, PID, PID_B, RT_A, SID, SID_B, SID_C, TOK_A, FakeGA4, Population)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 9, 25, 13, 0, tzinfo=timezone.utc)       # UTC noon passed: settled 23 Sep, final E = 20 Sep
PKG, PKG_B, PKG_C = "com.secret.alpha", "com.secret.beta", "com.secret.gamma"
A1, A2, A3, A4 = ("ca-app-pub-3333333333333333~%d" % i for i in (1, 2, 3, 4))
SECRETS = [EMAIL_A, RT_A, TOK_A, PID, PID_B, SID, SID_B, SID_C, PKG, PKG_B, PKG_C, A1, A2, A3, A4, "secret", "SECRET"]
CFG = {"client_id": "cid", "client_secret": "sec", "refresh_tokens": json.dumps({EMAIL_A: RT_A}), "refresh_token": "",
       "retry_hours": 3.0}


def _ga(pop, **kw):
    return ga.App(TOK_A, PID, SID, **kw)


@pytest.fixture
def fake(monkeypatch):
    def make(truths=None, **kw):
        f = FakeGA4(truths or {(PID, SID): Population()}, **kw)
        monkeypatch.setattr(ga4.requests, "post", f.post)
        return f
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: {RT_A: TOK_A}[rt])
    return make


def _names(body):
    return [r["name"] for r in body["dateRanges"]]


# ── the plan ─────────────────────────────────────────────────────────────────────────────────────────

def test_e_is_the_robots_settled_day_less_the_activity_settling_days():
    assert ga.final_end("UTC", NOW) == gu.settled_end("UTC", NOW) - timedelta(days=3) == E
    before_noon = datetime(2026, 9, 25, 11, 0, tzinfo=timezone.utc)
    assert ga.final_end("UTC", before_noon) == E - timedelta(days=1)


@pytest.mark.parametrize("age,want", [(1, [30]), (30, [30]), (31, [30, 60]), (61, [30, 60, 91]),
                                      (365, [eng.window_days(n) for n in range(1, 13)])])
def test_windows_are_whole_months_up_to_the_first_that_holds_the_history(age, want):
    assert ga.windows_for(E, E - timedelta(days=age - 1)) == want


def test_ranges_end_on_e_four_to_a_request_dau_first():
    hs = E - timedelta(days=1299)                                 # a 3.5-year app
    rs = ga.ranges_for(E, hs)
    assert rs[0] == ("dau", E, E) and all(b == E for _, _, b in rs)
    assert [(b - a).days + 1 for n, a, b in rs[1:]] == ga.windows_for(E, hs) and len(rs) == 44
    assert rs[-1][1] <= hs < rs[-2][1]                              # the last window holds the first install day
    assert [len(g) for g in ga.groups(rs)] == [4] * 11
    p = ga.plan_calls(E, hs)
    assert p == {"windows": 43, "ranges": 44, "calls": 11, "range_days": 1 + sum(ga.windows_for(E, hs)),
                 "tokens_est": 11 * ga.TOKENS_PER_CALL_EST}
    assert ga.plan_calls(E, E - timedelta(days=99))["calls"] == 2     # 100 days: dau + 4 windows


# ── the request ──────────────────────────────────────────────────────────────────────────────────────

def test_request_shape_named_ranges_one_dimension_total_stream_pinned(fake):
    pop = Population(days=400, per_day=6)
    f = fake({(PID, SID): pop})
    store = ga.fetch_app(_ga(pop), E, pop.start)
    rs = ga.ranges_for(E, pop.start)
    assert len(f.bodies) == len(ga.groups(rs)) == store["calls"]
    for (pid, b), g in zip(f.bodies, ga.groups(rs)):
        assert pid == PID
        assert b["dimensions"] == [{"name": "firstSessionDate"}] and b["metrics"] == [{"name": "activeUsers"}]
        assert b["metricAggregations"] == ["TOTAL"] and b["returnPropertyQuota"] is True
        assert b["dateRanges"] == [{"startDate": a.isoformat(), "endDate": e.isoformat(), "name": n} for n, a, e in g]
        assert b["orderBys"] == [{"dimension": {"dimensionName": "firstSessionDate"}}]
        assert b["offset"] == 0 and b["limit"] == ga.PAGE_ROWS
        ex = b["dimensionFilter"]["andGroup"]["expressions"]
        assert [(e["filter"]["fieldName"], e["filter"]["stringFilter"]["value"]) for e in ex] == \
            [("platform", "Android"), ("streamId", SID)]
    want = pop.aud_store()
    assert store["windows"] == want["windows"] and store["by_fsd"] == want["by_fsd"]
    assert store["total"] == want["total"] and store["dau_by_fsd"] == want["dau_by_fsd"]
    assert store["dau"] == want["dau"] and store["other"] == store["not_set"] == [0] * len(want["windows"])
    assert store["E"] == E.isoformat() and store["history_start"] == pop.start.isoformat() and store["v"] == 1
    assert store["tokens"] == 7 * store["calls"]
    fl = store["flags"]
    assert (fl["thresholded"], fl["other"], fl["sampled"], fl["truncated"], fl["cov_off"], fl["no_total"]) == \
        ([], [], [], [], {}, False)
    # the store answers the engine exactly as the population would
    assert eng.derive_app(store, pop.uni_store())["dead"] == eng.derive_app(want, pop.uni_store())["dead"]


def test_every_row_is_paged_and_a_multi_range_read_that_needs_pages_is_split(fake, monkeypatch):
    pop = Population(days=200, per_day=4)
    f = fake({(PID, SID): pop})
    monkeypatch.setattr(ga, "PAGE_ROWS", 150)                     # 200 install days: every range needs 2 pages
    app = _ga(pop)
    store = ga.fetch_app(app, E, pop.start)
    want = pop.aud_store()
    assert store["by_fsd"] == want["by_fsd"] and store["dau_by_fsd"] == want["dau_by_fsd"]
    assert store["flags"]["split_reads"] >= 1
    single = [b for _, b in f.bodies if len(b["dateRanges"]) == 1]
    assert {b["offset"] for b in single} >= {0, 150}               # offset paging to the last row
    assert all(b["limit"] == 150 for _, b in f.bodies)


def test_other_rows_are_asked_again_by_install_day_slices_and_stay_flagged(fake, monkeypatch):
    pop = Population(days=300, per_day=5)
    f = fake({(PID, SID): pop}, other_over=100)                    # > 100 install days in a range → "(other)"
    monkeypatch.setattr(ga, "IN_LIST_DAYS", 90)
    store = ga.fetch_app(_ga(pop), E, pop.start)
    want = pop.aud_store()
    assert store["by_fsd"] == want["by_fsd"] and store["other"] == [0] * len(want["windows"])
    fl = store["flags"]
    assert fl["other_reasked"] >= 1 and fl["other_kept"] == 0 and fl["other"] == []
    assert fl["other_first"] and all(v > 0 for v in fl["other_first"].values())    # what "(other)" held first
    sliced = [b for _, b in f.bodies if any("inListFilter" in e["filter"]
                                            for e in b["dimensionFilter"]["andGroup"]["expressions"])]
    vals = [e["filter"]["inListFilter"]["values"] for _, b in [(0, b) for b in sliced]
            for e in b["dimensionFilter"]["andGroup"]["expressions"] if "inListFilter" in e["filter"]]
    assert all(len(v) <= 90 for v in vals) and {v[0] for v in vals} >= {pop.start.strftime("%Y%m%d")}


def test_other_rows_without_room_for_the_slices_are_kept_and_flagged_never_spread(fake):
    pop = Population(days=300, per_day=5)
    fake({(PID, SID): pop}, other_over=100)
    store = ga.fetch_app(_ga(pop), E, pop.start, max_calls=3)
    fl = store["flags"]
    assert fl["other_kept"] >= 1 and fl["other"] and fl["loss_other"]
    i = [n for n in fl["other"] if n != "dau"][0]
    k = store["windows"].index(int(i[1:]))
    tot = sum(r[k] for r in store["by_fsd"].values()) + store["other"][k]
    assert store["other"][k] > 0 and tot == store["total"][k]      # every user is somewhere, "(other)" apart
    assert eng.derive_app(store, pop.uni_store())["other"][k] == store["other"][k]


def test_thresholding_sampling_and_not_set_are_flagged(fake):
    pop = Population(days=100, per_day=5)
    fake({(PID, SID): pop}, thresholded=True, sampled=True, not_set=3)
    store = ga.fetch_app(_ga(pop), E, pop.start)
    every = ["dau"] + ["w%d" % w for w in store["windows"]]
    assert store["flags"]["thresholded"] == every and store["flags"]["sampled"] == every
    assert store["not_set"] == [3] * len(store["windows"]) and store["dau"]["not_set"] == 3
    assert ga.flag_summary(store)["flagged"] and ga.flag_summary(store)["thresholded"]


def test_a_refused_total_is_asked_without_it_once_and_flagged(fake):
    pop = Population(days=100, per_day=5)
    f = fake({(PID, SID): pop}, no_total=True)
    store = ga.fetch_app(_ga(pop), E, pop.start)
    assert store["flags"]["no_total"] is True and store["total"] == [None] * len(store["windows"])
    assert store["by_fsd"] == pop.aud_store()["by_fsd"]
    tried = [b for _, b in f.bodies if b.get("metricAggregations")]
    assert len(tried) == 1                                          # the app's other reads go without it at once


def test_a_split_off_ga4s_own_total_is_flagged(fake, monkeypatch):
    pop = Population(days=100, per_day=20)
    f = fake({(PID, SID): pop})
    real = f.answer

    def short(p, body, in_list):                                    # GA4 drops a third of the rows silently
        r = real(p, body, in_list)
        r["rows"] = [x for i, x in enumerate(r["rows"]) if i % 3]
        r["rowCount"] = len(r["rows"])
        return r
    monkeypatch.setattr(f, "answer", short)
    store = ga.fetch_app(_ga(pop), E, pop.start)
    assert store["flags"]["cov_off"] and all(v < ga.COV_LO for v in store["flags"]["cov_off"].values())


def test_a_low_quota_or_a_429_stops_the_property_and_raises_stop(fake):
    pop = Population(days=200, per_day=4)
    fake({(PID, SID): pop}, quota={"tokensPerProjectPerHour": 6000})     # under half of 14,000
    prop = ga.new_prop()
    with pytest.raises(ga.Stop):
        ga.fetch_app(_ga(pop, prop=prop), E, pop.start)
    assert prop["stop"] == "hour_low"
    fake({(PID, SID): pop}, fail=lambda b: 429)
    prop = ga.new_prop()
    with pytest.raises(RuntimeError):
        ga.fetch_app(_ga(pop, prop=prop), E, pop.start)
    assert prop["stop"] == "quota_429"
    with pytest.raises(ga.Stop):
        ga.fetch_app(_ga(pop, prop=prop), E, pop.start)


def test_quota_rules():
    assert ga.quota_stop(None) is None
    assert ga.quota_stop({"tokensPerHour": {"consumed": 1, "remaining": 30000}}) is None
    assert ga.quota_stop({"tokensPerHour": {"consumed": 1, "remaining": 19000}}) == "hour_low"
    assert ga.quota_stop({"tokensPerDay": {"consumed": 1, "remaining": 15000}}) == "quota_low"
    assert ga.quota_stop({"potentiallyThresholdedRequestsPerHour": {"consumed": 1, "remaining": 5}}) == "count_low"
    assert ga.fits({"tokensPerProjectPerHour": {"consumed": 10, "remaining": 8000}}, 900)
    assert not ga.fits({"tokensPerProjectPerHour": {"consumed": 10, "remaining": 8000}}, 1100)


# ── the build's run ──────────────────────────────────────────────────────────────────────────────────

APPS = [{"app_id": A1, "app_name": "Alpha", "package": PKG}, {"app_id": A2, "app_name": "Beta", "package": PKG_B},
        {"app_id": A3, "app_name": "Gamma", "package": PKG_C},
        {"app_id": A4, "app_name": "Alpha copy", "package": None, "same_as": "Alpha", "same_pkg": PKG}]


def seed(data_dir, pops, routes=None):
    """Uninstall stores + the Uninstall state (routes, timezones, store meta) as the uninstall fetch leaves them."""
    st = gu._state_default()
    st["routes"]["by_package"] = routes or {PKG: {"property_id": PID, "stream_id": SID, "owner": EMAIL_A},
                                            PKG_B: {"property_id": PID, "stream_id": SID_B, "owner": EMAIL_A},
                                            PKG_C: {"property_id": PID_B, "stream_id": SID_C, "owner": EMAIL_A}}
    st["tz"] = {PID: "UTC", PID_B: "UTC"}
    pkg = {a["app_id"]: a["package"] for a in APPS}
    for aid, (pid, sid, pop) in pops.items():
        s = pop.uni_store()
        s.update(property_id=pid, stream_id=sid)
        gu.save_store(gu.store_path(data_dir, aid), s)
        st["fetch"][aid] = {"package": pkg[aid], "property_id": pid, "stream_id": sid, "meta": gu.store_meta(s)}
    gu.save_state(data_dir, st)


@pytest.fixture
def world(tmp_path, fake):
    pops = {A1: (PID, SID, Population(days=400, per_day=5, seed=1)),
            A2: (PID, SID_B, Population(days=90, per_day=5, seed=2)),
            A3: (PID_B, SID_C, Population(days=200, per_day=5, seed=3))}
    data = str(tmp_path / "data")
    os.makedirs(data)
    seed(data, pops)
    f = fake({(p, s): pop for p, s, pop in pops.values()})
    return data, pops, f


def _run(data, now=NOW, budget=ga.BUDGET_SEC, clock=lambda: 0.0, cfg=None):
    return ga.refresh_all(dict(CFG, **(cfg or {})), data, APPS, now, clock, budget=budget)


def test_every_app_is_fetched_once_a_day_and_the_store_is_whole(world):
    data, pops, f = world
    out = _run(data)
    assert out["apps"] == {A1: "fetched", A2: "fetched", A3: "fetched"}
    c = out["counts"]
    assert (c["selected"], c["with_ga4"], c["fetched"], c["calls"]) == (3, 3, 3, len(f.bodies))
    assert c["tokens"] == 7 * len(f.bodies)
    for aid, (pid, sid, pop) in pops.items():
        s = ga.load_store(ga.store_path(data, aid))
        want = pop.aud_store()
        assert s["by_fsd"] == want["by_fsd"] and s["windows"] == want["windows"]
        assert (s["app_id"], s["property_id"], s["stream_id"], s["time_zone"]) == (aid, pid, sid, "UTC")
    st = ga.load_state(data)["fetch"][A1]
    assert st["last_ok"] == "2026-09-25T13:00:00Z" and st["meta"]["E"] == E.isoformat() and st["calls"] > 0
    n = len(f.bodies)
    out = _run(data, now=NOW + timedelta(hours=5))                  # same final day: nothing asked
    assert out["apps"] == {A1: "fresh", A2: "fresh", A3: "fresh"} and len(f.bodies) == n
    out = _run(data, now=NOW + timedelta(days=1))                   # a new final day: read again
    assert out["counts"]["fetched"] == 3 and len(f.bodies) > n
    assert ga.load_store(ga.store_path(data, A1))["E"] == (E + timedelta(days=1)).isoformat()


def test_an_app_without_its_uninstall_store_waits_and_a_moved_history_is_read_again(world):
    data, pops, f = world
    os.remove(gu.store_path(data, A3))
    out = _run(data)
    assert out["apps"][A3] == "waiting" and out["counts"]["waiting"] == 1
    s = gu.load_store(gu.store_path(data, A1))                       # the Uninstall history now starts earlier
    s["history_start"] = (date.fromisoformat(s["history_start"]) - timedelta(days=10)).isoformat()
    gu.save_store(gu.store_path(data, A1), s)
    st = gu.load_state(data)
    st["fetch"][A1]["meta"] = gu.store_meta(s)
    gu.save_state(data, st)
    out = _run(data, now=NOW + timedelta(hours=1))
    assert out["apps"][A1] == "fetched" and out["apps"][A2] == "fresh"
    assert ga.load_store(ga.store_path(data, A1))["history_start"] == s["history_start"]


def test_the_budget_defers_apps_and_they_lead_the_next_run(world):
    data, pops, f = world
    t = iter([0.0] + [0.0] * 3 + [200.0] * 1000)
    out = _run(data, clock=lambda: next(t))
    assert list(out["apps"].values()).count("fetched") >= 1 and out["counts"]["deferred"] >= 1
    deferred = [a for a, v in out["apps"].items() if v == "deferred"]
    assert all(ga.load_state(data)["fetch"][a]["deferred"] for a in deferred)
    out = _run(data, now=NOW + timedelta(hours=1))
    assert all(out["apps"][a] == "fetched" for a in deferred)
    assert not any(ga.load_state(data)["fetch"][a].get("deferred") for a in deferred)


def test_a_started_app_that_runs_past_twice_the_budget_keeps_its_old_store(world):
    data, pops, f = world
    _run(data)
    before = {a: open(ga.store_path(data, a), "rb").read() for a in pops}
    t = iter([0.0] + [0.0] * 4 + [1000.0] * 1000)                  # the first app starts, then the clock jumps
    out = _run(data, now=NOW + timedelta(days=1), clock=lambda: next(t))
    assert out["apps"] == {A1: "deferred", A2: "deferred", A3: "deferred"}
    assert ga.load_state(data)["fetch"][A1]["stopped"] == "budget"          # A1 stopped after 2 of its 4 calls
    for a, v in out["apps"].items():
        if v == "deferred":
            assert open(ga.store_path(data, a), "rb").read() == before[a]       # whole or nothing


def test_a_low_hourly_quota_defers_the_propertys_other_apps_but_not_the_others(world):
    data, pops, f = world
    f.quota = {"tokensPerProjectPerHour": 7020}                    # just above half of 14,000: A1's calls go …
    out = _run(data)
    assert out["apps"] == {A1: "fetched", A2: "deferred", A3: "fetched"}    # … A2's estimate (2 calls) no longer fits
    assert ga.load_state(data)["fetch"][A2]["deferred"] is True        # (A3: another property, its own quota)
    f.quota = {"tokensPerProjectPerHour": 13000}
    assert _run(data, now=NOW + timedelta(hours=1))["apps"][A2] == "fetched"


def test_a_failed_app_waits_its_retry_hours_and_never_stops_the_others(world):
    data, pops, f = world
    f.fail = lambda b: 400 if b["dimensionFilter"]["andGroup"]["expressions"][1]["filter"]["stringFilter"][
        "value"] == SID_B else None
    out = _run(data)
    assert out["apps"] == {A1: "fetched", A2: "failed", A3: "fetched"}
    st = ga.load_state(data)["fetch"][A2]
    assert st["fail"] == "http" and st["fail_detail"] == {"http": 400, "status": "INVALID_ARGUMENT"}
    assert "SECRET" not in json.dumps(ga.load_state(data))
    f.fail = None
    assert _run(data, now=NOW + timedelta(hours=1))["apps"][A2] == "failed"      # waiting
    assert _run(data, now=NOW + timedelta(hours=4))["apps"][A2] == "fetched"


def test_a_token_that_does_not_refresh_fails_the_owners_apps_only(world, monkeypatch):
    data, pops, f = world
    monkeypatch.setattr(ga4, "access_token", lambda *a: (_ for _ in ()).throw(RuntimeError("invalid_grant SECRET")))
    out = _run(data)
    assert set(out["apps"].values()) == {"failed"} and not f.bodies
    assert ga.load_state(data)["fetch"][A1]["fail"] == "auth"


def test_refresh_all_never_raises_and_the_log_line_is_counts_only(world, monkeypatch):
    data, pops, f = world
    out = _run(data)
    line = ga.log_line(out)
    assert line.startswith("ga4 audience: apps 3, with GA4 3, fetched 3, fresh 0, failed 0, deferred 0, waiting 0, ")
    for s in SECRETS + [E.isoformat()]:
        assert s not in line
    monkeypatch.setattr(ga, "load_state", lambda d: 1 / 0)
    out = _run(data)
    assert out["error"] == "ZeroDivisionError" and ga.log_line(out).endswith("error ZeroDivisionError")


def test_store_files_are_deterministic_and_rewritten_only_on_change(world):
    data, pops, f = world
    _run(data)
    p = ga.store_path(data, A1)
    raw, mtime = open(p, "rb").read(), os.stat(p).st_mtime_ns
    s = ga.load_store(p)
    assert not ga.save_store(p, s) and os.stat(p).st_mtime_ns == mtime and open(p, "rb").read() == raw
    assert p.endswith(os.path.join("ga4_audience", gu.file_key(A1) + ".json.gz"))


# ── the plan rules ───────────────────────────────────────────────────────────────────────────────────

def test_plan_due_rules():
    r = {"property_id": PID, "stream_id": SID}
    um = {"history_start": "2025-01-01"}
    meta = {"v": 1, "E": E.isoformat(), "history_start": "2025-01-01", "property_id": PID, "stream_id": SID}
    assert ga.plan({}, None, um, r, E, NOW) == "fetch"
    assert ga.plan({}, meta, um, r, E, NOW) is None
    assert ga.plan({}, meta, um, r, E + timedelta(days=1), NOW) == "fetch"
    assert ga.plan({}, dict(meta, v=0), um, r, E, NOW) == "fetch"
    assert ga.plan({}, dict(meta, stream_id="x"), um, r, E, NOW) == "fetch"
    assert ga.plan({}, meta, {"history_start": "2024-12-01"}, r, E, NOW) == "fetch"
    failed = {"fail": "http", "last_try": "2026-09-25T12:00:00Z"}
    assert ga.plan(failed, None, um, r, E, NOW) is None
    assert ga.plan(failed, None, um, r, E, NOW + timedelta(hours=3)) == "fetch"


# ── the switch, the build hook, the workflows ─────────────────────────────────────────────────────────

def test_the_switch_is_off_by_default_and_the_refresh_workflow_passes_the_repo_variable(monkeypatch):
    from admob_iq.config import settings
    monkeypatch.delenv("GA4_AUDIENCE", raising=False)
    monkeypatch.delenv("GA4_AUDIENCE_BUDGET_SEC", raising=False)
    s = settings()
    assert s["ga4_audience"] is False and s["ga4_audience_budget_sec"] == 180
    monkeypatch.setenv("GA4_AUDIENCE", "true")
    assert settings()["ga4_audience"] is True
    with open(os.path.join(ROOT, ".github", "workflows", "refresh.yml"), encoding="utf-8") as fh:
        wf = yaml.safe_load(fh)
    env = [st for st in wf["jobs"]["refresh"]["steps"] if st.get("name") == "Build dashboard + send alerts"][0]["env"]
    assert env["GA4_AUDIENCE"] == "${{ vars.GA4_AUDIENCE || 'false' }}"
    assert env["GA4_AUDIENCE_BUDGET_SEC"] == "${{ vars.GA4_AUDIENCE_BUDGET_SEC }}"


def test_the_build_hook_runs_only_with_the_switch_and_adds_one_counts_line(tmp_path, monkeypatch, capsys):
    from tests import test_uninstall_build as tub
    from admob_iq import uninstall_build as ub
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    tub.seed(data)
    monkeypatch.setattr(gu, "refresh_all", lambda *a, **k: copy.deepcopy(tub.STATUS))
    calls = []
    monkeypatch.setattr(ga, "refresh_all", lambda cfg, d, apps, now, clock, budget: calls.append(
        (sorted(a["app_id"] for a in apps if a.get("package")), budget)) or {"counts": {"selected": 2, "fetched": 2}})
    ub.run_uninstall(tub.dashboard(), data, out, tub.ga4_settings(), now=tub.NOW)
    assert calls == [] and "ga4 audience" not in capsys.readouterr().err
    ub.run_uninstall(tub.dashboard(), data, out, tub.ga4_settings(ga4_audience=True, ga4_audience_budget_sec=60),
                     now=tub.NOW)
    err = capsys.readouterr().err
    assert len(calls) == 1 and calls[0][1] == 60
    lines = [ln for ln in err.splitlines() if ln.startswith("ga4 audience")]
    assert lines == ["ga4 audience: apps 2, with GA4 0, fetched 2, fresh 0, failed 0, deferred 0, waiting 0, calls 0, "
                     "tokens 0 (~0 per fetched app), flagged 0 (other 0, thresholded 0, coverage off 0)"]
    monkeypatch.setattr(ga, "refresh_all", lambda *a, **k: 1 / 0)    # a failure costs this step only
    dash = tub.dashboard()
    ub.run_uninstall(dash, data, out, tub.ga4_settings(ga4_audience=True), now=tub.NOW)
    assert "ga4 audience skipped: ZeroDivisionError" in capsys.readouterr().err and dash["uninstall"]["apps"]
