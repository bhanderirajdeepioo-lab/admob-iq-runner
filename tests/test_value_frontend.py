"""The 💸 Install value tab's frontend (frontend/index.html), rendered for real: tests/value_frontend.js runs the page's own
script in a node vm on the committed synthetic fixture (tests/fixtures/value_sample.json — dashboard["value"] and every
app's value_<key>.json.gz) and renders every Install value state: the All-apps page (every sort, every status chip
opened), each app's page in every week / sort / fold mode at phone and desktop width, the Alerts-screen section, $ and ₹,
and made-up states the fixture may not hold. Checked here, one test per owner must-have (spec §5.4, the F: ids): the tab's
title and place in the sidebar; five tiles; country rows ("X of 100", earning per install, verdict); few-installs badge
and the small / unknown / unassigned lines; "in N days" for a week that is not complete; ≈ for projections and short
GA4 days; the honest no-country-cost note; the Data check (GA4 ÷ AdMob, unassigned share); "Wait" for country weeks
that are not clean; the GA4-sample note; no red / green without an open alert; numbers never coloured; tiny per-install
money; the Alerts screen untouched when there is nothing to say; phone width; English labels with Roman Hinglish only;
country names from Intl with flags. Skipped where node is not installed."""

import json
from datetime import date
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.environ.get("VALUE_FE_FIXTURE") or os.path.join(ROOT, "tests", "fixtures", "value_sample.json")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
TILES = ["pay", "b7", "rpi", "cpi", "cty"]
RANK = {"worse": 0, "watch": 1, "better": 2, "maybe_dn": 3, "maybe_up": 3, "maybe": 3, "never": 4, "normal": 5, "ok": 5, "thin": 6,
        "low": 7, "few": 7, "unclean": 7, "nospend": 8, "wait": 9}
PAY_FAM = ("pay_slow", "pay_loss")


@pytest.fixture(scope="module")
def fixture():
    if not os.path.exists(FIXTURE):
        pytest.skip("tests/fixtures/value_sample.json not generated yet")
    with open(FIXTURE, encoding="utf-8") as f:
        fx = json.load(f)
    dv = fx.get("dashboard_value") or (fx.get("dashboard") or {}).get("value") or fx.get("value")
    files = {}
    for k, v in (fx.get("app_files") or fx.get("files") or {}).items():
        m = re.match(r"^value_([0-9a-f]+)\.json(\.gz)?$", k)
        files[m.group(1) if m else k] = v
    return {"dv": dv, "files": files}


@pytest.fixture(scope="module")
def html():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def report(fixture, html, tmp_path_factory):
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    path = str(tmp_path_factory.mktemp("fe") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "value_frontend.js"), path, FIXTURE],
                         check=True, capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout)


def rows(fx):
    return fx["dv"].get("apps") or []


def det(fx, r):
    return fx["files"].get(r["key"]) or {}


def detailed(fx):
    return [r for r in rows(fx) if det(fx, r)]


def st(m):
    s = (m or {}).get("st")
    return s if s in RANK else "wait"


def alerts_of(fx, r):
    d = det(fx, r)
    return [a for a in (fx["dv"].get("alerts") or []) if a.get("app_id") == r["app_id"]] + list(((d.get("changes") or {}).get("open")) or [])


def paid(d):
    return any(w.get("judged") for w in d.get("weeks") or [])


def test_every_value_state_renders_without_errors(report):
    assert report["errors"] == [] and report["bad"] == []
    assert report["scenarios"] >= 60


def test_tab_title_and_nav(report, html):
    assert report["titles"] == "Install value|Earning per install, ads money back & countries (GA4 + AdMob + Google Ads)"
    nav = re.findall(r'<li><button data-screen="([a-z]+)"', html.split('<ul class="nav" id="nav">')[1].split("</ul>")[0])
    assert nav.index("roas") + 1 == nav.index("value")                                # directly below 💰 Marketing ROAS
    assert nav.index("active") + 1 == nav.index("uninstall")                          # the Active / Uninstall order is kept
    assert '<li><button data-screen="value"><span class="i">💸</span> Install value</button></li>' in html
    assert "renderSettings(),renderValue());" in html                                 # rendered last: no other screen's chart ids move
    assert "if(id==='value') valEnsure();" in html


def test_jargon_and_devanagari(report):
    assert report["jargon"] == [] and report["devanagari"] == []


def test_detail_sections_in_order(report, fixture):
    for r in detailed(fixture):
        a = report["apps"][r["app"]]
        assert all(i > 0 for i in a["sections"]) and a["sections"] == sorted(a["sections"]), r["app"]
        assert a["titles"] == ["📌 At a glance", "🔔 What changed? (", "💸 Money back by install week", "🌍 Countries", "Data check",
                               "When will I know?", "← All apps", "Target: paisa"], r["app"]
        assert r["app"] in a["header"] and "Install-day data till" in a["header"]


def test_header_names_app(report, fixture):
    h = report["header"]
    assert h["app"] == h["name"] and h["valapp"] == rows(fixture)[0]["app_id"]
    assert "render" in h["calls"] and re.search(r'<option value="[^"]*" selected>', h["sel"])
    assert h["after"]["app"] == "" and h["after"]["valapp"] == ""
    g = report["gofrom"]                                                              # an Alerts card's "Open app →"
    assert g["calls"][0] == "value" and g["app"] == g["want"] and g["jump"] == "val-chg"


def test_ids_prefixed_and_unique(report):
    assert report["ids"] and all(not i["dup"] and not i["bad"] for i in report["ids"]), [i for i in report["ids"] if i["dup"] or i["bad"]][:3]


def test_tiles_five(report, fixture):
    for r in detailed(fixture):
        a, d = report["apps"][r["app"]], det(fixture, r)
        assert [t["m"] for t in a["tiles"]] == TILES, r["app"]
        assert a["phone_tiles"] and a["tile_open"], r["app"]
        for t in a["tiles"]:
            assert t["chip"] and t["big"], (r["app"], t)
            M = ((d.get("tiles") or {}).get(t["m"])) or {}
            if t["m"] == "pay":
                P = M or r.get("pay") or {}
                assert t["st"] == st(P), (r["app"], t)
                if P.get("never"):
                    assert t["big"] == "Over 1 year"
                elif P.get("v") is not None:                  # (+ the range right under it, for a phone)
                    big = re.sub(r" andaza.*$", "", t["big"])
                    assert big == ("" if P.get("obs") else "≈") + "%d day%s" % (round(P["v"]), "" if round(P["v"]) == 1 else "s")
                    assert P.get("obs") or t["big"] != big, t
                else:
                    assert t["big"] == "—"
            if t["m"] == "b7" and t["big"] != "—":
                assert re.fullmatch(r"[$₹][\d,.]+ per [$₹]100", t["big"]), t
            if t["m"] in ("rpi", "cpi") and t["big"] != "—":
                assert re.match(r"≈?[$₹]\d", t["big"]) and "<" not in t["big"], t
            if t["m"] == "cty" and t["st"] == "ok":
                assert t["big"].startswith("Best: ")
            if t["st"] not in ("wait", "nospend") and (M.get("from") or t["m"] in ("pay", "cty")) and t["m"] != "cty":
                assert t["span"].startswith("Installs "), (r["app"], t)
        assert a["ctx"].startswith("Installs") and "/week" in a["ctx"], a["ctx"]
        assert a["data_line"].startswith("Install-day data"), a["data_line"]


def test_no_red_without_warning(report, fixture):
    s = report["syn"]["no_red"]
    assert s["pills"] == [] and {"worse", "watch", "better"} <= set(s["blue"])        # the same words, in blue
    assert all(c == "info" for c, _ in s["strip"])
    assert report["syn"]["warn"]["red_tile"] and report["syn"]["warn"]["row"]          # with an open warning: red (and only then)
    for r in detailed(fixture):
        al = alerts_of(fixture, r)
        for t in report["apps"][r["app"]]["tiles"]:
            fam = PAY_FAM if t["m"] in ("pay", "b7", "cpi") else (("geo_move", "geo_cost") if t["m"] == "cty" else ())
            if t["cls"] == "p-r":
                assert any(x.get("family") in fam and x.get("severity") == "warning" for x in al), (r["app"], t)
            if t["cls"] == "p-g":
                assert any(x.get("family") in fam and x.get("severity") == "good" for x in al), (r["app"], t)
            if t["cls"] == "p-y":
                assert any(x.get("family") in fam for x in al), (r["app"], t)
            if t["st"] == "normal":
                assert t["cls"] == "uni-pz"                                          # grey outline, never green
            if t["m"] == "rpi":
                assert t["cls"] not in ("p-r", "p-y", "p-g")                         # earning per install is never coloured
        for cls, s_ in report["apps"][r["app"]]["pills"]:
            assert (cls, s_) in (("p-r", "worse"), ("p-y", "watch"), ("p-g", "better")), (r["app"], cls, s_)
    for cls, s_ in report["portfolio"]["table_pills"]:
        assert cls not in ("p-r", "p-g") or s_ in ("worse", "better")
    for cls, k, s_ in report["portfolio"]["strip_classes"]:
        assert cls not in ("bad", "good") or s_ in ("worse", "better")


def test_numbers_never_coloured(report):
    assert report["coloured"] == []                                                   # no red / green text, no up / down classes
    for a in report["apps"].values():
        for t in a["tiles"]:
            assert not re.search(r"−\d+(\.\d+)?%", t["big"]), t                       # a negative change is never a big red %


def test_valmoney_tiny_values(report):
    f = report["fmt"]
    assert f["usd"] == ["$0", "$0.0042", "$0.000040", "$0.0099", "$0.021", "$0.35", "$0.12", "$1.23", "$12.50", "−$0.0030", "—", "—", "—"]
    assert f["inr"] == ["₹0", "₹0.35", "₹0.0034", "₹0.83", "₹1.76", "₹29.40", "₹10.33", "₹103.70", "₹1,050.00", "−₹0.25", "—", "—", "—"]
    assert not any("<" in x or re.fullmatch(r"−?[$₹]0\.0+", x) for x in f["usd"] + f["inr"])     # never "<$0.01", never a "$0.00"
    assert f["big"] == ["$0", "$12", "$1,235", "—"] and f["p100"] == ["$4.3", "$42", "$143", "—"]


def test_country_names_intl_and_flags(report):
    n = {c: (name, flag) for c, name, flag in report["fmt"]["names"]}
    assert n["US"] == ("United States", "🇺🇸") and n["IN"] == ("India", "🇮🇳") and n["GB"] == ("United Kingdom", "🇬🇧")
    assert n["NG"] == ("Nigeria", "🇳🇬") and n["DE"] == ("Germany", "🇩🇪")
    assert n["--"] == ("Unknown", "❔") and n["ZZ"] == ("Other countries", "🌐") and n["zz"][0] == "Other countries"
    for r_ in report["apps"].values():
        for cc, name in r_["cty"]["names"]:
            assert name.split(" ", 1)[1] == n.get(cc, (name.split(" ", 1)[1],))[0] or cc not in n


def test_country_rows(report, fixture):
    seen = 0
    for r in detailed(fixture):
        d, c = det(fixture, r), report["apps"][r["app"]]["cty"]
        C = d.get("countries") or {}
        R = [x for x in C.get("rows") or [] if x.get("cc")]
        if not C.get("win") or not R:
            assert not c["table_desk"] and not c["cards"], r["app"]
            continue
        seen += 1
        want = [x["cc"] for x in sorted(R, key=lambda x: -(x.get("n") or 0))]
        assert c["rows_desk"] == want and c["rows_phone"] == want, r["app"]
        assert c["all_row"] == bool(C.get("app")), r["app"]
        if not C.get("geo"):
            assert c["heads"] == ["Country", "Share", "Next day", "After a week", "After 30 days", "Earning per install", "Verdict"]
        for cc, (cls, s_, label) in c["verdicts"].items():
            x = next(y for y in R if y["cc"] == cc)
            if s_ in ("top", "avg", "low", "keep", "slow", "costly"):
                assert cls == "uni-pz" and s_ == x.get("verdict")                     # a verdict: emoji + words, never a colour
        assert c["win"].startswith("Installs ") and "pakke hafte)" in c["win"], c["win"]      # (§6.4: settled → pakka)
        assert c["link"], r["app"]
        assert "of 100" in c["open_desk"] and c["open_sparks"] >= 1, r["app"]          # a tap: the sentence, the interval, 12-week lines
        assert c["open_phone"], r["app"]
        d1 = sorted([x for x in R if (x.get("d1") or {}).get("v") is not None], key=lambda x: -x["d1"]["v"])
        assert c["sort_d1"][:len(d1)] == [x["cc"] for x in d1], r["app"]
    assert seen >= 1


def test_few_badge_and_other_row(report, fixture):
    for r in detailed(fixture):
        d, c = det(fixture, r), report["apps"][r["app"]]["cty"]
        C = d.get("countries") or {}
        R = [x for x in C.get("rows") or [] if x.get("cc")]
        if not C.get("win") or not R:
            continue
        few = [x["cc"] for x in R if x.get("few")]
        assert sorted(c["few_badges"]) == sorted(few), r["app"]
        for cc in few:
            assert c["verdicts"][cc][1:] == ["few", "Few installs"] and c["verdicts"][cc][0] == "p-b"
        sm, un, ua = C.get("small") or {}, C.get("unknown") or {}, C.get("unassigned") or {}
        if (sm.get("n") or 0) > 0:
            want = ("Other small countries (%d) — %s installs, not judged" % (sm["countries"], format(sm["n"], ","))) if (sm.get("countries") or 0) > 0 \
                else "Other countries — %s installs, not judged" % format(sm["n"], ",")
            assert want in c["rest"], (r["app"], c["rest"])
        if (un.get("n") or 0) > 0 and not any(x["cc"] == "--" for x in R):
            assert "Unknown country — %s installs" % format(un["n"], ",") in c["rest"]
        nall = (C.get("app") or {}).get("n")
        share = max(ua.get("rev_share") or 0, (ua.get("n") or 0) / nall if nall else 0)
        assert any(x.startswith("Kisi country me nahi baanta (GA4)") for x in c["rest"]) == (share > 0.005), r["app"]


def test_immature_cell_text(report, fixture):
    imm = [t for a in report["apps"].values() for t in a["pay"]["imm"]]
    assert imm and all(re.fullmatch(r"in \d+ days?", t) for t in imm)                # never a small number
    for r in detailed(fixture):
        d = det(fixture, r)
        T = (fixture["dv"].get("consts") or {}).get("T") or [0, 1, 3, 7, 14, 30, 60, 90, 180, 365]
        for w in (d.get("weeks") or []):
            L = w.get("L") or [None] * 10
            for j, v in enumerate(L):
                if v is not None and w.get("t_o") is not None:
                    assert T[j] <= w["t_o"], (r["app"], w["from"], j)                 # nothing observed beyond the settled line


def test_projected_cell_marked(report):
    proj = [t for a in report["apps"].values() for t in a["pay"]["proj"]]
    assert proj and all(t.startswith("≈") for t in proj)
    for a in report["apps"].values():
        assert a["pay"]["proj_cls"] == len(a["pay"]["proj"])                          # grey italic
        assert all(t.startswith("≈") for t in a["pay"]["q"])                          # a short GA4 day: ≈ too


def test_money_back_column(report, fixture):
    for r in detailed(fixture):
        d = det(fixture, r)
        if not paid(d):
            continue
        W = sorted(d.get("weeks") or [], key=lambda w: w["from"], reverse=True)[:12]
        got = report["apps"][r["app"]]["pay"]["money_back"]
        assert len(got) == len(W), r["app"]
        for w, g in zip(W, got):
            P = w.get("pay")
            if not w.get("judged"):
                assert g in ("No ads", "Little spend"), (w["from"], g)
            elif not P:
                assert g == "—"
            elif P.get("never"):
                assert g == "Over 1 year"
            elif P.get("obs"):
                assert g == "%d day%s" % (round(P["p"]), "" if round(P["p"]) == 1 else "s")
            elif P.get("p") is not None:
                assert g.startswith("≈%d day" % round(P["p"])), (w["from"], g)


def test_week_table_and_toggle(report, fixture):
    for r in detailed(fixture):
        d, p = det(fixture, r), report["apps"][r["app"]]["pay"]
        n = len(d.get("weeks") or [])
        assert p["weeks_12"] == min(12, n) and p["weeks_all"] == n, r["app"]
        if paid(d):
            assert p["heads_desk"] == ["Week", "Installs", "Ads spend", "Cost per install", "Back in 1 day", "1 week", "30 days", "90 days", "1 year", "Money back in"]
            assert p["heads_phone"] == ["Week", "Cost per install", "1 week", "30 days", "Money back in"]
            assert p["line100"] and p["caption"] and "Cost per install = Google Ads kharcha ÷ saare naye users (ads + organic)." in p["foot"]
            assert p["inr"], r["app"]
        rels = [w["release"] for w in d.get("weeks") or [] if w.get("release") and w["release"].get("key")]
        assert sorted(k for _, k in p["rel_calls"]) == sorted(x["key"] for x in rels), r["app"]   # 📦 → Active users' Update impact
        assert all(i == r["app_id"] for i, _ in p["rel_calls"])


def test_no_geo_note(report, fixture):
    for r in detailed(fixture):
        C = det(fixture, r).get("countries") or {}
        if C.get("win") and C.get("rows"):
            assert report["apps"][r["app"]]["cty"]["nogeo"] == (not C.get("geo")), r["app"]
    g = report["syn"]["geo"]
    assert "Cost per install" in g["heads"] and "Money back in" in g["heads"] and not g["nogeo"]
    assert "✅ Keep:" in g["strip"] and "🐢 Slow:" in g["strip"] and "💸 Costly:" in g["strip"]
    assert "Cost per install" in g["open"]
    h = report["syn"]["h180"]
    assert h["rpi"] >= 1 and h["target"] and "180 din me utni kamai" in h["nogeo"]


def test_data_check_ratio(report, fixture):
    for r in detailed(fixture):
        a, d = report["apps"][r["app"]], det(fixture, r)
        assert a["chk"]["folded"] and a["chk"]["open"], r["app"]
        W = [w for w in ((d.get("scale") or {}).get("weeks") or []) if w.get("r") is not None]
        if len(W) >= 2:
            assert a["chk"]["chart"], r["app"]
        if W:
            last = sorted(w["r"] for w in W[-8:])
            m = last[len(last) // 2]
            want = "✅ GA4 aur AdMob ki kamai mel khati (±10%)" if 0.9 <= m <= 1.1 else "GA4 me AdMob ki kamai ka %d%% dikhta" % round(m * 100)
            assert want in a["chk"]["text"], r["app"]
            assert ("do baar log ho raha" in a["chk"]["text"]) == (sum(1 for w in W[-26:] if w["r"] >= 1.5) >= 8), r["app"]


def test_data_check_unassigned(report, fixture):
    for r in detailed(fixture):
        a, S = report["apps"][r["app"]], (det(fixture, r).get("scale") or {})
        if S.get("cty_gap"):
            assert "Country me na baanta gaya hissa: kamai ka" in a["chk"]["text"]
            assert re.search(r"\(last \d+ weeks\)", a["chk"]["text"])          # as many weeks as there are (≤ 12)
        if S.get("old_rev") is not None:
            assert "Purane users (14 mahine se pehle install) ki kamai:" in a["chk"]["text"]
        assert "AdMob / Google Ads India time me" in a["chk"]["text"]


def test_country_wait_not_clean(report):
    u = report["syn"]["unclean"]
    assert u["wait"] >= 2 and u["judged"] == 0 and u["approx"] >= 3 and u["tip"]
    assert "Abhi kisi country ka faisla nahi" in u["text"]                              # no Best / Least while not clean


def test_sample_note(report, fixture):
    s = report["syn"]["smp"]
    assert s["note"] == "≈ Is app ka country data GA4 sample se deta hai — country ke number andaza (≈), total sahi."
    assert s["approx"] >= 3 and any(x.startswith("Kisi country me nahi baanta (GA4) — 900 installs, kamai ka 3.4%") for x in s["unassigned"])
    for r in detailed(fixture):
        C = det(fixture, r).get("countries") or {}
        if C.get("win") and C.get("rows"):
            assert report["apps"][r["app"]]["cty"]["smp"] == bool(C.get("smp")), r["app"]


def test_release_short_day_thin_and_older(report):
    x = report["syn"]["extras"]
    assert x["rel_row"] and not x["chip"]                                             # 📦 row right above its week (the "After vX" chip: the Shuru cell now, §6.4)
    tips = {t for t, _ in x["q"]}
    assert len(x["q"]) >= 2 and all(v.startswith("≈") for _, v in x["q"])
    assert "GA4 ka is din ka data poora nahi mila — andaza" in tips and any("scale ki" in t for t in tips)
    assert x["closed"] == 1 and x["older"] == 0 and x["iap"] and x["thin"] and x["noads"] >= 3   # a year-old row: not listed (N3)


def test_never_pays_back(report):
    n = report["syn"]["never"]
    assert n["big"] == "Over 1 year" and n["chip"] == ["uni-pn", "🔴 Bigda"] and n["cell"] and n["sub"]   # §6.4: 💸 Not paying back → 🔴 Bigda


def test_changes_rows(report, fixture):
    for r in detailed(fixture):
        a, C = report["apps"][r["app"]], det(fixture, r).get("changes") or {}
        op = C.get("open") or []
        # SPEC_SIMPLIFY §6.3: "(n) … n shown · m folded below"; every open alert a row; info / older up to 90 days old
        assert a["chg_counts"] and a["chg_title"] == str(a["chg_counts"][0]) and sorted(a["chg_rows"]) == sorted(x.get("family", "") for x in op)
        assert a["all_normal"] == (a["chg_counts"] == [0, 0])
        rec = lambda o: not o.get("from") or (date.fromisoformat(r["settled_till"]) - date.fromisoformat(o.get("started") or o["from"])).days <= 90
        assert sorted(a["info_rows"]) == sorted(o.get("kind") or "info" for o in C.get("info") or [] if rec(o))
        assert a["closed_rows"] == len(C.get("closed") or []) and a["older_rows"] == sum(1 for o in C.get("older") or [] if rec(o))
        rel = [x["release"]["label"] for x in op if (x.get("release") or {}).get("key")]
        assert sorted(a["rel_chips"]) == sorted(rel)                                  # "v1.4 ke baad" in the Shuru cell (§6.4)


def test_alerts_screen_value_section_absent_when_empty(report, fixture):
    al = report["alerts"]
    assert al["absent"] == al["empty"] == al["bad"]                                  # nothing to say → not a byte more
    assert "💸 Install value" not in al["absent"] and "filterAlerts('value')" not in al["absent"]
    # SPEC_SIMPLIFY §7: the Alerts screen is ad units only — never an Install value card, sub-heading or chip
    assert al["all"]["cards"] == 0 and not al["all"]["sub"] and not al["all"]["chip"] and al["all"]["open_app"] == []
    for r in rows(fixture):
        assert al["per_app"][r["app"]]["cards"] == 0 and not al["per_app"][r["app"]]["sub"]


def test_portfolio(report, fixture):
    p, R = report["portfolio"], rows(fixture)
    # SPEC_SIMPLIFY §6.1 first line; the count line in the six words
    assert p["head"].startswith("Install value INSTALL VALUE · Sirf Google Ads wali apps (") and " tak judge hue · Pakka " in p["head"]
    assert re.fullmatch(r"(🔴 \d+ Bigda \(paisa dheere / ghate me\) · )?⚪ \d+ Normal( · 🔴 \d+ Bigda \(1 saal me bhi paisa wapas nahi\))?( · 🟡 \d+ Dhyan do \(purani halat: 1 saal me bhi paisa wapas nahi\))? · — \d+ Ads nahi chal rahe( · ⏳ \d+ Abhi jaldi)?( · ⚠️ \d+ is baar nahi bane)?", p["count"]), p["count"]
    assert [t["m"] for t in p["pool"]] == ["spend", "b7", "b30", "ok"]
    assert all(re.search(r"\d+ of %d apps" % len(R), t["text"]) for t in p["pool"])
    assert p["table_heads"] == [["app", "App"], ["spend", "Ads spend (4 wks)"], ["cpi", "Cost per install"], ["b7", "Back in 7 days"], ["b30", "30 days"],
                                ["pay", "Paisa wapas (din me)"], ["best", "Best country"], ["weak", "Weakest country"], ["status", "Status"]]   # §6.4
    assert sorted(i for _, i in p["table_rows"]) == sorted(r["app_id"] for r in R)
    assert p["chg_title"] is not None and int(p["chg_title"]) <= len(fixture["dv"].get("alerts") or [])   # the rows shown (§6.3)
    for k, o in p["xp"]["open"].items():                                             # each chip opens exactly its apps
        kind, s_ = k.split(":")
        assert o["panel"] == k and o["panels"] == 1
        assert len(o["apps"]) == p["xp"]["chips"][k]["n"]
    assert p["psorts"]["app|1"] == sorted((r["app"] for r in R), key=str.lower)
    assert p.get("noga4") == (str(len(fixture["dv"]["no_ga4"])) if fixture["dv"].get("no_ga4") else None)
    org = [r for r in R if st(r.get("pay")) == "nospend"]
    assert p.get("noads") == (str(len(org)) if org else None)
    assert p["timing"] and p["inr"] and p["ctyall_nofiles"]


def test_edge_states(report):
    s = report["syn"]
    assert "Not switched on yet" in s["no_value"] and 'id="val-off"' in s["no_value_html"]
    assert s["bad_payload"].endswith("true 0") and "THREW" not in s["bad_payload"]            # wrong shapes: renders, invents no alert
    assert "Try again" in s["file_error"] and "load ho raha hai" in s["file_loading"] and "ban nahi paya" in s["row_error"]
    assert "Countries ka data aa raha" in s["cty_wait"] and "Not enough installs per country" in s["cty_low"]
    assert "Install-wise kamai ka data aa raha" in s["no_weeks"]
    assert "Ye hissa abhi dikh nahi paya" in s["broken"] and "💸 Money back by install week" in s["broken"]    # one broken part costs only that part
    assert "📌 At a glance" in s["odd"] and "🔔 What changed? (0)" in s["odd"]
    assert all("🔌" in t for t in s["noga4"].values())
    w = s["wait_row"]                                                                  # the build's waiting row: a calm card, never "not built"
    assert 'id="val-wait"' in w["html"] and "Install-wise kamai ka data aa raha" in w["page"] and "⏳ ⏳" not in w["page"] and "ban nahi paya" not in w["page"]
    assert w["row"]


def test_phone_layout(report, fixture, html):
    assert report["wide"] == []                                                        # tables scroll inside their card; nothing wider
    for r in detailed(fixture):
        a, d = report["apps"][r["app"]], det(fixture, r)
        C = d.get("countries") or {}
        if C.get("win") and C.get("rows"):
            assert a["cty"]["cards"] and not a["cty"]["table_phone"] and a["cty"]["table_desk"] and not a["cty"]["cards_desk"]
        if a["pay"]["chart"]:
            assert a["pay"]["chart_ph"] == "1" and a["pay"]["chart_x_phone"] == ["0", "7", "30", "90", "1 yr"]
            assert a["pay"]["chart_x_desk"] == ["Install day", "1 d", "3 d", "1 wk", "2 wk", "30 d", "60 d", "90 d", "6 mo", "1 yr"]
    block = html.split("@media(max-width:430px){      /* a phone: one tile a row")[1].split("}\n  }")[0]
    assert ".val-tiles{grid-template-columns:minmax(0,1fr)}" in block and ".val-x{display:none}" in block


# ── review fixes ────────────────────────────────────────────────────────────────────────────────

def test_engine_tokens_drawn_in_the_viewers_currency(report):
    """The engine's sentences carry money / country tokens: none is ever left on a screen; money follows $ ⇄ ₹ and a
    Google Ads amount in ₹ is what Google Ads billed (its src rupees), never USD turned back at today's rate."""
    f = report["fix"]
    assert f["tokens"] == []
    assert f["spendfmt"]["a"] == ["$100", "$0.060", "$100"]
    assert f["spendfmt"]["b"][:3] == ["₹8,000", "₹5.07", "₹8,400"] and f["spendfmt"]["b"][3] == "₹8,400"   # src not INR
    assert f["spendfmt"]["t"][0] == "a $0.0042 b $0.060 c $1,335 d $0.04 e $100 f Nigeria g $20"
    assert f["spendfmt"]["t"][1] == "c ₹111,000 q ₹5.07"


def test_spend_not_in_yet_is_never_no_ads(report):
    """A week whose Google Ads spend is not in yet reads "aa raha" (unknown), never "No ads"; a week known to have had
    no spend still says "No ads"."""
    f = report["fix"]["spend_wait"]
    assert "aa raha" in f["wait"] and "No ads" not in f["wait"]
    assert "No ads" in f["none"] and "aa raha" not in f["none"]


def test_context_line_divides_by_the_weeks_it_has(report):
    f = report["fix"]
    assert "Installs 1,000 /week" in f["ctx3"] and "Google Ads $100 /week" in f["ctx3"] and "(pichhle 3 pakke hafte)" in f["ctx3"]
    assert "Google Ads ₹8,400 /week" in f["ctx3_inr"]                                   # 25,200 billed ÷ 3 weeks
    assert "Cost per install ₹8.40" in f["cpi3_inr"] and "Google Ads ₹25,200 ÷ 3,000" in f["cpi3_inr"]


def test_back_in_7_days_tile_uses_its_own_weeks_30_day_value(report):
    b = report["fix"]["b7same"]
    assert "≈$23 per $100" in b and "30 din: ≈$50" in b


def test_ranges_never_zero_width_and_kept_on_a_phone(report):
    f = report["fix"]
    assert "46–46" not in f["zerow"] and "(46" not in f["zerow"]
    assert f["rangeph"] == "andaza 107–112 din"
    assert f["paytd"].strip() == "≈109 days (107–112)"                                   # the All-apps cell


def test_wait_says_why(report):
    w = report["fix"]["waitnote"]
    assert "6 aise hafte chahiye jinke 180 din pure ho chuke" in w and "pichhla pata: kamai $0.012" in w
    assert "7 din pure hone ke ~5 din baad" not in w


def test_network_only_revenue_is_said(report):
    n = report["fix"]["network"]
    assert "AdMob ki kamai sirf AdMob network se" in n["chk"] and n["tip"]


def test_country_strip_says_what_was_judged_and_few_rows_sort_last(report):
    f = report["fix"]
    assert f["strip_none"].startswith("Abhi kisi country ka faisla nahi")
    assert "Abhi pakka nahi:" in f["strip_unranked"] and "sab app jaise" not in f["strip_unranked"]
    for order in f["few_sort"]:
        assert order and order[-1] == "KE"                                             # 120 installs: after the judged ones


def test_all_apps_while_nothing_is_checked(report):
    a = report["fix"]["all_waiting"]
    assert a["count"].startswith("⏳ Abhi koi check nahi hua") and "0 apps" not in a["count"]
    assert "All normal" not in a["chg"] and "Abhi koi check nahi hua" in a["chg"]


def test_small_per_100_values_never_read_zero(report):
    assert report["fmt"]["p100s"] == ["$0.042", "$0.0049", "$0"]


def test_observed_90_day_value_has_no_approx_mark(report, fixture):
    """The tile's 90-day earning per install comes only from weeks whose 90 days are complete (observed): no ≈ on it."""
    seen = 0
    for r in detailed(fixture):
        sub = next(t["sub"] for t in report["apps"][r["app"]]["tiles"] if t["m"] == "rpi")
        R = (det(fixture, r).get("tiles") or {}).get("rpi") or {}
        if (R.get("sub") or {}).get("90") is not None and not R.get("d90_est"):
            seen += 1
            assert "90 din $" in sub and "90 din ≈" not in sub, sub
    assert seen


def test_a_never_pays_back_level_that_was_already_there_is_purani_halat_not_red():
    # SPEC_SIMPLIFY D6: a long-standing level is never 🔴 — "1 saal+" now AND before → 🟡 Dhyan do · purani halat;
    # a NEW never-pays-back (before < 1 year) stays 🔴 Bigda
    import pathlib, re as _re
    s = pathlib.Path(__file__).resolve().parents[1].joinpath("frontend", "index.html").read_text()
    chip = s[s.index("function valChip(k,M,als){"):]
    chip = chip[:chip.index("\n}") if "\n}" in chip[:600] else 600]
    assert "st==='never'&&M&&valOk(M.p0)&&+M.p0>=366" in chip and "🟡 Dhyan do · purani halat" in chip
    summ = s[s.index("function valSumPortfolio(rows){"):][:1800]
    assert "K.neverOld++" in summ and "🟡 ${K.neverOld} Dhyan do (purani halat: 1 saal me bhi paisa wapas nahi)" in summ
