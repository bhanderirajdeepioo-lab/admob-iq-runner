"""✨ App Hub — the new layout (BETA, off by default). Owner, 5 Oct 2026: pick an app and get ONE page for it, every feature a
tab inside it ("same tabs, scope switch": the header App picker = the scope; Home = a sticky tab bar hosting the existing
screens). Behind a switch: "✨ Try new layout (beta)" in the sidebar / the phone's More menu, or ?layout=hub.

Run for real by tests/hub_frontend.js (the page script in a node vm, a small DOM, a fake browser history; render() and the
lazy loaders are stand-ins) on SYNTHETIC data made up there. Checked here:
  * the app key = sha1(app_id)[:12] (the review / GA4 file key) — the page's own SHA-1 against hashlib; #home routes parsed;
  * routing: every screen id in both scopes and both states (in Home / on a left-nav page), the tab fallbacks;
  * the switch: off by default, ?layout=hub on + remembered + taken out of the URL, ?layout=classic off, a blocked
    localStorage never throws; OFF = the old layout: no hub class, no #home, the old "app" Back step, hubOv() untouched;
  * ON: Home, tabs, a picker change keeps the tab (Overview when the tab is not in the new scope), one Back step per tap
    (a re-tap adds none; an app + a tab in one tap = one), Back / Forward walk the steps with their own #home URLs;
  * old screen names map to the tab of the scope in view; left-nav pages leave Home; Home returns to the last tab;
  * refresh / bookmarks (#home/<key>/<tab>), an unknown app / tab falls back, a same-view rebuild adds no step, navstate;
  * switching off live: no bar, no #home, the tab steps gone; on again;
  * the App Overview cards: a status word + one key line per feature (Review card statuses mapped to the owner's words,
    the eCPM tab's own status, Audience, Baseline, Alerts, Movers), money in $ and ₹, an app missing from the card, loading;
  * structure: the markup (switch, hub nav, tab bar, phone bar), the hooks, the CSS outside the Studios' scoped blocks.
Skipped where node is not installed. No real data: every name, id and URL is made up."""

import hashlib
import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")
IDS = {"big": "ca-app-pub-0000000000000001~1000000001", "small": "ca-app-pub-0000000000000002~2000000002",
       "noga": "ca-app-pub-0000000000000003~3000000003"}
key = lambda app_id: hashlib.sha1(app_id.encode()).hexdigest()[:12]


def _page():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        return f.read()


def _script():
    return max(re.findall(r"<script>(.*?)</script>", _page(), re.S), key=len)


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("hub_js") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_script())
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "hub_frontend.js"), path],
                         check=True, capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout)


def O(report, k):
    assert not report["errors"], report["errors"]
    assert k in report["out"], (k, report["errors"])
    return report["out"][k]


@needs_node
def test_keys_and_routes(report):
    k = O(report, "keys")
    assert k["abc"] == hashlib.sha1(b"abc").hexdigest() and k["empty"] == hashlib.sha1(b"").hexdigest()
    assert k["long"] == hashlib.sha1(b"a" * 1000).hexdigest() and k["utf8"] == hashlib.sha1("₹ जी".encode()).hexdigest()
    assert (k["big"], k["small"], k["noga"], k["all"]) == (key(IDS["big"]), key(IDS["small"]), key(IDS["noga"]), "all")
    assert k["back"] == ["Demo Gallery", "", None]
    assert k["parse"] == [{"key": "all", "tab": "active"}, {"key": "all", "tab": ""}, {"key": "abc123", "tab": ""}, None, None, None]
    assert k["tabsAll"] == ["overview", "revenue", "ecpm", "active", "uninstall", "value", "mediation", "roas", "baseline",
                            "deductions", "health", "movers"]                                   # (no Audience file in this build)
    assert k["tabsApp"] == ["overview", "revenue", "ecpm", "active", "uninstall", "value", "baseline", "alerts", "review",
                            "mediation", "roas", "deductions", "health", "movers"]


@needs_node
def test_resolve_every_screen(report):
    r = O(report, "resolve")
    T, F = True, False
    want = {
        "all|in|home": [T, "active", "active"], "all|in|overview": [T, "overview", "overview"],
        "all|in|placements": [T, "revenue", "placements"], "all|in|appdetail": [T, "revenue", "placements"],
        "all|in|ecpm": [T, "ecpm", "ecpm"], "all|in|movers": [T, "movers", "movers"], "all|in|health": [T, "health", "health"],
        "all|in|alerts": [F, "active", "alerts"], "all|out|alerts": [F, "active", "alerts"],      # All apps: Alerts = the page
        "all|in|review": [F, "active", "review"], "all|in|reco": [F, "active", "reco"], "all|in|settings": [F, "active", "settings"],
        "all|in|hubrv": [T, "active", "active"],                                                   # no Review history at All apps
        "all|in|datewise": [T, "active", "datewise"], "all|out|datewise": [T, "overview", "datewise"],
        "all|in|reportcard": [T, "active", "reportcard"], "all|out|reportcard": [T, "revenue", "reportcard"],
        "all|out|countries": [T, "overview", "countries"], "all|out|active": [T, "active", "active"],
        "app|in|appdetail": [T, "revenue", "appdetail"], "app|in|placements": [T, "revenue", "appdetail"],
        "app|in|alerts": [T, "alerts", "alerts"], "app|out|alerts": [F, "active", "alerts"],      # an app's tab only from Home
        "app|in|hubrv": [T, "review", "hubrv"], "app|in|review": [F, "active", "review"],
        "app|in|value": [T, "value", "value"], "app|out|uninstall": [T, "uninstall", "uninstall"],
        "app|in|audience": [T, "active", "active"],                                                # no Audience file: no tab
        "app|in|home@alerts": [T, "alerts", "alerts"], "all|in|home@alerts": [T, "overview", "overview"],
        "all|in|appdetail@revenue": [T, "revenue", "placements"], "app|in|placements@revenue": [T, "revenue", "appdetail"],
        "all|in|datewise@movers": [T, "movers", "datewise"],
    }
    for k, v in want.items():
        assert r[k] == v, (k, r[k], v)


@needs_node
def test_switch(report):
    d = O(report, "switch_default_off")
    assert (d["on"], d["hubOn"], d["bar"], d["inHub"], d["ls"], d["hash"], d["calls"]) == (False, False, False, False, None, "", [])
    p = O(report, "switch_param_on")
    assert p["on"] and p["hubOn"] and p["hubIn"] and p["bar"] and p["ls"] == "hub" and p["sw"] == ["true", "On"]
    assert p["url"] == "/?x=1#home/all/overview"                                     # the param leaves the URL, others stay
    assert O(report, "switch_stored") == {"on": True, "ls": "hub"}
    assert O(report, "switch_param_off") == {"on": False, "ls": None, "url": "/"}
    assert O(report, "switch_storage_blocked") == {"threw": None, "on": True}           # a blocked localStorage: on for the session


@needs_node
def test_off_is_the_old_layout(report):
    o = O(report, "off_untouched")
    for s in (o["a"], o["b"], o["c"]):
        assert not s["on"] and not s["hubOn"] and not s["hubIn"] and not s["bar"] and not s["inHub"]
    assert o["a"]["scr"] == "active" and o["c"]["scr"] == "alerts" and o["b"]["app"] == "Demo Gallery"
    assert o["b"]["st"] == ["app"] and o["hash"] == "" and all("#home" not in u for u in o["urls"])   # the old "← All apps" step
    assert o["ov"] is True


@needs_node
def test_walk_back_forward(report):
    w = O(report, "on_walk")
    L = {x["n"]: x for x in w["L"]}
    kb, ks = key(IDS["big"]), key(IDS["small"])
    exp = {"home": ("", "overview", "overview", "#home/all/overview", 1),
           "movers": ("", "movers", "movers", "#home/all/movers", 2),
           "movers-again": ("", "movers", "movers", "#home/all/movers", 2),            # a re-tap: no new step
           "pick-app": ("Demo Gallery", "movers", "movers", f"#home/{kb}/movers", 3),   # the picker keeps the tab
           "alerts": ("Demo Gallery", "alerts", "alerts", f"#home/{kb}/alerts", 4),
           "revenue": ("Demo Gallery", "revenue", "appdetail", f"#home/{kb}/revenue", 5),
           "review": ("Demo Gallery", "review", "hubrv", f"#home/{kb}/review", 6),
           "pick-all": ("", "overview", "overview", "#home/all/overview", 7)}          # Review history not at All → Overview
    for n, (app, tab, scr, h, ln) in exp.items():
        x = L[n]
        assert (x["app"], x["tab"], x["scr"], x["hash"], x["len"], x["inHub"], x["bar"]) == (app, tab, scr, h, ln, True, True), (n, x)
    back = [("back1", "review", 5), ("back2", "revenue", 4), ("back3", "alerts", 3), ("back4", "movers", 2)]
    for n, tab, idx in back:
        x = L[n]
        assert (x["app"], x["tab"], x["idx"], x["hash"]) == ("Demo Gallery", tab, idx, f"#home/{kb}/{tab}"), (n, x)
    assert (L["fwd1"]["tab"], L["fwd1"]["idx"], L["fwd2"]["tab"], L["fwd2"]["scr"], L["fwd2"]["idx"]) == ("alerts", 3, "revenue", "appdetail", 4)
    g = L["go-small-value"]                                                             # app + tab in one tap = ONE step
    assert (g["app"], g["tab"], g["scr"], g["hash"], g["idx"], g["len"]) == ("Puzzle Quest", "value", "value", f"#home/{ks}/value", 5, 6)
    assert len(g["st"]) == g["depth"] == 5 and all(t.startswith("hub") for t in g["st"])
    assert w["ad"] and set(w["ad"]) == {"Demo Gallery"}                                 # the app's report drawn by openAppDetail


@needs_node
def test_old_screen_names(report):
    r = O(report, "old_names")
    for sc in ("active", "uninstall", "value", "baseline", "mediation", "alerts", "ecpm"):
        assert (r[sc]["app"], r[sc]["tab"], r[sc]["scr"], r[sc]["inHub"]) == ("Demo Gallery", sc, sc, True), sc
    assert (r["placements"]["tab"], r["placements"]["scr"]) == ("revenue", "appdetail")
    assert (r["datewise"]["tab"], r["datewise"]["scr"], r["datewise"]["inHub"]) == ("ecpm", "datewise", True)   # a drill page
    assert (r["toAll"]["app"], r["toAll"]["tab"]) == ("", "ecpm")
    assert (r["alertsAll"]["scr"], r["alertsAll"]["inHub"], r["alertsAll"]["bar"]) == ("alerts", False, False)
    assert (r["reco"]["scr"], r["reco"]["inHub"], r["reco"]["bar"], r["reco"]["hash"]) == ("reco", False, False, "")
    assert (r["home"]["tab"], r["home"]["inHub"], r["home"]["hash"]) == ("ecpm", True, "#home/all/ecpm")      # Home = the last tab
    assert (r["appdetail"]["app"], r["appdetail"]["tab"], r["appdetail"]["scr"]) == ("Puzzle Quest", "revenue", "appdetail")
    assert (r["ovList"]["app"], r["ovList"]["tab"], r["ovList"]["scr"]) == ("Tiny Notes", "overview", "overview")   # Overview's list


@needs_node
def test_app_report_controls_stay_put(report):
    r = O(report, "appreport_controls")
    assert r["on"]["keep"] == [1, 1, 1, 1] and r["on"]["keepAfter"] == 0 and set(r["on"]["ad"]) == {"Demo Gallery"}
    assert (r["on"]["st"]["tab"], r["on"]["st"]["scr"], r["on"]["st"]["depth"]) == ("revenue", "appdetail", 1)   # no extra Back step
    assert r["off"] == {"keep": [1, 1], "keepAfter": 0}                                                          # off too: no jump (owner, 4 Oct)


@needs_node
def test_refresh_and_bookmarks(report):
    r = O(report, "refresh")
    ks = key(IDS["small"])
    assert r["k"] == ks
    assert (r["a"]["app"], r["a"]["tab"], r["a"]["scr"], r["a"]["hash"], r["a"]["depth"]) == ("Puzzle Quest", "uninstall", "uninstall", f"#home/{ks}/uninstall", 0)
    assert (r["b"]["app"], r["b"]["tab"], r["b"]["scr"]) == ("", "movers", "movers")
    assert (r["c"]["app"], r["c"]["tab"], r["c"]["hash"]) == ("", "active", "#home/all/active")                  # unknown app → All
    assert (r["d"]["app"], r["d"]["tab"], r["d"]["hash"]) == ("Puzzle Quest", "overview", f"#home/{ks}/overview")  # unknown tab
    assert not r["e"]["on"] and not r["e"]["hubOn"] and r["e"]["hash"] == "" and r["e"]["app"] == ""            # off: ignored + dropped
    assert (r["f"]["tab"], r["f"]["scr"], r["f"]["steps"], r["f"]["hash"]) == ("value", "value", 0, f"#home/{ks}/value")   # rebuild
    assert (r["g"]["app"], r["g"]["tab"], r["g"]["scr"], r["g"]["inHub"]) == ("", "active", "active", True)


@needs_node
def test_switch_off_live(report):
    r = O(report, "switch_off_live")
    assert r["before"]["hubOn"] and r["before"]["depth"] == 2 and r["before"]["hash"].startswith("#home/")
    a = r["after"]
    assert (a["on"], a["hubOn"], a["bar"], a["hash"], a["ls"], a["depth"], a["st"], a["scr"]) == (False, False, False, "", None, 0, [], "active")
    assert not r["later"]["hubOn"] and r["later"]["hash"] == "" and r["later"]["scr"] == "uninstall"
    g = r["again"]
    assert g["on"] and g["inHub"] and g["bar"] and g["tab"] == "uninstall" and g["hash"].endswith("/uninstall")


@needs_node
def test_app_overview_cards(report):
    c = O(report, "cards")
    usd = {x["id"]: x for x in c["usd"]}
    order = [x["id"] for x in c["usd"]]
    assert order == ["revenue", "ecpm", "active", "uninstall", "update", "value", "audience", "baseline", "alerts", "review",
                     "mediation", "roas", "deductions", "health", "movers"]
    st = {k: (v["st"], v["chip"]) for k, v in usd.items()}
    assert st == {"revenue": ("dhyan", "🟡 Watch"), "ecpm": ("bigda", "🔴 Worse"), "active": ("bigda", "🔴 Worse"),
                  "uninstall": ("normal", "⚪ Normal"), "update": ("jaldi", "⏳ Too early"), "value": ("behtar", "🟢 Better"),
                  "audience": ("info", "ℹ️ Info"), "baseline": ("dhyan", "🟡 Watch"), "alerts": ("bigda", "🔴 Worse"),
                  "review": ("bigda", "🔴 Worse"), "mediation": ("normal", "⚪ Normal"), "roas": ("lagu", "— N/A"),
                  "deductions": ("normal", "⚪ Normal"), "health": ("lagu", "— N/A"), "movers": ("info", "ℹ️ Info")}
    tabs = {k: v["tab"] for k, v in usd.items()}
    assert tabs["update"] == "uninstall" and tabs["roas"] == "roas" and all(tabs[k] == k for k in tabs if k != "update")
    d = c["day"]
    assert usd["revenue"]["line"] == "Splash show rate 71%, range 80%–84%"
    assert re.fullmatch(r"\$2\.80 on \d+ \w+ · 7-day avg \$3\.\d\d \(−2\d\.\d%\)", usd["ecpm"]["line"]), usd["ecpm"]["line"]
    assert usd["audience"]["line"] == "2.6M sleeping · ⚠️ 524K danger zone · 📲 707K push se"
    assert usd["baseline"]["line"] == "1 ad unit outside approved range · splash_open"
    assert usd["alerts"]["line"] == "3 open · ad units 2 (~$13/day loss) · users 1"                # ad + range + one GA4 "watch"
    assert usd["review"]["line"].endswith(": 1 Worse · 1 Watch")
    assert usd["deductions"]["line"] == "$4.2 deducted by AdMob · under 0.1% of revenue"
    assert usd["health"]["line"] == "No data"
    assert re.match(r"−\$\d[\d,]* last 7 days vs 7 before \(−\d+%\) · top: splash_open −\$\d", usd["movers"]["line"])
    inr = {x["id"]: x for x in c["inr"]}
    assert inr["deductions"]["line"] == "₹378 deducted by AdMob · under 0.1% of revenue"               # the card file's own rate
    assert inr["alerts"]["line"] == "3 open · ad units 2 (~₹1,125/day loss) · users 1"
    assert inr["ecpm"]["line"].startswith("₹252.00 on ") and [x["st"] for x in c["inr"]] == [x["st"] for x in c["usd"]]
    small = {x["id"]: x for x in c["small"]}
    assert small["revenue"]["st"] == "lagu" and small["revenue"]["line"].startswith("Not in the ") and small["revenue"]["line"].endswith(" Review card")
    assert (small["alerts"]["st"], small["alerts"]["line"]) == ("normal", "0 open alerts")
    assert (small["baseline"]["st"], small["baseline"]["line"]) == ("normal", "1 ad unit with a range · all inside")
    assert small["audience"]["st"] == "lagu"
    none = {x["id"]: x for x in c["none"]}                                                         # the card file still loading
    assert none["revenue"]["line"] == "⏳ loading…" and none["ecpm"]["st"] == "bigda"
    h = c["head"]
    assert h.strip().startswith("🅐 pub-0000000000000001 · AdMob till ") and "Demo Gallery" not in h[:h.index("Yesterday")]   # the logo + name: in the title only
    assert "💵 Revenue · " in h and "usual $" in h and "/day (−" in h
    assert "👥 DAU 123,456" in h and "GA4 · not final" in h and "🔔 Open alerts 3 ad units 2 · users 1" in h and "Features" in h
    assert h.index("Yesterday") < h.index("💵 Revenue · Yesterday") < h.index("📈 eCPM · Yesterday") < h.index("Features")   # the app's KPIs first, then Features
    # owner: "5 Oct me Yesterday likho, 6 me Today": the last full day = Yesterday; the Period caption names the period (Today …)
    assert re.search(r"Yesterday \d{1,2} [A-Z][a-z]{2} ", h) and re.search(r" (Today|Yesterday|Last 7 days|Last 30 days|This month|All time|Custom) ", h[h.index("📈 eCPM"):h.index("Features")])
    assert c["ov"] == {"same": True, "kids": 1, "id": "hub-ov"} and c["ovAll"] == 0                  # All apps: no app head


def test_back_arrow_out_of_an_app(report):
    r = O(report, "exit")
    assert not r["home"]["back"] and r["inApp"]["back"] and r["inApp"]["app"] == "Demo Gallery"   # All apps: no ←; inside an app: shown
    o = r["out1"]                                                   # opened from the All-apps Overview, left from its eCPM tab
    assert (o["app"], o["inHub"], o["tab"], o["scr"], o["back"], o["hash"], o["y"]) == ("", True, "overview", "overview", False, "#home/all/overview", 1500)
    assert (r["back1"]["app"], r["back1"]["tab"], r["back1"]["back"]) == ("Demo Gallery", "ecpm", True)   # phone Back: into the app again
    assert (r["out2"]["app"], r["out2"]["tab"], r["out2"]["scr"], r["out2"]["y"]) == ("", "active", "active", 800)   # from All apps' Active users
    assert r["bm"]["back"] and (r["out3"]["app"], r["out3"]["tab"], r["out3"]["scr"]) == ("", "ecpm", "ecpm") and not r["out3"]["y"]   # a bookmark: same tab
    assert (r["out4"]["app"], r["out4"]["tab"], r["out4"]["scr"]) == ("", "overview", "overview")   # an app-only tab → All apps' Overview
    assert not r["classic"]["back"] and r["classic2"]["app"] == "Demo Gallery"   # the old layout: no ←, hubExit does nothing
    # the App picker: inside an app (hub) only "Change app" (the title names the app, its logo once); elsewhere the app / All apps
    assert (r["inApp"]["pk"], r["inApp"]["pkIc"], r["inApp"]["hubApp"]) == ("Change app", False, True)
    assert r["home"]["pk"].startswith("All apps") and not r["home"]["hubApp"] and not r["out1"]["hubApp"] and r["out1"]["pk"].startswith("All apps")
    assert (r["classic"]["pk"], r["classic"]["pkIc"], r["classic"]["hubApp"]) == ("Demo Gallery", True, False)
    # the open app's own logo inside the pages: hidden by one rule (the title keeps it); other apps' logos untouched; off outside an app
    assert r["inApp"]["ico"] == ('body.hub-app .screen .aicon[data-ian="Demo Gallery"],'                # by name, and by its app id
                                 'body.hub-app .screen .aicon[data-iid="ca-app-pub-0000000000000001~1000000001"]{display:none!important}')
    assert r["home"]["ico"] == "" and r["out1"]["ico"] == "" and r["classic"]["ico"] == ""
    assert r["esc"] == 'body.hub-app .screen .aicon[data-ian="Say \\"Hi\\" \\\\ ok"]{display:none!important}'   # a quote / backslash in a name
    assert ' data-ian="Demo Gallery" data-l="D" ' in r["icon"]
    assert ' data-ian="Demo Gallery" data-iid="ca-app-pub-0000000000000001~1000000001" data-l="D" ' in r["iconId"]   # a Studio's icon, by id


def test_structure():
    page, js = _page(), _script()
    # the switch: a labelled role=switch in the sidebar (= the phone's More menu), default Off
    assert re.search(r'<button type="button" id="hub-beta" role="switch" aria-checked="false" onclick="hubToggle\(\)">.*✨ Try new layout'
                     r'<span class="hbb">beta</span>.*<span class="hbs" id="hub-beta-s">Off</span></button>', page)
    aside = page[page.index("<aside>"):page.index("</aside>")]
    assert 'id="hub-beta"' in aside and '<div class="nav-classic">' in aside
    assert aside.index('class="brand"') < aside.index('id="hub-beta"') < aside.index('class="hub-nav"') < aside.index('class="nav-classic"')   # seen without scrolling
    hub_nav = aside[aside.index('<div class="hub-nav"'):aside.index('<div class="nav-classic">')]
    assert re.findall(r'data-hnav="(\w+)"', hub_nav) == ["review", "home", "alerts", "reco", "settings"]
    assert 'id="nav-review-h"' in hub_nav and 'id="nav-alert-h"' in hub_nav
    top = page[page.index('<div class="topbar">'):page.index('<div class="content" id="content">')]
    assert '<div class="hub-bar" id="hub-bar" role="tablist" aria-label="App tabs" hidden onkeydown="hubBarKey(event)"></div>' in top
    assert re.search(r'<button type="button" class="hub-back" id="hub-back" hidden onclick="hubExit\(\)"[^>]*aria-label="Back to All apps">'
                     r'<span class="hbk-a" aria-hidden="true">←</span><span class="hbk-t">All apps</span></button>', top)
    assert top.index('id="hub-back"') < top.index('id="tb-title"')                                   # the ← sits before the app's name
    bot = page[page.index('<nav class="botbar"'):page.index("</nav>", page.index('<nav class="botbar"'))]
    assert "navTap('review')" in bot and "navTap('alerts')" in bot and 'data-hnav="home"' in bot and 'data-hnav="reco"' in bot
    assert bot.count('class="tabbtn hub-x"') == 2
    # the hooks: off = return early everywhere
    assert "if(HUB.on&&!HUB.hold){ id=hubPre(id); if(id==null) return; }" in js and "if(HUB.on&&!HUB.hold) hubPost(id);" in js
    assert "HUB.hold++; try{ show('overview'); }finally{ HUB.hold--; }" in js
    assert "root.append(hubOv(renderOverview()),renderPlacements()," in js and "if(HUB.on) root.append(renderHubRv());" in js
    assert "document.querySelectorAll('.nav button[data-screen]').forEach(b=>b.addEventListener('click',()=>show(b.dataset.screen)));" in js
    assert "function openAppDetail(name){\n  if(hubOpenApp(name)) return;" in js and "if(HUB.on) hubPost('appdetail');" in js
    assert "if(HUB.on&&HUB.inHub){ render(); show(hubHost(" in js and "if(HUB.on) return;   // ✨ hub (a page outside Home)" in js
    assert "if((n<0||d==null)&&typeof HUB!=='undefined'&&HUB.on&&hubPop(d,nd)) return;" in js
    assert "if(x&&x.hub&&x.url!=null) H.pushState({iqb:HB.depth+1},'',location.pathname+location.search+x.url); else H.pushState({iqb:HB.depth+1},'');" in js
    assert "if(!HUB.on) hbOv('ecpm',true,ecUndo); show('ecpm'); }" in js
    assert "function adRedraw(){ if(!ADAPP) return; SP.keep++; try{ openAppDetail(ADAPP); }finally{ SP.keep--; } }" in js
    for f in ("function adSetView(v){ ADVIEW=v; adRedraw(); }", "function adDWin(w){ ADRANGE=w; adRedraw(); }"):
        assert f in js
    assert "hubInit();" in js and js.index("hubInit();") < js.index("_navRestore();                           // restore the LAST")
    assert js.index("hubBoot();") > js.index("_navRestore();                           // restore the LAST") and "hubReady();" in js
    assert "function hubLsGet(){ try{ return localStorage.getItem(HUB_LS); }catch(e){ return null; } }" in js
    assert "function hubLsSet(v){ try{" in js
    # the hub's CSS is its own block, before the Review Studio's scoped CSS (never inside a Studio's block)
    css = page[page.index("<style>"):page.index("</style>")]
    i = css.index("/* ✨ App Hub (new layout, BETA"); assert i < css.index("/* ===== 🗂 REVIEW STUDIO")
    assert ".hub-nav{display:none}" in css and "body.hub-on .nav-classic{display:none}" in css and ".hub-bar[hidden]{display:none}" in css
    assert "overflow-x:auto" in css[css.index(".hub-bar{"):css.index(".hub-bar[hidden]")]       # the bar scrolls in its own box


def test_today_yesterday_labels(report):
    r = O(report, "labels")
    T, Y, L = r["T"], r["Y"], r["L"]
    assert r["rel"] == ["Today", "Yesterday", ""]
    assert L["today"] == {"lbl": "Today · " + T + " · live", "dates": T + " · live", "name": "Today"}
    assert L["yesterday"] == {"lbl": "Yesterday · " + Y, "dates": Y, "name": "Yesterday"}
    assert L["7d"]["name"] == "Last 7 days" and L["7d"]["lbl"].endswith(" · 7d") and "Today" not in L["7d"]["lbl"] and L["7d"]["dates"] == L["7d"]["lbl"]
