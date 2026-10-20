"""📈 ROI (a section of 💸 Install value) — the page side. tests/roi_frontend.js runs the ROI module + roiWrap of
frontend/index.html for real (a node vm, stub page helpers) on SYNTHETIC data made up there; checked here: where the block
goes, the day-by-day columns and their fallback to the checkpoints, past D30 every 30 days up to the app's age (the
cohort cube's m: columns, finality, week / month, title + note, breakeven / so far; the cube still on its way: only a
note; a file without m: the checkpoints), Today / Yesterday, week / month rows (complete days only), the four cell kinds, breakeven, the KPI tiles, the countries board
(order, what cutting saves), lifetime P/L (totals to the day both sides are in), All apps (icons, Worse first, hidden apps out), the hub card line, the four forms
of ROI (hero block, ranges printed from the file, GA4-measured paid split, budget call, mostly-organic flag, All-apps
table), 🌍 the install-day table by country (the picker, a pack read once, the same table for one country, the default
view byte for byte as before, the pick kept, the missing-country / error / retry / busy states, the notes, a short row
expanded exactly as the build's _zrow, no page jump at 375 and 1280 px; a pack of another build / gone from the site:
the app file read again once; a late pack never repaints; only 3 packs kept; Not split's columns; the notes' measured
limits), and the wiring into the page. Skipped where node is not installed. No real data."""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
PAGE = os.path.join(ROOT, "frontend", "index.html")


def _zrow_cases(path):
    """The build's own short-row rule (roi_build._zrow) on made-up days, for the page's zx to match exactly."""
    from datetime import date, timedelta

    from admob_iq import roi_build as rb
    thru, fthru = date(2026, 10, 13), date(2026, 10, 10)
    unk = [["2025-01-01", "2025-08-31"], ["2026-10-13", "2026-10-13"]]
    cases = []
    for billed in (1, 0):
        for back in (0, 1, 2, 3, 4, 29, 30, 33, 34, 60, 62, 63, 64, 90, 93, 200, 365, 400, 500, 650):
            X = thru - timedelta(days=back)
            u = any(a <= X.isoformat() <= b for a, b in unk)
            for cc in ("AA", "--", "XX"):
                cases.append({"x": X.isoformat(), "cc": cc,
                              "row": rb._row_out(rb._zrow(X, thru, fthru, u, cc, bool(billed))), "billed": billed})
    by = {}
    for c in cases:
        by.setdefault(c.pop("billed"), []).append(c)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"cd": {"thru": thru.isoformat(), "fthru": fthru.isoformat(), "geo": {"unk": unk, "billed": 1}},
                   "cases": by[1], "cd0": {"thru": thru.isoformat(), "fthru": fthru.isoformat(),
                                           "geo": {"unk": unk, "billed": 0}}, "cases0": by[0]}, f)


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    if NODE is None:
        pytest.skip("node is not installed")
    zc = str(tmp_path_factory.mktemp("zx") / "zrow.json")
    _zrow_cases(zc)
    r = subprocess.run([NODE, os.path.join(ROOT, "tests", "roi_frontend.js"), PAGE, zc],
                       check=True, capture_output=True, text=True, timeout=180)
    rep = json.loads(r.stdout)
    assert not rep["errors"], rep["errors"]
    return rep["out"]


def test_block_place(out):
    assert out["no_ptr"] and out["wrap_order"] and out["wrap_loading"]


def test_day_wise(out):
    assert out["cols"] == [35, "D0", "D30", "D60", "D365"]              # every day 0 … 30, then 60 / 90 / 180 / 365
    assert out["old_fallback"] == [[8, True], [None, False]]           # older days: the checkpoints, never a guess
    assert out["day_today"] and out["day_tiles"] and out["hero"] and out["day_be"] and out["day_tie"]
    assert out["day_rows"] == 60 and out["day_more"]                   # 60 at a time, "Show all" (nothing dropped)
    assert out["months"] == [["2026-10", 13], ["2026-09", 30], ["2026-08", 27]]
    assert out["month_cols"] == ["D0", "D1", "D3", "D7", "D14", "D30"] and out["month_d0"] == 30
    assert out["month_d30"] is None                                    # a month waits for its youngest day
    assert out["cells"] == [2, 20, 0.2, 5]                             # ROAS, revenue, per install, delta


def test_day_wise_past_d30(out):
    # the late read's m: D0 … D30 day by day, then every 30 days up to the oldest install day's age (229 days → D210)
    assert out["m_cols"] == [37, "D0", "D30", "D60", "D90", "D210", 6] and out["m_head"]
    # a cell = m[j] (final while j < mf); a row whose m does not reach the column: nothing (·), never a checkpoint
    assert out["m_cells"] == [[41, True], [91, True], [51, False], [None, False], [41, True], [None, False]]
    assert out["m_nf"]                                                 # not final: the same light style as D0 … D30
    # week / month: the T ≤ 30 checkpoints, then the same 30-day columns; a group's cell only when every day has it
    assert out["m_month_cols"] == ["D0", "D1", "D3", "D7", "D14", "D30", "D60", "D90", "D120", "D150", "D180", "D210"]
    assert out["m_month"] == [[1230, True], [1530, True], [None, False], [None, False]]
    assert out["m_week_cols"] == ["D30", "D60", "D90"]
    # the title says the real last column (a file without m: D365 as before); the Hinglish note + GA4's "(other)" share
    assert out["m_title"] and out["m_note"] and out["m_q"]
    assert out["m_be"]                                                 # breakeven / so far through the 30-day columns
    # the default Day view (newest 60 install days, none with m yet): the columns as before, the note says how far
    # the older rows go — never 30-day columns that are all "·"
    assert out["m_default"] == [35, "D60,D90,D180,D365", True]
    # a file whose late read reaches only D60 so far: no checkpoint column is lost, and a row without m keeps its own
    # D60 / D90 / D180 / D365 (final); the note lists only the columns there are; tiny shares print "<0.1%"
    assert out["m_part_cols"] == ["D0", "D1", "D3", "D7", "D14", "D30", "D60", "D90", "D180", "D365"]
    assert out["m_part_cells"] == [[61, True], [91, True], [181, True], [None, False]]
    assert all(out["m_part"]) and all(out["m_list"]) and out["m_q4"]
    # the cohort cube's first walk still on its way: no column, the Hinglish note says so, how far it read and when it
    # last moved on; once through, a walk that stalled says how far every day was read (the newest columns wait for it)
    assert all(out["m_busy"]) and len(out["m_busy"]) == 7
    assert out["m_thru"] == [True] * 7


def test_countries_life_all(out):
    assert out["cty_cut"] and out["cty_order"] == ["BB", "CC", "AA"] and out["cty_chips"] == 3
    assert out["life_total"] and out["life_since"] and out["life_live"] and out["life_inr"]   # ₹ = as billed
    assert out["hero_all"]
    assert out["co_rows"] == ["Jan 2026 · 1d", "Dec 2025 · 2d", "Total · Dec 2025 se"] and out["co_paid"]   # a part month says its days and out["co_total"] and out["co_usd"]
    assert out["all_order"] == ["id-a", "id-b"] and out["all_icons"] == 2
    assert out["card"] == "📈 D7 ROAS <b>40%</b> (usual 50%) · paisa wapas ~12 days"   # ROI's own numbers replace the card's


def test_four_forms(out):
    # the app's hero: the payback-target age when complete, else its longest; every range from the file's own consts
    assert out["f4_hero"] == [] and out["f4_hero_help_closed"] and out["f4_hero7"] and out["f4_hero90"]
    assert out["f4_help"] == [] and out["f4_share_bars"] == 30 and out["f4_share_nums"] == 5   # paid share per install day
    assert out["f4_down"] and out["f4_up"] and out["f4_off"] and out["f4_none"]          # paused spend: no raise / cut
    assert out["f4_own_beta"] and out["f4_na"]                  # an app's own beta range named; no Ads count: blended only
    # GA4 measured the paid split: measured paid share + premium, said so; paid-only one number; b / beta stay ranges
    assert out["f4_measured"] == [] and out["f4_measured_no_p_range"] and out["f4_measured_help"]
    assert out["f4_measured_elsewhere"]                         # the age switch marks the measured age (✓)
    # All apps: biggest blended-vs-paid gap first (no complete age last), flagged rows, every app with its icon
    assert out["f4_all_order"] == ["id-a", "id-b", "id-p", "id-c"] and out["f4_all_flag"] == ["id-a"]
    assert out["f4_all_icons"] == 4
    # chips: badhao / pakka nahi / ghatao / spend band / jaldi / zyada organic; the total leaves the paused app out
    assert out["f4_all"] == [] and out["f4_all_tot"] == [] and out["f4_all_chips"] == [0, 1, 1, 1, 1, 1, 1]
    assert out["f4_all_sp"] == ["id-b", "id-a", "id-p", "id-c"] and out["f4_all_inr"] and out["f4_hero_all"]
    # a paused app is paused whatever its call (also "too early"): ⏸️, out of the spend-on total and of the ⚖️ hero card
    # (a live app's D30, else its D7; no card when none); "✓ GA4" only on what GA4 measured (an all-paid range collapses)
    assert out["f4_paused_early"] and out["f4_paused_early_hero"] and out["f4_allpaid"]
    assert out["f4_paused_hero_all"] and out["f4_paused_hero_none"]
    # the premium range was measured at D30 (consts "pa"): every other age on screen that uses it says so
    assert out["f4_all_pa"] and out["f4_pa_hero"] and out["f4_pa_own"] and out["f4_pa_measured"]


def test_forecast_view(out):
    assert out["fc_tiles"] and out["fc_ready"] and out["fc_be"] and out["fc_parts"] and out["fc_slider"]
    assert out["fc_split"] and out["fc_split_off"]
    assert out["fc_users"] and out["fc_users_slider"]
    assert out["fc_vd"]                                                # engine vd's settings and note
    assert out["fc_vd_switch"]                                         # … and the engine switch in the learning log
    assert out["fc_gx"]                                                # GA4's late / paid cells: measured vs carried
    assert out["fc_gx_nosrc"]                                          # … no paid ÷ organic line without a source
    assert out["fc_gx_held"]                                           # … held off / never checked / users only / on
    # 💸 Budget by country: today's plan = the forecast; Keep total; out-of-range warning; owner-only; the slider
    assert out["pl_card"] and out["pl_keep"] and out["pl_warn"] and out["pl_nokeep"]
    assert out["pl_dev"] and out["pl_none"] and out["pl_slider"] and out["pl_h"] and out["pl_inr"]
    # … each row's own revenue per $ (GA4 paid cells) at 30 / 90 days with its source, one value past 90
    assert out["pl_own"] and out["pl_own_move"] and out["pl_own_180"] and out["pl_own_72"]
    # … its trust per row ("Mostly app avg" under half its own data) and this app's own back-test (waiting / lost)
    assert out["pl_own_weak"] and out["pl_own_weak2"] and out["pl_bt"]
    # 🔎 "Agle N din": the verified horizon's chips (fixed widths, N max, 365 locked with its day), the note, tiles,
    # band, users card, planner and accuracy at the chosen horizon; a young app / no horizon / a full year
    assert out["hz_chips"] and out["hz_note"] and out["hz_tiles"] and out["hz_users"] and out["hz_plan"]
    assert out["hz_band"] and out["hz_chart"] and out["hz_acc"] and out["hz_old_origins"] and out["hz_pick"]
    assert out["hz_young"] and out["hz_none"] and out["hz_365"] and out["hz_all"]
    # the range read the right way round (forecast ÷ (1 + error)), a very wide one capped on the chart, no normal test
    # said so, a step in the daily line said so
    assert out["hz_chart_wide"] and out["hz_no_normal"] and out["hz_jump"] and out["hz_acc_cut"]
    # a range beside the forecast said with its shrink; ± from the range's own tests; the first live check's day (and
    # why the growing N never gets one on its chip); a chip that can not be shown exactly said, not locked; x labels
    # never overlap
    assert out["hz_side"] and out["hz_nm"] and out["hz_chk"] and out["hz_drop"] and out["hz_axis"]
    # 📅 the eCPM calendar: markers with the measured %, tooltip, note, holidays not applied, owner-only
    assert out["cal_marks"] and out["cal_tip"] and out["cal_note"] and out["cal_30"] and out["cal_180"]
    assert out["cal_dev"] and out["cal_none"] and out["cal_wk"] and out["cal_off"] and out["cal_small"] and out["cal_zero"]


# the default view's digest on the page before the country filter (tests/roi_frontend.js defaultDigest, worked out there)
GOLDEN_DEFAULT = "afd5bf6e3a67b59154525ddec5b34724b11a6a0a158388d09ad8bada10b88982"


def test_country_filter(out):
    # "All countries" (the default) byte for byte as before: every grain × mode, the Day view, the Countries board
    assert out["cc_default_digest"] == GOLDEN_DEFAULT and out["cc_src_null"]
    # the picker: All countries + the top 6 as chips, EVERY country in the native list, then the two that are not one
    assert out["cc_chips"] == ["", "AA", "BB", "CC", "DD", "EE", "FF"]
    assert out["cc_list"] == ["", "AA", "BB", "CC", "DD", "EE", "FF", "GG", "HH", "--", "XX"] and out["cc_list_txt"]
    assert out["cc_all_same"]                       # All: the same table, only the picker first in the control row
    # a pick: its pack read once (?v=its sha; a second country of it: no read), "loading" only in the table area
    assert out["cc_loading"] and out["cc_fetch"] == ["roi_aaaaaaaaaaaa_c00.json.gz?v=0123456789ab"]
    # the same table for that country: title + "✕ All countries", D0 … D30, then (the newest 60 install days have no
    # 30-day column yet) the checkpoints as the All table does — the same cols(); 60 rows a page, "Show all"
    assert out["cc_table"] == [True, True, 35, "D0", "D30", "D60", 60, True, True, 35]
    assert out["cc_zero"] == [16, 0, 31, 31, [0], 1, None, "N/A"]   # a short [X] expanded (zero day, spend unknown)
    assert all(out["cc_cells"]) and out["cc_grains"]                # its own spend → ROAS; '—'; its ≈ texts; week / month
    assert out["cc_note"] == []                                     # every limitation said, with its measured size
    assert out["cc_more"] == [True, True, True, 2]                  # a country from the list: its pack (one more read)
    assert all(out["cc_unknown"]) and all(out["cc_notsplit"])       # "Unknown country" / "Not split"
    assert all(out["cc_persist"])                                   # kept across grain / mode / apps; missing → said
    assert all(out["cc_err"]) and out["cc_badname"] and out["cc_busy"]
    assert out["cc_board"] == [["BB", "CC", "AA"], False]          # 🌍 Countries: "📅 Day-wise" where the cube has it
    assert out["cc_zx"] and all(x == 1 for x in out["cc_zx"]), [x for x in out["cc_zx"] if x != 1][:3]
    assert len(out["cc_zx"]) == 120
    for w in ("w375", "w1280"):                                     # no page jump: the tapped control stays put
        nj = out["cc_nojump"][w]
        assert nj["moves"] == [0] * 13 and nj["keptWeek"] and nj["backAll"] and nj["picked"], (w, nj)
        assert nj["errShown"] and nj["retried"], (w, nj)                # error → "Try again" → read again, loaded
    # review fixes: a pack landing after the reader moved on never repaints the table on screen
    assert out["cc_late"] == [True, 0, True]
    assert out["cc_q_new"] and out["cc_pick_sel"]                  # bits 32 / 64 said; one option selected
    # 🧩 Not split: D0 … D30 day by day like every country, its cells '—' (as the note says)
    assert out["cc_xx_cols"] == [35, "D1", "D2", "D30", False, True, True, True]
    assert all(out["cc_noq"]) and out["cc_to"] and all(out["cc_nocd"]) and all(out["cc_tz"])
    assert out["cc_zx_guard"]                                       # a row past the index's last day: never expanded
    # a pack of another build than the index (its "b"): the app file read again once, then its own pack; a pack gone
    # from the site (404): the same; the site still on the other build after it: said, "Try again"
    assert all(out["cc_stale"]) and all(out["cc_gone"]) and all(out["cc_stale_again"])
    assert out["cc_lru"] == [3, True, 3, True, True]                # only the newest 3 packs kept (the one in use too)


def test_wiring():
    with open(PAGE, encoding="utf-8") as f:
        p = f.read()
    assert "return roiWrap(vsAppOn(r)?vsAppPage(r,old):old, r.app_id);" in p and 'id="val-more"' in p
    assert "return roiWrap(vsOn()?vsPortfolio():valPortfolio(), '');" in p
    assert "if(c[0]==='value') try{ roiCardLine(x,name); }catch(e){}" in p
    assert ".roi{position:relative;" in p
    assert "+`</div>`+f4Hero(d)+`</div>`; }" in p and "+f4All(apps)+(pc?" in p             # ⚖️ hero + All-apps table
    for a in ("data-roi-f4h", "data-roi-f4x", "data-roi-fsort"):                         # every toggle keeps its place
        assert "if((b=at('[%s]'))){ " % a in p and "keep(b,()=>{" in p.split("if((b=at('[%s]'))){ " % a)[1].split("\n")[0]
    seg = p.split("if((b=at('[data-roi-pl]'))||(b=at('[data-roi-plk]'))||(b=at('[data-roi-plr]'))){")[1].split("return; }")[0]
    assert "keep(b,()=>{" in seg and "fcPlan(dd)" in seg                                  # −/+, Keep total, Reset: in place
    for a in ("data-roi-cc", "data-roi-ccx", "data-roi-pick"):                          # 🌍 every country control too
        assert "keepAt(r," in p.split("if((b=at('[%s]'))){ " % a)[1].split("\n")[0]
    assert "keepAt(r,t,'[data-roi-ccs]'," in p                                          # … and the full list's change
    assert "if(PK[k].err||PK[k].stale) delete PK[k]; }); Object.keys(RLD).forEach(k=>{ delete RLD[k]; }); repaint();" in p   # Try again
    assert "/^roi_[0-9a-f]{12}_c\\d{2,3}\\.json\\.gz$/" in p                           # a pack name the build writes only
    assert "@media (max-width:760px){.roi-ccs{font-size:16px}}" in p                     # iOS: no zoom on the list
