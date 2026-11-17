"""🆕 First open tab — EXACT COUNTS on the page. tests/firstopen_exact_frontend.js runs the FO module of
frontend/index.html for real (a node vm, the stubs of tests/firstopen_frontend.js) on SYNTHETIC data made up there; checked
here: a row whose First opens / Splash / Home came from the country store's exact read (x = 1) has no "≈" on its day,
only on the steps that stay sampled (Language, Incl. late open); a sampled row keeps its day "≈" (and no other); an
unsampled row none; All apps: Splash → Home with no "≈" when the week's three are exact, Incl. late open and the steps
with "≈" from "sample_other"; the app's note says which numbers are exact. Skipped where node is not installed. No real
data."""
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
    r = subprocess.run([NODE, os.path.join(ROOT, "tests", "firstopen_exact_frontend.js"), PAGE],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout.strip().splitlines()[-1])
    assert o["errors"] == []
    return o


def test_an_exact_row_marks_only_the_steps_that_stay_sampled(out):
    assert out["x_day_plain"] and out["x_smp_cells"] == 2 and out["x_lang_smp"]


def test_a_sampled_row_keeps_its_day_mark_and_an_unsampled_row_has_none(out):
    assert out["s_day_smp"] and out["u_none"]


def test_all_apps_marks_from_sample_and_sample_other(out):
    assert out["all_s2h_plain"] and out["all_any_smp"] and out["all_steps_smp"]


def test_the_apps_note_says_which_numbers_are_exact(out):
    assert out["note_pct"] and out["note_exact"]


def test_the_charts_tip_never_calls_an_exact_day_sampled():
    with open(PAGE, encoding="utf-8") as f:
        page = f.read()
    assert "${d[IX.sample]!=null&&d[IX.sample]<1&&!d[IX.x]?`<br>≈ GA4 sampling:" in page
