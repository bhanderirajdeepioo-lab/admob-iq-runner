"""App icons everywhere (owner: "sab jagah app ka icon aana chahiye — pure dashboard me check kro and add kro").

Rendered for real by tests/app_icons_frontend.js (the page script in a node vm) on a synthetic Uninstall Studio site the
REAL build code made (tests/studio_synth.py — two same-named "Demo Gallery" apps in one account) with SYNTHETIC icon URLs,
and on the committed synthetic Review fixture. Checked here:

  * appIconId: an app's OWN icon by app_id — a same-named twin never borrows it (letter-avatar instead), no id → by name,
    a junk URL → letter-avatar; lazy + async, decoration only (aria-hidden, alt="", the letter drawn by CSS — no text);
  * the Studio: the map / table / story / alert cards / drawer header (28px) / full app page header (32px) / tooltips all
    put the app's own icon beside its name, and the "bina GA4" twin shows a letter, not its cousin's logo;
  * the Review card heading and the Summary lines carry the app's icon (by its app_id);
  * structural: the other Studios' name helpers and headers, the tabs' name spots and the header App selector.
Skipped where node is not installed. No real data: every name, id and URL is made up."""

import gzip
import json
import os
import re
import shutil
import subprocess

import pytest

from admob_iq import build_static
from admob_iq import uninstall_studio_build as usb
from admob_iq.config import settings
from tests import studio_synth as ss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
ICON = {ss.G1: "https://icons.example.test/g1.png", ss.N1: "https://icons.example.test/n1.png"}
TAG = re.compile(r"<[^>]*>")


def _page():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        return f.read()


def _script():
    return max(re.findall(r"<script>(.*?)</script>", _page(), re.S), key=len)


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("icons_fe"))
    site, _, dash = ss.make_site(root)
    assert build_static._studio_step(dash, os.path.join(root, "data"), site, dict(settings())) == ["/uninstall_studio.json.gz", "/uninstall_studio_old.json.gz"]
    dash["app_icons"] = dict(ICON)
    fx = os.path.join(root, "fx")
    os.makedirs(fx)
    with gzip.open(os.path.join(site, usb.FILE), "rt", encoding="utf-8") as f:
        studio = json.load(f)
    with gzip.open(os.path.join(site, "uninstall.json.gz"), "rt", encoding="utf-8") as f:
        uni = json.load(f)
    for name, body in (("dashboard.json", dash), ("uninstall_studio.json", studio), ("uninstall.json", uni)):
        with open(os.path.join(fx, name), "w", encoding="utf-8") as f:
            json.dump(body, f)
    path = str(tmp_path_factory.mktemp("icons_js") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_script())
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "app_icons_frontend.js"), path, fx,
                          os.path.join(ROOT, "tests", "fixtures", "review_sample.json")],
                         check=True, capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout)


def J(report, k):
    assert k in report["out"], (k, report["errors"])
    return json.loads(report["out"][k])


def _icons(h):
    """[(size, url or None, letter)] for every app icon in an html string, in order."""
    out = []
    for m in re.finditer(r'<span class="aicon[^"]*" aria-hidden="true" data-l="([^"]*)" style="width:(\d+)px[^"]*">(<img src="([^"]*)"[^>]*>)?</span>', h):
        out.append((int(m.group(2)), m.group(4), m.group(1)))
    return out


def test_renders_without_errors(report):
    assert report["errors"] == []


def test_icon_by_app_id_never_borrows_a_same_named_cousins_logo(report):
    h = J(report, "helpers")
    assert _icons(h["own"]) == [(16, "https://icons.example.test/one.png", "S")]
    for k in ("own", "inline", "big"):                                           # lazy, async, decoration only
        assert 'loading="lazy"' in h[k] and 'decoding="async"' in h[k] and 'alt=""' in h[k] and 'aria-hidden="true"' in h[k]
    assert _icons(h["twin"]) == [(16, None, "S")] and "one.png" not in h["twin"]   # same name, no logo of its own → letter
    assert "aicon-l" in h["twin"] and "<img" not in h["twin"]
    assert _icons(h["unknown"]) == [(20, None, "Z")]
    assert _icons(h["no_id"]) == _icons(h["by_name"]) == [(16, "https://icons.example.test/one.png", "S")]   # by name: its top app
    assert "<img" not in h["bad"] and "javascript" not in h["bad"]               # a junk URL is never used
    assert 'class="aicon ail"' in h["inline"] and _icons(h["big"])[0][0] == 32
    for k in ("own", "twin", "unknown", "bad"):                                  # the letter is CSS (data-l): no text node
        assert TAG.sub("", h[k]).strip() == ""
    assert "one.png" not in h["chip"] and TAG.sub(" ", h["chip"]).split() == ["Same", "Name"]   # appChip(name,size,id)
    assert "one.png" in h["chip_name"]
    assert h["sel_all"] == "📱" and _icons(h["sel_app"]) == [(18, "https://icons.example.test/one.png", "S")]


def test_the_studio_puts_each_apps_own_icon_beside_its_name(report):
    s = J(report, "studio")
    ids = {a["i"]: a["id"] for a in s["apps"]}
    assert ss.G1 in ids.values() and any(n["id"] == ss.G2 for n in s["noga"])   # the same-named pair is on screen
    # every name in the map, the table and the story is an icon + the name, the icon first
    for k in ("map", "tbl", "story"):
        names = re.findall(r'<span class="us-nmt us-ain">(<span class="aicon[^>]*>(?:<img[^>]*>)?</span>)<span class="us-aint">', s[k])
        assert names, k
        assert len(names) == s[k].count('class="us-nmt'), k
    rows = re.findall(r'data-go="(\d+)" data-tk="app:\d+">(<span class="us-nmt us-ain">.*?</span>)<span class="us-aint">', s["map"])
    assert len(rows) == len(s["apps"])
    for i, h in rows:
        want = ICON.get(ids[int(i)])
        assert _icons(h)[0][:2] == (16, want), (ids[int(i)], h)
    # the "bina GA4" twin of Demo Gallery: its own (letter) icon, never the GA4 twin's logo
    twin = re.search(r'<span class="us-nmt us-ain">(<span class="aicon[^>]*>(?:<img[^>]*>)?</span>)<span class="us-aint">Demo Gallery <span class="us-acn">· Studio One</span></span></span></div></div></td><td class="us-l">', s["tbl"])
    assert twin and _icons(twin.group(1)) == [(16, None, "D")]
    # the drawer header (28px) and the full app page header (32px), the app's own icon
    assert re.search(r'<h3 class="us-ainb"><span class="aicon[^"]*" aria-hidden="true" data-l="[^"]*" style="width:28px', s["drawer"])
    assert re.search(r'<h2 class="us-pgt us-ainb"><span class="aicon[^"]*" aria-hidden="true" data-l="[^"]*" style="width:32px', s["page"])
    assert _icons(s["page"])[0][1] == ICON.get(s["apps"][0]["id"])
    # a tooltip names its app with a small inline icon
    assert re.match(r'<div class="us-tt"><span class="aicon ail[^"]*" aria-hidden="true" data-l="[^"]*" style="width:14px', s["tip_app"])
    # every alert card's app line
    cards = re.findall(r'<div class="us-app us-ainb">(<span class="aicon[^>]*>(?:<img[^>]*>)?</span>)', s["chg"])
    assert len(cards) == s["chg"].count('class="us-app')


def test_the_review_cards_and_summary_name_apps_with_their_icon(report):
    r = J(report, "review")
    for k in r["keys"]:
        head = re.search(r'<h3 class="rv-app" id="rv-t-h-' + re.escape(k) + r'">(.*?)</h3>', r["cards"][k])
        assert head and head.group(1).startswith('<span class="aicon ail'), k
        assert (_icons(head.group(1))[0][1] == "https://icons.example.test/review.png") == (k == r["first"])
        assert _icons(head.group(1))[0][0] == 22
    jumps = re.findall(r'<button type="button" class="rv-jump" data-rvjump="[^"]*">(.*?)</button>', r["summary"])
    assert jumps and all(j.startswith('<span class="aicon ail') for j in jumps if not j.startswith("Open card"))
    assert all(p.startswith('⏳ <span class="aicon ail') for p in re.findall(r'class="rv-pill rv-pend" data-rvjump="[^"]*">(.*?)</button>', r["summary"]))
    assert all(s.endswith('</span>') for s in re.findall(r'</span>(<span class="aicon ail[^>]*>(?:<img[^>]*>)?</span>)<span class="rv-an">', r["summary"]))


def test_every_name_helper_and_header_carries_the_icon():
    js = _script()
    for P in ("as", "vs"):                                                   # the other two Studios: same helpers
        blk = js[js.index("const %s=(function(){" % P.upper()):]
        assert re.search(r"const ic=\(a,s,c\)=>appIconId\(a\.id,", blk)
        assert 'const nmH=a=>`<span class="%s-nmt %s-ain">${ic(a,16)}' % (P, P) in blk
        assert '<div class="%s-app %s-ainb">${ic(a,18)}' % (P, P) in blk
        assert '<span class="%s-lk" data-go="${a.i}">${ic(a,14,\'ail\')}' % P in blk
        assert not re.search(r'class="%s-tt">\$\{esc\((?:a\.nm|nameTxt\(a\))\)\}' % P, blk)   # no tooltip title without its icon
    assert "const appHead=(o,sz)=>{ const a=o.a; return `<h3 class=\"as-ainb\">${ic(a,sz||28)}" in js
    assert '<div class="as-pgh">${appHead(o,32)}</div>' in js
    assert '<h3 class="vs-ainb">${ic(a,28)}' in js and '<h2 class="vs-ainb">${ic(a,32)}' in js
    # the shared helpers: the change lists' chip and the old GA4 chips go by app_id
    assert "function smpAppHtml(id,name,size){ const a=smpApp(id,name); return `<span class=\"smp-app\">${appIconId(a.id||id," in js
    for f in ("uniOpen('${uniQ(a.app_id)}')\">${appIconId(a.app_id,a.app,18)}", "actOpen('${uniQ(r.app_id)}')\">${appIconId(r.app_id,r.app,18)}",
              "valOpen('${uniQ(r.app_id)}')\">${appIconId(r.app_id,r.app,18)}"):
        assert f in js
    # the tabs: placements cards + header, the per-app health table, the Accounts & Apps picker, the Review heading
    assert '<div class="appname">${appIcon(ap.name,22,\'ail\')}${ap.name}</div>' in js
    assert '<td class="nm">${appIcon(a.app,16,\'ail\')}${a.app}</td>' in js
    assert "${appIconId(x.app_id,x.app_name,18)}<span style=\"flex:1;" in js
    assert '<h3 class="rv-app" id="\'+id+"h-"+k+\'">\'+rvIcon(a,22)+' in js
    assert "📱 ${sel}" not in js and 'font-size:26px">📱</div>' not in js and 'font-size:24px">📱</div>' not in js
    # the header App selector: the chosen app's icon beside the native <select> (keyboard / phone picker kept)
    assert '<span id="appsel-ic" aria-hidden="true">📱</span> <span class="cx">App:</span><select id="appsel"' in _page()
    assert "function appSelSync(){ const sel=document.getElementById('appsel'); if(sel) sel.innerHTML=appSelHtml(); appSelIcon(); }" in js
    r0 = js.index("function render(){")
    assert "\n  appSelSync();\n" in js[r0:js.index("function show(", r0)]
