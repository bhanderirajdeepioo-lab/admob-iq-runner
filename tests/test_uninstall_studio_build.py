"""🧭 Uninstall Studio — the build step (admob_iq.uninstall_studio_build + its build_static wiring), on synthetic sites
made by the real build code (tests/studio_synth.py; no real data):

  * parity: the file holds EXACTLY what the owner-approved demo generator's data step (tests/studio_reference.py,
    frozen) makes of the same site — every array, alert, size class, name and meta value;
  * the contract: the keys, the compact arrays (all SPAN days long, decodable), the alert / app links, the pointer
    dashboard["uninstall"]["studio"] = {file, v}, deterministic bytes (an unchanged build rewrites nothing);
  * the size guard (≤ 300 KB gzipped for a 40-app portfolio; a hard cap past which no file is written);
  * failure isolation (a broken app costs only that app; any other failure: no file, no pointer, the error TYPE only);
  * the switch (UNINSTALL_STUDIO=false: the site, the dashboard, _headers and the log exactly as without the feature);
  * the public log: ONE counts-only line."""

import copy
import gzip
import hashlib
import json
import os
import re
import shutil
from datetime import date, timedelta

import pytest

from admob_iq import build_static
from admob_iq import uninstall_studio_build as usb
from admob_iq.config import settings
from tests import studio_synth as ss
from tests.studio_reference import reference

LINE = re.compile(r"^uninstall studio: apps \d+, skipped \d+, alerts \d+, no ga4 \d+, kb \d+$")
KEYS = ('nw', 'un', 'a28', 'md', 'lo', 'hi', 'g0', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'r1', 'rv', 'a1')


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("studio"))
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


def _run(site, cfg, dash, **kw):
    s = dict(settings(), **kw)
    return build_static._studio_step(dash, os.path.join(os.path.dirname(cfg), "data"), site, s)


# ── parity with the approved demo ─────────────────────────────────────────────────────────────────────────────────

def _beyond_the_demo(body, ref):
    """The owner's "no trim" (2 Oct: "13-19 july tak hi kyu? pura data hona chaiye") goes past the frozen demo in two
    places only: the install-week grid has EVERY week since the app's start (the demo: the 12 newest — they are its
    newest 12 rows, cell for cell) and the 📦 updates reach back before the span (the demo: inside the span — the same
    rows there). Checked here, then put back to the demo's, so the rest is compared whole."""
    S, E = ref["meta"]["S"], ref["meta"]["E"]
    for a, r in zip(body["apps"], ref["apps"]):
        assert a["id"] == r["id"]
        assert a["coh"]["ref"] == r["coh"]["ref"] and len(a["coh"]["w"]) >= len(r["coh"]["w"])
        assert a["coh"]["w"][len(a["coh"]["w"]) - len(r["coh"]["w"]):] == r["coh"]["w"]
        assert [x for x in a["rel"] if S <= x[0] <= E] == r["rel"] and all(x[0] <= E for x in a["rel"])
        a["coh"]["w"], a["rel"] = r["coh"]["w"], r["rel"]
    return body


def test_the_file_holds_exactly_the_demo_generators_numbers(site, capsys):
    s, cfg, dash = site
    ref = reference(s)                                         # the frozen demo step, reading the site's files
    assert ref["apps"] and ref["alerts"] and ref["noga"]       # (the synthetic site exercises all of it)
    assert _run(s, cfg, dash) == ["/uninstall_studio.json.gz"]
    body = _gz(os.path.join(s, usb.FILE))
    assert body.pop("v") == usb.V
    assert body.pop("gt")["apps"]                             # ("Gone by day N": its own block, after the demo —
    assert any(len(a["coh"]["w"]) > 12 for a in body["apps"])  #  tests/test_uninstall_studio_gone.py)
    assert _beyond_the_demo(body, ref) == ref
    # and the module's own entry point, straight
    U = _gz(os.path.join(s, "uninstall.json.gz"))
    got = usb.build_data(dash, U, lambda n: _gz(os.path.join(s, n)),
                         json.load(open(os.path.join(cfg, "account_names.json"))),
                         json.load(open(os.path.join(cfg, "app_names.json"))))
    got.pop("gt")
    assert _beyond_the_demo(got, ref) == ref


# ── no trim: the install-week grid = every week since the app's start (owner, 2 Oct) ──────────────────────────────

def _monday(d):
    d = date.fromisoformat(d)
    return d - timedelta(days=d.weekday())


def test_the_install_week_grid_has_every_week_since_the_apps_start(site, capsys):
    """Every ISO week from the one the app's history starts in (its launch, or the oldest cohort day) to the newest,
    none skipped; each cell recomputed here straight from the cohort file (installs of the week's days, gone by day N
    = the uninstalls at lag ≤ N) — the older "Install week × day" table's own arithmetic."""
    s, cfg, dash = site
    _run(s, cfg, dash)
    body = _gz(os.path.join(s, usb.FILE))
    M, U = body["meta"], _gz(os.path.join(s, "uninstall.json.gz"))
    E, cols = M["E"], M["cohCols"]
    det = {a["app_id"]: a for a in U["apps"]}
    n_old = 0
    for a in body["apps"]:
        c = _gz(os.path.join(s, "uninstall_c_%s.json.gz" % a["k"]))
        start = max(a["first"], c["start"])
        want = []
        m = _monday(start)
        while m <= _monday(E):
            want.append(m.isoformat())
            m += timedelta(days=7)
        W = a["coh"]["w"]
        assert [w[0] for w in W] == want, a["nm"]               # every week, oldest first, none skipped
        n_old += sum(1 for w in W if w[0] < (_monday(E) - timedelta(days=7 * 11)).isoformat())
        settled = det[a["id"]].get("settled_till") or E
        for w in W:
            f, t = (w[4], w[5]) if len(w) == 6 else (w[0], (date.fromisoformat(w[0]) + timedelta(days=6)).isoformat())
            assert f == max(w[0], start) and t == min((date.fromisoformat(w[0]) + timedelta(days=6)).isoformat(), E)
            assert (len(w) == 6) == (f != w[0] or t != (date.fromisoformat(w[0]) + timedelta(days=6)).isoformat())
            idx = [(date.fromisoformat(f) - date.fromisoformat(c["start"])).days + k
                   for k in range((date.fromisoformat(t) - date.fromisoformat(f)).days + 1)]
            n = sum(c["new"][i] or 0 for i in idx)
            assert w[1] == n
            v, bits = usb.dec(w[2]), format(w[3], "0%db" % len(cols))
            for k, N in enumerate(cols):
                if (date.fromisoformat(t) + timedelta(days=N)).isoformat() > E or not n:
                    assert v[k] is None and bits[k] == "0"
                    continue
                gone = sum(cnt for i in idx for lg, cnt in (c["lags"][i] or []) if lg <= N)
                assert v[k] == int(round((1 - gone / n) * 1000)), (a["nm"], w[0], N)
                assert bits[k] == ("1" if (date.fromisoformat(t) + timedelta(days=N)).isoformat() > settled else "0")
    assert n_old > 40                                          # (the synthetic site reaches well past 12 weeks)


def test_every_update_reaches_the_grid_even_before_the_span(site, capsys):
    """📦 the updates: all of them up to the span's end (the grid's 📦 lines over its oldest weeks; "📦 Updates" lists
    them all) — an update months before the span is there, one after the span's end is not."""
    s, cfg, dash = site
    U = _gz(os.path.join(s, "uninstall.json.gz"))
    a0 = next(a for a in U["apps"] if a.get("daily") and a.get("releases"))
    old_day = (date.fromisoformat(a0["daily"]["start"]) + timedelta(days=17)).isoformat()
    a0["releases"] = [{"date": old_day, "version": "0.9", "kind": "version"}, {"date": "2099-01-01", "version": "9.9"}] + a0["releases"]
    with gzip.open(os.path.join(s, "uninstall.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(U, f)
    _run(s, cfg, dash)
    body = _gz(os.path.join(s, usb.FILE))
    a = next(x for x in body["apps"] if x["id"] == a0["app_id"])
    assert old_day < body["meta"]["S"] and [old_day, "v0.9", None, False] in a["rel"]
    assert all(r[0] <= body["meta"]["E"] for r in a["rel"]) and a["rel"] == sorted(a["rel"])
    assert any(w[0] <= old_day <= (w[5] if len(w) == 6 else (date.fromisoformat(w[0]) + timedelta(days=6)).isoformat())
               for w in a["coh"]["w"])                     # …and the grid has its week


def test_the_synthetic_site_covers_the_studios_cases(site):
    s, cfg, dash = site
    ref = reference(s)
    nm = [a["nm"] for a in ref["apps"]]
    assert nm == ["Demo Gallery (2026 wala) · Studio One", "Demo Notes · Studio One", "Demo Torch · A/c 2002",
                  "Demo Young · A/c 2002"]                    # names with the account, the same-name tag, never cut
    assert [a["sz"] for a in ref["apps"]] == ["badi", "madhyam", "chhoti", "chhoti"]
    assert {(x["sev"], x["fam"]) for x in ref["alerts"]} >= {("bigda", "cohort"), ("behtar", "cohort")}
    assert all(x["at"] for x in ref["alerts"])                 # every alert carries its alert time
    assert sorted(n["nm"] for n in ref["noga"]) == ["Demo Clock · A/c 2002", "Demo Gallery · Studio One"]
    assert ref["apps"][0]["rel"] and ref["apps"][0]["rel"][0][1] == "v1.1"
    young = ref["apps"][3]
    assert usb.dec(young["nw"]).count(None) > 60              # 70 days of history inside the 156-day span


# ── the contract ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_contract_pointer_and_deterministic_bytes(site, capsys):
    s, cfg, dash = site
    _run(s, cfg, dash)
    p = os.path.join(s, usb.FILE)
    body = _gz(p)
    assert set(body) == {"v", "meta", "apps", "alerts", "noga", "gt"}     # (gt: tests/test_uninstall_studio_gone.py)
    M = body["meta"]
    assert set(M) == {"cohCols", "S", "E", "n", "today", "gen", "fx", "late", "lag", "actLate", "settled", "apps",
                      "noga", "portfolioSettled"}
    assert M["n"] == usb.SPAN and M["cohCols"] == usb.COH_COLS and M["apps"] == len(body["apps"])
    assert M["fx"] == ss.FX and M["today"] == dash["today_date"] and M["gen"] == dash["generated_at"]
    for a in body["apps"]:
        assert set(a) == {"id", "k", "nm", "store", "acc", "sz", "paisa", "first", "settled", "aset", "retFrom", "stage",
                          "ready", "vk", "pkg", "ac", "rel", "coh"} | set(KEYS)
        for k in KEYS:
            arr = usb.dec(a[k])
            assert len(arr) == usb.SPAN and usb.enc(arr) == a[k]
            assert all(v is None or isinstance(v, int) for v in arr)
        assert a["sz"] in ("badi", "madhyam", "chhoti") and a["vk"] in ("none", "low", "same", "worse", "better")
        assert len(a["coh"]["ref"]) == len(usb.COH_COLS)
        for w in a["coh"]["w"]:
            assert len(usb.dec(w[2])) == len(usb.COH_COLS) and len(w) in (4, 6)
        assert a["nm"].endswith(" · " + a["acc"])            # always with its account
    for x in body["alerts"]:
        assert 0 <= x["a"] < len(body["apps"]) and x["sev"] in ("bigda", "dhyan", "behtar", "normal")
        assert "id" not in x
    ptr = dash["uninstall"]["studio"]
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    assert ptr == {"file": usb.FILE, "v": hashlib.sha1(raw).hexdigest()[:12]}
    b1, m1 = open(p, "rb").read(), os.stat(p).st_mtime_ns
    dash2 = json.loads(json.dumps(dash))
    dash2["uninstall"].pop("studio")
    _run(s, cfg, dash2)                                        # the same inputs again: nothing rewritten
    assert open(p, "rb").read() == b1 and os.stat(p).st_mtime_ns == m1 and dash2["uninstall"]["studio"] == ptr


def test_headers_keep_the_file_out_of_stale_caches(site, capsys):
    s, cfg, dash = site
    extra = _run(s, cfg, dash)
    txt = build_static.headers_text(["uninstall.json.gz"], dash, extra=extra)
    assert "/uninstall_studio.json.gz\n  Cache-Control: no-store\n\n" in txt
    assert txt.index("/uninstall_studio.json.gz") < txt.index("/index.html")


# ── the size guard ────────────────────────────────────────────────────────────────────────────────────────────────

def _grow(s, n):
    """The site's GA4 apps copied to n apps (new ids / keys / files) — a big portfolio's size."""
    U = _gz(os.path.join(s, "uninstall.json.gz"))
    base = list(U["apps"])
    out = []
    for i in range(n):
        a = copy.deepcopy(base[i % len(base)])
        key = "%012x" % (0xabc000000000 + i)
        for pre in ("uninstall_c_", "active_"):
            shutil.copyfile(os.path.join(s, pre + a["key"] + ".json.gz"), os.path.join(s, pre + key + ".json.gz"))
        a.update(key=key, app_id=a["app_id"] + "%03d" % i, app="Grow %d" % i)
        out.append(a)
    U["apps"] = out
    with gzip.open(os.path.join(s, "uninstall.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(U, f)


def test_a_40_app_portfolio_stays_under_300_kb(site, capsys):
    s, cfg, dash = site
    _grow(s, 40)
    _run(s, cfg, dash)
    line = capsys.readouterr().err.strip()
    assert LINE.match(line) and line.startswith("uninstall studio: apps 40, skipped 0,")
    assert os.path.getsize(os.path.join(s, usb.FILE)) <= 300 * 1024


def test_past_the_hard_cap_nothing_is_written(site, monkeypatch, capsys):
    s, cfg, dash = site
    _run(s, cfg, dash)
    capsys.readouterr()
    monkeypatch.setattr(usb, "MAX_GZ", 1000)
    d2 = json.loads(json.dumps(dash))
    assert _run(s, cfg, d2) == []
    assert not os.path.exists(os.path.join(s, usb.FILE)) and "studio" not in d2["uninstall"]
    assert re.match(r"^uninstall studio: too big \(\d+ kb\), not written$", capsys.readouterr().err.strip())


# ── failure isolation ─────────────────────────────────────────────────────────────────────────────────────────────

def test_a_broken_app_costs_only_that_app(site, capsys):
    s, cfg, dash = site
    U = _gz(os.path.join(s, "uninstall.json.gz"))
    k = U["apps"][1]["key"]
    with open(os.path.join(s, "uninstall_c_%s.json.gz" % k), "wb") as f:
        f.write(b"broken")
    assert _run(s, cfg, dash) == ["/uninstall_studio.json.gz"]
    body = _gz(os.path.join(s, usb.FILE))
    assert len(body["apps"]) == 3 and U["apps"][1]["app_id"] not in {a["id"] for a in body["apps"]}
    assert all(0 <= x["a"] < 3 for x in body["alerts"])         # its alerts never point at a missing app
    assert ", skipped 1," in capsys.readouterr().err


def test_an_app_without_its_active_file_keeps_its_uninstall_numbers(site, capsys):
    s, cfg, dash = site
    U = _gz(os.path.join(s, "uninstall.json.gz"))
    os.remove(os.path.join(s, "active_%s.json.gz" % U["apps"][2]["key"]))   # (Active users switched off, say)
    _run(s, cfg, dash)
    body = _gz(os.path.join(s, usb.FILE))
    a = next(x for x in body["apps"] if x["k"] == U["apps"][2]["key"])
    assert set(usb.dec(a["rv"])) == {None} and set(usb.dec(a["r1"])) == {None} and any(usb.dec(a["un"]))


@pytest.mark.parametrize("how", ["asset", "raise"])
def test_any_other_failure_costs_the_studio_only(site, monkeypatch, capsys, how):
    s, cfg, dash = site
    _run(s, cfg, dash)                                         # an older file + pointer exist
    capsys.readouterr()
    d2 = json.loads(json.dumps(dash))
    if how == "asset":
        with open(os.path.join(s, "uninstall.json.gz"), "wb") as f:
            f.write(b"\x1f\x8bbroken")
    else:
        monkeypatch.setattr(usb, "build_data", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret-app-name")))
    before = {n: open(os.path.join(s, n), "rb").read() for n in os.listdir(s) if n != usb.FILE}
    assert _run(s, cfg, d2) == []
    assert "studio" not in d2["uninstall"] and not os.path.exists(os.path.join(s, usb.FILE))
    err = capsys.readouterr().err.strip()
    assert re.match(r"^uninstall studio skipped: [A-Za-z]+$", err) and "secret" not in err
    assert {n: open(os.path.join(s, n), "rb").read() for n in os.listdir(s)} == before   # nothing else touched
    d2.pop("uninstall"), dash.pop("uninstall")
    assert d2 == dash


def test_a_build_without_uninstall_data_leaves_no_studio_file(site, capsys):
    s, cfg, dash = site
    _run(s, cfg, dash)
    capsys.readouterr()
    d2 = {k: v for k, v in dash.items() if k != "uninstall"}
    assert _run(s, cfg, d2) == [] and not os.path.exists(os.path.join(s, usb.FILE))
    assert capsys.readouterr().err == "" and "uninstall" not in d2


# ── the switch ────────────────────────────────────────────────────────────────────────────────────────────────────

def _snap(d):
    return {n: open(os.path.join(d, n), "rb").read() for n in sorted(os.listdir(d))}


def test_switched_off_the_site_is_exactly_as_without_the_feature(site, capsys):
    s, cfg, dash = site
    without = _snap(s)                                         # the Uninstall step's own output, as HEAD writes it
    d_without = copy.deepcopy(dash)
    h_without = build_static.headers_text(["uninstall.json.gz"], d_without, extra=[])
    capsys.readouterr()
    paths = _run(s, cfg, dash, uninstall_studio=False)
    assert paths == [] and capsys.readouterr().err == ""
    assert _snap(s) == without and dash == d_without
    assert build_static.headers_text(["uninstall.json.gz"], dash, extra=paths) == h_without
    # switched off later: the file and the pointer go
    d_on = copy.deepcopy(d_without)
    _run(s, cfg, d_on)
    assert os.path.exists(os.path.join(s, usb.FILE))
    capsys.readouterr()
    d_off = copy.deepcopy(d_without)
    _run(s, cfg, d_off, uninstall_studio=False)
    assert _snap(s) == without and d_off == d_without and capsys.readouterr().err == ""


def test_the_workflow_passes_the_switch(monkeypatch):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        y = f.read()
    assert "UNINSTALL_STUDIO:     ${{ vars.UNINSTALL_STUDIO || 'true' }}" in y
    monkeypatch.delenv("UNINSTALL_STUDIO", raising=False)
    assert settings()["uninstall_studio"] is True
    monkeypatch.setenv("UNINSTALL_STUDIO", "false")
    assert settings()["uninstall_studio"] is False


def test_build_static_runs_the_step_after_the_uninstall_step_and_before_the_dashboard_is_written():
    src = open(build_static.__file__, encoding="utf-8").read()
    body = src[src.index("def build("):]
    i_uni, i_st = body.index("_uninstall_with_revenue("), body.index("studio_paths = _studio_step(")
    i_dash, i_hdr = body.index('_shipgz(out_dir, "dashboard.json", dashboard)'), body.index("+ studio_paths))")
    assert i_uni < i_st < i_dash < i_hdr


# ── the public log ────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_log_is_one_counts_only_line(site, capsys):
    s, cfg, dash = site
    _run(s, cfg, dash)
    err = capsys.readouterr().err
    lines = err.strip().splitlines()
    assert len(lines) == 1 and LINE.match(lines[0]), err
    assert lines[0] == "uninstall studio: apps 4, skipped 0, alerts %d, no ga4 2, kb %d" % (
        len(_gz(os.path.join(s, usb.FILE))["alerts"]), int(lines[0].rsplit(" ", 1)[1]))
    for secret in [ss.NAMES[a] for a in ss.NAMES] + list(ss.PKG.values()) + list(ss.PKG) + [ss.P1, ss.P2, "Studio One"]:
        assert secret not in err
