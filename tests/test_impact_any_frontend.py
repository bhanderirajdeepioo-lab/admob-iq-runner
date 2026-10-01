"""📅 Compare any date on the page (frontend/index.html), rendered for real: tests/impact_any_frontend.js runs the page's
own script in a node vm on SYNTHETIC apps built here by the real engine (tests.uninstall_synth stores → impact_app for
the 📦 Update impact card, engine.impact_any.build_app for impact_any_<key>.json.gz + its index), with a scripted fetch
(the files gzipped as the build writes them, the dashboard Worker's /api/marks). Checked here:
  * the page's decoder (anyDecode) equals engine.impact_any.decode on EVERY date of two apps (and null outside them);
  * the card for an update's release date shows the same rows as that update's own block — every row's Before /
    After / Change, its status and its split, at 7 / 14 / 30 / 60 days (kind "update": its After starts the next day);
  * the honest states: ⏳ Abhi jaldi — <ready_on> ko poora hoga, an update released on the date (a link to its own
    block), the real updates inside the windows (beech me … update aaya, Before ke din me …), a stale file's data date,
    a pending / missing app, a missing index;
  * the All-apps "📅 Ek date, sab apps" tool: progress, one row per app (name · account), the 6 status words, worst first,
    a row opens that app's card at that date, 📌 markers;
  * 📌 Saved dates through /api/marks: listed with the "*" ones, 💾 Save confirmed only on the API's OK, every error path
    said (server down, 500, 401, a static host's 404) while the comparison keeps working, delete for the author / admin;
  * the words: English labels, Hinglish in Roman script only, the 6 status words, no banned word (SPEC_SIMPLIFY §6.4);
  * 375 px: every new line wraps (the CSS rules that keep the page from scrolling sideways).
Every app, id and number here is made up. Skipped where node is not installed."""

import gzip
import json
import os
import re
import shutil
import subprocess
from datetime import date, timedelta

import pytest

from admob_iq.engine import impact as imp
from admob_iq.engine import impact_any as ia
from tests.test_impact_any import NOW, SURGES, surge_store
from tests.test_impact_windows import _stores
from tests.uninstall_synth import END

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

ACC = "pub-1001"
A_ID, B_ID, C_ID, D_ID = ("ca-app-pub-1001~%d" % n for n in (3001, 3002, 3003, 3004))
A_KEY, B_KEY, C_KEY, D_KEY = "a1a1a1a1a1a1", "b2b2b2b2b2b2", "c3c3c3c3c3c3", "d4d4d4d4d4d4"
TODAY = END + timedelta(days=2)

# SPEC_SIMPLIFY §6.4 (tests/test_simplify_frontend.py's lists) + the six status words
BANNED = re.compile(r"\bis hafte\b|\bthis week\b|\babhi ka\b|Provisional|kacch?a\b|kacche|Estimate|/1k|\bpts\b|\bpp\b|\bpoints?\b"
                    r"|cohort|ARPDAU|eCPM|mediation|Stay after|\bsettled\b|\blatest\b|\brecent\b", re.I)
BANNED_CASE = re.compile(r"\bNew\b|\bD\d{1,3}\b|\bMix\b|\bHALT\b|\bWIN\b|\bReturning\b")
DEVA = re.compile("[ऀ-ॿ]")
WORDS = {"bigda": "🔴 Worse", "dhyan": "🟡 Watch", "behtar": "🟢 Better", "normal": "⚪ Normal", "jaldi": "⏳ Too early",
         "lagu": "— N/A"}


def _detail(st, rv, app_id):
    """The 📦 Update impact card of the app as the asset carries it (impact_app on a first evaluation)."""
    store, ds, cd, whole, i0, rels, E, late = ia.prepare(dict(st, window_end=END.isoformat()), 7)
    detail, _, _ = imp.impact_app(store, ds, cd, whole, i0, rels, rv, {}, app_id, E, late, True, True, False, NOW)
    return detail


def _gz(path, obj):
    with open(path, "wb") as f:
        f.write(gzip.compress(json.dumps(obj, separators=(",", ":")).encode("utf-8"), mtime=0))


def build(d):
    """Two real apps (A: app_update surges — kind "update"; B: version rollouts), C pending in the index, D not in it."""
    apps, index, decoded = [], [], {}
    st_a, rv_a = surge_store(surges=SURGES, ipu=lambda x, v: 3.5 if x >= END - timedelta(days=60) else 4.0)
    st_b, rv_b = list(_stores())[5]
    for app_id, key, name, (st, rv) in ((A_ID, A_KEY, "Demo Surge Gallery", (st_a, rv_a)),
                                        (B_ID, B_KEY, "Demo Version Notes", (st_b, rv_b))):
        body, failed = ia.build_app(dict(st, window_end=END.isoformat()), rv, app_id, key, "sig-" + key, 7)
        assert failed == 0 and body["n"] > 100
        fn = "impact_any_%s.json.gz" % key
        _gz(os.path.join(d, fn), body)
        index.append(ia.index_entry(body, fn))
        X0 = date.fromisoformat(body["first"])
        decoded[app_id] = {(X0 + timedelta(days=i)).isoformat(): ia.decode(body, X0 + timedelta(days=i)) for i in range(body["n"])}
        apps.append({"app_id": app_id, "app": name, "key": key, "impact": _detail(st, rv, app_id),
                     "first": body["first"], "last": body["last"], "data_till": body["data_till"]})
    index[1]["fresh"] = False                             # B: the time budget ran out — its file is from older inputs
    index.append({"app_id": C_ID, "key": C_KEY, "file": None, "pending": True})
    idx = {"v": 1, "file_v": ia.V, "history_days": ia.HISTORY_DAYS, "windows": list(ia.WINDOWS),
           "apps": sorted(index, key=lambda x: x["app_id"])}
    _gz(os.path.join(d, "impact_any_index.json.gz"), idx)
    apps += [{"app_id": C_ID, "app": "Demo Pending Camera", "key": C_KEY, "impact": None},
             {"app_id": D_ID, "app": "Demo No GA4 Clock", "key": D_KEY, "impact": None}]
    a = apps[0]
    upd = sorted(b["date"] for b in a["impact"]["updates"])
    R = date.fromisoformat(upd[-3])                      # an update with another one 7 days later (Aug 10 → Aug 17)
    picks = {"update_dates": upd, "cut": (R - timedelta(days=3)).isoformat(), "overlap": (R + timedelta(days=3)).isoformat(),
             "last": a["last"], "first": a["first"], "halt": next(b["date"] for b in a["impact"]["updates"]
                                                                   if b["verdict"]["level"] == "halt")}
    fx = {"today": TODAY.isoformat(), "apps": apps, "index": idx, "decoded": decoded, "picks": picks,
          "catalog": [{"app_id": x["app_id"], "app_name": x["app"], "account_id": ACC} for x in apps]}
    with open(os.path.join(d, "fx.json"), "w", encoding="utf-8") as f:
        json.dump(fx, f, ensure_ascii=False)
    return fx


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("anyfe"))
    fx = build(d)
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    path = os.path.join(d, "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "impact_any_frontend.js"), path, d], check=True,
                         capture_output=True, text=True, timeout=600)
    rep = json.loads(out.stdout)
    rep["_fx"] = fx
    rep["_html"] = html
    return rep


def test_renders_without_errors(report):
    assert report["errors"] == []


def test_the_page_decoder_equals_the_engines_decode_on_every_date(report):
    D = report["decode"]
    assert D["dates"] >= 400 and D["same"] == D["dates"], D["diff"][:3]
    assert D["outside"] == [None, None, None, None]          # before the first / after the last date, a bad date, no file


def test_a_release_date_shows_the_same_rows_as_that_updates_own_block_at_every_window(report):
    P = report["parity"]
    assert P["dates"] == 6 and P["windows"] >= 20 and P["rows"] >= 150
    assert P["diffs"] == [], P["diffs"][:2]
    # what the rows say: before / after / change cells, the status, the split under a row. The file keeps a row's
    # numbers to the precision the card shows (the engine's asset: one digit more), so a last shown digit may round the
    # other way, and the plain "seedha" line (shown when it differs from the judged change by ≥ 0.005) may flip only
    # when that difference is within a rounding step of 0.005; "7 din ke faisle me pehle hi dikha" is an update's alert
    # history — a date never alerts
    assert P["cells"] >= 450 and P["split_rows"] >= 20
    assert P["exact"] >= 0.97 * P["cells"] and P["exact"] + P["digit"] + P["seedha"] == P["cells"]
    assert P["seedha"] == P["seedha_borderline"] <= 4
    # the custom card adds no version / adoption section and has its own title
    assert P["no_version_table"] and P["no_adoption"] and P["titles_ok"]


def test_the_card_at_a_date_title_verdict_dates_and_update_on_that_day(report):
    C = report["card"]
    assert C["title"].startswith("📌 Your date: No name — ")
    assert C["title_named"].startswith("📌 Your date: Banner ad hataya — ")
    assert C["verdict_chip"] and C["before_after"] == [True, True]
    # an update released exactly on that date says so, with a link to its own block (uniImp(key)) in this same card
    assert C["same_note"].startswith("📦 Isi din App update aaya — see its own card →")
    assert C["same_link"] == "uniImp('upd@%s')" % report["_fx"]["picks"]["update_dates"][-1]
    assert C["window_buttons"] == [[7, True, False], [14, False, False], [30, False, False], [60, False, False]]
    assert C["at_30"]["n"] == "30" and "Verdict (30 days)" in C["at_30"]["title"]


def test_early_pending_and_the_real_updates_inside_the_windows(report):
    C = report["card"]
    fx = report["_fx"]
    last = fx["decoded"][A_ID][fx["picks"]["last"]]
    ro = last["7"]["verdict"]["ready_on"]
    assert last["7"]["verdict"]["level"] is None and ro
    # the day it completes as the rows' "ready ~" say it: the GA4 data day it needs + GA4's lag (2 days here)
    assert C["pending_line"] == "⏳ Too early — %s ko poora hoga" % report["fmt"]["lag:" + ro]
    assert report["fmt"]["lag:" + ro] == report["fmt"].get((date.fromisoformat(ro) + timedelta(days=2)).isoformat(),
                                                           report["fmt"]["lag:" + ro])
    assert C["pending_rows"] >= 5                      # every row of a date this near is still ⏳
    cut = fx["decoded"][A_ID][fx["picks"]["cut"]]["7"]["cut_by"]
    assert C["cut_note"].startswith("Beech me App update aaya (%s) — After yahin tak" % report["fmt"][cut["date"]])
    ov = fx["decoded"][A_ID][fx["picks"]["overlap"]]["7"]["overlap_before"]
    assert C["overlap_note"] == "Before ke din me App update aaya (%s) — Before me uska asar bhi" % report["fmt"][ov["date"]]
    assert any(n.startswith("Beech me App update aaya (") for n in C["mixed_notes_30"])
    assert C["outside"].startswith("Ye date tulna ki range ke bahar hai")


def test_stale_pending_missing_and_no_index_say_so(report):
    S = report["states"]
    assert S["stale"].startswith("⚠️ Ye tulna ") and "naya data agle refresh me" in S["stale"]
    assert S["fresh_has_no_stale_line"]
    assert S["pending"] == "Is app ke liye tulna abhi nahi ban paya — agle refresh me try hoga"
    assert S["no_file"].startswith("GA4 data nahi")
    assert S["no_index"] == "Is app ke liye tulna abhi nahi ban paya — agle refresh me try hoga"
    assert S["net"].startswith("⚠️ Tulna ki file load nahi hui") and "Try again" in S["net"]
    assert S["loading"] == "⏳ Tulna load ho rahi hai…"
    assert S["file_once"] == 1                          # the app's file is fetched once, then every date is instant
    assert S["picks_without_fetch"] >= 5
    assert S["box_at_top"] and S["box_on_every_card"] == [True, True, True]   # right under the card's title, every app


def test_the_all_apps_tool_loads_every_file_with_progress_and_sorts_worst_first(report):
    T = report["all"]
    assert T["progress"] == ["⏳ 0 / 4 apps load hue…"] and T["files_fetched"] == 1      # (A was loaded already)
    rows = T["rows"]
    assert [r["app"] for r in rows][-2:] in (["Demo Pending Camera · A/c 1001", "Demo No GA4 Clock · A/c 1001"],
                                             ["Demo No GA4 Clock · A/c 1001", "Demo Pending Camera · A/c 1001"])
    rank = ["bigda", "dhyan", "normal", "behtar", "jaldi", "lagu"]
    assert [rank.index(r["sw"]) for r in rows] == sorted(rank.index(r["sw"]) for r in rows)
    assert rows[0]["sw"] == "bigda" and rows[0]["word"] == "🔴 Worse" and rows[0]["verdict"] == "🛑 Stop update"
    assert rows[0]["hl"].startswith("Purane users (roz): ") or ": " in rows[0]["hl"]
    assert all(r["word"] == WORDS[r["sw"]] for r in rows)
    assert all(" · A/c 1001" in r["app"] for r in rows)                               # names carry the account
    assert rows[0]["go"] == "uniAnyGo('%s','%s',7)" % (A_ID, report["_fx"]["picks"]["halt"])
    assert T["opened"] == {"app": A_ID, "date": report["_fx"]["picks"]["halt"], "win": 7, "name": "Halt wala din"}
    assert T["marker_rows"] == [A_ID, B_ID, C_ID, D_ID] and T["marker_chips"] >= 2   # a "*" mark: every row's 📌
    assert T["window_switch_instant"] and T["rows_30"] == 4
    # the sort itself (made-up rows): status word, then more worse rows, then the bigger fall, then the name
    assert T["sort_unit"] == ["w2", "w1b", "w1a", "y", "n", "g", "j", "l"]


def test_saved_dates_list_save_and_delete_through_the_api(report):
    M = report["marks"]
    assert M["get"] == {"url": "/api/marks", "method": "GET", "credentials": "same-origin", "redirect": "manual"}
    assert M["listed"] == ["📌 Notification shuru · 15 Aug", "📌 Sab apps ka SDK · 1 Aug · all apps"]   # this app + "*"
    assert M["other_app_hidden"]
    assert M["delete_buttons"] == [1]                    # only the viewer's own mark (not an admin)
    s = M["save"]
    assert s["disabled_without_name"] and s["enabled_with_name"]
    assert s["pending_msg"] == "⏳ Save ho raha hai…" and not s["listed_before_ok"]
    assert s["post"] == {"url": "/api/marks", "method": "POST", "ct": "application/json", "credentials": "same-origin",
                         "body": {"app_id": A_ID, "date": report["_fx"]["picks"]["cut"], "name": "Banner ad hataya"}}
    assert s["ok_msg"] == "✅ Saved — team ko bhi dikhega" and s["listed_after_ok"]
    assert s["star_body_app"] == "*"
    for k, want in (("down", "❌ Save nahi hua — Server se jud nahi paaye. Tulna upar chal rahi hai."),
                    ("e500", "❌ Save nahi hua — Server me dikkat — thodi der baad try karo (HTTP 500). Tulna upar chal rahi hai."),
                    ("e401", "❌ Save nahi hua — Login zaroori — page reload karo (HTTP 401). Tulna upar chal rahi hai."),
                    ("static404", "❌ Save nahi hua — Saved dates ka server abhi nahi laga (HTTP 404). Tulna upar chal rahi hai."),
                    ("e400", "❌ Save nahi hua — Naam 1–80 akshar ka ho (HTTP 400). Tulna upar chal rahi hai.")):
        assert s[k]["msg"] == want, (k, s[k]["msg"])
        assert s[k]["comparison_still_there"] and not s[k]["new_mark_listed"], k
    assert s["bad_name_not_sent"] and s["bad_name_msg"].startswith("Naam likho")
    assert M["list_down"] == "📌 Saved dates: abhi nahi mil paye (Server se jud nahi paaye) — tulna phir bhi chalegi"
    assert M["list_down_comparison"]
    assert M["pick_mark"] == {"date": "2026-08-15", "name": "Notification shuru", "rendered": True}
    d = M["delete"]
    assert d["cancelled_no_call"] and d["post"] == {"url": "/api/marks/delete", "body": {"id": 1}} and d["gone"]
    assert d["fail_msg"].startswith("❌ Hata nahi paaye — ")


def test_words_english_labels_hinglish_roman_six_status_words_no_banned_word(report):
    W = report["words"]
    assert W["screens"] >= 10
    for name, t in W["texts"].items():
        assert not DEVA.search(t), name
        assert not BANNED.search(t), (name, BANNED.search(t).group(0))
        assert not BANNED_CASE.search(t), (name, BANNED_CASE.search(t).group(0))
        assert "NaN" not in t and "undefined" not in t and "null" not in t, name
    # the labels the owner reads first are English; the card's own wording is unchanged (Actual / Expected)
    allt = " ".join(W["texts"].values())
    for lab in ("📅 Compare any date", "Date", "Before / after:", "💾 Save", "📌 Saved dates:", "All apps",
                "📅 One date, all apps", "Show", "Actual:", "Expected (without update):"):
        assert lab in allt, lab
    # in the All-apps tool: no status word outside the six
    assert set(W["all_words"]) <= set(WORDS.values())


def test_375px_every_new_line_wraps(report):
    css = report["_html"]
    rule = lambda sel: re.search(re.escape(sel) + r"\{([^}]*)\}", css).group(1)   # noqa: E731
    for sel in (".uni-any-in", ".uni-any-mks", ".uni-anyr", ".uni-any-l"):
        assert "flex-wrap:wrap" in rule(sel), sel
    for sel in (".uni-any-in input[type=date],.uni-any-in input[type=text]", ".uni-any-mk"):
        assert "max-width:100%" in rule(sel), sel
    assert "overflow-wrap:anywhere" in rule(".uni-any-note") and "overflow-wrap:anywhere" in rule(".uni-anyr .hl")
    phone = css[:css.index(".uni-upd .ap{max-width:100%}")]
    phone = css[phone.rindex("@media(max-width:760px){"):]
    phone = phone[:phone.index("\n  }")]
    assert ".uni-anyr .ap{max-width:100%;flex-basis:100%}" in phone and ".uni-any-in input[type=text]{max-width:100%}" in phone
    # the comparison itself is the update block: its table turns into one card per row at ≤ 600 px (existing CSS)
    assert report["card"]["block_class"] == "uni-imp-b on"
