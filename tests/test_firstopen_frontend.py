"""🆕 First open tab — the page side. tests/firstopen_frontend.js runs the FO module of frontend/index.html for real (a node
vm, stub page helpers) on SYNTHETIC data made up there; checked here: the pointer check, the lazy file (a failed load +
Try again), All apps (status chips, Worse first, a column sort, the chip filter that never pulls the page up, hidden apps
left out, the App picker's names), one app (Today / Yesterday / 7 days / usual, the steps, every month, every day with
not-final days and GA4 sampling marked), the hub card from the pointer, and the wiring into the page (nav, hub tab and
card, show(), the Period picker hidden); BY COUNTRY: the Country control (All + top 6 + every country in a <select>), the
country file loaded once and only for the open app (a failed load = Try again in the country area only), the board
(sort, status filter, the GA4-unnamed row last), a pick (chip / board row / select) redrawing the view from the country's
rows with the page height and the board's scroll kept, the pick kept across apps (+ the "no such country" message), and the
All countries view = today's view + the two country blocks; a country file with a HOLE (the date range, one warning on
the board and in the country view, a "gap" row in Every day, the chart's rows on the calendar); the Country control's one
height (one row, two on a phone; the top 6 in a sideways strip); hold() keeping the reader's place when the country file
arrives late (a layout model at 375 and 1280 px). Skipped where node is not installed. No real data."""
import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
PAGE = os.path.join(ROOT, "frontend", "index.html")


def _page():
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def out():
    if NODE is None:
        pytest.skip("node is not installed")
    r = subprocess.run([NODE, os.path.join(ROOT, "tests", "firstopen_frontend.js"), PAGE],
                       check=True, capture_output=True, text=True, timeout=120)
    rep = json.loads(r.stdout)
    assert not rep["errors"], rep["errors"]
    return rep["out"]


def test_pointer_and_lazy_load(out):
    assert out["no_ptr"] and out["bad_file"] and out["ptr"]
    assert out["loads_before_open"] == 0                       # the hub card never loads the file
    assert out["fail_html"] and out["loads"] == 2              # a failed load shows Try again; the tap loads again
    assert out["no_ptr_note"]


def test_all_apps(out):
    assert out["all_chips"] == [["Worse", 1], ["Watch", 0], ["Better", 1], ["Normal", 1], ["Too early", 0], ["N/A", 0]]
    assert out["all_rows"] == ["Alpha Pick", "Beta Pick", "Gamma"] and not out["all_hidden"]   # Worse first; the picker's names
    assert out["all_icons"] == [["id-a", "Alpha Pick", "Alpha Pick"], ["id-b", "Beta Pick", "Beta Pick"], ["id-c", "Gamma", "Gamma"]]   # every name with its own logo
    assert out["all_smp"] and out["all_zero_pts"]
    assert out["sort_rows"] == ["Beta Pick", "Gamma", "Alpha Pick"]
    assert out["filt_rows"] == ["Alpha Pick"] and out["filt_minh"] == "900px"   # the page keeps its height (no jump)
    assert out["filt_empty"] and out["filt_off_rows"] == 3
    assert out["row_tap"] == ["Alpha Pick"]


def test_one_app(out):
    assert out["app_mini"]
    assert out["app_months"] == [["Sep 2026", 29, "3,480"], ["Aug 2026", 31, "3,720"]]   # every month, newest first
    assert out["app_days"] == 60                                                         # every day, nothing trimmed
    assert out["app_first_day_row"] and out["app_changed"] and out["app_smp_note"]
    assert not out["app_lang_col"] and out["alpha_lang_col"] and out["alpha_steps"]
    assert out["app_missing"]


def test_hub_card(out):
    assert out["card_alpha"] == {"st": "bigda", "line": "Splash → Home <b>50%</b> · usual 60% (−10 pts)"}
    assert out["card_gamma"]["line"].endswith("(0 pts)") and out["card_gamma"]["st"] == "normal"
    assert out["card_none"]["st"] == "lagu"


def test_wiring():
    p = _page()
    assert '<li id="nav-fo-li" hidden><button data-screen="firstopen">' in p
    assert "li.hidden=!FO.ptr()" in p and "root.append(renderFirstOpen())" in p
    assert "if(id==='firstopen') FO.show();" in p
    assert re.search(r"firstopen:\['First open','🆕','firstopen','firstopen'\]", p)
    assert re.search(r"const HUB_ALL=\[[^\]]*'firstopen'", p) and re.search(r"const HUB_APP=\[[^\]]*'firstopen'", p)
    assert "(t!=='firstopen'||fo)" in p and "(c[0]!=='firstopen'||fo)" in p
    assert "['firstopen','firstopen','First open','🆕','fo']" in p and "if(src==='fo')" in p
    assert 'body[data-screen="firstopen"] #rangectl' in p
    assert "firstopen:[\"First open\"," in p


# ── by country ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_country_control_and_lazy_file(out):
    c = out["cc"]
    assert c["loading_ctl"] and c["view_at_once"]                 # the rest of the app view at once, from the main file
    assert c["loads_main"] == 1 and c["loads_b"] == 1 and c["loads_other"] == 0   # only the open app's country file
    assert c["chips"] == [["", "true"], ["XA", "false"], ["XB", "false"], ["XC", "false"], ["XD", "false"], ["XE", "false"],
                          ["XF", "false"]]                         # All countries + the top 6, in the file's order
    assert c["chip_xa"]                                            # flag + code, the name on hover
    assert [v for v, _ in c["select"]] == ["", "XA", "XB", "XC", "XD", "XE", "XF", "XG", "XH", "XI"]   # EVERY country
    assert c["select"][1][1] == "[XA] Name XA · 500 / day" and c["select"][-1][1] == "[XI] Name XI · 0.4 / day"
    assert c["select_placeholder"]


def test_country_board(out):
    c = out["cc"]
    assert c["board_rows"] == ["XA", "XB", "XC", "XD", "XE", "XF", "XG", "XH", "XI"] and c["board_unnamed_last"]
    assert c["board_chips"] == [["Worse", 1], ["Watch", 1], ["Better", 1], ["Normal", 1], ["Too early", 0], ["N/A", 5]]
    assert c["board_cells_xa"] and c["board_cells_xi"] and c["board_note"] and c["board_no_gap_note"]
    assert c["sort_s2h"][:3] == ["XB", "XC", "XA"] and c["sort_unnamed_last"]
    assert c["filt_rows"] == ["XE", "XF", "XG", "XH", "XI"] and c["filt_no_unnamed"] and c["filt_minh"] == "900px"
    assert c["filt_empty"] and c["filt_off"] == 9


def test_all_countries_view_is_todays_plus_the_country_blocks(out):
    c = out["cc"]
    assert c["all_plus_two"] and c["nocc_plain"] and c["top_under_crumb"] and c["board_after_grid"]


def test_country_pick(out):
    c = out["cc"]
    assert c["pick_cc"] == "XB" and c["pick_loads"] == 1 and c["pick_minh"] == "900px"   # no reload, no jump
    assert c["pick_crumb"] and c["pick_chip_on"] and c["pick_mini"] and c["pick_no_late"] and c["pick_steps"]
    assert c["pick_note"] and c["pick_no_gap"]                    # the date range first – last; no hole, no warning
    assert c["pick_months"] == [["Sep 2026", "29", "8,700", "7,250", "5,800", "80%", "83%"],
                                ["Aug 2026", "31", "9,300", "7,750", "6,200", "80%", "83%"]]
    assert c["pick_month_smp"] and c["pick_days"] == 60 and c["pick_nf"] and c["pick_smp_day"] and c["pick_board_on"]
    assert c["row_cc"] == "XH" and c["row_scroll"] == 333 and c["row_minh"] == "900px" and c["row_select_on"]
    assert c["sel_cc"] == "XG" and c["sel_view"]


def test_country_kept_across_apps_and_failed_load(out):
    c = out["cc"]
    assert c["g_loading"] and c["g_loads"] == 1 and c["g_missing"] and c["g_picker"] == ["", "XA", "XB"]
    assert c["a_missing"] and c["back_b"]
    assert c["x_cc"] == "" and c["x_all"]
    assert c["f_retry_in_area"] and c["f_rest"] and c["f_loading"] and c["f_loads"] == 2 and c["f_ok"]
    assert c["f_range_fallback"] and c["strip"]


def test_country_file_with_a_hole(out):
    """The backfill reads oldest / newest in turn and a fetch can fall behind: the page says so (never a silent "last 7
    days"), shows the hole between the days, and the chart breaks there."""
    c = out["cc"]
    assert c["g_warn"] and c["g_why"] and c["g_view_warn"]
    assert c["g_gap_rows"] == ["↕ gap: 20 din nahi padhe (21 Aug – 9 Sep) — upar aur neeche ke din lagatar nahi"]
    assert c["g_gap_between"] and c["g_days"] == 40 and c["g_months"] == [["Sep 2026", 20], ["Aug 2026", 20]]
    assert c["g_fill"] == [60, 20, "2026-08-21", None, "2026-09-10", 500]   # the chart on the calendar: 20 empty days


def test_late_country_file_keeps_the_readers_place(out):
    """hold() on a layout model (sticky top bar, block heights, scrollY) at 375 and 1280 px: the board's slot grows by the
    board while the owner reads — Every month just under the top bar (the old rule kept a strip of the chart and pushed the
    card down by the whole board) or mid-screen, Every day far below: none moves; at the top of the page nothing scrolls;
    the slot in the lower half: the chart stays and the board comes below it."""
    for w in ("375", "1280"):
        h = out["hold"][w]
        assert abs(h["month_under_bar"]) <= 1 and abs(h["month_mid"]) <= 1 and abs(h["day_far"]) <= 1, (w, h)
        assert h["top"]["y"] == 0 and h["top"]["mini"] == 0, (w, h)
        assert h["slot_low"]["y"] == 0 and h["slot_low"]["grid"] == 0, (w, h)


def test_country_wiring():
    p = _page()
    assert r"/^firstopen_cc_[0-9a-f]{12}\.json\.gz$/" in p      # the build's file name (key = sha1-12 of the app id)
    assert ".screen[data-screen=\"firstopen\"]{overflow-anchor:none}" in p
    # the Country control has ONE height in every state (loading, failed, loaded): 36px, 80px (two rows) on a phone
    assert ".fo-cc{display:flex;flex-wrap:nowrap;align-items:center;gap:8px;margin:0 0 12px;height:36px;min-width:0}" in p
    assert ".fo-cc{display:grid;grid-template-columns:auto auto minmax(0,1fr);grid-template-rows:36px 36px;height:80px}" in p
    assert ".fo-ccr{display:flex;flex:0 1 auto;gap:8px;min-width:0;height:36px;overflow-x:auto;" in p
