"""🖼️ Screens — the GA4 fetch behind the Screens tab (owner, 4 Nov 2026: "per app, per Activity: visits, the ad
impressions against them, the ratio … every advanced layer that needs no setup … all 28 apps, a new app tomorrow joins
automatically … as fast as possible, full data without any miss, accurate").

Per app and GA4 day, READS (each its own grain, recent_at, upto and backfill), every one stream-pinned (gf.App: platform
Android + the app's stream), one date range, dims starting with date; ad reads count ad_impression EVENTS (eventCount):
  t   the truth, 3 calls: TV date → views, engagement; TA date × adFormat → ad_impression; TE0 date → every event
  v   date × screen class → views, engagement                                   shape c          tied to TV
  w   date × adFormat × adUnitName → ad_impression (no screen)                  shape u          tied to TA (× format)
  a   ads by screen: class × format × unit / class × format / class             fu, f, c         TA (× format) / total
  nV rV cV  views by newVsReturning / appVersion / countryId × class / alone    c, a             TV
  nA rA cA  ads by that dimension × class × format / × format / alone           cf, f, a         TA (× format) / total
  k   clicks: TK date × eventName in (ad_click, ad_reward), split by class      c                TK (× event)
  e   exposure: TE date → adUnitExposure, split by class                        c                TE
  uV  sessions, users by class (not additive: flags only)                       c
  uA  users who saw ads by class / alone (not additive: flags only)             c, a
  s   ad_impression by format × ad source                                       fs               TA (× format)
  x   the app's own ad-like events: TX date × eventName in its list, by class   c                TX (× event)
      (the list: once a day, the last 28 final days' event names that look like ad events — ga4_activity_probe's
      AD_EVENT_RE, not the standard ones — top 20; a name GAINED re-reads x's history)
A day with no ad_impression in its truth costs the ad reads nothing (an empty whole record); k / e / x likewise on a
zero truth of their own.

WHOLE (counts only, revenue never read): no sampling, nothing cut, no undated row in a multi-day read (in a one-day read
it is the day's GA4 "(other)" row) and the split ties its truth per day (per format / event where the truth has one)
within max(2 %, 1): "(other)" rows are GA4's fold — state "w" (fold ≤ 0.5 %), "p" (more: rows and the fold share kept,
and the next coarser shape read beside it when over 2 % — through the same ladder and gate, a final day it is not
whole for retried on the next runs), "o" (the tie fails: silent loss, coverage kept, no rows; for the users reads, which
tie nothing, GA4's own dataLossFromOtherRow flag), "s" (sampled: GA4's sample share, no rows), "t" (thresholded users).
Never a sampled or scaled number as data.

GRAIN, per read and shape, decided by FINAL days only (≤ today − 5; today … today − 4 are re-read and never change a
grain): a multi-day read that is not whole is read again at half the days (31 → 14 → 7 → 3 → 1), two whole reads at a
size double it; a day not whole alone tries the next coarser shape — the shapes tried are saved at once, so a stop never
sends a failed read again; a shape failing 3 final days in a row is dead until 14 more days were read, then tried once;
a shape is not sent for a day whose events (TE0) are at or above what GA4 sampled at that shape before (the gate).

Store (private repo, kept for good):
    data/ga4_screens/<key>.json.gz                   meta {"v", "app_id", "package", "property_id", "stream_id",
                                                     "time_zone", "reads": {id: {"recent_at", "upto", "oldest",
                                                     "done", "top", "d", "dead", "gate", "streak", "read", "pend",
                                                     "cop" {day: [coarser shape owed, tries]}}},
                                                     "events": {"at", "names"}, "months": {grp: ["YYYY-MM", …]}}
    data/ga4_screens/<key>/recent.json.gz            {"v", "days": {day: {id: record}}} today − 4 … today (rewritten)
    data/ga4_screens/<key>/<grp>_<YYYY-MM>.json.gz   {"v", "days": {day: {id: record}}} final days; grp core = t v w
                                                     a, small = k e uV uA s x nV nA, ver = rV rA, cc = cV cA
  record {"st", "g" shape, "f" fold share (p), "cov" (o), "smp" (s), "thr", "loss", "tried", "fv", "r" rows, "co" the
  coarser shape's record (p over 2 %), "rc" (read while recent)}; t adds "v" [views, eng], "a" [[format, n]], "ev";
  k / e / x add "t" (their own truth), x "ev" (the names it read). Rows are positional and sorted (§2.7 of the spec).
A recent day turning final moves into its month file (a whole record never gives way to one that is not, a final read
never to one made while recent) and is read once more as final (the read's "upto" catches it up). A store file that is
there but cannot be read is never written over (StoreError: that app fails the run, the file stays).

Per run (the hourly build; this step runs after every other GA4 step): properties side by side (WORKERS), each app's
calls ≤ APP_CALLS, the run's clock BUDGET_SEC. Pass 1, most stale first: every due read (t v w a every 3 h, the layers
every 12 h) — its final days since "upto", then the recent window with the truth read just before — in at most 60 % of
the clock. Pass 2: the backfill, newest first by chunk across every read, the last 90 final days of every app first.
The property stops for this run (deferred, kept) under STRICTER floors than the other GA4 steps: an hourly token bucket
under 60 %, the day's under 40 %, < 60 potentially thresholded or ≤ 4 server-error requests left, or a 429.
The history job (backfill_all, .github/workflows/screens-backfill.yml) runs the same reads for the final days, 12
properties side by side for 5.5 h (access tokens renewed on the way), under floors above the other GA4 steps' 50 %: an
hourly bucket under 65 % rests the property until the next clock hour. It writes only the private repo's
ga4_screens_bf/; merge_staged copies its records in (whole ones over what is not whole; a final day's other outcome
where the build has none).
Switched by GA4_SCREENS. Never raises; never prints except log_line (counts only).
"""
import base64
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import ga4_probe
from ..db import write_json_gz_stable
from . import ga4
from . import ga4_audience as gaud
from . import ga4_firstopen as gf
from . import ga4_uninstall as gu

DIR = "ga4_screens"
BF_DIR = "ga4_screens_bf"               # the history job's own folder in the private repo (same layout as DIR)
STORE_V = 1
RECENT_DAYS = 5                         # today … today − 4: re-read on refresh (GA4 still adds to them)
FINAL_LAG = 5                           # final = today − 5 and older (written once)
CORE_HOURS = 3.0                        # t v w a: due again after this long …
LAYER_HOURS = 12.0                      # … every other read after this long
CHUNK0 = {"t": 31, "v": 31, "w": 31, "a": 14, "nV": 7, "rV": 7, "cV": 7, "nA": 7, "rA": 7, "cA": 7, "k": 31,
          "e": 31, "uV": 31, "uA": 7, "s": 31, "x": 31}
LADDER = (31, 14, 7, 3, 1)              # a read's days per call: halved down, doubled up (≤ its CHUNK0)
TIE_REL, TIE_ABS = 0.02, 1              # a split ties its truth within max(2 %, 1)
FOLD_OK = 0.005                         # fold share ≤ 0.5 %: "w"; more: "p"
FOLD_CO = 0.02                          # "p" over 2 %: the next coarser shape is read beside it
DEAD_AFTER = 3                          # final days in a row a shape failed → dead …
DEAD_RETRY = 14                         # … until this many more days were read, then tried once
TARGET_DAYS = 90                        # pass 2 fills the last 90 final days of every read of every app first
EVENTS_HOURS = 24.0                     # the x event list is read again after this long …
EVENTS_DAYS = 28                        # … over the last 28 final days …
EVENTS_MAX = 20                         # … its top 20 names
TRUTH_FRESH_SEC = 120                   # a recent split's truth is read again when older than this (same worker)
WORKERS = 6                             # properties side by side (each property: one call at a time)
BUDGET_SEC = 150                        # the run's clock (GA4_SCREENS_BUDGET_SEC)
PASS1_SHARE = 0.6                       # pass 1 (recent) stops starting reads past 60 % of it
APP_CALLS = 60                          # calls per app per run
RETRY_HOURS = 3.0                       # a failed app waits this long
PAGE_ROWS = 100000
FV = dict.fromkeys(CHUNK0, 1)           # each read's record format (a change re-reads that read only)
# quota floors — stricter than the other GA4 steps (gaud.quota_stop: 50 % hourly / 10 % daily), so this step, which
# runs after them, never takes what they need on the next build: a bucket's remaining share under its floor stops the
# property (for this run); fewer than 60 potentially thresholded / at most 4 server-error requests left too
FLOORS = {"tokensPerHour": 0.6, "tokensPerProjectPerHour": 0.6, "tokensPerDay": 0.4}
THR_MIN, ERR_MIN = 60, 4
# the history job (backfill_all): 12 properties side by side, 5.5 h; a property at a floor waits for the next hour.
# Its hourly floors sit well ABOVE the other GA4 steps' (gaud.HOUR_FLOOR 0.5): held there for hours, it still leaves
# every hourly build's Audience / First open / … reads their half of each bucket
BF_FLOORS = {"tokensPerHour": 0.65, "tokensPerProjectPerHour": 0.65, "tokensPerDay": 0.4}
BF_WORKERS = 12
BF_BUDGET_SEC = 19800
BF_APP_CALLS = 10 ** 7                  # (the clock and the floors bound it)
BF_FAIL_MAX = 5                         # errors (not quota / budget stops) an app may hit in one history run …
BF_RETRY_SEC = 180                      # … each followed by this rest of its property before the app is tried again
PUSH_SEC = 600                          # its folder is committed + pushed every 10 min, and at the end
PUSH_TRIES = 5
HEARTBEAT_SEC = 60
TOKEN_TTL_SEC = 2700                    # an owner's access token is fetched again after 45 min (Google's last about an
                                        # hour: the 5.5 h job outlives several) — and at once after a 401
TICK_SEC = 5.0
DATA_ROOT = "_private"                  # the history job's private clone (SCREENS_DATA_DIR)

SC, FMT, UNIT, SRC, EVN = "unifiedScreenClass", "adFormat", "adUnitName", "adSourceName", "eventName"
NVR, VER, CTY = "newVsReturning", "appVersion", "countryId"
IMP = "ad_impression"
CLICKS = ("ad_click", "ad_reward")
VM = ("screenPageViews", "userEngagementDuration")
EC = ("eventCount",)
FOLD = frozenset(("(other)", "other"))  # GA4's fold labels (any case)
# an app's own ad-like event — as ga4_activity_probe.AD_EVENT_RE / STD_AD_EVENTS (a test keeps them equal)
AD_EVENT_RE = re.compile(r"(?:^|_)(?:ads?|inter|interstitial|rewarded|reward|banner|native|app_?open|aoa|full_?screen)"
                         r"(?:_|$)|interstitial|rewarded|appopen|nativead|bannerad|interad|rewardad", re.I)
STD_AD_EVENTS = frozenset(("ad_impression", "ad_click", "ad_reward", "ad_exposure", "ad_query", "ad_activeview"))


def _layers():
    out = {}
    for p, dim in (("n", NVR), ("r", VER), ("c", CTY)):
        out[p + "V"] = {"shapes": (("c", (dim, SC)), ("a", (dim,))), "mets": ("screenPageViews",), "tie": "tv1"}
        out[p + "A"] = {"shapes": (("cf", (dim, SC, FMT)), ("f", (dim, FMT)), ("a", (dim,))), "mets": EC, "ev": IMP,
                        "tie": "ta"}
    return out


# id → shapes (finest first: (name, dims after date)), metrics, event filter (ev: one name, evs: a list or "@names"),
# the truth it ties ("tv": TV views + engagement, "tv1": TV views, "ta": TA, "own": its own truth read "own"; None:
# flags only)
READS = {
    "t": {"shapes": (("t", ()),), "tie": None},
    "v": {"shapes": (("c", (SC,)),), "mets": VM, "tie": "tv"},
    "w": {"shapes": (("u", (FMT, UNIT)),), "mets": EC, "ev": IMP, "tie": "ta"},
    "a": {"shapes": (("fu", (SC, FMT, UNIT)), ("f", (SC, FMT)), ("c", (SC,))), "mets": EC, "ev": IMP, "tie": "ta"},
    **_layers(),
    "k": {"shapes": (("c", (SC, EVN)),), "mets": EC, "evs": CLICKS, "tie": "own", "own": ((EVN,), EC)},
    "e": {"shapes": (("c", (SC,)),), "mets": ("adUnitExposure",), "tie": "own", "own": ((), ("adUnitExposure",))},
    "uV": {"shapes": (("c", (SC,)),), "mets": ("sessions", "activeUsers"), "tie": None},
    "uA": {"shapes": (("c", (SC,)), ("a", ())), "mets": ("activeUsers",), "ev": IMP, "tie": None},
    "s": {"shapes": (("fs", (FMT, SRC)),), "mets": EC, "ev": IMP, "tie": "ta"},
    "x": {"shapes": (("c", (SC, EVN)),), "mets": EC, "evs": "@names", "tie": "own", "own": ((EVN,), EC)},
}
ORDER = ("t", "v", "w", "a", "nV", "nA", "rV", "rA", "cV", "cA", "k", "e", "s", "x", "uV", "uA")
CORE = frozenset(("t", "v", "w", "a"))
AD_READS = frozenset(("w", "a", "nA", "rA", "cA", "uA", "s"))
GRP = {"t": "core", "v": "core", "w": "core", "a": "core", "k": "small", "e": "small", "uV": "small", "uA": "small",
       "s": "small", "x": "small", "nV": "small", "nA": "small", "rV": "ver", "rA": "ver", "cV": "cc", "cA": "cc"}
GRPS = ("core", "small", "ver", "cc")
KEY_RE = re.compile(r"[0-9a-f]{12}")
MONTH_RE = re.compile(r"(core|small|ver|cc)_(\d{4}-\d{2})\.json\.gz")
WHOLE = frozenset(("w", "p"))
STATES = {"w": "whole", "p": "partial", "o": "not_whole", "t": "not_whole", "s": "sampled"}


# ── small helpers ───────────────────────────────────────────────────────────────────────────────────────────────────
def _i(v):
    return gaud._int(v)


def _iso(d):
    return d.isoformat()


def _days(a, b):
    """Every ISO day a … b (dates), oldest first."""
    return [_iso(a + timedelta(days=i)) for i in range((b - a).days + 1)]


def _isfold(v):
    return str(v).strip().lower() in FOLD


def _tol(want):
    return max(TIE_REL * abs(want), TIE_ABS)


def _whole(rec):
    return bool(rec) and rec.get("st") in WHOLE


def body(a, b, dims, mets):
    """runReport body: [a, b], date then `dims`, `mets` (the App adds the stream and event filters and the quota)."""
    return {"dateRanges": [gu._rng(a, b)], "dimensions": ga4._dim("date", *dims), "metrics": ga4._dim(*mets),
            "keepEmptyRows": False}


def _down(n):
    """The ladder's next size under n days (1 at least)."""
    return next((x for x in LADDER if x < n), 1)


def _up(d, cap):
    """The ladder's next size over d (≤ cap; d when there is none)."""
    ups = [x for x in LADDER if d < x <= cap]
    return min(ups) if ups else d


def _gated(g, ev):
    """The volume gate: GA4 sampled this shape at ev events or fewer before, and never gave it whole at ev or more."""
    g = g or {}
    return ev is not None and g.get("bad") is not None and ev >= g["bad"] and not (ev <= (g.get("ok") or -1))


def merge_rec(old, new):
    """A (day, read) record already stored vs a new one → the one kept: a whole record never gives way to one that is
    not, and a final read never to one made while the day was recent ("rc"); otherwise the newer."""
    if not old:
        return new
    if _whole(old) and not _whole(new):
        return old
    if _whole(old) and not old.get("rc") and new.get("rc"):
        return old
    return new


def _status(rec):
    return {"st": rec.get("st"), "rc": bool(rec.get("rc")), "fv": _i(rec.get("fv")),
            "ev": frozenset(rec["ev"]) if isinstance(rec.get("ev"), list) else None}     # (x's names; t's is a count)


def _complete(s, rid, names):
    """A stored record that needs no read: made as final, of the read's format, x with every current name."""
    if not s or s["rc"] or s["fv"] < FV[rid]:
        return False
    return rid != "x" or set(names or ()) <= (s["ev"] or frozenset())


# ── files ───────────────────────────────────────────────────────────────────────────────────────────────────────────
class StoreError(Exception):
    """A store file that exists but cannot be read (damaged, cut, another format): never written over — the app ends
    "failed" for the run and the file is left as it is."""


def _read_gz(path):
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            j = json.load(f)
        return j if isinstance(j, dict) and j.get("v") == STORE_V else None
    except Exception:
        return None


def _read_or_raise(path):
    """A store file → its dict; None when there is none; StoreError when it is there but unreadable."""
    j = _read_gz(path)
    if j is None and os.path.exists(path):
        raise StoreError()
    return j


def _months_on_disk(root, key):
    """{grp: [YYYY-MM, …]} from an app's month files (a new meta beside files already there keeps finding them)."""
    out = {}
    try:
        names = sorted(os.listdir(os.path.join(root, key)))
    except OSError:
        return out
    for n in names:
        m = MONTH_RE.fullmatch(n)
        if m:
            out.setdefault(m.group(1), []).append(m.group(2))
    return out


def _sha1(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()
    except OSError:
        return None


def meta_path(root, key):
    return os.path.join(root, key + ".json.gz")


def month_path(root, key, grp, month):
    return os.path.join(root, key, "%s_%s.json.gz" % (grp, month))


def recent_path(root, key):
    return os.path.join(root, key, "recent.json.gz")


# ── loaders for the build (screens_build) ───────────────────────────────────────────────────────────────────────────
def store_keys(data_dir):
    """Every app key with a meta file in data/ga4_screens (sorted)."""
    try:
        names = os.listdir(os.path.join(data_dir, DIR))
    except OSError:
        return []
    return sorted(n[:12] for n in names if n.endswith(".json.gz") and KEY_RE.fullmatch(n[:-8]))


def load_meta(data_dir, key):
    """An app's meta ({"reads", "events", "months", …}) or None."""
    return _read_gz(meta_path(os.path.join(data_dir, DIR), key))


def iter_months(data_dir, key, grp):
    """One group's month files of an app, oldest first, one at a time → (YYYY-MM, sha1 of the file's bytes,
    {day: {read id: record}}); a missing or unreadable file is skipped (the month files on disk count too, so a meta
    that lost its "months" never hides them)."""
    root = os.path.join(data_dir, DIR)
    meta = _read_gz(meta_path(root, key)) or {}
    for m in sorted(set(((meta.get("months") or {}).get(grp)) or []) | set(_months_on_disk(root, key).get(grp) or [])):
        p = month_path(root, key, grp, m)
        sha, j = _sha1(p), _read_gz(p)
        if sha and j is not None:
            yield m, sha, j.get("days") or {}


def load_recent(data_dir, key):
    """The recent days of an app → {day: {read id: record}} ({} when none)."""
    return (_read_gz(recent_path(os.path.join(data_dir, DIR), key)) or {}).get("days") or {}


# ── the store of one app (a root: data/ga4_screens or the history job's ga4_screens_bf) ────────────────────────────
class Store:
    """One app's month files under `root` + its meta; `also`: a second Store read only (the history job: the build's
    own store, whose whole days are not read again). A month file that is there but unreadable raises StoreError
    (strict) — so put() never replaces it with only the new days; a read-only store (strict=False) sees it empty."""

    def __init__(self, root, key, meta, also=None, strict=True):
        self.root, self.key, self.meta, self.also, self.strict = root, key, meta, also, strict
        self.idx = {}                                   # (grp, month) → {day: {read id: status}}
        self.tcache = {}                                # day → its t record

    def _load(self, grp, m):
        p = month_path(self.root, self.key, grp, m)
        return ((_read_or_raise(p) if self.strict else _read_gz(p)) or {}).get("days") or {}

    def _index(self, grp, m, days=None):
        k = (grp, m)
        if days is None and k in self.idx:
            return self.idx[k]
        if days is None:
            days = self._load(grp, m)
        self.idx[k] = {d: {rid: _status(rec) for rid, rec in v.items() if isinstance(rec, dict)}
                       for d, v in days.items() if isinstance(v, dict)}
        if grp == "core":
            for d, v in days.items():
                if isinstance(v, dict) and isinstance(v.get("t"), dict):
                    self.tcache[d] = v["t"]
        return self.idx[k]

    def status(self, day, rid):
        return self._index(GRP[rid], day[:7]).get(day, {}).get(rid)

    def rec(self, day, rid):
        """The stored record of (day, read) or None (read from its month file)."""
        return (self._load(GRP[rid], day[:7]).get(day) or {}).get(rid)

    def t_rec(self, day):
        self._index("core", day[:7])
        return self.tcache.get(day)

    def put(self, recs):
        """{day: {read id: record}} → merged into the month files (merge_rec), each touched file written once →
        records changed."""
        by, n = {}, 0
        for d, v in recs.items():
            for rid, rec in v.items():
                by.setdefault((GRP[rid], d[:7]), {}).setdefault(d, {})[rid] = rec
        for (grp, m), days in sorted(by.items()):
            cur = self._load(grp, m)
            for d, v in days.items():
                day = cur.setdefault(d, {})
                for rid, rec in v.items():
                    keep = merge_rec(day.get(rid), rec)
                    if keep is not day.get(rid):
                        day[rid] = keep
                        n += 1
            write_json_gz_stable(month_path(self.root, self.key, grp, m), {"v": STORE_V, "days": cur})
            self._index(grp, m, cur)
            ms = self.meta.setdefault("months", {}).setdefault(grp, [])
            if m not in ms:
                ms.append(m)
                ms.sort()
        return n

    def save_meta(self):
        write_json_gz_stable(meta_path(self.root, self.key), self.meta)


# ── reading ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _ask(ga, b, event=None, events=None):
    """One report, every page → (rows, {"s": sampled, "smp": GA4's sample share, "trunc": cut, "thr": thresholded,
    "loss": GA4 says rows went into an "(other)" row it did not return (dataLossFromOtherRow)})."""
    rows = ga.report_all(b, event=event, events=events, page_rows=PAGE_ROWS)
    metas = [m or {} for m in (getattr(ga, "last_metas", None) or [])]
    smp = None
    for m in metas:
        for s in m.get("samplingMetadatas") or []:
            space = _i((s or {}).get("samplingSpaceSize"))
            f = _i((s or {}).get("samplesReadCount")) / float(space) if space else 0.0
            smp = f if smp is None else min(smp, f)
    rc = getattr(ga, "last_row_count", None)
    pages = getattr(ga, "last_pages", None) or 1
    return rows, {"s": smp is not None, "smp": None if smp is None else round(smp, 4),
                  "trunc": pages >= ga4.MAX_REPORT_PAGES or (rc is not None and _i(rc) > len(rows)),
                  "thr": any(bool(m.get("subjectToThresholding")) for m in metas),
                  "loss": any(bool(m.get("dataLossFromOtherRow")) for m in metas)}


def _parse(rows, dims, mets, a, b):
    """GA4 rows → ({day: [[dim values…, metric ints…]] sorted, for every day of [a, b]}, undated rows): a row with no
    real day is that day's in a one-day read (GA4's fold row there); in a longer read it is only counted."""
    one, out, und = a == b, {d: {} for d in _days(a, b)}, 0
    for r in rows:
        d = ga4._d(r.get("date"))
        if d is None:
            if not one:
                und += 1
                continue
            d = a
        day = out.get(_iso(d))
        if day is None:
            continue
        k = tuple(str(r.get(x) or "") for x in dims)
        v = day.setdefault(k, [0] * len(mets))
        for i, m in enumerate(mets):
            v[i] += _i(r.get(m))
    return {d: sorted(list(k) + v for k, v in day.items()) for d, day in out.items()}, und


def _read_t(job, a, b):
    """The truth for [a, b] (TV, TA, TE0) → ({day: record}, clean, info)."""
    ga, days = job.ga, _days(a, b)
    tv, i1 = _ask(ga, body(a, b, (), VM))
    ta, i2 = _ask(ga, body(a, b, (FMT,), EC), event=IMP)
    te, i3 = _ask(ga, body(a, b, (), EC))
    pv, u1 = _parse(tv, (), VM, a, b)
    pa, u2 = _parse(ta, (FMT,), EC, a, b)
    pe, u3 = _parse(te, (), EC, a, b)
    infos = (i1, i2, i3)
    if any(i["s"] for i in infos):
        smp = min(i["smp"] for i in infos if i["s"])
        return {d: {"st": "s", "g": "t", "smp": smp, "fv": FV["t"]} for d in days}, False, {"s": True}
    if any(i["trunc"] for i in infos) or u1 or u2 or u3:
        return {d: {"st": "o", "g": "t", "cov": None, "trunc": 1, "fv": FV["t"]} for d in days}, False, {"s": False}
    out = {}
    for d in days:
        rec = {"st": "w", "g": "t", "fv": FV["t"], "v": [sum(r[0] for r in pv[d]), sum(r[1] for r in pv[d])],
               "a": [[r[0], r[1]] for r in pa[d] if r[1]], "ev": sum(r[0] for r in pe[d])}
        if any(i["thr"] for i in infos):
            rec["thr"] = 1
        out[d] = rec
    return out, True, {"s": False}


def _own(rid, rows):
    """A k / x / e own truth's rows of a day → its stored form ([[event, n]] / exposure)."""
    if rid == "e":
        return sum(r[0] for r in rows)
    return [[r[0], r[1]] for r in rows if r[1]]


def _own_total(v):
    return v if isinstance(v, int) else sum(n for _, n in v or ())


def _empty(job, rid, shape, own=None):
    """The record of a day nothing was asked for (no ad that day / a zero own truth): whole and empty."""
    rec = {"st": "w", "g": shape, "fv": FV[rid], "r": []}
    if own is not None:
        rec["t"] = own
    if rid == "x":
        rec["ev"] = list(job.names)
    return rec


def _maps(job, rid, dims, day, own):
    """The truth a split of `rid` ties on `day` → (key column or None, [{key: value} per tied metric]) or None."""
    tie = READS[rid]["tie"]
    if tie is None:
        return None
    if tie == "own":
        if rid == "e":
            return None, [{"": own or 0}]
        m = {k: n for k, n in own or ()}
        return (dims.index(EVN), [m]) if EVN in dims else (None, [{"": sum(m.values())}])
    t = job.truth(day) or {}
    if tie == "tv":
        v = t.get("v") or [0, 0]
        return None, [{"": v[0]}, {"": v[1]}]
    if tie == "tv1":
        return None, [{"": (t.get("v") or [0])[0]}]
    m = {}
    for f, n in t.get("a") or ():
        m[f] = m.get(f, 0) + n
    return (dims.index(FMT), [m]) if FMT in dims else (None, [{"": sum(m.values())}])


def _tie(rows, ki, col, want):
    """Σ (named + fold) of a day's rows ties the truth `want` ({key: value}) on metric column `col`: the total, every
    key at most its truth, and the keys' shortfall covered by the rows whose own key is GA4's fold."""
    got, pool = {}, 0
    for r in rows:
        k = r[ki] if ki is not None else ""
        if ki is not None and _isfold(k):
            pool += r[col]
            continue
        got[k] = got.get(k, 0) + r[col]
    tw = sum(want.values())
    if abs(sum(got.values()) + pool - tw) > _tol(tw):
        return False
    short = 0
    for k in set(want) | set(got):
        w, g = want.get(k, 0), got.get(k, 0)
        if g > w + _tol(w):
            return False
        short += max(0, w - g - _tol(w))
    return short <= pool + _tol(tw)


def _judge(job, rid, shape, dims, day, rows, info, und, own):
    """One day of a split read → its record (§2.3)."""
    rec = {"g": shape, "fv": FV[rid]}
    if own is not None:
        rec["t"] = own
    if rid == "x":
        rec["ev"] = list(job.names)
    if info["s"]:
        rec.update(st="s", smp=info["smp"])
        return rec
    if info["trunc"] or und:
        rec.update(st="o", cov=None, trunc=1)
        return rec
    nd = len(dims)
    tot = sum(r[nd] for r in rows)
    fold = sum(r[nd] for r in rows if any(_isfold(v) for v in r[:nd]))
    f = fold / float(tot) if tot else 0.0
    tm = _maps(job, rid, dims, day, own)
    if tm is None:                                      # users: not additive, flags only
        if info.get("loss"):                            # rows GA4 folded away and did not return: nothing to tie
            rec.update(st="o", cov=None, loss=1)        # them to, so the day is not whole (a coarser shape next)
            return rec
        if info["thr"]:
            rec["st"] = "t"
            return rec
    else:
        if info.get("loss"):                            # the tie below finds what went missing; the flag is kept
            rec["loss"] = 1
        ki, wants = tm
        if not all(_tie(rows, ki, nd + i, w) for i, w in enumerate(wants)):
            tw = sum(wants[0].values())
            rec.update(st="o", cov=round(tot / float(tw), 4) if tw else None)
            return rec
        if info["thr"]:
            rec["thr"] = 1
    rec["st"] = "p" if (f > FOLD_OK or rec.get("thr")) else "w"
    if rec["st"] == "p":
        rec["f"] = round(f, 4)
    rec["r"] = rows
    return rec


def read_chunk(job, rid, shape, a, b):
    """One read of `rid` at `shape` for [a, b] (+ its own truth first: k / e / x) → ({day: record}, clean: no sampling,
    nothing cut, no undated row, info)."""
    if rid == "t":
        return _read_t(job, a, b)
    R, ga, days = READS[rid], job.ga, _days(a, b)
    dims = dict(R["shapes"])[shape]
    ev, evs = R.get("ev"), R.get("evs")
    if evs == "@names":
        evs = list(job.names)
    out, own, lo, hi = {}, None, a, b
    if R.get("own"):
        odims, omets = R["own"]
        orows, oi = _ask(ga, body(a, b, odims, omets), ev, evs)
        po, uo = _parse(orows, odims, omets, a, b)
        if oi["s"] or oi["trunc"] or uo or oi["loss"]:     # (an own truth that lost rows ties nothing)
            bad = ({"st": "s", "smp": oi["smp"]} if oi["s"] else
                   {"st": "o", "cov": None, "loss": 1} if oi["loss"] and not (oi["trunc"] or uo) else
                   {"st": "o", "cov": None, "trunc": 1})
            return {d: dict(bad, g=shape, fv=FV[rid]) for d in days}, False, oi
        own = {d: _own(rid, po[d]) for d in days}
        live = [d for d in days if _own_total(own[d]) > 0]
        out = {d: _empty(job, rid, shape, own[d]) for d in days if d not in live}
        if not live:
            return out, True, oi
        lo, hi = gu._d(live[0]), gu._d(live[-1])
    rows, info = _ask(ga, body(lo, hi, dims, R["mets"]), ev, evs)
    per, und = _parse(rows, dims, R["mets"], lo, hi)
    for d, rr in per.items():
        out[d] = _judge(job, rid, shape, dims, d, rr, info, und, own[d] if own is not None else None)
    return out, not (info["s"] or info["trunc"] or und), info


# ── the quota gate and the App ──────────────────────────────────────────────────────────────────────────────────────
def quota_gate(q, floors=FLOORS, thr_min=THR_MIN, err_min=ERR_MIN):
    """The property's last quota snapshot → a reason to stop it ("hour_low" / "day_low" / "count_low") or None."""
    for k, floor in floors.items():
        b = (q or {}).get(k) or {}
        if "remaining" in b:
            left = _i(b["remaining"])
            if left < floor * max(gu.QUOTA_CAP[k], _i(b.get("consumed")) + left):
                return "day_low" if k == "tokensPerDay" else "hour_low"
    for k, lo, strict in (("potentiallyThresholdedRequestsPerHour", thr_min, True),
                          ("serverErrorsPerProjectPerHour", err_min, False)):
        b = (q or {}).get(k) or {}
        if "remaining" in b and (_i(b["remaining"]) < lo if strict else _i(b["remaining"]) <= lo):
            return "count_low"
    return None


def bf_gate(q):
    return quota_gate(q, BF_FLOORS)


class Tokens:
    """Every owner's GA4 access token, shared by the threads (a lock): get(owner) → the token (None: no refresh token
    or the first fetch failed), fetched again once older than TOKEN_TTL_SEC; get(owner, bad=token) after GA4 refused
    `token` (401) → a new one (or the one another thread already fetched since)."""

    def __init__(self, cfg, refresh, clock=time.monotonic):
        self.cfg, self.refresh, self.clock = cfg, dict(refresh), clock
        self.have, self.lock = {}, threading.Lock()

    def get(self, owner, bad=None):
        with self.lock:
            tok, at = self.have.get(owner, (None, None))
            if owner in self.have:
                if bad is not None and tok != bad:
                    return tok                          # renewed by another thread meanwhile
                if bad is None and (tok is None or self.clock() - at < TOKEN_TTL_SEC):
                    return tok
            new = None
            if owner in self.refresh:
                try:
                    new = ga4.access_token(self.cfg["client_id"], self.cfg["client_secret"], self.refresh[owner])
                except Exception:
                    new = None
            self.have[owner] = (new or tok, self.clock())
            return new or tok


class App(gf.App):
    """gf.App (stream-pinned, paged) whose every call first passes the property's STRICTER gate (quota_gate), the run's
    clock and the app's call cap — raising gf.Stop — and which stops the property on a 429 / RESOURCE_EXHAUSTED
    ("quota_429": deferred, never failed). prop["stops"] counts the property's quota stops. renew (Tokens.get for the
    app's owner): the token is taken fresh before every call, and a 401 gets a new one and the call once more."""

    def __init__(self, token, property_id, stream_id, prop, over=None, max_calls=APP_CALLS, gate=quota_gate,
                 renew=None):
        super().__init__(token, property_id, stream_id, prop, over=over, max_calls=max_calls)
        self.gate, self.renew = gate, renew

    def _send(self, method, body):
        try:
            return ga4.Ga4App._post(self, method, body)
        except RuntimeError as e:
            if str(e).startswith("HTTP 429") or "RESOURCE_EXHAUSTED" in str(e):
                self._halt("quota_429")
            raise

    def _halt(self, why):
        p = self.prop
        if not p.get("stop"):
            p["stop"] = why
            p["stops"] = _i(p.get("stops")) + 1
            kinds = p.setdefault("kinds", {})
            kinds[why] = kinds.get(why, 0) + 1
        raise gf.Stop(why)

    def _post(self, method, body, measure=False):
        p = self.prop
        if p.get("stop"):
            raise gf.Stop(p["stop"])
        why = self.over() if self.over else None
        if why:
            raise gf.Stop(why)
        why = self.gate(p.get("quota")) if self.gate else None
        if why:
            self._halt(why)
        if self.calls >= self.max_calls:
            raise gf.Stop("calls")
        if self.renew:
            self.token = self.renew() or self.token
        try:
            j = self._send(method, body)
        except RuntimeError as e:
            if not (self.renew and str(e).startswith("HTTP 401")):
                raise
            self.token = self.renew(bad=self.token) or self.token     # expired / revoked: a new one, once
            j = self._send(method, body)
        q = j.get("propertyQuota")
        if q:
            p["quota"] = q
            self.tok += _i((q.get("tokensPerDay") or {}).get("consumed"))
        return j


# ── one app's run ───────────────────────────────────────────────────────────────────────────────────────────────────
class Job:
    """One app in one run: its store, the property's day, the run's counters."""

    def __init__(self, root, it, now, ga, clock=time.monotonic, also=None, bf=False):
        a, r = it["a"], it["r"]
        self.aid, self.key, self.now, self.ga, self.clock, self.bf = a["app_id"], gu.file_key(a["app_id"]), now, ga, \
            clock, bf
        self.root = root
        meta = _read_or_raise(meta_path(root, self.key))   # (an unreadable meta is never replaced by a new one)
        if meta is None:
            meta = {"v": STORE_V, "months": _months_on_disk(root, self.key)}
        meta.update(v=STORE_V, app_id=a["app_id"], package=a["package"], property_id=r["property_id"],
                    stream_id=r["stream_id"], time_zone=it["tz"])
        for k in ("reads", "events", "months"):
            if not isinstance(meta.get(k), dict):
                meta[k] = {}
        self.meta = meta
        self.store = Store(root, self.key, meta, also)
        self.today = now.astimezone(ZoneInfo(it["tz"])).date()
        self.final_end = self.today - timedelta(days=FINAL_LAG)
        self.recent_start = self.final_end + timedelta(days=1)
        self.hs = it["hs"]
        rj = None if bf else _read_gz(recent_path(root, self.key))
        self.recent = (rj or {}).get("days") or {}
        self.t_at = {}
        self.c = dict.fromkeys(("whole", "partial", "not_whole", "sampled", "gated", "dead"), 0)
        self.failed = set()
        self.did = False

    @property
    def names(self):
        return list((self.meta.get("events") or {}).get("names") or [])

    def rd(self, rid):
        rd = self.meta["reads"].setdefault(rid, {})
        for k in ("d", "dead", "gate", "streak", "pend", "cop"):
            if not isinstance(rd.get(k), dict):
                rd[k] = {}
        rd["read"] = _i(rd.get("read"))
        return rd

    def init_read(self, rid):
        """A read's backfill cursor and forward mark, set the first time (nothing filled: oldest = the day after the
        newest final day; upto = that day)."""
        rd = self.rd(rid)
        if not rd.get("oldest"):
            rd["oldest"] = _iso(self.final_end + timedelta(days=1))
            rd["top"] = _iso(self.final_end)
            rd.pop("done", None)
        if not rd.get("upto"):
            rd["upto"] = _iso(self.final_end)
        return rd

    def truth(self, day):
        if day >= _iso(self.recent_start):
            return (self.recent.get(day) or {}).get("t")
        t = self.store.t_rec(day)
        if not _whole(t) and self.store.also is not None:
            t = self.store.also.t_rec(day) or t
        return t

    def needs(self, rid, day):
        """A FINAL day `rid` must still read: no complete record here (the history job: nor a whole one in the
        build's store)."""
        if day in self.rd(rid)["pend"]:
            return True
        if _complete(self.store.status(day, rid), rid, self.names):
            return False
        if self.store.also is not None:
            s = self.store.also.status(day, rid)
            if _complete(s, rid, self.names) and s["st"] in WHOLE:
                return False
        return True

    def put(self, rid, recs, final, called=True, again=False):
        """Records of `rid` → the month files (final: merge_rec; the days' pending cascade cleared; "read" counts the
        days) or the recent file. called: they came from calls (counted by state); again: re-stored (not counted)."""
        if not recs:
            return
        if called and not again:
            for rec in recs.values():
                k = STATES.get(rec.get("st"))
                if k:
                    self.c[k] += 1
        if final:
            self.store.put({d: {rid: rec} for d, rec in recs.items()})
            rd = self.rd(rid)
            for d in recs:
                rd["pend"].pop(d, None)
            if not again:
                rd["read"] += len(recs)
            self.store.save_meta()
        else:
            for d, rec in recs.items():
                self.recent.setdefault(d, {})[rid] = rec
                if rid == "t":
                    self.t_at[d] = self.clock()
            self.save_recent()

    def save_recent(self):
        if not self.bf:
            write_json_gz_stable(recent_path(self.root, self.key), {"v": STORE_V, "days": self.recent})

    def move_recent(self):
        """Days that turned final leave the recent file for their month files (marked read-while-recent)."""
        cut = _iso(self.recent_start)
        old = {d: v for d, v in self.recent.items() if d < cut}
        if not old:
            return
        self.store.put({d: {rid: dict(rec, rc=1) for rid, rec in v.items() if rid in GRP} for d, v in old.items()})
        for d in old:
            del self.recent[d]
        self.save_recent()
        self.store.save_meta()

    def stale_truth(self, days):
        now = self.clock()
        return any(d not in self.t_at or now - self.t_at[d] > TRUTH_FRESH_SEC for d in days)


def _take(walk, d):
    """The next run of ≤ d consecutive days (walk order) off the front of `walk`."""
    chunk = [walk.pop(0)]
    step = None
    while walk and len(chunk) < d:
        diff = (gu._d(walk[0]) - gu._d(chunk[-1])).days
        if abs(diff) != 1 or (step is not None and diff != step):
            break
        step = diff
        chunk.append(walk.pop(0))
    return chunk


def _events(job, chunk):
    ev = [(job.truth(d) or {}).get("ev") for d in chunk]
    return None if any(e is None for e in ev) else sum(ev)


def ladder(job, rid, s, days, final, on_ok, on_fail, one=False):
    """`days` (walk order) of `rid` at shape `s`, in chunks of the read's size: a multi-day read not whole is read again
    at the ladder's next smaller size (its whole days kept when the read itself was clean); two whole reads at a size
    double it (final days only: a recent read never changes the grain). on_ok({day: record}) / on_fail(day, record)
    as each chunk is back."""
    rd = job.rd(rid)
    cap = CHUNK0[rid]
    d = 1 if one else min(cap, _i(rd["d"].get(s)) or cap)
    walk = list(days)
    while walk:
        chunk = _take(walk, d)
        ev = None if rid == "t" else _events(job, chunk)
        if len(chunk) > 1 and _gated(rd["gate"].get(s), ev):
            d = _down(len(chunk))                       # the volume says GA4 would sample it: fewer days a call
            walk = chunk + walk
            continue
        a, b = gu._d(min(chunk)), gu._d(max(chunk))
        recs, clean, info = read_chunk(job, rid, s, a, b)
        job.did = True
        bad = [x for x in chunk if not _whole(recs.get(x))]
        if final and ev is not None:                    # the gate learns from final reads only: sampled at ev …
            g = rd["gate"].setdefault(s, {})
            if info.get("s"):
                g["bad"] = ev if g.get("bad") is None else min(g["bad"], ev)
            elif clean and not bad:                     # … or whole at ev
                g["ok"] = max(_i(g.get("ok")), ev)
        if len(chunk) == 1 or not bad:
            ok = {x: recs[x] for x in chunk if x not in bad}
            if ok:
                on_ok(ok)
            for x in bad:
                on_fail(x, recs.get(x) or {"st": "o", "g": s, "cov": None, "fv": FV[rid]})
            if final:
                if bad:
                    rd["streak"][s] = 0
                elif len(chunk) >= d:
                    rd["streak"][s] = _i(rd["streak"].get(s)) + 1
                    if rd["streak"][s] >= 2 and d < cap:
                        d = _up(d, cap)
                        rd["d"][s] = d
                        rd["streak"][s] = 0
            continue
        keep = {x: recs[x] for x in chunk if x not in bad} if clean else {}
        if keep:
            on_ok(keep)
        d = _down(len(chunk))
        if final:
            rd["d"][s] = d
            rd["streak"][s] = 0
        walk = [x for x in chunk if x not in keep] + walk


def fill(job, rid, days, final):
    """Read `rid` for `days` (ISO, walk order: newest first in the backfill, oldest first otherwise), shape by shape,
    finest first: each day stores the first shape whole for it ("g"), the shapes it tried ("tried") — saved at once on
    a final day, so a stop never sends a failed read again — or, none whole, its last failure. Dead shapes and the
    volume gate are kept on final days and only obeyed on recent ones. Raises gf.Stop."""
    if not days:
        if final:
            _coarser(job, rid, {}, True)                # (earlier runs' coarser reads still waiting)
        return
    shapes = [s for s, _ in READS[rid]["shapes"]]
    rd = job.rd(rid)
    pend = rd["pend"] if final else {}
    todo, quiet = [], {}
    for d in days:
        if rid not in ("t", "uV"):
            t = job.truth(d)
            if not _whole(t):
                continue                                # no whole truth that day: nothing to tie (left unread)
            if rid in AD_READS and not sum(n for _, n in t.get("a") or ()):
                quiet[d] = _empty(job, rid, shapes[0])  # no ad that day: no call
                continue
        if rid == "x" and not job.names:
            quiet[d] = {"st": "w", "ev": [], "t": [], "r": [], "fv": FV[rid]}
            continue
        todo.append(d)
    job.put(rid, quiet, final, called=False)
    tried = {d: list((pend.get(d) or {}).get("tried") or []) for d in todo}
    last = {d: {k: v for k, v in pend[d].items() if k != "tried"} for d in todo if pend.get(d)}
    skipped, left, stored = {}, list(todo), {}
    for s in shapes:
        cand = [d for d in left if s not in tried[d] and (rid, s, d) not in job.failed]
        if not cand:
            continue
        dz = rd["dead"].get(s) or {}
        one = False
        if "until" in dz:                               # a dead shape: skipped — tried again on one final day once
            retry = cand[:1] if final and rd["read"] >= _i(dz["until"]) else []
            for d in cand[len(retry):]:
                skipped[d] = skipped.get(d) or ("dead", dz.get("st") or "o")
                job.c["dead"] += 1
            cand, one = retry, bool(retry)
        if rid != "t" and not one:                      # (the dead shape's one retry is sent whatever the volume)
            g, keep = rd["gate"].get(s), []
            for d in cand:
                if _gated(g, (job.truth(d) or {}).get("ev")):
                    skipped[d] = skipped.get(d) or ("gate", "s")
                    job.c["gated"] += 1
                else:
                    keep.append(d)
            cand = keep
        if not cand:
            continue

        def on_ok(recs, s=s):
            for d, rec in recs.items():
                rec["tried"] = tried[d] + [s]
                stored[d] = rec
                if d in left:
                    left.remove(d)
                if final:
                    rd["dead"].pop(s, None)             # whole on a final day: alive (again)
                    cs = _co_shape(rid, rec)
                    if cs:                              # its coarser shape is owed — saved with the record, so a
                        rd["cop"].setdefault(d, [cs, 0])  # stop before that read never loses it
            job.put(rid, recs, final)

        def on_fail(d, rec, s=s):
            tried[d].append(s)
            last[d] = rec
            job.failed.add((rid, s, d))
            if not final:
                return
            dz = rd["dead"].setdefault(s, {"n": 0})
            dz["n"] = _i(dz.get("n")) + 1
            dz["st"] = rec.get("st")
            if dz["n"] >= DEAD_AFTER:
                dz["until"] = rd["read"] + DEAD_RETRY
            pend[d] = dict(rec, tried=list(tried[d]))
            job.store.save_meta()

        ladder(job, rid, s, cand, final, on_ok, on_fail, one)
    done = {}
    for d in left:                                      # no shape whole: the last failure (or the skip) is final
        if d in last:
            rec = dict(last[d], tried=tried[d])
        else:
            why, st = skipped.get(d) or ("dead", "o")
            rec = {"st": st, "g": shapes[-1], "skip": why, "tried": tried[d], "fv": FV[rid]}
            if rid == "x":
                rec["ev"] = list(job.names)
        done[d] = rec
    job.put(rid, {d: r for d, r in done.items() if d in last}, final)
    job.put(rid, {d: r for d, r in done.items() if d not in last}, final, called=False)
    _coarser(job, rid, stored, final)


def _co_shape(rid, rec):
    """The next coarser shape a record stored "p" with more than FOLD_CO folded is owed (None: none)."""
    if rec.get("st") != "p" or (rec.get("f") or 0) <= FOLD_CO:
        return None
    shapes = [s for s, _ in READS[rid]["shapes"]]
    i = shapes.index(rec["g"]) if rec.get("g") in shapes else -1
    return shapes[i + 1] if 0 <= i < len(shapes) - 1 else None


def _co(rec):
    return {k: rec[k] for k in ("st", "g", "f", "cov", "smp", "thr", "loss", "r") if k in rec}


def _coarser(job, rid, stored, final):
    """Days stored "p" with more than FOLD_CO folded (`stored`, and on final days the read's "cop" {day: [shape,
    tries]} left by earlier runs): the next coarser shape read beside them ("co", whole numbers next to GA4's grouped
    split) through the ladder at that shape's own size and volume gate (learning from final days), unless the shape is
    dead or gated for the day. A final day whose coarser read was not whole keeps that outcome in "co" and stays in
    "cop" for the next run's retry (never twice a run, at most DEAD_AFTER tries)."""
    rd = job.rd(rid)
    cop = rd["cop"] if final else {}
    base = dict(stored)
    for d in sorted(cop):
        if d not in base:
            base[d] = job.store.rec(d, rid) or {}
    want = {}
    for d, rec in base.items():
        cs = _co_shape(rid, rec)
        if not cs or _whole(rec.get("co")) or ("co" in rec and d not in cop):
            cop.pop(d, None)                            # (nothing owed: whole beside it already, or given up)
            continue
        if d in cop and cop[d][:1] != [cs]:
            cop[d] = [cs, 0]                            # (the day's record changed shape since)
        if (rid, cs, d) in job.failed:
            continue                                    # sent this run already
        if "until" in (rd["dead"].get(cs) or {}) or _gated(rd["gate"].get(cs), (job.truth(d) or {}).get("ev")):
            cop.pop(d, None)
            continue
        want.setdefault(cs, {})[d] = rec
    for cs, recs in want.items():
        def on_ok(got, recs=recs):
            for d in got:
                cop.pop(d, None)
            job.put(rid, {d: dict(recs[d], co=_co(got[d])) for d in got}, final, again=True)

        def on_fail(d, rec, cs=cs, recs=recs):
            job.failed.add((rid, cs, d))
            n = _i((cop.get(d) or [cs, 0])[1]) + 1
            if final and n < DEAD_AFTER:
                cop[d] = [cs, n]
            else:
                cop.pop(d, None)
            job.put(rid, {d: dict(recs[d], co=_co(rec))}, final, again=True)
        ladder(job, rid, cs, sorted(recs, reverse=True), final, on_ok, on_fail)
    if final and (want or stored):
        job.store.save_meta()


# ── the passes ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _hours(rid):
    return CORE_HOURS if rid in CORE else LAYER_HOURS


def discover(job):
    """x's event list: once per EVENTS_HOURS, eventName → eventCount over the last EVENTS_DAYS final days (no filter),
    the ad-like names (not the standard ones), top EVENTS_MAX by count → meta.events {at, names}; a name GAINED resets
    x's backfill (its history is read again with the new names)."""
    ev = job.meta["events"]
    if "names" in ev and gu._hours_since(ev.get("at"), job.now) < EVENTS_HOURS:
        return
    a = job.final_end - timedelta(days=EVENTS_DAYS - 1)
    rows = job.ga.report_all({"dateRanges": [gu._rng(a, job.final_end)], "dimensions": ga4._dim(EVN),
                              "metrics": ga4._dim("eventCount"), "keepEmptyRows": False}, page_rows=PAGE_ROWS)
    job.did = True
    by = {}
    for r in rows:
        n = str(r.get(EVN) or "")
        by[n] = by.get(n, 0) + _i(r.get("eventCount"))
    like = sorted(((k, v) for k, v in by.items() if k not in STD_AD_EVENTS and AD_EVENT_RE.search(k) and v > 0),
                  key=lambda kv: (-kv[1], kv[0]))[:EVENTS_MAX]
    names = sorted(k for k, _ in like)
    # "seen": every name ever kept. A name that drops out of the top EVENTS_MAX and comes back is not new: only a name
    # never seen before resets x's history (rank churn at the cut must not re-read the whole x history every day)
    seen = set(ev.get("seen") or ev.get("names") or ())
    gained = set(names) - seen
    job.meta["events"] = {"at": gu._now_iso(job.now), "names": names, "seen": sorted(seen | set(names))}
    if gained:
        rd = job.rd("x")
        for k in ("oldest", "top", "done"):
            rd.pop(k, None)


def step_recent(job):
    """Pass 1 for one app: the days turned final move out of the recent file; every DUE read (t first whenever any is
    due) reads its final days since "upto" (oldest first) and then the recent window, its truth read just before;
    recent_at / upto set as soon as that read is stored. Raises gf.Stop."""
    job.move_recent()
    due = [rid for rid in ORDER if gu._hours_since(job.rd(rid).get("recent_at"), job.now) >= _hours(rid)]
    if not due:
        return
    discover(job)
    window = _days(job.recent_start, job.today)
    now_iso = gu._now_iso(job.now)
    for rid in ["t"] + [r for r in due if r != "t"]:
        rd = job.init_read(rid)
        start = max(gu._d(rd["upto"]) + timedelta(days=1), job.hs or job.final_end)
        gap = [d for d in _days(start, job.final_end) if job.needs(rid, d)] if start <= job.final_end else []
        fill(job, rid, gap, True)
        rd["upto"] = _iso(job.final_end)
        if rid != "t" and job.stale_truth(window):
            fill(job, "t", window, False)               # a recent split is tied to a truth read seconds before
            job.rd("t")["recent_at"] = now_iso
        fill(job, rid, window, False)
        rd["recent_at"] = now_iso
        job.store.save_meta()


def backfill(job, floor):
    """Pass 2 for one app, down to `floor` (and the history start): newest first BY CHUNK ACROSS EVERY READ — for the
    days [x − t's size + 1, x] (x: the newest day any read still lacks) t first, then each read in ORDER; days already
    complete are not read. A read's cursor ("oldest") moves once its part of the chunk is stored. Raises gf.Stop."""
    hs = job.hs or job.final_end
    floor = max(floor, hs)
    while True:
        tops = {}
        for rid in ORDER:
            rd = job.init_read(rid)
            if rd.get("done"):
                continue
            top = gu._d(rd["oldest"]) - timedelta(days=1)
            if top < hs:
                rd["done"] = True
                continue
            if top >= floor:
                tops[rid] = top
        if not tops:
            job.store.save_meta()
            return
        x = max(tops.values())
        a = max(floor, x - timedelta(days=min(CHUNK0["t"], _i(job.rd("t")["d"].get("t")) or CHUNK0["t"]) - 1))
        for rid in ORDER:
            top = tops.get(rid)
            if top is None or top < a:
                continue
            days = [d for d in reversed(_days(a, min(top, x))) if job.needs(rid, d)]
            fill(job, rid, days, True)
            rd = job.rd(rid)
            rd["oldest"] = _iso(a)
            if a <= hs:
                rd["done"] = True
            job.store.save_meta()


# ── state ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def load_state(data_dir):
    try:
        with open(os.path.join(data_dir, DIR, "state.json"), encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict) and isinstance(raw.get("fetch"), dict):
            raw.setdefault("staged", {})
            return raw
    except (OSError, ValueError):
        pass
    return {"v": 1, "fetch": {}, "staged": {}}


def save_state(data_dir, state):
    """Plain JSON, sorted keys, written only when it changed, atomic (gu.save_state's way). → True when written."""
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


# ── the history job's staged records → the build's store ────────────────────────────────────────────────────────────
def _merge_reads(meta, smeta, copied=None):
    """The history job's progress → the build's meta: a read's backfill reaches the older of the two fills when they
    touch (the staged fill's top ≥ the build's oldest − 1) and is done when either is — x's only when the job read
    every event name the build reads (a name the build GAINED reset its x: the job's older progress never undoes
    that); its grain / dead / gate come from the staged meta when the build has none; a copied day (`copied`: read id
    → days) still waiting for its coarser shape keeps waiting here ("cop")."""
    reads = meta.setdefault("reads", {})
    names = set((meta.get("events") or {}).get("names") or ())
    snames = set(((smeta or {}).get("events") or {}).get("names") or ())
    for rid, s in ((smeta or {}).get("reads") or {}).items():
        if rid not in FV or not isinstance(s, dict):
            continue
        m = reads.setdefault(rid, {})
        if s.get("oldest") and m.get("oldest") and s.get("top") and (rid != "x" or names <= snames):
            if gu._d(s["top"]) >= gu._d(m["oldest"]) - timedelta(days=1):
                m["oldest"] = min(m["oldest"], s["oldest"])
                if s.get("done"):
                    m["done"] = True
        for k in ("d", "dead", "gate"):
            if not m.get(k) and s.get(k):
                m[k] = json.loads(json.dumps(s[k]))
        scop = s.get("cop") if isinstance(s.get("cop"), dict) else {}
        for d in sorted((copied or {}).get(rid) or ()):
            if d in scop:
                if not isinstance(m.get("cop"), dict):
                    m["cop"] = {}
                m["cop"][d] = list(scop[d])
    if not (meta.get("events") or {}).get("names") and (smeta.get("events") or {}).get("names"):
        meta["events"] = dict(smeta["events"])


def merge_staged(data_dir, staged_dir, state=None):
    """Copy every (day, read) record of the history job's folder into data/ga4_screens where the store lacks it or
    holds it not whole and the staged one is whole — and a staged FINAL record that is not whole (sampled, grouped
    away, skipped) where the store has none, since the build's cursor moves past those days with the job's progress
    (a later whole read still replaces it: merge_rec); merge the reads' progress (_merge_reads). Idempotent; an
    unchanged staged file (its sha1 in state["staged"]) is not read again; a broken one is skipped and counted. →
    {"merged": whole records copied, "not_whole": records copied that are not whole, "bad": files skipped}."""
    out = {"merged": 0, "not_whole": 0, "bad": 0}
    if not staged_dir or not os.path.isdir(staged_dir):
        return out
    root = os.path.join(data_dir, DIR)
    seen = state.setdefault("staged", {}) if isinstance(state, dict) else {}
    for fn in sorted(os.listdir(staged_dir)):
        if not (fn.endswith(".json.gz") and KEY_RE.fullmatch(fn[:-8])):
            continue
        key = fn[:-8]
        try:
            smeta = _read_gz(os.path.join(staged_dir, fn))
            if smeta is None:
                out["bad"] += 1
                continue
            meta = _read_or_raise(meta_path(root, key))     # (unreadable: skipped and counted, left alone)
            if meta is None:                            # the build never read this app: its header from the job's
                meta = {k: smeta.get(k) for k in ("app_id", "package", "property_id", "stream_id", "time_zone")}
                meta.update(v=STORE_V, reads={}, events={}, months=_months_on_disk(root, key))
            store = Store(root, key, meta)
            copied = {}                                 # read id → the days copied from the job's files
            sub = os.path.join(staged_dir, key)
            files = sorted(f for f in (os.listdir(sub) if os.path.isdir(sub) else []) if MONTH_RE.fullmatch(f))
            for f in files:
                grp, m = MONTH_RE.fullmatch(f).groups()
                p, rel = os.path.join(sub, f), key + "/" + f
                sha = _sha1(p)
                if sha and seen.get(rel) == sha:
                    continue
                j = _read_gz(p)
                if j is None:
                    out["bad"] += 1
                    continue
                take, rest = {}, {}
                for d, v in (j.get("days") or {}).items():
                    for rid, rec in (v or {}).items():
                        if not (rid in GRP and GRP[rid] == grp and isinstance(rec, dict) and rec.get("st")) \
                                or rec.get("rc"):
                            continue
                        have = store.status(d, rid)
                        if _whole(rec) and not _whole_status(have):
                            take.setdefault(d, {})[rid] = rec
                        elif not _whole(rec) and not have:     # the day's final outcome (sampled / grouped away /
                            rest.setdefault(d, {})[rid] = rec  # skipped): the page says so; the build's cursor is
                out["merged"] += store.put(take) if take else 0        # past it and would never read it itself
                out["not_whole"] += store.put(rest) if rest else 0
                for d, v in list(take.items()) + list(rest.items()):
                    for rid in v:
                        copied.setdefault(rid, set()).add(d)
                seen[rel] = sha
            _merge_reads(meta, smeta, copied)
            store.save_meta()
        except Exception:
            out["bad"] += 1
    return out


def _whole_status(s):
    return bool(s) and s["st"] in WHOLE


# ── the runs ────────────────────────────────────────────────────────────────────────────────────────────────────────
COUNTS = ("selected", "with_ga4", "fetched", "fresh", "failed", "deferred", "waiting", "calls", "tokens", "whole",
          "partial", "not_whole", "sampled", "gated", "dead", "quota_stops", "merged", "merged_nw", "staged_bad")


def _select(cfg, data_dir, apps, now, state, counts, out, retry=True, clock=time.monotonic):
    """The apps with a GA4 stream and an Uninstall history → {property id: [item]} (tokens resolved here, before any
    thread; item["renew"]: the owner's shared Tokens.get, which keeps it fresh); waiting / failed apps go straight to
    out["apps"]."""
    ust = gu.load_state(data_dir)
    routes = ust["routes"].get("by_package") or {}
    tokens, _ = ga4_probe.owner_tokens({"GA4_REFRESH_TOKENS": cfg.get("refresh_tokens") or "",
                                        "GA4_REFRESH_TOKEN": cfg.get("refresh_token") or ""})
    toks, by_prop = Tokens(cfg, tokens, clock), {}
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
        if retry and st.get("fail") and gu._hours_since(st.get("last_try"), now) < RETRY_HOURS:
            out["apps"][aid] = "failed"
            continue
        owner = r.get("owner")
        by_prop.setdefault(str(r["property_id"]), []).append(
            {"a": a, "st": st, "r": r, "hs": gu._d(um["history_start"]), "tz": ust["tz"].get(r["property_id"]) or
             ust["tz"].get(str(r["property_id"])) or "UTC", "tok": toks.get(owner),
             "renew": lambda bad=None, o=owner: toks.get(o, bad)})
    return by_prop


def _kinds(props):
    """Every property's quota stops by kind (hour_low / day_low / count_low / quota_429) → {kind: n} (never printed)."""
    out = {}
    for p in props.values():
        for k, n in (p.get("kinds") or {}).items():
            out[k] = out.get(k, 0) + n
    return out


def _stale(it):
    """Pass 1 order: the app whose oldest read refresh is oldest first (never read: first of all)."""
    return min(((it.get("meta_reads") or {}).get(rid) or {}).get("recent_at") or "" for rid in ORDER)


def refresh_all(cfg, data_dir, apps, now=None, clock=time.monotonic, budget=BUDGET_SEC, workers=WORKERS,
                staged_dir=None):
    """Every selected app (uninstall_build's list) → {"counts", "apps": {app id: fetched|fresh|failed|deferred|
    waiting}}: the history job's staged records merged first, then pass 1 (the recent windows, ≤ PASS1_SHARE of the
    clock) and pass 2 (the backfill: the last TARGET_DAYS of every app, then older), properties side by side. Never
    raises; never prints."""
    now = now or datetime.now(timezone.utc)
    t0 = clock()
    counts = dict.fromkeys(COUNTS, 0)
    out = {"counts": counts, "apps": {}}
    lock = threading.Lock()
    root = os.path.join(data_dir, DIR)
    try:
        state = load_state(data_dir)
        if staged_dir:
            mg = merge_staged(data_dir, staged_dir, state)
            counts["merged"], counts["merged_nw"], counts["staged_bad"] = mg["merged"], mg["not_whole"], mg["bad"]
        t0 = clock()                                    # the merge is not GA4 time: the passes' clock starts here (a
        by_prop = _select(cfg, data_dir, apps, now, state, counts, out, clock=clock)   # long first merge never eats it)
        now_iso = gu._now_iso(now)
        props = {pid: {"quota": None, "stop": None, "stops": 0} for pid in by_prop}
        jobs, res = {}, {}

        def over1():
            return "budget" if clock() - t0 >= budget * PASS1_SHARE else None

        def over2():
            return "budget" if clock() - t0 >= budget else None

        def run(pid, it, what, over):
            aid = it["a"]["app_id"]
            if res.get(aid) == "failed":
                return
            if not it["tok"]:
                with lock:
                    res[aid] = "failed"
                    it["st"].update(last_try=now_iso, fail="auth")
                return
            try:
                job = jobs.get(aid)
                if job is None:
                    ga = App(it["tok"], pid, it["r"]["stream_id"], props[pid], over=over, max_calls=APP_CALLS,
                             renew=it.get("renew"))
                    job = jobs[aid] = Job(root, it, now, ga, clock)
                job.ga.over = over
                if what == "recent":
                    step_recent(job)
                else:
                    with lock:
                        it["st"]["turn"] = now_iso      # it had its turn (a cut-off app goes last next time too)
                    backfill(job, (job.final_end - timedelta(days=TARGET_DAYS - 1)) if what == "A" else
                             (job.hs or job.final_end))
            except gf.Stop:
                with lock:
                    res[aid] = "deferred"
            except Exception as e:
                with lock:
                    res[aid] = "failed"
                    it["st"].update(last_try=now_iso, fail=gu._fail_kind(e))
            finally:
                job = jobs.get(aid)
                if job is not None:
                    try:
                        job.store.save_meta()
                    except Exception:
                        pass

        def pass_(what, over, key):
            order = sorted(by_prop, key=lambda p: (min(key(t) for t in by_prop[p]), p))

            def one_prop(pid):
                for it in sorted(by_prop[pid], key=lambda t: (key(t), t["a"]["app_id"])):
                    run(pid, it, what, over)
            with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
                list(ex.map(one_prop, order))

        for xs in by_prop.values():
            for it in xs:
                it["meta_reads"] = (_read_gz(meta_path(root, gu.file_key(it["a"]["app_id"]))) or {}).get("reads")
        pass_("recent", over1, _stale)
        pass_("A", over2, lambda t: t["st"].get("turn") or "")
        pass_("B", over2, lambda t: t["st"].get("turn") or "")
        for xs in by_prop.values():
            for it in xs:
                aid, st = it["a"]["app_id"], it["st"]
                job = jobs.get(aid)
                r = res.get(aid) or ("fetched" if job is not None and job.did else "fresh")
                if r == "deferred":
                    st["deferred"] = True
                elif r != "failed":
                    st.pop("deferred", None)
                    st.update(last_try=now_iso, fail=None)
                    if r == "fetched":
                        st["last_ok"] = now_iso
                st["key"] = gu.file_key(aid)
                out["apps"][aid] = r
                if job is not None:
                    counts["calls"] += job.ga.calls
                    counts["tokens"] += job.ga.tok
                    for k, v in job.c.items():
                        counts[k] += v
        counts["quota_stops"] += sum(_i(p.get("stops")) for p in props.values())
        out["stops"] = _kinds(props)
        save_state(data_dir, state)
    except Exception as e:                              # a bug here must never cost the build
        out["error"] = type(e).__name__
    for v in out["apps"].values():
        if v in counts:
            counts[v] += 1
    return out


def log_line(status):
    """The build log's line for this step — counts only (and, after an internal error, the health line too)."""
    c = (status or {}).get("counts") or {}
    err = (status or {}).get("error")
    line = ("ga4 screens: apps %d, with GA4 %d, fetched %d, fresh %d, failed %d, deferred %d, waiting %d, calls %d, "
            "tokens %d, whole %d, partial %d, not whole %d, sampled %d, gated %d, dead %d, quota stops %d, merged %d%s%s"
            % tuple([_i(c.get(k)) for k in ("selected", "with_ga4", "fetched", "fresh", "failed", "deferred",
                                              "waiting", "calls", "tokens", "whole", "partial", "not_whole",
                                              "sampled", "gated", "dead", "quota_stops", "merged")]
                    + [(", staged bad %d" % _i(c.get("staged_bad"))) if _i(c.get("staged_bad")) else "",
                       (", error " + err) if err else ""]))
    return line + ("\n" + "ga4 screens skipped: %s" % err if err else "")


# ── the history job (python -m admob_iq.fetch.ga4_screens --backfill) ──────────────────────────────────────────────
BF_COUNTS = ("selected", "with_ga4", "done", "deferred", "failed", "waiting", "calls", "tokens", "whole", "partial",
             "not_whole", "sampled", "gated", "dead", "quota_stops", "pushes", "push_failed")


def _bf_job(staged_dir, data_dir, it, now, ga, clock):
    """An app's job in the history job: its staged meta (or a new one from the build's progress), the build's store
    beside it (read only). A read starts at the newest final day — or where the build's own fill already reaches,
    when that fill touches it."""
    main_root = os.path.join(data_dir, DIR)
    key = gu.file_key(it["a"]["app_id"])
    mmeta = _read_gz(meta_path(main_root, key)) or {}
    also = Store(main_root, key, mmeta, strict=False)   # (read only: a damaged build file is only read again)
    job = Job(staged_dir, it, now, ga, clock, also=also, bf=True)
    if not (job.meta["events"] or {}).get("names") and (mmeta.get("events") or {}).get("names"):
        job.meta["events"] = dict(mmeta["events"])
    for rid in ORDER:
        rd = job.init_read(rid)
        m = (mmeta.get("reads") or {}).get(rid) or {}
        for k in ("d", "dead", "gate", "streak"):
            if not rd.get(k) and isinstance(m.get(k), dict) and m[k]:
                rd[k] = json.loads(json.dumps(m[k]))
        rd["read"] = max(rd["read"], _i(m.get("read")))
        if rid == "x" and not set(job.names) <= set((mmeta.get("events") or {}).get("names") or ()):
            continue                                    # the build's x fill lacks a name this job reads
        if m.get("oldest") and m["oldest"] < rd["oldest"] and m.get("upto") \
                and gu._d(m["upto"]) >= gu._d(rd["oldest"]) - timedelta(days=1):
            rd["oldest"] = m["oldest"]                  # the build's fill touches ours: go on below it
            if m.get("done"):
                rd["done"] = True
    return job


def _next_hour(t):
    return t.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def _bf_note(job, state, why, typ, prop, at):
    """The history job's last word on an app, kept in its staged meta ("bf") so a stalled app can be read from the
    private repo while the job still runs: what happened (done A/B, paused, stopped, error), why (a quota floor, a
    fail kind), the exception TYPE only, how often each happened, and the property's hourly buckets' remaining share."""
    if job is None:
        return
    try:
        b = job.meta.setdefault("bf", {})
        b.update(at=gu._now_iso(at), state=state)
        b["why"], b["type"] = why, typ
        n = b.setdefault("n", {})
        n[state] = _i(n.get(state)) + 1
        q = (prop or {}).get("quota") or {}
        b["q"] = {k: round(_i((q.get(k) or {}).get("remaining")) / float(max(cap, _i((q.get(k) or {}).get("consumed")) +
                                                                               _i((q.get(k) or {}).get("remaining")))), 3)
                  for k, cap in (("tokensPerHour", 40000), ("tokensPerProjectPerHour", 14000), ("tokensPerDay", 200000))
                  if isinstance(q.get(k), dict)}
    except Exception:
        pass


def backfill_all(cfg, data_dir, staged_dir, apps, now=None, clock=time.monotonic, budget=BF_BUDGET_SEC,
                 workers=BF_WORKERS, push=None, push_sec=PUSH_SEC, say=None, wall=None, sleep=time.sleep,
                 tick=TICK_SEC):
    """The history in one go: the same reads, shapes, checks, grain, gates and store format as refresh_all, for FINAL
    days only (pass 2's order: the last TARGET_DAYS of every app first, then older), into `staged_dir` only. Properties
    side by side (`workers`); a property at the job's floors (BF_FLOORS) or a 429 waits for the next clock hour while
    the threads go on with the others. push() (commit + push of the folder) every push_sec and at the end; say() a
    counts-only heartbeat. → {"counts", "apps"}. Never raises."""
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
            return
        try:
            ok = bool(push())
        except Exception:
            ok = False
        counts["pushes" if ok else "push_failed"] += 1
        return ok

    try:
        state = load_state(data_dir)
        by_prop = _select(cfg, data_dir, apps, now, state, counts, out, retry=False, clock=clock)
        for xs in by_prop.values():
            for it in xs:
                out["apps"][it["a"]["app_id"]] = "deferred"
        props = {pid: {"quota": None, "stop": None, "stops": 0} for pid in by_prop}
        order = sorted(by_prop, key=lambda p: (min(t["st"].get("turn") or "" for t in by_prop[p]), p))
        work = [("A", p) for p in order] + [("B", p) for p in order]
        paused, busy, jobs, res, fails = {}, set(), {}, {}, {}

        def take():
            """The next runnable (phase, property): A of every property before B where it can; None + seconds to
            wait (None: nothing left)."""
            with lock:
                if not work:
                    return None, None
                t = wall()
                for i, (ph, pid) in enumerate(work):
                    if pid in busy or (pid in paused and t < paused[pid]):
                        continue
                    if ph == "B" and ("A", pid) in work:
                        continue
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
                with lock:                              # (res / jobs are read by the heartbeat: every write locked)
                    if res.get(aid) in ("failed", "done"):
                        continue
                    if not it["tok"]:
                        res[aid] = "failed"
                        continue
                try:
                    job = jobs.get(aid)
                    if job is None:
                        ga = App(it["tok"], pid, it["r"]["stream_id"], prop, over=over, max_calls=BF_APP_CALLS,
                                 gate=bf_gate, renew=it.get("renew"))
                        job = _bf_job(staged_dir, data_dir, it, now, ga, clock)
                        with lock:
                            jobs[aid] = job
                    discover(job)                       # (once a day; a stop before it is caught up here)
                    backfill(job, (job.final_end - timedelta(days=TARGET_DAYS - 1)) if ph == "A" else
                             (job.hs or job.final_end))
                    _bf_note(job, "done " + ph, None, None, prop, wall())
                    if ph == "B":
                        with lock:
                            res[aid] = "done"
                except gf.Stop as e:
                    _bf_note(jobs.get(aid), "paused" if prop.get("stop") else "stopped",
                             prop.get("stop") or (e.args or [""])[0], None, prop, wall())
                    if prop.get("stop"):
                        return "paused"
                    if (e.args or [""])[0] == "budget":
                        return "budget"
                except Exception as e:                  # a 5xx after ga4._call's one retry, a timeout, a dropped
                    _bf_note(jobs.get(aid), "error", gu._fail_kind(e), type(e).__name__, prop, wall())
                    with lock:                          # connection: the property rests BF_RETRY_SEC and the app is
                        fails[aid] = fails.get(aid, 0) + 1   # tried again (progress is saved per chunk); "failed" only
                        if fails[aid] >= BF_FAIL_MAX:   # after BF_FAIL_MAX errors in this run
                            res[aid] = "failed"
                        else:
                            return "retry"
                finally:
                    job = jobs.get(aid)
                    if job is not None:
                        try:
                            job.store.save_meta()
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
                        return                          # every property left waits past the job's clock
                    sleep(min(max(wait_s, 0.5), 60.0))
                    continue
                ph, pid = got
                r = run_prop(ph, pid)
                with lock:
                    busy.discard(pid)
                    if r == "paused":
                        paused[pid] = _next_hour(wall())
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
                    pushed()                            # (never raises)
                    last_push = clock()
                if say and clock() - last_beat >= HEARTBEAT_SEC:
                    try:                                # a heartbeat bug never stops the pushes
                        with lock:
                            calls = sum(j.ga.calls for j in list(jobs.values()))
                            n = sum(1 for v in list(res.values()) if v == "done")
                        say("screens backfill progress: apps %d/%d, calls %d, %ds" % (n, n_all, calls,
                                                                                       int(clock() - t0)))
                    except Exception:
                        pass
                    last_beat = clock()
                if not running:
                    break
        for aid, job in jobs.items():
            counts["calls"] += job.ga.calls
            counts["tokens"] += job.ga.tok
            for k, v in job.c.items():
                counts[k] += v
        for aid in out["apps"]:
            out["apps"][aid] = res.get(aid) or "deferred"
        counts["quota_stops"] += sum(_i(p.get("stops")) for p in props.values())
        out["stops"] = _kinds(props)
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
    return ("ga4 screens backfill: apps %d, with GA4 %d, done %d, deferred %d, failed %d, waiting %d, calls %d, "
            "tokens %d, whole %d, partial %d, not whole %d, sampled %d, gated %d, dead %d, quota stops %d, pushes %d, "
            "push failed %d%s" % tuple([_i(c.get(k)) for k in BF_COUNTS] + [(", error " + err) if err else ""]))


def bf_apps(data_dir, want=None):
    """The apps the build's Screens fetch reads (its state's app ids first, then the Uninstall fetch's), one per Play
    package → [{app_id, package}]; want: lower-case tokens (12-hex keys, app ids or packages; empty = all)."""
    ust = gu.load_state(data_dir)
    sst = load_state(data_dir)
    out, seen = [], set()
    for aid in list(sorted(sst["fetch"])) + list(sorted(ust["fetch"])):
        pkg = ((ust["fetch"].get(aid) or {}).get("package")
               or (_read_gz(meta_path(os.path.join(data_dir, DIR), gu.file_key(aid))) or {}).get("package"))
        if not pkg or pkg in seen:
            continue
        seen.add(pkg)
        if want and not ({gu.file_key(aid), str(aid).lower(), str(pkg).lower()} & set(want)):
            continue
        out.append({"app_id": aid, "package": pkg})
    return out


def git_push(repo, sub, token, tries=PUSH_TRIES, run=subprocess.run, pause=ga4._sleep):
    """Commit the private clone's `sub` folder ONLY, on top of the remote's newest main (fetch; the index reset to it;
    the folder added; commit; push — again on a race, `tries` times) → True when the remote has it. The token rides an
    http.extraheader for each command only (never a URL, a file or .git/config); git's output is discarded."""
    auth = base64.b64encode(("x-access-token:%s" % token).encode("utf-8")).decode("ascii")
    hdr = ["-c", "http.extraheader=AUTHORIZATION: basic " + auth]
    who = ["-c", "user.name=admob-iq-bot", "-c", "user.email=admob-iq-bot@users.noreply.github.com"]

    def git(*args, net=False):
        try:
            return run(["git"] + (hdr if net else []) + who + ["-C", repo] + list(args), stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=600).returncode
        except Exception:
            return 1
    for i in range(tries):
        if i:
            pause(5.0 * i)
        if git("fetch", "-q", "--depth=1", "origin", "main", net=True) or git("reset", "-q", "origin/main"):
            continue
        git("add", "-A", "--", sub)
        if git("diff", "--cached", "--quiet") == 0:
            return True                                 # nothing new since the last push
        if git("commit", "-q", "-m", "screens backfill %s UTC" % time.strftime("%Y-%m-%d %H:%M", time.gmtime())):
            continue
        if git("push", "-q", "origin", "HEAD:main", net=True) == 0:
            return True
    return False


def main(argv=None, env=None, now=None, clock=time.monotonic):
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    if "--backfill" not in argv:
        sys.exit("usage: python -m admob_iq.fetch.ga4_screens --backfill")
    from . import ga4_audience_probe as ap
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    if not (cid and sec and (env.get("GA4_REFRESH_TOKENS") or env.get("GA4_REFRESH_TOKEN"))):
        sys.exit("GA4 client or refresh tokens missing")
    root = env.get("SCREENS_DATA_DIR") or DATA_ROOT
    data_dir, staged = os.path.join(root, "data"), os.path.join(root, BF_DIR)
    apps = bf_apps(data_dir, ap.wanted(ap.event_inputs(env).get("apps") or env.get("SCREENS_APPS")))
    cfg = {"client_id": cid, "client_secret": sec, "refresh_tokens": env.get("GA4_REFRESH_TOKENS") or "",
           "refresh_token": env.get("GA4_REFRESH_TOKEN") or ""}
    token = env.get("DATA_REPO_TOKEN")
    push = (lambda: git_push(root, BF_DIR, token)) if token else None
    status = backfill_all(cfg, data_dir, staged, apps, now=now, clock=clock, push=push,
                          say=lambda s: print(s, flush=True))
    print(bf_line(status), flush=True)
    if push and not status.get("pushed"):
        sys.exit(1)                                     # the workflow says "failed"; details stay off the public log


if __name__ == "__main__":
    main()
