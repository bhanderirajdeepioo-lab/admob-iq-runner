"""KPI tiles always fit their number (owner, Overview in INR: "numbers hi bahar nikal gaye"). The .row .c2-.c9 grids
shrink tiles with minmax(0,1fr) (no sideways page scroll), so a tile must never get narrower than its number:
many-tile rows wrap into balanced rows, the tile is a size container and its big number is sized in cqi (a share of
the tile's own width) with only a px CAP — no later rule may pin a fixed px size back on it — and kpi() tags long
values (13+ / 16+ characters) for a smaller fit. Synthetic values only."""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


@pytest.fixture(scope="module")
def html():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def css(html):
    return html[html.index("<style>"):html.index("</style>")]


def test_tile_is_a_container_and_the_number_is_sized_by_its_width(css):
    assert re.search(r"\.kpi\{container-type:inline-size\}", css)
    m = re.search(r"\.kpi \.v\{--fit:(\d+)cqi;font-size:min\(var\(--vmax,24px\),var\(--fit\)\)", css)
    assert m and int(m.group(1)) <= 14                   # 14cqi: a 12-character "₹888,888,888" (7.0em) fits
    assert re.search(r"\.kpi \.v\.vl\{--fit:12cqi\}", css) and re.search(r"\.kpi \.v\.vxl\{--fit:10cqi\}", css)


def test_no_rule_pins_a_fixed_px_size_back_on_the_number(css):
    # every later .kpi .v rule (tablet / phone / Overview's bigger phone numbers) may only change the cap
    rules = re.findall(r"([^{}]*\.kpi \.v)\{([^}]*)\}", css)
    assert len(rules) >= 4
    for sel, body in rules[1:]:
        assert not re.search(r"(?<!-)font-size:\s*\d", body), (sel.strip(), body)


def test_many_tile_rows_wrap_into_balanced_rows(css):
    # 9 → 5+4 → 3+3+3 (never 8+1), 6 → 3+3, 5 → 3+2; the ≤1000px rules come after and still win
    wide9 = re.search(r"@media\(max-width:(\d+)px\)\{\.c9\{grid-template-columns:repeat\(5,minmax\(0,1fr\)\)\}\}", css)
    mid = re.search(r"@media\(max-width:(\d+)px\)\{\.c5,\.c9\{grid-template-columns:repeat\(3,minmax\(0,1fr\)\)\}\}", css)
    six = re.search(r"@media\(max-width:(\d+)px\)\{\.c6\{grid-template-columns:repeat\(3,minmax\(0,1fr\)\)\}\}", css)
    assert wide9 and mid and six
    assert int(wide9.group(1)) > int(six.group(1)) > int(mid.group(1)) > 1000
    assert css.index(mid.group(0)) < css.index("@media(max-width:1000px){.c4,.c5")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_kpi_tags_long_values_for_the_smaller_fit(html):
    src = re.search(r"function kpi\(l,v,d,cls,spark\)\{.*?\n.*?`;\}", html, re.S).group(0)
    vals = ["₹1,234,567", "₹888,888,888", "-₹100,000,000", "₹1,000,000,000", "appopen_splash_1", 0, None,
            '<span title="a long tooltip that is not shown">₹5</span>', "28 &middot; 7"]
    js = src + "\nconsole.log(JSON.stringify(" + json.dumps(vals) + ".map(v=>(kpi('L',v,'d').match(/class=\"(v[^\"]*)\"/)||[])[1])));"
    out = json.loads(subprocess.run([NODE, "-e", js], check=True, capture_output=True, text=True, timeout=60).stdout)
    assert out == ["v", "v", "v vl", "v vl", "v vl vxl", "v", "v", "v", "v"]
