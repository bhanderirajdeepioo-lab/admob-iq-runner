"""Auto-refresh (frontend/index.html's setInterval(refreshData, 300000)): the owner's report — reading lower down the
page, the 5-min poll fires, the page blinks and jumps back to the top. tests/refresh_frontend.js runs the real page
script in a node vm (a small DOM, same recipe as mobile_global_frontend.js) and checks:

  * same build (DATA.generated_at unchanged, i.e. the robot hasn't produced a new dashboard.json since the last poll):
    refreshData() never calls render()/show() at all — DATA still updates and LAST_BUILD/HB.mute/REFRESH_SILENT stay clean;
  * changed build: refreshData() DOES rebuild, but with REFRESH_SILENT set for render() and show() (HB.mute is also up,
    so it never adds a Back-button step), and restores the reader's exact pre-refresh scrollY afterward (requestAnimationFrame,
    clamped to the rebuilt page's height) — both flags are back to their normal state once it's done;
  * the restore clamps to the page's new height instead of scrolling past its new bottom;
  * the real show() function: REFRESH_SILENT suppresses its scrollTo(top:0) AND its closeNav() (an open mobile nav/"More"
    menu is left alone); without REFRESH_SILENT it behaves exactly as before.

Skipped where node is not installed."""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


def _script():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    return max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    if NODE is None:
        pytest.skip("node is not installed")
    path = str(tmp_path_factory.mktemp("refresh_js") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_script())
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "refresh_frontend.js"), path],
                          check=True, capture_output=True, text=True, timeout=180)
    rep = json.loads(out.stdout)
    assert rep["errors"] == [], rep["errors"]
    return rep


def O(report, k):
    assert k in report["out"], (k, report["errors"])
    return report["out"][k]


# ── same build: nothing to redraw ───────────────────────────────────────────────────────────────────────────────────
@needs_node
def test_same_build_never_touches_the_dom(report):
    r = O(report, "same_build_skips_render")
    assert r["render"] == 0                        # render() never called
    assert r["show"] == []                          # show()/openApp()/openAppDetail()/goPlacement() never called
    assert r["fresh"] == 1                           # only the "X min ago" text updates
    assert r["dataV"] == 2                           # DATA itself IS replaced with the freshly-fetched object
    assert r["lastBuild"] == "B1"                    # unchanged — still the same build id
    assert r["muteAfter"] == 0                       # HB.mute balanced (never even touched)
    assert r["silentAfter"] is False


# ── changed build: rebuilds in place, silently, and restores the reader's scroll ───────────────────────────────────
@needs_node
def test_changed_build_rerenders_silently_and_keeps_scroll(report):
    r = O(report, "changed_build_renders_silently_and_restores_scroll")
    assert r["renderSilentDuring"] is True           # render() ran with REFRESH_SILENT set
    assert r["showSilentDuring"] is True              # so did show(cur)
    assert r["showId"] == "uninstall"                # it re-opened the SAME tab the reader was on, not Overview
    assert r["muteDuring"] == 1                       # HB.mute was up during the rebuild → no new Back-button step
    assert r["silentRightAfter"] is False             # both flags cleaned up in the finally{}
    assert r["muteRightAfter"] == 0
    assert r["lastBuild"] == "B2"                     # the new build id is now remembered
    assert r["dataV"] == 2
    assert r["scrollCalls"] == 1                      # exactly one scroll adjustment — the restore, nothing from show()
    assert r["scrollYAfterRaf"] == 743                # landed back EXACTLY where the reader was


@needs_node
def test_scroll_restore_clamps_to_shorter_page(report):
    r = O(report, "scroll_restore_clamps_to_new_height")
    assert r["calls"], "the restore should still run even though the old Y is now out of range"
    assert r["scrollY"] == 300                        # 1200 (scrollHeight) - 900 (innerHeight) = 300, never the stale 5000


# ── show(): REFRESH_SILENT must block BOTH the top-jump and the nav/"More" menu auto-close ─────────────────────────
@needs_node
def test_show_silent_skips_scroll_and_nav_close(report):
    r = O(report, "show_real_no_scroll_or_navclose_when_silent")
    assert r["duringSilent"]["scrollCalls"] == 0
    assert r["duringSilent"]["navOpen"] is True        # an open mobile menu is left alone during a silent refresh
    assert r["normal"]["scrollCalls"] == 1             # the ordinary (non-refresh) path is unchanged
    assert r["normal"]["navOpen"] is False
