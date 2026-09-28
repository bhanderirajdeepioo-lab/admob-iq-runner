"""The Uninstall tab's frontend (frontend/index.html), rendered for real: tests/uninstall_frontend.js runs the page's
own script in a node vm on the committed fixture (the real build's output) and renders every Uninstall state —
portfolio (every Period and sort, every "At a glance" chip opened), each app in every chart / table mode, the
"Every day" pages, the App filter. Checked here: it parses and renders without errors or "undefined"/"NaN", every
title / heading / column / button / chip is English (short explanations may stay plain Roman Hinglish: no cumulative /
checkpoint / cohort / bharosa / headline, no Devanagari), the "How many stay" line never rises and stays within
0–100%, the "Stay after N days" tiles and the chips say exactly what the engine computed, and each chip opens exactly
its apps (no run-on app list by default). Skipped where node is not installed."""

import json
import math
import os
import re
import shutil
import subprocess
from datetime import date, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.environ.get("UNINSTALL_FE_FIXTURE") or os.path.join(ROOT, "tests", "fixtures", "uninstall_sample.json")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    path = str(tmp_path_factory.mktemp("fe") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "uninstall_frontend.js"), path, FIXTURE],
                         check=True, capture_output=True, text=True, timeout=180)
    return json.loads(out.stdout)


@pytest.fixture(scope="module")
def fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def per100(v):
    """The page's "of every 100" number (uni100): 1 decimal under 10, else whole (JS rounding: half up)."""
    x = v * 100
    return ("%.1f" % x).rstrip("0").rstrip(".") if 0 < x < 10 else str(int(math.floor(x + 0.5)))


def day_txt(iso):
    """The page's date (uniD) for a day of the fixture's own recent months: "14 Sep"."""
    m = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return "%d %s" % (int(iso[8:]), m[int(iso[5:7]) - 1])


def span_txt(a, b):
    """The page's install-day span (uniSpan) for two days of the fixture's own recent months: "16–22 Sep"."""
    if a == b:
        return day_txt(a)
    return ("%d" % int(a[8:]) if a[:7] == b[:7] else day_txt(a)) + "–" + day_txt(b)


def shown_gap(v):
    """The verdict's gap as shown: the difference of the two numbers on screen (uniVGap)."""
    return round(float(per100(v["recent"]["left"])) - float(per100(v["prev"]["left"])), 1)


def verdict_kind(v, min_pp):
    """The page's uniVKind: worse / better (a real change) · low · unsure (shown gap ≥ min_pp, not a real change) · same."""
    if v is None:
        return "none"
    if v["fires"]:
        return "worse" if v["dir"] == "worse" else "better"
    if v["low_sample"]:
        return "low"
    return "unsure" if abs(shown_gap(v)) >= min_pp else "same"


def gap_txt(v):
    """An app chip's short Δ: "−3", "+4", or with its day when that isn't day 7 ("−3 · 3 days")."""
    g = shown_gap(v)
    s = ("+" if g > 0 else "−" if g < 0 else "") + ("%g" % abs(g))
    return s if v["n"] == 7 else s + " · " + ("install day" if v["n"] == 0 else "1 day" if v["n"] == 1 else "%d days" % v["n"])


def expected_chips(fixture):
    """Every All-apps "At a glance" chip → its apps in page order, each with the short text its app chip shows."""
    by_id = {a["app_id"]: a for a in fixture["asset"]["apps"]}
    dets = [by_id[x["app_id"]] for x in fixture["dashboard_uninstall"]["apps"] if by_id.get(x["app_id"], {}).get("data_till")]
    mp = fixture["asset"]["consts"]["min_pp"]
    want = {k: [] for k in ("worse", "wk_up", "better", "wk_dn", "same", "unsure", "none",
                            "r_up", "r_zero", "r_dn", "r_ok", "r_none")}
    for a in dets:
        v = a["survival"]["verdict"]
        k = verdict_kind(v, mp)
        coh = [x for x in a["alerts"] if x["family"] == "cohort"]
        for d, key in (("up", "wk_up"), ("down", "wk_dn")):
            spans = [span_txt(x["installs_from"], x["installs_to"]) for x in coh if x["dir"] == d]
            if spans:
                want[key].append((a["app"], ", ".join(spans)))
        if k in ("worse", "better"):
            want[k].append((a["app"], gap_txt(v)))
        elif coh:
            pass                                                   # counted under "Some install weeks …"
        elif k == "unsure":
            want["unsure"].append((a["app"], gap_txt(v)))
        elif k == "same":
            want["same"].append((a["app"], ""))
        else:
            want["none"].append((a["app"], ""))
        # the daily rate (uniRateState): open rate alerts, or the last 7 days outside the normal range
        R = a["rate_now"]
        has = any(r is not None for r in a["daily"].get("rate") or []) and R.get("last7") is not None
        band = R.get("lo") is not None and R.get("hi") is not None
        hi = has and R.get("out_of_band") and band and R["last7"] > R["hi"]
        lo = has and R.get("out_of_band") and band and R["last7"] < R["lo"]
        up, dn, zero = (["Last 7 days high"] if hi else []), (["Last 7 days low"] if lo else []), []
        for x in a["alerts"]:
            if x["family"] == "rate_zero":
                zero.append("0 recorded · " + day_txt(x["day"]))
            elif x["family"] == "rate_spike":
                (up if x["dir"] == "up" else dn).append(("Spike · " if x["dir"] == "up" else "Drop · ") + day_txt(x["day"]))
            elif x["family"] == "rate_drift":
                (up if x["dir"] == "up" else dn).append(("Rising since " if x["dir"] == "up" else "Falling since ") + day_txt(x["since"]))
        if up:
            want["r_up"].append((a["app"], ", ".join(up)))
        if zero:
            want["r_zero"].append((a["app"], ", ".join(zero)))
        if not up and dn:
            want["r_dn"].append((a["app"], ", ".join(dn)))
        if not up and not zero and not dn:
            want["r_ok" if has else "r_none"].append((a["app"], ""))
    return want


def test_every_uninstall_state_renders_without_errors(report):
    assert report["errors"] == [] and report["bad"] == []
    assert report["scenarios"] >= 80


def test_plain_roman_hinglish_only(report):
    assert report["jargon"] == [] and report["devanagari"] == []


def test_every_title_label_and_chip_is_english(report):
    # none of the old Hinglish titles / buttons / chips anywhere on the tab ("Ek nazar me", "Kya badla?", "Usi din", …)
    assert report["old_titles"] == []
    assert report["titles"] == "Uninstall|Installs vs uninstalls (GA4)"                 # the top bar over every view
    h = report["has"]
    for k in ("glance_app", "portfolio_titles", "portfolio_cols", "daily_title", "curve_title", "modes", "toggle",
              "what_changed", "table_link", "table_open", "table_cols", "tri_labels", "tri_buttons", "avg4_row",
              "back_link", "open_links", "row_pills", "provisional_tag", "new_tag", "all_normal", "zoom_pill",
              "fetched_english"):
        assert h[k], k


def test_filled_days_are_an_estimate_and_emptied_rows_take_older_installs(report):
    h = report["has"]
    assert h["incomplete_kept"] and h["estimate_pill"] and h["estimate_cells"] and h["older_installs"]


def test_the_rate_tile_names_its_7_days_and_long_notes_are_one_line_until_tapped(report):
    h = report["has"]
    assert h["rate_window"]              # "Daily uninstall rate · last 7 days", its dates by the number, alerts first
    assert h["timing_fold"]              # "⏱️ When will I know?" — one line, its points on a tap
    assert h["header_gone"]              # the All apps table's footnote: one line


def test_the_how_many_stay_line_starts_at_100_and_never_rises(report):
    c = report["charts"]
    assert c["count"] >= 30 and c["all_never_rise"] and c["all_within"] and c["all_start_100"]
    assert c["all_hover_both"]                                  # hover: "N% stay" and "M% gone that day" together


def test_the_every_day_triangle_4_week_row_is_the_engines(report):
    assert report["avg4"]["bad"] == [] and report["avg4"]["checked"] >= 80


def test_the_owners_texts_are_all_there(report):
    assert {k: v for k, v in report["has"].items() if not v} == {}


def test_each_apps_stay_tiles_say_what_the_engine_computed(report, fixture):
    for a in fixture["asset"]["apps"]:
        c, days = a["survival"]["all"], a["survival"]["key_days"]
        want = [[N, per100(c["left"][N])] for N in days if N < len(c["left"]) and c["left"][N] is not None]
        assert want and report["summary"][a["app"]] == want, a["app"]


def test_the_portfolio_pools_every_apps_curve_the_engines_way(report, fixture):
    curves = [a["survival"]["all"] for a in fixture["asset"]["apps"]]
    S, left = 1.0, []
    for N in range(91):
        X = sum(c["x"][N] for c in curves if N < len(c["x"]))
        R = sum(c["r"][N] for c in curves if N < len(c["r"]))
        S *= 1 - (min(1, X / R) if R > 0 else (1 if X > 0 else 0))
        left.append(S)
    assert report["pooled"] == [[N, per100(left[N])] for N in (1, 7, 30, 90)]


def test_the_all_time_normal_row_is_the_apps_own_curve_and_never_goes_down(report):
    assert report["ref"]["bad"] == [] and report["ref"]["checked"] >= 80


def test_the_rate_tile_never_says_normal_next_to_an_open_rate_alert(report):
    assert report["rate_bad"] == []
    st = report["rate_states"]
    assert st["Demo Launcher"] == {"state": None, "alerts": ["⚠️ Spike · 23 Sep"]}
    assert st["Demo Wallpapers"] == {"state": None, "alerts": ["🟡 0 recorded · 14 Sep"]}
    assert st["Demo Weather"] == {"state": None, "alerts": ["⚠️ Rising since 12 Sep"]}
    assert st["Demo Caller – Test App"] == {"state": "normal", "alerts": []}
    assert st["Demo Notes"] == {"state": None, "alerts": []}                     # no rate yet: no chip at all


def test_an_open_install_alert_is_its_own_chip_never_under_a_plain_green_tick(report, fixture):
    assert report["coh_bad"] == []
    # the "Same as last month" count leaves out every app with an open install alert, and apps whose shown numbers
    # differ by min_pp or more without a real change ("Maybe changed"); worse / better stay where they were
    want, chips = expected_chips(fixture), report["xp"]["chips"]
    assert chips["same"] == {"label": "Same as last month", "n": len(want["same"])} and want["same"]
    assert chips["unsure"] == {"label": "Maybe changed", "n": len(want["unsure"])} and want["unsure"]
    for a in fixture["asset"]["apps"]:
        for x in a["alerts"]:
            if x["family"] == "cohort" and x["dir"] == "up":
                assert a["app"] in report["xp"]["open"]["wk_up"]["apps"]


def test_every_status_chip_opens_exactly_its_apps(report, fixture):
    want, xp = expected_chips(fixture), report["xp"]
    labels = {"worse": "Worse than last month", "wk_up": "Some install weeks worse", "better": "Better than last month",
              "wk_dn": "Some install weeks better", "same": "Same as last month", "unsure": "Maybe changed",
              "none": "Not enough data yet", "r_up": "Higher", "r_zero": "0 recorded", "r_dn": "Lower", "r_ok": "Normal",
              "r_none": "No rate yet"}
    assert sum(1 for L in want.values() if L) >= 9                          # the fixture opens most of them
    for k, L in want.items():
        o = xp["open"][k]
        if not L:                                                             # an empty group: no chip, nothing to open
            assert k not in xp["chips"] and o["panel"] is None and o["apps"] == [], k
            continue
        assert xp["chips"][k] == {"label": labels[k], "n": len(L)}, k
        assert o["panel"] == k and o["panels"] == 1 and o["on"] == 1, k      # one list open, its chip marked
        assert o["apps"] == [app for app, _ in L], k                          # exactly its apps, in the page's order
        assert o["text"].startswith(labels[k] + " "), k
        for app, short in L:                                                  # each app chip's short date / Δ
            assert (app + " " + short if short else app) in o["text"], (k, app, short)


def test_no_run_on_app_list_renders_by_default(report, fixture):
    xp, portfolio = report["xp"], report["portfolio"]
    assert xp["default_open"] is False                                        # no chip open, no app chip in the card
    assert xp["glance"].strip().startswith("📌 At a glance All apps Stay after 1 day ")
    for a in fixture["asset"]["apps"]:
        assert a["app"] not in xp["glance"]                                   # counts only — the names wait for a tap
    for s in ("me kuch dino ke installs", "Roz ka uninstall rate:", "pichhle mahine se kam bache", "baaki 1", "baaki 2", "baaki 3",
              "pichhle mahine jaisa", "apps me pichhle mahine", "100 naye users me se"):
        assert s not in portfolio, s


def test_every_gap_is_the_difference_of_the_numbers_shown(report):
    assert report["gap_bad"] == []


def test_the_curve_labels_the_summarys_days_and_its_phone_tooltip_is_readable(report):
    assert report["label_bad"] == [] and report["tip_big"]


def test_the_summary_and_the_curve_name_the_same_installs(report):
    assert report["span_bad"] == []


def test_an_apps_detail_puts_its_name_in_the_header_and_back_clears_it(report):
    h = report["header"]
    assert h["app"] == h["name"] and h["uniapp"] == h["id"] and h["calls"] == ["render", "show"]
    assert '<option value="%s" selected>' % h["name"] in h["sel"]                     # the header's App selector
    assert h["screen"].startswith('<span class="backlnk" onclick="uniBack()">← All apps</span>')
    assert h["after"]["app"] == "" and h["after"]["uniapp"] == ""
    assert h["after"]["sel"] == '<option value="">All apps (0)</option>' and "Uninstall" in h["after"]["screen"]
    assert not any("✕ Saari apps dikhao" in v for k, v in report["texts"].items() if k != "overview_no_admob")


def test_the_totals_meta_says_every_install_since_the_launch_and_where_the_stay_numbers_come_from(report, fixture):
    for a in fixture["asset"]["apps"]:
        t, c, L = report["totals"][a["app"]], a["survival"]["all"], a["launch"]
        head = ("Since launch (%s)" if L["hidden"] else "Since GA4 start (%s)") % t["day"]
        want = "%s: %s installs" % (head, t["installs"])
        if c["k"]:
            want += ' · "Stay" numbers from %d install days' % c["k"][0]
            gone = ["%s: data %s" % (", ".join(day_txt(d) for d in L_), w) for L_, w in
                    ((c["gap_inc"], "incomplete"), (c["gap_brk"], "missing")) if L_]
            if gone:
                want += " (%s — not counted)" % ", ".join(gone)
        assert t["line"] == want, a["app"]
    tx = report["texts"]                                    # a tracking break is "data missing", an incomplete day "incomplete"
    assert "(14 Sep: data missing — not counted)" in tx["detail|Demo Wallpapers|all|30|cp|false"]
    assert "(3 Sep: data incomplete — not counted)" in tx["detail|Demo Launcher|all|30|cp|false"]


def test_test_installs_before_the_launch_are_hidden_with_one_line_and_shown_on_a_tap(report, fixture):
    wall = [a for a in fixture["asset"]["apps"] if a["launch"]["hidden"]]
    assert [a["app"] for a in wall] == ["Demo Wallpapers"] and wall[0]["launch"]["pre_installs"] > 0
    L, tx = wall[0]["launch"], report["texts"]
    line = "🧪 %d test installs before launch (16 Jun) hidden · Show" % L["pre_installs"]
    assert line in tx["detail|Demo Wallpapers|all|30|cp|false"]
    assert not any("hidden · Show" in v for k, v in tx.items()
                   if "Wallpapers" not in k and k not in ("no_verdict_young_launch", "maybe_test"))
    for k in ("detail|Demo Wallpapers|all|30|cp|false", "detail|Demo Wallpapers|all|90|all|true"):
        assert "· test" not in tx[k] and "Since launch (16 Jun):" in tx[k]              # hidden by default
    for m in ("cp", "all"):
        t = tx["pre|Demo Wallpapers|" + m]
        assert "test installs before launch (16 Jun) shown · Hide" in t and "🧪 Test installs (before launch 16 Jun)" in t
        assert "installs · test" in t and "── 2025 ──" in t and "── 2026 ──" in t        # the test weeks + their year
        assert "0 installs · test" not in t                                               # an empty test week: not a row
        assert "Since GA4 start (20 Aug 2025):" in t and "20 Aug 2025–23 Sep 2026 · 400d" in t
        assert "(incl. test installs before launch 16 Jun 2026)" in t                      # next to a 2025 date: its year
    assert "(launch 16 Jun se; usse pehle ke test installs nahi)" in tx["detail|Demo Wallpapers|all|30|cp|false"]
    # more than a trickle a day before the launch: only "maybe test" (could be early real users)
    m = tx["maybe_test"]
    assert "%d installs (maybe test) before launch (16 Jun) hidden · Show" % L["pre_installs"] in m
    assert "🧪 Installs (maybe test) (before launch 16 Jun)" in m and "installs · maybe test" in m


def test_every_date_says_its_year_when_it_is_not_obvious(report):
    tx = report["texts"]
    cal = tx["detail|Demo Caller – Test App|all|30|cp|false"]
    assert "All time = 27 Jan–16 Sep 2026 ke saare pakke installs" in cal                # 8 months back: the year
    assert "── 2026 ──" in tx["detail|Demo Caller – Test App|all|90|all|true"]         # the triangle's year rows
    assert "Installs 16–22 Sep" in cal                                                   # this month: plain
    wal = tx["pre|Demo Wallpapers|all"]                                                  # across a year: both years
    assert "All time = 20 Aug 2025–16 Sep 2026 ke saare pakke installs" in wal and "20 Aug 2025–23 Sep 2026 · 400d" in wal
    assert "2025–16 Sep ke" not in wal and "2025–23 Sep ·" not in wal
    assert "29 Dec 2025–4 Jan" in wal                  # a triangle week under its "── 2026 ──" row: the short form


def test_old_install_changes_are_info_in_a_collapsed_list_never_counted(report, fixture):
    tx, glance = report["texts"], report["xp"]["glance"]
    olds = [(a["app"], o) for a in fixture["asset"]["apps"] for o in a["old_changes"]]
    assert olds and all(o["checkpoint"] == "D180" for _, o in olds)
    n_open = len(fixture["dashboard_uninstall"]["alerts"])
    assert report["plain_what_changed"] == str(n_open)                                   # not counted in "What changed?"
    assert "▸ Older changes (%d) Show" % len(olds) in tx["portfolio_30d"] and "Mar 2026" not in glance
    cal_closed = tx["detail|Demo Caller – Test App|all|30|cp|false"]
    assert "▸ Older changes (1) Show" in cal_closed and "Installs 14–20 Mar 2026" not in cal_closed
    assert "Closed alerts" not in cal_closed                                # none closed: no such list
    cal_open = tx["detail|Demo Caller – Test App|all|90|all|true"]
    # March installs are compared with the 4 weeks before THEM — "pichhle 4 hafte" would read as the last 4 weeks
    assert ("Info 180 din ke andar 58% ne hataya — usse pehle ke 4 hafte (14 Feb–13 Mar 2026) me 52% "
            "Installs 14–20 Mar 2026") in cal_open
    assert "▸ Older changes (1) Hide" in cal_open and "60 din se purane installs ke badlaav — sirf jaankari" in cal_open
    # the full table's 180-day row: the same change — "Old installs", never "Normal" next to its arrow
    assert re.search(r"180 days .*? ▲ \+6 pts 14–20 Mar 2026 ℹ️ Old installs 210 days", cal_open)


def test_what_changed_rows_carry_severity_dates_tags_and_open(report, fixture):
    p = report["texts"]["portfolio_30d"]
    ic = r"(?:[A-Z?] )?"                                     # the app icon (its letter when no image) before the name
    # one row per open alert: severity pill · app · plain line · dates · Provisional / New · Open →
    assert re.search(r"Worse " + ic + r"Demo Caller – Test App \d+ din ke andar [\d.]+% ne hataya, normal [\d.]+% — "
                     r"[^—]*? se zyada Installs 16–22 Sep Provisional Open →", p)
    assert re.search(r"Worse " + ic + r"Demo Launcher Ek din me achanak zyada uninstall — [^→]*? 23 Sep Provisional New Open →", p)
    assert re.search(r"Watch " + ic + r"Demo Wallpapers Ek bhi uninstall record nahi hua — GA4 / Firebase tracking check karo "
                     r"14 Sep New Open →", p)
    assert re.search(r"Worse " + ic + r"Demo Weather Roz ka uninstall dheere dheere badh raha — har 1,000 active users me [\d.]+ → [\d.]+ "
                     r"\(\+\d+%\) Since 12 Sep Provisional Open →", p)
    assert re.search(r"Better " + ic + r"Demo Flashlight Install ke din hi [\d.]+% ne hataya, normal [\d.]+% — [^—]*? se kam "
                     r"Installs 8–14 Sep Open →", p)
    assert p.count("Open →") == len(fixture["dashboard_uninstall"]["alerts"])        # old changes: collapsed
    # an app's own rows: no app, the same pill / dates / tags, and Open → (to its table or chart)
    cal = report["texts"]["detail|Demo Caller – Test App|all|30|cp|false"]
    assert re.search(r"What changed\? \(2\) Worse \d+ din ke andar [^→]*? Installs 16–22 Sep Provisional Open →", cal)   # + v3.2's HALT


def test_the_header_never_says_all_apps_over_one_apps_detail(report):
    h = report["header2"]
    # "All apps" picked in the header (here, or on another tab): the detail closes — the portfolio is shown
    assert h["all"]["app"] == "" and h["all"]["uniapp"] == "" and h["all"]["sel"] == '<option value="">All apps (0)</option>'
    assert h["all"]["screen"].startswith('<h2 class="sc">Uninstall</h2><p class="scd">')
    # another app picked: that app's detail; then "All apps": the portfolio (never the first app's detail again)
    assert h["other"]["app"] == h["B"] and h["other"]["uniapp"] == "" and "backlnk" in h["other"]["screen"]
    assert h["back"]["app"] == "" and h["back"]["screen"].startswith('<h2 class="sc">Uninstall</h2><p class="scd">')
    assert h["stale"]["screen"].startswith('<h2 class="sc">Uninstall</h2><p class="scd">')   # an old saved view


def test_overview_says_an_uninstall_only_app_has_no_admob_data(report):
    t = report["texts"]["overview_no_admob"]
    assert "Is app ka AdMob (kamai) data nahi — iska sirf GA4 uninstall data hai." in t and "Saari apps dikhao" in t
    assert "placements" not in t


def test_every_every_day_page_names_the_4_weeks_and_no_page_is_only_test_installs(report):
    t = report["texts"]["tripage1_caller"]
    assert "4-week average 17 Aug–13 Sep ke installs abhi itne din tak nahi pahunche" in t
    assert "Abhi 4 pakke hafte nahi" not in t
    p = report["pages"]
    assert p["hid"] == p["want_hid"] < p["all"] == p["want_all"]            # test installs hidden: fewer pages …
    assert p["last_col"] == p["reach"]                                       # … ending at the day the launch reached


def test_no_verdict_for_a_young_app_blames_its_age_not_the_data(report):
    t = report["texts"]["no_verdict_young_launch"]
    assert "ℹ️ Not enough data" in t and "Pichhle mahine se tulna ~2 mahine ke data ke baad" in t and "adhoora/gayab" not in t


def test_app_updates_are_a_line_right_above_the_install_week_they_fell_in(report):
    r, tx = report["rel"], report["texts"]
    # every app × both modes × test weeks hidden / shown × 12 / all rows (+ made-up updates): each 📦 line is right
    # above the week its update(s) fell in, that week alone has the 📦 badge, the legend only comes with a line
    assert r["bad"] == [] and r["checked"] >= 1000 and r["lines"] >= 20
    legend = "📦 = new update. Line ke upar wale hafte = naye version ke installs, neeche = purane version ke."
    for m in ("cp", "all"):                                  # the fixture's own updates (the engine's releases)
        cal, wea, lau, fla = (tx["rel|%s|%s|false|false" % (a, m)] for a in
                              ("Demo Caller – Test App", "Demo Weather", "Demo Launcher", "Demo QR Scanner"))
        assert "📦 New update v3.2 — 10 Sep (mid-week) 7–13 Sep 📦 " in cal and legend in cal
        assert re.search(r"14–20 Sep [^📦–]* 📦 New update v3\.2", cal)                   # between 14–20 and 7–13 Sep
        assert re.search(r"20–26 Jul [^📦–]* 📦 New update v4\.1 — 15 Jul \(mid-week\) 13–19 Jul 📦 ", wea)
        assert "📦 New update — 5 Aug (sudden jump in users updating) 3–9 Aug 📦 " in lau and legend in lau
        assert "📦" not in fla                                                             # no update: no line, no legend
        assert r["tips"]["Demo Caller – Test App|%s|false|false" % m] == ["New update v3.2 this week — 10 Sep"]
        assert r["tips"]["Demo Launcher|%s|false|false" % m] == [
            "New update this week — 5 Aug (sudden jump in users updating)"]
        # several in one week: ONE line naming them all (a version already called "v…" is not "vv…")
        two = tx["rel|two|" + m]
        assert "📦 3 updates: v3.2 (8 Sep), update (11 Sep), v3.2.1 (12 Sep) 7–13 Sep 📦 " in two
        assert two.count("updates:") == 1 and "vv" not in two
        assert r["tips"]["two|" + m] == ["3 updates this week: v3.2 (8 Sep), update (11 Sep), v3.2.1 (12 Sep)"]
        # in the newest (partial) week: under the year row, above that week, first thing after the 4-week row
        assert re.search(r"4-week average .*? ── 2026 ── 📦 New update v3\.3 — 22 Sep \(mid-week\) "
                         r"21–23 Sep \(only 3 days\) 📦 [\d.k]+ installs", tx["rel|newest|" + m])
        assert "📦" not in tx["rel|none|" + m]
        # among the test installs before the launch: only while those are shown, with its year, under its year row
        assert "📦" not in tx["rel|test|%s|false" % m]
        assert "── 2025 ── 📦 New update v1.1 — 24 Dec 2025 (mid-week) 22–28 Dec 📦 " in tx[
            "rel|test|%s|true" % m] and legend in tx["rel|test|%s|true" % m]
        # the week the launch cuts in two: the launch day's update above the first launched week, the last test
        # week's only while the test installs are shown
        launch = ["New update v1.0 this week — 16 Jun"]
        assert r["tips"]["launch|%s|false" % m] == launch
        assert r["tips"]["launch|%s|true" % m] == launch + ["New update v0.9 this week — 14 Jun"]
    # "Every day" page 2 (days 31–61: the same weeks) keeps every 📦 line
    for pre in ("false", "true"):
        assert r["pages"]["Demo Caller – Test App|all|%s|page2" % pre] == 1
        assert r["tips"]["Demo Caller – Test App|all|%s|page2" % pre] == ["New update v3.2 this week — 10 Sep"]
        assert r["tips"]["Demo Weather|all|%s|page2" % pre] == ["New update v4.1 this week — 15 Jul"]


# ── 📦 Update impact: the owner's verify gate ──────────────────────────────────────────────────────

IMPACT_ROWS = ["returning_dau", "new_d1", "new_d7", "sessions", "time", "arpdau", "uninstall_d0"]
IMPACT_LABELS = ["Returning DAU", "New users back next day (D1)", "New users back after 7 days (D7)", "Sessions per user",
                 "Time per user", "Ad revenue per user", "Uninstall on install day"]
IMPACT_HEADER = re.compile(r"📦 (v\S+( → v\S+)?|App update) — \d{1,2} [A-Z][a-z]{2}( \d{4})? · Verdict: "
                           r"(✅ WIN|👍 CONTINUE|⚠️ HOLD|🛑 HALT|⏳ Too early)")


def test_every_update_block_shows_the_four_must_haves_the_install_day_row_the_version_table_and_a_verdict(report, fixture):
    # the gate: each block of every app, rendered open, has EXACTLY the 7 rows (in the owner's order, English labels) +
    # the 2 version rows + the verdict header + "Why:" — deleting any row from the page fails here
    im = report["impact"]
    want = [(a["app"], b["key"], b) for a in fixture["asset"]["apps"] for b in (a.get("impact") or {}).get("updates", [])]
    assert len(want) >= 5 and [(b["app"], b["key"]) for b in im["blocks"]] == [(a, k) for a, k, _ in want]
    kinds = set()
    for blk, (_, _, b) in zip(im["blocks"], want):
        assert blk["n_open"] == 1 and blk["open_key"] == b["key"], blk["key"]
        assert blk["rows"] == IMPACT_ROWS and blk["vrows"] == ["ver_sessions", "ver_time"], blk["key"]
        assert blk["labels"] == IMPACT_LABELS + ["Sessions per user", "Time per user"], blk["key"]
        assert IMPACT_HEADER.search(blk["header"]), blk["header"]
        assert blk["heads"][0] == "Metric" and blk["heads"][1] == "Before (7 days)" and blk["heads"][3:5] == ["Change", "Status"]
        assert re.match(r"^After \((7 days|\d of 7 days)\)$", blk["heads"][2]), blk["heads"]
        assert blk["heads"][5:] == ["Metric", "Older versions", b["versions_cmp"]["new_label"] or "New version", "Difference", "Status"]
        assert blk["why"] and len(blk["statuses"]) == 9                # every row has its status pill
        kinds.add((b["kind"], b["verdict"]["level"]))
    assert {lv for _, lv in kinds} == {"halt", "hold", "continue", "win", None} and ("update", "continue") in kinds


def test_every_update_line_in_the_install_week_table_opens_its_block(report):
    im = report["impact"]
    assert im["jumps"] and all(j["open"] == j["want"] and j["rendered"] == j["want"] for j in im["jumps"]), im["jumps"]
    assert im["tri_keys"] and all(t["found"] for t in im["tri_keys"])
    f = im["folded"]                                           # an older (folded) block: unfolded and opened
    assert f["shut_fold"] and not f["shut_has"] and f["all"] and f["open"] == f["want"]
    # from the Alerts screen / Recent updates with the header's App already that app: the page ends ON the block
    j = im["jump_scroll"]
    assert j["open"] == j["k"] and j["pending"] == "" and j["calls"] and j["calls"][-1] == {"top": 1843, "behavior": "smooth"}
    assert {"top": 0} not in j["calls"]


def test_recent_updates_count_every_verdict_and_each_chip_shows_only_its_updates(report, fixture):
    counts = fixture["dashboard_uninstall"]["impact_counts"]
    p = report["impact"]["portfolio"]
    labels = {"halt": "🛑 HALT", "hold": "⚠️ HOLD", "continue": "👍 CONTINUE", "win": "✅ WIN", "pending": "⏳ Too early"}
    assert {k: v["n"] for k, v in p[""]["chips"].items()} == counts
    assert {k: v["label"] for k, v in p[""]["chips"].items()} == labels
    assert sorted(p[""]["rows"]) == sorted(k for k, n in counts.items() for _ in range(n)) and p[""]["on"] == []
    for k, n in counts.items():
        assert p[k]["rows"] == [k] * n and p[k]["on"] == [k], k
    assert "No app updates" not in p[""]["text"] and "updated" in p[""]["text"]


def test_update_alerts_on_the_alerts_screen_open_their_update(report, fixture):
    cards = report["alert_cards"]
    al = [a for a in fixture["dashboard_uninstall"]["alerts"] if a["family"] == "impact"]
    late = [a for a in fixture["dashboard_uninstall"]["alerts"] if a["family"] == "impact_late"]   # ⏰ (SPEC_WINDOWS §5)
    assert {a["level"] for a in al} == {"halt", "hold", "win"}
    for a in al:
        assert "📦 Update impact — " + a["release"]["label"] in cards
        assert "uniImpGo('%s','%s')" % (a["app_id"], a["release"]["key"]) in cards
    for a in late:
        assert "⏰ Late update impact — " + a["release"]["label"] in cards
        assert "uniImpGo('%s','%s','uni',30)" % (a["app_id"], a["release"]["key"]) in cards
    assert cards.count(">Update detail →</span>") == len(al) + len(late)


def test_update_cards_say_what_their_numbers_are_and_never_hide_a_failure(report):
    im = report["impact"]
    cal = next(b for b in im["blocks"] if b["key"] == "ver:3.2@2026-09-10")["html"]
    # D1 / D7 tooltips: n = install DAYS (+ the installs of those days), never "7 installs"
    assert 'title="Installs 13–19 Sep · 7 install din · 35.0k installs"' in cal and " · 7 installs\"" not in cal
    assert 'title="Installs 3–9 Sep · 7 install din"' in cal and 'title=" · ' not in cal
    # a pending row: the calendar day it is ready (GA4 data of 25 Sep arrives ~2 days later), the data day in its tooltip
    assert re.search(r'<span title="GA4 ka data 25 Sep tak aane par \(data ~2 din der se aata hai\)">ready ~27 Sep</span>', cal)
    # no earlier updates: the version table claims no "usual gap" correction
    assert "usual early-updater gap not known yet" in cal and "after the usual early-updater gap" not in cal
    assert "aam farak abhi pata nahi" in cal and "aam farak 0 pichhle" not in cal
    # the alert pill: open (What changed?), not claimed "sent"; the adoption pill: the After week's newest day
    assert 'title="Is update ka alert khula hai — What changed? me dekho">🔔 Alert' in cal and "bheja gaya" not in cal
    assert re.search(r'title="After hafte ke sabse naye din \(\d+ [A-Z][a-z]{2}\) tak kitne active users naye version pe', cal)
    # the change a row was judged on is the MAIN number (SPEC_WINDOWS §5): ARPDAU "Ads/user … vs expected", its plain
    # revenue change under it with eCPM (the market's); the old "net of the usual trend" / "(judged)" sub-lines are gone
    assert re.search(r">Ads/user [−+]?[\d.]+% vs expected</span>", cal)
    assert re.search(r">kamai/user [−+]?[\d.]+%? seedha \(eCPM [−+]?[\d.]+%? — market\)</div>", cal)
    assert "net of the usual trend" not in cal and "(judged)" not in cal
    n = im["never"]
    assert '⏳ Too early' in n["h"] and 'title="Agla update bahut jaldi aa gaya"' in n["h"] and ">No verdict</span>" in n["h"]
    assert ">No verdict</span>" in n["p"]
    assert im["upd_throw"]


def test_rows_nobody_judged_show_only_the_plain_change_and_no_headline_comes_from_them(report):
    # Low data / No data / Pending rows: never a model number (vs expected, net of the trend, "(judged)") — the plain
    # Before → After "vs before", or —; the folded line and the Recent updates list: a change only from a Worse / Better
    # row, else "No clear change" (a verdict) or nothing (too early)
    im = report["impact"]
    d = im["display"]
    assert d["rows"] == 7 * len(im["blocks"]) and d["bad"] == [] and d["mini_bad"] == []
    assert d["vs_before"] >= 1 and d["vs_expected"] >= 1                     # the fixture has both kinds
    heads = d["heads"]
    # (+ the late-effect apps' updates of the last 60 days, SPEC_WINDOWS §6: Late Drop's v2.0 / v2.1 continue, Late
    # Told's v3.1 holds on D1)
    assert len(heads) == 8
    for h in heads:
        # (a row with a ⏰ late chip says its headline is the 7 days': "7 days: …" — review 2026-09-28)
        pre = "7 days: " if h["late"] else ""
        if h["head_row"] is None:
            assert h["hl"] == (None if h["lv"] == "pending" else pre + "No clear change"), h
        else:
            assert h["head_status"] in ("worse", "better") and h["hl"] and h["hl"].startswith(pre), h
            assert h["hl"] != pre + "No clear change", h
    assert sorted(h["hl"] for h in heads if h["lv"] == "continue") == ["7 days: No clear change"] + ["No clear change"] * 2
    assert [h["late"] for h in heads].count(True) == 1                       # Late Drop v2.0 (its late HOLD)
    # a young app that grew fast before its update (synthetic): Low data rows with a model level beside them
    s = d["synth"]
    assert "1,200 1,300 +8.3% vs before Low data Update se pehle app tez badh raha tha (~×6.7/hafta)" in s["dau"]
    assert "vs expected" not in s["dau"] and "9,000" not in s["dau"] and "−86%" not in s["dau"]
    assert "+5% vs before" in s["arp"] and "(judged)" not in s["arp"] and "+310%" not in s["arp"]
    assert "impressions/user +40% · eCPM −30%" in s["arp"]                   # plain Before → After: still said
    assert "+10% vs before" in s["ses"] and "net of the usual trend" not in s["ses"] and "−60%" not in s["ses"]
    assert s["mini"].startswith("No clear change · Returning DAU low data · ") and "Ad revenue/user low data" in s["mini"]
    assert "%" not in s["mini"] and "pts" not in s["mini"]
    assert s["upd"].count("No clear change") == 2 and "−86%" not in s["upd"]  # a stale head on a Low data row: dropped
    assert 'Normal trend : update se pehle koi number hafte me ×1.35 se tez badh / ghat raha ho' in im["how"]


def test_a_worse_or_better_row_is_headlined_by_what_it_was_judged_on_never_a_number_pointing_the_other_way(report):
    # the headline (Recent updates) and the folded line: the change a Worse / Better row was JUDGED on, named so —
    # Returning DAU "vs expected", sessions / time "vs expected" (net of the trend), ad revenue on "Ads/user" (a HALT on ads/user −35%
    # while revenue/user rose +120% on eCPM never reads as a red "+120%"); the open row: a plain change whose sign
    # contradicts the status is not coloured, the judged number under it is. A block nothing could measure: "Not
    # enough data yet", never "No clear change"
    d = report["impact"]["display"]
    hl = sorted(h["hl"] for h in d["heads"] if h["head_row"])
    assert hl == ["Ads/user −7.8%", "D1 return +6 pts", "D1 return −2.5 pts", "Returning DAU −9.8% vs expected"], hl
    c = d["contra"]
    assert '<span class="down">Ads/user −35%</span>' in c["mini"] and "+120%" not in c["mini"]
    # (SPEC_WINDOWS §5: the open row says "−8% vs expected" — the folded line uses the same word, not "net of trend")
    assert '<span class="down">Sessions/user −8% vs expected</span>' in c["mini"] and "+3%" not in c["mini"]
    assert "Ads/user −35%" in c["upd"] and "+120%" not in c["upd"] and "No clear change" not in c["upd"]
    assert '<span class="hl down">Ads/user −35%</span>' in c["upd_html"]
    # the open rows (SPEC_WINDOWS §5): the judged "Ads/user −35%" / "−8% vs expected" is the main number, red; the plain
    # "kamai/user +120% seedha" / "seedha: +3% vs before" under it, never coloured
    assert '<span style="font-weight:700;color:var(--bad)">Ads/user −35% vs expected</span>' in c["arp_cell"], c["arp_cell"]
    assert re.search(r'<div class="s"[^>]*>kamai/user \+120% seedha \(eCPM \+210% — market\)</div>', c["arp_cell"]), c["arp_cell"]
    assert '<span style="font-weight:700;color:var(--bad)">−8% vs expected</span>' in c["ses_cell"], c["ses_cell"]
    assert re.search(r'<div class="s"[^>]*>seedha: \+3% vs before</div>', c["ses_cell"]), c["ses_cell"]
    assert "color:" not in c["arp_cell"].split("</span>", 1)[1].split('<td class="st">')[0]   # nothing under the main number is coloured
    assert "color:" not in c["ses_cell"].split("</span>", 1)[1].split('<td class="st">')[0]
    # nothing measured
    assert c["nd_mini"].startswith("Not enough data yet · Returning DAU low data · ") and "No clear change" not in c["nd_mini"]
    assert "Not enough data yet" in c["nd_upd"] and "No clear change" not in c["nd_upd"]
    assert 'title="Abhi koi number parkha nahi ja saka (Low data / No data)">Not enough data yet</span>' in c["nd_html"]


# ── 📦 Before / after windows: 7 / 14 / 30 / 60 days (SPEC_WINDOWS §5) ─────────────────────────────────────────────
# Two sources: the fixture's own by_window (impact v2 — skipped, and said so, while the committed fixture is still v1)
# and made-up windows of the §4 contract's shape (tests/impact_win_synth.js) on a copy of an app — those always run.

SEG = ["7 days", "14 days", "30 days", "60 days"]
IMPACT_ROWS_30 = IMPACT_ROWS + ["new_d30"]
D30_LABEL = "New users back after 30 days (D30)"
LAG = 2


def _d(s):
    return date.fromisoformat(s)


def _v2(fixture):
    return any(b.get("by_window") for a in fixture["asset"]["apps"] for b in (a.get("impact") or {}).get("updates", []))


def _block(fixture, key):
    return next(b for a in fixture["asset"]["apps"] for b in (a.get("impact") or {}).get("updates", []) if b["key"] == key)


def _seg_on(seg, n):
    return [x["t"] for x in seg] == SEG and [x["on"] for x in seg] == [t == "%d days" % n for t in SEG] and not any(x["dis"] for x in seg)


def test_windows_every_fixture_block_at_7_14_30_60_has_its_rows_heads_verdict_and_selector(report, fixture):
    if not _v2(fixture):
        pytest.skip("the committed fixture has no by_window yet (impact v1): the made-up windows below cover the page")
    W = report["win"]
    assert W["src"] == "fixture"
    want = sorted((a["app"], b["key"]) for a in fixture["asset"]["apps"] for b in (a.get("impact") or {}).get("updates", []))
    assert sorted({(b["app"], b["key"]) for b in W["blocks"]}) == want and len(W["blocks"]) == 4 * len(want)
    for b in W["blocks"]:
        n, fb = b["n"], _block(fixture, b["key"])
        assert b["open"] and _seg_on(b["seg"], n), (b["key"], n, b["seg"])
        if n == 7:                                                    # the gate: today's block, byte for byte
            assert b["rows"] == IMPACT_ROWS and b["heads"][1] == "Before (7 days)" and b["vtable"] and not b["vnote"], b["key"]
            assert IMPACT_HEADER.search(b["header"]) and "Verdict (" not in b["header"], b["header"]
            continue
        w = fb["by_window"][str(n)]
        rows = IMPACT_ROWS if n == 14 else IMPACT_ROWS_30
        assert b["rows"] == rows and b["labels"][:len(rows)] == IMPACT_LABELS + ([D30_LABEL] if n >= 30 else []), (b["key"], n)
        a = w["after"]
        ah = "After (%d days)" % n if a["settled"] >= a["days"] else "After (%d of %d days)" % (a["settled"], a["days"])
        assert b["heads"][:5] == ["Metric", "Before (%d days)" % n, ah, "Change", "Status"], (b["key"], n, b["heads"])
        assert "· Verdict (%d days): " % n in b["header"] and b["vnote"] and not b["vtable"], (b["key"], n)
        if w["state"] == "running":                                   # every row waits (or can never have data); the Why says when
            assert set(b["statuses"]) <= {"pending", "na"}, (b["key"], n, b["statuses"])
            jd = _d(a["judged_on"]) + timedelta(days=LAG)
            if "pending" in b["statuses"]:
                assert b["why"].startswith("Why: %d din poore ~%s ko · faisla ~%s ko" % (n, day_txt(a["to"]), day_txt(jd.isoformat()))), b["why"]
            else:                                                     # nothing to wait for: the engine's reason, no date promised
                assert "faisla ~" not in b["why"] and b["why"] == "Why: " + w["verdict"]["why"], b["why"]
        if w.get("mixed"):
            k = len(w["mixed"])
            assert b["mixed_pill"][1] == "Mixed · +%d %s in this window" % (k, "update" if k == 1 else "updates"), b["mixed_pill"]
            assert all(m["label"] in b["mixed_pill"][0] for m in w["mixed"]), b["mixed_pill"]
        if b["late_lv"]:
            assert b["late_chip"][0] == "event.stopPropagation();uniImp('%s','uni',30)" % b["key"], b["late_chip"]


def test_windows_fixture_late_alerts_chips_and_what_changed_open_the_block_at_30(report, fixture):
    if not _v2(fixture):
        pytest.skip("the committed fixture has no by_window / impact_late yet (impact v1): the made-up late family below covers the page")
    W = report["win"]
    late = [a for a in fixture["dashboard_uninstall"]["alerts"] if a["family"] == "impact_late"]
    assert late, "a v2 fixture carries a sent late alert (SPEC_WINDOWS §6 Demo Late Drop)"
    assert sorted(map(tuple, W["chg_late"])) == sorted((a["app_id"], a["release"]["key"]) for a in late)
    for a in late:
        assert [a["app_id"], a["release"]["key"]] in W["chg_late_app"], a["release"]
    ups = [(s["app_id"], u["key"]) for s in fixture["dashboard_uninstall"]["apps"] for u in s.get("updates") or [] if u.get("late")]
    assert ups and sorted((x[0], x[1]) for x in W["upd_late"]) == sorted(ups)
    assert all(x[2] in ("⏰ 30 days: ⚠️ HOLD", "⏰ 30 days: 🛑 HALT") for x in W["upd_late"])


def test_windows_card_default_a_blocks_own_choice_and_the_viewers_memory(report):
    c = report["win"]["syn"]["card"]
    assert c["nblocks"] == 2 and _seg_on(c["card_seg"], 7)
    assert c["first"] == ["", ""]                                         # nothing chosen: 7
    assert c["w30"] == [" (30 days)", " (30 days)"] and c["win"] == 30 and c["saved"] == [["imp_win_uni", "30"]]
    assert c["over"] == [" (30 days)", " (60 days)"] and c["again"] == c["over"] and c["wk"] == {c["k1"]: 60}   # survives a re-render
    assert c["w14"] == [" (14 days)", " (14 days)"] and c["wk2"] == {}   # a new card default clears the block's own choice
    assert c["act_win"] in (None, "unread")                              # the Active tab's copy keeps its own
    assert _seg_on(c["open30_seg"], 30) and c["open30_blk"] == IMPACT_ROWS_30
    s = report["win"]["syn"]["store"]
    assert s["remembered"] == [" (30 days)", " (30 days)"] and s["rwin"] == 30
    assert s["blocked"] == ["", ""] and s["bwin"] is None and _seg_on(s["bseg"], 7)   # storage that throws: 7, no crash
    assert s["blocked60"] == [" (60 days)", " (60 days)"]
    assert s["dflt"] == [" (30 days)", ""] and s["dflt7"] == ["", ""]     # default_window 30 unless the viewer chose


def test_windows_an_asset_without_them_disables_14_30_60_and_a_build_with_them_off_hides_the_selector(report):
    v = report["win"]["syn"]["v1"]
    for seg in (v["off_seg"], v["off_blk_seg"], v["fail_seg"]):
        assert [x["t"] for x in seg] == SEG and seg[0]["on"] and not seg[0]["dis"]
        assert all(x["dis"] and x["tip"] == "Agle robot run ke baad" for x in seg[1:]), seg
    assert v["after_hdr"] == ["", ""] and v["hid_has"] is False


def test_windows_actual_and_expected_label_every_model_number_and_only_on_judged_rows(report):
    im, V = report["impact"], report["win"]["syn"]["views"]
    cal = next(b for b in im["blocks"] if b["key"] == "ver:3.2@2026-09-10")["html"]
    dau = cal.split('<tr data-row="returning_dau">')[1].split("</tr>")[0]
    assert "Actual: <b>115,561</b>" in dau and "Expected (bina update ke): 128,145</div>" in dau and ">−9.8% vs expected</span>" in dau
    assert re.search(r'title="Update na aata to kitna hota — model ka andaza [^"]*Ye \'data aana baaki\' nahi hai — asli number upar hai"', dau)
    assert not any(re.search(r">expected [\d,]", h) for h in [b["html"] for b in im["blocks"]] + [v["h"] for v in V.values() if isinstance(v, dict) and "h" in v])
    c7 = V["7"]["cells"]
    assert "Actual: <b>2.40</b>" in c7["sessions"]["after"] and "Expected (bina update ke): 2.40" in c7["sessions"]["after"]
    assert "vs expected</span>" in c7["sessions"]["change"]
    assert "Ads/user: 4.4 · expected (bina update ke) 4.4</div>" in c7["arpdau"]["after"] and "Actual: <b>$" in c7["arpdau"]["after"]
    assert ">Ads/user −0.1% vs expected</span>" in c7["arpdau"]["change"]
    for n in ("14", "30"):                                                # per-user rows at 14 / 30: plain, no model number
        for k in ("sessions", "time", "arpdau"):
            cc = V[n]["cells"][k]
            assert "xpected" not in cc["after"] and "Actual:" not in cc["after"], (n, k)
            assert re.search(r"vs before</span>", cc["change"]) and "vs expected" not in cc["change"], (n, k)
        assert "Actual: <b>" in V[n]["cells"]["returning_dau"]["after"]  # DAU keeps its expected level (3 weeks of trend)
    y = V["young"]["cells"]["returning_dau"]                              # a Low data DAU row: its number alone
    assert "Actual:" not in y["after"] and "xpected" not in y["after"] and "vs expected" not in y["change"] and ">5,765<" in y["after"]
    assert "1,200 1,300 +8.3% vs before Low data" in report["impact"]["display"]["synth"]["dau"]


def test_windows_change_cell_main_number_is_the_judged_one_with_what_pakka_needs_and_plain_lines_never_coloured(report):
    V = report["win"]["syn"]["views"]
    d30 = V["30"]["cells"]["returning_dau"]["change"]
    assert '<span style="font-weight:700">−3% vs expected</span>' in d30 and ">seedha: −2% vs before</div>" in d30
    assert re.search(r'<div class="s uni-need" title="Bina update ke bhi 30-din tulna aam taur pe ±25% hil jaata hai \(update se pehle ke hafton me yahi tulna karke napa\) — pakka tabhi jab farak isse ~3 guna ho">pakka: ≥ −52%</div>', d30), d30
    assert "pakka: ≥ +7.4 pts" in V["30"]["cells"]["new_d1"]["change"] and "±2.5 pts" in V["30"]["cells"]["new_d1"]["change"]
    for n in ("7", "14", "30"):
        for k, cc in V[n]["cells"].items():
            subs = cc["change"].split("</span>", 1)[1] if "</span>" in cc["change"] else ""
            assert "color:" not in subs, (n, k)                             # only the main number is coloured
            assert "aam ±" not in cc["change"], (n, k)
            if n != "7" and k in ("sessions", "time"):
                assert "seedha" not in cc["change"], (n, k)                # plain basis: one "vs before" number only
    assert "kamai/user −10% seedha (eCPM +2% — market)" in V["30"]["cells"]["arpdau"]["change"]


def test_windows_a_running_window_says_when_it_ends_and_when_its_verdict_comes(report, fixture):
    V = report["win"]["syn"]["views"]
    b = _block(fixture, V["k"])
    a0 = _d(b["windows"]["after"]["from"])
    end, jd = a0 + timedelta(days=59), a0 + timedelta(days=59 + 10 + LAG)
    v = V["60"]
    assert v["heads"][:3] == ["Metric", "Before (60 days)", "After (12 of 60 days)"] and "(12 of 60 days settled)" in v["text"]
    assert v["mini_text"] == "⏳ 60 din poore ~%s · faisla ~%s" % (day_txt(end.isoformat()), day_txt(jd.isoformat()))
    assert "Why: 60 din poore ~%s ko · faisla ~%s ko" % (day_txt(end.isoformat()), day_txt(jd.isoformat())) in v["text"]
    st = [c["status"] for c in v["cells"].values()]
    assert len(st) == 8 and all('data-st="pending"' in s for s in st)
    assert sum('<span title="60 din poore hone par faisla">ready ~%s</span>' % day_txt(jd.isoformat()) in s for s in st) == 7   # D30: its own day
    assert "Verdict (60 days): ⏳ Too early" in v["header"]
    nv = V["never"]                                                   # no row can ever fill: the engine's why, no date promised
    assert "faisla ~" not in nv["h"] and "faisla ~" not in nv["mini"] and "din poore ~" not in nv["mini"]
    assert "<b>Why:</b> Update app launch ke 60 din ke andar aaya — pehle ke poore 60 din nahi</div>" in nv["h"]
    assert 'title="Update app launch ke 60 din ke andar aaya — pehle ke poore 60 din nahi">⏳ Too early</span>' in nv["mini"]
    assert "Early" in V["30"]["header"] and 'title="D30 abhi baaki — faisla badal sakta hai">Early</span>' in V["30"]["h"]


def test_windows_mixed_told_and_the_version_table(report):
    V = report["win"]["syn"]["views"]
    assert re.search(r'<span class="pill p-b uni-mixed" title="Is 30-din window me ye updates bhi aaye: v1\.3 \(19 Sep\) — farak in sabka mila-jula ho sakta hai">Mixed · \+1 update in this window</span>', V["30"]["h"])
    for n in ("14", "30", "60"):
        assert "Naya vs purana version: sirf 7-din window me (baad me naye updates aa jaate hain)" in V[n]["h"]
        assert "Same days: new version vs old versions" not in V[n]["h"]
    assert "Same days: new version vs old versions" in V["7"]["h"] and "sirf 7-din window me" not in V["7"]["h"]
    t = report["win"]["syn"]["views"]["told"]
    assert "7 din ke faisle me pehle hi dikha</div>" in t["arpdau"]["status"]                  # its own 7-day HOLD
    assert "7 din ke faisle me pehle hi dikha (v1.3)</div>" in t["new_d1"]["status"]         # an update inside the window
    tb = report["win"]["syn"]["views"]["told_by"]                                             # the engine's told_by names it
    assert "7 din ke faisle me pehle hi dikha (v9.9)</div>" in tb["new_d1"]["status"] and "pehle hi dikha</div>" in tb["arpdau"]["status"]
    y = V["young"]["h"]                                                   # the app's short history: said once
    assert "30-din tulna ke liye update se pehle ~26 hafte ka data chahiye — is app ke paas ~20 hafte ka tha; isliye kai rows 'Low data'" in y


def test_windows_late_chip_alert_card_what_changed_and_recent_updates_open_the_block_at_30(report):
    S = report["win"]["syn"]
    V, k = S["views"], S["views"]["k"]
    chip = "onclick=\"event.stopPropagation();uniImp('%s','uni',30)\">⏰ 30 days: " % k
    assert chip + "🛑 HALT</span>" in V["late_hdr"] and chip + "⚠️ HOLD</span>" in V["late_v30"]
    assert 'title="30 din baad naya nuksaan — 7 din me nahi dikha tha"' in V["late_hdr"]
    t = S["late_tap"]
    assert t["call"] == "event.stopPropagation();uniImp('%s','uni',30)" % t["want"] and t["chip"] == "⏰ 30 days: ⚠️ HOLD"
    assert t["open"] == t["want"] and t["wk"] == {t["want"]: 30} and t["hdr"] == "Verdict (30 days):"
    L = S["late_al"]
    go = "uniImpGo('%s','%s','uni',30)" % (L["app_id"], L["key"])
    assert "⏰ Late update impact — " + L["label"] in L["card"] and ('onclick="%s">Update detail →' % go) in L["card"]
    assert "💡 30 din baad naya nuksaan — agla rollout roko, jaanch karo." in L["card"]
    assert ('onclick="%s"' % go) in L["row_all"] and ("onclick=\"uniImp('%s','uni',30)\"" % L["key"]) in L["row_app"]
    assert L["when"] == "Update %s · %s · 30 din baad" % (L["label"], L["date"]) and L["sev"] == ["Worse", "p-r"]
    assert L["upd"].count("uni-late") == 1 and ("onclick=\"event.stopPropagation();%s\">⏰ 30 days: ⚠️ HOLD</span>" % go) in L["upd"]


def test_windows_how_we_compare_says_actual_expected_windows_and_the_late_alert(report):
    h = report["win"]["syn"]["how"]
    for s in ("Actual = asli number (GA4 / AdMob se aa chuka). Expected (bina update ke) = agar update na aata to kitna hota (model ka andaza) — ye data aana baaki nahi hai.",
              "7 / 14 / 30 / 60 din : Before = release se pehle utne hi din",
              "pakka ke liye isse ~3 guna farak chahiye. Har row ke neeche pakka: ≥ X yahi batata hai.",
              "30 / 60 din ki tulna ke liye update se pehle ~6 / ~11 mahine ka data chahiye",
              "30 din pe naya nuksaan (jo 7 din me nahi dikha) ho to ⏰ Late alert — ek app ka ek hi, 2 din lagatar dikhne pe."):
        assert s in h["t7"], s
    assert "Before = update se pehle ke 7 din" in h["t7"] and "Before = update se pehle ke 30 din" in h["t30"]
    assert "~34 hafton me har din yahi 30-din Before / After tulna" in h["t30"]


def test_windows_selector_fits_one_line_at_375px():
    # the open block's 7 / 14 / 30 / 60 at 375 px: the card's inner width is ~310 px (17 px padding, no side padding on
    # the block); 4 buttons at 12.5 px / 600 (~0.6 em a character) + 9 px padding each side must fit, the label wraps above
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    assert ".uni-imp-seg{display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px;margin:6px 0 8px;font-size:11.5px;color:var(--muted)}" in html
    assert ".uni-imp-seg .seg button{padding:6px 9px}" in html
    assert sum(len(t) * 12.5 * 0.6 + 2 * 9 + 1 for t in SEG) <= 310


# ── review fixes (2026-09-28) ────────────────────────────────────────────────────────────────────────────────────────

def test_windows_a_7_day_halt_stays_in_sight_when_the_card_shows_30_days(report):
    # the card's remembered default 30 must never hide the 7-day verdict alerts come from (review: "⏳ Too early … 🔔
    # Alert" with no HALT anywhere) — judged or still running; a tap opens the block at 7; at 7 nothing is added
    f = report["win"]["syn"]["fix"]
    chip = ('<span class="pill p-r uni-v7" title="7 din ka faisla (alert isi se aata hai) — tap: 7 din dekho" '
            "onclick=\"event.stopPropagation();uniImp('%s','uni',7)\">7 days: 🛑 HALT</span>" % f["k"])
    for h in (f["halt30"], f["halt30run"], f["mix_closed"], f["nodata"]):
        assert "Verdict (30 days): " in h and chip in h, h
    assert 'data-lv="pending"' in f["halt30run"] and "⏳ Too early" in f["halt30run"]
    assert "uni-v7" not in f["halt7"] and "Verdict: <span class=\"pill p-r\" data-lv=\"halt\"" in f["halt7"]


def test_windows_a_folded_mixed_window_says_mila_jula_on_its_header_and_chip(report):
    f = report["win"]["syn"]["fix"]
    tip = "Is 30-din window me ye updates bhi aaye: v8.1 (1 Sep), v8.2 (8 Sep) — farak in sabka mila-jula ho sakta hai"
    assert '<span class="pill p-b uni-mixh" title="%s">Mixed +2</span>' % tip in f["mix_closed"]
    assert 'title="Koi pakka nuksaan nahi — rollout chalne do · mila-jula (beech me 2 aur updates)">👍 CONTINUE' in f["mix_closed"]
    assert "uni-mixh" not in f["mix_open_hdr"] and f["mix_open_meta"]                  # open: the meta line's pill
    assert "mila-jula (beech me 2 aur updates)" in f["mix_open_hdr"]


def test_windows_a_plain_per_user_row_shows_one_vs_before_number_the_one_it_was_judged_on(report):
    # sessions: pooled +4% vs the paired days' −6% it was judged on — the main (red) number is −6%, no second "vs
    # before"; ads/user judged plain (−6.5%): no pooled "impressions/user −2%" beside it
    f = report["win"]["syn"]["fix"]
    ses, arp = f["plain"]["sessions"], f["plain"]["arpdau"]
    assert '<span style="font-weight:700;color:var(--bad)">−6% vs before</span>' in ses["change"] and "+4%" not in ses["change"]
    assert "seedha" not in ses["change"]
    assert '<span style="font-weight:700;color:var(--bad)">Ads/user −6.5% vs before</span>' in arp["change"]
    assert "impressions/user" not in arp["after"] and "kamai/user −1% seedha (eCPM +1% — market)" in arp["change"]
    assert '<span class="down">Sessions/user −6% vs before</span>' in f["plain_mini"]
    assert '<span class="down">Ads/user −6.5% vs before</span>' in f["plain_mini"]


def test_windows_the_young_line_is_the_engines_own_reason_said_once_and_no_row_repeats_it(report):
    f, V = report["win"]["syn"]["fix"], report["win"]["syn"]["views"]
    # D30 alone short (its own 30 weeks): named, not "kai rows"; its pill tooltip keeps the reason, no sub-line
    assert f["young1_line"] == "30-din tulna ke liye update se pehle ~30 hafte ka data chahiye — is app ke paas ~27 hafte ka tha; isliye D30 return 'Low data'"
    d30 = f["young1_cells"]["new_d30"]["status"]
    assert 'data-st="low" title="Update se pehle ka ~30 hafte ka data chahiye' in d30 and '<div class="s">' not in d30
    # two rows with different needs (DAU ~26 weeks, D30 its own ~30): one line, neither row repeats its reason under
    # its pill (each keeps its own weeks in the pill's tooltip)
    assert f["young2_line"].endswith("isliye kai rows 'Low data'") and "~26 hafte" in f["young2_line"]
    for k, w in (("returning_dau", 26), ("new_d30", 30)):
        st = f["young2_cells"][k]["status"]
        assert 'title="Update se pehle ka ~%d hafte' % w in st and '<div class="s">' not in st, (k, st)
    for k in ("returning_dau", "uninstall_d0"):                           # two rows share it: "kai rows", said once
        st = V["young"]["cells"][k]["status"]
        assert 'title="Update se pehle ka ~26 hafte' in st and "hafte ka tha</div>" not in st, (k, st)
    assert V["young"]["h"].count("hafte ka tha") == 3                     # the line + the 2 pill tooltips


def test_windows_a_long_window_nobody_could_measure_reads_not_enough_data_never_continue(report):
    f = report["win"]["syn"]["fix"]
    h = f["nodata"]
    assert ('<span class="pill uni-pz" data-lv="nodata" title="%s">Not enough data</span>' % f["nodata_young_line"]) in h
    assert "👍 CONTINUE" not in h.split("uni-v7")[0]


def test_windows_one_failed_window_disables_only_its_button_and_the_dau_model_says_its_n_day_pairing(report):
    f, h = report["win"]["syn"]["fix"], report["win"]["syn"]["how"]
    seg = f["seg_fail"]
    assert [(x["t"], x["dis"]) for x in seg] == [("7 days", False), ("14 days", False), ("30 days", False), ("60 days", True)]
    assert seg[3]["tip"] == "Agle robot run ke baad"
    dau30, dau7 = f["dau30"], f["dau7"]
    assert "Before window ke usi weekday ka din (~30 din pehle) × normal hafta-dar-hafta badlaav (zyada se zyada 3 hafte aage)" in dau30["after"]
    assert "Expected = Before window ke usi weekday ka din (~30 din pehle)" in dau30["label"]
    assert "pichhle hafte ka same din × normal trend" in dau7["after"] and "Expected = pichhle hafte ka same din" in dau7["label"]
    assert "Expected = Before ke usi weekday ka din (~30 din pehle)" in h["t30"] and "30 din pe seedha pehle vs baad" in h["t30"]
    assert "Expected = pichhle hafte ka same din" in h["t7"] and "trend hata ke. Haal ke installs" in h["t7"]
    for t in (h["t7"], h["t30"]):                                         # the 8N swing measured on live data
        assert "(DAU ~±35–45%, ads/user ~±20–40%)" in t and "±25–37%" not in t


def test_recent_updates_a_late_chip_follows_the_7_day_headline_said_as_the_7_days(report):
    upd = report["win"]["syn"]["late_al"]["upd"]
    row = upd.split('<div class="uni-upd"')[1]
    assert '<span class="hl muted" title="Koi number pakka kharab / behtar nahi hua">7 days: No clear change</span>' in row
    assert row.index("7 days: No clear change") < row.index("uni-late")
    other = upd.split('<div class="uni-upd"')[2]                          # (no late chip: today's words)
    assert ">No clear change</span>" in other and "7 days:" not in other
