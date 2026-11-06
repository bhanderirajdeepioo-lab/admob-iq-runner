"""📱 Devices v3 — the page on the build's own files (owner, 6 Nov 2026: All time "jab se app start hui he" + the standard
picker + Custom). Python makes the files with device_build.build_app on SYNTHETIC stores (tests/test_ga4_device.py's
made-up models, countries and months of history), tests/device_frontend_v3.js runs the page's ROI module on them in a node
vm. Checked: the loading message; the picker in the owner's order and words (Last 7 days … All time · Custom) + the month
mover; All time by default from the app's first install day; the JS sums equal the build's lists row for row for EVERY
standard button, All countries and each country (the parity rule); Custom across months; an old month from its own file;
the current month = This month; a country; an unknown period falls back to All time; a file of another build is "stale"
with Try again; the period's warnings: days still filling as "X of Y din", GA4's "(other)" share, the old revenue date,
no AdMob match. Skipped where node is not installed. No real data."""
import json
import os
import shutil
import subprocess
from datetime import date, timedelta

import pytest

from admob_iq import device_build as dvb
from tests import test_ga4_device as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
PAGE = os.path.join(ROOT, "frontend", "index.html")


def _run(tmp_path, name, **kw):
    if NODE is None:
        pytest.skip("node is not installed")
    data = T._v3_store(tmp_path / name, skip=kw.pop("skip", ()), old_from=kw.get("first") or T.FIRST)
    fold = kw.pop("fold", None)
    if fold:                                            # GA4 folds part of some old days into "(other)"
        st = T.gd.Store(os.path.join(data, T.gd.DIR), T.KEYV)
        for m in st.months():
            xs = st.month(m)
            for x in list(xs):
                if x[:7] == fold:                       # (and its revenue so far last read on 30 Sep)
                    xs[x] = dict(xs[x], **T._old_day(date.fromisoformat(x), at="2026-10-21T00:00:00Z", folded=0.8,
                                                     to=date(2026, 9, 30)))
            st.write_month(m, xs)
        st.save_meta()
    out = str(tmp_path / name / "site")
    stub, files = T._bt(data, out, **kw)
    with open(os.path.join(out, "stub.json"), "w", encoding="utf-8") as fh:
        json.dump(stub, fh)
    r = subprocess.run([NODE, os.path.join(ROOT, "tests", "device_frontend_v3.js"), PAGE, out], capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["errors"] == []
    return got


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("v3"), "full")


def test_loading_then_all_time_by_default_and_the_standard_picker(full):
    assert "📱 Devices ka data load ho raha hai" in full["loading"]
    s = full["all"]
    assert ("Today Yesterday Last 7 days This month Last month Last 30 days Last 60 days Last 90 days All time Custom "
            "‹ Sep 2026 ›") in s
    assert 'data-roi-dvper="all" aria-pressed="true"' in full["all_html"]
    days = (T.TODAY - T.FIRST).days + 1
    assert "Installs %s" % format(138 * days, ",") in s and "20 Jan – 31 Oct 2026" in s       # from the app's first install day
    assert "XBrand Phone 1" in s and "Purane din" not in s and "⚠️" not in s and "≈ Is period" not in s
    assert 'aria-label="Previous month: Aug 2026"' in full["all_html"]


def test_js_sums_equal_the_builds_lists_for_every_button_and_country(full):
    par = full["parity"]
    assert set(par) == {"today", "yday", "7", "tm", "lm", "30", "60", "90", "all"}
    for pid, e in par.items():
        assert e["bad"] == [], (pid, e["bad"][:5])
        assert e["rows"] > 0 and e["cc_rows"] > 0
    assert full["months"] == len(dvb.month_list(T.FIRST, T.TODAY))


def test_custom_an_old_month_this_month_a_country_and_the_fallback(full):
    assert "Custom ke liye din-wise data load ho raha hai" in full["custom_busy"]
    c = full["custom"]
    n = 138 * ((date(2026, 4, 20) - date(2026, 2, 10)).days + 1)
    assert "Installs %s" % format(n, ",") in c and "10 Feb – 20 Apr 2026" in c
    assert 'data-roi-dvf aria-label="From" min="2026-01-20" max="2026-10-31" value="2026-02-10"' in full["custom_html"]
    m = full["mon"]
    assert "Installs %s" % format(138 * 31, ",") in m and "1 Mar – 31 Mar 2026" in m and "‹ Mar 2026 ›" in m
    assert "Installs %s" % format(138 * 31, ",") in full["mon_cur"] and "1 Oct – 31 Oct 2026" in full["mon_cur"]
    assert "Devices · [XA] Country XA" in full["cc"] and "Installs %s" % format(92 * ((T.TODAY - T.FIRST).days + 1), ",") \
        in full["cc"]
    assert 'Installs %s' % format(138 * ((T.TODAY - T.FIRST).days + 1), ",") in full["fallback"]
    assert "Naya data abhi poora nahi pahuncha" in full["stale"] and "Try again" in full["stale"]


def test_the_periods_own_warnings(tmp_path):
    skip = {(date(2026, 2, 1) + timedelta(days=i)).isoformat() for i in range(10)}
    g = _run(tmp_path, "warn", skip=skip, kq=lambda X: X < date(2026, 3, 1), fold="2026-04")
    days = (T.TODAY - T.FIRST).days + 1
    s = g["all"]
    assert "⏳ Purane din abhi bhar rahe hain: %d of %d din ka data aa gaya" % (days - 10, days) in s
    assert '⚠️ Is period me GA4 ne kuch model-wise data "(other)" me daal diya' in s
    assert "≈ Is period ke %d din ke install-mahine me AdMob ka data nahi" % ((date(2026, 3, 1) - T.FIRST).days - 10) in s
    assert "🕒 Purane installs ki kamai 30 Sep 2026 tak gini hai" in s
    c = g["custom"]                                    # 10 Feb – 20 Apr: one day not filled (10 Feb), Feb's 18 other
    assert "⏳ Purane din abhi bhar rahe hain: 69 of 70 din ka data aa gaya" in c      # days without an AdMob match,
    assert '"(other)" me daal diya (sabse zyada 6%' in c and "🕒 Purane installs ki kamai 30 Sep 2026" in c   # April's fold
    assert "≈ Is period ke 18 din ke install-mahine me AdMob ka data nahi" in c
    m = g["mon"]                                       # March: whole, AdMob matched, not folded, read to F
    assert "Purane din" not in m and "(other)" not in m and "≈ Is period" not in m and "🕒" not in m
    for k in ("today", "7", "30", "lm"):
        assert g["parity"][k]["bad"] == []
    assert g["parity"]["all"]["bad"] == []


def test_every_date_carries_its_year_and_both_years_when_all_time_spans_two(tmp_path):
    # the app's first install day in an earlier year than today: All time names both years, never a year-less date
    g = _run(tmp_path, "years", first=date(2025, 12, 15))
    days = (T.TODAY - date(2025, 12, 15)).days + 1
    s = g["all"]
    assert "Installs %s" % format(138 * days, ",") in s and "15 Dec 2025 – 31 Oct 2026" in s
    assert "15 Dec –" not in s and "15 Dec 26" not in s
    assert "10 Feb – 20 Apr 2026" in g["custom"] and "1 Mar – 31 Mar 2026" in g["mon"]
    assert g["parity"]["all"]["bad"] == []
    assert 'aria-label="Previous month: Aug 2026"' in g["all_html"]


def test_try_again_on_a_stale_load_reads_the_app_file_and_the_index_again(full):
    af = "roi_%s.json.gz" % T.KEYV
    assert af in full["retry_asked"] and "roi_%s_dv.json.gz" % T.KEYV in full["retry_asked"]
    assert "Installs" in full["retry_after"] and "Naya data abhi poora nahi pahuncha" not in full["retry_after"]


def test_the_sums_cache_custom_outside_the_data_and_custom_opening_on_last_30_days(full):
    assert full["switch"][0] > 0 and full["switch"][1] == 0     # another index never answers from the cache
    assert full["outside"] == [T.FIRST.isoformat(), T.FIRST.isoformat()]
    assert "Custom ke liye" not in full["cus30"] and full["cus30_asked"] == 0
    assert "Installs %s" % format(138 * 30, ",") in full["cus30"]


def test_a_month_without_its_file_and_a_stopped_history_job_are_said(full):
    assert "⚠️ Missing months: Mar 2026" in full["gap"] and "kam dikhenge" in full["gap"]
    assert "Missing months" not in full["gap_other"]             # (Last 30 days: March is not in it)
    assert "purana data laane wala job abhi ruka hua hai" in full["hstale"]
    assert "har 6 ghante" not in full["hstale"]


def test_the_month_mover_of_a_new_app_offers_no_earlier_month(full):
    h = full["mover_new"]
    tm = T.TODAY.isoformat()[:7]
    assert 'data-roi-dvper="mon:%s" aria-pressed="false" aria-label="Pick ' % tm in h
    for ym in ("2026-09", "2026-08"):
        assert 'data-roi-dvper="mon:%s" aria-pressed="false" aria-label' % ym not in h
