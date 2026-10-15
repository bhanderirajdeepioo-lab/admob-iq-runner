"""🔮 Forecast engine vd (admob_iq.engine.forecast_vd) on a made-up app whose truth is known (tests/test_forecast_engine's:
2,000 installs a day, 1,000 organic + $500 at $0.50, every install day earns a(age) and keeps u(age) users) + its GA4
day ledger (revenue and active users by install-age band, landing 5 days after AdMob). Checked: the page's contract
(the same keys as engine v0), both views and their mix meet the truth, the spend slider is exact, no look-ahead (the
data after T — and GA4 after T − lag — can not move anything), the AdMob-only move q, the back-test objective / tune /
calibration, the portfolio band ratios, and an app without GA4. No real data."""
import math
from datetime import date, timedelta

from admob_iq.engine import forecast as F
from admob_iq.engine import forecast_vd as VD
from tests.test_forecast_engine import LAST, a_true, make, u_true, with_uninstalls

GB = ((0, 0), (1, 6), (7, 29), (30, 89), (90, 364), (365, 427))
GIX = [next((j for j, (lo, hi) in enumerate(GB) if lo <= L <= hi), None) for L in range(800)]
T0 = date(2025, 9, 1)


def with_ga4(app, lag=5, k=1.0):
    """+ g4 {day: {rev, rb[6], ab[6], k}} (GA4 = AdMob ÷ k), to `lag` days before the newest AdMob day."""
    g4 = {}
    for D in sorted(app["days"]):
        if D > app["last"] - timedelta(days=lag):
            continue
        rb, ab = [0.0] * 6, [0.0] * 6
        for X, c in app["coh"].items():
            if X > D:
                continue
            L = (D - X).days
            j = GIX[L]
            if j is None:
                continue
            rb[j] += c["n"] * a_true(L) / k
            ab[j] += c["n"] * u_true(L)
        G = sum(rb)
        g4[D] = {"rev": G, "rb": rb, "ab": ab, "k": app["days"][D]["rev"] / G}
    app.update(g4=g4, glag=lag, ida={})
    return app


def total(f, n=None):
    v = [a + b + c for a, b, c in zip(f["rev"]["old"], f["rev"]["org"], f["rev"]["paid"])]
    return sum(v[:n] if n else v)


def act(app, T, n):
    return sum(app["days"][T + timedelta(days=i)]["rev"] for i in range(1, n + 1))


def trunc(app, T):
    """The app as it stood at T: every dated input after T removed (GA4 after T − lag too)."""
    b = {k: v for k, v in app.items() if not k.startswith("_")}
    b["days"] = {D: dict(e) for D, e in app["days"].items() if D <= T}
    for D, e in b["days"].items():
        if D > T - timedelta(days=app["glag"]):
            e.pop("dau", None)
    b["g4"] = {D: e for D, e in app["g4"].items() if D <= T - timedelta(days=app["glag"])}
    coh = {}
    for X, c in app["coh"].items():
        if X > T:
            continue
        lim = (T - X).days
        coh[X] = dict(c, d=[v if i <= lim else None for i, v in enumerate(c["d"])], df=min(c["df"], lim + 1),
                      u=[v if i <= lim else None for i, v in enumerate(c["u"])], uf=min(c["uf"], lim + 1),
                      t=[v if F.T_AGES[j] <= lim else None for j, v in enumerate(c["t"])],
                      ul=[v if F.ULAGS[j] <= lim else None for j, v in enumerate(c["ul"])])
    b["coh"] = coh
    return b


def test_the_page_contract_and_the_truth():
    app = with_ga4(make())
    f = VD.forecast(app, T0, {}, h=90, spend={T0 + timedelta(days=i): 500.0 for i in range(1, 91)})
    assert set(f) >= {"rev", "dau", "dau_p", "un", "n", "sp", "parts"} and f["un"] is None     # no Uninstall store
    assert all(len(f["rev"][k]) == 90 and len(f["dau_p"][k]) == 90 for k in ("old", "org", "paid"))
    pt = f["parts"]
    assert {"mix", "mix_on", "org", "per_usd", "lev", "ulev", "lam", "arp", "zu", "q", "qraw", "nv", "bo"} <= set(pt)
    assert abs(pt["org"] - 1000) < 1 and abs(pt["per_usd"] - 2.0) < 0.01 and pt["glag"] == 5 and pt["TG"] == "2025-08-27"
    assert abs(total(f, 30) / act(app, T0, 30) - 1) < 0.03 and abs(total(f) / act(app, T0, 90) - 1) < 0.04
    dau = sum(f["dau"][:30]) / sum(app["days"][T0 + timedelta(days=i)]["dau"] for i in range(1, 31))
    assert abs(dau - 1) < 0.03
    for i in (0, 45, 89):                                 # the parts add up to the totals
        assert abs(sum(f["dau_p"][k][i] for k in ("old", "org", "paid")) - f["dau"][i]) < 1e-6
    for p in ({"bo": 0.0, "bn": 0.0}, {"bo": 1.0, "bn": 1.0}):           # each view alone meets the truth too
        g = VD.forecast(app, T0, p, h=90, spend={T0 + timedelta(days=i): 500.0 for i in range(1, 91)})
        assert abs(total(g, 30) / act(app, T0, 30) - 1) < 0.05, p


def test_the_spend_slider_is_exact_and_todays_run_rate():
    app = with_ga4(with_uninstalls(make()))
    s1 = {T0 + timedelta(days=i): 500.0 for i in range(1, 61)}
    s2 = {D: 2 * v for D, v in s1.items()}
    f1, f2 = VD.forecast(app, T0, {}, h=60, spend=s1), VD.forecast(app, T0, {}, h=60, spend=s2)
    assert f1["rev"]["old"] == f2["rev"]["old"] and f1["rev"]["org"] == f2["rev"]["org"]
    assert all(abs(b - 2 * a) < 1e-9 * max(1.0, b) for a, b in zip(f1["rev"]["paid"], f2["rev"]["paid"]))
    assert all(abs(b - 2 * a) < 1e-9 * max(1.0, b) for a, b in zip(f1["dau_p"]["paid"], f2["dau_p"]["paid"]))
    assert f1["un"] and abs(sum(f2["un"]["paid"]) / sum(f1["un"]["paid"]) - 2) < 1e-9
    assert abs(f2["n"][0] - (1000 + 2 * 1000)) < 1
    # spend None = the last 7 days' mean spend, with THEIR installs per $
    for i in range(7):
        app["days"][T0 - timedelta(days=i)]["sp"] = 1000.0
    f3 = VD.forecast(app, T0, {}, h=30)
    assert f3["sp"][0] == 1000.0 and abs(f3["parts"]["per_usd"] - 1.0) < 1e-9 and abs(f3["n"][0] - 2000) < 1e-6


def test_no_look_ahead():
    """At T the full app and the app truncated at T (GA4 at T − 5) give the very same numbers: totals, every past
    install day's future revenue and users, every new install's value."""
    app = with_ga4(make())
    T = date(2025, 10, 5)
    sp = {T + timedelta(days=i): 500.0 for i in range(1, 91)}
    out = []
    for a in (app, trunc(app, T)):
        st = VD.prepare(a, T, VD.params({"bo": 0.5, "bn": 0.5, "cq": 1.0}), {})
        r = VD.total(st, dict(sp), 90)
        coh = [VD.cohort_rev(st, X, (T - X).days - 2, [365]) for X in sorted(app["coh"]) if X <= T - timedelta(days=3)]
        usr = [VD.cohort_users(st, X, [60, 90, 180]) for X in sorted(app["coh"]) if X <= T]
        new = [VD.new_value(st, T + timedelta(days=i), [30, 90, 180]) for i in range(1, 31)]
        out.append((r, coh, usr, new, st["q"]))
    assert out[0] == out[1]
    # … and GA4 after T − glag is never read (the back-tests see GA4 as late as the live build does)
    plain = {k: v for k, v in app.items() if not k.startswith("_")}       # (no kept parts carried over)
    late = dict(plain, g4={D: (dict(e, rb=[x * 3 for x in e["rb"]]) if T - timedelta(days=5) < D <= T else e)
                           for D, e in app["g4"].items()})
    early = dict(plain, g4={D: (dict(e, rb=[x * 3 for x in e["rb"]]) if D == T - timedelta(days=6) else e)
                            for D, e in app["g4"].items()})
    p = VD.params({"bo": 1.0, "bn": 1.0})
    base = VD.total(VD.prepare(dict(plain), T, p), dict(sp), 30)["rev"]
    assert VD.total(VD.prepare(late, T, p), dict(sp), 30)["rev"] == base
    assert VD.total(VD.prepare(early, T, p), dict(sp), 30)["rev"] != base


def test_q_carries_the_admob_only_move():
    """AdMob ×1.5 on the days GA4 has not reached yet: q measures it; cq 1 carries it, cq 0 does not."""
    app = with_ga4(make())
    T = date(2025, 10, 5)
    for i in range(5):
        app["days"][T - timedelta(days=i)]["rev"] *= 1.5
    sp = {T + timedelta(days=i): 500.0 for i in range(1, 31)}
    s1 = VD.prepare(app, T, VD.params({"cq": 1.0}))
    s0 = VD.prepare(app, T, VD.params({"cq": 0.0}))
    assert abs(s1["qraw"] - 1.5) < 0.05 and s1["nt"] == 5 and s0["q"] == 1.0
    assert abs(sum(VD.total(s1, dict(sp), 30)["rev"]) / sum(VD.total(s0, dict(sp), 30)["rev"]) - s1["qraw"]) < 1e-9


def test_backtest_objective_tune_calibrate():
    app = with_ga4(make())
    ors = F.origins(app)[-4:]
    bt = VD.backtest(app, {}, None, ors)
    assert len(bt) == 4 and all({"h", "ev", "coh", "usr", "new"} <= set(r) for r in bt)
    assert all(r["coh"] for r in bt) and any(r["new"] for r in bt)     # (the newest origin: no new install reached day 30)
    assert VD.objective(bt) < 0.06 and VD.score is VD.objective
    p, bt2, steps = VD.tune(app, None, start_p={"bo": 1.0, "hl": 7, "gone": 1}, passes=1)
    assert set(p) == set(VD.GRID) and all(p[k] in VD.GRID[k] for k in p) and steps[0]["p"]["bo"] == 1.0
    assert steps[-1]["score"] <= steps[0]["score"] and bt2
    cal = F.calibrate(bt2)
    assert cal[30]["mape"] < 0.05 and cal[30]["n"] >= F.MIN_TESTS


def test_the_portfolio_band_ratios():
    """bandr: per Monday, the median over apps of each band's revenue per active user ÷ the band before's — only apps
    with enough users in both bands, at least 3 apps, clipped; the engine reads the Monday at or before the day."""
    def pre(ratio, users=10000.0, days=200):
        d0 = date(2025, 1, 1)
        P = [[0.0] * 18]
        for _ in range(days):
            rb = [1.0 * ratio ** b for b in range(7)]
            ab = [1.0] * 7
            row = [x * users for x in rb] + [users] * 7 + [0.0, 0.0, 0.0, 1.0]
            row[7:14] = [users * x for x in ab]
            P.append([x + y for x, y in zip(P[-1], row)])
        return {"d0": d0, "nd": days, "P": P}
    br = VD.bandr([pre(0.5), pre(0.8), pre(0.9), pre(3.0, users=10.0)])   # the last: too few users, left out
    M = max(br)
    assert abs(br[M][1] - 0.8) < 1e-12 and br[M][0] == 1.0
    assert VD.bandr([pre(0.5), pre(0.8)])[M] == [1.0] * 7                  # fewer than 3 apps: 1
    assert VD.bandr([pre(3.0), pre(3.0), pre(3.0)])[M][3] == 2.0             # clipped
    ix = VD._bandr_index(br)
    first = min(br)
    assert VD._port_ratio({"bandr": ix}, date.fromisoformat(M) + timedelta(days=30)) == br[M]   # a newer Monday: the last
    assert VD._port_ratio({"bandr": ix}, date.fromisoformat(first) - timedelta(days=1)) == [1.0] * 7
    assert VD._port_ratio({"bandr": None}, date.fromisoformat(M)) == [1.0] * 7


def test_without_ga4_view_a_alone():
    """No GA4 day ledger yet: view B has nothing to measure ARPDAU on — the forecast is view A's (one level)."""
    app = make()
    f = VD.forecast(app, T0, {"bo": 0.5, "bn": 0.5}, h=90, spend={T0 + timedelta(days=i): 500.0 for i in range(1, 91)})
    assert "arp" not in f["parts"] and f["parts"]["level_mode"] == "single"
    assert abs(total(f, 30) / act(app, T0, 30) - 1) < 0.03
    assert VD.params({"bo": 1, "x": 2}) == dict(VD.STRUCT, bo=1, bn=0.5, cq=0.0)
    assert not math.isnan(total(f))


def test_the_final_days_cut_as_live():
    """CLAG (on): a back-test origin also sees each install day's final daily data only to T − clag (as the live build);
    older install days untouched; off = the tournament's view."""
    app = with_ga4(make())
    T = date(2025, 10, 5)
    v = VD.lag_view(app, T, 5, 2)
    X = T - timedelta(days=8)
    assert app["coh"][X]["df"] == 31 and v["coh"][X]["df"] == 7 and v["coh"][X]["uf"] == 7
    assert v["coh"][X]["t"][F.T_AGES.index(3)] is not None and v["coh"][X]["t"][F.T_AGES.index(7)] is None
    assert v["coh"][T - timedelta(days=200)] is app["coh"][T - timedelta(days=200)] and v["g4"] == VD.lag_view(app, T, 5)["g4"]
    assert VD.CLAG is True
    app["clag"] = 2
    ors = F.origins(app)[-2:]
    on = VD.backtest(app, {}, None, ors)
    try:
        VD.CLAG = False
        off = VD.backtest(app, {}, None, ors)
    finally:
        VD.CLAG = True
    assert len(on) == len(off) and on[0]["h"][30]["err"] != off[0]["h"][30]["err"]
    assert abs(on[0]["h"][30]["err"]) < 0.05


def _numbers(st, app, T, sp):
    """Everything a forecast at T gives: totals, every past install day's future revenue / users, new installs' value."""
    return (VD.total(st, dict(sp), 90), [VD.cohort_rev(st, X, max(0, (T - X).days - 40), [90, 365]) for X in
                                         sorted(app["coh"]) if X <= T],
            [VD.cohort_users(st, X, [60, 90, 180]) for X in sorted(app["coh"]) if X <= T],
            [VD.new_value(st, T + timedelta(days=i), [30, 90, 180]) for i in range(1, 31)], st["q"])


def test_the_checkpoints_after_day_30_cut_as_live():
    """CLAG (on): an install day's checkpoints after day 30 (60 / 90 / 180 / 365) land tlag days after AdMob (measured
    by the build); a back-test origin sees them only to T − tlag, as the live build — so those dated after T − tlag can
    not move anything (the fit, nor the back-test's forecasts); with tlag 0 they would."""
    app = with_ga4(make())
    tl = 5
    for X, c in app["coh"].items():                      # as the data lands: checkpoints > 30 only to last − tlag
        c["t"] = [None if A > 30 and X + timedelta(days=A) > app["last"] - timedelta(days=tl) else v
                  for A, v in zip(F.T_AGES, c["t"])]
    app.update(clag=2, tlag=tl)
    v = VD.lag_view(app, F.origins(app)[-1], 5, 2, tl)
    T = F.origins(app)[-1]
    X = T - timedelta(days=62)                           # its day-60 checkpoint: 2 days before T (live: not there yet)
    assert app["coh"][X]["t"][F.T_AGES.index(60)] is not None and v["coh"][X]["t"][F.T_AGES.index(60)] is None
    X = T - timedelta(days=70)                           # … 10 days before T: there
    assert v["coh"][X]["t"][F.T_AGES.index(60)] == app["coh"][X]["t"][F.T_AGES.index(60)]
    p = VD.params({"bo": 0.5, "bn": 0.5, "cq": 1.0})
    for T in (F.origins(app)[-1], F.origins(app)[-3] + timedelta(days=2)):
        sp = {T + timedelta(days=i): 500.0 for i in range(1, 91)}
        late = _fresh(app)                               # the checkpoints > 30 dated in (T − tlag, T] × 3
        late["coh"] = {X: dict(c, t=[x * 3 if x is not None and A > 30 and
                                     T - timedelta(days=tl) < X + timedelta(days=A) <= T else x
                                     for A, x in zip(F.T_AGES, c["t"])]) for X, c in app["coh"].items()}
        assert late["coh"] != app["coh"]
        same = [_numbers(VD.prepare(a, T, p, {}, 2, tl), app, T, sp) for a in (_fresh(app), late)]
        assert same[0] == same[1], T
        seen = [_numbers(VD.prepare(a, T, p, {}, 2, 0), app, T, sp) for a in (_fresh(app), late)]
        assert seen[0] != seen[1], T
        bt = [VD.backtest(a, p, None, [T])[0] for a in (_fresh(app), late)]     # backtest() cuts them too
        assert [x["pred"] for x in bt[0]["h"].values()] == [x["pred"] for x in bt[1]["h"].values()]
        assert {k: c[0] for k, c in bt[0]["coh"].items()} == {k: c[0] for k, c in bt[1]["coh"].items()}
        assert {k: c[0] for k, c in bt[0]["new"].items()} == {k: c[0] for k, c in bt[1]["new"].items()}


def _ramped(app, r):
    """GA4's bands from 30 days on earn r % more each day: the portfolio's band ratios move from week to week."""
    for D, e in app["g4"].items():
        f = 1 + r * (D - date(2025, 1, 1)).days / 100
        e["rb"] = e["rb"][:3] + [x * f for x in e["rb"][3:]]
        e["rev"] = sum(e["rb"])
        e["k"] = app["days"][D]["rev"] / e["rev"]
    return app


def test_the_band_ratios_no_look_ahead_on_any_weekday():
    """A back-test origin on any weekday reads the portfolio's band ratios (made from every app's FULL data) only as
    the live build had them at T: the same numbers as with the ratios re-made from every app cut at T (each at its own
    GA4 lag — one app's GA4 lands 2 days later than the others', and its ratio is the median)."""
    apps = [_ramped(with_ga4(make()), 1.0), _ramped(with_ga4(make()), 0.5), _ramped(with_ga4(make(), lag=7), 0.75)]
    table = VD.bandr([VD.port_pre(_fresh(a)) for a in apps])
    assert len({tuple(v) for v in table.values()}) > 10    # the ratios do move
    p = VD.params({"bo": 1.0, "bn": 1.0, "cq": 1.0})
    for app in (apps[0], apps[2]):
        for T in (date(2025, 11, 2) + timedelta(days=i) for i in range(7)):           # Sunday … Saturday
            sp = {T + timedelta(days=i): 500.0 for i in range(1, 91)}
            full = dict(_fresh(app), port={"bandr": table})
            cut = dict(trunc(app, T), port={"bandr": VD.bandr([VD.port_pre(trunc(o, T)) for o in apps])})
            assert _numbers(VD.prepare(full, T, p, {}), app, T, sp) == _numbers(VD.prepare(cut, T, p, {}), app, T, sp), \
                (app["glag"], T.strftime("%a"))


def _rough(app, seed=7):
    """AdMob revenue ±12 % day to day (GA4 left as it was): the two views and q then differ from each other."""
    import random
    rnd = random.Random(seed)
    for e in app["days"].values():
        e["rev"] *= 1 + rnd.uniform(-0.12, 0.12)
    return app


def _fresh(app):
    return {k: v for k, v in app.items() if not k.startswith("_")}


def _by_interface(app, T, p):
    """One back-test origin rebuilt from the public interface (prepare / total / cohort_rev / cohort_users / new_value),
    the way the forecast tournament's harness scores a model: {hz: pred}, coh, usr, new cells."""
    days, last, start = app["days"], app["last"], app["start"]
    hmax = min(VD.H, (last - T).days)
    sp = {T + timedelta(days=i): (days.get(T + timedelta(days=i)) or {}).get("sp") or 0.0 for i in range(1, hmax + 1)}
    st = VD.prepare(app, T, VD.params(p), {}, (app.get("clag") or 0) if VD.CLAG else 0,
                    (app.get("tlag") or 0) if VD.CLAG else 0)
    f = VD.total(st, dict(sp), hmax)
    pred = {hz: sum(f["rev"][:hz]) for hz in VD.HORIZONS if hz <= hmax}
    coh, usr, new = {}, {}, {}
    for X, c in app["coh"].items():
        if X < start or X > T or not c.get("n"):
            continue
        g, (K, ck) = VD._grp((T - X).days), F._known(c, X, T)[-1]
        want = [C for C in VD.CHECK if C > K and C > (T - X).days and X + timedelta(days=C) <= last
                and VD._cum_at(c, C) is not None]
        for C, v in zip(want, VD.cohort_rev(st, X, K, want) if want else []):
            cell = coh.setdefault((g, C), [0.0, 0.0])
            cell[0] += v
            cell[1] += VD._cum_at(c, C) - ck
        uk = max(F._uknown(c, X, T) or [-1])
        lw = [L for L in VD.ULAG_CHECK if L > uk and L > (T - X).days and X + timedelta(days=L) <= last
              and VD._users_at(c, L) is not None]
        for L, v in zip(lw, (VD.cohort_users(st, X, lw) or []) if lw else []):
            cell = usr.setdefault((g, L), [0.0, 0.0])
            cell[0] += v
            cell[1] += VD._users_at(c, L)
    for i in range(1, 31):
        X = T + timedelta(days=i)
        c = app["coh"].get(X)
        want = [C for C in VD.NEW_AGES if c and X + timedelta(days=C) <= last and VD._cum_at(c, C) is not None]
        for C, v in zip(want, VD.new_value(st, X, want) if want else []):
            cell = new.setdefault(C, [0.0, 0.0])
            cell[0] += v * c["n"]
            cell[1] += VD._cum_at(c, C)
    return pred, coh, usr, new


def test_the_backtest_is_the_public_interface_exactly():
    """backtest() (both views fitted once per origin, then mixed) gives the very numbers of prepare / total /
    cohort_rev / cohort_users / new_value for each mix — with view B, and without it (no GA4 yet)."""
    for app, sets in ((_rough(with_ga4(make())), ({"bo": 0.0, "bn": 0.0, "cq": 0.0}, {"bo": 0.5, "bn": 0.5, "cq": 1.0},
                                                  {"bo": 1.0, "bn": 0.0, "cq": 0.5}, {"bo": 0.0, "bn": 1.0, "cq": 1.0})),
                      (_rough(make()), ({"bo": 0.5, "bn": 1.0, "cq": 1.0},))):
        app.update(clag=2, tlag=4)                       # the back-tests' cuts (final days, checkpoints > 30) too
        ors = F.origins(app)[-5:-1]
        for p in sets:
            bt = VD.backtest(_fresh(app), p, None, ors)
            assert len(bt) == len(ors) and any(r["new"] for r in bt) and all(r["coh"] and r["usr"] for r in bt)
            for r in bt:
                pred, coh, usr, new = _by_interface(_fresh(app), date.fromisoformat(r["T"]), p)
                assert {hz: x["pred"] for hz, x in r["h"].items()} == pred, p
                assert (r["coh"], r["usr"], r["new"]) == (coh, usr, new), p


def test_the_tune_shortcut_is_exact():
    """tune() scores every setting from fits shared across settings: each step's score = the objective of a back-test
    run from scratch with that setting, and the back-test it returns = backtest() with its pick."""
    app = _rough(with_ga4(make()))
    app.update(clag=2, tlag=4)
    ors = F.origins(app)
    p, bt, steps = VD.tune(_fresh(app), None, start_p={"bo": 0.0, "bn": 0.0, "cq": 1.0})
    assert len(steps) >= 2 and steps[-1]["score"] < steps[0]["score"]        # it moved (the rough AdMob days)
    for s in steps:
        assert VD.objective(VD.backtest(_fresh(app), s["p"], None, ors)) == s["score"]
    assert bt == VD.backtest(_fresh(app), p, None, ors)
