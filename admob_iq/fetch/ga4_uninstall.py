"""GA4 → per-app uninstall store (data/ga4_uninstall/), fetched inside the hourly build.

Four Data API reports per app, all pinned to the app's Android stream by Ga4App:
  * daily     date → newUsers, activeUsers, active28DayUsers           (installs + the rate denominator)
  * events    date × eventName → totalUsers, eventCount for app_remove / app_update
  * cells     firstSessionDate × date → app_remove users               (the install-cohort churn cells)
  * versions  date × appVersion → activeUsers                          (releases; Step 4 version scorecard)

FULL history on an app's first fetch (as far back as the property has data, ≤ GA4_MAX_HISTORY_DAYS), then
INCREMENTAL: the last GA4_REFETCH_DAYS dates (14: Firebase keeps adding events for up to ~7 days) + any gap,
at most once per GA4_MIN_HOURS per app, and a new day only from noon in the property's timezone (SETTLE_HOUR)
— every other hourly run makes ZERO GA4 calls. A full re-pull every
GA4_REBUILD_DAYS (staggered per app) self-heals anything the incremental merge missed; older days it no
longer returns are KEPT, never trimmed. Every report is paged to the last row; the paging safety cap and
GA4 thresholding are flagged in the store, never silent.

SELF-CHECKED CELLS: a long firstSessionDate × date report on a big app silently comes back with a fraction of
its uninstalls (seen live: 2–78% over 90 days, while ~11-day ranges were complete). So every cells slice is
checked against the date × eventName report of the same days (daily[d].un): a short slice is thrown away
whole and asked again as two halves, down to single days; a single day still short is KEPT and recorded in
flags.incomplete_days {day: coverage} (the engine takes no alert from it, the tab says "data adhoora"). Rows
GA4 folds into "(other)" never count as covered. When the shortfall is GA4's own (days short even alone), or
the fetch spent its call cap / run budget, a short slice is kept with its short days flagged instead of split
further; a re-read that comes back short never replaces cells we hold in full (keep_held). The slice size
that verified is remembered per app (cells_chunk_days) and grown back slowly.

LATE DATA: every fetch also records how the recent days it re-read changed since the last fetch, by the
day's age (store["revisions"]) — engine.uninstall.lateness turns that into "how much of a day's uninstalls
are there at age N", so the owner sees how late Firebase really is.

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

FULL_CHUNK_DAYS = 90        # the LONGEST cells slice (~H×90 rows — a page or two); an app's own verified size may be less
CELLS_MIN_COVERAGE = 0.97   # a cells slice must hold ≥97% of the app_remove users the events report counts for its days:
                            # user counts are sketches (a complete slice reads 100–107%), the silent undercount 2–78%
CELLS_DAY_MIN_COVERAGE = 0.90   # … and no day inside it under 90% — one bad day hides in a long slice's total
CELLS_MIN_USERS = 200       # a slice / day with fewer app_remove users is not judged: a few users either way is noise
CELLS_GROW_COVERAGE = 0.99  # every slice ≥99% at the app's full slice size → the next fetch tries 1.5× longer slices,
                            # so an app that once needed short slices (or a quiet one) doesn't stay there forever …
CELLS_GROW_GAP = 0.02       # … unless they read ≥2 points under the fetch's shorter slices: complete slices read
                            # 100–107% by app, so "≥99%" alone can hide a few % lost at that length
CELLS_REF_USERS = 1000      # (that comparison needs ≥1,000 users in the shorter slices — fewer is noise)
CELLS_ALONE_STOP = 3        # once 3 days of a fetch were short even asked ALONE (GA4 itself — e.g. thresholding —
CELLS_ALIKE = 0.05          # not the slice length), a short slice reading like them (≤5 points under their median)
                            # is kept and flagged day by day, not split down to single days (2n−1 calls a slice)
CELLS_MAX_CALLS = 30        # cells calls per fetch: at most 30 + one per 2 days of the window (a real 3-day limit on
                            # 1300 days needs ~470); past it — or past 2× the run budget — no slice is split any more:
                            # a short one is kept and its days flagged, never hidden
REVISION_FETCHES = 28       # lateness: the re-reads of the last 28 daily fetches are kept (4 weeks, rolling)
REVISION_MAX_AGE = 30       # … of days at most 30 days old (older re-reads only happen in full re-pulls)
UNI_PAGE_ROWS = 100000      # rows per Data API page (the API allows 250,000)
FULL_IF_GAP_DAYS = 90       # an incremental window longer than this is a full re-pull instead
REBUILD_MIN_RATIO = 0.5     # a re-pull with < half the installs of what we hold is suspect → keep the old
QUOTA_MIN_FRAC = 0.10       # stop a property's remaining apps when any quota bucket is below 10%
QUOTA_CAP = {"tokensPerDay": 200000, "tokensPerHour": 40000, "tokensPerProjectPerHour": 14000}
                            # standard-property bucket sizes — propertyQuota only says consumed/remaining
SETTLE_HOUR = 12            # the newest day (today−2) is fetched only from noon in the property's timezone: by
                            # then it has had ≥36h of GA4's 24–48h to settle. At 00:47 it has had just 24h, and
                            # a day still filling in reads LOW (a false "achanak kam" / 0-uninstall alert)
STORE_V = 2                 # 2: cells verified against the events report (v1 stores undercount big apps' cohorts) —
                            # plan() re-pulls an older store in full at once and its alert history starts over
DIR = "ga4_uninstall"
EVENTS = ["app_remove", "app_update"]


class NoData(RuntimeError):
    """The stream has no users at all in the window (a brand-new or unused stream)."""


class QuotaLow(RuntimeError):
    """The property's quota ran low while short cells slices were being asked again: the app stops here and
    keeps its old store (never a half-verified one); refresh_all holds the property back like a 429."""


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
            "cohorts": {}, "unplaced": {}, "versions": {}, "bad_rows": 0, "incomplete": {}, "alone": {},
            "cells_log": []}


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


# ── cells, checked against the events report ─────────────────────────────────────────────────────

def cells_judge(got, daily, days):
    """Cell users by event day (`got`, see _covered) vs the events report's app_remove users (daily[d].un)
    over `days` → (coverage, or None when too few users to judge; complete?). Complete = the slice holds
    ≥ CELLS_MIN_COVERAGE and no judged day inside it is under CELLS_DAY_MIN_COVERAGE."""
    want = sum(_un(daily, d) for d in days)
    if want < CELLS_MIN_USERS:
        return None, True
    cov = sum(got.get(d, 0) for d in days) / want
    for d in days:
        u = _un(daily, d)
        if u >= CELLS_MIN_USERS and got.get(d, 0) < CELLS_DAY_MIN_COVERAGE * u:
            return cov, False
    return cov, cov >= CELLS_MIN_COVERAGE


def _un(daily, d):
    return int((daily.get(d) or {}).get("un") or 0)


def _covered(rows, a, b):
    """Cell users by event day in [a, b] — cells_judge's `got` — from the rows whose install day is a DATE
    (one before the history counts: it is placed as an older install). "(other)" / unparseable ones don't:
    GA4 folds a report it finds too big into "(other)", and those users reach no cohort — a slice full of
    them must read short, not complete."""
    got = {}
    for r in rows:
        d = ga4._d(r.get("date"))
        if d is not None and a <= d <= b and ga4._d(r.get("firstSessionDate")) is not None:
            got[d.isoformat()] = got.get(d.isoformat(), 0) + int(r.get("totalUsers") or 0)
    return got


def short_days(got, daily, days):
    """The days of a slice KEPT short (see _fetch_cells) → {day: coverage}: every judged day under
    CELLS_MIN_COVERAGE, and — when the other days still fall short together — every other day under it too,
    so a shortfall the slice proved is never left unflagged."""
    under = {d: round(got.get(d, 0) / _un(daily, d), 4) for d in days
             if _un(daily, d) and got.get(d, 0) < CELLS_MIN_COVERAGE * _un(daily, d)}
    big = {d: c for d, c in under.items() if _un(daily, d) >= CELLS_MIN_USERS}
    return big if cells_judge(got, daily, [d for d in days if d not in big])[1] else under


def _alike(n, cov, log, alone, daily):
    """A short slice of n days reading like the days short even alone (`alone`: CELLS_ALONE_STOP judged ones —
    ≥ CELLS_MIN_USERS each — at least, cov within CELLS_ALIKE of their median), at a size no longer than the
    longest one of `log` that verified complete (any size before one did): GA4's own shortfall, not the slice
    length — splitting it further gains nothing."""
    ref = sorted(c for d, c in alone.items() if _un(daily, d) >= CELLS_MIN_USERS)
    if len(ref) < CELLS_ALONE_STOP or cov is None:
        return False
    best = max((r["days"] for r in log if r["ok"] and r["cov"] is not None), default=None)
    return (best is None or n <= best) and cov >= ref[len(ref) // 2] - CELLS_ALIKE


def _explained(rec, daily, alone, log):
    """A short slice that says nothing about how long a slice may be: it reads like the days short even alone
    (_alike — also one split before enough of them were found), or its shortfall sits wholly on such days."""
    return (bool(rec.get("alike")) or _alike(rec["days"], rec["cov"], log, alone, daily)
            or cells_judge(rec["got"], daily, [d for d in rec["span"] if d not in alone])[1])


def _works(rec):
    """A slice size that did all it can: verified complete (JUDGED — a slice too small to judge proves
    nothing), or short only like the days short even alone."""
    return (rec["ok"] and rec["cov"] is not None) or bool(rec.get("alike"))


def _pooled(recs, daily):
    """(Σ cell users, Σ events users) over the slices in `recs` that carry their days."""
    got = want = 0
    for r in recs:
        for d in r.get("span") or []:
            got, want = got + (r.get("got") or {}).get(d, 0), want + _un(daily, d)
    return got, want


def next_chunk(log, chunk, daily, alone):
    """The cells slice size to start the NEXT fetch with, from this fetch's `log` (every slice asked: days,
    coverage, ok) and `alone` (its days short even alone): after a real shortfall, the longest size that worked
    (_works) below the shortest that fell short, else unchanged; when every slice verified comfortably
    (≥ CELLS_GROW_COVERAGE) at the full `chunk` size — and those read no more than CELLS_GROW_GAP under the
    fetch's shorter judged slices — 1.5× (never above FULL_CHUNK_DAYS); otherwise unchanged."""
    short = [r["days"] for r in log if not r["ok"] and not _explained(r, daily, alone, log)]
    if short:
        return max([r["days"] for r in log if _works(r) and r["days"] < min(short)], default=chunk)
    ok = [r for r in log if r["ok"]]
    if not any(r["days"] >= chunk for r in ok) or any(r["cov"] is not None and r["cov"] < CELLS_GROW_COVERAGE
                                                      for r in ok):
        return chunk
    fg, fw = _pooled([r for r in ok if r["days"] >= chunk and r["cov"] is not None], daily)
    pg, pw = _pooled([r for r in ok if r["days"] < chunk and r["cov"] is not None], daily)
    if fw and pw >= CELLS_REF_USERS and fg / fw < pg / pw - CELLS_GROW_GAP:
        return chunk                                    # the full size loses a little the shorter ones keep
    return min(FULL_CHUNK_DAYS, chunk + max(1, chunk // 2))


def _start_chunk(store):
    try:
        return min(FULL_CHUNK_DAYS, max(1, int((store or {}).get("cells_chunk_days") or FULL_CHUNK_DAYS)))
    except (TypeError, ValueError):
        return FULL_CHUNK_DAYS


def _fetch_cells(ga, p, start, end, place_from, cut, chunk, stop=None):
    """Cells over [start, end] into `p`, slice by slice, each checked (cells_judge) against p["daily"] — the
    events report of the same days, fetched first. A short slice's rows are thrown away WHOLE (never counted
    twice) and its two halves asked instead, down to single days; a single day still short is kept and
    recorded in p["incomplete"] {day: coverage} (and p["alone"]) — shown, never hidden. Halves too small to
    judge (CELLS_MIN_USERS) are judged together: a shortfall their parent proved stays flagged on their days.
    A short slice is KEPT whole instead, its short days flagged (short_days), once CELLS_ALONE_STOP days were
    short even alone and it reads like them at a size no longer than one that verified (GA4's own shortfall:
    splitting gains nothing — rec["alike"]), or once the fetch spent its CELLS_MAX_CALLS or `stop()` (the run
    budget) says so. Slices start at `chunk` days; after a slice needed splitting, the next ones start at the
    size that worked. Every slice asked goes to p["cells_log"] (see next_chunk). Asking again while the
    property's quota is low raises QuotaLow."""
    log, daily, alone, inc = p["cells_log"], p["daily"], p["alone"], p["incomplete"]
    limit = CELLS_MAX_CALLS + ((end - start).days + 1) // 2

    def ask(a, b):
        """→ (cell users by day, as kept; judged?)"""
        n = (b - a).days + 1
        rows = rep_cells(ga, a, b)
        got = _covered(rows, a, b)
        span = [d.isoformat() for d in _days(a, b)]
        cov, ok = cells_judge(got, daily, span)
        rec = {"days": n, "cov": cov, "ok": ok, "got": got, "span": span}
        log.append(rec)
        if not ok and n > 1:
            if _alike(n, cov, log, alone, daily):
                rec["alike"] = True
            elif len(log) >= limit or (stop and stop()):
                rec["stopped"] = True
            else:
                del rows
                if _quota_low(ga.quota):
                    raise QuotaLow("quota low while re-asking short cells slices")
                mid = a + timedelta(days=n // 2 - 1)
                both, loose = {}, []
                for x, y in ((a, mid), (mid + timedelta(days=1), b)):
                    g, judged = ask(x, y)
                    both.update(g)
                    if not judged:
                        loose.append((x, y))
                # halves too small to judge alone: judged together (without the days already flagged) — still
                # short, the shortfall is on THEIR days
                if loose and not cells_judge(both, daily, [d for d in span if d not in inc])[1]:
                    for x, y in loose:
                        for d in (z.isoformat() for z in _days(x, y)):
                            u = _un(daily, d)
                            if u and both.get(d, 0) < CELLS_MIN_COVERAGE * u:
                                inc[d] = round(both.get(d, 0) / u, 4)
                                if x == y:
                                    alone[d] = inc[d]
                return both, True
        if ga.truncated(rows):
            cut.add("cells")
        _place_cells(p, rows, place_from)
        if not ok and n == 1:
            inc[span[0]] = alone[span[0]] = round(cov, 4)
        elif not ok:
            for d, c in short_days(got, daily, span).items():
                inc.setdefault(d, c)
        return got, cov is not None

    cur, cs = chunk, start
    while cs <= end:                           # parsed slice by slice: never ~1M row dicts in memory at once
        ce = min(cs + timedelta(days=cur - 1), end)
        mark = len(log)
        ask(cs, ce)
        mine = log[mark:]
        short = [r["days"] for r in mine if not r["ok"] and not _explained(r, daily, alone, log)]
        if short:
            cur = max([r["days"] for r in mine if _works(r) and r["days"] < min(short)], default=cur)
        cs = ce + timedelta(days=1)


def _fetch_window(ga, start, end, den, place_from, cut, daily=None, chunk=FULL_CHUNK_DAYS, stop=None):
    """daily + REPORTS + cells over [start, end] → parsed window. `cut` collects capped report names.
    `daily` = daily rows already fetched over a window covering [start, end] (rows outside it are skipped).
    `chunk` = the cells slice size to start with, `stop` = the run budget (see _fetch_cells)."""
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
    _fetch_cells(ga, p, start, end, place_from, cut, chunk, stop)
    return p


# ── full + incremental fetch ────────────────────────────────────────────────────────────────────

def fetch_full(ga, end, max_history_days, old_store=None, stop=None):
    """The app's whole history: the daily report over the widest window finds where its data starts
    (history_start), then the other reports from there. Cells whose install day is older than that but
    still inside `old_store`'s history are placed into those older cohorts. `stop` = the run budget (see
    _fetch_cells). Raises on any failure (the caller keeps the old store)."""
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
    chunk = _start_chunk(old_store)
    p = _fetch_window(ga, hs, end, den, place_from, cut, daily=rows, chunk=chunk, stop=stop)   # daily rows reused
    del rows
    return {"v": STORE_V, "den": p["den"], "history_start": hs.isoformat(), "window_end": end.isoformat(),
            "history_capped": hs <= start0, "covered": [[hs.isoformat(), end.isoformat()]],
            "daily": p["daily"], "cohorts": p["cohorts"], "unplaced": p["unplaced"], "versions": p["versions"],
            "cells_chunk_days": next_chunk(p["cells_log"], chunk, p["daily"], p["alone"]),
            "last_window": [hs.isoformat(), end.isoformat()],
            "flags": {"truncated": sorted(cut), "thresholded": bool(ga.thresholded), "kept_old_before": None,
                      "bad_rows": p["bad_rows"], "incomplete_days": dict(sorted(p["incomplete"].items()))}}


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


def _day_totals(store, days):
    """Cell users (placed + unplaced) a store / parsed window holds per event day in `days` (ISO) → {day: users}."""
    un = store.get("unplaced") or {}
    out = {d: int(un.get(d) or 0) for d in days}
    for f, lags in (store.get("cohorts") or {}).items():
        fd = _d(f)
        for lag, u in lags.items():
            d = (fd + timedelta(days=int(lag))).isoformat()
            if d in out:
                out[d] += int(u or 0)
    return out


def keep_held(held, fetched, flags):
    """A re-read (`fetched`) flagged SHORT on a day `held` — what we hold — has MORE cells for is a bad GA4
    answer, not news: late data only ever adds. That day's cells go back to held's (in `fetched`, in place)
    and its flag in `flags` (fetched's {day: coverage}) is judged again against the new events count."""
    mine, new = _day_totals(held, flags), _day_totals(fetched, flags)
    keep = {d for d in flags if mine[d] > new[d]}
    if not keep:
        return
    for src, dst in ((fetched, None), (held, fetched)):          # out with the short re-read, in with ours
        for f, lags in list((src.get("cohorts") or {}).items()):
            fd = _d(f)
            for lag in [k for k in lags if (fd + timedelta(days=int(k))).isoformat() in keep]:
                if dst is None:
                    del lags[lag]
                else:
                    dst["cohorts"].setdefault(f, {})[lag] = lags[lag]
            if dst is None and not lags:
                del src["cohorts"][f]
    un = fetched.setdefault("unplaced", {})
    for d in keep:
        un.pop(d, None)
        if (held.get("unplaced") or {}).get(d):
            un[d] = held["unplaced"][d]
        u = _un(fetched.get("daily") or {}, d)
        if u and mine[d] < CELLS_MIN_COVERAGE * u:
            flags[d] = round(mine[d] / u, 4)
        else:
            del flags[d]


def merge_window(store, fetched, start, end, held=True):
    """Replace everything whose date falls in [start, end] with `fetched` (in place, returns `store`):
    daily + versions by date; cohort cells by EVENT date (install day + lag) — so an old cohort's recent
    uninstalls are refreshed, its older cells stay frozen until the next full re-pull; unplaced by date.
    A day the re-read flags short keeps the cells we hold when they are more (keep_held; `held` False: not)."""
    start, end = _d(start), _d(end)
    got = fetched["incomplete"] if "incomplete" in fetched else (fetched.get("flags") or {}).get("incomplete_days")
    got = {k: v for k, v in (got or {}).items() if start <= _d(k) <= end}
    if held:
        keep_held(store, fetched, got)
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
    # incomplete days follow the cells they describe: re-read days take the new verdict (a day that is
    # complete now drops its flag), days outside the window keep theirs
    fl = store.setdefault("flags", {})
    inc = {k: v for k, v in (fl.get("incomplete_days") or {}).items() if not start <= _d(k) <= end}
    inc.update(got)
    fl["incomplete_days"] = dict(sorted(inc.items()))
    store["covered"] = _merge_ranges((store.get("covered") or []) + [[start, end]])
    store["window_end"] = max(_d(store.get("window_end") or end), end).isoformat()
    if not store.get("history_start") or start < _d(store["history_start"]):
        store["history_start"] = start.isoformat()
    return store


def fetch_incr(ga, store, end, refetch_days, stop=None):
    """The recent window (see incr_start) re-pulled and merged into `store` (in place, returned)."""
    start = incr_start(store, end, refetch_days)
    cut = set()
    chunk = _start_chunk(store)
    p = _fetch_window(ga, start, end, store.get("den") or "a28", _d(store["history_start"]), cut, chunk=chunk,
                      stop=stop)
    merge_window(store, p, start, end)
    store["cells_chunk_days"] = next_chunk(p["cells_log"], chunk, p["daily"], p["alone"])
    store["last_window"] = [start.isoformat(), end.isoformat()]
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


def stored_coverage(store, a, b):
    """Cells vs the events report per day for [a, b], from what `store` already holds (cohort cells by event
    day + unplaced vs daily un) → {day: coverage} of the judged days under CELLS_MIN_COVERAGE."""
    a, b = _d(a), _d(b)
    got = {}
    for f, lags in (store.get("cohorts") or {}).items():
        fd = _d(f)
        for lag, u in lags.items():
            d = fd + timedelta(days=int(lag))
            if a <= d <= b:
                got[d.isoformat()] = got.get(d.isoformat(), 0) + int(u or 0)
    for k, u in (store.get("unplaced") or {}).items():
        if a <= _d(k) <= b:
            got[k] = got.get(k, 0) + int(u or 0)
    out = {}
    for d in _days(a, b):
        cov, ok = cells_judge(got, store.get("daily") or {}, [d.isoformat()])
        if not ok:
            out[d.isoformat()] = round(cov, 4)
    return out


def apply_rebuild(old, new, check_ratio=True):
    """A full re-pull on top of what we hold → (store, ok). The new data replaces every overlapping date;
    days BEFORE its history_start (GA4 may have stopped returning them) are KEPT, never trimmed — and when
    they come from an older store format (v < STORE_V: cells never checked) each of their days is checked
    now from what is stored, a short one flagged incomplete. A re-pull carrying < REBUILD_MIN_RATIO of the
    installs we already hold for the same days is rejected (ok False): a partial GA4 answer must never
    overwrite good history — nor, day by day, a short one (keep_held). check_ratio False = the app moved to
    another stream: no ratio check, and no short day takes the old stream's cells."""
    if not old or not old.get("history_start"):
        return new, True
    ohs, nhs = _d(old["history_start"]), _d(new["history_start"])
    lo, hi = max(ohs, nhs), min(_d(old["window_end"]), _d(new["window_end"]))
    if check_ratio and lo <= hi:
        so, sn = _sum_new(old, lo, hi), _sum_new(new, lo, hi)
        if so > 0 and sn < REBUILD_MIN_RATIO * so:
            return old, False
    if nhs <= ohs:
        if check_ratio:
            inc = dict((new.get("flags") or {}).get("incomplete_days") or {})
            keep_held(old, new, inc)
            new.setdefault("flags", {})["incomplete_days"] = dict(sorted(inc.items()))
        return new, True
    unchecked = _store_v(old) < STORE_V
    merged = merge_window(old, new, nhs, _d(new["window_end"]), held=check_ratio)
    inc = dict((merged.get("flags") or {}).get("incomplete_days") or {})
    if unchecked:
        inc.update(stored_coverage(merged, ohs, nhs - timedelta(days=1)))
    merged.update(history_start=ohs.isoformat(), history_capped=new.get("history_capped", False),
                  den=new.get("den") or "a28")
    merged["flags"] = dict(new.get("flags") or {}, kept_old_before=nhs.isoformat(),
                           incomplete_days=dict(sorted(inc.items())))
    return merged, True


def store_meta(store):
    """The few store fields plan() needs — kept in state so planning never loads a big store."""
    if not store:
        return None
    return {"v": store.get("v"), "history_start": store.get("history_start"), "window_end": store.get("window_end"),
            "next_rebuild": store.get("next_rebuild"), "covered": store.get("covered") or [],
            "property_id": store.get("property_id"), "stream_id": store.get("stream_id"),
            "time_zone": store.get("time_zone")}


def _store_v(store):
    try:
        return int((store or {}).get("v") or 1)
    except (TypeError, ValueError):
        return 1


def _local_day(t, tz_name):
    """A UTC datetime (or our ISO timestamp) → its calendar date in the property's timezone (UTC if unknown)."""
    from zoneinfo import ZoneInfo
    t = _parse_iso(t) if isinstance(t, str) else t
    if t is None:
        return None
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    return t.astimezone(tz).date()


def revision_base(old, tz_name):
    """What the NEXT fetch compares against to measure late data: (the local day of `old`'s last fetch,
    {day: [app_remove users, new users]} for the days that fetch read — its last_window, or the whole history
    when its last fetch was a full one — no older than REVISION_MAX_AGE). None when unknown."""
    if not old or not old.get("fetched_at"):
        return None
    lw = old.get("last_window")
    if not lw and old.get("full_at") and old.get("full_at") == old.get("fetched_at"):
        lw = [old.get("history_start"), old.get("window_end")]
    P = _local_day(old["fetched_at"], old.get("time_zone") or tz_name)
    if not lw or not lw[0] or not lw[1] or P is None:
        return None
    a = max(_d(lw[0]), P - timedelta(days=REVISION_MAX_AGE))
    daily = old.get("daily") or {}
    vals = {}
    for d in _days(a, _d(lw[1])):
        r = daily.get(d.isoformat())
        if r is not None:
            vals[d.isoformat()] = [int(r.get("un") or 0), int(r.get("new") or 0)]
    return P, vals


def record_revisions(store, base, today, window, max_age=REVISION_MAX_AGE):
    """The recent days THIS fetch re-read (`window` = [start, end]) vs `base` (revision_base of the store
    before it) → store["revisions"][today] = {"un"|"new": {age: [before, after]}}, age = the day's age in days
    at the earlier fetch (its local day − the day). Only a fetch exactly one day after the last one is
    recorded, so each entry is "what arrived between age a and a+1"; the newest REVISION_FETCHES are kept.
    Only ages up to `max_age` (the refetch window: what every daily re-read covers) — a full fetch the day
    after another one re-reads ages 2..30 ONCE, and one thin sample at age 30 would end lateness()'s chain
    for a small app for 4 weeks."""
    if not base or today is None:
        return
    P, vals = base
    if (today - P).days != 1:
        return
    a, b = _d(window[0]), _d(window[1])
    daily = store.get("daily") or {}
    rec = {"un": {}, "new": {}}
    for k, (un0, new0) in vals.items():
        d = _d(k)
        age = (P - d).days
        r = daily.get(k)
        if r is None or not a <= d <= b or not 0 <= age <= min(max_age, REVISION_MAX_AGE):
            continue
        for name, before, after in (("un", un0, int(r.get("un") or 0)), ("new", new0, int(r.get("new") or 0))):
            s = rec[name].setdefault(str(age), [0, 0])
            s[0] += before
            s[1] += after
    if not rec["un"] and not rec["new"]:
        return
    revs = dict(store.get("revisions") or {})
    revs[today.isoformat()] = rec
    store["revisions"] = {k: revs[k] for k in sorted(revs)[-REVISION_FETCHES:]}


def reset_alerts(state, app_id):
    """Forget one app's alert history — evaluation (stage, streaks, claimed install days), open and closed
    episodes — so its next evaluation is a FIRST one: whatever it shows then is seeded, never sent."""
    state["eval"].pop(app_id, None)
    for k in [k for k, e in state["episodes"].items() if e.get("app_id") == app_id]:
        del state["episodes"][k]
    state["closed"] = [e for e in state["closed"] if e.get("app_id") != app_id]


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
    if _store_v(store) < STORE_V:                      # an older store format: re-pulled clean NOW, not in ~20h
        rejected = app_st.get("fail") == "rebuild_mismatch" and store.get("next_rebuild")
        return None if rejected and end < _d(store["next_rebuild"]) else "full"   # (never an incremental onto it) —
                                                        # a re-pull just rejected: again tomorrow, not every 3h
    if _hours_since(app_st.get("last_ok"), now) < cfg["min_hours"]:
        return None                                     # at most once per ~20h
    if store.get("next_rebuild") and end >= _d(store["next_rebuild"]):
        return "full"
    if end > _d(store["window_end"]) or holes(store):
        return "full" if (end - incr_start(store, end, cfg["refetch_days"])).days + 1 > FULL_IF_GAP_DAYS else "incr"
    return None


def _fail_kind(e):
    s = str(e)
    if isinstance(e, QuotaLow) or "HTTP 429" in s or "RESOURCE_EXHAUSTED" in s:
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

    def over():                                         # one app's cells re-asks stop splitting past 2× the budget
        return clock() - t0 >= 2 * cfg["run_budget_sec"]

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
                # an unreadable older store is outdated too (its format from the state's meta): its alert history
                # came from unchecked data all the same
                outdated = _store_v(old if old else st.get("meta")) < STORE_V and bool(old or aid in state["eval"])
                base = None if moved else revision_base(old, tz)    # read before a fetch changes `old` in place
                revs = (old or {}).get("revisions")
                if kind == "incr" and (not old or outdated):
                    kind = "full"
                if kind == "full":
                    new = fetch_full(ga, end, cfg["max_history_days"], old, stop=over)
                    store, ok = apply_rebuild(old, new, check_ratio=not moved)
                    if not ok:                          # keep what we hold; try the full pull again tomorrow
                        old["next_rebuild"] = (end + timedelta(days=1)).isoformat()
                        save_store(path, old)
                        st.update(last_try=_now_iso(now), fail="rebuild_mismatch", fail_detail=None,
                                  meta=store_meta(old))
                        out["apps"][aid] = "failed"
                        continue
                    stagger = zlib.crc32(aid.encode("utf-8")) % 7   # so the apps don't all re-pull on one day
                    store.update(full_at=_now_iso(now), cells_chunk_days=new["cells_chunk_days"],
                                 last_window=new["last_window"],
                                 next_rebuild=(end + timedelta(days=cfg["rebuild_days"] + stagger)).isoformat())
                else:
                    store = fetch_incr(ga, old, end, cfg["refetch_days"], stop=over)
                if revs and not moved:
                    store["revisions"] = revs
                elif moved:
                    store.pop("revisions", None)        # another stream's re-reads say nothing about this one
                record_revisions(store, base, _local_day(now, tz), store["last_window"], cfg["refetch_days"])
                store.update(v=STORE_V, app_id=aid, package=a.get("package"), property_id=str(pid),
                             stream_id=str(r["stream_id"]), time_zone=tz, fetched_at=_now_iso(now))
                store.setdefault("den", "a28")
                save_store(path, store)
                if outdated:                            # its alerts came from the older (unchecked) data: start
                    reset_alerts(state, aid)            # over — the next evaluation seeds, nothing is sent
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
