"""📈 eCPM first session vs returning — the build (admob_iq.nvr_build), on made-up stores: one lazy file per app (every day
first … last, null where not read, the day's totals from the country read, sessions, ad units indexed most revenue first,
countries), the pointer, a stale file removed, no store → no file and no pointer, and a counts-only line."""
import gzip
import json
import os
from datetime import datetime, timezone

from admob_iq import nvr_build as nb
from admob_iq.db import write_json_gz_stable
from admob_iq.fetch import ga4_nvr as gv
from admob_iq.fetch import ga4_uninstall as gu

NOW = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)
AID = "ca-app-pub-0000000000000000~21"


def store():
    day = {"u": [["n", "App open", "unit_open", 3, 100], ["n", "Banner", "unit_banner", 0.5, 400],
                 ["r", "Banner", "unit_banner", 2, 1000], ["x", "Banner", "unit_banner", 0.01, 3]],
           "c": [["n", "XA", 2, 300], ["n", "XB", 1.5, 200], ["r", "XA", 2.5, 1100], ["x", "--", 0.01, 3]],
           "s": [["n", 10, 9], ["r", 40, 30], ["x", 5, 0]]}
    return {"v": gv.STORE_V, "app_id": AID, "time_zone": "UTC",
            "days": {"2026-10-01": day, "2026-10-03": day, "2026-09-30": {"u": [], "c": [], "s": []}}}


def test_one_app_file():
    b = nb.build_app(store(), AID)
    assert (b["first_day"], b["last_day"]) == ("2026-10-01", "2026-10-03") and b["key"] == gu.file_key(AID)
    assert b["units"] == [["unit_open", "App open"], ["unit_banner", "Banner"]]           # most revenue first
    assert len(b["days"]) == 3 and b["days"][1] is None                                     # 2 Oct not read
    d = b["days"][0]
    assert d[0] == "2026-10-01" and d[1] == [3.5, 500, 2.5, 1100, 0.01, 3] and d[2] == [10, 9, 40, 30]
    assert d[3] == {"0": [3, 100, 0, 0], "1": [0.5, 400, 2, 1000]}
    assert d[4] == {"XA": [2, 300, 2.5, 1100], "XB": [1.5, 200, 0, 0]}


def test_run_writes_files_pointer_and_removes_stale(tmp_path):
    data, out = tmp_path / "data", tmp_path / "site"
    (data / gv.DIR).mkdir(parents=True)
    out.mkdir()
    write_json_gz_stable(str(data / gv.DIR / (gu.file_key(AID) + ".json.gz")), store())
    (out / "nvr_0123456789ab.json.gz").write_bytes(b"old")
    dash = {}
    assert nb.run(dash, str(data), str(out), {}, NOW) == ["/nvr*"]
    fn = "nvr_%s.json.gz" % gu.file_key(AID)
    assert sorted(f for f in os.listdir(out) if f.startswith("nvr_")) == [fn]
    p = dash["nvr"]["apps"][AID]
    assert p["file"] == fn and (p["from"], p["last"]) == ("2026-10-01", "2026-10-03")
    with gzip.open(out / fn, "rt") as f:
        assert json.load(f)["final_till"] == "2026-10-31"
    assert nb.pop_line() == "nvr: apps 1, days 3, ad units 2, by country 0"
    dash2 = {}
    assert nb.run(dash2, str(tmp_path / "none"), str(out), {}, NOW) == [] and "nvr" not in dash2
    assert not any(f.startswith("nvr_") for f in os.listdir(out)) and nb.pop_line() == "nvr: apps 0"
