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
    leaving the view, sorting, the tap-only tooltip pin;
  * the payload carries the FULL daily history (no trim) — the view's "Full" range reads it.
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
        json.dump({"dashboard": dash}, f)
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
    assert "if(id==='ecpm') ecPaint(); else ecLeft();" in h and "root.append(renderEcpm());" in h
    assert 'body[data-screen="ecpm"] #rangectl' in h                                       # the header Period is not this view's
    for t in ("['30','30 days'],['90','90 days'],['365','1 year'],['all','Full']", "[['day','Day'],['month','Month']]",
              "eCPM = har 1,000 ads (impressions) pe kamai", "← All apps (eCPM)", "← Overview"):
        assert t in h, t
    css = h[h.index("/* ===== 📈 eCPM trend"):h.index("/* \"Stay after N days\"")]
    assert ".ec-t th:first-child,.ec-t td:first-child{position:sticky;left:0" in css      # the App column stays on screen
    assert ".ec-tw{overflow-x:auto" in css                                                 # the table scrolls inside its card
    assert re.search(r"\.ec-seg button\{min-height:3[2-9]px", css) and re.search(r"\.ec-lnk\{[^}]*min-height:3[2-9]px", css)
    assert "@media(max-width:760px)" in css and ".ec-kpis.row.c4{grid-template-columns:repeat(2,minmax(0,1fr))" in css


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
