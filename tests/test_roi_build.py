"""📈 ROI (a section of the 💸 Install value tab) — the build step (admob_iq.roi_build), on made-up data: every install day
with its day-by-day revenue (the exact store × the engine's scale k), the checkpoints only when complete, the breakeven
day, the status vs usual, install months (one set of days per curve: never dips), payback from the newest month, the
lifetime P/L days, the countries board (Scale / Keep / Watch / Cut …) and what cutting saves, the four forms of ROI
(blended / paid-only / incremental / marginal as ranges, the paid share, the budget call; GA4's measured paid share and
premium from the paid cells once they cover an age), the portfolio file, the
pointer, one splat header rule, failure isolation and a counts-only line. Past D30 (the cohort cube, fetch.ga4_cube):
30-day buckets from the cube's "b" × the weekly k of each activity week, the base (d[30] or the D30 checkpoint), holes
stop the columns (a day neither folded nor hot), finality (folded) vs a hot day, breakeven / so far through them, ≈ from
the cube's measured loss (q bit 2) and from a day GA4 flagged (q bit 4), before the cube's walk first reached the final
edge (done) only the page's "on its way" note, and without a cube, with the switch off (GA4_CUBE) or another stream's
cube every byte of the file as the build made it before the 30-day columns existed (a fixed digest of it). 🌍 By country
(the cube's "e" / "c" through _late's one pass): every install day of every country, each country's AdMob ÷ GA4 per
activity month (own / pooled ±2 / clamped / ≈ / the app's k + its share), Google Ads by country × day (unknown days
null, "XX" → "Not split"), zero days written [X] exactly as the page expands them, holes, loss / flag bits, the packs
(deterministic, every country in one, a big one alone), the file without the cube / with the switch off byte for byte,
failure isolation, stale packs removed, the counts-only line; and build_static's AdMob country months (every month).
"""
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


# ── past D30 every 30 days (the cohort cube, fetch.ga4_cube) ─────────────────────────────────────────────────────────
LHS, LS, LTODAY = date(2026, 4, 1), date(2026, 10, 7), date(2026, 10, 13)
KSW = date(2026, 8, 3)                                  # the scale k (weekly): 2 before this week, 3 from it on


def _mon(d):
    return d - timedelta(days=d.weekday())


def _kf(d):
    return (2.0 if _mon(d) < KSW else 3.0), "ok", False, 2.0


def _cube_setup(tmp_path, holes=(), loss=None, flags=(), stream="222", hot_from=LTODAY - timedelta(days=2), done=True,
                hs=LHS, today=LTODAY, earners=None):
    """An app from hs: install-day checkpoints (R[30] = $62), the exact store for the last 100 install days ($0.50 GA4 a
    day) and the cube: every install day (or only `earners`) earns $0.01 GA4 on every activity day ≥ 31 days after it,
    every activity day hs … today folded (before hot_from) or hot (from it), except `holes`; `loss`: {day: (loss
    micros, day total micros)}; `flags`: days GA4 flagged."""
    from admob_iq.fetch import ga4_cube as cu
    P = _P(hs, LS if hs == LHS else today - timedelta(days=6))
    P["sc"]["kf"] = _kf if hs == LHS else P["sc"]["kf"]
    co = {"read_today": today.isoformat(), "stream_id": "222", "x": {}}
    for i in range(100):
        X = today - timedelta(days=i)
        co["x"][X.isoformat()] = {"r": [500000] * 31, "u": [100 - L for L in range(31)]}
    cube = cu.Cube(str(tmp_path), "a~1", stream)
    D = hs
    while D <= today:
        b = {}
        for X in (sorted(earners) if earners is not None else (hs + timedelta(days=i) for i in range((D - hs).days + 1))):
            if (D - X).days >= 31:
                b[X.isoformat()] = {str(cu.bucket((D - X).days)): {_mon(D).isoformat(): 10000}}
        lo, tt = (loss or {}).get(D, (0, 10000 * len(b)))
        rec = {"st": "loss" if lo or D in flags else "ok", "rows": len(b), "loss": lo, "t": tt,
               "fl": 1 if D in flags else 0, "via": "block", "at": "2026-10-13T06:00:00Z", "b": b, "c": {}, "e": {}}
        if D not in holes:
            if D >= hot_from:
                cube.head["d"][D.isoformat()] = rec
            else:
                cube.fold(D, rec)
        D += timedelta(days=1)
    cube.save()
    cube.head.update(done=done, stream_id=stream, next=hot_from.isoformat())
    cube.save_head()
    return P, co


def _rows(P, co, late, spend=None):
    by = {r["X"]: r for r in rb._cohorts(P, spend, lambda d: 1.0, co, LTODAY, late)}
    return by


def test_cube_buckets_weekly_k_base_finality(tmp_path):
    P, co = _cube_setup(tmp_path)
    late = rb._late(str(tmp_path), "a~1", "222", P)
    assert late["info"] == {"days": (LTODAY - LHS).days + 1, "oth": 0, "omax": 0.0, "loss": 0, "from": "2026-04-01",
                            "till": "2026-10-13", "thru": "2026-10-13"}
    by = _rows(P, co, late)
    old = by[LHS]                       # no exact cells: base = its D30 checkpoint ($62); every bucket = 30 days × $0.01 × k
    assert old["d"] is None and old["t"][T.index(30)] == 62.0
    assert old["m"] == [62.6, 63.2, 63.8, 64.67, 65.57]       # bucket 4 (Jul 31 … Aug 29): 3 days in the week at k 2
    assert old["mf"] == 5 and not old["qo"]                    # day 180 = Sep 28: whole and folded; day 210 not there
    mid = by[date(2026, 7, 10)]          # exact store final through day 30: base = d[30] (24 days × k 2 + 7 × k 3)
    assert mid["df"] == 31 and mid["d"][30] == 34.5 and mid["m"] == [35.4, 36.3] and mid["mf"] == 2
    edge = by[date(2026, 7, 15)]         # its day 90 = Oct 13: a hot day — the column is there, not final yet
    assert edge["m"] == [round(edge["d"][30] + 0.9, 4), round(edge["d"][30] + 1.8, 4)] and edge["mf"] == 1
    assert date(2026, 8, 20) in by and "m" not in by[date(2026, 8, 20)]   # 54 days old: no whole 30-day bucket
    # the k of each activity WEEK (kf at its Monday W, as the cube keys it): a k that moved mid-week (Wed Aug 5) counts
    # from the next week on — Jul 31 … Aug 9 at k 2, Aug 10 … 29 at k 3 (by the day it would be 64.65)
    P["sc"]["kf"] = lambda d: ((2.0 if d < date(2026, 8, 5) else 3.0), "ok", False, 2.0)
    assert _rows(P, co, rb._late(str(tmp_path), "a~1", "222", P))[LHS]["m"][3] == 64.6


def test_cube_holes_stop_the_columns(tmp_path):
    P, co = _cube_setup(tmp_path, holes={date(2026, 6, 15)})
    late = rb._late(str(tmp_path), "a~1", "222", P)
    assert late["info"]["thru"] == "2026-06-14" and late["info"]["till"] == "2026-10-13"   # the page says how far
    by = _rows(P, co, late)
    assert by[LHS]["m"] == [62.6]                              # bucket 2 (Jun 1 … 30) has a day not in the cube
    assert "m" not in by[date(2026, 5, 1)]                     # its bucket 1 (Jun 1 … 30): no column at all
    assert by[date(2026, 5, 16)]["m"] == [62.6, 63.32, 64.22, 65.12]   # buckets after the hole, the last one hot
    assert by[date(2026, 5, 16)]["mf"] == 3


def test_cube_hot_days_and_an_unfolded_gap(tmp_path):
    """A hot day (read while not final) fills a column but never makes it final; a gap the walk has not folded yet
    (a pause, a Stop) is a hole until it is."""
    P, co = _cube_setup(tmp_path / "a", hot_from=date(2026, 10, 1))
    by = _rows(P, co, rb._late(str(tmp_path / "a"), "a~1", "222", P))
    assert by[date(2026, 7, 3)]["m"][1] and by[date(2026, 7, 3)]["mf"] == 1   # day 90 = Oct 1: hot
    assert by[LHS]["mf"] == 5
    gap = {date(2026, 9, 20) + timedelta(days=i) for i in range(21)}           # Sep 20 … Oct 10 not folded yet
    P2, co2 = _cube_setup(tmp_path / "b", holes=gap)
    late2 = rb._late(str(tmp_path / "b"), "a~1", "222", P2)
    assert late2["info"]["thru"] == "2026-09-19" and late2["info"]["till"] == "2026-10-13"
    by2 = _rows(P2, co2, late2)
    assert by2[LHS]["m"] == [62.6, 63.2, 63.8, 64.67] and by2[LHS]["mf"] == 4    # day 180 (… Sep 28): a hole
    assert by2[date(2026, 7, 15)]["m"] == [round(by2[date(2026, 7, 15)]["d"][30] + 0.9, 4)]


def test_cube_so_far_breakeven_and_loss(tmp_path):
    loss = {date(2026, 9, 20): (50000, 2000000)}              # 2.5% of that day's revenue stayed "(other)"
    P, co = _cube_setup(tmp_path, loss=loss)
    young = date(2026, 8, 4)                                  # exact store, no install-day checkpoint row
    P["xs"].pop(young)
    late = rb._late(str(tmp_path), "a~1", "222", P)
    assert late["info"]["oth"] == 1 and late["info"]["omax"] == 0.025
    sp = {"ccy": "USD", "daily": {LHS.isoformat(): 63_000_000}, "installs": {}, "first": LHS.isoformat(),
          "till": LTODAY.isoformat()}
    by, base = _rows(P, co, late, sp), _rows(P, co, None, sp)
    # breakeven: $63 spent; D30 $62 → the first 30-day column ≥ $63 is D90 ($63.20), "≤ day 90" — not the
    # install-day checkpoint D60 ($122) the row without the columns uses
    assert by[LHS]["be"] == [90, False] and base[LHS]["be"] == [60, False]
    # so far: the furthest read — m's D60 (Oct 3) beats the exact store's day 30 (Sep 3)
    y = by[young]
    assert y["d"][30] == 46.5 and y["m"] == [47.4] and (y["s"], y["sd"]) == (47.4, "2026-10-03")
    assert (base[young]["s"], base[young]["sd"]) == (46.5, "2026-09-03")
    assert (by[LHS]["s"], by[LHS]["sd"]) == (base[LHS]["s"], base[LHS]["sd"])   # the install-day read reaches further
    # ≈: a row whose columns use Sep 20; a row whose columns end before it (Jul 18: through Sep 16) does not
    assert by[LHS]["qo"] == 2 and by[young]["qo"] == 2 and not by[date(2026, 7, 18)]["qo"]
    assert rb._row_out(by[LHS])[12] == 2 and rb._row_out(dict(by[LHS], q=True))[12] == 3
    assert rb._row_out(by[date(2026, 7, 18)])[12] == 0


def test_cube_breakeven_by_age_checkpoints_through_d30_first(tmp_path):
    """A row with no exact cells (its D0 … D30 from the install-day checkpoints) that got its spend back by D7 / D14 /
    D30: breakeven at that checkpoint, as without the columns — never "≤ day 60" from the first 30-day column; past
    the columns, the checkpoints after them."""
    P, co = _cube_setup(tmp_path)
    late = rb._late(str(tmp_path), "a~1", "222", P)
    for spend, want in ((15.0, 7), (16.0, 7), (30.0, 14), (50.0, 30), (62.0, 30), (62.5, 60), (63.0, 90)):
        sp = {"ccy": "USD", "daily": {LHS.isoformat(): int(spend * 1e6)}, "installs": {}, "first": LHS.isoformat(),
              "till": LTODAY.isoformat()}
        r, r0 = _rows(P, co, late, sp)[LHS], _rows(P, co, None, sp)[LHS]
        assert r["d"] is None and r["m"][0] == 62.6
        assert r["be"] == [want, False], spend
        if want <= 30:
            assert r0["be"] == r["be"]                     # the same as the build without the columns
    # a spend past every 30-day column: the checkpoints after the last one (here D60 only — a hole stops the rest —
    # so the D90 checkpoint, $182; the D60 checkpoint is the column's age, the column wins there)
    P2, co2 = _cube_setup(tmp_path / "h", holes={date(2026, 6, 15)})
    sp = {"ccy": "USD", "daily": {LHS.isoformat(): 100_000_000}, "installs": {}, "first": LHS.isoformat(),
          "till": LTODAY.isoformat()}
    r = _rows(P2, co2, rb._late(str(tmp_path / "h"), "a~1", "222", P2), sp)[LHS]
    assert r["m"] == [62.6] and r["t"][T.index(60)] == 122.0 and r["be"] == [90, False]


def test_cube_flagged_days_and_small_loss_share(tmp_path):
    """Days GA4 flagged with nothing to measure it by: q bit 4 on a row whose columns use one of them, counted in the
    file's note; a tiny loss share keeps its digits (never printed as 0.0%)."""
    P, co = _cube_setup(tmp_path, flags={date(2026, 9, 20), date(2026, 9, 21)},
                        loss={date(2026, 9, 25): (30, 1_000_000)})             # 0.003% of that day
    late = rb._late(str(tmp_path), "a~1", "222", P)
    assert late["info"]["loss"] == 2 and late["info"]["oth"] == 1 and late["info"]["omax"] == 3e-05
    by = _rows(P, co, late)
    assert by[LHS]["qo"] == 6 and rb._row_out(by[LHS])[12] == 6 and rb._row_out(dict(by[LHS], q=True))[12] == 7
    assert by[date(2026, 7, 18)]["qo"] == 0                    # its columns end Sep 16
    j = date(2026, 7, 22)                                      # columns through Sep 20 (flagged), not Sep 25 (loss)
    assert by[j]["qo"] == 4 and rb._row_out(by[j])[12] == 4


def test_cube_so_far_past_the_install_day_read(tmp_path):
    """An install day older than a year: the install-day read stops at day 365, m goes on to the app's age."""
    hs, today = date(2025, 1, 1), date(2026, 10, 13)
    P, co = _cube_setup(tmp_path, hs=hs, today=today, earners={hs})            # only the first install day earns
    co["x"] = {}
    by = {r["X"]: r for r in rb._cohorts(P, None, lambda d: 1.0, co, today, rb._late(str(tmp_path), "a~1", "222", P))}
    r = by[hs]
    assert len(r["m"]) == 20 and r["m"][-1] == 62 + 20 * 0.6                # D60 … D630 (650 days old today)
    assert r["sd"] == (hs + timedelta(days=630)).isoformat() and r["s"] == r["m"][-1]   # past the read's day 365
    other = by[date(2025, 6, 1)]                               # m to D480 (Sep 24 2026) beats its read's day 365
    assert other["m"][-1] == 62.0 and other["sd"] == "2026-09-24"


def test_without_a_cube_nothing_changes(tmp_path):
    P, co = _cube_setup(tmp_path)
    assert rb._late(str(tmp_path / "none"), "a~1", "222", P) is None          # no cube
    P0, co0 = _cube_setup(tmp_path / "half", done=False)                      # its first walk not through yet: only
    assert rb._late(str(tmp_path / "half"), "a~1", "222", P0) == {"info": {"busy": 1, "from": None,   # the page's note
                                                                           "next": "2026-10-11"}}
    assert rb._late(str(tmp_path), "a~1", "999", P) is None                    # another stream's cube
    P1, co1 = _cube_setup(tmp_path / "other", stream="999")
    assert rb._late(str(tmp_path / "other"), "a~1", "222", P1) is None
    sp = {"ccy": "USD", "daily": {LHS.isoformat(): 63_000_000}, "installs": {}, "first": LHS.isoformat(),
          "till": LTODAY.isoformat()}
    plain = rb._cohorts(P, sp, lambda d: 1.0, co, LTODAY)
    assert plain == rb._cohorts(P, sp, lambda d: 1.0, co, LTODAY, None)
    assert not any("m" in r or "qo" in r for r in plain) and {len(rb._row_out(r)) for r in plain} == {14}
    # with the cube: a row it does not reach is exactly the row without it; a row it reaches only gains fields
    late = rb._late(str(tmp_path), "a~1", "222", P)
    with_late = rb._cohorts(P, sp, lambda d: 1.0, co, LTODAY, late)
    for a, b in zip(plain, with_late):
        if "m" not in b:
            assert json.dumps(rb._row_out(a), default=str) == json.dumps(rb._row_out(b), default=str)
        else:
            assert rb._row_out(b)[:8] == rb._row_out(a)[:8]            # X … t as before; so far / breakeven via m
            assert rb._row_out(b)[14:] == [b["m"], b["mf"]] and len(rb._row_out(b)) == 16


def _stub_app(monkeypatch, P, co, spend=None):
    """app_step on made-up inputs: the install-day file, the engine's prep, the exact store, `spend`; no forecast."""
    from admob_iq import forecast_build, value_build
    from admob_iq.engine import value as val
    monkeypatch.setattr(value_build, "load_iday", lambda d, aid: {})
    monkeypatch.setattr(val, "settled_day", lambda ida, hs: P["S"])
    monkeypatch.setattr(val, "_prep", lambda store, ida, rev, ded, S: P)
    monkeypatch.setattr(value_build, "app_spend", lambda pre, a, store: spend)
    monkeypatch.setattr(rb.gco, "load_store", lambda d, aid: co)

    def no_fc(*a, **k):
        raise RuntimeError("no forecast in this test")
    monkeypatch.setattr(forecast_build, "start", no_fc)


# sha256 of the decompressed roi_<key>.json.gz that the build at 8de0000 (before any 30-day column existed) wrote for
# _app_step_run's made-up app — worked out once by loading that commit's admob_iq/roi_build.py next to this tree
GOLDEN_8DE0000 = "2774546b3476f5a8b0b418225040ac4f1014ed531d0d71cafc073f569f8498bf"


def _app_step_run(data, out, cube):
    from admob_iq.fetch import ga4_cube as cu    # noqa: F401  (the build reads it only with the switch on)
    os.makedirs(out, exist_ok=True)
    acc = rb.start(cube=cube)
    store, a = {"history_start": LHS.isoformat(), "stream_id": "222"}, {"app_id": "a~1", "app_name": "Alpha"}
    rb.app_step(acc, store, a, "aaaaaaaaaaaa", None, {}, {}, out, data)
    assert not acc.fails and len(acc.apps) == 1
    with open(os.path.join(out, "roi_aaaaaaaaaaaa.json.gz"), "rb") as f:
        return gzip.decompress(f.read())


SPEND = {"ccy": "USD", "daily": {(LHS + timedelta(days=i)).isoformat(): (40 + i % 9) * 1_000_000 for i in range(0, 190)},
         "installs": {(LHS + timedelta(days=i)).isoformat(): 30 + i % 5 for i in range(0, 190)},
         "first": LHS.isoformat(), "till": LTODAY.isoformat(), "sids": 1}


def test_app_step_cube_block_and_byte_identical_without_it(tmp_path, monkeypatch):
    import hashlib
    P, co = _cube_setup(tmp_path / "data")
    _stub_app(monkeypatch, P, co, SPEND)
    plain = _app_step_run(str(tmp_path / "empty"), str(tmp_path / "o1"), True)      # switch on, no cube
    off = _app_step_run(str(tmp_path / "data"), str(tmp_path / "o3"), False)        # cube on disk, switch off
    from admob_iq.fetch import ga4_cube as cu
    h = cu.load_head(str(tmp_path / "data"), "a~1")
    cu.write_json_gz_stable(cu.hot_path(str(tmp_path / "data"), "a~1"), dict(h, stream_id="999"))
    other = _app_step_run(str(tmp_path / "data"), str(tmp_path / "o5"), True)      # another stream's cube
    # every one byte for byte the file the build wrote before the 30-day columns existed
    assert plain == off == other and hashlib.sha256(plain).hexdigest() == GOLDEN_8DE0000
    # the cube's first walk not through yet: no column, only the page's note of it (every other byte as without)
    cu.write_json_gz_stable(cu.hot_path(str(tmp_path / "data"), "a~1"), dict(h, done=False, **{"from": "2026-04-01"}))
    early = json.loads(_app_step_run(str(tmp_path / "data"), str(tmp_path / "o4"), True))
    assert early.pop("late") == {"busy": 1, "from": "2026-04-01", "next": "2026-10-11"} and early == json.loads(plain)
    cu.write_json_gz_stable(cu.hot_path(str(tmp_path / "data"), "a~1"), h)
    full = json.loads(_app_step_run(str(tmp_path / "data"), str(tmp_path / "o2"), True))
    plain = json.loads(plain)
    assert "late" not in plain and {len(r) for r in plain["rows"]} == {14}
    assert full["late"] == {"days": (LTODAY - LHS).days + 1, "oth": 0, "omax": 0.0, "loss": 0, "from": "2026-04-01",
                            "till": "2026-10-13", "thru": "2026-10-13"}
    lens = {len(r) for r in full["rows"]}
    assert lens == {14, 16} and full["rows"][0][14] == [62.6, 63.2, 63.8, 64.67, 65.57] and full["rows"][0][15] == 5
    # every other part of the file as without the cube but what the columns feed (so far, breakeven → the forms)
    assert [r[:8] + r[11:14] for r in full["rows"]] == [r[:8] + r[11:14] for r in plain["rows"]]
    assert {k for k in full if full[k] != plain.get(k)} <= {"rows", "late", "sum", "f4", "months"}
    assert full["months"] == plain["months"] and full["cty"] == plain["cty"] and full["life"] == plain["life"]


# ── 🌍 the install-day table by country (the cube's "e" / "c" × each country's own AdMob match) ──────────────────────
CHS, CTODAY = date(2026, 8, 1), date(2026, 10, 13)
CHOT = CTODAY - timedelta(days=2)                       # Oct 11 … 13 hot (read while not final), Oct 10 and before folded
CINST = {"AA": 40, "BB": 5, "CC": 3, "--": 2}          # installs a day by country (made-up codes)
CRATE = {"AA": 100000, "BB": 1000, "CC": 20000, "--": 10000}   # GA4 micros a day per install day, at every age


def _cc_cube(root, holes=(), loss=None, flags=(), inst=None, rate=None, only=None, done=True):
    """A cube from CHS to CTODAY where every install day X of a country earns rate[cc] on every activity day D ≥ X
    (ages 0 … 30 in "e", later in "c" and "b"); inst[cc] installs on each install day (only: {cc: the install days
    it has}); every day folded before CHOT, hot from it, except `holes`."""
    from admob_iq.fetch import ga4_cube as cu
    inst, rate, only = inst or CINST, rate or CRATE, only or {}
    cube = cu.Cube(str(root), "a~1", "222")
    D = CHS
    while D <= CTODAY:
        e, c, b, t = {}, {}, {}, 0
        for cc in inst:
            X = CHS
            while X <= D:
                if cc in only and X not in only[cc]:
                    X += timedelta(days=1)
                    continue
                L, v, k = (D - X).days, rate[cc], X.isoformat()
                if L <= 30:
                    e.setdefault(cc, {})[k] = [inst[cc] if L == 0 else 0] + [0] * L + [v]
                else:
                    j = str(cu.bucket(L))
                    c.setdefault(cc, {}).setdefault(k, {})[j] = v
                    w = b.setdefault(k, {}).setdefault(j, {})
                    w[_mon(D).isoformat()] = w.get(_mon(D).isoformat(), 0) + v
                t += v
                X += timedelta(days=1)
        lo = (loss or {}).get(D, 0)
        rec = {"st": "loss" if lo else "ok", "rows": 1, "loss": lo, "t": t + lo, "fl": 1 if D in flags else 0,
               "via": "block", "at": "2026-10-13T06:00:00Z", "b": b, "c": c, "e": e}
        if D not in holes:
            if D >= CHOT:
                cube.head["d"][D.isoformat()] = rec
            else:
                cube.fold(D, rec)
        D += timedelta(days=1)
    cube.save()
    cube.head.update(done=done, stream_id="222", next=CHOT.isoformat())
    cube.save_head()


def _ga4_month(cc, M, rate=None, only=None):
    """The made-up cube's GA4 micros of a country in an activity month (every install day ≥ CHS, every age)."""
    rate, tot, D = rate or CRATE, 0, max(CHS, date(int(M[:4]), int(M[5:]), 1))
    while D.isoformat()[:7] == M and D <= CTODAY:
        tot += rate[cc] * sum(1 for i in range((D - CHS).days + 1)
                              if not (only and cc in only) or CHS + timedelta(days=i) in only[cc])
        D += timedelta(days=1)
    return tot


def _cc_world(tmp_path, kmul=None, mask_off=(), geo_holes=(date(2026, 9, 15),), **kw):
    """The cube + AdMob by country × month (kmul[cc][month] × the country's GA4; whole months by default, the newest
    through Oct 12) + Google Ads by store × day × country (from Sep 1; a store-day in geo_holes has spend but no split)."""
    data = tmp_path / "data"
    _cc_cube(data, **kw)
    kmul = kmul if kmul is not None else {"AA": {"2026-08": 1.5, "2026-09": 1.0, "2026-10": 1.0},
                                          "CC": {"2026-08": 3.0, "2026-09": 3.0, "2026-10": 3.0}}
    m = {}
    for cc, ks in kmul.items():
        for M, k in ks.items():
            m.setdefault(M, {})[cc] = int(_ga4_month(cc, M, kw.get("rate"), kw.get("only")) * k)
    d = {"2026-08": (1 << 31) - 1, "2026-09": (1 << 30) - 1, "2026-10": (1 << 12) - 1}
    for M in mask_off:
        d[M] &= ~(1 << 9)                                    # day 10 has no row (and day 11 has one: a real hole)
        d[M] &= ~(1 << 10)
    cmon = {"m": {"a~1": m}, "d": {"a~1": d}}
    P = _P(CHS, CTODAY - timedelta(days=6))
    P["sc"]["kf"] = lambda d_: (1.2, "ok", False, 1.2)
    sdaily, geo = {}, {}
    X = CHS
    while X <= CTODAY - timedelta(days=1):
        k = X.isoformat()
        sdaily[k] = 10_000_000
        if X >= date(2026, 9, 1) and X not in geo_holes:
            geo[k] = {"AA": [6_000_000, 3.0], "BB": [2_000_000, None], "XX": [1_000_000, None], "DD": [1_000_000, 1.0]}
        X += timedelta(days=1)
    pre = {"spend": {"ccy": "USD", "daily": {"s1": sdaily}, "installs": {}, "first": CHS.isoformat(),
                     "till": (CTODAY - timedelta(days=1)).isoformat()},
           "owner": {"s1": "Alpha"}, "fx": None}
    spend = {"ccy": "USD", "daily": dict(sdaily), "installs": {}, "first": CHS.isoformat(),
             "till": (CTODAY - timedelta(days=1)).isoformat(), "sids": 1}
    acc = rb.start(cube=True, cmon=cmon)
    acc.geo = {"ccy": "USD", "days": {"s1": geo}}
    return data, P, pre, spend, acc


def _cc_run(tmp_path, data, P, pre, spend, acc, ded=None, out="out"):
    cv = rb._Cty(P["hs"])
    late = rb._late(str(data), "a~1", "222", P, visit=cv.visit)
    co = {"read_today": CTODAY.isoformat(), "stream_id": "222", "x": {}}
    rows = rb._cohorts(P, spend, lambda d_: 1.0, co, CTODAY, late)
    od = tmp_path / out
    od.mkdir(exist_ok=True)
    cd = rb._cty(acc, cv, late, P, rows, spend, pre, {"app_id": "a~1", "app_name": "Alpha"}, {"package": "p.q"},
                 {"tz": "America/Los_Angeles"}, ded, ["a~1"], "aaaaaaaaaaaa", str(od), str(data))
    return cd, od, rows


def _pack_rows(od, cd):
    out = {}
    for name, sha in cd["packs"]:
        import hashlib
        with gzip.open(os.path.join(str(od), name), "rb") as f:
            raw = f.read()
        body = json.loads(raw)
        assert hashlib.sha1(raw).hexdigest()[:12] == sha                       # the page's ?v= is its content
        assert raw == json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        assert body["v"] == 1 and body["key"] == "aaaaaaaaaaaa" and body["ix"] == cd["packs"].index([name, sha])
        for cc, rows in body["c"].items():
            assert cc not in out                                                # every country in exactly one pack
            out[cc] = rows
    return out


def _expand(rows, cd, cc):
    """The page's zx: a short [X] → the row (the same rule as rb._zrow)."""
    unk = set()
    for a, b in cd["geo"]["unk"]:
        d = date.fromisoformat(a)
        while d <= date.fromisoformat(b):
            unk.add(d)
            d += timedelta(days=1)
    out = []
    for r in rows:
        if len(r) == 1:
            X = date.fromisoformat(r[0])
            r = rb._row_out(rb._zrow(X, date.fromisoformat(cd["thru"]), date.fromisoformat(cd["fthru"]), X in unk, cc,
                                     bool(cd["geo"]["billed"])))
        out.append(r)
    return out


def test_country_rows_kc_per_month_and_spend(tmp_path):
    data, P, pre, spend, acc = _cc_world(tmp_path)
    cd, od, rows = _cc_run(tmp_path, data, P, pre, spend, acc)
    assert cd["v"] == 1 and cd["from"] == "2026-08-01" and cd["thru"] == "2026-10-13" and cd["fthru"] == "2026-10-10"
    got = _pack_rows(od, cd)
    assert set(got) == {"AA", "BB", "CC", "--", "DD", "XX"} == {x[0] for x in cd["c"]}
    # the index: installs desc, then spend, then code; every country its pack
    assert [x[0] for x in cd["c"]] == ["AA", "BB", "CC", "--", "DD", "XX"]
    c = {x[0]: x for x in cd["c"]}
    days = (CTODAY - CHS).days + 1
    assert c["AA"][1] == 40 * days and c["--"][1] == 2 * days and c["DD"][1] == 0 and c["XX"][1] is None
    AA = {r[0]: r for r in _expand(got["AA"], cd, "AA")}
    assert len(AA) == days and min(AA) == "2026-08-01" and max(AA) == "2026-10-13"        # every install day
    r = AA["2026-08-10"]                    # ages 0 … 21 in Aug (k_c 1.5), 22 … 30 in Sep (k_c 1.0): $0.10 a day GA4
    assert r[1] == 40 and r[4][21] == pytest.approx(22 * 0.15) and r[4][30] == pytest.approx(22 * 0.15 + 9 * 0.1)
    assert r[5] == 31 and r[7][T.index(7)] == pytest.approx(8 * 0.15) and r[7][T.index(30)] == r[4][30]
    # D60 from the cube's buckets × k_c of each activity month (Oct: no whole month of its own → pooled, Sep's 1.0)
    assert r[14] == [pytest.approx(4.2 + 3.0)] and r[15] == 1 and r[7][T.index(60)] == r[14][0]
    assert r[3] is None and r[13] is None                                   # Aug: Google Ads by country unknown → '—'
    s = AA["2026-09-10"]
    assert s[3] == 6.0 and s[13] == 6.0 and s[2] == 3.0                     # USD (rate 1), as billed, Ads downloads
    assert AA["2026-09-15"][3] is None                                      # a store spent, no committed split: '—'
    assert AA["2026-10-13"][3] is None                                      # after the spend cache: unknown
    # statuses on the country's own rows (≥ $5 and ≥ 30 installs judged), the same _statuses
    assert AA["2026-08-10"][11] == "N/A" and AA["2026-09-25"][11] in ("Normal", "Watch", "Better", "Worse")
    assert AA["2026-10-12"][11] == "Too early"
    # q: k_c 1.5 is outside 0.8 – 1.25 (bit 8); the Sep / Oct rows on a measured k inside it: none
    assert r[12] & 8 and not AA["2026-09-20"][12] & 8 and not AA["2026-09-20"][12] & 16
    # CC: AdMob 3× → clamped to 2.0 (≈); BB: too thin even pooled → the app's k (1.2, ≈, bit 16); "--": always the app's
    CC = {x[0]: x for x in _expand(got["CC"], cd, "CC")}
    assert CC["2026-09-05"][4][0] == pytest.approx(0.02 * 2.0) and CC["2026-09-05"][12] & 8
    BB = {x[0]: x for x in _expand(got["BB"], cd, "BB")}
    assert BB["2026-09-05"][4][0] == pytest.approx(0.001 * 1.2) and BB["2026-09-05"][12] & 16
    NC = {x[0]: x for x in _expand(got["--"], cd, "--")}
    assert NC["2026-09-05"][4][0] == pytest.approx(0.01 * 1.2) and NC["2026-09-05"][12] & 16
    assert NC["2026-09-05"][3] is None and c["--"][2] is None               # GA4's "(not set)": no Ads country
    assert c["--"][6] == 1.0 and c["BB"][6] == 1.0 and c["AA"][6] == 0.0
    assert BB["2026-09-05"][3] == 2.0 and BB["2026-09-05"][2] is None       # downloads unknown: null
    # an Ads-only country: its spend per day, no installs, no revenue
    DD = {x[0]: x for x in _expand(got["DD"], cd, "DD")}
    assert DD["2026-09-05"][1] == 0 and DD["2026-09-05"][3] == 1.0 and DD["2026-09-05"][8] == 0.0
    # "Not split": Google Ads' unmapped cost by install day, no revenue
    XX = {x[0]: x for x in _expand(got["XX"], cd, "XX")}
    assert XX["2026-09-05"][3] == 1.0 and XX["2026-09-05"][1] is None and XX["2026-09-05"][4] is None
    assert XX["2026-08-05"][3] is None and len(XX) == days
    # the index: k_c months, Google Ads coverage, the measured gap to the All row
    # own: AA Aug + Sep, CC Sep; pooled: Oct of AA / CC (partial), CC Aug ($9.92 GA4); the app's k: BB, "--" every month;
    # ≈ (measured, outside 0.8 – 1.25): AA Aug (1.5) and CC's three (3.0 → 2.0)
    assert {k: v for k, v in cd["kc"].items() if k != "tzh"} == {"own_months": 3, "pool_months": 3, "app_months": 6,
                                                                  "est_months": 4}
    assert cd["kc"]["tzh"] is not None                                    # AdMob's day vs GA4's (UTC here): measured
    g = cd["geo"]
    assert g["from"] == "2026-09-01" and g["till"] == "2026-10-12" and g["unknown_days"] == 31 + 1 + 1
    assert g["unk"] == [["2026-08-01", "2026-08-31"], ["2026-09-15", "2026-09-15"], ["2026-10-13", "2026-10-13"]]
    assert g["xx_share"] == round(1 / 10, 4) and g["cov"] == 1.0
    assert c["AA"][2] == pytest.approx(6.0 * (g["known_days"] - 0)) and c["XX"][2] == pytest.approx(1.0 * g["known_days"])
    assert cd["diff"]["age"] == 30 and cd["diff"]["days"] >= 1 and cd["diff"]["n_cty"] == cd["diff"]["days"] * 50


def test_country_kc_rules(tmp_path):
    lo, ok = rb.val.K_CLAMP, rb.val.K_OK
    months = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    appk = {M: 1.1 for M in months}
    G = {"AA": {M: 100e6 for M in months}, "BB": {M: 5e6 for M in months}, "--": {M: 100e6 for M in months},
         "CC": {M: 100e6 for M in months}}
    A = {"AA": {"2026-01": 90.0, "2026-02": 130.0, "2026-03": 300.0, "2026-04": 10.0, "2026-05": 100.0},
         "BB": {M: 5.0 for M in months}, "--": {M: 100.0 for M in months}, "CC": {M: 20.0 for M in months}}
    whole = set(months) - {"2026-06"}
    kc = rb._kc(G, A, whole, months, appk)
    a = kc["AA"]
    assert a["2026-01"] == (0.9, "own", False)                          # inside 0.8 – 1.25
    assert a["2026-02"] == (1.3, "own", True)                           # outside: ≈
    assert a["2026-03"] == (lo[1], "own", True)                         # 3.0 clamped to 2.0, ≈
    assert a["2026-04"] == (pytest.approx(410 / 300), "pool", True)     # AdMob $10 < $20: Mar … May pooled, ≈
    assert a["2026-06"] == (pytest.approx(1.0), "pool", False)          # not whole: the whole months ≤ ±1 (May)
    b = kc["BB"]                                                        # $5 a side: ±2 around Mar → $25 a side
    assert b["2026-03"] == (pytest.approx(1.0), "pool", False)
    assert b["2026-01"] == (1.1, "app", True)                           # Jan … Mar only $15 a side: the app's k
    assert kc["--"]["2026-02"] == (1.1, "app", True)                    # GA4's "(not set)": always the app's k
    assert kc["CC"]["2026-02"] == (lo[0], "own", True)                  # $20 a side: own month, 0.2 → 0.5
    thin = rb._kc({"EE": {M: 1e6 for M in months}}, {"EE": {M: 1.0 for M in months}}, whole, months, appk)
    assert all(v == (1.1, "app", True) for v in thin["EE"].values())   # never measurable: the app's k, ≈
    assert ok == (0.8, 1.25) and rb.KC_POOL == 2
    # the AdMob side: a month counts only when every day has a row (a one-day hole between rows: a real 0)
    full = (1 << 31) - 1
    assert rb._admob_whole({"2026-01": full}, "2026-01")
    assert rb._admob_whole({"2026-01": full & ~(1 << 4)}, "2026-01")        # day 5 alone: between two rows
    assert not rb._admob_whole({"2026-01": full & ~(3 << 4)}, "2026-01")    # days 5 – 6: not known
    assert not rb._admob_whole({"2026-01": full & ~(1 << 30)}, "2026-01")   # the last day, no next month's row
    assert rb._admob_whole({"2026-01": full & ~(1 << 30), "2026-02": 1}, "2026-01")
    A2, m2 = rb._admob_side({"m": {"x": {"2026-01": {"AA": 2_000_000}}, "y": {"2026-01": {"AA": 1_000_000}}},
                             "d": {"x": {"2026-01": 1}, "y": {"2026-01": 2}}}, ["x", "y"], 0.9)
    assert A2 == {"AA": {"2026-01": pytest.approx(2.7)}} and m2 == {"2026-01": 3}   # × (1 − deduction), ids summed


def test_country_month_cover_and_deduction(tmp_path):
    # Sep's AdMob report misses two days in a row: Sep is not whole → its k_c is pooled from Aug (1.5) and Oct
    # (partial: never); an Aug install day's ages in Sep then use 1.5 too
    data, P, pre, spend, acc = _cc_world(tmp_path, mask_off=("2026-09",))
    cd, od, _ = _cc_run(tmp_path, data, P, pre, spend, acc)
    AA = {r[0]: r for r in _expand(_pack_rows(od, cd)["AA"], cd, "AA")}
    assert AA["2026-08-10"][4][30] == pytest.approx(31 * 0.15)
    # the deduction scales AdMob (as the app's k): 1.5 × 0.8 = 1.2 in Aug (inside 0.8 – 1.25: no ≈ on Aug's days)
    data2, P2, pre2, spend2, acc2 = _cc_world(tmp_path / "d")
    cd2, od2, _ = _cc_run(tmp_path / "d", data2, P2, pre2, spend2, acc2, ded=0.2)
    AA2 = {r[0]: r for r in _expand(_pack_rows(od2, cd2)["AA"], cd2, "AA")}
    assert AA2["2026-08-10"][4][21] == pytest.approx(22 * 0.12) and not AA2["2026-08-10"][12] & 8


def test_country_zero_rows_short_and_holes(tmp_path):
    # EE: installs on two days only; every other day of it has nothing → [X], and the page's expansion is the row
    inst = dict(CINST, EE=3)
    rate = dict(CRATE, EE=50000)
    only = {"EE": {date(2026, 9, 5), date(2026, 9, 6)}}
    data, P, pre, spend, acc = _cc_world(tmp_path, inst=inst, rate=rate, only=only)
    cd, od, _ = _cc_run(tmp_path, data, P, pre, spend, acc)
    got = _pack_rows(od, cd)
    ee = got["EE"]
    days = (CTODAY - CHS).days + 1
    assert len(ee) == days and sum(len(r) == 1 for r in ee) == days - 2   # every day, the zero ones short
    full = {r[0]: r for r in _expand(ee, cd, "EE")}
    z = full["2026-08-10"]                                                # D60 = Oct 9: read and folded
    assert z[1] == 0 and z[4] == [0.0] * 31 and z[5] == 31 and z[14] == [0.0] and z[15] == 1 and z[3] is None
    assert full["2026-08-12"][14] == [0.0] and full["2026-08-12"][15] == 0  # D60 = Oct 11: hot, not final
    assert len(full["2026-08-20"]) == 14 and full["2026-10-12"][4] == [0.0, 0.0] and full["2026-10-12"][5] == 0
    assert full["2026-09-20"][3] == 0.0 and full["2026-09-20"][11] == "N/A"   # a known day: spend 0
    assert full["2026-09-05"][1] == 3 and full["2026-09-05"][4][0] == pytest.approx(0.05 * 1.2)   # thin: app's k
    # the expansion equals what the build would write in full (every short row checked)
    for r in ee:
        if len(r) == 1:
            X = date.fromisoformat(r[0])
            assert rb._zrow(X, CTODAY, date(2026, 10, 10), full[r[0]][3] is None, "EE")["n"] == 0
    # a hole (a hot copy dropped before the walk folded it): the rows stop the day before it, the same as the
    # 30-day columns
    data2, P2, pre2, spend2, acc2 = _cc_world(tmp_path / "h", holes={date(2026, 10, 1)})
    cd2, od2, _ = _cc_run(tmp_path / "h", data2, P2, pre2, spend2, acc2)
    assert cd2["thru"] == "2026-09-30" and cd2["fthru"] == "2026-09-30"
    AA = {r[0]: r for r in _expand(_pack_rows(od2, cd2)["AA"], cd2, "AA")}
    assert max(AA) == "2026-09-30" and len(AA["2026-09-25"][4]) == 6 and AA["2026-09-25"][5] == 6


def test_country_loss_flags_and_not_split(tmp_path):
    loss = {date(2026, 9, 20): 500000}
    data, P, pre, spend, acc = _cc_world(tmp_path, loss=loss, flags={date(2026, 9, 25)})
    cd, od, _ = _cc_run(tmp_path, data, P, pre, spend, acc)
    assert cd["loss"]["days"] == 1 and cd["loss"]["flag_days"] == 1 and cd["loss"]["usd"] == pytest.approx(0.6)
    assert 0 < cd["loss"]["max_share"] < 1
    AA = {r[0]: r for r in _expand(_pack_rows(od, cd)["AA"], cd, "AA")}
    assert AA["2026-09-18"][12] & 2 and AA["2026-09-23"][12] & 4 and not AA["2026-09-26"][12] & 6
    assert AA["2026-08-10"][12] & 2                                       # its D60 column's days span Sep 20 too


def test_country_packs_deterministic_and_split(tmp_path, monkeypatch):
    data, P, pre, spend, acc = _cc_world(tmp_path)
    geo0 = json.loads(json.dumps(acc.geo))                               # (a build lets each app's stores go after it)
    monkeypatch.setattr(rb, "PACK_MAX", 30_000)                          # small packs: several, a big country alone
    cd, od, _ = _cc_run(tmp_path, data, P, pre, spend, acc)
    got = _pack_rows(od, cd)
    assert len(cd["packs"]) >= 3 and set(got) == {x[0] for x in cd["c"]}
    sizes = {}
    for name, _ in cd["packs"]:
        with gzip.open(os.path.join(str(od), name), "rb") as f:
            sizes[name] = len(f.read())
    big = [x for x in cd["c"] if x[0] == "AA"][0]
    assert sum(1 for x in cd["c"] if x[4] == big[4]) == 1                # AA (over 30 kB) has its pack alone
    for name, sz in sizes.items():
        ix = int(name.split("_c")[1][:2])
        if sum(1 for x in cd["c"] if x[4] == ix) > 1:
            assert sz <= 30_000 + 200
    assert [x[4] for x in cd["c"]] == sorted(x[4] for x in cd["c"])     # filled in the index's order
    names = sorted(os.listdir(str(od)))
    assert all(rb.PACK_RE.match(n) for n in names) and len(names) == len(cd["packs"])
    before = {n: open(os.path.join(str(od), n), "rb").read() for n in names}
    acc2 = rb.start(cube=True, cmon=acc.cmon)
    assert acc.geo["days"] == {}                                          # the app's store read once, then let go
    acc2.geo = geo0
    cd2, od2, _ = _cc_run(tmp_path, data, P, pre, spend, acc2)           # a second build: the same bytes
    assert cd2 == cd and {n: open(os.path.join(str(od2), n), "rb").read() for n in names} == before


def test_country_zrow_matches_cohorts(tmp_path):
    """A country day with nothing of its own: _cohorts (the build's own row) == _zrow (what the page expands [X] to),
    on every age the cube read / folded through (no m yet, m not final, final)."""
    from admob_iq.fetch import ga4_cube as cu    # noqa: F401
    data, P, pre, spend, acc = _cc_world(tmp_path)
    cv = rb._Cty(P["hs"])
    late = rb._late(str(data), "a~1", "222", P, visit=cv.visit)
    thru, fthru = CTODAY, date(2026, 10, 10)
    Pc = {"pre": P["pre"], "sc": {"kf": lambda d_: (1.0, "ok", False, 1.0)}, "xs": {}, "S": P["S"], "hs": CHS}
    days = [CHS + timedelta(days=i) for i in range((thru - CHS).days + 1)]
    sp = {"first": CHS.isoformat(), "till": "2026-10-12", "daily": {}, "installs": {}}
    got = rb._cohorts(Pc, sp, lambda d_: 1.0, {"read_today": thru.isoformat(), "x": {X.isoformat(): {"r": [], "u": [0]}
                                                                                     for X in days}},
                      thru, {"B": {}, "full": late["full"], "fin": late["fin"], "q": late["q"]}, edge=fthru)
    assert len(got) == len(days)
    rb._statuses(got)
    for r in got:
        r["u"], r["q"], r["qo"] = None, False, 0
        unk = r["X"] > date(2026, 10, 12)
        if unk:
            r["sp"] = r["spi"] = None
        if r.get("m"):
            for a_ in (60, 90, 180):
                if a_ // 30 - 2 < r["mf"]:
                    r["t"][T.index(a_)] = r["m"][a_ // 30 - 2]
        assert rb._row_out(r) == rb._row_out(rb._zrow(r["X"], thru, fthru, unk, "AA")), r["X"]


def _cc_app_step(tmp_path, monkeypatch, name, cube=True, strip=False, geo_calls=None, nocube=False):
    """app_step on the country world (the build's own path: _late's visit, the Ads split loaded once a build)."""
    import shutil
    from admob_iq.fetch import ga4_cube as cu
    from admob_iq.fetch import gads_geo_day as gdd
    data, P, pre, spend, acc0 = _cc_world(tmp_path / name)
    if nocube:
        shutil.rmtree(str(data / cu.DIR))
    if strip:                                           # the same cube without its country parts
        for M, mo in cu.months(str(data), "a~1", "222"):
            cu.write_json_gz_stable(cu.month_path(str(data), "a~1", M), dict(mo, c={}, e={}))
        h = cu.load_head(str(data), "a~1")
        for rec in h["d"].values():
            rec["c"], rec["e"] = {}, {}
        cu.write_json_gz_stable(cu.hot_path(str(data), "a~1"), h)
    co = {"read_today": CTODAY.isoformat(), "stream_id": "222", "x": {}}
    _stub_app(monkeypatch, P, co, spend)
    calls = geo_calls if geo_calls is not None else []
    monkeypatch.setattr(gdd, "load", lambda d_: calls.append(d_) or acc0.geo)
    out = tmp_path / name / "out"
    out.mkdir()
    acc = rb.start(cube=cube, cmon=acc0.cmon)
    store, a = {"history_start": CHS.isoformat(), "stream_id": "222"}, {"app_id": "a~1", "app_name": "Alpha"}
    rb.app_step(acc, store, a, "aaaaaaaaaaaa", {"tz": "UTC"}, pre, {}, str(out), str(data), ids=["a~1"])
    assert not acc.fails and len(acc.apps) == 1
    with open(os.path.join(str(out), "roi_aaaaaaaaaaaa.json.gz"), "rb") as f:
        return gzip.decompress(f.read()), acc, out


def test_country_app_step_file_and_isolation(tmp_path, monkeypatch):
    calls = []
    full, acc, out = _cc_app_step(tmp_path, monkeypatch, "on", geo_calls=calls)
    body = json.loads(full)
    assert body["cd"]["v"] == 1 and len(calls) == 1 and acc.cdn == {"apps": 1, "countries": 6, "packs": 1, "failed": 0}
    assert sorted(os.listdir(str(out))) == ["roi_aaaaaaaaaaaa.json.gz", "roi_aaaaaaaaaaaa_c00.json.gz"]
    # every other byte of the file = the same cube without its country parts (no "cd")
    bare, acc_b, _ = _cc_app_step(tmp_path, monkeypatch, "bare", strip=True)
    assert "cd" not in json.loads(bare) and acc_b.cdn["apps"] == 0
    rest = dict(body)
    rest.pop("cd")
    assert json.dumps(rest, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode() == bare
    # the switch off: no "late", no "cd", no pack — byte for byte the file without any cube
    off, acc_o, out_o = _cc_app_step(tmp_path, monkeypatch, "off", cube=False)
    assert "cd" not in json.loads(off) and "late" not in json.loads(off) and os.listdir(str(out_o)) == [
        "roi_aaaaaaaaaaaa.json.gz"]
    none, acc_n, _ = _cc_app_step(tmp_path, monkeypatch, "none", nocube=True)   # the switch on, no cube on disk
    assert none == off and acc_n.cdn == {"apps": 0, "countries": 0, "packs": 0, "failed": 0}
    # any failure in the country part: no "cd", every other byte as without it, counted
    monkeypatch.setattr(rb, "_cty", lambda *a_, **k_: 1 / 0)
    bad, acc_x, out_x = _cc_app_step(tmp_path, monkeypatch, "bad")
    assert bad == bare and acc_x.cdn["failed"] == 1 and os.listdir(str(out_x)) == ["roi_aaaaaaaaaaaa.json.gz"]


def test_country_visit_failure_keeps_the_columns(tmp_path, monkeypatch):
    def boom(self, M, e):
        raise ValueError("bad cell")
    monkeypatch.setattr(rb._Cty, "_e", boom)
    bad, acc, _ = _cc_app_step(tmp_path, monkeypatch, "v")
    bare, _, _ = _cc_app_step(tmp_path, monkeypatch, "b", strip=True)
    body = json.loads(bad)
    assert "cd" not in body and acc.cdn["failed"] == 1 and any(len(r) == 16 for r in body["rows"])   # m kept
    assert json.loads(bare)["late"] == body["late"]


def test_country_stale_packs_and_line(tmp_path, monkeypatch):
    full, acc, out = _cc_app_step(tmp_path, monkeypatch, "s")
    for f in ("roi_aaaaaaaaaaaa_c07.json.gz", "roi_bbbbbbbbbbbb_c00.json.gz"):   # an older build's: one too many /
        open(os.path.join(str(out), f), "w").close()                         # another app's (gone now)
    assert rb.finish(acc, {}, str(out)) == ["/roi*"]
    assert sorted(os.listdir(str(out))) == ["roi.json.gz", "roi_aaaaaaaaaaaa.json.gz", "roi_aaaaaaaaaaaa_c00.json.gz"]
    line = rb.pop_line()
    assert line.startswith("roi: apps 1,") and "; countries: apps 1, countries 6, packs 1, failed 0" in line
    assert "Alpha" not in line and "AA" not in line
    rb.off(str(out))                                                         # the section off: every file of it
    assert os.listdir(str(out)) == []
    acc2 = rb.start()                                                        # the switch off: the line as before
    acc2.apps = [dict(acc.apps[0])]
    rb.finish(acc2, {}, str(out))
    assert "countries" not in rb.pop_line()


def test_admob_country_months_every_month():
    from admob_iq.build_static import admob_country, admob_country_months
    rows = [{"app_id": "a", "report_date": "2026-10-01", "country": "IN", "estimated_earnings_micros": 5, "impressions": 9},
            {"app_id": "a", "report_date": "2026-10-01", "country": "IN", "estimated_earnings_micros": 1, "impressions": 1},
            {"app_id": "a", "report_date": "2024-07-31", "country": "IN", "estimated_earnings_micros": 9, "impressions": 9},
            {"app_id": "a", "report_date": "2026-10-03", "country": "US", "estimated_earnings_micros": 9, "impressions": 9},
            {"app_id": "a", "report_date": "2026-10-02", "country": "US", "estimated_earnings_micros": 4, "impressions": 9},
            {"app_id": "b", "report_date": "2026-10-01", "country": "", "estimated_earnings_micros": 9, "impressions": 9}]
    got = admob_country_months(rows, "2026-10-02")
    assert got == {"m": {"a": {"2026-10": {"IN": 6, "US": 4}, "2024-07": {"IN": 9}}},       # every month, never cut
                   "d": {"a": {"2026-10": 0b11, "2024-07": 1 << 30}}}
    assert admob_country(rows, "2026-10-02") == {"a": {"2026-10-01": {"IN": [6, 10]}, "2026-10-02": {"US": [4, 9]}}}
