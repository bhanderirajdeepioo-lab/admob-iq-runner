"""The page's own match / show arithmetic over the placement daily rows the engine ships (the ad unit's own requests /
matched requests from the mediation report without ad source): show rate is impressions / matched as AdMob reports
it — no 100% cap any more (the cap only hid the old mix of all-source impressions over AdMob-Network-only matched
requests). tests/match_source_frontend.js runs the real page script in a node vm over synthetic rows. Skipped where
node is not installed."""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    path = str(tmp_path_factory.mktemp("fe") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "match_source_frontend.js"), path],
                         check=True, capture_output=True, text=True, timeout=120)
    rep = json.loads(out.stdout)
    assert not rep["errors"], rep["errors"]
    return rep["out"]


def test_window_sums_use_the_shipped_requests_and_matched(report):
    m = report["sum_both"]
    assert (m["req"], m["matched"], m["impr"]) == (11_500 + 6_000, 10_900 + 5_000, 9_800 + 5_500)
    assert m["match"] == pytest.approx((10_900 + 5_000) / (11_500 + 6_000))
    assert m["show"] == pytest.approx((9_800 + 5_500) / (10_900 + 5_000))


def test_show_rate_is_not_capped(report):
    assert report["sum_day2"]["show"] == pytest.approx(5_500 / 5_000)       # 110%, not 100%
    assert report["series"]["show"] == pytest.approx([9_800 / 10_900, 5_500 / 5_000])
    assert report["series"]["match"] == pytest.approx([10_900 / 11_500, 5_000 / 6_000])


def test_no_show_cap_left_in_the_page():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    assert not re.search(r"show\s*:\s*\w+\s*\?\s*Math\.min\(\s*1\s*,", html)
    assert "show.push(o.m? Math.min(1" not in html
