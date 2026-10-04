"""👥 Audience tab — the build step (the owner-approved Audience demo, ported): who still has each app, who opens it, who
went quiet and for how many months, and what waking them could earn.

ONE lazy file, site/audience.json.gz, with what the page's Audience screen needs — the portfolio, every app's summary
and detail, and the all-apps table (the page sorts it by money) — and the pointer dashboard["audience"] = {"file", "v"}
(the page shows its nav item only with it). Every number is the demo's own formula, on the same inputs the demo read:

  * the phone split (Active users tab's day E = its settled_till): installed = Σ new − Σ un (GA4 Uninstall store, days ≤
    E) · opened on E = a1 · opened in 28 days and still installed = a28 − un28 · sleeping = installed − (a28 − un28)
    ("data kam" when that goes clearly negative or a28 − un28 < a1);
  * the journey on day 1 / 7 / 30 / 90 (opened = the Active tab's pooled return rate, removed = the Uninstall tab's
    survival "all", has = the rest), the long-term return (install-day iday grain, enough installs behind each knot),
    "pakke" users (installed 90+ days ago and opened on E, iday age bands), today's DAU by install age (iday bands);
  * money: revenue per daily / monthly user (AdMob, the 28 days to E), an OLD user's revenue per active day (its own;
    a young app takes the all-apps typical old/all ratio), and the page's "paise ka calculator" inputs on the same 28
    days (usage28: impressions, ads per user, eCPM, sessions per user — all users and returning users — from the Active
    users tab's own per-app file);
  * "data se" (the calculator's default opens a month): each app's return curve FITTED on its own last 12 install
    weeks (fit_curve: weighted least squares, power-law or exponential decay with a plateau) → expected active days in
    30, a P10–P90 range from weekly refits, and K = days × the per-open basis' sessions per active day; too few installs
    → the all-apps fit;
  * day-wise: every install day's installs and removals by when (the Uninstall tab's own cells and flags).

DEAD USERS BY MONTHS SINCE THE LAST OPEN — per app, whichever exists:
  * "ga4" (GA4 lagbhag exact): the app's COMPLETE GA4 Audience store (fetch.ga4_audience; its "partial" read in progress
    is never used) through engine.audience.derive_app — the windows / months come from the store (tiered), every total
    carries its range dead_lo … dead, the most dead / active install month and today's DAU by install month;
  * "andaza" (no complete store yet — "GA4 data aa raha hai" when a read is under way): the demo's cohort-curve
    estimate — the app's return curve (D1–D30, then 45 … 365 days) decides when each install day's users stopped
    opening, later uninstalls taken out, scaled to the phone card's sleeping total — on the SAME months as a GA4 read of
    that app would have (engine.audience.tier_months), a month being round(N × 30.44) days (the demo's windows).
  Both give per window month N: dead(N) = installed now and not opened for ≥ N months; the page draws the buckets
  between consecutive months exactly as engine.audience's last_open does.

Inputs (all written earlier in this build — no GA4 / AdMob call here): the dashboard in memory (active.apps,
active.portfolio, uninstall.asset, usd_inr), site/uninstall.json.gz, site/uninstall_c_<key>.json.gz,
site/<active portfolio file>, site/active_<key>.json.gz (the Active tab's per-app file: the calculator's inputs only — a
missing one costs just those), data/ga4_uninstall/<key>.json.gz (+ iday/<key>[.old].json.gz) and
data/ga4_audience/<key>.json.gz. Nothing is trimmed: every app, install day and install month since the launch.

  run(dashboard, data_dir, out_dir, s) → the _headers no-store paths (["/audience*"] — ONE splat rule for this file and
  any later per-app file; never a rule per app). off(out_dir): the switch (repo variable AUDIENCE_TAB=false) — the file
  removed, no pointer, nothing printed: the site exactly as without the feature.

Failure-isolated: an app whose inputs are missing or broken is left out (counted); any other failure costs this tab only
(no file, no pointer — the error TYPE only in the log). PRIVACY: ONE counts-only log line (pop_line).
"""

import gzip
import hashlib
import json
import math
import os
import sys
from datetime import date, timedelta

from .db import write_json_gz_stable
from .engine import audience as aud_eng

FILE = "audience.json.gz"
HEADER_PATHS = ["/audience*"]          # one splat rule: this file and any later per-app file (deploy guard: ≤ 100 rules)
V = 1
MONTH = 30.44                          # the demo's month: its windows are round(N × 30.44) days (30, 61, 91 … 365)
SLEEP_DAYS = 28                        # "sleeping" = not in the 28-day actives
ULAGS = (0, 1, 3, 7, 14, 30, 45, 60, 90, 120, 180, 270, 365)   # the iday store's lags (Install value tab's Q-B grain)
LONG_KNOTS = (45, 60, 90, 120, 180, 270, 365)
KNOT_MIN_N, KNOT_MIN_DAYS = 500, 14
JOURNEY_DAYS = (1, 7, 30, 90)
LONG_SHOW = ("30", "60", "90", "180", "270", "365")
MAX_GZ = 3000000                       # far above a 30-app portfolio's size: past it no file (counted, never trimmed)
LINE = None


def enabled(s):
    return bool((s or {}).get("audience_tab", True))


# ── small helpers ────────────────────────────────────────────────────────────────────────────────────────────────────
def _gz(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def D(s):
    return date.fromisoformat(str(s)[:10])


def iso(d):
    return d.isoformat()


def _r(v, k=6):
    return None if v is None else round(float(v), k)


def _int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return 0


def andaza_window(m):
    """The demo's window of m months, in days: round(m × 30.44) — 30, 61, 91, 122 … 365 for m = 12."""
    return int(round(m * MONTH))


def bucket_of(days):
    """The demo's bucket of a not-opened span (its model total is summed bucket by bucket, in this order)."""
    m = max(1, int(days // MONTH))
    if m <= 6:
        return str(m)
    return "7-12" if m < 12 else "12+"


_BUCKET_ORDER = ("1", "2", "3", "4", "5", "6", "7-12", "12+")


# ── return curves (the Active users tab's own definitions) ───────────────────────────────────────────────────────────
def pooled_ret(store, launch, E, new):
    """Active-tab return rate per N = 1..30: Σ a[N] ÷ Σ new over usable cohorts (ok, t > 0, a0/t in [0.9, 1.1], on or
    after ret_from and the launch, new > 0) whose day N is settled (c + N ≤ E). → {N: (rate, installs, days)}."""
    ret = store.get("ret") or {}
    rf = D(store["ret_from"]) if store.get("ret_from") else None
    num, den, cnt = [0] * 31, [0] * 31, [0] * 31
    for c, e in ret.items():
        cd = D(c)
        if cd < launch or (rf and cd < rf) or not e.get("ok"):
            continue
        t = int(e.get("t") or 0)
        a = [int(x or 0) for x in (e.get("a") or [])]
        n = new.get(c) or 0
        if t <= 0 or not a or not .9 <= a[0] / t <= 1.1 or n <= 0:
            continue
        for N in range(1, 31):
            if len(a) > N and cd + timedelta(days=N) <= E:
                num[N] += a[N]
                den[N] += n
                cnt[N] += 1
    return {N: (num[N] / den[N], den[N], cnt[N]) for N in range(1, 31) if den[N] > 0}


def iday_x(data_dir, key):
    """The install-day store's x (older file first, the current one wins) and the current file itself."""
    x = {}
    base = os.path.join(data_dir, "ga4_uninstall", "iday", key)
    for fn in (base + ".old.json.gz", base + ".json.gz"):
        if os.path.exists(fn):
            x.update(_gz(fn).get("x") or {})
    cur = _gz(base + ".json.gz") if os.path.exists(base + ".json.gz") else {}
    return x, cur


def pooled_long(x, to, launch):
    """Σ u[lag] ÷ Σ n over install days X ≥ launch whose day X+lag ≤ to (iday Q-B grain). → {lag: (rate, n, days)}."""
    out = {}
    for j, lag in enumerate(ULAGS):
        if lag < 30:
            continue
        num = den = k = 0
        for X, e in x.items():
            Xd = D(X)
            if Xd < launch or Xd + timedelta(days=lag) > to:
                continue
            u = e.get("u") or []
            n = e.get("n") or 0
            if len(u) > j and n > 0:
                num += u[j]
                den += n
                k += 1
        if den > 0:
            out[lag] = (num / den, den, k)
    return out


def long_ok(v, installs):
    """A long-term knot needs enough installs behind it: ≥ max(1000, 2% of the app's installs) over ≥ 21 install days
    (an app's first weeks — often a few test installs — must not set its 180 / 365-day rate alone)."""
    return v[1] >= max(1000, 0.02 * installs) and v[2] >= 21 and v[0] > 0


def curve(ret, longr, tmax, installs):
    """Daily grid r[0..tmax] of the day-t open rate: ret for 1..30, iday knots after (enough installs), log-log between
    knots, power-law past the last knot (never rising). → (r, knots, slope, last knot)."""
    knots = [(0, 1.0)]
    for N in range(1, 31):
        if N in ret and ret[N][1] >= KNOT_MIN_N and ret[N][2] >= KNOT_MIN_DAYS and ret[N][0] > 0:
            knots.append((N, ret[N][0]))
    if len(knots) < 3:                       # a tiny app: take what it has (any installs), never nothing
        knots = [(0, 1.0)] + [(N, ret[N][0]) for N in range(1, 31) if N in ret and ret[N][0] > 0 and ret[N][1] >= 30]
    if len(knots) < 3:
        knots = [(0, 1.0), (1, 0.2), (30, 0.05)]
    for lag in LONG_KNOTS:
        if lag in longr and long_ok(longr[lag], installs):
            knots.append((lag, longr[lag][0]))
    knots.sort()
    ks = [k for k, _ in knots]
    vs = [v for _, v in knots]
    for i in range(2, len(vs) - 1):          # light smoothing of the daily 1..30 part (weekday noise): 3-point median
        if ks[i] <= 30:
            vs[i] = sorted(vs[i - 1:i + 2])[1]
    knots = list(zip(ks, vs))
    last = knots[-1][0]
    r = [0.0] * (tmax + 1)
    r[0] = 1.0
    for (t0, v0), (t1, v1) in zip(knots, knots[1:]):
        for t in range(max(t0, 1), min(t1, tmax) + 1):
            if t0 == 0:
                r[t] = v1
            else:
                w = (math.log(t) - math.log(t0)) / (math.log(t1) - math.log(t0))
                r[t] = math.exp(math.log(v0) + w * (math.log(v1) - math.log(v0)))
    tail = [k for k in knots if k[0] >= max(14, last / 2.5)]
    if len(tail) >= 2:
        (ta, va), (tb, vb) = tail[0], tail[-1]
        b = min(0.0, (math.log(vb) - math.log(va)) / (math.log(tb) - math.log(ta)))
    else:
        b = -0.5
    for t in range(last + 1, tmax + 1):
        r[t] = knots[-1][1] * (t / last) ** b
    return r, knots, b, last


def dead_model(n_c, I_c, A_c, f_c, r, target, young_keep, windows):
    """The demo's k-calibrated alive curve S(t) = min(I(t), k·f·r(t)) for t ≥ 28 (S = I before), fitted so the cohorts'
    still-active users add up to `target` (the 28-day actives still installed) → (model total of still-installed users
    who left the 28-day pool, k, how, per-cohort [users not opened for ≥ W days for W in windows] or None). Each day's
    uninstalls are shared between that day's leavers and the dormant pool by their size (a dormant user can still
    uninstall later)."""
    C = len(n_c)
    rmin = []
    for c in range(C):
        A = A_c[c]
        rmin.append(min(r[SLEEP_DAYS:A + 1]) if A >= SLEEP_DAYS else None)
    old_inst = sum(n_c[c] * I_c[c][A_c[c]] for c in range(C) if rmin[c] is not None)
    want_old = target - young_keep

    def alive(k):
        s = 0.0
        for c in range(C):
            if rmin[c] is None:
                continue
            s += n_c[c] * min(I_c[c][A_c[c]], k * f_c[c] * rmin[c])
        return s
    if want_old <= 0:
        k, how = 0.0, "zero"
    elif want_old >= old_inst:
        k, how = None, "over"
    else:
        lo, hi = 0.0, 1.0
        while alive(hi) < want_old and hi < 1e4:
            hi *= 2
        for _ in range(60):
            mid = (lo + hi) / 2
            if alive(mid) < want_old:
                lo = mid
            else:
                hi = mid
        k, how = hi, "ok"
    out = {b: 0.0 for b in _BUCKET_ORDER}
    per = [None] * C
    if k is None:
        return 0.0, None, how, per
    for c in range(C):
        A = A_c[c]
        if A < SLEEP_DAYS:
            continue
        I = I_c[c]
        kf = k * f_c[c]
        S = list(I[:A + 1])
        for t in range(SLEEP_DAYS, A + 1):
            v = kf * r[t]
            if v < S[t]:
                S[t] = v
        for t in range(1, A + 1):            # never rising
            if S[t] > S[t - 1]:
                S[t] = S[t - 1]
        keep = [1.0] * (A + 1)
        s = [0.0] * (A + 1)
        for t in range(1, A + 1):
            st = S[t - 1] - S[t]
            u = I[t - 1] - I[t]
            dm = I[t - 1] - S[t - 1]
            den = st + dm
            g = min(1.0, max(0.0, u / den)) if den > 1e-12 else 0.0
            s[t] = st
            keep[t] = 1 - g
        keep[0] = 1.0                        # (g[0] = 0 in the demo: keep 1)
        rem = [0.0] * (A + 1)
        acc = 1.0
        for t in range(A, -1, -1):
            acc = acc * keep[t] if t < A else keep[t]
            rem[t] = acc
        left = [s[t] * rem[t] for t in range(A + 1)]
        for t in range(A + 1):
            if left[t] > 0:
                out[bucket_of(A - t + SLEEP_DAYS)] += n_c[c] * left[t]
        cs, run = [0.0] * (A + 1), 0.0
        for t in range(A + 1):
            run += left[t]
            cs[t] = run
        per[c] = [float(n_c[c] * cs[min(A, A + SLEEP_DAYS - W)]) if A + SLEEP_DAYS - W >= 0 else 0.0 for W in windows]
    return sum(out.values()), k, how, per


def usage28(det, rev_days, w28):
    """The calculator's per-open inputs, from the Active users tab's own per-app daily arrays (active_<key>.json.gz,
    written earlier in this build — its "ads per user", "eCPM" and "sessions per user" tiles' sums) over the money's 28
    days → {imp28, ads, ec, spu, spr, sd}, every value None when the arrays lack it:
      * imp28 = Σ AdMob impressions on the days rev28 counts (rev_days: its revenue known, active users > 0); ads =
        imp28 ÷ Σ those days' active users (impressions per active user per day); ec = eCPM = Σ revenue ÷ imp28 × 1000;
      * over the 28 days whose GA4 usage day is whole (its returning slot known — the tab's own rule): spu = Σ sessions ÷
        Σ active users of every slot (new + returning + other: all users), spr = the returning slot alone (users
        installed before that day — the tab's "sessions per user"), sd = those days."""
    out = {"imp28": None, "ads": None, "ec": None, "spu": None, "spr": None, "sd": 0}
    dl = (det or {}).get("daily") if isinstance(det, dict) else None
    if not isinstance(dl, dict) or not dl.get("start"):
        return out
    d0 = D(dl["start"])
    n = len(dl.get("a1") or [])

    def at(arr, k):
        i = (D(k) - d0).days
        return arr[i] if isinstance(arr, list) and 0 <= i < len(arr) and 0 <= i < n else None
    imp = rv = au = 0.0
    seen = 0
    for k in rev_days:
        im, r, a = at(dl.get("imp"), k), at(dl.get("rev"), k), at(dl.get("a1"), k)
        if im is None or r is None or not a:
            continue
        imp += im
        rv += r
        au += a
        seen += 1
    if seen and imp > 0:
        out.update(imp28=int(round(imp)), ads=_r(imp / au), ec=_r(rv / imp * 1000))
    u, s = dl.get("u") or {}, dl.get("s") or {}
    su = uu = sr = ur = 0.0
    for k in w28:
        r_u = at(u.get("r"), k)
        if not r_u:
            continue
        uu += sum(at(u.get(g), k) or 0 for g in "nro")
        su += sum(at(s.get(g), k) or 0 for g in "nro")
        ur += r_u
        sr += at(s.get("r"), k) or 0
        out["sd"] += 1
    if uu > 0 and su > 0:
        out["spu"] = _r(su / uu)
    if ur > 0 and sr > 0:
        out["spr"] = _r(sr / ur)
    return out


# ── "Data se": a woken user's opens a month, from a return curve FITTED on the app's own past installs ───────────────
# (the owner, 4 Oct: "isme tum ML use kar sakte ho based on back date data"). A woken sleeper is taken to drift away
# the way the app's new users do; its expected active days in the first 30 = 1 + Σ_{d=1..29} r(d), r(d) = the share of
# an install day's users who open the app on day d. r is fitted, not read point by point: weighted least squares over
# install days (weights = installs; final days only) of two decay-with-plateau families — power law p + b·d^−k and
# exponential p + b·e^(−d/τ) — the one with the smaller weighted error wins. The page multiplies the days by the app's
# sessions per active day (K opens a month). The range is the install-weighted P10 / P90 of the same fit redone week by
# week. An app with too few installs in the window takes the all-apps fit (all apps' installs pooled).
FIT_WEEKS, FIT_LAG, FIT_DAYS = 12, 30, 30   # the last 12 install weeks whose days 1 … 30 are all final
FIT_MIN = 3000                              # installs in the window for an app's own curve
FIT_WEEK_MIN, FIT_MIN_WEEKS = 100, 4        # a weekly refit needs 100 installs; a range needs 4 such weeks
_FAM = {"pow": (lambda d, t: d ** -t, 0.02, 4.0), "exp": (lambda d, t: math.exp(-d / t), 0.3, 300.0)}


def fit_weeks(store, launch, E, new):
    """The fit's window: the last FIT_WEEKS install weeks whose days 1 … 30 are all final — week j = install days
    E−30−7j−6 … E−30−7j — usable cohorts only (pooled_ret's rule: ok, t > 0, a0/t in [0.9, 1.1], on or after ret_from
    and the launch, new > 0) → [[n, a, installs]] per week, n[d] / a[d] = Σ new / Σ day-d openers of its cohorts."""
    ret = store.get("ret") or {}
    rf = D(store["ret_from"]) if store.get("ret_from") else None
    last = E - timedelta(days=FIT_LAG)
    weeks = [[[0] * (FIT_DAYS + 1), [0] * (FIT_DAYS + 1), 0] for _ in range(FIT_WEEKS)]
    for c, e in ret.items():
        cd = D(c)
        off = (last - cd).days
        if not 0 <= off < 7 * FIT_WEEKS or cd < launch or (rf and cd < rf) or not e.get("ok"):
            continue
        t = int(e.get("t") or 0)
        a = [int(x or 0) for x in (e.get("a") or [])]
        n = new.get(c) or 0
        if t <= 0 or not a or not .9 <= a[0] / t <= 1.1 or n <= 0:
            continue
        w = weeks[off // 7]
        w[2] += n
        for d in range(1, FIT_DAYS + 1):
            if len(a) > d:
                w[0][d] += n
                w[1][d] += a[d]
    return weeks


def _wls(pts, xs):
    """min Σ w (y − p − b·x)² with p, b ≥ 0 (closed form) → (error, p, b)."""
    Sw = Sx = Sy = Sxx = Sxy = 0.0
    for (_, w, y), x in zip(pts, xs):
        Sw += w
        Sx += w * x
        Sy += w * y
        Sxx += w * x * x
        Sxy += w * x * y
    den = Sw * Sxx - Sx * Sx
    b = (Sw * Sxy - Sx * Sy) / den if den > 1e-300 else 0.0
    p = (Sy - b * Sx) / Sw
    if p < 0:
        p, b = 0.0, (Sxy / Sxx if Sxx > 0 else 0.0)
    if b < 0:
        p, b = Sy / Sw, 0.0
    return sum(w * (y - p - b * x) ** 2 for (_, w, y), x in zip(pts, xs)), p, b


def fit_curve(n, a):
    """Weighted least squares of r(d) over d = 1 … 30 (weights = installs: Σ over install days of n_c·(y_cd − r(d))² =
    Σ_d N_d·(ȳ_d − r(d))² + const, so the per-day sums n[d], a[d] are enough) → {"f": family, "p", "b", "t"} or None
    (fewer than 3 days with installs). For a fixed shape t the model is linear in (p, b); t by a log grid, then a
    golden-section refine around the best grid point; the family with the smaller weighted error wins."""
    pts = [(d, n[d], a[d] / n[d]) for d in range(1, len(n)) if n[d] > 0]
    if len(pts) < 3:
        return None
    best = None
    for fam, (fx, lo, hi) in _FAM.items():
        def err(lt, fx=fx):
            return _wls(pts, [fx(d, math.exp(lt)) for d, _, _ in pts])
        L0, L1, G = math.log(lo), math.log(hi), 40
        grid = [L0 + (L1 - L0) * i / (G - 1) for i in range(G)]
        i = min(range(G), key=lambda j: err(grid[j])[0])
        x0, x1 = grid[max(0, i - 1)], grid[min(G - 1, i + 1)]
        g = (5 ** .5 - 1) / 2
        c, e = x1 - g * (x1 - x0), x0 + g * (x1 - x0)
        fc, fe = err(c)[0], err(e)[0]
        for _ in range(40):
            if fc < fe:
                x1, e, fe = e, c, fc
                c = x1 - g * (x1 - x0)
                fc = err(c)[0]
            else:
                x0, c, fc = c, e, fe
                e = x0 + g * (x1 - x0)
                fe = err(e)[0]
        lt = (x0 + x1) / 2
        sse, p, b = err(lt)
        if best is None or sse < best[0]:
            best = (sse, {"f": fam, "p": p, "b": b, "t": math.exp(lt)})
    return best[1]


def curve_at(f, d):
    """The fitted share opening on day d ≥ 1, clipped to [0, 1]."""
    return min(1.0, max(0.0, f["p"] + f["b"] * _FAM[f["f"]][0](d, f["t"])))


def curve_days(f):
    """Expected active days in the first 30 (the woken day counts): 1 + Σ_{d=1..29} r(d)."""
    return 1 + sum(curve_at(f, d) for d in range(1, FIT_LAG))


def wpct(vals, ws, q):
    """The install-weighted percentile q of vals (each value at the middle of its weight; linear between)."""
    xs = sorted(zip(vals, ws))
    tot = float(sum(w for _, w in xs))
    pts, acc = [], 0.0
    for v, w in xs:
        pts.append(((acc + w / 2) / tot, v))
        acc += w
    if q <= pts[0][0]:
        return pts[0][1]
    if q >= pts[-1][0]:
        return pts[-1][1]
    for (q0, v0), (q1, v1) in zip(pts, pts[1:]):
        if q0 <= q <= q1:
            return v0 + (v1 - v0) * (q - q0) / (q1 - q0) if q1 > q0 else v1
    return pts[-1][1]


def fit_app(weeks):
    """The window's weeks → {"d": days, "d10", "d90", "f": the fit, "n": installs, "wk": weeks refitted} or None: the
    pooled fit's days, and the install-weighted P10 / P90 of the weekly refits (weeks with FIT_WEEK_MIN installs; none
    with fewer than FIT_MIN_WEEKS of them), widened to hold the pooled answer."""
    n = [sum(w[0][d] for w in weeks) for d in range(FIT_DAYS + 1)]
    a = [sum(w[1][d] for w in weeks) for d in range(FIT_DAYS + 1)]
    f = fit_curve(n, a)
    if f is None:
        return None
    d = curve_days(f)
    wk = []
    for w in weeks:
        if w[2] >= FIT_WEEK_MIN:
            fw = fit_curve(w[0], w[1])
            if fw is not None:
                wk.append((curve_days(fw), w[2]))
    d10 = d90 = None
    if len(wk) >= FIT_MIN_WEEKS:
        d10 = min(d, wpct([v for v, _ in wk], [x for _, x in wk], 0.1))
        d90 = max(d, wpct([v for v, _ in wk], [x for _, x in wk], 0.9))
    return {"d": d, "d10": d10, "d90": d90, "f": f, "n": sum(w[2] for w in weeks), "wk": len(wk)}


def _jround(v):
    return int(math.floor(v + 0.5))                     # the page's Math.round (half up)


def kf_entry(fit, src, s):
    """The file's "kf" block: days (4 decimals), the fit, and K / K10 / K90 = max(1, round(days × s)) with s = the
    sessions per active day the page's per-open money uses (None: no K)."""
    r4 = lambda v: None if v is None else round(v, 4)
    d, d10, d90 = r4(fit["d"]), r4(fit["d10"]), r4(fit["d90"])
    K = lambda v: None if v is None or not s else max(1, _jround(v * s))
    f = fit["f"]
    return {"src": src, "d": d, "d10": d10, "d90": d90, "K": K(d), "K10": K(d10), "K90": K(d90), "n": fit["n"],
            "wk": fit["wk"], "fit": {"f": f["f"], "p": _r(f["p"]), "b": _r(f["b"]), "t": _r(f["t"])}}


def lags_of(cf, day):
    """The Uninstall tab's cells (fill_days-filled) of one install day → {lag: users}."""
    j = (D(day) - D(cf["start"])).days
    if not 0 <= j < len(cf["lags"]):
        return {}
    return {int(L): int(u) for L, u in cf["lags"][j]}


# ── dead users by months: the two sources, one shape ─────────────────────────────────────────────────────────────────
def _store_complete(store):
    """The store's COMPLETE result (its top level), or None: never the partial read in progress."""
    if not isinstance(store, dict) or store.get("complete") is False or not store.get("windows"):
        return None
    if store.get("complete") is not True and "partial" in store:
        return None
    return store


def ga4_part(store, uni_filled):
    """A complete GA4 Audience store + the app's filled Uninstall store → the page's "au" block (engine.audience)."""
    out = aud_eng.derive_app(store, uni_filled)
    if isinstance(out.get("months"), list):                # the store's own window months (tiered)
        mo = [int(m) for m in out["months"]]
    else:                                                  # (an engine without them: from the window days)
        mo = [int(round(int(w) / aud_eng.MONTH_DAYS)) for w in out["windows"]]
    mby = out.get("months_by") if isinstance(out.get("months_by"), dict) else out.get("months")
    dau = out.get("dau") or {}
    dbm = dau.get("by_month") or {}
    rows = []
    for m in sorted(mby):
        g = mby[m]
        if not g.get("installs"):
            continue
        rows.append([m, g["installs"], g["installed"], g["dead"][0], g["dead_lo"][0],
                     1 if (g.get("young_days") or [0])[0] else 0, _int(dbm.get(m))])
    flags = out.get("flags") or {}
    return {"src": "ga4", "E": out["E"], "hs": out["history_start"], "mo": mo, "full": bool(out.get("full")),
            "ins": out["installs"], "inst": out["installed"], "d": list(out["dead"]), "lo": list(out["dead_lo"]),
            "m": rows, "most": out.get("most"),
            "dau": {"users": dau.get("users"), "before": dau.get("before_history"), "other": dau.get("other"),
                    "not_set": dau.get("not_set"), "cov": dau.get("cov")},
            "clamps": out.get("clamps_by_month") or {},
            "imp": sum(v[0] for v in (out.get("impossible") or {}).values()),
            "flags": {k: flags.get(k) for k in ("un_provisional_days", "un_incomplete_days", "history_capped",
                                                  "impossible_cells", "clamped_cells") if k in flags},
            "other": any(_int(v) for v in (out.get("other") or []))}


def andaza_part(day_c, n_c, I_c, A_c, per, mos, wins, sc, cf, new, E, w1):
    """The demo's placeholder through its own audience_blob arithmetic, on the tiered months → the page's "au" block
    (per install month, rounded like the demo; the app's dead(N) = Σ of its months)."""
    rows = {}
    for c, day in enumerate(day_c):
        A, n = A_c[c], n_c[c]
        inst_c = n * I_c[c][A]
        lg = lags_of(cf, day)
        acts = []
        for j, W in enumerate(wins):
            deadW = min(inst_c, sc * per[c][j]) if per[c] is not None else 0.0
            unW = sum(u for L, u in lg.items() if A - W + 1 <= L <= A)
            acts.append(round(inst_c - deadW + unW))
        nn = int(new.get(day) or 0)
        if nn <= 0 or D(day) > E:
            continue
        lgA = {L: u for L, u in lg.items() if L <= A}
        inst = max(0, nn - sum(lgA.values()))
        dead = []
        for j, W in enumerate(wins):
            unW = sum(u for L, u in lgA.items() if L >= A - W + 1)
            dead.append(min(inst, max(0.0, inst - (acts[j] - unW))))
        r = rows.setdefault(day[:7], [0, 0, [0.0] * len(wins), 0])
        r[0] += nn
        r[1] += inst
        for j in range(len(wins)):
            r[2][j] += dead[j]
        if A < w1:
            r[3] = 1
    out_rows, d = [], [0] * len(mos)
    for m in sorted(rows):
        n, inst, dd, young = rows[m]
        dr = [int(round(v)) for v in dd]
        for j in range(len(mos)):
            d[j] += dr[j]
        out_rows.append([m, int(n), int(inst), dr[0] if dr else 0, None, young, None])
    ins = sum(r[1] for r in out_rows)
    inst = sum(r[2] for r in out_rows)
    groups = {r[0]: {"installs": r[1], "young_days": [r[5]], "dead": [r[3]], "alive": [r[2] - r[3]]}
              for r in out_rows if r[1]}
    return {"src": "andaza", "E": iso(E), "mo": list(mos), "full": True, "ins": ins, "inst": inst, "d": d, "lo": None,
            "m": out_rows, "most": aud_eng.most(groups, ins) if groups else None, "dau": None, "clamps": {},
            "imp": 0, "flags": {}, "other": False, "_rows_dead": {r[0]: rows[r[0]][2] for r in out_rows}}


# ── one app ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def app_entry(aa, ua, st, p, cf, x, cur, store, uni_filled_of, aud_mode=None, det=None):
    """One app (active row aa, uninstall detail ua, Uninstall store st, portfolio arrays p, cohort file cf, iday x + its
    current file, GA4 Audience store or None, the Active tab's per-app file or None) → (its page entry, its private
    extras for the all-apps step)."""
    E = D(aa["settled_till"])
    hs = D(st["history_start"])
    launch = D(ua["launch"]["day"]) if (ua.get("launch") or {}).get("day") else hs
    daily = st["daily"]
    new = {k: int(v.get("new") or 0) for k, v in daily.items()}
    un = {k: int(v.get("un") or 0) for k, v in daily.items()}
    days = [k for k in sorted(daily) if D(k) <= E]
    inst_total = sum(new[k] for k in days)
    removed = sum(un[k] for k in days)
    installed = inst_total - removed
    e = daily[iso(E)]
    a1, a28 = int(e["a1"]), int(e["a28"])
    w28 = [iso(E - timedelta(days=i)) for i in range(28)]
    un28 = sum(un.get(k, 0) for k in w28)
    new28 = sum(new.get(k, 0) for k in w28)
    a28k = a28 - un28                          # 28-day actives still on the phone (GA4 also counts the removed)
    sleeping_raw = installed - a28k
    data_kam = installed <= 0 or sleeping_raw < -max(50, 0.02 * installed) or a28k < a1
    sleeping = max(0, sleeping_raw)
    # revenue (Active tab / portfolio arrays, USD, GA4 days)
    p0 = D(p["start"])
    idx = {iso(p0 + timedelta(days=i)): i for i in range(len(p["a1"]))}
    idays = cur.get("days") or {}
    rev28 = a1_28 = 0.0
    old_rev = old_users = 0.0
    rev_days = 0
    rev_list = []
    for k in w28:
        i = idx.get(k)
        if i is None:
            continue
        rv, av = p["rev"][i], p["a1"][i]
        if rv is None or not av:
            continue
        rev28 += rv
        a1_28 += av
        rev_days += 1
        rev_list.append(k)
        dd = idays.get(k)
        if dd and dd.get("ab") and dd.get("rev"):
            ab = dd["ab"]
            ga = dd.get("a") or av
            ou = ab[3] + ab[4] + ab[5] + max(0, ga - (dd.get("a4") or 0))
            orv = dd["rb"][3] + dd["rb"][4] + dd["rb"][5] + max(0, dd.get("rb_old") or 0)
            old_users += av * ou / ga if ga else 0
            old_rev += rv * orv / dd["rev"]
    arpdau = rev28 / a1_28 if a1_28 else None
    per_mau = rev28 / a28 * 30 / 28 if a28 and rev_days >= 20 else None
    old_dau = old_users / rev_days if rev_days and old_users else 0.0
    old_a28 = a28 - new28
    own = old_dau >= 100 and old_a28 >= 1000 and old_rev > 0
    ret_arpu = old_rev / old_users if own else None
    freq = min(1.0, old_dau / old_a28) if own else None
    # pakke: old users (installed 90+ days ago) who opened on E (iday age bands)
    de = idays.get(iso(E))
    pakke_today = None
    if de and de.get("ab"):
        ga = de.get("a") or a1
        pakke_today = int(round((de["ab"][4] + de["ab"][5] + max(0, ga - (de.get("a4") or 0))) * a1 / ga))
    # return curves, journey, long-term
    ret = pooled_ret(st, launch, E, new)
    to = D(cur["to"]) if cur.get("to") else E
    longr = pooled_long(x, min(to, E), launch)
    surv = (ua.get("survival") or {}).get("all") or {}
    left = surv.get("left") or []
    inst_launch = sum(v for k_, v in new.items() if launch <= D(k_) <= E)
    journey = {}
    for N in JOURNEY_DAYS:
        o = ret.get(N) if N <= 30 else (longr[N] if N in longr and long_ok(longr[N], inst_launch) else None)
        rm = (1 - left[N]) if N < len(left) and left[N] is not None else None
        if o is None or rm is None:
            journey[str(N)] = None
            continue
        journey[str(N)] = {"open": o[0], "has": max(0.0, 1 - rm - o[0]), "gone": rm, "n": o[1]}
    longt = {str(lag): {"v": v[0], "n": v[1], "k": v[2]} for lag, v in longr.items() if long_ok(v, inst_launch)}
    if 30 in ret and ret[30][1] >= KNOT_MIN_N:            # day 30 = the Active tab's own (ret), like the journey
        longt["30"] = {"v": ret[30][0], "n": ret[30][1], "k": ret[30][2]}
    # the cohort-curve model (install-day cohorts since the launch): the phone card's sleeping split by months
    tmax = (E - launch).days
    r, knots, slope, last_knot = curve(ret, longr, max(tmax, 31), inst_launch)
    mon_act, mon_exp = {}, {}
    for X, ex in x.items():
        Xd = D(X)
        if Xd < launch:
            continue
        u, n = ex.get("u") or [], ex.get("n") or 0
        for j, lag in enumerate(ULAGS):
            if lag >= 30 and len(u) > j and Xd + timedelta(days=lag) <= min(to, E) and lag <= tmax:
                mon_act[X[:7]] = mon_act.get(X[:7], 0) + u[j]
                mon_exp[X[:7]] = mon_exp.get(X[:7], 0) + n * r[lag]
    fmon = {m: min(3.0, max(1 / 3, mon_act[m] / mon_exp[m])) if mon_exp.get(m, 0) >= 30 else 1.0 for m in mon_act}
    n_c, I_c, A_c, f_c, day_c = [], [], [], [], []
    for k_ in sorted(new):
        cd = D(k_)
        if cd < launch or cd > E or new[k_] <= 0:
            continue
        A = (E - cd).days
        n = new[k_]
        uu = [0.0] * (A + 1)
        for L, v in lags_of(cf, k_).items():
            if L <= A:
                uu[L] += v
        I, run = [0.0] * (A + 1), 0.0
        for t in range(A + 1):
            run += uu[t]
            I[t] = min(1.0, max(0.0, 1 - run / n))
        day_c.append(k_)
        n_c.append(n)
        I_c.append(I)
        A_c.append(A)
        f_c.append(fmon.get(k_[:7], 1.0))
    young_keep = sum(n_c[c] * I_c[c][A_c[c]] for c in range(len(n_c)) if A_c[c] < SLEEP_DAYS)
    mos = aud_eng.tier_months(max(1, tmax + 1))           # the months a GA4 read of this history would have
    wins = [andaza_window(m) for m in mos]
    model_total, kfit, how, per = dead_model(n_c, I_c, A_c, f_c, r, a28k, young_keep, wins)
    scale = (sleeping / model_total) if model_total > 0 and not data_kam else None
    sc = scale if scale is not None else 1.0
    # today's DAU by install age (iday bands on E, real)
    bands_real = None
    if de and de.get("ab"):
        ga = de.get("a") or a1
        ab = de["ab"]
        bands_real = [v * a1 / ga for v in (ab[0] + ab[1] + ab[2], ab[3], ab[4], ab[5] + max(0, ga - (de.get("a4") or 0)))]
    # dead users by months: the complete GA4 read when there is one, else the estimate on the same months
    comp = _store_complete(store) if aud_mode != "andaza" else None
    au, ga4_err = None, None
    if comp is not None:
        try:
            au = ga4_part(comp, uni_filled_of())
        except Exception as ex_:                         # a broken store costs its GA4 part only (counted)
            au, ga4_err = None, type(ex_).__name__
    if au is None:
        au = andaza_part(day_c, n_c, I_c, A_c, per, mos, wins, sc, cf, new, E, andaza_window(1))
        au["coming"] = bool(isinstance(store, dict) and store.get("partial"))
    au.pop("_rows_dead", None)
    au["bands"] = [round(v) for v in bands_real] if bands_real else None
    # day-wise: of each install day's users, how many removed (by when) and how many still installed, as of E
    c0 = D(cf["start"])
    fl = ua.get("flags") or {}
    inc = sorted((fl.get("incomplete_days") or {}).keys())
    estd = sorted((fl.get("estimated_days") or {}).keys())
    dw_n, dw_u, dw_f = [], [], []
    dstart = max(launch, c0)
    for i in range((E - dstart).days + 1):
        c = dstart + timedelta(days=i)
        j = (c - c0).days
        n = int(cf["new"][j] or 0) if 0 <= j < len(cf["new"]) else 0
        age = (E - c).days
        bk = [0, 0, 0, 0, 0]
        for lag, u in (cf["lags"][j] if 0 <= j < len(cf["lags"]) else []):
            if lag > age:
                continue
            bk[0 if lag == 0 else 1 if lag <= 7 else 2 if lag <= 30 else 3 if lag <= 90 else 4] += int(u)
        ci = iso(c)
        c30 = iso(min(E, c + timedelta(days=30)))     # ~90% of an install day's uninstalls fall in its first 30 days
        if ci in inc:
            f = 1                                     # its own day's cells incomplete: "data adhoora"
        elif any(ci < d_ <= c30 for d_ in inc):
            f = 2                                     # a day within 30 days incomplete: removed may read low
        elif any(ci <= d_ <= c30 for d_ in estd):
            f = 3                                     # a filled day (≥70% read, scaled to its total) within 30: ≈
        else:
            f = 0
        if c > E - timedelta(days=7):
            f = f or 4                                # uninstalls of the newest 7 days still arrive (not final)
        dw_n.append(n)
        dw_u.extend(bk)
        dw_f.append(str(f))
    entry = {
        "k": aa["key"], "id": aa.get("app_id"), "n": aa.get("app") or aa["key"], "E": iso(E), "hs": iso(hs),
        "L": iso(launch), "lh": bool((ua.get("launch") or {}).get("hidden")),
        "ins": inst_total, "rem": removed, "inst": installed, "a1": a1, "a28": a28, "a28k": a28k, "un28": un28,
        "sl": sleeping, "kam": bool(data_kam),
        "j": {N: (None if v is None else [_r(v["open"], 5), _r(v["has"], 5), _r(v["gone"], 5), v["n"]])
              for N, v in journey.items()},
        "lt": {L: [_r(v["v"], 5), v["n"]] for L, v in longt.items()},
        "pk": pakke_today, "au": au, "dm": round(model_total), "maxm": int(tmax // MONTH),
        "arp": _r(arpdau, 8), "pm": _r(per_mau, 8), "rev28": round(rev28, 2), "a128": int(round(a1_28)),
        "dw": {"s": iso(dstart), "n": dw_n, "u": dw_u, "f": "".join(dw_f)},
    }
    try:                                        # the calculator's inputs: a broken Active file costs only them
        entry.update(usage28(det, rev_list, w28))
    except Exception:
        entry.update(usage28(None, (), ()))
    try:                                        # the "data se" fit's window (a broken return store costs only it)
        fw = fit_weeks(st, launch, E, new)
    except Exception:
        fw = None
    extra = {"own": own, "ret_arpu": ret_arpu, "freq": freq, "old_dau": old_dau, "old_a28": old_a28,
             "arpdau": arpdau, "rev28": rev28, "a1_28": a1_28, "journey": journey, "long": longt,
             "ga4_err": ga4_err, "scale": scale, "k": kfit, "k_how": how, "fw": fw}
    return entry, extra


# ── every app + the portfolio ────────────────────────────────────────────────────────────────────────────────────────
def _align(au, glob):
    """An app's dead / dead_lo on its own months → on the portfolio's months: a month it has as is; past its last
    window, a full app's users are all young (dead 0); any other month unknown (None) — engine.audience.portfolio's rule."""
    at = {m: i for i, m in enumerate(au["mo"])}
    last = au["mo"][-1] if au["mo"] else 0

    def one(arr):
        return [arr[at[m]] if m in at else (0 if au.get("full") and m > last else None) for m in glob]
    d = one(au["d"])
    lo = one(au["lo"]) if au.get("lo") is not None else list(d)   # an estimate has one number: its own range
    return d, lo


def portfolio_au(entries):
    """The all-apps "au" block over the apps the page pools (not "data kam"): tiered months up to the longest window,
    dead / dead_lo summed (None when an app can't say), install months summed, the most dead / active month."""
    ok = [e for e in entries if not e["kam"]]
    if not ok:
        return None
    top = max(m for e in ok for m in (e["au"]["mo"] or [1]))
    glob = aud_eng.tier_months(aud_eng.window_days(top))
    d, lo = [0] * len(glob), [0] * len(glob)
    rows = {}
    for e in ok:
        a = e["au"]
        ad, alo = _align(a, glob)
        for i in range(len(glob)):
            d[i] = None if d[i] is None or ad[i] is None else d[i] + ad[i]
            lo[i] = None if lo[i] is None or alo[i] is None else lo[i] + alo[i]
        for r in a["m"]:
            t = rows.setdefault(r[0], [r[0], 0, 0, 0, 0, 0, 0])
            t[1] += r[1]
            t[2] += r[2]
            t[3] += r[3]
            t[4] += r[4] if r[4] is not None else r[3]
            t[5] = max(t[5], r[5])
            t[6] += r[6] or 0
    m = [rows[k] for k in sorted(rows)]
    ins = sum(e["au"]["ins"] for e in ok)
    groups = {r[0]: {"installs": r[1], "young_days": [r[5]], "dead": [r[3]], "alive": [r[2] - r[3]]} for r in m if r[1]}
    srcs = sorted({e["au"]["src"] for e in ok})
    return {"src": srcs[0] if len(srcs) == 1 else "mix", "n_ga4": sum(1 for e in ok if e["au"]["src"] == "ga4"),
            "n_andaza": sum(1 for e in ok if e["au"]["src"] != "ga4"), "E": max(e["au"]["E"] for e in ok),
            "mo": glob, "full": True, "ins": ins, "inst": sum(e["au"]["inst"] for e in ok), "d": d, "lo": lo,
            "m": m, "most": aud_eng.most(groups, ins) if groups else None,
            "bands": [sum((e["au"]["bands"] or [0, 0, 0, 0])[j] for e in ok) for j in range(4)]}


def build_data(dashboard, data_dir, out_dir, counts, aud_mode=None):
    """→ the file's body (without v), or None when this build has no Active users / Uninstall data."""
    act = dashboard.get("active") if isinstance(dashboard, dict) else None
    uni = dashboard.get("uninstall") if isinstance(dashboard, dict) else None
    if not isinstance(act, dict) or not isinstance(uni, dict):
        return None
    port = act.get("portfolio")
    if not isinstance(port, dict) or not port.get("file"):
        return None
    U = _gz(os.path.join(out_dir, uni.get("asset") or "uninstall.json.gz"))
    PF = _gz(os.path.join(out_dir, port["file"]))
    uapps = {a.get("key"): a for a in U.get("apps") or []}
    pf = {a.get("key"): a for a in PF.get("apps") or []}
    from .engine import uninstall as ueng
    entries, extras = [], []
    for aa in act.get("apps") or []:
        key = aa.get("key")
        try:
            if not key or not aa.get("settled_till") or key not in uapps or key not in pf:
                raise KeyError("inputs")
            sp = os.path.join(data_dir, "ga4_uninstall", key + ".json.gz")
            st = _gz(sp)
            cf = _gz(os.path.join(out_dir, "uninstall_c_%s.json.gz" % key))
            x, cur = iday_x(data_dir, key)
            ap = os.path.join(data_dir, aud_eng_dir(), key + ".json.gz")
            store = None
            if os.path.exists(ap):
                try:
                    store = _gz(ap)
                except Exception:
                    store = None
                    counts["store_bad"] = counts.get("store_bad", 0) + 1
            det = None
            dp = os.path.join(out_dir, aa["file"]) if isinstance(aa.get("file"), str) else None
            if dp and os.path.exists(dp):
                try:
                    det = _gz(dp)
                except Exception:
                    counts["usage_bad"] = counts.get("usage_bad", 0) + 1
            entry, extra = app_entry(aa, uapps[key], st, pf[key], cf, x, cur, store,
                                     lambda st=st: ueng.fill_days(st), aud_mode=aud_mode, det=det)
        except Exception:
            counts["skipped"] = counts.get("skipped", 0) + 1
            continue
        if extra.get("ga4_err"):
            counts["ga4_bad"] = counts.get("ga4_bad", 0) + 1
        entries.append(entry)
        extras.append(extra)
    if not entries:
        return None
    # young apps: the all-apps typical old-user frequency, and their own revenue per DAU × the typical old/all ratio
    good = [x for x in extras if x["own"]]
    f_all = (sum(x["old_dau"] for x in good) / sum(x["old_a28"] for x in good)) if good else None
    rr = sorted(x["ret_arpu"] / x["arpdau"] for x in good if x["arpdau"])
    ratio = rr[len(rr) // 2] if rr else None
    for e, x in zip(entries, extras):
        if x["own"]:
            e["fq"], e["ra"], e["own"] = _r(x["freq"], 5), _r(x["ret_arpu"], 8), True
        else:
            e["fq"] = _r(f_all, 5)
            e["ra"] = _r((x["arpdau"] or 0) * ratio, 8) if ratio is not None else None
            e["own"] = False
    # "data se": each app's own fitted curve (FIT_MIN installs in the window), else the all-apps fit (every app's window
    # pooled); K with the sessions per active day of the page's per-open basis (old users where it has its own)
    all_kf = None
    try:
        fws = [x["fw"] for x in extras if x.get("fw")]
        all_fit = fit_app([[[sum(f[j][0][d] for f in fws) for d in range(FIT_DAYS + 1)],
                            [sum(f[j][1][d] for f in fws) for d in range(FIT_DAYS + 1)],
                            sum(f[j][2] for f in fws)] for j in range(FIT_WEEKS)]) if fws else None
        if all_fit is not None:
            all_kf = kf_entry(all_fit, "all", None)
    except Exception:
        all_fit = None
        counts["fit_bad"] = counts.get("fit_bad", 0) + 1
    for e, x in zip(entries, extras):
        try:
            fw = x.get("fw")
            own_fit = fit_app(fw) if fw and sum(w[2] for w in fw) >= FIT_MIN else None
            fit, src = (own_fit, "own") if own_fit is not None else (all_fit, "all")
            if (e.get("ec") or 0) > 0 and e["own"] and (e.get("ra") or 0) > 0 and (e.get("spr") or 0) > 0:
                s_ = e["spr"]
            elif (e.get("ec") or 0) > 0 and (e.get("ads") or 0) > 0 and (e.get("spu") or 0) > 0:
                s_ = e["spu"]
            else:
                s_ = None
            e["kf"] = kf_entry(fit, src, s_) if fit is not None else None
            if e["kf"] is not None and src == "all":
                e["kf"]["n"] = sum(w[2] for w in fw) if fw else 0        # the app's own installs in the window
        except Exception:
            e["kf"] = None
            counts["fit_bad"] = counts.get("fit_bad", 0) + 1
    # all apps together (journey / long-term weighted by each app's installs base; money sums)
    allj = {}
    for N in JOURNEY_DAYS:
        js = [(x["journey"][str(N)], x["journey"][str(N)]["n"]) for x in extras if x["journey"].get(str(N))]
        w = sum(n for _, n in js)
        if w:
            v = {m: sum(j[m] * n for j, n in js) / w for m in ("open", "has", "gone")}
            allj[str(N)] = [_r(v["open"], 5), _r(v["has"], 5), _r(v["gone"], 5), w, len(js)]
        else:
            allj[str(N)] = None
    alll = {}
    for lag in LONG_SHOW:
        vs = [(x["long"][lag]["v"], x["long"][lag]["n"]) for x in extras if lag in x["long"]]
        w = sum(n for _, n in vs)
        if w:
            alll[lag] = [_r(sum(v * n for v, n in vs) / w, 5), w, len(vs)]
    counts["ga4"] = sum(1 for e in entries if e["au"]["src"] == "ga4")
    counts["andaza"] = len(entries) - counts["ga4"]
    counts["coming"] = sum(1 for e in entries if e["au"].get("coming"))
    entries.sort(key=lambda e: -e["inst"])
    noga = [str(n.get("app") or "") for n in (U.get("no_ga4") or []) if n.get("app")]
    return {"gen": dashboard.get("generated_at"), "fx": dashboard.get("usd_inr"), "cur": PF.get("currency") or "USD",
            "E": max(e["E"] for e in entries),
            "apps": entries, "no_ga4": noga,
            "all": {"j": allj, "lt": alll, "rev28": round(sum(x["rev28"] for x in extras), 2),
                    "a1_28": sum(x["a1_28"] for x in extras), "au": portfolio_au(entries), "kf": all_kf}}


def aud_eng_dir():
    try:
        from .fetch import ga4_audience
        return ga4_audience.DIR
    except Exception:
        return "ga4_audience"


# ── the build step ───────────────────────────────────────────────────────────────────────────────────────────────────
def _remove(out_dir):
    try:
        os.remove(os.path.join(out_dir, FILE))
    except OSError:
        pass


def run(dashboard, data_dir, out_dir, s=None):
    """This build's Audience file → HEADER_PATHS (for _headers), or [] (no GA4 data this build, or a failure — the file
    removed, no pointer). Sets dashboard["audience"] last. Never raises."""
    global LINE
    LINE = None
    if not isinstance(dashboard, dict):
        return []
    dashboard.pop("audience", None)             # (the pointer only ever names THIS build's file)
    try:
        counts = {}
        data = build_data(dashboard, data_dir, out_dir, counts)
        if data is None:
            _remove(out_dir)
            LINE = "audience: apps 0, skipped %d, ga4 0, estimate 0, reading 0, kb 0" % counts.get("skipped", 0)
            return []
        body = dict(data, v=V)
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        gz = len(gzip.compress(raw, 9, mtime=0))
        if gz > MAX_GZ:
            _remove(out_dir)
            LINE = "audience: too big (%d kb), not written" % (gz // 1024)
            return []
        write_json_gz_stable(os.path.join(out_dir, FILE), body)
        dashboard["audience"] = {"file": FILE, "v": hashlib.sha1(raw).hexdigest()[:12]}
        LINE = ("audience: apps %d, skipped %d, ga4 %d, estimate %d, reading %d, kb %d"
                % (len(data["apps"]), counts.get("skipped", 0), counts.get("ga4", 0), counts.get("andaza", 0),
                   counts.get("coming", 0), gz // 1024))
        return list(HEADER_PATHS)
    except Exception as e:
        dashboard.pop("audience", None)
        _remove(out_dir)
        LINE = None
        print("audience skipped: %s" % type(e).__name__, file=sys.stderr)
        return []


def off(out_dir):
    """The switch off: the file removed (a rollback leaves the site as without the feature), no pointer, no line."""
    global LINE
    LINE = None
    _remove(out_dir)


def pop_line():
    """This build's counts line (None when the step did not run) — once."""
    global LINE
    line, LINE = LINE, None
    return line
