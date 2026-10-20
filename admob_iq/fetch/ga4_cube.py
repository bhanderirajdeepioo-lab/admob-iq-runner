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
(report_all with gu.UNI_PAGE_ROWS: never cut), no firstSessionDate filter:
    dimensions [date, firstSessionDate, countryId], metrics [activeUsers, totalAdRevenue]
adaptive, per range of activity days:
  1. a block of BLOCK (30) days in one call; when any row has "(other)" (or a date that is not one), the answer was cut
     (truncated) or any page's metadata says dataLossFromOtherRow or sampling, the block's answer is dropped and
  2. each day of it is read alone; when a day still has "(other)" (or the same flags),
  3. that day is split by countries: the biggest ~1/SPLIT countries of its answer (the most rows — the cardinality GA4
     folds into "(other)" — then revenue) in one call (countryId inList), every other country in another (notExpression
     of the same list); what is STILL "(other)" after that is the day's measured loss: kept as such, never spread.
  A range at least as long as one that needed step 2 goes to step 2 straight away for HEAVY_KEEP activity days ("heavy":
  its block call would only be dropped again); then the block is tried once more.
Per row: countryId "(not set)" / empty → cc "--"; a firstSessionDate that is not a date ("(other)", "(not set)"), a
countryId "(other)" or an install day after the activity day → the day's loss (micros; st "loss" only then). GA4's
thresholding, sampling, a cut answer, or a flag still on the final answer with no "(other)" row to measure it by → the
day's "fl" (st stays ok / split: a flag is not a measured loss; the page marks ≈ with no direction; nothing guessed).

Stored in the private repo, data/ga4_cube/<key>/ — by ACTIVITY month; a month file never changes once its days are all
folded (a folded day is never read or folded again):
    <YYYY-MM>.json.gz = {"v", "stream_id",
      "days": {D: {"st": ok|split|loss, "rows", "loss", "t", "fl", "via": block|day|split, "at"}}     the ledger
      "b": {X: {j: {W: micros}}}          ALL countries summed, ages L ≥ 31 in 30-day buckets j = (L − 31) // 30 + 1
                                          (bucket j = ages 30j+1 … 30j+30: the step into D(30 + 30j)); W = the Monday of
                                          the activity day (engine.value._mon: the week of the AdMob ÷ GA4 scale k)
      "c": {cc: {X: {j: micros}}}         per country, the same buckets, summed over this activity month
      "e": {cc: {X: [u0, r0, r1 … r30]}}  per country, ages 0 … 30 day by day (u0 = activeUsers at age 0 = the
                                          country's installs; r in micros; trailing zeros trimmed)
      "t": {D: micros}                    every row of the day (the loss share's denominator)
      "loss": {D: micros}}                what stayed "(other)" / had no install day (days with some only)
    hot.json.gz = {"v", "app_id", "package", "property_id", "stream_id", "time_zone", "hs", "from", "next", "done",
      "walk_at", "hot_at", "hot_today", "heavy", "d": {D: {the ledger's fields + "b", "c", "e" of that one day}}}
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

Cost: the backfill ≈ app age / 30 block calls on a light app (rows a call ≈ 30 × a day's (install day, country) rows),
and on a heavy one about one call per activity day (+ 2 for a day that still needs the country split, + one block try
every HEAVY_KEEP days) — measured on the biggest app ≈ 70 GA4 tokens and 4–6 s a day call, so ≈ 25 days a run in the
150 s budget (the backfill goes on next run). After it, a day: the new final day (1 call) + the hot window (1 call, 3 on
a heavy app) every 6 hours and at the property's midnight.
"""
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
SPLIT = 8                           # a day still "(other)": its biggest ~1/8 countries, then the rest
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
LEDGER = ("st", "rows", "loss", "t", "fl", "via", "at")
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
def body(a, b):
    """Activity days a … b: every install day and country (no firstSessionDate filter)."""
    return {"dateRanges": [{"startDate": a.isoformat(), "endDate": b.isoformat()}],
            "dimensions": ga4._dim(*DIMS), "metrics": ga4._dim(*METS), "currencyCode": "USD", "keepEmptyRows": False}


def cc_in(ccs):
    return ga4._in_list("countryId", sorted(ccs))


def cc_not(ccs):
    return {"notExpression": cc_in(ccs)}


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
    return {"b": {}, "c": {}, "e": {}, "t": 0, "loss": 0, "rows": 0, "oth": 0}


def _add(acc, Dd, W, X, Xd, r):
    """One row of activity day Dd (W: its Monday) into the day's accumulator; X / Xd: its install day (None: not a
    date)."""
    v = int(round(float(r.get("totalAdRevenue") or 0) * 1e6))
    acc["rows"] += 1
    acc["t"] += v
    cc = _cc(r)
    if OTHER in (r.get("firstSessionDate"), r.get("countryId")):
        acc["oth"] += 1
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


def _rec(acc, via, fl, now_iso):
    """A day's accumulator → its record: the ledger's fields + "b", "c", "e"."""
    acc = acc or _new()
    flag = bool(fl & (F_SMP | F_CUT | F_THR)) or bool(fl & F_OTHER and not acc["oth"])
    e = {}
    for cc, xs in acc["e"].items():
        for X, arr in xs.items():
            a = _trim(arr)
            if a:
                e.setdefault(cc, {})[X] = a
    st = "loss" if acc["loss"] else ("split" if via == "split" else "ok")      # flagged only: "fl", never "loss"
    return {"st": st, "rows": acc["rows"], "loss": acc["loss"], "t": acc["t"], "fl": 1 if flag else 0, "via": via,
            "at": now_iso, "b": acc["b"], "c": acc["c"], "e": e}


def _top(rows):
    """The biggest ~1/SPLIT of the named countries of a day's answer (most rows, then revenue, then code)."""
    n, v = {}, {}
    for r in rows:
        cc = _cc(r)
        if cc in (NO_CC, OTHER):
            continue
        n[cc] = n.get(cc, 0) + 1
        v[cc] = v.get(cc, 0.0) + float(r.get("totalAdRevenue") or 0)
    order = sorted(n, key=lambda k: (-n[k], -v[k], k))
    return order[:-(-len(order) // SPLIT)]                  # ⌈n / SPLIT⌉ (≥ 1 when any country is named)


def read_day(ga, D, now_iso):
    """One activity day alone (steps 2 and 3 of the module doc) → its record. Raises Stop (nothing of the day kept)."""
    rows = ga.report_all(body(D, D), page_rows=gu.UNI_PAGE_ROWS)
    fl, via = _flags(ga, rows), "day"
    if _other(rows) or fl & RETRY:
        top = _top(rows)
        if top:
            ra = ga.report_all(body(D, D), extra=[cc_in(top)], page_rows=gu.UNI_PAGE_ROWS)
            fa = _flags(ga, ra)
            rb = ga.report_all(body(D, D), extra=[cc_not(top)], page_rows=gu.UNI_PAGE_ROWS)
            rows, fl, via = ra + rb, fa | _flags(ga, rb), "split"
    return _rec(_group(rows, D).get(D.isoformat()), via, fl, now_iso)


def _skip_block(head, a, n):
    hv = head.get("heavy")
    try:
        return bool(hv) and n >= int(hv["n"]) and 0 <= (a - _d(hv["at"])).days < HEAVY_KEEP
    except (KeyError, TypeError, ValueError):
        return False


def read_range(ga, a, b, head, now_iso):
    """Activity days a … b → (D, record) in day order, adaptive (see the module doc). A generator: a Stop between its
    calls keeps every day it yielded."""
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
        yield D, read_day(ga, D, now_iso)


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
        self.pruned = False

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
        self.touched.add(k[:7])
        self.head.setdefault("d", {}).pop(k, None)
        self.folded += 1
        self.split += rec.get("via") == "split"
        self.loss += bool(rec.get("loss"))          # measured: revenue GA4 left "(other)" / with no install day
        self.flagged += bool(rec.get("fl"))         # GA4's flag with nothing to measure it by (the page's ≈)
        return True

    def save(self, before=None):
        """The touched months (before: only those older than that month — written and let go: the walk moved on).
        In memory only (no data_dir): nothing to write, every month kept."""
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

    def save_head(self):
        if self.data_dir:
            write_json_gz_stable(hot_path(self.data_dir, self.app_id), self.head)


def step_app(ga, cube, today, hs, now):
    """One app's run on its cube → "fetched" or "fresh". Raises Stop (what was folded is kept, the cursor where it
    stopped; the caller saves the months, then the head)."""
    h, now_iso, did = cube.head, gu._now_iso(now), False
    edge = today - timedelta(days=FINAL_LAG)
    d = h.setdefault("d", {})
    for k in [k for k in d if k <= edge.isoformat()]:      # final now: a copy read while it was filling never counts
        d.pop(k)                                            # (a hole until the walk folds it — even when the walk stops
        cube.pruned = True                                  # before it)
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
        for D, rec in read_range(ga, a, today, h, now_iso):
            d[D.isoformat()] = rec                          # replaced (never folded: read while not final)
            did = True
        h["hot_at"], h["hot_today"] = now_iso, today.isoformat()
    return "fetched" if did else "fresh"


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


COUNTS = ("selected", "with_ga4", "fetched", "fresh", "failed", "deferred", "waiting", "days", "split", "loss",
          "flagged", "reread", "calls", "tokens")


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
                    if ga.calls or cube.folded or cube.pruned:
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
            "split %d, loss %d, flagged %d, months read again %d, calls %d, tokens %d%s"
            % tuple([gaud._int(c.get(k)) for k in COUNTS]
                    + [(", error " + status["error"]) if (status or {}).get("error") else ""]))
