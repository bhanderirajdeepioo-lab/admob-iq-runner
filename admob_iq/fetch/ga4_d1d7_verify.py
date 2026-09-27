"""GA4 D1/D7 DAY-BY-DAY verify, run by .github/workflows/ga4-d1d7-verify.yml: for EVERY install day of every GA4 app
of the build, is the new-user return the Active users tab shows right?

The tab reads the stored return cohorts — data/ga4_uninstall/<key>.json.gz, "ret" {install day X: {"t":
cohortTotalUsers, "a": [cohortActiveUsers on day X+0 .. X+30], "ok", "cov", "at"}} (fetch_ret, the cohortSpec API) —
and shows D1 = a[1] ÷ t, D7 = a[7] ÷ t. The owner's own method (Firebase → "Demographic details: Country" + secondary
dimension "First session date", ONE day at a time; ga4_d1d7_probe.py showed on 28 apps that it and cohortSpec agree
for install days up to 900 days old) is asked here for EVERY activity date D from the app's history_start to
min(window_end, today − 3) (property timezone), one runReport per day:
    {dateRanges: [{D, D}], dimensions: [firstSessionDate], metrics: [activeUsers, newUsers],
     dimensionFilter: platform == Android AND streamId == <the app's stream>, returnPropertyQuota: true,
     limit: PAGE_ROWS (+ offset paging to the last row), orderBys: firstSessionDate}
→ A[D][X] = users whose first session was X, active on D (X ≥ D − 30 kept), N[X] = newUsers on row X of day X.
Then for EVERY install day X in [history_start, window_end − 1] and k = 1..30 with X + k ≤ the last day asked (and
≤ that store's own window end — judged_to):
GA4 truth D_k(X) = A[X+k][X] ÷ N[X] against the store's a[k] ÷ t. Rules (both reported):
    users  |a_k − A| ≤ max(2, 2% of A)        rate  |a_k/t − A/N| ≤ 0.5 percentage points
    size   |t − N| ≤ 2% of N (cohort size vs newUsers; reported, not part of the verdict)
Each (X, k) gets ONE class, in this order: not_due (X + k after the last day asked) → unread (a GA4 day it needs was
not read: an error, or the run stopped) → no_ga4_row (N = 0: GA4 has no installs that day) → missing_in_store (no ret
entry) → short_in_store (a ret entry without a[k]) → not_ok_in_store (ret ok = false: the build's own self-check
failed; the numbers are compared anyway, would_match) → too_small (N < 20: reported, not judged) → match (both rules)
→ store_not_final (a mismatch on a day the store's read had not final yet: X + k > that read's end − 3, _final_to) →
mismatch. Every calendar install day gets a class for every k, so the completeness check is exact: gap_days = days
whose D1 or D7 lacks data on one side (missing_in_store / short_in_store / unread). A judged miss on a GA4 day that
was thresholded or had an "(other)" row (X or X + k) is marked (ga4_day_flagged; rules.dX.fail_on_flagged_day).

PRIVATE output: ga4/d1d7_verify.json (write_private — never data/ or site/, never a force), written every
WRITE_EVERY apps (a timeout keeps what is done; an app being checked again keeps its older result there until
its new one lands) and at the end. Per app: the activity days read (coverage of each
day's split against the store's daily active users, thresholding / "(other)" / "(not set)" days, errors), and per
store (an AdMob app id; two ids of one Play package share one GA4 read): class counts for D1, D7 and every k, the
rules' counts, what the tab really shows (shown: only ret entries the tab uses), cohort-size coverage, the 20 worst
mismatches, gap ranges, and a day-by-day table (TABLE_COLS) — one row per install day. A re-run with only_apps_missing
skips the apps the existing file holds as complete and carries them over.

PUBLIC LOG: counts only — progress lines (a side-thread heartbeat too: never a silent minute), how many stores are
still in the build's cohort backfill (ret_from unset), and one result line; no names, ids, emails, dates or user
numbers; stderr is hidden by the workflow step.

QUOTA (per PROPERTY, shared by every app of it — ga4_d1d7_probe's rules, stretched for a run of hours): one request
at a time per property, WORKERS properties in parallel; every call asks returnPropertyQuota. The DAILY token bucket
under half → the property stops for this run; an HOURLY token bucket under half → the property PAUSES (WAIT_SEC, then
one call reads the bucket again; the other properties go on), under a quarter → it stops; the hourly server-error
(10) and potentially-thresholded request (120) counts by the same half / quarter rule; a 429 → stop. Server errors:
each failed call is retried once by ga4._call, 2 failed calls within an hour pause the property until that hour is
over, MAX_5XX_RUN in the run stop it; a day that failed is asked once more at the end of its app. Access tokens (an
hour's life) are refreshed every TOKEN_TTL_SEC and on a 401. The run starts no call after its budget and still
writes what it has.
"""

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from admob_iq import ga4_probe
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_uninstall as gu
from admob_iq.fetch.ga4_d1d7_probe import Stop, write_private

K_MAX = gu.COHORT_DAYS              # D1 .. D30 (the store keeps a[0..30])
HEAD = (1, 7)                       # the headline days the Active users tab shows
SETTLE = 3                          # activity days up to today − 3 (property timezone) are asked
FINAL_LAG = 3                       # a full cohort read on local day `at` ended at at − 2 (from noon) or at − 3: at − 3
                                    # is its sure end, final up to that − ACT_LATE_DAYS (see _final_to)
MIN_N = 20                          # an install day with fewer new users is reported, not judged
USERS_ABS, USERS_REL = 2, 0.02      # users rule: |a_k − A| ≤ max(2, 2% of A)
RATE_PP = 0.005                     # rate rule: |a_k/t − A/N| ≤ 0.5 percentage points
SIZE_REL = 0.02                     # cohort size: |t − N| ≤ 2% of N
COV_OK, COV_MIN_A1 = 0.98, 50       # an activity day's split holds ≥ 98% of the store's daily actives (≥ 50 of them)
WORST = 20
RANGE_CAP = 200                     # at most this many runs per range list (the count of the rest is kept)
WORKERS = 8                         # properties in parallel — one request at a time per property
BUDGET_SEC = 275 * 60               # no new call after 275 min (the job's timeout is 300)
WAIT_SEC = 300                      # an hourly bucket under half: the property pauses this long, then one call
HOUR = 3600
QUOTA_FRAC = pr.QUOTA_FRAC          # 0.5: the probe's half floor
HARD_FRAC = 0.25                    # an hourly token bucket under a quarter: the property stops (the build stops at 10%)
# the hourly COUNT buckets (GA4 standard sizes), under the same half / quarter rule as the token buckets: this run makes
# thousands of calls (the probe's absolute floors of 4-5 left would let it drain 115 of the 120 thresholded requests an
# hour the build of the same property needs, if GA4 ever counted these reports as potentially thresholded)
COUNT_CAP = {"serverErrorsPerProjectPerHour": 10, "potentiallyThresholdedRequestsPerHour": 120}
TICK_SEC = 20                       # a side thread's heartbeat check (a slow call or the final write is never silent)
MAX_5XX = 2                         # failed calls (5xx, each retried once) within an hour → the property pauses
MAX_5XX_RUN = 6                     # … in the run → it stops
MAX_CONSEC_ERR = 5                  # an app stops after 5 failed days in a row (a request GA4 keeps refusing)
TOKEN_TTL_SEC = 45 * 60             # access tokens live an hour: refreshed before that
WRITE_EVERY = 10                    # the private file is rewritten every 10 apps done (and at the end)
PAGE_ROWS = 100000
DATA_DIR = "_private"               # the workflow's read-only clone of the private repo
OUT_PATH = "ga4/d1d7_verify.json"
CLASSES = ("match", "mismatch", "store_not_final", "missing_in_store", "short_in_store", "not_ok_in_store",
           "too_small", "no_ga4_row", "unread", "not_due")
JUDGED = ("match", "mismatch", "store_not_final")
GAP = ("missing_in_store", "short_in_store", "unread")
CODE = {"match": "m", "mismatch": "x", "store_not_final": "f", "missing_in_store": "M", "short_in_store": "s",
        "not_ok_in_store": "o", "too_small": "z", "no_ga4_row": "n", "unread": "u", "not_due": "d"}
TABLE_COLS = ("x", "N", "t", "daily_new", "A1", "a1", "c1", "A7", "a7", "c7", "k_mismatch", "k_judged", "tab_uses")
ACT_COLS = ("d", "rows", "act", "store_a1", "new_row", "store_new", "new_elsewhere", "other_rows", "not_set_act",
            "thresholded", "tokens")


# ── run, tokens, quota ──────────────────────────────────────────────────────────────────────────

class Run(pr.Run):
    """The probe's clock / budget / call counter / counts-only heartbeat, plus the pauses of properties waiting for an
    hourly quota bucket (slept in ≤ 30 s steps, each followed by a heartbeat check: the log is never silent)."""

    def __init__(self, budget=BUDGET_SEC, clock=time.monotonic, sleeper=time.sleep):
        super().__init__(budget, clock)
        self.sleeper, self.waiting = sleeper, 0

    def left(self):
        return self.budget - (self.clock() - self.t0)

    def pulse(self):
        with self.lock:
            now = self.clock()
            beat = now - self.beat >= pr.HEARTBEAT_SEC
            if beat:
                self.beat = now
            n, w, s = self.calls, self.waiting, int(now - self.t0)
        if beat:
            self.say("d1d7 progress: calls %d, waiting %d, %ds" % (n, w, s))

    def sleep(self, sec):
        with self.lock:
            self.waiting += 1
        try:
            rest = float(sec)
            while rest > 0:
                s = min(30.0, rest)
                self.sleeper(s)
                rest -= s
                self.pulse()
        finally:
            with self.lock:
                self.waiting -= 1


class Ticker:
    """`with Ticker(run):` — a daemon thread checks run.pulse() every `every` seconds while the block runs, so the
    counts-only heartbeat also comes while every worker sits in a slow call (up to ~4 min with the 5xx and 401 retries)
    or while the report is written (up to 5 tries)."""

    def __init__(self, run, every=TICK_SEC):
        self.run, self.every, self.ev = run, every, threading.Event()
        self.th = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self.ev.wait(self.every):
            try:
                self.run.pulse()
            except Exception:
                pass

    def __enter__(self):
        self.th.start()
        return self

    def __exit__(self, *exc):
        self.ev.set()
        self.th.join(5)
        return False


class Tokens:
    """Owner → access token: refreshed every TOKEN_TTL_SEC (they live an hour; this run lasts hours) and on a 401.
    Tokens stay in memory only."""

    def __init__(self, cid, sec, pairs, clock=time.monotonic):
        self.cid, self.sec, self.rt, self.clock = cid, sec, dict(pairs), clock
        self.cache, self.lock = {}, threading.Lock()
        self.refreshes = 0

    def get(self, owner, force=False):
        owner = owner or ""
        with self.lock:
            tok, t = self.cache.get(owner, (None, None))
            if tok and not force and self.clock() - t < TOKEN_TTL_SEC:
                return tok
            if owner not in self.rt:
                return None
            self.refreshes += 1
            try:
                tok = ga4.access_token(self.cid, self.sec, self.rt[owner])
            except Exception:
                tok = None
            self.cache[owner] = (tok, self.clock())
            return tok


def new_prop():
    """One property's shared state: its latest quota snapshot (fresh = read since the last pause), the clock times of
    its failed calls, why it stopped, and its pauses."""
    return {"quota": None, "fresh": True, "err_t": [], "stop": None, "waits": 0, "wait_sec": 0}


def quota_gate(q):
    """A property's quota snapshot → None (go on), "wait" (an HOURLY bucket under half — it refills: pause) or "stop"
    (the DAILY token bucket under half, an hourly one under a quarter). Hourly buckets: the token ones (gu.QUOTA_CAP)
    and the server-error / potentially-thresholded request counts (COUNT_CAP: pause ≤ 4 / < 60 left, stop ≤ 2 / < 30)."""
    q, wait = q or {}, False
    for k, cap in list(gu.QUOTA_CAP.items()) + list(COUNT_CAP.items()):
        b = q.get(k) or {}
        if "remaining" not in b:
            continue
        left = pr._int(b["remaining"])
        total = max(cap, pr._int(b.get("consumed")) + left)
        if k == "tokensPerDay":
            if left < QUOTA_FRAC * total:
                return "stop"
        elif left < HARD_FRAC * total:
            return "stop"
        elif left < QUOTA_FRAC * total:
            wait = True
    return "wait" if wait else None


class App(ga4.Ga4App):
    """ga4.Ga4App (stream-pinned, paged, returnPropertyQuota) whose every call first passes its PROPERTY's gate
    (quota / server errors / budget: pause or Stop), refreshes its owner's token on a 401, and counts calls + tokens."""

    def __init__(self, tokens, owner, property_id, stream_id, run, prop):
        super().__init__(tokens.get(owner) or "", property_id, stream_id)
        self.tokens, self.owner, self.run, self.prop = tokens, owner, run, prop
        self.n = self.tok = 0

    def gate(self):
        p = self.prop
        while True:
            why = p["stop"] or self.run.over()
            if why:
                p["stop"] = why
                raise Stop(why)
            now = self.run.clock()
            if len(p["err_t"]) >= MAX_5XX_RUN:
                p["stop"] = "server_errors"
                continue
            recent = [t for t in p["err_t"] if now - t < HOUR]
            wait = 0
            if len(recent) >= MAX_5XX:
                wait = recent[-MAX_5XX] + HOUR - now
            elif p["fresh"]:
                g = quota_gate(p["quota"])
                if g == "stop":
                    p["stop"] = "quota_low"
                    continue
                if g == "wait":
                    wait = WAIT_SEC
            if wait <= 0:
                return
            if self.run.left() <= wait:
                p["stop"] = "budget"
                continue
            p["waits"] += 1
            p["wait_sec"] += int(wait)
            self.run.sleep(wait)
            p["fresh"] = False                          # the snapshot is old now: the next call reads a new one

    def _post(self, method, body):
        self.gate()
        self.run.tick()
        self.n += 1
        p = self.prop
        for attempt in (1, 2):
            self.token = self.tokens.get(self.owner, force=attempt == 2) or self.token
            try:
                j = super()._post(method, body)
                break
            except RuntimeError as e:
                s = str(e)
                if attempt == 1 and s.startswith("HTTP 401"):
                    continue                            # an expired token: refreshed once
                if s.startswith("HTTP 5"):
                    p["err_t"].append(self.run.clock())
                elif s.startswith("HTTP 429"):
                    p["stop"] = "quota_429"
                raise
        p["quota"] = j.get("propertyQuota") or p["quota"]
        p["fresh"] = True
        self.tok += pr._int(((j.get("propertyQuota") or {}).get("tokensPerDay") or {}).get("consumed"))
        return j


# ── the app list ────────────────────────────────────────────────────────────────────────────────

def units_from_state(state):
    """The build's GA4 apps, one per Android stream (ga4_d1d7_probe.apps_from_state), each with every AdMob app id of
    that stream (app_ids: the stores to check — one GA4 read serves them all) and `days`, the activity days to read
    (from the state's store meta; 0 when unknown), for the run's order."""
    state = state or {}
    routes = (state.get("routes") or {}).get("by_package") or {}
    fetch = state.get("fetch") or {}
    units = pr.apps_from_state(state)
    for u in units:
        ids, hs, we = [], [], []
        for aid, st in sorted(fetch.items()):
            r = routes.get((st or {}).get("package")) or {}
            if (str(r.get("property_id")), str(r.get("stream_id"))) != (u["property_id"], u["stream_id"]):
                continue
            ids.append(aid)
            m = (st or {}).get("meta") or {}
            if m.get("history_start") and m.get("window_end"):
                hs.append(gu._d(m["history_start"]))
                we.append(gu._d(m["window_end"]))
        u["app_ids"] = ids
        u["days"] = (max(we) - min(hs)).days + 1 if hs else 0
    return units


def interleave(items, weight):
    """Biggest, smallest, 2nd biggest, 2nd smallest, … — a run stopped early has covered big AND many apps."""
    s = sorted(items, key=lambda i: -weight(i))
    out, i, j = [], 0, len(s) - 1
    while i <= j:
        out.append(s[i])
        i += 1
        if i <= j:
            out.append(s[j])
            j -= 1
    return out


def order_groups(units):
    """Apps grouped by property (one worker per group: a property never has two requests in flight), the groups and the
    apps inside each interleaved by size."""
    by = {}
    for u in units:
        by.setdefault(u["property_id"], []).append(u)
    groups = [interleave(g, lambda u: u.get("days") or 0) for _, g in sorted(by.items())]
    return interleave(groups, lambda g: sum(u.get("days") or 0 for u in g))


def plan_units(units, old, only_missing, cap):
    """→ (todo, carried). only_missing: the apps the existing report holds as complete are carried over, not asked
    again. cap > 0: only the `cap` smallest apps still to do (a quick trial). Every older result of an app not
    checked this run is carried, so a capped or resumed run never drops what the file held."""
    old_apps = {p: r for p, r in ((old or {}).get("apps") or {}).items() if isinstance(r, dict)}
    todo = [u for u in units if not (only_missing and (old_apps.get(u["package"]) or {}).get("complete"))]
    if cap > 0:
        todo = sorted(todo, key=lambda u: (u.get("days") or 0, u["package"]))[:cap]
    doing = {u["package"] for u in todo}
    known = {u["package"] for u in units}
    carried = {p: r for p, r in old_apps.items() if p in known and p not in doing}
    return todo, carried


# ── reading GA4, one activity day per call ─────────────────────────────────────────────────────

def day_body(d):
    """The owner's report as a Data API body: ONE activity day, users by first-session day (report_all adds limit,
    offset and the order; Ga4App the Android + stream filter and returnPropertyQuota)."""
    return {"dateRanges": [gu._rng(d, d)], "dimensions": ga4._dim("firstSessionDate"),
            "metrics": ga4._dim("activeUsers", "newUsers")}


def new_read():
    """What the activity days gave: act {X: {k: activeUsers of first-session day X on X+k}} (k ≤ K_MAX), new {X: newUsers
    on row X of day X}, ok (days read), meta {day: ACT_COLS-like facts}, err {day: error class}."""
    return {"act": {}, "new": {}, "ok": set(), "meta": {}, "err": {}}


def take(rd, d, rows, meta, tok, pages):
    """One activity day's rows → rd (in place)."""
    lo = d - timedelta(days=K_MAX)
    act = new_sum = n_row = new_else = other_r = ns_r = ns_a = 0
    for r in rows:
        f = str(r.get("firstSessionDate") or "")
        a, n = pr._int(r.get("activeUsers")), pr._int(r.get("newUsers"))
        act += a
        new_sum += n
        fd = ga4._d(f)
        if fd is None:
            if f == "(other)":
                other_r += 1
            else:
                ns_r += 1
                ns_a += a
            continue
        if fd == d:
            n_row += n
        else:
            new_else += n
        if lo <= fd <= d:
            rd["act"].setdefault(fd, {})[(d - fd).days] = a
    rd["new"][d] = n_row
    rd["ok"].add(d)
    rd["err"].pop(d, None)
    m = meta or {}
    rd["meta"][d] = {"rows": len(rows), "act": act, "new": new_sum, "new_row": n_row, "new_else": new_else,
                     "other": other_r, "not_set": ns_r, "not_set_act": ns_a,
                     "thresh": bool(m.get("subjectToThresholding")), "loss_other": bool(m.get("dataLossFromOtherRow")),
                     "sampled": bool(m.get("samplingMetadatas")), "tok": tok, "pages": pages}


def read_one(ga, d, rd):
    """Ask activity day d → True when read; an error is kept as its class only (never its text). Stop passes."""
    t0 = ga.tok
    try:
        rows = ga.report_all(day_body(d), page_rows=PAGE_ROWS)
    except Stop:
        raise
    except Exception as e:
        rd["err"][d] = pr._err(e)
        return False
    take(rd, d, rows, ga.last_meta, ga.tok - t0, ga.last_pages)
    return True


def read_all(ga, days, rd):
    """Every activity day, oldest first; each day that failed is asked once more at the end → the stop reason, or None
    when nothing stopped the app."""
    failed, streak = [], 0
    try:
        for d in days:
            if read_one(ga, d, rd):
                streak = 0
                continue
            if rd["err"][d].get("http") in (401, 403):
                return "auth"
            failed.append(d)
            streak += 1
            if streak >= MAX_CONSEC_ERR:
                return "errors"
        for d in failed:
            read_one(ga, d, rd)
    except Stop as e:
        return str(e)
    return None


# ── the comparison ──────────────────────────────────────────────────────────────────────────────

def judge(a, t, A, N):
    """→ (users_ok, rate_ok): |a − A| ≤ max(USERS_ABS, USERS_REL·A); |a/t − A/N| ≤ RATE_PP (False when t or N is 0)."""
    users = abs(a - A) <= max(USERS_ABS, USERS_REL * A)
    rate = bool(t) and bool(N) and abs(a / t - A / N) <= RATE_PP
    return users, rate


def _final_to(e, a, x, we):
    """The last activity day the store's read of cohort X had final: that read's end E − ACT_LATE_DAYS. E is EXACT
    when the read stopped short of day K_MAX (gu._ret_rows keeps a[0 .. min(K_MAX, E − X)], so E = X + len(a) − 1);
    for a full read it is bounded by the read's local day `at` − 3 (settled_end is at − 2 from noon, at − 3 before) and
    the store's window end — the EARLIER bound, so a day that may still have moved is never called a mismatch ("at" is
    also stamped on a kept older read, which only makes E earlier)."""
    if 0 < len(a) <= K_MAX:
        end = x + timedelta(days=len(a) - 1)
    else:
        try:
            end = min(gu._d(e["at"]) - timedelta(days=FINAL_LAG), we)
        except (KeyError, TypeError, ValueError):
            end = we
    return end - timedelta(days=gu.ACT_LATE_DAYS)


def classify(x, k, e, a, t, rd, last, final_to):
    """One install day X × day k → (class, GA4 users A, store users a_k, users_ok, rate_ok) — see the module docstring
    for the order. The rules are evaluated whenever both sides have numbers (would_match for not_ok / too_small)."""
    d = x + timedelta(days=k)
    if d > last:
        return "not_due", None, None, None, None
    if x not in rd["ok"] or d not in rd["ok"]:
        return "unread", None, None, None, None
    n = rd["new"].get(x) or 0
    A = (rd["act"].get(x) or {}).get(k, 0)             # GA4 leaves out empty rows: no row = 0 users
    if not n:
        return "no_ga4_row", A, None, None, None
    if e is None:
        return "missing_in_store", A, None, None, None
    if len(a) <= k:
        return "short_in_store", A, None, None, None
    u, r = judge(a[k], t, A, n)
    if not e.get("ok"):
        return "not_ok_in_store", A, a[k], u, r
    if n < MIN_N:
        return "too_small", A, a[k], u, r
    if u and r:
        return "match", A, a[k], u, r
    if d > final_to:
        return "store_not_final", A, a[k], u, r
    return "mismatch", A, a[k], u, r


def tab_use(e, x, rf):
    """Does the Active users tab use this ret entry (engine.active: ok, t > 0, a[0]/t in [0.9, 1.1], X ≥ ret_from)? →
    None when it does, else the reason."""
    if not e:
        return "no_entry"
    if not e.get("ok"):
        return "not_ok"
    t = pr._int(e.get("t"))
    if t <= 0:
        return "t0"
    a = e.get("a") or []
    if not a or not 0.9 <= pr._int(a[0]) / t <= 1.1:
        return "a0_off"
    if rf and x < rf:
        return "before_ret_from"
    return None


def ranges(days, cap=RANGE_CAP):
    """Dates → {"days": n, "runs": [[first, last], …]} (consecutive runs, ISO; at most `cap`, "cut": how many more)."""
    ds = sorted(set(days))
    runs = []
    for d in ds:
        if runs and (d - runs[-1][1]).days == 1:
            runs[-1][1] = d
        else:
            runs.append([d, d])
    out = {"days": len(ds), "runs": [[a.isoformat(), b.isoformat()] for a, b in runs[:cap]]}
    if len(runs) > cap:
        out["cut"] = len(runs) - cap
    return out


def _stats(v, ok=None):
    v = [x for x in v if x is not None]
    if not v:
        return {"n": 0}
    out = {"n": len(v), "median": round(ga4._median(v), 4), "min": round(min(v), 4), "max": round(max(v), 4)}
    if ok:
        out["within"] = sum(1 for x in v if ok(x))
    return out


def _rate(a, b):
    return round(a / b, 4) if b else None


def _worst(items, n=WORST):
    return sorted(items, key=lambda m: (-abs(m["pp"]) if m["pp"] is not None else 0, -abs(m["users"]), m["x"],
                                        m["k"]))[:n]


RULE_KEYS = ("judged", "users_ok", "rate_ok", "fail_users_only", "fail_rate_only", "fail_both", "fail_on_flagged_day")


def _flagged(rd, *days):
    """Was any of these GA4 days thresholded or folded into "(other)"? (its split can drop users: a mismatch there
    may be GA4's, not the store's)"""
    for d in days:
        m = rd["meta"].get(d) or {}
        if m.get("thresh") or m.get("other") or m.get("loss_other"):
            return True
    return False


def evaluate(s, rd, last):
    """One store against the GA4 days read → its verification (see the module docstring). `last`: the app's last
    activity day asked; this store is judged up to min(last, its own window end) — a day after its window end is one
    its fetch could not have yet (not_due), never a gap (two app ids of one stream can differ by a failed fetch)."""
    hs, we = gu._d(s["history_start"]), gu._d(s["window_end"])
    asked, last = last, min(last, we)
    xs = gu._days(hs, we - timedelta(days=1)) if we > hs else []
    ret, daily = s.get("ret") or {}, s.get("daily") or {}
    rf = gu._d(s["ret_from"]) if s.get("ret_from") else None
    by_k = {k: dict.fromkeys(CLASSES, 0) for k in range(1, K_MAX + 1)}
    rules = {k: dict.fromkeys(RULE_KEYS, 0) for k in HEAD}
    would = {k: {"not_ok_in_store": [0, 0], "too_small": [0, 0]} for k in HEAD}      # [would match, of]
    shown = {k: dict.fromkeys(JUDGED, 0) for k in HEAD}
    tab = dict.fromkeys(("used", "no_entry", "not_ok", "t0", "a0_off", "before_ret_from"), 0)
    per = {k: {c: [] for c in CLASSES if c != "match"} for k in HEAD}
    mism, size, dn_n, rows, gap = [], [], [], [], []
    for x in xs:
        iso = x.isoformat()
        e = ret.get(iso)
        e = e if isinstance(e, dict) else None
        a = [pr._int(v) for v in (e.get("a") or [])] if e else []
        t = pr._int(e.get("t")) if e else None
        n = rd["new"].get(x) if x in rd["ok"] else None
        dn = (daily.get(iso) or [None])[0]
        why = tab_use(e, x, rf)
        tab["used" if why is None else why] += 1
        fin = _final_to(e, a, x, we) if e else we
        head, kbad, kj = {}, 0, 0
        for k in range(1, K_MAX + 1):
            c, A, ak, u, r = classify(x, k, e, a, t, rd, last, fin)
            by_k[k][c] += 1
            kj += c in JUDGED
            flag = c in JUDGED and not (u and r) and _flagged(rd, x, x + timedelta(days=k))
            if c == "mismatch":
                kbad += 1
                m = {"x": iso, "k": k, "t": t, "a": ak, "N": n, "A": A, "store": _rate(ak, t), "ga4": _rate(A, n),
                     "users": ak - A, "class": c}
                m["pp"] = round(100 * (m["store"] - m["ga4"]), 2) if None not in (m["store"], m["ga4"]) else None
                if flag:
                    m["ga4_day_flagged"] = 1                # thresholded / "(other)" on X or X + k
                mism.append(m)
            if k in HEAD:
                head[k] = (c, A, ak)
                if c != "match":
                    per[k][c].append(x)
                if c in JUDGED:
                    rules[k]["judged"] += 1
                    rules[k]["users_ok"] += bool(u)
                    rules[k]["rate_ok"] += bool(r)
                    if not (u and r):                   # which rule failed (rate only: often 1-2 users on a small
                                                        # cohort — 1 user of 100 is 1 point)
                        rules[k]["fail_both" if not (u or r) else "fail_rate_only" if u else "fail_users_only"] += 1
                        rules[k]["fail_on_flagged_day"] += flag
                    if why is None:
                        shown[k][c] += 1
                if c in would[k]:
                    would[k][c][1] += 1
                    would[k][c][0] += bool(u and r)
        if n and n >= MIN_N:
            if e is not None:
                size.append((x, t, n))
            if dn is not None:
                dn_n.append(dn / n)
        if any(head[k][0] in GAP for k in HEAD):
            gap.append(x)
        rows.append([iso, n, t, dn, head[1][1], head[1][2], CODE[head[1][0]], head[7][1], head[7][2],
                     CODE[head[7][0]], kbad, kj, int(why is None)])
    size_r = [t / n for _, t, n in size]
    worst_size = sorted(size, key=lambda v: -abs(v[1] / v[2] - 1))[:10]
    in_win = {x.isoformat() for x in gu._days(hs, we)}          # the fetch also holds the cohort of window_end
    all_k = dict.fromkeys(CLASSES, 0)
    for c in by_k.values():
        for name, v in c.items():
            all_k[name] += v
    return {"history_start": hs.isoformat(), "window_end": we.isoformat(), "ret_from": s.get("ret_from"),
            "ret_to": s.get("ret_to"), "ret_k": s.get("ret_k"), "last_asked": asked.isoformat(),
            "judged_to": last.isoformat(),
            "install_days": len(xs), "ret_days": sum(1 for x in xs if x.isoformat() in ret),
            "ret_outside_window": sum(1 for d in ret if d not in in_win),
            "d1": by_k[1], "d7": by_k[7], "all_k": all_k,
            "by_k": {str(k): {c: v for c, v in by_k[k].items() if v} for k in by_k},
            "rules": {"d%d" % k: rules[k] for k in HEAD},
            "would_match": {"d%d" % k: {c: {"match": v[0], "of": v[1]} for c, v in would[k].items()} for k in HEAD},
            "shown": {"d%d" % k: shown[k] for k in HEAD}, "tab": tab,
            "size": dict(_stats(size_r, lambda r: abs(r - 1) <= SIZE_REL),
                         worst=[[x.isoformat(), t, n] for x, t, n in worst_size]),
            "daily_new_vs_N": _stats(dn_n, lambda r: abs(r - 1) <= SIZE_REL),
            "worst": _worst([m for m in mism if m["k"] in HEAD]), "worst_any_k": _worst(mism),
            "gaps": {"d%d" % k: {c: ranges(v) for c, v in per[k].items() if v} for k in HEAD},
            "gap_days": ranges(gap),
            "daily_missing": ranges([d for d in gu._days(hs, we) if d.isoformat() not in daily]),
            "table": {"cols": list(TABLE_COLS), "rows": rows}}


def activity(rd, days, daily):
    """The activity days asked → what GA4 gave, checked against the store's own daily numbers: coverage = Σ rows'
    activeUsers ÷ the store's daily actives (a split that lost users reads low), newUsers of the day's own row ÷ the
    store's daily new, thresholded / "(other)" / "(not set)" days, errors (class only), and a row per day."""
    m, ok = rd["meta"], sorted(rd["ok"])
    cov, low, ncov, noff, table = [], [], [], [], []
    for d in ok:
        v = m[d]
        new_s, a1_s = (daily.get(d.isoformat()) or [None, None])[:2]
        if a1_s and a1_s >= COV_MIN_A1:
            c = v["act"] / a1_s
            cov.append(c)
            if c < COV_OK:
                low.append(d)
        if new_s and new_s >= MIN_N:
            r = v["new_row"] / new_s
            ncov.append(r)
            if abs(r - 1) > SIZE_REL:
                noff.append(d)
        table.append([d.isoformat(), v["rows"], v["act"], a1_s, v["new_row"], new_s, v["new_else"], v["other"],
                      v["not_set_act"], int(v["thresh"]), v["tok"]])
    errs = {}
    for e in rd["err"].values():
        k = "http_%s" % e["http"] if "http" in e else e.get("type") or "other"
        errs[k] = errs.get(k, 0) + 1
    act_sum = sum(m[d]["act"] for d in ok)
    new_sum = sum(m[d]["new"] for d in ok)
    return {"days": len(days), "read": len(ok), "unread": ranges(set(days) - rd["ok"]), "errors": errs,
            "thresholded": ranges([d for d in ok if m[d]["thresh"]]),
            "with_other": ranges([d for d in ok if m[d]["other"]]),
            "loss_other": ranges([d for d in ok if m[d]["loss_other"]]),
            "sampled": ranges([d for d in ok if m[d]["sampled"]]),
            "not_set_share": _rate(sum(m[d]["not_set_act"] for d in ok), act_sum),
            "new_elsewhere_share": _rate(sum(m[d]["new_else"] for d in ok), new_sum),
            "cov": _stats(cov, lambda c: c >= COV_OK), "cov_low": ranges(low),
            "new_cov": _stats(ncov, lambda r: abs(r - 1) <= SIZE_REL), "new_cov_off": ranges(noff),
            "rows_max": max([m[d]["rows"] for d in ok], default=0),
            "pages_max": max([m[d]["pages"] or 0 for d in ok], default=0),
            "tokens_per_call": _stats([m[d]["tok"] for d in ok]),
            "table": {"cols": list(ACT_COLS), "rows": table}}


# ── one app ─────────────────────────────────────────────────────────────────────────────────────

def slim(store):
    """The few store fields the check needs — the big store itself is freed at once."""
    daily = store.get("daily") or {}
    return {"history_start": store.get("history_start"), "window_end": store.get("window_end"),
            "ret_from": store.get("ret_from"), "ret_to": store.get("ret_to"), "ret": store.get("ret") or {},
            "ret_k": ((store.get("flags") or {}).get("impact") or {}).get("ret_k"),
            "property_id": store.get("property_id"), "stream_id": store.get("stream_id"),
            "daily": {d: [pr._int((v or {}).get("new")), pr._int((v or {}).get("a1"))] for d, v in daily.items()}}


def load_stores(unit, data_dir):
    """→ ({app id: slim store}, {app id: why it can't be checked})."""
    ok, bad = {}, {}
    for aid in unit.get("app_ids") or []:
        st = gu.load_store(gu.store_path(data_dir, aid))
        if not st:
            bad[aid] = "no_store"
        elif (str(st.get("property_id")), str(st.get("stream_id"))) != (unit["property_id"], unit["stream_id"]):
            bad[aid] = "store_other_stream"
        elif not st.get("history_start") or not st.get("window_end"):
            bad[aid] = "store_without_history"
        else:
            ok[aid] = slim(st)
        st = None
    return ok, bad


def verify_unit(run, unit, tokens, data_dir, now, prop):
    """One app (stream): read its activity days, then check each of its stores → its result."""
    res = {"package": unit["package"], "property_id": unit["property_id"], "stream_id": unit["stream_id"],
           "owner": unit.get("owner"), "tz": unit["tz"], "app_ids": list(unit.get("app_ids") or []),
           "checked_at": gu._now_iso(now), "complete": False, "stores": {}}
    stores, bad = load_stores(unit, data_dir)
    res["stores"].update({aid: {"err": why} for aid, why in bad.items()})
    if not stores:
        res["err"] = "no_store"
        return res
    today = ga4.window_end_in(unit["tz"], now, lag=0)
    hs = min(gu._d(s["history_start"]) for s in stores.values())
    we = max(gu._d(s["window_end"]) for s in stores.values())
    last = min(we, today - timedelta(days=SETTLE))
    days = gu._days(hs, last) if last >= hs else []
    res.update(today=today.isoformat(), history_start=hs.isoformat(), window_end=we.isoformat(),
               last_asked=last.isoformat())
    rd = new_read()
    ga = App(tokens, unit.get("owner"), unit["property_id"], unit["stream_id"], run, prop)
    stopped = None
    if days:
        stopped = "auth" if not ga.token else read_all(ga, days, rd)
    # the property's counters so far (shared by its apps): failed calls on 5xx, pauses for an hourly bucket / 5xx
    res.update(stopped=stopped, complete=bool(not stopped and rd["ok"] >= set(days)), calls=ga.n, tokens=ga.tok,
               prop_server_errors=len(prop["err_t"]), prop_waits=prop["waits"], prop_wait_sec=prop["wait_sec"])
    first = stores[sorted(stores)[0]]
    res["activity"] = pr._safely(activity, rd, days, first["daily"])
    for aid, s in sorted(stores.items()):
        res["stores"][aid] = pr._safely(evaluate, s, rd, last)
    return res


# ── the report ──────────────────────────────────────────────────────────────────────────────────

class Book:
    """The results so far (thread-safe): workers add finished apps; a snapshot is a shallow copy of finished results,
    which are never changed again — safe to serialize while other apps are still being checked. held: the existing
    file's results of the apps this run checks again — a PARTIAL snapshot keeps each until its new result replaces it,
    so a run cut by the job's timeout never leaves the file with less than it had."""

    def __init__(self, carried, held=None):
        self.apps, self.lock, self.done = dict(carried or {}), threading.Lock(), 0
        self.held = {p: r for p, r in (held or {}).items() if isinstance(r, dict)}

    def add(self, pkg, res):
        with self.lock:
            self.apps[pkg] = res
            self.done += 1
            return self.done

    def snapshot(self, partial=False):
        with self.lock:
            out = dict(self.apps)
            if partial:
                for p, r in self.held.items():
                    out.setdefault(p, r)
            return out


def _stores(apps):
    return [s for a in apps.values() for s in ((a or {}).get("stores") or {}).values()
            if isinstance(s, dict) and isinstance(s.get("d1"), dict)]


def _judged(c):
    return sum(c.get(k, 0) for k in JUDGED)


def counts(apps, run, total):
    """The public counts (no ids, names, dates or user numbers)."""
    st = _stores(apps)

    def tot(key, cls):
        return sum((s.get(key) or {}).get(cls, 0) for s in st)
    stopped = [a.get("stopped") for a in apps.values() if a.get("stopped")]
    errs = sum(1 for a in apps.values() if a.get("err") or a.get("crash"))
    errs += sum(sum(((a.get("activity") or {}).get("errors") or {}).values()) for a in apps.values())
    return {"backfill": sum(1 for s in st if not s.get("ret_from")),        # the build's cohort backfill not done
            "apps": total, "apps_done": len(apps), "apps_complete": sum(1 for a in apps.values() if a.get("complete")),
            "install_days": sum(s.get("install_days") or 0 for s in st),
            "d1_match": tot("d1", "match"), "d1_judged": sum(_judged(s["d1"]) for s in st),
            "d7_match": tot("d7", "match"), "d7_judged": sum(_judged(s["d7"]) for s in st),
            "k_match": tot("all_k", "match"), "k_judged": sum(_judged(s.get("all_k") or {}) for s in st),
            "not_final": tot("d1", "store_not_final") + tot("d7", "store_not_final"),
            "missing": tot("d1", "missing_in_store"), "not_ok": tot("d1", "not_ok_in_store"),
            "small": tot("d1", "too_small"), "unread": tot("d1", "unread"),
            "calls": run.calls, "stopped": len(stopped), "errors": errs, "seconds": run.elapsed(),
            "tokens": sum(pr._int(a.get("tokens")) for a in apps.values())}


COUNT_KEYS = ("apps_complete", "apps", "install_days", "d1_match", "d1_judged", "d7_match", "d7_judged", "k_match",
              "k_judged", "not_final", "missing", "not_ok", "small", "unread", "backfill", "calls", "stopped", "errors",
              "seconds")


def public_line(c):
    return ("d1d7 verify: apps %d/%d complete, install days %d, D1 match %d/%d, D7 match %d/%d, D1-30 match %d/%d, "
            "not final %d, missing %d, not ok %d, small %d, unread %d, stores in backfill %d, calls %d, stopped %d, "
            "errors %d, %ds" % tuple(pr._int((c or {}).get(k)) for k in COUNT_KEYS))


def summary(apps):
    """Across apps: class totals for D1 / D7 / every k, the rules, what the tab shows, and one compact line per app."""
    st = _stores(apps)
    tot = {}
    for key in ("d1", "d7", "all_k"):
        tot[key] = {c: sum((s.get(key) or {}).get(c, 0) for s in st) for c in CLASSES}
    per = {}
    for p, a in sorted(apps.items()):
        for aid, s in sorted(((a or {}).get("stores") or {}).items()):
            if not isinstance(s, dict) or "d1" not in s:
                continue
            per["%s|%s" % (p, aid)] = {
                "complete": bool(a.get("complete")), "stopped": a.get("stopped"), "install_days": s["install_days"],
                "d1": [s["d1"]["match"], _judged(s["d1"])], "d7": [s["d7"]["match"], _judged(s["d7"])],
                "k": [s["all_k"]["match"], _judged(s["all_k"])],
                "shown_d1": [s["shown"]["d1"]["match"], _judged(s["shown"]["d1"])],
                "shown_d7": [s["shown"]["d7"]["match"], _judged(s["shown"]["d7"])],
                "missing": s["d1"]["missing_in_store"], "not_ok": s["d1"]["not_ok_in_store"],
                "gap_days": s["gap_days"]["days"], "size_within": (s["size"].get("within"), s["size"].get("n")),
                "cov_min": ((a.get("activity") or {}).get("cov") or {}).get("min")}
    return {"totals": tot,
            "rules": {k: {r: sum((s.get("rules") or {}).get(k, {}).get(r, 0) for s in st) for r in RULE_KEYS}
                      for k in ("d1", "d7")},
            "shown": {k: {c: sum((s.get("shown") or {}).get(k, {}).get(c, 0) for s in st) for c in JUDGED}
                      for k in ("d1", "d7")},
            "apps": per}


def build_report(apps, run, now, total, partial):
    return {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "run_started": gu._now_iso(now),
            "partial": partial,
            "rules": {"users": "|a_k - A| <= max(%d, %g%% of A)" % (USERS_ABS, 100 * USERS_REL),
                      "rate": "|a_k/t - A/N| <= %g pp" % (100 * RATE_PP), "size": "|t - N| <= %g%% of N" % (100 * SIZE_REL),
                      "min_n": MIN_N, "k_max": K_MAX, "settle_days": SETTLE, "final_lag": FINAL_LAG},
            "legend": {"classes": list(CLASSES), "codes": CODE, "table_cols": list(TABLE_COLS),
                       "activity_cols": list(ACT_COLS)},
            "counts": pr._safely(counts, apps, run, total, fallback={"apps": total, "calls": run.calls}),
            "summary": pr._safely(summary, apps), "apps": apps}


# ── the run ─────────────────────────────────────────────────────────────────────────────────────

def run_verify(units, carried, cid, sec, tokens, data_dir, now=None, budget=BUDGET_SEC, clock=time.monotonic,
               sleeper=time.sleep, workers=WORKERS, total=None, writer=None, held=None, run=None):
    """Check every unit → the report (dict). Never raises for one app's failure; prints counts-only progress (and a
    side-thread heartbeat). writer(report) → bool: called with a partial report every WRITE_EVERY apps done. held: the
    existing file's results of these units (kept in partial reports until replaced)."""
    run = run or Run(budget, clock, sleeper)
    now = now or datetime.now(timezone.utc)
    tk = Tokens(cid, sec, tokens, clock)
    book = Book(carried, held)
    total = total or (len(units) + len(carried or {}))
    props = {u["property_id"]: new_prop() for u in units}
    wlock = threading.Lock()

    def one(group):
        for u in group:
            try:
                res = verify_unit(run, u, tk, data_dir, now, props[u["property_id"]])
            except Exception as e:                   # a bug for one app must not cost the others
                res = {"package": u["package"], "crash": type(e).__name__, "complete": False}
            n = book.add(u["package"], res)
            run.say("d1d7 verify: apps %d/%d done, calls %d, %ds" % (n, len(units), run.calls, run.elapsed()))
            if writer and n % WRITE_EVERY == 0 and n < len(units):
                with wlock:
                    try:
                        ok = writer(build_report(book.snapshot(partial=True), run, now, total, True))
                    except Exception:
                        ok = False
                run.say("d1d7 verify: partial report %s" % ("written" if ok else "write failed"))

    with Ticker(run), ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(one, order_groups(units)))
    return build_report(book.snapshot(), run, now, total, False)


def backfill_pending(units, data_dir):
    """→ (stores whose cohort backfill has not reached its edge yet — ret_from unset: their older install days will
    read missing_in_store —, stores found). Read-only, counts only."""
    pend = found = 0
    for u in units:
        for aid in u.get("app_ids") or []:
            st = gu.load_store(gu.store_path(data_dir, aid))
            if st:
                found += 1
                pend += not st.get("ret_from")
            st = None
    return pend, found


def _old_report(path):
    try:
        with open(path, encoding="utf-8") as f:
            j = json.load(f)
        return j if isinstance(j, dict) else None
    except (OSError, ValueError):
        return None


def _flag(v):
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def main(env=None, now=None, clock=time.monotonic, sleeper=time.sleep):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    root = env.get("VERIFY_DATA_DIR") or DATA_DIR
    data_dir = os.path.join(root, "data")
    units = units_from_state(gu.load_state(data_dir))
    if not units:
        sys.exit("no GA4 app routes in the private state")
    old = _old_report(os.path.join(root, OUT_PATH))
    todo, carried = plan_units(units, old, _flag(env.get("VERIFY_ONLY_MISSING")), pr._int(env.get("VERIFY_MAX_APPS")))
    budget = pr._int(env.get("VERIFY_BUDGET_SEC")) or BUDGET_SEC
    print("d1d7 verify: %d app(s) to check, %d carried over, ~%d activity days"
          % (len(todo), len(carried), sum(u.get("days") or 0 for u in todo)), flush=True)
    if not todo:
        print("d1d7 verify: nothing to do", flush=True)
        return
    pend = pr._safely(lambda: dict(zip(("pending", "found"), backfill_pending(todo, data_dir))))
    print("d1d7 verify: %d of %d store(s) still in their cohort backfill"
          % (pr._int(pend.get("pending")), pr._int(pend.get("found"))), flush=True)
    old_apps = (old or {}).get("apps") or {}
    held = {u["package"]: old_apps[u["package"]] for u in todo if isinstance(old_apps.get(u["package"]), dict)}
    run = Run(budget, clock, sleeper)

    def writer(rep):
        return write_private(OUT_PATH, pr._dump(rep), "ga4 d1d7 verify (partial)")
    report = run_verify(todo, carried, cid, sec, tokens, data_dir, now=now, budget=budget, clock=clock,
                        sleeper=sleeper, total=len(units), writer=writer, held=held, run=run)
    print(public_line(report["counts"]), flush=True)
    with Ticker(run):
        ok = write_private(OUT_PATH, pr._dump(report), "ga4 d1d7 verify")
    if not ok:
        sys.exit("private repo write failed")            # stderr: hidden by the workflow step
    print("d1d7 verify: report written", flush=True)


if __name__ == "__main__":
    main()
