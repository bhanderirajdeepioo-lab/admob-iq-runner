"""Active users — pure math behind the GA4 "👥 Active users" tab (no I/O, no prints).

Input is one app's GA4 store (the same fill_days-ed store the uninstall engine read), the uninstall detail of that app
(read only — launch, stage, zoom, releases and the Update impact card are reused, never recomputed; everything kept is a
deep copy), its AdMob revenue and this tab's own private state. Output is the app's detail file (daily arrays, normal
bands, tiles, what changed, the return grid, the version table, a copy of the Update impact card) and its small summary
row.

  * RETURNING USERS R(d) = active users − that day's new installs, over the whole history. A day with a1 ≤ new is null
    (listed in rneg), never negative; a1 = 0 or a missing day is null too — unknown is never 0.
  * OLD USERS O(d) = R(d) − Y(d), Y = the recent installs coming back (the return cohorts where GA4 gave them, else the
    installs × the measured return rates ρ̂ — "≈", model mode). No ρ̂ yet (or more than MODEL_BACK_DAYS before its first
    window): no O at all.
  * DAILY NORMAL BAND ("FAST"): the median of the last 7 base days × a weekday factor, its residuals' own centre and
    spread; the band is ±BAND_K spreads = the spike threshold, so a dot outside the band is a What-changed row.
  * TILES: the last 7 SETTLED days vs the 28 before, judged against the same statistic at earlier ends (an empirical
    null — activity days move together, so √n errors are 2–4× too small). Uncentred on purpose: a steady decline reads
    "lower". Red / green only with an open alert; otherwise at most blue "Maybe".
  * ALERTS: act_drift (a steady shift, best of 36 start days, empirical null), act_spike (a day outside the band),
    act_break (tracking: a1 = 0, or R under half its normal), act_slow (3 months of slow decline), act_return (new users
    coming back on day N, recent week vs the 4 weeks before). Only settled days are judged (≤ E − ACT_LATE_DAYS); an
    obvious crash on a provisional day is an "Early look" info row only. Ad-spend swings are attributed to installs, not
    blamed on old users (§2.8); an eCPM-only move is the market's ("Ad price"), never an app alert.
  * EPISODES live in this tab's own state (active_state.json, owned by active_build): open → notify once → close after
    CLOSE_EVALS quiet advanced evaluations. The first evaluation, a moved stream, an outdated store, an input that just
    appeared (burn-in) and an episode that an open Update impact alert already covers are SEEDED: shown, never sent.
    Hourly re-runs with the same E change nothing.
"""

import copy
import math
from datetime import datetime, timedelta, timezone

from ..alerting.rules import fingerprint
from . import impact as imp
from . import uninstall as U

# ── constants (§2.2; every one is exported in consts) ──
ACT_V = 1
ACT_LATE_DAYS = imp.ACT_LATE_DAYS       # activity settles in 3 days (GA4's 72h); measured lateness later, not now
TILE_DAYS = 7
BASE_DAYS = 28
NULL_WEEKS_ACT = 13                     # the tile's null: the same statistic at every end of the 13 weeks before
NULL_MIN = 21                           # … at least 21 of them, else "Not enough data" (never a naive z)
SIGMA_FLOOR = imp.SIGMA_FLOOR           # HLL user counts are ±1%
Z_MAYBE = 2.0
DRIFT_Z = 4.0
WARN_Z = 5.0                            # a downward drift this far out is a warning (red), else watch
SPIKE_Z = 5.0
MIN_REL = {"ret_dau": .05, "sess": .05, "time": .05, "ads": .05}
SPIKE_MIN = {"ret_dau": .15, "sess": .10, "time": .15, "ads": .20}
SPIKE_MIN_USERS = 50
ADS_BROKE = -0.30                       # a single-day ads/user drop this big → warning
BREAK_FRAC = 0.5                        # R ≤ 50% of expected (expected ≥ MIN_DAU) → Check tracking
BREAK_CARRY_DAYS = 28                   # a break that runs on is judged against the last normal, for up to 28 days
MIN_VOL = {"ret_dau": 200, "sess": 200, "time": 200, "ads_users": 200, "ads_imps": 1000}
BAND_K = 5.0
WD_WEEKS = 8
WD_MIN = 4
WD_MIN_AMP = .02
LEVEL_DAYS = 7
LEVEL_MIN = 5
CENTRE_DAYS = 28
CENTRE_MIN = 14
SCALE_DAYS = 56
SCALE_MIN = 28
DRIFT_L = (7, 42)
DRIFT_BASE = 28
DRIFT_BASE_MIN = 21
DRIFT_SIDE = .7
DRIFT_COVER = .8
DRIFT_NULL = (7, 98)
DRIFT_MIN_USERS = 50                    # ret_dau drift: |Σ actual − expected| ≥ 50·√L users
SLOW_DAYS = 28
SLOW_GAP = 84
SLOW_MIN_REL = .10
SLOW_Z = 3.0
SLOW_NULL_WEEKS = 52
SLOW_NULL_MIN = 45
SLOW_MIN_KNOWN = 24
STEEP_DAYS = 21
ACT_READY_DAYS = 56
ACT_BURNIN_DAYS = 28
RET_ALERT_NS = (1, 3, 7, 14, 30)
RET_RECENT = 7
RET_PREV = 28
RET_ALL_MIN = 56
RET_BIG = 5000
RET_NULL_SHIFTS = (7, 91)
LADDER = {"naya": tuple(range(1, 15)) + (21, 30), "badh_raha": (1, 2, 3, 4, 5, 6, 7, 10, 14, 21, 30),
          "stable": (1, 3, 7, 14, 30)}
PHONE_COLS = (1, 3, 7, 14, 30)
MARKET_MIN_APPS = 8
MARKET_SHARE = .6
MARKET_MIN_REL = .05
MARKET_MIN_IMPS = 20000
MARKET_WEEKS = 9
LINK_BEFORE = 3
LINK_AFTER = 10
CLOSED_KEEP_DAYS = 400
MODEL_BACK_DAYS = 90
EDGE_RET_WINDOW = (45, 100)
OTHER_NET_MIN = .05
OTHER_NET_SWING = .05
EARLY_FRAC = .5
MEASURED_Y = 0.2                        # O is "measured" when at most 20% of Y was imputed
UNVERIFIED_USERS = imp.COH_MIN_USERS    # a batch of 14 install days under 200 installs: the fetch can't judge its edge
NODATA_SHARE = 0.5                      # a return-grid week whose cohorts hold < 50% of its installs: "No data"
USAGE_INC = 0.9                         # a usage day holding < 90% of the day's active users is incomplete
USAGE_PARTIAL = 0.05
ELASTIC_WEEKS = 26
ELASTIC_MIN = 12
BETA_DAYS = 7
MIX_SWING = 0.05                        # a share (new installs, recent returners, the r-slot gap) moved > 5 points
RET_SUM_MAX = 3.0                       # without return data: returners from the last 30 days' installs ≤ 3 × a
YS_MAX = 0.9                            # day's installs (Σ D1..D30 share; 30% D1 falling ~k^−½ gives 2.85), ≤ 90% of R
GAP_SHOW = 0.03
VER_ROWS = 10

# read-only reuse
ALERT_RECENT_DAYS = U.ALERT_RECENT_DAYS
SPIKE_MERGE_DAYS = U.SPIKE_MERGE_DAYS
SPIKE_KEEP_DAYS = U.SPIKE_KEEP_DAYS
CLOSE_EVALS = U.CLOSE_EVALS
FRESH_EVALS = U.FRESH_EVALS
DRIFT_PERSIST = U.DRIFT_PERSIST
DRIFT_CONFIRM_DAYS = U.DRIFT_CONFIRM_DAYS
HEAD_MIN_COHORTS = U.HEAD_MIN_COHORTS
ZERO_MIN_EXPECTED = U.ZERO_MIN_EXPECTED
SEV_ORDER = U.SEV_ORDER
TRI_AVG_WEEKS = U.TRI_AVG_WEEKS
YEAR_CLEAR_DAYS = U.YEAR_CLEAR_DAYS
RELEASE_SHARE = U.RELEASE_SHARE
TREND_MAX_WEEK = imp.TREND_MAX_WEEK
COHORT_DAYS = imp.COHORT_DAYS
MIN_DAU = imp.MIN_DAU
MIN_INSTALLS = imp.MIN_INSTALLS
MIN_EVENTS = imp.MIN_EVENTS
INSTALL_SWING = imp.INSTALL_SWING
NEWSHARE_SWING = imp.NEWSHARE_SWING
RECENT_SWING = imp.RECENT_SWING
VER_MIN_USERS = imp.VER_MIN_USERS
VER_MIN_REL = imp.VER_MIN_REL
BIAS_MIN = imp.BIAS_MIN
BIAS_MAX = imp.BIAS_MAX
SPREAD_SIGMA = U.SPREAD_SIGMA

WIN_METRICS = ("ret_dau", "sess", "time", "arpdau", "ads", "ecpm")
TILE_METRICS = ("ret_dau", "d1", "d7", "sess", "time", "arpdau", "ads", "ecpm")
BAND_METRICS = ("ret_dau", "sess", "time", "ads", "arpdau")
DRIFT_METRICS = ("ret_dau", "sess", "time", "ads")
D_NS = {"d1": 1, "d3": 3, "d7": 7, "d14": 14, "d30": 30}
IMPACT_ROW = {"ret_dau": "returning_dau", "sess": "sessions", "time": "time", "ads": "arpdau", "d1": "new_d1",
              "d7": "new_d7"}
SPIKY = ("act_spike", "act_break")
UNIT = {"ret_dau": "users", "sess": "num", "time": "sec", "usage": "num", "ads": "per1k"}
MPHRASE = {"ret_dau": "purane users", "sess": "sessions per user", "time": "time per user", "ads": "ads per user"}
NWORD = {1: "Agle din", 3: "3 din baad", 7: "7 din baad", 14: "14 din baad", 30: "30 din baad"}
SUMMARY_WORD = {"ret_dau": "purane users", "d1": "agle din wapsi", "d7": "hafte baad wapsi", "sess": "sessions per user",
                "time": "time per user", "arpdau": "revenue per user"}

CONSTS = {k.lower(): (list(v) if isinstance(v, tuple) else v) for k, v in dict(
    ACT_V=ACT_V, ACT_LATE_DAYS=ACT_LATE_DAYS, TILE_DAYS=TILE_DAYS, BASE_DAYS=BASE_DAYS, NULL_WEEKS=NULL_WEEKS_ACT,
    NULL_MIN=NULL_MIN, SIGMA_FLOOR=SIGMA_FLOOR, Z_MAYBE=Z_MAYBE, DRIFT_Z=DRIFT_Z, WARN_Z=WARN_Z, SPIKE_Z=SPIKE_Z,
    MIN_REL=MIN_REL, SPIKE_MIN=SPIKE_MIN, SPIKE_MIN_USERS=SPIKE_MIN_USERS, ADS_BROKE=ADS_BROKE, BREAK_FRAC=BREAK_FRAC,
    MIN_VOL=MIN_VOL, BAND_K=BAND_K, WD_WEEKS=WD_WEEKS, WD_MIN=WD_MIN, WD_MIN_AMP=WD_MIN_AMP, LEVEL_DAYS=LEVEL_DAYS,
    LEVEL_MIN=LEVEL_MIN, CENTRE_DAYS=CENTRE_DAYS, CENTRE_MIN=CENTRE_MIN, SCALE_DAYS=SCALE_DAYS, SCALE_MIN=SCALE_MIN,
    DRIFT_L=DRIFT_L, DRIFT_BASE=DRIFT_BASE, DRIFT_BASE_MIN=DRIFT_BASE_MIN, DRIFT_SIDE=DRIFT_SIDE,
    DRIFT_COVER=DRIFT_COVER, DRIFT_NULL=DRIFT_NULL, SLOW_DAYS=SLOW_DAYS, SLOW_GAP=SLOW_GAP, SLOW_MIN_REL=SLOW_MIN_REL,
    SLOW_Z=SLOW_Z, SLOW_NULL_WEEKS=SLOW_NULL_WEEKS, SLOW_NULL_MIN=SLOW_NULL_MIN, STEEP_DAYS=STEEP_DAYS,
    ACT_READY_DAYS=ACT_READY_DAYS, BURNIN_DAYS=ACT_BURNIN_DAYS, RET_ALERT_NS=RET_ALERT_NS, RET_RECENT=RET_RECENT,
    RET_PREV=RET_PREV, RET_ALL_MIN=RET_ALL_MIN, RET_BIG=RET_BIG, RET_NULL_SHIFTS=RET_NULL_SHIFTS,
    LADDER={k: list(v) for k, v in LADDER.items()}, PHONE_COLS=PHONE_COLS, MARKET_MIN_APPS=MARKET_MIN_APPS,
    MARKET_SHARE=MARKET_SHARE, MARKET_MIN_REL=MARKET_MIN_REL, MARKET_MIN_IMPS=MARKET_MIN_IMPS,
    MARKET_WEEKS=MARKET_WEEKS, LINK_BEFORE=LINK_BEFORE, LINK_AFTER=LINK_AFTER, CLOSED_KEEP_DAYS=CLOSED_KEEP_DAYS,
    MODEL_BACK_DAYS=MODEL_BACK_DAYS, EDGE_RET_WINDOW=EDGE_RET_WINDOW, OTHER_NET_MIN=OTHER_NET_MIN,
    OTHER_NET_SWING=OTHER_NET_SWING, EARLY_FRAC=EARLY_FRAC, ALERT_RECENT_DAYS=ALERT_RECENT_DAYS,
    YEAR_CLEAR_DAYS=YEAR_CLEAR_DAYS, COHORT_DAYS=COHORT_DAYS).items()}


# ── small helpers ────────────────────────────────────────────────────────────────────────────────

def _d(s):
    return U._d(s)


def _iso(d):
    return d.isoformat() if d else None


def _g4(x):
    """4 significant digits (ratios, bands)."""
    return None if x is None else float("%.4g" % x)


def _m4(x):
    return None if x is None else round(x, 4)


def _int(x):
    return None if x is None else int(round(x))


def _med(v):
    return U.median(v)


def _spread(v, c):
    return U.spread(v, c)


def _sgn(x):
    return 1 if x > 0 else -1 if x < 0 else 0


def _users(x):
    return "{:,}".format(int(round(x)))


def _num2(x):
    return ("%.2f" % x).rstrip("0").rstrip(".") if x < 10 else "%.1f" % x


def _pts(x):
    s = ("%.1f" % abs(x)).rstrip("0").rstrip(".")
    return s


def retention_date(v):
    """The config's GA4_RETENTION_CHANGED → a date, or None (empty / not a date: the reason is never claimed)."""
    try:
        return _d(v) if v else None
    except (TypeError, ValueError):
        return None


def min_pp(p):
    """The smallest return move (in points) worth a colour or an alert at a base share p (fraction)."""
    if p is None:
        return 0.5
    return max(min(max(0.15 * p * 100, 0.5), 1.5), 0.05 * p * 100)


# ── revenue on GA4 days, with a known-mask ────────────────────────────────────────────────────────

def _overlap_fn(tz_r, tz_g):
    """fn(GA4 day) → the AdMob days it overlaps (share > 0), DST-aware — the days impact._revenue_fn blends."""
    from zoneinfo import ZoneInfo
    try:
        zr = ZoneInfo(tz_r or "UTC")
    except Exception:
        zr = ZoneInfo("UTC")
    try:
        zg = ZoneInfo(tz_g or "UTC")
    except Exception:
        zg = ZoneInfo("UTC")
    if zr.key == zg.key:
        return lambda d: (d,)

    def start(day, z):
        return datetime(day.year, day.month, day.day, tzinfo=z).astimezone(timezone.utc)

    def f(d):
        s, t = start(d, zg), start(d + timedelta(days=1), zg)
        out = []
        for j in range(-2, 3):
            e = d + timedelta(days=j)
            if min(t, start(e + timedelta(days=1), zr)) > max(s, start(e, zr)):
                out.append(e)
        return tuple(out)
    return f


def _rev_series(revenue, key, tz_g, days):
    """revenue[key] ({AdMob day: [micros, impressions]}) → per GA4 day (revenue, impressions) or None: known only when
    every AdMob day it overlaps is known and ≤ till (impact._revenue_fn reads a missing in-span day as 0 — here it is
    "No ad data", never 0). An AdMob day is known when the app has its row — or (the network report, key "days") when
    its account's report has rows that day (revenue["cover_days"]: the app earned nothing), or it is a one-day hole
    between two rows: a real 0."""
    src = {k: v for k, v in ((revenue or {}).get(key) or {}).items() if v is not None}
    H = len(days)
    if not src:
        return None, None
    cover = set((revenue.get("cover_days") or ())) if key == "days" else set()
    f, _ = imp._revenue_fn({"tz": revenue.get("tz"), "till": revenue.get("till"), "days": src}, tz_g)
    over = _overlap_fn(revenue.get("tz"), tz_g)
    first, till = _d(min(src)), _d(revenue.get("till") or max(src))

    def known(e):
        k = e.isoformat()
        if k in src or k in cover:
            return True
        return ((e - timedelta(days=1)).isoformat() in src and (e + timedelta(days=1)).isoformat() in src)
    rev, imps = [None] * H, [None] * H
    for i, d in enumerate(days):
        if d < first - timedelta(days=2) or d > till + timedelta(days=2):
            continue
        ok = True
        for e in over(d):
            if e < first or e > till or not known(e):
                ok = False
                break
        if not ok:
            continue
        v = f(d)
        if v is not None:
            rev[i], imps[i] = v[0], v[1]
    return rev, imps


# ── the per-app data: daily arrays, cohorts, returners ───────────────────────────────────────────

def _pref(vals):
    out = [0.0] * (len(vals) + 1)
    run = 0.0
    for i, v in enumerate(vals):
        if v is not None:
            run += v
        out[i + 1] = run
    return out


def _psum(p, a, b):
    """Σ over indexes [a, b] of prefix array p (clipped)."""
    a = max(a, 0)
    b = min(b, len(p) - 2)
    return p[b + 1] - p[a] if b >= a else 0.0


def returners(P, d, rho, K):
    """Y(d) = Σ_{k=1..K} (the cohort d−k's day-k actives when it is usable, else its installs × ret_k × ρ̂_k) → (Y, the
    imputed part)."""
    y = yi = 0.0
    A, usable, new, rk = P["A"], P["usable"], P["new"], P["ret_k"]
    for k in range(1, K + 1):
        c = d - k
        if c < 0:
            continue
        a = A[c]
        if usable[c] and a is not None and len(a) > k:
            y += a[k]
        else:
            v = (new[c] or 0) * rk * rho[k]
            y, yi = y + v, yi + v
    return y, yi


def _rho_at(P, d):
    """ρ̂_k at day index d over the usable install days [d−28−k, d−1−k] with c + k ≤ S, ≥ 14 of them; K = the last k
    every k' ≤ k qualifies for → (rho, K) or None."""
    rho, K, iS = {}, 0, P["iS"]
    for k in range(1, COHORT_DAYS + 1):
        hi, lo = min(d - 1 - k, iS - k), max(0, d - 28 - k)
        if hi < lo:
            break
        pc = P["PC"][k]
        if pc[hi + 1] - pc[lo] < 14:
            break
        t = P["PT"][k][hi + 1] - P["PT"][k][lo]
        if t <= 0:
            break
        rho[k], K = (P["PA"][k][hi + 1] - P["PA"][k][lo]) / t, k
    return (rho, K) if K else None


def _steep_mask(x, iS):
    """μ(d) = median over settled j ∈ [d−20, d] of log(x(j)/x(j−7)); |μ| > TREND_MAX_WEEK → steep (no band, no
    judgement: a launch / growth phase is never extrapolated). Needs a third of the days."""
    H = len(x)
    wow = [None] * H
    for j in range(7, H):
        a, b = x[j], x[j - 7]
        if a and b and a > 0 and b > 0:
            wow[j] = math.log(a / b)
    out = [False] * H
    need = STEEP_DAYS // 3
    for d in range(H):
        v = [w for w in wow[max(0, d - STEEP_DAYS + 1):min(d, iS) + 1] if w is not None]
        if len(v) >= need:
            m = _med(v)
            out[d] = abs(m) > TREND_MAX_WEEK
    return out


class _Fast:
    """The daily normal band of one metric, built day by day (every quantity of day d reads only days before it, so the
    mask of a day can still change — a tracking break — before later days read it)."""

    def __init__(self, x, ok, steep, wd, poisson=False):
        H = len(x)
        self.x, self.ok, self.steep, self.wd, self.poisson = x, ok, steep, wd, poisson
        self.e, self.r, self.c = [None] * H, [None] * H, [None] * H
        self.med, self.lo, self.hi, self.z = [None] * H, [None] * H, [None] * H, [None] * H
        self.lv, self.lf = [None] * H, [None] * H          # the level and weekday factors behind e (a carried normal)
        self._lr = {}

    def _lrat(self, j):
        v = self._lr.get(j, 0)
        if v != 0:
            return v
        x, ok = self.x, self.ok
        v = None
        if j >= 3 and j + 3 < len(x) and all(ok[j + q] for q in range(-3, 4)):
            m = sum(x[j + q] for q in range(-3, 4)) / 7
            if m > 0 and x[j] > 0:
                v = math.log(x[j] / m)
        self._lr[j] = v
        return v

    def carried(self, d, last):
        """The normal of day d carried from day `last` (its level × day d's weekday factor) — a tracking break that
        runs on judges every day against the last normal it had, never against its own broken days."""
        if last is None or self.lv[last] is None:
            return None
        return self.lv[last] * math.exp(self.lf[last][self.wd[d]])

    def step(self, d):
        x, ok, wd = self.x, self.ok, self.wd
        if self.steep[d]:
            return
        groups = [[], [], [], [], [], [], []]
        for j in range(max(3, d - 7 * WD_WEEKS), d - 3):
            v = self._lrat(j)
            if v is not None:
                groups[wd[j]].append(v)
        lf = [_med(g) if len(g) >= WD_MIN else 0.0 for g in groups]
        mean = sum(lf) / 7
        lf = [v - mean for v in lf]
        if math.exp(max(lf) - min(lf)) - 1 < WD_MIN_AMP:
            lf = [0.0] * 7
        vals = [x[j] / math.exp(lf[wd[j]]) for j in range(max(0, d - LEVEL_DAYS), d) if ok[j]]
        if len(vals) < LEVEL_MIN:
            return
        e = _med(vals) * math.exp(lf[wd[d]])
        if e <= 0:
            return
        self.e[d] = e
        self.lv[d], self.lf[d] = _med(vals), lf
        if x[d] is not None and x[d] > 0:
            self.r[d] = math.log(x[d] / e)
        rs = [self.r[j] for j in range(max(0, d - CENTRE_DAYS), d) if ok[j] and self.r[j] is not None]
        if len(rs) < CENTRE_MIN:
            return
        c = _med(rs)
        self.c[d] = c
        dev = [abs(self.r[j] - self.c[j]) for j in range(max(0, d - SCALE_DAYS), d)
               if ok[j] and self.r[j] is not None and self.c[j] is not None]
        if len(dev) < SCALE_MIN:
            return
        sg = max(SPREAD_SIGMA * sum(dev) / len(dev), SIGMA_FLOOR, (1 / math.sqrt(e)) if self.poisson else 0.0)
        self.med[d] = e * math.exp(c)
        self.lo[d] = e * math.exp(c - BAND_K * sg)
        self.hi[d] = e * math.exp(c + BAND_K * sg)
        if self.r[d] is not None:
            self.z[d] = (self.r[d] - c) / sg


def prepare(store, udet, revenue, E, cfg=None, late_un=U.LATE_DAYS):
    """Everything an evaluation reads, computed ONCE per app (the whole history; each day's numbers read only the days
    before it, so an earlier end — the replay, the history — reuses them) → P."""
    cfg = cfg or {}
    E = _d(E)
    hs = _d(udet.get("history_start") or store["history_start"])
    H = max(0, (E - hs).days + 1)
    S = E - timedelta(days=ACT_LATE_DAYS)
    iS = (S - hs).days
    launch = udet.get("launch") or {}
    i0 = (_d(launch["day"]) - hs).days if launch.get("hidden") and launch.get("day") else 0
    i0 = max(0, min(i0, H))
    cx = imp._context(store, None, {"hs": hs}, i0, revenue, E, late_un)
    days = [hs + timedelta(days=i) for i in range(H)]
    iso = [d.isoformat() for d in days]
    wd0 = hs.weekday()
    wd = [(wd0 + i) % 7 for i in range(H)]
    P = {"hs": hs, "E": E, "S": S, "H": H, "iS": iS, "iE": H - 1, "i0": i0, "days": days, "iso": iso, "wd": wd,
         "cx": cx, "tz": store.get("time_zone") or "UTC", "ret_k": cx["ret_k"],
         "launch_day": _d(launch["day"]) if launch.get("day") else hs, "cfg": cfg}
    # daily totals
    daily = store.get("daily") or {}
    a1, new, R, rneg = [None] * H, [None] * H, [None] * H, set()
    for i in range(H):
        r = daily.get(iso[i])
        if not r:
            continue
        a, n = r.get("a1"), r.get("new")
        a1[i] = None if a is None else int(a)
        new[i] = None if n is None else int(n)
        if a1[i] and new[i] is not None:
            if a1[i] > new[i]:
                R[i] = a1[i] - new[i]
            else:
                rneg.add(i)
    P.update(a1=a1, new=new, R=R, rneg=rneg)
    # usage (sessions / time): a day holding < 90% of the day's actives is incomplete (never judged)
    usage = store.get("usage") or {}
    u3 = {k: [None] * H for k in "nro"}
    s3 = {k: [None] * H for k in "nro"}
    t3 = {k: [None] * H for k in "nro"}
    inc = set()
    for i in range(H):
        u = usage.get(iso[i])
        if not u:
            continue
        v = {k: list(u.get(k) or [0, 0, 0]) + [0, 0, 0] for k in "nro"}
        tot = sum(int(v[k][0] or 0) for k in "nro")
        if a1[i] and tot < USAGE_INC * a1[i]:
            inc.add(i)
            continue
        for k in "nro":
            u3[k][i], s3[k][i], t3[k][i] = int(v[k][0] or 0), int(v[k][1] or 0), int(v[k][2] or 0)
    P.update(u=u3, s=s3, t=t3, inc=inc, has_usage=bool(usage),
             usage_from=_d(cx["usage_from"]) if cx.get("usage_from") else None)
    # revenue on GA4 days (known-mask), + every mediation source (all_days) for the other-network share
    rev, imps = _rev_series(revenue, "days", P["tz"], days) if revenue else (None, None)
    arev, aimp = _rev_series(revenue, "all_days", P["tz"], days) if revenue and revenue.get("all_days") else (None, None)
    P.update(rev=rev, imp=imps, arev=arev, aimp=aimp, currency=(revenue or {}).get("currency") or "USD",
             rev_tz=(revenue or {}).get("tz"), tz_blend=bool(cx.get("tz_blend")))
    # return cohorts: usable = ok, t > 0 (when installs came), a[0]/t in [0.9, 1.1], on or after ret_from
    ret = store.get("ret") or {}
    rf = _d(store["ret_from"]) if store.get("ret_from") else None
    A, T, usable = [None] * H, [None] * H, [False] * H
    bad0 = empty = 0
    for i in range(H):
        e = ret.get(iso[i])
        if not e:
            continue
        t = int(e.get("t") or 0)
        a = [int(x or 0) for x in (e.get("a") or [])]
        A[i], T[i] = a, t
        if not e.get("ok"):
            continue
        if t <= 0:
            if (new[i] or 0) > 0:
                empty += 1
            continue
        if not a or not 0.9 <= a[0] / t <= 1.1:
            bad0 += 1
            continue
        if rf and days[i] < rf:
            continue
        usable[i] = True
    PA, PT, PC = [None] * (COHORT_DAYS + 1), [None] * (COHORT_DAYS + 1), [None] * (COHORT_DAYS + 1)
    for N in range(1, COHORT_DAYS + 1):
        pa, pt, pc = [0] * (H + 1), [0] * (H + 1), [0] * (H + 1)
        for i in range(H):
            ok = usable[i] and len(A[i]) > N
            pa[i + 1] = pa[i] + (A[i][N] if ok else 0)
            pt[i + 1] = pt[i] + (T[i] if ok else 0)
            pc[i + 1] = pc[i] + (1 if ok else 0)
        PA[N], PT[N], PC[N] = pa, pt, pc
    P.update(A=A, T=T, usable=usable, PA=PA, PT=PT, PC=PC, ret_from=rf, has_ret=bool(ret), ret_bad0=bad0,
             ret_empty=empty, ret=ret)
    # recent returners Y and old users O (§2.4)
    Y, yi, oq, Kd = [None] * H, [None] * H, [None] * H, [None] * H
    rhos = [_rho_at(P, d) for d in range(H)] if any(usable) else [None] * H
    first = next((d for d in range(H) if rhos[d]), None)
    if first is not None:
        ws, last = first - 29, None
        for d in range(H):
            src, own = rhos[d], True
            if src is None:
                own = False
                if d < first:
                    if d < ws - MODEL_BACK_DAYS:
                        continue
                    src = rhos[first]
                else:
                    src = last
            else:
                last = src
            if src is None:
                continue
            y, yv = returners(P, d, src[0], src[1])
            Y[d], yi[d], Kd[d] = y, yv, src[1]
            oq[d] = 2 if own and yv <= MEASURED_Y * y else 1
    old = [None] * H
    for d in range(H):
        if R[d] is not None and Y[d] is not None and R[d] - Y[d] > 0:
            old[d] = R[d] - Y[d]
    P.update(Y=Y, yi=yi, oq=oq, old=old, Kd=Kd)
    # metric numerators / denominators (per-user values: ratios of sums, never means of ratios)
    num, den = {}, {}
    num["ret_dau"], den["ret_dau"] = R, [1 if r is not None else None for r in R]
    num["a1"], den["a1"] = [a if a else None for a in a1], [1 if a else None for a in a1]
    for m, src in (("sess", s3["r"]), ("time", t3["r"])):
        num[m] = [src[i] if u3["r"][i] else None for i in range(H)]
        den[m] = [u3["r"][i] if u3["r"][i] else None for i in range(H)]
    if rev is not None:
        num["ads"] = [imps[i] if rev[i] is not None and a1[i] else None for i in range(H)]
        den["ads"] = [a1[i] if rev[i] is not None and a1[i] else None for i in range(H)]
        num["arpdau"] = [rev[i] * 1000 if rev[i] is not None and a1[i] else None for i in range(H)]
        den["arpdau"] = den["ads"]
        num["ecpm"] = [rev[i] * 1000 if rev[i] is not None and imps[i] else None for i in range(H)]
        den["ecpm"] = [imps[i] if rev[i] is not None and imps[i] else None for i in range(H)]
    else:
        for m in ("ads", "arpdau", "ecpm"):
            num[m], den[m] = [None] * H, [None] * H
    x = {m: [num[m][i] / den[m][i] if num[m][i] is not None and den[m][i] else None for i in range(H)] for m in num}
    P.update(num=num, den=den, x=x)
    steep = {m: _steep_mask(x[m], iS) for m in x}
    P["steep"] = steep
    # bands: returning users and actives in lockstep — a tracking break found on day d leaves every later base.
    # Revenue metrics: a revenue-known day that earned 0 (AdMob has its row) is a real 0 — counted in every sum and
    # day count (known / valid); only the band's logs need x > 0 (base).
    brk = [False] * H
    early = []
    zero_ok = ("ads", "arpdau", "ecpm")
    known = {m: [x[m][i] is not None and (x[m][i] > 0 or (m in zero_ok and x[m][i] == 0)) and i >= i0
                 and i not in rneg for i in range(H)] for m in x}
    base = {m: [known[m][i] and x[m][i] > 0 and i <= iS and not steep[m][i] for i in range(H)] for m in x}
    sbase = {m: [known[m][i] and i <= iS and not steep[m][i] for i in range(H)] for m in x}
    fr = _Fast(x["ret_dau"], base["ret_dau"], steep["ret_dau"], wd, poisson=True)
    fa = _Fast(x["a1"], base["a1"], steep["a1"], wd)
    last_r = last_a = None                             # the last day each had a normal of its own
    run = False                                        # the day before was a break (or an early look)
    for d in range(H):
        fr.step(d)
        fa.step(d)
        er, ea = fr.e[d], fa.e[d]
        if run:                                        # a break that runs on: judged against the last normal
            if er is None and last_r is not None and d - last_r <= BREAK_CARRY_DAYS:
                er = fr.carried(d, last_r)
            if ea is None and last_a is not None and d - last_a <= BREAK_CARRY_DAYS:
                ea = fa.carried(d, last_a)
        if fr.e[d] is not None:
            last_r = d
        if fa.e[d] is not None:
            last_a = d
        run = False
        if d < i0:
            continue
        kind = None
        if a1[d] == 0 and ea is not None and ea >= ZERO_MIN_EXPECTED:
            kind = "zero"
        elif R[d] is not None and er is not None and er >= MIN_DAU and R[d] <= BREAK_FRAC * er:
            kind = "low"
        if kind is None:
            continue
        exp_ = ea if kind == "zero" else er
        if d <= iS:
            brk[d] = {"kind": kind, "exp": exp_}
            run = True
            for m in base:
                base[m][d] = False
                sbase[m][d] = False
        elif kind == "zero" or R[d] <= EARLY_FRAC * er:
            early.append((d, kind, exp_))
            run = True
    fast = {"ret_dau": fr, "a1": fa}
    for m in ("sess", "time", "ads", "arpdau"):
        f = _Fast(x[m], base[m], steep[m], wd)
        for d in range(H):
            f.step(d)
        fast[m] = f
    valid = {m: [known[m][i] and not brk[i] for i in range(H)] for m in x}
    P.update(brk=brk, early=early, fast=fast, base=base, sbase=sbase, valid=valid)
    # prefix sums over valid days (tiles, drift W sums, slow)
    pn, pd, pc = {}, {}, {}
    for m in x:
        pn[m] = _pref([num[m][i] if valid[m][i] else None for i in range(H)])
        pd[m] = _pref([den[m][i] if valid[m][i] else None for i in range(H)])
        pc[m] = _pref([1 if valid[m][i] else None for i in range(H)])
    P.update(pn=pn, pd=pd, pc=pc)
    P["p_new"] = _pref([new[i] if i >= i0 else None for i in range(H)])
    P["p_newc"] = _pref([1 if new[i] is not None and i >= i0 else None for i in range(H)])
    P["p_a1"] = _pref([a1[i] if valid["ret_dau"][i] else None for i in range(H)])
    P["p_Y"] = _pref([Y[i] if valid["ret_dau"][i] else None for i in range(H)])
    P["p_yc"] = _pref([1 if valid["ret_dau"][i] and Y[i] is not None else None for i in range(H)])
    P["p_ur"] = _pref([u3["r"][i] if u3["r"][i] and i >= i0 and not brk[i] else None for i in range(H)])
    P["p_uall"] = _pref([sum(u3[k][i] for k in "nro") if u3["r"][i] is not None and i >= i0 and not brk[i] else None
                         for i in range(H)])
    P["p_uR"] = _pref([R[i] if u3["r"][i] and R[i] is not None and i >= i0 and not brk[i] else None for i in range(H)])
    P["p_ua1"] = _pref([a1[i] if u3["r"][i] and a1[i] and i >= i0 and not brk[i] else None for i in range(H)])
    P["p_unew"] = _pref([new[i] if u3["r"][i] and a1[i] and i >= i0 and not brk[i] else None for i in range(H)])
    if arev is not None and rev is not None:
        both = [rev[i] is not None and arev[i] is not None and imps[i] is not None and aimp[i] is not None
                for i in range(H)]
        P["p_nrev"] = _pref([rev[i] if both[i] else None for i in range(H)])
        P["p_arev"] = _pref([arev[i] if both[i] else None for i in range(H)])
        P["p_nimp"] = _pref([imps[i] if both[i] else None for i in range(H)])
        P["p_aimp"] = _pref([aimp[i] if both[i] else None for i in range(H)])
    P["drift"] = {m: _drift_table(P, m) for m in DRIFT_METRICS}
    return P


# ── drift: D_L(e) for every end and window length, once ────────────────────────────────────────

def _drift_table(P, m):
    """D[L][e] = log(Σ_W num ÷ Ê) of the W = [e−L+1, e] days against the 28 base days before it (weekday-pooled
    ratios), for every e ≤ S and L in DRIFT_L — computed once by accumulating over e for each start s → {"D", "G"}."""
    H, iS, wd = P["H"], P["iS"], P["wd"]
    num, den, base, valid, steep = P["num"][m], P["den"][m], P["sbase"][m], P["valid"][m], P["steep"][m]
    Lmin, Lmax = DRIFT_L
    D = {L: {} for L in range(Lmin, Lmax + 1)}
    G = {}
    if H == 0:
        return {"D": D, "G": G}
    pbn = [[0.0] * (H + 1) for _ in range(7)]
    pbd = [[0.0] * (H + 1) for _ in range(7)]
    pbc = [[0] * (H + 1) for _ in range(7)]
    for i in range(H):
        for k in range(7):
            pbn[k][i + 1], pbd[k][i + 1], pbc[k][i + 1] = pbn[k][i], pbd[k][i], pbc[k][i]
        if base[i]:
            k = wd[i]
            pbn[k][i + 1] += num[i]
            pbd[k][i + 1] += den[i]
            pbc[k][i + 1] += 1
    for s in range(DRIFT_BASE, iS - Lmin + 2):
        a = s - DRIFT_BASE
        if steep[s - 1]:
            continue
        nb = [pbn[k][s] - pbn[k][a] for k in range(7)]
        db = [pbd[k][s] - pbd[k][a] for k in range(7)]
        cb = [pbc[k][s] - pbc[k][a] for k in range(7)]
        if sum(cb) < DRIFT_BASE_MIN or sum(db) <= 0 or sum(nb) <= 0:
            continue
        rB = sum(nb) / sum(db)
        g = [(nb[k] / db[k]) if cb[k] >= 2 and db[k] > 0 else rB for k in range(7)]
        G[s] = g
        eh = nw = 0.0
        cw = 0
        for e in range(s, min(s + Lmax, iS + 1)):
            if valid[e]:
                eh += den[e] * g[wd[e]]
                nw += num[e]
                cw += 1
            L = e - s + 1
            if L >= Lmin and cw >= DRIFT_COVER * L and eh > 0 and nw > 0:
                D[L][e] = math.log(nw / eh)
    return {"D": D, "G": G}


def _drift_at(P, m, e, caps=None):
    """The best steady shift ending at day e (settled), per direction → {"up": condition|None, "down": …} (§2.7
    act_drift). Each direction is judged on its own (a stale long rise never hides the current fall). A window's
    null is the same statistic at the 92 ends before the window starts (never the window itself, so a trend that
    runs on is never its own yardstick); caps = {dir: day index}: while that direction's story is open, the null from
    before it began counts too — the smaller spread wins, so a story that runs on stays open and never flaps."""
    tb = P["drift"][m]
    D, G = tb["D"], tb["G"]
    steep = P["steep"][m]
    span = DRIFT_NULL[1] - DRIFT_NULL[0]
    cands = {"up": [], "down": []}
    for L in range(DRIFT_L[0], DRIFT_L[1] + 1):
        x = D[L].get(e)
        if x is None or abs(math.exp(x) - 1) < MIN_REL[m]:
            continue
        dr = "up" if x > 0 else "down"
        DL = D[L]
        sg = None
        his = [e - L]                                  # the last end before the window's first day
        if caps and caps.get(dr) is not None and caps[dr] < his[0]:
            his.append(caps[dr])                       # an open story: its null from before it began too — the
        for hi in his:                                 # smaller spread wins (hysteresis only ever keeps it open)
            nul = [DL[j] for j in range(hi - span, hi + 1) if j in DL and not steep[j]]
            if len(nul) >= NULL_MIN:
                v = max(_spread(nul, _med(nul)), SIGMA_FLOOR)
                sg = v if sg is None else min(sg, v)
        if sg is None:
            continue
        z = x / sg
        if abs(z) >= DRIFT_Z:
            cands[dr].append((abs(z), L, z, x))
    num, den, valid, wd = P["num"][m], P["den"][m], P["valid"][m], P["wd"]
    out = {"up": None, "down": None}
    for dr, cs in cands.items():
        cs.sort(key=lambda c: (-c[0], -c[1]))                  # ties: the longer window (the earlier start)
        for _, L, z, x in cs:
            s = e - L + 1
            g = G[s]
            eh = nw = dw = 0.0
            same = tot = 0
            for d in range(s, e + 1):
                if not valid[d]:
                    continue
                ex = den[d] * g[wd[d]]
                eh, nw, dw = eh + ex, nw + num[d], dw + den[d]
                if ex > 0:
                    tot += 1
                    same += 1 if ((num[d] / ex) > 1) == (x > 0) else 0
            if not tot or same / tot < DRIFT_SIDE:
                continue
            if m == "ret_dau" and abs(nw - eh) < DRIFT_MIN_USERS * math.sqrt(L):
                continue
            out[dr] = {"metric": m, "L": L, "s": s, "e": e, "z": z, "D": x, "rel": math.exp(x) - 1,
                       "before": eh / dw, "now": nw / dw, "exp_sum": eh, "act_sum": nw, "den_sum": dw,
                       "dir": dr, "bfrom": s - DRIFT_BASE, "bto": s - 1}
            break
    return out


# ── slow decline (3 months) ─────────────────────────────────────────────────────────────────────

def _slow_q(P, e):
    """Q = log(mean R over [e−27, e] ÷ mean R over [e−111, e−84]) — each side ≥ 24 known days, post-launch."""
    a0, a1 = e - SLOW_DAYS + 1, e
    b0, b1 = a0 - SLOW_GAP, a1 - SLOW_GAP
    if b0 < P["i0"]:
        return None
    pn, pc = P["pn"]["ret_dau"], P["pc"]["ret_dau"]
    ca, cb = _psum(pc, a0, a1), _psum(pc, b0, b1)
    if ca < SLOW_MIN_KNOWN or cb < SLOW_MIN_KNOWN:
        return None
    ma, mb = _psum(pn, a0, a1) / ca, _psum(pn, b0, b1) / cb
    if ma <= 0 or mb <= 0:
        return None
    return math.log(ma / mb), mb, ma


def _slow_at(P, e):
    q = _slow_q(P, e)
    if q is None:
        return None
    nul = []
    for w in range(1, SLOW_NULL_WEEKS + 1):
        v = _slow_q(P, e - 7 * w)
        if v is not None:
            nul.append(v[0])
    if len(nul) < SLOW_NULL_MIN:
        return None
    sg = max(_spread(nul, _med(nul)), SIGMA_FLOOR)
    Q, before, now = q
    z = Q / sg
    if abs(math.exp(Q) - 1) < SLOW_MIN_REL or abs(z) < SLOW_Z:
        return None
    return {"metric": "ret_dau", "Q": Q, "z": z, "rel": math.exp(Q) - 1, "before": before, "now": now,
            "dir": "up" if Q > 0 else "down", "s": e - SLOW_DAYS + 1, "e": e,
            "bfrom": e - SLOW_DAYS + 1 - SLOW_GAP, "bto": e - SLOW_GAP}


# ── spikes, tracking breaks ─────────────────────────────────────────────────────────────────────

def _spike_day(P, m, d):
    """Is day d outside the band (|z| ≥ SPIKE_Z, a real effect)? → {dir, now, med, lo, hi, z, rel} or None."""
    f = P["fast"][m]
    z, med = f.z[d], f.med[d]
    if med is None or P["brk"][d] or not P["valid"][m][d]:
        return None
    x = P["x"][m][d]
    if m == "ads" and x == 0:                         # AdMob's row says 0 ads that day: a real 0 (not "No ad data")
        a1 = P["den"]["ads"][d] or 0                   # — only where the day had the users and the ads to lose
        if a1 < MIN_VOL["ads_users"] or med * a1 < MIN_VOL["ads_imps"]:
            return None
        return {"dir": "down", "now": 0.0, "med": med, "lo": f.lo[d], "hi": f.hi[d], "z": None, "rel": -1.0,
                "day": d}
    if z is None:
        return None
    rel = x / med - 1
    if abs(z) < SPIKE_Z or abs(rel) < SPIKE_MIN[m]:
        return None
    if m == "ret_dau" and abs(x - med) < SPIKE_MIN_USERS:
        return None
    return {"dir": "up" if z > 0 else "down", "now": x, "med": med, "lo": f.lo[d], "hi": f.hi[d], "z": z, "rel": rel,
            "day": d}


# ── new users coming back (D-metrics) ───────────────────────────────────────────────────────────

def _cw(P, N, lo, hi):
    """(Σ a[N], Σ t, usable days) over install indexes [lo, hi]."""
    lo, hi = max(lo, 0), min(hi, P["H"] - 1)
    if hi < lo:
        return 0, 0, 0
    pa, pt, pc = P["PA"][N], P["PT"][N], P["PC"][N]
    return pa[hi + 1] - pa[lo], pt[hi + 1] - pt[lo], pc[hi + 1] - pc[lo]


def _ret_null(P, N, r1):
    """σ_null: the spread of the same recent-vs-4-weeks Δ at shifts 7..91 install days back, fully usable windows only
    (≥ NULL_MIN shifts) → σ or None."""
    vals = []
    for sh in range(RET_NULL_SHIFTS[0], RET_NULL_SHIFTS[1] + 1):
        e1 = r1 - sh
        e0 = e1 - RET_RECENT + 1
        b1, b0 = e0 - 1, e0 - RET_PREV
        if b0 < P["i0"]:
            break
        aw, tw, cw = _cw(P, N, e0, e1)
        ab, tb, cb = _cw(P, N, b0, b1)
        if cw < RET_RECENT or cb < RET_PREV or not tw or not tb:
            continue
        vals.append(aw / tw - ab / tb)
    if len(vals) < NULL_MIN:
        return None
    return max(_spread(vals, _med(vals)), SIGMA_FLOOR * 0.1)


def _ret_ref(P, N, lo, hi):
    """The all-time share at N over usable post-launch install days [lo, hi] → (p, t, days)."""
    a, t, c = _cw(P, N, max(lo, P["i0"]), hi)
    return (a / t if t else None), t, c


def _phi_at(P, N, lo, hi):
    each = []
    for c in range(max(lo, 0), min(hi, P["H"] - 1) + 1):
        a = P["A"][c]
        if P["usable"][c] and a is not None and len(a) > N and P["T"][c]:
            each.append((a[N], P["T"][c], c))
    return U._phi(each)


def _ret_stats(P, N, iS, sig=True):
    """Recent 7 install days (c + N ≤ S) vs the 28 before, + all-time: the numbers the tile and act_return judge."""
    r1 = iS - N
    r0 = r1 - RET_RECENT + 1
    b1, b0 = r0 - 1, r0 - RET_PREV
    if b0 < P["i0"]:
        b0 = P["i0"]
    aw, tw, cw = _cw(P, N, r0, r1)
    ab, tb, cb = _cw(P, N, b0, b1)
    out = {"N": N, "r0": r0, "r1": r1, "b0": b0, "b1": b1, "aw": aw, "tw": tw, "cw": cw, "ab": ab, "tb": tb, "cb": cb}
    if not tw or not tb:
        return out
    pw, pb = aw / tw, ab / tb
    pbar = (aw + ab) / (tw + tb)
    phi = _phi_at(P, N, b0, b1)
    naive = math.sqrt(max(pbar * (1 - pbar), 0.0) * (1 / tw + 1 / tb) * phi)
    sn = _ret_null(P, N, r1) if sig else None
    se = max(naive, sn or 0.0) or None
    pa, ta, ca = _ret_ref(P, N, P["i0"], r0 - 1)
    out.update(pw=pw, pb=pb, d=pw - pb, se=se, z=(pw - pb) / se if se else None, sn=sn, phi=phi,
               all=pa if ca >= RET_ALL_MIN else None, all_days=ca, mpp=min_pp(pb))
    return out


# ── install mix (§2.8) ──────────────────────────────────────────────────────────────────────────

def _mean_new(P, a, b):
    c = _psum(P["p_newc"], a, b)
    return _psum(P["p_new"], a, b) / c if c else None


def beta_hat(P, s):
    """Elasticity of returning users to installs: the Theil–Sen slope of the weekly Δlog R on the 14-day Δlog installs
    over the 26 weeks before s (≥ 12 pairs), clipped to [0, 1] → β̂ or None."""
    pts = []
    pn, pc = P["pn"]["ret_dau"], P["pc"]["ret_dau"]
    for w in range(ELASTIC_WEEKS):
        t = s - 1 - 7 * w
        if t - 27 < P["i0"]:
            break
        c1, c0 = _psum(pc, t - 6, t), _psum(pc, t - 13, t - 7)
        if c1 < 5 or c0 < 5:
            continue
        r1, r0 = _psum(pn, t - 6, t) / c1, _psum(pn, t - 13, t - 7) / c0
        n1, n0 = _mean_new(P, t - 13, t), _mean_new(P, t - 27, t - 14)
        if not (r1 and r0 and n1 and n0) or r1 <= 0 or r0 <= 0 or n1 <= 0 or n0 <= 0:
            continue
        pts.append((math.log(n1 / n0), math.log(r1 / r0)))
    if len(pts) < ELASTIC_MIN:
        return None
    sl = [(pts[j][1] - pts[i][1]) / (pts[j][0] - pts[i][0]) for i in range(len(pts)) for j in range(i + 1, len(pts))
          if abs(pts[j][0] - pts[i][0]) > 1e-9]
    if len(sl) < ELASTIC_MIN:
        return None
    return min(1.0, max(0.0, _med(sl)))


def _cohort_mode(P, a, b):
    """Every day of [a, b] has a measured split (O exists) and Y sums the SAME number of return days K — while the
    return data's edge is still young, K grows day by day and a mean of Y over two windows would compare different
    things."""
    oq, Kd, valid = P["oq"], P["Kd"], P["valid"]["ret_dau"]
    ks = set()
    for i in range(max(a, 0), b + 1):
        if not valid[i]:
            continue
        if oq[i] is None:
            return False
        ks.add(Kd[i])
    return len(ks) <= 1


def _inst_attr(P, w0, w1, b0, b1, rel, beta):
    """How much of a returning-users change the install mix explains → {mode, inst_part, old_part, swing, pot, est}.
    swing: the installs' move (the same-direction larger of the plain W-vs-B move and the move over the install days
    that feed each window's returners — [w0−14, w1−1] vs [b0−14, b1−1]); pot: the most the installs could explain
    without return data (the recent installs' share of returning users at most RET_SUM_MAX × installs ÷ returning
    users — every returning user a recent install coming back on every one of 30 days would be ~3 × installs)."""
    sw_w, sw_b = _mean_new(P, w0, w1), _mean_new(P, b0, b1)
    raw = (sw_w / sw_b - 1) if sw_w is not None and sw_b else None
    n1, n0 = _mean_new(P, w0 - 14, w1 - 1), _mean_new(P, b0 - 14, min(b1 - 1, w0 - 15))
    lag = (n1 / n0 - 1) if n1 is not None and n0 else None
    swing = raw
    for v in (lag,):
        if v is not None and (swing is None or (_sgn(v) == _sgn(rel) and (_sgn(swing) != _sgn(rel)
                                                                          or abs(v) > abs(swing)))):
            swing = v
    cb = _psum(P["pc"]["ret_dau"], b0, b1)
    rb = _psum(P["pn"]["ret_dau"], b0, b1) / cb if cb else None
    pot = None
    if swing is not None and swing > -1 and rb and n0:
        pot = min(YS_MAX, n0 * RET_SUM_MAX / rb) * math.log(1 + swing)
    if _cohort_mode(P, b0, w1):
        cy_w, cy_b = _psum(P["p_yc"], w0, w1), _psum(P["p_yc"], b0, b1)
        if cy_w and cy_b and rb:
            yw, yb = _psum(P["p_Y"], w0, w1) / cy_w, _psum(P["p_Y"], b0, b1) / cy_b
            if rb > 0:
                part = (yw - yb) / rb
                est = any(P["oq"][i] == 1 or (P["yi"][i] or 0) > 0 for i in range(max(b0, 0), w1 + 1))
                return {"mode": "cohort", "inst_part": part, "old_part": rel - part, "swing": swing, "pot": None,
                        "est": est}
    if beta is not None:
        if n1 and n0 and n1 > 0 and n0 > 0:
            part = beta * math.log(n1 / n0)
            return {"mode": "elastic", "inst_part": part, "old_part": rel - part, "swing": swing, "pot": pot,
                    "est": True}
    return {"mode": "raw", "inst_part": None, "old_part": None, "swing": swing, "pot": pot, "est": False}


def _inst_rule(att, rel, min_old=None):
    """→ "info" (installs explain it: not an alert), "cap" (an alert at most watch, tag installs) or None.
    Without return cohorts the old users can't be told apart: a change the installs COULD explain half of (pot, the
    same direction) is capped — never "good", never red — and a big install swing always is (§2.8 rule 3)."""
    min_old = MIN_REL["ret_dau"] if min_old is None else min_old
    ip = att["inst_part"]
    if ip is not None and ip and _sgn(ip) == _sgn(rel) and abs(ip) >= 0.5 * abs(rel):
        return "info" if abs(att["old_part"]) < min_old else "cap"
    if att["mode"] != "cohort":
        pot = att.get("pot")
        if pot is not None and pot and _sgn(pot) == _sgn(rel) and abs(pot) >= 0.5 * abs(rel):
            return "cap"
        if att["swing"] is not None and abs(att["swing"]) >= INSTALL_SWING:
            return "cap"                              # no return cohorts: a big install swing is never the old users'
    return None


def _share(p_num, p_den, a, b):
    d = _psum(p_den, a, b)
    return _psum(p_num, a, b) / d if d else None


def _mix_moves(P, w0, w1, b0, b1, m):
    """Did the users' mix move > 5 points between W and B (new-install share of DAU, recent returners Y/R, the r-slot
    gap; for ads the other-network impression share)? → list of what moved."""
    out = []
    ns_w, ns_b = _share(P["p_new"], P["p_a1"], w0, w1), _share(P["p_new"], P["p_a1"], b0, b1)
    if ns_w is not None and ns_b is not None and abs(ns_w - ns_b) > NEWSHARE_SWING:
        out.append("newshare")
    if _cohort_mode(P, b0, w1):
        yr_w, yr_b = _share(P["p_Y"], P["pn"]["ret_dau"], w0, w1), _share(P["p_Y"], P["pn"]["ret_dau"], b0, b1)
        if yr_w is not None and yr_b is not None and abs(yr_w - yr_b) > RECENT_SWING:
            out.append("recent")
    if m in ("sess", "time"):
        g_w, g_b = gap_g(P, w0, w1), gap_g(P, b0, b1)
        if g_w is not None and g_b is not None and abs(g_w - g_b) > MIX_SWING:
            out.append("gap")
    if m == "ads":
        o_w, o_b = other_share(P, w0, w1, "imp"), other_share(P, b0, b1, "imp")
        if o_w is not None and o_b is not None and abs(o_w - o_b) >= OTHER_NET_SWING:
            out.append("other_net")
    return out


def gap_g(P, a, b):
    """g = (Σu_r − ΣR) ÷ ΣR over [a, b]: GA4's 'returning' slot also counts new installs on a 2nd session."""
    ur, rr = _psum(P["p_ur"], a, b), _psum(P["p_uR"], a, b)
    return (ur - rr) / rr if rr > 0 and ur else None


def other_share(P, a, b, what="rev"):
    """1 − Σ AdMob Network ÷ Σ every mediation source over [a, b] (earnings or impressions) → share or None."""
    if "p_arev" not in P:
        return None
    n, al = (("p_nrev", "p_arev") if what == "rev" else ("p_nimp", "p_aimp"))
    tot = _psum(P[al], a, b)
    if tot <= 0:
        return None
    return max(0.0, 1 - _psum(P[n], a, b) / tot)


# ── tiles ────────────────────────────────────────────────────────────────────────────────────────

def _win_stat(P, m, e, clip=False):
    """(Σnum, Σden, days) over the tile's W = [e−6, e] and B = [e−34, e−7]; None when B starts before the history —
    unless clip (the tile of a young app: the days there are, counted honestly)."""
    w0, w1, b0, b1 = e - TILE_DAYS + 1, e, e - TILE_DAYS - BASE_DAYS + 1, e - TILE_DAYS
    if b0 < 0 and not clip:
        return None
    pn, pd, pc = P["pn"][m], P["pd"][m], P["pc"][m]
    return (_psum(pn, w0, w1), _psum(pd, w0, w1), int(_psum(pc, w0, w1)),
            _psum(pn, b0, b1), _psum(pd, b0, b1), int(_psum(pc, b0, b1)))


def _T(P, m, e):
    s = _win_stat(P, m, e)
    if s is None:
        return None
    nw, dw, cw, nb, db, cb = s
    if cw < 5 or cb < 21 or dw <= 0 or db <= 0 or nw <= 0 or nb <= 0:
        return None
    return math.log((nw / dw) / (nb / db))


def _tile_null(P, m, e):
    vals = []
    i0, steep = P["i0"], P["steep"][m]
    for j in range(e - TILE_DAYS - 7 * NULL_WEEKS_ACT + 1, e - TILE_DAYS + 1):
        if j - TILE_DAYS - BASE_DAYS + 1 < i0 or j < 0 or steep[j]:
            continue
        t = _T(P, m, j)
        if t is not None:
            vals.append(t)
    if len(vals) < NULL_MIN:
        return None
    return max(_spread(vals, _med(vals)), SIGMA_FLOOR)


def _M(**kw):
    out = {"v": None, "base": None, "all": None, "rel": None, "pp": None, "z": None, "usual": None, "st": "normal",
           "why": None, "est": False, "n": 0, "nb": 0, "from": None, "to": None, "bfrom": None, "bto": None,
           "s": None}
    out.update(kw)
    return out


def _vfmt(m, v):
    if v is None:
        return None
    if m == "ret_dau":
        return _g4(v)
    if m in ("arpdau", "ecpm"):
        return _m4(v)
    return _g4(v)


def _tile_window(P, m, alerts):
    """A window metric's tile (§2.6): the last 7 settled days vs the 28 before. States in the spec's order (wait, noad,
    low, growth, an open alert, maybe, normal) — except that an open alert of the metric always decides the tile over
    low / growth: an alert never sits next to a tile that says "Not enough data"."""
    iS, iso = P["iS"], P["iso"]
    w0, b0, b1 = iS - TILE_DAYS + 1, iS - TILE_DAYS - BASE_DAYS + 1, iS - TILE_DAYS
    span = {"from": iso[w0] if 0 <= w0 < P["H"] else None, "to": iso[iS] if 0 <= iS < P["H"] else None,
            "bfrom": iso[b0] if 0 <= b0 < P["H"] else None, "bto": iso[b1] if 0 <= b1 < P["H"] else None}
    rev_m = m in ("arpdau", "ads", "ecpm")
    M = _M(est=bool(rev_m and P["rev"] is not None), **span)
    if (m in ("sess", "time") and not P["has_usage"]) or (rev_m and P["rev"] is None):
        M.update(st="wait", why="wait")
        return M
    s = _win_stat(P, m, iS, clip=True) if iS >= 0 else None
    if s is None:
        M.update(st="low", why="gap")
        return _with_alert(M, alerts, m)
    nw, dw, cw, nb, db, cb = s
    M.update(n=cw, nb=cb)
    if m == "ret_dau":
        M["s"] = [_int(nw), cw, _int(nb), cb]
        v = nw / cw if cw else None
        bs = nb / cb if cb else None
    else:
        M["s"] = [_int(nw), _int(dw), _int(nb), _int(db)]      # whole numbers (revenue ×1,000, impressions, users)
        v = nw / dw if dw else None
        bs = nb / db if db else None
    M["v"], M["base"] = _vfmt(m, v), _vfmt(m, bs)
    if v is not None and bs:
        M["rel"] = _m4(v / bs - 1)
    if rev_m and cw == 0:
        M.update(st="noad", why="noad")
        return M
    if (P["S"] - P["launch_day"]).days < ACT_READY_DAYS:
        M.update(st="low", why="young")
        return _with_alert(M, alerts, m)
    if cw < 5 or cb < 21 or v is None or not bs or v <= 0 or b0 < 0:
        M.update(st="low", why="gap")
        return _with_alert(M, alerts, m)
    vol = None
    if m == "ret_dau":
        vol = v < MIN_VOL["ret_dau"]
    elif m in ("sess", "time"):
        vol = (_psum(P["pd"][m], w0, iS) / cw) < MIN_VOL[m]
    else:
        a1m = _psum(P["pd"]["ads"], w0, iS) / max(1, _psum(P["pc"]["ads"], w0, iS))
        imm = _psum(P["pn"]["ads"], w0, iS) / max(1, _psum(P["pc"]["ads"], w0, iS))
        vol = a1m < MIN_VOL["ads_users"] or imm < MIN_VOL["ads_imps"]
    sg = _tile_null(P, m, iS)
    T = math.log(v / bs)
    if sg is not None:
        M["z"], M["usual"] = round(T / sg, 2), _m4(2 * sg)
    if vol:
        M.update(st="low", why="few")
        return _with_alert(M, alerts, m)
    if P["steep"][m][iS]:                             # before null_short: the null skips steep ends, so a steep app
        M.update(st="growth", why="steep")            # would otherwise always read "Not enough data"
        return _with_alert(M, alerts, m)
    if sg is None:
        M.update(st="low", why="null_short")
        return _with_alert(M, alerts, m)
    mr = MIN_REL.get(m, MIN_REL["ads"])
    z = T / sg
    if abs(v / bs - 1) >= mr and abs(z) >= Z_MAYBE:
        M["st"] = "maybe_dn" if T < 0 else "maybe_up"
    return _with_alert(M, alerts, m)


def _with_alert(M, alerts, m):
    """An open alert of the metric decides the tile (worse / watch / slow / break / better) — also over low / growth
    (an alert never sits next to a tile saying "Not enough data") — but never against the tile's own number: next to
    a clear fall an open rise gives way to an open fall, else to Maybe lower (and the reverse); never Normal while an
    alert is open."""
    am = "ads" if m == "arpdau" else m
    st = _alert_state(alerts, am)
    if st is None:
        return M
    rel = M.get("rel")
    if st != "break" and rel is not None and abs(rel) >= MIN_REL.get(am, MIN_REL["ads"]):
        want = "down" if rel < 0 else "up"
        st2 = _alert_state(alerts, am, want)
        if st2 is None:
            M.update(st="maybe_dn" if rel < 0 else "maybe_up",
                     why=M["why"] if M["st"] in ("maybe_dn", "maybe_up") else None)
            return M
        st = st2
    M.update(st=st, why=None)
    return M


def _alert_state(alerts, m, want=None):
    """An open alert of metric m decides the tile: worse / watch / slow / break / better (want "up" / "down": only
    the alerts of that direction, a tracking break never)."""
    best = None
    for a in alerts:
        if m not in a["_metrics"]:
            continue
        if want is not None and (a["dir"] != want or a["family"] == "act_break"):
            continue
        if a["family"] == "act_break":
            st = "break"
        elif a["family"] == "act_slow":
            st = "slow" if a["dir"] == "down" else "better"
        elif a["dir"] == "down":
            st = "worse" if a["severity"] == "warning" else "watch"
        else:
            st = "better"
        rank = ("worse", "break", "watch", "slow", "better").index(st)
        if best is None or rank < best[0]:
            best = (rank, st)
    return best[1] if best else None


def _tile_d(P, key, alerts, edges):
    N = D_NS[key]
    M = _M()
    if not P["has_ret"] or edges["ret_state"] == "wait":
        M.update(st="wait", why="wait")
        return M, None
    st = _ret_stats(P, N, P["iS"])
    iso, H = P["iso"], P["H"]
    for k, i in (("from", st["r0"]), ("to", st["r1"]), ("bfrom", st["b0"]), ("bto", st["b1"])):
        M[k] = iso[i] if 0 <= i < H else None
    M.update(n=st["cw"], nb=st["cb"], s=[st["aw"], st["tw"], st["ab"], st["tb"]])
    if "pw" not in st:
        M.update(st="low", why="gap")
        a = _alert_state(alerts, key)                 # an open alert decides the tile, never "Not enough data"
        if a:
            M.update(st=a, why=None)
        return M, st
    M.update(v=_g4(st["pw"]), base=_g4(st["pb"]), all=_g4(P["ref_raw"][N]),
             rel=_m4(st["pw"] / st["pb"] - 1) if st["pb"] else None,
             pp=round(st["d"] * 100, 2), z=round(st["z"], 2) if st["z"] is not None else None,
             usual=round(2 * st["se"] * 100, 2) if st["se"] else None)
    if P["nmax"] < N:
        M.update(st="low", why="gap")
    elif (P["S"] - P["launch_day"]).days < ACT_READY_DAYS:
        M.update(st="low", why="young")
    elif st["cw"] < 5 or st["cb"] < 21:
        M.update(st="low", why="gap")
    elif st["tw"] < MIN_INSTALLS or st["tb"] < MIN_INSTALLS or st["aw"] < MIN_EVENTS or st["ab"] < MIN_EVENTS:
        M.update(st="low", why="few")
    else:
        a = _alert_state(alerts, key)
        if a:
            M["st"] = a
        elif st["z"] is not None and abs(st["d"]) * 100 >= st["mpp"] and abs(st["z"]) >= Z_MAYBE:
            M["st"] = "maybe_dn" if st["d"] < 0 else "maybe_up"
            sw_w = _mean_new(P, st["r0"], st["r1"])
            sw_b = _mean_new(P, st["b0"], st["b1"])
            if sw_w is not None and sw_b and abs(sw_w / sw_b - 1) >= INSTALL_SWING:
                M["why"] = "installs"
    if M["st"] == "low":
        a = _alert_state(alerts, key)
        if a:
            M.update(st=a, why=None)
    return M, st


# ── the return grid ("How many came back") ──────────────────────────────────────────────────────

def _nmax(P, iS=None):
    """The largest N (≤ 30) reached by ≥ HEAD_MIN_COHORTS usable post-launch install days with c + N ≤ S."""
    iS = P["iS"] if iS is None else iS
    best = 0
    for N in range(1, COHORT_DAYS + 1):
        if P["PC"][N][max(0, min(P["H"], iS - N + 1))] - P["PC"][N][min(P["i0"], P["H"])] >= HEAD_MIN_COHORTS:
            best = N
    return best


def _grid(P, udet, edges, portfolio_edge):
    H, E, S, hs, i0, iso = P["H"], P["E"], P["S"], P["hs"], P["i0"], P["iso"]
    usable, T, new = P["usable"], P["T"], P["new"]
    nmax = P["nmax"]
    stage = udet.get("stage") or "badh_raha"
    cols = [N for N in LADDER.get(stage, LADDER["badh_raha"]) if 1 <= N <= nmax]
    if udet.get("zoom"):
        cols = sorted(set(cols) | {N for N in range(1, 15) if N <= nmax})
    ref, ref_users, ref_thin = [None] * 31, [None] * 31, [None] * 31
    phis = [None] * 31
    for N in range(1, COHORT_DAYS + 1):
        p, t, c = _ret_ref(P, N, i0, P["iS"] - N)
        ref[N] = _g4(p)
        ref_users[N] = int(t)
        ref_thin[N] = bool(c < 7 or t < 300)
        phis[N] = _phi_at(P, N, i0, P["iS"] - N) if p is not None else 1.0
    first_u = next((i for i in range(i0, H) if usable[i]), None)
    label = ("All-time normal" if first_u is None or first_u <= i0 + 6 or (P["launch_day"] and
             P["days"][first_u] <= P["launch_day"] + timedelta(days=6))
             else "Normal since %s" % U.fmt_day(P["days"][first_u], E))
    # the fixed 4-week average: the 4 newest full Mon–Sun weeks whose last day ≤ S
    b = S - timedelta(days=(S.weekday() + 1) % 7)
    a = b - timedelta(days=7 * TRI_AVG_WEEKS - 1)
    ia, ib = (a - hs).days, (b - hs).days
    avg = {"from": _iso(a), "to": _iso(b), "v": [None] * 31, "prov": [None] * 31}
    if ia >= 0:
        for N in range(1, COHORT_DAYS + 1):
            if b + timedelta(days=N) > E:
                continue
            x, t, _ = _cw(P, N, ia, ib)
            avg["v"][N] = _g4(x / t) if t else None
            avg["prov"][N] = b + timedelta(days=N) > S
    rows = []
    oldest = next((i for i in range(H) if usable[i]), None)
    unverified = edges["ret_state"] == "unverified"
    pedge = _d(portfolio_edge) if portfolio_edge else None
    if oldest is not None:
        lo = P["days"][oldest]
        wk = E - timedelta(days=E.weekday())
        while wk + timedelta(days=6) >= lo - timedelta(days=lo.weekday()):
            wa, wb = max(wk, hs), min(wk + timedelta(days=6), E)
            i_a, i_b = (wa - hs).days, (wb - hs).days
            ndays = i_b - i_a + 1
            v, prov, heat = [None] * 31, [None] * 31, [None] * 31
            tsum = sum(T[i] or 0 for i in range(i_a, i_b + 1))
            nsum = sum(new[i] or 0 for i in range(i_a, i_b + 1))
            nodata = bool(nsum and tsum / nsum < NODATA_SHARE) or not nsum and not tsum
            part = ndays < 7 or any(not usable[i] for i in range(i_a, i_b + 1))
            users = sum(T[i] or 0 for i in range(i_a, i_b + 1) if usable[i])
            if not nodata:
                for N in range(1, COHORT_DAYS + 1):
                    if wb + timedelta(days=N) > E:
                        break
                    x, t, _ = _cw(P, N, i_a, i_b)
                    if not t:
                        continue
                    p = x / t
                    v[N] = _g4(p)
                    pv = wb + timedelta(days=N) > S
                    prov[N] = pv
                    h = 0
                    r = P["ref_raw"][N]
                    if not pv and not part and r is not None and 0 < r < 1:
                        zz = (p - r) / math.sqrt(r * (1 - r) / t * (phis[N] or 1.0))
                        if abs(p - r) * 100 >= min_pp(r) and abs(zz) >= 2:
                            h = 1 if p > r else -1
                    heat[N] = h
            iso_w = wk.isocalendar()
            rows.append({"week": "%d-W%02d" % (iso_w[0], iso_w[1]), "from": _iso(wa), "to": _iso(wb), "users": int(users),
                         "days": ndays, "v": v, "prov": prov, "heat": heat, "part": bool(part and not nodata),
                         "pre": i_b < i0, "q": bool(unverified and pedge is not None and wb < pedge),
                         "nodata": bool(nodata)})
            wk -= timedelta(days=7)
    return {"src": "ga4_return", "cols": cols, "cols_phone": [N for N in PHONE_COLS if N <= nmax], "nmax": nmax,
            "stage": stage, "label": label, "from": iso[first_u] if first_u is not None else None,
            "edge": _iso(P["ret_from"]), "ref": ref, "ref_users": ref_users, "ref_thin": ref_thin, "avg4": avg,
            "rows": rows}


# ── the version table ───────────────────────────────────────────────────────────────────────────

def _versions(P, udet):
    vuse = P["cx"]["vuse"]
    if not vuse:
        return [], []
    S, first5 = P["S"], P["cx"]["first5"]
    days = sorted(d for d in vuse if _d(d) <= S)
    tot = {d: sum((x[0] or 0) + (x[3] or 0) for x in vuse[d].values()) for d in days}
    info = {}
    for d in days:
        for v, x in vuse[d].items():
            it = info.setdefault(v, {"first": d, "last5": None, "last": d, "aR": 0, "sR": 0, "tR": 0, "days": {}})
            it["last"] = d
            u = (x[0] or 0) + (x[3] or 0)
            if tot[d] and u / tot[d] >= RELEASE_SHARE:
                it["last5"] = d
            it["days"][d] = x
    lastd = days[-1] if days else None

    def pooled(v, lo, hi):
        a = s = t = 0
        for d, x in info[v]["days"].items():
            if lo <= d <= hi:
                a, s, t = a + (x[3] or 0), s + (x[4] or 0), t + (x[5] or 0)
        return a, s, t

    rows = []
    for v, it in info.items():
        kind = "rest" if v == "_rest" else "x" if v == "_x" else None
        frm = (first5[v].isoformat() if v in first5 else it["first"]) if not kind else it["first"]
        to = (it["last5"] or it["last"]) if not kind else it["last"]
        a, s, t = pooled(v, frm, to)
        x = vuse.get(lastd, {}).get(v) if lastd else None
        share = ((x[0] or 0) + (x[3] or 0)) / tot[lastd] if x and lastd and tot[lastd] else 0.0
        rows.append({"ver": v, "kind": kind, "from": frm, "to": to, "share": _m4(share), "users": int(a),
                     "sess": _g4(s / a) if a else None, "time": _g4(t / a) if a else None, "vs": None})
    real = sorted([r for r in rows if not r["kind"]], key=lambda r: (r["from"], r["ver"]))
    gaps = []                                          # each version vs the one before, on their shared days

    for j, r in enumerate(real):
        if not j:
            continue
        p = real[j - 1]
        a1 = s1 = t1 = a0 = s0 = t0 = 0
        n1 = n0 = 0
        for d, x in info[r["ver"]]["days"].items():
            y = info[p["ver"]]["days"].get(d)
            if not y or (x[3] or 0) < VER_MIN_USERS or (y[3] or 0) < VER_MIN_USERS:
                continue
            a1, s1, t1, a0, s0, t0 = a1 + x[3], s1 + (x[4] or 0), t1 + (x[5] or 0), a0 + y[3], s0 + (y[4] or 0), t0 + (y[5] or 0)
            n1, n0 = n1 + (x[0] or 0), n0 + (y[0] or 0)
        if not (a1 and a0 and s0 and t0 and s1 and t1):
            gaps.append(None)
            continue
        ls, lt = math.log((s1 / a1) / (s0 / a0)), math.log((t1 / a1) / (t0 / a0))
        mixed = abs(n1 / (n1 + a1) - n0 / (n0 + a0)) > MIX_SWING
        prior = [g for g in gaps if g is not None][-BIAS_MAX:]
        bs = _med([g[0] for g in prior]) if prior else 0.0
        bt = _med([g[1] for g in prior]) if prior else 0.0
        if len(prior) < BIAS_MIN:
            st, why = "maybe", "few"
        else:
            adj = [ls - bs, lt - bt]
            dn = any(math.exp(x) - 1 <= -VER_MIN_REL for x in adj)
            up = any(math.exp(x) - 1 >= VER_MIN_REL for x in adj)
            st, why = ("lower" if dn and not up else "higher" if up and not dn else "same"), None
            if mixed and st in ("lower", "higher"):
                st, why = "maybe", "mix"
        r["vs"] = {"rel_s": _m4(math.exp(ls) - 1), "rel_t": _m4(math.exp(lt) - 1),
                   "bias": {"s": _m4(math.exp(bs) - 1), "t": _m4(math.exp(bt) - 1)} if prior else None,
                   "st": st, "why": why}
        gaps.append((ls, lt))
    newest = sorted(real, key=lambda r: (r["from"], r["ver"]), reverse=True)
    extra = sorted([r for r in rows if r["kind"]], key=lambda r: r["kind"])
    return newest[:VER_ROWS] + extra, newest[VER_ROWS:]


def ga4_trunc(store):
    """GA4's own truncation date (the fetch's flags.impact.meta[report].trunc_date, when it recorded one) → the
    earliest, or None."""
    meta = (((store.get("flags") or {}).get("impact") or {}).get("meta")) or {}
    got = [m.get("trunc_date") for m in meta.values() if isinstance(m, dict) and m.get("trunc_date")]
    return min(got) if got else None


# ── edges (§1.2) ────────────────────────────────────────────────────────────────────────────────

def _edges(P, store, fetch_trunc=None):
    E, hs, i0 = P["E"], P["hs"], P["i0"]
    cfg = P["cfg"]
    ret = P["ret"]
    rf = P["ret_from"]
    launch = P["launch_day"]
    rets = sorted(ret)
    fi = (store.get("flags") or {}).get("impact") or {}
    ret_short = len(fi.get("ret_short") or {})
    ret_oldest = rets[0] if rets else (store.get("ret_to") or None)
    if not ret:
        rs = "wait"
    else:
        sums = []
        new = P["new"]
        for d in rets:
            i = (_d(d) - hs).days
            if 0 <= i < P["H"]:
                sums.append(sum(new[j] or 0 for j in range(max(0, i - 13), i + 1)))
        if sums and _med(sums) < UNVERIFIED_USERS:
            rs = "unverified"
        elif rf is not None and rf <= max(hs, launch) + timedelta(days=7):
            rs = "whole"
        elif rf is not None:
            rs = "found"
        else:
            rs = "searching"
    changed = retention_date(cfg.get("retention_changed"))
    why = "ga4"
    if changed and rf and changed - timedelta(days=EDGE_RET_WINDOW[1]) <= rf <= changed - timedelta(days=EDGE_RET_WINDOW[0]):
        why = "retention"
    usage_from = P["usage_from"]
    if not P["has_usage"]:
        us = "wait"
    else:
        span = [i for i in range((usage_from - hs).days, P["iS"] + 1)] if usage_from else []
        bad = sum(1 for i in span if i in P["inc"] or P["u"]["r"][i] is None and (P["a1"][i] or 0) > 0)
        us = "partial" if span and bad / len(span) >= USAGE_PARTIAL else "ok"
    rev = P["rev"]
    known = [i for i in range(P["H"]) if rev is not None and rev[i] is not None]
    rev_from = P["iso"][known[0]] if known else None
    rev_to = P["iso"][known[-1]] if known else None
    gaps = []
    if known:
        run = None
        for i in range(known[0], known[-1] + 1):
            if rev[i] is None:
                run = [i, i] if run is None else [run[0], i]
            elif run is not None:
                if run[1] - run[0] + 1 >= 3:
                    gaps.append([P["iso"][run[0]], P["iso"][run[1]]])
                run = None
    if rev is None or not known:
        rv = "none"
    elif gaps or any(rev[i] is None for i in range(max(known[0], i0), min(P["iS"], P["H"] - 1) + 1)) \
            or known[-1] < P["iS"]:
        rv = "partial"
    else:
        rv = "ok"
    ed = {"hist": P["iso"][0] if P["H"] else None, "ret_from": _iso(rf), "ret_oldest": ret_oldest, "ret_state": rs,
          "ret_short": ret_short, "usage_from": _iso(usage_from), "usage_state": us,
          "usage_split": P["cx"]["split"], "rev_from": rev_from, "rev_to": rev_to, "rev_gaps": gaps,
          "rev_state": rv, "ga4_trunc": fetch_trunc, "edge_why": why, "text": []}
    ref = E
    t = ed["text"]
    if rs == "found":
        if why == "retention":
            t.append("🔁 Install ke din ke hisaab se wapsi (D1/D7) ka data %s se hai — GA4 pehle ye user-level data sirf "
                     "2 mahine rakhta tha (%s se 14 mahine; purana wapas nahi aata)."
                     % (U.fmt_day(rf, ref), U.fmt_day(changed, ref)))
        else:
            t.append("🔁 Install ke din ke hisaab se wapsi (D1/D7) ka data %s se hai — GA4 ne is se pehle ke install "
                     "dino ka user data poora nahi diya (GA4 ki taraf se; purana wapas nahi aata)." % U.fmt_day(rf, ref))
        if fetch_trunc:
            t[-1] += " GA4 khud kehta hai: %s se pehle ka data nahi." % U.fmt_day(fetch_trunc, ref)
    elif rs == "whole":
        t.append("🔁 Wapsi ka data poori history (%s) se." % U.fmt_day(hs, ref))
    elif rs == "searching":
        t.append("🔁 GA4 se purana wapsi data dhoondh rahe hain — abhi %s tak mila, roz ~4 mahine aur aayega."
                 % U.fmt_day(ret_oldest, ref))
    elif rs == "wait":
        t.append("🔁 Wapsi (D1/D7) ka data agle GA4 fetch ke saath aayega.")
    else:
        t.append("🔁 Installs kam hain, isliye GA4 ki purani seema check nahi ho sakti — purane hafte '?' ke saath.")
    if ret_short > 0 and rs != "wait":
        t[-1] += " (%d din ka data GA4 ne adhoora diya — hafte me ek baar dobara maangte hain.)" % ret_short
    t.append("📅 Roz ke active users aur installs %s se poore hain." % U.fmt_day(hs, ref))
    if us == "wait":
        t.append("⏳ Sessions aur time agle GA4 fetch ke baad aayenge (poori history ek saath).")
    else:
        t.append("⏱️ Sessions aur time %s se." % U.fmt_day(usage_from, ref))
        if not P["cx"]["split"]:
            t.append("Version ke hisaab se sessions/time sab users ke (GA4 split nahi deta).")
    if rev_from:
        s = "💰 AdMob revenue %s se." % U.fmt_day(rev_from, ref)
        if gaps:
            s += " No ad data: %s." % ", ".join(U.fmt_span(a, b, ref) for a, b in gaps)
        osh = other_share(P, max(0, P["iS"] - TILE_DAYS + 1), P["iS"], "rev")
        if osh is not None and osh >= OTHER_NET_MIN:
            s += (" Sirf AdMob Network — dusre ad networks (mediation) se ~%d%% aur kamai, wo isme nahi."
                  % round(osh / (1 - osh) * 100 if osh < 1 else 100))
        t.append(s)
    return ed


# ── conditions at one settled end ───────────────────────────────────────────────────────────────

def _metrics_of(c):
    if c["metric"] == "usage":
        return ["sess", "time"]
    if c["family"] == "act_return":
        return [c["metric"]] + list(c.get("also") or [])
    return [c["metric"]]


def _caps(P, open_eps, m):
    """{dir: the day before its open story began} for metric m — an open act_drift episode (sess / time: the usage
    group) or sudden change (act_spike): the drift null of an open story stays the one from before it."""
    km = "usage" if m in ("sess", "time") else m
    out = {}
    for e in open_eps:
        if e.get("family") == "act_spike" and e.get("metric") == m and not (e.get("last") or {}).get("cap"):
            since = e.get("day")                       # a sudden change that runs on: the same story
        elif e.get("family") == "act_drift" and (e.get("key_metric") or e.get("metric")) == km:
            since = e.get("since0") or (e.get("last") or {}).get("since")
        else:
            continue
        if not since:
            continue
        i = (_d(since) - P["hs"]).days - 1
        out[e["dir"]] = i if e["dir"] not in out else min(out[e["dir"]], i)
    return out


def _told(P, told, fam_ok, metric, dr, a, b):
    """Is there an episode (open or closed) of `metric`, direction dr, one of the families fam_ok, whose story began
    in the day indexes [a, b]? — a slower detector never re-tells a change a faster one already told."""
    lo, hi = P["days"][max(a, 0)], P["days"][min(b, P["H"] - 1)]
    for e in told or []:
        if e.get("family") not in fam_ok or e.get("dir") != dr:
            continue
        if (e.get("key_metric") or e.get("metric")) != metric and e.get("metric") != metric:
            continue
        last = e.get("last") or {}
        anc = e.get("since0") or last.get("since") or e.get("day") or last.get("day") or e.get("opened")
        if anc and lo <= _d(anc) <= hi:
            return True
    return False


def _spike_inst(P, d, rel, med):
    """Does the install mix explain half of a returning-users jump on day d (the same direction)? The recent installs'
    returners that day vs their 4 weeks before (return cohorts), else at most RET_SUM_MAX × the installs' move over the
    week that feeds them → the alert's install snapshot, or None."""
    if not med:
        return None
    Y = P["Y"]
    n1, n0 = _mean_new(P, d - 7, d - 1), _mean_new(P, d - 35, d - 8)
    swing = (n1 / n0 - 1) if n1 is not None and n0 else None
    part, upto = None, False
    if _cohort_mode(P, d - 28, d) and Y[d] is not None:
        yb = [Y[i] for i in range(max(0, d - 28), d) if Y[i] is not None and P["valid"]["ret_dau"][i]]
        if len(yb) >= 14:
            part = (Y[d] - sum(yb) / len(yb)) / med
    elif swing is not None and swing > -1 and n0:
        part, upto = min(YS_MAX, n0 * RET_SUM_MAX / med) * math.log(1 + swing), True
    if part is None or _sgn(part) != _sgn(rel) or abs(part) < 0.5 * abs(rel):
        return None
    return {"mode": "cohort" if not upto else "raw", "part": _m4(part if abs(part) <= abs(rel) else rel),
            "swing": _m4(swing), "upto": upto}


def _inst_snap(att, rel):
    """What an alert keeps of the install attribution (its text's "isme ~X point unka")."""
    part, upto = att["inst_part"], False
    if part is None or not (_sgn(part) == _sgn(rel) and abs(part) >= 0.5 * abs(rel)):
        pot = att.get("pot")
        if att["mode"] != "cohort" and pot is not None and _sgn(pot) == _sgn(rel) and abs(pot) >= 0.5 * abs(rel):
            part, upto = (pot if abs(pot) <= abs(rel) else rel), True
    return {"mode": att["mode"], "part": _m4(part), "swing": _m4(att["swing"]), "upto": upto}


def _inst_info(P, dr, rel, frm, to, slow=False):
    """The info row of a returning-users change the installs explain (never an alert)."""
    return {"kind": "installs", "metric": "ret_dau", "dir": dr, "from": frm, "to": to, "rel": _m4(rel),
            "tags": ["installs"], "prov": False,
            "text": "Returning users %s%s, par ye naye installs %s aane se (ad spend?) — 30+ din purane users normal"
                    % (U.fmt_rel(rel), " (3 mahine me)" if slow else "", "zyada" if rel > 0 else "kam")}


def conditions(P, iS, ev, open_eps, beta, recent_from, told=None):
    """Every condition that holds at settled end iS (drift, slow, spikes, breaks, returns) + the info rows (installs,
    price) — before persistence, seeding and links. ev = this app's eval state (claimed install ranges); told = this
    app's episodes, open and closed (a slow trend a drift / spike / break already told is not told again)."""
    H, iso = P["H"], P["iso"]
    out, info = [], []
    if iS < 0 or iS >= H:
        return out, info
    closed_eps = [e for e in (told or []) if e not in open_eps]
    told = list(open_eps) + closed_eps
    E_like = P["days"][iS]
    # drift
    only = P.get("only")
    drifts = {}
    young = (E_like - P["launch_day"]).days < ACT_READY_DAYS          # a new app: no drift / slow judged yet (§2.12)
    for m in DRIFT_METRICS:
        if young or (only is not None and m not in only):
            continue
        if m in ("sess", "time") and not P["has_usage"]:
            continue
        if m == "ads" and P["rev"] is None:
            continue
        for dr_, c in _drift_at(P, m, iS, _caps(P, open_eps, m)).items():
            if c:
                drifts[(m, dr_)] = c
    for (m, dd), dr in list(drifts.items()):
        s, e, L = dr["s"], dr["e"], dr["L"]
        c = {"family": "act_drift", "metric": m, "dir": dr["dir"], "z": round(dr["z"], 2), "rel": dr["rel"],
             "now": dr["now"], "before": dr["before"], "since": iso[s], "day": None, "days": L,
             "base_from": iso[max(0, dr["bfrom"])], "base_to": iso[dr["bto"]], "installs_from": None,
             "installs_to": None, "delta_pp": None, "users": _int(dr["act_sum"] / max(1, L)) if m == "ret_dau" else
             _int(dr["den_sum"] / max(1, L)), "tags": [], "cap": None, "also": [], "est": False}
        c["severity"] = "good" if dr["dir"] == "up" else ("warning" if abs(dr["z"]) >= WARN_Z else "watch")
        if m == "ads":
            c["now"], c["before"] = dr["now"] * 1000, dr["before"] * 1000
            c["est"] = P["tz_blend"]
        if m == "ret_dau":
            att = _inst_attr(P, s, e, dr["bfrom"], dr["bto"], dr["rel"], beta)
            rule = _inst_rule(att, dr["rel"])
            c["inst"] = _inst_snap(att, dr["rel"])
            if rule == "info" or (rule == "cap" and dr["dir"] == "up"):   # a rise the installs explain: never
                info.append(_inst_info(P, dr["dir"], dr["rel"], iso[s], iso[e]))
                continue
            if rule == "cap":
                c["cap"], c["tags"] = "watch", c["tags"] + ["installs"]
                c["est"] = att["est"]
        else:
            moved = _mix_moves(P, s, e, dr["bfrom"], dr["bto"], m)
            if moved:
                if dr["dir"] == "up":                  # the users' mix moved: a rise is not the app's (tile: Maybe)
                    continue
                c["cap"], c["tags"] = "watch", c["tags"] + ["mix"]
                if "other_net" in moved:
                    c["other_net"] = True
            if m == "ads" and P["has_usage"]:
                tn = _ratio_change(P, "time", s, e, dr["bfrom"], dr["bto"])
                if tn is not None and _sgn(tn) == _sgn(dr["rel"]) and abs(tn) >= 0.5 * abs(dr["rel"]):
                    c["tags"].append("time")
                    c["rel_t"] = tn
        drifts[(m, dd)]["cond"] = c
    for dd in ("down", "up"):
        usage = [m for m in ("sess", "time") if (m, dd) in drifts and "cond" in drifts[(m, dd)]]
        if len(usage) == 2:
            cs, ct = drifts[("sess", dd)]["cond"], drifts[("time", dd)]["cond"]
            g = dict(cs if abs(cs["z"]) >= abs(ct["z"]) else ct)
            g.update(metric="usage", rel_s=cs["rel"], rel_t=ct["rel"], now_t=ct["now"], before_t=ct["before"],
                     since=min(cs["since"], ct["since"]), tags=sorted(set(cs["tags"]) | set(ct["tags"])),
                     cap="watch" if cs["cap"] or ct["cap"] else None,
                     severity=_worst(cs["severity"], ct["severity"]))
            out.append(dict(g, key_metric="usage"))
        else:
            for m in usage:
                out.append(dict(drifts[(m, dd)]["cond"], key_metric="usage"))
    for m in ("ret_dau", "ads"):
        for dd in ("down", "up"):
            if (m, dd) in drifts and "cond" in drifts[(m, dd)]:
                out.append(dict(drifts[(m, dd)]["cond"], key_metric=m))
    # slow (3 months): the install mix attributed as for a drift; never a change a drift / spike / break told
    sl = _slow_at(P, iS) if not young and (only is None or "ret_dau" in only) else None
    if sl and not any(e.get("family") == "act_slow" and e.get("dir") == sl["dir"] for e in open_eps) and (
            _told(P, told, ("act_drift", "act_spike", "act_break"), "ret_dau", sl["dir"], sl["bfrom"], iS)
            or _told(P, closed_eps, ("act_slow",), "ret_dau", sl["dir"], sl["bfrom"], iS)):
        sl = None                                      # told already (or a slow trend that just closed: no flapping)
    if sl:
        att = _inst_attr(P, sl["s"], sl["e"], sl["bfrom"], sl["bto"], sl["rel"], beta)
        rule = _inst_rule(att, sl["rel"], SLOW_MIN_REL)
        c = {"family": "act_slow", "metric": "ret_dau", "key_metric": "ret_dau", "dir": sl["dir"],
             "severity": "good" if sl["dir"] == "up" else "watch", "z": round(sl["z"], 2), "rel": sl["rel"],
             "now": sl["now"], "before": sl["before"], "since": iso[sl["s"]], "day": None,
             "days": SLOW_DAYS, "base_from": iso[sl["bfrom"]], "base_to": iso[sl["bto"]],
             "installs_from": None, "installs_to": None, "delta_pp": None, "users": _int(sl["now"]),
             "tags": [], "cap": None, "also": [], "est": False, "inst": _inst_snap(att, sl["rel"])}
        if rule == "info" or (rule == "cap" and sl["dir"] == "up"):
            info.append(_inst_info(P, sl["dir"], sl["rel"], iso[sl["s"]], iso[sl["e"]], slow=True))
        else:
            if rule == "cap":
                c["cap"], c["tags"], c["est"] = "watch", ["installs"], att["est"]
            out.append(c)
    # breaks (settled days S−2..S; consecutive days are ONE break), then spikes on the other days
    brk_days = set()
    if only is None or "ret_dau" in only:
        grp = []
        for d in range(max(P["i0"], iS - 2), iS + 1):
            if P["brk"][d]:
                brk_days.add(d)
                if grp and d - grp[-1][-1] <= SPIKE_MERGE_DAYS:
                    grp[-1].append(d)
                else:
                    grp.append([d])
        for g in grp:
            bs = [P["brk"][d] for d in g]
            kind = "zero" if all(b["kind"] == "zero" for b in bs) else "low"
            d, b = g[-1], bs[-1]
            now = P["a1"][d] if b["kind"] == "zero" else P["R"][d]
            out.append({"family": "act_break", "metric": "ret_dau", "key_metric": "ret_dau", "dir": "down",
                        "severity": "watch", "kind": kind, "expected": b["exp"], "z": None,
                        "rel": (now / b["exp"] - 1) if b["exp"] else None, "now": now, "before": b["exp"],
                        "since": None, "day": iso[g[0]], "last_day": iso[g[-1]], "days_list": [iso[x] for x in g],
                        "base_from": None, "base_to": None, "installs_from": None, "installs_to": None,
                        "delta_pp": None, "users": int(now or 0), "tags": [], "cap": None, "also": [], "est": False})
    for m in DRIFT_METRICS:
        f = P["fast"].get(m)
        if f is None or (only is not None and m not in only):
            continue
        hits = []
        for d in range(max(P["i0"], iS - 2), iS + 1):
            if d in brk_days:
                continue
            sp = _spike_day(P, m, d)
            if sp:
                hits.append(sp)
        for dr in ("down", "up"):
            hs_ = [h for h in hits if h["dir"] == dr]
            if not hs_:
                continue
            grp = [[hs_[0]]]
            for h in hs_[1:]:
                if h["day"] - grp[-1][-1]["day"] <= SPIKE_MERGE_DAYS:
                    grp[-1].append(h)
                else:
                    grp.append([h])
            for g in grp:
                d0 = g[0]["day"]
                km = "usage" if m in ("sess", "time") else m
                dr_open = any(e["family"] == "act_drift" and e["dir"] == dr and e.get("key_metric", e["metric"]) == km
                              and (e["last"].get("since") or "9") <= iso[d0] for e in open_eps)
                dn = drifts.get((m, dr))
                dr_now = dn is not None and "cond" in dn and dn["s"] <= d0
                if dr_open or dr_now:
                    continue
                first = g[0]
                sev = "good" if dr == "up" else ("warning" if len(g) >= 2 or (m == "ads" and min(h["rel"] for h in g) <= ADS_BROKE)
                                                 else "watch")
                inst = _spike_inst(P, d0, first["rel"], first["med"]) if m == "ret_dau" else None
                if inst is not None and dr == "up":   # a jump the new installs explain: never good news of old users
                    continue
                out.append({"family": "act_spike", "metric": m, "key_metric": m, "dir": dr, "severity": sev,
                            "z": round(first["z"], 2) if first["z"] is not None else None, "rel": first["rel"],
                            "now": first["now"], "before": first["med"], "lo": first["lo"], "hi": first["hi"],
                            "since": None, "day": iso[d0], "last_day": iso[g[-1]["day"]],
                            "days_list": [iso[h["day"]] for h in g], "base_from": iso[max(0, d0 - BASE_DAYS)],
                            "base_to": iso[max(0, d0 - 1)], "installs_from": None, "installs_to": None,
                            "delta_pp": None, "users": _int(P["R"][d0]) if m == "ret_dau" else _int(P["den"][m][d0]),
                            "tags": ["installs"] if inst else [], "cap": "watch" if inst else None, "also": [],
                            "est": bool(m == "ads" and P["tz_blend"]), "inst": inst,
                            "broke": bool(m == "ads" and min(h["rel"] for h in g) <= ADS_BROKE)})
    # new users coming back
    if P["has_ret"] and (only is None or any(k in only for k in D_NS)):
        nmax = P["nmax"] if iS == P["iS"] else _nmax(P, iS)
        cl = (ev or {}).get("claimed") or {}
        per = {"up": [], "down": []}
        for N in RET_ALERT_NS:
            if N > nmax:
                continue
            st = _ret_stats(P, N, iS)
            c = _ret_cond(P, st, recent_from)
            if c:
                per[c["dir"]].append(c)
        for dr, cs in per.items():
            if not cs:
                continue
            cs.sort(key=lambda c: -abs(c["z"]))
            c = cs[0]
            c["also"] = ["d%d" % x["n"] for x in cs[1:]]
            claimed = U._claimed({"hs": P["hs"], "H": H}, cl.get(dr))
            window = set(range(c["_r0"], c["_r1"] + 1))
            if window & claimed:
                if not any(e["family"] == "act_return" and e["dir"] == dr for e in open_eps):
                    continue
            out.append(c)
    # price info (eCPM-only move)
    return out, info


def _worst(a, b):
    return a if SEV_ORDER.get(a, 9) <= SEV_ORDER.get(b, 9) else b


def _ratio_change(P, m, w0, w1, b0, b1):
    nw, dw, nb, db = (_psum(P["pn"][m], w0, w1), _psum(P["pd"][m], w0, w1), _psum(P["pn"][m], b0, b1),
                      _psum(P["pd"][m], b0, b1))
    if dw <= 0 or db <= 0 or nb <= 0 or nw <= 0:
        return None
    return (nw / dw) / (nb / db) - 1


def _ret_cond(P, st, recent_from):
    """act_return at one N (§2.7) → the condition or None."""
    if "pw" not in st or st["se"] is None or st["z"] is None:
        return None
    N, iso = st["N"], P["iso"]
    if st["cw"] < 5 or st["cb"] < 21 or st["r1"] < 0:
        return None
    if P["days"][st["r1"]] < recent_from:
        return None
    d, mp = st["d"], st["mpp"]
    if abs(d) * 100 < mp:
        return None
    if st["tw"] < MIN_INSTALLS or st["tb"] < MIN_INSTALLS or st["aw"] < MIN_EVENTS or st["ab"] < MIN_EVENTS:
        return None
    zlim = 3.0 if st["sn"] is not None else 4.0
    if abs(st["z"]) < zlim:
        return None
    if st["tw"] >= RET_BIG:                                   # big apps: breadth + not one day
        side, big, bt = 0, None, -1
        for c in range(st["r0"], st["r1"] + 1):
            a = P["A"][c]
            if not (P["usable"][c] and a is not None and len(a) > N and P["T"][c]):
                continue
            pc = a[N] / P["T"][c]
            side += 1 if (pc - st["pb"] > 0) == (d > 0) else 0
            if P["T"][c] > bt:
                big, bt = c, P["T"][c]
        if side < 4:
            return None
        if big is not None:
            aw2, tw2 = st["aw"] - P["A"][big][N], st["tw"] - P["T"][big]
            if tw2 <= 0:
                return None
            d2 = aw2 / tw2 - st["pb"]
            if _sgn(d2) != _sgn(d) or abs(d2) * 100 < mp or abs(d2 / st["se"]) < zlim:
                return None
    dr = "up" if d > 0 else "down"
    sw_w, sw_b = _mean_new(P, st["r0"], st["r1"]), _mean_new(P, st["b0"], st["b1"])
    swing = (sw_w / sw_b - 1) if sw_w is not None and sw_b else None
    capped = swing is not None and abs(swing) >= INSTALL_SWING
    if capped and dr == "up":                         # a campaign / country mix: never sent as good news
        return None
    vs_all = st["all"] is not None and (st["pw"] - st["all"]) * 100 * (1 if dr == "up" else -1) >= mp
    if dr == "up":
        sev = "good"
    elif abs(d) * 100 >= 2 * mp and st["sn"] is not None and not capped and vs_all:
        sev = "warning"
    else:
        sev = "watch"
    return {"family": "act_return", "metric": "d%d" % N, "key_metric": "ret", "n": N, "dir": dr, "severity": sev,
            "z": round(st["z"], 2), "rel": (st["pw"] / st["pb"] - 1) if st["pb"] else 0.0, "now": st["pw"],
            "before": st["pb"], "all": st["all"], "delta_pp": round(d * 100, 2), "since": None, "day": None,
            "installs_from": iso[st["r0"]], "installs_to": iso[st["r1"]], "base_from": iso[st["b0"]],
            "base_to": iso[st["b1"]], "users": int(st["tw"]), "vs": ["prev", "all"] if vs_all else ["prev"],
            "tags": ["installs"] if capped else [], "cap": "watch" if (capped or st["sn"] is None) else None,
            "inst_swing": swing, "also": [], "est": False, "_r0": st["r0"], "_r1": st["r1"]}


# ── text (§2.15) ────────────────────────────────────────────────────────────────────────────────

def _fmt_val(m, v):
    if v is None:
        return "—"
    if m == "ret_dau":
        return _users(v)
    if m == "time":
        return imp.fmt_dur(v)
    if m == "ads_1k":
        return _users(v)
    return _num2(v)


def _inst_txt(s):
    """The install part of a capped returning-users sentence (tag installs)."""
    inst = s.get("inst") or {}
    if "installs" not in (s.get("tags") or []) or inst.get("swing") is None:
        return ""
    t = " · naye installs bhi %s (ad spend?)" % U.fmt_rel(inst["swing"])
    if inst.get("part") is not None and abs(inst["part"]) * 100 >= 0.5:
        t += " — isme ~%s point %s" % (_pts(abs(inst["part"]) * 100), "tak unka ho sakta" if inst.get("upto")
                                      else "unka")
    return t


def _break_when(s, ref):
    """"{day} ko" — or "{from}–{to} me" when the break ran over several days."""
    days = sorted(set(s.get("days_list") or [s["day"]]))
    if len(days) > 1:
        whole = (_d(days[-1]) - _d(days[0])).days + 1 == len(days)
        return "%s me%s" % (U.fmt_span(days[0], days[-1], ref), "" if whole else " %d din" % len(days))
    return "%s ko" % U.fmt_day(days[0], ref)


def alert_text(s, E, app=None):
    """One Hinglish sentence per condition snapshot (dates via fmt_day with the data's year rule)."""
    fam, m, dr = s["family"], s["metric"], s["dir"]
    kz = "kam" if dr == "down" else "zyada"
    ref = _d(E)
    if fam == "act_drift":
        since = U.fmt_day(s["since"], ref)
        if m == "ret_dau":
            t = "%s se purane users %s: roz ~%s → ~%s (%s)" % (since, kz, _users(s["before"]), _users(s["now"]),
                                                              U.fmt_rel(s["rel"])) + _inst_txt(s)
        elif m == "usage":
            t = "%s se purane users %s baar aur %s time: sessions %s, time %s" % (
                since, "kam" if s["rel_s"] < 0 else "zyada", "kam" if s["rel_t"] < 0 else "zyada",
                U.fmt_rel(s["rel_s"]), U.fmt_rel(s["rel_t"]))
        elif m == "sess":
            t = "%s se har purana user %s baar app khol raha: %s → %s sessions/din (%s)" % (
                since, kz, _num2(s["before"]), _num2(s["now"]), U.fmt_rel(s["rel"]))
        elif m == "time":
            t = "%s se har purana user %s time de raha: %s → %s (%s)" % (
                since, kz, imp.fmt_dur(s["before"]), imp.fmt_dur(s["now"]), U.fmt_rel(s["rel"]))
        else:
            t = "%s se har user ko %s ads: 1,000 users pe %s → %s (%s)" % (
                since, kz, _users(s["before"]), _users(s["now"]), U.fmt_rel(s["rel"]))
            if "time" in (s.get("tags") or []) and s.get("rel_t") is not None:
                t += " — log %s time de rahe (time/user %s), ads usi hisaab se" % (kz, U.fmt_rel(s["rel_t"]))
            else:
                t += " — ad load/fill check karo"
            if s.get("other_net"):
                t += " · dusre ad networks (mediation) ka hissa badla — AdMob ke ads kam/zyada dikh sakte hain"
    elif fam == "act_spike":
        t = "%s ko %s achanak %s: %s (normal %s–%s)" % (
            U.fmt_day(s["day"], ref), MPHRASE.get(m, m), kz, _fmt_val(m, s["now"]), _fmt_val(m, s["lo"]),
            _fmt_val(m, s["hi"])) + (_inst_txt(s) if m == "ret_dau" else "")
    elif fam == "act_break":
        when = _break_when(s, ref)
        if s.get("kind") == "zero":
            t = "%s GA4 me ek bhi active user nahi (normal ~%s) — tracking check karo" % (
                when, _users(s["expected"] or 0))
        else:
            t = "%s active users normal ke aadhe se bhi kam (%s, normal ~%s) — GA4/Firebase tracking check karo" % (
                when, _users(s["now"] or 0), _users(s["expected"] or 0))
        if s.get("ongoing"):
            t += " — abhi bhi chal raha"
    elif fam == "act_slow":
        t = "Purane users 3 mahine se dheere-dheere %s rahe: roz ~%s → ~%s (%s)" % (
            "ghat" if dr == "down" else "badh", _users(s["before"]), _users(s["now"]), U.fmt_rel(s["rel"])) + _inst_txt(s)
    elif fam == "act_return":
        vs = s.get("vs") or ["prev"]
        which = "dono se" if len(vs) == 2 else "hamesha se" if vs == ["all"] else "pichhle 4 hafte se"
        t = "%s wapas aane wale %s: 100 me %s, pehle %s (%s %s) — %s ke installs" % (
            NWORD.get(s.get("n"), "%s din baad" % s.get("n")), kz, _pts(s["now"] * 100), _pts(s["before"] * 100),
            which, kz, U.fmt_span(s["installs_from"], s["installs_to"], ref))
        if "installs" in (s.get("tags") or []) and s.get("inst_swing") is not None:
            t += " · is hafte installs %s (alag campaign/country ho sakta hai)" % U.fmt_rel(s["inst_swing"])
    else:
        t = str(s.get("text") or "")
    rel = s.get("release")
    if rel and rel.get("label"):
        t += " · %s ke baad" % rel["label"]
    return t


# ── episodes (a local copy of uninstall.update_episodes' semantics, on this tab's own state) ─────

def _key(c, app_id):
    fam = c["family"]
    if fam == "act_drift":
        return "%s|act_drift|%s|%s" % (app_id, c["key_metric"], c["dir"])
    if fam == "act_slow":
        return "%s|act_slow|ret_dau|%s" % (app_id, c["dir"])
    if fam == "act_spike":
        return "%s|act_spike|%s|%s|%s" % (app_id, c["metric"], c["dir"], c["day"])
    if fam == "act_break":
        return "%s|act_break|%s" % (app_id, c["day"])
    return "%s|act_return|%s" % (app_id, c["dir"])


def _eid(app_id, c, opened, extra=""):
    return fingerprint(app_id, "active_%s_%s" % (c["family"], c.get("key_metric") if c["family"] == "act_drift" else
                                                 c["metric"]), None, c["dir"], opened + extra)


def episodes(st, app_id, E, ready, advanced, now, recent_from):
    """Open / refresh / close this app's Active episodes from the READY conditions (each carrying `seed`). Pure: only
    `st` changes. Spike / break days ≤ SPIKE_MERGE_DAYS from an open one of the same kind fold into it and stay
    SPIKE_KEEP_DAYS after their last day; the rest close after CLOSE_EVALS advanced evaluations without their condition;
    a return episode about installs older than ALERT_RECENT_DAYS closes at once. → this app's open episodes."""
    eps, closed = st.setdefault("episodes", {}), st.setdefault("closed", [])
    E = _d(E)
    E_iso, hit = E.isoformat(), set()
    for c in ready:
        key, snap = c["key"], U._snap({k: v for k, v in c.items() if not k.startswith("_") and k not in ("key", "seed")})
        ep = eps.get(key)
        spike = c["family"] in SPIKY
        if ep is None and spike:
            day = _d(c["day"])
            for k, e in eps.items():
                if (e["app_id"] == app_id and e["family"] == c["family"] and e["metric"] == c["metric"]
                        and e["dir"] == c["dir"] and k not in hit
                        and _d(e["day"]) - timedelta(days=SPIKE_MERGE_DAYS) <= day
                        <= _d(e["last_day"]) + timedelta(days=SPIKE_MERGE_DAYS)):
                    key, ep = k, e
                    break
        if ep is None:
            ep = {"id": _eid(app_id, c, E_iso), "app_id": app_id, "family": c["family"], "metric": c["metric"],
                  "key_metric": c.get("key_metric") or c["metric"], "dir": c["dir"], "opened": E_iso,
                  "last_true": E_iso, "misses": 0, "notified_at": now if c["seed"] else None, "notified_dry": False,
                  "seeded": bool(c["seed"]), "last": snap}
            if spike:
                ep["day"], ep["last_day"] = snap["day"], snap.get("last_day") or snap["day"]
                ep["days"] = sorted(set(snap.get("days_list") or [snap["day"]]))
            if c["family"] == "act_drift" and snap.get("since"):
                ep["since0"] = snap["since"]           # when the story began (its drift null stays before it)
            eps[key] = ep
        else:
            ep["last_true"], ep["misses"] = E_iso, 0
            if c["family"] == "act_drift" and snap.get("since"):
                ep["since0"] = min(ep.get("since0") or snap["since"], snap["since"])
            if spike:
                ep["last_day"] = max(ep["last_day"], snap.get("last_day") or snap["day"])
                ep["days"] = sorted(set(ep.get("days") or []) | set(snap.get("days_list") or [snap["day"]]))
                sev = ep["last"].get("severity")
                if snap["day"] == ep["day"] or c["family"] == "act_break":   # a break: its newest days' numbers
                    ep["last"] = snap
                if (c["family"] == "act_spike" and c["dir"] == "down" and len(ep["days"]) >= 2
                        and sev != "warning" and ep["last"].get("severity") != "warning"
                        and not ep["last"].get("cap") and not c.get("cap")):   # a capped one stays a watch
                    ep["last"] = dict(ep["last"], severity="warning")
                    if ep.get("notified_at") is not None and not ep.get("seeded"):
                        ep["id"] = _eid(app_id, c, ep["opened"], "|warning")
                        ep["notified_at"], ep["notified_dry"] = (now if c["seed"] else None), False
                        ep["seeded"] = bool(c["seed"])
            else:
                ep["last"] = snap
            if c["seed"] and ep.get("notified_at") is None:
                ep.update(notified_at=now, seeded=True)
        hit.add(key)
    for key in [k for k, e in eps.items() if e["app_id"] == app_id and k not in hit and e["family"] == "act_return"
                and e["last"].get("installs_to") and _d(e["last"]["installs_to"]) < recent_from]:
        closed.append(dict(eps.pop(key), closed=E_iso))
    if advanced:
        for key in [k for k, e in eps.items() if e["app_id"] == app_id and k not in hit]:
            ep = eps[key]
            if ep["family"] in SPIKY:
                done = (E - _d(ep["last_day"])).days > SPIKE_KEEP_DAYS
            else:
                ep["misses"] += 1
                done = ep["misses"] >= CLOSE_EVALS
            if done:
                closed.append(dict(eps.pop(key), closed=E_iso))
    keep = E - timedelta(days=CLOSED_KEEP_DAYS)
    st["closed"] = [e for e in closed if e["app_id"] != app_id or _d(e["closed"]) >= keep]
    return [e for e in eps.values() if e["app_id"] == app_id]


def alert_obj(ep, app, E):
    """Episode → the alert object (uninstall's alert_obj keys + the Active ones). Rebuilt every build: a renamed app
    shows its new name."""
    s, E = ep["last"], _d(E)
    if ep["family"] == "act_break" and ep.get("days"):  # one break over several days: its whole span, and whether
        s = dict(s, day=ep["day"], last_day=ep["last_day"], days_list=ep["days"],   # it still runs on the newest
                 ongoing="closed" not in ep and ep["last_day"] == _iso(E - timedelta(days=ACT_LATE_DAYS)))  # settled day
    text = alert_text(dict(s, family=ep["family"], metric=s.get("metric", ep["metric"]), dir=ep["dir"]), E)
    m = s.get("metric", ep["metric"])
    unit = "pp" if ep["family"] == "act_return" else ("num" if (ep["family"] == "act_spike" and m == "ads")
                                                       else UNIT.get(m, "users"))
    out = {"id": ep["id"], "source": "active", "app_id": ep["app_id"], "app": app, "family": ep["family"],
           "metric": m, "also": list(s.get("also") or []), "dir": ep["dir"],
           "severity": s.get("severity") or "watch", "unit": unit,
           "now": s.get("now"), "before": s.get("before"), "rel": s.get("rel") if s.get("rel") is not None else 0.0,
           "delta_pp": s.get("delta_pp"), "z": s.get("z"), "since": s.get("since"), "day": s.get("day"),
           "installs_from": s.get("installs_from"), "installs_to": s.get("installs_to"),
           "base_from": s.get("base_from"), "base_to": s.get("base_to"), "users": int(s.get("users") or 0),
           "opened": ep["opened"], "last_seen": ep["last_true"], "fresh": (E - _d(ep["opened"])).days < FRESH_EVALS,
           "notify": ep.get("notified_at") is None, "provisional": False, "estimate": bool(s.get("est")),
           "tags": sorted(set(s.get("tags") or []) | ({"update"} if s.get("release") else set())),
           "release": dict(s["release"]) if s.get("release") else None, "linked": bool(s.get("linked")),
           "data_till": _iso(E), "text": text, "message": "%s: %s" % (app, text)}
    if "closed" in ep:
        out.update(closed=ep["closed"], fresh=False, notify=False)
    return out


def sort_alerts(alerts):
    return sorted(alerts, key=lambda a: (SEV_ORDER.get(a["severity"], 9), not a["fresh"],
                                         -_d(a["opened"]).toordinal(), a["app"].casefold(), a["id"]))


# ── update link (§2.13) ─────────────────────────────────────────────────────────────────────────

def _anchor(c):
    return _d(c.get("since") or c.get("day") or c.get("installs_from"))


def _link(c, udet):
    """An Active episode an open Update impact alert already covers → (release, cap severity) — else the release block
    it falls just after → (release, None) — else (None, None)."""
    rows = [IMPACT_ROW.get(m) for m in ((["sess", "time"] if c["metric"] == "usage" else [c["metric"]]))]
    rows = [r for r in rows if r]
    a = _anchor(c)
    for al in udet.get("alerts") or []:
        if al.get("family") != "impact" or al.get("closed") or not al.get("release"):
            continue
        side = (al.get("rows") or {}).get("worse" if c["dir"] == "down" else "better") or []
        if not any(r in side for r in rows):
            continue
        R = _d(al["release"]["date"])
        if R - timedelta(days=LINK_BEFORE) <= a <= R + timedelta(days=LINK_AFTER):
            cap = {"halt": "warning", "hold": "watch", "win": "good"}.get(al.get("level"))
            return dict(al["release"]), cap
    for u in (udet.get("impact") or {}).get("updates") or []:
        R = _d(u["date"])
        if R <= a <= R + timedelta(days=LINK_AFTER):
            return {"key": u["key"], "label": u["label"], "date": u["date"]}, None
    return None, None


def _cap(sev, cap):
    if cap is None or sev == "good":
        return sev
    return cap if SEV_ORDER.get(sev, 9) < SEV_ORDER.get(cap, 9) else sev


# ── history ("Older changes") ───────────────────────────────────────────────────────────────────

def history(P, eps_all, udet):
    """Drift (4 metrics) and slow at every weekly end, spikes and breaks every day, over the post-launch history with
    the same thresholds and no persistence → segments, newest first, never capped; anything an episode (open or
    closed) of the same metric and direction covers is left to that episode."""
    iS, i0 = P["iS"], P["i0"]
    flagged = []
    ready = P["launch_day"] + timedelta(days=ACT_READY_DAYS)            # drift / slow: never on a new app (§2.12)
    ends = [e for e in range(i0, iS - 6) if P["wd"][e] == 6 and P["days"][e] >= ready]
    for e in ends:
        for m in DRIFT_METRICS:
            if (m in ("sess", "time") and not P["has_usage"]) or (m == "ads" and P["rev"] is None):
                continue
            for dr in _drift_at(P, m, e).values():
                if not dr:
                    continue
                bf, nw = dr["before"], dr["now"]
                if m == "ads":
                    bf, nw = bf * 1000, nw * 1000
                flagged.append({"kind": "act_drift", "metric": m, "dir": dr["dir"], "from": dr["s"], "to": e,
                                "before": bf, "now": nw, "rel": dr["rel"], "z": dr["z"], "gap": 14,
                                "win": (dr["s"], e, dr["bfrom"], dr["bto"])})
        sl = _slow_at(P, e)
        if sl:
            flagged.append({"kind": "act_slow", "metric": "ret_dau", "dir": sl["dir"], "from": sl["s"], "to": e,
                            "before": sl["before"], "now": sl["now"], "rel": sl["rel"], "z": sl["z"], "gap": 14,
                            "win": (sl["s"], e, sl["bfrom"], sl["bto"]), "bfrom": sl["bfrom"]})
    for d in range(i0, iS - 2):
        b = P["brk"][d]
        if b:
            now = P["a1"][d] if b["kind"] == "zero" else P["R"][d]
            flagged.append({"kind": "act_break", "metric": "ret_dau", "dir": "down", "from": d, "to": d, "before": b["exp"],
                            "now": now, "rel": (now / b["exp"] - 1) if b["exp"] else None, "z": None, "gap": 2,
                            "bkind": b["kind"]})
            continue
        for m in DRIFT_METRICS:
            if m not in P["fast"]:
                continue
            sp = _spike_day(P, m, d)
            if sp:
                flagged.append({"kind": "act_spike", "metric": m, "dir": sp["dir"], "from": d, "to": d,
                                "before": sp["med"], "now": sp["now"], "rel": sp["rel"], "z": sp["z"], "gap": 2,
                                "lo": sp["lo"], "hi": sp["hi"]})
    flagged.sort(key=lambda f: (f["kind"], f["metric"], f["dir"], f["to"], f["from"]))
    segs = []
    for f in flagged:
        last = segs[-1] if segs else None
        if (last and last["kind"] == f["kind"] and last["metric"] == f["metric"] and last["dir"] == f["dir"]
                and f["to"] - last["to"] <= f["gap"]):
            last["to"] = max(last["to"], f["to"])
            if f["z"] is not None and (last["z"] is None or abs(f["z"]) > abs(last["z"])):
                for k in ("from", "before", "now", "rel", "z", "lo", "hi", "win", "bfrom"):   # the strongest window
                    if k in f:
                        last[k] = f[k]
            continue
        segs.append(dict(f))
    spans = []
    for e in eps_all:
        a = e["last"].get("since") or e["last"].get("day") or e["last"].get("installs_from") or e["opened"]
        b = e.get("last_day") or e.get("closed") or e["last_true"]
        km = e.get("key_metric") or e["metric"]
        spans.append((e["family"], km, e["metric"], e["dir"], _d(a), _d(b)))
    E = P["E"]
    out = []
    rels = [(_d(u["date"]), u) for u in (udet.get("impact") or {}).get("updates") or []]
    fast = [(x["kind"], x["dir"], P["days"][x["from"]]) for x in segs
            if x["metric"] == "ret_dau" and x["kind"] in ("act_drift", "act_spike", "act_break")]
    fast += [(fam, dr, ea) for fam, km, mm, dr, ea, eb in spans
             if fam in ("act_drift", "act_spike", "act_break") and "ret_dau" in (km, mm)]
    for s in segs:
        a, b = P["days"][s["from"]], P["days"][s["to"]]
        if any(fam == s["kind"] and (s["metric"] in (km, mm) or (km == "usage" and s["metric"] in ("sess", "time")))
               and dr == s["dir"] and a <= eb and ea <= b for fam, km, mm, dr, ea, eb in spans):
            continue
        if s["kind"] == "act_slow" and any(dr == s["dir"] and P["days"][max(0, s["bfrom"])] <= fa <= b
                                           for _, dr, fa in fast):
            continue                                  # a drift / spike / break already told this change
        rel = next(({"key": u["key"], "label": u["label"], "date": u["date"]} for R, u in rels
                    if R - timedelta(days=LINK_BEFORE) <= a <= R + timedelta(days=LINK_AFTER)), None)
        snap = {"family": s["kind"], "metric": s["metric"], "dir": s["dir"], "since": _iso(a), "day": _iso(a),
                "before": s["before"], "now": s["now"], "rel": s["rel"] or 0.0, "lo": s.get("lo"), "hi": s.get("hi"),
                "kind": s.get("bkind"), "expected": s["before"], "release": rel}
        rule = None
        if s["kind"] in ("act_drift", "act_slow") and s["metric"] == "ret_dau" and s.get("win"):
            w0, w1, b0, b1 = s["win"]                  # the same install attribution as a live alert (§2.8)
            att = _inst_attr(P, w0, w1, b0, b1, s["rel"], beta_hat(P, w0))
            rule = _inst_rule(att, s["rel"], SLOW_MIN_REL if s["kind"] == "act_slow" else None)
            if rule == "cap":
                snap.update(tags=["installs"], inst=_inst_snap(att, s["rel"]))
        text = alert_text(snap, E)
        if rule == "info" or (rule == "cap" and s["dir"] == "up"):             # the installs explain it: said so
            text = _inst_info(P, s["dir"], s["rel"], None, None, slow=s["kind"] == "act_slow")["text"]
        if s["kind"] in ("act_drift", "act_slow") and s["to"] != s["from"]:
            text += " (%s tak)" % U.fmt_day(b, E)
        out.append({"kind": s["kind"], "metric": s["metric"], "dir": s["dir"], "from": _iso(a), "to": _iso(b),
                    "before": _g4(s["before"]), "now": _g4(s["now"]), "rel": _m4(s["rel"]),
                    "z": round(s["z"], 2) if s["z"] is not None else None, "release": rel, "text": text})
    out.sort(key=lambda o: (o["to"], o["from"], o["kind"], o["metric"]), reverse=True)
    return out


# ── market-wide eCPM (the pre-pass over every GA4 app's revenue) ────────────────────────────────

def market(revs, till):
    """revs = [{AdMob day: [micros, impressions]}] (one per GA4 app), till = the revenue's last day → {weeks: [the
    market-wide weeks of the last MARKET_WEEKS settled Mon–Sun weeks, newest first], latest}. A week is market-wide when
    ≥ MARKET_MIN_APPS apps (≥ MARKET_MIN_IMPS impressions that week and the 4 before) take part and ≥ MARKET_SHARE of
    them moved the same way by ≥ MARKET_MIN_REL. apps = those taking part, of = those that moved that way."""
    till = _d(till)
    b = till - timedelta(days=(till.weekday() + 1) % 7)
    weeks = []
    for w in range(MARKET_WEEKS):
        we = b - timedelta(days=7 * w)
        ws = we - timedelta(days=6)
        ps, pe = ws - timedelta(days=28), ws - timedelta(days=1)
        rels = []
        for days in revs:
            rw = iw = rp = ip = 0.0
            for k, v in days.items():
                d = k
                if ws.isoformat() <= d <= we.isoformat():
                    rw, iw = rw + (v[0] or 0), iw + (v[1] or 0)
                elif ps.isoformat() <= d <= pe.isoformat():
                    rp, ip = rp + (v[0] or 0), ip + (v[1] or 0)
            if iw >= MARKET_MIN_IMPS and ip * 7 / 28 >= MARKET_MIN_IMPS and rp > 0 and rw > 0:
                rels.append((rw / iw) / (rp / ip) - 1)
        n = len(rels)
        if n < MARKET_MIN_APPS:
            continue
        up = sum(1 for r in rels if r >= MARKET_MIN_REL)
        dn = sum(1 for r in rels if r <= -MARKET_MIN_REL)
        for dr, k in (("up", up), ("down", dn)):
            if k >= MARKET_SHARE * n:
                weeks.append({"from": ws.isoformat(), "to": we.isoformat(), "dir": dr, "share": round(k / n, 4),
                              "apps": n, "of": k, "median_rel": _m4(_med(rels))})
                break
    return {"weeks": weeks, "latest": weeks[0] if weeks else None}


# ── one app: evaluate → detail + summary row ────────────────────────────────────────────────────

def evaluate(store, app_id, app, state, now_iso, udet, key, revenue, mkt, *, stale=False, outdated=False,
             late_un=U.LATE_DAYS, cfg=None):
    """Evaluate one app → (detail, row). Changes only `state` (this tab's own, active_state.json); `udet` (the uninstall
    detail) is read, never changed — whatever is kept from it is a deep copy."""
    cfg = cfg or {}
    E = _d(store["window_end"])
    P = prepare(store, udet, revenue, E, cfg, late_un)
    P["nmax"] = _nmax(P)
    P["ref_raw"] = [None] + [_ret_ref(P, N, P["i0"], P["iS"] - N)[0] for N in range(1, COHORT_DAYS + 1)]
    iS, S, iso = P["iS"], P["S"], P["iso"]
    recent_from = E - timedelta(days=ALERT_RECENT_DAYS)
    src = [store.get("property_id"), store.get("stream_id")]
    evs = state.setdefault("eval", {})
    prev = evs.get(app_id)
    moved = prev is not None and prev.get("src") is not None and list(prev["src"]) != src
    if moved:                                         # the app moved stream: its Active history starts over
        state["episodes"] = {k: e for k, e in (state.get("episodes") or {}).items() if e["app_id"] != app_id}
        state["closed"] = [e for e in state.get("closed") or [] if e["app_id"] != app_id]
        prev = None
    first = prev is None
    advanced = first or E > _d(prev["end"])
    ev = copy.deepcopy(prev) if prev else {}
    edges = _edges(P, store, ga4_trunc(store))
    # inputs: the E each input was first seen (never now) — a burn-in clock for the metrics it feeds
    inputs = dict(ev.get("inputs") or {"usage": None, "ret": None, "ret_edge": None, "rev": None})
    if P["has_usage"] and not inputs.get("usage"):
        inputs["usage"] = _iso(E)
    if P["has_ret"] and not inputs.get("ret"):
        inputs["ret"] = _iso(E)
    if edges["ret_state"] in ("found", "whole", "unverified") and not inputs.get("ret_edge"):
        inputs["ret_edge"] = _iso(E)
    if P["rev"] is not None and not inputs.get("rev"):
        inputs["rev"] = _iso(E)
    beta = ev.get("beta") or {}
    if not beta.get("at") or (E - _d(beta["at"])).days > BETA_DAYS:
        b = beta_hat(P, iS - TILE_DAYS + 1)
        beta = {"v": None if b is None else round(b, 4), "at": _iso(E)}
    eps_before = [e for e in (state.get("episodes") or {}).values() if e["app_id"] == app_id]
    closed_before = [e for e in state.get("closed") or [] if e["app_id"] == app_id]
    conds, info = conditions(P, iS, ev, eps_before, beta["v"], recent_from, closed_before)
    streak, since = dict(ev.get("streak") or {}), dict(ev.get("since") or {})
    holding = {}
    for fam, km in (("act_drift", "ret_dau"), ("act_drift", "usage"), ("act_drift", "ads"), ("act_slow", "ret_dau")):
        for dr in ("up", "down"):
            holding["%s|%s|%s" % (fam, km, dr)] = any(c["family"] == fam and c["key_metric"] == km and c["dir"] == dr
                                                      for c in conds)
    if advanced:
        U.advance_streaks(streak, since, holding, E)
    claimed = {dr: list(r) for dr, r in (ev.get("claimed") or {}).items()}
    ready = []
    for c in conds:
        if c["family"] in ("act_drift", "act_slow"):
            k = "%s|%s|%s" % (c["family"], c["key_metric"], c["dir"])
            if not (first or (streak.get(k, 0) >= DRIFT_PERSIST and since.get(k)
                              and (E - _d(since[k])).days >= DRIFT_CONFIRM_DAYS)):
                continue
        c["key"] = _key(c, app_id)
        rel, cap = _link(c, udet)
        seed = first or bool(outdated)
        if rel is not None:
            c["release"] = rel
            if cap is not None:                       # an open Update impact alert already covers it: no double send
                seed = True                           # (and no second count in the Alerts badge)
                c["severity"] = _cap(c["severity"], cap)
                c["linked"] = True
        if c.get("cap"):
            c["severity"] = _cap(c["severity"], c["cap"])
        ms = _metrics_of(c)
        for x, mm in (("usage", ("sess", "time", "usage")), ("rev", ("ads",))):
            if any(m in mm for m in ms) and inputs.get(x) and (E - _d(inputs[x])).days < ACT_BURNIN_DAYS:
                seed = True
        if c["family"] == "act_return":
            re_ = inputs.get("ret_edge")
            if not re_ or (E - _d(re_)).days < ACT_BURNIN_DAYS:
                seed = True
            claimed[c["dir"]] = U._add_ranges(claimed.get(c["dir"]), [[c["installs_from"], c["installs_to"]]])
        c["seed"] = seed
        ready.append(c)
    open_eps = episodes(state, app_id, E, ready, advanced, now_iso, recent_from)
    if outdated:
        for e in open_eps:
            if e.get("notified_at") is None:
                e.update(notified_at=now_iso, seeded=True)
    evs[app_id] = {"end": _iso(E), "src": src, "streak": streak, "since": since,
                   "claimed": {dr: r for dr, r in sorted(claimed.items()) if r}, "beta": beta, "inputs": inputs}
    alerts = sort_alerts([alert_obj(e, app, E) for e in open_eps])
    by_id = {e["id"]: e for e in open_eps}
    for a in alerts:
        e = by_id[a["id"]]
        a["_metrics"] = _metrics_of(dict(e["last"], family=e["family"], metric=e["last"].get("metric", e["metric"])))
        if e["family"] == "act_break":
            a["_when"] = _break_when({"day": e.get("day") or a["day"], "days_list": e.get("days")}, E)
    closed = [alert_obj(e, app, E) for e in state.get("closed") or [] if e["app_id"] == app_id]
    closed.sort(key=lambda a: (a["closed"], a["opened"], a["id"]), reverse=True)
    # tiles
    tiles = {}
    for m in ("ret_dau", "sess", "time", "ads", "ecpm"):
        tiles[m] = _tile_window(P, m, alerts)
    ar = _tile_window(P, "arpdau", alerts)
    ads, ec = tiles["ads"], tiles["ecpm"]
    if ar["st"] in ("normal", "maybe_dn", "maybe_up"):
        if ads["st"] in ("maybe_dn", "maybe_up", "worse", "watch", "better"):
            ar["st"] = ads["st"]
            if ar["rel"] is not None and ads["rel"] is not None and _sgn(ar["rel"]) != _sgn(ads["rel"]):
                ar["why"] = "ads_dir"
            else:
                ar["why"] = ads["why"]
        elif (ec["rel"] is not None and ec["z"] is not None and abs(ec["rel"]) >= MIN_REL["ads"]
              and abs(ec["z"]) >= Z_MAYBE and ec["st"] not in ("low", "wait", "noad", "growth")):
            ar["st"], ar["why"] = ("price_dn" if ec["rel"] < 0 else "price_up"), None
        else:
            ar["st"], ar["why"] = "normal", None
    tiles["arpdau"] = ar
    split = inst = None
    w0, b0, b1 = iS - TILE_DAYS + 1, iS - TILE_DAYS - BASE_DAYS + 1, iS - TILE_DAYS
    rd = tiles["ret_dau"]
    if b0 >= 0 and rd["rel"] is not None:
        att = _inst_attr(P, w0, iS, b0, b1, rd["rel"], beta["v"])
        if att["mode"] == "cohort":
            cw_ = _psum(P["p_yc"], w0, iS)
            cb_ = _psum(P["p_yc"], b0, b1)
            yw = _psum(P["p_Y"], w0, iS) / cw_ if cw_ else None
            yb = _psum(P["p_Y"], b0, b1) / cb_ if cb_ else None
            rw = _share(P["pn"]["ret_dau"], P["pc"]["ret_dau"], w0, iS)
            rb = _share(P["pn"]["ret_dau"], P["pc"]["ret_dau"], b0, b1)
            if None not in (yw, yb, rw, rb) and rw - yw > 0 and rb - yb > 0 and yb > 0:
                split = {"old_rel": _m4((rw - yw) / (rb - yb) - 1), "recent_rel": _m4(yw / yb - 1), "est": att["est"]}
        else:
            inst = {"rel": _m4(att["swing"]), "part": _m4(att["inst_part"]), "mode": att["mode"]}
        rule = _inst_rule(att, rd["rel"])
        if rule and rd["st"] in ("maybe_dn", "maybe_up"):
            rd["why"] = "installs"
    for m in ("sess", "time", "ads"):
        t = tiles[m]
        if t["st"] in ("maybe_dn", "maybe_up") and b0 >= 0 and _mix_moves(P, w0, iS, b0, b1, m):
            t["why"] = "mix"
    for k in ("d1", "d7"):
        tiles[k], _ = _tile_d(P, k, alerts, edges)
    # info rows: eCPM-only move (the market's), early looks
    if (ec["rel"] is not None and ec["z"] is not None and abs(ec["rel"]) >= MIN_REL["ads"] and abs(ec["z"]) >= Z_MAYBE
            and ads["st"] in ("normal",) and ec["st"] not in ("low", "wait", "noad", "growth")):
        dr = "up" if ec["rel"] > 0 else "down"
        row_ = {"kind": "price", "metric": "ecpm", "dir": dr, "from": ec["from"], "to": ec["to"], "rel": ec["rel"],
                "tags": [], "prov": False,
                "text": "Ad ka rate (eCPM) %s (%s), ads per user wahi — market/mediation/country mix ka asar, app ke "
                        "use ka nahi" % (U.fmt_rel(ec["rel"]), U.fmt_span(ec["from"], ec["to"], E))}
        for wk in (mkt or {}).get("weeks") or []:
            if wk["dir"] != dr:
                continue
            ov = (min(_d(wk["to"]), _d(ec["to"])) - max(_d(wk["from"]), _d(ec["from"]))).days + 1
            if ov >= 4:
                row_["tags"] = ["market_wide"]
                row_["text"] += " · %d me se %d apps me aisa" % (wk["apps"], wk["of"])
                break
        info.append(row_)
    for d, kind, exp_ in P["early"]:
        info.append({"kind": "early", "metric": "ret_dau", "dir": "down", "from": iso[d], "to": iso[d],
                     "rel": _m4((P["R"][d] or 0) / exp_ - 1) if exp_ else None, "tags": [], "prov": True,
                     "text": "⏳ %s (abhi aa raha): active users normal ke aadhe se bhi kam — 3 din me pakka hoga"
                             % U.fmt_day(P["days"][d], E)})
    eps_all = open_eps + [e for e in state.get("closed") or [] if e["app_id"] == app_id]
    older = history(P, eps_all, udet)
    # context + latest
    w_idx = [i for i in range(max(0, w0), iS + 1)] if iS >= 0 else []
    va = [P["a1"][i] for i in w_idx if P["valid"]["ret_dau"][i] and P["a1"][i] is not None]
    vn = [P["new"][i] for i in w_idx if P["valid"]["ret_dau"][i] and P["new"][i] is not None]
    vo = [P["old"][i] for i in w_idx if P["valid"]["ret_dau"][i] and P["old"][i] is not None]
    ctx = {"a1": _int(sum(va) / len(va)) if va else None, "new": _int(sum(vn) / len(vn)) if vn else None,
           "old": _int(sum(vo) / len(vo)) if vo and len(vo) >= 5 else None,
           "old_est": bool(vo) and any(P["oq"][i] == 1 for i in w_idx)}
    iE = P["iE"]
    latest = {"day": iso[iE] if iE >= 0 else None, "ret_dau": P["R"][iE] if iE >= 0 else None,
              "a1": P["a1"][iE] if iE >= 0 else None, "prov": True}
    summary = _summary(tiles, alerts, edges, P, E)
    for a in alerts:
        a.pop("_metrics", None)
        a.pop("_when", None)
    grid = _grid(P, udet, edges, state.get("portfolio_edge"))
    vers, vers_more = _versions(P, udet)
    rels = []
    ups = (udet.get("impact") or {}).get("updates") or []
    for r in udet.get("releases") or []:
        k = imp.rel_key(r)
        blk = next((u["key"] for u in ups if k in (u.get("rel_keys") or [])), None)
        rels.append({"date": r["date"], "version": r.get("version"), "kind": r.get("kind"), "key": blk})
    osh = other_share(P, max(0, w0), iS, "rev") if iS >= 0 else None
    daily = _daily_out(P, edges)
    bands = {}
    for m in BAND_METRICS:
        f = P["fast"].get(m)
        bands[m] = {k: [_g4(v) for v in getattr(f, k)] if f else [None] * P["H"] for k in ("med", "lo", "hi")}
    steep = {m: _spans(P, P["steep"][m]) for m in ("ret_dau", "sess", "time", "ads")}
    launch = udet.get("launch") or {}
    detail = {"v": ACT_V, "app_id": app_id, "app": app, "key": key, "tz": P["tz"], "rev_tz": P["rev_tz"],
              "currency": P["currency"], "history_start": _iso(P["hs"]), "data_till": _iso(E), "settled_till": _iso(S),
              "act_late_days": ACT_LATE_DAYS, "fetched_at": store.get("fetched_at"), "stale": bool(stale),
              "launch": {"day": launch.get("day"), "hidden": bool(launch.get("hidden")), "sure": bool(launch.get("sure"))},
              "stage": udet.get("stage"), "stage_why": udet.get("stage_why"), "zoom": copy.deepcopy(udet.get("zoom")),
              "releases": rels, "edges": edges,
              "flags": {"tz_blend": P["tz_blend"], "rev_est": P["rev"] is not None, "usage_split": P["cx"]["split"],
                        "vuse_split": P["cx"]["split"], "ret_short": edges["ret_short"], "ret_bad0": P["ret_bad0"],
                        "ret_empty": P["ret_empty"], "thresholded": bool(P["cx"]["thresholded"]),
                        "gap_g": _m4(gap_g(P, max(0, w0), iS)) if iS >= 0 else None, "inc_days": len(P["inc"]),
                        "rneg_days": len(P["rneg"]), "other_share": _m4(osh)},
              "daily": daily, "bands": bands, "steep": steep, "tiles": tiles, "ctx": ctx, "latest": latest,
              "split": split, "inst": inst, "summary": summary,
              "changes": {"open": alerts, "closed": closed, "info": info, "older": older},
              "tri": grid, "versions": vers, "versions_more": vers_more,
              "impact": copy.deepcopy(udet.get("impact") or {})}
    counts = {"warning": 0, "watch": 0, "good": 0}
    for a in alerts:
        counts[a["severity"]] = counts.get(a["severity"], 0) + 1
    win = {"from": iso[w0] if 0 <= w0 < P["H"] else None, "to": iso[iS] if 0 <= iS < P["H"] else None,
           "bfrom": iso[b0] if 0 <= b0 < P["H"] else None, "bto": iso[b1] if 0 <= b1 < P["H"] else None}
    mrow = {}
    for m in TILE_METRICS:
        t = dict(tiles[m])
        if m in WIN_METRICS:                          # their dates are the row's shared win; all / pp are the
            for k in ("from", "to", "bfrom", "bto", "all", "pp"):   # d-metrics' only (always null here) — the row
                t.pop(k, None)                        # stays under 2.5 KB with every metric populated
        mrow[m] = t
    row = {"app_id": app_id, "app": app, "key": key, "file": None, "sig": None, "status": "ok",
           "data_till": _iso(E), "settled_till": _iso(S), "stale": bool(stale), "stage": udet.get("stage"),
           "launch_day": launch.get("day"), "ready": (S - P["launch_day"]).days >= ACT_READY_DAYS,
           "edges": {k: edges[k] for k in ("hist", "ret_from", "ret_state", "usage_from", "usage_state", "rev_from",
                                          "rev_state")},
           "win": win, "m": mrow, "ctx": ctx, "latest": latest, "alerts": counts, "summary": summary}
    return detail, row


def _spans(P, mask):
    out, run = [], None
    for i, v in enumerate(mask):
        if v and i >= P["i0"]:
            run = [i, i] if run is None else [run[0], i]
        elif run is not None:
            out.append([P["iso"][run[0]], P["iso"][run[1]]])
            run = None
    if run is not None:
        out.append([P["iso"][run[0]], P["iso"][run[1]]])
    return out


def _daily_out(P, edges):
    H = P["H"]
    rev, imps = P["rev"], P["imp"]
    coh = {k: [None] * H for k in ("t", "d1", "d3", "d7", "d14", "d30", "ok")}
    for i in range(H):
        a = P["A"][i]
        if a is None:
            continue
        coh["t"][i] = P["T"][i]
        coh["ok"][i] = 1 if P["usable"][i] else 0
        if P["usable"][i]:
            for k, N in D_NS.items():
                if len(a) > N:
                    coh[k][i] = a[N]
    return {"start": _iso(P["hs"]), "a1": P["a1"], "new": P["new"], "ret": P["R"],
            "y": [_int(v) for v in P["Y"]], "old": [_int(v) for v in P["old"]], "oq": P["oq"],
            "old_k": next((P["Kd"][i] for i in range(H - 1, -1, -1) if P["Kd"][i]), None),
            "u": P["u"], "s": P["s"], "t": P["t"],
            "rev": [None if v is None else round(v, 4) for v in rev] if rev is not None else [None] * H,
            "imp": [None if v is None else int(round(v)) for v in imps] if imps is not None else [None] * H,
            "breaks": [P["iso"][i] for i in range(H) if P["brk"][i]],
            "inc": [P["iso"][i] for i in sorted(P["inc"])], "rneg": [P["iso"][i] for i in sorted(P["rneg"])],
            "rev_gaps": [list(g) for g in edges["rev_gaps"]], "coh": coh}


def _summary(tiles, alerts, edges, P, E):
    """{kind, text} — the one line at the top of the app (§2.15)."""
    open_ = [a for a in alerts]
    worse = [a for a in open_ if a["severity"] == "warning" and a["dir"] == "down"]
    suffix = ""
    if edges["ret_state"] in ("wait", "searching"):
        suffix += " · Wapsi (D1/D7) ka data abhi aa raha."
    if edges["usage_state"] == "wait":
        suffix += " · Sessions/time agle fetch me."
    if worse:
        more = len(open_) - 1
        return {"kind": "worse", "text": "⚠️ " + worse[0]["text"] + (" (+%d aur — neeche dekho)" % more if more else "")
                + suffix}
    br = [a for a in open_ if a["family"] == "act_break"]
    if br:
        when = br[0].get("_when") or "%s ko" % U.fmt_day(br[0]["day"], E)
        return {"kind": "break", "text": "🟡 Tracking check karo — %s active users normal ke aadhe se bhi kam"
                % when + suffix}
    wt = [a for a in open_ if a["dir"] == "down"]
    if wt:
        return {"kind": "slow" if wt[0]["family"] == "act_slow" else "watch", "text": "🟡 " + wt[0]["text"] + suffix}
    gd = [a for a in open_ if a["dir"] == "up"]
    if gd:
        return {"kind": "better", "text": "🟢 " + gd[0]["text"] + suffix}
    judged = [m for m in ("ret_dau", "d1", "d7", "sess", "time", "arpdau")
              if tiles[m]["st"] not in ("wait", "low", "noad", "growth")]
    growth = tiles["ret_dau"]["st"] == "growth"
    if growth:
        suffix = " · Purane users: App abhi tez %s raha hai — normal range abhi nahi banti." % (
            "badh" if (tiles["ret_dau"]["rel"] or 0) >= 0 else "ghat") + suffix
    if not judged:
        if growth:
            return {"kind": "wait", "text": "📈" + suffix[len(" · Purane users:"):]}
        if (P["S"] - P["launch_day"]).days < ACT_READY_DAYS:
            text = "⏳ Naya app — normal range %s se" % U.fmt_day(P["launch_day"] + timedelta(days=ACT_READY_DAYS), E)
        else:
            text = "⏳ Abhi kam data — normal range ke liye aur din chahiye"
        return {"kind": "wait", "text": text + suffix}
    maybe = [m for m in judged if tiles[m]["st"] in ("maybe_dn", "maybe_up")]
    if maybe:
        m = maybe[0]
        return {"kind": "maybe", "text": "✅ Sab normal range me — %s thoda %s dikh raha, par pakka nahi." % (
            SUMMARY_WORD[m], "kam" if tiles[m]["st"] == "maybe_dn" else "zyada") + suffix}
    parts = []
    if "ret_dau" in judged:
        parts.append("purane users")
    if "d1" in judged or "d7" in judged:
        parts.append("wapsi")
    if "sess" in judged or "time" in judged:
        parts.append("time")
    if "arpdau" in judged:
        parts.append("revenue")
    what = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " aur " + parts[-1]
    return {"kind": "ok", "text": "✅ Sab normal — %s apni normal range me." % what + suffix}


# ── replay: daily evaluations over one prepared history (calibration and the private verification only) ─────────

def replay(store, app_id, udet, revenue, days, cfg=None, late_un=U.LATE_DAYS, families=None, metrics=None,
           state_out=None):
    """Daily evaluations over the store's last `days` data days on ONE prepared history (each day's numbers read only
    the days before it — the replay sees what each day's build saw, except late data): conditions → persistence →
    episodes, every alert that was due marked sent at once → the notifications [(E, family, metric, dir, severity,
    tags)]. The first evaluation is seeded (never sent). families / metrics: only those (the rest are not evaluated).
    state_out: a dict that gets the final episodes / closed."""
    E = _d(store["window_end"])
    P = prepare(store, udet, revenue, E, cfg or {}, late_un)
    P["nmax"] = _nmax(P)
    if metrics is not None:
        P["only"] = set(metrics)
    st, ev, sent = {"episodes": {}, "closed": []}, None, []
    beta = {"v": None, "at": None}
    for back in range(days - 1, -1, -1):
        Ed = E - timedelta(days=back)
        iS = P["iS"] - back
        first = ev is None
        ev = ev or {"streak": {}, "since": {}, "claimed": {}}
        if beta["at"] is None or (Ed - _d(beta["at"])).days > BETA_DAYS:
            beta = {"v": beta_hat(P, iS - TILE_DAYS + 1), "at": Ed.isoformat()}
        recent_from = Ed - timedelta(days=ALERT_RECENT_DAYS)
        conds, _ = conditions(P, iS, ev, list(st["episodes"].values()), beta["v"], recent_from, st["closed"])
        conds = [c for c in conds if (families is None or c["family"] in families)
                 and (metrics is None or any(m in metrics for m in _metrics_of(c)))]
        holding = {}
        for c in conds:
            if c["family"] in ("act_drift", "act_slow"):
                holding["%s|%s|%s" % (c["family"], c["key_metric"], c["dir"])] = True
        for k in list(ev["streak"]):
            holding.setdefault(k, False)
        U.advance_streaks(ev["streak"], ev["since"], holding, Ed)
        ready = []
        for c in conds:
            if c["family"] in ("act_drift", "act_slow"):
                k = "%s|%s|%s" % (c["family"], c["key_metric"], c["dir"])
                if not (first or (ev["streak"].get(k, 0) >= DRIFT_PERSIST and ev["since"].get(k)
                                  and (Ed - _d(ev["since"][k])).days >= DRIFT_CONFIRM_DAYS)):
                    continue
            if c.get("cap"):
                c["severity"] = _cap(c["severity"], c["cap"])
            if c["family"] == "act_return":
                ev["claimed"][c["dir"]] = U._add_ranges(ev["claimed"].get(c["dir"]),
                                                        [[c["installs_from"], c["installs_to"]]])
            c["key"], c["seed"] = _key(c, app_id), first
            ready.append(c)
        for e in episodes(st, app_id, Ed, ready, True, "seeded", recent_from):
            if e.get("notified_at") is None:
                s = e["last"]
                sent.append((Ed.isoformat(), e["family"], s.get("metric", e["metric"]), e["dir"],
                             s.get("severity") or "watch", tuple(sorted(s.get("tags") or []))))
                e["notified_at"] = "sent"
    if state_out is not None:
        state_out.update(st)
    return sent
