"""🖼️ Screens, end to end on made-up data: the fetch (admob_iq/fetch/ga4_screens.py) writes its store the way the hourly
build and the history job really do — history job into the staged folder, the build's own run merging it — and the build
step (admob_iq/screens_build.py) reads that exact store into the tab's files. The two modules were written side by side
against one layout; this is the check that what one writes the other reads. Made-up apps, classes and units only."""

import gzip
import json
import os
from datetime import date, timedelta

from admob_iq import screens_build as sb
from admob_iq.fetch import ga4_screens as gs
from admob_iq.fetch import ga4_uninstall as gu

from tests.test_ga4_screens import AID, AID2, NOW, Model, _http, _patch_routes


def _dash(days):
    """A dashboard with the two made-up apps, their AdMob units (IST days) and the build's calendar fields."""
    pl = []
    for aid, acc, app in ((AID, "acc1", "Alpha"), (AID2, "acc1", "Beta")):
        for uid, name, fmt, imp in (("/1", "unit_a", "BANNER", 60), ("/2", "unit_b", "INTERSTITIAL", 10)):
            daily = [[d.isoformat(), 1000, imp, imp * 2, int(imp * 1.6), 1] for d in days]
            pl.append({"id": aid.split("~")[0] + uid + aid[-2:], "name": name, "app": app, "account": acc,
                       "format": fmt, "platform": "ANDROID", "daily": daily})
    return {"apps_catalog": [{"account_id": "acc1", "app_id": AID, "app_name": "Alpha", "selected": True},
                             {"account_id": "acc1", "app_id": AID2, "app_name": "Beta", "selected": True}],
            "placements": pl, "latest_complete": (NOW.date() - timedelta(days=1)).isoformat(),
            "today_date": NOW.date().isoformat(), "report_tz": "Asia/Calcutta", "app_icons": {}}


def _read(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def test_what_the_fetch_writes_the_build_reads(monkeypatch, tmp_path):
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"},
            {"app_id": AID2, "package": "com.example.beta", "pid": "112"}]
    _patch_routes(monkeypatch, apps)                        # history start 2026-10-21 for both
    _http(monkeypatch, Model())
    data, staged = str(tmp_path / "data"), str(tmp_path / "private" / gs.BF_DIR)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    # the history job fills the staged folder; the hourly build merges it and reads its recent window
    bf = gs.backfill_all(cfg, data, staged, [dict(a) for a in apps], NOW, clock=lambda: 0.0, workers=2, tick=0.01)
    assert bf["apps"] == {AID: "done", AID2: "done"} and "error" not in bf
    st = gs.refresh_all(cfg, data, [dict(a) for a in apps], NOW, clock=lambda: 0.0, staged_dir=staged)
    assert "error" not in st and set(st["apps"].values()) <= {"fetched", "fresh"}
    # the build's own readers see the fetch's store
    keys = set(sb.store_keys(data))
    assert set(keys) == {gu.file_key(AID), gu.file_key(AID2)}
    # the build step on that store
    days = [date(2026, 10, 15) + timedelta(days=i) for i in range(25)]
    dash = _dash(days)
    out = str(tmp_path / "site")
    paths = sb.run(dash, data, out, {}, NOW)
    line = sb.pop_line()
    assert paths == sb.HEADER_PATHS and "scr" in dash, line
    assert "failed 0" in line and "Alpha" not in line and AID not in line
    ptr = dash["scr"]
    allf = _read(os.path.join(out, ptr["file"]))
    assert set(allf["apps"]) == {AID, AID2}
    for aid in (AID, AID2):
        a = allf["apps"][aid]
        key = gu.file_key(aid)
        labels = [i[0] for i in a["items"]]
        assert any("MainActivity" in x for x in labels) and any("ListActivity" in x for x in labels)
        assert a["ft"] == (NOW.date() - timedelta(days=2)).isoformat()
        # the history reached the build: whole ads days exist and the screens carry visits and ads
        assert any(v is not None for v in a["vis"]) and any(x is not None for x in a["A"])
        f2 = _read(os.path.join(out, "scr_%s.json.gz" % key))
        assert f2["key"] == key and f2["app_id"] == aid
        assert {u[0] for u in f2["units"]} >= {"unit_a", "unit_b"}
        assert any(u[2] for u in f2["units"] if u[0] == "unit_a")       # joined to its AdMob unit by name
        fl = _read(os.path.join(out, "scr_l_%s.json.gz" % key))
        assert fl["key"] == key and fl.get("report") is not None
    for fn in os.listdir(out):
        assert sb.APP_RE.match(fn), fn
