"""🔮 Forecast — the build step (admob_iq.forecast_build) on a made-up app (tests/test_forecast_engine's): the inputs from
the ROI rows, the bias folded into the days, once a day (a fresh run kept), the build's budget (an app left over keeps
yesterday's run, a brand-new one waits), the owner's start date from config/forecast_starts.json, the learning log, the
live check once a forecast's days have happened, and the portfolio season saved at the end."""
import json
import os
from datetime import date, datetime, timedelta, timezone

from admob_iq import forecast_build as fb
from admob_iq.engine import forecast as F
from tests.test_forecast_engine import make, LAST, D0


def _rows_life(app):
    rows, life = [], []
    for X in sorted(app["coh"]):
        c, e = app["coh"][X], app["days"][X]
        rows.append({"X": X, "n": c["n"], "na": e["na"], "sp": e["sp"], "spi": e["sp"] * 90, "d": c["d"], "df": c["df"],
                     "u": c["u"], "t": c["t"], "e": {"u": c["ul"]}, "iu": {}})
        life.append([X.isoformat(), e["rev"], e["sp"], e["sp"] * 90])
    ida = {"days": {D.isoformat(): {"a": e["dau"]} for D, e in app["days"].items()}, "c": {}, "cset": []}
    return rows, life, ida


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_corrected_folds_the_bias_into_the_days():
    ser = {"old": [10.0] * 180, "org": [0.0] * 180, "paid": [0.0] * 180}
    fac = fb.corrected(ser, {30: {"bias": 0.25}, 90: {"bias": 0.0}})
    tot = [10.0 * f for f in fac]
    assert abs(sum(tot[:30]) - 300 / 1.25) < 1e-6 and abs(sum(tot[:90]) - 900) < 1e-6
    assert fac[100] == fac[89]                                   # 180 not ready: the last factor carries on


def test_app_step_once_a_day_budget_start_and_live(tmp_path):
    data = str(tmp_path / "data")
    os.makedirs(data)
    app = make(trial=10)
    rows, life, ida = _rows_life(app)
    P = {"S": LAST}
    now = datetime(2026, 1, 2, 6, tzinfo=timezone.utc)
    clock = Clock()
    run = fb.start(data, now, clock)
    fc = fb.app_step(run, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), [])
    assert fc and fc["start"] == (D0 + timedelta(days=10)).isoformat() and fc["start_set"] is None   # the trial days left out
    assert fc["ready"]["30"] and len(fc["f"]["old"]) == F.H and fc["f"]["d0"] == (LAST + timedelta(days=1)).isoformat()
    assert fc["cal"]["30"]["mape"] < 0.05 and fc["log"] and fc["log"][-1]["d"] == "2026-01-02"
    assert abs(fc["f"]["spi"] - 500 * 90) < 1e-6 and len(fc["hist"]["rev"]) == fb.HIST_DAYS
    saved = json.load(open(os.path.join(data, "forecast", "k1.json")))
    assert saved["live"][-1]["made"] == "2026-01-02" and saved["p"] == fc["p"]
    # the same day again: kept, nothing re-run
    run2 = fb.start(data, now + timedelta(hours=2), clock)
    assert fb.app_step(run2, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), []) == fc and run2.kept == 1
    # out of budget: a new app waits, an old one keeps its run
    clock.t = 10_000
    run3 = fb.start(data, now + timedelta(days=2), Clock())
    run3.t0 = -10_000
    assert fb.app_step(run3, "a~2", "k2", rows, P, ida, life, LAST.isoformat(), []) is None and run3.skipped == 1
    assert fb.app_step(run3, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), []) == fc
    # the owner's start date (config/ next to data/)
    os.makedirs(tmp_path / "config")
    (tmp_path / "config" / "forecast_starts.json").write_text(json.dumps({"a~1": "2025-03-01"}))
    run4 = fb.start(data, now + timedelta(days=3), Clock())
    fc4 = fb.app_step(run4, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), [])
    assert fc4["start"] == "2025-03-01" and fc4["start_set"] == "2025-03-01" and fc4["start_auto"] == fc["start_auto"]
    fb.finish(run4)
    st = json.load(open(os.path.join(data, "forecast", "state.json")))
    assert set(st["season"]) == {str(m) for m in range(1, 13)}
    assert fb.line(run4) == "forecast: ran 1, kept 0, skipped 0"


def test_live_check_once_the_days_happened(tmp_path):
    data = str(tmp_path / "data")
    os.makedirs(os.path.join(data, "forecast"))
    app = make()
    rows, life, ida = _rows_life(app)
    # a forecast made 40 days before LAST, of the next 30 days: checked against what happened
    T0 = LAST - timedelta(days=40)
    json.dump({"v": fb.V, "live": [{"made": "2025-11-21", "T": T0.isoformat(), "p30": 1.0, "p90": None, "p180": None}]},
              open(os.path.join(data, "forecast", "k1.json"), "w"))
    run = fb.start(data, datetime(2026, 1, 2, tzinfo=timezone.utc), Clock())
    fc = fb.app_step(run, "a~1", "k1", rows, {"S": LAST}, ida, life, LAST.isoformat(), [])
    chk = [c for c in fc["checks"] if c["made"] == "2025-11-21"]
    assert chk and chk[0]["h"] == 30 and chk[0]["act"] > 0 and chk[0]["err"] < -0.99


def test_admob_country_keeps_the_newest_days_only():
    from admob_iq.build_static import admob_country
    rows = [{"app_id": "a", "report_date": "2026-10-01", "country": "IN", "estimated_earnings_micros": 5, "impressions": 9},
            {"app_id": "a", "report_date": "2026-10-01", "country": "IN", "estimated_earnings_micros": 1, "impressions": 1},
            {"app_id": "a", "report_date": "2026-07-01", "country": "IN", "estimated_earnings_micros": 9, "impressions": 9},
            {"app_id": "a", "report_date": "2026-10-03", "country": "US", "estimated_earnings_micros": 9, "impressions": 9},
            {"app_id": "b", "report_date": "2026-10-01", "country": "", "estimated_earnings_micros": 9, "impressions": 9}]
    assert admob_country(rows, "2026-10-02") == {"a": {"2026-10-01": {"IN": [6, 10]}}}


def test_split_multiplies_back_to_the_revenue_change():
    """Revenue per day, last 14 days vs X = users × ads per user × country mix × each country's eCPM — exactly; a
    country whose share grew at a higher eCPM is named as the mix mover."""
    last = date(2026, 9, 30)
    days, cty = {}, {}
    for i in range(70):
        D = last - timedelta(days=i)
        now = i < 14
        days[D] = {"dau": 1200.0 if now else 1000.0}
        hi_imp, lo_imp = (3000, 7000) if now else (2000, 8000)       # more impressions from the better country
        hi_e, lo_e = (6.0 if now else 5.0), 1.0                       # … and its eCPM rose
        cty[D.isoformat()] = {"US": [int(hi_imp * hi_e / 1000 * 1e6), hi_imp], "IN": [int(lo_imp * lo_e / 1000 * 1e6), lo_imp]}
    s = fb.split({"days": days}, cty, last - timedelta(days=13), last, last - timedelta(days=69), last - timedelta(days=14))
    tot = s["rev"][0] / s["rev"][1]
    prod = (1 + s["users"]) * (1 + s["ipu"]) * (1 + s["mix"]) * (1 + s["rate"])
    assert abs(prod - tot) < 1e-3 and abs(s["users"] - 0.2) < 1e-6 and abs(s["ipu"] + 1 / 6) < 1e-3
    assert s["mix"] > 0 and s["rate"] > 0 and s["mix_top"][0][0] == "US" and s["rate_top"][0][0] == "US"
    assert fb.split({"days": days}, {}, last, last, last, last) is None


def test_inputs_carry_the_country_cells():
    app = make()
    rows, life, ida = _rows_life(app)
    ida["c"] = {"2025-06-02": {"0": {"n": 5, "r": [1] * 8, "u": [1] * 7}}}
    P = {"S": LAST}
    got = fb.inputs(rows, P, ida, life, LAST.isoformat())
    assert got["cty"] == {date(2025, 6, 2): {"0": {"n": 5, "r": [1] * 8, "u": [1] * 7}}}
