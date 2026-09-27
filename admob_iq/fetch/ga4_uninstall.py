"""GA4 → per-app uninstall store (data/ga4_uninstall/), fetched inside the hourly build.

Data API reports per app, all pinned to the app's Android stream by Ga4App:
  * daily     date → newUsers, activeUsers, active28DayUsers           (installs + the rate denominator)
  * events    date × eventName → totalUsers, eventCount for app_remove / app_update
  * cells     firstSessionDate × date → app_remove users               (the install-cohort churn cells; app_remove
                                                                         EVENTS instead past the users edge, below)
  * versions  date × appVersion → activeUsers                          (releases; Step 4 version scorecard)
  * usage     date × newVsReturning → activeUsers, sessions, userEngagementDuration     (update impact: per user)
  * vuse      date × appVersion × newVsReturning → the same                              (update impact: new vs old
                                                                                          version, same days)
  * ret       cohortSpec DAILY by firstSessionDate, day 0..30 → cohortActiveUsers / cohortTotalUsers (update impact:
              new users back next day / after 7 days; see fetch_ret)

UPDATE IMPACT (engine.impact): usage and vuse are two more per-date REPORTS (sums only — ratios like sessionsPerUser
are not additive; the engine divides the sums). A re-read replaces a day we hold only when it is not lower (late data
only adds: keep_best_days). A v3 store from before them is backfilled at its next fetch (impact_v, no STORE_V bump, no
alert reset); the new-user return cohorts are read newest → oldest, a few calls a fetch (fetch_ret), and GA4's
user-data edge (retention was 2 months until Sep 2026) is found by self-check, never assumed. None of it ever fails the
uninstall fetch: a failed impact read keeps what we hold and is tried again at the next fetch.

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

INSTALL VALUE (engine.value; only with the setting GA4_IDAY): a separate private file per app,
data/ga4_uninstall/iday/<key>.json.gz (+ <key>.old.json.gz, the frozen old parts), read after the return cohorts in
every full / incremental fetch (fetch_iday, never failing it). Per ACTIVITY day D, once it is final (D ≤ E − 3): Q-B
[firstSessionDate] (all countries, install ages 0..427, exact: the truth), Q-C [countryId, firstSessionDate] with
firstSessionDate inList D−90..D (countries, tied to Q-B: whatever GA4 did not give to a country stays visible as
"unassigned", never spread, never dropped), and Q-T [date] day totals per block of days. Each day is folded ONCE into
aggregates (install day × lag; install week × country × lag) + a per-day ledger; a newest → oldest cursor backfills
the history ≤ IDAY_MAX_CALLS calls a fetch. The main store is never touched by it.

Nothing here prints, and refresh_all never raises: a failing owner / app is recorded in the PRIVATE state
(state.json, never shipped) and the others carry on. The public build log gets one line of counts from
admob_iq.uninstall_build (and one more, iday_log_line, when GA4_IDAY is on).
"""

import copy
import functools
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
# ── update impact (mirrored in engine.impact: the engine never imports this requests-based module) ──
IMPACT_V = 1                # the impact data format: a store without it gets usage / vuse backfilled at its next fetch
                            # (no STORE_V bump, its alert history stays)
COHORT_DAYS = 30            # new-user return cohorts are kept for day 0..30 after install
ACT_LATE_DAYS = 3           # activity days ≤ E−3 are final: the maturing cohorts re-read every fetch reach back that far
VUSE_MIN_SHARE = 0.01       # a version under 1% of the day's active users is pooled into "_rest" (~55 versions a day live)
COH_BATCH = 14              # cohorts per cohort request (the size ga4.cohort_body / probe_t3 ran live)
COH_MIN_USERS = 200         # a cohort with fewer installs is judged pooled with the batch's other small ones
COH_MIN_COVERAGE = 0.90     # a cohort holding < 90% of its installs (× the app's cohort scale ret_k) reads short
COH_EDGE_RUN = 2            # 2 short batches in a row = GA4's user-data edge: the backfill stops there
COH_MAX_CALLS = 60          # cohort requests per fetch at most (3 for the maturing ones + repair + backfill): the
                            # backfill walks ~840 install days a fetch — a counts-only probe (ga4-d1d7-probe, 27 Sep
                            # 2026) found return data whole back to ~900 days on every app, at ~5 tokens a call
COH_REPAIR_DAYS = 7         # a held short (or not yet mature) cohort is asked again at most once a week
IMPACT_REPORTS = ("usage", "vuse")
NVR_SLOT = {"new": "n", "returning": "r"}


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


USE_METS = ("activeUsers", "sessions", "userEngagementDuration")


class _Unsplit(list):
    """rep_vuse's rows asked WITHOUT newVsReturning (the property rejected the pair): _merge_vuse puts them in the
    returning slots and records vuse_split False."""


def rep_usage(ga, start, end):
    """Per day, new vs returning users: active users, sessions, engagement seconds — SUMS (ratios like
    sessionsPerUser / averageSessionDuration are not additive: the engine divides the sums). ~3 rows a day."""
    return ga.report_all({"dateRanges": [_rng(start, end)], "dimensions": ga4._dim("date", "newVsReturning"),
                          "metrics": ga4._dim(*USE_METS)}, page_rows=UNI_PAGE_ROWS)


def _nvr_rejected(e):
    s = str(e)
    return s.startswith("HTTP 400") and "newVsReturning" in s


def rep_vuse(ga, start, end):
    """rep_usage per app version (the same days: new version vs old). A property that rejects newVsReturning with
    appVersion is asked again without it (_Unsplit: every user in the returning slots, vuse_split False)."""
    body = {"dateRanges": [_rng(start, end)], "metrics": ga4._dim(*USE_METS)}
    try:
        return ga.report_all(dict(body, dimensions=ga4._dim("date", "appVersion", "newVsReturning")),
                             page_rows=UNI_PAGE_ROWS)
    except RuntimeError as e:
        if not _nvr_rejected(e):
            raise
    return _Unsplit(ga.report_all(dict(body, dimensions=ga4._dim("date", "appVersion")), page_rows=UNI_PAGE_ROWS))


def _use_vals(r):
    return [int(r.get("activeUsers") or 0), int(r.get("sessions") or 0),
            int(round(float(r.get("userEngagementDuration") or 0)))]


def _merge_usage(p, rows):
    """→ p["usage"][day] = {"n"|"r"|"o": [active users, sessions, engagement seconds]} — new, returning, anything
    else GA4 answers (e.g. "(not set)"); whole numbers."""
    for r in rows:
        d = ga4._d(r.get("date"))
        if not _in(p, d):
            p["bad_rows"] += 1
            continue
        u = p["usage"].setdefault(d.isoformat(), {"n": [0, 0, 0], "r": [0, 0, 0], "o": [0, 0, 0]})
        slot = u[NVR_SLOT.get(str(r.get("newVsReturning") or ""), "o")]
        for j, v in enumerate(_use_vals(r)):
            slot[j] += v


def _merge_vuse(p, rows):
    """→ p["vuse"][day][version] = [aN, sN, tN, aR, sR, tR] (new users, then returning — anything else GA4 answers
    counts as returning; unsplit rows (_Unsplit) all go there). A version under VUSE_MIN_SHARE of the day's active
    users (daily a1) is pooled into "_rest", "(not set)" / "(other)" into "_x" — sums stay exact (additive)."""
    split = not isinstance(rows, _Unsplit)
    if not split:
        p["vuse_split"] = False
    got = {}
    for r in rows:
        d = ga4._d(r.get("date"))
        if not _in(p, d):
            p["bad_rows"] += 1
            continue
        v = str(r.get("appVersion") or "")
        v = "_x" if v in ("", "(not set)", "(other)", "(none)") else v
        acc = got.setdefault(d.isoformat(), {}).setdefault(v, [0] * 6)
        off = 0 if split and str(r.get("newVsReturning") or "") == "new" else 3
        for j, x in enumerate(_use_vals(r)):
            acc[off + j] += x
    for k, vers in got.items():
        cap = VUSE_MIN_SHARE * int((p["daily"].get(k) or {}).get("a1") or 0)
        out = {}
        for v, acc in vers.items():
            key = v if v == "_x" or acc[0] + acc[3] >= cap else "_rest"
            cur = out.setdefault(key, [0] * 6)
            for j in range(6):
                cur[j] += acc[j]
        p["vuse"][k] = out


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
            "cells_log": [], "cov": {}, "gone": set(), "cell_src": {}, "probes": 0,
            "usage": {}, "vuse": {}, "vuse_split": True, "impact_failed": []}


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
# _parse and merge_window) and every full / incremental fetch then carries it. The IMPACT_REPORTS never fail the
# fetch (see _fetch_window).
REPORTS = [("events", rep_events, _merge_events), ("versions", rep_versions, _merge_versions),
           ("usage", rep_usage, _merge_usage), ("vuse", rep_vuse, _merge_vuse)]


def _spent(ga, q0):
    """tokensPerDay the calls since the quota snapshot `q0` consumed (from `remaining`; the last call's own
    `consumed` without a snapshot) — recorded privately (state), never printed."""
    b0, b1 = (q0 or {}).get("tokensPerDay") or {}, (ga.quota or {}).get("tokensPerDay") or {}
    try:
        if "remaining" in b0 and "remaining" in b1:
            return max(0, int(b0["remaining"]) - int(b1["remaining"]))
        return int(b1.get("consumed") or 0)
    except (TypeError, ValueError):
        return 0


def _tokens(ga, kind, q0):
    t = getattr(ga, "impact_tokens", None)
    if t is None:
        t = ga.impact_tokens = {}
    t[kind] = t.get(kind, 0) + _spent(ga, q0)


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
        q0 = ga.quota
        try:
            rows = fn(ga, start, end)
        except Exception:
            if name not in IMPACT_REPORTS:
                raise
            p["impact_failed"].append(name)       # an impact read never fails the uninstall fetch: the days we hold
            continue                              # stay (keep_best_days), it is asked again at the next fetch
        if name in IMPACT_REPORTS:
            _tokens(ga, name, q0)
        if ga.truncated(rows):
            cut.add(name)
        merge(p, rows)
        del rows
    _fetch_all_cells(ga, p, start, end, place_from, cut, chunk, stop, **(cells or {}))
    return p


# ── update impact: usage days kept at their best, new-user return cohorts ───────────────────────────

def _use_sessions(v, key):
    """Σ sessions of one day's usage ({"n"|"r"|"o": [a, s, t]}) or vuse ({version: [aN, sN, tN, aR, sR, tR]})."""
    if key == "usage":
        return sum(int((v.get(s) or [0, 0, 0])[1] or 0) for s in ("n", "r", "o"))
    return sum(int(x[1] or 0) + int(x[4] or 0) for x in (v or {}).values())


def keep_best_days(held, fetched, key, a, b):
    """Day by day over [a, b] ("usage" / "vuse"): a re-read replaces a day `held` holds only when its Σ sessions ≥ the
    held Σ × (1 − GRADE_TIE) — late data only adds, so a LOWER re-read means GA4 answered degraded; a day missing from
    the re-read keeps the held one too. Held days go back into `fetched` (in place) → how many were kept."""
    h, f = held.get(key) or {}, fetched.setdefault(key, {})
    kept = 0
    for x in _days(_d(a), _d(b)):
        k = x.isoformat()
        if k not in h:
            continue
        if k not in f or _use_sessions(f[k], key) < _use_sessions(h[k], key) * (1 - GRADE_TIE):
            f[k] = h[k]
            kept += 1
    return kept


def _impact_flags(store):
    """store["flags"]["impact"] (in place, defaults filled): vuse_split (GA4 split vuse by new / returning), ret_k (the
    cohort scale), ret_short {day: coverage} (cohorts read short: never used), usage_kept / vuse_kept (held days a lower
    re-read did not replace, last merge), thresholded (a cohort answer was thresholded) — and, when they happen,
    truncated (a cohort answer was cut) and ret_run (the backfill's short batches so far, carried to the next fetch)."""
    fl = store.setdefault("flags", {})
    fi = fl.get("impact")
    if not isinstance(fi, dict):
        fi = fl["impact"] = {}
    for k, v in (("vuse_split", True), ("ret_k", 1.0), ("ret_short", {}), ("usage_kept", 0), ("vuse_kept", 0),
                 ("thresholded", False)):
        fi.setdefault(k, v)
    return fi


def ret_body(days):
    """One DAILY cohort per install day (firstSessionDate), day 0..COHORT_DAYS. A cohort request carries NO top-level
    dateRanges — the dates live in each cohort (ga4.cohort_body)."""
    return {"dimensions": ga4._dim("cohort", "cohortNthDay"),
            "metrics": ga4._dim("cohortActiveUsers", "cohortTotalUsers"),
            "cohortSpec": {"cohorts": [{"name": "c" + d.strftime("%Y%m%d"), "dimension": "firstSessionDate",
                                        "dateRange": {"startDate": d.isoformat(), "endDate": d.isoformat()}}
                                       for d in days],
                           "cohortsRange": {"granularity": "DAILY", "startOffset": 0, "endOffset": COHORT_DAYS}},
            "limit": 10000}


def rep_ret(ga, days):
    """New-user return: of the users whose FIRST session was day c (cohortTotalUsers), how many were active N days
    later (cohortActiveUsers — the same "active user" as the DAU), N = 0..COHORT_DAYS, for the install days `days`
    (≤ COH_BATCH: ≤ 14 × 31 rows, so a request is bounded and GA4 never folds it into "(other)"). Limits, as GA4
    documents them (or doesn't): cohorts are by firstSessionDate only (no version split); the most cohorts one request
    may carry and its token cost are not documented (fetch_ret keeps batches at 14 and records the tokens); it may be
    thresholded (flags.impact.thresholded); user-level data older than the property's retention reads short or empty
    (the self-check in fetch_ret finds that edge). Not a REPORTS entry: a cohort request has no dateRanges."""
    return ga.report(ret_body(days))


def _ret_rows(rows, days, end):
    """Cohort rows → {install day ISO: {"t": total, "a": [active on day 0..M]}} for every day asked, M = min(COHORT_DAYS,
    end − day): a day N GA4 left out (it omits empty rows) is 0 when the cohort has any row; a cohort with none reads
    t 0. Day N past `end` (not settled for this fetch) is dropped."""
    got = {}
    for r in rows:
        name = str(r.get("cohort") or "")
        try:
            c = datetime.strptime(name[1:], "%Y%m%d").date()
            n = int(str(r.get("cohortNthDay")))
        except (TypeError, ValueError):
            continue
        g = got.setdefault(c, {"t": 0, "a": {}})
        g["t"] = max(g["t"], int(r.get("cohortTotalUsers") or 0))
        g["a"][n] = g["a"].get(n, 0) + int(r.get("cohortActiveUsers") or 0)
    out = {}
    for c in days:
        m = min(COHORT_DAYS, (end - c).days)
        if m < 0:
            continue
        g = got.get(c) or {"t": 0, "a": {}}
        out[c.isoformat()] = {"t": g["t"], "a": [g["a"].get(n, 0) for n in range(m + 1)]}
    return out


def _new(daily, k):
    return int((daily.get(k) or {}).get("new") or 0)


def _ret_judge(got, daily, k):
    """Each cohort's self-check against the day's installs (daily new) → in place cov / ok, and (judged, short) counts.
    cov = cohortTotalUsers ÷ newUsers; ok = not judged, or cov ≥ COH_MIN_COVERAGE × k (k = the app's cohort scale, like
    _users_k). A cohort under COH_MIN_USERS installs is judged pooled with the batch's other small ones (their Σ) —
    too few installs alone say nothing."""
    judged = short = 0
    small = []
    for day, e in got.items():
        n = _new(daily, day)
        e["cov"] = round(e["t"] / n, 4) if n else None
        if n >= COH_MIN_USERS:
            e["ok"] = e["cov"] >= COH_MIN_COVERAGE * k
            judged, short = judged + 1, short + (not e["ok"])
        elif n:
            small.append(day)
        else:
            e["ok"] = True
    st, sn = sum(got[d]["t"] for d in small), sum(_new(daily, d) for d in small)
    for day in small:
        got[day]["ok"] = sn < COH_MIN_USERS or st >= COH_MIN_COVERAGE * k * sn
        if sn >= COH_MIN_USERS:
            judged, short = judged + 1, short + (not got[day]["ok"])
    return judged, short


def _ret_scale(got, daily, held):
    """The app's cohort scale: cohortTotalUsers per newUser of the newest ≥7 judged cohorts of this read (their
    median, at most one batch of them) — else the one held (flags.impact.ret_k), else 1."""
    cov = [e["t"] / _new(daily, d) for d, e in sorted(got.items(), reverse=True)
           if _new(daily, d) >= COH_MIN_USERS and e["t"] > 0][:COH_BATCH]
    if len(cov) >= 7:
        cov.sort()
        n = len(cov)
        return round(cov[n // 2] if n % 2 else (cov[n // 2 - 1] + cov[n // 2]) / 2, 4)
    try:
        return float(held) if held else 1.0
    except (TypeError, ValueError):
        return 1.0


def _ret_keep(held, new):
    """The better read of one cohort: a held complete (ok) one is never replaced by a short re-read; otherwise the re-read
    wins when it is ok, reaches more days, or holds ≥ the held total × (1 − GRADE_TIE)."""
    if not held:
        return new
    if held.get("ok") and not new["ok"]:
        return held
    if new["ok"] or len(new["a"]) > len(held.get("a") or []) or new["t"] >= int(held.get("t") or 0) * (1 - GRADE_TIE):
        return new
    return held


def fetch_ret(ga, store, end, stop=None, full=False, at=None):
    """The new-user return cohorts into `store` (in place; store["ret"] {install day: {t, a, cov, ok, at}}), at most
    COH_MAX_CALLS cohort requests of COH_BATCH install days each, in this order:
      (a) the maturing cohorts — [E − COHORT_DAYS − ACT_LATE_DAYS − 1, E] (from ret_from / history_start at the
          earliest), ~3 requests: each one re-read until its day 30 is final;
      (b) repair: held cohorts in [ret_from, E − 35] that read short or stopped short of day 30, not asked in the last
          COH_REPAIR_DAYS, and install days there never read at all, the newest COH_BATCH;
      (c) backfill while GA4's user-data edge is unknown (ret_from None): newest → oldest from the oldest cohort asked so
          far (ret_to, the cursor: the oldest day really asked — a cut fetch leaves the rest to it) down to history_start; COH_EDGE_RUN short batches in a row (≥ half of ≥3 judged
          cohorts short) = the edge: ret_from = the day after the newest short cohort of the first of them (the history's
          start when it never came). A FULL re-pull first probes the batch just older than ret_from: reading complete,
          the edge moved (GA4 keeps user data longer now) and the backfill resumes.
    Every cohort is self-checked (_ret_judge, against daily new × the app's scale _ret_scale); a short one stays stored
    and flagged (flags.impact.ret_short {day: coverage}), never used. Each cohort keeps its better read (_ret_keep).
    Stops quietly at the run budget (`stop`), low quota or the call cap — the cursor resumes next fetch. A 400 naming the
    cohorts halves the batch. → the requests made."""
    daily, hs = store.get("daily") or {}, _d(store["history_start"])
    ret, fi = store.setdefault("ret", {}), _impact_flags(store)
    at = at or end.isoformat()
    calls = [0]
    rf = _d(store["ret_from"]) if store.get("ret_from") else None

    def can():
        return calls[0] < COH_MAX_CALLS and not (stop and stop()) and not _quota_low(ga.quota)

    def ask(days):
        """→ {day ISO: {"t", "a"}} of the install days asked, or None (the budget / quota / cap stopped it)."""
        if not days:
            return {}
        if not can():
            return None
        calls[0] += 1
        q0 = ga.quota
        try:
            rows = rep_ret(ga, days)
        except RuntimeError as e:
            if not (str(e).startswith("HTTP 400") and "cohort" in str(e).lower()):
                raise
            if len(days) == 1:
                return {}                               # GA4 won't take this one cohort: nothing to store
            a = ask(days[:len(days) // 2])
            b = ask(days[len(days) // 2:]) if a is not None else None
            return None if a is None or b is None else dict(a, **b)
        _tokens(ga, "ret", q0)
        if ga.truncated(rows):
            fi["truncated"] = True
        if (ga.last_meta or {}).get("subjectToThresholding"):
            fi["thresholded"] = True
        return _ret_rows(rows, days, end)

    def put(got, k):
        """Judge a batch, keep each cohort's better read → (short batch?, its newest short cohort, cohorts judged)."""
        judged, short = _ret_judge(got, daily, k)
        newest_short = max((d for d, e in got.items() if not e["ok"]), default=None)
        for d, e in got.items():
            e["at"] = at
            ret[d] = _ret_keep(ret.get(d), e)
            ret[d]["at"] = at                           # asked today (a kept older read too: its re-ask is spent)
        return judged >= 3 and short * 2 >= judged, newest_short, judged

    lo = max(hs, rf or hs, end - timedelta(days=COHORT_DAYS + ACT_LATE_DAYS + 1))
    recent = _days(lo, end) if lo <= end else []
    got, oldest = {}, None
    for i in range(len(recent), 0, -COH_BATCH):         # newest first: a stopped fetch still has the newest
        g = ask(recent[max(0, i - COH_BATCH):i])
        if g is None:
            break
        got.update(g)
        oldest = recent[max(0, i - COH_BATCH)]
    k = _ret_scale(got, daily, fi.get("ret_k"))
    fi["ret_k"] = k
    if got:
        put(got, k)
        # the cursor = the oldest day really asked: a fetch cut before the oldest recent batch leaves those days to
        # the backfill (they drop out of the recent window tomorrow — ret_to = lo would skip them for good)
        if not store.get("ret_to") or _d(store["ret_to"]) > oldest:
            store["ret_to"] = oldest.isoformat()
    if rf is not None:                                  # (b) repair
        top = end - timedelta(days=COHORT_DAYS + 5)
        # … held cohorts that read short / stopped short of day 30, and install days never read at all (a hole a
        # cut fetch left before the cursor rule above), newest first
        want = [d for d in sorted(set(ret) | {x.isoformat() for x in _days(rf, top)}, reverse=True)
                if rf <= _d(d) <= top and _new(daily, d)
                and (d not in ret or not ret[d].get("ok") or len(ret[d].get("a") or []) < COHORT_DAYS + 1)
                and (d not in ret or _age_days(ret[d].get("at"), at) >= COH_REPAIR_DAYS)]
        g = ask([_d(d) for d in sorted(want[:COH_BATCH])])
        if g:
            put(g, k)
    if full and rf is not None and rf > hs:             # (c) a full re-pull: did the edge move?
        b0 = max(hs, rf - timedelta(days=COH_BATCH))
        g = ask(_days(b0, rf - timedelta(days=1)))
        if g:
            bad, _, judged = put(g, k)
            if not bad and judged >= 3:
                rf, store["ret_from"], store["ret_to"] = None, None, b0.isoformat()
    run = list(fi.get("ret_run") or [])
    while rf is None:                                   # (c) backfill
        cur = _d(store["ret_to"]) if store.get("ret_to") else lo
        if cur <= hs:
            rf = _d(run[0]) + timedelta(days=1) if run else hs
            break
        b0 = max(hs, cur - timedelta(days=COH_BATCH))
        g = ask(_days(b0, cur - timedelta(days=1)))
        if g is None:
            break
        bad, newest, _ = put(g, k)
        store["ret_to"] = b0.isoformat()
        if bad:
            run.append(newest)
            if len(run) >= COH_EDGE_RUN:
                rf = _d(run[0]) + timedelta(days=1)
        else:
            run = []
    if rf is not None:
        store["ret_from"] = rf.isoformat()
        run = []
    fi["ret_run"] = run
    fi["ret_short"] = {d: e.get("cov") for d, e in sorted(ret.items()) if not e.get("ok")}
    store["ret"] = dict(sorted(ret.items()))
    return calls[0]


def _age_days(a, b):
    """Days from ISO day a to ISO day b (a huge number when a is unknown)."""
    try:
        return (_d(b) - _d(a)).days
    except (TypeError, ValueError):
        return 10 ** 6


def _impact_full(p):
    """Did a fetch's usage AND vuse reads both come back (so its window's impact data is whole)?"""
    return not any(n in (p.get("impact_failed") or []) for n in IMPACT_REPORTS)


# ── full + incremental fetch ────────────────────────────────────────────────────────────────────

def fetch_full(ga, end, max_history_days, old_store=None, stop=None, held=True, at=None, iday=None):
    """The app's whole history: the daily report over the widest window finds where its data starts
    (history_start), then the other reports from there. Cells whose install day is older than that but
    still inside `old_store`'s history are placed into those older cohorts. `stop` = the run budget (see
    _fetch_cells). held: `old_store` is this stream's — its users edge and events slice size are used, and
    its old days held as complete users cells are not asked by events (nothing could beat them, keep_best);
    False (the app moved to another stream): none of that. `at` = the fetch's day, into cell_src (default
    the window end). iday = refresh_all's box for the install-value reads (_iday_step; None: none). Raises on any
    failure (the caller keeps the old store)."""
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
    fi_old = ((mem or {}).get("flags") or {}).get("impact") or {}
    out = {"v": STORE_V, "den": p["den"], "history_start": hs.isoformat(), "window_end": end.isoformat(),
           "history_capped": hs <= start0, "covered": [[hs.isoformat(), end.isoformat()]],
           "daily": p["daily"], "cohorts": p["cohorts"], "unplaced": p["unplaced"], "versions": p["versions"],
           "cell_src": p["cell_src"], "users_ok_days": p["edge"], "events_chunk_days": p["echunk"],
           "cells_chunk_days": next_chunk(p["cells_log"], chunk, p["daily"], p["alone"]),
           "last_window": [hs.isoformat(), end.isoformat()],
           "usage": p["usage"], "vuse": p["vuse"],
           # the return cohorts this stream's store holds carry over (each keeps its best read); another stream's don't
           "ret": {d: dict(e) for d, e in ((mem or {}).get("ret") or {}).items()},
           "ret_from": (mem or {}).get("ret_from"), "ret_to": (mem or {}).get("ret_to"),
           "flags": {"truncated": sorted(cut), "thresholded": bool(ga.thresholded), "kept_old_before": None,
                     "bad_rows": p["bad_rows"], "incomplete_days": dict(sorted(p["incomplete"].items())),
                     "users_k": p.get("k"),
                     "impact": {"vuse_split": bool(p["vuse_split"]), "ret_k": fi_old.get("ret_k") or 1.0,
                                "ret_short": {}, "usage_kept": 0, "vuse_kept": 0, "thresholded": False,
                                "ret_run": list(fi_old.get("ret_run") or [])}}}
    if _impact_full(p):
        out["impact_v"] = IMPACT_V                      # usage + vuse over the whole history: the impact data is whole
    try:
        fetch_ret(ga, out, end, stop, full=True, at=at or end.isoformat())
    except Exception:
        pass                                            # never fails the uninstall fetch: the cursor resumes next time
    _iday_step(ga, out, iday, end, stop, at or end.isoformat())     # never fails it either (reads `out` only)
    return out


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
    # usage / vuse: the better of the held day and the re-read (keep_best_days — late data only adds)
    fi = _impact_flags(store) if any(key in fetched for key in IMPACT_REPORTS) else None
    for key in IMPACT_REPORTS:
        if key not in fetched:
            continue
        kept = keep_best_days(store, fetched, key, start, end) if held else 0
        fi[key + "_kept"] = kept
        tgt = store.setdefault(key, {})
        for d in _days(start, end):
            k = d.isoformat()
            if k in fetched[key]:
                tgt[k] = fetched[key][k]
            else:
                tgt.pop(k, None)
        store[key] = dict(sorted(tgt.items()))
    if fi is not None:
        split = fetched["vuse_split"] if "vuse_split" in fetched else \
            ((fetched.get("flags") or {}).get("impact") or {}).get("vuse_split")
        if split is not None and "vuse" not in (fetched.get("impact_failed") or []):
            fi["vuse_split"] = bool(split)
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


def fetch_incr(ga, store, end, refetch_days, stop=None, at=None, iday=None):
    """The recent window (see incr_start) re-pulled and merged into `store` (in place, returned). Its users
    edge stays as it is (only a full re-pull moves it); days of the window past it go by events. iday: see
    fetch_full."""
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
    impact_backfill(ga, store, start, p)
    try:
        fetch_ret(ga, store, end, stop, at=at or end.isoformat())
    except Exception:
        pass                                    # never fails the uninstall fetch: the cursor resumes next time
    _iday_step(ga, store, iday, end, stop, at or end.isoformat())   # never fails it either (reads `store` only)
    return store


def impact_backfill(ga, store, start, p):
    """A store from before the update-impact reports (impact_v < IMPACT_V): usage and vuse of its history before the
    incremental window (`start`; the window itself came with `p`) — 1–2 calls, paged — each day kept at its best
    (keep_best_days). impact_v is set only once both reads came back whole; on any failure it stays unset (asked again
    at the next fetch) and the uninstall data is saved as ever. No STORE_V bump: the alert history stays."""
    if int(store.get("impact_v") or 0) >= IMPACT_V:
        return
    try:
        if not _impact_full(p):
            return
        hs = _d(store["history_start"])
        if hs < start:
            q = {"daily": store.get("daily") or {}, "usage": {}, "vuse": {}, "vuse_split": True, "bad_rows": 0,
                 "impact_failed": []}
            for name, fn, merge in REPORTS:
                if name in IMPACT_REPORTS:
                    q0 = ga.quota
                    merge(q, fn(ga, hs, start - timedelta(days=1)))
                    _tokens(ga, name, q0)
            fi = _impact_flags(store)
            for key in IMPACT_REPORTS:
                fi[key + "_kept"] = keep_best_days(store, q, key, hs, start - timedelta(days=1))
                store[key] = dict(sorted(dict(store.get(key) or {}, **q[key]).items()))
            if not q["vuse_split"]:
                fi["vuse_split"] = False
        store["impact_v"] = IMPACT_V
    except Exception:
        pass


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
            fi = _impact_flags(new)
            for key in IMPACT_REPORTS:                   # usage / vuse days: the better read (keep_best_days)
                fi[key + "_kept"] = keep_best_days(old, new, key, nhs, new["window_end"])
                new[key] = dict(sorted((new.get(key) or {}).items()))
        return new, True
    unchecked = _store_v(old) < CHECKED_V
    merged = merge_window(old, new, nhs, _d(new["window_end"]), held=check_ratio)
    kept = {k: ((merged.get("flags") or {}).get("impact") or {}).get(k + "_kept", 0) for k in IMPACT_REPORTS}
    inc = dict((merged.get("flags") or {}).get("incomplete_days") or {})
    if unchecked:
        inc.update(stored_coverage(merged, ohs, nhs - timedelta(days=1)))
    merged.update(history_start=ohs.isoformat(), history_capped=new.get("history_capped", False),
                  den=new.get("den") or "a28", users_ok_days=new.get("users_ok_days"),
                  events_chunk_days=new.get("events_chunk_days"))
    merged["flags"] = dict(new.get("flags") or {}, kept_old_before=nhs.isoformat(),
                           incomplete_days=dict(sorted(inc.items())))
    for k in ("ret", "ret_from", "ret_to"):             # the return cohorts: fetch_full already kept the best of each
        merged[k] = new.get(k)
    merged.pop("impact_v", None)
    if new.get("impact_v"):
        merged["impact_v"] = new["impact_v"]
    fi = _impact_flags(merged)
    fi.update({k + "_kept": v for k, v in kept.items()})
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
            "time_zone": store.get("time_zone"), "impact_v": int(store.get("impact_v") or 0),
            "ret_done": bool(store.get("ret_from"))}


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
    {day: [app_remove users, new users, active users]} for the days that fetch read — its last_window, or the whole history
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
            vals[d.isoformat()] = [int(r.get("un") or 0), int(r.get("new") or 0), int(r.get("a1") or 0)]
    return P, vals


def record_revisions(store, base, today, window, max_age=REVISION_MAX_AGE):
    """The recent days THIS fetch re-read (`window` = [start, end]) vs `base` (revision_base of the store
    before it) → store["revisions"][today] = {"un"|"new"|"a1": {age: [before, after]}} (a1 = daily active users:
    how late the activity the update-impact card reads comes in), age = the day's age in days
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
    rec = {"un": {}, "new": {}, "a1": {}}
    for k, v in vals.items():
        d = _d(k)
        age = (P - d).days
        r = daily.get(k)
        if r is None or not a <= d <= b or not 0 <= age <= min(max_age, REVISION_MAX_AGE):
            continue
        for name, j in (("un", 0), ("new", 1), ("a1", 2)):
            if j < len(v):
                s = rec[name].setdefault(str(age), [0, 0])
                s[0] += int(v[j])
                s[1] += int(r.get(name) or 0)
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
        return iday_due(app_st, cfg, now)               # at most once per ~20h (the install-value backfill: its own)
    if store.get("next_rebuild") and end >= _d(store["next_rebuild"]):
        return "full"
    if end > _d(store["window_end"]) or holes(store):
        return "full" if (end - incr_start(store, end, cfg["refetch_days"])).days + 1 > FULL_IF_GAP_DAYS else "incr"
    if backfill_due(store):
        return "incr"                                   # its usage / vuse or return-cohort history is still coming in:
    return iday_due(app_st, cfg, now)                   # read on as soon as min_hours allows, not on the next GA4 day


def backfill_due(store, app_st=None):
    """A store (or its meta) whose update-impact data (usage / vuse, impact_v) or return-cohort history (ret_from: the
    edge found or history_start reached) isn't whole yet. A meta from before these keys never says so. (`app_st` is
    not read: the install-value backfill has its own fetch kind — iday_due — that never moves last_ok.)"""
    if "impact_v" in store and int(store.get("impact_v") or 0) < IMPACT_V:
        return True
    return store.get("ret_done") is False


def iday_due(app_st, cfg, now):
    """"iday" (GA4_IDAY on): an install-value-only fetch — the stored store only READ, never fetched or saved, last_ok
    never moved — for an app whose install-value history is still coming in (state.fetch[aid].iday.done False), at
    most every IDAY_EVERY_HOURS. It runs after every app that is due for real in the run, on the time left, so a new
    GA4 day is never held back by it: the uninstall / Active fetch of the next settled day keeps its own min_hours
    clock. An app whose install-value history never started (no state.fetch[aid].iday yet — GA4_IDAY just switched
    on) is due too, so the backfill starts at once instead of waiting for the app's next real fetch. None otherwise."""
    ida = app_st.get("iday")
    if not cfg.get("iday") or (ida is not None and ida.get("done") is not False):
        return None
    if _hours_since(app_st.get("last_iday"), now) < IDAY_EVERY_HOURS:
        return None
    return "iday"


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


# ── install value: GA4 per activity day, folded (the "iday" file; engine.value reads it) ─────────────

IDAY_V = 1                  # the iday file format: a file of another one starts over (a new `iday` input: seeded)
IDAY_DIR = "iday"           # data/ga4_uninstall/iday/<key>.json.gz (+ <key>.old.json.gz: the frozen old parts)
IDAY_MAX_CALLS = 120        # GA4 calls per app-fetch at most (shape probe: tokens p90 ≤ 12 a call → 120)
IDAY_CTY_DAYS = 400         # countries (Q-C) are read only for activity days D ≥ F − 400
IDAY_LATE = 3               # a day is read once it is final: D ≤ F = E − 3 (≥ 5 days old: whole on 28/28 apps)
IDAY_TRIES = 3              # a read that comes back short is asked at most 3 times in all, then kept (≈ / unassigned)
IDAY_HOUR_FLOOR = 0.5       # the BACKFILL stops for a property once an hourly token bucket is under 50%: the build's
                            # other reports always keep half
IDAY_RETRY_DAYS = 5         # step 2: at most 5 days asked again per fetch, each at most once a day
IDAY_CHECK_DAYS = 28        # step 3, the late check: in a file's first 28 days …
IDAY_CHECK_AGE = 7          # … day F − 7 (~12 days old, read fresh at ~5) is read again, only measured (chk)
IDAY_EDGE_RUN = 7           # 7 days in a row whose Q-B has no install-day-D row while the day had installs = the edge
IDAY_TOT_DAYS = 120         # a Q-T block holds at most 120 days
IDAY_TOT_RESERVE = 2        # calls the day reads leave for the Q-T blocks (new days + backfill: 2 blocks)
IDAY_ERR_STOP = 2           # 2 failed calls in a row stop the app's iday reads for this fetch
IDAY_EVERY_HOURS = 2        # an install-value-only fetch (plan "iday": backfill not done) at most every 2 h per app
IDAY_DUE_SHARE = 0.5        # the backfill inside a DUE app's fetch stops at half the run budget …
IDAY_RESERVE_SEC = 30       # … and early enough to leave 30 s for every due app still to come (none is deferred)
GAP_MAX = 0.02              # Q-C tie: Σ countries' ad revenue within 2% of Q-B's (fresh revenue moved ≤ ~1.3% between
TIE_NEW = 0.01              # reads minutes apart) and their install-day new users within 1% …
TIE_ABS_MICROS = 1000       # … or within $0.001 / 1 user (a tiny day: that much either way says nothing)
TIE_ABS_USERS = 1
QB_WIN = 427                # Q-B sees install ages 0..427 only — older users are missing even from its TOTAL
QB_NCOV = 0.99              # Q-B self-check: lag-0 new users ≥ 99% of the day's newUsers …
QB_COV = (0.97, 1.05)       # … Σ active users 97–105% of the day's (only while every user is inside the window)
QB_WIN_DROP = (420, 300)    # a read whose largest lag fell under 300 after one at ≥ 420: GA4 keeps less (qb_win)
CTY_LIST = 91               # Q-C install days: D − 90 .. D
CSET_N, CSET_MAX = 25, 35   # country slots: the top 25 by installs (+ "--" unknown, "ZZ" every other), ≤ 35 in all
CSET_ADD, CSET_WIN = 0.02, 28   # a country holding ≥ 2% of installs over the last 28 folded days gets a slot
ZZN_TOP = 10                # (per folded day, the 10 biggest countries without a slot are remembered for that)
IAP_MIN = 0.01              # flags.iap: in-app purchases ≥ 1% of ad revenue (Q-T)
HOT_X_DAYS, HOT_C_DAYS = 400, 100   # .old: x / days older than to − 400, country weeks ending before to − 100 (whole months)
ULAGS = (0, 1, 3, 7, 14, 30, 45, 60, 90, 120, 180, 270, 365)            # x[X].u: active users at these lags
RBANDS = ((0, 0), (1, 1), (2, 3), (4, 7), (8, 14), (15, 30), (31, 60), (61, 90), (91, 180), (181, 365))
CLAGS = (1, 3, 7, 14, 30, 60, 90)                                          # c[W][slot].u: users at these lags
CBANDS = RBANDS[:8]                                                        # c[W][slot].r, gap.r: revenue ≤ 90 days
ABANDS = ((0, 0), (1, 6), (7, 29), (30, 89), (90, 364), (365, 427))        # days[D].ab / rb: by install age
IDAY_METS = ("activeUsers", "newUsers", "totalAdRevenue", "totalRevenue")
QB_FOLDED = ("ok", "q", "empty")        # days[D].st that were folded into x (each exactly once)
QC_FOLDED = ("ok", "smp", "gap")        # days[D].cst that were folded into c


def _bands_ix(bands, top):
    ix = [None] * (top + 1)
    for i, (lo, hi) in enumerate(bands):
        for lag in range(lo, hi + 1):
            ix[lag] = i
    return ix


RB_IX, AB_IX = _bands_ix(RBANDS, 365), _bands_ix(ABANDS, QB_WIN)
UL_IX, CL_IX = {lag: i for i, lag in enumerate(ULAGS)}, {lag: i for i, lag in enumerate(CLAGS)}


def _mic(v):
    """USD → micros (int)."""
    try:
        return int(round(float(v or 0) * 1e6))
    except (TypeError, ValueError):
        return 0


def _int(v):
    try:
        return int(round(float(v or 0)))
    except (TypeError, ValueError):
        return 0


def iday_week(x):
    """An install day (date or ISO) → the ISO Monday of its week (Monday–Sunday, the GA4 timezone's days)."""
    x = _d(x)
    return (x - timedelta(days=x.weekday())).isoformat()


def iday_band(lag):
    """A lag in days (0..365) → its RBANDS index (None past 365)."""
    return RB_IX[lag] if 0 <= lag <= 365 else None


@functools.lru_cache(maxsize=4096)
def _x_date(f):
    """GA4 YYYYMMDD → date (None when not a date), cached: the same ~430 install days recur on every read."""
    return ga4._d(f)


def _slot_cc(v):
    """GA4 countryId → the ISO-2 code, "--" when unknown ("(not set)", empty, anything not a 2-letter code)."""
    s = str(v or "").strip()
    return s if len(s) == 2 and s.isalpha() and s.isupper() else "--"


def _date_ranges(keys):
    """Sorted ISO days → [[first, last]] runs of consecutive days."""
    out = []
    for k in keys:
        if out and (_d(k) - _d(out[-1][1])).days == 1:
            out[-1][1] = k
        else:
            out.append([k, k])
    return out


# the three reads (Ga4App adds the Android + stream filter, returnPropertyQuota, a total order and paging)

def _iday_body(a, b, dims, no_total=False, total_row=True):
    body = {"dateRanges": [_rng(a, b)], "dimensions": ga4._dim(*dims),
            "metrics": ga4._dim(*(IDAY_METS[:3] if no_total else IDAY_METS)), "currencyCode": "USD",
            "keepEmptyRows": False}
    if total_row:
        body["metricAggregations"] = ["TOTAL"]
    return body


def rep_iday_qb(ga, d, no_total=False):
    """Q-B: ONE activity day d, all countries, by install day (firstSessionDate): ≤ 428 rows, 1 token. The truth every
    country read is tied to; install ages 0..427 only (QB_WIN). no_total: without totalRevenue (a property that
    rejects it)."""
    return ga.report_all(_iday_body(d, d, ("firstSessionDate",), no_total), page_rows=UNI_PAGE_ROWS)


def rep_iday_qc(ga, d, no_total=False):
    """Q-C: ONE activity day d by country × install day, install days d−90 .. d only (a 91-value inList — GA4 refuses
    a numeric between on firstSessionDate). ≤ ~14k rows, one page. The list does NOT avoid GA4's "(other)" loss (it
    only hides the row): the loss is measured by tying the read to Q-B (_iday_check_qc)."""
    days = [(d - timedelta(days=i)).strftime("%Y%m%d") for i in range(CTY_LIST)]
    return ga.report_all(_iday_body(d, d, ("countryId", "firstSessionDate"), no_total),
                         extra=[ga4._in_list("firstSessionDate", days)], page_rows=UNI_PAGE_ROWS)


def rep_iday_tot(ga, a, b, no_total=False):
    """Q-T: the day totals of [a, b] by date (every install age): the GA4 side of the AdMob check, the IAP share, and
    the revenue of users older than Q-B's window (rb_old)."""
    return ga.report_all(_iday_body(a, b, ("date",), no_total, total_row=False), page_rows=UNI_PAGE_ROWS)


# parse, self-check, fold

def _qb_parse(rows, d, hs):
    """Q-B rows of day d → its sums (a4, rev4 micros, n = new users installed on d), ab / rb by install-age band (0..427),
    win (the largest lag with users), oth ("(other)" row), t91 (ad revenue of install days d−90..d: the tie's side),
    c91 [lag 0..90] (the same, install days ≥ hs: what the fold puts into x — the gap's side) and the cells to fold
    [(X, lag, active, new, ad, iap)] (X ≥ hs, lag ≤ 365). Rows with a bad date only add to a4 / rev4."""
    q = {"rows": len(rows), "a4": 0, "rev4": 0, "n": 0, "ab": [0] * len(ABANDS), "rb": [0] * len(ABANDS),
         "win": None, "oth": False, "t91": 0, "c91": [0] * CTY_LIST, "cells": []}
    for r in rows:
        f = str(r.get("firstSessionDate") or "")
        act, new, ad = _int(r.get("activeUsers")), _int(r.get("newUsers")), _mic(r.get("totalAdRevenue"))
        iap = _mic(r["totalRevenue"]) - ad if "totalRevenue" in r else None
        q["a4"] += act
        q["rev4"] += ad
        if f == "(other)":
            q["oth"] = True
        x = _x_date(f)
        if x is None or x > d:
            continue
        lag = (d - x).days
        if lag == 0:
            q["n"] += new
        if act and (q["win"] is None or lag > q["win"]):
            q["win"] = lag
        if lag <= QB_WIN:
            q["ab"][AB_IX[lag]] += act
            q["rb"][AB_IX[lag]] += ad
        if lag < CTY_LIST:
            q["t91"] += ad
            if x >= hs:
                q["c91"][lag] += ad
        if x >= hs and lag <= 365:
            q["cells"].append((x.isoformat(), lag, act, new, ad, iap))
    return q


def _meta_flags(meta):
    m = meta or {}
    return bool(m.get("dataLossFromOtherRow")), bool(m.get("samplingMetadatas")), bool(m.get("subjectToThresholding"))


def _iday_check_qb(q, meta, day, d, hs, tries, capped=False):
    """Q-B's self-check against the store's day (daily new / a1) → (st, ledger fields). ncov = lag-0 new users ÷ the
    day's newUsers; cov = Σ active users ÷ the day's, only while d − hs ≤ QB_WIN and the history isn't capped (`capped`:
    users older than history_start exist) — past that, older users are legitimately absent: null. st: ok (folded) · retry (short without a GA4 flag: not folded, asked again; after IDAY_TRIES reads →
    q) · q (folded, ≈: "(other)", loss, sampled, cov > 1.05 or tries used up) · empty (0 rows, 0 active users)."""
    new, a1 = _int((day or {}).get("new")), _int((day or {}).get("a1"))
    ncov = round(q["n"] / new, 4) if new else None
    cov = round(q["a4"] / a1, 4) if a1 and (d - hs).days <= QB_WIN and not capped else None
    loss, smp, thr = _meta_flags(meta)
    if not q["rows"] and not a1:
        st = "empty"
    elif q["oth"] or loss or smp or (cov is not None and cov > QB_COV[1]):
        st = "q"
    elif (ncov is not None and ncov < QB_NCOV) or (cov is not None and cov < QB_COV[0]):
        st = "q" if tries >= IDAY_TRIES else "retry"
    else:
        st = "ok"
    return st, {"a4": q["a4"], "n": q["n"], "rev4": q["rev4"], "ncov": ncov, "cov": cov, "win": q["win"],
                "oth": q["oth"], "loss": loss, "smp": smp, "thr": thr, "rows": q["rows"], "ab": list(q["ab"]),
                "rb": list(q["rb"])}


def _iday_fold_qb(ida, q):
    """Q-B's cells into x[X] (in place): u[ULAGS] active users, r[RBANDS] ad revenue micros (lag ≤ 365), p the same for
    in-app purchases (totalRevenue − totalAdRevenue; only where there are any), n the lag-0 new users."""
    x = ida["x"]
    for k, lag, act, new, ad, iap in q["cells"]:
        e = x.get(k)
        if e is None:
            e = x[k] = {"n": 0, "u": [0] * len(ULAGS), "r": [0] * len(RBANDS)}
        if lag == 0:
            e["n"] += new
        i = UL_IX.get(lag)
        if i is not None:
            e["u"][i] += act
        e["r"][RB_IX[lag]] += ad
        if iap:
            p = e.get("p") or [0] * len(RBANDS)
            p[RB_IX[lag]] += iap
            e["p"] = p


def _qc_parse(rows, d, hs):
    """Q-C rows of day d → rev / n0 (Σ named countries' ad revenue over install days d−90..d, their lag-0 new users:
    the tie's side), nr [lag 0..90] / nn0 (the same, install days ≥ hs: the gap's side), agg {(country, install
    week): {n, u[CLAGS], r[CBANDS]}} (install days ≥ hs) and inst {country: lag-0 new users}. "(other)" rows (either
    dimension) are never folded (their users are not additive): coth; a row with a bad install day neither."""
    lo = d - timedelta(days=CTY_LIST - 1)
    c = {"rows": len(rows), "coth": False, "rev": 0, "n0": 0, "nr": [0] * CTY_LIST, "nn0": 0, "agg": {}, "inst": {}}
    xs, slots = {}, {}                                  # ~14k rows, 91 install days, ~200 countries: parsed once each
    for r in rows:
        cc, f = str(r.get("countryId") or ""), str(r.get("firstSessionDate") or "")
        if cc == "(other)" or f == "(other)":
            c["coth"] = True
            continue
        xl = xs.get(f)
        if xl is None:
            x = _x_date(f)
            xl = xs[f] = (None, None, None) if x is None or not lo <= x <= d else (x, (d - x).days, iday_week(x))
        x, lag, week = xl
        if x is None:
            continue
        act, new, ad = _int(r.get("activeUsers")), _int(r.get("newUsers")), _mic(r.get("totalAdRevenue"))
        slot = slots.get(cc)
        if slot is None:
            slot = slots[cc] = _slot_cc(cc)
        c["rev"] += ad
        if lag == 0:
            c["n0"] += new
            c["inst"][slot] = c["inst"].get(slot, 0) + new
        if x < hs:
            continue
        c["nr"][lag] += ad
        if lag == 0:
            c["nn0"] += new
        key = (slot, week)
        a = c["agg"].get(key)
        if a is None:
            a = c["agg"][key] = {"n": 0, "u": [0] * len(CLAGS), "r": [0] * len(CBANDS)}
        if lag == 0:
            a["n"] += new
        i = CL_IX.get(lag)
        if i is not None:
            a["u"][i] += act
        a["r"][RB_IX[lag]] += ad
    return c


def _tie_inside(got, want, rel, floor):
    return abs(got - want) <= max(rel * abs(want), floor)


def _iday_check_qc(c, meta, t91, n0, ctries):
    """Q-C's self-check, tied to the same day's Q-B (t91 = its ad revenue over the 91 install days, n0 = its lag-0 new
    users) → (cst, ledger fields). The primary trigger is dataLossFromOtherRow (closs): GA4 sets it on a filtered read
    that shows NO "(other)" row. tie_rev / tie_new = Σ countries ÷ Q-B (active users are never tied: travellers + HLL
    run 0–4% high). cst: ok · smp (sampled, tie inside: folded as it is) · gap (closs / "(other)" / sampled with the
    tie outside / tries used up: the named rows folded, the shortfall kept as unassigned) · retry (tie outside without
    a flag: not folded, asked again with a fresh Q-B)."""
    closs, csmp, thr = _meta_flags(meta)
    frac = None
    for s in (meta or {}).get("samplingMetadatas") or []:
        try:
            v = int(s.get("samplesReadCount")) / int(s.get("samplingSpaceSize"))
        except (TypeError, ValueError, ZeroDivisionError, AttributeError):
            continue
        frac = round(v if frac is None else min(frac, v), 4)
    inside = (_tie_inside(c["rev"], t91, GAP_MAX, TIE_ABS_MICROS)
              and _tie_inside(c["n0"], n0, TIE_NEW, TIE_ABS_USERS))
    if closs or c["coth"]:
        cst = "gap"
    elif csmp:
        cst = "smp" if inside else "gap"
    elif inside:
        cst = "ok"
    else:
        cst = "gap" if ctries >= IDAY_TRIES else "retry"
    return cst, {"closs": closs, "coth": c["coth"], "csmp": csmp, "cthr": thr, "smp_frac": frac,
                 "tie_rev": round(c["rev"] / t91, 4) if t91 else None,
                 "tie_new": round(c["n0"] / n0, 4) if n0 else None}


def _zero(e):
    return not e.get("n") and not any(e.get("u") or []) and not any(e.get("r") or [])


def _iday_fold_gap(ida, c, qbc, d, hs):
    """The signed shortfall of a folded Q-C read into c[W]["gap"] {n, r[CBANDS]} (in place): per install day X ≥ hs of
    d−90..d, what the day's Q-B put into x[X] (qbc) minus Σ named countries — so Σ slots + gap = Σ x exactly, week by
    week and band by band. Never spread over the countries."""
    touched = set()
    for lag in range(CTY_LIST):
        x = d - timedelta(days=lag)
        if x < hs:
            break
        gr = int(qbc["r"][lag]) - c["nr"][lag]
        gn = int(qbc["n"]) - c["nn0"] if lag == 0 else 0
        if not gr and not gn:
            continue
        w = iday_week(x)
        g = ida["c"].setdefault(w, {}).setdefault("gap", {"n": 0, "r": [0] * len(CBANDS)})
        g["n"] += gn
        g["r"][RB_IX[lag]] += gr
        touched.add(w)
    for w in touched:
        if _zero(ida["c"][w]["gap"]):
            del ida["c"][w]["gap"]
        if not ida["c"][w]:
            del ida["c"][w]


def _iday_cset(ida, day_inst, before, days):
    """Country slots (in place). The first fetch with country data: the top CSET_N countries by lag-0 installs of its
    own reads, + "--" and "ZZ". Then per folded day the ZZN_TOP biggest countries without a slot are remembered (the
    newest CSET_WIN folded days); one holding ≥ CSET_ADD of those days' installs is appended (≤ CSET_MAX slots), with
    cset_since = the days folded before (ranges): a cell needing one of them is partial. Slots never move."""
    cset = ida["cset"]
    if not cset:
        if not day_inst:
            return
        tot = {}
        for inst in day_inst.values():
            for cc, n in inst.items():
                tot[cc] = tot.get(cc, 0) + n
        top = sorted((cc for cc, n in tot.items() if cc not in ("--", "ZZ") and n > 0), key=lambda cc: (-tot[cc], cc))
        cset.extend(top[:CSET_N] + ["--", "ZZ"])
    zzn = ida["zzn"]
    for k, inst in day_inst.items():
        zzn[k] = dict(sorted(((cc, n) for cc, n in inst.items() if cc not in cset and cc != "--" and n > 0),
                             key=lambda cn: (-cn[1], cn[0]))[:ZZN_TOP])
    for k in sorted(zzn)[:-CSET_WIN]:
        del zzn[k]
    want = sum(_int((days.get(k) or {}).get("n")) for k in zzn)
    got = {}
    for inst in zzn.values():
        for cc, n in inst.items():
            got[cc] = got.get(cc, 0) + n
    for cc in sorted((cc for cc, n in got.items() if want and n >= CSET_ADD * want), key=lambda cc: (-got[cc], cc)):
        if len(cset) >= CSET_MAX:
            break
        cset.append(cc)
        if before:
            ida["cset_since"][cc] = _date_ranges(before)
        for inst in zzn.values():
            inst.pop(cc, None)


def _iday_fold_pend(ida, pend):
    """This fetch's country cells {(country, week): {n, u, r}} into c[W][slot index] (in place; all-zero slots
    left out)."""
    if not pend:
        return
    ix = {cc: i for i, cc in enumerate(ida["cset"])}
    unk, zz = ix.get("--"), ix.get("ZZ")
    touched = set()
    for (cc, w), a in sorted(pend.items()):
        s = ix.get(cc, unk if cc == "--" else zz)
        if s is None:
            continue
        e = ida["c"].setdefault(w, {}).setdefault(str(s), {"n": 0, "u": [0] * len(CLAGS), "r": [0] * len(CBANDS)})
        e["n"] += a["n"]
        e["u"] = [p + v for p, v in zip(e["u"], a["u"])]
        e["r"] = [p + v for p, v in zip(e["r"], a["r"])]
        touched.add((w, str(s)))
    for w, s in touched:
        if _zero(ida["c"][w][s]):
            del ida["c"][w][s]
        if not ida["c"][w]:
            del ida["c"][w]


def _iday_new(src, at):
    return {"v": IDAY_V, "src": list(src), "tz": None, "cur": "USD", "born": at, "from": None, "to": None,
            "cfrom": None, "edge": None, "done": False,
            "flags": {"no_total": False, "iap": False, "smp": False, "qb_win": False},
            "cset": [], "cset_since": {}, "zzn": {}, "erun": [], "wlast": None, "days": {}, "x": {}, "c": {}}


def _hour_low(q, floor=IDAY_HOUR_FLOOR):
    """An hourly token bucket of the property under `floor` of its size (the backfill's own stop)."""
    for k in ("tokensPerHour", "tokensPerProjectPerHour"):
        b = (q or {}).get(k) or {}
        if "remaining" in b:
            total = max(QUOTA_CAP[k], (b.get("consumed") or 0) + (b.get("remaining") or 0))
            if (b.get("remaining") or 0) < floor * total:
                return True
    return False


def _rb_old(rec):
    """days[D].rb_old: Q-T's ad revenue − Q-B's (users installed > 427 days ago), once both are known (null before)."""
    if rec.get("rev") is not None and rec.get("rev4") is not None and rec.get("st") in QB_FOLDED:
        rec["rb_old"] = rec["rev"] - rec["rev4"]


class _Iday:
    """One app-fetch's iday reads (fetch_iday): the call cap, the stops, this fetch's country cells until the slots
    are known, and the counts."""

    def __init__(self, ga, store, ida, end, stop, at, plain, max_calls, cty_days):
        self.ga, self.ida, self.days, self.at = ga, ida, ida["days"], at
        self.stop, self.plain, self.max_calls = stop, plain, max_calls
        self.hs, self.daily = _d(store["history_start"]), store.get("daily") or {}
        self.capped = bool(store.get("history_capped"))
        self.F = end - timedelta(days=IDAY_LATE)
        self.cty_lo = self.F - timedelta(days=cty_days)
        self.calls = self.errs = 0
        self.halt = False
        self.pend, self.day_inst = {}, {}
        self.stats = {"days": 0, "cdays": 0, "folded": 0, "flagged": 0, "csmp": 0, "cgap": 0, "retry": 0, "calls": 0,
                      "tok": 0, "qstop": False, "why": None}

    # budget

    def can(self, need=1, back=False, reserve=True):
        """May the next `need` calls go? The call cap (IDAY_TOT_RESERVE kept for Q-T), stop() (the build's 2× budget), a
        low quota; the backfill (back) also the plain run budget and the hourly floor."""
        why = None
        if self.halt:
            return False
        if self.calls + need + (IDAY_TOT_RESERVE if reserve else 0) > self.max_calls:
            why = "cap"
        elif self.stop and self.stop():
            why = "budget"
        elif _quota_low(self.ga.quota):
            why = "quota"
        elif back and self.plain and self.plain():
            why = "budget"
        elif back and _hour_low(self.ga.quota):
            why = "hour"
        if why:
            self.stats["why"] = self.stats["why"] or why
            self.stats["qstop"] |= why in ("quota", "hour")
            return False
        return True

    def ask(self, fn, *args):
        """One read → (rows, metadata, tokens), or None: it failed (the day is `err`; IDAY_ERR_STOP in a row stop the
        fetch's reads; a quota answer stops them at once). A 400 is asked ONCE more without totalRevenue (flags.no_total,
        kept). A response in another currency than USD counts as failed."""
        fl = self.ida["flags"]
        nt = bool(fl.get("no_total"))
        while True:
            q0, c0 = self.ga.quota, getattr(self.ga, "calls", None)
            try:
                rows = fn(self.ga, *args, no_total=nt)
                meta = dict(self.ga.last_meta or {})
                if meta.get("currencyCode") not in (None, "", "USD"):
                    raise ValueError("currency")
            except Exception as e:
                self._count(q0, c0)
                if _fail_kind(e) == "quota":
                    self.halt, self.stats["qstop"] = True, True
                    self.stats["why"] = self.stats["why"] or "quota"
                    return None
                if not nt and str(e).startswith("HTTP 400"):
                    nt = True
                    continue
                self.errs += 1
                if self.errs >= IDAY_ERR_STOP:
                    self.halt = True
                    self.stats["why"] = self.stats["why"] or "errors"
                return None
            tok = self._count(q0, c0)
            self.errs = 0
            if nt:
                fl["no_total"] = True
            return rows, meta, tok

    def _count(self, q0, c0):
        """One read's calls and tokens → the fetch's counts and ga.impact_tokens['iday'] → its tokens."""
        c1 = getattr(self.ga, "calls", None)
        n = c1 - c0 if isinstance(c0, int) and isinstance(c1, int) and c1 > c0 else 1
        tok = _spent(self.ga, q0)
        self.calls += n
        self.stats["calls"] += n
        self.stats["tok"] += tok
        t = getattr(self.ga, "impact_tokens", None)
        if t is None:
            t = self.ga.impact_tokens = {}
        t["iday"] = t.get("iday", 0) + tok
        return tok

    # one day

    def _need(self, d):
        return 2 if d >= self.cty_lo else 1

    def day(self, d):
        """Q-B of day d → the ledger (+ its fold into x, and its Q-C when it folds inside the country horizon).
        → the parse (None: the call failed — the day is `err`, unread)."""
        k = d.isoformat()
        rec = self.days.setdefault(k, {"st": None, "tries": 0})
        res = self.ask(rep_iday_qb, d)
        if res is None:
            rec.update(st="err", at=self.at)
            return None
        rows, meta, tok = res
        self.stats["days"] += 1
        q = _qb_parse(rows, d, self.hs)
        tries = _int(rec.get("tries")) + 1
        st, f = _iday_check_qb(q, meta, self.daily.get(k), d, self.hs, tries, self.capped)
        rec.update(f, st=st, tries=tries, at=self.at, tok=tok)
        self._win(d, q)
        if st == "retry":
            self.stats["retry"] += 1
            return q
        _iday_fold_qb(self.ida, q)
        _rb_old(rec)
        self.stats["folded"] += 1
        self.stats["flagged"] += st == "q"
        if d < self.cty_lo:
            rec["cst"] = "none"
        elif st == "empty":
            rec.update(cst="ok", ctries=0, crows=0, ctok=0, closs=False, coth=False, csmp=False, cthr=False,
                       smp_frac=None, tie_rev=None, tie_new=None)
        else:
            rec["cst"] = None                           # asked next (or at a later fetch: step 2)
            rec["qbc"] = {"n": q["n"], "r": list(q["c91"])}
            if self.can(1):
                self.qc(d, q["t91"], q["n"])
        return q

    def qc(self, d, t91, n0):
        """Q-C of day d, tied to a Q-B read of the same fetch (t91, n0) → the ledger; folded (gap now, the country cells
        once the slots are known) unless `retry` / `err`."""
        k = d.isoformat()
        rec = self.days[k]
        res = self.ask(rep_iday_qc, d)
        if res is None:
            rec.update(cst="err", at=self.at)
            return
        rows, meta, tok = res
        self.stats["cdays"] += 1
        c = _qc_parse(rows, d, self.hs)
        ctries = _int(rec.get("ctries")) + 1
        cst, f = _iday_check_qc(c, meta, t91, n0, ctries)
        rec.update(f, cst=cst, ctries=ctries, crows=c["rows"], ctok=tok, at=self.at)
        if cst == "retry":
            self.stats["retry"] += 1
            return
        qbc = rec.pop("qbc", None)
        if qbc is not None:
            _iday_fold_gap(self.ida, c, qbc, d, self.hs)
        for key, a in c["agg"].items():
            p = self.pend.get(key)
            if p is None:
                self.pend[key] = {"n": a["n"], "u": list(a["u"]), "r": list(a["r"])}
            else:
                p["n"] += a["n"]
                p["u"] = [x + y for x, y in zip(p["u"], a["u"])]
                p["r"] = [x + y for x, y in zip(p["r"], a["r"])]
        self.day_inst[k] = c["inst"]
        self.stats["csmp"] += cst == "smp"
        self.stats["cgap"] += cst == "gap"
        if cst == "smp":
            self.ida["flags"]["smp"] = True

    def _win(self, d, q):
        """flags.qb_win: Q-B's window shrank (largest lag < 300 on a day that should reach ≥ 420, after a read that did)."""
        if (d - self.hs).days < QB_WIN_DROP[0] or not q["rows"]:
            return
        win, last = q["win"] or 0, self.ida.get("wlast")
        if win < QB_WIN_DROP[1] and isinstance(last, int) and last >= QB_WIN_DROP[0]:
            self.ida["flags"]["qb_win"] = True
        self.ida["wlast"] = win

    # the steps

    def prep(self):
        """Days still waiting for their country read that fell out of the country horizon: none now."""
        for k, r in self.days.items():
            if r.get("st") in ("ok", "q") and r.get("cst") in (None, "retry", "err") and _d(k) < self.cty_lo:
                r["cst"] = "none"
                r.pop("qbc", None)

    def new_days(self):
        """Step 1: every unread day after the newest one read, up to F, oldest first (normally one). A new file: F."""
        if not self.days:
            todo = [self.F] if self.F >= self.hs else []
        else:
            to = _d(max(self.days))
            todo = _days(max(to + timedelta(days=1), self.hs), self.F) if to < self.F else []
        for d in todo:
            if not self.can(self._need(d)):
                break
            self.day(d)

    def retries(self):
        """Step 2: ≤ IDAY_RETRY_DAYS days, newest first, each at most once a day: Q-B `retry` / `err` days, and folded
        days whose Q-C is `retry` / `err` / not asked yet (with a fresh Q-B for the tie — never folded again)."""
        er = set(self.ida.get("erun") or [])
        cand = []
        for k, r in self.days.items():
            d = _d(k)
            if r.get("at") == self.at or k in er or not self.hs <= d <= self.F:
                continue
            if r.get("st") in ("retry", "err"):
                cand.append((k, "qb"))
            elif r.get("st") in ("ok", "q") and d >= self.cty_lo and r.get("cst") in (None, "retry", "err"):
                cand.append((k, "qc"))
        for k, kind in sorted(cand, reverse=True)[:IDAY_RETRY_DAYS]:
            d = _d(k)
            if kind == "qb":
                if not self.can(self._need(d)):
                    break
                self.day(d)
                continue
            if not self.can(2):
                break
            res = self.ask(rep_iday_qb, d)             # the tie's side, read now (never folded again)
            self.days[k]["at"] = self.at
            if res is None:
                self.days[k]["cst"] = "err"
                continue
            self.stats["days"] += 1
            q = _qb_parse(res[0], d, self.hs)
            if self.can(1):
                self.qc(d, q["t91"], q["n"])

    def late(self):
        """Step 3 (a file's first IDAY_CHECK_DAYS days): day F − IDAY_CHECK_AGE, read fresh at ~5 days, read again —
        only measured (days[D].chk = {a, n, rev, closs, tie_rev, tie_new, at}), never folded again: how late GA4 is,
        and at what age country loss starts."""
        born = self.ida.get("born")
        if not born or _age_days(born, self.at) >= IDAY_CHECK_DAYS:
            return
        d = self.F - timedelta(days=IDAY_CHECK_AGE)
        k = d.isoformat()
        r = self.days.get(k)
        if not r or r.get("st") not in ("ok", "q") or r.get("chk") is not None:
            return
        if _age_days(k, r.get("at")) > IDAY_CHECK_AGE:
            return                                      # a backfilled day: not read fresh, nothing to compare
        cty = d >= self.cty_lo and r.get("cst") in QC_FOLDED
        if not self.can(2 if cty else 1):
            return
        res = self.ask(rep_iday_qb, d)
        if res is None:
            return
        q = _qb_parse(res[0], d, self.hs)
        chk = {"at": self.at, "a": q["a4"], "n": q["n"], "rev": q["rev4"], "closs": None, "tie_rev": None,
               "tie_new": None}
        if cty:
            res = self.ask(rep_iday_qc, d)
            if res is not None:
                _, f = _iday_check_qc(_qc_parse(res[0], d, self.hs), res[1], q["t91"], q["n"], 1)
                chk.update(closs=f["closs"], tie_rev=f["tie_rev"], tie_new=f["tie_new"])
        r["chk"] = chk

    def backfill(self):
        """Step 4: from the oldest day read − 1 down to history_start, newest first — the only step that obeys the plain
        run budget and the hourly floor. Stops at a failed call (the day is `err`: step 2 asks it again) and at the data
        edge: IDAY_EDGE_RUN days in a row (days without installs don't count) whose Q-B has no install-day-D row while
        the day had installs → edge = the newest of them, their st "edge"."""
        cur = _d(min(self.days)) - timedelta(days=1) if self.days else self.F
        er = list(self.ida.get("erun") or [])
        while cur >= self.hs and self.ida.get("edge") is None:
            if not self.can(self._need(cur), back=True):
                break
            q = self.day(cur)
            if q is None:
                break
            k = cur.isoformat()
            if _int((self.daily.get(k) or {}).get("new")) > 0:
                if q["n"] == 0 and self.days[k].get("st") == "retry":
                    er.append(k)
                else:
                    er = []
            if len(er) >= IDAY_EDGE_RUN:
                self.ida["edge"] = er[0]
                for e in er:
                    self.days[e]["st"] = "edge"
                er = []
                break
            cur -= timedelta(days=1)
        self.ida["erun"] = er

    def totals(self):
        """Step 5: Q-T for every day read without its totals (tt), one call per block of consecutive days
        (≤ IDAY_TOT_DAYS), newest first. A failed block stays null (unknown, never 0) and is asked at the next fetch."""
        blocks = []
        for k in sorted(k for k, r in self.days.items() if not r.get("tt")):
            d = _d(k)
            if blocks and (d - blocks[-1][1]).days == 1 and (d - blocks[-1][0]).days < IDAY_TOT_DAYS:
                blocks[-1][1] = d
            else:
                blocks.append([d, d])
        for a, b in sorted(blocks, reverse=True):
            if not self.can(1, reserve=False):
                break
            res = self.ask(rep_iday_tot, a, b)
            if res is None:
                continue
            nt = bool(self.ida["flags"].get("no_total"))
            by = {}
            for r in res[0]:
                d = ga4._d(r.get("date"))
                if d is not None:
                    by[d.isoformat()] = r
            for d in _days(a, b):
                k = d.isoformat()
                r, rec = by.get(k) or {}, self.days[k]
                rec.update(a=_int(r.get("activeUsers")), nn=_int(r.get("newUsers")), rev=_mic(r.get("totalAdRevenue")),
                           tot=None if nt and "totalRevenue" not in r else _mic(r.get("totalRevenue")), tt=self.at)
                _rb_old(rec)

    def finish(self):
        """The country slots and this fetch's country cells, the cursor (from / to / cfrom / done) and the flags."""
        ida = self.ida
        before = sorted(k for k, r in self.days.items() if r.get("cst") in QC_FOLDED and k not in self.day_inst)
        _iday_cset(ida, self.day_inst, before, self.days)
        _iday_fold_pend(ida, self.pend)
        ida["from"] = min(self.days) if self.days else None
        ida["to"] = max(self.days) if self.days else None
        cf = [k for k, r in self.days.items() if r.get("cst") in QC_FOLDED]
        ida["cfrom"] = min(cf) if cf else None
        ida["done"] = bool(ida.get("edge") is not None or self.F < self.hs
                           or (ida["from"] is not None and _d(ida["from"]) <= self.hs))
        rev = iap = 0
        for r in self.days.values():
            if r.get("rev") is not None and r.get("tot") is not None:
                rev, iap = rev + r["rev"], iap + r["tot"] - r["rev"]
        ida["flags"]["iap"] = bool(rev > 0 and iap >= IAP_MIN * rev)

    def run(self):
        self.prep()
        self.new_days()
        self.retries()
        self.late()
        self.backfill()
        self.totals()
        self.finish()


def _iday_defaults(ida):
    base = _iday_new(ida.get("src") or [], ida.get("born"))
    for k, v in base.items():
        if not isinstance(ida.get(k), type(v)) and v is not None:
            ida[k] = v
        ida.setdefault(k, v)
    for k, v in base["flags"].items():
        ida["flags"].setdefault(k, v)
    return ida


def fetch_iday(ga, store, ida, end, stop=None, at=None, plain=None, max_calls=IDAY_MAX_CALLS, cty_days=IDAY_CTY_DAYS):
    """The app's install-value reads (see the module docstring) → (the new iday data, counts). `ida` = what
    load_iday gave (None: none yet) — NEVER changed in place: a failure anywhere leaves it (and the file) as it was.
    `store` = the app's uninstall store, only read (history_start, daily new / a1 for the self-checks). end = the
    fetch's settled end E; F = E − IDAY_LATE, the newest day read. stop = the build's 2× budget, plain = the plain run
    budget (the backfill only); at most `max_calls` GA4 calls, countries for days ≥ F − `cty_days`. A new file starts
    when ida's stream (src) is not ga's or its format is not IDAY_V. In each fetch:
      1. new days: every unread day after the newest read, up to F, oldest first (Q-B, then its Q-C);
      2. retries: ≤ IDAY_RETRY_DAYS days (Q-B retry / err; Q-C retry / err / not asked, with a fresh Q-B for the tie);
      3. the late check (a file's first 28 days): day F − 7 read again, measured only;
      4. the backfill, newest → oldest (plain budget, hourly floor, the call cap, the data edge);
      5. Q-T for every day read without totals, one call per block.
    Counts (never ids / money): days (Q-B reads), cdays (Q-C reads), folded (flagged: ≈), csmp, cgap (country read
    sampled / unassigned), retry, calls, tok, qstop (a quota stop), why (the first stop)."""
    at = at or end.isoformat()
    src = [str(ga.property_id), str(ga.stream_id)]
    if not isinstance(ida, dict) or ida.get("src") != src or _int(ida.get("v")) != IDAY_V:
        ida = _iday_new(src, at)
    else:
        ida = _iday_defaults(copy.deepcopy(ida))
    run = _Iday(ga, store, ida, end, stop, at, plain, max_calls, cty_days)
    run.run()
    return ida, run.stats


def _iday_step(ga, store, box, end, stop, at):
    """fetch_iday for fetch_full / fetch_incr, never failing them. box (from refresh_all): {"ida", "plain", "max_calls",
    "cty_days"} in; "ok", "ida", "stats" out (ok False: nothing to save — the file stays as it was)."""
    if box is None:
        return
    box["ok"] = False
    try:
        ida, stats = fetch_iday(ga, store, box.get("ida"), end, stop=stop, at=at, plain=box.get("plain"),
                                max_calls=int(box.get("max_calls") or IDAY_MAX_CALLS),
                                cty_days=int(box.get("cty_days") or IDAY_CTY_DAYS))
    except Exception as e:
        box["err"] = type(e).__name__
        return
    box.update(ida=ida, stats=stats, ok=True)


# the file: hot + .old, merged in memory

def iday_path(data_dir, app_id, old=False):
    return os.path.join(data_dir, DIR, IDAY_DIR, file_key(app_id) + (".old" if old else "") + ".json.gz")


def load_iday(data_dir, app_id):
    """The app's iday data — the hot file with its .old part merged in: {v, src, tz, cur, born, from, to, cfrom, edge,
    done, flags, cset, cset_since, zzn, erun, wlast, days, x, c} — or None: none yet, unreadable, or an .old part that
    can't be read or belongs to another stream / format (the backfill then starts over: never half a history)."""
    hot = load_store(iday_path(data_dir, app_id))
    if not isinstance(hot, dict):
        return None
    ida = {k: v for k, v in hot.items() if k != "cut"}
    for k in ("days", "x", "c"):
        ida[k] = dict(hot.get(k) or {})
    op = iday_path(data_dir, app_id, old=True)
    if os.path.exists(op):
        old = load_store(op)
        if not isinstance(old, dict) or old.get("v") != hot.get("v") or old.get("src") != hot.get("src"):
            return None
        for k in ("days", "x", "c"):
            for kk, vv in (old.get(k) or {}).items():
                ida[k].setdefault(kk, vv)
    return ida


def _iday_split(ida):
    """→ (hot, old): .old holds days / x older than the first of the month of to − HOT_X_DAYS, and the country weeks
    that end before the first of the month of to − HOT_C_DAYS — whole months, so it is rewritten about once a month
    (and while the backfill folds into it)."""
    parts = {k: ida.get(k) or {} for k in ("days", "x", "c")}
    hot = {k: v for k, v in ida.items() if k not in parts}
    old = {"v": ida.get("v"), "src": ida.get("src"), "days": {}, "x": {}, "c": {}}
    if not ida.get("to"):
        hot.update(parts, cut=None)
        return hot, old
    to = _d(ida["to"])
    xc = (to - timedelta(days=HOT_X_DAYS)).replace(day=1).isoformat()
    cc = (to - timedelta(days=HOT_C_DAYS)).replace(day=1)
    hot["cut"] = {"x": xc, "c": cc.isoformat()}
    for k in ("days", "x"):
        hot[k] = {d: v for d, v in parts[k].items() if d >= xc}
        old[k] = {d: v for d, v in parts[k].items() if d < xc}
    wc = (cc - timedelta(days=6)).isoformat()          # a week ends before cc ⇔ its Monday is before cc − 6
    hot["c"] = {w: v for w, v in parts["c"].items() if w >= wc}
    old["c"] = {w: v for w, v in parts["c"].items() if w < wc}
    return hot, old


def save_iday(data_dir, app_id, ida):
    """Both files, deterministic (write_json_gz_stable: only when the content changed); no .old part → no .old file.
    → True when anything was written or removed."""
    hot, old = _iday_split(ida)
    op = iday_path(data_dir, app_id, old=True)
    wrote = False
    if old["days"] or old["x"] or old["c"]:
        wrote = write_json_gz_stable(op, old)
    elif os.path.exists(op):
        os.remove(op)
        wrote = True
    return write_json_gz_stable(iday_path(data_dir, app_id), hot) or wrote


def iday_meta(ida, stats=None):
    """state.fetch[aid].iday — what plan() (backfill_due) and the log read."""
    s = stats or {}
    return {"v": ida.get("v"), "from": ida.get("from"), "to": ida.get("to"), "cfrom": ida.get("cfrom"),
            "done": bool(ida.get("done")), "calls": int(s.get("calls") or 0), "tok": int(s.get("tok") or 0)}


IDAY_COUNTS = ("apps", "days", "cdays", "folded", "flagged", "csmp", "cgap", "retry", "whole", "filling", "calls",
               "qstops")


def iday_log_line(status):
    """The public counts-only line (refresh_all's status["iday"], present only when GA4_IDAY is on) — or None."""
    c = (status or {}).get("iday")
    if not isinstance(c, dict):
        return None
    return ("ga4 iday: apps %d, days read %d (with countries %d), folded %d (flagged %d), country sampled %d, "
            "country unassigned %d, retry %d, apps whole %d, filling %d, calls %d, quota stops %d"
            % tuple(int(c.get(k) or 0) for k in IDAY_COUNTS))


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


def _iday_box(data_dir, aid, cfg, plain):
    """refresh_all → fetch_full / fetch_incr: the app's iday file (None: a new one) and its limits (cfg "iday_max_calls",
    "iday_cty_days"; the defaults IDAY_MAX_CALLS / IDAY_CTY_DAYS)."""
    try:
        ida = load_iday(data_dir, aid)
    except Exception:
        ida = None
    return {"ida": ida, "plain": plain, "max_calls": cfg.get("iday_max_calls") or IDAY_MAX_CALLS,
            "cty_days": cfg.get("iday_cty_days") or IDAY_CTY_DAYS}


def _iday_save(data_dir, aid, box, tz, st, ic):
    """After the app's fetch went through: its iday file (written only on change), state.fetch[aid].iday, the counts.
    A failure here costs only the file (the next fetch reads on from the one on disk)."""
    try:
        ida, s = box["ida"], box.get("stats") or {}
        ida["tz"] = tz
        save_iday(data_dir, aid, ida)
        st["iday"] = iday_meta(ida, s)
        ic["apps"] += 1
        for k in ("days", "cdays", "folded", "flagged", "csmp", "cgap", "retry", "calls"):
            ic[k] += int(s.get(k) or 0)
        ic["qstops"] += bool(s.get("qstop"))
    except Exception:
        pass


def _iday_only(cfg, data_dir, a, st, r, tz, end, now, plain, over, access, owner_rt, ic, held_back):
    """plan "iday": the app's install-value reads alone (new days, retries, the backfill — the plain run budget), on
    the store as it is on disk: the store is never fetched or saved, and last_ok / last_try / fail stay as they were
    (this fetch never pushes back the app's next real one, and its failure never marks the app failed). Only
    st["last_iday"], and st["iday"] with the file after a read that went through. Never raises."""
    aid, pid = a["app_id"], r["property_id"]
    st["last_iday"] = _now_iso(now)
    ga = box = old = None
    try:
        owner = r.get("owner")
        if owner not in access:
            try:
                access[owner] = (ga4.access_token(cfg["client_id"], cfg["client_secret"], owner_rt[owner])
                                 if owner in owner_rt else None)
            except Exception:
                access[owner] = None
        tok = access.get(owner)
        if not tok:
            return
        old = load_store(store_path(data_dir, aid))
        if not old or (str(old.get("property_id")), str(old.get("stream_id"))) != (str(pid), str(r["stream_id"])):
            return                                      # no store yet / another stream: its real fetch comes first
        ga = ga4.Ga4App(tok, pid, r["stream_id"])
        box = _iday_box(data_dir, aid, cfg, plain)
        _iday_step(ga, old, box, end, over, _local_day(now, tz).isoformat())
        if box.get("ok"):
            _iday_save(data_dir, aid, box, tz, st, ic)
    except Exception:
        pass
    finally:
        if ga is not None and _quota_low(ga.quota):
            held_back.add(pid)
        old = box = None


def refresh_all(cfg, data_dir, apps, now=None, clock=time.monotonic):
    """Fetch what is due for every selected app (`apps` = [{app_id, app_name, package|None}]) → status
    {"counts", "apps": {app_id: fresh|fetched|failed|deferred}, "no_ga4": {app_id: reason}, "discovery"} (+ "iday":
    the install-value counts, IDAY_COUNTS, when cfg "iday" is on — iday_log_line). Never raises; never prints."""
    now = now or datetime.now(timezone.utc)
    t0 = clock()

    def over():                                         # one app's cells re-asks stop splitting past 2× the budget
        return clock() - t0 >= 2 * cfg["run_budget_sec"]

    def plain():                                        # the install-value backfill stops at the plain budget
        return clock() - t0 >= cfg["run_budget_sec"]

    iday_on = bool(cfg.get("iday"))                     # GA4_IDAY off: nothing of it is read, written or counted
    ic = dict.fromkeys(IDAY_COUNTS, 0)

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
        # deferred lead. The install-value-only fetches ("iday") come after every app due for real, on the time left
        rank = {"incr": 0, "repair": 1}
        todo.sort(key=lambda t: (t[0] == "iday", not t[2].get("deferred"), rank.get(t[0], 2),
                                 t[2].get("last_ok") is not None, t[2].get("last_ok") or "", t[1]["app_id"]))
        due_left = [sum(1 for t in todo if t[0] != "iday")]

        def back_stop(later):
            """The install-value backfill inside a due app's fetch stops at IDAY_DUE_SHARE of the budget, and early
            enough to leave IDAY_RESERVE_SEC for each of the `later` due apps still to come — the backfill never
            defers another app's new GA4 day."""
            cut = min(IDAY_DUE_SHARE * cfg["run_budget_sec"], cfg["run_budget_sec"] - IDAY_RESERVE_SEC * later)
            return lambda: clock() - t0 >= cut

        held_back = set()
        for kind, a, st, r, tz, end in todo:
            aid, pid = a["app_id"], r["property_id"]
            if kind == "iday":                          # the install-value backfill alone: never deferred — the app
                seen = "failed" if st.get("fail") else "fresh"   # keeps its own status (a failed one stays failed)
                if clock() - t0 >= cfg["run_budget_sec"] or pid in held_back:
                    out["apps"][aid] = seen
                    continue
                _iday_only(cfg, data_dir, a, st, r, tz, end, now, plain, over, access, owner_rt, ic, held_back)
                out["apps"][aid] = seen
                continue
            due_left[0] -= 1
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
                box = _iday_box(data_dir, aid, cfg, back_stop(due_left[0])) if iday_on and kind != "repair" else None
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
                    new = fetch_full(ga, end, cfg["max_history_days"], old, stop=over, held=not moved, at=at, iday=box)
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
                    store = fetch_incr(ga, old, end, cfg["refetch_days"], stop=over, at=at, iday=box)
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
                tok = getattr(ga, "impact_tokens", None)
                if tok:                                 # the impact reads' GA4 tokens (private: never printed)
                    st["tokens"] = {k: int(tok.get(k, 0)) for k in ("usage", "vuse", "ret") + (("iday",) * iday_on)}
                if box is not None and box.get("ok"):   # the install-value file: only after a fetch that went through
                    _iday_save(data_dir, aid, box, tz, st, ic)
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
                old = store = new = box = None          # free a big store (and iday data) before the next app
            if _quota_low(ga.quota):
                held_back.add(pid)
    except Exception as e:                              # a bug here must never cost the AdMob build
        out["error"] = type(e).__name__
    if iday_on:
        for a in apps:
            s = (state["fetch"].get(a["app_id"]) or {}).get("iday")
            if isinstance(s, dict):
                ic["whole" if s.get("done") else "filling"] += 1
        out["iday"] = ic
    for v in out["apps"].values():
        counts[v] += 1
    counts["no_ga4"] = len(out["no_ga4"])
    try:
        save_state(data_dir, state)
    except Exception:
        out["error"] = out.get("error") or "state_write"
    return out
