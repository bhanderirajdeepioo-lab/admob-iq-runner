"""📈 ROI (a section of 💸 Install value) — the page side. tests/roi_frontend.js runs the ROI module + roiWrap of
frontend/index.html for real (a node vm, stub page helpers) on SYNTHETIC data made up there; checked here: where the block
goes, the day-by-day columns and their fallback to the checkpoints, Today / Yesterday, week / month rows (complete days
only), the four cell kinds, breakeven, the KPI tiles, the countries board (order, what cutting saves), lifetime P/L
(totals to the day both sides are in), All apps (icons, Worse first, hidden apps out), the hub card line, and the wiring
into the page. Skipped where node is not installed. No real data."""
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
    r = subprocess.run([NODE, os.path.join(ROOT, "tests", "roi_frontend.js"), PAGE],
                       check=True, capture_output=True, text=True, timeout=120)
    rep = json.loads(r.stdout)
    assert not rep["errors"], rep["errors"]
    return rep["out"]


def test_block_place(out):
    assert out["no_ptr"] and out["wrap_order"] and out["wrap_loading"]


def test_day_wise(out):
    assert out["cols"] == [35, "D0", "D30", "D60", "D365"]              # every day 0 … 30, then 60 / 90 / 180 / 365
    assert out["old_fallback"] == [[8, True], [None, False]]           # older days: the checkpoints, never a guess
    assert out["day_today"] and out["day_tiles"] and out["hero"] and out["day_be"] and out["day_tie"]
    assert out["day_rows"] == 60 and out["day_more"]                   # 60 at a time, "Show all" (nothing dropped)
    assert out["months"] == [["2026-10", 13], ["2026-09", 30], ["2026-08", 27]]
    assert out["month_cols"] == ["D0", "D1", "D3", "D7", "D14", "D30"] and out["month_d0"] == 30
    assert out["month_d30"] is None                                    # a month waits for its youngest day
    assert out["cells"] == [2, 20, 0.2, 5]                             # ROAS, revenue, per install, delta


def test_countries_life_all(out):
    assert out["cty_cut"] and out["cty_order"] == ["BB", "CC", "AA"] and out["cty_chips"] == 3
    assert out["life_total"] and out["life_since"] and out["life_live"] and out["life_inr"]   # ₹ = as billed
    assert out["hero_all"]
    assert out["all_order"] == ["id-a", "id-b"] and out["all_icons"] == 2
    assert out["card"] == "📈 D7 ROAS <b>40%</b> (usual 50%) · paisa wapas ~12 days"   # ROI's own numbers replace the card's


def test_wiring():
    with open(PAGE, encoding="utf-8") as f:
        p = f.read()
    assert "return roiWrap(vsAppOn(r)?vsAppPage(r,old):old, r.app_id);" in p and 'id="val-more"' in p
    assert "return roiWrap(vsOn()?vsPortfolio():valPortfolio(), '');" in p
    assert "if(c[0]==='value') try{ roiCardLine(x,name); }catch(e){}" in p
    assert ".roi{position:relative;" in p
