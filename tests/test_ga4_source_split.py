"""💰 Revenue by source × country / × phone model — the fetches (admob_iq.fetch.ga4_source_cty, ga4_source_dev) and the
build's two views (admob_iq.source_build.cc_files / dv_file), offline with a fake GA4 and made-up countries, phones,
channels and numbers: the one read shape each, the country store one file a month (the recent days every 3 hours, the
history newest first in 30-day chunks, resumed after a stop), the phone windows read whole and again only when their days
moved, the groups (Paid / Notification / Organic / Other) per country per period and per day for Custom, GA4's "(not set)"
→ "--" and its "(other)" row kept, the phone rows biggest first with their names, the run's pointers and kept files, and
counts-only lines."""
import gzip
import json
from datetime import date, datetime, timedelta, timezone

from admob_iq import source_build as sb
from admob_iq.fetch import ga4_device as gd
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_source as gs
from admob_iq.fetch import ga4_source_cty as gsc
from admob_iq.fetch import ga4_source_dev as gsd
from admob_iq.fetch import ga4_uninstall as gu

NOW = datetime(2026, 10, 31, 6, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 31)
AID = "ca-app-pub-0000000000000000~21"
KEY = gu.file_key(AID)
# per country per day: {channel: (sessions, revenue)}; "(not set)" and GA4's folded "(other)" row as GA4 names them
CTY = {"XA": {"Cross-network": (10, 1.0), "Mobile Push Notifications": (5, 0.5), "Direct": (4, 0.25)},
       "XB": {"Cross-network": (2, 0.2), "Unassigned": (1, 0.05)},
       "(not set)": {"Direct": (1, 0.01)},
       "(other)": {"(other)": (3, 0.3)}}
PHONES = {"XP-1": {"Cross-network": (40, 4.0), "Mobile Push Notifications": (10, 1.0)},
          "XP-2": {"Direct": (30, 2.0)},
          "(other)": {"(other)": (5, 0.5)}}


class FakeGA:
    """Every day of every range asked (from `first` on): CTY per day (date × country × channel) or PHONES once per read
    (model × channel, the range as one)."""

    def __init__(self, first=None, stop_after=None, fold=False):
        self.calls, self.asked, self.first, self.stop_after, self.fold = 0, [], first, stop_after, fold
        self.last_metas, self.tok = [{}], 0

    def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise gf.Stop("calls")
        self.calls += 1
        self.asked.append(body)
        dims = [x["name"] for x in body["dimensions"]]
        a = date.fromisoformat(body["dateRanges"][0]["startDate"])
        b = date.fromisoformat(body["dateRanges"][0]["endDate"])
        if dims == ["mobileDeviceModel", "sessionDefaultChannelGroup"]:
            return [{"mobileDeviceModel": m, "sessionDefaultChannelGroup": ch, "sessions": s, "totalRevenue": r}
                    for m, chs in PHONES.items() for ch, (s, r) in chs.items()]
        assert dims == ["date", "countryId", "sessionDefaultChannelGroup"], dims
        rows, d = [], a
        while d <= b:
            if self.first is None or d >= self.first:
                for cc, chs in CTY.items():
                    for ch, (s, r) in chs.items():
                        rows.append({"date": d.strftime("%Y%m%d"), "countryId": cc, "sessionDefaultChannelGroup": ch,
                                     "sessions": s, "totalRevenue": r})
            d += timedelta(days=1)
        if self.fold:                                   # GA4's folded row: country, channel AND day "(other)"
            rows.append({"date": "(other)", "countryId": "(other)", "sessionDefaultChannelGroup": "(other)",
                         "sessions": 7 * ((b - a).days + 1), "totalRevenue": 0.7 * ((b - a).days + 1)})
        return rows


def test_country_store_one_file_a_month_recent_then_history(tmp_path):
    data = str(tmp_path)
    ga, meta = FakeGA(first=date(2026, 9, 1)), {"v": gsc.STORE_V}
    assert gsc.step_app(ga, meta, data, AID, TODAY, date(2026, 8, 1), NOW) == "fetched"
    b = ga.asked[0]
    assert [x["name"] for x in b["dimensions"]] == ["date", "countryId", "sessionDefaultChannelGroup"]
    assert [x["name"] for x in b["metrics"]] == ["sessions", "totalRevenue"] and b["currencyCode"] == "USD"
    ranges = [(x["dateRanges"][0]["startDate"], x["dateRanges"][0]["endDate"]) for x in ga.asked]
    assert ranges[0] == ("2026-10-27", "2026-10-31") and ranges[1] == ("2026-09-27", "2026-10-26")
    assert ranges[-1] == ("2026-08-01", "2026-08-27") and meta["backfill"] == {"oldest": "2026-08-01", "done": True}
    assert meta["months"] == ["2026-08", "2026-09", "2026-10"]
    with gzip.open(gsc.month_path(data, AID, "2026-09"), "rt", encoding="utf-8") as f:
        sep = json.load(f)["days"]
    assert len(sep) == 30 and sep["2026-09-01"]["XA"]["Mobile Push Notifications"] == [5, 0.5]
    assert sep["2026-09-01"]["(not set)"] == {"Direct": [1, 0.01]} and sep["2026-09-01"]["(other)"] == {"(other)": [3, 0.3]}
    days = gsc.load_days(data, AID, meta["months"])
    assert len(days) == (TODAY - date(2026, 8, 1)).days + 1 and days["2026-08-15"] == {}
    # the recent days again only after 3 hours
    ga2 = FakeGA()
    assert gsc.step_app(ga2, meta, data, AID, TODAY, date(2026, 8, 1), NOW + timedelta(hours=2)) == "fresh"
    assert gsc.step_app(ga2, meta, data, AID, TODAY, date(2026, 8, 1), NOW + timedelta(hours=3)) == "fetched"
    assert ga2.calls == 1


def test_country_history_resumes_after_a_stop(tmp_path):
    data = str(tmp_path)
    meta = {"v": gsc.STORE_V}
    try:
        gsc.step_app(FakeGA(stop_after=2), meta, data, AID, TODAY, date(2026, 6, 1), NOW)
        raise AssertionError("no stop")
    except gf.Stop:
        pass
    assert meta["backfill"] == {"oldest": "2026-09-27"} and meta["months"] == ["2026-09", "2026-10"]  # both reads kept
    ga = FakeGA()
    assert gsc.step_app(ga, meta, data, AID, TODAY, date(2026, 6, 1), NOW) == "fetched"
    assert ga.asked[0]["dateRanges"][0] == {"startDate": "2026-08-28", "endDate": "2026-09-26"}
    assert meta["backfill"]["done"] and len(gsc.load_days(data, AID, meta["months"])) == (TODAY - date(2026, 6, 1)).days + 1


def test_country_folded_row_read_day_by_day_and_kept(tmp_path):
    """GA4's "(other)" row has no real day: a range read holding one is read again a day at a time (the row then kept
    on its day, never dropped), and the app is read day by day from then on."""
    data = str(tmp_path)
    ga, meta = FakeGA(fold=True), {"v": gsc.STORE_V}
    gsc.step_app(ga, meta, data, AID, TODAY, date(2026, 10, 20), NOW)
    ranges = [(x["dateRanges"][0]["startDate"], x["dateRanges"][0]["endDate"]) for x in ga.asked]
    assert ranges[0] == ("2026-10-27", "2026-10-31") and ranges[1:6] == [("2026-10-%02d" % d,) * 2 for d in range(27, 32)]
    assert ranges[6] == ("2026-10-20", "2026-10-20") and meta["daily"] is True     # the backfill: one day a call now
    days = gsc.load_days(data, AID, meta["months"])
    # each day: the plain "(other)" country row (3, 0.3) + that day's folded row (7, 0.7), nothing dropped
    assert days["2026-10-30"]["(other)"] == {"(other)": [10, 1.0]} and days["2026-10-20"]["(other)"] == {"(other)": [10, 1.0]}
    assert len(days) == 12 and all(d["XA"]["Cross-network"] == [10, 1.0] for d in days.values())


def test_country_outage_days_read_before_the_recent_ones(tmp_path):
    """A refresh that comes back after a long gap reads the days since its last recent read first: never a hole."""
    data = str(tmp_path)
    meta = {"v": gsc.STORE_V, "upto": "2026-10-20", "recent_at": "2026-10-20T06:00:00Z",
            "backfill": {"oldest": "2026-10-01", "done": True}}
    ga = FakeGA()
    assert gsc.step_app(ga, meta, data, AID, TODAY, date(2026, 10, 1), NOW) == "fetched"
    ranges = [(x["dateRanges"][0]["startDate"], x["dateRanges"][0]["endDate"]) for x in ga.asked]
    assert ranges == [("2026-10-21", "2026-10-26"), ("2026-10-27", "2026-10-31")] and meta["upto"] == "2026-10-31"


def test_phone_windows_read_whole_and_again_when_they_move():
    # F = 31 Oct − 3 = 28 Oct, the newest final day; "lm" = the last month whose last day ≤ F (September)
    w = gsd.windows(TODAY, date(2026, 9, 15))
    assert w["30"] == (date(2026, 9, 29), date(2026, 10, 28)) and w["lm"] == (date(2026, 9, 15), date(2026, 9, 30))
    assert w["90"] == (date(2026, 9, 15), date(2026, 10, 28)) and w["all"] == (date(2026, 9, 15), date(2026, 10, 28))
    assert w["60"] == (date(2026, 9, 15), date(2026, 10, 28))                     # (from the history start)
    assert gsd.windows(TODAY, date(2026, 1, 1))["60"] == (date(2026, 8, 30), date(2026, 10, 28))
    assert gsd.windows(date(2026, 11, 3), date(2026, 1, 1))["lm"] == (date(2026, 10, 1), date(2026, 10, 31))
    assert gsd.windows(date(2026, 9, 10), date(2026, 9, 15)) == {}                  # nothing whole yet
    # the month mover (4 Nov 2026): every WHOLE month (last day ≤ F), from the history start; the current month never
    assert w["mon:2026-09"] == w["lm"] and not any(k.startswith("mon:2026-10") for k in w)
    full = gsd.windows(TODAY, date(2026, 1, 1))
    assert sorted(k for k in full if k.startswith("mon:")) == ["mon:2026-%02d" % m for m in range(1, 10)]
    assert full["mon:2026-02"] == (date(2026, 2, 1), date(2026, 2, 28))
    ga, store = FakeGA(), {"v": gsd.STORE_V}
    # 5 windows + 9 whole months (Jan–Sep); September = Last month's days: copied, no second call
    assert gsd.step_app(ga, store, TODAY, date(2026, 1, 1), NOW) == "fetched" and ga.calls == 13
    assert store["w"]["mon:2026-09"]["rows"] == store["w"]["lm"]["rows"]
    assert [x["name"] for x in ga.asked[0]["dimensions"]] == ["mobileDeviceModel", "sessionDefaultChannelGroup"]
    assert store["w"]["lm"]["lo"] == "2026-09-01" and store["w"]["all"]["lo"] == "2026-01-01"
    assert store["w"]["30"]["rows"]["XP-1"]["Mobile Push Notifications"] == [10, 1.0]
    ga2 = FakeGA()
    assert gsd.step_app(ga2, store, TODAY, date(2026, 1, 1), NOW) == "fresh" and ga2.calls == 0
    assert gsd.step_app(ga2, store, TODAY + timedelta(days=1), date(2026, 1, 1), NOW) == "fetched"
    assert ga2.calls == 4                                                         # 30 / 60 / 90 / all moved; lm not yet
    assert gsd.step_app(FakeGA(), store, TODAY + timedelta(days=3), date(2026, 1, 1), NOW) == "fetched"
    assert store["w"]["lm"]["hi"] == "2026-10-31"                                 # 3 Nov: October is final


def _country_store(data, first=date(2026, 9, 1)):
    meta = {"v": gsc.STORE_V}
    gsc.step_app(FakeGA(first=first), meta, data, AID, TODAY, date(2026, 8, 1), NOW)
    meta.update(app_id=AID, time_zone="UTC")
    _dump(gsc.store_path(data, AID), meta)


def _dump(path, obj):
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(obj, f)


def test_country_files_periods_and_days(tmp_path):
    data, out = str(tmp_path / "data"), tmp_path / "site"
    out.mkdir()
    _country_store(data)
    p = sb.cc_files(data, str(out), AID, NOW)
    assert p["file"] == "source_cc_%s.json.gz" % KEY and p["days"] == "source_ccd_%s.json.gz" % KEY and p["bf"] is True
    with gzip.open(out / p["file"], "rt", encoding="utf-8") as f:
        P = json.load(f)
    assert P["d0"] == "2026-09-01" and P["today"] == "2026-10-31" and set(P["P"]) == set(sb.CC_PERS)
    t = P["P"]["30"]
    assert (t["lo"], t["hi"], t["miss"]) == ("2026-10-01", "2026-10-30", 0)
    assert t["c"]["XA"] == [30, 15, 7.5, 0, 570]                     # 30 days × (paid 1, notification 0.5, organic 0.25)
    assert t["c"]["XB"] == [6, 0, 0, 1.5, 90] and t["c"]["--"] == [0, 0, 0.3, 0, 30] and t["c"]["(other)"] == [0, 0, 0, 9, 90]
    assert P["P"]["all"]["lo"] == "2026-09-01" and P["P"]["all"]["c"]["XA"][0] == 61
    with gzip.open(out / p["days"], "rt", encoding="utf-8") as f:
        D = json.load(f)
    assert D["rd"] == [[0, 60]]                                       # 1 Sep … 31 Oct read (August: before d0)
    assert D["c"]["XA"][0] == [0, 1, 0.5, 0.25, 0, 19] and len(D["c"]["XA"]) == 61


def test_phone_file_rows_biggest_first_with_names(tmp_path):
    data, out = tmp_path / "data", tmp_path / "site"
    out.mkdir()
    store = {"v": gsd.STORE_V}
    gsd.step_app(FakeGA(), store, TODAY, date(2026, 1, 1), NOW)
    _dump(gsd.store_path(str(data), AID), store)
    _dump(gd.store_path(str(data), AID), {"v": gd.STORE_V, "names": {"XP-1": ["XBrand", "Phone One"],
                                                                     "XP-9": ["XBrand", "Unused"]}})
    p = sb.dv_file(str(data), str(out), AID)
    with gzip.open(out / p["file"], "rt", encoding="utf-8") as f:
        D = json.load(f)
    assert set(D["w"]) == {"30", "lm", "60", "90", "all"} | {"mon:2026-%02d" % m for m in range(1, 10)}
    assert D["w"]["30"]["rows"] == [["XP-1", 4.0, 1.0, 0, 0, 50], ["XP-2", 0, 0, 2.0, 0, 30], ["(other)", 0, 0, 0, 0.5, 5]]
    assert D["names"] == {"XP-1": ["XBrand", "Phone One"]}


def test_run_points_at_both_views_and_keeps_their_files(tmp_path):
    data, out = tmp_path / "data", tmp_path / "site"
    (data / gs.DIR).mkdir(parents=True)
    out.mkdir()
    src = {"v": gs.STORE_V, "app_id": AID, "time_zone": "UTC",
           "days": {"2026-10-30": {"Cross-network": [1, 1, 0.1, 0.1]}}, "backfill": {"done": True}}
    with gzip.open(data / gs.DIR / (KEY + ".json.gz"), "wt", encoding="utf-8") as f:
        json.dump(src, f)
    _country_store(str(data))
    store = {"v": gsd.STORE_V}
    gsd.step_app(FakeGA(), store, TODAY, date(2026, 1, 1), NOW)
    _dump(gsd.store_path(str(data), AID), store)
    (out / ("source_cc_%s.json.gz" % "0123456789ab")).write_bytes(b"old")
    dash = {"apps_catalog": [{"app_id": AID, "app_name": "Alpha App"}]}
    assert sb.run(dash, str(data), str(out), {}, NOW) == ["/source*"]
    with gzip.open(out / "source.json.gz", "rt", encoding="utf-8") as f:
        e = json.load(f)["apps"][0]
    assert e["cc"]["file"] == "source_cc_%s.json.gz" % KEY and e["dv"]["file"] == "source_dv_%s.json.gz" % KEY
    for fn in (e["cc"]["file"], e["cc"]["days"], e["dv"]["file"]):
        assert (out / fn).exists()
    assert not (out / "source_cc_0123456789ab.json.gz").exists()                 # a stale view file is removed
    line = sb.pop_line()
    assert ", by country 1, by phone 1, kb " in line and AID not in line and "XA" not in line


def test_log_lines_are_counts_only():
    st = {"counts": {"selected": 3, "with_ga4": 2, "fetched": 1, "fresh": 1, "calls": 4, "tokens": 9}}
    assert gsc.log_line(st) == ("ga4 source by country: apps 3, with GA4 2, fetched 1, fresh 1, failed 0, deferred 0, "
                                "waiting 0, calls 4, tokens 9")
    assert gsd.log_line(dict(st, error="KeyError")).startswith("ga4 source by phone: apps 3, with GA4 2")
    assert gsd.log_line(dict(st, error="KeyError")).endswith(", error KeyError")
