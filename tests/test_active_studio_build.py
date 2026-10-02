"""🧭 Active users Studio — the build step (admob_iq.active_studio_build + its build_static wiring), on synthetic sites made
by the real build code (tests/active_studio_synth.py; no real data):

  * parity: the file holds EXACTLY what the owner-approved demo generator's data step (tests/active_studio_reference.py,
    frozen) makes of the same site — every array, noise grid, alert, size class, name and meta value;
  * the contract: the keys, the compact arrays (all SPAN days long, decodable), the alert / app links, the pointer
    dashboard["active"]["studio"] = {file, v}, deterministic bytes (an unchanged build rewrites nothing);
  * the size guard (≤ 300 KB gzipped for a 40-app portfolio; a hard cap past which no file is written — the data is
    never trimmed to fit);
  * failure isolation (a broken app costs only that app; any other failure: no file, no pointer, the error TYPE only);
  * the switch (ACTIVE_STUDIO=false: the site, the dashboard, _headers and the log exactly as without the feature);
  * the public log: ONE counts-only line."""

import copy
import gzip
import hashlib
import json
import math
import os
import re
import shutil
from datetime import date, timedelta

import pytest

from admob_iq import active_studio_build as asb
from admob_iq import build_static
from admob_iq.config import settings
from tests import active_studio_synth as ss
from tests.active_studio_reference import reference

LINE = re.compile(r"^active studio: apps \d+, skipped \d+, alerts \d+, no ga4 \d+, kb \d+$")
KEYS = ('a1', 'nw', 'rt', 'y', 'd1', 'd7', 'd30', 'rv', 'u', 'su', 'tu', 'im')


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("astudio"))
    site, cfg, dash = ss.make_site(root)
    return site, cfg, dash


@pytest.fixture
def site(base, tmp_path):
    """A fresh copy of the module's synthetic site (each test may change it) → (site, cfg, dashboard)."""
    s0, c0, d0 = base
    site, cfg = str(tmp_path / "site"), str(tmp_path / "config")
    shutil.copytree(s0, site)
    shutil.copytree(c0, cfg)
    return site, cfg, copy.deepcopy(d0)


def _gz(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def _wgz(p, body):
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump(body, f)


def _run(site, cfg, dash, **kw):
    s = dict(settings(), **kw)
    return build_static._active_studio_step(dash, os.path.join(os.path.dirname(cfg), "data"), site, s)


def _ref(s):
    return json.loads(json.dumps(reference(s)))                   # (as the file holds it: tuples → lists)


# ── parity with the approved demo ─────────────────────────────────────────────────────────────────────────────────

def _half(p):
    """the engine's share ×1000 lands exactly on .5 (its 4 decimals): the demo rounds it half-to-even, the page half up"""
    return abs(round(p * 1000, 6) - int(round(p * 1000, 6)) - 0.5) < 1e-9


def _beyond_the_demo(s, body, ref):
    """The owner's "no trim" (2 Oct) goes past the frozen demo here only: the "How many came back" grid has EVERY install
    week since the app's start (the demo: the 10 newest with numbers — they are rows of it, the same dates, installs
    and ⏳ bits), its cells rounded half up as the older table prints them (0.0545 → "5.5%"; the demo: half to even, so
    an exact .5 may read 1‰ lower there), and the 📦 updates reach back before the span (the demo: inside it — the same
    rows there). Checked here, then put back to the demo's, so the rest is compared whole."""
    S, E = ref["meta"]["S"], ref["meta"]["E"]
    for a, r in zip(body["apps"], ref["apps"]):
        assert a["id"] == r["id"]
        eng = {x["from"]: x for x in _gz(os.path.join(s, "active_%s.json.gz" % a["k"]))["tri"]["rows"] if not x.get("pre")}
        mine = {w[0]: w for w in a["tri"]["w"]}
        assert len(a["tri"]["w"]) >= len(r["tri"]["w"])
        for w in r["tri"]["w"]:
            m = mine[w[0]]
            assert m[1:3] == w[1:3] and m[4] == w[4]
            for k, (x, y) in enumerate(zip(asb.dec(m[3]), asb.dec(w[3]))):
                assert x == y or (x == y + 1 and _half(eng[w[0]]["v"][asb.TRI_COLS[k]])), (a["nm"], w[0], k)
        for x, y in zip(asb.dec(a["tri"]["ref"]), asb.dec(r["tri"]["ref"])):
            assert x == y or x == y + 1
        assert [x for x in a["rel"] if S <= x[0] <= E] == r["rel"] and all(x[0] <= E for x in a["rel"])
        a["tri"], a["rel"] = r["tri"], r["rel"]
    return body


def test_the_file_holds_exactly_the_demo_generators_numbers(site, capsys):
    s, cfg, dash = site
    ref = _ref(s)                                               # the frozen demo step, reading the site's files
    assert ref["apps"] and ref["alerts"] and ref["noga"]        # (the synthetic site exercises all of it)
    assert _run(s, cfg, dash) == ["/active_studio.json.gz"]
    body = _gz(os.path.join(s, asb.FILE))
    assert body.pop("v") == asb.V
    assert any(len(a["tri"]["w"]) > 10 for a in body["apps"])
    assert _beyond_the_demo(s, body, ref) == ref
    # and the module's own entry point, straight
    got = asb.build_data(dash, _gz(os.path.join(s, "active_portfolio.json.gz")), lambda n: _gz(os.path.join(s, n)),
                         json.load(open(os.path.join(cfg, "account_names.json"))),
                         json.load(open(os.path.join(cfg, "app_names.json"))),
                         asb._lag(dash, s))
    assert _beyond_the_demo(s, json.loads(json.dumps(got)), ref) == ref


# ── no trim: "How many new users came back" = every install week since the app's start (owner, 2 Oct) ─────────────

def test_the_came_back_grid_has_every_install_week_of_the_older_table(site, capsys):
    """Every week the older "How many came back" table shows (the engine's tri rows without the hidden test installs),
    newest first, none skipped — also a week whose day 1 is not reached yet and a week GA4 gave no return data for
    ("No data", flag 1); part data = flag 2, GA4's old limit unchecked = flag 4; each cell = the engine's share ×1000,
    half up (as the older table prints it)."""
    s, cfg, dash = site
    a0 = next(a for a in _gz(os.path.join(s, "active_portfolio.json.gz"))["apps"])
    key = next(r["key"] for r in dash["active"]["apps"] if r["app_id"] == a0["app_id"])
    af = _gz(os.path.join(s, "active_%s.json.gz" % key))
    nd = af["tri"]["rows"][5]
    nd.update(nodata=True, q=True)                             # a week GA4 gave no return data for
    _wgz(os.path.join(s, "active_%s.json.gz" % key), af)
    _run(s, cfg, dash)
    body = _gz(os.path.join(s, asb.FILE))
    n_old = 0
    for a in body["apps"]:
        eng = sorted((x for x in _gz(os.path.join(s, "active_%s.json.gz" % a["k"]))["tri"]["rows"] if not x.get("pre")),
                     key=lambda x: x["from"], reverse=True)
        W = a["tri"]["w"]
        assert [(w[0], w[1], w[2]) for w in W] == [(x["from"], x["to"], x["users"]) for x in eng], a["nm"]
        n_old += max(0, len(W) - 10)
        for w, x in zip(W, eng):
            fl = (1 if x.get("nodata") else 0) | (2 if x.get("part") else 0) | (4 if x.get("q") else 0)
            assert (w[5] if len(w) == 6 else 0) == fl
            v = asb.dec(w[3])
            for k, N in enumerate(asb.TRI_COLS):
                p = None if x.get("nodata") else (x.get("v") or [None] * 31)[N]
                assert v[k] == (None if p is None else int(math.floor(round(p * 1000, 6) + 0.5)))
            if x.get("nodata"):
                assert v == [None] * len(asb.TRI_COLS) and w[4] == 0
    assert n_old > 60
    a = next(x for x in body["apps"] if x["k"] == key)
    w = next(w for w in a["tri"]["w"] if w[0] == nd["from"])
    assert w[5] == 1 | 4 | (2 if nd.get("part") else 0)
    assert asb._k1000(0.0545) == 55 and asb._k1000(0.0085) == 9 and asb._k1000(0.1) == 100


def test_every_update_reaches_the_grid_even_before_the_span(site, capsys):
    s, cfg, dash = site
    r0 = next(r for r in dash["active"]["apps"] if r.get("file") and r.get("status") != "error")
    af = _gz(os.path.join(s, r0["file"]))
    old_day = (date.fromisoformat(af["daily"]["start"]) + timedelta(days=12)).isoformat()
    af["releases"] = [{"date": old_day, "version": "0.9"}, {"date": "2099-01-01", "version": "9.9"}] + (af.get("releases") or [])
    _wgz(os.path.join(s, r0["file"]), af)
    _run(s, cfg, dash)
    body = _gz(os.path.join(s, asb.FILE))
    a = next(x for x in body["apps"] if x["id"] == r0["app_id"])
    assert old_day < body["meta"]["S"] and [old_day, "v0.9", None, False] in a["rel"]
    assert all(x[0] <= body["meta"]["E"] for x in a["rel"])


def test_the_synthetic_site_covers_the_studios_cases(site):
    s, cfg, dash = site
    ref = _ref(s)
    nm = [a["nm"] for a in ref["apps"]]
    assert nm == ["Demo Notes · Studio One", "Demo Photos (2025 wala) · Studio One", "Demo Torch · A/c 4004",
                  "Demo Young · A/c 4004"]                     # names with the account, the same-name tag, never cut
    assert [a["sz"] for a in ref["apps"]] == ["madhyam", "badi", "chhoti", "chhoti"]
    assert {(x["sev"], x["m"], x["kind"]) for x in ref["alerts"]} >= {("bigda", "ret_dau", "open"), ("behtar", "ret_dau", "open"),
                                                                    ("normal", "ret_dau", "info")}
    assert all(x["at"] for x in ref["alerts"] if x["kind"] == "open")   # every alert carries its alert time
    assert sorted(n["nm"] for n in ref["noga"]) == ["Demo Clock · A/c 4004", "Demo Photos · Studio One"]
    assert ref["apps"][1]["rel"] and ref["apps"][1]["rel"][0][1] == "v2.1"
    young = ref["apps"][3]
    assert asb.dec(young["nw"]).count(None) > 100              # 60 days of history inside the 180-day span
    assert all(any(v is not None for v in a["nz"]["t"]) for a in ref["apps"][:3])   # the noise grid ("pakka") is there


# ── the contract ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_contract_pointer_and_deterministic_bytes(site, capsys):
    s, cfg, dash = site
    _run(s, cfg, dash)
    p = os.path.join(s, asb.FILE)
    body = _gz(p)
    assert set(body) == {"v", "meta", "apps", "alerts", "noga"}
    M = body["meta"]
    assert set(M) == {"S", "E", "n", "today", "gen", "fx", "actLate", "lag", "settled", "apps", "LG", "bandDays", "triCols",
                      "pfSettled", "mk"}
    assert M["n"] == asb.SPAN and M["LG"] == asb.LG and M["triCols"] == asb.TRI_COLS and M["apps"] == len(body["apps"])
    assert M["fx"] == ss.FX and M["today"] == dash["today_date"] and M["gen"] == dash["generated_at"]
    for a in body["apps"]:
        assert set(a) == {"id", "k", "nm", "store", "acc", "sz", "paisa", "first", "settled", "dt", "stage", "ready", "rs", "vs",
                          "est", "pkg", "K", "sh", "nz", "u1", "u7", "tst", "steep", "pre", "bnd", "rel", "tri", "al"} | set(KEYS)
        for k in KEYS:
            arr = asb.dec(a[k])
            assert len(arr) == asb.SPAN and asb.enc(arr) == a[k]
            assert all(v is None or isinstance(v, int) for v in arr)
        assert len(asb.dec(a["pre"])) == 31 and a["pkg"] == ""          # (never a package name)
        assert all(len(asb.dec(a["bnd"][k])) == asb.BAND_DAYS for k in ("lo", "hi", "med"))
        assert set(a["nz"]) == {"t", "a", "se", "tm", "rv", "ad"} and all(len(v) == len(asb.LG) for v in a["nz"].values())
        assert a["sz"] in ("badi", "madhyam", "chhoti")
        assert a["nm"].endswith(" · " + a["acc"])                       # always with its account
        assert len(asb.dec(a["tri"]["ref"])) == len(asb.TRI_COLS)
        for w in a["tri"]["w"]:
            assert len(w) in (5, 6) and len(asb.dec(w[3])) == len(asb.TRI_COLS) and (len(w) == 5 or w[5] in range(1, 8))
    for x in body["alerts"]:
        assert 0 <= x["a"] < len(body["apps"]) and x["sev"] in ("bigda", "dhyan", "behtar", "normal")
        assert x["kind"] in ("open", "closed", "info")
    ptr = dash["active"]["studio"]
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    assert ptr == {"file": asb.FILE, "v": hashlib.sha1(raw).hexdigest()[:12]}
    b1, m1 = open(p, "rb").read(), os.stat(p).st_mtime_ns
    dash2 = json.loads(json.dumps(dash))
    dash2["active"].pop("studio")
    _run(s, cfg, dash2)                                         # the same inputs again: nothing rewritten
    assert open(p, "rb").read() == b1 and os.stat(p).st_mtime_ns == m1 and dash2["active"]["studio"] == ptr


def test_headers_keep_the_file_out_of_stale_caches(site, capsys):
    s, cfg, dash = site
    extra = _run(s, cfg, dash)
    txt = build_static.headers_text(["uninstall.json.gz"], dash, extra=extra)
    assert "/active_studio.json.gz\n  Cache-Control: no-store\n\n" in txt
    assert txt.index("/active_studio.json.gz") < txt.index("/index.html")


# ── the size guard (never a trimmed file) ─────────────────────────────────────────────────────────────────────────

def _grow(s, dash, n):
    """The site's GA4 apps copied to n apps (new ids / keys / files, their daily slices too) — a big portfolio's size."""
    A = dash["active"]
    base = [r for r in A["apps"] if r.get("file")]
    PF = _gz(os.path.join(s, "active_portfolio.json.gz"))
    pf_by = {a["app_id"]: a for a in PF["apps"]}
    rows, pfa = [], []
    for i in range(n):
        r = copy.deepcopy(base[i % len(base)])
        key = "%012x" % (0xabc000000000 + i)
        shutil.copyfile(os.path.join(s, r["file"]), os.path.join(s, "active_%s.json.gz" % key))
        p = copy.deepcopy(pf_by[r["app_id"]])
        r.update(key=key, file="active_%s.json.gz" % key, app_id=r["app_id"] + "%03d" % i, app="Grow %d" % i)
        p["app_id"] = r["app_id"]
        rows.append(r)
        pfa.append(p)
    A["apps"], PF["apps"] = rows, pfa
    _wgz(os.path.join(s, "active_portfolio.json.gz"), PF)


def test_a_40_app_portfolio_stays_under_300_kb_with_nothing_dropped(site, capsys):
    s, cfg, dash = site
    _grow(s, dash, 40)
    _run(s, cfg, dash)
    line = capsys.readouterr().err.strip()
    assert LINE.match(line) and line.startswith("active studio: apps 40, skipped 0,")
    assert os.path.getsize(os.path.join(s, asb.FILE)) <= 300 * 1024
    assert len(_gz(os.path.join(s, asb.FILE))["apps"]) == 40     # every app, every day: no sampling, no cap


def test_past_the_hard_cap_nothing_is_written(site, monkeypatch, capsys):
    s, cfg, dash = site
    _run(s, cfg, dash)
    capsys.readouterr()
    monkeypatch.setattr(asb, "MAX_GZ", 1000)
    d2 = json.loads(json.dumps(dash))
    assert _run(s, cfg, d2) == []
    assert not os.path.exists(os.path.join(s, asb.FILE)) and "studio" not in d2["active"]
    assert re.match(r"^active studio: too big \(\d+ kb\), not written$", capsys.readouterr().err.strip())


# ── failure isolation ─────────────────────────────────────────────────────────────────────────────────────────────

def test_a_broken_app_costs_only_that_app(site, capsys):
    s, cfg, dash = site
    rows = [r for r in dash["active"]["apps"] if r.get("file")]
    with open(os.path.join(s, rows[1]["file"]), "wb") as f:
        f.write(b"broken")
    assert _run(s, cfg, dash) == ["/active_studio.json.gz"]
    body = _gz(os.path.join(s, asb.FILE))
    assert len(body["apps"]) == 3 and rows[1]["app_id"] not in {a["id"] for a in body["apps"]}
    assert all(0 <= x["a"] < 3 for x in body["alerts"])          # its alerts never point at a missing app
    assert ", skipped 1," in capsys.readouterr().err


def test_an_app_without_its_daily_slice_keeps_its_own_file_numbers(site, capsys):
    s, cfg, dash = site
    PF = _gz(os.path.join(s, "active_portfolio.json.gz"))
    gone = PF["apps"].pop(2)["app_id"]
    _wgz(os.path.join(s, "active_portfolio.json.gz"), PF)
    _run(s, cfg, dash)
    body = _gz(os.path.join(s, asb.FILE))
    a = next(x for x in body["apps"] if x["id"] == gone)
    assert set(asb.dec(a["rt"])) == {None} and any(v is not None for v in asb.dec(a["y"]))   # (the generator's own rule)
    ref = _ref(s)
    assert body.pop("v") == asb.V and _beyond_the_demo(s, body, ref) == ref


@pytest.mark.parametrize("how", ["portfolio", "raise"])
def test_any_other_failure_costs_the_studio_only(site, monkeypatch, capsys, how):
    s, cfg, dash = site
    _run(s, cfg, dash)                                          # an older file + pointer exist
    capsys.readouterr()
    d2 = json.loads(json.dumps(dash))
    if how == "portfolio":
        with open(os.path.join(s, "active_portfolio.json.gz"), "wb") as f:
            f.write(b"\x1f\x8bbroken")
    else:
        monkeypatch.setattr(asb, "build_data", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret-app-name")))
    before = {n: open(os.path.join(s, n), "rb").read() for n in os.listdir(s) if n != asb.FILE}
    assert _run(s, cfg, d2) == []
    assert "studio" not in d2["active"] and not os.path.exists(os.path.join(s, asb.FILE))
    err = capsys.readouterr().err.strip()
    assert re.match(r"^active studio skipped: [A-Za-z]+$", err) and "secret" not in err
    assert {n: open(os.path.join(s, n), "rb").read() for n in os.listdir(s)} == before   # nothing else touched
    d2.pop("active"), dash.pop("active")
    assert d2 == dash


def test_a_build_without_active_users_data_leaves_no_studio_file(site, capsys):
    s, cfg, dash = site
    _run(s, cfg, dash)
    capsys.readouterr()
    d2 = {k: v for k, v in dash.items() if k != "active"}
    assert _run(s, cfg, d2) == [] and not os.path.exists(os.path.join(s, asb.FILE))
    assert capsys.readouterr().err == "" and "active" not in d2
    d3 = json.loads(json.dumps(dash))                            # the All-apps daily file off this build
    d3["active"].pop("studio", None)
    d3["active"]["portfolio"] = None
    assert _run(s, cfg, d3) == [] and not os.path.exists(os.path.join(s, asb.FILE)) and "studio" not in d3["active"]
    assert capsys.readouterr().err.strip() == "active studio: apps 0, skipped 0, alerts 0, no ga4 0, kb 0"


# ── the switch ────────────────────────────────────────────────────────────────────────────────────────────────────

def _snap(d):
    return {n: open(os.path.join(d, n), "rb").read() for n in sorted(os.listdir(d))}


def test_switched_off_the_site_is_exactly_as_without_the_feature(site, capsys):
    s, cfg, dash = site
    without = _snap(s)                                          # the Uninstall step's own output, as HEAD writes it
    d_without = copy.deepcopy(dash)
    h_without = build_static.headers_text(["uninstall.json.gz"], d_without, extra=[])
    capsys.readouterr()
    paths = _run(s, cfg, dash, active_studio=False)
    assert paths == [] and capsys.readouterr().err == ""
    assert _snap(s) == without and dash == d_without
    assert build_static.headers_text(["uninstall.json.gz"], dash, extra=paths) == h_without
    # switched off later: the file and the pointer go
    d_on = copy.deepcopy(d_without)
    _run(s, cfg, d_on)
    assert os.path.exists(os.path.join(s, asb.FILE))
    capsys.readouterr()
    d_off = copy.deepcopy(d_without)
    _run(s, cfg, d_off, active_studio=False)
    assert _snap(s) == without and d_off == d_without and capsys.readouterr().err == ""


def test_the_workflow_passes_the_switch(monkeypatch):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        y = f.read()
    assert "ACTIVE_STUDIO:        ${{ vars.ACTIVE_STUDIO || 'true' }}" in y
    monkeypatch.delenv("ACTIVE_STUDIO", raising=False)
    assert settings()["active_studio"] is True
    monkeypatch.setenv("ACTIVE_STUDIO", "false")
    assert settings()["active_studio"] is False


def test_build_static_runs_the_step_after_the_uninstall_step_and_before_the_dashboard_is_written():
    src = open(build_static.__file__, encoding="utf-8").read()
    body = src[src.index("def build("):]
    i_uni, i_st = body.index("_uninstall_with_revenue("), body.index("as_paths = _active_studio_step(")
    i_dash, i_hdr = body.index('_shipgz(out_dir, "dashboard.json", dashboard)'), body.index("+ as_paths + studio_paths))")
    assert i_uni < i_st < i_dash < i_hdr


# ── the public log ────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_log_is_one_counts_only_line(site, capsys):
    s, cfg, dash = site
    _run(s, cfg, dash)
    err = capsys.readouterr().err
    lines = err.strip().splitlines()
    assert len(lines) == 1 and LINE.match(lines[0]), err
    assert lines[0] == "active studio: apps 4, skipped 0, alerts %d, no ga4 2, kb %d" % (
        len(_gz(os.path.join(s, asb.FILE))["alerts"]), int(lines[0].rsplit(" ", 1)[1]))
    for secret in list(ss.NAMES.values()) + list(ss.PKG.values()) + list(ss.PKG) + [ss.A1, ss.A2, "Studio One"]:
        assert secret not in err
