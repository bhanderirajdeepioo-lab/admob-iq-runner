"""📦 Update impact's two tabs and the 📅 Any date tab's CUSTOM COMPARE (owner, 2 Oct: "koi custom date ke sath bhi
compare kar saku"), rendered for real: tests/any_custom_frontend.js runs the page's own script in a node vm on
  * a SYNTHETIC app built here by the real engines from one store (tests.uninstall_synth): its Uninstall detail
    (engine.uninstall.evaluate_app), its Active users detail (engine.active.evaluate — the daily file the custom compare
    reads), its install-day cohorts (uninstall.cohort_file) and its precomputed any-date file (engine.impact_any);
  * HAND-MADE daily series whose every number is known here.
Checked:
  * the CROSS-CHECK: the custom compare with Before = X−N … X−1 and After = X+1 … X+N gives the engine's own before /
    after (the impact_any file) — every row at 7 days, the came-back / same day uninstall rows at 14 / 30 / 60, and the
    After of the per-day rows there (the engine pairs each After day with a Before day of its weekday at 14+ days, so its
    Before is not the plain mean — said in the report, not a bug) — on every date whose windows are whole and final;
  * the computation on the hand-made days: old users / day (mean of the days), sessions / time / revenue per user
    (pooled Σ ÷ Σ), came back next day / after 7 days (Pehle = the install days whose day N is inside Pehle, Baad = Baad's
    own install days), same day uninstall (a tracking break / incomplete day left out), the final-day cut (⏳ days
    excluded, ⏳ Too early with the day it is ready), the noise test against the app's own swing (a 20% step: Worse;
    flat: No change; a history too short: N/A), the people a day a rate change means;
  * the ranges: two ranges / date vs date (N days from each, the earlier = Pehle), the checks said in words, a swap,
    the quick picks and the first look (the last 7 final days vs the 7 before);
  * the card: "📅 Custom: …", the dates line, the one-line note "Custom compare: seedha pehle vs baad — trend adjust
    nahi", ONE table, no window picker for two ranges and ONE for date vs date;
  * the tabs 📦 Updates | 📅 Any date: remembered per browser (try / catch — a browser that blocks storage works), a jump
    to an update's block opens 📦 Updates, ONE 7 / 14 / 30 / 60 picker per open update block and none at the section;
    an auto-refresh (new data objects, the screen re-drawn) keeps the tab, the mode, the ranges, the typed name, "Kyun?";
  * 💾 a custom compare saved through /api/marks (its four range dates), listed, opened by a tap, deleted with kind
    "compare" (a date mark still with {id}); a Worker from before compares: the list reads, saving says why.
Every app, id and number here is made up. Skipped where node is not installed."""

import json
import math
import os
import re
import shutil
import subprocess
from datetime import date, timedelta

import pytest

from admob_iq.engine import active as act
from admob_iq.engine import impact as imp
from admob_iq.engine import impact_any as ia
from admob_iq.engine import uninstall as eng
from tests.test_impact_any import NOW, SURGES, surge_store
from tests.uninstall_synth import END

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

A_ID, KEY, NAME = "ca-app-pub-1001~3001", "a1a1a1a1a1a1", "Demo Surge Gallery"
H_ID, H_KEY = "ca-app-pub-1001~3009", "c9c9c9c9c9c9"
DEVA = re.compile("[ऀ-ॿ]")
BANNED = re.compile(r"\bpts\b|\bpp\b|\bpoints?\b|cohort|ARPDAU|eCPM|/1k|\bsettled\b|\blatest\b|\brecent\b|Verdict|Expected|Actual:|\bKeep\b", re.I)


def iso(d):
    return d.isoformat()


# ── the hand-made app: 200 days, every number known ──────────────────────────────────────────────────────────────────
H0 = date(2026, 3, 1)
HN = 200
HE = H0 + timedelta(days=HN - 1)                      # its data till (16 Sep)
HSA = HE - timedelta(days=3)                          # activity final till (13 Sep)
HSU = HE - timedelta(days=7)                          # install-day uninstalls final till (9 Sep)
STEP = 150                                            # from day 150 (29 Jul) the old users are 20% fewer
BREAK, INC = 130, 131                                 # a tracking break, an incomplete day (same day uninstall left out)


def wiggle(i, k):
    """A small deterministic day-to-day swing (±1.5%) — the app's own noise."""
    return 1 + 0.015 * math.sin(i * 1.7 + k) * math.cos(i * 0.31 + 2 * k)


def hand():
    new = [1000 + (i % 7) * 20 for i in range(HN)]
    ret = [round(9000 * wiggle(i, 1) * (0.8 if i >= STEP else 1.0)) for i in range(HN)]
    a1 = [ret[i] + new[i] for i in range(HN)]
    ur = ret[:]
    sr = [round(ur[i] * 2.0 * wiggle(i, 2)) for i in range(HN)]
    tr = [round(ur[i] * 300 * wiggle(i, 3)) for i in range(HN)]
    rev = [round(a1[i] * 0.02 * wiggle(i, 4), 4) for i in range(HN)]
    imps = [round(a1[i] * 3 * wiggle(i, 5)) for i in range(HN)]
    d1 = [round(new[i] * 0.25 * wiggle(i, 6)) for i in range(HN)]
    d7 = [round(new[i] * 0.12 * wiggle(i, 7)) for i in range(HN)]
    un0 = [round(new[i] * 0.30 * wiggle(i, 8)) for i in range(HN)]
    S = lambda v: {"r": v, "n": [0] * HN, "o": [0] * HN}   # noqa: E731
    adet = {"app_id": H_ID, "app": "Demo Hand Notes", "key": H_KEY, "currency": "USD", "data_till": iso(HE), "settled_till": iso(HSA),
            "daily": {"start": iso(H0), "a1": a1, "new": new, "ret": ret, "u": S(ur), "s": S(sr), "t": S(tr), "rev": rev, "imp": imps,
                      "coh": {"d1": d1, "d7": d7, "ok": [1] * HN, "t": new}}}
    arow = {"app_id": H_ID, "app": "Demo Hand Notes", "key": H_KEY, "file": "active_%s.json.gz" % H_KEY, "status": "ok",
            "data_till": iso(HE), "settled_till": iso(HSA)}
    udet = {"app_id": H_ID, "app": "Demo Hand Notes", "key": H_KEY, "data_till": iso(HE), "settled_till": iso(HSU),
            "history_start": iso(H0), "daily": {"breaks": [iso(H0 + timedelta(days=BREAK))]},
            "flags": {"incomplete_days": {iso(H0 + timedelta(days=INC)): 0.5}}, "launch": {"day": iso(H0), "hidden": False},
            "impact": {"updates": []}}
    coh = {"v": 1, "app_id": H_ID, "start": iso(H0), "end": iso(HE), "new": new, "lags": [[[0, un0[i]], [3, 40]] for i in range(HN)]}
    D = lambda i: iso(H0 + timedelta(days=i))   # noqa: E731
    cases = [{"id": "flat", "bf": D(100), "bt": D(106), "af": D(120), "at": D(126)},
             {"id": "step", "bf": D(136), "bt": D(142), "af": D(160), "at": D(166)},
             {"id": "final", "bf": D(170), "bt": D(176), "af": D(190), "at": D(199)},
             {"id": "short", "bf": D(1), "bt": D(90), "af": D(100), "at": D(196)},   # the whole history: nowhere to redo it
             {"id": "breaks", "bf": D(124), "bt": D(133), "af": D(140), "at": D(149)}]
    raw = {"new": new, "ret": ret, "a1": a1, "ur": ur, "sr": sr, "tr": tr, "rev": rev, "d1": d1, "d7": d7, "un0": un0}
    return {"adet": adet, "arow": arow, "udet": udet, "coh": coh, "cases": cases}, raw


def expect(raw, c):
    """The custom compare's numbers for a case, worked out here (the definitions the page must follow)."""
    ix = lambda s: (date.fromisoformat(s) - H0).days   # noqa: E731
    sa, su = (HSA - H0).days, (HSU - H0).days

    def days(f, t, last, sh=0):
        return [i for i in range(ix(f) - sh, ix(t) - sh + 1) if 0 <= i < HN and i <= last]
    out = {}
    for side, f, t in (("b", c["bf"], c["bt"]), ("a", c["af"], c["at"])):
        D = days(f, t, sa)
        mean = lambda v, L: sum(v[i] for i in L) / len(L) if L else None             # noqa: E731
        pool = lambda n, d, L: sum(n[i] for i in L) / sum(d[i] for i in L) if L else None   # noqa: E731
        out.setdefault("returning_dau", {})[side] = mean(raw["ret"], D)
        out.setdefault("sessions", {})[side] = pool(raw["sr"], raw["ur"], D)
        out.setdefault("time", {})[side] = pool(raw["tr"], raw["ur"], D)
        out.setdefault("arpdau", {})[side] = pool([x * 1000 for x in raw["rev"]], raw["a1"], D)
        for k, N in (("new_d1", 1), ("new_d7", 7)):
            L = days(f, t, sa - N, N if side == "b" else 0)
            out.setdefault(k, {})[side] = pool(raw["d1" if N == 1 else "d7"], raw["new"], L)
        L = [i for i in days(f, t, su) if i not in (BREAK, INC)]
        out.setdefault("uninstall_d0", {})[side] = pool(raw["un0"], raw["new"], L)
    return out


def build(d):
    st, rv = surge_store(surges=SURGES, ipu=lambda x, v: 3.5 if x >= END - timedelta(days=60) else 4.0)
    store = eng.fill_days(dict(st, window_end=END.isoformat()))
    udet, _ = eng.evaluate_app(store, A_ID, NAME, {}, NOW, key=KEY, revenue=rv)
    adet, arow = act.evaluate(store, A_ID, NAME, {}, NOW, udet, KEY, rv, None)
    arow = dict(arow, file="active_%s.json.gz" % KEY, status="ok")
    coh = eng.cohort_file(store)
    body, failed = ia.build_app(store, rv, A_ID, KEY, "sig-" + KEY, 7)
    assert failed == 0 and body["n"] > 100
    h, raw = hand()
    E = date.fromisoformat(adet["settled_till"])
    swap = [iso(E - timedelta(days=13)), iso(E - timedelta(days=7)), iso(E - timedelta(days=60)), iso(E - timedelta(days=54))]
    fx = {"today": (END + timedelta(days=2)).isoformat(), "app": {"app_id": A_ID, "app": NAME, "first": body["first"]},
          "udet": dict(udet, key=KEY), "adet": adet, "arow": arow, "coh": coh, "body": body,
          "entry": ia.index_entry(body, "impact_any_%s.json.gz" % KEY), "consts": dict(imp.CONSTS), "hand": h, "swap": swap,
          "catalog": [{"app_id": A_ID, "app_name": NAME, "account_id": "pub-1001"}, {"app_id": H_ID, "app_name": "Demo Hand Notes", "account_id": "pub-1001"}]}
    with open(os.path.join(d, "fx.json"), "w", encoding="utf-8") as f:
        json.dump(fx, f, ensure_ascii=False)
    return fx, raw


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("anycmp"))
    fx, raw = build(d)
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    path = os.path.join(d, "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "any_custom_frontend.js"), path, d], check=True,
                         capture_output=True, text=True, timeout=600)
    rep = json.loads(out.stdout)
    rep["_fx"], rep["_raw"] = fx, raw
    return rep


def test_renders_without_errors(report):
    assert report["errors"] == []


def test_the_cross_check_custom_compare_equals_the_engines_before_and_after(report):
    X = report["xcheck"]
    seven = X["7"]["full"]
    # 7 days: all seven rows, Before and After, on every date whose two windows are whole and final
    assert set(seven) == {"returning_dau", "new_d1", "new_d7", "sessions", "time", "arpdau", "uninstall_d0"}
    for k, c in seven.items():
        assert c["n"] >= 100, (k, c["n"])
        assert c["bad"] == [] and c["exact"] + c["digit"] == c["n"], (k, c)
        assert c["exact"] >= 0.98 * c["n"], (k, c)          # (revenue: the daily file keeps 4 decimals)
    for N in ("14", "30", "60"):
        full, after = X[N]["full"], X[N]["after"]
        # the rates (came back, same day uninstall) at 14 / 30 / 60: Before and After the same
        for k in ("new_d1", "new_d7", "uninstall_d0"):
            c = full[k]
            assert c["n"] >= 40 and c["bad"] == [] and c["exact"] + c["digit"] == c["n"], (N, k, c)
        # the per-day rows: the engine pairs weekdays for Before at 14+ (never the plain mean) — their After is the same
        for k in ("returning_dau", "sessions", "time", "arpdau"):
            c = after[k]
            assert c["n"] >= 40 and c["bad"] == [] and c["exact"] + c["digit"] == c["n"], (N, k, c)


def test_the_computation_on_hand_made_days(report):
    H, raw = report["hand"], report["_raw"]
    cases = {c["id"]: c for c in report["_fx"]["hand"]["cases"]}
    DP = {"returning_dau": 6, "new_d1": 9, "new_d7": 9, "sessions": 9, "time": 6, "arpdau": 9, "uninstall_d0": 9}
    for cid in ("flat", "step", "final", "breaks"):
        want = expect(raw, cases[cid])
        for k, w in want.items():
            for side in ("b", "a"):
                got = H[cid][k][side]
                if w[side] is None:
                    assert got is None, (cid, k, side, got)
                else:
                    assert got is not None and abs(got - w[side]) <= 10 ** -DP[k] * max(1, abs(w[side])), (cid, k, side, got, w[side])
    # came back: Pehle's install days are the ones whose day N is inside Pehle; Baad's are Baad's own days
    f = H["flat"]
    d = lambda i: iso(H0 + timedelta(days=i))   # noqa: E731
    assert f["new_d1"]["bs"] == [d(99), d(105)] and f["new_d1"]["as"] == [d(120), d(126)]
    assert f["new_d7"]["bs"] == [d(93), d(99)] and f["new_d7"]["as"] == [d(120), d(126)]
    assert f["uninstall_d0"]["bs"] == [d(100), d(106)]
    # the people a day a rate change means: Baad's installs a day
    assert abs(f["new_d1"]["perDay"] - sum(raw["new"][120:127]) / 7) < 1e-9
    # the noise test against the app's own swing: flat → No change; a 20% fall of old users → Worse (per user: unchanged)
    assert all(f[k]["st"] == "same" for k in f), {k: f[k]["st"] for k in f}
    s = H["step"]
    assert s["returning_dau"]["st"] == "worse" and s["returning_dau"]["z"] < -2 and s["returning_dau"]["nulls"] >= 20
    assert s["sessions"]["st"] == "same" and s["time"]["st"] == "same"
    assert "aam taur pe ±" in s["returning_dau"]["why"] and "— pakka" in s["returning_dau"]["why"]
    # the final-day cut: Baad 7–16 Sep → activity to 13 Sep (7 of 10), came back after 7 days: none yet → ⏳ Too early
    # (with the day it is ready), same day uninstall: to 9 Sep
    fi = H["final"]
    assert fi["new_d7"]["st"] == "early" and fi["new_d7"]["a"] is None and fi["new_d7"]["sub"].startswith("ready ~")
    assert "abhi pakke nahi" in fi["new_d7"]["why"]
    assert fi["uninstall_d0"]["as"] == [d(190), d(192)]
    assert "Baad me 10 me se 7 din pakke" in fi["returning_dau"]["why"]
    # a comparison the app's history has no room to redo ≥ 20 times (it spans nearly all of it): the numbers, no result
    sh = H["short"]
    assert sh["returning_dau"]["st"] == "na" and sh["returning_dau"]["sub"] == "history kam" and sh["returning_dau"]["b"] is not None
    # the tracking break and the incomplete day are left out of same day uninstall (but not of the other rows)
    br = H["breaks"]
    assert br["uninstall_d0"]["bs"] == [d(124), d(133)]
    assert abs(br["uninstall_d0"]["b"] - expect(raw, cases["breaks"])["uninstall_d0"]["b"]) < 1e-9


def test_the_custom_card_title_dates_line_one_line_note_one_table(report):
    C = report["hand"]["card"]
    c = report["_fx"]["hand"]["cases"][1]
    assert C["title"].startswith("📅 Custom: ") and " vs " in C["title"]
    assert re.match(r"^Pehle .+ \(7 din\) · Baad .+ · \(7 me se 7 din pakke\)$", C["dl"]), C["dl"]
    assert C["foot"].startswith("Custom compare: seedha pehle vs baad — trend adjust nahi.")
    assert C["heads"] == ["Metric", "Pehle", "Baad", "Badlaav", "Result"]
    assert list(C["rows"]) == ["returning_dau", "new_d1", "new_d7", "sessions", "time", "arpdau", "uninstall_d0"]
    r = C["rows"]["returning_dau"]
    assert r["st"] == "worse" and r["stt"].startswith("🔴 Worse") and "Kyun?" in r["stt"]
    assert re.match(r"^−[\d,]+/day \(−\d+(\.\d)?%\)$", r["cells"][2]), r["cells"]      # the number first, the % beside it
    d1 = C["rows"]["new_d1"]["cells"][2]
    assert re.match(r"^[+−]?[\d,]+/day \(\d+(\.\d)?%, was \d+(\.\d)?%\) roz ~[\d,]+ installs pe$", d1), d1
    assert C["save"].startswith("💾 Is tulna ko save karo:") and "Har app pe dikhao (all apps)" in C["save"] and "Naam zaroori hai" in C["save"]
    assert C["pickers"] == 0                                 # two ranges: no 7 / 14 / 30 / 60
    t = report["text_hand"]
    assert not DEVA.search(t) and not BANNED.search(t), BANNED.search(t)


def test_the_ranges_checks_swap_dates_and_quick_picks(report):
    G = report["ranges"]
    assert G["ok"] == {"ok": True, "bf": "2026-08-01", "bt": "2026-08-07", "af": "2026-09-01", "at": "2026-09-07", "swap": False}
    assert G["swap"] == {"ok": True, "bf": "2026-08-01", "bt": "2026-08-07", "af": "2026-09-01", "at": "2026-09-07", "swap": True}
    assert G["overlap"]["err"].startswith("Pehle aur Baad ke din ek dusre me aa rahe hain")
    assert G["backwards"]["err"].startswith("From date, To se pehle")
    assert G["long"]["err"] == "Ek range 400 din tak ki ho sakti hai"
    assert G["wait"]["wait"].startswith("Pehle aur Baad dono ki From / To chuno")
    # date vs date: N days from each date (the date itself in), the earlier one = Pehle
    assert G["dates"] == {"ok": True, "bf": "2026-08-01", "bt": "2026-08-07", "af": "2026-09-01", "at": "2026-09-07", "swap": False}
    assert G["dates_close"]["err"].startswith("Dono dates me kam se kam 7 din ka farak chahiye")
    assert G["dates_wait"]["wait"].startswith("Dono dates chuno")
    S = date.fromisoformat(G["last_final"])
    w = lambda a, b: [iso(S - timedelta(days=x)) for x in (a, b)]   # noqa: E731
    assert G["presets"]["prev"] == w(13, 7) + w(6, 0)
    assert G["presets"]["4w"] == w(34, 28) + w(6, 0)
    assert G["presets"]["prev30"] == w(59, 30) + w(29, 0)
    assert G["first_look"] == w(13, 7) + w(6, 0) and G["first_title"].startswith("📅 Custom: ")
    assert G["overlap_html"].startswith("⚠️ Pehle aur Baad ke din ek dusre me aa rahe hain") and G["overlap_no_card"]
    assert G["swap_note"][0] == "⇄ Pehle wali range baad ki thi — dono badal di (Pehle = purani range)"
    assert G["dates_pickers"] == 4 and G["dates_on"] == "14" and G["n_after"] == 30 and G["rng_pickers"] == 0
    assert G["dates_title"].startswith("📅 Custom: ")


def test_the_tabs_are_remembered_a_jump_opens_updates_one_picker_per_block(report):
    T = report["tabs"]
    assert T["tablist"] and T["labels"] == ["📦 Updates", "📅 Any date"] and T["default"] == "upd"
    assert T["updates_has_blocks"] and not T["section_picker"]
    assert T["block_pickers"] == T["open_blocks"] == 1                   # ONE 7 / 14 / 30 / 60, inside the open block
    assert T["saved"] == [["imp_tab_uni", "any"]] and T["any_box"] and T["any_pickers"] == 4
    assert T["remembered"] == "any"
    assert T["mode_saved"] == "cmp" and T["mode_remembered"] == "cmp"
    assert T["after_jump"] == "upd" and T["after_jump_card"] and T["jump_saved"] == "any"   # a jump is not a choice
    assert T["blocked_ok"] and T["blocked_default"] == "upd"
    assert T["uni_win"] is None                          # no hidden card-wide window from this browser
    # an auto-refresh re-draws from state: the tab, the mode, the ranges, the typed name, an open "Kyun?" — all kept (the
    # inputs keep their ids, so the page's focus restore finds them)
    assert T["refresh"] == {"same": True, "tab": True, "mode": True, "ranges": True, "name": True, "why": True, "ids": True}


def test_saving_a_custom_compare_through_the_marks_api(report):
    S, fx = report["save"], report["_fx"]
    assert S["disabled"] and S["enabled"] and S["label"] == "💾 Is tulna ko save karo:"
    assert S["placeholder"].startswith("Naam (zaroori)")
    sw = fx["swap"]
    assert S["ok"] is True and S["body"] == {"app_id": A_ID, "name": "Diwali vs pehle", "before_from": sw[2], "before_to": sw[3],
                                             "after_from": sw[0], "after_to": sw[1]}
    assert S["msg"] == "✅ Saved — team ko bhi dikhega"
    assert len(S["chips"]) == 1 and S["chips"][0][0] == "1" and S["chips"][0][1].startswith("📌 Diwali vs pehle · ") and S["chips"][0][2]
    assert S["del_button"] and S["title"].endswith(" · Diwali vs pehle")
    assert S["opened"] == {"mode": "cmp", "r": [sw[2], sw[3], sw[0], sw[1]], "name": "Diwali vs pehle", "cid": 1}
    assert S["star_app"] == "*"
    assert S["cid_before"] == 2 and S["del_body"] == {"id": 2, "kind": "compare"} and S["gone"] and S["cid_after"] == 0
    assert S["del_date_body"] == {"id": 7}                    # a date mark: the body every older page sends
    assert S["old_list"] == [0, 0, ""]                        # a Worker from before compares: the list reads
    assert S["old_ok"] is False and S["old_msg"].startswith("❌ Save nahi hua — Date galat hai (HTTP 400)")
