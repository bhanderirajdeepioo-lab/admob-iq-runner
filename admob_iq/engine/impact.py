"""Update impact — pure math behind the "📦 Update impact" card of the GA4 Uninstall tab (no I/O, no prints).

For every app update (engine.uninstall.releases: a new appVersion reaching 5% of a day's users, or an app_update surge),
one BLOCK, newest first, with the owner's four must-haves as Before (7 days) | After (7 days) | Change rows, a verdict
(✅ WIN / 👍 CONTINUE / ⚠️ HOLD / 🛑 HALT, or ⏳ Too early) and alerts through the Uninstall tab's episodes:
  1. RETURNING DAU = daily active users − that day's new installs ("purane users ka DAU"), judged against what it would
     have been without the update: the old users' level the same weekday before × their normal weekly change, + the
     recent installs coming back at the PRE-release return rates × the installs that really came (ad spend swings the
     installs — that part is expected, not the update's).
  2. NEW USERS BACK next day (D1) / after 7 days (D7): of the users who installed after the update vs before it (the
     same weekdays), how many were active again on day 1 / day 7 (GA4 cohorts, firstSessionDate) — per 100 of the
     install days' GA4 new users (daily "new", Firebase's "New users" base; Σ returners ÷ Σ new). The cohort's own
     total t only decides whether it is complete; an install day with new unknown or 0 is left out.
  3. SESSIONS / TIME PER USER of the RETURNING users (a new install's first day is different: never mixed in), before vs
     after, judged net of the weekly trend the app was already on — and, on the same days, users on the new version vs
     the older versions ("Same days: new version vs old"), net of the usual early-updater gap (the same comparison after
     the latest earlier updates). When recent installs (ad spend) reshape the returning users (RECENT_SWING), these
     rows are at most "Maybe": the change may be that mix.
  4. AD REVENUE PER ACTIVE USER (ARPDAU) = AdMob revenue ÷ GA4 active users, per 1,000 users, shown before / after.
     Judged on the part an update moves — ads (impressions) per active user (its own trend-net test, minimum, BIG_X);
     the price per ad (eCPM) is the market's: revenue per user moving while ads per user did not = "Market", not
     counted.
  + UNINSTALL ON INSTALL DAY (D0), the uninstall engine's own comparison (_judge_est: sample, minimum, estimate rule).

FAIR: before = the 7 days before the release (every weekday once); after = 7 days from when the new version runs on half
the day's users (at most 3 days after the release: a slower rollout is judged diluted); each after-day is compared with
the SAME WEEKDAY before; a hotfix ≤ CHAIN_DAYS after an update is the same update; the next update cuts the window. Only
SETTLED days are judged (activity ≤ E − ACT_LATE_DAYS: past GA4's 72h late-event cutoff; uninstalls as the tab's
LATE_DAYS); newer days are shown faded (after_prov), never judged. The normal weekly change comes from the 3 weeks
before the before-week (NOISE_LAG: the before-week itself is the baseline). NOISE = how much the SAME week comparison
moved when there was no update to judge: it is redone at every day of the NULL_WEEKS weeks before the release
("pseudo-updates", _null_sd) and its spread is the noise, floored at SIGMA_FLOOR (GA4 user counts are ±1–2% sketches).
Day-level noise ÷ √days is NOT used: the days of a week move together (live returning DAU: the weekly change of one day
and the next correlate 0.87; a 7-day mean varies 4× what 7 independent days would), which read plain noise as |z| ≥ 3
on ~1 date in 4. A row is "worse" / "better" only when significant (|z| ≥ Z_FINAL, Z_EARLY until the week is settled),
at least its minimum effect NET of the normal trend (the effect the z tests), and — before the block is final — the
same on 2 daily evaluations (PERSIST). A normal weekly change steeper than TREND_MAX_WEEK (a launch / growth phase) is
never extrapolated: the row is "Low data" with plain before vs after and no expected level (the headline, the alerts and
the verdict only ever use worse / better rows). GA4's own limits are said, never hidden: user
counts are estimates, consent-denied users are missing, user-level data older than GA4's retention reads short (the
fetch finds that edge: ret_from) — rows it touches say "No data" with the reason, never a guess.

7 / 14 / 30 / 60 DAYS (spec SPEC_WINDOWS; by_window, config IMPACT_WINDOWS): the 7-day block above stays exactly as it
was (every row, verdict and alert). Each block also gets 14 / 30 / 60-day windows: Before = [R−N, R−1], After = [a0,
a0+N−1] (the same a0), NEVER cut by the next update (the updates inside are listed: "Mixed"), each after-day paired with
the same weekday nearest its mirrored position (pair_day). Returning DAU extrapolates the normal weekly change ≤3 weeks;
per-user rows are plain (no trend); every row's noise = the same N-day comparison at pseudo-updates over 8N days (≥3N
of them, widened by t when few are independent; the rate rows use nothing else), read through prefix sums (O(1) a
shift). A long window is judged only once complete (end_a + 10; final with D30 at end_a + 33). The 30-day window's HOLD /
HALT on rows no 7-day verdict or alert already told (this update's or one released inside the window) is the late
family "impact_late": one episode per app, after 2 daily evaluations, seeded on rollout.
"""

import math
from datetime import date, datetime, timedelta, timezone

from ..alerting.rules import fingerprint
from . import attrib
from . import uninstall as U

# ── constants (each with its one-line why) ──
IMPACT_V = 1              # impact data format (a store without it is backfilled; alerts never reset)
ACT_LATE_DAYS = 3         # activity/revenue days ≤ E−3 are ≥5 days old at fetch: past GA4's 72h late-event cutoff
COHORT_DAYS = 30          # returns kept for day 0..30: D1/D7 rows + the recent-install returners the expected DAU needs
WIN_DAYS = 7              # before and after = 7 days: every weekday once
PRE_DAYS = 35             # 5 weeks: 21 week-over-week changes (noise + normal drift) and 28 install days for baselines
ADOPT_AFTER = 0.50        # after window starts once the new version runs on half the day's users (live median: 2 days)
ROLLOUT_WAIT = 3          # …but never waits more than 3 days (IQR upper end); slower rollouts are judged diluted
ADOPT_LOW = 0.30          # mean adoption under 30%: app-level rows too diluted to claim a WIN
CHAIN_DAYS = 3            # a hotfix ≤3 days after a release is the same update (one block, like RELEASE_GAP_DAYS)
IMPACT_MIN_DAYS = 3       # an early verdict needs ≥3 settled after-days (fewer = one weekend)
Z_FINAL = 3.0             # = uninstall Z_MIN: ~1 in 370 by chance per row
Z_EARLY = 4.0             # fewer than 7 settled days, re-judged daily: stricter until the week is complete
DAU_MIN_REL = 0.03        # returning DAU: 3% (live week-over-week noise of established apps 1–5%)
RET_MIN_PP = 1.5          # D1/D7: ≥1.5 points AND …
RET_MIN_REL = 0.05        # … ≥5% of before (live D1 ~25–45%, D7 ~10–25%)
USE_MIN_REL = 0.05        # sessions / time per user: 5%
ARPDAU_MIN_REL = 0.05     # ad revenue per user: 5% — judged on ads (impressions) per user, the part an update moves …
IMP_MIN_REL = 0.025       # …revenue per user moving for sure with ads per user under 2.5% = the market's eCPM (not counted)
VER_MIN_REL = 0.05        # new vs old version: 5% beyond the usual early-updater gap
BIG_X = 2.0               # HALT: a primary row at ≥2× its minimum effect
PERSIST = 2               # a non-final worse/better row must hold on 2 daily evaluations (E advanced)
MIN_DAU = 200             # mean returning DAU under 200: Low data (HLL noise on small counts)
MIN_INSTALLS = 300        # D1/D7 sample (= uninstall MIN_RECENT_USERS …
MIN_EVENTS = 10           # … / MIN_EVENTS)
VER_MIN_USERS = 100       # returning users per side per day for the version table
INSTALL_SWING = 0.5       # installs ±50% between windows: D1/D7 may be campaign mix → secondary only
NEWSHARE_SWING = 0.05     # new-user share of DAU moved >5 points: ARPDAU secondary only
SIGMA_FLOOR = 0.01        # HLL user counts are ±1%: no day-level noise below it
NOISE_LAG = 7             # the weekly-change / noise reference ends a week before the release: the before-week is the
                          # contrast's own baseline — shared, it makes plain noise read as z ~1.2× (≈1% false rows at z 3)
NULL_WEEKS = 8            # the week comparison's own noise: redone at every day of the 8 weeks before the release
NULL_MIN = 21             # ≥3 weeks of such pseudo-updates to measure it (fewer: Low data — never the day-level guess)
TREND_MAX_WEEK = 0.3      # the largest believable normal weekly change (log: ≈ ×1.35 a week). On live data (established
                          # = ≥200 days after launch, ≥200 returning users a day) it is above ~99% of the RETURNING DAU
                          # trends — at the releases and on every day (raw mode: no return cohorts read yet; cohort mode
                          # trends an old-users-only series — re-measure once cohorts land) — and above ~99% of the
                          # established releases' ads per user trends too. On every day ads per user passes it a few %
                          # of the time (most of it one app, whose ARPDAU will often be Low data) and revenue per user
                          # (eCPM, the market's) far more often — so a steep revenue trend alone never makes Low data:
                          # ads per user decides.
                          # A launch / growth phase goes far past it; extrapolated it makes no "expected" level: the row
                          # is Low data, plain before vs after. The pseudo-updates (noise) skip days past it too — the
                          # test would not have run there (too few left for that reason: LOW_NULL_TREND)
RECENT_SWING = 0.05       # recent installs' returners moved >5 points of the returning users (ad spend): the per-user
                          # rows and the version table may be the users' mix → at most Maybe (installs_swing)
BIAS_MIN = 3              # early-updater gap from the 3–6 …
BIAS_MAX = 6              # … latest earlier version updates
VUSE_MIN_SHARE = 0.01     # (fetch) a version under 1% of the day's users is pooled into "_rest"
COH_BATCH = 14            # (fetch) cohorts per cohort request
COH_MIN_USERS = 200       # (fetch) a smaller cohort is judged pooled with the batch's other small ones
COH_MIN_COVERAGE = 0.90   # (fetch) a cohort holding < 90% of its installs (× the app's scale) reads short
COH_EDGE_RUN = 2          # (fetch) 2 short batches in a row = GA4's user-data edge
COH_MAX_CALLS = 60        # (fetch) cohort requests per fetch at most
IMPACT_ALERT_DAYS = 35    # only updates of the last 5 weeks alert (final ≈ R+20); older = info
IMPACT_LIST_DAYS = 60     # All apps "Recent updates"
IMPACT_SHOW = 5           # newest 5 blocks listed; older folded, never dropped
# ── the 14 / 30 / 60-day windows (spec SPEC_WINDOWS; the 7-day block above stays exactly as it was) ──
WINDOWS = (7, 14, 30, 60)      # owner: 7 / 14 / 30 / 60 days; 7 = today's early verdict + alerts
LONG_MIN = 14                  # windows ≥14: never cut by the next update, judged only complete, noise required
TREND_HORIZON_WEEKS = 3        # DAU: the normal weekly change extrapolated ≤3 weeks (lowest 30/60-day noise; =today at 7/14)
PU_TREND_MAX_N = 7             # per-user rows: net of the trend at 7 only; 14/30/60 plain (lower noise at each)
NULL_SPAN_X = 8                # pseudo-updates over 8×N days (=56 at 7: NULL_WEEKS)
NULL_MIN_X = 3                 # ≥3×N of them (=21 at 7: NULL_MIN) — ~3 independent N-day stretches
NULL_DF_FULL = 8               # N≥14: spread widened by T975[df]/T975[8], df = valid // N, below 8
JUDGE_D = 7                    # a long window is judged once D7 of its last install day is settled (end_a+10)
RET30_MIN_PP = 1.0             # D30 (base ~5%): ≥1 point AND …
RET30_MIN_REL = 0.10           # … ≥10% of before
LATE_WINDOW = 30               # the late-effect check's window
LATE_ALERT_DAYS = 75           # judged ≈R+41, D30 ≈R+64, +persistence: older updates never raise a late alert
LATE_PERSIST = 2               # a late condition holds on 2 daily evaluations before it is sent
LATE_V = 1                     # state marker: the first evaluation without it seeds every late condition

CONSTS = {k.lower(): v for k, v in dict(
    IMPACT_V=IMPACT_V, ACT_LATE_DAYS=ACT_LATE_DAYS, COHORT_DAYS=COHORT_DAYS, WIN_DAYS=WIN_DAYS, PRE_DAYS=PRE_DAYS,
    ADOPT_AFTER=ADOPT_AFTER, ROLLOUT_WAIT=ROLLOUT_WAIT, ADOPT_LOW=ADOPT_LOW, CHAIN_DAYS=CHAIN_DAYS,
    IMPACT_MIN_DAYS=IMPACT_MIN_DAYS, Z_FINAL=Z_FINAL, Z_EARLY=Z_EARLY, DAU_MIN_REL=DAU_MIN_REL, RET_MIN_PP=RET_MIN_PP,
    RET_MIN_REL=RET_MIN_REL, USE_MIN_REL=USE_MIN_REL, ARPDAU_MIN_REL=ARPDAU_MIN_REL, IMP_MIN_REL=IMP_MIN_REL,
    VER_MIN_REL=VER_MIN_REL, BIG_X=BIG_X, PERSIST=PERSIST, MIN_DAU=MIN_DAU, MIN_INSTALLS=MIN_INSTALLS,
    MIN_EVENTS=MIN_EVENTS, VER_MIN_USERS=VER_MIN_USERS, INSTALL_SWING=INSTALL_SWING, NEWSHARE_SWING=NEWSHARE_SWING,
    SIGMA_FLOOR=SIGMA_FLOOR, NOISE_LAG=NOISE_LAG, NULL_WEEKS=NULL_WEEKS, NULL_MIN=NULL_MIN, TREND_MAX_WEEK=TREND_MAX_WEEK,
    RECENT_SWING=RECENT_SWING,
    BIAS_MIN=BIAS_MIN, BIAS_MAX=BIAS_MAX, VUSE_MIN_SHARE=VUSE_MIN_SHARE, COH_BATCH=COH_BATCH,
    COH_MIN_USERS=COH_MIN_USERS, COH_MIN_COVERAGE=COH_MIN_COVERAGE, COH_EDGE_RUN=COH_EDGE_RUN,
    COH_MAX_CALLS=COH_MAX_CALLS, IMPACT_ALERT_DAYS=IMPACT_ALERT_DAYS, IMPACT_LIST_DAYS=IMPACT_LIST_DAYS,
    IMPACT_SHOW=IMPACT_SHOW, WINDOWS=list(WINDOWS), LONG_MIN=LONG_MIN, JUDGE_D=JUDGE_D,
    TREND_HORIZON_WEEKS=TREND_HORIZON_WEEKS, PU_TREND_MAX_N=PU_TREND_MAX_N, NULL_SPAN_X=NULL_SPAN_X,
    NULL_MIN_X=NULL_MIN_X, NULL_DF_FULL=NULL_DF_FULL, RET30_MIN_PP=RET30_MIN_PP, RET30_MIN_REL=RET30_MIN_REL,
    LATE_WINDOW=LATE_WINDOW, LATE_ALERT_DAYS=LATE_ALERT_DAYS, LATE_PERSIST=LATE_PERSIST, LATE_V=LATE_V).items()}

ROWS = ("returning_dau", "new_d1", "new_d7", "sessions", "time", "arpdau", "uninstall_d0")
ROWS_LONG = ROWS + ("new_d30",)              # the 30 / 60-day windows add D30 (secondary, its own group)
VROWS = ("ver_sessions", "ver_time")
PRIMARY = ("returning_dau", "new_d1", "arpdau", "uninstall_d0")
GROUPS = (("usage", ("sessions", "time")), ("d7", ("new_d7",)), ("version", ("ver_sessions", "ver_time")),
          ("d30", ("new_d30",)))
APP_LEVEL = set(ROWS_LONG)                  # the version table is not diluted by adoption: the rest is
LEVEL_RANK = {"continue": 0, "win": 0, "hold": 1, "halt": 2}
SEVERITY = {"halt": "warning", "hold": "watch", "win": "good"}
ACT = {"halt": "🛑 Stop update — staged rollout rok do, hotfix bhejo",
       "hold": "⚠️ Wait and check — agla rollout roko, jaanch karo",
       "win": "✅ Update went well — isi disha me aage badho"}
UNIT = {"returning_dau": "users", "new_d1": "pct", "new_d7": "pct", "sessions": "num", "time": "sec",
        "arpdau": "usd1k", "uninstall_d0": "pct", "new_d30": "pct"}
EXTRA = {"returning_dau": ("raw_change", "mode", "k_days", "imputed_share", "mu_week", "expected_model"),
         "new_d1": ("installs_before", "installs_after", "swing", "cohorts_before", "cohorts_after", "phi"),
         "sessions": ("all_before", "all_after", "adj_change"),
         "arpdau": ("imp_change", "imp_adj", "ecpm_change", "newshare_before", "newshare_after", "tz_blend", "currency",
                    "imp_before", "imp_after", "imp_expected"),
         "uninstall_d0": ("read", "phi", "est")}
EXTRA["new_d7"], EXTRA["time"], EXTRA["new_d30"] = EXTRA["new_d1"], EXTRA["sessions"], EXTRA["new_d1"]
BASIS = ("expected", "plain", "rate")        # what a row is judged on (the page's "Actual / Expected" rule, §2.8)
DP = {"users": 0, "pct": 5, "num": 3, "sec": 1, "usd1k": 4}
STATUSES = ("worse", "better", "same", "unsure", "low", "pending", "na", "market")
JUDGED = ("worse", "better", "same", "unsure", "market")     # a status from the row's own test (the rest: not measured)
NOTES = ("installs_swing", "newshare_swing", "diluted", "slow_rollout", "no_cohorts", "no_revenue", "tz_blend",
         "before_overlap", "cut_by_next", "prov", "est", "thresholded")
NOTES_LONG = NOTES + ("mixed", "mixed_before", "trend_capped", "plain", "young")   # + the 14 / 30 / 60-day ones
STATES = ("running", "judged", "final")      # a 14 / 30 / 60-day window: not complete / judged (D30 may wait) / final

NA_YOUNG = "App launch ke turant baad ka update — pehle ka hafta nahi"
NA_CUT = "Agla update bahut jaldi aa gaya"
NA_OLD = "GA4 ab itna purana user data nahi rakhta"
NA_NOT_YET = "GA4 se ye data abhi aana baaki hai — agle fetch me"
NA_NO_NEW = "GA4 me in install dino ke naye users ki ginti nahi — kitne % wapas aaye, ye nahi nikal sakta"
NA_NO_USAGE = "GA4 usage data abhi aana baaki hai — agle fetch me"
NA_NO_REV = "AdMob revenue nahi mila"
NA_NO_VER = "Is update ka version number nahi"
WAIT_PERSIST = "pakka hone ke liye kal ka data bhi"
RAW_WHY = ("Naye users ke wapas aane ka data nahi — seedha pichhle hafte se tulna (minimum 2×); installs ke badlaav ka "
           "asar alag nahi ho sakta, isliye sirf andaza")
TREND_WHY = "Update se pehle %s tez %s raha tha (~%s/hafta) — normal trend pakka nahi, isliye sirf pehle vs baad"
# RAW_WORST: without return cohorts the returning DAU is never "worse" / "better" — on the 28 live stores (no cohorts
# read yet) 79 of 234 week-on-week DAU rows came out worse / better, 58 of them moving WITH the install volume (median
# ±26–46% installs): ad spend, not the update


def _d(s):
    return U._d(s)


def _steep(mu):
    """A normal weekly change (log) too steep to extrapolate (TREND_MAX_WEEK)."""
    return mu is not None and abs(mu) > TREND_MAX_WEEK


def trend_why(mu, what):
    """The Low data reason of a row whose normal weekly change is too steep: a rise as a factor ("…tez badh raha tha
    (~×2.6/hafta)…"), a fall as a percentage ("…tez ghat raha tha (~−30%/hafta)…" — never "×0.70")."""
    f = math.exp(mu)
    if mu > 0:
        x = "×%d" % round(f) if f >= 10 else "×%.1f" % f
    else:
        x = U._minus("-%d%%" % min(99, round((1 - f) * 100)))
    return TREND_WHY % (what, "badh" if mu > 0 else "ghat", x)


def _iso(d):
    return d.isoformat() if d else None


def _days(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)] if a <= b else []


def _mean(v):
    return sum(v) / len(v) if v else None


def _log(a, b):
    return math.log(a / b) if a and b and a > 0 and b > 0 else None


def _vlabel(v):
    v = str(v)
    return v if v[:1] in ("v", "V") else "v" + v


def rel_key(r):
    """One release → its key: "ver:<version>@<date>" or "upd@<date>" (the page's uniRelKey: the same rule)."""
    return "ver:%s@%s" % (r["version"], r["date"]) if r.get("version") else "upd@%s" % r["date"]


def _bday(R, d):
    """The before-day with d's weekday (in the week before the release R) and the weeks between them."""
    b = R - timedelta(days=7) + timedelta(days=(d - (R - timedelta(days=7))).days % 7)
    return b, (d - b).days // 7


# ── the data an app's store holds ────────────────────────────────────────────────────────────────

def _revenue_fn(revenue, tz_g):
    """AdMob revenue {tz, currency, till, days: {AdMob day: [earnings micros, impressions]}} → fn(GA4 day) → (revenue
    in the report currency, impressions) or None, and tz_blend. A GA4 day (in the store's timezone) takes each AdMob day
    (in the revenue's timezone) by the share of it that falls inside the GA4 day — DST-aware (zoneinfo); one timezone =
    exactly its own day. A GA4 day needs every AdMob day it overlaps ≤ `till`; inside the app's revenue span a day
    without a row earned 0, outside it None (unknown)."""
    from zoneinfo import ZoneInfo
    days = {k: v for k, v in ((revenue or {}).get("days") or {}).items() if v is not None}
    if not days:
        return None, False
    try:
        zr = ZoneInfo(revenue.get("tz") or "UTC")
    except Exception:
        zr = ZoneInfo("UTC")
    try:
        zg = ZoneInfo(tz_g or "UTC")
    except Exception:
        zg = ZoneInfo("UTC")
    first, till = _d(min(days)), _d(revenue.get("till") or max(days))
    same = zr.key == zg.key
    memo = {}

    def val(e):
        if e < first or e > till:
            return None
        v = days.get(e.isoformat())
        return (0.0, 0.0) if v is None else (float(v[0] or 0) / 1e6, float(v[1] or 0))

    def start(day, z):
        return datetime(day.year, day.month, day.day, tzinfo=z).astimezone(timezone.utc)

    def f(d):
        if d in memo:
            return memo[d]
        if same:
            memo[d] = val(d)
            return memo[d]
        s, t = start(d, zg), start(d + timedelta(days=1), zg)
        rev = imp = 0.0
        out = (0.0, 0.0)
        for j in range(-2, 3):
            e = d + timedelta(days=j)
            es, et = start(e, zr), start(e + timedelta(days=1), zr)
            ov = (min(t, et) - max(s, es)).total_seconds()
            if ov <= 0:
                continue
            v = val(e)
            if v is None:
                out = None
                break
            share = ov / (et - es).total_seconds()
            rev, imp = rev + v[0] * share, imp + v[1] * share
        memo[d] = None if out is None else (rev, imp)
        return memo[d]
    return f, not same


def revenue_share(tz_ga4, tz_admob, admob_day):
    """{GA4 day: share} of one AdMob day spread over the GA4 days it overlaps (the weights _revenue_fn uses; they add
    up to 1 — a DST day too)."""
    one = {"tz": tz_admob, "till": (admob_day + timedelta(days=3)).isoformat(),
           "days": {(admob_day + timedelta(days=j)).isoformat(): [1e6 if j == 0 else 0, 0] for j in range(-3, 4)}}
    f, _ = _revenue_fn(one, tz_ga4)
    out = {}
    for j in range(-2, 3):
        d = admob_day + timedelta(days=j)
        v = f(d)
        if v and v[0] > 0:
            out[d] = v[0]
    return out


def _context(store, cd, whole, i0, revenue, E, late):
    daily = store.get("daily") or {}
    fi = (store.get("flags") or {}).get("impact") or {}
    rev, blend = _revenue_fn(revenue, store.get("time_zone") or "UTC") if revenue else (None, False)
    usage = store.get("usage") or {}
    cx = {"E": E, "S_act": E - timedelta(days=ACT_LATE_DAYS), "S_un": E - timedelta(days=late), "late": late,
          "daily": daily, "usage": usage, "vuse": store.get("vuse") or {}, "ret": store.get("ret") or {},
          "vers": store.get("versions") or {}, "cd": cd,
          "ret_from": _d(store["ret_from"]) if store.get("ret_from") else None,
          "split": fi.get("vuse_split") is not False,
          "has_data": int(store.get("impact_v") or 0) >= IMPACT_V,
          "launch": whole["hs"] + timedelta(days=i0), "rev": rev, "tz_blend": blend,
          "currency": (revenue or {}).get("currency") or "USD",
          "thresholded": bool(fi.get("thresholded")) or bool((store.get("flags") or {}).get("thresholded")),
          "usage_from": min(usage) if usage else None}
    lo = [min(x) for x in (daily, cx["ret"], usage) if x]            # the prefix sums' day span (ordinals)
    cx["_span"] = (min(_d(x) for x in lo).toordinal() if lo else E.toordinal(), E.toordinal())
    rdays = [k for k, v in ((revenue or {}).get("days") or {}).items() if v is not None]
    # each series' first day (a 14 / 30 / 60-day row's history = the release − max(launch, its series' first day))
    cx["first"] = {"daily": _d(min(daily)) if daily else None, "usage": _d(min(usage)) if usage else None,
                   "ret": _d(min(cx["ret"])) if cx["ret"] else None, "rev": _d(min(rdays)) if rdays else None,
                   "d0": cd["hs"] if cd and cd.get("hs") else None}
    first5 = {}                                   # each version's first day on ≥ RELEASE_SHARE of the day's users
    for k in sorted(cx["vers"]):
        vs = cx["vers"][k] or {}
        tot = int((daily.get(k) or {}).get("a1") or 0) or sum(vs.values())
        for v, u in vs.items():
            if v not in first5 and tot and u / tot >= U.RELEASE_SHARE:
                first5[v] = _d(k)
    cx["first5"] = first5
    return cx


def _dv(cx, d, k):
    dd = cx.get("_dd")
    if dd is None:                                # {date: {a1, new}} — the rows re-read the same days many times
        dd = cx["_dd"] = {_d(k_): {"a1": int(r.get("a1") or 0), "new": int(r.get("new") or 0)}
                          for k_, r in cx["daily"].items() if r is not None}
    r = dd.get(d)
    return None if r is None else r[k]


def _ret_dau(cx, d):
    """Returning DAU of day d = active users − new installs (None: no data that day)."""
    a, n = _dv(cx, d, "a1"), _dv(cx, d, "new")
    return None if a is None else a - n


# ── blocks and their windows ─────────────────────────────────────────────────────────────────────

def make_blocks(rels, launch):
    """Releases (oldest first) → blocks: consecutive releases ≤ CHAIN_DAYS apart are ONE update (a hotfix chain);
    releases before the launch day (test builds) are left out."""
    out = []
    for r in rels:
        d = _d(r["date"])
        if d < launch:
            continue
        if out and (d - out[-1]["_last"]).days <= CHAIN_DAYS:
            out[-1]["rels"].append(r)
            out[-1]["_last"] = d
        else:
            out.append({"rels": [r], "R": d, "_last": d})
    for b in out:
        vers = []
        for r in b["rels"]:
            if r.get("version") and r["version"] not in vers:
                vers.append(r["version"])
        b["versions"], b["kind"] = vers, "version" if vers else "update"
        b["label"] = ("App update" if not vers else _vlabel(vers[0]) if len(vers) == 1
                      else "%s → %s" % (_vlabel(vers[0]), _vlabel(vers[-1])))
        b["key"], b["rel_keys"] = rel_key(b["rels"][0]), [rel_key(r) for r in b["rels"]]
    return out


def _adoption(cx, b):
    """Share of each day's active users on the block's versions, R−1 .. min(E, R+21) → {day: share}."""
    out = {}
    if b["kind"] != "version":
        return out
    for d in _days(b["R"] - timedelta(days=1), min(cx["E"], b["R"] + timedelta(days=21))):
        vs = cx["vers"].get(d.isoformat()) or {}
        tot = _dv(cx, d, "a1") or sum(vs.values())
        if tot:                                   # (user counts are sketches: a share never reads over 100%)
            out[d] = min(1.0, sum(vs.get(v, 0) for v in b["versions"]) / tot)
    return out


def _adopt_newer(cx, b, days):
    """Mean share of each day's active users on the block's versions OR any version first ≥5% of a day's users on or
    after the release ("this update or newer": a later release is not dilution) over `days` → float or None."""
    R, keep = b["R"], set(b["versions"])
    keep |= {v for v, d in cx["first5"].items() if d >= R}
    out = []
    for d in days:
        vs = cx["vers"].get(d.isoformat()) or {}
        tot = _dv(cx, d, "a1") or sum(vs.values())
        if tot:
            out.append(min(1.0, sum(u for v, u in vs.items() if v in keep) / tot))
    return _mean(out)


def _rel_ref(x):
    return {"key": x["key"], "label": x["label"], "date": _iso(x["R"])}


def windows(cx, b, blocks, j, N=WIN_DAYS):
    """The block's windows (see the module docstring). N = 7: today's (the next update cuts the after-week) → b["win"]
    (and b["A"]). N ≥ LONG_MIN: PURE (nothing written to b — the 7-day win is read again later): Before = [R−N, R−1],
    After = [a0, a0+N−1] never cut; the later updates inside After are listed (mixed), the earlier ones inside Before too
    (mixed_before); adoption = "this update or newer" over the After days so far."""
    R, E = b["R"], cx["E"]
    prev_b = blocks[j - 1] if j else None
    next_b = blocks[j + 1] if j + 1 < len(blocks) else None
    A = b["A"] if N != WIN_DAYS and "A" in b else _adoption(cx, b)
    if b["kind"] == "version":
        hit = next((d for d in sorted(A) if d >= R and A[d] >= ADOPT_AFTER), None)
        a0 = max(R + timedelta(days=1), min(hit or R + timedelta(days=ROLLOUT_WAIT), R + timedelta(days=ROLLOUT_WAIT)))
        slow = a0 <= E and (A.get(a0) or 0.0) < ADOPT_AFTER
    else:
        a0, slow = R + timedelta(days=1), False
    if N != WIN_DAYS:
        end_a = a0 + timedelta(days=N - 1)
        days_a = _days(a0, end_a)
        avail = [d for d in days_a if d <= E]
        return {"n": N, "a0": a0, "end_a": end_a, "days_a": days_a, "settled": [d for d in days_a if d <= cx["S_act"]],
                "avail": avail, "slow": slow, "cut_by": None, "b0": R - timedelta(days=N), "b1": R - timedelta(days=1),
                "overlap": None,
                "adopt_mean": _adopt_newer(cx, b, avail) if b["kind"] == "version" else None,
                "mixed": [_rel_ref(x) for x in blocks[j + 1:] if x["R"] <= end_a],
                "mixed_before": [_rel_ref(x) for x in blocks[:j] if R - timedelta(days=N) <= x["R"] <= R - timedelta(days=1)]}
    end_a, cut_by = a0 + timedelta(days=WIN_DAYS - 1), None
    if next_b is not None and next_b["R"] - timedelta(days=1) < end_a:
        end_a, cut_by = next_b["R"] - timedelta(days=1), {"label": next_b["label"], "date": _iso(next_b["R"])}
    days_a = _days(a0, end_a)
    settled = [d for d in days_a if d <= cx["S_act"]]
    avail = [d for d in days_a if d <= E]
    over = prev_b if prev_b is not None and R - timedelta(days=7) <= prev_b["R"] <= R - timedelta(days=1) else None
    shown = [A[d] for d in avail if d in A]
    b["A"] = A
    b["win"] = {"n": WIN_DAYS, "a0": a0, "end_a": end_a, "days_a": days_a, "settled": settled, "avail": avail,
                "slow": slow, "cut_by": cut_by, "b0": R - timedelta(days=7), "b1": R - timedelta(days=1),
                "overlap": over, "adopt_mean": _mean(shown) if b["kind"] == "version" else None}
    return b["win"]


def pair_day(win, R, d):
    """After-day d → (its before-day, the weeks between): the day of d's weekday inside [R−N, R−1] nearest to d's
    position mirrored into it (R−N + (d − a0)) — unique (±k offsets never share a weekday). At N = 7: _bday."""
    N = win.get("n", WIN_DAYS)
    lo, hi = R - timedelta(days=N), R - timedelta(days=1)
    t = lo + (d - win["a0"])
    r = (d - t).days % 7                             # t + r and t + r − 7 are the two candidates of d's weekday
    near, far = (r, r - 7) if r <= 3 else (r - 7, r)
    b = t + timedelta(days=near)
    if not lo <= b <= hi:
        b = t + timedelta(days=far)
        if not lo <= b <= hi:                        # (a window shorter than a week: never here)
            return _bday(R, d)
    return b, (d - b).days // 7


# ── rows ─────────────────────────────────────────────────────────────────────────────────────────

def _row(key):
    return {"before": None, "after": None, "expected": None, "after_prov": None, "change": None,
            "change_unit": "pp" if UNIT[key] == "pct" else "rel", "unit": UNIT[key], "z": None, "status": "na",
            "raw_status": "na", "streak": 0, "prov": False, "est": False, "n_before": 0, "n_after": 0,
            "from_b": None, "to_b": None, "from_a": None, "to_a": None, "reason": None, "ready_on": None,
            "extra": dict.fromkeys(EXTRA[key]), "basis": "rate" if UNIT[key] == "pct" else "expected",
            "noise": None, "need": None}


def _vrow():
    return {"old": None, "new": None, "diff": None, "adj": None, "bias": None, "z": None, "status": "na",
            "raw_status": "na", "streak": 0, "n_days": 0, "reason": None, "prov": False}


def _na(row, reason):
    row.update(status="na", raw_status="na", reason=reason)
    return row


def _judge(eff, mn, z, Z, sample=True):
    """A row's raw status from its effect (signed, in its own unit), minimum `mn`, significance z / Z → worse / better /
    unsure / same / low. Up = better for every row except the install-day uninstall (its caller flips the sign)."""
    if not sample:
        return "low"
    if eff is None:
        return "low"
    if abs(eff) >= mn and z is not None and abs(z) >= Z and (z > 0) == (eff > 0):
        return "better" if eff > 0 else "worse"
    return "unsure" if abs(eff) >= mn else "same"


def _zlevel(win):
    if win.get("n", WIN_DAYS) >= LONG_MIN:           # a long window is judged only once complete
        return Z_FINAL
    return Z_FINAL if win["settled"] and len(win["settled"]) == len(win["days_a"]) else Z_EARLY


def _long(win):
    return win.get("n", WIN_DAYS) >= LONG_MIN


def _need_rel(eff, noise, Z, mn):
    """The signed relative change a rel row would need to be worse / better (in its judged change's direction; down
    when 0): beyond Z × its noise (log) and its minimum."""
    if noise is None:
        return None
    if eff is not None and eff > 0:
        return max(math.exp(Z * noise) - 1, mn)
    return -max(1 - math.exp(-Z * noise), mn)


def _need_pp(eff, noise, Z, mn_pp, mn_rel_pp):
    """The signed change in points a pp row would need: beyond Z × its noise, its pp minimum and its rel minimum (in
    points)."""
    if noise is None:
        return None
    m = max(Z * noise, mn_pp, mn_rel_pp or 0.0)
    return m if eff is not None and eff > 0 else -m


def _pending(row, win, ready):
    row.update(status="pending", raw_status="pending", ready_on=_iso(ready))
    return row


def _span(row, a, b):
    if a:
        row["from_a"], row["to_a"] = _iso(min(a)), _iso(max(a))
    if b:
        row["from_b"], row["to_b"] = _iso(min(b)), _iso(max(b))


def _new_of(cx, c):
    """The install day's GA4 new users (the return rates' base) → int > 0, or None (unknown or 0: no rate)."""
    n = _dv(cx, c, "new")
    return n if n else None


def _rho(cx, R):
    """Pre-release return rates ρ̂_k = Σ day-k actives ÷ Σ the install days' GA4 new users over the complete cohorts
    [R−28−k, R−1−k] (new > 0), and K = the last day k (≤ COHORT_DAYS) that ≥14 such cohorts reach, every day before it
    too."""
    ret, rho, K = cx["ret"], {}, 0
    for k in range(1, COHORT_DAYS + 1):
        x = u = n = 0
        for j in range(28):
            c = R - timedelta(days=28 + k - j)
            e, nw = ret.get(c.isoformat()), _new_of(cx, c)
            if e and e.get("ok") and len(e.get("a") or []) > k and e.get("t") and nw:
                x, u, n = x + e["a"][k], u + nw, n + 1
        if n < 14 or not u:
            break
        rho[k], K = x / u, k
    return rho, K


def _null_sd(vals, N=WIN_DAYS):
    """The window comparison's own noise from its pseudo-updates: their spread around 0 (a model bias counts as noise
    too), floored at SIGMA_FLOOR. N ≥ LONG_MIN: widened by T975[df] / T975[NULL_DF_FULL], df = len // N (below it):
    pseudo-updates one day apart overlap by N−1 days, so 180 of them at 60 days hold only ~3 independent stretches."""
    s = max(U.spread(vals, 0.0), SIGMA_FLOOR)
    if N >= LONG_MIN:
        df = min(NULL_DF_FULL, len(vals) // N)
        if df < NULL_DF_FULL:
            s *= T975.get(df, T975[1]) / T975[NULL_DF_FULL]
    return s


def _shifts(R, days, N=WIN_DAYS):
    """The pseudo-update shifts Δ for after-days `days`: every shifted after-day before the release, NULL_SPAN_X × N of
    them (56 at 7: NULL_WEEKS weeks), one per day (each keeps its own same-weekday matching, so any Δ is a fair copy)."""
    lo = max((d - R).days for d in days) + 1
    return range(max(lo, 1), max(lo, 1) + (7 * NULL_WEEKS if N == WIN_DAYS else NULL_SPAN_X * N))


def _null_min(N):
    return NULL_MIN if N == WIN_DAYS else NULL_MIN_X * N


def _hist_need(N):
    """Days of history before the release the N-day noise needs (≥ NULL_MIN_X·N pseudo-updates, each reading ~5 weeks
    further back): 5N + 31."""
    return 5 * N + 31


# ≥ NULL_MIN pseudo-updates need ~10 weeks before the release: the first starts ≤10 days back, each looks 5 weeks further
LOW_NULL = "Update se pehle ka ~%d hafte ka data chahiye (aam utaar-chadhaav napne ke liye)" % math.ceil((10 + NULL_MIN + 35) / 7)
# …the data is there, but enough of those pseudo-updates sat in a launch / growth stretch (TREND_MAX_WEEK): said so
LOW_NULL_TREND = ("Update se pehle ke hafton me %s tez badh / ghat raha tha (launch ya tez growth) — aam utaar-chadhaav "
                  "napne layak normal hafte kam")
# the 14 / 30 / 60-day noise needs 5N+31 days before the release (15 / 26 / 48 weeks; D30 ~30 more): the app's age,
# said with it — ONLY when the row's series really is that short (else LOW_NULL_GAP: the history is there, its days not)
LOW_NULL_N = ("Update se pehle ka ~%d hafte%s ka data chahiye (%d-din tulna ka aam utaar-chadhaav napne ke liye) — is "
              "update se pehle ~%d hafte ka tha")
LOW_NULL_GAP = ("Update se pehle ke GA4 data me kai dino ki kami (ya un dino installs nahi) — %d-din tulna ka aam "
                "utaar-chadhaav napne layak din kam")
# the normal weekly change / its backtest read N days before the before-window at 14 / 30 / 60: short there (the app
# older than that): that stretch named — never "the weeks before the update", which the app had
LOW_REF_N = "Update se ~%d din pehle ke %d hafte ka data kam (normal trend napne ke liye)"
LOW_AB_N = "Before / After ke dino ka data kam"
NA_YOUNG_N = "Update app launch ke %d din ke andar aaya — pehle ke poore %d din nahi"
LOW_RATE = "Naye users kam — kam se kam %d installs aur %d wapas aane wale chahiye"
SERIES = {"dau": ("daily",), "sessions": ("usage",), "time": ("usage",), "rev": ("daily", "rev"), "imp": ("daily", "rev"),
          "rate": ("ret",), "d0": ("d0",)}


def _hist_from(cx, series):
    """The first day a row's pseudo-updates can read: max(launch, its series' first day(s)) — the return cohorts also
    not before GA4's user-data edge (ret_from)."""
    days = [cx.get("launch")] + [(cx.get("first") or {}).get(s) for s in SERIES.get(series, ())]
    if series == "rate":
        days.append(cx.get("ret_from"))
    days = [d for d in days if d is not None]
    return max(days) if days else None


def _avail(cx, R, series=None):
    """Days of the row's series before the release R (the history its noise can read)."""
    f = _hist_from(cx, series)
    return max(0, (R - f).days) if f is not None else 0


def _need_rate(win, R, k):
    """Days before R a rate row (return day k; 0 = install-day uninstall) reads for ≥ NULL_MIN_X·N pseudo-updates: the
    shifts start past its last after-day (+ k), each reads its before-install days N (+ k) further back."""
    N = win["n"]
    return (win["end_a"] - R).days + NULL_MIN_X * N + N + 2 * k


def low_null_n(cx, R, N, need=None, series=None):
    """LOW_NULL_N for window N at release R: the weeks needed (the window's 5N+31, or the row's own need when longer —
    D30) + the months at 60, and the weeks its series had (from max(launch, the series' first day))."""
    days = max(_hist_need(N), need or 0)
    weeks = math.ceil(days / 7)
    had = _avail(cx, R, series) // 7
    return LOW_NULL_N % (weeks, " (~%d mahine)" % round(days / 30.44) if N >= 60 else "", N, had)


def _hist_short(cx, R, N, need=None, series=None):
    """The row's series is shorter than its N-day noise needs (`need` days; default 5N+31) — the app's age, not gaps."""
    return _avail(cx, R, series) < (need if need else _hist_need(N))


def is_hist(reason):
    """A LOW_NULL_N reason (the app's history too short for the window's noise: the card's "young" line says it once)."""
    return bool(reason) and reason.startswith("Update se pehle ka ~") and reason.endswith(" hafte ka tha")


def _low_null(cx, R, N, nulls, steep_n, what, need=None, series=None):
    """Why a row has too few pseudo-updates: the steep weeks (LOW_NULL_TREND), else at 7 the history (LOW_NULL — byte
    for byte today's); at 14 / 30 / 60 the history (LOW_NULL_N) only when the row's series is shorter than its noise
    needs (`need`: its days, default 5N+31) — else the days are there but too many unreadable (LOW_NULL_GAP)."""
    if len(nulls) + steep_n >= _null_min(N):
        return LOW_NULL_TREND % what
    if N == WIN_DAYS:
        return LOW_NULL
    if _hist_short(cx, R, N, need, series):
        return low_null_n(cx, R, N, need, series)
    return LOW_NULL_GAP % N


def _low_ref(cx, R, N, weeks, series):
    """A 14 / 30 / 60-day row whose normal-trend reference ([R−N−7·weeks−7, R−N−1] with its week-over-week lookback) is
    short: the app's history (LOW_NULL_N: the reference sits before the series' first day) or that stretch's data."""
    f = _hist_from(cx, series)
    if f is not None and f > R - timedelta(days=N + 28):
        return low_null_n(cx, R, N, None, series)
    return LOW_REF_N % (N, weeks)


# ── the 14 / 30 / 60-day pseudo-updates in O(1) a shift: prefix sums (spec §2.7) ─────────────────────

class _Pfx:
    """Prefix sums of a per-day value `fn(day)` → tuple of `dim` numbers or None (invalid) over the days [lo, hi]
    (ordinals): the sum over any day range and how many of its days are invalid (a day outside [lo, hi] is) — two
    lookups whatever the range's length."""

    def __init__(self, fn, lo, hi, dim):
        self.lo, self.n, self.dim = lo, max(0, hi - lo + 1), dim
        self.P = [[0.0] * (self.n + 1) for _ in range(dim)]
        self.Q = [0] * (self.n + 1)
        self.v = []
        for i in range(self.n):
            x = fn(date.fromordinal(lo + i))
            self.v.append(x)
            for k in range(dim):
                self.P[k][i + 1] = self.P[k][i] + (x[k] if x is not None else 0.0)
            self.Q[i + 1] = self.Q[i] + (x is None)

    def rng(self, a, b, cnt):
        """Σ over the days a..b (ordinals) → (sums, invalid days); cnt = [reads] (the cost guard)."""
        cnt[0] += 2
        i, j = a - self.lo, b - self.lo
        tot = b - a + 1
        i0, j0 = max(i, 0), min(j, self.n - 1)
        if i0 > j0:
            return (0.0,) * self.dim, tot
        return (tuple(self.P[k][j0 + 1] - self.P[k][i0] for k in range(self.dim)),
                tot - (j0 - i0 + 1) + self.Q[j0 + 1] - self.Q[i0])

    def at(self, a, cnt):
        cnt[0] += 1
        i = a - self.lo
        return self.v[i] if 0 <= i < self.n else None


def _mset(days):
    """A day multiset (dates, repeats allowed) → (lo, hi, holes, extra) in ordinals: its hull [lo, hi] minus the hull
    days it lacks, plus each repeated day's extra count — Σ over the multiset = the hull range − holes + extras."""
    cnt = {}
    for d in days:
        o = d.toordinal()
        cnt[o] = cnt.get(o, 0) + 1
    lo, hi = min(cnt), max(cnt)
    return lo, hi, [o for o in range(lo, hi + 1) if o not in cnt], [(o, c - 1) for o, c in cnt.items() if c > 1]


def _mset_sum(pf, ms, D, cnt):
    """Σ of pf's value over the multiset ms shifted back by D days → (sums, invalid days)."""
    lo, hi, holes, extra = ms
    s, bad = pf.rng(lo - D, hi - D, cnt)
    s = list(s)
    for o in holes:
        x = pf.at(o - D, cnt)
        if x is None:
            bad -= 1
        else:
            for k in range(pf.dim):
                s[k] -= x[k]
    for o, c in extra:
        x = pf.at(o - D, cnt)
        if x is not None:
            for k in range(pf.dim):
                s[k] += c * x[k]
    return s, bad


def _pfx(cx, key, fn, dim):
    """The app's prefix sums of one per-day value (built once, shared by every block and window)."""
    cache = cx.setdefault("_pfx", {})
    if key not in cache:
        lo, hi = cx["_span"]
        cache[key] = _Pfx(fn, lo, hi, dim)
    return cache[key]


def _count(cx, N, n):
    """The pseudo-update cost guard: values read by the null loops of window N."""
    c = cx.setdefault("_nreads", {})
    c[N] = c.get(N, 0) + n


def _dau_memo(cx, blk):
    """What returning DAU reads that does not depend on the window — ρ̂, Y / O / recent / week-over-week by day, the
    normal weekly change and its backtest by their reference end day (μ for window N at shift Δ = μ for window N' at
    shift Δ + N − N') — built once per block, shared by its 7 / 14 / 30 / 60-day rows (blk["_m"])."""
    m = blk.setdefault("_m", {})
    if "dau" in m:
        return m["dau"]
    rho, Kx = _rho(cx, blk["R"])
    raw = Kx < 7
    K = 0 if raw else Kx
    ret = cx["ret"]
    memo, rmemo, omemo, wmemo, mumemo, btmemo = {}, {}, {}, {}, {}, {}
    touched = {}                                      # the days this row's Y was read on (imputed_share), in order

    def Y(d):
        if d not in memo:
            y = yi = 0.0
            for k in range(1, K + 1):
                c = d - timedelta(days=k)
                e = ret.get(c.isoformat())
                if e and e.get("ok") and len(e.get("a") or []) > k:
                    y += e["a"][k]
                else:                                 # ρ̂ is per GA4 new user: no cohort scale
                    v = (_dv(cx, c, "new") or 0) * rho[k]
                    y, yi = y + v, yi + v
            memo[d] = (y, yi)
        return memo[d][0]

    def Om(d):
        if d not in omemo:
            r = _ret_dau(cx, d)
            omemo[d] = None if r is None else r - Y(d)
        if d in memo and d not in touched:
            touched[d] = True
        return omemo[d]

    def recent(d):
        if d not in rmemo:
            rmemo[d] = sum((_dv(cx, d - timedelta(days=k), "new") or 0) * rho[k] for k in range(1, K + 1))
        return rmemo[d]

    def wow(u):
        if u not in wmemo:
            wmemo[u] = _log(Om(u), Om(u - timedelta(days=7)))
        return wmemo[u]

    def mu_ref(e):
        # the normal weekly change of the 3 weeks ending on e (= the before-window's first day − 1: the before-window
        # is the contrast's own baseline — reused as its reference it makes the noise look ~20% smaller than it is)
        if e not in mumemo:
            v = [wow(u) for u in _days(e - timedelta(days=20), e)]
            v = [x for x in v if x is not None]
            mumemo[e] = U.median(v) if v else 0.0
        return mumemo[e]

    def expd(d, b, w, mu):
        o = Om(b)
        return None if o is None or o <= 0 else o * math.exp(mu * min(w, TREND_HORIZON_WEEKS)) + recent(d)

    def backtest(e):
        if e not in btmemo:
            mu, bt = mu_ref(e), []
            for t in _days(e - timedelta(days=13), e):
                x = _log(_ret_dau(cx, t), expd(t, t - timedelta(days=7), 1, mu))
                if x is not None:
                    bt.append(x)
            btmemo[e] = bt
        return btmemo[e]
    m["dau"] = {"rho": rho, "Kx": Kx, "K": K, "raw": raw, "memo": memo, "touched": touched, "Om": Om, "Y": Y,
                "recent": recent, "mu_ref": mu_ref, "expd": expd, "backtest": backtest}
    return m["dau"]


def dau_row(cx, blk):
    """Returning DAU vs its expected level (see the module docstring, and the spec's §3.4a) over the block's window
    (blk["win"]: 7 days, or 14 / 30 / 60 — the same test with pair_day, the trend extrapolated ≤ TREND_HORIZON_WEEKS and
    that window's own pseudo-update noise). Also keeps, for the per-user rows, how much of the returning users are recent
    installs coming back (blk["_mix"])."""
    row, win, R = _row("returning_dau"), blk["win"], blk["R"]
    N = win.get("n", WIN_DAYS)
    ex = row["extra"]
    dm = _dau_memo(cx, blk)
    rho, Kx, K, raw = dm["rho"], dm["Kx"], dm["K"], dm["raw"]
    ex.update(mode="raw" if raw else "cohort", k_days=K)
    mn = DAU_MIN_REL * (2 if raw else 1)
    memo, touched, expd, backtest, mu_ref = dm["memo"], dm["touched"], dm["expd"], dm["backtest"], dm["mu_ref"]
    touched.clear()
    lag = timedelta(days=N + 1)                      # μ / backtest reference: the day before the before-window
    mu = mu_ref(R - lag)
    steep = _steep(mu)                               # a launch / growth phase: no expected level (TREND_MAX_WEEK)
    bt = [] if steep else backtest(R - lag)
    rb = [_ret_dau(cx, d) for d in _days(win["b0"], win["b1"])]
    rb = [x for x in rb if x is not None]
    ex["mu_week"] = round(mu, 5)
    used, bs, pat = [], [], []
    sr = se = srb = 0.0
    src = srcb = syb = stt = 0.0                     # (the split's: Σ recent(d), Σ recent(b), Σ Y(b), Σ Om(b)·(e^{μ·w} − 1)
                                                     # — read only)
    xa = []
    for d in win["settled"]:
        b, w = pair_day(win, R, d)
        r, e, r0 = _ret_dau(cx, d), expd(d, b, w, mu), _ret_dau(cx, b)
        x = _log(r, e)
        if x is None or not r0:
            continue
        xa.append(x)
        used.append(d), bs.append(b), pat.append((d, b, w))
        sr, se, srb = sr + r, se + e, srb + r0
        rc, yv = dm["recent"](d), dm["Y"](b)         # (memoized: re-reading them changes nothing)
        src, srcb, syb, stt = src + rc, srcb + dm["recent"](b), syb + yv, stt + (e - rc - (r0 - yv))
    if used:                                         # expected − before = (Σrecent(d) − ΣY(b) + Σtrend) ÷ n, exactly
        row["_spx"] = (("steep", mu) if steep else ("raw",) if raw
                       else ("dau", src, srcb, syb, stt, len(used), sum(rho[k] for k in range(1, K + 1))))
    ys = [memo[d] for d in touched]
    tot = sum(y for y, _ in ys)
    ex["imputed_share"] = round(sum(yi for _, yi in ys) / tot, 5) if tot else 0.0
    row["est"] = ex["imputed_share"] >= 0.01
    prov = [_ret_dau(cx, d) for d in win["avail"]]
    prov = [x for x in prov if x is not None]
    if len(win["avail"]) > len(win["settled"]) and prov:
        row["after_prov"] = _mean(prov)
    _span(row, used, bs)
    row["n_before"], row["n_after"] = len(set(bs)), len(used)
    if used:
        row.update(before=srb / len(used), after=sr / len(used), expected=se / len(used), change=sr / se - 1)
        ex["raw_change"] = round(sr / srb - 1, 5) if srb else None
        if steep:                                    # the model's level is kept aside, never shown as expected
            ex["expected_model"] = row["expected"]
            row.update(expected=None, change=sr / srb - 1 if srb else None)
    if steep:
        row["basis"] = "plain"
    if _long(win) and not steep and pat and any(w > TREND_HORIZON_WEEKS for _, _, w in pat):
        row["_capped"] = True                        # (note "trend_capped": 3 of its 4–9 weeks extrapolated)
    blk["_mix"] = _mix(cx, rho, Kx, used, bs)
    if len(win["settled"]) < IMPACT_MIN_DAYS:
        return _pending(row, win, win["a0"] + timedelta(days=IMPACT_MIN_DAYS - 1 + ACT_LATE_DAYS))
    if steep:
        row.update(status="low", raw_status="low", reason=trend_why(mu, "app"))
        return row
    if (_mean(rb) or 0) < MIN_DAU:
        row.update(status="low", raw_status="low", reason="Roz %d se kam old users — GA4 ginti ka noise zyada" % MIN_DAU)
        return row
    if len(bt) < 10 or len(xa) < IMPACT_MIN_DAYS:                # (14 / 30 / 60: the reference is N days further back)
        why = ("Update se pehle ke 2 hafte ka data kam" if N == WIN_DAYS else _low_ref(cx, R, N, 2, "dau")
               if len(bt) < 10 else LOW_AB_N)
        row.update(status="low", raw_status="low", reason=why)
        return row
    under = abs(row["change"]) < mn                  # under the minimum: Normal whatever the noise (_judge) — its
    if under and not cx.get("_noise_all"):           # noise is still measured (the page's "pakka" line), never judged
        row["raw_status"] = row["status"] = "same"
        row["_ratio"] = abs(row["change"]) / mn
        if raw:
            row["reason"] = RAW_WHY
        return row
    shift = _mean(xa) - U.median(bt)
    nulls, steep_n = [], 0                           # the same comparison at every pseudo-update before the release
    if N == WIN_DAYS or (R - cx["launch"]).days >= _hist_need(N):
        nulls, steep_n = (dm.get("nulls") or _dau_nulls)(cx, dm, R, N, used, pat)
    if len(nulls) >= _null_min(N):
        row["noise"] = _null_sd(nulls, N)
        row["need"] = _need_rel(row["change"], row["noise"], _zlevel(win), mn)
    if under:
        row["raw_status"] = row["status"] = "same"
        row["_ratio"] = abs(row["change"]) / mn
        if raw:
            row["reason"] = RAW_WHY
        return row
    if len(nulls) < _null_min(N):                    # (short only for the steep ones: not a short history)
        row.update(status="low", raw_status="low", reason=_low_null(cx, R, N, nulls, steep_n, "app", series="dau"))
        return row
    z = shift / row["noise"]
    row["z"] = z
    st = _judge(row["change"], mn, z, _zlevel(win))
    if raw:                                          # no return cohorts: the installs' returners can't be told apart
        row["reason"] = RAW_WHY                      # from the old users — at most "Maybe" (RAW_WORST)
        if st in ("worse", "better"):
            st = "unsure"
    row["raw_status"] = row["status"] = st
    row["_ratio"] = abs(row["change"]) / mn
    return row


def _dau_nulls(cx, dm, R, N, used, pat):
    """Returning DAU's pseudo-updates: the same comparison at every shift Δ before the release R (its after-days
    `used`, their (after-day, before-day, weeks) `pat`) → (nulls, the shifts skipped for a steep trend). dm =
    _dau_memo's (a precomputing stand-in may bring its own "nulls": engine.impact_any — the same values)."""
    lag = timedelta(days=N + 1)
    mu_ref, backtest, expd = dm["mu_ref"], dm["backtest"], dm["expd"]
    nulls, steep_n, cnt = [], 0, 0
    for dl in _shifts(R, used, N):
        Rq, D = R - timedelta(days=dl), timedelta(days=dl)
        e = Rq - lag
        mq = mu_ref(e)
        bq = backtest(e)
        xq = [_log(_ret_dau(cx, d - D), expd(d - D, b - D, w, mq)) for d, b, w in pat]
        cnt += 2 * len(pat)
        if len(bq) >= 10 and all(x is not None for x in xq):
            if _steep(mq):                       # the test would not run there (TREND_MAX_WEEK)
                steep_n += 1
                continue
            nulls.append(_mean(xq) - U.median(bq))
    _count(cx, ("dau", N), cnt)
    return nulls, steep_n


def _mix(cx, rho, K, used, bs):
    """How much of the returning users are recent installs coming back, on the matched after-days vs their before-days
    (ad spend moves it; their sessions / time differ from long-time users'): {share_b, share_a} from the pre-release
    return rates ρ̂ × the installs that came, or — without return rates — {swing} of the installs of the 14 days feeding
    each side. → None without matched days."""
    if not used:
        return None

    def feed(d):
        if K >= 7:
            return sum((_dv(cx, d - timedelta(days=k), "new") or 0) * rho[k] for k in range(1, K + 1))
        return sum(_dv(cx, d - timedelta(days=k), "new") or 0 for k in range(1, 15)) / 14

    fa, fb = sum(feed(d) for d in used), sum(feed(b) for b in bs)
    if K >= 7:
        ra, rb = sum(_ret_dau(cx, d) or 0 for d in used), sum(_ret_dau(cx, b) or 0 for b in bs)
        if ra > 0 and rb > 0:
            sa, sb = min(1.0, fa / ra), min(1.0, fb / rb)
            return {"share_b": sb, "share_a": sa, "moved": abs(sa - sb) > RECENT_SWING}
        return None
    sw = (fa / fb - 1) if fb else None
    return {"swing": sw, "moved": sw is not None and abs(sw) > INSTALL_SWING}


RET_KEY = {1: "new_d1", 7: "new_d7", 30: "new_d30"}


def _okc_fn(cx, N):
    """fn(install day) → (day-N returners, GA4 new users) when its cohort is complete up to day N and new > 0, else
    None — the app's, whatever the block (the prefix sums read it)."""
    ret = cx["ret"]

    def okc(c):
        e = ret.get(c.isoformat())
        if not (e and e.get("ok") and len(e.get("a") or []) > N and e.get("t")):
            return None
        nw = _new_of(cx, c)
        return (e["a"][N], nw) if nw else None
    return okc


def ret_row(cx, blk, N):
    """New users back on day N (1 / 7 / 30): after-install days vs before-install days of the same weekdays (§3.4b).
    The window's install days: after = [a0, end_a] (day N settled), before = [R−W−N, R−1−N] on their weekdays (W = the
    window's length). 7 days: noise = max(binomial·φ, the pseudo-updates' spread). 14 / 30 / 60: the pseudo-updates'
    spread only (slow install-mix drift — campaigns — that a 4-week φ never sees), ≥ NULL_MIN_X·W of them or Low data;
    judged only once every install day's day N is settled."""
    key = RET_KEY[N]
    row, win, R = _row(key), blk["win"], blk["R"]
    W = win.get("n", WIN_DAYS)
    lng = W >= LONG_MIN
    ex, ret = row["extra"], cx["ret"]
    S = cx["S_act"]
    mnpp, mnrel = (RET30_MIN_PP, RET30_MIN_REL) if N == 30 else (RET_MIN_PP, RET_MIN_REL)
    Ca = [c for c in win["days_a"] if c + timedelta(days=N) <= S]
    wd = {c.weekday() for c in Ca}
    Cb = [c for c in _days(R - timedelta(days=W + N), R - timedelta(days=1 + N)) if c.weekday() in wd]
    ready = win["a0"] + timedelta(days=2 + N + ACT_LATE_DAYS)
    if lng and len(Ca) < len(win["days_a"]):         # (D30 in a judged window: its day 30 comes at end_a + 33)
        return _pending(row, win, win["end_a"] + timedelta(days=N + ACT_LATE_DAYS))
    if len(Ca) < 3:
        return _pending(row, win, ready if len(win["days_a"]) >= 3 else None)
    rf = cx["ret_from"]
    if rf is not None and min(Cb + Ca) < rf:
        return _na(row, NA_OLD)

    okm = {}

    def done(c):
        """The install day's cohort when it is complete up to day N, else None."""
        e = ret.get(c.isoformat())
        return e if e and e.get("ok") and len(e.get("a") or []) > N and e.get("t") else None

    def okc(c):
        """The install day's (day-N returners, GA4 new users) when its cohort is complete and new > 0, else None."""
        if c not in okm:
            e, nw = done(c), _new_of(cx, c)
            okm[c] = (e["a"][N], nw) if e and nw else None
        return okm[c]
    A, B = [c for c in Ca if okc(c)], [c for c in Cb if okc(c)]
    if len(A) < 3 or not B:
        lost = any((ret.get(c.isoformat()) or {}).get("ok") is False for c in Ca + Cb)
        # a complete cohort left out only because its install day's GA4 new users are unknown / 0: no base for the
        # rate, and the next fetch would not bring one
        nonew = any(done(c) and not _new_of(cx, c) for c in Ca + Cb)
        return _na(row, NA_OLD if lost else NA_NO_NEW if nonew else NA_NOT_YET)
    xa, na = sum(okc(c)[0] for c in A), sum(okc(c)[1] for c in A)
    xb, nb = sum(okc(c)[0] for c in B), sum(okc(c)[1] for c in B)
    pb, pa = xb / nb, xa / na
    each = []
    for c in _days(R - timedelta(days=28 + N), R - timedelta(days=1 + N)):
        e = okc(c)
        if e:
            each.append((e[0], e[1], c.toordinal()))
    phi = max(1.0, U._phi(each))
    dpp = (pa - pb) * 100
    p = (xa + xb) / (na + nb)
    se = 100 * math.sqrt(p * (1 - p) * (1 / na + 1 / nb) * phi) if 0 < p < 1 else 0.0
    # the same comparison at every pseudo-update before the release (the install days of a week are not independent
    # — a campaign's users stay for days): its spread, when there are enough of them, if bigger than the model's
    nulls = []
    if not lng:
        for dl in _shifts(R - timedelta(days=N), A):
            D = timedelta(days=dl)
            Aq, Bq = [okc(c - D) for c in A], [okc(c - D) for c in B]
            if all(Aq) and all(Bq):
                nulls.append(100 * (sum(e[0] for e in Aq) / sum(e[1] for e in Aq)
                                    - sum(e[0] for e in Bq) / sum(e[1] for e in Bq)))
        _count(cx, ("rate", W), (len(A) + len(B)) * len(_shifts(R - timedelta(days=N), A)))
        if len(nulls) >= NULL_MIN:
            se = max(se, U.spread(nulls, 0.0))
    else:                                            # O(1) a shift: prefix sums of (returners, new) by install day
        pf = _pfx(cx, ("ret", N), _okc_fn(cx, N), 2)
        msA, msB, cnt = _mset(A), _mset(B), [0]
        for dl in _shifts(R - timedelta(days=N), A, W):
            sa, bad = _mset_sum(pf, msA, dl, cnt)
            if bad:
                continue
            sb, bad = _mset_sum(pf, msB, dl, cnt)
            if bad or not sa[1] or not sb[1]:
                continue
            nulls.append(100 * (sa[0] / sa[1] - sb[0] / sb[1]))
        _count(cx, ("rate", W), cnt[0])
        se = _null_sd(nulls, W) if len(nulls) >= _null_min(W) else 0.0
    z = dpp / se if se else None
    rel = dpp / (100 * pb) if pb else None
    nav, nbv = [_dv(cx, c, "new") or 0 for c in Ca], [_dv(cx, c, "new") or 0 for c in Cb]
    swing = (_mean(nav) / _mean(nbv) - 1) if nbv and _mean(nbv) else None
    ex.update(installs_before=nb, installs_after=na, swing=None if swing is None else round(swing, 4),
              cohorts_before=len(B), cohorts_after=len(A), phi=round(phi, 3))
    row.update(before=pb, after=pa, change=dpp, z=z, n_before=len(B), n_after=len(A))
    _span(row, A, B)
    provs = [c for c in win["days_a"] if c + timedelta(days=N) <= cx["E"] and okc(c)]
    if len(provs) > len(A):
        row["after_prov"] = sum(okc(c)[0] for c in provs) / sum(okc(c)[1] for c in provs)
    if se:
        row["noise"] = se
        row["need"] = _need_pp(dpp, se, _zlevel(win), mnpp, mnrel * pb * 100)
    sample = min(na, nb) >= MIN_INSTALLS and min(xa, xb) >= MIN_EVENTS and len(A) >= 3
    big = abs(dpp) >= mnpp and rel is not None and abs(rel) >= mnrel     # both minimums
    if not sample:
        st = "low"
        if lng:
            row["reason"] = LOW_RATE % (MIN_INSTALLS, MIN_EVENTS)
    elif lng and len(nulls) < _null_min(W):          # never the binomial·φ fallback at 14 / 30 / 60
        st = "low"
        row["reason"] = _low_null(cx, R, W, nulls, 0, "", need=_need_rate(win, R, N), series="rate")
    elif big and z is not None and abs(z) >= _zlevel(win) and (z > 0) == (dpp > 0):
        st = "better" if dpp > 0 else "worse"
    else:
        st = "unsure" if big else "same"
    if st in ("worse", "better") and na >= U.BIG_RECENT_USERS:        # a big app: breadth, as the uninstall alerts
        moved = sum(1 for c in A if (okc(c)[0] / okc(c)[1] > pb) == (dpp > 0))
        if moved < math.ceil(4 / 7 * len(A)):
            st = "unsure"
    row["status"] = row["raw_status"] = st
    row["_ratio"] = abs(dpp) / mnpp
    if swing is not None and abs(swing) > INSTALL_SWING:
        row["_swing"] = True
    return row


def _pu_memo(cx, mkey, M):
    """A per-user number's by-day memos (the app's, whatever the block or window): m(d), week-over-week, and the normal
    weekly change μ by its reference end day (the day before the before-window) with how many weeks it read."""
    cache = cx.setdefault("_pum", {})
    if mkey is not None and mkey in cache:
        return cache[mkey]
    memo, wmemo, mumemo = {}, {}, {}

    def m(d):
        if d not in memo:
            memo[d] = M(d)
        return memo[d]

    def wow(u):
        if u not in wmemo:
            wmemo[u] = _log(m(u), m(u - timedelta(days=7)))
        return wmemo[u]

    def mu_ref(e):
        if e not in mumemo:
            v = [wow(u) for u in _days(e - timedelta(days=20), e)]
            v = [x for x in v if x is not None]
            mumemo[e] = ((U.median(v) if v else 0.0), len(v))
        return mumemo[e]
    out = {"m": m, "mu_ref": mu_ref}
    if mkey is not None:
        cache[mkey] = out
    return out


def _pu_test(cx, blk, M, need=0.0, what="ye number", mkey=None):
    """The per-user test (§3.4d) of M (a per-user number by day): each settled after-day vs its before-day (pair_day),
    at 7 days net of the normal week-over-week change μ (the median of the 3 weeks before the before-window, NOISE_LAG),
    at 14 / 30 / 60 plain (PU_TREND_MAX_N: no trend — the lower-noise rule there); the noise = the same comparison at
    every pseudo-update before the release (_null_sd) — judged only when the effect reaches `need` (the row's minimum:
    under it the row is Normal whatever the noise; the noise itself is still measured for the page's "pakka" line). A
    normal weekly change steeper than TREND_MAX_WEEK is never extrapolated (why = trend_why(μ, `what`), steep = μ; no stat
    / adj), nor measured as noise (too few pseudo-updates left for that reason: LOW_NULL_TREND, else LOW_NULL). mkey:
    the number's name (its by-day memos and prefix sums are shared by every block and window). → {used, bs, stat (the
    mean log change it judges), adj (its effect: e^stat − 1 — what is judged), z, noise, why (None, "pending", or why
    there is no z), steep, trend (True: net of μ)}."""
    win, R = blk["win"], blk["R"]
    N = win.get("n", WIN_DAYS)
    trend = N <= PU_TREND_MAX_N
    pm = _pu_memo(cx, mkey, M)
    m, mu_ref = pm["m"], pm["mu_ref"]
    lag = timedelta(days=N + 1)
    mu, nw = mu_ref(R - lag)
    xa, used, bs, pat = [], [], [], []
    for d in win["settled"]:
        b, w = pair_day(win, R, d)
        x = _log(m(d), m(b))
        if x is None:
            continue
        xa.append(x - mu * w if trend else x)
        used.append(d), bs.append(b), pat.append((d, b, w))
    out = {"used": used, "bs": bs, "stat": None, "adj": None, "z": None, "noise": None, "why": None, "steep": None,
           "trend": trend}
    if len(win["settled"]) < IMPACT_MIN_DAYS:
        out["why"] = "pending"
        return out
    if nw < 10 or len(xa) < IMPACT_MIN_DAYS:                     # (14 / 30 / 60: the reference is N days further back)
        out["why"] = ("Update se pehle ke 3 hafte ka data kam" if trend else _low_ref(cx, R, N, 3, mkey)
                      if nw < 10 else LOW_AB_N)
        return out
    if _steep(mu):
        out["why"], out["steep"] = trend_why(mu, what), mu
        return out
    out["stat"] = st = _mean(xa)
    out["adj"] = math.exp(st) - 1
    under = abs(out["adj"]) < need
    if under and not cx.get("_noise_all"):
        return out
    nulls, steep_n = [], 0
    if trend:                                        # 7 days: today's loop, exactly
        for dl in _shifts(R, used, N):
            D = timedelta(days=dl)
            mq, nq = mu_ref(R - D - lag)
            if nq < 10:
                continue
            xq = [_log(m(d - D), m(b - D)) for d, b, _ in pat]
            if all(x is not None for x in xq):
                if _steep(mq):                       # the test would not run there (TREND_MAX_WEEK)
                    steep_n += 1
                    continue
                nulls.append(_mean([x - mq * w for x, (_, _, w) in zip(xq, pat)]))
        _count(cx, ("pu", N), 2 * len(pat) * len(_shifts(R, used, N)))
    elif (R - cx["launch"]).days >= _hist_need(N):   # 14 / 30 / 60: O(1) a shift (prefix sums of log m)
        def lg(d):
            v = m(d)
            return (math.log(v),) if v is not None and v > 0 else None
        pf = _pfx(cx, ("pu", mkey), lg, 1) if mkey is not None else _Pfx(lg, *cx["_span"], 1)
        msA, msB, cnt, n = _mset(used), _mset(bs), [0], len(used)
        for dl in _shifts(R, used, N):
            mq, nq = mu_ref(R - timedelta(days=dl) - lag)
            if nq < 10:
                continue
            sa, bad = _mset_sum(pf, msA, dl, cnt)
            if bad:
                continue
            sb, bad = _mset_sum(pf, msB, dl, cnt)
            if bad:
                continue
            if _steep(mq):
                steep_n += 1
                continue
            nulls.append((sa[0] - sb[0]) / n)
        _count(cx, ("pu", N), cnt[0])
    if len(nulls) >= _null_min(N):
        out["noise"] = _null_sd(nulls, N)
    if under:
        return out
    if len(nulls) < _null_min(N):                    # (short only for the steep ones: not a short history)
        out["why"] = _low_null(cx, R, N, nulls, steep_n, what, series=mkey)
        return out
    out["z"] = st / out["noise"]
    return out


def _pu(cx, blk, row, M, num, den, mn, what="ye number", mkey=None):
    """A per-user row: shown = pooled Σnum ÷ Σden after vs the matched before days (change = after ÷ before − 1, as
    the numbers read); judged = _pu_test's effect (adj: at 7 days net of the trend) against the minimum `mn` — a trend
    the app was already on never makes (or hides) a change; one too steep to extrapolate (TREND_MAX_WEEK) = Low data,
    the plain change only. → (row, the test)."""
    win = blk["win"]
    t = _pu_test(cx, blk, M, mn, what, mkey)
    used, bs = t["used"], t["bs"]
    sa = sum(num(d) for d in used)
    sda = sum(den(d) for d in used)
    sb = sum(num(b) for b in bs)
    sdb = sum(den(b) for b in bs)
    _span(row, used, bs)
    row["n_before"], row["n_after"] = len(set(bs)), len(used)
    if used and sda and sdb and sb:
        row.update(before=sb / sdb, after=sa / sda, change=(sa / sda) / (sb / sdb) - 1)
    pa = [d for d in win["avail"] if M(d) is not None]
    if len(win["avail"]) > len(win["settled"]) and pa and sum(den(d) for d in pa):
        row["after_prov"] = sum(num(d) for d in pa) / sum(den(d) for d in pa)
    row["basis"] = "expected" if t["trend"] and t["steep"] is None else "plain"
    if t["noise"] is not None:
        row["noise"] = t["noise"]
        row["need"] = _need_rel(t["adj"], t["noise"], _zlevel(win), mn)
    if t["why"] == "pending":
        _pending(row, win, win["a0"] + timedelta(days=IMPACT_MIN_DAYS - 1 + ACT_LATE_DAYS))
        return row, t
    if t["why"] or row["change"] is None:
        row.update(status="low", raw_status="low", reason=t["why"] or (
            "Update se pehle ke 3 hafte ka data kam" if win.get("n", WIN_DAYS) == WIN_DAYS else LOW_AB_N))
        return row, t
    row["z"] = t["z"]
    st = _judge(t["adj"], mn, t["z"], _zlevel(win))
    row["status"] = row["raw_status"] = st
    row["_ratio"] = abs(t["adj"]) / mn
    row["_eff"] = t["adj"]
    return row, t


MIX_WHY = ("Haal ke installs (ad spend) se old users ka mix badla — per-user farak mix ka bhi ho sakta hai, isliye "
           "abhi pakka nahi")


def _mix_cap(blk, row):
    """A per-user / version row while the returning users' mix moved (blk["_mix"], installs): at most Maybe."""
    mx = blk.get("_mix")
    if mx and mx["moved"] and row["status"] in ("worse", "better"):
        row["status"] = row["raw_status"] = "unsure"
        row["reason"] = MIX_WHY
        row["_mixed"] = True
    elif mx and mx["moved"]:
        row["_mixed"] = True


def use_row(cx, blk, key):
    """Sessions / engagement time per RETURNING user (usage[day]["r"]); all users in extra for the tooltip."""
    row = _row(key)
    if blk["win"].get("n", WIN_DAYS) > PU_TREND_MAX_N:
        row["basis"] = "plain"
    if not cx["usage"]:
        return _na(row, NA_NO_USAGE)
    j = 1 if key == "sessions" else 2

    def slot(d, s):
        u = cx["usage"].get(d.isoformat())
        return (u or {}).get(s) or None

    def num(d):
        return (slot(d, "r") or [0, 0, 0])[j]

    def den(d):
        return (slot(d, "r") or [0, 0, 0])[0]

    def M(d):
        r = slot(d, "r")
        return r[j] / r[0] if r and r[0] and r[j] else None
    row, t = _pu(cx, blk, row, M, num, den, USE_MIN_REL, "%s per user" % key, mkey=key)
    used, bs = t["used"], t["bs"]
    if row["basis"] == "expected" and t["adj"] is not None and row["after"] is not None:
        row["expected"] = row["after"] / (1 + t["adj"])     # "vs expected" = exactly the judged (trend-net) change

    def allu(days):
        n = sum((slot(d, "n") or [0, 0, 0])[j] + (slot(d, "r") or [0, 0, 0])[j] for d in days)
        a = sum(_dv(cx, d, "a1") or 0 for d in days)
        return n / a if a else None
    row["extra"].update(all_before=allu(bs), all_after=allu(used), adj_change=t["adj"])
    if row["status"] not in ("pending", "na") and t["steep"] is None:     # (a steep trend: its own reason)
        mr = [den(d) for d in bs]
        if mr and _mean(mr) < MIN_DAU:
            row.update(status="low", raw_status="low", reason="Roz %d se kam old users" % MIN_DAU)
    _mix_cap(blk, row)
    return row


MARKET_WHY = "Sirf ad rate badla, ads per user wahi — bazaar ka asar, update ka nahi"
IMP_ONLY_WHY = ("Revenue per user pehle se tez badal rahi thi (ad rate — bazaar) — faisla sirf ads per user (%s) se, uska "
                "trend normal")
NO_IMP_WHY = "Ads per user ka data kam — revenue per user ka farak update ka hai ya bazaar ka, pakka nahi"


def arpdau_row(cx, blk):
    """Ad revenue per 1,000 active users (AdMob revenue ÷ GA4 activeUsers), shown before / after. JUDGED on the part
    an update can move — ads (impressions) per active user, with its own trend-net test, minimum ARPDAU_MIN_REL and
    BIG_X: eCPM (the price per ad) is the market's. Revenue per user moving for sure while ads per user moved under
    IMP_MIN_REL (or the other way) = "Market", never counted (§3.4f). A normal weekly change too steep to extrapolate
    (TREND_MAX_WEEK): of ads per user = Low data, nothing judged; of revenue per user only (eCPM) = no Market / Maybe
    from revenue — ads per user alone may still say Worse / Better, else Low data."""
    row = _row("arpdau")
    if blk["win"].get("n", WIN_DAYS) > PU_TREND_MAX_N:
        row["basis"] = "plain"
    ex = row["extra"]
    ex.update(tz_blend=cx["tz_blend"], currency=cx["currency"])
    f = cx["rev"]
    if f is None:
        return _na(row, NA_NO_REV)

    def a1(d):
        return _dv(cx, d, "a1") or 0

    def rev(d):
        v = f(d)
        return v[0] if v and a1(d) else 0.0

    def imp(d):
        v = f(d)
        return v[1] if v and a1(d) else 0.0

    def M(d):
        v, a = f(d), a1(d)
        return v[0] / a * 1000 if v and a and v[0] > 0 else None

    def Mi(d):
        v, a = f(d), a1(d)
        return v[1] / a if v and a and v[1] > 0 else None

    def pool(days, fn):
        a = sum(a1(d) for d in days)
        return fn(days) / a if a else None
    win = blk["win"]
    row, t = _pu(cx, blk, row, M, lambda d: rev(d) * 1000, a1, ARPDAU_MIN_REL, "revenue per user", mkey="rev")
    used, bs = t["used"], t["bs"]
    ia, ib = pool(used, lambda ds: sum(imp(d) for d in ds)), pool(bs, lambda ds: sum(imp(d) for d in ds))
    ra, rb = sum(rev(d) for d in used), sum(rev(d) for d in bs)
    ea = ra / sum(imp(d) for d in used) if ia else None
    eb = rb / sum(imp(d) for d in bs) if ib else None
    ns_b = pool(bs, lambda ds: sum(_dv(cx, d, "new") or 0 for d in ds))
    ns_a = pool(used, lambda ds: sum(_dv(cx, d, "new") or 0 for d in ds))
    if used and bs:                                  # (the split's: active users per day, before / after)
        row["_spx"] = ("rev", sum(a1(d) for d in bs) / len(bs), sum(a1(d) for d in used) / len(used), ns_b, ns_a)
    ti = _pu_test(cx, blk, Mi, IMP_MIN_REL, "ads per user", mkey="imp")   # the update's part: ads per active user
    row["basis"] = "expected" if ti["trend"] and ti["steep"] is None else "plain"
    row["noise"] = ti["noise"]                       # (judged on ads per user: its noise, its minimum)
    row["need"] = _need_rel(ti["adj"], ti["noise"], _zlevel(win), ARPDAU_MIN_REL)
    ex.update(imp_before=ib, imp_after=ia,
              imp_expected=ia / (1 + ti["adj"]) if ia is not None and ti["adj"] is not None
              and row["basis"] == "expected" else None)
    ex.update(imp_change=round(ia / ib - 1, 4) if ia and ib else None, imp_adj=ti["adj"],
              ecpm_change=round(ea / eb - 1, 4) if ea and eb else None,
              newshare_before=None if ns_b is None else round(ns_b, 5),
              newshare_after=None if ns_a is None else round(ns_a, 5))
    if ns_a is not None and ns_b is not None and abs(ns_a - ns_b) > NEWSHARE_SWING:
        row["_swing"] = True
    if row["n_after"] == 0 and row["status"] not in ("pending",) and any(f(d) is None for d in win["settled"]):
        return _na(row, NA_NO_REV)
    if ti["steep"] is not None and row["status"] not in ("pending", "na"):    # ads per user (the update's part) on
        row.update(status="low", raw_status="low", z=None, reason=ti["why"])    # a steep trend: nothing judged
        row.pop("_ratio", None), row.pop("_eff", None)
        return row
    if t["steep"] is not None and row["status"] == "low":
        # revenue per user on a steep trend (eCPM — the market's): its own test can't run, so no Market / Maybe from
        # it; ads per user, judged on its own (believable) trend, still decides a Worse / Better by itself
        st_i = _judge(ti["adj"], ARPDAU_MIN_REL, ti["z"], _zlevel(win)) if ti["adj"] is not None else "low"
        if st_i in ("worse", "better"):
            row.update(status=st_i, raw_status=st_i, z=ti["z"], reason=IMP_ONLY_WHY % U.fmt_rel(ti["adj"]))
            row["_ratio"], row["_eff"] = abs(ti["adj"]) / ARPDAU_MIN_REL, ti["adj"]
            return row
    if row["status"] in ("pending", "low", "na"):
        row.pop("_ratio", None), row.pop("_eff", None)
        return row
    st_r, Z = row["raw_status"], _zlevel(win)
    small = ti["adj"] is not None and abs(ti["adj"]) < IMP_MIN_REL      # ads per user ~flat (its noise not needed)
    if ti["adj"] is None or (ti["z"] is None and not small):     # ads per user can't be judged: revenue alone never
        st = "unsure" if st_r in ("worse", "better", "unsure") else st_r              # decides whose it is
        if st == "same" and ti["adj"] is not None and abs(ti["adj"]) >= ARPDAU_MIN_REL:
            st = "low"                               # ads per user moved past the minimum, its noise unmeasured:
            row["reason"] = (ti["why"] if ti["why"] not in (None, "pending")    # never "Normal" next to that number
                             else NO_IMP_WHY)
        row.update(status=st, raw_status=st, z=None)
        if st == "unsure":
            row["reason"] = NO_IMP_WHY
        row.pop("_ratio", None), row.pop("_eff", None)
        return row
    st_i = "same" if small else _judge(ti["adj"], ARPDAU_MIN_REL, ti["z"], Z)
    if st_i in ("worse", "better"):
        st, z = st_i, ti["z"]
    elif st_r in ("worse", "better"):
        if small or (ti["adj"] < 0) != (st_r == "worse"):
            st, z = "market", row["z"]
            row["reason"] = MARKET_WHY
        else:
            st, z = "unsure", ti["z"]
            row["reason"] = ("Revenue per user ka farak pakka, par ads per user ka hissa (%s) abhi pakka nahi — baaki "
                             "ad rate (bazaar)" % U.fmt_rel(ti["adj"]))
    else:
        st, z = ("unsure" if "unsure" in (st_i, st_r) else "same"), (row["z"] if small else ti["z"])
    row.update(status=st, raw_status=st, z=z)
    row["_ratio"], row["_eff"] = abs(ti["adj"]) / ARPDAU_MIN_REL, ti["adj"]
    return row


def d0_row(cx, blk):
    """Uninstall on install day: the uninstall engine's comparison (_judge_est — sample, MIN_PP, MIN_REL, the estimate
    rule) of the after-install days vs the before-install days of the same weekdays. Two reads: the newest (every
    after-day ≤ E — late app_remove only adds, so a rise is real: worse only) and the settled one (≤ E − LATE_DAYS:
    both ways)."""
    row, win, R, cd = _row("uninstall_d0"), blk["win"], blk["R"], cx["cd"]
    ex = row["extra"]
    hs, H = cd["hs"], cd["H"]

    def each(days):
        out = []
        for c in days:
            i = (c - hs).days
            if 0 <= i < H and cd["n"][i] and U._left_out(cd, i, 0) is None:
                out.append((cd["cum"][i][0], cd["n"][i], i))
        return out

    def side(days):
        e = each(days)
        return sum(x[0] for x in e), sum(x[1] for x in e), len(e), e
    phi = max(1.0, U._phi(each(_days(R - timedelta(days=28), R - timedelta(days=1)))))
    ex["phi"] = round(phi, 3)
    reads = {}
    for name, top in (("newest", cx["E"]), ("settled", cx["S_un"])):
        Ca = [c for c in win["days_a"] if c <= top]
        wd = {c.weekday() for c in Ca}
        Cb = [c for c in _days(R - timedelta(days=7), R - timedelta(days=1)) if c.weekday() in wd]
        r, b = side(Ca), side(Cb)
        if not r[1] or not b[1]:
            reads[name] = None
            continue
        fires, z, dpp, relsm, est = U._judge_est(cd, 0, r, b, phi)
        ri = [x[2] for x in r[3]]
        est_r = U._est_of(cd, ri, 0, r[0], U._added(cd, ri, 0)[0], r[1])
        reads[name] = {"fires": fires, "z": z, "dpp": dpp, "relsm": relsm, "est": est or est_r, "r": r, "b": b,
                       "prov": any(c > cx["S_un"] for c in Ca), "Ca": [hs + timedelta(days=x[2]) for x in r[3]],
                       "Cb": [hs + timedelta(days=x[2]) for x in b[3]]}
    nw, stl = reads.get("newest"), reads.get("settled")
    if nw and nw["fires"] and nw["dpp"] > 0:
        use, st = nw, "worse"
    elif stl and stl["fires"]:
        use, st = stl, ("worse" if stl["dpp"] > 0 else "better")
    else:
        use = stl if stl and stl["r"][2] >= U.RECENT_MIN else nw
        st = None
    if use is None:
        if len(win["days_a"]) and win["a0"] > cx["E"] - timedelta(days=U.RECENT_MIN - 1):
            return _pending(row, win, win["a0"] + timedelta(days=U.RECENT_MIN - 1))
        row.update(status="low", raw_status="low", reason="Same day uninstall ka data kam")
        return row
    r, b = use["r"], use["b"]
    row["_spx"] = ("ur", b[1], b[2], r[1], r[2])     # (the split's: installs and install days, before / after)
    ex.update(read="newest" if use is nw else "settled", est=use["est"])
    row.update(before=b[0] / b[1], after=r[0] / r[1], change=use["dpp"], z=use["z"], n_before=b[2], n_after=r[2],
               prov=bool(use is nw and use["prov"]), est=bool(use["est"]))
    _span(row, use["Ca"], use["Cb"])
    pp = (r[0] + b[0]) / (r[1] + b[1])               # the binomial·φ se _judge_est used (its |Δ ÷ z|)
    if 0 < pp < 1:
        row["noise"] = 100 * math.sqrt(pp * (1 - pp) * (1 / r[1] + 1 / b[1]) * phi)
        pb = b[0] / b[1]
        row["need"] = _need_pp(use["dpp"], row["noise"], U.Z_MIN, U.MIN_PP, U.MIN_REL * min(pb, 1 - pb) * 100)
    if nw and stl and use is stl and nw["r"][2] > stl["r"][2]:
        row["after_prov"] = nw["r"][0] / nw["r"][1]
    if st is None:
        if r[2] < U.RECENT_MIN and win["days_a"] and win["days_a"][-1] > cx["E"]:
            return _pending(row, win, win["a0"] + timedelta(days=U.RECENT_MIN - 1))
        sample = U._sample(r[2], r[1], r[0]) and b[0] >= U.MIN_EVENTS and b[1] - b[0] >= U.MIN_EVENTS
        st = ("low" if not sample else "unsure" if abs(use["dpp"]) >= U.MIN_PP and use["relsm"] >= U.MIN_REL
              else "same")
        if st == "low":
            row["reason"] = "Same day uninstall ka data kam — %d din, %d installs (kam se kam %d din, %d installs)" % (
                r[2], r[1], U.RECENT_MIN, U.MIN_RECENT_USERS)
    row["status"] = row["raw_status"] = st
    row["_ratio"] = abs(use["dpp"]) / U.MIN_PP
    return row


def _d0_cell_fn(cx):
    """fn(install day) → (uninstalled on install day, installs) of a day that can count (_left_out: complete, no
    tracking break), else None — the app's, whatever the block."""
    cd = cx["cd"]
    hs, H = cd["hs"], cd["H"]

    def cell(c):
        i = (c - hs).days
        if 0 <= i < H and cd["n"][i] and U._left_out(cd, i, 0) is None:
            return (cd["cum"][i][0], cd["n"][i])
        return None
    return cell


def d0_long(cx, blk):
    """Uninstall on install day at 14 / 30 / 60 days: the SETTLED read only (install days ≤ S_un; pending until every
    after-install day is), pooled after − before in points, judged against the window's own pseudo-update noise (slow
    install-mix drift — campaigns — reads as a change on a within-4-weeks φ): worse / better only at |z| ≥ Z_FINAL and
    ≥ U.MIN_PP and ≥ U.MIN_REL of the smaller side; up = worse. The ESTIMATE RULE as the 7-day row (U._as_read)."""
    row, win, R, cd = _row("uninstall_d0"), blk["win"], blk["R"], cx["cd"]
    N = win["n"]
    ex = row["extra"]
    hs = cd["hs"]
    cell = _d0_cell_fn(cx)
    each28 = []
    for c in _days(R - timedelta(days=28), R - timedelta(days=1)):
        x = cell(c)
        if x:
            each28.append((x[0], x[1], (c - hs).days))
    phi = max(1.0, U._phi(each28))
    ex.update(phi=round(phi, 3), read="settled")
    if any(c > cx["S_un"] for c in win["days_a"]):
        return _pending(row, win, win["end_a"] + timedelta(days=cx["late"]))
    Ca = [c for c in win["days_a"] if cell(c)]
    Cb = [c for c in _days(win["b0"], win["b1"]) if cell(c)]
    if len(Ca) < 3 or not Cb:
        row.update(status="low", raw_status="low", reason="Install ke din ke uninstall ka data kam")
        return row
    xa, na = sum(cell(c)[0] for c in Ca), sum(cell(c)[1] for c in Ca)
    xb, nb = sum(cell(c)[0] for c in Cb), sum(cell(c)[1] for c in Cb)
    pa, pb = xa / na, xb / nb
    row["_spx"] = ("ur", nb, len(Cb), na, len(Ca))   # (the split's: installs and install days, before / after)
    dpp = round((pa - pb) * 100, 6)                  # rounded so float dust can't decide a flag at the edge
    ia, ib = [(c - hs).days for c in Ca], [(c - hs).days for c in Cb]
    ar, ab = U._added(cd, ia, 0)[0], U._added(cd, ib, 0)[0]
    est = U._est_of(cd, ib, 0, xb, ab, nb) or U._est_of(cd, ia, 0, xa, ar, na)
    ex["est"] = est
    row.update(before=pb, after=pa, change=dpp, n_before=len(Cb), n_after=len(Ca), est=bool(est))
    _span(row, Ca, Cb)
    small = min(pb, 1 - pb)
    sample = U._sample(len(Ca), na, xa) and xb >= U.MIN_EVENTS and nb - xb >= U.MIN_EVENTS
    nulls = []
    pf = _pfx(cx, ("d0",), cell, 2)
    msA, msB, cnt = _mset(Ca), _mset(Cb), [0]
    for dl in _shifts(R, Ca, N):
        sa, bad = _mset_sum(pf, msA, dl, cnt)
        if bad:
            continue
        sb, bad = _mset_sum(pf, msB, dl, cnt)
        if bad or not sa[1] or not sb[1]:
            continue
        nulls.append(100 * (sa[0] / sa[1] - sb[0] / sb[1]))
    _count(cx, ("d0", N), cnt[0])
    if len(nulls) >= _null_min(N):
        row["noise"] = _null_sd(nulls, N)
        row["need"] = _need_pp(dpp, row["noise"], Z_FINAL, U.MIN_PP, U.MIN_REL * small * 100)
    row["_ratio"] = abs(dpp) / U.MIN_PP
    if not sample:
        row.update(status="low", raw_status="low",
                   reason="Same day uninstall ka data kam — %d din, %d installs (kam se kam %d din, %d installs)"
                   % (len(Ca), na, U.RECENT_MIN, U.MIN_RECENT_USERS))
        return row
    if row["noise"] is None:
        row.update(status="low", raw_status="low",
                   reason=_low_null(cx, R, N, nulls, 0, "", need=_need_rate(win, R, 0), series="d0"))
        return row
    z = dpp / row["noise"]
    row["z"] = z

    def fires(d):
        return (abs(d / row["noise"]) >= Z_FINAL and abs(d) >= U.MIN_PP
                and (abs(d) / 100 / small if small > 0 else float("inf")) >= U.MIN_REL)
    big = abs(dpp) >= U.MIN_PP and (abs(dpp) / 100 / small if small > 0 else float("inf")) >= U.MIN_REL
    f = fires(dpp)
    if f and (ar or ab):                             # the ESTIMATE RULE: the cells as GA4 returned them fire too
        d2 = ((xa - ar) / na - (xb - ab) / nb) * 100
        f = fires(d2) and (d2 > 0) == (dpp > 0)
    st = ("worse" if dpp > 0 else "better") if f else "unsure" if big else "same"
    row["status"] = row["raw_status"] = st
    return row


def _vside(cx, d, keep):
    """Σ [aR, sR, tR] of the versions `keep(version)` says on day d (vuse; "_x" never)."""
    vu = cx["vuse"].get(d.isoformat()) or {}
    a = s = t = 0
    for v, x in vu.items():
        if v != "_x" and keep(v):
            a, s, t = a + x[3], s + x[4], t + x[5]
    return a, s, t


def ver_data(cx, blk):
    """The same-days comparison of a version block: per settled after-day with ≥ VER_MIN_USERS returning users on both
    sides, the new version (the chain's) vs the older ones (first ≥5% before the release, + "_rest") → {days, rows:
    {sessions|time: {r: [log ratios], new, old}}}."""
    chain, R = set(blk["versions"]), blk["R"]
    old = {v for v, d in cx["first5"].items() if d < R and v not in chain}
    days, acc = [], {"sessions": [[], 0, 0, 0, 0], "time": [[], 0, 0, 0, 0]}
    for d in blk["win"]["settled"]:
        n = _vside(cx, d, lambda v: v in chain)
        o = _vside(cx, d, lambda v: v in old or v == "_rest")
        if n[0] < VER_MIN_USERS or o[0] < VER_MIN_USERS:
            continue
        days.append(d)
        for key, j in (("sessions", 1), ("time", 2)):
            x = _log(n[j] / n[0], o[j] / o[0])
            if x is not None:
                a = acc[key]
                a[0].append(x)
                a[1], a[2], a[3], a[4] = a[1] + n[j], a[2] + n[0], a[3] + o[j], a[4] + o[0]
    return {"days": days, "rows": {k: {"r": a[0], "new": a[1] / a[2] if a[2] else None,
                                       "old": a[3] / a[4] if a[4] else None} for k, a in acc.items()}}


def ver_rows(cx, blk, earlier):
    """New version vs old versions, same days, net of the usual early-updater gap β (the median of the latest ≤ BIAS_MAX
    earlier version updates' own gap, each with ≥3 valid days); at most "unsure" with fewer than BIAS_MIN of them or when
    GA4 could not split new / returning users (§3.4h)."""
    out = {k: _vrow() for k in VROWS}
    win = blk["win"]
    cmp_ = {"new_label": blk["label"] if blk["kind"] == "version" else None, "days": {"from": None, "to": None, "n": 0},
            "adoption_mean": None if win["adopt_mean"] is None else round(win["adopt_mean"], 5), "split": cx["split"],
            "bias": {"releases": 0, "sessions": None, "time": None}, "rows": out}
    if blk["kind"] != "version":
        for r in out.values():
            _na(r, NA_NO_VER)
        return cmp_
    if not cx["vuse"]:
        for r in out.values():
            _na(r, NA_NO_USAGE)
        return cmp_
    vd = blk.get("_vd") or ver_data(cx, blk)
    blk["_vd"] = vd
    days = vd["days"]
    cmp_["days"] = {"from": _iso(days[0]) if days else None, "to": _iso(days[-1]) if days else None, "n": len(days)}
    prior = [e for e in earlier if e["kind"] == "version" and len((e.get("_vd") or {}).get("days") or []) >= 3][-BIAS_MAX:]
    cmp_["bias"]["releases"] = len(prior)
    for key, rk in (("sessions", "ver_sessions"), ("time", "ver_time")):
        row, d = out[rk], vd["rows"][key]
        row["n_days"] = len(d["r"])
        row["old"], row["new"] = d["old"], d["new"]
        if d["old"] and d["new"]:
            row["diff"] = d["new"] / d["old"] - 1
        xs = [_mean(e["_vd"]["rows"][key]["r"]) for e in prior if e["_vd"]["rows"][key]["r"]]
        beta = U.median(xs) if xs else 0.0
        if xs:
            cmp_["bias"][key] = round(math.exp(beta) - 1, 5)
            row["bias"] = math.exp(beta) - 1
        if len(d["r"]) < IMPACT_MIN_DAYS:
            if len(win["settled"]) < len(win["days_a"]):
                row.update(status="pending", raw_status="pending")
            else:
                row.update(status="low", raw_status="low",
                           reason="Naye / purane version pe roz %d se kam old users" % VER_MIN_USERS)
            continue
        m = _mean(d["r"])
        # the usual gap's spread: the robust one, never under the plain SD of so few updates (the robust one of 3
        # values is often ~0), widened by the 95% t ÷ normal ratio of its k − 1 degrees of freedom (a spread read
        # from 3–6 updates is itself a guess: 3 that agree by chance are not proof), + the uncertainty of β itself
        # (a median of k: 1.571 σ² / k)
        k = len(xs)
        sb = max(U.spread(xs, beta), _sd(xs), SIGMA_FLOOR) * (T975.get(k - 1, 1.96) / 1.96 if k else 1.0)
        sr = max(U.spread(d["r"], U.median(d["r"])), SIGMA_FLOOR)
        z = (m - beta) / math.sqrt(sb * sb * (1 + (1.571 / k if k else 0)) + sr * sr / len(d["r"]))
        row["adj"], row["z"] = math.exp(m - beta) - 1, z
        st = _judge(row["adj"], VER_MIN_REL, z, _zlevel(win))
        why = None
        if not cx["split"]:
            why = "GA4 is property me naye aur old users alag nahi deta — sab users ki tulna, sirf andaza"
        elif len(prior) < BIAS_MIN:
            why = "Pehle ke kam se kam %d update chahiye — aam farak abhi pata nahi" % BIAS_MIN
        if why and st in ("worse", "better"):
            st = "unsure"
        row["reason"] = why
        row["status"] = row["raw_status"] = st
        row["_ratio"] = abs(row["adj"]) / VER_MIN_REL
        _mix_cap(blk, row)                            # recent installs sit on the new version: their mix moved it
    return cmp_


# ── verdict, persistence, text ───────────────────────────────────────────────────────────────────

T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}   # t 97.5%, by df


def _sd(v):
    """Sample standard deviation (0 under 2 values)."""
    if len(v) < 2:
        return 0.0
    m = sum(v) / len(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def _eff(key, row):
    """The effect a row is judged on: the trend-net one of the per-user rows (ads per user for ARPDAU), else change."""
    return row.get("_eff", row["change"]) if key in ("sessions", "time", "arpdau") else row["change"]


def _pct(x, dp=1):
    s = ("%.*f" % (dp, abs(x) * 100)).rstrip("0").rstrip(".") if dp else "%d" % round(abs(x) * 100)
    return s + "%"


def _users(x):
    return "{:,}".format(int(round(x)))


def fmt_dur(sec):
    """48s · 5m 20s · 1h 05m (the page's uniDur)."""
    s = int(round(sec or 0))
    if s < 60:
        return "%ds" % s
    if s < 3600:
        return "%dm %02ds" % (s // 60, s % 60)
    return "%dh %02dm" % (s // 3600, (s % 3600) // 60)


def _money(v, cur):
    return ("$%.2f" % v) if cur == "USD" else "%s %.2f" % (cur, v)


def _money_pu(v1k, cur):
    """Revenue stored per 1,000 users → per user (÷ 1,000), with enough decimals for 2 significant digits:
    $4.20 per 1,000 → "$0.0042", ₹380 → "INR 0.38"."""
    if v1k is None:
        return "—"
    x = v1k / 1000
    a = abs(x)
    dp = 2 if a >= 0.1 or a == 0 else min(6, 1 - int(math.floor(math.log10(a))))
    t = "%.*f" % (dp, x)
    return ("$" + t) if cur == "USD" else "%s %s" % (cur, t)


BACK_NAME = {"new_d1": "back next day", "new_d7": "back after 7 days", "new_d30": "back after 30 days",
             "uninstall_d0": "same day uninstall"}


def _dir(x, up_word, down_word):
    return up_word if x > 0 else down_word


def _signed_pct(x):
    return U._minus(("+" if x > 0 else "-" if x < 0 else "") + _pct(x))


def head_phrase(key, row, cx, n=None):
    """The row's message phrase (alert text; spec §3.7). A row whose judged change points the other way from its plain
    before → after leads with the judged one (the alert never opens on a rise for a HALT). n: a 14 / 30 / 60-day
    window's length — a plain-basis per-user row says "<n> din pehle vs baad"."""
    c = row.get("change")
    if key == "returning_dau":
        pt = _plain_too(key, row, "; pehle se %s %s")
        what = "expected se %s %s" % (_pct(c), _dir(c, "zyada", "kam")) if pt else "%s %s" % (
            _pct(c), _dir(c, "badha", "gira"))
        return "old users ka DAU %s (expected %s → %s/day%s)" % (what, _users(row["expected"]), _users(row["after"]), pt)
    if key in ("new_d1", "new_d7", "new_d30", "uninstall_d0"):
        o, n, sd = U.shown_pct(row["before"], row["after"])
        return "%s %s → %s" % (BACK_NAME[key], o, n)
    if key in ("sessions", "time"):
        e = _eff(key, row)
        b, a = ((U._minus("%.1f" % row["before"]), U._minus("%.1f" % row["after"])) if key == "sessions"
                else (fmt_dur(row["before"]), fmt_dur(row["after"])))
        lead = "old users ke sessions per user" if key == "sessions" else "old users ka time per user"
        if row.get("basis") == "plain":
            return "%s%s %s → %s (%s)" % (lead, " %d din pehle vs baad" % n if n else "", b, a, U.fmt_rel(e))
        if _plain_too(key, row):
            return "%s normal trend hata ke %s (%s → %s, seedha %s)" % (lead, U.fmt_rel(e), b, a, U.fmt_rel(c))
        net = "" if e is None or abs(e - c) < 0.01 else "; normal trend hata ke %s" % U.fmt_rel(e)
        return "%s %s → %s (%s%s)" % (lead, b, a, U.fmt_rel(c), net)
    if key == "arpdau":
        imp = _eff(key, row)
        if imp and c and abs(c) >= 0.005 and (imp < 0) != (c < 0):
            return "ads per user %s (revenue per user %s → %s, %s)" % (
                U.fmt_rel(imp), _money_pu(row["before"], cx["currency"]), _money_pu(row["after"], cx["currency"]),
                U.fmt_rel(c))
        return "revenue per user %s → %s (%s) — ads per user %s" % (
            _money_pu(row["before"], cx["currency"]), _money_pu(row["after"], cx["currency"]), U.fmt_rel(c),
            U.fmt_rel(imp) if imp is not None else "—")
    what = "sessions per user" if key == "ver_sessions" else "time per user"
    return "naye version pe %s purane se %s %s (aam farak hata ke)" % (what, _pct(row["adj"], 0),
                                                                     _dir(row["adj"], "zyada", "kam"))


def short_phrase(key, row):
    """"time per user −14%", "back next day 22% → 18%" — the "aur … kharab" list."""
    if key == "returning_dau":
        return "DAU " + _signed_pct(row["change"])
    if key in ("new_d1", "new_d7", "new_d30", "uninstall_d0"):
        o, n, _sd = U.shown_pct(row["before"], row["after"])
        return "%s %s → %s" % (BACK_NAME[key], o, n)
    if key in ("sessions", "time"):
        return "%s per user %s" % (key, U.fmt_rel(_eff(key, row)))
    if key == "arpdau":
        return "ads per user " + U.fmt_rel(_eff(key, row))
    return "new version %s %s" % ("sessions" if key == "ver_sessions" else "time", U.fmt_rel(row["adj"]))


def why_phrase(key, row):
    """"old users ka DAU expected se 5.6% kam" — the verdict's why line."""
    if key == "returning_dau":
        return "old users ka DAU expected se %s %s%s" % (_pct(row["change"]), _dir(row["change"], "zyada", "kam"),
                                                         _plain_too(key, row))
    if key in ("new_d1", "new_d7", "new_d30", "uninstall_d0"):
        o, n, _sd = U.shown_pct(row["before"], row["after"])
        return "%s %s → %s" % (BACK_NAME[key], o, n)
    if key in ("sessions", "time"):
        e, pt = _eff(key, row), _plain_too(key, row)
        return "%s%s %s %s%s" % ("sessions per user" if key == "sessions" else "time per user",
                                 " normal trend hata ke" if pt else "", _pct(e, 0), _dir(e, "zyada", "kam"), pt)
    if key == "arpdau":
        e = _eff(key, row)
        return "ads per user %s %s (revenue per user %s)" % (_pct(e, 0), _dir(e, "zyada", "kam"),
                                                            U.fmt_rel(row["change"]))
    what = "sessions per user" if key == "ver_sessions" else "time per user"
    return "new version %s %s %s" % (what, _pct(row["adj"], 0), _dir(row["adj"], "zyada", "kam"))


def _join(parts):
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " aur " + parts[-1]


def _cap(s):
    return s[:1].upper() + s[1:] if s else s


def persist(rows, prev_rows, advanced, final, fresh):
    """Raw statuses → effective ones (in place): streak +1 when E advanced and the raw status repeats (hourly re-runs
    with the same E never advance it); a worse / better row counts only after PERSIST daily evaluations, or once the
    block is final, or on the app's first impact evaluation (seeded) — else it shows "unsure" (WAIT_PERSIST).
    → {row: [raw status, streak]} to keep."""
    keep = {}
    for key, row in rows.items():
        raw = row["raw_status"]
        pst, pstreak = (prev_rows.get(key) or [None, 0])[:2]
        if raw in ("worse", "better"):
            if advanced:
                streak = pstreak + 1 if pst == raw else 1
            else:
                streak = pstreak if pst == raw else 1
        else:
            streak = 0
        row["streak"] = streak
        keep[key] = [raw, streak]
        if raw in ("worse", "better") and not (streak >= PERSIST or final or fresh):
            row["status"] = "unsure"
            row["reason"] = WAIT_PERSIST
    return keep


def verdict(blk, rows, vrows, cx, final=None):
    """The block's verdict from its effective row statuses (spec §3.6) — over the rows present (the 7-day block's 7 + 2,
    a 14-day window's 7, a 30 / 60-day window's 8 with D30). final: a long window's, from its state (§2.6); the 7-day
    block computes its own (every after-day settled and D7 in)."""
    win = blk["win"]
    allr = dict(rows, **vrows)
    keys = [k for k in ROWS_LONG + VROWS if k in allr]
    settled = len(win["settled"])
    na_all = blk.get("_na")
    if final is None:
        final = bool(win["days_a"]) and settled == len(win["days_a"]) and rows["new_d7"]["status"] != "pending"
    worse = [k for k in keys if allr[k]["status"] == "worse"]
    better = [k for k in keys if allr[k]["status"] == "better"]
    pending = [k for k in keys if allr[k]["status"] == "pending"]
    primary = [k for k in PRIMARY if k in allr and not allr[k].get("_swing")]
    groups = ([[k for k in m if k in allr] for _, m in GROUPS] + [[k] for k in PRIMARY if k in allr and allr[k].get("_swing")])
    groups = [g for g in groups if g]
    diluted = win["adopt_mean"] is not None and win["adopt_mean"] < ADOPT_LOW
    readies = [allr[k]["ready_on"] for k in pending if allr[k].get("ready_on")]
    if final:
        ready_on = None
    else:
        last = win["days_a"][-1] if win["days_a"] else None
        cands = readies + ([_iso(last + timedelta(days=ACT_LATE_DAYS))] if last else [])
        ready_on = max(cands) if cands else None
    out = {"level": None, "early": not final, "final": final, "why": "", "worse": worse, "better": better,
           "pending": pending, "ready_on": ready_on, "settled_days": settled, "min_days": IMPACT_MIN_DAYS}
    if na_all:
        out.update(why=blk["_na"], ready_on=None)
        return out
    if settled < IMPACT_MIN_DAYS:
        out["why"] = "Abhi %d final day%s — kam se kam %d chahiye" % (settled, "" if settled == 1 else "s",
                                                                      IMPACT_MIN_DAYS)
        return out
    pw = [k for k in primary if k in worse]
    gw = [g for g in groups if any(k in worse for k in g)]
    big = any(allr[k].get("_ratio", 0) >= BIG_X for k in pw)
    pb = [k for k in primary if k in better and not (diluted and k in APP_LEVEL)]
    gb = [g for g in groups if any(k in better and not (diluted and k in APP_LEVEL) for k in g)]
    if len(pw) >= 2 or (pw and big) or (len(pw) == 1 and len(gw) >= 2):
        level = "halt"
    elif len(pw) == 1 or len(gw) >= 2:
        level = "hold"
    elif final and not worse and (pb or len(gb) >= 2):
        level = "win"
    else:
        level = "continue"
    out["level"] = level
    tail = {1: " — pakka", 2: " — dono pakke"}
    if level in ("halt", "hold"):
        ks = _rank(worse, allr)
        out["why"] = _cap(_join([why_phrase(k, allr[k]) for k in ks])) + tail.get(len(ks), " — sab pakke")
    elif level == "win":
        ks = _rank(better, allr)
        out["why"] = _cap(_join([why_phrase(k, allr[k]) for k in ks])) + " — pakka faayda, koi nuksaan nahi"
    elif worse:
        out["why"] = _cap(_join([why_phrase(k, allr[k]) for k in _rank(worse, allr)])) + \
            " — sirf ek taraf ka pakka nuksaan, baaki theek: rollout chalne do"
    else:
        un = [k for k in keys if allr[k]["status"] == "unsure" and allr[k].get("_ratio")]
        if better:
            out["why"] = _cap(_join([why_phrase(k, allr[k]) for k in _rank(better, allr)])) + \
                (" — adoption kam, isliye “Update went well” nahi" if diluted else " — abhi pakka nahi"
                 if not final else "")
        elif un:
            out["why"] = "Kuch farak dikh raha hai (%s), par abhi pakka nahi — rollout chalne do" % ", ".join(
                un_phrase(k, allr[k]) for k in _rank(un, allr)[:3])
        elif not any(allr[k]["status"] in JUDGED for k in keys):
            out["why"] = "Abhi koi number parkha nahi ja saka (data kam ya nahi) — rollout chalne do"
        else:
            out["why"] = "Koi pakka farak nahi — rollout chalne do"
    return out


def _judged_plain(key, row):
    """(the judged change, the plain before → after one) of a row judged on something else than its plain change —
    Returning DAU (vs expected), sessions / time (net of the trend) — else (None, None)."""
    if key == "returning_dau":
        return row["change"], row["extra"].get("raw_change")
    if key in ("sessions", "time") and row.get("basis") != "plain":
        return _eff(key, row), row["change"]
    return None, None


def _plain_too(key, row, fmt=" (pehle se %s %s)"):
    """" (pehle se 11% zyada)" when a row's judged change and its plain before → after point opposite ways (a DAU
    "expected se 8% kam" that rose, sessions "8% kam" net of a trend while the number went up), else ""."""
    e, p = _judged_plain(key, row)
    if e and p and abs(p) >= 0.005 and (e < 0) != (p < 0):
        return fmt % (_pct(p, 0), _dir(p, "zyada", "kam"))
    return ""


def un_phrase(key, row):
    """A Maybe row in the CONTINUE why line: short_phrase — but one whose judged change points the other way from its
    plain before → after says both: "DAU expected se 8% kam par pehle se 11% zyada" (a bare "DAU −8%" reads as a
    fall)."""
    pt = _plain_too(key, row, " par pehle se %s %s")
    if pt:
        e = _judged_plain(key, row)[0]
        what = "DAU expected se" if key == "returning_dau" else "%s per user normal trend hata ke" % key
        return "%s %s %s%s" % (what, _pct(e, 0), _dir(e, "zyada", "kam"), pt)
    return short_phrase(key, row)


def _rank(keys, allr):
    """Primary rows first, then the biggest effect ÷ minimum."""
    return sorted(keys, key=lambda k: (k not in PRIMARY, -allr[k].get("_ratio", 0), (ROWS_LONG + VROWS).index(k)))


def alert_text(blk, level, rows_all, keys, early, E):
    """The Hinglish message (without "{app}: "; alert_obj adds the estimate / provisional notes)."""
    ks = _rank(keys, rows_all)
    head = head_phrase(ks[0], rows_all[ks[0]], blk["_cx"])
    more = ""
    if len(ks) > 1:
        more = " · aur %d cheez%s %s: %s" % (len(ks) - 1, "ein" if len(ks) > 2 else "",
                                            "behtar" if level == "win" else "kharab",
                                            ", ".join(short_phrase(k, rows_all[k]) for k in ks[1:]))
    text = "%s (%s) ke baad %s%s · %s" % (blk["label"], U.fmt_day(blk["R"], E), head, more, ACT[level])
    if early and level in ("hold", "halt"):
        text += " · shuruaati — 7 din ka result abhi baaki"
    return text, ks[0]


# ── the installs vs per-user split of each judged row (SPEC_SPLIT F2 / F4 / F6) ───────────────────

def _split_rows(cx, rows, N):
    """Each JUDGED row's split wire "sp" from the sums the row already kept ("_spx"; dropped with the other "_" keys by
    _round_row) — returning DAU: expected − before = the installs' part + the rest the expected level already held
    (["imp", fi, tr(, nb, na)]): fi = Σ(recent(d) − recent(b)) ÷ n — the pair days' installs moving at the SAME ρ̂
    (pure volume) — and tr = the old users' usual trend + the before days' measured recent returners vs ρ̂ (Σ recent(b)
    − Σ Y(b): not installs moving); nb / na = the installs a day feeding them, ρ̂-weighted (fi = (na − nb) · Σρ̂), on the
    7-day rows only. Install-day uninstall: ["ur", installs / day before / after], ad revenue per user (7 days only):
    ["rev", active users / day before / after(, the new-user share when it moved)]. Low / na / pending rows get none —
    except a returning-DAU row on a trend too steep to extrapolate (Low data): ["no", "steep_up" | "steep_dn"] says why
    it has none. Read-only: no status, number or verdict reads it."""
    for key, row in rows.items():
        x = row.get("_spx")
        if not x:
            continue
        if x[0] == "steep":
            if row.get("status") == "low":
                sp = attrib.safe(attrib.no, "steep_up" if x[1] > 0 else "steep_dn")
                if sp is not None:
                    row["sp"] = sp
            continue
        if row.get("status") not in JUDGED:
            continue
        if x[0] == "raw":
            sp = attrib.safe(attrib.no, "cohorts")
        elif x[0] == "dau":
            def build(x=x):
                _, src, srcb, syb, stt, n, srho = x
                nb = na = None
                if N == WIN_DAYS and srho > 0:
                    nb, na = srcb / n / srho, src / n / srho
                return attrib.imp((src - srcb) / n, (stt + srcb - syb) / n, nb, na)
            sp = attrib.safe(build)
        elif x[0] == "ur":
            sp = attrib.safe(lambda x=x: attrib.rate("ur", x[1] / x[2], x[3] / x[4]))
        elif x[0] == "rev" and N == WIN_DAYS:
            def build(x=x):
                _, ub, ua, ns_b, ns_a = x
                notes = ([("new", ns_b, ns_a)] if ns_a is not None and ns_b is not None
                         and abs(ns_a - ns_b) > NEWSHARE_SWING else [])
                return attrib.rev(ub, ua, notes)
            sp = attrib.safe(build)
        else:
            sp = None
        if sp is not None:
            row["sp"] = sp


# ── one app ──────────────────────────────────────────────────────────────────────────────────────

def _round_row(row):
    dp = DP[row["unit"]]
    for k in ("before", "after", "expected", "after_prov"):
        if row[k] is not None:
            row[k] = int(round(row[k])) if dp == 0 else _rd(row[k], dp)
    if row["change"] is not None:
        row["change"] = _rd(row["change"], 2 if row["change_unit"] == "pp" else 4)
    if row["z"] is not None:
        row["z"] = _rd(row["z"], 2)
    for k in ("noise", "need"):                      # in the change's unit: log ≈ rel (4 dp) or points (2 dp)
        if row.get(k) is not None:
            row[k] = _rd(row[k], 2 if row["change_unit"] == "pp" else 4)
    ex = row["extra"]
    for k, v in list(ex.items()):
        if isinstance(v, float):
            ex[k] = _rd(v, 5)
    for k in [k for k in row if k.startswith("_")]:
        row.pop(k)
    return row


def _rd(v, dp):
    """round(), never "-0.0"."""
    return round(v, dp) + 0.0


def _round_vrow(row):
    for k in ("old", "new"):
        if row[k] is not None:
            row[k] = _rd(row[k], 3)
    for k in ("diff", "adj", "bias"):
        if row[k] is not None:
            row[k] = _rd(row[k], 4)
    if row["z"] is not None:
        row["z"] = _rd(row["z"], 2)
    for k in [k for k in row if k.startswith("_")]:
        row.pop(k)
    return row


def block_rows(cx, blk, blocks, j, done):
    """Block j's 7-day window (blk["win"]) and raw rows → (rows, the version table) — impact_app's, shared with
    engine.impact_any (a chosen date as a pseudo-block: the same rows, nothing re-derived). done = the blocks
    evaluated before it (the version table's usual early-updater gap)."""
    blk["_cx"] = cx
    windows(cx, blk, blocks, j)
    win = blk["win"]
    if blk["R"] < cx["launch"] + timedelta(days=7):
        blk["_na"] = NA_YOUNG
    elif len(win["days_a"]) < IMPACT_MIN_DAYS:
        blk["_na"] = NA_CUT
    rows = {}
    if blk.get("_na"):
        rows = {k: _na(_row(k), blk["_na"]) for k in ROWS}
        vc = ver_rows(cx, blk, done)
        for r in vc["rows"].values():
            _na(r, blk["_na"] if blk["kind"] == "version" else NA_NO_VER)
    else:
        rows["returning_dau"] = dau_row(cx, blk)
        rows["new_d1"], rows["new_d7"] = ret_row(cx, blk, 1), ret_row(cx, blk, 7)
        rows["sessions"], rows["time"] = use_row(cx, blk, "sessions"), use_row(cx, blk, "time")
        rows["arpdau"] = arpdau_row(cx, blk)
        rows["uninstall_d0"] = d0_row(cx, blk)
        vc = ver_rows(cx, blk, done)
    return rows, vc


def impact_app(store, ds, cd, whole, i0, rels, revenue, state, app_id, E, late, first, advanced, outdated, now,
               windows_on=True):
    """One app's update impact → (detail["impact"], summary["updates"], ready conditions for update_impact_episodes —
    and, family "impact_late", at most ONE for update_late_episodes). Keeps its per-row persistence in
    state["eval"][app_id]["impact"] (in place; the late condition's streak and LATE_V there too). `first` / `advanced`
    = the uninstall evaluation's (first ever / E moved on); a first evaluation WITH impact data, or an outdated store,
    seeds what it shows (never sent). windows_on (config IMPACT_WINDOWS): the 14 / 30 / 60-day windows (by_window), the
    late family and every row's noise — off: exactly the v1 card (noise / need null)."""
    E = _d(E)
    cx = _context(store, cd, whole, i0, revenue, E, late)
    cx["_noise_all"] = bool(windows_on)
    blocks = make_blocks(rels, cx["launch"])
    ev = state.setdefault("eval", {}).setdefault(app_id, {})
    prev = ev.get("impact") or {}
    fresh = not prev.get("data")
    seed = fresh or bool(outdated) or not cx["has_data"]
    pblocks = prev.get("blocks") or {}
    keep_state, conds, done = {}, [], []
    for j, blk in enumerate(blocks):
        rows, vc = block_rows(cx, blk, blocks, j, done)
        win = blk["win"]
        done.append(blk)
        vrows = vc["rows"]
        if not windows_on:                            # (the flag off: today's card exactly — no noise line)
            for r in rows.values():
                r["noise"] = r["need"] = None
        final_pre = (bool(win["days_a"]) and len(win["settled"]) == len(win["days_a"])
                     and rows["new_d7"]["status"] != "pending")
        prow = (pblocks.get(blk["key"]) or {}).get("rows") or {}
        kept = persist(dict(rows, **vrows), prow, advanced, final_pre, fresh)
        vd = verdict(blk, rows, vrows, cx)
        if not vd["final"] and blk["R"] >= E - timedelta(days=IMPACT_ALERT_DAYS):
            keep_state[blk["key"]] = {"rows": kept}
        notes = _notes(cx, blk, rows, vrows)
        allr = dict(rows, **vrows)
        level = vd["level"]
        head = None
        # the update's one-line change: a worse / better row only — never a Normal / Maybe / Low data one — and the
        # change it was JUDGED on (_eff: sessions / time net of the trend, ad revenue on ads per user; the plain change
        # of a per-user row can point the other way)
        hk = _rank(vd["worse"], allr)[0] if vd["worse"] else _rank(vd["better"], allr)[0] if vd["better"] else None
        if hk is not None:
            r = allr[hk]
            ch, unit = (r["adj"], "rel") if hk in VROWS else (_eff(hk, r), r["change_unit"])
            head = {"row": hk, "change": _rd(ch, 2 if unit == "pp" else 4), "unit": unit}
        if level in ("halt", "hold", "win") and blk["R"] >= E - timedelta(days=IMPACT_ALERT_DAYS):
            keys = vd["better"] if level == "win" else vd["worse"]
            conds.append(_cond(app_id, blk, level, allr, keys, vd, seed, E, rows))
        _split_rows(cx, rows, WIN_DAYS)
        blk["_out"] = {"key": blk["key"], "rel_keys": blk["rel_keys"], "kind": blk["kind"], "versions": blk["versions"],
                       "label": blk["label"], "date": _iso(blk["R"]),
                       "adoption": _adopt_out(blk),
                       "windows": _win_out(blk),
                       "rows": {k: _round_row(rows[k]) for k in ROWS},
                       "versions_cmp": dict(vc, rows={k: _round_vrow(vrows[k]) for k in VROWS}),
                       "verdict": vd, "notes": notes, "alert_id": None}
        blk["_head"] = head
        blk["_vd7"] = vd
    late_state, late_cands, late_ok, failed = None, [], False, 0
    if windows_on:                                   # the 14 / 30 / 60-day windows: failure-isolated per block AND
        late_fail = False                            # window — a crash costs that window, never the block's other
        for j, blk in enumerate(blocks):             # windows or its 7 days (counted: flags.windows_failed, the log)
            blk["_out"].update(default_window=WIN_DAYS, late=None)
            bw, cand = {}, None
            for N in WINDOWS[1:]:
                try:
                    W, c = _long_window(cx, blk, blocks, j, N, state, app_id, E)
                except Exception:
                    failed += 1
                    late_fail = late_fail or N == LATE_WINDOW
                    continue
                bw[str(N)] = W
                cand = c or cand
            if bw:
                blk["_out"]["by_window"] = bw
            if cand is not None:
                late_cands.append(cand)
                blk["_out"]["late"] = {"level": cand["level"], "alert_id": None, "seeded": False}
        try:
            late_state, lc = _late_pick(app_id, late_cands, prev, seed, advanced, E)
            if lc is not None:
                conds.append(lc)
                for blk in blocks:
                    if blk["_out"].get("late"):
                        blk["_out"]["late"]["seeded"] = bool(lc["seed"])
            late_ok = True
        except Exception:
            failed += 1
            late_ok = False
        # a 30-day window that failed may hide a late condition: LATE_V is written only by a run that saw them all
        # (else a crash on the first run after the merge would mark seeding done with nothing seeded — and send the
        # historical conditions once fixed)
        late_ok = late_ok and not late_fail
    ev["impact"] = {"data": bool(cx["has_data"] or prev.get("data")), "blocks": dict(sorted(keep_state.items()))}
    if windows_on and late_ok:
        ev["impact"]["late_v"] = LATE_V
        if late_state:
            ev["impact"]["late"] = late_state
    elif windows_on:                                 # (a failure: the late family's state carried unchanged)
        for k in ("late", "late_v"):
            if k in prev:
                ev["impact"][k] = prev[k]
    updates = []
    for blk in reversed(blocks):                     # (+ an older update whose late condition holds: its ⏰ chip —
        if blk["R"] >= E - timedelta(days=IMPACT_LIST_DAYS) or blk["_out"].get("late"):   # up to LATE_ALERT_DAYS)
            vd = blk["_out"]["verdict"]
            u = {"key": blk["key"], "label": blk["label"], "date": _iso(blk["R"]), "level": vd["level"],
                 "early": vd["early"], "final": vd["final"],
                 "adoption": blk["_out"]["adoption"]["last"], "head": blk["_head"],
                 "judged": sum(r["status"] in JUDGED for r in list(blk["_out"]["rows"].values())
                               + list(blk["_out"]["versions_cmp"]["rows"].values()))}
            if windows_on:
                lt = blk["_out"].get("late")
                u["late"] = {"level": lt["level"], "alert_id": None} if lt else None
            updates.append(u)
    rf = store.get("ret_from")
    rev = "none" if cx["rev"] is None else "ok"
    if cx["rev"] is not None:
        span = [d for d in _days(max(cx["launch"], E - timedelta(days=PRE_DAYS + 30)), cx["S_act"])]
        if any(cx["rev"](d) is None for d in span):
            rev = "partial"
    detail = {"v": 2 if windows_on else 1, "updates": [b["_out"] for b in reversed(blocks)],
              "flags": {"ret_from": rf, "vuse_split": cx["split"], "revenue": rev, "tz_blend": cx["tz_blend"],
                        "usage_from": cx["usage_from"]}}
    if failed:                                       # (only then: the page and the log say it; counts only)
        detail["flags"]["windows_failed"] = failed
    return detail, updates, conds


# ── the 14 / 30 / 60-day windows (spec SPEC_WINDOWS §2–§4) ──────────────────────────────────────────

def _state(win, N, E):
    """A long window's (state, judged_on, final_on): judged once D7 of its last install day is settled (end_a + 10),
    final once D30 is too at 30 / 60 (end_a + 33) — data days."""
    judged_on = win["end_a"] + timedelta(days=ACT_LATE_DAYS + JUDGE_D)
    final_on = judged_on if N < LATE_WINDOW else win["end_a"] + timedelta(days=30 + ACT_LATE_DAYS)
    return ("running" if E < judged_on else "judged" if E < final_on else "final"), judged_on, final_on


def _running_row(cx, wb, key, ready):
    """A row of a window still running: pending until `ready`, with the full Before value and the settled After days so
    far (after_prov, shown faded) — no change, no z, no test."""
    row, win, R = _row(key), wb["win"], wb["R"]
    if key in ("sessions", "time", "arpdau"):
        row["basis"] = "plain" if win["n"] > PU_TREND_MAX_N else "expected"
    b_days, a_days = _days(win["b0"], win["b1"]), win["settled"]

    def pool(days, num, den):
        n = [num(d) for d in days]
        dn = [den(d) for d in days]
        ok = [(x, y) for x, y in zip(n, dn) if x is not None and y]
        return sum(x for x, _ in ok) / sum(y for _, y in ok) if ok else None
    if key == "returning_dau":
        rb = [x for x in (_ret_dau(cx, d) for d in b_days) if x is not None]
        ra = [x for x in (_ret_dau(cx, d) for d in a_days) if x is not None]
        row.update(before=_mean(rb), after_prov=_mean(ra))
    elif key in ("new_d1", "new_d7", "new_d30"):
        k = {"new_d1": 1, "new_d7": 7, "new_d30": 30}[key]
        rf, okc = cx["ret_from"], _okc_fn(cx, k)
        cb = _days(R - timedelta(days=win["n"] + k), R - timedelta(days=1 + k))
        if rf is not None and cb and min(cb) < rf:
            return _na(row, NA_OLD)
        ca = [c for c in win["days_a"] if c + timedelta(days=k) <= cx["S_act"]]
        vb, va = [okc(c) for c in cb], [okc(c) for c in ca]
        vb, va = [x for x in vb if x], [x for x in va if x]
        row.update(before=sum(x for x, _ in vb) / sum(n for _, n in vb) if vb else None,
                   after_prov=sum(x for x, _ in va) / sum(n for _, n in va) if va else None)
        if key == "new_d30":
            ready = win["end_a"] + timedelta(days=30 + ACT_LATE_DAYS)
    elif key in ("sessions", "time"):
        if not cx["usage"]:
            return _na(row, NA_NO_USAGE)
        j = 1 if key == "sessions" else 2

        def slot(d):
            return ((cx["usage"].get(d.isoformat()) or {}).get("r")) or None
        row.update(before=pool(b_days, lambda d: (slot(d) or [0, 0, 0])[j], lambda d: (slot(d) or [0, 0, 0])[0]),
                   after_prov=pool(a_days, lambda d: (slot(d) or [0, 0, 0])[j], lambda d: (slot(d) or [0, 0, 0])[0]))
    elif key == "arpdau":
        f = cx["rev"]
        if f is None:
            return _na(row, NA_NO_REV)
        row["extra"].update(tz_blend=cx["tz_blend"], currency=cx["currency"])

        def rv(d):
            v = f(d)
            return v[0] * 1000 if v and _dv(cx, d, "a1") else None
        row.update(before=pool(b_days, rv, lambda d: _dv(cx, d, "a1") or 0),
                   after_prov=pool(a_days, rv, lambda d: _dv(cx, d, "a1") or 0))
    elif key == "uninstall_d0":
        cell = _d0_cell_fn(cx)
        vb = [x for x in (cell(c) for c in b_days) if x]
        va = [x for x in (cell(c) for c in win["days_a"] if c <= cx["S_un"]) if x]
        row.update(before=sum(x for x, _ in vb) / sum(n for _, n in vb) if vb else None,
                   after_prov=sum(x for x, _ in va) / sum(n for _, n in va) if va else None)
    return _pending(row, win, ready)


def _told_of(state, app_id, b):
    """The rows the 7-day verdict / alert already told for update b: its current 7-day HOLD / HALT's worse rows + the
    worse rows of every "impact" episode (open or closed) of the same update (_same_update, dir up)."""
    t = set()
    vd = b.get("_vd7")
    if vd and vd["level"] in ("hold", "halt"):
        t.update(vd["worse"])
    c = {"dir": "up", "kind": b["kind"], "vers": list(b["versions"]), "R": _iso(b["R"])}
    for e in list((state.get("episodes") or {}).values()) + list(state.get("closed") or []):
        if e.get("app_id") == app_id and _same_update(e, c):
            t.update(((e.get("last") or {}).get("rows") or {}).get("worse") or [])
    return t


# extra keys the page never reads (the 7-day rows keep them all): left out of the 14 / 30 / 60-day rows (size — live
# by_window averaged 9.3 KB a block, over the spec's estimate; the contract fills a missing extra key back as null)
EXTRA_UNREAD = ("k_days", "expected_model", "phi", "imp_before", "est")
# a 14 / 30 / 60-day row's basis by its unit when left out (the page and the contract fill it back): D1 / D7 / D30 /
# install day "rate", returning DAU "expected" (its trend capped; "plain" only on a steep trend — then kept), the
# per-user rows "plain" (PU_TREND_MAX_N)
BASIS_LONG = {"pct": "rate", "users": "expected", "num": "plain", "sec": "plain", "usd1k": "plain"}


def _sparse(row, W):
    """A long-window row without what the page fills back (uniImpNorm): null / false / "" / {} / [] values, raw_status
    = status, unit / change_unit (they follow the key), streak (always 0), from / to equal to the window's own, the
    basis when it is the window's default for the row (BASIS_LONG), and the extra keys the page never reads
    (EXTRA_UNREAD)."""
    out = {}
    for k, v in row.items():
        if k in ("unit", "change_unit", "streak") or (k == "raw_status" and v == row["status"]):
            continue
        if k == "basis" and v == BASIS_LONG.get(row.get("unit")):
            continue                                 # (its window's default: rate / plain per-user / DAU expected)
        if k == "extra":
            v = {x: y for x, y in v.items() if y is not None and x not in EXTRA_UNREAD}
        if v is None or v is False or (isinstance(v, (str, list, dict)) and not v):
            continue
        if (k, v) in (("from_a", W["after"]["from"]), ("to_a", W["after"]["to"]), ("from_b", W["before"]["from"]),
                      ("to_b", W["before"]["to"])):
            continue
        out[k] = v
    return out


def _mixed_why(n):
    return " · mila-jula (beech me %d aur update%s)" % (n, "s" if n > 1 else "")


def _long_window(cx, blk, blocks, j, N, state, app_id, E):
    """One block's N-day window (N ≥ LONG_MIN) → (W for by_window[str(N)], the late candidate (N = LATE_WINDOW only) or
    None). Pure for the block: the 7-day block and its win are never touched (a shallow copy shares only the memos)."""
    win = windows(cx, blk, blocks, j, N)
    blk.setdefault("_m", {})                         # (the memos: shared by the block's windows, even without 7 days)
    wb = dict(blk, win=win, _mix=None, _na=None)
    R = blk["R"]
    st, judged_on, final_on = _state(win, N, E)
    keys = ROWS_LONG if N >= LATE_WINDOW else ROWS
    young = R - timedelta(days=N) < cx["launch"]
    rows, vd, cand = {}, None, None
    if young:
        why = NA_YOUNG_N % (N, N)
        rows = {k: _na(_row(k), why) for k in keys}
        for k in ("sessions", "time", "arpdau"):
            rows[k]["basis"] = "plain"
        vd = {"level": None, "early": st != "final", "final": st == "final", "why": why, "worse": [], "better": [],
              "pending": [], "ready_on": None, "settled_days": len(win["settled"]), "min_days": IMPACT_MIN_DAYS}
    elif st == "running":
        rows = {k: _running_row(cx, wb, k, judged_on) for k in keys}
        lag = timedelta(days=U.LAG_DAYS)
        why = "%d din poore ~%s ko · faisla ~%s ko" % (N, U.fmt_day(win["end_a"], E), U.fmt_day(judged_on + lag, E))
        vd = {"level": None, "early": True, "final": False, "why": why, "worse": [], "better": [],
              "pending": [k for k in keys if rows[k]["status"] == "pending"], "ready_on": _iso(judged_on),
              "settled_days": len(win["settled"]), "min_days": IMPACT_MIN_DAYS}
    else:
        rows["returning_dau"] = dau_row(cx, wb)
        rows["new_d1"], rows["new_d7"] = ret_row(cx, wb, 1), ret_row(cx, wb, 7)
        if N >= LATE_WINDOW:
            rows["new_d30"] = ret_row(cx, wb, 30)
        rows["sessions"], rows["time"] = use_row(cx, wb, "sessions"), use_row(cx, wb, "time")
        rows["arpdau"] = arpdau_row(cx, wb)
        rows["uninstall_d0"] = d0_long(cx, wb)
        rows = {k: rows[k] for k in keys}
        vd = verdict(wb, rows, {}, cx, final=st == "final")
        if win["mixed"]:
            vd["why"] += _mixed_why(len(win["mixed"]))
    told, told_by, late = [], {}, None
    if not young and st != "running" and vd["worse"]:
        own = _told_of(state, app_id, blk)
        by = {}
        # the updates released inside this window (mixed) — and inside its Before (mixed_before): an earlier update's
        # drop that started there makes this After read worse than this Before, already told by THAT update
        for x in [x for x in blocks[j + 1:] if x["R"] <= win["end_a"]] + \
                [x for x in blocks[:j] if win["b0"] <= x["R"] <= win["b1"]]:
            for k in _told_of(state, app_id, x) - own:
                by.setdefault(k, x["label"])
        told = [k for k in vd["worse"] if k in own or k in by]
        told_by = {k: by[k] for k in told if k not in own}
        if N == LATE_WINDOW:
            masked = {k: dict(r, status="same") if k in told else r for k, r in rows.items()}
            lv = verdict(wb, masked, {}, cx, final=st == "final")["level"]
            late = lv if lv in ("hold", "halt") else None
    vd.update(n=N, state=st, mixed=bool(win["mixed"]), told=told, late=late)
    if told_by:
        vd["told_by"] = told_by
    if late and R >= E - timedelta(days=LATE_ALERT_DAYS):
        cand = _late_cand(app_id, blk, wb, rows, vd, E)
    notes = set(_notes(cx, wb, rows, {}))
    if win["mixed"]:
        notes.add("mixed")
    if win["mixed_before"]:
        notes.add("mixed_before")
    dau = rows["returning_dau"]
    if dau.get("_capped") or (st == "running" and not young and N >= LATE_WINDOW):
        notes.add("trend_capped")
    if any(rows[k]["basis"] == "plain" and rows[k]["status"] != "na" for k in ("sessions", "time", "arpdau")):
        notes.add("plain")
    if any(r["status"] == "low" and is_hist(r.get("reason")) for r in rows.values()):
        notes.add("young")                           # (the history really short — never data gaps: LOW_NULL_GAP)
    W = {"n": N, "state": st,
         "before": {"from": _iso(win["b0"]), "to": _iso(win["b1"]), "days": N},
         "after": {"from": _iso(win["a0"]), "to": _iso(win["end_a"]), "days": len(win["days_a"]),
                   "settled": len(win["settled"]),
                   "settled_till": _iso(win["settled"][-1]) if win["settled"] else None,
                   "judged_on": _iso(judged_on), "final_on": _iso(final_on)},
         "mixed": win["mixed"], "mixed_before": win["mixed_before"],
         "adoption_mean": None if win["adopt_mean"] is None else round(win["adopt_mean"], 5)}
    _split_rows(cx, rows, N)
    W.update(rows={k: _sparse(_round_row(rows[k]), W) for k in keys}, verdict=vd,
             notes=[n for n in NOTES_LONG if n in notes])
    return W, cand


def _late_cand(app_id, blk, wb, rows, vd, E):
    """A block whose 30-day verdict, told rows masked, is still HOLD / HALT → its late condition (everything the alert
    object and the text are built from; built before the rows are rounded, like _cond)."""
    level, win = vd["late"], wb["win"]
    untold = [k for k in vd["worse"] if k not in vd["told"]]
    ks = _rank(untold, rows)
    hk = ks[0]
    r = rows[hk]
    if r["change_unit"] == "pp":
        now, before, dpp = r["after"], r["before"], r["change"]
        rel = (r["after"] / r["before"] - 1) if r["before"] else 0.0
    else:
        now, before = r["after"], r["expected"] if hk == "returning_dau" else r["before"]
        rel, dpp = _eff(hk, r), None
    return {"key": "%s|impact_late" % app_id, "family": "impact_late", "dir": "up", "vers": list(blk["versions"]),
            "kind": blk["kind"], "severity": SEVERITY[level], "level": level, "block": blk["key"],
            "text": late_text(blk, level, rows, ks, win, vd["final"], E), "now": now, "before": before, "rel": rel,
            "delta_pp": dpp, "z": r["z"], "installs_from": _iso(win["a0"]), "installs_to": _iso(win["end_a"]),
            "base_from": _iso(win["b0"]), "base_to": _iso(win["b1"]), "since": _iso(blk["R"]), "day": None,
            "users": int(round(rows["returning_dau"]["after"] or 0)), "checkpoint": None, "n": None, "also": [],
            "vs": [], "prov": False, "est": bool(hk == "uninstall_d0" and r["est"]),
            "release": {"key": blk["key"], "label": blk["label"], "date": _iso(blk["R"])},
            "rows": {"worse": untold, "told": list(vd["told"])}, "mixed": [m["label"] for m in win["mixed"]],
            "window": LATE_WINDOW, "seed": False, "R": _iso(blk["R"])}


def late_text(blk, level, rows, ks, win, final, E):
    """The late alert's Hinglish message (without "{app}: "): "<label> (<day>) ke 30 din baad <head> · pehle 7 din me
    ye nahi dikha tha … · <ACT>"."""
    head = head_phrase(ks[0], rows[ks[0]], blk["_cx"], n=win["n"])
    more = ""
    if len(ks) > 1:
        more = " · aur %d cheez%s kharab: %s" % (len(ks) - 1, "ein" if len(ks) > 2 else "",
                                                ", ".join(short_phrase(k, rows[k]) for k in ks[1:]))
    mixed = ""
    if win["mixed"]:
        n = len(win["mixed"])
        mixed = " · beech me %d aur update%s (%s) — asar mila-jula ho sakta hai" % (
            n, "s" if n > 1 else "", ", ".join(m["label"] for m in win["mixed"]))
    text = "%s (%s) ke %d din baad %s%s · pehle 7 din me ye nahi dikha tha%s · %s" % (
        blk["label"], U.fmt_day(blk["R"], E), win["n"], head, more, mixed, ACT[level])
    if not final:
        text += " · 30 din ka result abhi baaki"
    return text


def _late_pick(app_id, cands, prev, seed, advanced, E):
    """This evaluation's late candidates → (the late state to keep, the ONE ready condition or None): the highest level,
    then the oldest update (its window holds the later ones; the others go in `also`); ready once it held on
    LATE_PERSIST daily evaluations (hourly re-runs never advance it), or at once when seeded (the app's first impact
    evaluation, an outdated store, or the first evaluation without LATE_V). The app's ONE late condition goes on while
    it holds at the same or a lower level — also when the chosen block changes (the older update aged out of
    LATE_ALERT_DAYS while a newer one holds the same drop): its streak carries, so the open episode is refreshed (the
    snapshot moves), never closed and re-opened under the newer update's name. Only a rise (HOLD → HALT) starts over."""
    if not cands:
        return None, None
    cands = sorted(cands, key=lambda c: (-LEVEL_RANK[c["level"]], c["R"]))
    c = dict(cands[0], also=[x["release"]["label"] for x in cands[1:]])
    pl = prev.get("late") or {}
    same = bool(pl.get("block")) and pl.get("level") in LEVEL_RANK and LEVEL_RANK[c["level"]] <= LEVEL_RANK[pl["level"]]
    streak = (int(pl.get("streak") or 0) + 1 if advanced else max(1, int(pl.get("streak") or 0))) if same else 1
    lseed = bool(seed) or prev.get("late_v") != LATE_V
    c["seed"] = lseed
    return {"block": c["block"], "level": c["level"], "streak": streak}, (c if streak >= LATE_PERSIST or lseed else None)


def _adopt_out(blk):
    A, win = blk["A"], blk["win"]
    days = sorted(A)
    last = [A[d] for d in win["avail"] if d in A] or [A[d] for d in days]
    return {"days": [_iso(d) for d in days], "share": [round(A[d], 5) for d in days],
            "at_start": round(A[win["a0"]], 5) if win["a0"] in A else None,
            "mean": None if win["adopt_mean"] is None else round(win["adopt_mean"], 5),
            "last": round(last[-1], 5) if last else None, "slow": bool(win["slow"])}


def _win_out(blk):
    win = blk["win"]
    ov = win["overlap"]
    return {"before": {"from": _iso(win["b0"]), "to": _iso(win["b1"])},
            "after": {"from": _iso(win["a0"]), "to": _iso(win["end_a"]), "days": len(win["days_a"]),
                      "settled": len(win["settled"]), "settled_till": _iso(win["settled"][-1]) if win["settled"] else None,
                      "cut_by": win["cut_by"]},
            "pre_from": _iso(blk["R"] - timedelta(days=PRE_DAYS)),
            "overlap_before": {"key": ov["key"], "label": ov["label"], "date": _iso(ov["R"])} if ov else None}


def _notes(cx, blk, rows, vrows):
    win, out = blk["win"], set()
    if rows["new_d1"].get("_swing") or rows["new_d7"].get("_swing"):
        out.add("installs_swing")
    if any(r.get("_mixed") for r in list(rows.values()) + list(vrows.values())):
        out.add("installs_swing")
    if rows["arpdau"].get("_swing"):
        out.add("newshare_swing")
    if win["adopt_mean"] is not None and win["adopt_mean"] < ADOPT_LOW:
        out.add("diluted")
    if win["slow"]:
        out.add("slow_rollout")
    if rows["returning_dau"]["extra"].get("mode") == "raw":
        out.add("no_cohorts")
    if cx["rev"] is None:
        out.add("no_revenue")
    if cx["tz_blend"]:
        out.add("tz_blend")
    if win["overlap"]:
        out.add("before_overlap")
    if win["cut_by"]:
        out.add("cut_by_next")
    if any(r["prov"] or r["after_prov"] is not None for r in rows.values()):
        out.add("prov")
    if any(r["est"] for r in rows.values()):
        out.add("est")
    if cx["thresholded"]:
        out.add("thresholded")
    return [n for n in NOTES if n in out]


def _cond(app_id, blk, level, allr, keys, vd, seed, E, rows):
    """A block's level → the condition update_impact_episodes keeps (everything its alert object is built from)."""
    text, hk = alert_text(blk, level, allr, keys, vd["early"], E)
    r = allr[hk]
    if hk in VROWS:
        now, before, rel, dpp = r["new"] or 0.0, r["old"] or 0.0, r["adj"] or 0.0, None
    elif r["change_unit"] == "pp":
        now, before, dpp = r["after"], r["before"], r["change"]
        rel = (r["after"] / r["before"] - 1) if r["before"] else 0.0
    else:                                             # rel: the change it was judged on (like the headline)
        now, before = r["after"], r["expected"] if hk == "returning_dau" else r["before"]
        rel, dpp = _eff(hk, r), None
    bad = level in ("hold", "halt")
    dau = rows["returning_dau"]
    win = blk["win"]
    return {"key": "%s|%s|%s" % (app_id, "impact" if bad else "impact_win", _ident(blk["kind"], blk["versions"], blk["key"])),
            "family": "impact", "vers": list(blk["versions"]), "kind": blk["kind"],
            "dir": "up" if bad else "down", "severity": SEVERITY[level], "level": level, "block": blk["key"],
            "text": text, "now": now, "before": before, "rel": rel, "delta_pp": dpp, "z": r["z"],
            "installs_from": _iso(win["a0"]), "installs_to": _iso(min(win["end_a"], E)),
            "base_from": _iso(win["b0"]), "base_to": _iso(win["b1"]), "since": _iso(blk["R"]), "day": None,
            "users": int(round(dau["after"] or 0)), "checkpoint": None, "n": None, "also": [], "vs": [],
            "prov": bool(bad and hk == "uninstall_d0" and r["prov"]), "est": bool(hk == "uninstall_d0" and r["est"]),
            "release": {"key": blk["key"], "label": blk["label"], "date": _iso(blk["R"])},
            "rows": {"worse": list(vd["worse"]), "better": list(vd["better"])}, "seed": bool(seed),
            "R": _iso(blk["R"])}


def _ident(kind, vers, key):
    """An update's identity for its alert episode: its first version ("ver:<v>") — the day it first reached 5% of the
    users can move by a day as late data lands; an update surge without a version: its key."""
    return "ver:%s" % vers[0] if kind == "version" and vers else key


def _same_update(e, c):
    """Is episode e (open or closed) about the same update as condition c? The same direction and a version in common
    (a hotfix chain that grew or merged), or — a surge without a version — dates ≤ CHAIN_DAYS apart."""
    if e.get("family") != "impact" or e.get("dir") != c["dir"]:
        return False
    if c["kind"] == "version":
        return bool(set(e.get("vers") or ()) & set(c["vers"]))
    R = (e.get("last") or {}).get("R")
    return e.get("kind") == "update" and bool(R) and abs((_d(R) - _d(c["R"])).days) <= CHAIN_DAYS


def _superseded(ep, releases):
    """Did a newer update of the app come out after this impact episode's own? releases = the app's updates known to
    this evaluation ([{key, date, versions}], detail["impact"]["updates"]); its own block (same key or a version in
    common) never counts. → its close_reason: "superseded", else "recovered" (shown only — nothing decides on it)."""
    last = ep.get("last") or {}
    R = last.get("R") or (last.get("release") or {}).get("date")
    if not R:
        return "recovered"
    own = {str(v) for v in (ep.get("vers") or last.get("vers") or []) if v is not None}
    for u in releases or ():
        if (u.get("date") and u["date"] > R and u.get("key") != ep.get("block")
                and not own & {str(v) for v in (u.get("versions") or []) if v is not None}):
            return "superseded"
    return "recovered"


def update_impact_episodes(state, app_id, E, conds, advanced, now, releases=None):
    """Open / refresh / close this app's update-impact episodes (shared state["episodes"] / "closed", so
    mark_notified works unchanged). Pure: it only changes `state`. ONE episode per update and direction, for good: a bad
    block (HOLD / HALT) is "<app>|impact|<update>", a WIN "<app>|impact_win|<update>" (<update> = _ident: its first
    version, so a first-5% day that moves by a day is the same update). id = fingerprint(app, "uninstall_impact", dir,
    "<opened>|<update>|<level>"): HOLD → HALT regenerates it with notified_at None (sent once more); HALT → HOLD never
    re-sends. An update whose episode closed (CLOSE_EVALS daily evaluations without its condition) and comes back takes
    that episode back — same id, nothing re-sent unless it goes above the highest level it reached (peak). A condition
    carrying seed (the app's first impact evaluation, an outdated store) is shown, not sent. An episode closes at once
    (never sent) when its update is older than IMPACT_ALERT_DAYS. → this app's open impact episodes.
    SPEC_SIMPLIFY (shown only): a new episode keeps opened_at = now; a close adds closed_at / close_reason (window_end:
    its update aged out; superseded: a newer update — `releases`, the app's update dates — came out after it; else
    recovered); an episode taken back from closed loses those and keeps its opened_at."""
    eps, closed = state.setdefault("episodes", {}), state.setdefault("closed", [])
    E = _d(E)
    E_iso, hit = E.isoformat(), set()
    for c in conds:
        key, snap = c["key"], U._snap(c)
        lvl, ident = c["level"], key.split("|", 2)[2]
        ep = eps.get(key)
        if ep is None:                                # the same update under another key (open), or closed earlier
            old = next((k for k, e in eps.items() if e["app_id"] == app_id and k not in hit and _same_update(e, c)),
                       None)
            if old is not None:
                ep = eps.pop(old)
            else:
                j = next((j for j in range(len(closed) - 1, -1, -1)
                          if closed[j].get("app_id") == app_id and _same_update(closed[j], c)), None)
                if j is not None:
                    ep = U.reopen_ep(closed.pop(j))
            if ep is not None:
                eps[key] = ep
                ep["misses"] = 0
        if ep is None:
            ep = {"id": fingerprint(app_id, "uninstall_impact", None, c["dir"], "%s|%s|%s" % (E_iso, ident, lvl)),
                  "app_id": app_id, "family": "impact", "dir": c["dir"], "opened": E_iso, "last_true": E_iso,
                  "misses": 0, "notified_at": now if c["seed"] else None, "notified_dry": False,
                  "seeded": bool(c["seed"]), "block": c["block"], "vers": list(c["vers"]), "kind": c["kind"],
                  "peak": lvl, "last": snap, "opened_at": now}
            eps[key] = ep
        else:
            ep["last_true"], ep["misses"] = E_iso, 0
            if LEVEL_RANK.get(lvl, 0) > LEVEL_RANK.get(ep.get("peak"), 0):   # HOLD → HALT: sent once more
                ep["peak"] = lvl
                ep["id"] = fingerprint(app_id, "uninstall_impact", None, c["dir"],
                                       "%s|%s|%s" % (ep["opened"], ident, lvl))
                ep["notified_at"] = now if c["seed"] else None
                ep["notified_dry"], ep["seeded"] = False, bool(c["seed"])
            ep["last"], ep["block"] = snap, c["block"]
            ep["vers"] = list(ep.get("vers") or []) + [v for v in c["vers"] if v not in (ep.get("vers") or [])]
            ep["kind"] = c["kind"]
        hit.add(key)
    old_before = E - timedelta(days=IMPACT_ALERT_DAYS)
    for key in [k for k, e in eps.items() if e["app_id"] == app_id and e.get("family") == "impact" and k not in hit]:
        ep = eps[key]
        R = ep["last"].get("R") or ep["last"].get("since")
        if R and _d(R) < old_before:
            closed.append(U.close_ep(eps.pop(key), E_iso, now, "window_end"))
            continue
        if advanced:
            ep["misses"] += 1
            if ep["misses"] >= U.CLOSE_EVALS:
                closed.append(U.close_ep(eps.pop(key), E_iso, now, _superseded(ep, releases)))
    return [e for e in eps.values() if e["app_id"] == app_id and e.get("family") == "impact"]


def update_late_episodes(state, app_id, E, cond, advanced, now, releases=None):
    """Open / refresh / close this app's ONE late-effect episode (family "impact_late", key "<app>|impact_late"; shared
    state["episodes"] / "closed", so mark_notified works unchanged). Pure: it only changes `state`. cond = the ready
    condition (impact_app) or None. id = fingerprint(app, "uninstall_impact_late", dir up, "<opened>|<update>|<level>")
    (<update> = _ident of its block). A newer block's condition refreshes the open episode (the snapshot moves, nothing
    re-sent); HOLD → HALT regenerates the id (sent once more), HALT → HOLD never re-sends. Closes after CLOSE_EVALS
    advanced evaluations without a condition — at once (never sent) when its update is older than LATE_ALERT_DAYS. A
    closed one of the same update comes back (same id, nothing re-sent unless above its peak); another update's is a
    new episode. A seeded condition is shown, never sent. The 7-day family's episodes are never touched (_same_update
    only matches family "impact"). → this app's open late episodes (0 or 1). opened_at / closed_at / close_reason as
    update_impact_episodes (window_end: older than LATE_ALERT_DAYS)."""
    eps, closed = state.setdefault("episodes", {}), state.setdefault("closed", [])
    E = _d(E)
    E_iso = E.isoformat()
    key = "%s|impact_late" % app_id
    ep = eps.get(key)
    if cond is not None:
        snap = U._snap(cond)
        lvl, ident = cond["level"], _ident(cond["kind"], cond["vers"], cond["block"])
        if ep is None:
            j = next((j for j in range(len(closed) - 1, -1, -1)
                      if closed[j].get("app_id") == app_id and closed[j].get("family") == "impact_late"
                      and closed[j].get("ident") == ident), None)
            if j is not None:                        # the same update's late episode comes back: taken back
                ep = U.reopen_ep(closed.pop(j))
                ep["misses"] = 0
                eps[key] = ep
        if ep is None:
            ep = {"id": fingerprint(app_id, "uninstall_impact_late", None, "up", "%s|%s|%s" % (E_iso, ident, lvl)),
                  "app_id": app_id, "family": "impact_late", "dir": "up", "opened": E_iso, "last_true": E_iso,
                  "misses": 0, "notified_at": now if cond["seed"] else None, "notified_dry": False,
                  "seeded": bool(cond["seed"]), "block": cond["block"], "ident": ident, "vers": list(cond["vers"]),
                  "kind": cond["kind"], "peak": lvl, "last": snap, "opened_at": now}
            eps[key] = ep
        else:
            ep["last_true"], ep["misses"] = E_iso, 0
            if LEVEL_RANK.get(lvl, 0) > LEVEL_RANK.get(ep.get("peak"), 0):   # HOLD → HALT: sent once more
                ep["peak"] = lvl
                ep["id"] = fingerprint(app_id, "uninstall_impact_late", None, "up",
                                       "%s|%s|%s" % (ep["opened"], ep.get("ident") or ident, lvl))
                ep["notified_at"] = now if cond["seed"] else None
                ep["notified_dry"], ep["seeded"] = False, bool(cond["seed"])
            ep["last"], ep["block"] = snap, cond["block"]
    elif ep is not None:
        R = (ep.get("last") or {}).get("R")
        if R and _d(R) < E - timedelta(days=LATE_ALERT_DAYS):
            closed.append(U.close_ep(eps.pop(key), E_iso, now, "window_end"))
        elif advanced:
            ep["misses"] += 1
            if ep["misses"] >= U.CLOSE_EVALS:
                closed.append(U.close_ep(eps.pop(key), E_iso, now, _superseded(ep, releases)))
    return [e for e in eps.values() if e["app_id"] == app_id and e.get("family") == "impact_late"]
