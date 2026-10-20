"""📈 Day-wise ROI — the hourly fetch (owner, 13 Oct 2026: "every date wise uska incremental day wise revenue from first
day of the app … delta, breakeven, % wise", every feature on the FULL history).

The Install value tab's install-day file (fetch.ga4_uninstall, iday) keeps an install day's ad revenue in lag BANDS
(0, 1, 2–3, 4–7, 8–14, 15–30, …); this store keeps EVERY day of an install day's first 31 days (lag 0 … 30), so the
page can show D0, D1, D2 … D30 one by one. Beyond day 30 the page uses the iday bands (60 / 90 / 180 / 365).

GA4 runReport (v1beta, Android + the app's stream), USD:
    dimensions [date, firstSessionDate], metrics [activeUsers, totalAdRevenue]
    over a block of ACTIVITY days [a, b], firstSessionDate in-list [a − 30 … b] (GA4 refuses a numeric between)
→ cell (install day X = firstSessionDate, lag L = date − X), 0 ≤ L ≤ 30: users active on day L, ad revenue on day L.
A block holds at most BLOCK × (BLOCK + 30) rows — one page. Like the iday Q-C, the in-list hides GA4's "(other)" row
rather than avoiding it; the build ties every activity day back to the iday Q-B read (roi_build) and marks a day that
does not tie.

Per app and run (at most MAX_CALLS calls; the property's quota floors, the run's budget):
  * a one-time backfill from the GA4 history start, BLOCK activity days a call, resumable (backfill.next);
  * every REFRESH_HOURS the last RECENT_DAYS activity days again (today included: not final, the page marks it).
Stored for good in the private repo, two files so the hourly commits stay small:
    data/ga4_cohort/<key>.json.gz      the hot part: install days from the month of (today − HOT_DAYS) on
    data/ga4_cohort/<key>.old.json.gz  the older install days (rewritten only when the split moves a month, or by the
                                       backfill)
    {"v", "app_id", "package", "property_id", "stream_id", "time_zone", "hs", "read_today", "recent_at",
     "backfill": {"from", "next", "done"}, "cut", "x": {X: {"r": [31 USD micros], "u": [31 users]}}}
Switched by GA4_COHORT (on by default in the workflow). Never raises; never prints (log_line: counts only).

LATE read (owner, 20 Oct 2026: "jitna purana app utna date" — the page's install-day table goes on past D30 in 30-day
columns up to the app's age; GA4_COHORT_LATE, its own switch; off = nothing of it read, written or printed, and every
file above exactly as without it):
    dimensions [date, firstSessionDate], metric totalAdRevenue (USD), a block of ACTIVITY days [a, b], NO in-list
    (every install day is active on them), every page (report_all, UNI_PAGE_ROWS a page: never cut)
→ only rows with lag L = date − firstSessionDate ≥ LAGS (31) and an install day ≥ the history start are folded; a row
whose firstSessionDate is not a real date (GA4's "(other)" / "(not set)") is folded into nobody, its revenue summed per
activity day as "oth" (the build marks ≈ and says how much); "t" = the activity day's revenue over EVERY row of the
read (the share's denominator). With no in-list GA4 may also drop rows WITHOUT an "(other)" row: a block whose response
(any page) says dataLossFromOtherRow, subjectToThresholding or sampling, or whose rows were cut (truncated), marks
every day of it in "loss" (the build marks ≈ and counts them; the block is not re-read in slices). Activity days
before history start + 31 hold nothing to fold: never read.
Stored by ACTIVITY month, so an old month's file never changes:
    data/ga4_cohort/late/<key>/<YYYY-MM>.json.gz = {"v": 1, "stream_id", "d": {D: {X: micros}}, "oth": {D: micros},
                                                    "t": {D: micros}, "loss": {D: 1}}
— a day present in "d" was read (an empty {} = read, nothing past day 30 that day); a re-read of days a … b REPLACES
them entirely; only the months a read touched are written (write_json_gz_stable; a month the reads moved past is
written and let go at once). Progress in the main store: "late": {"from", "next", "done", "read_till"} with ONE
cursor, next: every activity day before it was read when already final (≥ FINAL_LAG days old). A run reads from
min(next, today − RECENT_DAYS + 1) to today, BLOCK_LATE activity days a call, the cursor moving after each block (never
past today − FINAL_LAG + 1, so a day read while still filling is read again) — so the first read (the backfill from
history start + 31), a catch-up after any pause (the switch off, failed runs, a Stop, a quota-deferred day) and the
6-hourly recent refresh are the same read and no activity day is ever skipped. It runs when the cursor is older than the
recent window, when the recent refresh ran, or when the late part of the last one did not reach its day (read_till <
read_today); "done" once a read reached today (the build shows the 30-day columns only from then on), read_till = the
newest today a read reached. Same property quota gate, budget and MAX_CALLS as above, after the lag 0 … 30 reads (a
Stop keeps what was read and the cursor where it stopped).
Cost: the first read ≈ (app age − 31) / 30 calls ONCE per app (an app 900 days old: ~29 calls, over 1–2 runs next to
the lag 0 … 30 backfill's cap), then 2 calls per recent refresh (35 days in blocks of 30; every 6 hours → ~8 a day per
app), a pause of N days ≈ N / 30 + 2 calls once; rows a call ≈ 30 × the install days that earned that day (≤ 30 × app
age; one 100,000-row page up to ~3,300 install days).
"""
import json
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import ga4_probe
from ..db import write_json_gz_stable
from . import ga4
from . import ga4_audience as gaud
from . import ga4_uninstall as gu
from .ga4_firstopen import App, Stop

DIR = "ga4_cohort"
STORE_V = 1
LAGS = 31                           # lag 0 … 30
BLOCK = 30                          # activity days a call (in-list ≤ 60 install days, ≤ 1,800 rows)
RECENT_DAYS = 35                    # refreshed every REFRESH_HOURS (today … 34 days back)
REFRESH_HOURS = 6.0
FINAL_LAG = 3                       # an activity day is final once ≤ the property's today − 3 (as the iday reads)
HOT_DAYS = 45                       # the hot file: install days from the month of (today − 45) on
MAX_CALLS = 60                      # per app per run (the backfill goes on next run)
BUDGET_SEC = 150
RETRY_HOURS = 3.0
METS = ("activeUsers", "totalAdRevenue")
LATE_DIR = "late"                   # data/ga4_cohort/late/<key>/<YYYY-MM>.json.gz (by activity month)
LATE_V = 1
BLOCK_LATE = 30                     # activity days a late call (no in-list: rows ≈ 30 × install days)


def _d(s):
    return date.fromisoformat(s)


def _ymd(d):
    return d.strftime("%Y%m%d")


def _iso8(s):
    s = str(s or "")
    return "%s-%s-%s" % (s[:4], s[4:6], s[6:]) if len(s) == 8 and s.isdigit() else None


def body(a, b):
    """The block [a, b]: every install day a − 30 … b at every activity day of the block."""
    return {"dateRanges": [{"startDate": a.isoformat(), "endDate": b.isoformat()}],
            "dimensions": ga4._dim("date", "firstSessionDate"), "metrics": ga4._dim(*METS),
            "currencyCode": "USD", "keepEmptyRows": False}


def in_list(a, b):
    n = (b - a).days + LAGS
    return [_ymd(b - timedelta(days=i)) for i in range(n)]


def read_block(ga, a, b):
    """One block → {X: {L: [users, micros]}} for every row with 0 ≤ L ≤ 30 (and the X's GA4 answered)."""
    rows = ga.report_all(body(a, b), extra=[ga4._in_list("firstSessionDate", in_list(a, b))],
                         page_rows=gu.UNI_PAGE_ROWS)
    out = {}
    for r in rows:
        D, X = _iso8(r.get("date")), _iso8(r.get("firstSessionDate"))
        if not D or not X:
            continue
        L = (_d(D) - _d(X)).days
        if 0 <= L < LAGS:
            out.setdefault(X, {})[L] = [int(r.get("activeUsers") or 0), int(round(float(r.get("totalAdRevenue") or 0) * 1e6))]
    return out


def merge(store, got, a, b):
    """Cells of activity days a … b: set from the read; a cell the read did not return is 0 (nobody / no revenue)."""
    x = store.setdefault("x", {})
    X = a - timedelta(days=LAGS - 1)
    while X <= b:
        k = X.isoformat()
        g = got.get(k) or {}
        e = x.get(k)
        for L in range(LAGS):
            D = X + timedelta(days=L)
            if D < a or D > b:
                continue
            v = g.get(L)
            if e is None and not v:
                continue
            if e is None:
                e = x[k] = {"r": [0] * LAGS, "u": [0] * LAGS}
            e["u"][L], e["r"][L] = (v or [0, 0])
        X += timedelta(days=1)


def _blocks(start, end, n=BLOCK):
    out, a = [], start
    while a <= end:
        b = min(end, a + timedelta(days=n - 1))
        out.append((a, b))
        a = b + timedelta(days=1)
    return out


def step_app(ga, store, today, hs, now, late=None):
    """One app's run on its store → "fetched" or "fresh". Raises Stop (what was read is kept). late: the app's Late
    store (GA4_COHORT_LATE on) — its reads come after the lag 0 … 30 ones; None = none of it."""
    did, now_iso = False, gu._now_iso(now)
    recent = today - timedelta(days=RECENT_DAYS - 1)
    bf = store.setdefault("backfill", {})
    if not bf.get("done"):
        nxt = _d(bf["next"]) if bf.get("next") else hs
        bf.setdefault("from", nxt.isoformat())
        for a, b in _blocks(nxt, recent - timedelta(days=1)):
            merge(store, read_block(ga, a, b), a, b)
            bf["next"] = (b + timedelta(days=1)).isoformat()
            did = True
        bf["done"] = True
    ran = False
    if gu._hours_since(store.get("recent_at"), now) >= REFRESH_HOURS:
        a = max(hs, recent)
        merge(store, read_block(ga, a, today), a, today)
        store["recent_at"], store["read_today"] = now_iso, today.isoformat()
        did = ran = True
    if late is not None and step_late(ga, store, late, today, hs, ran):
        did = True
    return "fetched" if did else "fresh"


# ── the LATE read: every install day's ad revenue past day 30 (see the module doc) ───────────────────────────────────
def body_late(a, b):
    """The late block [a, b]: every install day at every activity day of the block (no in-list)."""
    return {"dateRanges": [{"startDate": a.isoformat(), "endDate": b.isoformat()}],
            "dimensions": ga4._dim("date", "firstSessionDate"), "metrics": ga4._dim("totalAdRevenue"),
            "currencyCode": "USD", "keepEmptyRows": False}


def _real(s):
    """GA4's YYYYMMDD → YYYY-MM-DD when it is a real date ("(other)", "(not set)", junk → None)."""
    k = _iso8(s)
    try:
        return _d(k).isoformat() if k else None
    except ValueError:
        return None


def _lossy(ga, rows):
    """The last report_all lost rows WITHOUT an "(other)" row to show it: any page with dataLossFromOtherRow,
    thresholding or sampling, or the read cut (truncated)."""
    metas = getattr(ga, "last_metas", None) or [getattr(ga, "last_meta", None) or {}]
    for m in metas:
        if isinstance(m, dict) and (m.get("dataLossFromOtherRow") or m.get("subjectToThresholding")
                                    or m.get("samplingMetadatas")):
            return True
    return bool(ga.truncated(rows)) if hasattr(ga, "truncated") else False


def read_late(ga, a, b, hs):
    """One late block → {"d": {D: {X: micros}} (lag ≥ LAGS, X ≥ hs, revenue > 0), "oth": {D: micros} (no real install
    day), "t": {D: micros} (every row of the day), "loss": the block's response said rows were dropped (_lossy)}."""
    rows = ga.report_all(body_late(a, b), page_rows=gu.UNI_PAGE_ROWS)
    d, oth, tot, h = {}, {}, {}, hs.isoformat()
    for r in rows:
        D = _real(r.get("date"))
        if not D:
            continue
        v = int(round(float(r.get("totalAdRevenue") or 0) * 1e6))
        tot[D] = tot.get(D, 0) + v
        X = _real(r.get("firstSessionDate"))
        if X is None:
            oth[D] = oth.get(D, 0) + v
            continue
        if X >= h and v and (_d(D) - _d(X)).days >= LAGS:
            e = d.setdefault(D, {})
            e[X] = e.get(X, 0) + v
    return {"d": d, "oth": oth, "t": tot, "loss": _lossy(ga, rows)}


def late_path(data_dir, app_id, month):
    return os.path.join(data_dir, DIR, LATE_DIR, gu.file_key(app_id), month + ".json.gz")


def late_months(data_dir, app_id, stream_id):
    """The app's late month files of THIS stream, oldest first → [(YYYY-MM, {"d", "oth", "t"})] — one at a time
    (a generator: the build folds a month and lets it go)."""
    folder = os.path.join(data_dir, DIR, LATE_DIR, gu.file_key(app_id))
    try:
        names = sorted(f for f in os.listdir(folder) if len(f) == 15 and f.endswith(".json.gz"))
    except OSError:
        return
    for f in names:
        s = gu.load_store(os.path.join(folder, f))
        if isinstance(s, dict) and s.get("v") == LATE_V and str(s.get("stream_id") or "") == str(stream_id or "") \
                and isinstance(s.get("d"), dict):
            yield f[:7], s


class Late:
    """One app's late store in a run: month files loaded on first use, the months a read touched (only those are
    written), counts for the log line."""

    def __init__(self, data_dir=None, app_id=None, stream_id=None):
        self.data_dir, self.app_id, self.stream_id = data_dir, app_id, stream_id
        self.m, self.touched, self.calls, self.days = {}, set(), 0, 0

    def month(self, k):
        if k not in self.m:
            s = gu.load_store(late_path(self.data_dir, self.app_id, k)) if self.data_dir else None
            if not (isinstance(s, dict) and s.get("v") == LATE_V and isinstance(s.get("d"), dict)
                    and str(s.get("stream_id") or "") == str(self.stream_id or "")):
                s = {"v": LATE_V, "stream_id": self.stream_id, "d": {}, "oth": {}, "t": {}, "loss": {}}
            for f in ("oth", "t", "loss"):
                s.setdefault(f, {})
            self.m[k] = s
        return self.m[k]

    def put(self, got, a, b):
        """Activity days a … b REPLACED by the read (a day it returned nothing for: read, nothing to fold; a lossy
        block: every day of it in "loss")."""
        D = a
        while D <= b:
            k = D.isoformat()
            f = self.month(k[:7])
            f["d"][k] = dict(got["d"].get(k) or {})
            for fld in ("oth", "t"):
                v = (got.get(fld) or {}).get(k)
                if v:
                    f[fld][k] = v
                else:
                    f[fld].pop(k, None)
            if got.get("loss"):
                f["loss"][k] = 1
            else:
                f["loss"].pop(k, None)
            self.touched.add(k[:7])
            self.days += 1
            D += timedelta(days=1)
        self.calls += 1
        if self.data_dir:                           # the reads go forward: a month before b's is done — written and let
            self.save(before=b.isoformat()[:7])     # go, so a long backfill never holds every month in memory

    def save(self, before=None):
        for k in sorted(self.touched):
            if before and k >= before:
                continue
            p = late_path(self.data_dir, self.app_id, k)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            write_json_gz_stable(p, self.m[k])
            self.touched.discard(k)
            if before:
                self.m.pop(k, None)


def step_late(ga, store, late, today, hs, ran):
    """The late reads of one app (after the lag 0 … 30 ones), from the cursor late.next (see the module doc): from
    min(next, the recent window's first day) to today in BLOCK_LATE blocks — whenever the cursor is older than the
    recent window (the first read, a catch-up after any pause), the recent refresh ran (`ran`), or the late part of the
    last one did not reach its day. → read anything?"""
    first = hs + timedelta(days=LAGS)               # the first activity day that can hold a lag ≥ 31 row
    recent = today - timedelta(days=RECENT_DAYS - 1)
    edge = today - timedelta(days=FINAL_LAG)        # the newest activity day a read today gets final
    lt = store.setdefault("late", {})
    nxt = max(first, _d(lt["next"])) if lt.get("next") else first
    if not (nxt < recent or ran or (lt.get("read_till") or "") < (store.get("read_today") or "")):
        return False
    lt.setdefault("from", first.isoformat())
    did = False
    for a, b in _blocks(min(nxt, max(first, recent)), today, BLOCK_LATE):
        late.put(read_late(ga, a, b, hs), a, b)
        nxt = max(nxt, min(b, edge) + timedelta(days=1))
        lt["next"] = nxt.isoformat()
        did = True
    lt["done"], lt["read_till"] = True, today.isoformat()
    return did


# ── store and state ─────────────────────────────────────────────────────────────────────────────────────────────────
def store_path(data_dir, app_id, old=False):
    return os.path.join(data_dir, DIR, gu.file_key(app_id) + (".old.json.gz" if old else ".json.gz"))


def load_store(data_dir, app_id):
    """The hot part with the older install days put back (a part of another format / stream: the whole store again)."""
    s = gu.load_store(store_path(data_dir, app_id))
    if not isinstance(s, dict) or s.get("v") != STORE_V:
        return None
    o = gu.load_store(store_path(data_dir, app_id, old=True))
    if isinstance(o, dict) and o.get("v") == STORE_V and o.get("stream_id") == s.get("stream_id"):
        s["x"] = dict(o.get("x") or {}, **(s.get("x") or {}))
    s.pop("cut", None)
    return s


def save_store(data_dir, app_id, store, today):
    """Hot part (install days from the month of today − HOT_DAYS) and the older part; the older file is written only
    when its content changed (write_json_gz_stable keeps an unchanged file as it is)."""
    cut = (today - timedelta(days=HOT_DAYS)).replace(day=1).isoformat()
    x = store.get("x") or {}
    hot = {k: v for k, v in x.items() if k >= cut}
    old = {k: v for k, v in x.items() if k < cut}
    os.makedirs(os.path.join(data_dir, DIR), exist_ok=True)
    head = {k: v for k, v in store.items() if k != "x"}
    write_json_gz_stable(store_path(data_dir, app_id), dict(head, x=hot, cut=cut))
    if old:
        write_json_gz_stable(store_path(data_dir, app_id, old=True),
                             {"v": STORE_V, "stream_id": store.get("stream_id"), "x": old})


def load_state(data_dir):
    try:
        with open(os.path.join(data_dir, DIR, "state.json"), encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict) and isinstance(raw.get("fetch"), dict):
            return raw
    except (OSError, ValueError):
        pass
    return {"v": 1, "fetch": {}}


def save_state(data_dir, state):
    path = os.path.join(data_dir, DIR, "state.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=1)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return True


COUNTS = ("selected", "with_ga4", "fetched", "fresh", "failed", "deferred", "waiting", "calls", "tokens")


def refresh_all(cfg, data_dir, apps, now=None, clock=None, budget=BUDGET_SEC, late=False):
    """Every selected app (uninstall_build's list) → {"counts", "apps": {app id: fetched|fresh|failed|deferred|
    waiting}} (+ "late": {"apps", "calls", "days"} when `late`, GA4_COHORT_LATE: the late reads too). Never raises;
    never prints."""
    import time
    clock = clock or time.monotonic
    now = now or datetime.now(timezone.utc)
    t0 = clock()
    counts = dict.fromkeys(COUNTS, 0)
    out = {"counts": counts, "apps": {}}
    if late:
        out["late"] = {"apps": 0, "calls": 0, "days": 0}
    try:
        state = load_state(data_dir)
        ust = gu.load_state(data_dir)
        routes = ust["routes"].get("by_package") or {}
        tokens, _ = ga4_probe.owner_tokens({"GA4_REFRESH_TOKENS": cfg.get("refresh_tokens") or "",
                                            "GA4_REFRESH_TOKEN": cfg.get("refresh_token") or ""})
        owner_rt, access, props = dict(tokens), {}, {}
        now_iso = gu._now_iso(now)

        def over():
            return "budget" if clock() - t0 >= budget else None
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
            um = gaud._uni_meta(ust, data_dir, aid, r)
            if not um:
                out["apps"][aid] = "waiting"
                continue
            st = state["fetch"].setdefault(aid, {})
            if st.get("fail") and gu._hours_since(st.get("last_try"), now) < RETRY_HOURS:
                out["apps"][aid] = "failed"
                continue
            todo.append((a, st, r, gu._d(um["history_start"])))
        todo.sort(key=lambda t: (not t[1].get("deferred"), t[1].get("last_ok") or "", t[0]["app_id"]))
        for a, st, r, hs in todo:
            aid, pid = a["app_id"], r["property_id"]
            prop = props.setdefault(pid, {"quota": None, "stop": None})
            if over() or prop["stop"]:
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
            if not access.get(owner):
                st.update(last_try=now_iso, fail="auth")
                out["apps"][aid] = "failed"
                continue
            tz = ust["tz"].get(pid) or "UTC"
            today = now.astimezone(ZoneInfo(tz)).date()
            store = load_store(data_dir, aid)
            if store is None or store.get("stream_id") != r["stream_id"]:
                store = {"v": STORE_V}
            ga = App(access[owner], pid, r["stream_id"], prop, over=over, max_calls=MAX_CALLS)
            lt = Late(data_dir, aid, r["stream_id"]) if late else None
            try:
                res = step_app(ga, store, today, hs, now, lt)
                st.pop("deferred", None)
                st.update(last_try=now_iso, fail=None)
                if res == "fetched":
                    st["last_ok"] = now_iso
                out["apps"][aid] = res
            except Stop:
                st["deferred"] = True
                out["apps"][aid] = "deferred"
            except Exception as e:
                st.update(last_try=now_iso, fail=gu._fail_kind(e))
                out["apps"][aid] = "failed"
            finally:
                if lt is not None and lt.touched:       # the months first: the progress never runs ahead of them
                    lt.save()
                if lt is not None and lt.calls:
                    out["late"]["apps"] += 1
                    out["late"]["calls"] += lt.calls
                    out["late"]["days"] += lt.days
                if ga.calls:
                    store.update(v=STORE_V, app_id=aid, package=a["package"], property_id=pid,
                                 stream_id=r["stream_id"], time_zone=tz, hs=hs.isoformat())
                    save_store(data_dir, aid, store, today)
                st["key"] = gu.file_key(aid)
                counts["calls"] += ga.calls
                counts["tokens"] += ga.tok
        save_state(data_dir, state)
    except Exception as e:                              # a bug here must never cost the build
        out["error"] = type(e).__name__
    for v in out["apps"].values():
        if v in counts:
            counts[v] += 1
    return out


def log_line(status):
    """The build log's ONE line for this step — counts only (the late reads' counts only when they are on)."""
    c = (status or {}).get("counts") or {}
    lt = (status or {}).get("late")
    return ("ga4 cohort: apps %d, with GA4 %d, fetched %d, fresh %d, failed %d, deferred %d, waiting %d, calls %d, "
            "tokens %d%s%s" % tuple([gaud._int(c.get(k)) for k in COUNTS]
                                    + [("; late: apps %d, calls %d, days %d" % tuple(gaud._int(lt.get(k)) for k in
                                                                                     ("apps", "calls", "days")))
                                       if isinstance(lt, dict) else "",
                                       (", error " + status["error"]) if (status or {}).get("error") else ""]))
