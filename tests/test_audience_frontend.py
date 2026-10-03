"""👥 Audience tab — the page (frontend/index.html, module AU), run for real by tests/audience_frontend.js in a node vm on
the synthetic world of tests/audience_tab_synth.py (made-up apps, ids and money; the file written by the real build
step). Checked here, the page's own arithmetic against an independent recount in Python / engine.audience:

  * render: every section card, the four summary tiles, the tags ("GA4 (lagbhag exact)", "andaza", "GA4 data aa raha
    hai"), the all-apps table only on All apps, the 🔒 module panels marked SAMPLE;
  * numbers: each app's buckets between its window months = engine.audience's last_open (users and the dead_lo curve);
    the all-apps pool = the build's portfolio (tiered months, dead / dead_lo, install months, most month) and journey /
    long-term / money; the GA4 app shows its dead_lo – dead range; the money scenario (10 % and "By age");
  * $ / ₹: the dashboard's currency (₹ = $ × usd_inr), on every money string, switched by the top bar's 💱 (toggleCur);
  * the all-apps table on a phone: installed under the name, short numbers (2.6M, 412K), the full ones in a tip; a tap
    on a number shows it (the app stays shut), a tap on the name opens the app; the desktop form beside it unchanged;
  * the top bar drives the view: its App picker (setApp), a table row / Enter / "← All apps" setting it, the phone's
    Back button, leaving the screen, an app Audience has no row for; no picker / toggle / title block of its own, one
    "Data till … · N apps · x GA4, y andaza" line;
  * "Kyun? ▸" folds, mode chips, "Show all months", the day picker;
  * the 5-min refresh with a new build: same app / ₹ / mode / day / open folds, no jump to the top, no new Back step,
    the new file fetched;
  * tooltips: hover on a mouse, a tap pins, a swipe never does; the month chart's numbers and crosshair;
  * no pointer (AUDIENCE_TAB off): the screen says so (and render() keeps the nav item hidden).
Skipped where node is not installed."""

import gzip
import json
import math
import os
import re
import shutil
import subprocess

import pytest

from admob_iq import audience_build as ab
from admob_iq.config import settings
from admob_iq.engine import audience as aud_eng
from admob_iq.engine import uninstall as ueng
from tests import audience_tab_synth as sy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")
GA4, EST, PART, YOUNG = "Demo Gallery · Studio Nine", "Demo Notes", "Demo Timer · A/c 77", "Demo Young"


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("audfe"))
    data, site, dash = sy.make_world(root)
    assert ab.run(dash, data, site, settings()) == ["/audience*"]
    ab.pop_line()
    with gzip.open(os.path.join(site, ab.FILE), "rt", encoding="utf-8") as f:
        body = json.load(f)
    return {"root": root, "data": data, "site": site, "dash": dash, "body": body,
            "by": {e["n"]: e for e in body["apps"]}}


@pytest.fixture(scope="module")
def report(world):
    if NODE is None:
        pytest.skip("node is not installed")
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    sp, fx = os.path.join(world["root"], "app.js"), os.path.join(world["root"], "fixture.json")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(js)
    with open(fx, "w", encoding="utf-8") as f:
        json.dump({"dashboard": world["dash"], "audience": world["body"]}, f)
    subprocess.run([NODE, "--check", sp], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "audience_frontend.js"), sp, fx], check=True,
                         capture_output=True, text=True, timeout=180)
    rep = json.loads(out.stdout)
    assert rep.get("errors") == [], rep.get("errors")
    return rep


def _n(v):
    return "{:,}".format(int(round(v)))


def _close(a, b, tol=1e-4):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


# ── render ──────────────────────────────────────────────────────────────────────────────────────────────────────────
@needs_node
def test_every_section_renders_on_all_apps(report):
    r = report["render"]
    assert r["screen"] == "audience" and r["title"] == "Audience" and r["strip"] == 4
    assert r["ids"] == ["au-s-phone", "au-s-day", "au-s-journey", "au-s-pakke", "au-s-dead", "au-s-mdead", "au-s-mact",
                        "au-s-dau", "au-s-money", "au-s-how", "au-s-table", "au-s-module"]
    h = r["html"]
    for label in ("Installed now", "Sleeping 28+ days", "Dead 3+ months", "If 10% wake up: money / month"):
        assert '<div class="au-l">%s</div>' % label in h
    assert "1 apps GA4 (lagbhag exact) · 3 andaza" in h and "SAMPLE numbers — asli nahi" in h
    assert "Demo Clock" in h                                                            # the apps without GA4: named
    # the top bar's App / ₹$ drive the screen: no picker, toggle or title block of its own — one line under the top bar
    assert 'id="au-app"' not in h and "data-au-cur" not in h and 'class="au-hd"' not in h and "<h2" not in h
    assert h.startswith('<div id="au-root"><div class="au-meta">Data till ')
    assert re.search(r'<div class="au-meta">Data till \d{1,2} [A-Z][a-z]{2} \d{4} · 4 apps · 1 GA4, 3 andaza</div>', h)
    for sec in ("au-s-mdead", "au-s-mact"):                                             # "Top" = the answer's month
        part = h[h.index('id="%s"' % sec):]
        part = part[:part.index("</section>")]
        month = re.search(r'<div class="au-ans"><b>([A-Z][a-z]{2} \d{4})</b>', part).group(1)
        assert part.count('<span class="au-topb">Top</span>') == 1 and month + ' <span class="au-topb">Top</span>' in part


@needs_node
def test_each_apps_page_carries_its_own_tag_and_no_table(report, world):
    by = world["by"]
    for name, e in by.items():
        h = report["apps"][e["k"]]
        assert 'id="au-s-table"' not in h and 'class="au-crumb"' in h and "data-au-cur" not in h and 'id="au-app"' not in h
        assert re.search(r'<div class="au-meta">Data till \d{1,2} [A-Z][a-z]{2} \d{4}</div>', h)
    g = report["apps"][by[GA4]["k"]]
    au = by[GA4]["au"]
    assert '<span class="au-tg">GA4 (lagbhag exact)</span>' in g
    assert "Dead 1+ month: <b>%s–%s</b>" % (_n(au["lo"][0]), _n(au["d"][0])) in g                    # the range, lo first
    assert "kuch log app khole bina hi hata dete hain" in g
    t = report["apps"][by[PART]["k"]]
    assert "andaza · GA4 data aa raha hai" in t and "GA4 data aa raha hai:" in t
    n = report["apps"][by[EST]["k"]]
    assert '<span class="au-tg au-est">andaza</span>' in n and "aa raha hai" not in n


# ── numbers ─────────────────────────────────────────────────────────────────────────────────────────────────────────
@needs_node
def test_buckets_are_the_engines_last_open(report, world):
    e = world["by"][GA4]
    store = json.load(gzip.open(os.path.join(world["data"], "ga4_audience", e["k"] + ".json.gz"), "rt"))
    st = json.load(gzip.open(os.path.join(world["data"], "ga4_uninstall", e["k"] + ".json.gz"), "rt"))
    out = aud_eng.derive_app(store, ueng.fill_days(st))
    bk = report["numbers"]["apps"][e["k"]]["bk"]
    assert [(b["f"], b["t"], b["v"], b["vl"]) for b in bk] == \
        [(x["from"], x["to"], x["users"], x["users_lo_curve"]) for x in out["last_open"]]
    for name in (EST, PART, YOUNG):                                       # the estimate: the same rule on its months
        a = world["by"][name]
        bk = report["numbers"]["apps"][a["k"]]["bk"]
        d, mo = a["au"]["d"], a["au"]["mo"]
        want = [a["au"]["inst"] - d[0]] + [d[i - 1] - d[i] for i in range(1, len(d))] + [d[-1]]
        assert [b["v"] for b in bk] == want and [b["f"] for b in bk] == [0] + mo and all(b["vl"] is None for b in bk)


@needs_node
def test_the_all_apps_pool_is_the_builds_portfolio(report, world):
    A, P = report["numbers"]["all"], world["body"]["all"]
    au = P["au"]
    assert (A["mo"], A["d"], A["lo"], A["src"], A["inst"], A["ins"]) == (au["mo"], au["d"], au["lo"], au["src"], au["inst"], au["ins"])
    assert A["m"] == au["m"] and A["bands"] == au["bands"]
    for kind in ("dead", "active"):
        for how in ("count", "share"):
            x, y = A["most"][kind][how], au["most"][kind][how]
            assert (x is None) == (y is None)
            if x:
                assert (x["month"], x["users"], x["installs"]) == (y["month"], y["users"], y["installs"]) and _close(x["share"], y["share"])
    for N, j in P["j"].items():
        assert (A["j"][N] is None) == (j is None)
        if j:
            assert all(_close(A["j"][N][i], j[i], 2e-4) for i in range(3)) and A["j"][N][3:] == j[3:]
    assert set(A["lt"]) == set(P["lt"]) and all(_close(A["lt"][L][0], P["lt"][L][0], 2e-4) and A["lt"][L][1:] == P["lt"][L][1:] for L in P["lt"])
    assert _close(A["arp"], P["rev28"] / P["a1_28"], 1e-3)
    assert A["inst2"] == sum(e["inst"] for e in world["body"]["apps"] if not e["kam"])
    assert A["sl"] == sum(e["sl"] for e in world["body"]["apps"] if not e["kam"])


@needs_node
def test_the_money_scenario(report, world):
    chance = lambda f: .15 if f < 2 else .08 if f < 4 else .04 if f < 7 else .02
    tot10 = totAge = 0.0
    for e in world["body"]["apps"]:
        r = report["numbers"]["apps"][e["k"]]
        au = e["au"]
        dead_tot = au["d"][au["mo"].index(1)] if au["src"] == "ga4" else e["sl"]
        assert r["deadTot"] == dead_tot
        w = 0 if e["kam"] or not e["sl"] else dead_tot * 0.1
        assert _close(r["w10"]["w"], w, 1e-9) and _close(r["w10"]["usd"], w * e["fq"] * e["ra"] * 30, 1e-9)
        wa = sum(b["v"] * chance(b["f"]) for b in r["bk"] if b["f"] >= 1 and b["v"])
        assert _close(r["wage"]["w"], wa, 1e-9) and _close(r["wage"]["users"], wa * e["fq"], 1e-9)
        tot10 += r["w10"]["usd"]
        totAge += r["wage"]["usd"]
    assert _close(report["numbers"]["all"]["w10"]["usd"], tot10, 1e-9) and _close(report["numbers"]["all"]["wage"]["usd"], totAge, 1e-9)


@needs_node
def test_tiers_labels_and_shares(report):
    n = report["numbers"]
    assert n["tier"] == [aud_eng.tier_months(30), aud_eng.tier_months(31), aud_eng.tier_months(400), aud_eng.tier_months(1300)]
    assert n["lab"] == ["0–1 months", "1–2 months", "12–15 months", "24–30 months", "2–3 years", "3+ years", "15+ months"]
    assert n["p"] == ["33%", "<0.1%", "0%", ""]


@needs_node
def test_money_in_dollars_and_rupees(report, world):
    fx = world["dash"]["usd_inr"]
    assert report["money"]["USD"]["m"] == ["$1,234", "$2.3", "$0.012", "$12K", "$0"]
    want = ["₹" + _n(1234.4 * fx), "₹" + _n(2.25 * fx), "₹%.1f" % (0.0123 * fx), "₹%.1fM" % (12345 * fx / 1e6), "₹0"]
    assert report["money"]["INR"]["m"] == want
    top = max(world["body"]["apps"], key=lambda e: report["numbers"]["apps"][e["k"]]["w10"]["usd"])
    usd = report["numbers"]["apps"][top["k"]]["w10"]["usd"]
    cell = lambda v, s: '<td class="au-r au-m"><span class="au-dk">%s%s</span>' % (s, _n(v) if v >= 10 else ("%.1f" % v))   # the desktop form
    assert cell(usd, "$") in report["money"]["USD"]["html"] and cell(usd * fx, "₹") in report["money"]["INR"]["html"]
    assert "₹ / month" in report["money"]["INR"]["html"] and "$ / month" in report["money"]["USD"]["html"]


# ── the all-apps table on a phone ─────────────────────────────────────────────────────────────────────────────────────
def _jr(v):                                                                              # Math.round (half up)
    return int(math.floor(v + 0.5))


def _cn(v):                                                                              # the page's CN: 2.6M · 412K · 4.1K · 950
    a = abs(v)
    if a >= 1e6:
        return ("%.0f" if a >= 1e8 else "%.1f") % (v / 1e6) + "M"
    if a >= 1e4:
        return "%dK" % _jr(v / 1e3)
    if a >= 1e3:
        return "%.1fK" % (v / 1e3)
    return _n(v)


def _mc(v, s):                                                                           # the page's MC (v already in s)
    a = abs(v)
    if a >= 1e3:
        return s + _cn(v)
    if a >= 10:
        return s + "{:,}".format(_jr(v))
    if a >= 1:
        return s + "%.1f" % v
    return s + ("0" if a == 0 else repr(float("%.2g" % v)))


@needs_node
def test_the_phone_table_uses_short_numbers_with_the_full_ones_in_a_tip(report, world):
    ph, fx = report["phone"], world["dash"]["usd_inr"]
    by_k = {e["k"]: e for e in world["body"]["apps"]}
    for cur, sym, f in (("USD", "$", 1.0), ("INR", "₹", fx)):
        r = ph[cur]
        assert '<span class="au-dk">Sleeping<br>28+ days</span><span class="au-ph">Sleeping</span>' in r["head"]
        assert '<span class="au-ph">10%% wapas = %s/mahina</span>' % sym in r["head"] and "10%% wake up =<br>%s / month" % sym in r["head"]
        assert "number pe tap — poora number" in r["hint"] and "row pe tap karo — us app ka view khulega" in r["hint"]
        for row in r["rows"]:
            e, usd = by_k[row["k"]], report["numbers"]["apps"][row["k"]]["w10"]["usd"]
            if e["kam"]:
                assert row["inst"] == "installed: data kam"
                continue
            assert row["inst"] == _cn(e["inst"]) + " installed"                           # under the name, short
            assert row["sl"] == _cn(e["sl"]) and row["slDk"] == _n(e["sl"])                 # phone short · desktop full
            dk, k, short = row["money"]
            assert k == row["k"] and short == _mc(usd * f, sym) and dk.startswith(sym)
    big = world["body"]["apps"][0]
    t = ph["USD"]["tip"]                                                                  # the tip: the full numbers
    assert "<b>%s</b>" % _n(big["inst"]) in t and "<b>%s (" % _n(big["sl"]) in t and "10% wapas = $ / mahina" in t


@needs_node
def test_a_tap_on_a_number_shows_its_tip_a_tap_on_the_name_opens_the_app(report, world):
    ph = report["phone"]
    big = world["body"]["apps"][0]
    assert ph["numTap"]["pinned"] is True and ph["numTap"]["sets"] == [] and _n(big["inst"]) in ph["numTap"]["tip"]
    assert ph["nameTap"]["sets"] == [big["n"]]


def test_the_phone_rules_hide_one_form_each():
    h = open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read()
    assert "@container au (min-width:560px){#au-root .au-ph{display:none!important}}" in h
    assert "@container au (max-width:559.98px){#au-root .au-dk{display:none!important}}" in h


# ── navigation ──────────────────────────────────────────────────────────────────────────────────────────────────────
@needs_node
def test_the_top_bars_app_drives_the_view_and_a_row_sets_it(report, world):
    v = report["nav"]
    big, second = world["body"]["apps"][0], world["body"]["apps"][1]
    r = v["row"]                                                                         # a row → the GLOBAL App (setApp)
    assert r["sets"] == [big["n"]] and r["APP"] == big["n"] and r["app"] == big["k"] and r["screen"] == "audience"
    assert r["st"] == ["app"] and r["idx"] == 1 and r["crumb"] and r["table"] is False   # the top bar's own Back step
    assert r["title"] == "Audience · Demo Gallery"
    assert v["back"] == {"app": "", "APP": "", "st": [], "idx": 0, "table": True, "screen": "audience"}   # Back = All apps
    assert v["enter"] == {"APP": second["n"], "app": second["k"], "st": ["app"]}         # Enter on a row: the same
    assert v["header"]["app"] == v["header"]["want"] and v["header"]["st"] == ["app"] and v["header"]["crumb"] and not v["header"]["table"]
    assert v["allBtn"] == {"app": "", "APP": "", "st": [], "idx": 0}                     # "← All apps" = the top bar's All apps
    assert v["left"] == {"screen": "placements", "st": ["app"], "APP": second["n"]}      # the top bar keeps the app across tabs
    assert v["back2"] == {"app": second["k"], "crumb": True}


@needs_node
def test_an_app_without_audience_data_says_so_in_one_line(report):
    v = report["nav"]
    n = v["noApp"]
    assert n["app"] == "!" and n["st"] == ["app"]
    assert '<p>Is app ka GA4 data nahi — Audience nahi ban sakta</p>' in n["html"] and 'data-au-all="1"' in n["html"]
    assert 'id="au-strip"' not in n["html"] and "au-crumb" not in n["html"] and "au-meta" not in n["html"]
    assert v["noAppBack"] == {"APP": "", "app": "", "st": [], "table": True}


@needs_node
def test_two_apps_with_one_name_the_row_tapped_is_shown(report):
    d = report["nav"]["dup"]
    assert d["none"] == d["want"][0] and d["picked"] == d["want"][1]


@needs_node
def test_folds_chips_currency_and_day(report):
    c = report["controls"]
    assert c["closed"] and c["opened"] == {"set": ["dead"], "attr": True} and c["reclosed"] == {"set": [], "attr": False}
    assert c["mode"] == {"mode": "age", "on": True, "table": True}
    assert c["more"]["before"] == 6 and c["more"]["after"] > 6 and c["more"]["set"] == ["mdead"] and c["more"]["btn"]
    # the top bar's 💱: the screen repainted at once in ₹, then back in $ (nothing of its own to click)
    assert c["inr"] == {"cur": "INR", "rupee": True, "screen": "audience", "repainted": True, "mode": "10", "own": False}
    assert c["usd"] == {"cur": "USD", "dollar": True, "screen": "audience"}
    assert c["day"] == {"day": "2026-03-15", "val": True} and c["dayChip"] == {"day": "2026-01-01", "on": True}


@needs_node
def test_the_refresh_brings_the_view_back_as_it_was(report):
    r = report["refresh"]
    assert r["screen"] == "audience" and r["newData"] and r["silent"] is False
    assert r["S"] == {"app": r["want"], "mode": "age", "day": "2026-02-01", "open": ["money", "dead"]}
    assert r["st"] == ["app"] and r["hist"] == 2 and r["scrolls"] == []                 # no new Back step, no jump
    assert r["crumb"] and r["fold"] and r["ageOn"] and r["cur"] == "INR" and r["rupee"]   # the top bar's App and ₹ kept
    assert r["fetched"] == ["audience.json.gz?v=0123456789ab"]                           # the new build's file


# ── tooltips ────────────────────────────────────────────────────────────────────────────────────────────────────────
@needs_node
def test_hover_shows_a_tap_pins_a_swipe_never_does(report, world):
    t = report["tips"]
    assert t["hover"]["on"] and not t["hover"]["pin"] and not t["hover"]["pinned"]
    assert "2–3 months se nahi khola" in t["hover"]["html"] and "GA4 + andaza" in t["hover"]["html"]
    assert t["tap"] == {"on": True, "pin": True, "pinned": True} and t["swipe"] == {"on": False}
    ch = t["chart"]
    assert ch["svg"].startswith('<svg id="au-mchart" data-hv="1" viewBox="0 0 600 150"') and ch["spk"]["w"] == 600
    assert ch["labels"] and all(re.fullmatch(r"\d+%", x) for x in ch["labels"])         # numbers printed on the chart
    assert "abhi bhi phone me" in ch["read"]
    assert t["hov"] is True and t["hovPin"] is True and t["xh"] == "1" and t["hovTip"] == ch["spk"]["last"]


@needs_node
def test_without_the_file_the_screen_says_so(report):
    assert report["off"]["ptr"] is False and "Audience ka data is build me nahi bana" in report["off"]["html"]


def test_the_nav_item_follows_the_pointer_and_the_screen_is_in_every_list():
    h = open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read()
    assert '<li id="nav-aud-li" hidden><button data-screen="audience">' in h
    assert "{ const li=document.getElementById('nav-aud-li'); if(li) li.hidden=!AU.ptr(); }" in h
    assert "root.append(renderAudience());" in h and "if(id==='audience') AU.show(); else AU.left();" in h
    assert "else if(cur==='audience') show('audience');" in h                           # refreshData's re-open list
    assert 'audience:["Audience",' in h and 'body[data-screen="audience"] #rangectl' in h
    css = h[h.index("/* ---------- 👥 Audience"):h.index("/* ---------- /Audience ---------- */")]
    for line in css.splitlines()[1:]:                                                    # every rule scoped
        if line.strip() and not line.startswith("@") and "{" in line:
            sel = line.split("{")[0]
            assert all(p.strip().startswith(("#au-root", "#au-tip", "body[data-screen=\"audience\"]", "body:not([data-screen=\"audience\"])"))
                       for p in sel.split(",")), line
