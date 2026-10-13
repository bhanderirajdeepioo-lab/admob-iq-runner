"""🆕 First open tab — the build step (admob_iq.firstopen_build), on made-up stores: every day of every store in one lazy
file (nothing trimmed), the status rule (last 7 final days vs the 28 before: Worse / Watch / Better / Normal, Too early,
N/A), the pointer the hub reads, one splat header rule, the switch, failure isolation and a counts-only line."""
import gzip
import json
import os
from datetime import date, datetime, timedelta, timezone

from admob_iq import firstopen_build as fb
from admob_iq.db import write_json_gz_stable
from admob_iq.fetch import ga4_firstopen as gf

NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)


def _store(data, aid, days, home7, home28, splash=1000, langs=True):
    """`days` days to 13 Oct; Home = home7 × Splash on the last 7 final days (≤ 11 Oct), home28 before."""
    d0 = date(2026, 10, 13) - timedelta(days=days - 1)
    recs = {}
    for i in range(days):
        d = d0 + timedelta(days=i)
        last7 = date(2026, 10, 5) <= d <= date(2026, 10, 11)
        h = round(splash * (home7 if last7 or d > date(2026, 10, 11) else home28))
        recs[d.isoformat()] = dict(first_open=splash + 20, splash=splash, home=h, splash_any=splash, home_any=h,
                                   **({"language": splash // 2} if langs else {}))
    s = {"v": gf.STORE_V, "app_id": aid, "package": "com.example." + aid[-1], "time_zone": "Asia/Kolkata",
         "steps": {"splash": "SplashActivity", "home": "MainActivity", **({"language": "LanguageActivity"} if langs else {})},
         "days": recs}
    write_json_gz_stable(gf.store_path(data, aid), s)


def test_file_status_pointer_and_header(tmp_path):
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    os.makedirs(os.path.join(data, gf.DIR)); os.makedirs(out)
    _store(data, "a~1", 60, 0.50, 0.60)          # −10 pts → Worse
    _store(data, "a~2", 60, 0.57, 0.60)          # −3 → Watch
    _store(data, "a~3", 60, 0.70, 0.60)          # +10 → Better
    _store(data, "a~4", 60, 0.61, 0.60)          # +1 → Normal
    _store(data, "a~5", 20, 0.61, 0.60)          # 20 days → Too early
    _store(data, "a~6", 60, 0.61, 0.60, splash=10)   # 70 Splash in 7 days → N/A
    dash = {"uninstall": {"apps": [{"app_id": "a~1", "app": "Alpha App"}]}}
    paths = fb.run(dash, data, out, {}, now=NOW)
    assert paths == ["/firstopen*"]
    with gzip.open(os.path.join(out, fb.FILE), "rt", encoding="utf-8") as f:
        body = json.load(f)
    st = {x["key"]: x["status"] for x in body["summary"]}
    from admob_iq.fetch import ga4_uninstall as gu
    assert [st[gu.file_key("a~%d" % i)] for i in range(1, 7)] == ["Worse", "Watch", "Better", "Normal", "Too early", "N/A"]
    a1 = next(x for x in body["summary"] if x["app"] == "Alpha App")
    assert abs(a1["s2h"] - 0.5) < 1e-6 and abs(a1["usual"] - 0.6) < 1e-6 and abs(a1["change"] + 0.1) < 1e-6
    assert a1["steps"]["language"] == [0.5, 0.5] and a1["final_days"] == 58 and abs(a1["fo_day"] - 1020) < 1e-6
    app1 = next(x for x in body["apps"] if x["app"] == "Alpha App")
    assert len(app1["days"]) == 60 and app1["days"][0][0] == "2026-08-15" and app1["final_till"] == "2026-10-11"   # nothing trimmed
    assert app1["days"][0][1:4] == [1020, 1000, 600] and app1["days"][0][-1] is None and a1["sample"] is None
    assert dash["firstopen"]["file"] == fb.FILE and dash["firstopen"]["apps"]["Alpha App"]["status"] == "Worse"
    assert dash["firstopen"]["apps"]["Alpha App"]["id"] == "a~1"
    line = fb.pop_line()
    assert line.startswith("first open: apps 6, days ") and "worse 1, watch 1, better 1, normal 1, too early 1, n/a 1" in line
    assert "Alpha" not in line and "example" not in line


def test_no_store_and_switch_off_leave_no_file(tmp_path):
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    os.makedirs(out)
    open(os.path.join(out, fb.FILE), "w").close()
    dash = {"firstopen": {"file": "old"}}
    assert fb.run(dash, data, out, {}, now=NOW) == [] and "firstopen" not in dash and not os.path.exists(os.path.join(out, fb.FILE))
    open(os.path.join(out, fb.FILE), "w").close()
    fb.off(out)
    assert not os.path.exists(os.path.join(out, fb.FILE)) and fb.enabled({}) and not fb.enabled({"firstopen_tab": False})
