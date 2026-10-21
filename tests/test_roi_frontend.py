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
limits), 🧮 the cohort card's totals strip (spend / revenue / profit-loss / ROAS / installs / install days over every
install day of All or the picked country: a hand recount, ₹ as billed, days left out counted, the same for every grain /
mode, '…' while loading, one height in every state, the page otherwise byte for byte as before), and the wiring into the
page. Skipped where node is not installed. No real data."""
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


# the default view's digest (tests/roi_frontend.js defaultDigest). Changed ON PURPOSE on 21 Oct 2026 when the Breakeven
# column moved from the far right to right after CPI (and its note joined): the page before that gave
# afd5bf6e3a67b59154525ddec5b34724b11a6a0a158388d09ad8bada10b88982. GOLDEN_NO_BE = the same parts with the Breakeven
# column and its note cut out, worked out on the page BEFORE the move (its far-right cell cut) — the new page gives it
# too: nothing else in any table, the Day view or the Countries board moved by a byte. (Review round: a "≤" on a column
# not final yet is faded + "not final", the note says so, and a week / month with a day's so far not read shows — instead
# of a too-low "% back": only the Breakeven cells + note changed, GOLDEN_NO_BE the same)
# 🧮 Changed ON PURPOSE again on 21 Oct 2026 when the totals strip joined the cohort card (between its title row and its
# control row): GOLDEN_PRE_KPI = the digest the page gave before it (the GOLDEN_DEFAULT above it), and the new page gives it
# again with the strip cut out (tests/roi_frontend.js kpiCut) — every table, the Day view and the Countries board otherwise
# byte for byte the same; GOLDEN_NO_BE is worked out with the strip cut out too.
GOLDEN_DEFAULT = "65b3d7ad62d5c151e9d12391231199db6be372b859c43e0ebd44f8b1b420cc9c"
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


# 🧮 the strip's value boxes, worked out from the page's own CSS (pinned in test_wiring) and checked in headless Chrome
# (21 Oct 2026: 360 → 131 px, 375 → 139, 761 → 202, 900 → 170, 1240 → 283, 1400 → 152): tiles a row by width, the card's
# and the tile's padding + border; beside the sidebar a classic 15 px scrollbar is taken off too
def _kpi_boxes():
    for w in range(360, 761):                                    # the phone / tablet layout: no sidebar, 2 a row
        pad = 10 if w <= 430 else 12                             # .content (≤430 px: 10, ≤760 px: 12) · .roi-card 12 + 1
        yield w, 0, ((w - 2 * pad - 26) - 8) / 2 - 22, True      # tile: 9px 10px + 1 px border
    for w in range(761, 2561):
        cols = 6 if w >= 1400 else 3 if w >= 900 else 2
        for sb in (0, 15):                                       # aside 220 · .content 24 · .roi-card 16 + 1 · tile 11 + 1
            yield w, sb, ((w - 220 - 48 - sb - 34) - 8 * (cols - 1)) / cols - 24, False


# advance widths (em) of the value font (weight 800, tabular figures) measured in headless Chrome; the largest of 13 /
# 14 / 15.5 / 17 px for every size (the system font is a little wider at small sizes)
_EM = dict({c: 0.68 for c in "0123456789+−₹$"}, **{",": 0.36, ".": 0.36, "%": 1.07, "—": 0.92, "…": 1.0})


def _px(text, size):
    return sum(_EM[c] for c in text) * size


def test_totals_strip(out):
    """🧮 Total spend / revenue / profit-loss / ROAS / installs / install days in the cohort card (owner, 21 Oct 2026: "kpi
    add karo yaha pe ki kitna total spend gaya he kitna total revenue aaya he — all country and jo country select kru uska
    kpi change ho jayega — total hi aayega"), on made-up rows."""
    # the default page: only the strip added — with it cut out, the digest is the one before it (2 parts carry it: the Day views)
    assert out["cc_default_nokpi"] == GOLDEN_PRE_KPI and out["cc_default_kpis"] == 2
    # under the title row, right above the control row (one per card, above the table; the Day view has one, the
    # Countries board none); its Hinglish note
    assert out["k_place"] == [True, 1, True, 1, False, True]
    # a hand recount (5 install days): spend $10 + $4 + $0 + $6 (2 Jan not known: out, said); so far $30 + $5 + $0 + $3
    # (3 Jan not read yet: out, said); profit / loss + ROAS over the 2 ads days with both (1 + 5 Jan; 4 Jan had no ads,
    # said): $33 − $16 = +$17, 206%
    assert out["k_usd"] == [["Total spend", "$20", "1 din ka spend pata nahi"],
                            ["Total revenue", "$38", "1 din ki kamai abhi nahi padhi"],
                            ["Profit / loss", "+$17", "sirf 2 ads din, jinka dono pata"],
                            ["ROAS", "206%", "1 din bina ads — isme nahi"],
                            ["Installs", "200", "GA4 · ads + organic"],
                            ["Install days", "5", "1 Jan 2026 – 5 Jan 2026"]]
    assert out["k_usd_cls"][2:4] == [["roi-kg", "roi-up"], ["", "roi-g"]]          # profit green, ROAS ≥ 100% green
    assert out["k_usd_table"] == [20, 38, 200]          # = Σ the table's own Spend / So far / Installs columns
    # ₹ billed (₹90 a $ on every day, today ₹100): spend ₹900 + ₹360 + ₹0 + ₹540 as billed (= Σ the Spend column in ₹),
    # revenue $38 × 100 (= Σ the So far column); profit / loss = each ads day's so far at its own billed rate − its bill:
    # $30 × 90 − ₹900 + $3 × 90 − ₹540 = +₹1,530; ROAS the $ one (206%). A ₹ view of a file not billed in ₹: $ × 100 throughout
    assert out["k_inr"] == [["Total spend", "₹1,800", "1 din ka spend pata nahi"],
                            ["Total revenue", "₹3,800", "1 din ki kamai abhi nahi padhi"],
                            ["Profit / loss", "+₹1,530", "sirf 2 ads din, jinka dono pata"],
                            ["ROAS", "206%", "1 din bina ads — isme nahi"]] and out["k_inr_table"] == 1800
    assert out["k_inr_usd"] == [["Total spend", "₹2,000", "1 din ka spend pata nahi"],
                                ["Total revenue", "₹3,800", "1 din ki kamai abhi nahi padhi"],
                                ["Profit / loss", "+₹1,700", "sirf 2 ads din, jinka dono pata"],
                                ["ROAS", "206%", "1 din bina ads — isme nahi"]]
    # review: no-ads days (spend 0) keep their revenue in Total revenue only — 3 × ($0, $100) + 3 × ($100, $80): profit
    # −$60 (red), ROAS 80% = every ads row's own "So far" %, the 3 days said (it read +$240 / 180% before)
    assert out["k_zero"] == [[["Total spend", "$300", "Google Ads"], ["Total revenue", "$540", "so far · AdMob-matched"],
                              ["Profit / loss", "−$60", "sirf 3 ads din, jinka dono pata"], ["ROAS", "80%", "3 din bina ads — isme nahi"]],
                             [["roi-kb", "roi-dn"], ["", "roi-w"]], ["$80 80%"] * 3]
    # review: ₹ billed at ₹83, today ₹88, 2 days of $100 spend / $98 so far: ROAS 98% in $ and in ₹ (= the rows' own %),
    # a loss in both (−$4.0; ₹: $98 × 83 − ₹8,300 twice = −₹332) — it read +₹648 / 104% (green) in ₹ before
    kd, ki, rows = out["k_rate"]
    assert kd == [[["Total spend", "$200", "Google Ads"], ["Total revenue", "$196", "so far · AdMob-matched"],
                   ["Profit / loss", "−$4.0", "revenue − spend"], ["ROAS", "98%", "revenue ÷ spend"]], [["roi-kb", "roi-dn"], ["", "roi-w"]]]
    assert ki == [[["Total spend", "₹16,600", "Google Ads"], ["Total revenue", "₹17,248", "so far · AdMob-matched"],
                   ["Profit / loss", "−₹332", "revenue − spend"], ["ROAS", "98%", "revenue ÷ spend"]], [["roi-kb", "roi-dn"], ["", "roi-w"]]]
    assert rows == [["₹8,300", "₹8,624 98%"]] * 2 and kd[0][3][1] == ki[0][3][1]
    # a loss: red (the existing classes); spend 0 everywhere (organic): no profit / ROAS (never ∞ / 0%), said; no rows: '—'
    assert out["k_loss"] == [[["Profit / loss", "−$48", "revenue − spend"], ["ROAS", "20%", "revenue ÷ spend"]],
                             [["roi-kb", "roi-dn"], ["", "roi-b"]]]
    assert out["k_org"] == [["Total spend", "$0.00", "Google Ads"], ["Total revenue", "$6.0", "so far · AdMob-matched"],
                            ["Profit / loss", "—", "koi ads din nahi (spend 0)"], ["ROAS", "—", "koi ads din nahi (spend 0)"]]
    assert [x[1] for x in out["k_none"]] == ["—", "—", "—", "—", "—", "0"]
    # every install day (70, not the 60 on screen), whatever the grain / mode / "Show more"
    assert out["k_inv"] == [True] * 24 and out["k_all70"] == ["Install days", "70", "5 Aug 2026 – 13 Oct 2026"]
    # 🌍 All with the country part = All without it; a pick: '…' while its rows load (aria-busy), then its own totals =
    # a recount of the rows its table shows (unknown spend out of spend + profit / ROAS, no-ads days out of profit / ROAS,
    # each counted); the same every grain / mode; another country of the same pack at once
    assert out["k_allcd"] == [True]
    assert out["k_load"] == [["…"] * 6, True, True, True]
    k, want, D, unk, nboth, nz = out["k_aa"]
    assert k == want and (D, unk, nboth, nz) == (70, 28, 32, 4)
    assert k[0] == ["Total spend", "$380", "28 din ka spend pata nahi"] and k[2][2] == "sirf 38 ads din, jinka dono pata"
    assert k[3] == ["ROAS", "104%", "4 din bina ads — isme nahi"]
    assert out["k_aa_inv"] == [True] * 12
    assert out["k_bb"][0] == out["k_bb"][1] and out["k_bb"][2]
    # "Unknown country": Google Ads has no such country → spend '—' (not 0), no profit / ROAS; its revenue + installs
    k, want = out["k_unk"]
    assert k == want and k[0] == ["Total spend", "—", "Google Ads me ye country nahi"] and k[2][1] == k[3][1] == "—"
    # "Not split": spend only (its unknown days counted); revenue / profit / ROAS / installs '—'
    k, want, has_unk, n_rev = out["k_xx"]
    assert k == want and has_unk and n_rev == 0
    assert [x[1] for x in k[1:5]] == ["—"] * 4 and k[1][2] == "Not split: koi kamai nahi"
    # a pack that failed / a country the app does not have: '—' (no busy flag); an app without the country part: All's own
    assert out["k_err"] == [["—"] * 6, True, True] and out["k_miss"] == [["—"] * 6, True] and out["k_nocd"] == [True, True]
    # ONE height in every state (21 made: loading, loaded, error, missing, ₹ / $, Unknown, Not split, loss, no ads, crore …):
    # the same box, one-line values, two-line reasons (the CSS pins are in test_wiring)
    assert out["k_skel"] == [1, 21]
    # review: crore-size ₹ printed in full — 14+ characters a size smaller (roi-ckw), shorter ones not
    assert out["k_big"] == [["₹23,45,76,190", "₹14,08,08,624", "−₹10,05,29,262", "57%", "1,234,577", "2"],
                            ["₹2,34,56,87,200", "₹1,40,80,08,624", "−₹1,00,52,91,123", "57%", "1,234,577", "2"],
                            [[False, False, True, False, False, False], [True, True, True, False, False, False]]]
    # every value printed in those states fits its box at EVERY width 360–2560 px (₹ crore, a classic scrollbar too), at its
    # own size (17 / 15.5 px, a 14+ character one 14 / 13 px); reasons ≤ 35 characters (two lines of the narrowest tile,
    # 131 px at 360, checked in Chrome); labels one short line
    pr = out["k_print"]
    assert len(pr) == 21 * 6 and any(v == "−₹1,00,52,91,123" for _, v, _, _ in pr)
    assert all(w == (len(v) >= 14) for _, v, w, _ in pr)
    tight = {}
    for w, sb, box, phone in _kpi_boxes():
        for lab, v, small, sub in pr:
            size = (13 if small else 15.5) if phone else (14 if small else 17)
            room = box - _px(v, size)
            if room < tight.get("room", 1e9):
                tight = {"room": room, "w": w, "sb": sb, "v": v}
    assert tight["room"] >= 2, tight
    assert all(len(sub) <= 35 and "<" not in sub and len(lab) <= 13 for lab, _, _, sub in pr)


def test_country_filter(out):
    # "All countries" (the default): every grain × mode, the Day view, the Countries board as pinned above
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
    # box), 6 / 3 / 2 tiles a row by width only; called once per card path, right before the table's own HTML
    assert ".roi-ck .roi-kl,.roi-ck .roi-kv{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" in p
    assert ".roi-ck .roi-ks{height:2.8em;overflow:hidden;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2}" in p
    # review (21 Oct): 2 a row up to 899 px, 3 from 900, 6 from 1400 — the value box never under ~150 px beside the sidebar
    # (it was 124 px at 761 and 126 at 1240: ₹ crore cut with '…'); the sizes test_totals_strip's width model uses
    assert ".roi-ckg{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}" in p
    assert ".roi-ck{padding:9px 11px}" in p and ".roi-ck .roi-kv{font-size:17px}.roi-ck .roi-ckw{font-size:14px}" in p
    assert "@media (min-width:900px){.roi-ckg{grid-template-columns:repeat(3,minmax(0,1fr))}}" in p
    assert "@media (min-width:1400px){.roi-ckg{grid-template-columns:repeat(6,minmax(0,1fr))}}" in p
    assert "@media (max-width:760px){.roi-ck .roi-kv{font-size:15.5px}.roi-ck .roi-ckw{font-size:13px}}" in p
    assert p.count(".roi-ckg{") == 3 and "@media (min-width:1240px){.roi-ckg" not in p
    # the layout numbers the model takes from the rest of the page (unchanged by this work)
    assert "aside{width:220px;" in p and ".content{padding:15px 24px 32px;" in p and ".content{padding:15px 12px 40px;" in p
    assert ".content{padding:13px 10px 36px}" in p and ".roi-card{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:14px 16px;" in p
    assert ".roi-k{padding:9px 10px}" in p and "padding:12px}}" in p
    assert p.count("${cohKpi(d,null)}${cohortTable(d)}</div>`;") == 1 and p.count("${cohKpi(d,cs)}${cohortTable(d,cs)}</div>`; }") == 1
    assert p.count("cohKpi(") == 3                                                    # defined once, called by cohCard only
