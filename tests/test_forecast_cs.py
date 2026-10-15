"""🔮 Forecast engine vd — installs by country (forecast_vd cs_*, STRUCT cs 1) and the "Budget by country" planner
(cs_plan → forecast_build.plan_out) on a made-up app (tests/test_forecast_engine's: 1,000 organic + $500 a day of paid
installs) whose Google Ads spend goes to two made-up countries AA (cheap) and BB (twice the CPI). Checked: the pooled
e (the slope a made-up CPI ∝ spend^e gives back, only from pairs known at T), the training weeks' model (stale / partial
data → none), the paid installs (today's mix and spend = the engine's per_usd × spend exactly; a mix move, a raise),
the revenue NOT moved by any of it (only installs / users / uninstalls), the back-test fed the real country shares, the
planner (rows, its revenue = the forecast's own at today's plan) and the build's inputs. No real data."""
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


def test_todays_mix_is_the_engine_and_revenue_never_moves():
    plain = with_uninstalls(with_ga4(make()))
    app = with_geo(with_uninstalls(with_ga4(make())))
    sp = {T0 + timedelta(days=i): 500.0 for i in range(1, 61)}
    f0, f1 = VD.forecast(plain, T0, {}, h=60, spend=sp), VD.forecast(app, T0, {}, h=60, spend=sp)
    assert all(abs(a - b) < 1e-9 * max(1.0, a) for a, b in zip(f0["n"], f1["n"]))          # same mix, same spend
    assert f0["rev"] == f1["rev"] and all(abs(a - b) < 1e-9 * a for a, b in zip(f0["dau"], f1["dau"]))
    # all spend to the cheap country: more installs, users and uninstalls — the revenue exactly the engine's
    W = {mon(T0 + timedelta(days=i)) for i in range(1, 61)}
    app2 = with_geo(with_uninstalls(with_ga4(make())), shares={w: {"AA": 1.0} for w in W})
    f2 = VD.forecast(app2, T0, {}, h=60, spend=sp)
    assert f2["rev"] == f0["rev"]
    paid0, paid2 = f0["n"][10] - 1000, f2["n"][10] - 1000
    cs = app2["_fv_cs"][T0]
    want = cs["cm"]["rho"]["AA"] * (500 / 300) ** -cs["e"]                # AA's installs per $ (≈ ×1.25) at 5/3 its spend
    assert abs(paid2 / paid0 - want) < 1e-9 and 1.24 < cs["cm"]["rho"]["AA"] < 1.25 and abs(cs["e"] - 0.2) < 0.01
    assert sum(f2["dau_p"]["paid"]) > sum(f0["dau_p"]["paid"]) and sum(f2["un"]["paid"]) > sum(f0["un"]["paid"])
    assert f2["dau_p"]["old"] == f0["dau_p"]["old"] and f2["dau_p"]["org"] == f0["dau_p"]["org"]
    # the country model off (cs 0) = no country data at all
    f3 = VD.forecast(app2, T0, {"cs": 0}, h=60, spend=sp)
    assert f3["n"] == f0["n"] and f3["rev"] == f0["rev"]


def test_a_raise_buys_fewer_installs_per_dollar():
    app = with_geo(with_ga4(make()))
    e = VD.cs_e(app["cs_pairs"], T0)[0]
    sp1 = {T0 + timedelta(days=i): 500.0 for i in range(1, 31)}
    sp2 = {D: 1000.0 for D in sp1}
    f1, f2 = VD.forecast(app, T0, {}, h=30, spend=sp1), VD.forecast(app, T0, {}, h=30, spend=sp2)
    r = (f2["n"][5] - 1000) / (f1["n"][5] - 1000)
    assert abs(r - 2 ** (1 - e)) < 1e-9 and r < 2                         # every country × 2: installs × 2^(1−e)
    assert all(abs(b - 2 * a) < 1e-9 * max(1.0, b) for a, b in zip(f1["rev"]["paid"], f2["rev"]["paid"]))


def test_the_backtest_reads_the_real_country_shares():
    # the truth: from T0 on the money goes to the cheap country — the paid installs follow its CPI
    app = with_ga4(make())
    W = sorted({mon(D) for D in app["days"] if D > T0 - timedelta(days=6)})
    shares = {w: {"AA": 1.0} for w in W if w > T0}
    for D, e in app["days"].items():
        if D > T0 and mon(D) in shares:
            e["na"] = e["sp"] / CPI["AA"]
            e["n"] = 1000 + e["na"]
    with_geo(app, shares=shares)
    bt = VD.backtest(app, {}, ors=[T0])
    plain = {k: v for k, v in app.items() if k not in ("geo", "cs_pairs") and not k.startswith("_")}
    bt0 = VD.backtest(plain, {}, ors=[T0])
    assert abs(bt[0]["h"][30]["n_err"]) < 0.6 * abs(bt0[0]["h"][30]["n_err"])
    assert bt[0]["h"][30]["pred"] == bt0[0]["h"][30]["pred"]               # the revenue: the engine's own


def test_the_planner_matches_the_forecast():
    app = with_ga4(make())
    app["ida"] = {"cset": ["AA", "BB", "ZZ"]}                            # both countries have their own GA4 slot
    for i in range(7):
        app["days"][T0 - timedelta(days=i)]["sp"] = 600.0                 # today's run-rate: $600 a day
    with_geo(app)
    f = VD.forecast(app, T0, {}, h=F.H)
    pl = f["plan"]
    assert pl and [x["cc"] for x in pl["rows"]] == ["AA", "BB"] and abs(pl["s"] - 600) < 1e-9
    assert abs(sum(x["s0"] for x in pl["rows"]) - 600) < 1e-9 and all(abs(sum(x["w"][j] for x in pl["rows"]) - 1) < 1e-9
                                                                       for j in range(3))
    assert abs(pl["n0"] - (f["n"][0] - pl["org"])) < 1e-9                 # today's plan = the forecast's paid installs
    fac = fb.corrected(f["rev"], {30: {"bias": 0.1}})
    out = fb.plan_out(pl, f, fac, (-0.19, -0.07, -0.03))
    for j, hz in enumerate(out["h"]):
        paid = sum(v * fac[i] for i, v in enumerate(f["rev"]["paid"][:hz]))
        assert abs(sum(x["s0"] * x["r"][j] for x in out["rows"]) / paid - 1) < 1e-5     # rows add up to the forecast
    a, b = out["rows"]
    assert a["ppu"] > b["ppu"] and a["lo"] <= 300 < a["hi"] and out["beta"] == [-0.19, -0.07, -0.03]
    # past install days / organic stay; every country its own curve: no GA4 slots here → one pooled value each
    assert out["old"][0] > 0 and abs(a["r"][0] / b["r"][0] - a["ppu"] / b["ppu"]) < 1e-3
    assert VD.forecast(with_ga4(make()), T0, {}, h=30).get("plan") is None           # no country data: no planner
    # a country without its own GA4 slot has no curve of its own: it is planned only inside "Other" (pooled curve)
    app["ida"] = {"cset": ["AA", "ZZ"]}
    app.pop("_fv_cs", None)
    pl2 = VD.forecast(app, T0, {}, h=30)["plan"]
    assert [(x["cc"], x["own"]) for x in pl2["rows"]] == [("AA", 1), ("OT", 0)] and abs(pl2["cov"] - 0.6) < 1e-9
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
        assert names == ccs[:VD.CS_TOP] + ["OT"] and pl["rows"][-1]["own"] == 0
        assert abs(sum(x["s0"] for x in pl["rows"]) - pl["s"]) < 1e-9
    finally:
        for cc in ccs:
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
    fc = fb.app_step(run, "a~1", "k1", rows, {"S": LAST}, ida, life, LAST.isoformat(), [], geo=geo, cs_pairs=pairs,
                     beta=[-0.19, -0.07, -0.03])
    pl = fc["plan"]
    assert pl and [x["cc"] for x in pl["rows"]] == ["AA", "BB"] and pl["beta"] == [-0.19, -0.07, -0.03]
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
