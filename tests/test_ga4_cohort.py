"""📈 Day-wise ROI — the hourly fetch (admob_iq.fetch.ga4_cohort), offline with a fake GA4 and made-up numbers: the block
query (dimensions, in-list of install days), the cells kept (lag 0 … 30 only; a cell GA4 leaves out = 0), the one-time
backfill from the history start (resumed after a stop), the recent refresh every 6 hours (today included), the hot /
older split of the store, a block with "(other)" rows — or only GA4's flag (the in-list drops the row) — read again
day by day (split by install-day halves; a day still flagged read with every install day, its cells taken from that
whole answer; the day's cap leaves measured loss in "lo"; a thresholded block's days in "lf"; a refresh cut by a Stop
goes on from its next day; a heavy refresh reads only its days not yet read alone when final), the one-time check of
the history an older version read, no day left unread between the backfill, the check and the refresh (the floor
"rf"; another version's refresh read again), a resumed backfill never calling a dropped block again, the older days'
marks in the older file, a whole-day answer that is not whole measuring nothing, the check's time room, and
counts-only lines."""
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
    assert ga.calls == 1 + 30 and last == b and info == {"oth_blocks": 1, "alone": 30, "loss_days": 0, "flagged": 0,
                                                         "hidden": 0, "checked": 0}
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


def test_a_flagged_block_is_read_day_by_day_and_thresholding_marks_its_days():
    """dataLossFromOtherRow on a block (the in-list hides the "(other)" row: oth 0): its days are read alone — the
    flagged day split and measured by its every install day (nothing missing here: no loss, no flag); thresholding (no
    smaller read avoids it): the block kept, its days in "lf", a clean read clears them."""
    a, b = date(2026, 9, 1), date(2026, 9, 30)
    store, ga = {}, _cga(oth_flag_day=date(2026, 9, 5))
    info, _ = _run(ga, store, a, b)
    assert info["oth_blocks"] == 1 and info["alone"] == 30 and info["flagged"] == 0 and info["loss_days"] == 0
    assert ga.calls == 1 + 29 + 4 and "lf" not in store and "lo" not in store and store["x"] == _truth(a, b)
    store = {}
    info, _ = _run(_cga(thr_day=date(2026, 9, 5)), store, a, b)
    assert info["oth_blocks"] == 0 and info["flagged"] == 30 and len(store["lf"]) == 30 and store["x"] == _truth(a, b)
    _run(_cga(), store, a, b)
    assert "lf" not in store


def test_a_refresh_read_day_by_day_goes_on_after_a_stop():
    store = {"v": gc.STORE_V, "backfill": {"done": True}, "chk": {"v": gc.CHK_V, "done": True}}
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
    out = {"counts": dict(dict.fromkeys(gc.COUNTS, 0), selected=2, oth_blocks=1, alone=30, loss_days=2, flagged=3,
                          hidden=4, checked=60)}
    assert gc.log_line(out) == ("ga4 cohort: apps 2, with GA4 0, fetched 0, fresh 0, failed 0, deferred 0, waiting 0, "
                                "blocks with (other) 1, days read alone 30, days with loss 2, flagged days 3, days with "
                                "hidden (other) 4, days checked again 60, calls 0, tokens 0")


# ── GA4's "(other)" hidden by the in-list, the refresh's memory, the history an older version read ─────────────────
def _hga(**kw):
    """The cube's fake, and on an answer with a firstSessionDate in-list the 5 oldest install days of the list are
    gone (GA4 rolled them into "(other)" and the in-list dropped that row: dataLossFromOtherRow only) — the same day
    with no in-list is whole (smp_whole: that answer is sampled; oth_whole: it has an "(other)" row — the row alone,
    no flag; flag_whole: the 5 oldest install days of D − 30 … D gone from it too, flagged dataLossFromOtherRow with
    no row)."""
    from tests.test_ga4_cube import FakeGA as CubeGA
    smp, oth, flag = (kw.pop(k, False) for k in ("smp_whole", "oth_whole", "flag_whole"))

    class H(CubeGA):
        def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
            rows = super().report_all(body, event, events, extra, page_rows)
            xs = [ex["filter"]["inListFilter"]["values"] for ex in extra or []
                  if "filter" in ex and ex["filter"]["fieldName"] == "firstSessionDate"]
            if xs:
                drop = set(sorted(xs[0])[:5])
                kept = [r for r in rows if r.get("firstSessionDate") not in drop]
                if len(kept) < len(rows):
                    self.last_metas = [{"dataLossFromOtherRow": True}]
                rows = kept
            elif smp:
                self.last_metas = [{"samplingMetadatas": [{"samplesReadCount": "1", "samplingSpaceSize": "2"}]}]
            elif oth:
                rows = rows + [{"date": body["dateRanges"][0]["startDate"].replace("-", ""),
                                "firstSessionDate": "(other)", "activeUsers": 1, "totalAdRevenue": 0.5}]
            elif flag:
                D = date.fromisoformat(body["dateRanges"][0]["startDate"])
                drop = {(D - timedelta(days=gc.LAGS - 1 - i)).strftime("%Y%m%d") for i in range(5)}
                rows = [r for r in rows if r.get("firstSessionDate") not in drop]
                self.last_metas = [{"dataLossFromOtherRow": True}]
            return rows
    return H(**dict({"today": date(2027, 1, 1), "start": date(2026, 6, 1)}, **kw))


def test_other_hidden_by_the_in_list_is_read_from_the_whole_day():
    """A block whose in-list hid "(other)" (no row, only the flag): its days alone; a day still flagged is split (the
    halves name nothing more: no more), then read with every install day (no in-list: whole) — its cells of D − 30 …
    D taken from that answer: nothing lost, nothing flagged. When that answer is sampled: nothing to measure by — the
    day in "lf" (≈ on the page), never silently low."""
    a, b = date(2026, 9, 1), date(2026, 9, 30)
    truth = _truth(a, b)
    store, ga = {}, _hga()
    info, _ = _run(ga, store, a, b)
    assert info == {"oth_blocks": 1, "alone": 30, "loss_days": 0, "flagged": 0, "hidden": 30, "checked": 0}
    assert ga.calls == 1 + 30 * 4 and store["x"] == truth and "lo" not in store and "lf" not in store
    assert all(not ex for _, ex, _, _ in ga.asked[4::4])           # each day's 4th call: no in-list (the whole day)
    store, ga = {}, _hga(smp_whole=True)
    info, _ = _run(ga, store, a, b)
    assert info["flagged"] == 30 and len(store["lf"]) == 30 and "lo" not in store
    got = sum(v for e in store["x"].values() for v in e["r"])
    assert 0 < got < sum(v for e in truth.values() for v in e["r"])


def test_a_heavy_refresh_reads_only_its_newest_days_again():
    """A refresh whose block came back with "(other)": its days alone, the final ones noted ("fa") — the next refreshes
    read only the days after them (no final day twice), day by day straight away for RH_DAYS ("rh"), then the block is
    tried again (whole: blocks again)."""
    hs = date(2026, 6, 1)
    store = {"v": gc.STORE_V, "backfill": {"done": True}, "chk": {"v": gc.CHK_V, "done": True}}
    ga, info = _cga(today=TODAY, cap=1000), {}
    gc.step_app(ga, store, TODAY, hs, NOW, info)
    fin = TODAY - timedelta(days=gc.FINAL_LAG)
    recent = TODAY - timedelta(days=gc.RECENT_DAYS - 1)
    assert ga.calls == 1 + gc.RECENT_DAYS and info["oth_blocks"] == 1 and store["rh"] == TODAY.isoformat()
    assert sorted(store["fa"]) == [D.isoformat() for D in gc._days(recent, fin)]
    ga = _cga(today=TODAY, cap=1000)                              # 6 hours on: the 3 days not final, alone
    gc.step_app(ga, store, TODAY, hs, NOW + timedelta(hours=7))
    assert [q[0]["dateRanges"][0]["startDate"] for q in ga.asked] == ["2026-10-11", "2026-10-12", "2026-10-13"]
    nxt = TODAY + timedelta(days=1)                                # a new day: Oct 11 final now (read while not)
    ga = _cga(today=nxt, cap=1000)
    gc.step_app(ga, store, nxt, hs, NOW + timedelta(days=1))
    assert ga.calls == 4 and ga.asked[0][0]["dateRanges"][0]["startDate"] == "2026-10-11"
    assert "2026-10-11" in store["fa"] and min(store["fa"]) == (nxt - timedelta(days=gc.RECENT_DAYS - 1)).isoformat()
    later = TODAY + timedelta(days=gc.RH_DAYS + 1)                 # RH_DAYS on: the block again — whole now
    ga = _cga(today=later, cap=1000)
    gc.step_app(ga, store, later, hs, NOW + timedelta(days=gc.RH_DAYS + 1))
    assert ga.calls == 1 and ga.asked[0][0]["dateRanges"][0] == {"startDate": "2026-10-12",
                                                                 "endDate": later.isoformat()}
    assert "rh" not in store


def test_history_an_older_version_read_is_checked_again():
    """A store whose backfill an older version made (blocks only: what the in-list hid is missing, nothing says so):
    read again once (CHK_V) — block by block, a block with "(other)" day by day — at most CHK_CALLS calls started a
    run, after the refresh; a Stop goes on from the day it cut (no block call first); then done for good."""
    hs = date(2026, 6, 1)
    recent = TODAY - timedelta(days=gc.RECENT_DAYS - 1)
    store = {"v": gc.STORE_V}
    for a, b in gc._blocks(hs, recent - timedelta(days=1)):       # the older version: blocks, merged as they came
        gc.merge(store, gc.read_block(_hga(today=TODAY), a, b), a, b)
    store.update(backfill={"from": hs.isoformat(), "next": recent.isoformat(), "done": True},
                 recent_at=gc.gu._now_iso(NOW), read_today=TODAY.isoformat())
    want = {}
    for a, b in gc._blocks(hs, recent - timedelta(days=1)):
        gc.merge(want, gc.read_block(_cga(today=TODAY), a, b), a, b)
    old = {X: v for X, v in want["x"].items() if X <= "2026-08-09"}            # every cell from those days
    assert {X: v for X, v in store["x"].items() if X <= "2026-08-09"} != old
    try:                                                           # the first run: June whole (nothing hidden: its
        gc.step_app(_hga(today=TODAY, stop_after=3), store, TODAY, hs, NOW + timedelta(hours=1))   # list's oldest days
        raise AssertionError("no stop")                            # are before the app), July's block dropped, cut
    except gc.Stop:                                                # in its first day alone
        pass
    assert store["chk"] == {"v": gc.CHK_V, "next": "2026-07-01", "end": "2026-09-08", "al": "2026-07-30", "c": 1,
                            "n": 1, "m": 1}                        # June: one step of one call
    assert store["rf"] == recent.isoformat()                       # the window that version refreshed: the next
                                                                   # refresh's, from its first day, whenever it runs
    ga, info = _hga(today=TODAY), {}
    gc.step_app(ga, store, TODAY, hs, NOW + timedelta(hours=2), info)
    assert ga.asked[0][0]["dateRanges"][0] == {"startDate": "2026-07-01", "endDate": "2026-07-01"}
    assert gc.CHK_CALLS <= ga.calls <= gc.CHK_CALLS + 4 and info["checked"] == ga.calls // 4
    for i in range(40):
        if store["chk"].get("done"):
            break
        ga = _hga(today=TODAY)
        gc.step_app(ga, store, TODAY, hs, NOW + timedelta(hours=2, minutes=i + 1), info)     # the refresh not due
        assert ga.calls <= gc.CHK_CALLS + 4
    assert store["chk"] == {"v": gc.CHK_V, "done": True} and info["checked"] == (recent - date(2026, 7, 1)).days
    assert {X: v for X, v in store["x"].items() if X <= "2026-08-09"} == old
    assert "lo" not in store and "lf" not in store
    ga = _hga(today=TODAY)                                          # done: never again
    assert gc.step_app(ga, store, TODAY, hs, NOW + timedelta(hours=3)) == "fresh" and ga.calls == 0


# ── no day left unread, nothing silently low (review, 21 Oct 2026) ─────────────────────────────────────────────────
def _day_cells(x, D):
    """Activity day D's cells in a store's "x": {install day: (users, micros)} (lag D − X, 0 … 30; non-zero only)."""
    out = {}
    for L in range(gc.LAGS):
        e = x.get((D - timedelta(days=L)).isoformat())
        if e and (e["u"][L] or e["r"][L]):
            out[(D - timedelta(days=L)).isoformat()] = (e["u"][L], e["r"][L])
    return out


def _older_store(hs, today, now):
    """A store an older version made (blocks only, every one's in-list hiding its 5 oldest install days): the
    backfill through the window, the window refreshed at `now`."""
    recent = today - timedelta(days=gc.RECENT_DAYS - 1)
    store = {"v": gc.STORE_V}
    for a, b in gc._blocks(hs, recent - timedelta(days=1)) + [(recent, today)]:
        gc.merge(store, gc.read_block(_hga(today=today), a, b), a, b)
    store.update(backfill={"from": hs.isoformat(), "next": recent.isoformat(), "done": True},
                 recent_at=gc.gu._now_iso(now), read_today=today.isoformat())
    return store


def test_the_first_refresh_goes_on_from_where_the_history_check_ends():
    """The history check ends where the window the older version last refreshed begins; that window is the refresh's
    to read again — from its first day even when the first refresh of this version comes on a later property day
    (the floor "rf"): no day an older version read is left as it was."""
    hs, nxt = date(2026, 6, 1), TODAY + timedelta(days=1)
    store = _older_store(hs, TODAY, NOW)
    truth = _truth(hs, nxt)
    D = TODAY - timedelta(days=gc.RECENT_DAYS - 1)                      # the window's first day (Sep 9)
    assert _day_cells(store["x"], D) != _day_cells(truth, D)            # 5 install days hidden by its in-list
    gc.step_app(_hga(today=TODAY), store, TODAY, hs, NOW + timedelta(hours=1))      # no refresh due: the check made
    assert store["chk"]["end"] == "2026-09-08" and store["rf"] == D.isoformat() and "rs" not in store
    for i in range(80):                                                 # the next property day on: the window moved
        gc.step_app(_hga(today=nxt), store, nxt, hs, NOW + timedelta(days=1, minutes=i))
        if store["chk"].get("done"):
            break
    assert store["chk"] == {"v": gc.CHK_V, "done": True} and "rf" not in store and "rn" not in store
    for X in gc._days(hs, nxt - timedelta(days=gc.FINAL_LAG)):          # every final day: its true cells
        assert _day_cells(store["x"], X) == _day_cells(truth, X), X
    assert "lo" not in store and "lf" not in store


def test_a_stop_between_the_backfill_and_its_refresh_leaves_no_day_unread():
    """The backfill done (through the window's day before), the refresh's block cut by a Stop before it read a day,
    then the property's day changes: the next refresh starts at the backfill's next day (the floor), not at its
    own window's — no day between them left unread (cells "0" that nobody read)."""
    store = {"v": gc.STORE_V}
    try:
        gc.step_app(FakeGA(stop_after=4), store, TODAY, FakeGA.HS, NOW)
        raise AssertionError("no stop")
    except gc.Stop:
        pass
    assert store["backfill"]["done"] and store["rf"] == "2026-09-09" and "recent_at" not in store
    nxt = TODAY + timedelta(days=1)
    ga = FakeGA()
    assert gc.step_app(ga, store, nxt, FakeGA.HS, NOW + timedelta(days=1)) == "fetched"
    assert [q[0]["dateRanges"][0] for q in ga.asked] == [{"startDate": "2026-09-09", "endDate": "2026-09-09"},
                                                         {"startDate": "2026-09-10", "endDate": nxt.isoformat()}]
    want = {}
    gc.merge(want, gc.read_block(FakeGA(), FakeGA.HS, nxt), FakeGA.HS, nxt)
    assert store["x"] == want["x"] and "rf" not in store and store["rs"] == [gc.gu._now_iso(NOW + timedelta(days=1)),
                                                                             "2026-09-10"]


def test_a_refresh_by_another_version_is_read_again():
    """Another (older) copy of this code refreshed the window since this version did — one block whose in-list hid
    "(other)", over days this version had read alone and noted final ("fa"): the next refresh sees a "recent_at" it
    did not write ("rs") and reads again from its own last window start (a day since slid out of the window too),
    nothing skipped."""
    hs = date(2026, 6, 1)
    store = {"v": gc.STORE_V, "backfill": {"done": True}, "chk": {"v": gc.CHK_V, "done": True}}
    gc.step_app(_hga(today=TODAY), store, TODAY, hs, NOW)
    recent = TODAY - timedelta(days=gc.RECENT_DAYS - 1)
    assert store["rs"] == [gc.gu._now_iso(NOW), recent.isoformat()] and len(store["fa"]) == gc.RECENT_DAYS - 3
    truth = _truth(hs, TODAY + timedelta(days=1))
    assert all(_day_cells(store["x"], D) == _day_cells(truth, D) for D in gc._days(recent, TODAY - timedelta(days=3)))
    gc.merge(store, gc.read_block(_hga(today=TODAY), recent, TODAY), recent, TODAY)     # the older version's refresh
    store.update(recent_at=gc.gu._now_iso(NOW + timedelta(hours=7)), read_today=TODAY.isoformat())
    assert _day_cells(store["x"], recent) != _day_cells(truth, recent)
    nxt = TODAY + timedelta(days=1)
    ga = _hga(today=nxt)
    gc.step_app(ga, store, nxt, hs, NOW + timedelta(days=1))
    assert ga.asked[0][0]["dateRanges"][0]["startDate"] == recent.isoformat()     # Sep 9: out of today's window
    for D in gc._days(recent, nxt - timedelta(days=gc.FINAL_LAG)):
        assert _day_cells(store["x"], D) == _day_cells(truth, D), D
    assert store["rs"][0] == store["recent_at"] and "rf" not in store and "lo" not in store and "lf" not in store


def test_a_resumed_backfill_never_calls_a_dropped_block_again():
    """A Stop in the days of a backfill block that was dropped: the next run goes on with that block's days alone
    ("al"), never a block call over them first — no day is in two block calls."""
    hs = date(2026, 6, 1)
    recent = TODAY - timedelta(days=gc.RECENT_DAYS - 1)
    store, blocks, first = {"v": gc.STORE_V}, [], []
    for i in range(20):
        ga = _cga(today=TODAY, cap=1000, stop_after=20)
        try:
            gc.step_app(ga, store, TODAY, hs, NOW + timedelta(minutes=i))
        except gc.Stop:
            pass
        rs = [q[0]["dateRanges"][0] for q in ga.asked]
        first.append(rs[0])
        blocks += [(date.fromisoformat(r["startDate"]), date.fromisoformat(r["endDate"])) for r in rs
                   if r["startDate"] != r["endDate"] and r["endDate"] < recent.isoformat()]
        if store["backfill"].get("done"):
            break
    assert store["backfill"] == {"from": hs.isoformat(), "next": recent.isoformat(), "done": True} and len(first) > 2
    days = [D for a, b in blocks for D in gc._days(a, b)]
    assert len(days) == len(set(days)) and len(blocks) == 4             # each block called once
    assert all(r["startDate"] == r["endDate"] for r in first[1:])       # every resumed run: a day alone first
    want = {}
    for a, b in gc._blocks(hs, recent - timedelta(days=1)):
        gc.merge(want, gc.read_block(_cga(today=TODAY), a, b), a, b)
    assert all(_day_cells(store["x"], D) == _day_cells(want["x"], D) for D in gc._days(hs, recent - timedelta(days=1)))


def test_older_days_marks_live_in_the_older_file(tmp_path):
    """"lo" / "lf" by activity day: the days before the hot cut go in the older file (written only when it changes),
    never in every hourly hot file; read back whole; a store saved before (every mark in the hot file) reads the
    same."""
    data = str(tmp_path)
    store = {"v": gc.STORE_V, "stream_id": "222", "x": {"2026-06-05": {"r": [1] * gc.LAGS, "u": [1] * gc.LAGS},
                                                        "2026-10-01": {"r": [2] * gc.LAGS, "u": [1] * gc.LAGS}},
             "lo": {"2026-06-05": 10, "2026-10-01": 20}, "lf": {"2026-07-01": 1}}
    gc.save_store(data, "a~1", store, TODAY)
    with gzip.open(gc.store_path(data, "a~1"), "rt") as f:
        hot = json.load(f)
    with gzip.open(gc.store_path(data, "a~1", old=True), "rt") as f:
        old = json.load(f)
    assert hot["cut"] == "2026-08-01" and hot["lo"] == {"2026-10-01": 20} and "lf" not in hot   # older only
    assert old["lo"] == {"2026-06-05": 10} and old["lf"] == {"2026-07-01": 1}
    back = gc.load_store(data, "a~1")
    assert back["lo"] == store["lo"] and back["lf"] == store["lf"] and back["x"] == store["x"]
    back["lo"].pop("2026-06-05")                                        # an older day read again clean
    gc.save_store(data, "a~1", back, TODAY)
    with gzip.open(gc.store_path(data, "a~1", old=True), "rt") as f:
        assert "lo" not in json.load(f)
    assert gc.load_store(data, "a~1")["lo"] == {"2026-10-01": 20}
    gc.write_json_gz_stable(gc.store_path(data, "a~1"), dict(hot, lo=store["lo"]))     # the version before
    assert gc.load_store(data, "a~1")["lo"] == store["lo"]


def test_a_whole_day_answer_that_is_not_whole_measures_nothing():
    """The day's every-install-day read (no in-list) measures what the in-list hid only when it is whole: an
    "(other)" row in it, GA4's dataLossFromOtherRow on it with no row (GA4 can flag a read with no filter too), or
    sampling → nothing to measure by: the day in "lf" (≈), never its cells taken from that answer, never silently
    low."""
    a, b = date(2026, 9, 1), date(2026, 9, 3)
    for kw in ({"oth_whole": True}, {"flag_whole": True}, {"smp_whole": True}):
        store, ga = {}, _hga(**kw)
        info, _ = _run(ga, store, a, b)
        assert sorted(store["lf"]) == [D.isoformat() for D in gc._days(a, b)] and "lo" not in store, kw
        assert info["flagged"] == 3 and info["hidden"] == 0, kw


def test_the_history_check_of_a_store_mid_backfill():
    """The check of a store an older version left mid-backfill ends at the backfill's day before "next" (this
    version's backfill reads the rest, and its own refresh after it); one whose backfill is done ends before the
    window and leaves that to the refresh (the floor); a store with nothing read: done at once."""
    hs = date(2026, 6, 1)
    recent = TODAY - timedelta(days=gc.RECENT_DAYS - 1)
    store = {"backfill": {"from": "2026-06-01", "next": "2026-08-01"}}
    assert gc._chk(store, hs, recent) == {"v": gc.CHK_V, "next": "2026-06-01", "end": "2026-07-31"}
    assert "rf" not in store
    store = {"backfill": {"from": "2026-06-01", "next": recent.isoformat(), "done": True}}
    assert gc._chk(store, hs, recent)["end"] == "2026-09-08" and store["rf"] == recent.isoformat()
    store = {}
    assert gc._chk(store, hs, recent) == {"v": gc.CHK_V, "done": True} and "rf" not in store


def test_the_check_starts_a_step_only_with_time_for_it():
    """The history check shares the run's budget: a step (a block, or a day alone) starts only when the time left
    fits the most calls a step took at the app's seconds a call — the run ends with the step it finished, never a
    budget Stop throwing a started day away."""
    hs = date(2026, 6, 1)
    store = _older_store(hs, TODAY, NOW)
    clock = [0.0]

    def timed():
        ga = _hga(today=TODAY)
        real = ga.report_all

        def report_all(body, event=None, events=None, extra=None, page_rows=None):
            if clock[0] >= 60:
                raise gc.Stop("budget")
            clock[0] += 5.0
            return real(body, event, events, extra, page_rows)
        ga.report_all = report_all
        ga.clock, ga.t_end, ga.t_app = (lambda: clock[0]), 60.0, clock[0]
        return ga
    for i in range(3):
        clock[0] = 0.0
        ga = timed()
        gc.step_app(ga, store, TODAY, hs, NOW + timedelta(hours=1, minutes=i))   # never raises
        assert ga.calls <= 12 and store["chk"]["s"] == 5.0
    assert store["chk"]["n"] >= 3 and not store["chk"].get("done")
