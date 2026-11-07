"""📉 CPI vs eCPM — the page side (owner, 6 Nov 2026: "short and direct view … sirf one view me direct pata chal jana chaiye,
lekin details dekhna he to kuchh miss nahi hona chahiye"). tests/cpx_frontend.js runs the CPX module of frontend/index.html
for real (a node vm, stub page helpers) on the SYNTHETIC build output of tests/cpx_fixture.js (SPEC §3.3 shapes); checked
here: inert at load; the picker (Last 14 days first, every standard key and the month keys → its dates, N days ending at
the alarm's data day t; Custom swapped / clamped; the saved choice); the "now" sums in ₹ (as billed) and $ (each day's own
rate) against hand math, CPI judged in ₹; normal / status / since / money of SPEC §1.2 for the default view (the pointer,
no file) and other periods (cpi.json.gz); the list's order, the summary and the footer; the file states (⏳ Loading… /
⚠️ + Try again / a refused file); the details (verdict, money line, every tab); one app; keep() — no page jump — at 375 and
1280 px; the Chart tab's three charts moving together (one 14-day window on all three, matched by its end date); the
developer copy; a hostile app name escaped; cpx- classes only; and the wiring into the page (gated on DATA.cpi). The level agent's part (AGENT SPEC §7, tests T-P1 … T-P9): its answer in the row tag, the lines under the verdict,
the scoreboard, the level rows it marks, the Agent decisions list, the owner's buttons; nothing of it without its fields.
Skipped where node is not installed. No real data."""
import json
import os
import re
import shutil
import subprocess
from datetime import date, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
PAGE = os.path.join(ROOT, "frontend", "index.html")
A, B, C_, D, E_, H, Z = ("ca-app-pub-0000000000000000~2%d" % i for i in range(1, 8))
DAY0, T, TODAY = date(2025, 10, 1), date(2026, 3, 28), date(2026, 3, 30)


def _page():
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def out():
    if NODE is None:
        pytest.skip("node is not installed")
    r = subprocess.run([NODE, os.path.join(ROOT, "tests", "cpx_frontend.js"), PAGE],
                       check=True, capture_output=True, text=True, timeout=120)
    rep = json.loads(r.stdout)
    assert not rep["errors"], rep["errors"]
    return rep["out"]


# ── the fixture's closed forms (hand math) ──
def fxd(d):                       # the day's own USD per ₹ (alternating; day0 = 0.0122)
    return 0.0122 if ((d - DAY0).days + 1) % 2 else 0.0118


def days(a, b):
    a, b = date.fromisoformat(a), date.fromisoformat(b)
    return [a + timedelta(k) for k in range((b - a).days + 1)]


def by(rows):
    return {r["id"]: r for r in rows}


def test_inert_at_load_and_the_pointer(out):
    assert out["inert"] == {"loads": 0, "html": ""}                               # no fetch, no DOM before the first paint
    assert out["no_ptr"]["ptr"] is None and out["no_ptr"]["n"] == 0 and out["no_ptr"]["card"] is None
    assert "data is build me nahi bana" in out["no_ptr"]["text"]
    assert out["bad_v"] is None and out["bad_apps"] is None
    assert out["bad_file"]["loads"] == [] and "Data load nahi hua" in out["bad_file"]["text"]   # a bad file name is never fetched


def test_picker_dates(out):
    r = out["rng"]
    assert out["cal"] == {"t": "2026-03-28", "td": "2026-03-30", "d0": "2025-10-01"}
    assert r["14"] == ["2026-03-15", "2026-03-28"] and r["7"] == ["2026-03-22", "2026-03-28"]   # N days end at t
    assert r["30"] == ["2026-02-27", "2026-03-28"] and r["60"] == ["2026-01-28", "2026-03-28"] and r["90"] == ["2025-12-29", "2026-03-28"]
    assert r["today"] == ["2026-03-30", "2026-03-30"] and r["yday"] == ["2026-03-29", "2026-03-29"]   # after t (not final)
    assert r["tm"] == ["2026-03-01", "2026-03-30"] and r["lm"] == ["2026-02-01", "2026-02-28"]
    assert r["mon:2026-02"] == ["2026-02-01", "2026-02-28"] and r["mon:2026-03"] == ["2026-03-01", "2026-03-30"]
    assert r["mon:2025-06"] == r["14"] and r["bogus"] == r["14"]                         # outside the data / unknown: the default
    assert r["all"] == ["2025-10-01", "2026-03-30"]
    assert r["cus"] == ["2026-03-10", "2026-03-20"] and r["cus_clamp"] == ["2025-10-01", "2026-03-30"] and r["cus_empty"] == r["14"]


def test_saved_period_per_viewer(out):
    s = out["restore"]
    assert s["k14"]["k"] == "14" and s["mon"]["k"] == "mon:2026-01"
    assert s["monOld"] is None and s["monNew"] is None and s["bad"] is None and s["junk"] is None and s["half"] is None
    assert s["cus"] == {"k": "cus", "f": "2025-10-01", "t": "2026-03-20"}              # swapped + clamped
    assert out["ls_throw"] == "14" and out["ls_read"] == "30"                           # a throwing localStorage is harmless


def test_now_sums_rupee_as_billed_and_dollar_dated(out):
    i, u = out["sums"]["INR"], out["sums"]["USD"]
    d14 = days("2026-03-15", "2026-03-28")
    # Alpha: ₹50,000 a day, 1,600 installs, eCPM $5, D0 value 30 % of spend
    assert i["a14"]["spi"] == pytest.approx(700000) and i["a14"]["sp"] == pytest.approx(700000)
    assert i["a14"]["n"] == pytest.approx(22400) and i["a14"]["cpi"] == pytest.approx(31.25) and i["a14"]["cpiV"] == pytest.approx(31.25)
    assert i["a14"]["ecpm"] == pytest.approx(5) and i["a14"]["roas"] == pytest.approx(0.30, abs=1e-6)
    usd = sum(50000 * fxd(d) for d in d14)
    assert u["a14"]["sp"] == pytest.approx(usd, abs=0.01) and u["a14"]["spi"] == pytest.approx(700000)   # ₹ stays as billed
    assert u["a14"]["cpiV"] == pytest.approx(usd / 22400, rel=1e-6) and u["a14"]["cpi"] == pytest.approx(31.25)   # judged in ₹
    assert u["a14"]["ecpm"] == i["a14"]["ecpm"] and u["a14"]["roas"] == i["a14"]["roas"]   # eCPM $ and D0 ROAS ₹÷₹ in both
    # Beta: CPI ₹20,000 ÷ 1,538.46 (2 dp) a day
    assert i["b14"]["cpi"] == pytest.approx(280000 / (14 * 1538.46), rel=1e-9)
    # Epsilon (7 days): spend only on 22–24 Mar; nothing on t−2..t
    d7 = days("2026-03-22", "2026-03-24")
    assert i["e7"]["spi"] == pytest.approx(18000) and i["e7"]["last3"] == 0
    assert u["e7"]["sp"] == pytest.approx(sum(6000 * fxd(d) for d in d7), abs=0.01)
    assert u["e7"]["k"] == pytest.approx(u["e7"]["sp"] / 18000)
    assert u["ay"]["sp"] == pytest.approx(50000 * fxd(date(2026, 3, 29)), abs=0.01)
    assert i["a14"] and out["sums"]["INR"]["memo"] and out["sums"]["USD"]["memo"]       # kept per (DATA, period, currency)


def test_default_view_comes_from_the_pointer(out):
    d = out["def"]
    assert d["loads"] == []                                                             # painted without any file
    rows = by(d["rows"])
    assert [rows[k]["st"] for k in (A, B, C_, Z, D, E_)] == ["alarm", "watch", "ok", "ok", "new", "paused"]
    assert H not in rows                                                                # hidden in Settings
    assert d["order"] == [A, B, C_, Z, D, E_]                                           # Alarm, Watch, OK, New, Paused (then money, spend)
    a = rows[A]
    assert a["since"] == "2026-03-10" and a["nrm"] == {"CPI": [20, 1], "ECPM": [6, 1], "ROAS_G": [0.4, 1]}   # the frozen baselines
    assert a["lost"]["inr"] == pytest.approx(175000) and a["lost"]["usd"] == pytest.approx(2100)      # the build's period number
    since = days("2026-03-10", "2026-03-28")                                            # since c: 19 days × (50,000 − 15,000 ÷ 0.4)
    assert a["lost"]["sinr"] == pytest.approx(19 * 12500) and a["lost"]["susd"] == pytest.approx(sum(12500 * fxd(x) for x in since), abs=0.01)
    assert a["lost"]["pre"] and a["lost"]["from"] == "2026-03-10"
    assert rows[B]["nrm"]["CPI"] == [10, 1] and rows[B]["nrm"]["ECPM"] == [3, 0] and rows[B]["lost"] is None
    assert rows[D]["nrm"] == {"CPI": None, "ECPM": None, "ROAS_G": None}
    t = d["text"]
    assert "Data till 28 Mar 2026 (final) · Last check 30 Mar, 10:52 IST" in t
    assert "● 1 Alarm ● 1 Watch ● 2 OK · Money lost: ≈₹1.8 L" in t
    assert "Alpha App spend ₹7.0 L · since 10 Mar (19 din) ₹31.3 +56% vs ₹20.0 $5.00 −17% vs $6.00 30.0% −25% vs 40.0% 10 Mar 19 din se" in t
    assert "Alarm ≈₹1.8 L since 10 Mar: ≈₹2.4 L" in t
    assert "no normal yet" in t and "Not linked spend: ₹12.3k (3 store ids) — Marketing ROAS me" in t
    # the $ view: the same words, the numbers at each day's own rate; the % the same (CPI's $ normal at the period's rate)
    u = out["def_usd"]["text"]
    assert "Money lost: ≈$2,100" in u and "$0.38 +56% vs $0.24" in u and "since 10 Mar: ≈$2,853" in u


def test_not_linked_spend_follows_the_period_picked(out):
    """The pointer ships the unlinked spend per day (+ each store id's runs of days): the footer sums the picked period
    (₹ or $) and counts the store ids with spend inside it; the old one-total shape is shown as it is."""
    f = out["foot"]
    assert f["d14"] == "Not linked spend: ₹900 (2 store ids) —" and f["d7"] == "Not linked spend: ₹700 (2 store ids) —"
    assert f["cus"] == "Not linked spend: ₹500 (1 store id) —"                          # 20–24 Mar: the second store id starts on 25 Mar
    assert f["cus_late"] == "Not linked spend: ₹300 (2 store ids) —" and f["all"] == f["d14"]
    assert f["d7_usd"] == "Not linked spend: $7.00 (2 store ids) —"                       # the $ view: the dated $ series
    assert f["yday"] is None and f["before"] is None and f["junk"] is None                # nothing in the period / a bad shape: no line
    assert f["old_shape"] == "Not linked spend: ₹12.3k (3 store ids) —"


def test_other_periods_are_judged_by_the_page(out):
    w = out["p7_wait"]
    assert all(r["wait"] for r in w["rows"]) and "⏳ Loading…" in w["text"] and "● … Alarm" in w["text"]
    assert out["p7"]["loads"] == ["cpi.json.gz"]
    p7 = by(out["p7"]["rows"])
    assert p7[A]["st"] == "alarm" and p7[A]["since"] == "2026-03-10" and p7[A]["lost"]["inr"] == pytest.approx(7 * 12500)
    assert p7[A]["lost"]["usd"] == pytest.approx(sum(12500 * fxd(x) for x in days("2026-03-22", "2026-03-28")), abs=0.01)
    assert p7[E_]["st"] == "paused" and p7[D]["st"] == "new" and p7[C_]["st"] == "ok"
    # December: the old D0 ROAS alarm (closed 20 Dec) — Dec 1–15 at 33 % vs B 40 %, then normal again
    dec = by(out["pdec"])
    assert dec[A]["st"] == "fixed" and dec[A]["since"] == "2025-12-01" and not dec[A]["lost"]["pre"]   # closed inside the month
    assert dec[A]["nrm"]["ROAS_G"] == [0.4, 0]                                          # closed by the period's end: the healthy level
    assert dec[A]["lost"]["inr"] == pytest.approx(15 * (50000 - 50000 * 0.33 / 0.4))
    usd = by(out["pdec_usd"])[A]["lost"]["usd"]
    assert usd == pytest.approx(sum(8750 * fxd(x) for x in days("2025-12-01", "2025-12-15")), abs=0.01)
    assert D not in dec                                                                 # no spend in the period: no row
    feb = by(out["pfeb"])
    assert {k: v["st"] for k, v in feb.items()} == {A: "ok", B: "ok", C_: "ok", E_: "ok", Z: "ok"}
    assert feb[A]["nrm"] == {"CPI": [20, 0], "ECPM": [6, 0], "ROAS_G": [0.4, 0]} and feb[A]["lost"] is None
    y = by(out["pyday"])[A]                                                             # Yesterday (after t): D0 not final
    assert y["st"] == "alarm" and y["lost"]["na"] and y["lost"]["sinr"] == pytest.approx(19 * 12500)
    assert by(out["p14_from_file"])[A] == by(out["def"]["rows"])[A]                     # the default view: the pointer, file or not


def test_normal_and_status_rules(out):
    n = out["normal"]
    assert n["open"] == {"v": 33, "b": 1, "c": "2026-02-20", "src": "B"}                # open at the period's end: its baseline
    assert n["settled"] == {"v": 99, "b": 1, "c": "2026-02-20", "src": "B"}             # D1: a settled one counts as open until its close
    assert n["closed"] == {"v": 20, "b": 0, "src": "H0", "on": None}                    # closed by then: H the day before
    assert n["later"] == {"v": 20, "b": 0, "src": "H0", "on": None}                     # opened after the period: not yet
    assert n["h"] == {"v": 6, "b": 0, "src": "H0", "on": None} and n["after_t"] == {"v": 6, "b": 0, "src": "H0", "on": None}   # after t: the last shipped day
    j = out["judge"]
    assert j["line"]["w"] is None and j["line"]["since"] is None and j["line"]["fam"] is None and j["line"]["e"] is None   # a LINE never sets the status
    # Alarm / Watch need an episode still OPEN at the period's end: the open D0 ROAS alarm, not the closed GAP one
    assert (j["two"]["w"], j["two"]["since"], j["two"]["fam"]) == (0, "2026-03-12", "ROAS_G")
    assert j["two"]["e"]["fam"] == "ROAS_G" and j["two"]["e"]["closed"] is None             # … and the episode itself
    # an ALERT that closed inside the period → Fixed (grade 2) with its own change start; a closed WATCH says nothing
    assert (j["fixed"]["w"], j["fixed"]["since"], j["fixed"]["fam"]) == (2, "2026-03-05", "GAP")
    assert j["late"]["w"] is None                                     # opened after the period's end: not known then


def test_d1_settled_is_open_until_its_close(out):
    d = out["d1"]
    assert d["open"] == {"v": 99, "b": 1, "c": "2026-02-20", "src": "B"}                # closes after the period's end: B on the whole period
    assert d["on_close"]["b"] == 0 and d["on_close"]["v"] == 20                        # closed by the period's end (on that day): skipped → H
    assert d["closed"]["b"] == 0 and d["closed"]["v"] == 20


def test_d2_money_only_from_the_d0_roas_episodes(out):
    d = out["d2"]
    assert d["gamma"]["st"] == "alarm" and d["gamma"]["lost"] is None                   # an AdMob install-day alarm: a status, no money
    assert d["beta_def"] is None                                                        # a pointer number of that line: not shown
    assert d["sum"].startswith("Money lost: ≈₹87.5k") and d["money_line"] == ""         # only Alpha's D0 ROAS days (7 × ₹12,500)
    assert "lossC0" not in _page()                                                      # the AdMob loss lives only in the Loss math tab
    lm = out["lm"]["def"]
    assert "AdMob D0 pe: loss = $6,590 − $1,779 ÷ 50.0% = ≈$3,031" in lm and "list / summary / sort me sirf Google D0 ka nuksaan" in lm
    h = out["hist"]
    assert "≈₹10.3 L" in h and "≈₹2.4 L" in h                                           # the D0 ROAS rows' money (the AdMob line shows "—")
    assert "Install-day ROAS D0 (AdMob) down Slow drift Open Line 11 Mar 2026 22 Mar 2026 — 50.0% −20% —" in h


def test_d3_normal_never_turns_every_app_new(out):
    d = out["d3"]
    st = d["all"]["st"]                                                                 # All time: H(a−1) does not exist → the first known H inside
    assert [st[k] for k in (A, B, C_, E_, Z, D)] == ["alarm", "watch", "ok", "ok", "ok", "new"]    # only the truly new app is New
    assert d["all"]["nrm"]["CPI"] == {"v": 20, "b": 0, "src": "Hin", "on": "2025-10-29"}
    assert d["all"]["a"]["ROAS_G"]["b"] == 1 and d["all"]["a"]["ROAS_G"]["src"] == "B"   # an episode open at the end: its baseline
    assert "normal = 29 Oct 2025 level" in d["all"]["cell"]                                  # the cell says which normal it is
    assert d["all"]["verdict"].startswith("Sab normal ke andar: CPI ₹20.0 → ₹20.0")
    e = d["early"]                                                                      # an early Custom (starts at day0)
    assert set(e["st"].values()) == {"ok"} and e["nrm"]["ROAS_G"]["src"] == "Hin" and "normal = 29 Oct 2025 level" in e["cell"]
    p = d["pre"]                                                                        # a period that ends before any healthy level exists
    assert set(p["st"].values()) == {"new"} and "no normal yet" in p["cell"]
    assert "history kam hai" not in p["verdict"] and p["verdict"].startswith("Normal nahi bana — period ke end tak")
    assert d["h"] == {"v": 5, "b": 0, "src": "Hin", "on": "2025-10-03"}                 # first known inside [a, b]
    assert d["h0"]["src"] == "H0" and d["h0"]["v"] == 6 and d["h_none"] is None and d["h_after"]["v"] == 7


def test_d4_d0_roas_now_counts_days_up_to_t(out):
    d = out["d4"]
    # This month (1 Mar … today): D0 ROAS on 1–28 Mar only: (9 × 40 % + 19 × 30 %) of ₹50,000 a day ÷ 28 days
    assert d["tm"]["roas"] == pytest.approx((9 * 0.4 + 19 * 0.3) / 28) and d["tm"]["till"] == "2026-03-28" and not d["tm"]["nf"]
    assert d["tm"]["sp1"] == pytest.approx(28 * 50000 * 0.012 * 1e6)                    # (the spend of those 28 days only)
    assert "33.2% −17% vs 40.0% till 28 Mar" in d["text_tm"]
    assert d["today"]["roas"] is None and d["today"]["nf"] and "— not final yet" in d["text_today"]
    assert d["d14"] == {"till": None, "nf": False} and not d["till_in_14"]              # a period ending at t: no note


def test_since_n_din_only_while_open_at_the_period_end(out):
    s = out["since"]
    c = s["closed"]                                                                     # December: the alarm closed on 20 Dec
    assert c["since"] == "2025-12-01" and not c["open"] and c["to"] == "2025-12-20" and not c["din"]
    assert "spend ₹15.5 L · 1 Dec – 20 Dec 2025" in c["text"] and "1 Dec – 20 Dec 2025 Fixed" in c["text"]   # (a past year keeps its year)
    assert c["verdict"].startswith("D0 ROAS 1 Dec – 20 Dec 2025 normal se neeche rahi (ab band). Is period me 36.6% (normal 40.0%)")
    o = s["open_at_b"]                                                                  # 1–10 Dec: still open on the last day → "N din se"
    assert o["open"] and "since 1 Dec 2025 (10 din)" in o["text"] and "1 Dec 2025 10 din se" in o["text"]
    assert o["verdict"].startswith("D0 ROAS 1 Dec 2025 se normal se neeche: 33.0% (normal 40.0%)")
    assert "20 Mar – closed" in s["def_closed"]["text"] and "din se" not in s["def_closed"]["text"].split("Alarm")[0]   # the pointer lists open ones only
    assert s["def_closed"]["n"] == 1 and out["sc"]                                      # (a closed alarm is not an open Alarm) · the pointer's lost.sc is the default "since c"


def test_nav_badge_and_alerts_note_count_open_alert_episodes(out):
    assert out["alarm0"] == 1                                                           # a closed alarm the window still touches: not counted
    a = out["alarm1"]
    assert a["n"] == 2 and "<b>2 alarm</b>" in a["note"] and "<b>1 alarm</b>" in a["note_beta"]   # an open ALERT episode on another app: counted


def test_loss_math_baseline_and_ratio_column(out):
    lm = out["lm"]
    assert "÷ 36.0% = ≈$0.00 (normal period se ek din pehle ka healthy level" in lm["feb"]            # no open C0 episode: H the day before
    assert "÷ 36.0% = ≈$1,573 (normal period ka pehla healthy level, 29 Oct 2025" in lm["early"]          # before H exists: the first known inside
    assert "÷ 50.0% = ≈$3,031 (normal alarm se pehle ka" in lm["def"]                                 # an episode open at the end: its baseline
    assert out["lm_head"]                                                                             # Ratio right after Month


def test_file_states(out):
    f = out["all_fail"]
    assert "⚠️ Data load nahi hua. Try again" in f["text"] and f["retry"] and "normal —" in f["text"]
    assert out["all_retry"] == {"loads": ["cpi.json.gz"], "wait": False}
    assert out["open1"]["wait"] and out["open1"]["loads"] == ["cpi_c0000000000a.json.gz"]
    assert "⚠️ Data load nahi hua. Try again" in out["app_fail"]["text"] and out["app_fail"]["retry"]
    assert out["app_retry"] == {"loads": ["cpi_c0000000000c.json.gz"], "ok": True}
    assert "⚠️ Data load nahi hua" in out["wrong_key"]                                   # a file of another key is refused
    assert out["bad_key"]["loads"] == [] and "detail file nahi bani" in out["bad_key"]["text"]


def test_details_and_every_tab(out):
    assert out["verdict"] == "D0 ROAS 10 Mar se normal se neeche: 30.0% (normal 40.0%). CPI ₹20.0 → ₹31.3 , eCPM $6.00 → $5.00 ."
    assert out["money"] == ("💸 ≈₹2.4 L zyada kharch hua — 10 Mar se ab tak ₹9.5 L spend pe utni hi D0 value normal ROAS (40.0%) "
                            "pe sirf ₹7.1 L me milti.")
    tb = out["tabs"]
    assert not any(v["err"] for v in tb.values())
    assert tb["ch"]["svgs"] == 3 and out["chd"] == ["cpx-c1", "cpx-c2", "cpx-c3"]
    assert tb["ch"]["labels"] == ["₹20.0", "₹31.3", "normal ₹20.0", "$6.00", "$5.00", "normal $6.00", "40.0%", "30.0%", "normal 40.0%"]
    s = out["series"]                                                                   # 14-day sums: ₹ ÷ installs
    assert s[0] == ["2026-03-01", 20, 20] and s[-1] == ["2026-03-28", 31.25, 20]
    assert s[9][1] == pytest.approx(700000 / (13 * 2500 + 1600))                        # 10 Mar: one day at 1,600 installs
    su = out["series_usd"][-1]
    assert su[1] == pytest.approx(sum(50000 * fxd(x) for x in days("2026-03-15", "2026-03-28")) / 22400)
    assert su[2] == pytest.approx(20 * su[1] / 31.25)                                   # the $ normal at the window's rate
    dw = out["day"]
    assert [z[:2] for z in dw["first"]] == [["2026-03-30", True], ["2026-03-29", True], ["2026-03-28", False], ["2026-03-27", False]]
    assert dw["rows"] == [31, 61, 60]                                                   # 30 rows (+ head), Show 30 more
    assert [f["fam"] for f in dw["t"]["fams"]] == ["ROAS_G", "CPI", "ECPM"]             # the open families that day
    assert "Rest 5% ₹35.0k — —" in tb["cc"]["text"] and "≈ app installs" not in tb["cc"]["text"]   # the Rest row: its spend and share only
    assert "⚠️ CPI up · since 12 Mar" in tb["cc"]["text"]
    assert "tROAS · target 55.0%" in tb["cp"]["text"] and "tCPA · target not known" in tb["cp"]["text"]
    assert "1 campaign ka is period me spend nahi" in tb["cp"]["text"]
    assert "Same country mix pe (normal span ke weights) price ka badlaav: −17%" in tb["ek"]["text"]
    assert "Sirf mix badalne se (purane eCPM pe): −4%" in tb["ek"]["text"] and "AdMob Network" in tb["ek"]["text"]
    assert "= ₹7.0 L − ₹5.3 L = ≈₹1.8 L" in tb["lm"]["text"] and "= ₹9.5 L − ₹7.1 L = ≈₹2.4 L" in tb["lm"]["text"]
    assert "1.11×" in tb["lm"]["text"]                                                  # Google D0 ÷ AdMob D0 (fixture: 1 ÷ 0.9)
    h = tb["hi"]["text"]
    assert h.index("Install-day ROAS D0 (AdMob) down") < h.index("Closed · recovered")  # newest first
    assert "≈₹10.3 L" in h and "₹20.0 +56%" in h


def test_one_row_open_at_a_time_and_one_app(out):
    assert out["open2"] == {"open": B, "tab": "ch", "dets": 1} and out["close"] == {"open": None, "dets": 0}
    o = out["one"]
    assert o["rows"] == 1 and o["open"] == A and o["det"] and not o["name"] and not o["sum"] and o["after_tap"] == A
    assert "Is app ka is period me Google Ads spend nahi" in o["none"]


def test_keep_no_page_jump(out):
    for w in ("375", "1280"):
        k = out["keep"][w]
        assert k["dy"] == [-120] and k["open"] == C_ and k["held"] == "900px"          # the tapped row back in place, height held
        assert k["close"]["open"] is None
    assert out["keep"]["push_375"] == ["cpx-dd"] and out["keep"]["push_1280"] == []     # a phone's Back closes the details


def test_picker_controls(out):
    assert out["sel"] == "60" and out["sel_bad"] == "60"
    assert out["mon"] == ["mon:2026-02", ["2026-02-01", "2026-02-28"]]
    assert out["cus"] == ["cus", ["2026-02-28", "2026-03-02"]]
    assert out["mover"] == ["mon:2026-01", "mon:2026-02", "mon:2026-03"]
    assert out["roas_link"] == ["roas"]


def test_outside_the_screen(out):
    assert out["alarmN"] == 1 and out["alarmN_beta"] == 1                                # the nav badge: every visible app
    assert "📉 CPI vs eCPM: <b>1 alarm</b>" in out["note"] and "show('cpx')" in out["note"]
    assert out["note_beta"] == ""                                                       # the header's app has none
    c = out["card"]
    assert c["a"]["st"] == "bigda" and c["a"]["line"].startswith("<b>Alarm</b> since 10 Mar · CPI ₹31.3 (+56%)") and "≈₹1.8 L lost" in c["a"]["line"]
    assert c["b"]["st"] == "dhyan" and c["c"]["st"] == "normal" and c["d"]["st"] == "jaldi" and c["none"]["st"] == "lagu"


def test_developer_copy_shows_nothing(out):
    assert out["dev"] == {"ptr": None, "html": "", "n": 0, "note": "", "card": None}


def test_hostile_name_and_classes(out):
    assert not out["def"]["hostile_raw"] and out["def"]["hostile_esc"]
    for c in out["classes"]:
        assert c.startswith("cpx-") or c in ("card", "aicon"), c                        # (aicon: the page's own icon helper)
    assert len(out["ids"]) == len(set(out["ids"])) and all(i.startswith('id="cpx-') for i in out["ids"])
    assert out["bad_words"] == []


def test_wiring():
    p = _page()
    assert ('<li id="nav-cpx-li" hidden><button data-screen="cpx"><span class="i">📉</span> CPI vs eCPM '
            '<span class="badge" id="nav-cpx" hidden></span></button></li>') in p
    assert p.index('data-screen="roas"><span class="i">💰</span> Marketing ROAS') < p.index('id="nav-cpx-li"') < p.index('data-screen="value"><span class="i">💸</span>')
    assert "try{ root.append(renderCpx()); }catch(e){}" in p and "li.hidden=!CPX.ptr()" in p and "bd.hidden=!n" in p
    assert "if(id==='cpx') CPX.show(); else CPX.left();" in p
    assert 'cpx:["CPI vs eCPM",' in p
    assert re.search(r"cpx:\['CPI vs eCPM','📉','cpx','cpx'\]", p)
    assert re.search(r"const HUB_ALL=\[[^\]]*'roas','cpx'", p) and re.search(r"const HUB_APP=\[[^\]]*'roas','cpx'", p)
    assert "(t!=='cpx'||cx)" in p and "cx=!!CPX.ptr()" in p and "(c[0]!=='cpx'||cx)" in p
    assert "['cpx','cpx','CPI vs eCPM','📉','cpx']" in p and "['roas','roas','Marketing ROAS','💰','rv:ads']" in p   # the ROAS card untouched
    assert "if(src==='cpx'){ try{ return CPX.card(name)" in p
    assert 'body[data-screen="cpx"] #rangectl,body[data-screen="cpx"] #rangecustom,body[data-screen="cpx"] #rangemon{display:none!important}' in p
    assert 'body[data-screen="cpx"] #smp-pick{display:inline-flex}' in p
    alerts = p[p.index("function renderAlerts(){"):p.index("// ---------- DEDUCTIONS")]
    assert "try{ cpn=CPX.alertNote(); }catch(e){}" in alerts and "${ga4}${cpn}" in alerts
    # the module: no top-level DOM / storage work; its own cpx- classes only (never the global 'chip'); no class 'cpi-'
    m = p[p.index("const CPX=(()=>{"):p.index("function renderCpx(){")]
    assert 'class="chip' not in m and "'chip'" not in m and "cpx-tab" in m
    for c in re.findall(r'class="([^"$]+)"', m):
        for w in c.split():
            assert w.startswith("cpx-") or w in ("card", "ct", "note", "lnk"), w        # (the Alerts note uses the page's own)
    assert m.index("localStorage") > m.index("function perLoad")
    assert "window.__DEV_VIEW__" in m


def test_list_layout_fits_every_width():
    p = _page()
    m = p[p.index("/* ---- 📉 CPI vs eCPM (CPX)"):p.index("/* ---------- 👥 Audience")]
    # the screen is its own container: the list lays itself out by the room it has (the sidebar takes 220 px of a wide window)
    assert re.search(r'\.screen\[data-screen="cpx"\]\{[^}]*container:cpx/inline-size', m)
    base = m[m.index(".cpx-row{display:grid"):m.index("@container cpx")]
    assert 'grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"app loss" "m m"' in base   # the default = the 2-line card
    q = m[m.index("@container cpx (min-width:900px)"):m.index("@media (max-width:760px)")]
    tracks = re.search(r"grid-template-columns:([^;]+);grid-template-areas:none", q).group(1)
    assert "minmax(0,1.9fr) repeat(3,minmax(0,1fr))" in tracks                           # shrinkable tracks: nothing can push Money lost out
    assert not re.search(r"minmax\(\d+px", tracks)                                        # … no fixed minimum
    px = sum(int(x) for x in re.findall(r"(?<![\d.(,])(\d+)px", tracks))
    assert px + 7 * 10 + 28 + 100 + 4 * 95 <= 900                                       # fixed tracks + gaps + padding + 4 flexible columns ≥ 95 px fit 900 px
    assert "@media (min-width:761px){.cpx-mob" not in m                                  # (the old viewport rule that cut the Money column)
    assert "grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr))" in m     # the charts: 3 / 2 / 1 across by the room


def test_no_owner_data_in_the_fixture():
    with open(os.path.join(ROOT, "tests", "cpx_fixture.js"), encoding="utf-8") as f:
        src = f.read()
    ids = set(re.findall(r"ca-app-pub-\d{16}~\d+", src))
    assert ids and all(i.startswith("ca-app-pub-0000000000000000~") for i in ids)
    assert set(re.findall(r"com\.[a-z0-9_.]+", src)) <= {"com.synth."}


def test_chart_country_picker_drives_the_same_three_charts(out):
    c = out["cty"]
    # All countries first (default): the app's three charts exactly as before; the file's countries by the period's spend share
    assert c["all"]["opts"] == [["", True, "All countries"], ["IN", False, "[IN] Name IN · 60%"], ["US", False, "[US] Name US · 25%"],
                                ["BR", False, "[BR] Name BR · 10%"]]
    assert c["list"] == [["IN", 0.6], ["US", 0.25], ["BR", 0.1]] and c["ls_read"]
    assert c["all"]["titles"] == ["CPI ₹ (cost ÷ installs)", "eCPM $ (AdMob)", "D0 ROAS (Google D0 ÷ cost)"]
    assert c["all"]["labels"] == out["tabs"]["ch"]["labels"] and c["all"]["svgs"] == 3
    # a country: the SAME three charts (never a fourth) from its own lines, its own normal printed; remembered per app
    us = c["us"]
    assert us["svgs"] == 3 and us["titles"] == ["CPI ₹ (cost ÷ downloads)", "eCPM $ (AdMob country)", "D0 ROAS (AdMob-matched)"]
    assert us["labels"] == ["₹20.0", "₹31.3", "normal ₹20.0", "$9.60", "$8.00", "normal $9.60", "43.2%", "32.4%", "normal 43.2%"]
    assert [o[0] for o in us["opts"] if o[1]] == ["US"] and "Teeno chart sirf is country ke" in us["text"]
    assert json.loads(c["ls"]) == {A: "US"} and json.loads(c["ls2"]) == {}
    assert "AdMob-matched" in us["text"] and "sirf matured din" in us["text"] and "1 Nov 2025 se" in us["text"]
    # the 14-day sums = hand math on the country's own arrays (D0 ROAS: r0 ÷ $ cost; unknown r0 → no point, the normal kept)
    for x, v, n, h in c["us_roas"]:
        assert n == 0.432 and (v is None) == (h is None) and (v is None or v == pytest.approx(h, rel=1e-9))
    assert [r[1] for r in c["us_roas"]][-3:] == [None] * 3 and c["us_roas"][5][1] == pytest.approx(0.324)
    assert all(v == pytest.approx(h) and n == 20 for _, v, n, h in c["us_cpi"]) and c["us_cpi"][0][1] == pytest.approx(31.25)
    assert c["us_ecpm"][0][1] == pytest.approx(c["us_ecpm"][0][3]) and c["us_ecpm"][0][2] == 9.6
    (x, v, n, (hv, hn)), = c["us_cpi_usd"]                    # $ view: dated $ ÷ downloads; the ₹ normal × the window's own rate
    assert v == pytest.approx(hv) and n == pytest.approx(hn)
    # a country without its D0 in this build: two charts + a note (never a chart of zeros); its own LINE episode shaded
    assert c["br"]["svgs"] == 2 and "country-wise install-day revenue nahi" in c["br"]["text"] and c["br"]["shade"] == 1
    assert c["bad"] == "BR"                                   # a code the file does not have: refused
    assert c["back"]["titles"] == c["all"]["titles"] and c["back"]["labels"] == c["all"]["labels"]
    # read once per viewer; a code the file no longer has → All countries; a throwing storage never breaks the charts
    assert c["read"] == ["IN", ""]
    assert c["throw"]["titles"] == c["all"]["titles"] and not c["throw"]["err"] and c["throw"]["after"] == us["titles"]
    # no page jump: the picker goes back to its place; an app file with no country: no picker, the charts as before
    assert c["keep"] == {"dy": [52], "cty": "US"}
    assert c["none"]["opts"] == [] and c["none"]["titles"] == c["all"]["titles"]


def test_country_picker_wiring_literals():
    src = _page()
    a, b = src.index("const CPX=(()=>{"), src.index("function renderCpx(){")
    m = src[a:b]
    assert "CTY_LS='cpx_cty_v1'" in m and "data-cpx-cty" in m and "keep('[data-cpx-cty]'" in m
    assert m.count("try{ localStorage.setItem(CTY_LS") == 1 and "localStorage.getItem(CTY_LS)" in m
    assert ".cpx-ctyp{" in src and "class=\"chip" not in m


# ── 📈 the three charts move together (owner, 7 Nov 2026: "koi ak chart pe arrow kru to vo data baki ke dono chart me bhi same
# period ka data selct ho — tino chart sath me same time ka data dikhayega") ──
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _win(end):                     # the tooltip's window: the 14 days ending `end` (the year at its end; on both across a year)
    end = date.fromisoformat(end)
    lo, d = end - timedelta(13), (lambda x: "%d %s" % (x.day, MON[x.month - 1]))
    return "%s %d – %s %d" % (d(lo), lo.year, d(end), end.year) if lo.year != end.year else "%s – %s %d" % (d(lo), d(end), end.year)


def _day_at(frm, n, f):            # a chart's own day under the pointer at a fraction f of its width (viewBox 360, margins 10 / 12)
    i = max(0, min(n - 1, int((f * 360 - 10) / 338 * (n - 1) + 0.5)))
    return (date.fromisoformat(frm) + timedelta(i)).isoformat()


def test_charts_move_together_on_every_set_at_both_widths(out):
    s = out["sync"]
    for key, n in (("all", 3), ("us", 3), ("br", 2)):              # All countries · a country · a country without its D0 (2 + a note)
        for wt in ("d", "m"):                                      # 3 across (desktop) · one under the other (phone)
            moves = s[key + "_" + wt]
            assert len(moves) == 3 * n and s[key + "_" + wt + "_titles"] == n
            for mv in moves:                                       # over chart 1 / 2 / 3 at 25 / 60 / 95 % of its width
                day = _day_at(mv["from"], mv["N"], mv["f"])
                tips = mv["s"]
                assert mv["day"] == day and len(tips) == n
                assert all(t["on"] and t["rule"] == "visible" for t in tips), (key, wt, mv["k"], mv["f"])
                assert [t["win"] for t in tips] == [_win(day)] * n           # the SAME 14-day window on every chart of the set
                assert [t["text"] for t in tips] == mv["exp"]                # … each with its own numbers of that window
                assert len({t["x"] for t in tips}) == 1                      # (the same days: each rule at the same x)
                assert all(0 <= t["left"] <= t["w"] - 200 for t in tips)     # each tip inside its own chart
            assert all(not t["on"] and t["rule"] == "hidden" for t in s[key + "_" + wt + "_leave"])   # the pointer gone: none
    # the numbers printed on each tip; the country's D0 ROAS has no number on its last 3 days (not matured): "—" + its normal
    mid = next(m for m in s["all_d"] if m["k"] == 1 and m["f"] == 0.6)
    assert [t["text"].split("(14 din ka jod) ")[1] for t in mid["s"]] == ["₹20.0 · normal ₹20.0 (±0%)", "$6.00 · normal $6.00 (±0%)",
                                                                          "40.0% · normal 40.0% (±0%)"]
    for m in s["us_d"] + s["us_m"]:
        cpi, ecpm, roas = (t["text"].split("(14 din ka jod) ")[1] for t in m["s"])
        assert cpi.startswith("₹") and ecpm.startswith("$") and "—" not in cpi + ecpm
        assert (roas == "— · normal 43.2%") == (m["f"] == 0.95) and (m["f"] == 0.95 or roas[0].isdigit())
    assert all("—" not in t["text"] for m in s["all_d"] + s["all_m"] for t in m["s"])


def test_charts_move_together_on_a_phone_tap_and_leaving_hides_them(out):
    s = out["sync"]
    t = s["tap"]                                                   # the finger lifted, then the click: all three, one window
    assert [z["on"] for z in t["s"]] == [True] * 3 and len({z["win"] for z in t["s"]}) == 1 and t["s"][0]["win"]
    assert t["open"] == A and t["tab"] == "ch" and t["det"]          # (a tap on a chart never folds the details)
    for k in ("gap", "fn"):                                        # onto the gap of the set / the note under it: none
        assert all(not z["on"] and z["rule"] == "hidden" for z in s[k])


def test_charts_pointer_is_cheap(out):
    c = out["sync"]["cheap"]
    assert c["days"][0] == c["days"][1] == c["days"][2] != c["days"][3] == c["days"][4]
    assert c["same"] == "b" and c["other"] == "b"                  # inside one day (this chart or another of the set): no write
    # a new day: every chart's box read before the first write, every tip's width before the first move (one forced layout)
    for k in ("first", "next", "back"):
        assert re.fullmatch(r"b{4}w+o{3}w{3}", c[k]), (k, c[k])
    assert c["n1"] == [1, 1, 1] and c["n2"] == [2, 2, 2]            # each tip rebuilt once per new day …
    assert c["n3"] == [2, 2, 2] and c["on"] == [True] * 3           # … and not again for the same day after leaving


def test_charts_match_by_date_never_by_index(out):
    g = out["sync"]["syn"]
    D = lambda k: (date(2026, 1, 5) + timedelta(k)).isoformat()
    assert g["N"] == [[D(0), 60], [D(20), 40], [D(0), 39], [D(0), 60]]   # s2 starts 20 days later; s3 ends 20 days earlier, no day 10
    tip = lambda nm: {z["id"]: z for z in g[nm]["s"]}
    t = tip("s1_5")                                                # s1 day 5: s3 its day 5; s2 (from day 20) nothing; the lone chart none
    assert t["cpx-s1"]["win"] == t["cpx-s3"]["win"] == _win(D(5)) and t["cpx-s3"]["text"] == g["s1_5"]["exp"][2]
    assert not t["cpx-s2"]["on"] and t["cpx-s2"]["rule"] == "hidden" and not t["cpx-o1"]["on"]
    t = tip("s1_10")                                               # s3 has no point on day 10: its rule between days 9 and 11 + "—"
    assert t["cpx-s3"]["on"] and t["cpx-s3"]["rule"] == "visible" and t["cpx-s3"]["x"] == 94.5
    assert t["cpx-s3"]["text"] == _win(D(10)) + " (14 din ka jod) —" and g["s1_10"]["exp"][2] is None
    t = tip("s1_25")                                               # s2 without a number in its first 14 days: "—" + its normal
    assert t["cpx-s2"]["text"] == _win(D(25)) + " (14 din ka jod) — · normal $4.00" and t["cpx-s3"]["win"] == _win(D(25))
    t = tip("s1_50")                                               # s3 ends on day 39: nothing there
    assert not t["cpx-s3"]["on"] and t["cpx-s3"]["rule"] == "hidden" and t["cpx-s2"]["win"] == _win(D(50))
    for nm, k in (("s2_0", 1), ("s3_last", 2)):                    # s2's 1st point = s1's 21st, s3's 20th; s3's last = s1's 40th, s2's 20th
        t, day = tip(nm), g[nm]["day"]
        assert day == (D(20) if k == 1 else D(39)) and all(t[i]["win"] == _win(day) for i in ("cpx-s1", "cpx-s2", "cpx-s3"))
        assert [t[i]["text"] for i in ("cpx-s1", "cpx-s2", "cpx-s3")] == g[nm]["exp"][:3]
    t = tip("lone_7")                                              # a chart outside a set: its own tooltip only, as before
    assert t["cpx-o1"]["on"] and t["cpx-o1"]["text"] == g["lone_tip"] and t["cpx-o1"]["x"] == round(10 + 338 * 7 / 59, 2)
    assert not any(t[i]["on"] for i in ("cpx-s1", "cpx-s2", "cpx-s3"))
    t = tip("s1_after_lone")                                       # … and hidden again when the pointer is on the set
    assert not t["cpx-o1"]["on"] and t["cpx-s1"]["on"] and t["cpx-s3"]["on"] and not t["cpx-s2"]["on"]


def test_charts_move_together_wiring_literals():
    m = _page()
    m = m[m.index("const CPX=(()=>{"):m.index("function renderCpx(){")]
    assert "set=svg&&svg.closest('.cpx-chs')" in m and "set.querySelectorAll('svg[data-cpx-ch]')" in m
    assert "P.findIndex(p=>p.x===day)" in m and "if(tip._d!==day)" in m        # by the window's end date · rebuilt on a new day only
    assert "s.addEventListener('pointermove',onMove); s.addEventListener('click',onMove);" in m
    assert "s.addEventListener('pointerleave',()=>onMove({target:null}));" in m
    assert ".cpx-tip{position:absolute;" in _page()                                # (a tip never moves the page)


# ── 🕘 History · Levels: the level history, the ✓ recompute, the owner's actions ──
def test_levels_history_read_only_with_the_page_recompute(out):
    lv = out["lv"]
    ro = lv["ro"]
    assert ro["q"] == "no" and not ro["buttons"]                                   # no API: the history, read-only
    assert "History read-only" in ro["text"] and "Level = in dino ka exact average" in ro["text"]
    assert ro["checks"] == 2 and ro["warn"] == 1 and ro["typed"] == 1              # ✓ ✓, the tampered one ⚠, the typed one
    assert ro["fams"] == ["CPI", "ECPM", "ROAS_G"] and ro["more"]                  # CPI · eCPM · D0 ROAS first; the rest under More
    for w in ("Alarm baseline", "Accepted after 56 days", "Auto · first level", "Set by owner", "In force", "Resting level",
              "Gone", "₹7.0 L ÷ 35,000 installs", "24 Feb – 9 Mar 2026 (14 din)", "Owner actions", "Not applied · UnknownLevel",
              "Alarms"):
        assert w in ro["text"], w
    assert ro["text"].index("Levels") < ro["text"].index("Alarms")                 # the Levels block on top
    assert not ro["hostile_raw"] and ro["hostile_esc"]                             # the owner's note escaped
    assert all(c.startswith("cpx-") or c in ("aicon",) for c in ro["classes"]), ro["classes"]
    assert lv["ro403"] == {"q": "ro", "text": True, "buttons": False}              # not an admin: read-only, says so


def test_levels_check_against_hand_math(out):
    lv = out["lv"]
    # the first level: 1–14 Nov, ₹50,000 a day ÷ 2,500 installs a day = ₹20 (₹ as billed); $: Σ ₹50,000 × the day's rate ÷ Σ installs
    usd = sum(round(50000 * fxd(d), 2) for d in days("2025-11-01", "2025-11-14")) / (14 * 2500)
    assert lv["v_inr"] == pytest.approx(20.0, rel=1e-12) and lv["v_usd"] == pytest.approx(usd, rel=1e-12)
    assert lv["chk"] == "ok" and lv["chk_e"] == "ok" and lv["v_ecpm"] == pytest.approx(6.0, rel=1e-9)
    assert lv["chk_tam"] == "bad" and lv["chk_typed"] == "typed"


def test_levels_owner_buttons_and_every_post_body(out):
    lv = out["lv"]
    adm = lv["adm"]
    assert adm["set"] and adm["accept"] and adm["prop"] and not adm["auto"]        # no pin in force: no "Back to auto"
    assert adm["fams"] == ["CPI", "ECPM", "ROAS_G"]                                # a family with only a proposal is listed
    assert adm["rollback"] == ["L-00000000a3", "L-00000000a4", "L-00000000a5"]     # every earlier level (not the ones in force)
    assert adm["reject"] == ["L-00000000a2"] and adm["undo"] == ["a-0000000000c1", "a-0000000000c2"]
    t, app = T.isoformat(), A
    bodies = [p["b"] for p in lv["posts"]]
    assert all(p["u"] == "/api/levels/act" for p in lv["posts"])
    assert bodies == [
        {"act": "rollback", "app": app, "fam": "CPI", "from": t, "level": "L-00000000a3"},
        {"act": "reject", "app": app, "fam": "CPI", "level": "L-00000000a2"},
        {"act": "auto", "app": app, "fam": "CPI", "from": t},
        {"act": "accept", "app": app, "fam": "ROAS_G", "from": t, "proposal": {"day": "2026-03-20", "days": ["2026-03-01", t]}},
        {"act": "undo", "ref": "a-0000000000c1"},
        {"act": "set", "app": app, "fam": "CPI", "from": t, "days": ["2026-03-10", t], "note": "naya normal <b>"},
        {"act": "set", "app": app, "fam": "CPI", "from": t, "value": 31.5},
        {"act": "set", "app": app, "fam": "ROAS_G", "from": t, "value": 0.35},        # typed 35 (%) → 0.35
    ]
    assert lv["short_days"] == 0                                                   # 4 days: Save does nothing (7–120)
    f = lv["form"]
    assert f["open"] and f["set"]["a"] == "2026-03-10" and f["set"]["b"] == t
    # the live preview: Σ ₹ cost ÷ Σ installs of 10–28 Mar (₹50,000 ÷ 1,600 a day) = ₹31.25, with the page's own ✓
    assert f["preview"].endswith("Level ₹31.3 = 10 Mar – 28 Mar 2026 (19 din) · ₹9.5 L ÷ 30,400 installs ✓")


def test_levels_pending_until_the_build_has_read_it_and_the_error_toast(out):
    lv = out["lv"]
    assert lv["toasts"].count("✅ Saved — agle update me lagega (1–1½ ghante)") == 8
    assert lv["pending"] == 8 and lv["pending_txt"] and lv["pending_after"] == 0
    assert lv["err_toast"] == ["⏳ Saving…", "❌ Save fail — Kisi aur ne abhi save kiya — dobara try karo (HTTP 409)"]


def test_levels_controls_keep_the_page_in_place(out):
    for w in ("375", "1280"):
        assert out["lv"]["keep"][w] == {"dy": [120], "f": "ECPM"}, w               # the tapped switch back where it was


def test_levels_on_the_chart_and_the_list(out):
    ch = out["lv"]["chart"]
    assert ch["marks"] == 4 and ch["hollow"] == 1                                  # 3 CPI level changes + 1 eCPM; the proposal hollow
    assert ch["labels"] == ["₹21.0 · accepted", "₹20.0 · first", "₹19.5 · set", "$6.00 · first", "new? 33.2%"]
    assert out["lv"]["tip"].endswith("Level: Alarm baseline · 13 Mar se · measured 24 Feb – 9 Mar")
    assert out["lv"]["tag"] == {"row": True, "det": True}                          # 🆕 on the row (pointer lp), the line in details
    c = out["lv"]["cty"]                                                           # a country picked: no app level on its charts
    assert c["svgs"] == 3 and c["marks"] == 0 and c["F"] is None and "Level:" not in (c["tip"] or "")
    assert c["back"] == 4                                                          # All countries: the app's markers again


# ── 🕘 Levels: review fixes (Save only for a level the build takes, one save at a time, the $ view, no history block) ──
def test_levels_save_only_for_a_level_the_build_takes(out):
    s = out["lvfix"]["save"]
    assert s["ok"]                                                                 # data for every day, worth more than 0: on
    assert s["nodata"] == {"disabled": True, "text": True}                         # days the file does not have: off, and says so
    assert s["zero"] == {"disabled": True, "text": True, "shown": False}           # a level worth 0: off, and no ✓ preview of it
    assert s["zero_posts"] == 0                                                    # … a stray tap sends nothing
    assert out["lvfix"]["from_clamp"] == ["2025-10-01", "2025-10-01", T.isoformat()]   # From never before the file's first day
    day = (T - timedelta(days=9)).isoformat()
    assert out["lvfix"]["from_default"] == [day, day, T.isoformat()]               # … the default From too (a young file)
    assert out["lvfix"]["from_default_old"] == (T - timedelta(days=27)).isoformat()   # an old file: the last 28 days, as before


def test_levels_one_save_at_a_time(out):
    d = out["lvfix"]["dbl"]
    assert d == {"posts": 1, "mid": [True, True], "busy": True, "after": [False, False], "idle": False}   # a double tap commits once
    lp = out["lvfix"]["lock_paint"]
    assert lp["n"] >= 5 and lp["off"] == 0 and lp["on"] == lp["n"]                 # a repaint during the flight keeps them disabled
    assert out["lvfix"]["save_dbl"] == 1                                           # the form's Save too


def test_levels_every_owner_button_is_disabled_while_a_save_is_in_flight():
    p = _page()
    m = p[p.index("const CPX=(()=>{"):p.index("function renderCpx(){")]
    tags = re.findall(r'<button type="button" class="cpx-lvb[^`]*?</button>', m)
    assert len(tags) == 8, len(tags)                                               # Save, Cancel, Accept, Use, Reject, Undo, Set, Auto
    assert all("lvDis()" in t or "LVBUSY" in t for t in tags), [t[:70] for t in tags if "lvDis()" not in t and "LVBUSY" not in t]
    assert "if(LVBUSY) return false; lvLock(true);" in m and "finally{ lvLock(false); }" in m


def test_levels_typed_cpi_in_the_dollar_view_goes_out_in_rupees(out):
    u, k = out["lvfix"]["usd"], out["lvfix"]["usd"]["k"]
    assert k == pytest.approx(0.0132)                                              # Σ$ ÷ Σ₹ of the 14 days ending the data day
    assert "Typed value · $ per install" in u["text"] and "(1 $ = ₹75.76, 15 Mar – 28 Mar 2026 ka rate)" in u["text"]
    assert "$ view: aapki $ value save par ₹ me badal di jaati hai" in u["text"] and not u["save_off"]
    assert u["body"] == [{"act": "set", "app": A, "fam": "CPI", "from": T.isoformat(), "value": pytest.approx(0.38 / k, abs=1e-6)}]
    assert u["body"][0]["value"] == pytest.approx(28.787879, abs=1e-6)             # not 0.38 as ₹, not the flat-rate 31.67
    n = out["lvfix"]["usd_norate"]                                                 # no spend in those days: no rate, no guess
    assert n["text"] and n["save_off"] and n["posts"] == 0 and n["toast"] == ["❌ $ se ₹ ka rate nahi mila — ₹ view me value daalo"]
    assert out["lvfix"]["usd_ecpm"] == {"unit": True, "note": False}               # eCPM is $ per 1000 in both views
    assert out["lvfix"]["inr"] == {"unit": True, "note": False, "save_off": False}   # the ₹ view: ₹ per install, as before


def test_levels_owner_actions_and_undo_stay_without_a_history_block(out):
    n = out["lvfix"]["nolv"]                                                       # the build shipped the actions but no history
    assert n["note"] and n["actions"] and n["undo"] == ["a-0000000000c1", "a-0000000000c2"] and n["switches"] == 0 and not n["set"]
    assert out["lvfix"]["nolv_ro"] == {"actions": True, "undo": 0}                 # a non-admin sees them, with no button
    p = out["lvfix"]["nolv_pending"]                                               # no actions either: the saved ones are pending
    assert p["pending"] == 1 and p["undo"] == ["a-0000000000d1"] and p["pend"] == 1
    assert p["undo_post"] == [{"act": "undo", "ref": "a-0000000000d1"}]


def test_dates_carry_their_year_when_not_in_the_reference_year(out):
    y = out["yr"]                                                                       # synthetic build: reference year 2026, history from 1 Oct 2025
    assert y["all"] == "1 Oct 2025 – 30 Mar 2026"                                       # All time crosses the year: both ends carry it
    assert y["cus"] == "20 Dec 2025 – 6 Jan 2026"                                       # a Custom range over New Year
    assert y["mon"] == "1 Dec – 31 Dec 2025"                                            # a past-year month: one year at the end
    assert y["one"] == "3 Feb 2026"                                                     # a single day: with its year (as before)
    assert y["d14"] == "15 Mar – 28 Mar 2026"                                           # the default stays as short as it was
    assert y["rg"] == ["1 Mar – 31 Mar 2025", "1 Mar – 10 Mar", "23 Dec 2025 – 5 Jan 2026",
                       "4 Mar", "4 Mar 2025", "1 Mar – 10 Mar 2026"]
    assert y["fd"] == ["4 Mar", "4 Mar 2025"]                                          # a past-year single date gets its year
    assert out["lv"]["ticks"][0].endswith("’25") and "Jan ’26" in out["lv"]["ticks"]    # chart month ticks: the first one and every January carry the year
    assert out["lv"]["ticks_cur"] == ["May", "Jun", "Jul", "Aug", "Sep"]                # a chart inside the reference year: no year on any tick
    assert out["lv"]["ticks_jan"] == ["Jan", "Feb", "Mar", "Apr"]                      # from 1 Jan of the reference year: January stays short


# ── 🤖 the level agent (AGENT SPEC §6.3–§6.6 ship fields → §7 page; synthetic `ag` / `agent` from cpx_fixture.agent()) ──
S1, S2, S3, P1, P2, W1, O1, H1, R1, C1 = ("D-00000000" + k for k in ("s1", "s2", "s3", "p1", "p2", "w1", "o1", "h1", "r1", "c1"))
ROWS_NEWEST_FIRST = [P1, W1, O1, S1, S2, P2, H1, R1, C1, S3]


def test_agent_without_its_fields_the_page_is_as_before(out):
    # every render of the plain fixture (list, all tabs, Levels read-only + admin): none of the agent's words, classes, controls
    assert out["noag"]["words"] == []
    assert not any(c.startswith("cpx-ag") for c in out["noag"]["classes"])
    o = out["ag"]["older"]                                   # an older build: the pointer's scoreboard only, no ag in any file
    assert o["tag"] == ["cpx-lvt", "🆕 New level ready"]     # the 🆕 tag stays
    assert o["lines"][1] == "🆕 D0 ROAS: new level ready 30.0% (12 hafte steady) · gap vs old level ≈₹1.2 L since 20 Mar — History → Levels"
    assert o["board"] and not o["list"] and o["accept"] == "✅ Accept" and not o["wrap"]
    assert o["reject"] == ["L-00000000o1"] and o["how"] == ["Accepted after 56 days old ₹18.0 · alarm 15 Nov 2025"]


def test_agent_row_tag_per_status(out):
    # T-P1: one text per status word (a blocked settle reads as a keep, an on-hold one as a wait); +N; unknown → none
    t = out["ag"]["tags"]
    assert (t["kept"], t["blocked"]) == ("🤖 Kept · S1", "🤖 Kept · S1")
    assert (t["waiting"], t["hold"]) == ("🤖 Waiting · S1 · next check 21 Mar", "🤖 Waiting · S1 · next check 21 Mar")
    assert t["trial"] == "🤖 Accept — trial · S1" and t["accepted"] == "🤖 Accepted 21 Mar"
    assert t["reverted"] == "↩ Reverted by agent 21 Mar" and t["overridden"] == "Overridden by you 21 Mar" and t["held"] == "Held by your action"
    assert t["passed"] == t["closed"] == t["bogus"] == t["constructor"] == ""
    assert t["more"] == "🤖 Kept · S1 (+2)" and t["more_txt"] == "🤖 Kept · S1" and t["no_day"] == "🤖 Waiting · S1"
    assert t["past"] == "🤖 Accepted 30 Dec 2025"             # the year rule: a date outside the reference year carries it
    assert t["none"] == ["", "", "", ""] and t["title"] == "Ads to pay back an install"
    # the list itself: the agent's answer in the 🆕 tag's place; an app without one keeps 🆕 (Gamma) or shows nothing (Epsilon)
    li = out["ag"]["list"]
    assert li["a"] == {"cls": "cpx-lvt cpx-agt", "text": "🤖 Accepted 21 Mar (+4)"}
    assert li["b"] == {"cls": "cpx-lvt cpx-agt", "text": "🤖 Accept — trial · CPI market move"}
    assert li["d"] == {"cls": "cpx-lvt cpx-agt", "text": "🤖 Waiting · still moving · next check 3 Apr (+1)"}
    assert li["c"] == {"cls": "cpx-lvt", "text": "🆕 New level ready"} and li["e"] is None


def test_agent_verdict_lines_in_the_details(out):
    # T-P2: one line per standing decision (and an accept / override of the last 28 days); a proposal with lp[i].ag → the
    # agent's line (+ the money level's gap); a CPI decision ends with its extra paid, "not a loss"; the reverted (25 Feb),
    # the closed and the passed ones stay in History only
    L = out["ag"]["lines"]
    assert L["a"][0].startswith("💸 ≈₹2.4 L zyada kharch hua")                       # the money line as before
    assert L["a"][1:] == [
        "🤖 D0 ROAS: Kept — CPI part 140% of the move: seen with spend ×2.6 since the old level (your lever). Agla check: 3 Apr · gap vs old level ≈₹1.2 L since 20 Mar — History → Levels",
        "🤖 Install-day ROAS D7 (AdMob): Waiting — CPI part 120% of the move: narrow: countries moving the same way = 61% of spend (opposite 9%). Agla check: 3 Apr · gap vs old level ≈₹40.0k since 13 Mar — History → Levels",
        "🤖 Install-day ROAS D0 (AdMob): Overridden by you 25 Mar — CPI part 130% of the move: seen with 62% of spend in campaigns new since / gone after the old level — History → Levels",
        "🤖 CPI: Engine settle blocked — seen with spend ×3.5 since the old level (your lever). Agla check: 3 Apr · extra paid vs old level ≈₹90.0k since 24 Mar (not a loss) — History → Levels",
        "🤖 Ads to pay back an install: Engine settle on hold — eCPM part 85% of the move: eCPM moved on this app only — the cause is not in the data (ad sources / mediation / units). Agla check: 3 Apr — History → Levels",
        "🤖 eCPM: Accepted 21 Mar — other apps' eCPM moved the same way (4 other apps: median −18% vs own −17%, 75% moved the same way); ads per user +2% — History → Levels",
        "🤖 Spend: Held by your action — budget / bid limit (your lever): spend −45%, campaign C1 carries 80% of the change — History → Levels"]
    assert out["ag"]["lines"]["cls"] == ["cpx-vm"] + ["cpx-vm cpx-agv"] * 7
    assert [x[0] for x in L["links"]] == [P1, W1, O1, S1, S2, P2, H1] and dict(L["links"])[S2] == "GAP"
    assert L["b"] == ["🤖 CPI: Accept — trial (not applied yet) — other apps' CPI moved the same way (3 other apps: median +29% vs own +30%, 100% moved the same way). Agla check: 3 Apr · extra paid vs old level ≈₹30.0k since 25 Mar (not a loss) — History → Levels"]
    # a proposal without the agent's answer keeps today's 🆕 line — a CPI one's gap says extra paid, not a loss (R-m2)
    assert L["c"] == ["🆕 CPI: new level ready ₹20.0 (120+ din se khula) · extra paid vs old level ≈₹60.0k since 24 Mar (not a loss) — History → Levels"]
    assert L["d"] == ["🤖 eCPM: Waiting — other apps' eCPM moved the same way (3 other apps: median −10% vs own −12%, 67% moved the same way); but coming back / still moving: last 14 days −6% vs the 14 before. Agla check: 3 Apr — History → Levels"]
    # the line's link: History · Levels with that decision open and its family's levels
    assert out["ag"]["link"] == {"tab": "hi", "agd": S2, "lvf": "GAP", "open": True}
    # opened before its file arrived: an empty slot, then the late file fills it (with the tab body), no full repaint
    assert out["ag"]["arrive"] == {"before": False, "lines": 7, "tb": True, "slot": True}


def test_agent_cpi_extra_paid_is_not_a_loss_and_the_money_is_unchanged(out):
    # T-P9 (R-m1): a CPI decision's extra paid shows on its own line only; the list's money = the D0 ROAS one, as without the agent
    m = out["ag"]["money"]
    assert m["ag"] == m["noag"] == "≈₹1.8 L"                                      # 14 × (₹50,000 − ₹15,000 ÷ 0.40)
    assert dict(m["rows"])[A] == pytest.approx(14 * 12500) and all(v is None for k, v in m["rows"] if k != A)
    assert m["card"]["line"].endswith("≈₹1.8 L lost") and m["det"] == "💸 ≈₹2.4 L zyada kharch hua"
    assert sum("not a loss" in x for x in out["ag"]["lines"]["a"]) == 1               # the blocked CPI settle's line only
    assert out["ag"]["usd"]["line"].endswith("extra paid vs old level ≈$1,080 since 24 Mar (not a loss) — History → Levels")


def test_agent_decisions_list_one_line_per_decision_newest_first(out):
    # T-P3: under the Levels table, one line per decision — date · Family · status word · short — newest first, full history
    h = out["ag"]["hist"]
    assert h["ids"] == ROWS_NEWEST_FIRST and out["ag"]["shuffled"] == ROWS_NEWEST_FIRST   # the page orders them itself
    assert h["lines"] == ["27 Mar · D0 ROAS · Kept · spend ×2.6 (your lever)",
                          "26 Mar · Install-day ROAS D7 (AdMob) · Waiting · narrow: countries 61%",
                          "25 Mar · Install-day ROAS D0 (AdMob) · Overridden · campaign mix 62%",
                          "24 Mar · CPI · Blocked · spend ×3.5 (your lever)",
                          "23 Mar · Ads to pay back an install · On hold · app only",
                          "21 Mar · eCPM · Accepted · eCPM market move",
                          "6 Mar · Spend · Held · budget (your lever)",
                          "25 Feb · eCPM · Reverted · eCPM market move",
                          "21 Feb · Install-day ROAS D1 (AdMob) · Closed · spend ×0.6 (your lever)",
                          "10 Jan · CPI · Passed · CPI market move"]
    assert out["ag"]["hist_b"] == ["27 Mar · CPI · Accept — trial · CPI market move"]
    words = {ln.split(" · ")[2] for ln in h["lines"] + out["ag"]["hist_b"]}
    assert words == {"Accepted", "Passed", "Kept", "Blocked", "Waiting", "On hold", "Accept — trial", "Reverted", "Overridden", "Held", "Closed"}
    a, lv, m, d = h["order"]                                                         # scoreboard → Levels → its table → Agent decisions
    assert 0 <= a < lv < m < d and h["hinglish"] == 1 and h["closed"] and h["expanded"] == 0
    e = out["ag"]["early"]                                                           # also in the two early-return paths
    assert e["d"] == {"note": True, "board": True, "list": ["27 Mar · eCPM · Waiting · still moving"]}
    assert e["z"] == {"note": True, "board": True, "list": 1}


def test_agent_decision_details_on_tap(out):
    d = out["ag"]["det"]
    s1 = d[S1]                                                                       # the blocked CPI settle
    assert s1[0] == "CPI · the engine's own new level (56 days steady) · change since 10 Mar · asked 1× (24 Mar)"
    assert s1[1] == "Cause: seen with spend ×3.5 since the old level (your lever)" and s1[2] == "Agla check: 3 Apr"
    assert s1[3] == "Asks | 24 Mar · 1× Keep · spend ×3.5 (your lever)"
    assert s1[4] == ("Numbers: Old → new ₹20.0 → ₹31.3 (+56%) · 4.5 bands · spend ×3.5 · last 14 d vs 14 before +1% · steady ±3% · "
                     "other apps 3, median +2% · spend in new / gone campaigns 12%")
    assert s1[5:] == ["Verdict: Pending",
                      "Extra paid vs old level ≈₹90.0k since 24 Mar — extra paid, not a loss (the D0 ROAS alarm carries the money)"]
    p1 = d[P1]                                                                       # the first ask's numbers when they differ (k0)
    assert p1[3] == "Asks | 27 Mar · 1× Keep · spend ×2.6 (your lever) | 20 Mar · 1× Wait · not steady"
    assert p1[4].endswith("cost part 140%, value part −40% of the move")
    assert p1[5] == "First ask (20 Mar): Old → new 40.0% → 31.0% (−23%) · 2.9 bands · spend ×1.9 · last 14 d vs 14 before −6% · steady ±13%"
    assert not any(x.startswith("First ask") for x in d[S1] + d[W1])               # k0 = k: no second line
    assert d[W1][4].endswith("persistence: the change started less than 84 days ago")
    p2 = d[P2]                                                                       # an applied accept: the days, the checks, the close
    assert "Applied 21 Mar · new level = 10 Mar – 21 Mar" in p2
    assert "Checks after 21 Mar (old $6.00, new $5.00): 28 d — · 56 d — · 84 d —" in p2 and p2[-1] == "Closed 21 Mar · new level accepted by agent"
    r1 = d[R1]                                                                       # reverted by the safety net (r3): wrong
    assert "Checks after 20 Feb (old $6.00, new $5.20): 28 d $5.90 · 56 d — · 84 d —" in r1 and "Verdict: Wrong" in r1
    assert "↩ Reverted by agent 25 Feb — the alarm, kept open without this level, closed as recovered" in r1
    c1 = d[C1]                                                                       # the build's two verdicts differ: both shown
    assert "Verdict: Pending · alarm check: Came back" in c1 and c1[-1] == "Closed 28 Feb · recovered"
    assert "Overridden by you 25 Mar, 15:00 IST · Accept new level — your action wins over the agent (Undo brings its decision back)" in d[O1]
    assert "Held: your own action holds Spend — the agent does not decide it (🔄 Back to auto gives it back)" in d[H1]
    assert d[H1][3] == "Numbers: Old → new $600/day → $330/day (−45%) · 5.0 bands"             # (no next check: one line less)
    assert d[S2][4] == "Numbers: Old → new 4.20 → 5.50 (+31%) · 3.0 bands · ads per user −2% · CPI part 15%, eCPM part 85% of the move"
    assert d[S3][-1] == "Closed 10 Jan · new level accepted"
    assert "Accept — trial: recorded, not applied yet — your ✅ Accept still works" in out["ag"]["det_b"]
    # the $ view: a CPI level at the 14 days' rate ending the ask day (Σ$ ÷ Σ₹ = 0.012 here), the % move as judged in ₹
    u = out["ag"]["usd"]
    assert u["s1"].startswith("Numbers: Old → new $0.24 → $0.38 (+56%)") and u["p2"].startswith("Numbers: Old → new $6.00 → $5.00 (−17%)")


def test_agent_decision_tap_opens_closes_and_keeps_the_page_in_place(out):
    t = out["ag"]["tap"]
    assert t[0] == {"agd": S1, "open": True, "exp": True} and t[1] == {"agd": None, "open": False} and t[2] == {"agd": None}
    assert out["ag"]["reopen"] is None                                               # another app's details: nothing open
    for w in ("375", "1280"):                                                        # keep(): the tapped line back where it was
        assert out["ag"]["keep"][w] == {"dy": [120], "agd": S1, "held": "900px"}, w
    # the anchor is the tapped control itself: the agent line's link / the tab button (links above the tabs point to the same tab)
    assert out["ag"]["keep_sel"] == ['[data-cpx-ago="%s"]' % S1, '.cpx-tab[data-cpx-tab="ch"]', '[data-cpx-tab="dw"]']


def test_agent_scoreboard_trial_live_again_and_the_backtest(out):
    # T-P4: the counts, the accepts' trial (live / trial / trial again), the backtest line only with every number, one Hinglish line
    b = out["ag"]["board"]
    head = ("🤖 Agent since 20 Jan: 2 accepted (0 right, 1 wrong, 1 pending) · 2 kept · 2 waiting · 1 reverted · 1 accept — trial · "
            "1 overridden by you · 1 held by you · Engine settles (CPI / GAP): 3 checked · 1 passed · 1 blocked · 1 on hold")
    hi = ("Agent khud decide karta hai: kaaran market ka ho aur number steady ho tabhi naya level; kaaran aapka apna lever ho "
          "(spend, campaigns, budget, ads per user) to alarm khula rehta hai — engine ka CPI / GAP accept bhi isi se check hota hai.")
    chk = " · 40 decisions re-checked (0 differ) · 6 re-asks on later data (0 accept flips)"
    assert b["live"] == head + " Accepts: live since 17 Feb " + hi
    assert b["trial"] == head + " Accepts: trial, day 18 of 28 (not applied yet)" + chk + " " + hi
    assert b["again"] == head + " Accepts: trial again since 14 Mar (an accept changed on later data), day 14 of 28 (not applied yet)" + chk + " " + hi
    assert "Accepts: trial again since 20 Mar (a past decision did not repeat), day 8 of 28" in b["parity"]
    assert "Accepts: trial again since 20 Dec 2025 (the rule changed), day 3 of 28" in b["rule"]
    assert b["bt"] == head + (" Accepts: live since 17 Feb Backtest on your history (1.8 y): 12 proposals → 2 accept (1 right, 0 wrong); "
                              "with the engine's steadiness test 0 · CPI / GAP settles 5 → 1 passed, 3 blocked, 1 on hold "
                              "(2 of them held the new level). Synthetic backtest note. ") + hi
    assert "1 on hold. Synthetic backtest note." in b["bt_nolh"]
    assert b["bt_bad"] == [False] * 6                                                 # years 0 / v 2 / a number missing / 80 y / −1 / junk
    assert b["off"] == b["v2"] == b["none"] == ""                                     # mode off · another version · no block
    assert b["junk"].startswith("🤖 Agent since —: 0 accepted (0 right, 0 wrong, 0 pending)") and "Accepts: trial (not applied yet)" in b["junk"]
    assert b["html"].startswith('<div class="cpx-agb" id="cpx-agb"><p class="cpx-agb1">🤖 Agent since')
    assert "3 accepts, 3 right" not in json.dumps(out["ag"], ensure_ascii=False)      # (D-f: numbers only from the private file)


def test_agent_level_rows_blocked_on_hold_reverted_and_passed(out):
    # T-P5: the How texts and status words; the never-applied rows stay off the chart; a reverted row is grey
    lv = out["ag"]["lv"]
    cpi = {r["id"]: r for r in lv["CPI"]}
    b1 = cpi["L-00000000b1"]["cells"]
    assert b1[4] == "Engine settle blocked by agent: seen with spend ×3.5 since the old level (your lever) old ₹20.0 · alarm 13 Mar"
    assert b1[5] == "Blocked" and b1[6] == "✓" and cpi["L-00000000b1"]["wrap"]        # its own 14 data days add up (✓); the How wraps
    assert cpi["L-00000000b2"]["cells"][4] == "Accepted after 56 days · 🤖 passed old ₹20.0 · alarm 15 Nov 2025"
    assert cpi["L-00000000b0"]["cells"][4:6] == ["Alarm baseline Sudden step · open", "In force"] and not cpi["L-00000000b0"]["wrap"]
    ec = {r["id"]: r for r in lv["ECPM"]}
    assert ec["L-00000000e2"]["cells"][4:7] == ["Accepted by agent · eCPM market move old $6.00 · alarm 12 Nov 2025", "In force", "✓"]
    assert ec["L-00000000e1"]["cells"][4:6] == ["Reverted by agent 25 Feb old $6.00 · alarm 15 Oct 2025", "Reverted"] and ec["L-00000000e1"]["rest"]
    g1 = lv["GAP"][0]["cells"]
    assert g1[4] == ("Engine settle on hold (agent): eCPM part 85% of the move: eCPM moved on this app only — the cause is not in the data "
                     "(ad sources / mediation / units) · next check 3 Apr old 4.20 · alarm 28 Dec 2025") and g1[5] == "On hold"
    ch = out["ag"]["chart"]
    assert ch["labels"] == ["₹21.0 · accepted", "₹20.0 · first", "$5.00 · agent", "$6.00 · first", "new? 30.0%"]   # no blocked ₹31.3 / reverted $5.20
    assert ch["tip1"].endswith("Level: Alarm baseline · 13 Mar se · measured 24 Feb – 9 Mar")   # not the blocked settle
    assert ch["tip2"].endswith("Level: Accepted by agent · 21 Mar se · measured 10 Mar – 21 Mar")
    p = out["ag"]["props"]                                                           # the proposal line carries the agent's answer
    assert p["g"] == ["🆕 New level ready: 30.0% (12 hafte steady) · 10 Mar – 28 Mar 2026 (19 din) · ₹2.9 L D0 value ÷ ₹9.5 L cost · old 40.0% · "
                      "gap vs old level ≈₹1.2 L since 20 Mar · 🤖 Kept · spend ×2.6 (your lever) ✅ Accept anyway"]
    assert p["c7"][0].endswith("· 🤖 Waiting · narrow: countries 61% · next check 3 Apr ✅ Accept anyway")
    assert p["b"] == ["🆕 New level ready: ₹13.0 (120+ din se khula) · 15 Mar – 27 Mar 2026 · old ₹10.0 · extra paid vs old level ≈₹30.0k since 25 Mar "
                      "(not a loss) · 🤖 Accept — trial · CPI market move (not applied yet) ✅ Accept"]
    assert p["c"] == ["🆕 New level ready: ₹20.0 (120+ din se khula) · 25 Feb – 24 Mar 2026 · old ₹16.0 · extra paid vs old level ≈₹60.0k since 24 Mar (not a loss) ✅ Accept"]


def test_agent_owner_buttons_reject_on_an_agent_accept_and_use_this_level_on_a_blocked_row(out):
    # T-P6: ✖ Reject on an accepted_agent level (the same POST as today), never on a blocked / on-hold / reverted row;
    # ↩ Use this level on every row not in force (blocked / on hold / reverted included); read-only: no button at all
    btn = {f: {r["id"]: r["btn"] for r in out["ag"]["lv"][f]} for f in ("CPI", "ECPM", "GAP")}
    assert btn["CPI"] == {"L-00000000b1": ["rollback"], "L-00000000b0": [], "L-00000000b2": ["reject"], "L-00000000b3": ["rollback"]}
    assert btn["ECPM"] == {"L-00000000e2": ["reject"], "L-00000000e1": ["rollback"], "L-00000000e0": ["rollback"]}
    assert btn["GAP"] == {"L-00000000g1": ["rollback"], "L-00000000g0": []}
    assert out["ag"]["lv_ro"] == {"CPI": [0, 0, 0, 0], "ECPM": [0, 0, 0], "GAP": [0, 0]}
    t = T.isoformat()
    assert out["ag"]["posts"] == [                                                   # the stray rejects (reverted / blocked) sent nothing
        {"act": "reject", "app": A, "fam": "ECPM", "level": "L-00000000e2"},
        {"act": "rollback", "app": A, "fam": "CPI", "from": t, "level": "L-00000000b1"},
        {"act": "rollback", "app": A, "fam": "GAP", "from": t, "level": "L-00000000g1"},
        {"act": "accept", "app": A, "fam": "ROAS_G", "from": t, "proposal": {"day": "2026-03-20", "days": ["2026-03-10", t]}}]
    c = out["ag"]["conf"]
    assert c[0] == "eCPM: 21 Mar ka agent wala accept reject karein? Alarm apne shuru se khula rahega."
    assert c[-1] == "Agent: Kept · spend ×2.6 (your lever). D0 ROAS: naya level 30.0% 28 Mar 2026 se accept karein?"


def test_agent_hostile_text_is_escaped(out):
    # T-P7: cause / short / ask-run short / id / backtest note: never raw HTML, always the escaped text
    h = out["ag"]["hostile"]
    assert h["raw"] == [] and h["esc"] == [True] * 5 and h["open"]
    assert h["tap"] == 'D-"><img src=x onerror=alert(6)>'                             # the tap still finds its row
    assert not out["ag"]["list_raw"]


def test_agent_dev_view_renders_nothing_and_classes_are_cpx_ag(out):
    # T-P8: the developer copy: no screen, no scoreboard / tag / rows / lines; new classes are cpx-ag* only
    assert out["ag"]["dev"] == {"html": "", "board": "", "tag": "", "rows": 0, "list": "", "lines": "", "ptr": None}
    cls = set(out["ag"]["classes"])
    assert all(c.startswith("cpx-") or c == "aicon" for c in cls), cls
    css = _page()[_page().index("<style>"):_page().index("</style>")]
    for c in cls - set(out["noag"]["classes"]):                                      # new to the agent renders: cpx-ag*, or an existing CPX class
        assert c.startswith("cpx-ag") or ("." + c) in css, c
    assert {"cpx-agt", "cpx-agb", "cpx-agl", "cpx-agr", "cpx-agx", "cpx-agw", "cpx-agv"} <= cls
    assert all(("." + c) in css for c in cls if c.startswith("cpx-ag"))
    assert out["ag"]["bad_words"] == [] and out["ag"]["causal"] == []               # no undefined / NaN; no causal claim (D-e)


def test_agent_wiring_literals():
    src = _page()
    m = src[src.index("const CPX=(()=>{"):src.index("function renderCpx(){")]
    a = m[m.index("// ---- 🤖 the level agent"):m.index("function levelsHtml(")]
    assert "keep(`[data-cpx-agd=\"${sq(id)}\"]`" in m                                # the new control keeps the page in place
    assert m.count("Agent khud decide karta hai") == 1                               # one Hinglish line
    assert not re.search(r"\b(follows|because|caused|due to|driven)\b", a, re.I)     # D-e: the page's own words claim no cause
    assert "LVNOREJ.has(x.st)" in m and "x.src==='accepted_agent'" in m             # Reject on an agent accept, never on a blocked one
    assert "AGD=null;" in m and "'AGD' in o" in m
