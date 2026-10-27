"""Google Ads rows PER CAMPAIGN × DAY (GADS_ARCHIVE; private data/ only, never shown, no existing number reads it).

The hourly spend fetch (google_ads.fetch_app_spend) already downloads campaign × day rows — cost (the spend query),
installs + conversion value (now with campaign.id, the same rows), day-1 value (the lag-bucket query) — and sums them
into the store × day spend cache (roas_spend_cache.json, unchanged). This keeps those rows instead of summing them away:

  capture   every build: google_ads.take_rows() (what fetch_app_spend kept aside — 0 extra calls) is laid over the store
            exactly like merge_spend lays the fresh window over the spend cache: per metric, a store-day present in the
            fresh rows replaces ALL that store-day's campaign cells; store-days not in the fresh rows keep theirs. So
            Σ campaigns of a store-day = the spend cache's number for it (the "ties" of the public line; day-1: the
            days the cache has not fixed yet — a fixed D0 day keeps its number there, this store Google's current one).
  backfill  newest → oldest in CD_CHUNK_DAYS chunks (≤ CD_BACKFILL_CHUNKS a build, inside the archive step's call
            budget), down to the spend cache's first day: the days below the newest covered range not covered yet
            (state "cov": the day ranges captured or backfilled — so a capture after a pause, which leaves a gap below
            it, has that gap filled first). The same three queries per account the roster says is ENABLED (all of
            them, not only the spend cache's campaign owners — the cache keeps a store's campaigns of its last fetch
            window, so an older owner can be missing there), for chunks in which some store had spend. A campaign
            owner (the cache's map) that is not ENABLED cannot answer (Google: 403) and is not asked — its campaigns'
            older days stay out (state "holes": ["all", account, first, last]); a store without any owner is counted
            "no account". An account answering the cost query with ANY 403 is skipped SKIP_DAYS like that (as the
            geo step does; a 403 other than CUSTOMER_NOT_ENABLED is also counted as an error). A chunk is written
            when every asked campaign owner answered the cost query; another account's failed cost query fails the
            chunk too (asked again) until CD_FAIL_BACKOFF chunks failed in a row, then that account is a hole
            (["all", …]) and the backfill goes on. A failed installs / day-1 query leaves that metric out for that
            account and chunk ([metric, account, first, last] in "holes", never 0).

File data/ads_campaign_day/<YYYY-MM>.json.gz (deterministic, only on change):
  {"v": 1, "month": "YYYY-MM", "camp": {campaign: {"s": store, "a": account}}, "ccy": {account: currency},
   "cost": {campaign: {day: micros}}, "inst": {campaign: {day: installs}}, "cv": {campaign: {day: value}},
   "cv1": {campaign: {day: day-1 value}}}
  Money is the ACCOUNT's currency, raw (micros for cost; no FX baked in — "ccy" names it). Days are the account's days
  (segments.date). Zero cells are left out. data/ads_campaign_day/state.json.gz: {"first", "till", "cov", "bfrom" (the
  newest covered range's first day), "done", "bfails", "bday", "skip", "holes", "ties"}.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from . import google_ads as gads
from .gads_geo import _Stop, _is403, _is_quota, _plan
from .gads_store import Months, cov_add, cov_next, cov_of, days, load_state, month_of, odd403, save_state, spend_ok

CD_V = 1
CD_DIR = "ads_campaign_day"
METRICS = ("cost", "inst", "cv", "cv1")
CACHE_KEY = {"cost": "daily", "inst": "installs", "cv": "convval", "cv1": "convval_day1"}
CD_CHUNK_DAYS = 180                 # a backfill chunk (one request per query per account)
CD_BACKFILL_CHUNKS = 2              # backfill chunks asked per build
CD_FAIL_BACKOFF = 3                 # failed chunks in a row before waiting for the next day
SKIP_DAYS = 7
DEFAULTS = {"first": None, "till": None, "cov": None, "bfrom": None, "done": False, "bfails": 0, "bday": None,
            "skip": {}, "holes": [], "ties": {}}


def _empty(m):
    return {"v": CD_V, "month": m, "camp": {}, "ccy": {}, "cost": {}, "inst": {}, "cv": {}, "cv1": {}}


def months(data_dir):
    return Months(os.path.join(data_dir, CD_DIR), _empty,
                  lambda o: o.get("v") == CD_V and all(isinstance(o.get(k), dict) for k in ("camp",) + METRICS))


def _value(metric, r):
    if metric == "cost":
        return int(r.get("cost_micros") or 0)
    if metric == "inst":
        return float(r.get("installs") or 0)
    return float(r.get("convval") or 0)


def _norm(metric, v):
    return int(v) if metric == "cost" else round(float(v), 6)


def overlay(mf, metric, rows, ccy):
    """Lay fresh rows of one metric over the store (merge_spend's rule, per store-day) → cells written."""
    grouped, meta = {}, {}
    for r in rows or []:
        cid, sid, dd = str(r.get("campaign_id") or ""), r.get("store_id"), str(r.get("date") or "")
        if not cid or not sid or len(dd) != 10:
            continue
        g = grouped.setdefault((sid, dd), {})
        g[cid] = g.get(cid, 0) + _value(metric, r)
        meta[cid] = (sid, str(r.get("account") or "") or None)
    by_month = {}
    for sid, dd in grouped:
        by_month.setdefault(month_of(dd), []).append((sid, dd))
    n = 0
    for m in sorted(by_month):
        f = mf.get(m)
        owned = {}
        for cid, x in f["camp"].items():
            owned.setdefault(x.get("s"), set()).add(cid)
        for sid, dd in sorted(by_month[m]):
            for cid in owned.get(sid, ()):                       # the store-day is replaced as a whole
                cells = f[metric].get(cid)
                if cells and dd in cells:
                    del cells[dd]
                    if not cells:
                        del f[metric][cid]
            for cid, v in sorted(grouped[(sid, dd)].items()):
                v = _norm(metric, v)
                if not v:
                    continue
                s_, a_ = meta[cid]
                f[metric].setdefault(cid, {})[dd] = v
                f["camp"][cid] = {"s": s_, "a": a_}
                owned.setdefault(s_, set()).add(cid)
                if a_:
                    f["ccy"][a_] = ccy.get(a_) or f["ccy"].get(a_) or "USD"
                n += 1
        live = set().union(*(f[k].keys() for k in METRICS))
        f["camp"] = {c: x for c, x in f["camp"].items() if c in live}
    return n


def load(data_dir, first=None, last=None):
    """Every month merged → {"camp", "ccy", "cost", "inst", "cv", "cv1"} (days in [first, last]) — the read API."""
    mf = months(data_dir)
    out = {k: {} for k in ("camp", "ccy") + METRICS}
    for m in mf.months():
        f = mf.peek(m)
        out["camp"].update(f["camp"])
        out["ccy"].update(f["ccy"])
        for k in METRICS:
            for cid, cells in f[k].items():
                for dd, v in cells.items():
                    if (first is None or dd >= str(first)) and (last is None or dd <= str(last)):
                        out[k].setdefault(cid, {})[dd] = v
    return out


def ties(mf, spend, first, last):
    """Store-days of [first, last] in the spend cache whose number = Σ of their campaigns here, converted to the cache's
    base currency the way google_ads._aggregate does → {metric: [equal, of]}. Day-1 (cv1): only the days after the
    cache's d1_fixed_till — a fixed D0 day keeps the number read when it was fixed (merge_spend), while this store keeps
    Google's current one, so it is not compared."""
    base, fx = spend.get("currency_src") or "USD", spend.get("fx") or {}
    fixed = str(spend.get("d1_fixed_till") or "")

    def rate(a, ccy):
        c = ccy.get(a) or base
        if c == base:
            return None
        return float(fx.get(c) or 0) / float(fx.get(base) or 1.0) if fx.get(c) else None

    camp, ccy, cells = {}, {}, {k: {} for k in METRICS}
    for m in sorted(x for x in mf.months() if month_of(first) <= x <= month_of(last)):
        f = mf.peek(m)
        camp.update(f["camp"])
        ccy.update(f["ccy"])
        for k in METRICS:
            for cid, cc in f[k].items():
                for dd, v in cc.items():
                    if first <= dd <= last:
                        cells[k].setdefault(cid, {})[dd] = v
    by_store = {}
    for cid, x in camp.items():
        by_store.setdefault(x.get("s"), []).append(cid)
    out = {}
    for k in METRICS:
        ok = n = 0
        for sid, dd in sorted((spend.get(CACHE_KEY[k]) or {}).items()):
            for day, want in dd.items():
                if not first <= day <= last or (k == "cv1" and day <= fixed):
                    continue
                n += 1
                tot = 0 if k == "cost" else 0.0
                for cid in by_store.get(sid, ()):
                    v = cells[k].get(cid, {}).get(day)
                    if v is None:
                        continue
                    r = rate(camp[cid].get("a"), ccy)
                    if k == "cost":
                        tot += int(v) if r is None else int(round(v * r))
                    else:
                        tot += v if r is None else v * r
                if (k == "cost" and tot == int(want)) or (k != "cost" and abs(round(tot, 2) - float(want)) < 0.0101):
                    ok += 1
        out[k] = [ok, n]
    return out


def _add_ties(dst, t):
    for k, (ok, n) in t.items():
        cur = dst.setdefault(k, [0, 0])
        cur[0] += ok
        cur[1] += n


def capture(data_dir, taken, spend, st):
    """This build's fetched rows → the store (0 calls)."""
    if not taken or not (taken.get("spend") or taken.get("inst") or taken.get("d1")):
        return
    ccy = {str(a.get("id")): a.get("currency") or "USD" for a in taken.get("accounts") or []}
    mf = months(data_dir)
    for metric, rows in (("cost", taken.get("spend")), ("inst", taken.get("inst")), ("cv", taken.get("inst")),
                         ("cv1", taken.get("d1"))):
        overlay(mf, metric, rows, ccy)
    lo, hi = str(taken.get("start"))[:10], str(taken.get("end"))[:10]
    st["camps"] |= {str(r.get("campaign_id")) for k in ("spend", "inst", "d1") for r in taken.get(k) or []
                    if r.get("campaign_id")}
    st["days"] += len(days(lo, hi))
    if spend_ok(spend):
        _add_ties(st["ties"], ties(mf, spend, lo, hi))
    mf.save()
    dirpath = os.path.join(data_dir, CD_DIR)
    state = load_state(dirpath, CD_V, DEFAULTS)
    state["first"] = min(state["first"] or lo, lo)
    state["till"] = max(state["till"] or hi, hi)
    state["cov"] = cov_add(cov_of(state), lo, hi)
    if state["cov"][-1][0] > (state["bfrom"] or ""):             # a range above a gap: the backfill fills the gap
        state["done"] = False
    state["bfrom"] = state["cov"][-1][0]
    state["ties"]["live"] = {k: v for k, v in st["ties"].items()}
    save_state(dirpath, state)


def _ask(sess, acct, a, b):
    """One account's three queries over [a, b] → {"spend", "inst", "d1": rows | None, "st": None | "gone" | "stop" |
    "err", "odd": a 403 other than CUSTOMER_NOT_ENABLED seen}. Any 403 on the cost query = "gone" (the account
    cannot answer); on installs / day-1 it leaves that metric out."""
    out = {"spend": None, "inst": None, "d1": None, "st": None, "odd": False}
    args = (acct, sess.mcc, sess.dev, sess.token, a.isoformat(), b.isoformat())
    for key, fn in (("spend", gads._app_spend_for), ("inst", gads._app_installs_for), ("d1", gads._app_convval_lag_for)):
        try:
            rows = fn(*args, search=sess.search)
        except _Stop:
            out["st"] = "stop"
            return out
        except Exception as e:
            if _is403(e):
                out["odd"] = out["odd"] or odd403(e)
                if key == "spend":
                    out["st"] = "gone"
                    return out
                continue
            if key == "spend" or _is_quota(e):
                out["st"] = "stop" if _is_quota(e) else "err"
                return out
            continue
        for r in rows:
            r["account"] = acct
            r["currency"] = sess.ccy(acct)
        out[key] = rows
    return out


def backfill(sess, data_dir, spend, today, st, max_chunks=CD_BACKFILL_CHUNKS):
    """Older chunks, newest first → state word ("done" | "filling" | "waiting")."""
    dirpath = os.path.join(data_dir, CD_DIR)
    if not os.path.exists(os.path.join(dirpath, "state.json.gz")):
        return "waiting"
    state = load_state(dirpath, CD_V, DEFAULTS)
    state["cov"] = cov_of(state)
    if not spend_ok(spend) or not state["cov"]:
        return "done" if state["done"] else "waiting"
    ts = today.isoformat()
    lim = min((dd for x in spend["daily"].values() for dd in (x or {})), default=None)

    def nxt():
        return cov_next(state["cov"], lim, CD_CHUNK_DAYS) if lim else None
    if nxt() is None:
        state["done"] = True
    elif int(state.get("bfails") or 0) >= CD_FAIL_BACKOFF and state.get("bday") == ts:
        state["done"] = False                                    # failed chunks today: wait for tomorrow
    else:
        state["done"] = False
        _fill(sess, data_dir, spend, today, st, state, nxt, max_chunks)
    state["bfrom"] = state["cov"][-1][0]
    tb = state["ties"].setdefault("backfill", {})
    _add_ties(tb, st["bties"])
    state["holes"] = [list(h) for h in sorted({tuple(h) for h in state["holes"]})]
    save_state(dirpath, state)
    return "done" if state["done"] else "filling"


def _fill(sess, data_dir, spend, today, st, state, nxt, max_chunks):
    """The backfill's chunks of this build (≤ max_chunks) → the month files and `state` (saved by the caller)."""
    ts = today.isoformat()
    state["skip"] = {k: v for k, v in state["skip"].items() if isinstance(v, str) and v > ts}
    # a failure of an account that owns no campaign in the cache fails the chunk like an owner's (a passing error is
    # asked again) — until CD_FAIL_BACKOFF chunks failed in a row: then it is a hole and the backfill goes on
    strict = int(state.get("bfails") or 0) < CD_FAIL_BACKOFF
    mf = months(data_dir)
    asked = 0
    while asked < max_chunks and not sess.run.stop:
        ch = nxt()
        if ch is None:
            state["done"] = True
            break
        a, b = ch
        own, noacct = _plan(spend, a, b)
        st["noacct"] |= noacct
        if not own:                                              # no store had spend in the chunk: nothing to ask
            state["cov"] = cov_add(state["cov"], a, b)
            continue
        if not sess.ready():
            break
        # every account that can answer (not only the cache's campaign owners: the cache lists a store's campaigns of
        # its last fetch window, an older owner may be missing there); owners that cannot answer = holes
        owners, live = set().union(*own.values()), set(sess.live())
        skip = {x for x in live | owners if x not in live or (state["skip"].get(x) or "") > ts}
        st["skipped"] |= skip & owners
        ask = sorted(live - skip)
        if ask and sess.run.left() < 3 * len(ask):
            sess.run.stop = sess.run.stop or "calls"
            break
        res = {}
        if ask:
            with ThreadPoolExecutor(max_workers=min(4, len(ask))) as ex:
                res = dict(zip(ask, ex.map(lambda x: _ask(sess, x, a, b), ask)))
        until = (today + timedelta(days=SKIP_DAYS)).isoformat()
        for x, r in sorted(res.items()):
            if r["st"] == "gone":
                state["skip"][x] = until
                st["skipped"].add(x)
            if r["odd"]:
                with sess.run.lock:
                    sess.run.errors += 1                         # an ENABLED account refused: not silent
        if any(r["st"] == "stop" for r in res.values()):
            break
        err = {x for x, r in res.items() if r["st"] == "err"}
        if err & owners or (err and strict):
            state["bfails"] = int(state.get("bfails") or 0) + 1
            state["bday"] = ts
            break
        ok = [x for x in ask if res[x]["spend"] is not None]
        ccy = {x: sess.ccy(x) for x in ok}
        for metric, key in (("cost", "spend"), ("inst", "inst"), ("cv", "inst"), ("cv1", "d1")):
            overlay(mf, metric, [r for x in ok for r in (res[x][key] or [])], ccy)
            for x in ok:
                if res[x][key] is None:
                    state["holes"].append([metric, x, a.isoformat(), b.isoformat()])
        for x in sorted((owners - set(ok)) | err):              # an owner that could not answer (not ENABLED / 403),
            state["holes"].append(["all", x, a.isoformat(), b.isoformat()])     # or another account that failed
        st["accounts"] |= set(ok)
        _add_ties(st["bties"], ties(mf, spend, a.isoformat(), b.isoformat()))
        state["cov"] = cov_add(state["cov"], a, b)
        state["bfails"] = 0
        strict = True
        st["bdays"] += (b - a).days + 1
        asked += 1
    if nxt() is None:
        state["done"] = True
    mf.save()


def stats():
    return {"camps": set(), "days": 0, "ties": {}, "bties": {}, "bdays": 0, "accounts": set(), "skipped": set(),
            "noacct": set()}


def public_line(st, state, calls, errors):
    t = st["ties"]

    def tv(k):
        return tuple(t.get(k) or (0, 0))
    return ("gads campaign days: campaigns %d, days %d, backfill days %d (%s), accounts %d (skipped %d), "
            "no account %d, ties cost %d/%d, installs %d/%d, value %d/%d, day1 %d/%d, calls %d, errors %d"
            % ((len(st["camps"]), st["days"], st["bdays"], state, len(st["accounts"] | st["skipped"]),
                len(st["skipped"]), len(st["noacct"])) + tv("cost") + tv("inst") + tv("cv") + tv("cv1")
               + (calls, errors)))
