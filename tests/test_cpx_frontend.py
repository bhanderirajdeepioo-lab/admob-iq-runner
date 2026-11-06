"""📉 CPI vs eCPM — the page side (owner, 6 Nov 2026: "short and direct view … sirf one view me direct pata chal jana chaiye,
lekin details dekhna he to kuchh miss nahi hona chahiye"). tests/cpx_frontend.js runs the CPX module of frontend/index.html
for real (a node vm, stub page helpers) on the SYNTHETIC build output of tests/cpx_fixture.js (SPEC §3.3 shapes); checked
here: inert at load; the picker (Last 14 days first, every standard key and the month keys → its dates, N days ending at
the alarm's data day t; Custom swapped / clamped; the saved choice); the "now" sums in ₹ (as billed) and $ (each day's own
rate) against hand math, CPI judged in ₹; normal / status / since / money of SPEC §1.2 for the default view (the pointer,
no file) and other periods (cpi.json.gz); the list's order, the summary and the footer; the file states (⏳ Loading… /
⚠️ + Try again / a refused file); the details (verdict, money line, every tab); one app; keep() — no page jump — at 375 and
1280 px; the developer copy; a hostile app name escaped; cpx- classes only; and the wiring into the page (gated on
DATA.cpi). Skipped where node is not installed. No real data."""
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
    assert "normal = 29 Oct level" in d["all"]["cell"]                                  # the cell says which normal it is
    assert d["all"]["verdict"].startswith("Sab normal ke andar: CPI ₹20.0 → ₹20.0")
    e = d["early"]                                                                      # an early Custom (starts at day0)
    assert set(e["st"].values()) == {"ok"} and e["nrm"]["ROAS_G"]["src"] == "Hin" and "normal = 29 Oct level" in e["cell"]
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
    assert "spend ₹15.5 L · 1 Dec – 20 Dec" in c["text"] and "1 Dec – 20 Dec Fixed" in c["text"]
    assert c["verdict"].startswith("D0 ROAS 1 Dec – 20 Dec normal se neeche rahi (ab band). Is period me 36.6% (normal 40.0%)")
    o = s["open_at_b"]                                                                  # 1–10 Dec: still open on the last day → "N din se"
    assert o["open"] and "since 1 Dec (10 din)" in o["text"] and "1 Dec 10 din se" in o["text"]
    assert o["verdict"].startswith("D0 ROAS 1 Dec se normal se neeche: 33.0% (normal 40.0%)")
    assert "20 Mar – closed" in s["def_closed"]["text"] and "din se" not in s["def_closed"]["text"].split("Alarm")[0]   # the pointer lists open ones only
    assert s["def_closed"]["n"] == 1 and out["sc"]                                      # (a closed alarm is not an open Alarm) · the pointer's lost.sc is the default "since c"


def test_nav_badge_and_alerts_note_count_open_alert_episodes(out):
    assert out["alarm0"] == 1                                                           # a closed alarm the window still touches: not counted
    a = out["alarm1"]
    assert a["n"] == 2 and "<b>2 alarm</b>" in a["note"] and "<b>1 alarm</b>" in a["note_beta"]   # an open ALERT episode on another app: counted


def test_loss_math_baseline_and_ratio_column(out):
    lm = out["lm"]
    assert "÷ 36.0% = ≈$0.00 (normal period se ek din pehle ka healthy level" in lm["feb"]            # no open C0 episode: H the day before
    assert "÷ 36.0% = ≈$1,573 (normal period ka pehla healthy level, 29 Oct" in lm["early"]          # before H exists: the first known inside
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
