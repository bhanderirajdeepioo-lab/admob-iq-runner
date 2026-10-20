"""📈 Day-wise ROI — the hourly fetch (admob_iq.fetch.ga4_cohort), offline with a fake GA4 and made-up numbers: the block
query (dimensions, in-list of install days), the cells kept (lag 0 … 30 only; a cell GA4 leaves out = 0), the one-time
backfill from the history start (resumed after a stop), the recent refresh every 6 hours (today included), the hot /
older split of the store, and a counts-only line. The LATE read (GA4_COHORT_LATE): no in-list, only lag ≥ 31 folded,
"(other)" / "(not set)" summed per day, files by activity month (a re-read replaces its days; only touched months
written), its backfill / recent refresh after the lag 0 … 30 reads, and off = nothing read, written or printed."""
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


# ── the LATE read: every install day's revenue past day 30 (GA4_COHORT_LATE) ───────────────────────────────────────
class FakeLate(FakeGA):
    """The late block (no in-list): every (D, X) with X ≥ HS − 10 (a few install days before the history start) and
    0 ≤ D − X ≤ 400 earns (lag + 1) cents; GA4 adds an "(other)" row of 7 cents and a "(not set)" row of 3 cents a day,
    and leaves out a row nobody earned on (lag 45)."""

    def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise gc.Stop("calls")
        self.calls += 1
        self.asked.append((body, extra, page_rows))
        a, b = (date.fromisoformat(body["dateRanges"][0][k]) for k in ("startDate", "endDate"))
        rows, D = [], a
        while D <= b:
            for lag in range(0, 401):
                X = D - timedelta(days=lag)
                if X < self.HS - timedelta(days=10) or lag == 45:
                    continue
                rows.append({"date": D.strftime("%Y%m%d"), "firstSessionDate": X.strftime("%Y%m%d"),
                             "totalAdRevenue": (lag + 1) / 100})
            rows.append({"date": D.strftime("%Y%m%d"), "firstSessionDate": "(other)", "totalAdRevenue": 0.07})
            rows.append({"date": D.strftime("%Y%m%d"), "firstSessionDate": "(not set)", "totalAdRevenue": 0.03})
            D += timedelta(days=1)
        return rows


def test_late_body_and_fold():
    ga, hs = FakeLate(), FakeGA.HS
    got = gc.read_late(ga, date(2026, 9, 1), date(2026, 9, 30), hs)
    body, extra, page_rows = ga.asked[0]
    assert [d["name"] for d in body["dimensions"]] == ["date", "firstSessionDate"] and body["currencyCode"] == "USD"
    assert [m["name"] for m in body["metrics"]] == ["totalAdRevenue"] and body["dateRanges"] == [
        {"startDate": "2026-09-01", "endDate": "2026-09-30"}]
    assert not extra and page_rows == gc.gu.UNI_PAGE_ROWS                    # no in-list: every install day; every page
    day = got["d"]["2026-09-01"]                                            # Sep 1: lags 31 … 92 back to Jun 1
    assert min(day) == "2026-06-01" and max(day) == "2026-08-01"            # X ≥ the history start; lag ≥ 31 only
    assert day["2026-08-01"] == 320000 and "2026-07-18" not in day          # lag 31 = 32 cents; lag 45 left out
    assert all((date(2026, 9, 1) - date.fromisoformat(X)).days >= gc.LAGS for X in day)
    assert got["oth"]["2026-09-01"] == 100000                               # "(other)" + "(not set)" summed
    lags = [L for L in range(0, 93) if L != 45] + list(range(93, 103))       # every row of the day (X ≥ HS − 10)
    assert got["t"]["2026-09-01"] == sum((L + 1) * 10000 for L in lags) + 100000
    assert gc.read_late(ga, date(2026, 6, 20), date(2026, 6, 20), hs)["d"] == {}   # nothing 31 days past HS yet


def test_late_store_by_month_replace_and_stream(tmp_path):
    data, hs = str(tmp_path), FakeGA.HS
    lt = gc.Late(data, "a~1", "222")
    lt.put(gc.read_late(FakeLate(), date(2026, 8, 25), date(2026, 9, 5), hs), date(2026, 8, 25), date(2026, 9, 5))
    assert lt.calls == 1 and lt.days == 12
    assert lt.touched == {"2026-09"} and list(lt.m) == ["2026-09"]           # August done: written and let go already
    assert os.path.exists(gc.late_path(data, "a~1", "2026-08"))
    lt.save()
    with gzip.open(gc.late_path(data, "a~1", "2026-08"), "rt") as f:
        aug = json.load(f)
    assert aug["v"] == 1 and aug["stream_id"] == "222" and sorted(aug["d"]) == ["2026-08-%02d" % i for i in range(25, 32)]
    assert aug["oth"]["2026-08-25"] == 100000 and aug["d"]["2026-08-25"]["2026-06-01"] == (85 + 1) * 10000
    # a re-read REPLACES its days (never adds): one day with less revenue, one with nothing at all
    lt2 = gc.Late(data, "a~1", "222")
    lt2.put({"d": {"2026-09-02": {"2026-06-01": 5}}, "oth": {}, "t": {"2026-09-02": 5}}, date(2026, 9, 2), date(2026, 9, 3))
    assert lt2.touched == {"2026-09"}                                       # only the month it touched is written
    p_aug = gc.late_path(data, "a~1", "2026-08")
    before = os.stat(p_aug).st_mtime_ns
    lt2.save()
    assert os.stat(p_aug).st_mtime_ns == before
    months = dict(gc.late_months(data, "a~1", "222"))
    sep = months["2026-09"]
    assert sep["d"]["2026-09-02"] == {"2026-06-01": 5} and sep["d"]["2026-09-03"] == {}   # read: nothing to fold
    assert "2026-09-02" not in sep["oth"] and "2026-09-03" not in sep["t"] and sep["oth"]["2026-09-01"] == 100000
    assert sorted(sep["d"]) == ["2026-09-%02d" % i for i in range(1, 6)]   # the days around kept as they were
    assert list(gc.late_months(data, "a~1", "999")) == []                   # another stream's months: not this app's
    lt3 = gc.Late(data, "a~1", "999")                                       # … and replaced when that stream reads
    lt3.put({"d": {}, "oth": {}, "t": {}}, date(2026, 9, 1), date(2026, 9, 1))
    assert lt3.month("2026-09")["stream_id"] == "999" and list(lt3.month("2026-09")["d"]) == ["2026-09-01"]


def test_late_backfill_then_recent_with_the_refresh():
    ga, store, lt = FakeLate(), {"v": gc.STORE_V}, gc.Late()
    assert gc.step_app(ga, store, TODAY, FakeGA.HS, NOW, lt) == "fetched"
    # the lag 0 … 30 reads first, exactly as without the late part (4 backfill blocks + the recent read) …
    main = [q for q in ga.asked if q[1]]
    assert len(main) == 5 and ga.asked[:5] == main
    late = [q[0]["dateRanges"][0] for q in ga.asked[5:]]
    # … then the late backfill from history start + 31 (Jul 2) to today − 35 (Sep 8) in blocks of 30, and the recent
    # 35 days again (2 calls)
    assert late == [{"startDate": "2026-07-02", "endDate": "2026-07-31"}, {"startDate": "2026-08-01", "endDate": "2026-08-30"},
                    {"startDate": "2026-08-31", "endDate": "2026-09-08"}, {"startDate": "2026-09-09", "endDate": "2026-10-08"},
                    {"startDate": "2026-10-09", "endDate": "2026-10-13"}]
    assert store["late"] == {"from": "2026-07-02", "next": "2026-09-09", "done": True, "read_till": "2026-10-13"}
    assert lt.touched == {"2026-07", "2026-08", "2026-09", "2026-10"} and lt.calls == 5
    # next run inside 6 hours: nothing; after 6 hours: the main recent read + the late recent (2 calls)
    ga2 = FakeLate()
    assert gc.step_app(ga2, store, TODAY, FakeGA.HS, NOW + timedelta(hours=2), gc.Late()) == "fresh" and ga2.calls == 0
    assert gc.step_app(ga2, store, TODAY, FakeGA.HS, NOW + timedelta(hours=7), gc.Late()) == "fetched" and ga2.calls == 3
    # a run whose late part stopped after the main recent read: the late recent is retried on the next run
    ga3, nxt = FakeLate(stop_after=2), TODAY + timedelta(days=1)
    try:
        gc.step_app(ga3, store, nxt, FakeGA.HS, NOW + timedelta(days=1), gc.Late())
        raise AssertionError("no stop")
    except gc.Stop:
        pass
    assert store["read_today"] == nxt.isoformat() and store["late"]["read_till"] == TODAY.isoformat()
    ga4_ = FakeLate()
    assert gc.step_app(ga4_, store, nxt, FakeGA.HS, NOW + timedelta(days=1, hours=1), gc.Late()) == "fetched"
    assert ga4_.calls == 2 and not any(q[1] for q in ga4_.asked) and store["late"]["read_till"] == nxt.isoformat()


def test_late_backfill_resumes_and_a_young_app_reads_nothing():
    store = {"v": gc.STORE_V, "backfill": {"done": True}, "recent_at": gc.gu._now_iso(NOW), "read_today": TODAY.isoformat()}
    ga = FakeLate(stop_after=1)
    try:
        gc.step_app(ga, store, TODAY, FakeGA.HS, NOW, gc.Late())
        raise AssertionError("no stop")
    except gc.Stop:
        pass
    assert store["late"]["next"] == "2026-08-01" and not store["late"].get("done")
    ga2 = FakeLate()
    assert gc.step_app(ga2, store, TODAY, FakeGA.HS, NOW, gc.Late()) == "fetched"
    assert ga2.asked[0][0]["dateRanges"][0]["startDate"] == "2026-08-01" and store["late"]["done"]
    young = {"v": gc.STORE_V, "backfill": {"done": True}, "recent_at": gc.gu._now_iso(NOW), "read_today": TODAY.isoformat()}
    ga3 = FakeLate()                                        # history start 20 days ago: no lag ≥ 31 row can exist yet
    assert gc.step_app(ga3, young, TODAY, TODAY - timedelta(days=20), NOW, gc.Late()) == "fresh" and ga3.calls == 0
    # the late switch off (late=None): the store gets no late key, nothing else read
    plain, ga4_ = {"v": gc.STORE_V}, FakeLate()
    gc.step_app(ga4_, plain, TODAY, FakeGA.HS, NOW)
    assert "late" not in plain and ga4_.calls == 5


def _refresh(monkeypatch, tmp_path, late):
    data = str(tmp_path)
    route = {"property_id": "111", "stream_id": "222", "owner": "o"}
    monkeypatch.setattr(gc.gu, "load_state", lambda d: {"routes": {"by_package": {"com.example.alpha": route}},
                                                        "tz": {"111": "Asia/Kolkata"}, "fetch": {}})
    monkeypatch.setattr(gc.gaud, "_uni_meta", lambda ust, d, aid, r: {"history_start": "2026-07-01"})
    monkeypatch.setattr(gc.ga4, "access_token", lambda c, s, r: "tok")

    class A(FakeLate):
        def __init__(self, token, pid, sid, prop, over=None, max_calls=gc.MAX_CALLS):
            super().__init__()

        def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
            return (FakeGA.report_all if extra else FakeLate.report_all)(self, body, event, events, extra, page_rows)
    monkeypatch.setattr(gc, "App", A)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    return data, gc.refresh_all(cfg, data, [{"app_id": "x~1", "package": "com.example.alpha"}], NOW, late=late)


def test_refresh_all_late_switch(monkeypatch, tmp_path):
    data, out = _refresh(monkeypatch, tmp_path / "on", True)
    # history start Jul 1: the late backfill Aug 1 … Sep 8 (2 calls) + the recent 35 days (2 calls)
    assert out["apps"] == {"x~1": "fetched"} and out["late"]["apps"] == 1 and out["late"]["calls"] == 4
    st = gc.load_store(data, "x~1")
    assert st["late"]["done"] and st["late"]["read_till"] == "2026-10-13"
    months = dict(gc.late_months(data, "x~1", "222"))
    assert sorted(months) == ["2026-08", "2026-09", "2026-10"] and min(months["2026-08"]["d"]) == "2026-08-01"
    line = gc.log_line(out)
    assert line.endswith("; late: apps 1, calls 4, days %d" % out["late"]["days"]) and "example" not in line
    # off: nothing of it read, written or printed — the main store and its line exactly as before
    data2, out2 = _refresh(monkeypatch, tmp_path / "off", False)
    assert "late" not in out2 and "late" not in gc.load_store(data2, "x~1")
    assert not os.path.exists(os.path.join(data2, gc.DIR, gc.LATE_DIR)) and "late" not in gc.log_line(out2)
    assert gc.log_line(out2) == line.split("; late:")[0].replace(", calls 8,", ", calls 4,")   # the run's calls: both
