"""GA4 → per-app uninstall store (data/ga4_uninstall/), fetched inside the hourly build.

Four Data API reports per app, all pinned to the app's Android stream by Ga4App:
  * daily     date → newUsers, activeUsers, active28DayUsers           (installs + the rate denominator)
  * events    date × eventName → totalUsers, eventCount for app_remove / app_update
  * cells     firstSessionDate × date → app_remove users               (the install-cohort churn cells)
  * versions  date × appVersion → activeUsers                          (releases; Step 4 version scorecard)

FULL history on an app's first fetch (as far back as the property has data, ≤ GA4_MAX_HISTORY_DAYS, cells in
90-day slices), then INCREMENTAL: the last GA4_REFETCH_DAYS dates (GA4 keeps adding late data) + any gap,
at most once per GA4_MIN_HOURS per app, and a new day only from noon in the property's timezone (SETTLE_HOUR)
— every other hourly run makes ZERO GA4 calls. A full re-pull every
GA4_REBUILD_DAYS (staggered per app) self-heals anything the incremental merge missed; older days it no
longer returns are KEPT, never trimmed. Every report is paged to the last row; the paging safety cap and
GA4 thresholding are flagged in the store, never silent.

Store files and state.json are deterministic (sorted keys, gzip without a timestamp) and only rewritten
when their content changes, so the private repo's history grows about once a day, not every run.

Nothing here prints, and refresh_all never raises: a failing owner / app is recorded in the PRIVATE state
(state.json, never shipped) and the others carry on. The public build log gets one line of counts from
admob_iq.uninstall_build.
"""

import hashlib
import json
import os
import time
import zlib
from datetime import date, datetime, timedelta, timezone

from . import ga4
from .. import ga4_probe
from ..db import _read_json_any, write_json_gz_stable

FULL_CHUNK_DAYS = 90        # cells report per 90 event-days (~H×90 rows at most — a page or two each)
UNI_PAGE_ROWS = 100000      # rows per Data API page (the API allows 250,000)
FULL_IF_GAP_DAYS = 90       # an incremental window longer than this is a full re-pull instead
REBUILD_MIN_RATIO = 0.5     # a re-pull with < half the installs of what we hold is suspect → keep the old
QUOTA_MIN_FRAC = 0.10       # stop a property's remaining apps when any quota bucket is below 10%
QUOTA_CAP = {"tokensPerDay": 200000, "tokensPerHour": 40000, "tokensPerProjectPerHour": 14000}
                            # standard-property bucket sizes — propertyQuota only says consumed/remaining
SETTLE_HOUR = 12            # the newest day (today−2) is fetched only from noon in the property's timezone: by
                            # then it has had ≥36h of GA4's 24–48h to settle. At 00:47 it has had just 24h, and
                            # a day still filling in reads LOW (a false "achanak kam" / 0-uninstall alert)
STORE_V = 1
DIR = "ga4_uninstall"
EVENTS = ["app_remove", "app_update"]


class NoData(RuntimeError):
    """The stream has no users at all in the window (a brand-new or unused stream)."""


def _now_iso(now):
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _hours_since(s, now):
    t = _parse_iso(s)
    return float("inf") if t is None else (now - t).total_seconds() / 3600


def _d(s):
    return s if isinstance(s, date) else date.fromisoformat(str(s)[:10])


def settled_end(tz_name, now):
    """The newest GA4 day to fetch now: today−2 in the property's timezone once it is SETTLE_HOUR there,
    else today−3 (see SETTLE_HOUR). UTC when the zone is unknown, as ga4.window_end_in."""
    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    end = ga4.window_end_in(tz.key, now)
    return end if now.astimezone(tz).hour >= SETTLE_HOUR else end - timedelta(days=1)


def _days(a, b):
    """Every date a..b inclusive."""
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


# ── store + state files ─────────────────────────────────────────────────────────────────────────

def file_key(app_id):
    return hashlib.sha1(str(app_id).encode("utf-8")).hexdigest()[:12]


def store_path(data_dir, app_id):
    return os.path.join(data_dir, DIR, file_key(app_id) + ".json.gz")


def load_store(path):
    try:
        return _read_json_any(path[:-3] if path.endswith(".gz") else path)
    except Exception:
        return None


def save_store(path, store):
    return write_json_gz_stable(path, store)


def _state_default():
    return {"v": 1, "routes": {"fetched_at": None, "tried_at": None, "by_package": {}, "stream_errors": 0,
                               "owners_failed": 0, "stale": False},
            "tz": {}, "fetch": {}, "eval": {}, "episodes": {}, "closed": []}


def load_state(data_dir):
    """The private uninstall state; an empty default on a missing or broken file — never crashes."""
    st = _state_default()
    try:
        with open(os.path.join(data_dir, DIR, "state.json"), encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k in st and isinstance(v, type(st[k])):
                    st[k] = v
            for k, v in _state_default()["routes"].items():
                st["routes"].setdefault(k, v)
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


# ── the four reports ────────────────────────────────────────────────────────────────────────────

def _rng(start, end):
    return {"startDate": start.isoformat(), "endDate": end.isoformat()}


def rep_daily(ga, start, end, a28=True):
    mets = ["newUsers", "activeUsers"] + (["active28DayUsers"] if a28 else [])
    return ga.report_all({"dateRanges": [_rng(start, end)], "dimensions": ga4._dim("date"),
                          "metrics": ga4._dim(*mets)}, page_rows=UNI_PAGE_ROWS)


def rep_events(ga, start, end):
    return ga.report_all({"dateRanges": [_rng(start, end)], "dimensions": ga4._dim("date", "eventName"),
                          "metrics": ga4._dim("totalUsers", "eventCount")}, events=EVENTS, page_rows=UNI_PAGE_ROWS)


def rep_cells(ga, start, end):
    """app_remove users by install day × event day, for every uninstall with its EVENT date in [start, end]
    (no firstSessionDate filter: old cohorts keep uninstalling). Newest cohorts first, as probe_t13."""
    return ga.report_all({"dateRanges": [_rng(start, end)], "dimensions": ga4._dim("firstSessionDate", "date"),
                          "metrics": ga4._dim("totalUsers"),
                          "orderBys": [{"dimension": {"dimensionName": "firstSessionDate"}, "desc": True},
                                       {"dimension": {"dimensionName": "date"}}]},
                         event="app_remove", page_rows=UNI_PAGE_ROWS)


def rep_versions(ga, start, end):
    return ga.report_all({"dateRanges": [_rng(start, end)], "dimensions": ga4._dim("date", "appVersion"),
                          "metrics": ga4._dim("activeUsers")}, page_rows=UNI_PAGE_ROWS)


def _a28_rejected(e):
    s = str(e)
    return s.startswith("HTTP 400") and "active28DayUsers" in s


def _daily_rows(ga, start, end, den):
    """rep_daily with the denominator fallback: if GA4 rejects active28DayUsers, daily actives it is."""
    if den == "a28":
        try:
            return rep_daily(ga, start, end), "a28"
        except RuntimeError as e:
            if not _a28_rejected(e):
                raise
    return rep_daily(ga, start, end, a28=False), "dau"


def _parse(start, end, den):
    return {"daily": {d.isoformat(): {"new": 0, "a1": 0, "a28": 0 if den == "a28" else None, "un": 0,
                                      "un_ev": 0, "upd": 0} for d in _days(start, end)},
            "cohorts": {}, "unplaced": {}, "versions": {}, "bad_rows": 0}


def _in(p, d):
    return d is not None and d.isoformat() in p["daily"]


def _merge_daily(p, rows):
    for r in rows:
        d = ga4._d(r.get("date"))
        if not _in(p, d):
            p["bad_rows"] += 1
            continue
        e = p["daily"][d.isoformat()]
        e["new"] += int(r.get("newUsers") or 0)
        e["a1"] += int(r.get("activeUsers") or 0)
        if e["a28"] is not None:
            e["a28"] += int(r.get("active28DayUsers") or 0)


def _merge_events(p, rows):
    for r in rows:
        d = ga4._d(r.get("date"))
        if not _in(p, d):
            p["bad_rows"] += 1
            continue
        e = p["daily"][d.isoformat()]
        if r.get("eventName") == "app_remove":
            e["un"] += int(r.get("totalUsers") or 0)
            e["un_ev"] += int(r.get("eventCount") or 0)
        elif r.get("eventName") == "app_update":
            e["upd"] += int(r.get("totalUsers") or 0)


def _place_cells(p, rows, place_from):
    """Cells → cohorts[install day][lag]; a row with no usable install day (not a date, "(other)", before
    the history, or after the event) goes to unplaced[event day] — kept visible, never guessed."""
    for r in rows:
        u = int(r.get("totalUsers") or 0)
        f, d = ga4._d(r.get("firstSessionDate")), ga4._d(r.get("date"))
        if not _in(p, d):
            p["bad_rows"] += u
            continue
        if f is None or f < place_from or f > d:
            p["unplaced"][d.isoformat()] = p["unplaced"].get(d.isoformat(), 0) + u
            continue
        c = p["cohorts"].setdefault(f.isoformat(), {})
        lag = str((d - f).days)
        c[lag] = c.get(lag, 0) + u


def _merge_versions(p, rows):
    for r in rows:
        d = ga4._d(r.get("date"))
        if not _in(p, d):
            p["bad_rows"] += 1
            continue
        v = p["versions"].setdefault(d.isoformat(), {})
        k = str(r.get("appVersion") or "(not set)")
        v[k] = v.get(k, 0) + int(r.get("activeUsers") or 0)


# Per-date reports fetched over the same window as the daily one: (name, report fn, merge fn into the parsed
# window). THE Step 4 extension point — a country / campaign report is one more entry here (plus a key in
# _parse and merge_window) and every full / incremental fetch then carries it.
REPORTS = [("events", rep_events, _merge_events), ("versions", rep_versions, _merge_versions)]


def _fetch_window(ga, start, end, den, place_from, cut, daily=None):
    """daily + REPORTS + cells over [start, end] → parsed window. `cut` collects capped report names.
    `daily` = daily rows already fetched over a window covering [start, end] (rows outside it are skipped)."""
    if daily is None:
        daily, den = _daily_rows(ga, start, end, den)
        if ga.truncated(daily):
            cut.add("daily")
    else:
        daily = [r for r in daily if start <= (ga4._d(r.get("date")) or date.min) <= end]
    p = _parse(start, end, den)
    p["den"] = den
    _merge_daily(p, daily)
    del daily
    for name, fn, merge in REPORTS:
        rows = fn(ga, start, end)
        if ga.truncated(rows):
            cut.add(name)
        merge(p, rows)
        del rows
    cs = start
    while cs <= end:                           # parsed slice by slice: never ~1M row dicts in memory at once
        ce = min(cs + timedelta(days=FULL_CHUNK_DAYS - 1), end)
        rows = rep_cells(ga, cs, ce)
        if ga.truncated(rows):
            cut.add("cells")
        _place_cells(p, rows, place_from)
        del rows
        cs = ce + timedelta(days=1)
    return p


# ── full + incremental fetch ────────────────────────────────────────────────────────────────────

def fetch_full(ga, end, max_history_days, old_store=None):
    """The app's whole history: the daily report over the widest window finds where its data starts
    (history_start), then the other reports from there. Cells whose install day is older than that but
    still inside `old_store`'s history are placed into those older cohorts. Raises on any failure (the
    caller keeps the old store)."""
    start0 = end - timedelta(days=max_history_days - 1)
    rows, den = _daily_rows(ga, start0, end, "a28")
    cut = {"daily"} if ga.truncated(rows) else set()
    active = sorted(d for d in (ga4._d(r.get("date")) for r in rows
                                if (r.get("newUsers") or 0) > 0 or (r.get("activeUsers") or 0) > 0) if d)
    if not active:
        raise NoData("no GA4 users in the window")
    hs = max(active[0], start0)
    place_from = hs
    if old_store and old_store.get("history_start"):
        place_from = min(hs, _d(old_store["history_start"]))
    p = _fetch_window(ga, hs, end, den, place_from, cut, daily=rows)     # the daily rows are reused, not re-asked
    del rows
    return {"v": STORE_V, "den": p["den"], "history_start": hs.isoformat(), "window_end": end.isoformat(),
            "history_capped": hs <= start0, "covered": [[hs.isoformat(), end.isoformat()]],
            "daily": p["daily"], "cohorts": p["cohorts"], "unplaced": p["unplaced"], "versions": p["versions"],
            "flags": {"truncated": sorted(cut), "thresholded": bool(ga.thresholded), "kept_old_before": None,
                      "bad_rows": p["bad_rows"]}}


def holes(store):
    """Date ranges inside [history_start, window_end] that no fetch has covered yet."""
    hs, we = _d(store["history_start"]), _d(store["window_end"])
    cur, out = hs, []
    for a, b in sorted((_d(a), _d(b)) for a, b in store.get("covered") or []):
        if a > cur:
            out.append((cur, min(a - timedelta(days=1), we)))
        cur = max(cur, b + timedelta(days=1))
        if cur > we:
            break
    if cur <= we:
        out.append((cur, we))
    return [h for h in out if h[0] <= h[1]]


def incr_start(store, end, refetch_days):
    """First date of the incremental window: the last `refetch_days`, the day after window_end, or the
    first gap — whichever is earliest (never before the history)."""
    cands = [end - timedelta(days=refetch_days - 1), _d(store["window_end"]) + timedelta(days=1)]
    h = holes(store)
    if h:
        cands.append(h[0][0])
    return max(min(cands), _d(store["history_start"]))


def _merge_ranges(rs):
    out = []
    for a, b in sorted((_d(a), _d(b)) for a, b in rs):
        if out and a <= out[-1][1] + timedelta(days=1):
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [[a.isoformat(), b.isoformat()] for a, b in out]


def merge_window(store, fetched, start, end):
    """Replace everything whose date falls in [start, end] with `fetched` (in place, returns `store`):
    daily + versions by date; cohort cells by EVENT date (install day + lag) — so an old cohort's recent
    uninstalls are refreshed, its older cells stay frozen until the next full re-pull; unplaced by date."""
    start, end = _d(start), _d(end)
    daily, vers = store.setdefault("daily", {}), store.setdefault("versions", {})
    for d in _days(start, end):
        k = d.isoformat()
        if k in fetched["daily"]:
            daily[k] = fetched["daily"][k]
        if k in fetched["versions"]:
            vers[k] = fetched["versions"][k]
        else:
            vers.pop(k, None)
    cells = store.setdefault("cohorts", {})
    for f in list(cells):
        fd = _d(f)
        lo, hi = (start - fd).days, (end - fd).days
        if hi < 0:
            continue
        lags = cells[f]
        for lag in [k for k in lags if lo <= int(k) <= hi]:
            del lags[lag]
        if not lags:
            del cells[f]
    for f, lags in fetched["cohorts"].items():
        c = cells.setdefault(f, {})
        for lag, u in lags.items():
            c[lag] = c.get(lag, 0) + u
    un = store.setdefault("unplaced", {})
    for k in [k for k in un if start <= _d(k) <= end]:
        del un[k]
    for k, u in fetched["unplaced"].items():
        un[k] = un.get(k, 0) + u
    store["covered"] = _merge_ranges((store.get("covered") or []) + [[start, end]])
    store["window_end"] = max(_d(store.get("window_end") or end), end).isoformat()
    if not store.get("history_start") or start < _d(store["history_start"]):
        store["history_start"] = start.isoformat()
    return store


def fetch_incr(ga, store, end, refetch_days):
    """The recent window (see incr_start) re-pulled and merged into `store` (in place, returned)."""
    start = incr_start(store, end, refetch_days)
    cut = set()
    p = _fetch_window(ga, start, end, store.get("den") or "a28", _d(store["history_start"]), cut)
    merge_window(store, p, start, end)
    fl = store.setdefault("flags", {})
    fl["truncated"] = sorted(set(fl.get("truncated") or []) | cut)
    fl["thresholded"] = bool(fl.get("thresholded")) or bool(ga.thresholded)
    fl["bad_rows"] = (fl.get("bad_rows") or 0) + p["bad_rows"]
    if p["den"] == "dau":
        store["den"] = "dau"                    # one denominator for the whole series
    return store


def _sum_new(store, a, b):
    d = store.get("daily") or {}
    return sum(int((d.get(x.isoformat()) or {}).get("new") or 0) for x in _days(a, b))


def apply_rebuild(old, new, check_ratio=True):
    """A full re-pull on top of what we hold → (store, ok). The new data replaces every overlapping date;
    days BEFORE its history_start (GA4 may have stopped returning them) are KEPT, never trimmed. A re-pull
    carrying < REBUILD_MIN_RATIO of the installs we already hold for the same days is rejected (ok False):
    a partial GA4 answer must never overwrite good history."""
    if not old or not old.get("history_start"):
        return new, True
    ohs, nhs = _d(old["history_start"]), _d(new["history_start"])
    lo, hi = max(ohs, nhs), min(_d(old["window_end"]), _d(new["window_end"]))
    if check_ratio and lo <= hi:
        so, sn = _sum_new(old, lo, hi), _sum_new(new, lo, hi)
        if so > 0 and sn < REBUILD_MIN_RATIO * so:
            return old, False
    if nhs <= ohs:
        return new, True
    merged = merge_window(old, new, nhs, _d(new["window_end"]))
    merged.update(history_start=ohs.isoformat(), history_capped=new.get("history_capped", False),
                  den=new.get("den") or "a28")
    merged["flags"] = dict(new.get("flags") or {}, kept_old_before=nhs.isoformat())
    return merged, True


def store_meta(store):
    """The few store fields plan() needs — kept in state so planning never loads a big store."""
    if not store:
        return None
    return {"history_start": store.get("history_start"), "window_end": store.get("window_end"),
            "next_rebuild": store.get("next_rebuild"), "covered": store.get("covered") or [],
            "property_id": store.get("property_id"), "stream_id": store.get("stream_id"),
            "time_zone": store.get("time_zone")}


def plan(app_st, store, end, now, cfg):
    """None | "full" | "incr" for one app this run. `store` = the store or its store_meta."""
    if app_st.get("fail") and _hours_since(app_st.get("last_try"), now) < cfg["retry_hours"]:
        return None                                     # a failed app waits retry_hours — even a moved one,
                                                        # so a stream we can't read isn't re-asked every hour
    if not store:
        return "full"
    if (str(store.get("property_id")), str(store.get("stream_id"))) != \
            (str(app_st.get("property_id")), str(app_st.get("stream_id"))):
        return "full"                                   # the app moved to another GA4 stream
    if _hours_since(app_st.get("last_ok"), now) < cfg["min_hours"]:
        return None                                     # at most once per ~20h
    if store.get("next_rebuild") and end >= _d(store["next_rebuild"]):
        return "full"
    if end > _d(store["window_end"]) or holes(store):
        return "full" if (end - incr_start(store, end, cfg["refetch_days"])).days + 1 > FULL_IF_GAP_DAYS else "incr"
    return None


def _fail_kind(e):
    s = str(e)
    if "HTTP 429" in s or "RESOURCE_EXHAUSTED" in s:
        return "quota"
    if s.startswith(("HTTP 401", "HTTP 403")) or "PERMISSION_DENIED" in s or "UNAUTHENTICATED" in s:
        return "auth"
    if s.startswith("HTTP ") or type(e).__module__.startswith("requests"):
        return "http"
    return "other"


def _quota_low(q):
    for k, cap in QUOTA_CAP.items():
        b = (q or {}).get(k) or {}
        if "remaining" in b:
            total = max(cap, (b.get("consumed") or 0) + (b.get("remaining") or 0))
            if (b.get("remaining") or 0) < QUOTA_MIN_FRAC * total:
                return True
    return False


# ── orchestration ───────────────────────────────────────────────────────────────────────────────

def _discover(cfg, tokens, state, apps, access, now):
    """Re-list every owner's Android streams → state["routes"] + timezones of the properties we use.
    Keeps the old routes when every owner fails. Returns False on total failure."""
    routes = state["routes"]
    routes["tried_at"] = _now_iso(now)
    paging = {}
    owners, props, readers = ga4_probe.discover_owners(cfg["client_id"], cfg["client_secret"], tokens, paging)
    for o in owners:
        if not o["ok"] and o.get("stage") == "auth":
            access[o["owner"]] = None
    for lst in readers.values():
        for owner, tok in lst:
            access.setdefault(owner, tok)
    if not any(o["ok"] for o in owners):
        return False
    streams, token_of, errors, _ = ga4_probe.list_streams(props, readers, paging)
    by_pkg = {}
    for s in streams:
        if s.get("package") and s["package"] not in by_pkg:
            by_pkg[s["package"]] = {"property_id": s["property_id"], "stream_id": s["stream_id"], "owner": s["owner"]}
    for pkg, r in (routes.get("by_package") or {}).items():
        if pkg not in by_pkg and r.get("property_id") not in token_of:
            by_pkg[pkg] = r                             # its property wasn't listed THIS time (its list or its
                                                        # owner's token failed) — keep the old route, don't lose it
    routes.update(fetched_at=_now_iso(now), by_package=by_pkg, stream_errors=len(errors),
                  owners_failed=sum(1 for o in owners if not o["ok"]), stale=False)
    wanted = {by_pkg[a["package"]]["property_id"] for a in apps if a.get("package") in by_pkg}
    for pid in sorted(wanted):
        if pid not in token_of:
            continue                                    # its list failed this time: keep the known timezone
        try:
            tz = ga4.property_meta(token_of[pid], pid).get("time_zone")
            if tz:
                state["tz"][pid] = tz
        except Exception:
            pass                                        # the store's own timezone (or UTC) is used instead
        ga4._sleep(ga4.PAUSE)
    return True


def refresh_all(cfg, data_dir, apps, now=None, clock=time.monotonic):
    """Fetch what is due for every selected app (`apps` = [{app_id, app_name, package|None}]) → status
    {"counts", "apps": {app_id: fresh|fetched|failed|deferred}, "no_ga4": {app_id: reason}, "discovery"}.
    Never raises; never prints."""
    now = now or datetime.now(timezone.utc)
    t0 = clock()
    counts = dict.fromkeys(("selected", "with_ga4", "fetched", "full", "fresh", "failed", "deferred", "no_ga4"), 0)
    counts["selected"] = len(apps)
    out = {"counts": counts, "apps": {}, "no_ga4": {}, "discovery": None}
    state = load_state(data_dir)
    try:
        tokens, _ = ga4_probe.owner_tokens({"GA4_REFRESH_TOKENS": cfg.get("refresh_tokens") or "",
                                            "GA4_REFRESH_TOKEN": cfg.get("refresh_token") or ""})
        owner_rt, access = dict(tokens), {}
        routes = state["routes"]
        age = _hours_since(routes.get("fetched_at"), now)
        tried = _hours_since(routes.get("tried_at"), now)
        missing = any(a.get("package") and a["package"] not in routes["by_package"] for a in apps)
        due = (age >= cfg["streams_ttl_hours"] or (routes.get("stale") and age >= cfg["retry_hours"])
               or (missing and age >= cfg["min_hours"]))
        if tokens and due and tried >= cfg["retry_hours"]:
            out["discovery"] = "ok" if _discover(cfg, tokens, state, apps, access, now) else "failed"

        todo = []
        for a in apps:
            aid, pkg = a["app_id"], a.get("package")
            r = routes["by_package"].get(pkg) if pkg else None
            if not pkg or not r:                        # "no stream" only when every list was really read
                gap = routes.get("stream_errors") or routes.get("owners_failed") or not routes.get("fetched_at")
                out["no_ga4"][aid] = "no_package" if not pkg else "stream_list_failed" if gap else "no_stream"
                continue
            counts["with_ga4"] += 1
            st = state["fetch"].setdefault(aid, {"last_try": None, "last_ok": None, "last_kind": None,
                                                 "fail": None, "fail_detail": None})
            st.update(key=file_key(aid), package=pkg, property_id=r["property_id"], stream_id=r["stream_id"])
            meta = st.get("meta")
            if not os.path.exists(store_path(data_dir, aid)):
                meta = st["meta"] = None                # state without its store → fetch it again
            elif meta is None:
                meta = st["meta"] = store_meta(load_store(store_path(data_dir, aid)))
            tz = state["tz"].get(r["property_id"]) or (meta or {}).get("time_zone") or "UTC"
            end = settled_end(tz, now)
            kind = plan(st, meta, end, now, cfg)
            if kind is None:
                out["apps"][aid] = "failed" if st.get("fail") else "fresh"
                continue
            todo.append((kind, a, st, r, tz, end))
        # incremental first (oldest first), then full fetches (never fetched first); last run's deferred lead
        todo.sort(key=lambda t: (not t[2].get("deferred"), t[0] != "incr", t[2].get("last_ok") is not None,
                                 t[2].get("last_ok") or "", t[1]["app_id"]))

        held_back = set()
        for kind, a, st, r, tz, end in todo:
            aid, pid = a["app_id"], r["property_id"]
            if clock() - t0 >= cfg["run_budget_sec"] or pid in held_back:
                st["deferred"] = True
                out["apps"][aid] = "deferred"
                continue
            st.pop("deferred", None)
            owner = r.get("owner")
            if owner not in access:
                try:                                    # an owner dropped from the secret → no token → "auth"
                    access[owner] = (ga4.access_token(cfg["client_id"], cfg["client_secret"], owner_rt[owner])
                                     if owner in owner_rt else None)
                except Exception:
                    access[owner] = None
            tok = access.get(owner)
            if not tok:
                st.update(last_try=_now_iso(now), fail="auth", fail_detail="owner token did not refresh")
                routes["stale"] = True                  # another owner may still see this property
                out["apps"][aid] = "failed"
                continue
            ga = ga4.Ga4App(tok, pid, r["stream_id"])
            path = store_path(data_dir, aid)
            try:
                old = load_store(path)
                moved = bool(old) and (str(old.get("property_id")), str(old.get("stream_id"))) != (str(pid), str(r["stream_id"]))
                if kind == "incr" and not old:
                    kind = "full"
                if kind == "full":
                    new = fetch_full(ga, end, cfg["max_history_days"], old)
                    store, ok = apply_rebuild(old, new, check_ratio=not moved)
                    if not ok:                          # keep what we hold; try the full pull again tomorrow
                        old["next_rebuild"] = (end + timedelta(days=1)).isoformat()
                        save_store(path, old)
                        st.update(last_try=_now_iso(now), fail="rebuild_mismatch", fail_detail=None,
                                  meta=store_meta(old))
                        out["apps"][aid] = "failed"
                        continue
                    stagger = zlib.crc32(aid.encode("utf-8")) % 7   # so the apps don't all re-pull on one day
                    store.update(full_at=_now_iso(now),
                                 next_rebuild=(end + timedelta(days=cfg["rebuild_days"] + stagger)).isoformat())
                else:
                    store = fetch_incr(ga, old, end, cfg["refetch_days"])
                store.update(v=STORE_V, app_id=aid, package=a.get("package"), property_id=str(pid),
                             stream_id=str(r["stream_id"]), time_zone=tz, fetched_at=_now_iso(now))
                store.setdefault("den", "a28")
                save_store(path, store)
                st.update(last_try=_now_iso(now), last_ok=_now_iso(now), last_kind=kind, fail=None,
                          fail_detail=None, meta=store_meta(store))
                out["apps"][aid] = "fetched"
                counts["full"] += kind == "full"
            except Exception as e:
                fk = _fail_kind(e)
                st.update(last_try=_now_iso(now), fail=fk, fail_detail=("%s: %s" % (type(e).__name__, e))[:300])
                out["apps"][aid] = "failed"
                if fk == "auth":
                    routes["stale"] = True
                if fk == "quota":
                    held_back.add(pid)
            finally:
                old = store = new = None                # free a big store before the next app
            if _quota_low(ga.quota):
                held_back.add(pid)
    except Exception as e:                              # a bug here must never cost the AdMob build
        out["error"] = type(e).__name__
    for v in out["apps"].values():
        counts[v] += 1
    counts["no_ga4"] = len(out["no_ga4"])
    try:
        save_state(data_dir, state)
    except Exception:
        out["error"] = out.get("error") or "state_write"
    return out
