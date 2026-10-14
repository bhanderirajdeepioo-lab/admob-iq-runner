"""Google Ads SPEND BY HOUR (GADS_ARCHIVE; private data/ only, never shown, no existing number reads it).

Google Ads days are the ACCOUNT's days (its time zone, e.g. IST), while an install day elsewhere is GMT: the hour split
lets a later step cut spend into any zone's days. Query: the spend query + segments.hour
(google_ads._app_hourly_spend_for), ONE request per account per run over the whole window.

When (inside the archive step's call budget): at most once per HR_EVERY_SEC (~20 h), the window today − HR_REFETCH_DAYS
.. today − 1 (complete days; hourly cost restates like the daily cost), reaching back to today − HR_BACK_DAYS on the
first run and over any gap since the last run. Accounts: those owning a store with spend in the window (the spend
cache's campaign → account map, like the geo step) that the roster says are ENABLED; an account answering 403 is
skipped SKIP_DAYS (as the geo step does; a 403 other than CUSTOMER_NOT_ENABLED is also counted as an error). An
account that answered has ALL its cells of the window replaced (a cell Google no longer reports goes); one that failed
keeps its cells and the run is asked again at the next build (HR_FAIL_BACKOFF failed runs in a row → wait for the next
~20 h).

File data/ads_hourly/<YYYY-MM>.json.gz (deterministic, only on change):
  {"v": 1, "month": "YYYY-MM", "ccy": {account: currency}, "tz": {account: time zone | null},
   "camp": {campaign: store}, "h": {account: {campaign: {day: [24 cost micros, hour 0 … 23]}}}}
  Money is the account's currency, raw micros; day and hour are the account's (tz names its zone). data/ads_hourly/
  state.json.gz: {"first", "till", "_ts", "fails", "skip", "ties"}.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from . import google_ads as gads
from .gads_geo import _Stop, _is403, _is_quota, _plan
from .gads_store import Months, d, days, load_state, month_of, odd403, save_state, spend_ok

HR_V = 1
HR_DIR = "ads_hourly"
HR_REFETCH_DAYS = 30                # asked again each run (hourly cost restates like the daily cost)
HR_BACK_DAYS = 90                   # how far back the store reaches
HR_EVERY_SEC = 20 * 3600            # a run at most once a ~day
HR_FAIL_BACKOFF = 3
HR_WORKERS = 4
SKIP_DAYS = 7
DEFAULTS = {"first": None, "till": None, "_ts": 0, "fails": 0, "skip": {}, "ties": {}}


def _empty(m):
    return {"v": HR_V, "month": m, "ccy": {}, "tz": {}, "camp": {}, "h": {}}


def months(data_dir):
    return Months(os.path.join(data_dir, HR_DIR), _empty,
                  lambda o: o.get("v") == HR_V and isinstance(o.get("h"), dict) and isinstance(o.get("camp"), dict))


def load(data_dir):
    """Every month merged → {"ccy", "tz", "camp", "h": {account: {campaign: {day: [24]}}}} — the read API."""
    mf = months(data_dir)
    out = {"ccy": {}, "tz": {}, "camp": {}, "h": {}}
    for m in mf.months():
        f = mf.peek(m)
        for k in ("ccy", "tz", "camp"):
            out[k].update(f[k])
        for a, cs in f["h"].items():
            for cid, dd in cs.items():
                out["h"].setdefault(a, {}).setdefault(cid, {}).update(dd)
    return out


def replace(mf, acct, rows, lo, hi, ccy, tz):
    """One account's answer for [lo, hi] → every cell of that account in the window replaced → cells written."""
    lo, hi = str(lo), str(hi)
    cells, camp = {}, {}
    for r in rows:
        dd, cid = r["date"], r["campaign_id"]
        if not cid or not lo <= dd <= hi:
            continue
        h = cells.setdefault(month_of(dd), {}).setdefault(cid, {}).setdefault(dd, [0] * 24)
        h[r["hour"]] += int(r["cost_micros"])
        camp[cid] = r["store_id"]
    n = 0
    for m in sorted({month_of(x) for x in days(lo, hi)}):
        f = mf.peek(m)
        have = f["h"].get(acct) or {}
        if not have and m not in cells:
            continue
        f = mf.get(m)
        keep = {}
        for cid, dd in have.items():
            rest = {x: v for x, v in dd.items() if not lo <= x <= hi}
            if rest:
                keep[cid] = rest
        for cid, dd in (cells.get(m) or {}).items():
            keep.setdefault(cid, {}).update(dd)
            f["camp"][cid] = camp[cid]
            n += len(dd)
        if keep:
            f["h"][acct] = keep
            f["ccy"][acct] = ccy
            f["tz"][acct] = tz
        else:
            f["h"].pop(acct, None)
        used = {c for cs in f["h"].values() for c in cs}
        f["camp"] = {c: s for c, s in f["camp"].items() if c in used}
        f["ccy"] = {a: c for a, c in f["ccy"].items() if a in f["h"]}
        f["tz"] = {a: z for a, z in f["tz"].items() if a in f["h"]}
    return n


def ties(mf, spend, lo, hi, answered, asked):
    """Store-days of [lo, hi] whose asked owners all answered: Σ hours (in the cache's base currency, as _aggregate
    converts) = the spend cache's day → [equal, of]."""
    base, fx = spend.get("currency_src") or "USD", spend.get("fx") or {}
    camps = spend.get("campaigns") or {}
    tot = {}
    for m in sorted({month_of(x) for x in days(lo, hi)}):
        f = mf.peek(m)
        for a, cs in f["h"].items():
            c = f["ccy"].get(a) or base
            r = None if c == base else (float(fx.get(c) or 0) / float(fx.get(base) or 1.0))
            for cid, dd in cs.items():
                sid = f["camp"].get(cid)
                for x, hs in dd.items():
                    if lo <= x <= hi:
                        v = sum(hs)
                        tot[(sid, x)] = tot.get((sid, x), 0) + (v if r is None else int(round(v * r)))
    ok = n = 0
    for sid, dd in sorted((spend.get("daily") or {}).items()):
        owners = {str(c.get("account")) for c in camps.get(sid) or [] if c.get("account")} & set(asked)
        if not owners or not owners <= answered:
            continue
        for x, want in dd.items():
            if lo <= x <= hi and want:
                n += 1
                ok += int(tot.get((sid, x), 0) == int(want))
    return [ok, n]


def stats():
    return {"accounts": set(), "skipped": set(), "camps": set(), "days": 0, "ties": [0, 0], "noacct": set()}


def hourly_part(sess, data_dir, spend, today, st, now=time.time):
    """The run when due → state word ("fresh" | "done" | "partial" | "waiting")."""
    if not spend_ok(spend):
        return "waiting"
    dirpath = os.path.join(data_dir, HR_DIR)
    state = load_state(dirpath, HR_V, DEFAULTS)
    t = int(now())
    if t - int(state.get("_ts") or 0) < HR_EVERY_SEC:
        return "fresh"
    ts = today.isoformat()
    state["skip"] = {k: v for k, v in state["skip"].items() if isinstance(v, str) and v > ts}
    hi = today - timedelta(days=1)
    lo = today - timedelta(days=HR_REFETCH_DAYS)
    if state["till"] is None:
        lo = today - timedelta(days=HR_BACK_DAYS)
    else:
        lo = max(min(lo, d(state["till"]) + timedelta(days=1)), today - timedelta(days=HR_BACK_DAYS))
    own, noacct = _plan(spend, lo, hi)
    st["noacct"] |= noacct
    wanted = set().union(*own.values()) if own else set()
    if wanted and not sess.ready():
        return "partial"
    live = set(sess.live()) if wanted else set()
    skip = {x for x in wanted if x not in live or (state["skip"].get(x) or "") > ts}
    st["skipped"] |= skip
    ask = sorted(wanted - skip)
    if ask and sess.run.left() < len(ask):
        sess.run.stop = sess.run.stop or "calls"
        return "partial"
    res = {}

    def one(x):
        try:
            return gads._app_hourly_spend_for(x, sess.mcc, sess.dev, sess.token, lo.isoformat(), hi.isoformat(),
                                              search=sess.search)
        except _Stop:
            return "stop"
        except Exception as e:
            if _is403(e):
                return "odd" if odd403(e) else "gone"
            return "stop" if _is_quota(e) else "err"
    if ask:
        with ThreadPoolExecutor(max_workers=min(HR_WORKERS, len(ask))) as ex:
            res = dict(zip(ask, ex.map(one, ask)))
    mf = months(data_dir)
    until = (today + timedelta(days=SKIP_DAYS)).isoformat()
    answered = set()
    for x in ask:
        r = res[x]
        if r in ("gone", "odd"):
            state["skip"][x] = until
            st["skipped"].add(x)
            if r == "odd":
                with sess.run.lock:
                    sess.run.errors += 1                     # an ENABLED account refused: not silent
            continue
        if isinstance(r, str):
            continue
        acc = sess.accounts.get(x) or {}
        replace(mf, x, r, lo, hi, acc.get("ccy") or "USD", acc.get("tz"))
        answered.add(x)
        st["camps"] |= {row["campaign_id"] for row in r}
    st["accounts"] |= answered
    mf.save()
    complete = all(not isinstance(res.get(x), str) or res.get(x) in ("gone", "odd") for x in ask)
    if answered:
        st["ties"] = ties(mf, spend, lo.isoformat(), hi.isoformat(), answered, ask)
    if complete:
        st["days"] = (hi - lo).days + 1
        state["first"] = min(state["first"] or lo.isoformat(), lo.isoformat())
        state["till"] = hi.isoformat()
        state.update(_ts=t, fails=0, ties={"window": [lo.isoformat(), hi.isoformat()], "store_days": st["ties"]})
    else:
        state["fails"] = int(state.get("fails") or 0) + 1
        if state["fails"] >= HR_FAIL_BACKOFF:
            state.update(_ts=t, fails=0)
    if ask or os.path.exists(os.path.join(dirpath, "state.json.gz")) or complete:
        save_state(dirpath, state)
    return "done" if complete else "partial"


def public_line(st, state, calls, errors):
    return ("gads hours: accounts %d (skipped %d), campaigns %d, days %d (%s), no account %d, ties %d/%d, calls %d, "
            "errors %d" % (len(st["accounts"] | st["skipped"]), len(st["skipped"]), len(st["camps"]), st["days"], state,
                           len(st["noacct"]), st["ties"][0], st["ties"][1], calls, errors))
