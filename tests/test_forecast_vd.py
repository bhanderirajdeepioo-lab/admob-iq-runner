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
    assert VD.params({"bo": 1, "x": 2}) == dict(VD.STRUCT, bo=1, bn=0.5, cq=0.0, gc=0, pc=0)
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


# ── GA4's install-day extension (IDAY_EXT c2 / cp / d2): gc (country curves past day 90), pc (paid vs organic) ────────
from tests.test_forecast_engine import D0, a_hi, a_lo, make_mix, u_hi, u_lo  # noqa: E402

READ0 = date(2025, 6, 1)                      # the extension's re-read reached back to here (d2: every day folded)
C2B, C2L = ((91, 180), (181, 365), (366, 427)), (120, 180, 270, 365)


def with_cells(app, read0=READ0, upto=None, shift=date(2025, 8, 1), before=0.2, after=0.6):
    """make_mix + GA4 + the ledgers and cells the engine reads: cset (the two country slots + ZZ), cfrom, the legacy
    day ledger (cst ok), and c2 (ad revenue in micros at 91–180 / 181–365 / 366–427, users at 120 / 180 / 270 / 365) of
    the activity days read0 … upto (d2 c2st ok) — a band of a week only partly in that range is a partial cell (the
    engine must leave it out)."""
    upto = upto or app["last"]
    ida = {"cset": ["H", "L", "ZZ"], "cfrom": D0.isoformat(),
           "days": {(D0 + timedelta(days=i)).isoformat(): {"cst": "ok"} for i in range((app["last"] - D0).days + 1)},
           "d2": {}, "c2": {}}
    D = read0
    while D <= upto:
        ida["d2"][D.isoformat()] = {"c2st": "ok"}
        D += timedelta(days=1)
    for X in sorted(app["coh"]):
        q = after if X >= shift else before
        W = (X - timedelta(days=X.weekday())).isoformat()
        for k, n, af, uf in (("0", 2000 * q, a_hi, u_hi), ("1", 2000 * (1 - q), a_lo, u_lo)):
            e = ida["c2"].setdefault(W, {}).setdefault(k, {"r2": [0.0] * 3, "u2": [0.0] * 4})
            for b, (lo, hi) in enumerate(C2B):
                for L in range(lo, hi + 1):
                    if read0 <= X + timedelta(days=L) <= upto:
                        e["r2"][b] += n * af(L) * 1e6
            for j, g in enumerate(C2L):
                if read0 <= X + timedelta(days=g) <= upto:
                    e["u2"][j] += n * uf(g)
    app["ida"] = ida
    return app


def _mixapp(**kw):
    app = with_ga4(make_mix())
    return with_cells(app, **kw)


def _late_numbers(app, T, p):
    st = VD.prepare(_fresh(app), T, VD.params(p), {})
    sp = {T + timedelta(days=i): 500.0 for i in range(1, 91)}
    r = VD.total(st, dict(sp), 90)
    coh = {X: VD.cohort_rev(st, X, F._known(c, X, T)[-1][0], [180, 365]) for X, c in app["coh"].items()
           if X <= T - timedelta(days=3) and F._known(c, X, T)}
    usr = {X: VD.cohort_users(st, X, [120, 180, 270, 365]) for X in app["coh"] if X <= T}
    new = [VD.new_value(st, T + timedelta(days=i), [30, 90, 180]) for i in range(1, 31)]
    return r, coh, usr, new, st["q"]


def test_late_country_cells_off_or_not_complete_change_nothing():
    """gc 2 with no complete late cell (no d2, or every band's window only partly read) gives exactly the gc 0 numbers;
    so does a switch the app's setting leaves off."""
    T = date(2025, 10, 6)
    for app in (_mixapp(read0=T + timedelta(days=30)),                  # nothing read before T
                _mixapp(read0=T - timedelta(days=8))):                  # 3 days to T − 5: no late window whole
        base = _late_numbers(app, T, {"gc": 0})
        assert _late_numbers(app, T, {"gc": 2}) == base
    app = _mixapp()
    assert _late_numbers(app, T, {"gc": 0}) == _late_numbers(dict(app, ida=dict(app["ida"], c2={})), T, {"gc": 0})


def test_late_country_cells_each_country_on_its_own_curve_past_90():
    """Two countries, the better one's curve flat and the other's fading fast (their standing keeps moving past day
    90); the better one's share jumps from 20 % to 60 % on Aug 1. With the late cells (gc 2) the install weeks after the
    jump get their own countries' standing past day 90 — their revenue to day 180 / 365 and their users at 120–365
    come closer to the truth than with the 61–90 standing carried (gc 0)."""
    app = _mixapp()
    T = date(2025, 11, 2)
    truth = {}
    for X in app["coh"]:
        q = 0.6 if X >= date(2025, 8, 1) else 0.2
        truth[X] = (lambda L, q=q: 2000 * (q * a_hi(L) + (1 - q) * a_lo(L)),
                    lambda L, q=q: 2000 * (q * u_hi(L) + (1 - q) * u_lo(L)))
    e = {}
    for gc in (0, 2):
        p = VD.params({"gc": gc, "bo": 0.5, "bn": 0.5, "cq": 0.0})
        st = VD.prepare(_fresh(app), T, p, {})
        er = eu = 0.0
        for X in [X for X in app["coh"] if date(2025, 8, 4) <= X <= date(2025, 8, 31)]:
            got = VD.cohort_rev(st, X, 90, [180, 365])                   # ages 91–180 and 91–365
            er += sum(abs(v / sum(truth[X][0](L) for L in range(91, C + 1)) - 1) for v, C in zip(got, (180, 365)))
            eu += sum(abs(v / truth[X][1](g) - 1) for v, g in zip(VD.cohort_users(st, X, C2L), C2L))
        e[gc] = (er, eu)
    assert e[2][0] < 0.85 * e[0][0] and e[2][1] < 0.8 * e[0][1], e
    # what the page shows: the share of the old installs' revenue at ages 91–427 resting on measured cells
    gx = VD.forecast(_fresh(app), T, {"gc": 2}, h=180)["parts"]["gx"]
    assert gx["on"] and 0 < gx["old"] < 1 and 0.5 < gx["meas"] <= 1 and gx["weeks"][0] > 0
    gx0 = VD.forecast(_fresh(app), T, {"gc": 0}, h=180)["parts"]["gx"]
    assert not gx0["on"] and abs(gx0["meas"] - gx["meas"]) < 0.01   # what is ready, even while gc stays off


def test_late_country_cells_no_look_ahead():
    """At T the late cells / ledger days after T − glag can not move anything: the same numbers with the cells re-made
    from the days to T − 5 only."""
    T = date(2025, 11, 2)
    full = _mixapp()
    cut = _mixapp(upto=T - timedelta(days=5))
    assert full["ida"]["c2"] != cut["ida"]["c2"]
    p = {"gc": 2, "bo": 0.5, "bn": 0.5, "cq": 1.0}
    assert _late_numbers(full, T, p) == _late_numbers(cut, T, p)
    assert _late_numbers(full, T, p) != _late_numbers(full, T, {"gc": 0, "bo": 0.5, "bn": 0.5, "cq": 1.0})


def test_tune_tries_the_cells_only_where_they_can_change_something():
    """The switches are tuned like the mix weights; an origin whose cells are not complete reuses the plain fit, and
    every step's score is still the objective of a back-test from scratch."""
    app = _rough(_mixapp())
    ors = F.origins(app)
    moved = [T for T in ors if VD._moves(_fresh(app), T, 2, 0)]
    assert moved and len(moved) < len(ors)
    p, bt, steps = VD.tune(_fresh(app), None, start_p={"bo": 0.5, "bn": 0.5, "cq": 0.0})
    assert set(p) == set(VD.GRID) and p["gc"] in (0, 2) and p["pc"] in (0, 1)
    for s in steps:
        assert VD.objective(VD.backtest(_fresh(app), s["p"], None, ors)) == s["score"]
    assert bt == VD.backtest(_fresh(app), p, None, ors)


def _pi_of(X):
    return 0.5 + 0.1 * math.sin(2 * math.pi * (X - D0).days / 28.0)


def make_paid(read0=date(2025, 8, 1), cp=True, over=1.1, upto=LAST):
    """2,000 installs a day, a GA4 paid share π(X) moving 0.4–0.6; a paid install earns 1.6 × and an organic one 0.7 ×
    the base curve, paid users keep 0.9 × and organic 1.1 × — the Google Ads count over-counts paid installs (× over).
    + GA4 (k 1), the legacy country cells (one slot) and IDAY_EXT's paid cells cp + d2 (cpst, cpn) from read0."""
    def a(L):
        return 0.05 / (L + 1) ** 0.8
    LB_ = VD.LB
    coh, days, cty = {}, {}, {}
    ida = {"cset": ["AA", "ZZ"], "cfrom": D0.isoformat(), "days": {}, "d2": {}, "cp": {}}
    X = D0
    while X <= LAST:
        pi, n = _pi_of(X), 2000
        npd, nod = pi * n, (1 - pi) * n
        lim = (LAST - X).days

        def rev(L):
            return npd * 1.6 * a(L) + nod * 0.7 * a(L)

        def usr(L):
            return n if L == 0 else npd * 0.9 * u_true(L) + nod * 1.1 * u_true(L)
        cum, d = 0.0, []
        for L in range(min(31, lim + 1)):
            cum += rev(L)
            d.append(cum)
        coh[X] = {"n": n, "d": d, "df": len(d), "u": [usr(L) for L in range(min(31, lim + 1))], "uf": len(d),
                  "t": [sum(rev(L) for L in range(A + 1)) if A <= lim else None for A in F.T_AGES],
                  "ul": [usr(L) if L <= lim else None for L in F.ULAGS]}
        days[X] = {"n": n, "na": npd * over, "sp": 500.0}
        ida["days"][X.isoformat()] = {"cst": "ok"}
        if read0 <= X <= upto:
            ida["d2"][X.isoformat()] = {"cpst": "ok", "cpn": pi}
        W = X - timedelta(days=X.weekday())
        e = cty.setdefault(W, {}).setdefault("0", {"n": 0, "r": [0.0] * len(F.CB), "u": [0.0] * len(F.CL)})
        e["n"] += n
        for b, (lo, hi) in enumerate(F.CB):
            e["r"][b] += sum(rev(L) for L in range(lo, min(hi, lim) + 1)) * 1e6
        for j, g in enumerate(F.CL):
            e["u"][j] += usr(g) if g <= lim else 0.0
        if cp:
            q = ida["cp"].setdefault(W.isoformat(), {}).setdefault("0", {"n": 0, "r": [0.0] * 11, "u": [0.0] * 11})
            q["n"] += npd
            for b, (lo, hi) in enumerate(LB_):
                q["r"][b] += sum(npd * 1.6 * a(L) * 1e6 for L in range(lo, hi + 1) if read0 <= X + timedelta(days=L) <= upto)
            for j, g in enumerate(VD.LL):
                if read0 <= X + timedelta(days=g) <= upto:
                    q["u"][j] += npd * 0.9 * u_true(g)
        X += timedelta(days=1)
    D = D0
    while D <= LAST:
        r = du = 0.0
        for X2 in coh:
            if X2 > D:
                continue
            L = (D - X2).days
            pi = _pi_of(X2)
            r += 2000 * (pi * 1.6 + (1 - pi) * 0.7) * a(L)
            du += 2000.0 if L == 0 else 2000 * (pi * 0.9 + (1 - pi) * 1.1) * u_true(L)
        days[D]["rev"], days[D]["dau"] = r, du
        D += timedelta(days=1)
    g4 = {}
    app = {"coh": coh, "days": days, "start": D0, "last": LAST, "cty": cty, "ida": ida, "glag": 5}
    for D in sorted(days):                                # GA4 = AdMob (k 1), by install-age band, landing 5 days late
        if D > LAST - timedelta(days=5):
            continue
        rb, ab = [0.0] * 6, [0.0] * 6
        for X2 in coh:
            if X2 > D:
                continue
            L = (D - X2).days
            j = GIX[L]
            if j is None:
                continue
            pi = _pi_of(X2)
            rb[j] += 2000 * (pi * 1.6 + (1 - pi) * 0.7) * a(L)
            ab[j] += 2000.0 if L == 0 else 2000 * (pi * 0.9 + (1 - pi) * 1.1) * u_true(L)
        G = sum(rb)
        g4[D] = {"rev": G, "rb": rb, "ab": ab, "k": days[D]["rev"] / G}
    app["g4"] = g4
    return app


def test_paid_cells_measure_the_paid_premium():
    """New installs' paid vs organic value (view B): from GA4's paid cells (pc 1) the paid ÷ organic revenue per install
    to day 30 meets the truth (1.6 ÷ 0.7) and beats the regression on the Google Ads share, which over-counts paid
    installs; without paid cells pc 1 is exactly pc 0."""
    T = date(2025, 11, 2)
    truth = 1.6 / 0.7
    got = {}
    for pc in (0, 1):
        f = VD.forecast(make_paid(), T, {"pc": pc, "bo": 0.5, "bn": 1.0}, h=90)
        nv = f["parts"]["nv"]
        got[pc] = (nv["paid"][1] / nv["org"][1], f["parts"]["nvsrc"], f)
    assert got[1][1] == "cp" and got[0][1] == "ads"
    assert abs(got[1][0] / truth - 1) < 0.08 and abs(got[1][0] / truth - 1) < abs(got[0][0] / truth - 1), got
    plain = make_paid(cp=False)
    a0 = VD.forecast(plain, T, {"pc": 0, "bo": 0.5, "bn": 1.0}, h=90)
    a1 = VD.forecast(make_paid(cp=False), T, {"pc": 1, "bo": 0.5, "bn": 1.0}, h=90)
    assert a0["rev"] == a1["rev"] and a1["parts"]["nvsrc"] == "ads"
    # no look-ahead: the paid cells / ledger days after T − glag can not move anything
    cut = VD.forecast(make_paid(upto=T - timedelta(days=5)), T, {"pc": 1, "bo": 0.5, "bn": 1.0}, h=90)
    assert cut["rev"] == got[1][2]["rev"] and cut["dau"] == got[1][2]["dau"]
    # the spend slider: twice the spend → the new paid installs' revenue twice, the organic and old untouched
    s1 = {T + timedelta(days=i): 500.0 for i in range(1, 61)}
    f1 = VD.forecast(make_paid(), T, {"pc": 1, "bo": 0.5, "bn": 1.0}, h=60, spend=s1)
    f2 = VD.forecast(make_paid(), T, {"pc": 1, "bo": 0.5, "bn": 1.0}, h=60, spend={D: 2 * v for D, v in s1.items()})
    assert f1["rev"]["org"] == f2["rev"]["org"] and f1["rev"]["old"] == f2["rev"]["old"]
    assert all(abs(b - 2 * a) < 1e-9 * max(1.0, b) for a, b in zip(f1["rev"]["paid"], f2["rev"]["paid"]))
