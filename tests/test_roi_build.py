"""📈 ROI (a section of the 💸 Install value tab) — the build step (admob_iq.roi_build), on made-up data: every install day
with its day-by-day revenue (the exact store × the engine's scale k), the checkpoints only when complete, the breakeven
day, the status vs usual, install months (one set of days per curve: never dips), payback from the newest month, the
lifetime P/L days, the countries board (Scale / Keep / Watch / Cut …) and what cutting saves, the portfolio file, the
pointer, one splat header rule, failure isolation and a counts-only line."""
import gzip
import json
import os
from datetime import date, timedelta

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
    acc.apps.append({"app_id": "a~1", "app": "Alpha", "key": "aaaaaaaaaaaa", "file": "roi_aaaaaaaaaaaa.json.gz",
                     "st": "Worse", "r7": 0.4, "u7": 0.6, "pb": 40, "life": [10.0, 12.0], "cut": 2})
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
    assert body["months"][0][0] == "2026-10"
    assert not os.path.exists(os.path.join(out, "roi_0123456789ab.json.gz"))   # stale file removed
    line = rb.pop_line()
    assert line.startswith("roi: apps 1, worse 1") and "Alpha" not in line
    acc2 = rb.start()
    dash2 = {}
    assert rb.finish(acc2, dash2, out) == [] and "roi" not in dash2
    assert not any(f.startswith("roi") for f in os.listdir(out))
    assert rb.enabled({}) and not rb.enabled({"roi_tab": False})
