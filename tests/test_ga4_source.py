"""💰 Revenue by source — the fetch (admob_iq.fetch.ga4_source) and the build (admob_iq.source_build), offline with a fake
GA4 and made-up apps / channels / numbers: the one read shape (date × session channel), the recent refresh every hour,
the history newest first in chunks (resumed after a stop), days with nothing kept as {}, sampled days marked, the store
kept for good; the build's groups (Paid / Notification / Organic / Other), one row a day d0 … today with null for days not
read yet, the per-app channel file, the pointer, stale files removed, and counts-only lines."""
import gzip
import json
import os
from datetime import date, datetime, timedelta, timezone

from admob_iq import source_build as sb
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_source as gs
from admob_iq.fetch import ga4_uninstall as gu

NOW = datetime(2026, 10, 31, 6, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 31)
AID = "ca-app-pub-0000000000000000~11"
CHS = {"Cross-network": (100, 1.0), "Mobile Push Notifications": (50, 0.5), "Direct": (40, 0.3), "Organic Search": (10, 0.1),
       "(other)": (5, 0.02), "Unassigned": (2, 0.01), "Paid Search": (1, 0.01)}


class FakeGA:
    """Every day of every range asked: each channel of CHS (sessions, revenue); days before `first` have no rows."""

    def __init__(self, first=None, stop_after=None, sampled=False):
        self.calls, self.asked, self.first, self.stop_after, self.sampled = 0, [], first, stop_after, sampled
        self.last_metas, self.tok = [], 0

    def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise gf.Stop("calls")
        self.calls += 1
        self.asked.append(body)
        a = date.fromisoformat(body["dateRanges"][0]["startDate"])
        b = date.fromisoformat(body["dateRanges"][0]["endDate"])
        rows, d = [], a
        while d <= b:
            if self.first is None or d >= self.first:
                for ch, (ses, rev) in CHS.items():
                    rows.append({"date": d.strftime("%Y%m%d"), "sessionDefaultChannelGroup": ch, "sessions": ses,
                                 "activeUsers": ses // 2, "totalAdRevenue": rev, "totalRevenue": rev})
            d += timedelta(days=1)
        self.last_metas = [{"samplingMetadatas": [{"samplesReadCount": "1", "samplingSpaceSize": "2"}]}] if self.sampled else [{}]
        return rows


def test_one_read_shape_recent_then_history_newest_first():
    ga, store = FakeGA(first=date(2026, 3, 1)), {"v": gs.STORE_V}
    assert gs.step_app(ga, store, TODAY, date(2026, 1, 1), NOW) == "fetched"
    b = ga.asked[0]
    assert [x["name"] for x in b["dimensions"]] == ["date", "sessionDefaultChannelGroup"]
    assert [x["name"] for x in b["metrics"]] == list(gs.METS) and b["currencyCode"] == "USD"
    # the recent 5 days first, then the history newest first in 180-day chunks down to the history start
    ranges = [(x["dateRanges"][0]["startDate"], x["dateRanges"][0]["endDate"]) for x in ga.asked]
    assert ranges[0] == ("2026-10-27", "2026-10-31")
    assert ranges[1] == ("2026-04-30", "2026-10-26") and ranges[2] == ("2026-01-01", "2026-04-29")
    assert store["backfill"] == {"oldest": "2026-01-01", "done": True}
    days = store["days"]
    assert len(days) == (TODAY - date(2026, 1, 1)).days + 1
    assert days["2026-02-01"] == {} and days["2026-03-01"]["Mobile Push Notifications"] == [50, 25, 0.5, 0.5]
    # nothing due an hour later … the recent days again after it
    ga2 = FakeGA()
    assert gs.step_app(ga2, store, TODAY, date(2026, 1, 1), NOW + timedelta(minutes=30)) == "fresh" and ga2.calls == 0
    assert gs.step_app(ga2, store, TODAY, date(2026, 1, 1), NOW + timedelta(hours=1)) == "fetched" and ga2.calls == 1


def test_history_resumes_after_a_stop_and_marks_sampled_days():
    ga, store = FakeGA(stop_after=2, sampled=True), {"v": gs.STORE_V}
    try:
        gs.step_app(ga, store, TODAY, date(2025, 1, 1), NOW)
        raise AssertionError("no stop")
    except gf.Stop:
        pass
    assert store["backfill"] == {"oldest": "2026-04-30"} and store["mark"]["2026-10-31"] == "s"
    ga2 = FakeGA()
    assert gs.step_app(ga2, store, TODAY, date(2025, 1, 1), NOW) == "fetched"
    first = ga2.asked[0]["dateRanges"][0]
    assert first == {"startDate": "2025-11-01", "endDate": "2026-04-29"}          # went on where it stopped
    assert store["backfill"]["done"] and store["backfill"]["oldest"] == "2025-01-01"
    assert "2026-10-31" in store["mark"]                                           # the recent read was not due again


def _store(first=date(2026, 9, 1), till=TODAY, gap=None):
    days = {}
    d = date(2026, 8, 25)
    while d <= till:
        k = d.isoformat()
        if d < first:
            days[k] = {}
        elif not (gap and gap[0] <= d <= gap[1]):
            days[k] = {ch: [s, s // 2, r, r] for ch, (s, r) in CHS.items()}
        d += timedelta(days=1)
    return {"v": gs.STORE_V, "app_id": AID, "package": "com.example.alpha", "time_zone": "UTC", "days": days,
            "mark": {"2026-10-30": "s"}, "backfill": {"oldest": "2026-08-25", "done": True}}


def test_build_groups_rows_and_channel_file():
    entry, body = sb.build_app(_store(gap=(date(2026, 10, 1), date(2026, 10, 2))), AID, "Alpha", NOW)
    assert entry["d0"] == "2026-09-01" and entry["today"] == "2026-10-31"
    assert len(entry["rev"]) == 61 and entry["rev"][30] is None and entry["rev"][31] is None   # 1-2 Oct not read yet
    assert entry["rev"][0] == [1.01, 0.5, 0.4, 0.03] and entry["ses"][0] == [101, 50, 50, 7]
    assert entry["mk"] == {"59": "s"} and entry["bf"] is True
    assert entry["ch"][:2] == ["Cross-network", "Paid Search"] and entry["ch"][2] == "Mobile Push Notifications"
    assert body["ch"] == entry["ch"] and body["days"][0][2] == [50, 25, 0.5, 0.5] and body["days"][30] is None
    assert entry["file"] == "source_%s.json.gz" % gu.file_key(AID)


def test_groups_follow_the_owners_rule():
    assert [sb.group_of(c) for c in ("Cross-network", "Paid Search", "Mobile Push Notifications", "Direct",
                                     "Organic Search", "(other)", "Unassigned", "Display", "Referral", "Something new")] \
        == [0, 0, 1, 2, 2, 3, 3, 0, 2, 3]


def test_run_writes_files_pointer_and_removes_stale(tmp_path):
    data, out = tmp_path / "data", tmp_path / "site"
    (data / gs.DIR).mkdir(parents=True)
    out.mkdir()
    with gzip.open(data / gs.DIR / (gu.file_key(AID) + ".json.gz"), "wt", encoding="utf-8") as f:
        json.dump(_store(), f)
    (out / "source_0123456789ab.json.gz").write_bytes(b"old")
    dash = {"apps_catalog": [{"app_id": AID, "app_name": "Alpha App"}]}
    assert sb.run(dash, str(data), str(out), {}, NOW) == ["/source*"]
    assert not (out / "source_0123456789ab.json.gz").exists()
    p = dash["source"]
    assert p["file"] == "source.json.gz" and list(p["apps"]) == [AID]
    with gzip.open(out / "source.json.gz", "rt", encoding="utf-8") as f:
        j = json.load(f)
    assert j["apps"][0]["app"] == "Alpha App" and [g[0] for g in j["groups"]] == ["paid", "notif", "org", "oth"]
    assert j["groups"][1][2] == ["Mobile Push Notifications"] and j["groups"][3][2] == ["(other)", "Unassigned"]
    assert (out / p["apps"][AID]["file"]).exists()
    line = sb.pop_line()
    assert line.startswith("source: apps 1, days 61, history done 1, channels 7, kb ") and AID not in line
    # no store: no files, no pointer
    dash2 = {}
    assert sb.run(dash2, str(tmp_path / "none"), str(out), {}, NOW) == [] and "source" not in dash2
    assert not (out / "source.json.gz").exists() and sb.pop_line() == "source: apps 0"


def test_log_line_is_counts_only():
    line = gs.log_line({"counts": {"selected": 3, "with_ga4": 2, "fetched": 1, "fresh": 1, "calls": 4, "tokens": 9}})
    assert line == "ga4 source: apps 3, with GA4 2, fetched 1, fresh 1, failed 0, deferred 0, waiting 0, calls 4, tokens 9"
