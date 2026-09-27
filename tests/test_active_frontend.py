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
app; the data-edge sentences; English labels with Roman Hinglish only; phone width. Skipped where node is not installed."""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.environ.get("ACTIVE_FE_FIXTURE") or os.path.join(ROOT, "tests", "fixtures", "active_sample.json")
UNI_FIXTURE = os.path.join(ROOT, "tests", "fixtures", "uninstall_sample.json")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
RANK = {"worse": 0, "break": 1, "watch": 2, "slow": 2, "better": 3, "maybe_dn": 4, "maybe_up": 4, "price_dn": 5, "price_up": 5,
        "growth": 6, "normal": 7, "low": 8, "noad": 8, "wait": 9}
TILE_KEYS = ("ret_dau", "d1", "d7", "sess", "time", "arpdau")


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
        assert a["has_titles"] == ["📌 At a glance", "🔔 What changed? (", "📦 Update impact", "When will I know?", "← All apps"], r["app"]
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
        assert a["ctx_text"].startswith("Active users") and "New installs" in a["ctx_text"]
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
        assert "Ads/user" in t["text"] and "eCPM" in t["text"], (r["app"], t["text"])
        if t["big"] != "—":
            assert t["big"].startswith("≈"), (r["app"], t["big"])
        osh = (det(fixture, r).get("flags") or {}).get("other_share")
        assert ("AdMob Network only · other networks ~" in t["text"]) == (osh is not None and osh >= 0.05), r["app"]


def test_ads_dir_chip_is_prefixed(report):
    assert report["syn"]["ads_dir"] == "Ads/user maybe lower"


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
        assert u["base"]["on"] == ["Time per user", "Returning", "7-day average"], (r["app"], u["base"])
        assert u["sess_all"]["on"] == ["Sessions per user", "All users", "7-day average"]
        assert u["time_new_day"]["on"] == ["Time per user", "New installs", "Every day"]
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
    for r in rows(fixture):
        C, a = det(fixture, r).get("changes") or {}, report["apps"][r["app"]]
        op = C.get("open") or []
        assert a["chg_title"] == str(len(op)), r["app"]
        assert sorted(a["chg_rows"]) == sorted(x.get("family") or "" for x in op), r["app"]
        assert a["info_rows"] == [o.get("kind") or "info" for o in C.get("info") or []], r["app"]
        assert a["closed_rows"] == len(C.get("closed") or []) and a["older_rows"] == len(C.get("older") or []), r["app"]
        for cls, lbl in a["sev_pills"]:
            assert (cls, lbl) in (("p-r", "Worse"), ("p-y", "Watch"), ("p-g", "Better"), ("p-b", "Info"))
        for x in op:
            assert x.get("text") and x["text"] in report["texts"]["detail|%s|base" % r["app"]], (r["app"], x.get("text"))


def test_changes_all_normal(report, fixture):
    seen = 0
    for r in rows(fixture):
        op = (det(fixture, r).get("changes") or {}).get("open") or []
        assert report["apps"][r["app"]]["all_normal"] == (not op), r["app"]
        seen += not op
    t = report["portfolio"]
    assert (t["chg_title"] == str(len(fixture["dashboard_active"].get("alerts") or [])))
    assert sorted(t["chg_rows"]) == sorted(x["app_id"] for x in fixture["dashboard_active"].get("alerts") or [])


def test_early_look_row_is_provisional_and_uncounted(report):
    e = report["syn"]["early"]
    assert e["row"] and e["pill"] and not e["counted"]
    assert e["title"] == e["open"]                                    # "What changed? (n)" = open alerts only


def test_pkg_chip_opens_block_in_active(report, fixture):
    imp = report["imp"]
    want = [(r["app"], x["key"]) for r in rows(fixture) for x in det(fixture, r).get("releases") or [] if x.get("key")]
    assert sorted((j["app"], j["key"]) for j in imp["jumps"]) == sorted(want)
    for j in imp["jumps"]:
        assert j["open"] == j["key"] and j["rendered"] == j["key"] and j["jump"] == j["key"] and j["uni_open"] == "", j
    assert all(c["known"] and c["call"] == c["key"] for c in imp["chips"])
    assert all(b["act"] and b["known"] for b in imp["badges"])
    if want:
        assert imp["chips"], "no 📦 chip under any chart"


def test_uniimpgo_act_path_shows_active(report):
    g = report["imp"].get("go")
    if g is None:
        pytest.skip("no app with an update block in the fixture")
    assert g["calls"][0] == "show:active" and g["app"] == g["want"] and g["open"] == g["key"] and g["uni"] == "" and g["screen"]


def test_imp_card_in_active(report, fixture):
    for r in rows(fixture):
        assert report["apps"][r["app"]]["imp_card"], r["app"]
    for b in report["imp"]["blocks"]:
        assert b["n_open"] == 1 and b["open_key"] == b["key"] and b["id_act"] and not b["id_uni"], b
        assert b["rows"] == 9, b                                          # 7 rows + the 2 version rows
        assert b["acts"] and all("'act')" in c for c in b["acts"]), b["acts"][:5]


def test_no_duplicate_ids_across_tabs(report, fixture):
    assert len(report["ids"]) == len([r for r in rows(fixture) if det(fixture, r)])
    for x in report["ids"]:
        assert x["dup_uni"] == [] and x["dup_act"] == [] and x["shared"] == [], x
        assert x["act_not_prefixed"] == [], x                            # every id in the tab starts with act-


def test_alerts_screen_active_section(report, fixture):
    AL = fixture["dashboard_active"].get("alerts") or []
    A = report["alerts"]
    assert A["all"]["cards"] == len(AL) and A["all"]["sub"] == bool(AL) and A["all"]["chip"] == bool(AL)
    assert sorted(A["all"]["open_app"]) == sorted(x["app_id"] for x in AL)
    assert sorted(map(tuple, A["all"]["upd"])) == sorted((x["app_id"], x["release"]["key"]) for x in AL if (x.get("release") or {}).get("key"))
    for r in rows(fixture):
        n = sum(1 for x in AL if x["app"] == r["app"])
        p = A["per_app"][r["app"]]
        assert p["cards"] == n and p["sub"] == bool(n) and p["chip"] == bool(n), r["app"]
    assert A["no_active"]["cards"] == 0 and not A["no_active"]["sub"] and not A["no_active"]["chip"]
    assert "GA4 not connected" in A["no_active_tab"]


def test_portfolio_chips_open_exact_apps(report, fixture):
    xp = report["portfolio"]["xp"]
    assert not xp["default_open"]                                         # no app list by default
    for k in TILE_KEYS:
        want = {}
        for r in rows(fixture):
            want.setdefault(st((r.get("m") or {}).get(k)), []).append(r["app"])
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
    assert c.startswith("⚠️ %d app" % K["worse"]) and "🟡 %d watch" % K["watch"] in c and "✅ %d normal" % K["ok"] in c and "ℹ️ %d not enough data" % K["wait"] in c


def test_portfolio_recent_updates(report, fixture):
    u = report["portfolio"]["updates"]
    assert u["has"]
    ids = {r["app_id"] for r in rows(fixture)}
    assert all(act and app in ids for app, _, act in u["rows"])
    assert u["uf"] and all(u["uf"])
    n = sum(len(x.get("updates") or []) for x in fixture["dashboard_uninstall"]["apps"] if x["app_id"] in ids)
    assert len(u["rows"]) == min(n, 10)


def test_portfolio_table_sort(report, fixture):
    R = {r["app"]: r for r in rows(fixture)}
    col = {"ret": ("ret_dau", "v"), "rel": ("ret_dau", "rel"), "d1": ("d1", "v"), "d7": ("d7", "v"), "sess": ("sess", "v"), "time": ("time", "v"), "rev": ("arpdau", "v")}
    heads = [k for k, _ in report["portfolio"]["table_heads"]]
    assert heads == ["app", "ret", "rel", "d1", "d7", "sess", "time", "rev", "status"]
    assert [l for _, l in report["portfolio"]["table_heads"]] == ["App", "Returning/day", "vs 4 wks", "Next day", "After a week", "Sessions/user", "Time/user", "Rev/1k users", "Status"]
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
    tot = 0
    for r in rows(fixture):
        n = len((det(fixture, r).get("changes") or {}).get("older") or [])
        assert report["apps"][r["app"]]["older_rows"] == n
        tot += n
    assert report["portfolio"]["older_open"] == tot                      # All apps: every loaded app's, none capped
    assert report["portfolio"]["older_nofiles"]


def test_prov_and_est_marks(report, fixture):
    for r in rows(fixture):
        d, a = det(fixture, r), report["apps"][r["app"]]
        L = d.get("latest") or {}
        if L.get("day"):
            assert a["latest"].startswith("Latest GA4 day") and a["latest_prov"] == (L.get("prov") is not False), r["app"]
        assert a["prov_note"] == bool(d.get("settled_till") and d.get("data_till") and d["settled_till"] < d["data_till"]), r["app"]
        assert "Provisional" in a["kpis_today"], r["app"]                     # "Today" = the newest GA4 day: provisional
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


def test_edge_states_render(report, fixture):
    for r in rows(fixture):
        E = det(fixture, r).get("edges") or {}
        assert report["apps"][r["app"]]["edges"] == [t for t in E.get("text") or [] if t], r["app"]
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


CHIPS = {"ret_dau": {"worse": "Lower", "watch": "Lower · watch", "slow": "Slowly falling", "break": "Check tracking", "better": "Higher",
                     "maybe_dn": "Maybe lower", "maybe_up": "Maybe higher", "normal": "Normal"},
         "d": {"worse": "Fewer came back", "watch": "Fewer · watch", "better": "More came back", "maybe_dn": "Maybe fewer", "maybe_up": "Maybe more",
               "normal": "Same"},
         "sess": {"worse": "Fewer sessions", "watch": "Less · watch", "better": "More sessions", "maybe_dn": "Maybe less", "maybe_up": "Maybe more",
                  "normal": "Normal"},
         "time": {"worse": "Less time", "watch": "Less · watch", "better": "More time", "maybe_dn": "Maybe less", "maybe_up": "Maybe more",
                  "normal": "Normal"},
         "arpdau": {"worse": "Lower (fewer ads per user)", "watch": "Lower · watch", "better": "Higher", "maybe_dn": "Maybe lower",
                    "maybe_up": "Maybe higher", "normal": "Normal", "price_dn": "Ad price lower", "price_up": "Ad price higher"}}
COMMON = {"low": "Not enough data", "noad": "No ad data", "wait": "Waiting for data"}


def chip_label(k, M):
    """The §4.3 chip vocabulary: one set for tiles, strips and the table."""
    s_ = st(M)
    if s_ == "growth":
        rel = (M or {}).get("rel")
        return "Shrinking fast" if rel is not None and rel < 0 else "Growing fast" if rel is not None and rel > 0 else "Growing / shrinking fast"
    if s_ in COMMON:
        return COMMON[s_]
    t = CHIPS["d" if k in ("d1", "d7") else k].get(s_) or CHIPS["ret_dau"].get(s_, "Normal")
    if k == "arpdau" and (M or {}).get("why") == "ads_dir" and s_ in ("maybe_dn", "maybe_up", "watch", "better"):
        t = "Ads/user " + t[0].lower() + t[1:]
    return t


def test_chip_vocabulary(report, fixture):
    for r in rows(fixture):
        tiles = (det(fixture, r).get("tiles") or {})
        for t in report["apps"][r["app"]]["tiles"]:
            assert t["chip"] == chip_label(t["m"], tiles.get(t["m"])), (r["app"], t["m"], t["chip"])
    for key, c in report["portfolio"]["xp"]["chips"].items():
        k, s_ = key.split(":")
        want = "Growing / shrinking fast" if s_ == "growth" else chip_label(k, {"st": s_})
        assert c["label"] == want, (key, c["label"])


# ── review fixes ────────────────────────────────────────────────────────────────────────────────

def test_market_lines_count_moved_of_total_and_old_weeks_are_past(report):
    fx = report["fix"]
    assert "eCPM down −10% in 13 of 15 apps" in fx["rev_market"], fx["rev_market"]       # of (moved) of apps (total)
    assert fx["pf_market_now"].startswith("💱 Market-wide: is hafte 15 me se 13 apps ka eCPM −10%")
    assert "kam dikhega, app ki galti nahi" in fx["pf_market_now"]
    old = fx["pf_market_old"]                                                            # a month-old week: past tense
    assert "is hafte" not in old and "dikhega" not in old and old.endswith("tha (ab ka nahi).") and "15 me se 13" in old


def test_install_part_keeps_its_sign(report):
    fx = report["fix"]
    assert "installs ne ~5.7 pts ghataya, warna ~+13% ≈" in fx["inst_opp"] and "about" not in fx["inst_opp"]
    assert "isme ~8 pts naye installs ki wajah se, purane users ~−4% ≈" in fx["inst_same"]
    assert "Installs +5% vs 4 weeks" in fx["inst_zero"] and "pts" not in fx["inst_zero"].split("Installs +5% vs 4 weeks")[1][:20]


def test_alert_hint_follows_the_metric(report):
    fx = report["fix"]
    assert "💡 Har user ko kam ads — ad load / fill / mediation" in fx["hint_ads"] and "Purane users" not in fx["hint_ads"]
    assert "💡 Purane users dheere dheere kam" in fx["hint_ret"]


def test_a_linked_alert_is_one_story_with_the_update_card(report):
    fx = report["fix"]
    assert "📦 Yahi badlaav v1.2 ke Update impact card me bhi hai" in fx["linked"]
    assert fx["total_unlinked"] is not None and fx["total_linked"] is not None
    assert int(fx["total_linked"]) == int(fx["total_unlinked"]) - 1                     # counted once (by Uninstall)


def test_waiting_metrics_say_why_on_the_all_apps_page(report):
    fx = report["fix"]
    by = {t["m"]: t["text"] for t in fx["pool_wait"]}
    for k in ("d1", "d7"):
        assert "Wapsi (D1/D7) ka data agle GA4 fetch ke saath aayega" in by[k] and " of " not in by[k]
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
