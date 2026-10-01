"""🧭 Uninstall Studio — "Gone by day N" (the owner, 1 Oct: every app × Same day / Day 1 / 3 / 7 / 14 / 30 / 45 / 60 — how
many of its new users had uninstalled by that day). On synthetic data only (tests/studio_synth.py, made-up apps):

  * the build step's gd block (admob_iq.uninstall_studio_build._gone): its contract, the cumulative maths on hand-made
    cohorts (the settled cutoff, the launch cut, zero-install days, incomplete days, tracking breaks and the engine's
    lmat cap), and failure isolation (a broken app costs only its own block; a file without the block still renders);
  * the page (tests/studio_frontend.js runs the real dashboard script): the table right under "Saari apps" with its 8 day
    columns, the actual number first and its % beside it, the fallback window (none of the range's install days has a
    pakka day N: the newest pakka ones, named under the header / in the cell and in the tooltip), the words, and the
    app view's 8 bars;
  * the engine cross-check: on a 7-day range every cell equals the engine's own settled comparison (compare(cd, N,
    late) from the GA4 store, exactly as evaluate_app builds cd), the checkpoint table's "recent" where its window is
    that one, and the page's port of the engine's _pick (gdPick) equals _pick on random spoiled cohorts."""

import gzip
import json
import os
import random
import re
import shutil
import subprocess
from datetime import date, timedelta

import pytest

from admob_iq import build_static
from admob_iq import uninstall_studio_build as usb
from admob_iq.config import settings
from admob_iq.engine import uninstall as eng
from admob_iq.fetch import ga4_uninstall as gu
from tests import studio_synth as ss
from tests.test_uninstall_studio_frontend import BANNED, BANNED_CASE, DEVA

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
GDL = ["Same day", "Day 1", "Day 3", "Day 7", "Day 14", "Day 30", "Day 45", "Day 60"]
CELL = re.compile(r"^[\d,]+(?:\.\d+)?(?: lakh)? \(\d+\.\d%\)$")


def _add(s, n):
    return (date.fromisoformat(s) + timedelta(days=n)).isoformat()


MO = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _span(a, b, yr):
    """The page's span(): "17–23 Jul", "28 Jun–4 Jul" (the year only when not this one)."""
    fd = lambda s: "%d %s%s" % (int(s[8:]), MO[int(s[5:7]) - 1], "" if s[:4] == yr else " " + s[:4])   # noqa: E731
    if a == b:
        return fd(a)
    if a[:4] != b[:4]:
        return fd(a) + "–" + fd(b)
    return (str(int(a[8:])) if a[:7] == b[:7] else "%d %s" % (int(a[8:]), MO[int(a[5:7]) - 1])) + "–" + fd(b)


def _gz(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


# ── the site, the build step, the page ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("gone"))
    site, cfg, dash = ss.make_site(root)
    assert build_static._studio_step(dash, os.path.join(root, "data"), site, dict(settings())) == ["/uninstall_studio.json.gz"]
    return root, site, cfg, dash, _gz(os.path.join(site, usb.FILE)), _gz(os.path.join(site, "uninstall.json.gz"))


def _cases():
    """Random cohorts spoiled by incomplete days and tracking breaks → the engine's own _pick on them (the page's port must
    agree: the same install days, window start and fall-back)."""
    rnd, out = random.Random(7), []
    for t in range(60):
        H = rnd.randint(40, 140)
        n = [0 if rnd.random() < 0.08 else rnd.randint(1, 900) for _ in range(H)]
        raw = [{lg: rnd.randint(0, max(1, v // 20)) for lg in range(0, min(H - i, 40), rnd.choice((1, 2, 3)))}
               for i, v in enumerate(n)]
        inc = sorted(rnd.sample(range(H), rnd.choice((0, 1, 3, 8, 20))))
        cd = {"H": H, "n": n, "raw": raw, "inc": inc}
        broken = [rnd.random() < (0.03 if t % 3 == 0 else 0) for _ in range(H)]
        eng.mark_breaks(cd, broken)
        N = rnd.choice((0, 1, 3, 7, 14, 30))
        K = rnd.choice((7, 7, 14, 30))
        need = max(1, round(K * 5 / 7))
        if H - 1 - N - 7 < 0:
            continue
        top = rnd.randint(max(0, H - 1 - N - 30), H - 1 - N)
        idx, w0, fb = eng._pick(cd, top, K, need, N)
        out.append({"use": [bool(n[j]) and not eng._left_out(cd, j, N) for j in range(H)],
                    "lost": [bool(n[j]) and bool(eng._left_out(cd, j, N)) for j in range(H)],
                    "top": min(top, H - 1 - N), "K": K, "need": need, "want": {"idx": idx, "w0": w0, "fb": bool(fb)}})
    return out


@pytest.fixture(scope="module")
def page(built, tmp_path_factory):
    if NODE is None:
        pytest.skip("node is not installed")
    root, site, cfg, dash, studio, uni = built
    fx = str(tmp_path_factory.mktemp("gone_fx"))
    cases = _cases()
    for name, body in (("dashboard.json", dash), ("uninstall_studio.json", studio), ("uninstall.json", uni),
                       ("gd_pick.json", cases)):
        with open(os.path.join(fx, name), "w", encoding="utf-8") as f:
            json.dump(body, f)
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    path = os.path.join(fx, "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "studio_frontend.js"), path, fx],
                         check=True, capture_output=True, text=True, timeout=300)
    rep = json.loads(out.stdout)
    assert rep["errors"] == [], rep["errors"]
    return json.loads(rep["out"]["gd"]), json.loads(rep["out"]["gdpick"]), cases


# ── the build step: the gd block ──────────────────────────────────────────────────────────────────────────────────

def test_the_block_contract(built):
    _, _, _, _, studio, uni = built
    g = studio["gd"]
    assert set(g) == {"cols", "pad", "apps"} and g["cols"] == usb.GD_COLS == [0, 1, 3, 7, 14, 30, 45, 60]
    assert g["pad"] == usb.GD_PAD and set(g["apps"]) == {a["id"] for a in studio["apps"]}
    M = studio["meta"]
    g0 = _add(M["S"], -usb.GD_PAD)
    for a in uni["apps"]:
        b = g["apps"][a["app_id"]]
        assert set(b) == {"n", "g", "x"} and len(b["g"]) == len(usb.GD_COLS) and b["x"] == []
        n = usb.dec(b["n"])
        cols = [usb.dec(e) for e in b["g"]]
        assert len(n) == usb.GD_PAD + usb.SPAN and all(len(c) == len(n) for c in cols)
        assert all(v is None or (isinstance(v, int) and v >= 0) for c in cols + [n] for v in c)
        for j in range(len(n)):
            d = _add(g0, j)
            vals = [c[j] for c in cols]
            if None in vals:                                   # once not counted, never again for a later day N
                assert all(v is None for v in vals[vals.index(None):])
            for N, v in zip(usb.GD_COLS, vals):
                if _add(d, N) > a["settled_till"] or not n[j]:
                    assert v is None, (d, N)                  # settled days only; no installs: nothing to count
                elif n[j]:
                    assert v is not None, (d, N)              # (no incomplete days / breaks on the synthetic site)
    young = next(a for a in studio["apps"] if a["nm"].startswith("Demo Young"))
    n = usb.dec(g["apps"][young["id"]]["n"])
    assert n[:usb.GD_PAD + 80].count(None) > 50                # only its 70 days of history


def _detail(hs, E, late=7, **kw):
    a = {"settled_till": _add(E, -late), "launch": {}, "flags": {"incomplete_days": {}}, "daily": {"breaks": []}}
    a.update(kw)
    return a


def _cohort(hs, E, new, lag_tbl):
    H = (date.fromisoformat(E) - date.fromisoformat(hs)).days + 1
    lags = []
    for i in range(H):
        age = H - 1 - i
        lags.append([[lg, u] for lg, u in lag_tbl if lg <= age])
    return {"start": hs, "end": E, "new": [new(i) for i in range(H)], "lags": lags}


LAGS = [(0, 10), (1, 3), (2, 2), (3, 1), (5, 1), (7, 1), (10, 2), (14, 1), (20, 1), (30, 2), (40, 1), (45, 1), (50, 1),
        (60, 1), (61, 5)]


def _want(N):
    return sum(u for lg, u in LAGS if lg <= N)


def test_cumulative_gone_by_day_n_with_the_settled_cutoff_and_the_launch(built):
    E = "2026-06-30"
    S = _add(E, -(usb.SPAN - 1))
    hs = _add(S, -60)
    launch = _add(S, -20)                                      # test installs before it: never counted
    c = _cohort(hs, E, lambda i: 0 if i == 100 else 100 + i % 7, LAGS)
    a = _detail(hs, E, launch={"day": launch, "hidden": True})
    out = usb._gone(a, c, E, S)
    n, cols = usb.dec(out["n"]), [usb.dec(e) for e in out["g"]]
    g0 = _add(S, -usb.GD_PAD)
    st = a["settled_till"]
    for j in range(len(n)):
        d = _add(g0, j)
        ci = (date.fromisoformat(d) - date.fromisoformat(hs)).days
        if d < launch:
            assert n[j] is None and all(col[j] is None for col in cols), d
            continue
        assert n[j] == c["new"][ci]
        run = 0
        for k, N in enumerate(usb.GD_COLS):
            v = cols[k][j]
            if ci == 100 or _add(d, N) > st:
                assert v is None, (d, N)
                continue
            run += v
            assert run == _want(N), (d, N)                   # the increments add up to gone-by-day-N
    # the newest install day of each column: exactly the last one whose day N is settled
    for k, N in enumerate(usb.GD_COLS):
        last = max(j for j in range(len(n)) if cols[k][j] is not None)
        assert _add(g0, last) == _add(st, -N)


def test_incomplete_days_and_breaks_leave_out_what_the_engine_leaves_out(built):
    E = "2026-06-30"
    S = _add(E, -(usb.SPAN - 1))
    hs = _add(S, -60)
    inc, brk = _add(E, -40), _add(E, -100)
    c = _cohort(hs, E, lambda i: 300, LAGS)
    a = _detail(hs, E, flags={"incomplete_days": {inc: {"cov": 0.4}}}, daily={"breaks": [brk]})
    out = usb._gone(a, c, E, S)
    cols = [usb.dec(e) for e in out["g"]]
    g0 = _add(S, -usb.GD_PAD)
    lmat = 30                                                 # LAGS lose ≥ 0.5% on day 30: the engine's cap (STEEP_MAX_N)
    for j in range(len(cols[0])):
        d = _add(g0, j)
        dead = False
        for k, N in enumerate(usb.GD_COLS):
            spoiled = (d <= inc <= _add(d, N)) or (d <= brk <= _add(d, min(N, lmat)))
            dead = dead or spoiled or _add(d, N) > a["settled_till"]
            assert (cols[k][j] is None) == dead, (d, N)
    assert out["x"] == sorted([[brk, "b"], [inc, "i"]])
    # a break 40 days after install no longer spoils Day 45 / 60 (past lmat), an incomplete day does
    d = _add(brk, -40)
    j = (date.fromisoformat(d) - date.fromisoformat(g0)).days
    assert cols[usb.GD_COLS.index(45)][j] is not None and cols[usb.GD_COLS.index(60)][j] is not None


def test_a_broken_app_costs_only_its_own_block(built, tmp_path, monkeypatch, capsys):
    root, site, cfg, dash, _, uni = built
    s = str(tmp_path / "site")
    shutil.copytree(site, s)
    bad = uni["apps"][1]["app_id"]
    real = usb._gone

    def gone(a, c, E, S):
        if a["app_id"] == bad:
            raise KeyError("secret-app")
        return real(a, c, E, S)
    monkeypatch.setattr(usb, "_gone", gone)
    d2 = json.loads(json.dumps(dash))
    d2["uninstall"].pop("studio", None)
    assert build_static._studio_step(d2, os.path.join(root, "data"), s, dict(settings())) == ["/uninstall_studio.json.gz"]
    body = _gz(os.path.join(s, usb.FILE))
    assert bad in {a["id"] for a in body["apps"]} and bad not in body["gd"]["apps"]   # the app stays in the Studio
    assert len(body["gd"]["apps"]) == len(body["apps"]) - 1
    err = capsys.readouterr().err
    assert re.match(r"^uninstall studio: apps 4, skipped 0, alerts \d+, no ga4 2, kb \d+$", err.strip()) and "secret" not in err


def test_the_file_stays_small(built):
    _, site, _, _, studio, _ = built
    raw = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()   # noqa: E731
    with_gd = len(gzip.compress(raw(studio), 9, mtime=0))
    without = len(gzip.compress(raw({k: v for k, v in studio.items() if k != "gd"}), 9, mtime=0))
    assert with_gd - without < 3 * 1024                      # 4 apps × 9 compact arrays: a few KB


# ── the page ──────────────────────────────────────────────────────────────────────────────────────────────────────

def _heads(panel):
    return [re.sub(r"<[^>]+>.*", "", h) for h in re.findall(r'<th class="[^"]*" data-gsort="[^"]+"[^>]*>(.*?)</th>', panel)]


def test_the_table_sits_under_saari_apps_with_8_day_columns(page):
    gd, _, _ = page
    for k in ("7", "30", "60"):
        r = gd[k]
        assert r["afterTbl"]
        assert "<h2>Gone by day N</h2>" in r["panel"] and "Naye users me se kitne N din ke andar app hata chuke" in r["panel"]
        assert _heads(r["panel"]) == ["App"] + GDL
        rows = re.findall(r'<tr data-app="(\d+)" data-gdgo="\1">', r["panel"])
        assert len(rows) == 4                                  # every GA4 app …
        assert r["panel"].count("N/A — ") == 2                 # … and the no-GA4 ones as N/A
        assert "Demo Gallery (2026 wala)" in r["panel"]        # the same-name tag, with the account
        assert 'id="us-gq"' in r["panel"] and 'id="us-gfst"' in r["panel"]   # the same search / filters as Saari apps


def test_cells_put_the_actual_number_first_and_the_percent_beside_it(page):
    gd, _, _ = page
    for k in ("7", "30", "60"):
        vals = re.findall(r'<span class="us-v">(.*?)</span>', gd[k]["panel"])
        txt = [re.sub(r"<[^>]+>", "", v) for v in vals]
        assert len(txt) >= 20 and all(CELL.match(t) for t in txt), txt[:5]
        for app in gd[k]["cells"]:
            for c in app["c"]:
                if c["k"] and c["n"] >= 20:                    # (the cell shows these very numbers)
                    assert c["p"] == pytest.approx(c["x"] / c["n"])
        assert not re.search(r"\b100 me\b|1,000 me|per 1,000", gd[k]["panel"])


def test_the_fallback_window_is_named_under_the_header_and_in_the_tooltip(built, page):
    yr = built[4]["meta"]["today"][:4]
    gd, _, _ = page
    r = gd["7"]
    W = r["W"]
    # a 7-day range: no install day of it has a pakka day N yet → every column takes the newest pakka 7 install days
    big = next(a for a in r["cells"] if a["c"][3]["n"] > 1000)
    for k, c in enumerate(big["c"]):
        assert c["mode"] == "fb" and c["t"] < W["f"] and c["k"] == 7
    hdr = re.findall(r'data-gsort="(\d)"[^>]*>.*?<span class="us-gsh">⏳ installs ([^<]+)</span>', r["panel"])
    assert len(hdr) == 8
    assert [h[1] for h in hdr] == [_span(c["f"], c["t"], yr) for c in big["c"]]   # the column's window, by name
    tips = r["tips"]
    t60 = [t for t in tips if " · Day 60 " in t and "Installs " in t]
    assert t60 and all("⏳ Not final · " in t and " ko pakka" in t and re.search(r"sabse naye pakke \d+ din ke installs", t) for t in t60)
    # a cell whose own window differs from its column's (the young app: its Day 60 window starts at its launch) names it
    young = next(a for a in r["cells"] if a["c"][7]["k"] and a["c"][7]["k"] < 7)
    assert young and '<span class="us-gsb">⏳ installs ' in r["panel"]
    # a 30-day range: the newest days left out (⏳ part) on the short columns, a fall-back on Day 30+
    r30 = gd["30"]
    modes = {c["mode"] for a in r30["cells"] for c in a["c"][:4] if c["k"]}
    assert modes == {"part"} and {c["mode"] for a in r30["cells"] for c in a["c"][5:] if c["k"]} == {"fb"}
    assert any("⏳ Not final · " in t and "abhi pakka nahi, wo nahi gine" in t for t in r30["tips"])


def test_cells_are_coloured_against_the_apps_own_normal(page):
    gd, _, _ = page
    s = [c["s"] for k in ("7", "30") for a in gd[k]["cells"] for c in a["c"] if c["k"]]
    assert any(v is not None for v in s)
    big = next(a for a in gd["7"]["cells"] if a["c"][0]["n"] > 1000)
    assert all(c["nrm"] is not None for c in big["c"])        # its 4 weeks of installs before each cell's own
    # the synthetic big app loses +45% more users from its newest 12 install days: its Same day cell reads Worse
    gal = next(a for a in gd["7"]["cells"] if a["c"][0]["s"] is not None and a["c"][0]["s"] >= 2)
    assert gal and 'class="us-hcell us-h' in gd["7"]["panel"]


def test_the_words(page):
    gd, _, _ = page
    names = sorted(set(ss.NAMES.values()), key=len, reverse=True)
    texts = []
    for k in ("7", "30", "60"):
        texts += [gd[k]["panel"], gd[k]["drawer"]] + gd[k]["tips"]
    texts += [gd["page"]]
    for t in texts:
        u = re.sub(r"<[^>]+>", " ", t).replace("&amp;", "&")
        for n in names:
            u = u.replace(n, "<app>")
        for w in ("undefined", "NaN", "[object Object]", "Infinity"):
            assert w not in u, (w, u[:200])
        assert not DEVA.search(u)
        m = BANNED.search(u) or BANNED_CASE.search(u)
        assert not m, (m.group(0), u[max(0, m.start() - 80):m.end() + 40])
        assert not re.search(r"\b100 me\b|1,000 me|per 1,000", u)
    statuses = set(re.findall(r"\b(Worse|Watch|Better|Normal|Too early|N/A)\b", " ".join(gd["7"]["tips"] + gd["30"]["tips"])))
    assert statuses and statuses <= {"Worse", "Watch", "Better", "Normal", "Too early", "N/A"}


def test_the_app_view_has_its_8_bars_with_the_numbers_and_the_row(page):
    gd, _, _ = page
    for h in (gd["7"]["drawer"], gd["page"]):
        bars = re.findall(r'<div class="us-gbr" data-tk="gd:\d+:(\d)">(.*?)</div>', h)
        assert [int(k) for k, _ in bars] == list(range(8))
        labels = [re.sub(r"<[^>]+>", "", re.search(r'<span class="us-gbv">(.*?)(?:<span class="us-gsb">|</span></div>|$)',
                                                      b + "</div>").group(1)) for _, b in bars]
        assert sum(bool(CELL.match(t.strip())) for t in labels) >= 6, labels
        assert "Gone by day N" in h and len(re.findall(r'<td[^>]*data-tk="gd:\d+:\d"', h)) == 8   # + the table's row
        assert 'class="us-gbn"' in h                           # the app's own normal on each bar


def test_a_file_without_the_block_still_renders(page):
    gd, _, _ = page
    n = gd["nogd"]
    assert n["screen"] and "agle refresh" in n["panel"] and "<table" not in n["panel"]
    assert "us-gbars" not in n["drawer"] and "Kitne abhi bhi app me" in n["drawer"]


# ── the cross-check with the engine ───────────────────────────────────────────────────────────────────────────────

def _engine_cd(data, aid, late):
    """cd exactly as evaluate_app builds it from the GA4 store (fill_days, the launch cut, breaks, incomplete days)."""
    store = eng.fill_days(gu.load_store(gu.store_path(data, aid)))
    E = eng._d(store["window_end"])
    whole = eng.cohort_data(store, E)
    L = eng.launch_day(whole["n"])
    i0 = L if sum(whole["n"][:L]) else 0
    ds = eng.daily_series(store, E, whole, late, i0)
    eng.mark_breaks(whole, ds["broken"])
    return eng.mark_breaks(eng.cut_cohorts(whole, i0), ds["broken"][i0:]) if i0 else whole


def test_a_7_day_range_equals_the_engines_own_numbers(built, page):
    root, _, _, _, studio, uni = built
    gd, _, _ = page
    late, M = int(uni["consts"]["late_days"]), studio["meta"]
    cells = {a["id"]: a["c"] for a in gd["7"]["cells"]}
    seen = coincide = 0
    for a in uni["apps"]:
        cd = _engine_cd(os.path.join(root, "data"), a["app_id"], late)
        tab = {r["n"]: r for r in a["table"]}
        for k, N in enumerate(usb.GD_COLS):
            g = cells[a["app_id"]][k]
            if N > cd["H"] - 1 - late or not g["k"]:
                continue
            sh = (date.fromisoformat(a["settled_till"]) - date.fromisoformat(min(a["settled_till"], M["settled"]))).days
            e = eng.compare(cd, N, late=late + sh)["recent"]     # the settled comparison the checkpoint table uses
                                                                 # (at the Studio's common pakka day: sh = 0 here)
            assert (g["n"], g["k"], g["f"], g["t"]) == (e["users"], e["k"], e["from"], e["to"]), (a["app"], N)
            assert g["p"] == pytest.approx(e["p"], abs=6e-6)
            seen += 1
            r = tab.get(N)
            if r and (r["recent"]["from"], r["recent"]["to"]) == (g["f"], g["t"]):
                assert r["recent"]["users"] == g["n"] and r["recent"]["p"] == pytest.approx(g["p"], abs=6e-6)
                coincide += 1
    assert seen >= 28 and coincide >= 1, (seen, coincide)


def test_the_pages_window_pick_is_the_engines(page):
    _, got, cases = page
    assert len(cases) >= 40 and sum(c["want"]["fb"] for c in cases) >= 3      # (the random cases do fall back)
    for c, g in zip(cases, got):
        assert (g["idx"], g["w0"], g["fb"]) == (c["want"]["idx"], c["want"]["w0"], c["want"]["fb"]), c["want"]
