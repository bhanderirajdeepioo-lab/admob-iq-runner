"""One-off GA4 probe, run by .github/workflows/ga4-d1d7-probe.yml: can the owner's "one day, Country + First session
date" report give NEW USERS BACK NEXT DAY (D1) and AFTER 7 DAYS (D7) for OLD install days too — months or years
back — although every property kept event data only 2 months until 26 Sep 2026?

The owner's method (Firebase → Analytics → "Demographic details: Country", secondary dimension "First session date",
date range ONE day D): each row holds the users active on D, grouped by the day they first opened the app. For an
install day X:
    D1(X) = activeUsers on D = X+1 with firstSessionDate = X  ÷  newUsers of X
    D7(X) = activeUsers on D = X+7 with firstSessionDate = X  ÷  newUsers of X
Google documents that data retention does not touch standard reports (secondary dimensions included), but not which
table a Data API query is answered from; an earlier diagnose (ga4_diagnose.py) saw user counts by firstSessionDate
vanish for days older than ~2 months on multi-day ranges. So for every GA4 app of the build and install days
X = today − age, age in AGES (only X ≥ the app's first data day and X + 7 ≤ the last settled day), this asks:
  F   the owner's method: ONE single-day runReport per activity day D in {X, X+1, X+7}, dims [firstSessionDate],
      every row (paged). Self-checked: Σ rows activeUsers ÷ that day's activeUsers from a dims [date] report
      (coverage; the TOTAL aggregation of the same call too; Σ eventCount too, ev_cov), newUsers on the row
      firstSessionDate = D ÷ the day's newUsers, "(other)" / "(not set)" rows and their share, the share of D's
      actives whose first session is ≥ OLD_DAYS old (old installs do appear on old days) — then D1 / D7;
  Fc  the same with dims [country, firstSessionDate] — the owner's screen — for 3 apps (biggest, oldest, a small one)
      × 3 ages (recent, ~200, ~500 days): Σ over countries = F?
  P   the three days packed into ONE request (3 one-day dateRanges), same 3 apps, every age: equal to F? (a backfill
      would need 3× fewer calls);
  C   the cohortSpec API (fetch_ret's method): one DAILY single-day cohort X, days 0..7 → cohortTotalUsers ÷ newUsers
      of X (coverage), D1, D7 — next to F;
  S   the owner's own two reports — the screenshot (15 Sep 2026) and the CSV export (17 Aug 2026) — as dims
      [country, firstSessionDate] on that day, every app: totals + each country's row for first-session day D and
      D−1, to match against the owner's numbers.
Plus each property's data-retention settings (Admin API, read-only), and the reference itself day by day (ref_series)
with X's actives per event against the last 28 days' (ref_ape_rel): coverage only compares the split with the date-level
report, so if the date-level user counts were retention-limited as well, ref_ape_rel (events survive) would fall far
under 1 on old days while the coverage still read ~1.

The app list is the build's own: data/ga4_uninstall/state.json in the PRIVATE repo (the routes the hourly fetch uses,
each with its owner's token). Output: ga4/d1d7_probe.json in the PRIVATE repo — raw results per app and install day and
a summary per method × age. PUBLIC LOG: progress counts and ONE result line of counts; no names, ids, emails, user or
revenue numbers, no API error text; a counts-only heartbeat at least every HEARTBEAT_SEC. QUOTA: every call asks
returnPropertyQuota (tokens are recorded per call). The quota state is PER PROPERTY (shared by every app of it): a
property stops politely when any token bucket is under HALF (QUOTA_FRAC — this one-off leaves the hourly build at least
half of every bucket, where the build's own rule stops only at 10%), when ≤ 4 server-error / ≤ 5 thresholded requests
are left this hour, on a 429, or after MAX_5XX server errors (each is retried once by ga4._call, so ≤ 4 of the 10 an
hour the project gets per property); one request at a time per property (WORKERS properties in parallel); the run stops
starting calls at its time budget and still writes what it has.
"""

import base64
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import requests

from admob_iq import ga4_probe
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_uninstall as gu
from admob_iq.fetch.ga4_diagnose import _private_json

# install-day ages (days before today in the property's timezone), asked in THIS order: a control inside the old
# 2-month retention first, then spread out, so a run cut by its budget still spans every age range
AGES = (20, 70, 200, 550, 900, 45, 100, 150, 300, 400, 700)
LAGS = (0, 1, 7)                    # activity days X, X+1, X+7
REF_DAYS = 1000                     # the dims [date] reference reaches this far back (≥ max(AGES) + 7)
METS = ("activeUsers", "newUsers", "totalUsers", "sessions", "userEngagementDuration", "eventCount")
MIN_METS = ("activeUsers", "newUsers")      # the fallback when GA4 rejects METS with these dimensions (HTTP 400)
SHORT = {"activeUsers": "act", "newUsers": "new", "totalUsers": "tot", "sessions": "ses",
         "userEngagementDuration": "eng", "eventCount": "ev"}
FC_WANT = (20, 200, 500)            # Fc ages: the app's available age nearest to each
EXPORT_DAYS = ("2026-09-15", "2026-08-17")  # the owner's screenshot day and CSV-export day (S)
OK_COV = 0.98                       # a day / cohort at ≥ 98% of the day's own total counts as complete
OLD_DAYS = 30                       # "old" users: first session ≥ 30 days before the activity day
SMALL_MIN_DAU = 50                  # Fc's small app: the smallest with ≥ 50 daily active users (else the smallest)
MAX_5XX = 2                         # a property stops after 2 failed calls on 5xx (≤ 4 server errors with the retry)
QUOTA_FRAC = 0.5                    # a property stops when any token bucket has less than half left
WORKERS = 4                         # properties probed in parallel — one request at a time per property
BUDGET_SEC = 22 * 60                # no new call after 22 min (the job's timeout is 30)
HEARTBEAT_SEC = 60                  # a counts-only progress line at least this often while calls go on
WRITE_TRIES = 5                     # the private write: attempts (sha re-read each time; never a force)
PAGE_ROWS = 100000
STATE_PATH = "data/ga4_uninstall/state.json"
OUT_PATH = "ga4/d1d7_probe.json"
AGE_BUCKETS = (("0", 0, 0), ("1", 1, 1), ("2_7", 2, 7), ("8_29", 8, 29), ("30_89", 30, 89), ("90_364", 90, 364),
               ("365+", 365, 10 ** 7))
OLD_BUCKETS = ("30_89", "90_364", "365+")


class Stop(Exception):
    """This app's probe stops here: quota low, a 429, too many server errors, or the run's time budget."""


class Run:
    """The run's clock, budget, call counter and (locked) public progress lines."""

    def __init__(self, budget=BUDGET_SEC, clock=time.monotonic):
        self.clock, self.budget = clock, budget
        self.t0 = clock()
        self.beat = self.t0
        self.lock = threading.Lock()
        self.calls = 0

    def over(self):
        return "budget" if self.clock() - self.t0 >= self.budget else None

    def tick(self):
        """One more call; every HEARTBEAT_SEC a counts-only line, so the public log is never silent for minutes."""
        with self.lock:
            self.calls += 1
            now = self.clock()
            beat = now - self.beat >= HEARTBEAT_SEC
            if beat:
                self.beat = now
            n, s = self.calls, int(now - self.t0)
        if beat:
            self.say("d1d7 progress: calls %d, %ds" % (n, s))

    def elapsed(self):
        return int(self.clock() - self.t0)

    def say(self, msg):
        with self.lock:
            print(msg, flush=True)


def new_prop():
    """One property's shared probe state: its latest quota snapshot, its 5xx count and why it stopped. Quota buckets are
    per property, so every app (stream) of a property reads and writes the same one."""
    return {"quota": None, "server_errors": 0, "stop": None}


class App(ga4.Ga4App):
    """ga4.Ga4App (stream-pinned, paged, returnPropertyQuota) that keeps each raw response (totals, metadata), counts
    calls and tokensPerDay per kind of measurement, and refuses a call once its PROPERTY must stop (raises Stop)."""

    def __init__(self, token, property_id, stream_id, run, prop=None):
        super().__init__(token, property_id, stream_id)
        self.run, self.raw, self.kind = run, {}, "other"
        self.prop = new_prop() if prop is None else prop
        self.by_kind, self.tok, self.min_mets = {}, 0, False

    @property
    def stop(self):
        return self.prop["stop"]

    @property
    def server_errors(self):
        return self.prop["server_errors"]

    def _post(self, method, body):
        p = self.prop
        why = p["stop"] or self.run.over() or ("quota_low" if quota_low(p["quota"]) else None)
        if why:
            p["stop"] = why
            raise Stop(why)
        k = self.by_kind.setdefault(self.kind, {"calls": 0, "tokens": 0})
        k["calls"] += 1
        self.run.tick()
        try:
            j = super()._post(method, body)
        except RuntimeError as e:
            s = str(e)
            if s.startswith("HTTP 5"):
                p["server_errors"] += 1
                if p["server_errors"] >= MAX_5XX:
                    p["stop"] = "server_errors"
            elif s.startswith("HTTP 429"):
                p["stop"] = "quota_429"
            raise
        self.raw = j
        p["quota"] = j.get("propertyQuota") or p["quota"]
        t = _int(((j.get("propertyQuota") or {}).get("tokensPerDay") or {}).get("consumed"))
        k["tokens"] += t
        self.tok += t
        return j


# ── small helpers ───────────────────────────────────────────────────────────────────────────────

def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def quota_low(q):
    """Any token bucket (the uninstall fetch's buckets and sizes, gu.QUOTA_CAP) with less than QUOTA_FRAC (half) left —
    stricter than the fetch's own 10%, so this one-off never pushes the hourly build of the same property into its
    quota stop — or ≤ 4 server errors / ≤ 5 potentially thresholded requests left this hour for the property."""
    q = q or {}
    for k, floor in (("serverErrorsPerProjectPerHour", 4), ("potentiallyThresholdedRequestsPerHour", 5)):
        b = q.get(k) or {}
        if "remaining" in b and _int(b["remaining"]) <= floor:
            return True
    for k, cap in gu.QUOTA_CAP.items():
        b = q.get(k) or {}
        if "remaining" in b:
            left = _int(b["remaining"])
            if left < QUOTA_FRAC * max(cap, _int(b.get("consumed")) + left):
                return True
    return False


def _ratio(a, b):
    return round(a / b, 4) if a is not None and b else None


def _median(v):
    v = [x for x in v if x is not None]
    return round(ga4._median(v), 4) if v else None


def _ymd(d):
    return d.strftime("%Y%m%d")


def _err(e):
    """An exception → its class only: {"http": 400, "status": "INVALID_ARGUMENT"} for a Google API error, else
    {"type": "ConnectionError"} — never the message text."""
    s = str(e)
    if s.startswith("HTTP "):
        head = s[5:].split(":", 2)
        out = {"http": _int(head[0])}
        st = head[1].strip() if len(head) > 1 else ""
        if st and st.replace("_", "").isalpha() and st.isupper():
            out["status"] = st
        return out
    return {"type": type(e).__name__}


def _guard(ga, kind, fn):
    """fn() with ga's calls counted under `kind` → its result (+ "tok", the tokensPerDay it cost) or {"err": class};
    a Stop is passed on (the app stops)."""
    ga.kind = kind
    t0 = ga.tok
    try:
        out = fn()
    except Stop:
        raise
    except Exception as e:
        return {"err": _err(e), "tok": ga.tok - t0}
    if isinstance(out, dict):
        out["tok"] = ga.tok - t0
    return out


def _bucket(age):
    if age < 0:
        return "future"
    for name, lo, hi in AGE_BUCKETS:
        if lo <= age <= hi:
            return name
    return "365+"


def _meta(ga):
    m = (ga.raw or {}).get("metadata") or {}
    return {"thresh": bool(m.get("subjectToThresholding")), "loss_other": bool(m.get("dataLossFromOtherRow")),
            "sampled": bool(m.get("samplingMetadatas"))}


def _totals(ga):
    """The TOTAL row (metricAggregations) of the last response → {metric: value}; {} when not asked / absent."""
    j = ga.raw or {}
    t = ga4._rows({"dimensionHeaders": j.get("dimensionHeaders"), "metricHeaders": j.get("metricHeaders"),
                   "rows": j.get("totals")})
    return t[0] if t else {}


# ── the app list, the install days ──────────────────────────────────────────────────────────────

def apps_from_state(state):
    """The build's GA4 apps: data/ga4_uninstall/state.json → [{app_id, package, property_id, stream_id, owner, tz}]
    — every app the hourly fetch keeps (state.fetch) whose package has a route, one per stream."""
    state = state or {}
    routes = (state.get("routes") or {}).get("by_package") or {}
    tzs = state.get("tz") or {}
    out, seen = [], set()
    for aid, st in sorted((state.get("fetch") or {}).items()):
        st = st or {}
        pkg = st.get("package")
        r = routes.get(pkg) if pkg else None
        if not r or not r.get("property_id") or not r.get("stream_id"):
            continue
        key = (str(r["property_id"]), str(r["stream_id"]))
        if key in seen:
            continue
        seen.add(key)
        out.append({"app_id": aid, "package": pkg, "property_id": key[0], "stream_id": key[1],
                    "owner": r.get("owner"), "tz": tzs.get(key[0]) or (st.get("meta") or {}).get("time_zone") or "UTC"})
    return out


def pick_days(today, end, first_day, ages=AGES):
    """→ [(age, X)]: X = today − age, kept only when X ≥ the app's first data day and X + 7 ≤ end (settled)."""
    out = []
    for a in ages:
        x = today - timedelta(days=a)
        if first_day and x >= first_day and x + timedelta(days=LAGS[-1]) <= end:
            out.append((a, x))
    return out


def fc_ages(avail):
    """Fc's ages for an app: its available age nearest to each of FC_WANT (no repeats)."""
    out = []
    for w in FC_WANT:
        if avail:
            a = min(avail, key=lambda v: (abs(v - w), v))
            if a not in out:
                out.append(a)
    return out


def pick_country_apps(infos):
    """{package: {first_day, dau28}} → [biggest (28-day mean DAU), oldest (first data day), a small one (the smallest
    with ≥ SMALL_MIN_DAU, else the smallest)] — three different apps when there are three."""
    ok = [(p, i) for p, i in sorted(infos.items()) if i.get("dau28") and i.get("first_day")]
    if not ok:
        return []
    big = max(ok, key=lambda t: t[1]["dau28"])[0]
    rest = [t for t in ok if t[0] != big]
    old = min(rest, key=lambda t: (t[1]["first_day"], -t[1]["dau28"]))[0] if rest else None
    rest = [t for t in rest if t[0] != old]
    pool = [t for t in rest if t[1]["dau28"] >= SMALL_MIN_DAU] or rest
    small = min(pool, key=lambda t: t[1]["dau28"])[0] if pool else None
    return [p for p in (big, old, small) if p]


# ── the measurements ────────────────────────────────────────────────────────────────────────────

def ref_report(ga, start, end):
    """dims [date] over [start, end] → {date: {metric: value}}: each day's own total — what every firstSessionDate
    split is checked against (a plain by-date report, the dashboard's daily numbers)."""
    rows = ga.report_all({"dateRanges": [gu._rng(start, end)], "dimensions": ga4._dim("date"),
                          "metrics": ga4._dim(*METS)}, page_rows=PAGE_ROWS)
    out = {}
    for r in rows:
        d = ga4._d(r.get("date"))
        if d:
            out[d] = {m: r.get(m) or 0 for m in METS}
    return out


def _mets_report(ga, body):
    """report_all with METS and the TOTAL aggregation; a 400 (GA4 won't pair something with these dimensions) → once
    more with MIN_METS and no aggregation, and every later call of this app asks only that (ga.min_mets)."""
    if not ga.min_mets:
        try:
            return ga.report_all(dict(body, metrics=ga4._dim(*METS), metricAggregations=["TOTAL"]),
                                 page_rows=PAGE_ROWS)
        except RuntimeError as e:
            if not str(e).startswith("HTTP 400"):
                raise
            ga.min_mets = True
    return ga.report_all(dict(body, metrics=ga4._dim(*MIN_METS)), page_rows=PAGE_ROWS)


def day_body(d, dims):
    """The owner's report as a Data API body: ONE activity day, `dims` (firstSessionDate [, country])."""
    return {"dateRanges": [gu._rng(d, d)], "dimensions": ga4._dim(*dims)}


def day_summary(rows, d, x, ref, ga, key="firstSessionDate"):
    """One activity day's rows (dims [firstSessionDate] or [country, firstSessionDate]) → the self-check and the row of
    install day X (cell_x, summed over countries). ref = the day's dims [date] totals."""
    by, hist = {}, {}
    other = [0, 0]                                   # rows, actives — any dimension "(other)"
    not_set = [0, 0]                                 # rows, actives — no usable first-session date
    new_else, countries = 0, set()
    for r in rows:
        f, a = str(r.get(key) or ""), r.get("activeUsers") or 0
        if "country" in r:
            countries.add(r.get("country"))
        if any(str(v) == "(other)" for k, v in r.items() if isinstance(v, str)):
            other[0] += 1
            other[1] += a
        fd = ga4._d(f)
        if fd is None:
            if f != "(other)":
                not_set[0] += 1
                not_set[1] += a
            hist["invalid"] = hist.get("invalid", 0) + a
        else:
            b = _bucket((d - fd).days)
            hist[b] = hist.get(b, 0) + a
            c = by.setdefault(fd, dict.fromkeys(METS, 0))
            for m in METS:
                c[m] += r.get(m) or 0
        if fd != d:
            new_else += r.get("newUsers") or 0
    act = sum(r.get("activeUsers") or 0 for r in rows)
    tot = _totals(ga).get("activeUsers")
    ref = ref or {}
    ra, rn = ref.get("activeUsers") or 0, ref.get("newUsers") or 0
    # events survive the old retention: Σ rows eventCount ÷ the day's → does the split lose whole users or only counts
    ev_cov = None if ga.min_mets else _ratio(sum(r.get("eventCount") or 0 for r in rows), ref.get("eventCount") or 0)
    cd = (by.get(d) or {}).get("newUsers", 0)
    cx = by.get(x) or dict.fromkeys(METS, 0)
    out = dict(_meta(ga), date=d.isoformat(), rows=len(rows), row_count=ga.last_row_count, pages=ga.last_pages,
               empty=not rows, act=act, act_total=tot, ref_act=ra, ref_new=rn, cov=_ratio(act, ra),
               cov_total=_ratio(tot, ra), ev_cov=ev_cov, new_row=cd, new_cov=_ratio(cd, rn), new_elsewhere=new_else,
               cell_x={SHORT[m]: cx.get(m, 0) for m in METS}, fsd_days=len(by),
               other={"rows": other[0], "act_share": _ratio(other[1], act)},
               not_set={"rows": not_set[0], "act_share": _ratio(not_set[1], act)},
               hist=dict(sorted(hist.items())), old_share=_ratio(sum(hist.get(b, 0) for b in OLD_BUCKETS), act),
               mets="min" if ga.min_mets else "all")
    if countries:
        out["countries"] = len(countries)
    return out


def measure_f(ga, x, ref, kind="F", dims=("firstSessionDate",)):
    """The owner's method for install day X: one single-day report per activity day X, X+1, X+7 → the days' self-checks
    and D1 / D7."""
    days = {}
    for n in LAGS:
        d = x + timedelta(days=n)
        days["d%d" % n] = _guard(ga, kind, lambda d=d: day_summary(_mets_report(ga, day_body(d, dims)), d, x,
                                                                    ref.get(d), ga))
    return derive(days, ref, x)


def derive(days, ref, x):
    """X's three days → D1 / D7 ÷ newUsers of X (the dims [date] report), and ÷ the X row's own actives on X (D1_a,
    D7_a); cov = the weakest day's coverage; ok = every day read, none empty, cov ≥ OK_COV."""
    d0, d1, d7 = (days.get("d%d" % n) or {} for n in LAGS)
    good = all("err" not in dd and dd and not dd.get("empty") for dd in (d0, d1, d7))

    def cell(dd, k="act"):
        return (dd.get("cell_x") or {}).get(k) if "err" not in dd and dd else None
    covs = [dd.get("cov") for dd in (d0, d1, d7)]
    cov = min(covs) if good and all(c is not None for c in covs) else None
    den = (ref.get(x) or {}).get("newUsers") or 0
    return dict(days, den_new=den, den_new_fsd=cell(d0, "new"), den_act_fsd=cell(d0),
                D1=_ratio(cell(d1), den), D7=_ratio(cell(d7), den),
                D1_a=_ratio(cell(d1), cell(d0)), D7_a=_ratio(cell(d7), cell(d0)),
                cov=cov, ok=bool(good and cov is not None and cov >= OK_COV))


def versus(a, b):
    """Two reads of the same three days (e.g. Fc vs F) → per day: Σ actives and the X row's actives, a ÷ b."""
    out = {}
    for n in LAGS:
        x, y = a.get("d%d" % n) or {}, b.get("d%d" % n) or {}
        out["d%d" % n] = {"act": _ratio(x.get("act"), y.get("act")),
                          "cell_x": _ratio((x.get("cell_x") or {}).get("act"), (y.get("cell_x") or {}).get("act"))}
    return out


def pack_body(x):
    return {"dateRanges": [dict(gu._rng(x + timedelta(days=n), x + timedelta(days=n)), name="d%d" % n) for n in LAGS],
            "dimensions": ga4._dim("firstSessionDate"), "metrics": ga4._dim(*MIN_METS)}


def measure_p(ga, x, f):
    """X's three days packed into ONE request (3 one-day dateRanges; GA4 adds the dateRange dimension) → per day Σ
    actives and the X row's actives, and each ÷ the single-day F read."""
    rows = ga.report_all(pack_body(x), page_rows=PAGE_ROWS)
    if rows and "dateRange" not in rows[0]:
        return {"err": {"type": "no_dateRange_dimension"}}
    out = dict(_meta(ga), rows=len(rows))
    for n in LAGS:
        rs = [r for r in rows if r.get("dateRange") == "d%d" % n]
        act = sum(r.get("activeUsers") or 0 for r in rs)
        cx = sum(r.get("activeUsers") or 0 for r in rs if str(r.get("firstSessionDate")) == _ymd(x))
        fd = f.get("d%d" % n) or {}
        out["d%d" % n] = {"act": act, "cell_x": cx, "act_vs_F": _ratio(act, fd.get("act")),
                          "cell_x_vs_F": _ratio(cx, (fd.get("cell_x") or {}).get("act"))}
    return out


def cohort_body(x):
    """cohortSpec, as fetch_ret asks it: ONE DAILY cohort (first session on X), days 0..7, no top-level dateRanges."""
    return {"dimensions": ga4._dim("cohort", "cohortNthDay"),
            "metrics": ga4._dim("cohortActiveUsers", "cohortTotalUsers"),
            "cohortSpec": {"cohorts": [{"name": "c" + _ymd(x), "dimension": "firstSessionDate",
                                        "dateRange": gu._rng(x, x)}],
                           "cohortsRange": {"granularity": "DAILY", "startOffset": 0, "endOffset": LAGS[-1]}},
            "limit": 100}


def measure_c(ga, x, ref, f):
    """cohortSpec for X → t (cohortTotalUsers), a[0..7] (cohortActiveUsers), cov = t ÷ newUsers of X (cov_fsd: ÷ the
    X row's actives on X in F), D1 / D7 = a ÷ t (D1_new / D7_new: ÷ newUsers, F's denominator), and the gaps to F:
    dD1 / dD7 (each method's own ratio), dD1_n / dD7_n (both ÷ newUsers)."""
    rows = ga.report(cohort_body(x))
    t, a = 0, {}
    for r in rows:
        try:
            n = int(str(r.get("cohortNthDay")))
        except (TypeError, ValueError):
            continue
        t = max(t, r.get("cohortTotalUsers") or 0)
        a[n] = a.get(n, 0) + (r.get("cohortActiveUsers") or 0)
    act = [a.get(n, 0) for n in range(LAGS[-1] + 1)]
    new = (ref.get(x) or {}).get("newUsers") or 0
    out = dict(_meta(ga), t=t, a=act, empty=not rows, cov=_ratio(t, new), cov_fsd=_ratio(t, (f or {}).get("den_act_fsd")),
               D1=_ratio(act[1], t), D7=_ratio(act[7], t), D1_new=_ratio(act[1], new), D7_new=_ratio(act[7], new))
    out["ok"] = bool(rows) and out["cov"] is not None and out["cov"] >= OK_COV
    for k, n in (("D1", 1), ("D7", 7)):
        fv = (f or {}).get(k)
        if fv is not None and out[k] is not None:
            out["d" + k] = round(abs(fv - out[k]), 4)
        if fv is not None and out[k + "_new"] is not None:
            out["d%s_n" % k] = round(abs(fv - out[k + "_new"]), 4)
    return out


def measure_s(ga, d, ref):
    """The owner's own report of day d (dims [country, firstSessionDate], every row) → the self-check, and each country's
    [activeUsers, newUsers] on the rows of first-session day d (installs) and d−1 (next-day returners)."""
    rows = _mets_report(ga, day_body(d, ("country", "firstSessionDate")))
    out = day_summary(rows, d, d - timedelta(days=1), ref.get(d), ga)
    keep = {_ymd(d): "fsd_D", _ymd(d - timedelta(days=1)): "fsd_D_1"}
    by = {"fsd_D": {}, "fsd_D_1": {}}
    for r in rows:
        k = keep.get(str(r.get("firstSessionDate")))
        if k and ((r.get("activeUsers") or 0) or (r.get("newUsers") or 0)):
            by[k][str(r.get("country"))] = [r.get("activeUsers") or 0, r.get("newUsers") or 0]
    out.update(by)
    return out


def retention(token, pid):
    """The property's data-retention settings (Admin API, read-only)."""
    try:
        j = ga4._call("GET", "%s/properties/%s/dataRetentionSettings" % (ga4.ADMIN, pid), token)
    except Exception as e:
        return {"err": _err(e)}
    return {k: j.get(k) for k in ("eventDataRetention", "userDataRetention", "resetUserDataOnNewActivity")}


# ── one app ─────────────────────────────────────────────────────────────────────────────────────

def phase1(run, app, token, now, prop=None):
    """The app's reference report and its property's retention settings → (result, App, reference). prop: the
    property's shared state (new_prop)."""
    today = ga4.window_end_in(app["tz"], now, lag=0)
    end = ga4.window_end_in(app["tz"], now)
    res = {"app_id": app["app_id"], "property_id": app["property_id"], "stream_id": app["stream_id"],
           "owner": app.get("owner"), "tz": app["tz"], "today": today.isoformat(), "end": end.isoformat(), "xs": {}}
    if not token:
        res["err"] = {"type": "auth"}
        return res, None, None
    ga = App(token, app["property_id"], app["stream_id"], run, prop)
    why = ga.stop or run.over()
    if why:                                          # the run's budget, or this property already stopped
        res["stopped"] = why
        return res, ga, None
    run.tick()
    res["retention"] = retention(token, app["property_id"])
    start = today - timedelta(days=REF_DAYS)
    ga.kind = "ref"
    try:
        ref = ref_report(ga, start, end)
    except Stop as e:
        res["stopped"] = str(e)
        return res, ga, None
    except Exception as e:
        res["err"] = _err(e)
        return res, ga, None
    active = sorted(d for d, v in ref.items() if v["activeUsers"] or v["newUsers"])
    res["first_day"] = active[0].isoformat() if active else None
    res["ref_capped"] = bool(active) and active[0] <= start
    last = [ref.get(end - timedelta(days=i), {}).get("activeUsers", 0) for i in range(28)]
    res["dau28"] = round(sum(last) / 28.0, 1)
    if active:
        # the reference itself, day by day (the denominators' own evidence: a cliff in actives per event at the old
        # retention edge, ~60 days back, would mean the date-level user counts are retention-limited too)
        span = [active[0] + timedelta(days=i) for i in range((end - active[0]).days + 1)]
        res["ref_series"] = {"from": active[0].isoformat(),
                             **{k: [(ref.get(d) or {}).get(m, 0) for d in span]
                                for k, m in (("act", "activeUsers"), ("new", "newUsers"), ("ev", "eventCount"))}}
        res["ref_ape28"] = _median([_ape(ref.get(end - timedelta(days=i))) for i in range(28)])
    return res, ga, ref


def _ape(v):
    """A day's reference → active users per event (None without events)."""
    v = v or {}
    return v.get("activeUsers", 0) / v["eventCount"] if v.get("eventCount") else None


def phase2(ga, res, ref, country):
    """Every measurement of one app, into res (in place). country: this app is one of Fc's three."""
    if ga is None or ref is None or not res.get("first_day"):
        return
    today, end = date.fromisoformat(res["today"]), date.fromisoformat(res["end"])
    days = pick_days(today, end, date.fromisoformat(res["first_day"]))
    fcs = fc_ages([a for a, _ in days]) if country else []
    res["fc_ages"] = fcs
    try:
        s = res.setdefault("S", {})
        for iso in EXPORT_DAYS:
            d = date.fromisoformat(iso)
            if d <= end and d - timedelta(days=1) >= date.fromisoformat(res["first_day"]):
                s[iso] = _guard(ga, "S", lambda d=d: measure_s(ga, d, ref))
        for age, x in days:
            rec = res["xs"][str(age)] = {"x": x.isoformat(), "age": age,
                                         "ref": {"d%d" % n: [(ref.get(x + timedelta(days=n)) or {}).get(m, 0)
                                                             for m in ("activeUsers", "newUsers")] for n in LAGS}}
            # X's actives per event ÷ the last 28 days' (≈ 1 when the reference kept X's users; ≪ 1 if it did not)
            rec["ref_ape_rel"] = _ratio(_ape(ref.get(x)), res.get("ref_ape28"))
            rec["F"] = measure_f(ga, x, ref)
            rec["C"] = _guard(ga, "C", lambda: measure_c(ga, x, ref, rec["F"]))
            if age in fcs:
                rec["Fc"] = measure_f(ga, x, ref, "Fc", ("country", "firstSessionDate"))
                rec["Fc"]["vs_F"] = versus(rec["Fc"], rec["F"])
            if country:
                rec["P"] = _guard(ga, "P", lambda: measure_p(ga, x, rec["F"]))
    except Stop as e:
        res["stopped"] = str(e)


def _finish(ga, res):
    if ga is not None:
        res.update(calls=ga.by_kind, tokens=ga.tok, quota=ga.quota, server_errors=ga.server_errors,
                   min_mets=ga.min_mets)
        if ga.stop and "stopped" not in res:
            res["stopped"] = ga.stop


# ── the summary ─────────────────────────────────────────────────────────────────────────────────

def _days3(f):
    return [f.get("d%d" % n) or {} for n in LAGS]


def summary(apps):
    """Per method × age: how many (app, X) were asked / measured, median coverage, how many at ≥ OK_COV, and the
    gaps between the methods (median |D1_F − D1_C|, |D7_F − D7_C|)."""
    out = {}
    for age in sorted(AGES):
        recs = [a["xs"][str(age)] for a in apps.values() if str(age) in (a.get("xs") or {})]
        fs = [r["F"] for r in recs if r.get("F")]
        fm = [f for f in fs if f.get("cov") is not None]
        cs = [r["C"] for r in recs if isinstance(r.get("C"), dict)]
        cm = [c for c in cs if "err" not in c]
        fcs = [r["Fc"] for r in recs if r.get("Fc")]
        ps = [r["P"] for r in recs if isinstance(r.get("P"), dict) and "err" not in r["P"]]
        row = {"F": {"asked": len(fs), "measured": len(fm),
                     "cov_median": _median([f["cov"] for f in fm]), "cov_min": min([f["cov"] for f in fm], default=None),
                     "ok": sum(1 for f in fm if f["ok"]),
                     "cov_total_median": _median([d.get("cov_total") for f in fm for d in _days3(f)]),
                     "ev_cov_median": _median([d.get("ev_cov") for f in fm for d in _days3(f)]),
                     "ref_ape_rel_median": _median([r.get("ref_ape_rel") for r in recs]),
                     "new_cov_median": _median([_days3(f)[0].get("new_cov") for f in fm]),
                     "old_share_median": _median([d.get("old_share") for f in fm for d in _days3(f)]),
                     "D1_median": _median([f.get("D1") for f in fm]), "D7_median": _median([f.get("D7") for f in fm]),
                     "with_other": sum(1 for f in fs if any((d.get("other") or {}).get("rows") for d in _days3(f))),
                     "thresholded": sum(1 for f in fs if any(d.get("thresh") for d in _days3(f))),
                     "empty_day": sum(1 for f in fs if any(d.get("empty") for d in _days3(f))),
                     "errors": sum(1 for f in fs if any("err" in d for d in _days3(f))),
                     "tokens_per_call_median": _median([d.get("tok") for f in fs for d in _days3(f) if "tok" in d])},
               "C": {"asked": len(cs), "measured": len(cm), "empty": sum(1 for c in cm if c.get("empty")),
                     "cov_median": _median([c.get("cov") for c in cm]),
                     "cov_fsd_median": _median([c.get("cov_fsd") for c in cm]),
                     "ok": sum(1 for c in cm if c.get("ok")), "errors": len(cs) - len(cm),
                     "dD1_median": _median([c.get("dD1") for c in cm]), "dD7_median": _median([c.get("dD7") for c in cm]),
                     "dD1_n_median": _median([c.get("dD1_n") for c in cm]),
                     "dD7_n_median": _median([c.get("dD7_n") for c in cm]),
                     "tokens_per_call_median": _median([c.get("tok") for c in cs])}}
        if fcs:
            vs = [v for f in fcs for v in (f.get("vs_F") or {}).values()]
            row["Fc"] = {"measured": sum(1 for f in fcs if f.get("cov") is not None),
                         "act_vs_F_median": _median([v.get("act") for v in vs]),
                         "cell_x_vs_F_median": _median([v.get("cell_x") for v in vs]),
                         "cell_x_within_2pct": sum(1 for f in fcs if all(
                             v.get("cell_x") is not None and abs(v["cell_x"] - 1) <= 0.02
                             for v in (f.get("vs_F") or {}).values()) and f.get("vs_F")),
                         "tokens_per_call_median": _median([d.get("tok") for f in fcs for d in _days3(f)])}
        if ps:
            dev = [abs(p["d%d" % n]["act_vs_F"] - 1) for p in ps for n in LAGS if p["d%d" % n].get("act_vs_F") is not None]
            row["P"] = {"measured": len(ps), "act_vs_F_abs_dev_median": _median(dev),
                        "within_1pct": sum(1 for p in ps if all(p["d%d" % n].get("cell_x_vs_F") is not None and
                                                              abs(p["d%d" % n]["cell_x_vs_F"] - 1) <= 0.01 for n in LAGS)),
                        "tokens_per_call_median": _median([p.get("tok") for p in ps])}
        out[str(age)] = row
    return out


def counts(apps, run):
    """The public counts (no ids, names or user numbers)."""
    recs = [r for a in apps.values() for r in (a.get("xs") or {}).values()]
    stopped = [a.get("stopped") for a in apps.values() if a.get("stopped")]
    errs = sum(1 for a in apps.values() if a.get("err") or a.get("crash"))
    errs += sum(1 for r in recs for d in _days3(r.get("F") or {}) if "err" in d)
    errs += sum(1 for r in recs if "err" in (r.get("C") or {}))
    return {"apps": len(apps), "apps_measured": sum(1 for a in apps.values() if a.get("xs")),
            "days": len(recs), "calls": run.calls,
            "f_ok": sum(1 for r in recs if (r.get("F") or {}).get("ok")), "f_of": sum(1 for r in recs if r.get("F")),
            "c_ok": sum(1 for r in recs if (r.get("C") or {}).get("ok")), "c_of": sum(1 for r in recs if "C" in r),
            "quota_low": sum(1 for s in stopped if s.startswith("quota")),
            "stopped_other": sum(1 for s in stopped if not s.startswith("quota")),
            "errors": errs, "seconds": run.elapsed(),
            "tokens": sum(_int(a.get("tokens")) for a in apps.values()),
            "tokens_max_property": max([_int(a.get("tokens")) for a in apps.values()], default=0)}


COUNT_KEYS = ("apps_measured", "apps", "days", "calls", "f_ok", "f_of", "c_ok", "c_of", "quota_low", "stopped_other",
              "errors", "seconds")


def public_line(c):
    return ("d1d7 probe: apps %d/%d, days %d, calls %d, F ok %d/%d, C ok %d/%d, quota low %d, stopped %d, "
            "errors %d, %ds" % tuple(_int((c or {}).get(k)) for k in COUNT_KEYS))


def _safely(fn, *args, fallback=None):
    """fn(*args), or — on a bug in the bookkeeping — `fallback` plus the exception's class: the GA4 calls are already
    spent, so the raw results must still be written."""
    try:
        return fn(*args)
    except Exception as e:
        out = dict(fallback or {})
        out["err"] = {"type": type(e).__name__}
        return out


def _dump(report):
    try:
        return json.dumps(report, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):                  # e.g. keys of mixed types: unsorted, but written
        return json.dumps(report, separators=(",", ":"), default=str)


def write_private(path, text, message, tries=WRITE_TRIES):
    """text → `path` in the PRIVATE repo (GitHub contents API; DATA_REPO / DATA_REPO_TOKEN) → True when written. The
    file's current sha comes from its folder's listing, which — unlike a GET of the file itself with the default media
    type — also works once the file is over 1 MB (a re-run replaces it). A race with another commit (409 / 422) is
    retried on the new sha; there is no force of any kind. Nothing is printed."""
    repo, tok = os.environ["DATA_REPO"], os.environ["DATA_REPO_TOKEN"]
    api = "https://api.github.com/repos/%s/contents/" % repo
    h = {"Authorization": "token " + tok, "Accept": "application/vnd.github+json", "User-Agent": "admob-iq-d1d7-probe"}
    content = base64.b64encode(text.encode("utf-8")).decode()
    folder = path.rsplit("/", 1)[0]
    for i in range(tries):
        if i:
            ga4._sleep(5.0 * i)
        try:
            ls = requests.get(api + folder, headers=h, timeout=30)
            if ls.status_code not in (200, 404):
                continue
            body = {"message": message, "content": content}
            listing = ls.json() if ls.status_code == 200 else []
            sha = next((e.get("sha") for e in listing if isinstance(e, dict) and e.get("path") == path), None) \
                if isinstance(listing, list) else None
            if sha:
                body["sha"] = sha
            r = requests.put(api + path, headers=h, data=json.dumps(body), timeout=120)
            if r.status_code in (200, 201):
                return True
        except (requests.RequestException, ValueError):
            pass
    return False


# ── the run ─────────────────────────────────────────────────────────────────────────────────────

def _groups(apps):
    """Apps grouped by property: one worker per group, so a property never has two requests in flight."""
    by = {}
    for a in apps:
        by.setdefault(a["property_id"], []).append(a)
    return [by[k] for k in sorted(by)]


def run_probe(apps, cid, sec, tokens, now=None, budget=BUDGET_SEC, clock=time.monotonic, workers=WORKERS):
    """Probe every app → the report (dict). Never raises for one app's failure; prints counts-only progress."""
    run = Run(budget, clock)
    now = now or datetime.now(timezone.utc)
    rt, access = dict(tokens), {}
    for owner in sorted({a.get("owner") or "" for a in apps}):
        try:
            access[owner] = ga4.access_token(cid, sec, rt[owner]) if owner in rt else None
        except Exception:
            access[owner] = None
    out, held = {}, {}
    props = {a["property_id"]: new_prop() for a in apps}     # quota / 5xx / stop are per property

    def one(group, fn):
        for a in group:
            try:
                fn(a)
            except Exception as e:                   # a bug for one app must not cost the others
                out.setdefault(a["package"], {})["crash"] = type(e).__name__

    def p1(a):
        res, ga, ref = phase1(run, a, access.get(a.get("owner") or ""), now, props[a["property_id"]])
        out[a["package"]], held[a["package"]] = res, (ga, ref)

    groups = _groups(apps)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(lambda g: one(g, p1), groups))
    run.say("d1d7 progress: references %d/%d, calls %d, %ds"
            % (sum(1 for r in out.values() if r.get("first_day")), len(apps), run.calls, run.elapsed()))
    country = _safely(pick_country_apps, {p: r for p, r in out.items() if not r.get("crash")})
    country = country if isinstance(country, list) else []
    done = [0]

    def p2(a):
        res = out[a["package"]]
        ga, ref = held.get(a["package"]) or (None, None)
        try:
            phase2(ga, res, ref, a["package"] in country)
        finally:
            _finish(ga, res)
            held.pop(a["package"], None)             # free the reference
            with run.lock:
                done[0] += 1
                n = done[0]
            run.say("d1d7 progress: apps %d/%d, calls %d, %ds" % (n, len(apps), run.calls, run.elapsed()))

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(lambda g: one(g, p2), groups))
    c = _safely(counts, out, run, fallback={"apps": len(apps), "calls": run.calls, "seconds": run.elapsed()})
    return {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ages": sorted(AGES), "lags": list(LAGS),
            "ok_cov": OK_COV, "old_days": OLD_DAYS, "export_days": list(EXPORT_DAYS), "country_apps": country,
            "quota_frac": QUOTA_FRAC, "counts": c, "summary": _safely(summary, out), "apps": out}


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    apps = apps_from_state(_private_json(STATE_PATH))
    cap = _int(env.get("PROBE_MAX_APPS"))
    if cap > 0:
        apps = apps[:cap]
    if not apps:
        sys.exit("no GA4 app routes in the private state")
    budget = _int(env.get("PROBE_BUDGET_SEC")) or BUDGET_SEC
    print("d1d7 probe: %d app(s) to probe" % len(apps), flush=True)
    report = run_probe(apps, cid, sec, tokens, now=now, budget=budget, clock=clock)
    print(public_line(report["counts"]), flush=True)
    if not write_private(OUT_PATH, _dump(report), "ga4 d1d7 probe"):
        sys.exit("private repo write failed")            # stderr: hidden by the workflow step
    print("d1d7 probe: report written", flush=True)


if __name__ == "__main__":
    main()
