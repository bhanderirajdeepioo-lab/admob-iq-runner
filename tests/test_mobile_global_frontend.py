"""Dashboard-wide phone fixes from the two mobile audits (A: Uninstall + Active, B: Install value, other tabs, global chrome).

Run for real by tests/mobile_global_frontend.js (the page script in a node vm, a small DOM and a fake browser history) on a
SYNTHETIC dashboard made up there. Checked here:

  * B-18 Recommendations: an ad unit with 3 metrics out of its approved range is ONE placement — one row listing its metrics
    together, its weekly $ counted once on the card and in "Total opportunity" (which also counts a placement named by two
    cards once); the same in ₹;
  * B-11 the phone's Back button: the More menu, the App picker sheet, a Studio drawer, an app picked in the header (a Studio
    app page) each keep ONE history step. Back closes / leaves the top one; a close on the page takes its step off (no double
    Back); a close + an open in one tap reuse the step; re-opening (‹ ›) or switching apps adds none; a re-render adds none;
    a Forward onto a closed step is stepped back off; a Review #hash left on the base step is dropped;
  * B-13 the toast: pointer-events:none (a tap goes through it), above the phone tab bar, its buttons / links still tappable;
  * B-01 the trend chart: drawn at its real width under 700px (every label ≥ 10px), the 1000-unit drawing above;
  * B-12 Alerts: rule / channel status is read-only text ("✓ On" / "Off"), never a toggle; Telegram / Email from DATA.notify,
    which the build writes as booleans only (notify_status);
  * structural: the phone CSS (top bar, More menu above the tab bar, 16px fields, drawer safe-area), the Studio drawers' one-line
    Back hook, the Overview row name → App Report with a separate ↗ Play Store link, the "Google Ads installs" labels.
Skipped where node is not installed. No real data: every name, id and number is made up."""

import json
import os
import re
import shutil
import subprocess

import pytest

from admob_iq.build_static import notify_status

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


def _page():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        return f.read()


def _script():
    return max(re.findall(r"<script>(.*?)</script>", _page(), re.S), key=len)


def _css():
    return re.search(r"<style>(.*?)</style>", _page(), re.S).group(1)


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    if NODE is None:
        pytest.skip("node is not installed")
    path = str(tmp_path_factory.mktemp("mg_js") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_script())
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "mobile_global_frontend.js"), path],
                         check=True, capture_output=True, text=True, timeout=300)
    rep = json.loads(out.stdout)
    assert rep["errors"] == []
    return rep


def O(report, k):
    assert k in report["out"], (k, report["errors"])
    return report["out"][k]


def kpi(html, label):
    m = re.search(r'<div class="l">' + re.escape(label) + r'</div><div class="v">([^<]*)</div>', html)
    assert m, label
    return m.group(1)


def card(html, action):
    """The card of one action: its text from the action name to the next card."""
    i = html.index(action)
    j = html.find('<div class="card">', i)
    return html[i:j if j > 0 else len(html)]


# ── B-18 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
@needs_node
def test_reco_rows_one_per_placement(report):
    r = O(report, "reco_rows")
    rows = r["rows"]
    assert [x["place"] for x in rows] == ["splash_open", "home_banner"]          # 4 range alerts → 2 placements, $ first
    sp = rows[0]
    assert sp["n"] == 3 and sp["mets"] == ["ctr", "show", "ecpm"] and sp["rev"] == 7000
    assert sp["sub"].count(" · ") == 2 and "CTR 4.1%" in sp["sub"] and "Show rate 71.0%" in sp["sub"] and "eCPM $11.60" in sp["sub"]
    assert rows[1]["n"] == 1 and rows[1]["rev"] == 2100
    assert r["revCalls"] == 2                                                       # the money is looked up once per placement
    # without an ad-unit id: name + app is the key; the same message twice is listed once
    assert [(x["place"], x["app"], x["n"]) for x in r["byName"]] == [("x", "A", 1), ("x", "B", 1)]
    assert r["empty"] == []


@needs_node
def test_reco_totals_count_each_placement_once(report):
    assert O(report, "reco_totals") == {"total": 16, "placements": 3}             # "a" named by two cards: 10 once, not 20


@needs_node
def test_reco_screen_totals(report):
    html = O(report, "reco_screen")["html"]
    assert kpi(html, "Total opportunity") == "$9,800"                             # 7,000 + 2,100 + 700 (was $30,800)
    assert kpi(html, "Placements") == "3"
    rng = card(html, "Out of approved range — investigate")
    assert '<span class="pill p-b">2 placements</span>' in rng                    # was "4 placements"
    assert "$9,100" in rng and "$23,100" not in rng                               # 7,000 + 2,100 (was 3 × 7,000 + 2,100)
    assert rng.count("bGotoUnit(") == 2
    assert rng.count(">3 metrics</span>") == 1
    med = card(html, "Add mediation networks / enable bidding")
    assert '<span class="pill p-b">2 placements</span>' in med and "$7,700" in med
    one = O(report, "reco_screen")["html"]
    assert "1 placements" not in one


@needs_node
def test_reco_screen_inr(report):
    html = O(report, "reco_screen_inr")["html"]
    assert kpi(html, "Total opportunity") == "₹882,000"                           # 9,800 × 90
    assert "₹819,000" in card(html, "Out of approved range — investigate")        # 9,100 × 90


# ── B-11 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
@needs_node
def test_back_boot(report):
    assert O(report, "boot") == {"listeners": 1, "depth": 0, "st": 0}


@needs_node
def test_back_more_menu(report):
    o = O(report, "nav_open")
    assert o["open"] is True
    assert o["h"]["st"] == ["nav"] and o["h"]["state"] == {"iqb": 1} and o["h"]["len"] == 2
    assert o["h"]["calls"] == ["replace", "push"]                                 # the page's own step marked, then ONE push
    b = O(report, "nav_back")
    assert b["open"] is False and b["h"]["st"] == [] and b["h"]["depth"] == 0 and b["h"]["left"] is False


@needs_node
def test_back_close_on_page_takes_the_step_off(report):
    o = O(report, "nav_close_on_page")
    assert o["h"]["calls"] == ["go(-1)"] and o["h"]["idx"] == 0 and o["h"]["depth"] == 0
    assert o["after_extra_back"]["left"] is True                                  # the next Back leaves the page: no dead step
    t = O(report, "nav_toggle_twice")                                             # open + close in one task: nothing at all
    assert t["calls"] == [] and t["len"] == 1


@needs_node
def test_back_studio_drawer(report):
    o = O(report, "drawer")
    assert o["a"]["st"] == ["vs-drawer"] and o["a"]["depth"] == 1
    assert o["again"]["calls"] == [] and o["again"]["len"] == 2                   # ‹ › re-open: the same step
    assert o["b"]["st"] == [] and o["b"]["depth"] == 0 and o["closed"] == 1
    x = O(report, "drawer_x")
    assert x["h"]["calls"] == ["go(-1)"] and x["h"]["depth"] == 0 and x["closed"] == 0


@needs_node
def test_back_app_picked_in_header(report):
    o = O(report, "app_pick")
    assert o["sheet"]["st"] == ["apk"]
    assert o["picked"]["st"] == ["app"] and o["picked"]["calls"] == [] and o["picked"]["len"] == 2   # the sheet's step reused
    assert o["back"]["st"] == [] and o["APP"] == ""
    assert o["calls"][0] == "valBack"                                             # a Studio tab: its own "← All apps"
    ov = O(report, "app_back_overview")
    assert ov["APP"] == "" and ov["calls"] == ["render", "show:overview"] and ov["h"]["depth"] == 0
    aa = O(report, "app_all_apps_on_page")
    assert aa["APP"] == "" and aa["h"]["calls"] == ["go(-1)"] and aa["h"]["depth"] == 0
    sw = O(report, "app_switch")
    assert sw["st"] == ["app"] and sw["calls"] == [] and sw["len"] == 2


@needs_node
def test_back_stack_mute_forward_hash(report):
    s = O(report, "stack")
    assert s["two"]["st"] == ["app", "vs-drawer"] and s["two"]["len"] == 3
    assert s["one"]["u"] == ["drawer"] and s["one"]["h"]["st"] == ["app"]
    assert s["u"] == ["drawer", "app"] and s["zero"]["depth"] == 0
    assert O(report, "muted")["calls"] == []                                      # a re-render / refresh: no new step
    f = O(report, "forward")
    assert f["calls"] == ["go(-1)"] and f["idx"] == 0 and f["depth"] == 0
    r = O(report, "review_hash")
    assert r["open"]["hash"] == "#review"
    assert r["after"]["hash"] == "" and r["base_url"] == "/" and r["after"]["calls"] == ["go(-1)", "replace"]


@needs_node
def test_back_hooks_in_place(report):
    s = O(report, "structure")
    assert "uniBack()" in s["hbAppUndo"] and "actBack()" in s["hbAppUndo"] and "valBack()" in s["hbAppUndo"]
    assert "adBack()" in s["hbAdUndo"]
    assert "hbPush('apk'" in s["apkOpen"] and "<=720" in s["apkOpen"]             # only the phone bottom sheet
    assert "hbDrop('apk')" in s["apkClose"] and "hbDrop('appdetail')" in s["adBack"]


def test_back_hooks_structure():
    js = _script()
    for t in ("us", "as", "vs"):                                                  # the one-line hook in each Studio's lock()
        assert re.search(r"function lock\(on\)\{[^\n]*'%s-lock'[^\n]*hbOv\('%s-drawer',!!on,closeDrawer\)" % (t, t), js), t
    assert js.count("addEventListener('popstate',hbPop)") == 1
    assert "pushState" in js and "history.pushState(" not in js                   # every push goes through hbSync
    assert re.search(r"function rerender\(\)\{[^}]*HB\.mute\+\+", js)
    assert "function _navRestore(){ HB.mute++;" in js
    assert re.search(r"if\(_adcur!=='appdetail'&&!HB\.mute\)\{ AD_ORIGIN=_adcur; hbPush\('appdetail',hbAdUndo\); \}", js)
    assert "if(!was&&a) hbPush('app',hbAppUndo); else if(was&&!a) hbDrop('app');" in js


# ── B-13 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
@needs_node
def test_toast_lets_taps_through(report):
    t = O(report, "toast")
    assert t == {"css": "pointer-events:none", "role": "status", "text": "Saved", "inBody": True}


def test_toast_css():
    css = _css()
    box = re.search(r"#btoast\{position:fixed;[^}]*\}", css).group(0)
    assert "pointer-events:none" in box and "z-index:9999" in box and "env(safe-area-inset-bottom" in box
    assert "#btoast :is(a,button,[onclick]){pointer-events:auto}" in css
    assert re.search(r"@media\(max-width:760px\)\{ #btoast\{bottom:calc\(72px \+ env\(safe-area-inset-bottom,0px\)\)\} \}", css)


# ── B-01 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
@needs_node
def test_trend_chart_real_width(report):
    c = O(report, "chart")
    assert c["narrow"].startswith('<svg viewBox="0 0 319 ') and 'data-w="319"' in c["narrow"]
    sizes = [float(x) for x in re.findall(r'font-size="([\d.]+)"', c["narrow"])]
    assert sizes and min(sizes) >= 10.5                                           # was 13 units drawn at 0.32 = 4px
    assert c["wide"].startswith('<svg viewBox="0 0 1000 260"') and 'data-w="1000"' in c["wide"]
    assert c["phone"].startswith('<svg viewBox="0 0 319 ')                        # a 375px phone: the first guess
    assert c["guess"] == [976, 320]
    assert c["kept"] is True and re.fullmatch(r"btc\d+", c["id"])
    assert c["fit400"].startswith('<svg viewBox="0 0 400 ') and 'id="%s"' % c["id"] in c["fit400"]   # redrawn at its real width
    assert c["fit325"] is None and c["fit0"] is None                              # close enough / not on screen: left alone
    assert c["fit980"].startswith('<svg viewBox="0 0 1000 260"')                  # grew past 700px: the wide drawing again
    # the x labels at the ends stay inside the drawing
    for m in re.finditer(r'<text x="([\d.]+)" y="[\d.]+" text-anchor="(\w+)" font-size="11" fill="#8496b5">(\d+ \w+)</text>', c["narrow"]):
        x, an = float(m.group(1)), m.group(2)
        assert 0 <= x <= 319 and (an != "middle" or 18 <= x <= 301)


@needs_node
def test_trend_chart_date_labels_never_touch(report):
    c = O(report, "chart")
    for svg, W, fz, ch in ((c["wide30"], 1000, "12.5", 7.2), (c["narrow30"], 304, "11", 6.3)):
        labs = re.findall(r'<text x="([\d.]+)" y="[\d.]+" text-anchor="(\w+)" font-size="%s" fill="#8496b5">(\d+ \w+)</text>' % fz, svg)
        assert labs and labs[-1][2] == "30 Jan"                                   # the last day always has its label
        boxes = []
        for x, an, t in labs:
            x, w = float(x), len(t) * ch
            boxes.append((x - w / 2, x + w / 2) if an == "middle" else ((x, x + w) if an == "start" else (x - w, x)))
        assert all(0 <= a and b <= W for a, b in boxes)
        assert all(boxes[i][1] + 6 <= boxes[i + 1][0] + 1e-6 for i in range(len(boxes) - 1)), labs


def test_trend_chart_fitter_wired():
    js = _script()
    assert "function btcFit(sv)" in js and "new ResizeObserver(" in js and "new MutationObserver(" in js
    assert re.search(r"id=\"\$\{bk\}\" data-w=\"\$\{W\}\"", js)


# ── B-12 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
@needs_node
def test_alerts_notify_status_text(report):
    n = O(report, "notify")
    assert "—" in n["none"][0] and "agle data refresh" in n["none"][1]
    assert n["dry"][0] == '<span class="rst">Off</span>' and n["dry"][1] == '<span class="rst">Off</span>'
    assert "dry run" in n["dry"][2] and "koi message nahi jaata" in n["dry"][2]
    assert n["tg"][0] == '<span class="rst on">✓ On</span>' and n["tg"][1] == '<span class="rst">Off</span>'
    assert "setup baaki" in n["tg"][2]


def test_alerts_no_fake_switches():
    js = _script()
    body = js[js.index("function renderAlerts(){"):js.index("// ---------- DEDUCTIONS")]
    assert 'class="tgl"' not in body
    assert '<span class="rst on">✓ On</span>' in body and "ntSt('telegram')" in body and "ntSt('email')" in body


def test_notify_status_booleans_only():
    off = notify_status({"notify_dry_run": True, "telegram_token": "t0k", "telegram_chat": "c1",
                         "smtp": {"host": "smtp.example.test", "to": "a@example.test"}})
    assert off == {"dry_run": True, "telegram": False, "email": False}
    live = notify_status({"notify_dry_run": False, "telegram_token": "t0k", "telegram_chat": "c1",
                          "smtp": {"host": "smtp.example.test", "to": "a@example.test"}})
    assert live == {"dry_run": False, "telegram": True, "email": True}
    half = notify_status({"notify_dry_run": False, "telegram_token": "", "telegram_chat": "c1", "smtp": {"host": ""}})
    assert half == {"dry_run": False, "telegram": False, "email": False}
    assert notify_status({}) == {"dry_run": True, "telegram": False, "email": False}
    for v in (off, live, half):                                                   # never a secret, only booleans
        assert all(isinstance(x, bool) for x in v.values())


# ── phone CSS + Overview (structural) ─────────────────────────────────────────────────────────────────────────────────
def test_phone_css():
    css = _css()
    assert ".tb-ctl{display:contents}" in css                                     # desktop top bar exactly as before
    tb = css[css.index("@media(max-width:1000px){\n    .topbar{--tbx:24px"):]
    tb = tb[:tb.index("\n  }\n")]
    assert "overflow-x:auto" in tb and "min-height:34px" in tb and ".topbar .sub,.topbar .spacer{display:none}" in tb
    assert re.search(r"aside\{height:auto;bottom:calc\(58px \+ env\(safe-area-inset-bottom,0px\)\)", css)
    assert "body.nav-open{overflow:hidden}" in css
    assert re.search(r"input:not\(\[type=checkbox\]\)[^{]*,select,textarea\{font-size:16px!important\}", css)
    assert re.search(r"\.vs-dh\{padding-top:calc\(12px \+ env\(safe-area-inset-top,0px\)\)\}", css)
    assert re.search(r"\.vs-drawer\{padding-top:0\}", css)


def test_overview_row_name_opens_app_report():
    js = _script()
    row = js[js.index("const appRows=appsShown"):js.index("// mobile card-list of the SAME apps")]
    assert "openAppDetail(" in row and "appNm(ap2.name)" not in row and "storeLnk(ap2.name)" in row
    fn = js[js.index("function storeLnk(name)"):js.index("function appNm(name)")]
    assert 'class="stlnk"' in fn and 'target="_blank"' in fn and 'rel="noopener"' in fn and "event.stopPropagation()" in fn
    assert "app pe tap = poori report · ↗ = Play Store" in js
    assert re.search(r"\.stlnk\{[^}]*width:32px;height:32px", _css())


def test_overview_installs_labels():
    js = _script()
    assert "kpi('Google Ads installs'" in js and "kpi('Total installs'" not in js
    assert js.count("<th>Google Ads installs<div") == 2                           # the app table + the date-wise table
    assert "<b>all installs</b> (ads + organic)" in js
