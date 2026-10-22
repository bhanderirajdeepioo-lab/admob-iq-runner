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
Review fixes: a spend-only row's ≈ bits, a borrowed k_c month (bit 32 + its revenue share), GA4 revenue without a country
per month (bit 64 past UNP_LIM, measured), the Ads split tied to the spend cache (else unknown, counted), the Ads split
read per app (shared store, a failed read counted), the Ads account's time zone, the packs' build stamp, and the
country part's time never in the forecast's budget.
The whole read past D30 (fetch.ga4_cube q): a week inside a month on q only when every day of it is (j ≤ 13 from q, j ≥
14 from the cube's cells; one day missing or "fl": the whole week on the cube), the D60 / D90 / D180 columns equal to
the install-day checkpoints when the cube kept 0.8 of it, a hot day with / without its q, ql (loss past age 420, exact)
and qneg / qpos (drift: its size, never loss — never young loss turned into loss past 420), a loss below a cent kept
to the micro, rows GA4 gave no install day as their own size (qn: never costing a week its q), a read naming fewer
install days than the cube kept staying on the cube (qshort), the days waiting (qwait) apart from those on the cube for
good (qfl), each with its "(other)" size, ≈ bits 2 / 4 only where a row still takes the cube's cells, days of nothing
needing no read, without q files — or q off / not used — the build as before; no borrowed k_c (a month not whole: the
app's k); GA4: country not given per month (cd.ng = All − Σ countries).
👥 Users: the All rows' mu (users on each 30-day column's day) from an install-day fixture first, then a whole read's
users (≤ 420), null otherwise; through the build's files (a hot day's only beside its own read) and the switch
(GA4_CUBE_U_USE=false: every byte as without); the country rows' u / mu (null where a day's users are not kept), ≈ bits
from "(other)" / flagged days, users-only countries, zero rows still [X], the packs' build stamp and PACK_MAX.
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
    assert lens == {14, 16, 17} and full["rows"][0][14] == [62.6, 63.2, 63.8, 64.67, 65.57] and full["rows"][0][15] == 5
    # 👥 users on each column's day (mu, index 16): the install-day file's at its ages 60 / 90 / 120 / 180 (day 150 is
    # none of them and no users' file is there: null); a row whose every column's day is past the file: no mu (16)
    assert full["rows"][0][16] == [100, 100, 100, None, 100]
    assert all(len(r) == 16 for r in full["rows"] if len(r) > 14 and date.fromisoformat(r[0]) + timedelta(days=60) > LS)
    # every other part of the file as without the cube but what the columns feed (so far, breakeven → the forms)
    assert [r[:8] + r[11:14] for r in full["rows"]] == [r[:8] + r[11:14] for r in plain["rows"]]
    assert {k for k in full if full[k] != plain.get(k)} <= {"rows", "late", "sum", "f4", "months"}
    assert full["months"] == plain["months"] and full["cty"] == plain["cty"] and full["life"] == plain["life"]


def test_cohort_other_loss_days_mark_their_rows(tmp_path, monkeypatch):
    """A day whose D0 … D30 read kept revenue in GA4's "(other)" (fetch.ga4_cohort "lo") or that GA4 flagged ("lf"):
    every row whose d uses it is ≈ (q bit 1, as a day that does not tie); nothing else of the file changes."""
    P, co = _cube_setup(tmp_path / "data")
    _stub_app(monkeypatch, P, co, SPEND)
    plain = json.loads(_app_step_run(str(tmp_path / "data"), str(tmp_path / "o1"), False))
    lo, lf = LTODAY - timedelta(days=40), LTODAY - timedelta(days=5)
    _stub_app(monkeypatch, P, dict(co, lo={lo.isoformat(): 1234}, lf={lf.isoformat(): 1}), SPEND)
    got = json.loads(_app_step_run(str(tmp_path / "data"), str(tmp_path / "o2"), False))
    marked = 0
    assert len(got["rows"]) == len(plain["rows"])
    for r0, r1 in zip(plain["rows"], got["rows"]):
        X = date.fromisoformat(r0[0])
        uses = bool(r0[4]) and any(X + timedelta(days=L) in (lo, lf) for L in range(len(r0[4])))
        marked += uses and not r0[12] & 1
        assert r1[12] == (r0[12] | 1 if uses else r0[12]) and r1[:12] == r0[:12] and r1[13:] == r0[13:], r0[0]
    assert marked >= 30
    assert {k for k in got if got[k] != plain[k]} <= {"rows", "sum"}


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


def _geo_files(data, days, ccy="USD"):
    """Google Ads by store × day × country on disk, as fetch.gads_geo_day writes it (one file a month + its state)."""
    from admob_iq.db import write_json_gz_stable
    from admob_iq.fetch import gads_geo_day as gdd
    d = os.path.join(str(data), gdd.GD_DIR)
    os.makedirs(d, exist_ok=True)
    by = {}
    for sid, dd in days.items():
        for k, ent in dd.items():
            by.setdefault(k[:7], {}).setdefault(sid, {})[k] = ent
    for M, st in by.items():
        write_json_gz_stable(os.path.join(d, M + ".json.gz"), {"v": gdd.GD_V, "month": M, "ccy": ccy, "days": st})
    write_json_gz_stable(os.path.join(d, "state.json.gz"), dict(gdd.DEFAULTS, v=gdd.GD_V, ccy=ccy))


def _cc_world(tmp_path, kmul=None, mask_off=(), geo_holes=(date(2026, 9, 15),), geo_more=None, **kw):
    """The cube + AdMob by country × month (kmul[cc][month] × the country's GA4; whole months by default, the newest
    through Oct 12) + Google Ads by store × day × country on disk (from Sep 1; a store-day in geo_holes has spend but no
    split; geo_more: more stores' days)."""
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
    _geo_files(data, dict({"s1": geo}, **(geo_more or {})))
    acc = rb.start(cube=True, cmon=cmon)
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
    # D60 from the cube's buckets × k_c of each activity month (Sep 10 … 30 at Sep's own 1.0; Oct 1 … 9: Oct is not whole
    # yet → the app's k 1.2, never a k_c borrowed from Sep — ≈ bit 16)
    assert r[14] == [pytest.approx(4.2 + 2.1 + 9 * 0.12)] and r[15] == 1 and r[7][T.index(60)] == r[14][0] and r[12] & 16
    assert not r[12] & 32
    assert r[3] is None and r[13] is None                                   # Aug: Google Ads by country unknown → '—'
    s = AA["2026-09-10"]
    assert s[3] == 6.0 and s[13] == 6.0 and s[2] == 3.0                     # USD (rate 1), as billed, Ads downloads
    assert AA["2026-09-15"][3] is None                                      # a store spent, no committed split: '—'
    assert AA["2026-10-13"][3] is None                                      # after the spend cache: unknown
    # statuses on the country's own rows (≥ $5 and ≥ 30 installs judged), the same _statuses
    assert AA["2026-08-10"][11] == "N/A" and AA["2026-09-25"][11] in ("Normal", "Watch", "Better", "Worse")
    assert AA["2026-10-12"][11] == "Too early"
    # q: k_c 1.5 is outside 0.8 – 1.25 (bit 8); a Sep / Oct row: Sep's measured k inside it (no 8), Oct on the app's
    # k (16)
    assert r[12] & 8 and not AA["2026-09-20"][12] & 8 and AA["2026-09-20"][12] & 16
    # CC: AdMob 3× → clamped to 2.0 (≈); BB: too thin even pooled → the app's k (1.2, ≈, bit 16); "--": always the app's
    CC = {x[0]: x for x in _expand(got["CC"], cd, "CC")}
    assert CC["2026-09-05"][4][0] == pytest.approx(0.02 * 2.0) and CC["2026-09-05"][12] & 8
    BB = {x[0]: x for x in _expand(got["BB"], cd, "BB")}
    assert BB["2026-09-05"][4][0] == pytest.approx(0.001 * 1.2) and BB["2026-09-05"][12] & 16
    NC = {x[0]: x for x in _expand(got["--"], cd, "--")}
    assert NC["2026-09-05"][4][0] == pytest.approx(0.01 * 1.2) and NC["2026-09-05"][12] & 16
    assert NC["2026-09-05"][3] is None and c["--"][2] is None               # GA4's "(not set)": no Ads country
    # the revenue share on the app's k: "--" / BB every month; AA its Oct (not whole yet: never a borrowed k_c)
    oct_ = _ga4_month("AA", "2026-10") / sum(_ga4_month("AA", M) for M in ("2026-08", "2026-09", "2026-10"))
    assert c["--"][6] == 1.0 and c["BB"][6] == 1.0 and c["AA"][6] == round(oct_, 4) and c["XX"][6] is None
    assert all(len(x) == 7 for x in cd["c"])                                 # no borrowed-k_c share any more
    assert AA["2026-09-05"][12] & 16 and not AA["2026-08-01"][12] & 16   # its ages in Oct / none in Oct (D0 … D60)
    assert not any(x[12] & 32 for x in AA.values() if len(x) > 12)
    assert BB["2026-09-05"][3] == 2.0 and BB["2026-09-05"][2] is None       # downloads unknown: null
    # an Ads-only country: its spend per day, no installs, no revenue
    DD = {x[0]: x for x in _expand(got["DD"], cd, "DD")}
    assert DD["2026-09-05"][1] == 0 and DD["2026-09-05"][3] == 1.0 and DD["2026-09-05"][8] == 0.0
    # "Not split": Google Ads' unmapped cost by install day, no revenue
    XX = {x[0]: x for x in _expand(got["XX"], cd, "XX")}
    assert XX["2026-09-05"][3] == 1.0 and XX["2026-09-05"][1] is None and XX["2026-09-05"][4] is None
    assert XX["2026-08-05"][3] is None and len(XX) == days
    # the index: k_c months, Google Ads coverage, the measured gap to the All row
    # own: AA Aug + Sep, CC Sep; pooled: CC Aug ($9.92 GA4, a whole month); the app's k: Oct of AA / CC (not whole yet:
    # never borrowed), BB, "--" every month; ≈ (measured, outside 0.8 – 1.25): AA Aug (1.5), CC Aug + Sep (3.0 → 2.0)
    assert {k: cd["kc"][k] for k in ("own_months", "pool_months", "app_months", "est_months")} == {
        "own_months": 3, "pool_months": 1, "app_months": 8, "est_months": 3} and "near_months" not in cd["kc"]
    assert cd["kc"]["tzh"] is not None                                    # AdMob's day vs GA4's (UTC here): measured
    # GA4 revenue without a country per month ("--" here; no loss): measured of the ledger's every row
    tot = {M: sum(_ga4_month(cc, M) for cc in CRATE) for M in ("2026-08", "2026-09", "2026-10")}
    assert cd["kc"]["unp"] == {M: round(_ga4_month("--", M) / tot[M], 4) for M in tot} and cd["kc"]["unp_lim"] == 0.02
    assert cd["kc"]["unp_all"] == round(sum(_ga4_month("--", M) for M in tot) / sum(tot.values()), 4)
    assert all(AA[x][12] & 64 for x in ("2026-08-10", "2026-10-05")) and not NC["2026-09-05"][12] & 64
    g = cd["geo"]
    assert g["from"] == "2026-09-01" and g["till"] == "2026-10-12" and g["unknown_days"] == 31 + 1 + 1
    assert g["untied_days"] == 0 and g["tzs"] == 0 and g["tzh"] is None    # every split ties; no Ads hourly store
    assert g["unk"] == [["2026-08-01", "2026-08-31"], ["2026-09-15", "2026-09-15"], ["2026-10-13", "2026-10-13"]]
    assert g["xx_share"] == round(1 / 10, 4) and g["cov"] == 1.0
    assert c["AA"][2] == pytest.approx(6.0 * (g["known_days"] - 0)) and c["XX"][2] == pytest.approx(1.0 * g["known_days"])
    assert cd["diff"]["age"] == 30 and cd["diff"]["days"] >= 1 and cd["diff"]["n_cty"] == cd["diff"]["days"] * 50
    assert cd["diff"]["unk"] == pytest.approx(cd["diff"]["days"] * 31 * 0.01 * 1.2, abs=0.02)   # "--": in the sum too


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
    assert a["2026-06"] == (1.1, "app", True)                           # not whole: the app's k, never borrowed
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
    # Sep's AdMob report misses two days in a row: Sep is not whole → the app's k (1.2), never a k_c borrowed from
    # Aug (1.5); an Aug install day's ages in Sep use 1.2 (≈, bit 16)
    data, P, pre, spend, acc = _cc_world(tmp_path, mask_off=("2026-09",))
    cd, od, _ = _cc_run(tmp_path, data, P, pre, spend, acc)
    AA = {r[0]: r for r in _expand(_pack_rows(od, cd)["AA"], cd, "AA")}
    assert AA["2026-08-10"][4][30] == pytest.approx(22 * 0.15 + 9 * 0.12) and AA["2026-08-10"][12] & 16
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
    cd2, od2, _ = _cc_run(tmp_path, data, P, pre, spend, acc2)           # a second build: the same bytes
    assert cd2 == cd and {n: open(os.path.join(str(od2), n), "rb").read() for n in names} == before
    # every pack says the build it belongs to (the index's "b"): the page never reads a pack of another build
    for name, _ in cd["packs"]:
        with gzip.open(os.path.join(str(od), name), "rb") as f:
            assert json.loads(f.read())["b"] == cd["b"] and len(cd["b"]) == 12
    cd3, _, _ = _cc_run(tmp_path, data, P, pre, spend, rb.start(cube=True, cmon=acc.cmon), ded=0.2, out="o3")
    assert cd3["b"] != cd["b"] and all(a[1] != b[1] for a, b in zip(cd3["packs"], cd["packs"]))   # rows moved → new b


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
    real = gdd.load
    monkeypatch.setattr(gdd, "load", lambda d_, keep=None: calls.append(sorted(keep or ())) or real(d_, keep=keep))
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
    assert body["cd"]["v"] == 1 and calls == [["s1"]] and acc.cdn == {"apps": 1, "countries": 6, "packs": 1, "failed": 0,
                                                                     "geo_failed": 0}   # only the app's own store read
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
    assert none == off and acc_n.cdn == {"apps": 0, "countries": 0, "packs": 0, "failed": 0, "geo_failed": 0}
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
    assert line.startswith("roi: apps 1,") and "; countries: apps 1, countries 6, packs 1, failed 0, ads split unread 0" in line
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


# ── 🌍 review fixes ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_country_spend_only_row_carries_the_loss_bit(tmp_path):
    # DD: Google Ads spend, no GA4 installs / revenue (its users went to "(other)" that day, say): the cube's loss day in
    # its span still marks it ≈ (bit 2) — a row with spend is never short, so the bit costs no [X]
    data, P, pre, spend, acc = _cc_world(tmp_path, loss={date(2026, 9, 20): 500000}, flags={date(2026, 9, 25)})
    cd, od, _ = _cc_run(tmp_path, data, P, pre, spend, acc)
    got = _pack_rows(od, cd)
    DD = {r[0]: r for r in _expand(got["DD"], cd, "DD")}
    assert DD["2026-09-20"][3] == 1.0 and DD["2026-09-20"][1] == 0 and DD["2026-09-20"][12] & 2
    assert DD["2026-09-24"][12] & 4 and not DD["2026-09-26"][12] & 6 and not DD["2026-09-26"][12]
    assert all(len(r) > 1 for r in got["DD"] if "2026-09-01" <= r[0] <= "2026-10-12" and r[0] != "2026-09-15")
    assert all(len(r) == 1 for r in got["DD"] if r[0] < "2026-09-01" or r[0] == "2026-09-15")   # nothing of its own: [X]


def test_country_unplaced_share_per_month(tmp_path):
    # "--" tiny; Sep has a measured "(other)" loss of 3% of its GA4 revenue: only Sep is past UNP_LIM (2%) → bit 64 on
    # the rows whose revenue uses Sep, never on "--" (its own k is the app's), never on an Oct-only row
    rate = dict(CRATE, **{"--": 10})
    sep = sum(_ga4_month(cc, "2026-09", rate) for cc in CRATE)
    data, P, pre, spend, acc = _cc_world(tmp_path, rate=rate, loss={date(2026, 9, 20): int(sep * 0.03)})
    cd, od, _ = _cc_run(tmp_path, data, P, pre, spend, acc)
    u = cd["kc"]["unp"]
    assert u["2026-09"] == round((_ga4_month("--", "2026-09", rate) + int(sep * 0.03)) / (sep + int(sep * 0.03)), 4)
    assert u["2026-09"] > rb.UNP_LIM > u["2026-08"] and u["2026-10"] < rb.UNP_LIM
    AA = {r[0]: r for r in _expand(_pack_rows(od, cd)["AA"], cd, "AA")}
    NC = {r[0]: r for r in _expand(_pack_rows(od, cd)["--"], cd, "--")}
    assert AA["2026-09-05"][12] & 64 and AA["2026-08-25"][12] & 64 and not AA["2026-10-05"][12] & 64
    assert AA["2026-08-01"][12] & 64 and AA["2026-08-01"][14]                  # Aug 1: D0 … D30 in Aug, its D60 in Sep
    assert not any(r[12] & 64 for r in NC.values() if len(r) > 1)


def test_country_geo_day_ties_to_the_spend_cache():
    days = [date(2026, 9, 1) + timedelta(days=i) for i in range(5)]
    k = [d.isoformat() for d in days]
    sdaily = {"s1": {x: 10_000_000 for x in k}, "s2": {k[0]: 4_000_000}}   # (tolerance: 1% or one unit, 1e6 micros)
    geo = {"days": {"s1": {k[0]: {"AA": [6_000_000, 1.0], "XX": [4_000_000, None]},       # ties
                           k[1]: {"AA": [9_950_000, 1.0]},                                 # 0.5% off: ties
                           k[2]: {},                                                       # committed {}, it spent
                           k[3]: {"AA": [8_000_000, 1.0]},                                 # 20% off
                           k[4]: {"AA": [10_000_000, 1.0], "BB": [1_500_000, None]}},      # 1.5 units more
                    "s2": {k[0]: {"BB": [4_000_000, 2.0]}}}}
    spend = {"first": k[0], "till": k[-1]}
    cost, unk, st = rb._geo_app(geo, ["s1", "s2"], sdaily, spend, days)
    assert unk == {days[2], days[3], days[4]} and st["untied_days"] == 3 and st["unknown_days"] == 3
    assert cost["AA"] == {days[0]: (6_000_000, 1.0), days[1]: (9_950_000, 1.0)} and cost["BB"] == {days[0]: (4_000_000, 2.0)}
    # a store with no committed day while it spent: unknown, not "untied"; a store that did not spend: never asked
    cost, unk, st = rb._geo_app({"days": {"s1": {k[0]: {"AA": [10_000_000, 1.0]}}}}, ["s1", "s2"], sdaily, spend, days[:1])
    assert unk == {days[0]} and st["untied_days"] == 0
    cost, unk, st = rb._geo_app({"days": {"s1": {k[1]: {"AA": [10_000_000, 1.0]}}}}, ["s1", "s2"], sdaily, spend, days[1:2])
    assert unk == set() and cost["AA"] == {days[1]: (10_000_000, 1.0)}


def test_country_geo_read_per_app_shared_store_and_failure(tmp_path, monkeypatch):
    # only the app's own stores are read (each app its own read: nothing held for the build, no order effect — two apps
    # on one store both get its split); a read that fails: every day it spent unknown, counted
    from admob_iq.fetch import gads_geo_day as gdd
    other = {"s9": {(date(2026, 9, 1) + timedelta(days=i)).isoformat(): {"ZZ": [1, None]} for i in range(30)}}
    data, P, pre, spend, acc = _cc_world(tmp_path, geo_more=other)
    calls, real = [], gdd.load
    monkeypatch.setattr(gdd, "load", lambda d_, keep=None: calls.append(sorted(keep or ())) or real(d_, keep=keep))
    cd1, _, _ = _cc_run(tmp_path, data, P, pre, spend, acc, out="o1")
    cd2, _, _ = _cc_run(tmp_path, data, P, pre, spend, acc, out="o2")              # a second app on the same store
    assert calls == [["s1"], ["s1"]] and cd1["geo"] == cd2["geo"] and cd1["c"] == cd2["c"]
    assert acc.cdn["geo_failed"] == 0 and not hasattr(acc, "geo")

    def boom(d_, keep=None):
        raise OSError("damaged")
    monkeypatch.setattr(gdd, "load", boom)
    cd3, _, _ = _cc_run(tmp_path, data, P, pre, spend, acc, out="o3")
    span = (CTODAY - timedelta(days=1) - CHS).days + 1
    assert acc.cdn["geo_failed"] == 1 and cd3["geo"]["known_days"] == 0 and cd3["geo"]["unknown_days"] == span + 1
    assert all(x[2] is None for x in cd3["c"] if x[0] != "XX")


def test_country_ads_time_zone(tmp_path):
    # the Ads day is the Ads account's: its zone from the hourly store's accounts of the app's stores → hours GA4's day
    # (UTC here) starts before it; two zones among the app's stores: none (said on the page), the count kept
    from admob_iq.db import write_json_gz_stable
    from admob_iq.fetch import gads_hourly as gh

    def hourly(data, tz):
        d = os.path.join(str(data), gh.HR_DIR)
        os.makedirs(d, exist_ok=True)
        write_json_gz_stable(os.path.join(d, "2026-10.json.gz"), {
            "v": gh.HR_V, "month": "2026-10", "ccy": {a: "USD" for a in tz}, "tz": tz,
            "camp": {"c%d" % i: "s1" for i, _ in enumerate(tz)},
            "h": {a: {"c%d" % i: {"2026-10-01": [0] * 24}} for i, a in enumerate(tz)}})
    data, P, pre, spend, acc = _cc_world(tmp_path)
    hourly(data, {"a1": "America/New_York"})
    cd, _, _ = _cc_run(tmp_path, data, P, pre, spend, acc)
    assert cd["geo"]["tzh"] == 4.0 and cd["geo"]["tzs"] == 1                # GA4 (UTC) starts 4 h before New York's
    data2, P2, pre2, spend2, acc2 = _cc_world(tmp_path / "m")
    hourly(data2, {"a1": "America/New_York", "a2": "Asia/Kolkata"})
    cd2, _, _ = _cc_run(tmp_path / "m", data2, P2, pre2, spend2, acc2)
    assert cd2["geo"]["tzh"] is None and cd2["geo"]["tzs"] == 2


def test_country_time_never_counts_in_the_forecast_budget(tmp_path, monkeypatch):
    # the forecast's clock runs from the first app; the country part (its cube visits + _cty) of a later app moves the
    # clock's start by exactly what it took — the forecast's budget, re-tunes and numbers as without it
    from types import SimpleNamespace
    now = [100.0]
    fc = SimpleNamespace(clock=lambda: now[0], t0=50.0)
    real_cty, real_e = rb._cty, rb._Cty._e
    visits = []

    def slow_cty(*a, **k):
        now[0] += 5.0
        return real_cty(*a, **k)

    def slow_e(self, *a):                                           # inside each visit (a month / a hot day)
        now[0] += 0.25
        visits.append(1)
        return real_e(self, *a)
    monkeypatch.setattr(rb, "_cty", slow_cty)
    monkeypatch.setattr(rb._Cty, "_e", slow_e)
    data, P, pre, spend, acc0 = _cc_world(tmp_path / "w")
    co = {"read_today": CTODAY.isoformat(), "stream_id": "222", "x": {}}
    _stub_app(monkeypatch, P, co, spend)
    out = tmp_path / "w" / "out"
    out.mkdir()
    acc = rb.start(cube=True, cmon=acc0.cmon)
    acc.fc = fc                                                     # (the forecast step itself then fails: caught)
    store, a = {"history_start": CHS.isoformat(), "stream_id": "222"}, {"app_id": "a~1", "app_name": "Alpha"}
    rb.app_step(acc, store, a, "aaaaaaaaaaaa", {"tz": "UTC"}, pre, {}, str(out), str(data), ids=["a~1"])
    assert not acc.fails and acc.cdn["apps"] == 1 and visits
    assert fc.t0 == pytest.approx(50.0 + 5.0 + 0.25 * len(visits))


# ── q: the whole no-country read past D30 (fetch.ga4_cube q; made-up numbers) ──────────────────────────────────────
QHS, QTODAY = date(2025, 1, 1), date(2026, 10, 13)
QX1 = QTODAY - timedelta(days=90)                       # a young install day: its D90 column ends today (hot days)
QR = [2.0, 4.0, 8.0, 16.0, 30.0, 62.0, 62.6, 63.2, 65.0, 68.7]   # checkpoints = the WHOLE revenue: +$0.6 every 30 days


def _q_world(root, b=8000, w=10000, q=True, skip=(), fl=(), hot_q=True, more=None, nset=None, drop=None, cfl=(),
             nothing=(), q_at="2026-10-13T06:00:00Z", fl_at=None, fl_rt=0, tz=None, gots=None):
    """Two install days (QHS, QX1) earning `w` GA4 micros a day at every age ≥ 31 (whole: $0.01, × k 2 = $0.02); the
    cube's cells keep `b` of it, the rest is the day's "(other)" loss (the cube's t holds it); every day QHS … today − 3
    folded, the last 3 hot (days before QHS + 31: nothing at all). q (whole: `w` an install day at ages ≤ 420, +
    more[day] on its qt) on every folded day but `skip` (`fl`: read, flagged — an empty q), on the hot days when hot_q.
    nset {day: micros}: a row GA4 gave no install day ("(not set)") — the cube's loss, q's "qn"; drop {day: {X}}: install
    days q's read does not name (a window that shrank); cfl: days the cube's read was flagged (thresholding …);
    nothing: days GA4 had no row at all (no revenue, no loss). fl_at / fl_rt: the `fl` days' read time (a callable of
    the day) / times read again after a settled "fl" ("rt"); tz: the head's time zone; gots: {day: its whole read}
    filled (each folded day's "ok" answer: what a read again once settled gives)."""
    from admob_iq.fetch import ga4_cube as cu
    P = _P(QHS, QTODAY - timedelta(days=6))
    P["xs"] = {X: dict(P["xs"][X], R=list(QR), Rr=list(QR)) for X in (QHS, QX1)}
    co = {"read_today": QTODAY.isoformat(), "stream_id": "222", "x": {}}
    cube = cu.Cube(str(root), "a~1", "222")
    hot_from = QTODAY - timedelta(days=2)
    D = QHS
    while D <= QTODAY:
        k, W, bb, qq, t, qt = D.isoformat(), _mon(D).isoformat(), {}, {}, 0, (more or {}).get(D, 0)
        for X in (QHS, QX1):
            L = (D - X).days
            if L < 31 or D in nothing:
                continue
            j = str(cu.bucket(L))
            bb[X.isoformat()] = {j: {W: b}}
            t += w
            if L <= cu.QL and X not in (drop or {}).get(D, ()):
                qq[X.isoformat()] = {j: w}
                qt += w
        ns = (nset or {}).get(D, 0)
        t += ns
        rec = {"st": "loss" if t > b * len(bb) else "ok", "rows": len(bb) + bool(ns), "loss": t - b * len(bb), "t": t,
               "fl": int(D in cfl), "via": "block", "at": "2026-10-13T06:00:00Z", "b": bb, "c": {}, "e": {}}
        got = {"q": {} if D in fl else qq, "qt": qt, "qn": ns, "qs": "fl" if D in fl else "ok", "qr": len(bb) + bool(ns)}
        if gots is not None:
            gots[k] = dict(got, q=qq, qs="ok")
        if D >= hot_from:
            if hot_q:
                rec.update(q=cu._qw(got["q"], k), qt=got["qt"], qs=got["qs"], qr=got["qr"])
            cube.head["d"][k] = rec
        else:
            cube.fold(D, rec)
            if q and D not in skip:
                cube.q_put(k, got, fl_at(D) if fl_at and D in fl else q_at)
                if fl_rt and D in fl:
                    cube.qmonth(k[:7])["days"][k]["rt"] = fl_rt
        D += timedelta(days=1)
    cube.save()
    cube.head.update(done=True, stream_id="222", next=hot_from.isoformat(), **({"time_zone": tz} if tz else {}))
    cube.save_head()
    return P, co


def _qrows(root, P, co):
    late = rb._late(str(root), "a~1", "222", P)
    return late, {r["X"]: r for r in rb._cohorts(P, None, lambda d: 1.0, co, QTODAY, late)}


def test_q_whole_weeks_give_the_checkpoints(tmp_path):
    """b = 0.8 × whole on the cube, q = whole: every 30-day column up to D420 equals the install-day read's
    checkpoint (D60 / D90 / D180 exactly); past 420 the cube's cells (bucket 14 on: never q)."""
    P, co = _q_world(tmp_path / "q")
    late, by = _qrows(tmp_path / "q", P, co)
    r = by[QHS]
    assert len(r["m"]) == 20 and r["mf"] == 20
    assert r["m"][:13] == pytest.approx([62 + 0.6 * j for j in range(1, 14)], abs=1e-4)
    assert (r["m"][0], r["m"][1], r["m"][4]) == (r["t"][T.index(60)], r["t"][T.index(90)], r["t"][T.index(180)]) \
        == (62.6, 63.2, 65.0)
    assert r["m"][13:] == pytest.approx([62 + 7.8 + 0.48 * i for i in range(1, 8)], abs=1e-4)   # j ≥ 14: b (0.8)
    y = by[QX1]                                          # its D90 column ends on the hot days: their q (same run)
    assert y["m"] == pytest.approx([62.6, 63.2], abs=1e-4) and y["mf"] == 1 and not y["qo"]
    old = (QTODAY - (QHS + timedelta(days=rb.gcu.QL + 1))).days + 1       # days of QHS past age 420 (each 0.2 × $0.02)
    assert late["info"]["ql"] == pytest.approx(old * 0.004, abs=1e-8) and late["info"]["qd"] == (QTODAY - QHS).days + 1
    assert late["info"]["qwait"] == late["info"]["qfl"] == late["info"]["qshort"] == 0 and late["info"]["oth"] > 0
    assert late["info"]["qneg"] == late["info"]["qpos"] == 0 and late["info"]["qdr"] == late["info"]["qn"] == 0
    assert r["qo"] == 2                                  # its columns past D420 still carry loss (ql > 0 there)
    # the same cube without any q: every column from the cube's cells (0.8 of it), as before
    P0, co0 = _q_world(tmp_path / "b", q=False, hot_q=False)
    late0, by0 = _qrows(tmp_path / "b", P0, co0)
    assert by0[QHS]["m"] == pytest.approx([62 + 0.48 * j for j in range(1, 21)], abs=1e-4)
    assert by0[QX1]["m"] == pytest.approx([62.48, 62.96], abs=1e-4) and by0[QX1]["qo"] == 2
    assert not any(f.startswith("q") for f in late0["info"])


def test_q_one_day_missing_puts_its_whole_week_on_the_cube(tmp_path):
    """A week inside a month is on q only when every day of it is (read and "ok"): one day not read (or "fl") — the
    whole week from the cube's cells, its loss still marked: waiting for its read ("qwait", its size "qwu") — a day not
    read yet, an "fl" read made before the day settled, or a settled "fl" read again fewer than Q_RETRY times (each
    read again by the fill) —, or — a final "fl" (settled, read again Q_RETRY times), never read again — on the cube for
    good ("qfl", "qfu"); a hot day with / without its q."""
    from admob_iq.fetch import ga4_cube as cu
    miss = date(2025, 6, 11)                             # a Wednesday: Jun 9 … 15, QHS ages 159 … 165 (bucket 5)
    early = lambda D: (D + timedelta(days=2)).isoformat() + "T19:52:00Z"    # noqa: E731  (2 days old: not settled)
    late4 = lambda D: (D + timedelta(days=4)).isoformat() + "T18:31:00Z"    # noqa: E731  (the property's day decides)
    for kind, kw, held_ in (("skip", {"skip": {miss}}, False), ("fl", {"fl": {miss}}, False),
                            ("early", {"fl": {miss}, "fl_at": early}, False),
                            ("final", {"fl": {miss}, "fl_rt": cu.Q_RETRY}, True),
                            ("final_tz", {"fl": {miss}, "fl_rt": cu.Q_RETRY, "tz": "Asia/Kolkata",  # 00:01 of day 5
                                          "fl_at": late4}, True),                                  # there: settled
                            ("utc_wait", {"fl": {miss}, "fl_rt": cu.Q_RETRY, "fl_at": late4}, False),  # UTC: day 4
                            ("retry", {"fl": {miss}, "fl_rt": cu.Q_RETRY - 1}, False)):
        root = tmp_path / kind
        P, co = _q_world(root, **kw)
        late, by = _qrows(root, P, co)
        r = by[QHS]
        assert r["m"][:4] == pytest.approx([62.6, 63.2, 63.8, 64.4], abs=1e-4)
        assert r["m"][4] == pytest.approx(65.0 - 7 * 0.004, abs=1e-4)       # 7 days of bucket 5 at 0.8
        wait, held = ("qfl", "qwait") if held_ else ("qwait", "qfl")
        assert late["info"][wait] == 7 and late["info"][held] == 0 and late["info"]["qd"] == (QTODAY - QHS).days + 1 - 7
        assert late["info"]["qfu" if held_ else "qwu"] == pytest.approx(7 * 2000 * 2 / 1e6), kind
        # ≈ (bit 2) only where the row still carries loss: through D420 the skipped week; past it, ql's weeks
        lo = QHS + timedelta(days=31)
        assert late["q"](lo, QHS + timedelta(days=180), 5) == 2 and late["q"](lo, QHS + timedelta(days=150), 4) == 0
    P, co = _q_world(tmp_path / "w")
    late, _ = _qrows(tmp_path / "w", P, co)
    lo = QHS + timedelta(days=31)
    assert late["q"](lo, QHS + timedelta(days=420), 13) == 0                  # through D420: all whole
    assert late["q"](lo, QHS + timedelta(days=450), 14) == 2                  # D450: ages 421 … 450 lost some
    assert late["q"](lo, QHS + timedelta(days=450)) == 2                      # (no jmax: any loss day — the countries)
    # hot days read without q (a Stop between the cube's read and q, or an older round): on the cube, ≈
    P2, co2 = _q_world(tmp_path / "h", hot_q=False)
    late2, by2 = _qrows(tmp_path / "h", P2, co2)
    assert by2[QX1]["m"] == pytest.approx([62.6, 62.6 + 27 * 0.02 + 3 * 0.016], abs=1e-4) and by2[QX1]["qo"] == 2
    assert late2["info"]["qwait"] == 3


def test_q_a_fresh_fl_read_again_once_settled_puts_its_week_on_q(tmp_path, monkeypatch):
    """A day whose whole read came back "fl" only because it was made before the day settled (2 days after it, as the
    code before read the new final day): its week waits on the cube's cells ("qwait", never "qfl"); the fill reads it
    again once settled — whole now —, the answer replaces the "fl" and the week goes on q: its column the whole
    revenue, nothing waiting. A hot day's "fl" (read while filling) waits too: never "qfl"."""
    from datetime import datetime, timezone
    from admob_iq.fetch import ga4_cube as cu
    miss, gots, root = date(2025, 6, 11), {}, tmp_path / "w"
    P, co = _q_world(root, fl={miss}, fl_at=lambda D: (D + timedelta(days=2)).isoformat() + "T19:52:00Z", gots=gots,
                     q_at="2026-10-15T06:00:00Z")              # every "ok" read once its day settled (Oct 10: Oct 15)
    late, by = _qrows(root, P, co)
    assert late["info"]["qwait"] == 7 and late["info"]["qfl"] == 0
    assert by[QHS]["m"][4] == pytest.approx(65.0 - 7 * 0.004, abs=1e-4)      # the week on the cube's 0.8
    monkeypatch.setattr(cu, "Q_CALLS", 120)
    monkeypatch.setattr(cu, "q_read", lambda ga, D: gots[D.isoformat()])   # GA4's answer once the day settled

    class G:
        calls = tok = 0
    cube = cu.Cube(str(root), "a~1", "222")
    now = datetime(2026, 10, 14, 6, tzinfo=timezone.utc)
    assert cu.q_rescan(cube, now) and [e[0] for e in cube.head["qh"]["r"]] == [miss.isoformat()] and cube.q_out == 0
    assert cube.head["qh"]["r"][0][2] > 0                                  # its week has measured loss: first
    assert cu.q_fill(G(), cube, now, lambda: True) == 1 and cube.q_rr == cube.q_rok == 1
    cube.save()
    cube.save_head()
    late2, by2 = _qrows(root, P, co)
    assert late2["info"]["qwait"] == late2["info"]["qfl"] == 0 and late2["info"]["qd"] == (QTODAY - QHS).days + 1
    assert by2[QHS]["m"][:13] == pytest.approx([62 + 0.6 * j for j in range(1, 14)], abs=1e-4)   # the whole revenue
    # a hot day whose q came back "fl": waiting for its next round / its settled read, never on the cube for good
    P3, co3 = _q_world(tmp_path / "h", fl={QTODAY})
    late3, _ = _qrows(tmp_path / "h", P3, co3)
    assert late3["info"]["qwait"] == 1 and late3["info"]["qfl"] == 0


def test_q_an_ok_read_before_its_day_settled_waits_then_its_week_goes_on_q(tmp_path, monkeypatch):
    """q files of before: every folded day read at one moment (Oct 13), so Oct 9 / Oct 10 were read 4 / 3 days after
    them — "ok" but not settled. q_rescan takes their week (Oct 5 … 10) out of the q file: on the cube's cells, its loss
    days waiting ("qwait", never "qfl"); the fill reads them again once settled (Oct 10 a day later) and the week goes
    on q: the whole revenue, nothing waiting. The build's rule is the same (a week on q only when every day is "ok")."""
    from datetime import datetime, timezone
    from admob_iq.fetch import ga4_cube as cu
    gots, root = {}, tmp_path / "e"
    P, co = _q_world(root, gots=gots)
    late0, by0 = _qrows(root, P, co)
    assert late0["info"]["qwait"] == late0["info"]["qfl"] == 0 and late0["info"]["qd"] == (QTODAY - QHS).days + 1
    monkeypatch.setattr(cu, "Q_CALLS", 120)
    monkeypatch.setattr(cu, "q_read", lambda ga, D: gots[D.isoformat()])

    class G:
        calls = tok = 0
    cube = cu.Cube(str(root), "a~1", "222")
    cube.head["qh"]["p"] = []                                   # every folded day read (the world's fold left them)
    t1 = datetime(2026, 10, 14, 6, tzinfo=timezone.utc)
    assert cu.q_rescan(cube, t1) and cube.q_out == 6
    assert cube.head["qh"]["p"] == ["2026-10-%02d" % d for d in range(5, 11)]
    cube.save()
    cube.save_head()
    late, by = _qrows(root, P, co)
    assert late["info"]["qwait"] == 6 and late["info"]["qfl"] == 0 and late["info"]["qd"] == late0["info"]["qd"] - 6
    assert cu.q_fill(G(), cube, t1, lambda: True) == 5 and cube.head["qh"]["p"] == ["2026-10-10"]   # Oct 10: 4 days
    t2 = t1 + timedelta(days=1)
    assert cu.q_fill(G(), cube, t2, lambda: True) == 1 and cube.head["qh"]["p"] == []
    cube.save()
    cube.save_head()
    late2, by2 = _qrows(root, P, co)
    assert late2["info"]["qwait"] == late2["info"]["qfl"] == 0 and late2["info"]["qd"] == late0["info"]["qd"]
    assert by2[QHS]["m"][:13] == pytest.approx(by0[QHS]["m"][:13], abs=1e-9)
    assert by2[QHS]["m"][:13] == pytest.approx([62 + 0.6 * j for j in range(1, 14)], abs=1e-4)


def test_q_loss_past_420_and_drift(tmp_path):
    """ql per week on q = Σ t − Σ qt − Σ b(j > 13): exact, no install day (AdMob-matched by the week's k); a week whose
    whole read holds MORE than the cube's t (read-time drift) is counted in qneg, never as loss; rounding is not loss."""
    old = (QTODAY - (QHS + timedelta(days=rb.gcu.QL + 1))).days + 1
    wk = [date(2025, 3, 10) + timedelta(days=i) for i in range(7)]           # Mar 10 … 16: one week, one month
    up = {D: 5000 for D in wk}                                                # q read later: more than the cube
    P, co = _q_world(tmp_path / "a", more=up)
    late, by = _qrows(tmp_path / "a", P, co)
    assert late["info"]["qneg"] == 1 and late["info"]["ql"] == pytest.approx(old * 0.004, abs=1e-8)
    assert late["info"]["qdr"] == pytest.approx(7 * 5000 * 2 / 1e6)          # its size: said, never loss
    assert by[QHS]["m"][1] == pytest.approx(63.2, abs=1e-4)                  # the cells: q's (its qt is a total only)
    down = {wk[2]: -3000}                                                     # 3000 micros nobody's install day
    P, co = _q_world(tmp_path / "b", more=down)
    late, _ = _qrows(tmp_path / "b", P, co)
    assert late["info"]["ql"] == pytest.approx(old * 0.004 + 3000 * 2 / 1e6, abs=1e-8) and late["info"]["qneg"] == 0
    tiny = {wk[2]: -1}                                                        # a micro: rounding, never loss
    P, co = _q_world(tmp_path / "c", more=tiny)
    late, _ = _qrows(tmp_path / "c", P, co)
    assert late["info"]["ql"] == pytest.approx(old * 0.004, abs=1e-8) and late["info"]["qneg"] == 0
    # a cube that lost nothing (b = whole) but read more than q on one week: never "no install day" (ql 0) — drift
    P, co = _q_world(tmp_path / "d", b=10000, more=down)
    late, _ = _qrows(tmp_path / "d", P, co)
    assert late["info"]["ql"] == 0 and late["info"]["qpos"] == 1 and late["info"]["qneg"] == 0
    assert late["info"]["qdr"] == pytest.approx(3000 * 2 / 1e6)
    assert late["info"]["oth"] == 0 and late["info"]["qwait"] == 0
    # a hot day's q read a moment after its cube read holds more (GA4 still adds to it): neither loss nor drift
    P, co = _q_world(tmp_path / "e", more={QTODAY: 5000})
    late, _ = _qrows(tmp_path / "e", P, co)
    assert late["info"]["qneg"] == late["info"]["qpos"] == 0 and late["info"]["ql"] <= old * 0.004 + 1e-8


def test_q_files_never_change_a_build_without_them(tmp_path):
    """No q file: B, the bits and the info exactly as the cube alone gives them (the jmax bits = every loss day)."""
    P, co = _q_world(tmp_path / "n", q=False, hot_q=False)
    late, by = _qrows(tmp_path / "n", P, co)
    for X, r in by.items():
        if r.get("m"):
            lo, hi = X + timedelta(days=31), X + timedelta(days=30 * (len(r["m"]) + 1))
            assert late["q"](lo, hi, len(r["m"])) == late["q"](lo, hi) == r["qo"]
    assert set(late["info"]) == {"days", "oth", "omax", "loss", "from", "till", "thru"}


def test_q_off_or_not_used_is_the_build_without_q(tmp_path, monkeypatch):
    """GA4_CUBE_Q_CALLS=0 (q off) or GA4_CUBE_Q_USE=false (reads go on, the page ignores them): q files and hot q on
    disk change nothing — B, every bit and the info exactly as without any q (a rollback that deletes no data)."""
    P0, co0 = _q_world(tmp_path / "b", q=False, hot_q=False)
    late0, by0 = _qrows(tmp_path / "b", P0, co0)
    P, co = _q_world(tmp_path / "q")
    for name, val in (("Q_CALLS", 0), ("Q_USE", False)):
        with monkeypatch.context() as m:
            m.setattr(rb.gcu, name, val)
            late, by = _qrows(tmp_path / "q", P, co)
        assert late["B"] == late0["B"] and late["info"] == late0["info"], name
        assert {X: (r.get("m"), r.get("qo")) for X, r in by.items()} == {X: (r.get("m"), r.get("qo")) for X, r in
                                                                          by0.items()}, name
    late, _ = _qrows(tmp_path / "q", P, co)                                   # on (the default): q used
    assert late["B"] != late0["B"] and "qd" in late["info"]


def test_q_rows_without_an_install_day_are_their_size(tmp_path):
    """q's "(not set)" rows (no install day at all, any age — the cube books them as loss) never cost a week its q (a
    1-micro one either): their size is "qn" (in no row, × k), ql (past age 420) stays the cube's "(other)" there, and no
    row gets ≈ for them."""
    old = (QTODAY - (QHS + timedelta(days=rb.gcu.QL + 1))).days + 1
    wk = [date(2025, 3, 10) + timedelta(days=i) for i in range(7)]           # QHS ages 68 … 74 only
    D = QHS + timedelta(days=31)
    ns = {d: 700 for d in wk}
    ns.update({D + timedelta(days=i): 1 for i in range(400)})                 # 1 micro on 400 days
    P, co = _q_world(tmp_path / "n", b=10000, nset=ns)
    late, by = _qrows(tmp_path / "n", P, co)
    assert late["info"]["qd"] == (QTODAY - QHS).days + 1 and late["info"]["qwait"] == late["info"]["qfl"] == 0
    assert late["info"]["qn"] == pytest.approx(sum(ns.values()) * 2 / 1e6) and late["info"]["ql"] == 0
    assert late["info"]["qpos"] == late["info"]["qneg"] == 0
    assert by[QHS]["m"][:13] == pytest.approx([62 + 0.6 * j for j in range(1, 14)], abs=1e-4) and not by[QHS]["qo"]
    P, co = _q_world(tmp_path / "m", nset={d: 700 for d in wk})             # with the cube's own loss too
    late, _ = _qrows(tmp_path / "m", P, co)
    assert late["info"]["ql"] == pytest.approx(old * 0.004, abs=1e-8) and late["info"]["qn"] == pytest.approx(
        7 * 700 * 2 / 1e6)


def test_q_a_read_naming_fewer_install_days_stays_on_the_cube(tmp_path):
    """A whole read whose window shrank (q names fewer install days than the cube kept, j ≤ 13): never on q — the
    week from the cube's cells ("qshort"; its loss days "qfl", on the cube for good), never a 0 for the install days q
    missed; a hot day the same (until its next read)."""
    wk = [date(2025, 6, 9) + timedelta(days=i) for i in range(7)]            # QHS ages 159 … 165 (bucket 5)
    P, co = _q_world(tmp_path / "s", drop={d: {QHS} for d in wk} | {QTODAY: {QX1}})
    late, by = _qrows(tmp_path / "s", P, co)
    assert by[QHS]["m"][4] == pytest.approx(65.0 - 7 * 0.004, abs=1e-4)      # the cube's 0.8, not q's 0
    assert late["info"]["qshort"] == 1 and late["info"]["qfl"] == 7 and late["info"]["qpos"] == 0
    assert late["info"]["qwait"] == 1                                         # the hot day: read again next round
    assert by[QX1]["m"] == pytest.approx([62.6, 63.2 - 0.004], abs=1e-4) and by[QX1]["qo"] == 2
    lo = QHS + timedelta(days=31)
    assert late["q"](lo, QHS + timedelta(days=180), 5) == 2 and late["q"](lo, QHS + timedelta(days=150), 4) == 0


def test_q_drift_never_turns_young_loss_into_loss_past_420(tmp_path):
    """A week whose whole read holds LESS than the cube kept (drift, "qpos"): where the cube's loss sits that week is
    not known — nothing added to ql (its size said as drift, "qdr"), its days ≈ past 420 (it lost something)."""
    old = (QTODAY - (QHS + timedelta(days=rb.gcu.QL + 1))).days + 1
    wk = [date(2026, 8, 24) + timedelta(days=i) for i in range(7)]           # QHS ~600 days old, QX1 ~40
    P, co = _q_world(tmp_path / "a", b=9000)
    base, _ = _qrows(tmp_path / "a", P, co)
    assert base["info"]["ql"] == pytest.approx(old * 0.002, abs=1e-8)        # 1000 a day past 420 (QHS), × k 2
    P, co = _q_world(tmp_path / "b", b=9000, more={d: -15000 for d in wk})
    late, by = _qrows(tmp_path / "b", P, co)
    assert late["info"]["ql"] == pytest.approx((old - 7) * 0.002, abs=1e-8) and late["info"]["qpos"] == 1
    assert late["info"]["qdr"] == pytest.approx((7 * (1000 + 15000) - 7 * 2000) * 2 / 1e6)
    assert late["q"](wk[0], wk[-1], 20) == 2                                  # a row whose ages there are all past 420


def test_q_loss_below_a_cent_is_never_zero(tmp_path):
    """A measured loss past D420 below $0.005 is written to the micro (never 0 while rows carry ≈ for it)."""
    old = (QTODAY - (QHS + timedelta(days=rb.gcu.QL + 1))).days + 1
    P, co = _q_world(tmp_path / "t", b=9995)
    late, by = _qrows(tmp_path / "t", P, co)
    assert 0 < late["info"]["ql"] < 0.005 and late["info"]["ql"] == pytest.approx(old * 5 * 2 / 1e6, abs=1e-8)
    assert by[QHS]["qo"] == 2


def test_q_flag_bit_only_where_the_row_uses_the_cubes_cells(tmp_path):
    """≈ bit 4 (GA4 flagged the cube's read) on an All row only for a day whose cells the row takes from the cube: a
    flagged day on a week read whole counts only for the row's ages past 420; on a week still on the cube, every age."""
    young = date(2025, 3, 12)                                                 # QHS age 70: its D90 from q
    P, co = _q_world(tmp_path / "a", b=10000, cfl={young})
    late, by = _qrows(tmp_path / "a", P, co)
    assert late["info"]["loss"] == 1 and not by[QHS]["qo"]
    assert late["q"](QHS + timedelta(days=31), QHS + timedelta(days=90)) == 4  # the country rows: the cube's cells
    P, co = _q_world(tmp_path / "b", b=10000, cfl={young}, skip={young})     # its week not on q: the cube's cells
    late, by = _qrows(tmp_path / "b", P, co)
    assert by[QHS]["qo"] == 4
    past = QHS + timedelta(days=500)                                          # QHS age 500: always the cube's cells
    P, co = _q_world(tmp_path / "c", b=10000, cfl={past})
    late, by = _qrows(tmp_path / "c", P, co)
    assert by[QHS]["qo"] == 4 and late["q"](QHS + timedelta(days=31), QHS + timedelta(days=420), 13) == 0


def test_q_days_of_nothing_need_no_read(tmp_path):
    """Days with no revenue, loss or flag (fetch.ga4_cube never reads them): their weeks still on q, exactly as when
    each was read (an empty whole read)."""
    zero = {date(2025, 2, 10), date(2025, 2, 11), date(2025, 2, 12)}         # inside the week Feb 10 … 16
    P, co = _q_world(tmp_path / "z", nothing=zero, skip=zero)
    late, by = _qrows(tmp_path / "z", P, co)
    assert late["info"]["qd"] == (QTODAY - QHS).days + 1 and late["info"]["qwait"] == late["info"]["qfl"] == 0
    P1, co1 = _q_world(tmp_path / "w", nothing=zero)
    late1, by1 = _qrows(tmp_path / "w", P1, co1)
    assert late["B"] == late1["B"] and late["info"] == late1["info"]
    assert by[QHS]["m"][0] == pytest.approx(62.6 - 3 * 0.02, abs=1e-4)


def test_country_not_given_per_month(tmp_path):
    """cd.ng = All − Σ countries per activity month: the app's k × the ledger's every row − Σ k_c × each country's GA4
    (the "--" row on the app's k), signed; "own" where the countries' own AdMob match carries the month, else "app" —
    there it is the measured "(other)" × k (in no country row)."""
    loss = {date(2026, 9, 20): 500000, date(2026, 10, 5): 300000}
    data, P, pre, spend, acc = _cc_world(tmp_path, loss=loss)
    cd, od, _ = _cc_run(tmp_path, data, P, pre, spend, acc)
    kc = {"AA": {"2026-08": 1.5, "2026-09": 1.0, "2026-10": 1.2}, "CC": {"2026-08": 2.0, "2026-09": 2.0, "2026-10": 1.2}}
    ng, all_ = cd["ng"], 0.0
    for M in ("2026-08", "2026-09", "2026-10"):
        lo = sum(v for D, v in loss.items() if D.isoformat()[:7] == M)
        tot = sum(_ga4_month(cc, M) for cc in CRATE) + lo
        s = sum((kc.get(cc) or {}).get(M, 1.2) * _ga4_month(cc, M) for cc in CRATE) / 1e6
        assert ng["m"][M][0] == pytest.approx(1.2 * tot / 1e6 - s, abs=0.01), M
        assert ng["m"][M][1] == cd["kc"]["unp"][M]
        all_ += 1.2 * tot / 1e6
    assert [ng["m"][M][2] for M in ("2026-08", "2026-09", "2026-10")] == ["own", "own", "app"]
    assert ng["m"]["2026-10"][0] == pytest.approx(1.2 * 0.3, abs=0.01)        # the app's k: exactly k × "(other)"
    assert ng["m"]["2026-08"][0] < 0                                           # signed (AA's k_c 1.5 > the app's 1.2)
    assert ng["usd"] == pytest.approx(sum(v[0] for v in ng["m"].values()), abs=0.01)
    assert ng["all"] == pytest.approx(all_, abs=0.01) and ng["rel"] == round(ng["usd"] / ng["all"], 4)


def test_q_read_weeks_after_the_cube_is_a_bound(tmp_path):
    """The history fill: a week's whole read made weeks after its cube read is not of one moment — the gap past D420
    may hold GA4's own change between the two reads, so it is "qlb" (at most), never the exact "ql"; the columns the
    rows show are the same either way."""
    P, co = _q_world(tmp_path / "s")
    same, by_s = _qrows(tmp_path / "s", P, co)
    P2, co2 = _q_world(tmp_path / "l", q_at="2026-11-03T06:00:00Z")
    late, by_l = _qrows(tmp_path / "l", P2, co2)
    old = (QTODAY - (QHS + timedelta(days=rb.gcu.QL + 1))).days + 1
    assert same["info"]["ql"] == pytest.approx(old * 0.004, abs=1e-8) and same["info"]["qlb"] == 0
    # the folded weeks read later → a bound; the hot days (their whole read in the same run as their cube read) stay exact
    assert late["info"]["qlb"] + late["info"]["ql"] == pytest.approx(old * 0.004, abs=1e-8)
    assert late["info"]["qlb"] > 0.9 * old * 0.004 and 0 < late["info"]["ql"] < 0.1 * same["info"]["ql"]
    assert by_l[QHS]["m"] == by_s[QHS]["m"] and by_l[QHS]["qo"] == by_s[QHS]["qo"]
    assert rb._same({"at": "2026-10-13T06:00:00Z"}, {"at": "2026-10-13T07:59:00Z"})
    assert not rb._same({"at": "2026-10-13T06:00:00Z"}, {"at": "2026-10-13T08:01:00Z"})
    assert not rb._same({}, {"at": "2026-10-13T06:00:00Z"}) and not rb._same({"at": "x"}, {"at": None})


def test_country_geo_day_short_rest_is_not_split():
    """Google Ads' geographic report names a country for all but a small part of a day's cost (≤ GEO_SHORT_MAX): the
    day is known — each country its own cost, the rest "Not split" (never given to a country); more than that short,
    or more than the spend cache: unknown as before."""
    days = [date(2026, 9, 1) + timedelta(days=i) for i in range(3)]
    k = [d.isoformat() for d in days]
    sdaily = {"s1": {x: 100_000_000 for x in k}}
    geo = {"days": {"s1": {k[0]: {"AA": [60_000_000, 1.0], "BB": [38_000_000, 2.0]},       # 2% has no country
                           k[1]: {"AA": [60_000_000, 1.0], "BB": [34_000_000, 2.0]},       # 6%: too much
                           k[2]: {"AA": [60_000_000, 1.0], "BB": [42_000_000, 2.0]}}}}     # 2% more than spent
    spend = {"first": k[0], "till": (days[-1] + timedelta(days=rb.GEO_SHORT_SETTLE)).isoformat()}
    cost, unk, st = rb._geo_app(geo, ["s1"], sdaily, spend, days)
    assert unk == {days[1], days[2]} and st["untied_days"] == 2 and st["short_days"] == 1
    assert cost["AA"] == {days[0]: (60_000_000, 1.0)} and cost["BB"] == {days[0]: (38_000_000, 2.0)}
    assert cost[rb.NOT_SPLIT] == {days[0]: (2_000_000, None)} and st["xx_share"] == 0.02
    assert st["short_share"] == 0.02

    # a day still settling (within GEO_SHORT_SETTLE days of the spend cache's last day): its split may be short only
    # because its cost was still being booked when the geo step read it — unknown until it ties
    cost, unk, st = rb._geo_app(geo, ["s1"], sdaily, {"first": k[0], "till": k[0]}, days[:1])
    assert unk == {days[0]} and st["untied_days"] == 1 and st["short_days"] == 0 and not cost
    # two short stores on one install day: one short day, both rests in Not split
    sd2 = {"s1": {k[0]: 100_000_000}, "s2": {k[0]: 50_000_000}}
    g2 = {"days": {"s1": {k[0]: {"AA": [98_000_000, 1.0]}}, "s2": {k[0]: {"BB": [48_000_000, 1.0]}}}}
    cost, unk, st = rb._geo_app(g2, ["s1", "s2"], sd2, spend, days[:1])
    assert not unk and st["short_days"] == 1 and cost[rb.NOT_SPLIT] == {days[0]: (4_000_000, None)}


# ── 👥 users: on each 30-day column's day (All rows: mu) and day by day + each column's day (the country rows) ────────
def _uw(data, M, q=None, c=None, sid="222"):
    """A users' month file (fetch.ga4_cube u) as the fetch writes it."""
    from admob_iq.fetch import ga4_cube as cu
    os.makedirs(cu.app_dir(str(data), "a~1"), exist_ok=True)
    cu.write_json_gz_stable(cu.u_path(str(data), "a~1", M), {"v": cu.U_V, "stream_id": sid, "q": q or {}, "c": c or {}})


def _uhw(data, d, sid="222"):
    """The users' head (its hot days) as the fetch writes it."""
    from admob_iq.fetch import ga4_cube as cu
    os.makedirs(cu.app_dir(str(data), "a~1"), exist_ok=True)
    cu.write_json_gz_stable(cu.uhead_path(str(data), "a~1"), {"v": cu.U_V, "stream_id": sid, "d": d})


def test_mu_from_an_iday_fixture_then_a_whole_reads_users():
    """All rows' mu (users active on exactly each 30-day column's day, aligned with m): the install-day file's users
    (fetch.ga4_uninstall ULAGS 60 / 90 / 120 / 180 / 270 — 365 is no column's day) where that activity day is folded
    there and its Q-B window reached the age; else a whole no-country read's (u "q", ages ≤ 420: its horizon); else
    null. A row with nothing known gets no mu."""
    from admob_iq.engine import value as val
    from admob_iq.fetch import ga4_cube as cu
    hs, S = date(2026, 1, 1), date(2026, 10, 7)
    X = hs
    days, D = {}, hs
    while D <= S:
        days[D.isoformat()] = {"st": "ok", "win": (D - hs).days}
        D += timedelta(days=1)
    days[(X + timedelta(days=90)).isoformat()]["st"] = "retry"            # not folded: none of its users known there
    days[(X + timedelta(days=120)).isoformat()]["win"] = 100               # its Q-B window stopped short of age 120
    ida = {"x": {X.isoformat(): {"n": 1000, "u": [1000, 500, 400, 300, 200, 150, 120, 100, 80, 60, 40, 30, 20],
                                 "r": [0] * 10}},
           "days": days, "flags": {"qb_win": True}, "to": S.isoformat(), "from": hs.isoformat()}
    P = val._prep({"history_start": hs.isoformat(), "time_zone": "UTC"}, ida, None, None, S)
    rows = [{"X": X, "m": [0.0] * 14}]                                      # columns D60 … D450
    rb._mu_all(rows, P, {"uq": {}})
    assert rows[0]["mu"] == [100, None, None, None, 40, None, None, 30, None, None, None, None, None, None]
    assert rb.gu.ULAGS[-1] == 365 and 365 % rb.LATE_STEP                  # 365: no column's day
    uq = {X + timedelta(days=A): [7000 + A] * len(cu.UQ_AGES) for A in (60, 90, 120, 150, 360, 450)}
    uq[date(2026, 10, 31)] = [55] * len(cu.UQ_AGES)
    rows = [{"X": X, "m": [0.0] * 14}, {"X": date(2026, 9, 1), "m": [0.0]}, {"X": date(2026, 8, 20), "m": [0.0]},
            {"X": date(2026, 9, 2)}]
    rb._mu_all(rows, P, {"uq": uq})
    # 60: the install-day file first; 90 / 120: a whole read's (the file's day not folded / window short); 150 / 360:
    # only a whole read has them; 450: past its horizon (420) — null even with a read of that day
    assert rows[0]["mu"] == [100, 7090, 7120, 7150, 40, None, None, 30, None, None, 7360, None, None, None]
    assert rows[1]["mu"] == [55] and "mu" not in rows[2] and "mu" not in rows[3]   # past the file: a read's / none
    r = dict(X=X, n=1, na=None, sp=None, d=None, df=0, u=None, t=[None] * 10, s=None, sd=None, be=None, spi=None,
             m=[1.0, 2.0], mf=2)
    assert rb._row_out(dict(r, mu=[5, None]))[14:] == [[1.0, 2.0], 2, [5, None]] and len(rb._row_out(r)) == 16


def test_mu_from_the_users_files_through_the_build(tmp_path, monkeypatch):
    """_late reads the users' files with the cube's months (their folded days only; a hot day's only beside its very
    read); a not-whole read is null; the file's "late" counts them; GA4_CUBE_U_USE=false ignores them."""
    from admob_iq.fetch import ga4_cube as cu
    P, co = _cube_setup(tmp_path)                       # the install-day file: 100 users at every age, through LS
    X = LHS
    _uw(tmp_path, "2026-08", q={"2026-08-29": {"s": "ok", "at": "x", "u": [0, 0, 0, 33] + [0] * 9}})   # X + 150
    _uw(tmp_path, "2026-09", q={"2026-09-28": {"s": "fl", "at": "x"}, "2026-09-12": {"s": "ok", "at": "x",
                                                                                      "u": [11] * 13}})
    hot_at = "2026-10-13T06:00:00Z"                     # the hot days' read in _cube_setup
    _uhw(tmp_path, {"2026-10-12": {"q": {"s": "ok", "at": hot_at, "u": [44] + [0] * 12}},
                    "2026-10-13": {"q": {"s": "ok", "at": "2026-10-12T00:00:00Z", "u": [45] + [0] * 12}}})
    late = rb._late(str(tmp_path), "a~1", "222", P)
    assert late["info"]["u"] == {"q": 2, "qfl": 1, "c": 0}
    by = _rows(P, co, late)
    rb._mu_all(list(by.values()), P, late)
    assert by[X]["mu"] == [100, 100, 100, 33, 100]                          # 150 from the users' file
    assert by[date(2026, 4, 15)]["mu"] == [100, 100, 100, 11, 0]            # day 150 = Sep 12; day 180 = Oct 12:
    assert by[date(2026, 7, 14)]["mu"] == [100, 0]                          # hot, its own read (0 at that age)
    assert by[date(2026, 8, 13)]["mu"] == [44]                              # day 60 = Oct 12
    assert "mu" not in by[date(2026, 8, 14)]                                # Oct 13: another read's — unknown
    monkeypatch.setattr(cu, "U_USE", False)
    off = rb._late(str(tmp_path), "a~1", "222", P)
    assert "u" not in off["info"] and off["uq"] == {} and off["info"] == {k: v for k, v in late["info"].items()
                                                                          if k != "u"}


def test_app_step_mu_and_the_users_switch(tmp_path, monkeypatch):
    """The file: index 16 (mu) on rows with columns where a user count is known, late "u" with users' files; with
    GA4_CUBE_U_USE=false every byte of it as without users (no index 16, no late "u")."""
    from admob_iq.fetch import ga4_cube as cu
    P, co = _cube_setup(tmp_path / "data")
    _stub_app(monkeypatch, P, co, SPEND)
    _uw(tmp_path / "data", "2026-08", q={"2026-08-29": {"s": "ok", "at": "x", "u": [0, 0, 0, 33] + [0] * 9}})
    full = json.loads(_app_step_run(str(tmp_path / "data"), str(tmp_path / "o1"), True))
    assert full["rows"][0][16] == [100, 100, 100, 33, 100] and full["late"]["u"] == {"q": 1, "qfl": 0, "c": 0}
    monkeypatch.setattr(cu, "U_USE", False)
    off = json.loads(_app_step_run(str(tmp_path / "data"), str(tmp_path / "o2"), True))
    assert {len(r) for r in off["rows"]} == {14, 16} and "u" not in off["late"]
    full["rows"] = [r[:16] for r in full["rows"]]
    full["sum"]["today"] = [r[:16] for r in full["sum"]["today"]]
    full["late"].pop("u")
    assert full == off


def _cc_users(data, skip=(), ou=None, fl=(), hot_at=None, extra=None):
    """Users' files for the country world (_cc_cube): each day's users of every country at ages 1 … 30 = its installs
    a day, at age 60 = half of them; the hot days' in the users' head (with their read's "at", or hot_at's); skip: days
    with no users kept; ou {D: users GA4 left "(other)"}; fl: days flagged; extra {(cc, X, age): users} more."""
    at, months, hot = "2026-10-13T06:00:00Z", {}, {}
    D = CHS
    while D <= CTODAY:
        if D not in skip:
            u, w = {}, {}
            for cc, n in CINST.items():
                u[cc] = [n if D - timedelta(days=L) >= CHS else 0 for L in range(31)]
                if D - timedelta(days=60) >= CHS:
                    w[cc] = {"60": n // 2}
            for (cc, X, L), v in (extra or {}).items():
                if X + timedelta(days=L) == D:
                    u[cc] = [0] * L + [v]
            rec = {"u": u, "w": w, "ou": (ou or {}).get(D, 0), "fl": 1 if D in fl else 0, "at": at, "by": "fold"}
            if D >= CHOT:
                hot[D.isoformat()] = {"c": dict(rec, at=(hot_at or {}).get(D, at))}
            else:
                months.setdefault(D.isoformat()[:7], {})[D.isoformat()] = rec
        D += timedelta(days=1)
    for M, c in months.items():
        _uw(data, M, c=c)
    _uhw(data, hot)


def test_country_users_day_by_day_columns_bits_and_zero_rows(tmp_path):
    """🌍 + 👥 Every country row gets u (day 0 = its installs, then each day's users kept, null where a day's are not)
    and mu (each 30-day column's day); a day with users GA4 left "(other)" → ≈ bit 2, flagged → 4 (their size in cd
    "uu", never spread); a hot day's users only beside its own read; a country with users only gets its rows; a row
    with no user and nothing else stays [X]; without users' files every byte as before (the other tests)."""
    kw = dict(inst=dict(CINST, EE=3), rate=dict(CRATE, EE=50000), only={"EE": {date(2026, 9, 5), date(2026, 9, 6)}})
    data, P, pre, spend, acc = _cc_world(tmp_path, **kw)
    cd0, od0, _ = _cc_run(tmp_path, data, P, pre, spend, acc, out="o0")      # no users' file
    assert "uu" not in cd0
    base = {cc: {r[0]: r for r in _expand(rows, cd0, cc)} for cc, rows in _pack_rows(od0, cd0).items()}
    assert all(r[6] is None and len(r) <= 16 for rs in base.values() for r in rs.values())
    hole, oday, fday = date(2026, 9, 10), date(2026, 9, 20), date(2026, 9, 25)
    _cc_users(data, skip={hole}, ou={oday: 7}, fl={fday}, hot_at={CTODAY: "2026-10-12T00:00:00Z"},
              extra={("FF", date(2026, 9, 1), 5): 3})
    cd, od, _ = _cc_run(tmp_path, data, P, pre, spend, rb.start(cube=True, cmon=acc.cmon), out="o1")
    days = (CTODAY - CHS).days + 1
    assert cd["uu"] == {"days": days - 2, "zero": 0, "ou_days": 1, "ou": 7, "fl_days": 1}   # the hole, Oct 13's other read
    got = _pack_rows(od, cd)
    assert set(got) == set(base) | {"FF"}
    AA = {r[0]: r for r in _expand(got["AA"], cd, "AA")}
    r = AA["2026-09-01"]
    assert r[6] == [40] + [None if L == 9 else 40 for L in range(1, 31)] and len(r[6]) == len(r[4])
    assert r[12] & 6 == 6 and not base["AA"]["2026-09-01"][12] & 6         # Sep 20 ("(other)") and Sep 25 (flag)
    assert AA["2026-08-05"][16] == [20] and AA["2026-08-12"][16] == [20]    # day 60: Oct 4 / Oct 11 (hot, its read)
    assert len(AA["2026-08-14"]) == 16                                      # day 60 = Oct 13: another read's — none
    assert AA["2026-10-10"][6] == [40, 40, 40, None] and AA["2026-10-13"][6] == [40]
    assert AA["2026-10-01"][12] & 6 == 0                                    # its days after Sep 25
    NC = {r[0]: r for r in _expand(got["--"], cd, "--")}
    assert NC["2026-09-02"][6][1] == 2 and NC["2026-09-02"][6][8] is None   # "Unknown country" too
    for cc, rs in base.items():                                             # every other cell as without users
        for X, r0 in rs.items():
            r1 = {r[0]: r for r in _expand(got[cc], cd, cc)}[X]
            assert r1[:6] + r1[7:12] + r1[13:16] == r0[:6] + r0[7:12] + r0[13:16], (cc, X)
            assert r1[12] & ~6 == r0[12] & ~6 and (cc not in ("XX",) or r1[6] is None)
    # a country with users only (no installs, no revenue): its row with them; its other days [X]
    FF = _expand(got["FF"], cd, "FF")
    full_ff = [x for x in got["FF"] if len(x) > 1]
    assert len(full_ff) == 1 and full_ff[0][0] == "2026-09-01" and full_ff[0][1] == 0
    assert full_ff[0][6] == [0, 0, 0, 0, 0, 3, 0, 0, 0, None] + [0] * 21 and len(FF) == days
    # a row with no user and nothing else: [X] as without users (the page has nothing to show of it)
    assert sum(len(x) == 1 for x in got["EE"]) == sum(len(x) == 1 for x in _pack_rows(od0, cd0)["EE"]) == days - 2
    # the packs' build stamp covers the users: a user count moved → a new "b"
    _cc_users(data, skip={hole}, ou={oday: 7}, fl={fday}, hot_at={CTODAY: "2026-10-12T00:00:00Z"},
              extra={("FF", date(2026, 9, 1), 5): 4})
    cd2, _, _ = _cc_run(tmp_path, data, P, pre, spend, rb.start(cube=True, cmon=acc.cmon), out="o2")
    assert cd2["b"] != cd["b"] and cd2["b"] != cd0["b"]
    cd3, _, _ = _cc_run(tmp_path, data, P, pre, spend, rb.start(cube=True, cmon=acc.cmon), out="o3")
    assert cd3 == cd2                                                       # the same files: the same bytes


def test_country_users_packs_stay_under_pack_max(tmp_path, monkeypatch):
    """With users the rows are longer: the packs still fill to PACK_MAX in the index's order (a bigger country alone),
    every country in exactly one, each saying its build."""
    data, P, pre, spend, acc = _cc_world(tmp_path)
    _cc_users(data)
    monkeypatch.setattr(rb, "PACK_MAX", 30_000)
    cd, od, _ = _cc_run(tmp_path, data, P, pre, spend, acc)
    got = _pack_rows(od, cd)
    assert len(cd["packs"]) >= 3 and set(got) == {x[0] for x in cd["c"]}
    assert all(r[6] is not None for r in got["AA"] if len(r) > 1)
    for name, _ in cd["packs"]:
        with gzip.open(os.path.join(str(od), name), "rb") as f:
            raw = f.read()
        ix = int(name.split("_c")[1][:2])
        if sum(1 for x in cd["c"] if x[4] == ix) > 1:
            assert len(raw) <= 30_000 + 200
        assert json.loads(raw)["b"] == cd["b"]
