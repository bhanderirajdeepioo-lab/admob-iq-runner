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


class PartGA(FakeGA):
    """GA4 flags only the ad-unit read, every time — the country and sessions reads come whole (the busiest app on 16 Nov
    2026: its ad-unit reads sampled, its first-session × country read whole)."""
    def report_all(self, body, **kw):
        rows = super().report_all(body, **kw)
        self.last_metas = ([{"samplingMetadatas": [{"samplesReadCount": "1"}]}]
                           if "adUnitName" in [x["name"] for x in body["dimensions"]] else [{}])
        return rows


def test_each_reads_own_flag_is_kept_and_a_sampled_ad_unit_read_never_marks_the_country_read():
    """Owner, 16 Nov 2026: "sample data de esa ho hi nhi sakta … proper check kro" — the day keeps "s" in "mark" (one of
    its reads was), but "mp" says which: the country read ("c") is whole, so the Breakeven card's day-1 base stands."""
    hs, store = TODAY - timedelta(days=10), {"v": gv.STORE_V}
    gv.step_app(PartGA(), store, TODAY, hs, NOW)
    d = TODAY.isoformat()
    assert store["mark"][d] == "s" and store["mp"][d] == {"u": "s"} and "c" not in store["mp"][d]
    assert all(store["mp"][x] == {"u": "s"} for x in store["days"])                 # (the history too: per read)


def test_a_day_marked_by_the_old_all_in_one_rule_is_read_alone_once_to_learn_its_reads_own_flags():
    hs, store = TODAY - timedelta(days=20), {"v": gv.STORE_V}
    gv.step_app(FakeGA(), store, TODAY, hs, NOW)
    old = (TODAY - timedelta(days=9)).isoformat()                                  # a final day, as an older store kept it:
    store["mark"][old] = "s"
    store["mp"].pop(old)
    store["rr"][old] = 1                                                           # … even one read alone before
    ga = PartGA()
    gv.step_app(ga, store, TODAY, hs, NOW + timedelta(minutes=10))                 # (the window is fresh: only that day)
    assert _ranges(ga) == [(old, old)] and store["mp"][old] == {"u": "s"}
    ga2 = PartGA()
    gv.step_app(ga2, store, TODAY, hs, NOW + timedelta(minutes=20))
    assert ga2.calls == 0                                                          # known now: never again


class UnitRawGA(RawGA):
    """Only the ad-unit read of a still-changing range comes from a sample (its revenue off: × 1.5); a final day read
    alone is whole, and the country and sessions reads always are."""
    def report_all(self, body, **kw):
        rows = super().report_all(body, **kw)
        unit = "adUnitName" in [x["name"] for x in body["dimensions"]]
        hot = bool(self.last_metas and self.last_metas[0].get("samplingMetadatas"))
        if unit and hot:
            rows = [dict(r, totalAdRevenue=r["totalAdRevenue"] * 1.5) for r in rows]
        else:
            self.last_metas = [{}]
        return rows


def test_a_final_day_whose_ad_unit_read_was_sampled_is_read_once_more_alone_and_healed():
    """The lone re-read heals whichever read of a final day was sampled — the ad-unit and sessions rows feed the eCPM tab
    and the CPI screen — not only the country one; "rr" still asks it once."""
    hs, store = TODAY - timedelta(days=20), {"v": gv.STORE_V}
    gv.step_app(UnitRawGA(TODAY), store, TODAY, hs, NOW)
    d = (TODAY - timedelta(days=2)).isoformat()
    assert store["mark"][d] == "s" and store["mp"][d] == {"u": "s"} and store["days"][d]["u"][0][3] == 1.5
    later, t2 = TODAY + timedelta(days=3), NOW + timedelta(days=3)
    ga = UnitRawGA(later)
    gv.step_app(ga, store, later, hs, t2)
    left = [(TODAY - timedelta(days=i)).isoformat() for i in (2, 3, 4)]               # final now, newest first
    assert _ranges(ga)[1:] == [(x, x) for x in left] and sorted(store["rr"]) == sorted(left)
    assert all(x not in store["mark"] and store["mp"][x] == {} and store["days"][x]["u"][0][3] == 1 for x in left)
    ga2 = UnitRawGA(later)
    gv.step_app(ga2, store, later, hs, t2 + timedelta(hours=1))
    assert ga2.calls == 3                                                             # the window only: never again


def test_a_window_refresh_replaces_each_days_flags_and_a_sample_outranks_a_threshold(monkeypatch):
    """The newest read of a still-changing day replaces its flags (a country read sampled at one refresh and whole at the
    next is whole: never merged); "mark" is "s" when any read was sampled even if another was only thresholded."""
    from admob_iq import be_ecpm as bec
    hs, store = TODAY - timedelta(days=10), {"v": gv.STORE_V}
    seq = {"u": "t", "c": "s", "s": None}
    monkeypatch.setattr(gv, "_mark", lambda ga: seq[ga.part])

    class Tag(FakeGA):
        def report_all(self, body, **kw):
            dims = [x["name"] for x in body["dimensions"]]
            self.part = "u" if "adUnitName" in dims else ("c" if "countryId" in dims else "s")
            return super().report_all(body, **kw)
    gv.step_app(Tag(), store, TODAY, hs, NOW)
    d = TODAY.isoformat()
    assert store["mark"][d] == "s" and store["mp"][d] == {"u": "t", "c": "s"} and bec._sampled_base(store, {d}) == {d}
    seq.update(u=None, c=None)
    gv.step_app(Tag(), store, TODAY, hs, NOW + timedelta(hours=1))
    assert d not in store["mark"] and store["mp"][d] == {} and bec._sampled_base(store, {d}) == set()


def test_a_backfill_chunk_never_overwrites_a_day_already_read_alone():
    """A run that stopped before the backfill started leaves it to begin at the window's edge; a day read alone meanwhile
    (final, its own read) keeps that read and its flags — the coarser chunk could be a sample of it, never asked again."""
    hs, store = TODAY - timedelta(days=20), {"v": gv.STORE_V}
    ga = RawGA(TODAY, stop_after=3)                                     # the window, then a stop: no backfill yet
    try:
        gv.step_app(ga, store, TODAY, hs, NOW)
        raise AssertionError("no stop")
    except gf.Stop:
        pass
    assert not store.get("backfill")
    later, t2 = TODAY + timedelta(days=1), NOW + timedelta(days=1)
    gone = (TODAY - timedelta(days=4)).isoformat()                      # left the window: read alone, whole

    class ChunkSampled(UnitRawGA):                                      # … while the backfill chunk's ad-unit read is
        def report_all(self, body, **kw):                               # a sample (× 1.5)
            rows = FakeGA.report_all(self, body, **kw)
            a, b = (date.fromisoformat(body["dateRanges"][0][k]) for k in ("startDate", "endDate"))
            unit = "adUnitName" in [x["name"] for x in body["dimensions"]]
            chunk = (b - a).days > gv.RECENT_DAYS
            if unit and chunk:
                rows = [dict(r, totalAdRevenue=r["totalAdRevenue"] * 1.5) for r in rows]
            self.last_metas = [{"samplingMetadatas": [{"samplesReadCount": "1"}]}] if unit and chunk else [{}]
            return rows
    gv.step_app(ChunkSampled(later), store, later, hs, t2)
    assert store["rr"] == {gone: 1} and gone not in store["mark"] and store["mp"][gone] == {}
    assert store["days"][gone]["u"][0][3] == 1                          # its lone (whole) read, not the chunk's
    older = (TODAY - timedelta(days=5)).isoformat()
    assert store["mark"][older] == "s" and store["mp"][older] == {"u": "s"}    # (the chunk's own days keep its flags)


class Filling(FakeGA):
    """GA4 still filling a day: one under RECENT_DAYS old (by `today`) reads half its final numbers, unflagged."""
    def __init__(self, today, **kw):
        super().__init__(**kw)
        self.today = today

    def report_all(self, body, **kw):
        rows = super().report_all(body, **kw)
        out = []
        for r in rows:
            d = date(int(r["date"][:4]), int(r["date"][4:6]), int(r["date"][6:]))
            if (self.today - d).days < gv.RECENT_DAYS and "totalAdRevenue" in r:
                r = dict(r, totalAdRevenue=r["totalAdRevenue"] / 2, eventCount=r["eventCount"] // 2)
            out.append(r)
        return out


def test_the_first_backfill_chunk_takes_a_day_that_left_the_window_unflagged_and_heals_a_sampled_lone_read_part():
    """The first chunk (from the window's edge) holds every day's FINAL read: a day that left the window unflagged (its
    read made while GA4 was still filling it) takes the chunk's; a day read alone (in "rr") keeps each of its reads,
    except one that was a sample where the chunk's is whole — never asked again either way."""
    hs, store = TODAY - timedelta(days=20), {"v": gv.STORE_V}
    ga = Filling(TODAY, stop_after=3)                                    # the window (half filled), then a stop
    try:
        gv.step_app(ga, store, TODAY, hs, NOW)
        raise AssertionError("no stop")
    except gf.Stop:
        pass
    plain = (TODAY - timedelta(days=4)).isoformat()                      # leaves the window unflagged
    assert store["days"][plain]["c"][1] == ["n", "XA", 0.6, 30] and plain not in store["mark"]
    lone = (TODAY - timedelta(days=6)).isoformat()                       # (made by hand: read alone, its ad-unit read
    store["days"][lone] = {"u": [["n", "App open", "unit_open", 9.0, 50]], "c": [], "s": []}   # a sample)
    store["mark"][lone], store["mp"][lone], store["rr"] = "s", {"u": "s"}, {lone: 1}
    later = TODAY + timedelta(days=1)
    ga2 = FakeGA()
    gv.step_app(ga2, store, later, hs, NOW + timedelta(days=1))
    assert store["days"][plain]["c"][1] == ["n", "XA", 1.2, 60] and store["mp"][plain] == {}    # the chunk's final read
    assert store["days"][lone]["u"][0] == ["n", "App open", "unit_open", 1, 50]                # the whole chunk part
    assert store["mp"][lone] == {} and lone not in store["mark"] and store["rr"] == {lone: 1}
    assert store["days"][lone]["c"] == [] and store["days"][lone]["s"] == []                  # (its own whole parts stay)
    ga3 = FakeGA()
    gv.step_app(ga3, store, later, hs, NOW + timedelta(days=1, minutes=10))
    assert ga3.calls == 0                                                                      # never asked again


def test_a_lone_read_part_is_replaced_only_by_a_better_chunk_part_and_a_day_with_no_rows_takes_the_chunk(monkeypatch):
    """A day read alone ("rr") keeps each part unless the first chunk's is better (whole > thresholded > sampled): a
    sampled chunk never replaces a sampled lone part; a day with no rows kept takes the chunk's read whole; a day read
    alone before the store kept "mp" is left as it was."""
    hs, lone = TODAY - timedelta(days=20), (TODAY - timedelta(days=6)).isoformat()

    def case(own, chunk_u, rows=True):
        store = {"v": gv.STORE_V}
        monkeypatch.setattr(gv, "_mark", lambda ga: getattr(ga, "flag", None))
        try:
            gv.step_app(FakeGA(stop_after=3), store, TODAY, hs, NOW)              # the window, then a stop
            raise AssertionError("no stop")
        except gf.Stop:
            pass
        if rows:
            store["days"][lone] = {"u": [["n", "App open", "unit_open", 9.0, 50]], "c": [], "s": []}
        if own is not None:
            store["mp"][lone] = own
            gv._remark(store["mark"], lone, own)
        store["rr"] = {lone: 1}

        class G(FakeGA):
            def report_all(self, body, **kw):
                got = super().report_all(body, **kw)
                a, b = (date.fromisoformat(body["dateRanges"][0][k]) for k in ("startDate", "endDate"))
                unit = "adUnitName" in [x["name"] for x in body["dimensions"]]
                self.flag = chunk_u if unit and (b - a).days > gv.RECENT_DAYS else None
                return got
        gv.step_app(G(), store, TODAY + timedelta(days=1), hs, NOW + timedelta(days=1))
        return store
    st = case({"u": "s"}, "s")                                                   # sampled vs sampled: the lone stays
    assert st["days"][lone]["u"][0][3] == 9.0 and st["mp"][lone] == {"u": "s"} and st["mark"][lone] == "s"
    st = case({"u": "s"}, "t")                                                   # thresholded beats sampled
    assert st["days"][lone]["u"][0][3] == 1 and st["mp"][lone] == {"u": "t"} and st["mark"][lone] == "t"
    st = case({"u": "t"}, None)                                                  # whole beats thresholded
    assert st["days"][lone]["u"][0][3] == 1 and st["mp"][lone] == {} and lone not in st["mark"]
    st = case(None, None)                                                        # (before "mp": left as it was)
    assert st["days"][lone]["u"][0][3] == 9.0 and lone not in st["mp"] and lone not in st["mark"]
    st = case({"u": "t"}, None, rows=False)                                      # no rows kept: the chunk's, whole
    assert st["days"][lone]["u"][0][3] == 1 and st["days"][lone]["c"] and st["mp"][lone] == {}
    assert st["rr"] == {lone: 1}
