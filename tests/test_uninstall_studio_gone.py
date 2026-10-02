"""🧭 Uninstall Studio — "Gone by day N" (the owner, 1 Oct: every app × Same day / Day 1 / 3 / 7 / 14 / 30 / 45 / 60 / 90 —
its ALL-TIME share of new users gone by that day, the % first and the count second, coloured by its last pakka week, whose
dates and change show on hover). On synthetic data only (tests/studio_synth.py, made-up apps):

  * the build step's gt block (admob_iq.uninstall_studio_build._gtable): its contract; all time = the engine table's own
    "All time" (table[N].all) and the last pakka week = the engine's settled comparison (compare(cd, N, late), cd built
    from the GA4 store exactly as evaluate_app builds it), with exact counts; a young app's all time since its launch; the
    launch cut / incomplete days / settled cutoff on a hand-made cohort; failure isolation;
  * the page (tests/studio_frontend.js runs the real dashboard script): the table right under "Saari apps" with its 9 day
    columns and one icon per app, the % first and big with the count second, not tied to the range, the hover box (the
    last pakka week with its dates, the 4 weeks before, the change, ⏳), the colours, the sort by change, the words, and
    the app view's 9 bars."""

import gzip
import json
import os
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
GDL = ["Same day", "Day 1", "Day 3", "Day 7", "Day 14", "Day 30", "Day 45", "Day 60", "Day 90"]
PCT = re.compile(r"^\d{1,3}\.\d%$")
CNT = re.compile(r"^[\d,]+(?:\.\d+)?(?: lakh)? gone$")


def _add(s, n):
    return (date.fromisoformat(s) + timedelta(days=n)).isoformat()


def _gz(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("gone"))
    site, cfg, dash = ss.make_site(root)
    assert build_static._studio_step(dash, os.path.join(root, "data"), site, dict(settings())) == ["/uninstall_studio.json.gz", "/uninstall_studio_old.json.gz"]
    return root, site, cfg, dash, _gz(os.path.join(site, usb.FILE)), _gz(os.path.join(site, "uninstall.json.gz"))


@pytest.fixture(scope="module")
def page(built, tmp_path_factory):
    if NODE is None:
        pytest.skip("node is not installed")
    root, site, cfg, dash, studio, uni = built
    fx = str(tmp_path_factory.mktemp("gone_fx"))
    for name, body in (("dashboard.json", dash), ("uninstall_studio.json", studio), ("uninstall.json", uni)):
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
    return json.loads(rep["out"]["gd"])


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


# ── the build step: the gt block ──────────────────────────────────────────────────────────────────────────────────

def test_the_block_contract(built):
    _, _, _, _, studio, uni = built
    g = studio["gt"]
    assert set(g) == {"cols", "apps"} and g["cols"] == usb.GT_COLS == [0, 1, 3, 7, 14, 30, 45, 60, 90]
    assert set(g["apps"]) == {a["id"] for a in studio["apps"]}
    for a in uni["apps"]:
        b = g["apps"][a["app_id"]]
        assert set(b) == {"since", "cap", "c"} and len(b["c"]) == 9 and b["cap"] is False
        L = a["launch"]
        assert b["since"] == (L["day"] if L.get("hidden") else a["history_start"])
        for c in b["c"]:
            if c is None:
                continue
            assert set(c) <= {"a", "ay", "az", "af", "r", "u", "p", "ls", "al", "d", "fb"} and c["d"] in (None, "up", "down")
            for k in ("a", "r", "u", "p"):
                if k in c:
                    x, n, f, t = c[k][:4]
                    assert isinstance(x, int) and isinstance(n, int) and 0 <= x and n > 0 and f <= t
    young = g["apps"][next(a["id"] for a in studio["apps"] if a["nm"].startswith("Demo Young"))]["c"]
    assert young[-1] is None and any(c and c.get("ay") == 1 for c in young)   # 70 days: no pakka Day 90; under 8 weeks
                                                                               # of install days: all time since launch


def test_all_time_is_the_engine_tables_and_the_last_pakka_week_its_settled_comparison(built):
    root, _, _, _, studio, uni = built
    late = int(uni["consts"]["late_days"])
    seen = dict(all=0, young=0, last=0, prev=0, table_last=0, table_newer=0)
    for a in uni["apps"]:
        cells = studio["gt"]["apps"][a["app_id"]]["c"]
        tab = {r["n"]: r for r in a["table"]}
        cd = _engine_cd(os.path.join(root, "data"), a["app_id"], late)
        for N, c in zip(usb.GT_COLS, cells):
            if c is None:
                assert cd["H"] - 1 - N - late < 0
                continue
            r = tab.get(N) or {}
            if r.get("all"):                                   # the dashboard table's own "All time", exactly
                x, n, f, t, _ = c["a"]
                assert (n, f, t) == (r["all"]["users"], r["all"]["from"], r["all"]["to"]) and "ay" not in c
                assert x / n == pytest.approx(r["all"]["p"], abs=6e-6)
                assert c.get("az") == round(r["all"]["z"], 2) and c.get("af", 0) == int(bool(r["all"]["fires"]))
                seen["all"] += 1
            else:                                              # too young for the engine's all time: since the launch
                x, n, k = eng._pool(cd, 0, cd["H"] - 1 - N - late, N, clean=True)
                assert c["a"][:2] == [x, n] and c["ay"] == 1 and c["a"][2] == (cd["hs"]).isoformat()
                seen["young"] += 1
            s = eng.compare(cd, N, late=late)                  # the engine's settled comparison: the last pakka week
            assert c["r"] == [s["recent"]["x"], s["recent"]["users"], s["recent"]["from"], s["recent"]["to"],
                              s["recent"]["k"]]
            seen["last"] += 1
            if s["prev"]:
                assert c["p"] == [s["prev"]["x"], s["prev"]["users"], s["prev"]["from"], s["prev"]["to"]]
                seen["prev"] += 1
            assert c["al"] == int(bool(r.get("alert"))) and c["d"] == r.get("dir")
            if r.get("recent", {}).get("from") == c["r"][2] and r["recent"]["to"] == c["r"][3]:
                assert r["recent"]["users"] == c["r"][1] and r["recent"]["p"] == pytest.approx(c["r"][0] / c["r"][1], abs=6e-6)
                assert "u" not in c
                seen["table_last"] += 1
            elif r.get("recent"):                              # the table shows its newer row: carried as it is
                u = eng.compare(cd, N)["recent"]
                assert c["u"] == [u["x"], u["users"], u["from"], u["to"], u["k"]]
                assert (r["recent"]["from"], r["recent"]["to"], r["recent"]["users"]) == (c["u"][2], c["u"][3], c["u"][1])
                assert r["recent"]["p"] == pytest.approx(c["u"][0] / c["u"][1], abs=6e-6)
                seen["table_newer"] += 1
    assert seen["all"] >= 20 and seen["young"] >= 3 and seen["last"] >= 30 and seen["prev"] >= 20, seen
    assert seen["table_last"] >= 1 and seen["table_newer"] >= 1, seen


def _cohort(hs, E, new, lag_tbl):
    H = (date.fromisoformat(E) - date.fromisoformat(hs)).days + 1
    return {"start": hs, "end": E, "new": [new(i) for i in range(H)],
            "lags": [[[lg, u] for lg, u in lag_tbl if lg <= H - 1 - i] for i in range(H)]}


LAGS = [(0, 10), (1, 3), (2, 2), (3, 1), (5, 1), (7, 1), (10, 2), (14, 1), (20, 1), (30, 2), (40, 1), (45, 1), (50, 1),
        (60, 1), (61, 5), (90, 2), (95, 9)]


def test_since_launch_with_the_settled_cutoff_and_incomplete_days_on_a_hand_made_cohort():
    E, hs = "2026-06-30", "2026-01-01"
    launch, inc = "2026-02-01", "2026-06-01"
    c = _cohort(hs, E, lambda i: 100 + i % 7, LAGS)
    a = {"settled_till": _add(E, -7), "late_days": 7, "launch": {"day": launch, "hidden": True}, "table": [],
         "flags": {"incomplete_days": {inc: {"cov": 0.4}}}, "daily": {"breaks": []}, "history_capped": True}
    out = usb._gtable(a, c)
    assert out["since"] == launch and out["cap"] is True
    for N, cell in zip(usb.GT_COLS, out["c"]):
        top = _add(a["settled_till"], -N)                     # the newest install day whose day N is pakka
        days = []
        d = launch
        while d <= top:
            if not (d <= inc <= _add(d, N)):                  # an incomplete day inside days 0..N: left out (engine)
                days.append(d)
            d = _add(d, 1)
        n = sum(c["new"][(date.fromisoformat(x) - date.fromisoformat(hs)).days] for x in days)
        x = len(days) * sum(u for lg, u in LAGS if lg <= N)
        assert cell["ay"] == 1 and cell["a"][:4] == [x, n, launch, top], N    # no engine table: since the launch
        assert cell["r"][3] <= top and cell["r"][1] > 0


def test_a_broken_app_costs_only_its_own_block(built, tmp_path, monkeypatch, capsys):
    root, site, cfg, dash, _, uni = built
    s = str(tmp_path / "site")
    shutil.copytree(site, s)
    bad = uni["apps"][1]["app_id"]
    real = usb._gtable

    def gt(a, c):
        if a["app_id"] == bad:
            raise KeyError("secret-app")
        return real(a, c)
    monkeypatch.setattr(usb, "_gtable", gt)
    d2 = json.loads(json.dumps(dash))
    d2["uninstall"].pop("studio", None)
    assert build_static._studio_step(d2, os.path.join(root, "data"), s, dict(settings())) == ["/uninstall_studio.json.gz", "/uninstall_studio_old.json.gz"]
    body = _gz(os.path.join(s, usb.FILE))
    assert bad in {a["id"] for a in body["apps"]} and bad not in body["gt"]["apps"]   # the app stays in the Studio
    assert len(body["gt"]["apps"]) == len(body["apps"]) - 1
    err = capsys.readouterr().err
    assert re.match(r"^uninstall studio: apps 4, skipped 0, alerts \d+, no ga4 2, kb \d+, older days kb \d+$", err.strip()) and "secret" not in err


def test_the_file_stays_small(built):
    studio = built[4]
    raw = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()   # noqa: E731
    assert len(gzip.compress(raw(studio), 9, mtime=0)) - len(gzip.compress(raw({k: v for k, v in studio.items() if k != "gt"}), 9, mtime=0)) < 2048


# ── the page ──────────────────────────────────────────────────────────────────────────────────────────────────────

def _heads(panel):
    return [re.sub(r"<[^>]+>.*", "", h) for h in re.findall(r'<th class="[^"]*" data-gsort="[^"]+"[^>]*>(.*?)</th>', panel)]


def test_the_table_sits_under_saari_apps_with_9_day_columns_and_one_icon_per_app(page):
    r = page["30"]
    assert r["afterTbl"] and "<h2>Gone by day N</h2>" in r["panel"] and "All time avg" in r["panel"]
    assert _heads(r["panel"]) == ["App"] + GDL
    rows = re.findall(r'<tr data-app="(\d+)" data-gdgo="\1">(.*?)</tr>', r["panel"])
    assert len(rows) == 4 and r["panel"].count("N/A — ") == 2        # every GA4 app, the no-GA4 ones as N/A
    for _, h in rows:
        assert h.count('class="aicon') == 1                        # exactly one icon (the app_id one)
        assert re.search(r'<div class="us-gsince">All time · since \d{1,2} \w{3}', h)
    assert "Demo Gallery (2026 wala)" in r["panel"]
    assert 'id="us-gq"' in r["panel"] and 'id="us-gfst"' in r["panel"]   # the same search / filters as Saari apps


def test_percent_first_and_big_the_count_second_and_small(page):
    r = page["30"]
    pairs = re.findall(r'<span class="us-gtp">([^<]*)</span><span class="us-gtn">([^<]*)</span>', r["panel"])
    assert len(pairs) >= 25 and all(PCT.match(p) and CNT.match(n) for p, n in pairs), pairs[:4]
    for app in r["cells"]:
        for c in app["c"]:
            if c["all"]:
                assert c["all"]["p"] == pytest.approx(c["all"]["x"] / c["all"]["n"])
    assert not re.search(r"\b100 me\b|1,000 me|per 1,000", r["panel"])
    for i, row in re.findall(r'<tr data-app="(\d+)" data-gdgo="\d+">(.*?)</tr>', r["panel"]):   # the big % IS all time
        tds = re.findall(r'<td[^>]*data-tk="gd:\d+:(\d)"[^>]*>(.*?)</td>', row)
        for k, td in tds:
            c = r["cells"][int(i)]["c"][int(k)]
            m = re.search(r'<span class="us-gtp">([\d.]+)%</span><span class="us-gtn">([^<]*)</span>', td)
            assert (m is None) == (c["all"] is None)
            if m:
                assert abs(float(m.group(1)) - c["all"]["p"] * 100) <= 0.051 and m.group(2).endswith(" gone")


def test_the_table_does_not_follow_the_range(page):
    assert page["7"]["panel"] == page["30"]["panel"] == page["60"]["panel"]
    assert page["7"]["cells"] == page["60"]["cells"]


def test_the_hover_box_shows_the_last_pakka_week_with_its_dates_and_the_change(built, page):
    tips = page["30"]["tips"]
    full = [t for t in tips if "Latest week " in t]
    assert len(full) >= 20
    for t in full:
        assert re.search(r"All time \d+\.\d% installs .+? · [\d,.]+(?: lakh)? of [\d,.]+(?: lakh)? gone", t)
        assert re.search(r"Latest week \d+\.\d% installs \d", t) and re.search(r"Change \d+\.\d% → \d+\.\d%", t)
        # the change line is number-first now: "≈ +30 log (+1.2%) · all-time se zyada gaye" (unchanged: "All-time jitne
        # hi gaye · ≈ ±0 log")
        assert re.search(r"≈ [+−±][\d,.]+(?: lakh)? log \([+−]\d+\.\d%\) · all-time se (?:zyada|kam) gaye|All-time jitne hi gaye · ≈ ±0 log", t)
        assert re.search(r"\(us week ke installs pe\)", t)
        assert re.search(r"\b(Worse|Watch|Better|Normal|Too early)\b", t)
        assert "⏳ Not final · final on " in t and " — " in t     # the newer install days left out, said so
    assert any("Previous 4 weeks " in t for t in full)
    assert any("New installs ⏳ (may still rise) " in t for t in full)   # the engine's newer row, when it shows one
    young = [t for t in tips if "app 8 hafte se nayi" in t]
    assert young and all("Too early" in t for t in young)


def test_the_colour_is_the_last_pakka_week_against_all_time(page):
    cells = {c["id"]: c["c"] for c in page["30"]["cells"]}
    for cs in cells.values():
        for c in cs:
            if c["s"]:                                         # red = more gone than all time (in the week judged:
                e = c["eng"] or c["lat"]                       # the engine's own row when it shows a newer one)
                assert (c["s"] > 0) == (e["p"] > c["all"]["p"])
                assert c["word"] in ("Worse", "Watch", "Better")
            if c["young"]:
                assert c["s"] is None and c["word"] == "Too early"
    words = {c["word"] for cs in cells.values() for c in cs}
    assert words <= {"Worse", "Watch", "Better", "Normal", "Too early", "N/A"}
    # the synthetic big app loses +45% more users from its newest 12 install days (more gone on install day): Worse
    big = max(cells.values(), key=lambda cs: cs[0]["all"]["n"] if cs[0]["all"] else 0)
    assert big[0]["s"] is not None and big[0]["s"] >= 2 and big[0]["word"] == "Worse"
    assert 'class="us-hcell us-gtc us-h' in page["30"]["panel"]


def test_sort_by_change(page):
    rows = re.findall(r'<tr data-app="(\d+)" data-gdgo', page["chg"])
    cells = page["30"]["cells"]
    ch = [(lambda c: None if (not c["all"] or not c["lat"] or c["young"]) else c["lat"]["p"] - c["all"]["p"])(cells[int(i)]["c"][3])
          for i in rows]
    vals = [v for v in ch if v is not None]
    assert vals == sorted(vals, reverse=True) and ch[:len(vals)] == vals    # biggest rise first, unknowns last
    assert 'data-by="chg" aria-pressed="true"' in page["chg"]


def test_the_words(page):
    names = sorted(set(ss.NAMES.values()), key=len, reverse=True)
    texts = []
    for k in ("7", "30", "60"):
        texts += [page[k]["panel"], page[k]["drawer"]] + page[k]["tips"]
    texts += [page["page"], page["chg"]]
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


def test_the_app_view_has_its_9_bars_with_the_numbers_and_the_row(page):
    for h in (page["30"]["drawer"], page["page"]):
        bars = re.findall(r'<div class="us-gbr" data-tk="gd:\d+:(\d)">(.*?)</small></span></div>', h)
        assert [int(k) for k, _ in bars] == list(range(9))
        for _, b in bars:
            v = re.sub(r"<[^>]+>", "", b.split('<span class="us-gbv">')[1])
            assert re.match(r"^\d+\.\d% · latest week \d+\.\d%(?: · new installs \d+\.\d% ⏳)?[\d,]+(?:\.\d+)?(?: lakh)? of [\d,]+(?:\.\d+)?(?: lakh)?$", v), v
            assert 'class="us-gbk' in b                         # the last pakka week marked on the all-time bar
        assert "Gone by day N" in h and len(re.findall(r'<td[^>]*data-tk="gd:\d+:\d"', h)) == 9   # + the table's row


def test_a_file_without_the_block_still_renders(page):
    n = page["nogd"]
    assert n["screen"] and "agle refresh" in n["panel"] and "<table" not in n["panel"]
    assert "us-gbars" not in n["drawer"] and "How many still in app" in n["drawer"]


def test_the_app_views_bars_share_one_track_at_every_width():
    """Mobile audit A-02: a row with a long comparison text squeezed its own bar to a stub (each row was its own grid with
    an auto, nowrap text column), so Day 1 at 35% drew no bar next to Same day at 30%. Every row now sits on the list's own
    columns (subgrid; the text column the widest row's, wrapping past 300px) and a phone puts the text under the bar: the
    bar's length depends on its % only."""
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    rule = lambda sel: re.findall(re.escape(":is(#us-root,#us-layer) " + sel) + r"\{([^}]*)\}", html)
    assert "grid-template-columns:66px minmax(0,1fr) fit-content(300px)" in rule(".us-gbars")[0]
    gbr = rule(".us-gbr")[0]
    assert "grid-column:1/-1" in gbr and "grid-template-columns:subgrid" in gbr
    assert "nowrap" not in rule(".us-gbv")[0] and "nowrap" in rule(".us-gbx")[0]   # wraps between its parts
    for narrow in (r"@container us \(max-width:608px\)\{(:is\(#us-root,#us-layer\) \.us-st\.us-gdt.*?)\}\}", r"@media \(max-width:480px\)\{(:is\(#us-root,#us-layer\) \.us-gbars.*?)\}\}"):
        blk = re.search(narrow, html, re.S).group(1)
        assert re.search(r"\.us-gbr\{grid-column:auto;grid-template-columns:5\dpx minmax\(0,1fr\)", blk), blk   # label | bar
        assert ".us-gbv{grid-column:2;text-align:left" in blk                                                 # text under the bar
