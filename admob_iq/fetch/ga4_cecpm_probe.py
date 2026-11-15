"""One-off GA4 RETURNING-SESSION eCPM probe, run by .github/workflows/ga4-cecpm-probe.yml: before the fetch for the
per-cohort-day eCPM index is built (design: spec_returning_ecpm.md §5.1), measure per app whether GA4 answers the
production read of that fetch WHOLE — date × firstSessionDate × countryId with totalAdRevenue + eventCount under
eventName == ad_impression and a firstSessionDate in-list of the install days D, D−1, D−2, D−3, D−6, D−13 — and decide
per app, from real answers, go or no-go. Read-only against GA4 and against the PRIVATE repo's data (the Uninstall
state's routes and the cohort cube's month files); the only write is ga4/cecpm_probe.json in the PRIVATE repo.

Days: per app up to four activity days F = today − 5 (the fetch's edge), F − 30, F − 100 and F − 480 (≈ 16 months
back: does an event-filtered read still answer whole past 14 months? Not before the app's history start + 13: that day
is used instead when F − 480 is older). On each day D (one-day range [D, D], USD):
  E6   date × firstSessionDate × countryId     totalAdRevenue, eventCount   eventName == ad_impression, firstSessionDate
                                                                            in-list = the six install days (AGES)
  E14  the same, in-list = the fourteen install days D … D − 13          (what a wider AGES would cost)
  EF   the same as E6 without the in-list                                 (does the in-list change a named row?)
  ET   date × firstSessionDate (no country)    totalAdRevenue, eventCount   E6's filter and in-list (the day's truth)
  P6   the same as E6 without the event filter  publisherAdImpressions, totalAdRevenue  (the metric the design rejects)
A record per read: accepted or the HTTP class / status (never the text), rows, "(other)" / "(not set)" shares, GA4's
flags (dataLossFromOtherRow, sampling, thresholding), the answer's rowCount vs the rows kept ("cut"), the quota tokens
the response reported and the seconds.

Cells and comparisons (a cell = country × install day × age; money in micros):
  EF vs E6    overlap = Σ min ÷ Σ max over the union of cells, for revenue and for events, + cells that differ
  E14 vs E6   the same on E6's ages
  coverage    per install day: Σ countries of E6 ÷ ET (revenue and events; "(other)" countries are not named rows)
  P6 vs E6    publisherAdImpressions vs eventCount per cell (overlap, Σ ratio, cells within 2 %) and revenue
  E6 vs cube  E6 revenue vs the cube's "e" cells (data/ga4_cube/<key>/<YYYY-MM>.json.gz of the activity month; the
              private clone, read-only): overlap and Σ ratio. A day the cube has not folded is "no cube day".
  day-1 base  (informational, never in the verdict) the owner, 15 Nov 2026: the index's day 1 = the FIRST SESSION's
              eCPM. Its revenue and impressions by country come from the private clone's ga4_nvr store ("n" rows of
              the install day, the same base the Breakeven benchmark already uses). Measured: the share of E6's
              returning revenue (ages ≥ 1, named countries) whose install day × country has a first-session base, and
              the first session's share of the install day's own revenue and impressions (E6 age 0).

Go / no-go per app (GO only when every day asked was read; every check a True / False / None — None = nothing to judge
it by, e.g. the read was not made, was refused for a diagnostic read, or the run stopped):
  e6_whole    every E6 accepted and not cut (a refused E6 = False)
  unsampled   no E6 answer sampled
  ef_equal    EF = E6 on the named cells: revenue and events overlap ≥ EF_EQUAL_MIN on every day
  coverage    on days whose E6 carries no flag (no dataLossFromOtherRow, sampling, "(other)" row or cut), every install
              day Σ countries ÷ ET ≥ COVERAGE_MIN for revenue and events
  cube_tie    E6 revenue ties the cube's cells for ≥ CUBE_TIE_MIN of the revenue (overlap, pooled over the days compared)
  verdict     "nogo" when any check is False; "go" when all are True and the app is complete; else "unknown"
If E6 is NOT whole either (the design's G2), the verdict is nogo for that app: stop and tell the owner.

LIMITS: the d1d7 probe's quota rule per PROPERTY (any token bucket under half, ≤ 4 server-error / ≤ 5 thresholded
requests left, a 429, 2 failed calls on 5xx), one request at a time per property (WORKERS properties in parallel), at
most APP_CALLS an app, MAX_CALLS GA4 calls in all (input "max_calls"), no call after BUDGET_SEC. What is read is kept
and written.

PUBLIC LOG: counts only — progress (calls, seconds, apps) and ONE result line: apps probed, reads made, accepted /
refused / failed, go / nogo / unknown. Never a name, id, date, amount or per-app number (stderr is hidden by the
workflow). The full result is in the PRIVATE repo.
"""

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from admob_iq import ga4_probe
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_audience_probe as ap
from admob_iq.fetch import ga4_country_probe as cp
from admob_iq.fetch import ga4_cube as gcu
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_device_probe as dp
from admob_iq.fetch import ga4_nvr as gv
from admob_iq.fetch import ga4_shape_probe as sp
from admob_iq.fetch import ga4_uninstall as gu
from admob_iq.fetch.ga4_d1d7_probe import Stop

AGES = (0, 1, 2, 3, 6, 13)          # the install ages of the design's read (card days 1, 2, 3, 4, 7, 14)
AGES14 = tuple(range(14))           # E14: every age 0 … 13
DAY_OFFSETS = (0, 30, 100, 480)     # F − n (the oldest ≈ 16 months back: past GA4's 14-month event-level horizon)
MIN_AGE_DAYS = 13                   # a day needs 13 install days behind it: not before the history start + 13
FINAL_LAG = 5                       # F = today − 5 (the fetch's own edge: GA4 answers the newest "final" day almost
#                                     empty for hours around D + 2 … D + 3 since 14 Nov 2026)
DIMS = ("date", "firstSessionDate", "countryId")
DIMS_T = ("date", "firstSessionDate")
IMPS = "publisherAdImpressions"
REV = "totalAdRevenue"
KINDS = ("E6", "ET", "EF", "P6", "E14")      # the order they are read in: the go/no-go's own reads first
COVERAGE_MIN = 0.98
CUBE_TIE_MIN = 0.99
EF_EQUAL_MIN = 0.999
WITHIN = 0.02                       # P6 vs E6: a cell within 2 %
MAX_CALLS = 650                     # GA4 calls in all (≈ 5 reads × 4 days × 27 apps = 540, plus pages)
APP_CALLS = 40
WORKERS = 4
BUDGET_SEC = 20 * 60
TICK_SEC = 20
DATA_DIR = "_private"
OUT_PATH = "ga4/cecpm_probe.json"
OTHER = "(other)"


class Run(cp.Run):
    """cp.Run (budget, run-wide call cap) with this probe's heartbeat words."""

    def pulse(self, count=False):
        with self.lock:
            if count:
                self.calls += 1
            now = self.clock()
            beat = now - self.beat >= pr.HEARTBEAT_SEC
            if beat:
                self.beat = now
            n, s = self.calls, int(now - self.t0)
        if beat:
            self.say("cecpm progress: calls %d, %ds" % (n, s))


# ── the request shapes ───────────────────────────────────────────────────────────────────────────

def pick_days(f, hs=None):
    """F, F − 30, F − 100, F − 400 (that one: the oldest day with 13 install days behind it when it falls before the
    history start + 13) — never before hs + 13, no duplicates, newest first."""
    lo = (hs + timedelta(days=MIN_AGE_DAYS)) if hs else None
    out = []
    for n in DAY_OFFSETS:
        d = f - timedelta(days=n)
        if lo and d < lo:
            if n != DAY_OFFSETS[-1]:
                continue
            d = lo
        if d <= f and d not in out:
            out.append(d)
    return out


def installs(d, ages):
    return [(d - timedelta(days=a)).isoformat() for a in ages]


def request(kind, d):
    """The kind's GA4 request on activity day d → {"body", "event", "extra", "dims", "mets"}."""
    ev = (REV, "eventCount")
    if kind == "E14":
        extra = [gcu.x_in(installs(d, AGES14))]
    elif kind == "EF":
        extra = []
    else:
        extra = [gcu.x_in(installs(d, AGES))]
    dims = DIMS_T if kind == "ET" else DIMS
    mets = (IMPS, REV) if kind == "P6" else ev
    return {"body": dp._body(d, d, dims, mets), "event": None if kind == "P6" else gv.EVENT, "extra": extra,
            "dims": dims, "mets": mets, "pair": (REV, IMPS if kind == "P6" else "eventCount")}


# ── cells and their comparisons ──────────────────────────────────────────────────────────────────

def micros(v):
    return int(round(float(v or 0) * 1e6))


def cells_of(rows, d, mets):
    """Rows of the one-day read of activity day d → ({(cc, X, age): [micros, count]}, rows in no cell). count = mets[1]  (mets = the (revenue, count) metric names).
    A row in no cell: not the day, an install day that is not a date, countryId "(other)", an install day after d."""
    out, rest, ds = {}, 0, d.isoformat()
    for r in rows or []:
        x = gcu._real(r.get("firstSessionDate"))
        cc = gcu._cc(r)
        if gcu._real(r.get("date")) != ds or x is None or cc == OTHER or (d - date.fromisoformat(x)).days < 0:
            rest += 1
            continue
        c = out.setdefault((cc, x, (d - date.fromisoformat(x)).days), [0, 0])
        c[0] += micros(r.get(mets[0]))
        c[1] += dp._num(r.get(mets[1]))
    return out, rest


def by_install(rows, d, mets):
    """The no-country read → {X: [micros, count]} for the day d."""
    out = {}
    for r in rows or []:
        x = gcu._real(r.get("firstSessionDate"))
        if x is None or gcu._real(r.get("date")) != d.isoformat():
            continue
        c = out.setdefault(x, [0, 0])
        c[0] += micros(r.get(mets[0]))
        c[1] += dp._num(r.get(mets[1]))
    return out


def restrict(cells, ages):
    return {k: v for k, v in cells.items() if k[2] in ages}


def overlap(a, b, i):
    """Σ min ÷ Σ max of component i over the union of the cells: 1.0 = identical, a missing cell counts as 0."""
    lo = hi = 0.0
    for k in set(a) | set(b):
        x, y = max(a.get(k, (0, 0))[i], 0), max(b.get(k, (0, 0))[i], 0)
        lo += min(x, y)
        hi += max(x, y)
    return round(lo / hi, 6) if hi else None


def same(x, y, tol=1.0):
    """Equal up to rounding: tol (a micro for money, half an event for a count) or 1 ppm."""
    return abs(x - y) <= max(tol, 1e-6 * max(abs(x), abs(y)))


def cmp_cells(a, b):
    """Two cell maps a (the reference, E6) and b → how they differ: cells, cells in both / only in one, cells whose two
    components agree, the overlap of each component and Σ b ÷ Σ a of each, cells whose count is within WITHIN."""
    both = set(a) & set(b)
    ra = sum(v[0] for v in a.values())
    ca = sum(v[1] for v in a.values())
    near = sum(1 for k in both if a[k][1] and abs(b[k][1] / a[k][1] - 1) <= WITHIN or a[k][1] == b[k][1])
    return {"a": len(a), "b": len(b), "both": len(both), "only_a": len(set(a) - set(b)), "only_b": len(set(b) - set(a)),
            "equal": sum(1 for k in both if same(a[k][0], b[k][0]) and same(a[k][1], b[k][1], 0.5)),
            "rev": overlap(a, b, 0), "cnt": overlap(a, b, 1), "rev_ratio": pr._ratio(sum(v[0] for v in b.values()), ra),
            "cnt_ratio": pr._ratio(sum(v[1] for v in b.values()), ca), "near": near}


def coverage(e6, et):
    """Per install day: Σ countries of E6 ÷ ET, for revenue and events → {X: [rev, events]} (days with ET > 0), and the
    smallest of them (None: nothing to judge)."""
    sums = {}
    for (cc, x, _), v in e6.items():
        s = sums.setdefault(x, [0, 0])
        s[0] += v[0]
        s[1] += v[1]
    out = {}
    for x, t in et.items():
        if t[0] > 0 or t[1] > 0:
            s = sums.get(x, (0, 0))
            out[x] = [pr._ratio(s[0], t[0]), pr._ratio(s[1], t[1])]
    vals = [v for pair in out.values() for v in pair if v is not None]
    return out, (min(vals) if vals else None)


def cube_clean(led):
    """Does the cube's own ledger say the day's named "e" cells are whole: no "(other)" loss ("ol"; an older ledger
    without it: a split day's loss is "(other)", ga4_cube._oloss's rule) and no GA4 flag ("fl")?"""
    if not isinstance(led, dict) or led.get("fl"):
        return False
    if led.get("ol") is None:
        return not (led.get("via") == "split" and int(led.get("loss") or 0))
    return not int(led.get("ol") or 0)


def cube_cells(data_dir, u, d, xs):
    """The cube's "e" revenue cells {(cc, X, age): [micros, 0]} of activity day d for the install days xs and the day's
    ledger, from the private clone → (cells, ledger); None when there is no clone, no month file of this stream or the
    cube has not folded the day."""
    if not data_dir:
        return None
    for aid in u.get("app_ids") or [u.get("app_id")]:
        mo = gu.load_store(gcu.month_path(data_dir, aid, d.isoformat()[:7]))
        if not gcu._month_ok(mo, u.get("stream_id")) or d.isoformat() not in mo["days"]:
            continue
        out = {}
        for cc, byx in mo["e"].items():
            for x in xs:
                arr = (byx or {}).get(x) or []
                age = (d - date.fromisoformat(x)).days
                if 0 <= age and len(arr) > age + 1 and arr[age + 1]:
                    out[(cc, x, age)] = [arr[age + 1], 0]
        return out, mo["days"][d.isoformat()]
    return None


def fs_cells(data_dir, u, xs):
    """The day-1 base: the first session's ("n") revenue micros and impressions {(cc, X): [micros, impressions]} of the
    install days xs, named countries only, from the private clone's ga4_nvr store (read-only) → (cells, the install
    days the store holds); None when there is no clone or no store of this stream."""
    if not data_dir:
        return None
    st = gv.load_store(os.path.join(data_dir, gv.DIR, u["key"] + ".json.gz"))
    if not st or (st.get("stream_id") and u.get("stream_id") and str(st["stream_id"]) != str(u["stream_id"])):
        return None
    days, out, held = st.get("days") or {}, {}, 0
    for x in xs:
        rec = days.get(x)
        if not isinstance(rec, dict):
            continue
        held += 1
        for row in rec.get("c") or []:
            if len(row) >= 4 and row[0] == "n" and isinstance(row[1], str) and len(row[1]) == 2 and row[1].isalpha():
                c = out.setdefault((row[1], x), [0, 0])
                c[0] += micros(row[2])
                c[1] += dp._num(row[3])
    return out, held


def fs_cmp(e6, fs, d):
    """E6's cells against the day-1 base (fs_cells) → the sums the pooled summary is made of: returning revenue (ages ≥
    1, named countries) and the part of it with a first-session base; the install day's own (age 0) revenue and
    impressions of the countries both hold, and the first session's."""
    base, held = fs
    named = lambda cc: len(cc) == 2 and cc.isalpha()
    ret = [(k, v) for k, v in e6.items() if k[2] >= 1 and named(k[0])]
    x0 = d.isoformat()
    zero = {k[0]: v for k, v in e6.items() if k[2] == 0 and named(k[0])}
    both = [cc for cc in zero if (base.get((cc, x0)) or (0, 0))[1] > 0]
    return {"held": held, "ret": sum(v[0] for _, v in ret),
            "ret_base": sum(v[0] for k, v in ret if (base.get((k[0], k[1])) or (0, 0))[1] > 0),
            "ret_cells": len(ret), "ret_cells_base": sum(1 for k, _ in ret if (base.get((k[0], k[1])) or (0, 0))[1] > 0),
            "day_rev": sum(zero[cc][0] for cc in both), "day_imp": sum(zero[cc][1] for cc in both),
            "fs_rev": sum(base[(cc, x0)][0] for cc in both), "fs_imp": sum(base[(cc, x0)][1] for cc in both)}


def fs_day(data_dir, u, d, e6):
    """One day's day-1 base comparison ({"store": False}: no clone / no store of this stream)."""
    fs = fs_cells(data_dir, u, installs(d, AGES))
    return {"store": False} if fs is None else fs_cmp(e6, fs, d)


def fs_pool(days):
    """The app's day-1 base summary pooled over its days (None: no store / no E6 answer to compare): base = the share
    of returning revenue with a first-session base; rev0 / imp0 = the first session's share of the install day's own
    revenue / impressions; ecpm0 = first-session eCPM ÷ the install day's whole-day eCPM."""
    got = [(dd.get("cmp") or {}).get("fs") for dd in days.values()]
    got = [g for g in got if isinstance(g, dict) and "ret" in g]
    if not got:
        return None
    s = {k: sum(g[k] for g in got) for k in ("ret", "ret_base", "ret_cells", "ret_cells_base", "day_rev", "day_imp",
                                             "fs_rev", "fs_imp")}
    e_fs = s["fs_rev"] / s["fs_imp"] if s["fs_imp"] else None
    e_day = s["day_rev"] / s["day_imp"] if s["day_imp"] else None
    return {"days": len(got), "held": sum(g["held"] for g in got), "base": pr._ratio(s["ret_base"], s["ret"]),
            "base_cells": pr._ratio(s["ret_cells_base"], s["ret_cells"]), "rev0": pr._ratio(s["fs_rev"], s["day_rev"]),
            "imp0": pr._ratio(s["fs_imp"], s["day_imp"]),
            "ecpm0": round(e_fs / e_day, 4) if e_fs is not None and e_day else None}


def flagged(rec):
    """An E6 answer with any of the flags that make coverage not required: dataLossFromOtherRow, sampling, an
    "(other)" row, a cut answer."""
    return bool(rec.get("loss") or rec.get("sampled") or rec.get("other_rows") or rec.get("cut"))


# ── the verdict ──────────────────────────────────────────────────────────────────────────────────

def _tri(vals):
    """True when all True, False when any False, None when nothing to judge (None entries are not judged)."""
    v = [x for x in vals if x is not None]
    if not v:
        return None
    return all(v)


SKIP = "skip"                       # a day with nothing to judge a check by (never counted)


def _ok(day, kind):
    return bool(((day.get("reads") or {}).get(kind) or {}).get("ok"))


def _ef_day(day):
    """One day's EF = E6: SKIP when E6 or EF was not read (EF is a diagnostic read: refused there is no evidence
    either way) or neither side holds a value; None when the comparison was not made (a bookkeeping bug); else
    whether every part that has a value overlaps ≥ EF_EQUAL_MIN (an overlap None = 0 on both sides: equal)."""
    if not (_ok(day, "E6") and _ok(day, "EF")):
        return SKIP
    e = (day.get("cmp") or {}).get("ef")
    if not isinstance(e, dict):
        return None
    v = [x for x in (e.get("rev"), e.get("cnt")) if x is not None]
    return all(x >= EF_EQUAL_MIN for x in v) if v else SKIP


def _cov_day(day):
    """One day's coverage: SKIP when E6 or ET was not read, the day's E6 carries a flag (coverage is not required
    then) or ET holds nothing; None when the comparison was not made; else min share ≥ COVERAGE_MIN."""
    if not (_ok(day, "E6") and _ok(day, "ET")):
        return SKIP
    c = day.get("cmp") or {}
    if "unflagged" not in c:
        return None
    if not c["unflagged"] or c.get("cov_min") is None:
        return SKIP
    return c["cov_min"] >= COVERAGE_MIN


def _every(vals):
    """False when any day is False; None when a day that had to be judged was not, or no day was judged; else True."""
    v = [x for x in vals if x is not SKIP]
    if any(x is False for x in v):
        return False
    return True if v and all(x is True for x in v) else None


def verdict(days, complete):
    """days: {D: {"reads": {kind: record}, "cmp": {...}}} → {"checks": {...}, "verdict": go | nogo | unknown}."""
    e6 = [(d.get("reads") or {}).get("E6") for d in days.values()]
    e6 = [r for r in e6 if r]
    refused = [cp._final(r.get("err")) for r in e6 if not r.get("ok")]
    whole = None
    if e6:
        whole = False if (any(refused) or any(r.get("ok") and r.get("cut") for r in e6)) else (
            True if all(r.get("ok") for r in e6) else None)
    uns = None if not [r for r in e6 if r.get("ok")] else not any(r.get("sampled") for r in e6 if r.get("ok"))
    ef = _every(_ef_day(d) for d in days.values())
    cov = _every(_cov_day(d) for d in days.values())
    pooled = [(d["cmp"]["cube"]["lo"], d["cmp"]["cube"]["hi"]) for d in days.values()
              if (d.get("cmp") or {}).get("cube") and d["cmp"]["cube"].get("hi") and d["cmp"]["cube"].get("clean")]
    tie = None if not pooled else (sum(a for a, _ in pooled) / sum(b for _, b in pooled)) >= CUBE_TIE_MIN
    checks = {"e6_whole": whole, "unsampled": uns, "ef_equal": ef, "coverage": cov, "cube_tie": tie}
    vals = list(checks.values())
    out = "nogo" if any(v is False for v in vals) else ("go" if complete and all(v is True for v in vals) else "unknown")
    return {"checks": checks, "verdict": out}


# ── one app ──────────────────────────────────────────────────────────────────────────────────────

def probe_app(run, u, token, now, prop, opts, data_dir=None):
    tz_today = ga4.window_end_in(u["tz"], now, lag=0)
    f = tz_today - timedelta(days=FINAL_LAG)
    hs = gu._d(u["history_start"]) if u.get("history_start") else None
    res = {"key": u["key"], "F": f.isoformat(), "days": {}}
    if not token:
        res.update(err={"type": "auth"}, complete=False)
        return res
    days = pick_days(f, hs)
    res["asked"] = [d.isoformat() for d in days]
    ga = cp.App(token, u["property_id"], u["stream_id"], run, prop, cap=opts.get("app_calls", APP_CALLS))
    try:
        for d in days:
            day = res["days"].setdefault(d.isoformat(), {"reads": {}, "cmp": {}})
            got = {}
            try:
                _day_reads(ga, d, day, got)
            finally:                                # (a Stop mid-day: the reads made are compared all the same)
                day["cmp"] = pr._safely(compare, got, day["reads"], d, u, data_dir, fallback={})
    except Stop as e:
        res["stopped"] = str(e)
    res["complete"] = "stopped" not in res and len(res["days"]) == len(days)
    res["verdict"] = pr._safely(verdict, res["days"], res["complete"], fallback={"verdict": "unknown"})
    res["fs"] = pr._safely(fs_pool, res["days"], fallback=None)
    res.update(calls=ga.by_kind, tokens=ga.tok, sec=round(ga.sec, 2))
    return res


def _day_reads(ga, d, day, got):
    """The five reads of activity day d into day["reads"] (records) and got (cells of the reads that came back)."""
    for kind in KINDS:
        req = request(kind, d)
        meta = {}

        def fetch(req=req):
            rows = ga.report_all(req["body"], event=req["event"], extra=req["extra"], page_rows=gu.UNI_PAGE_ROWS)
            meta["rc"], meta["cut"] = ga.last_row_count, bool(ga.truncated(rows))
            return rows

        def parse(rows, req=req, kind=kind):
            dims, mets, pair = req["dims"], req["mets"], req["pair"]
            rec = {"rows": len(rows), "row_count": meta.get("rc"), "cut": meta.get("cut", False),
                   "other_rows": sum(1 for r in rows if dp._other(r, dims)),
                   "unset_rows": sum(1 for r in rows if dp._unset(r, dims) and not dp._other(r, dims)),
                   "s": dp.shares(rows, dims, mets)}
            if kind == "ET":
                return rec, by_install(rows, d, pair)
            cells, rest = cells_of(rows, d, pair)
            rec.update(cells=len(cells), in_no_cell=rest)
            return rec, cells

        rec, idx = cp._read(ga, kind, fetch, parse)
        day["reads"][kind] = rec
        if rec.get("ok") and idx is not None:
            got[kind] = idx


def compare(got, reads, d, u, data_dir):
    """One day's cell comparisons from the answers in memory (got: {kind: cells, ET: {X: [...]}})."""
    out, e6 = {}, got.get("E6")
    if e6 is None:
        return out
    out["unflagged"] = not flagged(reads["E6"])
    if "EF" in got:
        out["ef"] = cmp_cells(e6, restrict(got["EF"], AGES))
    if "E14" in got:
        out["e14"] = cmp_cells(e6, restrict(got["E14"], AGES))
    if "P6" in got:
        out["p6"] = cmp_cells(e6, got["P6"])
    if "ET" in got:
        out["cov"], out["cov_min"] = coverage(e6, got["ET"])
    out["fs"] = pr._safely(fs_day, data_dir, u, d, e6, fallback={})
    got_c = cube_cells(data_dir, u, d, installs(d, AGES))
    if got_c is None:
        out["cube"] = {"day": False}
    else:
        cube, led = got_c
        c = cmp_cells({k: [v[0], 0] for k, v in e6.items()}, cube)
        lo = sum(min(e6.get(k, (0,))[0], cube.get(k, (0,))[0]) for k in set(e6) | set(cube))
        hi = sum(max(e6.get(k, (0,))[0], cube.get(k, (0,))[0]) for k in set(e6) | set(cube))
        out["cube"] = {"day": True, "lo": lo, "hi": hi, "rev": c["rev"], "ratio": c["rev_ratio"], "e6": c["a"],
                       "cube": c["b"], "only_e6": c["only_a"], "only_cube": c["only_b"], "equal": c["equal"],
                       "clean": cube_clean(led),     # (only a day the cube read whole is pooled for the tie)
                       "led": {f: led.get(f) for f in ("st", "via", "fl", "fu", "ol", "loss", "t")
                               if isinstance(led, dict)}}
    return out


# ── counts and the public line ───────────────────────────────────────────────────────────────────

def counts(apps, run):
    c = {"apps": len(apps), "reads": 0, "accepted": 0, "refused": 0, "failed": 0, "go": 0, "nogo": 0, "unknown": 0}
    for a in apps.values():
        for d in ((a or {}).get("days") or {}).values():
            for r in (d.get("reads") or {}).values():
                c["reads"] += 1
                if r.get("ok"):
                    c["accepted"] += 1
                elif cp._final(r.get("err")):
                    c["refused"] += 1
                else:
                    c["failed"] += 1
        v = ((a or {}).get("verdict") or {}).get("verdict")
        c[v if v in ("go", "nogo") else "unknown"] += 1
    c.update(calls=run.calls, seconds=run.elapsed())
    return c


def public_line(c):
    return ("cecpm probe: apps %d, reads %d, accepted %d, refused %d, failed %d, go %d, nogo %d, unknown %d, calls %d, %ds"
            % tuple(c.get(k, 0) for k in ("apps", "reads", "accepted", "refused", "failed", "go", "nogo", "unknown",
                                          "calls", "seconds")))


def run_probe(units, cid, sec, tokens, opts, now=None, clock=time.monotonic, last=None):
    """Probe every unit → the report; the apps of `last` (the last report's, same rules) not probed now are carried
    over as they were (a run that stopped can be completed for the apps it missed). Never raises for one app."""
    run = Run(opts.get("budget") or BUDGET_SEC, clock, opts.get("max_calls") or MAX_CALLS)
    now = now or datetime.now(timezone.utc)
    rt, access = dict(tokens), {}
    for owner in sorted({u.get("owner") or "" for u in units}):
        try:
            access[owner] = ga4.access_token(cid, sec, rt[owner]) if owner in rt else None
        except Exception:
            access[owner] = None
    probed = {u["key"] for u in units}
    out = {k: v for k, v in (last or {}).items() if k not in probed}
    props = {u["property_id"]: pr.new_prop() for u in units}
    lock, done = threading.Lock(), [0]

    def one(group):
        for u in group:
            try:
                r = probe_app(run, u, access.get(u.get("owner") or ""), now, props[u["property_id"]], opts,
                              opts.get("data_dir"))
            except Exception as e:
                r = {"key": u["key"], "crash": type(e).__name__, "complete": False}
            with lock:
                out[u["key"]] = r
                done[0] += 1
                n = done[0]
            run.say("cecpm progress: apps %d/%d, calls %d, %ds" % (n, len(units), run.calls, run.elapsed()))

    with sp.Beat(run, TICK_SEC):
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            list(ex.map(one, pr._groups(units)))
    c = pr._safely(counts, out, run, fallback={"apps": len(out), "calls": run.calls, "seconds": run.elapsed()})
    return {"v": 1, "probe": "ga4_cecpm", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rules": rules(run.max_calls), "counts": c, "apps": out}


def load_last(root, rules):
    """The last report's apps {key: result} made under the same rules (the clone's copy; {} when there is none, or it
    was made under other ages / days / thresholds — never mixed in)."""
    try:
        with open(os.path.join(root, OUT_PATH), encoding="utf-8") as f:
            j = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(j, dict) or j.get("v") != 1:
        return {}
    keep = ("ages", "offsets", "coverage_min", "cube_tie_min", "ef_equal_min")
    if {k: (j.get("rules") or {}).get(k) for k in keep} != {k: rules.get(k) for k in keep}:
        return {}
    return {k: v for k, v in (j.get("apps") or {}).items() if isinstance(v, dict)}


def rules(max_calls):
    return {"ages": list(AGES), "offsets": list(DAY_OFFSETS), "coverage_min": COVERAGE_MIN, "cube_tie_min": CUBE_TIE_MIN,
            "ef_equal_min": EF_EQUAL_MIN, "max_calls": max_calls}


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    inputs = ap.event_inputs(env)
    want = ap.wanted(inputs.get("apps") or env.get("CECPM_APPS"))
    root = env.get("CECPM_DATA_DIR") or DATA_DIR          # the clone's top folder (the routes: sp adds data/ itself)
    data_dir = os.path.join(root, "data")                 # the stores the cells are tied to
    if not os.path.isdir(os.path.join(data_dir, gcu.DIR)):
        sys.exit("no private clone: nothing to tie the reads to")     # before any GA4 call (stderr is hidden)
    units = cp.units_from_state(sp.load_state(root))
    if want:
        units = [u for u in units if ap.matches(u, want) or u["key"] in want]
    if not units:
        sys.exit("no GA4 app routes in the private state (or none matched)")
    max_calls = pr._int(inputs.get("max_calls") or env.get("CECPM_MAX_CALLS")) or MAX_CALLS
    last = load_last(root, rules(max_calls))
    print("cecpm probe: %d app(s) to probe, %d carried over" % (len(units), len(set(last) - {u["key"] for u in units})),
          flush=True)
    report = run_probe(units, cid, sec, tokens, {"app_calls": APP_CALLS, "data_dir": data_dir, "max_calls": max_calls},
                       now=now, clock=clock, last=last)
    print(public_line(report["counts"]), flush=True)
    if not pr.write_private(OUT_PATH, pr._dump(report), "ga4 cecpm probe"):
        sys.exit("private repo write failed")
    print("cecpm probe: report written", flush=True)


if __name__ == "__main__":
    main()
