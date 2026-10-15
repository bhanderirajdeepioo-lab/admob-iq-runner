"""🔮 Forecast engine vd — installs by country (forecast_vd cs_*; held off in the forecast: STRUCT cs 0) and the
"Budget by country" planner (cs_plan → forecast_build.plan_out) on a made-up app (tests/test_forecast_engine's: 1,000
organic + $500 a day of paid installs) whose Google Ads spend goes to two made-up countries AA (cheap) and BB (twice
the CPI). Checked: the pooled e (the slope a made-up CPI ∝ spend^e gives back, only from pairs known at T), the training
weeks' model (stale / partial data → none), the forecast untouched by country data with cs 0, the paid installs with
cs 1 (the training mix and level = the engine's per_usd × spend exactly; a raise), the revenue NOT moved by any of it,
the back-test never reading a future week's country shares, the planner (rows by spend, today's spend buying per_usd ×
spend, one revenue per $ for every country = the forecast's own) and the build's inputs. No real data."""
import math
from datetime import date, timedelta

import os
from datetime import datetime, timezone

from admob_iq import forecast_build as fb
from admob_iq.engine import forecast as F
from admob_iq.engine import forecast_vd as VD
from tests.test_forecast_engine import LAST, make, with_uninstalls
from tests.test_forecast_vd import with_ga4

T0 = date(2025, 9, 1)
CPI = {"AA": 0.4, "BB": 0.8}                  # $300 a day at $0.40 + $200 at $0.80 = 1,000 paid installs for $500


def mon(D):
    return D - timedelta(days=D.weekday())


def geo_of(app, shares=None, upto=None):
    """Google Ads country weeks matching the app's spend: {Monday: {cc: [USD, downloads]}}; shares {Monday: {cc: q}}
    overrides a week's split (its downloads at the countries' own CPIs)."""
    out = {}
    for D, e in app["days"].items():
        if upto and D > upto:
            continue
        W = mon(D)
        sh = (shares or {}).get(W) or {"AA": 0.6, "BB": 0.4}
        c = out.setdefault(W, {})
        for cc, q in sh.items():
            v = c.setdefault(cc, [0.0, 0.0])
            v[0] += e["sp"] * q
            v[1] += e["sp"] * q / CPI[cc]
    return out


def stores_with_e(e, n_weeks=60, start=date(2024, 6, 3), flip=None):
    """Made-up stores whose country CPI ∝ spend^e exactly (spend steps every 4 weeks); flip (Monday, e2): e2 after it."""
    out = {}
    for s in range(6):
        geo = {}
        for w in range(n_weeks):
            W = start + timedelta(weeks=w)
            blk = w // 4
            for k, cc in enumerate(("AA", "BB", "CC")):
                lvl = 1000.0 * (1.0 + 0.5 * math.sin(blk * 1.3 + s + k))           # USD a week, moving block to block
                ee = flip[1] if flip and W >= flip[0] else e
                cpi = 0.5 * (lvl / 1000.0) ** ee
                geo.setdefault(W, {})[cc] = [lvl, lvl / cpi]
        out["s%d" % s] = geo
    return out


def with_geo(app, **kw):
    app["geo"] = geo_of(app, **kw)
    app["cs_pairs"] = VD.cs_pairs(stores_with_e(0.2), LAST)
    return app


def tot(f, n=None):
    v = [a + b + c for a, b, c in zip(f["rev"]["old"], f["rev"]["org"], f["rev"]["paid"])]
    return sum(v[:n] if n else v)


def test_the_pooled_e_is_the_slope_and_known_at_t_only():
    pairs = VD.cs_pairs(stores_with_e(0.2), date(2026, 1, 1))
    e, n = VD.cs_e(pairs, date(2026, 1, 1))
    assert abs(e - 0.2) < 0.01 and n > 100                                # (4-week blocks across a spend step: ≈)
    assert VD.cs_e(pairs, date(2024, 6, 1)) == (0.0, 0)                  # nothing known yet: no e
    # a later change of e moves nothing known before its pairs ended (known = the later block's end)
    fl = VD.cs_pairs(stores_with_e(0.2, flip=(date(2025, 3, 3), 0.45)), date(2026, 1, 1))
    assert VD.cs_e(fl, date(2025, 3, 3)) == VD.cs_e(pairs, date(2025, 3, 3)) and VD.cs_e(fl, date(2026, 1, 1))[0] > 0.25
    assert VD.cs_e(VD.cs_pairs(stores_with_e(0.9), date(2026, 1, 1)), date(2026, 1, 1))[0] == VD.CS_EMAX   # clipped
    assert VD.cs_e(None, date(2026, 1, 1)) == (0.0, 0)


def test_the_training_weeks():
    app = make()
    geo = geo_of(app)
    cm = VD.cs_model(geo, T0)
    assert [W.weekday() for W in cm["weeks"]] == [0, 0] and cm["weeks"][-1] + timedelta(days=6) <= T0
    assert abs(sum(cm["share"][k] * cm["rho"][k] for k in cm["rho"]) - 1) < 1e-12          # ρ = 1 at the training mix
    assert 1.9 < cm["rho"]["AA"] / cm["rho"]["BB"] < 2.0                  # the cheap country (shrunk a little to the app)
    assert abs(cm["sbar"]["AA"] - 300) < 1e-9 and abs(cm["sbar"]["BB"] - 200) < 1e-9
    assert VD.cs_model(geo_of(app, upto=T0 - timedelta(days=30)), T0) is None              # stale: its newest weeks gone
    bad = geo_of(app)
    bad[cm["weeks"][0]]["BB"][1] = None                                   # a downloads count unknown
    assert VD.cs_model(bad, T0) is None and VD.cs_model({}, T0) is None


def test_the_forecast_holds_the_country_model_off_and_revenue_never_moves():
    plain = with_uninstalls(with_ga4(make()))
    app = with_geo(with_uninstalls(with_ga4(make())))
    sp = {T0 + timedelta(days=i): 500.0 for i in range(1, 61)}
    f0, f1 = VD.forecast(plain, T0, {}, h=60, spend=sp), VD.forecast(app, T0, {}, h=60, spend=sp)
    assert VD.STRUCT["cs"] == 0                                           # did not win at the shares a forecast knows
    assert all(f1[k] == f0[k] for k in ("n", "rev", "dau", "dau_p", "un"))   # country data: not a digit moves
    # cs 1 at the training weeks' mix and level ($300 AA + $200 BB a day): the engine's installs exactly
    f2 = VD.forecast(app, T0, {"cs": 1}, h=60, spend=sp)
    assert all(abs(a - b) < 1e-9 * max(1.0, a) for a, b in zip(f0["n"], f2["n"])) and f2["rev"] == f0["rev"]
    assert all(abs(a - b) < 1e-9 * a for a, b in zip(f0["dau"], f2["dau"]))


def test_a_raise_buys_fewer_installs_per_dollar():
    app = with_geo(with_ga4(make()))
    e = VD.cs_e(app["cs_pairs"], T0)[0]
    sp1 = {T0 + timedelta(days=i): 500.0 for i in range(1, 31)}
    sp2 = {D: 1000.0 for D in sp1}
    f1, f2 = VD.forecast(app, T0, {"cs": 1}, h=30, spend=sp1), VD.forecast(app, T0, {"cs": 1}, h=30, spend=sp2)
    r = (f2["n"][5] - 1000) / (f1["n"][5] - 1000)
    assert abs(r - 2 ** (1 - e)) < 1e-9 and r < 2 and abs(e - 0.2) < 0.01   # every country × 2: installs × 2^(1−e)
    assert all(abs(b - 2 * a) < 1e-9 * max(1.0, b) for a, b in zip(f1["rev"]["paid"], f2["rev"]["paid"]))
    assert sum(f2["dau_p"]["paid"]) > sum(f1["dau_p"]["paid"])


def test_the_backtest_never_reads_a_future_weeks_country_shares():
    # after T0 the money went to the cheap country: a back-test from T0 must not know it (the live forecast can't)
    app = with_ga4(make())
    with_geo(app, shares={mon(D): {"AA": 1.0} for D in app["days"] if D > T0})
    cut = with_geo(with_ga4(make()), upto=T0)                             # the same app, its country weeks cut at T0
    for p in ({"cs": 1}, {}):
        assert VD.backtest(app, p, ors=[T0]) == VD.backtest(cut, p, ors=[T0])
    # held off (cs 0): the back-test = the app without any country data
    assert VD.backtest(app, {}, ors=[T0]) == VD.backtest(with_ga4(make()), {}, ors=[T0])


def test_the_planner_matches_the_forecast():
    app = with_ga4(make())
    for i in range(7):
        app["days"][T0 - timedelta(days=i)]["sp"] = 600.0                 # today's run-rate: $600 a day
    with_geo(app)
    org, pu = F.installs_model(app["days"], T0, F.SPEND_DAYS)
    f = VD.forecast(app, T0, {}, h=F.H)
    pl = f["plan"]
    assert pl and [x["cc"] for x in pl["rows"]] == ["AA", "BB"] and abs(pl["s"] - 600) < 1e-9 and pl["fc"] == 0
    assert abs(sum(x["s0"] for x in pl["rows"]) - 600) < 1e-9
    # the training weeks spent less ($3,500 + $4,100 in 14 days); today's spend still buys per_usd × spend (the CPI
    # moves from today's level, not from theirs) — the planner's today = the forecast's paid installs
    assert abs(sum(app["_fv_cs"][T0]["cm"]["sbar"].values()) - 7600 / 14) < 1e-9          # (the kept model intact)
    assert abs(pl["n0"] / (pu * 600) - 1) < 1e-12 and abs((f["n"][0] - org) / (pu * 600) - 1) < 1e-12
    assert all(abs(x["sb"] / x["s0"] - 1) < 1e-12 for x in pl["rows"])
    f1 = VD.forecast(app, T0, {"cs": 1}, h=30)                            # cs 1: the forecast's own installs the same
    assert abs((f1["n"][0] - org) / (pu * 600) - 1) < 1e-12 and f1["plan"]["fc"] == 1
    fac = fb.corrected(f["rev"], {30: {"bias": 0.1}})
    out = fb.plan_out(pl, f, fac)
    for j, hz in enumerate(out["h"]):
        paid = sum(v * fac[i] for i, v in enumerate(f["rev"]["paid"][:hz]))
        assert abs(sum(x["s0"] * x["r"][j] for x in out["rows"]) / paid - 1) < 1e-5     # rows add up to the forecast
        assert len({x["r"][j] for x in out["rows"]}) == 1                 # one revenue per $ for every country
    a, b = out["rows"]
    assert a["ppu"] > b["ppu"] and a["lo"] <= 300 < a["hi"] and out["fc_cs"] == 0 and "beta" not in out
    assert out["old"][0] > 0 and fb.plan_out(f1["plan"], f1, fac[:30])["fc_cs"] == 1
    assert VD.forecast(with_ga4(make()), T0, {}, h=30).get("plan") is None           # no country data: no planner
    # an app spending less than CS_MIN a day: no planner (its run-rate installs per $ say nothing)
    for i in range(7):
        app["days"][T0 - timedelta(days=i)]["sp"] = VD.CS_MIN / 2
    app.pop("_fv_cs", None)
    assert VD.forecast(app, T0, {}, h=30)["plan"] is None


def test_the_rows_beyond_the_top_go_to_other():
    app = with_ga4(make())
    ccs = ["C%d" % i for i in range(12)]
    app["ida"] = {"cset": ccs + ["ZZ"]}
    CPI.update({cc: 0.5 + 0.05 * i for i, cc in enumerate(ccs)})
    try:
        W = {mon(D) for D in app["days"]}
        with_geo(app, shares={w: {cc: (12 - i) / 78.0 for i, cc in enumerate(ccs)} for w in W})
        pl = VD.forecast(app, T0, {}, h=30)["plan"]
        names = [x["cc"] for x in pl["rows"]]
        assert names == ccs[:VD.CS_TOP] + ["OT"]
        assert abs(sum(x["s0"] for x in pl["rows"]) - pl["s"]) < 1e-9
        # rows by spend, a GA4 slot or not (one revenue per $ for all); "XX" (no country) only inside Other
        app2 = with_ga4(make())
        CPI["XX"] = 0.6
        with_geo(app2, shares={w: {"AA": 0.5, "XX": 0.3, "BB": 0.2} for w in W})
        rows = VD.forecast(app2, T0, {}, h=30)["plan"]["rows"]
        assert [x["cc"] for x in rows] == ["AA", "BB", "OT"] and abs(rows[-1]["s0"] - 150) < 1e-9
    finally:
        for cc in ccs + ["XX"]:
            CPI.pop(cc, None)


def test_the_build_inputs():
    gw = {"s1": {"2025-08-25": {"AA": [3_000_000, 10.0], "BB": [1_000_000, None]}},
          "s2": {"2025-08-25": {"AA": [1_000_000, 5.0]}}, "s3": {"2025-08-25": {"AA": [9_000_000, 1.0]}}}
    g = fb.geo_weeks(gw, ["s1", "s2"], lambda d: 0.5 if d == date(2025, 8, 28) else None)
    assert g == {date(2025, 8, 25): {"AA": [2.0, 15.0], "BB": [0.5, None]}}           # USD at the week's rate (Mon + 3)
    run = fb.start("/nonexistent", None)
    assert fb.cs_pairs(run, {"weeks": {}, "till": "2025-09-01"}, lambda d: 1.0) is None and run.cs is False
    run2 = fb.start("/nonexistent", None)
    p = fb.cs_pairs(run2, {"weeks": gw, "till": "2025-09-01"}, lambda d: 1.0)
    assert p is not None and fb.cs_pairs(run2, None, None) is p                       # once per build


def test_the_build_step_carries_the_planner(tmp_path):
    from tests.test_forecast_build import Clock, _rows_life
    data = str(tmp_path / "data")
    os.makedirs(data)
    app = make()
    rows, life, ida = _rows_life(app, ga4=True)
    ida["cset"] = ["AA", "BB", "ZZ"]
    now = datetime(2026, 1, 2, 6, tzinfo=timezone.utc)
    run = fb.start(data, now, Clock())
    geo = geo_of(app)
    pairs = VD.cs_pairs(stores_with_e(0.2), LAST)
    fc = fb.app_step(run, "a~1", "k1", rows, {"S": LAST}, ida, life, LAST.isoformat(), [], geo=geo, cs_pairs=pairs)
    pl = fc["plan"]
    assert pl and [x["cc"] for x in pl["rows"]] == ["AA", "BB"] and pl["fc_cs"] == 0
    assert pl["rows"][0]["r"] == pl["rows"][1]["r"]
    assert abs(sum(x["s0"] * x["r"][2] for x in pl["rows"]) / pl["paid"][2] - 1) < 1e-3     # rows = the forecast's paid
    assert abs(pl["old"][0] + pl["orgr"][0] + pl["paid"][0] - sum(
        fc["f"][k][i] for k in ("old", "org", "paid") for i in range(30))) < 0.5              # the page's own series
    assert fb.line(run).endswith("budget planner 1")
    # the next build keeps the run (same day) and still carries the planner; no country data: no planner
    run2 = fb.start(data, now, Clock())
    assert fb.app_step(run2, "a~1", "k1", rows, {"S": LAST}, ida, life, LAST.isoformat(), [], geo=geo,
                       cs_pairs=pairs)["plan"] and run2.kept == 1 and run2.plans == 1
    assert fb.app_step(fb.start(data, now, Clock()), "a~1", "k1", rows, {"S": LAST}, ida, life, LAST.isoformat(),
                       [])["plan"] is None
