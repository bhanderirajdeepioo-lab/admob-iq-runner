"""💸 Install value Studio — the page (frontend/index.html): the Install value tab's All-apps view and its full app page,
rendered for real by tests/value_studio_frontend.js (the dashboard script in a node vm) from a Studio file the REAL build
code made of a synthetic site (tests/value_studio_synth.py; no real data). Checked here:

  * the one lens — "Ads profit / loss per day" — recomputed independently in Python straight from the file's arrays (the
    judged install weeks, earning by day H × installs − Google Ads spend, ÷ days) for 7 and 30 days, the status words
    that follow from it, and the portfolio = the sum of the apps;
  * the range / compare control IS the dashboard's shared KPIWINDOW (KWIN / KCMP, remembered, the other tabs follow) as
    whole install weeks (7 din = 1 · 14 = 2 · 30 = 4 · 60 = 8; "pichhle mahine" = 4 weeks before); ₹ / $ the dashboard's;
  * the drawer's "Poora app page →" opens the app's page; a refresh keeps an open drawer; the app page is the Studio's
    full-width page with the WHOLE older page in "🗂 Purane views" under it, and the older page alone without the Studio;
  * every value alert in "What's new", with the owner's timestamp line (🕒 Alert aaya in IST, the age chip, Badlaav
    shuru, Data); the Studio's own items and the engine's info say they are not alerts ("🕒 Alert aaya: —");
  * the key numbers printed on the charts (no hover needed);
  * the words (English labels, Hinglish in Roman script only, no banned word, never "100 me" / "1,000 me", no NaN);
  * the rest of the page unaffected (Uninstall and Active users byte-identical with and without the Studio; without its
    file — or when it fails to load — the older All-apps view exactly as before). Skipped where node is not installed."""

import gzip
import json
import math
import os
import re
import shutil
import subprocess

import pytest

from admob_iq import build_static
from admob_iq import value_studio_build as vsb
from admob_iq.config import settings
from tests import value_studio_synth as ss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
BANNED = re.compile(r"\bis hafte\b|\bthis week\b|\babhi ka\b|Provisional|kacch?a\b|kacche|Estimate|/1k|\bpts\b|\bpp\b|\bpoints?\b"
                    r"|cohort|ARPDAU|eCPM|mediation|Stay after|\bsettled\b|\blatest\b|\brecent\b"
                    r"|cumulative|checkpoint|bharosa|headline|\bLTV\b", re.I)
BANNED_CASE = re.compile(r"\bD\d{1,3}\b|\bMix\b|\bHALT\b|\bWIN\b|\bReturning\b|(?<!🆕 )\bNew\b(?!\s(?:vs|week|users|engine|installs|alert))")
DEVA = re.compile("[ऀ-ॿ]")
SIX = {"Worse", "Watch", "Better", "Normal", "Too early", "N/A"}
AGE = re.compile(r"🔔 (🆕 New alert · today \d\d:\d\d|🆕 Yesterday|📌 Open \d+ days|📌 Open since .+|📌 Open from start \(.+\)|📌 Open|✅ Fixed|Band · .+)$")
STUDIO_AGE = re.compile(r"^(🆕 Today|🆕 Yesterday|📌 Open \d+ days|📌 Open since .+|📌 Open)$")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("vstudio_fe"))
    site, cfg, dash = ss.make_site(root)
    assert build_static._value_studio_step(dash, os.path.join(root, "data"), site, dict(settings())) == ["/value_studio.json.gz"]
    fx = os.path.join(root, "fx")
    os.makedirs(fx)
    with gzip.open(os.path.join(site, vsb.FILE), "rt", encoding="utf-8") as f:
        studio = json.load(f)
    for name, body in (("dashboard.json", dash), ("value_studio.json", studio)):
        with open(os.path.join(fx, name), "w", encoding="utf-8") as f:
            json.dump(body, f)
    return fx, dash, studio


@pytest.fixture(scope="module")
def report(built, tmp_path_factory):
    fx, _, _ = built
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    path = str(tmp_path_factory.mktemp("fe") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "value_studio_frontend.js"), path, fx],
                         check=True, capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout)


def J(report, k):
    assert k in report["out"], (k, report["errors"])
    return json.loads(report["out"][k])


def test_renders_without_errors(report):
    assert report["errors"] == []
    assert 'id="vs-root"' in report["out"]["screen7"]


# ── the lens, independently ──────────────────────────────────────────────────────────────────────────────────────

T = [0, 1, 3, 7, 14, 30, 60, 90, 180, 365]


def _app(a):
    """One app of the file, decoded like the page does (independently written here)."""
    nw = len(a["j"])
    v = [None if x is None else x / 1e6 for x in vsb.dec(a["v"])]
    return {"n": vsb.dec(a["n"]), "sp": [None if x is None else x / 100 for x in vsb.dec(a["sp"])],
            "jo": vsb.dec(a["jo"]), "jd": [c == "1" for c in a["j"]], "v": [v[i * 10:i * 10 + 10] for i in range(nw)]}


def _cross(pts, c):
    prev = None
    for t, v in pts:
        if v is None:
            return None
        if v >= c:
            if prev is None or v <= prev[1]:
                return t
            return prev[0] + (c - prev[1]) / (v - prev[1]) * (t - prev[0])
        prev = (t, v)
    return None


def _lens(x, i0, i1, H, spend_min):
    """The page's lens for install weeks i0..i1 (USD): profit / day over the judged weeks that have their earning by day
    H, the margin, and whether the pooled money never comes back within a year (the status words' inputs)."""
    JH, n_ = T.index(H), len(x["n"])
    jw = jn = 0
    jsU = r90U = profV = 0.0
    spU = 0.0
    spW = cw = 0
    cs = cn = 0.0
    minjo = 9
    R, ok = [0.0] * 10, [True] * 10
    for i in range(max(0, i0), min(n_ - 1, i1) + 1):
        n, sp, v, jo = x["n"][i], x["sp"][i], x["v"][i], x["jo"][i]
        if n is None:
            continue
        if sp is not None:
            spW += 1
            spU += sp
        if x["jd"][i] and sp is not None and sp > 0 and n > 0:
            if v[JH] is not None:
                jw += 1
                jn += n
                jsU += sp
                r90U += n * v[JH]
                profV += n * v[JH] - sp
            if v[0] is not None:
                cw += 1
                cn += n
                cs += sp
                minjo = min(minjo, max(0, jo))
                for j in range(10):
                    if v[j] is None:
                        ok[j] = False
                        continue
                    R[j] += n * v[j]
    for j in range(1, 10):
        if not ok[j - 1]:
            ok[j] = False
    never = False
    if cw and cs > 0:
        C = [R[j] / cs if ok[j] else None for j in range(10)]
        pts = list(zip(T, C))
        if _cross(pts[:minjo + 1], 1) is None:
            if minjo >= 9:
                never = True
            elif _cross(pts, 1) is None and C[9] is not None:
                never = True
    ads = spU > 0
    thin = ads and not jw and not cw and spW > 0 and spU / spW < spend_min
    return {"profD": profV / (7 * jw) if jw else None, "marg": r90U / jsU - 1 if jsU > 0 else None, "ads": ads, "thin": thin,
            "never": never, "jw": jw}


def _pill(L):
    if not L["ads"] or L["thin"]:
        return "lagu"
    if L["never"]:
        return "bigda"
    if not L["jw"] or L["marg"] is None:
        return "jaldi"
    return "behtar" if L["marg"] >= .05 else ("normal" if L["marg"] > -.05 else "dhyan")


@pytest.mark.parametrize("key,weeks", [("rows7", 1), ("rows30", 4), ("rows30m", 4)])
def test_the_profit_lens_recomputed_independently(report, built, key, weeks):
    _, _, studio = built
    M = studio["meta"]
    got = J(report, key)
    i1 = M["nw"] - 1
    i0 = i1 - (weeks - 1)
    assert got["W"]["i1"] == i1 and got["W"]["i0"] == i0 and got["W"]["L"] == weeks
    if key == "rows30m":
        assert got["W"]["c0"] == i0 - 4 and got["W"]["c1"] == i0 - 1    # "pichhle mahine" = the 4 weeks before
    else:
        assert got["W"]["c1"] == i0 - 1 and got["W"]["cL"] == weeks       # the previous, same number of weeks
    by = {a["id"]: a for a in studio["apps"]}
    seen = 0
    tot = 0.0
    for r in got["rows"]:
        L = _lens(_app(by[r["id"]]), i0, i1, M["H"], (M["consts"] or {}).get("spend_min_week") or 20)
        if L["profD"] is None:
            assert r["profD"] is None, r
        else:
            assert r["profD"] == pytest.approx(L["profD"], rel=1e-9, abs=1e-9), r["nm"]
            seen += 1
        assert r["ads"] == L["ads"] and r["thin"] == L["thin"] and r["never"] == L["never"] and r["jw"] == L["jw"]
        assert r["pill"] == _pill(L), (r["nm"], r["pill"], L)
        if L["ads"] and not L["thin"] and L["profD"] is not None:
            tot += L["profD"]
    assert seen >= 1
    assert got["PT"]["profD"] == pytest.approx(tot)                         # the portfolio = the sum of the apps


def test_only_the_six_status_words(report):
    words = set()
    for h in [report["out"]["screen7"], report["out"]["chg"]]:
        words |= set(re.findall(r'<span class="vs-chip vs-st-\w+"><i></i>([^<]+)</span>', h))
    assert words and words <= SIX, words


# ── the shared KPIWINDOW, ₹ / $ ─────────────────────────────────────────────────────────────────────────────────

def test_range_and_compare_are_the_dashboards_shared_choice(report, built):
    _, dash, _ = built
    k = J(report, "kwin")
    assert k["weeks"] == {"7": 1, "14": 2, "30": 4, "60": 8}               # whole install weeks
    assert k["win30"]
    assert k["after14"] == {"KWIN": "14", "L": 2, "saved": "14"}           # the Studio sets it → remembered, shared
    assert k["custom"]["KWIN"] == "custom" and k["custom"]["from"] < k["custom"]["to"] and k["custom"]["L"] == 2
    assert k["dates"] == {"KWIN": "custom", "L": 6}
    assert k["month"] == {"KCMP": "month", "saved": "month", "gap": 4, "overlap": False}
    assert k["prev"] == {"L": 4, "cL": 4, "adj": True}
    assert k["cdates"]["KCMP"] == "custom" and k["cdates"]["cL"] == 2
    assert k["fx"] == dash["usd_inr"] == ss.FX
    assert k["inr"] == "₹1,000" and k["inrTiny"] == "~₹0" and k["inrP"] == "₹2.50"
    assert k["usd"] == "$1,000" and k["usdTiny"] == "~$0" and k["usdP"] == "$0.042"
    assert J(report, "header") == {"p60": True, "month": True, "inr": True}


# ── the drawer, the full app page ─────────────────────────────────────────────────────────────────────────────────

def test_drawer_poora_app_page_and_refresh(report, built):
    _, _, studio = built
    d = J(report, "drawer")
    assert d["open"] and d["full"] >= 2 and d["dataFull"] and d["lock"]
    assert d["afterRefresh"]                                                # the 5-minute refresh never wipes an open drawer
    big = next(a["id"] for a in studio["apps"] if a["sz"] == "badi")
    assert d["calls"] == [big] and d["closed"]                              # "Poora app page →" → the app's page
    assert any(t.startswith("money back: ") for t in d["labels"]), d["labels"]   # the payback point, printed
    assert any(re.match(r"^≈?[−+]?\$[\d,.]+ \(\d+% back\)$", t) for t in d["labels"]), d["labels"]   # the latest, number then %


def test_the_full_app_page(report):
    p = J(report, "page")
    assert p["closedDrawer"] and p["mode"] == "p" and p["root"] and p["pg"] and p["back"] and p["sections"]
    assert p["fold"] and p["foldAfter"] and p["oldInside"]                 # the WHOLE older page, under the Studio's
    assert p["range60"]                                                     # on the shared range
    assert p["noPtrSame"]                                                   # no Studio file: the older page exactly
    assert p.get("nogaOld", True)                                           # an app the Studio has nothing for: the older page
    assert any("→" in t and t.startswith("📦 v") for t in p["labels"]), p["labels"]   # 📦 version: before → after


# ── what's new: every alert with the owner's timestamp line ─────────────────────────────────────────────────────

def test_whats_new_keeps_every_alert_with_its_timestamps(report, built):
    _, dash, _ = built
    al = J(report, "alerts")
    want = {x["id"] for x in dash["value"]["alerts"]}
    assert want and {x["id"] for x in al if not x["closed"]} == want        # every open alert of the Studio's apps
    chg = report["out"]["chg"]
    cards = re.split(r'<div class="vs-ac ', chg)[1:]
    alert_cards = [c for c in cards if '<span class="vs-itag">' in c and "🔔 " in c]
    assert len(alert_cards) == len(want)
    for c in alert_cards:
        t = re.sub(r"<[^>]+>", "", c)
        assert "🕒 Alert time: " in t and " IST" in t and "Change started: " in t and "Data: " in t, t[:300]
        age = re.search(r'class="vs-age[^"]*"[^>]*>([^<]+)<', c).group(1)
        assert AGE.match(age), age
    for c in cards:
        if c in alert_cards:
            continue
        t = re.sub(r"<[^>]+>", "", c)
        assert "🕒 Alert time: — (" in t and "Change started: " in t and "Data: " in t, t[:300]   # not an alert, and says so
        age = re.search(r'class="vs-age[^"]*"[^>]*>([^<]+)<', c).group(1)
        assert STUDIO_AGE.match(age), age
    tbl = report["out"]["chgTable"]
    assert tbl.count("<tr data-app=") >= len(want) and "🕒 Alert time" in tbl


# ── the numbers printed on the charts ───────────────────────────────────────────────────────────────────────────

def test_the_charts_print_their_numbers(report):
    L = J(report, "labels")
    k = L["kpi"]
    assert any(t.startswith("range ") for t in k) and any(t.startswith("🎯 ") for t in k) and any(t.startswith("avg ") for t in k)
    assert any(re.search(r"\d+% *$", t) and "·" in t for t in k)            # back in 7 days: the money, then the %
    assert L["map"] >= 2                                                    # every app's 12 weeks: the latest
    assert len(L["tl"]) >= 1                                                # the timeline: the latest week at least


def test_back_in_7_days_tile_clean_empty_state(report):
    """vs-k-b7 (the portfolio 'Back in 7 days' KPI tile): the default 7-day window has no settled install week yet
    (data-v=""), so the big number must be a clean "—" — never the old "— of — · —" — and the small line must give
    a short Hinglish reason instead of the "of <blank>" trailer."""
    screen7 = report["out"]["screen7"]
    i = screen7.index('<div class="vs-kpi" id="vs-k-b7">')
    j = screen7.index('<div class="vs-kpi"', i + 1)
    tile = screen7[i:j]
    kv = re.search(r'<div class="vs-kv">(.*?)</div>', tile, re.S).group(1)
    ks = re.search(r'<div class="vs-ks">(.*?)</div>', tile, re.S).group(1)
    assert 'data-v=""' in kv, "fixture's default 7-day window is expected to have no settled week yet"
    assert re.sub(r"<[^>]+>", "", kv).strip() == "—"                        # a clean dash, never "— of — · —"
    assert "of " not in kv and "·" not in kv
    assert "7 din ka data abhi nahi" in ks


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
        assert not re.search(r"\b100 me\b|\b1,000 me\b|\bhar 1,000\b|\bper 100\b", u), u[:200]
    full = texts[0]
    for nm in ("Demo Spend App (2025 wala) · Studio Two", "Demo Organic App · Studio Two", "Demo Young App · Studio Two",
               "Demo Clock · A/c 3003"):
        assert nm in full, nm                                               # app names always with the account


# ── the rest of the page ───────────────────────────────────────────────────────────────────────────────────────

def test_other_tabs_and_the_older_view_are_unaffected(report):
    o = J(report, "others")
    assert o["uninstall_same"] and o["active_same"]
    assert o["old_is_portfolio"] and o["old_view"] == {"studio": False, "kw": True, "table": True}
    v = o["studio_view"]
    assert v["root"] and not v["kw"] and v["fold"] and all(v["folded"])     # every older All-apps section in "Purane views"
    s = J(report, "states")
    assert s["wait"] and s["back"]
    assert s["failed"] and s["failedRest"]                                  # a failed load: the older view + "Try again"
    assert s["pend"]                                                        # an app whose file is still coming: still listed


def test_the_page_script_scopes_the_studio():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    css = html[html.index("INSTALL VALUE STUDIO (the Install value tab's All-apps view)"):html.index("UNINSTALL STUDIO (the Uninstall tab's All-apps view)")]
    css = re.sub(r"/\*.*?\*/", "", css[css.index("*/") + 2:], flags=re.S)
    for rule in re.findall(r"([^{}]+)\{[^{}]*\}", re.sub(r"@(media|container)[^{]*\{", "", css)):
        for sel in rule.replace(":is(#vs-root,#vs-layer)", "§").split(","):
            sel = sel.replace("§", ":is(#vs-root,#vs-layer)").strip()
            if not sel or sel.startswith(("@", "from", "to", "0%", "100%")) or re.match(r"^[\d%,\s]+$", sel):
                continue
            assert sel.startswith((":is(#vs-root,#vs-layer)", "#vs-root", "#vs-layer", "#val-old", "#val-oldapp", "#vs-main",
                                   "body:not([data-screen=\"value\"]) #vs-layer", "body.vs-lock")), sel
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    blk = js[js.index("const VS=(function(){"):js.index("function renderValue(){")]
    for cls in re.findall(r'class="([^"$]+)"', blk):                           # every static class is a Studio one
        for c in cls.split():
            assert c.startswith("vs-"), c
    for i in re.findall(r'\bid="([^"$]+)"', blk):
        assert i.startswith("vs-"), i
    assert "if(!shownNow()) return;" in blk and "tg.tagName==='INPUT'" in blk      # keys: this tab only, never while typing
    assert "if(id==='value') valEnsure();" in js and "if(id==='value') VS.ensure(()=>valRerender());" in js
