"""The Install value tab's additions (SPEC_CD_GEO), rendered for real: tests/value_cd_frontend.js runs the page's own script
in a node vm on the committed synthetic fixture (tests/fixtures/value_sample.json) and makes up every new state from the
addendum's contract — 🌍 Google Ads cost by country (G: the cost columns only when every window week is covered, the
reason when not, "No ads here", money back seen / ≈ / "Over 1 year", the small and "Other / unmapped" lines, ₹ back per
₹100, the Keep / Costly tile), 🧬 new users by app version (C: states, "in N days" / "31*" / few / No data cells, chips
coloured only with an open alert, a row / card opened, the 📦 links both ways, the Alerts-screen card) and 🗓️ long-term
by install month (D: states, year rows, "in N days" / No data / few cells, ≈ projections, quarters, the 18 months | All
toggle, phone columns). Old files (by_version / long arrays) draw nothing. One test per must-have (the CF: / GF: ids of
SPEC_CD_GEO §C.10, §D.8, §G.13); tests/test_value_frontend.py and tests/value_frontend.js are not edited. Skipped where
node is not installed."""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.environ.get("VALUE_FE_FIXTURE") or os.path.join(ROOT, "tests", "fixtures", "value_sample.json")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
IN_DAYS = re.compile(r"^in \d+ days?$")


@pytest.fixture(scope="module")
def html():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def report(html, tmp_path_factory):
    if not os.path.exists(FIXTURE):
        pytest.skip("tests/fixtures/value_sample.json not generated yet")
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    path = str(tmp_path_factory.mktemp("fe") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "value_cd_frontend.js"), path, FIXTURE],
                         check=True, capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout)


def rows_by_ver(v):
    return {x["ver"]: x for x in v["rows"]}


def months(lg):
    return [x for x in lg["rows"] if "key" in x]


# ── shared ────────────────────────────────────────────────────────────────────────────────────

def test_every_new_state_renders_without_errors(report):
    assert report["errors"] == [] and report["bad"] == [] and report["tokens"] == []
    assert report["scenarios"] >= 60


def test_english_labels_roman_hinglish_never_coloured(report):
    assert report["jargon"] == [] and report["devanagari"] == []
    assert report["coloured"] == []                                                  # no red / green numbers anywhere


def test_ids_prefixed_and_unique(report):
    assert report["ids"] and all(not i["dup"] and not i["bad"] for i in report["ids"]), [i for i in report["ids"] if i["dup"] or i["bad"]][:3]


def test_phone_width_nothing_scrolls_the_page(report):
    assert report["wide"] == []


def test_sections_in_order_and_countries_slice_unchanged(report):
    """🧬 and 🗓️ sit between 🌍 Countries and 🔍 Data check; the Countries slice the existing harness reads (rows, verdicts,
    few badges, rest lines, notes, strip) and the money-back table are the same with C / D on as off."""
    p = report["page"]
    for k in ("phone", "desk"):
        assert all(i > 0 for i in p[k]) and p[k] == sorted(p[k]), (k, p[k])
    assert p["off"][4] == -1 and p["off"][5] == -1 and p["off_has"] == []
    assert p["titles"] == ["🧬 Users by app version", "🗓️ Long-term by install month"]   # (no word "New", SPEC_SIMPLIFY §9 check 1)
    assert p["slice_same_desk"] and p["slice_same_phone"] and p["pay_same"]
    assert p["slice_off"]["rows"] and p["slice_off"]["heads"][0] == "Country"


def test_fixture_pages_follow_the_contract(report):
    """The committed fixture as it is: before C / D (arrays) the new sections are absent; once the build writes them
    (consts.cd) every app page carries them in order, and nothing on them is undefined / Devanagari / a raw token."""
    fx = report["fixture"]
    for app, a in fx["apps"].items():
        assert not a["bad"] and not a["deva"] and not a["jargon"] and not a["tokens"], app
        for o in (a["order"], a["order_phone"]):
            got = [i for i in o if i >= 0]
            assert got == sorted(got), app
        has_v, has_l = a["bv"] not in ("array", "None", "undefined"), a["long"] not in ("array", "None", "undefined")
        assert (a["order"][4] > 0) == has_v and (a["order"][5] > 0) == has_l, app
        if not fx["cd"]:
            assert not has_v and not has_l, app


# ── 🌍 G: Google Ads cost by country ──────────────────────────────────────────────────────────

def test_geo_cost_columns_only_when_ok(report):
    g = report["geo"]
    cost = ["Cost per install", "Money back in"]
    assert all(h in g["ok|desk"]["heads"] for h in cost) and g["ok|desk"]["minw"] == "1060"
    for w in ("cov", "wait", "nostore", "noads"):
        assert not any(h in g[w + "|desk"]["heads"] for h in cost), w
        assert g[w + "|desk"]["minw"] == "880", w
        assert all(r["verdict"] not in ("keep", "slow", "costly") for r in g[w + "|desk"]["rows"]), w   # never mixed
        assert all("cost per install" not in m for _, m in g[w + "|phone"]["cards"]), w
    assert all(r["verdict"] in ("keep", "slow", "costly", "avg", "watch", "worse", "better", "few", "wait") for r in g["ok|desk"]["rows"])


def test_geo_why_notes(report):
    g = report["geo"]
    assert g["ok|desk"]["notes"] == []
    want = {"cov": "poora nahi mila — country cost nahi dikhaya (faisla bina cost ke)", "wait": "kharcha abhi", "nostore": "account ka country-wise data nahi mila",
            "noads": "Google Ads kharcha nahi — country ka cost nahi"}
    for w, t in want.items():
        n = g[w + "|desk"]["notes"]
        assert [i for i, _ in n] == ["val-geowhy"] and t in n[0][1], (w, n)                # never the "not available" note with C.geo on
    assert re.search(r"tak aaya — naye hafton ka country cost aane pe dikhega", g["wait|desk"]["notes"][0][1])


def test_geo_noads_chip(report):
    g = report["geo"]
    no = [r for r in g["ok|desk"]["rows"] if r["cells"][-3] == "No ads here"]
    assert len(no) == 1 and no[0]["cells"][-2] == "—" and no[0]["verdict"] == "avg"   # the no-cost verdict, never "cheapest"
    assert ["No ads here", "Is country me Google Ads kharcha nahi — yahan ke installs organic", True] in g["tips"]
    assert any(m.endswith("· No ads here") for _, m in g["ok|phone"]["cards"])


def test_geo_money_back_obs_has_no_approx(report):
    g = report["geo"]
    pays = [r["cells"][-2] for r in g["ok|desk"]["rows"]]
    assert "34 days" in pays and "≈61 days" in pays and "Over 1 year" in pays       # seen · ≈ projected · never
    tips = {t: tip for t, tip, _ in g["tips"]}
    assert tips["34 days"].startswith("Dikh chuka") and tips["≈61 days"] == "andaza 48–80 din"
    assert any("Money back 34 days" in m for _, m in g["ok|phone"]["cards"]) and any("Money back ≈61 days" in m for _, m in g["ok|phone"]["cards"])
    assert any(m.endswith("Money back: over 1 year") for _, m in g["ok|phone"]["cards"])
    assert g["ok|desk"]["all"][-3].startswith("$") and g["ok|desk"]["all"][-2] == "—"   # the app's own cost per install


def test_geo_rest_lines_small_and_unmapped(report):
    g = report["geo"]
    rest = g["ok|desk"]["rest"]
    # its share of the ads cost, and per Google Ads install (its installs are mostly organic: per install it looks cheap)
    assert any(re.fullmatch(r"Other small countries \(7\) — 4,471 installs, Google Ads \$\d+ \(3\.8% of ads cost, ≈\$0\.\d+ per "
                            r"Google Ads install\), not judged", x) for x in rest), rest
    assert any(re.fullmatch(r"Google Ads: \$\d+ kisi country se match nahi hua \(Other / unmapped\)", x) for x in rest), rest
    assert not any("Other / unmapped" in x for x in g["small_unmapped"]["rest"])      # ≤ 0.5% of the cost: not said
    assert not any("Google Ads" in x for x in g["cov|desk"]["rest"])                 # cost not shown → no cost lines
    assert any("₹" in x for x in g["ok|inr"]["rest"])


def test_geo_expand_back_per_100_and_cpi_spark(report):
    g = report["geo"]
    o = g["ok|open_desk"]["open"]
    assert re.search(r"Cost per install \$0\.024 \(sirf ads wale \$0\.031 · [\d,]+ Google Ads downloads\) · paisa wapas ≈61 days", o)
    assert "Ads se ~77% installs" in o and re.search(r"\$100 ke ads pe 7 din me \$\d+, 30 din me \$\d+ wapas, 90 din me ≈\$\d+", o)
    assert "Cost per install (12 weeks)" in o and g["ok|open_desk"]["open_sparks"] == 3
    assert "Cost per install" in g["ok|open_phone"]["open_phone"]


def test_geo_tile_keep_costly(report):
    t = report["geo"]["tile"]
    assert t["big"].startswith("✅ Keep: ") and "💸 Costly: " in t["sub"] and re.search(r"\d+ of \d+ countries judged", t["sub"])
    assert report["geo"]["ok|desk"]["strip"].startswith("✅ Keep:") and "💸 Costly:" in report["geo"]["ok|desk"]["strip"]


def test_geo_cost_alert_also_fewer_came_back(report):
    c = [x for x in report["chg"]["app"] if x["fam"] == "geo_cost"]
    assert c and "Saath me: kam log wapas aaye" in c[0]["t"] and c[0]["call"] == "valJump('val-cty')"
    a = [x for x in report["alerts"]["cards"] if x["title"].startswith("💸 Country ads costly")]
    assert a and a[0]["title"].endswith("· also fewer came back")


# ── 🧬 C: new users by app version ────────────────────────────────────────────────────────────

def test_version_section_states(report):
    v = report["ver"]
    assert v["desk"]["heads"] == ["Version", "Installs", "Next day", "After a week", "After 30 days", "Earning per install", "vs previous version", "Verdict"]
    assert v["desk"]["lead"].startswith("v2.2 (14,000 installs)") and v["desk"]["table"] and not v["desk"]["cardsbox"]
    for st, t in (("nosplit", "GA4 is app ke naye users ka version alag nahi deta"), ("nodata", "⏳ Version-wise data aa raha."),
                  ("low", "Kisi version pe 100+ installs nahi"), ("error", "⚠️ Ye hissa abhi dikh nahi paya."), ("unknown", "⏳ Version-wise data aa raha.")):
        x = v["state|" + st]
        assert x["empty"].startswith(t) and not x["rows"] and not x["cards"] and x["id"], st
    s = v["state|single"]
    assert s["empty"].startswith("Abhi ek hi version (v2.3)") and [c["ver"] for c in s["cards"]] == ["2.3"]
    f = v["desk"]["foot"]
    assert f[0] == "Version = install ke din ka version; baad me update karne wale bhi isi me gine."
    assert "Rollout ke 3 din (jab koi ek version 80%+ naye users pe nahi tha) gine nahi — 410 installs." in f
    assert any(x.startswith("Tulna: naye version ke pehle 28 din ke installs vs pichhle version ke aakhri 28 din") for x in f)
    assert "Short-lived versions (1) — 80 installs" in v["desk"]["more"] and "Older versions (2)" in v["desk"]["more"]


def test_version_rows_newest_first_and_older_fold(report):
    v = report["ver"]
    assert [x["ver"] for x in v["desk"]["rows"]] == ["2.3", "2.2", "2.1", "2.0", "1.9", "1.8", "1.7", "1.6"]   # 8 newest by first day
    assert [x["ver"] for x in v["older"]["rows"]][-2:] == ["1.5", "1.4.2"] and v["desk"]["fold"]
    oo = v["open_old"]                                                               # a row opened in the fold unfolds it
    assert len(oo["rows"]) == 10 and [x["ver"] for x in oo["rows"] if x["on"]] == ["1.4.2"]
    assert all(x["call"] == x["ver"] for x in v["desk"]["rows"])


def test_version_cells_wait_part_few(report):
    R = rows_by_ver(report["ver"]["desk"])
    new = R["2.3"]["cells"]
    assert new[2] == "31⏳ of 100" and IN_DAYS.match(new[3]) and IN_DAYS.match(new[4])   # never a small number
    assert any("3 of 5 din ke installs itne purane" in t for t in R["2.3"]["titles"])
    assert new[5].startswith("$0.0043⏳") and "in 3 days" in new[5]                # (⏳ = not all days in: SPEC_SIMPLIFY §1.4)
    assert R["2.2"]["cells"][4] == "4.9⏳ of 100"
    assert R["1.9"]["few"] and R["1.9"]["chip"] == ["p-b", "few", "⏳ Abhi jaldi · installs kam"]   # (the six words, §6.4)
    assert any("Sirf 66 users wapas aaye" in t for t in R["1.9"]["titles"])
    assert R["1.8"]["cells"][2] == "≈30 of 100" and R["1.8"]["cells"][4] == "No data"
    assert R["2.0"]["cells"][5].startswith("≈$0.0042")                                 # an estimate is ≈
    assert R["2.2"]["cells"][6] == "agle din 100 me −4.7 · 7 din baad 100 me −2.3 vs v2.1"       # grey words, never a colour
    assert R["2.3"]["cells"][6] == "wait vs v2.2" and R["1.9"]["cells"][6] == "—"


def test_version_chip_colours_only_with_alert(report):
    v = report["ver"]
    R = rows_by_ver(v["desk"])
    assert R["2.2"]["chip"] == ["uni-pz", "worse", "🔴 Bigda"] and R["2.0"]["chip"] == ["uni-pz", "better", "🟢 Behtar"]   # (§1.8 / §6.4 words)
    assert R["2.1"]["chip"] == ["uni-pz", "same", "⚪ Normal"] and R["2.3"]["chip"] == ["p-b", "wait", "⏳ Abhi jaldi"]
    for k, want, ver in (("watch", ["p-y", "watch", "🟡 Dhyan do"], 1), ("warn", ["p-r", "worse", "🔴 Bigda"], 1), ("good", ["p-g", "better", "🟢 Behtar"], 3)):
        a = v["alert|" + k]
        for side in ("desk", "phone"):
            assert a[side][ver] == want, (k, side)
            assert [c for i, c in enumerate(a[side]) if c[0] in ("p-r", "p-y", "p-g") and i != ver] == [], (k, side)
    assert all(c[0] not in ("p-r", "p-y", "p-g") for c in [x["chip"] for x in v["alert_closed"]["rows"]])   # a closed alert: neutral again


def test_version_row_opens_and_update_chip(report):
    v = report["ver"]
    R = rows_by_ver(v["open_desk"])
    assert R["2.2"]["on"] and R["2.2"]["id"] and sum(x["on"] for x in v["open_desk"]["rows"]) == 1
    o = v["open_desk"]["open"]
    assert "naye users kam ruk rahe" in o and "Next day 27 of 100 (26–28)" in o
    assert "v2.2 vs v2.1: next day 27 vs 32" in o and "Beech ka chhota update v2.1.1 tulna me nahi liya" in o
    assert re.search(r"Tulna: v2\.1 ke installs .+ \(14,000\) vs v2\.2 ke .+ \(9,000\) — dono same umar pe", o)
    rel = v["open_desk"]["open_rel"]
    assert len(rel) == 1 and rel[0][1].startswith("ver:2.2@") and rel[0][2].endswith("Update impact →")
    j = report["jumps"]
    assert j["toggles"] == {"c1": "2.2", "c2": "", "o1": True, "l1": "all", "l2": "18"}
    assert j["ver"]["calls"][0] == "value" and j["ver"]["open"] == "2.2" and j["ver"]["jump"] == "val-ver"
    assert j["back"] == {"open": "", "old": False, "app": ""} and j["ver"]["vapp"]


def test_version_link_without_a_row_is_said(report):
    """A 🧬 link (Update impact → valVerGo) to a version with no row of its own — a rollout, or too few new users — says
    so on that app's section (desktop and phone) instead of a table without it; a version with a row, or another
    app's page, has no such note."""
    v = report["ver"]
    for k in ("link_norow", "link_norow_phone"):
        t = v[k]["vnone"]
        assert t.startswith("ℹ️ v9.9 ki alag row nahi — is version pe kisi din 80%+ naye users nahi aaye (rollout), ya 100 se"), t
        assert v[k]["rows"] or v[k]["cards"]                              # the table / cards are still there
    assert v["link_row"]["vnone"] == "" and v["link_other_app"]["vnone"] == "" and v["desk"]["vnone"] == ""


def test_version_phone_cards(report):
    v = report["ver"]
    assert v["phone"]["cardsbox"] and not v["phone"]["table"]
    C = {c["ver"]: c for c in v["phone"]["cards"]}
    assert list(C) == ["2.3", "2.2", "2.1", "2.0", "1.9", "1.8", "1.7", "1.6"]
    assert re.fullmatch(r"📦 v2\.2 · .+ · 14,000 installs", C["2.2"]["h"])
    assert C["2.2"]["m"] == "27 of 100 next day (pichhla 32) · $0.021⏳ per install (30 d)"
    assert C["2.3"]["m"].endswith("30-day earning: in 26 days") and C["1.8"]["m"].endswith("30-day earning: No data")
    assert C["1.9"]["chip"] == ["p-b", "few", "⏳ Abhi jaldi · installs kam"]
    op = [c for c in v["open_phone"]["cards"] if c["open"]]
    assert len(op) == 1 and op[0]["ver"] == "2.2" and "naye users kam ruk rahe" in op[0]["detail"]


def test_impact_block_links_version_when_cd_on(report):
    i = report["imp"]
    for k in ("on_act", "on_uni"):
        assert i[k]["text"] == "🧬 Users of v2.2 — 30 din tak kitne ruke, kitna kamaya →", k   # the newest version of the block
        assert i[k]["call"][1] == "2.2" and i[k]["call"][0].startswith("ca-app-pub-")
    for k in ("closed", "cd_off", "no_value", "other_app", "update_kind"):
        assert i[k]["link"] is None, k
    assert i["cd_off"]["len"] == i["no_value"]["len"] == i["other_app"]["len"]        # nothing else moves
    assert i["base_same"]


def test_money_back_rel_row_links_version(report):
    r = report["rel"]
    assert [c["cell"] != "" for c in r["has"]["desk"]] == [True] and [c["cell"] != "" for c in r["has"]["phone"]] == [True]
    assert r["has"]["calls"] == [["2.2", "Users of v2.2 →"]] * 2
    assert all(c["cell"] == "" for c in r["missing"]["desk"] + r["missing"]["phone"]) and r["missing"]["calls"] == []
    assert all(c["cell"] == "" for c in r["no_cd"]["desk"])                            # an old file: the cell stays empty


def test_alerts_screen_ver_ret_card(report):
    cards = [c for c in report["alerts"]["cards"] if c["title"].startswith("💸 Users by version")]
    assert [c["sev"] for c in cards] == ["watch", "warning", "good"]
    assert cards[0]["title"] == "💸 Users by version — v2.2 · came back next day"
    assert cards[1]["title"] == "💸 Users by version — v2.2 · came back after a week"
    assert cards[0]["btns"][0][0].startswith("valVerGo(") and cards[0]["btns"][0][0].endswith(",'2.2')")
    assert cards[0]["btns"][1][1] == "Update detail →" and "uniImpGo(" in cards[0]["btns"][1][0]
    assert "naye users kam ruk rahe" in cards[0]["cause"] and "zyada ruk rahe" in cards[2]["cause"]
    assert not report["alerts"]["sub"] and len(report["alerts"]["screen"]) == 0     # the Alerts screen: ad units only (§7)
    rows = [x for x in report["chg"]["app"] if x["fam"] == "ver_ret"]
    assert rows and all(x["call"].startswith("valVerJump(") for x in rows) and all(re.search(r"v2\.\d ke baad", x["t"]) for x in rows)   # (🧬 vX → the Shuru cell, §6.4)
    allr = [x for x in report["chg"]["all"] if x["fam"] == "ver_ret"]
    assert allr and all(x["call"].startswith("valVerGo(") for x in allr)
    assert ["ver_d30", "valJump('val-ver')"] in report["chg"]["info"] and ["ver_mix", "valJump('val-ver')"] in report["chg"]["info"]


def test_old_array_by_version_renders_nothing(report):
    assert report["old"]["arrays"] == ["", "", ""]                                   # 🧬, 🗓️ and the 📦 → 🧬 link: not a byte
    assert report["old"]["missing"] == ["", ""]
    assert report["page"]["off_has"] == [] and report["page"]["off"][4] == -1


# ── 🗓️ D: long-term by install month ──────────────────────────────────────────────────────────

def test_long_section_states(report):
    L = report["long"]
    assert L["desk"]["heads"] == ["Installed in", "Installs", "Day 30", "Day 60 (2 mo)", "Day 90 (3 mo)", "Day 180 (6 mo)", "Day 365 (1 yr)", "Earning per install", "1 yr per $100"]
    assert L["desk"]["lead"].startswith("Jun 2026 ke installs: 90 din baad 100 me se")
    # each normal names its own months (the ages compare with different months) — never one span over all of them
    assert L["desk"]["base"] == ("Normal: Day 60 ~7 of 100 (pichhle 6 mahine, Jan–Jun 2026) · Day 90 ~5.9 of 100 (pichhle 6 "
                                 "mahine, Dec 2025–May 2026) · 6 mahine ki kamai ~$0.045 per install (pichhle 5 mahine, Aug–Dec 2025)")
    assert L["fix"]["base"].startswith("Normal (pichhle 6 mahine, Jan–Jun 2026): Day 60 ~7 of 100 · Day 90 ~7 of 100")   # shared: once
    for st, t in (("low", "Is app me mahine ke install kam"), ("error", "⚠️ Ye hissa abhi dikh nahi paya."), ("unknown", "⏳ Mahine-wise data aa raha.")):
        assert L["state|" + st]["empty"].startswith(t) and not months(L["state|" + st]) and L["state|" + st]["id"], st
    y = L["state|young"]
    assert y["empty"].startswith("⏳ Abhi koi mahina 60 din purana nahi") and len(months(y)) == 2
    f = L["desk"]["foot"]
    assert f[0] == "Day 60 = install ke 60ve din app kholne wale, 100 naye users me se (Firebase jaisa base)." and "Kamai = AdMob ki kamai (sab networks), install ke din se, ek install pe." in f
    assert "Mahine ka 90 din wala number mahina khatam hone ke ~95 din baad; 1 saal wala ~370 din baad." in f


def test_long_year_separator_and_labels(report):
    rows = report["long"]["all"]["rows"]
    yrs = [x["yr"] for x in rows if "yr" in x]
    assert yrs == sorted(set(yrs), reverse=True) and len(yrs) >= 2
    cur = None
    for x in rows:                                                                   # a year row wherever the year changes
        if "yr" in x:
            cur = x["yr"]
            assert x["t"] == "── %s ──" % cur
        else:
            assert cur and cur in x["label"], x["label"]                             # every label writes its year
            assert re.match(r"^[A-Z][a-z]{2} \d{4}", x["label"])
    keys = [x["key"] for x in months(report["long"]["all"])]
    assert keys == sorted(keys, reverse=True) and len(keys) == 20


def test_long_wait_nodata_few_cells(report):
    M = months(report["long"]["desk"])
    newest = M[0]["cells"]
    assert all(IN_DAYS.match(c) for c in newest[2:7]) and newest[7] == "in 14 days"   # a month is complete at t, or "in N days"
    for x in M:
        seen_wait = False
        for c in x["cells"][2:7]:                                                    # never a later age filled while an earlier waits
            if IN_DAYS.match(c):
                seen_wait = True
            else:
                assert not seen_wait or c in ("No data",), (x["key"], x["cells"])
    A = months(report["long"]["all"])
    last = A[-1]
    assert last["cells"][6] == "No data" and last["part_tip"] and "poora data me nahi" in last["part_tip"] and last["label"].split()[1].endswith("⏳")
    few = [x for x in M if any("Sirf 8 users wapas" in t for t in x["titles"])]
    assert len(few) == 1
    assert any(x["cells"][2].startswith("≈") for x in M)                             # a GA4 day not whole: ≈


def test_long_projection_marked(report):
    M = months(report["long"]["desk"])
    proj = [x for x in M if x["proj"]]
    assert proj and all("≈" in x["cells"][7] for x in proj)
    assert any(t.startswith("Andaza — is app ke purane mahino ki kamai ki chaal se") for x in proj for t in x["titles"])
    done = [x for x in M if not x["proj"] and not IN_DAYS.match(x["cells"][7])]
    assert done and all("≈" not in x["cells"][7] for x in done)                     # seen earning: no ≈
    b = [x["cells"][8] for x in M]
    assert any(c.startswith("≈$") for c in b) and "—" in b                          # 1 yr per $100: ≈ while projected, — outside the spend history
    assert report["long"]["inr"]["heads"][-1] == "1 yr per ₹100" and report["page"]["inr_b365"] == "1 yr per ₹100"


def test_long_quarter_note(report):
    q = report["long"]["quarter"]
    assert "Is app me mahine ke install 1,000 se kam — isliye 3-3 mahine milake." in q["foot"]
    labs = [x["label"] for x in months(q)]
    assert labs[0].startswith("Q2 2026 (Apr–Jun)") and all(re.match(r"^Q[1-4] \d{4} \((Jan–Mar|Apr–Jun|Jul–Sep|Oct–Dec)\)", l) for l in labs)
    assert q["chips"][0][1] == "8 quarters" and len(months(q)) == 8 and len(months(report["long"]["quarter_all"])) == 9
    assert "Is app me mahine ke install" not in " ".join(report["long"]["desk"]["foot"])


def test_long_toggle_18_all(report):
    L = report["long"]
    assert L["desk"]["chips"] == [["18", "18 months", True], ["all", "All", False]] and len(months(L["desk"])) == 18
    assert L["all"]["chips"] == [["18", "18 months", False], ["all", "All", True]] and len(months(L["all"])) == 20
    assert L["state|young"]["chips"] == []                                          # nothing to fold: no toggle


def test_long_phone_sticky(report):
    p = report["long"]["phone"]
    assert p["heads"] == ["Installed in", "Day 90", "Day 365", "Earning 1 yr"] and p["sticky"] and p["scroller"] and int(p["minw"]) <= 340
    assert all(len(x["cells"]) == 4 and "installs" in x["cells"][0] for x in months(p))
    assert any("yr" in x for x in p["rows"])                                         # the year rows are kept
    assert report["long"]["desk"]["scroller"] and report["long"]["quarter_phone"]["heads"] == p["heads"]


def test_long_release_marker(report):
    M = months(report["long"]["desk"])
    r = [x for x in M if x["rel"]]
    assert len(r) == 1 and len(r[0]["rel"]) == 1 and "v2.2" in r[0]["rel"][0][0] and "v2.2.1" in r[0]["rel"][0][0]
    assert r[0]["rel"][0][1].startswith("ver:2.2@")


def test_alerts_screen_long_ret_card(report):
    c = [x for x in report["alerts"]["cards"] if x["title"].startswith("💸 Long-term retention")]
    assert len(c) == 1 and c[0]["sev"] == "watch"                                   # watch only, never red
    assert c[0]["title"] == "💸 Long-term retention — Apr–May 2026 · still opening after 90 days"
    assert c[0]["btns"] == [[c[0]["btns"][0][0], "Open app →"]] and c[0]["btns"][0][0].endswith(",'val-long')")
    rows = [x for x in report["chg"]["app"] if x["fam"] == "long_ret"]
    assert rows and rows[0]["call"] == "valJump('val-long')"
    assert [x["call"] for x in report["chg"]["all"] if x["fam"] == "long_ret"][0].endswith(",'val-long')")
    # a Mar–Apr install-month row: > 90 days old — only in its own 🗓️ section, never in a list (SPEC_SIMPLIFY §1.3 / N3)
    assert not any(k == "long_up" for k, _ in report["chg"]["info"]) and not report["chg"]["info_tags"]
    assert report["jumps"]["long"]["jump"] == "val-long" and report["jumps"]["long"]["calls"][0] == "value"


def test_old_array_long_renders_nothing(report):
    assert report["old"]["arrays"][1] == "" and report["old"]["missing"][1] == ""
    assert report["page"]["off"][5] == -1


def test_small_helpers(report):
    f = report["fmt"]
    assert f["lab"] == ["v2.4.1", "v2.4.1", "V3", "v7", "v"]
    assert f["pts"] == ["−3", "−0.5", "+0.5", "+4", "0", "—", "+13"]
    assert f["per"] == ["Jun–Jul 2026", "Dec 2025–Jan 2026", "May 2026", "Q1–Q2 2026", "Apr–May 2026", ""]
    assert f["llab"][1] == {"s": "Q3 2025", "sub": "Jul–Sep"} and f["llab"][2] == {"s": "Q1 2025", "sub": "Jan–Mar"} and f["llab"][4]["s"] == "Nov 2024"
    assert f["months"] == ["Apr–May 2026", "Dec 2025–Jan 2026"]


def test_flags_off_nothing_new_in_the_page(html):
    """The page code keys every addition on the data: 🧬 / 🗓️ only for an object by_version / long, the 📦 → 🧬 line only
    with consts.cd, the cost columns only with C.geo (the envelope's geo_why ok)."""
    assert "function valCdOn(){ return !!(DATA&&DATA.value&&DATA.value.consts&&DATA.value.consts.cd===true); }" in html
    assert "if(!b||b.kind!=='version'||!valCdOn()) return '';" in html
    assert "(B&&typeof B==='object'&&!Array.isArray(B))?B:null" in html and "(L&&typeof L==='object'&&!Array.isArray(L))?L:null" in html


# ── the review's fixes ─────────────────────────────────────────────────────────────────────────────

def test_geo_little_ads_late_and_unknown_cells(report):
    """A trickle of ads: "Little ads" (grey, why in the tooltip, the no-cost verdict, no money back); not paid back by
    the last age the curve reaches: "Over 90 days" + a neutral "⏳ Not paid back in 90 days" chip (never "Few
    installs"), in the strip too; a country whose cost may sit in the unmapped part: "—", never "No ads here"."""
    g = report["geo"]
    R = {r["cc"]: r for r in g["fix|desk"]["rows"]}
    thin = next(r for r in R.values() if r["cells"][-3] == "Little ads")
    assert thin["cells"][-2] == "—" and thin["verdict"] in ("top", "avg", "low") and 'class="faint"' in thin["raw"][-3]
    assert "ads se sirf ~1% installs" in thin["raw"][-3] and "30 Google Ads downloads" in thin["raw"][-3]
    late = next(r for r in R.values() if r["verdict"] == "late")
    assert late["cells"][-2] == "Over 90 days" and late["cells"][-1] == "⏳ Not paid back in 90 days"
    assert "⏳ Not paid back yet:" in g["fix|desk"]["strip"]
    unk = [r for r in R.values() if r["cells"][-3] == "—" and r["verdict"] == "avg"]
    assert unk and "Other / unmapped" in unk[0]["raw"][-3]
    assert sum(1 for r in R.values() if r["cells"][-3] == "No ads here") == 1
    cards = dict(g["fix|phone"]["cards"])
    assert any(m.endswith("· Little ads") for m in cards.values())
    assert any(m.endswith("· Money back: over 90 days") for m in cards.values())
    o = g["fix|open_thin"]["open"]
    assert "Little ads — yahan ads se sirf ~1% installs, isliye ads ka faisla (Keep / Costly) nahi" in o
    assert re.search(r"sirf ads wale ≈\$[\d.]+ · 30 Google Ads downloads", o)                  # few downloads: ≈
    o = g["fix|open_late"]["open"]
    assert "90 din me paisa wapas nahi aaya" in o and re.search(r"30 din me ≈\$\d+ wapas", o)   # its own weeks' cost unknown: ≈
    assert "kisi country se match nahi kiya (Other / unmapped)" in g["fix|open_unk"]["open"]
    assert any(re.search(r"\( ?24% of ads cost ?, ≈\$[\d.]+ per Google Ads install\)", x) for x in g["fix|desk"]["rest"])   # (bold: ≥ 10%)


def test_geo_inr_view_shows_the_billed_rupees(report):
    """₹ view: a country's cost per install is what Google Ads billed (its base-currency cost), never USD at today's
    rate — the Data check's promise holds for the country numbers too."""
    g = report["geo"]["ok|inr"]
    cpis = [r["cells"][-3] for r in g["rows"] if r["cells"][-3].startswith("₹")]
    assert cpis[:3] == ["₹1.80", "₹2.16", "₹2.52"]                     # 0.020 / 0.024 / 0.028 × the billed 90, not × 84
    assert g["all"][-3].startswith("₹") and any(x.startswith("Other small countries") and "₹" in x for x in g["rest"])
    o = report["geo"]["ok|inr_open"]["open"]
    assert "Cost per install ₹1.80 (sirf ads wale ₹2.34 · " in o and "Cost per install (12 weeks) ₹1.80" in o   # the sparkline too


def test_version_short_part_few_and_phone_pair(report):
    """A finished 1-day version with 1,824 installs: "Too short to compare" (neutral), no "few installs" badge, "—" in
    the comparison column (never "wait"); a part cell on 260 installs: grey "31*" saying so; the phone's "(pichhla X)"
    sits beside the comparison's own number, never the version's all-days one."""
    v = report["ver"]
    R = rows_by_ver(v["fix|desk"])
    assert R["2.1"]["chip"] == ["uni-pz", "short", "— Faisla nahi (agla update jaldi aaya)"] and not R["2.1"]["few"]
    assert R["2.1"]["cells"][6] == "— vs v2.0" and any("tulna ke liye 3+ din chahiye" in t for t in R["2.1"]["titles"])
    assert R["2.3"]["cells"][2] == "31⏳ of 100" and any("Sirf 260 installs, 37 wapas aaye" in t for t in R["2.3"]["titles"])
    assert R["2.2"]["cells"][2] == "34 of 100" and R["2.2"]["cells"][6].startswith("agle din 100 me 0")   # (no "pts", §1.7)
    C = {c["ver"]: c for c in v["fix|phone"]["cards"]}
    assert C["2.2"]["m"].startswith("35 of 100 next day (pichhla 35)")                  # 34.51 vs 34.51: the same pair
    assert C["2.1"]["chip"] == ["uni-pz", "short", "— Faisla nahi (agla update jaldi aaya)"]


def test_version_link_to_a_newer_update_says_it_is_new(report):
    v = report["ver"]
    assert v["link_new"]["vnone"].startswith("ℹ️ v9.9 abhi naya hai — install-day data ") and "row kuch din me aayegi" in v["link_new"]["vnone"]
    assert "rollout" not in v["link_new"]["vnone"] and "rollout" in v["link_old"]["vnone"]
    i = report["imp"]
    assert re.fullmatch(r"🧬 Users of v2\.2 — abhi naya: install-day data .+ tak, number kuch din me →", i["newer"]["text"])
    assert i["newer"]["call"][1] == "2.2" and i["newer"]["call"][2] > i["on_act"]["call"][2]
    assert i["on_act"]["text"] == "🧬 Users of v2.2 — 30 din tak kitne ruke, kitna kamaya →"


def test_long_earning_not_yet_and_little_ads(report):
    """The combined earning cell: an age not old enough (no projection) reads "6 mo in N days" — like every not-yet
    cell — never "—"; a month with a trickle of spend: "Little ads" in "1 yr per $100"."""
    M = months(report["long"]["fix"])
    cells = [x["cells"][7] for x in M]
    assert any(re.search(r" · 90 d in \d+ days$", c) for c in cells) and any(re.search(r" · 6 mo in \d+ days$", c) for c in cells)
    assert any(re.search(r" · 1 yr in \d+ days$", c) for c in cells) and not any(c.endswith("· —") for c in cells)
    assert [x["cells"][8] for x in M].count("Little ads") == 1
