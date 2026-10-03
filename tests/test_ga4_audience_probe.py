"""GA4 Audience one-off probe (admob_iq.fetch.ga4_audience_probe + .github/workflows/ga4-audience-probe.yml) — offline,
synthetic users only: every app read with the build's own fetch, its numbers derived, one private report written; the
apps input (packages, keys or app ids, read from the event file — never the public log), resume (a partial read goes on,
complete apps are kept), every app of the last report carried over; the run's budget; a PUBLIC log (workflow + prints)
that stays counts-only."""

import json
import os
from datetime import timedelta

import pytest
import yaml

from admob_iq.engine import audience as eng
from admob_iq.fetch import ga4_audience as ga
from admob_iq.fetch import ga4_audience_probe as ap
from admob_iq.fetch import ga4_uninstall as gu
from tests.audience_synth import E, EMAIL_A, RT_A
from tests.test_ga4_audience import (A1, A2, A3, NOW, PKG, PKG_B, PKG_C, ROOT, SECRETS, SID, _asked, fake,  # noqa: F401
                                     world)

ENV = {"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec", "GA4_REFRESH_TOKENS": json.dumps({EMAIL_A: RT_A})}


def test_the_probe_workflow_keeps_secrets_and_details_off_the_public_log():
    with open(os.path.join(ROOT, ".github", "workflows", "ga4-audience-probe.yml"), encoding="utf-8") as fh:
        text = fh.read()
    wf = yaml.safe_load(text)
    on = wf.get("on", wf.get(True))
    assert set(on) == {"workflow_dispatch"} and set(on["workflow_dispatch"]["inputs"]) == {"max_apps", "apps", "resume"}
    assert on["workflow_dispatch"]["inputs"]["resume"]["type"] == "boolean"
    assert "inputs.apps" not in text                                # never into a step's env / script (both printed)
    assert wf["permissions"] == {"contents": "read"}
    job = wf["jobs"]["probe"]
    assert job["timeout-minutes"] == 30 and ap.BUDGET_SEC < 25 * 60
    steps = job["steps"]
    assert steps[0]["with"]["persist-credentials"] is False
    for st in steps:
        env = st.get("env") or {}
        if st.get("name") == "Run":
            assert st["run"].startswith("python -m admob_iq.fetch.ga4_audience_probe 2>/tmp/")
            assert "details kept off the public log" in st["run"]
            assert env["AUDIENCE_DATA_DIR"] == "_private"
            assert env["AUDIENCE_RESUME"] == "${{ github.event.inputs.resume }}" and "AUDIENCE_APPS" not in env
        else:
            assert not any(k.startswith("GA4_") for k in env), st.get("name")
            assert "secrets.GA4_" not in json.dumps(st)
        if "clone" in (st.get("run") or ""):
            assert "> /dev/null 2>&1" in st["run"] and "@github.com" not in st["run"]
            assert "http.extraheader" in st["run"] and "::add-mask::" in st["run"]


def _main(monkeypatch, root, put, now=NOW, **env):
    monkeypatch.setattr(ap.pr, "write_private", lambda path, text, msg: bool(put.update({path: text})) or True)
    ap.main(dict(ENV, AUDIENCE_DATA_DIR=root, **env), now=now)
    rep = json.loads(put[ap.OUT_PATH])
    os.makedirs(os.path.join(root, "ga4"), exist_ok=True)           # what the next run's private clone holds
    with open(os.path.join(root, ap.OUT_PATH), "w", encoding="utf-8") as f:
        f.write(put[ap.OUT_PATH])
    return rep


def test_the_probe_reads_every_app_derives_its_numbers_and_prints_counts_only(world, monkeypatch, capsys):
    data, pops, f = world
    rep = _main(monkeypatch, os.path.dirname(data), {})
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert all(ln.startswith("audience ") for ln in lines)
    assert lines[0] == "audience probe: 3 app(s) to probe, 0 carried over" and lines[-1] == "audience probe: report written"
    assert lines[-2].startswith("audience probe: apps 3/3 complete, 0 partial, 3 probed now, calls %d, tokens %d, "
                                "flagged 0" % (len(f.bodies), 7 * len(f.bodies)))
    for s in SECRETS + [E.isoformat()]:
        assert s not in out
    assert set(rep["apps"]) == {PKG, PKG_B, PKG_C}
    a = rep["apps"][PKG]
    pop = pops[A1][2]
    assert a["complete"] and a["E"] == E.isoformat() and a["plan"] == ga.plan_calls(E, pop.start)
    assert a["audience"]["by_fsd"] == pop.aud_store()["by_fsd"] and a["calls"] == a["plan"]["calls"] == a["calls_all"]
    assert a["k"] == round(a["tokens"] / a["audience"]["units"], 9) and a["k_prior"] == ga.PRIOR_K
    assert a["derived"]["dead"] == eng.derive_app(pop.aud_store(), pop.uni_store())["dead"]
    assert rep["portfolio"]["apps"] == 3 and rep["counts"]["apps_complete"] == 3
    assert rep["portfolio"]["installs"] == sum(len(p.users) for _, _, p in pops.values())
    assert not os.path.exists(os.path.join(data, "ga4_audience"))          # the probe never writes the data dir


def _event(tmp_path, **inputs):
    p = tmp_path / "event.json"
    p.write_text(json.dumps({"inputs": inputs}))
    return str(p)


@pytest.mark.parametrize("pick", ["package", "key", "app_id"])
def test_the_apps_input_picks_apps_by_package_key_or_app_id_and_the_rest_is_carried(world, monkeypatch, capsys,
                                                                                    tmp_path, pick):
    data, pops, f = world
    root = os.path.dirname(data)
    first = _main(monkeypatch, root, {})
    capsys.readouterr()
    f.bodies.clear()
    want = {"package": PKG.upper(), "key": gu.file_key(A1), "app_id": A1}[pick]
    rep = _main(monkeypatch, root, {}, GITHUB_EVENT_PATH=_event(tmp_path, apps=" %s , nothing.here" % want))
    out = capsys.readouterr().out
    assert "audience probe: apps filter 2 given, 1 matched" in out and PKG not in out and A1 not in out
    assert f.bodies and all(b["dimensionFilter"]["andGroup"]["expressions"][1]["filter"]["stringFilter"]["value"] == SID
                            for _, b in f.bodies)                   # only that app was asked
    assert set(rep["apps"]) == {PKG, PKG_B, PKG_C}                  # the others carried over from the last report
    kept = dict(rep["apps"][PKG_B])
    assert kept.pop("rederived") is True and kept == first["apps"][PKG_B]                 # carried, numbers derived again
    assert rep["counts"]["apps_now"] == 1 and rep["portfolio"]["apps"] == 3


def test_resume_goes_on_with_a_partial_read_and_keeps_complete_apps(world, monkeypatch, capsys, tmp_path):
    data, pops, f = world
    root = os.path.dirname(data)
    f.tokens, f.hourly = 100, {"tokensPerProjectPerHour": 7250}    # the first run: A1 stops part-way (property 1)
    rep = _main(monkeypatch, root, {})
    a = rep["apps"][PKG]
    assert not a["complete"] and a["stopped"] in ("quota_est", "quota_low") and a["progress"]["done"] >= 1
    assert a["audience"]["partial"]["E"] == E.isoformat() and "derived" not in a
    assert rep["counts"]["apps_partial"] >= 1
    done = set(a["audience"]["partial"]["ranges"])
    capsys.readouterr()
    f.bodies.clear()
    f.hour_left, f.hourly = {}, {}                                  # a day later: resume
    rep = _main(monkeypatch, root, {}, now=NOW + timedelta(days=1), AUDIENCE_RESUME="true")
    out = capsys.readouterr().out
    assert "2 carried over" in out and "resuming 1 partial" in out and "1 app(s) to probe" in out
    asked = _asked(f)
    assert asked and not done & set(asked)                          # nothing read twice
    ends = {r["endDate"] for _, b in f.bodies for r in b["dateRanges"]}
    assert ends == {E.isoformat()}                                  # the partial's own E, not the new final day
    assert rep["apps"][PKG]["complete"] and rep["apps"][PKG]["E"] == E.isoformat()


def test_resume_finishes_the_partial_and_derives_it(world, monkeypatch, tmp_path):
    data, pops, f = world
    root = os.path.dirname(data)
    f.tokens, f.hourly = 100, {"tokensPerProjectPerHour": 7250}
    first = _main(monkeypatch, root, {})
    partial = [p for p, a in first["apps"].items() if not a["complete"]]
    assert partial
    f.hour_left, f.hourly = {}, {}
    f.bodies.clear()
    rep = _main(monkeypatch, root, {}, AUDIENCE_RESUME="true")
    assert all(rep["apps"][p]["complete"] for p in (PKG, PKG_B, PKG_C))
    for p in partial:
        a = rep["apps"][p]
        assert a["calls_all"] == first["apps"][p]["calls"] + a["calls"] and "derived" in a
        assert a["audience"]["runs"] == 2 and "partial" not in a["audience"]
    done = {p for p, a in first["apps"].items() if a["complete"]}
    for p in done:
        kept = dict(rep["apps"][p])
        assert kept.pop("rederived") is True and kept == first["apps"][p]    # complete ones carried, not asked again
    assert rep["portfolio"]["apps"] == 3


def test_an_older_reports_complete_app_is_derived_again_into_the_portfolio(world, monkeypatch, tmp_path):
    data, pops, f = world
    root = os.path.dirname(data)
    pop = pops[A2][2]
    legacy = pop.aud_store()                                         # the first probe's store: "store", no months
    for key in ("months", "complete", "v"):
        legacy.pop(key)
    os.makedirs(os.path.join(root, "ga4"))
    with open(os.path.join(root, ap.OUT_PATH), "w", encoding="utf-8") as fh:
        json.dump({"apps": {PKG_B: {"package": PKG_B, "complete": True, "store": legacy, "derived": {"months": {}}}}},
                  fh)
    rep = _main(monkeypatch, root, {}, GITHUB_EVENT_PATH=_event(tmp_path, apps=gu.file_key(A3)),
                AUDIENCE_RESUME="true")
    b = rep["apps"][PKG_B]
    assert b["rederived"] and b["derived"]["dead"] == eng.derive_app(pop.aud_store(), pop.uni_store())["dead"]
    assert rep["portfolio"]["apps"] == 2 and set(rep["apps"]) == {PKG_B, PKG_C}


def test_the_probe_stops_at_its_budget_and_still_writes_what_it_has(world, monkeypatch):
    data, pops, f = world
    units = ap.vr.units_from_state(gu.load_state(data))
    t = iter([0.0] * 6 + [10 ** 6] * 1000)
    rep = ap.run_probe(units, data, "cid", "sec", [(EMAIL_A, RT_A)], now=NOW, clock=lambda: next(t), workers=1)
    assert rep["counts"]["stopped"] >= 1 and any(a.get("stopped") == "budget" for a in rep["apps"].values())
    json.loads(ap.pr._dump(rep))


def test_the_probe_without_credentials_or_routes_exits_before_any_call(world, monkeypatch, tmp_path):
    data, pops, f = world
    with pytest.raises(SystemExit):
        ap.main({"GA4_CLIENT_ID": "cid"}, now=NOW)
    empty = tmp_path / "empty"
    (empty / "data").mkdir(parents=True)
    with pytest.raises(SystemExit):
        ap.main({"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec", "GA4_REFRESH_TOKEN": RT_A,
                 "AUDIENCE_DATA_DIR": str(empty)}, now=NOW)
    assert not f.bodies


def test_event_inputs_are_read_quietly():
    assert ap.event_inputs({}) == {} and ap.event_inputs({"GITHUB_EVENT_PATH": "/nonexistent"}) == {}
    assert ap.wanted(" a , B,,") == {"a", "b"} and ap.wanted(None) == set()
    u = {"package": "com.secret.x", "app_ids": [A2, A3]}
    assert ap.matches(u, {gu.file_key(A3)}) and ap.matches(u, {"com.secret.x"}) and not ap.matches(u, {"zzz"})
