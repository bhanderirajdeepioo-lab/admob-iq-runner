"""📈 eCPM first session vs returning — the fetch (admob_iq.fetch.ga4_nvr), offline with a fake GA4 and made-up ad units /
countries / numbers: the three reads (ad unit, country, sessions) by newVsReturning, "(not set)" kept as "x", the recent days
every hour, the history newest first in chunks down to the history start (resumed after a stop), sampled days marked, and a
counts-only line."""
from datetime import date, datetime, timedelta, timezone

from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_nvr as gv

NOW = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)
TODAY = date(2026, 11, 2)
UNITS = (("App open", "unit_open"), ("Banner", "unit_banner"))
NV = {"new": (2.0, 100, 10, 9), "returning": (3.0, 1000, 40, 30), "(not set)": (0.01, 2, 5, 0)}   # revenue, impressions, sessions, users


class FakeGA:
    def __init__(self, first=None, stop_after=None, sampled=False):
        self.calls, self.asked, self.first, self.stop_after, self.sampled = 0, [], first, stop_after, sampled
        self.events = []                                    # each call's eventName filter
        self.last_metas, self.tok = [], 0

    def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise gf.Stop("calls")
        self.calls += 1
        self.asked.append(body)
        self.events.append(event)
        dims = [x["name"] for x in body["dimensions"]]
        a = date.fromisoformat(body["dateRanges"][0]["startDate"])
        b = date.fromisoformat(body["dateRanges"][0]["endDate"])
        rows, d = [], a
        while d <= b:
            if self.first is None or d >= self.first:
                for nv, (rev, imps, ses, us) in NV.items():
                    base = {"date": d.strftime("%Y%m%d"), "newVsReturning": nv}
                    if "adUnitName" in dims:
                        for fm, un in UNITS:
                            rows.append(dict(base, adFormat=fm, adUnitName=un, totalAdRevenue=rev / 2, eventCount=imps // 2))
                    elif "countryId" in dims:
                        rows.append(dict(base, countryId="XA", totalAdRevenue=rev * 0.6, eventCount=int(imps * 0.6)))
                        rows.append(dict(base, countryId="(not set)", totalAdRevenue=rev * 0.4, eventCount=int(imps * 0.4)))
                    else:
                        rows.append(dict(base, sessions=ses, activeUsers=us))
            d += timedelta(days=1)
        self.last_metas = [{"samplingMetadatas": [{"samplesReadCount": "1"}]}] if self.sampled else [{}]
        return rows


def test_three_reads_recent_then_history_newest_first():
    ga, store = FakeGA(first=date(2026, 6, 1)), {"v": gv.STORE_V}
    assert gv.step_app(ga, store, TODAY, date(2026, 1, 1), NOW) == "fetched"
    shapes = [[x["name"] for x in b["dimensions"]] for b in ga.asked[:3]]
    assert shapes == [["date", "newVsReturning", "adFormat", "adUnitName"], ["date", "newVsReturning", "countryId"],
                      ["date", "newVsReturning"]]
    assert [x["name"] for x in ga.asked[2]["metrics"]] == ["sessions", "activeUsers"] and ga.asked[0]["currencyCode"] == "USD"
    # the ad reads count impressions as ad_impression events; sessions are every event's
    assert [x["name"] for x in ga.asked[0]["metrics"]] == ["totalAdRevenue", "eventCount"]
    assert ga.events[:3] == ["ad_impression", "ad_impression", None]
    ranges = [(x["dateRanges"][0]["startDate"], x["dateRanges"][0]["endDate"]) for x in ga.asked[::3]]
    assert ranges[0] == ("2026-10-29", "2026-11-02") and ranges[1] == ("2026-07-31", "2026-10-28")
    assert ranges[-1][0] == "2026-01-01" and store["backfill"] == {"oldest": "2026-01-01", "done": True}
    days = store["days"]
    assert len(days) == (TODAY - date(2026, 1, 1)).days + 1 and days["2026-05-01"] == {"u": [], "c": [], "s": []}
    d = days["2026-10-05"]
    assert d["u"] == [["n", "App open", "unit_open", 1, 50], ["n", "Banner", "unit_banner", 1, 50],
                      ["r", "App open", "unit_open", 1.5, 500], ["r", "Banner", "unit_banner", 1.5, 500],
                      ["x", "App open", "unit_open", 0.005, 1], ["x", "Banner", "unit_banner", 0.005, 1]]
    assert d["c"][:2] == [["n", "--", 0.8, 40], ["n", "XA", 1.2, 60]]
    assert d["s"] == [["n", 10, 9], ["r", 40, 30], ["x", 5, 0]]
    ga2 = FakeGA()
    assert gv.step_app(ga2, store, TODAY, date(2026, 1, 1), NOW + timedelta(minutes=30)) == "fresh" and ga2.calls == 0
    assert gv.step_app(ga2, store, TODAY, date(2026, 1, 1), NOW + timedelta(hours=1)) == "fetched" and ga2.calls == 3


def test_history_resumes_after_a_stop_and_marks_sampled_days():
    ga, store = FakeGA(stop_after=4, sampled=True), {"v": gv.STORE_V}
    try:
        gv.step_app(ga, store, TODAY, date(2025, 6, 1), NOW)
        raise AssertionError("no stop")
    except gf.Stop:
        pass
    assert store["mark"]["2026-11-02"] == "s" and not store.get("backfill", {}).get("done")
    gv.step_app(FakeGA(), store, TODAY, date(2025, 6, 1), NOW)
    assert store["backfill"] == {"oldest": "2025-06-01", "done": True}
    assert all(len(store["days"][d]["u"]) == 6 for d in ("2025-06-01", "2026-01-15", "2026-10-28"))


def test_log_line_is_counts_only():
    line = gv.log_line({"counts": {"selected": 3, "with_ga4": 2, "fetched": 1, "fresh": 1, "calls": 4, "tokens": 9}})
    assert line == "ga4 nvr: apps 3, with GA4 2, fetched 1, fresh 1, failed 0, deferred 0, waiting 0, calls 4, tokens 9"


class RawGA(FakeGA):
    """GA4 samples a range that is still changing (it reaches the newest RECENT_DAYS days of `today`), never a final one
    (a busy app's raw events vs its daily tables)."""
    def __init__(self, today, **kw):
        super().__init__(**kw)
        self.today = today

    def report_all(self, body, **kw):
        rows = super().report_all(body, **kw)
        b = date.fromisoformat(body["dateRanges"][0]["endDate"])
        self.last_metas = ([{"samplingMetadatas": [{"samplesReadCount": "1"}]}]
                           if b > self.today - timedelta(days=gv.RECENT_DAYS) else [{}])
        return rows


def _ranges(ga):
    return [(x["dateRanges"][0]["startDate"], x["dateRanges"][0]["endDate"]) for x in ga.asked[::3]]


def test_a_final_day_still_marked_sampled_is_read_once_more_alone_newest_first():
    """16 Nov 2026 (the Breakeven card's day 1 on the busiest app): its newest days kept the sampled mark of the read made
    while GA4 was filling them — once final, each is read again alone and whole; never twice."""
    hs, store = TODAY - timedelta(days=20), {"v": gv.STORE_V}
    gv.step_app(RawGA(TODAY), store, TODAY, hs, NOW)
    recent = [(TODAY - timedelta(days=i)).isoformat() for i in range(gv.RECENT_DAYS)]
    assert sorted(store["mark"]) == sorted(recent) and set(store["mark"].values()) == {"s"} and store["rr"] == {}
    later, t2 = TODAY + timedelta(days=3), NOW + timedelta(days=3)
    ga = RawGA(later)
    assert gv.step_app(ga, store, later, hs, t2) == "fetched"
    left = [(TODAY - timedelta(days=i)).isoformat() for i in (2, 3, 4)]     # left the window: final now, newest first
    assert _ranges(ga)[1:] == [(d, d) for d in left] and ga.calls == 3 + 3 * len(left)
    assert all(d not in store["mark"] for d in left) and sorted(store["rr"]) == sorted(left)
    assert all(store["mark"][(later - timedelta(days=i)).isoformat()] == "s" for i in range(gv.RECENT_DAYS))
    ga2 = RawGA(later)                                                      # the next hour: the window only, nothing again
    gv.step_app(ga2, store, later, hs, t2 + timedelta(hours=1))
    assert ga2.calls == 3 and _ranges(ga2) == [((later - timedelta(days=gv.RECENT_DAYS - 1)).isoformat(), later.isoformat())]


def test_a_final_day_that_stays_sampled_keeps_its_mark_and_is_not_asked_again_and_a_stop_resumes():
    hs, store = TODAY - timedelta(days=20), {"v": gv.STORE_V}
    gv.step_app(RawGA(TODAY), store, TODAY, hs, NOW)                         # (the history whole, the window sampled)
    later, t2 = TODAY + timedelta(days=3), NOW + timedelta(days=3)
    ga = FakeGA(sampled=True, stop_after=3 + 3)                             # (from here on every read comes back sampled)                             # the window + one day alone, then a stop
    try:
        gv.step_app(ga, store, later, hs, t2)
        raise AssertionError("no stop")
    except gf.Stop:
        pass
    newest = (TODAY - timedelta(days=2)).isoformat()
    assert list(store["rr"]) == [newest] and store["mark"][newest] == "s"   # read alone, still sampled: the mark stays
    ga2 = FakeGA(sampled=True)
    gv.step_app(ga2, store, later, hs, t2 + timedelta(minutes=10))          # (the window is fresh: only the rest)
    assert _ranges(ga2) == [(d, d) for d in ((TODAY - timedelta(days=3)).isoformat(), (TODAY - timedelta(days=4)).isoformat())]
    ga3 = FakeGA(sampled=True)
    assert gv.step_app(ga3, store, later, hs, t2 + timedelta(minutes=20)) == "fresh" and ga3.calls == 0
