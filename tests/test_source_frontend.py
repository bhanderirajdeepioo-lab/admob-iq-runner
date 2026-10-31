"""💰 Revenue by source — the page side. tests/source_frontend.js runs the SRC module of frontend/index.html for real (a node
vm, stub page helpers) on SYNTHETIC data made up there; checked here: no pointer = nothing, the lazy file, All apps (30 days
to yesterday, sorted by total, the All apps row and the %), a period tap (no jump), All time, a tap on an app row, one app
(tiles, a day not read yet, months newest first, Today / Yesterday rows, GA4 sampled ≈), the GA4 channels card from the
app's own file (loaded once), and the ₹ view. Skipped where node is not installed. No real data."""
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
    r = subprocess.run([NODE, os.path.join(ROOT, "tests", "source_frontend.js"), PAGE], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_no_errors(out):
    assert out["errors"] == []


def test_no_pointer_no_block_and_lazy_load(out):
    assert out["no_pointer"] == ""
    assert "load ho raha hai" in out["loading"]
    assert out["loads1"] == ["source.json.gz?v=abc"]


def test_all_apps_30_days(out):
    s = out["all"]
    # 30 days to yesterday: Alpha 29 read days (one not read) × 20 = $580; Beta 30 × 2 = $60; All apps $640
    assert "All apps $640 $320 50% $145 23% $146 23% $29 4.5%" in s, s
    assert s.index("Alpha App") < s.index("Beta App")
    assert "Alpha App · 1 din baaki ≈ $580 $290 50% $145 25% $116 20% $29 5.0%" in s
    assert "1 app ki purani history abhi aa rahi hai" in s
    assert "Paid = Cross-network" in s and "Notification = Mobile Push Notifications" in s


def test_period_tap_and_all_time(out):
    assert "All apps $22 $11 50% $5.0 23% $5.0 23% $1.0 4.5%" in out["yday"]
    assert out["scroll_after_tap"] == 0
    assert "poori history" in out["all_time"] and "All apps $860 $430" in out["all_time"]
    assert out["appset"] == ["Alpha App"]


def test_one_app(out):
    s = out["app"]
    assert "Total $580 5,800 sessions" in s and "Notification $145 25%" in s
    assert "Is period ke 1 din ka data abhi aa raha hai" in s
    assert s.index("Oct 2026 so far") < s.index("Sep 2026")
    assert "Today so far $20 $10" in s and "Yesterday ≈ $20 $10" in s
    assert "≈" in out["app_html"]
    assert "Channels load ho rahe hain" in out["app_loading_channels"]
    assert out["loads2"].count("source_000000000001.json.gz?v=a1") == 1
    g = s[s.index("GA4 channels"):s.index("Month by month")]
    assert "Total 5,800 $580" in g
    assert g.index("Cross-network Paid") < g.index("Mobile Push Notifications Notification") < g.index("Direct Organic")


def test_rupee_view(out):
    assert "Total ₹51,040" in out["app_inr"]
