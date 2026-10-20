"""🧊 The cohort cube (admob_iq.fetch.ga4_cube), offline with a fake GA4 and made-up numbers: the query (dimensions
date × firstSessionDate × countryId, no install-day filter, every page), the adaptive read (a block → its days alone when
GA4 rolls rows into "(other)" or flags the answer → a day split by its biggest ~1/8 countries and the rest; what stays
"(other)" kept as that day's measured loss, never spread), "(not set)" country → "--", a non-date install day or one
after the activity day → loss, GA4's flags kept per day, the fold shapes (b / c / e / t / loss + the ledger), month
files that never change once folded, the hot days replaced on each re-read and read once more when final, ONE cursor (a
Stop, a pause, a new day: no hole, no day folded from a read made while it was still filling), the heavy-range memory,
the history start moving back, another stream, the run over properties with a counts-only line, and the build hook
(off: nothing read, written or printed)."""
import copy
import gzip
import json
import os
from datetime import date, datetime, timedelta, timezone

from admob_iq.fetch import ga4_cube as cu
from admob_iq.fetch import ga4_firstopen as gf

HS = date(2026, 6, 1)
TODAY = date(2026, 10, 13)
NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)
W = {"AA": 8, "BB": 6, "CC": 4, "DD": 2, "(not set)": 2}          # every country's weight (made up)
WSUM = sum(W.values())


def ymd(d):
    return d.strftime("%Y%m%d")


def _days(a, b):
    out = []
    while a <= b:
        out.append(a)
        a += timedelta(days=1)
    return out


class FakeGA:
    """GA4 for the cube. Activity day D, install day X (start … D, lag ≤ max_lag), country cc: revenue
    (lag + 1) × W[cc] × 100 micros, users 10 × W[cc] at lag 0. A day still filling (today − D < FINAL_LAG) reads
    `fill` of that. cap: an answer with more rows keeps its `cap` biggest and rolls the rest into a per-day "(other)"
    row (dataLossFromOtherRow). extra_day: 40 more countries "Q00" … that day (lags 0 … 30, weight 1). notset_day /
    neg_day: one row with install day "(not set)" / after the activity day. thr_day: any answer holding it says
    thresholding. smp_multi / cut_multi: a multi-day answer says sampling / was cut. stop_after: Stop at that call."""

    def __init__(self, today=TODAY, cap=None, stop_after=None, fill=0.5, start=HS, max_lag=120, extra_day=None,
                 notset_day=None, neg_day=None, thr_day=None, smp_multi=False, cut_multi=False, oth_flag_day=None):
        self.today, self.cap, self.stop_after, self.fill, self.start, self.max_lag = (today, cap, stop_after, fill,
                                                                                      start, max_lag)
        self.extra_day, self.notset_day, self.neg_day, self.thr_day = extra_day, notset_day, neg_day, thr_day
        self.smp_multi, self.cut_multi, self.oth_flag_day = smp_multi, cut_multi, oth_flag_day
        self.calls, self.asked, self.tok, self.last_metas, self._cut = 0, [], 0, [], False

    def rows_of(self, D):
        f = self.fill if (self.today - D).days < cu.FINAL_LAG else 1.0
        rows = []
        for L in range(self.max_lag + 1):
            X = D - timedelta(days=L)
            if X < self.start:
                break
            for cc, w in W.items():
                rows.append({"date": ymd(D), "firstSessionDate": ymd(X), "countryId": cc,
                             "activeUsers": 10 * w if L == 0 else w, "totalAdRevenue": (L + 1) * w * f / 10000})
        if D == self.extra_day:
            for i in range(40):
                for L in range(31):
                    rows.append({"date": ymd(D), "firstSessionDate": ymd(D - timedelta(days=L)), "countryId": "Q%02d" % i,
                                 "activeUsers": 1, "totalAdRevenue": (L + 1) * f / 10000})
        if D == self.notset_day:
            rows.append({"date": ymd(D), "firstSessionDate": "(not set)", "countryId": "AA", "activeUsers": 3,
                         "totalAdRevenue": 0.5 * f})
        if D == self.neg_day:
            rows.append({"date": ymd(D), "firstSessionDate": ymd(D + timedelta(days=1)), "countryId": "BB",
                         "activeUsers": 1, "totalAdRevenue": 0.25 * f})
        return rows

    def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise gf.Stop("calls")
        self.calls += 1
        self.asked.append((body, extra, page_rows, self.today))
        a, b = (date.fromisoformat(body["dateRanges"][0][k]) for k in ("startDate", "endDate"))
        keep = None
        for ex in extra or []:
            if "notExpression" in ex:
                vals = set(ex["notExpression"]["filter"]["inListFilter"]["values"])
                keep = (lambda cc, v=vals: cc not in v)
            else:
                vals = set(ex["filter"]["inListFilter"]["values"])
                keep = (lambda cc, v=vals: cc in v)
        rows = [r for D in _days(a, b) for r in self.rows_of(D) if keep is None or keep(r["countryId"])]
        meta = {}
        if self.cap is not None and len(rows) > self.cap:
            rows.sort(key=lambda r: (-r["totalAdRevenue"], r["date"], r["firstSessionDate"], r["countryId"]))
            oth = {}
            for r in rows[self.cap:]:
                o = oth.setdefault(r["date"], [0, 0.0])
                o[0] += r["activeUsers"]
                o[1] += r["totalAdRevenue"]
            rows = rows[:self.cap] + [{"date": D, "firstSessionDate": "(other)", "countryId": "(other)",
                                       "activeUsers": u, "totalAdRevenue": v} for D, (u, v) in sorted(oth.items())]
            meta["dataLossFromOtherRow"] = True
        if self.oth_flag_day and a <= self.oth_flag_day <= b:
            meta["dataLossFromOtherRow"] = True                 # the flag with no "(other)" row to measure it by
        if self.thr_day and a <= self.thr_day <= b:
            meta["subjectToThresholding"] = True
        if self.smp_multi and a < b:
            meta["samplingMetadatas"] = [{"samplesReadCount": "1", "samplingSpaceSize": "2"}]
        self._cut = self.cut_multi and a < b
        self.last_metas = [{}, meta]                            # the flag on any page counts
        return rows

    def truncated(self, rows):
        return self._cut


def micros(L, w=1, f=1.0):
    return round((L + 1) * w * f / 10000 * 1e6)


def day_total(fake, D):
    return sum(round(float(r["totalAdRevenue"]) * 1e6) for r in fake.rows_of(D))


def _rec_sum(rec):
    """Every micro of a day's record: b + e's r + loss (must be the day's total: nothing dropped, nothing doubled)."""
    s = sum(v for js in rec["b"].values() for ws in js.values() for v in ws.values())
    s += sum(sum(a[1:]) for xs in rec["e"].values() for a in xs.values())
    return s + rec["loss"]


def _multi(fake):
    return [(q[0]["dateRanges"][0]["startDate"], q[0]["dateRanges"][0]["endDate"]) for q in fake.asked
            if q[0]["dateRanges"][0]["startDate"] != q[0]["dateRanges"][0]["endDate"]]


# ── the read ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_body_and_one_day_shapes():
    b = cu.body(date(2026, 9, 1), date(2026, 9, 30))
    assert [d["name"] for d in b["dimensions"]] == ["date", "firstSessionDate", "countryId"]
    assert [m["name"] for m in b["metrics"]] == ["activeUsers", "totalAdRevenue"]
    assert b["currencyCode"] == "USD" and b["keepEmptyRows"] is False and "dimensionFilter" not in b
    assert cu.bucket(31) == 1 and cu.bucket(60) == 1 and cu.bucket(61) == 2 and cu.bucket(90) == 2 and cu.bucket(91) == 3
    D = date(2026, 9, 2)                                       # a Wednesday: its week's Monday = Aug 31
    rows = [{"date": "20260902", "firstSessionDate": "20260902", "countryId": "AA", "activeUsers": 5, "totalAdRevenue": 0.01},
            {"date": "20260902", "firstSessionDate": "20260831", "countryId": "AA", "activeUsers": 4, "totalAdRevenue": 0.02},
            {"date": "20260902", "firstSessionDate": "20260803", "countryId": "AA", "activeUsers": 1, "totalAdRevenue": 0.07},
            {"date": "20260902", "firstSessionDate": "20260802", "countryId": "BB", "activeUsers": 2, "totalAdRevenue": 0.03},
            {"date": "20260902", "firstSessionDate": "20260704", "countryId": "(not set)", "activeUsers": 1, "totalAdRevenue": 0.05},
            {"date": "20260902", "firstSessionDate": "20260703", "countryId": "", "activeUsers": 1, "totalAdRevenue": 0.04},
            {"date": "20260902", "firstSessionDate": "20260702", "countryId": "CC", "activeUsers": 9, "totalAdRevenue": 0},
            {"date": "20260902", "firstSessionDate": "(not set)", "countryId": "AA", "activeUsers": 1, "totalAdRevenue": 0.06},
            {"date": "20260902", "firstSessionDate": "20260601", "countryId": "(other)", "activeUsers": 1, "totalAdRevenue": 0.08},
            {"date": "20260902", "firstSessionDate": "20260903", "countryId": "BB", "activeUsers": 1, "totalAdRevenue": 0.09}]
    acc = cu._group(rows, D)["2026-09-02"]
    rec = cu._rec(acc, "day", 0, "2026-10-13T06:00:00Z")
    assert rec["e"] == {"AA": {"2026-09-02": [5, 10000], "2026-08-31": [0, 0, 0, 20000],
                               "2026-08-03": [0] + [0] * 30 + [70000]}}            # lag 30: the last daily slot
    assert rec["b"] == {"2026-08-02": {"1": {"2026-08-31": 30000}},               # lag 31: bucket 1
                        "2026-07-04": {"1": {"2026-08-31": 50000}},               # lag 60: still bucket 1
                        "2026-07-03": {"2": {"2026-08-31": 40000}}}               # lag 61: bucket 2
    assert rec["c"] == {"BB": {"2026-08-02": {"1": 30000}}, "--": {"2026-07-04": {"1": 50000}, "2026-07-03": {"2": 40000}}}
    # "(not set)" install day, a real install day of country "(other)", an install day after the activity day: loss
    assert rec["loss"] == 60000 + 80000 + 90000 and rec["t"] == 450000 and _rec_sum(rec) == rec["t"]
    assert rec["rows"] == 10 and rec["st"] == "loss" and rec["fl"] == 0 and rec["via"] == "day"
    assert set(rec) == set(cu.LEDGER) | {"b", "c", "e"}


def test_a_flag_on_any_page_counts():
    """ga4.Ga4App.report_all keeps every page's metadata (last_metas): GA4's flag on page 1 of 2 is not lost."""
    from admob_iq.fetch import ga4

    class Stub(ga4.Ga4App):
        def _post(self, method, body):
            first = body["offset"] == 0
            return {"dimensionHeaders": [{"name": "date"}], "metricHeaders": [{"name": "activeUsers"}], "rowCount": 3,
                    "rows": [{"dimensionValues": [{"value": "20260901"}], "metricValues": [{"value": "1"}]}] * (2 if first
                                                                                                             else 1),
                    "metadata": {"dataLossFromOtherRow": True} if first else {}}
    ga = Stub("t", "1", "2")
    rows = ga.report_all({"dimensions": [{"name": "date"}], "metrics": [{"name": "activeUsers"}]}, page_rows=2)
    assert len(rows) == 3 and ga.last_pages == 2 and ga.last_metas == [{"dataLossFromOtherRow": True}, {}]
    assert ga.last_meta == {} and cu._flags(ga, rows) == cu.F_OTHER


def test_light_block_is_one_call():
    ga, h = FakeGA(today=date(2027, 1, 1)), {}
    a, b = date(2026, 8, 1), date(2026, 8, 30)
    got = list(cu.read_range(ga, a, b, h, "t"))
    assert ga.calls == 1 and [D for D, _ in got] == _days(a, b) and not h.get("heavy")
    body, extra, page_rows, _ = ga.asked[0]
    assert not extra and page_rows == cu.gu.UNI_PAGE_ROWS                 # no install-day filter; every page
    for D, rec in got:
        assert rec["via"] == "block" and rec["st"] == "ok" and rec["t"] == day_total(ga, D) == _rec_sum(rec)
    D, rec = got[0]                                                       # Aug 1: install days Jun 1 … Aug 1
    assert rec["e"]["AA"]["2026-08-01"] == [80, micros(0, 8)]
    assert rec["b"]["2026-06-01"] == {"2": {"2026-07-27": micros(61, WSUM)}}    # lag 61 → bucket 2, week of Jul 27
    assert rec["c"]["--"]["2026-06-01"] == {"2": micros(61, 2)}           # country "(not set)" → "--"


def test_heavy_block_is_read_day_by_day():
    light = dict(cu.read_range(FakeGA(today=date(2027, 1, 1)), date(2026, 8, 1), date(2026, 8, 30), {}, "t"))
    ga, h = FakeGA(today=date(2027, 1, 1), cap=1000), {}
    got = dict(cu.read_range(ga, date(2026, 8, 1), date(2026, 8, 30), h, "t"))
    assert ga.calls == 1 + 30 and _multi(ga) == [("2026-08-01", "2026-08-30")]     # the block dropped, then each day
    assert h["heavy"] == {"at": "2026-08-01", "n": 30}
    for D, rec in got.items():
        assert rec["via"] == "day" and rec["st"] == "ok" and rec["loss"] == 0
        assert {k: rec[k] for k in ("b", "c", "e", "t")} == {k: light[D][k] for k in ("b", "c", "e", "t")}


def test_a_day_still_heavy_is_split_by_countries():
    D = date(2026, 9, 10)
    truth = day_total(FakeGA(today=date(2027, 1, 1), extra_day=D), D)
    # the split answers whole: the day's every cell, nothing lost
    ga = FakeGA(today=date(2027, 1, 1), cap=1500, extra_day=D)
    rec = cu.read_day(ga, D, "t")
    assert ga.calls == 3 and rec["via"] == "split" and rec["st"] == "split" and rec["loss"] == 0
    first, top, rest = ga.asked[0][1], ga.asked[1][1][0], ga.asked[2][1][0]
    vals = top["filter"]["inListFilter"]["values"]
    assert first is None and rest == {"notExpression": top} and top["filter"]["fieldName"] == "countryId"
    assert "(other)" not in vals and "(not set)" not in vals
    assert len(vals) == -(-44 // cu.SPLIT) and set(vals) >= {"AA", "BB", "CC", "DD"}  # the biggest ~1/8 (most rows)
    assert rec["t"] == truth == _rec_sum(rec) and len(rec["e"]) == 45                # AA … DD, "--", Q00 … Q39
    # the rest still over GA4's limit: what stays "(other)" is the day's measured loss — never spread
    ga2 = FakeGA(today=date(2027, 1, 1), cap=1000, extra_day=D)
    rec2 = cu.read_day(ga2, D, "t")
    assert ga2.calls == 3 and rec2["via"] == "split" and rec2["st"] == "loss" and rec2["fl"] == 0
    assert 0 < rec2["loss"] < rec2["t"] == truth == _rec_sum(rec2)
    kept = sum(v for xs in rec2["e"].values() for a in xs.values() for v in a[1:])
    assert kept + sum(v for js in rec2["b"].values() for ws in js.values() for v in ws.values()) == truth - rec2["loss"]
    for cc, xs in rec["e"].items():                                       # every cell that came back is exact
        for X, arr in rec2["e"].get(cc, {}).items():
            assert all(v == 0 or v == arr0 for v, arr0 in zip(arr[1:], xs[X][1:]))


def test_install_day_loss_and_flags():
    a, b = date(2026, 9, 1), date(2026, 9, 5)
    ga = FakeGA(today=date(2027, 1, 1), notset_day=a, neg_day=b)
    got = dict(cu.read_range(ga, a, b, {}, "t"))
    assert ga.calls == 1                                                  # no "(other)": the block is kept
    assert got[a]["loss"] == 500000 and got[a]["st"] == "loss" and got[b]["loss"] == 250000
    assert got[date(2026, 9, 3)]["st"] == "ok" and all(r["t"] == _rec_sum(r) for r in got.values())
    # thresholding: no smaller read avoids it — the block kept, every day of it flagged
    ga = FakeGA(today=date(2027, 1, 1), thr_day=date(2026, 9, 3))
    got = dict(cu.read_range(ga, a, b, {}, "t"))
    assert ga.calls == 1 and all(r["fl"] == 1 and r["st"] == "loss" and r["loss"] == 0 for r in got.values())
    # sampling or a cut answer on the block: read day by day (clean days: no flag)
    for kw in ({"smp_multi": True}, {"cut_multi": True}):
        ga = FakeGA(today=date(2027, 1, 1), **kw)
        got = dict(cu.read_range(ga, a, b, {}, "t"))
        assert ga.calls == 1 + 5 and all(r["via"] == "day" and r["fl"] == 0 and r["st"] == "ok" for r in got.values())
    # GA4 says it rolled rows into "(other)" but no "(other)" row shows: split, and still flagged → fl (≈ on the page)
    ga = FakeGA(today=date(2027, 1, 1), oth_flag_day=a)
    rec = cu.read_day(ga, a, "t")
    assert ga.calls == 3 and rec["via"] == "split" and rec["fl"] == 1 and rec["st"] == "loss" and rec["loss"] == 0


# ── the walk, the fold, the files ───────────────────────────────────────────────────────────────────────────────────
def _month(data, k, app="a~1"):
    with gzip.open(cu.month_path(data, app, k), "rt") as f:
        return json.load(f)


def test_walk_folds_by_activity_month_and_keeps_hot_days(tmp_path):
    data = str(tmp_path)
    cube, ga = cu.Cube(data, "a~1", "222"), FakeGA()
    assert cu.step_app(ga, cube, TODAY, HS, NOW) == "fetched"
    cube.save()
    cube.head.update(stream_id="222")
    cube.save_head()
    h = cu.load_head(data, "a~1")
    edge = TODAY - timedelta(days=cu.FINAL_LAG)
    assert h["from"] == "2026-06-01" and h["next"] == "2026-10-11" and h["done"] is True
    assert sorted(h["d"]) == ["2026-10-11", "2026-10-12", "2026-10-13"] and h["hot_today"] == "2026-10-13"
    assert all(r["t"] == day_total(ga, date.fromisoformat(D)) for D, r in h["d"].items())   # read while filling
    names = sorted(os.listdir(cu.app_dir(data, "a~1")))
    assert names == ["2026-06.json.gz", "2026-07.json.gz", "2026-08.json.gz", "2026-09.json.gz", "2026-10.json.gz",
                     cu.HOT]
    folded = set()
    for k, mo in cu.months(data, "a~1", "222"):
        assert set(mo) == {"v", "stream_id", "days", "b", "c", "e", "t", "loss"} and mo["stream_id"] == "222"
        folded |= set(mo["days"])
        for D, led in mo["days"].items():
            assert set(led) == set(cu.LEDGER) and led["st"] == "ok" and mo["t"][D] == led["t"]
            assert led["t"] == day_total(FakeGA(), date.fromisoformat(D))         # final reads: full values
    assert folded == {D.isoformat() for D in _days(HS, edge)}
    # b: install day Jun 1, bucket 1 = activity days Jul 2 … Jul 31 (lags 31 … 60), by the week of each activity day
    jul = _month(data, "2026-07")
    want = {}
    for D in _days(date(2026, 7, 2), date(2026, 7, 31)):
        Wk = (D - timedelta(days=D.weekday())).isoformat()
        want[Wk] = want.get(Wk, 0) + micros((D - HS).days, WSUM)
    assert jul["b"]["2026-06-01"]["1"] == want and min(want) == "2026-06-29"
    assert jul["c"]["AA"]["2026-06-01"]["1"] == sum(micros((D - HS).days, 8) for D in _days(date(2026, 7, 2),
                                                                                            date(2026, 7, 31)))
    # e: Jun 20's ages 0 … 30 straddle June and July; summed over the months they are every day of it
    e = [a + b for a, b in zip(_month(data, "2026-06")["e"]["BB"]["2026-06-20"] + [0] * 32,
                               jul["e"]["BB"]["2026-06-20"] + [0] * 32)][:32]
    assert e == [60] + [micros(L, 6) for L in range(31)]
    assert _month(data, "2026-06")["e"]["BB"]["2026-06-20"][0] == 60 and jul["e"]["BB"]["2026-06-20"][0] == 0


def test_month_files_never_change_once_folded(tmp_path):
    data = str(tmp_path)
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(), cube, TODAY, HS, NOW)
    cube.save()
    cube.save_head()
    old = {k: os.stat(cu.month_path(data, "a~1", k)).st_mtime_ns for k in ("2026-06", "2026-07", "2026-08", "2026-09")}
    raw = {k: open(cu.month_path(data, "a~1", k), "rb").read() for k in old}
    nxt = TODAY + timedelta(days=1)
    cube2, ga = cu.Cube(data, "a~1", "222"), FakeGA(today=nxt)
    cu.step_app(ga, cube2, nxt, HS, NOW + timedelta(days=1))
    cube2.save()
    cube2.save_head()
    assert cube2.folded == 1 and "2026-10-11" in _month(data, "2026-10")["days"]
    for k in old:
        assert os.stat(cu.month_path(data, "a~1", k)).st_mtime_ns == old[k] and open(cu.month_path(data, "a~1", k),
                                                                                    "rb").read() == raw[k]
    # a day already folded is never folded again (the ledger), whatever a read brings
    sep1 = date(2026, 9, 1)
    assert cube2.fold(sep1, cu._rec(cu._group(FakeGA().rows_of(sep1))[sep1.isoformat()], "day", 0, "x")) is False
    assert cube2.month("2026-09")["t"]["2026-09-01"] == day_total(FakeGA(), sep1)


def test_hot_days_replaced_then_read_again_when_final(tmp_path):
    data = str(tmp_path)
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(fill=0.5), cube, TODAY, HS, NOW)
    t11 = cube.head["d"]["2026-10-11"]["t"]
    ga = FakeGA(fill=0.5)                                       # within 6 hours, the same day: nothing read
    assert cu.step_app(ga, cube, TODAY, HS, NOW + timedelta(hours=2)) == "fresh" and ga.calls == 0
    ga = FakeGA(fill=0.75)                                      # 6 hours on: the hot days again, replaced
    assert cu.step_app(ga, cube, TODAY, HS, NOW + timedelta(hours=7)) == "fetched" and ga.calls == 1
    assert _multi(ga) == [("2026-10-11", "2026-10-13")] and cube.head["d"]["2026-10-11"]["t"] == t11 * 3 // 2
    assert "2026-10-11" not in cube.month("2026-10")["days"]    # never folded from a read while filling
    nxt = TODAY + timedelta(days=1)                             # the next property day: Oct 11 is final now
    ga = FakeGA(today=nxt, fill=0.75)
    assert cu.step_app(ga, cube, nxt, HS, NOW + timedelta(hours=9)) == "fetched"
    assert ga.asked[0][0]["dateRanges"][0] == {"startDate": "2026-10-11", "endDate": "2026-10-11"}
    assert cube.month("2026-10")["days"]["2026-10-11"]["t"] == day_total(FakeGA(today=nxt), date(2026, 10, 11))   # final
    assert sorted(cube.head["d"]) == ["2026-10-12", "2026-10-13", "2026-10-14"] and cube.head["next"] == "2026-10-12"
    assert cube.head["hot_today"] == nxt.isoformat()           # a new day re-reads the hot days once, not every hour
    ga = FakeGA(today=nxt)
    assert cu.step_app(ga, cube, nxt, HS, NOW + timedelta(hours=10)) == "fresh" and ga.calls == 0


# ── the cursor: no hole, no day folded from a read made while it was still filling ──────────────────────────────────
def _runs(cube, runs, hs=HS, cap=None):
    """runs: [(the property's today, now, stop_after)] (a Stop keeps what was folded, as refresh_all does)."""
    for today, now, stop in runs:
        try:
            cu.step_app(FakeGA(today=today, stop_after=stop, cap=cap, start=hs), cube, today, hs, now)
        except gf.Stop:
            pass


def _assert_whole(cube, today, hs=HS):
    """Every activity day hs … today − FINAL_LAG folded with the full (final) value, the cursor right after them; the
    days after it: in the hot part (or not read yet: then the cursor is before them)."""
    edge, full = today - timedelta(days=cu.FINAL_LAG), FakeGA(today=date(2100, 1, 1), start=hs)
    nxt = date.fromisoformat(cube.head["next"])
    for D in _days(hs, edge):
        led = cube.month(D.isoformat()[:7])["days"].get(D.isoformat())
        if D < nxt:
            assert led and led["t"] == day_total(full, D), D
        else:
            assert led is None, D
    assert nxt == edge + timedelta(days=1)


def test_stop_then_the_next_day_skips_nothing():
    for cap in (None, 1000):
        for stop in (0, 1, 2, 3, 7, 31, 33):
            cube = cu.Cube(None, "a~1", "222")
            _runs(cube, [(TODAY, NOW, stop), (TODAY + timedelta(days=1), NOW + timedelta(days=1), None)], cap=cap)
            _assert_whole(cube, TODAY + timedelta(days=1))
            assert sorted(cube.head["d"]) == ["2026-10-12", "2026-10-13", "2026-10-14"]


def test_a_stop_in_the_hot_read_keeps_it_due():
    cube = cu.Cube(None, "a~1", "222")
    _runs(cube, [(TODAY, NOW, None)])
    nxt = TODAY + timedelta(days=1)
    _runs(cube, [(nxt, NOW + timedelta(days=1), 1)])           # the new final day folded, then the hot read stopped
    assert cube.head["next"] == "2026-10-12" and cube.head["hot_today"] == TODAY.isoformat()
    assert "2026-10-11" not in cube.head["d"] and "2026-10-14" not in cube.head["d"]
    ga = FakeGA(today=nxt)
    assert cu.step_app(ga, cube, nxt, HS, NOW + timedelta(days=1, hours=1)) == "fetched" and ga.calls == 1
    assert sorted(cube.head["d"]) == ["2026-10-12", "2026-10-13", "2026-10-14"]


def test_pauses_catch_up_without_holes():
    """The switch off (or the app failing / deferred) for a while: the next run walks from the cursor — a long gap leaves
    no hole, and the days read while still filling are read again (final) before they are folded."""
    for gap in (50, 33, 3, 2, 1):
        cube = cu.Cube(None, "a~1", "222")
        _runs(cube, [(TODAY, NOW, None)])
        later = TODAY + timedelta(days=gap)
        _runs(cube, [(later, NOW + timedelta(days=gap), None)])
        _assert_whole(cube, later)
        assert sorted(cube.head["d"]) == [(later - timedelta(days=i)).isoformat() for i in (2, 1, 0)]
    # a young app (history start 2 days ago): nothing final yet, only hot days; done at once (nothing to walk)
    cube = cu.Cube(None, "a~1", "222")
    young = TODAY - timedelta(days=1)
    _runs(cube, [(TODAY, NOW, None)], hs=young)
    assert cube.head["done"] and sorted(cube.head["d"]) == ["2026-10-12", "2026-10-13"] and cube.folded == 0


def test_heavy_ranges_go_day_by_day_for_a_while():
    cube, ga = cu.Cube(None, "a~1", "222"), FakeGA(cap=1000)
    cu.step_app(ga, cube, TODAY, HS, NOW)
    # Jun 1 block heavy → Jul 1 and Jul 31 day by day without a block call; Aug 30 (90 days on) tried again (heavy);
    # the last 12 days (shorter: tried, heavy); the hot 3 days (shorter again: tried, heavy)
    assert _multi(ga) == [("2026-06-01", "2026-06-30"), ("2026-08-30", "2026-09-28"), ("2026-09-29", "2026-10-10"),
                          ("2026-10-11", "2026-10-13")]
    assert ga.calls == 4 + (TODAY - HS).days + 1 and cube.head["heavy"] == {"at": "2026-10-11", "n": 3}
    ga2 = FakeGA(cap=1000)                                      # the next hot read: day by day straight away
    cu.step_app(ga2, cube, TODAY, HS, NOW + timedelta(hours=7))
    assert ga2.calls == 3 and not _multi(ga2)
    # a block as long as the heavy one that comes back whole clears the memory
    h = {"heavy": {"at": "2026-01-01", "n": 3}}
    list(cu.read_range(FakeGA(today=date(2027, 1, 1)), date(2026, 8, 1), date(2026, 8, 3), h, "t"))
    assert "heavy" not in h


def test_history_start_moved_back_and_another_stream(tmp_path):
    data = str(tmp_path)
    late_hs = date(2026, 6, 21)
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(), cube, TODAY, late_hs, NOW)
    cube.save()
    cube.save_head()
    cube = cu.Cube(data, "a~1", "222")
    ga = FakeGA()
    cu.step_app(ga, cube, TODAY, HS, NOW + timedelta(hours=1))   # the history start moved back 20 days
    reads = [(q[0]["dateRanges"][0]["startDate"], q[0]["dateRanges"][0]["endDate"]) for q in ga.asked]
    assert reads == [("2026-06-01", "2026-06-20")]             # only those: the folded days never read again
    assert cube.head["from"] == "2026-06-01" and cube.head["next"] == "2026-10-11"
    cube.save()
    cube.save_head()
    assert len(_month(data, "2026-06")["days"]) == 30 and len(_month(data, "2026-07")["days"]) == 31
    # another stream: its own cube from the start (this stream's months not read as its own)
    other = cu.Cube(data, "a~1", "999")
    assert other.head == {"v": cu.V, "stream_id": "999", "d": {}} and other.month("2026-07")["days"] == {}
    assert list(cu.months(data, "a~1", "999")) == []


def test_a_head_left_behind_its_months(tmp_path):
    """A run that wrote its months but not its head (the job killed in between): the next walk finds the day in the
    ledger — not read again, not folded twice — and its stale hot copy goes."""
    data, nxt = str(tmp_path), TODAY + timedelta(days=1)
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(), cube, TODAY, HS, NOW)
    cube.save()
    cube.save_head()
    cube2 = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(today=nxt), cube2, nxt, HS, NOW + timedelta(days=1))
    cube2.save()                                                # … and no save_head()
    cube3, ga = cu.Cube(data, "a~1", "222"), FakeGA(today=nxt)
    assert cube3.head["next"] == "2026-10-11" and "2026-10-11" in cube3.head["d"]
    cu.step_app(ga, cube3, nxt, HS, NOW + timedelta(days=1, hours=1))
    assert [q[0]["dateRanges"][0]["startDate"] for q in ga.asked] == ["2026-10-12"] and cube3.folded == 0
    assert cube3.head["next"] == "2026-10-12" and sorted(cube3.head["d"]) == ["2026-10-12", "2026-10-13", "2026-10-14"]
    assert cube3.month("2026-10")["t"]["2026-10-11"] == day_total(FakeGA(today=nxt), date(2026, 10, 11))


# ── the run and the build hook ──────────────────────────────────────────────────────────────────────────────────────
def _refresh(monkeypatch, tmp_path, stop_after=None, apps=None):
    data = str(tmp_path)
    route = {"property_id": "111", "stream_id": "222", "owner": "o"}
    monkeypatch.setattr(cu.gu, "load_state", lambda d: {"routes": {"by_package": {"com.example.alpha": route,
                                                                                  "com.example.beta": dict(route, property_id="112")}},
                                                        "tz": {"111": "Asia/Kolkata", "112": "UTC"}, "fetch": {}})
    monkeypatch.setattr(cu.gaud, "_uni_meta", lambda ust, d, aid, r: {"history_start": "2026-08-01"})
    monkeypatch.setattr(cu.ga4, "access_token", lambda c, s, r: "tok")

    class A(FakeGA):
        def __init__(self, token, pid, sid, prop, over=None, max_calls=cu.MAX_CALLS):
            super().__init__(start=date(2026, 8, 1), stop_after=stop_after)
    monkeypatch.setattr(cu.gf, "App", A)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    apps = apps or [{"app_id": "x~1", "package": "com.example.alpha"}, {"app_id": "x~2", "package": "com.example.beta"},
                    {"app_id": "x~3", "package": "com.example.none"}]
    return data, cu.refresh_all(cfg, data, apps, NOW)


def test_refresh_all_files_and_counts_only(monkeypatch, tmp_path):
    data, out = _refresh(monkeypatch, tmp_path / "a")
    assert out["apps"] == {"x~1": "fetched", "x~2": "fetched"} and out["counts"]["with_ga4"] == 2
    assert out["counts"]["days"] == 2 * 71                     # Aug 1 … Oct 10 folded on each app
    for aid, tz in (("x~1", "Asia/Kolkata"), ("x~2", "UTC")):
        h = cu.load_head(data, aid)
        assert h["done"] and h["stream_id"] == "222" and h["time_zone"] == tz and h["hs"] == "2026-08-01"
        assert sorted(f for f in os.listdir(cu.app_dir(data, aid))) == ["2026-08.json.gz", "2026-09.json.gz",
                                                                        "2026-10.json.gz", cu.HOT]
    with open(os.path.join(data, cu.DIR, "state.json")) as f:
        st = json.load(f)
    assert st["fetch"]["x~1"]["last_ok"] and st["fetch"]["x~1"]["key"] == cu.gu.file_key("x~1")
    line = cu.log_line(out)
    assert line.startswith("ga4 cube: apps 3, with GA4 2, fetched 2, fresh 0, failed 0, deferred 0, waiting 0, days "
                           "folded ") and "example" not in line and "x~" not in line
    # a Stop part-way: what was folded is on disk (months before the head), the app deferred, the walk goes on next run
    data2, out2 = _refresh(monkeypatch, tmp_path / "b", stop_after=1, apps=[{"app_id": "x~1",
                                                                            "package": "com.example.alpha"}])
    assert out2["apps"] == {"x~1": "deferred"} and out2["counts"]["days"] == 30
    h = cu.load_head(data2, "x~1")
    assert h["next"] == "2026-08-31" and not h.get("done") and len(_month(data2, "2026-08", "x~1")["days"]) == 30


def test_build_hook_switch(tmp_path, monkeypatch, capsys):
    """GA4_CUBE off: the step is not run (nothing read, written or printed); on: one counts-only line with its own
    budget; a failure costs this step only."""
    from tests import test_uninstall_build as tub
    from admob_iq import uninstall_build as ub
    from admob_iq.config import settings
    assert settings()["ga4_cube"] is False and settings()["ga4_cube_budget_sec"] == 150
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    tub.seed(data)
    monkeypatch.setattr(cu.gu, "refresh_all", lambda *a, **k: copy.deepcopy(tub.STATUS))
    calls = []
    monkeypatch.setattr(cu, "refresh_all", lambda cfg, d, apps, now, clock, budget: calls.append(budget) or
                        {"counts": {"selected": 2, "fetched": 1}})
    ub.run_uninstall(tub.dashboard(), data, out, tub.ga4_settings(), now=tub.NOW)
    assert calls == [] and "ga4 cube" not in capsys.readouterr().err and not os.path.exists(os.path.join(data, cu.DIR))
    ub.run_uninstall(tub.dashboard(), data, out, tub.ga4_settings(ga4_cube=True, ga4_cube_budget_sec=60), now=tub.NOW)
    err = capsys.readouterr().err
    assert calls == [60] and [ln for ln in err.splitlines() if ln.startswith("ga4 cube")] == [
        "ga4 cube: apps 2, with GA4 0, fetched 1, fresh 0, failed 0, deferred 0, waiting 0, days folded 0, split 0, "
        "loss 0, calls 0, tokens 0"]
    monkeypatch.setattr(cu, "refresh_all", lambda *a, **k: 1 / 0)
    dash = tub.dashboard()
    ub.run_uninstall(dash, data, out, tub.ga4_settings(ga4_cube=True), now=tub.NOW)
    assert "ga4 cube skipped: ZeroDivisionError" in capsys.readouterr().err and dash["uninstall"]["apps"]
