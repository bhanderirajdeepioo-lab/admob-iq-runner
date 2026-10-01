"""SPEC_SIMPLIFY — the engines' additions (shown only; nothing decides on them) on synthetic data only:

  * every alert object (Uninstall incl. the update-impact families, Active users, Install value), open and closed:
    started ("Shuru": the day the change began in the data) / started_cap, seeded, opened_at (the build run that opened
    the episode — written once), and when closed closed_at + close_reason;
  * sort_alerts: severity, then the newest start first, then app / id — never fresh / opened;
  * info rows carry started; dashboard["active"|"value"] carry compact info / closed lists (≤ 5 per app, ≤ 90 days /
    closed ≤ 7 days) so the All-apps lists never depend on the opened per-app files;
  * ad-unit alerts (DATA.alerts.items[]) carry started (the halfway walk-back of the metric's daily series);
  * INVARIANCE: the synthetic histories the fixtures are built from give the same alerts, states and notifications
    with the additions perturbed (proof that no decision reads them) — only the added keys and the list order differ.
"""

import copy
import json
import os
from datetime import date, timedelta

import pytest

from admob_iq.api import dataservice
from admob_iq.engine import active as act
from admob_iq.engine import impact as imp
from admob_iq.engine import uninstall as U
from admob_iq.engine import value as V
from tests.uninstall_synth import END, check_simplify, make_store

AID = "ca-app-pub-0000000000000000~0000000042"
APP = "Demo Simplify"
T1, T2, T3, T4 = ("2026-09-21T01:00:00Z", "2026-09-21T02:00:00Z", "2026-09-22T01:00:00Z", "2026-09-23T01:00:00Z")
SEP = lambda d: date(2026, 9, d)                       # noqa: E731


def _dump(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False)


# ── opened_at: written once, when the episode opens ──────────────────────────────────────────────

def _ucond(dr="up", fam="rate_drift", **kw):
    c = {"key": AID + "|%s|%s" % (fam, dr), "family": fam, "dir": dr, "severity": "warning", "now": 5.6,
         "before": 4.1, "rel": 0.37, "z": 6.0, "since": "2026-09-03", "day": None, "users": 300, "delta_pp": None,
         "installs_from": None, "installs_to": None, "checkpoint": None, "n": None, "base_from": "2026-08-01",
         "base_to": "2026-09-02"}
    c.update(kw)
    return c


def test_opened_at_is_written_once_when_the_episode_opens_and_never_again():
    state = {}
    eps = U.update_episodes(state, AID, END, [_ucond()], True, False, T1)
    assert eps[0]["opened_at"] == T1
    before = _dump(state)
    U.update_episodes(state, AID, END, [_ucond()], False, False, T2)          # the hourly re-run, same E
    assert _dump(state) == before                                             # byte-identical
    eps = U.update_episodes(state, AID, END + timedelta(days=1), [_ucond(since="2026-09-04")], True, False, T3)
    assert eps[0]["opened_at"] == T1 and eps[0]["last"]["since"] == "2026-09-04"
    a = U.alert_obj(eps[0], APP, END + timedelta(days=1))
    assert a["opened_at"] == T1 and a["seeded"] is False and a["started"] == "2026-09-04" and a["started_cap"] is False
    check_simplify(a)


def test_an_episode_opened_before_the_change_reads_opened_at_none_never_an_invented_time():
    state = {}
    eps = U.update_episodes(state, AID, END, [_ucond()], True, True, T1)
    old = {k: v for k, v in eps[0].items() if k != "opened_at"}             # as an older build wrote it
    a = U.alert_obj(old, APP, END)
    assert a["opened_at"] is None and a["seeded"] is True
    closed = dict(old, closed="2026-09-20")                                  # … and one it closed
    a = U.alert_obj(closed, APP, END)
    assert a["closed_at"] is None and a["close_reason"] is None and a["opened_at"] is None
    check_simplify(a, closed=True)
    ep = {"id": "x", "app_id": AID, "family": "act_drift", "metric": "ret_dau", "key_metric": "ret_dau", "dir": "down",
          "opened": "2026-09-10", "last_true": "2026-09-19", "misses": 0, "notified_at": "sent", "seeded": False,
          "last": {"severity": "watch", "now": 900, "before": 1000, "rel": -0.1, "since": "2026-09-01", "z": -4.2}}
    a = act.alert_obj(ep, APP, END)
    assert a["opened_at"] is None and a["started"] == "2026-09-01"
    vep = {"id": "y", "app_id": AID, "family": "pay_slow", "metric": "b7", "cc": None, "dir": "down",
           "opened": "2026-09-06", "last_true": "2026-09-06", "misses": 0, "notified_at": None, "seeded": False,
           "last": {"severity": "watch", "week_from": "2026-08-24", "week_to": "2026-09-06", "now": 20, "before": 30}}
    a = V.alert_obj(vep, APP, SEP(6), 90)
    assert a["opened_at"] is None and a["started"] == "2026-08-24" and a["started_cap"] is False


# ── alert_at: when the ALERT came (owner, 1 Oct: "ye kab ka he? new alert he?") ────────────────────────────────

def test_alert_at_is_opened_at_then_the_notified_at_run_never_an_estimate():
    """alert_at = opened_at (the run that opened the episode) → else notified_at (an episode opened before opened_at was
    kept: the run that registered it for notification — the same run for a new one, the first run for a seeded one) →
    else None. Only a real recorded UTC run time counts: "sent", a date alone or nothing is never shown as a time."""
    assert U.alert_at({"opened_at": T2, "notified_at": T1}) == T2
    assert U.alert_at({"notified_at": T1}) == T1 and U.alert_at({"opened_at": None, "notified_at": T1}) == T1
    for bad in (None, "sent", "t0", "2026-09-21", "", 5):
        assert U.alert_at({"notified_at": bad}) is None, bad
        assert U.alert_at({"opened_at": bad, "notified_at": T3}) == T3, bad
    assert U.alert_at({}) is None


def test_every_engine_alert_carries_alert_at_open_and_closed():
    # Uninstall (a new episode: its opening run · an older one: its notified_at run · neither: None)
    state = {}
    eps = U.update_episodes(state, AID, END, [_ucond()], True, True, T1)          # first evaluation: seeded, sent T1
    a = U.alert_obj(eps[0], APP, END)
    assert a["alert_at"] == a["opened_at"] == T1
    old = {k: v for k, v in eps[0].items() if k != "opened_at"}                  # as a build before opened_at wrote it
    assert U.alert_obj(old, APP, END)["alert_at"] == T1 and U.alert_obj(old, APP, END)["opened_at"] is None
    assert U.alert_obj(dict(old, notified_at=None), APP, END)["alert_at"] is None
    assert U.alert_obj(dict(old, notified_at="sent"), APP, END)["alert_at"] is None
    c = U.alert_obj(dict(old, closed="2026-09-20"), APP, END)                     # closed: the same rule
    assert c["alert_at"] == T1 and c["closed_at"] is None
    check_simplify(c, closed=True)
    # an update's impact (uninstall alert family "impact")
    st = {}
    eps = imp.update_impact_episodes(st, "a", END, [_ic()], True, T2)
    a = U.alert_obj(eps[0], APP, END)
    assert a["family"] == "impact" and a["alert_at"] == T2
    ia = {k: v for k, v in eps[0].items() if k != "opened_at"}
    ia["notified_at"] = T3
    assert U.alert_obj(ia, APP, END)["alert_at"] == T3
    # Active users
    ep = {"id": "x", "app_id": AID, "family": "act_drift", "metric": "ret_dau", "key_metric": "ret_dau", "dir": "down",
          "opened": "2026-09-10", "last_true": "2026-09-19", "misses": 0, "notified_at": T1, "seeded": True,
          "last": {"severity": "watch", "now": 900, "before": 1000, "rel": -0.1, "since": "2026-09-01", "z": -4.2}}
    assert act.alert_obj(ep, APP, END)["alert_at"] == T1
    assert act.alert_obj(dict(ep, opened_at=T4), APP, END)["alert_at"] == T4
    assert act.alert_obj(dict(ep, notified_at="sent"), APP, END)["alert_at"] is None
    assert act.alert_obj(dict(ep, closed="2026-09-19"), APP, END)["alert_at"] == T1
    # Install value
    vep = {"id": "y", "app_id": AID, "family": "pay_slow", "metric": "b7", "cc": None, "dir": "down",
           "opened": "2026-09-06", "last_true": "2026-09-06", "misses": 0, "notified_at": T2, "seeded": False,
           "last": {"severity": "watch", "week_from": "2026-08-24", "week_to": "2026-09-06", "now": 20, "before": 30}}
    assert V.alert_obj(vep, APP, SEP(6), 90)["alert_at"] == T2
    assert V.alert_obj(dict(vep, opened_at=T1), APP, SEP(6), 90)["alert_at"] == T1
    assert V.alert_obj(dict(vep, notified_at=None), APP, SEP(6), 90)["alert_at"] is None


def test_the_full_uninstall_flow_keeps_the_first_runs_opened_at_and_an_hourly_rerun_changes_nothing():
    st = make_store(80, 1000, rate_fn=lambda c: 5.6 if c >= SEP(3) else 4.1, end=SEP(20))
    state = {}
    for day in (6, 7, 8, 9):
        U.evaluate_app(dict(st, window_end=SEP(day).isoformat()), AID, APP, state, T1)
    d, _ = U.evaluate_app(dict(st, window_end=SEP(10).isoformat()), AID, APP, state, T2)     # the drift opens here
    dr = [a for a in d["alerts"] if a["family"] == "rate_drift"]
    assert len(dr) == 1 and dr[0]["opened_at"] == T2 and dr[0]["started"] == dr[0]["since"] == "2026-09-03"
    before = _dump(state)
    U.evaluate_app(dict(st, window_end=SEP(10).isoformat()), AID, APP, state, T3)            # hourly: same E
    assert _dump(state) == before
    d, _ = U.evaluate_app(dict(st, window_end=SEP(11).isoformat()), AID, APP, state, T4)     # advanced
    dr = [a for a in d["alerts"] if a["family"] == "rate_drift"]
    assert dr and dr[0]["opened_at"] == T2 and state["episodes"][AID + "|rate_drift|up"]["opened_at"] == T2


# ── closed_at / close_reason ─────────────────────────────────────────────────────────────────────

def test_uninstall_closes_say_when_and_why():
    state = {}
    U.update_episodes(state, AID, END, [_ucond()], True, False, T1)
    for k in (1, 2):
        U.update_episodes(state, AID, END + timedelta(days=k), [], True, False, T2)
    assert not state["closed"]
    U.update_episodes(state, AID, END + timedelta(days=3), [], True, False, T3)      # CLOSE_EVALS quiet evaluations
    c = state["closed"][0]
    assert (c["closed"], c["closed_at"], c["close_reason"], c["opened_at"]) == ("2026-09-22", T3, "recovered", T1)
    a = U.alert_obj(c, APP, END + timedelta(days=3))
    assert a["closed_at"] == T3 and a["close_reason"] == "recovered" and a["notify"] is False
    check_simplify(a, closed=True)
    # a spike: a week after its last day → recovered
    st2 = {}
    spike = _ucond(fam="rate_spike", key=AID + "|rate_spike|up|2026-09-19", day=END, since=None, lo=3.5, hi=6.5)
    U.update_episodes(st2, AID, END, [spike], True, False, T1)
    U.update_episodes(st2, AID, END + timedelta(days=U.SPIKE_KEEP_DAYS + 1), [], True, False, T4)
    assert st2["closed"][0]["close_reason"] == "recovered" and st2["closed"][0]["closed_at"] == T4
    assert U.alert_obj(st2["closed"][0], APP, END)["started"] == "2026-09-19"
    # a cohort episode whose installs aged out (ALERT_RECENT_DAYS) → window_end, at once (even on an hourly run)
    st3 = {}
    coh = _ucond(fam="cohort", n=1, checkpoint="D1", now=0.3, before=0.2, installs_from="2026-07-01",
                 installs_to="2026-07-07", since=None)
    U.update_episodes(st3, AID, END, [coh], True, False, T1)
    U.update_episodes(st3, AID, END, [], False, False, T2, old_before=date(2026, 7, 20))
    assert st3["closed"][0]["close_reason"] == "window_end" and st3["closed"][0]["closed_at"] == T2


def _ic(level="hold", block="ver:1.1@2026-09-01", R="2026-09-01", seed=False):
    ver = block.split("@")[0][4:]
    return {"key": "a|impact|ver:%s" % ver, "family": "impact", "vers": [ver], "kind": "version", "dir": "up",
            "severity": imp.SEVERITY[level], "level": level, "block": block, "text": "x", "now": 1.0, "before": 1.1,
            "rel": -0.09, "delta_pp": None, "z": -4.0, "installs_from": R, "installs_to": R, "base_from": R,
            "base_to": R, "since": R, "day": None, "users": 1000, "checkpoint": None, "n": None, "also": [], "vs": [],
            "prov": False, "est": False, "release": {"key": block, "label": "v" + ver, "date": R},
            "rows": {"worse": ["time"], "better": []}, "seed": seed, "R": R}


def test_impact_closes_window_end_superseded_or_recovered_and_a_take_back_keeps_opened_at():
    E = SEP(10)
    state = {}
    imp.update_impact_episodes(state, "a", E, [_ic()], True, T1)
    assert state["episodes"]["a|impact|ver:1.1"]["opened_at"] == T1
    for k in (1, 2, 3):                                        # quiet; no newer update known → recovered
        imp.update_impact_episodes(state, "a", E + timedelta(days=k), [], True, T3, releases=[
            {"key": "ver:1.1@2026-09-01", "date": "2026-09-01", "versions": ["1.1"]},
            {"key": "ver:1.1.1@2026-09-03", "date": "2026-09-03", "versions": ["1.1", "1.1.1"]}])   # its own chain
    c = state["closed"][0]
    assert c["close_reason"] == "recovered" and c["closed_at"] == T3
    a = U.alert_obj(c, "Demo", E + timedelta(days=3))
    assert a["started"] == "2026-09-01" and a["close_reason"] == "recovered"
    # the same update comes back: taken back — closed / closed_at / close_reason gone, opened_at kept
    eps = imp.update_impact_episodes(state, "a", E + timedelta(days=4), [_ic()], True, T4)
    assert not state["closed"] and eps[0]["opened_at"] == T1
    assert not {"closed", "closed_at", "close_reason"} & set(eps[0])
    # … quiet again while a NEWER update came out → superseded
    for k in (5, 6, 7):
        imp.update_impact_episodes(state, "a", E + timedelta(days=k), [], True, T4, releases=[
            {"key": "ver:1.1@2026-09-01", "date": "2026-09-01", "versions": ["1.1"]},
            {"key": "ver:1.2@2026-09-12", "date": "2026-09-12", "versions": ["1.2"]}])
    assert state["closed"][0]["close_reason"] == "superseded"
    # an update older than IMPACT_ALERT_DAYS → window_end
    st2 = {}
    imp.update_impact_episodes(st2, "a", E, [_ic()], True, T1)
    imp.update_impact_episodes(st2, "a", date(2026, 10, 7), [], False, T2)
    assert st2["closed"][0]["close_reason"] == "window_end" and st2["closed"][0]["closed_at"] == T2


def test_a_late_impact_episode_closes_and_comes_back_the_same_way():
    lc = dict(_ic(block="ver:2.0@2026-08-08", R="2026-08-08"), key="a|impact_late", family="impact_late",
              rows={"worse": ["arpdau"], "told": []}, mixed=[], window=30)
    state, E = {}, SEP(18)
    imp.update_late_episodes(state, "a", E, lc, True, T1)
    for k in (1, 2, 3):
        imp.update_late_episodes(state, "a", E + timedelta(days=k), None, True, T3)
    c = state["closed"][0]
    assert c["close_reason"] == "recovered" and c["closed_at"] == T3 and c["opened_at"] == T1
    assert U.alert_obj(c, "Demo", E)["started"] == "2026-08-08"
    eps = imp.update_late_episodes(state, "a", E + timedelta(days=4), lc, True, T4)
    assert eps[0]["opened_at"] == T1 and "close_reason" not in eps[0] and "closed_at" not in eps[0]
    st2 = {}
    imp.update_late_episodes(st2, "a", E, lc, True, T1)
    imp.update_late_episodes(st2, "a", date(2026, 10, 30), None, False, T2)     # > LATE_ALERT_DAYS
    assert st2["closed"][0]["close_reason"] == "window_end"


def _acond(fam="act_drift", **kw):
    c = {"key": "a|%s|x" % fam, "family": fam, "metric": "ret_dau", "key_metric": "ret_dau", "dir": "down",
         "severity": "watch", "now": 900, "before": 1000, "rel": -0.1, "z": -4.5, "since": "2026-09-01", "day": None,
         "installs_from": None, "installs_to": None, "seed": False}
    c.update(kw)
    return c


def test_active_closes_recovered_or_window_end_and_opened_at_stays():
    st, E, rf = {}, SEP(19), SEP(19) - timedelta(days=act.ALERT_RECENT_DAYS)
    act.episodes(st, "a", E, [_acond()], True, T1, rf)
    act.episodes(st, "a", E, [_acond()], False, T2, rf)                       # hourly: nothing rewritten
    assert st["episodes"]["a|act_drift|x"]["opened_at"] == T1
    for k in (1, 2, 3):
        act.episodes(st, "a", E + timedelta(days=k), [], True, T3, rf)
    c = st["closed"][0]
    assert (c["close_reason"], c["closed_at"], c["opened_at"]) == ("recovered", T3, T1)
    a = act.alert_obj(c, APP, E + timedelta(days=3))
    assert a["started"] == "2026-09-01" and a["close_reason"] == "recovered"
    # act_return about installs older than ALERT_RECENT_DAYS → window_end
    st2 = {}
    ret = _acond("act_return", key="a|act_return|down", metric="d1", key_metric="ret", n=1, now=0.25, before=0.3,
                 installs_from="2026-07-01", installs_to="2026-07-07", since=None)
    act.episodes(st2, "a", E, [ret], True, T1, date(2026, 7, 1))
    act.episodes(st2, "a", E, [], False, T2, date(2026, 7, 20))
    assert st2["closed"][0]["close_reason"] == "window_end" and st2["closed"][0]["closed_at"] == T2
    # a spike's start is the episode's FIRST day, also after a later day folded into it
    st3 = {}
    sp = _acond("act_spike", key="a|act_spike|ret_dau|down|2026-09-16", day="2026-09-16", last_day="2026-09-16",
                days_list=["2026-09-16"], since=None, lo=950, hi=1050)
    act.episodes(st3, "a", E, [sp], True, T1, rf)
    sp2 = dict(sp, key="a|act_spike|ret_dau|down|2026-09-17", day="2026-09-17", last_day="2026-09-17",
               days_list=["2026-09-17"])
    eps = act.episodes(st3, "a", E + timedelta(days=1), [sp2], True, T3, rf)
    assert len(eps) == 1 and act.alert_obj(eps[0], APP, E)["started"] == "2026-09-16"


def _vcond(fam="pay_slow", wf="2026-08-24", **kw):
    c = {"key": "a|%s|down" % fam, "family": fam, "metric": "b7", "dir": "down", "cc": None, "severity": "watch",
         "seed": False, "week_from": wf, "week_to": "2026-09-06", "now": 20, "before": 30}
    c.update(kw)
    return c


def test_value_opened_at_first_changed_week_and_closes():
    st = V.empty_state()
    E = SEP(6)
    st, _ = V.episodes(st, "a", E, [_vcond()], True, T1)
    ep = st["episodes"]["a|pay_slow|down"]
    assert ep["opened_at"] == T1 and ep["week_from0"] == "2026-08-24"
    same, _ = V.episodes(st, "a", E, [_vcond(wf="2026-08-31")], False, T2)   # not advanced: a no-op
    assert _dump(same) == _dump(st)
    st, _ = V.episodes(st, "a", E + timedelta(days=7), [_vcond(wf="2026-08-31")], True, T3)
    ep = st["episodes"]["a|pay_slow|down"]
    assert ep["opened_at"] == T1 and ep["week_from0"] == "2026-08-24" and ep["last"]["week_from"] == "2026-08-31"
    a = V.alert_obj(ep, APP, E + timedelta(days=7), 90)
    assert a["started"] == "2026-08-24" and a["since"] == "2026-08-31"       # the change began in its first week
    for k in (2, 3):
        st, just = V.episodes(st, "a", E + timedelta(days=7 * k), [], True, T4)
    c = st["closed"][0]
    assert (c["close_reason"], c["closed_at"], c["opened_at"]) == ("recovered", T4, T1) and just == [c]
    a = V.alert_obj(c, APP, E + timedelta(days=21), 90)
    assert a["close_reason"] == "recovered" and a["closed_at"] == T4 and a["started"] == "2026-08-24"
    check_simplify(a, closed=True)
    # a version C no longer judges: its window ended
    st2 = V.empty_state()
    vr = _vcond("ver_ret", key="a|ver_ret|1.2|down", metric="d1", ver="1.2")
    st2, _ = V.episodes(st2, "a", E, [vr], True, T1)
    st2, _ = V.episodes(st2, "a", E + timedelta(days=7), [], True, T3, close={"a|ver_ret|1.2|down"})
    assert st2["closed"][0]["close_reason"] == "window_end"


# ── started: the cohort / return walk-back ───────────────────────────────────────────────────────

HS = date(2025, 8, 1)


def _cd(share, H=400, n=100):
    """Synthetic cohort data: every install day n installs, a share(i) of them uninstalled by day 1 (and after)."""
    cum = []
    for i in range(H):
        x = round(n(i) * share(i)) if callable(n) else round(n * share(i))
        cum.append([0] + [x] * (H - 1 - i))
    return {"hs": HS, "E": HS + timedelta(days=H - 1), "H": H,
            "n": [n(i) if callable(n) else n for i in range(H)], "cum": cum}


def _cs(cd, i_from, now=0.2, before=0.1):
    return {"n": 1, "now": now, "before": before, "installs_from": (HS + timedelta(days=i_from)).isoformat()}


def test_cohort_started_walks_back_to_the_first_week_closer_to_now():
    top = 400 - 2                                             # the newest install day complete for D1
    f = top - 6
    X = f - 21                                                # the change: 3 whole weeks before the alert's week
    cd = _cd(lambda i: 0.2 if i >= X else 0.1)
    st, cap = U.cohort_started(cd, _cs(cd, f))
    assert st == (HS + timedelta(days=X)).isoformat() and cap is False
    # the week before the alert's is already "before": its own week
    st, cap = U.cohort_started(_cd(lambda i: 0.2 if i >= f else 0.1), _cs(cd, f))
    assert st == (HS + timedelta(days=f)).isoformat() and cap is False
    # a week half-way (0.15) is not closer to now: the walk stops before it
    st, _ = U.cohort_started(_cd(lambda i: 0.2 if i >= X else (0.15 if i >= X - 7 else 0.1)), _cs(cd, f))
    assert st == (HS + timedelta(days=X)).isoformat()
    # a down move walks back the same way (now below before)
    st, _ = U.cohort_started(_cd(lambda i: 0.1 if i >= X else 0.2), _cs(cd, f, now=0.1, before=0.2))
    assert st == (HS + timedelta(days=X)).isoformat()


def test_cohort_started_stops_at_26_weeks_with_the_cap_and_at_a_week_without_data():
    top = 400 - 2
    f = top - 6
    cd = _cd(lambda i: 0.2)                                   # "now" for as far back as the data goes
    st, cap = U.cohort_started(cd, _cs(cd, f))
    assert cap is True and st == (HS + timedelta(days=f - 7 * U.STARTED_MAX_WEEKS)).isoformat()
    gap = _cd(lambda i: 0.2, n=lambda i: 0 if f - 14 <= i < f - 7 else 100)   # the 2nd week back: no installs
    st, cap = U.cohort_started(gap, _cs(gap, f))
    assert cap is False and st == (HS + timedelta(days=f - 7)).isoformat()
    # no cohort data / no numbers: its installs_from
    assert U.cohort_started(None, _cs(cd, f)) == ((HS + timedelta(days=f)).isoformat(), False)
    assert U.cohort_started(cd, dict(_cs(cd, f), now=None)) == ((HS + timedelta(days=f)).isoformat(), False)
    # the uninstall alert object uses it (a cohort episode), and falls back without cd
    ep = {"id": "i", "app_id": AID, "family": "cohort", "dir": "up", "opened": "2026-09-01", "last_true": "2026-09-01",
          "misses": 0, "notified_at": None, "seeded": False,
          "last": dict(_cs(cd, f), severity="watch", checkpoint="D1", installs_to=(HS + timedelta(days=top)).isoformat(),
                       vs=["prev"], also=[], delta_pp=10.0, z=5.0, users=700)}
    a = U.alert_obj(ep, APP, cd["E"], cd)
    assert a["started_cap"] is True and a["started"] == (HS + timedelta(days=f - 7 * U.STARTED_MAX_WEEKS)).isoformat()
    b = U.alert_obj(ep, APP, cd["E"])                          # no cohort data: its installs_from, no cap
    assert b["started"] == ep["last"]["installs_from"] and b["started_cap"] is False


def _P(rate, H=300, i0=0, new=1000, N=1):
    """Synthetic Active return series for return day N: new installs a day, a rate(i) of them back on day N."""
    pa, pn, pc = [0] * (H + 1), [0] * (H + 1), [0] * (H + 1)
    for i in range(H):
        ok = i + N <= H - 1
        pa[i + 1] = pa[i] + (round(new * rate(i)) if ok else 0)
        pn[i + 1] = pn[i] + (new if ok else 0)
        pc[i + 1] = pc[i] + (1 if ok else 0)
    PA, PN, PC = [None] * (N + 1), [None] * (N + 1), [None] * (N + 1)
    PA[N], PN[N], PC[N] = pa, pn, pc
    return {"hs": HS, "H": H, "i0": i0, "PA": PA, "PN": PN, "PC": PC}


def test_act_return_started_walks_the_return_series_back():
    f = 300 - 1 - 1 - 6
    X = f - 14
    P = _P(lambda i: 0.25 if i >= X else 0.3)
    s = {"n": 1, "now": 0.25, "before": 0.3, "installs_from": (HS + timedelta(days=f)).isoformat()}
    assert act.return_started(P, s) == ((HS + timedelta(days=X)).isoformat(), False)
    P = _P(lambda i: 0.25)
    st, cap = act.return_started(P, s)
    assert cap is True and st == (HS + timedelta(days=f - 7 * U.STARTED_MAX_WEEKS)).isoformat()
    P = _P(lambda i: 0.25, i0=f - 10)                          # the launch: nothing before it (its week: from it)
    assert act.return_started(P, s) == ((HS + timedelta(days=f - 10)).isoformat(), False)
    assert act.return_started(None, s) == (s["installs_from"], False)
    ep = {"id": "r", "app_id": AID, "family": "act_return", "metric": "d1", "key_metric": "ret", "dir": "down",
          "opened": "2026-09-01", "last_true": "2026-09-01", "misses": 0, "notified_at": None, "seeded": True,
          "last": dict(s, severity="watch", metric="d1", installs_to="2026-09-10", z=-5.0, rel=-0.17, delta_pp=-5.0)}
    a = act.alert_obj(ep, APP, date(2026, 9, 14), _P(lambda i: 0.25 if i >= X else 0.3))
    assert a["started"] == (HS + timedelta(days=X)).isoformat() and a["seeded"] is True


def test_started_per_family_in_the_uninstall_alert_object():
    base = {"id": "x", "app_id": AID, "dir": "up", "opened": "2026-09-10", "last_true": "2026-09-10", "misses": 0,
            "notified_at": None, "seeded": False}
    drift = dict(base, family="rate_drift", last={"since": "2026-09-03", "severity": "warning", "now": 5.6,
                                                   "before": 4.1, "rel": 0.37})
    assert U.alert_obj(drift, APP, END)["started"] == "2026-09-03"
    spike = dict(base, family="rate_spike", day="2026-09-15", last_day="2026-09-16",
                 last={"day": "2026-09-15", "severity": "warning", "now": 8.0, "before": 5.0, "lo": 3, "hi": 6, "users": 9})
    assert U.alert_obj(spike, APP, END)["started"] == "2026-09-15"
    impact = dict(base, family="impact", last={"release": {"key": "k", "label": "v2", "date": "2026-09-02"},
                                               "R": "2026-09-02", "since": "2026-09-02", "severity": "watch",
                                               "text": "x", "now": 1, "before": 1.1})
    assert U.alert_obj(impact, APP, END)["started"] == "2026-09-02"


# ── sort_alerts: never fresh / opened ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sort", [U.sort_alerts, act.sort_alerts, V.sort_alerts])
def test_sort_alerts_orders_by_severity_then_newest_start_never_by_fresh_or_opened(sort):
    mk = lambda sev, app, started, fresh, opened: {"severity": sev, "app": app, "id": app, "started": started,  # noqa
                                                   "fresh": fresh, "opened": opened}
    a = [mk("watch", "w", "2026-09-01", True, "2026-09-19"), mk("warning", "old", "2026-06-01", True, "2026-09-19"),
         mk("warning", "new", "2026-09-10", False, "2026-08-01"), mk("warning", "none", None, True, "2026-09-19"),
         mk("good", "g", "2026-09-18", True, "2026-09-19")]
    assert [x["app"] for x in sort(a)] == ["new", "old", "none", "w", "g"]
    flipped = [dict(x, fresh=not x["fresh"], opened="2026-01-01") for x in a]    # fresh / opened change nothing
    assert [x["app"] for x in sort(flipped)] == ["new", "old", "none", "w", "g"]
    tie = [mk("watch", "B", "2026-09-01", False, "2026-09-01"), mk("watch", "a", "2026-09-01", True, "2026-09-19")]
    assert [x["app"] for x in sort(tie)] == ["a", "B"]                             # then app (casefolded), id


# ── the compact lists ─────────────────────────────────────────────────────────────────────────────

def _row(kind, frm, to, **kw):
    return dict({"kind": kind, "metric": "ret_dau", "dir": "down", "from": frm, "to": to, "rel": -0.1, "text": kind,
                 "tags": [], "prov": False, "sp": None, "started": frm}, **kw)


def test_active_compact_info_at_most_5_per_app_newest_first_and_90_days():
    E = date(2026, 9, 20)
    d = lambda k: (E - timedelta(days=k)).isoformat()          # noqa: E731
    detail = {"app_id": AID, "data_till": E.isoformat(),
              "changes": {"info": [_row("price", d(13), d(7)), _row("early", d(0), d(0), prov=True, sp=["ret", 1])],
                          "older": [dict(_row("act_drift", d(40), d(30)), release={"key": "k", "label": "v", "date": d(41)},
                                         before=1, now=2, z=4.0),
                                    _row("act_spike", d(50), d(50)), _row("act_spike", d(60), d(60)),
                                    _row("act_spike", d(89), d(89)), _row("act_spike", d(91), d(91))]}}
    rows = act.compact_info(detail)
    assert [r["kind"] for r in rows] == ["early", "price", "act_drift", "act_spike", "act_spike"]
    assert [r["to"] for r in rows] == [d(0), d(7), d(30), d(50), d(60)]          # newest first, ≤ 5
    assert all(set(r) - {"sp"} == {"app_id", "src", "kind", "metric", "dir", "from", "to", "rel", "text", "tags",
                                   "prov", "release", "started"} for r in rows)
    assert rows[0]["sp"] == ["ret", 1] and "sp" not in rows[1] and rows[0]["prov"] is True
    assert rows[2]["src"] == "older" and rows[2]["release"]["key"] == "k" and rows[0]["release"] is None
    assert all(r["started"] == r["from"] for r in rows)
    detail["changes"] = {"info": [], "older": [_row("act_spike", d(89), d(89)), _row("act_spike", d(91), d(91))]}
    assert [r["to"] for r in act.compact_info(detail)] == [d(89)]                  # > 90 days: never listed


def test_closed_lists_keep_the_last_7_days_only():
    E = date(2026, 9, 20)
    mk = lambda k, i: {"id": i, "app": "A", "closed": (E - timedelta(days=k)).isoformat()}   # noqa: E731
    det = {"data_till": E.isoformat(), "changes": {"closed": [mk(0, "a"), mk(7, "b"), mk(8, "c"), mk(30, "d")]}}
    assert [a["id"] for a in act.recent_closed(det)] == ["a", "b"]
    assert [a["id"] for a in V.recent_closed(det["changes"]["closed"], E.isoformat())] == ["a", "b"]
    assert [a["id"] for a in act.sort_closed([mk(7, "b"), mk(0, "z"), mk(0, "a")])] == ["a", "z", "b"]


def test_value_compact_info_rows():
    S = date(2026, 9, 20)
    d = lambda k: (S - timedelta(days=k)).isoformat()          # noqa: E731
    info = [{"kind": "spend", "from": d(20), "to": None, "text": "t"}, {"kind": "k", "from": None, "to": None, "text": "k"},
            {"kind": "mix", "cc": "NG", "from": d(13), "to": d(7), "text": "m"},
            {"kind": "ver_mix", "ver": "1.2", "from": d(100), "to": d(95), "text": "old"},
            {"kind": "long_up", "from": d(60), "to": d(30), "text": "l", "release": {"date": d(61)}}]
    for r in info:
        r["started"] = r.get("from")
    rows = V.compact_info({"app_id": AID, "settled_till": S.isoformat(), "changes": {"info": info, "older": []}})
    assert [r["kind"] for r in rows] == ["k", "mix", "spend", "long_up"]          # undated = current; > 90 days: out
    assert rows[1]["cc"] == "NG" and "cc" not in rows[0] and rows[3]["release"] == {"date": d(61)}
    assert all(set(r) - {"cc", "release"} == {"app_id", "src", "kind", "from", "to", "text", "started"} for r in rows)


# ── ad-unit alerts ────────────────────────────────────────────────────────────────────────────────

def test_started_day_walks_back_to_the_halfway_crossing():
    days = ["2026-09-%02d" % d for d in range(1, 11)]
    ser = [100] * 7 + [30, 30, 30]
    assert dataservice.started_day(ser, days, 100, 30) == "2026-09-08"
    assert dataservice.started_day([100] * 9 + [30], days, 100, 30) == "2026-09-10"   # only the latest day
    assert dataservice.started_day([100] * 6 + [60, 50, 40, 30], days, 100, 30) == "2026-09-07"   # all under 65
    assert dataservice.started_day([100] * 6 + [60, 70, 80, 30], days, 100, 30) == "2026-09-10"   # 80: not past it
    assert dataservice.started_day([1, 1, 1, 1, 1, 1, 1, 4, 5, 6], days, 1, 6) == "2026-09-08"  # a spike: upward
    assert dataservice.started_day([5] * 10, days, 5, 5) == "2026-09-10"
    assert dataservice.started_day([], [], 1, 2) is None


def test_ad_unit_items_carry_started_and_nothing_else_moves():
    from admob_iq.db import InMemoryRepo
    from tests.test_api_data import _net_row
    repo = InMemoryRepo()
    latest = date(2026, 7, 25)
    unit = "ca-app-pub-1/3333"
    for i in range(14):
        earn = 100.0 if i < 11 else 20.0                            # the last 3 finished days crashed
        repo.upsert_network(_net_row(str(latest - timedelta(days=13 - i)), unit, earn))
    d = dataservice.build_from_db(repo, today=date(2026, 7, 26))
    it = next(a for a in d["alerts"]["items"] if a["id"] == unit)
    rev = next(m for m in it["metrics"] if m["metric"] == "revenue")
    assert rev["started"] == "2026-07-23" and it["started"] == "2026-07-23"
    assert set(rev) == {"metric", "message", "current", "lost", "kind", "started"}
    assert set(it) == {"place", "id", "app", "country", "base_rev", "severity", "kind", "lost", "metrics", "started"}


# ── invariance: the additions decide nothing ─────────────────────────────────────────────────────

NEW_KEYS = {"started", "started_cap", "opened_at", "alert_at", "closed_at", "close_reason", "week_from0"}


def _is_alert(x):
    return isinstance(x, dict) and "id" in x and "source" in x and "family" in x


def _strip(x, path=""):
    """Everything SPEC_SIMPLIFY added taken back out; alert lists by id (their order is the one specified change);
    the build hashes (asset_v / sig: of the content, new keys included) and mark_notified's wall-clock time (whether
    it is set is what counts) normalised."""
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            if k in NEW_KEYS or k in ("asset_v", "sig") or (k == "seeded" and _is_alert(x)):
                continue
            if k in ("info", "closed") and path.endswith(("/dashboard_active", "/dashboard_value")):
                continue
            out[k] = (v is not None) if k == "notified_at" else _strip(v, path + "/" + k)
        return out
    if isinstance(x, list):
        items = [_strip(v, path + "[]") for v in x]
        if items and all(_is_alert(v) for v in x):
            items.sort(key=lambda a: a["id"])
        return items
    return x


def _states(work):
    out = {}
    d = os.path.join(work, "data", "ga4_uninstall")
    for n in ("state.json", "active_state.json", "value_state.json"):
        p = os.path.join(d, n)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                out[n] = json.load(f)
    return out


def _lines(fx):
    for s in fx.get("sent") or []:
        for ch in ("telegram", "email"):
            if s.get(ch):
                s[ch] = sorted(s[ch].splitlines())        # one message's lines: in the (new) alert order
    return fx


def _run_all(root):
    from tests import make_uninstall_fixture as mu
    from tests import value_synth as vs
    out = {}
    for name, fn in (("uninstall", mu.build_fixture), ("active", mu.build_active_fixture), ("value", vs.build_fixture)):
        work = os.path.join(root, name)
        os.makedirs(work, exist_ok=True)
        out[name] = {"out": fn(work), "state": _states(work)}
    return out


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """The fixtures' synthetic histories (7 daily Uninstall runs, 7 daily Active runs, 6 weekly Install value runs):
    as built, and again with every addition perturbed (another start, cap, close reason and close time)."""
    real = _run_all(str(tmp_path_factory.mktemp("real")))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(U, "started_of", lambda ep, cd=None: ("2001-01-01", True))
        mp.setattr(U, "cohort_started", lambda cd, s, max_weeks=26: ("2001-01-01", True))
        mp.setattr(act, "started_of", lambda ep, P=None: ("2001-01-01", True))
        mp.setattr(V, "started_of", lambda ep: "2001-01-01")
        mp.setattr(U, "close_ep", lambda ep, E_iso, now, reason: dict(ep, closed=E_iso, closed_at="perturbed",
                                                                      close_reason="seed_cleanup"))
        mp.setattr(U, "alert_at", lambda ep: "1999-01-01T00:00:00Z")
        pert = _run_all(str(tmp_path_factory.mktemp("pert")))
    return real, pert


def test_the_additions_decide_nothing_alerts_states_and_notifications_are_the_same(runs):
    real, pert = runs
    for name in ("uninstall", "active", "value"):
        a, b = copy.deepcopy(real[name]), copy.deepcopy(pert[name])
        assert _strip(_lines(a["out"]), "") == _strip(_lines(b["out"]), ""), name
        assert _strip(a["state"]) == _strip(b["state"]), name
    # … and the perturbation did reach the outputs (the test would catch a decision that read them)
    al = pert["uninstall"]["out"]["dashboard_uninstall"]["alerts"]
    assert al and all(a["started"] == "2001-01-01" and a["started_cap"] for a in al)
    assert all(a["alert_at"] == "1999-01-01T00:00:00Z" for a in al)
    for name, sec in (("active", "dashboard_active"), ("value", "dashboard_value")):
        assert all(a["alert_at"] == "1999-01-01T00:00:00Z" for a in pert[name]["out"][sec]["alerts"]), name


def _decisions(fx_alerts):
    return sorted((a["id"], a["severity"], a["notify"], a.get("seeded"), json.dumps(a.get("sp"))) for a in fx_alerts)


def test_decision_fields_ids_severities_notify_sp_and_open_closed_sets_are_unchanged(runs):
    real, pert = runs
    U_r, U_p = real["uninstall"]["out"], pert["uninstall"]["out"]
    assert _decisions(U_r["dashboard_uninstall"]["alerts"]) == _decisions(U_p["dashboard_uninstall"]["alerts"])
    for ar, ap in zip(U_r["asset"]["apps"], U_p["asset"]["apps"]):
        assert _decisions(ar["alerts"]) == _decisions(ap["alerts"])
        assert _decisions(ar["alerts_closed"]) == _decisions(ap["alerts_closed"])
    A_r, A_p = real["active"]["out"]["dashboard_active"], pert["active"]["out"]["dashboard_active"]
    assert _decisions(A_r["alerts"]) == _decisions(A_p["alerts"]) and A_r["alert_counts"] == A_p["alert_counts"]
    V_r, V_p = real["value"]["out"]["dashboard_value"], pert["value"]["out"]["dashboard_value"]
    assert _decisions(V_r["alerts"]) == _decisions(V_p["alerts"]) and V_r["alert_counts"] == V_p["alert_counts"]
    for name, st in (("uninstall", "state.json"), ("active", "active_state.json"), ("value", "value_state.json")):
        sr, sp = real[name]["state"].get(st), pert[name]["state"].get(st)
        assert sorted(sr["episodes"]) == sorted(sp["episodes"]), name
        assert sorted(e["id"] for e in sr["closed"]) == sorted(e["id"] for e in sp["closed"]), name
        assert sr.get("eval") == sp.get("eval"), name


def test_the_built_alerts_carry_the_additions_and_the_lists_keep_their_caps(runs):
    real, _ = runs
    Ufx = real["uninstall"]["out"]
    for a in Ufx["dashboard_uninstall"]["alerts"]:
        check_simplify(a)
        assert a["opened_at"] is not None and a["started"] is not None
        if a["family"] == "rate_drift":
            assert a["started"] == a["since"]
        if a["family"] in ("rate_spike", "rate_zero"):
            assert a["started"] == a["day"]
        if a["family"] in ("impact", "impact_late"):
            assert a["started"] == a["release"]["date"]
        if a["family"] == "cohort":
            assert a["started"] <= a["installs_from"]
    for ap in Ufx["asset"]["apps"]:
        for o in ap["old_changes"]:
            assert o["started"] <= o["installs_from"]
    A = real["active"]["out"]["dashboard_active"]
    per = {}
    for r in A["info"]:
        per[r["app_id"]] = per.get(r["app_id"], 0) + 1
        E = next(x["data_till"] for x in A["apps"] if x["app_id"] == r["app_id"])
        assert (date.fromisoformat(E) - date.fromisoformat(r["to"] or r["from"])).days <= act.INFO_MAX_DAYS
    assert A["info"] and max(per.values()) <= act.INFO_PER_APP
    for a in A["alerts"]:
        check_simplify(a)
    for a in A["closed"]:
        check_simplify(a, closed=True)
    Vd = real["value"]["out"]["dashboard_value"]
    for a in Vd["alerts"]:
        check_simplify(a)
        assert a["started"] <= a["week_from"]
    # every state episode written by these runs carries its opening run's time
    for name, st in (("uninstall", "state.json"), ("active", "active_state.json"), ("value", "value_state.json")):
        for e in real[name]["state"][st]["episodes"].values():
            assert e.get("opened_at") and e["opened_at"].endswith("Z"), (name, e["id"])
    # … and every built alert says when it came: its opening run (alert_at = opened_at on these new histories)
    for a in Ufx["dashboard_uninstall"]["alerts"] + A["alerts"] + A["closed"] + Vd["alerts"]:
        assert a["alert_at"] and a["alert_at"] == a["opened_at"], a["id"]
