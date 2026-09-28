"""Google Ads cost and downloads BY COUNTRY for the 💸 Install value tab (SPEC_CD_GEO §G; GADS_GEO, default off).

The ROAS step of build_static calls geo_step(...) right after the spend cache is written, in its own try (a failure
costs only this cache's update and prints "gads geo skipped: <ExcName>"). READ-ONLY against Google Ads: the three
google_ads helpers (_app_geo_spend_for = Q-G1 cost, _app_geo_installs_for = Q-G2 DOWNLOAD conversions, _geo_iso =
Q-G3 criterion id → ISO-2), the MCC roster (currencies) and nothing else.

What is asked, and when (each build while GADS_GEO is on)
  1. Refresh — at most once per GEO_EVERY_SEC (~20 h): the Monday 9 weeks before the week of today − 1 .. today − 1
     (9 whole weeks + the current part-week), in pieces of ≤ 28 days starting on a Monday, newest first. A piece a
     build could not reach (the call / time budget) is done by the next build (`rpart`).
  2. Backfill, newest → oldest, 28-day chunks (4 whole weeks), ≤ GEO_BACKFILL_CHUNKS asked per build, to
     today − GEO_KEEP_DAYS or the spend cache's first day; it also stops at the data edge (GEO_EDGE_CHUNKS chunks in
     a row with no cost row although their stores had spend).
  Accounts: only those owning a campaign of a store WITH SPEND in the chunk's dates (the spend cache after
  apply_campaign_accounts). An account answering HTTP 403 (CUSTOMER_NOT_ENABLED …) costs one call and is skipped for
  GEO_SKIP_DAYS; an account no longer under the MCC costs none. GEO_WORKERS accounts in parallel, one request at a
  time per account (Q-G1, then Q-G2). Stops starting requests at GEO_MAX_SEC / GEO_MAX_CALLS, and at once on a quota
  error (HTTP 429 / RESOURCE_EXHAUSTED / quotaError) — the developer token's quota is the hourly spend fetch's too.

Commit rules (per chunk, all or nothing): a chunk is written only when every account asked answered Q-G1 (or 403).
Whole weeks are replaced for every store of the answered accounts; a skipped account's stores keep their weeks.
Q-G2 failed while Q-G1 worked → the cost is kept, dl is null (unknown, never 0) for that account's stores.

Money: base-currency micros (the spend cache's currency_src, "ccy"); an account billed in another currency goes
ccy → USD → base with google_ads._fx_to_usd, as google_ads._aggregate does. USD happens later, per install week, in
value_build._app_geo.

Files (data/, the private repo; write_json_gz_stable: deterministic, only on change):
  roas_geo_cache.json.gz      hot: the cursor fields, iso, skip, and the weeks from the first of the month of the
                              newest week − (GEO_HOT_WEEKS − 1) weeks on (13–17 weeks)
  roas_geo_cache.old.json.gz  {"v", "ccy", "weeks"}: the older weeks, moved a whole calendar month at a time
  {"v": 1, "ccy": "INR", "first", "till", "bfrom", "done", "edge", "_ts", "fails", "iso": {ccid: "US" | null},
   "iso_at", "skip": {account: until}, "rpart": null | {"end", "done": [piece Mondays]}, "erun", "bfails",
   "weeks": {store: {Monday: {cc: [cost_micros, dl | null]}}}}  (+ the hot file's "cut": weeks before that day live
  in .old, null without one — a hot file naming a cut whose .old is gone refills those weeks by backfill)
  cost_micros: int base-currency micros, rounded to GEO_MICROS_Q (the currency's 1/100 unit); dl: DOWNLOAD conversions,
  2 decimals, null = unknown (Q-G2 failed), never 0 for unknown.
  "XX" = Other / unmapped (Google Ads) — counted in totals, never judged. A cell with cost 0 and dl 0 is left out;
  weeks[store][W] exists (maybe {}) for every committed store-week ("committed, nothing spent" ≠ "never fetched").

load_geo(data_dir) is the read API (value_build's prepass): both files merged, or None.

PUBLIC LOG: geo_step returns ONE counts-only line (no ids, names, dates, money, country codes or ratios).
"""

import gzip
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from ..db import write_json_gz_stable
from . import google_ads as gads

GEO_V = 1
GEO_CHUNK_DAYS = 28                 # a backfill chunk / refresh piece: 4 whole weeks
GEO_REFETCH_WEEKS = 9               # the refresh: 9 whole weeks + the current part-week (conversions are credited back
                                    # to the click day for up to the action's 30-day lookback; cost restates in weeks)
GEO_EVERY_SEC = 20 * 3600           # the refresh: at most once a ~day
GEO_KEEP_DAYS = 400                 # the backfill goes this far back (the geo_cost replay's history)
GEO_BACKFILL_CHUNKS = 2             # backfill chunks asked per build
GEO_HOT_WEEKS = 13                  # newest weeks always in the hot file
GEO_WORKERS = 4                     # accounts in parallel — one request at a time per account
GEO_MAX_SEC = 150                   # no new request after this many seconds of the step
GEO_MAX_CALLS = 160                 # Google Ads requests per build
GEO_SKIP_DAYS = 7                   # an account answering HTTP 403 is not asked again for this long
GEO_ISO_DAYS = 30                   # the Country list is asked again after this long (and null ids with it)
GEO_FAIL_BACKOFF = 3                # failed refreshes (and backfill chunks) in a row before waiting ~a day
GEO_EDGE_CHUNKS = 2                 # empty backfill chunks in a row (their stores had spend) = the data edge
UNMAPPED = "XX"                     # "Other / unmapped (Google Ads)"
GEO_MICROS_Q = 10_000               # a cell's cost keeps the currency's 1/100 unit (paise / cents): ~20% smaller
                                    # files, at most half a paisa per country-week (coverage moves < 0.1%)
ISO_RESERVE = 2                     # calls kept free in a chunk for the by-id country map (id, then parents)
HOT_FILE = "roas_geo_cache.json.gz"
OLD_FILE = "roas_geo_cache.old.json.gz"
Q_ROSTER = "SELECT customer_client.id, customer_client.currency_code, customer_client.manager FROM customer_client"
DEFAULTS = {"first": None, "till": None, "bfrom": None, "done": False, "edge": None, "_ts": 0, "fails": 0,
            "iso": {}, "iso_at": None, "skip": {}, "rpart": None, "erun": 0, "bfails": 0}


# ── dates ─────────────────────────────────────────────────────────────────────────────────────────

def _d(s):
    return s if isinstance(s, date) else date.fromisoformat(str(s)[:10])


def _mon(d):
    d = _d(d)
    return d - timedelta(days=d.weekday())


def mondays(a, b):
    """Every Monday key of [a, b] (a is a Monday)."""
    a, b = _d(a), _d(b)
    out = []
    while a <= b:
        out.append(a.isoformat())
        a += timedelta(days=7)
    return out


def refresh_pieces(today):
    """The refresh's pieces, newest first: [(first, last)], each ≤ GEO_CHUNK_DAYS and starting on a Monday, from the
    Monday GEO_REFETCH_WEEKS weeks before the week of today − 1, to today − 1."""
    end = _d(today) - timedelta(days=1)
    a = _mon(end) - timedelta(weeks=GEO_REFETCH_WEEKS)
    out = []
    while a <= end:
        out.append((a, min(a + timedelta(days=GEO_CHUNK_DAYS - 1), end)))
        a += timedelta(days=GEO_CHUNK_DAYS)
    return out[::-1]


def cell_cost(micros):
    """A week-country cell's cost as stored: int base-currency micros rounded to GEO_MICROS_Q."""
    return int(round(micros / GEO_MICROS_Q)) * GEO_MICROS_Q


# ── the files ─────────────────────────────────────────────────────────────────────────────────────

def paths(data_dir):
    return os.path.join(data_dir, HOT_FILE), os.path.join(data_dir, OLD_FILE)


def _read(path):
    try:
        with gzip.open(path, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    except Exception:
        return None


def fresh(ccy):
    """A new, empty cache in the base currency `ccy`."""
    c = {"v": GEO_V, "ccy": ccy, "weeks": {}}
    c.update(json.loads(json.dumps(DEFAULTS)))
    return c


def _load(data_dir):
    """→ (cache | None, old): old ∈ {"ok", "none", "bad"} ("bad": the hot file says it has an .old part (its "cut")
    but that part is missing, can't be read or is of another version / currency — its weeks are left out)."""
    hp, op = paths(data_dir)
    hot = _read(hp)
    if not isinstance(hot, dict) or hot.get("v") != GEO_V or not isinstance(hot.get("weeks"), dict):
        return None, "none"
    c = {k: v for k, v in hot.items() if k not in ("weeks", "cut")}
    for k, v in DEFAULTS.items():
        c.setdefault(k, json.loads(json.dumps(v)))
    c["weeks"] = {sid: dict(ws) for sid, ws in hot["weeks"].items() if isinstance(ws, dict)}
    if not os.path.exists(op):
        return c, "bad" if hot.get("cut") else "none"
    old = _read(op)
    if not isinstance(old, dict) or old.get("v") != GEO_V or old.get("ccy") != hot.get("ccy") \
            or not isinstance(old.get("weeks"), dict):
        return c, "bad"
    for sid, ws in old["weeks"].items():
        if isinstance(ws, dict):
            dst = c["weeks"].setdefault(sid, {})
            for w, cells in ws.items():
                dst.setdefault(w, cells)
    return c, "ok"


def load_geo(data_dir):
    """The Google Ads country cache, hot + .old merged → dict (the module doc's format), or None: no hot file, or of
    another version. An .old part of another currency / unreadable is left out (its weeks read as never fetched)."""
    return _load(data_dir)[0]


def _cut(cache):
    """Weeks with a Monday before this go to .old: the first of the month of the newest week − (GEO_HOT_WEEKS − 1)
    weeks — so .old changes about once a month (plus while the backfill fills it)."""
    ws = [w for sw in cache["weeks"].values() for w in sw]
    if not ws:
        return None
    return (_d(max(ws)) - timedelta(weeks=GEO_HOT_WEEKS - 1)).replace(day=1).isoformat()


def save_geo(data_dir, cache):
    """Both files (deterministic, only on change); no old week → no .old file. → True when anything was written."""
    hp, op = paths(data_dir)
    cut = _cut(cache)
    hot = {k: v for k, v in cache.items() if k not in ("weeks", "cut")}
    hot["weeks"], oldw = {}, {}
    for sid, ws in cache["weeks"].items():
        h = {w: v for w, v in ws.items() if cut is None or w >= cut}
        o = {w: v for w, v in ws.items() if cut is not None and w < cut}
        if h:
            hot["weeks"][sid] = h
        if o:
            oldw[sid] = o
    hot["cut"] = cut if oldw else None                  # "this cache has an .old part" (a lost one is refilled)
    wrote = False
    if oldw:
        wrote = write_json_gz_stable(op, {"v": cache.get("v", GEO_V), "ccy": cache.get("ccy"), "weeks": oldw})
    elif os.path.exists(op):
        os.remove(op)
        wrote = True
    return write_json_gz_stable(hp, hot) or wrote


# ── one build's run: budget, calls, stop ─────────────────────────────────────────────────────────

class _Stop(Exception):
    """No further Google Ads request this build (time, calls or a quota error)."""


def _is403(e):
    return str(e).startswith("HTTP 403")


def _is_quota(e):
    s = str(e)
    return s.startswith("HTTP 429") or "RESOURCE_EXHAUSTED" in s or "quotaerror" in s.lower()


class _Run:
    def __init__(self, clock, max_calls=GEO_MAX_CALLS, max_sec=GEO_MAX_SEC):
        self.clock, self.max_calls, self.max_sec = clock, max_calls, max_sec
        self.t0 = clock()
        self.lock = threading.Lock()
        self.calls = self.errors = 0
        self.stop = None
        self.chunk_sec = 0.0                        # the longest chunk so far (a chunk is not started without room)

    def elapsed(self):
        return self.clock() - self.t0

    def left(self):
        return self.max_calls - self.calls

    def start(self):
        with self.lock:
            if not self.stop and self.elapsed() >= self.max_sec:
                self.stop = "time"
            if not self.stop and self.calls >= self.max_calls:
                self.stop = "calls"
            if self.stop:
                raise _Stop(self.stop)
            self.calls += 1

    def failed(self, e):
        with self.lock:
            if isinstance(e, _Stop) or _is403(e):
                return                              # 403: a disabled account — "skipped", not an error
            self.errors += 1
            if _is_quota(e):
                self.stop = self.stop or "quota"

    def counted(self, search):
        def f(*args, **kw):
            self.start()
            try:
                return search(*args, **kw)
            except Exception as e:
                self.failed(e)
                raise
        return f


class _Ctx:
    """The step's lazy Google Ads context: token + roster (currencies) + the rates into base, made only when a chunk
    has an account to ask."""

    def __init__(self, s, run, search, token, fx_fn, base):
        self.s, self.run, self.base = s, run, base
        self.search = run.counted(search or gads._search)
        self.token, self.fx_fn = token, fx_fn or gads._fx_to_usd
        self.mcc = str(s.get("google_ads_login_customer_id") or "").replace("-", "")
        self.dev = s.get("google_ads_dev_token")
        self.ok = None
        self.ccy = {}
        self._usd = {}
        self.map_failed = False                     # the by-id country map failed / was stopped in this build

    def ready(self):
        if self.ok is not None:
            return self.ok
        self.ok = False
        if not self.token:
            try:
                s = self.s
                self.token = gads._access_token(s.get("google_ads_client_id") or s.get("google_client_id"),
                                                s.get("google_ads_client_secret") or s.get("google_client_secret"),
                                                s.get("google_ads_refresh_token"))
            except Exception:
                self.run.errors += 1
                return False
        try:
            rows = self.search(self.mcc, self.mcc, self.dev, self.token, Q_ROSTER)
        except Exception as e:
            if _is403(e):                           # on the MCC a 403 is no disabled account: a real error
                self.run.errors += 1
            return False
        for row in rows or []:
            cc = row.get("customerClient") or {}
            if cc.get("manager") or cc.get("id") in (None, ""):
                continue
            self.ccy[str(cc.get("id"))] = cc.get("currencyCode") or "USD"
        self.ok = True
        return True

    def rate(self, acct):
        """Account currency → base (ccy → USD → base), 1.0 in the base currency."""
        ccy = self.ccy.get(acct) or self.base
        if ccy == self.base:
            return 1.0
        for c in (ccy, self.base):
            if c not in self._usd:
                self._usd[c] = float(self.fx_fn(c) or 0)
        return self._usd[ccy] / (self._usd[self.base] or 1.0)


# ── one chunk ─────────────────────────────────────────────────────────────────────────────────────

def _plan(spend, a, b):
    """The chunk's stores with spend (any daily value > 0 in [a, b]) → (own {store: {accounts}}, noacct stores)."""
    a, b = a.isoformat(), b.isoformat()
    camps = spend.get("campaigns") or {}
    own = {}
    for sid, dd in (spend.get("daily") or {}).items():
        if any(a <= d <= b and (v or 0) > 0 for d, v in (dd or {}).items()):
            own[sid] = {str(c.get("account")) for c in (camps.get(sid) or []) if c.get("account")}
    return own, {sid for sid, ac in own.items() if not ac}


def _ask(ctx, acct, a, b):
    """One account: Q-G1 then Q-G2 → {"g1": rows | None, "st": None | "403" | "stop" | "err", "g2": rows | None}."""
    out = {"g1": None, "st": None, "g2": None}
    args = (acct, ctx.mcc, ctx.dev, ctx.token, a.isoformat(), b.isoformat())
    try:
        out["g1"] = gads._app_geo_spend_for(*args, search=ctx.search)
    except _Stop:
        out["st"] = "stop"
        return out
    except Exception as e:
        out["st"] = "403" if _is403(e) else "err"
        return out
    try:
        out["g2"] = gads._app_geo_installs_for(*args, search=ctx.search)
    except Exception:
        out["g2"] = None
    return out


def _map_ids(ctx, cache, ids, today):
    """Ids not in the map: one by-id call for all of them (any target type) → own ISO-2, else the parent's (one more
    call for all parents), else null ("XX" — Google Ads answered, with no country: asked again with the next Country
    list, GEO_ISO_DAYS). → True when every id got Google Ads' answer; False when a call failed or the budget stopped
    it: those ids are NOT recorded (asked again at the next chance — never parked as "no country" for 30 days), their
    cost sits under "XX" meanwhile."""
    iso = cache["iso"]
    new = sorted({i for i in ids if i and i not in iso}, key=int)
    if not new:
        return True
    if ctx.map_failed:                                  # once a build: a failing map is asked again next build
        return False
    try:
        got = gads._geo_iso(ctx.mcc, ctx.dev, ctx.token, ids=new, search=ctx.search)
    except Exception:                                   # a failed call, or _Stop (the budget): nothing recorded
        ctx.map_failed = True
        return False
    if got is None:
        ctx.map_failed = True
        return False
    parents = {}
    for i in new:
        g = got.get(i) or {}
        if g.get("cc"):
            iso[i] = g["cc"]
        elif g.get("parent"):
            parents[i] = g["parent"]
        else:
            iso[i] = None
    need = sorted({p for p in parents.values() if not iso.get(p)}, key=int)
    if need:
        try:
            pgot = gads._geo_iso(ctx.mcc, ctx.dev, ctx.token, ids=need, search=ctx.search) or {}
        except Exception:                               # the children stay unrecorded (asked again, parents too)
            ctx.map_failed = True
            return False
        for p in need:
            if (pgot.get(p) or {}).get("cc"):
                iso[p] = pgot[p]["cc"]
    for i, p in parents.items():
        iso[i] = iso.get(p) or None
    return True


def _chunk(ctx, cache, spend, a, b, today, stats, backfill):
    """Ask, map and (maybe) commit one chunk [a, b] (a is a Monday) → "ok" | "empty" | "fail" | "stop" | "none"
    ("none": no store had spend — nothing asked; "empty": a backfill chunk whose accounts answered with no cost row
    although their stores had spend — nothing written)."""
    run = ctx.run
    own, noacct = _plan(spend, a, b)
    stats["noacct"] |= noacct
    wanted = set().union(*own.values()) if own else set()
    if not wanted:
        return "none"
    if run.stop:
        return "stop"
    first = ctx.ok is None
    if not ctx.ready():
        return "fail"
    if first:
        _iso_list(ctx, cache, today)
    ts = today.isoformat()
    skip = {x for x in wanted if (cache["skip"].get(x) or "") > ts or x not in ctx.ccy}
    ask = sorted(wanted - skip)
    stats["skipped"] |= skip
    if ask:
        if run.left() < 2 * len(ask) + ISO_RESERVE:
            run.stop = run.stop or "calls"
            return "stop"
        if run.elapsed() + run.chunk_sec > run.max_sec:
            run.stop = run.stop or "time"
            return "stop"
    res = {}
    if ask:
        t0 = run.clock()
        with ThreadPoolExecutor(max_workers=min(GEO_WORKERS, len(ask))) as ex:
            res = dict(zip(ask, ex.map(lambda x: _ask(ctx, x, a, b), ask)))
        run.chunk_sec = max(run.chunk_sec, run.clock() - t0)
    stats["accounts"] |= set(ask)
    until = (today + timedelta(days=GEO_SKIP_DAYS)).isoformat()
    for x, r in res.items():
        if r["st"] == "403":
            cache["skip"][x] = until
            skip.add(x)
            stats["skipped"].add(x)
    if any(r["st"] in ("stop", "err") for r in res.values()):
        return "stop" if all(r["st"] != "err" for r in res.values()) and run.stop else "fail"
    answered = [x for x in ask if res[x]["g1"] is not None]
    rows = sum(len(res[x]["g1"]) for x in answered)
    if backfill and answered and not rows:
        return "empty"
    ids = {r["ccid"] for x in answered for k in ("g1", "g2") for r in (res[x][k] or []) if r.get("ccid")}
    if not _map_ids(ctx, cache, ids, today) and backfill:
        # a backfilled week is never pulled again: its cost must not be parked under "XX" for good because the country
        # map failed once — the chunk is dropped and asked again (the refresh commits: its weeks are pulled again
        # within ~a day, and the engine does not read a week whose cost sits unmapped as covered)
        return "stop" if run.stop else "fail"
    iso = cache["iso"]
    lo, hi = a.isoformat(), b.isoformat()
    cells, seen, dlnull = {}, set(), set()
    for x in answered:
        rate = ctx.rate(x)
        mine = {sid for sid, ac in own.items() if x in ac}
        for r in res[x]["g1"]:
            sid, d = r["store_id"], r["date"]
            if not sid:
                stats["nostore"] += 1
                continue
            if not lo <= d <= hi:
                continue
            mine.add(sid)
            cc = (iso.get(r["ccid"]) if r["ccid"] else None) or UNMAPPED
            if r["ccid"]:
                stats["ids"][r["ccid"]] = iso.get(r["ccid"])
            c = cells.setdefault((sid, _mon(d).isoformat(), cc), [0.0, 0.0])
            c[0] += r["cost_micros"] * rate
        if res[x]["g2"] is None:
            dlnull |= mine
        for r in res[x]["g2"] or []:
            sid, d = r["store_id"], r["date"]
            if not sid:
                stats["nostore"] += 1
                continue
            if not lo <= d <= hi:
                continue
            mine.add(sid)
            cc = (iso.get(r["ccid"]) if r["ccid"] else None) or UNMAPPED
            c = cells.setdefault((sid, _mon(d).isoformat(), cc), [0.0, 0.0])
            c[1] += r["dl"]
        seen |= mine
    blocked = {sid for sid, ac in own.items() if ac & skip}
    replace = (({sid for sid, ac in own.items() if ac} | seen) - blocked)
    ws = mondays(a, b)
    for sid in sorted(replace):
        dst = cache["weeks"].setdefault(sid, {})
        for w in ws:
            dst[w] = {}
    for (sid, w, cc), (cost, dl) in cells.items():
        if sid not in replace:
            continue
        cost = cell_cost(cost)
        dl = None if sid in dlnull else round(dl, 2)
        if cost == 0 and not dl:
            continue
        cache["weeks"][sid][w][cc] = [cost, dl]
    stats["stores"] |= replace
    return "ok"


# ── the step ─────────────────────────────────────────────────────────────────────────────────────

def _usable(s, spend):
    need = ("google_ads_dev_token", "google_ads_login_customer_id", "google_ads_refresh_token")
    if not all(s.get(k) for k in need):
        return False
    if not (s.get("google_ads_client_id") or s.get("google_client_id")) \
            or not (s.get("google_ads_client_secret") or s.get("google_client_secret")):
        return False
    return isinstance(spend, dict) and not spend.get("error") and isinstance(spend.get("daily"), dict)


def _prune(cache, today):
    """Expired skips go; weeks older than the month of today − GEO_KEEP_DAYS go (a whole month at a time)."""
    ts = today.isoformat()
    cache["skip"] = {k: v for k, v in (cache.get("skip") or {}).items() if isinstance(v, str) and v > ts}
    keep = _mon((today - timedelta(days=GEO_KEEP_DAYS)).replace(day=1)).isoformat()
    for sid in list(cache["weeks"]):
        ws = {w: v for w, v in cache["weeks"][sid].items() if w >= keep}
        if ws:
            cache["weeks"][sid] = ws
        else:
            del cache["weeks"][sid]
    if cache.get("first") and cache["first"] < keep:
        cache["first"] = keep


def _iso_list(ctx, cache, today):
    """The Country list, when due (first run, then every GEO_ISO_DAYS): null ids go with it (asked again by id)."""
    at = cache.get("iso_at")
    if at and (today - _d(at)).days < GEO_ISO_DAYS:
        return
    try:
        got = gads._geo_iso(ctx.mcc, ctx.dev, ctx.token, ids=None, search=ctx.search)
    except Exception:
        return
    iso = {k: v for k, v in (cache.get("iso") or {}).items() if v}
    iso.update({k: g["cc"] for k, g in got.items() if g.get("cc")})
    cache["iso"], cache["iso_at"] = iso, today.isoformat()


STATS = ("accounts", "skipped", "stores", "wref", "wbf", "noacct")


def _stats():
    st = {k: set() for k in STATS}
    st.update(nostore=0, ids={})
    return st


def public_line(st, state, calls, errors):
    ids = st["ids"]
    mapped = sum(1 for v in ids.values() if v)
    return ("gads geo: accounts %d (skipped %d), stores %d, weeks refreshed %d, backfill weeks %d (%s), calls %d, "
            "errors %d, countries mapped %d, unmapped %d"
            % (len(st["accounts"] | st["skipped"]), len(st["skipped"]), len(st["stores"]), len(st["wref"]),
               len(st["wbf"]), state, calls, errors, mapped, len(ids) - mapped))


def geo_step(s, data_dir, spend, today, *, now=time.time, clock=time.monotonic, search=None, token=None,
             fx_fn=None, max_calls=GEO_MAX_CALLS, max_sec=GEO_MAX_SEC):
    """The build's geo step (GADS_GEO on): refresh when due, then backfill; the cache saved → the public counts line.
    `spend` = the merged spend cache (read only, never changed). search / token / fx_fn / now / clock: injectable."""
    today = _d(today)
    st = _stats()
    if not _usable(s, spend):
        return public_line(st, "off", 0, 0)
    base = spend.get("currency_src") or "USD"
    cache, old = _load(data_dir)
    if cache is None or cache.get("ccy") != base:
        cache = fresh(base)                                             # start over: a v bump or another currency
    elif old == "bad":
        oldest = min((w for ws in cache["weeks"].values() for w in ws), default=None)
        if oldest:                                                      # the .old part is lost: fill it again
            cache.update(first=oldest, bfrom=oldest, done=False, edge=None, erun=0)
    _prune(cache, today)
    run = _Run(clock, max_calls, max_sec)
    ctx = _Ctx(s, run, search, token, fx_fn, base)
    end = (today - timedelta(days=1)).isoformat()
    t = int(now())

    # 1. the refresh
    refreshed = failed = False
    # due every ~20 h — and, before the first commit, at every build until GEO_FAIL_BACKOFF refreshes failed in a row
    # (then _ts holds the next try ~20 h away: a persistent error never costs ~40 requests an hour)
    if t - int(cache.get("_ts") or 0) >= GEO_EVERY_SEC:
        rp = cache.get("rpart")
        if not isinstance(rp, dict) or rp.get("end") != end:
            rp = {"end": end, "done": []}
        cache["rpart"] = rp
        pieces = refresh_pieces(today)
        todo = [(a, b) for a, b in pieces if a.isoformat() not in rp["done"]]
        for a, b in todo:
            r = _chunk(ctx, cache, spend, a, b, today, st, backfill=False)
            if r in ("ok", "none"):
                rp["done"].append(a.isoformat())
                st["wref"] |= set(mondays(a, b))
                cache["first"] = min(cache["first"] or a.isoformat(), a.isoformat())
            elif r == "fail":
                failed = True
                break
            else:
                break
        if all(a.isoformat() in rp["done"] for a, _ in pieces):
            r0 = pieces[-1][0].isoformat()
            gap = cache["till"] is not None and cache["till"] < (_d(r0) - timedelta(days=1)).isoformat()
            if cache["bfrom"] is None or gap:
                cache.update(bfrom=r0, done=False, edge=None, erun=0)
            cache.update(till=end, _ts=t, fails=0, rpart=None)
            refreshed = True
        elif failed:
            cache["fails"] = int(cache.get("fails") or 0) + 1
            if cache["fails"] >= GEO_FAIL_BACKOFF:
                cache.update(_ts=t, fails=0, rpart=None)

    # 2. the backfill (never after a failed refresh; after GEO_FAIL_BACKOFF failed chunks only with the daily refresh)
    asked = 0
    spend_first = min((d for dd in (spend.get("daily") or {}).values() for d in (dd or {})), default=None)
    while (not cache["done"] and cache["bfrom"] and not failed and not run.stop and asked < GEO_BACKFILL_CHUNKS
           and (int(cache.get("bfails") or 0) < GEO_FAIL_BACKOFF or refreshed)):
        lim = today - timedelta(days=GEO_KEEP_DAYS)
        if spend_first:
            lim = max(lim, _d(spend_first))
        lim = _mon(lim)
        bfrom = _d(cache["bfrom"])
        if spend_first is None or bfrom <= lim:
            cache["done"] = True
            break
        a, b = max(bfrom - timedelta(days=GEO_CHUNK_DAYS), lim), bfrom - timedelta(days=1)
        r = _chunk(ctx, cache, spend, a, b, today, st, backfill=True)
        if r in ("ok", "none", "empty"):
            if r != "none":
                asked += 1
            cache["bfrom"] = a.isoformat()
            cache["bfails"] = 0
            if r == "empty":
                cache["erun"] = int(cache.get("erun") or 0) + 1
                if cache["erun"] >= GEO_EDGE_CHUNKS:
                    cache.update(done=True, edge=a.isoformat())
            else:
                cache["first"] = min(cache["first"] or a.isoformat(), a.isoformat())
                st["wbf"] |= set(mondays(a, b))
                if r == "ok":
                    cache["erun"] = 0
                if a <= lim:
                    cache["done"] = True
        elif r == "fail":
            cache["bfails"] = int(cache.get("bfails") or 0) + 1
            break
        else:
            break

    save_geo(data_dir, cache)
    state = ("edge" if cache.get("edge") else "done") if cache["done"] else "filling"
    return public_line(st, state, run.calls, run.errors)
