"""🆕 First open BY COUNTRY — the hourly fetch (owner, 20 Oct 2026: "country wise bhi dekh saku esa kara do").

The same strict GA4 funnel as fetch.ga4_firstopen (first_open → Splash ≤ 10 min → Home ≤ 60 min, Home never above the
Splash), per app per day per COUNTRY, for EVERY country (nothing cut, no "top N"):
  1. the day's countries: runReport first_open users by countryId (one call for all the days asked, no row limit);
  2. the day's total: the funnel once, as the First open fetch reads it;
  3. the countries in groups of GROUP (15, GA4's funnel breakdown limit): the funnel with step 1 = first_open IN the
     group's countries, broken down by countryId — every value of the group comes back for every step.
Measured on the real properties (ga4_firstopen_country_probe, 20 Oct 2026): the group read equals a single-country
funnel exactly, while reading "the top 15, then the next 15 …" by leaving countries out of step 1 lost 1–7 % (GA4 picks
each STEP's top 15 on its own, so an edge country could come back with first_open 0 and be left out after).
GA4's RESERVED_TOTAL row is dropped; what GA4 named no country for ("(not set)", thresholds) is the day's total minus
the named countries, worked out by the build — never spread over countries.

GA4 keeps event data only as long as the property's retention (2 months), so this store is the history: kept for good in
data/ga4_firstopen_cc/<key>.json.gz (private repo):
    {"v", "app_id", "package", "property_id", "stream_id", "time_zone", "recent_at",
     "days": {D: {"c": {cc: [first_open, splash, home]}, "t": [first_open, splash, home], "smp": share GA4 read | null,
                  "fin": final when read, "sg": the screens' signature, "at"}
               | {"none": true, "why": "ga4", "n": empty answers, "fo": {cc: first_open users}, "at"}   GA4's funnel
                 has nothing left for the day, but its report still names the countries' first opens ("fo")
               | {"none": true, "at"}},                                  GA4 named no country that day
     "mid": {D: the UTC time of its last read}}   only the mid_days (HOT_DAYS … FINAL_LAG − 1 days old); none at
                                                  GA4_FINAL_DAYS 3
Per app and run (its screens come from the First open store; at most MAX_CALLS calls — a day is begun only when ALL its
calls still fit, so the cap never cuts one; the property's quota floors):
  * the backfill days AT_RISK_DAYS or more old FIRST, oldest first: GA4 deletes the oldest days next (2 months'
    retention, in batches) and a deleted day can never be read again;
  * every REFRESH_HOURS the days not final yet (younger than FINAL_LAG: GA4 still adds to them) — the newest HOT_DAYS
    every time ("recent_at" is set as soon as they are read, so a run cut later in the backfill does not read them again
    next hour), an older one at most once a UTC day ("mid": {day: its last read}; GA4 moves a day most in its first
    days, and a read costs a funnel call per GROUP countries), after the final reads below; such an older day's answer
    collapsed against its stored read (as below) keeps that read, not final, for the next day's read;
  * a day read while not final is read once more when it is (≥ FINAL_LAG days old: GA4_FINAL_DAYS, owner 17 Nov 2026
    "max to max 7 din me to aa hi jaata he"), then the short days below; a day younger than FINAL_LAG the store kept as
    final (read final under a shorter lag: GA4_FINAL_DAYS raised), held ones aside, is not final again from the first
    run on ("fin" false, the store written even with no call made), so its final read comes at FINAL_LAG too;
  * the rest of the backfill, from the First open store's own first day (the All countries table's day 1; no store:
    BACKFILL_DAYS back), oldest first.
A day whose funnel GA4 answers empty: younger than AT_RISK_DAYS GA4 has not deleted it — nothing is stored and it is
asked again; older, it is kept as {"none": true, "why": "ga4"} with the first opens GA4's report still gives per country
("fo": the report is not cut by the retention; the page shows them, the funnel steps "—"), asked once more on a later
run (GONE_CONFIRM answers) before it is final. Nothing is stored as zeros.
A day GA4 answers COLLAPSED is never kept for a whole one (16 Nov 2026: GA4 answered 11 – 13 Nov almost empty, or with
most first opens in no country, at their final read, D+3 00:0x UTC, and this store kept that for good — the final read
replaced the day's earlier, whole one):
  * the final read of a day read before (not final) whose answer collapsed against that read — a part of it (first
    opens, the splash or home step; in all or by country) under SHORT × the same part there (REF_MIN or more; the
    steps only under the same screens, "sg": the First open store picks them again every week), GA4's funnel empty or
    gone, or GA4 naming no country — keeps the earlier read, final, marked "ho" (held: short, below), so such a day is
    never read every run until GA4 deletes it;
  * a SHORT day is read again: a final day whose first opens are under SHORT × the First open store's own count of the
    day (fetch.ga4_firstopen: the same funnel's first_open, read again every 6 h for 15 days, so it heals; judged at
    REF_MIN or more), with a step NONAME or more in no named country (and REF_MIN or more — measured on the real
    stores: a whole day's stay under 5 %), one stored as "GA4 named no country" while that count says the day had
    first opens, or a held one. It is read again REFRESH_HOURS after its last try ("rat", set before the read: a try a
    Stop cuts waits too), the wait doubled with every finished try (6, 12, 24, 48 h: rr_wait), while GA4 still keeps it
    (younger than AT_RISK_DAYS), at most RR_MAX finished tries ("rr": GA4 may hold a real hole — never read forever).
    GA4's new answer replaces the stored day only when no part of it is under the most the day ever held (its own, or
    "pm" kept from the answers it replaced) beyond GA4's own noise (NOISE of it, SAMPLED_NOISE when GA4 sampled one of
    the answers — "smp" —, or 1 user) and one is bigger (better)
    — a short-again, no-country or gone answer never takes its place. Known limit: across a screens change only the
    first opens compare (GA4 losing only the steps then can not be told from the change; never seen on the stores).
The log: "held" (final answers collapsed against the day's earlier read), "short read again", "healed" (no longer
short), "short left" (short days GA4 still keeps, over every app with a store).
Properties run side by side (each has its own quota), the property whose apps waited longest first (each app's
"turn"), so a big property never keeps the others waiting run after run. Within a day, the group calls go up to BATCH
side by side — only when the property's last quota snapshot and the run's clock show the one-at-a-time calls would all
have gone (App.batch_ok, with room); their answers are read in group order, so the day's record is the same.
Switched by GA4_FIRSTOPEN_CC (on by default in the workflow).
Never raises; never prints (log_line: counts only).
"""
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import ga4_final
from .. import ga4_probe
from ..db import write_json_gz_stable
from . import ga4
from . import ga4_audience as gaud
from . import ga4_firstopen as gf
from . import ga4_uninstall as gu

DIR = "ga4_firstopen_cc"
STORE_V = 1
GROUP = gf.CHUNK                    # GA4's funnel breakdown returns at most 15 values per call
DIM = "countryId"
RT = "RESERVED_TOTAL"               # GA4's own total row in a funnel breakdown
HOT_DAYS = 3                        # today … 2 days back: read again every REFRESH_HOURS (this store's window
#                                     before the knob)
FINAL_LAG = ga4_final.lag(3)        # a day is final from this many days old on — GA4_FINAL_DAYS, at least 3: the First
#                                     open page's edge (== ga4_firstopen.FINAL_LAG)
RECENT_DAYS = FINAL_LAG             # the days not final yet (today … FINAL_LAG − 1 days back): the newest HOT_DAYS
#                                     every REFRESH_HOURS, the older ones (mid_days) at most once a UTC day
BACKFILL_DAYS = 120                 # how far back without a First open store day 1 (with one: from that day)
AT_RISK_DAYS = 50                   # a day this old may be the next GA4 deletes: read before the recent refresh;
                                    # an empty funnel answer for a younger day is never taken as "gone"
GONE_CONFIRM = 2                    # empty funnel answers (on different runs) before a day is final as gone
SHORT = 0.5                         # a final day under this × the First open store's count of the day: read again
REF_MIN = 20                        # … judged only when that count is at least this many first opens
NONAME = 0.1                        # … or this share of its first opens (and REF_MIN or more) in no named country
NOISE = 0.02                        # a part of GA4's new answer this much (or 1 user) under the stored day's: noise
SAMPLED_NOISE = 0.1                 # … this much when GA4 sampled one of the answers ("smp"; measured: two big apps'
                                    # sampled days sit within ±5–11 % of the First open store's, p05–p95)
RR_MAX = 4                          # a short day read again at most this many times (≥ REFRESH_HOURS apart)
REFRESH_HOURS = 6.0
MAX_CALLS = 150                     # per app per run, passed to the App (the backfill goes on next run)
BUDGET_SEC = 240
RETRY_HOURS = 3.0
WORKERS = 10                        # properties read side by side (each its own quota; one call at a time each …)
                                    # GA4_FIRSTOPEN_CC_WORKERS (env) 6: as before
BATCH = 5                           # … but a day's group calls up to this many side by side when the one-at-a-time
                                    # calls would all go (App.funnel_many; GA4 allows 10 concurrent per property).
                                    # GA4_FIRSTOPEN_CC_BATCH (env) 1: one at a time, as before


def sig(steps):
    return hashlib.sha1(("%s|%s" % (steps.get("splash"), steps.get("home"))).encode()).hexdigest()[:8]


def group_body(splash, home, day, ccs):
    """The strict Home funnel of one day, step 1 = first_open in `ccs` (≤ GROUP), broken down by country."""
    b = gf.funnel_body(splash, home, day, day, DIM)
    b["funnel"]["steps"][0]["filterExpression"] = {"andGroup": {"expressions": [
        {"funnelEventFilter": {"eventName": "first_open"}},
        {"funnelFieldFilter": {"fieldName": DIM, "inListFilter": {"values": sorted(ccs)}}}]}}
    return b


def _three(t, key=None):
    """parse_table's {step: {value: users}} → [first_open, splash, home] of one value (key) or of all but RT."""
    pick = (lambda d: d.get(key, 0)) if key is not None else (lambda d: sum(v for b, v in d.items() if b != RT))
    return [pick(t.get("first_open") or {}), pick(t.get("splash") or {}), pick(t.get("step") or {})]


def countries(ga, a, b):
    """first_open users by country of every day a … b → {D: {cc: users}} (GA4's "(not set)" left out: it can not be a
    group's filter value; it stays in the day's total)."""
    rows = ga.report_all({"dateRanges": [{"startDate": a.isoformat(), "endDate": b.isoformat()}],
                          "dimensions": [{"name": "date"}, {"name": DIM}], "metrics": [{"name": "activeUsers"}]},
                         event="first_open")
    out = {}
    for r in rows:
        d, cc = str(r.get("date") or ""), str(r.get(DIM) or "")
        if len(d) == 8 and d.isdigit() and cc and cc not in ga4.NOT_SET:
            out.setdefault("%s-%s-%s" % (d[:4], d[4:6], d[6:]), {})[cc] = int(r.get("activeUsers") or 0)
    return out


def calls_for(ccs):
    """The funnel calls one day costs: its total + one per group of GROUP countries."""
    return 1 + -(-len(ccs) // GROUP)


def is_gone(rec):
    return isinstance(rec, dict) and bool(rec.get("none")) and rec.get("why") == "ga4"


def _int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


STEPS_AT = (1, 2, 4, 5)             # _parts' splash / home (the day's, the named countries'): screens-dependent


def _parts(rec):
    """A stored day's (first opens, splash, home — its total —, then the same three summed over its named countries);
    all 0 for a day with no funnel (no country / gone)."""
    if not isinstance(rec, dict) or rec.get("none"):
        return (0, 0, 0, 0, 0, 0)
    t = list(rec.get("t") or []) + [0, 0, 0]
    named = [0, 0, 0]
    for v in (rec.get("c") or {}).values():
        if isinstance(v, (list, tuple)):
            for j in range(min(3, len(v))):
                named[j] += _int(v[j])
    return (_int(t[0]), _int(t[1]), _int(t[2]), named[0], named[1], named[2])


def _fo(rec):
    """A stored day's first opens (its funnel total's step 1); 0 for a day with no funnel (no country / gone)."""
    return _parts(rec)[0]


def _idx(new, old):
    """The parts two answers of a day compare by: the first opens always (in all, by country); the splash / home steps
    only when both were read with the same screens ("sg": the First open store picks them again every week — a screens
    change is no collapse; under other screens GA4 losing only the steps can not be told from it)."""
    same = isinstance(new, dict) and isinstance(old, dict) and bool(new.get("sg")) and new.get("sg") == old.get("sg")
    return [i for i in range(6) if same or i not in STEPS_AT]


def _compared(new, old):
    """The (new, old) pairs of the parts the two answers compare by (_idx)."""
    n, o = _parts(new), _parts(old)
    return [(n[i], o[i]) for i in _idx(new, old)]


def _floor(rec):
    """The most each part of a stored day ever held: its own, or "pm" — the best of the answers it replaced (read with
    its screens). GA4's noise is measured against it, so tries never add their noise up."""
    p = list(_parts(rec))
    pm = rec.get("pm") if isinstance(rec, dict) else None
    if isinstance(pm, list) and len(pm) == 6:
        p = [max(a, _int(b)) for a, b in zip(p, pm)]
    return p


def is_short(rec, ref):
    """A stored day GA4 answered collapsed (module doc): a final day whose first opens are under SHORT × ref (the First
    open store's count of the day; ref None or under REF_MIN: not judged so), with a step (first opens, splash or home)
    NONAME or more in no named country (and REF_MIN or more), one stored as "GA4 named no country" while ref says it had
    first opens, or a held one ("ho"). A day read while not final (or all zeros) is due() "again"'s; a gone day its
    own."""
    if not isinstance(rec, dict):
        return False
    judged = not isinstance(ref, bool) and isinstance(ref, (int, float)) and ref >= REF_MIN
    if rec.get("none"):
        return judged and rec.get("why") != "ga4"
    if not rec.get("fin") or not any(rec.get("t") or []):
        return False
    p = _parts(rec)
    if rec.get("ho") or any(p[j] - p[j + 3] >= max(REF_MIN, NONAME * p[j]) for j in range(3)):
        return True
    return judged and p[0] < SHORT * ref


def _sampled(rec):
    """GA4 read only a share of the day's events for this answer ("smp" under 1)."""
    if not isinstance(rec, dict) or rec.get("smp") is None:
        return False
    try:
        return float(rec["smp"]) < 1
    except (TypeError, ValueError):
        return False


def _noisy(new, old):
    """GA4 sampled the new answer, the stored day, or an answer the stored day's floor ("pm") comes from ("pms")."""
    return _sampled(new) or _sampled(old) or bool(isinstance(old, dict) and old.get("pms"))


def better(new, old):
    """GA4's new answer of a short day takes the stored day's place: no part of it (_idx: first opens, splash and home —
    in all and by country) under the most the stored day ever held (_floor) beyond GA4's own noise (NOISE of it — or
    SAMPLED_NOISE when GA4 sampled an answer of it, _noisy — or 1 user), and more in one of them — or, for a held day
    (its earlier read kept), the final answer it waited for. A day with no funnel counts 0 everywhere."""
    if not isinstance(new, dict) or new.get("none"):
        return False
    idx, n, o, f = _idx(new, old), _parts(new), _parts(old), _floor(old)
    tol = SAMPLED_NOISE if _noisy(new, old) else NOISE
    if any(n[i] < f[i] - max(1, tol * f[i]) for i in idx):
        return False
    return any(n[i] > o[i] for i in idx) or bool(isinstance(old, dict) and old.get("ho"))


def _best(new, old):
    """The "pm" GA4's new answer takes over from the stored day it replaces (better): the most each part ever held —
    None when the answer holds it all itself (the steps under other screens: the new answer's own)."""
    n, f, idx = _parts(new), _floor(old), set(_idx(new, old))
    pm = [max(n[i], f[i]) if i in idx else n[i] for i in range(6)]
    return pm if pm != list(n) else None


def collapsed(new, old):
    """GA4's final answer of a day against the day's own earlier read (old: a whole record): a part of it (_compared) —
    first opens, the splash or home step, in all or by country — under SHORT × the same part there (REF_MIN or more)."""
    return any(b >= REF_MIN and a < SHORT * b for a, b in _compared(new, old))


def _kept(prev):
    """An earlier read of a day kept as its final one (held): GA4's final answer collapsed against it."""
    return isinstance(prev, dict) and not prev.get("none") and not prev.get("fin") and any(prev.get("t") or [])


def mid_days(today):
    """The days not final yet beyond the newest HOT_DAYS (HOT_DAYS … FINAL_LAG − 1 days old), newest first — read at
    most once a UTC day; none while FINAL_LAG is HOT_DAYS (GA4_FINAL_DAYS 3: every day not final is a hot one)."""
    return [today - timedelta(days=i) for i in range(HOT_DAYS, RECENT_DAYS)]


def mid_read(store, k, now):
    """Was day k read this UTC day as one of the mid_days ("mid": {day: the UTC time of its last read})?"""
    mid = store.get("mid")
    return isinstance(mid, dict) and str(mid.get(k) or "")[:10] == gu._now_iso(now)[:10]


def _funnel(prev):
    """A stored read of a day with a funnel answer (not "none", some first opens) — whole or not, final or not."""
    return isinstance(prev, dict) and not prev.get("none") and any(prev.get("t") or [])


def rr_wait(rec):
    """Hours a short day waits after its last try ("rat") or answer ("at"): REFRESH_HOURS, doubled with every finished
    try (6, 12, 24, 48 h — RR_MAX tries cover about 4 days of GA4 holding it)."""
    return REFRESH_HOURS * 2 ** min(_int(rec.get("rr")), RR_MAX)


def short_due(store, today, now, ref):
    """The short days to read again this run, oldest first: final (≤ today − FINAL_LAG), younger than AT_RISK_DAYS (GA4
    still keeps them), fewer than RR_MAX finished tries, their last try or answer rr_wait hours ago or more."""
    fin_edge = today - timedelta(days=FINAL_LAG)
    ref = ref or {}
    out = []
    for k, v in (store.get("days") or {}).items():
        d = gu._d(k)
        if (d <= fin_edge and (today - d).days < AT_RISK_DAYS and is_short(v, ref.get(k))
                and _int(v.get("rr")) < RR_MAX
                and gu._hours_since(v.get("rat") or v.get("at"), now) >= rr_wait(v)):
            out.append(d)
    return sorted(out)


def short_left(store, today, ref):
    """The short days GA4 still keeps (younger than AT_RISK_DAYS, final) — however many tries they had: the log's
    "short left" (a day still there after RR_MAX tries stays counted: GA4 kept it so)."""
    fin_edge = today - timedelta(days=FINAL_LAG)
    ref = ref or {}
    return sum(1 for k, v in ((store or {}).get("days") or {}).items()
               if gu._d(k) <= fin_edge and (today - gu._d(k)).days < AT_RISK_DAYS and is_short(v, ref.get(k)))


def ref_counts(main):
    """The First open store's count of every day it holds ({D: first_open}) — the short days' reference."""
    out = {}
    for k, v in ((main or {}).get("days") or {}).items():
        if isinstance(v, dict):
            try:
                out[str(k)] = int(v.get("first_open") or 0)
            except (TypeError, ValueError):
                continue
    return out


def read_day(ga, steps, day, ccs, today, now_iso, prev=None):
    """One day → its record (every group read, or Stop: a day is kept only whole), or None (nothing to store yet)."""
    j = ga.funnel(gf.funnel_body(steps["splash"], steps["home"], day, day, "date"))
    tot, smp = _three(gf.parse_table(j)), gf.sampling(j)
    if not any(tot):                                    # GA4's report named first opens that day, its funnel nothing
        if (today - day).days < AT_RISK_DAYS:
            return None                                 # not deleted yet (too young): a lag or a blip — asked again
        n = (int(prev.get("n") or 1) + 1) if is_gone(prev) else 1
        return {"none": True, "why": "ga4", "n": n, "fo": {k: int(v) for k, v in ccs.items()}, "at": now_iso}
    c = {}
    order = sorted(ccs, key=lambda k: (-ccs[k], k))
    groups = [order[i:i + GROUP] for i in range(0, len(order), GROUP)]
    for grp, j in _answers(ga, [(g, group_body(steps["splash"], steps["home"], day, g)) for g in groups]):
        t, s = gf.parse_table(j), gf.sampling(j)
        if s is not None:
            smp = s if smp is None else min(smp, s)
        for cc in grp:
            v = _three(t, cc)
            if any(v):
                c[cc] = v
    return {"c": c, "t": tot, "smp": smp, "fin": (today - day).days >= FINAL_LAG, "sg": sig(steps), "at": now_iso}


def _batch():
    try:
        return max(1, int(os.getenv("GA4_FIRSTOPEN_CC_BATCH") or BATCH))
    except ValueError:
        return BATCH


def _workers():
    """Properties read side by side: GA4_FIRSTOPEN_CC_WORKERS (env; empty or not a number: WORKERS)."""
    try:
        return max(1, int(os.getenv("GA4_FIRSTOPEN_CC_WORKERS") or WORKERS))
    except ValueError:
        return WORKERS


def _answers(ga, groups):
    """[(group, funnel body)] → (group, GA4's answer) in group order: as many as BATCH side by side as the App can tell
    the one-at-a-time calls would all go (funnel_many; else None — fewer tried, down to 2), one at a time otherwise —
    the same answers, in the same order, so the day's record is the same."""
    many, n, i = getattr(ga, "funnel_many", None), _batch(), 0
    while i < len(groups):
        chunk, got = groups[i:i + n], None
        for m in range(len(chunk) if many else 1, 1, -1):
            got = many([b for _, b in chunk[:m]])
            if got is not None:
                chunk = chunk[:m]
                break
        if got is None:                                 # (alone: measured, the margin of a later batch)
            chunk = chunk[:1]
            got = [ga.funnel(chunk[0][1], measure=True) if many else ga.funnel(chunk[0][1])]
        for (g, _), j in zip(chunk, got):
            yield g, j
        i += len(chunk)


def due(store, today, now, first=None, ref=None):
    """The days to read this run, in order: the backfill days AT_RISK_DAYS or more old (oldest first), the recent ones
    (when due: the newest HOT_DAYS), the not-final ones now final, the short days read again (short_due against ref,
    the First open store's counts; oldest first), the mid_days not read this UTC day (with the recent ones: when due;
    after the final reads, kept for good), then the rest of the backfill (oldest first). The backfill = every day from
    `first` (the First open store's first day; else BACKFILL_DAYS back) to FINAL_LAG days back the store has no record
    for, and the gone days not yet confirmed (asked again REFRESH_HOURS after their last answer)."""
    days = store.get("days") or {}
    recent, mid = [], []
    if gu._hours_since(store.get("recent_at"), now) >= REFRESH_HOURS:
        recent = [today - timedelta(days=i) for i in range(HOT_DAYS)]
        mid = [d for d in mid_days(today) if not mid_read(store, d.isoformat(), now)]
    fin_edge = today - timedelta(days=FINAL_LAG)
    again = sorted(gu._d(k) for k, v in days.items()            # read while not final, or stored as all zeros
                   if not v.get("none") and (not v.get("fin") or not any(v.get("t") or [])) and gu._d(k) <= fin_edge)
    back = [gu._d(k) for k, v in days.items()                   # gone once: asked again on a later run
            if is_gone(v) and int(v.get("n") or 1) < GONE_CONFIRM and gu._hours_since(v.get("at"), now) >= REFRESH_HOURS]
    d = first or (today - timedelta(days=BACKFILL_DAYS))
    while d <= fin_edge:
        if d.isoformat() not in days:
            back.append(d)
        d += timedelta(days=1)
    back.sort()
    risk = [d for d in back if (today - d).days >= AT_RISK_DAYS]
    out = risk + recent + again + short_due(store, today, now, ref) + mid + back[len(risk):]
    seen, uniq = set(), []
    for d in out:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


def step_app(ga, store, steps, today, now, first=None, ref=None, tally=None):
    """One app's run on its store → "fetched" / "fresh". Raises Stop (the days read so far are kept): the property's
    quota floor, the run's clock, or the app's call cap — checked BEFORE a day is begun (all its calls must fit).
    ref: the First open store's counts (ref_counts) — the short days; tally: {"held", "reread", "healed", "unfin" (days
    kept final under a shorter lag made not final again)} counted into.
    A day GA4 answers collapsed never replaces a whole one (module doc): a final answer collapsed against the day's
    earlier read keeps that read (held); an answer of a mid_days day collapsed against its stored read keeps that read,
    not final (read again the next UTC day; its final read follows the held rule); a short day takes GA4's new answer
    only when it is better. A mid_days day read (whatever GA4 answered) is not read again this UTC day ("mid")."""
    now_iso = gu._now_iso(now)
    tally = {} if tally is None else tally
    stored = store.get("days")
    if isinstance(stored, dict):                        # a day not final yet that the store kept as final — read under
        for k, v in stored.items():                     # a shorter lag (GA4_FINAL_DAYS raised): not final again, so
            if (isinstance(v, dict) and v.get("fin") and not v.get("ho")    # its final read comes at FINAL_LAG ("again")
                    and (today - gu._d(k)).days < FINAL_LAG):              # — counted: the store is written (refresh_all)
                stored[k] = dict(v, fin=False)
                tally["unfin"] = tally.get("unfin", 0) + 1
    todo = due(store, today, now, first, ref)
    if not todo:
        return "fresh"
    days = store.setdefault("days", {})
    rr = set(short_due(store, today, now, ref))         # the short days read again (each kept only if better)
    cc = countries(ga, min(todo), max(todo))
    recent = {today - timedelta(days=i) for i in range(RECENT_DAYS)}     # not final yet (never stored as no country)
    mids = set(mid_days(today))                         # … the older of them: read at most once a UTC day
    left = {d for d in todo if d in recent and d not in mids}    # the newest (HOT_DAYS) still to read this run
    if "mid" in store:                                  # a day that left mid_days (final now) leaves "mid"
        band = {d.isoformat() for d in mids}
        kept = {k: v for k, v in (store["mid"] if isinstance(store["mid"], dict) else {}).items() if k in band}
        if kept:
            store["mid"] = kept
        else:
            del store["mid"]
    cap = getattr(ga, "max_calls", None)
    did = False

    def hold(k, prev):                                  # GA4's final answer collapsed: the earlier read stays, final
        days[k] = dict(prev, fin=True, ho=1, rat=now_iso)
        tally["held"] = tally.get("held", 0) + 1
    for d in todo:
        k = d.isoformat()
        prev = days.get(k)
        if d in rr:                                     # a short day: GA4's new answer only if it is better
            rec = None
            if cc.get(k):                               # (GA4 naming no country again: nothing read, the day kept)
                if cap is not None and ga.calls + calls_for(cc[k]) > cap:
                    raise gf.Stop("calls")
                days[k] = prev = dict(prev, rat=now_iso)    # the try's time first: one a Stop cuts waits too
                rec = read_day(ga, steps, d, cc[k], today, now_iso, prev)
            n = _int(prev.get("rr")) + 1
            if better(rec, prev):
                rec["rr"] = n
                pm = _best(rec, prev)                   # the most each part ever held, when this answer is under it
                if pm:                                  # (within GA4's noise): the next try is measured against it
                    rec["pm"] = pm
                    if _noisy(rec, prev):               # … with the sampled answers' noise when one of them was
                        rec["pms"] = 1
                days[k] = rec
                if not is_short(rec, (ref or {}).get(k)):
                    tally["healed"] = tally.get("healed", 0) + 1
            else:                                       # short, no country, or gone again: the stored day stays
                days[k] = dict(prev, rr=n, rat=now_iso)
            tally["reread"] = tally.get("reread", 0) + 1
            did = True
            continue
        if cc.get(k):
            if cap is not None and ga.calls + calls_for(cc[k]) > cap:
                raise gf.Stop("calls")                  # the day would be cut: next run, from this day on
            rec = read_day(ga, steps, d, cc[k], today, now_iso, prev)
            if ((today - d).days >= FINAL_LAG and _kept(prev)    # the final read of a day read before: GA4's funnel
                    and (rec is None or rec.get("none") or collapsed(rec, prev))):   # empty, gone or collapsed —
                hold(k, prev)                           # the earlier read stays (never read every run till gone)
                did = True
            elif d in mids and rec is not None and _funnel(prev) and collapsed(rec, prev):
                days[k] = dict(prev, fin=False)         # a mid day collapsed against its stored read: that read stays,
                did = True                              # not final (one kept from an older, shorter lag too)
            elif rec is not None:
                days[k] = rec
                did = True
            elif is_gone(prev):                         # an older "gone" for a day too young for that: not read yet
                del days[k]
                did = True
        elif d not in recent:                           # GA4 names no country that day (no install / "(not set)" only)
            if _kept(prev):                             # … a day it named countries for before: collapsed, held
                hold(k, prev)
            else:
                days[k] = dict(prev, n=GONE_CONFIRM, at=now_iso) if is_gone(prev) else {"none": True, "at": now_iso}
            did = True
        if d in mids:                                   # read this UTC day: not again before the next
            store.setdefault("mid", {})[k] = now_iso
        if d in left:
            left.discard(d)
            if not left:
                store["recent_at"] = now_iso            # refreshed: not again for REFRESH_HOURS, even if a later day stops
    return "fetched" if did else "fresh"


# ── store and state ─────────────────────────────────────────────────────────────────────────────────────────────────
def store_path(data_dir, app_id):
    return os.path.join(data_dir, DIR, gu.file_key(app_id) + ".json.gz")


def load_store(path):
    s = gu.load_store(path)
    return s if isinstance(s, dict) and s.get("v") == STORE_V else None


def load_state(data_dir):
    try:
        with open(os.path.join(data_dir, DIR, "state.json"), encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict) and isinstance(raw.get("fetch"), dict):
            return raw
    except (OSError, ValueError):
        pass
    return {"v": 1, "fetch": {}}


def save_state(data_dir, state):
    path = os.path.join(data_dir, DIR, "state.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=1)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return True


COUNTS = ("selected", "with_store", "fetched", "fresh", "no_steps", "failed", "deferred", "days", "held", "reread",
          "healed", "short", "calls", "tokens")


def refresh_all(cfg, data_dir, apps, now=None, clock=time.monotonic, budget=BUDGET_SEC, workers=None):
    """Every selected app with a First open store → {"counts", "apps": {app id: fetched|fresh|no_steps|failed|
    deferred}}; workers: properties side by side (None: _workers()). Never raises; never prints."""
    now = now or datetime.now(timezone.utc)
    t0 = clock()
    counts = dict.fromkeys(COUNTS, 0)
    out = {"counts": counts, "apps": {}}
    lock = threading.Lock()
    try:
        state = load_state(data_dir)
        ust = gu.load_state(data_dir)
        routes = ust["routes"].get("by_package") or {}
        tokens, _ = ga4_probe.owner_tokens({"GA4_REFRESH_TOKENS": cfg.get("refresh_tokens") or "",
                                            "GA4_REFRESH_TOKEN": cfg.get("refresh_token") or ""})
        owner_rt, access = dict(tokens), {}
        now_iso = gu._now_iso(now)

        def over():
            return "budget" if clock() - t0 >= budget else None
        over.left = lambda: budget - (clock() - t0)    # (App.batch_ok: the run's seconds left)
        by_prop, mains, counted = {}, {}, set()      # (every app with a store: its short days counted, read or not)
        for a in apps:
            if a.get("same_as") or not a.get("package"):
                continue
            counts["selected"] += 1
            aid = a["app_id"]
            main = gf.load_store(gf.store_path(data_dir, aid))
            r = routes.get(a["package"])
            if not main or not r:
                continue
            counts["with_store"] += 1
            mains[aid] = (main, r)
            steps = main.get("steps") or {}
            if not steps.get("splash") or not steps.get("home"):
                out["apps"][aid] = "no_steps"
                continue
            st = state["fetch"].setdefault(aid, {})
            if st.get("fail") and gu._hours_since(st.get("last_try"), now) < RETRY_HOURS:
                out["apps"][aid] = "failed"
                continue
            owner = r.get("owner")
            if owner not in access:
                try:
                    access[owner] = (ga4.access_token(cfg["client_id"], cfg["client_secret"], owner_rt[owner])
                                     if owner in owner_rt else None)
                except Exception:
                    access[owner] = None
            by_prop.setdefault(r["property_id"], []).append((a, st, r, steps, main))
        for xs in by_prop.values():                     # the app that waited longest goes first (no turn yet = first)
            xs.sort(key=lambda t: (t[1].get("turn") or "", t[0]["app_id"]))
        order = sorted(by_prop, key=lambda p: (min(t[1].get("turn") or "" for t in by_prop[p]), p))

        def one_prop(pid):
            prop = {"quota": None, "stop": None}
            for a, st, r, steps, main in by_prop[pid]:
                aid = a["app_id"]
                if over() or prop["stop"]:
                    with lock:
                        st["deferred"] = True
                        out["apps"][aid] = "deferred"
                    continue
                tok = access.get(r.get("owner"))
                if not tok:
                    with lock:
                        st.update(last_try=now_iso, fail="auth")
                        out["apps"][aid] = "failed"
                    continue
                tz = main.get("time_zone") or (ust["tz"].get(pid) or "UTC")
                today = now.astimezone(ZoneInfo(tz)).date()
                mdays = sorted(main.get("days") or {})  # the All countries table's day 1 (as the build reads it)
                first = gu._d(mdays[0]) if mdays else None
                path = store_path(data_dir, aid)
                store = load_store(path) or {"v": STORE_V}
                n0 = len(store.get("days") or {})
                ref, tally = ref_counts(main), {}   # the First open store's counts: the short days' reference
                ga = gf.App(tok, pid, r["stream_id"], prop, over=over, max_calls=MAX_CALLS)
                try:
                    res = step_app(ga, store, steps, today, now, first, ref=ref, tally=tally)
                    upd = dict(last_try=now_iso, fail=None)
                    if res == "fetched":
                        upd["last_ok"] = now_iso
                except gf.Stop:
                    res, upd = "deferred", {"deferred": True}
                except Exception as e:
                    res, upd = "failed", dict(last_try=now_iso, fail=gu._fail_kind(e))
                # (a short day's try is kept even with no call made: never tried again at once; so is a day made not
                # final again)
                if ga.calls or tally.get("reread") or tally.get("held") or tally.get("unfin"):
                    store.update(v=STORE_V, app_id=aid, package=a["package"], property_id=pid,
                                 stream_id=r["stream_id"], time_zone=tz)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    write_json_gz_stable(path, store)
                with lock:
                    if res != "deferred":
                        st.pop("deferred", None)
                    st.update(upd)
                    st["turn"] = now_iso                # it had its turn (a cut-off app goes last next time too)
                    st["key"] = gu.file_key(aid)
                    out["apps"][aid] = res
                    counts["calls"] += ga.calls
                    counts["tokens"] += ga.tok
                    counts["days"] += max(0, len(store.get("days") or {}) - n0)
                    counts["held"] += tally.get("held", 0)
                    counts["reread"] += tally.get("reread", 0)
                    counts["healed"] += tally.get("healed", 0)
                    counts["short"] += short_left(store, today, ref)
                    counted.add(aid)

        with ThreadPoolExecutor(max_workers=max(1, workers or _workers())) as ex:
            list(ex.map(one_prop, order))
        save_state(data_dir, state)
        for aid, (main, r) in sorted(mains.items()):   # the apps not read this run (deferred, waiting, no screens):
            if aid in counted:                          # their short days stay counted — never a silent 0
                continue
            try:
                tz = main.get("time_zone") or (ust["tz"].get(r.get("property_id")) or "UTC")
                counts["short"] += short_left(load_store(store_path(data_dir, aid)), now.astimezone(ZoneInfo(tz)).date(),
                                              ref_counts(main))
            except Exception:
                continue
    except Exception as e:                              # a bug here must never cost the build
        out["error"] = type(e).__name__
    for v in out["apps"].values():
        if v in counts:
            counts[v] += 1
    return out


def log_line(status):
    """The build log's ONE line for this step — counts only."""
    c = (status or {}).get("counts") or {}
    return ("ga4 first open by country: apps %d, with store %d, fetched %d, fresh %d, no screens %d, failed %d, "
            "deferred %d, new days %d, held %d, short read again %d, healed %d, short left %d, calls %d, tokens %d%s"
            % tuple([gaud._int(c.get(k)) for k in COUNTS] + [(", error " + status["error"])
                                                             if (status or {}).get("error") else ""]))
