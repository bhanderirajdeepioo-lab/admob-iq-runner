"""📱 Devices — the hourly fetch (owner, 31 Oct 2026: the Devices tab beside 🌍 Countries in Install value → 📈 ROI, "isi
tarah banao"): per app, per install day X, GA4 by PHONE MODEL × COUNTRY — installs, paid installs, back next day and the
revenue at 7 / 30 / 90 days — every read tied to the same read without the split (a day's coverage).

The read shape (measured 31 Oct 2026, ga4_devcoh_probe, 28 apps): ONE install day at a time (filter firstSessionDate == X,
so every user of the read is exactly 0 … A−1 days old), dims mobileDeviceModel × countryId. Whole (Σ rows ÷ the read
without dims 1.000) on 26 of 28 apps; on the two biggest GA4 folds 10–50 % of a day into "(other)" whatever the split
(country alone too) — kept as measured: every split read stores its truth beside it, the build shows the coverage.

  P    [X, X]        newUsers of PAID users (firstUserGoogleAdsCampaignId a real Google Ads campaign id)
  D1   [X+1, X+1]    activeUsers (back next day) — install days of the 7-day window only
  R7   [X, X+6]      newUsers (= the install day's installs), totalAdRevenue
  R30  [X, X+29]     the same — install days of the 30-day window
  R90  [X, X+89]     the same — install days of the 90-day window
each with its truth (the same read without the split: ONE date × firstSessionDate call a kind for every install day
due — that read is whole on every app). Windows (F = the newest final day, E − LATE): each WIN install days
whose age A is complete — 7: [F−6−WIN+1, F−6], 30: [F−29−WIN+1, F−29], 90: [F−89−WIN+1, F−89]. P is read for every
install day of the three windows. A read is asked once (its days are final), newest install days first.
Names: every NAMES_DAYS the model → [brand, marketing name] of the last 90 days (one read).

Store v2 (owner, 6 Nov 2026: "muje all time ka chahiye jab se app start hui he"), private repo, kept for good — one
folder an app, sharded by INSTALL MONTH so the whole history fits (a month file is a few MB at most):
  data/ga4_device/<key>/meta.json.gz     {"v": 2, "app_id", "package", "property_id", "stream_id", "time_zone", "F",
                                         "today", "names": {model: [brand, marketing name]}, "names_at",
                                         "names_all_at", "tr": {kind: {X: truth}}, "bf": the history job's progress,
                                         "months": {YYYY-MM: sha1-12 of the month file's JSON}}
  data/ga4_device/<key>/recent.json.gz   {"v": 2, "x": {X: {kind: rec}}} — install days ≥ F − KEEP_DAYS (the hourly
                                         fetch's own: its windows and its period view; rewritten every run)
  data/ga4_device/<key>/<YYYY-MM>.json.gz {"v": 2, "month", "x": {X: {kind: rec}}} — older install days
  rec = {"t": truth, "m": {model: {cc: value | [installs, revenue]}}, "f": "s" | "t" | null, "at", "tok": the call's
         GA4 tokens, "fin" (P / D1 / R*: its days were final when read), S: "to" (the last activity day in it), "b"
         (the history job's S: install days read in that one call)}
An install day ageing past F − KEEP_DAYS MOVES into its month file (step_app hands it over in "aged"; nothing is
dropped any more). A v1 store (data/ga4_device/<key>.json.gz, one file) is split into v2 on its app's first run and
deleted on the next (a bad v2 write can still fall back to it). A store file that is there but cannot be read is never
written over (StoreError: the app fails the run, the file stays). load_store() gives readers ONE dict: the meta and the
recent days as "x" (or a v1 file's dict while there is no v2 store).
Switched by GA4_DEVICE. Never raises; never prints (log_line: counts only).
"""
import gzip
import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import ga4_probe
from ..db import write_gz_stable, write_json_gz_stable
from . import ga4
from . import ga4_audience as gaud
from . import ga4_firstopen as gf
from . import ga4_uninstall as gu

DIR = "ga4_device"
STORE_V = 2
V1 = 1                              # the one-file store before 6 Nov 2026 (data/ga4_device/<key>.json.gz): read, split
KEY_RE = re.compile(r"[0-9a-f]{12}")
MONTH_RE = re.compile(r"(\d{4}-\d{2})\.json\.gz")
MODEL, CC, CAMP = "mobileDeviceModel", "countryId", "firstUserGoogleAdsCampaignId"
PAID_RE = r"[^(].*"                 # a real Google Ads campaign id (not "(not set)" / "(organic)" …)
LATE = gu.IDAY_LATE                 # F = E − 3: the newest final day
WIN = 28                            # install days a window
AGES = (7, 30, 90)
KEEP_DAYS = 130                     # install days in the recent file (the 90-day window ends F − 89, starts F − 116);
                                    # older ones live in their month files
RANGE_DAYS = 92                     # the period view (owner, 31 Oct 2026: "uppar jo time period he uske hisab se"):
                                    # every install day of today … today − 91 — its installs, paid installs, back next
                                    # day and its revenue SO FAR (S: to today), re-read while it still changes:
FRESH_H = 2.0                       #   an install day ≤ 2 days old: S / P / D1 again after this many hours,
DAILY_H = 20.0                      #   ≤ 31 days old: after this many (once a day),
WEEKLY_H = 7 * 24.0                 #   older: once a week (its revenue so far grows slowly)
NAMES_DAYS = 7
NAMES_ALL_DAYS = 91                 # the whole life's names (names_all: the history job) again after this many days
MAX_CALLS = 80                      # per app per run (the rest next run)
BUDGET_SEC = 180
RETRY_HOURS = 3.0
PAGE_ROWS = 100000
WHOLE_TOL = 0.02                    # a record is whole when Σ rows ÷ its truth is within 2 % (keep_new)
WORKERS = 8                         # properties read side by side (each its own quota; one call at a time each)


def _r4(v):
    v = round(float(v or 0), 4)
    return int(v) if v.is_integer() else v


def windows(f):
    """{age: [first install day, last install day]} for the newest final day f."""
    return {a: (f - timedelta(days=a - 1 + WIN - 1), f - timedelta(days=a - 1)) for a in AGES}


def _fsd(x):
    return {"filter": {"fieldName": "firstSessionDate", "stringFilter": {"matchType": "EXACT", "value": x.strftime("%Y%m%d")}}}


def _paid():
    return {"filter": {"fieldName": CAMP, "stringFilter": {"matchType": "FULL_REGEXP", "value": PAID_RE}}}


def spec(kind, x, today=None):
    """kind → (date range a, b, metrics, extra filters). S: the install day's revenue so far (to `today`)."""
    if kind == "S":
        return x, today, ("newUsers", "totalAdRevenue"), [_fsd(x)]
    if kind == "P":
        return x, x, ("newUsers",), [_fsd(x), _paid()]
    if kind == "D1":
        return x + timedelta(days=1), x + timedelta(days=1), ("activeUsers",), [_fsd(x)]
    age = int(kind[1:])
    return x, x + timedelta(days=age - 1), ("newUsers", "totalAdRevenue"), [_fsd(x)]


def body(a, b, dims, mets):
    return {"dateRanges": [gu._rng(a, b)], "dimensions": ga4._dim(*dims), "metrics": ga4._dim(*mets),
            "currencyCode": "USD", "keepEmptyRows": False}


def _flag(ga):
    metas = getattr(ga, "last_metas", None) or [getattr(ga, "last_meta", None) or {}]
    if any((m or {}).get("samplingMetadatas") for m in metas):
        return "s"
    if any((m or {}).get("subjectToThresholding") for m in metas):
        return "t"
    return None


def read(ga, kind, x, today=None):
    """One kind for install day x → {"m": {model: {cc: value}}, "f": flag} (value: a number for P / D1, [installs,
    revenue] for R* / S); its truth ("t") comes from truths()."""
    a, b, mets, extra = spec(kind, x, today)
    rows = ga.report_all(body(a, b, (MODEL, CC), mets), extra=extra, page_rows=PAGE_ROWS)
    m = {}
    for r in rows:
        md, cc = str(r.get(MODEL) or "(not set)"), str(r.get(CC) or "(not set)")
        vals = [_r4(r.get(k)) for k in mets]
        cur = m.setdefault(md, {})
        if len(vals) == 1:
            cur[cc] = _r4((cur.get(cc) or 0) + vals[0])
        else:
            old = cur.get(cc) or [0, 0]
            cur[cc] = [_r4(old[0] + vals[0]), _r4(old[1] + vals[1])]
    return {"m": m, "f": _flag(ga)}


def truths(ga, kind, xs, today=None):
    """The same reads without the split, for every install day of xs in ONE call (date × firstSessionDate is whole on
    every app) → {X iso: truth} (a number for P / D1, [installs, revenue] for R*)."""
    lo, hi = min(xs), max(xs)
    days = [x.strftime("%Y%m%d") for x in xs]
    pick = {"filter": {"fieldName": "firstSessionDate", "inListFilter": {"values": days}}}
    if kind == "P":
        rows = ga.report_all(body(lo, hi, ("firstSessionDate", "date"), ("newUsers",)), extra=[pick, _paid()],
                             page_rows=PAGE_ROWS)
        out = {}
        for r in rows:
            x, d = ga4._d(r.get("firstSessionDate")), ga4._d(r.get("date"))
            if x and d == x:
                out[x.isoformat()] = _r4(out.get(x.isoformat(), 0) + float(r.get("newUsers") or 0))
        return out
    if kind == "D1":
        rows = ga.report_all(body(lo + timedelta(days=1), hi + timedelta(days=1), ("firstSessionDate", "date"),
                                  ("activeUsers",)), extra=[pick], page_rows=PAGE_ROWS)
        out = {}
        for r in rows:
            x, d = ga4._d(r.get("firstSessionDate")), ga4._d(r.get("date"))
            if x and d == x + timedelta(days=1):
                out[x.isoformat()] = _r4(out.get(x.isoformat(), 0) + float(r.get("activeUsers") or 0))
        return out
    if kind == "S":                                     # so far: every day from the install day to today
        rows = ga.report_all(body(lo, today, ("firstSessionDate", "date"), ("newUsers", "totalAdRevenue")),
                             extra=[pick], page_rows=PAGE_ROWS)
        out = {}
        for r in rows:
            x, d = ga4._d(r.get("firstSessionDate")), ga4._d(r.get("date"))
            if not x or not d or not (x <= d <= today):
                continue
            cur = out.setdefault(x.isoformat(), [0, 0])
            if d == x:
                cur[0] = _r4(cur[0] + float(r.get("newUsers") or 0))
            cur[1] = _r4(cur[1] + float(r.get("totalAdRevenue") or 0))
        return out
    age = int(kind[1:])
    rows = ga.report_all(body(lo, hi + timedelta(days=age - 1), ("firstSessionDate", "date"),
                              ("newUsers", "totalAdRevenue")), extra=[pick], page_rows=PAGE_ROWS)
    out = {}
    for r in rows:
        x, d = ga4._d(r.get("firstSessionDate")), ga4._d(r.get("date"))
        if not x or not d or not (x <= d <= x + timedelta(days=age - 1)):
            continue
        cur = out.setdefault(x.isoformat(), [0, 0])
        if d == x:
            cur[0] = _r4(cur[0] + float(r.get("newUsers") or 0))
        cur[1] = _r4(cur[1] + float(r.get("totalAdRevenue") or 0))
    return out


def _stale(rec, x, today, now, final_on):
    """Is the record of install day x due again? Never read: yes. Read once its days were final (final_on ≤ the newest
    final day when read — P / D1): no. Else by the install day's age: FRESH_H / DAILY_H / WEEKLY_H since it was read."""
    if not rec:
        return True
    if rec.get("fin"):
        return False
    age = (today - x).days
    h = FRESH_H if age <= 2 else DAILY_H if age <= 31 else WEEKLY_H
    return gu._hours_since(rec.get("at"), now) >= h


def todo(store, f, today=None, now=None):
    """The reads due → [(kind, X)]: the period view's newest install days first (today, yesterday: what the owner
    looks at), then the windows' (each once), then the period view's older days."""
    xs = store.get("x") or {}
    w = windows(f)
    need = {}
    for age, (a, b) in w.items():
        d = b
        while d >= a:
            k = d.isoformat()
            need.setdefault(k, set()).update({"P", "R%d" % age} | ({"D1"} if age == 7 else set()))
            d -= timedelta(days=1)
    win = []
    for k in sorted(need, reverse=True):
        have = xs.get(k) or {}
        for kind in ("P", "R7", "D1", "R30", "R90"):
            if kind in need[k] and kind not in have:
                win.append((kind, gu._d(k)))
    if today is None:
        return win
    fresh, older = [], []
    for i in range(RANGE_DAYS):
        x = today - timedelta(days=i)
        have = xs.get(x.isoformat()) or {}
        for kind in ("S", "P", "D1"):
            if kind == "D1" and x + timedelta(days=1) > today:
                continue
            if (kind, x) in win:                        # the window reads it already (once, when final)
                continue
            if _stale(have.get(kind), x, today, now, None):
                (fresh if i <= 2 else older).append((kind, x))
    return fresh + win + older


def _names_of(rows):
    """model × brand × marketing name rows → {model: [brand, marketing name]} (a model's most installed name)."""
    best = {}
    for r in rows:
        md = str(r.get(MODEL) or "")
        if not md or md in ("(other)", "(not set)"):
            continue
        n = float(r.get("newUsers") or 0)
        if md not in best or n > best[md][0]:
            best[md] = (n, [str(r.get("mobileDeviceBranding") or ""), str(r.get("mobileDeviceMarketingName") or "")])
    return {k: v[1] for k, v in best.items()}


def _names_body(a, b):
    return body(a, b, (MODEL, "mobileDeviceBranding", "mobileDeviceMarketingName"), ("newUsers",))


def names_read(ga, f):
    """The last 90 days' models → {model: [brand, marketing name]} (one read)."""
    return _names_of(ga.report_all(_names_body(f - timedelta(days=89), f), page_rows=PAGE_ROWS))


def names_all(ga, hs, f):
    """The app's WHOLE life's models (hs … f, one read a year range, oldest first) → {model: [brand, marketing name]}:
    an old phone's name as well as the 90-day read gives the new ones; a newer range's name wins."""
    out, a = {}, hs
    while a <= f:
        b = min(f, a + timedelta(days=364))
        out.update(_names_of(ga.report_all(_names_body(a, b), page_rows=PAGE_ROWS)))
        a = b + timedelta(days=1)
    return out


def step_app(ga, store, f, now, today=None):
    """One app's run on its store (its recent days in "x") → "fetched" or "fresh". Raises gf.Stop (what was read so far
    is kept). An install day older than F − KEEP_DAYS leaves "x" for store["aged"] (its month file: save_view), never
    dropped."""
    did = False
    store["F"] = f.isoformat()
    if today is not None:
        store["today"] = today.isoformat()
    xs = store.setdefault("x", {})
    for k in [k for k in xs if gu._d(k) < f - timedelta(days=KEEP_DAYS)]:
        store.setdefault("aged", {})[k] = xs.pop(k)
    if not store.get("names") or gu._hours_since(store.get("names_at"), now) >= NAMES_DAYS * 24:
        store["names"] = dict(store.get("names") or {}, **names_read(ga, f))     # an old phone's name stays
        store["names_at"] = gu._now_iso(now)
        did = True
    due = todo(store, f, today, now)
    tr = store.setdefault("tr", {})                     # truths read ahead of their split read: {kind: {X: truth}}
    for kind in ("S", "P", "R7", "D1", "R30", "R90"):
        need = [x for k, x in due if k == kind and (kind == "S" or x.isoformat() not in (tr.get(kind) or {}))]
        if need:
            tr.setdefault(kind, {}).update(truths(ga, kind, need, today))
            for x in need:                              # a day GA4 has nothing for: truth 0
                tr[kind].setdefault(x.isoformat(), 0 if kind in ("P", "D1") else [0, 0])
            did = True
    now_iso = gu._now_iso(now)
    for kind, x in due:
        tok0 = getattr(ga, "tok", 0)
        rec = read(ga, kind, x, today)
        rec["t"] = (tr.get(kind) or {}).pop(x.isoformat(), None)
        rec["at"] = now_iso
        rec["tok"] = getattr(ga, "tok", 0) - tok0
        last = x if kind == "P" else x + timedelta(days=1) if kind == "D1" else None
        if kind.startswith("R") or (last is not None and last <= f):
            rec["fin"] = True                           # its days were final when read: never again
        if kind == "S":
            rec["to"] = today.isoformat()
        xs.setdefault(x.isoformat(), {})[kind] = rec
        did = True
    for kind in list(tr):                               # truths of install days no longer due
        tr[kind] = {k: v for k, v in tr[kind].items() if gu._d(k) >= f - timedelta(days=KEEP_DAYS)}
    return "fetched" if did else "fresh"


# ── the store (v2: one folder an app, sharded by install month) ────────────────────────────────────────────────────
class StoreError(Exception):
    """A v2 store file that exists but cannot be read (damaged, cut, another format): never written over — the app ends
    "failed" for the run and the file is left as it is."""


def _dumps(obj):
    """write_json_gz_stable's bytes (sorted keys, compact): what a month file's sha1 is of."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _read_gz(path):
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            j = json.load(fh)
        return j if isinstance(j, dict) and j.get("v") == STORE_V else None
    except Exception:
        return None


def _read_or_raise(path, strict=True):
    """A v2 file → its dict; None when there is none; StoreError (strict) when it is there but unreadable."""
    j = _read_gz(path)
    if j is None and strict and os.path.exists(path):
        raise StoreError()
    return j


def store_path(data_dir, app_id):
    """The v1 one-file store's path (readers pass it to load_store; the v2 folder sits beside it)."""
    return os.path.join(data_dir, DIR, gu.file_key(app_id) + ".json.gz")


def meta_path(root, key):
    return os.path.join(root, key, "meta.json.gz")


def recent_path(root, key):
    return os.path.join(root, key, "recent.json.gz")


def month_path(root, key, m):
    return os.path.join(root, key, m + ".json.gz")


def months_on_disk(root, key):
    """An app's month files (YYYY-MM, sorted) — a meta that lost its "months" never hides one."""
    try:
        names = os.listdir(os.path.join(root, key))
    except OSError:
        return []
    return sorted(m.group(1) for m in (MONTH_RE.fullmatch(n) for n in names) if m)


def cut_of(f):
    """The oldest install day of the recent file for the newest final day f (older days: their month files)."""
    return f - timedelta(days=KEEP_DAYS)


def _whole(rec):
    """A record whose split ties its truth (Σ rows ÷ truth within WHOLE_TOL on every value; an empty record of a zero
    truth too); None truth: not known to be whole."""
    if not isinstance(rec, dict) or rec.get("t") is None:
        return False
    t = rec["t"] if isinstance(rec["t"], list) else [rec["t"]]
    s = [0.0] * len(t)
    for cmap in (rec.get("m") or {}).values():
        for v in cmap.values():
            vv = v if isinstance(v, list) else [v]
            for i in range(min(len(s), len(vv))):
                s[i] += float(vv[i] or 0)
    for a, b in zip(s, t):
        b = float(b or 0)
        if (b == 0 and a != 0) or (b and abs(a / b - 1) > WHOLE_TOL):
            return False
    return True


def keep_new(old, new):
    """Does `new` replace `old` for one (install day, kind)? When there is no old one, or new was read later and is not
    worse (a whole record never gives way to one that is not)."""
    if not isinstance(new, dict):
        return False
    if not isinstance(old, dict):
        return True
    if (new.get("at") or "") <= (old.get("at") or ""):
        return False
    return _whole(new) or not _whole(old)


def merge_days(cur, days):
    """{X: {kind: rec}} into cur (keep_new per record) → records taken."""
    n = 0
    for X, recs in (days or {}).items():
        if not isinstance(recs, dict):
            continue
        have = cur.setdefault(X, {})
        for kind, rec in recs.items():
            if keep_new(have.get(kind), rec):
                have[kind] = rec
                n += 1
    return n


class Store:
    """One app's v2 store under `root` (data/ga4_device, or the history job's ga4_device_bf). strict: a file there but
    unreadable raises StoreError (a writer never replaces it); a reader passes strict=False and sees it empty."""

    def __init__(self, root, key, strict=True):
        self.root, self.key, self.strict = root, key, strict
        self.meta = _read_or_raise(meta_path(root, key), strict)

    def months(self):
        return sorted(set((self.meta or {}).get("months") or {}) | set(months_on_disk(self.root, self.key)))

    def recent(self):
        return ((_read_or_raise(recent_path(self.root, self.key), self.strict) or {}).get("x")) or {}

    def month(self, m):
        return ((_read_or_raise(month_path(self.root, self.key, m), self.strict) or {}).get("x")) or {}

    def write_recent(self, xs):
        write_gz_stable(recent_path(self.root, self.key), _dumps({"v": STORE_V, "x": xs}))

    def write_month(self, m, xs):
        raw = _dumps({"v": STORE_V, "month": m, "x": xs})
        write_gz_stable(month_path(self.root, self.key, m), raw)
        if self.meta is None:
            self.meta = {"v": STORE_V}
        self.meta.setdefault("months", {})[m] = hashlib.sha1(raw).hexdigest()[:12]

    def save_meta(self):
        self.meta["v"] = STORE_V
        self.meta.setdefault("months", {})
        write_json_gz_stable(meta_path(self.root, self.key), self.meta)

    def view(self):
        """The meta + the recent days as ONE dict (what step_app and the readers work on)."""
        out = {k: v for k, v in (self.meta or {}).items() if k != "months"}
        out["x"] = self.recent()
        return out

    def file_days(self, days):
        """{X: {kind: rec}} of install days older than the recent file → their month files (merge_days), each written
        once → records taken."""
        by, n = {}, 0
        for X, recs in (days or {}).items():
            by.setdefault(X[:7], {})[X] = recs
        for m, part in sorted(by.items()):
            cur = self.month(m)
            n += merge_days(cur, part)
            self.write_month(m, cur)
        return n

    def save_view(self, view):
        """step_app's dict → the files: the days it aged out (and any recent day older than the cut) into their month
        files FIRST, then the recent file, then the meta (a stop between leaves a day in both: readers take the recent
        copy)."""
        view = dict(view)
        aged = dict(view.pop("aged", None) or {})
        xs = dict(view.pop("x", None) or {})
        if view.get("F"):
            cut = cut_of(gu._d(view["F"])).isoformat()
            for k in [k for k in xs if k < cut]:
                aged[k] = xs.pop(k)
        if aged:
            self.file_days(aged)
        self.write_recent(xs)
        months = (self.meta or {}).get("months") or {}
        self.meta = dict(view, months=months)
        self.save_meta()


def load_v1(path):
    """A v1 one-file store's dict (or None)."""
    s = gu.load_store(path)
    return s if isinstance(s, dict) and s.get("v") in (V1, STORE_V) and "months" not in s else None


def load_store(path):
    """The app's store for READERS (source_build's names, roi_build's Devices block) → ONE dict: the v2 meta with its
    recent install days as "x" — or, while the app has no v2 store yet, the v1 file's dict (None: neither)."""
    root, fn = os.path.split(path)
    key = fn[:-8] if fn.endswith(".json.gz") else fn
    try:
        st = Store(root, key, strict=False)
        if st.meta is not None:
            return st.view()
    except Exception:
        pass
    return load_v1(path)


def open_store(data_dir, aid):
    """The fetch's store of an app → (Store, its view, v1 path to delete or None): v2 when there is one (the v1 file
    beside it is deleted after this run: it was left one run for a fall back), else the v1 file split into v2 by
    save_view (kept one more run), else a new one. StoreError: a v2 file there but unreadable."""
    root, key = os.path.join(data_dir, DIR), gu.file_key(aid)
    st = Store(root, key)
    v1p = store_path(data_dir, aid)
    if st.meta is not None:
        st.recent()                                     # (unreadable: StoreError before anything is written)
        return st, st.view(), (v1p if os.path.exists(v1p) else None)
    v1 = load_v1(v1p)
    if v1 is not None:
        view = {k: v for k, v in v1.items() if k not in ("v", "months")}
        view.setdefault("x", {})
        view["migrated"] = True
        return st, view, None
    return st, {"x": {}}, None


def load_state(data_dir):
    try:
        with open(os.path.join(data_dir, DIR, "state.json"), encoding="utf-8") as fh:
            raw = json.load(fh)
        if isinstance(raw, dict) and isinstance(raw.get("fetch"), dict):
            if not isinstance(raw.get("staged"), dict):
                raw["staged"] = {}
            return raw
    except (OSError, ValueError):
        pass
    return {"v": 1, "fetch": {}, "staged": {}}


def save_state(data_dir, state):
    path = os.path.join(data_dir, DIR, "state.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=1)
    try:
        with open(path, encoding="utf-8") as fh:
            if fh.read() == text:
                return False
    except OSError:
        pass
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return True


COUNTS = ("selected", "with_ga4", "fetched", "fresh", "failed", "deferred", "waiting", "calls", "tokens")


def _one_app(a, st, r, prop, token, ust, data_dir, now, now_iso, over, counts, lock):
    """One app's run → fetched | fresh | deferred | failed (its store written when anything was read)."""
    aid, pid = a["app_id"], r["property_id"]
    tz = ust["tz"].get(pid) or "UTC"
    f = ga4.window_end_in(tz, now) - timedelta(days=LATE)
    try:
        today = now.astimezone(ZoneInfo(tz)).date()
    except Exception:
        today = now.date()
    ga = gf.App(token, pid, r["stream_id"], prop, over=over, max_calls=MAX_CALLS)
    sto = store = old_v1 = None
    try:
        sto, store, old_v1 = open_store(data_dir, aid)
        res = step_app(ga, store, f, now, today)
        st.pop("deferred", None)
        st.update(last_try=now_iso, fail=None)
        if res == "fetched":
            st["last_ok"] = now_iso
    except gf.Stop:
        st["deferred"] = True
        res = "deferred"
    except Exception as e:
        st.update(last_try=now_iso, fail="store" if isinstance(e, StoreError) else gu._fail_kind(e))
        res = "failed"
    finally:
        try:
            if sto is not None and (ga.calls or store.get("aged") or store.get("migrated")):
                store.pop("migrated", None)
                store.update(app_id=aid, package=a["package"], property_id=pid, stream_id=r["stream_id"],
                             time_zone=tz)
                sto.save_view(store)
            if old_v1 and res != "failed":              # v2 read fine this run: the v1 copy has had its run
                os.remove(old_v1)
        except Exception as e:
            st.update(last_try=now_iso, fail="store" if isinstance(e, StoreError) else "other")
            res = "failed"
        st["key"] = gu.file_key(aid)
        with lock:
            counts["calls"] += ga.calls
            counts["tokens"] += ga.tok
    return res


def refresh_all(cfg, data_dir, apps, now=None, clock=time.monotonic, budget=BUDGET_SEC, staged_dir=None):
    """Every selected app → {"counts", "apps": {app id: fetched|fresh|failed|deferred|waiting}}; the apps that waited
    longest first. staged_dir: the history job's folder (GA4_DEVICE_HISTORY), merged into the store FIRST
    (merge_staged; its time is not the GA4 budget's). Never raises; never prints."""
    now = now or datetime.now(timezone.utc)
    t0 = clock()
    counts = dict.fromkeys(COUNTS, 0)
    out = {"counts": counts, "apps": {}}
    try:
        state = load_state(data_dir)
        if staged_dir:
            mg = merge_staged(data_dir, staged_dir, state, now)
            counts["merged"], counts["staged_bad"], counts["stalled"] = mg["merged"], mg["bad"], mg["stalled"]
            save_state(data_dir, state)
        t0 = clock()
        ust = gu.load_state(data_dir)
        routes = ust["routes"].get("by_package") or {}
        tokens, _ = ga4_probe.owner_tokens({"GA4_REFRESH_TOKENS": cfg.get("refresh_tokens") or "",
                                            "GA4_REFRESH_TOKEN": cfg.get("refresh_token") or ""})
        owner_rt, access, props = dict(tokens), {}, {}
        now_iso = gu._now_iso(now)

        def over():
            return "budget" if clock() - t0 >= budget else None
        work = []
        for a in apps:
            if a.get("same_as") or not a.get("package"):
                continue
            counts["selected"] += 1
            r = routes.get(a["package"])
            if not r:
                continue
            counts["with_ga4"] += 1
            aid = a["app_id"]
            if not gaud._uni_meta(ust, data_dir, aid, r):
                out["apps"][aid] = "waiting"
                continue
            st = state["fetch"].setdefault(aid, {})
            if st.get("fail") and gu._hours_since(st.get("last_try"), now) < RETRY_HOURS:
                out["apps"][aid] = "failed"
                continue
            work.append((a, st, r))
        work.sort(key=lambda t: (not t[1].get("deferred"), t[1].get("last_ok") or "", t[0]["app_id"]))
        for owner in sorted({r.get("owner") for _, _, r in work}, key=str):   # the owners' tokens before the threads
            try:
                access[owner] = (ga4.access_token(cfg["client_id"], cfg["client_secret"], owner_rt[owner])
                                 if owner in owner_rt else None)
            except Exception:
                access[owner] = None
        lock = threading.Lock()
        groups = {}
        for item in work:                               # one worker a property (its quota), apps in the order above
            groups.setdefault(item[2]["property_id"], []).append(item)

        def one(group):
            for a, st, r in group:
                aid, pid = a["app_id"], r["property_id"]
                prop = props[pid]
                if over() or prop["stop"]:
                    st["deferred"] = True
                    res = "deferred"
                elif not access.get(r.get("owner")):
                    st.update(last_try=now_iso, fail="auth")
                    res = "failed"
                else:
                    res = _one_app(a, st, r, prop, access[r.get("owner")], ust, data_dir, now, now_iso, over, counts,
                                   lock)
                with lock:
                    out["apps"][aid] = res
        for pid in groups:
            props.setdefault(pid, {"quota": None, "stop": None})
        with ThreadPoolExecutor(max_workers=max(1, WORKERS)) as ex:
            list(ex.map(one, list(groups.values())))
        save_state(data_dir, state)
    except Exception as e:                              # a bug here must never cost the build
        out["error"] = type(e).__name__
    for v in out["apps"].values():
        if v in counts:
            counts[v] += 1
    return out


def log_line(status):
    """The build log's ONE line for this step — counts only (the history merge's counts when it ran); an internal error,
    a staged file the merge could not take or a history job that stopped (bf_stalled) also gets the health banner's
    line ("<step> skipped: <ErrorType>")."""
    c = (status or {}).get("counts") or {}
    err = (status or {}).get("error")
    mg = (", merged %d, staged bad %d" % (gaud._int(c.get("merged")), gaud._int(c.get("staged_bad")))
          if "merged" in c else "")
    line = ("ga4 device: apps %d, with GA4 %d, fetched %d, fresh %d, failed %d, deferred %d, waiting %d, calls %d, "
            "tokens %d%s%s" % tuple([gaud._int(c.get(k)) for k in ("selected", "with_ga4", "fetched", "fresh", "failed",
                                                                   "deferred", "waiting", "calls", "tokens")]
                                    + [mg, (", error " + err) if err else ""]))
    if err:
        line += "\nga4 device skipped: %s" % err
    if gaud._int(c.get("staged_bad")):
        line += "\nga4 device history skipped: StagedFileError"
    if gaud._int(c.get("stalled")):                 # (the job's own log is public-only: the build says it too)
        line += "\nga4 device history skipped: StalledError"
    return line


# ── the history job's staged records → the build's store (the hourly build, GA4_DEVICE_HISTORY) ─────────────────────
MERGE_KINDS = ("S", "P", "D1")


def _sha1_file(path):
    try:
        with open(path, "rb") as fh:
            return hashlib.sha1(fh.read()).hexdigest()
    except OSError:
        return None


def staged_keys(staged_dir):
    try:
        return sorted(n for n in os.listdir(staged_dir) if KEY_RE.fullmatch(n) and os.path.isdir(os.path.join(staged_dir,
                                                                                                             n)))
    except OSError:
        return []


STALL_H = 18                        # the history job runs every 6 h (a run: at most ~6 h): its word older than 3 runs
                                    # while a phase is not done = the job stopped ("ga4 device history skipped: StalledError")


def bf_stalled(bf, now=None):
    """The history job's progress ("bf") says it still has work (phase A or B not done) but its last word ("at") is
    STALL_H hours old or more (no word at all: not yet run, not stalled)."""
    if not isinstance(bf, dict) or not bf.get("at"):
        return False
    if (bf.get("A") or {}).get("done") and (bf.get("B") or {}).get("done"):
        return False
    return gu._hours_since(bf.get("at"), now or datetime.now(timezone.utc)) >= STALL_H


def merge_staged(data_dir, staged_dir, state=None, now=None):
    """Copy the history job's records (its folder: the v2 layout, month files only) into data/ga4_device, (install day,
    kind) by keep_new — never an install day the hourly fetch reads itself (≥ today − RANGE_DAYS + 1), only S / P / D1;
    a day ≥ the build's cut goes to its recent file, an older one to its month file (each file written once). Its
    whole-life names fill the build's (the build's own, newer, win) and its progress ("bf") is copied. An app the build
    has no v2 store of yet (its v1 file is split by this build's fetch) waits for the next build. Idempotent: a staged
    file whose sha1 is in state["staged"] is not read again; a broken one is skipped and counted. → {"merged": records
    taken, "files": staged files read, "bad": files or apps skipped, "stalled": apps whose history job stopped
    (bf_stalled)}."""
    out = {"merged": 0, "files": 0, "bad": 0, "stalled": 0}
    if not staged_dir or not os.path.isdir(staged_dir):
        return out
    root = os.path.join(data_dir, DIR)
    seen = state.setdefault("staged", {}) if isinstance(state, dict) else {}
    for key in staged_keys(staged_dir):
        try:
            smeta = _read_gz(meta_path(staged_dir, key))
            if smeta is None:
                out["bad"] += 1
                continue
            todo_files = []
            for m in months_on_disk(staged_dir, key):
                sha = _sha1_file(month_path(staged_dir, key, m))
                if sha and seen.get(key + "/" + m) != sha:
                    todo_files.append((m, sha))
            bst = Store(root, key)                      # (unreadable: StoreError, skipped and counted, left alone)
            if bst.meta is None:
                v1p = os.path.join(root, key + ".json.gz")
                if os.path.exists(v1p):
                    continue                            # split into v2 by this build's fetch: merged next build
                bst.meta = {k: smeta.get(k) for k in ("app_id", "package", "property_id", "stream_id", "time_zone",
                                                      "F", "today")}
            f = gu._d(bst.meta.get("F") or smeta.get("F"))
            today = gu._d(bst.meta.get("today") or smeta.get("today") or f.isoformat())
            cut = cut_of(f).isoformat()
            own = (today - timedelta(days=RANGE_DAYS - 1)).isoformat()      # the hourly fetch's install days
            to_recent, done = {}, []
            for m, sha in todo_files:                   # one staged file at a time (read, merged, written, dropped):
                j = _read_gz(month_path(staged_dir, key, m))        # a backlog of months is never held in memory
                out["files"] += 1
                if j is None:
                    out["bad"] += 1
                    continue
                to_month = {}
                for X, recs in (j.get("x") or {}).items():
                    if X >= own or not isinstance(recs, dict):
                        continue
                    part = {k: v for k, v in recs.items() if k in MERGE_KINDS and isinstance(v, dict)}
                    if part:
                        (to_recent if X >= cut else to_month.setdefault(X[:7], {}))[X] = part
                j = None
                for bm, days in sorted(to_month.items()):
                    cur = bst.month(bm)
                    n = merge_days(cur, days)
                    if n or bm not in (bst.meta.get("months") or {}):
                        bst.write_month(bm, cur)
                    out["merged"] += n
                done.append((m, sha))
            if to_recent:                               # (the recent days: a few weeks, written once)
                cur = bst.recent()
                n = merge_days(cur, to_recent)
                if n:
                    bst.write_recent(cur)
                    out["merged"] += n
            names = smeta.get("names") or {}
            if names:
                bst.meta["names"] = dict(names, **(bst.meta.get("names") or {}))
            if isinstance(smeta.get("bf"), dict):
                bst.meta["bf"] = smeta["bf"]
                if bf_stalled(smeta["bf"], now):
                    out["stalled"] += 1
            bst.save_meta()
            for m, sha in done:
                seen[key + "/" + m] = sha
        except Exception:
            out["bad"] += 1
    return out


# ── the history job (python -m admob_iq.fetch.ga4_device --backfill; .github/workflows/devices-backfill.yml) ────────
# Every install day of every app since its first one (hs, the Uninstall store's history start) that is older than the
# hourly fetch's own (≤ today − RANGE_DAYS): S / P / D1, as the hourly fetch reads them, newest first. Per install
# MONTH: the truths first (one call a kind — the date × firstSessionDate read, whole on every app and age, step 0
# probe 6 Nov 2026), then S MONTH-BATCHED (firstSessionDate × model × country with the month's days in one inList:
# measured identical cell for cell to the one-day read on every probed day; a batch holds ≤ S_BATCH_N installs so it
# stays one page), then P and D1 one install day a call (a day whose truth is 0 gets an empty record, no call).
# Phase A: the last year (today − A_DAYS … today − RANGE_DAYS) of every property before any phase B (older, to hs);
# phase R: an old install day's revenue so far read again when its "to" is R_NEAR (≤ a year old) / R_FAR days
# behind F — a month at a time. Resume = the stores: a day complete in the job's folder or in the build's store is
# never read again. Quota: the Screens history job's floors (65 % of an hourly bucket, 40 % of the day's — above
# the 50 % where the hourly build's GA4 steps stop) and its 429 rule; a property there waits for the next clock hour.
BF_DIR = "ga4_device_bf"
BF_WORKERS = 12
BF_BUDGET_SEC = 19800               # no GA4 call is started after 5.5 h (the workflow's timeout is 350 min)
BF_APP_CALLS = 10 ** 7              # (the clock and the floors bound it)
BF_FAIL_MAX = 5
BF_RETRY_SEC = 180
PUSH_SEC = 600
HEARTBEAT_SEC = 60
TICK_SEC = 5.0
DATA_ROOT = "_private"
A_DAYS = 365
S_BATCH_N = 60000                   # installs in one batched S call (rows ≤ about its installs: one page)
SAVE_EVERY = 20                     # one-day reads between two writes of the month file
R_NEAR, R_FAR = 28, 91
BF_COUNTS = ("selected", "with_ga4", "done", "deferred", "failed", "waiting", "days", "s_calls", "p_calls",
             "d1_calls", "empty", "refreshed", "calls", "tokens", "quota_stops", "pushes", "push_failed")


def read_batch(ga, xs, f):
    """S of several install days in ONE call: dims firstSessionDate × model × country over [the oldest, f], the days in
    an inList → {X iso: {"m": {model: {cc: [installs, revenue]}}, "f": flag}} (every asked day, empty when GA4 has
    nothing for it)."""
    days = sorted(xs)
    pick = {"filter": {"fieldName": "firstSessionDate", "inListFilter": {"values": [x.strftime("%Y%m%d") for x in days]}}}
    rows = ga.report_all(body(days[0], f, ("firstSessionDate", MODEL, CC), ("newUsers", "totalAdRevenue")),
                         extra=[pick], page_rows=PAGE_ROWS)
    out = {x.isoformat(): {"m": {}} for x in days}
    for r in rows:
        x = ga4._d(r.get("firstSessionDate"))
        e = out.get(x.isoformat()) if x else None
        if e is None:
            continue
        md, cc = str(r.get(MODEL) or "(not set)"), str(r.get(CC) or "(not set)")
        cur = e["m"].setdefault(md, {})
        old = cur.get(cc) or [0, 0]
        cur[cc] = [_r4(old[0] + float(r.get("newUsers") or 0)), _r4(old[1] + float(r.get("totalAdRevenue") or 0))]
    fl = _flag(ga)
    for e in out.values():
        e["f"] = fl
    return out


def _months_desc(lo, hi):
    """The calendar months of [lo, hi], newest first → [(first day, last day) ∩ [lo, hi]]."""
    out, m = [], hi.replace(day=1)
    while m >= lo.replace(day=1):
        nxt = (m + timedelta(days=32)).replace(day=1)
        out.append((max(m, lo), min(nxt - timedelta(days=1), hi)))
        m = (m - timedelta(days=1)).replace(day=1)
    return out


class BfJob:
    """One app in the history job: its staged store (written) and the build's (read only, strict=False)."""

    def __init__(self, staged_dir, data_dir, it, now, ga):
        a, r = it["a"], it["r"]
        self.aid, self.key, self.now, self.ga = a["app_id"], gu.file_key(a["app_id"]), now, ga
        self.st = Store(staged_dir, self.key)          # (unreadable: StoreError — the app fails, nothing written)
        meta = self.st.meta if self.st.meta is not None else {"v": STORE_V, "months": {}}
        tz = it["tz"]
        try:
            self.today = now.astimezone(ZoneInfo(tz)).date()
        except Exception:
            self.today = now.date()
        self.f = ga4.window_end_in(tz, now) - timedelta(days=LATE)
        self.top = self.today - timedelta(days=RANGE_DAYS)          # the newest install day the job reads
        self.hs = it["hs"]
        meta.update(app_id=a["app_id"], package=a["package"], property_id=r["property_id"],
                    stream_id=r["stream_id"], time_zone=tz, F=self.f.isoformat(), today=self.today.isoformat())
        self.st.meta = meta
        self.b = Store(os.path.join(data_dir, DIR), self.key, strict=False)
        if self.b.meta is not None:
            rec = self.b.recent()
        else:                                           # the build has not split its v1 file yet: read that one
            rec = (load_v1(store_path(data_dir, a["app_id"])) or {}).get("x") or {}
        top = self.top.isoformat()                      # (only its days this job could read, only their S / P / D1)
        self.b_recent = {k: {kk: vv for kk, vv in v.items() if kk in MERGE_KINDS} for k, v in rec.items()
                         if k <= top and isinstance(v, dict)}
        rec = None
        self.mine, self.theirs, self.dirty = {}, {}, set()
        self.now_iso = gu._now_iso(now)
        self.c = dict.fromkeys(("days", "s_calls", "p_calls", "d1_calls", "empty", "refreshed"), 0)

    # the two stores' records of a month
    def staged(self, m):
        if m not in self.mine:
            self.mine[m] = self.st.month(m)
        return self.mine[m]

    def build(self, m):
        if m not in self.theirs:
            got = self.b.month(m) if self.b.meta is not None else {}
            got = dict(got)
            for X, v in self.b_recent.items():          # (the recent copy of a day wins, as the build's readers)
                if X[:7] == m:
                    got[X] = v
            self.theirs[m] = got
        return self.theirs[m]

    def rec(self, x, kind):
        k = x.isoformat()
        return ((self.staged(k[:7]).get(k) or {}).get(kind)) or ((self.build(k[:7]).get(k) or {}).get(kind))

    def missing(self, x):
        """The kinds install day x still needs (S, P, D1 — D1 only once its day after is final)."""
        out = [k for k in ("S", "P") if not self.rec(x, k)]
        if x + timedelta(days=1) <= self.f and not self.rec(x, "D1"):
            out.append("D1")
        return out

    def put(self, x, kind, rec):
        k = x.isoformat()
        self.staged(k[:7]).setdefault(k, {})[kind] = rec
        self.dirty.add(k[:7])

    def save(self):
        for m in sorted(self.dirty):
            self.st.write_month(m, self.mine[m])
        self.dirty.clear()
        self.st.save_meta()

    def forget(self, keep=()):
        """Months done with leave memory (the job holds one month of an app at a time)."""
        for d in (self.mine, self.theirs):
            for m in [m for m in d if m not in keep and m not in self.dirty]:
                del d[m]

    # the reads
    def _s(self, xs, ts):
        tok0 = self.ga.tok
        got = read_batch(self.ga, xs, self.f)
        tok = self.ga.tok - tok0
        self.c["s_calls"] += 1
        for x in xs:
            rec = got.get(x.isoformat()) or {"m": {}, "f": None}
            rec.update(t=ts.get(x.isoformat()), to=self.f.isoformat(), at=self.now_iso, tok=tok, b=len(xs))
            self.put(x, "S", rec)

    def s_days(self, xs):
        """S of install days xs (newest first): the truth in one call, zero days empty, the rest in batches."""
        if not xs:
            return
        ts = truths(self.ga, "S", xs, self.f)
        batch, n = [], 0.0
        for x in sorted(xs, reverse=True):
            t = ts.get(x.isoformat()) or [0, 0]
            ts[x.isoformat()] = t
            if not float(t[0] or 0) and not float(t[1] or 0):
                self.put(x, "S", {"m": {}, "t": t, "f": None, "to": self.f.isoformat(), "at": self.now_iso, "tok": 0,
                                  "b": 0})
                self.c["empty"] += 1
                continue
            if batch and n + float(t[0] or 0) > S_BATCH_N:
                self._s(batch, ts)
                batch, n = [], 0.0
                self.save()
            batch.append(x)
            n += float(t[0] or 0)
        if batch:
            self._s(batch, ts)
        self.save()

    def one_day(self, kind, x, t):
        if not float(t or 0):
            rec = {"m": {}, "f": None, "tok": 0}
            self.c["empty"] += 1
        else:
            tok0 = self.ga.tok
            rec = read(self.ga, kind, x)
            rec["tok"] = self.ga.tok - tok0
            self.c["p_calls" if kind == "P" else "d1_calls"] += 1
        rec.update(t=t, at=self.now_iso, fin=True)
        self.put(x, kind, rec)

    def fill_month(self, need):
        """{x: [kinds]} of one install month → read: S (truth + batches), then P and D1 day by day newest first."""
        s = [x for x, ks in need.items() if "S" in ks]
        p = sorted((x for x, ks in need.items() if "P" in ks), reverse=True)
        d1 = sorted((x for x, ks in need.items() if "D1" in ks), reverse=True)
        tp = truths(self.ga, "P", p) if p else {}
        td = truths(self.ga, "D1", d1) if d1 else {}
        self.s_days(s)
        n = 0
        for x in sorted(set(p) | set(d1), reverse=True):
            if x in p:
                self.one_day("P", x, tp.get(x.isoformat(), 0))
                n += 1
            if x in d1:
                self.one_day("D1", x, td.get(x.isoformat(), 0))
                n += 1
            if n >= SAVE_EVERY:
                self.save()
                n = 0
        self.c["days"] += len(need)
        self.save()

    def names(self):
        m = self.st.meta
        if not m.get("names_all_at") or gu._hours_since(m.get("names_all_at"), self.now) >= NAMES_ALL_DAYS * 24:
            got = names_all(self.ga, self.hs, self.f)
            m["names"] = dict(m.get("names") or {}, **got)
            m["names_all_at"] = self.now_iso
            self.st.save_meta()

    def mark(self, ph, oldest=None, done=None):
        b = self.st.meta.setdefault("bf", {})
        e = b.setdefault(ph, {})
        if oldest is not None:
            e["oldest"] = oldest.isoformat()
        if done is not None:
            e["done"] = bool(done)
        e["at"] = self.now_iso


def fill(job, lo, hi, ph):
    """Every install day of [lo, hi] ∩ [hs, top] not complete in either store, a month at a time, newest first."""
    lo, hi = max(lo, job.hs), min(hi, job.top)
    if lo > hi:
        job.mark(ph, done=True)
        return
    for a, b in _months_desc(lo, hi):
        need = {}
        d = b
        while d >= a:
            ks = job.missing(d)
            if ks:
                need[d] = ks
            d -= timedelta(days=1)
        if need:
            job.fill_month(need)
        job.mark(ph, oldest=a)
        job.forget()
    job.mark(ph, done=True)


def refresh(job):
    """Phase R: an old install day's revenue so far read again (S only: truth + batches) when its "to" is R_NEAR (≤ a
    year old) / R_FAR days or more behind F — a month at a time, newest first; the job's own newer record counts first
    (never the same day twice in a row)."""
    if job.hs > job.top:
        return
    for a, b in _months_desc(job.hs, job.top):
        stale = []
        d = b
        while d >= a:
            rec = job.rec(d, "S")
            if rec is not None:
                gap = R_NEAR if (job.today - d).days <= A_DAYS else R_FAR
                to = rec.get("to")
                if not to or (job.f - gu._d(to)).days >= gap:
                    stale.append(d)
            d -= timedelta(days=1)
        if stale:
            job.s_days(stale)
            job.c["refreshed"] += len(stale)
        job.forget()
    b = job.st.meta.setdefault("bf", {})
    b["R"] = {"at": job.now_iso}


def _bf_note(job, state, why, typ, prop, at):
    """The job's last word on an app in its staged meta ("bf": state, why, the exception TYPE only, counts, the
    property's hourly buckets' remaining share) — counts and codes only."""
    if job is None:
        return
    try:
        b = job.st.meta.setdefault("bf", {})
        b.update(at=gu._now_iso(at), state=state, why=why, type=typ)
        n = b.setdefault("n", {})
        n[state] = gaud._int(n.get(state)) + 1
        q = (prop or {}).get("quota") or {}
        b["q"] = {k: round(gaud._int((q.get(k) or {}).get("remaining")) /
                           float(max(cap, gaud._int((q.get(k) or {}).get("consumed")) +
                                     gaud._int((q.get(k) or {}).get("remaining")))), 3)
                  for k, cap in gu.QUOTA_CAP.items() if isinstance(q.get(k), dict)}
    except Exception:
        pass


def _bf_select(cfg, data_dir, apps, now, counts, out, clock):
    """The apps with a GA4 route and an Uninstall history → {property id: [item]} (tokens shared: Tokens.get keeps
    them fresh); the others straight to out["apps"] ("waiting")."""
    from . import ga4_screens as gs
    ust = gu.load_state(data_dir)
    routes = ust["routes"].get("by_package") or {}
    tokens, _ = ga4_probe.owner_tokens({"GA4_REFRESH_TOKENS": cfg.get("refresh_tokens") or "",
                                        "GA4_REFRESH_TOKEN": cfg.get("refresh_token") or ""})
    toks, by_prop = gs.Tokens(cfg, tokens, clock), {}
    for a in apps:
        if a.get("same_as") or not a.get("package"):
            continue
        counts["selected"] += 1
        r = routes.get(a["package"])
        if not r:
            continue
        counts["with_ga4"] += 1
        um = gaud._uni_meta(ust, data_dir, a["app_id"], r)
        if not um:
            out["apps"][a["app_id"]] = "waiting"
            continue
        owner = r.get("owner")
        pid = str(r["property_id"])
        by_prop.setdefault(pid, []).append(
            {"a": a, "r": r, "hs": gu._d(um["history_start"]),
             "tz": ust["tz"].get(r["property_id"]) or ust["tz"].get(pid) or "UTC", "tok": toks.get(owner),
             "renew": lambda bad=None, o=owner: toks.get(o, bad)})
    return by_prop


def backfill_all(cfg, data_dir, staged_dir, apps, now=None, clock=time.monotonic, budget=BF_BUDGET_SEC,
                 workers=BF_WORKERS, push=None, push_sec=PUSH_SEC, say=None, wall=None, sleep=time.sleep,
                 tick=TICK_SEC):
    """The history in one go, into `staged_dir` only: phase A (the last year) of every property, then B (older, to the
    app's first install day), then R (old revenue so far again), properties side by side (`workers`, one call at a time
    each); a property at the job's floors (ga4_screens.BF_FLOORS) or a 429 waits for the next clock hour while the
    others go on. push() (commit + push of the folder) every push_sec and at the end; say() a counts-only heartbeat.
    → {"counts", "apps"}. Never raises."""
    from . import ga4_screens as gs
    now = now or datetime.now(timezone.utc)
    wall = wall or (lambda: datetime.now(timezone.utc))
    t0 = clock()
    counts = dict.fromkeys(BF_COUNTS, 0)
    out = {"counts": counts, "apps": {}}
    lock = threading.Lock()

    def over():
        return "budget" if clock() - t0 >= budget else None

    def pushed():
        if not push:
            return None
        try:
            ok = bool(push())
        except Exception:
            ok = False
        counts["pushes" if ok else "push_failed"] += 1
        return ok

    try:
        by_prop = _bf_select(cfg, data_dir, apps, now, counts, out, clock)
        for xs in by_prop.values():
            for it in xs:
                out["apps"][it["a"]["app_id"]] = "deferred"
        props = {pid: {"quota": None, "stop": None, "stops": 0} for pid in by_prop}
        order = sorted(by_prop)
        work = [(ph, p) for ph in ("A", "B", "R") for p in order]
        paused, busy, jobs, res, fails = {}, set(), {}, {}, {}

        def take():
            with lock:
                if not work:
                    return None, None
                t = wall()
                for i, (ph, pid) in enumerate(work):
                    if pid in busy or (pid in paused and t < paused[pid]):
                        continue
                    if any(w == (q, pid) for w in work for q in ("A", "B", "R")[:("A", "B", "R").index(ph)]):
                        continue                        # a property's phases in order: A, then B, then R
                    work.pop(i)
                    busy.add(pid)
                    return (ph, pid), 0
                ends = [paused[p] for _, p in work if p in paused and p not in busy and t < paused[p]]
                return None, (min(ends) - t).total_seconds() if ends else 1.0

        def run_prop(ph, pid):
            prop = props[pid]
            if prop.get("stop"):                        # a new clock hour: the property's buckets are full again
                prop["stop"], prop["quota"] = None, None
            for it in sorted(by_prop[pid], key=lambda t: t["a"]["app_id"]):
                aid = it["a"]["app_id"]
                with lock:
                    if res.get(aid) in ("failed", "done"):
                        continue
                    if not it["tok"]:
                        res[aid] = "failed"
                        continue
                job = None
                try:
                    job = jobs.get(aid)
                    if job is None:
                        ga = gs.App(it["tok"], pid, it["r"]["stream_id"], prop, over=over, max_calls=BF_APP_CALLS,
                                    gate=gs.bf_gate, renew=it.get("renew"))
                        job = BfJob(staged_dir, data_dir, it, now, ga)
                        with lock:
                            jobs[aid] = job
                    if ph == "A":
                        job.names()
                        fill(job, job.today - timedelta(days=A_DAYS), job.top, "A")
                    elif ph == "B":
                        fill(job, job.hs, job.today - timedelta(days=A_DAYS + 1), "B")
                    else:
                        refresh(job)
                        with lock:
                            res[aid] = "done"
                    _bf_note(job, "done " + ph, None, None, prop, wall())
                except gf.Stop as e:
                    _bf_note(job, "paused" if prop.get("stop") else "stopped",
                             prop.get("stop") or (e.args or [""])[0], None, prop, wall())
                    if prop.get("stop"):
                        return "paused"
                    if (e.args or [""])[0] == "budget":
                        return "budget"
                except StoreError:
                    with lock:
                        res[aid] = "failed"
                except Exception as e:                  # a 5xx after one retry, a timeout, a dropped connection:
                    _bf_note(job, "error", gu._fail_kind(e), type(e).__name__, prop, wall())
                    with lock:                          # the property rests BF_RETRY_SEC, the app is tried again
                        fails[aid] = fails.get(aid, 0) + 1
                        if fails[aid] >= BF_FAIL_MAX:
                            res[aid] = "failed"
                        else:
                            return "retry"
                finally:
                    if job is not None:
                        try:
                            job.save()
                        except Exception:
                            pass
            return "done"

        def worker():
            while not over():
                got, wait_s = take()
                if got is None:
                    if wait_s is None:
                        return
                    left = budget - (clock() - t0)
                    if wait_s > left:
                        return
                    sleep(min(max(wait_s, 0.5), 60.0))
                    continue
                ph, pid = got
                r = run_prop(ph, pid)
                with lock:
                    busy.discard(pid)
                    if r == "paused":
                        paused[pid] = gs._next_hour(wall())
                        work.insert(0, (ph, pid))
                    elif r == "retry":
                        paused[pid] = wall() + timedelta(seconds=BF_RETRY_SEC)
                        work.insert(0, (ph, pid))
                    elif r == "budget":
                        work.insert(0, (ph, pid))

        last_push = last_beat = clock()
        n_all = sum(len(xs) for xs in by_prop.values())
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futs = [ex.submit(worker) for _ in range(max(1, workers))]
            while True:
                _, running = wait(futs, timeout=tick)
                if push and clock() - last_push >= push_sec:
                    pushed()
                    last_push = clock()
                if say and clock() - last_beat >= HEARTBEAT_SEC:
                    try:
                        with lock:
                            calls = sum(j.ga.calls for j in list(jobs.values()))
                            n = sum(1 for v in list(res.values()) if v == "done")
                        say("devices backfill progress: apps %d/%d, calls %d, %ds" % (n, n_all, calls,
                                                                                       int(clock() - t0)))
                    except Exception:
                        pass
                    last_beat = clock()
                if not running:
                    break
        for job in jobs.values():
            counts["calls"] += job.ga.calls
            counts["tokens"] += job.ga.tok
            for k, v in job.c.items():
                counts[k] += v
        for aid in out["apps"]:
            out["apps"][aid] = res.get(aid) or "deferred"
        counts["quota_stops"] += sum(gaud._int(p.get("stops")) for p in props.values())
    except Exception as e:                              # a bug here must never lose what was read
        out["error"] = type(e).__name__
    out["pushed"] = pushed()
    for v in out["apps"].values():
        if v in counts:
            counts[v] += 1
    return out


def bf_line(status):
    """The history job's ONE result line — counts only."""
    c = (status or {}).get("counts") or {}
    err = (status or {}).get("error")
    return ("devices backfill: apps %d, with GA4 %d, done %d, deferred %d, failed %d, waiting %d, days read %d, "
            "S calls %d, P calls %d, D1 calls %d, empty %d, refreshed %d, calls %d, tokens %d, quota stops %d, "
            "pushes %d, push failed %d%s" % tuple([gaud._int(c.get(k)) for k in BF_COUNTS]
                                                  + [(", error " + err) if err else ""]))


def bf_apps(data_dir, want=None):
    """The apps the Devices fetch reads (its state's app ids first, then the Uninstall fetch's), one per Play package,
    SELECTED in the dashboard (no readable catalog: every app) → [{app_id, package}]; want: lower-case tokens (12-hex
    keys, app ids or packages; empty = all)."""
    from . import ga4_screens as gs
    ust = gu.load_state(data_dir)
    dst = load_state(data_dir)
    sel = gs._selected(data_dir)
    out, seen = [], set()
    for aid in list(sorted(dst["fetch"])) + list(sorted(ust["fetch"])):
        if sel is not None and str(aid) not in sel:
            continue
        pkg = (ust["fetch"].get(aid) or {}).get("package") or (load_store(store_path(data_dir, aid)) or {}).get("package")
        if not pkg or pkg in seen:
            continue
        seen.add(pkg)
        if want and not ({gu.file_key(aid), str(aid).lower(), str(pkg).lower()} & set(want)):
            continue
        out.append({"app_id": aid, "package": pkg})
    return out


def prune_merged(staged_dir, data_dir):
    """Staged month files the hourly build has merged (their sha1 in the build's state["staged"]) are removed before a
    run (the build's store has their records; the job's next push records the removal) → files removed."""
    seen = load_state(data_dir).get("staged") or {}
    n = 0
    for key in staged_keys(staged_dir):
        for m in months_on_disk(staged_dir, key):
            p = month_path(staged_dir, key, m)
            sha = _sha1_file(p)
            if sha and seen.get(key + "/" + m) == sha:
                try:
                    os.remove(p)
                    n += 1
                except OSError:
                    pass
        try:
            meta = _read_gz(meta_path(staged_dir, key))
            if meta is not None:
                ms = meta.get("months") or {}
                left = set(months_on_disk(staged_dir, key))
                meta["months"] = {m: v for m, v in ms.items() if m in left}
                write_json_gz_stable(meta_path(staged_dir, key), meta)
        except Exception:
            pass
    return n


def main(argv=None, env=None, now=None, clock=time.monotonic):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    if "--backfill" not in argv:
        sys.exit("usage: python -m admob_iq.fetch.ga4_device --backfill")
    from . import ga4_audience_probe as ap
    from . import ga4_screens as gs
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    if not (cid and sec and (env.get("GA4_REFRESH_TOKENS") or env.get("GA4_REFRESH_TOKEN"))):
        sys.exit("GA4 client or refresh tokens missing")
    root = env.get("DEVICES_DATA_DIR") or DATA_ROOT
    data_dir, staged = os.path.join(root, "data"), os.path.join(root, BF_DIR)
    print("devices backfill: merged files removed %d" % prune_merged(staged, data_dir), flush=True)
    apps = bf_apps(data_dir, ap.wanted(ap.event_inputs(env).get("apps") or env.get("DEVICES_APPS")))
    cfg = {"client_id": cid, "client_secret": sec, "refresh_tokens": env.get("GA4_REFRESH_TOKENS") or "",
           "refresh_token": env.get("GA4_REFRESH_TOKEN") or ""}
    token = env.get("DATA_REPO_TOKEN")
    push = (lambda: gs.git_push(root, BF_DIR, token, label="devices backfill")) if token else None
    status = backfill_all(cfg, data_dir, staged, apps, now=now, clock=clock, push=push,
                          say=lambda s: print(s, flush=True))
    print(bf_line(status), flush=True)
    if push and not status.get("pushed"):
        sys.exit(1)                                     # the workflow says "failed"; details stay off the public log


if __name__ == "__main__":
    main()
