"""QA for the baseline report engine (Step 3)."""

from admob_iq.db import nest_monthly, nest_daily
from admob_iq.engine.baseline_report import build_baseline, build_daily_series, build_country_yday


def _cell(unit, country, month, days, req, matched, impr, clicks, earn,
          ctr_min, ctr_max, ec_min, ec_max):
    return dict(ad_unit_id=unit, app_id="app-1", app_name="App", unit_name=unit,
                country=country, month=month, days=days, ad_requests=req,
                matched_requests=matched, impressions=impr, clicks=clicks,
                estimated_earnings_micros=earn, ctr_min=ctr_min, ctr_max=ctr_max,
                match_min=0.9, match_max=0.95, show_min=0.9, show_max=0.95,
                ecpm_min=ec_min, ecpm_max=ec_max, ctr_avg=clicks / impr,
                match_avg=matched / req, show_avg=min(1, impr / matched),
                ecpm_avg=earn / 1e6 / impr * 1000)


def test_baseline_range_trend_and_status():
    # one unit, one country (US), 3 months of eCPM rising 4 -> 5 -> 9 (last is ABOVE the 4-5 range)
    cells = [
        _cell("U1", "US", "2026-04", 30, 10000, 9000, 8000, 80, 32_000_000, 0.008, 0.012, 3.5, 4.5),  # ecpm 4.0
        _cell("U1", "US", "2026-05", 30, 10000, 9000, 8000, 80, 40_000_000, 0.008, 0.012, 4.5, 5.5),  # ecpm 5.0
        _cell("U1", "US", "2026-06", 30, 10000, 9000, 8000, 80, 72_000_000, 0.008, 0.012, 8.5, 9.5),  # ecpm 9.0
    ]
    acm = nest_monthly({"units": {}, "data": {}}, cells)
    acd = nest_daily([])
    rep = build_baseline(acm, acd, active_since="2026-01")
    assert len(rep["units"]) == 1
    u = rep["units"][0]
    assert u["months_n"] == 3 and u["countries_n"] == 1
    # standard range = min→max of the PRIOR months' avg eCPM (4.0 .. 5.0); latest (9) is judged vs it
    lo, hi = u["range"]["ecpm"]
    assert round(lo, 1) == 4.0 and round(hi, 1) == 5.0           # baseline = prior months only
    assert u["latest"]["ecpm"] == 9.0 and u["latest"]["month"] == "2026-06"
    assert u["status"]["ecpm"] == "above"                        # latest is above the standard range
    # market trend has a point per month
    assert rep["market"]["months"] == ["2026-04", "2026-05", "2026-06"]
    assert rep["market"]["ecpm"][-1] == 9.0
    # per-country row present with its own range (now shipped separately in unit_geo)
    assert rep["unit_geo"][u["id"]][0]["country"] == "US"
    assert rep["apps"]["App"]["by_country"][0]["country"] == "US"    # option A: app-level country view


def test_status_flags_movement_out_of_range():
    # 3 stable months (~5.0) then a 4th that CRASHES to 2.0 -> 'below' the standard range
    cells = [_cell("U1", "US", f"2026-0{m}", 30, 10000, 9000, 8000, 80, 40_000_000, 0.008, 0.012, 4.9, 5.1)
             for m in (2, 3, 4)]
    cells.append(_cell("U1", "US", "2026-05", 30, 10000, 9000, 8000, 80, 16_000_000, 0.008, 0.012, 1.9, 2.1))  # ecpm 2.0
    acm = nest_monthly({"units": {}, "data": {}}, cells)
    rep = build_baseline(acm, nest_daily([]), active_since="2026-01")
    u = rep["units"][0]
    assert u["latest"]["ecpm"] == 2.0
    assert u["status"]["ecpm"] == "below"          # latest is below the ~5.0 standard range


def test_low_sample_flagged_not_excluded():
    # a tiny country (few impressions/month) must still appear, just labelled low_sample
    big = _cell("U1", "US", "2026-05", 30, 100000, 90000, 80000, 800, 400_000_000, 0.008, 0.012, 4.5, 5.5)
    tiny = _cell("U1", "ZW", "2026-05", 5, 50, 40, 30, 1, 20_000, 0.02, 0.05, 0.5, 0.8)
    acm = nest_monthly({"units": {}, "data": {}}, [big, tiny])
    rep = build_baseline(acm, nest_daily([]), active_since="2026-01")
    uid = rep["units"][0]["id"]
    countries = {c["country"]: c for c in rep["unit_geo"][uid]}
    assert "ZW" in countries and "US" in countries          # nobody excluded (all countries)
    assert countries["ZW"]["low_sample"] and not countries["US"]["low_sample"]


def _net(unit, day, req, matched, impr, clicks, earn_micros, name="u", app="App"):
    return dict(ad_unit_id=unit, report_date=day, unit_name=name, app_name=app,
                ad_requests=req, matched_requests=matched, impressions=impr,
                clicks=clicks, estimated_earnings_micros=earn_micros)


def test_daily_series_derives_all_metrics_from_network():
    # two days for one unit; rates derived from raw counts, eCPM from earnings/impressions*1000
    rows = [
        _net("U1", "2026-07-27", 1000, 900, 800, 40, 4_000_000),   # match .9 show .888.. ctr .05 ecpm 5.0
        _net("U1", "2026-07-28", 2000, 1000, 500, 25, 5_000_000),  # match .5 show .5    ctr .05 ecpm 10.0
    ]
    out = build_daily_series(rows)
    r = out["U1"]
    assert r["d"] == ["2026-07-27", "2026-07-28"]                  # ascending
    assert r["name"] == "u" and r["app"] == "App"
    assert r["rev"] == [4.0, 5.0] and r["req"] == [1000, 2000]
    assert round(r["match"][0], 3) == 0.9 and r["match"][1] == 0.5
    assert r["show"][1] == 0.5 and round(r["ctr"][1], 3) == 0.05
    assert r["ecpm"] == [5.0, 10.0]                                # (earn/1e6)/impr*1000


def test_daily_series_null_on_zero_impressions_and_keep_filter():
    rows = [
        _net("U1", "2026-07-28", 500, 0, 0, 0, 0),                 # no fill: rates that need impr/matched are null
        _net("U2", "2026-07-28", 100, 90, 80, 4, 800_000),        # a different unit, filtered out below
    ]
    out = build_daily_series(rows, keep_ids={"U1"})
    assert set(out) == {"U1"}                                      # keep_ids limits to reachable units
    r = out["U1"]
    assert r["rev"] == [0.0] and r["req"] == [500]                # revenue/requests always present
    assert r["ecpm"] == [None] and r["ctr"] == [None] and r["show"] == [None]  # 0 impressions ⇒ blank, not fake 0
    assert r["match"] == [0.0]                                     # match uses ad_requests (present) ⇒ real 0


def _drow(unit, country, day, req, matched, impr, clicks, earn):
    return dict(ad_unit_id=unit, country=country, report_date=day, app_id="a",
                app_name="App", unit_name="u", ad_requests=req, matched_requests=matched,
                impressions=impr, clicks=clicks, estimated_earnings_micros=earn)


def test_country_yday_uses_last_complete_day():
    # the newest date is today (partial) → 'yesterday' must be the prior day, per country
    rows = [
        _drow("U1", "US", "2026-07-27", 1000, 900, 800, 40, 4_000_000),  # yesterday: ctr .05, ecpm 5.0
        _drow("U1", "US", "2026-07-28", 10, 5, 2, 0, 0),                 # today (partial) — must be ignored
        _drow("U1", "IN", "2026-07-27", 500, 0, 0, 0, 0),               # no fill ⇒ impression-based rates null
    ]
    acd = nest_daily(rows)
    day, ymap = build_country_yday(acd)
    assert day == "2026-07-27"                                          # not the partial 28th
    us = ymap["U1"]["US"]
    assert us["rev"] == 4.0 and round(us["ctr"], 3) == 0.05 and us["ecpm"] == 5.0 and round(us["match"], 2) == 0.9
    inn = ymap["U1"]["IN"]
    assert inn["show"] is None and inn["ctr"] is None and inn["ecpm"] is None  # 0 impressions ⇒ blank
    assert inn["match"] == 0.0                                          # ad_requests present ⇒ real 0
