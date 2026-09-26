"""Update impact — pure math behind the "📦 Update impact" card of the GA4 Uninstall tab (no I/O, no prints).

For every app update (engine.uninstall.releases: a new appVersion reaching 5% of a day's users, or an app_update surge),
one BLOCK, newest first, with the owner's four must-haves as Before (7 days) | After (7 days) | Change rows, a verdict
(✅ WIN / 👍 CONTINUE / ⚠️ HOLD / 🛑 HALT, or ⏳ Too early) and alerts through the Uninstall tab's episodes:
  1. RETURNING DAU = daily active users − that day's new installs ("purane users ka DAU"), judged against what it would
     have been without the update: the old users' level the same weekday before × their normal weekly change, + the
     recent installs coming back at the PRE-release return rates × the installs that really came (ad spend swings the
     installs — that part is expected, not the update's).
  2. NEW USERS BACK next day (D1) / after 7 days (D7): of the users who installed after the update vs before it (the
     same weekdays), how many were active again on day 1 / day 7 (GA4 cohorts, firstSessionDate).
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
same on 2 daily evaluations (PERSIST). GA4's own limits are said, never hidden: user
counts are estimates, consent-denied users are missing, user-level data older than GA4's retention reads short (the
fetch finds that edge: ret_from) — rows it touches say "No data" with the reason, never a guess.
"""

import math
from datetime import datetime, timedelta, timezone

from ..alerting.rules import fingerprint
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
RECENT_SWING = 0.05       # recent installs' returners moved >5 points of the returning users (ad spend): the per-user
                          # rows and the version table may be the users' mix → at most Maybe (installs_swing)
BIAS_MIN = 3              # early-updater gap from the 3–6 …
BIAS_MAX = 6              # … latest earlier version updates
VUSE_MIN_SHARE = 0.01     # (fetch) a version under 1% of the day's users is pooled into "_rest"
COH_BATCH = 14            # (fetch) cohorts per cohort request
COH_MIN_USERS = 200       # (fetch) a smaller cohort is judged pooled with the batch's other small ones
COH_MIN_COVERAGE = 0.90   # (fetch) a cohort holding < 90% of its installs (× the app's scale) reads short
COH_EDGE_RUN = 2          # (fetch) 2 short batches in a row = GA4's user-data edge
COH_MAX_CALLS = 12        # (fetch) cohort requests per fetch at most
IMPACT_ALERT_DAYS = 35    # only updates of the last 5 weeks alert (final ≈ R+20); older = info
IMPACT_LIST_DAYS = 60     # All apps "Recent updates"
IMPACT_SHOW = 5           # newest 5 blocks listed; older folded, never dropped

CONSTS = {k.lower(): v for k, v in dict(
    IMPACT_V=IMPACT_V, ACT_LATE_DAYS=ACT_LATE_DAYS, COHORT_DAYS=COHORT_DAYS, WIN_DAYS=WIN_DAYS, PRE_DAYS=PRE_DAYS,
    ADOPT_AFTER=ADOPT_AFTER, ROLLOUT_WAIT=ROLLOUT_WAIT, ADOPT_LOW=ADOPT_LOW, CHAIN_DAYS=CHAIN_DAYS,
    IMPACT_MIN_DAYS=IMPACT_MIN_DAYS, Z_FINAL=Z_FINAL, Z_EARLY=Z_EARLY, DAU_MIN_REL=DAU_MIN_REL, RET_MIN_PP=RET_MIN_PP,
    RET_MIN_REL=RET_MIN_REL, USE_MIN_REL=USE_MIN_REL, ARPDAU_MIN_REL=ARPDAU_MIN_REL, IMP_MIN_REL=IMP_MIN_REL,
    VER_MIN_REL=VER_MIN_REL, BIG_X=BIG_X, PERSIST=PERSIST, MIN_DAU=MIN_DAU, MIN_INSTALLS=MIN_INSTALLS,
    MIN_EVENTS=MIN_EVENTS, VER_MIN_USERS=VER_MIN_USERS, INSTALL_SWING=INSTALL_SWING, NEWSHARE_SWING=NEWSHARE_SWING,
    SIGMA_FLOOR=SIGMA_FLOOR, NOISE_LAG=NOISE_LAG, NULL_WEEKS=NULL_WEEKS, NULL_MIN=NULL_MIN, RECENT_SWING=RECENT_SWING,
    BIAS_MIN=BIAS_MIN, BIAS_MAX=BIAS_MAX, VUSE_MIN_SHARE=VUSE_MIN_SHARE, COH_BATCH=COH_BATCH,
    COH_MIN_USERS=COH_MIN_USERS, COH_MIN_COVERAGE=COH_MIN_COVERAGE, COH_EDGE_RUN=COH_EDGE_RUN,
    COH_MAX_CALLS=COH_MAX_CALLS, IMPACT_ALERT_DAYS=IMPACT_ALERT_DAYS, IMPACT_LIST_DAYS=IMPACT_LIST_DAYS,
    IMPACT_SHOW=IMPACT_SHOW).items()}

ROWS = ("returning_dau", "new_d1", "new_d7", "sessions", "time", "arpdau", "uninstall_d0")
VROWS = ("ver_sessions", "ver_time")
PRIMARY = ("returning_dau", "new_d1", "arpdau", "uninstall_d0")
GROUPS = (("usage", ("sessions", "time")), ("d7", ("new_d7",)), ("version", ("ver_sessions", "ver_time")))
APP_LEVEL = set(ROWS)                       # the version table is not diluted by adoption: the rest is
LEVEL_RANK = {"continue": 0, "win": 0, "hold": 1, "halt": 2}
SEVERITY = {"halt": "warning", "hold": "watch", "win": "good"}
ACT = {"halt": "HALT — staged rollout rok do, hotfix bhejo", "hold": "HOLD — agla rollout roko, jaanch karo",
       "win": "WIN — isi disha me aage badho"}
UNIT = {"returning_dau": "users", "new_d1": "pct", "new_d7": "pct", "sessions": "num", "time": "sec",
        "arpdau": "usd1k", "uninstall_d0": "pct"}
EXTRA = {"returning_dau": ("raw_change", "mode", "k_days", "imputed_share", "mu_week"),
         "new_d1": ("installs_before", "installs_after", "swing", "cohorts_before", "cohorts_after", "phi"),
         "sessions": ("all_before", "all_after", "adj_change"),
         "arpdau": ("imp_change", "imp_adj", "ecpm_change", "newshare_before", "newshare_after", "tz_blend", "currency"),
         "uninstall_d0": ("read", "phi", "est")}
EXTRA["new_d7"], EXTRA["time"] = EXTRA["new_d1"], EXTRA["sessions"]
DP = {"users": 0, "pct": 5, "num": 3, "sec": 1, "usd1k": 4}
STATUSES = ("worse", "better", "same", "unsure", "low", "pending", "na", "market")
NOTES = ("installs_swing", "newshare_swing", "diluted", "slow_rollout", "no_cohorts", "no_revenue", "tz_blend",
         "before_overlap", "cut_by_next", "prov", "est", "thresholded")

NA_YOUNG = "App launch ke turant baad ka update — pehle ka hafta nahi"
NA_CUT = "Agla update bahut jaldi aa gaya"
NA_OLD = "GA4 ab itna purana user data nahi rakhta"
NA_NOT_YET = "GA4 se ye data abhi aana baaki hai — agle fetch me"
NA_NO_USAGE = "GA4 usage data abhi aana baaki hai — agle fetch me"
NA_NO_REV = "AdMob revenue nahi mila"
NA_NO_VER = "Is update ka version number nahi"
WAIT_PERSIST = "pakka hone ke liye kal ka data bhi"
RAW_WHY = ("Naye users ke wapas aane ka data nahi — seedha pichhle hafte se tulna (minimum 2×); installs ke badlaav ka "
           "asar alag nahi ho sakta, isliye sirf andaza")
# RAW_WORST: without return cohorts the returning DAU is never "worse" / "better" — on the 28 live stores (no cohorts
# read yet) 79 of 234 week-on-week DAU rows came out worse / better, 58 of them moving WITH the install volume (median
# ±26–46% installs): ad spend, not the update


def _d(s):
    return U._d(s)


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
          "ret_k": U._pos(fi.get("ret_k"), 1.0), "split": fi.get("vuse_split") is not False,
          "has_data": int(store.get("impact_v") or 0) >= IMPACT_V,
          "launch": whole["hs"] + timedelta(days=i0), "rev": rev, "tz_blend": blend,
          "currency": (revenue or {}).get("currency") or "USD",
          "thresholded": bool(fi.get("thresholded")) or bool((store.get("flags") or {}).get("thresholded")),
          "usage_from": min(usage) if usage else None}
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


def windows(cx, b, prev_b, next_b):
    """The block's windows (see the module docstring) → b["win"]."""
    R, E = b["R"], cx["E"]
    A = _adoption(cx, b)
    if b["kind"] == "version":
        hit = next((d for d in sorted(A) if d >= R and A[d] >= ADOPT_AFTER), None)
        a0 = max(R + timedelta(days=1), min(hit or R + timedelta(days=ROLLOUT_WAIT), R + timedelta(days=ROLLOUT_WAIT)))
        slow = a0 <= E and (A.get(a0) or 0.0) < ADOPT_AFTER
    else:
        a0, slow = R + timedelta(days=1), False
    end_a, cut_by = a0 + timedelta(days=WIN_DAYS - 1), None
    if next_b is not None and next_b["R"] - timedelta(days=1) < end_a:
        end_a, cut_by = next_b["R"] - timedelta(days=1), {"label": next_b["label"], "date": _iso(next_b["R"])}
    days_a = _days(a0, end_a)
    settled = [d for d in days_a if d <= cx["S_act"]]
    avail = [d for d in days_a if d <= E]
    over = prev_b if prev_b is not None and R - timedelta(days=7) <= prev_b["R"] <= R - timedelta(days=1) else None
    shown = [A[d] for d in avail if d in A]
    b["A"] = A
    b["win"] = {"a0": a0, "end_a": end_a, "days_a": days_a, "settled": settled, "avail": avail, "slow": slow,
                "cut_by": cut_by, "b0": R - timedelta(days=7), "b1": R - timedelta(days=1),
                "overlap": over, "adopt_mean": _mean(shown) if b["kind"] == "version" else None}
    return b["win"]


# ── rows ─────────────────────────────────────────────────────────────────────────────────────────

def _row(key):
    return {"before": None, "after": None, "expected": None, "after_prov": None, "change": None,
            "change_unit": "pp" if UNIT[key] == "pct" else "rel", "unit": UNIT[key], "z": None, "status": "na",
            "raw_status": "na", "streak": 0, "prov": False, "est": False, "n_before": 0, "n_after": 0,
            "from_b": None, "to_b": None, "from_a": None, "to_a": None, "reason": None, "ready_on": None,
            "extra": dict.fromkeys(EXTRA[key])}


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
    return Z_FINAL if win["settled"] and len(win["settled"]) == len(win["days_a"]) else Z_EARLY


def _pending(row, win, ready):
    row.update(status="pending", raw_status="pending", ready_on=_iso(ready))
    return row


def _span(row, a, b):
    if a:
        row["from_a"], row["to_a"] = _iso(min(a)), _iso(max(a))
    if b:
        row["from_b"], row["to_b"] = _iso(min(b)), _iso(max(b))


def _rho(cx, R):
    """Pre-release return rates ρ̂_k = Σ day-k actives ÷ Σ cohort users over the complete cohorts [R−28−k, R−1−k], and
    K = the last day k (≤ COHORT_DAYS) that ≥14 such cohorts reach, every day before it too."""
    ret, rho, K = cx["ret"], {}, 0
    for k in range(1, COHORT_DAYS + 1):
        x = t = n = 0
        for j in range(28):
            e = ret.get((R - timedelta(days=28 + k - j)).isoformat())
            if e and e.get("ok") and len(e.get("a") or []) > k and e.get("t"):
                x, t, n = x + e["a"][k], t + e["t"], n + 1
        if n < 14 or not t:
            break
        rho[k], K = x / t, k
    return rho, K


def _null_sd(vals):
    """The week comparison's own noise from its pseudo-updates: their spread around 0 (a model bias counts as noise
    too), floored at SIGMA_FLOOR."""
    return max(U.spread(vals, 0.0), SIGMA_FLOOR)


def _shifts(R, days):
    """The pseudo-update shifts Δ for after-days `days`: every shifted after-day before the release, NULL_WEEKS weeks
    of them, one per day (each keeps its own same-weekday matching, so any Δ is a fair copy)."""
    lo = max((d - R).days for d in days) + 1
    return range(max(lo, 1), max(lo, 1) + 7 * NULL_WEEKS)


# ≥ NULL_MIN pseudo-updates need ~10 weeks before the release: the first starts ≤10 days back, each looks 5 weeks further
LOW_NULL = "Update se pehle ka ~%d hafte ka data chahiye (aam utaar-chadhaav napne ke liye)" % math.ceil((10 + NULL_MIN + 35) / 7)


def dau_row(cx, blk):
    """Returning DAU vs its expected level (see the module docstring, and the spec's §3.4a). Also keeps, for the
    per-user rows, how much of the returning users are recent installs coming back (blk["_mix"])."""
    row, win, R = _row("returning_dau"), blk["win"], blk["R"]
    ex = row["extra"]
    rho, K = _rho(cx, R)
    raw = K < 7
    Kx = K                                            # (the mix check below reads ρ̂ even in raw mode, when it has it)
    K = 0 if raw else K
    ex.update(mode="raw" if raw else "cohort", k_days=K)
    mn = DAU_MIN_REL * (2 if raw else 1)
    rk, ret = cx["ret_k"], cx["ret"]
    memo, rmemo = {}, {}

    def Y(d):
        if d not in memo:
            y = yi = 0.0
            for k in range(1, K + 1):
                c = d - timedelta(days=k)
                e = ret.get(c.isoformat())
                if e and e.get("ok") and len(e.get("a") or []) > k:
                    y += e["a"][k]
                else:
                    v = (_dv(cx, c, "new") or 0) * rk * rho[k]
                    y, yi = y + v, yi + v
            memo[d] = (y, yi)
        return memo[d][0]

    def O(d):
        r = _ret_dau(cx, d)
        return None if r is None else r - Y(d)

    def recent(d):
        if d not in rmemo:
            rmemo[d] = sum((_dv(cx, d - timedelta(days=k), "new") or 0) * rk * rho[k] for k in range(1, K + 1))
        return rmemo[d]

    omemo, wmemo = {}, {}

    def Om(d):
        if d not in omemo:
            omemo[d] = O(d)
        return omemo[d]

    def wow(u):
        if u not in wmemo:
            wmemo[u] = _log(Om(u), Om(u - timedelta(days=7)))
        return wmemo[u]

    def mu_at(Rq):
        # the normal weekly change comes from the weeks BEFORE the before-week (NOISE_LAG): the before-week is the
        # contrast's own baseline — reused as its reference it makes the noise look ~20% smaller than it is
        v = [wow(u) for u in _days(Rq - timedelta(days=21 + NOISE_LAG), Rq - timedelta(days=1 + NOISE_LAG))]
        v = [x for x in v if x is not None]
        return U.median(v) if v else 0.0

    def expd(d, b, w, mu):
        o = Om(b)
        return None if o is None or o <= 0 else o * math.exp(mu * w) + recent(d)

    def backtest(Rq, mu):
        bt = []
        for t in _days(Rq - timedelta(days=14 + NOISE_LAG), Rq - timedelta(days=1 + NOISE_LAG)):
            x = _log(_ret_dau(cx, t), expd(t, t - timedelta(days=7), 1, mu))
            if x is not None:
                bt.append(x)
        return bt
    mu = mu_at(R)
    bt = backtest(R, mu)
    rb = [_ret_dau(cx, d) for d in _days(win["b0"], win["b1"])]
    rb = [x for x in rb if x is not None]
    ex["mu_week"] = round(mu, 5)
    used, bs, pat = [], [], []
    sr = se = srb = 0.0
    xa = []
    for d in win["settled"]:
        b, w = _bday(R, d)
        r, e, r0 = _ret_dau(cx, d), expd(d, b, w, mu), _ret_dau(cx, b)
        x = _log(r, e)
        if x is None or not r0:
            continue
        xa.append(x)
        used.append(d), bs.append(b), pat.append((d, b, w))
        sr, se, srb = sr + r, se + e, srb + r0
    ys = [memo[d] for d in memo]
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
    blk["_mix"] = _mix(cx, rho, Kx, used, bs)
    if len(win["settled"]) < IMPACT_MIN_DAYS:
        return _pending(row, win, win["a0"] + timedelta(days=IMPACT_MIN_DAYS - 1 + ACT_LATE_DAYS))
    if (_mean(rb) or 0) < MIN_DAU:
        row.update(status="low", raw_status="low", reason="Roz %d se kam purane users — GA4 ginti ka noise zyada" % MIN_DAU)
        return row
    if len(bt) < 10 or len(xa) < IMPACT_MIN_DAYS:
        row.update(status="low", raw_status="low", reason="Update se pehle ke 2 hafte ka data kam")
        return row
    if abs(row["change"]) < mn:                      # under the minimum: Normal whatever the noise (_judge) — the
        row["raw_status"] = row["status"] = "same"   # noise is only measured when it can decide
        row["_ratio"] = abs(row["change"]) / mn
        if raw:
            row["reason"] = RAW_WHY
        return row
    shift = _mean(xa) - U.median(bt)
    nulls = []                                       # the same comparison at every pseudo-update before the release
    for dl in _shifts(R, used):
        Rq, D = R - timedelta(days=dl), timedelta(days=dl)
        mq = mu_at(Rq)
        bq = backtest(Rq, mq)
        xq = [_log(_ret_dau(cx, d - D), expd(d - D, b - D, w, mq)) for d, b, w in pat]
        if len(bq) >= 10 and all(x is not None for x in xq):
            nulls.append(_mean(xq) - U.median(bq))
    if len(nulls) < NULL_MIN:
        row.update(status="low", raw_status="low", reason=LOW_NULL)
        return row
    z = shift / _null_sd(nulls)
    row["z"] = z
    st = _judge(row["change"], mn, z, _zlevel(win))
    if raw:                                          # no return cohorts: the installs' returners can't be told apart
        row["reason"] = RAW_WHY                      # from the old users — at most "Maybe" (RAW_WORST)
        if st in ("worse", "better"):
            st = "unsure"
    row["raw_status"] = row["status"] = st
    row["_ratio"] = abs(row["change"]) / mn
    return row


def _mix(cx, rho, K, used, bs):
    """How much of the returning users are recent installs coming back, on the matched after-days vs their before-days
    (ad spend moves it; their sessions / time differ from long-time users'): {share_b, share_a} from the pre-release
    return rates ρ̂ × the installs that came, or — without return rates — {swing} of the installs of the 14 days feeding
    each side. → None without matched days."""
    if not used:
        return None
    rk = cx["ret_k"]

    def feed(d):
        if K >= 7:
            return sum((_dv(cx, d - timedelta(days=k), "new") or 0) * rk * rho[k] for k in range(1, K + 1))
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


def ret_row(cx, blk, N):
    """New users back on day N (1 / 7): after-install days vs before-install days of the same weekdays (§3.4b)."""
    key = "new_d1" if N == 1 else "new_d7"
    row, win, R = _row(key), blk["win"], blk["R"]
    ex, ret = row["extra"], cx["ret"]
    S = cx["S_act"]
    Ca = [c for c in win["days_a"] if c + timedelta(days=N) <= S]
    wd = {c.weekday() for c in Ca}
    Cb = [c for c in _days(R - timedelta(days=7 + N), R - timedelta(days=1 + N)) if c.weekday() in wd]
    ready = win["a0"] + timedelta(days=2 + N + ACT_LATE_DAYS)
    if len(Ca) < 3:
        return _pending(row, win, ready if len(win["days_a"]) >= 3 else None)
    rf = cx["ret_from"]
    if rf is not None and min(Cb + Ca) < rf:
        return _na(row, NA_OLD)

    okm = {}

    def okc(c):
        if c not in okm:
            e = ret.get(c.isoformat())
            okm[c] = e if e and e.get("ok") and len(e.get("a") or []) > N and e.get("t") else None
        return okm[c]
    A, B = [c for c in Ca if okc(c)], [c for c in Cb if okc(c)]
    if len(A) < 3 or not B:
        lost = any((ret.get(c.isoformat()) or {}).get("ok") is False for c in Ca + Cb)
        return _na(row, NA_OLD if lost else NA_NOT_YET)
    xa, na = sum(okc(c)["a"][N] for c in A), sum(okc(c)["t"] for c in A)
    xb, nb = sum(okc(c)["a"][N] for c in B), sum(okc(c)["t"] for c in B)
    pb, pa = xb / nb, xa / na
    each = []
    for c in _days(R - timedelta(days=28 + N), R - timedelta(days=1 + N)):
        e = okc(c)
        if e:
            each.append((e["a"][N], e["t"], c.toordinal()))
    phi = max(1.0, U._phi(each))
    dpp = (pa - pb) * 100
    p = (xa + xb) / (na + nb)
    se = 100 * math.sqrt(p * (1 - p) * (1 / na + 1 / nb) * phi) if 0 < p < 1 else 0.0
    # the same comparison at every pseudo-update before the release (the install days of a week are not independent
    # — a campaign's users stay for days): its spread, when there are enough of them, if bigger than the model's
    nulls = []
    for dl in _shifts(R - timedelta(days=N), A):
        D = timedelta(days=dl)
        Aq, Bq = [okc(c - D) for c in A], [okc(c - D) for c in B]
        if all(Aq) and all(Bq):
            nulls.append(100 * (sum(e["a"][N] for e in Aq) / sum(e["t"] for e in Aq)
                                - sum(e["a"][N] for e in Bq) / sum(e["t"] for e in Bq)))
    if len(nulls) >= NULL_MIN:
        se = max(se, U.spread(nulls, 0.0))
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
        row["after_prov"] = sum(okc(c)["a"][N] for c in provs) / sum(okc(c)["t"] for c in provs)
    sample = min(na, nb) >= MIN_INSTALLS and min(xa, xb) >= MIN_EVENTS and len(A) >= 3
    big = abs(dpp) >= RET_MIN_PP and rel is not None and abs(rel) >= RET_MIN_REL     # both minimums
    if not sample:
        st = "low"
    elif big and z is not None and abs(z) >= _zlevel(win) and (z > 0) == (dpp > 0):
        st = "better" if dpp > 0 else "worse"
    else:
        st = "unsure" if big else "same"
    if st in ("worse", "better") and na >= U.BIG_RECENT_USERS:        # a big app: breadth, as the uninstall alerts
        moved = sum(1 for c in A if (okc(c)["a"][N] / okc(c)["t"] > pb) == (dpp > 0))
        if moved < math.ceil(4 / 7 * len(A)):
            st = "unsure"
    row["status"] = row["raw_status"] = st
    row["_ratio"] = abs(dpp) / RET_MIN_PP
    if swing is not None and abs(swing) > INSTALL_SWING:
        row["_swing"] = True
    return row


def _pu_test(cx, blk, M, need=0.0):
    """The per-user test (§3.4d) of M (a per-user number by day): each settled after-day vs the same weekday before, net
    of the normal week-over-week change μ (the median of the 3 weeks before the before-week, NOISE_LAG); the noise = the
    same comparison at every pseudo-update before the release (_null_sd) — measured only when the effect reaches
    `need` (the row's minimum: under it the row is Normal whatever the noise). → {used, bs, stat (the mean trend-net log
    change), adj (its effect: e^stat − 1 — what is judged), z, why (None, "pending", or why there is no z)}."""
    win, R = blk["win"], blk["R"]
    memo, wmemo = {}, {}

    def m(d):
        if d not in memo:
            memo[d] = M(d)
        return memo[d]

    def wow(u):
        if u not in wmemo:
            wmemo[u] = _log(m(u), m(u - timedelta(days=7)))
        return wmemo[u]

    def mu_at(Rq):
        v = [wow(u) for u in _days(Rq - timedelta(days=21 + NOISE_LAG), Rq - timedelta(days=1 + NOISE_LAG))]
        v = [x for x in v if x is not None]
        return (U.median(v) if v else 0.0), len(v)
    mu, nw = mu_at(R)
    xa, used, bs, pat = [], [], [], []
    for d in win["settled"]:
        b, w = _bday(R, d)
        x = _log(m(d), m(b))
        if x is None:
            continue
        xa.append(x - mu * w)
        used.append(d), bs.append(b), pat.append((d, b, w))
    out = {"used": used, "bs": bs, "stat": None, "adj": None, "z": None, "why": None}
    if len(win["settled"]) < IMPACT_MIN_DAYS:
        out["why"] = "pending"
        return out
    if nw < 10 or len(xa) < IMPACT_MIN_DAYS:
        out["why"] = "Update se pehle ke 3 hafte ka data kam"
        return out
    out["stat"] = st = _mean(xa)
    out["adj"] = math.exp(st) - 1
    if abs(out["adj"]) < need:
        return out
    nulls = []
    for dl in _shifts(R, used):
        D = timedelta(days=dl)
        mq, nq = mu_at(R - D)
        xq = [_log(m(d - D), m(b - D)) for d, b, _ in pat]
        if nq >= 10 and all(x is not None for x in xq):
            nulls.append(_mean([x - mq * w for x, (_, _, w) in zip(xq, pat)]))
    if len(nulls) < NULL_MIN:
        out["why"] = LOW_NULL
        return out
    out["z"] = st / _null_sd(nulls)
    return out


def _pu(cx, blk, row, M, num, den, mn):
    """A per-user row: shown = pooled Σnum ÷ Σden after vs the matched before days (change = after ÷ before − 1, as
    the numbers read); judged = _pu_test's trend-net effect (adj) against the minimum `mn` — a trend the app was already
    on never makes (or hides) a change. → (row, the test)."""
    win = blk["win"]
    t = _pu_test(cx, blk, M, mn)
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
    if t["why"] == "pending":
        _pending(row, win, win["a0"] + timedelta(days=IMPACT_MIN_DAYS - 1 + ACT_LATE_DAYS))
        return row, t
    if t["why"] or row["change"] is None:
        row.update(status="low", raw_status="low", reason=t["why"] or "Update se pehle ke 3 hafte ka data kam")
        return row, t
    row["z"] = t["z"]
    st = _judge(t["adj"], mn, t["z"], _zlevel(win))
    row["status"] = row["raw_status"] = st
    row["_ratio"] = abs(t["adj"]) / mn
    row["_eff"] = t["adj"]
    return row, t


MIX_WHY = ("Haal ke installs (ad spend) se purane users ka mix badla — per-user farak mix ka bhi ho sakta hai, isliye "
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
    row, t = _pu(cx, blk, row, M, num, den, USE_MIN_REL)
    used, bs = t["used"], t["bs"]

    def allu(days):
        n = sum((slot(d, "n") or [0, 0, 0])[j] + (slot(d, "r") or [0, 0, 0])[j] for d in days)
        a = sum(_dv(cx, d, "a1") or 0 for d in days)
        return n / a if a else None
    row["extra"].update(all_before=allu(bs), all_after=allu(used), adj_change=t["adj"])
    if row["status"] not in ("pending", "na"):
        mr = [den(d) for d in bs]
        if mr and _mean(mr) < MIN_DAU:
            row.update(status="low", raw_status="low", reason="Roz %d se kam purane users" % MIN_DAU)
    _mix_cap(blk, row)
    return row


MARKET_WHY = "Sirf eCPM badla, ads per user wahi — market ka asar, update ka nahi"


def arpdau_row(cx, blk):
    """Ad revenue per 1,000 active users (AdMob revenue ÷ GA4 activeUsers), shown before / after. JUDGED on the part
    an update can move — ads (impressions) per active user, with its own trend-net test, minimum ARPDAU_MIN_REL and
    BIG_X: eCPM (the price per ad) is the market's. Revenue per user moving for sure while ads per user moved under
    IMP_MIN_REL (or the other way) = "Market", never counted (§3.4f)."""
    row = _row("arpdau")
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
    row, t = _pu(cx, blk, row, M, lambda d: rev(d) * 1000, a1, ARPDAU_MIN_REL)
    used, bs = t["used"], t["bs"]
    ia, ib = pool(used, lambda ds: sum(imp(d) for d in ds)), pool(bs, lambda ds: sum(imp(d) for d in ds))
    ra, rb = sum(rev(d) for d in used), sum(rev(d) for d in bs)
    ea = ra / sum(imp(d) for d in used) if ia else None
    eb = rb / sum(imp(d) for d in bs) if ib else None
    ns_b = pool(bs, lambda ds: sum(_dv(cx, d, "new") or 0 for d in ds))
    ns_a = pool(used, lambda ds: sum(_dv(cx, d, "new") or 0 for d in ds))
    ti = _pu_test(cx, blk, Mi, IMP_MIN_REL)          # the update's part: ads per active user
    ex.update(imp_change=round(ia / ib - 1, 4) if ia and ib else None, imp_adj=ti["adj"],
              ecpm_change=round(ea / eb - 1, 4) if ea and eb else None,
              newshare_before=None if ns_b is None else round(ns_b, 5),
              newshare_after=None if ns_a is None else round(ns_a, 5))
    if ns_a is not None and ns_b is not None and abs(ns_a - ns_b) > NEWSHARE_SWING:
        row["_swing"] = True
    if row["n_after"] == 0 and row["status"] not in ("pending",) and any(f(d) is None for d in win["settled"]):
        return _na(row, NA_NO_REV)
    if row["status"] in ("pending", "low", "na"):
        row.pop("_ratio", None), row.pop("_eff", None)
        return row
    st_r, Z = row["raw_status"], _zlevel(win)
    small = ti["adj"] is not None and abs(ti["adj"]) < IMP_MIN_REL      # ads per user ~flat (its noise not needed)
    if ti["adj"] is None or (ti["z"] is None and not small):     # ads per user can't be judged: revenue alone never
        st = "unsure" if st_r in ("worse", "better", "unsure") else st_r              # decides whose it is
        row.update(status=st, raw_status=st, z=None)
        if st == "unsure":
            row["reason"] = "Ads per user ka data kam — kamai ka farak update ka hai ya market ka, pakka nahi"
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
            row["reason"] = ("Kamai ka farak pakka, par ads per user ka hissa (%s) abhi pakka nahi — baaki eCPM (market)"
                             % U.fmt_rel(ti["adj"]))
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
        row.update(status="low", raw_status="low", reason="Install ke din ke uninstall ka data kam")
        return row
    r, b = use["r"], use["b"]
    ex.update(read="newest" if use is nw else "settled", est=use["est"])
    row.update(before=b[0] / b[1], after=r[0] / r[1], change=use["dpp"], z=use["z"], n_before=b[2], n_after=r[2],
               prov=bool(use is nw and use["prov"]), est=bool(use["est"]))
    _span(row, use["Ca"], use["Cb"])
    if nw and stl and use is stl and nw["r"][2] > stl["r"][2]:
        row["after_prov"] = nw["r"][0] / nw["r"][1]
    if st is None:
        if r[2] < U.RECENT_MIN and win["days_a"] and win["days_a"][-1] > cx["E"]:
            return _pending(row, win, win["a0"] + timedelta(days=U.RECENT_MIN - 1))
        sample = U._sample(r[2], r[1], r[0]) and b[0] >= U.MIN_EVENTS and b[1] - b[0] >= U.MIN_EVENTS
        st = ("low" if not sample else "unsure" if abs(use["dpp"]) >= U.MIN_PP and use["relsm"] >= U.MIN_REL
              else "same")
        if st == "low":
            row["reason"] = "Install ke din ke uninstall ka data kam — %d din, %d installs (kam se kam %d din, %d installs)" % (
                r[2], r[1], U.RECENT_MIN, U.MIN_RECENT_USERS)
    row["status"] = row["raw_status"] = st
    row["_ratio"] = abs(use["dpp"]) / U.MIN_PP
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
                           reason="Naye / purane version pe roz %d se kam purane users" % VER_MIN_USERS)
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
            why = "GA4 is property me naye / purane users alag nahi deta — sab users ki tulna, sirf andaza"
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


def _dir(x, up_word, down_word):
    return up_word if x > 0 else down_word


def _signed_pct(x):
    return U._minus(("+" if x > 0 else "-" if x < 0 else "") + _pct(x))


def head_phrase(key, row, cx):
    """The row's message phrase (alert text; spec §3.7)."""
    c = row.get("change")
    if key == "returning_dau":
        return "purane users ka DAU %s %s (expected %s → %s/din)" % (
            _pct(c), _dir(c, "badha", "gira"), _users(row["expected"]), _users(row["after"]))
    if key in ("new_d1", "new_d7", "uninstall_d0"):
        o, n, sd = U.shown_pct(row["before"], row["after"])
        lead = {"new_d1": "naye users me se agle din wapas aane wale", "new_d7": "naye users me se 7ve din wapas aane wale",
                "uninstall_d0": "install ke din hi hataane wale"}[key]
        return "%s %s → %s (%s point)" % (lead, o, n, U.fmt_pp(sd))
    if key in ("sessions", "time"):
        e = _eff(key, row)
        net = "" if e is None or abs(e - c) < 0.01 else "; normal trend hata ke %s" % U.fmt_rel(e)
        if key == "sessions":
            return "purane users ke sessions per user %s → %s (%s%s)" % (
                U._minus("%.1f" % row["before"]), U._minus("%.1f" % row["after"]), U.fmt_rel(c), net)
        return "purane users ka time per user %s → %s (%s%s)" % (fmt_dur(row["before"]), fmt_dur(row["after"]),
                                                                U.fmt_rel(c), net)
    if key == "arpdau":
        imp = _eff(key, row)
        return "kamai per 1,000 users %s → %s (%s) — ads per user %s" % (
            _money(row["before"], cx["currency"]), _money(row["after"], cx["currency"]), U.fmt_rel(c),
            U.fmt_rel(imp) if imp is not None else "—")
    what = "sessions per user" if key == "ver_sessions" else "time per user"
    return "naye version pe %s purane se %s %s (aam farak hata ke)" % (what, _pct(row["adj"], 0),
                                                                     _dir(row["adj"], "zyada", "kam"))


def short_phrase(key, row):
    """"time per user −14%", "D1 wapsi −4 point" — the "aur … kharab" list."""
    if key == "returning_dau":
        return "DAU " + _signed_pct(row["change"])
    if key in ("new_d1", "new_d7"):
        return "%s wapsi %s point" % ("D1" if key == "new_d1" else "D7", U.fmt_pp(row["change"]))
    if key == "uninstall_d0":
        return "install ke din uninstall %s point" % U.fmt_pp(row["change"])
    if key in ("sessions", "time"):
        return "%s per user %s" % (key, U.fmt_rel(_eff(key, row)))
    if key == "arpdau":
        return "ads per user " + U.fmt_rel(_eff(key, row))
    return "naye version pe %s %s" % ("sessions" if key == "ver_sessions" else "time", U.fmt_rel(row["adj"]))


def why_phrase(key, row):
    """"purane users ka DAU expected se 5.6% kam" — the verdict's why line."""
    if key == "returning_dau":
        return "purane users ka DAU expected se %s %s" % (_pct(row["change"]), _dir(row["change"], "zyada", "kam"))
    if key in ("new_d1", "new_d7", "uninstall_d0"):
        lead = {"new_d1": "agle din wapas aane wale naye users", "new_d7": "7ve din wapas aane wale naye users",
                "uninstall_d0": "install ke din hi hataane wale"}[key]
        return "%s %s point %s" % (lead, U.fmt_pp(abs(row["change"])), _dir(row["change"], "zyada", "kam"))
    if key in ("sessions", "time"):
        e = _eff(key, row)
        return "%s %s %s" % ("sessions per user" if key == "sessions" else "time per user", _pct(e, 0),
                             _dir(e, "zyada", "kam"))
    if key == "arpdau":
        e = _eff(key, row)
        return "ads per user %s %s (kamai per user %s)" % (_pct(e, 0), _dir(e, "zyada", "kam"), U.fmt_rel(row["change"]))
    what = "sessions per user" if key == "ver_sessions" else "time per user"
    return "naye version pe %s %s %s" % (what, _pct(row["adj"], 0), _dir(row["adj"], "zyada", "kam"))


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


def verdict(blk, rows, vrows, cx):
    """The block's verdict from its effective row statuses (spec §3.6)."""
    win = blk["win"]
    allr = dict(rows, **vrows)
    settled = len(win["settled"])
    na_all = blk.get("_na")
    final = bool(win["days_a"]) and settled == len(win["days_a"]) and rows["new_d7"]["status"] != "pending"
    worse = [k for k in ROWS + VROWS if allr[k]["status"] == "worse"]
    better = [k for k in ROWS + VROWS if allr[k]["status"] == "better"]
    pending = [k for k in ROWS + VROWS if allr[k]["status"] == "pending"]
    primary = [k for k in PRIMARY if not allr[k].get("_swing")]
    groups = [list(m) for _, m in GROUPS] + [[k] for k in PRIMARY if allr[k].get("_swing")]
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
        out["why"] = "Abhi %d pakka din — kam se kam %d chahiye" % (settled, IMPACT_MIN_DAYS)
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
        un = [k for k in ROWS + VROWS if allr[k]["status"] == "unsure" and allr[k].get("_ratio")]
        if better:
            out["why"] = _cap(_join([why_phrase(k, allr[k]) for k in _rank(better, allr)])) + \
                (" — adoption kam, isliye WIN nahi" if diluted else " — abhi pakka nahi" if not final else "")
        elif un:
            out["why"] = "Kuch farak dikh raha hai (%s), par abhi pakka nahi — rollout chalne do" % ", ".join(
                short_phrase(k, allr[k]) for k in _rank(un, allr)[:3])
        else:
            out["why"] = "Koi pakka farak nahi — rollout chalne do"
    return out


def _rank(keys, allr):
    """Primary rows first, then the biggest effect ÷ minimum."""
    return sorted(keys, key=lambda k: (k not in PRIMARY, -allr[k].get("_ratio", 0), (ROWS + VROWS).index(k)))


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
        text += " · shuruaati — D7 abhi baaki"
    return text, ks[0]


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


def impact_app(store, ds, cd, whole, i0, rels, revenue, state, app_id, E, late, first, advanced, outdated, now):
    """One app's update impact → (detail["impact"], summary["updates"], ready conditions for update_impact_episodes).
    Keeps its per-row persistence in state["eval"][app_id]["impact"] (in place). `first` / `advanced` = the uninstall
    evaluation's (first ever / E moved on); a first evaluation WITH impact data, or an outdated store, seeds what it
    shows (never sent)."""
    E = _d(E)
    cx = _context(store, cd, whole, i0, revenue, E, late)
    blocks = make_blocks(rels, cx["launch"])
    ev = state.setdefault("eval", {}).setdefault(app_id, {})
    prev = ev.get("impact") or {}
    fresh = not prev.get("data")
    seed = fresh or bool(outdated) or not cx["has_data"]
    pblocks = prev.get("blocks") or {}
    keep_state, conds, done = {}, [], []
    for j, blk in enumerate(blocks):
        blk["_cx"] = cx
        windows(cx, blk, blocks[j - 1] if j else None, blocks[j + 1] if j + 1 < len(blocks) else None)
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
        done.append(blk)
        vrows = vc["rows"]
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
        hk = (_rank(vd["worse"], allr)[0] if vd["worse"] else _rank(vd["better"], allr)[0] if vd["better"]
              else "returning_dau" if rows["returning_dau"]["change"] is not None else None)
        if hk is not None:
            r = allr[hk]
            head = {"row": hk, "change": _rd(r["adj"], 4) if hk in VROWS else
                    _rd(r["change"], 2 if r["change_unit"] == "pp" else 4),
                    "unit": "rel" if hk in VROWS else r["change_unit"]}
        if level in ("halt", "hold", "win") and blk["R"] >= E - timedelta(days=IMPACT_ALERT_DAYS):
            keys = vd["better"] if level == "win" else vd["worse"]
            conds.append(_cond(app_id, blk, level, allr, keys, vd, seed, E, rows))
        blk["_out"] = {"key": blk["key"], "rel_keys": blk["rel_keys"], "kind": blk["kind"], "versions": blk["versions"],
                       "label": blk["label"], "date": _iso(blk["R"]),
                       "adoption": _adopt_out(blk),
                       "windows": _win_out(blk),
                       "rows": {k: _round_row(rows[k]) for k in ROWS},
                       "versions_cmp": dict(vc, rows={k: _round_vrow(vrows[k]) for k in VROWS}),
                       "verdict": vd, "notes": notes, "alert_id": None}
        blk["_head"] = head
    ev["impact"] = {"data": bool(cx["has_data"] or prev.get("data")), "blocks": dict(sorted(keep_state.items()))}
    updates = []
    for blk in reversed(blocks):
        if blk["R"] >= E - timedelta(days=IMPACT_LIST_DAYS):
            vd = blk["_out"]["verdict"]
            updates.append({"key": blk["key"], "label": blk["label"], "date": _iso(blk["R"]), "level": vd["level"],
                            "early": vd["early"], "final": vd["final"],
                            "adoption": blk["_out"]["adoption"]["last"], "head": blk["_head"]})
    rf = store.get("ret_from")
    rev = "none" if cx["rev"] is None else "ok"
    if cx["rev"] is not None:
        span = [d for d in _days(max(cx["launch"], E - timedelta(days=PRE_DAYS + 30)), cx["S_act"])]
        if any(cx["rev"](d) is None for d in span):
            rev = "partial"
    detail = {"v": 1, "updates": [b["_out"] for b in reversed(blocks)],
              "flags": {"ret_from": rf, "vuse_split": cx["split"], "revenue": rev, "tz_blend": cx["tz_blend"],
                        "usage_from": cx["usage_from"]}}
    return detail, updates, conds


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
    else:
        now, before = r["after"], r["expected"] if hk == "returning_dau" else r["before"]
        rel, dpp = r["change"], None
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


def update_impact_episodes(state, app_id, E, conds, advanced, now):
    """Open / refresh / close this app's update-impact episodes (shared state["episodes"] / "closed", so
    mark_notified works unchanged). Pure: it only changes `state`. ONE episode per update and direction, for good: a bad
    block (HOLD / HALT) is "<app>|impact|<update>", a WIN "<app>|impact_win|<update>" (<update> = _ident: its first
    version, so a first-5% day that moves by a day is the same update). id = fingerprint(app, "uninstall_impact", dir,
    "<opened>|<update>|<level>"): HOLD → HALT regenerates it with notified_at None (sent once more); HALT → HOLD never
    re-sends. An update whose episode closed (CLOSE_EVALS daily evaluations without its condition) and comes back takes
    that episode back — same id, nothing re-sent unless it goes above the highest level it reached (peak). A condition
    carrying seed (the app's first impact evaluation, an outdated store) is shown, not sent. An episode closes at once
    (never sent) when its update is older than IMPACT_ALERT_DAYS. → this app's open impact episodes."""
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
                    ep = closed.pop(j)
                    ep.pop("closed", None)
            if ep is not None:
                eps[key] = ep
                ep["misses"] = 0
        if ep is None:
            ep = {"id": fingerprint(app_id, "uninstall_impact", None, c["dir"], "%s|%s|%s" % (E_iso, ident, lvl)),
                  "app_id": app_id, "family": "impact", "dir": c["dir"], "opened": E_iso, "last_true": E_iso,
                  "misses": 0, "notified_at": now if c["seed"] else None, "notified_dry": False,
                  "seeded": bool(c["seed"]), "block": c["block"], "vers": list(c["vers"]), "kind": c["kind"],
                  "peak": lvl, "last": snap}
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
            closed.append(dict(eps.pop(key), closed=E_iso))
            continue
        if advanced:
            ep["misses"] += 1
            if ep["misses"] >= U.CLOSE_EVALS:
                closed.append(dict(eps.pop(key), closed=E_iso))
    return [e for e in eps.values() if e["app_id"] == app_id and e.get("family") == "impact"]
