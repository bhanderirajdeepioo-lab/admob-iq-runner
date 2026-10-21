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
    pick restored per viewer, and the default view byte-identical to the page before the picker (git: BASE_REV);
    a baseline of a few hundred impressions (a launch ramp) = N/A "low data (baseline)", sorted last; a row that starts
    inside a labelled period prints its own days; the 1st of a month (the month of yesterday is whole, never "adhura");
    a short history keeps its picked chip lit; a partial month's status measured like the comparison (its first N days vs
    the whole month before, on earlier months) and Too early under 7 complete days — checked on noise only; the Countries
    card checked day by day (a failed chunk = a hole, its days named);
  * Month vs month's two pickers (owner, 21 Oct: "month vs month me sept vs aug nahi — oct vs sept, oct vs aug, ese oct vs
    month wise"): the current month stays (Oct 2026 (1–20)) and the compared month moves on its own — Oct vs Sep / Aug / Jul
    recounted here; the current month's ‹ › pushing a compared month it reaches; the limits; the status of two months that
    are not adjacent judged on the row's own swing over the SAME gap (Too early when that has under 7 pairs); the stored
    pick's old shape migrated; "Yesterday vs" byte-identical to the page before the two pickers (git: PREV_REV).
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
MDAYS_MIN = 7                 # Month vs month: complete days a partial newest month needs before its status is judged


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


def _with(today, units, countries=None):
    """a SYNTHETIC dashboard for another day: `units` = [(app, unit name, rows)], today's row made absurd (never counted)."""
    pl = []
    for k, (app, name, rows) in enumerate(units):
        rows = [([r[0], 10 ** 12, 1, 5, 4, 0] if r[0] == today else r) for r in rows if r[0] <= today]
        pl.append(_unit(f"ca-app-pub-0000000000000031/31000000{k:02d}", name, "banner", app, rows))
    apps = sorted({p["app"] for p in pl})
    d = _fixture()
    d.update({"today_date": today, "latest_complete": (date.fromisoformat(today) - timedelta(days=1)).isoformat(),
              "placements": pl, "countries_daily": countries or {}, "apps": [dict(d["apps"][0], name=a) for a in apps],
              "apps_catalog": [{"account_id": "pub-0000000000000000", "app_id": f"ca-app-pub-0000000000000000~{k + 40:010d}", "app_name": a,
                                "rev": 1.0, "selected": True, "account_decided": True} for k, a in enumerate(apps)]})
    return d


def _rows(days, impr, ecpm_of):
    """[date, earn_micros, impr, …] rows, impressions and eCPM per day (no "today" handling: _with does that)."""
    out = []
    for k, d in enumerate(days):
        i = impr(d, k) if callable(impr) else impr
        out.append([d, int(round(ecpm_of(d, k) * i * 1000)), i, int(i * 1.3), int(i * 1.1), i // 100])
    return out


RAMP_TODAY = "2026-10-21"


def _ramp_fixture():
    """an app launched 2 days before September ended (a ramp of 150 impressions a day at $9, then 50k a day at $3), one
    launched the same day at full volume, one started inside October, a steady one."""
    days = _days(date(2026, 1, 1), date.fromisoformat(RAMP_TODAY))
    launch = [d for d in days if d >= "2026-09-29"]
    ramp9 = lambda d, k: 9.0 if d < "2026-10-01" else 3.0
    return _with(RAMP_TODAY, [
        ("Steady Mail", "mail_banner", _rows(days, 50000, _alt(3.0, 0.01))),
        ("Ramp Cards", "cards_banner", _rows(launch, lambda d, k: 150 if d < "2026-10-01" else 50000, ramp9)),
        ("Big Launch", "launch_inter", _rows(launch, 50000, ramp9)),
        ("Mid Month", "mid_native", _rows([d for d in days if d >= "2026-10-10"], 30000, _alt(2.0, 0.01))),
    ])


def _first_fixture():
    """today = the 1st of a month: the month of yesterday (October) is whole."""
    days = _days(date(2026, 1, 1), date(2026, 11, 1))
    return _with("2026-11-01", [("Steady Mail", "mail_banner", _rows(days, 50000, _alt(3.0, 0.01)))])


def _short_fixture():
    """5 complete days of history (6–10 Mar): the 7-day default is picked, longer ranges are greyed out."""
    return _with(TODAY, [("Steady Mail", "mail_banner", _rows(_days(date(2026, 3, 6), date(2026, 3, 11)), 50000, _alt(3.0, 0.01)))])


NOISE_START, NOISE_END, NOISE_APPS = date(2025, 8, 1), date(2026, 12, 1), 40


def _noise_fixture():
    """steady eCPM with ±8% random day-to-day noise only (a fixed seed) — nothing really changes, month after month."""
    import random
    rnd = random.Random(20261021)
    days = _days(NOISE_START, NOISE_END)
    units = [(f"Noise App {a:02d}", f"noise_{a:02d}", _rows(days, 50000, lambda d, k: 4.0 * (1 + rnd.uniform(-0.08, 0.08))))
             for a in range(NOISE_APPS)]
    return _with(NOISE_END.isoformat(), units)


OCT_TODAY = "2026-10-21"
OCT_START = date(2024, 10, 1)


def _octs_fixture():
    """two years to 20 Oct 2026, eCPM flat inside a month: month-to-month alternating apps (every other month alike), a
    steady one, a young one, a thin October."""
    days = _days(OCT_START, date.fromisoformat(OCT_TODAY))

    def alt(base, amp, oct_of):
        m = lambda d: base * (1 + amp if _midx(d) % 2 else 1 - amp)
        return lambda d, k: oct_of(m) if d[:7] == "2026-10" else m(d)

    return _with(OCT_TODAY, [
        # ±3% month to month; October = September × 0.8
        ("Steady Cam", "cam_banner", _rows(days, 50000, alt(2.0, 0.03, lambda m: m("2026-09-01") * 0.8))),
        # ±10% month to month (every other month alike); October = August × 0.9: −10% vs Aug — a real drop against how much a
        # month differs from the one 2 before it (nothing), lost in the ±20% month-to-month swing
        ("Two Step", "step_inter", _rows(days, 40000, alt(3.0, 0.10, lambda m: m("2026-08-01") * 0.9))),
        # flat; October −1%
        ("Calm Notes", "notes_native", _rows(days, 30000, alt(3.0, 0.0, lambda m: 2.97))),
        # from 1 Jun 2026 only: 4 whole months of its own → Too early
        ("Late Start", "late_banner", _rows([d for d in days if d >= "2026-06-01"], 20000, lambda d, k: 4.0 if d[:7] == "2026-10" else 5.0)),
        # October: 40 impressions a day (800 so far) → N/A
        ("Quiet Clock", "clock_banner", _rows(days, lambda d, k: 40 if d[:7] == "2026-10" else 2000, alt(1.5, 0.03, lambda m: 1.4))),
    ])


# ── the independent maths (Python, straight from the raw rows) ──────────────────────────────────────────────────────────
def _maps(dash, upto=None):
    """day → [earn, impr] per app (and the portfolio): today's partial day (and anything after `upto`) left out."""
    pf, apps = {}, {}
    today = upto or dash.get("today_date", TODAY)
    for p in dash["placements"]:
        a = apps.setdefault(p["app"], {})
        for d, e, i, *_ in p["daily"]:
            if (d >= today) if upto else (d == today):
                continue
            for m in (pf, a):
                x = m.setdefault(d, [0, 0])
                x[0] += e
                x[1] += i
    return pf, apps


def _comp(dash, upto=None):
    if upto:
        return sorted({r[0] for p in dash["placements"] for r in p["daily"] if r[0] < upto})
    return sorted({r[0] for p in dash["placements"] for r in p["daily"]} - {dash.get("today_date", TODAY)})


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
        json.dump({"dashboard": dash, "long": _long_fixture(), "ramp": _ramp_fixture(), "first": _first_fixture(),
                   "short": _short_fixture(), "noise": _noise_fixture(), "octs": _octs_fixture()}, f)
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


MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fmt(d):
    return f"{int(d[8:10])} {MON[int(d[5:7]) - 1]}"


def _span(days):
    return "" if not days else (_fmt(days[0]) if days[0] == days[-1] else f"{_fmt(days[0])}–{_fmt(days[-1])}")


def _next_month(k):
    y, m = int(k[:4]), int(k[5:7])
    return f"{y + (m == 12)}-{(m % 12) + 1:02d}"


def _add_months(k, n):
    t = int(k[:4]) * 12 + int(k[5:7]) - 1 + n
    return f"{t // 12}-{t % 12 + 1:02d}"


def _gap(a, b):
    """months from a to b ("2026-08" → "2026-10" = 2)"""
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


def _first(dm):
    return min((d for d, x in dm.items() if x[1] > 0 or x[0] > 0), default="")


def _dn(cur, pm):
    """Month mode: the compared month's complete days when it is partial (0 = whole); Yesterday mode: 0."""
    return 0 if not pm or _full(cur[0][:7], cur) else len(cur)


def _mswing(dm, by, pm, dn=0, g=1):
    """the usual month-to-month swing, measured like the comparison it judges: over the whole months up to pm (the last
    12 + g), each one's first dn days (the whole month when dn = 0) vs the whole month g months before it (g = the pick's
    gap: Oct vs Aug → 2); only months the row had from the 1st, both sides ≥ MIN_IMPR impressions and some earnings; the
    median |change|, None under 7 pairs."""
    if dn and dn < MDAYS_MIN:                     # a newest month of 1–6 complete days is not judged (Too early)
        return None
    f = _first(dm)
    ks = [k for k in sorted(by) if k <= pm and _full(k, by[k])][-(12 + g):]
    ch = []
    for b in ks:
        a = _add_months(b, -g)
        if a not in ks or not f or by[a][0] < f:
            continue
        sa, sb = _sum(dm, by[a]), _sum(dm, by[b][:dn] if dn else by[b])
        if sa["i"] >= MIN_IMPR and sa["e"] > 0 and sb["i"] >= MIN_IMPR and sb["e"] > 0:
            ch.append(abs(sb["ec"] / sa["ec"] - 1))
    return statistics.median(ch) if len(ch) >= 7 else None


def _row_cmp(dm, comp, cur, base, pm=None, dn=0):
    """one row for a pick: pm = the compared (older) month in Month mode (its swing is over the same gap as the pick, on the
    first dn days), else the day swing. A row that starts inside a period carries its own days (ob / oc), a baseline under
    MIN_IMPR = N/A."""
    f = _first(dm)
    own = (lambda days: [d for d in days if d >= f] if f and days and f > days[0] else None)
    ob, oc = own(base), (own(cur) if pm else None)
    y, w = _sum(dm, cur), _sum(dm, base)
    chg = (y["ec"] - w["ec"]) if y["ec"] is not None and w["ec"] is not None else None
    pct = chg / w["ec"] if chg is not None and w["ec"] else None
    ncur = (len(oc) if oc is not None else len(cur)) if pm else 1
    sw = _mswing(dm, _by_month(comp), pm, dn, _gap(pm, cur[0][:7])) if pm else _swing(dm, comp[-31:-1])
    act = (y["i"] > 0 or w["i"] > 0) if pm else _sum(dm, comp[-30:])["i"] > 0
    low_b = y["i"] >= MIN_IMPR and 0 < w["i"] < MIN_IMPR
    return {"y": y["ec"], "yi": y["i"], "w7": w["ec"], "chg": chg, "pct": pct,
            "imp": (y["i"] / ncur) * chg / 1000 if chg is not None and ncur else None, "swing": sw,
            "st": "lagu" if low_b else _status(pct, sw, y["i"]), "act": act, "nc": ncur, "lowB": low_b,
            "ob": _span(ob or []), "oc": _span(oc or [])}


def _same_rows(got, exp, name):
    for k in ("y", "w7", "chg", "pct", "imp", "swing"):
        assert _close(got[k], exp[k]), (name, k, got[k], exp[k])
    assert got["yi"] == exp["yi"] and got["st"] == exp["st"] and got["act"] == exp["act"], (name, got, exp)
    for k in ("nc", "lowB", "ob", "oc"):
        assert got[k] == exp[k], (name, k, got[k], exp[k])


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
    # the compared month picked on its own (the current one stays)
    "mmVsJan": (MAR, JAN, "2026-01", "Mar 2026 (1–10) vs Jan 2026", "Mar 2026 (1–10)<br>eCPM", "Jan 2026<br>eCPM"),
    "mmVsDec": (MAR, DEC, "2025-12", "Mar 2026 (1–10) vs Dec 2025 (20–31)", "Mar 2026 (1–10)<br>eCPM", "Dec 2025 (20–31)<br>eCPM"),
    "mmFebDec": (FEB, DEC, "2025-12", "Feb 2026 vs Dec 2025 (20–31)", "Feb 2026<br>eCPM", "Dec 2025 (20–31)<br>eCPM"),
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
        assert g.get("g") == (_gap(pm, cur[0][:7]) if pm else None), k
        assert (g["title"], g["colCur"], g["colBase"]) == (title, cc, cb), k
        assert g["colImp"] == cc.replace("eCPM", "impr"), k
        for name, dm in apps.items():
            _same_rows(g["rows"][name], _row_cmp(dm, comp, cur, base, pm, _dn(cur, pm)), (k, name))
        for p in dash["placements"]:                                              # one app's ad units, the same maths
            if p["app"] != "Demo Gallery":
                continue
            dm = {r[0]: [r[1], r[2]] for r in p["daily"] if r[0] != TODAY}
            u, exp = next(x for x in g["units"] if x["id"] == p["id"]), _row_cmp(dm, comp, cur, base, pm, _dn(cur, pm))
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
    assert (m["mmVsJan"]["g"], m["mmVsDec"]["g"], m["mmFebDec"]["g"]) == (2, 3, 2) and m["mmVsJan"]["swm"] == ["2026-01"]
    # by hand: March (1–10) vs the whole of January — the same impressions every day, so a month's eCPM = the plain mean of
    # its daily eCPMs; impact/day = 100k impressions a day × the change ÷ 1000
    pq, dm = m["mmVsJan"]["rows"]["Puzzle Quest"], apps["Puzzle Quest"]
    assert _close(pq["w7"], statistics.mean(dm[d][0] / (dm[d][1] * 1000) for d in JAN), 1e-12)
    assert _close(pq["y"], statistics.mean(dm[d][0] / (dm[d][1] * 1000) for d in MAR), 1e-12)
    assert pq["yi"] == 100000 * 10 and _close(pq["imp"], 100000 * pq["chg"] / 1000)


@needs_node
def test_cmp_month_bounds_and_labels(report):
    m = report["cmp_math"]
    assert m["bounds"] == {"bMin": "2025-12", "bMax": "2026-03", "bDef": "2026-02", "bOk": True, "cMin": "2026-01", "cMax": "2026-03",
                           "cOk": True, "vMin": "2025-12", "ks": ["2025-12", "2026-01", "2026-02", "2026-03"]}
    assert m["gap"] == [1, 3, 3, 0]
    assert m["madd"] == ["2025-12", "2026-01", "2025-01", "2027-01"]
    assert m["perL"] == ["Feb 2026", "Dec 2025 (20–31)", "Mar 2026 (1–10)", "Mar 2026 (1)"]


@needs_node
def test_cmp_taps_navigate_within_the_history_and_stay_put(report):
    n = report["cmp_nav"]
    # every tapped control is still there after the repaint (same signature, same count) — the stay-put layer finds it again
    assert len(n["taps"]) == 26 and all(t["before"] == t["after"] == 1 for t in n["taps"]), n["taps"]
    titles = {k: n[k]["title"] for k in n if k not in ("taps", "b7html")}
    M3, F, J, D = "Mar 2026 (1–10)", "Feb 2026", "Jan 2026", "Dec 2025 (20–31)"
    assert titles == {"def": "yesterday vs last 7 days", "b14": "yesterday vs last 14 days", "b60": "yesterday vs last 60 days",
                      "feb": "yesterday vs Feb 2026", "jan": "yesterday vs Jan 2026", "dec": "yesterday vs Dec 2025 (20–31)",
                      "decStay": "yesterday vs Dec 2025 (20–31)", "feb2": "yesterday vs Feb 2026", "mar": "yesterday vs Mar 2026 (1–10)",
                      "marStay": "yesterday vs Mar 2026 (1–10)",
                      # Month vs month: the compared month alone (‹ ›), then the current month alone, pushing it when it reaches it
                      "m": f"{M3} vs {F}", "mCurStay": f"{M3} vs {F}", "mVsStay": f"{M3} vs {F}",
                      "vJan": f"{M3} vs {J}", "vDec": f"{M3} vs {D}", "vDecStay": f"{M3} vs {D}", "vJan2": f"{M3} vs {J}",
                      "cFeb": f"{F} vs {J}", "cJan": f"{J} vs {D}", "cJanStay": f"{J} vs {D}",
                      "cFeb2": f"{F} vs {D}", "cMar": f"{M3} vs {D}", "vFeb": f"{M3} vs {F}", "monInM": f"{M3} vs {J}",
                      "backY": "yesterday vs Mar 2026 (1–10)", "b7": "yesterday vs last 7 days"}
    prev, nxt = 'aria-label="Previous month"', 'aria-label="Next month"'
    assert prev + " disabled>" in n["decStay"]["ctl"] and nxt + ">" in n["decStay"]["ctl"]          # the first month: ‹ off
    assert nxt + " disabled>" in n["marStay"]["ctl"] and prev + ">" in n["marStay"]["ctl"]          # the month of yesterday: › off
    # the two pickers' arrows: on / off at their limits (cp / cn = the current month's ‹ ›, vp / vn = the compared month's)
    lab = {"cp": 'aria-label="Current month: previous"', "cn": 'aria-label="Current month: next"',
           "vp": 'aria-label="Compared month: previous"', "vn": 'aria-label="Compared month: next"'}

    def off(k):
        c = n[k]["ctl"]
        assert all(c.count(v) == 1 for v in lab.values()), k
        return {a for a, v in lab.items() if v + " disabled>" in c}
    assert off("m") == {"cn", "vn"}                       # this month (newest) vs the month just before it
    assert off("vJan") == {"cn"} and off("vDecStay") == {"cn", "vp"}          # the first month of the history: the compared ‹ off
    assert off("cFeb") == {"vn"} and off("cJanStay") == {"cp", "vp", "vn"}    # the second month: no older current month
    assert off("cFeb2") == {"vp"} and off("cMar") == {"cn", "vp"}             # the compared month stayed on the first month
    m = n["m"]["ctl"]
    assert ('<div class="ec-mnav" role="group" aria-label="Current month"><button type="button" class="ec-ma" onclick="ecCmpCur(-1)" '
            'aria-label="Current month: previous">‹</button><span class="ec-ml" aria-live="polite"><b>Mar 2026 (1–10)</b></span>'
            '<button type="button" class="ec-ma" onclick="ecCmpCur(1)" aria-label="Current month: next" disabled>›</button></div>') in m
    assert ('<div class="ec-mvs"><span class="ec-vs">vs</span><div class="ec-mnav" role="group" aria-label="Compared month">'
            '<button type="button" class="ec-ma" onclick="ecCmpVs(-1)" aria-label="Compared month: previous">‹</button>'
            '<span class="ec-ml" aria-live="polite">Feb 2026</span><button type="button" class="ec-ma" onclick="ecCmpVs(1)" '
            'aria-label="Compared month: next" disabled>›</button></div></div></div>') in m
    assert '<span class="ec-ml" aria-live="polite">Dec 2025 (20–31)</span>' in n["dec"]["ctl"] and "Dec 2025 (20–31)</span>" in n["vDec"]["ctl"]
    assert "ecCmpB(" not in m and "ecCmpMon(" not in m and "ecCmpMon(" not in n["def"]["ctl"]        # the Yesterday-vs arrows only with a month
    assert "ecCmpCur(" not in n["mar"]["ctl"] and "ecCmpVs(" not in n["mar"]["ctl"]                  # and the two pickers only in Month vs month
    # what the card says: the exact days compared, partial months by their days
    assert "last 14 days avg (kal samet 14 poore din: <b>25 Feb–10 Mar</b>)" in n["b14"]["card"]
    assert "kal (<b>10 Mar</b>) ka eCPM − <b>Feb 2026</b> ka avg eCPM (<b>1 Feb–28 Feb</b> ki kamai" in n["feb"]["card"]
    assert "adhura mahina: sirf poore din, kal samet" in n["mar"]["card"] and "data 20 Dec se hai, isliye sirf 12 din" in n["dec"]["card"]
    j = n["cJan"]["card"]
    assert "<h3>All apps · Jan 2026 vs Dec 2025 (20–31)</h3>" in j and "<b>1 Jan–31 Jan</b> vs <b>20 Dec–31 Dec</b>" in j
    assert "(impressions ÷ 31 din)" in j and "adhura mahina hai" not in j and "<b>Dec 2025 (20–31)</b> = data 20 Dec se hai, isliye sirf 12 din." in j
    assert "<b>Mar 2026 (1–10)</b> adhura mahina hai — sirf poore din (aaj ka adhura din nahi)." in n["m"]["card"]
    v = n["vJan"]["card"]                                  # two months apart: the title, the days, impact per day of March
    assert "<h3>All apps · Mar 2026 (1–10) vs Jan 2026</h3>" in v and "<b>1 Mar–10 Mar</b> vs <b>1 Jan–31 Jan</b>" in v
    assert "<b>Mar 2026 (1–10)</b> ka eCPM − <b>Jan 2026</b> ka eCPM" in v and "(impressions ÷ 10 din)" in v
    # each tap is saved for this viewer: the current month and the compared one on their own ('' = the default, moves on)
    ls = lambda k: json.loads(n[k]["ls"])
    assert n["def"]["ls"] is None
    assert ls("vDec") == {"v": 2, "m": "m", "b": "mon", "bm": "2026-03", "cm": "", "vm": "2025-12"}
    assert (ls("cFeb")["cm"], ls("cFeb")["vm"]) == ("2026-02", "") and (ls("cJan")["cm"], ls("cJan")["vm"]) == ("2026-01", "")
    assert (ls("cFeb2")["cm"], ls("cFeb2")["vm"]) == ("2026-02", "2025-12") and (ls("cMar")["cm"], ls("cMar")["vm"]) == ("", "2025-12")
    assert (ls("vFeb")["cm"], ls("vFeb")["vm"]) == ("", "")
    assert ls("b7")["b"] == "7" and ls("b7")["m"] == "y"
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
    v = t["appVs"]                                            # Mar vs Jan (2 months apart) in one app: both cards follow, recounted
    assert v["ct"] == {"u": "Mar 2026 (1–10) vs Jan 2026", "c": "Mar 2026 (1–10) vs Jan 2026"} and "ec-cw" not in v["countries"]
    assert "<h3>Ad units · Mar 2026 (1–10) vs Jan 2026</h3>" in v["units"] and "<h3>Countries · Mar 2026 (1–10) vs Jan 2026</h3>" in v["countries"]
    assert "Jan 2026<br>eCPM" in v["units"] and "Yahan: <b>Mar 2026 (1–10)</b> (1 Mar–10 Mar) vs <b>Jan 2026</b> (1 Jan–31 Jan)" in v["units"]
    comp = _comp(_fixture())
    dms = {p["id"]: {r[0]: [r[1], r[2]] for r in p["daily"] if r[0] != TODAY} for p in _fixture()["placements"] if p["app"] == "Demo Gallery"}
    dms.update({cn: {r[0]: [r[1], r[2]] for r in rows if r[0] != TODAY} for cn, rows in _fixture()["countries_daily"]["Demo Gallery"].items()})
    for r in v["u"] + v["c"]:
        exp = _row_cmp(dms[r["key"]], comp, MAR, JAN, "2026-01", 10)
        for k in ("y", "w7", "chg", "pct", "imp", "swing"):
            assert _close(r[k], exp[k]), (r["key"], k)
        assert r["yi"] == exp["yi"] and r["st"] == exp["st"], r["key"]
    assert len(v["u"]) == 2 and len(v["c"]) == 2
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
    D = {"v": 2, "m": "y", "b": "7", "bm": "", "cm": "", "vm": ""}
    M3 = "Mar 2026 (1–10)"
    # the shape stored before the two pickers (its cm moved BOTH months): the month pair → this month vs the month before,
    # the rest kept, saved back in the new shape
    for k, want, cmp in (("oldMm", f"{M3} vs Feb 2026", dict(D, m="m")), ("oldMmMon", f"{M3} vs Feb 2026", dict(D, m="m", b="mon", bm="2026-01")),
                         ("monJan", "yesterday vs Jan 2026", dict(D, b="mon", bm="2026-01")), ("b30", "yesterday vs last 30 days", dict(D, b="30"))):
        assert r[k]["title"] == want and r[k]["cmp"] == cmp and json.loads(r[k]["ls"]) == cmp, k
    # the new shape: each month as stored; a compared month that is not older than the current one / outside the history /
    # junk → the month just before the current one; the default kept as ''
    for k, want, cm, vm in (("mFeb", "Feb 2026 vs Jan 2026", "2026-02", ""), ("mFebDec", "Feb 2026 vs Dec 2025 (20–31)", "2026-02", "2025-12"),
                            ("mVsJan", f"{M3} vs Jan 2026", "", "2026-01"), ("vmSame", "Feb 2026 vs Jan 2026", "2026-02", ""),
                            ("vmAfter", "Feb 2026 vs Jan 2026", "2026-02", ""), ("vmBefore", f"{M3} vs Feb 2026", "", ""),
                            ("vmJunk", f"{M3} vs Feb 2026", "", ""), ("vmDefault", "Feb 2026 vs Jan 2026", "2026-02", ""),
                            ("future", f"{M3} vs Feb 2026", "", "")):
        assert r[k]["title"] == want and (r[k]["cmp"]["cm"], r[k]["cmp"]["vm"]) == (cm, vm) and json.loads(r[k]["ls"]) == r[k]["cmp"], k
    assert r["future"]["cmp"]["b"] == "14" and r["future"]["cmp"]["v"] == 2
    assert r["before"]["title"] == "yesterday vs Feb 2026" and r["before"]["cmp"]["bm"] == ""            # a month before the history → the default month
    assert r["after"]["title"] == f"{M3} vs Feb 2026" and r["after"]["cmp"]["cm"] == ""                   # after it → the newest
    assert json.loads(r["before"]["ls"])["bm"] == "" and json.loads(r["after"]["ls"])["cm"] == ""        # the fixed pick saved back
    for k in ("junk", "arr", "bad", "none"):
        assert r[k]["cmp"] == D and r[k]["title"] == "yesterday vs last 7 days", k
    # a build with less history (from 1 Feb): the stored 60 days / Dec no longer fit → the default; 60 days greyed out
    s = r["shorter"]
    assert s["cmp"] == D and json.loads(s["ls"]) == s["cmp"]
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
            _same_rows(g["rows"][name], _row_cmp(dm, comp, by[cm], by[pm], pm, _dn(by[cm], pm)), (k, name))
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


# ── review fixes: a thin baseline, rows that start inside a period, the 1st of a month, a short history, a partial month's
# status on noise, the Countries card checked day by day ──────────────────────────────────────────────────────────────────
@needs_node
def test_cmp_thin_baseline_is_low_data_and_own_days_are_printed(report):
    """an app launched 2 days before September ended: its "Sep 2026" is 300 impressions of a launch ramp — never a loss."""
    dash = _ramp_fixture()
    _, apps = _maps(dash)
    comp = _comp(dash)
    by = _by_month(comp)
    e = report["cmp_edge"]
    picks = {"mon": ([comp[-1]], by["2026-09"], None), "mm": (by["2026-10"], by["2026-09"], "2026-09"), "b30": ([comp[-1]], comp[-30:], None)}
    for k, (cur, base, pm) in picks.items():
        g = e[k]
        assert g["cur"] == cur and g["base"] == base, k
        for name, dm in apps.items():
            _same_rows(g["rows"][name], _row_cmp(dm, comp, cur, base, pm, _dn(cur, pm)), (k, name))
    for k in ("mon", "mm"):
        rc, bl = e[k]["rows"]["Ramp Cards"], e[k]["rows"]["Big Launch"]
        # the ramp: $9 from 300 impressions → N/A "low data (baseline)", sorted after every judged row (it was Worse, on top)
        assert rc["wi"] == 300 and _close(rc["w7"], 9.0) and rc["lowB"] is True and rc["st"] == "lagu" and rc["ob"] == "29 Sep–30 Sep"
        assert e[k]["order"][-1] == "Ramp Cards" and e[k]["order"][0] == "Big Launch"
        # the same launch at full volume (100k impressions at $9): a real drop, its own days printed under "Sep 2026"
        assert bl["wi"] == 100000 and bl["ob"] == "29 Sep–30 Sep" and _close(bl["imp"], -300.0)          # 50k/day × ($3 − $9) ÷ 1000
        card = e[k]["card"]
        assert '<small class="ec-own">29 Sep–30 Sep only</small>' in card and "N/A<small>low data (baseline)</small>" in card
        assert "(baseline) me 1,000 se kam impressions" in card and '<b>"… only"</b> kisi number ke neeche' in card
    assert e["mon"]["rows"]["Big Launch"]["st"] == "bigda" and e["mm"]["rows"]["Big Launch"]["st"] == "jaldi"   # no whole months yet
    # a row that starts inside the compared month: its own days, its impressions per day over those days
    mm = e["mm"]["rows"]["Mid Month"]
    assert mm["oc"] == "10 Oct–20 Oct" and mm["nc"] == 11 and mm["yi"] == 330000
    assert '<td title="330,000 impressions · 30,000/day (11 din)">330.0k</td>' in e["mm"]["card"]
    assert '<small class="ec-own">10 Oct–20 Oct only</small>' in e["mm"]["card"]
    assert e["b30"]["rows"]["Ramp Cards"]["ob"] == "29 Sep–20 Oct" and e["b30"]["rows"]["Ramp Cards"]["st"] == "normal"
    # the default (yesterday vs last 7 days) keeps its rows and words: no own-days tag, no baseline low data
    assert "ec-own" not in e["b7"]["card"] and "low data (baseline)" not in e["b7"]["card"] and "only" not in e["b7"]["card"]
    assert all(r.get("ob") is None for r in e["b7"]["rows"].values())


@needs_node
def test_cmp_first_of_the_month_a_whole_month_is_not_called_partial(report):
    e = report["cmp_edge"]
    m = e["first_mon"]                                         # today 1 Nov: "yesterday vs Oct 2026" = 1–31 Oct, whole
    assert m["title"] == "yesterday vs Oct 2026" and m["base"][0] == "2026-10-01" and m["base"][-1] == "2026-10-31"
    assert "(<b>1 Oct–31 Oct</b> ki kamai ÷ impressions × 1000 — poora mahina, kal samet)" in m["card"] and "adhura" not in m["card"]
    mm = e["first_mm"]
    assert mm["title"] == "Oct 2026 vs Sep 2026" and mm["dn"] == 0 and "adhura mahina hai" not in mm["card"]
    # the regular mid-month pick still says it is partial (see test_cmp_taps_navigate_within_the_history_and_stay_put)


@needs_node
def test_cmp_short_history_keeps_the_picked_chip_lit(report):
    c = report["cmp_edge"]["short"]["ctl"]                     # 5 complete days: 7 days is still the pick (never greyed out)
    assert """<button type="button" class="on" aria-pressed="true" onclick="ecCmpB('7')" title="Sirf 5 din ka data">7 days</button>""" in c
    for k in ("14", "30", "60"):
        assert f"""onclick="ecCmpB('{k}')" disabled title="Sirf 5 din ka data">{k} days</button>""" in c
    assert report["cmp_edge"]["short"]["title"] == "yesterday vs last 7 days"


NOISE_DAYS = {"2026-11-02": 1, "2026-11-03": 2, "2026-11-04": 3, "2026-11-05": 4, "2026-11-06": 5, "2026-11-09": 8, "2026-12-01": 0}


@needs_node
def test_cmp_partial_month_status_on_noise_only(report):
    """nothing changes (±8% day-to-day noise only): the first days of a month must not light up Worse / Better."""
    dash = _noise_fixture()
    r = report["cmp_noise"]
    flagged_before = {}
    for T, dn in NOISE_DAYS.items():
        _, apps = _maps(dash, T)
        comp = _comp(dash, T)
        by = _by_month(comp)
        cm, pm = comp[-1][:7], sorted(by)[-2]
        cur, base = by[cm], by[pm]
        g = r[T]
        assert g["dn"] == dn == _dn(cur, pm) and len(g["rows"]) == NOISE_APPS, T
        assert len(g["swm"]) == 13 and g["swm"][-1] == pm, T
        for name, dm in apps.items():
            _same_rows(g["rows"][name], _row_cmp(dm, comp, cur, base, pm, dn), (T, name))
        st = [x["st"] for x in g["rows"].values()]
        if dn and dn < MDAYS_MIN:
            assert set(st) == {"jaldi"}, (T, st)                   # 1–6 complete days: Too early, said in the status note
        else:
            assert st.count("bigda") + st.count("behtar") <= NOISE_APPS // 10, (T, st)
        # the old rule (whole month vs whole month swing) on the same rows: what this fix stops
        flagged_before[T] = sum(_status(g["rows"][n]["pct"], _mswing(dm, by, pm, 0), g["rows"][n]["yi"]) in ("bigda", "behtar")
                                for n, dm in apps.items())
    assert flagged_before["2026-11-02"] >= 10 and flagged_before["2026-11-03"] >= 10
    # measured like the comparison: 8 days vs a whole month swings more than whole months do (same rows, the 7-day rule aside)
    _, apps = _maps(dash, "2026-11-09")
    comp = _comp(dash, "2026-11-09")
    by = _by_month(comp)
    wider = sum(_mswing(dm, by, "2026-10", 8) > _mswing(dm, by, "2026-10", 0) for dm in apps.values())
    assert wider >= NOISE_APPS * 3 // 4


@needs_node
def test_cmp_month_status_note_says_why_a_short_month_waits(report):
    lc = report["cmp_long"]["card"]                             # Mar (1–10): judged, the swing measured on first-10-days pairs
    assert "har mahine ke <b>pehle 10 din</b> vs uska pichhla poora mahina" in lc and "poore din ke baad" not in lc
    n1 = report["cmp_noise"]["2026-11-02"]["note"]              # Nov (1): Too early, and why
    assert "<b>Nov 2026 (1)</b> me abhi sirf 1 poore din" in n1 and "isliye Status 7 poore din ke baad (tab tak Too early" in n1
    assert "poore din ke baad" not in report["cmp_noise"]["2026-11-09"]["note"]


@needs_node
def test_cmp_countries_checked_day_by_day(report, dash):
    h = report["cmp_holes"]
    comp = _comp(dash)
    assert h["febDef"]["ct"]["c"] == "yesterday vs last 7 days" and "ec-cw" not in h["febDef"]["countries"]
    # a failed chunk (1–20 Feb) inside the pick: the last covered view, the missing days said
    for k, want in (("febMon", "yesterday vs Feb 2026"), ("febMm", "Mar 2026 (1–10) vs Feb 2026")):
        x = h[k]
        assert x["ct"] == {"u": want, "c": "yesterday vs last 7 days"}, k
        assert (f"⚠ Country report me <b>1 Feb–20 Feb</b> ka data nahi hai — <b>{want}</b> ke liye poora nahi, isliye yeh table "
                "abhi bhi <b>yesterday vs last 7 days</b> dikha rahi hai.") in x["countries"], k
    assert h["feb14"]["ct"]["c"] == "yesterday vs last 14 days" and "ec-cw" not in h["feb14"]["countries"]   # 25 Feb on: covered
    # a hole (3–5 Mar) that every view reads: the pick stays, the missing days said; the default says it too
    assert h["mar14"]["ct"]["c"] == "yesterday vs last 14 days"
    assert "⚠ Country report me <b>3 Mar–5 Mar</b> ka data nahi hai — un din ke desh-wise number is table me nahi hain" in h["mar14"]["countries"]
    assert "⚠ Country report me <b>4 Mar–5 Mar</b> ka data nahi hai" in h["marDef"]["countries"]
    holed = {cn: {r[0]: [r[1], r[2]] for r in rows if r[0] != TODAY and not "2026-03-03" <= r[0] <= "2026-03-05"}
             for cn, rows in dash["countries_daily"]["Demo Gallery"].items()}
    for r in h["mar14"]["c"]:
        assert _close(r["w7"], _sum(holed[r["key"]], comp[-14:])["ec"]), r            # what is there, never padded
    # a young app whose country report starts with the app: covered (no app data before 6 Mar), no fallback
    assert h["young14"]["ct"]["c"] == "yesterday vs last 14 days" and "ec-cw" not in h["young14"]["countries"]
    assert h["ranges"] == ["1 Feb–3 Feb", "28 Feb–1 Mar, 5 Mar", "1 Jan, 3 Jan, 5 Jan, 7 Jan +2 more", ""]


# ── 🔀 Month vs month's two pickers (owner, 21 Oct: "month vs month me sept vs aug nahi — oct vs sept, oct vs aug, ese oct
# vs month wise"): October stays, the compared month moves ─────────────────────────────────────────────────────────────────
OCT_PICKS = {"sep": ("2026-09", 1), "aug": ("2026-08", 2), "jul": ("2026-07", 3)}
OCT_ST = {  # the statuses the SYNTHETIC October fixtures were built for (each also recounted row by row)
    "octs": {"sep": {"Steady Cam": "bigda", "Two Step": "normal", "Calm Notes": "normal", "Late Start": "jaldi", "Quiet Clock": "lagu"},
             "aug": {"Steady Cam": "bigda", "Two Step": "bigda", "Calm Notes": "normal", "Late Start": "jaldi", "Quiet Clock": "lagu"},
             "jul": {"Steady Cam": "bigda", "Two Step": "normal", "Calm Notes": "normal", "Late Start": "jaldi", "Quiet Clock": "lagu"}},
}


@needs_node
@pytest.mark.parametrize("fx", ["octs", "ramp"])
def test_cmp_oct_vs_sep_aug_jul_recounted(report, fx):
    dash = {"octs": _octs_fixture, "ramp": _ramp_fixture}[fx]()
    _, apps = _maps(dash)
    comp = _comp(dash)
    by = _by_month(comp)
    r = report["cmp_pickers"][fx]
    oct_ = by["2026-10"]
    assert oct_ == _days(date(2026, 10, 1), date(2026, 10, 20))                  # complete days only: 1 … yesterday (20 Oct)
    for k, (pm, gap) in OCT_PICKS.items():
        g, lbl = r[k], MON[int(pm[5:7]) - 1] + " " + pm[:4]
        assert (g["cm"], g["pm"], g["g"], g["dn"]) == ("2026-10", pm, gap, 20), (fx, k)
        assert g["cur"] == oct_ and g["base"] == by[pm], (fx, k)
        assert (g["title"], g["colCur"], g["colBase"], g["colImp"]) == (f"Oct 2026 (1–20) vs {lbl}", "Oct 2026 (1–20)<br>eCPM",
                                                                        f"{lbl}<br>eCPM", "Oct 2026 (1–20)<br>impr"), (fx, k)
        assert f"<h3>All apps · Oct 2026 (1–20) vs {lbl}</h3>" in g["card"] and f"<b>1 Oct–20 Oct</b> vs <b>{_span(by[pm])}</b>" in g["card"]
        assert "(impressions ÷ 20 din)" in g["card"]
        # the swing's months: the whole months up to the compared one, 12 pairs `gap` apart at most
        assert g["swm"] == [m for m in sorted(by) if m <= pm and _full(m, by[m])][-(12 + gap):], (fx, k)
        for name, dm in apps.items():
            exp = _row_cmp(dm, comp, oct_, by[pm], pm, 20)
            _same_rows(g["rows"][name], exp, (fx, k, name))
            if exp["chg"] is not None:   # impact/day = October's impressions per complete day × the eCPM change ÷ 1000
                assert _close(g["rows"][name]["imp"], exp["yi"] / exp["nc"] * exp["chg"] / 1000), (fx, k, name)
        _sorted_ok(g["order"], [dict(v, key=n, label=n) for n, v in g["rows"].items() if v["act"]], "imp", "asc")
        # the current month never moved: only the compared month is stored ('' = the month just before October)
        assert g["cmp"]["cm"] == "" and g["cmp"]["vm"] == ("" if k == "sep" else pm) and json.loads(g["ls"]) == g["cmp"], (fx, k)
        assert '<span class="ec-ml" aria-live="polite"><b>Oct 2026 (1–20)</b></span>' in g["ctl"]
        assert f'<span class="ec-ml" aria-live="polite">{lbl}</span>' in g["ctl"]
        if fx in OCT_ST:
            assert {n: v["st"] for n, v in g["rows"].items()} == OCT_ST[fx][k], (fx, k)
        # the status note says which gap the swing was measured over
        if gap == 1:
            assert "<b>mahine-dar-mahine ke normal utaar-chadhaav</b>" in g["note"] and "max 13" in g["note"]
            assert "har mahine ke <b>pehle 20 din</b> vs uska pichhla poora mahina" in g["note"] and "abhi 8 poore mahine ka data nahi" in g["note"]
        else:
            assert f"<b>{gap} mahine ke farq par normal utaar-chadhaav</b>" in g["note"] and f"max {12 + gap}" in g["note"]
            assert f"har mahine ke <b>pehle 20 din</b> vs usse <b>{gap} mahine pehle</b> ka poora mahina, bilkul Oct 2026 (1–20) vs {lbl} ki tarah" in g["note"]
            assert f"abhi {7 + gap} poore mahine ka data nahi" in g["note"]
    # the compared month's ‹ to the oldest month of the history (its ‹ greys out), › back to the default pair
    first = MON[int(comp[0][5:7]) - 1] + " " + comp[0][:4]
    assert r["oldest"]["title"] == f"Oct 2026 (1–20) vs {first}" and r["oldest"]["pm"] == comp[0][:7]
    assert 'aria-label="Compared month: previous" disabled>' in r["oldest"]["ctl"] and 'aria-label="Current month: next" disabled>' in r["oldest"]["ctl"]
    assert r["back"]["title"] == "Oct 2026 (1–20) vs Sep 2026" and (r["back"]["cmp"]["cm"], r["back"]["cmp"]["vm"]) == ("", "")


@needs_node
def test_cmp_two_months_apart_status_uses_the_same_gap(report):
    """Oct vs Aug is judged on how much a month usually differs from the one 2 before it — not from the next one."""
    dash = _octs_fixture()
    _, apps = _maps(dash)
    comp = _comp(dash)
    by = _by_month(comp)
    aug = report["cmp_pickers"]["octs"]["aug"]["rows"]
    ts = aug["Two Step"]   # ±10% month to month, every other month alike; October = August × 0.9
    assert _close(ts["pct"], -0.1) and ts["swing"] == 0 and ts["st"] == "bigda"            # 2 apart: no usual swing → −10% = Worse
    one = _mswing(apps["Two Step"], by, "2026-08", 20, 1)                                  # the adjacent months' swing: ~20%
    assert one > 0.18 and _status(ts["pct"], one, ts["yi"]) == "normal"                    # would have hidden the drop
    sc = aug["Steady Cam"]
    assert _close(sc["w7"], 2.0 * 1.03) and _close(sc["y"], 2.0 * 0.97 * 0.8) and sc["st"] == "bigda"
    # the ramp fixture (history from 1 Jan 2026): 8 adjacent pairs → judged; 6 pairs 2 apart, 4 pairs 3 apart → Too early
    rp = report["cmp_pickers"]["ramp"]
    assert rp["sep"]["rows"]["Steady Mail"]["swing"] is not None and rp["sep"]["rows"]["Steady Mail"]["st"] == "normal"
    for k in ("aug", "jul"):
        sm = rp[k]["rows"]["Steady Mail"]
        assert sm["swing"] is None and sm["st"] == "jaldi" and sm["chg"] is not None, k   # the change is real, the status waits
    assert "Too early</b> = abhi 9 poore mahine ka data nahi" in rp["aug"]["note"] and "abhi 10 poore mahine" in rp["jul"]["note"]


# the default view, byte for byte: the page before the picker and this one (comparison row taken out), $ and ₹, every sort
def _snap(tmp, page, dash, mode="snap"):
    js = max(re.findall(r"<script>(.*?)</script>", page, re.S), key=len)
    sp, fx = os.path.join(tmp, "p.js"), os.path.join(tmp, "f.json")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(js)
    with open(fx, "w", encoding="utf-8") as f:
        json.dump({"dashboard": dash}, f)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "ecpm_frontend.js"), sp, fx, mode], check=True, capture_output=True, text=True, timeout=180)
    rep = json.loads(out.stdout)
    assert rep["errors"] == [], rep["errors"]
    return rep[mode]


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


PREV_REV = "a9f7cdc"          # the page before Month vs month's two pickers: every "Yesterday vs" view must come out byte-identical


@needs_node
def test_cmp_yesterday_mode_is_byte_identical_to_before_the_two_pickers(tmp_path, dash):
    try:
        old = subprocess.run(["git", "-C", ROOT, "show", PREV_REV + ":frontend/index.html"], check=True, capture_output=True,
                             text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip("the page before the two pickers is not in this checkout's history")
    (tmp_path / "old").mkdir()
    (tmp_path / "new").mkdir()
    a = _snap(str(tmp_path / "old"), old, dash, "ysnap")
    b = _snap(str(tmp_path / "new"), _page(), dash, "ysnap")
    assert len(a["S"]) > 150 and a["S"].keys() == b["S"].keys()
    for k in a["S"]:
        assert a["S"][k] == b["S"][k], k
    # it saw the real thing: every pick's card with its control row, the Month ‹ › to the first month, Ad units + Countries
    S = b["S"]
    assert 'aria-label="Previous month" disabled>' in S["tap_USD_3_ecCmpMon(-1)"] and "All apps · yesterday vs Dec 2025 (20–31)" in S["tap_INR_3_ecCmpMon(-1)"]
    assert "All apps · yesterday vs Mar 2026 (1–10)" in S["tap_USD_7_ecCmpMon(1)"] and "All apps · yesterday vs last 30 days" in S["tap_USD_8_ecCmpB('30')"]
    assert "Countries · yesterday vs last 60 days" in S["tapu_USD_3_ecCmpB('60')"] and '<div class="ec-cmp">' in S['all_USD{"b":"14"}']
    assert "ecCmpCur(" not in "".join(v for v in S.values() if isinstance(v, str))


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
    assert re.search(r"\.ec-mvs\{display:inline-flex;[^}]*flex:none", css)                               # "vs ‹ month ›" wraps as one piece
