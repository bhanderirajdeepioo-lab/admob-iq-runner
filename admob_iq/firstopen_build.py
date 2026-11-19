"""🆕 First open tab — the build step: of the users opening an app for the first time, how many reach the Splash and,
after it in order, the Home (and Language / Permission / Intro) — Today / Yesterday, the last 7 days vs the usual, and the
FULL history kept by fetch.ga4_firstopen (owner, 13 Oct 2026: every feature on the whole history, at a glance what is a
problem, good or normal).

ONE lazy file, site/firstopen.json.gz:
  {"v", "apps": [{key, app, app_id, steps {step: screen class}, steps_changed, first_day, final_till (the property's
                  today − FIN_LAG: a newer day is not final), td (the property's today; at GA4_FINAL_DAYS 3, the
                  rollback, final till is today − 2 and no td: the file as before the knob),
                  days: [[YYYY-MM-DD, first_open, splash, home, splash_any, home_any, language, permission, intro,
                          sample (GA4 read only this share of the events: the numbers are estimates) | null,
                          x (1: first_open / splash / home are the country store's exact ones — EXACT COUNTS below;
                          only with FIRSTOPEN_EXACT on)], …]}],
   "summary": [{key, app, status, why, s2h, usual, change, s2h_any, opened, opened_usual, fo_day, fo_day_usual,
                steps {language|permission|intro: [share of Splash, last 7 days], usual}, final_days,
                sample (the lowest of the 7 days whose first_open / splash / home are GA4's sampled ones, or null),
                sample_other (the lowest of the 7 days, for the steps that stay sampled: splash_any, home_any,
                language, permission, intro — only with FIRSTOPEN_EXACT on)}]}
and the pointer dashboard["firstopen"] = {"file", "v", "apps": {app: {status, s2h, usual, change, fo_day, id}}} (the hub's
card and the tab's nav item read it). Every day of every store, nothing trimmed.

EXACT COUNTS (owner, 17 Nov 2026: "Haan, banao" — the All countries counts of the apps whose funnel GA4 samples):
the First open store reads 15 days a call and on the busiest apps GA4 SAMPLES every such read (it reads a share of the
events and scales them: "sample"; measured: every day of a few big apps, on some of them a small share of the events,
the day well off either way), while the country store (fetch.ga4_firstopen_cc) reads the SAME funnel one day at a
time and mostly gets it whole. A day the First open store read sampled whose country store record is whole and
unsampled — not held ("ho"), read once the day was final here (EX_AGE days after it or later; or kept as final by the
country store under the lag in force then, of a day final here: EX_AGE0), with the screens that
day's First open read had (its last read: _day_sig, from "steps_changed"), with first opens and a Splash, no step much
in no named country, not collapsed against the First open store's count of the day or the store's own days around it
(exact_days) — takes first_open / splash /
home from that record's day total, exact, and its row says so (x = 1); its other steps (splash_any, home_any, language,
permission, intro) stay GA4's sampled estimates (the page marks those cells ≈, the day itself not), and a step's share
of Splash stays that read's own (summarize: sp). Every other day as before. The summary's "sample" is then the lowest
of the 7 days whose three are still sampled, "sample_other" the lowest of the 7 days for the other steps. Switch
FIRSTOPEN_EXACT (s["firstopen_exact"]; off: every row and the summary exactly as before — no x, no sample_other). The
log line: "exact days"; a failure: "first open exact skipped: <kind>" (the rows as before). Known limit: the First
open store checks its screens and refreshes its last 15 days on clocks of their own, so for up to one refresh after a
screens change its newest days may still hold the old screens' reads while _day_sig already names the new ones (a
country day read with the new screens can be paired with such a row until that refresh reads it again).

BY COUNTRY (owner, 20 Oct 2026: "country wise bhi dekh saku esa kara do"): per app with a country store (fetch.
ga4_firstopen_cc, ≥ 1 real day) ONE more lazy file next to it, site/firstopen_cc_<key>.json.gz (key = the app's own):
  {"v", "key", "app_id", "final_till" (the app's), "first_day", "last_day" (the newest real day),
   "missing" (days of the status window final_till − 34 … final_till the store has no real day for; 0 = whole),
   "days": [[YYYY-MM-DD, first_open, splash, home (the day's total), sample | null, {cc: [first_open, splash, home]}], …]
           (every real day of the store, ascending, nothing trimmed — it can have holes; only these three steps exist
           per country),
   "summary": [{cc, status, why, s2h, usual, change, opened, opened_usual, fo_day, fo_day_usual, final_days, sample,
                share (the country's first opens ÷ the day totals', the same 7 days)}]   (EVERY country GA4 named; the
                app's own status rule, summarize() on rows in the app's row layout, fed only the UNBROKEN run of
                calendar days that ends at final_till: a hole (the backfill reads oldest / newest in turn) or a lag (a
                deferred / switched-off fetch) inside the 35 days = Too early with the why, never a window across a hole
                or weeks old; first opens of the 7 days first),
   "unnamed": {"summary": {fo_day, opened, s2h, share}}}   (the day's total − every named country: users GA4 named no
                country for; measured as is, slightly negative on sampled days, never clamped)
and the app's entry in firstopen.json.gz gets "cc": {file, v, from, last, n, days} — only when that file was written. A
failure or a too big file costs only that app's country file; stale country files are removed; the splat rule covers them.

INSTALLED BUT NEVER OPENED (owner, 2 Nov 2026: "google ads ka install bhi dikhao taki pata chale kitna open hi nahi kar
raha he user"; "google ads se aaya hua aur firebase me dikh rahaa dono"): per app with Google Ads store-days
(fetch.gads_inst_day, by its Play package) or GA4 first opens by country (fetch.ga4_newusers) ONE more lazy file,
site/firstopen_ads_<key>.json.gz:
  {"v", "key", "app_id", "first_day", "last_day", "ads_from" | null, "ga4_from" | null,
   "days": [[YYYY-MM-DD, [play, ads_fo, ga4_paid, ga4_all] (the day's totals), {cc: [play, ads_fo, ga4_paid, ga4_all]}],
            …]}   play = Google Play's installs from the app campaigns, ads_fo = Google Ads' first opens (both by the
           click day, the account's days), ga4_paid / ga4_all = GA4's first opens of Google Ads users / of everyone
           (the property's days); a part a source has not read for the day = null (never 0); "--" = no country named
           (Google Ads' unmapped ids and GA4's "(not set)"). Every day either source has, nothing trimmed.
and the app's entry gets "ads": {file, v, from, last, ads_from, ga4_from} — only when that file was written.

Status, per app: Splash → Home (Home ÷ Splash of the strict funnel) over the last 7 FINAL days (≤ final till: the
property's today − FIN_LAG, GA4_FINAL_DAYS) vs the 28 final days before: down ≥ 5 points Worse, ≥ 2 Watch, up ≥ 5
Better, else Normal; fewer than 35 final days Too early; fewer than 200 Splash users in the 7 days (or 400 in the 28)
N/A (too little data to judge).

run(dashboard, data_dir, out_dir, s) → the _headers no-store paths (["/firstopen*"], ONE splat rule) or [] (no store:
the file removed, no pointer). off(out_dir): the switch (FIRSTOPEN_TAB=false). Failure-isolated; ONE counts-only line.
"""
import gzip
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import ga4_final
from .db import write_json_gz_stable
from .fetch import ga4_firstopen as gf
from .fetch import ga4_uninstall as gu

FILE = "firstopen.json.gz"
HEADER_PATHS = ["/firstopen*"]
V = 1
MAX_GZ = 8 * 1024 * 1024
FIELDS = gf.FIELDS
WORSE, WATCH, BETTER = -0.05, -0.02, 0.05
MIN_DAYS, MIN_SPLASH7, MIN_SPLASH28 = 35, 200, 400
SX = len(FIELDS) + 1                # a day row's sample …
XI = SX + 1                         # … and its x (EXACT COUNTS; a row without it: x = 0)
CC_PREFIX = "firstopen_cc_"
CC_MAX_GZ = MAX_GZ                  # the same guard, per country file
CC_RE = re.compile(r"^firstopen_cc_[0-9a-f]{12}\.json\.gz$")
ADS_PREFIX = "firstopen_ads_"
ADS_RE = re.compile(r"^firstopen_ads_[0-9a-f]{12}\.json\.gz$")
CC_KEEP = ("status", "why", "s2h", "usual", "change", "opened", "opened_usual", "fo_day", "fo_day_usual", "final_days",
           "sample")
LINE = None


def enabled(s):
    return bool((s or {}).get("firstopen_tab", True))


def exact_on(s):
    return bool((s or {}).get("firstopen_exact", True))


def _x(r):
    return len(r) > XI and bool(r[XI])


FIN_LAG = ga4_final.page_lag(2, gf.FINAL_LAG)    # a day is final from this many days old on (GA4_FINAL_DAYS: the
#                                     First open store's final lag, == fetch.ga4_firstopen_cc's; at the rollback the
#                                     page's edge before the knob, 2): final till = today − FIN_LAG
EX_AGE = FIN_LAG                    # a country read counts once made this many property days after its day (once the
#                                     day is final: the First open store's reads of the page's final days are no newer)
EX_AGE0 = 2                         # … or, of a day final here, a read the country store kept as FINAL under the lag
#                                     in force then (its "fin": the reads made before GA4_FINAL_DAYS, at D+3, are never
#                                     read again) made this many days after it — EX_AGE before the knob
EDGES = not ga4_final.rollback()    # the app's "td" in the file; at the rollback the file as before the knob
EX_NB = 7                           # the country store's own whole days within ± this many of a day judge it …
EX_NB_MIN = 3                       # … when there are at least this many of them (same screens)
EX_LOW = 0.2                        # first opens under this × their median: an answer GA4 collapsed
EX_STEP = 0.5                       # Splash ÷ first opens, or Home ÷ Splash, under this × its median: collapsed too
EX_FLOOR = 0.2                      # … and first opens under this × the First open store's own (sampled) count of the
#                                     day (REF_MIN or more): collapsed (measured: a whole day never far under it)
EX_HALF = 0.5                       # first opens under this × EVERY reference there is (that count, the days around):
#                                     partly collapsed (one reference alone may be off: a sampled count, a real drop)


def _day_sig(store, d, sig):
    """The screens the First open store's LAST read of day d was made with — it reads a day again while it is
    RECENT_DAYS − 1 (14) days old or less: the "from" of the first screens change dated after that, else the current
    ones — as sig() makes them (Splash and Home)."""
    lim = (date.fromisoformat(d) + timedelta(days=gf.RECENT_DAYS - 1)).isoformat()
    for ch in store.get("steps_changed") or []:
        if isinstance(ch, dict) and str(ch.get("at") or "") > lim and isinstance(ch.get("from"), dict):
            return sig(ch["from"])
    return sig(store.get("steps") or {})


def _pday(at, tz):
    """A record's read time ("…Z") → the property's day then; None: not a time."""
    t = gu._parse_iso(str(at)) if at else None
    if t is None:
        return None
    try:
        z = ZoneInfo(tz or "UTC")
    except Exception:
        z = timezone.utc
    return t.astimezone(z).date()


def _low_all(v, refs, k):
    """v under k × every reference of refs that is there (None: not there) — and at least one is."""
    r = [x for x in refs if x is not None]
    return bool(r) and all(v < k * x for x in r)


def _med(v):
    v = sorted(v)
    n = len(v)
    return None if not n else (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2)


def exact_days(data_dir, store, counts=None, till=None):
    """The days of an app's First open store GA4 read SAMPLED whose country store record holds the same funnel's day
    exact (module doc: EXACT COUNTS) → {D: [first_open, splash, home]}. A record counts when it is whole and unsampled
    (not "none", "smp" null, not held "ho", "t" three ints), read EX_AGE property days or more after its day — or, a day
    ≤ till (the app's final till), kept by the country store as final ("fin": under the lag in force when it was read)
    and read EX_AGE0 days or more after it —, with the
    screens that day's First open read had (_day_sig), with first opens and a Splash, no step much in no named country
    (the country store's own NONAME / REF_MIN rule), and not collapsed: first opens under EX_FLOOR × the First open
    store's own count of the day (REF_MIN or more) or EX_LOW × the median of the store's own whole same-screens days
    within EX_NB (at least EX_NB_MIN of them), or under EX_HALF × every one of those two there is; Splash ÷ first opens
    or Home ÷ Splash under EX_STEP × every one there is of the days' median rate and the First open read's own rate
    (each only with REF_MIN or more users under it). {} when there are none; on a failure {} and its kind in
    counts["exact_err"] (the build prints its skipped line). Never raises."""
    try:
        from .fetch import ga4_firstopen_cc as fc
        cc = fc.load_store(fc.store_path(data_dir, str(store.get("app_id") or "")))
        ccd = (cc or {}).get("days") or {}
        if not ccd:
            return {}
        tz, good = store.get("time_zone"), {}
        for d, c in ccd.items():
            t = c.get("t") if isinstance(c, dict) else None
            if not (isinstance(t, list) and len(t) == 3 and all(type(v) is int and v >= 0 for v in t)) \
                    or c.get("none") or c.get("smp") is not None or c.get("ho"):
                continue
            rd = _pday(c.get("at"), tz)
            age = None if rd is None else (rd - date.fromisoformat(d)).days
            if age is not None and (age >= EX_AGE or (c.get("fin") is True and age >= EX_AGE0 and till is not None
                                                      and d <= till)):
                good[d] = c
        out = {}
        for d, rec in (store.get("days") or {}).items():
            smp = (rec or {}).get("sample")
            c = good.get(d)
            if c is None or type(smp) not in (int, float) or not smp < 1 or c.get("sg") != _day_sig(store, d, fc.sig):
                continue
            t, p, ref = c["t"], fc._parts(c), int((rec or {}).get("first_open") or 0)
            if t[0] <= 0 or t[1] <= 0 or any(p[j] - p[j + 3] >= max(fc.REF_MIN, fc.NONAME * p[j]) for j in range(3)) \
                    or ref >= fc.REF_MIN and t[0] < EX_FLOOR * ref:
                continue
            d0 = date.fromisoformat(d)
            nb = [good[k]["t"] for k in ((d0 + timedelta(days=i)).isoformat() for i in range(-EX_NB, EX_NB + 1) if i)
                  if k in good and good[k].get("sg") == c.get("sg") and good[k]["t"][0] > 0 and good[k]["t"][1] > 0]
            m0 = mo = ms = None                         # the days around: first opens, Splash ÷ them, Home ÷ Splash
            if len(nb) >= EX_NB_MIN:                    # (a rate only with REF_MIN or more users under it)
                m0 = _med(x[0] for x in nb)
                if _med(x[1] for x in nb) >= fc.REF_MIN:
                    mo = _med(x[1] / x[0] for x in nb)
                if _med(x[2] for x in nb) >= fc.REF_MIN:
                    ms = _med(x[2] / x[1] for x in nb)
            f, sp_, h = (int((rec or {}).get(k) or 0) for k in ("first_open", "splash", "home"))
            so = sp_ / f if sp_ >= fc.REF_MIN and f > 0 else None      # … and the First open read's own rates
            sh = h / sp_ if h >= fc.REF_MIN and sp_ > 0 else None
            if m0 is not None and t[0] < EX_LOW * m0 \
                    or _low_all(t[0], [ref if ref >= fc.REF_MIN else None, m0], EX_HALF) \
                    or _low_all(t[1] / t[0], [mo, so], EX_STEP) or _low_all(t[2] / t[1], [ms, sh], EX_STEP):
                continue
            out[d] = list(t)
        return out
    except Exception as e:
        if counts is not None:
            counts["exact_err"] = type(e).__name__
        return {}


def _names(dashboard):
    out = {}
    for c in dashboard.get("apps_catalog") or []:
        if c.get("app_id") and c.get("app_name"):
            out.setdefault(str(c["app_id"]), c["app_name"])
    for k in ("uninstall", "active", "value"):
        for a in ((dashboard.get(k) or {}).get("apps") or []):
            if a.get("app_id") and a.get("app"):
                out[str(a["app_id"])] = a["app"]
    return out


def _today(store, now):
    try:
        return now.astimezone(ZoneInfo(store.get("time_zone") or "UTC")).date()
    except Exception:
        return now.date()


def summarize(app, key, rows, final_till, sp=None):
    """One app's rows (days ascending) → its summary entry (the status rule above). sp: {D: Splash} of the rows whose
    three are the country store's exact ones (EXACT COUNTS) — the Splash of the First open read their other steps come
    from, so a step's share of Splash stays one read's (a sampled step ÷ an exact Splash is neither)."""
    fin = [r for r in rows if r[0] <= final_till]
    w7, p28 = fin[-7:], fin[-35:-7]
    ix = {f: i + 1 for i, f in enumerate(FIELDS)}

    def s(rs, f):
        return sum(int(r[ix[f]] or 0) for r in rs)
    s7, s28 = s(w7, "splash"), s(p28, "splash")
    s2h = s(w7, "home") / s7 if s7 else None
    usual = s(p28, "home") / s28 if s28 else None
    change = s2h - usual if s2h is not None and usual is not None else None
    if len(fin) < MIN_DAYS:
        status, why = "Too early", "history %d final days" % len(fin)
    elif s7 < MIN_SPLASH7 or s28 < MIN_SPLASH28:
        status, why = "N/A", "low data"
    elif change <= WORSE:
        status, why = "Worse", ""
    elif change <= WATCH:
        status, why = "Watch", ""
    elif change >= BETTER:
        status, why = "Better", ""
    else:
        status, why = "Normal", ""
    f7, f28 = s(w7, "first_open"), s(p28, "first_open")
    sa7 = s(w7, "splash_any")
    steps = {}
    sp = sp or {}

    def ss(rs):
        return sum(int(sp.get(r[0], r[ix["splash"]]) or 0) for r in rs)
    d7, d28 = ss(w7), ss(p28)
    for k in ("language", "permission", "intro"):
        if any(r[ix[k]] is not None for r in rows):
            steps[k] = [s(w7, k) / d7 if d7 else None, s(p28, k) / d28 if d28 else None]
    r6 = lambda v: None if v is None else round(v, 6)
    out = {"key": key, "app": app, "status": status, "why": why, "s2h": r6(s2h), "usual": r6(usual), "change": r6(change),
            "s2h_any": r6(s(w7, "home_any") / sa7) if sa7 else None, "opened": r6(s7 / f7) if f7 else None,
            "opened_usual": r6(s28 / f28) if f28 else None, "fo_day": r6(f7 / len(w7)) if w7 else 0,
            "fo_day_usual": r6(f28 / len(p28)) if p28 else None,
            "steps": {k: [r6(a), r6(b)] for k, (a, b) in steps.items()}, "final_days": len(fin),
            "sample": min([r[SX] for r in w7 if r[SX] is not None and not _x(r)], default=None)}
    if any(len(r) > XI for r in rows):                  # EXACT COUNTS on: the steps that stay sampled
        out["sample_other"] = min([r[SX] for r in w7 if r[SX] is not None], default=None)
    return out


def build_data(dashboard, data_dir, now, counts, exact=False):
    names = _names(dashboard)
    d = os.path.join(data_dir, gf.DIR)
    if not os.path.isdir(d):
        return None
    apps, summary = [], []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json.gz"):
            continue
        store = gf.load_store(os.path.join(d, fn))
        if not store or not store.get("days") or not (store.get("steps") or {}).get("home"):
            counts["skipped"] = counts.get("skipped", 0) + 1
            continue
        aid = str(store.get("app_id") or "")
        app = names.get(aid) or store.get("package") or aid
        key = gu.file_key(aid)
        td = _today(store, now)
        final_till = (td - timedelta(days=FIN_LAG)).isoformat()
        rows, sp, ex = [], {}, exact_days(data_dir, store, counts, till=final_till) if exact else {}
        for day in sorted(store["days"]):
            rec = store["days"][day] or {}
            row = [day] + [rec.get(f) if rec.get(f) is not None else (0 if f in ("first_open", "splash", "home")
                                                                        else None) for f in FIELDS] + [rec.get("sample")]
            if exact:                                   # EXACT COUNTS: the country store's exact three, said so
                e = ex.get(day)
                if e is not None:
                    sp[day] = row[2]                    # (the steps' own read's Splash: summarize)
                    row[1:4] = e
                row.append(1 if e is not None else 0)
            rows.append(row)
        counts["exact"] = counts.get("exact", 0) + len(ex)
        if store.get("package"):
            counts.setdefault("_pkg", {})[key] = str(store["package"])
        apps.append({"key": key, "app": app, "app_id": aid, "steps": store.get("steps"),
                     "steps_changed": store.get("steps_changed") or [], "first_day": rows[0][0], "final_till": final_till,
                     "days": rows})
        if EDGES:
            apps[-1]["td"] = td.isoformat()
        summary.append(summarize(app, key, rows, final_till, sp))
    if not apps:
        return None
    counts["apps"] = len(apps)
    counts["days"] = sum(len(a["days"]) for a in apps)
    for x in summary:
        counts[x["status"]] = counts.get(x["status"], 0) + 1
    return {"apps": apps, "summary": summary}


# ── by country ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _r6(v):
    return None if v is None else round(v, 6)


def cc_file(key):
    return "%s%s.json.gz" % (CC_PREFIX, key)


def cc_days(store):
    """The country store's real days, ascending → [[D, first_open, splash, home, sample | null, {cc: [three]}], …]. A day
    that is neither {"none": true} nor a whole record raises (that app's country part fails, nothing else)."""
    out = []
    days = store.get("days") or {}
    for d in sorted(days):
        rec = days[d]
        if not isinstance(rec, dict):
            raise ValueError("day")
        if rec.get("none"):
            continue
        date.fromisoformat(d)
        t, c, smp = rec.get("t"), rec.get("c"), rec.get("smp")
        if not (isinstance(t, list) and len(t) == 3 and isinstance(c, dict)):
            raise ValueError("day")
        cs = {}
        for k, v in c.items():
            if not (isinstance(k, str) and k and isinstance(v, list) and len(v) == 3):
                raise ValueError("country")
            cs[k] = [int(x) for x in v]
        out.append([d, int(t[0]), int(t[1]), int(t[2]), None if smp is None else float(smp), cs])
    return out


def cc_window(days, final_till):
    """The country file's status window → (run, missing). run = the indices (oldest first) of the UNBROKEN run of calendar
    days that ends exactly at final_till (empty when the store has no real day for final_till); missing = the calendar days
    of final_till − (MIN_DAYS − 1) … final_till, from the store's first real day on, the store has no real day for.
    The country store is not contiguous the way the app's is (its backfill reads the oldest and the newest day in turn;
    a deferred or switched-off fetch falls behind; a {"none": true} day): a window counted over the stored days would
    straddle a hole or be weeks old while the page says "last 7 days"."""
    have = {d[0]: i for i, d in enumerate(days)}
    end = date.fromisoformat(final_till)
    run, k = [], end
    while k.isoformat() in have:
        run.append(have[k.isoformat()])
        k -= timedelta(days=1)
    run.reverse()
    lo = max(date.fromisoformat(days[0][0]), end - timedelta(days=MIN_DAYS - 1)) if days else end + timedelta(days=1)
    missing = sum(1 for i in range((end - lo).days + 1) if (lo + timedelta(days=i)).isoformat() not in have)
    return run, missing


def build_cc(store, key, aid, final_till):
    """One app's country store → its country file's body, or None (no real day). Every country GA4 named is kept; its
    status is the app's own rule (summarize() on rows in the app's row layout: first_open / splash / home filled, the
    other steps None) fed ONLY the unbroken calendar run ending at final_till (cc_window) — a hole or a lag inside the
    rule's 35 days leaves fewer than MIN_DAYS days, so the rule itself says Too early (why: the hole or the last day);
    the share and the unnamed users over the same 7 calendar days. What GA4 named no country for = the day's total − the
    named countries, as measured. "days" keeps every real day (nothing trimmed); "last_day" = the newest one; "missing" =
    the days the status window lacks (0 = whole); "gone" = the days GA4's funnel no longer has, "gone_fo" = their first
    opens by country from GA4's report (no funnel step: the page shows "—" there), "nobody" = the days GA4 named no
    country — so the page tells every day from the app's day 1 apart from a day still to be read."""
    days = cc_days(store)
    if not days:
        return None
    ccs = sorted(set().union(*(set(d[5]) for d in days)))
    run, missing = cc_window(days, final_till)
    fin_all = [d[0] for d in days if d[0] <= final_till]
    w7 = run[-7:]
    t7 = sum(days[i][1] for i in w7)
    rest = [None] * (len(FIELDS) - 3)
    order = []
    for cc in ccs:
        rows = [[days[i][0]] + list(days[i][5].get(cc) or (0, 0, 0)) + rest + [days[i][4]] for i in run]
        x = summarize(cc, cc, rows, final_till)
        if x["status"] == "Too early" and len(fin_all) > len(run):    # the store has final days the run can not reach
            x["why"] = ("country data %s tak" % fin_all[-1] if fin_all[-1] < final_till
                        else "country data incomplete: %d din missing" % missing)
        f7 = sum(r[1] for r in rows[-7:])
        fall = sum(int((d[5].get(cc) or (0,))[0]) for d in days)
        e = {"cc": cc}
        e.update((k, x[k]) for k in CC_KEEP)
        if not w7:
            e["fo_day"] = None                                       # no day in the window: not known (never "0 / day")
        e["share"] = _r6(f7 / t7) if t7 > 0 else None
        order.append((-f7, -fall, cc, e))
    order.sort(key=lambda z: z[:3])
    un = [[d[j] - sum(v[j - 1] for v in d[5].values()) for j in (1, 2, 3)] for d in days]
    fu, su, hu = (sum(un[i][j] for i in w7) for j in range(3))
    unnamed = {"fo_day": _r6(fu / len(w7)) if w7 else None, "opened": _r6(su / fu) if fu > 0 and su >= 0 else None,
               "s2h": _r6(hu / su) if su > 0 and hu >= 0 else None, "share": _r6(fu / t7) if t7 > 0 else None}
    nones = {k: v for k, v in (store.get("days") or {}).items() if isinstance(v, dict) and v.get("none")}
    gone = sorted(k for k, v in nones.items() if v.get("why") == "ga4")   # GA4's funnel has nothing left for the day
    gone_fo = {k: {str(c): int(n) for c, n in nones[k]["fo"].items()}  # … its report's first opens by country
               for k in gone if isinstance(nones[k].get("fo"), dict)}
    nobody = sorted(k for k, v in nones.items() if v.get("why") != "ga4")  # GA4 named no country that day
    return {"v": V, "key": key, "app_id": aid, "final_till": final_till, "first_day": days[0][0],
            "last_day": days[-1][0], "missing": missing, "days": days, "gone": gone, "gone_fo": gone_fo,
            "nobody": nobody, "summary": [z[3] for z in order], "unnamed": {"summary": unnamed}}


def _cc_clean(out_dir, keep):
    try:
        names = os.listdir(out_dir)
    except OSError:
        return
    for f in names:
        if CC_RE.match(f) and f not in keep:
            try:
                os.remove(os.path.join(out_dir, f))
            except OSError:
                pass


def attach_cc(apps, data_dir, out_dir, counts):
    """Every app with a country store: its country file written, then (only then) its "cc" pointer on the app's entry.
    One app's failure (or a file over CC_MAX_GZ) costs only that app's country file; stale country files are removed.
    Never raises."""
    keep, seen = set(), set()
    counts.update(cc_apps=0, cc_kb=0, cc_failed=0, cc_big=0)
    try:
        from .fetch import ga4_firstopen_cc as fc
        for a in apps:
            try:
                store = fc.load_store(fc.store_path(data_dir, a["app_id"]))
                if not store:
                    continue
                body = build_cc(store, a["key"], a["app_id"], a["final_till"])
                if body is None:
                    continue
                raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
                gz = len(gzip.compress(raw, 9, mtime=0))
                if gz > CC_MAX_GZ:
                    counts["cc_big"] += 1
                    continue
                fn, names = cc_file(a["key"]), [x["cc"] for x in body["summary"]]
                ptr = {"file": fn, "v": hashlib.sha1(raw).hexdigest()[:12], "from": body["first_day"],
                       "last": body["last_day"], "n": len(names), "days": len(body["days"])}
                write_json_gz_stable(os.path.join(out_dir, fn), body)
                keep.add(fn)
                a["cc"] = ptr
                seen.update(names)
                counts["cc_apps"] += 1
                counts["cc_kb"] += gz
            except Exception:
                a.pop("cc", None)
                counts["cc_failed"] += 1
    except Exception:
        for a in apps:
            a.pop("cc", None)
        keep = set()
        counts["cc_failed"] += 1
    counts["cc_countries"] = len(seen) if keep else 0
    _cc_clean(out_dir, keep)


# ── installed but never opened ─────────────────────────────────────────────────────────────────────────────────────
def ads_file(key):
    return "%s%s.json.gz" % (ADS_PREFIX, key)


def _n2(v):
    v = round(float(v), 2)
    return int(v) if v.is_integer() else v


def build_ads(key, aid, ads, nu):
    """One app's Google Ads store-days ({day: {cc: [play, fo]}}, fetch.gads_inst_day) and GA4 first-open store
    (fetch.ga4_newusers: days {day: {"a": {cc: n}, "p": {cc: n}}}) → its ads file body, or None (neither has a day)."""
    ad = ads if isinstance(ads, dict) else {}
    gd = {d: v for d, v in ((nu or {}).get("days") or {}).items() if isinstance(v, dict)}
    days = sorted(set(ad) | set(gd))
    if not days:
        return None
    cc_ = lambda c: "--" if c in ("XX", "--", "", None) else str(c)
    out = []
    for d in days:
        a_, g = ad.get(d), gd.get(d)
        base = [0 if a_ is not None else None] * 2 + [0 if g is not None else None] * 2
        cells = {}
        for c, v in (a_ or {}).items():
            e = cells.setdefault(cc_(c), list(base))
            e[0] += float(v[0] or 0)
            e[1] += float(v[1] or 0)
        for j, part in ((2, "p"), (3, "a")):
            for c, n in ((g or {}).get(part) or {}).items():
                e = cells.setdefault(cc_(c), list(base))
                e[j] += int(n or 0)
        tot = [None if base[j] is None else sum(e[j] for e in cells.values()) for j in range(4)]
        fix = lambda e: [None if x is None else (_n2(x) if j < 2 else int(x)) for j, x in enumerate(e)]
        out.append([d, fix(tot), {c: fix(e) for c, e in sorted(cells.items())}])
    first = lambda src: next((d for d in days if src.get(d) is not None), None)
    return {"v": V, "key": key, "app_id": aid, "first_day": days[0], "last_day": days[-1], "ads_from": first(ad),
            "ga4_from": first(gd), "days": out}


def _ads_clean(out_dir, keep):
    try:
        names = os.listdir(out_dir)
    except OSError:
        return
    for f in names:
        if ADS_RE.match(f) and f not in keep:
            try:
                os.remove(os.path.join(out_dir, f))
            except OSError:
                pass


def attach_ads(apps, pkgs, data_dir, out_dir, counts):
    """Every app with Google Ads store-days or GA4 first opens by country: its ads file written, then (only then) its
    "ads" pointer. One app's failure (or a file over CC_MAX_GZ) costs only that app's file; stale files removed. Never
    raises."""
    keep = set()
    counts.update(ads_apps=0, ads_kb=0, ads_failed=0, ads_big=0)
    try:
        from .fetch import gads_inst_day as gi
        from .fetch import ga4_newusers as gn
        ads_all = gi.load_all(data_dir)
        for a in apps:
            try:
                nu = gn.load_store(gn.store_path(data_dir, a["app_id"]))
                body = build_ads(a["key"], a["app_id"], ads_all.get((pkgs or {}).get(a["key"]) or ""), nu)
                if body is None:
                    continue
                raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
                gz = len(gzip.compress(raw, 9, mtime=0))
                if gz > CC_MAX_GZ:
                    counts["ads_big"] += 1
                    continue
                fn = ads_file(a["key"])
                write_json_gz_stable(os.path.join(out_dir, fn), body)
                keep.add(fn)
                a["ads"] = {"file": fn, "v": hashlib.sha1(raw).hexdigest()[:12], "from": body["first_day"],
                            "last": body["last_day"], "ads_from": body["ads_from"], "ga4_from": body["ga4_from"]}
                counts["ads_apps"] += 1
                counts["ads_kb"] += gz
            except Exception:
                a.pop("ads", None)
                counts["ads_failed"] += 1
    except Exception:
        for a in apps:
            a.pop("ads", None)
        keep = set()
        counts["ads_failed"] += 1
    _ads_clean(out_dir, keep)


def _remove(out_dir):
    try:
        os.remove(os.path.join(out_dir, FILE))
    except OSError:
        pass
    _cc_clean(out_dir, set())
    _ads_clean(out_dir, set())


def run(dashboard, data_dir, out_dir, s=None, now=None):
    """This build's First open file → HEADER_PATHS, or [] (no store yet / a failure: the file removed, no pointer).
    Never raises."""
    global LINE
    LINE = None
    if not isinstance(dashboard, dict):
        return []
    dashboard.pop("firstopen", None)
    try:
        counts = {}
        data = build_data(dashboard, data_dir, now or datetime.now(timezone.utc), counts, exact=exact_on(s))
        if data is None:
            _remove(out_dir)
            LINE = "first open: apps 0, skipped %d" % counts.get("skipped", 0)
            return []
        attach_cc(data["apps"], data_dir, out_dir, counts)
        attach_ads(data["apps"], counts.pop("_pkg", {}), data_dir, out_dir, counts)
        body = dict(data, v=V)
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        gz = len(gzip.compress(raw, 9, mtime=0))
        if gz > MAX_GZ:
            _remove(out_dir)
            LINE = "first open: too big (%d kb), not written" % (gz // 1024)
            return []
        write_json_gz_stable(os.path.join(out_dir, FILE), body)
        ids = {a["key"]: a["app_id"] for a in data["apps"]}
        dashboard["firstopen"] = {"file": FILE, "v": hashlib.sha1(raw).hexdigest()[:12],
                                  "apps": {x["app"]: dict({k: x[k] for k in ("status", "s2h", "usual", "change", "fo_day")},
                                                          id=ids.get(x["key"], "")) for x in data["summary"]}}
        LINE = ("first open: apps %d, days %d, worse %d, watch %d, better %d, normal %d, too early %d, n/a %d, skipped %d, kb %d"
                % tuple([counts.get(k, 0) for k in ("apps", "days", "Worse", "Watch", "Better", "Normal", "Too early",
                                                    "N/A", "skipped")] + [gz // 1024]))
        LINE += ", by country: apps %d, countries %d, kb %d" % (counts["cc_apps"], counts["cc_countries"],
                                                                counts["cc_kb"] // 1024)
        if counts["cc_failed"] or counts["cc_big"]:
            LINE += ", failed %d, too big %d" % (counts["cc_failed"], counts["cc_big"])
        LINE += ", installs: apps %d, kb %d" % (counts["ads_apps"], counts["ads_kb"] // 1024)
        if counts["ads_failed"] or counts["ads_big"]:
            LINE += ", failed %d, too big %d" % (counts["ads_failed"], counts["ads_big"])
        if exact_on(s):
            LINE += ", exact days %d" % counts.get("exact", 0)
            if counts.get("exact_err"):                 # never silent: the health banner's shape
                print("first open exact skipped: %s" % counts["exact_err"], file=sys.stderr)
        return list(HEADER_PATHS)
    except Exception as e:
        dashboard.pop("firstopen", None)
        _remove(out_dir)
        LINE = None
        print("first open skipped: %s" % type(e).__name__, file=sys.stderr)
        return []


def off(out_dir):
    global LINE
    LINE = None
    _remove(out_dir)


def pop_line():
    global LINE
    line, LINE = LINE, None
    return line
