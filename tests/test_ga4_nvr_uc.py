"""📈 eCPM first session vs returning × country — the fetch (admob_iq.fetch.ga4_nvr_uc) and the build's shards
(admob_iq.nvr_build.uc_files), offline with a fake GA4 and made-up countries, ad units and numbers: the one read shape,
one store file a month, GA4's folded row (no real day) read day by day and kept, the shards (a country always in the
same one, day index from the nvr file's first day, GA4's not-set group left out), the pointer, the kept files and
counts-only lines."""
import gzip
import json
import os
from datetime import date, datetime, timedelta, timezone

from admob_iq import nvr_build as nb
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_nvr as gv
from admob_iq.fetch import ga4_nvr_uc as gnc
from admob_iq.fetch import ga4_uninstall as gu

NOW = datetime(2026, 10, 31, 6, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 31)
AID = "ca-app-pub-0000000000000000~31"
KEY = gu.file_key(AID)
# per day: (nvr, format, ad unit, country) → (revenue, impressions); "(not set)" country → "--"
ROWS = [("new", "App open", "u_open", "XA", 1.0, 500), ("returning", "App open", "u_open", "XA", 2.0, 2000),
        ("new", "Banner", "u_ban", "XB", 0.5, 400), ("returning", "Banner", "u_ban", "(not set)", 0.1, 100),
        ("(not set)", "Banner", "u_ban", "XA", 0.01, 2)]


class FakeGA:
    def __init__(self, fold=False, stop_after=None):
        self.calls, self.asked, self.fold, self.stop_after = 0, [], fold, stop_after
        self.last_metas, self.tok = [{}], 0

    def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise gf.Stop("calls")
        self.calls += 1
        self.asked.append(body)
        assert [x["name"] for x in body["dimensions"]] == ["date", "newVsReturning", "adFormat", "adUnitName", "countryId"]
        a = date.fromisoformat(body["dateRanges"][0]["startDate"])
        b = date.fromisoformat(body["dateRanges"][0]["endDate"])
        out, d = [], a
        while d <= b:
            for k, fm, un, cc, rv, im in ROWS:
                out.append({"date": d.strftime("%Y%m%d"), "newVsReturning": k, "adFormat": fm, "adUnitName": un,
                            "countryId": cc, "totalAdRevenue": rv, "publisherAdImpressions": im})
            d += timedelta(days=1)
        if self.fold:
            out.append({"date": "(other)", "newVsReturning": "(other)", "adFormat": "(other)", "adUnitName": "(other)",
                        "countryId": "(other)", "totalAdRevenue": 0.3, "publisherAdImpressions": 30})
        return out


def test_one_read_shape_month_files_and_the_folded_row(tmp_path):
    data = str(tmp_path)
    meta = {"v": gnc.STORE_V}
    assert gnc.step_app(FakeGA(), meta, data, AID, TODAY, date(2026, 10, 1), NOW) == "fetched"
    days = gnc.load_days(data, AID, meta["months"])
    assert len(days) == 31 and meta["months"] == ["2026-10"] and meta["backfill"]["done"]
    assert days["2026-10-05"] == sorted([["n", "App open", "u_open", "XA", 1, 500], ["r", "App open", "u_open", "XA", 2, 2000],
                                         ["n", "Banner", "u_ban", "XB", 0.5, 400], ["r", "Banner", "u_ban", "--", 0.1, 100],
                                         ["x", "Banner", "u_ban", "XA", 0.01, 2]])
    # GA4's folded row has no real day: the range is read again a day at a time and the row kept on its day
    meta2, ga = {"v": gnc.STORE_V}, FakeGA(fold=True)
    gnc.step_app(ga, meta2, str(tmp_path / "b"), AID, TODAY, date(2026, 10, 28), NOW)
    d2 = gnc.load_days(str(tmp_path / "b"), AID, meta2["months"])
    assert meta2["daily"] is True and ["x", "(other)", "(other)", "--", 0.3, 30] in d2["2026-10-30"]
    assert len(d2) == 5 and all(len(v) == 6 for v in d2.values())                 # the recent window: 27 … 31 Oct


def _app_store(data):
    """The nvr store (its own days, so the nvr file exists) + the ad unit × country store."""
    days = {(date(2026, 10, 1) + timedelta(days=i)).isoformat(): {"u": [["n", "App open", "u_open", 1.0, 500]],
                                                                   "c": [["n", "XA", 1.0, 500]], "s": [["n", 10, 9]]}
            for i in range(31)}
    st = {"v": gv.STORE_V, "app_id": AID, "time_zone": "UTC", "days": days, "backfill": {"done": True}}
    os.makedirs(os.path.join(data, gv.DIR), exist_ok=True)
    with gzip.open(gv.store_path(data, AID), "wt", encoding="utf-8") as f:
        json.dump(st, f)
    meta = {"v": gnc.STORE_V}
    gnc.step_app(FakeGA(), meta, data, AID, TODAY, date(2026, 10, 1), NOW)
    meta.update(app_id=AID, time_zone="UTC")
    with gzip.open(gnc.store_path(data, AID), "wt", encoding="utf-8") as f:
        json.dump(meta, f)


def test_shards_pointer_and_kept_files(tmp_path):
    data, out = str(tmp_path / "data"), tmp_path / "site"
    out.mkdir()
    _app_store(data)
    (out / ("nvr_uc_%s_9.json.gz" % "0123456789ab")).write_bytes(b"old")
    dash = {}
    assert nb.run(dash, data, str(out), {}, NOW) == ["/nvr*"]
    uc = dash["nvr"]["apps"][AID]["uc"]
    assert uc["n"] == nb.UC_SHARDS and len(uc["files"]) == nb.UC_SHARDS and uc["rd"] == [[0, 30]] and uc["bf"] is True
    assert nb.shard_of("XA") == (88 * 31 + 65) % 8 and nb.shard_of("--") == 0
    with gzip.open(out / uc["files"][nb.shard_of("XA")][0], "rt", encoding="utf-8") as f:
        sh = json.load(f)
    assert sh["d0"] == "2026-10-01" and sh["units"] == [["u_open", "App open"], ["u_ban", "Banner"]]
    assert sh["c"]["XA"][:2] == [[0, 0, 0, 1, 500], [0, 0, 1, 2, 2000]] and len(sh["c"]["XA"]) == 62   # not-set group out
    with gzip.open(out / uc["files"][0][0], "rt", encoding="utf-8") as f:
        assert json.load(f)["c"]["--"][0] == [0, 1, 1, 0.1, 100]
    for fn, _ in uc["files"]:
        assert (out / fn).exists()
    assert not (out / "nvr_uc_0123456789ab_9.json.gz").exists()
    line = nb.pop_line()
    assert line.endswith(", by country 1") and "XA" not in line and AID not in line


def test_log_line_is_counts_only():
    st = {"counts": {"selected": 3, "with_ga4": 2, "fetched": 1, "fresh": 1, "calls": 4, "tokens": 9}}
    assert gnc.log_line(st) == ("ga4 nvr by country: apps 3, with GA4 2, fetched 1, fresh 1, failed 0, deferred 0, "
                                "waiting 0, calls 4, tokens 9")


def test_shards_double_when_one_is_too_big_then_say_big(tmp_path, monkeypatch):
    data, out = str(tmp_path / "data"), tmp_path / "site"
    out.mkdir()
    _app_store(data)
    monkeypatch.setattr(nb, "MAX_GZ", 10)                       # every shard with a country is over it
    uc = nb.uc_files(data, str(out), AID, "2026-10-01")
    assert uc["big"] is True and uc["files"] == [] and uc["n"] == 0
    assert not any(f.startswith("nvr_uc_") for f in os.listdir(out))   # nothing half written
    monkeypatch.setattr(nb, "MAX_GZ", 8 * 1024 * 1024)
    uc = nb.uc_files(data, str(out), AID, "2026-10-01")
    assert uc["n"] == nb.UC_SHARDS and len(uc["files"]) == nb.UC_SHARDS and "big" not in uc
