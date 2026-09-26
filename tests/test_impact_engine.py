"""Update impact (admob_iq.engine.impact) — every app update's before / after card, on synthetic GA4 stores whose numbers
add up like GA4's (tests.uninstall_synth.make_impact_store): fair windows (same weekdays, settled days only, the next
update cuts, a hotfix is the same update), the owner's four must-haves (returning DAU vs its expected level, new users
back on day 1 / 7, sessions / time per returning user, ad revenue per user) + uninstall on install day + the same-days
new-vs-old version table, the verdict, persistence, the alerts, the contract — and no false alarms from plain noise."""

import math
import re
import sys
from datetime import date, timedelta

import pytest

from admob_iq.engine import impact as imp
from admob_iq.engine import uninstall as eng
from admob_iq.fetch import ga4_uninstall as gu
from tests.uninstall_synth import END, DEFAULT_RET, check_alert, check_impact, make_impact_store, rollout

R0 = date(2026, 8, 26)                                   # a Wednesday, 24 days before END: final by then


def run(st, rv=None, E=None, state=None, now="2026-09-21T01:00:00Z", aid="a", app="App"):
    """evaluate_app at data end E (default the store's) → (detail, summary row, state); the contract checked."""
    state = {} if state is None else state
    s = dict(st, window_end=(E or END).isoformat())
    d, row = eng.evaluate_app(s, aid, app, state, now, revenue=rv)
    check_impact(d["impact"], d)
    for a in d["alerts"]:
        check_alert(a)
    return d, row, state


def blk(d, day):
    return next(b for b in d["impact"]["updates"] if b["date"] == day.isoformat())


def one(R=R0, v="1.1", speed=0.3, **kw):
    """A 120-day app with ONE update on day R (version v from 1.0)."""
    return make_impact_store(120, versions=rollout("1.0", [(R, v, speed)]), **kw)


def test_the_engine_constants_match_the_fetch_and_the_asset():
    for k in ("IMPACT_V", "COHORT_DAYS", "ACT_LATE_DAYS", "VUSE_MIN_SHARE", "COH_BATCH", "COH_MIN_USERS",
              "COH_MIN_COVERAGE", "COH_EDGE_RUN", "COH_MAX_CALLS"):
        assert getattr(imp, k) == getattr(gu, k), k
    assert imp.CONSTS["dau_min_rel"] == 0.03 and len(imp.CONSTS) == 43 and all(k == k.lower() for k in imp.CONSTS)


# ── 1. windows ───────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("speed, a0, slow", [(0.3, 1, False), (0.2, 2, False), (0.1, 3, True), (0.05, 3, True)])
def test_the_after_window_starts_once_half_the_users_run_it_never_later_than_3_days(speed, a0, slow):
    st, rv = one(speed=speed)
    b = blk(run(st, rv)[0], R0)
    assert R0.weekday() == 2 and b["windows"]["before"] == {"from": "2026-08-19", "to": "2026-08-25"}   # a Wednesday
    w = b["windows"]["after"]
    assert w["from"] == (R0 + timedelta(days=a0)).isoformat() and w["days"] == 7 and w["cut_by"] is None
    assert w["to"] == (R0 + timedelta(days=a0 + 6)).isoformat() and w["settled"] == 7
    assert b["adoption"]["slow"] is slow and ("slow_rollout" in b["notes"]) is slow
    assert b["adoption"]["days"][0] == (R0 - timedelta(days=1)).isoformat() and b["adoption"]["share"][0] == 0.0
    assert b["verdict"]["final"] and b["verdict"]["level"] == "continue" and b["rows"]["returning_dau"]["status"] == "same"


def test_a_hotfix_within_3_days_is_the_same_update_the_next_one_cuts_the_window_and_a_short_cut_is_no_verdict():
    rels = [(R0, "1.1"), (R0 + timedelta(days=2), "1.1.1"), (R0 + timedelta(days=8), "1.2"),
            (R0 + timedelta(days=12), "1.3", 0.2), (R0 + timedelta(days=16), "1.4")]
    st, rv = make_impact_store(120, versions=rollout("1.0", rels))
    d = run(st, rv)[0]
    assert [b["date"] for b in d["impact"]["updates"]] == ["2026-09-11", "2026-09-07", "2026-09-03", "2026-08-26"]
    b = blk(d, R0)                                                  # 1.1 + its hotfix 1.1.1: one update
    assert b["label"] == "v1.1 → v1.1.1" and b["rel_keys"] == ["ver:1.1@2026-08-26", "ver:1.1.1@2026-08-28"]
    assert b["versions"] == ["1.1", "1.1.1"] and b["key"] == "ver:1.1@2026-08-26"
    w = b["windows"]["after"]                                       # 1.2 on 3 Sep cuts its after-week to 6 days
    assert (w["from"], w["to"], w["days"]) == ("2026-08-27", "2026-09-02", 7)
    b2 = blk(d, R0 + timedelta(days=8))
    w2 = b2["windows"]["after"]
    assert (w2["from"], w2["to"], w2["days"]) == ("2026-09-04", "2026-09-06", 3) and w2["cut_by"] == {
        "label": "v1.3", "date": "2026-09-07"}
    assert "cut_by_next" in b2["notes"] and b2["verdict"]["level"] is not None     # 3 days: still judged
    b3 = blk(d, R0 + timedelta(days=12))                            # 1.3 (slower) cut to 2 days by 1.4: no verdict
    assert b3["windows"]["after"]["days"] == 2 and b3["verdict"]["level"] is None
    assert all(r["status"] == "na" and r["reason"] == "Agla update bahut jaldi aa gaya"
               for r in list(b3["rows"].values()) + list(b3["versions_cmp"]["rows"].values()))
    assert b3["verdict"]["why"] == "Agla update bahut jaldi aa gaya"
    b4 = blk(d, R0 + timedelta(days=16))                            # 1.3 on 7 Sep sits in 1.4's week before
    assert b4["windows"]["overlap_before"] == {"key": "ver:1.3@2026-09-07", "label": "v1.3", "date": "2026-09-07"}
    assert "before_overlap" in b4["notes"] and "before_overlap" not in b["notes"]


def test_an_update_right_after_the_launch_has_no_week_before():
    st, rv = make_impact_store(40, versions=rollout("1.0", [(END - timedelta(days=36), "1.1")]))
    d = run(st, rv)[0]
    b = d["impact"]["updates"][0]
    assert all(r["status"] == "na" and r["reason"] == "App launch ke turant baad ka update — pehle ka hafta nahi"
               for r in b["rows"].values()) and b["verdict"]["level"] is None


# ── 2. settled days only ─────────────────────────────────────────────────────────────────────────

def test_after_days_past_the_settled_line_never_change_the_verdict_they_show_faded():
    R = END - timedelta(days=9)                                     # after 11–17 Sep; settled till 16 Sep (E−3)
    st, rv = one(R=R, act=lambda d, v: 0.9 if v == "1.1" else 1.0)
    d = run(st, rv)[0]
    b = blk(d, R)
    assert b["windows"]["after"]["settled"] == 6 and b["windows"]["after"]["settled_till"] == "2026-09-16"
    r = b["rows"]["returning_dau"]
    assert r["to_a"] == "2026-09-16" and r["after_prov"] is not None and "prov" in b["notes"]
    for k in ("2026-09-17", "2026-09-18", "2026-09-19"):             # the newest days crash — not judged
        st["daily"][k]["a1"] //= 2
        st["versions"][k] = {v: u // 2 for v, u in st["versions"][k].items()}
        st["usage"][k]["r"] = [x // 3 for x in st["usage"][k]["r"]]
    r2 = blk(run(st, rv)[0], R)
    for k in ("returning_dau", "sessions", "time", "arpdau"):
        a, c = b["rows"][k], r2["rows"][k]
        assert (a["z"], a["status"], a["after"], a["change"]) == (c["z"], c["status"], c["after"], c["change"]), k
    assert r2["rows"]["returning_dau"]["after_prov"] < r["after_prov"]


# ── 3. cohort rows: day N of a before-install day is before the release ─────────────────────────────

def test_cohort_rows_compare_install_days_whose_day_n_is_on_the_right_side_of_the_release():
    st, rv = one()
    b = blk(run(st, rv)[0], R0)
    d1, d7 = b["rows"]["new_d1"], b["rows"]["new_d7"]
    assert (d1["from_b"], d1["to_b"]) == ("2026-08-18", "2026-08-24")         # [R−8, R−2]: day 1 by R−1
    assert (d7["from_b"], d7["to_b"]) == ("2026-08-12", "2026-08-18")         # [R−14, R−8]: day 7 by R−1
    assert (d1["from_a"], d1["to_a"]) == ("2026-08-27", "2026-09-02") and d1["n_after"] == d1["n_before"] == 7
    assert d1["before"] == round(DEFAULT_RET(1), 5) and d7["before"] == round(int(2000 * DEFAULT_RET(7)) / 2000, 5)


# ── 4. returning DAU ─────────────────────────────────────────────────────────────────────────────

def test_three_times_the_installs_after_the_update_is_expected_not_the_updates_doing():
    a0 = R0 + timedelta(days=1)
    st, rv = one(new=lambda c: 6000 if c >= a0 else 2000, noise=0.005)
    r = blk(run(st, rv)[0], R0)["rows"]["returning_dau"]
    assert r["extra"]["raw_change"] > 0.05 and r["status"] == "same" and abs(r["change"]) < 0.01
    assert r["expected"] > r["before"] and r["extra"]["mode"] == "cohort" and r["extra"]["k_days"] == 30


def test_old_users_six_percent_less_active_is_worse_by_six_percent():
    st, rv = one(new=500, old=40000, act=lambda d, v: 0.94 if d >= R0 + timedelta(days=1) else 1.0)
    b = blk(run(st, rv)[0], R0)
    r = b["rows"]["returning_dau"]
    assert r["status"] == "worse" and abs(r["change"] + 0.06) <= 0.005 and r["z"] < -3
    assert b["verdict"]["level"] == "hold" and b["verdict"]["worse"] == ["returning_dau"]   # under 2× the 3% minimum
    assert b["verdict"]["why"] == "Purane users ka DAU expected se 5.8% kam — pakka"
    st, rv = one(new=500, old=40000, act=lambda d, v: 0.92 if d >= R0 + timedelta(days=1) else 1.0)
    assert blk(run(st, rv)[0], R0)["verdict"]["level"] == "halt"                          # −7.7%: ≥ 2× → HALT


def test_without_return_cohorts_the_dau_compares_week_on_week_with_twice_the_minimum_and_never_says_worse():
    for drop, want in ((0.95, "same"), (0.92, "unsure")):         # −4.8% passes 3% but not the doubled 6%; −7.7%:
        st, rv = one(new=500, old=40000, ret_ok=lambda c: False,   # only "Maybe" — installs can't be told apart
                     act=lambda d, v, x=drop: x if d >= R0 + timedelta(days=1) else 1.0)
        b = blk(run(st, rv)[0], R0)
        r = b["rows"]["returning_dau"]
        assert r["extra"]["mode"] == "raw" and r["extra"]["k_days"] == 0 and "no_cohorts" in b["notes"]
        assert r["status"] == r["raw_status"] == want and r["reason"] == imp.RAW_WHY
        assert b["rows"]["new_d1"]["status"] == "na" and b["rows"]["new_d1"]["reason"] == imp.NA_OLD
    st, rv = one(new=500, old=40000, act=lambda d, v: 0.95 if d >= R0 + timedelta(days=1) else 1.0)
    assert blk(run(st, rv)[0], R0)["rows"]["returning_dau"]["status"] == "worse"   # the same with its cohorts
    a0 = R0 + timedelta(days=1)                                    # 3× the installs, no cohorts: raw DAU +7% — "Maybe"
    st, rv = one(new=lambda c: 6000 if c >= a0 else 2000, ret_ok=lambda c: False)
    r = blk(run(st, rv)[0], R0)["rows"]["returning_dau"]
    assert r["change"] > 0.06 and r["status"] == "unsure"


def test_steady_growth_is_the_normal_trend_not_a_better_dau():
    st, rv = one(old=lambda d: 30000 * 1.01 ** ((d - R0).days / 7), noise=0.003)
    r = blk(run(st, rv)[0], R0)["rows"]["returning_dau"]
    assert r["status"] == "same" and r["extra"]["raw_change"] > 0.005 and abs(r["extra"]["mu_week"] - 0.00995) < 0.003


def test_a_strong_weekend_with_three_settled_days_from_a_friday_is_no_signal():
    fri = date(2026, 9, 11)                                         # Fri 11 Sep: settled Fri, Sat, Sun
    assert fri.weekday() == 4
    R = fri - timedelta(days=1)
    st, rv = one(R=R, speed=0.6, weekend=1.4, noise=0.01)
    b = blk(run(st, rv, E=fri + timedelta(days=2 + imp.ACT_LATE_DAYS))[0], R)
    assert b["windows"]["after"]["from"] == fri.isoformat() and b["windows"]["after"]["settled"] == 3
    for k in ("returning_dau", "sessions", "time", "arpdau"):
        assert b["rows"][k]["status"] in ("same", "unsure"), (k, b["rows"][k])
    assert b["verdict"]["level"] == "continue" and b["verdict"]["early"]


# ── 5. new users back: next day (D1) and after 7 days (D7) ──────────────────────────────────────────

def _rho(after_d1, a0=R0 + timedelta(days=1)):
    return lambda c, k: (after_d1 if k == 1 else DEFAULT_RET(k)) if c >= a0 else (0.30 if k == 1 else DEFAULT_RET(k))


def test_fewer_new_users_back_next_day_is_worse():
    st, rv = one(rho=_rho(0.26))
    b = blk(run(st, rv)[0], R0)
    r = b["rows"]["new_d1"]
    assert (r["before"], r["after"], r["change"], r["status"]) == (0.3, 0.26, -4.0, "worse") and r["z"] < -4
    assert r["extra"]["installs_before"] == r["extra"]["installs_after"] == 14000 and r["extra"]["phi"] == 1.0
    assert b["rows"]["new_d7"]["status"] == "same" and b["verdict"]["level"] == "halt"     # −4 points ≥ 2× 1.5
    assert "installs_swing" not in b["notes"]


def test_with_installs_up_80_percent_a_d1_drop_is_still_shown_but_only_secondary():
    a0 = R0 + timedelta(days=1)
    st, rv = one(rho=_rho(0.26), new=lambda c: 3600 if c >= a0 else 2000)
    b = blk(run(st, rv)[0], R0)
    r = b["rows"]["new_d1"]
    assert r["status"] == "worse" and r["extra"]["swing"] == 0.8 and "installs_swing" in b["notes"]
    assert b["verdict"]["level"] == "continue" and b["verdict"]["worse"] == ["new_d1"]      # campaign mix: one group


def test_d7_waits_for_its_seventh_day_and_says_when():
    R = END - timedelta(days=9)                                     # a0 = 11 Sep; day 7 of the 3rd install day (13 Sep) is
    st, rv = make_impact_store(124, end=date(2026, 9, 23),         # 20 Sep, final once GA4 data reaches 23 Sep
                               versions=rollout("1.0", [(R, "1.1", 0.3)]))
    b = blk(run(st, rv)[0], R)
    d7 = b["rows"]["new_d7"]
    assert d7["status"] == "pending" and d7["ready_on"] == "2026-09-23" and d7["before"] is None
    assert b["rows"]["new_d1"]["status"] == "same" and b["verdict"]["early"] and not b["verdict"]["final"]
    assert "new_d7" in b["verdict"]["pending"] and b["verdict"]["ready_on"] == "2026-09-23"
    assert blk(run(st, rv, E=date(2026, 9, 23))[0], R)["rows"]["new_d7"]["status"] == "same"


def test_cohorts_older_than_what_ga4_still_keeps_say_so():
    st, rv = one(ret_from=R0 - timedelta(days=3))
    b = blk(run(st, rv)[0], R0)
    for k in ("new_d1", "new_d7"):
        assert b["rows"][k]["status"] == "na" and b["rows"][k]["reason"] == "GA4 ab itna purana user data nahi rakhta"
    st, rv = one(ret_ok=lambda c: c > R0)                           # read short (not ok): the same
    assert blk(run(st, rv)[0], R0)["rows"]["new_d1"]["reason"] == "GA4 ab itna purana user data nahi rakhta"
    st["ret"] = {}                                                  # not read yet at all (the backfill is walking back)
    assert blk(run(st, rv)[0], R0)["rows"]["new_d1"]["reason"] == "GA4 se ye data abhi aana baaki hai — agle fetch me"


# ── 6. sessions / time: returning users only ─────────────────────────────────────────────────────

def test_more_new_users_alone_leave_per_user_usage_the_same_a_real_drop_is_worse():
    a0 = R0 + timedelta(days=1)
    st, rv = one(new=lambda c: 8000 if c >= a0 else 2000, spu=lambda d, v, new: 1.0 if new else 2.4)
    b = blk(run(st, rv)[0], R0)
    for k in ("sessions", "time"):
        r = b["rows"][k]
        assert r["status"] == "same" and r["extra"]["all_after"] < r["extra"]["all_before"], k   # all users: diluted
    st, rv = one(tpu=lambda d, v, new: 150.0 if new else (252.0 if v == "1.1" else 280.0),
                 spu=lambda d, v, new: 1.6 if new else (2.16 if v == "1.1" else 2.4))
    b = blk(run(st, rv)[0], R0)
    for k, before in (("sessions", 2.4), ("time", 280.0)):
        r = b["rows"][k]
        assert r["status"] == "worse" and r["before"] == before and -0.1 <= r["change"] < -0.09, (k, r)
    assert b["verdict"]["worse"] == ["sessions", "time"] and b["verdict"]["level"] == "continue"   # one group alone
    assert b["verdict"]["why"] == ("Sessions per user 9% kam aur time per user 9% kam — sirf ek taraf ka pakka "
                                   "nuksaan, baaki theek: rollout chalne do")
    vr = b["versions_cmp"]["rows"]
    assert vr["ver_sessions"]["diff"] == pytest.approx(-0.1, abs=0.002) and vr["ver_sessions"]["status"] == "unsure"


def test_a_trend_the_app_was_already_on_never_makes_or_hides_a_per_user_change():
    # time per returning user falling 3% a week all along: a true update effect of −3% (under the 5% minimum) is not
    # "worse" though after ÷ before reads ≈ −6% (it was: worse, z −5); a true −9% is worse, judged net of the trend
    T0 = END - timedelta(days=119)
    for eff, want in ((0.97, "same"), (0.91, "worse")):
        st, rv = one(speed=0.9, noise=0.004, seed=7,
                     tpu=lambda d, v, n, eff=eff: 150.0 if n else 280.0 * 0.97 ** ((d - T0).days / 7) * (eff if v == "1.1" else 1.0))
        r = blk(run(st, rv)[0], R0)["rows"]["time"]
        assert r["status"] == want and r["change"] < r["extra"]["adj_change"] - 0.02, (eff, r)
        assert r["extra"]["adj_change"] == pytest.approx(eff - 1, abs=0.015), (eff, r)


def test_per_user_rows_are_at_most_maybe_while_recent_installs_reshape_the_returning_users():
    # the same −10% sessions per returning user, once with installs steady (worse) and once with installs ×3 from the
    # release (ad spend): recent installs coming back now make up a much bigger part of the returning users, whose
    # sessions differ from long-time users' — the change may be that mix: Maybe, and the card says installs moved
    spu = lambda d, v, new: 1.6 if new else (2.16 if v == "1.1" else 2.4)
    assert blk(run(*one(spu=spu))[0], R0)["rows"]["sessions"]["status"] == "worse"
    b = blk(run(*one(new=lambda c: 6000 if c > R0 else 2000, spu=spu))[0], R0)
    r = b["rows"]["sessions"]
    assert r["status"] == "unsure" and r["raw_status"] == "unsure" and r["reason"] == imp.MIX_WHY
    assert "installs_swing" in b["notes"] and b["versions_cmp"]["rows"]["ver_sessions"]["status"] not in ("worse", "better")


def test_new_users_back_next_day_that_drift_in_slow_waves_are_the_normal_week_to_week_move():
    # install-day quality in 4-week waves (±12% of the return rate — a campaign mix that lasts for days): the week after
    # an update differs from the week before by up to 5 points with no update effect. Judged with the binomial ×
    # day-to-day swings alone that was worse / better at 6 of 14 phases; the same comparison at pseudo-updates before
    # the release knows these moves
    hs = END - timedelta(days=119)
    for ph in range(0, 28, 2):
        st, rv = one(rho=lambda c, k, ph=ph: DEFAULT_RET(k) * (1 + 0.12 * math.sin(2 * math.pi * ((c - hs).days + ph) / 28)))
        r = blk(run(st, rv)[0], R0)["rows"]["new_d1"]
        assert r["status"] in ("same", "unsure") and r["z"] is not None and abs(r["z"]) < 2, (ph, r["change"], r["z"])


def test_three_earlier_updates_that_agree_by_chance_are_not_proof_of_the_usual_gap():
    days = [END - timedelta(days=i) for i in range(10, 3, -1)]
    cx = {"split": True, "vuse": {"x": {}}}

    def vd(r):
        return {"days": days[:len(r)], "rows": {k: {"r": list(r), "new": 2.4, "old": 2.2} for k in ("sessions", "time")}}

    def rows(k, cur):
        earlier = [{"kind": "version", "_vd": vd([0.10, 0.10, 0.10])} for _ in range(k)]
        blk = {"kind": "version", "label": "v1.9", "versions": ["1.9"], "_vd": vd(cur),
               "win": {"adopt_mean": 0.8, "settled": days, "days_a": days}}
        return imp.ver_rows(cx, blk, earlier)["rows"]["ver_sessions"]
    cur = [0.03, 0.04, 0.02, 0.03, 0.04, 0.03, 0.02]                     # ≈ −6.5% vs the usual gap
    r3, r6 = rows(3, cur), rows(6, cur)
    assert r3["adj"] == pytest.approx(-0.066, abs=0.003) and r3["status"] == "unsure"     # 3 updates: not proof yet
    assert r6["status"] == "worse" and abs(r6["z"]) > abs(r3["z"])                         # 6 that agree: it is


# ── 7. ad revenue per user ───────────────────────────────────────────────────────────────────────

def test_fewer_ads_per_user_is_the_updates_a_lower_ecpm_alone_is_the_market():
    st, rv = one(ipu=lambda d, v: 3.52 if d >= R0 + timedelta(days=1) else 4.0)
    b = blk(run(st, rv)[0], R0)
    r = b["rows"]["arpdau"]
    assert r["status"] == "worse" and abs(r["change"] + 0.12) < 0.005 and r["extra"]["imp_change"] == pytest.approx(-0.12, abs=0.005)
    assert r["extra"]["ecpm_change"] == 0.0 and r["unit"] == "usd1k" and r["before"] == 8.0 and b["verdict"]["level"] == "halt"
    st, rv = one(ecpm=lambda d: 1.76 if d >= R0 + timedelta(days=1) else 2.0)
    b = blk(run(st, rv)[0], R0)
    r = b["rows"]["arpdau"]
    assert r["status"] == "market" and r["reason"].startswith("Sirf eCPM badla") and r["extra"]["ecpm_change"] == -0.12
    assert b["verdict"]["level"] == "continue" and not b["verdict"]["worse"]       # not counted


def test_a_market_ecpm_drop_with_a_small_ads_per_user_dip_is_never_a_halt_and_an_ecpm_rise_never_hides_fewer_ads():
    # the price per ad −15% from the release (a month-end eCPM reset) + ads per user −3% (under the minimum): the
    # revenue drop is shown, but only the ads-per-user part is the update's — no HALT (it was: −18% "worse", HALT)
    st, rv = one(ipu=lambda d, v: 4.0 * (0.967 if v == "1.1" else 1.0), ecpm=lambda d: 2.0 * (0.85 if d > R0 else 1.0),
                 noise=0.01, seed=5)
    b = blk(run(st, rv)[0], R0)
    r = b["rows"]["arpdau"]
    assert r["change"] < -0.15 and r["extra"]["ecpm_change"] == -0.15 and -0.04 < r["extra"]["imp_adj"] < -0.02
    assert r["status"] not in ("worse", "better") and b["verdict"]["level"] == "continue" and "arpdau" not in b["verdict"]["worse"]
    # ads per user −12% hidden under an eCPM +10%: revenue per user only −3%, still the update's loss — worse
    a0 = R0 + timedelta(days=1)
    st, rv = one(ipu=lambda d, v: 4.0 * (0.88 if d >= a0 else 1.0), ecpm=lambda d: 2.0 * (1.10 if d >= a0 else 1.0),
                 noise=0.01, seed=5)
    b = blk(run(st, rv)[0], R0)
    r = b["rows"]["arpdau"]
    assert r["status"] == "worse" and -0.04 < r["change"] < -0.02 and r["extra"]["imp_adj"] == pytest.approx(-0.12, abs=0.01)
    assert b["verdict"]["level"] == "halt"                          # ads per user −12% ≥ 2× the 5% minimum
    assert imp.short_phrase("arpdau", dict(r, _eff=r["extra"]["imp_adj"])).startswith("ads per user −")


def test_admob_days_in_another_timezone_are_spread_over_ga4_days_keeping_every_dollar():
    days = {("2026-09-%02d" % d): ([0, 0] if d in (1, 2, 29, 30) else [d * 1000000, d * 10]) for d in range(1, 31)}
    rv = {"tz": "America/Los_Angeles", "currency": "USD", "till": "2026-09-30", "days": days}
    f, blend = imp._revenue_fn(rv, "Asia/Kolkata")
    assert blend
    got = sum(f(date(2026, 9, d))[0] for d in range(2, 30))
    assert got == pytest.approx(sum(d for d in range(3, 29)), abs=1e-6)
    v = f(date(2026, 9, 10))                                        # IST day = 12.5h of PDT 9 Sep + 11.5h of 10 Sep
    assert v[0] == pytest.approx(9 * 12.5 / 24 + 10 * 11.5 / 24)
    assert f(date(2026, 8, 31)) is None and f(date(2026, 10, 1)) is None     # outside the span / past `till`
    same, blend = imp._revenue_fn(dict(rv, tz="Asia/Kolkata"), "Asia/Kolkata")
    assert not blend and same(date(2026, 9, 10)) == (10.0, 100.0)
    for day in (date(2026, 11, 1), date(2026, 3, 8), date(2026, 9, 10)):   # DST ends (25h) / starts (23h) / a plain day
        sh = imp.revenue_share("Asia/Kolkata", "America/Los_Angeles", day)
        assert sum(sh.values()) == pytest.approx(1.0) and len(sh) == 2


def test_without_admob_revenue_the_row_says_so_and_nothing_else_changes():
    st, rv = one(ipu=lambda d, v: 3.52 if d >= R0 + timedelta(days=1) else 4.0)
    with_rev = blk(run(st, rv)[0], R0)
    b = blk(run(st, None)[0], R0)
    assert b["rows"]["arpdau"]["status"] == "na" and b["rows"]["arpdau"]["reason"] == "AdMob revenue nahi mila"
    assert "no_revenue" in b["notes"] and b["verdict"]["level"] == "continue" and with_rev["verdict"]["level"] == "halt"
    for k in ("returning_dau", "new_d1", "new_d7", "sessions", "time", "uninstall_d0"):
        assert b["rows"][k] == with_rev["rows"][k], k


# ── 8. uninstall on install day ──────────────────────────────────────────────────────────────────

def test_install_day_uninstalls_reuse_the_uninstall_rules_a_rise_may_be_provisional_a_fall_needs_settled_days(monkeypatch):
    calls = []
    real = eng._judge_est

    def spy(*a):
        if sys._getframe(1).f_code.co_name == "d0_row":
            calls.append(a[1])
        return real(*a)
    monkeypatch.setattr(eng, "_judge_est", spy)
    R = END - timedelta(days=9)                                     # after 11–17 Sep; uninstalls settled till 12 Sep
    st, rv = make_impact_store(125, end=END + timedelta(days=5), versions=rollout("1.0", [(R, "1.1", 0.3)]),
                               bump=lambda c: {0: 100} if c > R else None)
    r = blk(run(st, rv)[0], R)["rows"]["uninstall_d0"]
    assert calls and set(calls) == {0}                              # _judge_est at day 0: sample, minimum, estimates
    assert (r["status"], r["before"], r["after"], r["change"]) == ("worse", 0.6, 0.7, 10.0)
    assert r["prov"] and r["extra"]["read"] == "newest"            # a rise already there: real (late data only adds)
    st, rv = make_impact_store(125, end=END + timedelta(days=5), versions=rollout("1.0", [(R, "1.1", 0.3)]),
                               bump=lambda c: {0: -100} if c > R else None)
    r = blk(run(st, rv)[0], R)["rows"]["uninstall_d0"]
    assert r["status"] == "unsure" and r["prov"] and r["change"] == -10.0   # a fall: only once its days are settled
    r = blk(run(st, rv, E=END + timedelta(days=5))[0], R)["rows"]["uninstall_d0"]
    assert r["status"] == "better" and r["extra"]["read"] == "settled" and r["change"] == -10.0


# ── 9. same days: new version vs old versions ────────────────────────────────────────────────────

def _versions_every(n, gap=12, first=END - timedelta(days=70)):
    return [(first + timedelta(days=gap * i), "1.%d" % (i + 1), 0.3) for i in range(n)]


def _early(rels, last_ratio):
    """Users on the newest version (as of the day) use it 10% more — the usual early-updater gap; the LAST
    release's users `last_ratio` instead."""
    def spu(d, v, new):
        cur = [r[1] for r in rels if r[0] <= d]
        if new or not cur or v != cur[-1]:
            return 1.6 if new else 2.4
        return 2.4 * (last_ratio if v == rels[-1][1] else 1.10)
    return spu


@pytest.mark.parametrize("ratio, want, adj", [(1.10, "same", 0.0), (0.95, "worse", -0.136)])
def test_the_new_version_is_compared_net_of_the_usual_early_updater_gap(ratio, want, adj):
    rels = _versions_every(5)
    st, rv = make_impact_store(120, versions=rollout("1.0", rels), spu=_early(rels, ratio))
    d = run(st, rv)[0]
    b = blk(d, rels[-1][0])
    vc, r = b["versions_cmp"], b["versions_cmp"]["rows"]["ver_sessions"]
    assert vc["bias"]["releases"] == 4 and vc["bias"]["sessions"] == pytest.approx(0.10, abs=0.002) and vc["split"]
    assert r["status"] == want and r["adj"] == pytest.approx(adj, abs=0.003) and r["n_days"] == 7
    assert r["diff"] == pytest.approx(ratio - 1, abs=0.003) and b["versions_cmp"]["rows"]["ver_time"]["status"] == "same"
    assert vc["new_label"] == "v1.5" and vc["days"]["n"] == 7


def test_the_version_table_never_says_worse_without_its_usual_gap_or_the_new_returning_split():
    rels = _versions_every(3)
    st, rv = make_impact_store(120, versions=rollout("1.0", rels), spu=_early(rels, 0.8))
    r = blk(run(st, rv)[0], rels[-1][0])["versions_cmp"]["rows"]["ver_sessions"]
    assert r["status"] == "unsure" and r["reason"] == "Pehle ke kam se kam 3 update chahiye — aam farak abhi pata nahi"
    rels = _versions_every(5)
    st, rv = make_impact_store(120, versions=rollout("1.0", rels), spu=_early(rels, 0.8), split=False)
    b = blk(run(st, rv)[0], rels[-1][0])
    assert not b["versions_cmp"]["split"]
    assert b["versions_cmp"]["rows"]["ver_sessions"]["status"] == "unsure"
    assert b["versions_cmp"]["rows"]["ver_sessions"]["reason"].startswith("GA4 is property me naye / purane users alag")


def test_an_app_update_surge_without_a_new_version_has_no_version_table():
    R = END - timedelta(days=24)
    st, rv = make_impact_store(120, upd=lambda d: 5000 if d == R else 300)
    b = blk(run(st, rv)[0], R)
    assert b["kind"] == "update" and b["label"] == "App update" and b["key"] == "upd@%s" % R.isoformat()
    assert b["adoption"]["mean"] is None and b["windows"]["after"]["from"] == (R + timedelta(days=1)).isoformat()
    assert all(r["status"] == "na" and r["reason"] == "Is update ka version number nahi"
               for r in b["versions_cmp"]["rows"].values())
    assert b["rows"]["returning_dau"]["status"] == "same" and b["verdict"]["level"] == "continue"


# ── 10. the verdict ──────────────────────────────────────────────────────────────────────────────

def _verdict(st, ratio=None, swing=(), final=True, settled=7, adopt=0.8):
    """imp.verdict on made-up rows: st {row: status} (the rest "same"), ratio {row: effect ÷ minimum} (default 1.2)."""
    ratio = ratio or {}
    base = date(2026, 9, 1)
    win = {"days_a": [base + timedelta(days=i) for i in range(7)], "adopt_mean": adopt}
    win["settled"] = win["days_a"][:settled]
    rows = {}
    for k in imp.ROWS + imp.VROWS:
        s = st.get(k, "same")
        sign = -1 if s == "worse" else 1
        r = {"status": s, "ready_on": None, "_ratio": ratio.get(k, 1.2), "change": sign * 0.05, "adj": sign * 0.06,
             "before": 0.3, "after": 0.3 + sign * 0.05, "expected": 1000, "extra": {"imp_change": sign * 0.05}}
        if k in swing:
            r["_swing"] = True
        rows[k] = r
    if not final:
        rows["new_d7"]["status"] = "pending"
    vr = {k: rows.pop(k) for k in imp.VROWS}
    return imp.verdict({"win": win}, rows, vr, {"currency": "USD"})


@pytest.mark.parametrize("st, ratio, swing, want", [
    ({"returning_dau": "worse", "arpdau": "worse"}, None, (), "halt"),              # 2 primary worse
    ({"new_d1": "worse"}, {"new_d1": 2.0}, (), "halt"),                              # one at 2× its minimum
    ({"uninstall_d0": "worse", "time": "worse", "new_d7": "worse"}, None, (), "halt"),   # 1 primary + 2 groups
    ({"uninstall_d0": "worse", "time": "worse"}, None, (), "hold"),                  # 1 primary (+ 1 group)
    ({"sessions": "worse", "ver_time": "worse"}, None, (), "hold"),                  # 2 secondary groups
    ({"sessions": "worse", "time": "worse"}, None, (), "continue"),                  # 1 group (usage) alone
    ({"new_d1": "worse"}, {"new_d1": 3.0}, ("new_d1",), "continue"),                 # campaign mix: secondary only
    ({"new_d1": "worse", "time": "worse"}, None, ("new_d1",), "hold"),               # … then 2 groups
    ({"returning_dau": "better"}, None, (), "win"),                                   # final, nothing worse
    ({"sessions": "better", "new_d7": "better"}, None, (), "win"),                    # 2 secondary groups better
    ({"sessions": "better", "time": "better"}, None, (), "continue"),                 # 1 group better: not enough
    ({"returning_dau": "better", "time": "worse"}, None, (), "continue"),             # something worse: never WIN
])
def test_the_verdict_truth_table(st, ratio, swing, want):
    v = _verdict(st, ratio, swing)
    assert v["level"] == want and v["final"] and not v["early"]
    assert v["worse"] == [k for k in imp.ROWS + imp.VROWS if st.get(k) == "worse"]
    if want in ("halt", "hold"):
        assert v["why"].endswith(("— pakka", "— dono pakke", "— sab pakke"))


def test_win_needs_a_final_block_and_enough_adoption_and_under_3_days_there_is_no_verdict():
    assert _verdict({"returning_dau": "better"}, final=False)["level"] == "continue"      # early: no WIN yet
    v = _verdict({"returning_dau": "better", "arpdau": "better"}, adopt=0.2)             # diluted: app-level better
    assert v["level"] == "continue" and "adoption kam" in v["why"]                        # doesn't count
    assert _verdict({"ver_sessions": "better", "returning_dau": "better", "sessions": "better"}, adopt=0.2)[
        "level"] == "continue"                                                            # the version group alone: 1
    assert _verdict({"returning_dau": "worse"}, adopt=0.2)["level"] == "hold"            # bad news counts diluted too
    for n in (0, 1, 2):
        v = _verdict({"returning_dau": "worse", "arpdau": "worse"}, settled=n, final=False)
        assert v["level"] is None and v["why"] == "Abhi %d pakka din — kam se kam 3 chahiye" % n
    assert _verdict({}, settled=3, final=False)["level"] == "continue"


# ── 11. persistence ──────────────────────────────────────────────────────────────────────────────

def test_a_worse_row_counts_on_a_non_final_block_only_the_second_day_hourly_runs_never_advance_it():
    R = date(2026, 9, 8)                                           # a0 9 Sep: 3 settled days at E = 14 Sep
    st, rv = make_impact_store(120, end=date(2026, 9, 19), new=500, old=40000,
                               versions=rollout("1.0", [(R, "1.1", 0.6)]), act=lambda d, v: 0.9 if v == "1.1" else 1.0)
    d, _, state = run(st, rv, E=date(2026, 9, 12))                  # pending: first impact evaluation (seeded)
    assert blk(d, R)["verdict"]["level"] is None
    d, _, state = run(st, rv, E=date(2026, 9, 14), state=state)
    r = blk(d, R)["rows"]["returning_dau"]
    assert (r["raw_status"], r["status"], r["streak"], r["reason"]) == ("worse", "unsure", 1,
                                                                       "pakka hone ke liye kal ka data bhi")
    assert blk(d, R)["verdict"]["level"] == "continue" and not [a for a in d["alerts"] if a["family"] == "impact"]
    d, _, state = run(st, rv, E=date(2026, 9, 14), state=state, now="2026-09-16T05:00:00Z")   # an hourly re-run
    assert blk(d, R)["rows"]["returning_dau"]["streak"] == 1 and blk(d, R)["rows"]["returning_dau"]["status"] == "unsure"
    d, _, state = run(st, rv, E=date(2026, 9, 15), state=state)
    r = blk(d, R)["rows"]["returning_dau"]
    assert (r["status"], r["streak"]) == ("worse", 2) and blk(d, R)["verdict"]["level"] == "halt"
    al = [a for a in d["alerts"] if a["family"] == "impact"]
    assert len(al) == 1 and al[0]["notify"] and al[0]["severity"] == "warning" and al[0]["level"] == "halt"
    assert al[0]["id"] == blk(d, R)["alert_id"]
    # the same data seen for the first time: shown at once, seeded (never sent)
    d, _, _ = run(st, rv, E=date(2026, 9, 14))
    assert blk(d, R)["rows"]["returning_dau"]["status"] == "worse"
    assert [a["notify"] for a in d["alerts"] if a["family"] == "impact"] == [False]


def test_persistence_state_keeps_only_blocks_that_can_still_change():
    rels = [(date(2026, 7, 1), "1.1"), (date(2026, 9, 8), "1.2", 0.6)]
    st, rv = make_impact_store(120, versions=rollout("1.0", rels))
    _, _, state = run(st, rv, E=date(2026, 9, 14))
    assert set(state["eval"]["a"]["impact"]["blocks"]) == {"ver:1.2@2026-09-08"} and state["eval"]["a"]["impact"]["data"]


# ── 12. alerts ───────────────────────────────────────────────────────────────────────────────────

def _c(level, block="ver:1.1@2026-09-01", seed=False, R="2026-09-01"):
    bad = level in ("hold", "halt")
    ver = block.split("@")[0][4:] if block.startswith("ver:") else None
    return {"key": "a|%s|%s" % ("impact" if bad else "impact_win", block.split("@")[0] if ver else block),
            "family": "impact", "vers": [ver] if ver else [], "kind": "version" if ver else "update",
            "dir": "up" if bad else "down", "severity": imp.SEVERITY[level], "level": level, "block": block,
            "text": "x", "now": 1.0, "before": 1.1, "rel": -0.09, "delta_pp": None, "z": -4.0, "installs_from": R,
            "installs_to": R, "base_from": R, "base_to": R, "since": R, "day": None, "users": 1000, "checkpoint": None,
            "n": None, "also": [], "vs": [], "prov": False, "est": False,
            "release": {"key": block, "label": "v1.1", "date": R}, "rows": {"worse": ["time"], "better": []},
            "seed": seed, "R": R}


def test_one_episode_per_update_hold_to_halt_goes_out_once_more_halt_to_hold_never():
    state, E = {}, date(2026, 9, 10)
    eps = imp.update_impact_episodes(state, "a", E, [_c("hold")], True, "t0")
    assert len(eps) == 1 and eps[0]["notified_at"] is None and eps[0]["id"].endswith("|ver:1.1|hold")
    eps[0]["notified_at"] = "sent"                                  # (mark_notified)
    eps = imp.update_impact_episodes(state, "a", E + timedelta(days=1), [_c("hold")], True, "t1")
    assert len(eps) == 1 and eps[0]["notified_at"] == "sent"       # the same HOLD: nothing new
    eps = imp.update_impact_episodes(state, "a", E + timedelta(days=2), [_c("halt")], True, "t2")
    assert eps[0]["notified_at"] is None and eps[0]["id"] == "a|uninstall_impact|ALL|up|2026-09-10|ver:1.1|halt"
    eps[0]["notified_at"] = "sent"
    for i, lvl in ((3, "hold"), (4, "halt")):                       # back down, back up: never re-sent
        eps = imp.update_impact_episodes(state, "a", E + timedelta(days=i), [_c(lvl)], True, "t")
        assert len(eps) == 1 and eps[0]["notified_at"] == "sent" and eps[0]["id"].endswith("|halt")
    win = imp.update_impact_episodes(state, "a", E + timedelta(days=5), [_c("hold"), _c("win", "ver:1.2@2026-09-05")],
                                     True, "t5")
    assert sorted(e["dir"] for e in win) == ["down", "up"]          # a WIN: its own (good) episode
    assert next(e for e in win if e["dir"] == "down")["id"].endswith("|ver:1.2|win")


def test_an_episode_closes_after_three_quiet_days_or_at_once_when_its_update_is_old_and_seeded_ones_are_not_sent():
    state, E = {}, date(2026, 9, 10)
    imp.update_impact_episodes(state, "a", E, [_c("hold", seed=True)], True, "t0")
    assert state["episodes"]["a|impact|ver:1.1"]["notified_at"] == "t0"      # seeded: shown, not sent
    for i in (1, 2):
        assert imp.update_impact_episodes(state, "a", E + timedelta(days=i), [], True, "t")
    assert imp.update_impact_episodes(state, "a", E + timedelta(days=2), [], False, "t")   # hourly: no miss counted
    assert imp.update_impact_episodes(state, "a", E + timedelta(days=3), [], True, "t") == []
    assert [c["closed"] for c in state["closed"]] == ["2026-09-13"]
    state = {}
    imp.update_impact_episodes(state, "a", E, [_c("hold")], True, "t0")
    assert imp.update_impact_episodes(state, "a", date(2026, 10, 7), [], False, "t") == []   # its update now > 35 days old


def test_an_update_that_comes_back_after_its_episode_closed_is_the_same_alert_never_sent_twice():
    state, E, sent = {}, date(2026, 9, 8), []
    for i, lvl in enumerate(["hold", None, None, None, "hold", "hold"]):   # HOLD, 3 quiet days (closed), HOLD again
        for e in imp.update_impact_episodes(state, "a", E + timedelta(days=i), [_c(lvl)] if lvl else [], True, "t"):
            if e["notified_at"] is None:
                sent.append(e["id"])
                e["notified_at"] = "sent"
    assert len(sent) == 1 and not state["closed"] and len(state["episodes"]) == 1   # reopened, not a new one
    # … the first ≥5% day read a day later (late data): the same update, the same alert
    eps = imp.update_impact_episodes(state, "a", E + timedelta(days=6), [_c("hold", block="ver:1.1@2026-09-02",
                                                                            R="2026-09-02")], True, "t")
    assert len(eps) == 1 and eps[0]["id"] == sent[0] and eps[0]["notified_at"] == "sent"
    assert eps[0]["block"] == "ver:1.1@2026-09-02"
    # … a hotfix joined its chain under the first version: still the same; above its peak (HALT): sent once more
    c = _c("halt")
    c["vers"] = ["1.1", "1.1.1"]
    eps = imp.update_impact_episodes(state, "a", E + timedelta(days=7), [c], True, "t")
    assert len(eps) == 1 and eps[0]["notified_at"] is None and eps[0]["vers"] == ["1.1", "1.1.1"]
    # a closed episode of ANOTHER update never swallows a new one
    eps = imp.update_impact_episodes(state, "a", E + timedelta(days=8), [c, _c("hold", block="ver:1.2@2026-09-12",
                                                                               R="2026-09-12")], True, "t")
    assert len(eps) == 2 and len({e["id"] for e in eps}) == 2


def test_updates_older_than_5_weeks_never_alert_and_the_alert_texts_follow_the_templates():
    R = date(2026, 8, 5)                                            # 45 days before END: final, HALT, but info only
    st, rv = one(R=R, new=500, old=40000, act=lambda d, v: 0.9 if v == "1.1" else 1.0)
    d = run(st, rv, state={"eval": {"a": {"end": "2026-09-18", "impact": {"data": True, "blocks": {}}}}})[0]
    assert blk(d, R)["verdict"]["level"] == "halt" and not [a for a in d["alerts"] if a["family"] == "impact"]
    st, rv = one(new=500, old=40000, act=lambda d, v: 0.9 if v == "1.1" else 1.0,
                 tpu=lambda d, v, new: 150.0 if new else (238.0 if v == "1.1" else 280.0))
    d = run(st, rv, state={"eval": {"a": {"end": "2026-09-18", "impact": {"data": True, "blocks": {}}}}}, app="Caller")[0]
    a = next(a for a in d["alerts"] if a["family"] == "impact")
    assert a["notify"] and a["message"] == "Caller: " + a["text"] and a["unit"] == "rel" and a["dir"] == "up"
    assert re.match(r"^v1\.1 \(26 Aug\) ke baad purane users ka DAU \d+\.?\d*% gira \(expected [\d,]+ → [\d,]+/din\) · "
                    r"aur 1 cheez kharab: time per user −\d+% · HALT — staged rollout rok do, hotfix bhejo$", a["text"]), a["text"]
    assert a["release"] == {"key": "ver:1.1@2026-08-26", "label": "v1.1", "date": "2026-08-26"} and a["level"] == "halt"
    assert a["rows"]["worse"][:2] == ["returning_dau", "time"] and a["installs_from"] == "2026-08-27"
    assert (a["base_from"], a["base_to"], a["since"]) == ("2026-08-19", "2026-08-25", "2026-08-26")
    assert a["now"] < a["before"] and a["rel"] < -0.08 and a["delta_pp"] is None and a["users"] > 30000


def test_early_bad_news_says_d7_is_still_to_come():
    R = date(2026, 9, 10)
    st, rv = make_impact_store(120, end=date(2026, 9, 19), new=500, old=40000,
                               versions=rollout("1.0", [(R, "1.1", 0.6)]), act=lambda d, v: 0.9 if v == "1.1" else 1.0)
    d = run(st, rv, state={"eval": {"a": {"end": "2026-09-18", "impact": {"data": True, "blocks": {
        "ver:1.1@2026-09-10": {"rows": {"returning_dau": ["worse", 1]}}}}}}})[0]
    a = next(a for a in d["alerts"] if a["family"] == "impact")
    assert a["text"].endswith("· HALT — staged rollout rok do, hotfix bhejo · shuruaati — D7 abhi baaki")


# ── 13. the contract: every kind of block carries every row ─────────────────────────────────────────

def test_every_kind_of_block_has_exactly_the_seven_rows_the_two_version_rows_and_a_verdict():
    hs = END - timedelta(days=119)
    rels = [(hs + timedelta(days=3), "1.1"), (END - timedelta(days=50), "1.2"), (END - timedelta(days=44), "1.3"),
            (END - timedelta(days=10), "1.4")]
    st, rv = make_impact_store(120, versions=rollout("1.0", rels), upd=lambda d: 6000 if d == END - timedelta(days=30) else 300)
    d, row, _ = run(st, rv)
    kinds = {b["key"]: (b["kind"], b["verdict"]["level"], b["rows"]["returning_dau"]["status"]) for b in d["impact"]["updates"]}
    assert kinds["ver:1.1@%s" % (hs + timedelta(days=3)).isoformat()][2] == "na"            # too young
    assert kinds["upd@%s" % (END - timedelta(days=30)).isoformat()][0] == "update"
    assert [u["key"] for u in row["updates"]] == [b["key"] for b in d["impact"]["updates"]
                                                    if b["date"] >= (END - timedelta(days=60)).isoformat()]
    assert len(d["impact"]["updates"]) == 5                         # check_impact (in run) checked every key of each


# ── 14. noise alone raises no alarm ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ar", [0.0, 0.9])
def test_two_hundred_updates_with_no_real_effect_rarely_show_a_worse_row_and_almost_never_hold(ar):
    # ar 0.9: the noise persists for days, like live returning DAU (a level that drifts; the weekly change of one day and
    # the next correlate ~0.87) — day-level noise ÷ √days read that as |z| ≥ 3 on ~1 date in 4
    import random
    blocks = worse = bad = 0
    for seed in range(20):
        rnd = random.Random(seed)
        noise = 0.03 + 0.02 * rnd.random()
        hs = END - timedelta(days=199)
        rels = [(hs + timedelta(days=50 + 14 * i), "1.%d" % (i + 1), 0.4) for i in range(10)]
        memo = {}

        def rho(c, k, memo=memo, rnd=rnd):
            if c not in memo:
                memo[c] = math.exp(rnd.gauss(0, 0.03))
            return min(0.9, DEFAULT_RET(k) * memo[c])
        st, rv = make_impact_store(200, new=int(1500 + 1000 * rnd.random()), old=int(20000 + 30000 * rnd.random()),
                                   versions=rollout("1.0", rels), noise=noise, seed=seed, rho=rho, weekend=1.1, noise_ar=ar)
        d = run(st, rv)[0]
        for b in d["impact"]["updates"]:
            if b["verdict"]["level"] is None:
                continue
            blocks += 1
            worse += bool(b["verdict"]["worse"])
            bad += b["verdict"]["level"] in ("hold", "halt")
    assert blocks == 200 and worse <= 4 and bad <= 2, (blocks, worse, bad)
