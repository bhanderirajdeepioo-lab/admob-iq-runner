"""GA4 Uninstall tab — the build step (admob_iq.uninstall_build + its build_static wiring): nothing changes
without GA4, the summary / lazy asset / cohort files follow the §5 contract, alerts carry the dashboard's
display names and go out through send_alerts ONCE (warning + good → Telegram, watch → email), a GA4
failure never costs the AdMob build, the public log is one counts line, re-runs rewrite nothing, and the
committed frontend fixture is exactly what the build code writes."""

import copy
import gzip
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone

import pytest
import yaml

from admob_iq import build_static
from admob_iq import uninstall_build as ub
from admob_iq.config import settings
from admob_iq.fetch import ga4_uninstall as gu
from tests import test_ga4
from admob_iq.engine import impact as imp
from tests.uninstall_synth import (END, check_asset, check_cohort_file, check_impact, check_summary, make_impact_store,
                                   make_store, rollout)

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=timezone.utc)
ASSET = "uninstall.json.gz"
PID, SID, EMAIL = "987654321", "5550001234", "owner.a@secret-ws.test"
A1, A2, A3, A4, A6, A9 = ("ca-app-pub-7777777777777777~%d" % i for i in (1, 2, 3, 4, 6, 9))
N1, N2, N3, N4, N6 = "Demo Caller – Test App", "Beta Down App", "Gamma No Package", "Delta No Stream", "Epsilon Watch"
PKG = {A1: "com.hidden.one", A2: "com.hidden.two", A4: "com.hidden.four", A6: "com.hidden.six"}
SECRETS = test_ga4.SECRETS + [PID, SID, EMAIL, "rt-SECRET-x", A1, A2, A3, A4, A6, N1, N2, N3, N4, N6] + list(PKG.values())
LOG_LINE = re.compile(r"^ga4 uninstall: apps \d+, with GA4 \d+, fetched \d+ \(full \d+, repair \d+\), fresh \d+, "
                      r"failed \d+, deferred \d+, open alerts \d+ \(new \d+\), impact updates \d+ \(halt \d+, "
                      r"hold \d+, win \d+, early \d+\), impact alerts \d+ \(new \d+\)$")


def _bump(delta):
    # a rise shows on the newest installs (provisional days: late data only adds — real); a fall only once
    # its days are settled, so the "good" app's change started a week earlier
    since = END - timedelta(days=7 if delta > 0 else 14)
    return lambda c: {1: delta, 2: -delta} if c >= since else None


def seed(data_dir, first_eval=False):
    """Stores as the fetch left them + a state with one earlier evaluation (so big-app alerts are due)."""
    os.makedirs(os.path.join(data_dir, "ga4_uninstall"), exist_ok=True)
    with open(os.path.join(data_dir, "app_store_ids.json"), "w", encoding="utf-8") as f:
        json.dump({"by_id": PKG}, f)
    for aid, delta in ((A1, 70), (A2, -70), (A6, 30)):
        st = make_store(42, 1000, bump=_bump(delta), app_id=aid, package=PKG[aid])
        st.update(property_id=PID, stream_id=SID)
        gu.save_store(gu.store_path(data_dir, aid), st)
    state = gu._state_default()
    state["routes"].update(fetched_at="2026-09-21T01:00:00Z", by_package={
        p: {"property_id": PID, "stream_id": SID, "owner": EMAIL} for a, p in PKG.items() if a != A4})
    state["tz"] = {PID: "Asia/Kolkata"}
    if not first_eval:
        state["eval"] = {a: {"end": (END - timedelta(days=1)).isoformat(), "stage": "badh_raha", "stable_hold": 0,
                             "streak": {"cohort|up": 1, "cohort|down": 1}} for a in (A1, A2, A6)}
    gu.save_state(data_dir, state)


def dashboard():
    cat = [{"app_id": a, "app_name": n, "account_id": "pub-7", "selected": True}
           for a, n in ((A1, N1), (A2, N2), (A3, N3), (A4, N4), (A6, N6))]
    cat.append({"app_id": A9, "app_name": "Hidden", "account_id": "pub-7", "selected": False})
    return {"apps_catalog": cat, "kpis": {"revenue": 12.5}, "alerts": {"items": []}, "placements": [1, 2]}


def ga4_settings(**kw):
    s = dict(settings(), ga4_enabled=True, ga4_client_id="cid", ga4_client_secret="sec",
             ga4_refresh_tokens=json.dumps({EMAIL: "rt-SECRET-x"}), ga4_refresh_token="", notify_dry_run=True)
    s.update(kw)
    return s


STATUS = {"counts": {"selected": 5, "with_ga4": 3, "fetched": 0, "full": 0, "fresh": 3, "failed": 0, "deferred": 0,
                     "no_ga4": 2},
          "apps": {A1: "fresh", A2: "fresh", A6: "fresh"}, "no_ga4": {A3: "no_package", A4: "no_stream"},
          "discovery": None}


@pytest.fixture
def site(tmp_path, monkeypatch):
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    seed(data)
    calls = []
    monkeypatch.setattr(gu, "refresh_all", lambda *a, **k: calls.append(a) or copy.deepcopy(STATUS))
    return data, out, calls


def run(data, out, s=None, now=NOW):
    dash = dashboard()
    files = ub.run_uninstall(dash, data, out, s or ga4_settings(), now=now)
    return dash, files


def _gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


# ── off: nothing changes ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("off", [dict(ga4_refresh_tokens="", ga4_refresh_token=""), dict(ga4_enabled=False),
                                 dict(ga4_client_id=None)])
def test_without_ga4_nothing_changes(tmp_path, monkeypatch, off):
    monkeypatch.setattr(gu, "refresh_all", lambda *a, **k: pytest.fail("GA4 must not be called"))
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    os.makedirs(data)
    dash = dashboard()
    before = copy.deepcopy(dash)
    assert ub.run_uninstall(dash, data, out, ga4_settings(**off), now=NOW) is None
    assert dash == before
    assert not os.path.exists(os.path.join(data, "ga4_uninstall")) and not os.path.exists(os.path.join(out, ASSET))


# ── the contract ─────────────────────────────────────────────────────────────────────────────────

def test_summary_asset_and_cohort_files_follow_the_contract(site):
    data, out, calls = site
    os.makedirs(out)
    with open(os.path.join(out, "uninstall_c_deadbeef0000.json.gz"), "wb") as f:
        f.write(b"stale")                                          # an app no longer shown
    dash, files = run(data, out)
    assert len(calls) == 1
    summary = dash["uninstall"]
    asset = _gz(os.path.join(out, ASSET))
    check_summary(summary)
    check_asset(asset, summary)
    keys = {d["app_id"]: d["key"] for d in asset["apps"]}
    assert files == [ASSET] + ["uninstall_c_%s.json.gz" % keys[a] for a in (A2, A1, A6)]   # by app name
    for d in asset["apps"]:
        check_cohort_file(_gz(os.path.join(out, "uninstall_c_%s.json.gz" % d["key"])), d)
    assert not os.path.exists(os.path.join(out, "uninstall_c_deadbeef0000.json.gz"))
    assert [r["app"] for r in summary["apps"]] == [N2, N1, N6]                             # case-insensitive name order
    assert summary["status"] == "ok" and summary["counts"] == {"selected": 5, "with_ga4": 3, "ready": 3, "no_ga4": 2,
                                                               "failed": 0, "deferred": 0, "stale": 0}
    assert summary["data_till_min"] == summary["data_till_max"] == END.isoformat()
    assert [(n["app"], n["reason"], n["package"]) for n in asset["no_ga4"]] == [
        (N4, "no_stream", PKG[A4]), (N3, "no_package", None)]
    assert all(n["text"] for n in asset["no_ga4"])
    by = {a["app_id"]: a for a in summary["alerts"]}
    assert by[A1]["message"] == (N1 + ": D1 uninstall 72% → 79% (+7 point) — 12–18 Sep ke installs, pichhle 4 hafte se "
                                 "zyada · abhi ka data kaccha — number aur badh sakta hai") and by[A1]["provisional"]
    assert by[A2]["installs_to"] == (END - timedelta(days=8)).isoformat() and not by[A2]["provisional"]   # settled
    assert (by[A1]["severity"], by[A2]["severity"], by[A6]["severity"]) == ("warning", "good", "watch")
    assert by[A2]["app"] == N2 and by[A2]["message"].startswith(N2 + ": D1 uninstall 72% → 65% (−7 point)")
    assert [a["severity"] for a in summary["alerts"]] == ["warning", "watch", "good"]
    assert all(a["notify"] and a["fresh"] for a in summary["alerts"])
    assert summary["alert_counts"] == {"warning": 1, "watch": 1, "good": 1}
    assert summary["asset_v"] == hashlib.sha1(json.dumps(
        asset, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()[:12]


def test_a_renamed_app_shows_its_new_name_in_the_same_alert(site):
    data, out, _ = site
    dash, _ = run(data, out)
    old_id = [a["id"] for a in dash["uninstall"]["alerts"] if a["app_id"] == A1][0]
    d2 = dashboard()
    d2["apps_catalog"][0]["app_name"] = "Renamed Caller"
    ub.run_uninstall(d2, data, out, ga4_settings(), now=NOW + timedelta(hours=1))
    a = [a for a in d2["uninstall"]["alerts"] if a["app_id"] == A1][0]
    assert a["id"] == old_id and a["message"].startswith("Renamed Caller: D1 uninstall")


# ── notifications ────────────────────────────────────────────────────────────────────────────────

def test_alerts_go_out_once_warning_and_good_on_telegram_watch_by_email(site):
    data, out, _ = site
    dash, _ = run(data, out)
    res = build_static.send_alerts(dash, ga4_settings())
    tele = next(r["text"] for r in res if r["channel"] == "telegram")
    mail = next(r["body"] for r in res if r["channel"] == "email")
    assert "🟠 [WARNING] " + N1 + ": D1 uninstall 72% → 79%" in tele and tele.count("uninstall (GA4)") == 2
    assert "🎉 [GOOD] " + N2 + ": D1 uninstall" in tele and N6 not in tele
    assert "🟡 [WATCH] " + N6 + ": D1 uninstall 72.0% → 75.0% (+3 point)" in mail and mail.count("uninstall (GA4)") == 3
    assert all(r.get("dry_run") for r in res)
    assert ub.mark_notified(data, dash["uninstall"], dry=True, now=NOW) == 3
    eps = gu.load_state(data)["episodes"].values()
    assert all(e["notified_at"] == "2026-09-21T06:00:00Z" and e["notified_dry"] for e in eps)
    for h in (1, 2, 5):                                             # the hourly runs after it: shown, never re-sent
        dash, _ = run(data, out, now=NOW + timedelta(hours=h))
        assert len(dash["uninstall"]["alerts"]) == 3 and not any(a["notify"] for a in dash["uninstall"]["alerts"])
        assert build_static.send_alerts(dash, ga4_settings()) == []
    assert ub.mark_notified(data, dash["uninstall"], dry=True) == 0


def _live(**kw):
    return ga4_settings(**dict(dict(notify_dry_run=False, telegram_token="bot-SECRET", telegram_chat="42",
                                    smtp={"host": "smtp.test", "port": 587, "user": "u", "pass": "p", "to": "t"}), **kw))


def test_a_failed_send_keeps_the_alert_due_until_its_channel_takes_it(site, monkeypatch):
    data, out, _ = site
    got = {"tg": 400, "mail": "sent", "tg_texts": []}

    def tg(text, token, chat, dry):
        got["tg_texts"].append(text)
        return {"channel": "telegram", "status": got["tg"]}
    monkeypatch.setattr(build_static.notifier, "send_telegram", tg)
    monkeypatch.setattr(build_static.notifier, "send_email", lambda subj, body, cfg, dry: {"channel": "email",
                                                                                              "status": got["mail"]})

    def due(h):
        dash, _ = run(data, out, now=NOW + timedelta(hours=h))
        return dash, sorted((a["app"], a["severity"]) for a in dash["uninstall"]["alerts"] if a["notify"])

    dash, _ = run(data, out)
    build_static._uninstall_mark_sent(dash, data, _live(), build_static.send_alerts(dash, _live()))
    dash, left = due(1)                          # Telegram said 400 (too long / rate-limited): not sent
    assert left == [(N2, "good"), (N1, "warning")]                  # … the watch went out in the email digest
    got["tg"] = 429
    build_static._uninstall_mark_sent(dash, data, _live(), build_static.send_alerts(dash, _live()))
    dash, left = due(2)
    assert left == [(N2, "good"), (N1, "warning")]
    got["tg"] = 200
    build_static._uninstall_mark_sent(dash, data, _live(), build_static.send_alerts(dash, _live()))
    dash, left = due(3)
    assert left == [] and build_static.send_alerts(dash, _live()) == []
    assert all(t.count("uninstall (GA4)") == 2 for t in got["tg_texts"])        # the same two, each time


def test_without_a_telegram_bot_the_email_is_the_urgent_ones_channel_and_no_smtp_means_not_sent(site, monkeypatch):
    data, out, _ = site
    monkeypatch.setattr(build_static.notifier, "send_email", lambda subj, body, cfg, dry: {"channel": "email",
                                                                                              "status": "sent"})
    dash, _ = run(data, out)
    s = _live(telegram_token="")
    build_static._uninstall_mark_sent(dash, data, s, build_static.send_alerts(dash, s))
    dash, _ = run(data, out, now=NOW + timedelta(hours=1))
    assert not any(a["notify"] for a in dash["uninstall"]["alerts"])
    seed(data)                                                                   # start over: nothing sent yet
    s = _live(smtp={"host": ""})
    monkeypatch.setattr(build_static.notifier, "send_email", lambda subj, body, cfg, dry: {  # no SMTP host yet:
        "channel": "email", "dry_run": True, "subject": subj, "body": body})              # the real one's answer
    monkeypatch.setattr(build_static.notifier, "send_telegram", lambda text, token, chat, dry: {
        "channel": "telegram", "status": 200})
    dash, _ = run(data, out, now=NOW + timedelta(hours=2))
    build_static._uninstall_mark_sent(dash, data, s, build_static.send_alerts(dash, s))
    dash, _ = run(data, out, now=NOW + timedelta(hours=3))
    assert [(a["app"], a["severity"]) for a in dash["uninstall"]["alerts"] if a["notify"]] == [(N6, "watch")]


def test_a_long_telegram_list_goes_in_parts_with_the_uninstall_lines_in_their_own(site):
    data, out, _ = site
    dash, _ = run(data, out)
    dash["alerts"]["items"] = [{"severity": "warning", "place": "Placement %03d " % i + "x" * 120,
                                "message": "eCPM gira"} for i in range(80)]
    res = build_static.send_alerts(dash, ga4_settings())
    tele = [r for r in res if r["channel"] == "telegram"]
    assert len(tele) >= 4 and all(len(r["text"]) <= 4096 for r in tele)
    assert sum(r["text"].count("Placement ") for r in tele) == 80                  # nothing dropped
    uni = [r for r in tele if r.get("uninstall_ids")]
    assert len(uni) == 1 and uni[0]["text"].count("uninstall (GA4)") == 2 and "Placement" not in uni[0]["text"]
    assert build_static.uninstall_delivered(res, ga4_settings()) == {
        a["id"] for a in dash["uninstall"]["alerts"] if a["notify"]}


def test_two_selected_apps_with_one_play_package_are_fetched_and_alerted_once(site):
    data, out, calls = site
    A7, N7 = "ca-app-pub-7777777777777777~7", "Caller Copy"
    with open(os.path.join(data, "app_store_ids.json"), "w", encoding="utf-8") as f:
        json.dump({"by_id": dict(PKG, **{A7: PKG[A1]})}, f)
    st = make_store(42, 1000, bump=_bump(70), app_id=A7, package=PKG[A1])       # a store it once had: ignored
    gu.save_store(gu.store_path(data, A7), st)
    dash = dashboard()
    dash["apps_catalog"].append({"app_id": A7, "app_name": N7, "account_id": "pub-7", "selected": True})
    ub.run_uninstall(dash, data, out, ga4_settings(), now=NOW)
    apps = {a["app_id"]: a for a in calls[-1][2]}
    assert apps[A1]["package"] == PKG[A1] and apps[A7]["package"] is None       # one GA4 fetch for the package
    assert {a["app"] for a in dash["uninstall"]["alerts"]} == {N1, N2, N6}
    asset = _gz(os.path.join(out, ASSET))
    check_asset(asset, dash["uninstall"])
    n7 = [n for n in asset["no_ga4"] if n["app_id"] == A7][0]
    assert n7["reason"] == "same_package" and N1 in n7["text"] and A7 not in [a["app_id"] for a in asset["apps"]]


def test_the_first_ever_evaluation_is_shown_but_not_sent(tmp_path, monkeypatch):
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    seed(data, first_eval=True)
    monkeypatch.setattr(gu, "refresh_all", lambda *a, **k: copy.deepcopy(STATUS))
    dash, _ = run(data, out)
    assert len(dash["uninstall"]["alerts"]) == 3 and not any(a["notify"] for a in dash["uninstall"]["alerts"])
    assert build_static.send_alerts(dash, ga4_settings()) == []


def test_build_marks_sent_alerts_after_send_alerts(site):
    data, out, _ = site
    dash, _ = run(data, out)
    build_static._uninstall_mark_sent(dash, data, ga4_settings())
    assert all(e["notified_at"] for e in gu.load_state(data)["episodes"].values())
    build_static._uninstall_mark_sent({"kpis": {}}, data, ga4_settings())          # no uninstall key: a no-op


# ── failures never cost the AdMob build ──────────────────────────────────────────────────────────

def test_a_failing_ga4_refresh_still_builds_from_the_stores(site, monkeypatch):
    data, out, _ = site

    def boom(*a, **k):
        raise RuntimeError("HTTP 403: " + PID)
    monkeypatch.setattr(gu, "refresh_all", boom)
    dash, files = run(data, out)
    assert len(dash["uninstall"]["apps"]) == 3 and len(files) == 4
    check_summary(dash["uninstall"])


def test_a_crash_in_the_uninstall_step_leaves_the_admob_dashboard_alone(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("HTTP 403: PERMISSION_DENIED on property " + PID + " for " + EMAIL)
    monkeypatch.setattr(ub, "run_uninstall", boom)
    dash = dashboard()
    before = copy.deepcopy(dash)
    dash["uninstall"] = {"half": "written"}
    assert build_static._uninstall_step(dash, str(tmp_path), str(tmp_path / "site"), ga4_settings()) == []
    assert dash == before
    monkeypatch.setattr(ub, "mark_notified", boom)
    build_static._uninstall_mark_sent({"uninstall": {"alerts": []}}, str(tmp_path), ga4_settings())
    err = capsys.readouterr()
    assert err.out == "" and err.err == ("ga4 uninstall skipped: RuntimeError\n"
                                         "ga4 uninstall notify-mark skipped: RuntimeError\n")


def test_run_uninstall_and_its_wrapper_return_the_files_for_headers(site):
    data, out, _ = site
    dash = dashboard()
    files = build_static._uninstall_step(dash, data, out, ga4_settings())
    assert files[0] == ASSET and len(files) == 4 and "uninstall" in dash


# ── privacy + determinism ────────────────────────────────────────────────────────────────────────

def test_public_log_is_one_counts_line_and_site_files_hold_no_ids(site, capsys):
    data, out, _ = site
    dash, _ = run(data, out)
    got = capsys.readouterr()
    assert got.out == ""
    lines = got.err.splitlines()
    assert len(lines) == 1 and LOG_LINE.match(lines[0]), lines
    assert lines[0] == ("ga4 uninstall: apps 5, with GA4 3, fetched 0 (full 0, repair 0), fresh 3, failed 0, "
                        "deferred 0, open alerts 3 (new 3), impact updates 0 (halt 0, hold 0, win 0, early 0), "
                        "impact alerts 0 (new 0)")
    for s in SECRETS:
        assert s not in got.err
    shipped = json.dumps(dash["uninstall"], ensure_ascii=False)
    for name in os.listdir(out):
        shipped += gzip.open(os.path.join(out, name), "rt", encoding="utf-8").read()
    for s in (PID, SID, EMAIL, "secret-ws", "rt-SECRET", "tok-SECRET"):
        assert s not in shipped


def test_re_runs_leave_every_file_byte_identical(site):
    data, out, _ = site
    dash, _ = run(data, out)
    ub.mark_notified(data, dash["uninstall"], dry=True, now=NOW)
    run(data, out, now=NOW + timedelta(hours=1))

    def snap():
        files = {}
        for root in (out, os.path.join(data, "ga4_uninstall")):
            for n in sorted(os.listdir(root)):
                p = os.path.join(root, n)
                files[p] = (open(p, "rb").read(), os.stat(p).st_mtime_ns)
        return files
    a = snap()
    dash, _ = run(data, out, now=NOW + timedelta(hours=2))
    assert snap() == a                                              # nothing rewritten: same bytes, same mtime
    assert build_static.send_alerts(dash, ga4_settings()) == []


def test_refresh_yml_hands_ga4_secrets_to_the_build_step_only():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wf = yaml.safe_load(open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8"))
    for step in wf["jobs"]["refresh"]["steps"]:
        env = step.get("env") or {}
        ga4 = {k: v for k, v in env.items() if k.startswith("GA4_")}
        if step.get("name") == "Build dashboard + send alerts":
            assert {k: ga4[k] for k in ("GA4_CLIENT_ID", "GA4_CLIENT_SECRET", "GA4_REFRESH_TOKENS", "GA4_REFRESH_TOKEN")} \
                == {k: "${{ secrets.%s }}" % k for k in ("GA4_CLIENT_ID", "GA4_CLIENT_SECRET", "GA4_REFRESH_TOKENS",
                                                          "GA4_REFRESH_TOKEN")}
            assert ga4["GA4_ENABLED"] == "${{ vars.GA4_ENABLED || 'true' }}"
            assert "> /tmp/build.log" in step["run"]                # the build's output never reaches the log
        else:
            assert not ga4, step.get("name")
            assert "secrets.GA4_" not in json.dumps(step)


# ── the frontend fixture ─────────────────────────────────────────────────────────────────────────

def test_the_committed_frontend_fixture_is_what_the_build_writes(tmp_path):
    from tests.make_uninstall_fixture import OUT, build_fixture, fixture_json
    fx = build_fixture(str(tmp_path))
    s, asset = fx["dashboard_uninstall"], fx["asset"]
    check_summary(s)
    check_asset(asset, s)
    for d in asset["apps"]:
        check_cohort_file(fx["cohort_files"]["uninstall_c_%s.json.gz" % d["key"]], d)
    fam = {(a["app"], a["family"], a["severity"], a["notify"], a["provisional"]) for a in s["alerts"]}
    assert ("Demo Launcher", "rate_spike", "warning", True, True) in fam                # today's day: "kaccha"
    assert ("Demo Caller – Test App", "cohort", "watch", False, True) in fam            # one alert while it lasts
    assert ("Demo Weather", "rate_drift", "warning", False, True) in fam
    assert ("Demo Wallpapers", "rate_zero", "watch", False, False) in fam               # a zero day once SETTLED
    assert ("Demo Flashlight", "cohort", "good", False, False) in fam                   # good news: settled only
    assert {("Demo Caller – Test App", "impact", "warning", False, False),              # 🛑 HALT (sent 21 Sep)
            ("Demo Wallpapers", "impact", "watch", False, False),                       # ⚠️ HOLD (seeded)
            ("Demo Flashlight", "impact", "good", False, False)} < fam and len(fam) == 8  # ✅ WIN (seeded)
    assert sum(1 for x in fx["sent"] if x["telegram"] or x["email"]) == 3               # sent once each, no flood
    assert {n["reason"] for n in asset["no_ga4"]} == {"no_package", "no_stream", "fetch_failed", "not_fetched_yet",
                                                      "same_package"}
    wall = [a for a in asset["apps"] if a["app"] == "Demo Wallpapers"][0]
    assert wall["daily"]["breaks"] == ["2026-09-14"] and any(t["break_day"] == "2026-09-14" for t in wall["table"])
    # Firebase-like late app_remove: the re-reads measure it (80% there at 2 days old, 99% at 7)
    late = asset["lateness"]
    assert [round(x, 2) for x in late["un"][:6]] == [0.8, 0.88, 0.93, 0.96, 0.98, 0.99] and late["new"][0] == 1.0
    assert late["ages"][0] == 2 and late["final_age"] == 15 and late["un"][6:] == [1.0] * 8
    assert all(a["settled_till"] == "2026-09-16" and a["lateness"] for a in asset["apps"])
    lau = [a for a in asset["apps"] if a["app"] == "Demo Launcher"][0]               # a day GA4 never returns in full:
    assert list(lau["flags"]["incomplete_days"]) == ["2026-09-03"]                  # flagged, shown, no alert from it
    assert any(t["inc_day"] == "2026-09-03" for t in lau["table"])
    assert all(not a["flags"]["incomplete_days"] for a in asset["apps"] if a["app"] != "Demo Launcher")
    # … and one GA4 only ever returns ~90% of: filled up to its exact total (an estimate, "≈"), used everywhere
    est = lau["flags"]["estimated_days"]
    assert list(est) == ["2026-08-20"] and 0.85 < est["2026-08-20"] < 0.97 and lau["flags"]["cell_days"]["estimated"] == 1
    assert all(not a["flags"]["estimated_days"] for a in asset["apps"] if a is not lau)
    cf = fx["cohort_files"]["uninstall_c_%s.json.gz" % lau["key"]]            # the "Every day" cells: the filled ones
    i20 = (date(2026, 8, 20) - date.fromisoformat(cf["start"])).days
    on20 = sum(u for i, lags in enumerate(cf["lags"]) for lag, u in lags if i + lag == i20) + cf["unplaced"].get("2026-08-20", 0)
    assert on20 == lau["daily"]["un"][i20]
    # the still-incomplete 3 Sep never empties a row that has older installs: they take those, and say so
    assert all(t["recent"]["p"] is not None for t in lau["table"])
    assert any(t["fallback"] and t["fallback"]["recent"] and t["fallback"]["days"] == ["2026-09-03"] for t in lau["table"])
    # GA4 keeps the Caller's install-day USERS 150 days only: its older days come from the events (used, shown)
    cal = [a for a in asset["apps"] if a["app"] == "Demo Caller – Test App"][0]
    assert cal["flags"]["cell_days"] == {"users": 155, "events": 85, "estimated": 0, "incomplete": 0}
    assert cal["flags"]["events_span"] == [cal["history_start"], "2026-04-21"]
    assert all(a["flags"]["cell_days"]["events"] == 0 for a in asset["apps"] if a is not cal)
    assert {a["stage"] for a in asset["apps"]} == {"naya", "badh_raha", "stable"}
    # "100 me se kitne bache": every app has its curve (check_asset: never rises, ≤100%, bars add up); the verdict
    # compares settled installs only — Flashlight kept more than the month before, the rest stayed alike
    sv = {a["app"]: a["survival"] for a in asset["apps"]}
    flash = sv["Demo Flashlight"]["verdict"]
    assert flash["fires"] and flash["dir"] == "better" and flash["n"] == 7
    assert all(not v["verdict"]["fires"] for k, v in sv.items() if k not in ("Demo Flashlight", "Demo Notes"))
    assert sv["Demo Notes"]["verdict"] is None and sv["Demo Notes"]["recent"] is None     # 20 days old
    assert sv["Demo Caller – Test App"]["key_days"] == [1, 7, 30, 90] and sv["Demo Caller – Test App"]["recent"]
    # ~10 months of a few TEST installs before the Wallpapers' launch: found, left out of every install-day number, kept
    wal = [a for a in asset["apps"] if a["app"] == "Demo Wallpapers"][0]
    assert wal["launch"]["day"] == "2026-06-16" and wal["launch"]["hidden"] and wal["launch"]["pre_installs"] > 100
    assert wal["history_start"] == "2025-08-20" and wal["survival"]["all"]["from"] == "2026-06-16"
    assert wal["survival"]["with_test"]["from"] == "2025-08-20" and any(r["pre"] for r in wal["triangle"]["rows"])
    assert all(not a["launch"]["hidden"] for a in asset["apps"] if a is not wal)
    # the Caller's installs of March moved its D180: old installs — info ("Purane badlaav"), never an alert
    assert [(o["checkpoint"], o["installs_from"], o["installs_to"]) for o in cal["old_changes"]] == [
        ("D180", "2026-03-14", "2026-03-20")]
    assert all(not a["old_changes"] for a in asset["apps"] if a is not cal)
    assert all(al["installs_to"] >= "2026-07-25" for al in s["alerts"] if al["family"] == "cohort")
    # app updates reach each app's detail — the install-week table draws a 📦 line above the week each fell in: the
    # Caller's 3.2, the Weather's 4.1 in the middle of its table, the Launcher's app_update jump (no new version)
    assert {a["app"]: a["releases"] for a in asset["apps"] if a["releases"]} == {
        "Demo Caller – Test App": [{"date": "2026-09-10", "version": "3.2", "kind": "version"}],
        "Demo Flashlight": [{"date": "2026-09-01", "version": "1.2", "kind": "version"},
                            {"date": "2026-09-19", "version": "1.3", "kind": "version"}],
        "Demo Wallpapers": [{"date": "2026-09-01", "version": "2.0", "kind": "version"}],
        "Demo Weather": [{"date": "2026-07-15", "version": "4.1", "kind": "version"}],
        "Demo Launcher": [{"date": "2026-08-05", "version": None, "kind": "update"}]}
    for a in asset["apps"]:
        for rel in a["releases"]:
            rows = [r for r in a["triangle"]["rows"] if r["from"] <= rel["date"] <= r["to"]]
            assert len(rows) == 1 and not rows[0]["pre"]
    wea = [a for a in asset["apps"] if a["app"] == "Demo Weather"][0]
    k = next(i for i, r in enumerate(wea["triangle"]["rows"]) if r["to"] == "2026-07-19")
    assert wea["triangle"]["rows"][k]["from"] == "2026-07-13" and 5 < k < len(wea["triangle"]["rows"]) - 5
    assert wea["zoom"]["reason"] == "alert"                        # an update 10 weeks old: no day-by-day zoom from it
    # the "📦 Update impact" card: every update, the owner's four must-haves before vs after, a verdict
    imp = {(a["app"], b["label"]): b for a in asset["apps"] for b in a["impact"]["updates"]}
    assert {k: (b["verdict"]["level"], b["verdict"]["final"]) for k, b in imp.items()} == {
        ("Demo Caller – Test App", "v3.2"): ("halt", False), ("Demo Flashlight", "v1.3"): (None, False),
        ("Demo Flashlight", "v1.2"): ("win", True), ("Demo Wallpapers", "v2.0"): ("hold", True),
        ("Demo Weather", "v4.1"): ("continue", True), ("Demo Launcher", "App update"): ("continue", True)}
    b = imp[("Demo Caller – Test App", "v3.2")]                  # old users on 3.2: less DAU, less time — early
    assert b["verdict"]["worse"] == ["returning_dau", "time"] and b["rows"]["new_d7"]["status"] == "pending"
    assert b["rows"]["returning_dau"]["change"] < -0.06 and b["rows"]["time"]["change"] < -0.1
    assert b["adoption"]["slow"] and "slow_rollout" in b["notes"] and b["versions_cmp"]["rows"]["ver_time"]["status"] == "unsure"
    halt = [x["telegram"] for x in fx["sent"] if x["telegram"] and "update impact (GA4)" in x["telegram"]]
    assert [x["run"] for x in fx["sent"] if x["telegram"] and "update impact (GA4)" in x["telegram"]] == ["2026-09-21T12:00Z"]
    assert re.search(r"🟠 \[WARNING\] Demo Caller – Test App: v3\.2 \(10 Sep\) ke baad purane users ka DAU [\d.]+% gira "
                     r"\(expected [\d,]+ → [\d,]+/din\) · aur 1 cheez kharab: time per user −\d+% · HALT — staged rollout "
                     r"rok do, hotfix bhejo · shuruaati — D7 abhi baaki · update impact \(GA4\)", halt[0])
    b = imp[("Demo Flashlight", "v1.2")]                         # new users come back more: a WIN (seeded: first eval)
    assert b["verdict"]["better"] == ["new_d1"] and b["rows"]["new_d1"]["change"] > 5 and not b["verdict"]["worse"]
    assert imp[("Demo Flashlight", "v1.3")]["verdict"]["why"].startswith("Abhi 1 pakka din")
    b = imp[("Demo Wallpapers", "v2.0")]                          # a staged rollout stuck at 25%: fewer ads per user
    r = b["rows"]["arpdau"]
    assert r["status"] == "worse" and -0.1 < r["change"] < -0.05 and abs(r["extra"]["imp_change"] - r["change"]) < 0.01
    assert {"diluted", "slow_rollout", "tz_blend"} <= set(b["notes"]) and b["adoption"]["mean"] < 0.3
    b = imp[("Demo Weather", "v4.1")]                             # GA4 keeps its user data 60 days: said, not guessed
    assert all(b["rows"][k]["reason"] == "GA4 ab itna purana user data nahi rakhta" for k in ("new_d1", "new_d7"))
    assert wea["impact"]["flags"]["ret_from"] > "2026-07-01" and "no_cohorts" in b["notes"]
    b = imp[("Demo Launcher", "App update")]
    assert b["kind"] == "update" and all(r["status"] == "na" for r in b["versions_cmp"]["rows"].values())
    assert s["impact_counts"] == {"halt": 1, "hold": 1, "continue": 1, "win": 1, "pending": 1}
    assert all(a["impact"]["flags"]["revenue"] in ("ok", "partial") for a in asset["apps"])      # the AdMob revenue
    assert all(LOG_LINE.match(line) for line in fx["public_log"]) and len(fx["public_log"]) == 7
    with open(OUT, encoding="utf-8") as f:
        committed = f.read()
    assert committed == fixture_json(fx), "regenerate: python -m tests.make_uninstall_fixture"


# ── the store-format bump (v1 → v2): no alert from the undercounted data is ever sent ──────────────

def test_a_v1_store_never_sends_an_alert_and_its_clean_re_pull_starts_the_alerts_over(tmp_path, monkeypatch):
    from tests import test_ga4_uninstall as tg
    w = tg.World(monkeypatch)
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    os.makedirs(data)
    with open(os.path.join(data, "app_store_ids.json"), "w", encoding="utf-8") as f:
        json.dump({"by_id": {tg.A1: tg.PKG1}}, f)
    s = ga4_settings(ga4_client_id="cid", ga4_client_secret="sec",
                     ga4_refresh_tokens=json.dumps({tg.EMAIL_A: tg.RT_A, tg.EMAIL_B: tg.RT_B}))
    dash = lambda: {"apps_catalog": [{"app_id": tg.A1, "app_name": "One", "account_id": "p", "selected": True}],  # noqa: E731
                    "kpis": {}, "alerts": {"items": []}}

    def build(now):
        d = dash()
        ub.run_uninstall(d, data, out, s, now=now)
        res = build_static.send_alerts(d, s)
        build_static._uninstall_mark_sent(d, data, s, res)
        return d, _gz(os.path.join(out, ASSET))["apps"][0]
    d, a = build(tg.NOW)                                            # first ever: full v2 fetch, seeded
    assert not any(x["notify"] for x in d["uninstall"]["alerts"]) and a["flags"]["outdated"] is False
    # what the first production run left: a v1 store whose older cohorts GA4 undercounted (~2%)
    path = gu.store_path(data, tg.A1)
    st = gu.load_store(path)
    cut = (tg.END - timedelta(days=10)).isoformat()
    st["v"] = 1
    for c, lags in st["cohorts"].items():
        if c < cut:
            for k in lags:
                lags[k] = lags[k] // 50
    gu.save_store(path, st)
    state = gu.load_state(data)
    state["fetch"][tg.A1]["meta"] = gu.store_meta(st)
    state["eval"][tg.A1].update(end=(tg.END - timedelta(days=1)).isoformat(), streak={"cohort|up": 1})   # held yesterday
    day = (tg.END - timedelta(days=1)).isoformat()                 # an alert a v1 run opened whose send FAILED:
    state["episodes"][tg.A1 + "|rate_spike|up|" + day] = {          # still due
        "id": "pending-v1", "app_id": tg.A1, "family": "rate_spike", "dir": "up", "opened": day, "last_true": day,
        "misses": 0, "notified_at": None, "notified_dry": False, "seeded": False, "day": day, "last_day": day,
        "last": {"day": day, "now": 9.0, "before": 5.0, "lo": 3.5, "hi": 6.5, "users": 900, "severity": "warning"}}
    gu.save_state(data, state)
    w.fail = lambda body: (_ for _ in ()).throw(RuntimeError("HTTP 500: INTERNAL"))   # the re-pull fails for now
    d, a = build(tg.NOW + timedelta(hours=21))
    assert a["flags"]["outdated"] is True and d["uninstall"]["alerts"]              # the bad data looks alarming …
    assert not any(x["notify"] for x in d["uninstall"]["alerts"])                  # … but nothing goes out —
    assert "pending-v1" in {x["id"] for x in d["uninstall"]["alerts"]}             # not even the one still due
    assert gu.load_state(data)["fetch"][tg.A1]["fail"] == "http"
    w.fail = None
    d, a = build(tg.NOW + timedelta(hours=25))                     # 3h later: the clean re-pull, alerts start over
    assert gu.load_store(path)["v"] == gu.STORE_V and a["flags"]["outdated"] is False
    state = gu.load_state(data)
    assert state["fetch"][tg.A1]["last_kind"] == "full" and not state["closed"]
    assert not any(x["notify"] for x in d["uninstall"]["alerts"])                  # a first evaluation: seeded
    assert all(e["seeded"] for e in state["episodes"].values())


# ── the store-format bump (v2 → v3): checked data, repaired in place, alerts kept unless it moved ─────

def test_a_v2_store_is_checked_data_while_its_repair_waits_and_a_repair_that_barely_moves_keeps_the_alerts(
        tmp_path, monkeypatch):
    from tests import test_ga4_uninstall as tg
    w = tg.World(monkeypatch)
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    os.makedirs(data)
    with open(os.path.join(data, "app_store_ids.json"), "w", encoding="utf-8") as f:
        json.dump({"by_id": {tg.A1: tg.PKG1}}, f)
    s = ga4_settings(ga4_client_id="cid", ga4_client_secret="sec",
                     ga4_refresh_tokens=json.dumps({tg.EMAIL_A: tg.RT_A, tg.EMAIL_B: tg.RT_B}))

    def build(now):
        d = {"apps_catalog": [{"app_id": tg.A1, "app_name": "One", "account_id": "p", "selected": True}],
             "kpis": {}, "alerts": {"items": []}}
        ub.run_uninstall(d, data, out, s, now=now)
        return d, _gz(os.path.join(out, ASSET))["apps"][0]
    build(tg.NOW)                                                   # v3 from the start
    path = gu.store_path(data, tg.A1)
    st = gu.load_store(path)
    for k in ("cell_src", "users_ok_days", "events_chunk_days"):   # what the v2 code wrote: one day GA4 answered
        st.pop(k)                                                   # at half, flagged
    st["flags"].pop("users_k")
    st["v"] = 2
    short = (END - timedelta(days=40)).isoformat()
    for c, lags in st["cohorts"].items():
        for lag in lags:
            if (datetime.fromisoformat(c) + timedelta(days=int(lag))).date().isoformat() == short:
                lags[lag] //= 2
    st["flags"]["incomplete_days"] = {short: 0.5}
    gu.save_store(path, st)
    state = gu.load_state(data)
    state["fetch"][tg.A1]["meta"] = gu.store_meta(st)
    gu.save_state(data, state)
    resets = []
    real_reset = gu.reset_alerts
    monkeypatch.setattr(gu, "reset_alerts", lambda state, aid: (resets.append(aid), real_reset(state, aid)))
    w.fail = lambda body: (_ for _ in ()).throw(RuntimeError("HTTP 500: INTERNAL"))
    d, a = build(tg.NOW + timedelta(hours=1))                      # the repair fails for now …
    assert gu.load_store(path)["v"] == 2 and gu.load_state(data)["fetch"][tg.A1]["fail"] == "http"
    assert a["flags"]["outdated"] is False                          # … a v2 store is checked data: evaluated and
    assert list(a["flags"]["incomplete_days"]) == [short]           # alerted as ever, its short day left out
    w.fail = None
    d, a = build(tg.NOW + timedelta(hours=5))                      # 4h later: a failed repair waits a day (and
    assert gu.load_store(path)["v"] == 2 and a["flags"]["incomplete_days"]   # no incremental is due yet)
    d, a = build(tg.NOW + timedelta(hours=25))                     # a day after it: repaired — that one day, by
    st = gu.load_store(path)                                        # events
    assert st["v"] == gu.STORE_V and st["flags"]["incomplete_days"] == {}
    assert st["cell_src"][short]["src"] == "events_scaled"
    assert a["flags"]["cell_days"] == {"users": 199, "events": 1, "estimated": 0, "incomplete": 0}
    assert gu.load_state(data)["fetch"][tg.A1]["last_kind"] == "repair"
    assert resets == []                                             # half a day of 200 moved: < 1% — its alert
                                                                    # history is kept


# ── update impact: the card rides the uninstall build, its alerts the notifications ─────────────────

R_IMP = date(2026, 8, 26)


def seed_impact(data_dir, fresh=False):
    """A1: an update whose old users open the app 10% less (HALT); A2: an update that changes nothing (CONTINUE); both
    with usage / vuse / return cohorts → the AdMob revenue {…, apps: {AdMob app id: {day: [micros, impressions]}}}."""
    os.makedirs(os.path.join(data_dir, "ga4_uninstall"), exist_ok=True)
    with open(os.path.join(data_dir, "app_store_ids.json"), "w", encoding="utf-8") as f:
        json.dump({"by_id": {A1: PKG[A1], A2: PKG[A2], A9: PKG[A1]}}, f)
    rev = {"tz": "Asia/Kolkata", "currency": "USD", "till": END.isoformat(), "apps": {}}
    for aid, act in ((A1, 0.9), (A2, 1.0)):
        st, rv = make_impact_store(120, new=500, old=40000, app_id=aid,
                                   versions=rollout("1.0", [(R_IMP, "1.1", 0.3)]),
                                   act=lambda d, v, x=act: x if v == "1.1" else 1.0)
        st.update(property_id=PID, stream_id=SID, package=PKG[aid])
        gu.save_store(gu.store_path(data_dir, aid), st)
        rev["apps"][aid] = rv["days"]
    rev["apps"][A9] = {k: [v[0] // 4, v[1] // 4] for k, v in rev["apps"][A1].items()}   # same Play package as A1
    state = gu._state_default()
    state["routes"].update(fetched_at="2026-09-21T01:00:00Z", by_package={
        PKG[a]: {"property_id": PID, "stream_id": SID, "owner": EMAIL} for a in (A1, A2)})
    state["tz"] = {PID: "Asia/Kolkata"}
    if not fresh:
        state["eval"] = {a: {"end": (END - timedelta(days=1)).isoformat(), "stage": "badh_raha", "stable_hold": 0,
                             "impact": {"data": True, "blocks": {}}} for a in (A1, A2)}
    gu.save_state(data_dir, state)
    return rev


def impact_dashboard():
    return {"apps_catalog": [{"app_id": a, "app_name": n, "account_id": "pub-7", "selected": True}
                             for a, n in ((A1, N1), (A2, N2), (A9, "Caller Copy"))],
            "kpis": {"revenue": 12.5}, "alerts": {"items": []}}


@pytest.fixture
def isite(tmp_path, monkeypatch):
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    rev = seed_impact(data)
    monkeypatch.setattr(gu, "refresh_all", lambda *a, **k: copy.deepcopy(dict(STATUS, apps={A1: "fresh", A2: "fresh"})))
    return data, out, rev


def irun(data, out, rev, now=NOW):
    dash = impact_dashboard()
    ub.run_uninstall(dash, data, out, ga4_settings(), now=now, revenue=rev)
    return dash, _gz(os.path.join(out, ASSET))


def test_every_app_update_gets_its_card_in_the_asset_and_the_summary(isite):
    data, out, rev = isite
    dash, asset = irun(data, out, rev)
    s = dash["uninstall"]
    check_summary(s)
    check_asset(asset, s)                                           # check_impact on every detail (the 7 + 2 rows)
    assert asset["consts"]["impact"] == imp.CONSTS
    assert asset["lateness"] is None or "a1" in asset["lateness"]
    by = {a["app_id"]: a for a in asset["apps"]}
    b1, b2 = by[A1]["impact"]["updates"][0], by[A2]["impact"]["updates"][0]
    assert (b1["verdict"]["level"], b2["verdict"]["level"]) == ("halt", "continue")
    assert b1["rows"]["returning_dau"]["status"] == "worse" and b1["alert_id"]
    assert s["impact_counts"] == {"halt": 1, "hold": 0, "continue": 1, "win": 0, "pending": 0}
    rows = {r["app_id"]: r for r in s["apps"]}
    assert rows[A1]["updates"] == [{"key": "ver:1.1@2026-08-26", "label": "v1.1", "date": "2026-08-26", "level": "halt",
                                    "early": False, "final": True, "adoption": b1["adoption"]["last"],
                                    "head": {"row": "returning_dau", "change": b1["rows"]["returning_dau"]["change"],
                                             "unit": "rel"}}]
    al = [a for a in s["alerts"] if a["family"] == "impact"]
    assert [(a["app"], a["severity"], a["level"], a["notify"]) for a in al] == [(N1, "warning", "halt", True)]
    assert al[0]["message"].startswith(N1 + ": v1.1 (26 Aug) ke baad purane users ka DAU ")


def test_the_same_play_packages_admob_apps_revenue_is_summed_and_without_revenue_only_arpdau_changes(isite):
    data, out, rev = isite
    one = ub.app_revenue(rev, {"app_id": A1, "package": PKG[A1]}, [{"app_id": A9, "same_pkg": PKG[A1]}])
    day = "2026-09-01"
    assert one["days"][day] == [rev["apps"][A1][day][0] + rev["apps"][A9][day][0],
                                rev["apps"][A1][day][1] + rev["apps"][A9][day][1]]
    assert ub.app_revenue(rev, {"app_id": A2, "package": PKG[A2]}, [{"app_id": A9, "same_pkg": PKG[A1]}])["days"][day] == \
        rev["apps"][A2][day]
    assert ub.app_revenue(None, {"app_id": A1, "package": PKG[A1]}, []) is None
    # an app the app list lost the package of: its OWN revenue still (the store's package joins its copies)
    own = ub.app_revenue(rev, {"app_id": A1, "package": None}, [{"app_id": A9, "same_pkg": PKG[A1]}])
    assert own["days"][day] == rev["apps"][A1][day]
    assert ub.app_revenue(rev, {"app_id": A1, "package": None}, [{"app_id": A9, "same_pkg": PKG[A1]}],
                          PKG[A1])["days"][day] == one["days"][day]
    # the copy's account reports in another timezone: spread over this app's days — every dollar kept, none moved
    # to a day as if the two days were one
    other = "America/Los_Angeles" if rev["tz"] != "America/Los_Angeles" else "Asia/Kolkata"
    ist = ub.app_revenue(dict(rev, tz_by_app={A9: other}), {"app_id": A1, "package": PKG[A1]},
                         [{"app_id": A9, "same_pkg": PKG[A1]}])
    assert ist["tz"] == rev["tz"] and ist["days"] != one["days"]
    gap = sum(v[0] for v in one["days"].values()) - sum(v[0] for v in ist["days"].values())
    assert 0 < gap < rev["apps"][A9][max(rev["apps"][A9])][0]      # only the part of its last day past `till` waits
    assert max(ist["days"]) <= rev["till"]
    assert ub.app_revenue(dict(rev, tz_by_app={A1: other}), {"app_id": A1, "package": PKG[A1]}, [])["tz"] == other
    apps = ub._selected_apps(impact_dashboard(), data)
    assert [a for a in apps if a["app_id"] == A9] == [{"app_id": A9, "app_name": "Caller Copy", "package": None,
                                                       "same_as": N1, "same_pkg": PKG[A1]}]
    _, asset = irun(data, out, rev)
    with_rev = asset["apps"][[a["app_id"] for a in asset["apps"]].index(A1)]["impact"]["updates"][0]
    assert with_rev["rows"]["arpdau"]["before"] == pytest.approx(8.0 * 1.25, abs=0.05)     # A1 + its copy (¼ of it)
    seed_impact(data)
    _, asset = irun(data, out, None)
    b = asset["apps"][[a["app_id"] for a in asset["apps"]].index(A1)]["impact"]["updates"][0]
    assert b["rows"]["arpdau"]["status"] == "na" and b["rows"]["arpdau"]["reason"] == "AdMob revenue nahi mila"
    assert {k: r for k, r in b["rows"].items() if k != "arpdau"} == {
        k: r for k, r in with_rev["rows"].items() if k != "arpdau"}
    assert all(a["impact"]["flags"]["revenue"] == "none" for a in asset["apps"])


def test_an_update_alert_goes_out_once_as_update_impact_and_its_log_line_is_counts_only(isite, capsys):
    data, out, rev = isite
    dash, _ = irun(data, out, rev)
    err = capsys.readouterr().err.splitlines()
    assert len(err) == 1 and LOG_LINE.match(err[0])
    assert err[0].endswith("impact updates 2 (halt 1, hold 0, win 0, early 0), impact alerts 1 (new 1)")
    for secret in (N1, N2, A1, A2, "1.1", "ver:", "Aug", PKG[A1]):
        assert secret not in err[0]
    res = build_static.send_alerts(dash, ga4_settings())
    tele = next(r["text"] for r in res if r["channel"] == "telegram")
    assert "🟠 [WARNING] " + N1 + ": v1.1 (26 Aug) ke baad" in tele and tele.count(" · update impact (GA4)") == 1
    assert "uninstall (GA4)" not in tele
    build_static._uninstall_mark_sent(dash, data, ga4_settings(), res)
    for h in (1, 2):                                                # the hourly runs after it: shown, never re-sent
        dash, _ = irun(data, out, rev, now=NOW + timedelta(hours=h))
        assert [a["notify"] for a in dash["uninstall"]["alerts"] if a["family"] == "impact"] == [False]
        assert build_static.send_alerts(dash, ga4_settings()) == []


def test_the_first_impact_evaluation_is_shown_not_sent_and_re_runs_rewrite_nothing(tmp_path, monkeypatch):
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    rev = seed_impact(data, fresh=True)
    monkeypatch.setattr(gu, "refresh_all", lambda *a, **k: copy.deepcopy(STATUS))
    dash, asset = irun(data, out, rev)
    al = [a for a in dash["uninstall"]["alerts"] if a["family"] == "impact"]
    assert len(al) == 1 and not al[0]["notify"]                     # seeded
    check_impact(asset["apps"][0]["impact"], asset["apps"][0])
    irun(data, out, rev, now=NOW + timedelta(hours=1))

    def snap():
        files = {}
        for root in (out, os.path.join(data, "ga4_uninstall")):
            for n in sorted(os.listdir(root)):
                p = os.path.join(root, n)
                files[p] = (open(p, "rb").read(), os.stat(p).st_mtime_ns)
        return files
    a = snap()
    irun(data, out, rev, now=NOW + timedelta(hours=2))
    assert snap() == a                                              # the impact state too: same bytes, same mtime


def test_the_build_hands_the_network_reports_revenue_to_the_uninstall_step(tmp_path, monkeypatch):
    from admob_iq.db import FileRepo
    repo = FileRepo(str(tmp_path / "d"))
    repo.init_schema()
    base = dict(account_id="pub-7", ad_unit_id="u", country="US", format="banner", platform="Android",
                ad_requests=100, matched_requests=90, clicks=0)
    for d, app, unit, imps, micros in (("2026-09-18", A1, "u1", 100, 250000), ("2026-09-18", A1, "u2", 50, 125000),
                                       ("2026-09-19", A1, "u1", 80, 200000), ("2026-09-20", A1, "u1", 9, 9),
                                       ("2026-09-18", A2, "u3", 10, 20000)):
        repo.upsert_network(dict(base, report_date=d, app_id=app, ad_unit_id=unit, impressions=imps,
                                 estimated_earnings_micros=micros))
    got = []
    monkeypatch.setattr(build_static, "_uninstall_step",
                        lambda dash, data_dir, out_dir, s, revenue=None: got.append(revenue) or ["x"])
    s = dict(ga4_settings(), report_currency="USD")
    assert build_static._uninstall_with_revenue({}, repo, "data", "site", s, "America/Los_Angeles",
                                                date(2026, 9, 20)) == ["x"]
    assert got == [{"tz": "America/Los_Angeles", "currency": "USD", "till": "2026-09-19",   # today (20th) still filling
                    "apps": {A1: {"2026-09-18": [375000, 150], "2026-09-19": [200000, 80]},
                             A2: {"2026-09-18": [20000, 10]}}, "tz_by_app": {}}]
    # a second account reporting in its own timezone: its apps are named, never read as Pacific days
    got.clear()
    build_static._uninstall_with_revenue({}, repo, "data", "site", s, "America/Los_Angeles", date(2026, 9, 20),
                                         {"pub-7": "Asia/Kolkata"})
    assert got[0]["tz_by_app"] == {A1: "Asia/Kolkata", A2: "Asia/Kolkata"}
    assert build_static.account_tzs([{"account_id": "pub-1", "reporting_tz": "Asia/Kolkata"}, {"account_id": "pub-2"}],
                                    s, "America/Los_Angeles", "mock", False) == {
        "pub-1": "Asia/Kolkata", "pub-2": "America/Los_Angeles"}
