"""💸 Install value Studio — the build step (admob_iq.value_studio_build + its build_static wiring), on a synthetic site
made by the real build code (tests/value_studio_synth.py; no real data):

  * parity: the file holds EXACTLY what the owner-approved demo generator's data step (tests/value_studio_reference.py,
    frozen) makes of the same site — every week array, country, version, long-term row, name, size class and meta value;
  * the contract: the keys, the compact arrays (all NW install weeks long, decodable), the pointer
    dashboard["value"]["studio"] = {file, v}, deterministic bytes (an unchanged build rewrites nothing);
  * nothing trimmed: every app with a file is in it, every week of the grid, every app without GA4;
  * the size guard (≤ 300 KB gzipped for a 40-app portfolio; a hard cap past which the WHOLE file is not written);
  * failure isolation (a broken app costs only that app; any other failure: no file, no pointer, the error TYPE only);
  * the switch (VALUE_STUDIO=false: the site, the dashboard, _headers and the log exactly as without the feature);
  * the public log: ONE counts-only line."""

import copy
import gzip
import hashlib
import json
import os
import re
import shutil

import pytest

from admob_iq import build_static
from admob_iq import value_studio_build as vsb
from admob_iq.config import settings
from tests import value_studio_synth as ss
from tests.value_studio_reference import reference

LINE = re.compile(r"^value studio: apps \d+, skipped \d+, info \d+, no ga4 \d+, kb \d+$")
WEEK = ('n', 'sp', 'sr', 'na', 'jo', 'q', 'pp', 'plo', 'phi', 'pf', 'p365')
CHECK = ('v', 'lo', 'hi')


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    return ss.make_site(str(tmp_path_factory.mktemp("vstudio")))


@pytest.fixture
def site(base, tmp_path):
    """A fresh copy of the module's synthetic site (each test may change it) → (site, cfg, dashboard)."""
    return ss.copy_site(*base, str(tmp_path))


def _gz(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def _run(site, cfg, dash, **kw):
    s = dict(settings(), **kw)
    return build_static._value_studio_step(dash, os.path.join(os.path.dirname(cfg), "data"), site, s)


def _names(cfg):
    return (json.load(open(os.path.join(cfg, "account_names.json"))), json.load(open(os.path.join(cfg, "app_names.json"))))


# ── parity with the approved demo ─────────────────────────────────────────────────────────────────────────────────

def test_the_file_holds_exactly_the_demo_generators_numbers(site, capsys):
    s, cfg, dash = site
    ref = reference(s)                                         # the frozen demo step, reading the site's files
    assert ref["apps"] and ref["noga"]
    assert _run(s, cfg, dash) == ["/value_studio.json.gz"]
    body = _gz(os.path.join(s, vsb.FILE))
    assert body.pop("v") == vsb.V
    assert body == ref
    got = vsb.build_data(dash, lambda n: _gz(os.path.join(s, n)), *_names(cfg))   # the module's own entry point
    assert got == ref


def test_the_synthetic_site_covers_the_studios_cases(site):
    s, cfg, dash = site
    ref = reference(s)
    assert [a["nm"] for a in ref["apps"]] == ["Demo Organic App · Studio Two", "Demo Spend App (2025 wala) · Studio Two",
                                              "Demo Young App · Studio Two"]   # with the account, the same-name tag
    org, spend, young = ref["apps"]
    assert spend["store"] == "Demo Spend App (2025 wala)" and spend["acc"] == "Studio Two"
    assert [a["sz"] for a in ref["apps"]] == ["madhyam", "badi", "chhoti"]
    assert sorted((n["store"], n["acc"]) for n in ref["noga"]) == [("Demo Clock", "A/c 3003"), ("Demo Spend App", "Studio Two")]
    assert set(spend["j"]) == {"1"} and set(org["j"]) == {"0"} and "1" in young["j"]          # judged / organic / young
    assert spend["cty"]["geo"] and not org["cty"]["geo"]       # Google Ads cost by country on the ads app
    assert spend["ver"]["r"] and spend["lng"]["k"] and spend["spd"]
    assert [r[1] for r in spend["rel"]] == ["v2.2", "v2.3"]    # 📦 its two updates
    assert org["info"] and dash["value"]["alerts"]              # engine info in the file; the alerts stay in DATA


# ── the contract ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_contract_pointer_and_deterministic_bytes(site, capsys):
    s, cfg, dash = site
    _run(s, cfg, dash)
    p = os.path.join(s, vsb.FILE)
    body = _gz(p)
    assert set(body) == {"v", "meta", "apps", "noga"}
    M = body["meta"]
    assert set(M) == {"SW", "EW", "nw", "today", "gen", "fx", "H", "settled", "spendTill", "T", "alerts", "closed",
                      "alertCounts", "apps", "consts"}
    assert M["nw"] == vsb.NW and M["T"] == vsb.T and M["apps"] == len(body["apps"]) and M["fx"] == ss.FX
    assert M["today"] == dash["today_date"] and M["gen"] == dash["generated_at"] and M["H"] == 90
    assert vsb.diff(M["SW"], M["EW"]) == 7 * (vsb.NW - 1)
    for a in body["apps"]:
        assert set(a) == {"id", "k", "nm", "store", "acc", "sz", "paisa", "settled", "spT", "revT", "fxL", "j", "why",
                          "rel", "spd", "cty", "ver", "lng", "eng", "info", "chk"} | set(WEEK) | set(CHECK)
        for k in WEEK:
            arr = vsb.dec(a[k])
            assert len(arr) == vsb.NW and vsb.enc(arr) == a[k] and all(v is None or isinstance(v, int) for v in arr)
        for k in CHECK:
            assert len(vsb.dec(a[k])) == vsb.NW * len(vsb.T)
        assert len(a["j"]) == len(a["why"]) == vsb.NW
        assert a["sz"] in ("badi", "madhyam", "chhoti") and a["nm"].endswith(" · " + a["acc"])   # always with its account
        for x in a["info"]:
            assert len(x) == 6 and "100 me" not in x[5]
    ptr = dash["value"]["studio"]
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    assert ptr == {"file": vsb.FILE, "v": hashlib.sha1(raw).hexdigest()[:12]}
    b1, m1 = open(p, "rb").read(), os.stat(p).st_mtime_ns
    dash2 = json.loads(json.dumps(dash))
    dash2["value"].pop("studio")
    _run(s, cfg, dash2)                                        # the same inputs again: nothing rewritten
    assert open(p, "rb").read() == b1 and os.stat(p).st_mtime_ns == m1 and dash2["value"]["studio"] == ptr


def test_nothing_is_trimmed(site, capsys):
    s, cfg, dash = site
    _run(s, cfg, dash)
    body = _gz(os.path.join(s, vsb.FILE))
    ok = [r["app_id"] for r in dash["value"]["apps"] if r.get("status") == "ok" and r.get("file")]
    assert sorted(a["id"] for a in body["apps"]) == sorted(ok)
    assert sorted(n["id"] for n in body["noga"]) == sorted(x["app_id"] for x in dash["value"]["no_ga4"])
    assert sum(len(a["info"]) for a in body["apps"]) == len(dash["value"]["info"])
    for a in body["apps"]:
        f = _gz(os.path.join(s, next(r["file"] for r in dash["value"]["apps"] if r["app_id"] == a["id"])))
        n = vsb.dec(a["n"])
        got = {vsb.add(body["meta"]["SW"], 7 * i): v for i, v in enumerate(n) if v is not None}
        want = {w["from"]: round(w["n"]) for w in f["weeks"] if w["from"] >= body["meta"]["SW"]}
        assert got == want                                     # every week of the grid the app has


def test_headers_keep_the_file_out_of_stale_caches(site, capsys):
    s, cfg, dash = site
    extra = _run(s, cfg, dash)
    txt = build_static.headers_text(["uninstall.json.gz"], dash, extra=extra)
    assert "/value_studio.json.gz\n  Cache-Control: no-store\n\n" in txt
    assert txt.index("/value_studio.json.gz") < txt.index("/index.html")


# ── the size guard ────────────────────────────────────────────────────────────────────────────────────────────────

def _grow(s, dash, n):
    """The site's Install value apps copied to n apps (new ids / keys / files) — a big portfolio's size."""
    base = [r for r in dash["value"]["apps"] if r.get("file")]
    out = []
    for i in range(n):
        r = copy.deepcopy(base[i % len(base)])
        key = "%012x" % (0xabc000000000 + i)
        shutil.copyfile(os.path.join(s, r["file"]), os.path.join(s, "value_%s.json.gz" % key))
        r.update(key=key, file="value_%s.json.gz" % key, app_id=r["app_id"] + "%03d" % i, app="Grow %d" % i)
        out.append(r)
    dash["value"]["apps"] = out


def test_a_40_app_portfolio_stays_under_300_kb(site, capsys):
    s, cfg, dash = site
    _grow(s, dash, 40)
    _run(s, cfg, dash)
    line = capsys.readouterr().err.strip()
    assert LINE.match(line) and line.startswith("value studio: apps 40, skipped 0,")
    assert os.path.getsize(os.path.join(s, vsb.FILE)) <= 300 * 1024
    assert len(_gz(os.path.join(s, vsb.FILE))["apps"]) == 40   # (never a part of them)


def test_past_the_hard_cap_nothing_is_written(site, monkeypatch, capsys):
    s, cfg, dash = site
    _run(s, cfg, dash)
    capsys.readouterr()
    monkeypatch.setattr(vsb, "MAX_GZ", 1000)
    d2 = json.loads(json.dumps(dash))
    assert _run(s, cfg, d2) == []
    assert not os.path.exists(os.path.join(s, vsb.FILE)) and "studio" not in d2["value"]
    assert re.match(r"^value studio: too big \(\d+ kb\), not written$", capsys.readouterr().err.strip())


# ── failure isolation ─────────────────────────────────────────────────────────────────────────────────────────────

def test_a_broken_app_costs_only_that_app(site, capsys):
    s, cfg, dash = site
    r = next(x for x in dash["value"]["apps"] if x["app"] == "Demo Young App")
    with open(os.path.join(s, r["file"]), "wb") as f:
        f.write(b"broken")
    assert _run(s, cfg, dash) == ["/value_studio.json.gz"]
    body = _gz(os.path.join(s, vsb.FILE))
    assert len(body["apps"]) == 2 and r["app_id"] not in {a["id"] for a in body["apps"]}
    assert ", skipped 1," in capsys.readouterr().err


def test_an_app_whose_data_breaks_midway_costs_only_that_app(site, capsys):
    s, cfg, dash = site
    r = next(x for x in dash["value"]["apps"] if x["app"] == "Demo Organic App")
    f = _gz(os.path.join(s, r["file"]))
    max(f["weeks"], key=lambda w: w["from"])["rpi"] = 5       # its newest week malformed (earnings not a list)
    with gzip.open(os.path.join(s, r["file"]), "wt", encoding="utf-8") as g:
        json.dump(f, g)
    _run(s, cfg, dash)
    body = _gz(os.path.join(s, vsb.FILE))
    assert r["app_id"] not in {a["id"] for a in body["apps"]} and len(body["apps"]) == 2
    assert ", skipped 1," in capsys.readouterr().err


@pytest.mark.parametrize("how", ["dashboard", "raise"])
def test_any_other_failure_costs_the_studio_only(site, monkeypatch, capsys, how):
    s, cfg, dash = site
    _run(s, cfg, dash)                                         # an older file + pointer exist
    capsys.readouterr()
    d2 = json.loads(json.dumps(dash))
    if how == "dashboard":
        d2.pop("today_date")
    else:
        monkeypatch.setattr(vsb, "build_data", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret-app-name")))
    before = {n: open(os.path.join(s, n), "rb").read() for n in os.listdir(s) if n != vsb.FILE}
    assert _run(s, cfg, d2) == []
    assert "studio" not in d2["value"] and not os.path.exists(os.path.join(s, vsb.FILE))
    err = capsys.readouterr().err.strip()
    assert re.match(r"^value studio skipped: [A-Za-z]+$", err) and "secret" not in err
    assert {n: open(os.path.join(s, n), "rb").read() for n in os.listdir(s)} == before   # nothing else touched
    d2.pop("value"), dash.pop("value")
    if how == "dashboard":
        dash.pop("today_date")
    assert d2 == dash


def test_a_build_without_install_value_data_leaves_no_studio_file(site, capsys):
    s, cfg, dash = site
    _run(s, cfg, dash)
    capsys.readouterr()
    d2 = {k: v for k, v in dash.items() if k != "value"}
    assert _run(s, cfg, d2) == [] and not os.path.exists(os.path.join(s, vsb.FILE))
    assert capsys.readouterr().err == "" and "value" not in d2


# ── the switch ────────────────────────────────────────────────────────────────────────────────────────────────────

def _snap(d):
    return {n: open(os.path.join(d, n), "rb").read() for n in sorted(os.listdir(d))}


def test_switched_off_the_site_is_exactly_as_without_the_feature(site, capsys):
    s, cfg, dash = site
    without = _snap(s)                                         # the value step's own output, as HEAD writes it
    d_without = copy.deepcopy(dash)
    h_without = build_static.headers_text(["uninstall.json.gz"], d_without, extra=[])
    capsys.readouterr()
    paths = _run(s, cfg, dash, value_studio=False)
    assert paths == [] and capsys.readouterr().err == ""
    assert _snap(s) == without and dash == d_without
    assert build_static.headers_text(["uninstall.json.gz"], dash, extra=paths) == h_without
    d_on = copy.deepcopy(d_without)                            # switched off later: the file and the pointer go
    _run(s, cfg, d_on)
    assert os.path.exists(os.path.join(s, vsb.FILE))
    capsys.readouterr()
    d_off = copy.deepcopy(d_without)
    _run(s, cfg, d_off, value_studio=False)
    assert _snap(s) == without and d_off == d_without and capsys.readouterr().err == ""


def test_the_workflow_passes_the_switch(monkeypatch):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        y = f.read()
    assert "VALUE_STUDIO:         ${{ vars.VALUE_STUDIO || 'true' }}" in y
    monkeypatch.delenv("VALUE_STUDIO", raising=False)
    assert settings()["value_studio"] is True
    monkeypatch.setenv("VALUE_STUDIO", "false")
    assert settings()["value_studio"] is False


def test_build_static_runs_the_step_after_the_value_step_and_before_the_dashboard_is_written():
    src = open(build_static.__file__, encoding="utf-8").read()
    body = src[src.index("def build("):]
    i_uni, i_st = body.index("_uninstall_with_revenue("), body.index("vstudio_paths = _value_studio_step(")
    i_dash, i_hdr = body.index('_shipgz(out_dir, "dashboard.json", dashboard)'), body.index("+ vstudio_paths + ")
    assert i_uni < i_st < i_dash < i_hdr


# ── the public log ────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_log_is_one_counts_only_line(site, capsys):
    s, cfg, dash = site
    _run(s, cfg, dash)
    err = capsys.readouterr().err
    lines = err.strip().splitlines()
    assert len(lines) == 1 and LINE.match(lines[0]), err
    assert lines[0] == "value studio: apps 3, skipped 0, info %d, no ga4 2, kb %d" % (
        len(dash["value"]["info"]), int(lines[0].rsplit(" ", 1)[1]))
    from tests import value_synth as vs
    for secret in list(ss.NAMES.values()) + [p for _, _, p, _ in vs.FIX_APPS] + [ss.P1, ss.P2, "Studio Two"]:
        assert secret not in err
