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


R5_LINE = re.compile(r", (?:guard cty \d+ \(sampled \d+, over \d+\)|ecpm off band \d+ \(recent \d+\)|gap rows \d+ \(recent \d+\), "
                     r"gap dates rel \d+ ledger \d+|users/install \d+ \(recent \d+\)|gap fail \d+|"
                     r"lived fallback \d+ \(app \d+\))")


def _l4(line):
    """⚖️ The counts line without round 5's own counts (their shape: tests/test_be_datafix.py) — FSC's output check
    counts the forecast rows outside B's 1st … 99th eCPM_fs percentile in almost any world; the parts these tests pin
    sit next to each other again."""
    return R5_LINE.sub("", line or "")


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
    fc = {"origin": "2031-01-01", "fits": {
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
    assert a_row[7] == 30 and a_row[8] <= 30 <= a_row[9] and a_row[10:12] == [90, 0]
    assert b_row[7] == 300 and b_row[8] <= 300 and a_row[7] < out["app"]["be"][0] < b_row[7] and b_row[10:12] == [360, 0]
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
    sk = b["skill"]                        # the shift's back-test: C on day 1 / 7 / 14, the AUC at 30 / 90 / 180 on day 7
    assert set(sk) == {"auc", "c", "n"} and len(sk["auc"]) == 3 and len(sk["c"]) == 3 and sk["n"] > 100
    assert any(v is not None for v in sk["auc"]) and all(v is not None and 50 < v <= 100 for v in sk["c"])
    shifted = 0
    for d in days:
        assert set(d) == {"d", "age", "sp", "inst", "cov", "real", "app", "unc", "cty", "card", "now"}   # (no data hole)
        a = d["app"]
        assert set(a) - {"anc"} == {"be", "lim", "roas", "lo", "hi"} and a["lim"] in be.GRID
        if "anc" in a:                     # shifted at its latest FINAL grid age within its curve (here every lived
            shifted += 1                   # cell is final: the synthetic rows' df = all of them), a daily one ≥ CLAG
            assert a["anc"] == max(g for g, v in zip(be.GRID, d["real"]) if v is not None and g <= a["lim"]
                                   and (g > 30 or g <= d["age"] - be.CLAG))       # days old (the newest one often empty)
        assert len(a["roas"]) == len(a["lo"]) == len(a["hi"]) == be.GRID.index(a["lim"]) + 1
        assert all(v is None or isinstance(v, int) for v in a["be"])
        assert a["roas"] == sorted(a["roas"])                    # the app curve never goes down with age
        ccs = [x[0] for x in d["cty"]]
        assert sorted(ccs) == ["AA", "BB", "CC"] and all(len(x) == 14 and isinstance(x[10], int) and x[11] in range(7) for x in d["cty"])
        assert all(isinstance(x[12], list) and len(x[12]) == 4 for x in d["cty"])      # bm: the country's benchmark
        assert all(x[13] is None or (len(x[13]) == 3 and x[13][0] <= d["age"]) for x in d["cty"])   # its "ROAS so far"
        assert [x[1] for x in d["cty"]] == sorted((x[1] for x in d["cty"]), reverse=True)
        named = [x for x in d["unc"] if x[0] != "…"]
        rest = [x for x in d["unc"] if x[0] == "…"]
        assert [x[0] for x in named] == ["EE"] and len(rest) == 1 and d["unc"][-1] == rest[0]
        assert rest[0][1] == pytest.approx(8.0 / 384.0, abs=0.004)          # DA … DH: 8 × 1 USD of ≈ 384 USD
        assert sum(x[1] for x in d["cty"]) + sum(x[1] for x in d["unc"]) == pytest.approx(1.0, abs=0.002)
        assert d["cov"] == pytest.approx(sum(x[1] for x in d["cty"]), abs=0.002)
        c = d["card"]
        assert set(c) == {"roas", "bench", "fin", "cv", "chk"} and all(len(v) == 6 for v in c.values())
        assert not any(c["chk"]) and all(v is None or 0 < v <= d["cov"] + 0.001 for v in c["cv"])   # (no pack gap here)
        assert all(f in (0, 1) and (f == 0 or v is not None) for f, v in zip(c["fin"], c["roas"]))   # final ⇒ a value
        seen = [i for i, j in enumerate(be.CARD_J) if be.GRID[j] <= d["age"]]
        assert [i for i, v in enumerate(c["roas"]) if v is not None] == seen   # (null where not observed yet)
        assert [i for i, v in enumerate(c["bench"]) if v is not None] == seen
        assert [i for i, v in enumerate(c["cv"]) if v is not None] == seen
    assert shifted == sum(1 for d in days if d["age"] >= be.CLAG)   # (no data hole: every day with a read old enough)
    new = days[-1]
    prov = [d for d in days if d["age"] < be.PROV]                 # provisional: answered and shown, not final
    assert [d["age"] for d in prov] == [3, 2, 1, 0] and all("app" in d for d in prov)
    assert new["now"][:2] == ["no", 0] and new["now"][3] == 0 and new["card"]["roas"][1:] == [None] * 5   # (not final)
    b2 = body_of(built["site"], "b")
    assert all("app" not in d and d["cov"] == 0.0 and d["cty"] == [] and d["unc"] == [["EE", 1.0]] for d in b2["days"])
    assert b2["skill"] == {"auc": [None, None, None], "c": [None, None, None], "n": 0}


def test_the_fits_recover_the_synthetic_benchmark(built):
    with gzip.open(os.path.join(built["data"], "be_tab", "fits_%s.json.gz" % KEYS["a"]), "rt") as f:
        fc = json.load(f)
    assert fc["v"] == 1 and fc["fv"] == be.FV == 2 and fc["origin"] == TODAY.isoformat() and sorted(fc["fits"]) == ["AA", "BB", "CC"]
    for cc, (sp, cpi, ecpm, kap) in CTY.items():
        a, b, c, s, tmax, kept, dropped, cens = fc["fits"][cc]["k3"]
        assert b == pytest.approx(1 / G, abs=0.15) and c == pytest.approx(-1 / G, abs=0.15)   # log(BE + 1) slopes
        assert a == pytest.approx(-math.log(kap) / G, abs=0.4) and kept >= be.MIN_KEPT and cens > 0
        assert [be.GRID[j] for j, *_ in fc["fits"][cc]["cv"]] == list(be.GRID)
    assert "app_med" not in fc and "app_idx" not in fc
    for cc in CTY:                                           # the benchmark triple from K3's own training set
        bcpi, becpm, bbe, blim = fc["fits"][cc]["bm"]
        assert bcpi == pytest.approx(CTY[cc][1], rel=0.3) and becpm == pytest.approx(CTY[cc][2], rel=0.3)
        assert blim == round(fc["fits"][cc]["k3"][4]) and (bbe is None or bbe > 0)


def test_headers_one_splat_rule_covers_the_files(built):
    base = bs.headers_text(["uninstall.json.gz"], built["dash"])
    text = bs.headers_text(["uninstall.json.gz"], built["dash"], extra=built["paths"])
    assert headers_rule_count(text) == headers_rule_count(base) + 1 <= HEADERS_MAX_RULES
    assert headers_cover(text, "be_%s.json.gz" % KEYS["a"]) and not headers_cover(base, "be_%s.json.gz" % KEYS["a"])
    assert "/be_*\n  Cache-Control: no-store" in text


def test_the_log_line_names_nothing(built):
    line = built["line"]
    assert re.fullmatch(r"be: apps \d+, days \d+, covered \d+, uncovered \d+, refit (yes|no), calib (yes|no)",
                        _l4(line)), line
    assert _l4(line) == "be: apps 3, days 660, covered 3, uncovered 11, refit yes, calib yes"   # every day with spend
    assert line == _l4(line) or re.fullmatch(r".*, calib yes, ecpm off band \d+ \(recent \d+\)", line)   # (round 5: counts)
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
    assert be.run(dash, data, site, {}, NOW) == ["/be_*"] and _l4(be.pop_line()).endswith("refit yes, calib yes")
    first, p1 = _snap(site, data), copy.deepcopy(dash["be"])
    calls = {}
    for nm in ("fit", "backtest", "asof", "calibrate", "skill2"):
        _spy(monkeypatch, nm, calls)
    d2 = copy.deepcopy(dash)
    assert be.run(d2, data, site, {}, NOW + timedelta(hours=5)) == ["/be_*"]
    assert _l4(be.pop_line()).endswith("refit no, calib no") and calls == {}
    assert _snap(site, data) == first and d2["be"] == p1              # byte for byte, from the caches
    d3 = copy.deepcopy(dash)
    be.run(d3, data, site, {}, NOW + timedelta(days=1))
    assert _l4(be.pop_line()).endswith("refit yes, calib yes")
    assert calls == {"fit": 3, "backtest": 3, "asof": 3, "calibrate": 1, "skill2": 3}   # (app c too: real numbers only)
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
    assert be.run(d2, data, site, {}, NOW) == ["/be_*"] and _l4(be.pop_line()).endswith("refit yes, calib no")
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
    assert _l4(be.pop_line()).endswith("refit yes, calib no") and calls["n"] == 1
    assert capsys.readouterr().err.count("be skipped: ZeroDivisionError") == 1
    with open(os.path.join(data, "be_tab", "calib.json"), encoding="utf-8") as f:
        kept = json.load(f)
    nxt = (TODAY + timedelta(days=1)).isoformat()
    same = lambda c: {k: v for k, v in c.items() if k not in ("tried", "skill")}    # noqa: E731
    assert same(kept) == same(good)                                      # the last good maps and ranges stay; the skill
    assert set(kept["skill"]) == set(good["skill"]) and all(isinstance(v["c"], list) for v in kept["skill"].values())
    assert kept["tried"] == nxt and d2["be"]["calib"] == TODAY.isoformat() and d2["be"]["origin"] == nxt   # (this build's)
    assert body_of(site, "a")["calib"] == TODAY.isoformat()
    be.run(copy.deepcopy(dash), data, site, {}, NOW + timedelta(days=1, hours=3))          # same day: not again
    assert calls["n"] == 1 and "skipped" not in capsys.readouterr().err and _l4(be.pop_line()).endswith("calib no")
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

    def bad(out_dir, data_dir, key, fn, *a):
        if key == KEYS["b"]:
            return 1 / 0
        return load(out_dir, data_dir, key, fn, *a)
    monkeypatch.setattr(be, "load", bad)
    assert be.run(dash, data, site, {}, NOW) == ["/be_*"]
    line = be.pop_line()
    assert line.startswith("be: apps 2, ") and _l4(line).endswith(", failed 1")
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


def _sk_row(a, ra, vals, be_day, obs=400):
    """One back-test day for the skill: its shifted curve after as-of age a (GRID ages), its real BE day (None: watched
    obs days without)."""
    pts = [(t, v) for t, v in zip([t for t in be.GRID if t > a], vals)]
    return (be._cut(a, ra, pts), pts[-1][0], be_day, None if be_day is not None else obs)


def test_skill_is_the_shifts_ranking_on_day_1_7_14_and_the_auc_on_day_7():
    # 10 days that broke even (the earlier the BE, the higher the curve) and 30 that never did (lower curves): C = 100
    good = [_sk_row(0, 0.5, [0.5 + 0.1 * (k + 1) * (1.3 - 0.01 * i) for k in range(12)], 10 + 5 * i) for i in range(10)]
    never = [_sk_row(0, 0.2, [0.2 + 0.02 * (k + 1) * (1 - 0.01 * i) for k in range(12)], None) for i in range(30)]
    AU = {H: [(math.log(1.2 - 0.01 * i), True) for i in range(10)] + [(math.log(0.5 - 0.01 * i), False)
                                                                     for i in range(30)] for H in be.HS}
    sk = be.skill2({0: good + never, 6: good + never, 13: good[1:] + never}, AU, 40)
    assert sk == {"c": [100.0, 100.0, None], "auc": [100.0, 100.0, 100.0], "n": 40}   # 9 real-BE days on day 14: None
    flip = {H: [(-x, y) for x, y in v] for H, v in AU.items()}
    assert be.skill2({}, flip, 0)["auc"][0] == 0.0                   # a forecast that ranks backwards shows under 50
    assert be.skill2({}, {H: v[1:] for H, v in AU.items()}, 0)["auc"] == [None] * 3   # 9 on the BE side: no AUC


def test_the_ranking_cuts_every_pair_at_the_shorter_curve():
    """The old score compared "beyond 120" with "beyond 270" (last age + 1000 × what is missing): two IDENTICAL forecasts
    whose curves stop at different ages counted as a wrong pair (one app read under 50 % that way). Cut at the shorter curve they tie."""
    same = [0.30, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70, 0.80, 0.85, 0.90, 0.92, 0.95]       # never 100 % (ages 1 … 360)
    early = _sk_row(0, 0.2, same, 100)                              # (the curve to 360; really broke even on day 100)
    late = _sk_row(0, 0.2, same[:9], None, obs=500)                 # (the same curve, stops at 120; no BE by day 500)
    old = [e[1] + 1000 * (1 - same[len(e[0]) - 1]) for e in (early, late)]
    assert old[0] > old[1]                  # the old score: "beyond 360 at 95 %" later than "beyond 120 at 85 %" — wrong
    assert be._cpair([early, late] * 10) == 50.0                    # identical forecasts: ties, never "wrong"
    late = _sk_row(0, 0.2, same, None, obs=500)
    hi = _sk_row(0, 0.2, [v + 0.2 for v in same], 100)             # a curve above the other at the cut: earlier → right
    assert be._cpair([hi, late] * 10) == 100.0
    cross = _sk_row(0, 0.5, [0.6, 0.8, 1.1] + [1.2] * 9, 3)          # crosses inside the cut: beats a non-crossing one
    assert be._cpair([cross, late] * 10) == 100.0


def test_a_day_outside_the_learned_range_is_answered_at_its_edge_moved_by_the_ratio():
    """Owner, 16 Nov 2026: "Cpi kitna bhi uppar jaye uspe vo rule mat lagao … benchmark se kitna plus hua he aur ecpm
    kitna benchmark se badla he": a country whose CPI or eCPM_fs is outside the range its benchmark learned from is
    answered too — its curve at the range's edge, moved by the ratio past it (twice the edge's CPI: half the ROAS; an
    eCPM_fs under the range: as much lower); an eCPM_fs above the range moves it no further than the range's top. Every
    such country counts in the app's curve (no "data kam" for it); K3's own chances only inside the range."""
    flat = [[j, [math.log(1.5), -0.5, 0.25], -0.2, 0.2, 40, math.log(1.5)] for j in range(13)]
    rng = [math.log(1.0), math.log(4.0), math.log(1.0), math.log(6.0)]
    fc = {"origin": "2031-01-01", "fits": {
        cc: {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": flat, "rng": rng}
        for cc in ("AA", "BB", "CC", "DD", "EE", "FF")}}
    cal = {"built": "2031-01-01", "cty": {str(H): [[0.0, 0.0], [1.0, 1.0]] for H in be.HS},
           "pit": {"0.1": 0.1, "0.5": 0.5, "0.9": 0.9}, "band": {}}
    day = "2030-12-30"
    app_row = R(day=day, sp=600.0, na=300.0, obs=0, oc=1.0)
    row = lambda cpi, ecpm: R(day=day, sp=100.0, na=50.0, cpi=cpi, c=math.log(cpi), e=math.log(ecpm))
    cs = {"AA": row(2.0, 3.0), "BB": row(8.0, 3.0), "CC": row(2.0, 0.5), "DD": row(2.0, 12.0), "EE": row(0.5, 3.0),
          "FF": row(8.0, 12.0)}
    want = {"AA": 1.5 * 2 ** -0.5 * 3 ** 0.25,                 # inside: the curve itself
            "BB": 1.5 * 4 ** -0.5 * 3 ** 0.25 / 2.0,           # CPI twice the top: the edge's curve, halved
            "CC": 1.5 * 2 ** -0.5 * 0.5,                       # eCPM_fs half the bottom: the edge's curve, halved
            "DD": 1.5 * 2 ** -0.5 * 6 ** 0.25,                 # eCPM_fs above the top: held at the top
            "EE": 1.5 * 1 ** -0.5 * 3 ** 0.25 * 2.0,           # CPI half the bottom: the edge's curve, doubled
            "FF": 1.5 * 4 ** -0.5 * 6 ** 0.25 / 2.0}           # both out: CPI by the ratio, eCPM_fs held at the top
    for cc, x in cs.items():
        ages, mid, lo, hi = be.curve_at(flat, rng, x)
        assert math.exp(mid[1]) == pytest.approx(want[cc], rel=1e-9)
        assert math.exp(lo[1]) == pytest.approx(want[cc] * math.exp(-0.2), rel=1e-9)     # (its band moves with it)
    out = be.predict("k", fc, cal, ("2030-12-31", [app_row], {day: cs}))["days"][0]
    assert sorted(x[0] for x in out["cty"]) == sorted(cs) and out["cov"] == 1.0 and out["unc"] == []
    assert out["app"]["roas"][1] == pytest.approx(sum(want.values()) / 6, abs=1e-4)   # each by its spend share
    assert out["app"]["roas"][0] == pytest.approx(1.0 / 600.0, abs=1e-4)               # (day 0 is observed: real)
    pk = {x[0]: x[4:7] for x in out["cty"]}
    assert all(v is not None for v in pk["AA"]) and all(pk[cc] == [None] * 3 for cc in cs if cc != "AA")
    # the edges: the learned range itself is inside (stored widened), and only usable days before O count
    O = date(2031, 1, 1).toordinal()
    rows = [R(day="2030-12-01", c=0.1234567, e=-0.5), R(day="2030-12-02", c=0.9, e=0.7654321),
            R(day="2030-11-20", c=5.0, e=5.0, jd=False),       # not judged: never learned from
            R(day="2030-12-20", c=-5.0, e=-5.0),               # judged but not settled by O (+ 30 days): not trained on
            R(day="2031-01-02", c=-6.0, e=-6.0)]               # after O
    g = be._rng(rows, O)
    assert g == [0.123456, 0.9, -0.5, 0.765433]                # (the young days being answered never widen it)
    assert be._seen(g, rows[0]) and be._seen(g, rows[1]) and not any(be._seen(g, x) for x in rows[2:])
    assert be._rng(rows[2:], O) is None and not be._seen(None, rows[0])     # nothing learned: no fit at all
    assert be._edge(g, rows[0]) == (rows[0].c, rows[0].e, 0.0)               # inside: no move
    # a row under $5 / 30 new users outside its range is not read past it ("data kam", as before): on a young day
    # where it alone has a benchmark it would otherwise stand for the whole app
    young = R(day=day, sp=1000.0, na=500.0, obs=0, oc=10.0)
    tiny = lambda jd: R(day=day, sp=0.5, na=5.0, cpi=0.01, c=math.log(0.01), e=math.log(3.0), jd=jd,   # noqa: E731
                        cum=[0.5] + [None] * 12, obs=0, oc=0.5)
    big = R(day=day, sp=999.5, na=495.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))                # (no benchmark)
    one = {"origin": "2031-01-01", "fits": {"AA": fc["fits"]["AA"]}}
    out = be.predict("k", one, cal, ("2030-12-31", [young], {day: {"AA": tiny(False), "ZB": big}}))["days"][0]
    assert "app" not in out and out["card"] is None and out["cw"] == "c" and out["cty"] == []
    assert sorted(u[0] for u in out["unc"]) == ["ZB", "…"] and out["cov"] == 0.0
    out = be.predict("k", one, cal, ("2030-12-31", [young], {day: {"AA": tiny(True), "ZB": big}}))["days"][0]
    assert [x[0] for x in out["cty"]] == ["AA"] and "app" in out                # judged: read at the edge


def test_the_back_tests_answer_a_country_outside_its_range_as_predict_does_and_k3_learns_only_inside(tmp_path,
                                                                                                      monkeypatch):
    """The two back-tests read the same curves as predict (_edge past the range): a narrower learned range answers the
    same days with the same countries (only how far each is moved changes), while K3's maps get only the rows inside."""
    site, data, dash = make(tmp_path)
    newest, app, cty = be.load(site, data, KEYS["a"], "roi_%s.json.gz" % KEYS["a"])
    A0, C0 = be.backtest(KEYS["a"], newest, app, cty, {})
    rb0, cb0, sk0, au0, n0, ga0, gc0 = be.asof(KEYS["a"], newest, app, cty, {})
    orig = be._rng

    def narrow(rows, O):
        g = orig(rows, O)
        if g is None:
            return None
        mc, me = (g[0] + g[1]) / 2, (g[2] + g[3]) / 2
        return [mc - 0.01, mc + 0.01, me - 0.01, me + 0.01]     # most days outside
    monkeypatch.setattr(be, "_rng", narrow)
    seen, orig_at = [], be.curve_at

    def rec(cf, g, x):                                          # every covered row read through the edge rule
        seen.append(be._seen(g, x))
        return orig_at(cf, g, x)
    monkeypatch.setattr(be, "curve_at", rec)
    A1, C1 = be.backtest(KEYS["a"], newest, app, cty, {})
    nb = len(seen)
    rb1, cb1, sk1, au1, n1, ga1, gc1 = be.asof(KEYS["a"], newest, app, cty, {})
    assert nb and not all(seen[:nb]) and len(seen) > nb and not all(seen[nb:])   # (outside rows too, in both)
    has = lambda A: [(x["X"], x["O"]) for x in A if x.get("a")]                    # noqa: E731
    assert has(A1) == has(A0) and len(has(A0)) >= 50                               # every day still answered
    assert any(x["a"]["roas"] != y["a"]["roas"] for x, y in zip(A0, A1) if x.get("a"))   # (moved, not dropped)
    assert 0 < len(C1) < len(C0)                                                   # K3: only the rows inside
    cnt = lambda E: {k: len(v) for k, v in E.items()}                              # noqa: E731
    assert n1 == n0 and cnt(rb1) == cnt(rb0) and cnt(cb1) == cnt(cb0) and cnt(gc1) == cnt(gc0)   # the same rows …
    assert any(sorted(rb1[k]) != sorted(rb0[k]) for k in rb0)                      # … read off the moved curves
    # one day by hand: the shift's app error at day 1 → 7 off the countries' curves at the edge (curve_at), as asof reads
    nw = date.fromisoformat(newest).toordinal()
    byday = {}
    for cc_, rows in cty.items():
        for x in rows:
            byday.setdefault(x.day, {})[cc_] = x
    F = {}
    r = next(r for r in app if be._usable(r) and r.cum and r.cum[1] and r.X + 6 + be.LAG <= nw and r.cum[4] is not None
             and any(cc_ in be._fits_at(cty, be._month(r.X + 1 + be.LAG), F) and not be._seen(
                 be._fits_at(cty, be._month(r.X + 1 + be.LAG), F)[cc_][2], x) for cc_, x in byday[r.day].items()
                 if x.c is not None and x.e is not None))
    cov = be._fits_at(cty, be._month(r.X + 1 + be.LAG), F)
    parts = [(x.sp,) + tuple(orig_at(cov[cc_][1], cov[cc_][2], x)[:2]) for cc_, x in byday[r.day].items()
             if cc_ in cov and x.c is not None and x.e is not None]
    ages, roas = be.combine(parts)
    ra = r.cum[1] / r.sp
    sh = be._bound(ages, be._shifted(ages, roas, 1, ra), 1, ra, be._gq(None, KEYS["a"], "app"))
    v6 = dict(be._after(ages, sh, 1, ra))[6]
    assert math.log(max(r.cum[4] / r.sp, be.ROAS_FLOOR) / v6) in [pytest.approx(e, abs=1e-12) for e in rb1[(1, 6)]]


def test_the_back_tests_skip_a_small_row_outside_its_range_as_predict_does(tmp_path):
    """The judged gate (_answers) holds in backtest() and asof() too: a covered country's row under $5 / 30 new users
    outside its learned range is not answered there ("data kam", as in predict) — the back-tests come out exactly as if
    the row were not there — while one inside its range still is."""
    site, data, dash = make(tmp_path)

    def run(c, e, drop):
        newest, app, cty = be.load(site, data, KEYS["a"], "roi_%s.json.gz" % KEYS["a"])
        days = set()
        for i, x in enumerate(cty["AA"]):
            if i >= 150 and i % 9 == 0:                         # (made small, as load() builds one: no cells)
                x.sp, x.n, x.jd, x.cpi, x.c = 2.0, 10, False, math.exp(c), c
                x.na = 2.0 / x.cpi
                if e is not None:
                    x.e = e
                x.cum = x.fin = x.dd = None
                days.add(x.day)
        if drop:
            cty["AA"] = [x for x in cty["AA"] if x.day not in days]
        A, C = be.backtest(KEYS["a"], newest, app, cty, {})
        rb, cb, sk, au, n, ga, gc = be.asof(KEYS["a"], newest, app, cty, {})
        norm = lambda E: {k: sorted(v) for k, v in E.items()}             # noqa: E731
        return A, C, norm(rb), norm(cb), sk, au, n, norm(ga), norm(gc)
    assert run(math.log(0.01), None, False) == run(math.log(0.01), None, True)          # outside: as if not there
    inn, gone = run(math.log(0.5), math.log(5.0), False), run(math.log(0.5), math.log(5.0), True)
    assert inn[0] != gone[0] and inn[2] != gone[2]                                       # inside: answered


def _one(fc_fits, cal, app_row, cs, day="2030-12-30"):
    fc = {"origin": "2031-01-01", "fits": fc_fits}
    return be.predict("k", fc, cal, ("2030-12-31", [app_row], {day: cs}))["days"][0]


CAL0 = {"built": "2031-01-01", "cty": {str(H): [[0.0, 0.0], [1.0, 1.0]] for H in be.HS},
        "pit": {"0.1": 0.1, "0.5": 0.5, "0.9": 0.9}, "band": {}, "cv": be.CALV}       # (a calibration with the shift's parts)


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
    assert full[7:12] == [0, 0, 0, 360, 0]                      # (a flat 150 % curve: its spend back on day 0)
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
    assert capsys.readouterr().err.count("be skipped: ValueError") == 1 and _l4(be.pop_line()).endswith("calib no")
    with open(os.path.join(data, "be_tab", "calib.json"), encoding="utf-8") as f:
        kept = json.load(f)
    same = lambda c: {k: v for k, v in c.items() if k not in ("tried", "skill")}    # noqa: E731
    assert same(kept) == same(good)                                      # the last good maps and ranges stay …
    b = body_of(site, "a")                                               # … the skill: this build's own (asof ran)
    assert b["calib"] == TODAY.isoformat() and b["skill"] == kept["skill"][KEYS["a"]] and d2["be"]["calib"] == TODAY.isoformat()
    assert isinstance(b["skill"]["c"], list)


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
        assert _one(fits, cal, row, cs)["cty"][0][7:12] == [0, 0, 0, 360, 0]       # (never a crash; the curve's day)
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
    assert dn["real"] == real and a["roas"] == real and a["anc"] == 360           # real everywhere …
    assert a["lo"] == a["hi"] == real                                             # … no spread where it has lived
    assert a["be"] == [None, None, None]                                           # never reached 100 % in its 360 days
    d17 = "2030-12-14"                     # (17 days old: its day-14 cell is 4 days old — the shift reads it)
    young = R(day=d17, sp=100.0, na=50.0, cum=[100.0 * v for v in real[:6]] + [None] * 7, obs=13, oc=25.0)
    dy = _one(fits, CAL0, young, {"AA": R(day=d17, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))},
              day=d17)
    y = dy["app"]                          # lived: real; after: the model's GROWTH from its final read (flat here: none)
    assert dy["real"] == real[:6] and y["roas"][:6] == real[:6] and y["roas"][6:] == [0.25] * 7 and y["anc"] == 13
    assert y["be"] == [None, None, None]   # (a flat model never lifts a day at 25 % to 100 % — not its 120 % level)
    fresh = R(day=day, sp=100.0, na=50.0, cum=[5.0] + [None] * 12, obs=0, oc=5.0, fin=[None] * 13)   # nothing final yet
    f = _one(fits, CAL0, fresh, cs)["app"]
    assert "anc" not in f and f["roas"][1:] == [1.2] * 12 and 0 < f["be"][0] <= 1   # unshifted: the model as it is
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
    assert 201 <= got[1] < got[0] < got[2] and got[3:5] == [360, 0]   # its curve given 80 % by day 200: a real band past it
    assert _one(fits, CAL0, old, {"AA": broke})["cty"][0][7:12] == [12, None, None, 360, 1]   # its real day, no range


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
    a = _one(fits, CAL0, row, cs)["app"]   # (the model said 2.3 at 360; shifted from its real 270: × 2.3 ÷ 2.2)
    assert a["roas"][11] == 2.4045 and a["roas"][12] == round(2.4045 * 2.3 / 2.2, 4) and a["anc"] == 270
    flat = [[j, [math.log(v), 0.0, 0.0], -0.2, 0.2, 40, math.log(v)] for j, v in
            enumerate([0.3, 0.4, 0.5, 0.6, 0.7, 0.9, 1.1, 1.4, 1.7, 1.9, 2.1, 2.3, 2.2])]      # a model dipping at 360
    fits2 = {"AA": dict(fits["AA"], cv=flat)}
    a2 = _one(fits2, CAL0, row, cs)["app"]
    assert a2["roas"][12] >= a2["roas"][11] == 2.4045                             # never below the real one before it


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



# ── the "ROAS ab tak" shift (owner, 15 Nov 2026: "haan, pehle backtest karke dikhao" → "haan live karo") ───────────

UP = [0.3, 0.35, 0.4, 0.42, 0.46, 0.54, 0.67, 0.84, 0.95, 1.4, 1.5, 1.6, 1.7]   # a growing model at the 13 grid ages


def _up_fits():
    cv = [[j, [math.log(v), 0.0, 0.0], -0.2, 0.2, 40, math.log(v)] for j, v in enumerate(UP)]
    return {"AA": {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": cv, "rng": WIDE}}


def test_the_shift_moves_the_curve_to_what_the_day_really_made():
    """A day at 1.5 × its model by day 14 (its latest final grid age, 13): after it, the model's GROWTH times what it made
    (UP(t) ÷ UP(13) × 81 %) — 100 % by day 30 (the unshifted curve: day 94); one at 0.5 × lags the same way: past its
    curve, never "day 94". The range: the shift's own errors at that age (bandb)."""
    day = "2030-12-14"                     # (17 days old: its day-14 cell is 4 days old — the shift reads it)
    cs = {"AA": R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))}
    i13, i30 = be.GRID.index(13), be.GRID.index(30)
    ahead = R(day=day, sp=100.0, na=50.0, cum=[150.0 * v for v in UP[:6]] + [None] * 7, obs=13, oc=81.0)
    bb = {"13": {str(t): [0.0, math.log(0.8), math.log(1.25), 99] for t in be.GRID if t > 13}}
    a = _one(_up_fits(), dict(CAL0, bandb=bb), ahead, cs, day=day)["app"]
    assert a["anc"] == 13 and a["roas"][i13] == 0.81 and a["roas"][i30] == round(0.81 * 0.67 / 0.54, 4)
    assert a["be"][0] == 30 and a["be"][1] < 30 < a["be"][2]                      # the range around it
    assert a["lo"][i30] == 0.81 and a["hi"][i30] == round(0.81 * 0.67 / 0.54 * 1.25, 4)   # (the low end: never below
    assert a["lo"][be.GRID.index(60)] == round(0.81 * 0.84 / 0.54 * 0.8, 4)                # what it made: 80.4 → 81 %)
    plain = _one(_up_fits(), dict(CAL0, bandb=bb), R(day=day, sp=100.0, na=50.0, cum=[150.0 * v for v in UP[:6]] +
                                                     [None] * 7, obs=13, oc=81.0, fin=[None] * 13), cs, day=day)["app"]
    assert "anc" not in plain and plain["be"][0] == 94                           # (unshifted: max(model, so far))
    behind = R(day=day, sp=100.0, na=50.0, cum=[50.0 * v for v in UP[:6]] + [None] * 7, obs=13, oc=27.0)
    b = _one(_up_fits(), CAL0, behind, cs, day=day)["app"]
    fresh = R(day="2030-12-15", sp=100.0, na=50.0, cum=[150.0 * v for v in UP[:6]] + [None] * 7, obs=13, oc=81.0)
    f = _one(_up_fits(), dict(CAL0, bandb=bb), fresh, {"AA": cs["AA"]}, day="2030-12-15")["app"]
    assert f["anc"] == 6                   # 16 days old: its day-14 cell is only 3 days old (often still empty) → day 7
    assert b["roas"][-1] == round(0.27 * 1.7 / 0.54, 4) < 1 and b["be"][0] is None  # 85 % by day 360: beyond data
    assert "lo" in b and all(v is None for v in b["lo"][i13 + 1:])                 # (no band at its age: no range)


def _days(n, r0, last=None, age0=40):
    """n consecutive install days (oldest first), each final through day 1 only (anchor 0), its day-0 ROAS r0 (the last
    one's: last)."""
    out, cs = [], {}
    for i in range(n):
        d = (date(2030, 12, 31) - timedelta(days=age0 + n - 1 - i)).isoformat()
        v = last if (last is not None and i == n - 1) else r0
        out.append(R(day=d, sp=100.0, na=50.0, cum=[100.0 * v] + [None] * 12, obs=0, oc=100.0 * v))
        cs[d] = {"AA": R(day=d, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))}
    return out, cs


def _many(rows, cs, cal=None):
    fc = {"origin": "2031-01-01", "fits": _up_fits()}
    return be.predict("k", fc, cal or CAL0, ("2030-12-31", rows, cs))["days"]


def test_a_country_is_shifted_on_its_own_read_with_the_range_for_its_size():
    """A country at 1.5 × its curve by day 14: its day off its own SHIFTED curve; its range from the shift's errors for its
    size bucket (40 new users: "0"), a bigger row with no bucket of its own takes every size pooled ("all")."""
    day = "2030-12-14"                                     # 17 days before the newest: its day-13 cell is 4 days old
    row = R(day=day, sp=100.0, na=50.0, cum=[150.0 * v for v in UP[:6]] + [None] * 7, obs=13, oc=81.0)
    cb = {"13": {str(t): {"0": [0.0, math.log(0.5), math.log(2.0), 99], "all": [0.0, math.log(0.9), math.log(1.1), 99]}
                 for t in be.GRID if t > 13}}
    cal = dict(CAL0, cbandb=cb)
    out = {}
    for n in (40, 500):
        x = R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0), n=n,
              cum=[150.0 * v for v in UP[:6]] + [None] * 7, obs=13, oc=81.0)
        out[n] = _one(_up_fits(), cal, row, {"AA": x}, day=day)["cty"][0][7:]
    small, big = out[40], out[500]
    assert small[0] == big[0] == 30 and small[3:5] == big[3:5] == [360, 0]          # the same shifted median
    assert small[1] < big[1] <= 30 <= big[2] < small[2]                          # the small row's range is wider
    x0 = R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0), n=40,
           cum=[150.0 * v for v in UP[:6]] + [None] * 7, obs=13, oc=81.0, fin=[None] * 13)
    assert _one(_up_fits(), cal, row, {"AA": x0}, day=day)["cty"][0][7] == 94    # nothing final: its curve unshifted
    # a country's daily cell 3 days old is often still empty (its split lags): the shift waits a day more (CLAG) —
    # 16 days old, its day-13 cell is 3 days old: shifted at day 7 (age 6) instead, never on that cell
    d2 = "2030-12-15"
    x3 = R(day=d2, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0), n=40,
           cum=[150.0 * v for v in UP[:5]] + [100.0 * UP[5]] + [None] * 7, obs=13, oc=54.0)   # (day 14: the empty cell)
    row2 = R(day=d2, sp=100.0, na=50.0, cum=[150.0 * v for v in UP[:6]] + [None] * 7, obs=13, oc=81.0)
    cb6 = {"6": cb["13"]}
    got = _one(_up_fits(), dict(CAL0, cbandb=cb6), row2, {"AA": x3}, day=d2)["cty"][0][7]
    assert got is not None and got < 94                       # its day-7 read (1.5 ×) shifts it, the empty cell does not


def test_the_shifts_fits_never_read_past_their_moment(tmp_path):
    """Every cell observed after a cut-off date multiplied by 1.37 (the app's rows and its country rows): every fit the
    shift's back-test answers with at a month start up to the cut-off (asof: the month start of install day + a + LAG) is
    exactly the same — the fits, the ranges and the anchors read nothing later — while the later ones do change."""
    site, data, dash = make(tmp_path)
    key, fn = KEYS["a"], "roi_%s.json.gz" % KEYS["a"]
    cut = date.fromordinal(TODAY.toordinal() - 120)

    def fits():
        newest, app, cty = be.load(site, data, key, fn)
        out = {}
        for O in sorted({be._month(o) for o in range(DAY0.toordinal() + 60, TODAY.toordinal())}):
            out[O] = json.dumps({cc: [v[0], v[1], v[2]] for cc, v in be._fits_at(cty, O).items()}, sort_keys=True,
                                default=list)
        return out
    before = fits()

    def bump(rows):
        for r in rows:
            X = date.fromisoformat(r[0])
            r[4] = [v * 1.37 if X + timedelta(days=a) > cut else v for a, v in enumerate(r[4])]
            if len(r) > 14 and r[14]:
                r[14] = [v * 1.37 if X + timedelta(days=30 * (i + 2)) > cut else v for i, v in enumerate(r[14])]
            r[8] = r[4][-1] if r[4] else r[8]
    for f in (fn, "roi_%s_c00.json.gz" % key):
        p = os.path.join(site, f)
        with gzip.open(p, "rt", encoding="utf-8") as h:
            body = json.load(h)
        for rows in ([body["rows"]] if "rows" in body else body["c"].values()):
            bump(rows)
        with gzip.open(p, "wt", encoding="utf-8") as h:
            json.dump(body, h)
    after = fits()
    upto = [O for O in before if O <= cut.toordinal()]
    later = [O for O in before if O > cut.toordinal() + 31]
    assert len(upto) >= 12 and len(later) >= 2
    assert all(before[O] == after[O] for O in upto)                              # nothing after the moment reached them
    assert any(before[O] != after[O] for O in later)                             # (the bump is real where it may act)


def test_the_shifts_ranges_need_enough_days_and_pool_the_sizes():
    from array import array
    RB = {(6, 30): array("d", [0.01 * i for i in range(60)]), (6, 90): array("d", [0.0] * 49)}
    CB = {(13, 90, 0): array("d", [0.02 * i for i in range(30)]), (13, 90, 3): array("d", [0.01 * i for i in range(60)])}
    bb, cb = be.bands(RB, CB)
    assert set(bb) == {"6"} and set(bb["6"]) == {"30"}                            # 49 errors at 90: no range
    m, q10, q90, n = bb["6"]["30"]
    assert n == 60 and q10 < m < q90 and m == pytest.approx(0.295) and q10 == pytest.approx(0.059)
    assert set(cb["13"]["90"]) == {"3", "all"} and cb["13"]["90"]["all"][3] == 90   # bucket 0 (30): only in "all"


def test_a_calibration_without_the_shifts_ranges_is_made_again_the_same_day(tmp_path):
    site, data, dash = make(tmp_path)
    be.run(dash, data, site, {}, NOW)
    be.pop_line()
    p = os.path.join(data, "be_tab", "calib.json")
    with open(p, encoding="utf-8") as f:
        cal = json.load(f)
    old = {k: v for k, v in cal.items() if k not in ("cv", "bandb", "cbandb")}      # (an older build's file)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(old, f)
    d2 = copy.deepcopy(dash)
    be.run(d2, data, site, {}, NOW + timedelta(hours=2))
    assert _l4(be.pop_line()).endswith("refit no, calib yes")
    with open(p, encoding="utf-8") as f:
        assert json.load(f)["cv"] == be.CALV


def test_a_failed_remake_after_calv_moved_keeps_the_last_good_one_shifting_and_tries_again(tmp_path, monkeypatch, capsys):
    """CALV moved past a calibration that already carries the shift's parts (cv ≥ SHIFT_CV): if the remake fails, the
    days stay shifted on the kept one (never every app's shift off for a failed remake), and every build tries again."""
    site, data, dash = make(tmp_path)
    be.run(dash, data, site, {}, NOW)
    be.pop_line()
    shifted = sum("anc" in (d.get("app") or {}) for d in body_of(site, "a")["days"])
    p = os.path.join(data, "be_tab", "calib.json")
    with open(p, encoding="utf-8") as f:
        cal = json.load(f)
    first_skill = cal["skill"]
    sentinel = {k: {"auc": [1.0] * 3, "c": [1.0] * 3, "n": 1} for k in cal["skill"]}
    with open(p, "w", encoding="utf-8") as f:                                    # (an older content with the parts)
        json.dump(dict(cal, cv=be.SHIFT_CV, skill=sentinel), f)
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        return 1 / 0
    monkeypatch.setattr(be, "calibrate", boom)
    capsys.readouterr()
    assert be.run(copy.deepcopy(dash), data, site, {}, NOW + timedelta(hours=3)) == ["/be_*"]
    assert _l4(be.pop_line()).endswith("calib no") and "be skipped: ZeroDivisionError" in capsys.readouterr().err
    assert shifted and sum("anc" in (d.get("app") or {}) for d in body_of(site, "a")["days"]) == shifted
    b_skill = body_of(site, "a")["skill"]
    assert b_skill != sentinel[KEYS["a"]] and b_skill["n"] > 1                    # this build's own skill, not the kept
    with open(p, encoding="utf-8") as f:
        kept = json.load(f)
    assert kept["cv"] == be.SHIFT_CV and kept["skill"][KEYS["a"]] == b_skill and set(kept["skill"]) == set(first_skill)
    be.run(copy.deepcopy(dash), data, site, {}, NOW + timedelta(hours=4))
    assert calls["n"] == 2                                                       # (tried again on the next build)
    be.pop_line()
    assert be._shifts({"cv": be.CALV}) and not be._shifts({"cv": be.SHIFT_CV - 1}) and not be._shifts({})
    assert not be._shifts({"cv": True}) and not be._shifts(None)


def test_a_skill_kept_from_before_the_shift_passes_through_as_it_was():
    """A calibration kept from before the shift (its new one failed) carries one install-time C (a number): the file keeps
    it as it was — the page reads that shape with its own old words — never the old AUC under the new day labels."""
    fc = {"origin": "2031-01-01", "fits": {}}
    row = R(day="2030-12-30", sp=100.0, na=50.0, obs=0, oc=10.0)
    old = {"auc": [80.0, 60.0, 45.0], "c": 55.0, "n": 600}
    got = be.predict("k", fc, CAL0, ("2030-12-31", [row], {}), old)["skill"]
    assert got == {"auc": [80.0, 60.0, 45.0], "c": 55.0, "n": 600}
    new = be.predict("k", fc, CAL0, ("2030-12-31", [row], {}), {"auc": [None] * 3, "c": [90.0, None, 95.0], "n": 9})
    assert new["skill"] == {"auc": [None] * 3, "c": [90.0, None, 95.0], "n": 9}
    assert be.predict("k", fc, CAL0, ("2030-12-31", [row], {}))["skill"]["c"] == [None] * 3


def test_a_failing_first_calibration_after_the_shift_keeps_the_unshifted_curve_and_its_old_skill(tmp_path, monkeypatch,
                                                                                                   capsys):
    """The first build after the shift ships finds a calibration from before it (no shift ranges, no growth bound, one
    install-time C per app) and its new calibration fails: no day is shifted without the shift's parts — the unshifted
    curve with its band, and the old skill as it was (the page reads that shape with its old words) — and the next build
    tries again (no "cv" stamped)."""
    site, data, dash = make(tmp_path)
    be.run(dash, data, site, {}, NOW)
    be.pop_line()
    p = os.path.join(data, "be_tab", "calib.json")
    with open(p, encoding="utf-8") as f:
        cal = json.load(f)
    old = {k: v for k, v in cal.items() if k not in ("cv", "bandb", "cbandb", "grow")}   # (a pre-shift file)
    old["skill"] = {k: {"auc": [80.0, 60.0, 45.0], "c": 55.0, "n": 600} for k in cal["skill"]}
    with open(p, "w", encoding="utf-8") as f:
        json.dump(old, f)
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        return 1 / 0
    monkeypatch.setattr(be, "calibrate", boom)
    capsys.readouterr()
    d2 = copy.deepcopy(dash)
    assert be.run(d2, data, site, {}, NOW + timedelta(hours=3)) == ["/be_*"]
    assert _l4(be.pop_line()).endswith("calib no") and "be skipped: ZeroDivisionError" in capsys.readouterr().err
    b = body_of(site, "a")
    assert b["skill"] == {"auc": [80.0, 60.0, 45.0], "c": 55.0, "n": 600}
    assert not any("anc" in (d.get("app") or {}) for d in b["days"])            # nothing shifted without its parts
    with open(p, encoding="utf-8") as f:
        assert "cv" not in json.load(f)
    be.run(copy.deepcopy(dash), data, site, {}, NOW + timedelta(hours=5))
    assert calls["n"] == 2                                                       # (tried again on the next build)
    be.pop_line()


def _cohorts(n, hole=None, weak=None, last=date(2030, 12, 31)):
    """n consecutive install days (oldest first) ending CLAG days before `last`, each earning 30 on its install day and
    1 a day after (daily cells final through day 30 or its age − LAG); on the calendar date `hole` every cohort earns 0
    that day; the install day `weak` earns a tenth of everyone else (a weak day, not a hole)."""
    rows = []
    for i in range(n):
        X = last - timedelta(days=be.CLAG + n - 1 - i)
        k = 0.1 if weak is not None and X == weak else 1.0
        dd, c = [], 0.0
        for a in range(min(31, (last - X).days - be.LAG + 1)):
            if not (hole is not None and X + timedelta(days=a) == hole):
                c += (30.0 if a == 0 else 1.0) * k
            dd.append(c)
        rows.append(R(day=X.isoformat(), sp=100.0, na=50.0, dd=dd))
    return rows


def _adm(low=None):
    """AdMob's own revenue of every day (100 USD), the date `low` at 5 (a real outage)."""
    d0 = date(2030, 9, 1).toordinal()
    return {o: (5.0 if low is not None and o == low.toordinal() else 100.0) for o in range(d0, d0 + 130)}


def test_a_hole_is_a_calendar_date_ga4_lost_on_every_cohort_never_a_weak_day_or_a_real_outage():
    """_holes: the older cohorts (7–30 days old: their revenue does not move with the day's spend) together earning near
    nothing on one date while AdMob's own revenue was normal is a GA4 hole; one install day earning little is a weak
    day; a date AdMob lost too is a real outage (its numbers are true); no AdMob read: no hole claimed."""
    nw = date(2030, 12, 31).toordinal()
    hole = date(2030, 12, 1)
    assert be._holes(_cohorts(60, hole=hole), nw, _adm()) == {hole.toordinal()}
    assert be._holes(_cohorts(60, hole=hole), nw, _adm(low=hole)) == set()        # AdMob lost it too: a real outage
    assert be._holes(_cohorts(60, hole=hole), nw) == set()                        # (no AdMob read: no claim)
    assert be._holes(_cohorts(60, weak=date(2030, 12, 1)), nw, _adm()) == set()  # one weak install day: no hole
    assert be._holes(_cohorts(60), nw, _adm()) == set()
    few = _cohorts(14, hole=date(2030, 12, 25))                                  # 5 older cohorts on that date
    half = {k: v / 2 for k, v in _adm().items()}
    assert be._holes(few, nw, half) == set()                                     # (< HOLE_MIN: no claim …)
    hm = be.HOLE_MIN
    try:
        be.HOLE_MIN = 1
        assert be._holes(few, nw, half) == {date(2030, 12, 25).toordinal()}     # (… that is the only reason)
    finally:
        be.HOLE_MIN = hm
    long = _cohorts(60)
    for x in long:                         # a 6-day hole: every date of it, never its own baseline
        X = date.fromisoformat(x.day)
        c, dd = 0.0, []
        for a in range(len(x.dd)):
            if not date(2030, 12, 1) <= X + timedelta(days=a) <= date(2030, 12, 6):
                c += 30.0 if a == 0 else 1.0
            dd.append(c)
        x.dd = dd
    assert be._holes(long, nw, _adm()) == {date(2030, 12, d).toordinal() for d in range(1, 7)}
    big = {k: v * 20 for k, v in _adm().items()}                                 # paid cohorts ~1 % of AdMob's revenue
    assert be._holes(_cohorts(60, hole=hole), nw, big) == set()                  # (too small a signal to call a hole)


def test_a_day_with_a_hole_in_its_first_week_says_data_check_and_stays_shifted():
    """The days whose first 7 days hold a hole date carry "chk" (the page: "data check" — their real ROAS is low by
    what the data lost); their forecast stays the shift (measured against the recorded data, falling back to the
    unshifted curve cost accuracy). Days before and after that window: no mark."""
    hole = date(2030, 11, 20)
    rows = _cohorts(60, hole=hole)
    for x in rows:                         # (their model view: final grid cells from the daily ones)
        x.cum = [x.dd[a] if a < len(x.dd) else None for a in be.GRID]
        x.fin = list(x.cum)
        x.obs = max(a for a in be.GRID if a < len(x.dd))
        x.oc = x.dd[x.obs]
        x.sfa, x.sfv = x.obs, x.oc
    cs = {x.day: {"AA": R(day=x.day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))} for x in rows}
    fc = {"origin": "2031-01-01", "fits": _up_fits()}
    out = {d["d"]: d for d in be.predict("k", fc, CAL0, ("2030-12-31", rows, cs, _adm()))["days"]}
    assert not any(d.get("chk") for d in _many(rows, cs))                       # (no AdMob read: no mark)
    marked = sorted(d for d, x in out.items() if x.get("chk"))
    want = sorted((hole - timedelta(days=k)).isoformat() for k in range(be.HOLE_W)
                  if "anc" in out[(hole - timedelta(days=k)).isoformat()]["app"])
    assert marked == want and len(marked) >= 5                                    # its first 7 days held the hole
    assert all("anc" in out[d]["app"] for d in marked)                           # … still shifted


def test_the_shifts_growth_never_leaves_what_real_days_grew():
    """A model read far outside its inputs can claim growth no real install day had (×1.5 from day 90 to 120 where real
    days grew ≤ ×1.2): the shift's growth stays inside the 1st / 99th percentile of the apps' real growth at that step
    (calib "grow")."""
    ages = [0, 1, 2, 3, 6, 13, 30, 60, 90, 120]
    vals = [0.1, 0.12, 0.13, 0.14, 0.16, 0.2, 0.3, 0.4, 0.5, 0.75]              # ×1.5 from 90 to 120
    gq = {"90": {"120": [0.0, math.log(1.2), 500]}}
    got = be._bound(ages, be._shifted(ages, vals, 90, 0.7), 90, 0.7, gq)
    assert got[-1] == pytest.approx(0.7 * 1.2) and got[ages.index(90)] == pytest.approx(0.7)
    low = be._bound(ages, be._shifted(ages, [v if t != 120 else 0.5 for t, v in zip(ages, vals)], 90, 0.7), 90,
                    0.7, {"90": {"120": [math.log(1.02), math.log(1.2), 500]}})
    assert low[-1] == pytest.approx(0.7 * 1.02)                                   # (a flat model: at least the 1st %)
    assert be._bound(ages, None, 90, 0.7, gq) is None


def test_the_day_7_auc_and_the_country_ranges_leave_out_what_had_already_broken_even(tmp_path, monkeypatch):
    """On day 7 a day that had already broken even shows its real day, never a forecast: it is not an AUC point (a free
    right answer) — nor, at its age, a country range error or a ranking row (_open)."""
    assert be._open(R(hi=None), 6) and be._open(R(hi=7), 6) and not be._open(R(hi=6), 6) and not be._open(R(hi=2), 6)
    site, data, dash = make(tmp_path)
    newest, app, cty = be.load(site, data, KEYS["a"], "roi_%s.json.gz" % KEYS["a"])
    use = [r for r in app if be._usable(r) and r.X + 200 < date.fromisoformat(newest).toordinal()]
    for r in use[::20]:                    # (a few old days made early breakers: back on day 3)
        r.hi, r.be = 3, 3.0
    seen = []
    orig = be._mature
    monkeypatch.setattr(be, "_mature", lambda age, hi, obs, H: seen.append(hi) or orig(age, hi, obs, H))
    be.asof(KEYS["a"], newest, app, cty, {})
    assert len(use[::20]) >= 10 and seen and all(h is None or h > be.AUC_A for h in seen)   # (left out of the AUC)


def test_the_growth_bound_is_the_apps_own_widened_by_every_apps_and_predict_uses_it():
    """An app whose days really grow faster keeps its own room (its q99 above the pooled one), a model read far outside
    every app's experience is still held: _gq takes the wider of the two; predict bounds the app line and each
    country with it."""
    grow = {"app": {"13": {"30": [0.0, math.log(1.2), 900]}}, "cty": {"13": {"30": [0.0, math.log(1.1), 900]}},
            "apps": {"k": {"app": {"13": {"30": [math.log(1.05), math.log(1.6), 80]}}}}}
    assert be._gq(grow, "k", "app") == {"13": {"30": [0.0, math.log(1.6), 900]}}
    assert be._gq(grow, "other", "app") == {"13": {"30": [0.0, math.log(1.2), 900]}}
    assert be._gq(None, "k", "cty") == {}
    day = "2030-12-14"
    cs = {"AA": R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0), n=40,
                  cum=[150.0 * v for v in UP[:6]] + [None] * 7, obs=13, oc=81.0)}
    row = R(day=day, sp=100.0, na=50.0, cum=[150.0 * v for v in UP[:6]] + [None] * 7, obs=13, oc=81.0)
    free = _one(_up_fits(), CAL0, row, cs, day=day)
    held = _one(_up_fits(), dict(CAL0, grow={"app": {"13": {"30": [0.0, math.log(1.1), 900]}},
                                             "cty": {"13": {"30": [0.0, math.log(1.1), 900]}}}), row, cs, day=day)
    i30 = be.GRID.index(30)
    assert free["app"]["roas"][i30] == round(0.81 * 0.67 / 0.54, 4)               # × 1.24 unbounded
    assert held["app"]["roas"][i30] == round(0.81 * 1.1, 4)                       # × 1.1 at most
    assert held["cty"][0][7] > free["cty"][0][7]                                   # (the country bounded too: later)


def test_growth_keeps_the_1st_and_99th_percentile_of_enough_days():
    from array import array
    GA = {(6, 30): array("d", [math.log(1.0 + 0.01 * i) for i in range(100)]), (6, 90): array("d", [0.1] * 49)}
    g = be.growth(GA, {})
    assert set(g) == {"app", "cty"} and g["cty"] == {} and set(g["app"]["6"]) == {"30"}       # (49 days: no bound)
    lo, hi, n = g["app"]["6"]["30"]
    assert n == 100 and lo == pytest.approx(math.log(1.0099), abs=1e-4) and hi == pytest.approx(math.log(1.9801), abs=1e-4)


def test_the_ranking_and_the_country_ranges_also_leave_out_rows_broken_even_by_then(tmp_path):
    """The same _open filter as the day-7 AUC: an install day already broken even by a is no ranking row at a, and a
    country row broken even by a gives no range error at a (the page shows their real days)."""
    site, data, dash = make(tmp_path)
    newest, app, cty = be.load(site, data, KEYS["a"], "roi_%s.json.gz" % KEYS["a"])
    rb, cb, sk, au, n, ga, gc = be.asof(KEYS["a"], newest, app, cty, {})
    nsk, ncb = len(sk[6]), sum(len(v) for (a, t, z), v in cb.items() if a == 6)
    nw = date.fromisoformat(newest).toordinal()
    old = [r for r in app if be._usable(r) and r.X + 200 < nw and r.hi is None or (r.hi is not None and r.hi > 6)][::25]
    for r in old:
        r.hi, r.be = 3, 3.0
    oc = [x for rows in cty.values() for x in rows if x.jd and x.X + 200 < nw and (x.hi is None or x.hi > 6)][::25]
    for x in oc:
        x.hi, x.be = 3, 3.0
    rb, cb, sk, au, n, ga, gc = be.asof(KEYS["a"], newest, app, cty, {})
    assert len(old) >= 10 and len(sk[6]) < nsk                                    # those days: no ranking row on day 7
    assert len(oc) >= 10 and sum(len(v) for (a, t, z), v in cb.items() if a == 6) < ncb   # … and no range error


# ── the country benchmark (owner, 15 Nov 2026: "haan dono karo") ────────────────────────────────────────────────────

def test_the_kaplan_meier_median():
    """No censoring: the plain median event time; a censored day moves it later (it stays at risk until its time);
    S never reaching 0.5: null; a day censored AT an event time is still at risk then."""
    assert be.km_median([(t, True) for t in (1.0, 2.0, 3.0, 4.0, 5.0)]) == 3.0
    assert be.km_median([(t, True) for t in (1.0, 2.0, 3.0)]) == 2.0
    cens = [(1.0, True), (2.0, True), (3.0, True), (1.5, False), (10.0, False), (10.0, False)]
    assert be.km_median(cens) == 3.0 > be.km_median(cens[:3])        # S: 5/6, then ×3/4 = 0.625, then ×2/3 = 0.417
    assert be.km_median([(1.0, True), (5.0, False), (5.0, False), (5.0, False), (5.0, False)]) is None   # S = 0.8
    assert be.km_median([(2.0, True), (2.0, False)]) == 2.0          # (the censored day at 2 is at risk: S = 0.5)
    assert be.km_median([(2.0, False), (3.0, False)]) is None and be.km_median([]) is None
    assert be.km_median([(1, True), (1, True), (2, True), (3, False)]) == 1      # tied events: S(1) = 1 − 2/4 = 0.5
    assert be.km_median([(1, True), (1, False), (2, True), (3, True)]) == 2      # a tie of an event and a censored day


def _train(rows, O):
    """K3's own training set at O, rebuilt from the public pieces (bot-kept events + the not-yet days)."""
    obs = [(r,) + be.at_origin(r, O) for r in rows if r.X < O and be._usable(r) and be.at_origin(r, O) is not None]
    kept, _ = be.bot([r for r, k, _ in obs if k == "e"])
    return [(r, True, r.be) for r in kept] + [(r, False, t) for r, k, t in obs if k == "c"]


def test_the_benchmark_triple_is_k3s_own_training_set_in_the_fits_and_at_index_12_of_the_cty_rows(built):
    site, data = built["site"], built["data"]
    newest, app, cty = be.load(site, data, KEYS["a"], "roi_%s.json.gz" % KEYS["a"])
    O = TODAY.toordinal()
    with gzip.open(be._fits_path(data, KEYS["a"]), "rt") as f:
        fc = json.load(f)
    for cc in CTY:
        tr = _train(cty[cc], O)
        k3 = be.k3_fit(cty[cc], O)
        want = [round(math.exp(be._median([r.c for r, _, _ in tr])), 4),
                round(math.exp(be._median([r.e for r, _, _ in tr])), 3),
                be._r(be.km_median([(t, e) for _, e, t in tr]), 1), round(k3["tmax"])]
        assert fc["fits"][cc]["bm"] == want and k3["bm"][3] == want[3]
        assert any(not e for _, e, _ in tr)                           # (the not-yet days are in it, censored)
    for d in body_of(site, "a")["days"]:
        for x in d["cty"]:
            assert x[12] == fc["fits"][x[0]]["bm"]
    old = {"origin": "2031-01-01", "fits": {"AA": dict(_up_fits()["AA"])}}      # a cache from before: no triple
    rows = R(day="2030-12-30", sp=100.0, na=50.0, obs=0, oc=1.0)
    cs = {"AA": R(day="2030-12-30", sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0))}
    assert be.predict("k", old, CAL0, ("2030-12-31", [rows], {"2030-12-30": cs}))["days"][0]["cty"][0][12] is None
    for bad in ([1.0, 2.0, None], "x", [1.0, 2.0, "n", 3], [None, 2.0, 3.0, 4]):
        old["fits"]["AA"]["bm"] = bad
        assert be.predict("k", old, CAL0, ("2030-12-31", [rows], {"2030-12-30": cs}))["days"][0]["cty"][0][12] is None


def test_the_benchmark_triple_leaves_out_the_days_the_bot_drops():
    """A hand-made country: 40 ordinary real-BE days plus 4 planted outliers (far larger CPI / eCPM_fs and a BE the
    regression cannot explain) and 5 not-yet days. k3_fit drops the outliers, and bm is the medians and the Kaplan–Meier
    median of the KEPT events + the censored days — different from those of all the events."""
    O = date(2031, 1, 1).toordinal()
    rows = []

    def add(i, c, e, be):
        X = date.fromordinal(O - 400 + i)
        hi = be if be is not None else None
        rows.append(R(day=X.isoformat(), X=X.toordinal(), sp=50.0, na=25.0, c=c, e=e, lo=None if hi is None else hi - 1,
                      hi=hi, be=None if be is None else float(be), obs=None if be is not None else 40, jd=True))
    for i in range(40):
        c, e = 0.5 + 0.02 * (i % 9), -1.0 + 0.03 * (i % 7)
        add(i, c, e, int(round(math.exp(1.8 + 0.4 * c - 0.3 * e + 0.05 * math.sin(i * 7.0)))))
    for i in range(4):
        add(40 + i, 3.0 + 0.1 * i, 1.0 + 0.1 * i, 330 + i)                     # the planted outliers
    for i in range(5):
        X = date.fromordinal(O - 80 + i)                                         # not-yet days: no BE, 80 days lived
        rows.append(R(day=X.isoformat(), X=X.toordinal(), sp=50.0, na=25.0, c=0.6, e=-0.9, lo=None, hi=None, be=None,
                      obs=76, jd=True))
    rows.sort(key=lambda r: r.X)
    k3 = be.k3_fit(rows, O)
    assert k3 is not None and k3["dropped"] >= 1
    tr = _train(rows, O)
    ev = [r for r in rows if r.X < O and be.at_origin(r, O) and be.at_origin(r, O)[0] == "e"]
    allr = [(r, True, r.be) for r in ev] + [(r, False, t) for r, k, t in
                                            [(r,) + be.at_origin(r, O) for r in rows if be.at_origin(r, O)] if k == "c"]
    assert len(tr) < len(allr)

    def triple(t):
        return [math.exp(be._median([r.c for r, _, _ in t])), math.exp(be._median([r.e for r, _, _ in t])),
                be.km_median([(x, e) for _, e, x in t])]
    got, want, wrong = k3["bm"], triple(tr), triple(allr)
    assert got[0] == pytest.approx(want[0]) and got[1] == pytest.approx(want[1]) and got[2] == want[2]
    assert got[0] != pytest.approx(wrong[0]) or got[1] != pytest.approx(wrong[1]) or got[2] != wrong[2]


def test_a_fits_cache_without_fv_or_an_older_one_is_refitted_the_same_day(tmp_path):
    site, data, dash = make(tmp_path)
    assert be.run(dash, data, site, {}, NOW) == ["/be_*"]
    be.pop_line()
    path = be._fits_path(data, KEYS["a"])
    for fv in (None, 1):
        with gzip.open(path, "rt") as f:
            fc = json.load(f)
        assert fc["fv"] == 2
        fc.pop("fv")
        for v in fc["fits"].values():
            v.pop("bm")
        if fv:
            fc["fv"] = fv
        be.save_fits(data, KEYS["a"], fc)
        assert be.load_fits(data, KEYS["a"]) is not None                  # (older caches stay readable …)
        d2 = copy.deepcopy(dash)
        assert be.run(d2, data, site, {}, NOW) == ["/be_*"]
        assert _l4(be.pop_line()).endswith("refit yes, calib no")          # … they just refit, with the triple
        with gzip.open(path, "rt") as f:
            fc = json.load(f)
        assert fc["fv"] == 2 and all(len(v["bm"]) == 4 for v in fc["fits"].values())
    d3 = copy.deepcopy(dash)
    be.run(d3, data, site, {}, NOW)
    assert _l4(be.pop_line()).endswith("refit no, calib no")


def _card_world(specs, day="2030-12-14", gaps=(), whole=False, jd=True):
    """specs {cc: (spend, cum at j 0..5, fin at j 0..5, curve medians log at j 0..5 or None for no entry, covered (a
    benchmark)? — True, False (none) or "out" (one whose learned range the day's CPI / eCPM_fs is outside)[, small?])}
    → the card of one install day through predict() (whole: the day's body; small: a row under $5 / 30 new users — it
    carries only its card cells kc / kf, like load() builds it)."""
    fits, cs = {}, {}
    for cc, (sp, cum, fin, med, ok, *sm) in specs.items():
        cv = [[j, [m, 0.0, 0.0], -0.2, 0.2, 40, m] for j, m in enumerate(med) if m is not None]
        if ok:                             # (no benchmark: no fit — a CPI / eCPM_fs outside the range is covered now)
            fits[cc] = {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": cv,
                        "rng": [9, 9, 9, 9] if ok == "out" else WIDE}
        if sm and sm[0]:
            cs[cc] = R(day=day, sp=sp, na=sp / 2, cpi=2.0, c=math.log(2.0), e=math.log(3.0), kc=list(cum), kf=list(fin), jd=False)
        else:
            cs[cc] = R(day=day, sp=sp, na=sp / 2, cpi=2.0, c=math.log(2.0), e=math.log(3.0),
                       cum=list(cum) + [None] * 7, fin=list(fin) + [None] * 7, obs=5)
    tot = sum(v[0] for v in specs.values())
    tot = tot or 10.0
    row = R(day=day, sp=tot, na=tot / 2, cum=[None] * 13, obs=0, oc=0.0, jd=jd)
    fc = {"origin": "2031-01-01", "fits": fits}
    d = be.predict("k", fc, CAL0, ("2030-12-31", [row], {day: cs}, None, frozenset(gaps)))["days"][0]
    return d if whole else d["card"]


def test_the_card_joins_each_countries_own_median_by_the_days_spend_share():
    """One set S per card = the covered countries with a curve entry at every card day (small rows too): roas = Σ
    cumulative ÷ Σ spend, bench = spend-weighted exp(its curve median), cv = S's spend ÷ the day's whole country spend;
    a day where a country of S has no cell is null for BOTH lines (the set never changes along the line); fin needs every
    country's final cell AND a date at least CLAG days old; a country without a benchmark is no covered country."""
    L = math.log
    specs = {"AA": (300.0, [30, 60, 90, 120, 150, 180], [30, 60, 90, 120, 150, None], [L(0.2), L(0.4), L(0.6), L(0.8), L(1.0), L(1.2)], True),
             "BB": (100.0, [40, 50, None, None, 100, 110], [40, 50, None, None, 100, 110], [L(0.5), L(0.7), L(0.9), L(1.1), L(1.4), L(1.6)], True),
             "CC": (100.0, [10, 20, 30, 40, 50, 60], [10, 20, 30, 40, 50, 60], [L(0.1)] * 6, False),    # (no benchmark)
             "DD": (50.0, [5] * 6, [5] * 6, [L(0.1), L(0.1), L(0.1), None, L(0.1), L(0.1)], True)}      # (no curve entry at 3)
    c = _card_world(specs)
    assert c["roas"][0] == pytest.approx((30 + 40) / 400, abs=1e-4)             # (CC, DD not in S: 400 of 550)
    assert c["bench"][0] == pytest.approx((300 * 0.2 + 100 * 0.5) / 400, abs=1e-4)
    assert c["cv"] == [pytest.approx(400 / 550, abs=1e-4), pytest.approx(400 / 550, abs=1e-4), None, None,
                       pytest.approx(400 / 550, abs=1e-4), pytest.approx(400 / 550, abs=1e-4)]
    assert c["roas"][2] is None and c["roas"][3] is None and c["bench"][2] is None and c["bench"][3] is None   # BB: no cell
    assert c["roas"][4] == pytest.approx(250 / 400, abs=1e-4)
    assert c["fin"] == [1, 1, 0, 0, 1, 0]                                           # j = 5: AA's cell is not final
    assert c["roas"][5] == pytest.approx(290 / 400, abs=1e-4) and c["bench"][5] == pytest.approx((300 * 1.2 + 100 * 1.6) / 400, abs=1e-4)
    o = _card_world({"AA": specs["AA"], "EE": (100.0, [10, 20, 30, 40, 50, 60], [10, 20, 30, 40, 50, 60], [L(0.1)] * 6,
                                                 "out")})          # outside its learned range: in S, both lines
    assert o["cv"][0] == 1.0 and o["roas"][0] == pytest.approx((30 + 10) / 400, abs=1e-4)
    assert o["bench"][0] == pytest.approx((300 * 0.2 + 100 * 0.1) / 400, abs=1e-4)
    d = _card_world({"AA": (100.0, [None] * 6, [None] * 6, [L(0.2)] * 6, True)}, whole=True)    # nothing known at any j
    assert d["card"] is None and d["cw"] == "r"
    assert _card_world({"AA": (50.0, [5] * 6, [5, 5, None, 5, 5, 5], [L(0.2)] * 6, True)})["fin"] == [1, 1, 0, 1, 1, 1]


def test_the_card_reads_a_covered_small_row_and_says_why_there_is_none():
    """A covered country whose row is under $5 / 30 new users stays in S (cv = 1 when it is the whole spend); a day with
    no card says why: j (a small day), k (no country spend split), c (no covered country), r (no ROAS cell yet)."""
    L = math.log
    full = (300.0, [30, 60, 90, 120, 150, 180], [30, 60, 90, 120, 150, 180], [L(0.2)] * 6, True)
    small = (100.0, [40, 50, 60, 70, 80, 90], [40, 50, 60, 70, 80, 90], [L(0.5)] * 6, True, True)
    c = _card_world({"AA": full, "BB": small})
    assert c["cv"] == [1.0] * 6 and c["roas"][0] == pytest.approx(70 / 400, abs=1e-4)
    assert c["bench"][0] == pytest.approx((300 * 0.2 + 100 * 0.5) / 400, abs=1e-4) and c["fin"] == [1] * 6
    out = {"AA": (100.0, [1] * 6, [1] * 6, [L(0.2)] * 6, False)}                        # nobody covered
    d = _card_world(out, whole=True)
    assert d["card"] is None and d["cw"] == "c"
    assert _card_world({"AA": full}, whole=True, jd=False)["cw"] == "j"
    assert _card_world({}, whole=True)["cw"] == "k"


def test_a_country_cell_three_days_old_is_not_final_for_the_card():
    """A card day whose date is newer than newest − CLAG is not final even when its cells are marked final (they are
    often still empty): install day = newest − 4, days 1 and 2 are at newest − 4 and − 3."""
    L = math.log
    sp = {"AA": (100.0, [10, 20, 30, 40, 50, 60], [10, 20, 30, 40, 50, 60], [L(0.2)] * 6, True)}
    assert _card_world(sp, day="2030-12-27")["fin"] == [1, 0, 0, 0, 0, 0]
    assert _card_world(sp, day="2030-12-28")["fin"] == [0] * 6                       # age 3: nothing final yet
    assert _card_world(sp, day="2030-12-14")["fin"] == [1] * 6


def test_the_cards_data_check_window_is_install_day_to_install_day_plus_the_card_age():
    """chk[j] = 1 when a pack-gap date lies in [X, X + GRID[j]] (days 1, 2, 3, 4, 7, 14 = ages 0, 1, 2, 3, 6, 13)."""
    X = date(2030, 12, 14)
    spec = {"AA": (100.0, [10] * 6, [10] * 6, [0.0] * 6, True)}
    for k, want in ((0, [1, 1, 1, 1, 1, 1]), (1, [0, 1, 1, 1, 1, 1]), (3, [0, 0, 0, 1, 1, 1]), (6, [0, 0, 0, 0, 1, 1]),
                    (13, [0, 0, 0, 0, 0, 1]), (14, [0] * 6), (-1, [0] * 6)):
        assert _card_world(spec, gaps={(X + timedelta(days=k)).toordinal()})["chk"] == want
    assert _card_world(spec)["chk"] == [0] * 6


def _gap_site(tmp, pack_upto, extra=None, newest_off=40, tiny=False):
    """An app whose All rows cover 20 install days (each paying 10 USD a day on its first 3 days, final); the country
    pack carries only the install days up to pack_upto (extra: {cc: …} more rows of the install days after it)."""
    site, data = str(tmp / "site"), str(tmp / "data")
    os.makedirs(site, exist_ok=True)
    os.makedirs(data, exist_ok=True)
    k = KEYS["a"]
    d0 = date(2030, 1, 1)
    sc = 0.01 if tiny else 1.0
    allr, pack = [], {"AA": []}
    for i in range(20):
        xs = (d0 + timedelta(days=i)).isoformat()
        row = roi_row(xs, 50, 20.0, 100.0, [10.0 * sc, 20.0 * sc, 30.0 * sc], [])
        allr.append(row)
        if i <= pack_upto:
            pack["AA"].append(row)
        elif extra:
            for cc in extra:
                pack.setdefault(cc, []).append(row)
    pf = "roi_%s_c00.json.gz" % k
    with gzip.open(os.path.join(site, pf), "wt") as f:
        json.dump({"v": 1, "b": "x", "key": k, "c": pack}, f)
    with gzip.open(os.path.join(site, "roi_%s.json.gz" % k), "wt") as f:
        json.dump({"v": 1, "key": k, "newest": (d0 + timedelta(days=newest_off)).isoformat(), "rows": allr,
                   "cd": {"packs": [[pf, "x"]]}}, f)
    return site, data, d0.toordinal()


def test_a_pack_gap_is_a_date_the_country_packs_lost_never_noise_a_fresh_date_or_a_tiny_total(tmp_path):
    """load(): the All rows' final daily revenue vs every country row (the "--" / "XX" / "ZZ" ones too). Install days
    0 … 9 are in the pack, 10 … 19 are not: the dates they alone pay are gaps; a date with ≥ 35 % in the pack is not;
    the rows of no-country codes make the packs whole again."""
    site, data, o = _gap_site(tmp_path, 9)
    fn = "roi_%s.json.gz" % KEYS["a"]
    newest, app, cty, adm, gaps = be.load(site, data, KEYS["a"], fn, True)
    assert gaps == {o + D for D in range(11, 22)}              # D = 10: 2 of 3 rows in the pack (0.67); D = 11: 1 of 3 (0.33)
    assert not gaps & {o + D for D in range(0, 11)}
    site2, data2, o2 = _gap_site(tmp_path / "w", 9, extra=["--", "XX", "ZZ"])
    assert be.load(site2, data2, KEYS["a"], fn, True)[4] == set()      # the no-country rows count: the All row has them
    assert be.load(site, data, KEYS["a"], fn)[0] == newest                # (the plain read keeps its 3 values)
    s3, d3, _ = _gap_site(tmp_path / "t", 9, tiny=True)
    assert be.load(s3, d3, KEYS["a"], fn, True)[4] == set()            # a tiny total (< PACK_MIN): no claim
    s4, d4, o4 = _gap_site(tmp_path / "n", 9, newest_off=15)           # newest = day 15: only D ≤ 15 − CLAG = 11 counts
    assert be.load(s4, d4, KEYS["a"], fn, True)[4] == {o4 + 11}


def test_pack_gaps_stop_at_the_packs_own_final_edge_and_no_packs_no_gap(tmp_path):
    """Dates the cube has not folded yet (after cd["fthru"]) are not gaps; a file without packs has none."""
    site, data, o = _gap_site(tmp_path, 9)
    fn = "roi_%s.json.gz" % KEYS["a"]
    full = be.load(site, data, KEYS["a"], fn, True)[4]
    assert full and max(full) > o + 14
    path = os.path.join(site, fn)
    with gzip.open(path, "rt") as f:
        body = json.load(f)
    body["cd"]["fthru"] = (date.fromordinal(o) + timedelta(days=14)).isoformat()
    with gzip.open(path, "wt") as f:
        json.dump(body, f)
    cut = be.load(site, data, KEYS["a"], fn, True)[4]
    assert cut == {D for D in full if D <= o + 14} and cut != full
    body["cd"] = {}
    with gzip.open(path, "wt") as f:
        json.dump(body, f)
    assert be.load(site, data, KEYS["a"], fn, True)[4] == set()
    assert be.pack_gaps({990: 100.0, 995: 100.0}, {}, 1000, 992) == {990}


def test_pack_gaps_ordinary_noise_is_not_a_gap_and_the_limits_are_exact():
    nw = 1000
    assert be.pack_gaps({990: 100.0}, {990: 90.0}, nw) == set()         # ±10 % noise
    assert be.pack_gaps({990: 100.0}, {990: 110.0}, nw) == set()
    assert be.pack_gaps({990: 100.0}, {990: 34.0}, nw) == {990}         # under 0.35 ×
    assert be.pack_gaps({990: 100.0}, {990: 35.0}, nw) == set()
    assert be.pack_gaps({990: 100.0}, {}, nw) == {990}                  # an empty-country date
    assert be.pack_gaps({nw - be.CLAG: 100.0, nw - be.CLAG + 1: 100.0}, {}, nw) == {nw - be.CLAG}   # newer: not final
    assert be.pack_gaps({990: be.PACK_MIN - 0.01}, {}, nw) == set() and be.pack_gaps({990: be.PACK_MIN}, {}, nw) == {990}


def test_run_carries_the_pack_gaps_to_the_card(tmp_path):
    """End to end: the gap dates reach predict through the pin, so a card point whose window holds one says chk."""
    site, data, dash = make(tmp_path)
    fn = "roi_%s.json.gz" % KEYS["a"]
    pk = os.path.join(site, "roi_%s_c00.json.gz" % KEYS["a"])
    with gzip.open(pk, "rt") as f:
        body = json.load(f)
    gap = TODAY - timedelta(days=60)
    for cc, rows in body["c"].items():                       # the packs lose every cell of one activity date
        for r in rows:
            X = date.fromisoformat(r[0])
            a = (gap - X).days
            if 0 <= a < len(r[4]) and a < r[5]:
                step = r[4][a] - (r[4][a - 1] if a else 0.0)
                r[4][a:] = [v - step for v in r[4][a:]]
    with gzip.open(pk, "wt") as f:
        json.dump(body, f)
    assert be.load(site, data, KEYS["a"], fn, True)[4] == {gap.toordinal()}
    assert be.run(dash, data, site, {}, NOW) == ["/be_*"]
    days = {d["d"]: d for d in body_of(site, "a")["days"]}
    for k in (0, 1, 5, 13, 14, -1):
        x = (gap - timedelta(days=k)).isoformat()
        if x in days:
            ch = days[x]["card"]["chk"]
            assert ch == [1 if 0 <= k <= be.GRID[j] else 0 for j in be.CARD_J], (k, ch)


def test_the_apps_median_benchmark_is_gone():
    import inspect
    assert "app_med" not in inspect.getsource(be).replace("app_med is gone", "") .replace('"app_med" not in', "")
    assert "app_med" not in be.fit([], {}, TODAY.toordinal())
