"""💰 Google Ads spend in the $ view at each spend day's OWN INR→USD rate (owner-approved: old days were re-valued at
today's rate and read low in $). Every screen's $ view reads it through ONE helper (roasDaily: the Marketing ROAS tab,
the app page one tap away, Overview, the hub), so they never disagree; every ₹ view keeps reading "daily" (one rate:
today's), so ₹ stays the exact rupee Google Ads billed. Only INR spend: any other currency keeps one rate everywhere.

Backend: build_static._spend_daily_dated (the ROI section's own dated series + lookup: value_build._load_fx +
engine.value._fx_fn) and engine.roas.build_roas(daily_dated=...). Frontend: renderRoas(), spendByApp(), hubSpend(),
dateWiseRows() and renderOverview() run for real by tests/roas_fx_frontend.js on dashboards the REAL build code made
here. Every name, id, rate and amount is SYNTHETIC; the expected numbers are worked out by hand below (not through the
code under test)."""

import json
import os
import re
import shutil
import subprocess
from datetime import date, timedelta

import pytest

from admob_iq.build_static import _spend_daily_dated, _spend_to_usd
from admob_iq.engine.roas import build_roas

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
TAG = re.compile(r"<[^>]*>")

TODAY = "2026-01-08"                               # partial: outside the tab's "all" window
DAYS = [(date(2025, 12, 31) + timedelta(days=i)).isoformat() for i in range(9)]       # 31 Dec … 8 Jan
SERIES = {"2026-01-01": 0.0125, "2026-01-02": 0.012, "2026-01-05": 0.0118, "2026-01-06": 0.0115, "2026-01-07": 0.0112}
# by hand: before the series → its first rate; Sat / Sun → Friday's; after its last day → the last rate
RATE = {"2025-12-31": 0.0125, "2026-01-01": 0.0125, "2026-01-02": 0.012, "2026-01-03": 0.012, "2026-01-04": 0.012,
        "2026-01-05": 0.0118, "2026-01-06": 0.0115, "2026-01-07": 0.0112, "2026-01-08": 0.0112}
NOW = 1 / 90                                       # today's one rate: $1 = ₹90
INR = 1_000_000                                    # ₹1 in micros
DEMO, PUZ, OTHER = "com.example.demo", "com.example.puzzle", "com.example.other"
SPEND = {"v": 2, "currency_src": "INR", "fx": {}, "note": None,
         "daily": {DEMO: {d: 9_000 * INR for d in DAYS},                                  # ₹9,000 a day, every day
                   PUZ: {d: 4_500 * INR for d in DAYS[2:7]},                              # ₹4,500 a day, 2–6 Jan
                   OTHER: {d: 1_800 * INR for d in DAYS[3:8]}},                           # ₹1,800 a day, 3–7 Jan
         "installs": {DEMO: {d: 10 for d in DAYS}}, "convval": {}, "convval_day1": {},
         "campaigns": {DEMO: [{"id": "c1", "name": "Demo one", "status": "ENABLED", "cost_micros": 81_000 * INR,
                               "account": "1110000001", "account_name": "Demo Ads"}],
                       PUZ: [{"id": "c2", "name": "Puzzle one", "status": "ENABLED", "cost_micros": 22_500 * INR,
                              "account": "1110000002", "account_name": "Puzzle Ads"}],
                       OTHER: [{"id": "c3", "name": "Other one", "status": "PAUSED", "cost_micros": 9_000 * INR,
                                "account": "1110000003", "account_name": "Other Ads"}]}}
IDS = {"ca-app-pub-0000000000000001~1000000001": DEMO, "ca-app-pub-0000000000000001~1000000002": PUZ}
CATALOG = [{"app_id": "ca-app-pub-0000000000000001~1000000001", "app_name": "Demo Gallery", "rev": 1200,
            "account_id": "pub-0000000000000001"},
           {"app_id": "ca-app-pub-0000000000000001~1000000002", "app_name": "Puzzle Quest", "rev": 320,
            "account_id": "pub-0000000000000001"}]


def _data_dir(tmp_path, series=SERIES):
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    if series is not None:
        (d / "fx_series.json").write_text(json.dumps({"INR": series, "_ts": 1}))
    return str(d)


# ── backend ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_each_day_takes_its_own_rate(tmp_path):
    got = _spend_daily_dated(SPEND, _data_dir(tmp_path))
    assert set(got) == {DEMO, PUZ, OTHER}
    for sid, dd in SPEND["daily"].items():
        assert set(got[sid]) == set(dd)
        for d, v in dd.items():
            assert got[sid][d] == int(round(v * RATE[d])), (sid, d)
    assert got[DEMO]["2026-01-03"] == got[DEMO]["2026-01-02"] == 108 * INR      # Saturday = Friday's rate
    assert got[DEMO]["2025-12-31"] == 112_500_000                                 # before the series: its first rate
    assert got[DEMO]["2026-01-08"] == 100_800_000                                 # after it: its last rate


def test_nothing_dated_to_give_means_none(tmp_path):
    assert _spend_daily_dated(SPEND, _data_dir(tmp_path, series=None)) is None          # no series yet → one rate
    assert _spend_daily_dated(dict(SPEND, currency_src="USD"), _data_dir(tmp_path)) is None   # USD needs no FX
    eur = tmp_path / "eur"
    eur.mkdir()
    (eur / "fx_series.json").write_text(json.dumps({"EUR": {"2026-01-02": 1.05}, "_ts": 1}))
    assert _spend_daily_dated(dict(SPEND, currency_src="EUR"), str(eur)) is None   # the page explains INR only
    assert _spend_daily_dated({k: v for k, v in SPEND.items() if k != "currency_src"}, _data_dir(tmp_path)) is None
    assert _spend_daily_dated({"error": "x"}, _data_dir(tmp_path)) is None
    assert _spend_daily_dated(None, _data_dir(tmp_path)) is None


def test_spend_is_only_read(tmp_path):
    before = json.dumps(SPEND, sort_keys=True)
    _spend_daily_dated(SPEND, _data_dir(tmp_path))
    assert json.dumps(SPEND, sort_keys=True) == before


def test_build_roas_without_dated_is_the_payload_as_before():
    usd = _spend_to_usd(SPEND, NOW)
    a, b = build_roas(usd, IDS, CATALOG), build_roas(usd, IDS, CATALOG, daily_dated=None)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert "spend_fx" not in a and all("daily_dated" not in e for e in a["by_app"].values())
    assert all("daily_dated" not in u for u in a["unmatched_apps"])


def test_build_roas_dated_rides_the_same_join(tmp_path):
    usd = _spend_to_usd(SPEND, NOW)
    dated = _spend_daily_dated(SPEND, _data_dir(tmp_path))
    one, r = build_roas(usd, IDS, CATALOG), build_roas(usd, IDS, CATALOG, daily_dated=dated)
    assert r["spend_fx"] == "dated"
    strip = lambda p: {**{k: v for k, v in p.items() if k != "spend_fx"},
                       "by_app": {a: {k: v for k, v in e.items() if k != "daily_dated"} for a, e in p["by_app"].items()},
                       "unmatched_apps": [{k: v for k, v in u.items() if k != "daily_dated"} for u in p["unmatched_apps"]]}
    assert json.dumps(strip(r), sort_keys=True) == json.dumps(one, sort_keys=True)   # every other key: unchanged
    assert r["by_app"]["Demo Gallery"]["daily_dated"] == dated[DEMO]
    assert r["by_app"]["Puzzle Quest"]["daily_dated"] == dated[PUZ]
    assert [u["store_id"] for u in r["unmatched_apps"]] == [OTHER] and r["unmatched_apps"][0]["daily_dated"] == dated[OTHER]


def test_two_store_ids_of_one_app_add_up(tmp_path):
    sp = json.loads(json.dumps(SPEND))
    sp["daily"]["com.example.demo.old"] = {"2026-01-02": 1_000 * INR}
    dated = _spend_daily_dated(sp, _data_dir(tmp_path))
    r = build_roas(_spend_to_usd(sp, NOW), IDS, CATALOG, aliases={"com.example.demo.old": "Demo Gallery"}, daily_dated=dated)
    e = r["by_app"]["Demo Gallery"]
    assert e["daily_dated"]["2026-01-02"] == dated[DEMO]["2026-01-02"] + 12 * INR
    assert set(e["daily_dated"]) == set(e["daily"])


def test_rupees_still_round_trip_exactly(tmp_path):
    """The ₹ view reads "daily" × usd_inr: the exact rupee Google Ads billed, dated series or not."""
    usd = _spend_to_usd(SPEND, NOW)
    r = build_roas(usd, IDS, CATALOG, daily_dated=_spend_daily_dated(SPEND, _data_dir(tmp_path)))
    usd_inr = round(1.0 / NOW, 4)
    for d, v in r["by_app"]["Demo Gallery"]["daily"].items():
        assert abs(v * usd_inr / 1e6 - 9_000) < 0.01, d


# ── frontend: renderRoas() for real ───────────────────────────────────────────────────────────────────────────────────
def _dash(roas):
    rows = lambda usd: [[d, int(usd * 1e6), 100_000, 120_000, 110_000, 50] for d in DAYS]
    return {"currency": "USD", "usd_inr": round(1.0 / NOW, 4), "today_date": TODAY, "latest_complete": DAYS[-2],
            "generated_at": "2026-01-08T06:00:00Z", "apps_catalog": CATALOG, "app_icons": {}, "app_store_ids": {},
            "accounts": [], "known_accounts": ["pub-0000000000000001"],
            "apps": [{"name": n, "account": "pub-0000000000000001", "placements": 1, "revenue": 1.0, "avg_health": 70,
                      "platform": "Android", "ecpm": 1.0, "change_pct": 0, "at_risk": 0, "declining": 0,
                      "health_dist": [1, 0, 0]} for n in ("Demo Gallery", "Puzzle Quest")],
            "alerts": {"counts": {"critical": 0, "warning": 0, "improving": 0}, "items": []},
            "movers": {"increasing": [], "decreasing": []}, "kpis": {"apps": 2, "accounts": 1, "revenue": 0, "ecpm": 0},
            "placements": [{"id": "ca-app-pub-0000000000000001/1111111111", "name": "splash_open", "app": "Demo Gallery",
                            "daily": rows(150)},
                           {"id": "ca-app-pub-0000000000000001/2222222222", "name": "list_native", "app": "Puzzle Quest",
                            "daily": rows(40)}],
            "roas": roas}


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    if NODE is None:
        pytest.skip("node is not installed")
    tmp = tmp_path_factory.mktemp("roas_fx")
    usd = _spend_to_usd(SPEND, NOW)
    dated = build_roas(usd, IDS, CATALOG, daily_dated=_spend_daily_dated(SPEND, _data_dir(tmp)))
    fx = {"app": "Demo Gallery", "dated": _dash(dated), "one": _dash(build_roas(usd, IDS, CATALOG)),
          "eur": _dash(dict(json.loads(json.dumps(dated)), currency_src="EUR"))}   # a payload the build no longer makes
    (tmp / "fx.json").write_text(json.dumps(fx))
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        script = max(re.findall(r"<script>(.*?)</script>", f.read(), re.S), key=len)
    (tmp / "app.js").write_text(script, encoding="utf-8")
    subprocess.run([NODE, "--check", str(tmp / "app.js")], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "roas_fx_frontend.js"), str(tmp / "app.js"), str(tmp / "fx.json")],
                         check=True, capture_output=True, text=True, timeout=300)
    rep = json.loads(out.stdout)
    assert rep["errors"] == []
    return {**rep["out"], "other": rep["other"]}


def _num(s):
    return float(re.sub(r"[^0-9.\-]", "", s.replace("−", "-")))


def _kpis(h):
    """{label: value text} of the four KPI cards."""
    return {l: TAG.sub("", v) for l, v in re.findall(r'<div class="card kpi"><div class="l">([^<]*)</div><div class="v[^"]*">(.*?)</div>', h)}


def _rows(h):
    """{app: [revenue, spend, roas, net]} of the app table (texts)."""
    out = {}
    for tr in re.findall(r'<tr class="clk"[^>]*>(.*?)</tr>', h, re.S):
        tds = [TAG.sub("", t).strip() for t in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        nm = re.sub(r"\s*com\.example\.\S+$", "", tds[0]).strip()
        out[nm] = tds[1:5]
    return out


RULE_SPLIT = " · $ me aaj ke rate pe — campaign ka din-wise spend nahi"


def _notes(h):
    """The tab's explanation lines: the head's <p class="scd"> and the 💱 rate line."""
    return re.findall(r'<p class="scd[^"]*"[^>]*>.*?</p>', h, flags=re.S)


def _body(h):
    """The tab minus its explanation lines and the account split's rate remark: every number, row and split."""
    return re.sub(r'<p class="scd[^"]*"[^>]*>.*?</p>', "", h, flags=re.S).replace(RULE_SPLIT, "")


def test_dollar_view_uses_each_days_own_rate(page):
    h = page["dated|USD|all"]
    k = _kpis(h)
    # by hand: Demo 9,000 × (0.0125 + 0.0125 + 3 × 0.012 + 0.0118 + 0.0115 + 0.0112) = $859.50 · Puzzle 4,500 ×
    # (3 × 0.012 + 0.0118 + 0.0115) = $266.85 → $1,126.35 spend · AdMob revenue $1,520 → ROAS 1.35×, net +$393.65
    assert _num(k["Ad spend"]) == 1126 and _num(k["AdMob revenue"]) == 1520
    assert k["Blended ROAS"] == "1.35×" and _num(k["Net profit"]) == 394
    r = _rows(h)
    assert _num(r["Demo Gallery"][1]) == 860 and r["Demo Gallery"][2] == "1.40×"       # 1,200 ÷ 859.50
    assert _num(r["Puzzle Quest"][1]) == 267 and r["Puzzle Quest"][2] == "1.20×"       # 320 ÷ 266.85
    assert _num(r["Other Ads"][1]) == 105                                             # 1,800 × 0.0585 = $105.30
    assert "<b>$ me:</b> har din ka spend <b>us din ke apne</b> INR→USD rate pe" in h
    # the period's average rate: ₹94,500 billed ÷ $1,126.35 = ₹83.90 a dollar; today's ₹90.00
    assert "💱 Is period ke spend ka average rate <b>$1 = ₹83.90</b> · aaj $1 = ₹90.00</p>" in h
    assert RULE_SPLIT in h                                                            # the account split: one rate, said


def test_dollar_view_without_a_dated_series_is_as_before(page):
    h = page["one|USD|all"]
    k = _kpis(h)
    assert _num(k["Ad spend"]) == 1050 and k["Blended ROAS"] == "1.45×" and _num(k["Net profit"]) == 470
    assert _rows(h)["Demo Gallery"][2] == "1.50×"
    assert "Spend <b>INR→USD</b> convert kiya (apples-to-apples)." in h and "💱" not in h and "din-wise" not in h


def test_rupee_view_is_unchanged(page):
    for scope in ("all", "app"):
        a, b = page[f"dated|INR|{scope}"], page[f"one|INR|{scope}"]
        assert _body(a) == _body(b), scope                       # every number, row and split: byte-identical
    k = _kpis(page["dated|INR|all"])
    assert _num(k["Ad spend"]) == 94500 and _num(k["AdMob revenue"]) == 136800 and k["Blended ROAS"] == "1.45×"
    h = page["dated|INR|all"]
    assert "<b>₹ me:</b> wahi ₹ jo Google Ads ne bill kiya, AdMob revenue aaj ke rate pe" in h
    assert "isliye ₹ aur $ ka ROAS thoda alag ho sakta hai" in h
    assert "thoda alag" not in page["one|INR|all"] and "💱" not in page["one|INR|all"]   # no dated series → as before


def test_the_toggle_never_moves_the_table(page):
    """₹ ⇄ $ re-renders the tab: the explanation lines above the table are the SAME text in both views (same height),
    so the rows under the reader stay where they were (owner rule: no page jump on taps)."""
    for scope in ("all", "app"):
        a, b = _notes(page[f"dated|USD|{scope}"]), _notes(page[f"dated|INR|{scope}"])
        assert a == b and len(a) == 2, scope
        assert page[f"dated|USD|{scope}"].count(RULE_SPLIT) == page[f"dated|INR|{scope}"].count(RULE_SPLIT)
        assert _notes(page[f"one|USD|{scope}"]) == _notes(page[f"one|INR|{scope}"])


def test_one_app_page(page):
    h = page["dated|USD|app"]
    assert _num(_kpis(h)["Ad spend"]) == 860 and _kpis(h)["Blended ROAS"] == "1.40×"
    assert list(_rows(h)) == ["Demo Gallery", "Other Ads"]
    assert "$1 = ₹83.77" in h                                   # ₹72,000 ÷ $859.50
    assert _num(_kpis(page["one|USD|app"])["Ad spend"]) == 800


def test_a_non_inr_spend_keeps_one_rate_and_its_old_note(page):
    """Spend billed in another currency: no rupee sentence, no "$1 = ₹" line made of a mix of rates — the tab is the
    one-rate tab it was (the same numbers and note as a payload without daily_dated)."""
    for view in ("USD", "INR"):
        for scope in ("all", "app"):
            h = page[f"eur|{view}|{scope}"]
            assert "Spend <b>EUR→USD</b> convert kiya (apples-to-apples)." in h, (view, scope)
            assert "💱" not in h and "₹ me:" not in h and "din-wise" not in h, (view, scope)
            assert _kpis(h) == _kpis(page[f"one|{view}|{scope}"]), (view, scope)
            assert _rows(h) == _rows(page[f"one|{view}|{scope}"]), (view, scope)
    assert page["other"]["eur|USD"]["spa"] == page["other"]["one|USD"]["spa"]


def _ov_kpi(h):
    m = re.search(r'<div class="card kpi"><div class="l">Ad spend</div><div class="v[^"]*">(.*?)</div>', h)
    return _num(TAG.sub("", m.group(1)))


def test_the_screens_one_tap_away_show_the_tabs_own_spend(page):
    """A ROAS row opens the app page; Overview, its date-wise table and the hub read the same spend: in $ every one of
    them shows the tab's dated number, in ₹ the billed rupees — one app, one period, one number."""
    o = page["other"]
    for dash in ("dated", "one"):
        for view in ("USD", "INR"):
            h, x = page[f"{dash}|{view}|all"], o[f"{dash}|{view}"]
            rows = _rows(h)
            for app in ("Demo Gallery", "Puzzle Quest"):
                assert round(x["spa"][app] * (90 if view == "INR" else 1)) == _num(rows[app][1]), (dash, view, app)
            tot = x["spa"]["Demo Gallery"] + x["spa"]["Puzzle Quest"]
            assert round(tot * (90 if view == "INR" else 1)) == _num(_kpis(h)["Ad spend"]) == _ov_kpi(x["ov"]), (dash, view)
            assert abs(x["dw"] - tot) < 1e-6, (dash, view)                 # the date-wise table's spend column adds up
    # by hand: $ dated — Demo $859.50, Puzzle $266.85; one rate — $800, $250; the hub's last full day (7 Jan): Demo
    # ₹9,000 × 0.0112 = $100.80 dated, ₹9,000 ÷ 90 = $100 one rate; its usual: 31 Dec – 6 Jan, ₹63,000 → $758.70 ÷ 7
    assert abs(o["dated|USD"]["spa"]["Demo Gallery"] - 859.5) < 1e-6 and abs(o["dated|USD"]["spa"]["Puzzle Quest"] - 266.85) < 1e-6
    assert abs(o["dated|INR"]["spa"]["Demo Gallery"] - 800) < 1e-6 and o["one|USD"]["spa"] == o["dated|INR"]["spa"]
    assert abs(o["dated|USD"]["hub"]["y"] - 100.8) < 1e-6 and abs(o["dated|USD"]["hub"]["usual"] - 758.7 / 7) < 1e-6
    assert abs(o["dated|INR"]["hub"]["y"] - 100) < 1e-6 and o["dated|INR"]["hub"] == o["one|USD"]["hub"]


def test_overview_says_the_rule_the_same_in_both_views(page):
    o = page["other"]
    rule = "<b>$ me:</b> har din ka spend <b>us din ke apne</b> INR→USD rate pe"
    note = lambda h: TAG.sub("", re.search(r'<div class="ov-note[^"]*"[^>]*>(.*?)</div>', h, re.S).group(1))
    assert rule in o["dated|USD"]["ov"] and rule in o["dated|INR"]["ov"]
    strip = lambda t: re.sub(r"\d+\.\d+×|[$₹][\d,.]+", "#", t)      # only the numbers differ between the views
    assert strip(note(o["dated|USD"]["ov"])) == strip(note(o["dated|INR"]["ov"]))
    assert "us din ke apne" not in o["one|USD"]["ov"] and "us din ke apne" not in o["eur|USD"]["ov"]
