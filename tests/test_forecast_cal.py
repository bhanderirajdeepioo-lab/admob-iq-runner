"""📅 The eCPM calendar inside the 🔮 forecast (engine vd: admob_iq.engine.forecast_vd + fc_calendar) on the made-up
app of tests/test_forecast_vd (its truth known, no calendar in it) with a made-up calendar: old users take an event's
measured effect in full, new installs × φv, paid installs per $ × e^(φn·…); only the seasons complete by T; q measured
against the calendar-corrected model; back-test == the public interface; off (cal 0 / no calendar) == the engine
before. No real data."""
import math
from datetime import date, timedelta

from admob_iq.engine import fc_calendar as FC
from admob_iq.engine import forecast as F
from admob_iq.engine import forecast_vd as VD
from tests.test_forecast_engine import make
from tests.test_forecast_vd import _by_interface, _fresh, _rough, with_ga4

EV = {"bf": 0.12, "cyber": 0.06, "dec": -0.03, "xmas": -0.09, "j1": -0.18, "j2": -0.21, "j3": -0.24, "j4": -0.27,
      "j5": -0.30, "j6": -0.33}


def calendar(scale=(1.0, 0.5), extra=None):
    """Two complete seasons (2023, 2024) whose eCPM effects are EV × each scale (CTR = half of it, revenue per click
    the rest); extra: {season: scale} added."""
    s = {}
    for y, k in list(zip((2023, 2024), scale)) + list((extra or {}).items()):
        s[str(y)] = {"ev": {e: [v * k, v * k / 2, v * k / 2] for e, v in EV.items()}, "units": 40, "apps": 6}
    return {"v": 1, "till": "2025-10-15", "s": s}


def _app(cal=None):
    app = with_ga4(make())
    app["cal"] = cal
    return app


def _prof(n=2, scale=0.75):
    """The profile at an origin with both seasons complete: the mean (EV × 0.75), × n ÷ (n + 1) (STRUCT csh 1)."""
    return {e: v * scale * n / (n + VD.STRUCT["csh"]) for e, v in EV.items()}


def test_old_users_in_full_new_installs_partly():
    T = date(2025, 9, 1)
    sp = {T + timedelta(days=i): 500.0 for i in range(1, 181)}
    on = VD.forecast(_app(calendar()), T, {"bo": 0.5, "bn": 0.5, "cq": 1.0, "cal": 1}, h=180, spend=sp)
    off = VD.forecast(_app(calendar()), T, {"bo": 0.5, "bn": 0.5, "cq": 1.0, "cal": 0}, h=180, spend=sp)
    pr = _prof()
    nv, nn = VD.STRUCT["cnv"], VD.STRUCT["cnn"]
    assert nv == 0.61 and nn == -0.48                     # app eCPM +10 % → installs per $ −4.8 %, ROAS +1.3 %

    def at(d):
        return (d - T).days - 1
    for d, e in ((date(2025, 11, 26), pr["bf"]), (date(2025, 12, 3), pr["cyber"]), (date(2025, 12, 26), pr["xmas"]),
                 (date(2026, 1, 20), pr["j3"]), (date(2026, 2, 20), pr["j6"]), (date(2025, 10, 15), 0.0)):
        i = at(d)
        assert abs(on["rev"]["old"][i] / off["rev"]["old"][i] - math.exp(e)) < 1e-9, d       # old users: in full
        assert abs(on["rev"]["org"][i] / off["rev"]["org"][i] - math.exp(nv * e)) < 1e-9, d  # organic: × φv
        paid = (on["n"][i] - on["parts"]["org"]) / (off["n"][i] - off["parts"]["org"])     # paid installs per $
        assert abs(paid - math.exp(nn * e)) < 1e-9, d
    assert on["dau_p"]["old"] == off["dau_p"]["old"] and on["dau_p"]["org"] == off["dau_p"]["org"]   # users: price only
    assert abs(on["parts"]["q"] / off["parts"]["q"] - 1) < 1e-12    # (the days GA4 has not reached: no event in them)
    ev = {x["k"]: x for x in on["cal"]["ev"]}
    assert on["cal"]["n"] == 2 and on["cal"]["phi"] == [nv, nn] and on["cal"]["use"] == 1
    assert off["cal"]["use"] == 0 and [x["e"] for x in off["cal"]["ev"]] == [x["e"] for x in on["cal"]["ev"]]
    assert all(x["o"] is None for x in off["cal"]["ev"])               # (off: the weeks shown, the forecast without)
    assert list(ev) == ["bf", "cyber", "dec", "xmas", "j1", "j2", "j3", "j4", "j5", "j6", "hold"]
    # the page's measured effect: the seasons' plain mean (no shrink) and the lowest / highest season; the forecast's
    # own move (o) the shrunk profile
    assert abs(ev["bf"]["e"] - (math.exp(0.09) - 1)) < 1e-12 and abs(ev["j6"]["e"] - (math.exp(-0.33 * 0.75) - 1)) < 1e-12
    assert abs(ev["bf"]["lo"] - (math.exp(0.06) - 1)) < 1e-12 and abs(ev["bf"]["hi"] - (math.exp(0.12) - 1)) < 1e-12
    assert abs(ev["j6"]["lo"] - (math.exp(-0.33) - 1)) < 1e-12 and abs(ev["j6"]["hi"] - (math.exp(-0.165) - 1)) < 1e-12
    assert on["cal"]["ys"] == off["cal"]["ys"] == [[2023, 6], [2024, 6]] and off["cal"]["n"] == 2
    assert abs(ev["bf"]["o"] - (math.exp(pr["bf"]) - 1)) < 1e-12
    assert abs(ev["bf"]["nv"] - (math.exp(nv * pr["bf"]) - 1)) < 1e-12
    assert abs(ev["bf"]["np"] - (math.exp(nn * pr["bf"]) - 1)) < 1e-12
    assert ev["hold"]["a"] == "2026-02-12" and ev["hold"]["b"] is None
    assert abs(ev["hold"]["o"] - (math.exp(pr["j6"]) - 1)) < 1e-12


def test_only_the_seasons_complete_by_t():
    """A season counts once its January week 6 is over: at an origin in December the season in progress is not used,
    whatever it holds; the calendar reads nothing dated after T."""
    T = date(2025, 9, 1)
    sp = {T + timedelta(days=i): 500.0 for i in range(1, 121)}
    a = VD.forecast(_app(calendar()), T, {"cal": 1}, h=120, spend=sp)
    b = VD.forecast(_app(calendar(extra={2025: 9.0})), T, {"cal": 1}, h=120, spend=sp)    # the 2025 season: a wild one
    assert a["rev"] == b["rev"] and a["n"] == b["n"] and a["cal"] == b["cal"]
    cal = calendar(extra={2025: 9.0})
    assert FC.profile(cal, date(2026, 2, 11))[1] == 2 and FC.profile(cal, date(2026, 2, 12))[1] == 3


def test_q_measured_against_the_calendar():
    """The days AdMob has but GA4 not yet fall in Black Friday week: the calendar explains their move first, q carries
    the rest (view A alone: q × e^(c − ref) = q without the calendar)."""
    T = date(2025, 11, 30)
    app = _app(calendar())
    p = {"bo": 0.0, "bn": 0.0, "cq": 1.0, "cal": 1}
    on, off = VD.prepare(app, T, VD.params(p)), VD.prepare(_app(calendar()), T, VD.params(dict(p, cal=0)))
    cal = on["a"]["cal"]
    e = _prof()["bf"]
    TG = cal["TG"]
    assert TG == date(2025, 11, 25) and on["nt"] == 5
    rA = cal["ref"][0]
    assert abs(rA - (cal["c"](date(2025, 11, 10)) + math.log((26 + 2 * math.exp(e)) / 28))) < 1e-12
    f = math.exp(cal["c"](date(2025, 11, 27)) - rA)
    assert f > 1.05 and abs(on["qraw"] * f - off["qraw"]) < 1e-9


def test_the_backtest_is_the_public_interface_with_the_calendar():
    app = _rough(with_ga4(make()))
    app["cal"] = calendar()
    app.update(clag=2, tlag=4)
    ors = [T for T in F.origins(app) if T.month in (10, 11, 12)][-4:]
    assert len(ors) == 4
    for p in ({"bo": 0.5, "bn": 0.5, "cq": 1.0, "cal": 1}, {"bo": 1.0, "bn": 0.0, "cq": 0.5, "cal": 1}):
        bt = VD.backtest(_fresh(app), p, None, ors)
        off = VD.backtest(_fresh(dict(app, cal=None)), p, None, ors)
        assert any(abs(r["h"][30]["pred"] / o["h"][30]["pred"] - 1) > 0.01 for r, o in zip(bt, off))
        for r in bt:
            pred, coh, usr, new = _by_interface(_fresh(app), date.fromisoformat(r["T"]), p)
            assert {hz: x["pred"] for hz, x in r["h"].items()} == pred, p
            assert (r["coh"], r["usr"], r["new"]) == (coh, usr, new), p


def test_off_is_the_engine_before():
    """cal 0, no calendar, or no complete season: exactly the numbers without the calendar."""
    T = date(2025, 11, 2)
    sp = {T + timedelta(days=i): 500.0 for i in range(1, 91)}
    base = VD.forecast(_app(None), T, {}, h=90, spend=sp)
    for app, p, page in ((_app(calendar()), {"cal": 0}, True), (_app({"v": 1, "s": {}}), {"cal": 1}, False),
                         (_app({"v": 1, "s": {"2025": calendar()["s"]["2023"]}}), {"cal": 1}, False)):
        f = VD.forecast(app, T, p, h=90, spend=sp)
        assert f["rev"] == base["rev"] and f["n"] == base["n"] and f["dau"] == base["dau"]
        assert (f["cal"]["use"] == 0) if page else f["cal"] is None


def test_the_live_run_rate_reference():
    """spend None (today's run-rate): the paid installs' reference is the run-rate's own window (SPEND_DAYS)."""
    T = date(2025, 12, 2)                                  # the last 7 days: 5 BF days + 2 Cyber days
    app = _app(calendar())
    f = VD.forecast(app, T, {"cal": 1}, h=30)
    g = VD.forecast(_app(calendar()), T, {"cal": 0}, h=30)
    st = VD.prepare(_app(calendar()), T, VD.params({"cal": 1}))
    cal = st["a"]["cal"]
    r7 = FC.ref(cal["cr"], T, F.SPEND_DAYS)
    D = T + timedelta(days=10)                             # Dec 12: "dec"
    i = 9
    paid = (f["n"][i] - f["parts"]["org"]) / (g["n"][i] - g["parts"]["org"])
    assert abs(paid - math.exp(VD.STRUCT["cnn"] * (cal["c"](D) - r7))) < 1e-9 and abs(r7 - cal["ref"][3]) > 1e-6


def test_off_while_the_slide_is_in_progress():
    """cjan 1: at an origin whose newest GA4 day is inside a January slide the calendar is off (the levels see the
    slide already) — the very numbers of cal 0; before January it is on."""
    app = _rough(with_ga4(make()))
    app["cal"] = calendar()
    sp = {date(2025, 12, 1) + timedelta(days=i): 500.0 for i in range(1, 120)}
    for T, same in ((date(2025, 12, 1), False), (date(2025, 12, 31), False)):
        f1 = VD.forecast(_fresh(app), T, {"cal": 1, "cjan": 1}, h=30, spend=sp)
        f0 = VD.forecast(_fresh(app), T, {"cal": 0}, h=30, spend=sp)
        assert (f1["rev"] == f0["rev"]) == same
    assert FC.sliding(date(2026, 1, 1)) and FC.sliding(date(2026, 2, 11)) and not FC.sliding(date(2026, 2, 12))
    assert not FC.sliding(date(2025, 12, 31))
