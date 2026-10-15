"""🔮 The verified horizon (owner, 15 Oct 2026: "verified horizon, khud badhe") — engine vd back-tested on a horizon grid
(30, 44, … 352 every 14 days + 90 / 180 / 365), each horizon calibrated on its own tests, N = the longest one with
≥ MIN_TESTS, the page's chips, the day each horizon unlocks, the monotone band. Checked on the made-up app of
tests/test_forecast_engine (+ its GA4 ledger and Uninstall cells): 30 / 90 / 180 exactly the tune's numbers (the tune
untouched), a long horizon = the public interface, a forecast to 365 days whose first 180 do not move, no look-ahead,
the older origins only where the newest do not reach, the unlock day = the origins' own count. No real data."""
from datetime import date, timedelta

from admob_iq.engine import forecast as F
from admob_iq.engine import forecast_vd as VD
from tests.test_forecast_engine import make, with_uninstalls
from tests.test_forecast_vd import _fresh, _rough, trunc, with_ga4

KEYS = ("pred", "act", "err", "un_err")


def _app():
    app = _rough(with_ga4(with_uninstalls(make())))
    app.update(clag=2, tlag=4)
    return app


def _k0(h):
    return max(0, -(-(h - 30) // F.ORIGIN_STEP))


def test_the_grid_follows_the_origin_step():
    assert VD.STD == (30, 90, 180, 365) and VD.HMAX == 365 and VD.GRID_ORIGINS == F.MAX_ORIGINS + 2
    assert VD.HG == tuple(sorted(set(range(30, 353, 14)) | {90, 180, 365})) and len(VD.HG) == 27
    # an origin is last − 30 − 14k: every horizon in (30 + 14(k − 1), 30 + 14k] has the same tests; 30 + 14k the longest
    assert _k0(90) == _k0(100) and _k0(180) == _k0(184) and _k0(365) == _k0(352 + 14) and _k0(86) < _k0(90)


def test_30_90_180_are_the_tunes_own_numbers():
    """The grid back-test reuses the tune's fits: at 30 / 90 / 180 the very rows (pred, act, error, uninstall error) and
    the very calibration of forecast.calibrate on the tune's back-test; the tune itself is untouched by fits=."""
    app = _app()
    fits = {}
    p, bt, steps = VD.tune(_fresh(app), None, fits=fits)
    a2 = _fresh(app)
    assert VD.tune(a2, None) == (p, bt, steps) and set(fits) == {(0, 0)} and len(fits[(0, 0)]) == len(F.origins(app))
    gbt = VD.grid_backtest(_fresh(app), p, None, fits)
    assert gbt == VD.grid_backtest(_fresh(app), p, None)                 # the fits reused = fitted afresh, exactly
    by = {r["T"]: r for r in bt}
    n = 0
    for r in gbt:
        for h in F.HORIZONS:
            if h in r["h"]:
                assert {k: r["h"][h][k] for k in KEYS} == {k: by[r["T"]]["h"][h][k] for k in KEYS}
                assert (h in r["ev"]) == (h in by[r["T"]]["ev"])
                n += 1
    assert n == sum(len(r["h"]) for r in bt) and any(x["un_err"] is not None for r in gbt for x in r["h"].values())
    gc, cal = VD.grid_cal(gbt), F.calibrate(bt)
    assert all(gc[h] == cal[h] for h in F.HORIZONS) and cal[30]["un_mape"] is not None
    # a year of data, 21 origins (k = 0 … 20): N = 30 + 14 × (20 − 3) = 268 — four tests, 282 not yet
    ors = F.origins(app)
    assert len(ors) == 21 and max(gc) == 268 and gc[268]["n"] == F.MIN_TESTS and 282 not in gc
    assert all(gc[h]["n"] == len(ors) - _k0(h) for h in gc)               # each horizon: every origin that reaches it
    assert VD.chips(gc) == [30, 90, 180, 268] and len(VD.grid_tests(gbt, 268)) == 4


def test_a_long_horizon_is_the_public_interface():
    """A grid row at 254 / 268 days = prepare(…, h) + total() with the spend that happened, summed over its days."""
    app = _app()
    p = VD.params({"bo": 0.5, "bn": 0.5, "cq": 1.0})
    gbt = VD.grid_backtest(_fresh(app), p)
    T = F.origins(app)[0]
    r = next(x for x in gbt if x["T"] == T.isoformat())
    h = (app["last"] - T).days
    assert h == 310 and {254, 268, 282, 296, 310} <= set(r["h"]) and 324 not in r["h"]
    st = VD.prepare(_fresh(app), T, p, {}, 2, 4, h=h)
    sp = {T + timedelta(days=i): app["days"][T + timedelta(days=i)]["sp"] for i in range(1, h + 1)}
    rev = VD.total(st, sp, h)["rev"]
    for hz in (254, 268, 30, 180):
        act = sum(app["days"][T + timedelta(days=i)]["rev"] for i in range(1, hz + 1))
        assert r["h"][hz]["pred"] == sum(rev[:hz]) and r["h"][hz]["act"] == act
    assert abs(r["h"][268]["err"]) < 0.25


def test_the_forecast_reaches_365_and_its_first_180_days_do_not_move():
    app = with_ga4(with_uninstalls(make()))
    T = app["last"]
    a, b = VD.forecast(_fresh(app), T, {}, h=180), VD.forecast(_fresh(app), T, {}, h=365)
    for k in ("old", "org", "paid"):
        assert len(b["rev"][k]) == 365 and b["rev"][k][:180] == a["rev"][k]
        assert b["dau_p"][k][:180] == a["dau_p"][k] and b["un"][k][:180] == a["un"][k]
    assert b["dau"][:180] == a["dau"] and b["n"][:180] == a["n"] and b["sp"][:180] == a["sp"]
    assert all(v > 0 for v in b["rev"]["old"]) and b["parts"] == a["parts"]


def test_no_look_ahead_at_the_longest_horizons():
    """From the oldest origin (310 days of data after it), forecasting to its last day: the app as it is and the app cut
    at T (every dated input after T removed, GA4 after T − lag) give the very same numbers — and the grid row's
    prediction is that number."""
    app = with_ga4(make())
    T = F.origins(app)[0]
    h = (app["last"] - T).days
    p = VD.params({"bo": 0.5, "bn": 0.5, "cq": 1.0})
    sp = {T + timedelta(days=i): 500.0 for i in range(1, h + 1)}
    full = VD.total(VD.prepare(_fresh(app), T, p, {}, h=h), dict(sp), h)
    cut = VD.total(VD.prepare(trunc(app, T), T, p, {}, h=h), dict(sp), h)
    assert full == cut and len(full["rev"]) == h > 300
    r = next(x for x in VD.grid_backtest(_fresh(app), p) if x["T"] == T.isoformat())
    assert r["h"][268]["pred"] == sum(full["rev"][:268]) and r["h"][310]["pred"] == sum(full["rev"])


def test_older_origins_only_where_the_newest_do_not_reach(monkeypatch):
    """With the tune's MAX_ORIGINS newest origins (6 here) a horizon they score fewer than MIN_TESTS times takes the
    older ones (up to GRID_ORIGINS, 8 here) — never 30 / 90 / 180 (the tune's numbers stay the tune's)."""
    monkeypatch.setattr(F, "MAX_ORIGINS", 6)
    monkeypatch.setattr(VD, "GRID_ORIGINS", 8)
    app = with_ga4(make())
    assert len(F.origins(app)) == 6 and len(F.origins(app, VD.GRID_ORIGINS)) == 8
    gbt = VD.grid_backtest(_fresh(app), VD.DEFAULT)
    assert len(gbt) == 8 and sum(1 for r in gbt if r.get("x")) == 2 and [r["T"] for r in gbt] == sorted(r["T"] for r in gbt)
    t = {h: VD.grid_tests(gbt, h) for h in VD.HG}
    assert len(t[58]) == 4 and not any(r.get("x") for r in t[58])          # k 2 … 5: the newest suffice
    assert len(t[72]) == 5 and sum(1 for r in t[72] if r.get("x")) == 2    # k 3 … 7
    assert len(t[86]) == 4 and len(t[100]) == 3 and len(t[90]) == 1        # 90: a standard one never takes them
    gc = VD.grid_cal(gbt)
    assert max(gc) == 86 and 90 not in gc and VD.chips(gc) == [30, 86]
    assert VD.unlock(app["start"], 86) <= app["last"] and VD.unlock(app["start"], 100) is None
    assert VD.unlock(app["start"], 90) is None                              # (k 8 ≥ the 6 origins it may use)


def test_the_unlock_day_is_the_origins_own_count():
    """unlock(start, h) = the first data day on which h has MIN_TESTS tests by the origins' own rule (the newest
    MAX_ORIGINS; past 338 days up to GRID_ORIGINS), every day of two years, every grid horizon."""
    start = date(2024, 3, 1)
    want = {h: VD.unlock(start, h) for h in VD.HG}
    first = {}
    for d in range(0, 760):
        last = start + timedelta(days=d)
        app = {"start": start, "last": last}
        new, old = F.origins(app), F.origins(app, VD.GRID_ORIGINS)
        for h in VD.HG:
            n = sum(1 for T in new if (last - T).days >= h)
            if n < F.MIN_TESTS and h not in F.HORIZONS:
                n = sum(1 for T in old if (last - T).days >= h)
            if n >= F.MIN_TESTS and h not in first:
                first[h] = last
            if h in first:
                assert n >= F.MIN_TESTS, (h, last)                  # once verified, it stays (the window slides)
    assert first == want and want[30] == start + timedelta(days=114) and want[365] == start + timedelta(days=450)
    assert (want[184] - want[170]).days == 14 and want[180] == want[184] and want[90] == want[100]


def test_chips_and_the_band():
    c = lambda n, lo, hi: {"n": n, "lo": lo, "hi": hi}      # noqa: E731
    assert VD.chips({}) == [] and VD.chips({30: 1}) == [30] and VD.chips({30: 1, 44: 1, 58: 1, 72: 1}) == [30, 72]
    assert VD.chips({str(h): 1 for h in (30, 44, 90, 100, 180, 184, 198)}) == [30, 90, 180, 198]
    assert VD.chips({h: 1 for h in VD.HG}) == [30, 90, 180, 365]
    cal = {30: c(20, -0.10, 0.12), 44: c(18, -0.08, 0.15), 58: c(4, -0.20, 0.10), 72: c(4, -0.15, 0.30), 86: c(4, 0.02, 0.2)}
    b = VD.band(cal)                                        # never narrower further out, always around the forecast
    assert b == [[30, -0.10, 0.12], [44, -0.10, 0.15], [58, -0.20, 0.15], [72, -0.20, 0.30], [86, -0.20, 0.30]]
    ok = {"30": c(9, -0.1, 0.1), "90": c(5, -0.2, 0.2), "180": c(4, -0.3, 0.4)}
    assert VD.band(ok) == [[30, -0.1, 0.1], [90, -0.2, 0.2], [180, -0.3, 0.4]] and VD.band({}) == []
    assert VD.band({365: c(4, -0.64, -0.61)}) == [[365, -0.64, 0.0]]       # a band beside the forecast: 0 kept inside


def test_calibrate_one_horizon_at_a_time():
    rows = [{"T": "2025-0%d-01" % (i + 1), "h": {30: {"err": e, "un_err": None}, 44: {"err": e / 2, "un_err": 0.1}},
             "ev": {30: {"kind": "installs"}} if i == 2 else {}} for i, e in enumerate((0.1, -0.05, 0.3, 0.02, 0.07))]
    cal = F.calibrate(rows)
    assert set(cal) == {30} and cal[30] == F.cal1(rows, 30) and cal[30]["n"] == 5 and cal[30]["n_normal"] == 4
    assert F.calibrate(rows, (30, 44)) == {30: cal[30], 44: F.cal1(rows, 44)} and F.cal1(rows[:3], 30) is None
