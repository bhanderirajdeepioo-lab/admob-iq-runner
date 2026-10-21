"""📈 eCPM trend — opened from the Overview "Avg eCPM" tile (owner: "ecpm kpi pe click kru to ek eCPM trend view … default
last 30 days, full pe pura history, day wise, month wise … niche sab app ka yesterday ka eCPM + last 7 days ke saath
comparison … app pe click → us app ka same view"; no tab of its own).

tests/ecpm_frontend.js runs the real page script in a node vm (stub DOM + a fake browser history) on the SYNTHETIC
dashboard written here (made-up apps, ids and money). Checked here, with the maths recomputed independently in Python
straight from the fixture's raw daily rows (never reusing the page's arithmetic):

  * eCPM = earnings ÷ impressions × 1000 over the same complete days as the dashboard; today's partial day is never used;
  * the windows (yesterday, last 7 / 30 days, previous 7 / 30, month to date vs the same days last month), the per-app
    change, the impact formula (yesterday impressions × (yesterday eCPM − 7-day avg) ÷ 1000) and the status rule (the
    app's own day-to-day swing: beyond 2× = Worse, beyond 1× = Watch, up beyond 2× = Better; low data = N/A; too little
    history = Too early);
  * Day and Month chart points (whole months, the current month partial, the first month "from" its first day), and what
    the chart prints (latest, range average dashed, min, max) + the tooltip's lines;
  * the Overview "Avg eCPM" tile equals the view for the same period (Yesterday / 7 / 30 days / This month), USD and INR;
  * the entry from the tile (and straight into an app's view when one is picked in the header), the phone's Back steps,
    leaving the view, the 5-min auto-refresh bringing it back as it was, sorting, the tap-only tooltip pin;
  * the payload carries the FULL daily history (no trim) — the view's "Full" range reads it;
  * 🔀 the tables' comparison picker (owner, 21 Oct): Yesterday vs last 7 (default) / 14 / 30 / 60 days / a month ‹ ›, and
    Month vs month ‹ ›: every pick's rows recounted here, the month bounds, partial months labelled by their days, the
    month-to-month status on a long synthetic history, Ad units / Countries following the pick (or saying why not), the
    pick restored per viewer, and the default view byte-identical to the page before the picker (git: BASE_REV).
Skipped where node is not installed."""

import json
import os
import re
import shutil
import statistics
import subprocess
from datetime import date, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")

TODAY = "2026-03-11"          # the live, partial day (its rows are absurd on purpose: they must never count)
LATEST = "2026-03-10"         # yesterday = the newest complete day
START = date(2025, 12, 20)
MIN_IMPR = 1000


def _days(a, b):
    out, d = [], a
    while d <= b:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


ALL_DAYS = _days(START, date(2026, 3, 11))


def _unit(uid, name, fmt, app, rows):
    return {"id": uid, "name": name, "app": app, "account": "pub-0000000000000000", "format": fmt, "platform": "Android",
            "daily": rows, "trend": [], "change_pct": 0, "health": 70, "band": "good", "verdict": "stable"}


def _series(days, impr, ecpm_of):
    """[date, earn_micros, impr, req, matched, clicks] rows with the given impressions and eCPM per day."""
    rows = []
    for k, d in enumerate(days):
        i = impr(d, k) if callable(impr) else impr
        e = ecpm_of(d, k)
        if d == TODAY:
            rows.append([d, 10 ** 12, 1, 5, 4, 0])           # the partial day: a crazy eCPM that must never show up
            continue
        rows.append([d, int(round(e * i * 1000)), i, int(i * 1.3), int(i * 1.1), i // 100])
    return rows


def _alt(base, amp):
    """eCPM alternating base·(1+amp) / base·(1−amp) — a steady day-to-day swing of ~2·amp."""
    return lambda d, k: base * (1 + amp if k % 2 else 1 - amp)


def _fixture():
    days = ALL_DAYS
    before = lambda f, last: (lambda d, k: last if d == LATEST else f(d, k))
    pl = [
        # Demo Gallery: swing ~2%, yesterday's banner eCPM crashes 25% → Worse (the biggest money loss)
        _unit("ca-app-pub-0000000000000001/1000000001", "home_banner", "banner", "Demo Gallery",
              _series(days, 200000, before(_alt(2.0, 0.01), 1.5))),
        _unit("ca-app-pub-0000000000000001/1000000002", "level_inter", "interstitial", "Demo Gallery",
              _series(days, 50000, _alt(8.0, 0.01))),
        # Puzzle Quest: swing ~6%, yesterday −2% → Normal
        _unit("ca-app-pub-0000000000000002/2000000001", "menu_native", "native", "Puzzle Quest",
              _series(days, 100000, before(_alt(3.0, 0.03), 2.94))),
        # Word Hunt: swing ~2%, yesterday +30% → Better
        _unit("ca-app-pub-0000000000000003/3000000001", "reward_hint", "rewarded", "Word Hunt",
              _series(days, 80000, before(_alt(1.0, 0.01), 1.3))),
        # Photo Frames: swing ~5%, yesterday −9% vs the 7-day avg → Watch (between 1× and 2×)
        _unit("ca-app-pub-0000000000000004/4000000001", "save_inter", "interstitial", "Photo Frames",
              _series(days, 60000, before(_alt(4.0, 0.025), 3.6))),
        # Tiny Notes: yesterday only 500 impressions → N/A (low data), never judged
        _unit("ca-app-pub-0000000000000005/5000000001", "list_banner", "banner", "Tiny Notes",
              _series(days, lambda d, k: 500 if d == LATEST else 20000, before(_alt(1.0, 0.01), 0.2))),
        # New Timer: only 5 days of data → Too early
        _unit("ca-app-pub-0000000000000006/6000000001", "open_ad", "app_open", "New Timer",
              _series([d for d in days if d >= "2026-03-06"], 20000, _alt(5.0, 0.01))),
        # Old Radio: no data in the last 30 days → listed only on "Show more"
        _unit("ca-app-pub-0000000000000007/7000000001", "old_banner", "banner", "Old Radio",
              _series([d for d in days if d <= "2026-01-15"], 30000, _alt(0.8, 0.01))),
    ]
    apps = sorted({p["app"] for p in pl})
    dash = {
        "today_date": TODAY, "latest_complete": LATEST, "currency": "USD", "usd_inr": 90.0, "generated_at": "2026-03-11T06:00:00+00:00",
        "placements": pl,
        "apps": [{"name": a, "account": "pub-0000000000000000", "placements": sum(p["app"] == a for p in pl), "revenue": 100.0,
                  "avg_health": 70, "platform": "Android", "ecpm": 1.0, "change_pct": 0, "at_risk": 0, "declining": 0,
                  "health_dist": [1, 0, 0]} for a in apps],
        "apps_catalog": [{"account_id": "pub-0000000000000000", "app_id": f"ca-app-pub-0000000000000000~{k:010d}", "app_name": a,
                          "rev": 1.0, "selected": True, "account_decided": True} for k, a in enumerate(apps)],
        "app_icons": {}, "app_store_ids": {},
        "alerts": {"counts": {"critical": 0, "warning": 0, "improving": 0}, "items": []},
        "movers": {"increasing": [], "decreasing": []},
        "kpis": {"apps": len(apps), "accounts": 1, "revenue": 0, "ecpm": 0},
        "countries_daily": {"Demo Gallery": {"US": _series(days, 30000, before(_alt(6.0, 0.01), 4.0)),
                                             "IN": _series(days, 90000, _alt(0.5, 0.01))}},
        "range_alerts": [], "recommendations": {"items": [], "root_cause": []}, "deductions": {"rows": []},
    }
    return dash


LONG_START = date(2025, 1, 1)   # the long SYNTHETIC history (14 whole months + March so far) for the month-to-month status


def _midx(d):
    return (int(d[:4]) - 2025) * 12 + int(d[5:7]) - 1


def _monthly(base, amp, mar):
    """eCPM flat inside a month, base·(1±amp) alternating month to month; March 2026 (so far) = February × mar."""
    feb = base * (1 + amp if _midx("2026-02-01") % 2 else 1 - amp)
    return lambda d, k: feb * mar if d[:7] == "2026-03" else base * (1 + amp if _midx(d) % 2 else 1 - amp)


def _long_fixture():
    days = _days(LONG_START, date(2026, 3, 11))
    pl = [
        # month-to-month swing ~6%, March −20% → Worse
        _unit("ca-app-pub-0000000000000011/1100000001", "cam_banner", "banner", "Steady Cam", _series(days, 50000, _monthly(2.0, 0.03, 0.8))),
        # swing ~6%, March −2% → Normal
        _unit("ca-app-pub-0000000000000012/1200000001", "notes_inter", "interstitial", "Calm Notes", _series(days, 40000, _monthly(3.0, 0.03, 0.98))),
        # swing ~2% (the floor), March +10% → Better
        _unit("ca-app-pub-0000000000000013/1300000001", "tiles_native", "native", "Bright Tiles", _series(days, 30000, _monthly(1.0, 0.01, 1.10))),
        # swing ~5%, March −7% → Watch
        _unit("ca-app-pub-0000000000000014/1400000001", "watch_reward", "rewarded", "Mid Watch", _series(days, 30000, _monthly(4.0, 0.025, 0.93))),
        # from 15 Nov only: 3 whole months of its own → Too early
        _unit("ca-app-pub-0000000000000015/1500000001", "cards_banner", "banner", "Fresh Cards",
              _series([d for d in days if d >= "2025-11-15"], 20000, lambda d, k: 4.0 if d[:7] == "2026-03" else 5.0)),
        # March: 40 impressions a day (400 so far) → N/A
        _unit("ca-app-pub-0000000000000016/1600000001", "clock_banner", "banner", "Quiet Clock",
              _series(days, lambda d, k: 40 if d[:7] == "2026-03" else 2000, _monthly(1.5, 0.03, 0.9))),
    ]
    apps = sorted({p["app"] for p in pl})
    d = _fixture()
    d.update({"placements": pl, "countries_daily": {},
              "apps": [dict(d["apps"][0], name=a) for a in apps],
              "apps_catalog": [{"account_id": "pub-0000000000000000", "app_id": f"ca-app-pub-0000000000000000~{k + 20:010d}", "app_name": a,
                                "rev": 1.0, "selected": True, "account_decided": True} for k, a in enumerate(apps)]})
    return d


# ── the independent maths (Python, straight from the raw rows) ──────────────────────────────────────────────────────────
def _maps(dash):
    pf, apps = {}, {}
    for p in dash["placements"]:
        a = apps.setdefault(p["app"], {})
        for d, e, i, *_ in p["daily"]:
            if d == TODAY:
                continue
            for m in (pf, a):
                x = m.setdefault(d, [0, 0])
                x[0] += e
                x[1] += i
    return pf, apps


def _comp(dash):
    return sorted({r[0] for p in dash["placements"] for r in p["daily"]} - {TODAY})


def _sum(dm, days):
    e = sum(dm[d][0] for d in days if d in dm)
    i = sum(dm[d][1] for d in days if d in dm)
    return {"e": e, "i": i, "ec": (e / (i * 1000)) if i else None}


def _swing(dm, days):
    v = [(dm[d][0] / (dm[d][1] * 1000)) if d in dm and dm[d][1] >= MIN_IMPR and dm[d][0] > 0 else None for d in days]
    ch = [abs(v[k] / v[k - 1] - 1) for k in range(1, len(v)) if v[k] is not None and v[k - 1] is not None]
    return statistics.median(ch) if len(ch) >= 7 else None


def _status(pct, swing, yi):
    if not yi >= MIN_IMPR:
        return "lagu"
    if swing is None or pct is None:
        return "jaldi"
    s = max(swing, 0.02)
    if pct <= -2 * s:
        return "bigda"
    if pct <= -s:
        return "dhyan"
    if pct >= 2 * s:
        return "behtar"
    return "normal"


def _row(dm, comp):
    y, w = _sum(dm, [LATEST]), _sum(dm, comp[-7:])
    chg = (y["ec"] - w["ec"]) if y["ec"] is not None and w["ec"] is not None else None
    pct = chg / w["ec"] if chg is not None and w["ec"] else None
    sw = _swing(dm, comp[-31:-1])
    return {"y": y["ec"], "yi": y["i"], "w7": w["ec"], "chg": chg, "pct": pct,
            "imp": (y["i"] * chg / 1000) if chg is not None else None, "swing": sw, "st": _status(pct, sw, y["i"]),
            "act": _sum(dm, comp[-30:])["i"] > 0}


@pytest.fixture(scope="module")
def dash():
    return _fixture()


@pytest.fixture(scope="module")
def report(tmp_path_factory, dash):
    if NODE is None:
        pytest.skip("node is not installed")
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    d = tmp_path_factory.mktemp("ecpm")
    sp, fx = str(d / "app.js"), str(d / "fixture.json")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(js)
    with open(fx, "w", encoding="utf-8") as f:
        json.dump({"dashboard": dash, "long": _long_fixture()}, f)
    subprocess.run([NODE, "--check", sp], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "ecpm_frontend.js"), sp, fx], check=True, capture_output=True,
                         text=True, timeout=180)
    rep = json.loads(out.stdout)
    assert rep.get("errors") == [], rep.get("errors")
    return rep


def _close(a, b, tol=1e-9):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


# ── the maths ───────────────────────────────────────────────────────────────────────────────────────────────────────────
@needs_node
def test_windows_are_the_dashboards_complete_days(report, dash):
    comp = _comp(dash)
    w = report["win"]
    assert w["L"] == LATEST and w["T"] == TODAY and w["y"] == [LATEST]
    assert w["d7"] == comp[-7:] and w["d30"] == comp[-30:] and w["p7"] == comp[-14:-7] and w["p30"] == comp[-60:-30]
    assert w["sw"] == comp[-31:-1] and w["s30"] == comp[-30:]
    assert w["mtd"] == _days(date(2026, 3, 1), date(2026, 3, 10))                    # month to date (yesterday's month)
    assert w["lm"] == _days(date(2026, 2, 1), date(2026, 2, 10))                     # the same days last month
    assert w["first"] == START.isoformat() and w["last"] == LATEST and w["ncomp"] == len(comp)
    assert TODAY not in comp


@needs_node
def test_todays_partial_day_is_never_used(report):
    assert report["agg"]["hasToday"] is False
    for p in report["pts_day"]:
        assert p["anyToday"] is False and p["last"] == LATEST
    assert all(m["k"] <= "2026-03" for m in report["pts_month"]["all"])


@needs_node
def test_portfolio_sums_match_an_independent_recount(report, dash):
    pf, _ = _maps(dash)
    comp = _comp(dash)
    want = {"y": [LATEST], "d7": comp[-7:], "d30": comp[-30:], "mtd": _days(date(2026, 3, 1), date(2026, 3, 10)),
            "lm": _days(date(2026, 2, 1), date(2026, 2, 10)), "p7": comp[-14:-7], "p30": comp[-60:-30]}
    for k, days in want.items():
        exp = _sum(pf, days)
        got = report["pf_sums"][k]
        assert got["e"] == exp["e"] and got["i"] == exp["i"], k
        assert _close(got["ec"], exp["ec"]), k


@needs_node
def test_every_app_row_change_impact_and_status(report, dash):
    _, apps = _maps(dash)
    comp = _comp(dash)
    for name, dm in apps.items():
        exp, got = _row(dm, comp), report["rows"][name]
        for k in ("y", "w7", "chg", "pct", "imp", "swing"):
            assert _close(got[k], exp[k]), (name, k, got[k], exp[k])
        assert got["yi"] == exp["yi"] and got["st"] == exp["st"] and got["act"] == exp["act"], name
        if exp["chg"] is not None:                       # impact = yesterday impressions × (yesterday eCPM − 7-day avg) ÷ 1000
            assert _close(got["imp"], got["yi"] * (got["y"] - got["w7"]) / 1000)
    # the fixture was built so every status shows up once
    st = {n: report["rows"][n]["st"] for n in report["rows"]}
    assert st == {"Demo Gallery": "bigda", "Puzzle Quest": "normal", "Word Hunt": "behtar", "Photo Frames": "dhyan",
                  "Tiny Notes": "lagu", "New Timer": "jaldi", "Old Radio": "lagu"}
    assert report["rows"]["Old Radio"]["act"] is False and report["rows"]["Tiny Notes"]["act"] is True


@needs_node
def test_status_rule_edges(report):
    # (−25%, swing 3%) Worse · (−7%, 5%) Watch · (+20%, 5%) Better · (+6%, 5%) Normal · (−3%, swing 1% → floor 2%) Watch ·
    # (−5%, 1%) Worse · 999 impressions N/A · no swing Too early · no data N/A
    assert report["status_fn"] == ["bigda", "dhyan", "behtar", "normal", "dhyan", "bigda", "lagu", "jaldi", "lagu"]


@needs_node
def test_ad_unit_rows(report, dash):
    comp = _comp(dash)
    units = {u["id"]: u for u in report["units"]}
    for p in dash["placements"]:
        if p["app"] != "Demo Gallery":
            continue
        dm = {r[0]: [r[1], r[2]] for r in p["daily"] if r[0] != TODAY}
        exp, got = _row(dm, comp), units[p["id"]]
        assert got["format"] == p["format"] and _close(got["y"], exp["y"]) and _close(got["imp"], exp["imp"]) and got["st"] == exp["st"]
    assert units["ca-app-pub-0000000000000001/1000000001"]["st"] == "bigda"          # the banner that fell
    assert units["ca-app-pub-0000000000000001/1000000002"]["st"] == "normal"


@needs_node
def test_day_points_per_range_and_full_history(report, dash):
    comp = _comp(dash)
    pf, _ = _maps(dash)
    by = {p["r"]: p for p in report["pts_day"]}
    assert by["30"]["n"] == 30 and by["30"]["first"] == comp[-30] and by["90"]["n"] == len(comp) == 81   # 90 > the 81 days there are
    assert by["all"]["n"] == len(comp) and by["all"]["first"] == START.isoformat()          # Full = from the very first day
    assert _close(by["30"]["lastEc"], _sum(pf, [LATEST])["ec"])
    assert _close(by["30"]["firstPv"], _sum(pf, [comp[-31]])["ec"])                        # "vs previous day" even at the range's edge
    assert by["all"]["firstPv"] is None


@needs_node
def test_month_points(report, dash):
    pf, apps = _maps(dash)
    comp = _comp(dash)
    ms = report["pts_month"]["all"]
    assert [m["k"] for m in ms] == ["2025-12", "2026-01", "2026-02", "2026-03"]
    for m in ms:
        days = [d for d in comp if d[:7] == m["k"]]
        exp = _sum(pf, days)
        assert m["e"] == exp["e"] and m["i"] == exp["i"] and _close(m["ec"], exp["ec"]) and m["n"] == len(days)
    assert [m["partial"] for m in ms] == [False, False, False, True]                      # March: till yesterday only
    assert ms[0]["from"] == START.isoformat() and ms[1]["from"] == ""                      # the first month starts mid-month
    assert ms[0]["pv"] is None and _close(ms[3]["pv"], ms[2]["ec"])
    assert report["pts_month"]["m30"] == ["2026-02", "2026-03"]                            # 30 days → whole months it touches
    nt = report["pts_month"]["app"]
    assert len(nt) == 1 and nt[0]["from"] == "2026-03-06" and nt[0]["n"] == 5              # an app's months start at its first day


@needs_node
def test_chart_prints_latest_average_min_max_and_the_tooltip(report):
    c = report["chart"]
    svg = c["svg"]
    assert c["W"] == 800 and c["n"] == 30 and svg.startswith('<svg viewBox="0 0 800 ')
    for t in (c["avgTxt"], c["maxTxt"], c["minTxt"], c["lastTxt"]):
        assert t.replace("$", "") in svg.replace("$", ""), t
    assert 'stroke-dasharray="6 5"' in svg                                                 # the range average, dashed
    assert 'fill-opacity=".16"' in svg                                                     # the faint impressions bars
    assert 'class="ec-gl"' in svg and 'class="ec-hd"' in svg                               # hover guide + dot
    assert re.search(r'aria-label="Daily eCPM: latest \$[\d.]+, range avg \$[\d.]+, min \$[\d.]+, max \$[\d.]+"', svg)
    assert c["empty"] is None
    assert "Mar '26*" in c["msvg"]                                                         # the partial month is marked
    tip = c["tipDay"]
    for t in ("Tue, 10 Mar 2026", "eCPM", "Earnings", "Impressions", "vs previous day"):
        assert t in tip
    assert "Bahar tap karo = band" in c["tipPin"] and "Bahar tap" not in tip
    assert "Mar 2026 · so far (10 days)" in c["tipMonth"] and "vs previous month" in c["tipMonth"]


# ── the Overview tile = the view, same period ──────────────────────────────────────────────────────────────────────────
@needs_node
@pytest.mark.parametrize("cur", ["USD", "INR"])
def test_overview_tile_equals_the_view(report, cur):
    r = report["consistency_" + cur]
    for rg in ("yesterday", "7d", "30d", "month"):
        assert r[rg]["overview"] and r[rg]["overview"] == r[rg]["view"], (rg, r[rg])
    tiles = dict(r["tiles"])
    assert tiles["Yesterday eCPM"] == r["yesterday"]["overview"]
    assert tiles["Last 7 days"] == r["7d"]["overview"] and tiles["Last 30 days"] == r["30d"]["overview"]
    assert tiles["This month vs last month"] == r["month"]["overview"]
    # Today (live, first tile): today's partial day only — the same number summed from today's rows; one app's too
    t = r["today"]
    assert t["T"] and t["own"] and tiles["Today eCPM · live"] == t["own"] == t["fn"] and t["app"] == t["appFn"]
    assert list(tiles)[0] == "Today eCPM · live" and 'class="row c5 ec-kpis"' in r["html"]
    assert re.search(r"\(<b>[+−]?\d+\.\d%</b> vs yesterday <b>" + re.escape("₹" if cur == "INR" else "$"), r["html"])   # plain %: a part of a day
    assert " · ab tak · " in r["html"] and " · not final" in r["html"] and t["none"]["ec"] is None
    sym = "₹" if cur == "INR" else "$"
    assert all(v.startswith(sym) for v in tiles.values())
    # number first, % beside it: "(−4.2% vs 7-day avg ₹310.00)"
    assert re.search(r"\(<b class=\"(up|down|)\">[+−]?\d+\.\d%</b> vs 7-day avg <b>" + re.escape(sym), r["html"])
    assert "same days last month" in r["html"] and "previous 30 days" in r["html"]


@needs_node
def test_currency_formatting(report):
    m = report["money_fmt"]
    assert m["inr"][:6] == ["₹180.00", "−₹23.40", "₹0.00", "−₹111,105", "+₹45.00", "₹0.00"]
    assert m["inr"][6:9] == ["−8.1%", "0.0%", "—"]
    assert m["inr"][9:] == ["₹0", "₹250", "₹12,000"]
    assert m["usd"] == ["$2.00", "−$0.26", "−$1,235", "+$0.50", "$2.50"]                 # cents only under 100


# ── the entry, Back, sorting, the tap rule ──────────────────────────────────────────────────────────────────────────────
@needs_node
def test_the_avg_ecpm_tile_opens_the_view(report):
    e = report["entry_tile"]
    assert e["n"] == 1 and e["hint"] and e["label"]
    assert 'role="button"' in e["tile"] and 'tabindex="0"' in e["tile"] and 'onclick="ecOpen()"' in e["tile"]
    a, b = report["entry_open"]["a"], report["entry_open"]["b"]
    assert a["screen"] == "ecpm" and a["app"] == "" and a["st"] == ["ecpm"] and a["title"] == "eCPM trend"
    assert a["r"] == "30" and a["g"] == "day"                                             # always opens on 30 days · Day
    assert "← Overview" in a["html"] and "eCPM trend · All apps" in a["html"]
    assert b["screen"] == "ecpm" and b["app"] == "Puzzle Quest" and b["units"] and not b["all"] and b["back"]
    assert b["title"] == "eCPM · Puzzle Quest"


@needs_node
def test_phone_back_steps(report):
    r = report["back"]
    assert r["open"]["screen"] == "ecpm" and r["open"]["st"] == ["ecpm"] and r["open"]["idx"] == 1
    assert r["app"]["app"] == "Demo Gallery" and r["app"]["st"] == ["ecpm", "ecpm-app"] and r["app"]["idx"] == 2
    assert r["back1"]["screen"] == "ecpm" and r["back1"]["app"] == "" and r["back1"]["all"] and r["back1"]["st"] == ["ecpm"]
    assert r["back2"]["screen"] == "overview" and r["back2"]["st"] == [] and r["back2"]["idx"] == 0
    assert r["reopen"]["st"] == ["ecpm", "ecpm-app"]
    assert r["closed"] == {"screen": "overview", "st": [], "idx": 0}                       # "← Overview": no Back press left over
    assert r["allapps"]["app"] == "" and r["allapps"]["st"] == ["ecpm"] and r["allapps"]["idx"] == 1
    assert r["left"]["screen"] == "placements" and r["left"]["st"] == [] and r["left"]["idx"] == 0
    assert r["rerender"]["added"] == 0 and r["rerender"]["st"] == ["ecpm"] and r["rerender"]["screen"] == "ecpm"


@needs_node
def test_auto_refresh_brings_the_view_back_as_it_was(report):
    r = report["refresh"]
    assert r["newData"] and r["rebuilt"] and r["silent"] is False                          # a new build: re-summed from the new data
    assert r["screen"] == "ecpm" and r["app"] == "Demo Gallery" and r["units"] and r["month"]
    assert (r["r"], r["g"], r["usort"]) == ("365", "month", {"k": "name", "d": "asc"})
    assert r["st"] == ["ecpm", "ecpm-app"] and r["scrolls"] == []                          # no new Back step, no jump to the top


@needs_node
def test_sorting(report):
    s = report["sort"]
    rows = {r["key"]: r for r in s["rows"]}
    # default: the biggest money loss first, low data (N/A) after every judged row, the inactive app hidden
    d = s["def"]
    assert d[0] == "Demo Gallery" and "Old Radio" not in d
    judged = [k for k in d if rows[k]["st"] != "lagu"]
    assert d[:len(judged)] == judged and d[-1] == "Tiny Notes"
    imps = [rows[k]["imp"] for k in judged]
    assert imps == sorted(imps)
    t = s["toggles"]
    assert (t[0]["k"], t[0]["d"]) == ("imp", "desc") and t[0]["order"][0] == "Word Hunt"     # same column again → flips
    assert (t[1]["k"], t[1]["d"]) == ("imp", "asc") and t[1]["order"] == d
    assert (t[2]["k"], t[2]["d"]) == ("name", "asc") and t[2]["order"] == sorted(d, key=str.lower)
    assert (t[3]["k"], t[3]["d"]) == ("y", "desc")
    assert (t[4]["k"], t[4]["d"]) == ("pct", "asc") and t[4]["order"][0] == "Demo Gallery"
    assert (t[5]["k"], t[5]["d"]) == ("st", "asc") and t[5]["order"][:2] == ["Demo Gallery", "Photo Frames"]
    assert (t[6]["k"], t[6]["d"]) == ("yi", "desc") and t[6]["order"][0] == "Demo Gallery"
    assert t[7]["k"] == "w7"
    h = s["html"]
    assert h.count('<th class="ec-on" aria-sort="descending">') == 1 and h.count('aria-sort="none"') == 6
    assert "Status" in h and "impact<br>/day" in h and "30 days" in h
    assert s["idleHidden"] is False and s["idleShown"] is True


@needs_node
def test_tooltip_pins_on_a_tap_only(report):
    t = report["tap"]
    assert t["drawn"] and {"pointermove", "pointerdown", "pointerup", "pointercancel", "pointerleave"} <= set(t["listeners"])
    assert t["hover"] == [[100, False]]                     # a mouse hovers
    assert t["tap"] == [[204, True]]                        # a tap (under 10px) pins
    assert t["swipeBack"] == [] and t["swipe"] == []        # a swipe (10px+, even one that came back) never pins
    assert t["cancel"] == []                                # the browser took the touch for a scroll
    assert t["pen"] == [[309, True]]


# ── the page: structure (no tab of its own, the view's own range, phones) ──────────────────────────────────────────────
def _page():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        return f.read()


def test_no_tab_of_its_own_and_the_views_controls():
    h = _page()
    assert not re.search(r'<(button|a)[^>]*data-screen="ecpm"', h)                         # never a menu / tab-bar entry
    assert "${ecKpiTile(kpi('Avg eCPM',cm(k.ecpm),dspan,'muted',sparkbars(trendSeries)))}" in h
    assert "else if(cur==='ecpm') show('ecpm');" in h                                     # the auto-refresh re-opens it
    assert "if(id==='ecpm') ecPaint(); else ecLeft();" in h and "root.append(renderEcpm());" in h
    assert 'body[data-screen="ecpm"] #rangectl' in h                                       # the header Period is not this view's
    for t in ("['30','30 days'],['90','90 days'],['365','1 year'],['all','Full']", "[['day','Day'],['month','Month']]",
              "eCPM = har 1,000 ads (impressions) pe kamai", "← All apps (eCPM)", "← Overview"):
        assert t in h, t
    css = h[h.index("/* ===== 📈 eCPM trend"):h.index("/* \"Stay after N days\"")]
    assert ".ec-t th:first-child,.ec-t td:first-child{position:sticky;left:0" in css      # the App column stays on screen
    assert ".ec-tw{overflow-x:auto" in css                                                 # the table scrolls inside its card
    assert re.search(r"\.ec-seg button\{min-height:3[2-9]px", css) and re.search(r"\.ec-lnk\{[^}]*min-height:3[2-9]px", css)
    assert "@media(max-width:760px)" in css and ".ec-kpis.row.c4,.ec-kpis.row.c5{grid-template-columns:repeat(2,minmax(0,1fr))" in css


def test_the_payload_keeps_every_day_of_history():
    """The view's "Full" range reads placements[].daily — the build ships every stored day (no trim)."""
    from admob_iq.api.dataservice import build_from_db
    from admob_iq.db import InMemoryRepo

    repo = InMemoryRepo()
    first, n = date(2023, 6, 20), 900
    for k in range(n):
        d = (first + timedelta(days=k)).isoformat()
        repo.upsert_network(dict(report_date=d, account_id="pub-0000000000000000", app_id="ca-app-pub-0000000000000000~0000000001",
                                 app_name="Demo App", ad_unit_id="ca-app-pub-0000000000000000/0000000001", unit_name="banner",
                                 ad_source="AdMob", source_name="AdMob Network", country="US", format="banner",
                                 platform="android", ad_requests=1200, matched_requests=1100, impressions=1000, clicks=5,
                                 estimated_earnings_micros=2_000_000 + k, impression_rpm_micros=0, observed_ecpm_micros=0,
                                 currency_code="USD", is_finalized=True))
    d = build_from_db(repo, today=first + timedelta(days=n))
    daily = d["placements"][0]["daily"]
    assert len(daily) == n and daily[0][0] == first.isoformat() and daily[-1][0] == (first + timedelta(days=n - 1)).isoformat()
    assert d["latest_complete"] == daily[-1][0]


# ── 📈 Today tile: same time yesterday + the last hour (owner, 6 Oct: "yesterday same time pe kitna tha aur abhi kitna") ──
@needs_node
def test_today_tile_same_time_yesterday(report):
    r = report["intra"]
    ix = r["ix"]
    assert ix["m"] == 600 and abs(ix["yEc"] - 3.0) < 1e-9 and ix["hrM"] == 60 and abs(ix["hEc"] - 4.0) < 1e-9 and abs(ix["yhEc"] - 3.0) < 1e-9
    assert re.search(r'\(<b class="(up|down|)">[+−]?\d+\.\d%</b> vs kal isi samay <b>\$3\.00</b>\)', r["full"])   # like with like: coloured
    assert "pichhle 60 min: <b>$4.00</b> · kal isi waqt <b>$3.00</b>" in r["full"] and " · 10:00 AM tak · " in r["full"]
    assert r["gap"]["yEc"] is None and r["late"]["yEc"] is None and abs(r["near"]["yEc"] - 3.0) < 1e-9 and abs(r["gapNear"]["yEc"] - 3.0) < 1e-9
    assert "kal-isi-samay tulna " + r["next"] + " se" in r["first"] and " · poora din)" in r["first"]
    assert "kal isi samay ka point nahi" in r["missing"] and "kal-isi-samay tulna" not in r["missing"]
    for k in ("stale", "none"):                                   # no points for today: yesterday's whole day, no note
        assert " · poora din)" in r[k] and "kal isi" not in r[k] and " · ab tak · " in r[k]


@needs_node
def test_today_tile_small_chart(report):
    r = report["intra"]
    sp = r["spk"]
    assert sp.startswith('<div class="ec-spk" data-s="') and 'onpointermove="ecSpkAt(event,this)"' in sp and 'onclick="ecSpkAt(event,this)"' in sp
    assert '<path d="M' in sp and 'class="ec-spy"' in sp and 'class="ec-spt0"' in sp and 'class="ec-spd"' in sp   # yesterday + today + now
    assert "<span>12 AM</span><span>12 PM</span><span>12 AM</span>" in sp and '<span class="ec-spl-y">yesterday</span>' in sp   # 12-hour clock
    assert [p[0] for p in r["pts"]] == [540, 600]                     # 10 impressions at 00:30: under 2% of the day, left out
    assert abs(r["val"][0] - 3.0) < 1e-9 and r["val"][1] is None and r["val"][2] is None   # 10:00 between 09:00 / 11:00; a 12 h gap; before any
    assert 'class="ec-spy"' not in r["spk1"] and '<span class="ec-spl-y">yesterday · from ' in r["spk1"]   # no yesterday yet: today alone, when kal starts
    assert r["tileSpk"]
    # the table's own row sparkline (ecSpark(values, status)) still draws: the tile's chart has its own name (a same-named
    # function had replaced it, 6 Oct — every row's 30-day line went blank)
    assert r["rowSpk"].count("<svg") >= 3 and "ec-spk" not in r["rowSpk"]


# owner: "ha sab tiles me laga do" — every eCPM tile has its small daily chart; "format 12 hr" for the times
@needs_node
def test_every_tile_has_a_chart_and_12_hour_times(report):
    r = report["tilecharts"]
    assert r["hm"] == ["12:00 AM", "10:00 AM", "12:00 PM", "1:05 PM", "11:59 PM"]
    assert r["n"] == 5 and r["legends"] == [["today", "yesterday · from " + r["next"]], ["daily", "7-day avg"],
                                            ["last 7 days", "previous 7"], ["last 30 days", "previous 30"], ["this month", "last month"]]
    assert r["avgLine"] == 1 and r["prevLines"] == 3            # Yesterday: its 7-day avg dashed; the 3 period tiles: the period before
    assert r["onePt"] == "" and "M" in r["gap"] and r["gap"].count("M") == 2   # a lone point: no chart; a day without data: a gap


# ── the Date-wise report: Day | Month rows (owner, 7 Oct: "ek option month ka bhi … all time ya jo bhi period … table me hi") ──
@needs_node
def test_datewise_month_rows(report):
    r = report["datewise_month"]
    rows, mon = r["rows"], r["mon"]
    want = {}
    for x in rows:                                               # summed here on their own, per calendar month
        w = want.setdefault(x["d"][:7], {"n": 0, "rev": 0.0, "pl": 0.0})
        w["n"] += 1
        w["rev"] += x["rev"]
        w["pl"] += x["pl"]
    assert [m["d"] for m in mon] == sorted(want) and len(mon) >= 3
    for m in mon:
        assert m["n"] == want[m["d"]]["n"] and abs(m["rev"] - want[m["d"]]["rev"]) < 1e-6 and abs(m["pl"] - want[m["d"]]["pl"]) < 1e-6
    t = r["tblM"]
    assert "<th>Month</th>" in t and "<th>Date</th>" not in t and "Dec 2025 <span" in t
    assert re.search(r'Total · %d months · %dd</td>' % (len(mon), len(rows)), t)
    first = mon[0]
    assert re.search(r'>Dec 2025 <span class="faint"[^>]*>· %dd</span>' % first["n"], t)   # a month the period cuts says its days
    assert t.index(">Mar 2026 <") < t.index(">Dec 2025 <")          # newest month first, as the day rows
    assert "<th>Date</th>" in r["tblD"] and "Total · %dd</td>" % len(rows) in r["tblD"]
    b = r["box"]
    assert '<div class="ec-seg" role="group" aria-label="Rows by">' in b and \
        '<button type="button" class="on" aria-pressed="true" onclick="dwSetMode(\'month\')">Month</button>' in b
    assert (r["ls"], r["mode"]) == ("day", "day")                   # the choice is remembered on this device


# ── 🔀 the tables' comparison picker (owner, 21 Oct: "yesterday vs 7 days — option add karo: 7 days / 14 days / 30 days /
# 60 days / last month - change month by ‹ ›" · "this month vs last month - change month by ‹ ›") ─────────────────────────
BASE_REV = "9b17756"          # the page before the picker: its default view must come out byte-identical


def _by_month(comp):
    by = {}
    for d in comp:
        by.setdefault(d[:7], []).append(d)
    return by


def _full(m, days):
    return bool(days) and days[0] == m + "-01" and (date.fromisoformat(days[-1]) + timedelta(days=1)).day == 1


def _mswing(dm, by, pm):
    """median |month-to-month change| over the whole months up to pm (the last 13), only months the row had from the 1st."""
    f = min((d for d, x in dm.items() if x[1] > 0 or x[0] > 0), default="")
    ks = [k for k in sorted(by) if k <= pm and _full(k, by[k])][-13:]
    ks = [k for k in ks if f and by[k][0] >= f]
    mdm = {k: [sum(dm[d][0] for d in by[k] if d in dm), sum(dm[d][1] for d in by[k] if d in dm)] for k in ks}
    return _swing(mdm, ks)


def _row_cmp(dm, comp, cur, base, pm=None):
    """one row for a pick: pm = the older month in Month mode (its swing is month-to-month), else the day swing."""
    y, w = _sum(dm, cur), _sum(dm, base)
    chg = (y["ec"] - w["ec"]) if y["ec"] is not None and w["ec"] is not None else None
    pct = chg / w["ec"] if chg is not None and w["ec"] else None
    ncur = len(cur) if pm else 1
    sw = _mswing(dm, _by_month(comp), pm) if pm else _swing(dm, comp[-31:-1])
    act = (y["i"] > 0 or w["i"] > 0) if pm else _sum(dm, comp[-30:])["i"] > 0
    return {"y": y["ec"], "yi": y["i"], "w7": w["ec"], "chg": chg, "pct": pct,
            "imp": (y["i"] / ncur) * chg / 1000 if chg is not None else None, "swing": sw, "st": _status(pct, sw, y["i"]), "act": act}


def _same_rows(got, exp, name):
    for k in ("y", "w7", "chg", "pct", "imp", "swing"):
        assert _close(got[k], exp[k]), (name, k, got[k], exp[k])
    assert got["yi"] == exp["yi"] and got["st"] == exp["st"] and got["act"] == exp["act"], (name, got, exp)


FEB, JAN, MAR = _days(date(2026, 2, 1), date(2026, 2, 28)), _days(date(2026, 1, 1), date(2026, 1, 31)), _days(date(2026, 3, 1), date(2026, 3, 10))
DEC = _days(date(2025, 12, 20), date(2025, 12, 31))
# pick → (current days, baseline days, the older month in Month mode, title, current / baseline column)
PICKS = {
    "b14": ([LATEST], "-14", None, "yesterday vs last 14 days", "Yesterday<br>eCPM", "Last 14 days<br>avg"),
    "b30": ([LATEST], "-30", None, "yesterday vs last 30 days", "Yesterday<br>eCPM", "Last 30 days<br>avg"),
    "b60": ([LATEST], "-60", None, "yesterday vs last 60 days", "Yesterday<br>eCPM", "Last 60 days<br>avg"),
    "mon": ([LATEST], FEB, None, "yesterday vs Feb 2026", "Yesterday<br>eCPM", "Feb 2026<br>avg"),          # default month: the one before today's
    "monJan": ([LATEST], JAN, None, "yesterday vs Jan 2026", "Yesterday<br>eCPM", "Jan 2026<br>avg"),
    "monDec": ([LATEST], DEC, None, "yesterday vs Dec 2025 (20–31)", "Yesterday<br>eCPM", "Dec 2025 (20–31)<br>avg"),   # history starts 20 Dec
    "monMar": ([LATEST], MAR, None, "yesterday vs Mar 2026 (1–10)", "Yesterday<br>eCPM", "Mar 2026 (1–10)<br>avg"),     # complete days only
    "mm": (MAR, FEB, "2026-02", "Mar 2026 (1–10) vs Feb 2026", "Mar 2026 (1–10)<br>eCPM", "Feb 2026<br>eCPM"),
    "mmFeb": (FEB, JAN, "2026-01", "Feb 2026 vs Jan 2026", "Feb 2026<br>eCPM", "Jan 2026<br>eCPM"),
    "mmJan": (JAN, DEC, "2025-12", "Jan 2026 vs Dec 2025 (20–31)", "Jan 2026<br>eCPM", "Dec 2025 (20–31)<br>eCPM"),
}


@needs_node
def test_cmp_every_pick_matches_an_independent_recount(report, dash):
    _, apps = _maps(dash)
    comp = _comp(dash)
    m = report["cmp_math"]
    assert m["b7"]["def"] is True and m["b7"]["rows"] == report["rows"]          # the default: the very rows it always had
    for k, (cur, base, pm, title, cc, cb) in PICKS.items():
        base = comp[int(base):] if isinstance(base, str) else base
        g = m[k]
        assert g["def"] is False and g["cur"] == cur and g["base"] == base and g["ncur"] == (len(cur) if pm else 1), k
        assert (g["title"], g["colCur"], g["colBase"]) == (title, cc, cb), k
        assert g["colImp"] == cc.replace("eCPM", "impr"), k
        for name, dm in apps.items():
            _same_rows(g["rows"][name], _row_cmp(dm, comp, cur, base, pm), (k, name))
        for p in dash["placements"]:                                              # one app's ad units, the same maths
            if p["app"] != "Demo Gallery":
                continue
            dm = {r[0]: [r[1], r[2]] for r in p["daily"] if r[0] != TODAY}
            u, exp = next(x for x in g["units"] if x["id"] == p["id"]), _row_cmp(dm, comp, cur, base, pm)
            assert _close(u["y"], exp["y"]) and _close(u["w7"], exp["w7"]) and _close(u["imp"], exp["imp"]) and u["st"] == exp["st"], (k, p["id"])
    # by hand (flat-alternating eCPMs, whole numbers of micros): Puzzle Quest's February averages $3.00 exactly, Word Hunt's $1.00
    pq, wh = m["mon"]["rows"]["Puzzle Quest"], m["mon"]["rows"]["Word Hunt"]
    assert _close(pq["y"], 2.94) and _close(pq["w7"], 3.0) and _close(pq["pct"], -0.02) and _close(pq["imp"], 100000 * -0.06 / 1000)
    assert _close(wh["w7"], 1.0) and _close(wh["pct"], 0.3) and _close(wh["imp"], 80000 * 0.3 / 1000)
    # Month mode: impact/day = the month's impressions per complete day × the eCPM change ÷ 1000
    for name, r in m["mm"]["rows"].items():
        if r["chg"] is not None:
            assert _close(r["imp"], r["yi"] / 10 * r["chg"] / 1000), name
    assert m["mm"]["rows"]["New Timer"]["chg"] is None                           # no February: no change, never a made-up one
    # here only Jan + Feb are whole months → 1 pair < 7 → Too early (the long history below judges for real)
    assert m["mm"]["swm"] == ["2026-01", "2026-02"] and m["mmJan"]["swm"] == []
    assert {r["st"] for r in m["mm"]["rows"].values()} == {"jaldi", "lagu"}


@needs_node
def test_cmp_month_bounds_and_labels(report):
    m = report["cmp_math"]
    assert m["bounds"] == {"bMin": "2025-12", "bMax": "2026-03", "bDef": "2026-02", "bOk": True, "cMin": "2026-01", "cMax": "2026-03",
                           "cOk": True, "ks": ["2025-12", "2026-01", "2026-02", "2026-03"]}
    assert m["madd"] == ["2025-12", "2026-01", "2025-01", "2027-01"]
    assert m["perL"] == ["Feb 2026", "Dec 2025 (20–31)", "Mar 2026 (1–10)", "Mar 2026 (1)"]


@needs_node
def test_cmp_taps_navigate_within_the_history_and_stay_put(report):
    n = report["cmp_nav"]
    # every tapped control is still there after the repaint (same signature, same count) — the stay-put layer finds it again
    assert len(n["taps"]) == 17 and all(t["before"] == t["after"] == 1 for t in n["taps"]), n["taps"]
    titles = {k: n[k]["title"] for k in n if k not in ("taps", "b7html")}
    assert titles == {"def": "yesterday vs last 7 days", "b14": "yesterday vs last 14 days", "b60": "yesterday vs last 60 days",
                      "feb": "yesterday vs Feb 2026", "jan": "yesterday vs Jan 2026", "dec": "yesterday vs Dec 2025 (20–31)",
                      "decStay": "yesterday vs Dec 2025 (20–31)", "feb2": "yesterday vs Feb 2026", "mar": "yesterday vs Mar 2026 (1–10)",
                      "marStay": "yesterday vs Mar 2026 (1–10)", "m": "Mar 2026 (1–10) vs Feb 2026", "mStay": "Mar 2026 (1–10) vs Feb 2026",
                      "mFeb": "Feb 2026 vs Jan 2026", "mJan": "Jan 2026 vs Dec 2025 (20–31)", "mJanStay": "Jan 2026 vs Dec 2025 (20–31)",
                      "backY": "yesterday vs Mar 2026 (1–10)", "b7": "yesterday vs last 7 days"}
    prev, nxt = 'aria-label="Previous month"', 'aria-label="Next month"'
    assert prev + " disabled>" in n["decStay"]["ctl"] and nxt + ">" in n["decStay"]["ctl"]          # the first month: ‹ off
    assert nxt + " disabled>" in n["marStay"]["ctl"] and prev + ">" in n["marStay"]["ctl"]          # the month of yesterday: › off
    assert nxt + " disabled>" in n["m"]["ctl"] and prev + " disabled>" in n["mJanStay"]["ctl"]
    assert prev + ">" in n["mFeb"]["ctl"] and nxt + ">" in n["mFeb"]["ctl"]
    assert n["feb2"]["cmp"]["bm"] == "" and n["mar"]["cmp"]["bm"] == "2026-03"                    # the default month kept as '' (it moves on)
    assert '<span class="ec-ml" aria-live="polite"><b>Mar 2026 (1–10)</b><span>vs Feb 2026</span></span>' in n["m"]["ctl"]
    assert '<span class="ec-ml" aria-live="polite">Dec 2025 (20–31)</span>' in n["dec"]["ctl"]
    assert "ecCmpB(" not in n["m"]["ctl"] and "ecCmpMon(" not in n["def"]["ctl"]                    # the arrows only with a month
    # what the card says: the exact days compared, partial months by their days
    assert "last 14 days avg (kal samet 14 poore din: <b>25 Feb–10 Mar</b>)" in n["b14"]["card"]
    assert "kal (<b>10 Mar</b>) ka eCPM − <b>Feb 2026</b> ka avg eCPM (<b>1 Feb–28 Feb</b> ki kamai" in n["feb"]["card"]
    assert "adhura mahina: sirf poore din, kal samet" in n["mar"]["card"] and "data 20 Dec se hai, isliye sirf 12 din" in n["dec"]["card"]
    j = n["mJan"]["card"]
    assert "<h3>All apps · Jan 2026 vs Dec 2025 (20–31)</h3>" in j and "<b>1 Jan–31 Jan</b> vs <b>20 Dec–31 Dec</b>" in j
    assert "(impressions ÷ 31 din)" in j and "adhura mahina hai" not in j
    assert "<b>Mar 2026 (1–10)</b> adhura mahina hai — sirf poore din (aaj ka adhura din nahi)." in n["m"]["card"]
    # each tap is saved for this viewer
    assert n["def"]["ls"] is None and json.loads(n["mJan"]["ls"]) == {"m": "m", "b": "mon", "bm": "2026-03", "cm": "2026-01"}
    assert json.loads(n["b7"]["ls"])["b"] == "7"
    # back on 7 days: the card is the default one again, word for word
    assert ("<h3>All apps · yesterday vs last 7 days</h3>" in n["b7html"] and
            "<b>Change</b> = kal ka eCPM − last 7 days avg (kal samet 7 poore din). <b>$ impact/day</b> = kal ke impressions × "
            "(kal ka eCPM − 7-day avg) ÷ 1,000 — sirf eCPM badalne se kal kitna kam / zyada kamaya.</div>" in n["b7html"])


STO = {"bigda": 0, "dhyan": 1, "normal": 2, "behtar": 3, "jaldi": 4, "lagu": 5}


def _sorted_ok(order, rows, key, d):
    by = {r["key"]: r for r in rows}
    if key == "name":
        vals = [by[k]["label"].lower() for k in order]
    else:
        judged = [k for k in order if by[k]["st"] != "lagu"]
        if key != "yi":
            assert order[:len(judged)] == judged, (key, order)               # low data (N/A) after every judged row
        val = (lambda k: STO[by[k]["st"]]) if key == "st" else (lambda k: by[k][key])
        vals = [val(k) for k in (order if key == "yi" else judged) if val(k) is not None]
    assert vals == sorted(vals, reverse=(d == "desc")), (key, d, vals)


@needs_node
def test_cmp_table_keeps_icons_row_tap_na_and_sorting(report):
    t = report["cmp_table"]
    for k in ("b14", "mon", "monDec", "monMar", "mm", "mmJan"):
        o = t[k]
        shown = [r for r in o["rows"] if r["act"]]
        tb = o["card"].split('<div id="ec-tb-a">')[1]
        assert tb.count('onclick="ecApp(this.dataset.n)"') == len(shown) == len(o["order"]), k   # every row opens its app
        assert tb.count('class="aicon') == len(shown), k                                            # every app name with its icon
        assert len(re.findall(r"<th[\s>]", tb)) == 8 and tb.count('aria-sort="none"') == 6 and tb.count('<th class="ec-on"') == 1, k
        _sorted_ok(o["order"], o["rows"], "imp", "asc")                                             # biggest loss first
        for tg in o["toggles"]:
            _sorted_ok(tg["order"], o["rows"], tg["k"], tg["d"])
    assert t["mon"]["order"][-1] == "Tiny Notes" and "N/A<small>low data</small>" in t["mon"]["card"]   # low data last, said so
    assert "Show 1 more apps (no data in these 2 months)" in t["mm"]["card"]                          # Old Radio: nothing in Feb / Mar
    assert "Hide 1 apps with no data in these 2 months" in t["mmJan"]["idle"]
    assert "Show 1 more apps (no data in 30 days)" in t["mon"]["card"]
    assert re.search(r'<td title="2,500,000 impressions · 250,000/day">2\.5M</td>', t["mm"]["card"])     # the month's impressions, per day on hover
    # a row tap opens that app under the same pick: Ad units + Countries follow it, Prev / Next in the table's order
    a = t["app"]
    assert a["app"] == "Demo Gallery" and "<h3>Ad units · Mar 2026 (1–10) vs Feb 2026</h3>" in a["units"]
    assert "<h3>Countries · Mar 2026 (1–10) vs Feb 2026</h3>" in a["countries"] and "ec-cw" not in a["countries"]
    assert "Mar 2026 (1–10)<br>eCPM" in a["units"] and "Mar 2026 (1–10)<br>impr" in a["countries"]
    assert a["order"] == t["mm"]["order"] and 'title="Photo Frames">Next app ›' in a["nav"]
    assert a["units"].count('<div class="ec-cmp">') == 1 and a["countries"].count('<div class="ec-cmp">') == 1
    assert t["back"] == {"app": "", "title": "Mar 2026 (1–10) vs Feb 2026"}
    assert "Yahan: kal (<b>10 Mar</b>) vs <b>Last 14 days</b> (25 Feb–10 Mar). Is app ka data <b>6 Mar 2026</b> se hai — usse pehle ke din khaali hain." in t["young"]
    assert "Is app ka data" not in t["youngDef"] and "Yahan:" not in t["youngDef"]                  # the default card: its words as before


@needs_node
def test_cmp_countries_follow_or_say_why_not(report, dash):
    c = report["cmp_cards"]
    comp = _comp(dash)
    assert c["def"]["ct"] == {"u": "yesterday vs last 7 days", "c": "yesterday vs last 7 days", "cb": 7} and c["def"]["ctlN"] == 2
    assert c["full14"]["ct"]["c"] == "yesterday vs last 14 days" and "ec-cw" not in c["full14"]["countries"]
    assert c["short14"]["ct"]["c"] == "yesterday vs last 14 days" and "ec-cw" not in c["short14"]["countries"]   # 25 Feb on: covered
    # the country report from 15 Feb only: February, 60 days, Mar vs Feb are not covered → the last covered view (14 days), said in one line
    for k, want in (("shortMon", "yesterday vs Feb 2026"), ("short60", "yesterday vs last 60 days"), ("shortMm", "Mar 2026 (1–10) vs Feb 2026")):
        x = c[k]
        assert x["ct"] == {"u": want, "c": "yesterday vs last 14 days", "cb": 14}, k
        assert "<h3>Countries · yesterday vs last 14 days</h3>" in x["countries"] and f"<h3>Ad units · {want}</h3>" in x["units"]
        assert x["countries"].count('class="ec-note ec-cw"') == 1
        assert f"⚠ Country report ka data <b>15 Feb 2026</b> se hai — <b>{want}</b> ke liye poora nahi, isliye yeh table abhi bhi <b>yesterday vs last 14 days</b> dikha rahi hai." in x["countries"]
    # its numbers are the 14-day ones; the ad units' are the pick's
    cd = {cn: {r[0]: [r[1], r[2]] for r in rows if r[0] != TODAY and r[0] >= "2026-02-15"} for cn, rows in dash["countries_daily"]["Demo Gallery"].items()}
    for r in c["shortMon"]["c"]:
        assert _close(r["w7"], _sum(cd[r["key"]], comp[-14:])["ec"]), r
    assert c["fresh"]["ct"]["c"] == "yesterday vs last 7 days"            # nothing covered before: the default
    assert c["shortDef"]["ct"]["c"] == "yesterday vs last 7 days" and "ec-cw" not in c["shortDef"]["countries"]


@needs_node
def test_cmp_pick_restored_and_reset_safely(report):
    r = report["cmp_restore"]
    assert (r["mFeb"]["title"], r["monJan"]["title"], r["b30"]["title"]) == ("Feb 2026 vs Jan 2026", "yesterday vs Jan 2026", "yesterday vs last 30 days")
    assert r["before"]["title"] == "yesterday vs Feb 2026" and r["before"]["cmp"]["bm"] == ""            # a month before the history → the default month
    assert r["after"]["title"] == "Mar 2026 (1–10) vs Feb 2026" and r["after"]["cmp"]["cm"] == ""        # after it → the newest
    assert json.loads(r["before"]["ls"])["bm"] == "" and json.loads(r["after"]["ls"])["cm"] == ""        # the fixed pick saved back
    for k in ("junk", "bad", "none"):
        assert r[k]["cmp"] == {"m": "y", "b": "7", "bm": "", "cm": ""} and r[k]["title"] == "yesterday vs last 7 days", k
    # a build with less history (from 1 Feb): the stored 60 days / Dec no longer fit → the default; 60 days greyed out
    s = r["shorter"]
    assert s["cmp"] == {"m": "y", "b": "7", "bm": "", "cm": ""} and json.loads(s["ls"]) == s["cmp"]
    assert s["bounds"] == ["2026-02", "2026-03", "2026-03", "2026-03", True]
    assert "onclick=\"ecCmpB('60')\" disabled title=\"Sirf 38 din ka data\">60 days</button>" in s["ctl"]
    assert r["blocked0"]["title"] == "yesterday vs last 7 days" and r["blocked"]["title"] == "yesterday vs last 30 days"   # storage blocked: still works


LONG_PICKS = {'{"m":"m"}': ("2026-03", "2026-02"), '{"m":"m","cm":"2026-02"}': ("2026-02", "2026-01"),
              '{"m":"m","cm":"2025-09"}': ("2025-09", "2025-08"), '{"m":"m","cm":"2025-08"}': ("2025-08", "2025-07")}


@needs_node
def test_cmp_month_to_month_status_on_a_long_history(report):
    lg = _long_fixture()
    _, apps = _maps(lg)
    comp = _comp(lg)
    by = _by_month(comp)
    sel = report["cmp_long"]["sel"]
    for k, (cm, pm) in LONG_PICKS.items():
        g = sel[k]
        assert g["cur"] == by[cm] and g["base"] == by[pm] and g["ncur"] == len(by[cm]), k
        for name, dm in apps.items():
            _same_rows(g["rows"][name], _row_cmp(dm, comp, by[cm], by[pm], pm), (k, name))
    now = sel['{"m":"m"}']
    assert now["swm"] == [f"2025-{m:02d}" for m in range(2, 13)] + ["2026-01", "2026-02"]                # 13 whole months → 12 pairs
    assert {n: r["st"] for n, r in now["rows"].items()} == {"Steady Cam": "bigda", "Calm Notes": "normal", "Bright Tiles": "behtar",
                                                             "Mid Watch": "dhyan", "Fresh Cards": "jaldi", "Quiet Clock": "lagu"}
    sc = now["rows"]["Steady Cam"]   # by hand: Feb $2.06 → Mar $1.648 (−20%); swing = (|0.97/1.03 − 1| + |1.03/0.97 − 1|) ÷ 2
    assert _close(sc["w7"], 2.06) and _close(sc["y"], 1.648) and _close(sc["pct"], -0.2) and _close(sc["imp"], 50000 * (1.648 - 2.06) / 1000)
    assert abs(sc["swing"] - (abs(0.97 / 1.03 - 1) + abs(1.03 / 0.97 - 1)) / 2) < 1e-12
    assert now["rows"]["Fresh Cards"]["swing"] is None                                                   # its own whole months: Dec, Jan, Feb
    assert all(r["st"] == "normal" for n, r in sel['{"m":"m","cm":"2025-09"}']["rows"].items() if n not in ("Fresh Cards",))   # 7 pairs: judged
    assert all(r["st"] == "jaldi" for n, r in sel['{"m":"m","cm":"2025-08"}']["rows"].items() if n != "Fresh Cards")         # 6 pairs: Too early
    # Yesterday mode keeps the day-to-day rule, whatever the baseline (flat days here → the 2% floor)
    assert sel['{"m":"y","b":"mon"}']["rows"]["Mid Watch"]["st"] == "bigda" and sel['{"m":"y","b":"mon"}']["swm"] == []
    lc = report["cmp_long"]
    assert lc["order"] == ["Steady Cam", "Fresh Cards", "Mid Watch", "Calm Notes", "Bright Tiles", "Quiet Clock"]
    assert "mahine-dar-mahine ke normal utaar-chadhaav" in lc["card"] and "<b>Too early</b> = abhi 8 poore mahine ka data nahi" in lc["card"]
    assert "<b>N/A</b> = Mar 2026 (1–10) me 1,000 se kam impressions" in lc["card"]


# the default view, byte for byte: the page before the picker and this one (comparison row taken out), $ and ₹, every sort
def _snap(tmp, page, dash):
    js = max(re.findall(r"<script>(.*?)</script>", page, re.S), key=len)
    sp, fx = os.path.join(tmp, "p.js"), os.path.join(tmp, "f.json")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(js)
    with open(fx, "w", encoding="utf-8") as f:
        json.dump({"dashboard": dash}, f)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "ecpm_frontend.js"), sp, fx, "snap"], check=True, capture_output=True, text=True, timeout=180)
    rep = json.loads(out.stdout)
    assert rep["errors"] == [], rep["errors"]
    return rep["snap"]


@needs_node
def test_cmp_default_view_is_byte_identical_to_before(tmp_path, dash):
    try:
        old = subprocess.run(["git", "-C", ROOT, "show", BASE_REV + ":frontend/index.html"], check=True, capture_output=True,
                             text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip("the page before the picker is not in this checkout's history")
    (tmp_path / "old").mkdir()
    (tmp_path / "new").mkdir()
    a = _snap(str(tmp_path / "old"), old, dash)
    b = _snap(str(tmp_path / "new"), _page(), dash)
    assert a["hasCtl"] is False and b["hasCtl"] is True
    assert len(a["S"]) > 40 and a["S"].keys() == b["S"].keys()
    for k in a["S"]:
        assert a["S"][k] == b["S"][k], k
    assert "All apps · yesterday vs last 7 days" in b["S"]["all_USD"] and "Countries · yesterday vs last 7 days" in b["S"]["app_INR_Demo Gallery"]


def test_cmp_control_css_phone_and_tap_targets():
    css = _page()
    css = css[css.index("/* ===== 📈 eCPM trend"):css.index("/* \"Stay after N days\"")]
    assert re.search(r"\.ec-cmp\{display:flex;flex-wrap:wrap", css)                                     # the row wraps
    assert ".ec-cmp .ec-seg{overflow-x:auto" in css                                                    # a chip group scrolls inside it
    assert ".ec-tc{padding:0;margin-bottom:14px;min-width:0;overflow:hidden}" in css                    # never the page
    assert re.search(r"\.ec-ma\{[^}]*min-width:36px;min-height:36px", css)                              # ‹ › ≥ 36px
    phone = css[css.index("@media(max-width:760px)"):]
    assert ".ec-ma{min-width:40px;min-height:40px}.ec-cmp .ec-seg button{min-height:40px}" in phone      # chips = ‹ › height
    assert ".ec-cmp .ec-seg button{flex:none;min-height:36px}" in css
    assert re.search(r"\.ec-ml\{[^}]*min-width:11\.2em", css)                                            # a fixed label: ‹ › never move
    assert re.search(r"\.ec-mnav\{[^}]*flex:none", css)
