"""🖼️ Screens tab — the page side (owner, 4 Nov 2026: "per app, per Activity: visits, the ad impressions against them, the
ratio — a NEW tab"). tests/scr_frontend.js runs the SCR module of frontend/index.html for real (a node vm, stub page
helpers) on SYNTHETIC files in the shape of admob_iq/screens_build.py's; checked here: the picker (every standard key incl.
the month keys and Custom → its GA4 dates; N days end at the last final day; Today / Yesterday not final), the period's
normal (the max(28, length) final days before it), the score muted under 7 final days and "—" for All time, the sums that
skip a day whose grain lacks the row's quantity, the coverage strip (N / M apps whole per piece from the day-state
strings, the apps not whole with why), the status words → chips and the Worse-first order, All apps and the app page
(+ every drill-down section and fold) for a normal app, an app whose ads by screen are sampled, an app with screen-only
days, an app with no AdMob placements and an app with no days yet, a hostile class name escaped, the 90 % split + Show
more, the Copy report helper's paths, the period saved per viewer (bad keys ignored, a throwing localStorage harmless),
the chart's model and its printed labels, keep() (no page jump: the height held through the repaint itself), the
drill-down tied to its app, "Details ▸" going to the drill-down, late files redrawing only their own slots with the scroll
boxes kept, whole months from the build's month sums (ver_m / cc_m), labels in simple English (hints stay Hinglish), the
status sort's direction, the report's Copy control holding its place while its files load (Try again on a failed load),
All apps' period sums / coverage strip kept per (build, period) with no date string per day, a day whose store file
could not be read ("x": store file unreadable), a day that is not whole never read as "GA4 sampled" (one GA4 was never
asked about, one not read yet), the build's why shown whole and escaped, all formats because GA4 gave no screen ×
format split (allf 2: its note with the measured full-screen share), a row under 1 % of the app's ads of its kind
showing no score (and a "Too few ads" row never in Needs attention), Ads / user per user per day from file 2 (⏳ until
it is here — the app page asks for it at once — its failed load "—" + Try again, its late arrival redrawing the tiles and
the table; the Screens column: Σ ads ÷ Σ the screen's daily users on the final days with users, never the mean of the
daily ratios; "—" + why for an aggregate row, Today / Yesterday and no whole users day; the tooltips, the sort; the app
tile: inline + full-screen ÷ the app's daily users, "Format not recorded" left out, its parts adding up; Users who saw
ads in the drill-down: Σ ÷ Σ, ⏳ while scr_l loads, why when none), the tiles' 1180 px rule, and the wiring into the page
(gated on DATA.scr); the time columns after Ads / user (Time / view, Time / user / day, Ads / min: Σ ÷ Σ on their own days,
a day with views but no engagement left out, an aggregate row's "—" for users, ⏳ / "—" while file 2 loads, the format, the
details tiles). Status v2 (owner, 6–7 Nov 2026): Imp / user / day — the Screens table's 10 columns on one day set (the
chain Views / user / day × Time / view × Ads / min ÷ 60 holds exactly), the aggregates pinned with their share of the
screen ads, Today / Yesterday "—" + the ads so far ⏳, the Full-screen table per app user (5 columns), the App total block
from scr_all alone (its parts adding up, copy days left out), All apps from scr_all's "au" (a data N/A's score muted, "Worse
(AdMob)"), Needs attention one line per cause with ≈ Σ impact, the details (Ads / 100, reach, the parts, the chart per
user), v 2 files only (a v 1 file refused visibly).
Skipped where node is not installed. No real data."""
import json
import math
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
    r = subprocess.run([NODE, os.path.join(ROOT, "tests", "scr_frontend.js"), PAGE],
                       check=True, capture_output=True, text=True, timeout=120)
    rep = json.loads(r.stdout)
    assert not rep["errors"], rep["errors"]
    return rep["out"]


def test_pointer_and_lazy_load(out):
    assert out["no_ptr"] and out["bad_file"] and out["no_apps"] and out["no_ptr_note"]
    assert out["v1_all"]                                                             # a v 1 file (ads / 100): refused, Try again
    assert out["loading"] and out["fail_html"] and out["loads_all"] == 2          # a failed load shows Try again; the tap loads again
    assert out["reload_no_loading"] and out["reload_quiet"] == 4                   # a new build: the older data stays on screen
    assert out["ready"]


def test_picker_dates(out):
    r = out["rng"]
    assert r["today"] == ["2026-03-30", "2026-03-30"] and r["yday"] == ["2026-03-29", "2026-03-29"]
    assert r["7"] == ["2026-03-22", "2026-03-28"] and r["30"] == ["2026-02-27", "2026-03-28"]          # N days end at ft
    assert r["60"] == ["2026-01-28", "2026-03-28"] and r["90"] == ["2025-12-29", "2026-03-28"]
    assert r["tm"] == ["2026-03-01", "2026-03-30"] and r["lm"] == ["2026-02-01", "2026-02-28"]
    assert r["mon_feb"] == ["2026-02-01", "2026-02-28"] and r["mon_mar"] == ["2026-03-01", "2026-03-30"]
    assert r["all"] == ["2026-01-01", "2026-03-30"]
    assert r["cus"] == ["2026-03-10", "2026-03-20"]                                 # swapped when reversed
    assert r["cus_clamp"] == ["2026-01-01", "2026-03-30"] and r["cus_empty"] == ["2026-01-01", "2026-03-30"]   # inside [d0, td]
    assert r["bogus"] == r["30"]
    assert out["notfinal"] == {"today": True, "yday": True, "tm": True, "7": False, "30": False}


def test_period_normal_and_muted_score(out):
    n = out["norm"]
    assert n["d7"] == ["2026-02-22", "2026-03-21"]                                   # 28 final days before 7 days
    assert n["d30"] == ["2026-01-28", "2026-02-26"]                                  # max(28, 30) = 30
    assert n["d60"] == ["2025-11-29", "2026-01-27"]
    assert n["today"] == ["2026-03-01", "2026-03-28"]                                # a not-final period: ending ft
    m = out["muted"]
    assert m["today"]["muted"] and m["today"]["fin"] == 0
    assert not m["d7"]["muted"] and m["d7"]["fin"] == 7 and m["d7"]["score"] == 100
    assert m["short"]["muted"] and m["short"]["fin"] == 4
    assert m["all"]["score"] is None                                                 # All time: no normal


def test_sums_skip_days_without_the_quantity(out):
    # Gamma: every 3rd day GA4 gave the screen without the format → no inline ads that day; visits still counted beside
    assert out["sum_c"] == [10000, 1000, 20, 30, 30, 15000, 10]
    assert out["sum_sampled"] == [None, None, 0, None, 32145]                        # sampled every day: unknown, never 0
    assert out["sum_fs"][2] == 30 and out["sum_fs"][1] == 1200                       # triggers (from the unit read) whole


def test_coverage_strip(out):
    want = [["v", 5, 6], ["a", 4, 6], ["w", 5, 6], ["r", 3, 6], ["c", 3, 6], ["n", 4, 6], ["k", 5, 6], ["e", 4, 6],
            ["u", 4, 6], ["s", 5, 6], ["x", 5, 6]]                                  # (u: Alpha's users who saw ads sampled 26 Mar)
    assert out["cov"] == want and out["cov_fn"] == want                              # the hidden app is not counted
    ids = [x[0] for x in out["cov_list"]]
    assert ids == ["ca-app-pub-0000000000000000~22", "ca-app-pub-0000000000000000~23", "ca-app-pub-0000000000000000~25"]
    assert out["cov_list"][0][1] == "GA4 sampled 30 din"
    assert out["cov_list"][1][1] == "history 2 Mar 2026 se (bhar rahi hai) · 3 din abhi padhe nahi"
    assert out["cov_list"][2][1] == "abhi koi din nahi padha"


def test_status_words_and_order(out):
    assert out["wdk"] == {"Worse": "bigda", "Watch": "dhyan", "Better": "behtar", "Normal": "normal", "Too early": "jaldi", "N/A": "lagu"}
    assert out["rank"] == {"Worse": 0, "Watch": 1, "Better": 2, "Normal": 3, "Too early": 4, "N/A": 5}
    assert out["all_rows"] == ["Alpha App", "Gamma App", "Hostile App", "Delta App", "Empty App", "Beta App"]   # Worse first
    assert out["all_chips"] == ["bigda", "dhyan", "behtar", "normal", "jaldi", "lagu"]
    assert out["sort_v"][0] == "Alpha App"                                           # by daily users (the others have none)
    # judged screens by status, then the aggregate rows pinned at the bottom in their fixed order (never sorted)
    assert out["sort_items"] == [0, 1, 2, 3, 4, 5]


def test_all_apps(out):
    assert not out["all_hidden"] and len(out["all_icons"]) == 6                      # every name with its own logo by app id
    assert out["all_hostile_why"] and out["all_period"] and out["all_time"]
    assert out["row_tap"] == "Gamma App"


def test_app_pages_render_for_every_kind_of_app(out):
    p = out["pages"]
    keys = {"a": "a00000000001", "b": "a00000000002", "c": "a00000000003", "d": "a00000000004", "h": "a00000000006"}
    for k, key in keys.items():
        assert not p[k]["errors"] and p[k]["n_sections"] == 40 and not p[k]["empty"], k
        assert p[k]["loaded"][:2] == ["scr_%s.json.gz" % key, "scr_l_%s.json.gz" % key]      # file 2, then its layers
    assert p["e"]["empty"] and out["empty_msg"] == "28 Mar 2026 tak"                 # no days yet: says so
    assert p["a"]["rows"] == [0, 1, 2, 3, 4, 5]                                      # the aggregates pinned last
    assert p["d"]["ok_all"]                                                          # no flag: "✅ Sab normal"
    assert not p["b"]["ok_all"]                                                      # all N/A: never "Sab screens normal"
    assert out["hidden_page"]


def test_app_page_parts(out):
    a = out["a_page"]
    assert a["crumb"] and a["mini"] and a["seg"] and a["period"] and a["cus_row"] and a["how"] and a["total"]
    # Needs attention: the App row first, then one line per (word, cause group) with ≈ Σ the rows' impacts
    assert a["attn"][0] == ["bigda", "App total", "imp/user 1.20 → 0.90 (−25%) · z −5.1 · AdMob agrees (inline −28%)"]
    assert a["attn"][1:] == [["bigda", "Lower fill", "1 row (Main) · ≈ −12.0% of the app's imp/user"],
                             ["dhyan", "Fewer ad requests", "1 row (All other screens) · ≈ −3.0% of the app's imp/user"]]
    assert a["editor"] and a["title"] and a["unjudged"] == 3                         # "Activity" dropped, the full class on hover
    assert a["folds"] == ["app", "src", "cov", "rep", "how"]                         # Versions now inside the App total's details
    assert a["cov_fold"] and a["rep_fold"] and a["src_fold"] and a["notes"]
    assert a["chips"] == ["today", "yday", "7", "tm", "lm", "30", "60", "90", "all", "cus", "mon:2026-01", "mon:2026-02", "mon:2026-03"]
    assert a["mover"] == [["mon:2026-01", "false", False, "‹"], ["mon:2026-02", "false", False, "Feb 2026"], ["mon:2026-03", "false", False, "›"]]
    assert out["today"] == {"line": True, "muted": True}                             # "Today (GA4 · 30 Mar) · not final", score muted
    assert out["top"] == [0, 1, 2, 3, 4, 5]
    assert out["top_many"] == [0, 1, 2, 9, 10]                                       # 90 % of views + the Worse row + unjudged
    assert out["many_less"][1] == "6" and out["many_more"] == [11, True]


def test_drill_down_sections(out):
    x = out["alpha"]
    assert x["ov_terms"] and x["ov_months"] == [["Mar 2026", 30], ["Feb 2026", 28], ["Jan 2026", 31]]
    assert x["ov_days"] == 89 and x["ov_first_day"] == "30 Mar 2026"               # full history, newest first
    assert x["un"] == ["unit_a", "unit_a"] and x["un_fs"] == ["unit_b"]            # the period's units + the cause's (status window)
    assert x["un_cz"] == ("<td>2,000 <small>normal 2,100</small></td><td>90.0% <small>92.0%</small></td>"
                          "<td>9.2% <small>9.5%</small></td><td>0.97 <small>0.99</small></td>")
    assert "<td>3,000</td><td>62.5%</td><td>2,000 <small>normal 2,000</small></td><td>90.0% <small>90.0%</small></td>" in x["un_row"]
    assert x["ver"] and x["ver_same"] == ["11.0", "12.0", "−8%"]
    assert x["cc"] == [["[XA] Name XA", "16,800", "1,960", "11.7"], ["[XB] Name XB", "8,400", "560", "6.7"]]   # the edge month's shard
    assert x["cc_notes"] == [True, True]                                             # a too-big / failed month says so
    assert x["nvr"][:2] == [["Returning", "23,145", "2,400"], ["New", "9,000", "900"]]
    # Users who saw ads = Σ the screen's users who saw ads ÷ Σ its users, over the days both users reads are whole (the
    # sampled 26 Mar left out) — never the mean of the daily ratios (both vary by day); an aggregate row: "—" and why
    ek = [k for k in K30 if k != 84]
    sa, sv = sum(600 - 40 * (k % 3) for k in ek), sum(800 + 50 * (k % 5) for k in ek)
    pct = lambda v: "%.1f%%" % (_jr(v * 1000) / 10.0)
    assert pct(sa / float(sv)) != pct(sum((600 - 40 * (k % 3)) / float(800 + 50 * (k % 5)) for k in ek) / len(ek))
    assert x["eng"] == [["Time / view", "28s"], ["Time / user / day", "38s"], ["Ads / min", "0.23"], ["Clicks", "90"], ["Exposure per view", "0.04 s"],
                        ["Users who saw ads", pct(sa / float(sv))], ["Sessions", "27,000"]]
    tt = ("us screen ke ad dekhne wale users ka har din ka jod ÷ us screen ke users ka har din ka jod (GA4 me user sirf ek "
          "din aur ek screen ke andar unique) · sirf wo din jin me dono users reads whole aaye")
    assert x["eng_users"] == [[tt, pct(sa / float(sv)), "Σ ÷ Σ (har din ke users ka jod) · 29/30 days"], [None, "—", AGGW]]
    assert x["x"] and x["rep"] and x["rep_none"]
    assert "scr_c_a00000000001_202603.json.gz" in out["shard_loads"]               # only the partial edge month
    assert out["delta"] == {"un_noplace": True, "eng_noclick": True, "dq": True, "cov_exposure": True}
    assert out["gamma"]["un_split"] and out["gamma"]["ov_why"] and out["beta"]["tbl_null"]
    assert out["phone_push"] == ["scr-dd"] and out["open_after"] == 1 and out["closed"] is None


def test_labels_are_simple_english():
    # owner rule: table headers, headings, chips and buttons in simple English; the faint hints / why lines stay Hinglish
    p = _page()
    m = p[p.index("const SCR=(()=>{"):p.index("function renderScreens(){")]
    for old in ("Badlav ka hissa", "Pehla kharab din", "Status window ke units", "Is period me · version-wise",
                "Har version · poori life", "Same din", "(yahan)", "Unit ke ads me hissa", "28 din pehle",
                "AdMob me nahi mila", "} se ${h.done", "fdy(x.d0)} se", "+' se'", "'abhi nahi'", "din</small>", "din)</small>",
                "${p.nv} din", "/${p.nd} din"):
        assert old not in m, old
    # short cell / count labels in English too ("N days", "from <date>"); faint hints and why-lines stay Hinglish
    for sm in re.findall(r"<small(?![^>]*sc-faint)[^>]*>([^<]*)</small>", m):
        assert not re.search(r"(?:\}|\d)\s*din\b|\}\s*se\b|nahi mila", sm), sm
    labels = re.findall(r"<th[^>]*>(.*?)</th>|<h[34][^>]*>(.*?)</h[34]>|<button[^>]*>([^<]*)</button>", m)
    assert len(labels) > 60
    for lab in ("".join(x) for x in labels):
        assert not re.search(r"\b(?:ka|ke|ki|me|din|pehle|hissa|yahan|nahi|har|poori|wala|wale)\b",
                             re.sub(r"<small[^>]*>.*?</small>|\$\{[^}]*\}", "", lab)), lab


def test_rendered_labels(out):
    assert out["labels"] == {"terms": True, "un": True, "cz": True, "ver": True}
    assert out["a_page"]["mini"]                                                     # the App total's columns
    # the short cell labels: the History column, the crumb, the days a number stands on, a unit AdMob does not have
    assert out["all_hist"] == ["from 1 Jan 2026 ✓"] * 4 + ["from 20 Mar 2026 ⏳", "from 1 Jan 2026 ✓"]
    assert out["a_page"]["crumb"]                                                    # "history from 1 Jan 2026"
    assert out["pages"]["a"]["basis"] == "27/30 days"                                # the days with the screen's users
    assert out["gamma"]["month_days"] == []                                          # no users: no per-user month numbers
    assert out["not_in_admob"] == "<small>Not in AdMob</small>"


def test_phone_tiles_wrap_into_two_columns():
    # ≤ 480 px: the KPI tiles in a 2-column grid (all in view, no sideways scroll; the app's five: Status across both
    # columns); wider phones / desktop unchanged (the app's own row: five columns)
    p = _page()
    css = p[p.index("/* ---------- 🖼️ Screens"):p.index("/* ---------- 👥 Audience")]
    assert ".sc-tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:0 0 14px}" in css
    assert ".sc-tiles.sc-five{grid-template-columns:repeat(5,minmax(0,1fr))}" in css
    i760, i480 = css.index("@media (max-width:760px){"), css.index("@media (max-width:480px){")
    assert i480 > i760                                                               # after the 760 px rules: it wins
    rule = css[i480:css.index("}}", i480) + 2]
    assert ".sc-tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;overflow-x:visible}" in rule
    assert ".sc-tiles.sc-five{grid-template-columns:repeat(2,minmax(0,1fr))}.sc-five .sc-kst{grid-column:1/-1}" in rule
    assert ".sc-k{min-width:0;max-width:none}" in rule
    # 761–1180 px (five tiles under ~175 px wrap their labels / the Status value): the app's five tiles in three columns,
    # Status across the last two — a rule BEFORE the 760 / 480 px ones with the same selectors (same specificity), so
    # those still win at their widths (375 / 480 / 1280 px unchanged)
    i1180 = css.index("@media (max-width:1180px){")
    assert i1180 < i760 < i480 and css.count("@media (max-width:1180px){") == 1
    assert css[i1180:css.index("}}", i1180) + 2] == ("@media (max-width:1180px){\n  .sc-tiles.sc-five{grid-template-columns:"
                                                     "repeat(3,minmax(0,1fr))}.sc-five .sc-kst{grid-column:span 2}}")


def _jr(v):
    """JS Math.round."""
    return math.floor(v + 0.5)


def _p2(v):
    """The page's PU under 10: two places (JS Math.round)."""
    return "%.2f" % (_jr(v * 100) / 100.0)


def _p3(v):
    """The page's PQ under 1 (an Imp / user / day number, as the build's _q): three places (JS Math.round)."""
    return "%.3f" % (_jr(v * 1000) / 1000.0)


def _p1(v):
    """The page's P1: a share as "12.3%" (JS Math.round)."""
    return "%.1f%%" % (_jr(v * 1000) / 10.0)


# the harness's made-up Alpha (tests/scr_frontend.js): day k from 1 Jan 2026, ft = day 86 (28 Mar), its 30 days = 57 … 86;
# file 2's users vary by day (none every 10th day, none after ft) — so Σ ÷ Σ and the mean of the daily ratios differ
K30 = range(57, 87)
U_DAYS = [k for k in K30 if k % 10 != 5]
A_MAIN = lambda k: _jr((1000 + k) * (0.08 if k >= 79 else 0.12))                   # Main's inline ads a day
U_MAIN, U_EDIT, AU = (lambda k: 500 + 100 * (k % 7)), (lambda k: 200 + 30 * (k % 4)), (lambda k: 400 + 60 * (k % 6))
KN30 = range(27, 57)                                                                # the 30 days' normal (the 30 final days before)


def _app_u(ks):
    """Alpha's App total by hand over days ks: GA4's inline (Main + 88 more a day) + full-screen (65) + not recorded (120
    every 4th day, left out on its copy day 60) ÷ the app's daily users → (imp / user, inline, full, not recorded)."""
    il, fl = sum(A_MAIN(k) + 88 for k in ks), 65 * len(ks)
    ns, u = sum(120 for k in ks if k % 4 == 0 and k != 60), float(sum(AU(k) for k in ks))
    return (il + fl + ns) / u, il / u, fl / u, ns / u
AGGW = "screens ke users jode nahi ja sakte (GA4 user sirf ek screen aur ek din ke andar unique)"
NFW = "Today / Yesterday: daily users ~2 din baad aate hain — imp / user nahi; ads ⏳ abhi badhenge"


def test_users_who_saw_ads_waits_for_its_file_and_says_why(out):
    # scr_l on its way: ⏳ "aa raha hai…" (never a reason); an aggregate row: "—" and why at once; a day whose users who
    # saw ads GA4 sampled; a day GA4 gave them for the app only (not per screen)
    assert out["eng_wait"] == [["⏳", "aa raha hai…"], ["—", AGGW]]
    assert out["eng_none"] == [["—", "GA4 sampled 1 din"], ["—", "GA4 ne ad dekhne wale users screen-wise nahi diye"]]


def test_a_section_needing_both_files_shows_a_failed_file_2(out):
    g = out["gate"]
    for s in ("ver", "nvr", "x"):                                                    # file 2 failed, scr_l here
        assert g[s] == ["scr_a00000000001.json.gz", False, False], s                 # Try again, never "Loading" for good
    assert g["cc"] == [None, False, True]                                            # scr_l only: drawn
    assert g["ver_loading"] == [None, True, False]                                   # file 2 still on its way
    assert g["nvr_l_err"] == ["scr_l_a00000000001.json.gz", False, False]


def test_status_sort_honours_its_direction(out):
    t = out["tsort"]
    assert t["asc"] == [[0, 1, 2, 3, 4, 5], "ascending"]                             # Worse first (the default)
    assert t["desc"] == [[1, 0, 2, 3, 4, 5], "descending"]                           # reversed, as its header says
    assert t["back"] == t["asc"]
    assert out["sort_items_desc"] == [1, 0, 2, 3, 4, 5]                             # the aggregates stay pinned at the bottom


def test_report_copy_control_keeps_its_place_while_loading(out):
    r = out["rep"]
    head = ('<div class="sc-copy"><button type="button" class="sc-back" data-sc-copy="row"%s>%s</button>'
            '<span class="sc-cpl" id="sc-cpl-row" aria-live="polite">%s</span></div>')
    assert r["ready_head"] == head % ("", "📋 Copy report", "4 lines")
    assert r["l_loading"] == head % (" disabled", "Loading data…", "") == r["f2_loading"]   # same button, same reserved line
    assert ('<div class="sc-copy"><button type="button" class="sc-back" data-sc-copy="app" disabled>Loading data…</button>'
            '<span class="sc-cpl" id="sc-cpl-app" aria-live="polite"></span></div>') in r["fold_loading"]
    for k, f in (("l_err", "scr_l_a00000000001.json.gz"), ("f2_err", "scr_a00000000001.json.gz"),
                 ("fold_err", "scr_l_a00000000001.json.gz")):
        assert 'data-sc-retry="%s">Try again</button>' % f in r[k] and "data-sc-copy" not in r[k], k
    assert "Is app ki detail file is build me nahi bani." in r["nofile"] and r["after"]


def test_all_apps_sums_are_kept_per_build_and_period(out):
    m = out["memo"]
    assert m["same_build"]                       # a sort tap, a coverage-chip tap and a refresh on the same build: no recount
    assert m["new_period"] and m["new_data"]     # another period / a new build's data: counted again, the same numbers
    assert m["sum_same"] and m["sum_period"] and m["sum_data"]
    assert m["iso"] == [0, 0, 30]                # coverage + period sums build no date string per day (sumItem reads them)


def test_unreadable_store_days_say_so(out):
    x = out["xstate"]
    assert x["c"] == [5, 2, 23, 30, False] and x["day"] == ["x", "?", "w"]
    assert x["why"] == ("store file unreadable 5 din (build store ki month file padh nahi saka — ye din gine nahi) · "
                        "2 din aur wajah se not whole")
    assert x["vrow"] == "<td>23</td><td>0</td><td>7</td><td>0</td><td>—</td><td class=\"sc-why\">%s</td>" % x["why"]


def test_a_day_not_whole_is_never_called_ga4_sampled(out):
    # a day the fetch never asked GA4 about ships "-" (not read yet): no line puts every day that is not whole on GA4 —
    # the N/A line names each part, a layer note counts the days not read beside the ones GA4 gave
    assert out["a_page"]["how_na"] == ["whole din kam / logging badli / ads nahi / users nahi aaye / ads bahut kam"]
    assert out["nvr_note"] == "2/30 din ye layer whole nahi aayi ya abhi padhi nahi (us din ka hissa nahi gina)."
    p = _page()
    m = p[p.index("const SCR=(()=>{"):p.index("function renderScreens(){")]
    for old in ("GA4 sampled / logging badli", "GA4 se whole nahi", "Jis din GA4 ne koi hissa whole nahi diya"):
        assert old not in m, old


def test_the_apps_why_shows_whole_and_escaped(out):
    # the build's N/A why ("Not whole" + the missing W days by their state): the crumb, the All apps row and Needs
    # attention show it whole (never cut at its dash) and through the page's escaping
    why = "Not whole — 0 whole days of inline ads in the last 10 (GA4 sampled 10)"
    b = out["pages"]["b"]
    assert out["all_why_b"] == b["crumb"] == b["attn_why"] == why
    assert out["pages"]["h"]["crumb"] == "&lt;b&gt;bold&lt;/b&gt;"                  # (a why with markup: escaped)


def test_all_formats_when_ga4_gives_no_format_split(out):
    # allf 2: GA4 gave the screens without the format on most whole days — the header stays "Ads (all formats)", the
    # table's line says why is in Data coverage, whose note carries the measured full-screen share on app screens
    a = out["allf2"]
    assert a["head"] and a["sub"]
    head = "GA4 is app ke screen × format split ko sampled deta hai, isliye screens ke ads saare formats pe gine aur judge hue"
    assert a["note"] == [head + "; jin dinon split poora tha, app screens pe full-screen ads 0.23% the."]
    assert a["none"] == [head + " (split poora kisi din nahi mila)."]                 # no split day measured
    assert a["one"] == ["Format kam record hota hai (5% se zyada &quot;not set&quot;): screens ke ads sab formats pe gine "
                        "aur judge hue."]                                           # allf 1: its own note, as before
    assert a["off"] == [[], True]


def test_a_row_with_too_few_ads_shows_no_score(out):
    # under 1 % of the app's ads of its kind in the period AND its normal: "score —" (titled, no colour); an aggregate row has
    # no per-user score at all; a row the build left N/A "Too few ads" never in Needs attention
    low, mut = out["low"], '<span class="sc-mut" title="kam ads: app ke ads ka 1% se kam">score —</span>'
    assert low["share"] == [0.0244, 0.0098, 0.0049, 1]                 # Not recorded · Ad screens · GA4 grouped · a trigger
    assert low["cells"] == ['score <b class="">99</b>', "—", "—", "—"]
    assert low["ps"] == [[False, 99], [False, None], [True, None], [True, None]]
    assert low["dd"].endswith(" · <small>imp / user nahi (users jode nahi ja sakte)</small>")
    t = out["tiny"]
    assert t["attn"] == [0] and t["small"] == mut and t["big"] == '<span class="sc-mut">score —</span>'   # (no file 2: no users)
    assert t["why"].endswith("<small>Too few ads — 0.5% of the app&#39;s inline ads</small>")


def test_hostile_names_are_escaped(out):
    h = out["hostile"]
    assert not h["raw"] and h["esc"] and h["why"] and h["cause"]
    assert h["disp"] == "&lt;img src=x onerror=alert(1)&gt;"
    assert h["item"] == "&lt;x&gt;&quot;y&#39;"


def test_copy_report(out):
    assert out["copy_noapi"] == ["fallback", "✅ Copied (3 lines)", ["copy"], [0, 5], {"preventScroll": True}]
    assert out["copy_reject"] == ["async", "✅ Copied (3 lines)", ["copy"]]          # rejected → the selected textarea
    assert out["copy_ok"] == ["async", "✅ Copied (2 lines)", 0]
    assert out["copy_manual"] == ["manual", "Select karke copy karein"]
    assert out["copy_throw"][0] == "fallback"


def test_period_memory(out):
    p = out["per"]
    for k in ("bogus", "notjson", "old_mon", "future_mon", "half", "bad_date", "nul", "arr"):
        assert p[k] is None, k
    assert p["mon"] == {"k": "mon:2026-02", "f": "", "t": ""} and p["ok90"]["k"] == "90" and p["num"]["k"] == "7"
    assert p["cus"] == {"k": "cus", "f": "2026-01-01", "t": "2026-03-20"}           # swapped, clamped to d0
    assert p["cus_hi"] == {"k": "cus", "f": "2026-03-01", "t": "2026-03-30"}        # clamped to td
    assert out["per_throw"] == ["30", True] and out["per_badkey"] == "30" and out["per_good"] == "60"
    assert json.loads(out["per_saved"]) == {"k": "7", "f": "", "t": ""}


def test_chart(out):
    c = out["chart"]
    assert c["d"][:2] == ["d", 30] and c["d"][2] is None and c["d"][3] is None     # < 100 views / not whole: no point
    assert c["d"][4] == "GA4 sampled" and c["d"][5] is True and c["d"][6] is False
    assert c["d"][7] == {"last": "10.0", "avg": "Avg 10.0", "norm": "Normal 12.3"}
    assert c["w"][:2] == ["w", 29] and c["w"][4] == 10                              # > 120 days: weekly, Σ ads ÷ Σ views
    assert c["m"][:2] == ["m", 20] and c["m"][2] is None                            # > 540 days: monthly
    s = out["chart_svg"]
    assert s["normal"] and s["last"] and s["avg"] and s["bars"] == 27                # per user: a bar on each users day


def test_keep_holds_the_tapped_control(out):
    assert out["keep"] == {"dy": [60], "row": 140, "minh": "900px"}
    # the real taps call paint() inside keep(): the page's height stays held through that repaint (else a shorter page
    # lets the browser clamp the scroll before the control is put back) and unholdLater lets it go afterwards
    k = out["keep_paint"]
    assert k["held_in"] == "900px" and k["held_after"] == "900px" and k["dy"] == [-20]
    assert k["plain_paint"] == ""                                                   # a paint outside keep() drops a stale hold


def test_drill_down_belongs_to_its_app(out):
    s = out["switch"]
    assert s["same"] == [3, "cc", True, True, "ca-app-pub-0000000000000000~21"] and s["pushed"] == ["scr-dd"]   # same app: kept
    assert s["other"] == [None, False, False, False, ["scr-dd"]]                    # another app: closed, no row lit, Back step gone
    assert s["back"] == [None, False] and s["from_all"] is None


def test_attention_details_goes_to_the_drill_down(out):
    a = out["attn"]
    assert a["open"] == [2, [1432]]                                                 # 1500 − (0 top bar + 60 strip + 8)
    assert a["close"] == [None, []] and a["row"] == [2, []]                         # closing / a table row: no move


def test_late_file_redraws_only_its_slots_and_keeps_scroll(out):
    r = out["arrive"]
    # file 2 brings the screens' users: the table and the drill-down — never the App total (scr_all alone)
    assert r["f2"] == {"sc-ddb": 1, "sc-f-src": 0, "sc-f-ver": 0, "sc-f-cov": 1, "sc-f-rep": 0, "sc-total": 0, "sc-tb": 1} and r["dd"]
    assert r["kept"] == [300, 50, 25]                                               # the day box's place, sideways tables
    assert r["tb"] == [True, False, out["v2"]["main"][1]]                            # its numbers, no ⏳ left
    assert r["c_on_ver"] == r["f2"]                                                 # a country shard while on Versions: nothing
    assert r["r_on_ver"]["sc-ddb"] == 2 and r["r_on_ver"]["sc-f-src"] == 0 and r["r_on_ver"]["sc-tb"] == 1
    assert r["l_on_ver"] == {"sc-ddb": 3, "sc-f-src": 1, "sc-f-ver": 1, "sc-f-cov": 1, "sc-f-rep": 1, "sc-total": 0, "sc-tb": 1}


def test_whole_months_come_from_the_month_sums(out):
    m = out["month"]
    assert m["cc"] == [["[XA] Name XA", "20,000", "2,400", "12.0"], ["[XB] Name XB", "8,000", "800", "10.0"],
                       ["Other (GA4 grouped)", "500", "40", "8.0"]] and not m["cc_miss"]
    assert m["ver"] == [["1.0", "10,000", "1,200", "12.0"]] and not m["ver_miss"]
    assert m["lp_r"] == {"it": {"1.0": [10000, 1200, 0]}, "app": {"1.0": [40000, 4200, 1200]}, "miss": []}   # −1 rows: app level
    assert m["lp_c_mixed"] == {"XA": [36800, 4360, 0], "miss": [], "wait": []}      # Feb whole (cc_m) + Mar edge (shard)


def test_wiring():
    p = _page()
    assert '<li id="nav-scr-li" hidden><button data-screen="scr"><span class="i">🖼️</span> Screens</button></li>' in p
    assert "li.hidden=!SCR.ptr()" in p and "root.append(renderScreens())" in p
    assert "if(id==='scr') SCR.show(); else SCR.left();" in p
    assert re.search(r"scr:\['Screens','🖼️','scr','scr'\]", p)
    assert re.search(r"const HUB_ALL=\[[^\]]*'firstopen','scr'", p) and re.search(r"const HUB_APP=\[[^\]]*'firstopen','scr'", p)
    assert "(t!=='scr'||sc)" in p and "sc=!!SCR.ptr()" in p
    assert "(t!=='firstopen'||fo)" in p                                              # the pinned literals stay
    assert 'body[data-screen="scr"] #rangectl,body[data-screen="scr"] #rangecustom,body[data-screen="scr"] #rangemon{display:none!important}' in p
    assert 'body[data-screen="firstopen"] #rangectl,body[data-screen="firstopen"] #rangecustom{display:none!important}' in p
    assert 'scr:["Screens",' in p
    assert "['scr','scr'," not in p                                                  # no hub card
    # the module: no top-level DOM / storage work; its own sc- classes only (never the global 'chip')
    m = p[p.index("const SCR=(()=>{"):p.index("function renderScreens(){")]
    assert 'class="chip' not in m and "'chip'" not in m
    for c in re.findall(r'class="([^"$]+)"', m):
        for w in c.split():
            assert w.startswith("sc-") or w in ("card", "ct"), w                     # (the page's own card base)
    assert m.index("localStorage") > m.index("function perLoad")


def test_screen_views_wording(out):
    """'Visits' is 'Screen views' on the whole Screens tab (the data and sort keys keep their names)."""
    p = _page()
    for w in ("th('vu','Views / user / day'", "'Per 100 app views':'Ads / 100 views'", "<th>Screen views</th>", "tile('Time / view'",
              "tile('Exposure per view'", "Ads / 100 views", "Screen views (bars)", "['v','Screen views',['v']]",
              "<b>Screen views</b> = screen_view"):
        assert w in p, w
    a, b = p.index("const SCR=(()=>{"), p.index("function renderScreens(){")
    scr = p[a:b]
    assert not re.search(r"Visits|visits|visit\b", "\n".join(l for l in scr.split("\n") if not l.lstrip().startswith("//"))), "a 'visit' word is left"


def test_banner_refresh_line(out):
    """More than 1 ad per screen view (Ads / 100 above 100) and a known time per view: a line in the row details' Ads / 100
    tile (the main row is per user now)."""
    b = out["bn"]
    assert b["hot"] == ["150", "screen khuli rahe to banner har ~30–90 sec me dobara load hota hai: har refresh ek naya impression",
                        "1 view me 1 se zyada ad — banner refresh · avg 45 sec"]       # 44,600 s ÷ 1,000 views, rounded
    assert b["notime"] == ["150"] and b["calm"] == ["90.0"] and b["agg"] == ["150"]   # no engagement / 0.9 per view / aggregate
    assert b["fn"] == [45, None, None, None]                                           # exactly 100 is not above 1 · aggregate · no file 2
    assert b["table"] is False and b["full"] is False and out["bn_alpha"] is False      # never in the tables; Alpha is ~10 / 100


def test_dates_carry_their_year_when_not_in_the_reference_year(out):
    y = out["years"]                                                                     # reference year = the last final day's year (2026 here)
    assert y["all"] == "All time (GA4 · 20 Jun 2024 – 30 Mar 2026) · not final"          # All time crosses years: both ends carry it
    assert y["jan"] == "All time (GA4 · 9 Dec 2025 – 7 Jan 2026)"                        # a 30-day window over New Year
    assert y["old"] == "All time (GA4 · 1 Mar – 31 Mar 2025)"                            # a whole past-year range: the year at the end
    assert y["cur"] == "All time (GA4 · 27 Feb – 28 Mar)"                                # the reference year stays short
    assert y["one_old"] == "All time (GA4 · 4 Mar 2025)" and y["one_cur"] == "All time (GA4 · 4 Mar)"
    assert y["tip_week"].startswith("<b>28 Dec 2025 – 3 Jan 2026</b>") and y["tip_one"].startswith("<b>28 Dec 2025</b>")   # the New Year week: both years
    assert y["ticks_all"] == ["20 Jun 2024", "1 Apr 2025", "1 Mar"]                      # the axis ticks of a multi-year chart (monthly buckets)
    assert y["ticks_jan"] == ["9 Dec 2025", "23 Dec 2025", "7 Jan"]                      # over New Year: the December ticks carry 2025


def _ft(v):
    """The page's fmtT: "38s", "9m 21s", "1h 05m"."""
    t = _jr(v)
    if t < 60:
        return "%ds" % t
    if t < 3600:
        return "%dm %02ds" % (t // 60, t % 60)
    m = _jr(t / 60.0)
    return "%dh %02dm" % (m // 60, m % 60)


def test_time_format(out):
    # seconds as "38s", "9m 21s", "1h 05m" (minutes padded after an hour, seconds after a minute); under a second "<1s"
    assert out["fmt"] == ["0s", "<1s", "1s", "1s", "38s", "38s", "59s", "1m 00s", "1m 00s", "1m 20s", "9m 21s", "59m 59s",
                          "1h 00m", "1h 00m", "1h 05m", "1h 59m", "2h 00m", "24h 00m", "—", "—", "—", "—"]
    assert [_ft(v) for v in (38, 561, 3900, 79.5)] == ["38s", "9m 21s", "1h 05m", "1m 20s"]


def test_endsnap_class_toggle(out):
    e = out["es"]          # [class on, scrollLeft after]
    assert e["fits1136"] == [False, 0] and e["fitsWasOn"] == [False, 0]     # a table that fits is never stretched (1440 px laptops)
    assert e["over1000"][0] is True and e["over1240"][0] is True and e["edge1250"] == [False, 0]  # overflow decides, not a width
    assert e["hidden"][0] is False                                          # a box not shown (width 0) has it off
    assert e["keepScroll"] == [True, 180] and e["argScroll"] == [True, 120]  # the sideways scroll is put back
    assert e["none"] == "ok"                                                # no box: nothing happens


# ── v 2: Imp / user / day (owner, 6–7 Nov 2026: "total user ke samne kitna impression mila vo imp hota he") ─────────

def test_v2_screens_table_ten_columns_on_one_day_set(out):
    # main row = Screen | Imp / user / day | Normal | Score | Users / day | Views / user / day | Time / view | Time / user / day
    # | Ads / min | Cause — Ads / 100, screen views, ads and the share in the row details
    v = out["v2"]
    assert v["heads"] == ["Screen", "Imp / user / day", "Normal", "Score", "Users / day", "Views / user / day", "Time / view",
                          "Time / user / day", "Ads / min", "Cause"]
    # by hand: Σ Main's ads ÷ Σ its own users on the 27 days file 2 gives them (every 10th day missing) — never the mean of
    # the daily ratios (users vary by day)
    ads, users = sum(A_MAIN(k) for k in U_DAYS), sum(U_MAIN(k) for k in U_DAYS)
    assert v["hand"][0] == pytest.approx(ads / float(users)) and v["hand"][1] == 27
    assert ads / float(users) != pytest.approx(sum(A_MAIN(k) / float(U_MAIN(k)) for k in U_DAYS) / 27)
    assert v["fn"] == pytest.approx(v["hand"] + [30])
    # Imp / user / day and its Normal under 1 with three places, as the build's why prints them ("0.412 → 0.457"); the
    # other per-user columns keep two
    nk = [k for k in KN30 if k % 10 != 5]
    normal = sum(A_MAIN(k) for k in nk) / float(sum(U_MAIN(k) for k in nk))
    assert v["main"][1:] == ["<b>%s</b><small>27/30 days</small>" % _p3(ads / float(users)), _p3(normal),
                             'score <b class="">95</b>', "793", "1.35", "28s", "38s", "0.23", "Lower fill"]
    assert _p3(ads / float(users)) != _p2(ads / float(users)) + "0"                      # (the third place shows)
    # the chain on ONE day set, exactly: Views / user / day × Time / view × Ads / min ÷ 60 = Imp / user / day (also =
    # Time / user / day × Ads / min ÷ 60), on a period that reaches Today too (its per-user days end at ftU)
    assert all(abs(c) < 1e-12 for c in v["chain"]) and v["tm_n"] == [25, 30]
    # a day with the screen's users but no time read (file 2's "v" missing; views without engagement: a GA4 gap) is not
    # in the one day set: out of n, the ads, the users and Time / view
    t = v["notime"]
    assert t["users"] == [500, 600] and t["fn"][0] == t["hand"][0] == 25 and t["fn"] == pytest.approx(t["hand"])
    assert v["reach"][0] == pytest.approx(v["reach"][1])                             # Σ screen users ÷ Σ the app's daily users
    assert v["th_r"].startswith("is screen ke inline ads ÷ is screen ke users (roz unique; din ka jod) = Views / user / day ×")
    assert v["nofile"] == [True, None]                                               # never a number without file 2


def test_v2_aggregates_pinned_and_their_share(out):
    v = out["v2"]
    # an aggregate row: "—" (users are never added across screens) + "x % of ads" on one line (a phone's narrow column
    # wrapped "of the screen ads" into 4 lines; the full words in its title); Time / view and Ads / min where views and
    # time exist
    p = _p1(v["share"])
    assert v["other"][1] == '<b>—</b><small class="sc-nw" title="%s of the screen ads">%s of ads</small>' % (p, p)
    assert v["other"][2:6] == ["—"] * 4 and v["other"][7] == "—" and v["other"][6] == "13s" and v["other"][8] == "0.45"
    assert v["agg"] == [True, None]
    # pinned at the bottom in their fixed order under every sort
    for k, order in v["pinned"].items():
        assert order[-4:] == [2, 3, 4, 5], k


def test_v2_today_and_yesterday_show_the_ads_only(out):
    # no daily users yet, and the screen users are read hours apart from the ads: the main cell "—" with "ads N ⏳", the
    # chain columns "—"
    for k in ("today", "yday"):
        c = out["v2"][k]["cells"]
        assert c[1] == "<b>—</b><small>ads %d ⏳</small>" % out["v2"][k]["ads"], k
        assert c[4:9] == ["—"] * 5 and c[3] == '<span class="sc-mut">score —</span>'


def test_v2_full_screen_table_per_app_user(out):
    f = out["v2"]["fs"]
    assert f["heads"] == ["Trigger", "Imp / app user / day", "Normal", "Score", "Cause"]
    assert f["fn"][0] == pytest.approx(f["hand"]) and f["fn"][1] == 30               # Σ trigger ads ÷ Σ the app's daily users
    assert f["cell"][1] == "<b>0.073</b>" and f["th"].startswith("trigger ke ads ÷ app ke daily users")
    assert f["cell"][2] == _p3(40 * 30 / float(sum(AU(k) for k in KN30)))           # its Normal: the build's three places


def test_v2_app_total_block(out):
    t = out["v2"]["total"]
    assert t["rows"] == ["Imp / user / day", "Daily users", "Views / user / day"]
    assert t["heads"] == ["30 days", "Normal", "7 days", "Yesterday", "Today"] and t["no_tiles"]
    # GA4's inline + full-screen + not recorded ÷ the app's daily users; a copy day AdMob did not confirm ("dk" 2): its
    # not recorded left out and said so; the hover's parts add up to the printed total
    assert t["fn"][0] == pytest.approx(t["hand"][0]) and t["fn"][4] == pytest.approx(t["hand"][1]) and t["fn"][6] == t["hand"][2] == 1
    tt, cell = t["imp"][0]
    m = re.match(r"inline ([\d.]+) \+ full-screen ([\d.]+) \+ not recorded ([\d.]+) = ([\d.]+) · GA4 ad_impression ÷ app ke daily "
                 r"users \(GA4 Active users, wahi stream\) · sirf final din · copy-pattern din: 1, unke not-recorded ads gine nahi$", tt)
    assert m and round(sum(float(g) for g in m.groups()[:3]), 3) == float(m.group(4)) and cell.startswith("<b>%s</b>" % m.group(4))
    # under 1: three places everywhere it is an Imp / user / day number (the cell, its hover, the Normal, the crumb, the
    # per-format tiles in its details) — the build's why prints "0.412 → 0.457"
    r, ir, fr, nr = _app_u(K30)
    assert m.groups() == (_p3(ir), _p3(fr), _p3(nr), _p3(r)) and t["imp"][1][1] == "<b>%s</b>" % _p3(_app_u(KN30)[0])
    assert t["tiles"] == [["Inline / user", _p3(ir)], ["Full-screen / user", _p3(fr)], ["Not recorded / user", _p3(nr)]]
    assert t["imp"][3][1].startswith("<b>—</b><small>ads ") and t["imp"][4][1].startswith("<b>—</b><small>ads ")   # Yesterday · Today
    assert t["note"] and "App total <b>%s</b> vs %s <small>" % (_p3(r), _p3(_app_u(KN30)[0])) in t["crumb"]
    assert t["nvr"]                                                                  # the users mix in the details (GA4 = AdMob)


def test_v2_needs_attention_one_line_per_cause(out):
    a = out["v2"]["attn"]
    assert a["app"].startswith('<span class="hub-st st-bigda">bigda</span><span class="sc-atn">App total</span>')
    # the users mix, measured parts only (critic S1: never "not the cause")
    assert "ads / view: new-user mix +1.2%, within −20.5% · views / user −3.1% (split nahi" in a["app"] and "not the cause" not in a["app"]
    # two rows of one cause group ("Mixed: A + B" groups under A): one line, ≈ Σ their impacts; the rows open under it
    assert a["sum"][0] == ["bigda", "Lower fill", "2 rows (Main, Interstitial · Back press) · ≈ −14.1% of the app's imp/user"]
    assert [r[0] for r in a["list"]] == ["Main", "Interstitial · Back press", "All other screens"]
    # each row's impact and its whole days of the last 10 — from scr_all's status alone, so they are there on the first
    # paint (file 2 comes later and never redraws this card): a status without them (an older file) prints none, never
    # file 2's (its row has 10 W days here)
    assert a["list"][0][1] == "−12.0% · 9/10 days · ads/100 34% gira" and a["list"][2][1] == "−3.0% · 10/10 days · thoda gira"
    assert "/10 days" not in a["list"][1][1]
    assert a["no_dw"][0] == ["Main", "−12.0% · ads/100 34% gira"] and a["f2_w"] == 10
    # GA4 ≠ AdMob: judged on AdMob ("Worse (AdMob)"), without GA4's users mix (the same GA4 logging); AdMob too thin: N/A
    # with a ⚠️ line
    assert a["admob"].startswith('<span class="hub-st st-bigda">bigda</span> <small class="sc-adm">(AdMob)</small>')
    assert "new-user mix" not in a["admob"] and "new-user mix" not in a["na"]
    assert a["na"].startswith("⚠️ <span class=\"sc-atn\">App total</span><span class=\"sc-atr\">Not measurable (GA4 ≠ AdMob)")


def test_v2_all_apps_from_scr_all_alone(out):
    a = out["v2"]["all"]
    assert a["heads"] == [["rank", "App · status"], ["r", "Imp / user / day"], ["n", "Normal"], ["sc", "Score"],
                          ["dau", "Daily users"], ["wn", "Worse"], ["an", "Watch"]]
    r, ir, fr, _nr = _app_u(K30)                                                    # under 1: three places (the build's _q)
    assert a["alpha"][0] == "<b>%s</b><small>%s · %s</small>" % (_p3(r), _p3(ir), _p3(fr)) and a["fn"] == _p3(r)
    assert a["alpha"][1] == _p3(_app_u(KN30)[0]) and a["alpha"][3] == "550"
    assert a["loads"] == []                                                          # no file 2 asked for (scr_all's "au")
    assert a["admob"]                                                                # "Worse (AdMob)"
    assert a["mute"] == [True, None, True] and a["keep"] == [False, True]            # a data N/A mutes the period score only


def test_v2_admob_judged_app_row_mutes_the_ga4_score(out):
    # critic S3 after B3: "Worse (AdMob)" (GA4 ≠ AdMob) never sits next to a GA4 period score — "score —" (titled) in All
    # apps, the App total and the details; the crumb drops its GA4 "vs"; the GA4 Imp / user number itself stays
    m, why = out["v2"]["all"]["admob_mute"], "GA4 logging changed (GA4 ≠ AdMob) — period score GA4 pe nahi"
    mut = '<span class="sc-mut" title="%s">score —</span>' % why
    assert m["all"][0].startswith("<b>") and m["all"][0] != "<b>—</b>"            # Imp / user / day kept
    assert m["all"][1] == mut and m["all"][2] is None
    assert m["total"].startswith("<b>") and "<small>%s</small>" % mut in m["total"] and "score <b" not in m["total"]
    assert "App total <b>" in m["crumb"] and " vs " not in m["crumb"]
    assert m["tile"] == "inline %s · full %s" % (mut, mut)
    # GA4's new vs returning split comes from the GA4 logging that changed: not in the details, not in Needs attention —
    # nor for an App row not measurable (GA4 ≠ AdMob, AdMob too thin)
    assert m["nvr"] == [False, False, False]


def test_v2_drill_down_parts_reach_and_chart(out):
    d = out["v2"]["dd"]
    assert d["tiles"][0][:2] == ["Ads / 100 views", "10.9"] and "32,145 views · 3,511 ads" in d["tiles"][0][2]
    assert d["tiles"][1][:2] == ["Screen users / day", "793"] and d["tiles"][1][2].startswith("Reach ")
    assert d["parts"] == [["Views per user", "−3.2%"], ["Time per view", "+1.1%"], ["Ads per minute", "−31.9%"]] and d["why"]
    assert " · reach <b>" in d["head"] and d["adlogic"]
    assert d["months"] == [["Month", ["Screen users / day", "Ads", "Imp / user", "Reach"]], ["Day", ["Screen users / day", "Ads", "Imp / user", "Reach"]]]
    assert d["svg"] == {"aria": True, "normal": True, "last": True, "avg": True, "bars": 27} and d["ch"]["pu"]
    assert out["v2"]["days"]["last2"] == [[None, True, "users abhi nahi (~2 din baad)"]] * 2   # Today / Yesterday: no users
    c = out["v2"]["chart"]
    assert c[0] == [None, 0.8, None] and c[1] == {"last": "0.80", "avg": "Avg 0.80", "norm": "Normal 0.90"} and c[2]
    assert "users abhi nahi" in c[3] and "100 se kam user-days: point nahi" in c[4]


def test_v2_waits_for_file_2_and_refuses_v1(out):
    w = out["v2_wait"]
    assert w["main"][1] == "⏳" and w["ud"][1] == "⏳" and w["total"]                 # the App total never waits
    assert w["other"][1].endswith("% of ads</small>")                                # an aggregate row needs no file
    assert w["err"][1] == "<b>—</b><small>data load nahi hua</small>" == w["v1"][1]   # failed / a v 1 file: refused, said so
    n = out["v2_none"]
    assert n["one"][1] == "<b>—</b><small>GA4 sampled 7 din</small>" and n["fn"] is None
    assert n["total"] == [' title="app ke daily users doosre GA4 stream ke hain — gine nahi"', "<b>—</b>"]


def test_v2_page_contract():
    p = _page()
    m = p[p.index("const SCR=(()=>{"):p.index("function renderScreens(){")]
    assert "j.v!==2||!j.apps" in m and "j=>!!j&&j.v===2&&j.key===a.key&&Array.isArray(j.days)" in m and "j=>!!j&&j.v===2&&(j.key==null" in m
    assert "j=>!!j&&j.v===1&&j.key===a.key&&String(j.m)" in m                       # shards stay v 1
    for gone in ("puTile", "function tilesIn", "function miniHtml", "function perUser", "function appUser", "'Inline ads / 100'"):
        assert gone not in m, gone
    assert "colspan=\"${seg==='f'?5:10}\"" in m and "sc-t10" in m and "#sc-ttw.sc-endsnap .sc-t.sc-t10 th:last-child" in p
    assert ".sc-t td small.sc-nw{white-space:nowrap}" in p                          # the aggregates' "x% of ads": one line


def test_v2_per_user_numbers_print_as_the_build_does(out):
    # under 1: three places, the build's _q ("0.412 → 0.457" in its why), from 1 up as before; the App total's hover
    # parts add up to its printed total on the same places
    from admob_iq import screens_build as sb
    vals = [0, 0.0004, 0.0451, 0.412, 0.4126, 0.9996, 1, 4.517, 12.34, 123.4, 1234.6, None]
    assert out["pq"] == [sb._q(v) for v in vals] == ["0.000", "0.000", "0.045", "0.412", "0.413", "1.000", "1.00", "4.52",
                                                     "12.3", "123", "1,235", "—"]
    assert out["addup"] == [{"t": "0.500", "p": ["0.375", "0.125"]}, {"t": "1.00", "p": ["0.34", "0.33", "0.33"]},
                            {"t": "123", "p": ["100", "23"]}, {"t": "12.3", "p": ["6.1", "6.2"]}]


def test_v2_details_show_the_rows_share_of_the_apps_screen_views(out):
    # the Ads / 100 tile: "x% of the app's screen views" (the row's views ÷ the app's, the period) for a screen and an
    # aggregate row — never a trigger (its views are the app's own)
    assert out["alpha"]["ov_share"] == [_p1(sum(1000 + k for k in K30) / float(sum(1870 + k for k in K30))),
                                        _p1(300 * 30 / float(sum(1870 + k for k in K30))), None]

