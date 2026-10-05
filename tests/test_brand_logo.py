"""The dashboard's logo: the Helsy x AdMob mark (owner's pick, 5 Oct 2026: Helsy's hexagon and colours, { } braces, rising
revenue bars). The sidebar shows it inline; the browser tab, the home-screen icon and the web-app manifest carry PNGs of it."""
import base64
import json
import os
import re
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FE = os.path.join(ROOT, "frontend")
NAVY, CYAN = "#1C5787", "#019EC9"          # Helsy's own colours


def _page():
    with open(os.path.join(FE, "index.html"), encoding="utf-8") as f:
        return f.read()


def _png(data):
    """(width, height, colour type) from a PNG's IHDR."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR"
    w, h = struct.unpack(">II", data[16:24])
    return w, h, data[25]


def test_sidebar_brand_is_the_helsy_mark():
    page = _page()
    m = re.search(r'<div class="brand"><div class="logo" title="AdMob IQ by Helsy">(<svg .*?</svg>)</div>'
                  r'<div class="nm">AdMob IQ<small>by Helsy</small></div></div>', page)
    assert m, "the sidebar brand"
    svg = m.group(1)
    assert 'viewBox="0 0 100 100" width="36" height="36" aria-hidden="true"' in svg
    assert NAVY in svg and CYAN in svg and svg.count("<polygon") == 2 and svg.count("<rect") == 3 and svg.count("<path") == 2
    assert "◈" not in page and "Revenue Intelligence" not in page
    assert page.count('class="logo"') == 1


def test_browser_tab_icon():
    links = re.findall(r'<link rel="icon" type="image/png" href="data:image/png;base64,([A-Za-z0-9+/=]+)">', _page())
    assert len(links) == 1
    w, h, ct = _png(base64.b64decode(links[0]))
    assert (w, h, ct) == (64, 64, 6)          # RGBA: the mark on a transparent ground (light and dark tab bars)


def test_home_screen_icons_and_manifest():
    for n in (180, 192, 512):
        with open(os.path.join(FE, "icon-%d.png" % n), "rb") as f:
            assert _png(f.read())[:2] == (n, n)
    assert 'rel="apple-touch-icon" href="icon-180.png"' in _page()
    with open(os.path.join(FE, "manifest.webmanifest"), encoding="utf-8") as f:
        man = json.load(f)
    got = []
    for i in man["icons"]:
        assert i["src"].startswith("data:image/png;base64,") and i["type"] == "image/png"
        w, h, _ = _png(base64.b64decode(i["src"].split(",", 1)[1]))
        assert "%dx%d" % (w, h) == i["sizes"]
        got.append((i["sizes"], i["purpose"]))
    assert got == [("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")]   # maskable: Android's round crops
    assert man["background_color"] == man["theme_color"] == "#0a1120"
