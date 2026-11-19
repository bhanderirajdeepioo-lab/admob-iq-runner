"""⚖️ Breakeven — the RETURNING-session eCPM of each install day's users, by country, for the tab's 14-day card (owner, 14
Nov 2026: "return session ke ecpm ko check karne ke liye day 1,2,3,4,7,14 … 100 number ke hisab se"; 15 Nov 2026: day 1 =
the FIRST session's eCPM, "haan pehla session wala lo"). Day 1's base is already stored: fetch.ga4_nvr's first-session
("new") revenue and impressions by country, the same base the tab's benchmark uses. This fetch reads the SAME users
(GA4's firstSessionDate = the install day) on their later days: card days 2, 3, 4, 7 and 14 = install ages 1, 2, 3, 6
and 13. Age 0 is read too (the install day as a whole), for the checks against the cohort cube.

ONE read shape, one call an ACTIVITY day D (design: spec_returning_ecpm.md §2; measured first by ga4_cecpm_probe):
  runReport [D, D] date × firstSessionDate × countryId → totalAdRevenue, eventCount, eventName == ad_impression (the
  impressions as events: whole where publisherAdImpressions is not, fetch.ga4_nvr's measurement), firstSessionDate
  in-list = the install days D − a for a in AGES, pinned to the app's Android stream, every row paged (USD).
  Revenue and impressions of a row come from the same ad_impression events: a named row's eCPM is exact, and a row GA4
  folds into "(other)" goes whole (the coverage drops, the value does not move) — nothing to split or repair.
  On the biggest apps GA4 SAMPLES this read on their busiest days (ga4_cecpm_probe measured it, and a sampled cohort
  eCPM came far off GA4's whole numbers — never kept). The same read without the country (date × firstSessionDate)
  came whole there: such a day keeps that one ("pool", every country together under "*"). The newest days read it
  once a run tells them to (the run's first final day always asks the country read again); the history does too after
  POOL_RUN sampled country reads in a row, asking the country read again every POOL_CHECK days of it (an app's older,
  quieter days often come whole) — never the slow, costly sampled read on every day.

Store, kept for good (private repo), the ACTIVITY month's file and a head:
  data/ga4_cecpm/<key>/<YYYY-MM>.json.gz   {"v", "stream_id", "ages", "days": {D: day record}}
  data/ga4_cecpm/<key>/head.json.gz        {"v", "app_id", "package", "property_id", "stream_id", "time_zone", "ages",
                                            "hs", "upto", "oldest", "done", "hot_at", "hot_today", "hot": {D: day
                                            record}, "retry": {D: [reads again so far, last read at]}, "redo": [D, …],
                                            "pk": {D: the most ad events a day not folded yet showed}, "low": {D:
                                            first seen collapsed}, "chk": the property day the months were checked,
                                            "mid": {D: last read — a day not folded yet older than HOT_DAYS (only
                                            while FINAL_LAG is past HOT_DAYS)}}
  data/ga4_cecpm/state.json                {"v": 1, "fetch": {app id: {"last_try", "fail", "fails", "last_ok",
                                            "deferred", "turn", "fturn" (its last history fill), "key"}}}
  day record  {"st": "ok" | "oth" | "thr" | "smp" | "cut" | "low" | "pool", "f": GA4's flag bits (ga4_cube F_*), "at",
               "n": rows, "xn" / "xr" / "xi": rows in no cell / their revenue micros / their events,
               "rt": reads again (a retried day only),
               "c": {cc: [r0, i0, r1, i1, …]}}   r = revenue micros and i = ad_impression events of install day D − AGES[k]
               at k (trailing zeros trimmed); cc = GA4's country ("--" not set, "~" its "(other)" country of a real
               install day; "*" every country together: a "pool" day — GA4 sampled the country split, so the day's
               no-country read is kept, "f6" its flags); no "c" on "smp" / "cut" (GA4's sampled numbers are estimates;
               a cut answer is not whole)
  key = ga4_uninstall.file_key(app id) — the same key as the roi_ / be_ files. Cell (country cc, install day X, age
  AGES[k]) = days[X + AGES[k]]["c"][cc][2k : 2k + 2].
  A file of another version, ages or stream is never mixed in: the head of another one starts over (every day read
  again); a month file that cannot be read has its days read again ("redo") before anything is written over it.

Per app and run (step_app; at most MAX_CALLS calls; the property's quota floors as the Audience fetch's; the budget):
  1. the hot copies of days folded since are dropped (a copy read while GA4 was filling never stands in for the final
     read — the cube's rule); edge = the property's today − FINAL_LAG (HOT_DAYS 5 at least: since 14 Nov 2026 GA4
     answers the newest "final" day almost empty for hours around D + 2 … D + 3, and the cube, folding at D + 3, kept
     two such days; and at least GA4_FINAL_DAYS: ga4_final).
     Once a property day every month file the walk folded is checked: a missing or damaged one has its days read again;
  2. forward: every final day since the newest folded one, oldest first ("upto"; the first run: the edge only) — an
     outage never leaves a hole. A day GA4 answers with under COLLAPSE × the most ad events it showed in an earlier
     read of the SAME day (GA4's numbers of a day only grow while it fills; judged on the day's own reads, never
     against other days, so a real drop in traffic folds as it is) is not folded: its fuller hot copy stays, it is read
     again every run, up to LOW_WAIT days past the edge, then folded as it is with its state "low";
  3. hot: every day not folded yet up to today, again every REFRESH_HOURS or when a new property day began — but a day
     HOT_DAYS … FINAL_LAG − 1 days old (not final yet: GA4_FINAL_DAYS past HOT_DAYS) at most once a UTC day ("mid": its
     last read) — replaced, never folded (an answer collapsed against the day's own earlier reads never replaces its
     fuller copy);
  4. retries: a sampled or cut day is read again at most RETRY more times, each ≥ RETRY_GAP_HOURS after the last; an
     answer that is whole replaces it, after the last one it stays as it is;
  5. redo: the days of a month file that could not be read, newest first;
  6. the backfill: oldest − 1 … the app's history start (the Uninstall store's), newest first — the recent history (the
     benchmark's most useful days) comes first. A history start that moved back goes on from where the walk stopped; a
     day its month already holds whole is not asked again (a lost head never costs the history twice).
  A Stop (budget, quota floor, call cap) keeps every day read; the next run goes on in the same order. Month files are
  written as the walk leaves them (at most two held) and at the end, the head after them (the head never runs ahead).
refresh_all: two rounds — every app's newest days (steps 1–5) first, then the history (step 6) with the time left, so a
history fill never holds back another app's newest days; properties side by side (WORKERS; one call at a time each,
own quota), the property whose app waited longest first; on a property the app the budget cut (or never reached) goes
first next run. The budget: the caller's, else FILL_SEC while any app's history is still being read and BUDGET_SEC
after. An app failing FAIL_LINE runs in a row counts "stuck" (the build prints the health banner's line). Switched by
GA4_CECPM. Never raises; never prints (log_line: counts only — never a name, id, date, country or amount).
load_cells: the build's read (be_build) — read-only, one app at a time.
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import ga4_final
from .. import ga4_probe
from ..db import write_json_gz_stable
from . import ga4
from . import ga4_audience as gaud
from . import ga4_cube as gcu
from . import ga4_firstopen as gf
from . import ga4_nvr as gv
from . import ga4_uninstall as gu

DIR = "ga4_cecpm"
V = 1
AGES = (0, 1, 2, 3, 6, 13)          # install ages read: card days 1, 2, 3, 4, 7, 14 (day 1's base is the first session)
DIMS = ("date", "firstSessionDate", "countryId")
DIMS_P = ("date", "firstSessionDate")         # the no-country read: an app whose country split GA4 samples
METS = gv.EV                        # totalAdRevenue, eventCount (under eventName == ad_impression)
HOT_DAYS = 5                        # the newest days read again every REFRESH_HOURS (ages 0 … HOT_DAYS − 1): this
#                                     store's final lag before GA4_FINAL_DAYS — ga4_final.lag's floor (since 14 Nov
#                                     2026 GA4 answers the newest "final" day (D + 2 … D + 3) almost empty for hours,
#                                     and the cube, folding at D + 3, kept two such days for good: the GA4-hole session)
FINAL_LAG = ga4_final.lag(HOT_DAYS)  # an activity day is folded once ≤ the property's today − FINAL_LAG (HOT_DAYS, and
#                                     at least GA4_FINAL_DAYS); a day not folded yet HOT_DAYS … FINAL_LAG − 1 days old
#                                     is read again at most once a UTC day (head "mid")
REFRESH_HOURS = 6.0                 # the hot days (every day not folded yet up to today) read again
COLLAPSE = 0.5                      # a day GA4 answers with under this × the most it showed in an earlier read …
TOT_MIN = 1000                      # (when that was ≥ this many ad events) is not taken: its fuller copy stays, it is read
LOW_WAIT = 4                        # again every run, up to LOW_WAIT days past the edge, then folded as it is ("low")
RETRY = 2                           # a sampled / cut day: read again at most this many times …
RETRY_GAP_HOURS = 24.0              # … at least this long after its last read
MAX_CALLS = 150                     # per app per run (the walk goes on next run)
BUDGET_SEC = 60                     # seconds a run once every app's history is read …
FILL_SEC = 180                      # … and while any app's is still being read (the history fill)
RETRY_HOURS = 3.0                   # an app whose run failed waits this long
FAIL_LINE = 3                       # … and after this many failed runs in a row it is "stuck": the health banner
WORKERS = 6                         # properties read side by side (each its own quota; as ga4_nvr)
HEAD = "head.json.gz"
OTHER = "(other)"
NO_CC = gcu.NO_CC                   # "--": countryId not set
OTHER_CC = "~"                      # GA4's "(other)" country of a real install day
BAD = ("smp", "cut")                # a day with no usable cells (retried)
POOL = "pool"                       # GA4 sampled the country split: the day's no-country read kept instead ("*")
POOL_CC = "*"                       # its cells: every country together
POOL_RUN = 3                        # the history: this many sampled country reads in a row → it reads pooled …
POOL_CHECK = 7                      # … asking the country read again every this many days of it
LOW = "low"                         # a newest day still collapsed LOW_WAIT days past the edge (its cells kept, not used)
COUNTS = ("selected", "with_ga4", "fetched", "fresh", "failed", "deferred", "waiting", "days", "hot", "flagged",
          "sampled", "pooled", "held", "low", "no_cell", "reread", "left", "stuck", "calls", "tokens")


# ── the read ───────────────────────────────────────────────────────────────────────────────────────────────────────
def installs(D):
    """The install days the read of activity day D asks for: D − a for a in AGES (YYYY-MM-DD)."""
    return [(D - timedelta(days=a)).isoformat() for a in AGES]


def body(D, dims=DIMS):
    return {"dateRanges": [gu._rng(D, D)], "dimensions": ga4._dim(*dims), "metrics": ga4._dim(*METS),
            "currencyCode": "USD", "keepEmptyRows": False}


def _micros(v):
    try:
        return int(round(float(v or 0) * 1e6))
    except (TypeError, ValueError):
        return 0


def _events(v):
    try:
        return int(round(float(v or 0)))
    except (TypeError, ValueError):
        return 0


def _cc(r):
    cc = gcu._cc(r)
    return OTHER_CC if cc == OTHER else cc


def _state(f):
    if f & gcu.F_SMP:
        return "smp"
    if f & gcu.F_CUT:
        return "cut"
    if f & gcu.F_OTHER:
        return "oth"
    if f & gcu.F_THR:
        return "thr"
    return "ok"


def _trim(arr):
    """Trailing [revenue, events] pairs of zeros dropped (whole pairs: a cell is always even-length)."""
    n = len(arr)
    while n >= 2 and not arr[n - 2] and not arr[n - 1]:
        n -= 2
    return arr[:n]


def parse(rows, D, f, now_iso, cc=None):
    """One day's answer → its record. A row of another day, an install day that is not a date or not one of the asked
    ones counts in "xn" / "xr" / "xi" (measured, in no cell). cc: every row's country (the no-country read: "*")."""
    ds = D.isoformat()
    rec = {"st": _state(f), "f": f, "at": now_iso, "n": len(rows or []), "xn": 0, "xr": 0, "xi": 0}
    if rec["st"] in BAD:
        return rec
    c, w = {}, 2 * len(AGES)
    for r in rows or []:
        x = gcu._real(r.get("firstSessionDate"))
        m, e = _micros(r.get(METS[0])), _events(r.get(METS[1]))
        age = (D - date.fromisoformat(x)).days if x else None
        if gcu._real(r.get("date")) != ds or age not in AGES:
            rec["xn"] += 1
            rec["xr"] += m
            rec["xi"] += e
            continue
        k = AGES.index(age)
        arr = c.setdefault(cc or _cc(r), [0] * w)
        arr[2 * k] += m
        arr[2 * k + 1] += e
    rec["c"] = {cc: _trim(arr) for cc, arr in sorted(c.items())}
    return rec


def read_day(ga, D, now_iso, pool=False):
    """Activity day D → its record (raises Stop as the App does: nothing is kept of a read that did not end). The
    country read; when GA4 samples it, the same day's no-country read instead — whole on every app the probe measured
    — kept as st "pool" with its cells under "*" (the country split's sampled numbers are never kept: the probe found
    a sampled cohort eCPM far off GA4's whole numbers). pool: the no-country read only (an app whose country read GA4
    samples: never the slow, costly sampled read again on every day)."""
    f6 = None
    if not pool:
        rows = ga.report_all(body(D), event=gv.EVENT, extra=[gcu.x_in(installs(D))], page_rows=gu.UNI_PAGE_ROWS)
        f = gcu._flags(ga, rows) | (gcu.F_OTHER if gcu._other(rows) else 0)
        if not f & gcu.F_SMP:
            return parse(rows, D, f, now_iso)
        f6 = f
    rows = ga.report_all(body(D, DIMS_P), event=gv.EVENT, extra=[gcu.x_in(installs(D))], page_rows=gu.UNI_PAGE_ROWS)
    f = gcu._flags(ga, rows) | (gcu.F_OTHER if gcu._other(rows) else 0)
    rec = parse(rows, D, f, now_iso, cc=POOL_CC)
    if rec["st"] not in BAD:
        rec["st"] = POOL
    if f6 is not None:
        rec["f6"] = f6
    return rec


# ── the store ──────────────────────────────────────────────────────────────────────────────────────────────────────
def app_dir(data_dir, key_or_app_id):
    k = str(key_or_app_id)
    return os.path.join(data_dir, DIR, k if _is_key(k) else gu.file_key(k))


def _is_key(s):
    return len(s) == 12 and all(ch in "0123456789abcdef" for ch in s)


def month_path(data_dir, app_id, k):
    return os.path.join(app_dir(data_dir, app_id), k + ".json.gz")


def head_path(data_dir, app_id):
    return os.path.join(app_dir(data_dir, app_id), HEAD)


def _ok(s, stream_id):
    return (isinstance(s, dict) and s.get("v") == V and s.get("ages") == list(AGES)
            and (stream_id is None or str(s.get("stream_id") or "") == str(stream_id or "")))


def _month_ok(s, stream_id):
    return _ok(s, stream_id) and isinstance(s.get("days"), dict)


def _head_ok(h, stream_id):
    return (_ok(h, stream_id) and isinstance(h.get("hot"), dict) and isinstance(h.get("retry"), dict)
            and isinstance(h.get("redo"), list))


def _days(a, b):
    out = []
    while a <= b:
        out.append(a)
        a += timedelta(days=1)
    return out


class Store:
    """One app's store in a run: the head, the month files loaded on first use (at most two held while walking), the
    months a fold touched (only those are written), counts for the log line. data_dir None: in memory only."""

    def __init__(self, data_dir, app_id, stream_id):
        self.data_dir, self.app_id, self.stream_id = data_dir, app_id, str(stream_id or "")
        h = gu.load_store(head_path(data_dir, app_id)) if data_dir else None
        self.fresh = not _head_ok(h, self.stream_id)    # none, or another version / ages / stream: start over
        if self.fresh:
            h = {"v": V, "stream_id": self.stream_id, "ages": list(AGES), "hot": {}, "retry": {}, "redo": []}
        self.head = h
        self.disk = None if self.fresh else json.loads(json.dumps(h))     # the head as it is on disk
        self.m, self.touched, self.bad = {}, set(), set()
        self.folded = self.hot = self.flagged = self.sampled = self.no_cell = self.reread = self.held = self.low = 0
        self.pooled = 0
        self.dirty = False

    def month(self, k):
        """Month k's file (loaded once). Missing: empty. On disk but unreadable or of another version / ages / stream
        (a head of this one was kept): empty too, and every day of it the walk had folded goes to "redo"."""
        if k not in self.m:
            s = None
            if self.data_dir:
                p = month_path(self.data_dir, self.app_id, k)
                if os.path.exists(p) or os.path.exists(p[:-3]):
                    s = gu.load_store(p)
                    if not _month_ok(s, self.stream_id):
                        s = None
                        self._bad(k)
                elif self._held(k):                 # the walk folded days there and the file is gone: read again
                    self._bad(k)
            self.m[k] = s if s is not None else {"v": V, "stream_id": self.stream_id, "ages": list(AGES), "days": {}}
        return self.m[k]

    def check_months(self, today):
        """Once a property day: every month the walk folded (oldest … upto) is on disk and readable — a missing or
        damaged one has its days read again (redo), never dropped in silence."""
        h = self.head
        if self.fresh or not self.data_dir or not (h.get("oldest") and h.get("upto")) or h.get("chk") == today.isoformat():
            return
        k, last = h["oldest"][:7], h["upto"][:7]
        while k <= last:
            if k not in self.m and k not in self.bad:
                s = gu.load_store(month_path(self.data_dir, self.app_id, k))     # read and let go, never held
                if not _month_ok(s, self.stream_id):
                    self._bad(k)
                del s
            k = (date.fromisoformat(k + "-01") + timedelta(days=32)).strftime("%Y-%m")
        h["chk"] = today.isoformat()
        self.dirty = True

    def _held(self, k):
        """Did the walk fold days of month k (oldest … upto)?"""
        h = self.head
        return bool(h.get("oldest") and h.get("upto")) and h["oldest"][:7] <= k <= h["upto"][:7]

    def _bad(self, k):
        if self.fresh or k in self.bad:
            return
        self.bad.add(k)
        h = self.head
        if not (h.get("oldest") and h.get("upto")):
            return
        m0 = date.fromisoformat(k + "-01")
        a = max(gu._d(h["oldest"]), m0)
        b = min(gu._d(h["upto"]), (m0 + timedelta(days=32)).replace(day=1) - timedelta(days=1))
        add = [D.isoformat() for D in _days(a, b)]
        if not add:
            return
        h["redo"] = sorted(set(h.get("redo") or []) | set(add))
        self.reread += len(add)
        self.dirty = True
        if self.data_dir and self.disk is not None:     # durable BEFORE the damaged month can be written over (the
            self.disk["redo"] = sorted(set(self.disk.get("redo") or []) | set(add))     # head as on disk + redo:
            p = head_path(self.data_dir, self.app_id)   # never ahead of the months)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            write_json_gz_stable(p, self.disk)

    def fold(self, D, rec, now_iso):
        """A FINAL day's record into its month (a day read again: replaced). A sampled / cut answer is kept (with no
        cells) and queued for RETRY more reads; its last read again leaves it as it is."""
        k = D.isoformat()
        mo = self.month(k[:7])
        rt = self.head["retry"]
        if k in rt:                                 # a read again
            n = int(rt[k][0]) + 1
            rec["rt"] = n
            if rec["st"] not in BAD or n >= RETRY:
                rt.pop(k)
            else:
                rt[k] = [n, now_iso]
        elif rec["st"] in BAD:
            rt[k] = [0, now_iso]
        mo["days"][k] = rec
        self.touched.add(k[:7])
        self.head["redo"] = [x for x in self.head.get("redo") or [] if x != k]
        for f in ("hot", "pk", "low", "mid"):
            (self.head.get(f) or {}).pop(k, None)
        if self.head.get("mid") == {}:
            self.head.pop("mid")
        self.folded += 1
        self.count(rec)

    def count(self, rec):
        st = rec.get("st")
        self.flagged += st in ("oth", "thr")
        self.sampled += st in BAD
        self.low += st == LOW
        self.pooled += st == POOL
        self.no_cell += int(rec.get("xn") or 0)

    def save(self, keep=None):
        """The touched months written (and every month let go but `keep`)."""
        for k in sorted(self.m):
            if k == keep:
                continue
            if k in self.touched and self.data_dir:
                p = month_path(self.data_dir, self.app_id, k)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                write_json_gz_stable(p, self.m[k])
            self.touched.discard(k)
            self.m.pop(k)

    def save_head(self):
        if self.data_dir:
            p = head_path(self.data_dir, self.app_id)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            write_json_gz_stable(p, self.head)
            self.disk = json.loads(json.dumps(self.head))

    def left(self, hs, edge):
        """FINAL activity days still to read: a walk not started yet, every one of hs … edge; else the forward gap
        (upto + 1 … edge, a held day included) and the backfill's days down to the history start; plus redo."""
        h = self.head
        n = len(h.get("redo") or [])
        if not hs or edge < hs:
            return n
        if not (h.get("upto") and h.get("oldest")):
            return n + (edge - hs).days + 1
        n += max(0, (edge - max(gu._d(h["upto"]), hs - timedelta(days=1))).days)
        n += max(0, (gu._d(h["oldest"]) - hs).days)
        return n


def step_app(ga, st, today, hs, now, part=None):
    """One app's run on its store → "fetched" (something read) or "fresh" (nothing due). part "new": steps 1–5 (the
    newest days: every app gets them first), "fill": the backfill (with the time left), None: both. Raises Stop
    (gf.Stop): every day read is in the store's months (the caller writes them, then the head)."""
    edge = today - timedelta(days=FINAL_LAG)
    did = False
    if part != "fill":
        did = _new(ga, st, today, hs, now, edge) or did
    if part != "new":
        did = _fill(ga, st, hs, edge, gu._now_iso(now), now) or did
    return "fetched" if did else "fresh"


def _new(ga, st, today, hs, now, edge):
    h, now_iso, did = st.head, gu._now_iso(now), False
    one = timedelta(days=1)
    hot, pk = h["hot"], h.setdefault("pk", {})
    up0 = h.get("upto")
    for m in (hot, pk, h.get("low") or {}, h.get("mid") or {}):     # 1. folded (or before the history): a hot copy
        for k in [k for k in m if (up0 and k <= up0) or k < hs.isoformat()]:   # never stands in
            m.pop(k)
            st.dirty = True
    if h.get("mid") == {}:
        h.pop("mid")
        st.dirty = True
    if h.get("hs") != hs.isoformat():
        if h.get("hs") and hs < gu._d(h["hs"]):     # the history start moved back: the backfill goes on
            h.pop("done", None)
        h["hs"] = hs.isoformat()
        st.dirty = True
    st.check_months(today)
    fresh = set()                                   # days read this run (the hot step leaves them alone)
    if edge >= hs:
        D = max(hs, gu._d(h["upto"]) + one) if h.get("upto") else edge     # 2. forward, oldest first
        tried = False                               # (the run's first final day always asks the country read: an
        while D <= edge:                            # app whose country split GA4 stops sampling goes back to it)
            k = D.isoformat()
            rec = read_day(ga, D, now_iso, pool=bool(h.get("pool")) and tried)
            if not tried and rec["st"] not in BAD:
                h["pool"] = rec["st"] == POOL
                st.dirty = True
            tried = True
            did = True
            if _collapsed(h, D, rec):               # GA4 answered a day it had filled with far less: held, its fuller
                if (today - D).days < FINAL_LAG + LOW_WAIT:     # hot copy stays, read again next run …
                    h.setdefault("low", {}).setdefault(k, now_iso)
                    st.held += 1
                    st.dirty = True
                    fresh.add(k)
                    break
                rec["st"] = LOW                     # … GA4 kept it so: folded as it is, marked (never blocks the walk)
            st.save(keep=k[:7])
            st.fold(D, rec, now_iso)
            h["upto"] = k
            if not h.get("oldest"):
                h["oldest"] = k
            D += one
    up = gu._d(h["upto"]) if h.get("upto") else edge
    a = max(hs, up + one)                           # 3. hot: every day not folded yet, read again, never folded
    due = gu._hours_since(h.get("hot_at"), now) >= REFRESH_HOURS or h.get("hot_today") != today.isoformat()
    if a <= today and due:
        for D in _days(a, today):
            k = D.isoformat()
            if k in fresh:
                continue
            mid = HOT_DAYS <= (today - D).days < FINAL_LAG      # older than HOT_DAYS, not final yet: once a UTC day
            if mid and max(str((h.get("mid") or {}).get(k) or ""), str((hot.get(k) or {}).get("at") or ""))[:10] \
                    >= now_iso[:10]:                            # (its last read: "mid", or the copy a whole answer
                continue                                        # left) — read already on this UTC day
            rec = read_day(ga, D, now_iso, pool=bool(h.get("pool")))
            if mid:
                h.setdefault("mid", {})[k] = now_iso
            st.hot += 1
            did = True
            if _collapsed(h, D, rec):               # GA4 emptied a day it is filling: the fuller copy stays
                st.held += 1
            else:
                hot[k] = rec
            _peak(h, D, rec)
        h["hot_at"], h["hot_today"] = now_iso, today.isoformat()
    return did


def _fill(ga, st, hs, edge, now_iso, now=None):
    """The history (the second round, with the time left): 5. the days of a month file that could not be read, 4.
    sampled / cut days again, 6. the backfill, newest first (a day its month already holds whole is not asked again:
    a head lost or behind its months never costs the history twice)."""
    h, did = st.head, False
    one = timedelta(days=1)
    did = _redo(ga, st, hs, edge, now_iso) or did
    for k in sorted(h["retry"], reverse=True):      # sampled / cut days again, newest first
        if (now is not None and gu._hours_since(h["retry"][k][1], now) < RETRY_GAP_HOURS) \
                or not hs.isoformat() <= k <= edge.isoformat():
            continue
        D = gu._d(k)
        st.save(keep=k[:7])
        st.fold(D, read_day(ga, D, now_iso, pool=bool(h.get("bpool"))), now_iso)
        did = True
    while h.get("oldest") and not h.get("done"):
        top = gu._d(h["oldest"]) - one
        if top < hs:
            h["done"] = True
            st.dirty = True
            break
        k = top.isoformat()
        st.save(keep=k[:7])
        old = st.month(k[:7])["days"].get(k)
        if not (isinstance(old, dict) and old.get("st") not in BAD + (LOW,) and k not in (h.get("redo") or [])):
            ask = not h.get("bpool") or int(h.get("bcount") or 0) >= POOL_CHECK - 1     # the country read?
            rec = read_day(ga, top, now_iso, pool=not ask)
            if ask:
                if rec["st"] == POOL:
                    h["bstreak"] = int(h.get("bstreak") or 0) + 1
                elif rec["st"] not in BAD:
                    h["bstreak"] = 0
                h["bpool"], h["bcount"] = int(h.get("bstreak") or 0) >= POOL_RUN, 0
            else:
                h["bcount"] = int(h.get("bcount") or 0) + 1
            st.fold(top, rec, now_iso)
            did = True
        h["oldest"] = k
        st.dirty = True
    return _redo(ga, st, hs, edge, now_iso) or did  # (a month the backfill found it could not read: this run too)


def _day_events(rec):
    """A record's ad events (every cell, every age, and the rows in no cell)."""
    return sum(sum(arr[1::2]) for arr in (rec.get("c") or {}).values()) + int(rec.get("xi") or 0)


def _peak(h, D, rec):
    """The most ad events a day not folded yet has shown in any read (GA4's numbers of a day only grow while it fills)."""
    if rec.get("st") in BAD:
        return
    pk, k = h.setdefault("pk", {}), D.isoformat()
    pk[k] = max(int(pk.get(k) or 0), _day_events(rec))


def _collapsed(h, D, rec):
    """Did GA4 answer a day it had already filled with far less — its ad events under COLLAPSE × the most this day
    showed in an earlier read? Judged on the day's OWN reads, never against other days: a real drop in traffic is low
    in every read of the day and folds as it is. A day never read before (no peak, as after an outage), one whose
    earlier reads were small (< TOT_MIN events) and a sampled / cut answer (the retries') never are."""
    if rec.get("st") in BAD:
        return False
    p = int((h.get("pk") or {}).get(D.isoformat()) or 0)
    return p >= TOT_MIN and _day_events(rec) < COLLAPSE * p


def _redo(ga, st, hs, edge, now_iso):
    """Read again every day of "redo" (newest first) → True when one was read."""
    h, did = st.head, False
    for k in sorted(h.get("redo") or [], reverse=True):
        if not hs.isoformat() <= k <= edge.isoformat():
            h["redo"] = [x for x in h["redo"] if x != k]
            st.dirty = True
            continue
        st.save(keep=k[:7])
        st.fold(gu._d(k), read_day(ga, gu._d(k), now_iso, pool=bool(st.head.get("bpool"))), now_iso)
        did = True
    return did


# ── the run ────────────────────────────────────────────────────────────────────────────────────────────────────────
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


def pick_budget(budget, stores):
    """The run's seconds: the caller's; else FILL_SEC while any app's history is still being read (a new store, the
    backfill not done, days to read again), BUDGET_SEC after."""
    if budget:
        return budget
    return FILL_SEC if any(s.fresh or not s.head.get("done") or s.head.get("redo") for s in stores) else BUDGET_SEC


def _turn(t, f="turn"):
    """An app's place in a round's line: one the budget cut (or never reached) first, then the one that waited longest
    — for the newest days its last run ("turn"), for the history its last fill ("fturn")."""
    return (not t[1].get("deferred"), t[1].get(f) or "", t[0]["app_id"])


def _fill_due(h, hs, now):
    """Has an app's history anything to read: the backfill not done, days to read again (redo) or a retry due?"""
    if h.get("redo") or (h.get("oldest") and not h.get("done") and h["oldest"] > hs.isoformat()):
        return True
    return any(gu._hours_since(v[1], now) >= RETRY_GAP_HOURS for v in (h.get("retry") or {}).values())


def _worst(a, b):
    """Two rounds' answers of one app → the run's."""
    for v in ("failed", "deferred", "fetched"):
        if v in (a, b):
            return v
    return b or a


def refresh_all(cfg, data_dir, apps, now=None, clock=None, budget=None, workers=WORKERS):
    """Every selected app (uninstall_build's list) → {"counts", "apps": {app id: fetched|fresh|failed|deferred|
    waiting}}. Two rounds over the properties (each property one call at a time, WORKERS side by side, the one whose
    app waited longest first): every app's newest days first ("new"), then the history with the time left ("fill") —
    a history fill never holds back another app's newest days. budget: seconds (None / 0: FILL_SEC while any app's
    history is being read, else BUDGET_SEC). Never raises; never prints."""
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
            by_prop.setdefault(r["property_id"], []).append(
                (a, st, r, gu._d(um["history_start"]), Store(data_dir, aid, r["stream_id"])))
        budget = pick_budget(budget, [s for xs in by_prop.values() for *_, s in xs])

        def over():
            return "budget" if clock() - t0 >= budget else None
        line = {}                                   # each round's line: its apps per property, the properties
        for part, f in (("new", "turn"), ("fill", "fturn")):     # by their longest waiting app
            per = {pid: sorted(xs, key=lambda t: _turn(t, f)) for pid, xs in by_prop.items()}
            line[part] = (per, sorted(per, key=lambda p: (min(_turn(t, f)[:2] for t in per[p]), p)))
        props = {pid: {"quota": None, "stop": None} for pid in by_prop}
        gas, res, ran, fran, fail, ok1 = {}, {}, set(), set(), {}, set()

        def one_prop(pid, part):
            prop = props[pid]
            for a, st, r, hs, store in line[part][0][pid]:
                aid = a["app_id"]
                if res.get(aid) in ("failed", "deferred"):
                    continue                        # (its first round ended it)
                if part == "fill" and not _fill_due(store.head, hs, now):
                    continue                        # (nothing of its history left: its first round's answer stands)
                if over() or prop["stop"]:
                    res[aid] = "deferred"
                    continue
                tok = access.get(r.get("owner"))
                if not tok:
                    res[aid], fail[aid] = "failed", "auth"
                    continue
                tz = ust["tz"].get(pid) or "UTC"
                today = now.astimezone(ZoneInfo(tz)).date()
                ga = gas.get(aid)
                if ga is None:                      # one App an app a run: its call cap spans both rounds
                    ga = gas[aid] = gf.App(tok, pid, r["stream_id"], prop, over=over, max_calls=MAX_CALLS)
                ran.add(aid)
                if part == "fill":
                    fran.add(aid)
                try:
                    got = step_app(ga, store, today, hs, now, part)
                except gf.Stop:
                    got = "deferred"
                except Exception as e:
                    got, fail[aid] = "failed", gu._fail_kind(e)
                try:                                # the months first: the head never runs ahead of them
                    store.save()
                    store.head.update(v=V, app_id=aid, package=a["package"], property_id=pid,
                                      stream_id=str(r["stream_id"]), time_zone=tz, ages=list(AGES))
                    if ga.calls or store.folded or store.dirty or store.fresh:
                        store.save_head()
                        store.dirty = False
                except Exception as e:
                    got, fail[aid] = "failed", gu._fail_kind(e)
                if part == "new" and got in ("fetched", "fresh"):
                    ok1.add(aid)                    # (its newest days read: a failure streak ends here)
                res[aid] = _worst(res.get(aid), got)

        for part in ("new", "fill"):                # (each property in one thread a round: one call at a time)
            with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
                list(ex.map(lambda p: one_prop(p, part), line[part][1]))
        for pid, xs in by_prop.items():
            edge = now.astimezone(ZoneInfo(ust["tz"].get(pid) or "UTC")).date() - timedelta(days=FINAL_LAG)
            for a, st, r, hs, store in xs:
                aid = a["app_id"]
                v = res.get(aid) or "deferred"
                if v == "failed":
                    st.update(last_try=now_iso, fail=fail.get(aid) or "other", fails=int(st.get("fails") or 0) + 1)
                    if aid in ran:
                        st["turn"] = now_iso
                elif v == "deferred":
                    st["deferred"] = True           # (never reached: its old turn stays, so it goes first next run)
                    if aid in ran:
                        st["turn"] = now_iso
                    if aid in ok1:                  # (its newest days were read whole: no failure streak)
                        st.update(last_try=now_iso, fail=None, fails=None)
                else:
                    st.update(last_try=now_iso, fail=None, fails=None, turn=now_iso, deferred=None)
                    if v == "fetched":
                        st["last_ok"] = now_iso
                for f in ("deferred", "fail", "fails"):
                    if not st.get(f):
                        st.pop(f, None)
                if aid in fran:
                    st["fturn"] = now_iso
                st["key"] = gu.file_key(aid)
                out["apps"][aid] = v
                ga = gas.get(aid)
                if ga is not None:
                    counts["calls"] += ga.calls
                    counts["tokens"] += ga.tok
                for c, n in (("days", store.folded), ("hot", store.hot), ("flagged", store.flagged),
                             ("sampled", store.sampled), ("pooled", store.pooled), ("held", store.held),
                             ("low", store.low),
                             ("no_cell", store.no_cell), ("reread", store.reread)):
                    counts[c] += n
                counts["left"] += store.left(hs, edge)
                counts["stuck"] += v == "failed" and int(st.get("fails") or 0) >= FAIL_LINE
        for aid, v in out["apps"].items():          # (an app the RETRY_HOURS gate held back is still stuck)
            if v == "failed" and aid not in res and int((state["fetch"].get(aid) or {}).get("fails") or 0) >= FAIL_LINE:
                counts["stuck"] += 1
        save_state(data_dir, state)
    except Exception as e:                          # a bug here must never cost the build
        out["error"] = type(e).__name__
    for v in out["apps"].values():
        if v in counts:
            counts[v] += 1
    return out


def log_line(status):
    """The build log's ONE line for this step — counts only."""
    c = (status or {}).get("counts") or {}
    return ("ga4 cohort ecpm: apps %d, with GA4 %d, fetched %d, fresh %d, failed %d, deferred %d, waiting %d, "
            "days folded %d, hot days %d, flagged %d, sampled %d, pooled %d, held back %d, folded low %d, "
            "rows in no cell %d, "
            "read again %d, days left %d, stuck %d, calls %d, tokens %d%s" % tuple([gaud._int(c.get(k)) for k in COUNTS]
                                            + [(", error " + status["error"]) if (status or {}).get("error") else ""]))


# ── the build's read ───────────────────────────────────────────────────────────────────────────────────────────────
def load_cells(data_dir, key, stream_id=None, want=None):
    """One app's store, read-only → {"cells": {(cc, X): [r0, i0, …, r13, i13]}, "days": {D: (state, hot)}, "hs",
    "upto", "oldest", "done"} or None (no head of this version / ages (/ stream when given)). want: the install days X
    kept (None: every one). A folded day wins over a hot copy; a hot copy stands only for a day not folded."""
    h = gu.load_store(head_path(data_dir, key))
    if not _head_ok(h, stream_id):
        return None
    sid = str(h.get("stream_id") or "")
    w, cells, days = 2 * len(AGES), {}, {}

    def put(D, rec, hot):
        days[D] = (rec.get("st"), hot)
        Dd = date.fromisoformat(D)
        for cc, arr in (rec.get("c") or {}).items():
            for k, a in enumerate(AGES):
                if 2 * k >= len(arr):
                    break
                r, i = arr[2 * k], (arr[2 * k + 1] if 2 * k + 1 < len(arr) else 0)
                if not (r or i):
                    continue
                X = (Dd - timedelta(days=a)).isoformat()
                if want is not None and X not in want:
                    continue
                c = cells.setdefault((cc, X), [0] * w)
                c[2 * k], c[2 * k + 1] = r, i
    folder = app_dir(data_dir, key)
    try:
        names = sorted(f for f in os.listdir(folder)
                       if len(f) == 15 and f.endswith(".json.gz") and f[4] == "-" and f[:4].isdigit())
    except OSError:
        names = []
    for f in names:
        mo = gu.load_store(os.path.join(folder, f))
        if not _month_ok(mo, sid):
            continue
        for D, rec in sorted(mo["days"].items()):
            if isinstance(rec, dict):
                put(D, rec, False)
        del mo
    for D, rec in sorted((h.get("hot") or {}).items()):
        if D not in days and isinstance(rec, dict):
            put(D, rec, True)
    return {"cells": cells, "days": days, "hs": h.get("hs"), "upto": h.get("upto"), "oldest": h.get("oldest"),
            "done": bool(h.get("done")), "time_zone": h.get("time_zone")}
