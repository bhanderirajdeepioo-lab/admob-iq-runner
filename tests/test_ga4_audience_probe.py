"""GA4 Audience one-off probe (admob_iq.fetch.ga4_audience_probe + .github/workflows/ga4-audience-probe.yml) — offline,
synthetic users only: every app fetched once with the build's own fetch, its numbers derived, one private report written,
the run's budget, and a PUBLIC log (workflow + prints) that stays counts-only."""

import json
import os

import pytest
import yaml

from admob_iq.engine import audience as eng
from admob_iq.fetch import ga4_audience as ga
from admob_iq.fetch import ga4_audience_probe as ap
from admob_iq.fetch import ga4_uninstall as gu
from tests.audience_synth import E, EMAIL_A, RT_A
from tests.test_ga4_audience import A1, NOW, PKG, PKG_B, PKG_C, ROOT, SECRETS, fake, world  # noqa: F401 (fixtures)


def test_the_probe_workflow_keeps_secrets_and_details_off_the_public_log():
    with open(os.path.join(ROOT, ".github", "workflows", "ga4-audience-probe.yml"), encoding="utf-8") as fh:
        wf = yaml.safe_load(fh)
    on = wf.get("on", wf.get(True))
    assert set(on) == {"workflow_dispatch"} and set(on["workflow_dispatch"]["inputs"]) == {"max_apps"}
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
        else:
            assert not any(k.startswith("GA4_") for k in env), st.get("name")
            assert "secrets.GA4_" not in json.dumps(st)
        if "clone" in (st.get("run") or ""):
            assert "> /dev/null 2>&1" in st["run"] and "@github.com" not in st["run"]
            assert "http.extraheader" in st["run"] and "::add-mask::" in st["run"]


def test_the_probe_fetches_every_app_derives_its_numbers_and_prints_counts_only(world, monkeypatch, capsys):
    data, pops, f = world
    root = os.path.dirname(data)
    put = {}
    monkeypatch.setattr(ap.pr, "write_private", lambda path, text, msg: bool(put.update({path: text})) or True)
    env = {"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec", "GA4_REFRESH_TOKENS": json.dumps({EMAIL_A: RT_A}),
           "AUDIENCE_DATA_DIR": root}
    ap.main(env, now=NOW)
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert all(ln.startswith("audience ") for ln in lines)
    assert lines[0] == "audience probe: 3 app(s) to probe" and lines[-1] == "audience probe: report written"
    assert lines[-2].startswith("audience probe: apps 3/3 complete, calls %d, tokens %d, flagged 0" % (
        len(f.bodies), 7 * len(f.bodies)))
    for s in SECRETS + [E.isoformat()]:
        assert s not in out
    rep = json.loads(put[ap.OUT_PATH])
    assert set(rep["apps"]) == {PKG, PKG_B, PKG_C}
    a = rep["apps"][PKG]
    pop = pops[A1][2]
    assert a["complete"] and a["E"] == E.isoformat() and a["plan"] == ga.plan_calls(E, pop.start)
    assert a["store"]["by_fsd"] == pop.aud_store()["by_fsd"] and a["calls"] == a["plan"]["calls"]
    assert a["derived"]["dead"] == eng.derive_app(pop.aud_store(), pop.uni_store())["dead"]
    assert rep["portfolio"]["apps"] == 3 and rep["counts"]["apps_complete"] == 3
    assert rep["portfolio"]["installs"] == sum(len(p.users) for _, _, p in pops.values())
    assert not os.path.exists(os.path.join(data, "ga4_audience"))          # the probe never writes the data dir


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
