"""KPIWINDOW: the shared period + comparison selector that drives the top KPI numbers of the Uninstall, Active
users and Install value tabs (owner: "7 days pe hi kyu? 14/30/60/custom?"), replacing the old permanent "pichhle 7
din". tests/kpiwindow_frontend.js runs the real page script in a node vm with a REAL in-memory localStorage and
checks: the pure window / comparison math (7/14/30/60/custom, the previous-period / same-month / custom
comparison baselines, validation, the "100%"-style rate display with its actual-number line, the per-day-average
count display), persistence (round-trips, survives a blocked store, a stale saved custom compare range resets to
the default), real sums against the committed Uninstall / Active fixtures (cross-checked independently here, in
Python, straight from the fixture's raw daily arrays — never reusing the page's own arithmetic), the All-apps
"common end date" fix, the retention tile's note, and that Overview / the global RANGE are never touched by any
of this. Skipped where node is not installed."""

import json
import math
import os
import re
import shutil
import subprocess
from datetime import date, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNI_FIXTURE = os.environ.get("UNINSTALL_FE_FIXTURE") or os.path.join(ROOT, "tests", "fixtures", "uninstall_sample.json")
ACT_FIXTURE = os.environ.get("ACTIVE_FE_FIXTURE") or os.path.join(ROOT, "tests", "fixtures", "active_sample.json")
VAL_FIXTURE = os.environ.get("VALUE_FE_FIXTURE") or os.path.join(ROOT, "tests", "fixtures", "value_sample.json")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
UNI_APP = "Demo Caller – Test App"


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    path = str(tmp_path_factory.mktemp("fe") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "kpiwindow_frontend.js"), path, UNI_FIXTURE, ACT_FIXTURE, VAL_FIXTURE],
                          check=True, capture_output=True, text=True, timeout=180)
    return json.loads(out.stdout)


@pytest.fixture(scope="module")
def uni_fixture():
    with open(UNI_FIXTURE, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def act_fixture():
    with open(ACT_FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def out(report, name):
    assert name in report["out"], f"scenario {name!r} did not run (see report['errors'])"
    return report["out"][name]


def jout(report, name):
    return json.loads(out(report, name))


def test_no_errors(report):
    assert report["errors"] == [], report["errors"]
    assert report["n"] > 50


# ---- pure window math --------------------------------------------------------------------------------------
def test_window_presets_7_14_30_60(report):
    wins = jout(report, "win_presets")
    for w, n in zip(wins, (7, 14, 30, 60)):
        assert w["days"] == n and not w["empty"]
        assert date.fromisoformat(w["to"]) - date.fromisoformat(w["from"]) == timedelta(days=n - 1)
        assert w["to"] == "2026-09-23"


def test_window_custom_bounds_and_clipping(report):
    assert jout(report, "win_custom_valid") == {"from": "2026-08-01", "to": "2026-08-20", "days": 20, "empty": False}
    assert jout(report, "win_custom_clip_hs")["empty"] is True   # entirely before the data starts
    assert jout(report, "win_custom_f_gt_t")["empty"] is True    # from > to
    assert jout(report, "win_custom_too_long")["empty"] is True  # > 365 days
    assert jout(report, "win_no_data")["empty"] is True
    assert jout(report, "win_hs_after_till")["empty"] is True


def test_valid_custom_messages(report):
    msgs = jout(report, "valid_custom")
    ok, swapped, no_from, no_to, too_long, same_day = msgs
    assert ok == ""
    assert "baad nahi ho sakti" in swapped
    assert no_from == "Dono dates chuno" and no_to == "Dono dates chuno"
    assert "365" in too_long
    assert same_day == ""   # a single day (from == to) is a valid 1-day custom window


def test_previous_period_same_length_and_clipped(report):
    p = jout(report, "prev_14")
    assert p == {"from": "2026-08-27", "to": "2026-09-09", "days": 14, "full": True, "empty": False}
    clipped = jout(report, "prev_clipped")   # hs cuts it short: 30-day window, only 5 days of history before it
    assert clipped["days"] == 5 and clipped["full"] is False
    assert jout(report, "prev_none_room")["empty"] is True   # hs == the main window's own from: no room at all


def test_month_shift_clamps_to_month_end(report):
    shifted = jout(report, "shift_month")
    assert shifted[0] == "2025-12-31"   # 31 Jan -> Dec has 31 days, no clamp needed
    assert shifted[1] == "2026-02-28"   # 31 Mar -> Feb 2026 (not leap) clamps to 28
    assert shifted[2] == "2028-02-29"   # 31 Mar -> Feb 2028 (leap) clamps to 29
    assert shifted[3] == "2026-04-15"   # no clamp needed at all
    mw = jout(report, "month_win")
    assert mw["from"] == "2026-07-25" and mw["to"] == "2026-08-23" and mw["days"] == 30 and mw["full"] is True
    assert jout(report, "month_win_out_of_data")["empty"] is True


def test_custom_compare_bounds(report):
    assert jout(report, "custom_cmp") == {"from": "2026-07-01", "to": "2026-07-20", "days": 20, "full": True, "empty": False}
    assert jout(report, "custom_cmp_unequal")["days"] == 14
    assert jout(report, "custom_cmp_outside")["empty"] is True


def test_compare_dispatch_picks_the_right_baseline(report):
    d = jout(report, "cmp_dispatch")
    assert d["prev"]["to"] == "2026-07-26" or d["prev"]["from"] == "2026-07-26"   # the 30 days right before the main window
    assert d["prev"]["days"] == 30
    assert d["month"]["from"] == "2026-07-25" and d["month"]["to"] == "2026-08-23"
    assert d["custom"] == {"from": "2026-06-01", "to": "2026-06-10", "days": 10, "full": True, "empty": False}


# ---- stale custom compare range resets to the default, and persists that reset -----------------------------
def test_stale_custom_compare_resets_to_prev(report):
    r = jout(report, "stale_reset")
    assert r["before"] is True   # 2020 dates are nowhere near the 2026 data: genuinely stale
    assert r["after"] == "prev"
    assert r["saved"]["cmp"] == "prev"   # the reset was persisted, not just an in-memory default


def test_custom_compare_in_range_is_kept(report):
    assert out(report, "stale_keep_in_range") == "custom"


# ---- persistence: round-trips, survives a blocked store, a bad saved value is never fatal -------------------
def test_persistence_roundtrip(report):
    r = jout(report, "persist_roundtrip")
    assert r["win"] == "30" and r["custom"] == {"from": "2026-07-01", "to": "2026-07-30"} and r["cmp"] == "month"


def test_persistence_survives_a_storage_error(report):
    r = jout(report, "persist_survives_error")
    assert r["threw"] is False   # kwSave() never lets a blocked localStorage reach the caller
    assert r["kwin"] == "60"     # and the in-memory choice for the rest of the session is unaffected


def test_persistence_survives_corrupt_json(report):
    r = jout(report, "persist_bad_json")
    assert r["threw"] is False
    assert r["win"] == "7"   # falls back to the default rather than crashing the page


# ---- COUNT tiles: always "roz ~<avg> (+/-%)"; totals only (small, grey) when the lengths differ -------------
def test_count_tile_display(report):
    equal = out(report, "cmpline_equal")
    assert equal.startswith("daily ~30 ") and "kw-avg-note" not in equal   # 900/30 = 30/day; same length -> no totals text
    assert re.search(r"\(-?\d+%\)", equal) or "−" in equal
    unequal = out(report, "cmpline_unequal")
    assert unequal.startswith("daily ~920 ")   # 27600/30 = 920/day
    assert "kw-avg-note" in unequal and "27,600" in unequal and "25,100" in unequal   # both periods' totals, in grey, because 30 != 14 days
    assert "no complete data for before" in out(report, "cmpline_missing_prev")
    assert "no data in this range" in out(report, "cmpline_missing_range")


def test_count_tile_percent_matches_per_day_average(report):
    # 920/day vs 25100/14=1792.86/day -> same % the page shows
    cur_avg, cmp_avg = 27600 / 30, 25100 / 14
    pct = round((cur_avg - cmp_avg) / abs(cmp_avg) * 100)
    assert f"({'+' if pct >= 0 else ''}{pct}%)" in out(report, "cmpline_unequal")


# ---- percent formatting: 1 decimal from 10%, 2 below 10%, no trailing zeros, never a fake "0%" ---------------
def test_percent_formatting_rules(report):
    got = jout(report, "pct_fmt")
    assert got == ["28%", "24.4%", "0.97%", "0.01%", "0%", "−9%", "10%", "5%"]
    for s in got[:-2]:
        assert not s.endswith(".0%") and not s.endswith(".00%")   # no trailing zeros
    assert got[4] == "0%"            # a real, exact zero still prints "0%"
    assert got[3] != "0%"            # a tiny but real non-zero rate never collapses to "0%"


# ---- RATE tiles (a proportion): the actual number is primary, percentages beside it, no "100 me" / "1,000 me" /
# "Matlab" text anywhere (the owner's final display rule) --------------------------------------------------
def test_rate_tile_actual_number_and_percent(report):
    t = out(report, "ratepct_period_total")
    assert t == "+186 uninstall (28%, before 22%)"          # 0.06 * 3098 ~= 185.88 -> 186
    assert "100 me" not in t and "1,000 me" not in t and "har 1,000" not in t and "Matlab" not in t


def test_rate_tile_daily_figure_for_a_recurring_rate(report):
    t = out(report, "ratepct_daily")
    assert t == "≈ +2/day uninstall (0.97%, before 0.81%)"    # (0.0097-0.0081)*(7000/7) ~= 1.6 -> 2/day; est -> ≈


def test_rate_tile_missing_and_no_base(report):
    assert "no complete data for before" in out(report, "ratepct_missing")
    assert out(report, "ratepct_no_base") == "(28%, before 22%)"   # no base given -> no actual-number part, percentages still shown


def test_rate_tile_percent_is_length_invariant(report):
    # the SAME underlying daily rates (0.0097 vs 0.0081) must give the SAME percentages whatever the compare
    # window's length is (7 / 14 / 30 days) -- the whole point of comparing a rate "per 100", never per-day
    rows = jout(report, "ratepct_len_invariant")
    assert len(set(rows)) == 1
    assert rows[0] == "(0.97%, before 0.81%)"


# ---- money-per-user RATE tiles: the actual money is a daily figure, then the per-user values -- never a % ----
def test_money_rate_tile(report):
    t = out(report, "ratemoney")
    assert t.startswith("+₹20/day (")   # (2.31-1.92) * (1_500_000/30) / 1000 = 19.5 -> 20/day
    assert "per user" in t and "%" not in t
    assert "before ₹" in t
    assert "no complete data for before" in out(report, "ratemoney_missing")


# ---- plain continuous averages (sessions/user, time/user, purane users roz): before -> after with a plain % --
def test_plain_average_tile(report):
    assert out(report, "rateavg") == "2.1 → 2.3 (+10%)"
    assert "no complete data for before" in out(report, "rateavg_missing")


def test_pool_sums_skips_missing_apps_never_a_fake_zero(report):
    p = jout(report, "pool_sums")
    assert p["ins"] == 30 and p["outs"] == 4 and p["net"] == 26   # the null entry contributes nothing, not a 0
    assert p["rate"] == 5 and p["rA"] == 2000


# ---- the retention tile ("7 din baad bhi app me") is judged on settled install weeks -- never this selector --
def test_retention_tile_note_present(report):
    app_card = out(report, "uni_retention_note_app")
    assert "install hafte ke hisaab se" in app_card and "upar ka chunav ispe nahi" in app_card
    pool = out(report, "uni_retention_note_pool")
    assert "install hafte ke hisaab se" in pool and "upar ka chunav ispe nahi" in pool


# ---- common end date: every visible app pooled to the SAME end day (the min data_till), never each app's own
# last-N-days (the bug the owner's spec names) -----------------------------------------------------------------
def test_common_end_date(report):
    r = jout(report, "uni_common_till")
    assert r["to0"] == r["to1"] == r["common"]
    assert r["html_has_note"] is True


# ---- real sums, independently recomputed from the fixture's own raw daily arrays (never reusing the page's
# own arithmetic) -- Uninstall: a window's sums, and its previous-period's sums -------------------------------
def _uni_app(fx, name):
    return next(a for a in fx["asset"]["apps"] if a["app"] == name)


def _direct_uni_sum(app, frm, to):
    start = date.fromisoformat(app["daily"]["start"])
    i0, i1 = (date.fromisoformat(frm) - start).days, (date.fromisoformat(to) - start).days
    new, un = app["daily"]["new"], app["daily"]["un"]
    ins = sum(v for v in new[i0:i1 + 1] if v is not None)
    outs = sum(v for v in un[i0:i1 + 1] if v is not None)
    return ins, outs


def test_uninstall_window_sums_match_the_fixture(uni_fixture, report):
    app = _uni_app(uni_fixture, UNI_APP)
    by_n = jout(report, "uni_app_sums")
    for n in ("7", "14", "30", "60"):
        w, sm = by_n[n]["w"], by_n[n]["sm"]
        want_ins, want_outs = _direct_uni_sum(app, w["from"], w["to"])
        assert sm["ins"] == want_ins and sm["outs"] == want_outs and sm["net"] == want_ins - want_outs, n


def test_uninstall_previous_period_sums_match_the_fixture(uni_fixture, report):
    app = _uni_app(uni_fixture, UNI_APP)
    by_n = jout(report, "uni_app_sums")
    for n in ("7", "14", "30", "60"):
        cw, csm = by_n[n]["cmp"]["w"], by_n[n]["cmp"]["sm"]
        assert cw["days"] == int(n)   # plenty of history before this app's window (history_start is far enough back)
        want_ins, want_outs = _direct_uni_sum(app, cw["from"], cw["to"])
        assert csm["ins"] == want_ins and csm["outs"] == want_outs, n


# ---- Active: the app-page KPI row's window sums, respecting the existing "settled days only" clip -------------
def test_active_window_sums_match_the_fixture(act_fixture, report):
    key = next(iter(act_fixture["app_files"]))
    d = act_fixture["app_files"][key]
    start = date.fromisoformat(d["daily"]["start"])
    settled = date.fromisoformat(d["settled_till"])
    by_n = jout(report, "act_app_sums")
    for n in ("7", "14", "30", "60"):
        w, S = by_n[n]["w"], by_n[n]["S"]
        frm = date.fromisoformat(w["from"])
        to = min(date.fromisoformat(w["to"]), settled)   # the page clips to settled days, same as before KPIWINDOW
        assert S["to"] == to.isoformat()
        i0, i1 = (frm - start).days, (to - start).days
        ret, newv = d["daily"]["ret"], d["daily"]["new"]
        want_r = sum(v for v in ret[i0:i1 + 1] if v is not None)
        want_nr = sum(1 for v in ret[i0:i1 + 1] if v is not None)
        want_nw = sum(v for v in newv[i0:i1 + 1] if v is not None)
        assert S["R"] == want_r and S["nR"] == want_nr and S["nw"] == want_nw, n


# ---- rendering: every preset + a custom range + an invalid custom range, on both tabs' app pages and the
# portfolio, with every compare baseline -- no crash, no "undefined", no "NaN" ----------------------------------
BAD_TEXT = re.compile(r"undefined|\bNaN\b")


@pytest.mark.parametrize("name", ["uni_detail_7", "uni_detail_14", "uni_detail_30", "uni_detail_60", "uni_detail_custom",
                                   "uni_portfolio_30", "uni_portfolio_month_cmp", "uni_portfolio_custom_cmp",
                                   "act_detail_7", "act_detail_14", "act_detail_30", "act_detail_60",
                                   "act_portfolio_30", "act_portfolio_14_custom_cmp",
                                   "val_portfolio_30", "val_detail_30"])
def test_renders_clean(report, name):
    html = out(report, name)
    assert html and not BAD_TEXT.search(html), name


def test_invalid_custom_range_shows_the_hinglish_message_not_a_crash(report):
    html = out(report, "uni_detail_custom_invalid")
    assert "baad nahi ho sakti" in html and not BAD_TEXT.search(html)


def test_the_selector_appears_on_all_three_tabs(report):
    for name in ("uni_portfolio_30", "act_portfolio_30", "val_portfolio_30"):
        html = out(report, name)
        assert "14 days" in html and "30 days" in html and "60 days" in html and "Custom" in html
        assert "Ye chunav sirf upar ke numbers ke liye" in html


def test_value_judged_card_is_unaffected_by_the_window(report):
    r = jout(report, "val_detail_7_vs_30_pay_unchanged")
    assert r["same"] is True


# ---- other tabs / the global RANGE: never touched by any of this ----------------------------------------------
def test_overview_window_math_unaffected(report):
    r = jout(report, "overview_unaffected")
    assert r["same"] is True and r["range_after"] == "30d"


def test_range_global_never_mutated(report):
    assert out(report, "range_not_mutated_by_kw") == "90d"


def test_kpi_bands_never_say_per_1000_owner_rule():
    # owner (1 Oct): "100 me / har 1,000 me" is backend formula — the KPI bands show the actual number + a percent,
    # money as per user; never "har 1,000 users" / "Per 1,000 users" / "Kamai har 1,000 users se"
    import pathlib
    s = pathlib.Path(__file__).resolve().parents[1].joinpath("frontend", "index.html").read_text()
    uni = s[s.index("kpi('📊 Uninstall rate'"):][:400]
    assert "kwPct(P.rate/1000)" in uni and "har 1,000" not in uni
    assert "💵 Revenue per user ≈" in s and "💵 Per 1,000 users ≈" not in s
    assert "tile('arpdau','Revenue per user (/day)'" in s and "tile('arpdau','Kamai har 1,000 users se (roz)'" not in s
    assert "S1.rv*1000/S1.ra" not in s and "A.rv*1000/A.ra" not in s
