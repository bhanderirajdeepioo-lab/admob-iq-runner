"""🧊 The cohort cube (admob_iq.fetch.ga4_cube), offline with a fake GA4 and made-up numbers: the query (dimensions
date × firstSessionDate × countryId, no install-day filter, every page), the adaptive read (a block → its days alone when
GA4 rolls rows into "(other)" or flags the answer → a day split by its biggest ~1/8 countries and the rest; what stays
"(other)" kept as that day's measured loss, never spread), "(not set)" country → "--", a non-date install day or one
after the activity day → loss, GA4's flags kept per day, the fold shapes (b / c / e / t / loss + the ledger), month
files that never change once folded, the hot days replaced on each re-read and read once more when final, ONE cursor (a
Stop, a pause, a new day: no hole, no day folded from a read made while it was still filling), the heavy-range memory,
the deeper split (21 Oct 2026: parts halved by countries, then by install days, while "(other)" is left — shown, or
hidden under an in-list with only GA4's flag, then measured by the day's own total; a split that names nothing new
stops; the parts partition the day in every one of those GA4 behaviours; the cap leaves measured loss; a Stop keeps
nothing of the day; a day cut as the run's first read, run after run, gets a smaller cap — recoverable, "cap" 2 —
only in an app that had the run's whole budget (one that started late goes first next run); the walk and the hot
days keep their own cut memory; a hot round a Stop cut goes on with its unread days; the day's total measures only
when whole, a hot day never), the repair (months folded with the one-level split read again day by day into a copy —
a day started only with room for it, calls and time — and replaced whole once every day is in it; biggest loss share
first; never twice for one split version; its head written even in a run with no call, the copy removed after it; a
month whose file is gone let go),
the history start moving back (and "done" cleared until the walk is through), another stream, a month file that cannot
be read (read again from its first day, never written over), at most two months in memory, a hot copy of a day that is
final now dropped, flagged days kept apart from measured loss, turns on a property (a backfill never starves a light
app), the run over properties with a counts-only line, and the build hook (off: nothing read, written or printed).
q (the whole no-country read of a day, ages 31 … 420): its request and age edges, "fl" (an empty q) on anything not
whole ("(other)", GA4's flags) while rows GA4 gave no install day ("(not set)", after the day) are their size ("qn", the
day "ok"), a new final day and the hot days read in the same run, a Stop keeping the fold and the q days read, the
app's call cap ending it quietly, any other error ending q for the app (counted, never the app's run), days of nothing
never read, the history queue (lossy months first), the run's Q_CALLS and Q_SEC caps, the second round (lossy apps
first), an app not scanned yet counted apart, q files never taken for months and never touched by the repair, the
counts in the log and the state."""
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


import pytest


@pytest.fixture(autouse=True)
def _repair_on(monkeypatch):
    """The repair is off by default (GA4_CUBE_REPAIR_CALLS unset → 0); these tests check it as it runs when on."""
    monkeypatch.setattr(cu, "REPAIR_CALLS", 30)


@pytest.fixture(autouse=True)
def _q_off(monkeypatch):
    """q (the whole no-country day reads) off for the tests of the cube's own reads (their call counts are the cube's);
    the q tests below turn it on (Q_CALLS > 0) themselves."""
    monkeypatch.setattr(cu, "Q_CALLS", 0)


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
    `fill` of that. Filters: every expression ANDed (an in-list on any field, or its notExpression); rows grouped by
    the dimensions asked for. cap: an answer with more rows keeps its `cap` biggest and rolls the rest into a per-day
    "(other)" row (dataLossFromOtherRow). extra_day: 40 more countries "Q00" … that day (lags 0 … 30, weight 1).
    notset_day / neg_day: one row with install day "(not set)" / after the activity day. thr_day: any answer holding it
    says thresholding. smp_multi / cut_multi: a multi-day answer says sampling / was cut. stop_after: Stop(stop_why) at
    that call; max_calls: the App's call cap (Stop("calls") once used up). keep: every answer kept (answers).
    hide: an answer with an in-list filter (not its notExpression) drops its "(other)" row, keeping
    dataLossFromOtherRow (as GA4 does under an in-list: the row gone, its revenue too). prefold: GA4 rolls rows into
    "(other)" BEFORE the filters (the whole day's answer cut to `cap` rows, then filtered: an in-list drops the
    "(other)" row, a notExpression keeps it) — no split by a filter names a row more. oth_flag_day: the flag with no
    "(other)" row on that day's answers — not on a day's total read (no filter, no countryId: the cube's date-only
    total, the cohort's every-install-day read) unless oth_flag_total. smp_total / cut_total: such a total read
    sampled / cut. grow: every call, the revenue of a day not final yet grows by that share (GA4 still adding to it
    during the read). smp_day: every answer with countryId holding that day says sampling (each part of a split too)."""

    def __init__(self, today=TODAY, cap=None, stop_after=None, fill=0.5, start=HS, max_lag=120, extra_day=None,
                 notset_day=None, neg_day=None, thr_day=None, smp_multi=False, cut_multi=False, oth_flag_day=None,
                 max_calls=None, keep=False, stop_why="calls", hide=False, prefold=False, oth_flag_total=False,
                 smp_total=False, cut_total=False, grow=0.0, smp_day=None):
        self.hide, self.prefold, self.smp_day = hide, prefold, smp_day
        self.oth_flag_total, self.smp_total, self.cut_total, self.grow = oth_flag_total, smp_total, cut_total, grow
        self.today, self.cap, self.stop_after, self.fill, self.start, self.max_lag = (today, cap, stop_after, fill,
                                                                                      start, max_lag)
        self.extra_day, self.notset_day, self.neg_day, self.thr_day = extra_day, notset_day, neg_day, thr_day
        self.smp_multi, self.cut_multi, self.oth_flag_day = smp_multi, cut_multi, oth_flag_day
        self.calls, self.asked, self.tok, self.last_metas, self._cut = 0, [], 0, [], False
        self.stop_why = stop_why
        self.answers = [] if keep else None                     # keep: every answer (the partition checks)
        if max_calls is not None:                               # the App's call cap: Stop("calls") once it is used up
            self.max_calls, self.stop_after = max_calls, max_calls

    def rows_of(self, D):
        f = self.fill * (1 + self.grow) ** self.calls if (self.today - D).days < cu.FINAL_LAG else 1.0
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
            raise gf.Stop(self.stop_why)
        self.calls += 1
        self.asked.append((body, extra, page_rows, self.today))
        a, b = (date.fromisoformat(body["dateRanges"][0][k]) for k in ("startDate", "endDate"))
        preds = [_pred(ex) for ex in extra or []]                # every filter expression ANDed (as stream_filter)
        dims = [d["name"] for d in body["dimensions"]]
        agg = {}                                                 # grouped by the dimensions asked for
        for D in _days(a, b):
            for r in self.rows_of(D):
                if self.prefold or all(p(r) for p in preds):
                    g = agg.setdefault(tuple(r[d] for d in dims), [0, 0.0])
                    g[0] += r["activeUsers"]
                    g[1] += r["totalAdRevenue"]
        rows = [dict(zip(dims, k), activeUsers=u, totalAdRevenue=v) for k, (u, v) in agg.items()]
        meta = {}
        if self.cap is not None and len(rows) > self.cap:
            rows.sort(key=lambda r: (-r["totalAdRevenue"],) + tuple(r[d] for d in dims))
            oth = {}
            for r in rows[self.cap:]:
                o = oth.setdefault(r["date"], [0, 0.0])
                o[0] += r["activeUsers"]
                o[1] += r["totalAdRevenue"]
            rows = rows[:self.cap] + [dict({d: "(other)" for d in dims}, date=D, activeUsers=u, totalAdRevenue=v)
                                      for D, (u, v) in sorted(oth.items())]
            meta["dataLossFromOtherRow"] = True
        if self.prefold:                                         # the filters on the answer GA4 already cut
            rows = [r for r in rows if all(p(r) for p in preds)]
        if self.hide and any("filter" in ex for ex in extra or []):
            rows = [r for r in rows if "(other)" not in (r.get("firstSessionDate"), r.get("countryId"))]
        if self.answers is not None:
            self.answers.append(rows)
        total = not extra and "countryId" not in dims           # a day's total read (no filter, no country)
        if self.oth_flag_day and a <= self.oth_flag_day <= b and (self.oth_flag_total or not total):
            meta["dataLossFromOtherRow"] = True                 # the flag with no "(other)" row to measure it by
        if self.smp_total and total:
            meta["samplingMetadatas"] = [{"samplesReadCount": "1", "samplingSpaceSize": "2"}]
        if self.thr_day and a <= self.thr_day <= b:
            meta["subjectToThresholding"] = True
        if self.smp_multi and a < b:
            meta["samplingMetadatas"] = [{"samplesReadCount": "1", "samplingSpaceSize": "2"}]
        if self.smp_day and a <= self.smp_day <= b and "countryId" in dims:
            meta["samplingMetadatas"] = [{"samplesReadCount": "1", "samplingSpaceSize": "2"}]   # every part of it
        self._cut = (self.cut_multi and a < b) or (self.cut_total and total)
        self.last_metas = [{}, meta]                            # the flag on any page counts
        return rows

    def truncated(self, rows):
        return self._cut


def _pred(ex):
    """A filter expression (an in-list on any field, or its notExpression) → a test on a fake row."""
    if "notExpression" in ex:
        p = _pred(ex["notExpression"])
        return lambda r: not p(r)
    f = ex["filter"]
    vals = set(f["inListFilter"]["values"])
    return lambda r, k=f["fieldName"]: r.get(k) in vals


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


CELLS = ("b", "c", "e", "t")
LATER = date(2027, 1, 1)                                       # every day of 2026 final


def _cells_le(rec, truth):
    """Every one-row cell of rec that came back ("e", "c") is exactly the true one, and "b" (all countries summed) is
    never over it — what GA4 kept "(other)" is missing (the measured loss), never wrong, never counted twice."""
    for cc, xs in rec["e"].items():
        for X, arr in xs.items():
            assert all(v == 0 or v == t for v, t in zip(arr, truth["e"][cc][X])), (cc, X)
    for cc, xs in rec["c"].items():
        for X, js in xs.items():
            assert all(v == truth["c"][cc][X][j] for j, v in js.items()), (cc, X)
    for X, js in rec["b"].items():
        for j, ws in js.items():
            assert all(v <= truth["b"][X][j][W] for W, v in ws.items()), X


def test_a_day_still_heavy_is_split_by_countries():
    D = date(2026, 9, 10)
    tga = FakeGA(today=LATER, extra_day=D)
    truth = cu.read_day(tga, D, "t")                           # GA4 with no limit: one call, every cell
    assert tga.calls == 1 and truth["via"] == "day" and truth["loss"] == 0 and truth["t"] == day_total(tga, D)
    # one level: the biggest named countries up to half the named rows in an in-list, the rest (every other country,
    # those GA4 hid in "(other)", "(not set)") in its notExpression — the split answers whole, nothing lost
    ga = FakeGA(today=LATER, cap=1500, extra_day=D, keep=True)
    rec = cu.read_day(ga, D, "t")
    assert ga.calls == 3 and rec["via"] == "split" and rec["st"] == "split" and rec["loss"] == 0 and rec["n"] == 3
    first, top, rest = ga.asked[0][1], ga.asked[1][1][0], ga.asked[2][1][0]
    vals = top["filter"]["inListFilter"]["values"]
    assert first is None and rest == {"notExpression": top} and top["filter"]["fieldName"] == "countryId"
    assert "(other)" not in vals and "(not set)" not in vals
    n = {}                                                      # the named rows of the day's (folded) answer
    for r in ga.answers[0]:
        if r["countryId"] not in ("(other)", "(not set)"):
            n[r["countryId"]] = n.get(r["countryId"], 0) + 1
    order = sorted(n, key=lambda c: (-n[c], -W.get(c, 1), c))   # most rows, then revenue, then code
    k = len(vals)
    assert set(vals) == set(order[:k]) and {"AA", "BB", "CC", "DD"} <= set(vals) and 4 < k < len(order)
    assert 2 * sum(n[c] for c in order[:k - 1]) < sum(n.values()) <= 2 * sum(n[c] for c in order[:k])   # ≈ half
    assert {k: rec[k] for k in CELLS} == {k: truth[k] for k in CELLS} and len(rec["e"]) == 45
    assert rec["sv"] == cu.SPLIT_V and rec["ol"] == 0 and rec["cap"] == 0
    # a part still over GA4's limit is split again (and again): where one level kept "(other)", every cell comes
    # back — more calls, each a smaller read (given calls enough; the day's own cap: test_the_cap_leaves_measured_loss)
    for cap, at_least in ((1000, 3), (500, 5), (200, 9), (110, 15)):
        ga = FakeGA(today=LATER, cap=cap, extra_day=D)
        rec = cu.read_day(ga, D, "t", cap=200)
        assert rec["loss"] == rec["ol"] == rec["cap"] == 0 and rec["st"] == "split", cap
        assert {k: rec[k] for k in CELLS} == {k: truth[k] for k in CELLS}, cap
        assert rec["n"] == ga.calls >= at_least and "hd" not in rec and "fu" not in rec, cap
    ga = FakeGA(today=LATER, cap=500, extra_day=D)              # within the day's own cap
    rec = cu.read_day(ga, D, "t")
    assert rec["loss"] == rec["cap"] == 0 and ga.calls <= cu.DAY_CAP


def test_one_country_over_the_limit_is_split_by_install_days():
    """A country whose own rows are over GA4's limit: split by install days (firstSessionDate in-list halves and
    "every install day but those"), recursively — every cell comes back."""
    D = date(2026, 10, 1)                                      # 121 install days a country (lags 0 … 120)
    truth = cu.read_day(FakeGA(today=LATER), D, "t")
    ga = FakeGA(today=LATER, cap=50)
    rec = cu.read_day(ga, D, "t", cap=200)
    assert rec["loss"] == 0 and rec["cap"] == 0 and {k: rec[k] for k in CELLS} == {k: truth[k] for k in CELLS}
    one = [ex for _, ex, _, _ in ga.asked if ex and len(ex) == 2 and ex[0].get("filter", {}).get("fieldName") ==
           "countryId" and len(ex[0]["filter"]["inListFilter"]["values"]) == 1]
    assert one                                                  # a one-country part split by install days
    for ex in one:
        x = ex[1].get("filter") or ex[1]["notExpression"]["filter"]
        assert x["fieldName"] == "firstSessionDate" and all(len(v) == 8 and v.isdigit()
                                                            for v in x["inListFilter"]["values"])
    ins = [ex[1]["filter"]["inListFilter"]["values"] for ex in one if "filter" in ex[1]]
    assert any(len(v) > 1 and v == sorted(v) for v in ins)      # in-list halves of install days (by date)
    # GA4 naming no row at all: nothing to split by — measured loss, not a cap
    ga = FakeGA(today=LATER, cap=0)
    rec = cu.read_day(ga, D, "t")
    assert rec["loss"] == rec["t"] == truth["t"] == _rec_sum(rec) and ga.calls == 1 and rec["cap"] == 0
    # GA4 rolling rows into "(other)" BEFORE the filters: the first split names no row the day had not — no filter
    # reads more of it, the split stops there (3 calls, not the cap); its "(other)" is the day's measured loss
    ga = FakeGA(today=LATER, cap=50, prefold=True)
    rec = cu.read_day(ga, D, "t")
    assert 0 < rec["loss"] == rec["ol"] and rec["t"] == truth["t"] == _rec_sum(rec) and ga.calls == 3
    assert rec["fu"] == 1 and rec["cap"] == 0 and rec["via"] == "day" and rec["fl"] == 0
    cube = cu.Cube(None, "a~1", "222")
    cube.fold(D, rec)
    assert (cube.futile, cube.hidden, cube.capped) == (1, 0, 0)


def test_the_cap_leaves_measured_loss():
    D = date(2026, 9, 10)
    truth = cu.read_day(FakeGA(today=LATER, extra_day=D), D, "t")
    for cap in (3, 5, 9):
        ga = FakeGA(today=LATER, cap=200, extra_day=D)
        rec = cu.read_day(ga, D, "t", cap=cap)
        assert ga.calls <= cap and rec["n"] == ga.calls and rec["cap"] == 1 and rec["st"] == "loss"
        assert 0 < rec["loss"] == rec["ol"] < rec["t"] == truth["t"] == _rec_sum(rec)     # kept as loss, never spread
        _cells_le(rec, truth)
    # the hot days' own (smaller) cap; the final read later uses the day's full one
    ga = FakeGA(cap=200, extra_day=date(2026, 10, 12))
    got = dict(cu.read_range(ga, date(2026, 10, 12), date(2026, 10, 12), {}, "t", cap=cu.HOT_CAP))
    assert ga.calls <= cu.HOT_CAP and got[date(2026, 10, 12)]["n"] == ga.calls


def test_other_hidden_under_an_in_list_is_split_and_measured():
    """GA4 drops the "(other)" row from an answer with an in-list filter (dataLossFromOtherRow only): such a part is
    split again like one that shows the row, and what is still hidden when the cap stops it is measured by the day's
    own total (date only, no filter: one call) — in t, loss and ol, "cap" 1 — never missing unrecorded."""
    D = date(2026, 9, 10)
    truth = cu.read_day(FakeGA(today=LATER, extra_day=D), D, "t")
    for lim in (1000, 500, 200):
        ga = FakeGA(today=LATER, cap=lim, extra_day=D, hide=True)
        rec = cu.read_day(ga, D, "t", cap=200)
        assert {k: rec[k] for k in CELLS} == {k: truth[k] for k in CELLS} and rec["loss"] == 0, lim
        assert "hd" not in rec and rec["fl"] == 0 and rec["n"] == ga.calls, lim
    for c in (3, 9, 15):                                        # the cap keeps hidden parts from a split
        ga = FakeGA(today=LATER, cap=200, extra_day=D, hide=True)
        rec = cu.read_day(ga, D, "t", cap=c)
        assert ga.calls == c + 1 and ga.asked[-1][0]["dimensions"] == [{"name": "date"}] and not ga.asked[-1][1]
        assert rec["hd"] > 0 and rec["t"] == truth["t"] == _rec_sum(rec) and rec["cap"] == 1 and rec["fl"] == 0
        assert rec["loss"] == rec["ol"] >= rec["hd"] and rec["st"] == "loss"
        _cells_le(rec, truth)
    cube = cu.Cube(None, "a~1", "222")
    cube.fold(D, rec)
    assert (cube.hidden, cube.capped, cube.loss, cube.flagged) == (1, 1, 1, 0)


def test_the_parts_partition_the_day():
    """Over many GA4 limits (and days with 40 more countries, a "(not set)" install day, an install day after the
    activity day), with GA4's "(other)" row shown, hidden under an in-list, or rolled up before the filters: the final
    parts never share a row and, with what the day's own total says they hid, add up to the day's total — nothing
    dropped, nothing counted twice — and every cell that came back is the true one."""
    cases = ((date(2026, 9, 10), {"extra_day": date(2026, 9, 10)}),
             (date(2026, 10, 1), {"notset_day": date(2026, 10, 1), "neg_day": date(2026, 10, 1)}))
    for D, kw in cases:
        truth = cu.read_day(FakeGA(today=LATER, **kw), D, "t")
        whole = day_total(FakeGA(today=LATER, **kw), D)
        for mode in ({}, {"hide": True}, {"prefold": True}):
            for cap in (0, 2, 7, 30, 60, 150, 400, 1000, None):
                ga = FakeGA(today=LATER, cap=cap, **kw, **mode)
                rows, info = cu.split_read(ga, D, total=cu.day_total)
                named = [(r["firstSessionDate"], r["countryId"]) for r in rows
                         if "(other)" not in (r["firstSessionDate"], r["countryId"])]
                assert len(named) == len(set(named)), (D, cap, mode)              # no row in two parts
                assert cu._micros(rows) + info["hid"] == whole, (D, cap, mode)    # … nor one missing unmeasured
                assert info["hid"] == 0 or mode, (D, cap)                         # (shown "(other)": nothing hidden)
                rec = cu.read_day(FakeGA(today=LATER, cap=cap, **kw, **mode), D, "t")
                assert rec["t"] == truth["t"] == _rec_sum(rec), (D, cap, mode)   # every row in one part
                assert info["calls"] == ga.calls <= cu.DAY_CAP + 1 and info["parts"] >= 1
                _cells_le(rec, truth)
                assert rec["loss"] >= truth["loss"] >= rec["loss"] - rec["ol"]  # "(not set)" install day: loss
    # the parts of one split, checked one by one: the answers of the two halves of a part add up to the part
    ga = FakeGA(today=LATER, cap=150, extra_day=date(2026, 9, 10), keep=True)
    cu.split_read(ga, date(2026, 9, 10))
    tot = [round(sum(r["totalAdRevenue"] for r in a) * 1e6) for a in ga.answers]
    assert len(tot) >= 5 and abs(tot[0] - tot[1] - tot[2]) <= 2         # the day = its first two parts


def test_install_day_loss_and_flags():
    a, b = date(2026, 9, 1), date(2026, 9, 5)
    ga = FakeGA(today=date(2027, 1, 1), notset_day=a, neg_day=b)
    got = dict(cu.read_range(ga, a, b, {}, "t"))
    assert ga.calls == 1                                                  # no "(other)": the block is kept
    assert got[a]["loss"] == 500000 and got[a]["st"] == "loss" and got[b]["loss"] == 250000
    assert got[date(2026, 9, 3)]["st"] == "ok" and all(r["t"] == _rec_sum(r) for r in got.values())
    # thresholding: no smaller read avoids it — the block kept, every day of it flagged (a flag, not a measured loss:
    # st stays "ok", the ledger and the log keep the two apart)
    ga = FakeGA(today=date(2027, 1, 1), thr_day=date(2026, 9, 3))
    got = dict(cu.read_range(ga, a, b, {}, "t"))
    assert ga.calls == 1 and all(r["fl"] == 1 and r["st"] == "ok" and r["loss"] == 0 for r in got.values())
    cube = cu.Cube(None, "a~1", "222")
    for D, r in got.items():
        cube.fold(D, r)
    assert (cube.folded, cube.loss, cube.flagged) == (5, 0, 5)
    cube2 = cu.Cube(None, "a~1", "222")
    for D, r in cu.read_range(FakeGA(today=date(2027, 1, 1), notset_day=a), a, b, {}, "t"):
        cube2.fold(D, r)
    assert (cube2.loss, cube2.flagged) == (1, 0) and cube2.month("2026-09")["days"][a.isoformat()]["st"] == "loss"
    # sampling or a cut answer on the block: read day by day (clean days: no flag)
    for kw in ({"smp_multi": True}, {"cut_multi": True}):
        ga = FakeGA(today=date(2027, 1, 1), **kw)
        got = dict(cu.read_range(ga, a, b, {}, "t"))
        assert ga.calls == 1 + 5 and all(r["via"] == "day" and r["fl"] == 0 and r["st"] == "ok" for r in got.values())
    # GA4 says it rolled rows into "(other)" but no "(other)" row shows: split (the halves name nothing new: no more),
    # then the day's own total (date only, no filter) measures it — here nothing is missing: no loss, no flag
    ga = FakeGA(today=date(2027, 1, 1), oth_flag_day=a)
    rec = cu.read_day(ga, a, "t")
    assert ga.calls == 4 and [q[0]["dimensions"] for q in ga.asked][-1] == [{"name": "date"}] and not ga.asked[-1][1]
    assert rec["fl"] == 0 and rec["st"] == "ok" and rec["loss"] == 0 and rec["t"] == day_total(ga, a)
    cube = cu.Cube(None, "a~1", "222")
    cube.fold(a, rec)                                   # one level, futile: never "deeper" (its n counts the total)
    assert rec["via"] == "day" and rec["fu"] == 1 and "dp" not in rec
    assert (cube.deeper, cube.split, cube.futile) == (0, 0, 1)
    # … and when its total cannot be read whole — sampled, cut, flagged dataLossFromOtherRow itself, or with a row
    # whose day is not a date —, the flag stays: nothing to measure it by (no "hd", never booked as loss)
    class OthTotal(FakeGA):
        def report_all(self, body, **kw):
            rows = super().report_all(body, **kw)
            if [d["name"] for d in body["dimensions"]] == ["date"]:
                rows = rows + [{"date": "(other)", "activeUsers": 1, "totalAdRevenue": 0.5}]
            return rows
    for ga in (FakeGA(today=LATER, oth_flag_day=a, smp_total=True), FakeGA(today=LATER, oth_flag_day=a, cut_total=True),
               FakeGA(today=LATER, oth_flag_day=a, oth_flag_total=True), OthTotal(today=LATER, oth_flag_day=a)):
        rec = cu.read_day(ga, a, "t")
        assert ga.calls == 4 and ga.asked[-1][0]["dimensions"] == [{"name": "date"}] and cu.day_total(ga, a) is None
        assert rec["fl"] == 1 and rec["loss"] == 0 and "hd" not in rec and rec["st"] == "ok"
    assert cu.day_total(FakeGA(today=LATER), a) == day_total(FakeGA(today=LATER), a)


def test_the_days_total_against_the_parts():
    """What the day's total holds beyond the parts is hidden "(other)" (measured: in loss, "cap" only when the cap kept
    a hidden part from a split — here the split was futile, not capped); parts holding MORE than the total: nothing
    to measure by — a flag, nothing booked."""
    a = date(2026, 9, 1)
    rows, info = cu.split_read(FakeGA(today=LATER, oth_flag_day=a), a, total=lambda g, D: cu.day_total(g, D) + 5000)
    assert info["hid"] == 5000 and info["cap"] == 0 and info["futile"] == 1 and not info["flag"]
    rows, info = cu.split_read(FakeGA(today=LATER, oth_flag_day=a), a, total=lambda g, D: cu.day_total(g, D) - 5000)
    assert info["hid"] == 0 and info["flag"] and info["cap"] == 0
    rec = cu.read_day(FakeGA(today=LATER, oth_flag_day=a, hide=True, cap=200), a, "t", cap=3)
    assert rec["cap"] == 1                                      # the cap kept a hidden part: "cap" 1 (test above)


def test_a_hot_day_is_never_measured_by_its_total():
    """A day still filling: GA4 adds to it between the calls — a gap to a total read after the parts would be revenue
    that came in during the read, not "(other)": a hot day's hidden part is a flag (≈), no total call, nothing booked
    as loss; the same day final is measured."""
    D = TODAY
    ga = FakeGA(oth_flag_day=D, grow=0.002)
    rows, info = cu.split_read(ga, D, cu.HOT_CAP, total=cu.day_total)
    assert info["hid"] > 0                                      # what a total read after the parts would book
    ga = FakeGA(oth_flag_day=D, grow=0.002)
    (_, rec), = cu.read_range(ga, D, D, {}, "t", cap=cu.HOT_CAP, key="hcut", hot=True)
    assert "hd" not in rec and rec["loss"] == rec["ol"] == 0 and rec["fl"] == 1 and rec["st"] == "ok"
    assert all(q[0]["dimensions"] != [{"name": "date"}] for q in ga.asked)
    cube = cu.Cube(None, "a~1", "222")                         # the run's hot round: the same
    cu.step_app(FakeGA(oth_flag_day=D, grow=0.002), cube, TODAY, HS, NOW)
    hot = cube.head["d"][D.isoformat()]
    assert hot["fl"] == 1 and hot["loss"] == 0 and "hd" not in hot
    nxt = TODAY + timedelta(days=cu.FINAL_LAG)                  # final: measured (nothing hidden here: no flag)
    rec = cu.read_day(FakeGA(today=nxt, oth_flag_day=D, grow=0.002), D, "t")
    assert rec["fl"] == 0 and rec["loss"] == 0 and rec["t"] == day_total(FakeGA(today=nxt), D)


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


def _save(cube):
    cube.save()
    cube.save_head()


def _reads(ga):
    return [(q[0]["dateRanges"][0]["startDate"], q[0]["dateRanges"][0]["endDate"]) for q in ga.asked]


def test_a_month_file_that_cannot_be_read_is_read_again_never_written_over(tmp_path):
    """The month the cursor is in, on disk but unreadable (a cut gzip), not this format or another stream's: never
    folded into as an empty month (that would write over the days it held, the cursor already past them) — the cursor
    goes back to the month's first day and the whole month is read again; a Stop on the way keeps the cursor honest."""
    nxt = TODAY + timedelta(days=1)
    oct_days = [D.isoformat() for D in _days(date(2026, 10, 1), date(2026, 10, 11))]
    for name, bad, counted in (("cut", b"\x1f\x8b\x08\x00 a cut copy", 1),
                               ("format", gzip.compress(b'{"v": 1, "stream_id": "222", "days": []}'), 1),
                               ("stream", gzip.compress(json.dumps(dict(cu._empty_month("999"), days={
                                   "2026-10-01": {}})).encode()), 0)):
        data = str(tmp_path / name)
        cube = cu.Cube(data, "a~1", "222")
        cu.step_app(FakeGA(), cube, TODAY, HS, NOW)
        _save(cube)
        assert sorted(_month(data, "2026-10")["days"]) == oct_days[:10]
        with open(cu.month_path(data, "a~1", "2026-10"), "wb") as f:
            f.write(bad)
        # a Stop before any read: nothing written over the file, the cursor back at the month's first day, not done
        cube = cu.Cube(data, "a~1", "222")
        try:
            cu.step_app(FakeGA(today=nxt, stop_after=0), cube, nxt, HS, NOW + timedelta(days=1))
        except gf.Stop:
            pass
        _save(cube)
        assert open(cu.month_path(data, "a~1", "2026-10"), "rb").read() == bad
        assert cube.head["next"] == "2026-10-01" and "done" not in cube.head and cube.reread == counted
        # the next run: the whole month again (one block, then the hot days), every day of it final, nothing lost
        cube, ga = cu.Cube(data, "a~1", "222"), FakeGA(today=nxt)
        assert cu.step_app(ga, cube, nxt, HS, NOW + timedelta(days=1, hours=1)) == "fetched"
        _save(cube)
        assert _reads(ga) == [("2026-10-01", "2026-10-11"), ("2026-10-12", "2026-10-14")], name
        mo = _month(data, "2026-10")
        assert sorted(mo["days"]) == oct_days and mo["stream_id"] == "222"
        assert all(mo["t"][D] == day_total(FakeGA(today=nxt), date.fromisoformat(D)) for D in oct_days)
        assert cube.head["next"] == "2026-10-12" and cube.head["done"] and cube.reread == counted
    # heavy (day by day) and a Stop part-way through the month read again: the file holds exactly the days before the
    # cursor (re-read from the month's first day), the rest follow next run
    data = str(tmp_path / "heavy")
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(), cube, TODAY, HS, NOW)
    _save(cube)
    with open(cu.month_path(data, "a~1", "2026-10"), "wb") as f:
        f.write(b"\x1f\x8b broken")
    cube = cu.Cube(data, "a~1", "222")
    try:
        cu.step_app(FakeGA(today=nxt, cap=1000, stop_after=3), cube, nxt, HS, NOW + timedelta(days=1))
    except gf.Stop:
        pass
    _save(cube)
    assert sorted(_month(data, "2026-10")["days"]) == ["2026-10-01", "2026-10-02"] and cube.head["next"] == "2026-10-03"
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(today=nxt), cube, nxt, HS, NOW + timedelta(days=1, hours=1))
    _save(cube)
    assert sorted(_month(data, "2026-10")["days"]) == oct_days and cube.head["done"] and cube.reread == 0


class _Peak(cu.Cube):
    """A cube that remembers the most months it held at once."""
    peak = 0

    def month(self, k):
        r = super().month(k)
        self.peak = max(self.peak, len(self.m))
        return r


def test_a_walk_over_folded_days_holds_two_months_at_most(tmp_path):
    """A history start moved back, or a lost head file: the walk passes every folded month (reads nothing of them) and
    lets each go — never the app's every month in memory at once."""
    data = str(tmp_path / "a")
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(), cube, TODAY, date(2026, 6, 21), NOW)
    _save(cube)
    cube, ga = _Peak(data, "a~1", "222"), FakeGA()
    cu.step_app(ga, cube, TODAY, HS, NOW + timedelta(hours=1))           # moved back 20 days
    assert _reads(ga) == [("2026-06-01", "2026-06-20")] and cube.peak <= 2 and len(cube.m) <= 2
    _save(cube)
    os.remove(cu.hot_path(data, "a~1"))                                  # the head lost: the walk from the start again
    raw = {k: open(cu.month_path(data, "a~1", k), "rb").read() for k in ("2026-06", "2026-07", "2026-08", "2026-09")}
    cube, ga = _Peak(data, "a~1", "222"), FakeGA()
    assert cube.head == {"v": cu.V, "stream_id": "222", "d": {}}
    cu.step_app(ga, cube, TODAY, HS, NOW + timedelta(hours=2))
    _save(cube)
    assert _reads(ga) == [("2026-10-11", "2026-10-13")] and cube.peak <= 2 and cube.folded == 0   # only the hot days
    assert cube.head["next"] == "2026-10-11" and cube.head["done"]
    assert all(open(cu.month_path(data, "a~1", k), "rb").read() == v for k, v in raw.items())


def test_a_hot_copy_of_a_final_day_is_dropped_even_when_the_walk_stops():
    """Hot copies are read while the day is filling: once the day is final it counts only when folded from a final
    read — a walk that stops before it leaves a hole (the build's column stops there), never the early copy."""
    cube = cu.Cube(None, "a~1", "222")
    _runs(cube, [(TODAY, NOW, None)])
    assert sorted(cube.head["d"]) == ["2026-10-11", "2026-10-12", "2026-10-13"]
    later = TODAY + timedelta(days=2)                                    # edge Oct 12: Oct 11 and 12 final now
    _runs(cube, [(later, NOW + timedelta(days=2), 0)])                   # … and the run stops at its first call
    assert sorted(cube.head["d"]) == ["2026-10-13"] and cube.pruned and cube.head["next"] == "2026-10-11"
    _runs(cube, [(later, NOW + timedelta(days=2, hours=1), None)])
    _assert_whole(cube, later)


def test_history_start_moved_back_clears_done_until_the_walk_is_through(tmp_path):
    from admob_iq import roi_build as rb
    data = str(tmp_path)
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(), cube, TODAY, date(2026, 6, 21), NOW)
    _save(cube)
    assert rb._late(data, "a~1", "222", {"hs": date(2026, 6, 21), "sc": {"kf": lambda d: (1.0,)}})["info"]["thru"] == \
        "2026-10-13"
    cube = cu.Cube(data, "a~1", "222")
    try:
        cu.step_app(FakeGA(stop_after=0), cube, TODAY, HS, NOW + timedelta(hours=1))
    except gf.Stop:
        pass
    _save(cube)
    assert "done" not in cube.head and cube.head["next"] == "2026-06-01"
    assert rb._late(data, "a~1", "222", {"hs": HS}) == {"info": {"busy": 1, "from": "2026-06-01", "next": "2026-06-01",
                                                                 "at": "2026-10-13"}}
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(), cube, TODAY, HS, NOW + timedelta(hours=2))
    _save(cube)
    assert cube.head["done"] and rb._late(data, "a~1", "222", {"hs": HS, "sc": {"kf": lambda d: (1.0,)}})["info"][
        "from"] == "2026-06-01"


# ── the deeper split in the walk: a Stop, the cut memory ────────────────────────────────────────────────────────────
def _day_calls(ga, D):
    """(index of the first call of activity day D alone, how many calls it took) in a fake's log."""
    k = {"startDate": D.isoformat(), "endDate": D.isoformat()}
    i = [n for n, q in enumerate(ga.asked) if q[0]["dateRanges"][0] == k]
    return i[0], len(i)


def test_a_stop_in_the_middle_of_a_split_keeps_nothing_of_the_day():
    """A Stop (the run's budget, the quota, the call cap) between the calls of a day's split: the day is NOT folded —
    the cursor stays on it, no part of it anywhere — and the next run reads it again whole and folds it once. A day
    the Stop cut after other reads of the run (it had only what they left) is never counted as the day's cut."""
    X = date(2026, 8, 1)                                        # 1,550 rows that day: a split of several levels
    dry = FakeGA(cap=500, extra_day=X)
    cu.step_app(dry, cu.Cube(None, "a~1", "222"), TODAY, HS, NOW)
    i0, n = _day_calls(dry, X)
    assert n >= 5 and i0 > 0
    cube = cu.Cube(None, "a~1", "222")
    try:
        cu.step_app(FakeGA(cap=500, extra_day=X, stop_after=i0 + n - 1, stop_why="budget"), cube, TODAY, HS, NOW)
        raise AssertionError("no stop")
    except gf.Stop:
        pass
    assert cube.head["next"] == "2026-08-01" and "2026-08-01" not in cube.month("2026-08")["days"]
    assert "2026-07-31" in cube.month("2026-07")["days"] and cube.month("2026-08")["t"] == {}
    assert "cut" not in cube.head                               # started with what the walk left: not its cut
    ga = FakeGA(cap=500, extra_day=X)
    cu.step_app(ga, cube, TODAY, HS, NOW + timedelta(hours=1))
    assert _day_calls(ga, X) == (0, n) and "cut" not in cube.head        # read whole again, from its first call
    led = cube.month("2026-08")["days"]["2026-08-01"]
    truth = cu.read_day(FakeGA(today=LATER, extra_day=X), X, "t")
    assert led["t"] == truth["t"] and led["loss"] == led["cap"] == 0 and led["n"] == n and led["sv"] == cu.SPLIT_V
    assert cube.head["next"] == "2026-10-11" and cube.deeper >= 1 and cube.capped == 0
    # the run's first read cut after ≥ MIN_CAP calls (the budget): counted; before MIN_CAP calls, or by the app's
    # call cap (the run's allotment, not the day's cost): never
    for stop, why, counted in ((cu.MIN_CAP, "budget", True), (cu.MIN_CAP - 1, "budget", False),
                               (cu.MIN_CAP + 1, "calls", False)):
        h = {}
        try:
            list(cu.read_range(FakeGA(today=LATER, cap=500, extra_day=X, stop_after=stop, stop_why=why), X, X, h,
                               "t"))
        except gf.Stop:
            pass
        assert ("cut" in h) is counted and (not counted or h["cut"] == {"D": "2026-08-01", "n": stop, "k": 1})


def test_a_day_cut_run_after_run_gets_a_smaller_cap():
    """A day too costly for what a run can give it never stalls the walk: cut as the run's first read CUT_TRIES times
    (each after ≥ MIN_CAP of its calls), it is read with the calls a run gave it less one (then half that …, never
    below MIN_CAP): folded with what is still "(other)" as measured loss, "cap" 2 — under its full cap a read again
    could take more (the repair's queue counts it)."""
    D, C = date(2026, 9, 10), 64                                # C: the day's cap here
    full = cu.read_day(FakeGA(today=LATER, cap=110, extra_day=D), D, "t", cap=C)
    N, h = full["n"], {}
    assert 10 <= N <= C and full["loss"] == 0
    for stop in (N - 2, N - 4):
        try:
            list(cu.read_range(FakeGA(today=LATER, cap=110, extra_day=D, stop_after=stop, stop_why="budget"), D, D, h,
                               "t", cap=C))
            raise AssertionError("no stop")
        except gf.Stop:
            pass
    assert h["cut"] == {"D": "2026-09-10", "n": N - 2, "k": 2}
    assert cu._cap_of(h["cut"], C) == N - 3 and cu._cap_of(None, C) == C
    assert cu._cap_of({"D": "x", "n": N - 2, "k": 3}, C) == max(cu.MIN_CAP, (N - 3) // 2)
    assert cu._cap_of({"D": "x", "n": 3, "k": 9}, C) == cu.MIN_CAP
    ga = FakeGA(today=LATER, cap=110, extra_day=D)
    (_, rec), = cu.read_range(ga, D, D, h, "t", cap=C)
    assert ga.calls <= N - 3 and rec["n"] == ga.calls and rec["cap"] == 2 and rec["loss"] == rec["ol"] > 0
    assert rec["t"] == full["t"] == _rec_sum(rec) and "cut" not in h
    _cells_le(rec, full)
    assert cu._oloss(rec) == rec["ol"] and cu._oloss(dict(rec, cap=1)) == 0     # recoverable only under a smaller cap
    # the day's own cap reached (not a smaller one): "cap" 1, final for this split version
    ga = FakeGA(today=LATER, cap=110, extra_day=D)
    rec = cu.read_day(ga, D, "t")
    assert rec["cap"] == 1 and ga.calls <= cu.DAY_CAP and cu._oloss(rec) == 0


def test_a_cut_counts_only_when_the_app_had_the_runs_whole_budget(monkeypatch, tmp_path):
    """Apps of one property run one after another on one budget: a day the budget cut as the first read of an app
    that started late (after another app) never had the run's whole allowance — not its cut (its cap never shrinks
    to fit a part of a run); that app goes first next run instead ("late"), so its day gets the whole allowance."""
    X = date(2026, 8, 1)
    for full, counted in ((True, True), (False, False)):
        h, ga = {}, FakeGA(today=LATER, cap=500, extra_day=X, stop_after=cu.MIN_CAP, stop_why="budget")
        ga.full = full
        try:
            list(cu.read_range(ga, X, X, h, "t"))
        except gf.Stop:
            pass
        assert ("cut" in h) is counted
    data = str(tmp_path)
    routes = {"com.example.first": {"property_id": "111", "stream_id": "221", "owner": "o"},
              "com.example.second": {"property_id": "111", "stream_id": "222", "owner": "o"}}
    monkeypatch.setattr(cu.gu, "load_state", lambda d: {"routes": {"by_package": routes}, "tz": {"111": "UTC"},
                                                        "fetch": {}})
    monkeypatch.setattr(cu.gaud, "_uni_meta", lambda ust, d, aid, r: {"history_start": "2026-08-01"})
    monkeypatch.setattr(cu.ga4, "access_token", lambda c, s, r: "tok")
    clock, phase, D, made, full = [0.0], [1], date(2026, 10, 11), {}, {}

    class A(FakeGA):
        def __init__(self, token, pid, sid, prop, over=None, max_calls=cu.MAX_CALLS):
            heavy = sid == "222" and phase[0] == 2              # the second app's new final day: a heavy one
            super().__init__(today=TODAY + timedelta(days=phase[0] - 1), start=date(2026, 8, 1),
                             cap=500 if heavy else None, extra_day=D if heavy else None)
            self.over, self.max_calls, self.sid = over, max_calls, sid
            self.cost = 14.0 if sid == "221" else 3.0           # seconds a call

        def report_all(self, body, **kw):
            full[self.sid] = self.full
            if self.over and self.over():
                raise gf.Stop("budget")
            clock[0] += self.cost
            made[self.sid] = made.get(self.sid, 0) + 1
            return super().report_all(body, **kw)
    monkeypatch.setattr(cu.gf, "App", A)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    apps = [{"app_id": "x~1", "package": "com.example.first"}, {"app_id": "x~2", "package": "com.example.second"}]
    out = cu.refresh_all(cfg, data, apps, NOW, clock=lambda: clock[0], budget=1000)
    assert out["apps"] == {"x~1": "fetched", "x~2": "fetched"} and full == {"221": True, "222": True}
    phase[0], made = 2, {}
    out = cu.refresh_all(cfg, data, apps, NOW + timedelta(days=1), clock=lambda: clock[0], budget=40)
    assert out["apps"] == {"x~1": "fetched", "x~2": "deferred"} and made["221"] == 2 and made["222"] >= cu.MIN_CAP
    assert full == {"221": True, "222": False}                  # x~2 started with 12 s of 40 left
    h = cu.load_head(data, "x~2")
    assert "cut" not in h and h["next"] == D.isoformat()       # cut, not counted; read again whole next run
    assert cu.load_state(data)["fetch"]["x~2"]["late"] is True
    made, order = {}, []
    real = A.report_all

    def first(self, body, **kw):
        if not order or order[-1] != self.sid:
            order.append(self.sid)
        return real(self, body, **kw)
    monkeypatch.setattr(A, "report_all", first)
    out = cu.refresh_all(cfg, data, apps, NOW + timedelta(days=1, hours=7), clock=lambda: clock[0], budget=40)
    assert order[0] == "222" and full["222"] is True                   # first now (x~1's hot round is due too: it
                                                                       # would have gone first), the whole budget
    assert D.isoformat() in cu.Cube(data, "x~2", "222").month("2026-10")["days"]   # its day read and folded
    assert "late" not in cu.load_state(data)["fetch"]["x~2"]


def test_hot_and_final_reads_keep_their_own_cut_memory():
    """A hot day cut run after run (the hot cap) never passes its smaller cap to its final read: the walk reads it
    with the day's full cap; the hot day's memory goes once the day is final."""
    D = date(2026, 10, 11)
    cube = cu.Cube(None, "a~1", "222")
    _runs(cube, [(TODAY, NOW, None)])
    cube.head["hcut"] = {"D": D.isoformat(), "n": 5, "k": 2}   # cut twice while hot, after 5 calls
    nxt = TODAY + timedelta(days=1)                             # Oct 11 final now
    ga = FakeGA(today=nxt, cap=200, extra_day=D)
    cu.step_app(ga, cube, nxt, HS, NOW + timedelta(days=1))
    led = cube.month("2026-10")["days"][D.isoformat()]
    assert "hcut" not in cube.head and led["cap"] != 2 and _day_calls(ga, D)[1] >= 10
    clean = cu.read_day(FakeGA(today=LATER, cap=200, extra_day=D), D, "t")
    assert led["loss"] == clean["loss"] and led["n"] == clean["n"]
    # a hot read takes its own memory, never the walk's
    h = {"cut": {"D": "2026-10-12", "n": 5, "k": 2}}
    ga = FakeGA(cap=200, extra_day=date(2026, 10, 12))
    got = dict(cu.read_range(ga, date(2026, 10, 12), date(2026, 10, 12), h, "t", cap=cu.HOT_CAP, key="hcut"))
    assert got[date(2026, 10, 12)]["n"] > 4 and h["cut"]["n"] == 5


def test_a_hot_round_cut_by_a_stop_goes_on_with_the_days_it_has_not_read():
    cube = cu.Cube(None, "a~1", "222")
    _runs(cube, [(TODAY, NOW, None)])
    ga = FakeGA(cap=1000)                                      # heavy: the hot days day by day (block dropped)
    try:
        cu.step_app(FakeGA(cap=1000, stop_after=2), cube, TODAY, HS, NOW + timedelta(hours=7))   # block + Oct 11
    except gf.Stop:
        pass
    assert cube.head["hot_cyc"] == [cu.gu._now_iso(NOW + timedelta(hours=7)), TODAY.isoformat()]
    assert cube.head["d"]["2026-10-11"]["at"] == cu.gu._now_iso(NOW + timedelta(hours=7))
    cu.step_app(ga, cube, TODAY, HS, NOW + timedelta(hours=8))
    assert _reads(ga) == [("2026-10-12", "2026-10-13"), ("2026-10-12", "2026-10-12"), ("2026-10-13", "2026-10-13")]
    assert "hot_cyc" not in cube.head and cube.head["hot_at"] == cu.gu._now_iso(NOW + timedelta(hours=8))


# ── the repair: months folded with the one-level split, read again and replaced whole ──────────────────────────────
RS = date(2026, 9, 1)                                           # the repaired app's history start


def _old(D, today, cap=40):
    """Day D as the one-level split read it before 21 Oct 2026: ≤ 3 calls, the ledger without sv / ol / n / cap."""
    rec = cu.read_day(FakeGA(today=today, cap=cap, start=RS), D, "t", cap=3)
    for f in ("sv", "ol", "n", "cap"):
        rec.pop(f)
    return rec


def _old_cube(data, today):
    """Sep 1 … today − FINAL_LAG folded by the one-level split (GA4's limit 40 rows: most days kept "(other)"), the
    walk through and the hot days just read — a run then has only the repair to do."""
    cube = cu.Cube(data, "a~1", "222")
    edge = today - timedelta(days=cu.FINAL_LAG)
    for D in _days(RS, edge):
        cube.fold(D, _old(D, today))
    now = datetime(today.year, today.month, today.day, 1, 0, tzinfo=timezone.utc)
    cube.head.update(stream_id="222", **{"from": RS.isoformat(), "next": (edge + timedelta(days=1)).isoformat(),
                                         "done": True, "hot_at": cu.gu._now_iso(now), "hot_today": today.isoformat()})
    _save(cube)
    return cube


def _raw(data, k):
    with open(cu.month_path(data, "a~1", k), "rb") as f:
        return f.read()


def test_repair_reads_lossy_months_again_and_replaces_them_whole(tmp_path):
    data, T0 = str(tmp_path), date(2026, 10, 13)
    _old_cube(data, T0)
    old = {k: _raw(data, k) for k in ("2026-09", "2026-10")}
    sep, octo = _month(data, "2026-09"), _month(data, "2026-10")
    assert all(v["sv"] is None for v in sep["days"].values()) and sum(sep["loss"].values()) > 0
    share = {k: cu._month_oloss(m)[0] / cu._month_oloss(m)[2] for k, m in (("2026-09", sep), ("2026-10", octo))}
    assert share["2026-10"] > share["2026-09"] > 0.05                    # October lost more: it goes first
    runs, seen_copy, T = 0, False, T0
    while runs < 40:
        runs += 1
        T = T0 + timedelta(days=1) if runs >= 2 else T0                  # run 2 on: a new day, the walk folds Oct 11
        cube = cu.Cube(data, "a~1", "222")
        ga = FakeGA(today=T, cap=40, start=RS, max_calls=cu.MAX_CALLS)
        cu.step_app(ga, cube, T, RS, datetime(T.year, T.month, T.day, 2, runs % 24, tzinfo=timezone.utc))
        _save(cube)
        rp = cube.head["rep"]
        assert ga.calls <= cu.MAX_CALLS
        for k in ("2026-09", "2026-10"):
            if rp.get("k") == k:                                        # being built: the month file as it was (the
                assert os.path.exists(cube.rep_path(k))                 # walk's new days only)
                live = _month(data, k)
                assert {D: v for D, v in live["days"].items() if D <= "2026-10-10"} == \
                    (octo if k == "2026-10" else sep)["days"]
                assert k == "2026-10" or _raw(data, k) == old[k]
                seen_copy = True
            else:
                assert not os.path.exists(cube.rep_path(k))
        if not rp.get("k") and not rp.get("q"):
            break
    assert seen_copy and 3 <= runs < 40 and [e[0] for e in rp["log"]] == ["2026-10", "2026-09"]    # biggest share 1st
    full = cu.Cube(None, "a~1", "222")
    for D in _days(RS, date(2026, 10, 11)):
        full.fold(D, cu.read_day(FakeGA(today=LATER, start=RS), D, "t"))
    for k in ("2026-09", "2026-10"):
        mo = _month(data, k)
        assert mo["rep"]["sv"] == cu.SPLIT_V and mo["rep"]["ol0"] > 0 and mo["loss"] == {}
        assert all(v["sv"] == cu.SPLIT_V and v["loss"] == 0 and v["ol"] == 0 for v in mo["days"].values())
        assert {f: mo[f] for f in ("b", "c", "e", "t")} == {f: full.month(k)[f] for f in ("b", "c", "e", "t")}, k
    assert sorted(_month(data, "2026-10")["days"])[-1] == "2026-10-11"  # the day the walk folded meanwhile: in it
    assert [e[2] for e in rp["log"]] == [0, 0] and all(e[1] > 0 for e in rp["log"])
    # never repaired twice: the queue made again finds nothing (every day read with this split)
    cube = cu.Cube(data, "a~1", "222")
    cube.head["rep"]["scan"] = "2026-01-01T00:00:00Z"
    ga = FakeGA(today=T, cap=40, start=RS)
    assert cu.repair(ga, cube, datetime(2026, 10, 15, tzinfo=timezone.utc)) is False and ga.calls == 0
    assert cube.head["rep"]["q"] == [] and cube.repaired == 0


def test_repair_keeps_the_old_month_until_every_day_is_read(tmp_path, monkeypatch):
    """A Stop in the repair (the budget): the days read are kept in the copy, the month file is untouched; the app's
    own call cap only ends the repair for the run (no deferral). The copy becomes the month only when it holds every
    day of it."""
    data, T = str(tmp_path), date(2026, 10, 3)
    _old_cube(data, T)
    old = _raw(data, "2026-09")
    now = datetime(2026, 10, 3, 2, tzinfo=timezone.utc)
    cube = cu.Cube(data, "a~1", "222")
    try:
        cu.step_app(FakeGA(today=T, cap=40, start=RS, stop_after=14, stop_why="budget"), cube, T, RS, now)
        raise AssertionError("no stop")
    except gf.Stop:
        pass
    _save(cube)                                                     # what refresh_all does after a Stop
    rep = cu.gu.load_store(cube.rep_path("2026-09"))
    assert _raw(data, "2026-09") == old and cube.head["rep"]["k"] == "2026-09"
    assert 1 <= len(rep["days"]) < 30 and all(v["sv"] == cu.SPLIT_V for v in rep["days"].values())
    got = set(rep["days"])
    cube = cu.Cube(data, "a~1", "222")                              # the call cap: the repair just ends, "fetched"
    ga = FakeGA(today=T, cap=40, start=RS, max_calls=12)
    assert cu.step_app(ga, cube, T, RS, now + timedelta(hours=1)) == "fetched"
    _save(cube)
    rep = cu.gu.load_store(cube.rep_path("2026-09"))
    assert got < set(rep["days"]) and _raw(data, "2026-09") == old and ga.calls <= 12
    for i in range(20):                                             # on to the end
        cube = cu.Cube(data, "a~1", "222")
        cu.step_app(FakeGA(today=T, cap=40, start=RS, max_calls=cu.MAX_CALLS), cube, T, RS,
                    now + timedelta(hours=2 + i))
        _save(cube)
        if not cube.head["rep"].get("k"):
            break
    mo = _month(data, "2026-09")
    assert sorted(mo["days"]) == [D.isoformat() for D in _days(RS, date(2026, 9, 30))] and mo["loss"] == {}
    assert not os.path.exists(cube.rep_path("2026-09")) and _raw(data, "2026-09") != old
    # a copy of an older split version (or another stream's) is never taken as this one's
    cube = cu.Cube(data, "a~1", "222")
    cu.write_json_gz_stable(cube.rep_path("2026-08"), dict(cu._empty_month("222"), rep={"sv": 1},
                                                            days={"2026-08-01": {}}))
    assert cube.rep("2026-08")["days"] == {}


def test_repair_queue_order_and_versions():
    """The queue: months with "(other)" a deeper split could read — the biggest share of the month's revenue first,
    the more recent month first on a tie; a "block" / "day" day's loss (install days that are not dates) and a day
    read with this split never count; a newer split version queues a month again only where "(other)" is left."""
    cube = cu.Cube(None, "a~1", "222")

    def day(D, via, loss, t, **kw):
        cube.fold(D, dict({"st": "loss" if loss else "ok", "rows": 1, "loss": loss, "t": t, "fl": 0, "via": via,
                           "at": "x", "b": {}, "c": {}, "e": {}}, **kw))
    day(date(2026, 5, 1), "split", 500, 1000, sv=2, ol=500)       # read with this split: never again
    day(date(2026, 6, 1), "block", 300, 1000)                     # no "(other)" row: its loss no split reads
    day(date(2026, 6, 2), "day", 300, 1000)
    day(date(2026, 7, 1), "split", 100, 1000)                     # 10 %
    day(date(2026, 8, 1), "split", 200, 1000)                     # 20 %
    day(date(2026, 9, 1), "split", 100, 500)                      # 10 % (with a clean day)
    day(date(2026, 9, 2), "day", 0, 500)
    day(date(2026, 10, 1), "split", 0, 1000)                      # a split day that kept nothing "(other)"
    assert cu._scan(cube) == [["2026-08", 0.2], ["2026-09", 0.1], ["2026-07", 0.1]]
    assert cu._oloss({"via": "split", "loss": 9, "ol": 4}) == 4 and cu._oloss({"via": "split", "loss": 9, "sv": 2}) == 0
    old_v = cu.SPLIT_V
    try:
        cu.SPLIT_V = 3                                            # a still deeper split one day: "ol" > 0 again
        assert cu._scan(cube) == [["2026-05", 0.5], ["2026-08", 0.2], ["2026-09", 0.1], ["2026-07", 0.1]]
    finally:
        cu.SPLIT_V = old_v
    # a one-level split day GA4 flagged with no "(other)" row (its in-list part may have hidden some): queued, by
    # how much unknown — after every month with a measured share, the more recent first
    day(date(2026, 4, 1), "split", 0, 1000, fl=1)
    day(date(2026, 3, 1), "split", 0, 1000, fl=1)
    day(date(2026, 2, 1), "day", 0, 1000, fl=1)                  # no split part: nothing a split reads
    assert cu._scan(cube) == [["2026-08", 0.2], ["2026-09", 0.1], ["2026-07", 0.1], ["2026-04", 0.0],
                              ["2026-03", 0.0]]
    # a day read with this split under a smaller cap than a day's (cap 2: cut run after run): recoverable — once: a
    # day folded after the month's repair of this split counts, one the repair itself read so does not (no loop)
    cube = cu.Cube(None, "a~1", "222")
    day(date(2026, 7, 1), "split", 100, 1000, sv=2, ol=100, cap=2, at="2026-07-02T01:00:00Z")
    day(date(2026, 7, 2), "split", 100, 1000, sv=2, ol=100, cap=1, at="2026-07-03T01:00:00Z")    # the day's own cap
    assert cu._scan(cube) == [["2026-07", 0.05]]
    cube.month("2026-07")["rep"] = {"sv": cu.SPLIT_V, "at": "2026-07-05T01:00:00Z"}
    assert cu._scan(cube) == []
    day(date(2026, 7, 9), "split", 300, 1000, sv=2, ol=300, cap=2, at="2026-07-10T01:00:00Z")    # after the repair
    assert cu._scan(cube) == [["2026-07", 0.1]] and cu._month_oloss(cube.month("2026-07"))[:3] == (300, 500, 3000)


def _filled_copy(data, T, k="2026-09"):
    """The repair's copy of month k holding every day (read with this split), the head naming it — as a run that read
    its last day but stopped (the budget) before it could replace the month leaves them."""
    _old_cube(data, T)
    cube = cu.Cube(data, "a~1", "222")
    live = cube.month(k)
    acc = cube.rep(k)
    for D in sorted(live["days"]):
        cu._merge(acc, D, cu.read_day(FakeGA(today=T, cap=40, start=RS), date.fromisoformat(D), "t"))
    cube.rp["dirty"] = True
    ol, lo, t, _ = cu._month_oloss(live)
    cube.head["rep"] = {"sv": cu.SPLIT_V, "scan": "2026-10-03T00:00:00Z", "q": [], "k": k, "old": {"ol": ol, "loss": lo,
                                                                                                  "t": t},
                        "at": "2026-10-03T00:00:00Z", "c": 90, "n": 30}
    _save(cube)
    return cube


def test_repair_completed_in_a_run_with_no_call_writes_its_head(tmp_path):
    """The copy already whole (an earlier run read every day): the run that makes it the month reads nothing — its
    head is written all the same (k cleared), and the copy goes only after it; a head left naming a month already
    repaired (the run killed between the month and its head, the copy gone) reads nothing of it again."""
    data, T = str(tmp_path), date(2026, 10, 3)
    _filled_copy(data, T)
    old_head = cu.gu.load_store(cu.hot_path(data, "a~1"))
    cube, ga = cu.Cube(data, "a~1", "222"), FakeGA(today=T, cap=40, start=RS, max_calls=cu.MAX_CALLS)
    now = datetime(2026, 10, 3, 2, tzinfo=timezone.utc)
    assert cu.repair(ga, cube, now) is False and ga.calls == 0 and cube.repaired == 1
    assert cube.dirty and os.path.exists(cube.rep_path("2026-09"))      # the copy kept until the head is written
    cube.save()                                                         # refresh_all: months, then the head (the
    assert os.path.exists(cube.rep_path("2026-09"))                     # run's condition holds: dirty)
    cube.save_head()
    assert not os.path.exists(cube.rep_path("2026-09"))
    h = cu.load_head(data, "a~1")
    assert "k" not in h["rep"] and [e[0] for e in h["rep"]["log"]] == ["2026-09"]
    mo = _month(data, "2026-09")
    assert mo["rep"]["sv"] == cu.SPLIT_V and all(v["sv"] == cu.SPLIT_V for v in mo["days"].values())
    # the head as it was before (still naming the month), the copy gone: nothing read again, the entry cleared
    cu.write_json_gz_stable(cu.hot_path(data, "a~1"), old_head)
    raw = _raw(data, "2026-09")
    cube, ga = cu.Cube(data, "a~1", "222"), FakeGA(today=T, cap=40, start=RS, max_calls=cu.MAX_CALLS)
    assert cu.repair(ga, cube, now + timedelta(hours=1)) is False and ga.calls == 0 and cube.dirty
    assert "k" not in cube.head["rep"] and cube.repaired == 0
    _save(cube)
    assert _raw(data, "2026-09") == raw and "k" not in cu.load_head(data, "a~1")["rep"]


def test_repair_reads_day_by_day_and_starts_a_day_only_with_room(tmp_path):
    """The repair never tries a block (a month with "(other)" only comes back with it again); it starts a day only
    when the run's calls left fit what a day needs (DAY_CAP + 1 before its first day, then its calls a day so far) —
    checked before every day; a day the app's call cap cut is read again next run, never counted as its cut (no
    smaller cap from what the walk and the hot days left)."""
    data, T = str(tmp_path), date(2026, 10, 3)
    _old_cube(data, T)
    now = datetime(2026, 10, 3, 2, tzinfo=timezone.utc)
    cube = cu.Cube(data, "a~1", "222")
    ga = FakeGA(today=T, cap=40, start=RS, max_calls=cu.MAX_CALLS)
    ga.calls = cu.MAX_CALLS - cu.DAY_CAP                                 # what the walk and the hot days left
    assert cu.repair(ga, cube, now) is False and ga.calls == cu.MAX_CALLS - cu.DAY_CAP
    assert cube.head["rep"]["k"] == "2026-09" and cube.head["rep"]["n"] == 0
    ga = FakeGA(today=T, cap=40, start=RS, max_calls=cu.MAX_CALLS)
    assert cu.repair(ga, cube, now) is True and not _multi(ga) and cube.rep_days >= 3
    rp = cube.head["rep"]
    need = max(cu.MIN_CAP, -(-rp["c"] // rp["n"]))
    assert rp["c"] == ga.calls and (ga.calls >= cu.REPAIR_CALLS or cu.MAX_CALLS - ga.calls < need)
    assert "cut" not in rp
    acc = cube.rep("2026-09")["days"]                          # the log's per-day counts take the repair days too
    assert cube.folded == 0 and cube.rep_days == len(acc) and 0 < cube.split == sum(v["via"] == "split"
                                                                                    for v in acc.values())
    # a day cut by the app's call cap (its calls a day so far fitted, this one needed more): not kept, not its cut
    seen = False
    for _ in range(3):
        got = len(cube.rep("2026-09")["days"])
        ga = FakeGA(today=T, cap=40, start=RS, max_calls=need)
        rp["c"], rp["n"] = rp["n"], rp["n"]                              # one call a day so far: room for need
        cu.repair(ga, cube, now)
        assert "cut" not in rp and len(cube.rep("2026-09")["days"]) >= got
        seen = seen or (ga.calls == need and len(cube.rep("2026-09")["days"]) == got)
    assert seen                                                          # a day was cut (and not kept) at least once


def test_repair_starts_a_day_only_with_time_for_it(tmp_path):
    """The run's budget, not only its calls: a repair day is started only when the time left fits the most calls a
    repair day took at the app's seconds a call (this run's, else the last measured) — a budget Stop would throw the
    started day's calls (and the property's shared tokens) away. Runs the budget ends make no more calls in all than
    runs with no budget."""
    ga = FakeGA(max_calls=cu.MAX_CALLS)
    t = [50.0]
    ga.clock, ga.t_end, ga.t_app = (lambda: t[0]), 100.0, 0.0
    rp = {"c": 20, "n": 4, "m": 9, "s": 5.0}                     # 5 calls a day, 9 the most, 5 s a call
    assert cu._room(ga, rp)                                     # 50 s left ≥ 9 × 5 s
    t[0] = 60.0
    assert not cu._room(ga, rp)                                 # 40 s left
    assert cu._room(ga, dict(rp, s=None)) and cu._room(FakeGA(), rp)   # nothing measured / no clock: yes

    def runs(budget_calls):
        data, T = str(tmp_path / str(budget_calls)), date(2026, 10, 3)
        _old_cube(data, T)
        calls = stops = 0
        for i in range(30):
            clock = [0.0]

            class G(FakeGA):
                def report_all(self, body, **kw):
                    if budget_calls and clock[0] >= budget_calls * 5:
                        raise gf.Stop("budget")
                    clock[0] += 5.0
                    return super().report_all(body, **kw)
            ga = G(today=T, cap=40, start=RS, max_calls=cu.MAX_CALLS)
            ga.clock, ga.t_end, ga.t_app = (lambda: clock[0]), (budget_calls or 10 ** 6) * 5.0, 0.0
            cube = cu.Cube(data, "a~1", "222")
            try:
                cu.step_app(ga, cube, T, RS, datetime(2026, 10, 3, 2, i, tzinfo=timezone.utc))
            except gf.Stop:
                stops += 1
            _save(cube)
            calls += ga.calls
            if not cube.head["rep"].get("k") and not cube.head["rep"].get("q"):
                return calls, stops, cube.head["rep"]
        raise AssertionError("repair never done")
    free, _, rep = runs(None)
    assert rep["s"] == 5.0 and [e[0] for e in rep["log"]] == ["2026-09"]
    for b in (28, 25):
        assert runs(b)[:2] == (free, 0), b                      # no day thrown away


def test_repair_of_a_month_whose_file_is_gone_moves_on(tmp_path):
    """The head names a month being repaired, its copy holds days, but the month file is gone: nothing to read in it
    — the copy dropped and the entry cleared (never a repair stuck on it, every other month blocked)."""
    data, T = str(tmp_path), date(2026, 10, 3)
    _old_cube(data, T)
    now = datetime(2026, 10, 3, 2, tzinfo=timezone.utc)
    cube = cu.Cube(data, "a~1", "222")
    try:
        cu.step_app(FakeGA(today=T, cap=40, start=RS, stop_after=14, stop_why="budget"), cube, T, RS, now)
        raise AssertionError("no stop")
    except gf.Stop:
        pass
    _save(cube)
    assert cube.head["rep"]["k"] == "2026-09" and os.path.exists(cube.rep_path("2026-09"))
    os.remove(cu.month_path(data, "a~1", "2026-09"))
    cube, ga = cu.Cube(data, "a~1", "222"), FakeGA(today=T, cap=40, start=RS, max_calls=cu.MAX_CALLS)
    assert cu.step_app(ga, cube, T, RS, now + timedelta(hours=1)) == "fresh" and ga.calls == 0 and cube.dirty
    _save(cube)
    assert "k" not in cu.load_head(data, "a~1")["rep"] and not os.path.exists(cube.rep_path("2026-09"))


# ── the run and the build hook ──────────────────────────────────────────────────────────────────────────────────────
def _refresh(monkeypatch, tmp_path, stop_after=None, apps=None, tick=None, workers=cu.WORKERS):
    """refresh_all over two made-up properties; tick: seconds each GA4 call takes on a fake clock (None: the real one)."""
    data, clk = str(tmp_path), [0.0]
    route = {"property_id": "111", "stream_id": "222", "owner": "o"}
    monkeypatch.setattr(cu.gu, "load_state", lambda d: {"routes": {"by_package": {"com.example.alpha": route,
                                                                                  "com.example.beta": dict(route, property_id="112")}},
                                                        "tz": {"111": "Asia/Kolkata", "112": "UTC"}, "fetch": {}})
    monkeypatch.setattr(cu.gaud, "_uni_meta", lambda ust, d, aid, r: {"history_start": "2026-08-01"})
    monkeypatch.setattr(cu.ga4, "access_token", lambda c, s, r: "tok")

    class A(FakeGA):
        def __init__(self, token, pid, sid, prop, over=None, max_calls=cu.MAX_CALLS):
            super().__init__(start=date(2026, 8, 1), stop_after=stop_after)

        def report_all(self, *a, **k):
            clk[0] += tick or 0
            return super().report_all(*a, **k)
    monkeypatch.setattr(cu.gf, "App", A)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    apps = apps or [{"app_id": "x~1", "package": "com.example.alpha"}, {"app_id": "x~2", "package": "com.example.beta"},
                    {"app_id": "x~3", "package": "com.example.none"}]
    return data, cu.refresh_all(cfg, data, apps, NOW, clock=(lambda: clk[0]) if tick is not None else None,
                                workers=workers)


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
    assert ", deeper 0, capped 0, " in line and ", repair days 0, months repaired 0, q days 0, q flagged 0, " in line
    assert all(cu.load_head(data, aid)["rep"] == {"sv": cu.SPLIT_V, "scan": "2026-10-13T06:00:00Z", "q": []}
               for aid in ("x~1", "x~2"))                       # nothing to repair: the queue made once, empty
    # a Stop part-way: what was folded is on disk (months before the head), the app deferred, the walk goes on next run
    data2, out2 = _refresh(monkeypatch, tmp_path / "b", stop_after=1, apps=[{"app_id": "x~1",
                                                                            "package": "com.example.alpha"}])
    assert out2["apps"] == {"x~1": "deferred"} and out2["counts"]["days"] == 30
    h = cu.load_head(data2, "x~1")
    assert h["next"] == "2026-08-31" and not h.get("done") and len(_month(data2, "2026-08", "x~1")["days"]) == 30


def test_a_long_backfill_never_starves_a_light_app(monkeypatch, tmp_path):
    """Two apps on one property: a heavy one whose backfill (day by day) takes the whole budget each run, and a light
    one. The light app gets its turn the next run (it waited longest), and on a tie the app the budget cut off last
    time goes after the others — the heavy backfill goes on, the light app is never left "deferred" run after run."""
    data = str(tmp_path)
    routes = {"com.example.heavy": {"property_id": "111", "stream_id": "221", "owner": "o"},
              "com.example.light": {"property_id": "111", "stream_id": "222", "owner": "o"}}
    monkeypatch.setattr(cu.gu, "load_state", lambda d: {"routes": {"by_package": routes}, "tz": {"111": "UTC"},
                                                        "fetch": {}})
    hs = {"x~1": "2025-01-01", "x~2": "2026-08-01"}
    monkeypatch.setattr(cu.gaud, "_uni_meta", lambda ust, d, aid, r: {"history_start": hs[aid]})
    monkeypatch.setattr(cu.ga4, "access_token", lambda c, s, r: "tok")
    clock = [0.0]

    class A(FakeGA):
        def __init__(self, token, pid, sid, prop, over=None, max_calls=cu.MAX_CALLS):
            heavy = sid == "221"
            super().__init__(start=date(2025, 1, 1) if heavy else date(2026, 8, 1), cap=1000 if heavy else None)
            self.over = over

        def report_all(self, body, **kw):
            if self.over and self.over():
                raise gf.Stop("budget")
            clock[0] += 1.0                                     # a call takes a second of the run's budget
            return super().report_all(body, **kw)
    monkeypatch.setattr(cu.gf, "App", A)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    apps = [{"app_id": "x~1", "package": "com.example.heavy"}, {"app_id": "x~2", "package": "com.example.light"}]
    got = []
    for i in range(4):
        out = cu.refresh_all(cfg, data, apps, NOW + timedelta(hours=i), clock=lambda: clock[0], budget=20)
        got.append(out["apps"])
    assert got[0] == {"x~1": "deferred", "x~2": "deferred"}            # the heavy app first (by id), the budget gone
    assert got[1] == {"x~1": "deferred", "x~2": "fetched"}             # the light app waited longest: first now
    assert got[2] == got[3] == {"x~1": "deferred", "x~2": "fresh"}     # a tie: the one cut off last time goes after
    h = cu.load_head(data, "x~1")
    assert not h.get("done") and h["next"] > "2025-02-15"              # the backfill went on every run
    st = cu.load_state(data)["fetch"]
    assert st["x~1"]["cut"] is True and "cut" not in st["x~2"] and st["x~2"]["turn"] == st["x~1"]["turn"]


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
        "deeper 0, capped 0, hidden 0, futile 0, loss 0, flagged 0, months read again 0, repair days 0, "
        "months repaired 0, q days 0, q flagged 0, q calls 0, q left 0, q unscanned 0, q errors 0, calls 0, tokens 0"]
    monkeypatch.setattr(cu, "refresh_all", lambda *a, **k: 1 / 0)
    dash = tub.dashboard()
    ub.run_uninstall(dash, data, out, tub.ga4_settings(ga4_cube=True), now=tub.NOW)
    assert "ga4 cube skipped: ZeroDivisionError" in capsys.readouterr().err and dash["uninstall"]["apps"]


def test_repair_off_by_default(monkeypatch):
    """GA4_CUBE_REPAIR_CALLS unset → REPAIR_CALLS 0 and step_app never calls the repair (no call, no copy, head kept)."""
    import importlib
    monkeypatch.delenv("GA4_CUBE_REPAIR_CALLS", raising=False)
    fresh = importlib.reload(cu)
    try:
        assert fresh.REPAIR_CALLS == 0
        monkeypatch.setattr(fresh, "repair", lambda *a, **k: (_ for _ in ()).throw(AssertionError("repair called")))
        ga = FakeGA(today=LATER)
        cube = fresh.Cube(None, "x~1", "s1")
        fresh.step_app(ga, cube, LATER, HS, datetime(LATER.year, LATER.month, LATER.day, 12, tzinfo=timezone.utc))
    finally:
        monkeypatch.setenv("GA4_CUBE_REPAIR_CALLS", "30")
        importlib.reload(cu)
    assert cu.REPAIR_CALLS == 30


def test_sampled_day_not_chased():
    """A day whose every part GA4 samples: one split (3 calls) shows the halves sampled too → stop there (no 23-call
    walk to the cap); the day kept as read, flagged, "fu" kept on its ledger."""
    D = TODAY - timedelta(days=10)
    ga = FakeGA(today=TODAY, smp_day=D)
    rows, info = cu.split_read(ga, D, cap=cu.DAY_CAP, total=cu.day_total)
    assert ga.calls <= 3 and info["futile"] == 1 and info["flag"]
    rec = cu.read_day(FakeGA(today=TODAY, smp_day=D), D, "2026-10-21T00:00:00Z")
    assert rec.get("fu") == 1 and rec["n"] <= 3
    mo = cu._empty_month("s1")
    cu._merge(mo, D.isoformat(), rec)
    assert mo["days"][D.isoformat()]["fu"] == 1 and "hd" not in mo["days"][D.isoformat()]



# ── q: the whole no-country read of a day (ages 31 … 420 of the All rows) ───────────────────────────────────────────
class QGA:
    """GA4 answering one fixed set of rows (dimension firstSessionDate) with the given flags."""

    def __init__(self, rows, meta=None, cut=False):
        self.rows, self.meta, self.cut, self.calls, self.asked = rows, meta or {}, cut, 0, []

    def report_all(self, body, extra=None, page_rows=None, **kw):
        self.calls += 1
        self.asked.append((body, extra, page_rows))
        self.last_metas = [{}, self.meta]
        return [dict(r) for r in self.rows]

    def truncated(self, rows):
        return self.cut


def _qrow(D, L, usd, X=None):
    return {"firstSessionDate": X if X is not None else ymd(D - timedelta(days=L)), "activeUsers": 1,
            "totalAdRevenue": usd}


def test_q_read_ages_and_shape():
    D = date(2026, 9, 30)
    ages = (0, 30, 31, 60, 61, 420, 421, 427)
    ga = QGA([_qrow(D, L, (L + 1) / 1e6) for L in ages])
    got = cu.q_read(ga, D)
    body, extra, page_rows = ga.asked[0]
    assert [d["name"] for d in body["dimensions"]] == ["firstSessionDate"] and not extra   # no filter, every page
    assert body["dateRanges"] == [{"startDate": "2026-09-30", "endDate": "2026-09-30"}] and page_rows == cu.gu.UNI_PAGE_ROWS
    X = lambda L: (D - timedelta(days=L)).isoformat()                       # noqa: E731
    assert got["q"] == {X(31): {"1": 32}, X(60): {"1": 61}, X(61): {"2": 62}, X(420): {"13": 421}}
    assert got["qt"] == sum(L + 1 for L in ages if L <= 420) and got["qs"] == "ok" and got["qr"] == len(ages)
    assert got["qn"] == 0 and got["qx"] == 427                              # the oldest age GA4 returned: kept
    assert cu.QJ == 13 and cu.QL == 420 and cu.bucket(cu.QL) == cu.QJ and cu.bucket(cu.QL + 1) == cu.QJ + 1


def test_q_read_not_whole_is_flagged_empty():
    D = date(2026, 9, 30)
    base = [_qrow(D, 40, 0.5), _qrow(D, 3, 0.25)]
    for rows, meta, cut in (([_qrow(D, 0, 0.1, "(other)")], {}, False), ([], {"dataLossFromOtherRow": True}, False),
                            ([], {"samplingMetadatas": [{"samplesReadCount": "1"}]}, False),
                            ([], {"subjectToThresholding": True}, False), ([], {}, True)):
        got = cu.q_read(QGA(base + rows, meta, cut), D)
        assert got["qs"] == "fl" and got["q"] == {} and got["qr"] == len(base + rows), (rows, meta, cut)
    assert cu.q_read(QGA(base), D)["qs"] == "ok"


def test_q_read_rows_without_an_install_day_are_their_size_never_fl():
    """GA4's "(not set)" install day (or one not a date, or after the day) is a real row of a whole read — not a fold:
    kept out of q and qt as "qn" (its micros), the day still "ok" (a 1-micro one too: it never costs a week its q)."""
    D, X40 = date(2026, 9, 30), (date(2026, 9, 30) - timedelta(days=40)).isoformat()
    base = [_qrow(D, 40, 0.5), _qrow(D, 3, 0.25)]
    for extra, qn in (([_qrow(D, 0, 0.000001, "(not set)")], 1),
                      ([_qrow(D, 0, 0.1, "(not set)"), _qrow(D, 0, 0.2, "junk"), _qrow(D, -1, 0.05)], 350000)):
        got = cu.q_read(QGA(base + extra), D)
        assert got["qs"] == "ok" and got["qn"] == qn and got["qt"] == 750000 and got["q"] == {X40: {"1": 500000}}
        assert got["qx"] == 40 and got["qr"] == len(base + extra)
    # the cube's own read of such a day books the same row as its loss (no install day): q's qn is that row
    ga = FakeGA(notset_day=D)
    got = cu.q_read(ga, D)
    assert got["qs"] == "ok" and got["qn"] == 500000 and got["qt"] == day_total(FakeGA(), D)


def _qday_want(D, max_lag=120, start=HS, fill=1.0):
    """The fake's whole q of activity day D: {X: {j: micros}} of ages 31 … 420 and qt (ages 0 … 420)."""
    q, qt = {}, 0
    for L in range(max_lag + 1):
        if D - timedelta(days=L) < start or L > cu.QL:
            continue
        v = micros(L, WSUM, fill)
        qt += v
        if L >= 31:
            q.setdefault((D - timedelta(days=L)).isoformat(), {})[str(cu.bucket(L))] = v
    return q, qt


def test_q_a_new_day_and_the_hot_days_get_q_in_the_same_run(tmp_path, monkeypatch):
    data = str(tmp_path)
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(), cube, TODAY, HS, NOW)                 # the cube before q (q off): nothing pending
    _save(cube)
    monkeypatch.setattr(cu, "Q_CALLS", 120)
    nxt = TODAY + timedelta(days=1)
    on = FakeGA(today=nxt)
    cube = cu.Cube(data, "a~1", "222")
    assert cu.step_app(on, cube, nxt, HS, NOW + timedelta(days=1)) == "fetched"
    _save(cube)
    # the new final day (Oct 11) folded (1 call) + the hot round (Oct 12 … 14, 1 block call) + their q: 3 + 1
    assert on.calls == 2 + 3 + 1 and cube.q_days == 4 and cube.q_calls == 4 and cube.q_fl == 0
    qf = cu.load_q(data, "a~1", "222", "2026-10")
    assert set(qf["days"]) == {"2026-10-11"} and qf["days"]["2026-10-11"]["qs"] == "ok"
    want, wqt = _qday_want(date(2026, 10, 11))
    W = "2026-10-05"
    assert qf["q"] == {X: {j: {W: v} for j, v in js.items()} for X, js in want.items()}
    led = _month(data, "2026-10")["days"]["2026-10-11"]
    assert qf["days"]["2026-10-11"]["qt"] == wqt == led["t"]        # nothing lost: the whole read = the cube's every row
    h = cu.load_head(data, "a~1")
    assert h["qh"]["p"] == []
    for k in ("2026-10-12", "2026-10-13", "2026-10-14"):           # read while filling: the same moment as the cube's
        rec = h["d"][k]
        assert rec["qs"] == "ok" and rec["qt"] == rec["t"] and rec["qr"] > 0
        assert all(len(ws) == 1 for js in rec["q"].values() for ws in js.values())
    # within 6 hours: nothing due, nothing read (a hot copy of an earlier round never gets a q)
    ga = FakeGA(today=nxt)
    assert cu.step_app(ga, cu.Cube(data, "a~1", "222"), nxt, HS, NOW + timedelta(days=1, hours=2)) == "fresh"
    assert ga.calls == 0


def test_q_a_stop_keeps_the_fold_and_the_q_days_read(tmp_path, monkeypatch):
    data = str(tmp_path)
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(), cube, TODAY, HS, NOW)
    _save(cube)
    monkeypatch.setattr(cu, "Q_CALLS", 120)
    nxt = TODAY + timedelta(days=1)
    cube = cu.Cube(data, "a~1", "222")
    ga = FakeGA(today=nxt, stop_after=4, stop_why="budget")        # fold 1 + hot 1 + 2 hot q, then the budget
    try:
        cu.step_app(ga, cube, nxt, HS, NOW + timedelta(days=1))
        raise AssertionError("no Stop")
    except gf.Stop:
        pass
    _save(cube)                                                     # as refresh_all does
    assert "2026-10-11" in _month(data, "2026-10")["days"]          # the fold kept
    h = cu.load_head(data, "a~1")
    assert [h["d"][k].get("qs") for k in ("2026-10-12", "2026-10-13", "2026-10-14")] == ["ok", "ok", None]
    assert h["qh"]["p"] == ["2026-10-11"] and cu.load_q(data, "a~1", "222", "2026-10") is None
    ga = FakeGA(today=nxt)                                          # the next run: the pending day read (1 call); the
    cube = cu.Cube(data, "a~1", "222")                              # hot day of the cut round stays without q
    assert cu.step_app(ga, cube, nxt, HS, NOW + timedelta(days=1, hours=1)) == "fetched" and ga.calls == 1
    _save(cube)
    assert set(cu.load_q(data, "a~1", "222", "2026-10")["days"]) == {"2026-10-11"}
    assert "qs" not in cu.load_head(data, "a~1")["d"]["2026-10-14"] and cu.load_head(data, "a~1")["qh"]["p"] == []
    # the app's call cap ends q quietly (the rest stays pending); never a day read twice
    cube = cu.Cube(None, "a~1", "222")
    cube.head["qh"] = {"p": ["2026-09-01", "2026-09-02", "2026-09-03"]}
    ga = FakeGA(max_calls=2)
    assert cu.q_fwd(ga, cube, NOW, []) is True and ga.calls == 2
    assert cube.head["qh"]["p"] == ["2026-09-03"] and cube.q_has("2026-09-01") and cube.q_has("2026-09-02")
    cube.head["qh"]["p"] = ["2026-09-02", "2026-09-03"]
    ga = FakeGA()
    cu.q_fwd(ga, cube, NOW, [])
    assert ga.calls == 1 and cube.head["qh"]["p"] == []


def _lossy_cube(monkeypatch, loss):
    """Jun 1 … Oct 10 folded (q off: nothing pending), hot days read; `loss` {YYYY-MM: share} put on each day's ledger
    of those months (measured "(other)" loss)."""
    monkeypatch.setattr(cu, "Q_CALLS", 0)
    cube = cu.Cube(None, "a~1", "222")
    cu.step_app(FakeGA(), cube, TODAY, HS, NOW)
    for k, sh in loss.items():
        for led in cube.month(k)["days"].values():
            led["loss"] = int(led["t"] * sh)
    monkeypatch.setattr(cu, "Q_CALLS", 120)
    return cube


def test_q_history_lossy_months_first_and_the_cap(monkeypatch):
    cube = _lossy_cube(monkeypatch, {"2026-07": 0.1, "2026-09": 0.3})
    assert cu.q_scan(cube, NOW) is True and cu.q_scan(cube, NOW) is False          # once (not again while queued)
    todo = cube.head["qh"]["todo"]
    assert [e[0] for e in todo] == ["2026-09", "2026-07", "2026-10", "2026-08", "2026-06"]  # loss (biggest share)
    assert [e[2] for e in todo] == [30, 31, 10, 31, 30] and cube.q_left() == 132           # first, then newest first
    assert todo[0][1] == pytest.approx(0.3, abs=1e-4) and todo[0][3] > 0 and todo[2][3] == 0
    left = [40]

    def take():
        left[0] -= 1
        return left[0] >= 0
    ga = FakeGA()
    assert cu.q_fill(ga, cube, NOW, take) == 40 and ga.calls == 40                         # the run's cap holds
    assert all(cube.q_has("2026-09-%02d" % d) for d in range(1, 31)) and cube.q_has("2026-07-10")
    assert not cube.q_has("2026-07-11") and not cube.q_has("2026-10-01")
    assert [e[0] for e in cube.head["qh"]["todo"]][0] == "2026-07" and cube.q_left() == 132 - 40
    for k in ("2026-09-15", "2026-07-03"):                                                 # each the fake's whole read
        assert cube.qmonth(k[:7])["days"][k]["qt"] == _qday_want(date.fromisoformat(k))[1]
    ga = FakeGA()                                                                          # the rest: the queue empties
    assert cu.q_fill(ga, cube, NOW, lambda: True) == 92 and cube.head["qh"]["todo"] == [] and cube.q_left() == 0
    # a Stop (the app's call cap) ends it quietly: what was read is kept
    cube2 = _lossy_cube(monkeypatch, {})
    cu.q_scan(cube2, NOW)
    assert cu.q_fill(FakeGA(max_calls=5), cube2, NOW, lambda: True) == 5 and cube2.q_days == 5


def test_q_round_lossy_apps_first_within_the_runs_calls(monkeypatch):
    import threading
    plain, lossy = _lossy_cube(monkeypatch, {}), _lossy_cube(monkeypatch, {"2026-08": 0.2})
    plain.app_id, lossy.app_id = "a~1", "z~9"                       # by id the plain app would go first
    monkeypatch.setattr(cu, "Q_CALLS", 50)
    fill = [("a~1", {}, plain, FakeGA()), ("z~9", {}, lossy, FakeGA())]
    counts = dict.fromkeys(cu.COUNTS, 0)
    cu.q_round(fill, NOW, lambda: None, threading.Lock(), counts, workers=1)
    assert lossy.q_days == 50 and plain.q_days == 0 and counts["calls"] == 50   # the lossy app first, 50 in all
    assert all(lossy.q_has("2026-08-%02d" % d) for d in range(1, 32))          # its lossy month first


def test_q_files_are_never_months_and_the_repair_leaves_them(tmp_path, monkeypatch):
    data, T0 = str(tmp_path), date(2026, 10, 13)
    cube = _old_cube(data, T0)
    monkeypatch.setattr(cu, "Q_CALLS", 120)
    cube.q_put("2026-09-05", cu.q_read(FakeGA(today=T0, start=RS), date(2026, 9, 5)), "t")
    _save(cube)
    qp = cu.q_path(data, "a~1", "2026-09")
    raw = open(qp, "rb").read()
    assert os.path.exists(qp) and [k for k, _ in cu.months(data, "a~1", "222")] == ["2026-09", "2026-10"]
    monkeypatch.setattr(cu, "Q_CALLS", 0)
    for i in range(40):                                             # the repair reads and replaces 2026-10, then 09
        c = cu.Cube(data, "a~1", "222")
        cu.repair(FakeGA(today=T0, cap=40, start=RS, max_calls=cu.MAX_CALLS), c, datetime(2026, 10, 13, 2, i,
                                                                                         tzinfo=timezone.utc))
        _save(c)
        if "rep" in _month(data, "2026-09"):
            break
    assert "rep" in _month(data, "2026-09") and open(qp, "rb").read() == raw
    assert cu.load_q(data, "a~1", "999", "2026-09") is None         # another stream's: never read


def test_q_in_the_run_two_rounds_counts_and_files(monkeypatch, tmp_path):
    """refresh_all with q on: each app's walk / hot days, their q in the same run, then the history fill (second
    round) within the run's Q_CALLS; q files next to the months, the per-app counts in the private state, the log line
    counts only."""
    monkeypatch.setattr(cu, "Q_CALLS", 20)
    data, out = _refresh(monkeypatch, tmp_path)
    c = out["counts"]
    # per app: 71 days folded (Aug 1 … Oct 10, all pending), hot 3 + Q_FWD 7 in its run; then 20 more in all
    assert out["apps"] == {"x~1": "fetched", "x~2": "fetched"}
    assert c["q_days"] == 2 * (3 + cu.Q_FWD) + 20 and c["q_flagged"] == 0 and c["q_calls"] == c["q_days"]
    assert c["q_left"] == 2 * 71 - 2 * cu.Q_FWD - 20
    st = cu.load_state(data)["fetch"]
    assert sum(st[a]["q"]["d"] for a in ("x~1", "x~2")) == c["q_days"]
    assert all(set(st[a]["q"]) == {"d", "c", "fl", "err", "left"} for a in ("x~1", "x~2"))
    names = sorted(os.listdir(cu.app_dir(data, "x~1")))
    assert "2026-08.q.json.gz" in names and [k for k, _ in cu.months(data, "x~1", "222")] == ["2026-08", "2026-09",
                                                                                                "2026-10"]
    h = cu.load_head(data, "x~1")
    assert all(h["d"][k]["qs"] == "ok" for k in h["d"]) and h["qh"]["p"][0] > "2026-08-07"
    line = cu.log_line(out)
    assert ", q days %d, q flagged 0, q calls %d, q left %d, q unscanned 0, q errors 0, calls " % (
        c["q_days"], c["q_calls"], c["q_left"]) in line
    assert "example" not in line and "x~" not in line


def test_q_days_of_nothing_are_never_read(monkeypatch):
    """A folded day with no revenue, no loss and no GA4 flag (before the app's first user): never pending, never queued,
    never read — its whole read would be empty too (the build takes such a day as whole). A flagged empty day is read."""
    monkeypatch.setattr(cu, "Q_CALLS", 0)
    cube = cu.Cube(None, "a~1", "222")
    cu.step_app(FakeGA(start=date(2026, 8, 1)), cube, TODAY, HS, NOW)      # June, July: no row at all
    assert cube.month("2026-07")["days"]["2026-07-15"]["t"] == 0 and not cu.q_need(cube.month("2026-07")["days"]["2026-07-15"])
    monkeypatch.setattr(cu, "Q_CALLS", 120)
    assert cu.q_scan(cube, NOW) is True
    assert [e[0] for e in cube.head["qh"]["todo"]] == ["2026-10", "2026-09", "2026-08"] and cube.q_left() == 71
    ga = FakeGA(start=date(2026, 8, 1))
    assert cu.q_fill(ga, cube, NOW, lambda: True) == ga.calls == 71
    assert cube.q_has("2026-08-01") and not cube.q_has("2026-07-31") and not cube.q_has("2026-06-01")
    c2 = cu.Cube(None, "a~1", "222")                                         # the fold: only a day that needs one
    empty = cu._rec(cu._new(), "block", 0, "t")
    c2.fold(date(2026, 7, 5), empty)
    c2.fold(date(2026, 7, 6), dict(empty, fl=1))
    c2.fold(date(2026, 7, 7), dict(empty, t=1))
    assert c2.head["qh"]["p"] == ["2026-07-06", "2026-07-07"]
    hot = {"2026-10-12": dict(empty), "2026-10-13": dict(empty, t=5)}       # a hot day of nothing: no q read either
    c2.head["d"], c2.head["qh"]["p"] = hot, []
    ga = FakeGA()
    assert cu.q_fwd(ga, c2, NOW, sorted(hot)) is True and ga.calls == 1
    assert "qs" not in hot["2026-10-12"] and hot["2026-10-13"]["qs"] == "ok"


def test_q_an_error_never_fails_the_app_and_is_counted(tmp_path, monkeypatch):
    """A q read failing with anything but a Stop (a GA4 5xx past its retry): q ends for that app this run (counted, the
    day it was on stays pending), never the app's run; the history fill the same (counted, nothing lost)."""
    data = str(tmp_path)
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(), cube, TODAY, HS, NOW)
    _save(cube)
    monkeypatch.setattr(cu, "Q_CALLS", 120)

    def boom(ga, D):
        raise RuntimeError("a GA4 error")
    monkeypatch.setattr(cu, "q_read", boom)
    nxt = TODAY + timedelta(days=1)
    cube = cu.Cube(data, "a~1", "222")
    assert cu.step_app(FakeGA(today=nxt), cube, nxt, HS, NOW + timedelta(days=1)) == "fetched"
    assert cube.q_err == 1 and cube.q_halt and cube.head["qh"]["p"] == ["2026-10-11"]
    assert all("qs" not in cube.head["d"][k] for k in ("2026-10-12", "2026-10-13", "2026-10-14"))
    assert cu.q_fill(FakeGA(), cube, NOW, lambda: True) == 0 and cube.q_err == 1     # ended for this run
    c2 = cu.Cube(None, "a~1", "222")
    c2.head["qh"] = {"p": ["2026-09-01", "2026-09-02"]}
    assert cu.q_fill(FakeGA(), c2, NOW, lambda: True) == 0 and c2.q_err == 1 and c2.head["qh"]["p"] == ["2026-09-01",
                                                                                                         "2026-09-02"]


def test_q_errors_in_the_run_counted_never_a_failed_app(monkeypatch, tmp_path):
    monkeypatch.setattr(cu, "Q_CALLS", 20)

    def boom(ga, D):
        raise RuntimeError("a GA4 error")
    monkeypatch.setattr(cu, "q_read", boom)
    data, out = _refresh(monkeypatch, tmp_path)
    c = out["counts"]
    assert out["apps"] == {"x~1": "fetched", "x~2": "fetched"}
    assert c["failed"] == 0 and c["q_errors"] == 2 and c["q_days"] == 0
    st = cu.load_state(data)["fetch"]
    assert all(st[a]["q"]["err"] == 1 and not st[a].get("fail") for a in ("x~1", "x~2"))
    assert ", q errors 2, calls " in cu.log_line(out)


def test_q_round_ends_at_its_seconds(monkeypatch, tmp_path):
    """The history fill gets at most Q_SEC seconds a run (from the end of every app's walk and hot days): a run never
    much longer for it, whatever Q_CALLS allows."""
    monkeypatch.setattr(cu, "Q_CALLS", 500)
    monkeypatch.setattr(cu, "Q_SEC", 10.0)
    data, out = _refresh(monkeypatch, tmp_path, tick=0.5, workers=1)        # every GA4 call half a second
    c = out["counts"]
    assert c["q_days"] == 2 * (3 + cu.Q_FWD) + 20                            # the fill: 10 s ÷ 0.5 s
    assert c["q_left"] == 2 * 71 - 2 * cu.Q_FWD - 20 and c["q_unscanned"] == 0


def test_q_an_app_not_scanned_is_counted_apart(monkeypatch, tmp_path):
    """No time left for the second round: no app's queue made — "q unscanned" says so, "q left" never counts them as 0
    days left (the private state: left None)."""
    monkeypatch.setattr(cu, "Q_CALLS", 20)
    monkeypatch.setattr(cu, "Q_SEC", 0.0)
    data, out = _refresh(monkeypatch, tmp_path)
    c = out["counts"]
    assert c["q_unscanned"] == 2 and c["q_left"] == 0 and c["q_days"] == 2 * (3 + cu.Q_FWD)
    st = cu.load_state(data)["fetch"]
    assert all(st[a]["q"]["left"] is None for a in ("x~1", "x~2"))
    assert ", q left 0, q unscanned 2, q errors 0, " in cu.log_line(out)
