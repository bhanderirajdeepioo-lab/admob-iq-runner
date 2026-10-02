"""🧭 Active users Studio — the page (frontend/index.html): the Active users tab's All-apps view and one app's page,
rendered for real by tests/active_studio_frontend.js (the dashboard script in a node vm) from a Studio file the REAL build
code made of a synthetic site (tests/active_studio_synth.py; no real data). Checked here:

  * the "Users ka farak" lens, recomputed independently in Python straight from the file's arrays (the same-weekday
    normal of the 28 days before the range, the engine's installs split, the noise test) for 7 and 30 days, and the
    portfolio as the sum of its apps;
  * one order everywhere: map #1 = rank 1 = the 🔥 card; no "Behtar" pill with a real loss; only the six status words;
  * the range / compare control IS the dashboard's shared KPIWINDOW (KWIN / KCMP, remembered, the other tabs follow); ₹ / $
    and the fx are the dashboard's;
  * the drawer's "Poora app page →" opens the app's page; a refresh keeps an open drawer; an app page closes it;
  * one app's page: the Studio's page first, the WHOLE older app page folded under it (a jump into it opens the fold);
    without the Studio's file the older page exactly as before;
  * every "What changed?" alert, with the owner's timestamp line (🕒 Alert aaya in IST, the age chip, Badlaav shuru, Data);
  * the numbers printed on the charts (latest values, averages, the 📦 before → after, the alert days; never two labels
    on top of each other);
  * the words (English labels, Hinglish in Roman script only, no banned word, never "100 me" / "1,000 me", no NaN);
  * the rest of the page unaffected (Uninstall and Install value byte-identical with and without the Studio; without its
    file the older All-apps view exactly as before; a file that fails to load says so, with Try again). Skipped where
    node is not installed."""

import gzip
import json
import math
import os
import re
import shutil
import subprocess
from datetime import date

import pytest

from admob_iq import active_studio_build as asb
from admob_iq import build_static
from admob_iq.config import settings
from tests import active_studio_synth as ss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
BANNED = re.compile(r"\bis hafte\b|\bthis week\b|\babhi ka\b|Provisional|kacch?a\b|kacche|Estimate|/1k|\bpts\b|\bpp\b|\bpoints?\b"
                    r"|cohort|ARPDAU|eCPM|mediation|Stay after|\bsettled\b|\blatest\b|\brecent\b", re.I)
# narrowed: the English 🆕 chips ("🆕 New", "🆕 New alert · today", "New users", "New vs old", "New engine alerts") are
# wanted now — ban only a standalone OLD "New" pill (not preceded by "🆕 ", not followed by a word that makes it one
# of the wanted phrases above)
BANNED_CASE = re.compile(r"(?<!🆕 )\bNew\b(?! (?:engine|vs|users|alert))|\bD\d{1,3}\b|\bMix\b|\bHALT\b|\bWIN\b|\bReturning\b")
DEVA = re.compile("[ऀ-ॿ]")
SIX = {"Worse", "Watch", "Better", "Normal", "Too early", "N/A"}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("astudio_fe"))
    site, cfg, dash = ss.make_site(root)
    assert build_static._active_studio_step(dash, os.path.join(root, "data"), site, dict(settings())) == ["/active_studio.json.gz"]
    fx = os.path.join(root, "fx")
    os.makedirs(fx)
    with gzip.open(os.path.join(site, asb.FILE), "rt", encoding="utf-8") as f:
        studio = json.load(f)
    files = {}
    for r in dash["active"]["apps"]:                           # each app's own file (the older app page, in full)
        with gzip.open(os.path.join(site, r["file"]), "rt", encoding="utf-8") as f:
            files[r["key"]] = json.load(f)
    for name, body in (("dashboard.json", dash), ("active_studio.json", studio), ("active_files.json", files)):
        with open(os.path.join(fx, name), "w", encoding="utf-8") as f:
            json.dump(body, f)
    return fx, dash, studio


@pytest.fixture(scope="module")
def report(built, tmp_path_factory):
    fx, _, _ = built
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    path = str(tmp_path_factory.mktemp("afe") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "active_studio_frontend.js"), path, fx],
                         check=True, capture_output=True, text=True, timeout=600)
    return json.loads(out.stdout)


def J(report, k):
    assert k in report["out"], (k, report["errors"])
    return json.loads(report["out"][k])


def test_renders_without_errors(report):
    assert report["errors"] == []
    assert 'id="as-root"' in report["out"]["screen7"] and 'id="act-old"' in report["out"]["screen7"]


# ── the lens, independently ──────────────────────────────────────────────────────────────────────────────────────

def _d(s):
    return date.fromisoformat(s)


def _app(a, M):
    """One app of the file, decoded like the page does (independently written here)."""
    S, N = _d(M["S"]), M["n"]
    x = {k: asb.dec(a[k]) for k in ("rt", "y", "nw", "rv", "a1")}
    x["rv"] = [None if v is None else v / 1000 for v in x["rv"]]
    x["pre"] = asb.dec(a["pre"])
    x["sh"] = [v / 1e5 for v in asb.dec(a["sh"])]
    x["K"] = a["K"]
    x["fi"] = max(0, (_d(a["first"]) - S).days)
    x["si"] = min(N - 1, (_d(a["settled"]) - S).days)
    x["wd0"] = (S.weekday() + 1) % 7                     # the page counts weekdays from Sunday (getUTCDay)
    x["stp"] = [((_d(f) - S).days, (_d(t) - S).days) for f, t in a["steep"]]
    x["ready"], x["nz"] = a["ready"], a["nz"]
    return x


def _sg(g, L, LG):
    pts = [(math.log(l), g[k] / 1e4) for k, l in enumerate(LG) if g[k] is not None]
    if not pts or not L:
        return None
    xv = math.log(L)
    if xv <= pts[0][0]:
        return pts[0][1]
    if xv >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if xv <= x1:
            return y0 + (y1 - y0) * (xv - x0) / (x1 - x0)
    return None


def _lens(x, F, T, N, LG):
    """The page's "Users ka farak" for range days F..T (span indices)."""
    i0, i1, b0, b1 = max(F, x["fi"]), min(T, x["si"], N - 1), F - 28, F - 1
    if T < x["fi"] or i1 < i0 or b0 < x["fi"] or b0 < 0:
        return None
    rt, y = x["rt"], x["y"]
    B = [i for i in range(b0, b1 + 1) if rt[i] is not None and y[i] is not None]
    Wd = [i for i in range(i0, i1 + 1) if rt[i] is not None and y[i] is not None]
    if len(B) < 21 or not Wd:
        return None
    wd = lambda i: (x["wd0"] + i) % 7
    ws, wc = [0.0] * 7, [0] * 7
    for i in B:
        ws[wd(i)] += rt[i]
        wc[wd(i)] += 1
    base = sum(rt[i] for i in B) / len(B)
    far = sum(rt[i] - (ws[wd(i)] / wc[wd(i)] if wc[wd(i)] else base) for i in Wd) / len(Wd)
    yb = sum(y[i] for i in B) / len(B)
    fi = None
    steep = any(f <= i1 and t >= i1 - 6 for f, t in x["stp"])
    if x["ready"] and not steep and x["K"] and x["sh"]:
        def nwat(i):
            if i >= 0:
                return x["nw"][i] if i < N else None
            return x["pre"][len(x["pre"]) + i] if i >= -len(x["pre"]) else "missing"

        def wn(days):
            s = 0.0
            for k in range(1, x["K"] + 1):
                t = 0.0
                for i in days:
                    v = nwat(i - k)
                    if v == "missing":
                        return None
                    t += v or 0
                s += x["sh"][k - 1] * t / len(days)
            return s
        nb, na = wn(B), wn(Wd)
        if nb and na is not None and nb > 0:
            fi = yb * (na / nb - 1)
    asli = None if fi is None else far - fi
    L = len(Wd)
    sT, sA = _sg(x["nz"]["t"], L, LG), _sg(x["nz"]["a"], L, LG)
    zT = math.log1p(far / base) / sT if sT and far / base > -1 else None
    zA = math.log1p(asli / base) / sA if sA and asli is not None and asli / base > -1 else None
    return {"far": far, "fi": fi, "asli": asli, "base": base, "zT": zT, "zA": zA, "n": L,
            "sigT": zT is not None and abs(zT) >= 2, "sigA": zA is not None and abs(zA) >= 2}


@pytest.mark.parametrize("key,days", [("order7", 7), ("rows30", 30)])
def test_the_users_ka_farak_lens_recomputed_independently(report, built, key, days):
    _, _, studio = built
    M = studio["meta"]
    got = J(report, key)
    assert got["W"]["L"] == days and got["W"]["t"] == M["E"]
    N = M["n"]
    T = N - 1
    F = T - (days - 1)
    real = 0
    for r in got["rows"]:
        L = _lens(_app(studio["apps"][r["i"]], M), F, T, N, M["LG"])
        if L is None:
            assert "why" in r["L"] and r["L"]["why"], r
            continue
        g = r["L"]
        for k in ("far", "base", "zT"):
            assert g[k] == pytest.approx(L[k], rel=1e-9, abs=1e-9), (r["nm"], k)
        for k in ("fi", "asli", "zA"):
            assert (g[k] is None) == (L[k] is None) and (L[k] is None or g[k] == pytest.approx(L[k], rel=1e-9, abs=1e-9)), (r["nm"], k)
        assert g["sigT"] == L["sigT"] and g["sigA"] == L["sigA"] and g["n"] == L["n"]
        if g["fi"] is not None:
            assert g["far"] == pytest.approx(g["fi"] + g["asli"])            # installs + asli — no double counting
        real += L["sigA"]
    assert real >= 1                                                           # (the synthetic site has a real change)


def test_the_portfolio_farak_is_the_sum_of_the_apps(report):
    o = J(report, "order7")
    rows = [r for r in o["rows"] if "far" in r["L"]]
    assert o["PT"]["nL"] == len(rows)
    assert o["PT"]["Lfar"] == pytest.approx(sum(r["L"]["far"] for r in rows))
    assert o["PT"]["Lfi"] == pytest.approx(sum(r["L"]["fi"] or 0 for r in rows))
    assert o["PT"]["Lasli"] == pytest.approx(sum(r["L"]["asli"] or 0 for r in rows))
    assert o["PT"]["Lusd"] == pytest.approx(sum(r["L"]["usd"] or 0 for r in rows))
    assert o["PT"]["Lfar"] == pytest.approx(o["PT"]["Lfi"] + o["PT"]["Lasli"] + o["PT"]["Lnone"])


# ── one order, consistent words ──────────────────────────────────────────────────────────────────────────────────

def test_one_order_map_and_the_story_cards(report):
    o = J(report, "order7")
    assert o["map1"] == o["rank1"] == o["loss"], o                 # the biggest farak tops the map and is the 🔥 card
    assert o["names"][o["loss"]] == "Demo Photos (2025 wala) · Studio One"
    assert o["names"][o["gain"]] == "Demo Notes · Studio One"
    torch = next(r for r in o["rows"] if r["nm"].startswith("Demo Torch"))
    assert torch["L"]["fi"] > 0.5 * torch["L"]["far"] > 0                    # the installs explain its change


@pytest.mark.parametrize("key", ["order7", "rows30"])
def test_pills_never_contradict_the_lens_or_the_alerts(report, key):
    for r in J(report, key)["rows"]:
        L, red = r["L"], any(c is not None and c >= 2 for c in r["cells"])
        assert r["pill"] in ("bigda", "dhyan", "behtar", "normal", "jaldi")
        if r["pill"] == "behtar":
            assert not red and (r["alP"] == "behtar" or (L.get("asli") or 0) > 0), r
        if r["pill"] == "bigda":
            assert r["alP"] == "bigda" or (L.get("asli") or 0) < 0, r
        if r["alP"] == "bigda":
            assert r["pill"] == "bigda", r                              # an open engine alert decides when more severe


def test_only_the_six_status_words(report):
    words = set()
    for h in [report["out"]["screen7"], report["out"]["chg"]]:
        words |= set(re.findall(r'<span class="as-chip as-st-\w+"><i></i>([^<]+)</span>', h))
    assert words and words <= SIX, words


# ── the shared KPIWINDOW, ₹ / $ ─────────────────────────────────────────────────────────────────────────────────

def test_range_and_compare_are_the_dashboards_shared_choice(report, built):
    _, _, studio = built
    k = J(report, "kwin")
    E = studio["meta"]["E"]
    assert k["ext30"] == 30 and k["win30"]                     # KWIN set elsewhere → the Studio shows it
    assert k["after14"] == {"KWIN": "14", "L": 14, "saved": "14"}   # the Studio sets it → remembered, shared
    assert k["custom"]["KWIN"] == "custom" and k["custom"]["to"] == E and k["custom"]["L"] == 14
    assert k["month"]["KCMP"] == "month" and k["month"]["saved"] == "month"
    W = k["month"]["W"]
    assert W["ct"] < W["f"]                                    # a month back, never overlapping the range
    assert k["dates"]["KWIN"] == "custom" and k["dates"]["L"] == 10 and k["dates"]["to"] == E
    assert k["cdates"]["KCMP"] == "custom" and k["cdates"]["from"] < k["cdates"]["to"]   # (dates given the wrong way round)
    assert k["fx"] == ss.FX and k["inr"] == "₹832" and k["usd"] == "$10" and k["inrTiny"] == "~₹0" and k["usdTiny"] == "~$0"
    assert J(report, "header") == {"p60": True, "month": True, "usd": True}


# ── the drawer and one app's page ────────────────────────────────────────────────────────────────────────────────

def test_drawer_full_app_page_refresh_and_app_page(report, built):
    _, _, studio = built
    d = J(report, "drawer")
    assert d["open"] and d["full"] >= 2 and d["dataFull"] and d["lock"]
    assert d["afterRefresh"]                                   # the 5-minute refresh never wipes an open drawer
    assert d["calls"] == [studio["apps"][0]["id"]] and d["closed"]   # "Poora app page →" → the app's own page
    assert d["closedOnAppPage"]


def test_one_apps_page_is_the_studio_with_the_whole_older_page_folded_under_it(report):
    p = J(report, "page")
    assert p["mode"] == "page"
    i_root, i_pg_root, i_pg, i_old = p["order"]
    assert 0 <= i_root < i_pg < i_old and i_pg_root > 0          # the Studio's page, then "🗂 Purane views"
    assert p["oldInFold"] and p["oldFull"]                      # the older app page, whole, inside the fold
    assert "🗂 Old views" in p["html"] and p["html"].count('id="act-') >= 5   # label renamed (GLOSSARY §3; was "Purane views")
    assert p["noPtrSame"]                                       # no Studio file: the older page exactly as before
    assert p["win30"]                                           # the page follows the shared range
    assert p["foldOpenOnJump"]                                  # a jump into the older page (Alerts → this app) opens it


# ── "How many new users came back": every install week (owner, 2 Oct: "13-19 july tak hi kyu? pura data hona chaiye") ──

def test_came_back_grid_shows_every_week_of_the_older_table(report):
    t = J(report, "tri")
    W, old = t["weeks"], t["old"]
    assert len(W) > 10 and [w["f"] for w in W] == [o["w"] for o in old]        # the older table's weeks, all, newest first
    for view in ("page", "drawer"):
        rows = [x for x in t[view] if x["k"] == "rh"][1:]                       # (row 1 = All-time normal)
        assert len(rows) == len(W), view
        assert [x["t"].split(" 📦")[0].split(" ")[0] for x in rows] == [o["lab"].split(" ")[0] for o in old], view
        # a year row over each year's weeks (these weeks cross a year), oldest at the bottom
        yrs = [x["t"] for x in t[view] if x["k"] == "cyr"]
        assert yrs == sorted(yrs, reverse=True) and len(yrs) >= 2 and all(re.fullmatch(r"── \d{4} ──", y) for y in yrs)
        # 📦 a line right ABOVE the week each update fell in (old weeks too), the week's label carries a 📦
        seq = t[view]
        lines = [(i, x["t"]) for i, x in enumerate(seq) if x["k"] == "crel"]
        assert any("v0.5" in l for _, l in lines) and any(re.search(r"v0\.7 \(.*\) · Update \(", l) for _, l in lines)
        for i, l in lines:
            assert seq[i + 1]["k"] == "rh" and "📦" in seq[i + 1]["t"] and re.search(r"— (mid-week|week start)$", l)
        # a week GA4 gave no return data for: its row says "No data" (as the older table), never a 0
        nd = [x["t"] for x in seq if x["k"] == "nd"]
        assert nd == ["No data"]
        # a partial week says how many days
        assert any(re.search(r"\(only \d+ days?\)", x["t"]) for x in rows)
    assert t["pageHead"].startswith("Install week × day · all %d weeks " % len(W)) and "saare hafte" in t["pageHead"]
    assert "No data — GA4 ne us hafte ke installs ka wapsi data nahi diya" in t["tipNd"]
    assert "📦 v0.7" in t["tipRel"] and "Update hafte ke" in t["tipRel"]
    words = " ".join([t["tipNd"], t["tipRel"], t["pageHead"]] + [x["t"] for x in t["page"]])
    for n in sorted(set(ss.NAMES.values()), key=len, reverse=True):
        words = words.replace(n, "<app>")
    assert not (BANNED.search(words) or BANNED_CASE.search(words) or DEVA.search(words)) and "NaN" not in words


def test_came_back_grid_scrolls_in_its_box_with_its_column_names_on_top():
    css = open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read()
    assert re.search(r"\.as-cohw\{overflow:auto;max-height:min\(70vh,720px\)", css)
    assert re.search(r"\.as-cohw \.as-coh \.as-chh\{position:sticky;top:0;z-index:3;background:var\(--panel\)", css)
    assert re.search(r"\.as-cohw \.as-coh \.as-rh,:is\(#as-root,#as-layer\) \.as-cohw \.as-coh \.as-stk\{position:sticky;left:0", css)
    assert re.search(r"\(pointer:coarse\)\{:is\(#as-root,#as-layer\) \.as-coh \.as-relb\{display:inline-block;padding:9px", css)


# ── every alert, with the owner's timestamp line ───────────────────────────────────────────────────────────────

def test_what_changed_keeps_every_alert_with_its_timestamps(report):
    al = J(report, "alerts")
    chg = report["out"]["chg"]
    assert al and sorted(int(k) for k in re.findall(r'data-alk="(\d+)"', chg)) == sorted(x["k"] for x in al)
    cards = re.split(r'<div class="as-ac ', chg)[1:]
    assert len(cards) == len(al)
    for c, x in zip(cards, al):
        assert "Change started: " in c and "Data: " in c   # "Badlaav shuru:" -> "Change started:"
        if 'as-s-info' in c[:40]:
            continue                                           # an engine info row (not an alert): 🕒 Data · Change started
        assert "🕒 Alert time: " in c and " IST" in c   # "Alert aaya:" -> "Alert time:"
        assert re.search(r'class="as-age[^"]*"[^>]*>🔔 (🆕 New alert · today \d\d:\d\d|🆕 Yesterday|📌 Open \d+ days|📌 Open since .+'
                         r'|📌 Open from start \(.+\)|✅ Closed|📌 Open)<', c), c[:300]
    rows = re.split(r"<tr data-app=", report["out"]["chgTable"])[1:]
    assert rows and all("Change started: " in r and "Data: " in r for r in rows)
    assert all("🕒 Alert time: " in r for r in rows if "ℹ️ Info" not in r)


# ── the numbers printed on the charts ────────────────────────────────────────────────────────────────────────────

def test_the_charts_print_their_numbers_without_hover(report):
    c = J(report, "charts")
    assert all(len(s) >= 1 for s in c["kpis"]) and all(len(s) >= 1 for s in c["kpis2"])   # each line's latest value
    assert any(t.startswith("avg ") for s in c["kpis"] for t in s)
    assert any(re.match(r"^[\d,]+ \(\d+\.\d%\)$", t) for s in c["kpis"] for t in s)      # number first, % beside
    assert c["map"] >= 4                                       # every map row's trend carries its latest value
    assert any(t.startswith("avg ") for t in c["tl"]) and any(" → " in t for t in c["tl"])
    d = c["drawer"]
    assert any(t.startswith("chosen range · difference ") and t.endswith("%)") for t in d)    # the range's farak -> "difference", users/day
    assert any(t.startswith("normal ") for t in d) and any(t.startswith("avg ") for t in d)
    assert any(t.startswith(c["rel"][0] + " · ") and " → " in t for t in d)             # 📦 version + before → after
    assert any(re.match(r"^\d{1,2} [A-Z][a-z]{2} · ", t) for t in d)                     # an alert day + its number
    assert not c["overlap"] and c["inside"] and c["fitN"] > 5 and c["prio"] == ["high"]  # never on top of each other


# ── the words ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_words(report):
    texts = json.loads(report["out"]["texts"])
    assert len(texts) > 40
    names = sorted(set(ss.NAMES.values()), key=len, reverse=True)
    for t in texts:
        for w in ("undefined", "NaN", "[object Object]", "Infinity"):
            assert w not in t, (w, t[:200])
        assert not DEVA.search(t)
        u = t
        for n in names:
            u = u.replace(n, "<app>")
        m = BANNED.search(u) or BANNED_CASE.search(u)
        assert not m, (m.group(0), u[max(0, m.start() - 80):m.end() + 40])
        assert not re.search(r"\b100 me\b|\b1,000 me\b|\bhar 1,000\b|\bper 1,000\b|\bper 100\b", u), u[:200]
    full = texts[0]
    for nm in ("Demo Photos (2025 wala) · Studio One", "Demo Notes · Studio One", "Demo Torch · A/c 4004", "Demo Young · A/c 4004",
               "Demo Clock · A/c 4004"):
        assert nm in full, nm                                 # app names always with the account


# ── the rest of the page ───────────────────────────────────────────────────────────────────────────────────────

def test_other_tabs_and_the_older_views_are_unaffected(report):
    o = J(report, "others")
    assert o["uninstall_same"] and o["value_same"]
    assert o["old_view"] == {"studio": False, "sum": True, "table": True, "note": False}   # no Studio file: as before
    assert o["old_is_portfolio"]
    sv = o["studio_view"]
    assert sv["root"] and sv["fold"] and all(sv["folded"]) and sv["splitBlocks"]   # every older section in "Purane views"
    assert J(report, "loading") == {"wait": True, "failed": True, "back": True}


def test_the_page_script_scopes_the_studio():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    css = html[html.index("ACTIVE USERS STUDIO (the Active users tab's All-apps view"):html.index("/* ===== /ACTIVE USERS STUDIO ===== */")]
    css = re.sub(r"/\*.*?\*/", "", css[css.index("*/") + 2:], flags=re.S)
    for rule in re.findall(r"([^{}]+)\{[^{}]*\}", re.sub(r"@(media|container)[^{]*\{", "", css)):
        for sel in rule.replace(":is(#as-root,#as-layer)", "§").split(","):
            sel = sel.replace("§", ":is(#as-root,#as-layer)").strip()
            if not sel or sel.startswith(("/*", "@", "from", "to", "0%", "100%")) or re.match(r"^[\d%,\s]+$", sel):
                continue
            assert sel.startswith((":is(#as-root,#as-layer)", "#as-root", "#as-layer", "#act-old", "#as-main",
                                   "body:not([data-screen=\"active\"]) #as-layer", "body.as-lock")), sel
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    blk = js[js.index("const AS=(function(){"):js.index("// ---------- 👥 ACTIVE USERS (GA4) ----------")]
    for cls in re.findall(r'class="([^"$\'+]+)"', blk):                        # every static class is a Studio one
        for c in cls.split():
            assert c.startswith("as-"), c
    for i in re.findall(r'\bid="([^"$]+)"', blk):
        assert i.startswith("as-"), i
