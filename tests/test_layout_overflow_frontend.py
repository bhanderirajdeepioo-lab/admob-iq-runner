"""Overflow sweep (every tab × 360-2560px × ₹/$): nothing sticks out of its box, nothing is clipped out of reach.
Static pins on frontend/index.html for the layout rules that fixed it — wide tables scroll inside their card at every
width (they were clipped at 761-1000px), names in Movers / Recommendations / Baseline wrap instead of being cut to a
few letters, the phone tables keep their key column on screen, and the Install value week chart makes room for its
₹-lakh axis labels. Synthetic values only."""

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


def test_wide_tables_scroll_inside_their_card_at_every_width(css):
    # a top-level rule (not inside a phone-only @media) — the last word on .card.pad0's sideways overflow
    top = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)
    rules = re.findall(r"(?:^|[}\s])\.card\.pad0\{([^}]*)\}", top)
    last = [r for r in rules if "overflow" in r][-1]
    assert "overflow-x:auto" in last and "overflow:hidden" not in last


def test_names_wrap_instead_of_being_cut(html, css):
    assert re.search(r"\.mv-nm,\.mv-sub,\.rc-nm,\.rc-sub,\.bl-apph\{[^}]*-webkit-line-clamp:2[^}]*overflow-wrap:anywhere", css)
    for cls in ("mv-nm", "mv-sub", "rc-nm", "rc-sub", "bl-apph"):
        tags = re.findall(r'<[a-z0-9]+ class="[^"]*\b' + cls + r'\b[^"]*"[^>]*>', html)
        assert tags, cls
        assert all("white-space:nowrap" not in t and "text-overflow:ellipsis" not in t for t in tags), (cls, tags)


def test_phone_tables_keep_the_key_column_on_screen(css):
    m = re.search(r"\.card\.pad0 table th:first-child,\.card\.pad0 table td:first-child\{([^}]*)\}", css)
    assert m and "position:sticky" in m.group(1) and "left:0" in m.group(1) and "background:" in m.group(1)


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_week_chart_axis_room_grows_with_its_labels(html):
    # the line that sizes the plot's left edge: never less than before, more for a longer (₹ lakh) label
    line = re.search(r"const mx=Math\.max\(\.\.\.vv\.map\(Math\.abs\)\)\*1\.15\|\|1, pl=(Math\.max\(pl0,.*?\*5\.9\)\+8\))", html)
    assert line, "weekChart's pl no longer sized from its labels"
    js = ("const out=[];for(const [pl0,lab] of [[50,'+$1,234'],[50,'+₹1.23 lakh'],[60,'+₹1.23 lakh'],[60,'+$9']]){"
          "const mx=1, mL=()=>lab; out.push(" + line.group(1) + ");} console.log(JSON.stringify(out));")
    out = json.loads(subprocess.run([NODE, "-e", js], check=True, capture_output=True, text=True, timeout=60).stdout)
    assert out[0] == 50 and out[3] == 60                       # short $ labels: the old fixed room
    assert out[1] > 50 + 15 and out[2] >= out[1]               # "+₹1.23 lakh" (11 chars): room for ~65px of text
