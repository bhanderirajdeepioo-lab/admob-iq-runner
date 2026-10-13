"""🆕 First open tab — the page side. tests/firstopen_frontend.js runs the FO module of frontend/index.html for real (a node
vm, stub page helpers) on SYNTHETIC data made up there; checked here: the pointer check, the lazy file (a failed load +
Try again), All apps (status chips, Worse first, a column sort, the chip filter that never pulls the page up, hidden apps
left out, the App picker's names), one app (Today / Yesterday / 7 days / usual, the steps, every month, every day with
not-final days and GA4 sampling marked), the hub card from the pointer, and the wiring into the page (nav, hub tab and
card, show(), the Period picker hidden). Skipped where node is not installed. No real data."""
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
    r = subprocess.run([NODE, os.path.join(ROOT, "tests", "firstopen_frontend.js"), PAGE],
                       check=True, capture_output=True, text=True, timeout=120)
    rep = json.loads(r.stdout)
    assert not rep["errors"], rep["errors"]
    return rep["out"]


def test_pointer_and_lazy_load(out):
    assert out["no_ptr"] and out["bad_file"] and out["ptr"]
    assert out["loads_before_open"] == 0                       # the hub card never loads the file
    assert out["fail_html"] and out["loads"] == 2              # a failed load shows Try again; the tap loads again
    assert out["no_ptr_note"]


def test_all_apps(out):
    assert out["all_chips"] == [["Worse", 1], ["Watch", 0], ["Better", 1], ["Normal", 1], ["Too early", 0], ["N/A", 0]]
    assert out["all_rows"] == ["Alpha Pick", "Beta Pick", "Gamma"] and not out["all_hidden"]   # Worse first; the picker's names
    assert out["all_smp"] and out["all_zero_pts"]
    assert out["sort_rows"] == ["Beta Pick", "Gamma", "Alpha Pick"]
    assert out["filt_rows"] == ["Alpha Pick"] and out["filt_minh"] == "900px"   # the page keeps its height (no jump)
    assert out["filt_empty"] and out["filt_off_rows"] == 3
    assert out["row_tap"] == ["Alpha Pick"]


def test_one_app(out):
    assert out["app_mini"]
    assert out["app_months"] == [["Sep 2026", 29, "3,480"], ["Aug 2026", 31, "3,720"]]   # every month, newest first
    assert out["app_days"] == 60                                                         # every day, nothing trimmed
    assert out["app_first_day_row"] and out["app_changed"] and out["app_smp_note"]
    assert not out["app_lang_col"] and out["alpha_lang_col"] and out["alpha_steps"]
    assert out["app_missing"]


def test_hub_card(out):
    assert out["card_alpha"] == {"st": "bigda", "line": "Splash → Home <b>50%</b> · usual 60% (−10 pts)"}
    assert out["card_gamma"]["line"].endswith("(0 pts)") and out["card_gamma"]["st"] == "normal"
    assert out["card_none"]["st"] == "lagu"


def test_wiring():
    p = _page()
    assert '<li id="nav-fo-li" hidden><button data-screen="firstopen">' in p
    assert "li.hidden=!FO.ptr()" in p and "root.append(renderFirstOpen())" in p
    assert "if(id==='firstopen') FO.show();" in p
    assert re.search(r"firstopen:\['First open','🆕','firstopen','firstopen'\]", p)
    assert re.search(r"const HUB_ALL=\[[^\]]*'firstopen'", p) and re.search(r"const HUB_APP=\[[^\]]*'firstopen'", p)
    assert "(t!=='firstopen'||fo)" in p and "(c[0]!=='firstopen'||fo)" in p
    assert "['firstopen','firstopen','First open','🆕','fo']" in p and "if(src==='fo')" in p
    assert 'body[data-screen="firstopen"] #rangectl' in p
    assert "firstopen:[\"First open\"," in p
