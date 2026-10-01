"""SPEC_SIMPLIFY on the page (frontend/index.html), rendered for real: tests/simplify_frontend.js runs the page's own
script in a node vm on the committed synthetic fixtures (uninstall / active / value samples) plus made-up rows. Checked
here: the date / age / IST helpers, one status word + one status chip + the owner's grey 🕒 timestamp line on every row
of the three tabs (Alert aaya · Data · Badlaav shuru · Band hua; an info row: Data · Badlaav shuru), the alert-age
chip (owner, 1 Oct: 🆕 Naya alert · aaj HH:MM / 🆕 Kal aaya / 📌 N din se khula / 📌 <date> se khula / 📌 Shuru se khula,
in IST) with its legend above every list, the §6.3 folds, the All-apps lists built from
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
BANNED_CASE = re.compile(r"(?<!🆕 )\bNew\b|\bD\d{1,3}\b|\bMix\b|\bHALT\b|\bWIN\b|\bReturning\b")   # the old chips / codes, as written — 🆕 New (today/yesterday chip, GLOSSARY problem chips) is wanted now
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
    assert h["umar"] == ["0 days", "3 days", "30 days", "4 weeks", "13 weeks", "3 months", "7 months"]      # §1.2 Umar
    assert h["ist"] == "28 Sep, 10:26 IST" and h["ist_date"] == "28 Sep" and h["ist_none"] == ""          # never an invented time
    assert h["d_this"] == "16 Mar" and h["d_last"] == "29 Dec 2025"                                         # the year only when not this year
    assert h["pakka"] == "⏳ Not final · final on 5 Oct" and h["pakka0"] == "⏳ Not final"
    assert h["nw"] == ["same day uninstall", "uninstalled within 1 day", "uninstalled within 7 days", "uninstalled within 12 days"]  # §6.4 D0 / D1 / D7 / Dn
    assert h["rel"] == ["+14%", "−28%", "0%", ""] and h["count"] == ["12,345", "2.5 lakh", "34.5 lakh"]


def test_one_chip_and_the_timestamp_line(report):
    r = report["rows"]
    # the chip is the ALERT's age (owner, 1 Oct: "new alert he?") — never the change's: a change that began 5 days ago in
    # an alert made 4 days ago reads "📌 4 din se khula" (the change's start is "Badlaav shuru" in the 🕒 line)
    assert r["naya"]["chip"] == "📌 Open 4 days" and r["naya"]["tip"] == "Alert time: 21 Sep, 10:30 IST"
    # the owner's 🕒 line, in its order: Alert time (IST time) · Data · Change started
    assert r["naya"]["ts"] == "🕒 Alert time: 21 Sep, 10:30 IST · Data: Installs 19–25 Sep · vs pehle (22 Aug–18 Sep) · Change started: 20 Sep · 5 days"
    # an episode with no recorded time at all (neither opened_at nor notified_at): its opened is the DATA day it was
    # judged on (2–3 days before the run that made it) — said so, never as the run's day and never with a time
    assert r["chal"]["ts"].startswith("🕒 Alert time: on data till 3 Sep · Data: ") and r["chal"]["ts"].endswith("Change started: 1 Sep · 24 days")
    assert r["chal"]["chip"] == "📌 Open" and "New" not in r["old_red"]["chip"] and "Ongoing" not in r["old_red"]["chip"]
    assert r["cap"]["ts"].endswith("Change started: 6+ months")
    assert " · ≈ · ⏳ Not final · final on 5 Oct · Change started: " in r["pakka"]["ts"]
    # an info row: no age chip (🗄 Old past 30 days) and its own 🕒 line — Data · Change started (· Seen when known)
    assert r["info30"]["chip"] == "" and r["info60"]["chip"] == "🗄 Old" and "Alert time" not in r["info30"]["ts"]
    assert r["info30"]["ts"] == "🕒 Data: Installs 19–25 Sep · vs pehle (22 Aug–18 Sep) · Change started: 10 Sep · 15 days"
    assert r["info_dikha"]["ts"].endswith("Change started: 10 Sep · 15 days · Seen: 12 Sep")
    assert r["info_nodata"]["ts"] == "🕒 Change started: 10 Sep · 15 days"
    # closed: ✅ Fixed (recovered) / "Band" with its reason, the close time last
    assert r["theek"]["chip"] == "✅ Fixed" and r["theek"]["ts"].endswith("Closed: 22 Sep, 10:30 IST (recovered)")
    assert r["theek"]["ts"].startswith("🕒 Alert time: 3 Sep, 10:30 IST · Data: ")
    assert r["band"]["chip"] == "" and r["band"]["ts"].endswith("Closed: on data till 22 Sep (new update)")
    # §1.3: recovered ≤ 7 days ago, was 🔴 / 🟡, not small, opened before it closed
    assert r["theek_rule"] == [True, False, False, False, False, False]


def test_the_alert_age_chip_boundaries_in_ist(report):
    """🆕 Naya alert · aaj HH:MM (the same IST day as the last check) · 🆕 Kal aaya (the IST day before) · 📌 N din se khula
    (2–29) · 📌 <date> se khula (30+) · 📌 Shuru se khula (<date>) for an episode the feature's first run made (seeded,
    whatever its day). The last check here: 25 Sep 03:30 UTC = 25 Sep 09:00 IST."""
    r = report["rows"]
    assert r["age_aaj_utc_yday"]["chip"] == "🆕 New alert · today 00:30" and r["age_aaj_utc_yday"]["isnew"]   # 24 Sep 19:00 UTC
    assert r["age_kal_utc_same"]["chip"] == "🆕 Yesterday" and r["age_kal_utc_same"]["isnew"]                  # 24 Sep 23:59 IST
    assert r["age_kal"]["chip"] == "🆕 Yesterday"
    assert r["age_2"]["chip"] == "📌 Open 2 days" and not r["age_2"]["isnew"]
    assert r["age_29"]["chip"] == "📌 Open 29 days" and r["age_30"]["chip"] == "📌 Open since 26 Aug"
    assert r["age_old_year"]["chip"] == "📌 Open since 30 Dec 2025"
    assert r["age_seeded"]["chip"] == "📌 Open from start (19 Sep)" and not r["age_seeded"]["isnew"]
    assert r["age_seeded"]["tip"] == "Ye halat feature shuru hone se pehle se thi — tab hi mil gayi · Alert time: 19 Sep, 17:30 IST"
    assert r["age_seeded_today"]["chip"] == "📌 Open from start (25 Sep)"
    assert not any(r[k]["isnew"] for k in ("age_2", "age_29", "age_30", "age_old_year", "age_seeded", "age_seeded_today", "naya", "chal"))


def test_the_alert_time_falls_back_opened_at_then_notified_at_then_the_data_day(report):
    """The time shown is the run that opened the episode (opened_at); an older episode's is the engine's alert_at (its
    notified_at run); with neither, the data day it was judged on in words — never an invented time."""
    r = report["rows"]
    assert r["fb_opened"]["ts"].startswith("🕒 Alert time: 24 Sep, 09:30 IST · ") and r["fb_opened"]["chip"] == "🆕 Yesterday"
    assert r["fb_alert_at"]["ts"].startswith("🕒 Alert time: 23 Sep, 18:30 IST · ") and r["fb_alert_at"]["chip"] == "📌 Open 2 days"
    assert r["fb_bad_opened"]["ts"].startswith("🕒 Alert time: 23 Sep, 18:30 IST · ")      # "sent" is not a time
    assert r["fb_none"]["ts"].startswith("🕒 Alert time: on data till 21 Sep · ") and r["fb_none"]["chip"] == "📌 Open"
    assert r["fb_none_closed"]["ts"].startswith("🕒 Alert time: on data till 3 Sep · ")
    assert r["fb_none_closed"]["ts"].endswith("Closed: on data till 22 Sep (window ended)")


def test_a_legend_above_every_what_changed_list_and_the_heads_count_new_alerts(report):
    for k, x in report["legend"].items():
        assert x["lists"] == 1 and x["legends"] == 1 and x["order"], (k, x)
    n = report["naye"]
    assert n["uni"] is not None and int(n["uni"]) == n["uni_rows"]
    assert n["act"] is not None and int(n["act"]) == n["act_rows"]


def test_reviewer_timestamp_share_and_fold_fixes(report):
    """Reviewer fixes (2026-10-01): a run time that is not an ISO time is never shown as one (the data day instead); an
    engine "isme ~X point unka" (the installs' share of a % change) reads "~X%", never "100 me X" (a rate); "market" /
    "eCPM" / "mediation" in an engine sentence are said in Hinglish; a small app's info row > 90 days old is listed
    nowhere (§1.3, like every other app's), while an OPEN alert told as ℹ️ (N1) is always listed, whatever its age."""
    h, r = report["helpers"], report["rows"]
    assert r["not_iso"]["ts"].startswith("🕒 Alert time: on data till 21 Sep · Data: ")
    assert h["share"].endswith("— isme ~25.5% unka") and "100 me 25.5" not in h["share"]
    assert h["share_upto"].endswith("— isme ~12% tak unka ho sakta")
    assert h["pp"] == "back next day 26% kam"
    assert "bazaar/dusre ad networks/country mix" in h["market"] and not re.search(r"eCPM|market|mediation", h["market"])
    assert r["small_info120"]["small_app"] is None
    assert r["n1_old"]["fold"] == "purana" and r["n1_old"]["fold_app"] == "purana" and r["n1_old"]["ts"].startswith("🕒 Alert time: ")


def test_reviewer_old_labels_gone_from_the_notes_tables_and_pooled_tiles(report):
    """The "How we compare" note names the verdicts as the chips do (🛑 Update roko …, never HALT / HOLD / CONTINUE /
    WIN / Too early); the Uninstall full table's status column and the folded update lines use the six words; the Active
    pooled tiles count users in lakh like the rest of the card (never "3.4M" beside "34.5 lakh"); the Active All-apps page
    points to the update card it lost (§6.5)."""
    t = report["texts"]
    how = t["how"]
    for w in ("🛑 Update roko = ", "⚠️ Ruk ke jaancho = ", "👍 Chalne do = ", "✅ Update achha gaya = ", "⏳ Too early = "):
        assert w in how, w
    assert not re.search(r"HALT|HOLD|CONTINUE|\bWIN\b|Returning DAU|\bMaybe\b|eCPM", how), how
    cp = t["uni_cp_all"]
    assert "Full table" in cp and not re.search(r"🎉 Better|🟠 Worse|\bMaybe\b|\bmarket\b|low data ·", cp)
    assert re.search(r"Old users/day \d+(\.\d)? lakh", report["pool_big"]) and not re.search(r"\d(\.\d)?M\b", report["pool_big"])
    # the Active All-apps page lost its "📦 Recent updates" card (§6.5): one line points to where it lives now
    act_pf = t["act_pf_nofiles"]
    assert "📦 Update impact → Uninstall tab ›" in act_pf and "Recent updates" not in act_pf


def test_active_says_in_one_line_whether_an_app_had_an_update_and_goes_to_its_block_in_uninstall(report):
    """The owner (1 Oct): Update impact stays on the Uninstall tab ("rehne do, vaha se dekh lunga"); the Active users tab
    says in ONE line whether the app had an update in the last 60 days and where its full card is — the tap opens the
    Uninstall tab at that app with that update's block open. All apps: "📦 Updates ka asar → Uninstall tab ›"."""
    L = report["updline"]
    apps, allp = [x for x in L if not x.get("all")], next(x for x in L if x.get("all"))
    assert allp["text"] == "📦 Update impact → Uninstall tab ›" and allp["go"] == "show('uninstall')"
    with_u = [x for x in apps if x["n"]]
    assert with_u and [x for x in apps if not x["n"]]
    for x in apps:
        if not x["n"]:
            assert x["text"] == "📦 Pichhle 60 din me koi update nahi" and x["go"] == "", x
            continue
        assert re.match(r"^📦 Is app ka aakhri update: \S.* \(\d{1,2} [A-Z][a-z]{2}\) · .+ → Full card in Uninstall ›$", x["text"]), x["text"]
        assert x["go"] == "uniImpGo('%s','%s')" % (x["app_id"], x["newest"]), x
        assert x["calls"][0] == "show:uninstall" and x["UNIAPP"] == x["app_id"] and x["APP"] == x["app"], x
        assert x["open"] == x["newest"] and x["rendered_open"] == [x["newest"]] and x["card"] and x["detail"], x


def test_update_impact_alert_rows_stay_in_uninstalls_what_changed_with_the_age_chip_and_the_clock(report):
    I = report["imp_rows"]
    assert I["want"] >= 2 and len(I["all"]) >= I["want"]
    assert all(AGE.match(x["chip"]) and x["clock"] and x["ts"] for x in I["all"]), I["all"]


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


AGE = re.compile(r"^(?:🆕 New alert · today \d\d:\d\d|🆕 Yesterday|📌 Open \d+ days|📌 Open since \d{1,2} [A-Z][a-z]{2}(?: \d{4})?"
                 r"|📌 Open from start \(\d{1,2} [A-Z][a-z]{2}(?: \d{4})?\)|✅ Fixed|Closed · .*)$")


def test_every_row_has_one_word_one_chip_and_its_timestamp_line(report):
    seen = alerts = 0
    for k, rows in report["rows_all"].items():
        for x in rows:
            seen += 1
            assert x["words"] == 1 and x["chips"] <= 1, (k, x["t"])
            assert x["shuru"], (k, x["t"])
            assert x["ts_clock"], (k, x["t"])                                  # EVERY row (info too): the 🕒 line
            assert "Naya ·" not in x["chip"] or x["chip"].startswith("🆕 Naya alert"), (k, x["chip"])
            assert x["chip"] not in ("🆕 Naya", "🔁 Chal raha"), (k, x["chip"])   # the change-age chip is gone
            if not x["info"]:                                                   # every alert: its age chip, 🕒 Alert aaya, Data
                alerts += 1
                assert x["chips"] == 1 and AGE.match(x["chip"]) and x["clock"] and x["data"], (k, x["t"])
                assert not x["fallback"], (k, x["t"])                           # built alerts: a real time, never the data day
    assert seen >= 20 and alerts >= 10


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
    assert a["ga4_cards"] == 0 and "Ad unit problems · Only big (money) ad units · AdMob data till 24 Sep" in report["texts"]["alerts"]
    assert a["total"] == "2"                                                  # critical + warning (the watch never counts)
    assert a["chips"] == [["🆕 New", "22 Sep · 3 days"], ["🔁 Ongoing", "30 Aug · 26 days"], ["🆕 New", "24 Sep · 1 day"]]
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
