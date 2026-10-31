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


def test_all_countries_30_days(out):
    s = out["all"]
    assert "🔴 Loss 1 🟡 Slow 1 🟢 Profit 1" in s
    assert s.index("XBrand XM-2") < s.index("XM-3") < s.index("XBrand Phone One XM-1")        # Loss first
    assert "XBrand XM-2 XM-2" not in s                                                       # the code once
    # Installs (paid %) · CPI ≈ · Revenue (so far) · Revenue / install · vs CPI · back next day · money back
    assert "XBrand Phone One XM-1 🟢 Profit 5,000 90% paid ≈$0.400 $2,250 $0.450 113% 45% 31–90 din" in s
    assert "XBrand XM-2 🔴 Loss 900 95% paid ≈$0.500 $90 $0.100 20% 30% 1 saal me nahi" in s
    assert "XM-3 🟡 Slow ≈30 700 80% paid ≈$0.450 $140 $0.200 44% 40% ≈ 181–365 din" in s
    assert "+ 15 aur models (har ek ke kam installs) — 2% installs (upar ke tiles me shamil)." in s
    assert "Today Yesterday 7 days 30 days This month Last month 90 days" in s
    assert "⚠️" not in s and 'class="roi-g"' in out["all_html"] and 'class="roi-b"' in out["all_html"]


def test_kpi_tiles(out):
    s = out["all"]
    assert "Installs 6,720 89% paid · 1 Oct 26–30 Oct 26" in s
    assert "CPI $0.400 Google Ads cost ÷ paid installs" in s
    assert "Revenue $2,600 in installs ki ab tak ki kamai · Ads cost $2,400" in s
    assert "Revenue / install $0.387" in s and "vs CPI 97% Revenue / install ÷ CPI" in s and "Back next day 42%" in s
    c = out["cc"]
    assert "CPI $0.500" in c and "vs CPI 100%" in c


def test_period_pick(out):
    t = out["today"]
    assert "Installs 260 88% paid · 31 Oct 26" in t and "XBrand Phone One XM-1 🟢 Profit 200 90% paid ≈$0.400 $9.0 $0.0450 11% —" in t
    assert "Is period / country me abhi kisi model ke kaafi installs nahi." in out["missing_period"]
    assert "Devices ka data aa raha hai" in out["old_format"]
    assert "⏳ Is period ke 10 din ka data GA4 se abhi aa raha hai" in out["partial"] and "⏳ Is period" not in out["all"]


def test_coverage_warning(out):
    assert '⚠️ Is app me GA4 ne kuch din ka model-wise data "(other)" me daal diya (sabse zyada 22%' in out["warn"]


def test_country_and_sort(out):
    assert "Devices · [XA] Country XA" in out["cc"] and "3,500" in out["cc"] and "XM-2" not in out["cc"]
    s = out["sorted_n"]
    assert s.index("XM-1") < s.index("XM-2") < s.index("XM-3")
    assert "Devices · All countries" in out["unknown_cc"]
    v = out["sorted_vs"]
    assert v.index("XM-2") < v.index("XM-3") < v.index("XM-1")                              # vs CPI: lowest first
