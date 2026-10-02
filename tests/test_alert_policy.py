"""The one alert policy of the three GA4 tabs (Active users, Uninstall, Install value): the owner's metrics do not move
meaningfully day to day, so an alert rests on ≥ 10 FINAL days (never one day, never a provisional one), is MATERIAL (the
users or the money it moves a day), holds (both halves of its window / a few daily evaluations), is told once per
cause, and good news only when it is big. Everything smaller stays visible in the tab — never sent. The first build on
these rules closes an open alert they would not open with the reason "rule_tuned", and sends nothing.
All data is synthetic."""

from datetime import date, timedelta

from admob_iq.engine import active as act
from admob_iq.engine import uninstall as eng
from admob_iq.engine import value as V
from tests.test_active_engine import S, daily, quiet, run, settle
from tests.uninstall_synth import DEFAULT_RET, END, make_store

ALERT_POLICY_TESTS = True              # (tests/conftest.py: the Uninstall / Install value gate is ON in this module)
AID = "ca-app-pub-0000000000000000~0000000001"


def _opened(d, fam=None):
    return [a for a in d["changes"]["open"] if fam is None or a["family"] == fam]


# ── Active users ─────────────────────────────────────────────────────────────────────────────────

def test_active_a_drift_needs_ten_final_days():
    """Old users −15% for 4 settled days, then back (a few days' wobble — the old rules' 7-day window told it): never
    an alert — a shift is judged over ≥ 10 settled days and must still hold on the newest ones. The same drop that
    stays: an alert, its window ≥ 10 days."""
    a = S - timedelta(days=20)
    short, rv = quiet(old=lambda d: 20000 * (0.85 if a <= d < a + timedelta(days=4) else 1.0))
    sent, *_ = daily(short, rv, a - timedelta(days=2), END)
    assert not [x for x in sent if x[1] == "act_drift"], sent
    stays, rv2 = quiet(old=lambda d: 20000 * (0.85 if d >= a else 1.0))
    ast = {}
    sent, d, *_ = daily(stays, rv2, a - timedelta(days=2), END, ast)
    first = [x for x in sent if x[1] == "act_drift" and x[3] == "down"][0]
    ep = [e for e in ast["episodes"].values() if e["family"] == "act_drift"][0]
    assert ep["opened"] == first[0] and ep["last"]["days"] >= act.DRIFT_L[0] == 10


def test_active_a_drift_is_seen_in_both_halves_of_its_window():
    """A shift whose first days barely moved and whose last days dropped hard is no steady shift yet: each half of the
    window must have moved ≥ DRIFT_HALF × the minimum effect, the same way."""
    a = S - timedelta(days=12)                                           # −1.5% for 8 days, then −25% for 5
    st, rv = quiet(old=lambda d: 20000 * (0.985 if a <= d < a + timedelta(days=8) else 0.75 if d >= a + timedelta(days=8)
                                          else 1.0))
    _, _, _, _, udet = run(st, rv)
    P = act.prepare(dict(st, window_end=END.isoformat()), udet, rv, END)
    down = act._drift_at(P, "ret_dau", P["iS"])["down"]
    assert down is None                                                 # no ≥ 10-day window has both halves moved
    act.DRIFT_HALF, keep = 0.0, act.DRIFT_HALF
    try:
        loose = act._drift_at(P, "ret_dau", P["iS"])["down"]
    finally:
        act.DRIFT_HALF = keep
    assert loose is not None and loose["L"] >= 10                        # (the rule is what keeps it out)


def test_active_a_small_change_is_info_never_an_alert():
    """A tiny app's −15% (≈ 45 users a day, a few cents) is real but small: an info row ("chhota badlaav"), no alert.
    The same −15% on a big app is an alert."""
    a = S - timedelta(days=20)
    tiny, rv = quiet(old=lambda d: 300 * (0.85 if d >= a else 1.0), new=20)
    d = settle(tiny, rv, END, {}, {})
    assert _opened(d) == []
    small = [i for i in d["changes"]["info"] if i["kind"] == "small" and i["metric"] == "ret_dau"]
    assert small and small[0]["dir"] == "down" and "chhota badlaav" in small[0]["text"] and "alert nahi" in small[0]["text"]
    big, rv2 = quiet(old=lambda d: 20000 * (0.85 if d >= a else 1.0))
    d2 = settle(big, rv2, END, {}, {})
    assert [(x["family"], x["metric"], x["dir"]) for x in _opened(d2)] == [("act_drift", "ret_dau", "down")]


def test_active_good_news_only_when_big():
    """+7% old users (real, but under 2 × the minimum effect) is info; +25% is good news."""
    a = S - timedelta(days=20)
    up7, rv = quiet(old=lambda d: 20000 * (1.07 if d >= a else 1.0))
    d = settle(up7, rv, END, {}, {})
    assert not [x for x in _opened(d) if x["dir"] == "up"]
    assert [i for i in d["changes"]["info"] if i["kind"] == "small" and i["dir"] == "up"
            and "achha badlaav par bada nahi" in i["text"]]
    up25, rv2 = quiet(old=lambda d: 20000 * (1.25 if d >= a else 1.0))
    d2 = settle(up25, rv2, END, {}, {})
    assert [(x["family"], x["dir"], x["severity"]) for x in _opened(d2)] == [("act_drift", "up", "good")]


def test_active_return_rates_need_two_weeks_of_install_days():
    """D1 −4 points on the newest 7 install days only: half the alert window — no alert. 14 install days: an alert."""
    for days, want in ((7, []), (14, [("d1", "down")])):
        lo = S - timedelta(days=days)
        st, rv = quiet(new=2000, rho=lambda c, k: DEFAULT_RET(k) - (0.04 if k == 1 and lo <= c <= S - timedelta(days=1)
                                                                       else 0.0))
        d, *_ = run(st, rv, astate={"eval": {}, "episodes": {}, "closed": []})
        assert [(a["metric"], a["dir"]) for a in _opened(d, "act_return")] == want, days


def _closed_drift(reason, closed):
    return {"id": "a|active_act_drift_ret_dau|old", "app_id": "a", "family": "act_drift", "metric": "ret_dau",
            "key_metric": "ret_dau", "dir": "down", "opened": (closed - timedelta(days=20)).isoformat(),
            "last_true": closed.isoformat(), "misses": 3, "notified_at": "2026-08-01T12:00:00Z", "notified_dry": False,
            "seeded": False,
            "last": {"family": "act_drift", "metric": "ret_dau", "dir": "down", "since": "2026-08-01",
                     "severity": "watch", "now": 17000.0, "before": 20000.0, "rel": -0.15, "z": -6.0, "days": 14,
                     "users": 17000, "base_from": "2026-07-04", "base_to": "2026-07-31", "tags": []},
            "opened_at": None, "closed": closed.isoformat(), "closed_at": None, "close_reason": reason}


def test_active_the_same_story_back_soon_is_shown_not_sent_again():
    """A drop that closed ≤ REOPEN_SEED_DAYS ago and is back: shown, never re-sent. Closed longer ago — or closed only
    because the rules changed — it is news again."""
    a = S - timedelta(days=20)
    st, rv = quiet(old=lambda d: 20000 * (0.85 if d >= a else 1.0))
    for reason, ago, notify in (("recovered", 5, False), ("recovered", 30, True), ("rule_tuned", 5, True)):
        ast, ust = {}, {}
        run(st, rv, END - timedelta(days=60), ast, ust)                       # (the first evaluation: before it)
        ast["closed"].append(_closed_drift(reason, END - timedelta(days=ago)))
        d = settle(st, rv, END, ast, ust)
        dr = [x for x in _opened(d, "act_drift") if x["metric"] == "ret_dau"]
        assert len(dr) == 1 and dr[0]["notify"] is notify, (reason, ago)


def test_active_one_cause_several_metrics_is_one_alert():
    """Old users and ads per user fall from the same day: one alert is sent, the other is shown with it (never sent on
    its own) and each one's text lists the other metric."""
    a = S - timedelta(days=20)
    st, rv = quiet(old=lambda d: 20000 * (0.8 if d >= a else 1.0), ipu=lambda d, v: 4.0 * (0.8 if d >= a else 1.0))
    ast, ust = {}, {}
    run(st, rv, END - timedelta(days=60), ast, ust)
    sent, d, *_ = daily(st, rv, a, END, ast, ust)
    down = [x for x in _opened(d) if x["dir"] == "down"]
    assert {x["metric"] for x in down} == {"ret_dau", "ads"}
    assert len([x for x in sent if x[3] == "down"]) == 1, sent
    assert all(" · saath me: " in x["text"] and x["message"].endswith(x["text"]) for x in down)
    by = {x["metric"]: x for x in down}
    assert "ads per user bhi kam" in by["ret_dau"]["text"] and "old users bhi kam" in by["ads"]["text"]


def test_active_switch_over_closes_what_the_tuned_rules_would_not_open():
    """The first build on the tuned rules: an open alert they would not open (a one-day spike) closes at once with the
    reason "rule_tuned" and is never sent; one they would still open stays open; the state records the rules."""
    a = S - timedelta(days=20)
    st, rv = quiet(old=lambda d: 20000 * (0.85 if d >= a else 1.0))
    ast, ust = {}, {}
    run(st, rv, END - timedelta(days=60), ast, ust)
    settle(st, rv, END - timedelta(days=1), ast, ust)
    assert [e["family"] for e in ast["episodes"].values()] == ["act_drift"]
    day = (S - timedelta(days=4)).isoformat()
    sid = "a|active_act_spike_time|old"
    spike = {"id": sid, "app_id": "a", "family": "act_spike", "metric": "time", "key_metric": "time",
             "dir": "down", "opened": day, "last_true": day, "misses": 0, "notified_at": None, "notified_dry": False,
             "seeded": False, "day": day, "last_day": day, "days": [day], "opened_at": "2026-09-15T01:00:00Z",
             "last": {"family": "act_spike", "metric": "time", "dir": "down", "severity": "watch", "day": day,
                      "last_day": day, "now": 200.0, "before": 280.0, "lo": 250.0, "hi": 310.0, "rel": -0.29,
                      "users": 20000, "tags": []}}
    ast["episodes"]["a|act_spike|time|down|%s" % day] = spike         # opened by the old rules, its send still due
    ast["eval"]["a"].pop("rules")                                     # (a state the old rules wrote)
    d, *_ = run(st, rv, END, ast, ust, now="2026-09-21T02:00:00Z")
    assert [a_["family"] for a_ in _opened(d)] == ["act_drift"]
    cl = [c for c in d["changes"]["closed"] if c["id"] == sid]
    assert len(cl) == 1 and cl[0]["close_reason"] == "rule_tuned" and cl[0]["notify"] is False
    assert cl[0]["closed_at"] == "2026-09-21T02:00:00Z" and ast["eval"]["a"]["rules"] == act.RULES_V
    assert "rule_tuned" in eng.CLOSE_REASONS


def test_active_switch_over_sends_nothing_new():
    """Whatever the tuned rules open on their first build is shown, never sent (no burst on the day they go live)."""
    a = S - timedelta(days=20)
    st, rv = quiet(old=lambda d: 20000 * (0.85 if d >= a else 1.0))
    ast, ust = {}, {}
    run(st, rv, END - timedelta(days=60), ast, ust)
    ast["eval"]["a"].pop("rules")
    ast["eval"]["a"]["streak"] = {"act_drift|ret_dau|down": 5}         # (the old rules saw it for days)
    ast["eval"]["a"]["since"] = {"act_drift|ret_dau|down": (END - timedelta(days=6)).isoformat()}
    d, *_ = run(st, rv, END, ast, ust)
    dr = _opened(d, "act_drift")
    assert dr and not any(x["notify"] for x in dr) and all(x["seeded"] for x in dr)


# ── Uninstall ────────────────────────────────────────────────────────────────────────────────────

def _ev(store, state, E, now=None):
    d, _ = eng.evaluate_app(dict(store, window_end=E.isoformat()), AID, "App", state,
                            now or E.isoformat() + "T12:00:00Z")
    return d


def _days(store, first, last, state=None):
    """Daily builds, every due alert marked sent → (sent [(E, family, dir, provisional, installs_to)], last detail)."""
    state = {} if state is None else state
    sent, E, d = [], first, None
    while E <= last:
        d = _ev(store, state, E)
        for a in d["alerts"]:
            if a["notify"]:
                sent.append((E, a["family"], a["dir"], a["provisional"], a.get("installs_to")))
                for ep in state["episodes"].values():
                    if ep["id"] == a["id"]:
                        ep["notified_at"] = E.isoformat() + "T12:00:00Z"
        E += timedelta(days=1)
    return sent, d


def _bump(delta, since):
    return lambda c: {1: delta, 2: -delta} if c >= since else None


def test_uninstall_a_cohort_rise_waits_for_final_days_and_three_evaluations(monkeypatch):
    """+7 points uninstalled within 1 day from an install day on: the old rules sent it while those days were still
    provisional; the policy sends it once ≥ 7 FINAL install days moved and held on 3 daily evaluations — once."""
    since = END - timedelta(days=24)
    st = make_store(90, 1000, bump=_bump(70, since))
    first, last = END - timedelta(days=26), END
    sent, _ = _days(st, first, last, {})
    co = [x for x in sent if x[1] == "cohort"]
    assert len(co) == 1 and co[0][2] == "up" and co[0][3] is False
    assert date.fromisoformat(co[0][4]) + timedelta(days=1) <= co[0][0] - timedelta(days=eng.LATE_DAYS)  # final days
    monkeypatch.setattr(eng, "ALERT_POLICY", False)
    old, _ = _days(st, first, last, {})
    old_co = [x for x in old if x[1] == "cohort"]
    assert old_co[0][3] is True and old_co[0][0] < co[0][0]           # (before: sent on provisional days, earlier)


def test_uninstall_a_small_cohort_change_is_not_an_alert(monkeypatch):
    """The same +7 points on 100 installs a day is 7 more uninstalls a day: under MAT_UNINSTALLS — shown in the tab's
    rows, never an alert; on 1,000 installs a day (70 a day) it is one."""
    since = END - timedelta(days=15)
    for per_day, want in ((100, 0), (1000, 1)):
        st = make_store(90, per_day, bump=_bump(70, since))
        d = _ev(st, {}, END)                                            # (a first evaluation: everything shown)
        assert len([a for a in d["alerts"] if a["family"] == "cohort"]) == want, per_day
        monkeypatch.setattr(eng, "ALERT_POLICY", False)                 # (the old rules: an alert either way)
        assert [a for a in _ev(st, {}, END)["alerts"] if a["family"] == "cohort"], per_day
        monkeypatch.setattr(eng, "ALERT_POLICY", True)
    assert eng.MAT_UNINSTALLS == 50


def _rate(days, fn):
    return make_store(days, 1000, rate_fn=fn)


def test_uninstall_one_day_is_never_an_alert_and_a_tracking_break_needs_two():
    spike = _rate(60, lambda c: 12.0 if c == END - timedelta(days=8) else 5.0)
    d = _ev(spike, {}, END)
    assert not [a for a in d["alerts"] if a["family"] == "rate_spike"]
    assert d["daily"]["hi"][-9] is not None                            # (the band still shows the day)
    one = _rate(60, lambda c: 0.0 if c == END - timedelta(days=8) else 5.0)
    assert not [a for a in _ev(one, {}, END)["alerts"] if a["family"] == "rate_zero"]
    two = _rate(60, lambda c: 0.0 if END - timedelta(days=9) <= c <= END - timedelta(days=8) else 5.0)
    z = [a for a in _ev(two, {}, END)["alerts"] if a["family"] == "rate_zero"]
    assert len(z) == 1 and z[0]["severity"] == "watch"


def test_uninstall_a_rate_drift_needs_ten_final_days():
    """Uninstalls +50% (≈ 250 more a day) on 6 settled days: no alert; on 14 settled days: a warning, never resting on
    a provisional day."""
    S_ = END - timedelta(days=eng.LATE_DAYS)
    for n, want in ((6, []), (14, ["up"])):
        a = S_ - timedelta(days=n - 1)
        d = _ev(_rate(90, lambda c: 7.5 if c >= a else 5.0), {}, END)
        dr = [x for x in d["alerts"] if x["family"] == "rate_drift"]
        assert [x["dir"] for x in dr] == want, n
        assert all(not x["provisional"] for x in dr)


def test_uninstall_one_update_is_one_alert():
    """A cohort / rate story that starts inside an open Update impact alert's window (its release R − 3 … R + 10, the
    same direction) is that update's: shown, never sent on its own. And a story back ≤ 14 days after it closed (not by
    a rule change): shown, not resent."""
    R = END - timedelta(days=16)
    imp_ep = {"id": AID + "|impact", "app_id": AID, "family": "impact", "dir": "up",
              "last": {"release": {"key": "b", "label": "v2.0", "date": R.isoformat()}}}
    story = lambda start, dr="up": {"family": "cohort", "dir": dr, "installs_from": start.isoformat()}  # noqa: E731
    assert eng.policy_seed(story(R + timedelta(days=2)), [imp_ep], [], END)
    assert eng.policy_seed(story(R - timedelta(days=3)), [imp_ep], [], END)
    assert not eng.policy_seed(story(R + timedelta(days=11)), [imp_ep], [], END)          # after its window
    assert not eng.policy_seed(story(R + timedelta(days=2), "down"), [imp_ep], [], END)   # the other way
    since = END - timedelta(days=15)
    st = make_store(90, 1000, bump=_bump(70, since))
    seed = {}
    _ev(st, seed, END)                                                  # a real cohort episode (seeded), closed …
    old = [e for e in seed["episodes"].values() if e["family"] == "cohort"][0]
    for ago, reason, notify in ((12, "recovered", False), (12, "rule_tuned", True), (40, "recovered", True)):
        gone = eng.close_ep(dict(old, id="x"), (END - timedelta(days=ago)).isoformat(), None, reason)
        state = {}
        _ev(st, state, END - timedelta(days=40))                         # (the first evaluation: before it)
        state["closed"] = state.get("closed", []) + [gone]
        sent, d = _days(st, END - timedelta(days=12), END, state)
        assert [a for a in d["alerts"] if a["family"] == "cohort"], (ago, reason)
        assert bool([x for x in sent if x[1] == "cohort"]) is notify, (ago, reason)


def test_uninstall_switch_over_closes_old_rule_alerts_never_sends(monkeypatch):
    spike = _rate(60, lambda c: 12.0 if c == END - timedelta(days=2) else 5.0)
    state = {}
    monkeypatch.setattr(eng, "ALERT_POLICY", False)
    _ev(spike, state, END - timedelta(days=30))
    d = _ev(spike, state, END)                                          # the old rules: a (provisional) spike, due
    assert [a["family"] for a in d["alerts"] if a["notify"]] == ["rate_spike"]
    monkeypatch.setattr(eng, "ALERT_POLICY", True)
    d = _ev(spike, state, END, now="2026-09-21T03:00:00Z")              # the first build on the tuned rules
    assert d["alerts"] == [] and state["eval"][AID]["rules"] == eng.RULES_V
    cl = [c for c in d["alerts_closed"] if c["family"] == "rate_spike"]
    assert len(cl) == 1 and cl[0]["close_reason"] == "rule_tuned" and cl[0]["notify"] is False
    assert cl[0]["closed_at"] == "2026-09-21T03:00:00Z"


# ── Install value ────────────────────────────────────────────────────────────────────────────────

def _c(fam, metric, now, before, users, days=14, dr="down", **kw):
    wf = date(2026, 9, 1)
    return dict({"family": fam, "metric": metric, "dir": dr, "now": now, "before": before, "users": users,
                 "week_from": wf.isoformat(), "week_to": (wf + timedelta(days=days - 1)).isoformat()}, **kw)


def test_value_alerts_must_be_material():
    # a country's D7 −6 points on 14 days of 700 installs (50 a day ≈ 3 fewer back a day): no; on 14,000 (60 a day): yes
    assert not V.material(_c("geo_move", "d7", 15.0, 21.0, 700))
    assert V.material(_c("geo_move", "d7", 15.0, 21.0, 14000))
    # earning per install −$0.01 on 1,400 installs (100 a day = $1 a day): no; on 14,000 ($10 a day): yes
    assert not V.material(_c("ver_ret", "rpi7", 0.05, 0.06, 1400))
    assert V.material(_c("ver_ret", "rpi7", 0.05, 0.06, 14000))
    # a country's ads losing $0.02 an install on 140 installs a day ($2.8 a day): no; $0.10 ($14 a day): yes
    assert not V.material(_c("geo_cost", "cost", 0.12, 0.10, 1960, dr="down"))
    assert V.material(_c("geo_cost", "cost", 0.20, 0.10, 1960, dr="down"))
    # good news needs GOOD_X × the floor
    assert not V.material(_c("geo_move", "d7", 24.0, 21.0, 35000, dr="up"))          # 75 back a day: < 100
    assert V.material(_c("geo_move", "d7", 25.0, 21.0, 35000, dr="up"))              # 100 a day
    # the money-back families judge money already: never gated here
    assert V.material({"family": "pay_loss", "metric": "pay", "dir": "down"})


def test_value_switch_over_closes_an_immaterial_open_alert():
    from tests.test_value_engine import AID as VAID, _seen, app, ev
    m = app()
    st = _seen()
    st["eval"].pop("rules", None)
    small = {"id": VAID + "|geo", "app_id": VAID, "family": "geo_move", "metric": "d7", "cc": "NG", "dir": "down",
             "opened": "2026-08-30", "last_true": "2026-08-30", "misses": 0, "notified_at": "2026-08-31T12:00:00Z",
             "notified_dry": False, "seeded": False, "opened_at": "2026-08-31T12:00:00Z",
             "last": dict(_c("geo_move", "d7", 15.0, 21.0, 700), cc="NG", severity="watch", tags=[])}
    st["episodes"][VAID + "|geo_move|NG|down"] = small
    det, row, new_st = ev(m, st=st)
    assert not [a for a in row["_alerts"] if a["family"] == "geo_move" and a["cc"] == "NG"]
    cl = [e for e in new_st["closed"] if e["id"] == VAID + "|geo"]
    assert len(cl) == 1 and cl[0]["close_reason"] == "rule_tuned" and new_st["eval"]["rules"] == V.RULES_V


def test_value_every_closed_alert_is_kept():
    """History is never trimmed: 30 closed alerts, the oldest closed 2 years ago, all stay in the state and all are in
    the app's (lazy) detail file."""
    from tests.test_value_engine import AID as VAID, _seen, app, ev
    st = _seen()
    base = date(2024, 9, 1)
    for k in range(30):
        day = (base + timedelta(days=25 * k)).isoformat()
        st["closed"].append({"id": "%s|value_pay_loss_pay|ALL|down|%s" % (VAID, day), "app_id": VAID,
                             "family": "pay_loss", "metric": "pay", "cc": None, "dir": "down", "opened": day,
                             "last_true": day, "misses": 1, "notified_at": day + "T12:00:00Z", "notified_dry": False,
                             "seeded": False, "opened_at": None, "closed": day, "closed_at": None,
                             "close_reason": "recovered",
                             "last": {"metric": "pay", "severity": "watch", "now": 200, "p": 200, "never": False,
                                      "tags": [], "spend": 50.0, "users": 1000}})
    det, row, new_st = ev(app(), st=st)
    assert len([e for e in new_st["closed"] if e["family"] == "pay_loss"]) >= 30
    assert len([a for a in det["changes"]["closed"] if a["family"] == "pay_loss"]) >= 30
    assert V.CLOSED_KEEP_DAYS is None
