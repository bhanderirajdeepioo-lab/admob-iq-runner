"""📈 eCPM "same time yesterday" store (admob_iq/intraday_build.py), on SYNTHETIC data only: each build's point of
today's totals so far, by minute of the day in the report time zone; 8 days kept; the page payload; never for the
sample data; failure-isolated."""
import json
import os
from datetime import datetime, timezone

from admob_iq import intraday_build as ib

TZ = "Asia/Kolkata"            # UTC+5:30


def _dash(today, rows_by_app, demo=False):
    pl = []
    for app, rows in rows_by_app.items():
        pl.append({"id": "u-" + app, "app": app, "daily": [[d, e, i, 0, 0, 0] for d, e, i in rows]})
    return {"today_date": today, "placements": pl, "is_demo": demo}


def _utc(h, m, day=6):
    return datetime(2026, 10, day, h, m, tzinfo=timezone.utc)


def test_points_by_local_minute_and_per_app(tmp_path):
    d = _dash("2026-10-06", {"Alpha": [("2026-10-05", 9_000_000, 3000), ("2026-10-06", 2_000_000, 1000)],
                             "Beta": [("2026-10-06", 1_000_000, 500)], "Idle": [("2026-10-06", 0, 0)]})
    st = ib.record(d, str(tmp_path), TZ, now=_utc(4, 30))            # 04:30 UTC = 10:00 IST
    pt = st["days"]["2026-10-06"]
    assert pt == [[600, 3_000_000, 1500, {"Alpha": [2_000_000, 1000], "Beta": [1_000_000, 500]}]]   # yesterday's row left out
    assert st["tz"] == TZ and st["since"] == "2026-10-06"
    # a second build later the same day adds a point; the same minute again replaces it
    d["placements"][0]["daily"][1][1:3] = [4_000_000, 2000]
    ib.record(d, str(tmp_path), TZ, now=_utc(5, 30))
    d["placements"][0]["daily"][1][1:3] = [4_500_000, 2100]
    st = ib.record(d, str(tmp_path), TZ, now=_utc(5, 30))
    assert [p[0] for p in st["days"]["2026-10-06"]] == [600, 660] and st["days"]["2026-10-06"][1][1:3] == [5_500_000, 2600]
    with open(tmp_path / "ecpm_intraday.json", encoding="utf-8") as f:
        assert json.load(f) == st


def test_keeps_eight_days_and_payload(tmp_path):
    for day in range(1, 11):
        d = _dash("2026-10-%02d" % day, {"Alpha": [("2026-10-%02d" % day, day * 1_000_000, day * 100)]})
        st = ib.record(d, str(tmp_path), TZ, now=_utc(6, 0, day))
    assert sorted(st["days"]) == ["2026-10-%02d" % k for k in range(3, 11)] and st["since"] == "2026-10-01"
    pl = ib.payload(st, "2026-10-10")
    assert (pl["today"], pl["yday"]) == ("2026-10-10", "2026-10-09")
    assert pl["t"] == [[690, 10_000_000, 1000]] and pl["y"] == [[690, 9_000_000, 900]]     # 06:00 UTC = 11:30 IST
    assert pl["apps"]["Alpha"] == {"t": [[690, 10_000_000, 1000]], "y": [[690, 9_000_000, 900]]}


def test_step_attaches_payload_never_for_demo_and_survives_a_bad_store(tmp_path):
    d = _dash("2026-10-06", {"Alpha": [("2026-10-06", 1_000_000, 100)]})
    ib.step(d, str(tmp_path), TZ, now=_utc(4, 30))
    assert d["ecpm_intraday"]["t"] == [[600, 1_000_000, 100]]
    line = ib.pop_line()
    assert line == "ecpm intraday: 1 points today, 0 yesterday, 1 days kept" and not any(c.isalpha() and c.isupper() for c in line)
    demo = _dash("2026-10-06", {"Alpha": [("2026-10-06", 1, 1)]}, demo=True)
    ib.step(demo, str(tmp_path / "demo"), TZ, now=_utc(4, 30))
    assert "ecpm_intraday" not in demo and not os.path.exists(tmp_path / "demo" / "ecpm_intraday.json")
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "ecpm_intraday.json").write_text("{not json", encoding="utf-8")
    d2 = _dash("2026-10-06", {"Alpha": [("2026-10-06", 1_000_000, 100)]})
    ib.step(d2, str(tmp_path / "bad"), TZ, now=_utc(4, 30))           # a broken file: a fresh store, not a failure
    assert d2["ecpm_intraday"]["t"] == [[600, 1_000_000, 100]]
    broken = {"today_date": "2026-10-06", "placements": [{"app": "A", "daily": [["2026-10-06", "x", 1]]}]}
    ib.step(broken, str(tmp_path / "x"), TZ, now=_utc(4, 30))
    assert "ecpm_intraday" not in broken and ib.pop_line() == "ecpm intraday skipped: ValueError"
