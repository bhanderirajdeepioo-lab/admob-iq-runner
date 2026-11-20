"""GA4_FINAL_DAYS, step 2 — the Uninstall family's activity lag (owner, 17 Nov 2026: "max to max 7 din me to aa hi jaata
he"): fetch.ga4_uninstall.ACT_LATE_DAYS (the maturing cohorts' re-read reach) and IDAY_LATE (the install-day reads, made
once a day is final) are ga4_final.lag(5) − 2 — E is today − 2 from noon, so a day is final at age lag(5): 3 at the
rollback (exactly as before the knob), 5 at 7. engine.impact mirrors ACT_LATE_DAYS (the engine never imports the fetch
module) and every consumer derives from one of the two: engine.active's settled edge S = E − ACT_LATE_DAYS (its detail,
its provisional days, its early look), Update impact's settled after-days and its long windows' judged / final days,
fetch.ga4_audience's E, the install-day reads' F (fetch.ga4_iday_ext reads it as run.F; engine.value's settled day S is
the newest day those reads folded), fetch.ga4_device's F (E − LATE) and fetch.ga4_source_dev's (the property's today −
lag(3): it counts from today, not from E). Each module is re-run at F by the final_days fixture (tests/conftest.py).
Made-up apps and numbers only (tests/uninstall_synth)."""
from datetime import date, datetime, timedelta, timezone

from admob_iq import value_build
from admob_iq.engine import active, impact
from admob_iq.engine import uninstall as eng
from admob_iq.engine import value
from admob_iq.fetch import ga4_audience, ga4_device, ga4_source_dev, ga4_uninstall
from tests.uninstall_synth import END, make_active_store, make_impact_store, rollout

NOW = "2026-09-21T01:00:00Z"
KEY = "0123456789ab"


def _mods(final_days, f):
    """The family at F = f (the pin's own modules at 3), each store before the modules that read it."""
    mods = (ga4_uninstall, impact, active, ga4_audience, ga4_device, ga4_source_dev, value, value_build)
    return final_days.pin(*mods) if f == 3 else final_days(f, *mods)


def test_the_lags_are_lag_5_minus_2_and_every_consumer_takes_them(final_days):
    for f, lag, src in ((3, 3, 3), (7, 5, 7), (14, 12, 14)):
        gu, imp, act, ga, gd, gsd, val, vb = _mods(final_days, f)
        assert gu.ACT_LATE_DAYS == gu.IDAY_LATE == imp.ACT_LATE_DAYS == act.ACT_LATE_DAYS == lag, f
        assert imp.CONSTS["act_late_days"] == act.CONSTS["act_late_days"] == lag
        assert ga.FINAL_LAG_DAYS == gd.LATE == lag and gsd.LATE == src
        assert val.FOLD_AGE == 2 + lag                       # (the Install value words: folded at age 2 + IDAY_LATE)
        final_days.close()


def test_the_audience_e_the_install_day_reads_f_and_the_source_windows_follow(final_days):
    now = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)   # 12:00 UTC: past SETTLE_HOUR, settled end = today − 2
    today = date(2026, 9, 25)
    for f, lag, src in ((3, 3, 3), (7, 5, 7)):
        gu, imp, act, ga, gd, gsd, val, vb = _mods(final_days, f)
        E = gu.settled_end("UTC", now)
        assert E == today - timedelta(days=2)
        assert ga.final_end("UTC", now) == E - timedelta(days=lag)
        run = gu._Iday(None, {"history_start": "2026-01-01"}, {"days": {}}, E, None, now, None, 10, 400)
        assert run.F == E - timedelta(days=lag)              # (fetch.ga4_iday_ext reads run.F)
        w = gsd.windows(today, date(2026, 1, 1))
        assert w["30"] == (today - timedelta(days=src + 29), today - timedelta(days=src))
        assert w["all"][1] == today - timedelta(days=src)
        final_days.close()


def _quiet_crash(day):
    """A big, quiet established app whose old users fall to 30 % on one activity day."""
    return make_active_store(400, noise=0.01, hll=0.01, seed=1, old=lambda d: 20000 * (0.3 if d == day else 1.0))


def test_active_at_7_settles_5_days_before_e_and_a_day_newer_than_that_is_only_an_early_look(final_days):
    """END − 4: settled at the pin (judged, never an early look), provisional at 7 (S = END − 5): the early look says
    it is final in 5 days."""
    st, rv = _quiet_crash(END - timedelta(days=4))
    s = dict(st, window_end=END.isoformat())
    for f, lag in ((3, 3), (7, 5)):
        gu, imp, act, *_ = _mods(final_days, f)
        act.ALERT_POLICY = False                             # (tests/conftest.py's session default)
        udet, _ = eng.evaluate_app(s, "a", "App", {}, NOW, revenue=rv)
        d, row = act.evaluate(s, "a", "App", {}, NOW, udet, KEY, rv, None)
        assert d["act_late_days"] == lag
        assert d["settled_till"] == (END - timedelta(days=lag)).isoformat() == row["settled_till"]
        early = [i for i in d["changes"]["info"] if i["kind"] == "early"]
        if f == 3:
            assert early == []
        else:
            assert [(i["from"], i["prov"]) for i in early] == [((END - timedelta(days=4)).isoformat(), True)]
            assert early[0]["text"].endswith(" — 5 din me pakka hoga")
        final_days.close()


def test_update_impact_at_7_judges_only_days_5_before_e_and_its_long_windows_two_days_later(final_days):
    R = END - timedelta(days=9)                              # an update whose 7 after-days run past E − 3
    st, rv = make_impact_store(120, versions=rollout("1.0", [(R, "1.1", 0.6)]))
    s = dict(st, window_end=END.isoformat())
    for f, lag in ((3, 3), (7, 5)):
        gu, imp, act, *_ = _mods(final_days, f)
        d, _ = eng.evaluate_app(s, "a", "App", {}, NOW, revenue=rv)      # (its lazy impact import: the copy at f)
        a = next(u for u in d["impact"]["updates"] if u["date"] == R.isoformat())["windows"]["after"]
        assert a["to"] > (END - timedelta(days=lag)).isoformat()            # (the window reaches past the edge)
        assert a["settled_till"] == (END - timedelta(days=lag)).isoformat()
        assert a["settled"] == (END - timedelta(days=lag) - date.fromisoformat(a["from"])).days + 1
        win = {"end_a": R + timedelta(days=7)}
        assert imp._state(win, 14, END)[1] == win["end_a"] + timedelta(days=lag + imp.JUDGE_D)
        assert imp._state(win, 30, END)[2] == win["end_a"] + timedelta(days=30 + lag)
        final_days.close()


def test_value_build_writes_the_install_day_lag_only_off_the_rollback(final_days):
    cfg = {"payback_days": 90, "iap": False, "cpi": "ads", "deduct": False, "geo": False}
    for f, want in ((3, None), (7, 5)):
        *_, val, vb = _mods(final_days, f)
        c = vb.consts(cfg)
        assert c.get("iday_late") == want and ("iday_late" in c) == (want is not None)
        assert {k: v for k, v in c.items() if k != "iday_late"} == dict(val.CONSTS, horizon=90, iap_in_payback=False,
                                                                         cpi_main="ads", deduct=False, geo=False)
        final_days.close()


# ── the review's follow-ups (P2-2 … P2-5): what else moves with the lag ─────────────────────────────────────────────

def test_the_install_day_late_check_still_runs_at_every_f(final_days):
    """_Iday.late (step 3, measured only): day F − IDAY_CHECK_AGE is read again when its kept read was fresh — made at
    age 2 + IDAY_LATE (on time) or up to 2 fetch-days later, by IDAY_FRESH_AGE (7 at the rollback: exactly as before
    the knob, 9 at 7, 16 at 14) — and not when it was older (backfilled)."""
    class GA:
        quota = None

    E = date(2026, 9, 23)
    for f, fresh in ((3, 7), (7, 9), (14, 16)):
        gu = final_days.pin(ga4_uninstall) if f == 3 else final_days(f, ga4_uninstall)
        assert gu.IDAY_FRESH_AGE == fresh == 2 + gu.IDAY_LATE + 2 and gu.IDAY_CHECK_AGE == 7, f
        d = E - timedelta(days=gu.IDAY_LATE + gu.IDAY_CHECK_AGE)
        for extra, want in ((0, True), (1, True), (2, True), (3, False)):
            at = (d + timedelta(days=2 + gu.IDAY_LATE + extra)).isoformat() + "T13:00:00Z"
            ida = {"born": (E - timedelta(days=3)).isoformat(), "flags": {},
                   "days": {d.isoformat(): {"st": "ok", "at": at, "chk": None, "cst": "none"}}}
            run = gu._Iday(GA(), {"history_start": "2026-01-01"}, ida, E, None,
                           (E + timedelta(days=2)).isoformat() + "T13:00:00Z", None, 10, 400)
            asked = []
            run.ask = lambda fn, *a: asked.append(a) or None
            run.late()
            assert bool(asked) is want, (f, extra)
        final_days.close()


def test_the_cohort_repair_never_re_asks_a_maturing_cohort_at_7(final_days, monkeypatch):
    """fetch_ret at 7: (a) the maturing cohorts [E − 36, E] (COHORT_DAYS + ACT_LATE_DAYS + 1), (b) the repair up to
    E − 37 — the day before (a)'s window, never inside it: a cohort GA4 rejects (HTTP 400, nothing stored) in (a) is
    asked once in a fetch, not again by the repair (the old top E − 35 overlapped (a) at 7)."""
    gu = final_days(7, ga4_uninstall)
    E = date(2026, 9, 23)
    bad = E - timedelta(days=36)
    asked = []

    def rep_ret(ga, days):
        asked.append(list(days))
        if bad in days:
            raise RuntimeError("HTTP 400: cohort spec rejected")
        return []

    class GA:
        quota, last_meta = None, {}

        def truncated(self, rows):
            return False

    monkeypatch.setattr(gu, "rep_ret", rep_ret)
    hs = E - timedelta(days=120)
    daily = {(hs + timedelta(days=i)).isoformat(): {"new": 1000} for i in range(121)}
    st = {"history_start": hs.isoformat(), "ret_from": hs.isoformat(), "daily": daily, "ret": {}}
    gu.fetch_ret(GA(), st, E)
    days = [d for b in asked for d in b]
    assert min(d for b in asked[:3] for d in b) == E - timedelta(days=gu.COHORT_DAYS + gu.ACT_LATE_DAYS + 1) == bad
    assert [b for b in asked if b == [bad]] == [[bad]]               # the rejected one: asked alone once, (a) only
    rep = asked[-1]                                                   # (b): the newest never-read days before (a)
    assert max(rep) == E - timedelta(days=37) and len(rep) == gu.COH_BATCH and min(days) == E - timedelta(days=50)
    assert all(bad not in b for b in asked[asked.index([bad]) + 1:])  # (its batch halved in (a) only)
    final_days.close()


def test_a_late_effect_keeps_its_days_to_be_sent_at_every_f(final_days):
    """impact.LATE_ALERT_DAYS (older updates never raise a late alert) = 72 + ACT_LATE_DAYS: the 30-day window of an
    update rolled out 3 days after its release is final with D30 at end_a + 30 + ACT_LATE_DAYS, its late condition is
    sent LATE_PERSIST evaluations later — 9 days inside the limit at every F (75 at the rollback, as before the knob)."""
    R = date(2026, 1, 1)
    for f, cap in ((3, 75), (7, 77), (14, 84)):
        imp = final_days.pin(impact) if f == 3 else final_days(f, impact)
        assert imp.LATE_ALERT_DAYS == cap and imp.CONSTS["late_alert_days"] == cap, f
        a0 = R + timedelta(days=3)
        win = {"end_a": a0 + timedelta(days=imp.LATE_WINDOW - 1)}
        _, _, final_on = imp._state(win, imp.LATE_WINDOW, R)
        sent = final_on + timedelta(days=imp.LATE_PERSIST - 1)
        assert (R + timedelta(days=imp.LATE_ALERT_DAYS) - sent).days == 9, f
        final_days.close()


def test_impact_any_reuses_a_file_only_at_the_same_activity_lag(final_days):
    """engine.impact_any.input_sig names impact.ACT_LATE_DAYS off its rollback 3: a GA4_FINAL_DAYS flip without a code
    change rebuilds every app's file; at the pin the key is the one before the knob (the same five inputs, nothing
    added)."""
    import hashlib
    import json
    from admob_iq.engine import impact_any
    E = date(2026, 9, 23)
    rv = {"tz": "UTC", "currency": "USD", "days": {"2026-09-20": 1.5}}
    sig = {}
    for f in (3, 7):
        imp, ia = final_days.pin(impact, impact_any) if f == 3 else final_days(f, impact, impact_any)
        assert ia.I is imp
        sig[f] = ia.input_sig("s", rv, E, 7, "c", "UTC")
        if f == 3:
            r = [ia.rev_reach(E, "UTC", "UTC").isoformat()]
            raw = json.dumps(["s", ["UTC", "USD", min("2026-09-20", r[0]), "2026-09-20", [["2026-09-20", 1.5]]],
                              E.isoformat(), 7, "c"], separators=(",", ":"), sort_keys=True, default=str)
            assert sig[3] == hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]        # (the key before the knob)
        final_days.close()
    assert sig[3] != sig[7]
