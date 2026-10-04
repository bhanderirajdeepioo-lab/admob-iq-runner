"""Stay put — owner, on his iPhone: "kuchh change karte he to upar chala jata he page … pure dashboard me check karo, aage se
dhyan rakhna" (tap a control mid-page and the page jumps back up). Many controls rebuild a whole screen, and iOS Safari has
no CSS scroll anchoring, so ONE layer in frontend/index.html (SP) keeps a tapped control where it was on screen, on every
screen. tests/stayput_frontend.js runs that layer, taken out of the page as it is, in a node vm on a small SYNTHETIC page
(elements with a document position, a window that scrolls and clamps, capture / bubble listeners, timers and frames run by
hand) and checks:

  * a tap whose handler rebuilds the screen (new nodes, content above grown, the page thrown to the top) → the control is
    back exactly where it was — right after the handlers (a microtask), and again when the page shifts late (150 ms);
  * the control is found again by its signature (data-* / id / onclick …), by its index among twins, or by its path + text
    (also when its onclick carried a state, open ⇄ closed);
    a row inside a box that scrolls on its own keeps the box in place; a control in the sticky top bar (₹/$) keeps scrollY;
  * a scroll the code asks for (scrollTo / scrollIntoView: a drill-down, "Open →", Back) is NOT undone; nor a reader who
    scrolls (touchmove / wheel) after the tap; nor a new screen / app; nor a control that is gone; nor ≤ 3px;
  * a <select> keeps its place on its change; a text field is never anchored (the phone keyboard scrolls on purpose);
    a control in a fixed layer (drawer) is left alone; a finger that scrolled after touching down is not a tap;
  * SP.keepY (rerender's restore) clamps to the new page and is not "intentional"; scrollTo / scroll / scrollBy /
    scrollIntoView are wrapped.
Plus the wiring in the page: rerender() / show() / the Audience levers (see also test_refresh_frontend.py and
test_audience_frontend.py for those run for real). Skipped where node is not installed. No real data."""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "frontend", "index.html")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


def _script():
    with open(PAGE, encoding="utf-8") as f:
        return max(re.findall(r"<script>(.*?)</script>", f.read(), re.S), key=len)


@pytest.fixture(scope="module")
def report():
    if NODE is None:
        pytest.skip("node is not installed")
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "stayput_frontend.js"), PAGE],
                         check=True, capture_output=True, text=True, timeout=120)
    rep = json.loads(out.stdout)
    assert rep["errors"] == [], rep["errors"]
    return rep["out"]


def same_place(r):
    assert r["before"] == r["after"], r


@needs_node
def test_a_rebuilt_screen_keeps_the_tapped_control_in_place(report):
    r = report["rebuild_restored"]
    same_place(r)
    assert r["y"] == 2600 + 172                                                 # not 0: the page was thrown to the top
    same_place(report["restored_without_a_timer"])                              # right after the handlers already
    same_place(report["late_shift_at_150ms"])                                   # iOS settles late: caught at 150 ms


@needs_node
def test_the_control_is_found_again(report):
    for k in ("same_node_moved", "path_signature", "state_in_onclick", "twin_chips_by_index", "scroll_box_anchor", "keyboard_enter", "select_change"):
        same_place(report[k])
    assert report["top_bar_keeps_scrollY"]["y"] == 2600                         # ₹/$ in the sticky top bar: scrollY kept


@needs_node
def test_intentional_scrolls_are_not_undone(report):
    r = report["intentional_scrollTo_kept"]
    assert r["y"] == 0 and r["intent"] is True                                  # a drill-down / Back to the top stays there
    r = report["intentional_scrollIntoView_kept"]
    assert r["y"] == r["want"]                                                  # "Open →" lands where it was sent


@needs_node
def test_the_layer_never_fights_the_reader_or_real_navigation(report):
    assert report["reader_scrolls_after_tap"]["y"] == 1234                      # touchmove after the tap: hands off
    assert report["wheel_cancels"]["y"] == 777
    assert report["screen_changed"]["y"] == 0 and report["app_changed"]["y"] == 0
    assert report["control_gone"]["y"] == 500                                   # the view under it changed: leave it
    r = report["small_move_left"]
    assert r["after"] - r["before"] == 2 and r["y"] == 2600                     # ≤ 3px: no scroll at all
    assert report["fixed_layer_left_alone"]["y"] == 100                         # a drawer's control: not the page's scroll
    assert report["text_field_ignored"]["y"] == 3200                            # the phone keyboard scrolls on purpose
    same_place(report["stale_pointerdown_not_used"])                            # finger down → scroll → tap: today's place


@needs_node
def test_keep_y_and_wrappers(report):
    k = report["keepY"]
    assert k["a1"] == 2500 and k["a2"] == 1200 and k["quiet"] is True and k["intentAfterCodeScroll"] is True
    assert report["wrapped"] == {"to": True, "by": True, "sc": True, "siv": True}


def test_page_wiring():
    js = _script()
    assert js.count("const SP=(function(){") == 1 and "\n  install();\n  return api;\n})();" in js
    assert js.index("const SP=(function(){") < js.index("function show(id){")    # defined before anything can scroll
    # rerender(): a same-view rebuild — show() does not jump to the top inside it, the reader's place comes back
    rr = js[js.index("function rerender(){"):js.index("function applyRangeCustom(){")]
    assert "SP.keep++" in rr and "SP.keep--" in rr and "SP.keepY(y)" in rr and "const y=window.scrollY||0" in rr
    sh = js[js.index("function show(id){"):js.index("function _navSave(){")]
    assert "if(!_rvKeep&&!REFRESH_SILENT&&!SP.keep) window.scrollTo({top:0});" in sh
    assert js.count("if(!REFRESH_SILENT&&!SP.keep) window.scrollTo({top:0});") == 2   # openApp / openAppDetail
    # real navigation still scrolls through the (wrapped) window.scrollTo: a new app, a drill-down, Back
    assert "render(); show(cur==='reportcard'?'placements':cur); if(!REFRESH_SILENT) window.scrollTo({top:0});" in js   # setApp
    for f in ("function bDrill(app){", "function ecApp(name){", "function allApps(){ hideTip(); if(APP){ setApp(''); return; } paint(); window.scrollTo({top:0}); }"):
        i = js.index(f)
        assert "window.scrollTo({top:0})" in js[i:js.index("\n", i)], f
    # the Audience levers redraw only what they feed
    oc = js[js.index("function onClick(e){ const t=e.target; if(!inAu(t)) return;"):js.index("// ---- navigation: the top bar's App picker")]
    for k in ("auMode", "auOpens", "auEcpm"):
        assert re.search(r"dataset\.%s; save\(\); levers\(\); return; \}" % k, oc), k
    lv = js[js.index("function levers(){"):js.index("function show(){ paint(); }")]
    assert "money.outerHTML=secMoney(a)" in lv and "st.innerHTML=secStrip(a)" in lv and "tb.outerHTML=secTable()" in lv
    assert "return paint();" in lv and "preventScroll:true" in lv
