"""GA4 strict first-open funnel probe (admob_iq.fetch.ga4_funnel_probe + .github/workflows/ga4-funnel-probe.yml) — offline,
made-up apps / screens / numbers: the screens it picks per app (a home with its own name too), the CLOSED funnels it asks
(first_open → Splash within 10 min → step within 60 min; Home again with the Splash at any time), the day / month pieces
of the full history, the table it reads, resume, and a PUBLIC log that stays counts-only."""
import json
import os
from datetime import date

import yaml

from admob_iq.fetch import ga4_funnel_probe as fp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG, PKG_B = "com.example.alpha", "com.example.beta"


def test_picks_the_steps_and_a_home_with_its_own_name():
    disc = [["MainActivity", 900], ["AdActivity", 800], ["AppSplashActivity", 700], ["SplashLanguageActivity", 300],
            ["PermissionActivity", 500], ["SettingPermissionActivity", 200], ["CallerCadHomeDialogActivity", 950],
            ["HomeSearchActivity", 990], ["IntroActivity", 50], ["WelcomeBackActivity", 40]]
    assert fp.pick_steps(disc) == {"home": "MainActivity", "splash": "AppSplashActivity", "language": "SplashLanguageActivity",
                                   "permission": "PermissionActivity", "intro": "IntroActivity"}
    own = [["SplashActivity", 808], ["CalculatorActivity", 603], ["AdActivity", 395], ["UnitConverterActivity", 51],
           ["PlayCoreDialogWrapperActivity", 46], ["AboutCalcActivity", 28], ["CallerCadHomeNativeFullActivity", 3]]
    assert fp.pick_steps(own) == {"splash": "SplashActivity", "home": "CalculatorActivity"}   # the most-seen non-step screen


def test_the_funnels_are_closed_and_in_order():
    b = fp.funnel_body("SplashActivity", "MainActivity", date(2026, 9, 1), date(2026, 9, 15), "date")
    f = b["funnel"]
    assert f["isOpenFunnel"] is False and [s["name"] for s in f["steps"]] == ["first_open", "splash", "step"]
    assert f["steps"][0]["filterExpression"] == {"funnelEventFilter": {"eventName": "first_open"}}
    assert f["steps"][1]["withinDurationFromPriorStep"] == "600s" and f["steps"][2]["withinDurationFromPriorStep"] == "3600s"
    p = f["steps"][2]["filterExpression"]["funnelEventFilter"]
    assert p["eventName"] == "screen_view" and p["funnelParameterFilterExpression"]["funnelParameterFilter"] == {
        "eventParameterName": "firebase_screen_class", "stringFilter": {"matchType": "EXACT", "value": "MainActivity"}}
    assert b["funnelBreakdown"] == {"breakdownDimension": {"name": "date"}, "limit": "15"}
    assert b["dateRanges"] == [{"startDate": "2026-09-01", "endDate": "2026-09-15"}]
    anyt = fp.funnel_body("SplashActivity", "MainActivity", date(2026, 9, 1), date(2026, 9, 15), "date", any_time=True)
    assert "withinDurationFromPriorStep" not in anyt["funnel"]["steps"][1]               # a first run in the background
    assert anyt["funnel"]["steps"][2]["withinDurationFromPriorStep"] == "3600s"


def test_pieces_cover_the_history_and_the_table_is_read():
    d = fp._chunks(date(2026, 8, 1), date(2026, 9, 29), step_days=15)
    assert d[0] == (date(2026, 8, 1), date(2026, 8, 15)) and d[-1] == (date(2026, 9, 15), date(2026, 9, 29)) and len(d) == 4
    m = fp._chunks(date(2023, 8, 1), date(2026, 10, 13), months=15)
    assert m[0] == (date(2023, 8, 1), date(2024, 10, 31)) and m[1][0] == date(2024, 11, 1) and m[-1][1] == date(2026, 10, 13)
    j = {"funnelTable": {"dimensionHeaders": [{"name": "funnelStepName"}, {"name": "date"}],
                         "metricHeaders": [{"name": "activeUsers"}, {"name": "completionRate"}],
                         "rows": [{"dimensionValues": [{"value": "1. first_open"}, {"value": "20261001"}], "metricValues": [{"value": "100"}, {"value": "0.9"}]},
                                  {"dimensionValues": [{"value": "2. splash"}, {"value": "20261001"}], "metricValues": [{"value": "90"}, {"value": "0.8"}]},
                                  {"dimensionValues": [{"value": "3. step"}, {"value": "RESERVED_TOTAL"}], "metricValues": [{"value": "70"}, {"value": "0"}]}]}}
    assert fp.parse_table(j) == {"first_open": {"20261001": 100}, "splash": {"20261001": 90}, "step": {"RESERVED_TOTAL": 70}}


class FakeApp:
    asked = []

    def __init__(self, token, pid, sid, run, prop=None):
        self.kind, self.calls, self.tok, self.by_kind = "other", 0, 0, {}

    def funnel(self, body):
        self.calls += 1
        self.tok += 3
        FakeApp.asked.append((self.kind, body))
        b = body["funnelBreakdown"]["breakdownDimension"]["name"]
        v = "20261001" if b == "date" else "202610"
        rows = [(n, s) for n, s in (("first_open", 100), ("splash", 90), ("step", 60))]
        return {"funnelTable": {"dimensionHeaders": [{"name": "funnelStepName"}, {"name": b}], "metricHeaders": [{"name": "activeUsers"}],
                                "rows": [{"dimensionValues": [{"value": "%d. %s" % (i + 1, n)}, {"value": v}], "metricValues": [{"value": str(s)}]}
                                         for i, (n, s) in enumerate(rows)]}}


FIRST = {PKG: {"disc_screens": [["SplashActivity", 100], ["LanguageActivity", 80], ["MainActivity", 70]]},
         PKG_B: {"disc_screens": [["SomeActivity", 5]]}}


def _unit(pkg):
    return {"package": pkg, "property_id": "111", "stream_id": "222", "tz": "Asia/Kolkata", "owner": "o", "app_ids": ["a~1"]}


def test_probe_unit_asks_each_funnel_by_day_and_month(monkeypatch):
    FakeApp.asked = []
    monkeypatch.setattr(fp, "App", FakeApp)
    monkeypatch.setattr(fp.ap, "pick_store", lambda u, d: ("a~1", {"history_start": "2026-07-20"}))
    r = fp.probe_unit(fp.Run(budget=60), _unit(PKG), "tok", "/x", fp.pr.new_prop(), FIRST)
    assert r["complete"] and r["steps"] == {"splash": "SplashActivity", "language": "LanguageActivity", "home": "MainActivity"}
    kinds = sorted({k for k, _ in FakeApp.asked})
    assert kinds == ["daily_home", "daily_home_any", "daily_language", "monthly_home", "monthly_home_any", "monthly_language"]
    assert r["daily"]["home"]["step"] == {"2026-10-01": 60} and r["monthly"]["home_any"]["splash"] == {"2026-10": 90}
    homes = [b for k, b in FakeApp.asked if k == "daily_home"]
    assert all(b["funnel"]["steps"][2]["filterExpression"]["funnelEventFilter"]["funnelParameterFilterExpression"]
               ["funnelParameterFilter"]["stringFilter"]["value"] == "MainActivity" for b in homes)
    first_month = [b for k, b in FakeApp.asked if k == "monthly_home"][0]
    assert first_month["dateRanges"][0]["startDate"] == "2026-07-20"            # the full history from its first day
    r2 = fp.probe_unit(fp.Run(budget=60), _unit(PKG_B), "tok", "/x", fp.pr.new_prop(), FIRST)
    assert r2["err"] == "no_splash_or_home" and not r2["complete"]


def test_main_writes_privately_and_prints_counts_only(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(fp, "App", FakeApp)
    monkeypatch.setattr(fp.ap, "pick_store", lambda u, d: ("a~1", {"history_start": "2026-09-20"}))
    monkeypatch.setattr(fp.vr, "units_from_state", lambda st: [_unit(PKG), _unit(PKG_B)])
    monkeypatch.setattr(fp.gu, "load_state", lambda d: {})
    monkeypatch.setattr(fp.ga4, "access_token", lambda c, s, r: "tok")
    monkeypatch.setattr(fp.ga4_probe, "owner_tokens", lambda env: ([("o", "rt")], None))
    put = {}
    monkeypatch.setattr(fp.pr, "write_private", lambda path, text, msg: bool(put.update({path: text})) or True)
    os.makedirs(tmp_path / "ga4")
    (tmp_path / fp.FIRST_PATH).write_text(json.dumps({"apps": FIRST}), encoding="utf-8")
    fp.main({"GA4_CLIENT_ID": "c", "GA4_CLIENT_SECRET": "s", "FUNNEL_DATA_DIR": str(tmp_path)})
    rep = json.loads(put[fp.OUT_PATH])
    assert rep["counts"]["complete"] == 1 and rep["counts"]["errors"] == 1
    out = capsys.readouterr().out
    assert "com.example" not in out and "Activity" not in out and out.strip().splitlines()[-1] == "funnel probe: report written"


def test_the_workflow_keeps_secrets_and_details_off_the_public_log():
    with open(os.path.join(ROOT, ".github", "workflows", "ga4-funnel-probe.yml"), encoding="utf-8") as fh:
        wf = yaml.safe_load(fh.read())
    on = wf.get("on", wf.get(True))
    assert set(on) == {"workflow_dispatch"} and wf["permissions"] == {"contents": "read"}
    for st in wf["jobs"]["probe"]["steps"]:
        env = st.get("env") or {}
        if st.get("name") == "Run":
            assert st["run"].startswith("python -m admob_iq.fetch.ga4_funnel_probe 2>/tmp/") and env["FUNNEL_DATA_DIR"] == "_private"
        else:
            assert not any(k.startswith("GA4_") for k in env)
