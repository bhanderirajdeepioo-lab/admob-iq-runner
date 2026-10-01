"""🧭 Uninstall Studio — the page (frontend/index.html): the Uninstall tab's All-apps view, rendered for real by
tests/studio_frontend.js (the dashboard script in a node vm) from a Studio file the REAL build code made of a synthetic
site (tests/studio_synth.py; no real data). Checked here:

  * the "Nuksaan" loss lens, recomputed independently in Python straight from the file's arrays (naye + purane users, no
    double counting, the noise test) for 7 and 30 days;
  * one order everywhere: map #1 = the 🔥 card = the apps table's row 1 = "Kahan se aaya" #1; no "Behtar" pill with a red
    cell or a real loss; only the six status words;
  * the range / compare control IS the dashboard's shared KPIWINDOW (KWIN / KCMP, remembered, the other tabs follow); ₹ / $
    and the fx are the dashboard's;
  * the drawer's "Poora app page →" opens the existing app page; a refresh keeps an open drawer; an app page closes it;
  * every "Kya badla?" alert, with the owner's timestamp line (🕒 Alert aaya in IST, the age chip, Badlaav shuru, Data);
  * the words (English labels, Hinglish in Roman script only, no banned word, never "100 me" / "1,000 me", no NaN);
  * the rest of the page unaffected (Active users, Install value and the app page are byte-identical with and without the
    Studio; without its file the older All-apps view is exactly as before). Skipped where node is not installed."""

import gzip
import json
import math
import os
import re
import shutil
import subprocess
from datetime import date, timedelta

import pytest

from admob_iq import build_static
from admob_iq import uninstall_studio_build as usb
from admob_iq.config import settings
from tests import studio_synth as ss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
BANNED = re.compile(r"\bis hafte\b|\bthis week\b|\babhi ka\b|Provisional|kacch?a\b|kacche|Estimate|/1k|\bpts\b|\bpp\b|\bpoints?\b"
                    r"|cohort|ARPDAU|eCPM|mediation|Stay after|\bsettled\b|\blatest\b|\brecent\b", re.I)
BANNED_CASE = re.compile(r"\bNew\b|\bD\d{1,3}\b|\bMix\b|\bHALT\b|\bWIN\b|\bReturning\b")
DEVA = re.compile("[ऀ-ॿ]")
SIX = {"Bigda", "Dhyan do", "Behtar", "Normal", "Abhi jaldi", "Lagu nahi"}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("studio_fe"))
    site, cfg, dash = ss.make_site(root)
    assert build_static._studio_step(dash, os.path.join(root, "data"), site, dict(settings())) == ["/uninstall_studio.json.gz"]
    fx = os.path.join(root, "fx")
    os.makedirs(fx)
    with gzip.open(os.path.join(site, usb.FILE), "rt", encoding="utf-8") as f:
        studio = json.load(f)
    with gzip.open(os.path.join(site, "uninstall.json.gz"), "rt", encoding="utf-8") as f:
        uni = json.load(f)
    for name, body in (("dashboard.json", dash), ("uninstall_studio.json", studio), ("uninstall.json", uni)):
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
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "studio_frontend.js"), path, fx],
                         check=True, capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout)


def J(report, k):
    assert k in report["out"], (k, report["errors"])
    return json.loads(report["out"][k])


def test_renders_without_errors(report):
    assert report["errors"] == []
    assert 'id="us-root"' in report["out"]["screen7"]


# ── the loss lens, independently ─────────────────────────────────────────────────────────────────────────────────

def _d(s):
    return date.fromisoformat(s)


def _prep(a, M):
    """One app of the file, decoded like the page does (independently written here)."""
    S, N = _d(M["S"]), M["n"]
    x = {k: usb.dec(a[k]) for k in ("nw", "un", "a28", "g0", "c1", "c2", "c3", "c4", "c5", "c6", "c7")}
    x["fi"] = max(0, (_d(a["first"]) - S).days)
    x["c"] = [x["g0"]] + [x["c%d" % L] for L in range(1, 8)]
    E = [None] * N
    for d in range(7, N):
        t, ok = 0, True
        for L in range(8):
            i = d - L
            n = x["nw"][i]
            if i < x["fi"] or n is None or n == 0:
                continue
            v = x["c"][L][i]
            if v is None:
                ok = False
                break
            t += v
        if ok:
            E[d] = t
    x["E"] = E
    return x


def _loss(x, i0, i1, N):
    """The page's loss lens for days i0..i1 (span indices): naye users (gone 0–7 days after install) vs the app's own
    lag hazards × installs; purane users (the rest) vs its own old-user rate × 28-day active users; the noise test."""
    i0, i1 = max(i0, x["fi"]), min(i1, N - 1)
    if i1 < i0:
        return None
    H, Nn, nd = [0] * 8, 0, 0
    for i in range(max(0, x["fi"], i0 - 35), i0 - 7):
        n = x["nw"][i]
        if n is None or n <= 0 or any(x["c"][L][i] is None for L in range(8)):
            continue
        Nn += n
        nd += 1
        for L in range(8):
            H[L] += x["c"][L][i]
    if nd < 14 or Nn < 100:
        return None
    h = [v / Nn for v in H]

    def exE(d):
        t = 0
        for L in range(8):
            i = d - L
            if i < x["fi"] or i < 0:
                continue
            if x["nw"][i]:
                t += x["nw"][i] * h[L]
        return t
    So = Sa = od = 0
    for d in range(max(0, i0 - 28), i0):
        e, u, b = x["E"][d], x["un"][d], x["a28"][d]
        if e is None or u is None or not b:
            continue
        So += u - e
        Sa += b
        od += 1
    part = od < 14 or not Sa
    orate = 0 if part else So / Sa

    def res(d):
        e, u, b = x["E"][d], x["un"][d], x["a28"][d]
        if e is None or u is None:
            return None
        xe = exE(d)
        if part:
            return (e - xe, 0.0, xe)
        if not b:
            return None
        xo = orate * b
        return (e - xe, (u - e) - xo, xe + xo)
    sa = sb = sx = 0.0
    n = 0
    for d in range(i0, i1 + 1):
        r = res(d)
        if r:
            sa, sb, sx, n = sa + r[0], sb + r[1], sx + r[2], n + 1
    if not n:
        return None
    pre = [r[0] + r[1] for r in (res(d) for d in range(max(0, i0 - 28), i0)) if r]
    mu = sum(pre) / len(pre)
    sd = math.sqrt(sum((v - mu) ** 2 for v in pre) / max(1, len(pre) - 1))
    tot = (sa + sb) / n
    z = tot / (max(sd, 1) / math.sqrt(min(n, 7)))
    return {"a": sa / n, "b": None if part else sb / n, "tot": tot, "exp": sx / n, "z": z, "sig": abs(z) >= 2,
            "part": part, "days": n}


@pytest.mark.parametrize("key,days", [("order7", 7), ("rows30", 30)])
def test_the_loss_lens_recomputed_independently(report, built, key, days):
    _, _, studio = built
    M = studio["meta"]
    got = J(report, key)
    assert got["W"]["L"] == days and got["W"]["t"] == M["E"]
    i1 = M["n"] - 1
    i0 = i1 - (days - 1)
    real = 0
    for r in got["rows"]:
        x = _prep(studio["apps"][r["i"]], M)
        L = _loss(x, i0, i1, M["n"])
        if L is None:
            assert "why" in r["L"], r
            continue
        g = r["L"]
        for k in ("a", "tot", "exp", "z"):
            assert g[k] == pytest.approx(L[k], rel=1e-9, abs=1e-9), (r["nm"] if "nm" in r else r["i"], k)
        assert (g["b"] is None) == (L["b"] is None) and (L["b"] is None or g["b"] == pytest.approx(L["b"], abs=1e-9))
        assert g["sig"] == L["sig"] and g["part"] == L["part"] and g["days"] == L["days"]
        assert g["tot"] == pytest.approx(g["a"] + (g["b"] or 0))               # naye + purane — no double counting
        real += L["sig"] and L["tot"] > 0
    assert real >= 1                                                           # (the synthetic site has a real loss)


def test_the_portfolio_loss_is_the_sum_of_the_apps(report):
    o = J(report, "order7")
    rows = [r for r in o["rows"] if "tot" in r["L"]]
    assert o["PT"]["La"] == pytest.approx(sum(r["L"]["a"] for r in rows))
    assert o["PT"]["Lb"] == pytest.approx(sum(r["L"]["b"] or 0 for r in rows))
    assert o["PT"]["Ltot"] == pytest.approx(o["PT"]["La"] + o["PT"]["Lb"])
    assert o["PT"]["Lusd"] == pytest.approx(sum(r["usd"] or 0 for r in o["rows"]))


# ── one order, consistent words ──────────────────────────────────────────────────────────────────────────────────

def test_one_order_map_fire_card_table_and_kahan_se_aaya(report):
    o = J(report, "order7")
    assert o["fire"] is not None
    assert o["map1"] == o["fire"] == o["tbl1"] == o["src1"] == o["rank1"], o
    assert o["names"][o["map1"]] == "Demo Gallery (2026 wala) · Studio One"


@pytest.mark.parametrize("key", ["order7", "rows30"])
def test_pills_never_contradict_the_cells_or_the_loss(report, key):
    for r in J(report, key)["rows"]:
        red = any(c is not None and c >= 2 for c in r["cells"])
        L = r["L"]
        assert r["pill"] in ("bigda", "dhyan", "behtar", "normal", "jaldi")
        if r["pill"] == "behtar":
            assert not red and L.get("sig") and L["tot"] < 0, r
        if L.get("sig") and L.get("tot", 0) > 0:
            assert r["pill"] in ("bigda", "dhyan"), r
        if red:
            assert r["pill"] in ("bigda", "dhyan"), r


def test_only_the_six_status_words(report):
    words = set()
    for h in [report["out"]["screen7"], report["out"]["chg"]]:
        words |= set(re.findall(r'<span class="us-chip us-st-\w+"><i></i>([^<]+)</span>', h))
    assert words and words <= SIX, words


# ── the shared KPIWINDOW, ₹ / $ ─────────────────────────────────────────────────────────────────────────────────

def test_range_and_compare_are_the_dashboards_shared_choice(report, built):
    _, _, studio = built
    k = J(report, "kwin")
    E = studio["meta"]["E"]
    assert k["ext30"] == 30 and k["win30"]                     # KWIN set elsewhere → the Studio shows it
    assert k["after14"] == {"KWIN": "14", "L": 14, "saved": "14", "other": 14}   # the Studio sets it → remembered, shared
    assert k["custom"]["KWIN"] == "custom" and k["custom"]["to"] == E and k["custom"]["L"] == 14
    assert k["month"]["KCMP"] == "month" and k["month"]["saved"] == "month"
    W = k["month"]["W"]
    assert W["ct"] < W["f"]                                    # a month back, never overlapping the range
    assert k["dates"]["KWIN"] == "custom" and k["dates"]["L"] == 10 and k["dates"]["to"] == E
    assert k["cdates"]["KCMP"] == "custom" and k["cdates"]["from"] < k["cdates"]["to"]   # (dates given the wrong way round)
    assert k["fx"] == ss.FX and k["inr"] == "₹832" and k["usd"] == "$10" and k["inrTiny"] == "~₹0" and k["usdTiny"] == "~$0"
    h = J(report, "header")
    assert h == {"p60": True, "month": True, "inr": True}


# ── the drawer and the full app page ────────────────────────────────────────────────────────────────────────────

def test_drawer_full_app_page_refresh_and_app_page(report, built):
    _, _, studio = built
    d = J(report, "drawer")
    assert d["open"] and d["full"] >= 2 and d["dataFull"] and d["lock"]
    assert d["afterRefresh"]                                   # the 5-minute refresh never wipes an open drawer
    assert d["calls"] == [studio["apps"][0]["id"]] and d["closed"]   # "Poora app page →" → the existing app page
    assert d["closedOnAppPage"]


# ── every alert, with the owner's timestamp line ───────────────────────────────────────────────────────────────

def test_kya_badla_keeps_every_alert_with_its_timestamps(report):
    al = J(report, "alerts")
    chg = report["out"]["chg"]
    assert al and sorted(int(k) for k in re.findall(r'data-alk="(\d+)"', chg)) == sorted(x["k"] for x in al)
    cards = re.split(r'<div class="us-ac ', chg)[1:]
    assert len(cards) == len(al)
    for c in cards:
        assert "🕒 Alert aaya: " in c and " IST" in c and "Badlaav shuru: " in c and "Data: " in c
        assert re.search(r'class="us-age[^"]*"[^>]*>🔔 (🆕 Naya alert · aaj \d\d:\d\d|🆕 Kal aaya|📌 \d+ din se khula|📌 .+ se khula|📌 Shuru se khula \(.+\)|✅ Theek ho gaya|📌 Khula)<', c), c[:300]


# ── the words ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_words(report):
    texts = json.loads(report["out"]["texts"])
    assert len(texts) > 20
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
        assert not re.search(r"\b100 me\b|\b1,000 me\b|\bhar 1,000\b", u), u[:200]
    full = texts[0]
    for nm in ("Demo Gallery (2026 wala) · Studio One", "Demo Notes · Studio One", "Demo Torch · A/c 2002", "Demo Young · A/c 2002",
               "Demo Clock · A/c 2002"):
        assert nm in full, nm                                 # app names always with the account


# ── the rest of the page ───────────────────────────────────────────────────────────────────────────────────────

def test_other_tabs_and_the_app_page_are_unaffected(report):
    o = J(report, "others")
    assert o["active_same"] and o["value_same"]
    # one app: the Studio app page, and the whole older app page — exactly as it is without the Studio — folded under it
    assert o["apppage_studio"] and o["apppage_old_kept"] and o["apppage_old_alone"]
    assert o["old_view"] == {"kw": True, "studio": False, "table": True}        # no Studio file: the older view, as before
    assert o["studio_view"]["root"] and not o["studio_view"]["kw"] and o["studio_view"]["fold"]   # no duplicate KPI band
    assert all(o["studio_view"]["folded"])                     # 📦 + 📅, the table, the older What changed: in "Purane views"
    L = J(report, "loading")
    assert L == {"wait": True, "back": True}


def test_the_page_script_scopes_the_studio():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    css = html[html.index("UNINSTALL STUDIO (the Uninstall tab's All-apps view)"):html.index("</style>")]
    css = re.sub(r"/\*.*?\*/", "", css[css.index("*/") + 2:], flags=re.S)
    for rule in re.findall(r"([^{}]+)\{[^{}]*\}", re.sub(r"@(media|container)[^{]*\{", "", css)):
        for sel in rule.replace(":is(#us-root,#us-layer)", "§").split(","):
            sel = sel.replace("§", ":is(#us-root,#us-layer)")
            sel = sel.strip()
            if not sel or sel.startswith(("/*", "@", "from", "to", "0%", "100%")) or re.match(r"^[\d%,\s]+$", sel):
                continue
            assert sel.startswith((":is(#us-root,#us-layer)", "#us-root", "#us-layer", "#uni-old", "#us-main",
                                   "body:not([data-screen=\"uninstall\"]) #us-layer", "body.us-lock")), sel
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    blk = js[js.index("const US=(function(){"):js.index("function renderUninstall(){")]
    for cls in re.findall(r'class="([^"$]+)"', blk):                           # every static class is a Studio one
        for c in cls.split():
            assert c.startswith("us-"), c
    for i in re.findall(r'\bid="([^"$]+)"', blk):
        assert i.startswith("us-"), i



# ── the full app page (owner, 1 Oct: "Poora app page" was still the old page) ───────────────────────────────────────

def test_one_app_is_the_studio_app_page_with_the_whole_older_page_folded_under_it(report, built):
    _, _, studio = built
    p = J(report, "page")
    assert p["view"] == {"VIEW": "app", "PAGE": p["id"]}
    assert p["root"] and p["apg"] and p["back"] and p["nav"] == 2 and p["top"]      # ← All apps, ‹ ›, the shared range bar
    assert p["fold"] and p["oldNoStudio"]                  # the older page, byte for byte as without the Studio, in the fold
    assert p["kwbar"]                                      # (its own KPI band lives in the fold, never above the Studio)
    assert p["kpis"] == 8 and p["charts"] == 2 and p["coh"] and p["daytable"]
    assert p["cards"] == p["alerts"] and p["ts"] == p["alerts"]          # every alert of the app, each with its 🕒 line
    assert p["sameKpis"]                                   # the same numbers as the drawer (one computation)
    assert p["after7"] == 7 and p["html7"]                 # the shared range drives the page
    assert p["loading"] and p["noGa4"]


def test_the_app_page_words(report):
    for t in json.loads(report["out"]["pageWords"]):
        assert t
        for w in ("undefined", "NaN", "[object Object]", "Infinity"):
            assert w not in t, (w, t[:200])
        assert not DEVA.search(t)
        u = t
        for n in sorted(set(ss.NAMES.values()), key=len, reverse=True):
            u = u.replace(n, "<app>")
        m = BANNED.search(u) or BANNED_CASE.search(u)
        assert not m, (m.group(0), u[max(0, m.start() - 80):m.end() + 40])
        assert not re.search(r"\b100 me\b|\b1,000 me\b|\bhar 1,000\b|per 1,000", u), u[:200]
        assert "🕒 Alert aaya: " in u or "Is app pe koi khula alert nahi" in u


# ── the charts: hover numbers through ONE path, numbers printed on them, labels never overlapping ──────────────────

def test_every_chart_hovers_through_one_registered_path(report):
    c = J(report, "charts")
    # the drawer chart's own mousemove listener (shown, then hidden at once by the document's) is gone: every chart and
    # sparkline is a registered svg[data-hv] that the one document listener (hov) reads — crosshair AND numbers
    assert c["n"] >= 10 and c["registered"] and c["tips"] and c["oldHit"]


def test_numbers_are_printed_on_the_charts(report):
    c = J(report, "charts")
    big = c["bigLabels"]
    assert any(re.match(r"^\d{1,2} \w{3}: [\d,]+(?: lakh)? \(\d+(?:\.\d+)?%\)$", t) for t in big), big   # the latest day
    assert any(t.startswith("Avg ") and "/din (" in t for t in big) or any(t.startswith("Normal ") for t in big), big
    assert any(t.startswith("v1.1: ") for t in big), big                           # the 📦 version, before → after
    assert c["inside"] and c["overlap"] == 0                                        # inside the chart, never on each other
    assert any(t.startswith("Max ") for t in c["ioLabels"]) and any(re.match(r"^\d{1,2} \w{3}: ", t) for t in c["ioLabels"])
    assert any(t.startswith("Avg ") for t in c["tlLabels"]) and any(re.match(r"^\d{1,2} \w{3}: ", t) for t in c["tlLabels"])
    assert len(c["kpiLabels"]) >= 4 and all(re.match(r"^(\d{1,2} \w{3}: |avg )", t) for t in c["kpiLabels"]), c["kpiLabels"]
    for t in big + c["ioLabels"] + c["tlLabels"] + c["kpiLabels"]:
        assert not re.search(r"\b100 me\b|1,000 me|per 1,000|NaN|undefined", t), t
        if "%" in t:                                                                # the actual number first, its % beside
            assert re.search(r"[\d,]+(?: lakh)?(?:/din)? \(\d+(?:\.\d+)?%\)", t) or re.search(r"[\d,]+→[\d,]+/din \(", t), t


def test_labels_drop_rather_than_overlap(report):
    got = J(report, "charts")["helper"]
    texts = [t for _, _, t in got]
    assert texts[0] == "Aaaa 1,000 (1.0%)"                  # the first priority placed as asked
    assert "Bbbb 2,000 (2.0%)" not in texts                 # no free spot (no nudges allowed) → dropped, never overlapped
    assert "Cccc 3,000 (3.0%)" in texts                     # nudged down to a free spot
    for x, y, t in got:                                     # all inside the box
        assert 0 <= x and x + len(t) * 10.5 * .56 + 3 <= 200.5 and y + 3 <= 60 and y - 10.5 + 1 >= 0
