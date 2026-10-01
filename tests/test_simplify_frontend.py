"""SPEC_SIMPLIFY on the page (frontend/index.html), rendered for real: tests/simplify_frontend.js runs the page's own
script in a node vm on the committed synthetic fixtures (uninstall / active / value samples) plus made-up rows. Checked
here: the date / age / IST helpers, one status word + one status chip + the owner's grey 🕒 timestamp line on every row
of the three tabs (Alert bana · Data · Badlaav shuru · Band hua), the §6.3 folds, the All-apps lists built from
dashboard.json only (identical before and after a per-app file loads), no banned word on any screen, the Alerts screen
= ad units only (Total issues = critical + warning, a chip and Shuru on each card), the Alerts badge without the GA4 tabs
and ✅ Review as the landing screen. Skipped where node is not installed."""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX = os.path.join(ROOT, "tests", "fixtures")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

# SPEC_SIMPLIFY §1.1 / §1.7 / §6.4 / §9 checks 1 + 2: words no screen of these tabs may show
BANNED = re.compile(r"\bis hafte\b|\bthis week\b|\babhi ka\b|Provisional|kacch?a\b|kacche|Estimate|/1k|\bpts\b|\bpp\b|\bpoints?\b"
                    r"|cohort|ARPDAU|eCPM|mediation|Stay after|\bsettled\b|\blatest\b|\brecent\b", re.I)
BANNED_CASE = re.compile(r"\bNew\b|\bD\d{1,3}\b|\bMix\b|\bHALT\b|\bWIN\b|\bReturning\b")   # the old chips / codes, as written
DEVA = re.compile("[ऀ-ॿ]")


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    path = str(tmp_path_factory.mktemp("fe") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "simplify_frontend.js"), path, os.path.join(FX, "uninstall_sample.json"),
                          os.path.join(FX, "active_sample.json"), os.path.join(FX, "value_sample.json")],
                         check=True, capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout)


def test_renders_without_errors(report):
    assert report["errors"] == []


def test_dates_age_and_ist_time(report):
    h = report["helpers"]
    assert h["umar"] == ["0 din", "3 din", "30 din", "4 hafte", "13 hafte", "3 mahine", "7 mahine"]      # §1.2 Umar
    assert h["ist"] == "28 Sep, 10:26 IST" and h["ist_date"] == "28 Sep" and h["ist_none"] == ""          # never an invented time
    assert h["d_this"] == "16 Mar" and h["d_last"] == "29 Dec 2025"                                         # the year only when not this year
    assert h["pakka"] == "⏳ Pakka nahi · 5 Oct ko pakka" and h["pakka0"] == "⏳ Pakka nahi"
    assert h["nw"] == ["install ke din hi", "agle din", "7 din me", "12 din me"]                          # §6.4 D0 / D1 / D7 / Dn
    assert h["rel"] == ["+14%", "−28%", "0%", ""] and h["count"] == ["12,345", "2.5 lakh", "34.5 lakh"]


def test_one_chip_and_the_timestamp_line(report):
    r = report["rows"]
    assert r["naya"]["chip"] == "🆕 Naya" and r["chal"]["chip"] == "🔁 Chal raha" and r["old_red"]["chip"] == "🔁 Chal raha"
    # the owner's 🕒 line, in its order: Alert bana (IST time; the date alone for an older episode) · Data · Badlaav shuru
    assert r["naya"]["ts"] == "🕒 Alert bana: 21 Sep, 10:30 IST · Data: Installs 19–25 Sep · vs pehle (22 Aug–18 Sep) · Badlaav shuru: 20 Sep · 5 din"
    # an episode opened before opened_at was kept: its opened is the DATA day it was judged on (2–3 days before the run
    # that made it) — said so, never as the run's day and never with a time
    assert r["chal"]["ts"].startswith("🕒 Alert bana: 3 Sep tak ke data pe (pehli jaanch me hi mila) · Data: ") and r["chal"]["ts"].endswith("Badlaav shuru: 1 Sep · 24 din")
    assert r["cap"]["ts"].endswith("Badlaav shuru: 6+ mahine se")
    assert " · ≈ Andaza · ⏳ Pakka nahi · 5 Oct ko pakka · Badlaav shuru: " in r["pakka"]["ts"]
    assert r["info30"]["chip"] == "🔁 Chal raha" and r["info60"]["chip"] == "🗄 Purana" and "Alert bana" not in r["info30"]["ts"]
    # closed: ✅ Theek ho gaya (recovered) / "Band" with its reason, the close time last
    assert r["theek"]["chip"] == "✅ Theek ho gaya" and r["theek"]["ts"].endswith("Band hua: 22 Sep, 10:30 IST (theek ho gaya)")
    assert r["band"]["chip"] == "" and r["band"]["ts"].endswith("Band hua: 22 Sep tak ke data pe (naya update aaya)")
    # §1.3: recovered ≤ 7 days ago, was 🔴 / 🟡, not small, opened before it closed
    assert r["theek_rule"] == [True, False, False, False, False, False]


def test_reviewer_timestamp_share_and_fold_fixes(report):
    """Reviewer fixes (2026-10-01): a run time that is not an ISO time is never shown as one (the data day instead); an
    engine "isme ~X point unka" (the installs' share of a % change) reads "~X%", never "100 me X" (a rate); "market" /
    "eCPM" / "mediation" in an engine sentence are said in Hinglish; a small app's info row > 90 days old is listed
    nowhere (§1.3, like every other app's), while an OPEN alert told as ℹ️ (N1) is always listed, whatever its age."""
    h, r = report["helpers"], report["rows"]
    assert r["not_iso"]["ts"].startswith("🕒 Alert bana: 21 Sep tak ke data pe · Data: ")
    assert h["share"].endswith("— isme ~25.5% unka") and "100 me 25.5" not in h["share"]
    assert h["share_upto"].endswith("— isme ~12% tak unka ho sakta")
    assert h["pp"] == "agle din wapas aane wale naye users 100 me 26 kam"
    assert "bazaar/dusre ad networks/country mix" in h["market"] and not re.search(r"eCPM|market|mediation", h["market"])
    assert r["small_info120"]["small_app"] is None
    assert r["n1_old"]["fold"] == "purana" and r["n1_old"]["fold_app"] == "purana" and r["n1_old"]["ts"].startswith("🕒 Alert bana: ")


def test_reviewer_old_labels_gone_from_the_notes_tables_and_pooled_tiles(report):
    """The "How we compare" note names the verdicts as the chips do (🛑 Update roko …, never HALT / HOLD / CONTINUE /
    WIN / Too early); the Uninstall full table's status column and the folded update lines use the six words; the Active
    pooled tiles count users in lakh like the rest of the card (never "3.4M" beside "34.5 lakh"); the Active All-apps page
    points to the update card it lost (§6.5)."""
    t = report["texts"]
    how = t["how"]
    for w in ("🛑 Update roko = ", "⚠️ Ruk ke jaancho = ", "👍 Chalne do = ", "✅ Update achha gaya = ", "⏳ Abhi jaldi = "):
        assert w in how, w
    assert not re.search(r"HALT|HOLD|CONTINUE|\bWIN\b|Too early|Returning DAU|\bWorse\b|\bBetter\b|\bMaybe\b|eCPM|\bMarket\b", how), how
    cp = t["uni_cp_all"]
    assert "Full table" in cp and not re.search(r"🎉 Better|🟠 Worse|\bMaybe\b|\bmarket\b|low data ·", cp)
    assert re.search(r"Purane users \(roz\) \d+(\.\d)? lakh", report["pool_big"]) and not re.search(r"\d(\.\d)?M\b", report["pool_big"])
    # the Active All-apps page lost its "📦 Recent updates" card (§6.5): one line points to where it lives now
    act_pf = t["act_pf_nofiles"]
    assert "📦 Sab apps ke updates ka asar → Uninstall tab ›" in act_pf and "Recent updates" not in act_pf


def test_every_open_alert_is_listed_on_all_apps_visible_or_in_a_fold(report):
    """(Reviewer: the old "What changed? (n) = every open alert" checks became subsets once rows fold.) Every open alert of
    the three tabs is one row of its All-apps list — shown or in a fold, never dropped (an act_slow told inside its
    act_drift row, M5, is the only one that is not a row of its own)."""
    L, A = report["lists"], report["open_alerts"]
    for tab in ("uni", "act", "val"):
        rows = [r for r in L.get(tab, []) if r["type"] == "alert" or r["info"]]
        want = sorted(set(A[tab]) - set(A["act_slow_merged"] if tab == "act" else []))
        assert sorted(r["key"] for r in rows) == want, tab
        assert all(r["fold"] is not None for r in rows), [r for r in rows if r["fold"] is None]
    assert A["uni"] and A["act"]


def test_section_6_3_folds(report):
    r = report["rows"]
    assert r["naya"]["fold"] == "" and r["chal"]["fold"] == "" and r["old_red"]["fold"] == "purana"   # 🔴 / 🟡 > 30 days: 🗄 fold
    assert r["good"]["fold"] == "achhi" and r["info30"]["fold"] == "info" and r["info60"]["fold"] == "purana"
    assert r["info120"]["fold"] is None and r["info120"]["fold_app"] is None                          # > 90 days: listed nowhere
    assert r["theek"]["fold"] == "theek" and r["band"]["fold"] is None and r["band"]["fold_app"] == "band"   # Band: the app's history only


def test_every_row_has_one_word_one_chip_and_its_timestamp_line(report):
    seen = 0
    for k, rows in report["rows_all"].items():
        for x in rows:
            seen += 1
            assert x["words"] == 1 and x["chips"] <= 1, (k, x["t"])
            assert x["shuru"], (k, x["t"])
            if not x["info"]:                                                   # every alert: the 🕒 line, its Data
                assert x["chips"] == 1 and x["clock"] and x["data"], (k, x["t"])
    assert seen >= 20


def test_all_apps_lists_are_the_same_before_and_after_an_app_file_loads(report):
    assert report["same_lists"] == {"act": True, "val": True}


def _app_names():
    """The made-up app names of the fixtures ("Demo Mediation", "Demo D1 Drop" …): a name is the app's own, never a label."""
    names = set()

    def walk(o, k=None):
        if isinstance(o, dict):
            for kk, v in o.items():
                walk(v, kk)
        elif isinstance(o, list):
            for v in o:
                walk(v, k)
        elif isinstance(o, str) and k in ("app", "app_name", "name") and o.startswith("Demo "):
            names.add(o)
    for f in ("uninstall_sample.json", "active_sample.json", "value_sample.json"):
        with open(os.path.join(FX, f), encoding="utf-8") as fh:
            walk(json.load(fh))
    return sorted(names, key=len, reverse=True)


def test_no_banned_word_on_any_screen(report):
    names = _app_names()
    for k, t in report["texts"].items():
        for n in names:
            t = t.replace(n, "<app>")
        m = BANNED.search(t) or BANNED_CASE.search(t)
        assert not m, (k, m.group(0), t[max(0, m.start() - 60):m.end() + 40])
        assert not DEVA.search(t), k
        for w in ("undefined", "NaN", "[object Object]", "Infinity"):
            assert w not in t, (k, w)


def test_alerts_screen_is_ad_units_only(report):
    a = report["alerts"]
    assert a["ga4_cards"] == 0 and "Ad units ke problems · Sirf badi (paise wali) ad units · AdMob data 24 Sep tak" in report["texts"]["alerts"]
    assert a["total"] == "2"                                                  # critical + warning (the watch never counts)
    assert a["chips"] == [["🆕 Naya", "22 Sep · 3 din"], ["🔁 Chal raha", "30 Aug · 26 din"], ["🆕 Naya", "24 Sep · 1 din"]]
    assert "uninstall aur install value ki khabar ab unke apne tabs me hai" in report["texts"]["alerts"]


def test_alerts_badge_leaves_the_ga4_tabs_out(report):
    b = report["badge"]
    assert b["n"] == 3 and b["ga4_warnings"] > 0                             # 1 critical + 1 warning + 1 range breach


def test_review_is_the_landing_screen_when_it_has_a_day(report):
    L = report["landing"]
    assert L["day"] is True and L["day_calls"] == ["review"]
    assert L["none"] is False and L["none_calls"] == [] and L["err"] is False and L["err_calls"] == []
    assert L["saved"] is False and L["saved_calls"] == []                    # a recent saved view wins
    assert L["hash"] is False and L["hash_calls"] == []                      # a #review… deep link (rvBoot) wins
    assert L["moved"] is False and L["moved_calls"] == []                    # the reader already moved on
