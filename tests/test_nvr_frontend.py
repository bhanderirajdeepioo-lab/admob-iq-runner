"""📈 eCPM · first session vs returning — the page side (tests/nvr_frontend.js runs the NVR module of frontend/index.html in
node on synthetic data): the pointer, the lazy file, the period (Today … Last month, All time, Custom; 7 / 30 days = the
last final days), the tiles, the chart with its values printed, the ad unit / format / country tables (sort, top 15 + Show
all, the unnamed country), a day not read yet, ₹, a failed load + Try again, the tapped control kept in place; and the
section is wired into the eCPM tab's app page."""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "frontend", "index.html")
NODE = shutil.which("node")


@pytest.fixture(scope="module")
def out():
    if NODE is None:
        pytest.skip("node is not installed")
    r = subprocess.run([NODE, os.path.join(ROOT, "tests", "nvr_frontend.js"), PAGE], check=True, capture_output=True,
                       text=True, timeout=120)
    rep = json.loads(r.stdout)
    assert not rep["errors"], rep["errors"]
    return rep["out"]


def test_pointer_and_lazy_file(out):
    assert out["no_pointer"] == "" and "abhi nahi aaya" in out["no_app"]
    assert out["loading"] == "⏳ First session vs Returning load ho raha hai…" and out["loads"] == 1
    assert out["fail"] and out["retry"]


def test_tiles_chart_and_tables(out):
    assert out["title30"] == "2 Oct 2026 – 31 Oct 2026 · GA4"                     # 30 days = the last 30 final days
    assert out["tiles30"] == [["First session eCPM", "$2.00", "30,000 impressions · $60"],
                              ["Returning eCPM", "$1.00", "90,000 impressions · $90"],
                              ["First ÷ Returning", "2.0×", "first session ka eCPM zyada"],
                              ["Impressions / session", "10.0 · 6.0", "first session · returning"],
                              ["Kamai ka hissa", "40% · 60%", "first session · returning"]]
    assert out["chart"] and out["note"]
    assert [x.strip() for x in out["units_rows"][:2]] == ["unit_banner", "unit_open"] and len(out["units_rows"]) == 15
    assert out["unit_open"] and out["units_more"] and out["units_all"] == 20
    assert out["formats"] == [["Banner", "$1.25", "$1.00", "1.3×"], ["App open", "$2.50", "$1.00", "2.5×"], ["Native", "$1.00", "—", "—"]]
    assert out["countries"] == [["Name XA", "$2.00", "$1.00"], ["Name XB", "$4.00", "$0.50"], ["Not named", "$5.00", "—"]]
    assert [x.strip() for x in out["sort_er"]] == ["unit_open", "unit_banner"]


def test_periods_custom_and_currency(out):
    assert out["periods"] == {"today": "2 Nov 2026 · GA4", "yday": "1 Nov 2026 · GA4", "7": "25 Oct 2026 – 31 Oct 2026 · GA4",
                              "tm": "1 Nov 2026 – 2 Nov 2026 · GA4", "lm": "1 Oct 2026 – 31 Oct 2026 · GA4",
                              "all": "1 Sep 2026 – 2 Nov 2026 · GA4"}
    assert out["all_miss"] and out["scroll"] == 0
    assert out["custom"] == ["11 Oct 2026 – 20 Oct 2026 · GA4", True, "$2.00"]
    assert out["inr"] == ["₹176", "30,000 impressions · ₹5,280"]


def test_wired_into_the_ecpm_app_page():
    s = open(PAGE, encoding="utf-8").read()
    assert "${typeof NVR!=='undefined'&&L.id?NVR.block(L.id):''}`;" in s
    for k in ("today", "yday", "7", "30", "tm", "lm", "all", "cus"):
        assert "['%s'," % k in s[s.index("const NVR=(()=>{"):s.index("// the Install value page: 📈 ROI first")]


def test_country_picker(out):
    """Owner, 2 Nov 2026: "isme country ka option add karo, jo country select krunga uska chart aayega vrna default all
    country … top 5 country revenue wise bhi rakh dena": All countries (picked by default) + the period's top countries by
    revenue + every country in a list (most revenue first, its revenue beside); a pick → that country's tiles and chart, its
    row marked in the Countries table, one line saying so; a pick from the list; All countries back."""
    assert out["cc_chips"] == [["", "true"], ["XA", "false"], ["XB", "false"]]
    assert out["cc_list"] == [["XA", "[XA] Name XA · $96"], ["XB", "[XB] Name XB · $54"]]
    x = out["cc_xb"]
    assert x["title"] == '👥 First session vs Returning · eCPM · <span class="nvr-fl">[XB]</span> Name XB'
    assert x["tiles"] == [["First session eCPM", "$4.00"], ["Returning eCPM", "$0.50"], ["First ÷ Returning", "8.0×"],
                          ["Impressions", "6,000 · 60,000"], ["Kamai ka hissa", "44% · 56%"]]
    assert x["chart"] and x["row_on"] and x["note"]
    assert out["cc_xa"] == "$2.00" and out["cc_all"] == ["$2.00", False]
