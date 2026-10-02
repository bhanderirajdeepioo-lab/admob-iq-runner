"""🗂 Alert history in the Studios (owner, 2 Oct: "vo aana chaiye" — the older views had it, the Studios lost it). Rendered for
real by tests/alert_history_frontend.js (the dashboard script in a node vm) from Studio files the REAL build code made of the
synthetic sites (tests/studio_synth.py, active_studio_synth.py, value_studio_synth.py) plus synthetic closed alerts and older
changes put into the very lists the older views read (no real data). Checked, in the Uninstall, Active users and Install
value Studios, on All apps and an app's page:

  * under "What changed?" two folds, "▸ Older changes (N)" and "▸ Closed alerts (N)", N = every row of the lists the older
    views showed (Uninstall: the detail's alerts_closed / old_changes; Active users: the dashboard's lists on All apps, the
    app's own file on its page; Install value: the info rows over 30 days, the closed list / the app's file) — nothing trimmed;
    the older partial folds ("✅ Fixed — last 7 days", "🗄 Older", "🗄 Old info", "Band hue …") are gone into them;
  * a closed alert says when it opened (as which status), when it closed, how long it stayed open and why, in plain words —
    run times only when both are kept, else both data days; its status Normal (recovered) or N/A;
  * "Open →" on every card and table row, the older views' targets: an install-week change → the install-week grid (its week),
    a rate → the daily chart, an update → its 📦 block (a late one at 30 days); Active users: old users → the chart, new users
    back → the grid, sessions / time / ads / revenue → that section of the older page (the fold opens); Install value: money
    back → week by week, a country → Countries, a version → Users by app version, long-term → Long-term, the link → Data check
    (missing here → the older page's). From All apps it opens the app's page and jumps there once it is drawn;
  * the folds the viewer opened stay open through the 5-minute refresh (render()); the phone layout: the fold heads' hints
    stay short (a long nowrap hint once made the page 443 px wide on a 375 px phone), Open → is a 32 px tap target;
  * the words: English labels, Hinglish explanations in Roman script, the six status words, never "100 me" / "per 1,000".
Skipped where node is not installed."""

import gzip
import json
import os
import re
import shutil
import subprocess

import pytest

from admob_iq import active_studio_build as asb
from admob_iq import build_static
from admob_iq import uninstall_studio_build as usb
from admob_iq import value_studio_build as vsb
from admob_iq.config import settings
from tests import active_studio_synth as ass
from tests import studio_synth as ss
from tests import value_studio_synth as vss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
BANNED = re.compile(r"\bis hafte\b|\bthis week\b|\babhi ka\b|Provisional|kacch?a\b|kacche|Estimate|/1k|\bpts\b|\bpp\b|\bpoints?\b"
                    r"|cohort|ARPDAU|eCPM|mediation|\bsettled\b|\brecent\b", re.I)
PER = re.compile(r"\b100 me\b|\b1,000 me\b|\bhar 1,000\b|\bper 1,000\b|\bper 100\b")
DEVA = re.compile("[ऀ-ॿ]")
SIX = {"Worse", "Watch", "Better", "Normal", "Too early", "N/A"}


def _script(tmp):
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    path = os.path.join(tmp, "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    return path


def _gz(site, name):
    with gzip.open(os.path.join(site, name), "rt", encoding="utf-8") as f:
        return json.load(f)


def _run(root, fx, mode, **bodies):
    os.makedirs(fx, exist_ok=True)
    for name, body in bodies.items():
        with open(os.path.join(fx, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(body, f)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "alert_history_frontend.js"), _script(root), fx, mode],
                         check=True, capture_output=True, text=True, timeout=600)
    rep = json.loads(out.stdout)
    assert rep["errors"] == [], rep["errors"]
    return rep


@pytest.fixture(scope="module")
def us(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("hist_us"))
    site, cfg, dash = ss.make_site(root)
    assert build_static._studio_step(dash, os.path.join(root, "data"), site, dict(settings()))[0] == "/uninstall_studio.json.gz"
    return _run(root, os.path.join(root, "fx"), "us", dashboard=dash, uninstall_studio=_gz(site, usb.FILE),
                uninstall=_gz(site, "uninstall.json.gz"))


@pytest.fixture(scope="module")
def act(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("hist_act"))
    site, cfg, dash = ass.make_site(root)
    assert build_static._active_studio_step(dash, os.path.join(root, "data"), site, dict(settings()))[0] == "/active_studio.json.gz"
    files = {r["key"]: _gz(site, r["file"]) for r in dash["active"]["apps"]}
    return _run(root, os.path.join(root, "fx"), "active", dashboard=dash, active_studio=_gz(site, asb.FILE), active_files=files,
                active_portfolio=_gz(site, dash["active"]["portfolio"]["file"]))


@pytest.fixture(scope="module")
def val(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("hist_val"))
    site, cfg, dash = vss.make_site(root)
    assert build_static._value_studio_step(dash, os.path.join(root, "data"), site, dict(settings())) == ["/value_studio.json.gz"]
    files = {r["key"]: _gz(site, r["file"]) for r in dash["value"]["apps"] if r.get("file")}
    return _run(root, os.path.join(root, "fx"), "value", dashboard=dash, value_studio=_gz(site, vsb.FILE), value_files=files)


def J(rep, k):
    assert k in rep["out"], (k, rep["errors"])
    return json.loads(rep["out"][k])


def _text(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h or "").replace("&amp;", "&").replace("&quot;", '"')).strip()


def _fold(h, key):
    """one fold's markup: <details … data-fold="key"> … </details>"""
    i = h.index('data-fold="%s"' % key)
    return h[h.rindex("<details", 0, i):h.index("</details>", i) + 10]


def _count(summary):
    return int(re.search(r"\((\d+)\)", summary).group(1))


def _cards(fold, p):
    """the history fold's cards / rows: each one carries its Open → target"""
    return re.findall(r'data-hgo="([^"]+)"', fold)


# ── Uninstall ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_uninstall_all_apps_folds_hold_every_closed_alert_and_older_change(us):
    a = J(us, "all")
    assert a["sumOld"].startswith("▸ Older changes (") and a["sumCl"].startswith("▸ Closed alerts (")
    assert _count(a["sumOld"]) == a["exp"]["old"] >= 3 and _count(a["sumCl"]) == a["exp"]["cl"] >= 3
    # folded by default (no `open`), every row still in the markup; opened: the very rows, one card each
    assert 'data-fold="hold" open' not in a["shut"] and 'data-fold="hcl" open' not in a["shut"]
    assert len(_cards(_fold(a["open"], "hold"), "us")) == a["exp"]["old"]
    assert len(_cards(_fold(a["open"], "hcl"), "us")) == a["exp"]["cl"]
    assert not a["theekFold"]                                            # the "✅ Fixed — last 7 days" fold went into Closed alerts
    n_open = len(re.findall(r'<div class="us-ac us-s-(?:bigda|dhyan|behtar|normal)"', a["shut"].split('<details')[0]))
    assert re.search(r"\b%d shown · (\d+) folded below" % n_open, a["hint"])
    # the Table view: the same rows, each with its Open → (and an Open column)
    for k, n in (("hold", a["exp"]["old"]), ("hcl", a["exp"]["cl"])):
        f = _fold(a["tbl"], k)
        assert len(re.findall(r'<tr data-app="\d+" data-go="\d+" data-hgo="[^"]+"', f)) == n and ">Open</th>" in f


def test_uninstall_a_closed_alert_tells_when_it_opened_closed_how_long_and_why(us):
    a, g = J(us, "all"), J(us, "go")
    f = _fold(a["open"], "hcl")
    cards = re.split(r'(?=<div class="us-ac us-s-ah us-ahc")', f)[1:]
    by = {}
    for c in cards:
        by[re.search(r'data-hgo="([^"]+)"', c).group(1)] = _text(c)
    h1, h2, h3 = by[g["specs"]["h1"]], by[g["specs"]["h2"]], by[g["specs"]["h3"]]
    # h1: both run times kept → IST times; 05:00 UTC → 10:30 IST, 06:30 UTC → 12:00 IST; 9 IST days apart; recovered
    assert re.search(r"Opened \d{1,2} \w{3}(?: \d{4})?, 10:30 IST as Worse", h1) and re.search(r"Closed \d{1,2} \w{3}(?: \d{4})?, 12:00 IST", h1)
    assert "Open for 9 days" in h1 and "Why closed: Back to normal" in h1 and h1.startswith("Normal ")
    assert "(data days)" not in h1
    # h2: no opened_at (its alert_at is the run that SENT it) and no reason → both data days, 5 days, "Not recorded", N/A
    assert "(data days)" in h2 and "Open for 5 days" in h2 and "Why closed: Not recorded" in h2 and h2.startswith("N/A ")
    assert "as Watch" in h2 and "✅ Closed ·" in h2
    # h3: a newer update replaced it
    assert "Why closed: Newer update replaced it" in h3 and h3.startswith("N/A ")
    for t in (h1, h2, h3):
        assert "🕒 Alert time:" in t and "Change started:" in t and "Open →" in t
    # the reasons said in Hinglish once, under the fold's head
    assert "Back to normal = number wapas" in _text(f) and "Not recorded = purana alert" in _text(f)


def test_uninstall_older_changes_say_they_are_not_alerts(us):
    f = _fold(J(us, "all")["open"], "hold")
    for c in re.split(r'(?=<div class="us-ac us-s-ah us-ahc")', f)[1:]:
        t = _text(c)
        assert t.startswith("🗄 Older · not an alert") and "🕒 Alert time: — (not an alert, never sent)" in t and "Open →" in t
        assert "Next step" not in t                                        # nothing to do: compact, no "Kuch nahi" box


def test_uninstall_open_targets_are_the_older_views_and_open_the_apps_page(us):
    g = J(us, "go")
    i0, i1 = g["a0i"], g["a1"]
    assert g["specs"]["h1"] == "%d|coh|%s|%s|0" % (i0, g["from"], g["to"])     # an install week → the grid, its week, day 0
    assert g["specs"]["h2"] == "%d|rate" % i0                                # a rate → the daily chart
    assert g["specs"]["h3"] == "%d|imp|%s|" % (i1, g["key"])                 # an update → its 📦 block
    assert g["specs"]["late"] == "%d|imp|%s|30" % (i1, g["key"])             # … a late one at 30 days
    assert g["specs"]["old"].split("|")[1] == "coh"
    # from All apps: the app's page opens and the jump waits for it; an update goes through the 📦 jump (its own wait)
    assert g["calls"][0] == ["open", g["a0"]] and g["pj"]["id"] == g["a0"] and g["pj"]["s"][1] == "coh"
    assert g["calls"][1] == ["impgo", g["a1id"], g["key"], "uni", None]


def test_uninstall_app_page_its_folds_targets_and_the_waiting_jump(us):
    p = J(us, "page")
    h = p["page"]
    assert p["view"]["VIEW"] == "app"
    for i in ("us-pg-rate", "us-pg-coh", "us-pg-chg"):
        assert ('id="%s"' % i) in h
    assert re.search(r'class="us-rh" data-cw="\d{4}-\d\d-\d\d"', h)            # each install week's row can be found
    assert _count(p["sumOld"]) == p["exp"]["old"] and _count(p["sumCl"]) == p["exp"]["cl"]
    assert 'data-fold="pghold" open' in h and 'data-fold="pghcl" open' in h
    assert p["calls"] and p["waited"] and p["pjAfter"] is None               # the jump made from All apps happens on the page
    assert p["rateFl"]                                                       # on the page: straight to the chart, flashed
    assert 'data-fold="dhold"' in p["drawer"] and 'data-fold="dhcl"' in p["drawer"]   # the quick look has them too


# ── Active users ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_active_folds_hold_the_older_findings_and_the_closed_alerts(act):
    a = J(act, "all")
    assert _count(a["sumOld"]) == a["exp"]["old"] == 2 and _count(a["sumCl"]) == a["exp"]["cl"] == 2
    assert not a["theekFold"] and not a["olderFold"]                     # the partial folds went into the two
    assert len(_cards(_fold(a["open"], "hold"), "as")) == 2 and len(_cards(_fold(a["open"], "hcl"), "as")) == 2
    cl = _text(_fold(a["open"], "hcl"))
    assert re.search(r"Opened \d{1,2} \w{3}(?: \d{4})?, 10:30 IST as Worse", cl) and "Why closed: Back to normal" in cl
    assert "Why closed: Check window ended" in cl and "(data days)" in cl and "Open for 10 days" in cl
    assert "Check window ended = jin installs" in cl
    assert "har app ki poori list uske page pe" in _text(_fold(a["open"], "hold"))
    for k in ("hold", "hcl"):
        assert len(re.findall(r'<tr data-app="\d+" data-go="\d+" data-hgo="[^"]+"', _fold(a["tbl"], k))) == 2


def test_active_targets_and_jumps(act):
    g = J(act, "go")
    i = g["i0"]
    exp = {"ret": "big", "d7": "tri", "sess": "old:act-use", "time": "old:act-use", "ads": "old:act-rev", "arpdau": "old:act-rev",
           "price": "old:act-rev", "brk": "big", "old": "old:act-use", "oldPrice": "old:act-rev"}
    assert g["specs"] == {k: "%d|%s" % (i, v) for k, v in exp.items()}
    # from All apps: the page opens and the jump waits (a chart here) / the older page's section opens with it (ACTJUMP)
    assert g["calls"][0][:2] == ["open", g["a0"]] and g["pj"] == {"id": g["a0"], "sec": "big"}
    assert g["calls"][1] == ["open", g["a0"], "act-use"] and g["aj"] == "act-use"
    p = J(act, "page")
    assert p["mode"] == "page" and 'id="as-pg-big"' in p["page"] and 'id="as-pg-tri"' in p["page"]
    assert _count(p["sumOld"]) == p["exp"]["old"] == 3 and _count(p["sumCl"]) == p["exp"]["cl"] == 2   # the app's own file
    assert p["triFl"] and p["rr"] == ["act-use"] and p["aj"] == "act-use"


# ── Install value ────────────────────────────────────────────────────────────────────────────────────────────────

def test_value_folds_hold_the_older_info_and_the_closed_alerts(val):
    a = J(val, "all")
    assert _count(a["sumOld"]) == a["exp"]["old"] >= 2 and _count(a["sumCl"]) == a["exp"]["cl"] == 1
    assert not a["oldFold"] and not a["bandFold"]
    assert len(_cards(_fold(a["open"], "hold"), "vs")) == a["exp"]["old"] and len(_cards(_fold(a["open"], "hcl"), "vs")) == 1
    cl = _text(_fold(a["open"], "hcl"))
    assert re.search(r"Opened \d{1,2} \w{3}(?: \d{4})?, 10:30 IST as Worse", cl) and "Open for 27 days" in cl and "Why closed: Back to normal" in cl
    p = J(val, "page")
    assert p["mode"] == "p"
    assert _count(p["sumCl"]) == p["exp"]["cl"] == 2                                     # the app's own file (closed alerts filtered out no more)
    assert _count(p["sumOld"]) == p["exp"]["oldInfo"] + 1                                # + the row only its own file has
    for i in ("vs-pg-cur", "vs-pg-wk", "vs-pg-cty", "vs-pg-chg"):
        assert ('id="%s"' % i) in p["page"]


def test_value_targets_and_jumps(val):
    g = J(val, "go")
    i = g["i0"]
    assert g["specs"] == {"pay": "%d|wk|val-pay|" % i, "loss": "%d|wk|val-pay|" % i, "geo": "%d|cty|val-cty|" % i, "cost": "%d|cty|val-cty|" % i,
                          "ver": "%d|ver|val-ver|v9.9" % i, "lng": "%d|lng|val-long|" % i, "link": "%d|chk|val-chk|" % i,
                          "mix": "%d|cty|val-cty|" % i, "spend": "%d|wk|val-pay|" % i, "k": "%d|chk|val-chk|" % i, "vd": "%d|ver|val-ver|" % i,
                          "lu": "%d|lng|val-long|" % i}
    assert g["calls"] == [g["a0"]] and g["pj"]["id"] == g["a0"] and g["pj"]["s"][1] == "cty"
    p = J(val, "page")
    assert p["ctyFl"]                                                        # on the page: straight to Countries, flashed
    assert p["rr"] == [["val-chk", True]]                                    # no Data check here → the older page's, opened


# ── all three ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_open_folds_survive_the_refresh(us, act, val):
    r = J(us, "refresh")
    assert r["cl"] and not r["old"] and r["folds"] == ["hcl"]               # opened, opened + shut again: as the viewer left them
    for rep in (act, val):
        r = J(rep, "refresh")
        assert r["cl"] and r["old"] and r["oldShut"]


def test_phone_layout_short_fold_heads_and_tap_targets(us, act, val):
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    for p in ("us", "as", "vs"):
        R = ":is(#%s-root,#%s-layer)" % (p, p)
        assert re.search(re.escape(R) + r" \.%s-opn\{[^}]*min-height:32px" % p, html)          # Open → is a 32 px tap target
        assert re.search(re.escape(R) + r" \.%s-ahl\{display:flex;flex-wrap:wrap" % p, html)    # the closed line wraps
        assert re.search(re.escape(R) + r" \.%s-ahg\{display:flex;flex-wrap:wrap" % p, html)    # so does the explanation
    # the fold heads' hints never wrap (white-space:nowrap) — they stay short, the explanation lives inside the fold
    for rep, keys in ((us, ("hold", "hcl")), (act, ("hold", "hcl")), (val, ("hold", "hcl"))):
        h = J(rep, "all")["shut"]
        for k in keys:
            pv = re.search(r'<span class="\w\w-pv">([^<]*)</span></summary>', _fold(h, k)).group(1)
            assert len(pv) <= 22, pv


def test_words(us, act, val):
    T = []
    for rep in (us, act, val):
        a = J(rep, "all")
        T += [_text(_fold(a["open"], "hold")), _text(_fold(a["open"], "hcl"))]
    T.append(_text(J(us, "page")["page"]))
    for t in T:
        assert not BANNED.search(t), BANNED.search(t).group(0)
        assert not PER.search(t) and not DEVA.search(t) and "NaN" not in t and "undefined" not in t
    for rep, p in ((us, "us"), (act, "as"), (val, "vs")):
        f = _fold(J(rep, "all")["open"], "hcl")
        words = set(re.findall(r'<span class="%s-chip %s-st-\w+"><i></i>([^<]+)</span>' % (p, p), f))
        assert words and words <= SIX, words
