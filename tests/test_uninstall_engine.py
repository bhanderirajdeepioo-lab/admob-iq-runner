"""Uninstall engine (admob_iq.engine.uninstall) — pure math on synthetic stores: cumulative cohort churn,
the comparable headline curve, the install-week triangle, adaptive checkpoints, recent-change alerts at
every checkpoint (vs the 4 weeks before and vs all-time, both directions, no spam), the daily rate band
(spikes + slow drift), alert episodes and the Hinglish messages."""

import copy
import random
import re
from datetime import date, timedelta

from admob_iq.engine import uninstall as eng
from tests.uninstall_synth import END, Truth, make_store, noisy_store, rate_year, run_daily, truth_store

AID = "ca-app-pub-0000000000000000~0000000001"
APP = "Phone Call – Caller ID"
NOW = "2026-09-21T01:00:00Z"
SEP = lambda d: date(2026, 9, d)                       # noqa: E731
DEVANAGARI = re.compile("[%s-%s]" % (chr(0x900), chr(0x97F)))     # UI text is Roman-script Hinglish only
STABLE_LAGS = {0: 300, 1: 40, 2: 25, 3: 15, 4: 10, **{n: 5 for n in range(5, 15)},
               **{n: 3 for n in range(15, 31)}, **{n: 1 for n in range(31, 400)}}


def evaluate(store, state=None, app=APP, aid=AID, E=None):
    state = {} if state is None else state
    if E is not None:
        store = dict(store, window_end=E.isoformat())
    detail, row = eng.evaluate_app(store, aid, app, state, NOW)
    return detail, row, state


def cohort_alerts(detail):
    return [a for a in detail["alerts"] if a["family"] == "cohort"]


def owner_bump(delta, since=SEP(12)):
    """Installs from `since` uninstall `delta`/1,000 more on day 1 — and that many fewer on day 2 (they
    left a day earlier), so only D1 moves; every later day of the curve stays the same."""
    return lambda c: {1: delta, 2: -delta} if c >= since else None


# ── cohort curve ─────────────────────────────────────────────────────────────────────────────────

def test_cumulative_per_cohort_is_monotonic_and_d2_d10_come_back_from_the_raw_lags():
    rnd = random.Random(3)
    st = make_store(60, lambda c: 800 + rnd.randint(0, 400), bump=lambda c: {rnd.randint(0, 20): rnd.randint(0, 40)})
    cd = eng.cohort_data(st)
    H = cd["H"]
    assert H == 60 and cd["E"] == END
    for i, row in enumerate(cd["cum"]):
        assert len(row) == H - i                                   # lags 0..age only: no incomplete day
        assert all(a <= b for a, b in zip(row, row[1:]))            # per cohort the curve only rises
    cf = eng.cohort_file(st)                                        # what the "Saare din" view reads
    assert cf["start"] == cd["hs"].isoformat() and len(cf["lags"]) == H and cf["new"] == cd["n"]
    for i, lags in enumerate(cf["lags"]):
        assert [l for l, _ in lags] == sorted(l for l, _ in lags) and all(l <= H - 1 - i for l, _ in lags)
    for N in (2, 10):                                               # not in a sparse list — still exact
        row = eng.compare(cd, N)
        top = H - 1 - N                                             # newest install day complete for N
        idx = range(top - eng.RECENT_K + 1, top + 1)
        x = sum(u for i in idx for l, u in cf["lags"][i] if l <= N)
        n = sum(cf["new"][i] for i in idx)
        assert row["recent"]["p"] == round(x / n, 5) and row["recent"]["users"] == n
        assert row["recent"]["to"] == (END - timedelta(days=N)).isoformat()


def test_headline_curve_uses_the_28_newest_complete_install_days_for_every_n():
    st = make_store(80, lambda c: 1000 + c.toordinal() % 97)
    cd = eng.cohort_data(st)
    cur = eng.headline_curve(cd)
    H = cd["H"]
    assert all(len(v) == H for v in cur.values())                   # every day N, none dropped
    for N in range(H):
        top = H - 1 - N
        lo = max(0, top - eng.HEAD_K + 1)
        assert cur["users"][N] == sum(cd["n"][lo:top + 1])
        assert cur["k"][N] == top - lo + 1
        x = sum(cd["cum"][i][N] for i in range(lo, top + 1))
        assert cur["p"][N] == round(x / cur["users"][N], 5)
        assert cur["lo"][N] <= cur["p"][N] <= cur["hi"][N]
    nmax = H - eng.HEAD_MIN_COHORTS
    assert all(k >= eng.HEAD_MIN_COHORTS for k in cur["k"][:nmax + 1]) and cur["k"][nmax + 1] < 7
    assert cur["k"][:H - eng.HEAD_K + 1] == [eng.HEAD_K] * (H - eng.HEAD_K + 1)   # equal count per N
    assert abs(cur["inc"][1] - 12.0) < 0.2                          # 12% of installs leave ON day 1


def test_triangle_rows_are_whole_weeks_newest_first_with_only_complete_cells():
    st = make_store(100, lambda c: 1000 + (c.toordinal() % 5) * 10)
    cd = eng.cohort_data(st)
    cols = [0, 1, 7, 30]
    tri = eng.triangle(cd, cols)
    rows = tri["rows"]
    assert rows[0]["to"] == END.isoformat() and rows[0]["partial"]          # E = Sat → Mon–Sat, 6 days
    assert rows[0]["from"] == (END - timedelta(days=END.weekday())).isoformat() and rows[0]["days"] == 6
    assert rows[-1]["from"] == cd["hs"].isoformat()                          # EVERY week, oldest last
    assert sum(r["days"] for r in rows) == 100 and sum(r["users"] for r in rows) == sum(cd["n"])
    assert [r["from"] for r in rows] == sorted((r["from"] for r in rows), reverse=True)
    for r in rows:
        last = date.fromisoformat(r["to"])
        for N, p in zip(cols, r["p"]):
            if last + timedelta(days=N) > END:
                assert p is None                                             # a day N still ahead: no cell
                continue
            i0, i1 = (date.fromisoformat(r["from"]) - cd["hs"]).days, (last - cd["hs"]).days
            x = sum(cd["cum"][i][N] for i in range(i0, i1 + 1))
            assert p == round(x / sum(cd["n"][i0:i1 + 1]), 5)                # the row's own pooled value
    assert rows[0]["p"][0] is not None and rows[0]["p"][1] is None           # Sat installs: D1 not seen yet
    assert tri["ref"][1] == 0.72 and tri["cols"] == cols


# ── adaptive checkpoints ─────────────────────────────────────────────────────────────────────────

def test_worked_example_new_app_is_every_day():
    d, row, _ = evaluate(make_store(20, 500))
    assert d["stage"] == "naya" and d["checkpoints"] == list(range(14)) and d["nmax"] == 13
    assert row["stage"] == "naya" and row["ready"]


def test_worked_example_growing_app_is_daily_first_week_then_wider():
    d, _, _ = evaluate(make_store(60, 150))
    assert d["stage"] == "badh_raha" and d["nmax"] == 53
    assert d["checkpoints"] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 14, 21, 30, 45]


def test_worked_example_big_stable_app_is_sparse_and_a_release_zooms_back_in():
    st = make_store(400, 5000, lags=STABLE_LAGS)
    d, _, _ = evaluate(st)
    assert d["stage"] == "stable" and d["nmax"] == 393 and d["zoom"] is None
    assert d["checkpoints"] == [0, 1, 2, 3, 7, 14, 30, 45, 60, 90, 120, 150] + list(range(180, 391, 30))
    rel = END - timedelta(days=5)
    st2 = make_store(400, 5000, lags=STABLE_LAGS,
                     versions=lambda c: {"1.0": 25000} if c < rel else {"1.0": 20000, "2.0": 5000})
    d2, _, _ = evaluate(st2)
    assert d2["releases"] == [{"date": rel.isoformat(), "version": "2.0", "kind": "version"}]
    assert d2["zoom"]["reason"] == "release" and d2["zoom"]["until"] == (rel + timedelta(days=21)).isoformat()
    assert "2.0" in d2["zoom"]["label"] and not DEVANAGARI.search(d2["zoom"]["label"])
    assert d2["checkpoints"] == sorted(set(d["checkpoints"]) | set(range(15)) | set(eng.LADDER_GROW))


def test_an_update_surge_is_a_release_too():
    surge = END - timedelta(days=3)
    st = make_store(200, 1000, upd=lambda c: 2000 if c == surge else 300)
    d, _, _ = evaluate(st)
    assert {"date": surge.isoformat(), "version": None, "kind": "update"} in d["releases"]


def test_steep_days_stay_daily_and_a_small_app_is_never_stable():
    steep = {0: 300, **{n: 25 for n in range(1, 13)}, **{n: 3 for n in range(13, 400)}}
    d, _, _ = evaluate(make_store(120, 1000, lags=steep))
    assert d["stage"] == "badh_raha" and set(range(13)) <= set(d["checkpoints"]) and 13 not in d["checkpoints"]
    small, _, _ = evaluate(make_store(400, 50, lags=STABLE_LAGS))            # ±1 point needs ~350 installs/day
    assert small["stage"] == "badh_raha" and small["checkpoints"][:10] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 10]
    assert "installs" in small["stage_why"]


def test_stable_needs_7_daily_evaluations_in_a_row_but_is_immediate_on_the_first():
    st = make_store(410, 5000, lags=STABLE_LAGS, end=END + timedelta(days=10))
    state = {"eval": {AID: {"end": (END - timedelta(days=1)).isoformat(), "stage": "badh_raha",
                            "stable_hold": 0, "streak": {}}}}
    stages = []
    for k in range(8):
        d, _, _ = evaluate(st, state, E=END + timedelta(days=k))
        stages.append(d["stage"])
        if k == 2:                                                            # an hourly re-run: no count
            evaluate(st, state, E=END + timedelta(days=k))
    assert stages == ["badh_raha"] * 6 + ["stable", "stable"]
    assert "7" in evaluate(st, {"eval": {AID: {"end": END.isoformat(), "stage": "badh_raha", "stable_hold": 2,
                                               "streak": {}}}}, E=END + timedelta(days=1))[0]["stage_why"]
    first, _, _ = evaluate(st, E=END)
    assert first["stage"] == "stable"


# ── recent-change alerts ─────────────────────────────────────────────────────────────────────────

def test_owner_example_d1_72_to_79_gives_exactly_the_message():
    d, row, state = evaluate(make_store(42, 1000, bump=owner_bump(70)))
    al = cohort_alerts(d)
    assert len(al) == 1
    a = al[0]
    assert a["message"] == ("Phone Call – Caller ID: D1 uninstall 72% → 79% (+7 point) — 12–18 Sep ke installs, "
                            "pichhle 4 hafte se zyada · abhi ka data kaccha — number aur badh sakta hai")
    assert a["provisional"] is True                     # 12–18 Sep's day 1 = 13–19 Sep: still filling in (late data
                                                        # only ADDS uninstalls — the rise is real, it can only grow)
    assert a["text"] == a["message"].split(": ", 1)[1]
    assert a["severity"] == "warning" and a["dir"] == "up" and a["checkpoint"] == "D1" and a["n"] == 1
    assert a["vs"] == ["prev"] and a["also"] == [] and a["unit"] == "pct"
    assert (a["installs_from"], a["installs_to"]) == ("2026-09-12", "2026-09-18")
    assert (a["base_from"], a["base_to"]) == ("2026-08-15", "2026-09-11")
    assert a["now"] == 0.79 and a["before"] == 0.72 and a["delta_pp"] == 7.0 and a["users"] == 7000
    assert a["z"] > 3
    assert a["id"] == AID + "|uninstall_cohort|ALL|up|2026-09-19"
    assert row["head4"]["D1"]["alert"] and row["head4"]["D1"]["dir"] == "up" and row["alerts"]["warning"] == 1
    assert not row["head4"]["D0"]["alert"] and row["head4"]["D0"]["dir"] is None
    t1 = [t for t in d["table"] if t["n"] == 1][0]
    assert t1["alert"] and t1["prev"]["fires"] and t1["all"] is None        # all-time needs ≥8 weeks


def test_small_moves_do_not_fire_but_a_small_rate_moving_by_half_does():
    d, _, _ = evaluate(make_store(42, 1000, bump=owner_bump(20)))           # 72% → 74%: 7% of the kept side
    assert cohort_alerts(d) == []
    low = {0: 30, 1: 10, 2: 25, 3: 5, 4: 5}                                   # D1 4% → 6%: a THIRD more leave
    d, _, _ = evaluate(make_store(42, 1000, lags=low, bump=owner_bump(20)))
    a = cohort_alerts(d)
    assert len(a) == 1 and a[0]["checkpoint"] == "D1" and a[0]["severity"] == "warning"
    assert a[0]["text"].startswith("D1 uninstall 4.0% → 6.0% (+2 point)")
    d, _, _ = evaluate(make_store(42, 1000, bump=owner_bump(30)))           # 72% → 75%: real, but mild
    a = cohort_alerts(d)
    assert len(a) == 1 and a[0]["severity"] == "watch"
    assert a[0]["text"].startswith("D1 uninstall 72.0% → 75.0% (+3 point)")


def test_a_tiny_app_is_low_sample_and_never_alerts():
    d, row, _ = evaluate(make_store(42, 40, bump=owner_bump(100)))           # 7 × 40 = 280 installs
    assert cohort_alerts(d) == []
    t1 = [t for t in d["table"] if t["n"] == 1][0]
    assert t1["low_sample"] and not t1["alert"] and row["head4"]["D1"]["low_sample"]


def test_one_bad_install_day_on_a_big_app_is_not_an_alert():
    bad = END - timedelta(days=3)
    d, _, _ = evaluate(make_store(120, 5000, bump=lambda c: {1: 300} if c == bad else None))
    assert cohort_alerts(d) == []
    t1 = [t for t in d["table"] if t["n"] == 1][0]
    assert t1["prev"]["delta_pp"] > 4 and not t1["prev"]["fires"]            # big + significant, but ONE day


def test_a_big_app_alerts_on_the_second_daily_evaluation_only():
    X = END - timedelta(days=4)                                              # installs from X leave more on D0
    st = make_store(120, 5000, bump=lambda c: {0: 100} if c >= X else None)
    state = {}
    d0, _, _ = evaluate(st, state, E=END - timedelta(days=2))                # 3 moved days: not broad yet
    assert cohort_alerts(d0) == []
    d1, _, _ = evaluate(st, state, E=END - timedelta(days=1))                # holds (1st time): wait
    assert cohort_alerts(d1) == [] and state["eval"][AID]["streak"]["cohort|up"] == 1
    evaluate(st, state, E=END - timedelta(days=1))                           # hourly re-run: still waits
    assert state["eval"][AID]["streak"]["cohort|up"] == 1
    d2, _, _ = evaluate(st, state, E=END)                                    # holds again → alert, sent once
    a = cohort_alerts(d2)
    assert len(a) == 1 and a[0]["checkpoint"] == "D0" and a[0]["notify"] and a[0]["fresh"]


def test_a_drop_is_good_news_only_on_settled_data():
    # the drop from 12 Sep: its day 1 (13–19 Sep) is still PROVISIONAL (settled till 12 Sep) — a low reading
    # there may just be late app_remove still to come, so no "good news" yet
    d, row, _ = evaluate(make_store(42, 1000, bump=lambda c: {1: -70, 2: 70} if c >= SEP(12) else None))
    assert cohort_alerts(d) == [] and d["settled_till"] == "2026-09-12"
    assert row["head4"]["D1"]["dir"] is None and row["head4"]["D1"]["prov"] is True     # no ▼ from kaccha data
    t1 = [t for t in d["table"] if t["n"] == 1][0]
    assert t1["recent"]["p"] == 0.65 and t1["prov"] and t1["dir"] is None             # shown, marked kaccha
    # from 5 Sep: 5–11 Sep's day 1 is settled → good news, about exactly those install days
    d, row, _ = evaluate(make_store(42, 1000, bump=lambda c: {1: -70, 2: 70} if c >= SEP(5) else None))
    a = cohort_alerts(d)
    assert len(a) == 1 and a[0]["severity"] == "good" and a[0]["dir"] == "down" and a[0]["provisional"] is False
    assert a[0]["text"] == "D1 uninstall 72% → 65% (−7 point) — 5–11 Sep ke installs, pichhle 4 hafte se kam"
    h = row["head4"]["D1"]
    assert h["dir"] == "down" and h["alert"] and not h["prov"] and (h["from"], h["to"]) == ("2026-09-05", "2026-09-11")


def test_a_move_only_against_all_time_says_all_time_normal():
    hs = END - timedelta(days=119)
    st = make_store(120, 1000, bump=lambda c: {1: 60, 2: -60} if c >= hs + timedelta(days=60) else None)
    d, _, _ = evaluate(st)
    a = cohort_alerts(d)
    assert len(a) == 1 and a[0]["vs"] == ["all"] and a[0]["checkpoint"] == "D1"
    assert a[0]["text"] == ("D1 uninstall 74.8% → 78.0% (+3.2 point) — 12–18 Sep ke installs, all-time normal se zyada"
                            + eng.PROV_NOTE)
    t1 = [t for t in d["table"] if t["n"] == 1][0]
    assert not t1["prev"]["fires"] and t1["all"]["fires"]


def test_a_day_0_jump_is_one_alert_headlined_d0_with_the_rest_in_also():
    d, _, _ = evaluate(make_store(42, 1000, bump=lambda c: {0: 100} if c >= SEP(13) else None))
    a = cohort_alerts(d)
    assert len(a) == 1 and a[0]["checkpoint"] == "D0"
    assert a[0]["also"] == ["D1", "D2", "D3"]                   # D4: only 3 moved install days in view
    assert a[0]["text"] == ("D0 uninstall 60% → 70% (+10 point) — 13–19 Sep ke installs, pichhle 4 hafte se zyada"
                            " · D1, D2, D3 bhi upar · abhi ka data kaccha — number aur badh sakta hai")
    assert all(t["alert"] for t in d["table"] if "D%d" % t["n"] in ["D0"] + a[0]["also"])


# ── no repeats: an alert is about install days, and each install day is told once ─────────────────

LONG_END = date(2027, 1, 20)                          # past D30, D45, D60, D90 and D120 of a mid-Sep week
LONG_DAYS = (LONG_END - date(2026, 7, 1)).days + 1
BAD_WEEK = lambda c: SEP(12) <= c <= SEP(18)          # noqa: E731


def test_one_bad_install_week_is_one_notification_for_months():
    # a small app: the week's installs leave more on day 0 — so their curve sits higher at EVERY later
    # checkpoint as they age (D30 in Oct, D45, D60, D90 in Dec, D120 in Jan …): old news, never re-sent
    st = make_store(LONG_DAYS, 600, bump=lambda c: {0: 70} if BAD_WEEK(c) else None, end=LONG_END)
    sent, state = run_daily(st, SEP(1), LONG_END)
    assert [(x[1], x[2]) for x in sent] == [("watch", "cohort")] and sent[0][3].startswith("D0 uninstall 60.0% → 64.0%")
    assert state["closed"] and not state["episodes"]                       # it closed, and stayed closed
    # a big app (waits for a second evaluation), the change on day 1: still exactly one
    st = make_store(LONG_DAYS, 3000, bump=lambda c: {1: 50} if BAD_WEEK(c) else None, end=LONG_END)
    sent, _ = run_daily(st, SEP(1), LONG_END)
    assert len(sent) == 1 and sent[0][2] == "cohort" and sent[0][3].startswith("D1 uninstall 72.0% → 75.6%")


def test_a_lasting_change_is_one_alert_and_a_new_bad_week_later_is_news_again():
    st = make_store(LONG_DAYS, 1000, bump=lambda c: {1: 70} if c >= SEP(12) else None, end=LONG_END)
    sent, _ = run_daily(st, SEP(1), LONG_END)                             # every install since 12 Sep is worse
    assert len(sent) == 1 and sent[0][1] == "warning"
    later = lambda c: BAD_WEEK(c) or date(2026, 11, 20) <= c <= date(2026, 11, 26)     # noqa: E731
    st = make_store(LONG_DAYS, 1000, bump=lambda c: {1: 70} if later(c) else None, end=LONG_END)
    sent, _ = run_daily(st, SEP(1), LONG_END)
    assert [x[1] for x in sent] == ["warning", "warning"] and "18–24 Nov ke installs" in sent[1][3]


def test_a_late_checkpoint_move_on_the_kept_side_stays_a_watch():
    def row(before, now):
        b = {"p": before, "fires": True, "exact_pp": (now - before) * 100, "z": 6.0, "from": "2026-05-17",
             "to": "2026-06-13", "rel_small": abs(now - before) / min(before, 1 - before)}
        return {"n": 90, "recent": {"p": now, "users": 7000, "from": "2026-06-14", "to": "2026-06-20"},
                "prev": b, "all": None}
    assert eng.cohort_conditions([row(0.95, 0.97)])["up"]["severity"] == "watch"    # "40% of the 5% who kept it"
    assert eng.cohort_conditions([row(0.90, 0.96)])["up"]["severity"] == "warning"  # 6 points
    assert eng.cohort_conditions([row(0.04, 0.06)])["up"]["severity"] == "warning"  # the uninstall share +50%


# ── daily rate: band, spikes, drift ──────────────────────────────────────────────────────────────

def test_an_install_surge_or_cut_with_the_same_churn_is_no_rate_alert():
    start, end = date(2026, 5, 1), date(2026, 10, 15)
    for x in (1.6, 0.6):                                          # ad spend: +60% / −40% installs for 12 days
        t = Truth(start, end, lambda c: int(3000 * x) if SEP(1) <= c <= SEP(12) else 3000, old_per_day=300, seed=3)
        st = truth_store(t, end)
        d, _, _ = evaluate(st, E=SEP(7))
        i = (SEP(7) - start).days
        assert abs(d["daily"]["rate"][i] / d["daily"]["rate"][i - 10] - 1) > 0.2        # the raw rate DID jump …
        assert d["daily"]["lo"][i] <= d["daily"]["rate"][i] <= d["daily"]["hi"][i]      # … and "normal" moved with it
        sent, _ = run_daily(st, date(2026, 8, 20), end)
        assert sent == []


def test_a_steady_noisy_app_gets_well_under_one_false_rate_alert_a_year():
    # nothing changes; the daily uninstalls just wobble (weekend bump + 15% / 20% lognormal noise, or a small
    # app's pure counting noise at ~25 a day). The ±3 band on a 4-week MAD gave 2–6 false spikes and 3–6
    # false drifts per app-year here; 6 synthetic years per noise level:
    for kw in (dict(sigma=0.15), dict(sigma=0.20), dict(sigma=0.0, a28=5000, poisson=True)):
        tot = {"rate_drift": 0, "rate_spike": 0, "rate_zero": 0}
        for seed in range(6):
            for k, v in rate_year(noisy_store(seed=seed, **kw)).items():
                tot[k] += v
        assert tot["rate_drift"] / 6 <= 0.5 and (tot["rate_spike"] + tot["rate_zero"]) / 6 <= 0.5, (kw, tot)


def test_one_tracking_break_blinds_only_the_install_days_around_it():
    br = END - timedelta(days=10)
    st = make_store(430, 3000, rate_fn=lambda c: 0.0 if c == br else 5.0, end=END + timedelta(days=30))
    for c, lags in st["cohorts"].items():                                  # no app_remove on that day at all
        for lag in list(lags):
            if date.fromisoformat(c) + timedelta(days=int(lag)) == br:
                del lags[lag]
    spoilt = {br - timedelta(days=k) for k in range(8)}   # the break hit their day 0–7, which still loses ≥0.5%
    for E in (END, END + timedelta(days=30)):
        d, _, _ = evaluate(st, E=E)
        assert d["daily"]["breaks"] == [br.isoformat()] and d["stage"] == "stable"
        for t in d["table"]:                                  # at EVERY checkpoint only those 8 install days go
            days = {date.fromisoformat(t["recent"]["to"]) - timedelta(days=k) for k in range(7)}
            lost = len(days & spoilt) if t["n"] >= 7 else len({c for c in days & spoilt if (br - c).days <= t["n"]})
            assert t["recent"]["users"] == 3000 * (7 - lost), (E, t["n"])
            assert t["break_day"] == (br.isoformat() if lost else None) and t["low_sample"] == (lost > 2)
    rows = {t["n"]: t["recent"]["users"] for t in evaluate(st, E=END)[0]["table"]}
    assert rows[7] == rows[14] == 9000 and rows[30] == rows[60] == rows[90] == rows[180] == 21000




def _rate_store(rate, days=60, capped=False, day=END):
    st = make_store(days, 1000, rate_fn=lambda c: rate if c == day else 5.0)
    st["history_capped"] = capped              # capped = GA4 had data before our window: 28-day actives are full
    return st


def rate_alerts(d):
    return [a for a in d["alerts"] if a["family"].startswith("rate")]


def test_a_spike_day_above_the_band_is_a_warning_and_a_dip_is_good_news_once_settled():
    d, _, _ = evaluate(_rate_store(8.0))
    sp = [a for a in d["alerts"] if a["family"] == "rate_spike"]
    assert len(sp) == 1 and sp[0]["dir"] == "up" and sp[0]["severity"] == "warning" and sp[0]["unit"] == "per1k"
    assert sp[0]["text"] == ("19 Sep ko uninstall rate 8.0 /1k active (normal 3.4–7.5) — achanak zyada (800 uninstalls)"
                             " · abhi ka data kaccha — number aur badh sakta hai")
    assert sp[0]["day"] == "2026-09-19" and sp[0]["now"] == 8.0 and sp[0]["before"] == 5.0
    assert d["daily"]["hi"][-1] == 7.459 and d["daily"]["lo"][-1] == 3.352 and d["daily"]["med"][-1] == 5.0
    assert d["rate_now"]["out_of_band"] is False and d["rate_now"]["dir"] == "flat"  # 7-day pooled: +9%
    assert (d["rate_now"]["med"], d["rate_now"]["lo"], d["rate_now"]["hi"]) == (5.0, 3.352, 7.459)
    d, _, _ = evaluate(_rate_store(12.0))
    assert d["rate_now"]["dir"] == "up" and d["rate_now"]["last7"] == 6.0      # +20% vs its normal level
    dip = _rate_store(2.0, day=END - timedelta(days=7))
    for k in range(7, 0, -1):                                                  # 6 days old or younger: may still fill in
        d, _, _ = evaluate(dip, E=END - timedelta(days=k))
        assert rate_alerts(d) == [], k
    d, _, _ = evaluate(dip)                                                    # 7 days old: settled
    sp = [a for a in d["alerts"] if a["family"] == "rate_spike"]
    assert len(sp) == 1 and sp[0]["dir"] == "down" and sp[0]["severity"] == "good" and not sp[0]["provisional"]
    assert sp[0]["text"].startswith("12 Sep ko") and sp[0]["text"].endswith("— achanak kam (200 uninstalls)")


def test_a_zero_day_is_a_tracking_watch_once_it_is_settled():
    st = _rate_store(0.0, day=END - timedelta(days=7))
    d, _, _ = evaluate(st, E=END - timedelta(days=1))                          # 6 days old: late data may fill it
    assert rate_alerts(d) == [] and d["daily"]["breaks"] == ["2026-09-12"]    # (shown as a gap meanwhile)
    d, _, _ = evaluate(st)
    z = [a for a in d["alerts"] if a["family"] == "rate_zero"]
    assert len(z) == 1 and z[0]["severity"] == "watch"
    assert z[0]["text"] == "12 Sep ko ek bhi uninstall record nahi hua (normal ~500/din) — GA4/Firebase tracking check karo"
    assert d["daily"]["breaks"] == ["2026-09-12"]


def test_no_band_and_no_rate_alert_in_an_apps_first_4_weeks():
    d, _, _ = evaluate(_rate_store(20.0, days=28))
    assert d["daily"]["rate"][:27] == [None] * 27 and d["daily"]["rate"][27] == 20.0  # 28-day actives fill up first
    assert d["daily"]["med"] == [None] * 28 and rate_alerts(d) == []
    assert d["daily"]["un"][0] == 500                                     # the counts themselves are all there
    d, _, _ = evaluate(_rate_store(20.0, days=28, capped=True))            # full actives: a rate from day 1 …
    assert d["daily"]["rate"][0] == 5.0 and d["daily"]["med"] == [None] * 28   # … the band still needs 4 weeks
    d, _, _ = evaluate(_rate_store(20.0, days=34))                        # a band needs 14 SETTLED judged days
    assert d["daily"]["med"][33] is None
    d, _, _ = evaluate(_rate_store(20.0, days=35))
    assert round(d["daily"]["med"][34], 1) == 5.0 and [a["family"] for a in d["alerts"]] == ["rate_spike"]


def test_a_tracking_break_day_is_not_good_news():
    br = END - timedelta(days=9)                                            # settled: a real break, not late data
    st = make_store(90, 1000, rate_fn=lambda c: 0.0 if c == br else 5.0,
                    bump=lambda c: {0: -600, 1: -120, 2: -80} if c == br else None)   # no app_remove that day at all
    for c, lags in st["cohorts"].items():                                  # ... from ANY install day
        for lag in list(lags):
            if date.fromisoformat(c) + timedelta(days=int(lag)) == br:
                del lags[lag]
    d, _, _ = evaluate(st)
    assert [a["family"] for a in d["alerts"]] == ["rate_zero"]              # no drift / cohort "good news"
    assert d["daily"]["rate"][-10] == 0.0 and d["rate_now"]["last7"] == 5.0
    cd = eng.cohort_data(st)
    eng.mark_breaks(cd, eng.daily_series(st, None, cd)["broken"])
    row = eng.compare(cd, 0, late=eng.LATE_DAYS)                            # D0 on settled days: 6–12 Sep
    assert row["recent"]["p"] == 0.6 and row["recent"]["users"] == 6000     # the broken install day left out


def _drift_store(noise=None, spike_day=None):
    rnd = random.Random(11)

    def rate(c):
        r = 5.6 if c >= SEP(3) else 4.1
        if noise is not None:
            r = 5.0 * (1 + rnd.gauss(0, noise))
        if c == spike_day:
            r = 12.0
        return r
    return make_store(70, 1000, rate_fn=rate, end=SEP(16))


def test_a_slow_step_is_drift_since_its_first_day_not_a_row_of_spikes():
    st = _drift_store()
    ds = eng.daily_series(st)
    dr = eng.rate_drift(ds)
    assert dr["since"] == SEP(3) and dr["dir"] == "up" and round(dr["before"], 1) == 4.1 and round(dr["now"], 1) == 5.6
    d, _, _ = evaluate(st)
    al = [a for a in d["alerts"] if a["family"].startswith("rate")]
    assert [a["family"] for a in al] == ["rate_drift"]                       # the spikes inside it fold away
    assert al[0]["message"] == ("Phone Call – Caller ID: 3 Sep se uninstall rate 4.1 → 5.6 /1k active (+37%) — "
                                "dheere dheere badh raha hai · abhi ka data kaccha — number aur badh sakta hai")
    assert al[0]["since"] == "2026-09-03" and d["rate_now"]["drift"]["since"] == "2026-09-03"


def test_noise_or_one_spike_day_is_not_drift_and_drift_needs_3_new_days_to_confirm():
    assert eng.rate_drift(eng.daily_series(_drift_store(noise=0.05))) is None
    assert eng.rate_drift(eng.daily_series(_drift_store(noise=0.0, spike_day=SEP(10)))) is None
    st = make_store(80, 1000, rate_fn=lambda c: 5.6 if c >= SEP(3) else 4.1, end=SEP(20))
    state = {}
    d0, _, _ = evaluate(st, state, E=SEP(6))                                  # 4 days in: too short to be drift
    assert not [a for a in d0["alerts"] if a["family"] == "rate_drift"]
    for day in (7, 8, 9):                                                     # seen from 7 Sep: not yet confirmed
        d, _, _ = evaluate(st, state, E=SEP(day))
        evaluate(st, state, E=SEP(day))                                       # an hourly re-run: no count
        assert not [a for a in d["alerts"] if a["family"] == "rate_drift"]
    assert state["eval"][AID]["streak"]["drift|up"] == 3 and state["eval"][AID]["since"]["drift|up"] == "2026-09-07"
    d2, _, _ = evaluate(st, state, E=SEP(10))                                 # 3 new days on top: pakka
    dr = [a for a in d2["alerts"] if a["family"] == "rate_drift"]
    assert len(dr) == 1 and dr[0]["notify"] and dr[0]["severity"] == "warning" and dr[0]["dir"] == "up"
    assert dr[0]["since"] == "2026-09-03"


# ── episodes ─────────────────────────────────────────────────────────────────────────────────────

def _cond(dr="up"):
    return {"key": AID + "|cohort|" + dr, "family": "cohort", "dir": dr, "severity": "warning", "checkpoint": "D1",
            "n": 1, "also": [], "vs": ["prev"], "now": 0.79, "before": 0.72, "delta_pp": 7.0, "rel": 0.097,
            "z": 9.0, "installs_from": "2026-09-12", "installs_to": "2026-09-18", "base_from": "2026-08-15",
            "base_to": "2026-09-11", "since": None, "day": None, "users": 7000, "ns": [1]}


def test_an_episode_opens_once_notifies_once_and_closes_after_3_quiet_days():
    state, E = {}, END
    eps = eng.update_episodes(state, AID, E, [_cond()], True, False, NOW)
    assert len(eps) == 1 and eps[0]["notified_at"] is None and eps[0]["opened"] == "2026-09-19"
    first_id = eps[0]["id"]
    assert eng.alert_obj(eps[0], APP, E)["notify"] is True
    eps[0]["notified_at"] = NOW                                               # mark_notified after the send
    for _ in range(5):                                                        # hourly re-runs, same E
        eps = eng.update_episodes(state, AID, E, [], False, False, NOW)
    assert len(eps) == 1 and eps[0]["misses"] == 0
    eps = eng.update_episodes(state, AID, E + timedelta(days=1), [_cond()], True, False, NOW)
    assert eng.alert_obj(eps[0], APP, E + timedelta(days=1))["notify"] is False   # still the same episode
    for k in (2, 3):
        eps = eng.update_episodes(state, AID, E + timedelta(days=k), [], True, False, NOW)
        assert len(eps) == 1 and eps[0]["misses"] == k - 1
    eps = eng.update_episodes(state, AID, E + timedelta(days=4), [], True, False, NOW)
    assert eps == [] and len(state["closed"]) == 1 and state["closed"][0]["closed"] == "2026-09-23"
    eps = eng.update_episodes(state, AID, E + timedelta(days=9), [_cond()], True, False, NOW)
    assert eps[0]["id"] != first_id and eps[0]["notified_at"] is None       # a re-open is news again


def test_first_ever_evaluation_is_seeded_and_spike_days_close_a_week_later():
    state = {}
    eps = eng.update_episodes(state, AID, END, [_cond()], True, True, NOW)
    assert eps[0]["seeded"] and eps[0]["notified_at"] == NOW
    assert eng.alert_obj(eps[0], APP, END)["notify"] is False
    spike = {"key": AID + "|rate_spike|up|2026-09-19", "family": "rate_spike", "dir": "up", "severity": "warning",
             "day": END, "now": 8.0, "before": 5.0, "lo": 3.5, "hi": 6.5, "users": 800, "expected": 500.0}
    st2 = {}
    eng.update_episodes(st2, AID, END, [spike], True, False, NOW)
    nxt = dict(spike, key=AID + "|rate_spike|up|2026-09-20", day=END + timedelta(days=1))
    eps = eng.update_episodes(st2, AID, END + timedelta(days=1), [nxt], True, False, NOW)
    assert len(eps) == 1 and eps[0]["last_day"] == "2026-09-20"               # next day = the same jhatka
    assert eps[0]["last"]["day"] == "2026-09-19"
    eps = eng.update_episodes(st2, AID, END + timedelta(days=8), [], True, False, NOW)
    assert len(eps) == 1
    eps = eng.update_episodes(st2, AID, END + timedelta(days=9), [], True, False, NOW)
    assert eps == [] and st2["closed"][0]["family"] == "rate_spike"


def test_alerts_sort_warning_watch_good_then_fresh_first():
    mk = lambda sev, fresh, opened, app: {"severity": sev, "fresh": fresh, "opened": opened, "app": app, "id": app}  # noqa: E731
    got = eng.sort_alerts([mk("good", True, "2026-09-19", "a"), mk("watch", False, "2026-09-10", "b"),
                           mk("warning", False, "2026-09-18", "c"), mk("warning", True, "2026-09-17", "d"),
                           mk("warning", False, "2026-09-18", "B")])
    assert [a["app"] for a in got] == ["d", "B", "c", "b", "a"]


# ── messages ─────────────────────────────────────────────────────────────────────────────────────

def test_shown_delta_always_adds_up_and_text_is_roman_hinglish():
    for old, new in ((0.7249, 0.7951), (0.0404, 0.0611), (0.5, 0.5449), (0.8, 0.7), (0.123, 0.1449)):
        o, n, sd = eng.shown_pct(old, new)
        assert round(float(n.rstrip("%")) - float(o.replace("−", "-").rstrip("%")), 1) == sd
    assert eng.fmt_pp(7.0) == "+7" and eng.fmt_pp(-2.5) == "−2.5" and eng.fmt_pp(0) == "0"
    assert eng.fmt_span(SEP(12), SEP(18)) == "12–18 Sep"
    assert eng.fmt_span(date(2026, 8, 28), SEP(3)) == "28 Aug–3 Sep" and eng.fmt_span(SEP(12), SEP(12)) == "12 Sep"
    for st in (make_store(42, 1000, bump=owner_bump(70)), _drift_store(), _rate_store(0.0), _rate_store(9.0),
               make_store(42, 1000, bump=lambda c: {0: 100} if c >= SEP(5) else None)):
        d, _, _ = evaluate(st)
        for a in d["alerts"]:
            assert DEVANAGARI.search(a["message"]) is None and a["message"].startswith(APP + ": ")
        assert DEVANAGARI.search(d["stage_why"]) is None


def test_detail_carries_every_day_and_nothing_is_capped():
    st = make_store(400, 2000)
    d, row, _ = evaluate(st)
    assert len(d["daily"]["rate"]) == 400 and len(d["curve"]["p"]) == 400 and d["daily"]["start"] == st["history_start"]
    assert len(d["triangle"]["rows"]) == 58 and d["lifetime"]["users"] == 800000
    assert d["lifetime"]["un"] == sum(sum(v.values()) for v in st["cohorts"].values())
    assert [t["n"] for t in d["table"]] == d["checkpoints"]
    assert set(row["head4"]) == {"D0", "D1", "D7", "D30"}


# ── late data (Firebase adds app_remove for ~7 days) and incomplete days ──────────────────────────

LATE_SHARE = {0: 0.80, 1: 0.88, 2: 0.93, 3: 0.96, 4: 0.98, 5: 0.99}   # by days before E: what GA4 shows so far


def late_view(store, E=END, share=LATE_SHARE):
    """`store` as GA4 shows it at E while the newest days are still filling: each of those days' app_remove
    (daily users and every cell on that event day) scaled down — late data only ever adds, never removes."""
    st = copy.deepcopy(dict(store, window_end=E.isoformat()))
    for c, lags in st["cohorts"].items():
        for lag in lags:
            k = (E - (date.fromisoformat(c) + timedelta(days=int(lag)))).days
            if k in share:
                lags[lag] = int(lags[lag] * share[k])
    for d, r in st["daily"].items():
        k = (E - date.fromisoformat(d)).days
        if k in share:
            r["un"] = r["un_ev"] = int(r["un"] * share[k])
    return st


def test_late_data_is_never_read_as_good_news():
    st = late_view(make_store(120, 1000, rate_fn=lambda c: 9.3))
    d, row, _ = evaluate(st)
    assert d["alerts"] == [] and d["rate_now"]["dir"] != "down"              # nothing "kam" from a day still filling
    assert all(h["dir"] != "down" for h in row["head4"].values() if h)
    t0 = [t for t in d["table"] if t["n"] == 0][0]
    assert t0["prov"] and t0["recent"]["p"] < 0.58 and t0["dir"] is None     # shown as it is — marked kaccha
    full = evaluate(make_store(120, 1000, rate_fn=lambda c: 9.3))[0]
    assert d["curve"] == full["curve"]                                      # the curve: settled days only
    assert d["daily"]["med"][-1] == full["daily"]["med"][-1]                # … and so is every normal band
    old_rule, _ = eng.evaluate_app(st, AID, APP, {}, NOW, late=0)           # without the rule: false good news
    assert any(a["dir"] == "down" and a["family"] == "cohort" for a in old_rule["alerts"])


def test_a_rise_shows_through_late_data_with_the_kaccha_note():
    st = late_view(make_store(120, 1000, bump=lambda c: {0: 100} if c >= END - timedelta(days=10) else None))
    a = cohort_alerts(evaluate(st)[0])
    assert len(a) == 1 and a[0]["dir"] == "up" and a[0]["checkpoint"] == "D0" and a[0]["provisional"]
    assert a[0]["installs_to"] == END.isoformat() and a[0]["text"].endswith(eng.PROV_NOTE)


def test_a_moderate_rise_hidden_by_late_data_is_alerted_from_settled_days():
    # from 3 Sep, installs leave on day 0 instead of day 1: only D0 moves (+6 points) — and the newest D0
    # days read ~7% low while their late data is still coming, which hides it there
    st = late_view(make_store(120, 1000, bump=lambda c: {0: 60, 1: -60} if c >= END - timedelta(days=16) else None))
    cd = eng.cohort_data(st)
    eng.mark_breaks(cd, eng.daily_series(st, None, cd)["broken"])
    assert not eng._fires(eng.compare(cd, 0), "up") and eng._fires(eng.compare(cd, 0, late=7), "up")
    d, row, _ = evaluate(st)
    t0 = [t for t in d["table"] if t["n"] == 0][0]
    a = cohort_alerts(d)
    assert len(a) == 1 and a[0]["dir"] == "up" and a[0]["checkpoint"] == "D0" and not a[0]["provisional"]
    assert (a[0]["installs_from"], a[0]["installs_to"]) == ("2026-09-06", "2026-09-12")   # settled installs
    assert not a[0]["text"].endswith(eng.PROV_NOTE)
    assert t0["dir"] == "up" and t0["alert"] and not t0["prov"] and t0["recent"]["to"] == "2026-09-12"   # same numbers
    assert row["head4"]["D0"]["dir"] == "up" and row["head4"]["D0"]["to"] == "2026-09-12"


def test_a_falling_rate_is_drift_only_once_its_days_are_settled():
    st = make_store(90, 1000, rate_fn=lambda c: 3.0 if c >= SEP(10) else 5.0, end=SEP(24))
    d, _, _ = evaluate(st, E=SEP(19))                                        # 10–19 Sep: mostly provisional
    assert not [a for a in d["alerts"] if a["family"] == "rate_drift"] and d["rate_now"]["drift"] is None
    assert [a["family"] for a in eng.evaluate_app(dict(st, window_end="2026-09-19"), AID, APP, {}, NOW, late=0)[0]
            ["alerts"]].count("rate_drift") == 1                            # (the old rule would call it already)
    d, _, _ = evaluate(st)                                                   # 24 Sep: 10–17 Sep settled
    dr = [a for a in d["alerts"] if a["family"] == "rate_drift"]
    assert len(dr) == 1 and dr[0]["dir"] == "down" and dr[0]["severity"] == "good" and not dr[0]["provisional"]
    assert dr[0]["since"] == "2026-09-10" and d["rate_now"]["drift"]["prov"] is False
    assert d["rate_now"]["dir"] == "down" and d["rate_now"]["to"] == "2026-09-17" and not d["rate_now"]["prov"]


def test_an_incomplete_day_blinds_the_install_days_it_touches_and_never_alerts():
    from admob_iq.fetch import ga4_uninstall as gu
    from tests.uninstall_synth import UniStub
    t = Truth(END - timedelta(days=119), END, 1000, old_per_day=100)
    bad = END - timedelta(days=10)
    t.short_day = {bad: 0.2}                                               # GA4 never returns that day in full
    st = gu.fetch_full(UniStub(t, "tok", "p", "s"), END, 1300)
    st.update(app_id=AID, fetched_at="2026-09-21T01:00:00Z")
    assert list(st["flags"]["incomplete_days"]) == [bad.isoformat()]
    d, _, _ = evaluate(st)
    assert d["alerts"] == [] and list(d["flags"]["incomplete_days"]) == [bad.isoformat()]
    rows = [t for t in d["table"] if t["inc_day"]]
    assert rows and all(t["inc_day"] == bad.isoformat() for t in rows)
    for t_ in rows:                                                          # every install day it touched: left out
        assert t_["recent"]["users"] < 7000
    blind = copy.deepcopy(st)
    blind["flags"]["incomplete_days"] = {}                                   # if it were NOT flagged: false good news
    assert any(a["dir"] == "down" for a in evaluate(blind)[0]["alerts"])


def test_a_provisional_week_reading_under_the_band_is_not_shown_as_good_news():
    harsh = {k: 0.3 + 0.07 * k for k in range(7)}                  # Firebase far behind: the newest week reads ~half
    rn = evaluate(late_view(make_store(120, 1000, rate_fn=lambda c: 9.3), share=harsh))[0]["rate_now"]
    assert rn["prov"] and rn["last7"] < rn["lo"]                   # it does read under the band …
    assert rn["out_of_band"] is False and rn["dir"] != "down"      # … which is no news yet ("▼ range se kam")
    hot = make_store(120, 1000, rate_fn=lambda c: 12.0 if c > END - timedelta(days=7) else 5.0)
    rn = evaluate(hot)[0]["rate_now"]
    assert rn["prov"] and rn["last7"] > rn["hi"] and rn["out_of_band"] is True     # above it: real (only grows)


def test_a_closed_alert_no_longer_says_kaccha():
    st = late_view(make_store(120, 1000, bump=lambda c: {0: 100} if c >= END - timedelta(days=10) else None))
    _, _, state = evaluate(st)
    ep = [e for e in state["episodes"].values() if e["family"] == "cohort"][0]
    a = eng.alert_obj(ep, APP, END)
    assert a["provisional"] and a["text"].endswith(eng.PROV_NOTE)
    a = eng.alert_obj(dict(ep, closed="2026-10-02"), APP, date(2026, 10, 2))     # history: those days settled
    assert not a["provisional"] and not a["text"].endswith(eng.PROV_NOTE) and a["notify"] is False


def test_an_older_store_format_sends_nothing_not_even_an_alert_whose_send_failed():
    st = make_store(42, 1000, bump=owner_bump(70))
    _, _, state = evaluate(st)                                      # (seeded) …
    for e in state["episodes"].values():
        e.update(notified_at=None, seeded=False)                    # … say it opened on a later run and its send
    d, _, _ = evaluate(st, copy.deepcopy(state))                    # failed: still due — sent by the next run
    assert [a["notify"] for a in cohort_alerts(d)] == [True]
    d, _ = eng.evaluate_app(st, AID, APP, state, NOW, outdated=True)  # but not from an older store format
    assert cohort_alerts(d) and not any(a["notify"] for a in d["alerts"]) and d["flags"]["outdated"] is True
    assert all(e["seeded"] and e["notified_at"] == NOW for e in state["episodes"].values())


def test_install_days_held_only_while_provisional_are_not_told():
    # bad installs 20–24 Aug: while the days after them are still provisional they can't tell yet, so they keep
    # the alert open ("held") — claimed like the rest (the alert ends as it always did: a new bad week soon after
    # is news again), but never TOLD: once settled, a rise of their own counts them in
    bad = lambda c: date(2026, 8, 20) <= c <= date(2026, 8, 24)                      # noqa: E731
    st = make_store(200, 1000, bump=lambda c: {0: 100} if bad(c) else None, end=date(2026, 10, 15))
    sent, state = run_daily(st, date(2026, 8, 22), date(2026, 9, 6))
    ev = state["eval"][AID]
    assert len(sent) == 1 and ev["claimed"] == {"up": [["2026-08-17", "2026-08-27"]]}
    assert ev["held"] == {"up": [["2026-08-25", "2026-08-27"]]}                     # 25–27 Aug: normal, not told
    later = lambda c: date(2026, 8, 25) <= c <= date(2026, 8, 31)                    # noqa: E731
    st2 = make_store(200, 1000, bump=lambda c: {0: 100} if bad(c) else {0: 150} if later(c) else None,
                     end=date(2026, 10, 15))
    for E in (date(2026, 9, 7), date(2026, 9, 8)):                  # their late data is in: 25–31 Aug were bad too
        d, _ = eng.evaluate_app(dict(st2, window_end=E.isoformat()), AID, APP, state, NOW)
    a = cohort_alerts(d)
    assert len(a) == 1 and a[0]["notify"] and a[0]["installs_from"] == "2026-08-26"   # 26–27 Aug counted in
    assert "held" not in a[0] and "held" not in state["episodes"][AID + "|cohort|up"]["last"]
    b0 = date(2026, 8, 31)                                          # a second bad week a week later: news again
    two = lambda c: bad(c) or b0 <= c <= b0 + timedelta(days=4)     # noqa: E731
    sent, _ = run_daily(make_store(200, 1000, bump=lambda c: {0: 100} if two(c) else None, end=date(2026, 10, 15)),
                        date(2026, 8, 22), date(2026, 9, 30))
    assert [x[0] for x in sent] == ["2026-08-24", "2026-09-04"]
