"""One-off GA4 SCREENS probe, run by .github/workflows/ga4-screens-probe.yml (owner, 6 Nov 2026, on a big app's Screens
page: "ye kyu nahi he data?"). The Screens fetch (ga4_screens) keeps a day's ads-by-screen read only when GA4 gives it
whole; on the biggest apps many days come back sampled, and many more were never asked one day at a time (a shape
"dead" after three failures, or the volume gate). GA4's sampling is not a plain function of the day's events either: the
unit read was whole on a day with MORE events than a later day it came back sampled. This asks GA4 directly, ONE DAY PER
REQUEST, and keeps every answer:

  ALT    per app, on the days final_end − n (n in ALT_BACK; the nearest older day with a whole truth): every KIND — the
         fetch's own shapes and every other request GA4 offers for ads by screen (the Publisher ads report's
         publisherAdImpressions; screen path / page screen / screen name instead of class; no date dimension; no stream
         pin; the event as a dimension instead of a filter). Is any of them whole on a day the fetch's are sampled?
  SWEEP  per app, the days its store does not hold whole for the ads-by-screen read ("a"), spread evenly over its whole
         history (at most SWEEP_MAX), its TOP_WHOLE whole "a" days with the most events and its NEWEST final days:
         SWEEP_KINDS only. What decides the sampling — the day's events (the stream's, the property's), its age, neither?
  EQ     the ALT answers' top rows (KEEP_ROWS per answer, private): does another kind's per-screen split equal the
         fetch's "c" where both are whole?

Every answer: sampled (samplesReadCount, samplingSpaceSize), dataLossFromOtherRow, thresholding, rows / rowCount, the
named rows' sum, GA4's "(other)" and "(not set)" rows' sums, the tokens it cost (the response's tokensPerDay consumed)
and seconds; a refusal keeps its HTTP status class only, never the text. Each probed day also carries what the store
holds for it (the truth: TA ad_impression events by format, TE0 every event, views; the "a" and "w" records' state,
shape, tries, skip reason, sample share).

Apps: the workflow input `apps` (comma list of file keys / app ids / packages, read from the event file only), else every
app whose Screens store holds a final "a" day that is not whole, plus CONTROL: of the others, the one with the most
events on its newest whole final day (its EQ says whether another metric equals the fetch's at all).

ROUND 4 (owner, 8 Nov 2026, Firebase's own "Pages and screens" export beside the tab: "Firebase jaise numbers … Revenue"):
         revenue by screen (totalRevenue / totalAdRevenue by date × class or page path, 31 days and one day, against
         their date totals — GA4 gives revenue as a decimal: kept here in micros) and the users of a whole PERIOD by
         screen and of the app (no date dimension: unique within the period, as Firebase's "Active users"), 7 … 1000
         days; plus each property's currency and time zone (Admin API). The workflow input `days` pins the ALT days to
         ISO dates (the last day of a 31-day month: "31 days" = that month; a shorter month needs its own range).

Output: ga4/screens_probe.json in the PRIVATE repo only (dp.write_private). PUBLIC LOG: a counts-only heartbeat and ONE
result line of counts — no names, ids, dates or numbers of the data. Quota: the Screens fetch's own App and floors
(ga4_screens.quota_gate: a property stops when a token bucket is under 60 %, so the hourly builds keep theirs); one request
at a time per property, properties side by side; no request after BUDGET_SEC (what was read is still written)."""

import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import ga4
from . import ga4_audience_probe as ap
from . import ga4_d1d7_probe as dp
from . import ga4_firstopen as gf
from . import ga4_screens as gs
from . import ga4_uninstall as gu

OUT = "ga4/screens_probe.json"
BUDGET_SEC = 20 * 60                    # no GA4 request after this; what was read is written
ALT_BACK = (0, 30, 95, 200)             # ALT days: final_end − n
SWEEP_MAX = 40                          # not-whole "a" days per app, evenly over its history …
TOP_WHOLE = 5                           # … its whole "a" days with the most events …
NEWEST = 5                              # … and its newest final days
LIMIT = 100000                          # rows per request (a day's split is far smaller; rowCount says if not)
KEEP_ROWS = 120                         # an ALT answer's top rows kept for EQ
WORKERS = 8                             # properties side by side
HEARTBEAT_SEC = 60
SC, PP, PS, SN = gs.SC, "unifiedPagePathScreen", "unifiedPageScreen", "unifiedScreenName"
FMT, UNIT, EVN, IMP = gs.FMT, gs.UNIT, gs.EVN, gs.IMP
NVR, VER, CTY = gs.NVR, gs.VER, gs.CTY
EC, PUB, PV, EXP = "eventCount", "publisherAdImpressions", "screenPageViews", "adUnitExposure"
ENG, USR, SES = "userEngagementDuration", "activeUsers", "sessions"
REV_T, REV_A = "totalRevenue", "totalAdRevenue"
REV = frozenset((REV_T, REV_A))         # GA4 answers these as decimals: kept in micros (int) here
UNSET = frozenset(("(not set)", ""))
INLINE = ("Banner", "Native advanced", "Native")          # GA4's ad format names (as the truth TA holds them)
FULL = ("Interstitial", "App open", "Rewarded", "Rewarded interstitial")
# kind → (date dimension?, dims, metric, filter[, days: the range ends on the probed day, 1 when left out]): "pe" the
# fetch's pin (platform Android + the app's stream) + eventName == ad_impression · "pi" / "pfs" / "pb" that and the
# ad format in INLINE / in FULL / == Banner · "pk" the pin + the click events (the fetch's "k") · "p" the pin alone · "se" the stream + the event (no platform) · "e" the event alone (the whole property)
# · "" nothing (the whole property, every event)
KINDS = {
    "t": (True, (), EC, "pe"),              # the day's ad_impression events now (the truth the fetch ties)
    "t_all": (True, (), EC, "p"),           # every event of the stream (the fetch's TE0)
    "t_prop": (True, (), EC, ""),           # every event of the property (GA4 samples on the property's events)
    "t_stream": (True, (), EC, "se"),
    "t_nopin": (True, (), EC, "e"),
    "t_pub": (True, (), PUB, "p"),
    "t_pub_prop": (True, (), PUB, ""),
    "t_views": (True, (), PV, "p"),
    "t_exp": (True, (), EXP, "p"),
    "c": (True, (SC,), EC, "pe"),           # the fetch's "a" at its coarsest shape …
    "cf": (True, (SC, FMT), EC, "pe"),      # … at "f"
    "u": (True, (FMT, UNIT), EC, "pe"),     # the fetch's "w"
    "c_nodate": (False, (SC,), EC, "pe"),
    "pp": (True, (PP,), EC, "pe"),
    "ps": (True, (PS,), EC, "pe"),
    "sn": (True, (SN,), EC, "pe"),
    "ce": (True, (SC, EVN), EC, "p"),       # the event as a dimension, not a filter (its ad_impression rows kept)
    "c_stream": (True, (SC,), EC, "se"),
    "c_nopin": (True, (SC,), EC, "e"),
    "c_pub": (True, (SC,), PUB, "p"),
    "cf_pub": (True, (SC, FMT), PUB, "p"),
    "pp_pub": (True, (PP,), PUB, "p"),
    "ppf_pub": (True, (PP, FMT), PUB, "p"),
    "u_pub": (True, (FMT, UNIT), PUB, "p"),
    "c_pub_prop": (True, (SC,), PUB, ""),
    "v": (True, (SC,), PV, "p"),            # views by class: the fetch's "v"
    "e": (True, (SC,), EXP, "p"),           # the fetch's "e"
    # round 2 (6 Nov: the page path was whole wherever the class was sampled or lost rows): the page path in every
    # shape the Screens reads use, and 31 days in one request
    "t31": (True, (), EC, "pe", 31),
    "t_k": (True, (), EC, "pk"),
    "t_eng": (True, (), ENG, "p"),
    "ppf": (True, (PP, FMT), EC, "pe"),
    "ppfu": (True, (PP, FMT, UNIT), EC, "pe"),
    "pp31": (True, (PP,), EC, "pe", 31),
    "ppf31": (True, (PP, FMT), EC, "pe", 31),
    "ppk": (True, (PP, EVN), EC, "pk"),         # "k": clicks by screen
    "ppe": (True, (PP, EVN), EC, "p"),          # every event by screen ("x"'s shape)
    "ppx": (True, (PP,), EXP, "p"),             # "e"
    "ppv": (True, (PP,), PV, "p"),              # "v"
    "ppeng": (True, (PP,), ENG, "p"),
    "ppu": (True, (PP,), USR, "pe"),            # "uA" (users: not additive, flags only)
    "ppsu": (True, (PP,), SES, "p"),            # "uV" (flags only)
    "nppf": (True, (NVR, PP, FMT), EC, "pe"),
    "npp": (True, (NVR, PP), EC, "pe"),
    "nppv": (True, (NVR, PP), PV, "p"),
    "rppf": (True, (VER, PP, FMT), EC, "pe"),
    "rpp": (True, (VER, PP), EC, "pe"),
    "rppv": (True, (VER, PP), PV, "p"),
    "cppf": (True, (CTY, PP, FMT), EC, "pe"),
    "cpp": (True, (CTY, PP), EC, "pe"),
    "cppv": (True, (CTY, PP), PV, "p"),
    "cfu": (True, (SC, FMT, UNIT), EC, "pe"),   # the fetch's "a" at "fu" (last: the class is the costly one)
    "ncf": (True, (NVR, SC, FMT), EC, "pe"),    # the fetch's "nA" at "cf"
    # round 3 (6 Nov: the page path is whole alone but sampled with the ad format on the biggest apps): the format by
    # a filter instead of a dimension, and the ad unit (whose format the unit read gives) instead of the format
    "tI": (True, (), EC, "pi"),
    "tFS": (True, (), EC, "pfs"),
    "tB": (True, (), EC, "pb"),
    "tI31": (True, (), EC, "pi", 31),
    "ppI": (True, (PP,), EC, "pi"),
    "ppFS": (True, (PP,), EC, "pfs"),
    "ppB": (True, (PP,), EC, "pb"),
    "ppI31": (True, (PP,), EC, "pi", 31),
    "ppU": (True, (PP, UNIT), EC, "pe"),
    "ppU31": (True, (PP, UNIT), EC, "pe", 31),
    # round 4 (8 Nov: Firebase's numbers beside the tab): revenue by screen against its date total, and a period's users
    # (no date: unique in the period) by class and for the app
    "t_rv31": (True, (), REV_T, "p", 31),
    "t_rva31": (True, (), REV_A, "p", 31),
    "rv_c31": (True, (SC,), REV_T, "p", 31),
    "rva_c31": (True, (SC,), REV_A, "p", 31),
    "rv_pp31": (True, (PP,), REV_T, "p", 31),
    "t_rv": (True, (), REV_T, "p"),
    "rv_c": (True, (SC,), REV_T, "p"),
    "us_t31": (False, (), USR, "p", 31),
    "us_c31": (False, (SC,), USR, "p", 31),
    "us_c7": (False, (SC,), USR, "p", 7),
    "us_c90": (False, (SC,), USR, "p", 90),
    "us_c365": (False, (SC,), USR, "p", 365),
    "us_c1000": (False, (SC,), USR, "p", 1000),
    "us_t1000": (False, (), USR, "p", 1000),
}
SWEEP_KINDS = ("c", "u", "t_prop")
# a split kind → the day total (a kind above) its rows must add up to: the same metric under the same filter
REF = {"c": "t", "cf": "t", "u": "t", "c_nodate": "t", "pp": "t", "ps": "t", "sn": "t", "ce": "t", "c_stream": "t_stream",
       "c_nopin": "t_nopin", "c_pub": "t_pub", "cf_pub": "t_pub", "pp_pub": "t_pub", "ppf_pub": "t_pub", "u_pub": "t_pub",
       "c_pub_prop": "t_pub_prop", "v": "t_views", "e": "t_exp",
       "cfu": "t", "ppf": "t", "ppfu": "t", "pp31": "t31", "ppf31": "t31", "ppk": "t_k", "ppe": "t_all", "ppx": "t_exp",
       "ppv": "t_views", "ppeng": "t_eng", "nppf": "t", "npp": "t", "nppv": "t_views", "rppf": "t", "rpp": "t",
       "rppv": "t_views", "cppf": "t", "cpp": "t", "cppv": "t_views", "ncf": "t",
       "ppI": "tI", "ppFS": "tFS", "ppB": "tB", "ppI31": "tI31", "ppU": "t", "ppU31": "t31",
       "rv_c31": "t_rv31", "rva_c31": "t_rva31", "rv_pp31": "t_rv31", "rv_c": "t_rv"}
KEEP_KINDS = frozenset(k for k, v in KINDS.items() if v[1] and v[1][0] in (SC, PP, PS, SN))
TAG_RE = re.compile(r"[a-z0-9]{1,12}")
DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _i(v):
    return gs._i(v)


def _http_class(e):
    """A refusal → its status class only ("4xx" / "5xx" / "other"), never the text."""
    s = str(e)
    if s.startswith("HTTP 4"):
        return "4xx"
    if s.startswith("HTTP 5"):
        return "5xx"
    return "other"


def _flt(f, stream_id):
    ex = []
    fmt = {"pi": INLINE, "pfs": FULL, "pb": ("Banner",)}.get(f)
    if f in ("pe", "pk", "p") or fmt:
        ex.append(ga4._exact("platform", "Android"))
    if f in ("pe", "pk", "p", "se") or fmt:
        ex.append(ga4._exact("streamId", stream_id))
    if f in ("pe", "se", "e") or fmt:
        ex.append(ga4._exact("eventName", IMP))
    if f == "pk":
        ex.append(ga4._in_list("eventName", gs.CLICKS))
    if fmt:
        ex.append(ga4._in_list(FMT, fmt))
    return {"andGroup": {"expressions": ex}} if ex else None


def _kind(kind):
    """KINDS[kind] → (date dimension?, dims, metric, filter, days)."""
    v = KINDS[kind]
    return tuple(v) + (1,) * (5 - len(v))


def request(kind, day, stream_id):
    """The runReport body of `kind` for the range of its days ending on `day`."""
    dated, dims, met, f, n = _kind(kind)
    b = {"dateRanges": [gu._rng(day - timedelta(days=n - 1), day)],
         "dimensions": ga4._dim(*((("date",) if dated else ()) + dims)),
         "metrics": ga4._dim(met), "keepEmptyRows": False, "limit": LIMIT, "returnPropertyQuota": True}
    flt = _flt(f, stream_id)
    if flt:
        b["dimensionFilter"] = flt
    return b


def measure(kind, j):
    """One answer → (its record without kind / day, {row key: value} of the rows that count). A row's key is its
    dimensions after date joined by "|"; "ce" keeps only its ad_impression rows (keyed by class)."""
    dated, dims, met, _, _ = _kind(kind)
    meta = j.get("metadata") or {}
    rows = ga4._rows(j)
    rec = {"n": len(rows), "rc": _i(j.get("rowCount", len(rows))), "loss": bool(meta.get("dataLossFromOtherRow")),
           "thr": bool(meta.get("subjectToThresholding"))}
    sm = [s or {} for s in meta.get("samplingMetadatas") or []]
    if sm:
        space = sum(_i(s.get("samplingSpaceSize")) for s in sm)
        read = sum(_i(s.get("samplesReadCount")) for s in sm)
        rec.update(s=True, space=space, read=read, smp=round(read / float(space), 4) if space else None)
    q = j.get("propertyQuota") or {}
    rec["tok"] = _i((q.get("tokensPerDay") or {}).get("consumed"))
    vals, named, fold, unset = {}, 0, 0, 0
    for r in rows:
        if kind == "ce":
            if str(r.get(EVN)) != IMP:
                continue
            key = (str(r.get(SC) if r.get(SC) is not None else ""),)
        else:
            key = tuple(str(r.get(d) if r.get(d) is not None else "") for d in dims)
        v = int(round(float(r.get(met) or 0) * 1e6)) if met in REV else _i(r.get(met))
        if any(gs._isfold(x) for x in key):
            fold += v
        elif dims and any(x.strip().lower() in UNSET for x in key):
            unset += v
        else:
            named += v
        k = "|".join(key)
        vals[k] = vals.get(k, 0) + v
    rec.update(sum=named, fold=fold, unset=unset)
    return rec, vals


def ask(ga, run, kind, day, stream_id):
    """One GA4 answer for one day → (record, row values or None). gf.Stop passes up (the property stops, the run goes
    on with the others); any other refusal is kept as its HTTP class."""
    rec = {"k": kind, "d": day.isoformat()}
    t0 = time.monotonic()
    try:
        j = ga._post("runReport", request(kind, day, stream_id))
    except gf.Stop:
        raise
    except Exception as e:                              # noqa: BLE001 — a refusal is data here, never fatal
        run.count(rec.setdefault("http", _http_class(e)))
        return rec, None
    m, vals = measure(kind, j)
    rec.update(m, sec=round(time.monotonic() - t0, 2))
    run.count("s" if rec.get("s") else "loss" if rec.get("loss") else "ok", rec.get("tok"))
    return rec, vals


class Run(dp.Run):
    """dp.Run's clock and counts-only heartbeat, with this probe's own counters."""

    def __init__(self, budget=BUDGET_SEC, clock=time.monotonic):
        super().__init__(budget, clock)
        self.c = dict.fromkeys(("ok", "s", "loss", "4xx", "5xx", "other", "tok", "stopped"), 0)

    def count(self, what, tok=None):
        """One answer (or refusal) of kind `what`; the call is ticked."""
        self.bump(what, tok)
        self.tick()

    def bump(self, what, tok=None):
        with self.lock:
            self.c[what] = self.c.get(what, 0) + 1
            self.c["tok"] += _i(tok)

    def tick(self):
        with self.lock:
            self.calls += 1
            now = self.clock()
            beat = now - self.beat >= HEARTBEAT_SEC
            if beat:
                self.beat = now
            n, s = self.calls, int(now - self.t0)
        if beat:
            self.say("screens probe progress: calls %d, %ds" % (n, s))


# ── the store side ──────────────────────────────────────────────────────────────────────────────────────────────────
def store_days(data_dir, key):
    """An app's final records of the core reads → {day: {read id: record}}."""
    out = {}
    for _, _, days in gs.iter_months(data_dir, key, "core"):
        for d, recs in days.items():
            out.setdefault(d, {}).update(recs)
    return out


def _brief(rec):
    return {k: rec[k] for k in ("st", "g", "tried", "skip", "smp", "cov", "f") if isinstance(rec, dict) and k in rec}


def day_info(recs):
    """What the store holds for a day (the probe's comparison side; private)."""
    t = recs.get("t") or {}
    taf = {str(f): _i(n) for f, n in t.get("a") or ()}
    return {"ev": t.get("ev"), "ta": sum(taf.values()), "taf": taf, "views": (t.get("v") or [None])[0],
            "a": _brief(recs.get("a")), "w": _brief(recs.get("w"))}


def evenly(xs, n):
    """At most n items of xs, spread evenly (its first and last kept)."""
    if len(xs) <= n:
        return list(xs)
    if n <= 1:
        return list(xs[-1:])
    return [xs[round(i * (len(xs) - 1) / float(n - 1))] for i in range(n)]


def plan(days, final_end, back=ALT_BACK):
    """{day: recs} of the store → (ALT days: final_end − n for n in `back`, SWEEP days) — final days with a whole truth
    only, ISO, newest first."""
    fe = final_end.isoformat()
    ok = sorted(d for d, r in days.items() if d <= fe and gs._whole(r.get("t")))
    if not ok:
        return [], []
    alt = []
    for n in back:
        want = (final_end - timedelta(days=n)).isoformat()
        older = [d for d in ok if d <= want]
        if older and older[-1] not in alt:
            alt.append(older[-1])
    bad = [d for d in ok if not gs._whole(days[d].get("a"))]
    top = sorted((d for d in ok if gs._whole(days[d].get("a"))), key=lambda d: -_i((days[d].get("t") or {}).get("ev")))
    sweep = set(evenly(bad, SWEEP_MAX)) | set(top[:TOP_WHOLE]) | set(ok[-NEWEST:])
    return alt, sorted(sweep, reverse=True)


def _final_end(tz, now):
    try:
        today = now.astimezone(ZoneInfo(tz or "UTC")).date()
    except Exception:                                   # noqa: BLE001 — an unknown zone reads as UTC
        today = now.astimezone(timezone.utc).date()
    return today - timedelta(days=gs.FINAL_LAG)


def choose(data_dir, now, want=None):
    """The app keys to probe: `want` (a set of lower-case tokens) when given, else every app with a final "a" day not
    whole + the CONTROL app → ([key], control key or None)."""
    keys = gs.store_keys(data_dir)
    if want:
        out = []
        for k in keys:
            m = gs.load_meta(data_dir, k) or {}
            if {k, str(m.get("app_id") or "").lower(), str(m.get("package") or "").lower()} & set(want):
                out.append(k)
        return out, None
    bad, ctrl, best = [], None, -1
    for k in keys:
        m = gs.load_meta(data_dir, k) or {}
        days = store_days(data_dir, k)
        fe = _final_end(m.get("time_zone"), now).isoformat()
        ok = [d for d in sorted(days) if d <= fe and gs._whole(days[d].get("t"))]
        if any(not gs._whole(days[d].get("a")) for d in ok):
            bad.append(k)
        elif ok:
            ev = _i((days[ok[-1]].get("t") or {}).get("ev"))
            if ev > best:
                ctrl, best = k, ev
    return bad + ([ctrl] if ctrl else []), ctrl


# ── one app ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def probe_app(ga, run, it, data_dir, now, keep, opts=None):
    """One app: ALT (every kind — or opts["only"] — on its ALT days) then SWEEP (unless opts["sweep"] is False) → its
    private result. gf.Stop ends it (kept so far)."""
    opts = opts or {}
    key = gu.file_key(it["a"]["app_id"])
    sid = it["r"]["stream_id"]
    days = store_days(data_dir, key)
    fe = _final_end(it.get("tz"), now)
    alt, sweep = plan(days, fe, opts.get("back") or ALT_BACK)
    if opts.get("days"):
        alt = list(opts["days"])
    if opts.get("sweep") is False:
        sweep = []
    res = {"final_end": fe.isoformat(), "alt": alt, "sweep": sweep, "ans": [], "rows": {}, "days": {},
           "stopped": None}
    try:                                                # the property's currency and time zone (round 4)
        res["prop"] = ga4.property_meta(ga.token, ga.property_id)
    except Exception as e:                              # noqa: BLE001 — a refusal is data here, never fatal
        res["prop"] = {"http": _http_class(e)}
    for d in set(alt) | set(sweep):
        res["days"][d] = day_info(days.get(d) or {})
    kinds = [k for k in KINDS if not opts.get("only") or k in opts["only"]]
    todo = [(k, d) for d in alt for k in kinds] + [(k, d) for d in sweep if d not in alt for k in SWEEP_KINDS]
    try:
        for k, d in todo:
            rec, vals = ask(ga, run, k, gu._d(d), sid)
            res["ans"].append(rec)
            if vals and k in keep and d in alt:
                res["rows"]["%s|%s" % (k, d)] = dict(sorted(vals.items(), key=lambda kv: -kv[1])[:KEEP_ROWS])
    except gf.Stop as e:
        res["stopped"] = (e.args or ["stop"])[0]
        run.bump("stopped")
    return res


def summary(apps):
    """Per kind: answers, sampled, loss, refused, and "tie": its rows (named + "(other)" + "(not set)") within the
    fetch's tolerance of the same day's REF total, when that total came back unsampled (tie_n) — counts only."""
    out = {}
    for res in apps.values():
        tot = {(r["k"], r["d"]): r["sum"] + r["fold"] + r["unset"] for r in res["ans"]
               if r["k"].startswith("t") and "sum" in r and not r.get("s")}
        for r in res["ans"]:
            s = out.setdefault(r["k"], {"n": 0, "s": 0, "loss": 0, "refused": 0, "tie": 0, "tie_n": 0})
            s["n"] += 1
            if r.get("http"):
                s["refused"] += 1
                continue
            s["s"] += 1 if r.get("s") else 0
            s["loss"] += 1 if r.get("loss") else 0
            want = tot.get((REF.get(r["k"]), r["d"]))
            if want and not r.get("s"):
                s["tie_n"] += 1
                if abs(r["sum"] + r["fold"] + r["unset"] - want) <= max(gs.TIE_REL * want, gs.TIE_ABS):
                    s["tie"] += 1
    return out


def run_all(cfg, data_dir, apps_want, now=None, clock=time.monotonic, budget=BUDGET_SEC, workers=WORKERS, opts=None):
    """Every chosen app → {"v", "at", "control", "opts", "apps": {key: result}, "summary", "counts"}. Never raises."""
    now = now or datetime.now(timezone.utc)
    run = Run(budget, clock)
    opts = opts or {}
    out = {"v": 1, "at": now.isoformat(), "control": None, "apps": {}, "summary": {}, "counts": run.c,
           "opts": {k: sorted(v) if isinstance(v, (set, frozenset)) else v for k, v in opts.items()}}
    try:
        keys, ctrl = choose(data_dir, now, apps_want)
        out["control"] = ctrl
        apps = gs.bf_apps(data_dir, set(keys))
        counts = dict.fromkeys(gs.BF_COUNTS, 0)
        by_prop = gs._select(cfg, data_dir, apps, now, gs.load_state(data_dir), counts, {"apps": {}}, retry=False,
                             clock=clock)
        lock = threading.Lock()

        def one(pid):
            prop = {"quota": None, "stop": None, "stops": 0}
            for it in sorted(by_prop[pid], key=lambda t: t["a"]["app_id"]):
                if not it["tok"]:
                    continue
                ga = gs.App(it["tok"], pid, it["r"]["stream_id"], prop, over=run.over, max_calls=10 ** 6,
                            gate=gs.quota_gate, renew=it.get("renew"))
                res = probe_app(ga, run, it, data_dir, now, KEEP_KINDS, opts)
                with lock:
                    out["apps"][gu.file_key(it["a"]["app_id"])] = res
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            for f in [ex.submit(one, pid) for pid in sorted(by_prop)]:
                try:
                    f.result()
                except Exception:                       # noqa: BLE001 — one property's trouble never ends the probe
                    run.count("other")
        out["summary"] = summary(out["apps"])
    except Exception as e:                              # noqa: BLE001 — what was read is still written
        out["error"] = type(e).__name__
    return out


def line(out):
    """The ONE public result line — counts only."""
    c = out.get("counts") or {}
    return ("screens probe: apps %d, calls %d, tokens %d, sampled %d, loss %d, refused %d, stopped %d%s"
            % (len(out.get("apps") or {}), sum(_i(c.get(k)) for k in ("ok", "s", "loss", "4xx", "5xx", "other")),
               _i(c.get("tok")), _i(c.get("s")), _i(c.get("loss")), sum(_i(c.get(k)) for k in ("4xx", "5xx", "other")),
               _i(c.get("stopped")), (", error " + out["error"]) if out.get("error") else ""))


def options(inp):
    """The workflow inputs → (opts, the private path): `only` a comma list of kinds (unknown ones dropped; none left =
    every kind), `sweep` "0" / "no" = no SWEEP, `back` a comma list of day offsets for the ALT days, `days` a comma list
    of ISO dates that ARE the ALT days (anything else dropped; newest first), `tag` [a-z0-9]{1,12} →
    ga4/screens_probe_<tag>.json (a new round never overwrites an earlier one's file)."""
    inp = inp or {}
    only = {k.strip() for k in str(inp.get("only") or "").split(",") if k.strip() in KINDS}
    back = tuple(int(x) for x in str(inp.get("back") or "").split(",") if x.strip().isdigit())
    days = []
    for x in str(inp.get("days") or "").split(","):
        x = x.strip()
        if DAY_RE.fullmatch(x):
            try:
                days.append(date.fromisoformat(x).isoformat())
            except ValueError:
                pass
    opts = {"only": only or None, "sweep": str(inp.get("sweep") or "").strip().lower() not in ("0", "no", "false"),
            "back": back or None, "days": tuple(sorted(set(days), reverse=True)) or None}
    tag = str(inp.get("tag") or "").strip().lower()
    return opts, ("ga4/screens_probe_%s.json" % tag) if TAG_RE.fullmatch(tag) else OUT


def main(env=None, now=None):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    if not (cid and sec and (env.get("GA4_REFRESH_TOKENS") or env.get("GA4_REFRESH_TOKEN"))):
        sys.exit("GA4 client or refresh tokens missing")
    data_dir = os.path.join(env.get("SCREENS_PROBE_DATA_DIR") or gs.DATA_ROOT, "data")
    cfg = {"client_id": cid, "client_secret": sec, "refresh_tokens": env.get("GA4_REFRESH_TOKENS") or "",
           "refresh_token": env.get("GA4_REFRESH_TOKEN") or ""}
    inp = ap.event_inputs(env)
    opts, path = options(inp)
    out = run_all(cfg, data_dir, ap.wanted(inp.get("apps")), now=now, opts=opts)
    ok = dp.write_private(path, json.dumps(out, separators=(",", ":"), sort_keys=True),
                          "screens probe %s UTC" % time.strftime("%Y-%m-%d %H:%M", time.gmtime()))
    print(line(out) + (", written" if ok else ", NOT written"), flush=True)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
