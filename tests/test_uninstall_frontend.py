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
