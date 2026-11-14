"""📐 Breakeven — the build step (admob_iq.be_build) on made-up apps whose truth is known: every country's revenue curve
is a closed form, cumulative ROAS(age) = κ · eCPM ÷ CPI · (1 + age)^½ · noise, so log(BE + 1) = −2 log κ + 2 log CPI −
2 log eCPM (± the noise) and log ROAS(age) is linear in log CPI and log eCPM; noise from xorshift32. The rows are built
in roi_build's row shape, the first-session store in fetch.ga4_nvr's. Covered: the judged rule, the censored regression
and the bot, the ROAS curve (monotone, stops at its limit), the owner's rule (the countries' curves summed by spend,
never an average of BE days — his worked example), the calibration maps, the files and the pointer in the shapes the
page reads (skill, the card's index, the "…" rest, provisional days, null + limit), one _headers splat rule, the
counts-only line, the daily caches, failure isolation (the health banner's line), the switch and the build_static
wiring. No real data: apps "app~synth-…", countries AA … DH, the calendar 2030–2031.

  app a  540 install days; AA / BB / CC spend 200 / 100 / 60 USD a day with first-session reads (covered); EE 15
         USD a day, no first-session read (uncovered, named); DA … DH 1 USD a day each (uncovered, under 0.5 %: one
         "…" rest); "--" and "XX" (no country: never a row)
  app b  60 install days, only EE: no country covered (no app answer)   ·   app c  spend under 5 USD every day: its file
  holds only its real numbers (no model: "jd" 0)
"""
import copy
import gzip
import hashlib
import json
import math
import os
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq import be_build as be
from admob_iq import build_static as bs
from admob_iq import health
from admob_iq.config import settings
from admob_iq.deploy_guard import HEADERS_MAX_RULES, headers_cover, headers_rule_count
from admob_iq.fetch import ga4_uninstall as gu

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY0, NDAYS = date(2030, 1, 1), 540
TODAY = DAY0 + timedelta(days=NDAYS - 1)
NOW = datetime(TODAY.year, TODAY.month, TODAY.day, 8, 0, tzinfo=timezone.utc)
APPS = {"a": "app~synth-a", "b": "app~synth-b", "c": "app~synth-c"}
KEYS = {k: gu.file_key(v) for k, v in APPS.items()}
G = 0.5                                                   # ROAS grows as (1 + age)^G
CTY = {"AA": (200.0, 0.50, 5.0, 0.014), "BB": (100.0, 0.30, 2.0, 0.020), "CC": (60.0, 0.80, 6.0, 0.012)}
TINY = ["D" + ch for ch in "ABCDEFGH"]


def prng(seed):
    x = seed & 0xFFFFFFFF or 1
    while True:
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        yield (x / 0xFFFFFFFF) * 2.0 - 1.0


def roi_row(xs, n, na, sp, d, m):
    """roi_build's row: [X, n, n_ads, spend, d, df, u, t, s, sd, be, st, q, spi] (+ [m, mf] once past day 60)."""
    row = [xs, n, na, sp, d, len(d), [], [], d[-1] if d else None, xs, None, "N/A", 0, round(sp * 80, 2)]
    return row + [m, len(m)] if m else row


def _country_days(g, sp0, cpi0, ecpm0, kap, ndays, today):
    """One country's install days → [(day, n, na, sp, ecpm, d, m)] observed up to each day's age."""
    out = []
    for i in range(ndays):
        x = today - timedelta(days=ndays - 1 - i)
        age = (today - x).days
        sp = sp0 * (1 + 0.1 * next(g))
        cpi, ecpm = cpi0 * math.exp(0.4 * next(g)), ecpm0 * math.exp(0.4 * next(g))
        r0 = kap * ecpm / cpi * math.exp(0.15 * next(g))
        na = round(sp / cpi, 2)
        d = [round(sp * r0 * (1.0 + a) ** G, 6) for a in range(min(age, 30) + 1)]
        m = [round(sp * r0 * (1.0 + a) ** G, 6) for a in range(60, age + 1, 30)]
        out.append((x.isoformat(), int(na * 1.3) + 1, na, round(sp, 6), ecpm, d, m))
    return out


def write_app(site, data, key, countries, ndays, today, seed, nvr=("AA", "BB", "CC")):
    """countries {cc: (spend, CPI, eCPM, κ)} → roi_<key>.json.gz (the All rows), one country pack, the first-session
    store (only the countries in nvr have a read)."""
    g = prng(seed)
    pack, store, allr = {}, {}, {}
    for cc, prm in countries.items():
        for xs, n, na, sp, ecpm, d, m in _country_days(g, *prm, ndays, today):
            pack.setdefault(cc, []).append(roi_row(xs, n, na, sp, d, m))
            if cc in nvr:
                imp = n * 10
                store.setdefault(xs, {"c": [], "u": [], "s": []})["c"] += [["n", cc, round(ecpm * imp / 1000, 6), imp],
                                                                         ["r", cc, 1.0, 400]]
            a = allr.setdefault(xs, [0, 0.0, 0.0, [0.0] * len(d), [0.0] * len(m)])
            a[0] += n
            a[1] += na
            a[2] += sp
            a[3] = [p + q for p, q in zip(a[3], d)]
            a[4] = [p + q for p, q in zip(a[4], m)]
    rows = [roi_row(xs, a[0], round(a[1], 2), round(a[2], 6), [round(v, 6) for v in a[3]], [round(v, 6) for v in a[4]])
            for xs, a in sorted(allr.items())]
    pf = "roi_%s_c00.json.gz" % key
    with gzip.open(os.path.join(site, pf), "wt", encoding="utf-8") as f:
        json.dump({"v": 1, "b": "x", "key": key, "c": pack}, f)
    with gzip.open(os.path.join(site, "roi_%s.json.gz" % key), "wt", encoding="utf-8") as f:
        json.dump({"v": 1, "key": key, "newest": today.isoformat(), "rows": rows, "cd": {"packs": [[pf, "x"]]}}, f)
    os.makedirs(os.path.join(data, "ga4_nvr"), exist_ok=True)
    with gzip.open(os.path.join(data, "ga4_nvr", key + ".json.gz"), "wt", encoding="utf-8") as f:
        json.dump({"v": 2, "days": store}, f)


def make(tmp, today=TODAY):
    site, data = str(tmp / "site"), str(tmp / "data")
    os.makedirs(site, exist_ok=True)
    os.makedirs(data, exist_ok=True)
    big = dict(CTY, EE=(15.0, 0.5, 4.0, 0.01), **{cc: (1.0, 0.5, 4.0, 0.01) for cc in TINY})
    big["--"] = big["XX"] = (3.0, 0.5, 4.0, 0.01)
    write_app(site, data, KEYS["a"], big, NDAYS, today, 7)
    write_app(site, data, KEYS["b"], {"EE": (40.0, 0.5, 4.0, 0.01)}, 60, today, 11)
    write_app(site, data, KEYS["c"], {"AA": (2.0, 0.5, 4.0, 0.01)}, 60, today, 13)
    dash = {"roi": {"file": "roi.json.gz", "apps": {APPS[k]: {"file": "roi_%s.json.gz" % KEYS[k], "st": "Normal"}
                                                    for k in "abc"}}}
    return site, data, dash


def body_of(site, k):
    with gzip.open(os.path.join(site, "be_%s.json.gz" % KEYS[k]), "rt", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("be")
    site, data, dash = make(tmp)
    paths = be.run(dash, data, site, {}, NOW)
    return {"site": site, "data": data, "dash": dash, "paths": paths, "line": be.pop_line(), "tmp": tmp}


def R(**kw):
    """A hand-made row (the models' view of one install day)."""
    x = be._R()
    for k in be._R.__slots__:
        setattr(x, k, None)
    x.n, x.jd = 100, True
    for k, v in kw.items():
        setattr(x, k, v)
    if "sfa" not in kw:                    # as _row: the latest so-far read = the last observed point (no s / sd here)
        x.sfa, x.sfv = x.obs, x.oc
    if "rbe" not in kw and x.hi is not None:
        x.rbe = (int(round(x.be if x.be is not None else x.hi)), "x")
    if "fin" not in kw and x.cum is not None and x.obs is not None:   # every lived cell final unless a test says not
        x.fin = [v if a <= x.obs else None for a, v in zip(be.GRID, x.cum)]
    if x.day and x.X is None:
        x.X = date.fromisoformat(x.day).toordinal()
    return x


# ── the rows and the models ─────────────────────────────────────────────────────────────────────────────────────────

def test_the_judged_rule_is_5_usd_and_30_new_users():
    def jd(sp, n):
        return be._row(roi_row("2030-05-01", n, 10.0, sp, [1.0, 2.0], []), 3.0, True).jd
    assert jd(5.0, 30) and jd(120.0, 400)
    assert not jd(4.99, 30) and not jd(5.0, 29) and not jd(5.0, None) and not jd(0.5, 1000)


def test_a_row_reads_its_cells_columns_and_breakeven_day():
    d = [10.0 * (a + 1) for a in range(31)]                  # spend 100: back on day 9 exactly (cell 9 = 100)
    x = be._row(roi_row("2030-05-01", 50, 20.0, 100.0, d, [400.0]), 4.0, True)
    assert (x.lo, x.hi, x.be, x.obs, x.oc) == (8, 9, 9.0, 60, 400.0)
    assert x.cum[:7] == [10.0, 20.0, 30.0, 40.0, 70.0, 140.0, 310.0] and x.cum[7] == 400.0 and x.cum[8] is None
    assert x.cpi == 5.0 and x.c == pytest.approx(math.log(5.0)) and x.e == pytest.approx(math.log(4.0))
    y = be._row(roi_row("2030-05-01", 50, 20.0, 350.0, d, [500.0]), None, False)   # past day 30: inside (30, 60]
    assert (y.lo, y.hi) == (30, 60) and y.be == pytest.approx(30 + 30 * (350 - 310) / (500 - 310), abs=0.01)
    assert y.e is None and y.cum is None and not be._usable(y)


def test_no_look_ahead_at_an_origin():
    O = date(2030, 6, 1).toordinal()
    seen = R(day="2030-04-01", hi=20, be=19.5, obs=60)            # BE visible by O (+ the final lag)
    late = R(day="2030-05-01", hi=40, be=39.5, obs=60)            # BE on day 40, only 28 days visible: BE > 28
    later = R(day="2030-04-20", hi=50, be=49.5, obs=60)           # 39 days visible: BE > 30 (the 30-day grid)
    young = R(day="2030-05-10", hi=5, be=5.0, obs=20)             # inside the 30 settle days: not used at all
    assert be.at_origin(seen, O) == ("e", 19.5)
    assert be.at_origin(late, O) == ("c", 28.0) and O - late.X - be.LAG == 28
    assert be.at_origin(later, O) == ("c", 30.0)
    assert be.at_origin(young, O) is None


def test_the_censored_regression_recovers_known_coefficients():
    g = prng(5)
    X, y, cz = [], [], []
    for _ in range(3000):
        x1, x2 = 2.0 * next(g), 2.0 * next(g)
        u1, u2 = (next(g) + 1.0) / 2.0 or 1e-9, (next(g) + 1.0) / 2.0
        eps = math.sqrt(-2.0 * math.log(max(u1, 1e-12))) * math.cos(2.0 * math.pi * u2)      # Box–Muller
        v = 1.0 + 0.8 * x1 - 0.5 * x2 + 0.3 * eps
        cap = 1.2                                                  # watched only so far: a lower bound past it
        X.append([1.0, x1, x2])
        y.append(min(v, cap))
        cz.append(v > cap)
    assert 0.3 < sum(cz) / len(cz) < 0.6
    beta, s = be.cens_reg(X, y, cz)
    assert beta == pytest.approx([1.0, 0.8, -0.5], abs=0.04) and s == pytest.approx(0.3, abs=0.03)
    naive = be.huber(X, y)                                         # the censored days taken as real: biased
    assert abs(naive[1] - 0.8) > 0.15


def test_the_bot_drops_the_planted_outliers_only():
    g = prng(9)
    ev = []
    for i in range(60):
        c, e = 0.5 * next(g), 0.5 * next(g)
        ly = 3.0 + 1.5 * c - 1.2 * e + 0.05 * next(g)
        ev.append(R(day="2030-01-01", c=c, e=e, be=math.exp(ly) - 1.0))
    planted = [ev[7], ev[23], ev[41]]
    for r in planted:
        r.be = (r.be + 1.0) * math.exp(1.5) - 1.0               # ≫ 3 robust spreads off what CPI / eCPM say
    ev[50].be = (ev[50].be + 1.0) * math.exp(0.05) - 1.0         # a little off: kept
    kept, dropped = be.bot(ev)
    assert dropped == planted and len(kept) == 57 and ev[50] in kept
    kept2, dropped2 = be.bot([r for r in ev if r not in planted])
    assert dropped2 == []


def test_the_roas_curve_is_monotone_in_age_and_stops_at_its_limit():
    O = date(2031, 1, 1).toordinal()
    g = prng(3)
    rows = []
    for i in range(60):                                          # 60 days 31 … 90 days old: ages to 60 reached by
        x = O - 31 - i                                           # all, 90 by those ≥ 93 days old (< 20): limit 60
        c, e = 0.3 * next(g), 0.3 * next(g)
        cum = [math.exp(-2.0 - c + e + 0.25 * math.log(1 + a) + 0.05 * next(g)) * 100.0 for a in be.GRID]
        cum[4] = cum[3] * 0.95                                   # a dip at day 7 (the fit must not show it)
        age = O - x
        rows.append(R(day=date.fromordinal(x).isoformat(), sp=100.0, c=c, e=e,
                      cum=[v if a + be.LAG <= age else None for a, v in zip(be.GRID, cum)]))
    rows.sort(key=lambda r: r.X)
    cf = be.curve_fit(rows, O)
    assert [be.GRID[j] for j, *_ in cf] == [0, 1, 2, 3, 6, 13, 30, 60]
    assert all(n >= be.MIN_KEPT for _, _, _, _, n, _ in cf)
    for c, e in ((0.0, 0.0), (0.3, -0.3), (-0.3, 0.3)):
        ages, mid, lo, hi = be.curve_predict(cf, c, e)
        for v in (mid, lo, hi):
            assert all(b >= a for a, b in zip(v, v[1:]))
        assert all(l <= m <= h for l, m, h in zip(lo, mid, hi))
    b = cf[6][1]                                                 # day 31's fit: log ROAS = −2 − c + e + 0.25 log 31
    assert b == pytest.approx([-2.0 + 0.25 * math.log(31), -1.0, 1.0], abs=0.05)


WIDE = [-50.0, 50.0, -50.0, 50.0]                               # a learned range every test input is inside


def test_the_owners_rule_sums_the_countries_curves_never_averages_their_be_days():
    """His worked example: two countries, 50 / 50 spend; A breaks even on day 30 and is at 200 % by day 90, B is at 40 %
    by day 90 and breaks even on day 300. The average of the BE days says 165; the app's spend really comes back
    between day 30 and day 90 (day 70 here)."""
    ra = [0.10, 0.20, 0.28, 0.35, 0.50, 0.70, 1.00, 1.50, 2.00]                      # GRID ages 0 … 90 (its limit)
    rb = [0.02, 0.04, 0.05, 0.06, 0.08, 0.12, 0.20, 0.30, 0.40, 0.50, 0.70, 0.90, 1.20]   # 0 … 360
    A = (100.0, list(be.GRID[:9]), [math.log(v) for v in ra])
    B = (100.0, list(be.GRID), [math.log(v) for v in rb])
    be_a, be_b = be.crossing(A[1], ra), be.crossing(B[1], rb)
    assert (be_a, be_b) == (30.0, pytest.approx(300.0)) and (be_a + be_b) / 2 == pytest.approx(165.0)
    ages, roas = be.combine([A, B])
    assert ages == list(be.GRID) and roas[6] == pytest.approx(0.6) and roas[8] == pytest.approx(1.2)
    assert roas[9] == pytest.approx(0.5 * 2.0 + 0.5 * 0.5)       # A carried at its last value past its limit
    app_be = be.crossing(ages, roas)
    assert 30 < app_be < 90 and app_be == pytest.approx(70.0)
    # … and through predict(): the app line says day 70; the countries' own K3 days, B's past its watched limit
    def flat(curve):                                             # a curve that is the same whatever CPI / eCPM
        return [[j, [math.log(v), 0.0, 0.0], -0.2, 0.2, 40, math.log(v)] for j, v in enumerate(curve)]
    fc = {"origin": "2031-01-01", "app_med": [], "fits": {
        "AA": {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": flat(ra), "rng": WIDE},
        "BB": {"k3": [math.log(301.0), 0.0, 0.0, 0.5, 270, 30, 0, 10], "cv": flat(rb), "rng": WIDE}}}
    cal = {"built": "2031-01-01", "cty": {str(H): [[0.0, 0.0], [1.0, 1.0]] for H in be.HS},
           "pit": {"0.1": 0.1, "0.5": 0.5, "0.9": 0.9}, "band": {}}
    day = "2030-12-30"
    app_row = R(day=day, sp=200.0, na=100.0, obs=0, oc=1.0)
    cs = {cc: R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0)) for cc in ("AA", "BB")}
    out = be.predict("k", fc, cal, ("2030-12-31", [app_row], {day: cs}))["days"][0]
    assert out["app"]["be"][0] == 70 and out["app"]["lim"] == 360 and out["cov"] == 1.0 and out["unc"] == []
    r = out["app"]["roas"]                                       # the page's ROAS at 30 / 90 / 180: the same curve
    assert "p" not in out["app"] and [r[be.GRID.index(H)] for H in be.HS] == [pytest.approx(v) for v in (0.6, 1.2, 1.35)]
    a_row, b_row = sorted(out["cty"])
    lo_k = math.exp(0.5 * be.ninv(0.1))                          # the 10 % level's factor at σ = 0.5
    # each country's day is ITS OWN curve's (the one the app line adds up): A crosses 100 % on day 30 (its curve to 90),
    # B on day 300 (to 360) — the app's day 70 lies between them, never before both
    assert a_row[7] == 30 and a_row[8] <= 30 <= a_row[9] and a_row[10:] == [90, 0]
    assert b_row[7] == 300 and b_row[8] <= 300 and a_row[7] < out["app"]["be"][0] < b_row[7] and b_row[10:] == [360, 0]
    assert out["app"]["lo"] == [None] * 13 and out["app"]["be"][1:] == [None, None]   # no band yet: no range (never the line)


def test_the_calibration_maps_are_monotone(built):
    with open(os.path.join(built["data"], "be_tab", "calib.json"), encoding="utf-8") as f:
        cal = json.load(f)
    assert "app" not in cal                                      # (the app's line is its curve alone)
    for part in ("cty",):
        for H in ("30", "90", "180"):
            m = cal[part][H]
            assert len(m) >= 2 and m[-1][0] > m[0][0]
            assert all(b[0] >= a[0] for a, b in zip(m, m[1:]))      # (equal scores may sit in two blocks)
            assert all(b[1] >= a[1] for a, b in zip(m, m[1:])) and 0.0 <= m[0][1] <= m[-1][1] <= 1.0
    p = cal["pit"]
    assert 0 < p["0.1"] < p["0.5"] < p["0.9"] < 1
    assert cal["band"] and all(q10 <= med <= q90 and n >= be.MIN_BAND for med, q10, q90, n in cal["band"].values())
    assert set(cal["band"]) <= {str(a) for a in be.GRID}
    raw = be.calibrate([{"key": "k", "X": 1, "O": 1, "age": 400, "hi": h, "be": h, "obs": 360,
                         "a": {"ages": list(be.GRID), "roas": [r] * 13, "full": [1.0] * 13}, "tc": [0.0] * 13}
                        for h, r in ((20, 1.5), (100, 0.4), (None, 0.2), (25, 0.9), (200, 1.1))], [(math.log(r + 1.0), 0.5, h, h, 360, 400)
                                          for h, r in ((20, 5), (200, 8), (25, 10), (100, 60), (None, 300))], 1)
    m = raw["cty"]["30"]                                         # K3 r = 8 says sooner than r = 10, yet only 10 did
    assert all(b[1] >= a[1] for a, b in zip(m, m[1:]))          # PAVA pools the out-of-order pair


# ── the step: files, pointer, line ─────────────────────────────────────────────────────────────────────────────────

def test_run_writes_one_file_per_app_with_days_and_the_pointer(built):
    site, dash = built["site"], built["dash"]
    assert built["paths"] == ["/be_*"]
    names = sorted(f for f in os.listdir(site) if f.startswith("be_"))
    assert names == sorted("be_%s.json.gz" % KEYS[k] for k in "abc")         # app c: no judged day — its real numbers only
    ptr = dash["be"]
    assert ptr["v"] == 1 and ptr["origin"] == TODAY.isoformat() and ptr["calib"] == TODAY.isoformat()
    assert set(ptr["apps"]) == {APPS["a"], APPS["b"], APPS["c"]}
    for k in "ab":
        p = ptr["apps"][APPS[k]]
        raw = gzip.decompress(open(os.path.join(site, p["file"]), "rb").read())
        b = json.loads(raw)
        assert p == {"key": KEYS[k], "file": "be_%s.json.gz" % KEYS[k], "v": hashlib.sha1(raw).hexdigest()[:12],
                     "n": len(b["days"]), "cov": b["days"][-1]["cov"]}


def test_the_shapes_the_page_reads(built):
    b = body_of(built["site"], "a")
    assert set(b) == {"v", "key", "origin", "grid", "calib", "skill", "days"}
    assert b["grid"] == list(be.GRID) and b["origin"] == b["calib"] == TODAY.isoformat()
    days = b["days"]
    assert len(days) > 14 and [d["d"] for d in days] == sorted(d["d"] for d in days)  # every judged day, oldest first
    assert [d["age"] for d in days[-14:]] == list(range(13, -1, -1))                    # … the newest at age 0
    sk = b["skill"]
    assert set(sk) == {"auc", "c", "n"} and len(sk["auc"]) == 3 and sk["n"] > 100
    assert any(v is not None for v in sk["auc"]) and 0 <= sk["c"] <= 100
    for d in days:
        assert set(d) == {"d", "age", "sp", "inst", "cov", "real", "app", "unc", "cty", "card", "now"}
        a = d["app"]
        assert set(a) == {"be", "lim", "roas", "lo", "hi"} and a["lim"] in be.GRID
        assert len(a["roas"]) == len(a["lo"]) == len(a["hi"]) == be.GRID.index(a["lim"]) + 1
        assert all(v is None or isinstance(v, int) for v in a["be"])
        assert a["roas"] == sorted(a["roas"])                    # the app curve never goes down with age
        ccs = [x[0] for x in d["cty"]]
        assert sorted(ccs) == ["AA", "BB", "CC"] and all(len(x) == 12 and isinstance(x[10], int) and x[11] in range(7) for x in d["cty"])
        assert [x[1] for x in d["cty"]] == sorted((x[1] for x in d["cty"]), reverse=True)
        named = [x for x in d["unc"] if x[0] != "…"]
        rest = [x for x in d["unc"] if x[0] == "…"]
        assert [x[0] for x in named] == ["EE"] and len(rest) == 1 and d["unc"][-1] == rest[0]
        assert rest[0][1] == pytest.approx(8.0 / 384.0, abs=0.004)          # DA … DH: 8 × 1 USD of ≈ 384 USD
        assert sum(x[1] for x in d["cty"]) + sum(x[1] for x in d["unc"]) == pytest.approx(1.0, abs=0.002)
        assert d["cov"] == pytest.approx(sum(x[1] for x in d["cty"]), abs=0.002)
        c = d["card"]
        assert set(c) == {"roas", "bench"} and all(len(v) == 6 for v in c.values())     # (no revenue index: owner)
        seen = [i for i, j in enumerate(be.CARD_J) if be.GRID[j] <= d["age"]]
        assert [i for i, v in enumerate(c["roas"]) if v is not None] == seen   # (null where not observed yet)
        assert all(v is not None for v in c["bench"])
    new = days[-1]
    prov = [d for d in days if d["age"] < be.PROV]                 # provisional: answered and shown, not final
    assert [d["age"] for d in prov] == [3, 2, 1, 0] and all("app" in d for d in prov)
    assert new["now"] == ["no", 0, new["card"]["roas"][0], 0] and new["card"]["roas"][1:] == [None] * 5   # (not final)
    b2 = body_of(built["site"], "b")
    assert all("app" not in d and d["cov"] == 0.0 and d["cty"] == [] and d["unc"] == [["EE", 1.0]] for d in b2["days"])
    assert b2["skill"] == {"auc": [None, None, None], "c": None, "n": 0}


def test_the_fits_recover_the_synthetic_benchmark(built):
    with gzip.open(os.path.join(built["data"], "be_tab", "fits_%s.json.gz" % KEYS["a"]), "rt") as f:
        fc = json.load(f)
    assert fc["v"] == 1 and fc["origin"] == TODAY.isoformat() and sorted(fc["fits"]) == ["AA", "BB", "CC"]
    for cc, (sp, cpi, ecpm, kap) in CTY.items():
        a, b, c, s, tmax, kept, dropped, cens = fc["fits"][cc]["k3"]
        assert b == pytest.approx(1 / G, abs=0.15) and c == pytest.approx(-1 / G, abs=0.15)   # log(BE + 1) slopes
        assert a == pytest.approx(-math.log(kap) / G, abs=0.4) and kept >= be.MIN_KEPT and cens > 0
        assert [be.GRID[j] for j, *_ in fc["fits"][cc]["cv"]] == list(be.GRID)
    assert [j for j, *_ in fc["app_med"]] == list(range(13)) and "app_idx" not in fc


def test_headers_one_splat_rule_covers_the_files(built):
    base = bs.headers_text(["uninstall.json.gz"], built["dash"])
    text = bs.headers_text(["uninstall.json.gz"], built["dash"], extra=built["paths"])
    assert headers_rule_count(text) == headers_rule_count(base) + 1 <= HEADERS_MAX_RULES
    assert headers_cover(text, "be_%s.json.gz" % KEYS["a"]) and not headers_cover(base, "be_%s.json.gz" % KEYS["a"])
    assert "/be_*\n  Cache-Control: no-store" in text


def test_the_log_line_names_nothing(built):
    line = built["line"]
    assert re.fullmatch(r"be: apps \d+, days \d+, covered \d+, uncovered \d+, refit (yes|no), calib (yes|no)",
                        line), line
    assert line == "be: apps 3, days 660, covered 3, uncovered 11, refit yes, calib yes"   # every day with spend
    for bad in list(APPS.values()) + list(KEYS.values()) + ["2030", "2031", "$", "AA", "EE"]:
        assert bad not in line


# ── the daily caches ────────────────────────────────────────────────────────────────────────────────────────────────

def _spy(monkeypatch, name, calls):
    f = getattr(be, name)

    def w(*a, **k):
        calls[name] = calls.get(name, 0) + 1
        return f(*a, **k)
    monkeypatch.setattr(be, name, w)


def _snap(site, data):
    out = {f: open(os.path.join(site, f), "rb").read() for f in os.listdir(site) if f.startswith("be_")}
    for f in os.listdir(os.path.join(data, "be_tab")):
        out["cache/" + f] = open(os.path.join(data, "be_tab", f), "rb").read()
    return out


def test_a_second_build_the_same_day_neither_refits_nor_recalibrates_a_new_day_does(tmp_path, monkeypatch):
    site, data, dash = make(tmp_path)
    assert be.run(dash, data, site, {}, NOW) == ["/be_*"] and be.pop_line().endswith("refit yes, calib yes")
    first, p1 = _snap(site, data), copy.deepcopy(dash["be"])
    calls = {}
    for nm in ("fit", "backtest", "calibrate", "skill"):
        _spy(monkeypatch, nm, calls)
    d2 = copy.deepcopy(dash)
    assert be.run(d2, data, site, {}, NOW + timedelta(hours=5)) == ["/be_*"]
    assert be.pop_line().endswith("refit no, calib no") and calls == {}
    assert _snap(site, data) == first and d2["be"] == p1              # byte for byte, from the caches
    d3 = copy.deepcopy(dash)
    be.run(d3, data, site, {}, NOW + timedelta(days=1))
    assert be.pop_line().endswith("refit yes, calib yes")
    assert calls == {"fit": 3, "backtest": 3, "calibrate": 1, "skill": 1}        # (app c too: fitted, real numbers only)
    with open(os.path.join(data, "be_tab", "calib.json"), encoding="utf-8") as f:
        cal = json.load(f)
    nxt = (TODAY + timedelta(days=1)).isoformat()
    assert cal["built"] == cal["tried"] == nxt and d3["be"]["origin"] == d3["be"]["calib"] == nxt
    with gzip.open(be._fits_path(data, KEYS["a"]), "rt") as f:
        assert json.load(f)["origin"] == nxt


def test_a_damaged_fits_cache_is_refitted_not_a_failure(tmp_path, capsys):
    site, data, dash = make(tmp_path)
    be.run(dash, data, site, {}, NOW)
    be.pop_line()
    with open(be._fits_path(data, KEYS["a"]), "wb") as f:
        f.write(b"\x1f\x8b broken")
    d2 = copy.deepcopy(dash)
    assert be.run(d2, data, site, {}, NOW) == ["/be_*"] and be.pop_line().endswith("refit yes, calib no")
    assert "skipped" not in capsys.readouterr().err and d2["be"] == dash["be"]


def test_a_failing_calibration_keeps_the_last_good_one_and_tries_again_the_next_day(tmp_path, monkeypatch, capsys):
    site, data, dash = make(tmp_path)
    be.run(dash, data, site, {}, NOW)
    be.pop_line()
    with open(os.path.join(data, "be_tab", "calib.json"), encoding="utf-8") as f:
        good = json.load(f)
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        return 1 / 0
    monkeypatch.setattr(be, "calibrate", boom)
    capsys.readouterr()
    d2 = copy.deepcopy(dash)
    assert be.run(d2, data, site, {}, NOW + timedelta(days=1)) == ["/be_*"]
    assert be.pop_line().endswith("refit yes, calib no") and calls["n"] == 1
    assert capsys.readouterr().err.count("be skipped: ZeroDivisionError") == 1
    with open(os.path.join(data, "be_tab", "calib.json"), encoding="utf-8") as f:
        kept = json.load(f)
    nxt = (TODAY + timedelta(days=1)).isoformat()
    assert {k: v for k, v in kept.items() if k != "tried"} == {k: v for k, v in good.items() if k != "tried"}
    assert kept["tried"] == nxt and d2["be"]["calib"] == TODAY.isoformat() and d2["be"]["origin"] == nxt
    assert body_of(site, "a")["calib"] == TODAY.isoformat()
    be.run(copy.deepcopy(dash), data, site, {}, NOW + timedelta(days=1, hours=3))          # same day: not again
    assert calls["n"] == 1 and "skipped" not in capsys.readouterr().err and be.pop_line().endswith("calib no")
    be.run(copy.deepcopy(dash), data, site, {}, NOW + timedelta(days=2))                   # the next day: again
    assert calls["n"] == 2


def test_no_calibration_yet_and_the_first_one_failing_ships_nothing_and_retries(tmp_path, monkeypatch, capsys):
    site, data, dash = make(tmp_path)
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise KeyError("x")
    monkeypatch.setattr(be, "calibrate", boom)
    assert be.run(dash, data, site, {}, NOW) == [] and "be" not in dash and be.pop_line() is None
    err = capsys.readouterr().err
    assert err.count("be skipped:") == 1 and "be skipped: KeyError" in err
    assert not [f for f in os.listdir(site) if f.startswith("be_")]
    be.run(dash, data, site, {}, NOW + timedelta(hours=1))
    assert calls["n"] == 2                                       # nothing to answer with: every build tries


# ── failure isolation, the switch, the wiring ───────────────────────────────────────────────────────────────────────

def test_one_apps_failure_costs_that_app_only_and_reaches_the_health_banner(tmp_path, monkeypatch, capsys):
    site, data, dash = make(tmp_path)
    load = be.load

    def bad(out_dir, data_dir, key, fn):
        if key == KEYS["b"]:
            return 1 / 0
        return load(out_dir, data_dir, key, fn)
    monkeypatch.setattr(be, "load", bad)
    assert be.run(dash, data, site, {}, NOW) == ["/be_*"]
    line = be.pop_line()
    assert line.startswith("be: apps 2, ") and line.endswith(", failed 1")
    assert set(dash["be"]["apps"]) == {APPS["a"], APPS["c"]}
    assert sorted(f for f in os.listdir(site) if f.startswith("be_")) == sorted("be_%s.json.gz" % KEYS[k] for k in "ac")
    err = capsys.readouterr().err
    assert "be skipped: ZeroDivisionError" in err
    health.FAULTS.clear()
    for ln in err.splitlines():
        health.scan(ln)
    assert health.FAULTS == {"be": "ZeroDivisionError"}
    health.FAULTS.clear()


def test_any_failure_costs_this_tab_only(tmp_path, monkeypatch, capsys):
    site, data, dash = make(tmp_path)
    be.run(dash, data, site, {}, NOW)
    be.pop_line()
    other = os.path.join(site, "roi_%s.json.gz" % KEYS["a"])
    before = open(other, "rb").read()
    monkeypatch.setattr(be, "_apps", lambda *a, **k: 1 / 0)
    d = copy.deepcopy(dash)
    assert be.run(d, data, site, {}, NOW) == [] and "be" not in d and be.pop_line() is None
    assert "be skipped: ZeroDivisionError" in capsys.readouterr().err
    assert not [f for f in os.listdir(site) if f.startswith("be_")] and open(other, "rb").read() == before
    assert d == {k: v for k, v in dash.items() if k != "be"}
    monkeypatch.setattr(be, "run", lambda *a, **k: 1 / 0)
    d = {"be": {"v": 1}}
    assert bs._be_step(d, data, site, {}) == [] and "be" not in d
    assert "be skipped: ZeroDivisionError" in capsys.readouterr().err


def test_no_roi_files_no_tab(tmp_path):
    site, data, dash = make(tmp_path)
    open(os.path.join(site, "be_%s.json.gz" % KEYS["a"]), "wb").close()                 # a stale one
    d = {"be": {"v": 1}}
    assert be.run(d, data, site, {}, NOW) == [] and "be" not in d and be.pop_line() == "be: apps 0"
    assert not [f for f in os.listdir(site) if f.startswith("be_")]


def test_switched_off_the_site_is_exactly_as_without_the_tab(tmp_path):
    site, data, dash = make(tmp_path)
    before = {f: open(os.path.join(site, f), "rb").read() for f in os.listdir(site)}
    s = dict(settings(), be_tab=True)
    assert bs._be_step(dash, data, site, s) == ["/be_*"] and "be" in dash
    d2 = {k: v for k, v in dash.items() if k != "be"}
    assert bs._be_step(d2, data, site, dict(s, be_tab=False)) == [] and "be" not in d2
    assert {f: open(os.path.join(site, f), "rb").read() for f in os.listdir(site)} == before
    assert be.enabled({}) and not be.enabled({"be_tab": False}) and be.pop_line() is None


def test_settings_pass_the_switch(monkeypatch):
    monkeypatch.delenv("BE_TAB", raising=False)
    assert settings()["be_tab"] is True
    monkeypatch.setenv("BE_TAB", "false")
    assert settings()["be_tab"] is False and be.enabled(settings()) is False


def test_build_static_runs_the_step_after_cpi_and_before_health_and_headers():
    src = open(os.path.join(ROOT, "admob_iq", "build_static.py"), encoding="utf-8").read()
    body = src[src.index("def build("):]
    i_c = body.index("aud_paths = aud_paths + _cpi_step(dashboard, data_dir, out_dir, s)")
    i_b = body.index("aud_paths = aud_paths + _be_step(dashboard, data_dir, out_dir, s)")
    i_h, i_x = body.index("health.attach(dashboard)"), body.index("headers_text(uni_files")
    assert i_c < i_b < i_h < i_x and "+ aud_paths + any_paths" in body


def _brute_auc(pts):
    pos = [s for s, y in pts if y]
    neg = [s for s, y in pts if not y]
    w = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in pos for b in neg)
    return round(100.0 * w / (len(pos) * len(neg)), 1)


def test_auc_is_mann_whitney_with_half_ties():
    assert be._auc([(1, False), (2, False), (3, True), (4, True)]) == 100.0
    assert be._auc([(1, True), (2, True), (3, False), (4, False)]) == 0.0
    assert be._auc([(5, True), (5, False), (5, True), (5, False)]) == 50.0
    pts = [((i * 7919) % 23 / 4.0, (i * 104729) % 3 == 0) for i in range(60)]     # ties and both sides mixed
    assert any(a[0] == b[0] for a in pts for b in pts if a is not b)
    assert be._auc(pts) == _brute_auc(pts)


def _rec(key, i, be_day, r30):
    """One back-test answer: the app curve's ROAS at 30 / 90 / 180 and the real BE day (None: not yet, watched 400 d)."""
    return {"key": key, "age": 400, "a": {"ages": [30, 90, 180], "roas": [r30, r30 * 1.5, r30 * 2.0]},
            "hi": be_day, "be": be_day, "obs": None if be_day is not None else 400, "be_a": 400 - 100 * r30}


def test_skill_scores_auc_c_and_needs_ten_days_each_side():
    # 10 days that broke even within 30 days (high ROAS(30)) and 30 that never did: AUC30 = 100, C from 10 real BE days
    A = [_rec("k", i, 20 + i, 0.9 + 0.001 * i) for i in range(10)] + [_rec("k", 10 + i, None, 0.2 + 0.01 * i)
                                                                      for i in range(30)]
    sk = be.skill(A)["k"]
    assert sk["n"] == 40 and sk["auc"][0] == 100.0 and sk["c"] is not None
    assert sk["auc"][1] == 100.0 and sk["auc"][2] == 100.0          # (the same 10 within 90 / 180 days)
    sk9 = be.skill(A[1:])["k"]                                       # 9 on the BE side: no AUC, and C has 9 real BE days
    assert sk9 == {"auc": [None, None, None], "c": None, "n": 39}
    flip = [dict(x, a={"ages": [30, 90, 180], "roas": [1.2 - r, 1.2 - r, 1.2 - r]}, be_a=1000 - x["be_a"])
            for x, r in ((x, x["a"]["roas"][0]) for x in A)]
    assert be.skill(flip)["k"]["auc"][0] == 0.0                      # a model that ranks backwards shows under 50


def test_a_day_outside_the_learned_range_is_not_answered():
    """A country's CPI or eCPM_fs outside the range its benchmark learned from gets no answer (its spend: "data kam"),
    never an extrapolated one: the app's curve is the country inside alone."""
    flat = [[j, [math.log(1.5), -1.0, 0.0], -0.2, 0.2, 40, math.log(1.5)] for j in range(13)]   # cheaper CPI → more ROAS
    rng = [math.log(1.0), math.log(4.0), math.log(1.0), math.log(6.0)]
    fc = {"origin": "2031-01-01", "app_med": [], "fits": {
        cc: {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": flat, "rng": rng} for cc in ("AA", "BB", "CC")}}
    cal = {"built": "2031-01-01", "cty": {str(H): [[0.0, 0.0], [1.0, 1.0]] for H in be.HS},
           "pit": {"0.1": 0.1, "0.5": 0.5, "0.9": 0.9}, "band": {}}
    day = "2030-12-30"
    app_row = R(day=day, sp=300.0, na=150.0, obs=0, oc=1.0)
    row = lambda cpi, ecpm: R(day=day, sp=100.0, na=50.0, cpi=cpi, c=math.log(cpi), e=math.log(ecpm))
    cs = {"AA": row(2.0, 3.0), "BB": row(0.026, 3.0), "CC": row(2.0, 0.1)}      # inside; CPI below; eCPM_fs below
    out = be.predict("k", fc, cal, ("2030-12-31", [app_row], {day: cs}))["days"][0]
    assert [x[0] for x in out["cty"]] == ["AA"] and out["cov"] == pytest.approx(1 / 3, abs=1e-3)
    assert sorted(x[0] for x in out["unc"]) == ["BB", "CC"]
    assert out["app"]["roas"][1] == pytest.approx(1.5 / 2.0, abs=1e-3)          # AA's curve at CPI 2: 1.5 × 2^−1
    assert out["app"]["roas"][0] == pytest.approx(1.0 / 300.0, abs=1e-4)        # (day 0 is observed: its real ROAS)
    # the edges: the learned range itself is inside (stored widened), and only usable days before O count
    O = date(2031, 1, 1).toordinal()
    rows = [R(day="2030-12-01", c=0.1234567, e=-0.5), R(day="2030-12-02", c=0.9, e=0.7654321),
            R(day="2030-11-20", c=5.0, e=5.0, jd=False),       # not judged: never learned from
            R(day="2030-12-20", c=-5.0, e=-5.0),               # judged but not settled by O (+ 30 days): not trained on
            R(day="2031-01-02", c=-6.0, e=-6.0)]               # after O
    g = be._rng(rows, O)
    assert g == [0.123456, 0.9, -0.5, 0.765433]                # (the young days being answered never widen it)
    assert be._seen(g, rows[0]) and be._seen(g, rows[1]) and not any(be._seen(g, x) for x in rows[2:])
    assert be._rng(rows[2:], O) is None and not be._seen(None, rows[0])     # nothing learned: nothing answered


def _one(fc_fits, cal, app_row, cs, day="2030-12-30"):
    fc = {"origin": "2031-01-01", "app_med": [], "fits": fc_fits}
    return be.predict("k", fc, cal, ("2030-12-31", [app_row], {day: cs}))["days"][0]


CAL0 = {"built": "2031-01-01", "cty": {str(H): [[0.0, 0.0], [1.0, 1.0]] for H in be.HS},
        "pit": {"0.1": 0.1, "0.5": 0.5, "0.9": 0.9}, "band": {}}


def test_what_is_already_observed_floors_the_curve():
    """A day already at 108 % ROAS by day 13 (it broke even on day 12) is never answered below that: from its age on, the
    curve is at least what it has really made — its breakeven day is then at or before day 13."""
    low = [[j, [math.log(v), 0.0, 0.0], -0.2, 0.2, 40, math.log(v)] for j, v in
           enumerate([0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.7, 0.9, 1.0, 1.2, 1.4, 1.5])]     # alone: BE on day 120
    fits = {"AA": {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": low, "rng": WIDE}}
    day = "2030-12-30"
    app_row = R(day=day, sp=100.0, na=50.0, obs=13, oc=108.0, hi=12, be=12.0)
    cs = {"AA": R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))}
    a = _one(fits, CAL0, app_row, cs)["app"]
    i13 = be.GRID.index(13)
    assert a["roas"][:i13] == [0.1, 0.15, 0.2, 0.25, 0.3] and all(v >= 1.08 for v in a["roas"][i13:])
    assert a["be"] == [12, None, None] and a["roas"][-1] == 1.5      # its real day, no range (above the floor: the curve's)
    later = R(day=day, sp=100.0, na=50.0, obs=13, oc=80.0)          # not yet: 80 % so far
    b = _one(fits, CAL0, later, cs)["app"]
    assert all(v >= 0.8 for v in b["roas"][i13:]) and b["roas"][i13] == 0.8 and b["be"][0] == 120
    unfloored = _one(fits, CAL0, R(day=day, sp=100.0, na=50.0, obs=None, oc=None), cs)["app"]
    assert unfloored["be"][0] == 120


def test_a_calibration_without_a_level_answers_no_day_never_past_its_limit():
    flat = [[j, [math.log(1.5), 0.0, 0.0], -0.2, 0.2, 40, math.log(1.5)] for j in range(13)]
    fits = {"AA": {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": flat, "rng": WIDE}}
    day = "2030-12-30"
    cs = {"AA": R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))}
    app_row = R(day=day, sp=100.0, na=50.0, obs=0, oc=1.0)
    full = _one(fits, CAL0, app_row, cs)["cty"][0]
    assert full[7:] == [0, 0, 0, 360, 0]                      # (a flat 150 % curve: its spend back on day 0)
    for q in ("0.5", "0.1", "0.9"):                         # (Kaplan–Meier never reaching 0.9 under heavy censoring …)
        cal = dict(CAL0, pit=dict(CAL0["pit"], **{q: None}))
        row = _one(fits, cal, app_row, cs)["cty"][0]
        assert row == full                                   # a country's day is its curve's: no calibration level needed


def test_the_app_range_reaches_only_as_far_as_its_band():
    """A band to 30 days only: the range's early end where the band's high curve crosses; its late end (the low curve)
    does not cross within the band's reach → null (the page: "<reach>+"), never the median line."""
    cv = [[j, [math.log(v), 0.0, 0.0], -0.2, 0.2, 40, math.log(v)] for j, v in
          enumerate([0.1, 0.15, 0.2, 0.25, 0.3, 0.5, 0.9, 1.1, 1.3, 1.4, 1.5, 1.6, 1.7])]       # median BE between 30 and 60
    fits = {"AA": {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": cv, "rng": WIDE}}
    band = {str(a): [0.0, math.log(0.5), math.log(1.5), 99] for a in be.GRID[:7]}            # ages 0 … 30
    day = "2030-12-30"
    cs = {"AA": R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))}
    a = _one(fits, dict(CAL0, band=band), R(day=day, sp=100.0, na=50.0, obs=0, oc=1.0), cs)["app"]
    assert a["lo"][6] is not None and a["lo"][7:] == [None] * 6 and a["hi"][7:] == [None] * 6
    assert 30 < a["be"][0] < 60 and a["be"][1] is not None and a["be"][1] <= 30 and a["be"][2] is None


def test_an_empty_back_test_is_no_calibration_the_last_good_one_stays(tmp_path, monkeypatch, capsys):
    site, data, dash = make(tmp_path)
    be.run(dash, data, site, {}, NOW)
    be.pop_line()
    with open(os.path.join(data, "be_tab", "calib.json"), encoding="utf-8") as f:
        good = json.load(f)
    monkeypatch.setattr(be, "backtest", lambda *a, **k: ([], []))        # (e.g. every app's reads unusable that day)
    capsys.readouterr()
    d2 = copy.deepcopy(dash)
    assert be.run(d2, data, site, {}, NOW + timedelta(days=1)) == ["/be_*"]
    assert capsys.readouterr().err.count("be skipped: ValueError") == 1 and be.pop_line().endswith("calib no")
    with open(os.path.join(data, "be_tab", "calib.json"), encoding="utf-8") as f:
        kept = json.load(f)
    assert {k: v for k, v in kept.items() if k != "tried"} == {k: v for k, v in good.items() if k != "tried"}
    b = body_of(site, "a")                                               # the day's answers: the last good calibration's
    assert b["calib"] == TODAY.isoformat() and b["skill"] == good["skill"][KEYS["a"]] and d2["be"]["calib"] == TODAY.isoformat()


def test_a_day_not_broken_even_never_answers_a_day_before_its_age():
    """The model says 100 % on day 3, but the day is only at 80 % on day 10 (not broken even): its BE day comes after
    day 10 — the observed point is on the curve (capped before it, floored after it), even between grid ages 6 and 13."""
    fast = [[j, [math.log(v), 0.0, 0.0], -0.2, 0.2, 40, math.log(v)] for j, v in
            enumerate([0.3, 0.6, 0.9, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0])]
    fits = {"AA": {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": fast, "rng": WIDE}}
    band = {str(a): [0.0, math.log(0.8), math.log(1.25), 99] for a in be.GRID}
    day = "2030-12-30"
    cs = {"AA": R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))}
    row = R(day=day, sp=100.0, na=50.0, obs=10, oc=80.0)
    a = _one(fits, dict(CAL0, band=band), row, cs)["app"]
    i6, i13 = be.GRID.index(6), be.GRID.index(13)
    assert a["roas"][:i6 + 1] == [0.3, 0.6, 0.8, 0.8, 0.8] and a["roas"][i13] == 1.3       # capped at 80 % before day 10
    assert all(v is None or v > 10 for v in a["be"]) and 10 < a["be"][0] < 13             # median and range: after day 10
    assert a["be"][1] <= a["be"][0] <= a["be"][2]


def test_a_level_of_0_or_1_is_no_level_and_never_crashes():
    flat = [[j, [math.log(1.5), 0.0, 0.0], -0.2, 0.2, 40, math.log(1.5)] for j in range(13)]
    fits = {"AA": {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": flat, "rng": WIDE}}
    day = "2030-12-30"
    cs = {"AA": R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))}
    row = R(day=day, sp=100.0, na=50.0, obs=0, oc=1.0)
    for bad in (1.0, 0.0):
        cal = dict(CAL0, pit={"0.1": 0.1, "0.5": bad, "0.9": 0.9})
        assert _one(fits, cal, row, cs)["cty"][0][7:] == [0, 0, 0, 360, 0]       # (never a crash; the curve's day)
    # calibrate() never stores such a level: 40 events early, 100 days censored late, 3 extreme events
    C = [(math.log(31.0), 0.3, 20, 20.0, 400, 400)] * 40 + [(math.log(31.0), 0.3, None, None, 40, 400)] * 100 + \
        [(math.log(31.0), 0.3, 900, 900.0, 950, 1000)] * 3
    pit = be.calibrate([], C, 1)["pit"]
    assert all(v is None or 0.0 < v < 1.0 for v in pit.values())


def test_an_old_day_shows_its_real_roas_where_it_has_lived_never_the_model():
    """Every install day now (the owner's "baki ke din"): a 425-day-old day that never broke even made 40 / 65 / 80 % by
    days 30 / 90 / 180 — those are its ROAS there, not the model's 120 % (nor a "≥ 90 %" floor); a day that broke even on
    day 120 shows its real 40 % at 30 days (no ✓) and its real day."""
    hi_model = [[j, [math.log(1.2), 0.0, 0.0], -0.2, 0.2, 40, math.log(1.2)] for j in range(13)]
    fits = {"AA": {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": hi_model, "rng": WIDE}}
    day = "2030-12-30"
    cs = {"AA": R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))}
    real = [0.05, 0.08, 0.1, 0.12, 0.16, 0.25, 0.4, 0.55, 0.65, 0.7, 0.8, 0.85, 0.9]          # at the 13 grid ages
    never = R(day=day, sp=100.0, na=50.0, cum=[100.0 * v for v in real], obs=360, oc=90.0)
    dn = _one(fits, CAL0, never, cs)
    a = dn["app"]
    assert dn["real"] == real and a["roas"] == real and a["lo"] == [None] * 13    # real everywhere (no band in CAL0)
    assert a["be"] == [None, None, None]                                           # never reached 100 % in its 360 days
    young = R(day=day, sp=100.0, na=50.0, cum=[100.0 * v for v in real[:6]] + [None] * 7, obs=13, oc=25.0)
    dy = _one(fits, CAL0, young, cs)
    y = dy["app"]
    assert dy["real"] == real[:6] and y["roas"][:6] == real[:6] and y["roas"][6:] == [1.2] * 7   # lived: real; after: model
    assert 13 < y["be"][0] <= 30
    bec = [0.05, 0.08, 0.1, 0.12, 0.16, 0.25, 0.4, 0.7, 0.9, 1.005, 1.3, 1.4, 1.5]
    broke = R(day=day, sp=100.0, na=50.0, cum=[100.0 * v for v in bec], obs=360, oc=150.0, hi=120, be=118.0)
    b = _one(fits, CAL0, broke, cs)["app"]
    assert b["roas"][be.GRID.index(30)] == 0.4 and b["be"] == [118, None, None]   # 30 days: its real 40 %, no ✓


def test_a_day_just_under_100_percent_is_never_answered_its_own_age():
    """99.9 % by day 90, the model's next grid age at 140 %: the crossing (≈ 90.0) would round to "day 90" while it has not
    broken even by day 90 — the answer is day 91 at the earliest."""
    up = [[j, [math.log(v), 0.0, 0.0], -0.2, 0.2, 40, math.log(v)] for j, v in
          enumerate([0.3, 0.35, 0.4, 0.42, 0.46, 0.54, 0.67, 0.84, 0.95, 1.4, 1.5, 1.6, 1.7])]
    fits = {"AA": {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": up, "rng": WIDE}}
    day = "2030-12-30"
    cs = {"AA": R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))}
    real = [0.3, 0.35, 0.4, 0.42, 0.46, 0.54, 0.67, 0.84, 0.999] + [None] * 4
    row = R(day=day, sp=100.0, na=50.0, cum=[None if v is None else 100.0 * v for v in real], obs=90, oc=99.9)
    a = _one(fits, CAL0, row, cs)["app"]
    assert a["roas"][be.GRID.index(90)] == 0.999 and a["be"][0] == 91


def _roi_row(X, sp, d, df, t=None, s=None, sd=None, b=None, m=None, mf=0):
    """A roi row in roi_build's shape (only the fields be_build reads)."""
    return [X, 100, 50, sp, d, df, None, t or [None] * 10, s, sd, b, None, 0, sp, m, mf]


def test_real_means_final_cells_and_the_rois_own_answer():
    # d final through df only; a 30-day column final only below mf; s / sd later than the last point; the ROI's be
    d = [1.0 * (i + 1) for i in range(31)]                           # cumulative revenue on ages 0 … 30
    x = be._row(_roi_row("2030-01-01", 100.0, d, df=20, m=[50.0, 70.0], mf=1, s=75.0, sd="2030-04-15"), None, True)
    gi = be.GRID.index
    assert x.fin[gi(13)] == 14.0 and x.fin[gi(30)] is None          # age 30 is not final (df 20)
    assert x.fin[gi(60)] == 50.0 and x.fin[gi(90)] is None          # the 90 column is not final (mf 1)
    assert (x.sfa, x.sfv) == (104, 75.0) and x.rbe is None           # so far through 15 Apr = age 104 > the last column (90)
    y = be._row(_roi_row("2030-01-01", 10.0, d, df=31, b=[9, True]), None, True)
    assert y.rbe == (9, "x")
    z = be._row(_roi_row("2030-01-01", 10.0, d, df=31, b=[90, False]), None, True)
    assert z.rbe == (90, "b")                                         # "≤ day 90" (a 30-day column)
    w = be._row(_roi_row("2030-01-01", 10.0, d, df=5, b=[9, False]), None, True)
    assert w.rbe == (9, "nf")                                         # a daily cell, not final yet
    s_ = be._row(_roi_row("2030-01-01", 70.0, d, df=31, s=75.0, sd="2030-04-15"), None, True)
    assert s_.rbe == (104, "s")                                       # its so-far read paid back, no cell pins the day
    # the 30-day column before the checkpoint at 90 (the ROI row's own breakeven reads it): not final = not real
    t = [None] * 10
    t[be.T.index(90)] = 99.0
    q = be._row(_roi_row("2030-01-01", 100.0, d, df=31, t=t, m=[50.0, 60.0], mf=2), None, True)
    assert q.fin[gi(90)] == 60.0
    q2 = be._row(_roi_row("2030-01-01", 100.0, d, df=31, t=t, m=[50.0, 60.0], mf=1), None, True)
    assert q2.fin[gi(90)] is None


def test_every_day_carries_its_real_roas_even_with_nothing_covered_and_a_country_answers_its_real_day():
    flat = [[j, [math.log(1.5), 0.0, 0.0], -0.2, 0.2, 40, math.log(1.5)] for j in range(13)]
    fits = {"AA": {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": flat, "rng": WIDE}}
    day = "2030-12-30"
    real = [0.05, 0.08, 0.1, 0.12, 0.16, 0.25, 0.4, 0.55, 0.65, 0.7, 0.8, 0.85, 0.9]
    old = R(day=day, sp=100.0, na=50.0, cum=[100.0 * v for v in real], obs=360, oc=90.0)
    nobody = _one({}, CAL0, old, {"ZZ": R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))})
    assert "app" not in nobody and nobody["real"] == real and nobody["now"] == ["no", 360, 0.9, 0]
    broke = R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0), rbe=(12, "x"))
    later = R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0), sfa=200, sfv=80.0)
    got = _one(fits, CAL0, old, {"AA": later})["cty"][0][7:]
    assert 201 <= got[1] < got[0] < got[2] and got[3:] == [360, 0]   # its curve given 80 % by day 200: a real band past it
    assert _one(fits, CAL0, old, {"AA": broke})["cty"][0][7:] == [12, None, None, 360, 1]   # its real day, no range


def test_a_model_age_never_falls_below_the_real_one_before_it():
    """Final cells to 270 days at 240 %, its so-far read a little lower (another source), the model at 360 lower still:
    360 days is never below the real 270 (the real values stay as given)."""
    low = [[j, [math.log(v), 0.0, 0.0], -0.2, 0.2, 40, math.log(v)] for j, v in
           enumerate([0.3, 0.4, 0.5, 0.6, 0.7, 0.9, 1.1, 1.4, 1.7, 1.9, 2.1, 2.2, 2.3])]
    fits = {"AA": {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": low, "rng": WIDE}}
    day = "2030-12-30"
    cs = {"AA": R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))}
    real = [0.3, 0.4, 0.5, 0.6, 0.7, 0.9, 1.1, 1.4, 1.7, 1.9, 2.1, 2.4045]
    row = R(day=day, sp=100.0, na=50.0, cum=[100.0 * v for v in real] + [None], obs=277, oc=239.0, rbe=(2, "x"))
    a = _one(fits, CAL0, row, cs)["app"]
    assert a["roas"][11] == 2.4045 and a["roas"][12] == 2.4045                     # (the model said 2.3; its so far 2.39)


def test_a_so_far_read_past_spend_is_broken_even_by_that_day_never_abhi_nahi():
    """No cell pins the day (the ROI row's be is null) but its so-far read through day 113 is 102 %: the answer is "≤ day
    113" (kind "s"), never "abhi nahi" with a model day 114 or "day N tak nahi"."""
    up = [[j, [math.log(v), 0.0, 0.0], -0.2, 0.2, 40, math.log(v)] for j, v in
          enumerate([0.3, 0.35, 0.4, 0.42, 0.46, 0.54, 0.67, 0.84, 0.95, 1.4, 1.5, 1.6, 1.7])]
    fits = {"AA": {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": up, "rng": WIDE}}
    day = "2030-12-30"
    cs = {"AA": R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))}
    real = [0.3, 0.35, 0.4, 0.42, 0.46, 0.54, 0.67, 0.84, 0.95] + [None] * 4
    row = R(day=day, sp=100.0, na=50.0, cum=[None if v is None else 100.0 * v for v in real], obs=90, oc=95.0,
            sfa=113, sfv=102.0, rbe=(113, "s"))
    out = _one(fits, CAL0, row, cs)
    assert out["now"] == ["be", 113, "s", 113, 1.02, 0] and out["app"]["be"] == [113, None, None]
    assert out["app"]["roas"][be.GRID.index(120)] >= 1.02                       # floored by its so far past day 113


def test_the_so_far_read_is_capped_at_365_and_never_below_the_last_point_and_never_rounds_to_100():
    d = [1.0 * (i + 1) for i in range(31)]
    x = be._row(_roi_row("2030-01-01", 1000.0, d, df=31, s=40.0, sd="2031-06-01"), None, True)
    assert x.sfa == 365                                    # the install-day read stops at day 365 (no 30-day column here)
    y = be._row(_roi_row("2030-01-01", 1000.0, d, df=31, s=20.0, sd="2030-03-01"), None, True)
    assert (y.sfa, y.sfv) == (59, 31.0)                    # a later read lower than the last point keeps the point's value
    assert be._rr(0.99996) == 0.9999 and be._rr(1.00004) == 1.0 and be._rr(0.5) == 0.5

