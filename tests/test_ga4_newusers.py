"""🆕 First open — first opens by country × day (admob_iq.fetch.ga4_newusers), offline with a fake GA4 and made-up
countries / numbers: the two reads (every user, Google Ads users by the paid rule), the recent days every hour, the
history newest first in chunks down to the history start (resumed after a stop), "(not set)" kept as "--", sampled days
marked, and a counts-only line."""
from datetime import date, datetime, timedelta, timezone

from admob_iq.fetch import ga4_device as gd
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_newusers as gn

NOW = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)
TODAY = date(2026, 11, 2)
CC = {"XA": (100, 80), "XB": (10, 2), "(not set)": (3, 0)}     # a day: every user, Google Ads users


class FakeGA:
    def __init__(self, first=None, stop_after=None, sampled=False):
        self.calls, self.asked, self.first, self.stop_after, self.sampled = 0, [], first, stop_after, sampled
        self.last_metas, self.tok = [], 0

    def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise gf.Stop("calls")
        self.calls += 1
        paid = bool(extra) and extra[0] == gd._paid()
        self.asked.append((body, paid))
        a = date.fromisoformat(body["dateRanges"][0]["startDate"])
        b = date.fromisoformat(body["dateRanges"][0]["endDate"])
        rows, d = [], a
        while d <= b:
            if self.first is None or d >= self.first:
                for cc, (n, p) in CC.items():
                    v = p if paid else n
                    if v:
                        rows.append({"date": d.strftime("%Y%m%d"), "countryId": cc, "newUsers": v})
            d += timedelta(days=1)
        self.last_metas = [{"samplingMetadatas": [{"samplesReadCount": "1"}]}] if self.sampled else [{}]
        return rows


def test_two_reads_recent_then_history_newest_first():
    ga, store = FakeGA(first=date(2026, 3, 1)), {"v": gn.STORE_V}
    assert gn.step_app(ga, store, TODAY, date(2026, 1, 1), NOW) == "fetched"
    b0, p0 = ga.asked[0]
    assert [x["name"] for x in b0["dimensions"]] == ["date", "countryId"] and [x["name"] for x in b0["metrics"]] == ["newUsers"]
    assert [p for _, p in ga.asked[:2]] == [False, True]                       # every user, then Google Ads users
    ranges = [(x["dateRanges"][0]["startDate"], x["dateRanges"][0]["endDate"]) for x, _ in ga.asked[::2]]
    assert ranges[0] == ("2026-10-29", "2026-11-02") and ranges[1] == ("2026-07-01", "2026-10-28")
    assert ranges[-1][0] == "2026-01-01" and store["backfill"] == {"oldest": "2026-01-01", "done": True}
    days = store["days"]
    assert len(days) == (TODAY - date(2026, 1, 1)).days + 1
    assert days["2026-02-01"] == {"a": {}, "p": {}}
    assert days["2026-10-05"] == {"a": {"XA": 100, "XB": 10, "--": 3}, "p": {"XA": 80, "XB": 2}}
    ga2 = FakeGA()
    assert gn.step_app(ga2, store, TODAY, date(2026, 1, 1), NOW + timedelta(minutes=30)) == "fresh" and ga2.calls == 0
    assert gn.step_app(ga2, store, TODAY, date(2026, 1, 1), NOW + timedelta(hours=1)) == "fetched" and ga2.calls == 2


def test_history_resumes_after_a_stop_and_marks_sampled_days():
    ga, store = FakeGA(stop_after=3, sampled=True), {"v": gn.STORE_V}
    try:
        gn.step_app(ga, store, TODAY, date(2025, 1, 1), NOW)
        raise AssertionError("no stop")
    except gf.Stop:
        pass
    assert store["mark"]["2026-11-02"] == "s" and "backfill" in store and not store["backfill"].get("done")
    ga2 = FakeGA()
    assert gn.step_app(ga2, store, TODAY, date(2025, 1, 1), NOW) == "fetched"
    assert store["backfill"]["done"] and store["backfill"]["oldest"] == "2025-01-01"
    assert all(len(store["days"][d]["a"]) == 3 for d in ("2025-01-01", "2026-06-30", "2026-10-28"))


def test_log_line_is_counts_only():
    line = gn.log_line({"counts": {"selected": 3, "with_ga4": 2, "fetched": 1, "fresh": 1, "calls": 4, "tokens": 9}})
    assert line == "ga4 newusers: apps 3, with GA4 2, fetched 1, fresh 1, failed 0, deferred 0, waiting 0, calls 4, tokens 9"
