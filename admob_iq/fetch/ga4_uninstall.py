"""GA4 → per-app uninstall store (data/ga4_uninstall/), fetched inside the hourly build.

Four Data API reports per app, all pinned to the app's Android stream by Ga4App:
  * daily     date → newUsers, activeUsers, active28DayUsers           (installs + the rate denominator)
  * events    date × eventName → totalUsers, eventCount for app_remove / app_update
  * cells     firstSessionDate × date → app_remove users               (the install-cohort churn cells; app_remove
                                                                         EVENTS instead past the users edge, below)
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
flags.incomplete_days {day: coverage} — as GA4 returned it: the engine fills one holding ≥ 70% up to its total at
evaluation time (an estimate, engine.uninstall.fill_days) and leaves the rest out (the tab says "data adhoora"). Rows
GA4 folds into "(other)" never count as covered. When the shortfall is GA4's own (days short even alone), or
the fetch spent its call cap / run budget, a short slice is kept with its short days flagged instead of split
further; a re-read that comes back short never replaces cells we hold in full (keep_best). The slice size
that verified is remembered per app (cells_chunk_days, and events_chunk_days for the events path below) and grown
back slowly.

USERS LOST BY AGE → EVENTS: on some properties GA4 loses the install-day split of app_remove USERS for days older
than ~2 months (seen live: 2–25% of them, at ANY slice length, even one day), while the app_remove EVENT counts by
install day stay (nearly) complete there. So each app learns the age (users_ok_days, days before window_end) past
which its users cells go short — a probe of one day ALONE at the oldest age that can be judged when the first slice
reads short, halved down to the edge (~11 probes for 1,300 days; a short probe counts only when the day past it is
short too — one day GA4 answers short at any range is no loss by age), never under EDGE_MIN_DAYS, then one probe
past the edge per full re-pull to see it move — and reads the days older than that straight from the EVENTS path:
the same checked slices, against daily un_ev (≥ EVENTS_MIN_COVERAGE: an exact count, not a sketch). Each complete
day's events cells are its SPLIT by install day, scaled as one to the day's app_remove users × the app's users-cell
scale (_users_k: what its verified users days read per un, ~98–107%) — so an old day sits on the same scale as the
recent users days every alert compares it with; the split assumes users are the same share of the events at every
install age. A day whose users cells stay short even alone is re-read the same way (events can be ~85% on RECENT
days, so users stay the first choice there); a day short both ways stays flagged incomplete.

BEST VERSION PER EVENT DAY: every day's cells carry their provenance, cell_src[day] = {src: users | events_scaled,
cov, k (the scale, events), at}. A re-read (incremental, full re-pull, repair) replaces a day only when it is at
least as good (keep_best): complete users beat an events estimate beat an incomplete read; within one grade the
higher coverage against the day's count NOW, then the newer (late data only adds: a lower complete re-read lost
something). Held cells that late data left short are no longer complete, and stay only flagged. So a day verified
while it was young is never overwritten by the degraded answer GA4 gives for it later — a full re-pull does not
even ask for the old days it holds complete. A v2 store (before provenance) is REPAIRED at once (fetch_repair:
only its incomplete days, by events; the verified ones stay; a failed repair is tried again a day later, the
incrementals carry on meanwhile), and its alert history starts over only when that moved > 1% of its all-time
uninstalls on the days an alert can use.

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
EVENTS_MIN_COVERAGE = 0.95  # the events path's slice AND day: app_remove EVENTS are an exact count, not a sketch (a
                            # complete read is 100%); old days seen live at 100% and 96.8% (both taken), 77% (flagged)
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
CHECKED_V = 2               # 2: cells verified against the events report (v1 stores undercount big apps' cohorts) —
                            # plan() re-pulls a v1 store in full at once and its alert history starts over
STORE_V = 3                 # 3: per-day provenance (cell_src), the events-scaled fallback, the users edge — plan()
                            # REPAIRS a v2 store at once (its incomplete days only), see fetch_repair
USERS, EVENTS_SCALED = "users", "events_scaled"
PROBE_MAX_DAYS = 7          # an age probe asks ONE day's users cells (+ the days before it, up to 7 in all, while
                            # they hold < CELLS_MIN_USERS)
PROBE_MAX = 24              # probes per fetch at most (halving 1,300 days down to the day takes 11, + ~6 confirmations)
EDGE_RUN = 3                # a users loss by age the users pass runs into itself: its oldest ≥3 judged days all
                            # short even alone (or like them) → the edge moves before them …
EDGE_MIN_DAYS = 28          # … unless that puts it under 28 days: GA4 keeps user data ≥ 2 months, so a shortfall that
                            # young is something else — an edge only READ OFF flags is never trusted under it (the
                            # probes, which measure it, decide at the next full re-pull)
EV_GAP_DAYS = 7             # short days ≤7 days apart are re-read by events in ONE slice (the days between keep their
                            # users cells — complete users beat an estimate)
GRADE_TIE = 0.01            # two reads of one grade within 1 point: a tie (→ users in a fetch, the newer in a merge)
SCALE_MIN_DAYS = 7          # the users-cell scale (_users_k) needs ≥7 verified users days, else the one stored / 1.0
REPAIR_MATERIAL = 0.01      # a v2 → v3 upgrade that moved > 1% of the app's all-time uninstalls resets its alerts
REPAIR_RETRY_HOURS = 24     # a repair that failed is tried again a day later — incrementals go on meanwhile
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


def rep_cells(ga, start, end, metric="totalUsers"):
    """app_remove users by install day × event day, for every uninstall with its EVENT date in [start, end]
    (no firstSessionDate filter: old cohorts keep uninstalling). Newest cohorts first, as probe_t13.
    metric "eventCount": app_remove EVENTS instead — the events path (see the module docstring)."""
    return ga.report_all({"dateRanges": [_rng(start, end)], "dimensions": ga4._dim("firstSessionDate", "date"),
                          "metrics": ga4._dim(metric),
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
            "cells_log": [], "cov": {}, "gone": set(), "cell_src": {}, "probes": 0}


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


def _place_cells(p, rows, place_from, m="totalUsers"):
    """Cells → cohorts[install day][lag]; a row with no usable install day (not a date, "(other)", before
    the history, or after the event) goes to unplaced[event day] — kept visible, never guessed. m = the
    metric the rows carry (eventCount on the events path)."""
    for r in rows:
        u = int(r.get(m) or 0)
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

def _need(metric="totalUsers"):
    """(slice, day) coverage a cells read needs to be complete: users are sketches (CELLS_MIN_COVERAGE, and
    CELLS_DAY_MIN_COVERAGE a day inside the slice), the events path's eventCount an exact count (EVENTS_MIN_COVERAGE
    both)."""
    return ((EVENTS_MIN_COVERAGE, EVENTS_MIN_COVERAGE) if metric == "eventCount"
            else (CELLS_MIN_COVERAGE, CELLS_DAY_MIN_COVERAGE))


def cells_judge(got, daily, days, need=None):
    """Cell users by event day (`got`, see _covered) vs the events report's app_remove users (daily[d].un)
    over `days` → (coverage, or None when too few users to judge; complete?). Complete = the slice holds
    ≥ CELLS_MIN_COVERAGE and no judged day inside it is under CELLS_DAY_MIN_COVERAGE (`need`: other (slice,
    day) shares, see _need)."""
    lo, day_lo = need or _need()
    want = sum(_un(daily, d) for d in days)
    if want < CELLS_MIN_USERS:
        return None, True
    cov = sum(got.get(d, 0) for d in days) / want
    for d in days:
        u = _un(daily, d)
        if u >= CELLS_MIN_USERS and got.get(d, 0) < day_lo * u:
            return cov, False
    return cov, cov >= lo


def _un(daily, d):
    return int((daily.get(d) or {}).get("un") or 0)


def _covered(rows, a, b, m="totalUsers"):
    """Cell users by event day in [a, b] — cells_judge's `got` — from the rows whose install day is a DATE
    (one before the history counts: it is placed as an older install). "(other)" / unparseable ones don't:
    GA4 folds a report it finds too big into "(other)", and those users reach no cohort — a slice full of
    them must read short, not complete. m = the metric (eventCount: events by day, judged against un_ev)."""
    got = {}
    for r in rows:
        d = ga4._d(r.get("date"))
        if d is not None and a <= d <= b and ga4._d(r.get("firstSessionDate")) is not None:
            got[d.isoformat()] = got.get(d.isoformat(), 0) + int(r.get(m) or 0)
    return got


def short_days(got, daily, days, need=None):
    """The days of a slice KEPT short (see _fetch_cells) → {day: coverage}: every judged day under
    CELLS_MIN_COVERAGE (need[0], see _need), and — when the other days still fall short together — every other
    day under it too, so a shortfall the slice proved is never left unflagged."""
    lo = (need or _need())[0]
    under = {d: round(got.get(d, 0) / _un(daily, d), 4) for d in days
             if _un(daily, d) and got.get(d, 0) < lo * _un(daily, d)}
    big = {d: c for d, c in under.items() if _un(daily, d) >= CELLS_MIN_USERS}
    return big if cells_judge(got, daily, [d for d in days if d not in big], need)[1] else under


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
            or cells_judge(rec["got"], daily, [d for d in rec["span"] if d not in alone], rec.get("need"))[1])


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


def _start_chunk(store, key="cells_chunk_days"):
    try:
        return min(FULL_CHUNK_DAYS, max(1, int((store or {}).get(key) or FULL_CHUNK_DAYS)))
    except (TypeError, ValueError):
        return FULL_CHUNK_DAYS


def _fetch_cells(ga, p, start, end, place_from, cut, chunk, stop=None, metric="totalUsers", pre=None, limit=None):
    """Cells over [start, end] into `p`, slice by slice, each checked (cells_judge) against p["daily"] — the
    events report of the same days, fetched first. A short slice's rows are thrown away WHOLE (never counted
    twice) and its two halves asked instead, down to single days; a single day still short is kept and
    recorded in p["incomplete"] {day: coverage} (and p["alone"]) — shown, never hidden. Halves too small to
    judge (CELLS_MIN_USERS) are judged together: a shortfall their parent proved stays flagged on their days.
    A short slice is KEPT whole instead, its short days flagged (short_days), once CELLS_ALONE_STOP days were
    short even alone and it reads like them at a size no longer than one that verified (GA4's own shortfall:
    splitting gains nothing — rec["alike"]), or once the fetch spent its `limit` of slices (default
    CELLS_MAX_CALLS + one per 2 days) or `stop()` (the run budget) says so. Slices start at `chunk` days;
    after a slice needed splitting, the next ones start at the size that worked. Every slice asked goes to
    p["cells_log"] (see next_chunk). Asking again while the property's quota is low raises QuotaLow.
    metric "eventCount" = the events path (p["daily"][d]["un"] then holds the day's app_remove EVENTS; judged
    by _need). The base slices are bounded too: once what is left can't be read at `chunk` within the `limit`
    (or `stop()` says so), it is read in longer slices (≤ FULL_CHUNK_DAYS; past the limit none is split — every
    day read, a short one flagged). pre = (a, b, rows, truncated) of the first slice, already asked. p["cov"][day] =
    [coverage, judged?] of the slice each day's rows were kept from; p["gone"] = the days short even alone, or
    like them. → the slice size reached (the next range starts there)."""
    log, daily, alone, inc = p["cells_log"], p["daily"], p["alone"], p["incomplete"]
    covs, gone = p["cov"], p["gone"]
    limit = CELLS_MAX_CALLS + ((end - start).days + 1) // 2 if limit is None else limit
    need = _need(metric)

    def ask(a, b, given=None):
        """→ (cell users by day, as kept; judged?)"""
        n = (b - a).days + 1
        rows, trunc = given if given else (rep_cells(ga, a, b, metric), None)
        if trunc is None:
            trunc = ga.truncated(rows)
        got = _covered(rows, a, b, metric)
        span = [d.isoformat() for d in _days(a, b)]
        cov, ok = cells_judge(got, daily, span, need)
        rec = {"days": n, "cov": cov, "ok": ok, "got": got, "span": span, "need": need}
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
                if loose:
                    jc, jok = cells_judge(both, daily, [d for d in span if d not in inc], need)
                    for x, y in loose:
                        for d in (z.isoformat() for z in _days(x, y)):
                            if jc is not None and d in covs:
                                covs[d][1] = True        # judged after all: together with its sibling
                            u = _un(daily, d)
                            if not jok and u and both.get(d, 0) < need[0] * u:
                                inc[d] = round(both.get(d, 0) / u, 4)
                                if x == y:
                                    alone[d] = inc[d]
                                    gone.add(d)
                return both, True
        if trunc:
            cut.add("cells")
        _place_cells(p, rows, place_from, metric)
        for d in span:
            u = _un(daily, d)
            covs[d] = [round(got.get(d, 0) / u, 4) if u else None, cov is not None]
        if not ok and n == 1:
            inc[span[0]] = alone[span[0]] = round(cov, 4)
            gone.add(span[0])
        elif not ok:
            for d, c in short_days(got, daily, span, need).items():
                inc.setdefault(d, c)
                if rec.get("alike"):
                    gone.add(d)
        return got, cov is not None

    cur, cs = chunk, start
    while cs <= end:                           # parsed slice by slice: never ~1M row dicts in memory at once
        if pre and pre[0] == cs:
            ce, given = pre[1], pre[2:]        # the first slice, already asked
        else:
            left = 1 if stop and stop() else limit - len(log)   # base slices, too, stay within the limit: the
            cur = min(FULL_CHUNK_DAYS, max(cur, -(-((end - cs).days + 1) // max(1, left))))   # rest in longer ones
            ce, given = min(cs + timedelta(days=cur - 1), end), None
        pre = None
        mark = len(log)
        ask(cs, ce, given)
        mine = log[mark:]
        short = [r["days"] for r in mine if not r["ok"] and not _explained(r, daily, alone, log)]
        if short:
            cur = max([r["days"] for r in mine if _works(r) and r["days"] < min(short)], default=cur)
        cs = ce + timedelta(days=1)
    return cur


# ── users lost by age: the edge, and the events path past it ────────────────────────────────────

def _probe_win(daily, start, end, age):
    """The days a probe of `age` asks: the day `age` days before `end` ALONE — with the days before it (after it
    at the history's start), up to PROBE_MAX_DAYS in all, while they hold < CELLS_MIN_USERS app_remove users →
    (first, last), or None: outside [start, end], or too few users to say even so."""
    d = end - timedelta(days=age)
    if not start <= d <= end:
        return None
    a = b = d
    want = _un(daily, d.isoformat())
    while want < CELLS_MIN_USERS and (b - a).days + 1 < PROBE_MAX_DAYS and (a > start or b < end):
        if a > start:
            a -= timedelta(days=1)
            want += _un(daily, a.isoformat())
        else:
            b += timedelta(days=1)
            want += _un(daily, b.isoformat())
    return (a, b) if want >= CELLS_MIN_USERS else None


def _oldest_judged(daily, start, end):
    """The oldest age a probe can judge (_probe_win) — an app's launch weeks often can't (too few uninstalls) —
    or None: no age can."""
    for age in range((end - start).days, -1, -1):
        if _probe_win(daily, start, end, age):
            return age
    return None


def _probe(ga, p, start, end, age):
    """Are the users cells of the day `age` days before `end` short? Its _probe_win asked → (True complete,
    False short, None: too few users to say, or PROBE_MAX probes spent — no call; the window or None). A users
    loss by AGE shows at any slice length."""
    w = _probe_win(p["daily"], start, end, age)
    if w is None or p["probes"] >= PROBE_MAX:
        return None, w
    if _quota_low(ga.quota):
        raise QuotaLow("quota low while probing where users cells go short")
    p["probes"] += 1
    a, b = w
    rows = rep_cells(ga, a, b)
    return cells_judge(_covered(rows, a, b), p["daily"], [x.isoformat() for x in _days(a, b)])[1], w


def _lost(ga, p, start, end, age):
    """Is the day `age` days before `end` past the users edge? Its probe short, CONFIRMED by a second probe — of
    the nearest day older than the first one's days (younger when none older can be judged): a loss by age holds
    for every older day, while one day GA4 answers short at any range (seen live) is no loss by age. → True
    (lost; also when the second probe can't say), False, None (the first can't say)."""
    ok, w = _probe(ga, p, start, end, age)
    if ok is not False:
        return None if ok is None else False
    older, younger = (end - w[0]).days + 1, (end - w[1]).days - 1
    nxt = older if _probe_win(p["daily"], start, end, older) else younger
    return _probe(ga, p, start, end, nxt)[0] is not True


def _find_edge(ga, p, start, end, good, bad):
    """The oldest age whose users cells read complete, between `good` (reads complete; −1: none known) and
    `bad` (lost), by halving — the loss grows with age (each short probe confirmed, _lost). A probe that can't
    say counts as complete: the users pass still checks every day it reads, and a short one there goes to the
    events path anyway. Never under EDGE_MIN_DAYS (GA4 keeps user data ≥ 2 months: a shortfall that young is
    something else) — −1, every age short (the newest too), stays."""
    while bad - good > 1:
        mid = (good + bad) // 2
        if _lost(ga, p, start, end, mid):
            bad = mid
        else:
            good = mid
    return good if good < 0 else max(good, EDGE_MIN_DAYS)


def _edge_first(ga, p, start, end, chunk, edge, stop):
    """Before a FULL fetch's users pass: where its users cells can be trusted → (edge, pre). edge = the oldest
    age (days before `end`) whose users cells read complete — None: no loss by age seen, −1: none complete.
    No loss seen yet: the oldest slice is asked first (what the users pass asks first anyway — handed over as
    `pre`, so a complete one costs nothing); only when it reads short (or too few users to judge) is the oldest
    day that CAN be judged asked alone — lost there too (_lost) is a loss by age, and halving finds its edge
    (the slice is dropped: its days go by events). A known edge: one probe of the day past it — complete there,
    the edge moved (the oldest day that can be judged, then halving). Nothing when the run budget is spent."""
    if stop and stop():
        return edge, None
    oldest, top = (end - start).days, _oldest_judged(p["daily"], start, end)
    if edge is None:
        a, b = start, min(start + timedelta(days=chunk - 1), end)
        rows = rep_cells(ga, a, b)
        pre = (a, b, rows, ga.truncated(rows))
        cov, ok = cells_judge(_covered(rows, a, b), p["daily"], [x.isoformat() for x in _days(a, b)])
        if (ok and cov is not None) or top is None or not _lost(ga, p, start, end, top):
            return None, pre                          # the day alone is fine: the slice's LENGTH, split as ever
        return _find_edge(ga, p, start, end, -1, top), None
    if edge < oldest and _probe(ga, p, start, end, edge + 1)[0]:
        if top is None or top <= edge + 1:
            return edge, None                         # nothing older can say where the loss starts now
        if _lost(ga, p, start, end, top):
            return _find_edge(ga, p, start, end, edge + 1, top), None
        return None, None
    return edge, None


def _edge_tail(p, u_from, end, edge):
    """A users loss by age the users pass ran into itself (an edge set too old): its oldest EDGE_RUN+ judged
    days all short even alone, or like them (p["gone"]) → the edge moves to the day before them (not under
    EDGE_MIN_DAYS)."""
    run = []
    for x in _days(u_from, end):
        k = x.isoformat()
        if _un(p["daily"], k) < CELLS_MIN_USERS:
            continue                                  # too few users to say either way
        if k not in p["gone"]:
            break
        run.append(x)
    a = (end - run[-1]).days - 1 if run else -1
    if len(run) < EDGE_RUN or a < EDGE_MIN_DAYS:
        return edge
    return a if edge is None else min(edge, a)


def _stored_edge(store):
    """The users edge a store knows: its users_ok_days (None: no loss by age seen) — or, a v2 store without one,
    read off its incomplete days: its oldest EDGE_RUN+ judged days all flagged → the day before them (None
    under EDGE_MIN_DAYS: flags that young say nothing about age)."""
    if not store or not store.get("history_start") or not store.get("window_end"):
        return None
    if "users_ok_days" in store:
        e = store["users_ok_days"]
        return e if isinstance(e, int) and not isinstance(e, bool) and e >= -1 else None
    inc = (store.get("flags") or {}).get("incomplete_days") or {}
    daily, we = store.get("daily") or {}, _d(store["window_end"])
    run = []
    for x in _days(_d(store["history_start"]), we):
        k = x.isoformat()
        if _un(daily, k) < CELLS_MIN_USERS:
            continue
        if k not in inc:
            break
        run.append(x)
    a = (we - run[-1]).days - 1 if run else -1
    return a if len(run) >= EDGE_RUN and a >= EDGE_MIN_DAYS else None


def _runs(days, gap):
    """Sorted dates → [[first, last]] of runs whose neighbours are at most `gap` days apart."""
    out = []
    for x in days:
        if out and (x - out[-1][1]).days <= gap:
            out[-1][1] = x
        else:
            out.append([x, x])
    return out


def _pad(run, daily, start, end):
    """A run of short days too small to judge by events alone (< CELLS_MIN_USERS app_remove events) takes in
    the days around it (≤ EV_GAP_DAYS a side) until it can be judged — they keep their own cells."""
    a, b = run
    want = sum(_un(daily, x.isoformat()) for x in _days(a, b))
    for _ in range(EV_GAP_DAYS):
        if want >= CELLS_MIN_USERS:
            break
        if a > start:
            a -= timedelta(days=1)
            want += _un(daily, a.isoformat())
        if b < end and want < CELLS_MIN_USERS:
            b += timedelta(days=1)
            want += _un(daily, b.isoformat())
    return [a, b]


def _scale_day(items, ratio):
    """One event day's events cells [(key, events)] → {key: users}: each × ratio (users per event, see
    _take_events), rounded by largest remainder so the day adds up to round(Σ events × ratio) — whole users, the day's
    total within one of the exact product; a cell of a single event can round to 0 (ties by key: deterministic)."""
    want = int(round(sum(e for _, e in items) * ratio))
    raw = [(k, e * ratio) for k, e in items]
    got = {k: int(x) for k, x in raw}
    for k, x in sorted(raw, key=lambda kx: (int(kx[1]) - kx[1], str(kx[0])))[:max(0, want - sum(got.values()))]:
        got[k] += 1
    return got


def _drop_days(p, days):
    """Every cell (and unplaced count) of the event days in `days` out of p, in place."""
    cells = p["cohorts"]
    for f in list(cells):
        fd, lags = _d(f), cells[f]
        for lag in [k for k in lags if (fd + timedelta(days=int(k))).isoformat() in days]:
            del lags[lag]
        if not lags:
            del cells[f]
    for k in days:
        p["unplaced"].pop(k, None)


def _users_k(p, held=None):
    """The users-cell scale: cell users per app_remove user of the events report (daily un) on the users report's
    verified days of this read (≥ CELLS_MIN_USERS, not flagged) — their median; with fewer than SCALE_MIN_DAYS
    of them, the one `held` (default p) last used (flags.users_k), else 1. User counts are sketches: a complete
    users day reads ~98–107% of un, app by app — the events path scales its days to THIS, so an old (events) day
    sits on the scale of the recent (users) ones every alert compares it with."""
    src, inc, daily = p.get("cell_src") or {}, p.get("incomplete") or {}, p["daily"]
    days = [k for k, s in src.items() if (s or {}).get("src") == USERS and k not in inc and k in daily
            and _un(daily, k) >= CELLS_MIN_USERS]
    if len(days) >= SCALE_MIN_DAYS:
        tot = _day_totals(p, days)
        r = sorted(tot[k] / _un(daily, k) for k in days)
        return round(r[len(r) // 2], 4)
    try:
        return float((((p if held is None else held).get("flags") or {}).get("users_k")) or 1.0)
    except (TypeError, ValueError):
        return 1.0


def _take_events(p, pe, take, at, scale=1.0):
    """The days in `take` ({day: (flag or None, coverage)}) get their cells from the events path's `pe`, in
    place of what p holds for them — their flag and provenance (events_scaled, its coverage and scale) with
    them. Each day's cells are scaled as ONE (_scale_day): a complete day to its app_remove users on the
    users-cell scale (daily un × scale, _users_k — the events it read are the SPLIT by install day, the day's
    total comes from the events report), a short one by un × scale ÷ un_ev (its shortfall stays in sight).
    Assumed: users are the same share of the events at every install age (live: ~2–5% fewer per day)."""
    if not take:
        return
    _drop_days(p, take)
    items = {}
    for f, lags in pe["cohorts"].items():
        fd = _d(f)
        for lag, e in lags.items():
            k = (fd + timedelta(days=int(lag))).isoformat()
            if k in take:
                items.setdefault(k, []).append(((f, lag), e))
    for k, e in pe["unplaced"].items():
        if k in take:
            items.setdefault(k, []).append((None, e))
    for day in sorted(take):
        flag, cov = take[day]
        r, its = p["daily"].get(day) or {}, items.get(day) or []
        u, uev, got = int(r.get("un") or 0), int(r.get("un_ev") or 0), sum(e for _, e in its)
        base = uev if flag is not None and uev else got
        for key, n in _scale_day(its, u * scale / base if base else 0.0).items():
            if not n:
                continue
            if key is None:
                p["unplaced"][day] = p["unplaced"].get(day, 0) + n
            else:
                c = p["cohorts"].setdefault(key[0], {})
                c[key[1]] = c.get(key[1], 0) + n
        if flag is None:
            p["incomplete"].pop(day, None)
        else:
            p["incomplete"][day] = flag
        p["cell_src"][day] = {"src": EVENTS_SCALED, "cov": cov, "k": scale, "at": at}


def _held_src(store):
    """→ fn(day) → the provenance of `store`'s cells for that event day, or None when it holds nothing for it.
    A covered day with none (a store from before provenance) came from the users report."""
    cs = (store or {}).get("cell_src") or {}
    cov = [(_d(a), _d(b)) for a, b in (store or {}).get("covered") or []]

    def src(k):
        s = cs.get(k)
        if s is None and any(a <= _d(k) <= b for a, b in cov):
            return {"src": USERS, "cov": None, "at": None}
        return s
    return src


def _held_best(held, daily, a, b):
    """The event days in [a, b] (older than the users edge) whose cells `held` holds COMPLETE and still complete
    against the new count (`daily`, see _grade): from the users report — nothing read later can beat them — or
    from the events path (GA4 keeps an old day's events as they were: a re-read ties at best). A full re-pull
    doesn't ask for them."""
    if not held or a > b or _store_v(held) < CHECKED_V:
        return set()
    days = [x.isoformat() for x in _days(a, b)]
    src, tot = _held_src(held), _day_totals(held, days)
    fl = (held.get("flags") or {}).get("incomplete_days") or {}
    return {k for k in days if src(k) and _grade(src(k), fl.get(k), tot[k], _un(daily, k), True)[0] >= 1}


def _events_pass(ga, p, start, end, place_from, cut, echunk, stop=None, old_to=None, held=None, at=None, force=False):
    """The events path over [start, end] into `p`: the days up to `old_to` (older than the users edge — never
    read by users; those `held` holds complete are skipped, _held_best), and the days p flags short from
    the users report (in runs ≤ EV_GAP_DAYS apart, _pad-ded to be judged) — the latter left alone once the run
    budget is spent (unless `force`: a repair). Checked slice by slice as the users cells (_fetch_cells,
    against daily un_ev, _need), the size starting at `echunk`. Per day: a day never read by users takes the
    events read (flagged when short); a users day short takes it when complete (judged), or short but better by
    > GRADE_TIE; a complete users day keeps its cells. A day the events report counts no app_remove event for
    while it counts ≥ CELLS_MIN_USERS users can't be checked: flagged. Every day taken is scaled (_take_events)
    to p["k"] (_users_k). → the next events slice size (next_chunk)."""
    daily = p["daily"]
    p["k"] = _users_k(p, held)
    skip = _held_best(held, daily, start, old_to) if old_to is not None else set()
    old = [] if old_to is None or old_to < start else [x for x in _days(start, old_to) if x.isoformat() not in skip]
    fb = sorted(_d(k) for k in p["incomplete"]
                if start <= _d(k) <= end and (old_to is None or _d(k) > old_to))
    if fb and not force and stop and stop():
        fb = []                                     # the run budget is spent: short days stay flagged
    if fb and _quota_low(ga.quota):
        raise QuotaLow("quota low before re-reading short days by events")
    ev = {x.isoformat(): {"un": int((daily.get(x.isoformat()) or {}).get("un_ev") or 0)} for x in _days(start, end)}
    runs = []
    for a, b in sorted(_runs(old, 1) + [_pad(r, ev, start, end) for r in _runs(fb, EV_GAP_DAYS + 1)]):
        if runs and a <= runs[-1][1] + timedelta(days=1):
            runs[-1][1] = max(runs[-1][1], b)
        else:
            runs.append([a, b])
    if not runs:
        return echunk
    pe = {"daily": ev, "cohorts": {}, "unplaced": {}, "bad_rows": 0, "incomplete": {}, "alone": {},
          "cells_log": [], "cov": {}, "gone": set()}
    limit = CELLS_MAX_CALLS + sum((b - a).days + 1 for a, b in runs) // 2
    cur = echunk
    for a, b in runs:
        cur = _fetch_cells(ga, pe, a, b, place_from, cut, cur, stop, "eventCount", limit=limit)
    p["bad_rows"] += pe["bad_rows"]
    take = {}
    for a, b in runs:
        for x in _days(a, b):
            k = x.isoformat()
            if k in skip:
                continue
            flag, (cov, judged) = pe["incomplete"].get(k), pe["cov"].get(k) or (None, False)
            if flag is None and not ev[k]["un"] and _un(daily, k) >= CELLS_MIN_USERS:
                flag = 0.0                              # users but no event that day: the read can't be checked
            mine = p["cell_src"].get(k)
            if mine is None or mine.get("src") != USERS:
                take[k] = (flag, cov)                   # nothing from users: the events read is what there is
                continue
            uf = p["incomplete"].get(k)
            if uf is not None and ((flag is None and judged) or (flag is not None and flag > uf + GRADE_TIE)):
                take[k] = (flag, cov)
    _take_events(p, pe, take, at, p["k"])
    return next_chunk(pe["cells_log"], echunk, ev, pe["alone"])


def _fetch_all_cells(ga, p, start, end, place_from, cut, chunk, stop=None, edge=None, echunk=FULL_CHUNK_DAYS,
                     full=False, held=None, at=None):
    """Every event day's cells in [start, end] into `p`, the best read of each: from the users report for the
    days no older than `edge` (the app's users_ok_days; a FULL fetch checks it first, _edge_first, and moves it
    by what its users pass ran into, _edge_tail), from the events path for the older ones and for the users
    days that stayed short (_events_pass). p["cell_src"] = each day's provenance, p["edge"] = the edge now,
    p["echunk"] = the next events slice size."""
    pre = None
    if full:
        edge, pre = _edge_first(ga, p, start, end, chunk, edge, stop)
    u_from = start if edge is None else max(start, end - timedelta(days=edge))
    if u_from <= end:
        _fetch_cells(ga, p, u_from, end, place_from, cut, chunk, stop, pre=pre if pre and pre[0] == u_from else None)
        if full:
            edge = _edge_tail(p, u_from, end, edge)
        for x in _days(u_from, end):
            k = x.isoformat()
            p["cell_src"][k] = {"src": USERS, "cov": (p["cov"].get(k) or [None])[0], "at": at}
    p["echunk"] = _events_pass(ga, p, start, end, place_from, cut, echunk, stop, old_to=u_from - timedelta(days=1),
                               held=held, at=at)
    p["edge"] = edge


def _fetch_window(ga, start, end, den, place_from, cut, daily=None, chunk=FULL_CHUNK_DAYS, stop=None, cells=None):
    """daily + REPORTS + cells over [start, end] → parsed window. `cut` collects capped report names.
    `daily` = daily rows already fetched over a window covering [start, end] (rows outside it are skipped).
    `chunk` = the users cells slice size to start with, `stop` = the run budget (see _fetch_cells), `cells` =
    _fetch_all_cells' options (edge, echunk, full, held, at)."""
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
    _fetch_all_cells(ga, p, start, end, place_from, cut, chunk, stop, **(cells or {}))
    return p


# ── full + incremental fetch ────────────────────────────────────────────────────────────────────

def fetch_full(ga, end, max_history_days, old_store=None, stop=None, held=True, at=None):
    """The app's whole history: the daily report over the widest window finds where its data starts
    (history_start), then the other reports from there. Cells whose install day is older than that but
    still inside `old_store`'s history are placed into those older cohorts. `stop` = the run budget (see
    _fetch_cells). held: `old_store` is this stream's — its users edge and events slice size are used, and
    its old days held as complete users cells are not asked by events (nothing could beat them, keep_best);
    False (the app moved to another stream): none of that. `at` = the fetch's day, into cell_src (default
    the window end). Raises on any failure (the caller keeps the old store)."""
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
    chunk = _users_chunk(old_store)
    mem = old_store if held else None
    echunk = _start_chunk(mem, "events_chunk_days")
    p = _fetch_window(ga, hs, end, den, place_from, cut, daily=rows, chunk=chunk, stop=stop,   # daily rows reused
                      cells={"edge": _stored_edge(mem), "echunk": echunk, "full": True, "held": mem,
                             "at": at or end.isoformat()})
    del rows
    return {"v": STORE_V, "den": p["den"], "history_start": hs.isoformat(), "window_end": end.isoformat(),
            "history_capped": hs <= start0, "covered": [[hs.isoformat(), end.isoformat()]],
            "daily": p["daily"], "cohorts": p["cohorts"], "unplaced": p["unplaced"], "versions": p["versions"],
            "cell_src": p["cell_src"], "users_ok_days": p["edge"], "events_chunk_days": p["echunk"],
            "cells_chunk_days": next_chunk(p["cells_log"], chunk, p["daily"], p["alone"]),
            "last_window": [hs.isoformat(), end.isoformat()],
            "flags": {"truncated": sorted(cut), "thresholded": bool(ga.thresholded), "kept_old_before": None,
                      "bad_rows": p["bad_rows"], "incomplete_days": dict(sorted(p["incomplete"].items())),
                      "users_k": p.get("k")}}


def _users_chunk(store):
    """The users cells slice size to start with: the store's own — not a store from before v3's: it learned it
    while it took a users loss by AGE for a slice-length limit (the users pass now reads only younger days)."""
    return _start_chunk(store) if _store_v(store) >= STORE_V else FULL_CHUNK_DAYS


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


def _grade(src, flag, total, un, rejudge=False):
    """How good one event day's cells are → (tier, coverage), the higher the better: tier 2 = from the users
    report, complete; 1 = scaled from the events report, complete; 0 = incomplete — flagged, or (`rejudge`, for
    cells held from an earlier read) now under what a complete read holds of the day's app_remove users `un`
    (CELLS_MIN_COVERAGE; EVENTS_MIN_COVERAGE on the events' scale) — late data came in since, or it never held
    more; −1 = nothing read (`src` None). coverage = cells ÷ un (÷ un × the day's users-cell scale, events), and
    for a complete events day at most the share of its events the read placed (it is scaled to the day's total)."""
    if src is None:
        return (-1, 0.0)
    ev = src.get("src") == EVENTS_SCALED
    try:
        k = float(src.get("k") or 1.0) if ev else 1.0
    except (TypeError, ValueError):
        k = 1.0
    cov = total / (k * un) if un else (flag if flag is not None else 1.0)
    if ev and flag is None and isinstance(src.get("cov"), (int, float)):
        cov = min(cov, src["cov"])
    if flag is not None or (rejudge and un >= CELLS_MIN_USERS
                            and cov < (EVENTS_MIN_COVERAGE if ev else CELLS_MIN_COVERAGE)):
        return (0, cov)
    return (1 if ev else 2, cov)


def _better(held, new):
    """Held cells stay only when BETTER than the new read: a higher tier, or the same one at a coverage more
    than GRADE_TIE higher (late data only adds: a complete re-read lower than what we hold lost something).
    Otherwise the newer read wins."""
    if held[0] != new[0]:
        return held[0] > new[0]
    return held[1] > new[1] + GRADE_TIE


def keep_best(held, fetched, flags, a, b):
    """Day by day over [a, b]: where what `held` holds for an event day is BETTER than what `fetched` read
    (_grade / _better — each against the day's app_remove users now), held's cells go back into `fetched`
    (in place), with their provenance (cell_src) and their flag in `flags` (fetched's {day: coverage}, in
    place): complete users cells are never replaced by a degraded re-read nor by an events estimate, and a
    short re-read never by a shorter one. Held cells are judged again against the day's count now (_grade
    rejudge: late data may have left them short) — held cells kept short are FLAGGED at that coverage, and a
    held users day's cov is refreshed to it."""
    days = [x.isoformat() for x in _days(_d(a), _d(b))]
    src_h, src_n = _held_src(held), fetched.setdefault("cell_src", {})
    hfl = (held.get("flags") or {}).get("incomplete_days") or {}
    mine, new = _day_totals(held, days), _day_totals(fetched, days)
    nd, hd = fetched.get("daily") or {}, held.get("daily") or {}
    keep = {}
    for k in days:
        hs = src_h(k)
        if hs is None:
            continue
        un = _un(nd if k in nd else hd, k)
        hg = _grade(hs, hfl.get(k), mine[k], un, True)
        if _better(hg, _grade(src_n.get(k), flags.get(k), new[k], un)):
            keep[k] = (dict(hs, cov=round(mine[k] / un, 4)) if hs.get("src") == USERS and un else hs, hg)
    if not keep:
        return
    for src, dst in ((fetched, None), (held, fetched)):          # out with the re-read, in with ours
        for f, lags in list((src.get("cohorts") or {}).items()):
            fd = _d(f)
            for lag in [x for x in lags if (fd + timedelta(days=int(x))).isoformat() in keep]:
                if dst is None:
                    del lags[lag]
                else:
                    dst["cohorts"].setdefault(f, {})[lag] = lags[lag]
            if dst is None and not lags:
                del src["cohorts"][f]
    un = fetched.setdefault("unplaced", {})
    for k, (hs, g) in keep.items():
        un.pop(k, None)
        if (held.get("unplaced") or {}).get(k):
            un[k] = held["unplaced"][k]
        src_n[k] = hs
        if g[0] == 0:
            flags[k] = round(g[1], 4)
        else:
            flags.pop(k, None)


def merge_window(store, fetched, start, end, held=True):
    """Replace everything whose date falls in [start, end] with `fetched` (in place, returns `store`):
    daily + versions by date; cohort cells by EVENT date (install day + lag) — so an old cohort's recent
    uninstalls are refreshed, its older cells stay frozen until the next full re-pull; unplaced by date.
    A day keeps the cells we hold when they are better than the re-read's (keep_best; `held` False: never),
    and every day's provenance (cell_src) follows its cells."""
    start, end = _d(start), _d(end)
    got = fetched["incomplete"] if "incomplete" in fetched else (fetched.get("flags") or {}).get("incomplete_days")
    got = {k: v for k, v in (got or {}).items() if start <= _d(k) <= end}
    if held:
        keep_best(store, fetched, got, start, end)
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
    if "cell_src" not in store:                  # a store from before provenance: its covered days get theirs first
        _fill_src(store)
    src = store["cell_src"]
    for k in [k for k in src if start <= _d(k) <= end]:
        del src[k]
    src.update({k: v for k, v in (fetched.get("cell_src") or {}).items() if start <= _d(k) <= end})
    store["covered"] = _merge_ranges((store.get("covered") or []) + [[start, end]])
    store["window_end"] = max(_d(store.get("window_end") or end), end).isoformat()
    if not store.get("history_start") or start < _d(store["history_start"]):
        store["history_start"] = start.isoformat()
    return store


def fetch_incr(ga, store, end, refetch_days, stop=None, at=None):
    """The recent window (see incr_start) re-pulled and merged into `store` (in place, returned). Its users
    edge stays as it is (only a full re-pull moves it); days of the window past it go by events."""
    start = incr_start(store, end, refetch_days)
    cut = set()
    chunk = _users_chunk(store)
    cells = {"edge": _stored_edge(store), "echunk": _start_chunk(store, "events_chunk_days"), "held": store,
             "at": at or end.isoformat()}
    p = _fetch_window(ga, start, end, store.get("den") or "a28", _d(store["history_start"]), cut, chunk=chunk,
                      stop=stop, cells=cells)
    merge_window(store, p, start, end)
    store.update(cells_chunk_days=next_chunk(p["cells_log"], chunk, p["daily"], p["alone"]),
                 events_chunk_days=p["echunk"], users_ok_days=p["edge"])
    store["last_window"] = [start.isoformat(), end.isoformat()]
    fl = store.setdefault("flags", {})
    fl["truncated"] = sorted(set(fl.get("truncated") or []) | cut)
    fl["thresholded"] = bool(fl.get("thresholded")) or bool(ga.thresholded)
    fl["bad_rows"] = (fl.get("bad_rows") or 0) + p["bad_rows"]
    fl["users_k"] = p.get("k", fl.get("users_k"))
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
    they come from an unchecked store format (v < CHECKED_V) each of their days is checked now from what is
    stored, a short one flagged incomplete. A re-pull carrying < REBUILD_MIN_RATIO of the installs we already
    hold for the same days is rejected (ok False): a partial GA4 answer must never overwrite good history —
    nor, day by day, a better read with a worse one (keep_best: a day verified from the users report while it
    was young keeps its cells when GA4 answers it degraded later). check_ratio False = the app moved to
    another stream: no ratio check, and no day keeps the old stream's cells."""
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
            keep_best(old, new, inc, nhs, new["window_end"])
            new.setdefault("flags", {})["incomplete_days"] = dict(sorted(inc.items()))
        return new, True
    unchecked = _store_v(old) < CHECKED_V
    merged = merge_window(old, new, nhs, _d(new["window_end"]), held=check_ratio)
    inc = dict((merged.get("flags") or {}).get("incomplete_days") or {})
    if unchecked:
        inc.update(stored_coverage(merged, ohs, nhs - timedelta(days=1)))
    merged.update(history_start=ohs.isoformat(), history_capped=new.get("history_capped", False),
                  den=new.get("den") or "a28", users_ok_days=new.get("users_ok_days"),
                  events_chunk_days=new.get("events_chunk_days"))
    merged["flags"] = dict(new.get("flags") or {}, kept_old_before=nhs.isoformat(),
                           incomplete_days=dict(sorted(inc.items())))
    return merged, True


def _fill_src(store):
    """Every covered event day without a provenance gets one: its cells came from the users report (a store
    from before provenance — v2: checked; v1: its short days flagged by stored_coverage) — with its coverage
    vs the day's app_remove users, dated by the store's last fetch."""
    src = store.setdefault("cell_src", {})
    days = sorted({x.isoformat() for a, b in store.get("covered") or [] for x in _days(_d(a), _d(b))} - set(src))
    if not days:
        return
    tot, daily = _day_totals(store, days), store.get("daily") or {}
    at = (store.get("fetched_at") or "")[:10] or None
    for k in days:
        u = _un(daily, k)
        src[k] = {"src": USERS, "cov": round(tot[k] / u, 4) if u else None, "at": at}


def fetch_repair(ga, store, stop=None, at=None):
    """A v2 store (cells checked, the days GA4 answered short flagged incomplete) → v3, IN PLACE, reading ONLY
    what it lacks: its incomplete days, by the events path (with the days around them when too few events to
    judge alone — those keep their own cells); each day keeps the better read (users short vs events). Every
    verified day stays as it is, with provenance "users"; the users edge is read off the incomplete days (no
    call). The day's app_remove users / events it is judged against are the store's own, the users-cell scale
    its verified days' (_users_k). Every event slice is checked and split like a fetch's (`stop` = the run
    budget). Its users slice size starts over (_users_chunk). → Σ |change| of the cell users of the days it
    re-read (the caller judges what that moved, moved_share). Raises on any failure — QuotaLow too: the caller
    keeps the store on disk as it was."""
    hs, we = _d(store["history_start"]), _d(store["window_end"])
    store["users_ok_days"] = _stored_edge(store)
    store["cells_chunk_days"] = _users_chunk(store)
    _fill_src(store)
    fl = store.setdefault("flags", {})
    inc = {k: v for k, v in (fl.get("incomplete_days") or {}).items() if hs <= _d(k) <= we}
    if not inc:
        return 0
    p = {"daily": store.setdefault("daily", {}), "cohorts": store.setdefault("cohorts", {}),
         "unplaced": store.setdefault("unplaced", {}), "incomplete": dict(inc), "cell_src": store["cell_src"],
         "bad_rows": 0, "flags": fl}
    before, cut = _day_totals(store, list(inc)), set()
    store["events_chunk_days"] = _events_pass(ga, p, hs, we, hs, cut, _start_chunk(store, "events_chunk_days"), stop,
                                              at=at, force=True)
    rest = {k: v for k, v in (fl.get("incomplete_days") or {}).items() if k not in inc}
    fl["incomplete_days"] = dict(sorted(dict(rest, **p["incomplete"]).items()))
    fl["truncated"] = sorted(set(fl.get("truncated") or []) | cut)
    fl["bad_rows"] = (fl.get("bad_rows") or 0) + p["bad_rows"]
    fl["users_k"] = p.get("k", fl.get("users_k"))
    after = _day_totals(store, list(inc))
    return sum(abs(after[k] - before[k]) for k in inc)


def moved_share(before, store, flagged=()):
    """How much an upgrade moved what the alerts read (an incomplete day feeds none): Σ over the event days
    usable before or now of the cell users that changed — |now − `before`| (a _day_totals of the store before)
    on a day usable both times; a day usable only now (among `flagged`, the days incomplete before) or only
    before counts whole: it joined / left every baseline — ÷ the app's all-time app_remove users (daily un).
    A day short before and after moves nothing, however its cells changed. 0 without any."""
    inc = set((store.get("flags") or {}).get("incomplete_days") or {})
    flagged = set(flagged or ())
    days = sorted(set(before) | set(store.get("daily") or {}))
    now = _day_totals(store, days)
    total = sum(_un(store.get("daily") or {}, k) for k in store.get("daily") or {})
    moved = 0
    for k in days:
        if k in inc:
            moved += 0 if k in flagged else before.get(k, 0)
        else:
            moved += now[k] if k in flagged else abs(now[k] - before.get(k, 0))
    return moved / total if total else 0.0


def _all_days(store):
    """Every event day a store covers or holds anything for (ISO)."""
    return sorted(set(store.get("daily") or {}) | set(store.get("unplaced") or {}))


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


def repair_due(app_st, now):
    """May a v2 store's repair be tried now? Not within REPAIR_RETRY_HOURS of one that failed (repair_failed):
    a repair that keeps failing must never freeze the app's incrementals."""
    return _hours_since(app_st.get("repair_failed"), now) >= REPAIR_RETRY_HOURS


def plan(app_st, store, end, now, cfg):
    """None | "full" | "repair" | "incr" for one app this run. `store` = the store or its store_meta."""
    if app_st.get("fail") and _hours_since(app_st.get("last_try"), now) < cfg["retry_hours"]:
        return None                                     # a failed app waits retry_hours — even a moved one,
                                                        # so a stream we can't read isn't re-asked every hour
    if not store:
        return "full"
    if (str(store.get("property_id")), str(store.get("stream_id"))) != \
            (str(app_st.get("property_id")), str(app_st.get("stream_id"))):
        return "full"                                   # the app moved to another GA4 stream
    if CHECKED_V <= _store_v(store) < STORE_V and repair_due(app_st, now):
        return "repair"                                 # a v2 store: its incomplete days re-read NOW (fetch_repair) —
                                                        # after a failed one, a day later: incrementals meanwhile
    if _store_v(store) < CHECKED_V:                    # an unchecked store format: re-pulled clean NOW, not in ~20h
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

    counts = dict.fromkeys(("selected", "with_ga4", "fetched", "full", "repair", "fresh", "failed", "deferred",
                            "no_ga4"), 0)
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
        # incremental first (oldest first), then repairs, then full fetches (never fetched first); last run's
        # deferred lead
        rank = {"incr": 0, "repair": 1}
        todo.sort(key=lambda t: (not t[2].get("deferred"), rank.get(t[0], 2), t[2].get("last_ok") is not None,
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
                ov = _store_v(old if old else st.get("meta"))
                outdated = ov < CHECKED_V and bool(old or aid in state["eval"])
                # a v2 store (checked, before provenance) → v3: its alerts start over only if that moved its cells
                upgrade = CHECKED_V <= ov < STORE_V and not moved and bool(old or aid in state["eval"])
                base = None if moved else revision_base(old, tz)    # read before a fetch changes `old` in place
                revs = (old or {}).get("revisions")
                if kind == "repair" and (not old or moved):
                    kind = "full"
                if kind == "incr" and (not old or outdated):
                    kind = "full"
                if kind == "incr" and _store_v(old) < STORE_V and repair_due(st, now):
                    kind = "repair"                     # a v2 store is repaired before anything is added to it
                if kind == "incr":                      # (a failed repair: incrementals onto the v2 store
                    upgrade = False                     # meanwhile — it stays v2, the repair is tried again)
                before = _day_totals(old, _all_days(old)) if upgrade and old else None
                flagged = ((old.get("flags") or {}).get("incomplete_days") or {}) if upgrade and old else {}
                at = _local_day(now, tz).isoformat()
                if kind == "repair":                    # only the incomplete days, by events — no new day, so
                    store = old                         # fetched_at / last_ok / revisions stay the last fetch's
                    fetch_repair(ga, store, stop=over, at=at)
                    _fill_src(store)
                    store.update(v=STORE_V, repaired_at=_now_iso(now))
                    save_store(path, store)
                    if upgrade and moved_share(before, store, flagged) > REPAIR_MATERIAL:
                        reset_alerts(state, aid)        # the next evaluation seeds what the repaired days show
                    st.update(last_try=_now_iso(now), last_kind="repair", fail=None, fail_detail=None,
                              meta=store_meta(store))
                    st.pop("repair_failed", None)
                    out["apps"][aid] = "fetched"
                    counts["repair"] += 1
                    if _quota_low(ga.quota):
                        held_back.add(pid)
                    continue
                if kind == "full":
                    new = fetch_full(ga, end, cfg["max_history_days"], old, stop=over, held=not moved, at=at)
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
                                 events_chunk_days=new["events_chunk_days"], users_ok_days=new["users_ok_days"],
                                 last_window=new["last_window"],
                                 next_rebuild=(end + timedelta(days=cfg["rebuild_days"] + stagger)).isoformat())
                else:
                    store = fetch_incr(ga, old, end, cfg["refetch_days"], stop=over, at=at)
                if revs and not moved:
                    store["revisions"] = revs
                elif moved:
                    store.pop("revisions", None)        # another stream's re-reads say nothing about this one
                record_revisions(store, base, _local_day(now, tz), store["last_window"], cfg["refetch_days"])
                store.update(v=STORE_V if kind == "full" else _store_v(store), app_id=aid, package=a.get("package"),
                             property_id=str(pid), stream_id=str(r["stream_id"]), time_zone=tz,
                             fetched_at=_now_iso(now))
                store.setdefault("den", "a28")
                _fill_src(store)
                save_store(path, store)
                if outdated:                            # its alerts came from the older (unchecked) data: start
                    reset_alerts(state, aid)            # over — the next evaluation seeds, nothing is sent
                elif upgrade and (before is None or moved_share(before, store, flagged) > REPAIR_MATERIAL):
                    reset_alerts(state, aid)            # v2 → v3 by a full pull: the same rule as a repair (an
                                                        # unreadable v2 store can't show it didn't move: reset)
                st.update(last_try=_now_iso(now), last_ok=_now_iso(now), last_kind=kind, fail=None,
                          fail_detail=None, meta=store_meta(store))
                if kind == "full":
                    st.pop("repair_failed", None)
                out["apps"][aid] = "fetched"
                counts["full"] += kind == "full"
            except Exception as e:
                fk = _fail_kind(e)
                st.update(last_try=_now_iso(now), fail=fk, fail_detail=("%s: %s" % (type(e).__name__, e))[:300])
                if kind == "repair":
                    st["repair_failed"] = _now_iso(now)    # tried again a day later (repair_due)
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
