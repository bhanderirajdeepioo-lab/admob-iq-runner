"""📱 Devices — the page side. tests/device_frontend.js runs the ROI module of frontend/index.html for real (a node vm, stub
page helpers) on SYNTHETIC data made up there; checked here: the waiting message, the status chips, Loss first, names (brand +
marketing name, the model code), paid %, ≈ cost, the money back labels, back next day, "≈30", the small models line, the
coverage warning, a country pick (and an unknown one falling back to All countries) and a column sort. Skipped where node is
not installed. No real data."""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
PAGE = os.path.join(ROOT, "frontend", "index.html")


@pytest.fixture(scope="module")
def out():
    if NODE is None:
        pytest.skip("node is not installed")
    r = subprocess.run([NODE, os.path.join(ROOT, "tests", "device_frontend.js"), PAGE], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_no_errors(out):
    assert out["errors"] == []


def test_waiting(out):
    assert "Devices ka data aa raha hai" in out["wait"]


def test_all_countries(out):
    s = out["all"]
    assert "🔴 Loss 1" in s and "🟡 Slow 1" in s and "🟢 Profit 1" in s
    assert s.index("XBrand XM-2") < s.index("XBrand Phone One XM-1")             # Loss first; no marketing name: brand + code
    assert "XBrand XM-2 XM-2" not in s                                           # the code once
    # Installs · CPI · Revenue 7d · revenue per user 7 / 30 / 90 days with their ROAS · money back · back next day
    assert "XBrand Phone One XM-1 🟢 Profit 5,000 90% paid ≈$0.420 $500 $0.100 20% $0.300 90% $0.600 130% 31–90 din 45%" in s
    assert "XM-3 🟡 Slow ≈30 700 80% paid ≈$0.450 $70 $0.100 10% $0.300 50% — ≈ 181–365 din 40%" in s
    assert "1 saal me nahi" in s and "≈ 181–365 din" in s and "≈30" in s
    assert "+ 15 aur models (har ek 30 se kam installs) — 2% installs (upar ke tiles me shamil)." in s
    assert "⚠️" not in s and 'class="roi-g"' in out["all_html"] and 'class="roi-b"' in out["all_html"]


def test_kpi_tiles(out):
    s = out["all"]
    assert "Installs 6,720 89% paid · 25 Sep 26–22 Oct 26" in s
    assert "CPI $0.400 Google Ads cost ÷ paid installs" in s
    assert "Revenue / user · 7d $0.100 ROAS 28%" in s and "Revenue / user · 30d $0.300 ROAS 84%" in s
    assert "Revenue / user · 90d — 90 din ka data abhi aa raha hai" in s and "Revenue · 7d $672 Ads cost $2,400" in s
    c = out["cc"]
    assert "CPI $0.500" in c and "Revenue / user · 90d $0.600 ROAS 133%" in c


def test_coverage_warning(out):
    assert '⚠️ Is app me GA4 ne kuch din ka model-wise data "(other)" me daal diya (sabse zyada 22%' in out["warn"]


def test_country_and_sort(out):
    assert "Devices · [XA] Country XA" in out["cc"] and "3,500" in out["cc"] and "XM-2" not in out["cc"]
    s = out["sorted_n"]
    assert s.index("XM-1") < s.index("XM-2") < s.index("XM-3")
    assert "Devices · All countries" in out["unknown_cc"]
    u = out["sorted_u30"]
    assert u.index("XM-1") < u.index("XM-2")                                       # every row $0.300: installs decide
