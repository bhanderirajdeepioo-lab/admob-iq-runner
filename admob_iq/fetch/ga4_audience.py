"""GA4 → per-app Audience store (data/ga4_audience/<key>.json.gz): for every install day, how many of its users were
active in each trailing window of 1, 2, 3 … months — straight from GA4, no app-side module. engine.audience turns it
(with the Uninstall store's installs and uninstalls) into "dead users by months since their last open".

THE REQUEST — the owner's method on the Data API: metric activeUsers, dimension firstSessionDate, pinned to the app's
Android stream (ga4.Ga4App), over trailing date ranges that all END on E, the latest FINAL activity day:
    E        = ga4_uninstall.settled_end − ACT_LATE_DAYS (today − 2 in the property's timezone from noon, else − 3; GA4
               activity is final 3 days later — the Active users tab's settled_till, the install-value reads' F);
    window N = [E − w_N + 1, E], w_N = floor(N × 30.4375) days (30, 60, 91, 121, …, 365 at N = 12), N = 1, 2, … up to the
               first window that holds the app's whole history (the Uninstall store's history_start);
    "dau"    = E alone: actives on E by install day (today's DAU by install month).
Up to RANGES_PER_CALL (4, the Data API's limit) named date ranges per request (GA4 adds the dateRange dimension), every
row paged (Ga4App.report_all: offset += limit up to rowCount), metricAggregations TOTAL (GA4's own distinct actives of
each range: the split's self-check). A request that needed more than one page with 2+ ranges is asked again range by
range: one dimension is one total order, so offset paging can't repeat or skip a row.

NEVER HIDDEN — flagged in the store:
  * "(other)" rows (GA4 folds what it can't keep into one row) or metadata.dataLossFromOtherRow: the request is asked
    again in slices of IN_LIST_DAYS install days (firstSessionDate inList — the uninstall cells' trick), within
    MAX_CALLS; whatever still sits in "(other)" stays there per window (store "other"), never spread over install days;
  * "(not set)" first-session days (store "not_set"); install days before history_start stay in by_fsd as GA4 gave
    them (engine.audience shows them apart);
  * thresholding (subjectToThresholding: small counts withheld), sampling, a cut report (truncated), TOTAL refused (a
    400: asked without it, no_total), a split whose Σ rows is off TOTAL by more than 5% (cov_off {window: Σ ÷ TOTAL}).

THE STORE (deterministic gzip, rewritten only when its content changes): {v, app_id, package, property_id, stream_id,
time_zone, history_start, E, fetched_at, windows [w_1 …], by_fsd {install day: [actives in window N …]} (0 = no row),
total / other / not_set [per window], dau_by_fsd {install day: actives on E}, dau {total, other, not_set}, flags,
calls, tokens}. Whole or nothing: an app whose reads stop half-way (quota, budget, an error) keeps its old store.

IN THE BUILD (uninstall_build, only with the repo variable GA4_AUDIENCE=true): after the Uninstall fetch, each selected
app with an Uninstall store is read again when a new final day E appears — at most once a day per app; a failed one
waits RETRY_HOURS. Its own run budget (GA4_AUDIENCE_BUDGET_SEC): no app starts past it, a started one stops at 2×.
QUOTA (per property): an app starts only when its token estimate (its last fetch's tokens, else calls ×
TOKENS_PER_CALL_EST) leaves every hourly token bucket above HOUR_FLOOR; every call first checks the last snapshot
(quota_stop) and a 429 stops the property for the run — the Uninstall fetch of the next hour keeps its quota. State
(private): data/ga4_audience/state.json. Nothing here prints: the build log gets ONE counts-only line (log_line).
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone

from . import ga4
from . import ga4_uninstall as gu
from .. import ga4_probe
from ..db import write_json_gz_stable
from ..engine.audience import window_days

DIR = "ga4_audience"
STORE_V = 1                 # the store format: another one is read again in full at the next run
RANGES_PER_CALL = 4         # date ranges per runReport (the Data API's limit)
PAGE_ROWS = 100000          # rows per page (≤ 4 ranges × one row per install day: one page, even at 1,300 days)
IN_LIST_DAYS = 120          # an "(other)" request is asked again in slices of 120 install days (the size the uninstall
                            # cohorts' inList ran live)
MAX_CALLS = 60              # calls per app per fetch at most (a 3.5-year app needs 12; the rest is "(other)" re-asks)
HOUR_FLOOR = 0.5            # an app starts only if its estimate leaves each hourly token bucket ≥ half; a call stops
                            # under half (the install-value backfill's own floor)
COUNT_FLOOR = {"serverErrorsPerProjectPerHour": 4, "potentiallyThresholdedRequestsPerHour": 5}
COV_LO, COV_HI = 0.95, 1.05  # Σ rows ÷ GA4's TOTAL outside this → cov_off (user counts are sketches: ±1–2% is noise)
COV_MIN_USERS = 200         # (a window with fewer actives is not judged)
TOKENS_PER_CALL_EST = 25    # a-priori tokens per call before an app's first fetch (then its own measured tokens)
BUDGET_SEC = 180            # the build's own budget for this step
RETRY_HOURS = 3.0           # a failed app waits this long
DAU = "dau"


class Stop(Exception):
    """The app's reads stop here: the property's quota, a 429, or the run's budget. Its old store stays."""


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


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


# ── the plan: windows, ranges, requests ─────────────────────────────────────────────────────────────

def final_end(tz_name, now):
    """E, the latest FINAL activity day: the robot's settled day (gu.settled_end) − ACT_LATE_DAYS."""
    return gu.settled_end(tz_name, now) - timedelta(days=gu.ACT_LATE_DAYS)


def windows_for(end, hs):
    """Window lengths (days) for N = 1, 2, … up to the first window holding every install day since `hs`."""
    age, out, n = (end - hs).days + 1, [], 1
    while True:
        out.append(window_days(n))
        if out[-1] >= age:
            return out
        n += 1


def ranges_for(end, hs):
    """[(name, start, end)]: "dau" (E alone), then "w<days>" for every window — all ending on E."""
    return [(DAU, end, end)] + [("w%d" % w, end - timedelta(days=w - 1), end) for w in windows_for(end, hs)]


def groups(rs, k=RANGES_PER_CALL):
    return [rs[i:i + k] for i in range(0, len(rs), k)]


def request_body(group, total=True):
    """One runReport: these named date ranges, users by first-session day (Ga4App adds the stream filter, the quota
    flag, limit / offset and the order)."""
    body = {"dateRanges": [dict(gu._rng(a, b), name=n) for n, a, b in group],
            "dimensions": ga4._dim("firstSessionDate"), "metrics": ga4._dim("activeUsers")}
    if total:
        body["metricAggregations"] = ["TOTAL"]
    return body


def plan_calls(end, hs, per_call=TOKENS_PER_CALL_EST):
    """One app's request plan → {windows, ranges, calls, range_days (Σ days the ranges cover), tokens_est}."""
    rs = ranges_for(end, hs)
    n = len(groups(rs))
    return {"windows": len(rs) - 1, "ranges": len(rs), "calls": n,
            "range_days": sum((b - a).days + 1 for _, a, b in rs), "tokens_est": n * per_call}


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


def fits(q, est):
    """Does an app's token estimate leave every hourly token bucket (of the last snapshot) above HOUR_FLOOR?"""
    for k in ("tokensPerHour", "tokensPerProjectPerHour"):
        b = (q or {}).get(k) or {}
        if "remaining" in b:
            left = _int(b["remaining"])
            total = max(gu.QUOTA_CAP[k], _int(b.get("consumed")) + left)
            if left - est < HOUR_FLOOR * total:
                return False
    return True


class App(ga4.Ga4App):
    """ga4.Ga4App (stream-pinned, paged, returnPropertyQuota) whose every call first passes its PROPERTY's gate and the
    run's clock (raises Stop), and which counts tokens (tokensPerDay consumed) and keeps each read's metadata + TOTAL.
    over() → a reason to stop the run (or None); tick() → called once per call (a heartbeat); gate(quota) → a reason."""

    def __init__(self, token, property_id, stream_id, prop=None, over=None, tick=None, gate=quota_stop):
        super().__init__(token, property_id, stream_id)
        self.prop = new_prop() if prop is None else prop
        self.over, self.tick, self.gate = over, tick, gate
        self.tok, self.no_total, self.split_reads = 0, False, 0
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


def _in_slices(hs, end):
    days = gu._days(hs, end)
    return [days[i:i + IN_LIST_DAYS] for i in range(0, len(days), IN_LIST_DAYS)]


def read_group(ga, group, hs, end, flags, max_calls=MAX_CALLS):
    """read() one group; when any of its ranges has "(other)" users or GA4's dataLossFromOtherRow, the group is asked
    again in slices of IN_LIST_DAYS install days (hs..end, firstSessionDate inList) — if the app's call cap allows —
    and those slices replace its install days; days outside them (before hs) and "(not set)" stay from the first read,
    its TOTAL too (other_first: what "(other)" held before). Without the room, the first read is kept, flagged."""
    res = read(ga, group)
    if not any(r["other"] or r["loss_other"] for r in res.values()):
        return res
    slices = _in_slices(hs, end)
    if ga.calls + len(slices) > max_calls:
        flags["other_kept"] += 1
        return res
    again = {n: {"by": {}, "other": 0, "thresh": False, "loss_other": False, "sampled": False, "truncated": False,
                 "bad": 0} for n, _, _ in group}
    for sl in slices:
        part = read(ga, group, extra=[ga4._in_list("firstSessionDate", [d.strftime("%Y%m%d") for d in sl])])
        for n, p in part.items():
            a = again[n]
            for x, u in p["by"].items():
                a["by"][x] = a["by"].get(x, 0) + u
            a["other"] += p["other"] + p["not_set"]      # inList can't match "(not set)": anything else is "(other)"
            a["bad"] += p["bad"]
            for f in ("thresh", "loss_other", "sampled", "truncated"):
                a[f] = a[f] or p[f]
    lo, hi = hs.isoformat(), end.isoformat()
    for n, r in res.items():
        a = again[n]
        by = {x: u for x, u in r["by"].items() if not lo <= x <= hi}
        by.update(a["by"])
        r.update(by=by, other_first=r["other"], other=a["other"], loss_other=a["loss_other"], bad=r["bad"] + a["bad"],
                 thresh=r["thresh"] or a["thresh"], sampled=r["sampled"] or a["sampled"],
                 truncated=r["truncated"] or a["truncated"])
    flags["other_reasked"] += 1
    return res


def fetch_app(ga, end, hs, max_calls=MAX_CALLS):
    """Every window + the DAU day of one app → its store (without the app's ids — refresh_all / the probe add them).
    Raises (Stop, or the read's error) instead of returning a partial store."""
    rs = ranges_for(end, hs)
    flags = {"other_reasked": 0, "other_kept": 0}
    res = {}
    for g in groups(rs):
        res.update(read_group(ga, g, hs, end, flags, max_calls))
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
    return {"v": STORE_V, "E": end.isoformat(), "history_start": hs.isoformat(),
            "windows": [int(n[1:]) for n in names], "by_fsd": by,
            "total": [res[n]["total"] for n in names], "other": [res[n]["other"] for n in names],
            "not_set": [res[n]["not_set"] for n in names],
            "dau_by_fsd": dict(d["by"]), "dau": {"total": d["total"], "other": d["other"], "not_set": d["not_set"]},
            "flags": {"thresholded": which("thresh"), "other": which("other"), "loss_other": which("loss_other"),
                      "other_first": {n: res[n]["other_first"] for n in every if res[n].get("other_first")},
                      "sampled": which("sampled"), "truncated": which("truncated"), "cov_off": cov,
                      "no_total": ga.no_total, "split_reads": ga.split_reads, "rows": sum(res[n]["rows"] for n in every),
                      "bad_users": sum(res[n]["bad"] for n in every), **flags},
            "calls": ga.calls, "tokens": ga.tok}


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
    return {k: store.get(k) for k in ("v", "E", "history_start", "property_id", "stream_id")}


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
    """"fetch" or None for one app this run. meta = its Audience store's store_meta (None: no store); uni_meta = its
    Uninstall store's (gu.store_meta). Due when there is no store (or another format / stream / history start) or a
    newer final day E exists — so at most once a day; a failed app waits retry_hours."""
    if app_st.get("fail") and gu._hours_since(app_st.get("last_try"), now) < retry_hours:
        return None
    if not meta or _int(meta.get("v")) != STORE_V:
        return "fetch"
    if (str(meta.get("property_id")), str(meta.get("stream_id"))) != (str(route.get("property_id")),
                                                                       str(route.get("stream_id"))):
        return "fetch"
    if meta.get("history_start") != (uni_meta or {}).get("history_start"):
        return "fetch"                                  # the windows must reach the Uninstall history's first day
    if not meta.get("E") or gu._d(meta["E"]) < end:
        return "fetch"
    return None


COUNTS = ("selected", "with_ga4", "fetched", "fresh", "failed", "deferred", "waiting", "calls", "tokens", "flagged",
          "other", "thresholded", "cov_off")


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
    """Fetch what is due for every selected app (`apps` = uninstall_build's list; an app without a package or sharing
    another's is skipped) → {"counts": COUNTS, "apps": {app id: fetched|fresh|failed|deferred|waiting}}. Reads the
    Uninstall state's routes and timezones and each app's Uninstall store meta (never writes them). Never raises;
    never prints."""
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
            if not um or gu._d(um["history_start"]) > end:
                out["apps"][aid] = "waiting"            # no Uninstall store of this stream yet / no final day yet
                continue
            meta = st.get("meta") if os.path.exists(store_path(data_dir, aid)) else None
            if plan(st, meta, um, r, end, now, retry) is None:
                out["apps"][aid] = "failed" if st.get("fail") else "fresh"
                continue
            todo.append((a, st, r, tz, end, gu._d(um["history_start"])))
        # last run's deferred first, then the longest unfetched
        todo.sort(key=lambda t: (not t[1].get("deferred"), t[1].get("last_ok") is not None, t[1].get("last_ok") or "",
                                 t[0]["app_id"]))
        props = {}

        def over():
            return "budget" if clock() - t0 >= 2 * budget else None
        for a, st, r, tz, end, hs in todo:
            aid, pid = a["app_id"], r["property_id"]
            prop = props.setdefault(pid, new_prop())
            est = _int(st.get("tokens")) or plan_calls(end, hs)["tokens_est"]
            if clock() - t0 >= budget or prop["stop"] or not fits(prop["quota"], est):
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
            try:
                store = fetch_app(ga, end, hs)
                store.update(app_id=aid, package=a["package"], property_id=str(pid), stream_id=str(r["stream_id"]),
                             time_zone=tz, fetched_at=now_iso)
                save_store(store_path(data_dir, aid), store)
                st.pop("deferred", None)
                st.pop("stopped", None)
                st.update(key=gu.file_key(aid), last_try=now_iso, last_ok=now_iso, fail=None, fail_detail=None,
                          calls=ga.calls, tokens=ga.tok, meta=store_meta(store), flags=flag_summary(store))
                out["apps"][aid] = "fetched"
                fetched.append(st["flags"])
            except Stop as e:                           # quota / budget: the old store stays, next run again
                st.update(deferred=True, stopped=str(e))
                out["apps"][aid] = "deferred"
            except Exception as e:
                fk = gu._fail_kind(e)
                st.update(last_try=now_iso, fail=fk, fail_detail=_err(e))
                if fk == "quota":
                    prop["stop"] = prop["stop"] or "quota"
                out["apps"][aid] = "failed"
            finally:
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
    n = _int(c.get("fetched"))
    line = ("ga4 audience: apps %d, with GA4 %d, fetched %d, fresh %d, failed %d, deferred %d, waiting %d, calls %d, "
            "tokens %d (~%d per fetched app), flagged %d (other %d, thresholded %d, coverage off %d)"
            % tuple([_int(c.get(k)) for k in ("selected", "with_ga4", "fetched", "fresh", "failed", "deferred",
                                              "waiting", "calls", "tokens")]
                    + [_int(c.get("tokens")) // n if n else 0]
                    + [_int(c.get(k)) for k in ("flagged", "other", "thresholded", "cov_off")]))
    if (status or {}).get("error"):
        line += ", error %s" % status["error"]
    return line
