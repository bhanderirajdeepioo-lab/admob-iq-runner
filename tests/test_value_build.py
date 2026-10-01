"""The Install value tab's build step (admob_iq.value_build + its uninstall_build / build_static wiring, SPEC_AB_FINAL
§3.4): nothing changes while no app has install-day data or with GA4_VALUE off, the Uninstall and Active outputs stay
byte-identical, alerts are seeded on the first build and later go out ONCE with their label, the state survives the
other steps' saves, a failure costs only this tab, the public log is one counts line, re-runs rewrite nothing, and the
committed frontend fixture is exactly what the build code writes. All data is synthetic (tests.value_synth)."""

import copy
import gzip
import json
import os
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq import active_build as ab
from admob_iq import build_static
from admob_iq import uninstall_build as ub
from admob_iq import value_build as vb
from admob_iq.config import settings
from admob_iq.engine import value as val
from admob_iq.fetch import ga4_uninstall as gu
from tests import value_synth as vs

APPS = vs.FIX_APPS
SPEND_ID, ORG_ID, YOUNG_ID = (a[0] for a in APPS)
NAMES = [a[1] for a in APPS]
PKGS = [a[2] for a in APPS]
NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
UNI_LOG = re.compile(r"^ga4 uninstall: apps \d+, with GA4 \d+, ")
VAL_LOG = re.compile(r"^ga4 value: apps \d+, with ads \d+, organic \d+, install-day data \d+ \(whole \d+, filling \d+, "
                     r"waiting \d+\), country sampled \d+, country weeks not clean \d+, country cost (on|off), "
                     r"open alerts \d+ \(new \d+\), errors \d+$")
STATUS = {"counts": {"selected": 3, "with_ga4": 3, "fetched": 0, "full": 0, "fresh": 3, "failed": 0, "deferred": 0,
                     "no_ga4": 0}, "apps": {}, "no_ga4": {}, "discovery": None}


def ga4_settings(**kw):
    s = dict(settings(), ga4_enabled=True, ga4_client_id="cid", ga4_client_secret="sec",
             ga4_refresh_tokens=json.dumps({"owner@example.test": "rt-SECRET-v"}), ga4_refresh_token="",
             notify_dry_run=True, ga4_value=True)                  # (the tab's own tests: switched on)
    s.update(kw)
    return s


def dashboard():
    cat = [{"app_id": aid, "app_name": name, "account_id": "pub-5", "selected": True} for aid, name, _, _ in APPS]
    return {"apps_catalog": cat, "kpis": {"revenue": 1.0}, "alerts": {"items": []}, "placements": [],
            "usd_inr": 83.3}


@pytest.fixture
def vsite(tmp_path, monkeypatch):
    monkeypatch.setattr(gu, "refresh_all", lambda *a, **k: copy.deepcopy(STATUS))
    return str(tmp_path / "data"), str(tmp_path / "site")


def vbuild(data, out, now=NOW, s=None, step=False, iday=True, hours=0):
    """One daily build: the stores / install-day files as the fetch left them on GA4 day now − 2 → (dash, files).
    An hourly re-run (hours > 0) finds the files as they are."""
    end = now.date() - timedelta(days=2)
    rev, _ = vs.seed_build(data, end=end, write=not hours)
    if not iday:
        for aid in (SPEND_ID, ORG_ID, YOUNG_ID):
            for p in vb.iday_paths(data, aid):
                if os.path.exists(p):
                    os.remove(p)
    dash = dashboard()
    now = now + timedelta(hours=hours)
    s = s or ga4_settings()
    if step:
        files = build_static._uninstall_step(dash, data, out, s, revenue=rev, now=now)
    else:
        files = ub.run_uninstall(dash, data, out, s, now=now, revenue=rev)
    return dash, files


def _snap(*roots):
    got = {}
    for root in roots:
        for n in sorted(os.listdir(root)):
            p = os.path.join(root, n)
            if os.path.isfile(p):
                got[p] = (open(p, "rb").read(), os.stat(p).st_mtime_ns)
    return got


def _others(data, out, dash):
    """Everything the Uninstall and Active tabs wrote (bytes) + their dashboard keys."""
    got = {n: open(os.path.join(out, n), "rb").read() for n in sorted(os.listdir(out))
           if n.startswith(("uninstall", "active_"))}
    for n in ("state.json", "active_state.json"):
        p = os.path.join(data, "ga4_uninstall", n)
        got[n] = open(p, "rb").read() if os.path.exists(p) else None
    return got, json.dumps({k: dash.get(k) for k in ("uninstall", "active")}, sort_keys=True)


# ── nothing changes without data, or switched off ───────────────────────────────────────────────

def test_without_install_day_data_nothing_is_written_set_or_printed(vsite, capsys):
    data, out = vsite
    dash, files = vbuild(data, out, iday=False)
    assert "value" not in dash and "uninstall" in dash and "active" in dash
    assert not [n for n in os.listdir(out) if n.startswith("value_")]
    assert not os.path.exists(vb.state_path(data))
    err = capsys.readouterr().err.splitlines()
    assert len(err) == 1 and UNI_LOG.match(err[0])
    assert files[0] == "uninstall.json.gz" and all(not f.startswith("value_") for f in files)


def test_value_off_changes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gu, "refresh_all", lambda *a, **k: copy.deepcopy(STATUS))
    runs = {}
    for name, s in (("on", ga4_settings()), ("off", ga4_settings(ga4_value=False))):
        data, out = str(tmp_path / name / "data"), str(tmp_path / name / "site")
        capsys.readouterr()
        dash, files = vbuild(data, out, s=s)
        runs[name] = (_others(data, out, dash), dash, data, out, files, capsys.readouterr().err)
    on, off = runs["on"], runs["off"]
    assert on[0] == off[0]                                            # Uninstall + Active: byte-identical
    assert on[4] == off[4] and on[5] == off[5]                        # the same files returned, the same log line
    assert "value" in on[1] and "value" not in off[1]
    assert not [n for n in os.listdir(off[3]) if n.startswith("value_")]
    assert not os.path.exists(vb.state_path(off[2]))
    assert {k: v for k, v in on[1].items() if k != "value"} == off[1]


def test_uninstall_and_active_outputs_unchanged(tmp_path, monkeypatch, capsys):
    """GA4_VALUE on changes nothing of the Uninstall and Active tabs: (1) the existing harnesses — the committed Uninstall
    fixture (seven builds) and Active fixture — are still exactly what the build writes with the setting switched on;
    (2) with install-day files present, over three daily builds (alerts sent and marked in between), the Uninstall and
    Active files, dashboard keys and states and the returned file list are byte-identical to the same builds with it
    off, and the step prints the same lines plus the value tab's ONE counts line."""
    from tests import make_uninstall_fixture as mf
    monkeypatch.setenv("GA4_VALUE", "true")
    assert settings()["ga4_value"] is True
    with open(mf.OUT, encoding="utf-8") as f:
        assert mf.fixture_json(mf.build_fixture(str(tmp_path / "uni"))) == f.read()
    with open(mf.OUT_ACTIVE, encoding="utf-8") as f:
        assert mf.active_fixture_json(mf.build_active_fixture(str(tmp_path / "act"))) == f.read()
    monkeypatch.delenv("GA4_VALUE")
    monkeypatch.setattr(gu, "refresh_all", lambda *a, **k: copy.deepcopy(STATUS))
    got = {}
    for name, s in (("on", ga4_settings(ga4_value=True)), ("off", ga4_settings(ga4_value=False))):
        data, out = str(tmp_path / name / "data"), str(tmp_path / name / "site")
        runs = []
        for now in vs.RUNS[-3:]:
            capsys.readouterr()
            dash, files = vbuild(data, out, now=now, s=s, step=True)
            res = build_static.send_alerts(dash, s)
            build_static._uninstall_mark_sent(dash, data, s, res)
            err = capsys.readouterr().err.splitlines()
            runs.append((_others(data, out, dash), files, [l for l in err if not l.startswith("ga4 value: ")],
                         [l for l in err if l.startswith("ga4 value: ")],
                         [r for r in res if "install value" not in json.dumps(r, ensure_ascii=False)]))
        got[name] = runs
    for on, off in zip(got["on"], got["off"]):
        assert on[0] == off[0] and on[1] == off[1] and on[2] == off[2] and on[4] == off[4]
        assert len(on[3]) == 1 and VAL_LOG.match(on[3][0]) and off[3] == []


# ── the contract ─────────────────────────────────────────────────────────────────────────────────

def test_summary_rows_and_files_follow_the_contract(vsite):
    data, out = vsite
    dash, files = vbuild(data, out)
    V = dash["value"]
    assert set(V) == {"v", "status", "asset_v", "horizon", "settled_till_min", "settled_till_max", "counts", "consts",
                      "alerts", "alert_counts", "no_ga4", "apps", "spend_ccy",
                      "info", "closed"}                           # info / closed: SPEC_SIMPLIFY (a contract extension)
    assert V["status"] == "ok" and V["horizon"] == 90 and re.match(r"^[0-9a-f]{12}$", V["asset_v"])
    assert V["counts"]["apps"] == 3 and V["counts"]["organic"] == 1 and V["counts"]["with_spend"] == 2
    assert V["counts"]["iday"] == {"wait": 0, "filling": 1, "whole": 2} and V["counts"]["cty"]["sampled"] == 1
    rows = {r["app_id"]: r for r in V["apps"]}
    for r in V["apps"]:
        assert set(r) == {"app_id", "app", "key", "file", "sig", "status", "settled_till", "iday", "pay", "rpi", "cpi",
                          "cty", "alerts", "summary", "s", "src_ccy"}
        assert r["file"] == "value_%s.json.gz" % gu.file_key(r["app_id"]) and os.path.exists(os.path.join(out, r["file"]))
        assert len(json.dumps(r, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 2048
        assert os.path.getsize(os.path.join(out, r["file"])) <= 150 * 1024
        with gzip.open(os.path.join(out, r["file"]), "rt", encoding="utf-8") as f:
            d = json.load(f)
        for k in ("v", "app_id", "app", "key", "tz", "currency", "horizon", "settled_till", "fetched_at", "iday", "scale",
                  "fx", "tiles", "summary", "weeks", "curve", "countries", "changes", "by_version", "long"):
            assert k in d, k
        assert set(d["tiles"]) == {"pay", "b7", "rpi", "cpi", "cty"}
        assert d["summary"] == r["summary"]
    assert rows[SPEND_ID]["pay"]["p"] is not None and rows[ORG_ID]["pay"]["st"] == "nospend"
    assert rows[YOUNG_ID]["iday"]["state"] == "filling" and rows[ORG_ID]["cty"]["smp"]
    assert len(json.dumps(V, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 60 * 1024


# ── alerts: seeded first, then ONCE with their label ─────────────────────────────────────────────

def test_first_value_build_sends_nothing(vsite):
    data, out = vsite
    dash, _ = vbuild(data, out)
    al = dash["value"]["alerts"]
    assert al and not any(a["notify"] for a in al)                   # the cost jump and Nigeria: shown, seeded
    res = build_static.send_alerts(dash, ga4_settings())
    assert "install value" not in json.dumps(res, ensure_ascii=False)
    assert vb.load_state(data)["eval"].keys() == {SPEND_ID, ORG_ID, YOUNG_ID}


def test_value_alerts_go_out_once_with_label(vsite):
    data, out = vsite
    tele, mail = [], []
    for now in vs.RUNS:                                                # 6 weekly builds: the first one seeds
        dash, _ = vbuild(data, out, now=now)
        res = build_static.send_alerts(dash, ga4_settings())
        tele += [l for r in res if r["channel"] == "telegram" for l in r["text"].split("\n")]
        mail += [l for r in res if r["channel"] == "email" for l in r["body"].split("\n")]
        build_static._uninstall_mark_sent(dash, data, ga4_settings(), res)
    tl = [l for l in tele if l.endswith(" · install value (GA4 + Ads)")]
    ml = [l for l in mail if l.endswith(" · install value (GA4 + Ads)")]
    assert [l.split(":")[0] for l in tl] == ["🟠 [WARNING] Demo Spend App"]
    assert "Ads ka paisa wapas aane me der" in tl[0] and "install ka kharcha $0.060 → $0.096" in tl[0]
    assert [l.split(":")[0] for l in ml if l.startswith("🟡")] == ["🟡 [WATCH] Demo Spend App"]
    assert "Nigeria me agle din wapas aane wale kam" in [l for l in ml if l.startswith("🟡")][0]
    assert not [l for l in tl + ml if "pay_loss" in l or "paisa wapas nahi karte" in l]   # 7-day pay dedupe
    for h in (1, 2):                                                  # the hourly runs after: nothing again
        dash, _ = vbuild(data, out, now=vs.RUNS[-1], hours=h)
        assert "install value" not in json.dumps(build_static.send_alerts(dash, ga4_settings()), ensure_ascii=False)
        assert len(dash["value"]["alerts"]) == 3 and not any(a["notify"] for a in dash["value"]["alerts"])


def test_value_state_survives_refresh_and_marks(vsite, monkeypatch):
    data, out = vsite
    dash, _ = vbuild(data, out, now=vs.RUNS[-1])
    before = copy.deepcopy(vb.load_state(data))
    assert before["eval"] and before["episodes"]
    ub.mark_notified(data, dash["uninstall"], dry=True)
    ab.mark_notified_active(data, dash["active"], dry=True)
    monkeypatch.setattr(gu, "refresh_all", lambda cfg, d, *a, **k: (gu.save_state(d, gu.load_state(d)),
                                                                   copy.deepcopy(STATUS))[1])
    vbuild(data, out, now=vs.RUNS[-1] + timedelta(days=7))                          # a week later
    after = vb.load_state(data)
    for k, e in before["episodes"].items():
        if k in after["episodes"]:
            assert (after["episodes"][k]["opened"], after["episodes"][k]["seeded"]) == (e["opened"], e["seeded"])
    assert after["eval"][SPEND_ID]["inputs"] == before["eval"][SPEND_ID]["inputs"]      # not a first evaluation again
    assert after["eval"][SPEND_ID]["end_week"] > before["eval"][SPEND_ID]["end_week"]
    assert "value" not in json.load(open(os.path.join(data, "ga4_uninstall", "state.json")))


def test_re_runs_leave_every_file_byte_identical(vsite):
    data, out = vsite
    dash, _ = vbuild(data, out)
    vb.mark_notified_value(data, dash["value"], dry=True, now=NOW)
    vbuild(data, out, hours=1)
    a = _snap(out, os.path.join(data, "ga4_uninstall"))
    assert vb.state_path(data) in a
    dash, _ = vbuild(data, out, hours=2)
    assert _snap(out, os.path.join(data, "ga4_uninstall")) == a        # same bytes, same mtimes
    assert "install value" not in json.dumps(build_static.send_alerts(dash, ga4_settings()), ensure_ascii=False)


# ── privacy: one counts line, nothing private ships ──────────────────────────────────────────────

def test_log_line_counts_only(vsite, capsys):
    data, out = vsite
    capsys.readouterr()
    dash, _ = vbuild(data, out, step=True)
    got = capsys.readouterr()
    lines = got.err.splitlines()
    assert got.out == "" and len(lines) == 3 and UNI_LOG.match(lines[0]) and lines[1].startswith("ga4 active: ")
    assert VAL_LOG.match(lines[2]) and lines[2] == vb.log_line(dash["value"])
    for s in NAMES + PKGS + [SPEND_ID, "p-spend", "2026-", "Sep", "$", "NG", "US", "Nigeria", "com.demo"]:
        assert s not in lines[2]
    shipped = json.dumps(dash["value"], ensure_ascii=False)
    for n in os.listdir(out):
        if n.startswith("value_"):
            shipped += gzip.open(os.path.join(out, n), "rt", encoding="utf-8").read()
    for s in ("p-spend", "s-spend", "owner@example.test", "rt-SECRET"):
        assert s not in shipped


def test_stale_value_files_removed(vsite):
    data, out = vsite
    os.makedirs(out)
    for n in ("value_deadbeef0000.json.gz", "value_notes.txt"):
        with open(os.path.join(out, n), "wb") as f:
            f.write(b"stale")
    dash, files = vbuild(data, out)
    names = vb.files(dash)
    assert sorted(names) == sorted("value_%s.json.gz" % gu.file_key(a) for a in (SPEND_ID, ORG_ID, YOUNG_ID))
    assert not os.path.exists(os.path.join(out, "value_deadbeef0000.json.gz"))
    assert os.path.exists(os.path.join(out, "value_notes.txt"))
    headers = build_static.headers_text(files, dash)
    for n in names:
        assert "/%s\n  Cache-Control: no-store\n" % n in headers
    assert build_static.headers_text(files, {k: v for k, v in dash.items() if k != "value"}) == \
        headers.replace("".join("/%s\n  Cache-Control: no-store\n\n" % n for n in names), "")


def test_prepass_reads_no_country_revenue(vsite, monkeypatch):
    data, out = vsite
    rev, _ = vs.seed_build(data)

    class Repo:
        def fetch_network(self):
            return []

        def fetch_mediation(self):
            return []

        def fetch_country(self):
            raise AssertionError("the value tab must not read AdMob country revenue")
    seen = []
    real = ub.run_uninstall
    monkeypatch.setattr(ub, "run_uninstall", lambda d, *a, **k: seen.append(1) or real(d, *a, **dict(k, now=NOW)))
    dash = dashboard()
    build_static._uninstall_with_revenue(dash, Repo(), data, out, ga4_settings(), "UTC", date(2026, 9, 21))
    assert seen and "value" in dash
    pre = vb.prepass(data, [], None, dashboard(), vb.cfg_from(ga4_settings()), vb.load_state(data))
    assert set(pre) == {"data_dir", "spend", "aliases", "owner", "siblings", "fx", "ded", "geo", "portfolio_shape"}
    assert pre["geo"] is None and pre["ded"] == {} and pre["fx"]["mode"] == "dated"


# ── failures cost only this tab ──────────────────────────────────────────────────────────────────

def test_a_crash_in_the_value_step_never_costs_the_other_tabs(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gu, "refresh_all", lambda *a, **k: copy.deepcopy(STATUS))
    data, out = str(tmp_path / "ok" / "data"), str(tmp_path / "ok" / "site")
    dash, _ = vbuild(data, out)
    good = _others(data, out, dash)
    capsys.readouterr()
    real = val.evaluate_app

    def boom(*a, **k):
        if k.get("app_id") == ORG_ID:
            raise RuntimeError("HTTP 403 on property p-organic")
        return real(*a, **k)
    monkeypatch.setattr(val, "evaluate_app", boom)
    data, out = str(tmp_path / "per_app" / "data"), str(tmp_path / "per_app" / "site")
    dash, _ = vbuild(data, out)
    assert _others(data, out, dash) == good
    rows = {r["app_id"]: r for r in dash["value"]["apps"]}
    assert rows[ORG_ID]["status"] == "error" and rows[ORG_ID]["file"] is None and rows[SPEND_ID]["status"] == "ok"
    assert dash["value"]["status"] == "partial" and dash["value"]["counts"]["errors"] == 1
    assert ORG_ID not in vb.load_state(data)["eval"]
    err = capsys.readouterr().err.splitlines()
    assert len(err) == 1 and UNI_LOG.match(err[0])                   # silent: the one uninstall line
    monkeypatch.setattr(val, "evaluate_app", real)

    def fail(*a, **k):
        raise RuntimeError("disk")
    monkeypatch.setattr(vb, "save_state", fail)                      # the end of the step fails
    data, out = str(tmp_path / "finish" / "data"), str(tmp_path / "finish" / "site")
    dash, _ = vbuild(data, out)
    assert _others(data, out, dash) == good and "value" not in dash
    err = capsys.readouterr().err.splitlines()
    assert len(err) == 2 and UNI_LOG.match(err[0]) and err[1] == "ga4 value skipped: RuntimeError"


def test_uninstall_step_crash_pops_value_too(tmp_path, monkeypatch, capsys):
    def half(dash, *a, **k):
        dash["uninstall"], dash["value"] = {"half": 1}, {"alerts": [{"id": "x", "notify": True}]}
        raise RuntimeError("boom")
    monkeypatch.setattr(ub, "run_uninstall", half)
    dash = dashboard()
    before = copy.deepcopy(dash)
    assert build_static._uninstall_step(dash, str(tmp_path), str(tmp_path / "site"), ga4_settings()) == []
    assert dash == before and capsys.readouterr().err == "ga4 uninstall skipped: RuntimeError\n"


def test_value_mark_runs_even_if_the_others_fail(vsite, monkeypatch, capsys):
    data, out = vsite
    for now in vs.RUNS[:-1]:
        dash, _ = vbuild(data, out, now=now)
        build_static._uninstall_mark_sent(dash, data, ga4_settings(), build_static.send_alerts(dash, ga4_settings()))
    dash, _ = vbuild(data, out, now=vs.RUNS[-1])
    due = [a["id"] for a in dash["value"]["alerts"] if a["notify"]]
    assert due
    capsys.readouterr()

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(ub, "mark_notified", boom)
    monkeypatch.setattr(ab, "mark_notified_active", boom)
    build_static._uninstall_mark_sent(dash, data, ga4_settings(), build_static.send_alerts(dash, ga4_settings()))
    assert capsys.readouterr().err == ("ga4 uninstall notify-mark skipped: RuntimeError\n"
                                       "ga4 active notify-mark skipped: RuntimeError\n")
    st = vb.load_state(data)
    assert all(e["notified_at"] for e in st["episodes"].values() if e["id"] in due)


# ── the pieces: install-day files, spend join, FX series, settings ───────────────────────────────

def test_iday_old_part_is_folded_back(tmp_path):
    m = vs.make_app(start=vs.FIX_START["spend"], seed=11)
    data = str(tmp_path)
    vs.write_iday(data, SPEND_ID, m["ida"])
    hot, old = vb.iday_paths(data, SPEND_ID)
    assert os.path.exists(hot) and os.path.exists(old)
    assert vb.load_iday(data, SPEND_ID) == m["ida"]
    ida = vb.load_iday(data, SPEND_ID)
    det, _, _ = val.evaluate_app(m["store"], ida, m["rev"], m["spend"], m["fx"], [], None, {}, {"payback_days": 90},
                                 "2026-09-21T12:00:00Z", app_id=SPEND_ID, app="x", key="k")
    one, _, _ = val.evaluate_app(m["store"], m["ida"], m["rev"], m["spend"], m["fx"], [], None, {},
                                 {"payback_days": 90}, "2026-09-21T12:00:00Z", app_id=SPEND_ID, app="x", key="k")
    assert det == one
    with open(hot, "wb") as f:
        f.write(b"not gzip")
    assert vb.load_iday(data, SPEND_ID) is None and vb.load_iday(data, ORG_ID) is None


def test_the_engine_reads_exactly_what_the_real_fetch_writes(tmp_path):
    """The contract between the two halves, end to end: a synthetic GA4 (tests.test_ga4_iday's IdayGA / IdayTruth) →
    the REAL fetch_iday (reads, self-checks, folds; a backfill over several hourly runs) → the REAL save_iday / load_iday
    (hot + frozen .old files) → the build's reader → the engine. Every number the engine builds from the file equals the
    GA4 truth: the day totals and the AdMob scale, installs and earning per install per install week at each age
    (complete exactly when every day it needs was read), country installs and earnings per week, and the day GA4 lost
    30% of its country rows is measured as unassigned (never spread) and keeps that week from being judged."""
    from tests.test_ga4_iday import END as T_END, F as T_F, IdayGA, IdayTruth, PID, SID
    data, aid, k = str(tmp_path), "ca-app-pub-5555555555555555~777", 1.1
    t = IdayTruth(T_END - timedelta(days=223), T_END, new=lambda d: 350 + (d.toordinal() % 7) * 20)
    lossy = T_F - timedelta(days=40)
    t.qc_loss[lossy] = 0.3
    store = dict(t.store(), app_id=aid, property_id=PID, stream_id=SID, time_zone="UTC",
                 fetched_at=T_END.isoformat() + "T06:00:00Z")
    runs = 0
    while True:                                                   # hourly builds of one day: the backfill carries on
        ida, _ = gu.fetch_iday(IdayGA(t), store, gu.load_iday(data, aid), T_END,
                               at="%sT%02d:00:00Z" % (T_END.isoformat(), runs))
        gu.save_iday(data, aid, ida)
        runs += 1
        if runs == 1:
            part = vb.load_iday(data, aid)                        # after the first run: the newest days only
        if ida["done"] or runs > 12:
            break
    assert ida["done"] and runs >= 3 and os.path.exists(gu.iday_path(data, aid, old=True))
    got = vb.load_iday(data, aid)
    assert got == gu.load_iday(data, aid) and got["to"] == T_F.isoformat() and got["from"] == t.start.isoformat()
    hs, S = t.start, T_F
    tot = {d: sum(v[2] for v in t.cells(d).values()) for d in t.days}              # GA4's day totals (micros)
    rev = {"tz": "UTC", "currency": "USD", "till": T_END.isoformat(),
           "days": {d.isoformat(): [int(round(m * k)), 1] for d, m in tot.items()},
           "all_days": {d.isoformat(): [int(round(m * k)), 1] for d, m in tot.items()}}
    P = val._prep(store, got, rev, None)
    assert P["S"] == S and P["sc"]["st"] == "ok" and P["sc"]["src"] == "all"
    assert all(P["sc"]["G"][d] == tot[d] / 1e6 for d in t.days if d <= S) and len(P["sc"]["G"]) == (S - hs).days + 1
    assert all(abs(v[3] - k) < 1e-6 for v in P["sc"]["kinfo"].values())               # AdMob ÷ GA4, every month
    checked = 0
    for w in P["weeks"]:
        xs = [x for x in t.days if w["first"] <= x <= min(w["last"], S)]
        assert w["n"] == sum(t.new[x] for x in xs)
        for j, age in enumerate(val.T):
            assert w["cj"][j] == (w["last"] + timedelta(days=age) <= S)             # complete ⇔ every day read
            if w["cj"][j]:
                want = k * sum(t.cells(x + timedelta(days=lag))[x][2] for x in xs for lag in range(age + 1)
                               if x in t.cells(x + timedelta(days=lag))) / 1e6
                assert abs(w["R"][j] - want) <= 1e-6 * max(want, 1.0), (w["W"], age)
                checked += 1
    assert checked > 100
    Pp = val._prep(store, part, rev, None)                        # a backfill half way: nothing before `from` counts
    pf = date.fromisoformat(part["from"])
    assert hs < pf and not part["done"]
    for w in Pp["weeks"]:
        for j, age in enumerate(val.T):
            assert w["cj"][j] == (w["first"] >= pf and w["last"] + timedelta(days=age) <= S)
    # countries: the file's slots → ISO codes; per install week the named rows + the unassigned gap = Q-B installs
    cset, cw, _ = val._country_data(P, got)
    assert set(cset) == {"US", "IN", "BR", "DE", "NG", "KE", "--", "ZZ"}
    want_n, want_r7 = {}, {}
    for d in t.days:
        if d > S:
            continue
        for cc, x, v in t.cty_rows(d, [d - timedelta(days=i) for i in range(91)]):
            if x < hs:
                continue
            cc = "--" if cc == "(not set)" else cc
            W = x - timedelta(days=x.weekday())
            if d == lossy:
                v = [v[0], int(v[1] * 0.7), int(v[2] * 0.7), v[3]]
            if d == x:
                want_n[(W, cc)] = want_n.get((W, cc), 0) + v[1]
            if (d - x).days <= 7:
                want_r7[(W, cc)] = want_r7.get((W, cc), 0) + v[2]
    for W, e in cw.items():
        assert sum(r["n"] for r in e["rows"].values()) + e["gap"]["n"] == P["wk"][W]["n"]
        for cc, r in e["rows"].items():
            assert r["n"] == want_n.get((W, cc), 0), (W, cc)
            if P["wk"][W]["cj"][val.T.index(7)]:
                assert abs(r["R"][val.T.index(7)] - k * want_r7.get((W, cc), 0) / 1e6) < 1e-6
    C = val._Cty(P, got)
    lw = lossy - timedelta(days=lossy.weekday())
    assert cw[lw]["gap"]["n"] > 0 and not C.clean(lw, 1)
    assert all(C.clean(W, t_) for W in cw if W > lossy for t_ in (1, 7, 30) if C.complete(W, t_))
    # and the whole evaluation runs on it: Google Ads spend (INR at dated rates) → cost per install per week
    rate = {d.isoformat(): 0.012 for d in t.days}
    spend = {"ccy": "INR", "daily": {d.isoformat(): int(round(0.05 * t.new[d] / 0.012 * 1e6)) for d in t.days},
             "installs": {d.isoformat(): t.new[d] * 0.8 for d in t.days}, "first": hs.isoformat(),
             "till": T_END.isoformat()}
    det, row, _ = val.evaluate_app(store, got, rev, spend, {"series": rate, "now": 0.012}, [], None, {},
                                   {"payback_days": 90}, T_END.isoformat() + "T12:00:00Z", app_id=aid, app="Contract",
                                   key=gu.file_key(aid))
    assert row["status"] == "ok" and det["iday"]["state"] == "whole" and det["iday"]["pct"] == 100
    assert det["settled_till"] == S.isoformat() and det["spend_till"] == T_END.isoformat()
    full = [w for w in det["weeks"] if w["from"] >= hs.isoformat() and w["to"] <= S.isoformat()]
    assert full and all(abs(w["ecpi"] - 0.05) < 1e-6 and w["n"] == sum(t.new[x] for x in t.days
                        if w["from"] <= x.isoformat() <= w["to"]) for w in full)
    assert det["iday"]["cty"]["gap"] == 1 and det["scale"]["old_rev"] == 0


def test_spend_joins_by_package_and_roas_alias(tmp_path):
    data = str(tmp_path / "data")
    os.makedirs(os.path.join(str(tmp_path), "config"))
    with open(os.path.join(str(tmp_path), "config", "roas_app_aliases.json"), "w") as f:
        json.dump({"com.ads.other.listing": "Demo Spend App"}, f)
    os.makedirs(data)
    sp = {"daily": {"2026-09-01": 1000000}, "installs": {"2026-09-01": 10.0}}
    with open(os.path.join(data, "roas_spend_cache.json"), "w") as f:
        json.dump(vs.spend_cache([("com.demo.value.spend", sp), ("com.ads.other.listing", sp),
                                  ("com.unrelated", sp)]), f)
    pre = vb.prepass(data, [], None, dashboard(), vb.cfg_from(ga4_settings()), vb._default())
    got = vb.app_spend(pre, {"app_id": SPEND_ID, "app_name": "Demo Spend App", "package": "com.demo.value.spend"}, {})
    assert got["daily"] == {"2026-09-01": 2000000} and got["installs"] == {"2026-09-01": 20.0} and got["sids"] == 2
    none = vb.app_spend(pre, {"app_id": ORG_ID, "app_name": "Demo Organic App", "package": "com.nothing"}, {})
    assert none["daily"] == {} and none["sids"] == 0
    assert vb.app_spend({"spend": None}, {"app_id": ORG_ID, "app_name": "x"}, {}) is None


def test_spend_goes_to_exactly_the_app_the_roas_tab_gives_it(tmp_path):
    """The Marketing ROAS tab's store id → app map decides (engine.roas.store_owner, handed over by the build or
    rebuilt the same way): an alias naming "Demo Spend App" never also lands on "Demo Spend App Plus" (a longer name
    that merely starts with it), a Play package the ROAS tab gives another AdMob app is not taken, a second AdMob app
    on the same package (one GA4 stream) brings its spend along, and an unplaced own package still counts."""
    data = str(tmp_path / "data")
    os.makedirs(os.path.join(str(tmp_path), "config"))
    with open(os.path.join(str(tmp_path), "config", "roas_app_aliases.json"), "w") as f:
        json.dump({"com.ads.other.listing": "Demo Spend App"}, f)
    os.makedirs(data)
    with open(os.path.join(data, "app_store_ids.json"), "w") as f:
        json.dump({"by_id": {"ca-app-pub-1~1": "com.demo.plus", "ca-app-pub-1~2": "com.demo.shared",
                             "ca-app-pub-1~3": "com.demo.shared", "ca-app-pub-1~4": "com.demo.taken"}}, f)
    sp = {"daily": {"2026-09-01": 1000000}, "installs": {"2026-09-01": 10.0}}
    with open(os.path.join(data, "roas_spend_cache.json"), "w") as f:
        json.dump(vs.spend_cache([(p, sp) for p in ("com.demo.value.spend", "com.ads.other.listing", "com.demo.plus",
                                                    "com.demo.shared", "com.demo.taken")]), f)
    dash = dashboard()
    dash["apps_catalog"] += [{"app_id": "ca-app-pub-1~1", "app_name": "Demo Spend App Plus", "rev": 5.0},
                             {"app_id": "ca-app-pub-1~2", "app_name": "Twin A", "rev": 1.0},
                             {"app_id": "ca-app-pub-1~3", "app_name": "Twin B", "rev": 9.0},
                             {"app_id": "ca-app-pub-1~4", "app_name": "Big Other", "rev": 50.0}]
    apps = [{"app_id": "ca-app-pub-1~2", "app_name": "Twin A", "package": "com.demo.shared"},
            {"app_id": "ca-app-pub-1~3", "app_name": "Twin B", "package": None, "same_as": "Twin A",
             "same_pkg": "com.demo.shared"}]
    pre = vb.prepass(data, apps, None, dash, vb.cfg_from(ga4_settings()), vb._default())

    def sids(name, pkg):
        return vb.app_spend(pre, {"app_id": "x", "app_name": name, "package": pkg}, {})["sids"]
    assert sids("Demo Spend App", "com.demo.value.spend") == 2               # its package + the alias naming it
    assert sids("Demo Spend App Plus", "com.demo.plus") == 1                 # never the alias of a shorter name
    assert sids("Twin A", "com.demo.shared") == 1                            # ROAS gives it to Twin B: one stream
    assert sids("Mine Too", "com.demo.taken") == 0                           # ROAS gives it to another app
    handed = dict(pre, owner={"com.demo.plus": "Demo Spend App"})           # the build's own map wins
    assert vb.app_spend(handed, {"app_id": "x", "app_name": "Demo Spend App", "package": None}, {})["sids"] == 1
    assert vb.cfg_from(ga4_settings(roas_store_owner={"a": "b"}))["store_owner"] == {"a": "b"}


def test_fx_series_one_call_a_day(tmp_path):
    data = str(tmp_path)
    calls = []

    class R:
        def __init__(self, rates):
            self.rates = rates

        def json(self):
            return {"rates": self.rates}

    def get(url, timeout=None):
        calls.append(url)
        return R({"2026-09-01": {"USD": 0.0120}, "2026-09-02": {"USD": 0.0121}})
    t0 = 1_800_000_000
    assert vb.update_fx_series(data, "INR", "2026-09-01", date(2026, 9, 3), get=get, now=t0) == 2
    assert calls[0].startswith("https://api.frankfurter.dev/v1/2026-09-01..2026-09-03?from=INR&to=USD")
    assert vb.update_fx_series(data, "INR", "2026-09-01", date(2026, 9, 4), get=get, now=t0 + 3600) == 0
    assert len(calls) == 1                                                  # at most one call a ~day
    vb.update_fx_series(data, "INR", "2026-09-01", date(2026, 9, 4), get=get, now=t0 + 21 * 3600)
    assert calls[1].split("/v1/")[1].startswith("2026-09-03..2026-09-04")   # from the last stored day on
    fx = vb._load_fx(data, {"usd_inr": 80.0}, "INR")
    assert fx["mode"] == "dated" and fx["series"]["2026-09-02"] == 0.0121 and fx["now"] == pytest.approx(1 / 80)
    assert vb._load_fx(str(tmp_path / "none"), {"usd_inr": 80.0}, "INR")["mode"] == "one"

    def down(url, timeout=None):
        raise OSError("offline")
    with pytest.raises(OSError):
        vb.update_fx_series(str(tmp_path / "x"), "INR", "2026-09-01", date(2026, 9, 4), get=down, now=t0)
    assert vb.update_fx_series(data, "USD", "2026-09-01", date(2026, 9, 4), get=down) == 0


def test_settings_defaults_and_names(monkeypatch):
    s = settings()
    assert s["ga4_value"] is False and s["value_payback_days"] == 90 and s["gads_geo"] is False   # rollout step 3
    assert s["ga4_iday"] is False and ub.ga4_cfg(ga4_settings())["iday"] is False
    assert ub.ga4_cfg(ga4_settings(ga4_iday=True))["iday"] is True and ub.ga4_cfg(ga4_settings())["iday_max_calls"] == 120
    assert s["value_iap"] is False and s["value_cpi"] == "blended" and s["value_deduct"] is True
    assert s["iday_max_calls"] == 120 and s["iday_cty_days"] == 400
    monkeypatch.setenv("VALUE_TARGET_DAYS", "180")
    assert settings()["value_payback_days"] == 180
    monkeypatch.setenv("VALUE_PAYBACK_DAYS", "60")
    assert settings()["value_payback_days"] == 60                             # the spec's name wins
    monkeypatch.setenv("VALUE_PAYBACK_DAYS", "soon")
    assert settings()["value_payback_days"] == 180
    monkeypatch.setenv("GA4_VALUE", "true")
    assert settings()["ga4_value"] is True
    assert vb.cfg_from({"value_payback_days": 45})["payback_days"] == 90      # only 30/60/90/180/365


# ── the committed frontend fixture ───────────────────────────────────────────────────────────────

def test_the_committed_fixture_is_what_the_build_writes(tmp_path):
    if not os.path.exists(vs.OUT):
        pytest.skip("tests/fixtures/value_sample.json not generated yet")
    with open(vs.OUT, encoding="utf-8") as f:
        committed = f.read()
    assert vs.fixture_json(vs.build_fixture(str(tmp_path))) == committed
    fx = json.loads(committed)
    assert fx["dashboard_value"]["alert_counts"] == {"warning": 1, "watch": 2, "good": 0}
    assert all(VAL_LOG.match(l) for l in fx["public_log"])
    assert set(fx["app_files"]) == {gu.file_key(a) for a in (SPEND_ID, ORG_ID, YOUNG_ID)}


def test_releases_carry_their_update_impact_block():
    udet = {"releases": [{"date": "2026-08-26", "version": "3.1", "kind": "version"},
                         {"date": "2026-09-01", "kind": "update"}],
            "impact": {"updates": [{"key": "B1", "rel_keys": ["ver:3.1@2026-08-26"]}]}}
    assert vb.releases(udet) == [{"date": "2026-08-26", "version": "3.1", "kind": "version", "key": "B1"},
                                 {"date": "2026-09-01", "version": None, "kind": "update", "key": None}]
    assert vb.releases(None) == []


# ── review fixes: the spend's own "fetched till", country cost per day, the market's weeks ────────────────────────

def test_spend_till_is_the_last_good_fetch_not_the_newest_spend_day(tmp_path):
    """The cache keeps its history when a Google Ads fetch fails: its newest day with spend says nothing about how far
    spend is KNOWN. The ROAS step records the last day a fetch went through; the tab reads spend only up to it."""
    data = str(tmp_path)
    days = {"2026-09-%02d" % d: 1_000_000 for d in range(1, 21)}
    with open(os.path.join(data, vb.SPEND_FILE), "w", encoding="utf-8") as f:
        json.dump({"v": 2, "currency_src": "INR", "daily": {"com.x": days}, "installs": {}}, f)
    assert vb._load_spend(data)["till"] == "2026-09-20" and vb._load_spend(data)["till_src"] == "max"
    assert vb.record_spend_fetch(data, date(2026, 9, 18)) == "2026-09-17"
    first = os.stat(os.path.join(data, vb.SPEND_OK_FILE)).st_mtime_ns
    assert vb.record_spend_fetch(data, "2026-09-18") == "2026-09-17"                     # written only on change
    assert os.stat(os.path.join(data, vb.SPEND_OK_FILE)).st_mtime_ns == first
    sp = vb._load_spend(data)
    assert sp["till"] == "2026-09-17" and sp["till_src"] == "fetch"
    assert vb._load_spend(data, "2026-09-12")["till"] == "2026-09-12"                  # this build's own fetch wins
    assert vb.cfg_from({"roas_spend_ok_till": "2026-09-12"})["spend_ok_till"] == "2026-09-12"


def test_country_cost_goes_to_the_engine_per_day(tmp_path):
    """GADS_GEO: the country cache → cost per DAY (USD at each day's rate) over the last GEO_DAYS days, so the engine
    sums exactly the weeks of the installs it divides by."""
    pre = {"geo": {"daily": {"com.x": {"2026-09-%02d" % d: {"IN": [83_000_000, 10]} for d in range(1, 21)},
                             "com.other": {"2026-09-01": {"IN": [1, 1]}}}},
           "spend": {"ccy": "INR"}, "owner": {"com.x": "App X", "com.other": "Other"}, "siblings": {}}
    fx = {"mode": "one", "now": 1 / 83.0, "series": {}}
    got = vb._app_geo(pre, {"app_name": "App X", "package": "com.x"}, {"package": "com.x"}, fx, "2026-09-20")
    assert set(got) == {"IN"} and len(got["IN"]["daily"]) == 20
    assert got["IN"]["daily"]["2026-09-05"] == pytest.approx([1.0, 10.0])
    old = vb._app_geo(pre, {"app_name": "App X", "package": "com.x"}, {"package": "com.x"}, fx, "2027-01-30")
    assert old is None                                                                   # older than GEO_DAYS: none


@pytest.mark.parametrize("active", [True, False])
def test_the_market_weeks_reach_the_tab_with_or_without_active(vsite, monkeypatch, active):
    """The weeks most apps' ad rate moved together (Active's market prepass) reach every app's value step — read by
    the tab itself when the Active tab is off."""
    data, out = vsite
    mk = {"weeks": [{"from": "2026-08-24", "to": "2026-08-30", "dir": "down", "share": 0.9, "apps": 9, "of": 8}]}
    monkeypatch.setattr(ab, "market_prepass", lambda *a, **k: mk)
    seen = []
    real = vb.app_step

    def spy(*a, **k):
        seen.append(k.get("market"))
        return real(*a, **k)
    monkeypatch.setattr(vb, "app_step", spy)
    dash, _ = vbuild(data, out, s=ga4_settings(ga4_active=active))
    assert dash.get("value") and seen and all(m == mk for m in seen)
