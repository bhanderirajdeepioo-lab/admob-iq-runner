"""👥 Audience tab — the page (frontend/index.html, module AU), run for real by tests/audience_frontend.js in a node vm on
the synthetic world of tests/audience_tab_synth.py (made-up apps, ids and money; the file written by the real build
step). Checked here, the page's own arithmetic against an independent recount in Python / engine.audience:

  * render: every section card, the four summary tiles, the tags ("GA4 (lagbhag exact)", "andaza", "GA4 data aa raha
    hai"), the all-apps table only on All apps, the 🔒 module panels marked SAMPLE;
  * numbers: each app's buckets between its window months = engine.audience's last_open (users and the dead_lo curve);
    the all-apps pool = the build's portfolio (tiered months, dead / dead_lo, install months, most month) and journey /
    long-term / money; the GA4 app shows its dead_lo – dead range; the woken users (10 % and "By age");
  * who a notification can still reach (Android 12+ hibernates an app unused ~3 months: no push until it is opened):
    the sleeping bars in two groups (📲 1–3 months · 📢 3+ months) whose subtotals = the sums of their bars, the ⚠️
    danger zone (the 2–3 months bar), the strip's "📲 push · ⚠️ danger zone · 📢 sirf ads" line = the same bars;
  * "Paise ka calculator" (its "data se" K = the build's fitted curve × sessions, its range; no fit → the day 1 / 7 / 30
    join): "Kahan se jagayein" (📲 only the 1–3 month sleepers count, 📢 only the 3+ month ones, Dono all — push + ads =
    both), one open = A ads × eCPM ÷ 1000 (old users where the app has its own, else all users; the
    all-users R × sessions = arp), every lever combination = N × K × R × (1 + e), the ads break-even K × R × (1 + e) =
    money ÷ woken users (the "How to wake them" card: the data one), All apps = Σ every app's own, the card
    (each line can be redone by hand; the opens table with its row lit; the eCPM box; the old tiles gone, the asleep-for
    table behind "Kyun? ▸"), per-open decimals, the money table's fixed order, the chips set / lit / remembered;
  * $ / ₹: the dashboard's currency (₹ = $ × usd_inr), on every money string, switched by the top bar's 💱 (toggleCur);
  * the all-apps table on a phone: installed under the name, short numbers (2.6M, 412K), the full ones in a tip; a tap
    on a number shows it (the app stays shut), a tap on the name opens the app; the desktop form beside it unchanged;
  * the top bar drives the view: its App picker (setApp), a table row / Enter / "← All apps" setting it, the phone's
    Back button, leaving the screen, an app Audience has no row for; no picker / toggle / title block of its own, one
    "Data till … · N apps · x GA4, y andaza" line;
  * "Kyun? ▸" folds, mode chips, "Show all months", the day picker;
  * the 5-min refresh with a new build: same app / ₹ / mode / opens / eCPM / day / open folds, no jump to the top, no new Back step,
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


def _wake_days(e, apps, fitted=True):
    """Mirror of the page's wakeDays: the build's fitted active days in 30 (kf.d); without a fit, 1 + Σ(day 1…29) of the
    app's new-user "opened that day" share, joined linearly between its day 1 / 7 / 30 points (all apps' install-weighted
    curve when the app lacks one of them)."""
    if fitted and (e.get("kf") or {}).get("d"):
        return e["kf"]["d"]
    j = e.get("j") or {}
    if not all(j.get(k) for k in ("1", "7", "30")):
        j = {}
        for k in ("1", "7", "30"):
            xs = [a["j"][k] for a in apps if (a.get("j") or {}).get(k)]
            w = sum(x[3] for x in xs)
            j[k] = [sum(x[0] * x[3] for x in xs) / w] if w else None
        if not all(j.values()):
            return 1.0
    r1, r7, r30 = j["1"][0] or 0, j["7"][0] or 0, j["30"][0] or 0
    return 1 + sum(r1 + (r7 - r1) * (t - 1) / 6 if t <= 7 else r7 + (r30 - r7) * (t - 7) / 23 for t in range(1, 30))


CHANCE = lambda f: .15 if f < 2 else .08 if f < 4 else .04 if f < 7 else .02
VIAS = ("push", "ads", "both")


def _in_via(f, via):
    """The calculator's "Kahan se jagayein": 📲 push = asleep 1–3 months (a notification still reaches them), 📢 ads = 3+
    months (Android 12+ has put the app to sleep — only ads / Play), Dono = every sleeper (1+ month)."""
    return f >= 1 and (via == "both" or (f >= 3 if via == "ads" else f < 3))


def _base(r, via):
    """The sleepers a choice wakes from (the % levers): ads = the 3+ month bars (≤ every sleeper), push = the rest."""
    t = r["deadTot"]
    ads = min(t, sum(b["v"] for b in r["bk"] if b["f"] >= 3 and b["v"]))
    return ads if via == "ads" else t - ads if via == "push" else t


def _woken(e, r, mode, via="both"):
    """N: the woken users of one app at a "Kahan se" × "Kitne jaagein" lever (the page's wake)."""
    if e["kam"] or not e["sl"]:
        return 0
    if mode == "age":
        return sum(b["v"] * CHANCE(b["f"]) for b in r["bk"] if _in_via(b["f"], via) and b["v"])
    return _base(r, via) * int(mode) / 100


@needs_node
def test_the_woken_users_and_their_drift_away_days(report, world):
    """N = a share of the sleeping users (5 / 10 / 20 %, or By age); a woken sleeper opens once, then drifts away like
    the app's NEW users (its own 1 / 7 / 30-day curve): days a month = 1 + Σ(day 1…29) share, users a day = N × days ÷ 30
    (the owner, 4 Oct: never a loyal regular's whole month)."""
    apps = world["body"]["apps"]
    totW, totAge = {}, {}
    for e in apps:
        r = report["numbers"]["apps"][e["k"]]
        au = e["au"]
        dead_tot = au["d"][au["mo"].index(1)] if au["src"] == "ga4" else e["sl"]
        assert r["deadTot"] == dead_tot
        days = _wake_days(e, apps)
        assert 1 <= days <= 30 and _close(r["wd"], days, 1e-9)
        for via in VIAS:
            w = _woken(e, r, "10", via)
            assert _close(r["w10"][via]["w"], w, 1e-9) and _close(r["w10"][via]["users"], w * (days if w else 0) / 30, 1e-9)
            wa = _woken(e, r, "age", via)
            assert _close(r["wage"][via]["w"], wa, 1e-9) and _close(r["wage"][via]["users"], wa * (days if wa else 0) / 30, 1e-9)
            totW[via] = totW.get(via, 0) + w
            totAge[via] = totAge.get(via, 0) + wa
    for via in VIAS:
        assert _close(report["numbers"]["all"]["w10"][via]["w"], totW[via], 1e-9) and _close(report["numbers"]["all"]["wage"][via]["w"], totAge[via], 1e-9)


# ── "Paise ka calculator" ───────────────────────────────────────────────────────────────────────────────────────────
MODES, OPS, ECS = ("5", "10", "20", "age"), ("data", "1", "2", "5", "10", "20", "30"), ("-10", "0", "10", "20")
G = lambda *k: "|".join(k)                                  # a lever setting's key: via|mode|opens|ecpm


def _po(e):
    """One open's money (the page's perOpen): OLD users where the app has its own (R = ra ÷ sessions per returning user
    a day, A = R × 1000 ÷ eCPM), else ALL users (A = ads per user a day ÷ sessions per user a day, R = A × eCPM ÷ 1000)."""
    if not (e.get("ec") or 0) > 0:
        return None
    if e["own"] and (e.get("ra") or 0) > 0 and (e.get("spr") or 0) > 0:
        R = e["ra"] / e["spr"]
        return {"b": "old", "s": e["spr"], "E": e["ec"], "R": R, "A": R * 1000 / e["ec"]}
    if (e.get("ads") or 0) > 0 and (e.get("spu") or 0) > 0:
        A = e["ads"] / e["spu"]
        return {"b": "all", "s": e["spu"], "E": e["ec"], "A": A, "R": A * e["ec"] / 1000}
    return None


def _calc(e, r, apps, via, mode, op, ec):
    """N users × K opens × R × (1 + e) a month; users a day = N × active days ÷ 30 (the page's calc)."""
    p = _po(e)
    if p is None:
        return None
    w, days = _woken(e, r, mode, via), _wake_days(e, apps)
    Kd = max(1, _jr(days * p["s"]))
    K = Kd if op == "data" else int(op)
    ad = days if op == "data" else min(30, max(1, K / p["s"]))
    return {"w": w, "K": K, "Kd": Kd, "R": p["R"], "A": p["A"], "E": p["E"], "base": _base(r, via),
            "usd": w * K * p["R"] * (1 + int(ec) / 100), "users": w * ad / 30, "be": K * p["R"] * (1 + int(ec) / 100)}


@needs_node
def test_one_open_is_ads_times_ecpm(report, world):
    """R = A × eCPM ÷ 1000 for every app: its old users where it has its own, else all users — and the all-users R ×
    sessions per user a day is the revenue per daily user (arp) again."""
    po = report["calc"]["po"]
    bases = {}
    for e in world["body"]["apps"]:
        want, got = _po(e), po[e["k"]]
        assert got["b"] == want["b"] and all(_close(got[k], want[k], 1e-9) for k in ("s", "E", "R", "A"))
        assert _close(got["A"] * got["E"] / 1000, got["R"], 1e-9)
        assert _close(e["ads"] / e["spu"] * e["ec"] / 1000 * e["spu"], e["arp"], 1e-5)        # R_all × sessions = arp
        if got["b"] == "old":
            assert _close(got["R"] * got["s"], e["ra"], 1e-9)                                  # R × sessions = ra
        bases[e["n"]] = got["b"]
    assert bases == {GA4: "old", EST: "old", PART: "old", YOUNG: "all"}


@needs_node
def test_every_lever_is_users_times_opens_times_per_open(report, world):
    """Every app, every lever: money = N × K × R × (1 + e); K = 'data se' (drift-away days × sessions a day, rounded) or
    1 … 30; users a day = N × (days, or K ÷ sessions a day within 1 … 30) ÷ 30."""
    apps = world["body"]["apps"]
    n = 0
    for via in VIAS:
        for m in MODES:
            for op in OPS:
                for ec in ECS:
                    g = report["calc"]["grid"][G(via, m, op, ec)]
                    for e in apps:
                        want, got = _calc(e, report["numbers"]["apps"][e["k"]], apps, via, m, op, ec), g[e["k"]]
                        assert got["ok"] is True and got["K"] == want["K"] and got["Kd"] == want["Kd"] == e["kf"]["K"]
                        assert (got["K10"], got["K90"]) == (e["kf"]["K10"], e["kf"]["K90"])
                        for k in ("w", "base", "R", "usd", "users", "be"):
                            assert _close(got[k], want[k], 1e-9), (e["n"], via, m, op, ec, k)
                        n += 1
    assert n == 3 * 4 * 7 * 4 * 4
    g = report["calc"]["grid"]
    for e in apps:                                                                 # the levers move it the obvious way
        k = e["k"]
        for via in VIAS:
            assert _close(g[G(via, "10", "5", "0")][k]["usd"] * 2, g[G(via, "10", "10", "0")][k]["usd"], 1e-9)
            assert _close(g[G(via, "10", "5", "10")][k]["usd"], g[G(via, "10", "5", "0")][k]["usd"] * 1.1, 1e-9)
            assert _close(g[G(via, "20", "5", "0")][k]["usd"], g[G(via, "10", "5", "0")][k]["usd"] * 2, 1e-9)


@needs_node
def test_all_apps_is_the_sum_of_each_apps_own(report, world):
    """All apps = Σ every app's own N × K × R × (1 + e); the K, R, ads and eCPM it shows are the averages that multiply
    back (K and 'data se' by woken users, R / ads / eCPM by woken opens)."""
    for key, t in report["calc"]["all"].items():
        g = report["calc"]["grid"][key]
        xs = list(g.values())
        w = sum(x["w"] for x in xs)
        wK = sum(x["w"] * x["K"] for x in xs)
        assert _close(t["usd"], sum(x["usd"] for x in xs), 1e-9) and _close(t["w"], w, 1e-9)
        assert _close(t["users"], sum(x["users"] for x in xs), 1e-9) and t["skip"] == 0
        assert _close(t["K"], wK / w, 1e-9) and _close(t["Kd"], sum(x["w"] * x["Kd"] for x in xs) / w, 1e-9)
        assert _close(t["R"], sum(x["w"] * x["K"] * x["R"] for x in xs) / wK, 1e-9)
        assert _close(t["w"] * t["K"] * t["R"] * (1 + int(key.split("|")[3]) / 100), t["usd"], 1e-9)   # multiplies back
        assert _close(t["A"] * t["E"] / 1000, t["R"], 1e-9)
        assert (t["be"] is None) == (t["w"] == 0) and (t["be"] is None or _close(t["be"], t["usd"] / t["w"], 1e-9))   # break-even
        assert _close(t["base"], sum(x["base"] for x in xs), 1e-9)


_NUM = r"[\d,]+(?:\.\d+)?"


def _v(s):
    return float(s.replace(",", ""))


def _mok(shown, v):
    """A number the page's M printed (whole from 10, 1 decimal from 1, 2 significant digits below) is v."""
    a = abs(v)
    if a >= 9.5:
        return abs(shown - v) <= 0.5 + 1e-9
    if a >= 0.95:
        return abs(shown - v) <= 0.05 + 1e-9
    return abs(shown - v) <= 0.051 * a + 1e-12


def _card(report, k, via, m, op, ec, cur):
    return report["calc"]["cards"]["|".join((k, via, m, op, ec, cur))]


CARDS = (("push", "10", "data", "0", "USD"), ("ads", "20", "5", "10", "USD"), ("both", "age", "30", "-10", "INR"),
         ("push", "5", "data", "20", "INR"), ("ads", "age", "data", "0", "INR"), ("both", "10", "2", "20", "USD"))


@needs_node
def test_the_card_one_open_levers_result_table_and_ecpm_box(report, world):
    """The card, as it renders (every app + All apps, $ and ₹): the number first, every line one that can be redone by
    hand — "~A ads × eCPM E ÷ 1000 = R har baar", "N users × K baar × R × (1+e) = ≈ X / mahina", the opens → money table
    (the chosen row lit), the eCPM box (today's users + the woken ones); the old tiles and chain gone, the ₹0 note kept,
    the asleep-for table behind "Kyun? ▸"."""
    fx = world["dash"]["usd_inr"]
    apps = world["body"]["apps"]
    for k in [e["k"] for e in apps] + ["all"]:
        e = next((x for x in apps if x["k"] == k), None)
        for via, m, op, ec, cur in CARDS:
            h = _card(report, k, via, m, op, ec, cur)
            sym, f = ("$", 1.0) if cur == "USD" else ("₹", fx)
            t = report["calc"]["all" if k == "all" else "grid"][G(via, m, op, ec)]
            c = t if k == "all" else t[k]
            assert "Paise ka calculator" in h and "Sleeping users aaj <b>%s0</b> dete hain" % sym in h
            for gone in ("au-tiles", "Per daily active user", "Old user, per day", "Money from waking", "au-chain", "Money estimate"):
                assert gone not in h
            # every coloured box carries its label
            for box, lab in (("au-po", "1 baar app kholne pe kamai"), ("au-calc", "Extra money / month"), ("au-ecb", "eCPM ")):
                assert re.search(r'<div class="%s"><div class="au-l">%s' % (box, re.escape(lab)), h), (box, lab)
            # 1 · one open
            po = re.search(r'<div class="au-eq">~(%s) ads × eCPM %s(%s) ÷ 1000 = <b>%s(%s)</b> har baar</div>' % (_NUM, re.escape(sym), _NUM, re.escape(sym), _NUM), h)
            A, E, R = _v(po.group(1)), _v(po.group(2)), _v(po.group(3))
            assert abs(A - c["A"]) <= 0.006 + 0.051 * c["A"] and _close(E, c["E"] * f, 0.006) and _close(R, c["R"] * f, 0.051)
            assert _close(A * E / 1000, R, 0.08)                                                   # redo by hand
            # 2 · the levers: the chosen chip of each lit
            for at, v in (("via", via), ("mode", m), ("opens", op), ("ecpm", ec)):
                assert h.count('class="au-chip on" data-au-%s=' % at) == 1 and 'class="au-chip on" data-au-%s="%s"' % (at, v) in h
            assert 'data-au-opens="data">Data se (~' in h
            # the "data se" line: where K comes from, its range
            lvn = re.search(r'<div class="au-lvn">(.*?)</div>', h).group(1)
            if k == "all":
                assert lvn.startswith("Data se: har app ka apna curve — avg ~") and ", range " in lvn
            else:
                kf = e["kf"]
                src = "pichhle installs ka curve" if kf["src"] == "own" else "sab apps ke pichhle installs ka curve — is app ke installs kam"
                assert lvn == "Data se: ~%d baar (%s, range %d–%d)" % (kf["K"], src, kf["K10"], kf["K90"]), lvn
                kb0 = h[h.index('<details class="au-kyun" data-kyun="money"'):]
                assert "curve fit kiya (ML" in kb0 and ("is app ke apne pichhle installs (12 hafte, %s)" % _n(kf["n"]) in kb0) == (kf["src"] == "own")
            # 3 · the result, one line
            rs = re.search(r'<div class="au-eq"><b>(%s)</b> users × <b>(~?)(%s)</b> baar × <b>%s(%s)</b>( \(avg\))?(?: × <b>(%s)</b>)? = <b>≈ %s(%s) / mahina</b></div>'
                           % (_NUM, _NUM, re.escape(sym), _NUM, _NUM, re.escape(sym), _NUM), h)
            Nn, til, K, Rr, avg, fac, X = _v(rs.group(1)), rs.group(2), _v(rs.group(3)), _v(rs.group(4)), rs.group(5), rs.group(6), _v(rs.group(7))
            assert Nn == _jr(c["w"]) and _close(Rr, R, 1e-9) and (avg is not None) == (k == "all")
            assert (til == "~") == (k == "all" and op == "data") and (K == c["K"] if k != "all" else abs(K - c["K"]) <= 0.05)
            assert (fac is None) == (ec == "0") and (fac is None or _close(_v(fac), 1 + int(ec) / 100, 1e-9))
            assert _mok(X, c["usd"] * f) and '<div class="au-n">≈ %s' % sym in h
            assert X == 0 if Nn == 0 else _close(Nn * K * Rr * (_v(fac) if fac else 1), X, 0.06 + 0.5 / Nn + 0.05 / K)   # redo by hand (N whole; 📢 a young app: nobody)
            assert "+%s users/day (mahine ka avg) · pehle din +%s" % (_n(c["users"]), _n(c["w"])) in h
            # the woken users: the sleepers this "Kahan se" counts, × the share (or by age)
            vn = {"push": "📲 1–3 mahine wale", "ads": "📢 3+ mahine wale", "both": "Sab sleeping (📲 + 📢)"}[via]
            wl = re.search(r'<div class="au-w au-wn">(.*?)</div>', h).group(1)
            assert wl == "%s: <b>%s</b> sleeping%s = <b>%s</b> users" % (
                vn, _nj(c["base"]), " · by age (jitna purana, utna kam %)" if m == "age" else " × %s%%" % m, _nj(c["w"])), wl
            # 📢 Ads / Dono: an ad's break-even = one woken user's month (K × R × (1 + e)) = money ÷ woken users
            bm = re.search(r'<div class="au-be">📢 Ad ka kharcha ek wapas aaye user pe <b>~%s(%s)</b> se kam hona chahiye, warna ghata\.'
                           % (re.escape(sym), _NUM), h)
            if via == "push":
                assert bm is None and 'class="au-be"' not in h
            else:
                ra = report["calc"]["all" if k == "all" else "grid"][G("ads", m, op, ec)]
                ra = ra if k == "all" else ra[k]
                assert _close(_v(bm.group(1)), ra["be"] * f, 0.051)
                assert _close(ra["be"], ra["K"] * ra["R"] * (1 + int(ec) / 100), 1e-9)
                assert ra["w"] == 0 or _close(ra["be"], ra["usd"] / ra["w"], 1e-9)
                bl = re.search(r'<div class="au-be">.*?<div class="au-w">(.*?)</div></div>', h, re.S).group(1)
                assert bl.startswith("%s%s = " % (sym, bm.group(1))) and "ek jaage user ki 1 mahine ki kamai" in bl
            # 4 · opens → money: 1 / 2 / 5 / 10 / 20 / 30 + the "data se" row in its place, the chosen one lit
            tb = h[h.index("Kitni baar khole → %s/mahina" % sym):]
            rows = re.findall(r'<tr class="(au-on)?" data-au-opens="(\w+)"><td>(.*?)</td><td class="au-r"><b>%s(%s)</b></td></tr>' % (re.escape(sym), _NUM), tb)
            assert [x[1] for x in rows if x[1] != "data"] == ["1", "2", "5", "10", "20", "30"] and len(rows) == 7
            assert [x[1] for x in rows if x[0]] == [op]
            if k == "all":                                  # every app its own K: "data se" leads, its avg K named
                assert rows[0][1] == "data" and "har app ka apna · avg ~" in rows[0][2] and "row 1 … 30 ke beech" in tb
            else:                                           # one app: in its place among 1 … 30
                Ks = [c["Kd"] if x[1] == "data" else int(x[1]) for x in rows]
                assert Ks == sorted(Ks) and "~%d baar <small>data se</small>" % c["Kd"] in tb
            for on, o, _lab, v in rows:
                cc = report["calc"]["all" if k == "all" else "grid"][G(via, m, o, ec)]
                cc = cc if k == "all" else cc[k]
                assert _mok(_v(v), cc["usd"] * f)
            # 5 · the eCPM box: +10% when the lever is 0, else the lever
            eb = 0.10 if ec == "0" else int(ec) / 100
            rev28 = sum(x["rev28"] for x in apps) if k == "all" else e["rev28"]
            x0 = report["calc"]["all" if k == "all" else "grid"][G(via, m, op, "0")]
            x0 = (x0 if k == "all" else x0[k])["usd"]
            box = h[h.index('class="au-ecb"'):]
            assert ("eCPM %s ka asar" % ("+%d%%" % round(eb * 100) if eb > 0 else "−%d%%" % round(-eb * 100))) in box
            vals = [(_v(x[1]), x[0]) for x in re.findall(r"<b>([+−])%s(%s) / month</b>" % (re.escape(sym), _NUM), box)]
            vals = [(-v if sg == "−" else v) for v, sg in [(a_, b_) for a_, b_ in vals]]
            want = [rev28 * 30 / 28 * eb * f, x0 * eb * f, (rev28 * 30 / 28 + x0) * eb * f]
            assert len(vals) == 3 and all(_mok(a_, b_) for a_, b_ in zip(vals, want))
            # Kyun: the basis, "data se", the asleep-for table — all behind the fold
            kb = h[h.index('<details class="au-kyun" data-kyun="money"'):]
            assert "<th>Asleep for</th>" in kb and "<th>Asleep for</th>" not in h[:h.index('<details class="au-kyun"')]
            assert "1 open = 1 session" in kb and "Data se" in kb
            if k != "all":
                assert ("Purane (30+ din) user ki ek din ki kamai" in kb) == (_po(e)["b"] == "old")
                assert ("Naya app — purane users ka apna hisaab nahi" in kb) == (_po(e)["b"] == "all")


@needs_node
def test_per_open_money_keeps_its_decimals(report, world):
    """Per-open money: 2 decimals under 10, three significant digits below 0.1 (never "0.00"), whole numbers from 10."""
    fx = world["dash"]["usd_inr"]
    assert report["calc"]["mo"]["USD"] == ["$12", "$1.23", "$0.43", "$0.0123", "$0.00517", "$0.000204", "$0"]
    want = []
    for v in (12.345, 1.2345, 0.4321, 0.0123, 0.00517, 0.000204):
        x = v * fx
        want.append("₹" + (_n(x) if x >= 10 else "%.2f" % x if x >= 0.1 else repr(float("%.3g" % x))))
    assert report["calc"]["mo"]["INR"] == want + ["₹0"]


@needs_node
def test_the_all_apps_table_follows_the_levers_in_a_fixed_order(report, world):
    """The money-by-app table: each app's money at the calculator's levers, the rows ordered by the 10% · data se · eCPM 0
    scenario whatever the levers say (stable — no row jumps on a chip tap)."""
    t = report["calc"]["table"]
    base = t[G("push", "10", "data", "0")]["order"]
    fixed = sorted(world["body"]["apps"], key=lambda e: (-report["calc"]["grid"][G("push", "10", "data", "0")][e["k"]]["usd"], -e["sl"]))
    assert base == [e["k"] for e in fixed]
    for key, v in t.items():
        assert v["order"] == base
        g = report["calc"]["grid"][key]
        for k, cell in zip(v["order"], v["money"]):
            usd = g[k]["usd"]
            assert cell == "$" + (_n(usd) if usd >= 10 else ("%.1f" % usd if usd >= 1 else "0" if usd == 0 else repr(float("%.2g" % usd))))
    assert "(📲 Notification · 10% jaagein · data se · eCPM 0)" in t[G("push", "10", "data", "0")]["h2s"]
    assert "(Dono · By age jaagein · 1 baar · eCPM +20%)" in t[G("both", "age", "1", "20")]["h2s"]
    assert "(📢 Ads / Play · 5% jaagein · 30 baar · eCPM −10%)" in t[G("ads", "5", "30", "-10")]["h2s"]
    assert "order hamesha 📲 Notification · 10% · data se · eCPM 0 pe" in t[G("ads", "5", "30", "-10")]["h2s"]


@needs_node
def test_an_app_without_the_calculators_inputs_says_so(report, world):
    d = report["calc"]["noData"]
    assert d["po"] is None and d["w"] > 0 and _close(d["all"]["skip"], d["w"], 1e-9)
    g = report["calc"]["grid"][G("push", "10", "data", "0")]
    assert _close(d["all"]["usd"], sum(x["usd"] for k, x in g.items() if k != d["k"]), 1e-9)       # Σ of the others
    assert _close(d["all"]["w"], sum(x["w"] for k, x in g.items() if k != d["k"]), 1e-9)
    assert "Is app ka GA4 sessions / AdMob impressions data nahi" in d["card"] and "au-calc" not in d["card"]
    assert "Sleeping users aaj" in d["card"] and d["strip"] == "—"
    assert d["money"][d["order"].index(d["k"])] == "—"
    assert "%s users ke apps ka sessions / eCPM data nahi (paise me nahi gine)" % _n(d["w"]) in d["allCard"]


@needs_node
def test_without_a_fit_data_se_is_the_day_1_7_30_join(report, world):
    d = report["calc"]["noFit"]
    e = next(x for x in world["body"]["apps"] if x["k"] == d["k"])
    assert _close(d["wd"], _wake_days(e, world["body"]["apps"], fitted=False), 1e-9) and d["K10"] is None
    assert "Data se: ~%d baar (naye users ke 1 / 7 / 30 din se)" % d["Kd"] in d["card"] and "curve fit kiya" not in d["card"]
    big = world["body"]["apps"][0]["kf"]
    assert report["calc"]["noRange"] == "Data se: ~%d baar (pichhle installs ka curve, range nahi — kam hafton me kaafi installs)" % big["K"]


@needs_node
def test_the_chips_set_light_and_remember_the_levers(report):
    c = report["calc"]
    assert c["chips"]["S"] == ["20", "5", "20"] and c["chips"]["on"] == [True, True, True] and c["chips"]["row"]
    assert c["chips"]["via"] == "ads" and c["chips"]["viaOn"]                      # "Kahan se jagayein": one lit
    assert c["chips"]["viaChips"] == [["push", "📲 Notification (1–3 mahine)"], ["ads", "📢 Ads / Play (3+ mahine)"], ["both", "Dono"]]
    assert {k: c["chips"]["ls"][k] for k in ("via", "mode", "opens", "ecpm")} == {"via": "ads", "mode": "20", "opens": "5", "ecpm": "20"}
    assert c["boot"] == ["20", "5", "20", "ads"]                                  # a page load restores them
    assert c["bootBad"] == ["10", "data", "0", "push"]                            # an unknown saved value: the default
    assert c["dflt"]["S"] == "push" and c["dflt"]["w"] == c["dflt"]["wPush"]       # 📲 Notification by default
    assert c["rowTap"] == "10"                                                    # a row of the opens table is a lever


@needs_node
def test_a_lever_redraws_only_the_money_card_strip_and_table(report):
    """Owner, on his iPhone: a calculator chip tap mid-page threw the page to the top — every tap rebuilt the whole
    screen. A lever now redraws only what it feeds, in place; the rest of the screen (the month chart, open folds, the
    reader's place) is not touched — and what is redrawn is exactly what a full paint would draw."""
    r = report["levers_partial"]
    a = r["all"]
    assert a["screen"] == "SCREEN-KEPT"                                           # the screen itself never rebuilt
    assert a["S"] == ["20", "5", "10", "both"] and {k: a["ls"][k] for k in ("via", "mode", "opens", "ecpm")} == {"via": "both", "mode": "20", "opens": "5", "ecpm": "10"}
    assert 'class="au-chip on" data-au-via="both"' in a["money"] and 'class="au-be"' in a["money"]   # the "Kahan se" chip: the same in-place redraw
    assert a["money"] and a["money"] == a["want"]["money"]                        # = the full paint's card at those levers
    assert 'class="au-chip on" data-au-opens="5"' in a["money"] and 'class="au-chip on" data-au-mode="20"' in a["money"]
    assert 'data-kyun="money" open' in a["money"]                                 # an open "Kyun? ▸" stays open
    assert a["table"] and a["table"] == a["want"]["table"] and a["strip"] == a["want"]["strip"]
    p = r["app"]
    assert p["screen"] == "SCREEN-KEPT" and p["money"] == p["want"] and 'class="au-chip on" data-au-ecpm="10"' in p["money"]
    assert p["table"] == "TABLE-UNTOUCHED"                                        # one app: no all-apps table
    assert r["noCard"] and r["appMoved"]                                          # anything unexpected → the full paint


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
    top = max(world["body"]["apps"], key=lambda e: report["numbers"]["apps"][e["k"]]["c10"]["usd"])
    usd = report["numbers"]["apps"][top["k"]]["c10"]["usd"]
    cell = lambda v, s: '<td class="au-r au-m"><span class="au-dk">%s%s</span>' % (s, _n(v) if v >= 10 else ("%.1f" % v))   # the desktop form
    assert cell(usd, "$") in report["money"]["USD"]["html"] and cell(usd * fx, "₹") in report["money"]["INR"]["html"]
    assert "₹ / month" in report["money"]["INR"]["html"] and "$ / month" in report["money"]["USD"]["html"]


# ── who a notification can still reach (Android 12+ app hibernation at ~3 months) ──────────────────────────────────────
def _pp(a, b):                                                                           # the page's P (a share as text)
    if not b or a is None:
        return ""
    p = 100 * a / b
    if a != 0 and abs(p) < 0.05:
        return "<0.1%"
    v = _jr(p * 10) / 10 if abs(p) < 10 else _jr(p)
    return ("%d" % v if v == int(v) else "%s" % v) + "%"


def _sec(h, sid):
    i = h.index('id="%s"' % sid)
    return h[h.rindex("<section", 0, i):h.index("</section>", i)]


def _groups(bk):
    """The bars' sums: 📲 push = Σ 1 ≤ f < 3 (dz = its 2–3 months bar), 📢 ads = Σ f ≥ 3."""
    push = sum(b["v"] for b in bk if 1 <= b["f"] < 3 and b["v"])
    dz = sum(b["v"] for b in bk if b["f"] == 2 and b["v"])
    ads = sum(b["v"] for b in bk if b["f"] >= 3 and b["v"])
    return push, dz, ads


def _pages(report, world):
    """(key, page html, bars, installed) for every app and All apps."""
    out = [(e["k"], report["apps"][e["k"]], report["numbers"]["apps"][e["k"]]["bk"], e["au"]["inst"]) for e in world["body"]["apps"]]
    return out + [("all", report["render"]["html"], report["numbers"]["all"]["bk"], report["numbers"]["all"]["inst"])]


PUSH_HEAD = '📲 Notification se pahunch sakte<small>(1–3 mahine)</small>'
ADS_HEAD = "📢 Sirf Ads / Play se<small>(3+ mahine — Android 12+ app ko 'so' deta hai, notification nahi pahunchti)</small>"


@needs_node
def test_the_sleeping_bars_split_at_three_months_with_subtotals(report, world):
    """The Sleeping card's bars in two labelled groups — 📲 1–3 months (a notification still reaches them) and 📢 3+ months
    (Android 12+ has put the app to sleep: only ads / Play) — each with its subtotal (the number first, its % of installed
    beside it) = the sum of its own bars; the two together = every 1+ month sleeper; the rule cited under "Kyun? ▸"."""
    young = world["by"][YOUNG]["k"]
    for k, h, bk, inst in _pages(report, world):
        d = _sec(h, "au-s-dead")
        push, dz, ads = _groups(bk)
        heads = re.findall(r'<div class="au-gh" style="--gc:var\(--au-(\w+)\)"><div class="au-gt">(.*?)</div><div class="au-gv">([\d,]+)<small>([^<]*)</small></div></div>', d)
        assert [(x[0], x[1]) for x in heads] == [("sleep", PUSH_HEAD), ("ads", ADS_HEAD)], k
        assert [x[2] for x in heads] == [_nj(push), _nj(ads)] and [x[3] for x in heads] == [_pp(push, inst), _pp(ads, inst)], k
        assert push + ads == sum(b["v"] for b in bk if b["f"] >= 1 and b["v"])            # together: every 1+ month sleeper
        # every bar sits under its own group: 1–2 / 2–3 months under 📲, 3+ months under 📢
        i_ads = d.index(ADS_HEAD)
        labs = re.findall(r'<div class="au-hl">([^<]+?)(?: <span class="au-dzb">⚠️ Danger</span>)?</div><div class="au-ht" data-at', d)
        assert len(labs) >= (1 if k == young else 3)
        for lab in re.findall(r'<div class="au-hl">([^<]+?)(?: <span class="au-dzb">⚠️ Danger</span>)?</div><div class="au-ht" data-at', d):
            f0 = int(re.match(r"(\d+)", lab).group(1)) * (12 if "year" in lab else 1)
            pos = d.index('<div class="au-hl">' + lab)
            assert (pos > i_ads) == (f0 >= 3), (k, lab)
        assert "<b>3 mahine kyun?</b> Android 12+ ~3 mahine na khule app ko \"so\" (hibernate) deta hai" in d[d.index('data-kyun="dead"'):]
        # ⚠️ the danger zone: the 2–3 months bar, in the warning colour, its count with its %
        if k == young:                                                   # 1 month of data: no 2–3 months bar, nobody 3+
            assert 'class="au-dz"' not in d and "— abhi koi nahi · data 1 mahine tak" in d and heads[1][2] == "0"
            continue
        assert d.count('<span class="au-dzb">⚠️ Danger</span>') == 1 and '<div class="au-hl">2–3 months <span class="au-dzb">⚠️ Danger</span></div>' in d
        assert "background:var(--au-dz)" in d and d.count("background:var(--au-dz)") == 1
        assert ('<div class="au-dz">⚠️ <b>Danger zone (61–90 din)</b>: <b class="au-dzn">%s</b> (%s) — abhi nahi jagaye to ~3 mahine pe '
                'Android app ko so dega, phir notification nahi pahunchegi.</div>' % (_nj(dz), _pp(dz, inst))) in d, k


@needs_node
def test_the_strips_sleeping_tile_says_who_push_can_reach(report, world):
    """Under "Sleeping 28+ days": 📲 push se (1–2 months) · ⚠️ danger zone (2–3 months) · 📢 sirf ads se (3+ months) — the
    Sleeping card's own bars, so 📢 = the "Dead 3+ months" tile beside it; All apps = Σ every app. The money tile: 10% of
    the 📲 1–3 month sleepers (the calculator's default), so named."""
    tot = [0, 0, 0]
    for k, h, bk, inst in _pages(report, world):
        st = h[h.index('<div class="au-strip" id="au-strip">'):h.index('<div class="au-grid">')]
        if k == "all":
            push, dz, ads = tot
            r = report["numbers"]["all"]["reach"]
        else:
            p, dz, ads = _groups(bk)
            push = p - dz
            tot = [tot[0] + push, tot[1] + dz, tot[2] + ads]
            r = report["numbers"]["apps"][k]["reach"]
        assert _close(r["push"], push, 1e-9) and _close(r["dz"], dz, 1e-9) and _close(r["ads"], ads, 1e-9)
        line = re.search(r'<div class="au-rch" title="[^"]*">(.*?)</div>', st).group(1)
        assert line == ('<span>📲 <b>%s</b> push se</span> · <span class="au-rdz">⚠️ <b>%s</b> danger zone</span> · <span>📢 <b>%s</b> sirf ads se</span>'
                        % (_cn(push), _cn(dz), _cn(ads))), (k, line)
        assert st.index('<div class="au-l">Sleeping 28+ days</div>') < st.index('class="au-rch"') < st.index("Dead 3+ months")
        users = report["numbers"]["all"]["w10"]["push"]["users"] if k == "all" else report["numbers"]["apps"][k]["c10"]["users"]
        assert "📲 notification se (1–3 mahine) · +%s users / day" % _cn(users) in st
    assert report["numbers"]["all"]["fix"] == {"via": "push", "mode": "10", "opens": "data", "ecpm": "0"}


@needs_node
def test_kahan_se_counts_only_the_sleepers_that_way_can_reach(report, world):
    """📲 Notification: only the 1–3 month sleepers; 📢 Ads / Play: only the 3+ month ones; Dono: all — so push + ads =
    both (users and money, every lever); on a GA4 app the 📲 base is exactly its 1–3 month bars. The asleep-for table
    behind "Kyun? ▸" dims the rows the choice leaves out."""
    for e in world["body"]["apps"]:
        r = report["numbers"]["apps"][e["k"]]
        b = r["base"]
        push, dz, ads = _groups(r["bk"])
        assert _close(b["push"] + b["ads"], b["both"], 1e-9) and b["both"] == r["deadTot"]
        assert _close(b["ads"], min(r["deadTot"], ads), 1e-9) and r["split"] == {"push": push, "dz": dz, "ads": ads}
        if e["au"]["src"] == "ga4":
            assert _close(b["push"], push, 1e-9)
        for mode in ("10", "age"):
            w = r["w10" if mode == "10" else "wage"]
            assert _close(w["push"]["w"] + w["ads"]["w"], w["both"]["w"], 1e-9)
        assert _close(r["wage"]["ads"]["w"], sum(x["v"] * CHANCE(x["f"]) for x in r["bk"] if x["f"] >= 3 and x["v"]), 1e-9)
    g = report["calc"]["grid"]
    for m in MODES:
        for op in ("data", "5"):
            for ec in ("0", "10"):
                for k in g[G("both", m, op, ec)]:
                    x = [g[G(v, m, op, ec)][k] for v in VIAS]
                    assert _close(x[0]["usd"] + x[1]["usd"], x[2]["usd"], 1e-9) and _close(x[0]["w"] + x[1]["w"], x[2]["w"], 1e-9)
                a = [report["calc"]["all"][G(v, m, op, ec)] for v in VIAS]
                assert _close(a[0]["usd"] + a[1]["usd"], a[2]["usd"], 1e-9)
    # the asleep-for table: the rows outside the choice dimmed, the total = the rows it counts
    for via, m, op, ec, cur in CARDS:
        kb = _card(report, "all", via, m, op, ec, cur)
        kb = kb[kb.index("<th>Asleep for</th>"):]
        rows = re.findall(r'<tr( class="au-off")?><td>([^<]+)</td><td class="au-r">([\d,]+)</td><td class="au-r">([^<]+)</td><td class="au-r"><b>([^<]+)</b></td></tr>', kb)
        assert [x[1] for x in rows] == ["1–2 months", "2–3 months", "3–4 months", "4–7 months", "7+ months"]
        on = [bool(x[0]) is False for x in rows]
        assert on == [_in_via(f, via) for f in (1, 2, 3, 4, 7)]
        assert all(x[3] == "—" and x[4] == "—" for x in rows if x[0])
        tot = re.search(r'<tr class="au-tot"><td>Total[^<]*</td><td class="au-r">([\d,]+)</td>', kb).group(1)
        assert abs(_v(tot) - sum(_v(x[2]) for x in rows if not x[0])) <= 3                 # whole numbers each


@needs_node
def test_how_to_wake_them_and_the_module_panels_note(report, world):
    """"How to wake them": 📲 push for 1–3 months · 📢 3+ months = Google Ads app engagement (the DATA break-even: data se
    K × R, fixed whatever the levers) + Play update notes / promotional content · 🛡️ prevention ("Pause app activity if
    unused", the official intent, sparingly) · 🪜 the new users' ladder. The 🔒 "Last opened" panel: FCM misses hibernated
    phones."""
    fx = world["dash"]["usd_inr"]
    for k, n in [(e["k"], e["n"]) for e in world["body"]["apps"]] + [("all", "")]:
        for via, m, op, ec, cur in CARDS:
            h = report["calc"]["how"]["|".join((k, via, m, op, ec, cur))]
            sym, f = ("$", 1.0) if cur == "USD" else ("₹", fx)
            lis = re.findall(r"<li>(.*?)</li>", h, re.S)
            assert len(lis) == 4 and [re.match(r"<b>(.*?)</b>", x).group(1) for x in lis] == [
                "📲 1–3 mahine — notification (FCM):", "📢 3+ mahine — sirf phone ke bahar se:", "🛡️ Rokna:", "🪜 Naye users ke liye ladder:"]
            assert "⚠️ 2–3 mahine wale pehle" in lis[0] and "We miss you" in lis[0]
            assert "Google Ads app engagement campaign" in lis[1] and "Play Store pe update notes + promotional content" in lis[1]
            assert '"Pause app activity if unused"' in lis[2] and "official intent" in lis[2] and "Kam use karo" in lis[2]
            assert "3, 7, 14, 30, 45, 60 din" in lis[3] and "~75 din" in lis[3] and "holdout" in lis[3] and "Last app engagement" in lis[3]
            c = report["calc"]["howBe"][k]
            bm = re.search(r"ek wapas aaye user pe kharcha <b>~%s(%s)</b> se kam ho tabhi faayda \((avg, )?data se ~(%s) baar × %s(%s)\)"
                           % (re.escape(sym), _NUM, _NUM, re.escape(sym), _NUM), lis[1])
            assert bm and _close(_v(bm.group(1)), c["be"] * f, 0.051) and (bm.group(2) is not None) == (k == "all")
            assert _close(c["be"], c["K"] * c["R"], 1e-9)                                    # data se K × R (eCPM 0)
            assert abs(_v(bm.group(3)) - c["K"]) <= (0.05 if k == "all" else 0) and _close(_v(bm.group(4)), c["R"] * f, 0.051)
    m = _sec(report["render"]["html"], "au-s-module")
    assert ('⚠️ FCM wali "abhi bhi installed" ginti me so gaye (hibernated, Android 12+) phones nahi aayenge — isliye 3+ mahine '
            'wale sleeping kam gine jaayenge.') in m and m.index("🔒 Last opened") < m.index("so gaye (hibernated")


@needs_node
def test_a_bars_tip_names_the_way_that_reaches_it(report):
    t = report["tips"]["reach"]
    assert "⚠️ danger zone — abhi notification" in t["push"]["dz"] and "📲 notification" in t["push"]["one"] and "📢 sirf ads / Play" in t["push"]["ads"]
    off = "— (is choice me nahi)"
    assert off not in t["push"]["dz"] and off not in t["push"]["one"] and off in t["push"]["ads"]
    assert off in t["ads"]["dz"] and off in t["ads"]["one"] and off not in t["ads"]["ads"]
    assert all(off not in x for x in t["both"].values())


# ── the all-apps table on a phone ─────────────────────────────────────────────────────────────────────────────────────
def _jr(v):                                                                              # Math.round (half up)
    return int(math.floor(v + 0.5))


def _nj(v):                                                                              # the page's N: Math.round, grouped
    return "{:,}".format(_jr(v))


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
            e, usd = by_k[row["k"]], report["numbers"]["apps"][row["k"]]["c10"]["usd"]
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
    assert r["S"] == {"app": r["want"], "via": "ads", "mode": "age", "opens": "5", "ecpm": "10", "day": "2026-02-01", "open": ["money", "dead"]}
    assert r["st"] == ["app"] and r["hist"] == 2 and r["scrolls"] == []                 # no new Back step, no jump
    assert r["crumb"] and r["fold"] and r["ageOn"] and r["leversOn"] and r["cur"] == "INR" and r["rupee"]   # App, ₹, levers kept
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
