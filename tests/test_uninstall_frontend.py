"""The Uninstall tab's frontend (frontend/index.html), rendered for real: tests/uninstall_frontend.js runs the page's
own script in a node vm on the committed fixture (the real build's output) and renders every Uninstall state —
portfolio (every Period and sort), each app in every chart / table mode, the "Har din" pages, the App filter.
Checked here: it parses and renders without errors or "undefined"/"NaN", speaks plain Roman Hinglish (no
cumulative / checkpoint / cohort / bharosa / headline, no Devanagari), the "kitne bache" line never rises and
stays within 0–100%, the owner's texts are all there, and the summary sentences say exactly what the engine
computed. Skipped where node is not installed."""

import json
import math
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "uninstall_sample.json")
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


def day(N):
    return "usi din" if N == 0 else "1 din baad" if N == 1 else "%d din baad" % N


def day_txt(iso):
    """The page's date (uniD) for a day of the fixture's own recent months: "14 Sep"."""
    m = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return "%d %s" % (int(iso[8:]), m[int(iso[5:7]) - 1])


def test_every_uninstall_state_renders_without_errors(report):
    assert report["errors"] == [] and report["bad"] == []
    assert report["scenarios"] >= 70


def test_plain_roman_hinglish_only(report):
    assert report["jargon"] == [] and report["devanagari"] == []


def test_the_kitne_bache_line_starts_at_100_and_never_rises(report):
    c = report["charts"]
    assert c["count"] >= 30 and c["all_never_rise"] and c["all_within"] and c["all_start_100"]
    assert c["all_hover_both"]                                  # hover: "N% bache" and "us din M% gaye" together


def test_the_har_din_triangle_4_week_row_is_the_engines(report):
    assert report["avg4"]["bad"] == [] and report["avg4"]["checked"] >= 80


def test_the_owners_texts_are_all_there(report):
    assert {k: v for k, v in report["has"].items() if not v} == {}


def test_each_apps_summary_says_what_the_engine_computed(report, fixture):
    for a in fixture["asset"]["apps"]:
        sv = a["survival"]
        c, days = sv["all"], sv["key_days"]
        want = "100 naye users me se: " + " · ".join(
            "%s %s%s" % (day(N), per100(c["left"][N]), " bache" if j == 0 else "") for j, N in enumerate(days))
        assert report["summary"][a["app"]].startswith(want), a["app"]


def test_the_portfolio_pools_every_apps_curve_the_engines_way(report, fixture):
    curves = [a["survival"]["all"] for a in fixture["asset"]["apps"]]
    S, left = 1.0, []
    for N in range(91):
        X = sum(c["x"][N] for c in curves if N < len(c["x"]))
        R = sum(c["r"][N] for c in curves if N < len(c["r"]))
        S *= 1 - (min(1, X / R) if R > 0 else (1 if X > 0 else 0))
        left.append(S)
    want = "100 naye users me se (saari apps milakar): " + " · ".join(
        "%s %s%s" % (day(N), per100(left[N]), " bache" if j == 0 else "") for j, N in enumerate((1, 7, 30, 90)))
    assert report["pooled"] == want


def test_the_all_time_normal_row_is_the_apps_own_curve_and_never_goes_down(report):
    assert report["ref"]["bad"] == [] and report["ref"]["checked"] >= 80


def test_the_rate_line_never_says_normal_next_to_an_open_rate_alert(report):
    assert report["rate_bad"] == []


def test_an_open_install_alert_is_said_next_to_the_verdict_never_under_a_plain_green_tick(report, fixture):
    assert report["coh_bad"] == []
    # the portfolio's "jaisa" count leaves out every app with an open install alert, and apps whose shown numbers
    # differ by min_pp or more without a real change ("pakka nahi"); worse / better stay where they were
    mp = fixture["asset"]["consts"]["min_pp"]
    same = unsure = 0
    for a in fixture["asset"]["apps"]:
        v = a["survival"]["verdict"]
        if v is None or v["fires"] or v["low_sample"] or any(x["family"] == "cohort" for x in a["alerts"]):
            continue
        g = float(per100(v["recent"]["left"])) - float(per100(v["prev"]["left"]))
        if abs(g) >= mp:
            unsure += 1
        else:
            same += 1
    lines = report["portfolio_lines"]
    assert ("Baaki %d apps pichhle mahine jaisa" % same) in lines or ("Sab %d apps pichhle mahine jaisa" % same) in lines
    assert ("ℹ️ %d app%s me pichhle mahine se farak dikha, par abhi pakka nahi" % (unsure, "" if unsure == 1 else "s")) in lines
    for a in fixture["asset"]["apps"]:
        for x in a["alerts"]:
            if x["family"] == "cohort" and x["dir"] == "up":
                assert re.search(r"⚠️ \d+ apps? me kuch dino ke installs zyada hata rahe: .*" + re.escape(a["app"]), lines)


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
    assert h["screen"].startswith('<span class="backlnk" onclick="uniBack()">← Saari apps</span>')
    assert h["after"]["app"] == "" and h["after"]["uniapp"] == ""
    assert h["after"]["sel"] == '<option value="">All apps (0)</option>' and "Uninstall" in h["after"]["screen"]
    assert not any("✕ Saari apps dikhao" in v for k, v in report["texts"].items() if k != "overview_no_admob")


def test_the_totals_line_says_every_install_since_the_launch_and_where_the_bache_numbers_come_from(report, fixture):
    for a in fixture["asset"]["apps"]:
        t, c, L = report["totals"][a["app"]], a["survival"]["all"], a["launch"]
        head = ("Launch (%s)" if L["hidden"] else "GA4 data shuru (%s)") % t["day"]
        want = "%s se ab tak %s installs" % (head, t["installs"])
        if c["k"]:
            want += ' · "100 me se kitne bache" %d din ke installs se' % c["k"][0]
            gone = ["%s ka data %s" % (", ".join(day_txt(d) for d in L_), w) for L_, w in
                    ((c["gap_inc"], "adhoora"), (c["gap_brk"], "gayab")) if L_]
            if gone:
                want += " (%s — %s is ginti me nahi)" % (", ".join(gone), "ye din" if c["gap_days"] > 1 else "woh din")
        assert t["line"] == want, a["app"]
    tx = report["texts"]                                    # a tracking break is "gayab", an incomplete day "adhoora"
    assert "(14 Sep ka data gayab — woh din is ginti me nahi)" in tx["detail|Demo Wallpapers|all|30|cp|false"]
    assert "(3 Sep ka data adhoora — woh din is ginti me nahi)" in tx["detail|Demo Launcher|all|30|cp|false"]


def test_test_installs_before_the_launch_are_hidden_with_one_line_and_shown_on_a_tap(report, fixture):
    wall = [a for a in fixture["asset"]["apps"] if a["launch"]["hidden"]]
    assert [a["app"] for a in wall] == ["Demo Wallpapers"] and wall[0]["launch"]["pre_installs"] > 0
    L, tx = wall[0]["launch"], report["texts"]
    line = "🧪 Launch (16 Jun) se pehle ke %d test installs chhupaye · dikhao" % L["pre_installs"]
    assert line in tx["detail|Demo Wallpapers|all|30|cp|false"]
    assert not any("test installs chhupaye" in v for k, v in tx.items()
                   if "Wallpapers" not in k and k not in ("no_verdict_young_launch", "maybe_test"))
    for k in ("detail|Demo Wallpapers|all|30|cp|false", "detail|Demo Wallpapers|all|90|all|true"):
        assert "· test" not in tx[k] and "Launch (16 Jun) se ab tak" in tx[k]           # hidden by default
    for m in ("cp", "all"):
        t = tx["pre|Demo Wallpapers|" + m]
        assert "test installs bhi dikh rahe · chhupao" in t and "🧪 Test installs (launch 16 Jun se pehle)" in t
        assert "installs · test" in t and "── 2025 ──" in t and "── 2026 ──" in t        # the test weeks + their year
        assert "0 installs · test" not in t                                               # an empty test week: not a row
        assert "GA4 data shuru (20 Aug 2025) se ab tak" in t and "20 Aug 2025–23 Sep 2026 · 400d" in t
        assert "(launch 16 Jun 2026 se pehle ke test installs bhi)" in t                   # next to a 2025 date: its year
    assert "(launch 16 Jun se; usse pehle ke test installs nahi)" in tx["detail|Demo Wallpapers|all|30|cp|false"]
    # more than a trickle a day before the launch: only "shayad test" (could be early real users)
    m = tx["maybe_test"]
    assert "se pehle ke %d installs (shayad test) chhupaye · dikhao" % L["pre_installs"] in m
    assert "🧪 Installs (shayad test) (launch 16 Jun se pehle)" in m and "installs · shayad test" in m


def test_every_date_says_its_year_when_it_is_not_obvious(report):
    tx = report["texts"]
    cal = tx["detail|Demo Caller – Test App|all|30|cp|false"]
    assert "Hamesha = 27 Jan–16 Sep 2026 ke saare pakke installs" in cal                 # 8 months back: the year
    assert "── 2026 ──" in tx["detail|Demo Caller – Test App|all|90|all|true"]         # the triangle's year rows
    assert "16–22 Sep ke installs" in cal                                                # this month: plain
    wal = tx["pre|Demo Wallpapers|all"]                                                  # across a year: both years
    assert "Hamesha = 20 Aug 2025–16 Sep 2026 ke saare pakke installs" in wal and "20 Aug 2025–23 Sep 2026 · 400d" in wal
    assert "2025–16 Sep ke" not in wal and "2025–23 Sep ·" not in wal
    assert "29 Dec 2025–4 Jan" in wal                  # a triangle week under its "── 2026 ──" row: the short form


def test_old_install_changes_are_info_in_a_collapsed_list_never_counted(report, fixture):
    tx, lines = report["texts"], report["portfolio_lines"]
    olds = [(a["app"], o) for a in fixture["asset"]["apps"] for o in a["old_changes"]]
    assert olds and all(o["checkpoint"] == "D180" for _, o in olds)
    n_open = len(fixture["dashboard_uninstall"]["alerts"])
    assert report["plain_kya_badla"] == str(n_open)                                      # not counted in "Kya badla?"
    assert "Purane installs ke badlaav (%d) dikhao" % len(olds) in tx["portfolio_30d"] and "Mar 2026" not in lines
    cal_closed = tx["detail|Demo Caller – Test App|all|30|cp|false"]
    assert "Purane installs ke badlaav (1) dikhao" in cal_closed and "14–20 Mar 2026 ke installs" not in cal_closed
    assert "Band ho chuke alerts" not in cal_closed                          # none closed: no such list
    cal_open = tx["detail|Demo Caller – Test App|all|90|all|true"]
    # March installs are compared with the 4 weeks before THEM — "pichhle 4 hafte" would read as the last 4 weeks
    assert ("ℹ️ 14–20 Mar 2026 ke installs: 180 din ke andar 58% ne hataya — usse pehle ke 4 hafte (14 Feb–13 Mar "
            "2026) me 52%") in cal_open
    assert "60 din se purane installs ke badlaav — sirf jaankari" in cal_open
    # the full table's 180-din row: the same change — "Purane installs", never "Normal" next to its arrow
    assert re.search(r"180 din .*? ▲ \+6 point 14–20 Mar 2026 ℹ️ Purane installs 210 din", cal_open)


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


def test_every_har_din_page_names_the_4_weeks_and_no_page_is_only_test_installs(report):
    t = report["texts"]["tripage1_caller"]
    assert "4 hafte ka average 17 Aug–13 Sep ke installs abhi itne din tak nahi pahunche" in t
    assert "Abhi 4 pakke hafte nahi" not in t
    p = report["pages"]
    assert p["hid"] == p["want_hid"] < p["all"] == p["want_all"]            # test installs hidden: fewer pages …
    assert p["last_col"] == p["reach"]                                       # … ending at the day the launch reached


def test_no_verdict_for_a_young_app_blames_its_age_not_the_data(report):
    t = report["texts"]["no_verdict_young_launch"]
    assert "Pichhle mahine se tulna ~2 mahine ke data ke baad" in t and "adhoora/gayab" not in t


def test_app_updates_are_a_line_right_above_the_install_week_they_fell_in(report):
    r, tx = report["rel"], report["texts"]
    # every app × both modes × test weeks hidden / shown × 12 / all rows (+ made-up updates): each 📦 line is right
    # above the week its update(s) fell in, that week alone has the 📦 badge, the legend only comes with a line
    assert r["bad"] == [] and r["checked"] >= 1000 and r["lines"] >= 20
    legend = "📦 = naya update. Line ke upar wale hafte = naye version ke installs, neeche = purane version ke."
    for m in ("cp", "all"):                                  # the fixture's own updates (the engine's releases)
        cal, wea, lau, fla = (tx["rel|%s|%s|false|false" % (a, m)] for a in
                              ("Demo Caller – Test App", "Demo Weather", "Demo Launcher", "Demo Flashlight"))
        assert "📦 Naya update v3.2 aaya — 10 Sep (is hafte ke beech) 7–13 Sep 📦 " in cal and legend in cal
        assert re.search(r"14–20 Sep [^📦–]* 📦 Naya update v3\.2", cal)                   # between 14–20 and 7–13 Sep
        assert re.search(r"20–26 Jul [^📦–]* 📦 Naya update v4\.1 aaya — 15 Jul \(is hafte ke beech\) 13–19 Jul 📦 ", wea)
        assert "📦 Naya update aaya — 5 Aug (update karne wale achanak badhe) 3–9 Aug 📦 " in lau and legend in lau
        assert "📦" not in fla                                                             # no update: no line, no legend
        assert r["tips"]["Demo Caller – Test App|%s|false|false" % m] == ["Is hafte naya update v3.2 aaya — 10 Sep"]
        assert r["tips"]["Demo Launcher|%s|false|false" % m] == [
            "Is hafte naya update aaya — 5 Aug (update karne wale achanak badhe)"]
        # several in one week: ONE line naming them all (a version already called "v…" is not "vv…")
        two = tx["rel|two|" + m]
        assert "📦 3 update: v3.2 (8 Sep), update (11 Sep), v3.2.1 (12 Sep) 7–13 Sep 📦 " in two
        assert two.count("update:") == 1 and "vv" not in two
        assert r["tips"]["two|" + m] == ["Is hafte 3 update: v3.2 (8 Sep), update (11 Sep), v3.2.1 (12 Sep)"]
        # in the newest (partial) week: under the year row, above that week, first thing after the 4-week row
        assert re.search(r"4 hafte ka average .*? ── 2026 ── 📦 Naya update v3\.3 aaya — 22 Sep \(is hafte ke beech\) "
                         r"21–23 Sep \(sirf 3 din\) 📦 [\d.k]+ installs", tx["rel|newest|" + m])
        assert "📦" not in tx["rel|none|" + m]
        # among the test installs before the launch: only while those are shown, with its year, under its year row
        assert "📦" not in tx["rel|test|%s|false" % m]
        assert "── 2025 ── 📦 Naya update v1.1 aaya — 24 Dec 2025 (is hafte ke beech) 22–28 Dec 📦 " in tx[
            "rel|test|%s|true" % m] and legend in tx["rel|test|%s|true" % m]
        # the week the launch cuts in two: the launch day's update above the first launched week, the last test
        # week's only while the test installs are shown
        launch = ["Is hafte naya update v1.0 aaya — 16 Jun"]
        assert r["tips"]["launch|%s|false" % m] == launch
        assert r["tips"]["launch|%s|true" % m] == launch + ["Is hafte naya update v0.9 aaya — 14 Jun"]
    # "Har din" page 2 (days 31–61: the same weeks) keeps every 📦 line
    for pre in ("false", "true"):
        assert r["pages"]["Demo Caller – Test App|all|%s|page2" % pre] == 1
        assert r["tips"]["Demo Caller – Test App|all|%s|page2" % pre] == ["Is hafte naya update v3.2 aaya — 10 Sep"]
        assert r["tips"]["Demo Weather|all|%s|page2" % pre] == ["Is hafte naya update v4.1 aaya — 15 Jul"]
