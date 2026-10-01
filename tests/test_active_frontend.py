"""The Active users tab's frontend (frontend/index.html), rendered for real: tests/active_frontend.js runs the page's own
script in a node vm on the committed fixtures (tests/fixtures/active_sample.json — the real build's Active output — and
tests/fixtures/uninstall_sample.json for the Uninstall asset) and renders every Active state: the All-apps page (every
Period and sort, every status chip opened), each app in every chart / table mode, the 📦 Update impact blocks in this
tab, the Alerts-screen section, phone and desktop widths, and made-up states the fixture may not hold. Checked here, one
test per owner must-have (spec §0, the F: ids): the tab's title and place in the sidebar; returning users with its
context; D1 / D7 tiles and their by-install-day chart; sessions / time modes and the version table; the revenue split;
no red / green without an open alert; settled dates on every tile; "What changed?" (alerts, info rows, ⏳ Early look
uncounted); 📦 chips opening the right block in THIS tab; the return grid; the Update impact card with no id clash; the
Alerts screen; the All-apps chips / updates / table; honest counts; provisional / estimate marks; the header naming the
app; the data-edge sentences; English labels with Roman Hinglish only; phone width; and the All-apps "📅 Daily — all apps"
section (active_portfolio.json.gz: every row recomputed from the file, the build's own total, ranges, provisional days,
app-count markers, same-apps week-over-week, the app filter, $ ⇄ ₹, lazy load, failure isolation). Skipped where node is
not installed."""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.environ.get("ACTIVE_FE_FIXTURE") or os.path.join(ROOT, "tests", "fixtures", "active_sample.json")
UNI_FIXTURE = os.environ.get("UNINSTALL_FE_FIXTURE") or os.path.join(ROOT, "tests", "fixtures", "uninstall_sample.json")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
RANK = {"worse": 0, "break": 1, "watch": 2, "slow": 2, "better": 3, "maybe_dn": 4, "maybe_up": 4, "price_dn": 5, "price_up": 5,
        "growth": 6, "normal": 7, "low": 8, "noad": 8, "wait": 9}
TILE_KEYS = ("ret_dau", "d1", "d7", "sess", "time", "arpdau")
# SPEC_SIMPLIFY §1.8 / §6.4: exactly six status words — one per state (the metric is named by its tile / strip / column)
WORD = {"worse": "🔴 Bigda", "watch": "🟡 Dhyan do", "slow": "🟡 Dhyan do", "break": "🟡 Dhyan do", "better": "🟢 Behtar",
        "maybe_dn": "⚪ Normal", "maybe_up": "⚪ Normal", "normal": "⚪ Normal", "price_dn": "⚪ Normal", "price_up": "⚪ Normal",
        "growth": "⏳ Abhi jaldi", "low": "⏳ Abhi jaldi", "wait": "⏳ Abhi jaldi", "noad": "— Lagu nahi"}


@pytest.fixture(scope="module")
def fixture():
    if not os.path.exists(FIXTURE):
        pytest.skip("tests/fixtures/active_sample.json not generated yet")
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


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
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "active_frontend.js"), path, FIXTURE, UNI_FIXTURE],
                         check=True, capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout)


def rows(fx):
    return fx["dashboard_active"]["apps"]


def det(fx, r):
    return fx["app_files"].get(r["key"]) or {}


def st(m):
    return (m or {}).get("st") if (m or {}).get("st") in RANK else "wait"


def day_words(iso):
    """The day and month an engine / page date names ("28 Jul"), whatever its year style."""
    return "%d %s" % (int(iso[8:]), MON[int(iso[5:7]) - 1])


def test_every_active_state_renders_without_errors(report):
    assert report["errors"] == [] and report["bad"] == []
    assert report["scenarios"] >= 70


def test_tab_title_and_nav(report, html):
    assert report["titles"] == "Active users|Returning users, comebacks, time & ad revenue (GA4)"
    nav = re.findall(r'<li><button data-screen="([a-z]+)"', html.split('<ul class="nav" id="nav">')[1].split("</ul>")[0])
    assert nav.index("active") + 1 == nav.index("uninstall")                       # directly above 🚪 Uninstall
    assert '<li><button data-screen="active"><span class="i">👥</span> Active users</button></li>' in html


def test_jargon_and_devanagari(report):
    assert report["jargon"] == [] and report["devanagari"] == []


def test_detail_sections_in_order_with_english_titles(report, fixture):
    for r in rows(fixture):
        a = report["apps"][r["app"]]
        assert all(i > 0 for i in a["sections"]) and a["sections"] == sorted(a["sections"]), r["app"]
        assert a["daily_title"] and a["tri_title"] and a["use_title"] and a["rev_title"]
        # (SPEC_SIMPLIFY §6.5: the update card lives on the Uninstall tab — here its one-line link)
        assert a["has_titles"] == ["📌 At a glance", "🔔 What changed? (", "📦 Is app ke updates ka asar", "When will I know?", "← All apps"], r["app"]
        assert {"7-day average", "Every day", "30 days", "3 months", "1 year", "All time"} <= set(a["chips_seen"]), r["app"]


def test_header_names_app(report, fixture):
    h = report["header"]
    assert h["app"] == h["name"] and h["actapp"] == rows(fixture)[0]["app_id"]
    assert "render" in h["calls"] and re.search(r'<option value="[^"]*" selected>', h["sel"])
    assert h["name"].replace("&", "&amp;") in h["screen"] or h["name"] in h["screen"]
    assert h["after"]["app"] == "" and h["after"]["actapp"] == ""
    for r in rows(fixture):
        assert r["app"] in report["apps"][r["app"]]["header"]
    g = report["gofrom"]                                              # an Alerts card's "Open app →"
    assert g["calls"][0] == "active" and g["app"] == g["want"] and g["jump"] == "act-chg"


def test_tile_returning_has_context_line(report, fixture):
    for r in rows(fixture):
        a = report["apps"][r["app"]]
        assert a["ctx"], r["app"]
        assert a["ctx_text"].startswith("Active users") and "Installs" in a["ctx_text"]              # (no word "New": §9 check 1)
        c = det(fixture, r).get("ctx") or {}
        assert ("days ago" in a["ctx_text"]) == (c.get("old") is not None), r["app"]
        assert ("≈" in a["ctx_text"]) == bool(c.get("old") is not None and c.get("old_est")), r["app"]
        rt = next(t for t in a["tiles"] if t["m"] == "ret_dau")
        assert rt["chip"], r["app"]


def test_tiles_d1_and_d7_separate(report, fixture):
    for r in rows(fixture):
        tiles = [t["m"] for t in report["apps"][r["app"]]["tiles"]]
        assert tiles == list(TILE_KEYS), (r["app"], tiles)
        for t in report["apps"][r["app"]]["tiles"]:
            if t["m"] in ("d1", "d7") and t["st"] not in ("wait", "noad") and t["big"] != "—":
                assert t["big"].endswith("of 100"), (r["app"], t)


def test_tiles_show_settled_dates(report, fixture):
    for r in rows(fixture):
        d = det(fixture, r)
        for t in report["apps"][r["app"]]["tiles"]:
            M = (d.get("tiles") or {}).get(t["m"]) or {}
            assert t["st"] == st(M), (r["app"], t["m"])
            if t["st"] in ("wait", "noad") or not (M.get("from") or (t["m"] not in ("d1", "d7") and (r.get("win") or {}).get("from"))):
                continue
            assert t["dates"], (r["app"], t["m"])
            assert t["dates"].startswith("Installs ") == (t["m"] in ("d1", "d7")), (r["app"], t)


def test_no_red_or_green_without_open_alert(report, fixture):
    assert report["colour"] == []
    s = report["syn"]["no_alert_red"]
    assert not s["red"] and not s["green"] and len(s["blue"]) >= 2
    for r in rows(fixture):
        for t in report["apps"][r["app"]]["tiles"]:
            if t["cls"] in ("p-r", "p-g"):
                assert t["st"] in ("worse", "better"), (r["app"], t)
            if t["st"] == "normal":
                assert t["cls"] == "uni-pz"                                # grey outline, never green
    for cls, s_ in report["portfolio"]["table_pills"]:
        assert cls not in ("p-r", "p-g") or s_ in ("worse", "better")
    for cls, k, s_ in report["portfolio"]["strip_classes"]:
        assert cls not in ("bad", "good") or s_ in ("worse", "better")


def test_rev_tile_split(report, fixture):
    for r in rows(fixture):
        t = next(x for x in report["apps"][r["app"]]["tiles"] if x["m"] == "arpdau")
        if t["st"] in ("noad", "wait"):
            assert t["big"] == "—" and "$0" not in t["text"]
            continue
        assert "AdMob ads har user" in t["text"] and "Ad rate (1,000 ads ka)" in t["text"], (r["app"], t["text"])   # §6.4 words
        if t["big"] != "—":
            assert t["big"].startswith("≈"), (r["app"], t["big"])
        osh = (det(fixture, r).get("flags") or {}).get("other_share")
        assert ("Sirf AdMob Network · dusre ad networks se ~" in t["text"]) == (osh is not None and osh >= 0.05), r["app"]


def test_ads_dir_chip_is_prefixed(report):
    # SPEC_SIMPLIFY §1.8: the status word alone, whose number it is in its "Saath me:" line
    assert report["syn"]["ads_dir"] == "⚪ Normal | AdMob ads har user ke hisaab se"


def test_no_ad_data_never_renders_zero(report, fixture):
    for r in rows(fixture):
        assert not report["apps"][r["app"]]["rev"]["zero_money"], r["app"]
        gaps = (det(fixture, r).get("daily") or {}).get("rev_gaps") or []
        assert bool(report["apps"][r["app"]]["rev"]["gaps"]) == bool(gaps), r["app"]
        if gaps:
            assert report["apps"][r["app"]]["rev"]["gaps"].startswith("No ad data ")
    assert report["syn"]["all_wait"]["dashes"] >= 5 and not report["syn"]["all_wait"]["zero_money"]


def test_rev_note_names_data_zones(report):
    z, zg, zs = report["syn"]["zones"], report["syn"]["zones_gmt"], report["syn"]["zones_same"]
    assert "AdMob ka din (Tokyo) aur GA4 ka din (Los Angeles) alag" in z
    assert "AdMob ka din (UTC+5) aur GA4 ka din (UTC) alag" in zg
    assert "alag —" not in zs and "Sirf AdMob Network" in zs
    for n in (z, zg, zs):
        assert not re.search(r"\b(IST|GMT)\b", n), n


def test_use_card_modes(report, fixture):
    for r in rows(fixture):
        u = report["apps"][r["app"]]["use_modes"]
        if (det(fixture, r).get("edges") or {}).get("usage_state") == "wait":
            assert all(m["wait"] for m in u.values()), r["app"]
            continue
        assert u["base"]["on"] == ["Time per user", "Purane users (roz)", "7-day average"], (r["app"], u["base"])   # §6.4
        assert u["sess_all"]["on"] == ["Sessions per user", "All users", "7-day average"]
        assert u["time_new_day"]["on"] == ["Time per user", "Installs", "Every day"]
        assert u["time_new_day"]["context"] and not u["time_new_day"]["band"] and not u["base"]["band"]
    assert report["syn"]["usage_wait"]["tiles"] == 2 and report["syn"]["usage_wait"]["card"]


def test_version_table(report, fixture):
    for r in rows(fixture):
        d, a = det(fixture, r), report["apps"][r["app"]]
        V, VM = d.get("versions") or [], d.get("versions_more") or []
        assert a["versions_base"] == [v["ver"] for v in V if not v.get("kind")] + [v["ver"] for v in V if v.get("kind")], r["app"]
        assert len(a["versions"]) == len(V) + len(VM), r["app"]                 # "Show all versions": none dropped
        for ver, label in a["versions"]:
            kind = next((v.get("kind") for v in V + VM if v["ver"] == ver), None)
            if kind == "rest":
                assert label == "Other versions (<1% each)"
            elif kind == "x":
                assert label == "Version not set"


def test_changes_rows(report, fixture):
    # SPEC_SIMPLIFY §6.3: "What changed? (n) Sirf ye app: … · n shown · m folded below"; every open alert is a row (an
    # act_slow told inside its act_drift, M5), info / older rows up to 90 days old in the folds; one of the 6 words each
    for r in rows(fixture):
        C, a = det(fixture, r).get("changes") or {}, report["apps"][r["app"]]
        op = C.get("open") or []
        slow_in_drift = [x for x in op if x.get("family") == "act_slow" and any(z.get("family") == "act_drift" and z.get("metric") == x.get("metric") for z in op)]
        assert sorted(a["chg_rows"]) == sorted(x.get("family") or "" for x in op if x not in slow_in_drift), r["app"]
        assert a["chg_counts"] and a["chg_title"] == str(a["chg_counts"][0]), r["app"]
        assert sorted(a["info_rows"]) == sorted(o.get("kind") or "info" for o in C.get("info") or []
                                                if not o.get("from") or (_date.fromisoformat(r["data_till"]) - _date.fromisoformat(o.get("started") or o["from"])).days <= 90), r["app"]
        assert a["closed_rows"] == len(C.get("closed") or []), r["app"]
        for cls, lbl in a["sev_pills"]:
            assert (cls, lbl) in (("p-r", "🔴 Bigda"), ("p-y", "🟡 Dhyan do"), ("p-g", "🟢 Behtar"), ("p-b", "ℹ️ Jaankari"))


def test_changes_all_normal(report, fixture):
    for r in rows(fixture):
        a = report["apps"][r["app"]]
        # "✅ All normal — no changes" only when the list has no row at all (folded ones count: SPEC_SIMPLIFY §6.3)
        assert a["all_normal"] == (a["chg_counts"] == [0, 0]), r["app"]
    t = report["portfolio"]
    AL = fixture["dashboard_active"].get("alerts") or []
    assert set(t["chg_rows"]) <= {x["app_id"] for x in AL} and t["chg_title"] == str(len(t["chg_rows"]))


def test_early_look_row_is_provisional_and_uncounted(report):
    e = report["syn"]["early"]
    assert e["row"] and e["pill"] and not e["counted"]               # an ℹ️ Jaankari row with its "⏳ Pakka nahi", never an alert
    assert e["title"] is not None and int(e["title"]) <= int(e["open"])   # "What changed? (n)" = the rows shown (never the info row)


def test_pkg_chip_opens_block_in_active(report, fixture):
    # SPEC_SIMPLIFY §6.5 / D4: the update card lives on the Uninstall tab only — a 📦 chip here opens THAT block there
    imp = report["imp"]
    want = [(r["app"], x["key"]) for r in rows(fixture) for x in det(fixture, r).get("releases") or [] if x.get("key")]
    assert sorted((j["app"], j["key"]) for j in imp["jumps"]) == sorted(want)
    for j in imp["jumps"]:
        assert j["open"] == "" and j["rendered"] is None and j["uni_open"] == j["key"], j
    assert all(c["known"] and c["call"] == c["key"] for c in imp["chips"])
    assert all(b["act"] and b["known"] for b in imp["badges"])
    if want:
        assert imp["chips"], "no 📦 chip under any chart"


def test_uniimpgo_act_path_shows_active(report):
    g = report["imp"].get("go")
    if g is None:
        pytest.skip("no app with an update block in the fixture")
    assert g["calls"][0] == "show:uninstall" and g["uni"] == g["key"] and g["open"] == "" and not g["screen"]   # §6.5: the Uninstall tab's card


def test_imp_card_in_active(report, fixture):
    # SPEC_SIMPLIFY §6.5 / D4: no update card on the Active app page — one line "Is app ke updates ka asar → Uninstall tab ›"
    for r in rows(fixture):
        assert report["apps"][r["app"]]["imp_card"], r["app"]
    for b in report["imp"]["blocks"]:
        assert b["n_open"] == 0 and not b["id_act"] and not b["id_uni"] and b["rows"] == 0, b
        assert b["acts"] == ["onclick=\"uniGo('%s')\"" % next(r["app_id"] for r in rows(fixture) if r["app"] == b["app"])], b["acts"]


def test_no_duplicate_ids_across_tabs(report, fixture):
    assert len(report["ids"]) == len([r for r in rows(fixture) if det(fixture, r)])
    for x in report["ids"]:
        assert x["dup_uni"] == [] and x["dup_act"] == [] and x["shared"] == [], x
        assert x["act_not_prefixed"] == [], x                            # every id in the tab starts with act-


def test_alerts_screen_active_section(report, fixture):
    # SPEC_SIMPLIFY §7: the Alerts screen is ad units only — no Active users cards, sub-heading or filter chip
    A = report["alerts"]
    assert A["all"]["cards"] == 0 and not A["all"]["sub"] and not A["all"]["chip"] and A["all"]["open_app"] == []
    for r in rows(fixture):
        p = A["per_app"][r["app"]]
        assert p["cards"] == 0 and not p["sub"] and not p["chip"], r["app"]
    assert A["no_active"]["cards"] == 0 and not A["no_active"]["sub"] and not A["no_active"]["chip"]
    assert "GA4 not connected" in A["no_active_tab"]


def test_portfolio_chips_open_exact_apps(report, fixture):
    xp = report["portfolio"]["xp"]
    assert not xp["default_open"]                                         # no app list by default
    for k in TILE_KEYS:
        want = {}                                                          # one chip per status WORD (SPEC_SIMPLIFY §1.8), its id the
        for r in rows(fixture):                                            # metric + its group's most urgent state
            want.setdefault(WORD[st((r.get("m") or {}).get(k))], []).append((st((r.get("m") or {}).get(k)), r["app"]))
        want = {min((s0 for s0, _ in L), key=lambda z: RANK[z]): [a for _, a in L] for L in want.values()}
        for s_, apps in want.items():
            c = xp["chips"].get("%s:%s" % (k, s_))
            assert c and c["n"] == len(apps), (k, s_, c, apps)
            o = xp["open"]["%s:%s" % (k, s_)]
            assert o["panels"] == 1 and o["on"] == 1 and o["panel"] == "%s:%s" % (k, s_)
            assert o["apps"] == apps, (k, s_, o["apps"], apps)
            assert len(o["calls"]) == len(apps)
    K = {"worse": 0, "watch": 0, "ok": 0, "wait": 0, "better": 0}
    for r in rows(fixture):
        s_ = (r.get("summary") or {}).get("kind")
        K["worse" if s_ == "worse" else "watch" if s_ in ("break", "watch", "slow") else "better" if s_ == "better" else "ok" if s_ in ("ok", "maybe") else "wait"] += 1
    c = report["portfolio"]["count"]
    assert c.startswith("🔴 %d Bigda" % K["worse"]) and "🟡 %d Dhyan do" % K["watch"] in c and "⚪ %d Normal" % K["ok"] in c and "⏳ %d Abhi jaldi" % K["wait"] in c


def test_portfolio_recent_updates(report, fixture):
    # SPEC_SIMPLIFY §6.5: "📦 Updates ka asar" is removed from the Active All-apps page (it is the Uninstall tab's)
    u = report["portfolio"]["updates"]
    assert not u["has"] and u["rows"] == []


def test_portfolio_table_sort(report, fixture):
    R = {r["app"]: r for r in rows(fixture)}
    col = {"ret": ("ret_dau", "v"), "rel": ("ret_dau", "rel"), "d1": ("d1", "v"), "d7": ("d7", "v"), "sess": ("sess", "v"), "time": ("time", "v"), "rev": ("arpdau", "v")}
    heads = [k for k, _ in report["portfolio"]["table_heads"]]
    assert heads == ["app", "ret", "rel", "d1", "d7", "sess", "time", "rev", "status"]
    assert [l for _, l in report["portfolio"]["table_heads"]] == ["App", "Purane users (roz)", "vs 4 wks", "Next day", "After a week", "Sessions/user", "Time/user", "Kamai har 1,000 users se", "Status"]   # §6.4
    for key, order in report["portfolio"]["sorts"].items():
        k, d = key.split("|")
        assert sorted(order) == sorted(R), key
        if k == "app":
            continue
        if k == "status":
            v = [min(RANK[st((R[a].get("m") or {}).get(m))] for m in TILE_KEYS) for a in order]
        else:
            v = [((R[a].get("m") or {}).get(col[k][0]) or {}).get(col[k][1]) for a in order]
        known = [x for x in v if x is not None]
        assert v[:len(known)] == known, key                                 # no value → always last
        assert known == sorted(known, reverse=(d == "-1")), (key, known)


def test_honest_counts(report, fixture):
    assert report["syn"]["six_days"]
    n = len(rows(fixture))
    for p in report["portfolio"]["pool"]:
        assert re.search(r"\b\d+ of %d apps\b" % n, p["text"]), p
    assert report["portfolio"]["noga4"] == str(len(fixture["dashboard_active"].get("no_ga4") or [])) or not fixture["dashboard_active"].get("no_ga4")


def test_older_changes_never_dropped(report, fixture):
    for r in rows(fixture):
        O = (det(fixture, r).get("changes") or {}).get("older") or []
        n = sum(1 for o in O if not o.get("from") or (_date.fromisoformat(r["data_till"]) - _date.fromisoformat(o.get("started") or o["from"])).days <= 90)
        assert report["apps"][r["app"]]["older_rows"] == n                # > 90 days old: only in the charts (SPEC_SIMPLIFY §1.3)
    # All apps: the build's compact rows (dashboard.json — the same before and after opening an app, §6.3)
    info = fixture["dashboard_active"].get("info") or []
    assert report["portfolio"]["older_open"] == sum(1 for o in info if o.get("src") == "older")
    assert not report["portfolio"]["older_nofiles"]                       # no "open an app for its full history" any more


def test_prov_and_est_marks(report, fixture):
    for r in rows(fixture):
        d, a = det(fixture, r), report["apps"][r["app"]]
        L = d.get("latest") or {}
        assert a["latest"] == ""                                          # one metric = one number: no single-day line (§6.5)
        assert a["prov_note"] == bool(d.get("settled_till") and d.get("data_till") and d["settled_till"] < d["data_till"]), r["app"]
        assert "Pichhle 7 din (" in a["kpis_today"], r["app"]                  # a fixed 7 days, whatever the Period (§6.2)
    assert report["portfolio"]["prov_note"]


def test_prov_cell_never_coloured(report):
    assert report["grid"], "no grid rendered"
    for g in report["grid"]:
        assert g["prov_bad"] == 0 and g["part_bad"] == 0, g


def test_grid_rows(report, fixture):
    for g in report["grid"]:
        r = next(x for x in rows(fixture) if x["app"] == g["app"])
        T = det(fixture, r).get("tri") or {}
        allr = sorted(T.get("rows") or [], key=lambda x: x["from"], reverse=True)
        vis = allr if g["pre"] else [x for x in allr if not x.get("pre")]
        want = vis if g["exp"] else vis[:12]
        assert g["weeks"] == [x["from"] for x in want], (g["app"], g["pre"], g["exp"])
        assert g["more"] == (len(vis) > 12)
        assert g["nodata"] == sum(1 for x in want if x.get("nodata"))


def test_grid_year_sep(report, fixture):
    for g in report["grid"]:
        r = next(x for x in rows(fixture) if x["app"] == g["app"])
        allr = sorted((det(fixture, r).get("tri") or {}).get("rows") or [], key=lambda x: x["from"], reverse=True)
        byf = {x["from"]: x for x in allr}
        yrs, last, pre = [], None, False
        for w in g["weeks"]:
            x = byf[w]
            if x.get("pre") and not pre:
                pre, last = True, None
            if x["to"][:4] != last:
                last = x["to"][:4]
                yrs.append(last)
        assert g["years"] == yrs, (g["app"], g["years"], yrs)


def test_grid_test_toggle(report, fixture):
    for g in report["grid"]:
        r = next(x for x in rows(fixture) if x["app"] == g["app"])
        d = det(fixture, r)
        pre = [x for x in (d.get("tri") or {}).get("rows") or [] if x.get("pre")]
        assert g["test_sep"] == bool(g["pre"] and pre), g["app"]
    for r in rows(fixture):
        hid = bool((det(fixture, r).get("launch") or {}).get("hidden"))
        assert ("Show test installs" in report["apps"][r["app"]]["chips_seen"]) == (hid and bool(((det(fixture, r).get("tri") or {}).get("rows"))) and (det(fixture, r).get("edges") or {}).get("ret_state") != "wait"), r["app"]


def test_grid_pkg_line(report, fixture):
    for g in report["grid"]:
        r = next(x for x in rows(fixture) if x["app"] == g["app"])
        d = det(fixture, r)
        allr = {x["from"]: x for x in (d.get("tri") or {}).get("rows") or []}
        rels = [x for x in d.get("releases") or [] if x.get("date")]
        pend = False
        for o in g["order"]:
            if o == "uni-rel":
                pend = True
                continue
            if o == "uni-yr":
                assert not pend, "a year row under a 📦 line"
                continue
            w = allr[o[2:]]
            has = any(w["from"] <= x["date"] <= w["to"] for x in rels)
            assert has == pend, (g["app"], w["from"], has, pend)
            pend = False
        assert len(g["rel_lines"]) == sum(1 for w in g["weeks"] if any(allr[w]["from"] <= x["date"] <= allr[w]["to"] for x in rels))


def test_return_daily_chart(report, fixture):
    for c in report["retc"]:
        r = next(x for x in rows(fixture) if x["app"] == c["app"])
        d = det(fixture, r)
        E = d.get("edges") or {}
        nmax = (d.get("tri") or {}).get("nmax") or 0
        if E.get("ret_state") == "wait" or not ((d.get("tri") or {}).get("rows")) or nmax < 1:
            assert not c["has"], c
            continue
        assert c["chips"] == [n for n in (1, 3, 7, 14, 30) if n <= nmax], c
        if c["N"] > nmax:
            continue
        assert c["has"], c
        if c["n"] and E.get("ret_from"):
            assert c["first"] and c["first"] >= E["ret_from"], c                  # no value before the data edge
        assert c["edge_mark"] == (E.get("ret_state") == "found" and bool(E.get("ret_from"))), c


def test_return_chart_rate_is_over_the_install_days_new_users(report):
    """The by-install-day chart divides by the install day's GA4 new users (Firebase's "New users" base): the cohort's
    own total t changing moves nothing, new users changing moves the points."""
    got = [c for c in report["retbase"] if c["n"]]
    assert got, report["retbase"]
    assert all(c["t_same"] and c["new_moves"] for c in got), got


def test_grid_week_installs_unknown_reads_dash_never_0(report):
    """A grid week without a rate day has unknown installs (null): its label reads "— installs", never "0 installs"."""
    assert report["ginst"], report["ginst"]
    for g in report["ginst"]:
        assert "— installs" in g["none"] and not re.search(r"(^|\s)0 installs", g["none"]), g
        assert "12,345 installs" in g["some"], g


def test_edge_states_render(report, fixture):
    for r in rows(fixture):
        E = det(fixture, r).get("edges") or {}
        # (the engine's sentences, said the SIMPLIFY way: no "D1 / D7" code, §6.4)
        assert report["apps"][r["app"]]["edges"] == [re.sub(r"\bD1 ?/ ?D7\b", "agle din / 7 din baad", t).replace(" (mediation)", "") for t in E.get("text") or [] if t], r["app"]
        if E.get("ret_state") == "found" and E.get("ret_from"):
            assert any(day_words(E["ret_from"]) in t for t in E.get("text") or []), r["app"]
    s = report["syn"]
    assert s["searching"]["text"] and not s["searching"]["edge_row"] and s["searching"]["grid"]
    assert s["wait"]["text"] and s["wait"]["tiles"] == 2
    assert s["found"]["edge_row"]


def test_phone_layout(report, fixture):
    for g in report["grid"]:
        r = next(x for x in rows(fixture) if x["app"] == g["app"])
        T = det(fixture, r).get("tri") or {}
        if g["mode"] == "all":
            assert g["heads"] == list(range(1, (T.get("nmax") or 0) + 1))
        elif g["w"] == 375:
            assert g["heads"] == [n for n in (T.get("cols_phone") or T.get("cols") or []) if 1 <= n <= 30], g
        else:
            assert g["heads"] == [n for n in T.get("cols") or [] if 1 <= n <= 30], g
    for r in rows(fixture):
        a = report["apps"][r["app"]]
        assert a["phone_short"] and a["tile_open"], r["app"]


def chip_label(k, M):
    """SPEC_SIMPLIFY §1.8: one set for tiles, strips and the table — the status word of the state (was: a per-metric
    English vocabulary, "Lower · watch", "Ads/user maybe lower", …)."""
    return WORD[st(M)]


def test_chip_vocabulary(report, fixture):
    for r in rows(fixture):
        tiles = (det(fixture, r).get("tiles") or {})
        for t in report["apps"][r["app"]]["tiles"]:
            assert t["chip"] == chip_label(t["m"], tiles.get(t["m"])), (r["app"], t["m"], t["chip"])
    for key, c in report["portfolio"]["xp"]["chips"].items():
        k, s_ = key.split(":")
        want = chip_label(k, {"st": s_})
        assert c["label"] == want, (key, c["label"])


# ── review fixes ────────────────────────────────────────────────────────────────────────────────

def test_market_lines_count_moved_of_total_and_old_weeks_are_past(report):
    # SPEC_SIMPLIFY §6.2 / §6.4: the market line is "Saath me: kai apps me ek saath — bazaar ka asar", always with its
    # dates, and only while it is ≤ 14 days old (a month-old week: hidden, never told in the past tense)
    fx = report["fix"]
    assert fx["rev_market"] == "", fx["rev_market"]                                       # a week of 1–7 Sep: > 14 days old
    assert fx["pf_market_now"].startswith("Saath me: kai apps me ek saath — bazaar ka asar · ")
    assert "15 me se 13 apps ka ad rate −10%" in fx["pf_market_now"] and "kam dikhegi, app ki galti nahi" in fx["pf_market_now"]
    assert fx["pf_market_old"] == ""


def test_install_part_keeps_its_sign(report):
    """SPEC_SPLIT §6.4.2: the installs' part of the returning users' change keeps its sign — opposite, same and ~0 — now
    as the split block (whole %s that add up as printed, the per-user part absorbing the rounding; the elastic estimate
    says ≈ Andaza; no "pts")."""
    fx = report["fix"]
    for k, (t, f, p) in (("inst_opp", ("+8%", "−6%", "+14%")), ("inst_same", ("−12%", "−8%", "−4%")), ("inst_zero", ("+2%", "0%", "+2%"))):
        b = fx[k].strip()
        assert b.startswith("Purane users roz: %s (" % t), b
        assert "• installs ki wajah se: %s (" % f in b and "• asli badlaav: %s" % p in b, b
        assert "≈ Andaza" in b and "pts" not in b and "about" not in b, b


def test_alert_hint_follows_the_metric(report):
    fx = report["fix"]
    assert "💡 Har user ko kam ads — ad load / fill / mediation" in fx["hint_ads"] and "Purane users" not in fx["hint_ads"]
    assert "💡 Purane users dheere dheere kam" in fx["hint_ret"]


def test_a_linked_alert_is_one_story_with_the_update_card(report):
    fx = report["fix"]
    assert "📦 Yahi badlaav v1.2 ke Update impact card me bhi hai" in fx["linked"]
    assert fx["total_unlinked"] is not None and fx["total_linked"] is not None
    assert int(fx["total_linked"]) == int(fx["total_unlinked"]) == 0                   # SPEC_SIMPLIFY §7: ad units only


def test_waiting_metrics_say_why_on_the_all_apps_page(report):
    fx = report["fix"]
    by = {t["m"]: t["text"] for t in fx["pool_wait"]}
    for k in ("d1", "d7"):
        assert "Wapsi ka data agle GA4 fetch ke saath aayega" in by[k] and " of " not in by[k]
    for k in ("sess", "time"):
        assert "Sessions / time agle GA4 fetch me aayenge" in by[k]
    assert "Next day / After a week: wapsi ka data agle GA4 fetch ke saath" in fx["table_wait"]


def test_a_tile_that_is_not_judged_shows_no_big_change(report):
    t = report["fix"]["young_tile"]
    assert "+99%" not in t and "+127%" not in t
    assert "Naya app — tulna baad me" in t and "Tulna pakki nahi" in t


def test_period_row_says_network_only_and_one_day(report, fixture):
    for r in rows(fixture):
        k = report["apps"][r["app"]]["kpis_today"]
        assert "1 days" not in k
        if "with ad data" in k:
            assert "AdMob Network only" in k


def test_phone_status_strip_never_widens_the_page(html):
    block = html.split("@media(max-width:760px){\n    .act-strip")[1].split("}\n  }")[0]
    assert "grid-template-columns:minmax(0,1fr)" in block and "min-width:0" in block



# ── 📦 Before / after windows in this tab (SPEC_WINDOWS §5) ─────────────────────────────────────────────────────────

def test_windows_in_active_have_their_own_default_act_onclicks_and_open_here_at_30(report):
    w = report["win"]["syn"]
    assert w, "no app with an update block in the fixture"
    assert w["act"] and set(w["act"]) == {" (30 days)"} and w["acwin"] == 30        # this tab's card at 30 …
    assert w["uni"] and set(w["uni"]) == {""} and w["uwin"] == 7                   # … the Uninstall tab's still at 7
    assert w["saved"] == [["imp_win_act", "30"]]
    assert w["note"] == "Ye card = har update ke 30 din pehle vs 30 din baad (upar chuno) · upar ke tiles = pichhle 7 pakke din"
    assert set(w["act2"]) == {" (30 days)"} and set(w["uni2"]) == {" (60 days)"} and w["saved2"][-1] == ["imp_win_uni", "60"]
    calls = [c for c in w["onclicks"] if c.startswith('onclick="uni')]
    assert calls and all("'act')" in c for c in calls), calls                        # every tap stays in this tab
    assert any(c.startswith('onclick="uniImpWinX(') for c in calls) and any(c.startswith('onclick="uniImpWX(') for c in calls)
    assert w["late"] == ["event.stopPropagation();uniImp('%s','act',30)" % w["key"], "30 din baad: ⚠️ Ruk ke jaancho"]   # §6.4 words
    assert w["upd"] == ["event.stopPropagation();uniImpGo('%s','%s','act',30)" % (w["app_id"], w["key"]), "30 din baad: 🛑 Update roko"]
    assert all(i.startswith("act-") for i in w["ids"]), w["ids"]


def test_windows_every_fixture_block_in_active_at_30(report):
    if not report["win"]["v2"]:
        pytest.skip("the committed Active fixture has no by_window yet (impact v1): the made-up windows above cover this tab")
    for b in report["win"]["blocks"]:                                    # SPEC_SIMPLIFY §6.5: no block on the Active page
        assert not b["id_act"] and b["hdr"] is None and b["rows"] == [], b
        assert len(b["acts"]) == 1 and b["acts"][0].startswith('onclick="uniGo('), b["acts"]


def test_the_note_says_upar_chuno_only_right_under_its_selector(report, fixture):
    # (review 2026-09-28) the note sat above the selector while saying "upar chuno", and showed on apps with no
    # selector at all: now under the selector (an app with updates) — else today's words, under the title
    seg = [report["apps"][r["app"]]["imp_seg"] for r in rows(fixture)]
    assert not any(seg), seg                                              # SPEC_SIMPLIFY §6.5: the card (and its note) is gone here
    assert all(report["apps"][r["app"]]["imp_card"] for r in rows(fixture))   # … its one-line link instead


# ── 📅 Daily — all apps (the All-apps page's day-by-day portfolio, active_portfolio.json.gz) ────────────────────────
# The harness renders the section on the fixture's own portfolio file (or, until the fixture carries one, a stub it
# builds from the per-app details by the same contract) — report["pf"]["file"] is the file it used. Every number on the
# page is recomputed here, independently, from that file.

from datetime import date as _date, timedelta as _td


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


PF_MISS = 0.02     # a missing app "matters" on a day when its own recent DAU (mean of its last 7 days with data) is >= 2% of the day's


def pf_days(F, vis=None, n_err=None):
    """The contract's page rules, in Python: {day: sums} over the visible apps (vis = app ids, None = all). On top (the
    page's own): an app not built this run (the file's missing list, why != "no_data"; n_err overrides the count) is in
    nn every day; ms = the usual DAU of the in-set apps without data that day (each one's mean over its last 7 days with
    data) and inc = ms >= 2% of (DAU + ms) — a day whose sums read low."""
    A = [a for a in F.get("apps") or [] if isinstance(a, dict) and isinstance(a.get("start"), str) and a.get("a1")
         and (vis is None or a["app_id"] in vis)]
    D = _date.fromisoformat
    frm = min(D(a["start"]) for a in A)
    fc = F.get("currency") or next((a["currency"] for a in A if a.get("currency")), None)
    P = []
    for a in A:
        off, till = (D(a["start"]) - frm).days, (D(a["data_till"]) - frm).days
        end = (D(a["to"]) - frm).days if a.get("stopped") and a.get("to") else None
        P.append({"a": a, "off": off, "till": till, "end": end, "L": min(len(a["a1"]), (min(end, till) if end is not None else till) - off + 1),
                  "si": (D(a["settled_till"]) - frm).days, "rv": not a.get("currency") or not fc or a["currency"] == fc})
    n = max(p["till"] for p in P) + 1

    def at(p, f, i):
        k = i - p["off"]
        arr = p["a"].get(f) or []
        return _num(arr[k]) if 0 <= k < p["L"] and k < len(arr) else None

    def has(p, i):
        x = at(p, "a1", i)
        return x is not None and x > 0

    if n_err is None:
        n_err = sum(1 for m in F.get("missing") or [] if isinstance(m, dict) and m.get("why") != "no_data"
                    and (vis is None or m.get("app_id") in vis))
    ms = [0.0] * n
    for p in P:
        q = []
        hi = min(p["end"], n - 1) if p["end"] is not None else n - 1
        for i in range(max(0, p["off"]), hi + 1):
            if has(p, i):
                q = (q + [at(p, "a1", i)])[-7:]
            elif q:
                ms[i] += sum(q) / len(q)
    out = {}
    for i in range(n):
        r = dict(nn=n_err, k=0, dau=0, rt=0, rtn=0, rta=0, nw=0, nwn=0, d1n=0, d1d=0, d1c=0, d1p=False, d7n=0, d7d=0, d7c=0, d7p=False,
                 sS=0, sU=0, tT=0, tU=0, rv=0.0, ra=0, rvc=0, prov=False, w1=0, w0=0, wc=0, apps=[])
        for p in P:
            if i >= p["off"] and (p["end"] is None or i <= p["end"]):
                r["nn"] += 1
            if not has(p, i):
                continue
            x, w = at(p, "a1", i), at(p, "new", i)
            r["k"] += 1
            r["dau"] += x
            r["apps"].append(p["a"]["app_id"])
            r["prov"] = r["prov"] or i > p["si"]
            if w is not None:
                r["nw"] += w
                r["nwn"] += 1
            rt = at(p, "ret", i)
            if rt is not None:
                r["rt"] += rt
                r["rtn"] += 1
                r["rta"] += x
            for N, f in ((1, "d1"), (7, "d7")):
                q = at(p, f, i)
                if q is not None and w is not None and w > 0:
                    r[f + "n"] += q
                    r[f + "d"] += w
                    r[f + "c"] += 1
                    r[f + "p"] = r[f + "p"] or i + N > p["si"]
            u = at(p, "u", i)
            if u is not None and u > 0:
                s_, t_ = at(p, "s", i), at(p, "t", i)
                if s_ is not None:
                    r["sS"] += s_
                    r["sU"] += u
                if t_ is not None:
                    r["tT"] += t_
                    r["tU"] += u
            e = at(p, "rev", i) if p["rv"] else None
            if e is not None:
                r["rv"] += e
                r["ra"] += x
                r["rvc"] += 1
            if i >= 7 and has(p, i - 7):
                r["w1"] += x
                r["w0"] += at(p, "a1", i - 7)
                r["wc"] += 1
        r["ms"] = ms[i]
        r["inc"] = ms[i] > 0 and ms[i] >= PF_MISS * (r["dau"] + ms[i]) and r["k"] > 0
        out[(frm + _td(days=i)).isoformat()] = r
    return out, frm.isoformat(), n


def _int(c):
    return int(c.replace(",", "").replace("*", "").replace("†", "").strip())         # († = some app's number left out)


def _dur(c):
    m = re.fullmatch(r"(?:(\d+)h (\d+)m|(\d+)m (\d+)s|(\d+)s)", c)
    assert m, c
    h, hm, mm, ms, ss = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + hm * 60 + mm * 60 + ms + ss


def _chg(c):
    if c == "0%":
        return 0.0
    m = re.fullmatch(r"([+−])([\d.]+)%", c)
    assert m, c
    return (1 if m.group(1) == "+" else -1) * float(m.group(2))


def check_pf_rows(rows_, days, usd_inr=1.0, sym="$"):
    """Every rendered row against the recomputed sums (unknown = "—", never 0)."""
    assert rows_
    for row in rows_:
        r, c = days[row["day"]], row["cells"]
        assert c[1] == "%d of %d" % (r["k"], r["nn"]) + (" ⏸️" if r["inc"] else ""), (row["day"], c[1])
        for j in (2, 3, 4):                                                              # a big app missing: faded, said on the cell
            assert ("act-pfi" in row["cls"][j]) == r["inc"], (row["day"], j)
        if r["inc"]:
            assert row["tips"][2].startswith("≈%d%% of DAU missing — " % max(1, round(100 * r["ms"] / (r["dau"] + r["ms"])))), row["tips"][2]
        assert (c[2] == "—") if not r["k"] else _int(c[2]) == r["dau"], (row["day"], c[2])
        assert (c[3] == "—") if not r["rtn"] else _int(c[3]) == r["rt"], (row["day"], c[3])
        assert row["star"] == (0 < r["rtn"] < r["k"]), row["day"]                          # some app's returning left out: "†"
        assert (c[4] == "—") if not r["nwn"] else _int(c[4]) == r["nw"], (row["day"], c[4])
        for j, N in ((5, "d1"), (6, "d7")):
            if r[N + "c"]:
                assert abs(float(c[j].rstrip("%")) - 100.0 * r[N + "n"] / r[N + "d"]) <= 0.051, (row["day"], N, c[j])
                assert ("act-pfv" in row["cls"][j]) == r[N + "p"], (row["day"], N)      # provisional: faded
            else:
                assert c[j] == "—", (row["day"], N, c[j])
        assert (c[7] == "—") if not r["sU"] else abs(float(c[7]) - r["sS"] / r["sU"]) <= 0.051, (row["day"], c[7])
        assert (c[8] == "—") if not r["tU"] else abs(_dur(c[8]) - r["tT"] / r["tU"]) <= 60, (row["day"], c[8])
        if r["rvc"] and r["ra"]:
            assert c[9].startswith("≈ " + sym) or c[9].startswith(sym), (row["day"], c[9])
            v = float(c[9].replace("≈", "").replace(sym, "").replace(",", "").replace("<", "").strip())
            assert abs(v - 1000.0 * r["rv"] / r["ra"] * usd_inr) <= 0.006 or c[9].startswith("<"), (row["day"], c[9])
        else:
            assert c[9] == "—", (row["day"], c[9])                                        # no ad data: never $0
        if r["wc"] and r["w0"] > 0:
            assert abs(_chg(c[10]) - 100.0 * (r["w1"] / r["w0"] - 1)) <= 0.51, (row["day"], c[10])
            assert "same apps" in row["tips"][10] and ("sirf wo %d apps" % r["wc"]) in row["tips"][10], row["tips"][10]
        else:
            assert c[10] == "—", (row["day"], c[10])
        assert row["prov"] == r["prov"] and row["pill"] == r["prov"], row["day"]


def test_pf_section_sits_after_the_alerts_and_before_the_app_table(report):
    """(review) the open alerts keep their place right under "At a glance"; the long day-by-day card comes after them."""
    s = report["pf"]["s"]["90d"]
    assert s["has"] and "📅 Daily — all apps" in s["text"]
    o = s["order"]
    assert 0 < o[0] < o[1] < o[2] < o[3], o                                            # At a glance · What changed · 📅 · table (no updates card, §6.5)
    assert s["heads"] == ["Date", "Apps with data", "DAU", "Purane users (roz)", "Installs", "Came back next day %", "After a week %",
                          "Sessions/user", "Time/user", "Kamai har 1,000 users se", "vs same day last week"]
    assert report["pf"]["portfolio_30d"]["has"]                                        # the Period (header) never hides it


def test_pf_every_row_matches_the_file(report):
    F = report["pf"]["file"]
    days, frm, n = pf_days(F)
    s = report["pf"]["s"]["all_rows"]
    assert [r["day"] for r in s["rows"]] == sorted(days, reverse=True)                  # whole history, newest first
    check_pf_rows(s["rows"], days)


def test_pf_sums_equal_the_builds_own_total(report):
    """The page's sums (all apps shown) = the engine's `total` in the file, day by day."""
    F = report["pf"]["file"]
    T = F.get("total")
    if report["pf"]["src"] != "fixture" or not isinstance(T, dict):
        pytest.skip("the fixture carries no built portfolio file yet (a stub is rendered)")
    days, frm, n = pf_days(F)
    assert frm == F["from"] and len(T["a1"]) == n
    for t, d in enumerate(sorted(days)):
        r = days[d]
        assert T["n"][t] == r["nn"] and T["k"][t] == r["k"], d
        assert T["a1"][t] == (r["dau"] if r["k"] else None), d
        assert T["new"][t] == (r["nw"] if r["nwn"] else None) and T["ret"][t] == (r["rt"] if r["rtn"] else None), d
        for N in ("d1", "d7"):
            assert T[N][t] == (r[N + "n"] if r[N + "c"] else None) and T[N + "n"][t] == (r[N + "d"] if r[N + "c"] else None), (d, N)
            assert bool(T[N + "p"][t]) == r[N + "p"], (d, N)
        assert bool(T["prov"][t]) == r["prov"], d
        assert (T["wow"][t] is None) == (not (r["wc"] and r["w0"] > 0)), d
        if T["wow"][t] is not None:
            assert abs(T["wow"][t] - (r["w1"] / r["w0"] - 1)) < 1e-3 and T["wk"][t] == r["wc"], d


def test_pf_ranges_default_90_and_chart_points(report):
    F = report["pf"]["file"]
    days, frm, n = pf_days(F)
    S = report["pf"]["s"]
    assert S["90d"]["ranges"] == [["30d", "30 days", False], ["90d", "3 months", True], ["180d", "6 months", False], ["all", "All time", False]]
    for k, N in (("30d", 30), ("90d", 90), ("180d", 180), ("all", n)):
        want = [d for d in sorted(days)[-min(N, n):] if days[d]["k"]]
        pts = S[k]["pts"]
        assert len(pts) == len(want), (k, len(pts), len(want))
        assert [p["v"] for p in pts] == ["{:,} active users".format(days[d]["dau"]) for d in want], k
    assert S["30d"]["ranges"][0][2] and not S["30d"]["ranges"][1][2]


def test_pf_provisional_days_hatched_faded_and_pilled(report):
    F = report["pf"]["file"]
    days, frm, n = pf_days(F)
    s = report["pf"]["s"]["90d"]
    shown = [d for d in sorted(days)[-90:] if days[d]["k"]]
    assert any(days[d]["prov"] for d in shown) and s["hatch"] >= 1 and s["prov_note"]
    assert len(s["pts"]) == len(shown)
    for p, d in zip(s["pts"], shown):                                                   # the hover names the day and says provisional
        assert p["l"].startswith("%s %s" % (_wd(d), _dm(d))) and p["l"].endswith(" · ⏳ pakka nahi") == days[d]["prov"], (d, p["l"])
    assert [r["day"] for r in s["rows"] if r["prov"]] == [d for d in sorted(days, reverse=True)[:14] if days[d]["prov"]]
    assert "⏳ Pakka nahi" in s["lgd"]                                                  # (was "Provisional", SPEC_SIMPLIFY §1.4)


def _wd(d):
    return ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[_date.fromisoformat(d).weekday()]


def _dm(d):
    return day_words(d)


def test_pf_app_count_markers(report, fixture):
    """A new app's first day (and an app that stopped) is marked on the chart and named under it — never read as growth."""
    F = report["pf"]["file"]
    frm = min(a["start"] for a in F["apps"])
    first = sorted({a["start"] for a in F["apps"] if a["start"] > frm})
    stops = sorted({(_date.fromisoformat(a["to"]) + _td(days=1)).isoformat() for a in F["apps"] if a.get("stopped")
                    and a["to"] < max(x["data_till"] for x in F["apps"])})
    s = report["pf"]["s"]["all"]
    assert s["marks"] == sorted(set(first) | set(stops))
    moved = sum(int(x) for t in s["mlabels"] for x in re.findall(r"[+−](\d+)", t))      # close marks share a label, never hide a count
    assert moved == sum(1 for a in F["apps"] if a["start"] > frm) + len(stops), s["mlabels"]
    if isinstance(F.get("marks"), list):                                                 # the build's own marks agree
        assert s["marks"] == sorted(m["day"] for m in F["marks"])
    for d in first:
        apps = [a["app"] for a in F["apps"] if a["start"] == d]
        chip = next(c for c in s["chips"] if c["k"] == "first" and c["day"] == d)
        assert chip["text"].startswith("🆕 + ") and (("%d apps" % len(apps)) in chip["text"] if len(apps) > 2 else all(x in chip["text"] for x in apps))
    # an app late by a day / an app gone stale: named, counted "15 of 16", not a dashed "stopped" line
    late, stale = report["pf"]["s"]["late"], report["pf"]["s"]["stale"]
    assert any(c["k"] == "late" and "not in yet" in c["text"] for c in late["chips"])
    assert any(c["k"] == "stale" and "old data" in c["text"] for c in stale["chips"])
    last = late["rows"][0]
    nn = len(F["apps"])
    assert last["cells"][1] in ("%d of %d" % (nn - 1, nn), "%d of %d ⏸️" % (nn - 1, nn)) and "Not in yet:" in last["tips"][1]
    days, _, _ = pf_days(F)
    shown = [d for d in sorted(days) if days[d]["k"]]
    assert any(days[d]["k"] < days[d]["nn"] for d in shown)                              # the fixture has a day an app has no data
    for p, d in zip(s["pts"], shown):                                                   # … said on hover: "15 of 16 apps"
        assert (" · %d of %d apps" % (days[d]["k"], days[d]["nn"]) in p["l"]) == (days[d]["k"] < days[d]["nn"]), (d, p["l"])
    assert any(c["k"] == "gap" and "no data" in c["text"] for c in s["chips"])


def test_pf_week_over_week_is_same_apps_only(report):
    """An app late on the newest day: the "vs same day last week" % compares only the apps with data on both days."""
    F = report["pf"]["file"]
    s = report["pf"]["s"]["late"]
    lid = next(a for a in F["apps"] if a["app"] == "Demo Old Drop")["app_id"] if any(a["app"] == "Demo Old Drop" for a in F["apps"]) else F["apps"][1]["app_id"]
    F2 = json.loads(json.dumps(F))
    a = next(x for x in F2["apps"] if x["app_id"] == lid)
    for k in ("a1", "new", "ret", "d1", "d7", "u", "s", "t", "rev"):
        a[k] = a[k][:-1]
    a["data_till"] = (_date.fromisoformat(a["data_till"]) - _td(days=1)).isoformat()
    a["settled_till"] = (_date.fromisoformat(a["settled_till"]) - _td(days=1)).isoformat()
    days, _, _ = pf_days(F2)
    check_pf_rows(s["rows"], days)
    r = days[s["rows"][0]["day"]]
    naive_prev = sum(x["a1"][-8] for x in F["apps"] if x["a1"][-8])
    assert r["wc"] == len(F["apps"]) - 1 and abs((r["dau"] / naive_prev - 1) - (r["w1"] / r["w0"] - 1)) > 0.01   # the naive % would read a drop


def test_pf_follows_the_app_filter(report):
    vis = set(report["pf"]["vis"])
    F = report["pf"]["file"]
    days, _, _ = pf_days(F, vis)
    s = report["pf"]["s"]["filter"]
    check_pf_rows(s["rows"], days)
    assert all(int(r["cells"][1].split(" of ")[1].rstrip(" ⏸️")) <= len(vis) for r in s["rows"])
    assert any(re.search(r"\b\d+ of %d apps\b" % len(vis), p) for p in s["pool"])      # the pooled tiles use the same filter
    assert "(%d)" % len(vis) in s["note"]


def test_pf_counts_in_full_past_a_million(report):
    """The owner reads the date-wise DAU day by day: a count past a million shows in full ("1,234,567"), never "1.2M"
    (which reads the same for a month of days)."""
    import copy
    F = copy.deepcopy(report["pf"]["file"])
    for a in F["apps"]:
        for k in ("a1", "new", "ret"):
            a[k] = [v if v is None else v * 1000 for v in a[k]]
    days, _, _ = pf_days(F)
    s = report["pf"]["s"]["big"]
    assert max(r["dau"] for r in days.values()) >= 1_000_000
    check_pf_rows(s["rows"], days)
    bad = [c for r in s["rows"] for c in r["cells"][2:5] if not re.fullmatch(r"—|\d{1,3}(,\d{3})*\s*[*†]?", c)]
    assert not bad, bad[:3]
    assert re.search(r"\d{1,3},\d{3},\d{3} active users \(DAU\)", s["last"]), s["last"]
    assert all(re.fullmatch(r"\d{1,3}(,\d{3})* active users", p["v"]) for p in s["pts"])   # the chart's hover too


def test_pf_money_follows_the_currency_toggle(report):
    F = report["pf"]["file"]
    days, _, _ = pf_days(F)
    check_pf_rows(report["pf"]["s"]["usd"]["rows"], days)
    check_pf_rows(report["pf"]["s"]["inr"]["rows"], days, usd_inr=83.0, sym="₹")


def test_pf_states_and_failure_isolation(report):
    S = report["pf"]["s"]
    assert "⏳ Roz ka data load ho raha hai" in S["loading"]["text"] and not S["loading"]["rows"]
    assert "Roz ka data load nahi hua" in S["error"]["text"] and "Try again" in S["error"]["text"]
    assert not S["noptr"]["has"] and S["noptr"]["order"][2] == -1 and 0 < S["noptr"]["order"][1] < S["noptr"]["order"][3]   # no pointer: no section, the page as before
    assert "Dikhne wali apps ka roz ka data abhi nahi" in S["empty"]["text"]
    assert "ye hissa abhi dikh nahi paya" in S["throw"]["text"] and report["pf"]["throw_rest"]
    assert S["broken"]["has"] and S["broken"]["rows"]                                  # junk values: "—", never NaN (checked for every scenario)
    empty_days = [r for r in S["broken"]["rows"] if r["cells"][1].startswith("0 of")]
    assert empty_days and all(c == "—" for r in empty_days for c in r["cells"][2:]), empty_days   # a day no app has: "—", never 0


def test_pf_refresh_drops_the_file_only_when_its_sig_changes(report):
    R = report["pf"]["refresh"]
    assert R["same"] == {"kept": True, "same_asset_v": True}                            # nothing changed: no re-fetch
    assert R["changed"] == {"kept": False, "same_asset_v": True}                         # its own sig moved (asset_v the same)
    assert R["gone"]["kept"] is False                                                    # no pointer any more: dropped


def test_pf_default_range_is_3_months_and_14_rows(html):
    assert "ACTPFR='90d', ACTPFN=14, ACTPFMK=false;" in html


def test_pf_lazy_file_loads_once_on_all_apps_only(report):
    L = report["pf"]["load"]
    assert L and L["loading"] and len(L["calls"]) == 1 and L["calls"][0].startswith("active_portfolio.json.gz?t=")
    assert L["on_app"] == 0


def test_pf_paging_newest_first(report):
    F = report["pf"]["file"]
    days, _, n = pf_days(F)
    S = report["pf"]["s"]
    newest = sorted(days, reverse=True)
    assert [r["day"] for r in S["90d"]["rows"]] == newest[:14]
    assert S["90d"]["more_calls"] == [30] and S["90d"]["more"].startswith("Show more (30 days)")
    assert [r["day"] for r in S["more"]["rows"]] == newest[:44] and 0 in S["more"]["more_calls"]
    assert len(S["all_rows"]["rows"]) == n and S["all_rows"]["more"].startswith("All %d days" % n)
    assert all(_dm(r["day"]) in r["cells"][0] and _wd(r["day"]) in r["cells"][0] for r in S["all_rows"]["rows"])


def test_pf_phone_width(report):
    S = report["pf"]
    assert S["wide"] == []                                                              # the table scrolls inside its card
    assert S["s"]["90d"]["vbw"] == 520 and S["s"]["desktop"]["vbw"] == 1000            # a narrower drawing on a phone


def test_pf_honesty_notes(report):
    s = report["pf"]["s"]["90d"]
    assert "2 apps pe ho to 2 baar gina" in s["note"] and "same apps" in s["note"]
    assert s["last"].startswith("📅 ") and "(aakhri pakka din)" in s["last"] and "active users (DAU)" in s["last"]   # (no "latest" / "settled", §1.1 / §6.4)
    assert "vs last" in s["last"]
    assert "App count changed" in s["lgd"] or not s["marks"]


# ── (review 2026-09-28) a day's sum that reads low is never shown as a sure drop ─────────────────────────────────────

def _pf_mut_stale(F, app_id, k=6):
    import copy
    F2 = copy.deepcopy(F)
    a = next(x for x in F2["apps"] if x["app_id"] == app_id)
    for f in ("a1", "new", "ret", "d1", "d7", "u", "s", "t", "rev"):
        a[f] = a[f][:-k]
    for f in ("data_till", "settled_till"):
        a[f] = (_date.fromisoformat(a[f]) - _td(days=k)).isoformat()
    a["stale"] = True
    return F2


def _pf_chart_checks(s, days, N):
    """The chart over the last N days: a day a big app's data is missing (inc) — and a provisional day — is never on the
    solid DAU line; it gets a hollow dot; the first day of each such run a "⏸️" mark."""
    shown = [d for d in sorted(days)[-N:] if days[d]["k"]]
    assert len(s["pts"]) == len(shown)
    x = {d: p["x"] for d, p in zip(shown, s["pts"])}
    solid = {v for ln in s["lines"] if ln["s"] == "dau" and ln["f"] == 0 for v in ln["xs"]}
    soft = {v for ln in s["lines"] if ln["s"] == "dau" and ln["f"] == 1 for v in ln["xs"]}
    for d in shown:
        if days[d]["inc"] or days[d]["prov"]:
            assert x[d] not in solid, d
            if len(shown) > 1:
                assert x[d] in soft, d
    inc = [d for d in shown if days[d]["inc"]]
    assert s["inc"] == inc
    runs = [d for j, d in enumerate(shown) if days[d]["inc"] and (j == 0 or not days[shown[j - 1]]["inc"])]
    assert s["gmarks"] == runs
    for p, d in zip(s["pts"], shown):                                                   # the hover says how much is missing
        assert ("% of DAU missing)" in p["l"]) == days[d]["inc"], (d, p["l"])
    if inc:
        assert "⏸️" in "".join(s["mlabels"]) and "App data missing (total low)" in s["lgd"] and "khokhla gola" in s["note"]
    return inc


def test_pf_a_big_app_gone_stale_never_reads_as_a_drop(report):
    """(review, medium) The biggest app goes stale 6 days before the others: those days' sums miss ~its DAU. They are
    faded + dotted on the chart (never a solid settled point), the day it went stale is marked "⏸️", every such row reads
    "15 of 16 ⏸️" (faded, the missing share on the cell) and the latest-day line is the newest settled day WITHOUT a big app
    missing — never the partial sum."""
    F = report["pf"]["file"]
    big = report["pf"]["big"]
    F2 = _pf_mut_stale(F, big)
    days, _, n = pf_days(F2)
    s = report["pf"]["s"]["stalebig"]
    check_pf_rows(s["rows"], days)
    inc = _pf_chart_checks(s, days, 90)
    gone = (_date.fromisoformat(next(a for a in F2["apps"] if a["app_id"] == big)["data_till"]) + _td(days=1)).isoformat()
    assert gone in inc and gone in s["gmarks"]                                           # a mark on the day it went stale
    settled = [d for d in sorted(days) if days[d]["k"] and not days[d]["prov"]]
    assert any(days[d]["inc"] for d in settled)                                          # the drop sits on settled days
    want = [d for d in settled if not days[d]["inc"]][-1]
    assert s["last"].startswith("📅 %s %s " % (_wd(want), _dm(want))), s["last"]
    assert "{:,} active users (DAU)".format(days[want]["dau"]) in s["last"]
    skipped = [d for d in settled if d > want and days[d]["inc"]]
    assert ("⏸️ baad ke %d pakke din me " % len(skipped)) in s["last"] and "isliye ye din" in s["last"]
    assert any(c["k"] == "stale" for c in s["chips"])


def test_pf_a_gap_day_of_a_big_app_is_marked_on_the_chart(report):
    """(review, low) The fixture's one-day gap of a big app (15 of 16, −12%): faded + dotted + "⏸️" on every range and width;
    a tiny app's gap (under 2% of the day) stays a plain "k of n" day."""
    F = report["pf"]["file"]
    days, _, n = pf_days(F)
    assert any(days[d]["inc"] for d in days)
    for k, N in (("30d", 30), ("90d", 90), ("180d", 180), ("all", n), ("desktop", 90)):
        _pf_chart_checks(report["pf"]["s"][k], days, N)
    check_pf_rows(report["pf"]["s"]["all_rows"]["rows"], days)                          # "⏸️" + faded cells exactly on those days


def test_pf_an_app_not_built_counts_in_k_of_n(report):
    """(review, low) An app whose part was not built this run (the file's missing list says "error" — or, a file without
    that list, its summary row is an error) is in n on every day: "15 of 16", like the pooled tiles; named on the cell."""
    import copy
    F = report["pf"]["file"]
    big = report["pf"]["big"]
    name = next(a["app"] for a in F["apps"] if a["app_id"] == big)
    F2 = copy.deepcopy(F)
    F2["apps"] = [a for a in F2["apps"] if a["app_id"] != big]
    F2["missing"] = (F2.get("missing") or []) + [{"app_id": big, "app": name, "why": "error"}]
    days, _, _ = pf_days(F2)
    for k in ("errbig", "errrow"):
        s = report["pf"]["s"][k]
        check_pf_rows(s["rows"], days)
        assert all(r["cells"][1].split(" of ")[1].rstrip(" ⏸️") == str(days[r["day"]]["nn"]) for r in s["rows"])
        assert all(("Not built this time: " + name) in r["tips"][1] for r in s["rows"]), k
        m = re.search(r" · (\d+) of (\d+) apps", s["last"])
        assert m and int(m.group(2)) == int(m.group(1)) + 1, s["last"]
        assert ("Is baar nahi bana" in s["note"]) and name in s["note"]
        pool = [p for p in s["pool"] if re.search(r"\b\d+ of \d+ apps\b", p)]
        assert pool and all(re.search(r"\b\d+ of %s apps\b" % m.group(2), p) for p in pool)   # the same n as the pooled tiles


def test_pf_tracking_check_runs_are_named_and_banded(report):
    """(review, medium) A tracking-check run is a chip ("⚠️ <app> · tracking check · <dates>"), on the hover of its days,
    and — for an app holding >= 2% of the day — an orange band on the chart with a legend entry."""
    F = report["pf"]["file"]
    runs = []
    for a in F["apps"]:
        b = sorted(a.get("brk") or [])
        for d in b:
            if runs and runs[-1][0] == a["app"] and (_date.fromisoformat(d) - _date.fromisoformat(runs[-1][2])).days == 1:
                runs[-1][2] = d
            else:
                runs.append([a["app"], d, d])
    assert runs, "the fixture has a tracking-check day"
    s = report["pf"]["s"]["all"]
    for app, d0, d1 in runs:
        c = [c for c in s["chips"] if c["k"] == "brk" and c["day"] == d0]
        assert c and c[0]["text"].startswith("⚠️ %s · tracking check · " % app), (app, c)
    shown = [d for d in sorted(pf_days(F)[0]) if pf_days(F)[0][d]["k"]]
    for p, d in zip(s["pts"], shown):
        assert ("tracking check: " in p["l"]) == any(d0 <= d <= d1 for _, d0, d1 in runs), (d, p["l"])
    for fr, to in s["brk"]:
        assert any(d0 == fr and d1 == to for _, d0, d1 in runs)
    if s["brk"]:
        assert "Tracking check" in s["lgd"] and "tracking check" in s["note"]
    assert s["brk"], "the fixture's tracking-check app is a big one: banded"


def test_pf_table_repeats_its_column_names_every_block(report):
    """(review, low) After "Show more" the old rows are never 10 unnamed number columns: each 30-day block starts with the
    column names again."""
    s = report["pf"]["s"]["all_rows"]
    days = [r["day"] for r in s["rows"]]
    want = [days[i] for i in range(14, len(days), 30)]
    assert s["rh_after"] == want and s["rh"] == len(want)
    assert report["pf"]["s"]["90d"]["rh"] == 0 and report["pf"]["s"]["more"]["rh"] == 1


def test_pf_footnote_explains_the_star_and_the_marks(report):
    """(review, low) "*" on Returning is explained in the footnote whenever a row shows one; "dotted up-down line" is
    never confused with the dashed Returning line; the revenue column reads like the tile above."""
    S = report["pf"]["s"]
    for k in ("90d", "all_rows", "broken", "stalebig"):
        s = S[k]
        assert any(r["star"] for r in s["rows"]) == ("† (Purane users) = " in s["note"]), k
    assert not any(r["star"] for r in S["broken"]["rows"])
    assert "khadi (upar-neeche) dotted line" in S["90d"]["note"] and "Dashed line wale din" not in S["90d"]["note"]


def test_pf_chips_wrap_on_a_phone(html):
    """(review, low) At <= 430px a chip wraps, so its date is never cut off (its tooltip does not open on touch)."""
    assert any(".act-pfc{white-space:normal}" in b for b in re.findall(r"@media\(max-width:430px\)\{([\s\S]*?)\n  \}", html))


def test_pf_folded_chips_keep_every_chip_of_a_chart_mark(report):
    """(review) Chips are newest first and fold after 8 — but a chip of something drawn on the chart (a big app's
    tracking-check band, a "⏸️" run) is never folded away: a big app's old tracking check behind ten newer one-day gaps of
    a tiny app still shows its chip."""
    s = report["pf"]["s"]["pin"]
    kinds = [c["k"] for c in s["chips"]]
    assert kinds.count("gap") == 8 and kinds.count("brk") == 1 and "first" not in kinds, kinds
    assert all(c["day"] > "2026-01-30" for c in s["chips"] if c["k"] == "gap")          # the newest 8 gaps, not the old solo one
    b = next(c for c in s["chips"] if c["k"] == "brk")
    assert b["text"] == "⚠️ Pin Big · tracking check · %s" % b["text"].split(" · ")[-1] and b["day"] == "2026-01-06"
    assert s["brk"] == [["2026-01-06", "2026-01-11"]] and s["chip_more"] == "+4 more"
    assert not s["inc"] and not s["gmarks"]                                              # a tiny app's gap: no "⏸️" (under 2%)
    solo = next(r for r in s["rows"] if r["day"] == "2025-12-22")                        # no app has data: "—", no "⏸️", not pinned
    assert solo["cells"][1] == "0 of 1" and all(c == "—" for c in solo["cells"][2:10])
