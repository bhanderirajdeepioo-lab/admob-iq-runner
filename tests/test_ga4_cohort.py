"""📈 Day-wise ROI — the hourly fetch (admob_iq.fetch.ga4_cohort), offline with a fake GA4 and made-up numbers: the block
query (dimensions, in-list of install days), the cells kept (lag 0 … 30 only; a cell GA4 leaves out = 0), the one-time
backfill from the history start (resumed after a stop), the recent refresh every 6 hours (today included), the hot /
older split of the store, a block with "(other)" rows read again day by day (split by install-day halves; the day's
cap leaves measured loss in "lo"; a flagged block's days in "lf"; a refresh cut by a Stop goes on from its next day),
and counts-only lines."""
import gzip
import json
import os
from datetime import date, datetime, timedelta, timezone

from admob_iq.fetch import ga4_cohort as gc

NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 13)


class FakeGA:
    """Every (activity day D, install day X) with 0 ≤ D − X ≤ 40 has users 100 − lag and revenue (lag + 1) cents;
    nothing before HS. stop_after: raise Stop at that call."""
    HS = date(2026, 6, 1)

    def __init__(self, stop_after=None):
        self.calls, self.asked, self.stop_after, self.tok = 0, [], stop_after, 0

    def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise gc.Stop("calls")
        self.calls += 1
        self.asked.append((body, extra))
        a, b = (date.fromisoformat(body["dateRanges"][0][k]) for k in ("startDate", "endDate"))
        allowed = set(extra[0]["filter"]["inListFilter"]["values"])
        rows, D = [], a
        while D <= b:
            for lag in range(0, 41):
                X = D - timedelta(days=lag)
                if X < self.HS or X.strftime("%Y%m%d") not in allowed:
                    continue
                if lag == 5:                                            # GA4 leaves out a row nobody had
                    continue
                rows.append({"date": D.strftime("%Y%m%d"), "firstSessionDate": X.strftime("%Y%m%d"),
                             "activeUsers": 100 - lag, "totalAdRevenue": (lag + 1) / 100})
            D += timedelta(days=1)
        return rows


def test_block_query_and_cells():
    ga = FakeGA()
    got = gc.read_block(ga, date(2026, 9, 1), date(2026, 9, 30))
    body, extra = ga.asked[0]
    assert [d["name"] for d in body["dimensions"]] == ["date", "firstSessionDate"] and body["currencyCode"] == "USD"
    vals = extra[0]["filter"]["inListFilter"]["values"]
    assert len(vals) == 60 and min(vals) == "20260802" and max(vals) == "20260930"    # install days a − 30 … b
    assert got["2026-09-01"][0] == [100, 10000] and got["2026-09-01"][29] == [71, 300000]
    assert all(L <= 30 for X in got for L in got[X])
    store = {}
    gc.merge(store, got, date(2026, 9, 1), date(2026, 9, 30))
    c = store["x"]["2026-09-01"]
    assert c["r"][:3] == [10000, 20000, 30000] and c["r"][5] == 0 and c["u"][5] == 0      # left out = 0
    assert c["r"][29] == 300000 and c["r"][30] == 0                                       # day 30 is Oct 1: not read yet
    assert store["x"]["2026-08-02"]["r"][30] == 310000 and store["x"]["2026-08-02"]["r"][29] == 0


def test_backfill_from_history_start_then_recent(tmp_path):
    ga, store = FakeGA(), {"v": gc.STORE_V}
    assert gc.step_app(ga, store, TODAY, FakeGA.HS, NOW) == "fetched"
    assert store["backfill"] == {"from": "2026-06-01", "next": "2026-09-09", "done": True}
    recent = TODAY - timedelta(days=gc.RECENT_DAYS - 1)
    assert recent.isoformat() == "2026-09-09"
    assert ga.calls == 4 + 1                                   # Jun 1 … Sep 8 in 4 blocks of ≤ 30 days + the recent read
    x = store["x"]
    assert min(x) == "2026-06-01" and max(x) == "2026-10-13" and x["2026-10-13"]["r"][0] == 10000
    assert x["2026-06-01"]["r"][30] == 310000                  # Jul 1: inside the backfill
    ga2 = FakeGA()
    assert gc.step_app(ga2, store, TODAY, FakeGA.HS, NOW + timedelta(hours=2)) == "fresh" and ga2.calls == 0
    assert gc.step_app(ga2, store, TODAY, FakeGA.HS, NOW + timedelta(hours=7)) == "fetched" and ga2.calls == 1
    # the store: hot part from the month of today − 45 days, the rest in the older file
    gc.save_store(str(tmp_path), "a~1", store, TODAY)
    with gzip.open(gc.store_path(str(tmp_path), "a~1"), "rt") as f:
        hot = json.load(f)
    with gzip.open(gc.store_path(str(tmp_path), "a~1", old=True), "rt") as f:
        old = json.load(f)
    assert hot["cut"] == "2026-08-01" and min(hot["x"]) == "2026-08-01" and max(old["x"]) == "2026-07-31"
    back = gc.load_store(str(tmp_path), "a~1")
    assert back["x"] == store["x"] and "cut" not in back


def test_backfill_resumes_after_a_stop():
    ga, store = FakeGA(stop_after=2), {"v": gc.STORE_V}
    try:
        gc.step_app(ga, store, TODAY, FakeGA.HS, NOW)
        raise AssertionError("no stop")
    except gc.Stop:
        pass
    assert store["backfill"]["next"] == "2026-07-31" and not store["backfill"].get("done")
    ga2 = FakeGA()
    assert gc.step_app(ga2, store, TODAY, FakeGA.HS, NOW) == "fetched" and store["backfill"]["done"]
    assert ga2.asked[0][0]["dateRanges"][0]["startDate"] == "2026-07-31"


def test_refresh_all_counts_only(monkeypatch, tmp_path):
    data = str(tmp_path)
    route = {"property_id": "111", "stream_id": "222", "owner": "o"}
    monkeypatch.setattr(gc.gu, "load_state", lambda d: {"routes": {"by_package": {"com.example.alpha": route}},
                                                        "tz": {"111": "Asia/Kolkata"}, "fetch": {}})
    monkeypatch.setattr(gc.gaud, "_uni_meta", lambda ust, d, aid, r: {"history_start": "2026-09-20"})
    monkeypatch.setattr(gc.ga4, "access_token", lambda c, s, r: "tok")

    class A(FakeGA):
        def __init__(self, token, pid, sid, prop, over=None, max_calls=gc.MAX_CALLS):
            super().__init__()
    monkeypatch.setattr(gc, "App", A)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    out = gc.refresh_all(cfg, data, [{"app_id": "x~1", "package": "com.example.alpha"},
                                     {"app_id": "x~2", "package": "com.example.none"}], NOW)
    assert out["apps"] == {"x~1": "fetched"} and out["counts"]["with_ga4"] == 1
    st = gc.load_store(data, "x~1")
    assert st["hs"] == "2026-09-20" and st["stream_id"] == "222" and min(st["x"]) >= "2026-08-21"
    line = gc.log_line(out)
    assert line.startswith("ga4 cohort: apps 2, with GA4 1, fetched 1") and "example" not in line


# ── "(other)" in a block: the block read again day by day, split like the cube (owner, 21 Oct 2026) ────────────────
def _cga(**kw):
    """The cube's fake (countries, GA4's row limit `cap`, filters on any field), grouped by the dimensions asked for —
    here date × firstSessionDate."""
    from tests.test_ga4_cube import FakeGA as CubeGA
    return CubeGA(**dict({"today": date(2027, 1, 1), "start": date(2026, 6, 1)}, **kw))


def _truth(a, b):
    store = {}
    gc.merge(store, gc.read_block(_cga(), a, b), a, b)
    return store["x"]


def _run(ga, store, a, b, alone=False):
    info = dict.fromkeys(gc.INFO, 0)
    last = None
    for D in gc._read(ga, store, a, b, info, alone):
        last = D
    return info, last


def test_a_block_with_other_rows_is_read_day_by_day():
    a, b = date(2026, 9, 1), date(2026, 9, 30)
    truth = _truth(a, b)
    bi, ga = {}, _cga(cap=1000)                     # the block: 30 days × up to 60 install days → over the limit
    gc.read_block(ga, a, b, bi)
    assert bi["oth"] == 30 and bi["om"] > 0 and bi["fl"] & gc.gcu.F_OTHER        # counted: one "(other)" row a day
    store, ga = {}, _cga(cap=1000)
    info, last = _run(ga, store, a, b)
    assert ga.calls == 1 + 30 and last == b and info == {"oth_blocks": 1, "alone": 30, "loss_days": 0, "flagged": 0}
    for _, ex, _, _ in ga.asked[1:]:                # each day alone: install days D − 30 … D (31)
        assert len(ex[0]["filter"]["inListFilter"]["values"]) == gc.LAGS
    assert store["x"] == truth and "lo" not in store and "lf" not in store
    # a day still over the limit: split by install-day halves (no country here) — every cell back
    store, ga = {}, _cga(cap=20)
    info, _ = _run(ga, store, a, b)
    assert store["x"] == truth and info["alone"] == 30 and info["loss_days"] == 0 and ga.calls == 1 + 30 * 3
    # the day's cap reached: what is still "(other)" is that day's measured loss ("lo"), never spread
    old = gc.DAY_CAP
    try:
        gc.DAY_CAP = 1
        store, ga = {}, _cga(cap=20)
        info, _ = _run(ga, store, a, b)
    finally:
        gc.DAY_CAP = old
    assert info["loss_days"] == 30 and sorted(store["lo"]) == [D.isoformat() for D in gc._days(a, b)]
    for D in gc._days(a, b):                        # kept + loss = the day's own total (install days D − 30 … D)
        k = D.isoformat()
        tot = sum(truth[X]["r"][L] for X in truth for L in range(gc.LAGS)
                  if (date.fromisoformat(X) + timedelta(days=L)).isoformat() == k)
        got = sum(store["x"][X]["r"][L] for X in store["x"] for L in range(gc.LAGS)
                  if (date.fromisoformat(X) + timedelta(days=L)).isoformat() == k)
        assert abs(got + store["lo"][k] - tot) <= 2 and got < tot
    # read again whole: the day's loss goes
    info, _ = _run(_cga(), store, a, b)
    assert "lo" not in store and store["x"] == truth


def test_a_flagged_block_marks_its_days_and_a_clean_read_clears_them():
    a, b = date(2026, 9, 1), date(2026, 9, 30)
    store = {}
    info, _ = _run(_cga(oth_flag_day=date(2026, 9, 5)), store, a, b)      # the flag with no "(other)" row to measure
    assert info["oth_blocks"] == 0 and info["flagged"] == 30 and len(store["lf"]) == 30 and store["x"] == _truth(a, b)
    _run(_cga(), store, a, b)
    assert "lf" not in store


def test_a_refresh_read_day_by_day_goes_on_after_a_stop():
    store = {"v": gc.STORE_V, "backfill": {"done": True}}
    hs = date(2026, 6, 1)
    try:
        gc.step_app(_cga(today=TODAY, cap=1000, stop_after=11), store, TODAY, hs, NOW)
        raise AssertionError("no stop")
    except gc.Stop:
        pass
    recent = TODAY - timedelta(days=gc.RECENT_DAYS - 1)
    assert store["rn"] == (recent + timedelta(days=10)).isoformat() and "recent_at" not in store   # 10 days kept
    ga = _cga(today=TODAY, cap=1000)
    info = {}
    assert gc.step_app(ga, store, TODAY, hs, NOW + timedelta(hours=1), info) == "fetched"
    k = (recent + timedelta(days=10)).isoformat()                         # no block call first: on from that day
    assert ga.asked[0][0]["dateRanges"][0] == {"startDate": k, "endDate": k}
    assert ga.calls == gc.RECENT_DAYS - 10 and info["oth_blocks"] == 0 and info["alone"] == gc.RECENT_DAYS - 10
    assert "rn" not in store and store["recent_at"] and store["read_today"] == TODAY.isoformat()
    want = {}
    gc.merge(want, gc.read_block(_cga(today=TODAY), recent, TODAY), recent, TODAY)
    assert {X: v for X, v in store["x"].items() if X >= "2026-08-10"} == \
        {X: v for X, v in want["x"].items() if X >= "2026-08-10"}


def test_the_line_counts_only():
    out = {"counts": dict(dict.fromkeys(gc.COUNTS, 0), selected=2, oth_blocks=1, alone=30, loss_days=2, flagged=3)}
    assert gc.log_line(out) == ("ga4 cohort: apps 2, with GA4 0, fetched 0, fresh 0, failed 0, deferred 0, waiting 0, "
                                "blocks with (other) 1, days read alone 30, days with loss 2, flagged days 3, calls 0, "
                                "tokens 0")
