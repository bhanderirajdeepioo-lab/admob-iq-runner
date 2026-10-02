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
    #                                                        (but its 📦 Update impact card: one line — the card is up on the page)
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
    assert W[0]["w"] not in lines and not any("9.0" in t for t in lines.values())          # before the grid's weeks: none
    assert re.fullmatch(r"📦 v1\.1 %s — mid-week" % D, lines[W[8]["w"]]) and len(lines) == 4  # (the app's real update)
    for i, x in enumerate(seq):                     # each line right ABOVE its week's row, whose label carries a 📦
        if x["k"] == "crel":
            assert seq[i + 1]["k"] == "rh" and "📦" in seq[i + 1]["t"]
    assert sum("📦" in x["t"] for x in seq if x["k"] == "rh") == 4
    assert [x["t"] for x in seq] == [x["t"] for x in c["modes"]["dev"]]                    # the same in "Vs normal"
    # the partial week says so, as the older table does
    part = [w for w in W if w["part"]]
    assert part and all(any(x["k"] == "rh" and "(only %d days)" % ((date.fromisoformat(w["t"]) - date.fromisoformat(w["f"])).days + 1)
                            in x["t"] for x in seq) for w in part)
    # the very lines the older table draws, above the same weeks (its table also has older weeks: "9.0" sits there)
    lab = {x["lab"]: x["w"] for x in c["newByLabel"]}
    both = [o for o in c["old"] if o["wk"] in lab]
    assert len(both) == 4 and any("9.0" in o["rel"] and o["wk"] not in lab for o in c["old"])
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
    assert c["year"] == ["rh All-time normal all installs", "cyr ── 2026 ──", "rh 5–7 Jan 5,400 installs (only 3 days)",
                         "crel 📦 v5.0 (31 Dec 2025) — mid-week", "rh 29 Dec 2025–4 Jan 📦 5,400 installs", "cyr ── 2025 ──",
                         "crel 📦 Update (23 Dec 2025) — mid-week", "rh 22–28 Dec 2025 📦 5,400 installs", "rh 15–21 Dec 2025 5,400 installs"]
