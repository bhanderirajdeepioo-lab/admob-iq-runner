"""📈 ROI (a section of 💸 Install value) — the page side. tests/roi_frontend.js runs the ROI module + roiWrap of
frontend/index.html for real (a node vm, stub page helpers) on SYNTHETIC data made up there; checked here: where the block
goes, the day-by-day columns and their fallback to the checkpoints, past D30 every 30 days up to the app's age (the
cohort cube's m: columns, finality, week / month, title + note, breakeven / so far; the cube still on its way: only a
note; a file without m: the checkpoints), Today / Yesterday, week / month rows (complete days only), the four cell kinds, breakeven
(right after CPI: the row's own on Day, the group's first green cell on Week / Month), the KPI tiles, the countries board
(order, what cutting saves), lifetime P/L (totals to the day both sides are in), All apps (icons, Worse first, hidden apps out), the hub card line, the four forms
of ROI (hero block, ranges printed from the file, GA4-measured paid split, budget call, mostly-organic flag, All-apps
table), 🌍 the install-day table by country (the picker, a pack read once, the same table for one country, the default
view byte for byte as before, the pick kept, the missing-country / error / retry / busy states, the notes, a short row
expanded exactly as the build's _zrow, no page jump at 375 and 1280 px; a pack of another build / gone from the site:
the app file read again once; a late pack never repaints; only 3 packs kept; Not split's columns; the notes' measured
limits), 🧮 the cohort card's totals strip for All or the picked country — one group over every install day (Total
spend = Σ the Spend column, Total revenue = Σ the So far column, Profit / loss = printed revenue − printed spend to the
last digit, ROAS blended, 🎯 Avg breakeven, installs, install days; days with no spend data / so far not read counted,
never 0): hand recounts, the owner's case in its shape, the same for every grain / mode, '…' while loading, one height in every state,
no value cut at any width, the page otherwise byte for byte as before), "Show 60 more" / "Show
all" keeping the reader's row and the table box's scroll (every grain × mode, every country, the lifetime table, 375 and
1280 px, with the stay-put layer: no second scroll) — sideways by column (the Day table's columns change with the rows
shown), Mode switches keeping the box's row and column too — and the wiring into the page. Skipped where node is not
installed. No real data."""
import json
import os
import re
import shutil
import subprocess
from html import unescape

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
    # the build's own late info on a made-up cube whose loss past D420 is below a cent (the page must say "<$0.01")
    from tests import test_roi_build as trb
    root = os.path.join(os.path.dirname(path), "qcube")
    P, co = trb._q_world(root, b=9995)
    qlate = rb._late(root, "a~1", "222", P)["info"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"cd": {"thru": thru.isoformat(), "fthru": fthru.isoformat(), "geo": {"unk": unk, "billed": 1}},
                   "cases": by[1], "cd0": {"thru": thru.isoformat(), "fthru": fthru.isoformat(),
                                           "geo": {"unk": unk, "billed": 0}}, "cases0": by[0], "qlate": qlate}, f)


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
    # q (the whole no-country read past D30): D31–D420 whole, GA4's no-install-day share past D420 and with no install
    # day at all as measured sizes (never $0 when it is not), the days still on the cube's cells (waiting / for good,
    # their "(other)" size), drift with its size and no cause claimed; no q fields: the note as before
    assert out["m_qnote"] == [True] * 14, out["m_qnote"]
    # the build's own sub-cent loss past D420 (roi_build._late on a made-up cube) → the page's "<$0.01", never "nothing"
    assert out["m_qbuild"] == [True] * 3, out["m_qbuild"]


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


# the default view's digest (tests/roi_frontend.js defaultDigest). Changed ON PURPOSE on 21 Oct 2026 when the Breakeven
# column moved from the far right to right after CPI (and its note joined): the page before that gave
# afd5bf6e3a67b59154525ddec5b34724b11a6a0a158388d09ad8bada10b88982. GOLDEN_NO_BE = the same parts with the Breakeven
# column and its note cut out, worked out on the page BEFORE the move (its far-right cell cut) — the new page gives it
# too: nothing else in any table, the Day view or the Countries board moved by a byte. (Review round: a "≤" on a column
# not final yet is faded + "not final", the note says so, and a week / month with a day's so far not read shows — instead
# of a too-low "% back": only the Breakeven cells + note changed, GOLDEN_NO_BE the same)
# 🧮 Changed ON PURPOSE again on 21 Oct 2026 when the totals strip joined the cohort card (between its title row and its
# control row): GOLDEN_PRE_KPI = the digest the page gave before it (the GOLDEN_DEFAULT above it), and the strip page gave
# it again with the strip cut out (tests/roi_frontend.js kpiCut) — every table, the Day view and the Countries board
# otherwise byte for byte the same.
# Changed ON PURPOSE again on 21 Oct 2026: every install-day / week / month row got its key (<tr data-roi-k="…">) so
# "Show 60 more" / "Show all" keep the reader's row in place. The page now has both changes, so each cut sees the other:
# GOLDEN_DEFAULT_NOK = the key cut out, the strip kept = the strip page's own GOLDEN_DEFAULT (the page before the key);
# GOLDEN_DEFAULT_NOKPI = the strip cut out, the key kept (= what the key alone gave on the page before the strip); both
# cut out = GOLDEN_PRE_KPI, the page before both byte for byte: the strip and the key are the only changes.
# GOLDEN_NO_BE is worked out with the strip and the key cut out too (kpiCut, then beStrip's noK).
# Changed ON PURPOSE again on 21 Oct 2026 when the strip became two groups ("Spend pata wale din" / "Poori history", the
# owner: "profit loss me wrong lag raha he"): only the strip changed — GOLDEN_DEFAULT_NOKPI, GOLDEN_PRE_KPI and
# GOLDEN_NO_BE (the strip cut out) are the same as before; the strip page before the two groups gave GOLDEN_DEFAULT
# 16bb214bf4da82bd17f7e6e1b317c25fef607b17b619f0fb846f0603edc28baf and GOLDEN_DEFAULT_NOK
# 65b3d7ad62d5c151e9d12391231199db6be372b859c43e0ebd44f8b1b420cc9c.
# Changed ON PURPOSE again on 21 Oct 2026 when the two groups became ONE group over every install day (the owner: "poori
# history vala hi sahi he — spend pata wale din nikal do — profit loss total puri history pe hi hona chaiye"): again only
# the strip — GOLDEN_DEFAULT_NOKPI, GOLDEN_PRE_KPI and GOLDEN_NO_BE the same; the two-group page gave GOLDEN_DEFAULT
# fe4ef94df5f6792ed2169db0dfe081c003a5995ef4ccdc6fa1e5cffd10e9e717 and GOLDEN_DEFAULT_NOK
# a79cb926cc8aa51d985029ae477fda8cf617f7423ed918e2534fa948fbafcfdb.
# 🔁 Changed ON PURPOSE again on 22 Oct 2026 when every D cell got its retention line (a small second line inside the
# cell) and the legend line under the table: GOLDEN_RET_CUT = the page with only those cut out (tests/roi_frontend.js
# retCut) = the GOLDEN_DEFAULT before them byte for byte; every other golden is taken with them cut out too (the same
# values as before): no cell value, column, row, note or tile moved in any grain × mode. Changed on purpose once more the
# same day (review fixes): a "·" cell keeps its line ("—" when not measured) like every other mode, T's checkpoint columns
# past D30 have no line (no users source), the week / month line is final only once every day with users is, and the
# legend says so — GOLDEN_RET_CUT unchanged (nothing outside the lines and the legend moved).
# 🎯 Changed ON PURPOSE again on 22 Oct 2026 when the strip got its 7th tile, Avg breakeven (the owner: "average breakeven
# day ka KPI add kar do"), its line under the tiles and a sentence in its note: again only the strip — GOLDEN_DEFAULT_NOKPI,
# GOLDEN_PRE_KPI and GOLDEN_NO_BE (the strip cut out) the same; the one-group page gave GOLDEN_DEFAULT
# a58589ba371a9cfb3b64cafbb2f169cf2ca28182c5ade16f343d486a51b7cfbe and GOLDEN_DEFAULT_NOK
# 3072f1658c636ddad28ba3b475175a25e9e8438973ce08bcde75d2d5bdca12d7.
# 🎯 And again ON PURPOSE on 22 Oct 2026 after its review (Avg breakeven over every $5+ ads day: the Kaplan–Meier median,
# only days 2 × it old averaged, "≤ D<n>", each left-out day by its own why; the line's box 4 / 3 / 2 lines by width; the
# made-up rows' so-far dates set to the day each so far was read to — read by nothing but this tile): only the strip —
# GOLDEN_DEFAULT_NOKPI, GOLDEN_PRE_KPI and GOLDEN_NO_BE the same; the first Avg breakeven page gave GOLDEN_DEFAULT
# f16df0114ed2af8f00027ec2854f76367faf228b7d78d00a98ef05bf8ab0759b and GOLDEN_DEFAULT_NOK
# f927fa5ebcb05d6d2459ca8eb8402c0e9eab65466d745bda0243f784bff7e53b.
# Merged with the retention lines (also 22 Oct): GOLDEN_RET_CUT (retention lines cut) = this branch's own default page.
# 🎯 And again ON PURPOSE on 22 Oct 2026 when Avg breakeven became the plain median rule (the owner: "200 din me se 100 din
# me agar breakeven mila he to … vo 100 din ka kya avg he BE vo dikhana chaiye aur dikhao ki 100 din abhi breakeven tak
# nahi pahoche": the mean over the days that reached breakeven, whatever their age, the fast ones out; its tile reason, its
# line and the note's sentence): only the strip — GOLDEN_DEFAULT_NOKPI, GOLDEN_PRE_KPI and GOLDEN_NO_BE (the strip cut
# out) the same; GOLDEN_DEFAULT, GOLDEN_DEFAULT_NOK and GOLDEN_RET_CUT (each with the strip in) moved — the Kaplan–Meier
# page gave b2f6e83b9b63ec3731afe05b1238102818f77b15aee95e4ad3fa293378e5cb1b,
# 0850be88d98457b5d50c85d3ae76ff8babf68628e1039fec509d3da09497ce61 and
# fa39df20e85ec92db68880a4c4ed1b1aac09f0a0d68bd4f2e869f83b769bac14.
# 👥 Not changed on 22 Oct 2026 by the small numbers' ≈ (cd "uu" runs for a country, late "u" "qou" for All): the default
# view's files (appFile, lateFile) carry neither field (rt_uu_golden_fx) — every golden as before.
GOLDEN_DEFAULT = "9ef76c49a61c84d77011d7fbe1339efbdb0c8f0b122173bcfd417828cf4dabff"
GOLDEN_RET_CUT = "7d5fed94def3685a4ae814cfffb302da846cbc23db35abe196b45ffa5be4a9ad"
GOLDEN_DEFAULT_NOK = "8ea8ca3eb5c377e83fec7ce75a4ad64e74429daec4c1a87690161261e7fccd13"
GOLDEN_DEFAULT_NOKPI = "98ae0afdcb42a1e9d258ef5fe660fba126dad93f9b7b6c83e4f801eca78514eb"
GOLDEN_PRE_KPI = "fb638f026d2a902459c3287cb620536bbb6474fecb17809c9799ba6264ac0a86"
GOLDEN_NO_BE = "acabb725b05aa314e38c4f97b7880196122d333a0bdd823a0db9c1bc7d1d23b6"


def test_breakeven_column(out):
    """🎯 Breakeven right after CPI, before D0 (owner, 21 Oct 2026: "D0 ke pehle ak column add kar do — konse day pe
    breakeven milta he"): every grain × mode, the All table and every country's, no far-right copy, never a day the
    cells do not show."""
    assert out["be_order"] == [True] * 48                         # … Spend, CPI, Breakeven, D0 …, So far (last)
    assert out["cc_default_nobe"] == GOLDEN_NO_BE                  # the rest byte for byte as before the move
    # Day: the row's own breakeven from the build; not yet: so far ÷ spend (muted; green once ≥ 100%); no spend: —
    # a "≤" whose day's cell is seen but not final (D1 after a final D0, or D0 itself): faded + "not final" like that cell
    nfd = '<td class="roi-g roi-nf" title="not final">≤ day %d</td>'
    assert out["be_day"] == ['<td class="roi-g">day 9</td>', '<td class="roi-g">≤ day 120</td>', '<td class="roi-na">63% back</td>',
                             '<td class="roi-g">104% back</td>', '<td class="roi-na">—</td>', '<td class="roi-na">—</td>',
                             '<td class="roi-na">—</td>', nfd % 1, nfd % 0, '<td class="roi-g">day 1</td>']
    assert [[c.split('"')[1] for c in r] for r in out["be_day_cells"]] == [                    # their D0, D1 cells
        ["roi-w", "roi-g roi-nf"], ["roi-g roi-nf", "roi-na"], ["roi-w", "roi-g"]]
    assert out["m_be"]                                             # … through the 30-day columns (≤ day 120), in place
    # week / month: the group's own, from agg (the cells' numbers): exact only where the cells pin the day
    assert out["be_month"] == [["Jan 2026", '<td class="roi-g">day 0</td>'], ["Feb 2026", '<td class="roi-g">day 1</td>'],
                               ["Mar 2026", '<td class="roi-g">≤ day 3</td>'], ["Apr 2026", nfd % 1],
                               ["May 2026", '<td class="roi-g">≤ day 3</td>'], ["Jun 2026", '<td class="roi-g">≤ day 60</td>'],
                               ["Jul 2026", '<td class="roi-na">63% back</td>'], ["Aug 2026", '<td class="roi-na">—</td>'],
                               ["Sep 2026", '<td class="roi-na">—</td>']]     # a day's so far not read: —, not "30% back"
    assert out["be_week"] == ['<td class="roi-g">day 1</td>'] and out["be_month_cells"]
    # [day, exact?, that column final?]: spend 0 / unknown / never reached: no day; Apr: D1 not final; Mar: final, a gap
    assert out["be_grp"] == [[1, True, True], None, None, None, [1, False, False], [3, False, True]]
    # "% back" only from a measured so far: days not read yet → — on Day, and on their week / month (never "0% back" or a
    # too-low share of the whole spend)
    assert out["be_nos"] == [[["Today · 14 Oct 26", '<td class="roi-na">—</td>'], ["Yesterday · 13 Oct 26", '<td class="roi-na">—</td>'],
                              ["12 Oct 26", '<td class="roi-na">—</td>'], ["6 Oct 26", '<td class="roi-na">80% back</td>'],
                              ["5 Oct 26", '<td class="roi-na">80% back</td>']],
                             [["12 Oct–18 Oct 26", '<td class="roi-na">—</td>'], ["5 Oct–11 Oct 26", '<td class="roi-na">80% back</td>']],
                             [["Oct 2026", '<td class="roi-na">—</td>']]]
    # both made-up files, week + month: every group's breakeven = its first green (ROAS ≥ 100%) cell (faded exactly when
    # that cell is), or none at all
    assert [c[1] for c in out["be_cells"]] == [True] * 4 and all(c[2] for c in out["be_cells"])
    # a country's table: the same column, every grain; its groups = their first green cell; Not split: — on every row
    assert [c[:2] for c in out["be_cty"]] == [[cc, g] for cc in ("AA", "BB", "XX") for g in ("day", "week", "month")]
    assert all(c[2:] == ["Spend,CPI,Breakeven,D0", "So far", True, True, True, True] for c in out["be_cty"]), out["be_cty"]
    assert out["be_cty_day"] == ['<td class="roi-g">130% back</td>', '<td class="roi-na">30% back</td>']
    assert all(out["be_note"])                                      # the Hinglish line under the table, per grain


# 🧮 the strip's value boxes, worked out from the page's own CSS (pinned in test_wiring) and checked in headless Chrome.
# 22 Oct 2026, 7 tiles (🎯 Avg breakeven joined; every one of the 52 states below, one height per width, no value / label /
# reason / line cut, no tile alone in a row, 360–2560 px): up to 899 px 2 a row with Avg breakeven across both (rows
# 2 · 2 · 1 · 2; 360 → 131 px, its own 292); from 900 px a 12-column grid — the three money tiles 4 columns each, ROAS ·
# Avg breakeven · Installs · Install days 3 each (rows 3 · 4; 900 → 165–170 / 116–120 px, 1599 → 398 / 291); from 1600 px
# 7 a row (1600 → 152–155, 2560 → 292). (The one-group page before it: 6 tiles, 2 / 3 / 6 a row from 900 / 1400 px.) The
# card's and the tile's padding + border; beside the sidebar a classic 15 px scrollbar is taken off too.
# → (width, scrollbar, phone?, the value box of a tile by its label)
_MONEY = ("Total spend", "Total revenue", "Profit / loss")


def _kpi_boxes():
    for w in range(360, 761):                                    # the phone / tablet layout: no sidebar, 2 a row
        pad = 10 if w <= 430 else 12                             # .content (≤430 px: 10, ≤760 px: 12) · .roi-card 12 + 1
        inner = w - 2 * pad - 26                                 # tile: 9px 10px + 1 px border; Avg breakeven spans both
        yield w, 0, True, lambda lab, i=inner: (i if lab == "Avg breakeven" else (i - 8) / 2) - 22
    for w in range(761, 2561):
        for sb in (0, 15):                                       # aside 220 · .content 24 · .roi-card 16 + 1 · tile 11 + 1
            inner = w - 220 - 48 - sb - 34
            if w < 900:
                yield w, sb, False, lambda lab, i=inner: (i if lab == "Avg breakeven" else (i - 8) / 2) - 24
            elif w < 1600:                                       # 12 columns, 11 gaps of 8
                yield w, sb, False, lambda lab, c=(inner - 88) / 12: (4 * c + 24 if lab in _MONEY else 3 * c + 16) - 24
            else:
                yield w, sb, False, lambda lab, i=inner: (i - 48) / 7 - 24


# advance widths (em) of the value font (weight 800, tabular figures) measured in headless Chrome; the largest of 13 /
# 14 / 15.5 / 17 px for every size (the system font is a little wider at small sizes); "D" (Avg breakeven's "D77"):
# 0.749 at weight 800, measured the same way (22 Oct 2026); "≤ " (its "≤ D77" over a "≤ day"): 0.679 + 0.244
_EM = dict({c: 0.68 for c in "0123456789+−₹$≤"}, **{",": 0.36, ".": 0.36, "%": 1.07, "—": 0.92, "…": 1.0, "D": 0.75, " ": 0.25})


def _px(text, size):
    return sum(_EM[c] for c in text) * size


def _money(v):
    """A printed money value → its number ('−₹1,23,456' → -123456)."""
    return (-1 if v.startswith("−") else 1) * float("".join(c for c in v if c.isdigit() or c == "."))


def _holds(k, rc=None):
    """The printed tiles: Profit / loss = Total revenue − Total spend to the last printed digit, ROAS = Total revenue ÷ Total
    spend (blended) — over the same strip, every install day (the owner: "profit loss total puri history pe hi hona chaiye").
    ROAS from the sums themselves (rc: the recount's unrounded s / r — the So far column's so far ÷ spend), not from the
    rounded tiles; without rc the printed tiles are the exact sums."""
    s, r, p = (_money(k[i][1]) for i in range(3))
    rs, rr = (rc["s"], rc["r"]) if rc else (s, r)
    return round((r - s) * 100) == round(p * 100) and k[3][1] == f"{int(rr / rs * 100 + 0.5)}%"


# (🎯 Avg breakeven given per case: these hand cases' days mostly have no breakeven day — '—' + why; test_avg_breakeven has
# its own cases)
def _tiles(spend, rev, profit, roas, installs, days, sub_s="Google Ads", sub_r="so far · AdMob-matched", be=None):
    assert be is not None
    return [["Total spend", spend, sub_s], ["Total revenue", rev, sub_r], ["Profit / loss", profit, "revenue − spend"],
            ["ROAS", roas, "revenue ÷ spend · blended"], ["Avg breakeven", *be], ["Installs", installs, "GA4 · ads + organic"],
            ["Install days", *days]]


def test_totals_strip(out):
    """🧮 The cohort card's totals strip (owner, 21 Oct 2026: "kpi add karo yaha pe ki kitna total spend gaya he kitna total
    revenue aaya he — all country and jo country select kru uska kpi change ho jayega — total hi aayega"), ONE group over
    every install day since the owner saw the two groups ("poori history vala hi sahi he — spend pata wale din nikal do —
    profit loss total puri history pe hi hona chaiye"): Total spend = Σ the Spend column (days with no spend data left out,
    counted), Total revenue = Σ the So far column (days not read yet left out, counted), Profit / loss = printed revenue −
    printed spend, ROAS = revenue ÷ spend, Installs, Install days — on made-up rows."""
    # the default page: only the strip changed — with it cut out, the digest is the one before it (2 parts carry it: the
    # Day views); the rows' key (Show 60 more) is on the page too: the strip cut, the key kept = GOLDEN_DEFAULT_NOKPI; both
    # cut = the page before both
    assert out["cc_default_nokpi"] == GOLDEN_DEFAULT_NOKPI and out["cc_default_kpis"] == 2
    assert out["cc_default_nokpi_nok"] == GOLDEN_PRE_KPI
    # under the title row, right above the control row (one per card, above the table; the Day view has one, the
    # Countries board none); its fixed Hinglish note; ONE grid, no group heads / two-group wrapper left; 🎯 Avg breakeven
    # right after ROAS (the only tile with a class of its own: its span), its line first under the tiles
    assert out["k_place"] == [True, 1, True, 1, False, True, 1, False, True, True,
                              "Total spend · Total revenue · Profit / loss · ROAS · Avg breakeven · Installs · Install days", 1]
    # a hand recount (5 install days): 2 Jan has no spend data (out of Total spend, said — its $5 revenue in), 3 Jan's so
    # far is not read yet (out of Total revenue, said — its $4 spend in), 4 Jan ads paused ($0, $0). Total spend $10 + $4 +
    # $0 + $6 = $20, Total revenue $30 + $5 + $0 + $3 = $38 → +$18 (= $38 − $20), ROAS 190%; 200 installs, 5 days
    k, line, (s, r, p, roas, exact) = out["k_usd"]
    assert k == _tiles("$20", "$38", "+$18", "190%", "200", ["5", "1 Jan 2026 – 5 Jan 2026"],
                       "1 din ka spend data nahi", "1 din ki kamai abhi nahi padhi", ("—", "abhi koi din BE nahi hua (2 ads din)")) and _holds(k) and exact
    assert line == "1 din ka spend data nahi (2 Jan 26) — unka spend jod me nahi, revenue hai."
    assert out["k_usd_cls"] == [["", ""], ["", ""], ["roi-kg", "roi-up"], ["", "roi-g"], ["roi-cka", ""], ["", ""], ["", ""]]   # profit green, ROAS ≥ 100% green
    # = the table's own columns: Σ Spend, Σ So far, Σ Installs
    assert out["k_usd_table"] == [20, 38, 200] == [s, r, 200]
    # ₹ billed (₹90 a $ on every day, today ₹100): the bill ₹900 + ₹360 + ₹0 + ₹540 = ₹1,800 (= Σ the Spend column), the so
    # far at today's rate $38 × 100 = ₹3,800 (= Σ the So far column) → +₹2,000 exactly, ROAS 211%
    # (the ₹ view says "₹ aaj ka rate" on Total revenue with the unread count too: spend as billed, revenue at today's rate)
    k, line, (s, r, p, roas, exact), table, rc = out["k_inr"]
    assert k == _tiles("₹1,800", "₹3,800", "+₹2,000", "211%", "200", ["5", "1 Jan 2026 – 5 Jan 2026"],
                       "1 din ka spend data nahi", "₹ aaj ka rate; 1 din nahi padhe", ("—", "abhi koi din BE nahi hua (2 ads din)")) and _holds(k, rc) and exact
    assert table == [s, r] == [rc["S"], rc["R"]] and p == rc["P"] and line == out["k_usd"][1]
    # a ₹ view of a file not billed in ₹: $ × 100 on both sides — ₹2,000 / ₹3,800 → +₹1,800, the $ view's 190%
    k, (s, r, p, roas, exact), table, rc = out["k_inr_usd"]
    assert [x[1] for x in k[:4]] == ["₹2,000", "₹3,800", "+₹1,800", "190%"] and _holds(k, rc) and exact
    assert k[1][2] == "₹ aaj ka rate; 1 din nahi padhe"
    assert table == [s, r] == [rc["S"], rc["R"]] and p == rc["P"]


def test_totals_strip_owner_case(out):
    """🧾 The owner's case in its shape (a country in ₹, Google Ads country spend for about a year), on made-up rows: 30 old
    days with revenue and no spend data, 20 ads days at a loss, 5 ads-paused days (spend 0 + revenue), 3 ads days at a
    gain, the 2 newest days' so far not read yet; billed at ₹82 / 82.5 / 83 / 83.5 a $ by day, today ₹88. Profit / loss over
    the whole history = Total revenue − Total spend, exactly."""
    # $: Total spend 25 × $20 + 5 × $0 = $500 (the 30 old days left out, said); Total revenue 30 × $10 + 20 × $18 + 5 × $4 +
    # 3 × $30 = $770 (the 2 newest left out, said) → +$270, ROAS 154%
    k, cls, line, (s, r, p, roas, exact), rc, table = out["k_own_usd"]
    assert k == _tiles("$500", "$770", "+$270", "154%", "600", ["60", "1 Mar 2025 – 29 Apr 2025"],
                       "30 din ka spend data nahi", "2 din ki kamai abhi nahi padhi", ("—", "abhi koi din BE nahi hua (25 ads din)"))
    assert exact and r - s == p and _holds(k, rc) and cls[2:4] == [["roi-kg", "roi-up"], ["", "roi-g"]]
    assert line == "30 din ka spend data nahi (1 Mar 25 – 30 Mar 25) — unka spend jod me nahi, revenue hai."
    assert [rc[x] for x in ("S", "R", "P", "M", "K", "nsp", "nrv")] == [500, 770, 270, 30, 2, 30, 58] and table == [500, 770]
    # ₹ as billed: 20 × 5 × (1,640 + 1,650 + 1,660 + 1,670) + 1,670 + 1,640 + 1,650 + 1,660 + 1,670 = ₹41,390 (= Σ the Spend
    # column); Total revenue $770 × 88 = ₹67,760 (= Σ the So far column) → +₹26,370 to the rupee, ROAS 164%
    k, cls, line, (s, r, p, roas, exact), rc, table = out["k_own_inr"]
    assert k == _tiles("₹41,390", "₹67,760", "+₹26,370", "164%", "600", ["60", "1 Mar 2025 – 29 Apr 2025"],
                       "30 din ka spend data nahi", "₹ aaj ka rate; 2 din nahi padhe", ("—", "abhi koi din BE nahi hua (25 ads din)"))
    assert exact and r - s == p == 26370 and _holds(k, rc) and [rc[x] for x in ("S", "R", "P")] == [41390, 67760, 26370]
    assert table == [41390, 67760] and line == out["k_own_usd"][2]
    # a ₹ view of a file not billed in ₹: $ × 88 on both sides — +₹23,760, the $ view's 154%
    k, (s, r, p, roas, exact), rc = out["k_own_inr_usd"]
    assert [x[1] for x in k] == ["₹44,000", "₹67,760", "+₹23,760", "154%"] and exact and _holds(k, rc)
    assert [rc[x] for x in ("S", "R", "P")] == [44000, 67760, 23760]
    # a country in ₹ as billed with odd paise everywhere (15 old days with no spend data, 5 ads-paused, the 2 newest not
    # read): the printed tiles = an independent recount, Total revenue − Total spend = Profit / loss to the rupee; the
    # columns' sums agree up to each printed row's rounding
    k, line, (s, r, p, roas, exact), rc, (ts, tr) = out["k_cty_inr"]
    assert exact and _holds(k, rc) and [s, r, p] == [rc["S"], rc["R"], rc["P"]] and (rc["M"], rc["K"], rc["nsp"]) == (15, 2, 25)
    assert k[0][2] == "15 din ka spend data nahi" and k[1][2] == "₹ aaj ka rate; 2 din nahi padhe" and k[6] == ["Install days", "40", "1 Jun 2025 – 10 Jul 2025"]
    assert abs(ts - s) <= 0.5 * 25 and abs(tr - r) <= 0.5 * 38
    assert line == "15 din ka spend data nahi (1 Jun 25 – 15 Jun 25) — unka spend jod me nahi, revenue hai."
    k, (s, r, p, roas, exact), rc, want = out["k_cty_usd"]
    assert k == want and exact and _holds(k, rc) and [s, r, p] == [rc["S"], rc["R"], rc["P"]] and k[1][1] == "$201"
    assert k[1][2] == "2 din ki kamai abhi nahi padhi"


def test_totals_strip_states(out):
    """🧮 Every other state of the strip: All countries, spend-0 days, a moved rupee, crore-size ₹, a loss, no ads, no
    spend data at all, nothing; a country (its own recount), Unknown country, Not split; loading / error / missing; one
    height in every state; every value fits its box at every width."""
    # spend-0 days are in Total spend with their 0, their revenue in Total revenue — 3 × ($0, $100) + 3 × ($100, $80): $300,
    # $540 → +$240, ROAS 180%
    k, cls, line = out["k_zero"]
    assert [x[1] for x in k[:4]] == ["$300", "$540", "+$240", "180%"] and _holds(k) and k[0][2] == "Google Ads"
    assert cls == [["roi-kg", "roi-up"], ["", "roi-g"]] and line == ""
    # a ₹-billed file, the rupee moved (billed at ₹83, today ₹88), 2 days of $100 spend / $98 so far: $ −$4, 98%; ₹ = the
    # columns as printed — the bill 2 × ₹8,300, the so far at today's rate 2 × ₹8,624 → +₹648, 104% (the rupee's move)
    (kd, cd_), (ki, ci), rows = out["k_rate"]
    assert [x[1] for x in kd[:4]] == ["$200", "$196", "−$4", "98%"] and cd_ == [["roi-kb", "roi-dn"], ["", "roi-w"]]
    assert ki[:2] == [["Total spend", "₹16,600", "Google Ads"], ["Total revenue", "₹17,248", "so far · ₹ aaj ke rate se"]]
    assert [x[1] for x in ki[2:4]] == ["+₹648", "104%"] and ci == [["roi-kg", "roi-up"], ["", "roi-g"]]
    assert rows == [["₹8,300", "₹8,624 98%"]] * 2 and _holds(kd) and _holds(ki)
    # a loss: red
    k, cls = out["k_loss"]
    assert [x[1] for x in k] == ["$60", "$12", "−$48", "20%"] and cls == [["roi-kb", "roi-dn"], ["", "roi-b"]] and _holds(k)
    # no ads at all (spend 0 on every day): Total spend $0, its revenue — no profit / ROAS (never organic revenue as an ads
    # profit, never ∞ / 0%), said
    k, cls, line = out["k_org"]
    assert k == [["Total spend", "$0", "Is app me koi ads din nahi"], ["Total revenue", "$60", "so far · AdMob-matched"],
                 ["Profit / loss", "—", "spend 0 — profit / loss nahi"], ["ROAS", "—", "spend 0 — ROAS nahi"],
                 ["Avg breakeven", "—", "koi ads din nahi — BE nahi"],
                 ["Installs", "20", "GA4 · ads + organic"], ["Install days", "2", "1 Jan 2026 – 2 Jan 2026"]]
    assert cls == [["", ""], ["", ""]] and line == ""
    # no spend data on any day: '—' (never $0), its revenue, no profit / ROAS, the days said
    k, line = out["k_nosp"]
    assert [x[1] for x in k] == ["—", "$60", "—", "—", "—", "20", "2"] and k[0][2] == "2 din ka spend data nahi"
    assert k[2][2] == "spend nahi — profit / loss nahi" and k[3][2] == "spend nahi — ROAS nahi"
    assert line == "2 din ka spend data nahi (1 Jan 26 – 2 Jan 26) — unka spend jod me nahi, revenue hai."
    k, line = out["k_none"]
    assert [x[1] for x in k] == ["—"] * 6 + ["0"] and line == ""
    # a few paise of ₹-billed spend (its own ₹); a ₹-billed file whose rows have no ₹ spend (= the Spend column: today's rate)
    k, a = out["k_tiny"]
    assert k[:2] == [["Total spend", "₹1,760", "Google Ads"], ["Total revenue", "₹3,520", "so far · ₹ aaj ke rate se"]] and a[2] == 1760 and a[4]
    k, a, table = out["k_nobill"]
    assert [x[1] for x in k] == ["₹880", "₹1,056", "+₹176", "120%"] and a[4] and table == 880
    # All countries (the made-up app: spend known on all 70 days) = an independent recount; whatever the grain / mode /
    # "Show more"
    k, line, rc, (s, r, p, roas, exact) = out["k_all"]
    assert k == _tiles("$700", "$1,915", "+$1,215", "274%", "7,000", ["70", "5 Aug 2026 – 13 Oct 2026"],
                       be=["D9", "28 install din ka avg · median D9"]) and _holds(k, rc) and exact
    assert [rc[x] for x in ("S", "R", "P", "M", "K")] == [700, 1915, 1215, 0, 0] and line == ""
    assert out["k_inv"] == [True] * 24 and out["k_allcd"] == [True]
    # 🌍 a pick: '…' while its rows load (aria-busy), then its own totals = a recount of the rows its table shows (28 days
    # with no spend data in 2 runs: out of Total spend, their revenue in); the same every grain / mode; another country of
    # the same pack at once
    k, busy, done, msg, line = out["k_load"]
    assert [x[1] for x in k] == ["…"] * 7 and busy and done and msg and line == ""
    k, want, line, cnt, (s, r, p, roas, exact), table, same, rc = out["k_aa"]
    assert k == want and cnt == [70, 28, 0, 42, "2026-08-05", "2026-10-13"] and exact and _holds(k, rc)
    # (ROAS from the sums: Σ so far $799.50 ÷ $380 = 210% — the rounded $800 ÷ $380 would say 211%)
    assert [x[1] for x in k] == ["$380", "$800", "+$420", "210%", "—", "1,260", "70"] and k[0][2] == "28 din ka spend data nahi"
    # (its rows: no breakeven day, more 100%+ back with no day pinned than not even yet; = the recount)
    assert k[4] == ["Avg breakeven", "—", "BE din pakka nahi (38 ads din)"]
    # = Σ its Spend / So far columns over every row (each so far printed whole: ≤ $0.50 a row off)
    assert table[0] == 380 and abs(table[1] - 800) <= 0.5 * 70 and same
    assert line == "28 din ka spend data nahi (2 hisson me, 5 Aug 26 – 13 Oct 26) — unka spend jod me nahi, revenue hai."
    assert out["k_aa_inv"] == [True] * 12
    assert out["k_bb"][0] == out["k_bb"][1] and out["k_bb"][2]
    # "Unknown country": Google Ads has no such country → Total spend '—' (not 0), its revenue; profit / ROAS '—'
    k, want, line = out["k_unk"]
    assert k == want and k[0] == ["Total spend", "—", "Google Ads me ye country nahi"] and k[1][1] == "$888"
    assert [x[1] for x in k[2:4]] == ["—"] * 2 and k[2][2] == "spend nahi — profit / loss nahi"
    assert line == "70 din ka spend data nahi (5 Aug 26 – 13 Oct 26) — unka spend jod me nahi, revenue hai."
    # "Not split": spend only (its days with no spend data said); the rest '—'
    k, want, line, unk, n_rev = out["k_xx"]
    assert k == want and unk == 28 and n_rev == 0 and k[0] == ["Total spend", "$28", "28 din ka spend data nahi"]
    assert [x[1] for x in k[1:]] == ["—"] * 6 and k[1][2] == "Not split: koi kamai nahi"
    assert line == "28 din ka spend data nahi (2 hisson me, 5 Aug 26 – 13 Oct 26) — unka spend jod me nahi."
    # a pack that failed / a country the app does not have: '—' (no busy flag); an app without the country part: All's own
    k, not_busy, msg, line = out["k_err"]
    assert [x[1] for x in k] == ["—"] * 7 and not_busy and msg and line == ""
    assert out["k_miss"] == [["—"] * 7, True, ""] and out["k_nocd"] == [True, True]
    # ONE height in every state (69 made: loading, loaded, error, missing, ₹ / $, Unknown, Not split, loss, no ads, no
    # spend data, crore, the owner's case, a few cents of spend, 1,234 days, 🎯 every Avg breakeven case — its longest
    # reason and line too …): the same box — one grid, seven tiles, labels, the two lines' boxes, the note (the CSS pins
    # are in test_wiring; measured in headless Chrome: one height per width over every state, 360 – 2560 px, classic
    # scrollbar too, 22 Oct 2026 after the plain-median rule — no value / reason / line cut)
    assert out["k_skel"] == [1, 69]
    # crore-size ₹ printed in full — 14+ characters a size smaller (roi-ckw), shorter ones not; the arithmetic still exact
    big7, big8, small, n7, n8 = out["k_big"]
    assert big7 == ["₹23,45,76,190", "₹14,08,08,624", "−₹9,37,67,566", "60%", "—", "1,234,577", "2"]
    assert big8 == ["₹2,34,56,87,200", "₹1,40,80,08,624", "−₹93,76,78,576", "60%", "—", "1,234,577", "2"]
    assert small == [[False] * 7, [True, True, True, False, False, False, False]]
    assert n7[4] and n8[4] and n8[1] - n8[0] == n8[2]
    # every value printed in those states fits its box at EVERY width 360–2560 px (₹ crore, a classic scrollbar too), at its
    # own size (17 / 15.5 px, a 14+ character one 14 / 13 px); reasons ≤ 35 characters (two lines of the narrowest tile,
    # 131 px at 360, checked in Chrome) — ≤ 31 on the four tiles 3 columns wide from 900 px (116 px at 900 beside the
    # sidebar: the 31-character ones measured in two lines there); labels one short line
    pr = out["k_print"]
    assert len(pr) == 69 * 7 and any(v == "−₹93,76,78,576" for _, v, _, _ in pr) and any(v == "≤ D2025" for _, v, _, _ in pr)
    assert all(w == (len(v) >= 14) for _, v, w, _ in pr)
    tight = {}
    for w, sb, phone, box in _kpi_boxes():
        for lab, v, small, sub in pr:
            size = (13 if small else 15.5) if phone else (14 if small else 17)
            room = box(lab) - _px(v, size)
            if room < tight.get("room", 1e9):
                tight = {"room": room, "w": w, "sb": sb, "v": v, "lab": lab}
    assert tight["room"] >= 2, tight
    # (a reason's "<" is "&lt;" in the HTML: measured as the one character it shows). 🎯 Avg breakeven's reason up to 40
    # characters — "1,300 install din ka avg · median ≤D2001", "abhi koi din BE nahi hua (9,999 ads din)": measured in Chrome
    # in two lines of its narrowest box (116 px at 900 beside the sidebar; its count first, so a 4-digit count never
    # pushes a third line), every other width more room
    assert all(len(unescape(sub)) <= 35 and "<" not in sub and len(lab) <= 13 for lab, _, _, sub in pr if lab != "Avg breakeven")
    assert all(len(unescape(sub)) <= 31 for lab, _, _, sub in pr if lab not in _MONEY and lab != "Avg breakeven")
    be_subs = [sub for lab, _, _, sub in pr if lab == "Avg breakeven"]
    assert all(len(unescape(x)) <= 40 and "<" not in x for x in be_subs) and max(len(unescape(x)) for x in be_subs) == 40
    # the line under the tiles in every state: within its two fixed lines (Chrome: a 103-character line — 365 days, 12
    # runs — in two lines at 360 px and every width up to 2560); 🎯 Avg breakeven's line above it within ITS fixed lines
    # (4 up to 430 px, 3 to 899, 2 from 900): its longest, 191 characters (every count 4 digits, its fast cut too), measured
    # in Chrome in 4 lines at 360 / 375, 3 at 431 and 761 beside the sidebar (classic scrollbar), 2 at 900 — every state
    # every width 360–2560 px, none cut; no raw "<" in it
    assert all(len(x) <= 103 for x in out["k_lines"]) and max(map(len, out["k_lines"])) > 90
    bl = [unescape(x) for x in out["k_blines"]]
    assert all(len(x) <= 191 for x in bl) and max(map(len, bl)) == 191 and not any("<" in x for x in out["k_blines"])



def test_totals_strip_small_spend(out):
    """🧮 Review round (21 Oct 2026): a few cents of Google Ads spend under whole-unit revenue (a small country: stray clicks
    + organic revenue) — the spend printed with the Spend column's own cents (one precision for the three money tiles, so
    Profit / loss stays printed revenue − printed spend), never "$0" with "no ads days"; ROAS from the sums (= the So far
    column's so far ÷ spend on the same rows), not from the rounded tiles; the ₹ view says today's rate whatever the
    unread count."""
    (k1, c1, a1, col1, w1, r1), (k2, c2, a2, col2, w2, r2), (k3, c3, a3, col3, w3, r3) = out["k_cents"]
    # $0.12 + $0.18 + $0.10 (the Spend column prints each), so far $30 + $25 + $20: $0.4 · $75.0 → +$74.6, 18750%
    assert k1 == _tiles("$0.4", "$75.0", "+$74.6", "18750%", "30", ["3", "1 Jan 2026 – 3 Jan 2026"], be=("—", "3 din, sab spend &lt;$5")) == w1
    assert sorted(col1) == ["$0.10", "$0.12", "$0.18"] and a1[4] and _holds(k1, r1) and r1["dp"] == 1
    assert c1 == [["roi-kg", "roi-up"], ["", "roi-g"]]
    # 2 × $0.02, so far 2 × $2.50: two digits — $0.04 · $5.00 → +$4.96, 12500%
    assert k2 == _tiles("$0.04", "$5.00", "+$4.96", "12500%", "20", ["2", "1 Jan 2026 – 2 Jan 2026"], be=("—", "2 din, sab spend &lt;$5")) == w2
    assert col2 == ["$0.02"] * 2 and a2[4] and _holds(k2, r2) and r2["dp"] == 2
    # under a cent ($0.003 + $0, the column "$0.00"): the precision as it was, ≈ 0 said — not "no ads", no profit / ROAS
    assert k3 == w3 and [x[1] for x in k3[:4]] == ["$0", "$60", "—", "—"] and k3[0][2] == "Google Ads" and col3 == ["$0.00"] * 2
    assert k3[2][2] == "spend ≈ 0 — profit / loss nahi" and k3[3][2] == "spend ≈ 0 — ROAS nahi" and c3 == [["", ""], ["", ""]]
    # ROAS from the sums: [tiles, the So far cells, the printed numbers, what the strip must print, the recount]
    (v1, t1, b1, e1, q1), (v2, t2, b2, e2, q2), (v3, t3, b3, e3, q3) = out["k_roas"]
    # one day, $10.60 spend / $10.40 so far: $11 · $10 → −$1 (printed − printed), ROAS 98% = the So far cell's own 98%
    assert v1 == ["$11", "$10", "−$1", "98%"] and t1 == ["$10 98%"] and b1[4] and q1["ro"] == 98
    # 2 × $1.70 / 2 × $75: $3 · $150 → +$147, 4412% (= each row's 4412%; the rounded $3 would say 5000%)
    assert v2 == ["$3", "$150", "+$147", "4412%"] and t2 == ["$75 4412%"] * 2 and b2[4] and q2["ro"] == 4412
    # $0.90 + $0.50 / 2 × $100: $1 · $200 → +$199, 14286% (the rounded $1 would say 20000%)
    assert v3 == ["$1", "$200", "+$199", "14286%"] and b3[4] and q3["ro"] == 14286
    assert [[x[1] for x in e[:4]] for e in (e1, e2, e3)] == [v1, v2, v3]
    # the ₹ view, 1,234 install days, the newest 1,200 not read: "₹ aaj ka rate" with the 4-digit count, in 35 characters
    k, line = out["k_k4"]
    assert k[1] == ["Total revenue", "₹5,984", "₹ aaj ka rate; 1,200 din nahi padhe"] and len(k[1][2]) == 35
    assert [x[1] for x in k] == ["₹1,08,592", "₹5,984", "−₹1,02,608", "6%", "—", "12,340", "1,234"] and line == ""
    assert k[4] == ["Avg breakeven", "—", "1,234 din, sab spend &lt;$5"]     # ($1 a day: under the Status rule's $5)

def test_avg_breakeven(out):
    """🎯 Avg breakeven (owner, 22 Oct 2026: "average breakeven day ka KPI add kar do — jo country wise filter pe vo country
    ka milega … koi koi din ese ho jate he jo us din ka BE 2–5–10 din hota he — usko avg BE me exclude karna he taki muje
    actual BE mile … manlo 100 BE day he to 50% se kam din vale date ko count hi nahi karna"; then, over a young country's
    '—': "200 din me se 100 din me agar breakeven mila he to … vo 100 din ka kya avg he BE vo dikhana chaiye aur dikhao ki
    100 din abhi breakeven tak nahi pahoche"): over every install day of the table's source with ads — spend ≥ the file's
    min_spend (the Status rule's $5; a few cents of stray clicks are counted, never averaged) —, each day's breakeven
    exactly as the Breakeven column prints it; reached = the days with a breakeven day, whatever their age; median = the
    plain median of those days; a day that broke even before half of it is left out; Avg breakeven = the mean of the rest
    ("≤ D<n>" over any "≤ day"); '—' only under 3 reached. Its line: how many reached of how many ads days, the fast ones,
    the ones not even yet ("abhi BE tak nahi pahunche"), 100%+ back with no day, not read, under the floor — never one
    called another. The same in $ / ₹, every grain / mode; a country's own; on made-up rows, each = an independent recount
    (the harness's beRef / beText)."""
    # the hand case: 8 days broke even on 3, 5, 40, 50, 60, ≤ 90, 100, ≤ 120 (the Breakeven column's own cells, read back
    # from the table — with the $2 day's day 0); one not even ($4 of $10: "40% back"), one 100%+ back with no day ("120%
    # back", green), one old day not read ("—"), one new day not read; a $2 day (under $5), an ads-paused day, a day with no
    # spend data. Median of the 8: (50 + 60) / 2 = 55 — "≤" (the ≤ 90 and ≤ 120 days sit above it: the true median can only
    # be lower); 3 and 5 before 27.5: out; (40 + 50 + 60 + 90 + 100 + 120) / 6 = 76.7 → ≤ D77 (two "≤ day" in it)
    tile, line, ba, col, ref, sline, cells = out["abe_hand"]
    assert col == [0, 3, 5, 40, 50, 60, 90, 100, 120]
    assert cells == ['<td class="roi-na">40% back</td>', '<td class="roi-g">120% back</td>', '<td class="roi-na">—</td>', '<td class="roi-na">—</td>']
    assert {k: ba[k] for k in ("ads", "lo", "nr", "med", "mq", "cut", "fast", "kept", "inexact", "wait", "pend", "unread")} == {
        "ads": 12, "lo": 1, "nr": 8, "med": 55, "mq": "≤", "cut": 27.5, "fast": 2, "kept": 6, "inexact": 2, "wait": 1, "pend": 1, "unread": 2}
    assert round(ba["avg"], 6) == round(460 / 6, 6) and not any(k in ba for k in ("young", "mat", "H", "seen", "oldest"))
    assert tile == ["Avg breakeven", "≤ D77", "6 install din ka avg · median ≤D55"] and [tile, line] == ref
    # each day by its own why: the not-even day is the only "abhi BE tak nahi pahunche"; the green 120% one "100%+ back, din
    # pakka nahi"; both unread days (old and new alike) "kamai nahi padhi" — never "not even" for an unknown or an even day
    assert line == ("8 din BE hue (12 ads din me) · 2 jaldi BE (&lt;D28) avg se bahar · 1 din abhi BE tak nahi pahunche · "
                    "1 100%+ back, din pakka nahi · 2 kamai nahi padhi · 1 spend &lt;$5.")
    assert sline == "1 din ka spend data nahi (12 Jan 25) — unka spend jod me nahi, revenue hai."    # its own line, below
    # the same day in every grain × mode × "Show more" (24), in ₹ as billed and ₹ at today's rate (the ₹ view really on)
    inv, inr, inr_usd, spend_inr = out["abe_inv"]
    assert inv == [True] * 24 and inr == inr_usd == [tile, line] and spend_inr.startswith("₹")
    c = out["abe_cases"]
    for k, (t, ln, b, (rt, rl)) in c.items():                      # the page = the independent recount, every case
        assert [t, ln] == [rt, rl], k
        assert t[0] == "Avg breakeven" and (t[1] == "—") == (b["nr"] < 3), k   # '—' only under 3 reached
    T = {k: v[0][1:] for k, v in c.items()}
    L = {k: v[1] for k, v in c.items()}
    B = {k: v[2] for k, v in c.items()}
    # 🧑‍💼 the owner's example: 200 ads days, 100 reached (10 lucky on day 5, 45 on day 100, 45 on day 140), 100 not even.
    # Median D100 → the 10 before D50 out → (45 × 100 + 45 × 140) / 90 = D120; "100 din abhi BE tak nahi pahunche"
    assert T["owner"] == ["D120", "90 install din ka avg · median D100"]
    assert L["owner"] == "100 din BE hue (200 ads din me) · 10 jaldi BE (&lt;D50) avg se bahar · 100 din abhi BE tak nahi pahunche."
    assert (B["owner"]["ads"], B["owner"]["nr"], B["owner"]["fast"], B["owner"]["kept"], B["owner"]["wait"]) == (200, 100, 10, 90, 100)
    assert out["abe_owner_inv"] == [True] * 13                     # every grain × mode and ₹: the same tile and line
    # a young country (made up: every ads day in its last 300 days — the old 2 × median age rule gave '—'): 120 reached —
    # 20 on day 7, 30 on day 120, 70 on ≤ day 180 —, 180 not even, 15 days under $5. Median ≤ D180 → the 20 before D90
    # out → (30 × 120 + 70 × 180) / 100 = ≤ D162 — shown, never '—'
    assert T["young300"] == ["≤ D162", "100 install din ka avg · median ≤D180"]
    assert L["young300"] == ("120 din BE hue (300 ads din me) · 20 jaldi BE (&lt;D90) avg se bahar · 180 din abhi BE tak nahi "
                             "pahunche · 15 spend &lt;$5.")
    # the floor: exactly 3 reached — shown (10 before 20 out → D45); 2 reached — '—', said; none — '—' by why: not even
    # yet / 100%+ back with no day pinned / not read
    assert T["three"] == ["D45", "2 install din ka avg · median D40"] and L["three"] == "3 din BE hue (3 ads din me) · 1 jaldi BE (&lt;D20) avg se bahar."
    assert T["two"] == ["—", "sirf 2 din BE hue (7 ads din)"] and L["two"] == "2 din BE hue (7 ads din me) · 5 din abhi BE tak nahi pahunche."
    assert B["two"]["med"] is None and B["two"]["avg"] is None
    assert T["none"] == ["—", "abhi koi din BE nahi hua (2 ads din)"] and L["none"] == "0 din BE hue (2 ads din me) · 2 din abhi BE tak nahi pahunche."
    assert T["pend"] == ["—", "BE din pakka nahi (5 ads din)"]
    assert L["pend"] == "0 din BE hue (5 ads din me) · 2 din abhi BE tak nahi pahunche · 3 100%+ back, din pakka nahi."
    # none reached, the reason by the LARGER count — never "din pakka nahi" for a young country where nearly every day is
    # not even yet: 20 not even beside 3 100%+ back and 2 not read → "abhi koi din BE nahi hua"; a tie (2 and 2) → the same
    assert T["mostWait"] == ["—", "abhi koi din BE nahi hua (25 ads din)"]
    assert L["mostWait"] == ("0 din BE hue (25 ads din me) · 20 din abhi BE tak nahi pahunche · 3 100%+ back, din pakka nahi · "
                             "2 kamai nahi padhi.")
    assert (B["mostWait"]["wait"], B["mostWait"]["pend"], B["mostWait"]["unread"]) == (20, 3, 2)
    assert T["tie"] == ["—", "abhi koi din BE nahi hua (4 ads din)"] and (B["tie"]["wait"], B["tie"]["pend"]) == (2, 2)
    assert L["tie"] == "0 din BE hue (4 ads din me) · 2 din abhi BE tak nahi pahunche · 2 100%+ back, din pakka nahi."
    assert T["unread"] == ["—", "kamai abhi nahi padhi"] and L["unread"] == "0 din BE hue (3 ads din me) · 3 kamai nahi padhi."
    # an even count's median (10 … 60: 35, 10 before 17.5 out → D40); a day at exactly half the median stays (only
    # "before" half is out: D18); an odd count's median (40: 1 and 2 out → D50); nothing left out (62.5 → D63)
    assert T["five"] == ["D40", "5 install din ka avg · median D35"] and L["five"] == "6 din BE hue (6 ads din me) · 1 jaldi BE (&lt;D18) avg se bahar."
    assert T["half"] == ["D18", "5 install din ka avg · median D20"] and B["half"]["fast"] == 0 and L["half"] == "5 din BE hue (5 ads din me)."
    assert T["odd"] == ["D50", "5 install din ka avg · median D40"] and (B["odd"]["med"], B["odd"]["fast"], B["odd"]["avg"]) == (40, 2, 50)
    assert T["all"] == ["D63", "6 install din ka avg · median D63"] and B["all"]["med"] == B["all"]["avg"] == 62.5
    # only lucky fast days reached (6 of 40, day 2 … 10): their avg (median 4.5: day 2 out → D6), the 34 not even beside it
    assert T["lucky40"] == ["D6", "5 install din ka avg · median D5"]
    assert L["lucky40"] == "6 din BE hue (40 ads din me) · 1 jaldi BE (&lt;D3) avg se bahar · 34 din abhi BE tak nahi pahunche."
    # "≤": every day ≤ day 90 → ≤ D90, median ≤D90; a ≤ 120 above the median of 40 / 50 / 60 / ≤ 120 → median ≤D55, avg
    # 67.5 → ≤ D68; a ≤ 50 below the median (40, ≤ 50, 60, 70, 80) → median D60 exact, the avg ≤ D60; a ≤ 30 that is fast
    # (≤ 30, 60 … 90: median 70, cut 35) → out, neither "≤": D75
    assert T["le90"] == ["≤ D90", "30 install din ka avg · median ≤D90"] and L["le90"] == "30 din BE hue (30 ads din me)."
    assert T["leAbove"] == ["≤ D68", "4 install din ka avg · median ≤D55"]
    assert T["leKept"] == ["≤ D60", "5 install din ka avg · median D60"] and B["leKept"]["inexact"] == 1
    assert T["leFast"] == ["D75", "4 install din ka avg · median D70"] and (B["leFast"]["fast"], B["leFast"]["inexact"]) == (1, 0)
    # 10 real ads days ($50, ≤ day 60) + 12 days of a few cents (day 0): the cents days out, counted — ≤ D60, not D27
    assert T["stray"] == ["≤ D60", "10 install din ka avg · median ≤D60"] and L["stray"] == "10 din BE hue (10 ads din me) · 12 spend &lt;$5."
    # age never matters: 10 old days on day 100 + 5 days 70 days old on day 60 → median D100, (1,000 + 300) / 15 = D87,
    # their 5 not-even siblings said; 10 days only 20 days old, all on day 15 → D15
    assert T["young"] == ["D87", "15 install din ka avg · median D100"] and L["young"] == "15 din BE hue (20 ads din me) · 5 din abhi BE tak nahi pahunche."
    assert T["early"] == ["D15", "10 install din ka avg · median D15"]
    # a file whose min_spend is $20: its own floor (every day of $15 out, counted)
    assert T["floor20"] == ["D40", "5 install din ka avg · median D35"]
    assert L["floor20"] == "6 din BE hue (6 ads din me) · 1 jaldi BE (&lt;D18) avg se bahar · 1 spend &lt;$20."
    # 9,999 install days, every count with 4 digits (1,500 under $5, 1,200 lucky on day 2, 1,300 on ≤ day 100 … 149, 2,000
    # not even, 1,999 100%+ back, 2,000 not read): median ≤D101, the 1,200 before 50.5 out, mean 124.5 → ≤ D125
    tile, line, (rt, rl) = out["abe_big"]
    assert [tile, line] == [rt, rl] and tile == ["Avg breakeven", "≤ D125", "1,300 install din ka avg · median ≤D101"]
    assert line == ("2,500 din BE hue (8,499 ads din me) · 1,200 jaldi BE (&lt;D51) avg se bahar · 2,000 din abhi BE tak nahi "
                    "pahunche · 1,999 100%+ back, din pakka nahi · 2,000 kamai nahi padhi · 1,500 spend &lt;$5.")
    # the longest reason and line: the 1,300 on ≤ day 2,000 … 2,049 (its half 4 digits too) — 40 and 191 characters, each
    # measured in Chrome in its fixed lines; 9,999 ads days none of which broke even — 40 characters
    (gt, gl, gr), (nt, nl, nr) = out["abe_long"]
    assert [gt, gl] == gr and gt == ["Avg breakeven", "≤ D2025", "1,300 install din ka avg · median ≤D2001"]
    assert len(unescape(gl)) == 191 and "1,200 jaldi BE (&lt;D1001) avg se bahar" in gl
    assert [nt, nl] == nr and nt == ["Avg breakeven", "—", "abhi koi din BE nahi hua (9,999 ads din)"]
    assert nl == "0 din BE hue (9,999 ads din me) · 9,999 din abhi BE tak nahi pahunche."
    # no avg: no ads (spend 0 every day), no spend data, nothing at all — '—' with its reason, no line. All countries of the
    # made-up app: 28 days broke even on day 9 (6 of them younger than the old 2 × median age rule let in: age never
    # matters now), 9 not even, 33 100%+ back with no day pinned — named so, never "not even"
    g, gl, q, ql, z, zl, a, al, ref = out["abe_none"]
    assert g == ["Avg breakeven", "—", "koi ads din nahi — BE nahi"] and q == ["Avg breakeven", "—", "spend nahi — BE nahi"]
    assert z == ["Avg breakeven", "—", "ads din ke Breakeven ka avg"] and gl == ql == zl == ""
    assert a == ["Avg breakeven", "D9", "28 install din ka avg · median D9"] and [a, al] == ref
    assert al == "28 din BE hue (70 ads din me) · 9 din abhi BE tak nahi pahunche · 33 100%+ back, din pakka nahi."
    # 🌍 a country: '…' while its rows load, then ITS days (2, 10, 12, 14, 16, 18: median 13 → 2 out → D14; its $3 day
    # under the floor), the same in ₹ and every grain / mode; All again: All's own ≤ D77
    ld, busy, c_, cl, ci, civ, A, Al, cref = out["abe_cty"]
    assert ld == ["Avg breakeven", "…", "ads din ke Breakeven ka avg"] and busy
    assert c_ == ["Avg breakeven", "D14", "5 install din ka avg · median D13"] and [c_, cl] == cref
    assert cl == "6 din BE hue (6 ads din me) · 1 jaldi BE (&lt;D7) avg se bahar · 1 spend &lt;$5."
    assert ci == [c_, cl] and civ == [True] * 4
    assert A == tile_hand(out) and Al == out["abe_hand"][1]
    # Unknown country / Not split: '—' with why; a pack that failed / a country the app does not have: '—'; loading: '…'
    un, unl, xx, xxl, er, erl, ms, ldg, ldl = out["abe_cty_sp"]
    assert un == ["Avg breakeven", "—", "Google Ads me ye country nahi"] and xx == ["Avg breakeven", "—", "Not split: koi kamai nahi"]
    assert er == ms == ["Avg breakeven", "—", "ads din ke Breakeven ka avg"] and ldg == ["Avg breakeven", "…", "ads din ke Breakeven ka avg"]
    assert unl == xxl == erl == ldl == ""


def tile_hand(out):
    return out["abe_hand"][0]


def test_country_filter(out):
    # "All countries" (the default): every grain × mode, the Day view, the Countries board as pinned above
    assert out["cc_default_digest"] == GOLDEN_DEFAULT and out["cc_src_null"]
    assert out["cc_default_nort"] == GOLDEN_RET_CUT                 # 🔁 the retention lines cut: the page before them
    assert out["cc_default_nok"] == GOLDEN_DEFAULT_NOK              # … the rows' key the only change (Show 60 more)
    assert out["cc_default_nokpi_nok"] == GOLDEN_PRE_KPI            # … the key + the strip cut: the page before both
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
    assert out["cc_q_new"] and out["cc_pick_sel"]                  # bit 64 said (32 gone); one option selected
    # GA4: country not given (cd.ng): its total (signed), the matched months and the app-k months with their sums
    assert out["cc_ng"] == [True] * 9, out["cc_ng"]
    # 🧩 Not split: D0 … D30 day by day like every country, its cells '—' (as the note says)
    assert out["cc_xx_cols"] == [35, "D1", "D2", "D30", False, True, True, True]
    assert all(out["cc_noq"]) and out["cc_to"] and all(out["cc_nocd"]) and all(out["cc_tz"])
    assert out["cc_zx_guard"]                                       # a row past the index's last day: never expanded
    # a pack of another build than the index (its "b"): the app file read again once, then its own pack; a pack gone
    # from the site (404): the same; the site still on the other build after it: said, "Try again"
    assert all(out["cc_stale"]) and all(out["cc_gone"]) and all(out["cc_stale_again"])
    assert out["cc_lru"] == [3, True, 3, True, True]                # only the newest 3 packs kept (the one in use too)


def test_country_order_by_spend(out):
    # 💸 the owner, 22 Oct 2026: "country list he vo spending wise kar do" — chips + the list by the whole history's
    # Google Ads spend high → low, one order per app in every view (a ₹ / $ switch never reorders): ₹ as billed for an
    # app billed in ₹ (the money it paid; USD at each day's rate puts CC $52 above GG $50 while GG paid ₹4,400 > CC
    # ₹4,300), else USD; equal spend by installs, then code; no spend (0 or not known alike) after every spender, by
    # installs, then code; under a cent still a spender; Unknown country / Not split last, never chips
    chips_b, chips_u = ["", "JJ", "BB", "GG", "CC", "AA", "FF"], ["", "JJ", "BB", "CC", "AA", "GG", "FF"]
    tail = ["DD", "II", "EE", "HH", "--", "XX"]
    order_b, order_u = chips_b + tail, chips_u + tail
    want = {  # view → (chips, list, the list's header): the two views of the ₹-billed app share one order
        "usd": (chips_b, order_b, "Every country (10) · most spend first (₹ as billed)"),
        "inr_billed": (chips_b, order_b, "Every country (10) · most spend first"),
        "inr_usd_billed": (chips_u, order_u, "Every country (10) · most spend first")}
    sp = out["cc_spend"]
    lab = {   # the label: spend in the view's currency (₹ as billed / $ / ₹ at the view rate), whole numbers, installs
        "usd": {"JJ": "$1,235 spend", "BB": "$80 spend", "AA": "$50 spend", "CC": "$52 spend", "GG": "$50 spend",
                "FF": "&lt;$0.01 spend"},
        "inr_billed": {"JJ": "₹1,23,457 spend", "BB": "₹6,500 spend", "AA": "₹4,100 spend", "CC": "₹4,300 spend",
                       "GG": "₹4,400 spend", "FF": "₹0.35 spend"},
        "inr_usd_billed": {"JJ": "₹1,08,642 spend", "BB": "₹7,040 spend", "AA": "₹4,400 spend", "CC": "₹4,576 spend",
                           "GG": "₹4,400 spend", "FF": "₹0.35 spend"}}
    inst = {"JJ": "30", "BB": "900", "AA": "1,000", "CC": "800", "GG": "400", "FF": "500", "DD": "700", "II": "700",
            "EE": "600", "HH": "400"}
    amt = lambda t: 0.005 if t.startswith("&lt;") else float(re.sub(r"[^0-9.]", "", t.split(" ")[0]))
    assert set(sp) == set(want)
    for v, picks in sp.items():
        chips, order, grp = want[v]
        for k, p in picks.items():
            # whatever is picked: the same chips / list / header
            assert p["chips"] == chips and p["list"] == order and p["grp"] == grp, (v, k, p["chips"], p["list"], p["grp"])
            for cc, s in lab[v].items():
                assert p["opt"][cc] == "[%s] Country %s · %s · %s installs" % (cc, cc, s, inst[cc]), (v, k, cc)
            for cc in ("DD", "HH"):
                assert p["opt"][cc] == "[%s] Country %s · no ads · %s installs" % (cc, cc, inst[cc]), (v, k, cc)
            for cc in ("II", "EE"):                                   # not known: never "no ads"
                assert p["opt"][cc] == "[%s] Country %s · spend not known · %s installs" % (cc, cc, inst[cc]), (v, k, cc)
            assert p["opt"]["--"] == "[--] Unknown country · 40 installs" and p["opt"]["XX"] == "🧩 Not split"
            assert p["title"] == "Country JJ · %s · 30 installs" % lab[v]["JJ"].replace("&lt;", "<")
        # the amounts the list prints fall in step with its order — except the $ view of the ₹-billed app, whose header
        # says the order is ₹ as billed (there GG $50 sits above CC $52)
        shown = [amt(lab[v][cc]) for cc in order if cc in lab[v]]
        assert (shown == sorted(shown, reverse=True)) == ("(₹ as billed)" not in grp), (v, shown)
        # what is picked stays picked: All / a chip → "More countries" in the box, the list on "More countries"; a
        # list country → its option selected, its full label in the box (on); Unknown / Not split the same; a country
        # this app does not have → "More countries"
        assert [picks["none"]["sel"], picks["none"]["shown"], picks["none"]["on"], picks["none"]["pressed"]] == [[""], "More countries", False, ""]
        assert [picks["chip"]["sel"], picks["chip"]["shown"], picks["chip"]["on"], picks["chip"]["pressed"]] == [[""], "More countries", False, "JJ"]
        assert [picks["list"]["sel"], picks["list"]["shown"], picks["list"]["on"], picks["list"].get("pressed")] == [
            ["DD"], "[DD] Country DD · no ads · 700 installs", True, None]
        assert [picks["unk"]["sel"], picks["unk"]["shown"], picks["unk"]["on"]] == [["--"], "[--] Unknown country · 40 installs", True]
        assert [picks["ns"]["sel"], picks["ns"]["shown"], picks["ns"]["on"]] == [["XX"], "🧩 Not split", True]
        assert [picks["gone"]["sel"], picks["gone"]["shown"], picks["gone"]["on"]] == [[""], "More countries", False]
    # a ₹ / $ switch never reorders: the ₹-billed app's $ and ₹ views list the same countries in the same order
    assert sp["usd"]["none"]["list"] == sp["inr_billed"]["none"]["list"] and sp["usd"]["none"]["chips"] == sp["inr_billed"]["none"]["chips"]
    # the order is the page's own: the index's rows in any order give the same chips and list (the two that are not a
    # country keep the index's order); no app currency → USD
    assert out["cc_spend_rev"] == [chips_u, order_u[:-2] + ["XX", "--"]]
    # a ₹-billed app's index without ₹ for one spender: USD for every row (never ₹ against $), header without the note
    for v, m in out["cc_spend_mixed"].items():
        assert m == {"list": order_u, "grp": "Every country (10) · most spend first"}, (v, m)
    # no country spent: by installs, then code, and the header says so (never "most spend first")
    for v, m in out["cc_spend_none"].items():
        assert m == {"chips": ["", "QQ", "RR", "PP", "SS"], "list": ["", "QQ", "RR", "PP", "SS", "--"],
                     "grp": "Every country (4) · most installs first", "opt": "[QQ] Country QQ · spend not known · 90 installs"}, (v, m)
    # spend order on a tapped page: HH (the fewest installs, the most spend) first; the full tap run (AA / EE chips,
    # GG from the list, the board) and the new order's own taps (HH chip, DD from the list, HH, back to All) — the
    # tapped control stays put at 375 and 1280 px, and the pick shows where it should
    nj = out["cc_spend_nojump"]
    assert nj["chips"] == ["", "HH", "EE", "AA", "BB", "CC", "FF"]
    for w in ("w375", "w1280"):
        assert nj[w]["moves"] == [0] * 13 and nj[w]["keptWeek"] and nj[w]["backAll"] and nj[w]["picked"], (w, nj[w])
        assert nj[w]["errShown"] and nj[w]["retried"], (w, nj[w])
    for w in ("t375", "t1280"):
        assert nj[w]["moves"] == [0] * 8, (w, nj[w])
        assert nj[w]["seen"] == [["HH", "HH", "", "More countries"], ["DD", None, "DD", "[DD] Country DD · no ads · 700 installs"],
                                 ["HH", "HH", "", "More countries"], ["", "", "", "More countries"]], (w, nj[w])


def test_country_list_label_never_cut():
    # the native list sits invisible over its own label: the picked country's spend / installs wrap there (between
    # words, never inside a number), never clipped or ellipsed at 375 px; iOS: the list itself still 16px on a phone (no
    # zoom). The box one fixed width (capped by its row), never as wide as the picked label: a pick never moves the box
    # to another row or another left edge (measured in Chrome with the page CSS at 320-1920 px: only its height
    # changes); the segs after it keep their own height when it grows a line
    with open(PAGE, encoding="utf-8") as f:
        p = f.read()
    css = p[p.index("<style>"):p.index("</style>")]
    assert ".roi-ccv{min-width:0;overflow-wrap:break-word}.roi-cca{flex:none}.roi-ccw~.roi-mini{align-self:flex-start}" in css
    assert ".roi-ccs{position:absolute;inset:-1px;width:calc(100% + 2px);height:calc(100% + 2px);margin:0;padding:0;border:0;opacity:0;" in css
    ccw = re.findall(r"\.roi-ccw\{[^}]*\}", css)
    assert ccw[0].startswith(".roi-ccw{position:relative;display:inline-flex;align-items:center;justify-content:space-between;gap:8px;align-self:flex-start;width:min(100%,30em);min-height:34px;")
    for rule in re.findall(r"\.roi-ccw[^{]*\{[^}]*\}", css):                # nothing sizes the box by its label
        assert not re.search(r"(?<![-\w])(?:max-|min-)?width:(?!min\(100%,30em\))", rule) and "fit-content" not in rule and "flex:" not in rule, rule
    for rule in re.findall(r"\.roi-cc[wva][^{]*\{[^}]*\}", css):
        assert "nowrap" not in rule and "ellipsis" not in rule and "overflow:hidden" not in rule, rule
    assert "@media (max-width:760px){.roi-ccs{font-size:16px}}" in css
    assert ('<span class="roi-ccw${pk?\' on\':\'\'}"><span class="roi-ccv" aria-hidden="true">${pk?lab(pk):\'More countries\'}</span>'
            '<span class="roi-cca" aria-hidden="true">▾</span>') in p
    assert "`<select class=\"roi-ccs\" data-roi-ccs=\"1\" aria-label=\"Every country\">" in p


def test_show_more_keeps_the_row(out):
    """"Show 60 more" / "Show all" (owner, 21 Oct 2026: "show 60 more krte he to table pehle se scroll hoke uppar se start
    hota he"): the table's own box (at most 640px, scrolls down and sideways) came back at the top and the left after the
    repaint — the reader's row 600–5000 px away inside it, out of sight. Now the last row in sight stays where it was
    (≤ 1 px) and the box keeps its sideways scroll, at 375 and 1280 px: every grain × mode of the All countries table, every
    country's table (Not split too), the lifetime "Every day" table; the page itself does not move and the stay-put layer
    adds no scroll; when something above the table grows in the same repaint, the page takes it back — one scroll in all.
    (On the page before this fix: moves of 631–5008 px and scrollLeft 260 → 0 — this test fails there.)"""
    mk = out["more_keep"]
    assert [len(mk[k]) for k in ("coh", "cty", "life", "grow")] == [48, 64, 4, 2]
    taps = [(r["name"], t) for k in ("coh", "cty", "life") for r in mk[k] for t in r["taps"] if not t.get("gone")]
    assert len(taps) == 152                                                    # 80 + 64 + 8 taps
    for name, t in taps:
        assert abs(t["move"]) <= 1 and t["inView"], (name, t)                 # the reader's row: where it was
        assert t["sl"][1] == t["sl"][0], (name, t)                             # the box's sideways scroll kept
        assert t["dy"] == 0 and t["calls"] == 0 and not t["intent"], (name, t)   # no page scroll at all (ours or the layer's)
        assert t["rows"][1] > t["rows"][0] and t["idx"][1] == t["idx"][0], (name, t)   # the new rows below it, none above
        assert t["key"], (name, t)                                             # found by the page's own key too
    # the install-day tables are wider than their box at both widths: the reader had really scrolled them sideways
    assert all(t["sl"] == [260, 260] for k in ("coh", "cty") for r in mk[k] for t in r["taps"] if not t.get("gone"))
    # every step ran: Day / Week 60 → 120 → 180 → all, Month (67 months) 60 → all (then no button); "Show all" at once
    full = {"day": 334, "week": 287, "month": 67}
    for r in mk["coh"]:
        g, steps = r["name"].split()[1], [t.get("rows") for t in r["taps"]]
        if r["name"].endswith("60+60+all"):
            assert steps == ([[60, 120], [120, 180], [180, full[g]]] if g != "month" else [[60, 67], None]), r["name"]
        else:
            assert steps == [[60, full[g]]], r["name"]
    assert all([t["rows"] for t in r["taps"]] == [[60, 70]] for r in mk["cty"])   # a country's 70 install days
    assert [[t["rows"] for t in r["taps"]] for r in mk["life"]] == [[[60, 120], [120, 180], [180, 199]], [[60, 199]]] * 2
    # something above the table grew in the same repaint: the row still in place, the page scrolled by it once — the
    # page's own code (intentional for the stay-put layer, which then adds nothing)
    for r in mk["grow"]:
        assert len(r["taps"]) == 2, r
        for t in r["taps"]:
            assert abs(t["move"]) <= 1 and t["dy"] > 0 and t["calls"] == 1 and t["intent"] and t["sl"] == [260, 260], (r["name"], t)


def _side_kept(t):
    """The box's sideways place after a repaint, as the reader sees it: at the left start → still 0; at the right end
    ("So far" in sight) → still at the right end; else the column under the box's visible right edge (gone → the next one
    to its left) at the same x, ≤ 1 px."""
    c = t["col"]
    if t["sl"][0] <= 1:
        return t["sl"][1] == 0
    if c["end"][0]:
        return c["end"][1] is True
    return c["x"] is not None and abs(c["x"][1] - c["x"][0]) <= 1 and (c["gone"] or c["lab"] == c["edge"])


def test_show_more_keeps_the_column(out):
    """Review (21 Oct 2026): the Day table's columns past D30 come and go with the rows shown (a month column per 30 days
    of the oldest shown day; T's late checkpoints only while no shown day has the late read) and every column is as wide
    as its widest cell — the old pixel scrollLeft put another column under the reader. Now the column at the box's right
    edge stays at its x (≤ 1 px; gone → the next one left), the right end stays the right end, the start the start: every
    grain at the right end, a file whose 60 → 120 step changes the columns (41 → 49 headers, D365 gone), the lifetime
    table; 375 and 1280 px. The row stays put too, no page scroll. (On the page before: "So far" 96–384 px off to the
    right, the reader's column 96 px away — this test fails there.)"""
    mk = out["more_keep"]
    side = [(r["name"], t) for r in mk["side"] for t in r["taps"] if not t.get("gone")]
    assert len(mk["side"]) == 34 and len(side) == 60
    for name, t in side:
        assert abs(t["move"]) <= 1 and t["inView"], (name, t)
        assert t["dy"] == 0 and t["calls"] == 0 and not t["intent"], (name, t)
        assert t["rows"][1] > t["rows"][0], (name, t)
        assert _side_kept(t), (name, t)
    by = {}
    for r in mk["side"]:
        by[r["name"]] = [t for t in r["taps"] if not t.get("gone")]
    for w in ("375", "1280"):
        # at the right end ("So far" in sight, the box really scrolled): still the right end, "So far" still the edge column
        for g in ("day", "week", "month"):
            for t in by[f"{w} {g} max 60+60+all"] + by[f"{w} {g} max all"]:
                assert t["col"]["end"] == [True, True] and t["col"]["edge"] == "So far" and t["sl"][0] > 300, (w, g, t)
        # the columns really changed with the rows shown (D365 among the first 60's columns only)
        for nm in ("max", "D90", "D20", "0"):
            assert by[f"{w} m400 {nm} all"][0]["col"]["n"] == [41, 49], (w, nm)
            assert by[f"{w} m400 {nm} 60+60+all"][0]["col"]["n"] == [41, 49], (w, nm)
        for t in by[f"{w} m400 D365 60"] + by[f"{w} m400 D365 all"]:
            assert t["col"]["edge"] == "D365" and t["col"]["gone"] and t["col"]["lab"] == "D180", (w, t)   # → the next one left
        for nm in ("D90", "D20"):
            for t in by[f"{w} m400 {nm} 60+60+all"] + by[f"{w} m400 {nm} all"]:
                assert t["col"]["edge"] == nm and t["col"]["lab"] == nm and t["sl"][0] > 300, (w, nm, t)
        for t in by[f"{w} m400 max all"] + by[f"{w} m400 max 60+60+all"]:
            assert t["col"]["end"] == [True, True], (w, t)
        for t in by[f"{w} m400 0 all"] + by[f"{w} m400 0 60+60+all"]:
            assert t["sl"] == [0, 0], (w, t)
    assert [t["col"]["end"] for t in by["375 life max"]] == [[True, True]] * 2      # the lifetime table (wider than a phone)


def test_mode_switch_keeps_the_box(out):
    """Review (21 Oct 2026): Mode (ROAS % / Revenue / Per install / Delta) repainted the table into a new box — back at row
    1, column 1 ("table pehle se scroll hoke uppar se start hota he" again, after "Show all" too), while the page stayed.
    Now the same rows keep their place: the reader's row ≤ 1 px, the right-edge column at its x (the columns get wider /
    narrower with the mode), the right end the right end; every grain after "Show all", 60 shown, a country's table and
    Not split; 375 and 1280 px; no page scroll (ours or the stay-put layer's). (On the page before: the row 631–4878 px
    away, out of sight, and scrollLeft back to 0 — this test fails there.)"""
    mk = out["more_keep"]
    met = [(r["name"], t) for r in mk["met"] for t in r["taps"] if not t.get("gone")]
    assert len(mk["met"]) == 24 and len(met) == 92
    for name, t in met:
        assert t["rows"][1] == t["rows"][0] and t["idx"][1] == t["idx"][0], (name, t)   # the same rows
        assert abs(t["move"]) <= 1 and t["inView"] and t["key"], (name, t)
        assert t["dy"] == 0 and t["calls"] == 0 and not t["intent"], (name, t)
        assert _side_kept(t), (name, t)
    rows = {r["name"]: r["taps"][0]["rows"][0] for r in mk["met"]}
    assert rows["375 day max met"] == 334 and rows["1280 week D270 met"] == 287 and rows["375 day 60 met"] == 60
    assert rows["375 AA met"] == 70 and rows["1280 XX met"] == 70
    # the box was really scrolled sideways (not at its start) in all but the 1280 px week / month D30 runs (D30 in sight at 0)
    assert all(t["sl"][0] > 100 for n, t in met if not n.startswith(("1280 week D30", "1280 month D30")))


def _rt(v, title=None, cls=""):
    """One retention line as the page writes it (title None: "—", not measured)."""
    if title is None:
        return '<span class="roi-rt roi-rtna">—</span>'
    return '<span class="roi-rt%s" title="%s">%s</span>' % (cls, title, v)


def test_retention_cells(out):
    """🔁 Retention in every D cell (owner, 22 Oct 2026: "isme jo day 0,1,2… cohort table he usme yahi box me small text
    me retention add karna he"; All countries D1–D30 now, countries and D60+ once their data is in the file): a small second
    line = the install day's users active on that day ÷ its GA4 new users (u[L] ÷ n; past D30 mu[j] ÷ n) — the same ratio
    as roi_build._ret (pooled Σu ÷ Σn), without its fallback to the install-day file's iu. Real data only: not measured →
    "—", never 0; no line on D0 and on T's checkpoint columns past D30 (no users source there)."""
    # Day: the row's own; D0 nothing (the install day itself); 4.5% (one decimal under 10%); a real 0 of 200 users is 0%;
    # u[4] not measured → —; D10 / D12 not final (L ≥ df = 10): the cell is faded, the line fades with it (never twice)
    assert out["rt_day"] == ["", _rt("40%", "D1 retention: 80 of 200 users"), _rt("4.5%", "D2 retention: 9 of 200 users"),
                             _rt("0%", "D3 retention: 0 of 200 users"), _rt(None), _rt("20%", "D5 retention: 40 of 200 users"),
                             _rt("20%", "D10 retention: 40 of 200 users · not final"),
                             _rt(None)]                 # D12 lands on the file's newest day (today, still counted): —
    assert out["rt_day_td"] == ["roi-g roi-nf", '<td class="roi-na">·</td>', False]   # past what was read: · alone
    # no u at all → —; no installs (n 0) → —, never 0%; under 0.1% said so (escaped), 30,000 of 100,000 → 30%
    assert out["rt_day_none"] == [_rt(None), _rt(None), _rt("&lt;0.1%", "D1 retention: 50 of 100,000 users"),
                                  _rt("30%", "D2 retention: 30,000 of 100,000 users")]
    assert out["rt_day_zero"]
    # users read only up to D1 (null past the read edge, every day final): "—" there, never 0%
    assert out["rt_day_pad"] == [_rt("25%", "D1 retention: 50 of 200 users"), _rt(None), _rt(None)]
    # the file's newest day (today) is still being counted: a column landing on it shows —, never 0 % (its users not read yet)
    assert out["rt_today"] == [_rt(None), _rt("20%", "D1 retention: 20 of 100 users"), _rt(None)]
    # every mode (ROAS % / Revenue / Per install / Delta): the same lines; the main values never depend on u
    assert out["rt_modes"] == [[True, True, True]] * 4
    # … also where the mode has no number ("·": ROAS % with no spend, Per install with no installs): "—" when not measured,
    # the value when it is, in every mode alike; a day not reached: "·" alone; D0: no line
    assert out["rt_modes_na"] == [True, [[_rt(None), ""], [_rt(None), ""], [_rt("40%", "D1 retention: 40 of 100 users"), ""],
                                         '<td class="roi-na">·</td>']]
    assert out["rt_modes_na_td"] == ['<td class="roi-na">·' + _rt(None) + "</td>",
                                     '<td class="roi-na">·' + _rt("40%", "D1 retention: 40 of 100 users") + "</td>",
                                     '<td class="roi-na">·' + _rt(None) + "</td>", '<td class="roi-na">·</td>']
    # week: pooled Σu ÷ Σn over the install days whose day is final (7–13 Sep: a day without u left out — final); final
    # only once no day with users still has that day to come: 5–11 Oct D3 = 2 of 3 final → their 30%, NOT final (the
    # third still to come; the cell faded too, the line with it); none final yet → over those seen, faded on a "·" cell;
    # nothing: · alone
    nf = "D3 retention: 60 of 200 users · 2 of 3 install days (the final ones) · not final"
    # (the third day's D7 lands on the file's newest day — still counted, left out: 1 of 3)
    d7 = _rt("10%", "D7 retention: 10 of 100 users · 1 of 3 install days · not final", " roi-rtnf")
    assert out["rt_week"] == [_rt("25%", "D1 retention: 100 of 400 users · 2 of 3 install days"),
                              _rt("15%", "D3 retention: 60 of 400 users · 2 of 3 install days"),
                              _rt("33%", "D1 retention: 100 of 300 users · 3 of 3 install days"), _rt("30%", nf),
                              "roi-b roi-nf", '<td class="roi-na">·' + d7 + "</td>", '<td class="roi-na">·</td>', ""]
    assert out["rt_month"] == [_rt("25%", "D1 retention: 100 of 400 users · 2 of 3 install days"),
                               _rt("33%", "D1 retention: 100 of 300 users · 3 of 3 install days"), _rt("30%", nf), d7]
    # the cell faded by a day WITHOUT users (its revenue not final): the line says not final (faded with the cell, never
    # "final" under a faded value); a day with users still to read (u only [u0]) → the final one's value, not final, faded
    assert out["rt_week_nf"] == ["roi-b roi-nf", _rt("30%", "D1 retention: 30 of 100 users · 1 of 2 install days · not final"),
                                 "roi-b", _rt("30%", "D1 retention: 30 of 100 users · 1 of 2 install days (the final ones) · not final",
                                              " roi-rtnf")]
    # the Hinglish legend per grain, once, after the box and its "Show more" (keepRows / metBox: the box's neighbours as
    # before), before the Breakeven line
    assert out["rt_legend"] == [True] * 5
    # past D30: mu[j] ÷ n (final while j < mf, as m — D90 faded with its cell); a row without mu / a null entry → —;
    # D30 of a row without u → —; no checkpoint column past D30 → the legend names none
    assert out["rt_m"] == ["D60,D90,So far", _rt("30%", "D60 retention: 30 of 100 users"),
                           _rt("20%", "D90 retention: 20 of 100 users · not final"), "roi-g roi-nf", _rt(None), _rt(None), _rt(None),
                           _rt("10%", "D90 retention: 5 of 50 users"), _rt(None), True]
    # a file without m: T's checkpoints past D30 have no users source → no line (never a "—" waiting for nothing), named
    # in the legend; D1 … D30 as before
    assert out["rt_tcol"] == ["D60,D90,D180,D365,So far", ["", "", "", "", _rt(None), _rt(None)], False, True]
    # a country: no u / only u0 / a short row (zx: no installs) → — and one line saying its users are not in yet; with u
    # → its own; Not split: no line, no legend; users past day 0 all null (not read) → still "not in yet", —
    assert out["rt_cty"] == [True, [_rt(None), _rt(None), _rt(None)], True, _rt("25%", "D1 retention: 5 of 20 users"), True, True,
                             True, True, _rt(None)]
    # the page's own pieces: the line inside the cell after its value (all four modes); a "·" cell keeps the line when
    # the day's value is there (only the mode has no number) or when retention was seen; the legend after the box +
    # "Show more"; CSS: a block line, small, faded only when the cell is not; every cell's first line on the baseline
    with open(PAGE, encoding="utf-8") as f:
        p = f.read()
    assert "${fmtCell(x,MET)}${xx?'':retLn(rt,c,gr,!fin,!fin)}</td>`; }).join('');" in p
    assert "`<td class=\"roi-na\">·${ok(v)||rt?retLn(rt,c,gr,!fin,false):''}</td>`" in p
    assert "</table></div>${more}`\n    +(xx?'':retNote(d.rows,src&&src.rows?src.cc:'',C))" in p
    assert ".roi-t td .roi-rt{display:block;margin-top:1px;font-size:10.5px;line-height:1.2;font-weight:500;color:var(--ink2)}" in p
    assert ".roi-t td .roi-rtnf{opacity:.62;font-style:italic}.roi-t td .roi-rtna{color:var(--faint)}" in p
    assert ".roi-heat td{padding-top:5px;padding-bottom:5px;line-height:1.3;vertical-align:baseline}" in p
    assert "const R={X:0,n:1,na:2,sp:3,d:4,df:5,u:6,t:7,s:8,sd:9,be:10,st:11,q:12,spi:13,m:14,mf:15,mu:16};" in p


_QO = "GA4 ne us din kuch users kisi country ko nahi diye (&#39;(other)&#39;) — ye % kam ho sakta hai"
_QF = "GA4 ka read sampled / thresholded tha"


def test_retention_users_marks(out):
    """👥 ≈ on a country's small number (owner, 22 Oct 2026: real data only — what GA4 did not attribute is said with its
    size, never hidden): the file's cd "uu" "ou_r" / "fl_r" = runs of activity days on which GA4 put users into "(other)"
    (no install day / no country) / flagged the read (sampled / thresholded). A line whose activity day (install day + its
    age; a 30-day column: the column's day) is in a run gets "≈" and says why in its title; a week / month line when any
    install day it POOLED is on one; the legend's one line (only when a number on screen got ≈) counts the days of each
    kind from the runs, with the "(other)" users' size. All countries: no ≈ from users — GA4's whole reads' users with no
    install day (late "u" "qou" > 0) said once with their size. Without these fields: every byte as before."""
    # Day: runs "(other)" 3 Oct + 8–9 Oct, flagged 5 Oct + 9 Oct (given out of order, one twice); install day 1 Oct:
    # D2 = 3 Oct, D4 = 5 Oct, D7 = 8 Oct, D8 = 9 Oct (both reasons); 5 Jul's D60 = 3 Sep (none), D90 = 3 Oct; a row
    # without users: — (no ≈ on a number that is not there)
    assert out["rt_uu_day"] == [
        _rt("50%", "D1 retention: 10 of 20 users"), _rt("≈ 40%", "D2 retention: 8 of 20 users · ≈ " + _QO),
        _rt("30%", "D3 retention: 6 of 20 users"), _rt("≈ 25%", "D4 retention: 5 of 20 users · ≈ " + _QF),
        _rt("20%", "D6 retention: 4 of 20 users"), _rt("≈ 20%", "D7 retention: 4 of 20 users · ≈ " + _QO),
        _rt("≈ 20%", "D8 retention: 4 of 20 users · ≈ " + _QO + " · " + _QF), _rt("20%", "D9 retention: 4 of 20 users"),
        _rt("30%", "D60 retention: 30 of 100 users"), _rt("≈ 20%", "D90 retention: 20 of 100 users · ≈ " + _QO), _rt(None)]
    # a day not final yet: its own line still gets its ≈ (Day: the row's own number)
    assert out["rt_uu_day_nf"] == _rt("≈ 10%", "D1 retention: 10 of 100 users · not final · ≈ " + _QF)
    # the legend: one line inside the legend paragraph (3 "(other)" days after merging, 7 users; 2 flagged days); only
    # the kind on screen; no number marked → no line, the table byte for byte as without "uu"
    assert out["rt_uu_legend"] == [True, 1, 1, True, True]
    # the revenue cells, the rows' own ≈ and every other byte unchanged: only the small numbers and the legend's line
    assert out["rt_uu_only"] == [True, True, True]
    # week: 28 Sep–4 Oct D1 pools 29 Sep's D1 = 30 Sep ("(other)") → ≈ (1 install day); D3 none; 21–27 Sep D1: 22 Sep's
    # D1 (23 Sep, flagged) is not final → not pooled → no ≈; D3: 21 Sep's D3 (24 Sep, flagged, final, pooled) → ≈
    wk = " · 2 of 2 install days"
    one = " · 1 of 2 install days (the final ones) · not final"
    assert out["rt_uu_week"] == [_rt("≈ 30%", "D1 retention: 60 of 200 users" + wk + " · ≈ " + _QO + " (1 install day)"),
                                 _rt("30%", "D3 retention: 60 of 200 users" + wk),
                                 _rt("30%", "D1 retention: 30 of 100 users" + one),
                                 _rt("≈ 30%", "D3 retention: 30 of 100 users" + one + " · ≈ " + _QF + " (1 install day)")]
    # month: the same pooled days (22 Sep's flagged D1 not pooled: only the "(other)" reason on D1); its legend
    mo = " · 3 of 4 install days (the final ones) · not final"
    assert out["rt_uu_month"] == [_rt("≈ 30%", "D1 retention: 90 of 300 users" + mo + " · ≈ " + _QO + " (1 install day)"),
                                  _rt("≈ 30%", "D3 retention: 90 of 300 users" + mo + " · ≈ " + _QF + " (1 install day)"), True]
    # absent / old files: no "uu", "uu" without runs, empty / malformed runs, All countries (whatever src carries), Not
    # split — byte for byte as before, every grain
    assert out["rt_uu_absent"] == [True] * 24
    # All countries: late "u" "qou" > 0 → one line with its size, said as what it is (a day-wise sum over qou_days days,
    # in no row, spread over install days GA4 did not name — never "one number is short by all of it"), whatever the
    # columns: the default Day view (D60+ checkpoints only, no 30-day column) too — never hidden; no cell ≈; qou 0 / no
    # "u" / no late / a country: byte for byte as before; days unknown → the line without them
    assert out["rt_uu_all"] == [True] * 10 and out["rt_uu_all_week"]
    # the picked country's source carries cd "uu"; without it, none
    assert out["rt_uu_src"] == [True, True]
    # the goldens: the default view's files carry neither field (so GOLDEN_DEFAULT & co. are unchanged — asserted in
    # test_country_filter too)
    assert out["rt_uu_golden_fx"] == [True, True, True, True]
    assert out["cc_default_digest"] == GOLDEN_DEFAULT and out["cc_default_nort"] == GOLDEN_RET_CUT
    with open(PAGE, encoding="utf-8") as f:
        p = f.read()
    assert "return {ctl,cc:CTY,x,rows,qt:qb=>ccQ(qb,cd),note:ccNote(d,cd,x),uu:cd.uu}; }" in p
    assert "RET_UU=!xx&&src&&src.rows?retRuns(src.uu):null; RET_QU=src&&src.rows?null:((d0.late||{}).u||null); RET_AX=0;" in p


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
    # 🎯 Breakeven: its head right after CPI, none after "So far" (both fail on the page before the move)
    assert "<th>CPI</th><th>Breakeven</th>${C.map(c=>`<th>${c.lab}</th>`).join('')}<th>So far</th></tr>`" in p
    assert "<th>So far</th><th>Breakeven</th>" not in p and p.count("<th>Breakeven</th>") == 1
    # its cell styled only by the heat table's own classes (the harness pins every cell's exact markup: BE_TD) — each
    # defined, no new colour, no breakeven-only rule
    assert all(c in p for c in (".roi-heat td.roi-g{", ".roi-heat td.roi-nf{", ".roi-t td.roi-na{color:var(--faint)}"))
    assert "roi-be" not in p
    # unchanged layout pins (the same before this change): the table scrolls only inside its own box, its first column sticks
    assert ".roi-tw{overflow:auto;" in p and '<div class="roi-tw"><table class="roi-t roi-heat">' in p
    assert ".roi-t th:first-child,.roi-t td:first-child{position:sticky;left:0;" in p
    # 🧮 the totals strip: one height in every state — one-line labels / values (never wrapped), two-line reasons (a fixed
    # box), tiles a row by width only; called once per card path, right before the table's own HTML
    assert ".roi-ck .roi-kl,.roi-ck .roi-kv{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" in p
    assert ".roi-ck .roi-ks{height:2.8em;overflow:hidden;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2}" in p
    # 🎯 7 tiles (22 Oct, Avg breakeven joined), none alone in a row: 2 a row up to 899 px with Avg breakeven across both;
    # from 900 a 12-column grid — the first three (the money tiles) 4 columns each, the other four 3 each; from 1600 7 a
    # row (the one-group page: 2 / 3 / 6 from 900 / 1400) — the sizes test_totals_strip_states' width model uses
    assert ".roi-ckg{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.roi-cka{grid-column:span 2}" in p
    assert ".roi-ck{padding:9px 11px}" in p and ".roi-ck .roi-kv{font-size:17px}.roi-ck .roi-ckw{font-size:14px}" in p
    assert ("@media (min-width:900px){.roi-ckg{grid-template-columns:repeat(12,minmax(0,1fr))}.roi-ckg>.roi-ck{grid-column:span 3}"
            ".roi-ckg>.roi-ck:nth-child(-n+3){grid-column:span 4}}") in p
    assert "@media (min-width:1600px){.roi-ckg{grid-template-columns:repeat(7,minmax(0,1fr))}.roi-ckg>.roi-ck:nth-child(n){grid-column:auto}}" in p
    assert "@media (max-width:760px){.roi-ck .roi-kv{font-size:15.5px}.roi-ck .roi-ckw{font-size:13px}}" in p
    assert p.count(".roi-ckg{") == 3 and "@media (min-width:1400px){.roi-ckg" not in p and p.count("roi-cka") == 2
    # the two lines under the tiles: a fixed number of lines each, empty or not (the spend line ≤ 103 characters in 2,
    # Avg breakeven's ≤ 191 in 4 / 3 / 2 by width: measured in Chrome)
    assert ".roi-ckm{height:3em;overflow:hidden;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2}" in p
    assert (".roi-ckb{height:6em;overflow:hidden;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:4}"
            "@media (min-width:431px){.roi-ckb{height:4.5em;-webkit-line-clamp:3}}@media (min-width:900px){.roi-ckb{height:3em;-webkit-line-clamp:2}}") in p
    # Avg breakeven: the owner's 50% rule and the 3-day floor are named constants; each day read through beDay (the
    # Breakeven column's own), never a second breakeven; the plain median of the days that reached breakeven (22 Oct 2026,
    # the owner: "vo 100 din ka kya avg he BE vo dikhana chaiye") — the Kaplan–Meier median and the 2 × median age rule gone
    assert "const BE_FAST_SHARE=0.5, BE_MIN_N=3;" in p and "b=beDay(r,[],T)" in p and p.count("beAvg(") == 2
    assert not any(x in p for x in ("beKM(", "BE_AGE_X", "beBelow(", "Too early · median", "Kam din · ", "BE din pata:"))
    # the spend floor is the file's own min_spend (the Status rule), $5 when a file has none
    assert "d.consts.min_spend>0?+d.consts.min_spend:5" in p
    # the two-group code and CSS are gone: no group heads / wrapper class, no group titles
    assert not any(c in p for c in ("roi-ckh", "roi-ckq", "roi-ckx", "Spend pata wale din", "<b>Poori history</b>", "Do group kyun"))
    # the layout numbers the model takes from the rest of the page (unchanged by this work)
    assert "aside{width:220px;" in p and ".content{padding:15px 24px 32px;" in p and ".content{padding:15px 12px 40px;" in p
    assert ".content{padding:13px 10px 36px}" in p and ".roi-card{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:14px 16px;" in p
    assert ".roi-k{padding:9px 10px}" in p and "padding:12px}}" in p
    assert p.count("${cohKpi(d,null)}${cohortTable(d)}</div>`;") == 1 and p.count("${cohKpi(d,cs)}${cohortTable(d,cs)}</div>`; }") == 1
    assert p.count("cohKpi(") == 3                                                    # defined once, called by cohCard only
    # "Show 60 more" / "Show all": both tables' buttons keep the reader's row (keepRows), the rows keyed
    assert "if((b=at('[data-roi-more]'))){ const v=b.dataset.roiMore; keepRows(r,b,()=>{ SHOW=v==='all'?1e9:SHOW+60; repaint(); }); return; }" in p
    assert "if((b=at('[data-roi-lmore]'))){ const v=b.dataset.roiLmore; keepRows(r,b,()=>{ LSHOW=v==='all'?1e9:LSHOW+60; repaint(); }); return; }" in p
    # Mode: the page keeps the tapped button (keep), the box its row + column (boxAt / boxBack)
    assert "const w=metBox(b), p=w?boxAt(w):null;\n      keep(b,()=>{ MET=b.dataset.roiMet; repaint(); if(p) boxBack(r,p); }); return; }" in p
    assert '<tr data-roi-k="${E(gr.k)}"><td class="roi-nm">' in p and '<tr data-roi-k="${E(x[0])}"><td class="roi-nm">' in p
    assert p.count("SHOW+60; repaint(); return;") == 0                     # never a bare repaint (the box back at the top)
