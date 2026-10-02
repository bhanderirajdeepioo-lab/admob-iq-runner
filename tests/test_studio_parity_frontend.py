"""🧭 / 💸 The Active users and Install value Studios: what the older views had and the Studios now show too ("purane page me
tha aur new version me nahi"), rendered for real by tests/studio_parity_frontend.js (the dashboard script in a node vm) from
Studio files the REAL build code made of the synthetic sites (tests/active_studio_synth.py, tests/value_studio_synth.py; no
real data). Every brought-in number is checked against the OLD view's own helper on the same data:

  Active users
  * an app's "Users by app version" = the old actVerTable, row by row and cell by cell ("Show all versions" too);
  * ad rate = the engine tile's own number on its own window; "other networks add ~x% more" = the old actOther;
  * the engine's older findings (30-90 days, not alerts) in a "▸ Older changes (N)" fold — All apps (DATA.active.info) and the app
    page (its own file) — each with its 🕒 line;
  * All apps, day by day: "Apps with data" k of n, ⏸️ a big app's day missing, +1 / −1 apps joined / stopped, "vs same day
    last week" (same apps) = the old 📅 Daily helpers (actPfSeries / actPfMarks); the markers on the sparklines and the guard
    line under the KPIs; a return's ▲▼ follows the rate everywhere;
  * the old views' small fixes: "Revenue per user" said per user, the "Installs / day" tile a daily number, the pointers to
    the Uninstall tab's 📦 Update impact.
  Install value
  * week by week: 12 / 26 / All weeks — every week of the app's detail file = the old "Money back by install week" table;
  * a no-ads app's 30-day earning per install (= the old row's) where the Studio said "—": table, map, drawer, app page;
  * the app page's closed alerts in a "▸ Closed alerts (N)" fold with their 🕒 line; no "Other small countries (0)" row;
  * the words (English labels, Hinglish in Roman script only, no banned word, never "100 me" / "per 1,000"). Skipped where node
    is not installed."""

import gzip
import json
import math
import os
import re
import shutil
import subprocess

import pytest

from admob_iq import active_studio_build as asb
from admob_iq import build_static
from admob_iq import value_studio_build as vsb
from admob_iq.config import settings
from tests import active_studio_synth as ass
from tests import value_studio_synth as vss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
BANNED = re.compile(r"\bis hafte\b|\bthis week\b|\babhi ka\b|Provisional|kacch?a\b|kacche|Estimate|/1k|\bpts\b|\bpp\b|\bpoints?\b"
                    r"|cohort|ARPDAU|eCPM|mediation|Stay after|\bsettled\b|\blatest\b|\brecent\b|cumulative|\bLTV\b", re.I)
BANNED_CASE = re.compile(r"\bD\d{1,3}\b|\bMix\b|\bHALT\b|\bWIN\b|\bReturning\b")
PER = re.compile(r"\b100 me\b|\b1,000 me\b|\bhar 1,000\b|\bper 1,000\b|\bper 100\b")
DEVA = re.compile("[ऀ-ॿ]")


def _script(tmp):
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    path = os.path.join(tmp, "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    return path


def _dump(fx, **bodies):
    os.makedirs(fx, exist_ok=True)
    for name, body in bodies.items():
        with open(os.path.join(fx, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(body, f)


def _run(path, fx, mode):
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "studio_parity_frontend.js"), path, fx, mode],
                         check=True, capture_output=True, text=True, timeout=600)
    return json.loads(out.stdout)


def _gz(site, name):
    with gzip.open(os.path.join(site, name), "rt", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def act(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("parity_act"))
    site, cfg, dash = ass.make_site(root)
    assert build_static._active_studio_step(dash, os.path.join(root, "data"), site, dict(settings())) == ["/active_studio.json.gz", "/active_studio_old.json.gz"]
    files = {r["key"]: _gz(site, r["file"]) for r in dash["active"]["apps"]}
    fx = os.path.join(root, "fx")
    _dump(fx, dashboard=dash, active_studio=_gz(site, asb.FILE), active_files=files,
          active_portfolio=_gz(site, dash["active"]["portfolio"]["file"]))
    rep = _run(_script(root), fx, "active")
    assert rep["errors"] == [], rep["errors"]
    return rep, dash, files


@pytest.fixture(scope="module")
def val(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("parity_val"))
    site, cfg, dash = vss.make_site(root)
    assert build_static._value_studio_step(dash, os.path.join(root, "data"), site, dict(settings())) == ["/value_studio.json.gz"]
    files = {r["key"]: _gz(site, r["file"]) for r in dash["value"]["apps"] if r.get("file")}
    fx = os.path.join(root, "fx")
    _dump(fx, dashboard=dash, value_studio=_gz(site, vsb.FILE), value_files=files)
    rep = _run(_script(root), fx, "value")
    assert rep["errors"] == [], rep["errors"]
    return rep, dash, files


def J(rep, k):
    assert k in rep["out"], (k, rep["errors"])
    return json.loads(rep["out"][k])


def _num(s):
    m = re.search(r"-?[0-9][0-9,]*\.?[0-9]*", str(s).replace("−", "-"))
    return float(m.group(0).replace(",", "")) if m else None


# ── Active users ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_version_table_is_the_old_one(act):
    rep, _, files = act
    V = J(rep, "ver")
    assert any(len(x["st"]) >= 2 for x in V)                             # (the synthetic rollout: 2.0 → 2.1)
    for x in V:
        assert len(x["st"]) == len(x["old"]), x["nm"]
        if x["st"]:
            assert x["inPage"], x["nm"]
        for s, o in zip(x["st"], x["old"]):
            # Version · Out since (the Studio's date) · Users now · Sessions/user · Time/user · vs previous · Status
            assert s[0] == o[0].replace("<1%", "under 1%"), (s, o)
            assert s[2:5] == o[2:5], (s, o)                               # the old formatters, the same numbers
            ow = re.search(r"(Better|Worse|Normal \(not sure\)|Normal)$", o[5])
            assert s[5] == (re.sub(r"\s*[🟢🔴⚪]\s*$", "", o[5][:ow.start()]).strip() if ow else o[5]), (s, o)
            assert (s[6].startswith(ow.group(1).replace(" (not sure)", "")) if ow else s[6] == "—"), (s, o)
            if ow and "not sure" in ow.group(1):
                assert "not sure" in s[6]


def test_show_all_versions(act):
    v = J(act[0], "verAll")
    assert v["btn"] == v["all"] == v["oldAll"] and v["few"] == v["all"] - 1


def test_ad_rate_is_the_engine_tiles_number(act):
    for x in J(act[0], "adrate"):
        if x["tv"] is None or x["v"] is None:
            continue
        assert abs(x["v"] / x["tv"] - 1) <= 2e-3, x                       # (the file's per-day rounding only)
        if x["tb"] and x["b"]:
            assert abs(x["b"] / x["tb"] - 1) <= 2e-3, x
    p = J(act[0], "adratePage")
    assert p["v"] and ("Ad rate " + p["v"]) in p["txt"]                  # the old view's own format (2 decimals)
    assert "Ad rate = AdMob kamai ÷ dikhaye gaye ads" in p["tip"] and "Engine · last 7 final days" in p["tip"]


def test_other_networks_line(act):
    o = J(act[0], "other")
    assert not o["off"]                                                  # unknown share: nothing said
    assert o["x"] == 43 and "AdMob Network only · other networks add ~43% more" in o["on"]   # 0.3 / 0.7 (the old actOther)
    assert "~43%" in o["tip"] and "30%" in o["tip"]


def test_older_findings_fold(act):
    o = J(act[0], "older")
    chg, page, tbl = o["chg"], o["page"], o["tbl"]
    assert re.search(r"Older changes \(2\)</span><span class=\"as-pv\">2 apps</span>", chg)       # the two DATA.active.info rows
    assert "Engine ki purani findings" in chg
    assert "📌 Open over 30 days" not in chg or "🗄 Older than 30 days" not in chg
    cards = re.findall(r'<div class="as-ac as-s-info as-oldc".*?</div></div>', chg, re.S)
    assert len(cards) == 2
    for c in cards:
        t = re.sub(r"<[^>]+>", " ", c)
        assert "🕒 Alert time: — (purani finding" in t and "Change started:" in t and "Data: Daily avg" in t
        assert "📦 after v9.9" in t and "−42%" in t
    assert re.search(r"Older changes \(3\)", page)                                    # the app's own file: 3 rows
    assert "<th class=\"as-l\">App</th>" in tbl                                         # the table view: App first


def test_honesty_guards_equal_the_old_daily_helpers(act):
    h = J(act[0], "hon")
    assert h["head"][:2] == ["Day", "Apps with data"] and "Back after 7 days" in h["head"] and "Sessions per user" in h["head"] \
        and h["head"][-1] == "vs same day last week"
    assert len(h["cells"]) == len(h["exp"])
    joined = 0
    for c, e in zip(h["cells"], h["exp"]):
        assert c[1].startswith("%d of %d" % (e["k"], e["n"])), (c, e)
        assert c[-1] == e["wow"], (c, e)
        assert ("⏸️" in c[1]) == e["inc"]
        for m in e["marks"]:
            for s in m:
                assert ("+1" if s > 0 else "−1") in c[1], (c, e)
                joined += s > 0
    assert joined >= 1                                                   # (the synthetic young app's first day is in the range)
    assert "+1 app joined" in h["hon"] and "Demo Young" in h["hon"]
    assert any(e["t"] == "+1" for e in h["ev"]) and "as-evl" in h["kpis"] and "as-evl" in h["kpis2"]
    # ⏸️ a big app's missing day: marked in the table, the guard line and the sparkline
    hit = [r for r in h["missLed"] if "⏸️" in r[1]]
    assert hit, h["missDay"]
    assert "Big app data missing" in h["missHon"] and any(e.get("miss") for e in h["missEv"])
    assert "of active users missing" in h["missTip"]


def test_without_the_daily_file_nothing_is_guessed(act):
    n = J(act[0], "honNone")
    assert n["hon"] == "" and "⏳ ginti ka data load ho raha hai" in n["led"]


def test_return_arrow_follows_the_rate(act):
    r = J(act[0], "retdl")
    for t in (r["k"], r["k2"]):
        for m in re.finditer(r"([+−±][\d,]+)/day · rate ([▲▼■]) ([\d.]+)%, was ([\d.]+)%", t):
            now, was = float(m.group(3)), float(m.group(4))
            assert m.group(2) == ("■" if abs(now - was) < .05 else ("▲" if now > was else "▼")), m.group(0)
    assert "/day · rate " in r["k"]


def test_old_views_small_fixes(act):
    o = J(act[0], "oldfix")
    # "Revenue per user" — the stored per-1,000 value said per user (never ~1,000× too high)
    v = (o["arpdau"] or {}).get("v")
    if v is not None:
        m = re.search(r'data-m="arpdau".*?<div class="v">([^<]*)', o["sum"], re.S)
        assert m and _num(m.group(1)) == pytest.approx(v / 1000, rel=0.02, abs=0.006), m.group(1)
    assert o["arpTxt"]
    for good, bad in zip(o["arpTxt"], o["perK"]):
        assert good in o["table"] and (good == bad or bad not in o["table"]), (good, bad)
    # the old All-apps tile "Installs / day": a daily number, the total beside it
    t = re.search(r'data-m="new"><div class="l">Installs / day</div><div class="v">([^<]*)</div>.*?total ([^ <]+)', o["tiles"], re.S)
    assert t and _num(t.group(1)) < _num(t.group(2))
    # the pointers: the 📦 Update impact card is on the Uninstall tab
    assert "Uninstall → app page → 📦 Update impact" in o["hint"] and "kisi bhi date se tulna" not in o["hint"]
    assert "in Update impact above" not in o["tri"]


def test_active_words(act):
    for t in J(act[0], "words"):
        assert not BANNED.search(t), BANNED.search(t).group(0) + " | " + t[:160]
        assert not BANNED_CASE.search(t), BANNED_CASE.search(t).group(0) + " | " + t[:160]
        assert not PER.search(t) and not DEVA.search(t) and "NaN" not in t and "undefined" not in t, t[:160]


# ── Install value ────────────────────────────────────────────────────────────────────────────────────────────────

def _p100(x):
    a = abs(x)
    s = str(int(math.floor(a + 0.5))) if a >= 10 else (("%.1f" % a).rstrip("0").rstrip(".") if a >= 1 else ("0" if a == 0 else ("%.2g" % a)))
    return ("−" if x < 0 else "") + s


def test_week_history_is_the_old_table(val):
    W = J(val[0], "weeks")
    checked = 0
    for x in W:
        if x.get("nodet"):
            continue
        assert x["src"] == "det"
        old = {r["w"]: r["c"] for r in x["old"]}
        assert sorted(old) == sorted(s["w"] for s in x["st"]), x["nm"]   # every week, none left out
        for s in x["st"]:
            o = old[s["w"]]
            assert _num(o[1]) == s["n"], (x["nm"], s["w"])
            for k, j in enumerate((1, 3, 5, 7, 9)):
                oc = o[4 + k] if x["paid"] else o[2 + k]
                if oc.startswith("in ") or oc in ("—", "No ads", "Little spend"):
                    continue
                if "/install" in oc or not x["paid"]:
                    assert oc.replace("/install", "").replace("≈", "") == s["vt"][j].replace("≈", ""), (x["nm"], s["w"], j, oc, s["vt"][j])
                else:
                    cpi = s["sp"] / s["n"] if s["sp"] and s["n"] else None
                    b = s["p100"][j] if s["p100"] and s["p100"][j] is not None else (s["v"][j] / cpi * 100)
                    assert _num(oc) == _num(_p100(b)), (x["nm"], s["w"], j, oc, b)
                checked += 1
            if x["paid"] and _num(o[9]) is not None:
                assert _num(o[9]) == _num(s["pay"]), (x["nm"], s["w"], o[9], s["pay"])
    assert checked > 50


def test_week_modes(val):
    m = J(val[0], "modes")
    assert m["12"] == min(12, m["n"]) and m["26"] == min(26, m["n"]) and m["all"] == m["n"] and m["rng"] == m["rngExp"]
    assert m["12p"] == "12 weeks" and m["allp"] == "All (%d)" % m["n"] and m["inPage"]


def test_no_ads_30_day_earning(val):
    r = J(val[0], "r30")
    assert r["r30"]["src"] == "eng" and r["eng"] == pytest.approx(r["old"]) and r["mp"] == r["oldTxt"]
    assert r["inrTxt"] == r["oldInr"]                                    # ₹ at today's rate, as the old views print it
    row = " ".join(r["tblRow"]["cells"])
    assert r["mp"] + " 30d · no ads" in row
    assert r["mapHas"] and "No ads in this range" in r["map"] and r["mp"] + " 30d · no ads" in r["map"]
    assert "Earning in 30 days" in r["drawer"] and r["mp"] in r["drawer"] and "30d · no ads" in r["drawer"]
    assert "Earning in 30 days" in r["page"] and "(engine)" in r["page"]
    assert "In 30 days" in r["tip"] and "paisa-wapas nahi" in r["tip"]


def test_closed_alerts_fold(val):
    c = J(val[0], "closed")
    assert c["n"] == 1
    p = c["page"]
    assert re.search(r"Closed alerts \(1\)", p)
    t = re.sub(r"<[^>]+>", " ", p[p.index("Closed alerts (1)"):])
    assert "🕒 Alert time:" in t and "Change started:" in t
    assert re.search(r"Opened\s+10 Aug\s+as\s+Worse", t) and re.search(r"Closed\s+1 Sep", t) and re.search(r"Open for\s+22 days", t)
    assert "Why closed:" in t


def test_no_small_countries_zero_row(val):
    s = J(val[0], "small")
    assert "Other small countries (0)" not in s["zero"] and "kisi country se match nahi hua" in s["zero"]
    assert "Other small countries (3)" in s["three"]


def test_tiny_money_never_an_exponent(val):
    assert J(val[0], "mp") == ["$0.00000087", "$0.0060", "$0.0042", "$0.042", "$1.50"]


def test_whats_new_chip_agrees_with_its_card(val):
    n = J(val[0], "news")
    for c in n["cards"]:
        m = re.search(r'vs-s-(behtar|bigda)".*vs-st-([a-z]+)', c)
        assert m.group(1) == m.group(2), c


def test_value_words(val):
    for t in J(val[0], "words"):
        assert not BANNED.search(t), BANNED.search(t).group(0) + " | " + t[:160]
        assert not BANNED_CASE.search(t), BANNED_CASE.search(t).group(0) + " | " + t[:160]
        assert not PER.search(t) and not DEVA.search(t) and "NaN" not in t and "undefined" not in t, t[:160]
