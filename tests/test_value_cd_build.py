"""The Install value build with VALUE_CD / GADS_GEO (SPEC_CD_GEO §S.1, §S.7 "CB:"): both flags off → everything the
tab writes, keeps or prints is byte-identical to abd6ee8's builder (pinned digests, computed with abd6ee8's own code on
these same synthetic inputs); on → C / D reach the detail files, the counts and the consts, and nothing else of the
contract moves. All data is synthetic (tests.value_synth).

The digest helpers below import only what abd6ee8 already had, so the pins can be recomputed by running them against a
checkout of that commit (python -c "import tests.test_value_cd_build as t; print(t.flags_off_digest(dir), …)")."""

import contextlib
import gzip
import hashlib
import io
import json
import os
import re
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from admob_iq import build_static
from admob_iq import value_build as vb
from admob_iq.config import settings
from admob_iq.engine import value as val
from admob_iq.fetch import ga4_uninstall as gu
from tests import value_synth as vs

APPS = vs.FIX_APPS
SPEND_ID, ORG_ID, YOUNG_ID = (a[0] for a in APPS)
NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
STATUS = {"counts": {"selected": 3, "with_ga4": 3, "fetched": 0, "full": 0, "fresh": 3, "failed": 0, "deferred": 0,
                     "no_ga4": 0}, "apps": {}, "no_ga4": {}, "discovery": None}
VAL_LOG = re.compile(r"^ga4 value: apps \d+, with ads \d+, organic \d+, install-day data \d+ \(whole \d+, filling \d+, "
                     r"waiting \d+\), country sampled \d+, country weeks not clean \d+, country cost (on|off), "
                     r"open alerts \d+ \(new \d+\), errors \d+$")
# abd6ee8's builder / engine on the inputs below (see the module doc) — the flags-off outputs must never move
ABD6EE8_BUILD = "238f49d6fff5e270"
ABD6EE8_LEGACY_GEO = "29a9f9e5b7be7cc1"


def _settings(**kw):
    s = dict(settings(), ga4_enabled=True, ga4_client_id="cid", ga4_client_secret="sec",
             ga4_refresh_tokens=json.dumps({"owner@example.test": "rt-x"}), ga4_refresh_token="", notify_dry_run=True,
             ga4_value=True, ga4_active=True, value_payback_days=90, value_iap=False, value_cpi="blended",
             value_deduct=True, gads_geo=False, value_cd=False)
    s.update(kw)
    return s


def _dashboard():
    cat = [{"app_id": aid, "app_name": name, "account_id": "pub-5", "selected": True} for aid, name, _, _ in APPS]
    return {"apps_catalog": cat, "kpis": {"revenue": 1.0}, "alerts": {"items": []}, "placements": [],
            "usd_inr": 83.3}


def run_builds(tmp, s=None, seed_kw=None, days=(7, 0)):
    """Daily builds of the three made-up apps (GA4 till now − 2), the state carried from one to the next → [{value,
    files, state, err}] per build: dashboard["value"], every value_<key>.json.gz (parsed), value_state.json (text) and
    the build's stderr lines."""
    data, out = os.path.join(tmp, "data"), os.path.join(tmp, "site")
    s = s or _settings()
    got = []
    with mock.patch.object(gu, "refresh_all", lambda *a, **k: json.loads(json.dumps(STATUS))):
        for back in days:
            now = NOW - timedelta(days=back)
            rev, _ = vs.seed_build(data, end=now.date() - timedelta(days=2), **(seed_kw or {}))
            dash = _dashboard()
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                build_static._uninstall_step(dash, data, out, s, revenue=rev, now=now)
            files = {}
            for r in (dash.get("value") or {}).get("apps") or []:
                if r.get("file"):
                    with gzip.open(os.path.join(out, r["file"]), "rt", encoding="utf-8") as f:
                        files[r["file"]] = json.load(f)
            p = os.path.join(data, "ga4_uninstall", "value_state.json")
            got.append({"value": dash.get("value"), "files": files,
                        "state": open(p, encoding="utf-8").read() if os.path.exists(p) else None,
                        "err": err.getvalue().splitlines(), "dash": dash})
    return got


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def flags_off_digest(tmp):
    return _digest([{k: v for k, v in b.items() if k != "dash"} for b in run_builds(tmp)])


def legacy_geo_digest():
    """The engine's countries block, summary row, alerts and state for the legacy country-cost inputs (a plain
    per-country total, and cost per day) and without any — as abd6ee8's engine gives them."""
    S = vs.END - timedelta(days=vs.LATE)
    m = vs.make_app(start=vs.END - timedelta(days=60 * 7 - 1), seed=3)

    def ev(geo):
        return val.evaluate_app(m["store"], m["ida"], m["rev"], m["spend"], m["fx"], [], None, {},
                                {"payback_days": 90}, "2026-09-21T12:00:00Z", app_id="app-x", app="Demo App",
                                key="k", geo=geo)
    det0, _, _ = ev(None)
    n = {r["cc"]: r["n"] for r in det0["countries"]["rows"]}
    plain = {"US": {"cost": 0.05 * n["US"], "dl": n["US"]}, "IN": {"cost": 0.034 * n["IN"], "dl": n["IN"]},
             "NG": {"cost": 0.2 * n["NG"], "dl": n["NG"]}}
    daily = {}
    for i in range(120):
        d = S - timedelta(days=i)
        k = m["new"][d] * vs.CTY["IN"][0]
        daily[d.isoformat()] = [0.05 * k, 0.87 * k]
    out = {}
    for name, geo in (("off", None), ("plain", plain), ("daily", {"IN": {"daily": daily}, "US": {"daily": daily}})):
        det, row, st = ev(geo)
        out[name] = {"countries": det["countries"], "check": det["scale"]["text"], "tiles": det["tiles"],
                     "cty": row["cty"], "alerts": row["_alerts"], "state": st}
    return _digest(out)


# ── both flags off: byte-identical to abd6ee8 ───────────────────────────────────────────────────

def test_flags_off_byte_identical(tmp_path):
    """dashboard["value"], the detail files, value_state.json and every stderr line of two daily builds."""
    assert flags_off_digest(str(tmp_path)) == ABD6EE8_BUILD


def test_legacy_country_cost_shapes_byte_identical():
    assert legacy_geo_digest() == ABD6EE8_LEGACY_GEO


# ── VALUE_CD on ─────────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def cd_builds(tmp_path_factory):
    return run_builds(str(tmp_path_factory.mktemp("cd")), s=_settings(value_cd=True), seed_kw={"cd": True})


def test_cd_contract_objects(cd_builds):
    b = cd_builds[-1]
    V = b["value"]
    assert set(V) == {"v", "status", "asset_v", "horizon", "settled_till_min", "settled_till_max", "counts", "consts",
                      "alerts", "alert_counts", "no_ga4", "apps", "spend_ccy"}
    for r in V["apps"]:                                  # the summary rows: exactly the keys they had
        assert set(r) == {"app_id", "app", "key", "file", "sig", "status", "settled_till", "iday", "pay", "rpi", "cpi",
                          "cty", "alerts", "summary", "s", "src_ccy"}
        assert set(r["cty"]) == {"best", "weak", "judged", "of", "all_avg", "win_weeks", "geo", "smp", "clean"}
    det = {f["app_id"]: f for f in b["files"].values()}
    bv = det[SPEND_ID]["by_version"]
    assert set(bv) == {"state", "text", "dom_min", "left_out", "no_vuse", "phi", "short", "older", "rows"}
    assert bv["state"] == "ok" and bv["dom_min"] == 0.8 and bv["left_out"]["days"] == 3 and bv["left_out"]["n"] > 0
    assert [r["ver"] for r in bv["rows"]] == ["2.3", "2.2", "2.1.1", "2.1", "2.0"]
    row = bv["rows"][0]
    assert set(row) == {"ver", "label", "from", "to", "days", "n", "share_dom", "current", "gaps", "release", "d1",
                        "d7", "d30", "rpi", "vs", "verdict", "text"}
    assert set(row["d1"]) == {"v", "lo", "hi", "n", "ret", "st", "days", "of", "in", "q"}
    assert set(row["rpi"]) == {"1", "7", "30"} and set(row["rpi"]["7"]) == {"v", "lo", "hi", "est", "n", "st", "days",
                                                                          "of", "in"}
    assert row["label"] == "v2.3" and row["current"] and row["d7"]["st"] == "wait" and row["d7"]["v"] is None
    two = next(r for r in bv["rows"] if r["ver"] == "2.2")
    assert two["vs"]["ver"] == "2.1" and two["vs"]["skipped"] == ["2.1.1"] and two["verdict"] == "same"
    assert set(two["vs"]["d1"]) >= {"v0", "v1", "delta", "rel", "z", "n0", "n1", "days0", "days1", "from0", "to0",
                                    "from1", "to1", "st"}
    assert set(two["vs"]["rpi7"]) >= {"v0", "v1", "rel", "z", "st"}
    assert det[ORG_ID]["by_version"]["state"] == "nosplit" and det[YOUNG_ID]["by_version"]["state"] == "single"
    lg = det[SPEND_ID]["long"]
    assert set(lg) == {"state", "grain", "text", "note", "edge", "phi", "rows", "base"}
    assert lg["state"] == "ok" and lg["grain"] == "month" and set(lg["phi"]) == {"30", "60", "90", "180", "365"}
    r0 = lg["rows"][0]
    assert set(r0) == {"key", "label", "year", "from", "to", "n", "days", "part", "q", "d", "rpi", "b365",
                       "b365_proj", "b365_thin", "release"}
    assert set(r0["d"]) == {"30", "60", "90", "180", "365"} and set(r0["rpi"]) == {"30", "90", "180", "365"}
    assert set(r0["d"]["30"]) == {"v", "lo", "hi", "ret", "st", "in"}
    assert set(r0["rpi"]["30"]) >= {"v", "lo", "hi", "est", "proj", "shape", "st", "in"}
    assert lg["rows"][-1]["part"] and not any(r["part"] for r in lg["rows"][:-1])
    assert any(r["d"]["365"]["st"] == "ok" for r in lg["rows"])                       # D365 complete for the oldest
    assert det[YOUNG_ID]["long"]["state"] == "young"
    # steady made-up users: no C / D alert, the tab's pinned alert mix unchanged
    assert not [a for a in V["alerts"] if a["family"] in ("ver_ret", "long_ret")]
    assert V["alert_counts"] == {"warning": 1, "watch": 2, "good": 0}


def test_counts_ver_long_geo_only_when_on(cd_builds, tmp_path):
    c = cd_builds[-1]["value"]["counts"]
    assert c["ver"] == {"ok": 1, "single": 1, "low": 0, "nodata": 0, "nosplit": 1, "error": 0}
    assert c["long"] == {"ok": 2, "young": 1, "low": 0, "error": 0}
    assert set(c["geo"]) == {"on", "off"}
    off = run_builds(str(tmp_path / "off"), days=(0,))[-1]["value"]["counts"]
    assert "ver" not in off and "long" not in off and set(off["geo"]) == {"on", "off"}
    geo = run_builds(str(tmp_path / "geo"), s=_settings(gads_geo=True), days=(0,))[-1]["value"]["counts"]
    assert set(geo["geo"]) == {"on", "off", "cov", "wait", "nostore", "noads"} and "ver" not in geo


def test_value_log_line_unchanged_with_cd_and_geo_on(cd_builds, tmp_path):
    on = [ln for b in run_builds(str(tmp_path / "on"), s=_settings(value_cd=True, gads_geo=True),
                                  seed_kw={"cd": True}, days=(0,)) for ln in b["err"]]
    off = [ln for b in run_builds(str(tmp_path / "off"), days=(0,)) for ln in b["err"]]
    von = [ln for ln in on if ln.startswith("ga4 value")]
    voff = [ln for ln in off if ln.startswith("ga4 value")]
    assert len(von) == 1 and VAL_LOG.match(von[0]) and von == voff        # steady users: the same counts too
    assert not [ln for ln in on if ln.startswith("gads geo")]             # the ROAS step's line, never this step's


def test_consts_cd_gated():
    from admob_iq.engine import value_cd
    base = vb.consts(vb.cfg_from({}))
    assert base == dict(val.CONSTS, horizon=90, iap_in_payback=False, cpi_main="blended", deduct=True, geo=False)
    assert "cd" not in base and "geo_cov_min" not in base
    on = vb.consts(vb.cfg_from({"value_cd": True}))
    assert on["cd"] is True and on["ver_dom"] == 0.8 and on["long_t"] == [30, 60, 90, 180, 365]
    assert on["reopen_seed_days"] == {"pay_loss": 91, "geo_move": 42, "geo_cost": 42, "long_ret": 91}
    assert {k: v for k, v in on.items() if k not in value_cd.CONSTS and k != "cd"} == \
        {k: v for k, v in base.items() if k != "reopen_seed_days"}
    geo = vb.consts(vb.cfg_from({"gads_geo": True}))
    assert (geo["geo_cov_min"], geo["geo_cov_max"], geo["geo_days"]) == (0.97, 1.03, vb.GEO_DAYS) and "cd" not in geo
    assert geo["reopen_seed_days"]["geo_cost"] == 42 and base["reopen_seed_days"] == val.CONSTS["reopen_seed_days"]
    assert vb.cfg_from({})["cd"] is False and vb.cfg_from({"value_cd": True})["cd"] is True


def test_release_impact_rows_reach_engine(tmp_path):
    udet = {"releases": [{"date": "2026-08-10", "version": "2.2", "kind": "version"}],
            "impact": {"updates": [
                {"key": "B2", "versions": ["2.2"], "verdict": {"worse": ["new_d1", "sessions"], "better": []}},
                {"key": "B1", "versions": ["2.1", "2.2"], "verdict": {"worse": [], "better": ["new_d7"]}}]}}
    assert vb.release_impact(udet) == {"2.2": {"worse": ["new_d1", "sessions"], "better": [], "key": "B2"},
                                       "2.1": {"worse": [], "better": ["new_d7"], "key": "B1"}}
    assert vb.release_impact(None) == {} and vb.release_impact({"impact": {"updates": [{"versions": 5}]}}) == {}
    seen = []
    real = val.evaluate_app

    def spy(*a, **k):
        seen.append(k.get("impact", "absent"))
        return real(*a, **k)
    with mock.patch.object(val, "evaluate_app", spy):
        run_builds(str(tmp_path / "on"), s=_settings(value_cd=True), seed_kw={"cd": True}, days=(0,))
        run_builds(str(tmp_path / "off"), days=(0,))
    assert len(seen) == 6 and all(isinstance(x, dict) for x in seen[:3]) and seen[3:] == ["absent"] * 3
