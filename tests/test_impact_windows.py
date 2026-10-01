"""Update impact — the 7 / 14 / 30 / 60-day windows (spec SPEC_WINDOWS): the 7-day block exactly as before, the long
windows (same-weekday pairing, never cut by the next update, "Mixed", the trend rules, the window's own pseudo-update
noise, the running / judged / final states, D30), the late-effect family "impact_late" (told rows, persistence, one
per app, seeding) and its glue — on synthetic stores only (tests.uninstall_synth.make_impact_store)."""

import copy
import math
import random
import re
from datetime import date, timedelta

import pytest

from admob_iq.engine import impact as imp
from admob_iq.engine import uninstall as eng
from tests.uninstall_synth import (END, DEFAULT_RET, IMPACT_TREND, check_alert, check_impact, check_updates, make_impact_store,
                                   rollout)

NOW = "2026-09-21T01:00:00Z"


def run(st, rv=None, E=None, state=None, now=NOW, aid="a", app="App", windows=True, outdated=False):
    state = {} if state is None else state
    s = dict(st, window_end=(E or END).isoformat())
    d, row = eng.evaluate_app(s, aid, app, state, now, revenue=rv, windows=windows, outdated=outdated)
    check_impact(d["impact"], d)
    for a in d["alerts"]:
        check_alert(a)
    return d, row, state


def _basis(k, r):
    """A 14 / 30 / 60-day row's basis (left out when it is the window's default for the row: filled back as the page does)."""
    return r.get("basis", imp.BASIS_LONG[imp.UNIT[k]])


def blk(d, day):
    return next(b for b in d["impact"]["updates"] if b["date"] == day.isoformat())


def strip7(detail):
    """The v1 card: the 7-day block without the §2.8 additions (basis / noise / need, sessions / time expected, the
    arpdau imp_* extras) and without the windows' own keys."""
    imp_ = copy.deepcopy(detail["impact"])
    imp_["v"] = 1
    for b in imp_["updates"]:
        for k in ("by_window", "default_window", "late"):
            b.pop(k, None)
        for k, r in b["rows"].items():
            for f in ("basis", "noise", "need"):
                r.pop(f)
            if k in ("sessions", "time"):
                r["expected"] = None
            if k == "arpdau":
                for f in ("imp_before", "imp_after", "imp_expected"):
                    r["extra"].pop(f)
    return imp_


# the stores the 7-day tests use (tests/test_impact_engine.py), a few of each kind
R0 = date(2026, 8, 26)


def _stores():
    rels = [(R0, "1.1"), (R0 + timedelta(days=2), "1.1.1"), (R0 + timedelta(days=8), "1.2"),
            (R0 + timedelta(days=12), "1.3", 0.2), (R0 + timedelta(days=16), "1.4")]
    yield make_impact_store(120, versions=rollout("1.0", [(R0, "1.1", 0.3)]))
    yield make_impact_store(120, versions=rollout("1.0", rels))
    yield make_impact_store(120, versions=rollout("1.0", [(R0, "1.1", 0.3)]), act=lambda d, v: 0.9 if v == "1.1" else 1.0,
                            tpu=lambda d, v, new: 150.0 if new else (238.0 if v == "1.1" else 280.0), new=500, old=40000)
    yield make_impact_store(120, versions=rollout("1.0", [(R0, "1.1", 0.3)]),
                            ipu=lambda d, v: 3.52 if d >= R0 + timedelta(days=1) else 4.0)
    yield make_impact_store(120, versions=rollout("1.0", [(R0, "1.1", 0.3)]),
                            rho=lambda c, k: (0.26 if k == 1 else DEFAULT_RET(k)) if c > R0 else DEFAULT_RET(k))
    hs = END - timedelta(days=199)
    yield make_impact_store(200, versions=rollout("1.0", [(hs + timedelta(days=50 + 14 * i), "1.%d" % (i + 1), 0.4)
                                                           for i in range(10)]), noise=0.04, seed=3, noise_ar=0.9)
    yield make_impact_store(400, versions=rollout("1.0", [(END - timedelta(days=d), "2.%d" % i, 0.5)
                                                           for i, d in enumerate((200, 130, 90, 60, 42, 32, 12))]),
                            noise=0.03, seed=5, ipu=lambda d, v: 3.4 if d >= END - timedelta(days=24) else 4.0)


# ── E1. the 7-day block is exactly as before ────────────────────────────────────────────────────

@pytest.mark.parametrize("i", range(7))
def test_the_7_day_block_its_alerts_and_their_texts_are_unchanged_after_the_long_windows_ran(i):
    st, rv = list(_stores())[i]
    for E in (END - timedelta(days=4), END):
        on, row_on, st_on = run(st, rv, E=E, windows=True)
        off, row_off, st_off = run(st, rv, E=E, windows=False)
        assert on["impact"]["v"] == 2 and off["impact"]["v"] == 1
        assert strip7(on) == strip7(off)                            # (windows() is pure at 14+: compared AFTER them)
        assert all(r["noise"] is None and r["need"] is None for b in off["impact"]["updates"] for r in b["rows"].values())
        seven = [a for a in on["alerts"] if a["family"] != "impact_late"]
        assert seven == off["alerts"]                               # the 7-day alerts, ids and texts byte-identical
        assert [dict(u, late=None) for u in row_on["updates"]] == [dict(u, late=None) for u in row_off["updates"]]
        ev_on, ev_off = st_on["eval"]["a"]["impact"], st_off["eval"]["a"]["impact"]
        assert ev_on["blocks"] == ev_off["blocks"] and ev_on["late_v"] == 1 and "late_v" not in ev_off


def test_a_7_day_row_keeps_its_z_and_says_its_noise_and_what_pakka_needs():
    st, rv = make_impact_store(120, versions=rollout("1.0", [(R0, "1.1", 0.3)]),
                               ipu=lambda d, v: 3.52 if d >= R0 + timedelta(days=1) else 4.0, noise=0.02, seed=4)
    b = blk(run(st, rv)[0], R0)
    for k, r in b["rows"].items():
        assert r["basis"] == {"new_d1": "rate", "new_d7": "rate", "uninstall_d0": "rate"}.get(k, "expected"), k
    a = b["rows"]["arpdau"]
    assert a["status"] == "worse" and a["noise"] > 0 and a["need"] < 0 and a["need"] <= -imp.ARPDAU_MIN_REL
    assert a["extra"]["imp_expected"] == pytest.approx(a["extra"]["imp_after"] / (1 + a["extra"]["imp_adj"]), rel=1e-3)
    s = b["rows"]["sessions"]
    assert s["expected"] == pytest.approx(s["after"] / (1 + s["extra"]["adj_change"]), abs=0.002)
    d0 = b["rows"]["uninstall_d0"]
    assert d0["noise"] > 0 and d0["need"] and (not d0["z"] or abs(abs(d0["change"] / d0["z"]) - d0["noise"]) < 0.05)


# ── 2. pairing ──────────────────────────────────────────────────────────────────────────────────

def test_pair_day_is_the_7_day_bday_and_keeps_the_weekday_inside_the_before_window_at_every_length():
    for wd in range(7):
        R = date(2026, 8, 3) + timedelta(days=wd)
        for off in (1, 2, 3):
            a0 = R + timedelta(days=off)
            win = {"n": 7, "a0": a0}
            for d in imp._days(a0, a0 + timedelta(days=6)):
                assert imp.pair_day(win, R, d) == imp._bday(R, d)
            for N, lags in ((14, {2, 3}), (30, {4, 5}), (60, {8, 9})):
                win = {"n": N, "a0": a0}
                got = set()
                for d in imp._days(a0, a0 + timedelta(days=N - 1)):
                    b, w = imp.pair_day(win, R, d)
                    assert b.weekday() == d.weekday() and R - timedelta(days=N) <= b <= R - timedelta(days=1)
                    assert w == (d - b).days // 7 and (d - b).days % 7 == 0
                    got.add(w)
                assert got <= lags, (N, got)


# ── 3. windows ──────────────────────────────────────────────────────────────────────────────────

def test_long_windows_are_never_cut_list_the_updates_inside_and_keep_the_7_day_one_as_it_was():
    E = END
    rels = [(E - timedelta(days=150), "1.1", 0.6), (E - timedelta(days=100), "1.2", 0.6), (E - timedelta(days=80), "1.3", 0.6),
            (E - timedelta(days=75), "1.4", 0.6), (E - timedelta(days=60), "1.5", 0.6)]
    st, rv = make_impact_store(300, versions=rollout("1.0", rels))
    d, _, _ = run(st, rv)
    b = blk(d, E - timedelta(days=80))                               # 1.3: 1.4 five days later cuts its 7 days
    assert b["windows"]["after"]["cut_by"] == {"label": "v1.4", "date": (E - timedelta(days=75)).isoformat()}
    R = E - timedelta(days=80)
    for N in (14, 30, 60):
        W = b["by_window"][str(N)]
        a0 = date.fromisoformat(W["after"]["from"])
        assert W["before"] == {"from": (R - timedelta(days=N)).isoformat(), "to": (R - timedelta(days=1)).isoformat(),
                               "days": N}
        assert W["after"]["to"] == (a0 + timedelta(days=N - 1)).isoformat() and W["after"]["days"] == N
        assert a0 == date.fromisoformat(b["windows"]["after"]["from"])        # the same a0 (the ≥50% rule)
    assert [m["label"] for m in b["by_window"]["14"]["mixed"]] == ["v1.4"]
    assert [m["label"] for m in b["by_window"]["30"]["mixed"]] == ["v1.4", "v1.5"]         # oldest first
    assert [m["label"] for m in b["by_window"]["60"]["mixed"]] == ["v1.4", "v1.5"]
    assert [m["label"] for m in b["by_window"]["14"]["mixed_before"]] == []
    assert [m["label"] for m in b["by_window"]["30"]["mixed_before"]] == ["v1.2"]
    assert [m["label"] for m in b["by_window"]["60"]["mixed_before"]] == ["v1.2"]
    assert "mixed" in b["by_window"]["30"]["notes"] and "mixed_before" in b["by_window"]["30"]["notes"]
    W = b["by_window"]["30"]
    if W["verdict"]["level"] is not None:
        assert W["verdict"]["why"].endswith(" · mila-jula (beech me 2 aur updates)") and W["verdict"]["mixed"]


def test_the_60_day_adoption_is_this_update_or_newer_over_days_past_r_plus_21_and_the_7_day_one_is_unchanged():
    E = END
    R, R2 = E - timedelta(days=90), E - timedelta(days=70)
    st, rv = make_impact_store(300, versions=rollout("1.0", [(R, "2.0", 0.2, 0.9), (R2, "2.1", 0.3)]))
    on, _, _ = run(st, rv)
    off, _, _ = run(st, rv, windows=False)
    b = blk(on, R)
    assert b["adoption"] == blk(off, R)["adoption"]                  # the 7-day adoption output: days R−1..R+21
    assert b["adoption"]["days"][-1] == (R + timedelta(days=21)).isoformat()
    # 2.1 takes users from 2.0 after R2: "2.0 only" would fall — "this update or newer" stays ~0.97
    assert b["by_window"]["60"]["adoption_mean"] > 0.85 and b["by_window"]["60"]["adoption_mean"] > b["adoption"]["mean"]


# ── 4 / 5. the late effect: an untold drop, a told one ─────────────────────────────────────────────

def late_store(drop_from, drop=0.85, extra=(), seed=3, **kw):
    """400 days, v1.9 at E−100, v2.0 at E−42 and v2.1 at E−32 (instant adoption: a0 = R+1), ads per user × `drop` from
    `drop_from`."""
    E = END
    rels = [(E - timedelta(days=100), "1.9", 1.0), (E - timedelta(days=42), "2.0", 1.0),
            (E - timedelta(days=32), "2.1", 1.0)] + list(extra)
    return make_impact_store(400, versions=rollout("1.0", rels), noise=0.02, seed=seed,
                             ipu=lambda d, v: 4.0 * (drop if drop_from is not None and d >= drop_from else 1.0), **kw)


def test_a_late_ads_drop_is_judged_at_30_days_and_sent_as_one_late_alert_on_the_second_daily_evaluation():
    E = END
    R = E - timedelta(days=42)
    st, rv = late_store(E - timedelta(days=24))
    state, sent = {}, []
    for off in (3, 2, 1, 0):
        d, row, state = run(st, rv, E=E - timedelta(days=off), state=state)
        b = blk(d, R)
        assert b["verdict"]["level"] == "continue" and blk(d, E - timedelta(days=32))["verdict"]["level"] == "continue"
        W = b["by_window"]["30"]
        late = [a for a in d["alerts"] if a["family"] == "impact_late"]
        if off == 3:                                                  # end_a = E−12: judged on E−2
            assert W["state"] == "running" and W["verdict"]["level"] is None and not late
            assert W["verdict"]["why"] == "30 din poore ~7 Sep ko · faisla ~19 Sep ko"
            continue
        assert W["state"] == "judged" and W["verdict"]["early"] and not W["verdict"]["final"]
        assert W["rows"]["new_d30"]["status"] == "pending" and W["rows"]["new_d30"]["ready_on"] == W["after"]["final_on"]
        a = W["rows"]["arpdau"]
        assert a["status"] == "worse" and _basis("arpdau", a) == "plain" and "expected" not in a and a["extra"]["imp_adj"] < -0.05
        assert W["verdict"]["level"] == "hold" and W["verdict"]["late"] == "hold" and W["verdict"]["told"] == []
        assert b["late"]["level"] == "hold"
        if off == 2:                                                  # the first judged evaluation: held once
            assert not late and state["eval"]["a"]["impact"]["late"] == {"block": b["key"], "level": "hold", "streak": 1}
            continue
        assert len(late) == 1
        al = late[0]
        if off == 1:
            assert al["notify"] and b["default_window"] == 30 and b["late"]["alert_id"] == al["id"]
            sent.append(al["id"])
            eng_ep = state["episodes"]["a|impact_late"]
            eng_ep["notified_at"] = "sent"                            # (mark_notified)
        else:
            assert not al["notify"] and al["id"] == sent[0]           # the same episode: never twice
        assert "ke 30 din baad" in al["text"] and "pehle 7 din me ye nahi dikha tha" in al["text"]
        assert "beech me 1 aur update (v2.1) — asar mila-jula ho sakta hai" in al["text"]
        assert al["text"].endswith("⚠️ Wait and check — agla rollout roko, jaanch karo · 30 din ka result abhi baaki")
        assert al["release"]["key"] == b["key"] and al["rows"] == {"worse": ["arpdau"], "told": []}
        assert al["mixed"] == ["v2.1"] and al["window"] == 30 and al["severity"] == "watch"
        assert (al["installs_from"], al["installs_to"]) == (W["after"]["from"], W["after"]["to"])
        assert (al["base_from"], al["base_to"]) == (W["before"]["from"], W["before"]["to"])
        u = next(u for u in row["updates"] if u["key"] == b["key"])
        assert u["late"] == {"level": "hold", "alert_id": al["id"]} and u["level"] == "continue"
        assert b["alert_id"] is None                                  # the 7-day alert id: none (CONTINUE)


def test_a_7_day_hold_that_lasts_to_30_days_is_told_and_never_raises_a_late_alert():
    E = END
    R = E - timedelta(days=42)
    st, rv = late_store(R + timedelta(days=1), drop=0.91)               # from v2.0's first after-day, lasting
    d, _, state = run(st, rv, E=E)
    b = blk(d, R)
    assert b["verdict"]["level"] == "hold" and "arpdau" in b["verdict"]["worse"]
    W = b["by_window"]["30"]["verdict"]
    assert W["level"] == "hold" and W["told"] == ["arpdau"] and W["late"] is None and "told_by" not in W
    assert b["late"] is None and not [a for a in d["alerts"] if a["family"] == "impact_late"]
    assert "late" not in state["eval"]["a"]["impact"]


def test_a_drop_an_update_inside_the_window_already_told_is_never_re_sent_under_the_older_update():
    E = END
    R1, R2 = E - timedelta(days=42), E - timedelta(days=32)
    st, rv = late_store(R2 + timedelta(days=1), drop=0.91)              # starts with v2.1 (inside v2.0's 30 days)
    d, _, _ = run(st, rv, E=E)
    assert blk(d, R2)["verdict"]["level"] in ("hold", "halt") and blk(d, R1)["verdict"]["level"] == "continue"
    W = blk(d, R1)["by_window"]["30"]["verdict"]
    assert W["level"] == "hold" and W["told"] == ["arpdau"] and W["told_by"] == {"arpdau": "v2.1"} and W["late"] is None
    assert not [a for a in d["alerts"] if a["family"] == "impact_late"]


def test_a_7_day_episode_of_the_same_update_tells_its_rows_even_once_closed():
    E = END
    R = E - timedelta(days=42)
    st, rv = late_store(E - timedelta(days=24))
    ep = {"id": "a|uninstall_impact|ALL|up|2026-08-20|ver:2.0|hold", "app_id": "a", "family": "impact", "dir": "up",
          "vers": ["2.0"], "kind": "version", "opened": "2026-08-20", "last_true": "2026-08-27", "misses": 3,
          "notified_at": "sent", "notified_dry": False, "seeded": False, "block": "ver:2.0@%s" % R.isoformat(),
          "peak": "hold", "closed": "2026-08-30",
          "last": {"R": R.isoformat(), "since": R.isoformat(), "severity": "watch", "level": "hold", "text": "x",
                   "release": {"key": "ver:2.0@%s" % R.isoformat(), "label": "v2.0", "date": R.isoformat()},
                   "rows": {"worse": ["arpdau"], "better": []}, "now": 1.0, "before": 1.1, "rel": -0.1, "users": 10,
                   "installs_from": R.isoformat(), "installs_to": R.isoformat(), "base_from": R.isoformat(),
                   "base_to": R.isoformat()}}
    d, _, _ = run(st, rv, E=E, state={"closed": [ep]})
    W = blk(d, R)["by_window"]["30"]["verdict"]
    assert W["level"] == "hold" and W["told"] == ["arpdau"] and W["late"] is None


# ── 6 / 7. escalation, one episode per app ─────────────────────────────────────────────────────

def _lc(level, block="ver:2.0@2026-08-08", seed=False, worse=("arpdau",), R="2026-08-08"):
    ver = block.split("@")[0][4:]
    return {"key": "a|impact_late", "family": "impact_late", "dir": "up", "vers": [ver], "kind": "version",
            "severity": imp.SEVERITY[level], "level": level, "block": block, "text": "x", "now": 1.0, "before": 1.1,
            "rel": -0.09, "delta_pp": None, "z": -4.0, "installs_from": R, "installs_to": R, "base_from": R,
            "base_to": R, "since": R, "day": None, "users": 1000, "checkpoint": None, "n": None, "also": [], "vs": [],
            "prov": False, "est": False, "release": {"key": block, "label": "v" + ver, "date": R},
            "rows": {"worse": list(worse), "told": []}, "mixed": [], "window": 30, "seed": seed, "R": R}


def test_a_late_hold_that_turns_halt_goes_out_once_more_halt_to_hold_and_a_new_secondary_row_never():
    state, E = {}, date(2026, 9, 18)
    eps = imp.update_late_episodes(state, "a", E, _lc("hold"), True, "t0")
    assert len(eps) == 1 and eps[0]["notified_at"] is None and eps[0]["id"] == "a|uninstall_impact_late|ALL|up|2026-09-18|ver:2.0|hold"
    eps[0]["notified_at"] = "sent"
    eps = imp.update_late_episodes(state, "a", E + timedelta(days=1), _lc("hold", worse=("arpdau", "new_d30")), True, "t")
    assert eps[0]["notified_at"] == "sent"                           # a new secondary row: nothing new
    eps = imp.update_late_episodes(state, "a", E + timedelta(days=2), _lc("halt", worse=("arpdau", "new_d1")), True, "t")
    assert eps[0]["notified_at"] is None and eps[0]["id"].endswith("|2026-09-18|ver:2.0|halt")
    eps[0]["notified_at"] = "sent"
    for i, lvl in ((3, "hold"), (4, "halt")):
        eps = imp.update_late_episodes(state, "a", E + timedelta(days=i), _lc(lvl), True, "t")
        assert len(eps) == 1 and eps[0]["notified_at"] == "sent"


def test_a_7_day_episode_and_a_late_one_of_the_same_update_live_side_by_side():
    state, E = {}, date(2026, 9, 18)
    c7 = dict(_lc("hold"), key="a|impact|ver:2.0", family="impact", rows={"worse": ["time"], "better": []})
    imp.update_impact_episodes(state, "a", E, [c7], True, "t0")
    imp.update_late_episodes(state, "a", E, _lc("hold"), True, "t0")
    for i in (1, 2, 3):                                              # the 7-day condition gone: only it closes
        e7 = imp.update_impact_episodes(state, "a", E + timedelta(days=i), [], True, "t")
        el = imp.update_late_episodes(state, "a", E + timedelta(days=i), _lc("hold"), True, "t")
        assert len(el) == 1 and el[0]["family"] == "impact_late"
    assert e7 == [] and [c["family"] for c in state["closed"]] == ["impact"]
    imp.update_impact_episodes(state, "a", E + timedelta(days=4), [c7], True, "t")   # back: its own closed one
    assert {e["family"] for e in state["episodes"].values()} == {"impact", "impact_late"} and not state["closed"]
    for i in (5, 6, 7):
        el = imp.update_late_episodes(state, "a", E + timedelta(days=i), None, True, "t")
    assert el == [] and [c["family"] for c in state["closed"]] == ["impact_late"]
    assert imp.update_late_episodes(state, "a", E + timedelta(days=8), _lc("hold"), True, "t")[0]["id"] == \
        state["episodes"]["a|impact_late"]["id"]                     # the same update: taken back, same id
    assert not state["closed"]


def test_two_updates_whose_30_day_windows_both_flag_make_one_episode_named_after_the_older():
    old, new = _lc("hold"), _lc("hold", block="ver:2.1@2026-08-18", R="2026-08-18")
    for c in (old, new):
        c["text"] = "x " + c["block"]
    ls, c = imp._late_pick("a", [new, old], {"late_v": 1}, False, True, date(2026, 9, 18))
    assert c is None and ls == {"block": old["block"], "level": "hold", "streak": 1}    # held once: not ready
    ls, c = imp._late_pick("a", [new, old], {"late_v": 1, "late": ls}, False, True, date(2026, 9, 19))
    assert ls["streak"] == 2 and c["block"] == old["block"] and c["also"] == ["v2.1"]
    state = {}
    eps = imp.update_late_episodes(state, "a", date(2026, 9, 19), c, True, "t")
    eps[0]["notified_at"] = "sent"
    first = eps[0]["id"]
    # the older one no longer holds, the newer does at the same level: the app's ONE condition goes on (its streak
    # carries — review: a reset here let the older update's episode age out and the newer open a 2nd, sent), the
    # snapshot moves to the newer block, nothing re-sent
    ls, c = imp._late_pick("a", [new], {"late_v": 1, "late": ls}, False, True, date(2026, 9, 20))
    assert ls == {"block": new["block"], "level": "hold", "streak": 3} and c["block"] == new["block"]
    eps = imp.update_late_episodes(state, "a", date(2026, 9, 20), c, True, "t")
    assert len(eps) == 1 and eps[0]["id"] == first and eps[0]["notified_at"] == "sent" and eps[0]["block"] == new["block"]
    # a lower level carries too (HALT → HOLD is never re-sent); only a rise starts a new streak (held twice, then sent)
    ls2, c2 = imp._late_pick("a", [dict(new, level="halt")], {"late_v": 1, "late": ls}, False, True, date(2026, 9, 21))
    assert c2 is None and ls2 == {"block": new["block"], "level": "halt", "streak": 1}
    ls3, c3 = imp._late_pick("a", [old], {"late_v": 1, "late": ls2}, False, True, date(2026, 9, 22))
    assert ls3["streak"] == 2 and c3["block"] == old["block"]
    ls, c = imp._late_pick("a", [old, dict(new, level="halt")], {"late_v": 1}, True, True, date(2026, 9, 21))
    assert c["block"] == new["block"] and c["level"] == "halt" and c["seed"]      # the highest level first


# ── 8. seeding ─────────────────────────────────────────────────────────────────────────────────

def test_late_conditions_are_seeded_on_the_first_evaluation_without_late_v_and_an_outdated_store_and_the_state_survives():
    E = END
    R = E - timedelta(days=42)
    st, rv = late_store(E - timedelta(days=24))
    d, _, state = run(st, rv, E=E)                                   # the app's first evaluation: seeded
    al = [a for a in d["alerts"] if a["family"] == "impact_late"]
    assert len(al) == 1 and not al[0]["notify"] and blk(d, R)["late"]["seeded"]
    # an evaluation with 7-day state but no late_v (the first run after the merge): seeded too
    d, _, st2 = run(st, rv, E=E, state={"eval": {"a": {"end": (E - timedelta(days=1)).isoformat(),
                                                       "impact": {"data": True, "blocks": {}}}}})
    al = [a for a in d["alerts"] if a["family"] == "impact_late"]
    assert len(al) == 1 and not al[0]["notify"] and st2["eval"]["a"]["impact"]["late_v"] == imp.LATE_V
    # an outdated store (its clean re-pull pending): never sent
    st3 = {"eval": {"a": {"end": (E - timedelta(days=1)).isoformat(),
                          "impact": {"data": True, "blocks": {}, "late_v": 1,
                                     "late": {"block": blk(d, R)["key"], "level": "hold", "streak": 1}}}}}
    d, _, _ = run(st, rv, E=E, state=st3, outdated=True)
    assert [a["notify"] for a in d["alerts"] if a["family"] == "impact_late"] == [False]
    # late_v and the streak survive evaluate_app's rebuild of state["eval"][app]
    _, _, s4 = run(st, rv, E=E - timedelta(days=2), state={"eval": {"a": {"end": (E - timedelta(days=3)).isoformat(),
                                                                          "impact": {"data": True, "blocks": {},
                                                                                     "late_v": 1}}}})
    assert s4["eval"]["a"]["impact"]["late"]["streak"] == 1 and s4["eval"]["a"]["impact"]["late_v"] == 1
    d, _, s4 = run(st, rv, E=E - timedelta(days=1), state=s4)
    assert s4["eval"]["a"]["impact"]["late"]["streak"] == 2
    assert [a["notify"] for a in d["alerts"] if a["family"] == "impact_late"] == [True]      # a new one: sent
    d, _, s4 = run(st, rv, E=E - timedelta(days=1), state=s4, now="2026-09-21T05:00:00Z")   # hourly: no advance
    assert s4["eval"]["a"]["impact"]["late"]["streak"] == 2


def test_updates_older_than_75_days_never_raise_a_late_alert():
    E = END + timedelta(days=40)                                     # v2.0 is 82 days old then
    st, rv = late_store(END - timedelta(days=24))
    st2, rv2 = make_impact_store(440, end=E, versions=rollout("1.0", [(END - timedelta(days=100), "1.9", 1.0),
                                                                      (END - timedelta(days=42), "2.0", 1.0),
                                                                      (END - timedelta(days=32), "2.1", 1.0)]),
                                 noise=0.02, seed=3, ipu=lambda d, v: 4.0 * (0.85 if d >= END - timedelta(days=24) else 1.0))
    d, _, _ = run(st2, rv2, E=E)
    W = blk(d, END - timedelta(days=42))["by_window"]["30"]
    assert W["state"] == "final" and W["verdict"]["late"] == "hold"
    assert blk(d, END - timedelta(days=42))["late"] is None           # v2.0: 82 days old — shown, never alerted
    late = [a for a in d["alerts"] if a["family"] == "impact_late"]
    assert [a["release"]["label"] for a in late] == ["v2.1"]          # (v2.1, 72 days old: the same drop, its own)
    assert blk(d, END - timedelta(days=32))["late"]["level"] in ("hold", "halt")


# ── 9. noise ───────────────────────────────────────────────────────────────────────────────────

def test_the_noise_span_minimum_and_widening_follow_the_window_length():
    R = date(2026, 6, 1)
    days = [R + timedelta(days=3 + i) for i in range(30)]
    for N in (7, 14, 30, 60):
        sh = imp._shifts(R, days[:N] if N <= 30 else days, N)
        assert len(sh) == (56 if N == 7 else 8 * N) and imp._null_min(N) == (21 if N == 7 else 3 * N)
    vals = [0.01 * ((-1) ** i) * (1 + i % 5) for i in range(240)]
    base = max(eng.spread(vals, 0.0), imp.SIGMA_FLOOR)
    assert imp._null_sd(vals[:30], 7) == max(eng.spread(vals[:30], 0.0), imp.SIGMA_FLOOR)     # 7: no widening
    for df in (3, 4, 5, 6, 7, 8):
        v = vals[:30 * df]
        want = max(eng.spread(v, 0.0), imp.SIGMA_FLOOR) * (imp.T975[df] / imp.T975[8] if df < 8 else 1.0)
        assert imp._null_sd(v, 30) == pytest.approx(want)
    assert [round(imp.T975[df] / imp.T975[8], 2) for df in (3, 4, 5, 6, 7)] == [1.38, 1.2, 1.11, 1.06, 1.03]
    assert base > 0


def test_need_is_the_change_pakka_needs_and_never_changes_a_status():
    assert imp._need_rel(-0.1, 0.05, 3.0, 0.03) == pytest.approx(-(1 - math.exp(-0.15)))
    assert imp._need_rel(0.1, 0.05, 3.0, 0.03) == pytest.approx(math.exp(0.15) - 1)
    assert imp._need_rel(0.0, 0.001, 3.0, 0.03) == -0.03 and imp._need_rel(None, 0.2, 3.0, 0.05) < 0
    assert imp._need_pp(1.0, 0.4, 3.0, 1.5, 1.0) == pytest.approx(1.5) and imp._need_pp(-1.0, 1.0, 3.0, 1.5, 4.0) == -4.0
    assert imp._need_pp(-1.0, 1.0, 3.0, 1.5, 2.0) == -3.0
    st, rv = make_impact_store(120, versions=rollout("1.0", [(R0, "1.1", 0.3)]), noise=0.02, seed=9)
    d = run(st, rv)[0]
    off = run(st, rv, windows=False)[0]
    for k, r in blk(d, R0)["rows"].items():
        assert r["status"] == blk(off, R0)["rows"][k]["status"] and r["z"] == blk(off, R0)["rows"][k]["z"], k
    r = blk(d, R0)["rows"]["returning_dau"]
    assert r["status"] == "same" and r["z"] is None and r["noise"] and abs(r["need"]) >= imp.DAU_MIN_REL   # under the min


def test_a_long_window_without_the_history_for_its_noise_is_low_data_and_says_the_weeks():
    E = END
    R = E - timedelta(days=60)
    st, rv = make_impact_store(200, versions=rollout("1.0", [(R, "1.1", 1.0)]),     # 140 days before R: < 5·30+31
                               act=lambda d, v: 0.9 if v == "1.1" else 1.0)
    d = run(st, rv)[0]
    W = blk(d, R)["by_window"]["30"]
    assert W["state"] != "running" and "young" in W["notes"]
    r = W["rows"]["returning_dau"]
    assert r["status"] == "low" and r["reason"] == ("Update se pehle ka ~26 hafte ka data chahiye (30-din tulna ka aam "
                                                    "utaar-chadhaav napne ke liye) — is update se pehle ~19 hafte ka tha")
    for k in ("new_d1", "new_d7", "uninstall_d0"):                   # (a row under its minimum stays Normal)
        assert W["rows"][k]["status"] == "low" and "30-din tulna" in W["rows"][k]["reason"], k
    assert imp.low_null_n({"launch": R - timedelta(days=139)}, R, 60) == (
        "Update se pehle ka ~48 hafte (~11 mahine) ka data chahiye (60-din tulna ka aam utaar-chadhaav napne ke liye) — "
        "is update se pehle ~19 hafte ka tha")
    assert imp.low_null_n({"launch": R - timedelta(days=139)}, R, 14).startswith("Update se pehle ka ~15 hafte ka data")
    assert W["verdict"]["level"] == "continue" and not W["verdict"]["worse"] and "noise" not in r


# ── 10 / 16. no false alarms from plain noise at 14 / 30 / 60 ──────────────────────────────────────

def _noisy(seed, days=520, n_up=10, gap=21, first=200):
    rnd = random.Random(seed)
    hs = END - timedelta(days=days - 1)
    rels = [(hs + timedelta(days=first + gap * i), "1.%d" % (i + 1), 0.4) for i in range(n_up)]
    noise = 0.03 + 0.02 * rnd.random()
    ph = rnd.random() * 6.28
    memo = {}

    def rho(c, k, memo=memo, rnd=rnd):                                # D1 drifting in slow waves (±3 points over
        if c not in memo:                                            # months) + a day-to-day wobble
            memo[c] = math.exp(rnd.gauss(0, 0.03))
        wave = 0.03 * math.sin(ph + 2 * math.pi * (c - hs).days / 120) if k == 1 else 0.0
        return min(0.9, max(0.01, DEFAULT_RET(k) * memo[c] + wave))

    def bump(c):                                                     # install-day uninstall drifting too (campaigns)
        return {0: int(60 * math.sin(ph + 2 * math.pi * (c - hs).days / 90))}
    return make_impact_store(days, new=int(1500 + 1000 * rnd.random()), old=int(20000 + 30000 * rnd.random()),
                             versions=rollout("1.0", rels), noise=noise, seed=seed, rho=rho, weekend=1.1, noise_ar=0.9,
                             bump=bump)


def test_no_effect_updates_rarely_read_worse_at_14_30_and_60_days_and_never_raise_a_late_alert():
    # 200 updates with no real effect, D1 and install-day uninstall drifting in slow waves (campaign mix): the long
    # windows' own pseudo-update noise keeps them quiet (binomial·φ read ~1 in 3 install-day rows at 60 days as moved)
    judged = {14: 0, 30: 0, 60: 0}
    worse = {14: 0, 30: 0, 60: 0}
    bad = {14: 0, 30: 0, 60: 0}
    rate_rows = rate_flag = 0
    for seed in range(20):
        st, rv = _noisy(seed)
        d = run(st, rv)[0]
        assert not [a for a in d["alerts"] if a["family"] == "impact_late"]
        for b in d["impact"]["updates"]:
            for N in (14, 30, 60):
                W = b["by_window"][str(N)]
                if W["verdict"]["level"] is None or not any(r.get("noise") for r in W["rows"].values()):
                    continue
                judged[N] += 1
                worse[N] += bool(W["verdict"]["worse"])
                bad[N] += W["verdict"]["level"] in ("hold", "halt")
                for k in ("new_d1", "new_d7", "new_d30", "uninstall_d0"):
                    r = W["rows"].get(k)
                    if r and r["status"] not in ("low", "na", "pending"):
                        rate_rows += 1
                        rate_flag += r["status"] in ("worse", "better")
                        assert r.get("noise"), (N, k)                # judged only on the window's own noise
    assert judged[14] >= 150 and judged[30] >= 150 and judged[60] >= 100, judged
    assert rate_rows >= 1000 and rate_flag <= 0.01 * rate_rows, (rate_rows, rate_flag)
    for N in (14, 30, 60):
        assert worse[N] <= 0.03 * judged[N] and bad[N] <= 0.01 * judged[N], (N, judged, worse, bad)


# ── 11. trends ─────────────────────────────────────────────────────────────────────────────────

def test_steady_growth_is_not_better_at_30_or_60_days_and_the_expected_level_extrapolates_three_weeks(monkeypatch):
    E = END
    R = E - timedelta(days=80)
    g = lambda d: 1.05 ** ((d - (E - timedelta(days=499))).days / 7)                    # noqa: E731  +5% a week
    st, rv = make_impact_store(500, new=200, old=lambda d: 3000 * g(d), versions=rollout("1.0", [(R, "1.1", 1.0)]))
    d = run(st, rv)[0]
    for N in (30, 60):
        r = blk(d, R)["by_window"][str(N)]["rows"]["returning_dau"]
        assert r["status"] not in ("better", "worse") and _basis("returning_dau", r) == "expected", (N, r)
        mu = r["extra"]["mu_week"]
        assert mu == pytest.approx(math.log(1.05), abs=0.002)
        assert math.log(r["expected"] / r["before"]) == pytest.approx(3 * mu, abs=0.012)    # 3 weeks, not 4–9
        assert "trend_capped" in blk(d, R)["by_window"][str(N)]["notes"]
    monkeypatch.setattr(imp, "TREND_HORIZON_WEEKS", 99)
    r = blk(run(st, rv)[0], R)["by_window"]["60"]["rows"]["returning_dau"]
    assert math.log(r["expected"] / r["before"]) > 7 * math.log(1.05)                     # uncapped: 8–9 weeks


def test_a_steady_per_user_trend_is_plain_at_14_30_60_absorbed_by_the_noise_and_trend_net_at_7():
    E = END
    R = E - timedelta(days=80)
    hs = E - timedelta(days=499)
    spu = lambda d, v, new: 1.6 if new else 2.4 * 0.98 ** ((d - hs).days / 7)             # noqa: E731  −2% a week
    st, rv = make_impact_store(500, versions=rollout("1.0", [(R, "1.1", 1.0)]), spu=spu, noise=0.01, seed=2)
    b = blk(run(st, rv)[0], R)
    r7 = b["rows"]["sessions"]
    assert r7["basis"] == "expected" and r7["status"] == "same" and r7["expected"] is not None
    assert r7["change"] < -0.01                                       # the plain change; the trend-net one ~0
    for N in (14, 30, 60):
        r = b["by_window"][str(N)]["rows"]["sessions"]
        assert _basis("sessions", r) == "plain" and "expected" not in r and r["status"] not in ("worse", "better"), (N, r)
        assert "plain" in b["by_window"][str(N)]["notes"]
    assert b["by_window"]["60"]["rows"]["sessions"]["change"] < -0.08


def test_a_trend_too_steep_to_extrapolate_is_low_data_at_every_window():
    E = END
    R = E - timedelta(days=45)
    st, rv = make_impact_store(420, new=300, old=lambda d: 400 * 1.5 ** ((d - (E - timedelta(days=419))).days / 7),
                               ret_ok=lambda c: False, versions=rollout("1.0", [(R, "1.1", 1.0)]),
                               spu=lambda d, v, new: 1.6 if new else 2.4 * 1.5 ** ((d - E).days / 7))
    b = blk(run(st, rv)[0], R)
    assert b["rows"]["returning_dau"]["status"] == "low" and IMPACT_TREND in b["rows"]["returning_dau"]["reason"]
    for N in ("14", "30"):
        W = b["by_window"][N]
        assert W["state"] != "running"
        for k in ("returning_dau", "sessions"):
            r = W["rows"][k]
            assert r["status"] == "low" and r["reason"].endswith(IMPACT_TREND) and _basis(k, r) == "plain", (N, k, r)
            assert "z" not in r and "expected" not in r


# ── 12. states ─────────────────────────────────────────────────────────────────────────────────

def test_a_window_runs_until_complete_is_judged_at_end_a_plus_10_and_final_once_d30_is_in():
    E = END
    R = E - timedelta(days=42)
    st, rv = late_store(None)
    W = blk(run(st, rv, E=E - timedelta(days=5))[0], R)["by_window"]["30"]
    assert W["state"] == "running" and W["after"]["settled"] == 30          # every day settled, D7 not yet
    for k, r in W["rows"].items():
        want = W["after"]["final_on"] if k == "new_d30" else W["after"]["judged_on"]
        assert r["status"] == "pending" and r["ready_on"] == want and "change" not in r and "z" not in r, k
        assert "before" in r and "after_prov" in r, k
    assert W["verdict"]["level"] is None and W["verdict"]["why"] == "30 din poore ~7 Sep ko · faisla ~19 Sep ko"
    W = blk(run(st, rv, E=E - timedelta(days=20))[0], R)["by_window"]["30"]
    assert W["state"] == "running" and W["after"]["settled"] == 19 and W["after"]["settled_till"] == "2026-08-27"
    J = blk(run(st, rv, E=E)[0], R)["by_window"]["30"]
    assert J["state"] == "judged" and J["rows"]["new_d30"]["status"] == "pending" and J["verdict"]["early"]
    assert J["verdict"]["level"] in ("continue", "hold", "halt") and J["verdict"]["level"] != "win"
    st2, rv2 = make_impact_store(440, end=E + timedelta(days=40), noise=0.02, seed=3,
                                 versions=rollout("1.0", [(END - timedelta(days=100), "1.9", 1.0),
                                                          (R, "2.0", 1.0), (END - timedelta(days=32), "2.1", 1.0)]))
    F = blk(run(st2, rv2, E=E + timedelta(days=40))[0], R)["by_window"]["30"]
    assert F["state"] == "final" and F["verdict"]["final"] and F["rows"]["new_d30"]["status"] != "pending"


def test_a_window_of_a_release_just_out_is_running_with_nothing_settled():
    R = END - timedelta(days=1)
    st, rv = make_impact_store(400, versions=rollout("1.0", [(END - timedelta(days=100), "1.9", 1.0), (R, "2.0", 0.3)]))
    b = blk(run(st, rv)[0], R)
    for N in ("14", "30", "60"):
        W = b["by_window"][N]
        assert W["state"] == "running" and W["after"]["settled"] == 0 and W["verdict"]["level"] is None
        assert all("after_prov" not in r for r in W["rows"].values())


# ── 13. D30 ────────────────────────────────────────────────────────────────────────────────────

def test_d30_compares_install_days_by_their_ga4_new_users_is_secondary_and_ranks_after_the_primaries():
    E = END + timedelta(days=40)
    R = END - timedelta(days=42)
    a0 = R + timedelta(days=1)
    rho = lambda c, k: DEFAULT_RET(k) - (0.03 if k == 30 and c >= a0 else 0.0)            # noqa: E731
    st, rv = make_impact_store(440, end=E, versions=rollout("1.0", [(END - timedelta(days=100), "1.9", 1.0),
                                                                     (R, "2.0", 1.0)]), rho=rho)
    W = blk(run(st, rv, E=E)[0], R)["by_window"]["30"]
    r = W["rows"]["new_d30"]
    assert W["state"] == "final" and r["status"] == "worse" and r["change"] < -2.5 and _basis("new_d30", r) == "rate"
    assert r["from_b"] == (R - timedelta(days=60)).isoformat() and r["to_b"] == (R - timedelta(days=31)).isoformat()
    assert W["verdict"]["worse"] == ["new_d30"] and W["verdict"]["level"] == "continue"          # alone: never HOLD
    rows = {k: {"status": "same", "_ratio": 1.0, "change": 0.0} for k in imp.ROWS_LONG}
    rows["new_d30"] = {"status": "worse", "_ratio": 9.0, "change": -3.0, "before": 0.05, "after": 0.02}
    rows["time"] = {"status": "worse", "_ratio": 1.2, "change": -0.1, "before": 1.0, "after": 0.9, "adj": -0.1}
    rows["new_d1"] = {"status": "worse", "_ratio": 1.1, "change": -2.0, "before": 0.3, "after": 0.28}
    assert imp._rank(["new_d30", "time", "new_d1"], rows) == ["new_d1", "new_d30", "time"]
    base = date(2026, 9, 1)
    win = {"n": 30, "days_a": [base + timedelta(days=i) for i in range(30)], "adopt_mean": 0.9}
    win["settled"] = win["days_a"]
    v = imp.verdict({"win": win}, rows, {}, {"currency": "USD"}, final=True)
    assert v["level"] == "halt" and v["worse"] == ["new_d1", "time", "new_d30"]     # 1 primary + 2 groups (usage, d30)
    rows["new_d1"] = {"status": "same", "_ratio": 0.2, "change": 0.0}
    v = imp.verdict({"win": win}, rows, {}, {"currency": "USD"}, final=True)
    assert v["level"] == "hold" and v["worse"] == ["time", "new_d30"]                # 2 secondary groups: D30 its own


def test_d30_has_its_own_minimum_one_point_and_ten_percent():
    assert (imp.RET30_MIN_PP, imp.RET30_MIN_REL) == (1.0, 0.10)
    E = END + timedelta(days=40)
    R = END - timedelta(days=42)
    a0 = R + timedelta(days=1)
    rho = lambda c, k: DEFAULT_RET(k) - (0.004 if k == 30 and c >= a0 else 0.0)           # noqa: E731  −0.4 points
    st, rv = make_impact_store(440, end=E, versions=rollout("1.0", [(END - timedelta(days=100), "1.9", 1.0),
                                                                     (R, "2.0", 1.0)]), rho=rho)
    r = blk(run(st, rv, E=E)[0], R)["by_window"]["30"]["rows"]["new_d30"]
    assert r["status"] == "same" and abs(r["need"]) >= 1.0


# ── 15. cost ───────────────────────────────────────────────────────────────────────────────────

def test_the_long_windows_pseudo_updates_read_prefix_sums_never_the_whole_window(monkeypatch):
    # 12 updates on a store long enough for every row's 60-day noise: the per-user, rate and install-day null loops read
    # ≤ 12 prefix values a shift (an O(N) loop reads 2N: 120 at 60), and all three long windows together ≤ 8× the 7-day
    # loops (the returning DAU keeps its O(N) loop: log(r / expected) is not separable)
    E = END
    rels = [(E - timedelta(days=380 - 25 * i), "1.%d" % (i + 1), 0.6) for i in range(12)]
    st, rv = make_impact_store(520, versions=rollout("1.0", rels), noise=0.02, seed=4)
    counts = {}
    orig = imp._count

    def count(cx, key, n):
        counts.setdefault(key, []).append(n)
        orig(cx, key, n)
    monkeypatch.setattr(imp, "_count", count)
    run(st, rv)
    tot = {}
    for (kind, N), ns in counts.items():
        if kind == "dau":
            continue
        tot[N] = tot.get(N, 0) + sum(ns)
        if N >= 14:
            assert max(ns) <= 12 * 8 * N, (kind, N, max(ns))          # ≤ 12 values a shift, 8N shifts
    assert {(k, N) for k, N in counts if N == 60} >= {("pu", 60), ("rate", 60), ("d0", 60), ("dau", 60)}
    assert tot[14] + tot[30] + tot[60] <= 8 * tot[7], tot


# ── glue ───────────────────────────────────────────────────────────────────────────────────────

def test_the_generic_loop_never_closes_a_late_episode_and_each_is_listed_once_with_its_fields():
    state = {"episodes": {"a|impact_late": {"id": "L", "app_id": "a", "family": "impact_late", "dir": "up",
                                            "opened": "2026-09-10", "last_true": "2026-09-10", "misses": 0,
                                            "notified_at": None, "last": {}}}}
    for i in range(5):
        eng.update_episodes(state, "a", date(2026, 9, 11 + i), [], True, False, "t")
    assert state["episodes"]["a|impact_late"]["misses"] == 0
    E = END
    st, rv = late_store(E - timedelta(days=24))
    d, _, state = run(st, rv, E=E)
    late = [a for a in d["alerts"] if a["family"] == "impact_late"]
    assert len(late) == 1 and len({a["id"] for a in d["alerts"]}) == len(d["alerts"])
    a = late[0]
    assert a["unit"] == "rel" and a["level"] == "hold" and a["window"] == 30 and a["mixed"] == ["v2.1"]
    assert a["rows"]["worse"] == ["arpdau"] and a["message"] == "App: " + a["text"]


def test_the_block_keeps_its_7_day_alert_id_when_both_families_are_open():
    E = END
    R = E - timedelta(days=42)
    st, rv = late_store(E - timedelta(days=24), extra=())
    d0, _, state = run(st, rv, E=E)
    k = blk(d0, R)["key"]
    # (a 7-day episode closes at once past IMPACT_ALERT_DAYS (35) and a 30-day window is judged at R+40 at the earliest:
    # the two can only meet through state like this one — kept open by a recent "R")
    recent = (E - timedelta(days=10)).isoformat()
    seven = "a|uninstall_impact|ALL|up|2026-08-20|ver:2.0|hold"
    state["episodes"]["a|impact|ver:2.0"] = {"id": seven, "app_id": "a", "family": "impact", "dir": "up",
                                             "opened": "2026-08-20", "last_true": E.isoformat(), "misses": 0,
                                             "notified_at": "sent", "block": k, "vers": ["2.0"], "kind": "version",
                                             "peak": "hold", "last": {"R": recent, "since": R.isoformat(),
                                                                      "text": "v2.0 (8 Aug) ke baad time per user "
                                                                              "−10% · ⚠️ Wait and check — agla "
                                                                              "rollout roko, jaanch karo",
                                                                      "severity": "watch", "level": "hold",
                                                                      "release": {"key": k, "label": "v2.0",
                                                                                  "date": R.isoformat()},
                                                                      "now": 1.0, "before": 1.1, "rel": -0.1,
                                                                      "installs_from": recent, "installs_to": recent,
                                                                      "base_from": recent, "base_to": recent,
                                                                      "rows": {"worse": ["time"], "better": []}}}
    d, _, _ = run(st, rv, E=E, state=state, now="2026-09-21T05:00:00Z")
    b = blk(d, R)
    late = next(a for a in d["alerts"] if a["family"] == "impact_late")
    assert b["alert_id"] == seven and b["late"]["alert_id"] == late["id"] and b["default_window"] == 30


def test_the_windows_flag_off_is_the_v1_card_with_no_late_family():
    E = END
    st, rv = late_store(E - timedelta(days=24))
    d, row, state = run(st, rv, E=E, windows=False)
    assert d["impact"]["v"] == 1 and all("by_window" not in b and "late" not in b for b in d["impact"]["updates"])
    assert not [a for a in d["alerts"] if a["family"] == "impact_late"] and "late_v" not in state["eval"]["a"]["impact"]
    assert all("late" not in u for u in row["updates"])


def test_a_crash_in_the_long_windows_costs_their_block_never_the_7_day_card(monkeypatch):
    E = END
    st, rv = late_store(E - timedelta(days=24))
    good = run(st, rv, E=E)[0]

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(imp, "_long_window", boom)
    s = dict(st, window_end=E.isoformat())
    d, _ = eng.evaluate_app(s, "a", "App", {}, NOW, revenue=rv)
    assert all("by_window" not in b and b["late"] is None and b["default_window"] == 7 for b in d["impact"]["updates"])
    assert d["impact"]["flags"].pop("windows_failed") == 3 * len(d["impact"]["updates"])      # counted, never silent
    check_impact(dict(d["impact"], flags=dict(d["impact"]["flags"], windows_failed=1)), d)
    assert strip7(d) == strip7(good) and not [a for a in d["alerts"] if a["family"] == "impact_late"]


def test_the_alert_line_names_the_late_family():
    from admob_iq import build_static
    dash = {"uninstall": {"alerts": [{"id": "L", "notify": True, "severity": "watch", "family": "impact_late",
                                      "message": "App: v2.0 (8 Aug) ke 30 din baad …"},
                                     {"id": "S", "notify": True, "severity": "watch", "family": "impact",
                                      "message": "App: v2.0 (8 Aug) ke baad …"}]}}
    s = {"notify_dry_run": True, "telegram_token": "", "telegram_chat": "", "smtp": {"host": ""}}
    res = build_static.send_alerts(dash, s)
    text = " ".join(str(r.get("text") or r.get("body") or "") for r in res)
    assert "App: v2.0 (8 Aug) ke 30 din baad … · late update impact (GA4)" in text
    assert "App: v2.0 (8 Aug) ke baad … · update impact (GA4)" in text


def test_an_active_drift_inside_a_late_window_is_capped_and_seeded():
    from admob_iq.engine import active as act
    R = date(2026, 8, 8)
    udet = {"alerts": [{"family": "impact_late", "level": "hold", "dir": "up", "severity": "watch",
                        "release": {"key": "ver:2.0@2026-08-08", "label": "v2.0", "date": "2026-08-08"},
                        "rows": {"worse": ["arpdau"], "told": []}, "installs_to": "2026-09-07"}],
            "impact": {"updates": [{"key": "ver:2.0@2026-08-08", "label": "v2.0", "date": "2026-08-08",
                                    "by_window": {"30": {"after": {"from": "2026-08-09", "to": "2026-09-07"}}}}]}}
    c = {"metric": "ads", "dir": "down", "since": "2026-09-10"}
    rel, cap = act._link(c, udet)
    assert rel["label"] == "v2.0" and cap == "watch"                    # inside [R, to + LINK_AFTER]
    rel, cap = act._link(dict(c, since="2026-09-30"), udet)
    assert cap is None                                                  # past the window: not covered
    rel, cap = act._link(dict(c, dir="up"), udet)
    assert cap is None                                                  # the other direction: never
    rel, cap = act._link(dict(c, metric="ret_dau"), udet)
    assert cap is None                                                  # another metric: never
    rel, cap = act._link(dict(c, since=(R - timedelta(days=1)).isoformat()), udet)
    assert cap is None                                                  # before the release: never


# ── review fixes (2026-09-28): the Low data reasons say their real cause, told rows, one late episode ──────────────

LOW_N = re.compile(r"^Update se pehle ka ~(\d+) hafte(?: \(~\d+ mahine\))? ka data chahiye \((\d+)-din tulna ka aam "
                   r"utaar-chadhaav napne ke liye\) — is update se pehle ~(\d+) hafte ka tha$")


def _hist_rows(d):
    """Every long-window row reading LOW_NULL_N (the app's history): (N, key, weeks needed, weeks had)."""
    out = []
    for b in d["impact"]["updates"]:
        for n, W in (b.get("by_window") or {}).items():
            for k, r in W["rows"].items():
                m = LOW_N.match(r.get("reason") or "")
                if m:
                    assert int(m.group(2)) == int(n)
                    out.append((int(n), k, int(m.group(1)), int(m.group(3))))
    return out


def test_an_old_enough_app_whose_ga4_data_has_gaps_reads_gaps_never_its_age():
    # 400 days of history, a 140-day hole in the usage data before the release: the 14 / 30-day sessions noise can't
    # be measured — because of the hole, not the app's age (review: it said "needs ~15 weeks — had ~45")
    R = END - timedelta(days=80)
    st, rv = make_impact_store(400, versions=rollout("1.0", [(R, "1.1", 1.0)]), noise=0.01, seed=2,
                               spu=lambda d, v, new: 1.6 if new else (2.16 if d > R else 2.4))
    for i in range(60, 201):
        st["usage"].pop((R - timedelta(days=i)).isoformat())
    d = run(st, rv)[0]
    b = blk(d, R)
    for N in ("14", "30"):
        W = b["by_window"][N]
        r = W["rows"]["sessions"]
        assert r["status"] == "low" and r["reason"] == imp.LOW_NULL_GAP % int(N), (N, r)
        assert "young" not in W["notes"] and not imp.is_hist(r["reason"])
    # at 60 the normal-trend reference (R−88 … R−61) sits in the hole: that stretch is named, not "the 3 weeks before
    # the update" (which the app had)
    r = b["by_window"]["60"]["rows"]["sessions"]
    assert r["status"] == "low" and r["reason"] == "Update se ~60 din pehle ke 3 hafte ka data kam (normal trend napne ke liye)"
    assert _hist_rows(d) == []


def test_d30_needs_its_own_longer_history_and_says_so_without_contradicting_itself():
    # the app is 195 days old at the release: enough for the 30-day noise of every row (5·30+31 = 181 days) but not for
    # D30's (its cohorts reach 30 days further back: ~210) — D30 alone reads the app's age, with ITS weeks
    R = END - timedelta(days=70)
    st, rv = make_impact_store(266, versions=rollout("1.0", [(R, "1.1", 1.0)]), noise=0.01, seed=2,
                               rho=lambda c, k: DEFAULT_RET(k) - (0.02 if k == 30 and c > R else 0.0))
    d = run(st, rv)[0]
    W = blk(d, R)["by_window"]["30"]
    assert W["state"] == "final" and "young" in W["notes"]
    hist = [h for h in _hist_rows(d) if h[0] == 30]
    assert [(n, k) for n, k, _, _ in hist] == [(30, "new_d30")], hist
    assert hist[0][2:] == (30, 27)                                   # needs ~30 weeks, had ~27: never had ≥ needed
    assert all(h < w for _, _, w, h in _hist_rows(d))                 # (at 60 every row: 48 weeks needed, 27 had)
    assert all(r["status"] != "low" for k, r in W["rows"].items() if k != "new_d30")


def test_a_long_window_whose_trend_reference_is_before_launch_reads_the_apps_age_and_the_7_day_texts_stay():
    # launched 40 days before the release: its 30-day trend reference (R−58 … R−31) is mostly before the launch — the
    # app's age (the "young" line), never "the 2 / 3 weeks before the update were short" (it had 5 weeks)
    R = END - timedelta(days=80)
    st, rv = make_impact_store(121, versions=rollout("1.0", [(R, "1.1", 1.0)]), noise=0.01, seed=2,
                               spu=lambda d, v, new: 1.6 if new else (2.16 if d > R else 2.4),
                               old=lambda d: 30000 * (0.9 if d > R else 1.0))
    d = run(st, rv)[0]
    b = blk(d, R)
    W = b["by_window"]["30"]
    for k in ("returning_dau", "sessions", "arpdau"):
        assert W["rows"][k]["status"] == "low" and imp.is_hist(W["rows"][k]["reason"]), (k, W["rows"][k])
    assert "young" in W["notes"] and all(h < w for _, _, w, h in _hist_rows(d))
    assert not any("hafte ka data kam" in (r.get("reason") or "") for W in b["by_window"].values() for r in W["rows"].values())
    assert b["rows"]["returning_dau"]["reason"] == imp.LOW_NULL and b["rows"]["sessions"]["reason"] == imp.LOW_NULL


def test_no_long_window_row_ever_says_it_had_as_many_weeks_as_it_needs():
    # the invariant on a mixed bag of stores (young, old, gaps, noisy): a LOW_NULL_N row always had fewer weeks
    for i, (st, rv) in enumerate(list(_stores()) + [_noisy(1)]):
        d = run(st, rv)[0]
        for n, k, w, h in _hist_rows(d):
            assert h < w, (i, n, k, w, h)


def test_a_drop_an_update_in_the_before_window_already_told_is_never_re_sent_under_the_newer_update():
    # v2.0's ads/user drop (−9%, lasting) was its own 7-day HALT; v2.1, 11 days later, has v2.0 inside its 30-day
    # Before: its After reads worse than that Before — v2.0's news, never a late alert under v2.1's name
    A, B = END - timedelta(days=70), END - timedelta(days=59)
    st, rv = make_impact_store(400, versions=rollout("1.0", [(END - timedelta(days=150), "1.9", 1.0), (A, "2.0", 1.0),
                                                             (B, "2.1", 1.0)]),
                               noise=0.02, seed=3, ipu=lambda d, v: 4.0 * (0.91 if d >= A + timedelta(days=1) else 1.0))
    d = run(st, rv)[0]
    assert blk(d, A)["verdict"]["level"] in ("hold", "halt") and "arpdau" in blk(d, A)["verdict"]["worse"]
    b = blk(d, B)
    assert b["verdict"]["level"] == "continue"
    W = b["by_window"]["30"]
    assert [m["label"] for m in W["mixed_before"]] == ["v2.0"] and W["state"] != "running"
    v = W["verdict"]
    assert v["level"] == "hold" and v["told"] == ["arpdau"] and v["told_by"] == {"arpdau": "v2.0"} and v["late"] is None
    assert b["late"] is None and not [a for a in d["alerts"] if a["family"] == "impact_late"]


def test_the_late_alert_is_never_sent_twice_when_the_older_update_ages_out_while_a_newer_one_holds_the_same_drop():
    # daily evaluations through v2.0's day 75: its 30-day HOLD and v2.1's (released inside it) hold the same drop at
    # the same level — the ONE episode moves to v2.1 (refreshed), never closed and re-opened (review: re-sent)
    st, rv = make_impact_store(440, end=END + timedelta(days=40), noise=0.02, seed=3,
                               versions=rollout("1.0", [(END - timedelta(days=100), "1.9", 1.0),
                                                        (END - timedelta(days=42), "2.0", 1.0),
                                                        (END - timedelta(days=32), "2.1", 1.0)]),
                               ipu=lambda d, v: 4.0 * (0.8 if END - timedelta(days=24) <= d < END - timedelta(days=12)
                                                       else 1.0))
    state, ids, sent, blocks = {}, set(), [], []
    for off in range(30, 38):                                       # v2.0 (R = END−42) ages out on END+34
        E = END + timedelta(days=off)
        d, row, state = run(st, rv, E=E, state=state, now=E.isoformat() + "T01:00:00Z")
        late = [a for a in d["alerts"] if a["family"] == "impact_late"]
        assert len(late) == 1, off
        ids.add(late[0]["id"])
        sent += [off for a in late if a["notify"]]
        blocks.append(state["episodes"]["a|impact_late"]["block"])
        if off >= 34:                                                # v2.1: 67–71 days old — still in Recent updates
            u = next(u for u in row["updates"] if u["label"] == "v2.1")
            assert u["late"] == {"level": "hold", "alert_id": late[0]["id"]}
    assert len(ids) == 1 and sent == []                              # seeded on the first run, never (re)sent
    assert blocks[0].startswith("ver:2.0@") and blocks[-1].startswith("ver:2.1@")


def test_an_update_60_to_75_days_old_with_a_late_condition_stays_in_recent_updates():
    E = END + timedelta(days=35)                                     # v2.1 is 67 days old: past IMPACT_LIST_DAYS (60)
    st, rv = make_impact_store(440, end=END + timedelta(days=40), noise=0.02, seed=3,
                               versions=rollout("1.0", [(END - timedelta(days=100), "1.9", 1.0),
                                                        (END - timedelta(days=42), "2.0", 1.0),
                                                        (END - timedelta(days=32), "2.1", 1.0)]),
                               ipu=lambda d, v: 4.0 * (0.8 if END - timedelta(days=24) <= d < END - timedelta(days=12)
                                                       else 1.0))
    d, row, _ = run(st, rv, E=E)
    late = [a for a in d["alerts"] if a["family"] == "impact_late"]
    assert [a["release"]["label"] for a in late] == ["v2.1"]
    assert [(u["label"], u["late"]["level"]) for u in row["updates"]] == [("v2.1", "hold")]   # v2.0 (77 days): none
    check_updates(row["updates"], row["data_till"])                   # (the contract: ≤ 60 days, ≤ 75 with a late chip)


def test_a_crash_in_one_window_costs_only_that_window_and_a_30_day_crash_never_marks_seeding_done(monkeypatch):
    E = END
    rels = [(END - timedelta(days=100), "1.9", 1.0), (END - timedelta(days=42), "2.0", 1.0),
            (END - timedelta(days=32), "2.1", 1.0)]
    st, rv = make_impact_store(403, end=END + timedelta(days=3), versions=rollout("1.0", rels), noise=0.02, seed=3,
                               ipu=lambda d, v: 4.0 * (0.85 if d >= END - timedelta(days=24) else 1.0))
    real = imp._long_window

    def crash_at(n):
        def f(cx, blk_, blocks, j, N, *a):
            if N == n:
                raise RuntimeError("x")
            return real(cx, blk_, blocks, j, N, *a)
        return f
    # a 60-day crash: the 14 / 30-day windows and the late condition stay, the failure is counted
    monkeypatch.setattr(imp, "_long_window", crash_at(60))
    d, _, st60 = run(st, rv, E=E)
    assert all(set(b["by_window"]) == {"14", "30"} for b in d["impact"]["updates"])
    assert d["impact"]["flags"]["windows_failed"] == len(d["impact"]["updates"])
    assert [a["release"]["label"] for a in d["alerts"] if a["family"] == "impact_late"] == ["v2.0"]
    assert st60["eval"]["a"]["impact"]["late_v"] == imp.LATE_V                  # (the 30-day windows all ran)
    # the first run after the merge (7-day state, no late_v) hits a 30-day crash: seeding is NOT marked done — the
    # next run seeds the historical condition (shown, never sent)
    state = {}
    eng.evaluate_app(dict(st, window_end=(E - timedelta(days=1)).isoformat()), "a", "App", state, NOW, revenue=rv,
                     windows=False)
    monkeypatch.setattr(imp, "_long_window", crash_at(30))
    d, _, state = run(st, rv, E=E, state=state)
    assert "late_v" not in state["eval"]["a"]["impact"] and d["impact"]["flags"]["windows_failed"] == 3
    monkeypatch.setattr(imp, "_long_window", real)
    for off in (1, 2):
        d, _, state = run(st, rv, E=E + timedelta(days=off), state=state)
        late = [a for a in d["alerts"] if a["family"] == "impact_late"]
        assert [a["notify"] for a in late] == [False] and state["eval"]["a"]["impact"]["late_v"] == imp.LATE_V
        assert "windows_failed" not in d["impact"]["flags"]


def test_a_live_shaped_app_keeps_its_windows_within_10_kb_a_block():
    # the fixture's blocks are small (review: live by_window averaged 9.3 KB, max 12.1): a live-shaped app — 520 days,
    # an update every 10 days (many Mixed), noisy AR days — keeps the spec's ≤ 10 KB raw a block; the sparse rows leave
    # out the extra keys the page never reads and a basis that is the window's default (filled back by the page)
    rels = [(END - timedelta(days=40 + 10 * i), "3.%d" % i, 0.6) for i in range(30)]
    st, rv = make_impact_store(520, versions=rollout("1.0", sorted(rels)), noise=0.03, seed=5, noise_ar=0.9,
                               ipu=lambda d, v: 4.0 * (0.9 if v == "3.3" else 1.0))
    d = run(st, rv)[0]
    sizes = [len(json_bytes(b["by_window"])) for b in d["impact"]["updates"]]
    assert len(sizes) == 30 and max(sizes) <= 10000 and sum(sizes) / len(sizes) <= 9500, (max(sizes), sum(sizes) / 30)
    for b in d["impact"]["updates"]:
        for W in b["by_window"].values():
            for k, r in W["rows"].items():
                assert not set(r.get("extra") or {}) & set(imp.EXTRA_UNREAD), (k, r["extra"])
                assert r.get("basis") != imp.BASIS_LONG[imp.UNIT[k]], (k, r.get("basis"))


def test_the_workflow_passes_the_impact_windows_switch(monkeypatch):
    # the rollback switch (spec §7.1) must reach the build step from a repo variable — no code push to turn it off
    import os
    from admob_iq.config import settings
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        y = f.read()
    assert "IMPACT_WINDOWS:       ${{ vars.IMPACT_WINDOWS || 'true' }}" in y
    monkeypatch.setenv("IMPACT_WINDOWS", "false")
    assert settings()["impact_windows"] is False
    monkeypatch.setenv("IMPACT_WINDOWS", "true")
    assert settings()["impact_windows"] is True


# ── the committed frontend fixture (tests.make_uninstall_fixture) ─────────────────────────────────

def _fixture():
    import json
    import os
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "uninstall_sample.json"),
              encoding="utf-8") as f:
        return json.load(f)


def test_the_fixture_shows_a_late_drop_sent_once_a_told_hold_and_running_windows_within_the_size_guard():
    fx = _fixture()
    apps = {a["app"]: a for a in fx["asset"]["apps"]}
    for a in fx["asset"]["apps"]:
        check_impact(a["impact"], a)
        for b in a["impact"]["updates"]:                            # ≤ 10 KB raw of windows a block
            assert len(json_bytes(b["by_window"])) <= 10000, (a["app"], b["label"])
    ld = {b["label"]: b for b in apps["Demo Late Drop"]["impact"]["updates"]}
    assert ld["v2.0"]["verdict"]["level"] == ld["v2.1"]["verdict"]["level"] == "continue"
    W = ld["v2.0"]["by_window"]["30"]
    assert W["state"] == "judged" and W["verdict"]["late"] == "hold" and W["verdict"]["told"] == []
    assert W["rows"]["new_d30"]["status"] == "pending" and [m["label"] for m in W["mixed"]] == ["v2.1"]
    assert ld["v2.0"]["by_window"]["60"]["state"] == "running" and ld["v1.9"]["by_window"]["60"]["state"] == "final"
    assert ld["v2.0"]["default_window"] == 30 and ld["v2.0"]["late"]["level"] == "hold"
    late = [x for x in apps["Demo Late Drop"]["alerts"] if x["family"] == "impact_late"]
    assert len(late) == 1 and late[0]["id"] == ld["v2.0"]["late"]["alert_id"] and not late[0]["notify"]   # sent
    assert "30 din ka result abhi baaki" in late[0]["text"] and "beech me 1 aur update (v2.1)" in late[0]["text"]
    sent = [s["run"] for s in fx["sent"] if "ke 30 din baad" in (s["email"] or "") + (s["telegram"] or "")]
    assert sent == ["2026-09-24T12:00Z"]                            # run 6 (data day E−1): held on runs 5 and 6
    lt = apps["Demo Late Told"]["impact"]["updates"][0]
    assert lt["verdict"]["level"] == "hold" and lt["by_window"]["30"]["verdict"]["told"] == ["new_d1"]
    assert lt["by_window"]["30"]["verdict"]["late"] is None and lt["late"] is None
    assert not [x for x in apps["Demo Late Told"]["alerts"] if x["family"] in ("impact", "impact_late")]
    for name, label in (("Demo Caller – Test App", "v3.2"), ("Demo Flashlight", "v1.3")):
        b = next(b for b in apps[name]["impact"]["updates"] if b["label"] == label)
        assert b["by_window"]["30"]["state"] == b["by_window"]["60"]["state"] == "running"
    rows = {r["app"]: r for r in fx["dashboard_uninstall"]["apps"]}
    u = next(u for u in rows["Demo Late Drop"]["updates"] if u["label"] == "v2.0")
    assert u["late"] == {"level": "hold", "alert_id": late[0]["id"]}
    assert fx["public_log"][5].endswith("impact_late alerts 1 (new 1)")
    assert fx["public_log"][0].endswith("impact_late alerts 0 (new 0)")                  # the seed run: nothing


def json_bytes(x):
    import json
    return json.dumps(x, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
