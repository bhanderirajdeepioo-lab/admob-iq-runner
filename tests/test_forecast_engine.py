"""🔮 Forecast — the engine (admob_iq.engine.forecast) on a made-up app whose truth is known: every install day earns
a(age) per install and keeps u(age) users, installs = organic + spend ÷ CPI. Checked: the triangle (a day's revenue at an
age is learnt only from install days that reached it), an install day that does better keeps doing better (scale),
the forecast vs the truth, back-tests / tuning / calibration, sudden changes kept apart, the start of the real run and
the organic installs."""
import math
from datetime import date, timedelta

from admob_iq.engine import forecast as F

D0, LAST = date(2025, 1, 1), date(2025, 12, 31)


def a_true(L):
    return 0.05 / (L + 1) ** 0.8


def u_true(L):
    return 1.0 if L == 0 else 0.4 / (L + 1) ** 0.5


def make(spike=None, trial=0, boost=None):
    """A year of a steady app (2,000 installs a day: 1,000 organic + $500 at $0.50), its install days complete to LAST.
    trial: the first days with 30 installs; spike: (day, ×) installs without spend; boost: (day, ×) revenue of the install
    days from that day on."""
    coh, days = {}, {}
    X = D0
    while X <= LAST:
        i = (X - D0).days
        n = 30 if i < trial else 2000
        if spike and spike[0] <= X < spike[0] + timedelta(days=30):
            n *= spike[1]
        f = boost[1] if boost and X >= boost[0] else 1.0
        lim = (LAST - X).days
        cum, d = 0.0, []
        for L in range(min(31, lim + 1)):
            cum += n * a_true(L) * f
            d.append(cum)
        t = []
        for A in F.T_AGES:
            t.append(sum(n * a_true(L) * f for L in range(A + 1)) if A <= lim else None)
        u = [round(n * u_true(L)) for L in range(min(31, lim + 1))]
        ul = [round(n * u_true(L)) if L <= lim else None for L in F.ULAGS]
        coh[X] = {"n": n, "d": d, "df": len(d), "u": u, "uf": len(u), "t": t, "ul": ul}
        days[X] = {"n": n, "na": 0 if i < trial else 1000 * (spike[1] if spike and spike[0] <= X < spike[0] + timedelta(days=30) else 1),
                   "sp": 0.0 if i < trial else 500.0}
        X += timedelta(days=1)
    D = D0
    while D <= LAST:
        rev = dau = 0.0
        for X2, c in coh.items():
            if X2 > D:
                continue
            L = (D - X2).days
            f = boost[1] if boost and X2 >= boost[0] else 1.0
            rev += c["n"] * a_true(L) * f
            dau += c["n"] * u_true(L)
        days[D]["rev"], days[D]["dau"] = rev, dau
        D += timedelta(days=1)
    return {"coh": coh, "days": days, "start": D0, "last": LAST}


def test_the_triangle_learns_each_age_from_install_days_that_reached_it():
    app = make()
    T = date(2025, 7, 1)
    a, u, maxage = F.curve(app["coh"], T, D0, 100000)
    assert maxage == 180                                  # the oldest install day (181 days): its day-180 checkpoint
    for L in (0, 1, 5, 20, 30):
        assert abs(a[L] / a_true(L) - 1) < 0.01
    assert abs(sum(a[31:61]) / sum(a_true(L) for L in range(31, 61)) - 1) < 0.02   # the 31–60 band keeps its total
    assert abs(u[1] / u_true(1) - 1) < 0.02
    # a cohort that did twice as well: its scale says so, trusted more the older it is
    app["coh"][date(2025, 6, 1)]["d"] = [v * 2 for v in app["coh"][date(2025, 6, 1)]["d"]]
    app["coh"][date(2025, 6, 1)]["t"] = [v * 2 if v is not None else None for v in app["coh"][date(2025, 6, 1)]["t"]]
    s = F.scales(app["coh"], T, D0, a, 30)
    assert 1.4 < s[date(2025, 6, 1)] < 2.01 and abs(s[date(2025, 5, 1)] - 1) < 0.02


def test_the_forecast_meets_the_truth():
    app = make()
    T = date(2025, 9, 1)
    f = F.forecast(app, T, dict(F.DEFAULT, g=0.0), h=90)
    pred = [o + g + q for o, g, q in zip(f["rev"]["old"], f["rev"]["org"], f["rev"]["paid"])]
    act = [app["days"][T + timedelta(days=i)]["rev"] for i in range(1, 91)]
    assert abs(sum(pred[:30]) / sum(act[:30]) - 1) < 0.02 and abs(sum(pred) / sum(act) - 1) < 0.03
    assert abs(f["parts"]["org"] - 1000) < 1 and abs(f["parts"]["per_usd"] - 2.0) < 0.01   # $0.50 a paid install
    dau = sum(f["dau"][:30]) / sum(app["days"][T + timedelta(days=i)]["dau"] for i in range(1, 31))
    assert abs(dau - 1) < 0.03
    # spend doubled: the paid part doubles, the rest stays
    f2 = F.forecast(app, T, dict(F.DEFAULT, g=0.0), h=90, spend={T + timedelta(days=i): 1000.0 for i in range(1, 91)})
    assert abs(sum(f2["rev"]["paid"]) / sum(f["rev"]["paid"]) - 2) < 0.01 and sum(f2["rev"]["old"]) == sum(f["rev"]["old"])


def test_backtests_tune_calibrate_and_the_sudden_change():
    app = make()
    ors = F.origins(app)
    assert ors and ors[-1] == LAST - timedelta(days=30) and all((b - a).days == F.ORIGIN_STEP for a, b in zip(ors, ors[1:]))
    p, bt, steps = F.tune(app, None, passes=1)
    cal = F.calibrate(bt)
    assert cal[30]["mape"] < 0.03 and cal[30]["n"] >= F.MIN_TESTS and cal[30]["ev_rate"] == 0
    # installs ×5 for a month with spend unchanged: those tests are a sudden change, kept apart
    app2 = make(spike=(date(2025, 10, 1), 5))
    bt2 = F.backtest(app2, F.DEFAULT, None)
    hit = [r for r in bt2 if r.get("ev")]
    assert hit and all(e["kind"] == "installs" for r in hit for e in r["ev"].values())
    c2 = F.calibrate(bt2)
    assert c2[30]["ev_rate"] > 0 and c2[30]["mape_normal"] is not None and c2[30]["mape_normal"] < c2[30]["mape"]


def test_start_skips_the_trial_days_and_organic_installs():
    app = make(trial=20)
    assert F.auto_start({D: e for D, e in app["days"].items()}) == D0 + timedelta(days=20)
    days = {date(2025, 1, d): {"n": 100, "na": None, "sp": 0.0} for d in range(1, 15)}   # no Google Ads data, no spend
    assert F.installs_model(days, date(2025, 1, 14), 14) == (100.0, 0.0)
