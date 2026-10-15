"""📈 ROI (a section of 💸 Install value) — the page side. tests/roi_frontend.js runs the ROI module + roiWrap of
frontend/index.html for real (a node vm, stub page helpers) on SYNTHETIC data made up there; checked here: where the block
goes, the day-by-day columns and their fallback to the checkpoints, Today / Yesterday, week / month rows (complete days
only), the four cell kinds, breakeven, the KPI tiles, the countries board (order, what cutting saves), lifetime P/L
(totals to the day both sides are in), All apps (icons, Worse first, hidden apps out), the hub card line, the four forms
of ROI (hero block, ranges printed from the file, GA4-measured paid split, budget call, mostly-organic flag, All-apps
table), and the wiring into
the page. Skipped where node is not installed. No real data."""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
PAGE = os.path.join(ROOT, "frontend", "index.html")


@pytest.fixture(scope="module")
def out():
    if NODE is None:
        pytest.skip("node is not installed")
    r = subprocess.run([NODE, os.path.join(ROOT, "tests", "roi_frontend.js"), PAGE],
                       check=True, capture_output=True, text=True, timeout=120)
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
    # 📅 the eCPM calendar: markers with the measured %, tooltip, note, holidays not applied, owner-only
    assert out["cal_marks"] and out["cal_tip"] and out["cal_note"] and out["cal_30"] and out["cal_180"]
    assert out["cal_dev"] and out["cal_none"] and out["cal_wk"] and out["cal_off"] and out["cal_small"] and out["cal_zero"]


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
