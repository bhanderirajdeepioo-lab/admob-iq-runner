"""GA4 first-open funnel one-off probe (admob_iq.fetch.ga4_firstopen_probe + .github/workflows/ga4-firstopen-probe.yml) —
offline, made-up apps / screens / numbers only: what it asks GA4 (first sessions only, the full history), which screens and
events it follows (named like a first-open step, never caller-ID or ad screens, + the top ones), the day-by-day series it
keeps, resume, and a PUBLIC log that stays counts-only."""
import json
import os
import time
from datetime import date

import yaml

from admob_iq.fetch import ga4_firstopen_probe as fp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG, PKG_B = "com.example.alpha", "com.example.beta"


def test_picks_first_open_steps_generically():
    disc = [["MainActivity", 900], ["SplashActivity", 1000], ["CallerCadHomeDialogActivity", 400], ["AdActivity", 300],
            ["LanguageActivity", 800], ["PermissionActivity", 500], ["ViewerActivity", 700], ["(not set)", 5],
            ["GatewaySplashActivity", 50], ["SettingsActivity", 20]]
    got = fp.pick_classes(disc)
    assert got[:5] == ["MainActivity", "SplashActivity", "LanguageActivity", "PermissionActivity", "GatewaySplashActivity"]
    assert "ViewerActivity" in got and "SettingsActivity" not in got    # the top classes kept whatever their names, not all
    assert not {"CallerCadHomeDialogActivity", "AdActivity", "(not set)"} & set(got)
    ev = fp.pick_events([["screen_view", 9], ["first_open", 8], ["app_splash_created", 7], ["ad_impression", 6],
                         ["app_language_created", 5], ["app_home_created", 4], ["session_start", 3]])
    assert ev == ["first_open", "app_splash_created", "app_language_created", "app_home_created"]


class FakeApp:
    """Answers the probe's five kinds of report from made-up rows and records what was asked."""
    asked = []

    def __init__(self, token, pid, sid, run, prop=None):
        self.kind, self.calls, self.tok, self.by_kind, self.thresholded = "other", 0, 0, {}, False

    def report_all(self, body, event=None, events=None, extra=None):
        self.calls += 1
        self.tok += 10
        FakeApp.asked.append((self.kind, body, event, events, extra))
        dims = [d["name"] for d in body["dimensions"]]
        if self.kind == "disc_screens":
            return [{"unifiedScreenClass": c, "activeUsers": n} for c, n in
                    [("SplashActivity", 100), ("LanguageActivity", 90), ("MainActivity", 80), ("CallerCadHomeActivity", 60)]]
        if self.kind == "disc_events":
            return [{"eventName": e, "activeUsers": n} for e, n in [("first_open", 100), ("app_home_created", 70)]]
        if dims == ["date"]:
            return [{"date": "20261001", "newUsers": 100, "activeUsers": 900}, {"date": "20261002", "newUsers": 120}]
        key = dims[1]
        vals = ["SplashActivity", "MainActivity"] if key == "unifiedScreenClass" else ["first_open", "app_home_created"]
        return [{"date": "20261001", key: vals[0], "activeUsers": 99}, {"date": "20261001", key: vals[1], "activeUsers": 77}]


def _unit(pkg):
    return {"package": pkg, "property_id": "111", "stream_id": "222", "tz": "Asia/Kolkata", "owner": "o", "app_ids": ["a~1"]}


def test_probe_unit_asks_first_sessions_over_the_full_history(monkeypatch):
    FakeApp.asked = []
    monkeypatch.setattr(fp.pr, "App", FakeApp)
    monkeypatch.setattr(fp.ap, "pick_store", lambda u, d: ("a~1", {"history_start": "2024-03-05"}))
    run = fp.Run(budget=60)
    r = fp.probe_unit(run, _unit(PKG), "tok", "/x", fp.pr.new_prop())
    assert r["complete"] and r["history_start"] == "2024-03-05" and r["calls"] == 5
    assert r["classes"] == ["SplashActivity", "LanguageActivity", "MainActivity"] and r["events"] == ["first_open", "app_home_created"]
    assert r["new_users"] == {"2026-10-01": 100, "2026-10-02": 120}
    assert r["screens"] == {"SplashActivity": {"2026-10-01": 99}, "MainActivity": {"2026-10-01": 77}}
    assert r["events_daily"] == {"first_open": {"2026-10-01": 99}, "app_home_created": {"2026-10-01": 77}}
    kinds = {k: (b, ev, evs, ex) for k, b, ev, evs, ex in FakeApp.asked}
    new_only = {"filter": {"fieldName": "newVsReturning", "stringFilter": {"matchType": "EXACT", "value": "new"}}}
    for k in ("disc_screens", "disc_events", "hist_screens", "hist_events"):
        assert new_only in kinds[k][3], k                              # first sessions only
    for k in ("hist_new", "hist_screens", "hist_events"):
        assert kinds[k][0]["dateRanges"][0]["startDate"] == "2024-03-05"   # the FULL history, not a recent window
    assert kinds["hist_screens"][1] == "screen_view" and kinds["hist_events"][2] == ["first_open", "app_home_created"]
    assert {"filter": {"fieldName": "unifiedScreenClass", "inListFilter": {"values": r["classes"]}}} in kinds["hist_screens"][3]


def test_main_writes_privately_resumes_and_prints_counts_only(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(fp.pr, "App", FakeApp)
    monkeypatch.setattr(fp.ap, "pick_store", lambda u, d: ("a~1", {"history_start": "2025-01-01"}))
    monkeypatch.setattr(fp.vr, "units_from_state", lambda st: [_unit(PKG), _unit(PKG_B)])
    monkeypatch.setattr(fp.gu, "load_state", lambda d: {})
    monkeypatch.setattr(fp.ga4, "access_token", lambda c, s, r: "tok")
    monkeypatch.setattr(fp.ga4_probe, "owner_tokens", lambda env: ([("o", "rt")], None))   # pairs, as the real one
    put = {}
    monkeypatch.setattr(fp.pr, "write_private", lambda path, text, msg: bool(put.update({path: text})) or True)
    env = {"GA4_CLIENT_ID": "c", "GA4_CLIENT_SECRET": "s", "FIRSTOPEN_DATA_DIR": str(tmp_path)}
    fp.main(env)
    rep = json.loads(put[fp.OUT_PATH])
    assert set(rep["apps"]) == {PKG, PKG_B} and rep["counts"]["complete"] == 2 and rep["counts"]["calls"] == 10
    out = capsys.readouterr().out
    assert "com.example" not in out and "Activity" not in out and "2025-01-01" not in out   # counts only
    assert out.strip().splitlines()[-1] == "firstopen probe: report written"
    os.makedirs(tmp_path / "ga4", exist_ok=True)
    (tmp_path / fp.OUT_PATH).write_text(put[fp.OUT_PATH], encoding="utf-8")
    put.clear()
    fp.main(dict(env, FIRSTOPEN_RESUME="true"))
    assert "0 app(s) to probe, 2 carried over" in capsys.readouterr().out and json.loads(put[fp.OUT_PATH])["counts"]["complete"] == 2


def test_the_workflow_keeps_secrets_and_details_off_the_public_log():
    with open(os.path.join(ROOT, ".github", "workflows", "ga4-firstopen-probe.yml"), encoding="utf-8") as fh:
        text = fh.read()
    wf = yaml.safe_load(text)
    on = wf.get("on", wf.get(True))
    assert set(on) == {"workflow_dispatch"} and set(on["workflow_dispatch"]["inputs"]) == {"max_apps", "resume"}
    assert wf["permissions"] == {"contents": "read"}
    job = wf["jobs"]["probe"]
    assert job["timeout-minutes"] == 30 and fp.BUDGET_SEC < 25 * 60
    for st in job["steps"]:
        env = st.get("env") or {}
        if st.get("name") == "Run":
            assert st["run"].startswith("python -m admob_iq.fetch.ga4_firstopen_probe 2>/tmp/")
            assert env["FIRSTOPEN_DATA_DIR"] == "_private"
        else:
            assert not any(k.startswith("GA4_") for k in env), st.get("name")
        if "clone" in (st.get("run") or ""):
            assert "> /dev/null 2>&1" in st["run"] and "http.extraheader" in st["run"] and "::add-mask::" in st["run"]
