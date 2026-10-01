"""The header App picker (owner: "isme icon nahi aaya abhi tak" — a native <select> can't show app icons).

Run for real by tests/app_picker_frontend.js (the page script in a node vm with a small DOM) on a SYNTHETIC dashboard made
up there: two same-named "Demo Gallery" apps in two accounts, one app hidden in Accounts & Apps, a logo-less app, a name
with HTML characters, a very long name. Checked here:

  * the list: "All apps (N)" first (📱), then every VISIBLE app in the hidden <select>'s order, each with ITS OWN icon
    (by app_id — a same-named twin never borrows a cousin's logo), the account in muted text only when the name doesn't
    already carry it, the app in view marked ✓ (aria-selected) and highlighted; names escaped;
  * the search box (focused on open): filters by app or account, case-blind, every word must match; nothing → a note;
  * the keyboard: ↓ / ↑ / PageDown / PageUp move and clamp, Enter picks, Esc closes (back to the button), Tab leaves
    (not swallowed), typing on the closed button opens the list with that letter;
  * the mouse / touch: a click on a row picks it (focus kept in the search box on mousedown), the button toggles, a click
    outside or on the phone scrim closes, a touch open focuses the list (no phone keyboard over the icons);
  * a pick runs the old path — setApp(name) — once, keeps the hidden <select> in sync and refreshes the button;
    re-picking the app in view does nothing (as the native <select>); "All apps" → setApp('');
  * an app in view with no AdMob row (an Uninstall-tab app) is listed and ✓; an open list survives a refresh;
  * structural: the topbar markup (button ARIA, the hidden <select>, the Hinglish title), the wiring in render().
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
ROW = re.compile(r'<li role="option" id="apk-o-(\d+)" data-i="(\d+)" class="([^"]*)" aria-selected="(true|false)">(.*?)</li>', re.S)
ICON = re.compile(r'<span class="aicon[^"]*" aria-hidden="true" data-l="([^"]*)" style="width:(\d+)px[^"]*">(?:<img src="([^"]*)"[^>]*>)?</span>')
VISIBLE = ["Demo Gallery · Alpha Studio", "Demo Gallery · pub-2000…", "Puzzle Quest", 'Tom & Jerry "Run" <2>',
           "Very Long Name Calculator Pro Plus With Many Extra Words To Wrap Nicely"]


def _page():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        return f.read()


def _script():
    return max(re.findall(r"<script>(.*?)</script>", _page(), re.S), key=len)


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("apk_js") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_script())
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "app_picker_frontend.js"), path],
                         check=True, capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout)


def O(report, k):
    assert k in report["out"], (k, report["errors"])
    return report["out"][k]


def rows(html):
    """[{i, act, cur, sel, name, acc, icon:(letter,size,url)|None, all, check}] for every option in the list html."""
    out = []
    for m in ROW.finditer(html):
        body = m.group(5)
        ic = ICON.search(body)
        nm = re.search(r'<span class="apk-nm">([^<]*)</span>', body)
        ac = re.search(r'<span class="apk-ac">([^<]*)</span>', body)
        ck = re.search(r'<span class="apk-ck" aria-hidden="true">([^<]*)</span>', body)
        out.append({"i": int(m.group(1)), "act": " act" in " " + m.group(3), "cur": "cur" in m.group(3).split(),
                    "sel": m.group(4) == "true", "name": nm.group(1) if nm else None, "acc": ac.group(1) if ac else None,
                    "icon": (ic.group(1), int(ic.group(2)), ic.group(3)) if ic else None,
                    "all": '<span class="apk-all" aria-hidden="true">📱</span>' in body, "check": ck.group(1) if ck else None})
        assert m.group(1) == m.group(2)
    return out


def unesc(s):
    return s.replace("&lt;", "<").replace("&quot;", '"').replace("&amp;", "&")


def test_runs_without_errors(report):
    assert report["errors"] == []


def test_wired_once_into_body_with_the_search_and_listbox(report):
    w = O(report, "wired")
    assert w["pop_children"] == 1 and w["pop_id"] == "apk-pop"            # apkWire() twice → one popover, in <body>
    h = w["pop_html"]
    assert '<input id="apk-q" type="text" role="combobox" aria-expanded="true" aria-controls="apk-list" aria-autocomplete="list"' in h
    assert 'placeholder="Search app or account…"' in h and 'aria-label="Search app or account"' in h
    assert '<ul id="apk-list" role="listbox" aria-label="Apps" tabindex="-1"></ul>' in h
    assert '<div class="apk-none" id="apk-none" role="status" hidden>No apps found</div>' in h
    assert [o["value"] for o in w["select_opts"]] == [""] + VISIBLE          # the hidden <select> = appSelHtml(), as before


def test_closed_button_names_all_apps(report):
    c = O(report, "closed")
    assert c["nm"] == "All apps (5)" and c["label"] == "App: All apps (5)"
    assert c["open"] is False and c["hidden"] is True and c["APP"] == "" and c["calls"] == []


def test_list_every_visible_app_with_its_own_icon(report):
    s = O(report, "open_click")
    assert s["open"] and not s["hidden"] and s["exp"] == "true" and s["focus"] == "apk-q"   # search focused on open
    r = rows(s["list"])
    assert [unesc(x["name"]) for x in r] == ["All apps (5)"] + VISIBLE         # "All apps" on top, then the <select>'s order
    assert "Hidden Tool" not in s["list"]                                     # unselected in Accounts & Apps → not listed
    assert r[0]["all"] and r[0]["icon"] is None                               # 📱 for All apps
    icons = {unesc(x["name"]): x["icon"] for x in r[1:]}
    assert icons["Demo Gallery · Alpha Studio"] == ("D", 20, "https://icons.example.test/g1.png")
    assert icons["Demo Gallery · pub-2000…"] == ("D", 20, "https://icons.example.test/g2.png")   # the twin: ITS OWN logo
    assert icons["Puzzle Quest"] == ("P", 20, "https://icons.example.test/pq.png")
    assert icons['Tom & Jerry "Run" <2>'] == ("T", 20, "https://icons.example.test/tj.png")
    assert icons["Very Long Name Calculator Pro Plus With Many Extra Words To Wrap Nicely"] == ("V", 20, None)   # no logo → letter
    assert all(x["icon"] is not None for x in r[1:])
    # the account, muted, only where the name doesn't already say it
    acc = {unesc(x["name"]): x["acc"] for x in r[1:]}
    assert acc["Demo Gallery · Alpha Studio"] is None                          # "· Alpha Studio" is in the name
    assert acc["Puzzle Quest"] == "Alpha Studio"                               # the Accounts & Apps name wins over the label
    assert acc["Demo Gallery · pub-2000…"] == "Second"                         # no friendly name → the account's label
    # the app in view (All apps) ✓, aria-selected, highlighted = the active descendant
    assert [x["sel"] for x in r] == [True] + [False] * 5 and r[0]["check"] == "✓" and r[0]["cur"] and r[0]["act"]
    assert all(x["check"] == "" for x in r[1:])
    assert s["ad"] == "apk-o-0" == s["ad_list"]
    # names are escaped
    assert "Tom &amp; Jerry &quot;Run&quot; &lt;2>" in s["list"] and "<2>" not in s["list"]


def test_search_filters_by_app_or_account(report):
    a = O(report, "search_alpha")                                             # account name OR app name
    assert [unesc(x["name"]) for x in rows(a["list"])] == ["Demo Gallery · Alpha Studio", "Puzzle Quest"]
    assert a["ad"] == "apk-o-1" and rows(a["list"])[0]["act"] and a["none_hidden"] is True   # the first match highlighted
    p = O(report, "search_puzzle")                                            # case-blind, trimmed
    assert [x["name"] for x in rows(p["list"])] == ["Puzzle Quest"] and p["ad"] == "apk-o-3"
    t = O(report, "search_two_words")                                         # every word must match (account + app)
    assert [unesc(x["name"]) for x in rows(t["list"])] == ["Demo Gallery · pub-2000…"]
    n = O(report, "search_none")
    assert rows(n["list"]) == [] and n["none_hidden"] is False and n["ad"] is None and n["act"] == -1
    assert n["enter_prevented"] and n["after"]["open"] and n["after"]["calls"] == []   # Enter on nothing: no pick
    c = O(report, "search_cleared")
    assert len(rows(c["list"])) == 6 and c["ad"] == "apk-o-0" and c["none_hidden"] is True


def test_keyboard_moves_and_enter_picks(report):
    k = O(report, "keys")
    assert k["up_at_top"] == 0                                                # ↑ at the top stays
    assert k["after_two_down"]["ad"] == "apk-o-2" and k["after_two_down"]["act"] == 2
    assert k["pagedown_clamps"] is True and k["pageup_clamps"] == 0
    assert k["want"] == VISIBLE[1]
    a = k["after"]
    assert k["enter_prevented"] and a["calls"] == [VISIBLE[1]]                # setApp(name), once
    assert a["open"] is False and a["hidden"] is True and a["exp"] == "false" and a["focus"] == "apk-btn"
    assert a["sel"] == VISIBLE[1] and a["APP"] == VISIBLE[1]                  # the hidden <select> follows
    assert a["nm"] == VISIBLE[1] and a["label"] == "App: " + VISIBLE[1]       # the button names the app
    assert a["quiet"] is False                                                # a keyboard pick keeps the focus ring


def test_escape_closes_back_to_the_button(report):
    e = O(report, "esc")
    o = e["opened"]
    assert o["open"] and o["focus"] == "apk-q"                                # ↓ on the button opens it
    assert [x["sel"] for x in rows(o["list"])][2] is True and o["ad"] == "apk-o-2"   # the app in view ✓ + highlighted
    assert e["prevented"] and e["stopped"]                                    # Esc is ours (no Studio shortcut behind it)
    a = e["after"]
    assert a["open"] is False and a["focus"] == "apk-btn" and a["calls"] == [] and a["APP"] == VISIBLE[1]


def test_click_picks_the_row(report):
    c = O(report, "click_pick")
    assert c["want"] == VISIBLE[2] and c["hover_act"] == "apk-o-3"           # hover highlights
    assert c["mousedown_prevented"] is True                                   # the search box keeps focus
    a = c["after"]
    assert a["calls"] == [VISIBLE[2]] and a["APP"] == VISIBLE[2] and a["sel"] == VISIBLE[2] and a["nm"] == VISIBLE[2]
    assert a["open"] is False and a["focus"] == "apk-btn" and a["quiet"] is True   # mouse pick: no focus ring
    s = O(report, "same_app")
    assert s["after"]["calls"] == [] and s["after"]["open"] is False          # the app already in view: nothing redone


def test_all_apps_row(report):
    a = O(report, "all_apps")
    r = rows(a["opened"]["list"])
    assert [x["sel"] for x in r] == [False, False, False, True, False, False]   # Puzzle Quest in view
    assert a["after"]["calls"] == [""] and a["after"]["APP"] == "" and a["after"]["sel"] == ""
    assert a["after"]["nm"] == "All apps (5)"


def test_typing_tab_outside_scrim_toggle(report):
    t = O(report, "type_on_button")
    assert t["open"] and t["q"] == "q" and t["prevented"] and t["stopped"] and t["focus"] == "apk-q"
    assert [x["name"] for x in rows(t["list"])] == ["Puzzle Quest"] and t["ad"] == "apk-o-3"
    assert t["space_prevented"] is False
    tab = O(report, "tab")
    assert tab["open"] is False and tab["focus"] == "apk-btn" and tab["prevented"] is False   # the browser's Tab moves on
    o = O(report, "outside")
    assert o["capture"] and o["inside"] is True and o["on_button"] is True   # inside the list / on the button: stays
    assert o["after"]["open"] is False and o["after"]["calls"] == []
    assert O(report, "scrim")["open"] is False and O(report, "scrim")["focus"] == "apk-btn"
    tb = O(report, "toggle_btn")
    assert tb["open"] is False and tb["focus"] == "apk-btn"


def test_touch_open_focuses_the_list(report):
    t = O(report, "touch_open")
    assert t["open"] and t["focus"] == "apk-list" and t["ad_list"] == "apk-o-0"
    assert t["type_goes_to_search"] == "apk-q"                                # a key on the list → the search box
    k = O(report, "keyboard_open_after_touch")
    assert k["open"] and k["focus"] == "apk-q"


def test_refresh_ghost_app_and_placement(report):
    r = O(report, "refresh_while_open")
    assert r["open"] is True and r["was"] == r["now"]                         # a 5-min refresh keeps the highlighted row
    g = O(report, "ghost")
    gr = rows(g["list"])
    assert gr[1]["name"] == "Ghost App" and gr[1]["sel"] and gr[1]["check"] == "✓" and gr[1]["icon"] == ("G", 20, None)
    assert len(gr) == 7
    p = O(report, "place")
    assert p == {"--apk-x": "880px", "--apk-y": "58px", "--apk-w": "340px", "--apk-mh": "460px"}


def test_topbar_markup_and_wiring():
    page, js = _page(), _script()
    # the button (ARIA), the hidden <select> kept for every reader, the Hinglish title kept
    assert ('<label class="ctrl" id="apk" for="apk-btn" style="cursor:pointer;gap:6px" '
            'title="Ek app choose karo — poora dashboard us app ka ho jayega">') in page
    assert '<select id="appsel" hidden tabindex="-1" aria-hidden="true"></select>' in page
    assert ('<button type="button" id="apk-btn" aria-haspopup="listbox" aria-expanded="false" aria-controls="apk-list">'
            '<span id="apk-nm">All apps</span><span class="apk-cv" aria-hidden="true">▾</span></button></label>') in page
    # render(): the <select> is still filled + its change listener kept; the picker wired once beside it
    assert "if(sel) sel.innerHTML=appSelHtml();\n  appSelIcon();" in js
    blk = js[js.index("if(!window.__wired){"):]
    blk = blk[:blk.index("\n  }\n")]
    assert "sel0.addEventListener('change',e=>setApp(e.target.value));" in blk and "apkWire();" in blk
    assert "apkSync(); }" in js[js.index("function appSelIcon(){"):js.index("function setApp(")]
    # a pick goes through setApp, nothing else
    pick = js[js.index("function apkPick("):js.index("function apkKey(")]
    assert pick.count("setApp(") == 1
    # styling: above the topbar / Studio headers / phone tab bar (z 90), below the drawers (1000); the phone sheet
    css = page[:page.index("</style>")]
    assert ".apk-pop{position:fixed;inset:0;z-index:90;pointer-events:none}" in css
    assert "@media(max-width:720px){" in css[css.index(".apk-none{"):]
