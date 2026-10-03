"""GA4 → Audience store (admob_iq.fetch.ga4_audience) — offline, against a fake Data API (requests mocked; synthetic
users only): the tiered windows and the request shape (named ranges ending on the final day, grouped by the token
estimate, one dimension, TOTAL), paging to the last row, "(other)" re-asked by install-day slices and flagged, thresholding
/ sampling / a refused TOTAL / coverage flagged; the RESUMABLE read (every finished call kept across runs, E frozen until
complete then rolled forward, slices resumed, the call's estimate gate, the per-app measured k); the plan, the build's
run (budget, quota, failures), the switch and the build hook's one counts-only line."""

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
NOW_ISO = "2026-09-25T13:00:00Z"
PKG, PKG_B, PKG_C = "com.secret.alpha", "com.secret.beta", "com.secret.gamma"
A1, A2, A3, A4 = ("ca-app-pub-3333333333333333~%d" % i for i in (1, 2, 3, 4))
SECRETS = [EMAIL_A, RT_A, TOK_A, PID, PID_B, SID, SID_B, SID_C, PKG, PKG_B, PKG_C, A1, A2, A3, A4, "secret", "SECRET"]
CFG = {"client_id": "cid", "client_secret": "sec", "refresh_tokens": json.dumps({EMAIL_A: RT_A}), "refresh_token": "",
       "retry_hours": 3.0}
ROUTE = {"property_id": PID, "stream_id": SID}


def _ga(**kw):
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


def _sid(body):
    return body["dimensionFilter"]["andGroup"]["expressions"][1]["filter"]["stringFilter"]["value"]


def _asked(f, sliced=None, sid=SID):
    """Range names asked for stream `sid` without an inList (sliced=False), with one (True) or all (None), in order."""
    out = []
    for _, b in f.bodies:
        has = any("inListFilter" in e["filter"] for e in b["dimensionFilter"]["andGroup"]["expressions"])
        if _sid(b) == sid and (sliced is None or has == sliced):
            out += _names(b)
    return out


def _ends(f):
    return {r["endDate"] for _, b in f.bodies for r in b["dateRanges"]}


# ── the plan ─────────────────────────────────────────────────────────────────────────────────────────

def test_e_is_the_robots_settled_day_less_the_activity_settling_days():
    assert ga.final_end("UTC", NOW) == gu.settled_end("UTC", NOW) - timedelta(days=3) == E
    before_noon = datetime(2026, 9, 25, 11, 0, tzinfo=timezone.utc)
    assert ga.final_end("UTC", before_noon) == E - timedelta(days=1)


def test_ranges_are_the_tiered_windows_ending_on_e_dau_first():
    hs = E - timedelta(days=1299)                                 # a 1,300-day app
    rs = ga.ranges_for(E, hs)
    months = list(range(1, 13)) + [15, 18, 21, 24, 30, 36, 42, 48]
    assert rs[0] == ("dau", E, E) and all(b == E for _, _, b in rs)
    assert [(b - a).days + 1 for _, a, b in rs[1:]] == [eng.window_days(m) for m in months]
    assert [n for n, _, _ in rs[1:]] == ["w%d" % eng.window_days(m) for m in months]
    assert rs[-1][1] <= hs < rs[-2][1]                              # the last window holds the first install day
    p = ga.plan_calls(E, hs)
    assert (p["windows"], p["ranges"], p["install_days"], p["months"]) == (20, 21, 1300, months)
    assert p["range_days"] == 1 + sum(eng.window_days(m) for m in months)
    assert p["units"] == p["range_days"] * 1300 and p["tokens_est"] == round(ga.PRIOR_K * p["units"])
    old = 1 + sum(eng.window_days(n) for n in range(1, 44))        # (the first probe's 43 monthly windows)
    assert p["range_days"] < old / 2.5                              # past a year a coarser step: far fewer tokens


def test_a_call_takes_more_ranges_only_while_its_estimate_stays_under_the_cap():
    hs = E - timedelta(days=1299)
    rs, rows = ga.ranges_for(E, hs), 1300
    for k in (ga.PRIOR_K, 10 * ga.PRIOR_K, 1e-9):
        todo, calls = list(rs), 0
        while todo:
            g = ga.next_group(todo, rows, k)
            assert 1 <= len(g) <= ga.RANGES_PER_CALL
            assert len(g) == 1 or ga.estimate(g, rows, k) <= ga.CALL_EST_CAP
            todo, calls = todo[len(g):], calls + 1
        assert calls == ga.plan_calls(E, hs, k)["calls"]
    assert ga.plan_calls(E, hs, 1e-9)["calls"] == 6                # cheap: 4 ranges a call
    assert ga.plan_calls(E, hs, 10 * ga.PRIOR_K)["calls"] > ga.plan_calls(E, hs)["calls"]   # a costly app: smaller steps
    assert ga.plan_calls(E, E - timedelta(days=99))["calls"] == 2    # 100 days: dau + 4 windows


# ── the request ──────────────────────────────────────────────────────────────────────────────────────

def test_request_shape_named_ranges_one_dimension_total_stream_pinned(fake):
    pop = Population(days=400, per_day=6)
    f = fake({(PID, SID): pop})
    store = ga.fetch_app(_ga(), E, pop.start)
    assert len(f.bodies) == store["calls"] == ga.plan_calls(E, pop.start)["calls"]
    assert _asked(f) == [n for n, _, _ in ga.ranges_for(E, pop.start)]          # every range once, in order
    for pid, b in f.bodies:
        assert pid == PID and 1 <= len(b["dateRanges"]) <= 4
        assert b["dimensions"] == [{"name": "firstSessionDate"}] and b["metrics"] == [{"name": "activeUsers"}]
        assert b["metricAggregations"] == ["TOTAL"] and b["returnPropertyQuota"] is True
        assert all(set(r) == {"startDate", "endDate", "name"} and r["endDate"] == E.isoformat()
                   for r in b["dateRanges"])
        assert b["orderBys"] == [{"dimension": {"dimensionName": "firstSessionDate"}}]
        assert b["offset"] == 0 and b["limit"] == ga.PAGE_ROWS
        ex = b["dimensionFilter"]["andGroup"]["expressions"]
        assert [(e["filter"]["fieldName"], e["filter"]["stringFilter"]["value"]) for e in ex] == \
            [("platform", "Android"), ("streamId", SID)]
    want = pop.aud_store()
    for key in ("months", "windows", "by_fsd", "total", "dau_by_fsd", "dau"):
        assert store[key] == want[key], key
    assert store["other"] == store["not_set"] == [0] * len(want["windows"]) and store["complete"] is True
    assert store["E"] == E.isoformat() and store["history_start"] == pop.start.isoformat()
    assert store["tokens"] == 7 * store["calls"] and store["units"] == ga.plan_calls(E, pop.start)["units"]
    fl = store["flags"]
    assert (fl["thresholded"], fl["other"], fl["sampled"], fl["truncated"], fl["cov_off"], fl["sliced"]) == \
        ([], [], [], [], {}, {})
    assert eng.derive_app(store, pop.uni_store())["dead"] == eng.derive_app(want, pop.uni_store())["dead"]


def test_every_row_is_paged_and_a_multi_range_read_that_needs_pages_is_split(fake, monkeypatch):
    pop = Population(days=200, per_day=4)
    f = fake({(PID, SID): pop})
    monkeypatch.setattr(ga, "PAGE_ROWS", 150)                     # 200 install days: every range needs 2 pages
    app = _ga()
    store = ga.fetch_app(app, E, pop.start)
    want = pop.aud_store()
    assert store["by_fsd"] == want["by_fsd"] and store["dau_by_fsd"] == want["dau_by_fsd"]
    assert app.split_reads >= 1
    single = [b for _, b in f.bodies if len(b["dateRanges"]) == 1]
    assert {b["offset"] for b in single} >= {0, 150}               # offset paging to the last row
    assert all(b["limit"] == 150 for _, b in f.bodies)


def test_other_rows_are_asked_again_by_install_day_slices_and_stay_flagged(fake, monkeypatch):
    pop = Population(days=300, per_day=5)
    f = fake({(PID, SID): pop}, other_over=100)                    # > 100 install days in a range → "(other)"
    monkeypatch.setattr(ga, "IN_LIST_MAX", 90)
    store = ga.fetch_app(_ga(), E, pop.start)
    want = pop.aud_store()
    assert store["by_fsd"] == want["by_fsd"] and store["other"] == [0] * len(want["windows"])
    fl = store["flags"]
    assert fl["other"] == [] and fl["sliced"] and all(v >= 4 for v in fl["sliced"].values())   # 300 days: 4 slices
    assert fl["other_first"] and all(v > 0 for v in fl["other_first"].values())    # what "(other)" held first
    assert set(fl["sliced"]) == set(fl["other_first"])             # only the ranges that had "(other)" rows
    vals = [e["filter"]["inListFilter"]["values"] for _, b in f.bodies
            for e in b["dimensionFilter"]["andGroup"]["expressions"] if "inListFilter" in e["filter"]]
    assert vals and all(len(v) <= 90 for v in vals) and pop.start.strftime("%Y%m%d") in {v[0] for v in vals}
    assert all(len(b["dateRanges"]) == 1 for _, b in f.bodies
               if any("inListFilter" in e["filter"] for e in b["dimensionFilter"]["andGroup"]["expressions"]))


def test_a_slice_still_folded_at_the_smallest_size_is_kept_and_flagged_never_spread(fake, monkeypatch):
    pop = Population(days=300, per_day=5)
    f = fake({(PID, SID): pop}, other_over=10, other_slices=True)  # even a 30-day slice has "(other)"
    store = ga.fetch_app(_ga(), E, pop.start)
    fl = store["flags"]
    assert fl["other"] and fl["loss_other"]
    vals = [e["filter"]["inListFilter"]["values"] for _, b in f.bodies
            for e in b["dimensionFilter"]["andGroup"]["expressions"] if "inListFilter" in e["filter"]]
    assert min(len(v) for v in vals) >= ga.IN_LIST_MIN // 2 and max(len(v) for v in vals) <= ga.IN_LIST_MAX
    k = store["windows"].index(int([n for n in fl["other"] if n != "dau"][-1][1:]))
    tot = sum(r[k] for r in store["by_fsd"].values()) + store["other"][k]
    assert store["other"][k] > 0 and tot == store["total"][k]      # every user is somewhere, "(other)" apart
    assert eng.derive_app(store, pop.uni_store())["other"][k] == store["other"][k]


def test_data_loss_without_any_other_row_re_asks_every_range_of_that_call(fake):
    pop = Population(days=150, per_day=5)
    fake({(PID, SID): pop}, loss_only=True)
    store = ga.fetch_app(_ga(), E, pop.start)
    assert store["by_fsd"] == pop.aud_store()["by_fsd"]
    assert set(store["flags"]["sliced"]) == {n for n, _, _ in ga.ranges_for(E, pop.start)}
    assert store["flags"]["loss_other"] == []                       # the slices read clean


def test_thresholding_sampling_and_not_set_are_flagged(fake):
    pop = Population(days=100, per_day=5)
    fake({(PID, SID): pop}, thresholded=True, sampled=True, not_set=3)
    store = ga.fetch_app(_ga(), E, pop.start)
    every = ["dau"] + ["w%d" % w for w in store["windows"]]
    assert store["flags"]["thresholded"] == every and store["flags"]["sampled"] == every
    assert store["not_set"] == [3] * len(store["windows"]) and store["dau"]["not_set"] == 3
    assert ga.flag_summary(store)["flagged"] and ga.flag_summary(store)["thresholded"]


def test_a_refused_total_is_asked_without_it_once(fake):
    pop = Population(days=100, per_day=5)
    f = fake({(PID, SID): pop}, no_total=True)
    app = _ga()
    store = ga.fetch_app(app, E, pop.start)
    assert app.no_total is True and store["total"] == [None] * len(store["windows"])
    assert store["by_fsd"] == pop.aud_store()["by_fsd"]
    assert len([b for _, b in f.bodies if b.get("metricAggregations")]) == 1   # the app's other reads go without it


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
    store = ga.fetch_app(_ga(), E, pop.start)
    assert store["flags"]["cov_off"] and all(v < ga.COV_LO for v in store["flags"]["cov_off"].values())


# ── resumable ─────────────────────────────────────────────────────────────────────────────────────────

def test_a_read_stopped_by_the_quota_keeps_every_finished_call_and_goes_on_next_hour(fake):
    pop = Population(days=500, per_day=5)
    hourly = {"tokensPerProjectPerHour": 7000 + 3 * 300 - 1}       # three calls of 300 tokens, then under half
    f = fake({(PID, SID): pop}, hourly=hourly, tokens=300)
    store = {}
    with pytest.raises(ga.Stop) as e:
        ga.step(_ga(prop=ga.new_prop()), store, E, pop.start, ROUTE, NOW_ISO, k=1e-9)
    assert str(e.value) == "hour_low"
    part = store["partial"]
    assert part["E"] == E.isoformat() and part["calls"] == 3 and part["tokens"] == 900 and part["runs"] == 1
    first = _asked(f)
    assert set(part["ranges"]) == set(first) and ga.progress(part)["done"] == len(first) < ga.progress(part)["total"]
    assert not store.get("complete")
    f.hour_left = {}                                                # a new hour
    res = ga.step(_ga(prop=ga.new_prop()), store, E, pop.start, ROUTE, NOW_ISO, k=1e-9)
    assert res == "fetched" and "partial" not in store and store["complete"] and store["runs"] == 2
    asked = _asked(f)
    assert sorted(asked) == sorted(n for n, _, _ in ga.ranges_for(E, pop.start))   # no range asked twice
    assert store["by_fsd"] == pop.aud_store()["by_fsd"] and store["calls"] == len(f.bodies)


def test_e_is_frozen_until_the_read_completes_then_it_rolls_forward(fake):
    pop = Population(days=400, per_day=5)
    f = fake({(PID, SID): pop})
    store = {}
    with pytest.raises(ga.Stop):
        ga.step(_ga(), store, E, pop.start, ROUTE, NOW_ISO, max_calls=2)
    assert store["partial"]["E"] == E.isoformat()
    f.bodies.clear()
    later = E + timedelta(days=1)                                   # a new final day before the read completed
    with pytest.raises(ga.Stop):
        ga.step(_ga(), store, later, pop.start, ROUTE, NOW_ISO, max_calls=1)
    assert _ends(f) == {E.isoformat()} and store["partial"]["E"] == E.isoformat()   # the old E goes on …
    f.bodies.clear()
    assert ga.step(_ga(), store, later, pop.start, ROUTE, NOW_ISO, roll=False) == "fetched"
    assert store["E"] == E.isoformat() and "partial" not in store                     # … is finished first …
    assert _ends(f) == {E.isoformat()}
    f.bodies.clear()
    assert ga.step(_ga(), store, later, pop.start, ROUTE, NOW_ISO) == "fetched"       # … then rolls forward
    assert store["E"] == later.isoformat() and _ends(f) == {later.isoformat()}
    assert ga.step(_ga(), store, later, pop.start, ROUTE, NOW_ISO) == "fresh"


def test_finishing_an_old_e_rolls_forward_in_the_same_turn(fake):
    pop = Population(days=200, per_day=5)
    f = fake({(PID, SID): pop})
    store = {}
    with pytest.raises(ga.Stop):
        ga.step(_ga(), store, E, pop.start, ROUTE, NOW_ISO, max_calls=1)
    later = E + timedelta(days=1)
    assert ga.step(_ga(), store, later, pop.start, ROUTE, NOW_ISO) == "fetched"
    assert store["E"] == later.isoformat() and _ends(f) == {E.isoformat(), later.isoformat()}


def test_other_slices_resume_where_they_stopped(fake, monkeypatch):
    pop = Population(days=300, per_day=5)
    f = fake({(PID, SID): pop}, other_over=100)
    monkeypatch.setattr(ga, "IN_LIST_MAX", 90)
    store, stops = {}, 0
    while True:
        try:
            ga.step(_ga(), store, E, pop.start, ROUTE, NOW_ISO, max_calls=3)
            break
        except ga.Stop:
            stops += 1
            p = store["partial"]
            if p["slicing"]:
                s = next(iter(p["slicing"].values()))
                assert s["reads"] >= 0 and s["todo"]                 # the slicing state is kept in the store
    assert stops >= 3 and store["complete"] and store["by_fsd"] == pop.aud_store()["by_fsd"]
    full = FakeGA4({(PID, SID): pop}, other_over=100)
    monkeypatch.setattr(ga4.requests, "post", full.post)
    one = ga.fetch_app(_ga(), E, pop.start)
    assert len(f.bodies) == len(full.bodies) == store["calls"] == one["calls"]   # resuming re-asked nothing


def test_a_call_whose_estimate_does_not_fit_waits_for_the_next_run(fake):
    pop = Population(days=300, per_day=5)
    fake({(PID, SID): pop}, quota={"tokensPerProjectPerHour": 7200})       # 200 above half of 14,000
    store, app = {}, _ga()
    k = 300 / (sum(d for d in (1, 30, 60, 91)) * 300)               # the first call (dau + 3 windows) ≈ 300 tokens
    with pytest.raises(ga.Stop) as e:
        ga.step(app, store, E, pop.start, ROUTE, NOW_ISO, k=k)
    assert str(e.value) == "quota_est" and app.calls == 1          # the first goes (no snapshot yet), not the next
    assert len(store["partial"]["ranges"]) == 4


def test_the_measured_k_replaces_the_prior(fake):
    pop = Population(days=300, per_day=5)
    rows = 300
    fake({(PID, SID): pop}, tokens=lambda b: sum((date.fromisoformat(r["endDate"]) -
                                                  date.fromisoformat(r["startDate"])).days + 1
                                                 for r in b["dateRanges"]) * rows // 1000)
    app = _ga()
    store = ga.fetch_app(app, E, pop.start)
    k = ga.measured_k(app, 0.123)
    assert k == round(store["tokens"] / store["units"], 9) and abs(k - 1 / 1000) < 1e-4
    assert ga.measured_k(_ga(), 0.123) == 0.123                     # no call: the old k stays


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


def test_every_app_is_read_whole_once_a_day(world):
    data, pops, f = world
    out = _run(data)
    assert out["apps"] == {A1: "fetched", A2: "fetched", A3: "fetched"}
    c = out["counts"]
    assert (c["selected"], c["with_ga4"], c["fetched"], c["calls"]) == (3, 3, 3, len(f.bodies))
    assert c["tokens"] == 7 * len(f.bodies)
    for aid, (pid, sid, pop) in pops.items():
        s = ga.load_store(ga.store_path(data, aid))
        want = pop.aud_store()
        assert s["by_fsd"] == want["by_fsd"] and s["months"] == want["months"] and s["complete"]
        assert (s["app_id"], s["property_id"], s["stream_id"], s["time_zone"]) == (aid, pid, sid, "UTC")
        assert "partial" not in s
    st = ga.load_state(data)["fetch"][A1]
    assert st["last_ok"] == NOW_ISO and st["meta"]["E"] == E.isoformat() and st["calls"] > 0
    assert st["k"] == round(st["tokens"] / ga.load_store(ga.store_path(data, A1))["units"], 9)   # measured, kept
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


def test_an_app_stopped_mid_read_keeps_its_progress_and_completes_next_run(world):
    data, pops, f = world
    _run(data)
    before = ga.load_store(ga.store_path(data, A1))
    f.bodies.clear()
    t = iter([0.0] + [0.0] * 3 + [1000.0] * 1000)                  # A1 starts, then the clock jumps past 2× budget
    out = _run(data, now=NOW + timedelta(days=1), clock=lambda: next(t))
    assert out["apps"] == {A1: "partial", A2: "deferred", A3: "deferred"} and out["counts"]["partial"] == 1
    s = ga.load_store(ga.store_path(data, A1))
    assert s["E"] == before["E"] and s["by_fsd"] == before["by_fsd"]         # the complete result stays shown …
    assert s["partial"]["E"] == (E + timedelta(days=1)).isoformat() and s["partial"]["ranges"]   # … the new read kept
    st = ga.load_state(data)["fetch"][A1]
    assert st["stopped"] == "budget" and st["meta"]["partial_E"] == s["partial"]["E"]
    done = set(s["partial"]["ranges"])
    f.bodies.clear()
    out = _run(data, now=NOW + timedelta(days=1, hours=1))
    assert out["apps"][A1] == "fetched"
    assert done and not done & set(_asked(f))                       # nothing read twice
    assert ga.load_store(ga.store_path(data, A1))["E"] == (E + timedelta(days=1)).isoformat()


def test_a_low_hourly_quota_reads_part_now_and_the_rest_next_hour(world):
    data, pops, f = world
    f.tokens, f.hourly = 100, {"tokensPerProjectPerHour": 7250}    # 250 above half of 14,000, 100 tokens a call
    out = _run(data)
    # A1 (4 calls): 2 go, the 3rd's estimate no longer fits; A2 (1 small call) still fits; A3: another property
    assert out["apps"] == {A1: "partial", A2: "fetched", A3: "fetched"}
    st = ga.load_state(data)["fetch"][A1]
    assert st["stopped"] == "quota_est" and st["meta"]["partial_progress"]["done"] == 8
    assert st["k"] == round(200 / ((1 + 30 + 60 + 91 + 121 + 152 + 182 + 213) * 400), 9)   # its own cost, measured
    f.hour_left, f.hourly = {}, {}                                  # the next hour
    out = _run(data, now=NOW + timedelta(hours=1))
    assert out["apps"] == {A1: "fetched", A2: "fresh", A3: "fresh"}
    s = ga.load_store(ga.store_path(data, A1))
    assert s["complete"] and "partial" not in s and s["by_fsd"] == pops[A1][2].aud_store()["by_fsd"]
    assert s["runs"] == 2 and s["calls"] == 4


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
    assert line.startswith("ga4 audience: apps 3, with GA4 3, fetched 3, partial 0, fresh 0, failed 0, deferred 0, "
                           "waiting 0, ")
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


def test_an_older_format_store_is_read_again_from_scratch(world):
    data, pops, f = world
    p = ga.store_path(data, A1)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    ga.save_store(p, dict(pops[A1][2].aud_store(), v=1, property_id=PID, stream_id=SID))
    st = ga.load_state(data)
    st["fetch"][A1] = {"meta": dict(ga.store_meta(ga.load_store(p)))}
    ga.save_state(data, st)
    assert _run(data)["apps"][A1] == "fetched"
    assert ga.load_store(p)["v"] == ga.STORE_V


# ── the plan rules ───────────────────────────────────────────────────────────────────────────────────

def test_plan_due_rules():
    r = {"property_id": PID, "stream_id": SID}
    um = {"history_start": "2025-01-01"}
    meta = {"v": 2, "complete": True, "E": E.isoformat(), "history_start": "2025-01-01", "property_id": PID,
            "stream_id": SID}
    assert ga.plan({}, None, um, r, E, NOW) == "fetch"
    assert ga.plan({}, meta, um, r, E, NOW) is None
    assert ga.plan({}, meta, um, r, E + timedelta(days=1), NOW) == "fetch"
    assert ga.plan({}, dict(meta, v=1), um, r, E, NOW) == "fetch"
    assert ga.plan({}, dict(meta, stream_id="x"), um, r, E, NOW) == "fetch"
    assert ga.plan({}, meta, {"history_start": "2024-12-01"}, r, E, NOW) == "fetch"
    going = dict(meta, partial_E=(E - timedelta(days=2)).isoformat(), partial_stream=[PID, SID])
    assert ga.plan({}, going, um, r, E, NOW) == "continue"          # a read under way goes on, even on an older E
    assert ga.plan({}, dict(going, partial_stream=[PID, "x"]), um, r, E, NOW) is None
    failed = {"fail": "http", "last_try": "2026-09-25T12:00:00Z"}
    assert ga.plan(failed, None, um, r, E, NOW) is None
    assert ga.plan(failed, None, um, r, E, NOW + timedelta(hours=3)) == "fetch"


def test_quota_rules():
    assert ga.quota_stop(None) is None
    assert ga.quota_stop({"tokensPerHour": {"consumed": 1, "remaining": 30000}}) is None
    assert ga.quota_stop({"tokensPerHour": {"consumed": 1, "remaining": 19000}}) == "hour_low"
    assert ga.quota_stop({"tokensPerDay": {"consumed": 1, "remaining": 15000}}) == "quota_low"
    assert ga.quota_stop({"potentiallyThresholdedRequestsPerHour": {"consumed": 1, "remaining": 5}}) == "count_low"
    assert ga.fits({"tokensPerProjectPerHour": {"consumed": 10, "remaining": 8000}}, 900)
    assert not ga.fits({"tokensPerProjectPerHour": {"consumed": 10, "remaining": 8000}}, 1100)
    assert not ga.fits({"tokensPerDay": {"consumed": 10, "remaining": 20500}}, 1000)   # daily: ≥ 10% left
    half = {k: 0.5 for k in ("tokensPerHour", "tokensPerProjectPerHour", "tokensPerDay")}
    assert not ga.fits({"tokensPerDay": {"consumed": 10, "remaining": 100500}}, 1000, half)


# ── the switch, the build hook ────────────────────────────────────────────────────────────────────────

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
        (sorted(a["app_id"] for a in apps if a.get("package")), budget)) or {"counts": {"selected": 2, "fetched": 1,
                                                                                       "partial": 1}})
    ub.run_uninstall(tub.dashboard(), data, out, tub.ga4_settings(), now=tub.NOW)
    assert calls == [] and "ga4 audience" not in capsys.readouterr().err
    ub.run_uninstall(tub.dashboard(), data, out, tub.ga4_settings(ga4_audience=True, ga4_audience_budget_sec=60),
                     now=tub.NOW)
    err = capsys.readouterr().err
    assert len(calls) == 1 and calls[0][1] == 60
    lines = [ln for ln in err.splitlines() if ln.startswith("ga4 audience")]
    assert lines == ["ga4 audience: apps 2, with GA4 0, fetched 1, partial 1, fresh 0, failed 0, deferred 0, waiting 0, "
                     "calls 0, tokens 0 (~0 per app read), flagged 0 (other 0, thresholded 0, coverage off 0)"]
    monkeypatch.setattr(ga, "refresh_all", lambda *a, **k: 1 / 0)    # a failure costs this step only
    dash = tub.dashboard()
    ub.run_uninstall(dash, data, out, tub.ga4_settings(ga4_audience=True), now=tub.NOW)
    assert "ga4 audience skipped: ZeroDivisionError" in capsys.readouterr().err and dash["uninstall"]["apps"]
