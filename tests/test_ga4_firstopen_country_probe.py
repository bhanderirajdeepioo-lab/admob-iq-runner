"""The First open country probe: every country is read in rounds of 15 (no cut), and the sum is checked against the total.
Synthetic data only (this repo is public)."""
from datetime import date

from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_firstopen_country_probe as cp

STEPS = {"splash": "SplashScreen", "home": "HomeScreen"}


def _table(rows, dim):
    return {"funnelTable": {"dimensionHeaders": [{"name": "funnelStepName"}, {"name": dim}],
                            "metricHeaders": [{"name": "activeUsers"}],
                            "rows": [{"dimensionValues": [{"value": s}, {"value": b}], "metricValues": [{"value": str(v)}]}
                                     for s, b, v in rows]}}


class FakeGa:
    """GA4 with 40 synthetic countries (C00 … C39): the breakdown answers the 15 biggest not excluded from step 1."""

    def __init__(self):
        self.tok, self.calls, self.bodies = 0, 0, []
        self.data = {"C%02d" % i: (100 - i, 90 - i, 50 - i) for i in range(40)}

    def funnel(self, body):
        self.calls += 1
        self.tok += 7
        self.bodies.append(body)
        dim = body["funnelBreakdown"]["breakdownDimension"]["name"]
        if dim == "date":
            t = [sum(v[i] for v in self.data.values()) for i in range(3)]
            return _table([("1. first_open", "20261001", t[0]), ("2. splash", "20261001", t[1]),
                           ("3. step", "20261001", t[2]), ("1. first_open", cp.RT, t[0]), ("2. splash", cp.RT, t[1]),
                           ("3. step", cp.RT, t[2])], "date")
        f = body["funnel"]["steps"][0]["filterExpression"]
        ex = set()
        if "andGroup" in f:
            ex = set(f["andGroup"]["expressions"][1]["notExpression"]["funnelFieldFilter"]["inListFilter"]["values"])
        rest = [c for c in self.data if c not in ex]
        left = sorted(rest, key=lambda c: -self.data[c][0])[:gf.CHUNK]
        rows = [("%d. %s" % (i + 1, s), cp.RT, sum(self.data[c][i] for c in rest)) for i, s in
                enumerate(("first_open", "splash", "step"))]
        for c in left:
            a, b, h = self.data[c]
            rows += [("1. first_open", c, a), ("2. splash", c, b), ("3. step", c, h)]
        return _table(rows, dim)


def test_rounds_read_every_country_and_stop_on_an_empty_round():
    ga = FakeGa()
    r = cp.by_country(ga, STEPS, date(2026, 10, 1))
    assert len(r["countries"]) == 40 and r["rounds"] == 4 and not r["capped"]       # 15 + 15 + 10, then an empty round
    assert r["countries"]["C39"] == [61, 51, 11] and r["tokens"] == 28 and cp.RT not in r["countries"]
    assert r["rt"][0] == [sum(100 - i for i in range(40)), sum(90 - i for i in range(40)), sum(50 - i for i in range(40))]
    assert r["rt"][-1] == [0, 0, 0]                                    # nothing left after the last named country
    # round n leaves out exactly the countries of rounds 1 … n-1, on step 1 only
    second = ga.bodies[1]["funnel"]["steps"]
    vals = second[0]["filterExpression"]["andGroup"]["expressions"][1]["notExpression"]["funnelFieldFilter"]
    assert vals["fieldName"] == "countryId" and len(vals["inListFilter"]["values"]) == 15
    assert "andGroup" not in second[1]["filterExpression"] and "andGroup" not in second[2]["filterExpression"]
    assert ga.bodies[0]["funnel"]["steps"][0]["filterExpression"] == {"funnelEventFilter": {"eventName": "first_open"}}


def test_coverage_is_the_sum_over_countries_against_the_total():
    class Ga(FakeGa):
        pass
    ga = Ga()
    store = {"app_id": "ca-app-pub-0~1", "steps": STEPS, "property_id": "1", "stream_id": "2", "time_zone": "UTC"}
    real_app = gf.App
    gf.App = lambda *a, **k: ga
    try:
        res = cp.probe_app(store, "tok", {"quota": None, "stop": None}, lambda: None, today_of=lambda tz: date(2026, 10, 20))
    finally:
        gf.App = real_app
    assert res["complete"] and len(res["days"]) == len(cp.DAYS_BACK)
    d = res["days"]["2026-10-17"]
    assert d["coverage"] == {"first_open": 1.0, "splash": 1.0, "home": 1.0} and d["n"] == 40 and d["under10"] == 0
    assert cp.counts({"k": res})["full_cover"] == len(cp.DAYS_BACK)


def test_public_line_is_counts_only():
    line = cp.public_line(cp.counts({}))
    assert line.startswith("firstopen country probe: apps 0") and "ca-app" not in line
