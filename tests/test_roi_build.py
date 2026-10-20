"""📈 ROI (a section of the 💸 Install value tab) — the build step (admob_iq.roi_build), on made-up data: every install day
with its day-by-day revenue (the exact store × the engine's scale k), the checkpoints only when complete, the breakeven
day, the status vs usual, install months (one set of days per curve: never dips), payback from the newest month, the
lifetime P/L days, the countries board (Scale / Keep / Watch / Cut …) and what cutting saves, the four forms of ROI
(blended / paid-only / incremental / marginal as ranges, the paid share, the budget call; GA4's measured paid share and
premium from the paid cells once they cover an age), the portfolio file, the
pointer, one splat header rule, failure isolation and a counts-only line. Past D30 (the late store): 30-day buckets ×
each activity day's k, the base (d[30] or the D30 checkpoint), holes stop the columns, finality, breakeven / so far
through them, ≈ from GA4's "(other)" and from a block GA4 flagged (q bit 4), the final edge from the late cursor, and
without a late store, with the switch off (GA4_COHORT_LATE) or before the late read first reached today (late.done)
nothing of the file changes."""
import gzip
import json
import os
from datetime import date, timedelta

import pytest

from admob_iq import roi_build as rb

T = rb.T


class Pre:
    """Every activity day up to S is folded (complete)."""
    g = c = None

    def __init__(self, S):
        self.S = S

    def all(self, arr, a, b):
        return b <= self.S

    def win_ok(self, first, a, b):
        return True


def _P(hs, S, rate=0.01, n=100):
    """Install days hs … S: n installs; GA4 revenue `rate` USD a day per install day (k = 2 → AdMob-matched 2×)."""
    xs, X = {}, hs
    while X <= S:
        cum = [rate * n * (a + 1) * 2 for a in T]
        xs[X] = {"n": n, "u": [n] * 13, "R": cum, "E": [False] * 10, "Rr": cum, "P": [0] * 10}
        X += timedelta(days=1)
    return {"pre": Pre(S), "sc": {"kf": lambda d: (2.0, "ok", False, 2.0),
                                  "weeks": [{"ga4": 50.0, "admob": 100.0}] * 6},
            "xs": xs, "S": S, "hs": hs, "tz": "UTC"}


def test_cohorts_day_by_day_checkpoints_breakeven():
    hs, S = date(2026, 6, 1), date(2026, 10, 7)
    P = _P(hs, S)
    today = date(2026, 10, 13)
    co = {"read_today": today.isoformat(), "x": {}}
    for i in range(40):                                  # exact store: the last 40 install days, $0.50 GA4 a day
        X = today - timedelta(days=i)
        co["x"][X.isoformat()] = {"r": [500000] * 31, "u": [100 - L for L in range(31)]}
    spend = {"ccy": "USD", "daily": {}, "installs": {}, "first": "2026-06-01", "till": "2026-10-12"}
    X = hs
    while X <= today:
        spend["daily"][X.isoformat()] = 10_000_000       # $10 a day
        spend["installs"][X.isoformat()] = 80
        X += timedelta(days=1)
    rows = rb._cohorts(P, spend, lambda d: 1.0, co, today)
    by = {r["X"]: r for r in rows}
    assert rows[0]["X"] == hs and rows[-1]["X"] == today                 # every install day, through today
    r = by[date(2026, 9, 10)]                                           # 33 days old: every exact day final
    assert r["d"][:3] == [1.0, 2.0, 3.0] and r["df"] == 31 and len(r["d"]) == 31
    assert r["t"][T.index(7)] == 8.0                                    # D7 = the exact day 7 (k = 2)
    assert r["be"] == [9, True]                                         # $10 spent: back on day 9 (exact, final)
    assert r["sp"] == 10.0 and r["na"] == 80 and r["n"] == 100
    y = by[today - timedelta(days=1)]                                   # yesterday: day 0 and 1 seen, none final
    assert y["d"] == [1.0, 2.0] and y["df"] == 0 and y["t"] == [None] * 10 and y["be"] is None
    old = by[date(2026, 6, 10)]                                         # no exact cells: the install-day checkpoints
    assert old["d"] is None and old["t"][T.index(30)] == 0.01 * 100 * 31 * 2
    assert old["t"][T.index(180)] is None                              # day 180 is after S: not complete
    assert old["be"] == [7, False]                                     # ≥ $10 first at the day-7 checkpoint ($16)


def test_status_months_payback():
    hs, S = date(2026, 1, 1), date(2026, 10, 7)
    P = _P(hs, S)
    spend = {"ccy": "USD", "daily": {}, "installs": {}, "first": "2026-01-01", "till": "2026-10-07"}
    X = hs
    while X <= S:
        spend["daily"][X.isoformat()] = 10_000_000 if X < date(2026, 9, 25) else 30_000_000   # cost × 3 at the end
        X += timedelta(days=1)
    rows = rb._cohorts(P, spend, lambda d: 1.0, None, S)
    rb._statuses(rows)
    sts = {r["X"]: r["st"] for r in rows}
    assert sts[date(2026, 9, 20)] == "Normal" and sts[date(2026, 9, 26)] == "Worse"
    assert sts[date(2026, 10, 5)] == "Too early"                        # 2 days old: no D7 yet
    months = rb._months(rows)
    jan = months[0]
    assert jan[0] == "2026-01" and jan[1] == 3100 and jan[2] == 310.0 and jan[4] == 31
    assert jan[3][T.index(180)] is not None and jan[3][T.index(365)] is None   # Jan + 365 > S: not one curve point
    sep = [m for m in months if m[0] == "2026-09"][0]
    assert sep[3][T.index(14)] is None                                  # Sep 24 + 14 > S: the month waits (no dip)
    summ = rb._summary(rows, P, set(), 0, S)
    # the newest month with spend whose own curve crosses 100%: $2 a day per install day, $10 → day ~4
    assert summ["pb"] is not None and summ["pbm"] == "2026-09"
    assert summ["cov"] == 0.5 and summ["st"] in ("Worse", "Watch")
    assert summ["pools"]["7"]["r"]["n"] == rb.N_RECENT and summ["nb"] is None
    # nothing ever pays back: the newest month whose curve reached day 90 says how much came back (no older month asked)
    P2 = _P(hs, S, rate=0.0001)
    rows2 = rb._cohorts(P2, spend, lambda d: 1.0, None, S)
    rb._statuses(rows2)
    s2 = rb._summary(rows2, P2, set(), 0, S)
    assert s2["pb"] is None and s2["nb"][0] == 90 and s2["nb"][2] == "2026-06" and s2["best"][2] == "2026-10"
    assert s2["ret"]["1"]["r"] == 1.0                                   # the install-day users when no exact store


def test_four_forms_math():
    # every install is paid: paid-only = incremental = blended; marginal = blended × (1 + beta); no gap
    f = rb._f4(0.8, 1.0)
    assert f["paid"] == [0.8] * 3 and f["inc"] == [0.8] * 3 and f["gap"] == [0.0] * 3
    assert f["mar"] == [round(0.8 * (1 + b), 4) for b in rb.F4_BETA]
    # half paid: paid-only = blended × p·s ÷ (p·s + 1 − s) for each premium p; incremental keeps (1 − b) of the organic
    f = rb._f4(1.0, 0.5)
    for i, p in enumerate(rb.F4_P):
        assert f["paid"][i] == pytest.approx(p * 0.5 / (p * 0.5 + 0.5), abs=1e-4)
    c = f["paid"][1]
    assert f["inc"][1] == pytest.approx(1 - rb.F4_B[1] * (1 - c), abs=1e-4)
    assert f["mar"][1] == pytest.approx(f["inc"][1] * (1 + rb.F4_BETA[1]), abs=1e-4)
    assert f["gap"][1] == pytest.approx(1 - c, abs=1e-4)
    for k in ("paid", "inc", "mar", "gap"):                             # a range: low ≤ central ≤ high, never one number
        assert f[k][0] < f[k][1] < f[k][2]
    assert f["paid"][2] < 1.0 and f["inc"][0] > f["paid"][0]            # paid-only below blended; incremental above it
    # nothing paid: paid-only 0, incremental = what the organic part the spend caused would bring
    f = rb._f4(1.0, 0.0)
    assert f["paid"] == [0.0] * 3 and f["inc"] == [round(1 - b, 4) for b in rb.F4_B] and f["gap"] == [1.0] * 3


def test_budget_call():
    D = rb._decide
    assert D({"90": {"mar": [1.0, 1.1, 1.2]}}, 90) == {"a": 90, "v": "up", "mar": [1.0, 1.1, 1.2]}
    assert D({"90": {"mar": [0.5, 0.7, 0.99]}}, 90)["v"] == "down"
    assert D({"90": {"mar": [0.9, 1.05, 1.2]}}, 90)["v"] == "mixed"
    assert D({"90": {"bl": 0.5}}, 90)["v"] == "na"                    # no Google Ads install count: no paid share
    # the target age not complete yet: a shorter age already ≥ 100% at its low end says up (revenue only grows) …
    assert D({"7": {"mar": [0.2, 0.3, 0.4]}, "30": {"mar": [1.1, 1.3, 1.5]}}, 90) == {"a": 30, "v": "up",
                                                                                      "mar": [1.1, 1.3, 1.5]}
    assert D({"30": {"mar": [0.9, 1.3, 1.5]}}, 90) == {"a": 90, "v": "early", "mar": None}   # … else too early
    assert D({"7": {"bl": 0.2}, "30": {"bl": 0.5}}, 90)["v"] == "na"  # no age has a paid share: na, not "too early"


def test_beta_per_app(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    assert rb._betas(str(data)) == {}                                   # no file: every app on the pooled range
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / rb.F4_BETA_FILE).write_text(json.dumps({
        "a~1": [-0.12, -0.05, -0.01], "b~2": [-0.01, -0.05, -0.12],     # out of order
        "c~3": [-0.1, "x", 0], "d~4": [-2, -0.1, 0], "e~5": [-0.1, 0.0]}))   # not a number / out of bounds / short
    assert rb._betas(str(data)) == {"a~1": (-0.12, -0.05, -0.01)}
    (tmp_path / "config" / rb.F4_BETA_FILE).write_text("{not json")
    assert rb._betas(str(data)) == {}
    own = (-0.12, -0.05, -0.01)
    f = rb._f4(1.0, 0.5, own)
    assert f["mar"] == pytest.approx([f["inc"][i] * (1 + own[i]) for i in range(3)], abs=2e-4)


def _spend(hs, till, installs):
    sp = {"ccy": "USD", "daily": {}, "installs": {}, "first": hs.isoformat(), "till": till.isoformat()}
    X = hs
    while X <= till:
        sp["daily"][X.isoformat()] = 10_000_000                         # $10 a day
        sp["installs"][X.isoformat()] = installs(X)
        X += timedelta(days=1)
    return sp


def test_forms_same_days_as_the_section():
    hs, S = date(2026, 1, 1), date(2026, 10, 7)
    P = _P(hs, S)                                                       # 100 GA4 installs a day
    no_ads = {S - timedelta(days=8), S - timedelta(days=9)}             # two days of the D7 window: no Ads count
    rows = rb._cohorts(P, _spend(hs, S, lambda X: None if X in no_ads else 50), lambda d: 1.0, None, S)
    f = rb._forms(rows, 90)
    assert sorted(f["by"], key=int) == ["7", "30", "90"] and f["h"] == 90
    for a in (7, 30, 90):
        e, pool = f["by"][str(a)], rb._pool(rows, T.index(a))
        assert e["bl"] == pool["roas"] and e["from"] == pool["from"] and e["to"] == pool["to"]   # = the section's ROAS
        assert e["days"] == rb.N_RECENT and e["s"] == 0.5 and e["sp"] == 10.0 * rb.N_RECENT
        assert e["paid"][0] < e["paid"][1] < e["paid"][2] < e["bl"]
    e7 = f["by"]["7"]                                                   # the paid share from the days with a count
    assert e7["days_na"] == rb.N_RECENT - 2 and e7["nn"] == 100 * (rb.N_RECENT - 2) and e7["na"] == 50 * (rb.N_RECENT - 2)
    assert f["by"]["30"]["days_na"] == rb.N_RECENT
    assert f["dec"]["a"] == 90 and f["dec"]["mar"] == f["by"]["90"]["mar"]
    # the payback target is one more age when it is not one of the usual three
    assert sorted(rb._forms(rows, 180)["by"], key=int) == ["7", "30", "90", "180"]
    # a young app: no D90 yet, but D30 already pays at its low end → up from D30; slow → too early
    hs2 = S - timedelta(days=40)
    rich = rb._cohorts(_P(hs2, S, rate=0.05), _spend(hs2, S, lambda X: 50), lambda d: 1.0, None, S)
    assert sorted(rb._forms(rich, 90)["by"], key=int) == ["7", "30"] and rb._forms(rich, 90)["dec"]["v"] == "up"
    poor = rb._cohorts(_P(hs2, S, rate=0.001), _spend(hs2, S, lambda X: 50), lambda d: 1.0, None, S)
    assert rb._forms(poor, 90)["dec"] == {"a": 90, "v": "early", "mar": None, "live": True}
    assert rb._forms(rb._cohorts(_P(hs, S, rate=0.0001), _spend(hs, S, lambda X: 50), lambda d: 1.0, None, S),
                     90)["dec"]["v"] == "down"
    # no Google Ads install count at all: blended only, no invented split
    bare = rb._forms(rb._cohorts(P, _spend(hs, S, lambda X: None), lambda d: 1.0, None, S), 90)
    assert "s" not in bare["by"]["30"] and "mar" not in bare["by"]["30"] and bare["dec"]["v"] == "na"
    assert rb._forms([], 90) == {"h": 90, "by": {}, "dec": {"a": 90, "v": "early", "mar": None, "live": False},
                                 "beta": list(rb.F4_BETA), "bsrc": "pool"}
    # an app's own beta range (config/roi_beta.json): its marginal form and its label
    own = rb._forms(rows, 90, (-0.12, -0.05, -0.01))
    assert own["bsrc"] == "app" and own["beta"] == [-0.12, -0.05, -0.01] and f["bsrc"] == "pool"
    e, e0 = own["by"]["30"], f["by"]["30"]
    assert e["inc"] == e0["inc"] and e["mar"] == pytest.approx([e["inc"][i] * (1 + b) for i, b in enumerate(own["beta"])],
                                                               abs=2e-4)
    # a paused app (no spend day ≥ MIN_SPEND in its last F4_LIVE spend days): the call is kept, marked not live
    stop = S - timedelta(days=rb.F4_LIVE)
    paused = rb._cohorts(_P(hs, S, rate=0.0001), _spend(hs, S, lambda X: 50), lambda d: 1.0, None, S)
    for r in paused:
        if r["X"] > stop:
            r["sp"] = 1.0                                               # a trickle below MIN_SPEND
    pd = rb._forms(paused, 90)["dec"]
    assert pd["v"] == "down" and pd["live"] is False
    assert rb._forms(rows, 90)["dec"]["live"] is True


def _paid_ida(first, last, weeks, paid_n=800, org_n=200, prem=1.5, holes=(), share=0.8):
    """IDAY_EXT-shaped data: install weeks `weeks` (Mondays) with legacy cells c (all users) and paid cells cp; every
    activity day first … last folded in both reads (cst / cpst) except `holes` (the paid read failed). Revenue per
    install and band: organic 1, paid `prem` (micros × 1e6); country slots "0" / "1" + a gap row that must be ignored."""
    days, d2, c, cp = {}, {}, {}, {}
    D = first
    while D <= last:
        days[D.isoformat()] = {"st": "ok", "cst": "ok"}
        d2[D.isoformat()] = {"cpst": "err" if D in holes else "ok", "cpn": share}
        D += timedelta(days=1)
    for W in weeks:
        k = W.isoformat()
        pr, orr = int(paid_n * prem * 1e6) // 2, int(org_n * 1e6) // 2
        c[k] = {"0": {"n": (paid_n + org_n) // 2, "r": [pr + orr] * 8}, "1": {"n": (paid_n + org_n) // 2,
                                                                             "r": [pr + orr] * 8},
                "gap": {"n": 999, "r": [10 ** 9] * 8}}
        cp[k] = {"0": {"n": paid_n // 2, "r": [pr] * 11}, "1": {"n": paid_n // 2, "r": [pr] * 11}}
    return {"days": days, "d2": d2, "c": c, "cp": cp}


def test_ga4_paid_cells():
    mon = [date(2026, 8, 3) + timedelta(days=7 * i) for i in range(8)]           # Aug 3 … Sep 21
    last = date(2026, 10, 9)
    hole = date(2026, 9, 25)                                                    # the paid read of one day failed
    ida = _paid_ida(mon[0], last, mon, holes={hole})
    g = rb._ga4p(ida, [7, 30, 90, 180])
    assert g["share"][last.isoformat()] == 0.8 and hole.isoformat() not in g["share"]
    p7 = g["prem"]["7"]                     # weeks Sep 14 / 21 reach the hole by day 7: the newest 4 whole ones before
    assert p7["w"] == rb.F4_PW and p7["to"] == "2026-09-07" and p7["from"] == "2026-08-17"
    assert p7["p"] == 1.5 and p7["s"] == 0.8 and p7["rs"] == round(1200 / 1400, 4)            # the gap row left out
    assert p7["np"] == 4 * 800 and p7["no"] == 4 * 200
    p30 = g["prem"]["30"]                                  # W + 36 before the hole: Aug 3 … Aug 17 only
    assert p30["to"] == "2026-08-17" and p30["w"] == 3 and p30["p"] == 1.5
    assert "90" not in g["prem"] and "180" not in g["prem"]   # not whole yet / past the legacy cells' 90 days
    # too few organic installs to tell a premium: none (the range stays); no paid cells at all: None
    assert rb._ga4p(_paid_ida(mon[0], last, mon, org_n=20), [7])["prem"] == {}
    assert rb._ga4p({"days": ida["days"], "c": ida["c"]}, [7]) is None
    assert rb._ga4p({"cp": {}, "d2": {}}, [7]) is None


def test_ga4_paid_cells_late_ages():
    """Ages 180 / 365: every install's revenue = the legacy cells to 90 + IDAY_EXT's late cells (c2), the paid cells to
    the age — only for weeks whose late days are folded in c2 too (c2st); a = 90 never needs c2."""
    mon = [date(2025, 12, 1) + timedelta(days=7 * i) for i in range(20)]       # Dec 1 … Apr 13
    last = date(2026, 10, 9)
    ida = _paid_ida(mon[0], last, mon)
    hole = date(2026, 9, 25)                                                   # one late (c2) read failed
    for W in mon:
        pr, orr = int(800 * 1.5 * 1e6) // 2, int(200 * 1e6) // 2
        ida.setdefault("c2", {})[W.isoformat()] = {"0": {"r2": [pr + orr] * 3}, "1": {"r2": [pr + orr] * 3},
                                                   "gap": {"r2": [10 ** 9] * 3}}
    for k, e in ida["d2"].items():
        e["c2st"] = "err" if k == hole.isoformat() else "ok"
    g = rb._ga4p(ida, [90, 180, 365])
    p180 = g["prem"]["180"]                     # W + 186 ≤ Oct 9 and before the hole: Mar 16 back (Mar 23 + 186 = the hole)
    assert p180["to"] == "2026-03-16" and p180["w"] == rb.F4_PW and p180["p"] == 1.5 and p180["s"] == 0.8
    assert "365" not in g["prem"]                                              # W + 371 not whole yet
    assert g["prem"]["90"]["to"] == "2026-04-13"           # a = 90 needs no late read (the hole is past its days)
    del ida["c2"]                                          # without the late cells the organic side has no 91–180
    assert rb._ga4p(ida, [180])["prem"]["180"]["p"] > 1.5


def test_forms_ga4_measured():
    hs, S = date(2026, 1, 1), date(2026, 10, 7)
    P = _P(hs, S)
    rows = rb._cohorts(P, _spend(hs, S, lambda X: 50), lambda d: 1.0, None, S)   # Google Ads count: s = 0.5
    w7 = rb._win(rows, T.index(7))
    gp = {"share": {r["X"].isoformat(): 0.8 for r in w7},
          "prem": {"7": {"p": 1.5, "s": 0.79, "rs": 0.85, "np": 4000, "no": 1000, "w": 4, "from": "2026-08-24",
                         "to": "2026-09-14"}}}
    f = rb._forms(rows, 90, None, gp)
    e = f["by"]["7"]
    assert e["src"] == "ga4" and e["s"] == 0.5 and e["m"]["sw"] == 0.8 and e["m"]["p"] == 1.5 and e["m"]["days"] == 7
    paid = round(e["bl"] * 1.5 * 0.8 / (1.5 * 0.8 + 0.2), 4)
    assert e["paid"] == [paid] * 3 and e["gap"][0] == e["gap"][2]   # measured: one number, no premium range
    assert e["inc"][0] < e["inc"][1] < e["inc"][2]                  # b and beta stay ranges
    assert e["mar"][1] == pytest.approx(e["inc"][1] * (1 + rb.F4_BETA[1]), abs=2e-4)
    assert f["by"]["30"]["src"] == "range" and "m" not in f["by"]["30"]   # no measured premium at D30: the range
    assert f["by"]["30"]["paid"][0] < f["by"]["30"]["paid"][2]
    # the window's GA4 paid share from fewer than half its days: the range, never a share of other days
    few = dict(gp, share={r["X"].isoformat(): 0.8 for r in w7[:3]})
    assert rb._forms(rows, 90, None, few)["by"]["7"]["src"] == "range"
    # no Google Ads install count, but GA4 measured both: the measured forms; nothing measured: blended only
    bare = rb._cohorts(P, _spend(hs, S, lambda X: None), lambda d: 1.0, None, S)
    fb = rb._forms(bare, 90, None, gp)
    assert fb["by"]["7"]["src"] == "ga4" and "s" not in fb["by"]["7"] and "src" not in fb["by"]["30"]


def test_life_and_countries():
    rev = {"till": "2026-10-13", "days": {"2026-10-01": [5_000_000, 1], "2026-10-02": [7_000_000, 1]},
           "all_days": {"2026-10-01": [6_000_000, 1], "2026-10-02": [8_000_000, 1]}}
    spend = {"daily": {"2026-09-30": 3_000_000, "2026-10-02": 2_000_000}, "till": "2026-10-02"}
    life = rb._life(rev, spend, lambda d: 0.5, 0.1)
    assert life == [["2026-09-30", 0, 1.5, 3.0], ["2026-10-01", 5.4, 0, 0], ["2026-10-02", 7.2, 1.0, 2.0]]   # all sources,
    # −10% deduction; spend in USD at that day's rate and as billed
    assert rb._life_till(rev, spend) == "2026-10-02"
    det = {"countries": {"win": {"weeks": 4}, "rows": [
        {"cc": "AA", "verdict": "keep", "sure": True, "pay": {"p": 20}, "cpi": {"v": 0.1, "spend": 100.0},
         "back": {"7": 60.0, "30": 110.0, "90": 150.0}, "rpi": {"90": {"v": 0.15}}, "n": 1000},
        {"cc": "BB", "verdict": "keep", "sure": False, "pay": {"p": 20}, "cpi": {"v": 0.1, "spend": 50.0}, "n": 10},
        {"cc": "CC", "verdict": "costly", "pay": {"never": True}, "cpi": {"v": 0.5, "spend": 200.0},
         "back": {"90": 20.0}, "rpi": {"90": {"v": 0.1}}, "n": 400},
        {"cc": "DD", "verdict": "few", "cpi": {}, "n": 5}, {"cc": "EE", "verdict": "slow", "n": 50}]}}
    c = rb._countries(det, 90)
    assert [x["dec"] for x in c["rows"]] == ["Scale", "Keep", "Cut", "Too little data", "Watch"]
    assert c["cut"] == {"n": 1, "spend": 200.0, "spend_src": 0.0, "rev90": 40.0, "spend_all": 350.0, "weeks": 4}


def test_finish_pointer_header_and_isolation(tmp_path):
    out = str(tmp_path)
    open(os.path.join(out, "roi_0123456789ab.json.gz"), "w").close()      # a stale app file
    acc = rb.start()
    rb.app_step(acc, {"history_start": "bad"}, {"app_id": "x~1", "app_name": "Broken"}, "k", None,
                {"data_dir": out}, {}, out, out)                        # a failing app: counted, never raised
    assert acc.fails + acc.skipped == 1 and not acc.apps
    f4 = {"h": 90, "by": {"30": {"bl": 0.5, "s": 0.5}}, "dec": {"a": 90, "v": "early", "mar": None}}
    acc.apps.append({"app_id": "a~1", "app": "Alpha", "key": "aaaaaaaaaaaa", "file": "roi_aaaaaaaaaaaa.json.gz",
                     "st": "Worse", "r7": 0.4, "u7": 0.6, "pb": 40, "life": [10.0, 12.0], "cut": 2, "f4": f4})
    open(os.path.join(out, "roi_aaaaaaaaaaaa.json.gz"), "w").close()
    acc.life = {"2026-10-01": [5.0, 6.0, 500.0]}
    acc.rows = {"2026-10-01": {"n": 10, "sp": 6.0, "spi": 500.0, "s": 4.0, "t": [1.0] * 10, "ok": [True] + [False] * 9,
                               "apps": 1}}
    acc.ccy = {"INR"}
    acc.till = ["2026-10-01", "2026-10-01", "2026-09-01"]
    dash = {"roi": {"old": 1}}
    assert rb.finish(acc, dash, out) == ["/roi*"]
    p = dash["roi"]
    assert p["ccy"] == "INR"
    assert p["file"] == "roi.json.gz" and p["apps"]["a~1"] == {"file": "roi_aaaaaaaaaaaa.json.gz", "st": "Worse",
                                                                "r7": 0.4, "u7": 0.6, "pb": 40, "nb": None,
                                                                "life": [10.0, 12.0], "cut": 2, "fc": None}
    with gzip.open(os.path.join(out, "roi.json.gz"), "rt") as f:
        body = json.load(f)
    assert body["rows"][0][3][:2] == [1.0, None] and body["life_till"] == "2026-10-01"
    assert body["rows"][0][5] == 500.0 and body["rows"][0][6] == 4.0 and body["months"][0][6] == 500.0
    assert body["ccy"] == "INR"
    assert body["apps"][0]["f4"] == f4 and body["f4c"] == rb.f4_consts()
    assert body["f4c"]["p"][0] < body["f4c"]["p"][1] < body["f4c"]["p"][2] and body["f4c"]["pa"] in body["f4c"]["ages"]
    assert body["months"][0][0] == "2026-10"
    assert not os.path.exists(os.path.join(out, "roi_0123456789ab.json.gz"))   # stale file removed
    line = rb.pop_line()
    assert line.startswith("roi: apps 1, worse 1") and "Alpha" not in line
    acc2 = rb.start()
    dash2 = {}
    assert rb.finish(acc2, dash2, out) == [] and "roi" not in dash2
    assert not any(f.startswith("roi") for f in os.listdir(out))
    assert rb.enabled({}) and not rb.enabled({"roi_tab": False})


# ── past D30 every 30 days (the late read, fetch.ga4_cohort's late store) ───────────────────────────────────────────
LHS, LS, LTODAY = date(2026, 4, 1), date(2026, 10, 7), date(2026, 10, 13)
KSW = date(2026, 8, 1)                                  # the scale k: 2 before, 3 from this activity day on


def _late_setup(tmp_path, holes=(), oth=None, stream="222", read_till=LTODAY, loss=(), done=True):
    """An app from LHS: install-day checkpoints (R[30] = $62), the exact store for the last 100 install days ($0.50 GA4 a
    day), and the late store: every install day earns $0.01 GA4 on every activity day ≥ 31 days after it, every day
    read from LHS + 31 to today except `holes`; `oth`: {day: (other micros, day total micros)}; `loss`: days of a
    block GA4 flagged. The late cursor (next) as fetch.ga4_cohort leaves it after a read on read_till."""
    from admob_iq.fetch import ga4_cohort as gco
    P = _P(LHS, LS)
    P["sc"]["kf"] = lambda d: ((2.0 if d < KSW else 3.0), "ok", False, 2.0)
    co = {"read_today": LTODAY.isoformat(), "stream_id": "222", "x": {},
          "late": {"from": (LHS + timedelta(days=31)).isoformat(),
                   "next": (read_till - timedelta(days=gco.FINAL_LAG - 1)).isoformat(), "done": done,
                   "read_till": read_till.isoformat()}}
    for i in range(100):
        X = LTODAY - timedelta(days=i)
        co["x"][X.isoformat()] = {"r": [500000] * 31, "u": [100 - L for L in range(31)]}
    lt = gco.Late(str(tmp_path), "a~1", stream)
    got, first = {"d": {}, "oth": {}, "t": {}}, LHS + timedelta(days=31)
    D = first
    while D <= LTODAY:
        k = D.isoformat()
        got["d"][k] = {}
        X = LHS
        while X <= D - timedelta(days=31):
            got["d"][k][X.isoformat()] = 10000
            X += timedelta(days=1)
        if oth and D in oth:
            got["oth"][k], got["t"][k] = oth[D]
        D += timedelta(days=1)
    a = first
    for h in sorted(holes) + [LTODAY + timedelta(days=1)]:
        if a <= h - timedelta(days=1):
            lt.put(got, a, h - timedelta(days=1))
        a = h + timedelta(days=1)
    for D in sorted(loss):                              # the same day read again in a block GA4 flagged
        lt.put(dict(got, loss=True), D, D)
    lt.save()
    return P, co


def _rows(P, co, late, spend=None):
    by = {r["X"]: r for r in rb._cohorts(P, spend, lambda d: 1.0, co, LTODAY, late)}
    return by


def test_late_buckets_scale_base_finality(tmp_path):
    P, co = _late_setup(tmp_path)
    late = rb._late(str(tmp_path), "a~1", co, P)
    assert late["info"] == {"days": (LTODAY - LHS).days - 30, "oth": 0, "omax": 0.0, "loss": 0, "from": "2026-05-02",
                            "till": "2026-10-13"} and late["C"] == date(2026, 10, 10)
    by = _rows(P, co, late)
    old = by[LHS]                       # no exact cells: base = its D30 checkpoint ($62); every bucket = 30 days × $0.01 × k
    assert old["d"] is None and old["t"][T.index(30)] == 62.0
    assert old["m"] == [62.6, 63.2, 63.8, 64.69, 65.59]       # bucket 4 (Jul 31 … Aug 29): 1 day at k 2, 29 at k 3
    assert old["mf"] == 5 and not old["qo"]                    # day 180 = Sep 28: whole and final; day 210 not read yet
    mid = by[date(2026, 7, 10)]          # exact store final through day 30: base = d[30] (22 days × k 2 + 9 × k 3)
    assert mid["df"] == 31 and mid["d"][30] == 35.5 and mid["m"] == [36.4, 37.3] and mid["mf"] == 2
    edge = by[date(2026, 7, 15)]         # its day 90 = Oct 13: read, not final yet (final edge = read_till − 3)
    assert edge["m"] == [round(edge["d"][30] + 0.9, 4), round(edge["d"][30] + 1.8, 4)] and edge["mf"] == 1
    assert date(2026, 8, 20) in by and "m" not in by[date(2026, 8, 20)]   # 54 days old: no whole 30-day bucket
    # the late read's own final edge (its cursor): an older read makes fewer columns final
    P2, co2 = _late_setup(tmp_path / "b", read_till=date(2026, 10, 1))
    assert _rows(P2, co2, rb._late(str(tmp_path / "b"), "a~1", co2, P2))[LHS]["mf"] == 5   # Sep 28 ≤ Sep 28
    assert _rows(P2, co2, rb._late(str(tmp_path / "b"), "a~1", co2, P2))[date(2026, 7, 10)]["mf"] == 1


def test_late_holes_stop_the_columns(tmp_path):
    P, co = _late_setup(tmp_path, holes={date(2026, 6, 15)})
    by = _rows(P, co, rb._late(str(tmp_path), "a~1", co, P))
    assert by[LHS]["m"] == [62.6]                              # bucket 2 (Jun 1 … 30) has a day never read: stops there
    assert "m" not in by[date(2026, 5, 1)]                     # its bucket 1 (Jun 1 … 30): no column at all
    assert by[date(2026, 5, 16)]["m"][0] == 62.6 and len(by[date(2026, 5, 16)]["m"]) == 4   # buckets after the hole


def test_late_so_far_breakeven_and_other(tmp_path):
    oth = {date(2026, 9, 20): (50000, 2000000)}               # 2.5% of that day's revenue GA4 gave no install day
    P, co = _late_setup(tmp_path, oth=oth)
    young = date(2026, 8, 4)                                  # exact store, no install-day checkpoint row
    P["xs"].pop(young)
    late = rb._late(str(tmp_path), "a~1", co, P)
    assert late["info"]["oth"] == 1 and late["info"]["omax"] == 0.025
    sp = {"ccy": "USD", "daily": {LHS.isoformat(): 63_000_000}, "installs": {}, "first": LHS.isoformat(),
          "till": LTODAY.isoformat()}
    by, base = _rows(P, co, late, sp), _rows(P, co, None, sp)
    # breakeven: $63 spent; D30 $62 → the first 30-day column ≥ $63 is D90 ($63.20), "≤ day 90" — not the
    # install-day checkpoint D60 ($122) the row without late columns uses
    assert by[LHS]["be"] == [90, False] and base[LHS]["be"] == [60, False]
    # so far: the furthest read — m's D60 (Oct 3) beats the exact store's day 30 (Sep 3)
    y = by[young]
    assert y["d"][30] == 46.5 and y["m"] == [47.4] and (y["s"], y["sd"]) == (47.4, "2026-10-03")
    assert (base[young]["s"], base[young]["sd"]) == (46.5, "2026-09-03")
    assert (by[LHS]["s"], by[LHS]["sd"]) == (base[LHS]["s"], base[LHS]["sd"])   # the install-day read reaches further
    # ≈: a row whose columns use Sep 20; a row whose columns end before it (Jul 18: through Sep 16) does not
    assert by[LHS]["qo"] and by[young]["qo"] and not by[date(2026, 7, 18)]["qo"]
    assert rb._row_out(by[LHS])[12] == 2 and rb._row_out(dict(by[LHS], q=True))[12] == 3
    assert rb._row_out(by[date(2026, 7, 18)])[12] == 0


def test_late_flagged_block_and_small_other_share(tmp_path):
    """A block GA4 flagged (data loss / thresholding / sampling / cut): q bit 4 on a row whose columns use one of its
    days, counted in the file's note; a tiny "(other)" share keeps its digits (never printed as 0.0%)."""
    P, co = _late_setup(tmp_path, loss={date(2026, 9, 20), date(2026, 9, 21)},
                        oth={date(2026, 9, 25): (30, 1_000_000)})                  # 0.003% of that day
    late = rb._late(str(tmp_path), "a~1", co, P)
    assert late["info"]["loss"] == 2 and late["info"]["oth"] == 1 and late["info"]["omax"] == 3e-05
    by = _rows(P, co, late)
    assert by[LHS]["qo"] == 6 and rb._row_out(by[LHS])[12] == 6 and rb._row_out(dict(by[LHS], q=True))[12] == 7
    assert by[date(2026, 7, 18)]["qo"] == 0                    # its columns end Sep 16
    j = date(2026, 7, 22)                                      # columns through Sep 20 (loss), not Sep 25 (other)
    assert by[j]["qo"] == 4 and rb._row_out(by[j])[12] == 4


def test_late_cursor_is_the_final_edge(tmp_path):
    """Days read while still filling (on or after the cursor) never count final, however late read_till is: after a
    gap the cursor waits for their re-read."""
    P, co = _late_setup(tmp_path)
    co["late"]["next"] = "2026-09-20"                          # e.g. a pause: Sep 20 … read only while filling
    late = rb._late(str(tmp_path), "a~1", co, P)
    assert late["C"] == date(2026, 9, 19)
    by = _rows(P, co, late)
    assert by[LHS]["mf"] == 4 and len(by[LHS]["m"]) == 5       # day 180 = Sep 28: read, not final
    assert by[date(2026, 6, 25)]["m"][1] and by[date(2026, 6, 25)]["mf"] == 1   # day 90 = Sep 23: the same
    co["late"].pop("next")
    assert rb._late(str(tmp_path), "a~1", co, P)["C"] is None    # no cursor: nothing final


def test_late_so_far_past_the_install_day_read(tmp_path):
    """An install day older than a year: the install-day read stops at day 365, m goes on to the app's age."""
    from admob_iq.fetch import ga4_cohort as gco
    hs, S, today = date(2025, 1, 1), date(2026, 10, 7), date(2026, 10, 13)
    P = _P(hs, S)
    co = {"read_today": today.isoformat(), "stream_id": "222", "x": {},
          "late": {"next": "2026-10-11", "done": True, "read_till": today.isoformat()}}
    lt = gco.Late(str(tmp_path), "a~1", "222")
    got, D = {"d": {}, "oth": {}, "t": {}}, hs + timedelta(days=31)
    while D <= today:
        got["d"][D.isoformat()] = {hs.isoformat(): 10000}     # only the first install day earns past day 30
        D += timedelta(days=1)
    lt.put(got, hs + timedelta(days=31), today)
    lt.save()
    by = {r["X"]: r for r in rb._cohorts(P, None, lambda d: 1.0, co, today, rb._late(str(tmp_path), "a~1", co, P))}
    r = by[hs]
    assert len(r["m"]) == 20 and r["m"][-1] == 62 + 20 * 0.6                # D60 … D630 (650 days old today)
    assert r["sd"] == (hs + timedelta(days=630)).isoformat() and r["s"] == r["m"][-1]   # past the read's day 365
    other = by[date(2025, 6, 1)]                               # m to D480 (Sep 24 2026) beats its read's day 365
    assert other["m"][-1] == 62.0 and other["sd"] == "2026-09-24"


def test_without_a_late_store_nothing_changes(tmp_path):
    P, co = _late_setup(tmp_path)
    assert rb._late(str(tmp_path / "none"), "a~1", co, P) is None              # no late files
    P0, co0 = _late_setup(tmp_path / "half", done=False)                      # its first read not through yet
    assert rb._late(str(tmp_path / "half"), "a~1", co0, P0) is None
    assert rb._late(str(tmp_path), "a~1", dict(co, stream_id="999"), P) is None   # another stream's files
    assert rb._late(str(tmp_path), "a~1", None, P) is None
    sp = {"ccy": "USD", "daily": {LHS.isoformat(): 63_000_000}, "installs": {}, "first": LHS.isoformat(),
          "till": LTODAY.isoformat()}
    plain = rb._cohorts(P, sp, lambda d: 1.0, co, LTODAY)
    assert plain == rb._cohorts(P, sp, lambda d: 1.0, co, LTODAY, None)
    assert not any("m" in r or "qo" in r for r in plain) and {len(rb._row_out(r)) for r in plain} == {14}
    # with the late store: a row it does not reach is exactly the row without it; a row it reaches only gains fields
    late = rb._late(str(tmp_path), "a~1", co, P)
    with_late = rb._cohorts(P, sp, lambda d: 1.0, co, LTODAY, late)
    for a, b in zip(plain, with_late):
        if "m" not in b:
            assert json.dumps(rb._row_out(a), default=str) == json.dumps(rb._row_out(b), default=str)
        else:
            assert rb._row_out(b)[:8] == rb._row_out(a)[:8]            # X … t as before; so far / breakeven via m
            assert rb._row_out(b)[14:] == [b["m"], b["mf"]] and len(rb._row_out(b)) == 16


def _stub_app(monkeypatch, P, co):
    """app_step on made-up inputs: the install-day file, the engine's prep, the exact store; no spend, no forecast."""
    from admob_iq import forecast_build, value_build
    from admob_iq.engine import value as val
    monkeypatch.setattr(value_build, "load_iday", lambda d, aid: {})
    monkeypatch.setattr(val, "settled_day", lambda ida, hs: P["S"])
    monkeypatch.setattr(val, "_prep", lambda store, ida, rev, ded, S: P)
    monkeypatch.setattr(value_build, "app_spend", lambda pre, a, store: None)
    monkeypatch.setattr(rb.gco, "load_store", lambda d, aid: co)

    def no_fc(*a, **k):
        raise RuntimeError("no forecast in this test")
    monkeypatch.setattr(forecast_build, "start", no_fc)


def test_app_step_late_block(tmp_path, monkeypatch):
    P, co = _late_setup(tmp_path / "data")
    _stub_app(monkeypatch, P, co)
    store, a = {"history_start": LHS.isoformat(), "stream_id": "222"}, {"app_id": "a~1", "app_name": "Alpha"}

    def run(data, out, on=True):
        os.makedirs(out, exist_ok=True)
        acc = rb.start(late=on)
        rb.app_step(acc, store, a, "aaaaaaaaaaaa", None, {}, {}, out, data)
        assert not acc.fails and len(acc.apps) == 1
        with gzip.open(os.path.join(out, "roi_aaaaaaaaaaaa.json.gz"), "rt") as f:
            return json.load(f)
    plain = run(str(tmp_path / "empty"), str(tmp_path / "o1"))           # no late store: no block, 14 fields a row
    assert "late" not in plain and {len(r) for r in plain["rows"]} == {14}
    full = run(str(tmp_path / "data"), str(tmp_path / "o2"))
    assert full["late"] == {"days": (LTODAY - LHS).days - 30, "oth": 0, "omax": 0.0, "loss": 0, "from": "2026-05-02",
                            "till": "2026-10-13"}
    # GA4_COHORT_LATE off (the late files still on disk): the file byte for byte as without a late store
    run(str(tmp_path / "data"), str(tmp_path / "o3"), on=False)
    with open(os.path.join(tmp_path, "o1", "roi_aaaaaaaaaaaa.json.gz"), "rb") as f1, \
            open(os.path.join(tmp_path, "o3", "roi_aaaaaaaaaaaa.json.gz"), "rb") as f3:
        assert gzip.decompress(f1.read()) == gzip.decompress(f3.read())
    lens = {len(r) for r in full["rows"]}
    assert lens == {14, 16} and full["rows"][0][14] == [62.6, 63.2, 63.8, 64.69, 65.59] and full["rows"][0][15] == 5
    # every other part of the file as without the late store
    assert {k: v for k, v in full.items() if k not in ("rows", "late")} == {k: v for k, v in plain.items() if k != "rows"}
    assert [r[:8] + r[10:14] for r in full["rows"]] == [r[:8] + r[10:14] for r in plain["rows"]]   # no spend: no be
