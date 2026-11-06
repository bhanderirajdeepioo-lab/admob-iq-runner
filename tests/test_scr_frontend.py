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
showing no score (and a "Too few ads" row never in Needs attention), and the wiring into the page (gated on DATA.scr).
Skipped where node is not installed. No real data."""
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
    r = subprocess.run([NODE, os.path.join(ROOT, "tests", "scr_frontend.js"), PAGE],
                       check=True, capture_output=True, text=True, timeout=120)
    rep = json.loads(r.stdout)
    assert not rep["errors"], rep["errors"]
    return rep["out"]


def test_pointer_and_lazy_load(out):
    assert out["no_ptr"] and out["bad_file"] and out["no_apps"] and out["no_ptr_note"]
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
            ["u", 5, 6], ["s", 5, 6], ["x", 5, 6]]
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
    assert out["sort_v"][:2] == ["Alpha App", "Beta App"] and out["sort_v"][-1] == "Empty App"   # by visits; no days last
    assert out["sort_items"] == [0, 2, 1, 4, 3, 5]                                   # Worse, Watch, Normal, then unjudged by visits


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
    assert p["a"]["rows"] == [0, 2, 1, 4, 3, 5]
    assert not p["b"]["ok_all"]                                                      # all N/A: never "Sab screens normal"
    assert out["hidden_page"]


def test_app_page_parts(out):
    a = out["a_page"]
    assert a["crumb"] and a["mini"] and a["seg"] and a["period"] and a["cus_row"] and a["how"]
    assert a["tiles"] == [["Visits", "58,245"], ["Inline ads / 100", "10.6"], ["Full-screen / 100", "3.3"], ["Status", "1 Worse · 1 Watch"]]
    assert a["attn"][0] == ["bigda", "Main", "ads/100 12.0 → 8.8 (−27%)"] and a["attn"][1][0] == "dhyan"
    assert a["editor"] and a["title"] and a["unjudged"] == 3                         # "Activity" dropped, the full class on hover
    assert a["folds"] == ["src", "ver", "cov", "rep", "how"]
    assert a["cov_fold"] and a["rep_fold"] and a["src_fold"] and a["notes"]
    assert a["chips"] == ["today", "yday", "7", "tm", "lm", "30", "60", "90", "all", "cus", "mon:2026-01", "mon:2026-02", "mon:2026-03"]
    assert a["mover"] == [["mon:2026-01", "false", False, "‹"], ["mon:2026-02", "false", False, "Feb 2026"], ["mon:2026-03", "false", False, "›"]]
    assert out["today"] == {"line": True, "muted": True}                             # "Today (GA4 · 30 Mar) · not final", score muted
    assert out["top"] == [0, 1, 2, 3, 4, 5]
    assert out["top_many"] == [0, 1, 2, 9, 10]                                       # 90 % of views + the Worse row + unjudged
    assert out["many_less"] == [[9, 0, 1, 2, 10], "6"] and out["many_more"] == [11, True]


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
    assert x["eng"] == [["Time per visit", "28 s"], ["Ads per minute", "0.23"], ["Clicks", "90"], ["Exposure per visit", "0.04 s"],
                        ["Saw ads ÷ users", "75.0%"], ["Sessions", "27,000"]]
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
    assert out["a_page"]["mini"]                                                     # "Normal 28 days before"
    # the short cell labels: the History column, the crumb, the days a number stands on, a unit AdMob does not have
    assert out["all_hist"] == ["from 1 Jan 2026 ✓"] * 4 + ["from 20 Mar 2026 ⏳", "from 1 Jan 2026 ✓"]
    assert out["a_page"]["crumb"] and out["a_page"]["visits_sub"]                    # "history from 1 Jan 2026", "30 days"
    assert out["pages"]["c"]["basis"] == "20/30 days"                                # a row's days with inline ads
    assert out["gamma"]["month_days"] == ["20/30 days", "19/28 days", "20/31 days"]  # Every month: days with the number
    assert out["not_in_admob"] == "<small>Not in AdMob</small>"


def test_phone_tiles_wrap_into_two_columns():
    # ≤ 480 px: the KPI tiles in a 2-column grid (all four in view, no sideways scroll); wider phones / desktop unchanged
    p = _page()
    css = p[p.index("/* ---------- 🖼️ Screens"):p.index("/* ---------- 👥 Audience")]
    assert ".sc-tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:0 0 14px}" in css
    i760, i480 = css.index("@media (max-width:760px){"), css.index("@media (max-width:480px){")
    assert i480 > i760                                                               # after the 760 px rules: it wins
    rule = css[i480:css.index("}}", i480) + 2]
    assert ".sc-tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;overflow-x:visible}" in rule
    assert ".sc-k{min-width:0;max-width:none}" in rule


def test_a_section_needing_both_files_shows_a_failed_file_2(out):
    g = out["gate"]
    for s in ("ver", "nvr", "x"):                                                    # file 2 failed, scr_l here
        assert g[s] == ["scr_a00000000001.json.gz", False, False], s                 # Try again, never "Loading" for good
    assert g["cc"] == [None, False, True]                                            # scr_l only: drawn
    assert g["ver_loading"] == [None, True, False]                                   # file 2 still on its way
    assert g["nvr_l_err"] == ["scr_l_a00000000001.json.gz", False, False]


def test_status_sort_honours_its_direction(out):
    t = out["tsort"]
    assert t["asc"] == [[0, 2, 1, 4, 3, 5], "ascending"]                             # Worse first (the default)
    assert t["desc"] == [[4, 3, 5, 1, 2, 0], "descending"]                           # a second tap: reversed, as its header says
    assert t["back"] == t["asc"]
    assert out["sort_items_desc"] == [4, 3, 5, 1, 2, 0]                             # unjudged first (by visits), Worse last


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
    # the N/A line says the status names each part, a layer note counts the days not read beside the ones GA4 gave
    na, score = out["a_page"]["how_na"]
    assert na == ('whole din kam ("Not whole" — kitne din kis wajah se, saath me likha: GA4 sampled / rows chhodi / '
                  'grouped / abhi padhe nahi …) / logging badli / ads nahi / ads bahut kam ("Too few ads" — W aur N '
                  'dono me app ke us kism ke ads ka 1% se kam)')
    assert score == "koi hissa whole nahi (GA4 ne sampled / grouped / rows chhodi, ya wo din abhi padha nahi)"
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
    # under 1 % of the app's ads of its kind in the period AND its normal: "score —" (titled, no colour) in the table and
    # the drill-down, the score left out of the sort; a row the build left N/A "Too few ads" never in Needs attention
    low, mut = out["low"], '<span class="sc-mut" title="kam ads: app ke ads ka 1% se kam">score —</span>'
    assert low["share"] == [0.0244, 0.0098, 0.0049, 1]                 # Not recorded · Ad screens · GA4 grouped · a trigger
    assert low["cells"] == ['score <b class="">100</b>'] * 2 + [mut] * 2
    assert low["ps"] == [[False, 100], [False, 100], [True, None], [True, None]]
    assert low["dd"].endswith(" · " + mut)
    t = out["tiny"]
    assert t["attn"] == [0] and t["big"] == 'score <b class="sc-dn">60</b>' and t["small"] == mut
    assert t["why"].endswith("<small>Too few ads — 0.5% of the app&#39;s inline ads</small>")
    assert out["a_page"]["how_low"]                                                  # How this works says so


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
    assert c["d"][:2] == ["d", 30] and c["d"][2] is None and c["d"][3] is None     # < 100 visits / not whole: no point
    assert c["d"][4] == "GA4 sampled" and c["d"][5] is True and c["d"][6] is False
    assert c["d"][7] == {"last": "10.0", "avg": "Avg 10.0", "norm": "Normal 12.3"}
    assert c["w"][:2] == ["w", 29] and c["w"][4] == 10                              # > 120 days: weekly, Σ ads ÷ Σ visits
    assert c["m"][:2] == ["m", 20] and c["m"][2] is None                            # > 540 days: monthly
    s = out["chart_svg"]
    assert s["normal"] and s["last"] and s["avg"] and s["bars"] == 30


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
    assert r["f2"] == {"sc-ddb": 1, "sc-f-src": 0, "sc-f-ver": 0, "sc-f-cov": 1, "sc-f-rep": 0} and r["dd"]
    assert r["kept"] == [300, 50, 25]                                               # the day box's place, sideways tables
    assert r["c_on_ver"] == r["f2"]                                                 # a country shard while on Versions: nothing
    assert r["r_on_ver"]["sc-ddb"] == 2 and r["r_on_ver"]["sc-f-src"] == 0
    assert r["l_on_ver"] == {"sc-ddb": 3, "sc-f-src": 1, "sc-f-ver": 1, "sc-f-cov": 1, "sc-f-rep": 1}


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
