"""🔮 Forecast — the build step (admob_iq.forecast_build) on a made-up app (tests/test_forecast_engine's, + its GA4 day
ledger from tests/test_forecast_vd): the inputs from the ROI rows (GA4 bands, the GA4 lag), the bias folded into the
days, once a day (a fresh run kept, recomputed on today's data), the build's budget (an app left over keeps its last
run, a brand-new one waits; engine vd re-tunes only when its last tune's seconds fit), the owner's start date from
config/forecast_starts.json, the learning log, the live check once a forecast's days have happened, the engine switch
(FORECAST_ENGINE=v0 the rollback; a file of the other engine kept and recomputed by its own engine until re-made), and
the portfolio season + band ratios saved at the end and read back by the next build."""
import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq import forecast_build as fb
from admob_iq.engine import forecast as F
from admob_iq.engine import forecast_vd as VD
from tests.test_forecast_engine import make, LAST, D0
from tests.test_forecast_vd import with_ga4


@pytest.fixture(autouse=True)
def _engine_default(monkeypatch):
    monkeypatch.delenv("FORECAST_ENGINE", raising=False)


def _rows_life(app, ga4=False):
    rows, life = [], []
    for X in sorted(app["coh"]):
        c, e = app["coh"][X], app["days"][X]
        rows.append({"X": X, "n": c["n"], "na": e["na"], "sp": e["sp"], "spi": e["sp"] * 90, "d": c["d"], "df": c["df"],
                     "u": c["u"], "t": c["t"], "e": {"u": c["ul"]}, "iu": {}})
        life.append([X.isoformat(), e["rev"], e["sp"], e["sp"] * 90])
    ida = {"days": {D.isoformat(): {"a": e["dau"]} for D, e in app["days"].items()}, "c": {}, "cset": []}
    if ga4:                                              # + the GA4 day ledger (USD micros by install-age band)
        for D, g in with_ga4(app)["g4"].items():
            ida["days"][D.isoformat()].update(rev=g["rev"] * 1e6, rb=[x * 1e6 for x in g["rb"]], ab=g["ab"], cst="ok")
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
    rows, life, ida = _rows_life(app, ga4=True)
    P = {"S": LAST}
    now = datetime(2026, 1, 2, 6, tzinfo=timezone.utc)
    clock = Clock()
    run = fb.start(data, now, clock)
    fc = fb.app_step(run, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), [])
    assert fc and fc["start"] == (D0 + timedelta(days=10)).isoformat() and fc["start_set"] is None   # the trial days left out
    assert fc["ready"]["30"] and len(fc["f"]["old"]) == F.H and fc["f"]["d0"] == (LAST + timedelta(days=1)).isoformat()
    assert fc["cal"]["30"]["mape"] < 0.05 and fc["log"] and fc["log"][-1]["d"] == "2026-01-02"
    assert abs(fc["f"]["spi"] - 500 * 90) < 1e-6 and len(fc["hist"]["rev"]) == fb.HIST_DAYS
    assert fc["eng"] == "vd" and fc["v"] == 2 and set(fc["p"]) == set(VD.GRID)                       # engine vd: 3 mix weights
    assert fc["parts"]["glag"] == 5 and len(fc["parts"]["arp"]) == 7 and fc["parts"]["org"] > 0       # both views, GA4 lag 5
    assert all(len(fc["f"][k]) == F.H for k in ("old", "org", "paid", "dau", "n", "sp")) and fc["f"]["dau_p"]
    saved = json.load(open(os.path.join(data, "forecast", "k1.json")))
    assert saved["live"][-1]["made"] == "2026-01-02" and saved["p"] == fc["p"] and saved["v"] == 2
    assert saved["tune_sec"] == 0.0
    # the same day again: kept, nothing re-run
    run2 = fb.start(data, now + timedelta(hours=2), clock)
    assert fb.app_step(run2, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), []) == fc and run2.kept == 1
    # … but its "why" is today's: the AdMob country rows that came since show up without a model run
    cty = {(LAST - timedelta(days=i)).isoformat(): {"US": [2000000, 1000], "IN": [500000, 4000]} for i in range(70)}
    k2 = fb.app_step(fb.start(data, now + timedelta(hours=3), clock), "a~1", "k1", rows, P, ida, life, LAST.isoformat(),
                     [], rev_cty=cty)
    assert k2["drv"]["split"]["mix"] == 0 and k2["f"] == fc["f"] and "split" not in fc["drv"]
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
    assert st["vd_struct"] == {"v": VD.STRUCT_VERSION, "p": VD.STRUCT} and st["bandr"]       # one app: ratios 1
    assert all(v == [1.0] * 7 and date.fromisoformat(k).weekday() == 0 for k, v in st["bandr"].items())
    assert fb.line(run4).startswith("forecast vd: ran 1, kept 0, skipped 0; tune ")


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


def test_inputs_carry_the_country_cells_and_the_ga4_ledger():
    app = make()
    rows, life, ida = _rows_life(app, ga4=True)
    ida["c"] = {"2025-06-02": {"0": {"n": 5, "r": [1] * 8, "u": [1] * 7}}}
    P = {"S": LAST}
    got = fb.inputs(rows, P, ida, life, LAST.isoformat())
    assert got["cty"] == {date(2025, 6, 2): {"0": {"n": 5, "r": [1] * 8, "u": [1] * 7}}}
    D = LAST - timedelta(days=40)
    g, want = got["g4"][D], app["g4"][D]                 # GA4 USD by install-age band, active users, AdMob ÷ GA4
    assert abs(g["rev"] - want["rev"]) < 1e-6 and all(abs(a - b) < 1e-6 for a, b in zip(g["rb"], want["rb"]))
    assert g["ab"] == want["ab"] and abs(g["k"] - 1.0) < 1e-9 and max(got["g4"]) == LAST - timedelta(days=5)
    assert got["glag"] == 5 and got["clag"] == 0 and got["tlag"] == 0 and got["ida"] is ida
    assert fb.inputs(rows, P, {}, life, LAST.isoformat())["glag"] == 0
    # the checkpoints after day 30 (60 / 90 / 180 / 365) landing 5 days after AdMob: tlag 5 (the back-tests cut them so)
    late = [dict(r, t=[None if A > 30 and r["X"] + timedelta(days=A) > LAST - timedelta(days=5) else v
                       for A, v in zip(F.T_AGES, r["t"])]) for r in rows]
    assert fb.inputs(late, P, ida, life, LAST.isoformat())["tlag"] == 5
    none = [dict(r, t=[v if A <= 30 else None for A, v in zip(F.T_AGES, r["t"])]) for r in rows]
    assert fb.inputs(none, P, ida, life, LAST.isoformat())["tlag"] == 0          # none yet (a young app): nothing to cut


def test_the_engine_switch_and_the_rollback(tmp_path, monkeypatch):
    """FORECAST_ENGINE=v0 runs the earlier engine (files v 1); back on vd, a v 1 file is kept — recomputed on today's
    data by v0 itself — until a build has the budget to re-make it with vd (files v 2); and the other way round."""
    data = str(tmp_path / "data")
    os.makedirs(data)
    app = make()
    rows, life, ida = _rows_life(app, ga4=True)
    P, now = {"S": LAST}, datetime(2026, 1, 2, 6, tzinfo=timezone.utc)
    monkeypatch.setenv("FORECAST_ENGINE", "v0")
    run = fb.start(data, now, Clock())
    f0 = fb.app_step(run, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), [])
    assert run.eng == "v0" and f0["v"] == 1 and "hl" in f0["p"] and "parts" in f0
    monkeypatch.delenv("FORECAST_ENGINE")
    broke = fb.start(data, now + timedelta(days=1), Clock())
    broke.t0 = -10_000                                   # no budget: the v0 run kept, recomputed by v0
    k = fb.app_step(broke, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), [])
    assert broke.eng == "vd" and broke.kept == 1 and k["v"] == 1 and k["p"] == f0["p"] and k["f"] == f0["f"]
    run2 = fb.start(data, now + timedelta(days=1), Clock())
    f2 = fb.app_step(run2, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), [])
    assert run2.ran == 1 and f2["v"] == 2 and set(f2["p"]) == set(VD.GRID)
    assert json.load(open(os.path.join(data, "forecast", "k1.json")))["v"] == 2
    # the learning log goes on across the switch: the first vd entry says which engine and that every setting is new
    assert f0["log"][-1]["eng"] == "v0" and f0["log"][-1]["changed"] == []
    assert len(f2["log"]) == 2 and f2["log"][-1]["eng"] == "vd" and f2["log"][-1]["changed"] == sorted(VD.GRID)
    a = dict(fb.inputs(rows, P, ida, life, LAST.isoformat()), start=D0)
    assert f2["log"][-1]["sc_old"] is None and f2["start"] == D0.isoformat()
    assert f2["log"][-1]["sc"] == round(VD.objective(VD.backtest(a, f2["p"], F.season(a["days"]))), 4)
    monkeypatch.setenv("FORECAST_ENGINE", "v0")          # the rollback, out of budget: the vd run kept (by vd)
    back = fb.start(data, now + timedelta(days=2), Clock())
    back.t0 = -10_000
    k2 = fb.app_step(back, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), [])
    assert back.kept == 1 and k2["v"] == 2 and k2["f"] == f2["f"]
    back2 = fb.start(data, now + timedelta(days=2), Clock())           # … and with the budget: re-made by v0
    f3 = fb.app_step(back2, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), [])
    assert back2.ran == 1 and f3["v"] == 1 and f3["eng"] == "v0" and "hl" in f3["p"] and f3["log"][-1]["eng"] == "v0"


def test_vd_kept_forecast_follows_a_new_day(tmp_path):
    """Engine vd between its daily tunes: a build with a new day of data re-makes the forecast from that day with the
    stored setting (no tune, the log as it was) — the page never shows the day before's forecast."""
    data = str(tmp_path / "data")
    os.makedirs(data)
    app = make()
    rows, life, ida = _rows_life(app, ga4=True)
    y = LAST - timedelta(days=1)
    rows1, life1 = [r for r in rows if r["X"] <= y], [x for x in life if x[0] <= y.isoformat()]
    ida1 = dict(ida, days={k: v for k, v in ida["days"].items() if k <= y.isoformat()})
    now = datetime(2026, 1, 2, 6, tzinfo=timezone.utc)
    f1 = fb.app_step(fb.start(data, now, Clock()), "a~1", "k1", rows1, {"S": y}, ida1, life1, y.isoformat(), [])
    assert f1["T"] == y.isoformat()
    run = fb.start(data, now + timedelta(hours=3), Clock())
    f2 = fb.app_step(run, "a~1", "k1", rows, {"S": LAST}, ida, life, LAST.isoformat(), [])
    assert run.kept == 1 and run.ran == 0 and run.tune_sec == []
    assert f2["T"] == LAST.isoformat() and f2["f"]["d0"] == (LAST + timedelta(days=1)).isoformat()
    assert f2["p"] == f1["p"] and f2["log"] == f1["log"] and f2["f"]["old"] != f1["f"]["old"]
    a = dict(fb.inputs(rows, {"S": LAST}, ida, life, LAST.isoformat()), port={"bandr": {}})
    a["start"] = F.auto_start({D: e for D, e in a["days"].items() if e.get("n") is not None})
    want = VD.forecast(a, LAST, f1["p"], h=F.H, seas=F.season(a["days"]))      # the stored setting on today's data
    assert f2["f"]["dau"] == [round(v, 1) for v in want["dau"]] and f2["parts"]["q"] == round(want["parts"]["q"], 6)
    assert json.load(open(os.path.join(data, "forecast", "k1.json")))["T"] == y.isoformat()   # the file: the tune's


def test_vd_setting_stored_before_the_ga4_switches(tmp_path):
    """A vd setting stored before the switches gc / pc existed reads as them at their default (off): a re-tune that
    keeps everything adds no learning-log entry; one that turns a switch on names only that one."""
    data = str(tmp_path / "data")
    os.makedirs(data)
    app = make()
    rows, life, ida = _rows_life(app, ga4=True)
    P, now = {"S": LAST}, datetime(2026, 1, 2, 6, tzinfo=timezone.utc)
    fc = fb.app_step(fb.start(data, now, Clock()), "a~1", "k1", rows, P, ida, life, LAST.isoformat(), [])
    path = os.path.join(data, "forecast", "k1.json")
    saved = json.load(open(path))
    saved["p"] = {k: v for k, v in saved["p"].items() if k not in ("gc", "pc")}      # as stored by the earlier engine
    json.dump(saved, open(path, "w"))
    run = fb.start(data, now + timedelta(days=1), Clock())
    f = fb.app_step(run, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), [])
    assert run.ran == 1 and f["p"] == fc["p"] and f["p"]["gc"] == 0 and f["log"] == fc["log"]
    assert fb.line(run).endswith("GA4 late cells 0, paid cells 0; budget planner 0")


def test_vd_setting_the_engine_cannot_make_is_tuned_at_once(tmp_path):
    """Within EVERY_H a vd file is kept — unless its setting is one the current engine's tune could not have made: a
    setting stored before the switches gc / pc existed (never tested with them) or with a switch the engine now holds
    off. Those are re-tuned in the next build, not a day later; a current one is kept."""
    data = str(tmp_path / "data")
    os.makedirs(data)
    app = make()
    rows, life, ida = _rows_life(app, ga4=True)
    P, now = {"S": LAST}, datetime(2026, 1, 2, 6, tzinfo=timezone.utc)
    fc = fb.app_step(fb.start(data, now, Clock()), "a~1", "k1", rows, P, ida, life, LAST.isoformat(), [])
    path = os.path.join(data, "forecast", "k1.json")
    saved = json.load(open(path))
    run = fb.start(data, now + timedelta(hours=3), Clock())
    fb.app_step(run, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), [])
    assert run.kept == 1 and run.ran == 0                                # a current setting: kept
    for p in ({k: v for k, v in saved["p"].items() if k not in ("gc", "pc")},   # stored before the switches
              dict(saved["p"], gc=2)):                                          # a switch now held off
        json.dump(dict(saved, p=p), open(path, "w"))
        run = fb.start(data, now + timedelta(hours=3), Clock())
        f = fb.app_step(run, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), [])
        assert run.ran == 1 and run.kept == 0 and f["p"] == fc["p"] and f["p"]["gc"] == 0
    assert not fb._tuned_now(VD, {"bo": 0.5, "bn": 0.5, "cq": 0.0}) and fb._tuned_now(VD, fc["p"])


def test_vd_tunes_only_when_its_seconds_fit(tmp_path):
    """A day later the setting is stale; with less budget left than TUNE_MARGIN × the app's last tune seconds the build
    keeps the setting (today's forecast with it) and tunes another time."""
    data = str(tmp_path / "data")
    os.makedirs(data)
    app = make()
    rows, life, ida = _rows_life(app, ga4=True)
    P, now = {"S": LAST}, datetime(2026, 1, 2, 6, tzinfo=timezone.utc)
    fc = fb.app_step(fb.start(data, now, Clock()), "a~1", "k1", rows, P, ida, life, LAST.isoformat(), [])
    path = os.path.join(data, "forecast", "k1.json")
    saved = json.load(open(path))
    saved["tune_sec"] = 100.0                            # 1.3 × 100 s > the 120 s a build has
    json.dump(saved, open(path, "w"))
    run = fb.start(data, now + timedelta(days=1), Clock())
    k = fb.app_step(run, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), [])
    assert run.kept == 1 and run.ran == 0 and k["f"] == fc["f"] and k["p"] == fc["p"]
    saved["tune_sec"] = 50.0
    json.dump(saved, open(path, "w"))
    run2 = fb.start(data, now + timedelta(days=1), Clock())
    assert fb.app_step(run2, "a~1", "k1", rows, P, ida, life, LAST.isoformat(), []) and run2.ran == 1


def test_band_ratios_saved_and_read_back(tmp_path):
    """finish() keeps the portfolio's band ratios per Monday (3 apps or more); the next build reads them, and the
    engine's band ARPDAU prior uses them."""
    data = str(tmp_path / "data")
    os.makedirs(data)
    run = fb.start(data, datetime(2026, 1, 2, 6, tzinfo=timezone.utc), Clock())
    app = make()
    rows, life, ida = _rows_life(app, ga4=True)
    for i in range(3):
        fb.app_step(run, "a~%d" % i, "k%d" % i, rows, {"S": LAST}, ida, life, LAST.isoformat(), [])
    assert len(run.pool_b) == 3
    fb.finish(run)
    st = json.load(open(os.path.join(data, "forecast", "state.json")))
    br = st["bandr"]
    M = max(br)
    assert date.fromisoformat(M).weekday() == 0 and date.fromisoformat(M) <= LAST + timedelta(days=7)
    assert br[M][0] == 1.0 and br[M][1] != 1.0 and all(0.1 <= x <= 2.0 for x in br[M])
    run2 = fb.start(data, datetime(2026, 1, 3, 6, tzinfo=timezone.utc), Clock())
    assert run2.bandr == br
    one = fb.inputs(rows, {"S": LAST}, ida, life, LAST.isoformat())
    one.update(start=D0, port={"bandr": run2.bandr})
    assert VD._port_ratio(VD._pre(one), date.fromisoformat(M)) == br[M]
    assert VD.port_pre(one)["lag"] == 5                  # each app's GA4 lag goes with its data


def test_a_build_without_the_season_keeps_the_saved_one(tmp_path):
    """No app gave a day with both revenue and active users this build (e.g. the GA4 ledger missing): state.json keeps
    the saved portfolio season (and band ratios) — the next build still reads all 12 months."""
    data = str(tmp_path / "data")
    os.makedirs(os.path.join(data, "forecast"))
    seas = {str(m): round(1.0 + m / 100, 4) for m in range(1, 13)}
    json.dump({"v": 1, "season": seas, "bandr": {"2026-01-05": [1.0] * 7}},
              open(os.path.join(data, "forecast", "state.json"), "w"))
    run = fb.start(data, datetime(2026, 1, 6, tzinfo=timezone.utc), Clock())
    assert run.season and len(run.season) == 12
    life = [["2026-01-0%d" % i, 10.0, 0.0, 0.0] for i in range(1, 6)]
    fb.app_step(run, "a~1", "k1", [], {"S": None}, None, life, "2026-01-05", [])
    assert not run.pool and not run.pool_b
    fb.finish(run)
    st = json.load(open(os.path.join(data, "forecast", "state.json")))
    assert st["season"] == seas and st["bandr"] == {"2026-01-05": [1.0] * 7}
    assert fb.start(data, datetime(2026, 1, 7, tzinfo=timezone.utc), Clock()).season == run.season


def test_the_ecpm_calendar_reaches_the_page(tmp_path):
    """📅 build_static's calendar (fc_calendar.seasons + the measured holidays) → roi_build.start → the forecast's run →
    every app's forecast: fc["fcal"] = the coming event weeks; the holidays measured once (Ramadan, Diwali) shown with
    the app's own revenue share there but NOT in the forecast; without a calendar no fcal and the plain forecast."""
    import math
    from admob_iq import roi_build as rb
    from tests.test_forecast_cal import calendar
    app = make()
    rows, life, ida = _rows_life(app, ga4=True)
    now = datetime(2026, 1, 2, 6, tzinfo=timezone.utc)
    cty = {(LAST - timedelta(days=i)).isoformat(): {"ID": [2e6, 1000], "US": [6e6, 1000]} for i in range(40)}
    out = []
    for i, cal in enumerate((dict(calendar(), hol={"ramadan": {"y": 2025, "x": math.log(0.95), "cells": [3, 9]}}),
                             calendar(), None)):
        data = str(tmp_path / ("data%d" % i))
        os.makedirs(data)
        acc = rb.start(cal=cal)
        assert acc.cal is cal
        run = fb.start(data, now, Clock(), cal=acc.cal)
        out.append(fb.app_step(run, "a~1", "k1", rows, {"S": LAST}, ida, life, LAST.isoformat(), [], rev_cty=cty))
    fe = out[0]["fcal"]
    assert fe["n"] == 2 and [x["k"] for x in fe["ev"]] == ["j1", "j2", "j3", "j4", "j5", "j6", "hold"]
    assert all(x["e"] < 0 for x in fe["ev"])
    if VD.STRUCT["cal"]:                                                                   # in the forecast
        assert fe["use"] == 1 and all(x["o"] < 0 for x in fe["ev"]) and out[2]["f"]["old"] != out[0]["f"]["old"]
    else:                                                                                  # held off: shown only
        assert fe["use"] == 0 and all(x["o"] is None for x in fe["ev"]) and out[2]["f"]["old"] == out[0]["f"]["old"]
    hol = fe["hol"]
    assert [h["k"] for h in hol] == ["ramadan"] and hol[0]["a"] == "2026-02-18" and hol[0]["y"] == 2025
    assert abs(hol[0]["x"] + 0.05) < 1e-4 and abs(hol[0]["s"] - 0.25) < 1e-9 and abs(hol[0]["app"] + 0.0125) < 1e-4
    assert hol[0]["c"] == [3, 9]                                                          # (the cells it rests on)
    assert hol[0]["xt"] is None and hol[0]["xc"] is None                                  # (a measure without its parts)
    assert out[1]["f"]["old"] == out[0]["f"]["old"] and "hol" not in out[1]["fcal"]      # the holidays: page only
    assert out[2]["fcal"] is None                                                         # no calendar: nothing shown


def test_the_weekday_rhythm_keeps_every_total():
    """📅 The after-call weekday rhythm on the page's daily forecast: each day × its weekday's factor, every part's
    30 / 90 / 180-day totals unchanged; no factors: the series as it was."""
    d0 = date(2026, 10, 16)                                    # a Friday
    W = [1.02, 1.02, 1.01, 1.01, 1.0, 0.99, 0.95]
    ser = {"old": [10.0] * 180, "org": [2.0 + 0.01 * i for i in range(180)], "paid": [3.0] * 180}
    out = fb.weekly(ser, d0, W)
    for k in ser:
        for a, b in ((0, 30), (30, 90), (90, 180)):
            assert abs(sum(out[k][a:b]) - sum(ser[k][a:b])) < 5e-3                  # (4-decimal rounding)
    sun = 2                                                    # Oct 18, 2026: a Sunday
    assert out["old"][sun] < out["old"][sun - 1] and abs(out["old"][sun] / out["old"][0] - 0.95 / 1.0) < 1e-3
    assert fb.weekly(ser, d0, None) is ser


def test_the_weekday_rhythm_reaches_the_page(tmp_path):
    """📅 build_static's per-trigger revenue (fc_calendar.trigger_days) → each app's weekday factors → the page's daily
    forecast takes them (the fcal["wk"] note), every 30 / 90 / 180-day total as without them."""
    from tests.test_forecast_cal import calendar
    app = make()
    rows, life, ida = _rows_life(app, ga4=True)
    now = datetime(2026, 1, 2, 6, tzinfo=timezone.utc)
    ac, inf = {}, {}
    d = LAST - timedelta(days=139)
    while d <= LAST:
        ac[d.isoformat()] = 40.0 * (0.85 if d.weekday() == 6 else 1.0)
        inf[d.isoformat()] = 60.0
        d += timedelta(days=1)
    out = []
    for i, wk in enumerate(({"a~1": {"after-call": ac, "in-feature": inf}}, None)):
        data = str(tmp_path / ("w%d" % i))
        os.makedirs(data)
        run = fb.start(data, now, Clock(), cal=dict(calendar(), wk=wk) if wk else calendar())
        out.append(fb.app_step(run, "a~1", "k1", rows, {"S": LAST}, ida, life, LAST.isoformat(), []))
    W = out[0]["fcal"]["wk"]
    assert len(W) == 7 and W[6] < 0.95 and "wk" not in out[1]["fcal"]
    for k in ("old", "org", "paid"):
        a, b = out[0]["f"][k], out[1]["f"][k]
        assert a != b and all(abs(sum(a[x:y]) - sum(b[x:y])) < 5e-3 for x, y in ((0, 30), (30, 90), (90, 180)))
    # no complete season yet (a new account): the rhythm still reaches the daily line, no event week is shown
    data = str(tmp_path / "w2")
    os.makedirs(data)
    run = fb.start(data, now, Clock(), cal={"v": 1, "till": LAST.isoformat(), "s": {}, "hol": {},
                                             "wk": {"a~1": {"after-call": ac, "in-feature": inf}}})
    o2 = fb.app_step(run, "a~1", "k1", rows, {"S": LAST}, ida, life, LAST.isoformat(), [])
    assert o2["fcal"]["wk"] == W and o2["fcal"]["ev"] == [] and (o2["f"] == out[0]["f"] or VD.STRUCT["cal"])
    assert fb.start(data, now, Clock(), cal={"v": 1, "s": {}, "hol": {}, "wk": {}}).cal is None
