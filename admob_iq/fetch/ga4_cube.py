"""🧊 The cohort cube — GA4 ad revenue by ACTIVITY day × INSTALL day × COUNTRY, from the app's GA4 history start to
today, kept for good (owner, 20 Oct 2026: "jitna purana app utna date" — the ROI section's install-day table goes on
past D30 in 30-day columns up to the app's age; real data only, nothing trimmed, the full history).

Why this read (measured on the real properties by fetch/ga4_cohort_country_probe.py, report in the private repo):
  * runReport dimensions [date, firstSessionDate] WITHOUT countryId answers install days only back to about 15 months
    (GA4's horizon for that shape): on an old app such a read misses much of the revenue of the users installed
    earlier — so it is never used past D30;
  * the SAME read WITH countryId answers every install day back to the app's start (the whole block total on the small
    and medium apps);
  * on the biggest app a 30-day block comes back with "(other)" rows (firstSessionDate and countryId both "(other)")
    holding a large share of the revenue, while ONE activity day a query comes back with no "(other)" at all.

The read — runReport v1beta on the app's Android stream (ga4.stream_filter), USD, keepEmptyRows false, every page
(report_all with gu.UNI_PAGE_ROWS: never cut), no firstSessionDate filter (only a split part's, step 3):
    dimensions [date, firstSessionDate, countryId], metrics [activeUsers, totalAdRevenue]
adaptive, per range of activity days:
  1. a block of BLOCK (30) days in one call; when any row has "(other)" (or a date that is not one), the answer was cut
     (truncated) or any page's metadata says dataLossFromOtherRow or sampling, the block's answer is dropped and
  2. each day of it is read alone; when a day still has "(other)" (or the same flags),
  3. that day is split (split_read), again and again while a part of it still has "(other)" (owner, 21 Oct 2026:
     "revenue cross check kro country wise, admob ke sath verify kro" — on the biggest apps one split left a large
     share of some months' revenue in "(other)"). A part is a filter on countries (an in-list, or "not in" a list) and
     on install days (an in-list, or "not in" a list); a part whose answer still has "(other)" — a row, or only GA4's
     dataLossFromOtherRow (an in-list filter DROPS the "(other)" row: its revenue is gone from the answer, the flag
     alone says so — ga4_uninstall's Q-C note) — or was sampled / cut is read again as two parts that PARTITION it
     (every row of it in exactly one of them, never in both; the part's own answer kept until both are in):
       * by countries while it holds more than one: an in-list → its two halves; "every country but E" → the biggest
         named countries of its answer up to half its rows (the most rows — the cardinality GA4 folds into "(other)" —
         then revenue, then code) in an in-list H, and "every country but E + H" (countries GA4 hid in "(other)",
         "(not set)" and empty stay in that one: never in a list, so never lost);
       * one country left (or none named): by install days (firstSessionDate) — an in-list → its two halves (by date,
         each half about half the rows); no list → the oldest named install days of its answer up to half its rows in
         an in-list H, and "every install day but H" (a "(not set)" install day, one GA4 hid: in that one);
       * one country and one install day: it cannot be split — what stays "(other)" in it is measured loss.
     The part with the most "(other)" revenue goes first (a flagged one with no row: the most rows first); at the day's
     call cap (DAY_CAP calls, HOT_CAP for a hot day) no more parts are read: whatever is STILL "(other)" is the day's
     measured loss ("ol", in "loss"): kept as such, never spread ("cap" 1 on the day: a deeper split could have read
     more). A split whose two halves name no row their part had not (GA4 rolled the rows into "(other)" before the
     filters — then no filter ever names them) ends the day's split at once ("fu": 3 calls, not the cap; the part as it
     was, its "(other)" the measured loss). A final part still flagged dataLossFromOtherRow with no "(other)" row →
     ONE more call, the day's own total (dimension date only, no filter: one row — nothing to roll up or drop): what
     it holds beyond every part's rows (past ½ micro a row + 1 ppm of rounding) is "(other)" GA4 hid — added to the
     day's t, loss and ol ("hd" on the record; the log's "hidden"), never missing unrecorded; that total sampled / cut
     (nothing to measure by) → "fl". A Stop (the run's budget, the property's quota, MAX_CALLS) in the middle of a day
     keeps nothing of it: the day is not folded and is read again, whole, next run (first in it). A Stop counts as the
     day's cut only when the day was the run's FIRST read (it had the run's whole allowance — never one that started
     with what the walk, the hot days or the other days left), after ≥ MIN_CAP calls of it and not the app's own call
     cap: a day cut that way CUT_TRIES times gets a smaller cap — the calls a run gave it less one, then half that …
     never below MIN_CAP (the old one-level split) — so a day too costly for one run can never stall the walk (its loss
     stays measured, "cap" 2: under its full cap a read again could take more — the repair's queue counts it). The walk
     ("cut") and the hot days ("hcut") keep their own cut memory: a hot day's smaller cap never follows it into its
     final read (its memory goes once the day is final).
  A range at least as long as one that needed step 2 goes to step 2 straight away for HEAVY_KEEP activity days ("heavy":
  its block call would only be dropped again); then the block is tried once more.
Per row: countryId "(not set)" / empty → cc "--"; a firstSessionDate that is not a date ("(other)", "(not set)"), a
countryId "(other)" or an install day after the activity day → the day's loss (micros; st "loss" only then). GA4's
thresholding, sampling, a cut answer, or a flag still on the final answer with no "(other)" row to measure it by → the
day's "fl" (st stays ok / split: a flag is not a measured loss; the page marks ≈ with no direction; nothing guessed).

Stored in the private repo, data/ga4_cube/<key>/ — by ACTIVITY month; a month file never changes once its days are all
folded (a folded day is never read or folded again by the walk; only the repair below replaces a whole month, once per
split version):
    <YYYY-MM>.json.gz = {"v", "stream_id",
      "days": {D: {"st": ok|split|loss, "rows", "loss", "t", "fl", "via": block|day|split, "at",     the ledger
                   "sv" (the split's version: SPLIT_V; absent = 1, the one-level split before 21 Oct 2026), "ol" (the
                   part of "loss" that is "(other)": what a deeper split could still read), "n" (GA4 calls the day
                   took, its total included; 0 = a share of one block call), "cap" (1: the day's cap left "(other)" a
                   deeper split could read; 2: a smaller cap did — a day cut run after run)}}
      "b": {X: {j: {W: micros}}}          ALL countries summed, ages L ≥ 31 in 30-day buckets j = (L − 31) // 30 + 1
                                          (bucket j = ages 30j+1 … 30j+30: the step into D(30 + 30j)); W = the Monday of
                                          the activity day (engine.value._mon: the week of the AdMob ÷ GA4 scale k)
      "c": {cc: {X: {j: micros}}}         per country, the same buckets, summed over this activity month
      "e": {cc: {X: [u0, r0, r1 … r30]}}  per country, ages 0 … 30 day by day (u0 = activeUsers at age 0 = the
                                          country's installs; r in micros; trailing zeros trimmed)
      "t": {D: micros}                    every row of the day (the loss share's denominator)
      "loss": {D: micros}                 what stayed "(other)" / had no install day (days with some only)
      "rep": {"sv", "at", "ol0", "loss0", "t0"}}   only on a month the repair rebuilt (below): when, and what it held
    <YYYY-MM>.rep.json.gz — the repair's copy of that month while it is being built (the same format; never read by
      the build: months() takes YYYY-MM.json.gz only)
    hot.json.gz = {"v", "app_id", "package", "property_id", "stream_id", "time_zone", "hs", "from", "next", "done",
      "walk_at", "hot_at", "hot_today", "hot_cyc" ([when, property day] of a round of the hot days a Stop cut: the next
      run reads only its days not read since), "heavy", "cut" / "hcut" (the final / hot day a Stop cut as the run's first
      read: {"D", "n" calls it had, "k" times}), "rep" (the repair's state, below), "d": {D: {the ledger's fields + "b",
      "c", "e" of that one day (+ "hd" / "fu")}}}
— the head (progress) and the NON-FINAL days (today − 2 … today), each replaced when read again. The ROI build reads only
a hot day's ledger and "b"; its "c" / "e" are kept in the same shapes as the months for a per-country / D0 … D30 view
(nothing reads them yet — the biggest app's ≈ 3 hot days of them are most of this file).
X = install day (firstSessionDate), D = activity day (date), both YYYY-MM-DD in the property's time zone; j, W as text.

Progress — ONE cursor, "next": every activity day before it is folded, from a read made when it was already FINAL
(≤ the property's today − FINAL_LAG). A run walks from the cursor to the final edge (the first walk = the backfill
from the history start; a catch-up after a Stop, a pause, failed runs or a new day is the same walk), folding each day
ONCE (a day already in its month's ledger is skipped, never re-read), the cursor moving after each day; "done" once a
walk reached the final edge (the build uses the cube only from then on: the columns come in one go). Then, every
REFRESH_HOURS or on a new property day, today − 2 … today again (hot: never folded; such a day is read once more when
final and folded then; a hot copy of a day that is final now is dropped at the start of every run — a hole until the
walk folds it, never a read made while it was filling standing in for the final one). A history start that moves back
restarts the walk from it and clears "done" (the build waits for it again). A month file on disk that cannot be read
(a damaged gzip, a cut copy), is not this format or is another stream's is never written over with only the days after
the cursor: the cursor goes back to that month's first day and the whole month is read again ("months read again" in
the log). The walk holds at most two months in memory (a month it left is written and let go; folded days are passed
a month at a time). Month files are written as the walk leaves them and at the end, the head after them (it never runs
ahead of the months). The property quota gate of ga4_firstopen.App, MAX_CALLS a run per app, its own budget
(GA4_CUBE_BUDGET_SEC); properties side by side (WORKERS); on a property the app that waited longest goes first and an
app cut off by the budget goes after the others next run (a long backfill never starves a light app). Switched by
GA4_CUBE (off: nothing read, written or printed; the ROI build leaves the store unread). Never raises; never prints
(log_line: counts only).

The repair (repair()) — months folded before the deeper split, whose days still carry "(other)" loss, are read again
and REPLACED whole. Only once the walk reached the final edge in the run and the hot days are read, with what the run
has left (at most REPAIR_CALLS calls started a run, MAX_CALLS and the budget as always). One month at a time:
  * the queue: every month file of the app (one at a time) with recoverable loss — the days whose ledger "sv" is older
    than SPLIT_V and whose "ol" > 0 (an older ledger without "ol": a "split" day's loss; a "block" / "day" day had no
    "(other)" row, its loss is install days that are not dates — no split reads those), and the days of this split
    with "cap" 2 folded after the month's last repair of this split (a day the repair itself read so is never queued
    again: no month is repaired again and again) — biggest share of the month's revenue first, the more recent month
    first on a tie; then the months whose only reason is a one-level "split" day GA4 flagged with no "(other)" row (its
    in-list part may have hidden some, by how much unknown: share 0, after every measured one); made once per SPLIT_V
    and again every RESCAN_DAYS while it is empty (a month folded by an older copy of this code elsewhere);
  * the month's every day is read again, day by day (never a block: a month with "(other)" only comes back with it
    again) with the deeper split, into its copy <YYYY-MM>.rep.json.gz, kept across runs (a Stop keeps the days read; a
    day the Stop cut is read again, whole); a day is started only when the run's calls left fit what a day needs (its
    calls a day so far, DAY_CAP + 1 before the first) — checked before every day; the month file itself is never touched
    meanwhile (the build reads it as it was);
  * once the copy holds every day the month file holds (a day the walk folds into the current month meanwhile is read
    into the copy too), the copy becomes the month file ("rep": what the old one held), the head is written (even in a
    run that made no call) and only then the copy is removed (a run killed before the head finds the copy whole and
    does the same again; a head left naming a month with nothing left to read reads nothing of it again). Its days now
    carry "sv" = SPLIT_V: never queued again unless SPLIT_V goes up (a still deeper split) and their "ol" is still > 0.
  head "rep" = {"sv", "scan" (when the queue was made), "q": [[YYYY-MM, share]], "k" (the month being rebuilt), "old"
  {"ol", "loss", "t"} (what it held), "at", "c" / "n" (calls / days of this repair), "cut" (the cut memory of its
  reads), "log": [[month, "(other)" micros before, after, the month's revenue, when]] (the last LOG_KEEP)}.

Cost: the backfill ≈ app age / 30 block calls on a light app (rows a call ≈ 30 × a day's (install day, country) rows),
and on a heavy one about one call per activity day (+ 2 per part split, + one block try every HEAVY_KEEP days) —
measured on the biggest app ≈ 70 GA4 tokens and 4–6 s a day call, so ≈ 25 calls a run in the 150 s budget (the walk
goes on next run). A day that still has "(other)": 1 + 2 × (parts split) calls (+ 1, its total, only when a part
hides "(other)") — when GA4 rolls rows up per answer, a day r times over its limit needs about 2r − 1 or more (the
halves stop as soon as a part comes back whole; synthetic: 5 calls at 1.5×, 9 at 3×, 25 at 8×); when GA4 rolls them
up before the filters, 3 (the first split names nothing more) + 1; never more than DAY_CAP (24, one run's budget) + 1
— which of the two GA4 does the log's "futile" / "hidden" counts will show (not measured yet). After the walk, a day:
the new final day + the hot window (≤ 3 × (HOT_CAP + 1) calls, a round a Stop cut going on with its unread days) every
6 hours and at the property's midnight. The repair of a month ≈ 30 day reads × the calls a day takes (≈ 30 × 4–10 =
120–300 on the biggest app): ≤ REPAIR_CALLS (30) started a run, and only with a day's room left → about 4–10 runs a
month, the biggest loss first. A run never makes more than MAX_CALLS (60) calls an app: the final day (≤ 25, on a new
day) and the hot days (≤ 39, every 6 h) go first, the repair only with what they left (most hourly runs: they read
nothing, the repair gets its 30); what does not fit is read next run. GA4 tokens stay under the property's quota
floors (the App's gate stops every read of the property before them).
"""
import heapq
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import ga4_probe
from ..db import write_json_gz_stable
from . import ga4
from . import ga4_audience as gaud
from . import ga4_firstopen as gf
from . import ga4_uninstall as gu
from .ga4_firstopen import Stop

DIR = "ga4_cube"
V = 1
LAGS = 31                           # ages 0 … 30 day by day ("e"); from 31 on in 30-day buckets ("b", "c")
STEP = 30                           # bucket j = ages 30j+1 … 30j+30
BLOCK = 30                          # activity days a block call
SPLIT_V = 2                         # the split's version (ledger "sv"): 1 one country level, 2 recursive (21 Oct 2026)
DAY_CAP = 24                        # GA4 calls a final day's split may take (then what is still "(other)" is its loss):
                                    # one run's budget (≈ 25 calls of 4–6 s in 150 s) — a day fits the run it starts
HOT_CAP = 12                        # … a hot day's (read again every 6 hours, never folded: its final read is kept)
MIN_CAP = 3                         # the smallest cap a day cut again and again gets (the one-level split's 3 calls)
CUT_TRIES = 2                       # runs a day may be cut by a Stop (after ≥ MIN_CAP calls of it) before its cap
                                    # shrinks
REPAIR_CALLS = 30                   # calls a run may start repair days with (a started day finishes or is cut)
RESCAN_DAYS = 7                     # the repair's queue made again (while empty) after this many days
LOG_KEEP = 24                       # repaired months kept in the head's "rep" "log"
REP = ".rep.json.gz"                # a month's copy while the repair builds it
HEAVY_KEEP = 90                     # activity days a range goes day by day after a block of its length needed it
FINAL_LAG = 3                       # an activity day is final once ≤ the property's today − 3 (as ga4_cohort)
REFRESH_HOURS = 6.0                 # the hot days (today − 2 … today) read again
MAX_CALLS = 60                      # per app per run (the walk goes on next run)
BUDGET_SEC = 150
RETRY_HOURS = 3.0
WORKERS = 3                         # properties read side by side (each its own quota)
DIMS = ("date", "firstSessionDate", "countryId")
METS = ("activeUsers", "totalAdRevenue")
OTHER = "(other)"
NO_CC = "--"                        # countryId "(not set)" / empty
HOT = "hot.json.gz"
LEDGER = ("st", "rows", "loss", "t", "fl", "via", "at", "sv", "ol", "n", "cap")
F_OTHER, F_SMP, F_CUT, F_THR = 1, 2, 4, 8       # GA4's flags on an answer
RETRY = F_OTHER | F_SMP | F_CUT                 # … that a smaller read can avoid


def _d(s):
    return date.fromisoformat(s)


def _real(s):
    """GA4's YYYYMMDD → YYYY-MM-DD when it is a real date ("(other)", "(not set)", junk → None)."""
    s = str(s or "")
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:])).isoformat()
    except ValueError:
        return None


def _mon(d):
    return d - timedelta(days=d.weekday())


def bucket(L):
    """Age L ≥ 31 → its 30-day bucket j (1: ages 31 … 60, 2: 61 … 90, …)."""
    return (L - LAGS) // STEP + 1


def _days(a, b):
    out = []
    while a <= b:
        out.append(a)
        a += timedelta(days=1)
    return out


# ── the read ────────────────────────────────────────────────────────────────────────────────────────────────────────
def body(a, b, dims=DIMS):
    """Activity days a … b: every install day and country (no firstSessionDate filter)."""
    return {"dateRanges": [{"startDate": a.isoformat(), "endDate": b.isoformat()}],
            "dimensions": ga4._dim(*dims), "metrics": ga4._dim(*METS), "currencyCode": "USD", "keepEmptyRows": False}


def cc_in(ccs):
    return ga4._in_list("countryId", sorted(ccs))


def cc_not(ccs):
    return {"notExpression": cc_in(ccs)}


def x_in(xs):
    """firstSessionDate in-list of install days (YYYY-MM-DD → GA4's YYYYMMDD)."""
    return ga4._in_list("firstSessionDate", sorted(x.replace("-", "") for x in xs))


def _flags(ga, rows):
    """GA4's flags on the last report_all: any page's dataLossFromOtherRow / sampling / thresholding, a cut answer."""
    f = 0
    for m in getattr(ga, "last_metas", None) or [getattr(ga, "last_meta", None) or {}]:
        if isinstance(m, dict):
            f |= (F_OTHER if m.get("dataLossFromOtherRow") else 0) | (F_SMP if m.get("samplingMetadatas") else 0) \
                 | (F_THR if m.get("subjectToThresholding") else 0)
    if hasattr(ga, "truncated") and ga.truncated(rows):
        f |= F_CUT
    return f


def _other(rows):
    """Any row GA4 rolled into "(other)" (or whose activity day is not a date)?"""
    for r in rows:
        if OTHER in (r.get("firstSessionDate"), r.get("countryId")) or not _real(r.get("date")):
            return True
    return False


def _cc(r):
    cc = str(r.get("countryId") or "")
    return NO_CC if cc in ("", "(not set)") else cc


def _new():
    return {"b": {}, "c": {}, "e": {}, "t": 0, "loss": 0, "rows": 0, "oth": 0, "ol": 0}


def _add(acc, Dd, W, X, Xd, r):
    """One row of activity day Dd (W: its Monday) into the day's accumulator; X / Xd: its install day (None: not a
    date)."""
    v = int(round(float(r.get("totalAdRevenue") or 0) * 1e6))
    acc["rows"] += 1
    acc["t"] += v
    cc = _cc(r)
    if OTHER in (r.get("firstSessionDate"), r.get("countryId")):
        acc["oth"] += 1
        acc["ol"] += v
    L = (Dd - Xd).days if Xd else -1
    if Xd is None or cc == OTHER or L < 0:
        acc["loss"] += v
        return
    if L < LAGS:
        u = int(r.get("activeUsers") or 0) if L == 0 else 0
        if not (u or v):
            return
        arr = acc["e"].setdefault(cc, {}).setdefault(X, [])
        if len(arr) < L + 2:
            arr.extend([0] * (L + 2 - len(arr)))
        arr[0] += u
        arr[L + 1] += v
    elif v:
        j = str(bucket(L))
        w = acc["b"].setdefault(X, {}).setdefault(j, {})
        w[W] = w.get(W, 0) + v
        c = acc["c"].setdefault(cc, {}).setdefault(X, {})
        c[j] = c.get(j, 0) + v


def _trim(arr):
    n = len(arr)
    while n and not arr[n - 1]:
        n -= 1
    return arr[:n]


def _group(rows, day=None):
    """Rows → {D: accumulator} (a row without a real activity day: `day`'s, when the read was of one day)."""
    out, ds, xs = {}, {}, {}
    for r in rows:
        raw = r.get("date")
        if raw not in ds:
            D = _real(raw) or (day.isoformat() if day else None)
            ds[raw] = (D, _d(D), _mon(_d(D)).isoformat()) if D else None
        if ds[raw] is None:
            continue
        D, Dd, W = ds[raw]
        raw = r.get("firstSessionDate")
        if raw not in xs:
            X = _real(raw)
            xs[raw] = (X, _d(X) if X else None)
        if D not in out:
            out[D] = _new()
        _add(out[D], Dd, W, xs[raw][0], xs[raw][1], r)
    return out


def _rec(acc, via, fl, now_iso, info=None):
    """A day's accumulator → its record: the ledger's fields + "b", "c", "e". info: split_read's (its leaves' flag, its
    calls, the cap); None: a block's share."""
    acc = acc or _new()
    if info is not None:
        flag = info["flag"]
    else:
        flag = bool(fl & (F_SMP | F_CUT | F_THR)) or bool(fl & F_OTHER and not acc["oth"])
    e = {}
    for cc, xs in acc["e"].items():
        for X, arr in xs.items():
            a = _trim(arr)
            if a:
                e.setdefault(cc, {})[X] = a
    st = "loss" if acc["loss"] else ("split" if via == "split" else "ok")      # flagged only: "fl", never "loss"
    return {"st": st, "rows": acc["rows"], "loss": acc["loss"], "t": acc["t"], "fl": 1 if flag else 0, "via": via,
            "at": now_iso, "sv": SPLIT_V, "ol": acc["ol"], "n": info["calls"] if info else 0,
            "cap": info["cap"] if info else 0, "b": acc["b"], "c": acc["c"], "e": e}


# ── the recursive split of one activity day ─────────────────────────────────────────────────────────────────────────
# A part = (cin, cout, xin, xout): countries in cin (a frozenset; None: no in-list) else not in cout; install days
# (YYYY-MM-DD) in xin (None: no in-list) else not in xout. The day itself = (None, ∅, None, ∅).
def _filters(p):
    cin, cout, xin, xout = p
    ex = []
    if cin is not None:
        ex.append(cc_in(cin))
    elif cout:
        ex.append(cc_not(cout))
    if xin is not None:
        ex.append(x_in(xin))
    elif xout:
        ex.append({"notExpression": x_in(xout)})
    return ex


def _stats(rows, key):
    """{named value: [rows, revenue]} of one dimension in an answer — a country: not "(other)" / "(not set)" / empty;
    an install day: a real date (YYYY-MM-DD)."""
    out = {}
    for r in rows:
        v = _cc(r) if key == "countryId" else _real(r.get(key))
        if not v or v in (NO_CC, OTHER):
            continue
        s = out.setdefault(v, [0, 0.0])
        s[0] += 1
        s[1] += float(r.get("totalAdRevenue") or 0)
    return out


def _half(order, st, keep_one):
    """The first values of `order` until they hold half its rows (a value the answer did not name counts 1 row) —
    at least one; keep_one: at least one left for the other half."""
    w = [max(1, (st.get(v) or (0,))[0]) for v in order]
    tot, cum, n = sum(w), 0, 0
    while n < len(order) and (n == 0 or 2 * cum < tot):
        cum += w[n]
        n += 1
    return order[:min(n, len(order) - 1) if keep_one else n]


def _kids(p, rows, dims):
    """A part whose answer still has "(other)" → the two parts that partition it (module doc, step 3); None: it cannot
    be split (one country and one install day, or nothing named to split by)."""
    cin, cout, xin, xout = p
    if "countryId" in dims and (cin is None or len(cin) > 1):
        st = _stats(rows, "countryId")
        if cin is not None:
            order = sorted(cin, key=lambda c: (-(st.get(c) or (0, 0.0))[0], -(st.get(c) or (0, 0.0))[1], c))
            h = frozenset(_half(order, st, True))
            return [(h, frozenset(), xin, xout), (cin - h, frozenset(), xin, xout)]
        order = sorted((c for c in st if c not in cout), key=lambda c: (-st[c][0], -st[c][1], c))
        if order:
            h = frozenset(_half(order, st, False))
            return [(h, frozenset(), xin, xout), (None, cout | h, xin, xout)]
    st = _stats(rows, "firstSessionDate")
    if xin is not None:
        if len(xin) < 2:
            return None
        h = frozenset(_half(sorted(xin), st, True))
        return [(cin, cout, h, frozenset()), (cin, cout, xin - h, frozenset())]
    order = sorted(x for x in st if x not in xout)
    if not order:
        return None
    h = frozenset(_half(order, st, False))
    return [(cin, cout, h, frozenset()), (cin, cout, None, xout | h)]


def _orev(rows):
    return sum(float(r.get("totalAdRevenue") or 0) for r in rows
               if OTHER in (r.get("firstSessionDate"), r.get("countryId")) or not _real(r.get("date")))


def _named(rows):
    """Rows GA4 kept by name (not "(other)", a real activity day)."""
    return sum(1 for r in rows if OTHER not in (r.get("firstSessionDate"), r.get("countryId")) and _real(r.get("date")))


def _micros(rows):
    return sum(int(round(float(r.get("totalAdRevenue") or 0) * 1e6)) for r in rows)


def _hidden(rows, fl):
    """GA4 says it rolled rows into "(other)" but no "(other)" row shows (an in-list filter drops that row)."""
    return bool(fl & F_OTHER) and not _other(rows)


def day_total(ga, D):
    """Activity day D's whole ad revenue (micros): dimension date only and no filter — one row, nothing GA4 could roll
    into "(other)" or a filter could drop. None: GA4 sampled or cut that answer (nothing to measure by)."""
    rows = ga.report_all(body(D, D, ("date",)), page_rows=gu.UNI_PAGE_ROWS)
    if _flags(ga, rows) & (F_SMP | F_CUT):
        return None
    return _micros(rows)


def split_read(ga, D, cap=DAY_CAP, xs=None, dims=DIMS, root_why=RETRY, total=None):
    """Activity day D through the recursive split (module doc, step 3) → (rows of every final part, info {"calls",
    "parts", "depth", "cap" (1: the cap left "(other)" a deeper split could read), "fl" (every part's GA4 flags), "flag"
    (a flag with nothing to measure it by: sampling / thresholding / a cut answer, dataLossFromOtherRow on a part with
    no "(other)" row when the day's total could not be read, or parts holding more than that total), "hid" (micros the
    day's total holds beyond every part's rows: "(other)" GA4 hid under an in-list — 0: none, or not measured), "tot"
    (that total, when read), "futile" (1: a split named no row its part had not — filters read no more of this day)}).
    xs: the install days (YYYY-MM-DD) the read is held to (an in-list; None: every one); dims: without countryId only
    install days split; root_why: the flags that split the whole day's answer (a part's own: "(other)" rows, sampling,
    a cut answer, dataLossFromOtherRow); total(ga, D): the day's true total in micros, or None (read once, only when a
    final part is flagged "(other)" with no "(other)" row — a call past the cap). Raises Stop: nothing of the day
    kept."""
    c0, seq, leaves, heap = ga.calls, 0, [], []
    info = {"calls": 0, "parts": 0, "depth": 0, "cap": 0, "fl": 0, "flag": False, "hid": 0, "tot": None, "futile": 0}
    held = False                                                # a hidden-"(other)" part the cap kept from a split

    def read(p):
        ex = _filters(p)
        rows = ga.report_all(body(D, D, dims), extra=ex or None, page_rows=gu.UNI_PAGE_ROWS)
        return rows, _flags(ga, rows)

    def put(p, rows, fl, depth, why):
        nonlocal seq
        if _other(rows) or fl & why:
            seq += 1                                            # the most "(other)" revenue first; a hidden one (no
            heapq.heappush(heap, (-_orev(rows), -len(rows), seq, depth, p, rows, fl))   # row): the most rows first
        else:
            leaves.append((rows, fl))
    root = (None, frozenset(), frozenset(xs) if xs is not None else None, frozenset())
    rows, fl = read(root)
    put(root, rows, fl, 0, root_why)
    while heap:
        _, _, _, depth, p, rows, fl = heapq.heappop(heap)
        kids = _kids(p, rows, dims)
        if kids and ga.calls - c0 + len(kids) > cap:            # the cap: no more parts read
            info["cap"] |= int(_other(rows))
            held = held or _hidden(rows, fl)
            kids = None
        if not kids:
            leaves.append((rows, fl))                           # what is still "(other)" in it: the day's loss
            continue
        got = [read(k) for k in kids]                           # the part's rows kept until both halves are in
        if not fl & (F_SMP | F_CUT) and sum(_named(r) for r, _ in got) <= _named(rows):
            info["futile"] = 1                                  # the halves named no row the part had not (GA4 rolls
            leaves.append((rows, fl))                           # rows into "(other)" before a filter): no part read
            leaves.extend((e[5], e[6]) for e in heap)           # by a filter will — the part as it was, the others as
            heap.clear()                                        # they are; what is "(other)" in them: measured loss
            break
        del rows
        for k, (r, f) in zip(kids, got):
            put(k, r, f, depth + 1, RETRY)
        info["depth"] = max(info["depth"], depth + 1)
    measured = False
    if total is not None and any(_hidden(r, f) for r, f in leaves):
        T = total(ga, D)                                        # GA4 hid "(other)" somewhere: the day's own total
        if T is not None:
            measured, info["tot"] = True, T
            s, n = sum(_micros(r) for r, _ in leaves), sum(len(r) for r, _ in leaves)
            tol = n // 2 + 1 + T // 1000000                     # rounding: ½ micro a row, 1 ppm of the total
            if T - s > tol:
                info["hid"] = T - s
                info["cap"] |= int(held)
            elif s - T > tol:
                info["flag"] = True                             # the parts hold more than the day: no measure
    out = []
    for rows, f in leaves:
        out.extend(rows)
        info["fl"] |= f
        info["flag"] = info["flag"] or bool(f & (F_SMP | F_CUT | F_THR)) or (_hidden(rows, f) and not measured)
    info.update(calls=ga.calls - c0, parts=len(leaves))
    return out, info


def read_day(ga, D, now_iso, cap=DAY_CAP, full=None):
    """One activity day alone (steps 2 and 3 of the module doc) → its record ("(other)" GA4 hid, measured by the day's
    total, in its t / loss / ol; "hd" / "fu" on the record only when there is one: the hidden micros / a futile split).
    full: the cap a day of its kind gets — read with less (a day cut run after run), "cap" 2 when the cap left
    "(other)" (a full read could take more of it). Raises Stop (nothing of the day kept)."""
    rows, info = split_read(ga, D, cap, total=day_total)
    acc = _group(rows, D).get(D.isoformat()) or _new()
    del rows
    if info["hid"]:
        for f in ("t", "loss", "ol"):
            acc[f] += info["hid"]
    if info["cap"] and full is not None and cap < full:
        info["cap"] = 2
    rec = _rec(acc, "split" if info["depth"] else "day", info["fl"], now_iso, info)
    if info["hid"]:
        rec["hd"] = info["hid"]
    if info["futile"]:
        rec["fu"] = 1
    return rec


def _cap_of(cut, cap):
    """A day's cap: `cap`, or — cut by a Stop in CUT_TRIES runs or more — what a run gave it less one, halved for every
    further cut, never below MIN_CAP."""
    if isinstance(cut, dict) and int(cut.get("k") or 0) >= CUT_TRIES:
        return max(MIN_CAP, min(cap, (int(cut.get("n") or 0) - 1) >> (int(cut["k"]) - CUT_TRIES)))
    return cap


def _read_day(ga, D, now_iso, mem, cap, key="cut"):
    """read_day with the cut memory mem[key] ("cut": a final day of the walk, "hcut": a hot day — never one for the
    other: a hot day's smaller cap never follows it into its final read; the repair: its own state's "cut"). A Stop
    counts as the day's cut only when the day was the run's FIRST read (it had the run's whole allowance — never one
    started with what the walk, the hot days or other days left), after ≥ MIN_CAP calls of it, and not the app's call
    cap: {"D", "n" the most calls a run gave it, "k" how many times}."""
    k, c0 = D.isoformat(), ga.calls
    cut = mem.get(key) if isinstance(mem.get(key), dict) and mem[key].get("D") == k else None
    try:
        rec = read_day(ga, D, now_iso, _cap_of(cut, cap), full=cap)
    except Stop as e:
        n = ga.calls - c0
        if c0 == 0 and n >= MIN_CAP and str(e) != "calls":
            mem[key] = {"D": k, "n": max(n, int((cut or {}).get("n") or 0)), "k": int((cut or {}).get("k") or 0) + 1}
        raise
    if cut is not None:
        mem.pop(key, None)
    return rec


def _skip_block(head, a, n):
    hv = head.get("heavy")
    try:
        return bool(hv) and n >= int(hv["n"]) and 0 <= (a - _d(hv["at"])).days < HEAVY_KEEP
    except (KeyError, TypeError, ValueError):
        return False


def read_range(ga, a, b, head, now_iso, cap=DAY_CAP, key="cut"):
    """Activity days a … b → (D, record) in day order, adaptive (see the module doc). A generator: a Stop between its
    calls keeps every day it yielded. head: where the heavy and cut memories live; key: the cut memory's (the walk's
    "cut", the hot days' "hcut")."""
    n = (b - a).days + 1
    if n > 1 and not _skip_block(head, a, n):
        rows = ga.report_all(body(a, b), page_rows=gu.UNI_PAGE_ROWS)
        fl = _flags(ga, rows)
        if not (_other(rows) or fl & RETRY):
            hv = head.get("heavy")
            if hv and n >= int(hv.get("n") or 0):           # a block as long as the heavy one came back whole
                head.pop("heavy", None)
            got = _group(rows)
            del rows
            for D in _days(a, b):
                yield D, _rec(got.get(D.isoformat()), "block", fl, now_iso)
            return
        del rows
        head["heavy"] = {"at": a.isoformat(), "n": n}
    for D in _days(a, b):
        yield D, _read_day(ga, D, now_iso, head, cap, key)


# ── the store ───────────────────────────────────────────────────────────────────────────────────────────────────────
def app_dir(data_dir, app_id):
    return os.path.join(data_dir, DIR, gu.file_key(app_id))


def month_path(data_dir, app_id, k):
    return os.path.join(app_dir(data_dir, app_id), k + ".json.gz")


def hot_path(data_dir, app_id):
    return os.path.join(app_dir(data_dir, app_id), HOT)


def _month_ok(s, stream_id):
    return (isinstance(s, dict) and s.get("v") == V and str(s.get("stream_id") or "") == str(stream_id or "")
            and all(isinstance(s.get(f), dict) for f in ("days", "b", "c", "e", "t", "loss")))


def load_head(data_dir, app_id):
    """The app's head + hot days (None: no cube, or not of this format)."""
    s = gu.load_store(hot_path(data_dir, app_id))
    return s if isinstance(s, dict) and s.get("v") == V and isinstance(s.get("d"), dict) else None


def months(data_dir, app_id, stream_id):
    """The app's month files of THIS stream, oldest first → (YYYY-MM, file) one at a time (a generator: the build folds
    a month and lets it go)."""
    folder = app_dir(data_dir, app_id)
    try:
        names = sorted(f for f in os.listdir(folder)
                       if len(f) == 15 and f.endswith(".json.gz") and f[4] == "-" and f[:4].isdigit())
    except OSError:
        return
    for f in names:
        s = gu.load_store(os.path.join(folder, f))
        if _month_ok(s, stream_id):
            yield f[:7], s


def _empty_month(stream_id):
    return {"v": V, "stream_id": stream_id, "days": {}, "b": {}, "c": {}, "e": {}, "t": {}, "loss": {}}


def _merge(mo, k, rec):
    """Day k's record into a month (its b / c / e added, its t / loss / ledger set) — the caller makes sure it is not
    there yet."""
    for X, js in (rec.get("b") or {}).items():
        bx = mo["b"].setdefault(X, {})
        for j, ws in js.items():
            bj = bx.setdefault(j, {})
            for W, v in ws.items():
                bj[W] = bj.get(W, 0) + v
    for cc, xs in (rec.get("c") or {}).items():
        cm = mo["c"].setdefault(cc, {})
        for X, js in xs.items():
            cx = cm.setdefault(X, {})
            for j, v in js.items():
                cx[j] = cx.get(j, 0) + v
    for cc, xs in (rec.get("e") or {}).items():
        em = mo["e"].setdefault(cc, {})
        for X, arr in xs.items():
            cur = em.get(X) or []
            if len(cur) < len(arr):
                cur = cur + [0] * (len(arr) - len(cur))
            em[X] = _trim([a + (arr[i] if i < len(arr) else 0) for i, a in enumerate(cur)])
    mo["t"][k] = rec.get("t") or 0
    if rec.get("loss"):
        mo["loss"][k] = rec["loss"]
    mo["days"][k] = {f: rec.get(f) for f in LEDGER}


def _oloss(led, rep_at=None):
    """A folded day's "(other)" micros a read again could still take (0: none):
      * read with an older split (sv < SPLIT_V): "ol" when the ledger has it; an older ledger: a "split" day's loss (a
        "block" / "day" day had no "(other)" row: its loss is install days that are not dates, which no split reads);
      * read with this split but under a smaller cap than a day's (cap 2: a day cut run after run) — only when folded
        after the month's last repair of this split (rep_at; a day the repair itself read so stays as it is: a month is
        repaired once for what the walk folded, never again and again)."""
    if not isinstance(led, dict):
        return 0
    if int(led.get("sv") or 1) >= SPLIT_V:
        if int(led.get("cap") or 0) == 2 and (rep_at is None or str(led.get("at") or "") > rep_at):
            return int(led.get("ol") or 0)
        return 0
    if led.get("ol") is not None:
        return int(led.get("ol") or 0)
    return int(led.get("loss") or 0) if led.get("via") == "split" else 0


def _ofl(led):
    """A day the one-level split read (sv 1, "split") that GA4 flagged with no "(other)" row to measure it by: its
    country in-list part may have hidden "(other)" — worth a read again, by how much unknown."""
    return int(isinstance(led, dict) and int(led.get("sv") or 1) < SPLIT_V and led.get("via") == "split"
               and bool(led.get("fl")))


def _month_oloss(mo):
    """A month → (recoverable "(other)" micros, loss micros, revenue micros, flagged one-level split days) over its
    folded days."""
    ol = lo = t = nf = 0
    rep = mo.get("rep") if isinstance(mo.get("rep"), dict) else {}
    rep_at = str(rep["at"]) if rep.get("sv") == SPLIT_V and rep.get("at") else None
    for led in (mo.get("days") or {}).values():
        if isinstance(led, dict):
            ol += _oloss(led, rep_at)
            nf += _ofl(led)
            lo += int(led.get("loss") or 0)
            t += int(led.get("t") or 0)
    return ol, lo, t, nf


class Cube:
    """One app's cube in a run: the head (+ hot days), the month files loaded on first use, the months a fold touched
    (only those are written), counts for the log line. data_dir None: in memory only."""

    def __init__(self, data_dir, app_id, stream_id):
        self.data_dir, self.app_id, self.stream_id = data_dir, app_id, str(stream_id or "")
        h = load_head(data_dir, app_id) if data_dir else None
        if not h or str(h.get("stream_id") or "") != self.stream_id:     # another stream: start over
            h = {"v": V, "stream_id": self.stream_id, "d": {}}
        self.head = h
        self.m, self.touched = {}, set()
        self.bad = set()                # months whose file is on disk but not a month of this stream (read again)
        self.folded = self.split = self.loss = self.flagged = self.reread = 0
        self.deeper = self.capped = self.rep_days = self.repaired = self.hidden = self.futile = 0
        self.pruned = self.dirty = False    # dirty: the head changed with no read (the repair's queue)
        self.rp = None                  # the repair's copy of a month: {"k", "mo", "dirty", "done"}

    def month(self, k):
        """Month k's file (loaded once). Missing: an empty month. On disk but unreadable (a damaged gzip, a cut copy …),
        not this format or another stream's: an empty month too, but in `bad` — step_app then reads the WHOLE month
        again before anything is folded into it, so the file is never written over with fewer days than it held."""
        if k not in self.m:
            s = None
            if self.data_dir:
                p = month_path(self.data_dir, self.app_id, k)
                if os.path.exists(p) or os.path.exists(p[:-3]):
                    s = gu.load_store(p)
                    if not _month_ok(s, self.stream_id):
                        self.bad.add(k)
                        if not (isinstance(s, dict) and str(s.get("stream_id") or "") != self.stream_id):
                            self.reread += 1        # this stream's (or unreadable): counted; another stream's: not
                        s = None
            self.m[k] = s if s is not None else _empty_month(self.stream_id)
        return self.m[k]

    def has(self, D):
        k = D.isoformat()
        return k in self.month(k[:7])["days"]

    def fold(self, D, rec):
        """A FINAL day's record into its month — once (a day already in the ledger: nothing)."""
        k = D.isoformat()
        mo = self.month(k[:7])
        if k in mo["days"]:
            return False
        _merge(mo, k, rec)
        self.touched.add(k[:7])
        self.head.setdefault("d", {}).pop(k, None)
        self.folded += 1
        self.split += rec.get("via") == "split"
        self.deeper += (rec.get("n") or 0) > 3      # past the first split (one level is 3 calls)
        self.capped += bool(rec.get("cap"))         # the cap left "(other)" a deeper split could read
        self.hidden += bool(rec.get("hd"))          # "(other)" GA4 hid under an in-list, measured by the day's total
        self.futile += bool(rec.get("fu"))          # a split that named nothing new (filters read no more)
        self.loss += bool(rec.get("loss"))          # measured: revenue GA4 left "(other)" / with no install day
        self.flagged += bool(rec.get("fl"))         # GA4's flag with nothing to measure it by (the page's ≈)
        return True

    def rep_path(self, k):
        return os.path.join(app_dir(self.data_dir, self.app_id), k + REP)

    def rep(self, k):
        """Month k's repair copy (loaded once): the file of an earlier run when it is this stream's and of SPLIT_V (its
        days are final reads of this split), else empty."""
        if self.rp is None or self.rp["k"] != k:
            s = gu.load_store(self.rep_path(k)) if self.data_dir else None
            if not (_month_ok(s, self.stream_id) and (s.get("rep") or {}).get("sv") == SPLIT_V):
                s = dict(_empty_month(self.stream_id), rep={"sv": SPLIT_V})
            self.rp = {"k": k, "mo": s, "dirty": False, "done": False}
        return self.rp["mo"]

    def drop_rep(self, k):
        """An older repair's copy of month k: gone (never made the month file)."""
        if self.rp is not None and self.rp["k"] == k:
            self.rp = None
        if self.data_dir:
            try:
                os.remove(self.rep_path(k))
            except OSError:
                pass

    def each_month(self):
        """Every month of the app, oldest first, one at a time (on disk: the touched ones written first)."""
        if not self.data_dir:
            yield from sorted(self.m.items())
            return
        self.save()
        for k, s in months(self.data_dir, self.app_id, self.stream_id):
            yield k, self.m.get(k, s)

    def let_go(self, keep):
        """Every month but `keep` written and let go (the repair holds its month and its copy only)."""
        if self.data_dir:
            self.save()
            for k in [k for k in self.m if k != keep]:
                self.m.pop(k)

    def save(self, before=None):
        """The touched months (before: only those older than that month — written and let go: the walk moved on).
        In memory only (no data_dir): nothing to write, every month kept. Without `before`, the repair's copy after
        the months: written while it is being built (once it became its month, save_head removes it — after the
        head that no longer names it)."""
        if not self.data_dir:
            return
        for k in sorted(self.touched):
            if before and k >= before:
                continue
            write_json_gz_stable(month_path(self.data_dir, self.app_id, k), self.m[k])
            self.touched.discard(k)
        if before:
            for k in [k for k in self.m if k < before and k not in self.touched]:
                self.m.pop(k, None)
        elif self.rp is not None and not self.rp["done"] and self.rp["dirty"]:
            write_json_gz_stable(self.rep_path(self.rp["k"]), self.rp["mo"])
            self.rp["dirty"] = False

    def save_head(self):
        """The head (after the months: it never runs ahead of them); then a repair's copy that became its month goes
        (a run killed before that leaves a copy no head names: the next repair of that month starts without it)."""
        if self.data_dir:
            write_json_gz_stable(hot_path(self.data_dir, self.app_id), self.head)
        if self.rp is not None and self.rp["done"]:
            self.drop_rep(self.rp["k"])


def step_app(ga, cube, today, hs, now):
    """One app's run on its cube → "fetched" or "fresh". Raises Stop (what was folded is kept, the cursor where it
    stopped; the caller saves the months, then the head)."""
    h, now_iso, did = cube.head, gu._now_iso(now), False
    edge = today - timedelta(days=FINAL_LAG)
    d = h.setdefault("d", {})
    for k in [k for k in d if k <= edge.isoformat()]:      # final now: a copy read while it was filling never counts
        d.pop(k)                                            # (a hole until the walk folds it — even when the walk stops
        cube.pruned = True                                  # before it)
    hc = h.get("hcut")
    if hc is not None and not (isinstance(hc, dict) and str(hc.get("D") or "") > edge.isoformat()):
        h.pop("hcut")                                       # a hot day's cut memory goes with it (its final read: the
        cube.pruned = True                                  # walk's own cap and memory)
    if not h.get("from") or not h.get("next") or hs < _d(h["from"]):  # first walk, or the history start moved back:
        h["from"], h["next"] = hs.isoformat(), hs.isoformat()         # from it (folded days are skipped, not re-read)
        h.pop("done", None)                                 # … and the build waits for the walk again (columns in one go)
    nxt = max(hs, _d(h["next"]))
    h["next"] = nxt.isoformat()
    while nxt <= edge:
        k = nxt.isoformat()[:7]
        cube.save(before=k)                                 # months the walk left: written and let go (≤ 2 held)
        mo = cube.month(k)
        start = max(hs, nxt.replace(day=1))
        if k in cube.bad and any(D.isoformat() not in mo["days"] for D in _days(start, nxt - timedelta(days=1))):
            nxt = start                                     # its file unreadable / not this stream's: the whole month
            h["next"] = nxt.isoformat()                     # again (never written over with only the days after the
            h.pop("done", None)                             # cursor); the build waits for the walk again
            continue
        if nxt.isoformat() in mo["days"]:                   # folded already (a walk from a moved history start, or a
            while nxt <= edge and nxt.isoformat()[:7] == k and nxt.isoformat() in mo["days"]:   # run whose head was
                nxt += timedelta(days=1)                    # not written after its months): past them, read nothing
            h["next"] = nxt.isoformat()
            continue
        b = min(edge, nxt + timedelta(days=BLOCK - 1))
        x = nxt + timedelta(days=1)
        while x <= b:                                       # never a folded day in a block
            if cube.has(x):
                b = x - timedelta(days=1)
                break
            x += timedelta(days=1)
        for D, rec in read_range(ga, nxt, b, h, now_iso):
            cube.fold(D, rec)
            h["next"] = (D + timedelta(days=1)).isoformat()
            h["walk_at"] = now_iso                          # the walk's last step (the page's "on its way" note)
            did = True
        nxt = b + timedelta(days=1)
    h["done"] = True                                        # the walk reached the final edge
    for k in [k for k in d if not (hs.isoformat() <= k <= today.isoformat())]:
        d.pop(k)
    a = max(hs, edge + timedelta(days=1))
    due = gu._hours_since(h.get("hot_at"), now) >= REFRESH_HOURS or h.get("hot_today") != today.isoformat()
    if a <= today and due:
        cyc = h.get("hot_cyc")                              # this round of the hot days: one a Stop cut goes on with
        if not (isinstance(cyc, list) and len(cyc) == 2 and cyc[1] == today.isoformat()):  # the days it has not read
            cyc = h["hot_cyc"] = [now_iso, today.isoformat()]     # (the same property day); else a new round
        todo = [D.isoformat() for D in _days(a, today) if str((d.get(D.isoformat()) or {}).get("at") or "") < cyc[0]]
        for x, y in _runs(todo):
            for D, rec in read_range(ga, x, y, h, now_iso, cap=HOT_CAP, key="hcut"):
                d[D.isoformat()] = rec                      # replaced (never folded: read while not final)
                did = True
        h["hot_at"], h["hot_today"] = now_iso, today.isoformat()
        h.pop("hot_cyc", None)
    did = repair(ga, cube, now) or did                      # with what the run has left
    return "fetched" if did else "fresh"


def _scan(cube):
    """The repair's queue: every month of the app with recoverable "(other)" loss (or one-level split days GA4 flagged
    with no "(other)" row) → [[YYYY-MM, its measured share of the month's revenue]], the biggest share first, the more
    recent month first on a tie (a month with flagged days only: share 0, after every measured one)."""
    q = []
    for k, mo in cube.each_month():
        ol, _, t, nf = _month_oloss(mo)
        if ol > 0 or nf > 0:
            q.append([k, round(ol / t, 6) if t > 0 else (1.0 if ol else 0.0)])
    q.sort(key=lambda e: e[0], reverse=True)
    q.sort(key=lambda e: -e[1])
    return q


def _runs(days):
    """Sorted YYYY-MM-DD days → (a, b) ranges of consecutive days, ≤ BLOCK days each."""
    out = []
    for k in days:
        D = _d(k)
        if out and D == out[-1][1] + timedelta(days=1) and (D - out[-1][0]).days < BLOCK:
            out[-1][1] = D
        else:
            out.append([D, D])
    return out


def _room(ga, rp):
    """Calls the run has left ≥ what a repair day needs: the repair's calls a day so far (rounded up; at least
    MIN_CAP), DAY_CAP + 1 before its first day (a day's cap and its total) — checked before every day (unknown cap:
    yes)."""
    mx = getattr(ga, "max_calls", None)
    if mx is None:
        return True
    n = int(rp.get("n") or 0)
    need = max(MIN_CAP, -(-int(rp.get("c") or 0) // n)) if n else DAY_CAP + 1
    return mx - ga.calls >= need


REP_FIELDS = ("k", "old", "at", "c", "n", "heavy", "cut")


def repair(ga, cube, now):
    """The repair of months folded before the deeper split (module doc) → True when a day was read. Raises Stop (the
    days read kept in the copy; the app's own call cap only ends the repair for this run)."""
    h, now_iso = cube.head, gu._now_iso(now)
    rp = h.get("rep")
    if not isinstance(rp, dict) or rp.get("sv") != SPLIT_V:     # first time, or a newer split: its own queue
        if isinstance(rp, dict) and rp.get("k"):
            cube.drop_rep(rp["k"])
        rp = h["rep"] = {"sv": SPLIT_V}
        cube.dirty = True
    if not rp.get("k"):
        if not rp.get("q") and gu._hours_since(rp.get("scan"), now) >= RESCAN_DAYS * 24:
            rp["q"], rp["scan"] = _scan(cube), now_iso
            cube.dirty = True
        while rp.get("q") and not rp.get("k"):
            k = str(rp["q"].pop(0)[0])
            cube.dirty = True
            ol, lo, t, nf = _month_oloss(cube.month(k))
            if (ol > 0 or nf > 0) and k not in cube.bad:
                cube.drop_rep(k)                            # a copy no head names (a run killed after its month was
                rp.update(k=k, old={"ol": ol, "loss": lo, "t": t}, at=now_iso, c=0, n=0)   # written): never used
            elif cube.data_dir and k not in cube.touched:   # nothing to repair in it (any more): let go
                cube.m.pop(k, None)
    k = rp.get("k")
    if not k:
        return False
    cube.let_go(keep=k)
    live = cube.month(k)
    acc = None if k in cube.bad else cube.rep(k)
    if acc is None or not acc["days"] and not any(_month_oloss(live)[i] for i in (0, 3)):
        cube.drop_rep(k)                                    # its file unreadable now (never a copy made the month with
        for f in REP_FIELDS:                                # nothing to hold it against), or nothing left to read in
            rp.pop(f, None)                                 # it (a run that wrote the repaired month but not its head):
        cube.dirty = True                                   # the next month of the queue next run
        return False
    did, c0 = False, ga.calls
    try:
        for D in sorted(D for D in live["days"] if D not in acc["days"]):   # day by day: a block of a month with
            if ga.calls - c0 >= REPAIR_CALLS or not _room(ga, rp):         # "(other)" only comes back with it again
                break
            last = ga.calls
            rec = _read_day(ga, _d(D), now_iso, rp, DAY_CAP)
            _merge(acc, D, rec)
            cube.rp["dirty"] = did = True
            cube.rep_days += 1
            cube.hidden += bool(rec.get("hd"))
            cube.futile += bool(rec.get("fu"))
            rp["c"], rp["n"] = int(rp.get("c") or 0) + ga.calls - last, int(rp.get("n") or 0) + 1
    except Stop as e:
        if str(e) != "calls":                               # the budget, the property's quota: the app stops here
            raise
    if live["days"] and all(D in acc["days"] for D in live["days"]):    # every day read again: the copy is the month
        t = _month_oloss(acc)[2]
        nol = sum(int(v.get("ol") or 0) for v in acc["days"].values() if isinstance(v, dict))
        old = rp.get("old") or {}
        acc["rep"] = {"sv": SPLIT_V, "at": now_iso, "ol0": old.get("ol"), "loss0": old.get("loss"), "t0": old.get("t")}
        cube.m[k] = acc
        cube.touched.add(k)
        cube.rp["done"] = True
        cube.repaired += 1
        cube.dirty = True                                   # the head written (k cleared) even in a run with no call
        rp["log"] = (list(rp.get("log") or []) + [[k, old.get("ol"), nol, t, now_iso]])[-LOG_KEEP:]
        for f in REP_FIELDS:
            rp.pop(f, None)
    return did


# ── state and the run ───────────────────────────────────────────────────────────────────────────────────────────────
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


COUNTS = ("selected", "with_ga4", "fetched", "fresh", "failed", "deferred", "waiting", "days", "split", "deeper",
          "capped", "hidden", "futile", "loss", "flagged", "reread", "repair_days", "repaired", "calls", "tokens")


def refresh_all(cfg, data_dir, apps, now=None, clock=None, budget=BUDGET_SEC, workers=WORKERS):
    """Every selected app (uninstall_build's list) → {"counts", "apps": {app id: fetched|fresh|failed|deferred|
    waiting}}. Never raises; never prints."""
    clock = clock or time.monotonic
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
        by_prop = {}
        for a in apps:
            if a.get("same_as") or not a.get("package"):
                continue
            counts["selected"] += 1
            r = routes.get(a["package"])
            if not r:
                continue
            counts["with_ga4"] += 1
            aid = a["app_id"]
            um = gaud._uni_meta(ust, data_dir, aid, r)
            if not um:
                out["apps"][aid] = "waiting"
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
            by_prop.setdefault(r["property_id"], []).append((a, st, r, gu._d(um["history_start"])))
        for xs in by_prop.values():                     # turns: the app that waited longest first; on a tie the one
            xs.sort(key=lambda t: (t[1].get("turn") or "", bool(t[1].get("cut")),   # cut off last time (a backfill
                                   t[1].get("last_ok") or "", t[0]["app_id"]))    # using the budget) after the others

        def one_prop(pid):
            prop = {"quota": None, "stop": None}
            for a, st, r, hs in by_prop[pid]:
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
                tz = ust["tz"].get(pid) or "UTC"
                today = now.astimezone(ZoneInfo(tz)).date()
                cube = Cube(data_dir, aid, r["stream_id"])
                ga = gf.App(tok, pid, r["stream_id"], prop, over=over, max_calls=MAX_CALLS)
                try:
                    res = step_app(ga, cube, today, hs, now)
                    upd = dict(last_try=now_iso, fail=None, turn=now_iso, cut=None)
                    if res == "fetched":
                        upd["last_ok"] = now_iso
                except Stop:
                    res, upd = "deferred", dict(deferred=True, turn=now_iso, cut=True)
                except Exception as e:
                    res, upd = "failed", dict(last_try=now_iso, fail=gu._fail_kind(e), turn=now_iso, cut=None)
                try:                                    # the months first: the head never runs ahead of them
                    cube.save()
                    if ga.calls or cube.folded or cube.pruned or cube.dirty:
                        cube.head.update(v=V, app_id=aid, package=a["package"], property_id=pid,
                                         stream_id=str(r["stream_id"]), time_zone=tz, hs=hs.isoformat())
                        cube.save_head()
                except Exception as e:
                    res, upd = "failed", dict(last_try=now_iso, fail=gu._fail_kind(e))
                with lock:
                    if res != "deferred":
                        st.pop("deferred", None)
                    st.update(upd)
                    if not st.get("cut"):
                        st.pop("cut", None)
                    st["key"] = gu.file_key(aid)
                    out["apps"][aid] = res
                    counts["calls"] += ga.calls
                    counts["tokens"] += ga.tok
                    counts["days"] += cube.folded
                    counts["split"] += cube.split
                    counts["deeper"] += cube.deeper
                    counts["capped"] += cube.capped
                    counts["hidden"] += cube.hidden
                    counts["futile"] += cube.futile
                    counts["repair_days"] += cube.rep_days
                    counts["repaired"] += cube.repaired
                    counts["loss"] += cube.loss
                    counts["flagged"] += cube.flagged
                    counts["reread"] += cube.reread

        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            list(ex.map(one_prop, sorted(by_prop)))
        save_state(data_dir, state)
    except Exception as e:                              # a bug here must never cost the build
        out["error"] = type(e).__name__
    for v in out["apps"].values():
        if v in counts:
            counts[v] += 1
    return out


def log_line(status):
    """The build log's ONE line for this step — counts only."""
    c = (status or {}).get("counts") or {}
    return ("ga4 cube: apps %d, with GA4 %d, fetched %d, fresh %d, failed %d, deferred %d, waiting %d, days folded %d, "
            "split %d, deeper %d, capped %d, hidden %d, futile %d, loss %d, flagged %d, months read again %d, "
            "repair days %d, months repaired %d, calls %d, tokens %d%s"
            % tuple([gaud._int(c.get(k)) for k in COUNTS]
                    + [(", error " + status["error"]) if (status or {}).get("error") else ""]))
