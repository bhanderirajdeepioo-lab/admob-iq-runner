"""GA4 → per-app Audience store (data/ga4_audience/<key>.json.gz): for every install day, how many of its users were
active in each trailing window of 1, 2, 3 … months — straight from GA4, no app-side module. engine.audience turns it
(with the Uninstall store's installs and uninstalls) into "dead users by months since their last open".

THE REQUEST — the owner's method on the Data API: metric activeUsers, dimension firstSessionDate, pinned to the app's
Android stream (ga4.Ga4App), over trailing date ranges that all END on E, the latest FINAL activity day:
    E        = ga4_uninstall.settled_end − FINAL_LAG_DAYS (today − 2 in the property's timezone from noon, else − 3; GA4
               activity is final 3 days later — the Active users tab's settled_till, the install-value reads' F);
    windows  = TIERED months (engine.audience.tier_months): 1, 2 … 12, then 15, 18, 21, 24, then every 6 months (30,
               36 …) up to the first window that holds the app's whole history (the Uninstall store's history_start);
               window N months = [E − w + 1, E], w = floor(N × 30.4375) days. Past a year a coarser step costs far fewer
               tokens (a 1,300-day app: 20 windows, ~9,500 range-days, instead of 43 monthly ones, ~28,800);
    "dau"    = E alone: actives on E by install day ("today's DAU by install month" — on the latest FINAL day, ~5 days
               back: the days after it are still filling in. FINAL_LAG_DAYS = 0 would read the robot's settled day
               itself, ~2 days back, with its newest days a little low).
Named date ranges, up to RANGES_PER_CALL (4, the Data API's limit) per request while the call's token estimate stays
under CALL_EST_CAP (a big app's long windows go one or two a call: smaller steps fit an hourly bucket and resume
cleanly). Every row paged (Ga4App.report_all), metricAggregations TOTAL (GA4's own distinct actives of each range: the
split's self-check). A request that needed more than one page with 2+ ranges is asked again range by range.

RESUMABLE — a big app's read spans runs. The store keeps the latest COMPLETE result at its top level and the read in
progress under "partial": {E, history_start, months, windows, ranges {name: result} (the ranges done), slicing {name:
state} ("(other)" re-asks under way), calls, tokens, units, runs, started_at}. Every finished call is kept; a run that
hits the quota, its budget or a call cap stops and the next run (or hour) goes on from there — never from the start.
E is FROZEN for a partial: when a new final day appears before it completes, the old E is finished first, then the
read rolls forward to the new E (in the same run when quota and time allow).

TOKENS — estimated per call as k × Σ (range days × install days in the history) ("range-days × rows": GA4 charges by
the data a report scans and the rows it returns; a firstSessionDate split returns up to one row per install day). k is
PER APP: measured from its own calls (tokens ÷ units, state "k" — its last run's) and used next time; PRIOR_K before
its first call, calibrated on the first probe's biggest apps (~1,500 tokens for a call of four ~1,250-day windows over
~1,300 install days); small apps paid far less, and their own k replaces it after one call. A slice of an "(other)"
re-ask is estimated like the whole range (if GA4 charges by the data scanned, a slice costs as much).

NEVER HIDDEN — flagged in the store:
  * "(other)" rows (GA4 folds what it can't keep into one row): that range is asked again by install-day slices
    (firstSessionDate inList, ≤ IN_LIST_MAX days each; a slice that still has "(other)" is halved down to IN_LIST_MIN
    days, then kept flagged) — resumable slice by slice. metadata.dataLossFromOtherRow without any "(other)" row
    re-asks every range of that call (the response can't say which). Whatever still sits in "(other)" stays there per
    window (store "other"), never spread over install days;
  * "(not set)" first-session days (store "not_set"); install days before history_start stay in by_fsd as GA4 gave
    them (engine.audience shows them apart);
  * thresholding (subjectToThresholding: small counts withheld), sampling, a cut report (truncated), TOTAL refused (a
    400: asked without it, no_total), a split whose Σ rows is off TOTAL by more than 5% (cov_off {window: Σ ÷ TOTAL}).

IN THE BUILD (uninstall_build, only with the repo variable GA4_AUDIENCE=true): after the Uninstall fetch, each selected
app with an Uninstall store is read when it has a partial read or a new final day E — a complete app at most once a day;
a failed one waits RETRY_HOURS. Its own run budget (GA4_AUDIENCE_BUDGET_SEC): no app starts past it, a started one stops
at 2× (its progress kept). QUOTA (per property): a call goes only when its estimate leaves every hourly token bucket of
the last snapshot above HOUR_FLOOR (and the daily one above 10%); every call first checks the snapshot (quota_stop) and a
429 stops the property for the run — the Uninstall fetch of the next hour keeps its quota. State (private):
data/ga4_audience/state.json. Nothing here prints: the build log gets ONE counts-only line (log_line).
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone

from . import ga4
from . import ga4_uninstall as gu
from .. import ga4_probe
from ..db import write_json_gz_stable
from ..engine.audience import tier_months, window_days

DIR = "ga4_audience"
FINAL_LAG_DAYS = gu.ACT_LATE_DAYS   # E = the robot's settled day − 3: GA4 activity is final then (the Active users tab)
STORE_V = 2                 # 2: tiered windows + the resumable partial read (another format: read again)
RANGES_PER_CALL = 4         # date ranges per runReport (the Data API's limit)
PAGE_ROWS = 100000          # rows per page (≤ 4 ranges × one row per install day: one page, even at 1,300 days)
IN_LIST_MAX = 400           # an "(other)" range is asked again in slices of ≤ 400 install days (inList values) …
IN_LIST_MIN = 30            # … a slice that still has "(other)" is halved, down to 30 days (then kept, flagged)
MAX_CALLS = 40              # calls per app per RUN at most (its read goes on in the next run)
PRIOR_K = 2.5e-4            # tokens per unit (range-day × install day) before an app's own calls are measured
CALL_EST_CAP = 1500         # a call takes another range (≤ 4) only while its estimate stays under this many tokens
HOUR_FLOOR = 0.5            # a call goes only if its estimate leaves each hourly token bucket ≥ half (and stops under
                            # half: the install-value backfill's own floor) …
DAY_FLOOR = 0.1             # … and the daily bucket ≥ 10% (the Uninstall fetch's own stop)
COUNT_FLOOR = {"serverErrorsPerProjectPerHour": 4, "potentiallyThresholdedRequestsPerHour": 5}
COV_LO, COV_HI = 0.95, 1.05  # Σ rows ÷ GA4's TOTAL outside this → cov_off (user counts are sketches: ±1–2% is noise)
COV_MIN_USERS = 200         # (a window with fewer actives is not judged)
BUDGET_SEC = 180            # the build's own budget for this step
RETRY_HOURS = 3.0           # a failed app waits this long
DAU = "dau"


class Stop(Exception):
    """The app's reads stop here: the property's quota, a call's estimate that doesn't fit, a 429, the run's budget
    or its call cap. Whatever was read is kept (the partial read)."""


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _d(s):
    return gu._d(s)


def _err(e):
    """An exception → its class only (never its text): {"http": 400, "status": "INVALID_ARGUMENT"} or {"type": …}."""
    s = str(e)
    if s.startswith("HTTP "):
        head = s[5:].split(":", 2)
        out = {"http": _int(head[0])}
        st = head[1].strip() if len(head) > 1 else ""
        if st and st.replace("_", "").isalpha() and st.isupper():
            out["status"] = st
        return out
    return {"type": type(e).__name__}


# ── the plan: windows, ranges, calls, tokens ────────────────────────────────────────────────────────

def final_end(tz_name, now):
    """E, the latest FINAL activity day: the robot's settled day (gu.settled_end) − FINAL_LAG_DAYS."""
    return gu.settled_end(tz_name, now) - timedelta(days=FINAL_LAG_DAYS)


def install_days(end, hs):
    """Install days in the history: the rows a firstSessionDate split can return (the token estimate's "rows")."""
    return max(1, (end - hs).days + 1)


def months_for(end, hs):
    return tier_months(install_days(end, hs))


def ranges_for(end, hs, months=None):
    """[(name, start, end)]: "dau" (E alone), then "w<days>" for every window — all ending on E."""
    ms = months or months_for(end, hs)
    return [(DAU, end, end)] + [("w%d" % window_days(m), end - timedelta(days=window_days(m) - 1), end) for m in ms]


def _days_of(rg):
    return (rg[2] - rg[1]).days + 1


def estimate(group, rows, k):
    """Tokens a call of these ranges should cost: k × Σ range days × rows."""
    return k * sum(_days_of(rg) for rg in group) * rows


def next_group(todo, rows, k):
    """The next call's ranges: the first one left, then more (≤ RANGES_PER_CALL) while the estimate stays under
    CALL_EST_CAP."""
    g = [todo[0]]
    for rg in todo[1:RANGES_PER_CALL]:
        if estimate(g + [rg], rows, k) > CALL_EST_CAP:
            break
        g.append(rg)
    return g


def plan_calls(end, hs, k=PRIOR_K):
    """One app's request plan (no "(other)" re-asks) → {windows, months, ranges, calls, range_days, install_days, units,
    tokens_est}."""
    rs, rows = ranges_for(end, hs), install_days(end, hs)
    calls, todo = 0, list(rs)
    while todo:
        g = next_group(todo, rows, k)
        todo = todo[len(g):]
        calls += 1
    rd = sum(_days_of(rg) for rg in rs)
    return {"windows": len(rs) - 1, "months": months_for(end, hs), "ranges": len(rs), "calls": calls,
            "range_days": rd, "install_days": rows, "units": rd * rows, "tokens_est": int(round(k * rd * rows))}


def request_body(group, total=True):
    """One runReport: these named date ranges, users by first-session day (Ga4App adds the stream filter, the quota
    flag, limit / offset and the order)."""
    body = {"dateRanges": [dict(gu._rng(a, b), name=n) for n, a, b in group],
            "dimensions": ga4._dim("firstSessionDate"), "metrics": ga4._dim("activeUsers")}
    if total:
        body["metricAggregations"] = ["TOTAL"]
    return body


# ── quota ───────────────────────────────────────────────────────────────────────────────────────────

def new_prop():
    """One property's shared state for a run: its latest quota snapshot and why it stopped."""
    return {"quota": None, "stop": None}


def quota_stop(q):
    """The build's gate on the property's last quota snapshot → a reason, or None to go on: any bucket under 10%
    (gu._quota_low, the Uninstall fetch's own stop), an hourly token bucket under HOUR_FLOOR, or ≤ COUNT_FLOOR
    server-error / potentially-thresholded requests left this hour."""
    if gu._quota_low(q):
        return "quota_low"
    if gu._hour_low(q, HOUR_FLOOR):
        return "hour_low"
    for k, floor in COUNT_FLOOR.items():
        b = (q or {}).get(k) or {}
        if "remaining" in b and _int(b["remaining"]) <= floor:
            return "count_low"
    return None


FLOORS = {"tokensPerHour": HOUR_FLOOR, "tokensPerProjectPerHour": HOUR_FLOOR, "tokensPerDay": DAY_FLOOR}


def fits(q, est, floors=None):
    """Does a call's token estimate leave every token bucket of the last snapshot above its floor (FLOORS)?"""
    for k, floor in (floors or FLOORS).items():
        b = (q or {}).get(k) or {}
        if "remaining" in b:
            left = _int(b["remaining"])
            total = max(gu.QUOTA_CAP[k], _int(b.get("consumed")) + left)
            if left - est < floor * total:
                return False
    return True


class App(ga4.Ga4App):
    """ga4.Ga4App (stream-pinned, paged, returnPropertyQuota) whose every call first passes its PROPERTY's gate, the
    run's clock and the call's own estimate (self.est must fit — raises Stop), and which counts tokens (tokensPerDay
    consumed) and units (the estimate's) and keeps each read's metadata + TOTAL. over() → a reason to stop the run (or
    None); tick() → called once per call (a heartbeat); gate(quota) → a reason; floors → fits()'s floors."""

    def __init__(self, token, property_id, stream_id, prop=None, over=None, tick=None, gate=quota_stop, floors=None):
        super().__init__(token, property_id, stream_id)
        self.prop = new_prop() if prop is None else prop
        self.over, self.tick, self.gate, self.floors = over, tick, gate, floors
        self.tok, self.units, self.est, self.no_total, self.split_reads = 0, 0, 0, False, 0
        self.begin()

    def begin(self):
        """A new read: its metadata (OR over its pages) and its TOTAL rows (the first page's)."""
        self.meta = {"thresh": False, "loss_other": False, "sampled": False}
        self.totals = None

    def _post(self, method, body):
        p = self.prop
        if p["stop"]:
            raise Stop(p["stop"])
        why = self.over() if self.over else None
        if why:
            raise Stop(why)
        why = self.gate(p["quota"]) if self.gate else None
        if why:
            p["stop"] = why
            raise Stop(why)
        if self.est and p["quota"] and not fits(p["quota"], self.est, self.floors):
            raise Stop("quota_est")                     # this call would take a bucket under its floor: next run
        if self.tick:
            self.tick()
        try:
            j = super()._post(method, body)
        except RuntimeError as e:
            if str(e).startswith("HTTP 429") or "RESOURCE_EXHAUSTED" in str(e):
                p["stop"] = "quota_429"
            raise
        p["quota"] = j.get("propertyQuota") or p["quota"]
        self.tok += _int(((j.get("propertyQuota") or {}).get("tokensPerDay") or {}).get("consumed"))
        m = j.get("metadata") or {}
        self.meta["thresh"] |= bool(m.get("subjectToThresholding"))
        self.meta["loss_other"] |= bool(m.get("dataLossFromOtherRow"))
        self.meta["sampled"] |= bool(m.get("samplingMetadatas"))
        if self.totals is None and j.get("totals"):
            self.totals = ga4._rows({"dimensionHeaders": j.get("dimensionHeaders"),
                                     "metricHeaders": j.get("metricHeaders"), "rows": j.get("totals")})
        return j


# ── reading ─────────────────────────────────────────────────────────────────────────────────────────

def parse(rows, totals, group, meta=None, truncated=False):
    """One read's rows (+ its TOTAL rows) → {range name: {by {install day ISO: actives}, other, not_set, total, rows,
    bad, thresh, loss_other, sampled, truncated}}. GA4 adds the dateRange dimension only for 2+ ranges: a single range's
    rows carry none. A row of an unknown range or an install day after the range's end is counted bad, never placed."""
    names = [n for n, _, _ in group]
    ends = {n: b for n, _, b in group}
    sole = names[0] if len(names) == 1 else None
    meta = meta or {}
    out = {n: {"by": {}, "other": 0, "not_set": 0, "total": None, "rows": 0, "bad": 0,
               "thresh": bool(meta.get("thresh")), "loss_other": bool(meta.get("loss_other")),
               "sampled": bool(meta.get("sampled")), "truncated": bool(truncated)} for n in names}
    for r in rows:
        n = r.get("dateRange") or sole
        o = out.get(n)
        if o is None:
            continue
        o["rows"] += 1
        f, a = str(r.get("firstSessionDate") or ""), _int(r.get("activeUsers"))
        if f == "(other)":
            o["other"] += a
            continue
        d = ga4._d(f)
        if d is None:
            o["not_set"] += a
            continue
        if d > ends[n]:
            o["bad"] += a
            continue
        o["by"][d.isoformat()] = o["by"].get(d.isoformat(), 0) + a
    for t in totals or []:
        n = t.get("dateRange") or sole
        if n in out:
            out[n]["total"] = _int(t.get("activeUsers"))
    return out


def read(ga, group, extra=None):
    """One request (every page) for these ranges → parse(). TOTAL refused (a 400) → asked without it, for this app's
    other reads too (ga.no_total). 2+ ranges that needed more than one page → asked again one range per request."""
    ga.begin()
    try:
        rows = ga.report_all(request_body(group, not ga.no_total), extra=extra, page_rows=PAGE_ROWS)
    except RuntimeError as e:
        if ga.no_total or not str(e).startswith("HTTP 400"):
            raise
        ga.no_total = True
        ga.begin()
        rows = ga.report_all(request_body(group, False), extra=extra, page_rows=PAGE_ROWS)
    if (ga.last_pages or 0) > 1 and len(group) > 1:
        ga.split_reads += 1
        out = {}
        for rg in group:
            out.update(read(ga, [rg], extra))
        return out
    return parse(rows, ga.totals, group, ga.meta, ga.truncated(rows))


def _counted(ga, group, rows, k, extra=None, as_days=None):
    """read() with this call's estimate set (the gate) and its units counted once the read went through."""
    days = as_days if as_days is not None else sum(_days_of(rg) for rg in group)
    ga.est = k * days * rows
    res = read(ga, group, extra)
    ga.units += days * rows
    return res


# ── the partial read (resumable) ────────────────────────────────────────────────────────────────────

def new_partial(end, hs, property_id, stream_id, now_iso):
    """A read of one final day E, frozen until it completes."""
    ms = months_for(end, hs)
    return {"E": end.isoformat(), "history_start": hs.isoformat(), "property_id": str(property_id),
            "stream_id": str(stream_id), "months": ms, "windows": [window_days(m) for m in ms], "ranges": {},
            "slicing": {}, "calls": 0, "tokens": 0, "units": 0, "runs": 0, "started_at": now_iso, "updated_at": now_iso}


def progress(part):
    """{done, total, slicing} ranges of a partial read."""
    total = len(part.get("windows") or []) + 1
    return {"done": len(part.get("ranges") or {}), "total": total, "slicing": len(part.get("slicing") or {})}


def _spans(hs, end, size=None):
    """[hs, end] in near-equal spans of ≤ size (IN_LIST_MAX) days → [[from ISO, to ISO], …]."""
    size = size or IN_LIST_MAX
    days = gu._days(hs, end)
    n = max(1, -(-len(days) // size))
    step = -(-len(days) // n)
    return [[days[i].isoformat(), days[min(i + step, len(days)) - 1].isoformat()] for i in range(0, len(days), step)]


def _acc():
    return {"by": {}, "other": 0, "bad": 0, "thresh": False, "loss_other": False, "sampled": False,
            "truncated": False}


def _slice_step(ga, part, name, rg, k, rows):
    """One slice of an "(other)" re-ask (resumable: the slicing state lives in the partial)."""
    s = part["slicing"][name]
    lo, hi = s["todo"][0]
    days = gu._days(_d(lo), _d(hi))
    r = _counted(ga, [rg], rows, k, extra=[ga4._in_list("firstSessionDate", [d.strftime("%Y%m%d") for d in days])],
                 as_days=_days_of(rg))                 # estimated like the whole range (see TOKENS)
    s["todo"].pop(0)
    s["reads"] += 1
    if (r[name]["other"] or r[name]["loss_other"]) and len(days) > IN_LIST_MIN:
        mid = days[len(days) // 2 - 1].isoformat()
        s["todo"][:0] = [[lo, mid], [(_d(mid) + timedelta(days=1)).isoformat(), hi]]
        s["halved"] += 1
    else:
        a, p = s["acc"], r[name]
        for x, u in p["by"].items():
            a["by"][x] = a["by"].get(x, 0) + u
        a["other"] += p["other"] + p["not_set"]         # inList can't match "(not set)": anything else is "(other)"
        a["bad"] += p["bad"]
        for f in ("thresh", "loss_other", "sampled", "truncated"):
            a[f] = a[f] or p[f]
    if not s["todo"]:
        f, a = s["first"], s["acc"]
        lo_h, hi_h = part["history_start"], part["E"]
        by = {x: u for x, u in f["by"].items() if not lo_h <= x <= hi_h}
        by.update(a["by"])
        part["ranges"][name] = dict(f, by=by, other_first=f["other"], other=a["other"], loss_other=a["loss_other"],
                                    bad=f["bad"] + a["bad"], thresh=f["thresh"] or a["thresh"],
                                    sampled=f["sampled"] or a["sampled"], truncated=f["truncated"] or a["truncated"],
                                    sliced=s["reads"], halved=s["halved"])
        del part["slicing"][name]


def advance(ga, part, k=PRIOR_K, max_calls=MAX_CALLS):
    """Read on: "(other)" slices under way first, then the next call of ranges not read yet → True once every range is
    done. Raises Stop (quota, budget, the call cap) or the read's error — every finished call is already in `part`."""
    end, hs = _d(part["E"]), _d(part["history_start"])
    rs = ranges_for(end, hs, part["months"])
    by_name = {rg[0]: rg for rg in rs}
    rows = install_days(end, hs)
    while True:
        slicing = [n for n, _, _ in rs if n in part["slicing"]]
        todo = [rg for rg in rs if rg[0] not in part["ranges"] and rg[0] not in part["slicing"]]
        if not slicing and not todo:
            return True
        if ga.calls >= max_calls:
            raise Stop("calls")
        t0, c0, u0 = ga.tok, ga.calls, ga.units
        try:
            if slicing:
                _slice_step(ga, part, slicing[0], by_name[slicing[0]], k, rows)
                continue
            group = next_group(todo, rows, k)
            res = _counted(ga, group, rows, k)
            any_row = any(r["other"] for r in res.values())
            for n, r in res.items():
                if r["other"] or (r["loss_other"] and not any_row):
                    part["slicing"][n] = {"first": r, "todo": _spans(hs, end), "acc": _acc(), "reads": 0, "halved": 0}
                else:
                    part["ranges"][n] = r
        finally:
            part["calls"] += ga.calls - c0
            part["tokens"] += ga.tok - t0
            part["units"] += ga.units - u0


def complete(part):
    """A partial read whose every range is done → the store's top-level (complete) fields."""
    end, hs = _d(part["E"]), _d(part["history_start"])
    rs = ranges_for(end, hs, part["months"])
    res = part["ranges"]
    names = [n for n, _, _ in rs if n != DAU]
    by = {}
    for i, n in enumerate(names):
        for x, u in res[n]["by"].items():
            by.setdefault(x, [0] * len(names))[i] = u
    cov = {}
    for n in names:
        r = res[n]
        if r["total"] and r["total"] >= COV_MIN_USERS:
            c = (sum(r["by"].values()) + r["other"] + r["not_set"]) / r["total"]
            if not COV_LO <= c <= COV_HI:
                cov[n] = round(c, 4)
    every = [n for n, _, _ in rs]

    def which(key):
        return [n for n in every if res[n].get(key)]
    d = res[DAU]
    return {"complete": True, "E": part["E"], "history_start": part["history_start"], "months": list(part["months"]),
            "windows": list(part["windows"]), "by_fsd": by,
            "total": [res[n]["total"] for n in names], "other": [res[n]["other"] for n in names],
            "not_set": [res[n]["not_set"] for n in names],
            "dau_by_fsd": dict(d["by"]), "dau": {"total": d["total"], "other": d["other"], "not_set": d["not_set"]},
            "flags": {"thresholded": which("thresh"), "other": which("other"), "loss_other": which("loss_other"),
                      "other_first": {n: res[n]["other_first"] for n in every if res[n].get("other_first")},
                      "sliced": {n: res[n]["sliced"] for n in every if res[n].get("sliced")},
                      "sampled": which("sampled"), "truncated": which("truncated"), "cov_off": cov,
                      "rows": sum(res[n]["rows"] for n in every), "bad_users": sum(res[n]["bad"] for n in every)},
            "calls": part["calls"], "tokens": part["tokens"], "units": part["units"], "runs": part["runs"],
            "started_at": part["started_at"]}


TOP = ("complete", "E", "history_start", "months", "windows", "by_fsd", "total", "other", "not_set", "dau_by_fsd", "dau",
       "flags", "calls", "tokens", "units", "runs", "started_at", "fetched_at")


def step(ga, store, end, hs, route, now_iso, k=PRIOR_K, max_calls=MAX_CALLS, roll=True):
    """One app's turn, in place on `store` (its saved dict, or {} for a new one) → "fresh" (nothing to read), "fetched"
    (a read completed this turn) or raises Stop / an error with every finished call kept in store["partial"]. A partial
    of another stream is dropped; a partial is finished on ITS E before anything else; a complete store older than E
    (or of another stream or history start) starts a new partial — and roll=True starts it right after finishing an
    older one, in the same turn."""
    pid, sid = str(route["property_id"]), str(route["stream_id"])
    store.setdefault("v", STORE_V)
    if store.get("v") != STORE_V or (store.get("complete") and (str(store.get("property_id")),
                                                                 str(store.get("stream_id"))) != (pid, sid)):
        for f in TOP + ("partial",):
            store.pop(f, None)
        store["v"] = STORE_V
    part = store.get("partial")
    if part and (part.get("property_id"), part.get("stream_id")) != (pid, sid):
        part = store["partial"] = None
    done = None
    while True:
        if not part:
            if store.get("complete") and _d(store["E"]) >= end and store.get("history_start") == hs.isoformat():
                return done or "fresh"
            if done and not roll:
                return done
            part = store["partial"] = new_partial(end, hs, pid, sid, now_iso)
        part["runs"] += 1
        part["updated_at"] = now_iso
        advance(ga, part, k, max_calls)
        for f in TOP:
            store.pop(f, None)
        store.update(complete(part), property_id=pid, stream_id=sid, fetched_at=now_iso)
        store.pop("partial", None)
        part, done = None, "fetched"
        if not roll:
            return done


def fetch_app(ga, end, hs, max_calls=10 ** 6, k=PRIOR_K):
    """A whole read of one app in one go → its complete store fields (no ids). Raises instead of a partial."""
    part = new_partial(end, hs, ga.property_id, ga.stream_id, None)
    advance(ga, part, k, max_calls)
    return complete(part)


def measured_k(ga, old=None):
    """The app's tokens per unit from this turn's calls (its old k when none were measured)."""
    return round(ga.tok / ga.units, 9) if ga.units and ga.tok else old


def flag_summary(store):
    """A store's flags → the few booleans the counts (and state) carry."""
    f = (store or {}).get("flags") or {}
    s = {"other": bool(f.get("other")), "thresholded": bool(f.get("thresholded")), "cov_off": bool(f.get("cov_off")),
         "sampled": bool(f.get("sampled")), "truncated": bool(f.get("truncated")),
         "no_total": bool(f.get("no_total"))}
    s["flagged"] = any(s.values())
    return s


# ── store + state files ─────────────────────────────────────────────────────────────────────────────

def store_path(data_dir, app_id):
    return os.path.join(data_dir, DIR, gu.file_key(app_id) + ".json.gz")


def load_store(path):
    return gu.load_store(path)


def save_store(path, store):
    return write_json_gz_stable(path, store)


def store_meta(store):
    """What plan() needs — kept in state, so planning never opens a store."""
    if not store:
        return None
    m = {k: store.get(k) for k in ("v", "complete", "E", "history_start", "property_id", "stream_id")}
    p = store.get("partial")
    if p:
        m.update(partial_E=p.get("E"), partial_stream=[p.get("property_id"), p.get("stream_id")],
                 partial_progress=progress(p))
    return m


def load_state(data_dir):
    """The private Audience state ({"v", "fetch": {app id: …}}); an empty one on a missing or broken file."""
    st = {"v": 1, "fetch": {}}
    try:
        with open(os.path.join(data_dir, DIR, "state.json"), encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict) and isinstance(raw.get("fetch"), dict):
            st["fetch"] = raw["fetch"]
    except Exception:
        pass
    return st


def save_state(data_dir, state):
    """Plain JSON, sorted keys, written only when it changed. → True when written."""
    path = os.path.join(data_dir, DIR, "state.json")
    text = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=1)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(path + ".tmp", path)
    return True


# ── the build's run ─────────────────────────────────────────────────────────────────────────────────

def plan(app_st, meta, uni_meta, route, end, now, retry_hours=RETRY_HOURS):
    """"continue" (a partial read of this stream is under way), "fetch" (a new read is due) or None for one app this
    run. meta = its Audience store's store_meta (None: no store); uni_meta = its Uninstall store's (gu.store_meta). A
    complete store is due once a newer final day E exists — at most once a day; a failed app waits retry_hours."""
    if app_st.get("fail") and gu._hours_since(app_st.get("last_try"), now) < retry_hours:
        return None
    if not meta or _int(meta.get("v")) != STORE_V:
        return "fetch"
    here = [str(route.get("property_id")), str(route.get("stream_id"))]
    if meta.get("partial_E") and [str(v) for v in meta.get("partial_stream") or []] == here:
        return "continue"
    if not meta.get("complete") or [str(meta.get("property_id")), str(meta.get("stream_id"))] != here:
        return "fetch"
    if meta.get("history_start") != (uni_meta or {}).get("history_start"):
        return "fetch"                                  # the windows must reach the Uninstall history's first day
    if not meta.get("E") or _d(meta["E"]) < end:
        return "fetch"
    return None


COUNTS = ("selected", "with_ga4", "fetched", "partial", "fresh", "failed", "deferred", "waiting", "calls", "tokens",
          "flagged", "other", "thresholded", "cov_off")


def _uni_meta(ust, data_dir, aid, route):
    """The app's Uninstall store meta when that store exists and is of the routed stream with a history (else None)."""
    if not os.path.exists(gu.store_path(data_dir, aid)):
        return None
    m = (ust["fetch"].get(aid) or {}).get("meta")
    if not m:
        m = gu.store_meta(gu.load_store(gu.store_path(data_dir, aid)))
    if not m or not m.get("history_start"):
        return None
    if (str(m.get("property_id")), str(m.get("stream_id"))) != (str(route["property_id"]), str(route["stream_id"])):
        return None
    return m


def refresh_all(cfg, data_dir, apps, now=None, clock=time.monotonic, budget=BUDGET_SEC):
    """Read on for every selected app (`apps` = uninstall_build's list; an app without a package or sharing another's
    is skipped) → {"counts": COUNTS, "apps": {app id: fetched|partial|fresh|failed|deferred|waiting}} (partial: read on,
    not complete yet). Reads the Uninstall state's routes and timezones and each app's Uninstall store meta (never
    writes them). Never raises; never prints."""
    now = now or datetime.now(timezone.utc)
    t0 = clock()
    counts = dict.fromkeys(COUNTS, 0)
    out = {"counts": counts, "apps": {}}
    fetched = []
    try:
        state = load_state(data_dir)
        ust = gu.load_state(data_dir)
        routes = ust["routes"].get("by_package") or {}
        tokens, _ = ga4_probe.owner_tokens({"GA4_REFRESH_TOKENS": cfg.get("refresh_tokens") or "",
                                            "GA4_REFRESH_TOKEN": cfg.get("refresh_token") or ""})
        owner_rt, access = dict(tokens), {}
        retry = float(cfg.get("retry_hours") or RETRY_HOURS)
        todo = []
        for a in apps:
            if a.get("same_as") or not a.get("package"):
                continue
            counts["selected"] += 1
            r = routes.get(a["package"])
            if not r:
                continue
            counts["with_ga4"] += 1
            aid = a["app_id"]
            st = state["fetch"].setdefault(aid, {})
            um = _uni_meta(ust, data_dir, aid, r)
            tz = ust["tz"].get(r["property_id"]) or (um or {}).get("time_zone") or "UTC"
            end = final_end(tz, now)
            if not um or _d(um["history_start"]) > end:
                out["apps"][aid] = "waiting"            # no Uninstall store of this stream yet / no final day yet
                continue
            meta = st.get("meta") if os.path.exists(store_path(data_dir, aid)) else None
            kind = plan(st, meta, um, r, end, now, retry)
            if kind is None:
                out["apps"][aid] = "failed" if st.get("fail") else "fresh"
                continue
            todo.append((kind, a, st, r, tz, end, _d(um["history_start"])))
        # reads under way first (finish before anything new), then last run's deferred, then the longest unfetched
        todo.sort(key=lambda t: (t[0] != "continue", not t[2].get("deferred"), t[2].get("last_ok") is not None,
                                 t[2].get("last_ok") or "", t[1]["app_id"]))
        props = {}

        def over():
            return "budget" if clock() - t0 >= 2 * budget else None
        for kind, a, st, r, tz, end, hs in todo:
            aid, pid = a["app_id"], r["property_id"]
            prop = props.setdefault(pid, new_prop())
            if clock() - t0 >= budget or prop["stop"]:
                st["deferred"] = True
                out["apps"][aid] = "deferred"
                continue
            owner = r.get("owner")
            if owner not in access:
                try:
                    access[owner] = (ga4.access_token(cfg["client_id"], cfg["client_secret"], owner_rt[owner])
                                     if owner in owner_rt else None)
                except Exception:
                    access[owner] = None
            now_iso = gu._now_iso(now)
            if not access.get(owner):
                st.update(last_try=now_iso, fail="auth", fail_detail={"type": "token"})
                out["apps"][aid] = "failed"
                continue
            ga = App(access[owner], pid, r["stream_id"], prop, over=over)
            path = store_path(data_dir, aid)
            store = (load_store(path) or {}) if os.path.exists(path) else {}
            try:
                res = step(ga, store, end, hs, r, now_iso, float(st.get("k") or PRIOR_K))
                st.pop("deferred", None)
                st.pop("stopped", None)
                st.update(last_try=now_iso, fail=None, fail_detail=None)
                if res == "fetched":
                    st.update(last_ok=now_iso, flags=flag_summary(store))
                    fetched.append(st["flags"])
                out["apps"][aid] = res
            except Stop as e:                           # quota / budget / call cap: what was read stays, next run on
                st.update(deferred=True, stopped=str(e))
                out["apps"][aid] = "partial" if ga.calls else "deferred"
            except Exception as e:
                fk = gu._fail_kind(e)
                st.update(last_try=now_iso, fail=fk, fail_detail=_err(e))
                if fk == "quota":
                    prop["stop"] = prop["stop"] or "quota"
                out["apps"][aid] = "failed"
            finally:
                if ga.calls or store.get("partial"):
                    store.update(app_id=aid, package=a["package"], time_zone=tz)
                    save_store(path, store)
                if store:
                    st["meta"] = store_meta(store)
                st["key"] = gu.file_key(aid)
                st["k"] = measured_k(ga, st.get("k"))
                if ga.calls:
                    st.update(calls=ga.calls, tokens=ga.tok)
                counts["calls"] += ga.calls
                counts["tokens"] += ga.tok
                store = None
        save_state(data_dir, state)
    except Exception as e:                              # a bug here must never cost the build
        out["error"] = type(e).__name__
    for v in out["apps"].values():
        counts[v] += 1
    for f in fetched:
        for k in ("flagged", "other", "thresholded", "cov_off"):
            counts[k] += bool(f.get(k))
    return out


def log_line(status):
    """The build log's ONE line for this step — counts only (no names, ids, dates or user numbers)."""
    c = (status or {}).get("counts") or {}
    n = _int(c.get("fetched")) + _int(c.get("partial"))
    line = ("ga4 audience: apps %d, with GA4 %d, fetched %d, partial %d, fresh %d, failed %d, deferred %d, waiting %d, "
            "calls %d, tokens %d (~%d per app read), flagged %d (other %d, thresholded %d, coverage off %d)"
            % tuple([_int(c.get(k)) for k in ("selected", "with_ga4", "fetched", "partial", "fresh", "failed",
                                              "deferred", "waiting", "calls", "tokens")]
                    + [_int(c.get("tokens")) // n if n else 0]
                    + [_int(c.get(k)) for k in ("flagged", "other", "thresholded", "cov_off")]))
    if (status or {}).get("error"):
        line += ", error %s" % status["error"]
    return line
