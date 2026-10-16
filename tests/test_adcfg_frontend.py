"""⚙️ Ad setting badlav — the page side. tests/adcfg_frontend.js runs the ROI module of frontend/index.html for real (a
node vm, stub page helpers) on SYNTHETIC data made up there; checked here: the card inside 🔮 Forecast's "why" (Today /
Yesterday on top, the full history newest first, one status word per row, Low folded, "Aur dikhao", a row's evidence),
the weekly ads-per-user chart (a ⚙ mark at every change, numbers printed), the ⚙ marks on the forecast's daily chart and
on its back-test chart (+ their tooltips and the material changes' line) — every mark's number printed at 1280 / 375 px
and 30 / 90 / 365 days —, and nothing at all without the block or in the developer's view. Skipped where node is not installed. No real data."""
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
    r = subprocess.run([NODE, os.path.join(ROOT, "tests", "adcfg_frontend.js"), PAGE],
                       check=True, capture_output=True, text=True, timeout=120)
    rep = json.loads(r.stdout)
    assert not rep["errors"], rep["errors"]
    return rep["out"]


def test_the_card_today_yesterday_and_the_full_history(out):
    assert out["card_head"] and out["today"] and out["yesterday"] and out["till"] and out["history"]
    assert out["today_low"]                                         # only a Low one new: said, not listed
    assert out["rows"] == ["2026-10-03", "2026-09-28", "2026-09-02", "2026-08-24", "2026-07-10"]   # newest first, Low folded
    assert out["status"] == ["Checking", "Confirmed", "Reverted", "Confirmed", "With update"]      # one word a row
    assert out["kinds"] and out["update_col"] and out["sizes"] and out["explain"]


def test_low_more_and_a_rows_evidence(out):
    assert out["low_btn"] and out["low_on"] and out["more"]
    assert out["open_row"] and out["open_rel"] and out["open_near"] and out["open_nu_alike"]


def test_the_charts_carry_the_marks(out):
    assert out["chart_lines"] and out["chart_labels"] and out["chart_tip"] and out["chart_marks"] == 4
    assert out["fc_marks"] == 3 and out["fc_tip"] and out["fc_same"]
    for r in out["fc_all_labels"]:                                 # every ⚙ mark has its number, inside the drawing
        if r[0] == "weekly":
            assert r[2] == 3 and r[3] == 3, r
        else:
            assert r[2] == 3 and r[3] == 3 and r[4], r
            assert r[5] == "⚙ INT +50%|⚙ INT −42%|⚙ NAT −28%", r
    assert out["bt_marks"] == 1 and out["bt_tip"] and out["bt_line"] and out["bt_same"]


def test_where_it_sits_and_when_it_is_not_there(out):
    assert out["view_order"] and out["view_none"] and out["empty"] and out["dev"]
