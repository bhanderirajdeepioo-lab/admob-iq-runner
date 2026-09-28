"""The Install value tab's country cost input (admob_iq.value_build._load_geo / _app_geo week path; SPEC_CD_GEO §G.8):
the Google Ads country cache (fetch.gads_geo, week grain) → the engine's week envelope — only the app's own spend
store ids, USD at each week's spend-weighted rate (so Σ countries = coverage × the week's USD spend), coverage over
base micros, a store week never fetched is not covered, and the prepass key set unchanged. All data is synthetic."""

import json
import os
from datetime import date, timedelta

import pytest

from admob_iq import value_build as vb
from admob_iq.engine import value as val
from admob_iq.fetch import gads_geo as gg

S1, S2, SX = "com.synth.app", "com.synth.app.lite", "com.synth.other"
M = 1_000_000
TILL = "2026-09-20"                                     # a Sunday: the install data's last day
FX = {"mode": "dated", "now": 0.0119, "series": {"2026-05-01": 0.0120, "2026-09-02": 0.0125, "2026-09-05": 0.0110,
                                                 "2026-09-09": 0.0115}}


def days(a, b):
    a, b = date.fromisoformat(a), date.fromisoformat(b)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def spend_cache():
    """S1 and S2 are the app's (S2 a sibling listing the ROAS map gives the same app), SX another app's."""
    daily = {S1: {d: 1000 * M for d in days("2026-06-01", "2026-09-20")},
             S2: {d: 300 * M for d in days("2026-08-31", "2026-09-02")},
             SX: {d: 700 * M for d in days("2026-06-01", "2026-09-20")}}
    daily[S1].update({d: 0 for d in days("2026-09-14", "2026-09-20")})   # a week without spend
    return {"ccy": "INR", "daily": daily, "installs": {}, "first": "2026-06-01", "till": "2026-09-20",
            "till_src": "fetch"}


def geo_cache():
    c = gg.fresh("INR")
    c.update(first="2026-05-18", till="2026-09-23", done=True, _ts=1)
    w = {}
    for W in (date(2026, 5, 18) + timedelta(weeks=k) for k in range(18)):
        k = W.isoformat()
        w[k] = {"US": [4200 * M, 60.0], "IN": [2100 * M, 90.5], "XX": [630 * M, 1.25]}   # 6930 of 7000: cov 0.99
    w["2026-09-14"] = {}                                                # nothing spent that week
    w["2026-09-07"] = {"US": [5 * M, 1.0]}                              # country cost without campaign cost
    c["weeks"] = {S1: w,
                  S2: {"2026-08-31": {"US": [600 * M, 10.0], "BR": [300 * M, None]}},
                  SX: {k: {"US": [99999 * M, 999.0]} for k in w}}
    return c


def pre_of(geo=None, spend=None):
    return {"geo": geo if geo is not None else geo_cache(), "spend": spend or spend_cache(),
            "owner": {S1: "App X", S2: "App X", SX: "Other"}, "siblings": {}, "aliases": {}, "fx": FX}


APP, STORE = {"app_name": "App X", "package": S1}, {"package": S1}


def test_app_geo_week_envelope_rate_and_coverage():
    pre = pre_of()
    env = vb._app_geo(pre, APP, STORE, FX, TILL)
    assert env["v"] == 2 and env["ccy"] == "INR" and (env["first"], env["till"]) == ("2026-05-18", "2026-09-23")
    t = date.fromisoformat(TILL)
    lo = t - timedelta(days=vb.GEO_DAYS)
    lo -= timedelta(days=lo.weekday())
    assert sorted(env["weeks"]) == [(lo + timedelta(weeks=k)).isoformat() for k in range(len(env["weeks"]))]
    assert min(env["weeks"]) == lo.isoformat() and max(env["weeks"]) == "2026-09-14"
    f, _ = val._fx_fn(FX, "INR")
    e = env["weeks"]["2026-08-31"]                                      # S1 7 days + S2 3 days, rates moving in the week
    sp = [(d, 1000 * M + (300 * M if d <= "2026-09-02" else 0)) for d in days("2026-08-31", "2026-09-06")]
    rate = sum(v * f(date.fromisoformat(d)) for d, v in sp) / sum(v for _, v in sp)
    assert e["rate"] == pytest.approx(rate) and e["rate"] != f(date(2026, 8, 31))
    assert e["spend"] == pytest.approx(7900 * M * rate / M)
    assert e["cov"] == pytest.approx((6930 + 900) / 7900)              # base micros, the app's stores only
    assert e["geo"] == pytest.approx(e["cov"] * e["spend"])            # Σ countries = cov × the week's USD spend
    assert sum(v[0] for v in e["by"].values()) == pytest.approx(e["geo"])
    assert set(e["by"]) == {"US", "IN", "XX", "BR"}                     # never another app's store (SX)
    assert e["by"]["US"] == [pytest.approx(4800 * rate), pytest.approx(70.0), pytest.approx(4800)]   # + the billed ₹
    assert e["by"]["BR"][1] is None and e["dl_ok"] is False            # downloads unknown stays unknown
    assert e["whole"] is True
    # the rounding the cache can explain: half a paisa for each of ≥ GEO_TOL_CELLS countries of each store-week
    assert e["tol"] == pytest.approx(2 * vb.GEO_TOL_CELLS * gg.GEO_MICROS_Q / 2 * rate / M)
    e = env["weeks"]["2026-08-24"]                                      # one store, steady spend: cov 0.99
    assert e["cov"] == pytest.approx(0.99) and e["dl_ok"] is True and e["by"]["IN"][1] == pytest.approx(90.5)
    assert env["weeks"]["2026-09-14"]["cov"] == 1.0 and env["weeks"]["2026-09-14"]["spend"] == 0   # none on both sides
    assert env["weeks"]["2026-09-14"]["rate"] == pytest.approx(sum(f(date(2026, 9, 14) + timedelta(days=i))
                                                                    for i in range(7)) / 7)
    assert env["weeks"]["2026-09-07"]["cov"] == pytest.approx(5 / 7000)
    assert vb._app_geo(pre, APP, STORE, FX, TILL, spend=vb.app_spend(pre, APP, STORE)) == env   # spend= handed over


def test_app_geo_whole_needs_both_caches_and_a_rate():
    pre = pre_of()
    g = pre["geo"]
    g["first"] = "2026-06-08"
    g["till"] = "2026-09-16"
    env = vb._app_geo(pre, APP, STORE, FX, TILL)
    assert env["weeks"]["2026-06-01"]["whole"] is False                 # before the geo cache's first week
    assert env["weeks"]["2026-06-08"]["whole"] is True
    assert env["weeks"]["2026-09-07"]["whole"] is True and env["weeks"]["2026-09-14"]["whole"] is False
    one = {"mode": "one", "now": None, "series": {}}                     # no rate at all: never whole, no USD
    env = vb._app_geo(pre, APP, STORE, one, TILL)
    e = env["weeks"]["2026-08-31"]
    assert e["whole"] is False and e["rate"] is None and e["spend"] is None and e["by"]["US"][0] is None
    assert e["cov"] == pytest.approx((6930 + 900) / 7900)               # coverage is money-free (base micros)
    usd = dict(spend_cache(), ccy="USD")
    env = vb._app_geo(pre_of(spend=usd), APP, STORE, one, TILL)
    assert env["weeks"]["2026-08-24"]["rate"] == 1.0 and env["weeks"]["2026-08-24"]["spend"] == pytest.approx(7000)


def test_app_geo_missing_store_week_is_not_ok():
    geo = geo_cache()
    del geo["weeks"][S2]                                                # S2 spent in that week, never fetched
    env = vb._app_geo(pre_of(geo), APP, STORE, FX, TILL)
    e = env["weeks"]["2026-08-31"]
    assert e["cov"] is None and e["whole"] is True                      # not ok (the engine's gate), never partial cost
    assert env["weeks"]["2026-08-24"]["cov"] == pytest.approx(0.99)     # S2 had no spend then: nothing missing
    geo["weeks"][S2] = {"2026-08-31": {}}                                # fetched, nothing returned: plain low coverage
    e = vb._app_geo(pre_of(geo), APP, STORE, FX, TILL)["weeks"]["2026-08-31"]
    assert e["cov"] == pytest.approx(6930 / 7900)
    geo = geo_cache()
    geo["weeks"] = {SX: geo["weeks"][SX]}                                # none of the app's stores in the cache
    env = vb._app_geo(pre_of(geo), APP, STORE, FX, TILL)
    spent = [e for e in env["weeks"].values() if e["spend"]]
    assert spent and all(e["cov"] is None and e["geo"] == 0 and e["by"] == {} for e in spent)
    assert env["in_cache"] == 0 and env["stores"] == 2
    none = pre_of()
    none["spend"] = None                                                 # no spend cache: no envelope (unknown)
    assert vb._app_geo(none, APP, STORE, FX, TILL) is None
    assert vb._app_geo(pre_of(), APP, STORE, FX, None) is None


def test_prepass_keys_unchanged_with_geo_on(tmp_path):
    data = str(tmp_path / "data")
    os.makedirs(data)
    with open(os.path.join(data, vb.SPEND_FILE), "w", encoding="utf-8") as f:
        json.dump({"v": 2, "currency_src": "INR", "daily": spend_cache()["daily"], "installs": {}}, f)
    keys = {"data_dir", "spend", "aliases", "owner", "siblings", "fx", "ded", "geo", "portfolio_shape"}
    on = dict(vb.cfg_from({"gads_geo": True}), store_owner={S1: "App X"})
    pre = vb.prepass(data, [], None, {}, on, vb.load_state(data))
    assert set(pre) == keys and pre["geo"] is None                       # on, no cache yet: none
    c = geo_cache()
    gg.save_geo(data, c)
    assert os.path.exists(gg.paths(data)[1])                             # the old weeks live in the .old part
    pre = vb.prepass(data, [], None, {}, on, vb.load_state(data))
    assert set(pre) == keys and pre["geo"]["weeks"] == c["weeks"] and pre["geo"]["till"] == "2026-09-23"
    off = dict(vb.cfg_from({"gads_geo": False}), store_owner={S1: "App X"})
    pre = vb.prepass(data, [], None, {}, off, vb.load_state(data))
    assert set(pre) == keys and pre["geo"] is None                       # GADS_GEO off: never read
    assert not os.path.exists(os.path.join(data, vb.GEO_FILE))           # the old day-grain name is never written
