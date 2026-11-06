"""Daily App Review — the "ads" feature follows the 📉 CPI vs eCPM alarm (one verdict everywhere), on the synthetic
site of tests/review_synth.py plus a made-up CPI pointer (dashboard["cpi"], SPEC §3.3 shape): Alarm → red, Watch →
amber, Fixed → green, OK → normal, New → too early, Paused → n/a, each with its short line (normal → now from the same
dashboard keys the CPI screen sums, the reason, since); an app without a pointer row, a missing or damaged pointer =
today's 7-vs-7 rule, byte for byte; the build runs the cpi step before the review (this build's pointer, never the
last one). No real data."""

import copy
import inspect
import json
from datetime import timedelta

import pytest

from admob_iq import build_static
from admob_iq.review import build_day
from admob_iq.review.fmt import plain
from admob_iq.review.site import Site
from tests import review_synth as rs
from tests.test_review_build import check_doc

DAY = rs.DAY
T = DAY - timedelta(3)                            # the pointer's data day
SINCE = T - timedelta(5)
iso = lambda d: d.isoformat()


@pytest.fixture
def site(tmp_path):
    p = str(tmp_path / "site")
    rs.make_site(p)
    return p


def dash(site_dir):
    return Site(site_dir).dashboard()


def with_cpi(db, rows, app=4):
    """The synthetic dashboard + a CPI pointer; app 4 (Google Ads: $50/day, 100 installs/day) also gets Google's D0
    value ($15/day → Day-0 ROAS 30.0%) and the ₹ rate (USD per ₹ = 1/88 → CPI ₹44.0)."""
    db = copy.deepcopy(db)
    e = db["roas"]["by_app"][rs.DNAME[4]]
    e["convval_day1_daily"] = {x: 15.0 for x in e["daily"]}
    db["roas"]["fx"] = {"INR": 1 / 88}
    base = {"name": rs.DNAME[app], "key": "0123456789ab", "file": "cpi_0123456789ab.json.gz", "v": "000000000000",
            "st": "ok", "since": None, "to": None, "open": [], "nrm": {"CPI": 40.0, "ECPM": 6.0, "ROAS_G": 0.4},
            "lost": None}
    db["cpi"] = {"v": 1, "t": iso(T), "at": "2026-01-01T00:00:00Z", "day0": iso(T - timedelta(60)),
                 "file": "cpi.json.gz", "fv": "000000000000", "apps": {rs.A[app]: dict(base, **rows)}, "counts": {},
                 "unlinked": {}, "alerts": [], "closed": []}
    return db


def ads_of(site_dir, db, app=4):
    doc = build_day(Site(site_dir, db), DAY, now=rs.NOW)
    check_doc(doc)
    a = next(x for x in doc["apps"] if x["app_id"] == rs.A[app])
    return a["f"]["ads"], a, doc


def test_alarm_is_red_with_the_numbers_the_reason_and_since(site):
    lost = {"inr": 8800.0, "usd": 100.0, "from": iso(SINCE - timedelta(20)), "sc": {"inr": 17600.0, "usd": 200.0}}
    ep = ["ROAS_G", "SUDDEN", "ALERT", iso(SINCE), iso(SINCE + timedelta(2)), 0.4]
    f, a, _ = ads_of(site, with_cpi(dash(site), {"st": "alarm", "since": iso(SINCE), "lost": lost, "open": [ep]}))
    assert f["st"] == "red"
    assert f["t"] == "Alarm (Sudden step in Day-0 ROAS): Day-0 ROAS 40.0% → 30.0%, CPI ₹40.0 → ₹44.0, since 23 Sep"
    q = f["q"]
    assert plain(q["kya"]) == f["t"] and q["kab"].startswith("23 Sep · ")
    assert plain(q["kit"]) == "≈$100 lost 15–28 Sep (Day-0 ROAS below normal) · since 3 Sep ≈$200"
    assert q["karo"].startswith("📉 CPI screen kholo")
    assert plain(q["kis"]) == "📉 CPI screen · Google Ads + AdMob 15–28 Sep · vs normal"
    assert a["tier"] == "red"                                      # the app's card goes red with it


def test_watch_amber_and_fixed_green(site):
    f, _, _ = ads_of(site, with_cpi(dash(site), {"st": "watch", "since": iso(SINCE),
                                            "open": [["CPI", "DRIFT", "WATCH", iso(SINCE), iso(SINCE), 40.0]]}))
    assert f["st"] == "amber"
    assert f["t"] == "Watch (Slow drift in CPI): CPI ₹40.0 → ₹44.0, Day-0 ROAS 40.0% → 30.0%, since 23 Sep"
    assert plain(f["q"]["kit"]).startswith("Spend $50 → $50")   # no money lost: the 7-day spend
    f, _, _ = ads_of(site, with_cpi(dash(site), {"st": "fixed", "since": iso(SINCE), "to": iso(T - timedelta(1))}))
    assert f["st"] == "green" and f["q"] is None
    assert f["t"] == "Fixed (alarm 23–27 Sep is over): CPI ₹40.0 → ₹44.0, Day-0 ROAS 40.0% → 30.0%"


@pytest.mark.parametrize("st,want,line", [
    ("ok", "normal", "📉 CPI screen: OK · CPI ₹44.0 (+10%) · eCPM "),
    ("new", "wait", "⏳ Too early — 📉 CPI screen: is app ka normal abhi nahi bana"),
    ("paused", "na", "Google Ads spend paused (no spend 26–28 Sep) · 📉 CPI screen"),
])
def test_ok_new_paused(site, st, want, line):
    f, a, _ = ads_of(site, with_cpi(dash(site), {"st": st}))
    assert f["st"] == want and f["q"] is None and f["t"].startswith(line), f["t"]
    if st == "ok":
        assert f["t"].endswith("· Day-0 ROAS 30.0% (−25%) (15–28 Sep)")


def test_no_pointer_row_or_a_bad_pointer_keeps_the_7_vs_7_rule(site):
    db = dash(site)
    f0, _, d0 = ads_of(site, db)
    assert f0["st"] == "normal" and f0["t"].startswith("Spend $50")
    other = with_cpi(db, {"st": "alarm", "since": iso(SINCE)}, app=1)   # a pointer row for another app only
    other["roas"] = db["roas"]                                            # (app 4's own inputs as before)
    f1, _, d1 = ads_of(site, other)
    assert f1 == f0
    for bad in ({"v": 2, "t": iso(T), "apps": {}}, {"v": 1, "t": "not a day", "apps": {}}, "x",
                {"v": 1, "t": iso(T), "apps": {rs.A[4]: {"st": "unknown"}}}):
        b = copy.deepcopy(db)
        b["cpi"] = bad
        f2, _, d2 = ads_of(site, b)
        assert f2 == f0
        assert json.dumps(d2["apps"], sort_keys=True) == json.dumps(d0["apps"], sort_keys=True)


def test_the_review_reads_this_builds_pointer():
    """build_static: the cpi step (it writes dashboard["cpi"]) runs before the review step in the same build."""
    src = inspect.getsource(build_static)
    i_cpi = src.index("aud_paths = aud_paths + _cpi_step(dashboard, data_dir, out_dir, s)")
    i_rv = src.index("review_paths = _review_step(dashboard, data_dir, out_dir)")
    assert i_cpi < i_rv
