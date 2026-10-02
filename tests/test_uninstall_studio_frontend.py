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
    Studio — but the app page's 📦 Update impact card, which is the Studio app page's own section (owner, 2 Oct: "update
    impact vala isme bhi kar do"; one line in the fold) with its windows, 📅 any date, 📌 saved dates (the same
    /api/marks calls) and 📦 jumps; without its file the older views are exactly as before). Skipped where node is not
    installed."""

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
from admob_iq.engine import impact_any as ia
from tests import studio_synth as ss
from tests.uninstall_synth import END

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
BANNED = re.compile(r"\bis hafte\b|\bthis week\b|\babhi ka\b|Provisional|kacch?a\b|kacche|Estimate|/1k|\bpts\b|\bpp\b|\bpoints?\b"
                    r"|cohort|ARPDAU|eCPM|mediation|Stay after|\bsettled\b|\blatest\b(?! week\b)|\brecent\b", re.I)   # "Latest week" (Gone by day N) is the owner's word
BANNED_CASE = re.compile(r"\bNew\b(?!\s*(?:alert|users?|installs?|vs\b|engine|=))|\bD\d{1,3}\b|\bMix\b|\bHALT\b|\bWIN\b|\bReturning\b")
DEVA = re.compile("[ऀ-ॿ]")
SIX = {"Worse", "Watch", "Better", "Normal", "Too early", "N/A"}


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
    # 📅 the app with an update: its impact_any file (the real engine), for the any-date box on the Studio app page
    st, rv = ss.stores()[ss.G1]
    body, failed = ia.build_app(dict(st, window_end=END.isoformat()), rv, ss.G1, "a1b2c3d4e5f6", "sig-test", 7)
    assert failed == 0 and body["n"] > 100
    with open(os.path.join(fx, "impact_any_app.json"), "w", encoding="utf-8") as f:
        json.dump({"body": body, "entry": ia.index_entry(body, "impact_any_a1b2c3d4e5f6.json.gz")}, f)
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
        assert "🕒 Alert time: " in c and " IST" in c and "Change started: " in c and "Data: " in c
        assert re.search(r'class="us-age[^"]*"[^>]*>🔔 (🆕 New alert · today \d\d:\d\d|🆕 Yesterday|📌 Open \d+ days?|📌 Open since .+|📌 Open from start \(.+\)|✅ Fixed|📌 Open)<', c), c[:300]


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
    # one app: the Studio app page, and the whole older app page — exactly as it is without the Studio — folded under it,
    # its 📦 Update impact card alone being one line there (the card is the Studio page's own section: owner, 2 Oct)
    assert o["apppage_studio"] and o["apppage_old_kept"] and o["apppage_old_alone"]
    assert o["old_view"] == {"kw": True, "studio": False, "table": True}        # no Studio file: the older view, as before
    assert o["studio_view"]["root"] and not o["studio_view"]["kw"] and o["studio_view"]["fold"]   # no duplicate KPI band
    assert all(o["studio_view"]["folded"])                     # the band, 📦 (one line), 📅, the table, the older What changed: folded
    assert o["studio_view"]["updCard"] and o["studio_view"]["updSection"]   # the 📦 list is the Studio's own section, drawn once
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
    #                                                        (but its 📦 Update impact card: one line — the card is up on the page)
    assert p["kwbar"]                                      # (its own KPI band lives in the fold, never above the Studio)
    # 3 charts: the rate chart, installs vs uninstalls and (owner, 2 Oct) "📉 How many stay", the older page's curve
    assert p["kpis"] == 8 and p["charts"] == 3 and p["coh"] and p["daytable"]
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
        assert "🕒 Alert time: " in u or "Is app pe koi khula alert nahi" in u


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
    assert any(t.startswith("Avg ") and "/day (" in t for t in big) or any(t.startswith("Normal ") for t in big), big
    assert any(t.startswith("v1.1: ") for t in big), big                           # the 📦 version, before → after
    assert c["inside"] and c["overlap"] == 0                                        # inside the chart, never on each other
    assert any(t.startswith("Max ") for t in c["ioLabels"]) and any(re.match(r"^\d{1,2} \w{3}: ", t) for t in c["ioLabels"])
    assert any(t.startswith("Avg ") for t in c["tlLabels"]) and any(re.match(r"^\d{1,2} \w{3}: ", t) for t in c["tlLabels"])
    assert len(c["kpiLabels"]) >= 4 and all(re.match(r"^(\d{1,2} \w{3}: |avg )", t) for t in c["kpiLabels"]), c["kpiLabels"]
    for t in big + c["ioLabels"] + c["tlLabels"] + c["kpiLabels"]:
        assert not re.search(r"\b100 me\b|1,000 me|per 1,000|NaN|undefined", t), t
        if "%" in t:                                                                # the actual number first, its % beside
            assert re.search(r"[\d,]+(?: lakh)?(?:/day)? \(\d+(?:\.\d+)?%\)", t) or re.search(r"[\d,]+→[\d,]+/day \(", t), t


def test_labels_drop_rather_than_overlap(report):
    got = J(report, "charts")["helper"]
    texts = [t for _, _, t in got]
    assert texts[0] == "Aaaa 1,000 (1.0%)"                  # the first priority placed as asked
    assert "Bbbb 2,000 (2.0%)" not in texts                 # no free spot (no nudges allowed) → dropped, never overlapped
    assert "Cccc 3,000 (3.0%)" in texts                     # nudged down to a free spot
    for x, y, t in got:                                     # all inside the box
        assert 0 <= x and x + len(t) * 10.5 * .56 + 3 <= 200.5 and y + 3 <= 60 and y - 10.5 + 1 >= 0


# ── 📦 Update impact on the app page (owner, 2 Oct: "update impact vala isme bhi kar do") ───────────────────────────────

def _words_ok(t):
    assert t and not DEVA.search(t)
    for w in ("undefined", "NaN", "[object Object]", "Infinity"):
        assert w not in t, (w, t[:200])
    m = BANNED.search(t) or BANNED_CASE.search(t)
    assert not m, (m.group(0), t[max(0, m.start() - 80):m.end() + 40])


def test_the_whole_update_impact_card_is_a_section_of_the_studio_app_page(report):
    m = J(report, "imppage")
    assert m["n"] == {"card": 1, "any": 1, "block": 1, "section": 1, "up": 1}    # drawn ONCE; the fold keeps one line to it
    assert m["dups"] == []                                                      # no id twice on the whole screen
    w = m["where"]          # on the Studio page: after every chart, Gone by day N, the install-week grid and the alerts —
    assert w == {"studio": True, "charts": True, "grid": True, "gone": True, "alerts": True, "table": True}   # right before the day-by-day table
    assert m["head"]                                                            # its heading: "📦 Update impact"
    assert not m["shortList"] and m["lines"] == m["rel"] >= 1                   # the uninstall lines per update inside it, not a 2nd panel
    # everything the card has: the older page's card byte for byte, only its frame + title line now the section's
    assert m["same"] == {"frame": True, "body": True, "onPage": True, "handlers": True}
    f = m["fold"]
    assert f["line"] and not f["card"] and not f["any"] and not f["open"] and not f["open0"]
    assert "📦 Update impact → upar" in f["text"] and "(📦 Update impact ab upar)" in f["text"]
    for t in (m["secText"], f["text"]):
        _words_ok(t)
    assert "Uninstalls per day" in m["secText"] and re.search(r"uninstalls [\d,]+→[\d,]+/day \(\d+(?:\.\d+)?%→\d+(?:\.\d+)?%\)", m["secText"])


def test_update_impact_windows_switch_on_the_studio_page(report):
    w = J(report, "imppage")["wins"]
    assert w["state"] == "on" and w["seg"]                                      # the card's 7 / 14 / 30 / 60
    assert w["c30"] == {"on": True, "verdict": True, "saved": "30"}             # every block at 30, remembered
    assert w["b14"] == {"verdict": True, "on": True}                            # one block's own 14
    assert w["back7"]


def test_any_date_and_saved_dates_on_the_studio_page_make_the_same_calls(report):
    m = J(report, "imppage")
    assert m["any"] == {"file": True, "inputs": True, "save": True, "mark": True, "del": True, "box": True}
    S, O = m["flowStudio"], m["flowOld"]                                         # the Studio page · the older page (no Studio)
    assert S["where"] == ["studio", "studio"] and O["where"] == ["page", "page"]
    assert S["picked"] == O["picked"] and S["picked"]["name"] == "Banner ad hataya" and re.match(r"^\d{4}-\d\d-\d\d$", S["picked"]["date"])
    assert S["result"] and O["result"] and S["rows"] == O["rows"] > 0           # the chosen date's comparison, the same rows
    assert S["mk"] == S["picked"]                                               # a 📌 saved date re-opens it
    base = {"credentials": "same-origin", "redirect": "manual"}
    want = [dict(base, url="/api/marks", method="GET", body=None),
            dict(base, url="/api/marks", method="POST", body={"app_id": m["id"], "date": S["picked"]["date"], "name": "Banner ad hataya"}),
            dict(base, url="/api/marks/delete", method="POST", body={"id": 41})]
    assert S["calls"] == want and O["calls"] == want                            # same endpoints, same bodies


def test_update_impact_jumps_land_on_the_studio_section(report):
    j = J(report, "imppage")["jump"]
    # Alerts → "Update detail →" (uniImpGo): the page drawn while the jump waits opens that block in the section, the
    # fold stays shut; the scroll waits for the page's fit-to-width pass, then puts the block under the bars
    assert j["drawn"] and j["open"] and not j["fold"] and j["waited"] and j["cleared"]
    assert j["scroll"] == [{"top": 992, "behavior": "smooth"}]                  # 900 on screen + 100 scrolled − 8
    # the 📦 line of the install-week table (in the fold) → the same block, up in the section
    assert j["marker"].startswith("uniImp(") and j["markerOpen"] and j["markerScroll"] == j["scroll"]


def test_update_impact_fallbacks_keep_the_card_where_it_was(report):
    m = J(report, "imppage")
    # the Studio's file still loading: the card in the fold as before, a waiting 📦 jump opens the fold
    assert m["loading"] == {"card": True, "section": False, "up": False, "open": True, "dups": []}
    # the Studio failing to draw its page: the card stays in the fold — never lost, never twice
    assert m["failed"] == {"card": 1, "inFold": True, "up": False, "dups": []}
    # no Studio file: the older app page exactly as it was (its framed card, no section, no fold, no line)
    assert m["noStudio"] == {"same": True, "frame": True, "section": False, "up": False, "fold": False, "dups": []}
    # the drawer keeps its short list, pointing at the app page
    assert m["drawer"] == {"short": True, "hint": True, "card": False}
    # an app with no update: the section still there (📅 any date works without one), no uninstall lines
    assert m["noUpd"] == {"section": True, "card": 1, "lines": 0, "dups": []}


def test_the_studio_table_and_button_look_skips_the_card():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    css = html[html.index("UNINSTALL STUDIO (the Uninstall tab's All-apps view)"):html.index("</style>")]
    css = re.sub(r"/\*.*?\*/", "", css[css.index("*/") + 2:], flags=re.S)
    bare = 0
    for rule in re.findall(r"([^{}]+)\{[^{}]*\}", re.sub(r"@(media|container)[^{]*\{", "", css)):
        for sel in rule.replace(":is(#us-root,#us-layer)", "§").split(","):
            m = re.fullmatch(r"§ (?:table|th|td|button|input|select|tbody tr(?::hover td)?)(:not\(.*\))?", sel.strip())
            if m:                                   # a plain element rule of the Studio: never on the card (its own look)
                bare += 1
                assert m.group(1) == ":not(:where(.us-impb *))", sel
    assert bare >= 8


# ── 📦 updates in the install-week grid (owner, 2 Oct: "agar kahi par bhi update aata he to vaha se divide kro taki pata
# chale effect") — the older "Install week × day" table's own release list, dates and placement ────────────────────────

def test_install_week_grid_draws_a_line_above_each_updates_week(report):
    c = J(report, "crel")
    W, seq = c["weeks"], c["modes"]["abs"]
    lines = {x["rw"]: x["t"] for x in seq if x["k"] == "crel"}
    D = r"\(\d{1,2} \w{3}\)"
    assert re.fullmatch(r"📦 v9\.1 %s — mid-week" % D, lines[W[1]["w"]])                     # one update mid-week
    assert re.fullmatch(r"📦 v9\.2 %s · v9\.3 %s — mid-week" % (D, D), lines[W[2]["w"]])     # two in one week: one line
    assert re.fullmatch(r"📦 v9\.4 %s — week start" % D, lines[W[3]["w"]])                    # on the week's first day
    assert W[0]["w"] not in lines and not any("9.0" in t for t in lines.values())          # before the app's start: none
    w11 = next(w["w"] for w in W if w["f"] <= "2026-08-30" <= w["t"])                        # (the app's real update)
    assert re.fullmatch(r"📦 v1\.1 %s — mid-week" % D, lines[w11]) and len(lines) == 4
    for i, x in enumerate(seq):                     # each line right ABOVE its week's row, whose label carries a 📦
        if x["k"] == "crel":
            assert seq[i + 1]["k"] == "rh" and "📦" in seq[i + 1]["t"]
    assert sum("📦" in x["t"] for x in seq if x["k"] == "rh") == 4
    assert [x["t"] for x in seq] == [x["t"] for x in c["modes"]["dev"]]                    # the same in "Vs normal"
    # the partial week says so, as the older table does
    part = [w for w in W if w["part"]]
    assert part and all(any(x["k"] == "rh" and "(only %d days)" % ((date.fromisoformat(w["t"]) - date.fromisoformat(w["f"])).days + 1)
                            in x["t"] for x in seq) for w in part)
    # the very lines the older table draws, above the same weeks — every week of it is in the grid now (no 12-week
    # cut: the owner, 2 Oct, "13-19 july tak hi kyu? pura data hona chaiye"), the oldest ones too
    lab = {x["lab"]: x["w"] for x in c["newByLabel"]}
    both = [o for o in c["old"] if o["wk"] in lab]
    assert len(both) == 4 == len(c["old"]) and not any("9.0" in o["rel"] for o in c["old"])
    assert len(W) > 12 and c["pageRows"] == len(W) == c["drawerRows"]
    assert c["pageHead"].startswith("Install week × day · all %d weeks " % len(W)) and "saare hafte" in c["pageHead"]
    for o in both:
        assert re.findall(r"v[\d.]+", o["rel"]) == re.findall(r"v[\d.]+", lines[lab[o["wk"]]]), o
    # the page and the drawer draw the same lines (no year row: these weeks are all in one year)
    want = [x["t"] for x in seq if x["k"] != "rh"]
    assert c["page"] == want and c["drawer"] == want and not c["yearPage"]
    assert c["pageLg"] == "📦 = new update. Line ke upar = naye version ke installs, neeche = purane version ke. Tap 📦 → update impact."
    _words_ok(" ".join(want + [c["pageLg"]]))


def test_install_week_grid_update_tap_jumps_to_its_update_impact_block(report):
    c = J(report, "crel")
    key = c["orig"][0]["key"]
    assert key == c["orig"][0]["block"] == c["key"]                       # the older table's key, a block of the card
    assert set(c["pageTaps"]) == {key} and len(c["pageTaps"]) == 2        # the version on the line + the week's 📦
    assert key in c["pageBlocks"] and c["secAfterGrid"]                    # …whose block is on this page, below the grid
    assert set(c["drawerTaps"]) == {key}
    # the page: the older table's own jump (uniImp) · the drawer: closed, the app page opened on that block (uniImpGo)
    assert c["calls"] == [["uniImp", key, None], ["uniImpGo", c["id"], key, "uni"]] and c["drawerClosed"]
    # no older detail (still loading / failed): the Studio file's own updates, no tap
    assert c["noUni"] == [{"t": "📦 %s (%d %s) — mid-week" % (r[1], int(r[0][8:]), date.fromisoformat(r[0]).strftime("%b")), "tap": False}
                          for r in c["rel"]]


def test_install_week_grid_year_rows_only_when_the_weeks_cross_a_year(report):
    c = J(report, "crel")
    # under its year row a week's label says no year again — the older table's own labels (uniSpan(…, noYr))
    assert c["year"] == ["rh All-time normal all installs", "cyr ── 2026 ──", "rh 5–7 Jan 5,400 installs (only 3 days)",
                         "crel 📦 v5.0 (31 Dec 2025) — mid-week", "rh 29 Dec 2025–4 Jan 📦 5,400 installs", "cyr ── 2025 ──",
                         "crel 📦 Update (23 Dec 2025) — mid-week", "rh 22–28 Dec 📦 5,400 installs", "rh 15–21 Dec 5,400 installs"]


def test_install_week_grid_scrolls_in_its_box_with_its_column_names_on_top():
    """Every week since the start makes a long grid: it scrolls in its own box (both ways), the column names stick to its
    top (the corner "Install week" to both edges), the week column to its left; on a phone its 📦 taps are 32px."""
    css = open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read()
    assert re.search(r"\.us-cohw\{overflow:auto;max-height:min\(70vh,720px\)", css)
    assert re.search(r"\.us-cohw \.us-coh \.us-chh\{position:sticky;top:0;z-index:3;background:var\(--panel\)", css)
    assert re.search(r"\.us-cohw \.us-coh \.us-chh\.us-stk\{left:0;z-index:4", css)
    assert re.search(r"\.us-cohw \.us-coh \.us-rh,:is\(#us-root,#us-layer\) \.us-cohw \.us-coh \.us-stk\{position:sticky;left:0", css)
    assert re.search(r"@media \(max-width:760px\),\(pointer:coarse\)\{:is\(#us-root,#us-layer\) \.us-coh \.us-relb\{display:inline-block;padding:9px", css)
    assert "function keepCoh(" in css and "keepCoh(inD?$('us-drawer'):$('us-apg')" in css   # % bache ⇄ Vs normal keeps its place


# ── 📉 How many stay (owner, 2 Oct: "purane view ka ye feature (How many stay) tumne new view me to gayab hi kar diya") ──

def test_how_many_stay_is_on_the_studio_app_page_with_the_older_curves_numbers(report):
    c = J(report, "curve")
    w = c["where"]
    assert 0 < w["gone"] < w["curve"] < w["grid"] and w["oldKept"]           # after Gone by day N, before the grid; old kept
    assert [(x["cs"], x["cr"]) for x in c["combos"]] == [("all", "90"), ("all", "30"), ("all", "all"), ("recent", "90"), ("recent", "30")]
    for x in c["combos"]:
        assert x["n"] == x["oldN"]                         # the same days (install + day 0 … the last shown) as the older chart
        assert x["pressed"] == [x["cs"], x["cr"]]          # both toggles say what is shown
        for d in x["days"]:                                # the hover: the older chart's very numbers (its formats)
            stay, gone, _ = d["old"].split(" | ")
            pct = stay.replace(" stay", "").replace("estimate ", "≈ ")
            assert "Still installed " + pct in d["tip"], (d, x["cs"], x["cr"])
            g = gone.replace(" gone that day", "")
            assert re.search(r"Gone that day [\d,.]+(?: lakh)? users \(%s\)" % re.escape(g), d["tip"]), d     # count first, % beside
            assert d["tip"].count("day %d after install" % d["N"]) == 1 if d["N"] else "install day (same day)" in d["tip"]
        # the % printed on the chart: day 1 / 3 / 7 / 14 / 30 … and the last day, each = the older chart's rounding,
        # and every day both print reads the same; inside the chart, never on each other
        last = x["n"] - 2
        new = dict(t.split(": ") for t in x["newLab"])
        old = dict(t.split(": ") for t in x["oldLab"])
        assert "Day %d" % last in new and set(new) <= {"Day %d" % N for N in (1, 3, 7, 14, 30, 60, 90, 180, 365, 730, last)}
        assert {k: v for k, v in new.items() if k in old} == {k: old[k] for k in new if k in old} and len(set(new) & set(old)) >= 3
        assert x["geo"] == {"inside": True, "overlap": 0}
        assert x["tip0"].endswith("install Still installed 100% Install ke waqt sab ke paas app")
        assert x["lg"].startswith("% gone that day % still installed ≈ range")
        assert ("Faded = low data" in x["lg"]) == x["dashed"]
        assert x["ex"].startswith("Last 90 days = " if x["cs"] == "recent" else "All time = ")
        assert "Laal bar = us din kitne gaye · hari line = ab tak kitne bache · saare laal bar + hari line = 100%." in x["ex"]
        _words_ok(x["text"])
        assert not re.search(r"\b100 me\b|1,000 me|per 1,000", x["text"])
    by = {(x["cs"], x["cr"]): x for x in c["combos"]}
    assert by[("all", "30")]["n"] == 32 and by[("all", "90")]["n"] == 92 and by[("all", "all")]["n"] > 92
    assert by[("all", "90")]["days"][1]["left"] != by[("recent", "90")]["days"][1]["left"]   # the two sets of installs differ


def test_how_many_stay_toggles_drawer_low_data_and_loading(report):
    c = J(report, "curve")
    assert c["tog1"] == {"cvR": "30", "cvS": "all", "pressed": ["all", "30"]}          # one click handler, the page redrawn
    assert c["tog2"]["cvS"] == "recent" and c["tog2"]["pressed"] == ["recent", "30"]
    assert c["tog2"]["saved"]["cvS"] == "recent" and c["tog2"]["saved"]["cvR"] == "30"  # remembered
    assert c["drawer"]["has"] and c["drawer"]["svg"] and c["drawer"]["order"] and "Day 7: 11%" in c["drawer"]["lab"]
    t = c["thin"]                                          # low data from day 5: faded / dashed, said in legend and tooltip
    assert t["dashed"] and t["lg"].endswith("Faded = low data")
    assert "Low data" in t["tip7"] and "Low data" not in t["tip3"]
    assert t["faint"] and all(int(re.match(r"Day (\d+)", f).group(1)) >= 5 for f in t["faint"])
    assert c["loading"].endswith("⏳ Is graph ka data load ho raha hai…") and c["failed"].endswith("⚠️ Is graph ka data load nahi hua — page refresh karo")


# ── parity with the older All-apps views (owner, 2 Oct: "parity aur speed") ───────────────────────────────────────────

def _words_all(t):
    _words_ok(t)
    assert not re.search(r"\b100 me\b|\b1,000 me\b|\bhar 1,000\b|per 1,000", t), t[:200]


def test_the_all_apps_band_is_back_in_the_fold(report):
    p = J(report, "parity")
    assert p["dups"] == []
    # the grey "ALL APPS TOGETHER" band: the pooled tile and both chip rows — first in the fold, without range KPIs
    assert p["fold"] == {"band": True, "pool": True, "kw": False, "secs": 2, "first": True}
    for k in ("loading", "failed"):                            # the Studio not there: the band and the card, nothing twice
        assert p[k]["card"] and not p[k]["line"] and p[k]["dups"] == [], (k, p[k])
    assert p["loading"]["band"]
    assert p["noStudio"] == {"band": True, "card": True, "studio": False}       # no Studio file: as before (its KPIs too)


def test_the_studio_panel_has_the_older_bands_numbers(report):
    p = J(report, "parity")
    e = p["eng"]
    assert e["where"] and e["rows"] == ["App status", "Uninstall rate"]
    assert e["now"] == e["old"] and e["now"]                   # the same chips, labels and counts as the older band
    assert e["pool"][0] == e["pool"][1] and e["before"][0] == e["before"][1] and e["pool"][0]
    assert e["apps"][0] == e["apps"][1]                        # "21 of 27 apps": the apps judged on the same weeks
    assert "installs" in p["engTip"] and "Now" in p["engTip"] and "Before" in p["engTip"]
    for k, L in p["lists"].items():                            # a chip's apps = the older chip's apps; a name opens the app
        assert L["names"] and len(L["now"]) == len(L["names"]), (k, L)
        _words_all(L["text"])
        for t in L["tips"]:
            assert "Last 4 final weeks" in t and "4 weeks before" in t and "installs" in t, t
    assert p["click"] == {"uf": "halt", "sec": True, "off": True, "uall": True, "uall2": False, "eng": True, "eng2": True, "mapSame": True}
    assert p["wait"] == {"eng": True, "upd": True, "root": True}   # the older views' file still loading: the parts wait


def test_the_studio_panel_matches_on_every_kind_of_chip(report):
    q = J(report, "parity2")
    kinds = {k for k, _ in q["old"]}
    assert {"worse", "better", "unsure", "wk_up", "r_up", "r_zero", "r_dn", "r_ok"} <= kinds, kinds
    assert q["now"] == q["old"]
    P = q["pool"]
    assert P["old"] == P["now"] and P["before"] == P["nowBefore"] and P["apps"] == P["oldApps"] == [3, 4]
    # the pooled number: Σ installs × still in app ÷ Σ installs, over the apps judged on the SAME weeks (the low-data app
    # on other weeks is left out), recomputed here
    r = (1000 * .40 + 900 * .61 + 700 * .55) / 2600
    assert abs(P["P"]["r"] - r) < 1e-9 and P["P"]["su"] == 2600 and P["P"]["ku"] == round(r * 2600) == 1334
    for k, L in q["lists"].items():
        assert L["now"] == L["old"] or (k == "same" and not L["old"]), (k, L)   # the same gap / reason per app
        assert L["n"] == L["oldN"], (k, L)
    assert q["lists"]["worse"]["now"] == ["−12"] and q["lists"]["better"]["now"] == ["+11"]
    assert q["lists"]["r_up"]["now"] == ["Spike · 14 Sep"] and q["lists"]["r_zero"]["now"] == ["0 recorded · 15 Sep"]
    for t in q["words"]:
        _words_all(t)


def test_update_impact_is_a_studio_section_with_the_cards_rows(report):
    p = J(report, "parity")
    u = p["upd"]
    assert u["where"] and u["rowsSame"] and u["restHidden"] and u["foldLine"] and not u["card"]
    _words_all(u["text"])
    q = J(report, "parity2")["upd"]
    assert q["n"] == 8 and q["mainSame"]
    assert q["order"] == ["syn-halt", "syn-hold", "syn-late", "syn-win"]          # 🛑, ⚠️ (the ⏰ late one too), ✅ — the card's order
    assert q["go"] == q["order"]                                # a row = that app's page at that update (uniImpGo)
    assert q["late"] == ["After 30 days: ⚠️ Wait and check"]
    assert q["updated"] == 4 and q["judged"] == ["Back next day −25.6%", "Same day uninstall +6.5%", "Same day uninstall −3.1%"]
    # the filter: a chip per verdict with its count, the six status words; the counts are the card's own
    assert q["chips"] == [["", 8], ["halt", 1], ["hold", 2], ["win", 1], ["continue", 2], ["pending", 1], ["never", 1]]
    assert q["fold"] == q["cardFold"] == [1, 2, 1]
    assert q["groups"] == {"halt": 1, "hold": 2, "win": 1, "pending": 1, "continue": 2, "never": 1}
    f = J(report, "parity2")["filt"]
    assert f["halt"] == ["syn-halt"] and f["hold"] == ["syn-hold", "syn-late"] and f["win"] == ["syn-win"]
    assert f["pending"] == ["syn-wait"] and f["never"] == ["syn-never"] and "syn-cont" in f["continue"]
    _words_all(q["text"])
    pf = p["filt"]
    for k, v in pf.items():
        assert v["rows"] == v["want"], (k, v)
        if k != "all":
            assert v["on"]
            _words_all(v["text"])


def test_when_will_i_know_and_the_status_chip_counts(report):
    p = J(report, "parity")
    assert p["when"]["sec"] and p["when"]["same"]
    _words_all(p["when"]["text"])
    fst = dict((k, n) for k, _, n in p["fst"])
    for k in set(fst) - {"lagu"}:
        assert fst[k] == p["R"].count(k), (k, fst)
    assert fst["lagu"] == p["R"].count("lagu") + p["noga"]
    assert [w for _, w, _ in p["fst"]][:6] == ["Worse", "Watch", "Better", "Normal", "Too early", "N/A"]


def test_the_panel_and_the_list_do_not_follow_the_range_or_the_currency(report):
    out = json.loads(report["out"]["parityStable"])
    assert len(out) == 6 and len(set(out)) == 1


# ── the phone audit (mobile_audit A-01, A-04 .. A-12) on the All-apps view and the Studio's shared code ────────────────

def test_a_tooltip_pins_on_a_tap_never_on_a_swipe(report):
    m = J(report, "mobile")
    assert m["swipe"] == {"on": False, "pin": False}            # a scroll that starts on a cell pins nothing (A-01)
    assert m["tap"] == {"on": True, "pin": True}                # a tap shows the numbers, pinned
    assert m["long"] == {"on": False, "pin": False} and m["pinch"] == {"on": False, "pin": False}
    assert m["pinned"] and m["scrollAtOnce"] and m["scrollLater"] == {"on": False, "pin": False} and m["scrollCapture"]


def test_what_changed_table_the_map_cells_and_the_timeline_on_a_phone(report):
    m = J(report, "mobile")
    assert m["table"] == {"heads": ["App", "Status", "Alert"], "first": True, "cls": True}      # A-06: App first, sticky
    assert m["cells"] and len(m["cellLabels"]) == m["cells"]                                       # A-10: each cell its metric
    assert set(m["cellLabels"]) == {"Same day", "Rate", "In app day 7", "Back day 1"}
    t = m["tl"]                                                                                      # A-11
    assert len(t["u"]) >= 3 and t["gapU"] >= 28 and t["hit"] == t["marks"]                         # apart, each a 28px circle
    assert t["items"] == t["want"] == 25                                                            # merged, never dropped
    assert any("updates" in x and "Sep ·" in x for x in t["tips"])                                  # a merged one lists each day
    assert t["notFinal"]
    for x in t["tips"]:
        _words_all(x)


def _css(html):
    css = html[html.index("UNINSTALL STUDIO (the Uninstall tab's All-apps view)"):html.index("</style>")]
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def _cr(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + .05) / (min(la, lb) + .05)


def test_heat_cells_text_reads_at_4_5_to_1():
    """A-09: every line in a coloured cell (the map, the tables, Gone by day N) — the small second line too — reaches
    4.5 : 1 on its cell, the cell's colour laid over the panel."""
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    hx = lambda h: tuple(int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    root = re.search(r":root\{([^}]*)\}", html).group(1)
    var = lambda k: re.search(r"--%s:(#[0-9a-f]{6})" % k, root).group(1)
    panel, ink2 = hx(var("panel")), hx(var("ink2"))
    css = _css(html)
    us = re.search(r":is\(#us-root,#us-layer\)\{([^}]*)\}", css).group(1)
    for k, want in (("h1", ink2), ("h2", ink2), ("g1", ink2), ("g2", ink2), ("h3", (255, 255, 255)), ("g3", (255, 255, 255))):
        r, g, b, a = [float(x) for x in re.search(r"--us-%s:rgba\(([\d.]+),([\d.]+),([\d.]+),([\d.]+)\)" % k, us).groups()]
        bg = tuple(round(c * a + p * (1 - a)) for c, p in zip((r, g, b), panel))
        assert _cr(want, bg) >= 4.5, (k, _cr(want, bg))
    rules = {}
    for sels, body in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"@(media|container)[^{]*\{", "", css)):
        for sel in sels.replace(":is(#us-root,#us-layer)", "§").split(","):
            rules.setdefault(sel.strip().replace("§", ":is(#us-root,#us-layer)"), []).append(body)
    P = ":is(#us-root,#us-layer) "
    for h in (".us-h1", ".us-h2", ".us-h-1", ".us-h-2"):         # the second line: light ink on the light / mid cells
        for t in ("small", ".us-gtn", ".us-hcl"):
            assert "color:var(--ink2)!important;opacity:1!important" in rules.get(P + h + " " + t, []), (h, t)
        assert "color:var(--ink2)!important" in rules.get(P + ".us-hcell" + h + " .us-d", []), h
    for h in (".us-h3", ".us-h-3"):                               # white on the strong cells, every line
        for t in ("small", ".us-gtn", ".us-gtp", ".us-hcl", ".us-d", ".us-v"):
            assert "color:#fff!important;opacity:1!important" in rules.get(P + h + " " + t, []), (h, t)


def test_phone_jumps_scroll_boxes_and_tap_sizes():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    css = _css(html)
    # A-04: a jump lands below the sticky bars (stick() keeps both heights current)
    assert "scroll-margin-top:calc(var(--us-stick,0px) + var(--us-toph,0px) + 10px)" in css
    assert "r.style.setProperty('--us-toph'," in html
    # A-05: on a phone the big tables have no inner vertical scroll (the page scrolls)
    assert "@media (max-width:760px){:is(#us-root,#us-layer) .us-tw.us-st-tw{max-height:none}}" in css
    # A-07: a long list collapses in place
    assert "moreToggle('us-mapMore'" in html and "moreToggle('us-srcMore'" in html
    # A-08: the loss column wraps instead of clipping on a phone
    assert ":is(#us-root,#us-layer) .us-hm .us-inr{overflow:visible}" in css
    # A-12: ▶, ← All apps and the saved date's × are 32px targets
    assert re.search(r"\.us-st \.us-xp\{min-width:32px;min-height:32px", css)
    assert re.search(r"\.us-lk\[data-back\]\{display:inline-flex;align-items:center;min-height:32px", css)
    assert re.search(r"\.uni-any-x\{[^}]*min-width:32px;min-height:32px", html)
    for sel in (".us-ech{", ".us-ufs button{", ".us-eap{"):
        assert re.search(re.escape(sel) + r"[^}]*min-height:32px", css), sel
    # A-18: the older views' 1000-wide charts get their own sideways scroller on a phone
    assert "#uni-old-app svg[data-pts]{min-width:720px}" in css
