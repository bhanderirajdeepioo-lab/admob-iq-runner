"""The Baseline ad-unit jump (bGotoUnit: an alert / recommendation row → that placement's page) and the header App picker.

The jump sets APP='' ("All apps") and shows Baseline WITHOUT a full render(), so the header (the picker button, its icon,
the hidden <select>) kept naming the old app until the next render. Run for real by tests/baseline_goto_frontend.js (the
page script in a node vm with a small DOM) on a SYNTHETIC dashboard made up there. Checked here:

  * right after the jump the header says "All apps (N)" (button text + aria-label), the icon is 📱, the hidden <select>
    is on "All apps" — already when show('baseline') runs;
  * an app listed only because it was in view (an Uninstall-tab app with no AdMob row) leaves the <select>'s list;
  * the Baseline navigation is unchanged: BUNIT = the unit, BSEL = its app (once Baseline is loaded), show('baseline')
    once then bRerender; no full render(), no setApp(); not loaded yet → the lazy load starts and BSEL is left alone;
  * structural: render() and bGotoUnit share one header sync (appSelSync).
Skipped where node is not installed. No real data: every name, id and URL is made up."""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
ALL = ["", "Demo Gallery", "Puzzle Quest"]


def _script():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        return max(re.findall(r"<script>(.*?)</script>", f.read(), re.S), key=len)


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("bgoto_js") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_script())
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "baseline_goto_frontend.js"), path],
                         check=True, capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout)


def O(report, k):
    assert k in report["out"], (k, report["errors"])
    return report["out"][k]


def all_apps(h):
    """the header on "All apps": button, its label, the 📱 icon, the hidden <select>"""
    return h["APP"] == "" and h["nm"] == "All apps (2)" and h["label"] == "App: All apps (2)" and h["ic"] == "📱" \
        and h["sel"] == ""


def test_runs_without_errors(report):
    assert report["errors"] == []


def test_jump_puts_the_header_on_all_apps(report):
    b = O(report, "before")
    assert b["nm"] == "Puzzle Quest" and b["sel"] == "Puzzle Quest" and "icons.example.test/pq.png" in b["ic"]
    g = O(report, "goto")
    assert all_apps(g) and g["opts"] == ALL
    assert g["calls"][0] == 'show:baseline APP="" nm=All apps (2)'          # synced before Baseline is shown


def test_jump_keeps_the_baseline_navigation(report):
    g = O(report, "goto")
    assert g["BUNIT"] == "unit-101" and g["BSEL"] == "Puzzle Quest"
    assert [c.split(" ")[0] for c in g["calls"]] == ["show:baseline", "bRerender"]   # no render(), no setApp()


def test_ghost_app_leaves_the_list_and_lazy_load(report):
    b = O(report, "ghost_before")
    assert b["opts"] == ["", "Ghost App", "Demo Gallery", "Puzzle Quest"] and b["sel"] == "Ghost App"
    g = O(report, "ghost_goto")
    assert all_apps(g) and g["opts"] == ALL                                   # listed only while in view
    assert g["BUNIT"] == "unit-102" and g["BSEL"] is None and g["BLOADING"] is True
    assert [c.split(" ")[0] for c in g["calls"]] == ["show:baseline"]         # not loaded: no bRerender yet


def test_jump_from_all_apps(report):
    a = O(report, "all_goto")
    assert all_apps(a) and a["opts"] == ALL and a["BUNIT"] == "unit-102" and a["BSEL"] == "Demo Gallery"
    assert [c.split(" ")[0] for c in a["calls"]] == ["show:baseline", "bRerender"]


def test_one_header_sync_for_render_and_the_jump():
    js = _script()
    goto = js[js.index("function bGotoUnit("):]
    goto = goto[:goto.index("\n")]
    assert "APP=''; appSelSync(); }" in goto and goto.index("appSelSync()") < goto.index("show('baseline')")
    assert not re.search(r"(?<![\w.])render\(", goto) and "setApp(" not in goto   # bRerender() is the Baseline's own
    r0 = js.index("function render(){")
    assert "\n  appSelSync();\n" in js[r0:js.index("function show(", r0)]
