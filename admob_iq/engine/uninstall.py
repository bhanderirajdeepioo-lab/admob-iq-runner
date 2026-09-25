"""Uninstall engine — pure math behind the GA4 Uninstall tab (no I/O, no prints).

Input is one app's GA4 store (admob_iq.fetch.ga4_uninstall: daily totals + app_remove users by install
day × lag); output is what the tab shows and which alerts are open.

  * DAILY RATE — app_remove users that day per 1,000 28-day active users (active28DayUsers): the line
    the tab shows. It is NOT what the rate alerts judge, because most uninstalls are brand-new installs
    (D0 alone is often ~60%), so the raw rate follows ad spend. The alerts judge the day's uninstalls
    against what that day's installs make EXPECTED: uninstalls by installs of the last 28 days = those
    installs × the usual share leaving on that day after install (the 28 days before), + the usual count
    from older users. More installs raise the expectation, not the alarm. The NORMAL BAND is on the log
    of actual ÷ expected (skewed day-to-day noise is symmetric there): median of the 28 days before ±
    BAND_K sigmas (how far the 8 weeks before sat from their own normal, floored at 10% and at Poisson
    noise), shown in rate units, so it moves with installs. A day outside it is a SPIKE; a steady shift
    over ≥1 week is DRIFT.
  * COHORT CHURN — of the users whose first session was day c (n_c = newUsers that day), the CUMULATIVE
    share that uninstalled by day N after it. A cohort counts for N only once complete (c + N <= E, the
    last settled GA4 day), so per cohort the curve can only rise. Every lag is kept — no day dropped.
  * HEADLINE CURVE — per N, the 28 newest complete install days: the same count for every N, but NOT the
    same install days, so the curve may dip (older installs had a different mix). The install-week
    TRIANGLE compares like with like.
  * CHECKPOINTS — which N to show and alert on, per app: every day while the app is new / small / still
    losing users fast, a sparse 1, 3, 7, 14, 30… ladder once it is big and stable, and daily detail again
    after a release or an alert. The curve is cumulative, so a change at a skipped N still shows at the
    next listed N (a D2 change shows at D3, a D10 change at D14).
  * RECENT-CHANGE ALERTS — at every listed N, the newest 7 complete install days vs the 4 weeks before AND
    vs all-time, both directions. Needs significance (two-proportion z, widened by how much the install
    days of the 4 weeks before really swing from day to day) AND a real effect AND (big apps) breadth +
    persistence. One condition per app and direction; alerts are EPISODES: open → notify once → close
    after 3 quiet daily evaluations → a re-open notifies again. The install days an alert was about are
    remembered per direction: the curve is cumulative, so the same bad install week shows again at D30,
    D45, D60… — that is old news and never re-alerts; only installs not alerted on yet can open a new one.
  * LATE DATA — Firebase keeps adding events for up to LATE_DAYS (~7) days (mostly app_remove, which Play
    reports late), and late data only ever ADDS. So the newest LATE_DAYS days are PROVISIONAL (S = E −
    LATE_DAYS is the last settled day): nothing that treats a LOW reading as news uses them — a "kam"
    (down) cohort alert counts install day c for N only if c + N <= S, a dip or a 0-uninstall day needs
    day <= S, a downward drift ends at S, a ▼ arrow comes from settled data, and no normal band, baseline or
    headline curve is built from them. A rise already visible in them is real (it can only grow), so "up"
    alerts may use them — their message says the newest days are still filling in (PROV_NOTE). Every "up"
    test also runs on the settled days: the provisional ones read LOW, so a moderate rise shows there only
    once its late data is in — about LATE_DAYS later, but never missed.
  * INCOMPLETE DAYS — days whose install-day cells GA4 never returned in full (the store's
    flags.incomplete_days, see fetch.ga4_uninstall) feed no baseline, and no cohort comparison counts an
    install day whose checkpoint window touches one: shown ("data adhoora"), never alerted on.
  * LATENESS — how much of a day's uninstalls / installs are in at each age, measured from the fetch's
    day-to-day re-reads (store["revisions"]) — see lateness().

Dates are datetime.date inside, ISO strings in and out. Fractions 0–1 (5 dp), rates per 1,000 (3 dp),
points = percentage points.
"""

import math
from datetime import date, timedelta

from ..alerting.rules import fingerprint

LAG_DAYS = 2              # GA4 settles in ~48h (mirrors fetch.ga4.LAG_DAYS without importing requests)
LATE_DAYS = 7             # Firebase adds events (mostly app_remove) up to ~7 days late: the newest 7 days are
                          # PROVISIONAL — they can only grow (config GA4_LATE_DAYS; the build passes it in)
PROV_NOTE = " · abhi ka data kaccha — number aur badh sakta hai"   # on an "up" alert that uses provisional days
LATE_MIN_USERS = 50       # lateness: an age needs ≥50 re-read users before its share is shown (fewer is noise)
NOT_SET = {"", "(not set)", "(other)", "(none)"}

# ── daily rate + normal band ──
YOUNG_DAYS = 28           # uninstalls by installs of the last 28 days are expected from those installs (see above)
BAND_DAYS = 28            # the 4 weeks before each day: every weekday counted 4 times
BAND_MIN_DAYS = 14        # a median of fewer days is noise, so no band yet
SCALE_DAYS = 56           # the band's WIDTH = how far the 8 weeks before sat from their own normal: a 4-week
                          # spread wobbles so much that a band a third too narrow now and then made "spikes"
BAND_K = 4.0              # ±4 sigmas on log(actual ÷ expected). A year of steady synthetic data with 10–20%
                          # day-to-day noise: ~0.1–0.2 false spikes per app (±3 on a 4-week MAD gave 2–6)
SPREAD_SIGMA = 1.2533     # scales the MEAN absolute deviation to a standard deviation: it wobbles far less than
                          # the MAD (a band a third too narrow now and then is what turned noise into "spikes")
BAND_REL_FLOOR = 0.10     # spread never below 10%, so a flat series (spread 0) doesn't flag wobbles
ARROW_REL = 0.10          # arrow: pooled last-7 rate at least ±10% vs its normal level

SPIKE_LOOKBACK = 3        # the 3 settled days before the provisional ones are judged too (a missed run can't hide
                          # a spike); a rise is looked for in every provisional day as well (late data can raise one)
SPIKE_MIN_USERS = 15      # tiny apps: 3 vs 1 uninstalls is not news
ZERO_MIN_EXPECTED = 20    # 0 on a day that should have ≥20 is a tracking break, not good news
SPIKE_KEEP_DAYS = 7       # a spike alert stays up a week after its (last) day
SPIKE_MERGE_DAYS = 2      # spike days ≤2 days apart are ONE jhatka — one alert, not one per day

DRIFT_MIN_DAYS, DRIFT_MAX_DAYS = 7, 42   # a slow change lasts ≥1 week; look back ≤6 weeks for its start
DRIFT_Z = 4.0             # after vs before, the noise of BOTH counted; ~36 start days are tried, so 4 (not 3):
                          # the same synthetic year gives ~0.25 false drifts per app (3–6 before)
DRIFT_MIN_REL = 0.15                     # smaller moves sit inside the normal weekly swing
DRIFT_SIDE = 0.7                         # a steady shift, not one spike day
DRIFT_MIN_USERS = 30; DRIFT_REL_FLOOR = 0.05   # ≥30 extra (or fewer) uninstalls in total; 5% spread floor
DRIFT_PERSIST = 2                        # seen on 2 daily evaluations …
DRIFT_CONFIRM_DAYS = 3                   # … and still there with ≥3 NEW days since it was first seen (the
                                         # windows of consecutive days share all but one day — not new evidence)
DRIFT_COVER = 0.8                        # ≥80% of the drift days need a rate
STALE_HOURS = 48                         # an app whose GA4 fetch is older than this is shown as "purana"
A28_FILL = 27             # GA4's 28-day actives only count a full 28 days from the app's 28th day of data

# ── cohort curve ──
HEAD_K = 28               # 28 newest complete install days per N: every weekday 4×, same count for every N
HEAD_MIN_COHORTS = 7      # a checkpoint needs ≥1 full week of complete installs
WILSON_Z = 1.96           # 95% interval
BREAK_MIN_PP = 0.5        # a tracking break only spoils an install day if it hit a day-after-install still
                          # losing ≥0.5% of installs (later days lose ~0.1%: leaving it in costs nothing)

# ── adaptive checkpoints ──
NEW_DAYS = 30; STABLE_DAYS = 90
CI_MAX_PP = 1.0           # "big enough": 95% CI at D1/D7/D30 within ±1 point (~≥350 installs/day)
STEEP_PP = 2.0            # a day that still loses ≥2% of installs is shown on its own — that's where the curve's shape lives
STEEP_MAX_N = 30; STABLE_MAX_STEEP_N = 7   # stable = the fast part of the curve ends within the first week
STAGE_HOLD = 7            # 7 daily evaluations in a row before switching to the sparse ladder (no flapping)
LADDER_GROW = (0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 14, 21, 30, 45, 60, 90, 120, 150)
LADDER_STABLE = (0, 1, 3, 7, 14, 30, 45, 60, 90, 120, 150); LADDER_STEP = 30
ZOOM_DAYS = 21; ZOOM_DENSE = 14           # 3 weeks of day-by-day detail after a release / an alert
RELEASE_SHARE = 0.05      # a version is "out" once ≥5% of that day's active users run it
UPDATE_SURGE_X = 3.0; UPDATE_MIN_USERS = 100   # app_update users ≥3× their 4-week median (and ≥100)
RELEASE_GAP_DAYS = 3      # an update surge this close to a release is that same release

# ── recent-change alerts ──
RECENT_K = 7; PREV_K = 28; RECENT_MIN = 5; PREV_MIN = 21; ALL_MIN_COHORTS = 56  # all-time only when ≥8 weeks, else it equals "pehle"
Z_MIN = 3.0               # ~1 in 370 by chance (z already corrected for real day-to-day swings, see dispersion)
MIN_PP = 2.0              # smaller moves aren't worth acting on
MIN_REL = 0.10            # of the SMALLER side (uninstalled or kept): 72%→79% = 25% fewer kept → alerts; 72%→74% = 7% → no
MIN_RECENT_USERS = 300; MIN_EVENTS = 10    # normal approximation needs ≥10 on each side
BIG_RECENT_USERS = 5000; BREADTH_MIN = 4; PERSIST_BIG = 2   # big apps: one bad install day or one run can't fire it
WARN_PP = 5.0; WARN_REL = 0.25; ARROW_PP = 1.0
CLOSE_EVALS = 3           # closes after 3 daily evaluations without the condition
FRESH_EVALS = 3           # "naya" badge for 3 days after opening
HEAD4 = (0, 1, 7, 30)     # the portfolio table's D columns

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
SEV_ORDER = {"warning": 0, "watch": 1, "good": 2}


# ── small helpers ────────────────────────────────────────────────────────────────────────────────

def _d(s):
    return s if isinstance(s, date) else date.fromisoformat(str(s)[:10])


def _iso(d):
    return d.isoformat() if d else None


def _r(v, dp):
    return None if v is None else round(v, dp)


def z2(x1, n1, x2, n2):
    """Two-proportion z score (pooled standard error) of x1/n1 vs x2/n2; None when it can't be computed.
    A copy of fetch.ga4._z2, so the engine never imports the requests-based fetch module."""
    if not n1 or not n2:
        return None
    p = (x1 + x2) / (n1 + n2)
    se = (p * (1 - p) * (1 / n1 + 1 / n2)) ** 0.5 if 0 < p < 1 else 0
    return round((x1 / n1 - x2 / n2) / se, 2) if se else None


def wilson(x, n, z=WILSON_Z):
    """95% Wilson interval of x/n → (lo, hi); (None, None) without users. GA4 user counts are approximate
    (x can pass n) — p is clamped to 0..1 for the interval only, never in what is shown."""
    if not n:
        return None, None
    p = min(max(x / n, 0.0), 1.0)
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


def spread(v, center):
    """Robust-enough standard deviation of v around its median `center`: 1.2533 × mean |x − center|."""
    return SPREAD_SIGMA * sum(abs(x - center) for x in v) / len(v) if v else 0.0


def median(v):
    v = sorted(v)
    n = len(v)
    return (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2) if n else None


def fmt_day(d):
    d = _d(d)
    return "%d %s" % (d.day, MONTHS[d.month - 1])


def fmt_span(a, b):
    """"12–18 Sep"; across months "28 Aug–3 Sep"; a single day "12 Sep"."""
    a, b = _d(a), _d(b)
    if a == b:
        return fmt_day(a)
    if (a.year, a.month) == (b.year, b.month):
        return "%d–%d %s" % (a.day, b.day, MONTHS[b.month - 1])
    return fmt_day(a) + "–" + fmt_day(b)


def _minus(s):
    return s.replace("-", "−")


def fmt_pct(p, dp=1):
    """Fraction → "72%" / "4.1%" (dp decimals)."""
    return _minus("%.*f%%" % (dp, p * 100))


def fmt_pp(d):
    """Signed percentage points, trailing ".0" trimmed: +7, −2.5."""
    s = ("%.1f" % abs(d)).rstrip("0").rstrip(".")
    return ("+" if d > 0 else "−" if d < 0 else "") + s


def fmt_rate(r):
    return _minus("%.1f" % r)


def fmt_rel(rel):
    return ("+" if rel > 0 else "−" if rel < 0 else "") + "%d%%" % round(abs(rel) * 100)


def shown_pct(old, new):
    """(old text, new text, shown Δ points): 0 decimals when the exact move is ≥5 points, else 1; the
    shown Δ is shown new − shown old, so the message always adds up."""
    dp = 0 if abs(new - old) * 100 >= 5 else 1
    o, n = float("%.*f" % (dp, old * 100)), float("%.*f" % (dp, new * 100))
    return fmt_pct(old, dp), fmt_pct(new, dp), round(n - o, dp)


# ── daily rate, normal band, spikes, drift ──────────────────────────────────────────────────────

def daily_series(store, E=None, cd=None, late=LATE_DAYS):
    """Columnar day-by-day arrays from history_start to E: new installs, uninstalling users, the rate
    denominator (active28DayUsers, or activeUsers when the store's den is "dau"), app_update users, the
    rate per 1,000 and its normal band. A day outside every fetched range is unknown (null), never 0.
    The rate stays null for the first A28_FILL days of an app's data (28-day actives still filling up).

    Behind the band (see the module docstring): exp[i] = the uninstalls day i's installs make normal,
    zs[i] = how far the day sits from it in robust sigmas (log scale), med/lo/hi = exp and its band in
    rate units. Every step only looks at days BEFORE i. A day with NO uninstall where ≥ZERO_MIN_EXPECTED
    were expected is a tracking break (broken[i]): shown as 0 and alerted as rate_zero, but never
    counted into a band, a drift or a cohort comparison — it isn't news about users. Only BASE days —
    good, settled (not among the last `late`) and not incomplete — go into a band or a baseline:
    provisional days read low until their late data is in, an incomplete day's install-day split is wrong."""
    hs, E = _d(store["history_start"]), _d(E or store["window_end"])
    n = max(0, (E - hs).days + 1)
    late = max(0, int(late or 0))
    S = n - late                                # index of the first provisional day
    inc = set()
    for k in ((store.get("flags") or {}).get("incomplete_days") or {}):
        inc.add((_d(k) - hs).days)
    covered = [(_d(a), _d(b)) for a, b in store.get("covered") or []]
    daily = store.get("daily") or {}
    dau = store.get("den") == "dau"
    fill = 0 if dau or store.get("history_capped") else A28_FILL
    new, un, den, upd, rate = [], [], [], [], []
    for i in range(n):
        d = hs + timedelta(days=i)
        r = daily.get(d.isoformat())
        if r is None and not any(a <= d <= b for a, b in covered):
            for arr in (new, un, den, upd, rate):
                arr.append(None)
            continue
        r = r or {}
        dv = r.get("a1") if dau else r.get("a28")
        new.append(r.get("new") or 0)
        un.append(r.get("un") or 0)
        den.append(dv if dv is None else int(dv))
        upd.append(r.get("upd") or 0)
        rate.append(round(un[-1] * 1000 / dv, 3) if dv and i >= fill else None)
    raw = cd["raw"] if cd is not None else _raw_lags(store, hs, n)[1]
    K = YOUNG_DAYS
    # uninstalls by installs of the last K days (from the install-day cells) and by everyone older
    young = [sum(raw[i - L].get(L, 0) for L in range(min(K - 1, i) + 1)) for i in range(n)]
    old = [None if un[i] is None else max(0, un[i] - young[i]) for i in range(n)]
    # running sums over the BASE days only (known, not a tracking break, settled, complete): per lag L, users
    # who left on day L after install (C) and those install days' installs (I) → the usual share leaving on day L
    C = [[0] * (n + 1) for _ in range(K)]
    I = [[0] * (n + 1) for _ in range(K)]
    V = [0] * (n + 1)
    q, dev, exp, zs, med, lo, hi, broken, good, base = [], [], [], [], [], [], [], [], [], []
    for i in range(n):
        a = max(0, i - BAND_DAYS)
        e0 = None
        if un[i] is not None and V[i] - V[a] >= BAND_MIN_DAYS:
            ey = 0.0
            for L in range(min(K - 1, i) + 1):
                ib = I[L][i] - I[L][a]
                if ib > 0 and new[i - L]:
                    ey += new[i - L] * (C[L][i] - C[L][a]) / ib
            e0 = ey + median([old[j] for j in range(a, i) if base[j]])
        q.append(math.log(max(un[i], 0.5) / e0) if e0 else None)     # 0.5: log of a 0-day stays finite
        prior = [q[j] for j in range(a, i) if base[j] and q[j] is not None]
        m = e = z = None
        if e0 and len(prior) >= BAND_MIN_DAYS:
            mq = median(prior)
            e = e0 * math.exp(mq)                                    # what a normal day would have had
            devs = [dev[j] for j in range(max(0, i - SCALE_DAYS), i) if base[j] and dev[j] is not None]
            sc = spread(devs, 0.0) if len(devs) >= BAND_DAYS else spread(prior, mq)
            sc = max(sc, BAND_REL_FLOOR, 1 / math.sqrt(max(e, 1)))
            z = (q[i] - mq) / sc
            if rate[i] is not None and den[i]:
                k = 1000 / den[i]
                m = (round(e * k, 3), round(e * math.exp(-BAND_K * sc) * k, 3), round(e * math.exp(BAND_K * sc) * k, 3))
        exp.append(e), zs.append(z), dev.append(q[i] - mq if z is not None else None)
        med.append(m and m[0]), lo.append(m and m[1]), hi.append(m and m[2])
        broken.append(bool(e is not None and un[i] == 0 and e >= ZERO_MIN_EXPECTED))
        good.append(un[i] is not None and not broken[i])
        base.append(good[i] and i < S and i not in inc)
        V[i + 1] = V[i] + base[i]
        for L in range(K):
            c, iL = C[L], I[L]
            c[i + 1], iL[i + 1] = c[i], iL[i]
            if base[i] and i >= L and new[i - L]:
                c[i + 1] += raw[i - L].get(L, 0)
                iL[i + 1] += new[i - L]
    return {"start": hs, "end": E, "n": n, "new": new, "un": un, "den": den, "upd": upd, "rate": rate,
            "med": med, "lo": lo, "hi": hi, "broken": broken, "exp": exp, "zs": zs, "good": good,
            "base": base, "late": late, "old": old, "C": C, "I": I}


def rate_spikes(ds, n=None):
    """Sudden days (of the first n) that have a band → conditions: the SPIKE_LOOKBACK settled days before the
    provisional ones, and the provisional ones themselves. A LOW reading (a dip, or 0) counts only on a
    settled day — late data can still raise a provisional one; a HIGH one counts on any of them (late data
    only adds), marked prov when the day is still provisional."""
    out = []
    n = ds["n"] if n is None else n
    S = n - ds.get("late", 0)                   # days before index S are settled
    for i in range(max(0, S - SPIKE_LOOKBACK), n):
        r, m, x, e, z = ds["rate"][i], ds["med"][i], ds["un"][i], ds["exp"][i], ds["zs"][i]
        if r is None or m is None:
            continue
        settled = i < S
        day = ds["start"] + timedelta(days=i)
        c = {"day": day, "now": r, "before": m, "lo": ds["lo"][i], "hi": ds["hi"][i], "users": x,
             "expected": e, "z": round(z, 2), "rel": x / e - 1 if e else None, "prov": not settled}
        if x == 0 and e >= ZERO_MIN_EXPECTED:
            if settled:
                out.append(dict(c, family="rate_zero", dir="down", severity="watch"))
        elif z >= BAND_K and x - e >= SPIKE_MIN_USERS:
            out.append(dict(c, family="rate_spike", dir="up", severity="warning"))
        elif z <= -BAND_K and e - x >= SPIKE_MIN_USERS and settled:
            out.append(dict(c, family="rate_spike", dir="down", severity="good"))
    return out


def _expect_from(ds, a, s):
    """Expected uninstalls of any day from the good days [a, s−1] ALONE (the usual share leaving per day after
    install there + their median count from older users) → fn(day index) → raw expected, or None. Kept on
    `ds` per baseline, so judging day after day (rate_drift for each n) reuses what it already worked out."""
    memo = ds.setdefault("_expect", {})
    if (a, s) in memo:
        return memo[(a, s)]
    K, C, I, new = YOUNG_DAYS, ds["C"], ds["I"], ds["new"]
    h = [(C[L][s] - C[L][a]) / (I[L][s] - I[L][a]) if I[L][s] > I[L][a] else 0.0 for L in range(K)]
    eo = median([ds["old"][j] for j in range(a, s) if ds["base"][j]]) or 0
    got = {}

    def f(i):
        if i not in got:
            e = eo + sum(new[i - L] * h[L] for L in range(min(K - 1, i) + 1) if new[i - L])
            got[i] = e if e > 0 else None
        return got[i]
    memo[(a, s)] = f
    return f


def rate_drift(ds, n=None, want=None):
    """A slow, steady change that ends at day n−1 (default E) → {since, before, now, rel, z, dir, …} or
    None. For every start s 7–42 days back, the days since s are judged against what the 4 weeks before
    s make expected (so the new level can't leak into its own baseline, and installs are allowed for):
    z = mean log(actual ÷ expected) after vs its median before, with the noise of BOTH. The largest |z|
    wins (ties: the earlier s). before / now = rate per 1,000 expected at the old level vs actual.
    want = "up" / "down": only a change that way (see drift_now)."""
    n, best = ds["n"] if n is None else n, None
    for L in range(DRIFT_MIN_DAYS, DRIFT_MAX_DAYS + 1):
        s = n - L
        if s < BAND_MIN_DAYS:
            break
        a = max(0, s - BAND_DAYS)
        bef = [j for j in range(a, s) if ds["base"][j]]
        aft = [i for i in range(s, n) if ds["good"][i] and ds["rate"][i] is not None and ds["den"][i]]
        if len(aft) < DRIFT_COVER * L or len(bef) < BAND_MIN_DAYS:
            continue
        f = _expect_from(ds, a, s)
        eb = [(j, f(j)) for j in bef]
        ea = [(i, f(i)) for i in aft]
        rb = [math.log(max(ds["un"][j], 0.5) / e) for j, e in eb if e]
        ra = [math.log(max(ds["un"][i], 0.5) / e) for i, e in ea if e]
        if len(rb) < BAND_MIN_DAYS or len(ra) < DRIFT_COVER * L:
            continue
        mb = median(rb)
        su = sum(ds["un"][i] for i, e in ea if e)
        se_ = sum(e * math.exp(mb) for i, e in ea if e)              # expected at the old level
        sd = sum(ds["den"][i] for i, e in ea if e)
        pois = 1 / math.sqrt(max(se_ / len(ra), 1))
        sc = max(spread(rb, mb), DRIFT_REL_FLOOR, pois)
        shift = sum(ra) / len(ra) - mb               # a MEAN after: a start too early dilutes it (the true start wins)
        z = shift / (sc * math.sqrt(1 / len(ra) + 1.571 / len(rb)))        # 1.571: a median's extra noise
        rel = su / se_ - 1 if se_ else 0.0
        side = sum(1 for x in ra if (x > mb if shift > 0 else x < mb)) / len(ra)
        extra = abs(su - se_)
        if want and (rel > 0) != (want == "up"):
            continue
        if (abs(z) >= DRIFT_Z and abs(rel) >= DRIFT_MIN_REL and (rel > 0) == (shift > 0) and side >= DRIFT_SIDE
                and extra >= DRIFT_MIN_USERS):
            if best is None or abs(z) >= abs(best["z"]):              # >= : a longer window = an earlier s
                best = {"since": ds["start"] + timedelta(days=s), "before": se_ * 1000 / sd, "now": su * 1000 / sd,
                        "rel": rel, "z": round(z, 2), "dir": "up" if rel > 0 else "down", "days": L, "users": su,
                        "extra": round(extra), "base_from": ds["start"] + timedelta(days=a),
                        "base_to": ds["start"] + timedelta(days=s - 1)}
    return best


def drift_now(ds, n=None):
    """The drift at day n−1 (default E): a RISE may end on the provisional days (late data only adds
    uninstalls — a rise already visible is real; marked prov; drift windows run up to 6 weeks, so the few
    provisional days still reading low barely dilute it), a FALL is judged on settled days only, ending at
    the last settled day. A rise wins over a fall (the bad news is the one to act on)."""
    n = ds["n"] if n is None else n
    late = ds.get("late", 0)
    up = rate_drift(ds, n, "up")
    if up:
        return dict(up, prov=late > 0)
    down = rate_drift(ds, n - late, "down")
    return dict(down, prov=False) if down else None


# ── cohort curve ────────────────────────────────────────────────────────────────────────────────

def cohort_data(store, E=None, broken=None):
    """Per install day c in [history_start, E] (index i = c − history_start): n[i] = new installs,
    cum[i] = cumulative uninstalling users for lags 0..age (age = E − c), raw[i] = {lag: users}.
    `broken` = daily_series' tracking-break flags (same index), see mark_breaks."""
    hs, E = _d(store["history_start"]), _d(E or store["window_end"])
    H = max(0, (E - hs).days + 1)
    n, raw = _raw_lags(store, hs, H)
    cum = []
    unplaced, over = sum((store.get("unplaced") or {}).values()), 0
    for i in range(H):
        lags, age = raw[i], H - 1 - i
        row, run = [0] * (age + 1), 0
        for lag in range(age + 1):
            run += lags.get(lag, 0)
            row[lag] = run
        if not n[i]:
            unplaced += run                    # uninstalls with no install count to sit against: shown, not used
        elif run > n[i]:
            over += 1                          # GA4 counts are approximate — shown, never clipped
        cum.append(row)
    inc = sorted(i for i in ((_d(k) - hs).days for k in (store.get("flags") or {}).get("incomplete_days") or {})
                 if 0 <= i < H)
    cd = {"hs": hs, "E": E, "H": H, "n": n, "cum": cum, "raw": raw, "inc": inc,
          "flags": {"unplaced_users": int(unplaced), "over_100": over}}
    mark_breaks(cd, broken)
    return cd


def mark_breaks(cd, broken):
    """Tracking-break days (daily_series' broken flags) → what an alert comparison leaves out. A break on
    day b hides that day's app_remove of EVERY install day, at a different day-after-install each. It only
    matters where that day still loses a real share of installs: nb[i] = the first break ≥ install day i,
    lmat = the last day-after-install (≤ STEEP_MAX_N) still losing ≥ BREAK_MIN_PP % of installs. Install
    day i is left out of checkpoint N when its break falls on day 0..min(N, lmat) after install — so one
    GA4 hiccup costs the 8 or so install days around it, not every checkpoint for months."""
    H, n, raw = cd["H"], cd["n"], cd["raw"]
    brk = [bool(broken and i < len(broken) and broken[i]) for i in range(H)]
    nb, nxt = [H] * H, H
    for i in range(H - 1, -1, -1):
        if brk[i]:
            nxt = i
        nb[i] = nxt
    lmat = 0
    for L in range(min(STEEP_MAX_N, H - 1) + 1):
        top = H - 1 - L
        on = users = 0
        for i in range(max(0, top - HEAD_K + 1), top + 1):
            if n[i] and not brk[i + L]:
                on, users = on + raw[i].get(L, 0), users + n[i]
        if users and on * 100 / users >= BREAK_MIN_PP:
            lmat = L
    cd["nb"], cd["lmat"] = nb, lmat
    cd["breaks"] = [i for i in range(H) if brk[i]]
    # incomplete days (cells GA4 never returned in full): ni[i] = the first one ≥ install day i. Unlike a
    # break it can hide a share of ANY day-after-install, so it spoils every checkpoint whose days it touches
    inc, ni, nxt = set(cd.get("inc") or []), [H] * H, H
    for i in range(H - 1, -1, -1):
        if i in inc:
            nxt = i
        ni[i] = nxt
    cd["ni"] = ni
    return cd


def _pool(cd, i0, i1, N, per=False, clean=False, skip=None):
    """Σ uninstalled-by-N and Σ installs over the NON-EMPTY cohorts with index in [i0, i1] that are complete
    for N → (x, n, k[, [(x_c, n_c, i)]]). clean: also skip install days with a tracking break in days
    0..min(N, lmat) or an incomplete day in days 0..N (see mark_breaks). skip: install-day indexes left out
    as well."""
    x = n = k = 0
    each = []
    nb = cd.get("nb") if clean else None
    ni = cd.get("ni") if clean else None
    reach = min(N, cd.get("lmat", N))
    for i in range(max(0, i0), min(i1, cd["H"] - 1 - N) + 1):
        nc = cd["n"][i]
        if not nc or (nb and nb[i] <= i + reach) or (ni and ni[i] <= i + N) or (skip and i in skip):
            continue
        xc = cd["cum"][i][N]
        x, n, k = x + xc, n + nc, k + 1
        if per:
            each.append((xc, nc, i))
    return (x, n, k, each) if per else (x, n, k)


def headline_curve(cd, late=0):
    """For EVERY N in 0..H−1: the HEAD_K newest complete install days → p, Wilson lo/hi, users, cohorts k,
    and inc = % of installs uninstalling ON day N (how steep the curve still is). late: an install day c
    counts for N only once c + N is SETTLED (≤ E − late) — provisional days read low, and the curve (and the
    checkpoints chosen from it) must not dip because of them."""
    H = cd["H"]
    out = {k: [] for k in ("p", "lo", "hi", "users", "k", "inc")}
    for N in range(H):
        top = H - 1 - N - late
        x, n, k = _pool(cd, top - HEAD_K + 1, top, N)
        on = sum(cd["raw"][i].get(N, 0) for i in range(max(0, top - HEAD_K + 1), top + 1) if cd["n"][i])
        lo, hi = wilson(x, n)
        out["p"].append(_r(x / n, 5) if n else None)
        out["lo"].append(_r(lo, 5)), out["hi"].append(_r(hi, 5))
        out["users"].append(n), out["k"].append(k)
        out["inc"].append(round(on / n * 100, 3) if n else None)
    return out


def _win(cd, i0, i1):
    """Index window → ISO (from, to), clipped to the history."""
    i0, i1 = max(0, i0), min(i1, cd["H"] - 1)
    return _iso(cd["hs"] + timedelta(days=i0)), _iso(cd["hs"] + timedelta(days=i1))


def dispersion(cd, i0, i1, N):
    """Quasi-binomial dispersion φ of the per-install-day shares uninstalled by N over index window
    [i0, i1] (complete, non-empty days): 1 when the days differ only as much as pure chance would, more
    when real day-to-day swings (weekday, campaign / country mix) add to it — which the plain
    two-proportion z ignores, so on real data it calls noise "significant"."""
    x, n, k, each = _pool(cd, i0, i1, N, per=True, clean=True)
    p = x / n if n else 0
    if k < 2 or not 0 < p < 1:
        return 1.0
    return sum((xc - nc * p) ** 2 / (nc * p * (1 - p)) for xc, nc, _ in each) / (k - 1)


def compare(cd, N, skip=None, late=0):
    """Checkpoint N: the RECENT_K newest complete install days (R) vs the PREV_K before them (P) and vs
    every older install day (A, all-time). A base fires when the sample is big enough, the move is
    significant (|z| >= Z_MIN, z = two-proportion z ÷ √φ, φ = the day-to-day dispersion of the 4 weeks
    before, never below 1) AND real (>= MIN_PP points and >= MIN_REL of the smaller side), and — for a
    big app — at least BREADTH_MIN of the recent days individually sit on the moved side.
    skip: install-day indexes left out of R (the ones an alert already covered — see evaluate_app).
    late: "complete" means settled — c + N ≤ E − late (the "down" test; see the module docstring)."""
    top = cd["H"] - 1 - N - late
    xr, nr, kr, each = _pool(cd, top - RECENT_K + 1, top, N, per=True, clean=True, skip=skip)
    pr = xr / nr if nr else None
    sample = kr >= RECENT_MIN and nr >= MIN_RECENT_USERS and xr >= MIN_EVENTS and nr - xr >= MIN_EVENTS
    f, t = _win(cd, top - RECENT_K + 1, top)
    if skip and each:                                  # the install days actually in R
        f, t = _win(cd, each[0][2], each[-1][2])
    reach = min(N, cd.get("lmat", N))
    rng = range(max(0, top - RECENT_K + 1), top + 1)
    lost = [cd["nb"][i] for i in rng if cd.get("nb") and cd["n"][i] and cd["nb"][i] <= i + reach]
    gap = [cd["ni"][i] for i in rng if cd.get("ni") and cd["n"][i] and cd["ni"][i] <= i + N]
    row = {"n": N, "late": late, "recent": {"p": _r(pr, 5), "users": nr, "from": f, "to": t, "k": kr, "x": xr},
           "low_sample": not sample, "prev": None, "all": None,
           "break_day": _iso(cd["hs"] + timedelta(days=min(lost))) if lost else None,
           "inc_day": _iso(cd["hs"] + timedelta(days=min(gap))) if gap else None}
    phi = max(1.0, dispersion(cd, top - RECENT_K - PREV_K + 1, top - RECENT_K, N))
    row["phi"] = round(phi, 3)
    for name, i0, need in (("prev", top - RECENT_K - PREV_K + 1, PREV_MIN), ("all", 0, ALL_MIN_COHORTS)):
        i1 = top - RECENT_K
        xb, nb, kb = _pool(cd, i0, i1, N, clean=True)
        if kb < need or not nb or pr is None:
            continue
        pb = xb / nb
        dpp = round((pr - pb) * 100, 6)              # rounded so float dust can't decide a flag at the edge
        z = z2(xr, nr, xb, nb)
        z = None if z is None else round(z / math.sqrt(phi), 2)
        small = min(pb, 1 - pb)
        relsm = abs(pr - pb) / small if small > 0 else float("inf")
        fires = (sample and xb >= MIN_EVENTS and nb - xb >= MIN_EVENTS and z is not None and abs(z) >= Z_MIN
                 and abs(dpp) >= MIN_PP and relsm >= MIN_REL)
        if fires and nr >= BIG_RECENT_USERS:
            moved = sum(1 for xc, nc, _ in each if (xc / nc > pb if dpp > 0 else xc / nc < pb))
            fires = moved >= BREADTH_MIN
        bf, bt = _win(cd, i0, i1)
        row[name] = {"p": _r(pb, 5), "users": nb, "from": bf, "to": bt, "delta_pp": round(dpp, 1), "z": z,
                     "fires": bool(fires), "k": kb, "x": xb, "rel_small": relsm, "exact_pp": dpp}
    return row


def triangle(cd, cols):
    """Install ISO-week × checkpoint grid, newest week first, EVERY week. A cell is shown only when every
    install day of that week is complete for N; ref[N] = all-time pooled value (the heat reference)."""
    E, hs, H = cd["E"], cd["hs"], cd["H"]
    ref = []
    for N in cols:
        x, n, _ = _pool(cd, 0, H - 1, N)
        ref.append(_r(x / n, 5) if n else None)
    rows = []
    if H:
        wk = E - timedelta(days=E.weekday())            # Monday of E's week
        while wk + timedelta(days=6) >= hs:
            a, b = max(wk, hs), min(wk + timedelta(days=6), E)
            i0, i1 = (a - hs).days, (b - hs).days
            users = sum(cd["n"][i0:i1 + 1])
            p = []
            for N in cols:
                if (E - b).days < N:
                    p.append(None)
                    continue
                x, n, _ = _pool(cd, i0, i1, N)
                p.append(_r(x / n, 5) if n else None)
            iso = wk.isocalendar()
            rows.append({"week": "%d-W%02d" % (iso[0], iso[1]), "from": _iso(a), "to": _iso(b),
                         "days": i1 - i0 + 1, "users": users, "partial": i1 - i0 + 1 < 7, "p": p})
            wk -= timedelta(days=7)
    return {"cols": list(cols), "ref": ref, "rows": rows}


def lifetime(cd, ds):
    """"All time": everyone ever installed (any age) who has uninstalled by now, + the all-time median rate."""
    x = sum(cd["cum"][i][-1] for i in range(cd["H"]) if cd["n"][i])
    n = sum(cd["n"])
    rates = [r for r, b in zip(ds["rate"], ds["broken"]) if r is not None and not b]
    return {"p": _r(x / n, 5) if n else None, "users": n, "un": x, "rate_all_med": _r(median(rates), 3)}


def releases(store, ds):
    """Releases, oldest first: the first day a new appVersion reached RELEASE_SHARE of that day's active
    users ("version"), or an app_update surge ("update") not already explained by a nearby release."""
    vers, daily = store.get("versions") or {}, store.get("daily") or {}
    days = sorted(d for d in vers if _d(d) <= ds["end"])
    first, out = {}, []
    for d in days:
        tot = (daily.get(d) or {}).get("a1") or sum(vers[d].values())
        for v, u in vers[d].items():
            if v not in NOT_SET and v not in first and tot and u / tot >= RELEASE_SHARE:
                first[v] = d
    start = days[0] if days else None
    for v, d in first.items():
        if d != start:                                # already out on the first day we have: not a release
            out.append({"date": d, "version": v, "kind": "version"})
    near = sorted(_d(r["date"]) for r in out)
    for i in range(ds["n"]):
        u = ds["upd"][i]
        prior = [x for x in ds["upd"][max(0, i - BAND_DAYS):i] if x is not None]
        if u is None or len(prior) < BAND_MIN_DAYS or u < UPDATE_MIN_USERS or u < UPDATE_SURGE_X * median(prior):
            continue
        d = ds["start"] + timedelta(days=i)
        if any(abs((d - r).days) <= RELEASE_GAP_DAYS for r in near):
            continue                                  # the same rollout (or a version release) — not a new one
        out.append({"date": _iso(d), "version": None, "kind": "update"})
        near.append(d)
    return sorted(out, key=lambda r: (r["date"], r["kind"], r["version"] or ""))


# ── adaptive checkpoints ────────────────────────────────────────────────────────────────────────

def checkpoints(cd, curve, H, rels, open_eps, prev_eval, advanced):
    """Which N this app shows and alerts on, and why (see the module docstring)."""
    E, nmax = cd["E"], H - HEAD_MIN_COHORTS
    ci_ns = [N for N in (1, 7, 30) if N <= nmax]
    hw = {N: (curve["hi"][N] - curve["lo"][N]) * 50 if curve["hi"][N] is not None else None for N in ci_ns}
    ci_ok = bool(ci_ns) and all(v is not None and v <= CI_MAX_PP for v in hw.values())
    dsteep = max([N for N in range(1, min(STEEP_MAX_N, nmax) + 1)
                  if curve["inc"][N] is not None and curve["inc"][N] >= STEEP_PP], default=0)
    if H < NEW_DAYS:
        raw = "naya"
    elif H >= STABLE_DAYS and ci_ok and dsteep <= STABLE_MAX_STEEP_N:
        raw = "stable"
    else:
        raw = "badh_raha"
    prev = prev_eval or {}
    if advanced:
        hold = prev.get("stable_hold", 0) + 1 if raw == "stable" else 0
        if raw == "stable" and (not prev_eval or hold >= STAGE_HOLD or prev.get("stage") == "stable"):
            stage = "stable"
        else:
            stage = "badh_raha" if raw == "stable" else raw
    else:
        hold, stage = prev.get("stable_hold", 0), prev.get("stage") or raw
    # zoom: daily detail for ZOOM_DAYS after a release, or after a cohort / drift alert opened
    cands = [(_d(r["date"]) + timedelta(days=ZOOM_DAYS), "release", r) for r in rels
             if 0 <= (E - _d(r["date"])).days <= ZOOM_DAYS]
    cands += [(_d(e["opened"]) + timedelta(days=ZOOM_DAYS), "alert", e) for e in open_eps
              if e.get("family") in ("cohort", "rate_drift")]
    zoom = None
    if cands and stage != "naya":
        until, why, src = max(cands, key=lambda c: c[0])
        if until >= E:
            what = ("Naya version %s" % src["version"] if src.get("version") else "App update") \
                if why == "release" else "Alert"
            when = fmt_day(src["date"] if why == "release" else src["opened"])
            zoom = {"until": _iso(until), "reason": why,
                    "label": "%s (%s) — %s tak har din" % (what, when, fmt_day(until))}
    if nmax < 0:
        cps = set()
    elif stage == "naya":
        cps = set(range(nmax + 1))
    else:
        ladder = LADDER_GROW if stage == "badh_raha" else LADDER_STABLE
        cps = set(ladder) | set(range(max(ladder) + LADDER_STEP, nmax + 1, LADDER_STEP)) | set(range(dsteep + 1))
        if zoom:
            cps |= set(LADDER_GROW) | set(range(ZOOM_DENSE + 1))
    cps = sorted(N for N in cps if 0 <= N <= nmax)
    per_day = round(sum(cd["n"][-28:]) / max(1, min(28, H)))
    if stage == "naya":
        why = "Sirf %d din ka data — isliye har din ka checkpoint" % H
    elif stage == "stable":
        why = "%d din ka data, roz ~%d installs, D%d ke baad curve dheemi — isliye 1, 3, 7, 14, 30…" % (H, per_day, dsteep)
    elif raw == "stable":
        why = "Stable ho raha hai — %d/%d din pakka, tab tak pehle hafte har din" % (hold, STAGE_HOLD)
    elif H < STABLE_DAYS:
        why = "Abhi %d din ka data — 90 din ke baad checkpoints door-door ho sakte hain" % H
    elif not ci_ok:
        why = "Roz ~%d installs — uninstall %% me ±1 point se zyada ghat-badh, isliye pehle hafte har din" % per_day
    else:
        why = "D%d tak roz 2%%+ installs hat rahe — isliye pehle hafte har din" % dsteep
    return {"stage": stage, "raw": raw, "stable_hold": hold, "list": cps, "nmax": nmax, "dsteep": dsteep,
            "ci_ok": ci_ok, "zoom": zoom, "why": why}


# ── alerts: conditions → episodes → alert objects ────────────────────────────────────────────────

def cohort_conditions(rows):
    """Group the firing checkpoints per direction into ONE condition (curves are cumulative, so one change
    shows at every later N): headline = the smallest N (newest installs, earliest signal)."""
    fired = {"up": {}, "down": {}}
    for row in rows:
        for base in ("prev", "all"):
            b = row[base]
            if b and b["fires"]:
                fired["up" if b["exact_pp"] > 0 else "down"].setdefault(row["n"], []).append(base)
    by_n = {row["n"]: row for row in rows}
    out = {}
    for dr, ns in fired.items():
        if not ns:
            continue
        N = min(ns)
        row, vs = by_n[N], ns[N]
        b = row["prev"] if "prev" in vs else row["all"]
        now, before = row["recent"]["p"], b["p"]
        _, _, sd = shown_pct(before, now)
        rel = (now - before) / before if before else 0.0
        # warning: a big move in points, or the uninstall share itself jumping by a quarter while it is the
        # SMALL side (4% → 6%). At late checkpoints the small side is the few who kept the app (~5%), where
        # 2 points is "40%" of it — that alone stays a watch, never an escalation to Telegram
        big = abs(sd) >= WARN_PP or (before < 0.5 and b["rel_small"] >= WARN_REL)
        out[dr] = {"family": "cohort", "dir": dr, "unit": "pct",
                   "severity": "good" if dr == "down" else "warning" if big else "watch",
                   "checkpoint": "D%d" % N, "n": N, "also": ["D%d" % k for k in sorted(ns) if k != N], "vs": vs,
                   "now": now, "before": before, "delta_pp": round((now - before) * 100, 1), "rel": round(rel, 4),
                   "z": b["z"], "installs_from": row["recent"]["from"], "installs_to": row["recent"]["to"],
                   "base_from": b["from"], "base_to": b["to"], "since": None, "day": None,
                   "users": row["recent"]["users"], "ns": sorted(ns),
                   "held": {k: by_n[k]["held"] for k in sorted(ns) if by_n[k].get("held")}}
    return out


def _cohort_text(s):
    old, new, sd = shown_pct(s["before"], s["now"])
    vs = s.get("vs") or []
    basis = ("pichhle 4 hafte aur all-time dono" if len(vs) > 1 else
             "pichhle 4 hafte" if vs == ["prev"] else "all-time normal")
    also = (" · %s bhi %s" % (", ".join(s["also"]), "upar" if s["dir"] == "up" else "neeche")) if s.get("also") else ""
    return "%s uninstall %s → %s (%s point) — %s ke installs, %s se %s%s" % (
        s["checkpoint"], old, new, fmt_pp(sd), fmt_span(s["installs_from"], s["installs_to"]), basis,
        "zyada" if s["dir"] == "up" else "kam", also)


def alert_text(family, dr, s):
    """The Hinglish message (without the leading "{app}: "); an "up" alert that rests on provisional days
    says so (PROV_NOTE) — the number can still grow, never shrink."""
    return _alert_text(family, dr, s) + (PROV_NOTE if s.get("prov") and dr == "up" else "")


def _alert_text(family, dr, s):
    if family == "cohort":
        return _cohort_text(dict(s, dir=dr))
    if family == "rate_spike":
        return "%s ko uninstall rate %s /1k active (normal %s–%s) — achanak %s (%d uninstalls)" % (
            fmt_day(s["day"]), fmt_rate(s["now"]), fmt_rate(s["lo"]), fmt_rate(s["hi"]),
            "zyada" if dr == "up" else "kam", s["users"])
    if family == "rate_zero":
        return "%s ko ek bhi uninstall record nahi hua (normal ~%d/din) — GA4/Firebase tracking check karo" % (
            fmt_day(s["day"]), round(s["expected"]))
    if family == "rate_drift":
        return "%s se uninstall rate %s → %s /1k active (%s) — dheere dheere %s" % (
            fmt_day(s["since"]), fmt_rate(s["before"]), fmt_rate(s["now"]), fmt_rel(s["rel"]),
            "badh raha hai" if dr == "up" else "ghat raha hai")
    return str(s.get("text") or "")


def _snap(c):
    """A condition → the JSON-safe snapshot an episode keeps (everything its alert object is built from)."""
    out = {}
    for k, v in c.items():
        if isinstance(v, date):
            v = v.isoformat()
        elif isinstance(v, float):
            v = round(v, 5)
        out[k] = v
    return out


def update_episodes(state, app_id, E, ready, advanced, first_eval, now):
    """Open / refresh / close this app's episodes from the conditions that are READY now. Pure: it only
    changes `state`. A new key opens an episode (on the app's first-ever evaluation it is SEEDED: shown,
    not sent); spike days ≤SPIKE_MERGE_DAYS from an open spike of the same kind fold into it. Only an
    evaluation whose E moved on counts misses / closes — the hourly runs in between change nothing."""
    eps, closed = state.setdefault("episodes", {}), state.setdefault("closed", [])
    E_iso, hit = _iso(_d(E)), set()
    for c in ready:
        key, snap = c["key"], _snap(c)
        ep = eps.get(key)
        spike = c["family"] in ("rate_spike", "rate_zero")
        if ep is None and spike:
            day = _d(c["day"])
            for k, e in eps.items():
                if (e["app_id"] == app_id and e["family"] == c["family"] and e["dir"] == c["dir"]
                        and _d(e["day"]) - timedelta(days=SPIKE_MERGE_DAYS) <= day
                        <= _d(e["last_day"]) + timedelta(days=SPIKE_MERGE_DAYS)):
                    key, ep = k, e
                    break
        if ep is None:
            opened = E_iso
            ep = {"id": fingerprint(app_id, "uninstall_" + c["family"], None, c["dir"], opened),
                  "app_id": app_id, "family": c["family"], "dir": c["dir"], "opened": opened, "last_true": E_iso,
                  "misses": 0, "notified_at": now if first_eval else None, "notified_dry": False,
                  "seeded": bool(first_eval), "last": snap}
            if spike:
                ep["day"] = ep["last_day"] = snap["day"]
            eps[key] = ep
        else:
            ep["last_true"], ep["misses"] = E_iso, 0
            if spike:
                ep["last_day"] = max(ep["last_day"], snap["day"])
                if snap["day"] == ep["day"]:
                    ep["last"] = snap                 # a later day of the run keeps the first day's story
            else:
                ep["last"] = snap
        hit.add(key)
    if advanced:
        for key in [k for k, e in eps.items() if e["app_id"] == app_id and k not in hit]:
            ep = eps[key]
            if ep["family"] in ("rate_spike", "rate_zero"):
                done = (_d(E) - _d(ep["last_day"])).days > SPIKE_KEEP_DAYS
            else:
                ep["misses"] += 1
                done = ep["misses"] >= CLOSE_EVALS
            if done:
                closed.append(dict(eps.pop(key), closed=E_iso))
    return [e for e in eps.values() if e["app_id"] == app_id]


def alert_obj(ep, app, E):
    """Episode → the alert object the Alerts screen and the notifications read. The message is rebuilt
    every build, so a renamed app shows its new name."""
    s, E = ep["last"], _d(E)
    prov = bool(s.get("prov")) and ep["dir"] == "up" and "closed" not in ep    # history: its days have settled
    text = alert_text(ep["family"], ep["dir"], dict(s, prov=prov))
    out = {"id": ep["id"], "source": "uninstall", "app_id": ep["app_id"], "app": app, "family": ep["family"],
           "dir": ep["dir"], "severity": s.get("severity") or "watch",
           "unit": "pct" if ep["family"] == "cohort" else "per1k",
           "checkpoint": s.get("checkpoint"), "n": s.get("n"), "also": list(s.get("also") or []),
           "vs": list(s.get("vs") or []), "now": s.get("now"), "before": s.get("before"),
           "delta_pp": s.get("delta_pp"), "rel": s.get("rel") if s.get("rel") is not None else 0.0,
           "z": s.get("z"), "installs_from": s.get("installs_from"), "installs_to": s.get("installs_to"),
           "base_from": s.get("base_from"), "base_to": s.get("base_to"), "since": s.get("since"),
           "day": s.get("day"), "users": int(s.get("users") or 0), "opened": ep["opened"],
           "provisional": prov,
           "last_seen": ep["last_true"], "fresh": (E - _d(ep["opened"])).days < FRESH_EVALS,
           "notify": ep.get("notified_at") is None, "data_till": _iso(E),
           "message": "%s: %s" % (app, text), "text": text}
    if "closed" in ep:                                # history only: never "new", never (re)sent
        out.update(closed=ep["closed"], fresh=False, notify=False)
    return out


def sort_alerts(alerts):
    """warning, watch, good; fresh first; newest opened first; then app."""
    return sorted(alerts, key=lambda a: (SEV_ORDER.get(a["severity"], 9), not a["fresh"],
                                         -_d(a["opened"]).toordinal(), a["app"].casefold(), a["id"]))


# ── one app: evaluate → detail + summary ──────────────────────────────────────────────────────────

def _delta(row, head):
    """A comparison row's move in points: a portfolio D cell (head) = recent − the 4 weeks before, from the
    shown values; a checkpoint-table row = vs the 4 weeks before, else vs all-time. None without a base."""
    if row is None:
        return None
    if head:
        b, p = row["prev"], row["recent"]["p"]
        return round((p - b["p"]) * 100, 1) if b and p is not None else None
    b = row["prev"] or row["all"]
    return b["delta_pp"] if b else None


def arrow(new, settled, head=False, lit=None):
    """→ (▲ / ▼ / None, the comparison that says so — the one a cell SHOWS, so its numbers agree with the
    arrow). ▲ from the newest comparison (late data only adds uninstalls: a rise already there is real), else
    from the settled one (compare(.., late) — the newest reads low until its late data is in); ▼ only from
    the settled one. lit = (dir, late) of an open alert at this checkpoint: its direction and its data."""
    if lit:
        return lit[0], (settled if lit[1] else new)
    d = _delta(new, head)
    if d is not None and d >= ARROW_PP:
        return "up", new
    d = _delta(settled, head)
    if d is not None and abs(d) >= ARROW_PP:
        return ("up" if d > 0 else "down"), settled
    return None, new


def _head(up, down, lit):
    """One portfolio-table D cell: recent 7 install days vs the 28 before (▼ and its numbers: settled data)."""
    if up is None:
        return None
    dr, row = arrow(up, down, True, lit)
    prov = row is up and down is not up             # the newest comparison: its day N is still provisional
    if row["recent"]["p"] is None:
        return None
    r, b = row["recent"], row["prev"]
    return {"p": r["p"], "prev": b["p"] if b else None, "delta_pp": _delta(row, True), "dir": dr,
            "alert": bool(lit), "low_sample": row["low_sample"], "from": r["from"], "to": r["to"],
            "prov": prov}


def _pooled_rate(ds, i0, i1):
    """Days [i0, i1): pooled rate vs the pooled normal level / band of the SAME days → (rate, med, lo, hi,
    rel). Days without a rate or with a tracking break are left out; once any of them has a band, only the
    days with one count — rate and "normal" always cover the same days."""
    idx = [i for i in range(max(0, i0), i1) if ds["rate"][i] is not None and not ds["broken"][i]]
    band = [i for i in idx if ds["med"][i] is not None]
    idx = band or idx
    sd = sum(ds["den"][i] for i in idx)
    rate = round(sum(ds["un"][i] for i in idx) * 1000 / sd, 3) if sd else None
    m = lo = hi = None
    if band and sd:
        m, lo, hi = (round(sum(ds[k][i] * ds["den"][i] for i in band) / sd, 3) for k in ("med", "lo", "hi"))
    return rate, m, lo, hi, ((rate - m) / m if rate is not None and m else None)


def _rate_now(ds, drift):
    """The last 7 days' pooled rate vs its normal (the UI's Rate KPI uses this same rule for any period).
    Those are the provisional days: a rise (↑, ≥ ARROW_REL) is read there; otherwise the 7 SETTLED days
    before them decide (↑ or ↓) — and then THOSE days are the ones shown (from / to, prov False). Out of
    band UNDER it (good news) only when the days shown are settled."""
    n, late = ds["n"], ds.get("late", 0)
    f, t = n - 7, n
    rate, m, lo, hi, rel = _pooled_rate(ds, f, t)
    dr = None if rel is None else "up" if rel >= ARROW_REL else "flat"
    if dr != "up" and late:
        got = _pooled_rate(ds, n - late - 7, n - late)
        if got[4] is not None and abs(got[4]) >= ARROW_REL:
            (rate, m, lo, hi, rel), f, t = got, n - late - 7, n - late
            dr = "up" if rel > 0 else "down"
    elif dr == "flat" and rel <= -ARROW_REL:
        dr = "down"
    day = lambda i: _iso(ds["start"] + timedelta(days=max(0, i))) if n else None    # noqa: E731
    prov = bool(late and t > n - late)
    return {"last7": rate, "med": m, "lo": lo, "hi": hi, "dir": dr, "from": day(f), "to": day(t - 1), "prov": prov,
            # under the band is good news: never from provisional days (they read low until their late data is in)
            "out_of_band": bool(rate is not None and lo is not None and (rate > hi or (rate < lo and not prov))),
            "drift": ({"since": _iso(drift["since"]), "before": round(drift["before"], 3),
                       "now": round(drift["now"], 3), "rel": round(drift["rel"], 4), "z": drift["z"],
                       "prov": bool(drift.get("prov"))}
                      if drift else None)}


def _fires(row, dr):
    """Does checkpoint row fire in direction dr against either base?"""
    return any(row[b] and row[b]["fires"] and (row[b]["exact_pp"] > 0) == (dr == "up") for b in ("prev", "all"))


def _claimed(cd, ranges):
    """Merged ISO install-date ranges → the install-day indexes they cover."""
    out = set()
    for a, b in ranges or []:
        out.update(range(max(0, (_d(a) - cd["hs"]).days), min((_d(b) - cd["hs"]).days, cd["H"] - 1) + 1))
    return out


def _add_ranges(ranges, add):
    """Merge ISO [from, to] ranges (adjacent days join)."""
    out = []
    for a, b in sorted((_d(a), _d(b)) for a, b in list(ranges or []) + list(add)):
        if out and a <= out[-1][1] + timedelta(days=1):
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [[_iso(a), _iso(b)] for a, b in out]


def new_cohort_rows(cd, rows, dr, claimed, is_open, late_days=0):
    """The checkpoint rows that are NEWS in direction dr. A firing row whose 7 install days include days an
    alert already covered (`claimed`) is judged again on the other days alone: still firing → news (its
    numbers are those days'); else, while the alert is still open, those days moving the same way by
    ≥ MIN_PP keep it alive (the change goes on) — and so does a row whose other days are all still
    PROVISIONAL at N (the last `late_days` days: they read low until their late data is in, so they can't
    tell yet — not a miss; row["held"] = those days: claimed like the rest, so the alert ends as it would,
    but not TOLD — see evaluate_app); else it is the old week showing again — dropped."""
    out = []
    for row in rows:
        if not _fires(row, dr):
            continue
        late, N = row.get("late", 0), row["n"]
        top = cd["H"] - 1 - N - late
        if not any(i in claimed for i in range(top - RECENT_K + 1, top + 1)):
            out.append(row)
            continue
        fresh = compare(cd, N, skip=claimed, late=late)
        free = [i for i in range(max(0, top - RECENT_K + 1), top + 1) if i not in claimed and cd["n"][i]]
        if _fires(fresh, dr):
            out.append(fresh)
        elif is_open and fresh["recent"]["k"] and any(
                fresh[b] and (fresh[b]["exact_pp"] > 0) == (dr == "up") and abs(fresh[b]["exact_pp"]) >= MIN_PP
                for b in ("prev", "all")):
            out.append(row)
        elif is_open and late_days and free and all(i + N > cd["H"] - 1 - late_days for i in free):
            out.append(dict(row, held=free))
    return out


def advance_streaks(streak, since, holding, E):
    """One more daily evaluation: +1 for each condition still holding (else back to 0); `since` keeps the
    day each current run of evaluations first saw its condition."""
    for k, h in holding.items():
        streak[k] = streak.get(k, 0) + 1 if h else 0
        if not h:
            since.pop(k, None)
        elif streak[k] == 1:
            since[k] = _iso(E)


def rate_ready(ds, drift, app_id, streak, since, E, first, n=None):
    """The daily-rate conditions that are ready to be (or stay) alerts at day n−1 (default E): a drift once
    it has held for DRIFT_PERSIST evaluations AND DRIFT_CONFIRM_DAYS new days since first seen (on an
    app's first evaluation straight away — seeded, not sent), and the spike / zero days."""
    out = []
    dk = drift and "drift|" + drift["dir"]
    if drift and (first or (streak.get(dk, 0) >= DRIFT_PERSIST and since.get(dk)
                            and (_d(E) - _d(since[dk])).days >= DRIFT_CONFIRM_DAYS)):
        out.append({"key": "%s|rate_drift|%s" % (app_id, drift["dir"]), "family": "rate_drift",
                    "dir": drift["dir"], "severity": "warning" if drift["dir"] == "up" else "good",
                    "now": drift["now"], "before": drift["before"], "delta_pp": None, "rel": drift["rel"],
                    "z": drift["z"], "since": drift["since"], "day": None, "users": drift["users"],
                    "base_from": drift["base_from"], "base_to": drift["base_to"], "prov": bool(drift.get("prov")),
                    "installs_from": None, "installs_to": None, "checkpoint": None, "n": None})
    for sp in rate_spikes(ds, n):
        if drift and sp["dir"] == drift["dir"] and sp["family"] == "rate_spike" and sp["day"] >= drift["since"]:
            continue                                  # part of a slow drift already in view — not "achanak"
        tail = sp["day"].isoformat()
        k = ("%s|rate_zero|%s" % (app_id, tail) if sp["family"] == "rate_zero"
             else "%s|rate_spike|%s|%s" % (app_id, sp["dir"], tail))
        out.append(dict(sp, key=k, delta_pp=None, since=None, checkpoint=None, n=None,
                        base_from=sp["day"] - timedelta(days=BAND_DAYS), base_to=sp["day"] - timedelta(days=1),
                        installs_from=None, installs_to=None))
    return out


def evaluate_app(store, app_id, app, state, now, stale=False, key=None, package=None, late=LATE_DAYS,
                 outdated=False):
    """Evaluate one app's store against its saved evaluation state → (detail, summary row). Updates
    state["eval"][app_id] and this app's episodes in place (pure otherwise). late = the provisional days
    (config GA4_LATE_DAYS). outdated = the store is an older format still waiting for its clean re-pull:
    shown (and flagged), but whatever it opens is seeded, never sent."""
    E = _d(store["window_end"])
    late = max(0, int(late or 0))
    S = E - timedelta(days=late)                     # the last settled day
    prev = (state.get("eval") or {}).get(app_id)
    advanced, first = prev is None or E > _d(prev["end"]), prev is None
    cd = cohort_data(store, E)
    ds = daily_series(store, E, cd, late)
    mark_breaks(cd, ds["broken"])
    H = cd["H"]
    curve = headline_curve(cd, late)
    rels = releases(store, ds)
    eps_before = state.get("episodes") or {}
    open_before = [e for e in eps_before.values() if e["app_id"] == app_id]
    cp = checkpoints(cd, curve, H, rels, open_before, prev, advanced)
    rows = [compare(cd, N) for N in cp["list"]]                               # newest: "up" tests, ▲
    settled = [compare(cd, N, late=late) for N in cp["list"]] if late else rows   # settled only: "down", ▼
    claimed = {dr: list(r) for dr, r in ((prev or {}).get("claimed") or {}).items()}
    held = {dr: list(r) for dr, r in ((prev or {}).get("held") or {}).items()}   # claimed only while provisional
    conds = {}
    # up: the newest install days first (earliest signal), then the settled ones (the newest read low until
    # their late data is in, so a moderate rise may show only once settled); down: settled only
    for dr, sets in (("up", ((rows, 0), (settled, late))), ("down", ((settled, late),))):
        for rs, lt in sets[:1] if not late else sets:
            cl = _claimed(cd, claimed.get(dr))
            if lt:                                   # settled: a HELD day (never told) can show its own rise now
                cl -= _claimed(cd, held.get(dr))
            news = new_cohort_rows(cd, rs, dr, cl, "%s|cohort|%s" % (app_id, dr) in eps_before, late)
            c = cohort_conditions(news).get(dr)
            if c:
                c["late"], c["prov"] = lt, dr == "up" and _d(c["installs_to"]) + timedelta(days=c["n"]) > S
                conds[dr] = c
                break
    drift = drift_now(ds)
    streak = dict((prev or {}).get("streak") or {})
    since = dict((prev or {}).get("since") or {})
    holding = {"cohort|up": "up" in conds, "cohort|down": "down" in conds,
               "drift|up": bool(drift and drift["dir"] == "up"), "drift|down": bool(drift and drift["dir"] == "down")}
    if advanced:
        advance_streaks(streak, since, holding, E)
    ready = []
    for dr, c in conds.items():
        hd = c.pop("held")                                                # {N: its held install days}
        need = PERSIST_BIG if c["users"] >= BIG_RECENT_USERS else 1      # big apps: one run can't fire it
        if first or streak.get("cohort|" + dr, 0) >= need:
            ready.append(dict(c, key="%s|cohort|%s" % (app_id, dr)))
            lt = c["late"]
            told = {N: _win(cd, H - N - RECENT_K - lt, H - 1 - N - lt) for N in c["ns"]}
            claimed[dr] = _add_ranges(claimed.get(dr), told.values())    # these install days are told now —
            real = _claimed(cd, [w for N, w in told.items() if N not in hd])      # all but the provisional ones
            keep = (_claimed(cd, held.get(dr)) | {i for f in hd.values() for i in f}) - real   # a row only held:
            held[dr] = _add_ranges([], [_win(cd, i, i) for i in sorted(keep)])   # claimed, not told
    ready += rate_ready(ds, drift, app_id, streak, since, E, first)
    eps = update_episodes(state, app_id, E, ready, advanced, first or outdated, now)
    if outdated:                                     # NOTHING goes out from an older store format — not even an
        for e in eps:                                # episode opened earlier whose send failed (still due)
            if e.get("notified_at") is None:
                e.update(notified_at=now, seeded=True)
    state.setdefault("eval", {})[app_id] = {"end": _iso(E), "stage": cp["stage"], "stable_hold": cp["stable_hold"],
                                            "streak": streak, "since": since,
                                            "claimed": {dr: r for dr, r in sorted(claimed.items()) if r},
                                            "held": {dr: r for dr, r in sorted(held.items()) if r}}
    alerts = sort_alerts([alert_obj(e, app, E) for e in eps])
    closed = [alert_obj(e, app, E) for e in state.get("closed") or [] if e["app_id"] == app_id]
    closed.sort(key=lambda a: (a["closed"], a["opened"], a["id"]), reverse=True)
    lit = {}                                         # checkpoint → (dir, late) of its open cohort alert
    for e in eps:
        if e["family"] == "cohort":
            for N in e["last"].get("ns") or [e["last"].get("n")]:
                lit[N] = (e["dir"], e["last"].get("late") or 0)
    table = []
    for up, dn in zip(rows, settled):
        N = up["n"]
        dr, row = arrow(up, dn, False, lit.get(N))
        prov = row is up and dn is not up
        table.append({"n": N, "key": "D%d" % N,
                      "head": {"p": curve["p"][N], "lo": curve["lo"][N], "hi": curve["hi"][N], "users": curve["users"][N]},
                      "recent": {k: row["recent"][k] for k in ("p", "users", "from", "to")},
                      "prev": _base_out(row["prev"]), "all": _base_out(row["all"]), "prov": prov,
                      "dir": dr, "alert": N in lit, "low_sample": row["low_sample"], "break_day": row["break_day"],
                      "inc_day": row["inc_day"]})
    by_n = {row["n"]: row for row in rows}
    by_s = {row["n"]: row for row in settled}

    def cell(N):
        if N > cp["nmax"]:
            return None
        up = by_n.get(N) or compare(cd, N)
        dn = (by_s.get(N) or compare(cd, N, late=late)) if late else up
        return _head(up, dn, lit.get(N))
    head4 = {"D%d" % N: cell(N) for N in HEAD4}
    counts = {"warning": 0, "watch": 0, "good": 0}
    for a in alerts:
        counts[a["severity"]] = counts.get(a["severity"], 0) + 1
    rn = _rate_now(ds, drift)
    fl = store.get("flags") or {}
    inc = {k: v for k, v in sorted((fl.get("incomplete_days") or {}).items()) if cd["hs"] <= _d(k) <= E}
    detail = {"app_id": app_id, "app": app, "package": package or store.get("package"), "key": key,
              "tz": store.get("time_zone") or "UTC", "den": store.get("den") or "a28",
              "history_start": _iso(cd["hs"]), "data_till": _iso(E), "settled_till": _iso(S), "late_days": late,
              "fetched_at": store.get("fetched_at"),
              "stale": bool(stale), "history_capped": bool(store.get("history_capped")),
              "flags": {"truncated": sorted(fl.get("truncated") or []), "thresholded": bool(fl.get("thresholded")),
                        "unplaced_users": cd["flags"]["unplaced_users"], "over_100": cd["flags"]["over_100"],
                        "kept_old_before": fl.get("kept_old_before"), "incomplete_days": inc,
                        "outdated": bool(outdated)},
              "daily": {"start": _iso(ds["start"]), "new": ds["new"], "un": ds["un"], "a28": ds["den"],
                        "upd": ds["upd"], "rate": ds["rate"], "med": ds["med"], "lo": ds["lo"], "hi": ds["hi"],
                        "breaks": [_iso(ds["start"] + timedelta(days=i)) for i in range(ds["n"]) if ds["broken"][i]]},
              "rate_now": rn, "stage": cp["stage"], "stage_why": cp["why"], "zoom": cp["zoom"],
              "checkpoints": cp["list"], "nmax": cp["nmax"], "curve": curve, "table": table, "head4": head4,
              "lifetime": lifetime(cd, ds), "triangle": triangle(cd, cp["list"]), "releases": rels,
              "lateness": lateness(revision_sums(store)), "alerts": alerts, "alerts_closed": closed}
    summary = {"app_id": app_id, "app": app, "data_till": _iso(E), "stale": bool(stale), "ready": cp["nmax"] >= 0,
               "stage": cp["stage"], "rate7": rn["last7"], "rate_med": rn["med"], "rate_dir": rn["dir"],
               "head4": head4, "alerts": counts}
    return detail, summary


# ── late data: how complete a day is at each age ──────────────────────────────────────────────────

def revision_sums(store, into=None):
    """store["revisions"] ({fetch day: {"un"|"new": {age: [before, after]}}}, fetch.ga4_uninstall) → summed
    per metric and age {"un"|"new": {age: [Σbefore, Σafter, re-reads]}}, added into `into` when given (the
    portfolio pools every app's)."""
    out = into if into is not None else {"un": {}, "new": {}, "fetches": 0}
    for rec in (store.get("revisions") or {}).values():
        out["fetches"] = out.get("fetches", 0) + 1
        for m in ("un", "new"):
            for age, (b, a) in (rec.get(m) or {}).items():
                s = out.setdefault(m, {}).setdefault(str(age), [0, 0, 0])
                s[0], s[1], s[2] = s[0] + int(b), s[1] + int(a), s[2] + 1
    return out


def lateness(sums):
    """How much of a day's final uninstalls (un) / installs (new) GA4 already shows at each age (days from
    the day to the fetch): chained back from the oldest age measured, share[a] = share[a+1] × Σbefore ÷
    Σafter of the re-reads at age a (what arrived between age a and a+1). An age with under LATE_MIN_USERS
    re-read users ends the chain (None from there down). → {"ages", "un", "new", "final_age", "fetches"},
    or None before any re-read."""
    if not sums or not sums.get("fetches"):
        return None
    ages = sorted({int(a) for m in ("un", "new") for a in (sums.get(m) or {})})
    if not ages:
        return None
    top = ages[-1] + 1                           # the oldest age a re-read reached: taken as "final"
    span = list(range(ages[0], top + 1))
    out = {"ages": span, "final_age": top, "fetches": int(sums["fetches"])}
    for m in ("un", "new"):
        got = sums.get(m) or {}
        share, v = [None] * len(span), 1.0
        share[-1] = 1.0
        for j in range(len(span) - 2, -1, -1):
            s = got.get(str(span[j]))
            if not s or s[0] < LATE_MIN_USERS or s[1] <= 0:
                break
            v *= s[0] / s[1]
            share[j] = round(v, 4)
        out[m] = share
    return out


def _base_out(b):
    if not b:
        return None
    return {k: b[k] for k in ("p", "users", "from", "to", "delta_pp", "z", "fires")}


def _raw_lags(store, hs, H):
    """Per install day (index i = c − history_start): n[i] = new installs, raw[i] = {lag: users} for
    lags 0..age — the cells exactly as stored, nothing summed."""
    daily, cells = store.get("daily") or {}, store.get("cohorts") or {}
    n, raw = [], []
    for i in range(H):
        c = (hs + timedelta(days=i)).isoformat()
        age = H - 1 - i
        lags = {}
        for k, u in (cells.get(c) or {}).items():
            lag = int(k)
            if 0 <= lag <= age and u:
                lags[lag] = lags.get(lag, 0) + u
        n.append(int((daily.get(c) or {}).get("new") or 0)), raw.append(lags)
    return n, raw


def cohort_file(store, E=None):
    """The raw per-install-day lags for the "Saare din" triangle (§5d): nothing aggregated, nothing cut."""
    hs, E = _d(store["history_start"]), _d(E or store["window_end"])
    n, raw = _raw_lags(store, hs, max(0, (E - hs).days + 1))
    return {"v": 1, "app_id": store.get("app_id"), "start": _iso(hs), "end": _iso(E), "new": n,
            "lags": [[[lag, u] for lag, u in sorted(r.items())] for r in raw],
            "unplaced": {d: u for d, u in sorted((store.get("unplaced") or {}).items()) if u}}
