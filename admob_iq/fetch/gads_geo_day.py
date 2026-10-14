"""Google Ads cost and downloads by COUNTRY × DAY (GADS_GEO + GADS_ARCHIVE; private data/ only, never shown, no
existing number reads it).

The geo step (fetch.gads_geo) asks Q-G1 / Q-G2 with segments.date and folds the days into Monday weeks
(roas_geo_cache*.json.gz — the Install value tab's cache, unchanged). This keeps the days:

  capture   the geo step's own chunks: when a chunk commits, the SAME rows (same accounts, same country map, same
            currency rate, same "replace whole store-days" and "downloads unknown = null" rules) are written here by
            day as well (0 extra calls). The weekly cache is not touched by it, and a failure here never stops it
            (the hook is in its own try; a broken capture is simply not saved this build).
  backfill  newest → oldest, GD_CHUNK_DAYS chunks, ≤ GD_BACKFILL_CHUNKS a build, with its OWN small budget (GD_MAX_CALLS
            / GD_MAX_SEC; the same stops: quota error, 403 skip): the days below the newest covered range not covered
            yet (state "cov": the day ranges committed or found empty — a chunk committed out of order, e.g. the weekly
            backfill's while the refresh is not due, leaves a gap that is filled first), back to
            today − GD_KEEP_DAYS (the weekly cache's depth) or the spend cache's first day, whichever is later — and to
            the data edge (GD_EDGE_CHUNKS chunks in a row with no cost row though their stores had spend). Country ids
            unknown to the weekly map are asked by id (gads_geo._map_ids) and kept in this store's own map — the
            weekly cache's map is only read. A chunk whose country map failed is asked again (never parked as "XX").

File data/ads_geo_day/<YYYY-MM>.json.gz (deterministic, only on change):
  {"v": 1, "month": "YYYY-MM", "ccy": base, "days": {store: {day: {cc: [cost_micros, dl | null]}}}}
  cost_micros: int base-currency micros (exact — not rounded like the weekly cells); dl: DOWNLOAD conversions,
  2 decimals, null = unknown. "XX" = Other / unmapped. days[store][day] exists (maybe {}) for every committed store-day.
  data/ads_geo_day/state.json.gz: {"ccy", "first", "till", "cov", "bfrom" (the newest covered range's first day),
  "done", "edge", "erun", "bfails", "bday", "iso", "skip", "ties"}. Ties: a weekly cell's cost = gads_geo.cell_cost(Σ
  of its days) (counted per store-week-country).
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from . import gads_geo as gg
from .gads_store import Months, cov_add, cov_next, cov_of, d, days, load_state, month_of, save_state, spend_ok

GD_V = 1
GD_DIR = "ads_geo_day"
GD_KEEP_DAYS = gg.GEO_KEEP_DAYS     # the backfill's depth = the weekly cache's
GD_CHUNK_DAYS = 28
GD_BACKFILL_CHUNKS = 2
GD_MAX_CALLS = 80                   # the day backfill's own budget per build
GD_MAX_SEC = 90
GD_EDGE_CHUNKS = 2
GD_FAIL_BACKOFF = 3
DEFAULTS = {"ccy": None, "first": None, "till": None, "cov": None, "bfrom": None, "done": False, "edge": None,
            "erun": 0, "bfails": 0, "bday": None, "iso": {}, "skip": {}, "ties": {}}


def _mk(ccy):
    return lambda m: {"v": GD_V, "month": m, "ccy": ccy, "days": {}}


class DayStore:
    """The open day store of one build (month files + state). commit() is the geo chunk's hook; save() writes."""

    def __init__(self, data_dir, base):
        self.dir = os.path.join(data_dir, GD_DIR)
        self.state = load_state(self.dir, GD_V, DEFAULTS)
        if self.state.get("ccy") not in (None, base):            # another base currency: start over
            self.state = dict(json.loads(json.dumps(DEFAULTS)), v=GD_V)
        self.state["ccy"] = base
        self.mf = Months(self.dir, _mk(base),
                         lambda o: o.get("v") == GD_V and o.get("ccy") == base and isinstance(o.get("days"), dict))
        self.broken = False
        self.st = {"stores": set(), "days": set(), "bdays": 0, "ties": [0, 0]}

    def commit(self, res, answered, replace, dlnull, a, b, iso, rate, weeks=None):
        """A committed geo chunk [a, b] → its days (the weekly rules). `weeks` (the weekly cache's weeks, read only)
        → the ties."""
        lo, hi = a.isoformat(), b.isoformat()
        cells = {}
        for x in answered:
            r_ = rate(x)
            for r in res[x]["g1"] or []:
                sid, dd = r["store_id"], r["date"]
                if not sid or sid not in replace or not lo <= dd <= hi:
                    continue
                cc = (iso.get(r["ccid"]) if r["ccid"] else None) or gg.UNMAPPED
                c = cells.setdefault((sid, dd, cc), [0.0, 0.0])
                c[0] += r["cost_micros"] * r_
            for r in res[x]["g2"] or []:
                sid, dd = r["store_id"], r["date"]
                if not sid or sid not in replace or not lo <= dd <= hi:
                    continue
                cc = (iso.get(r["ccid"]) if r["ccid"] else None) or gg.UNMAPPED
                c = cells.setdefault((sid, dd, cc), [0.0, 0.0])
                c[1] += r["dl"]
        span = days(lo, hi)
        for sid in sorted(replace):
            for dd in span:
                self.mf.get(month_of(dd))["days"].setdefault(sid, {})[dd] = {}
        for (sid, dd, cc), (cost, dl) in sorted(cells.items()):
            cost = int(round(cost))
            dl = None if sid in dlnull else round(dl, 2)
            if cost == 0 and not dl:
                continue
            self.mf.get(month_of(dd))["days"][sid][dd][cc] = [cost, dl]
        self.st["stores"] |= set(replace)
        self.st["days"] |= set(span)
        self.state["first"] = min(self.state["first"] or lo, lo)
        self.state["till"] = max(self.state["till"] or hi, hi)
        self.cover(lo, hi)
        if weeks is not None:
            self._ties(weeks, replace, a, b)

    def cover(self, lo, hi):
        """[lo, hi] settled (committed, or nothing to keep) → "cov"; a range above a gap re-opens the backfill."""
        st = self.state
        st["cov"] = cov_add(cov_of(st), lo, hi)
        if st["cov"][-1][0] > (st["bfrom"] or ""):
            st.update(done=False, erun=0)
        st["bfrom"] = st["cov"][-1][0]

    def _ties(self, weeks, replace, a, b):
        for sid in sorted(replace):
            for w in gg.mondays(a, b):
                wk = (weeks.get(sid) or {}).get(w)
                if wk is None:
                    continue
                tot = {}
                for dd in days(max(d(w), a), min(d(w) + timedelta(days=6), b)):
                    for cc, (cost, _dl) in ((self.mf.peek(month_of(dd))["days"].get(sid) or {}).get(dd) or {}).items():
                        tot[cc] = tot.get(cc, 0) + cost
                for cc in set(tot) | set(wk):
                    self.st["ties"][1] += 1
                    self.st["ties"][0] += int(gg.cell_cost(tot.get(cc, 0)) == (wk.get(cc) or [0])[0])

    def save(self):
        if self.broken:
            return 0
        n = self.mf.save()
        if n or os.path.exists(os.path.join(self.dir, "state.json.gz")) or self.state["first"]:
            save_state(self.dir, self.state)
        return n


def open_store(data_dir, spend):
    """The day store for this build, or None (no usable spend cache)."""
    if not spend_ok(spend):
        return None
    return DayStore(data_dir, spend.get("currency_src") or "USD")


def load(data_dir):
    """Every month merged → {"ccy", "days": {store: {day: {cc: [cost, dl]}}}} — the read API (None: no file)."""
    st = load_state(os.path.join(data_dir, GD_DIR), GD_V, DEFAULTS)
    if not st.get("ccy"):
        return None
    mf = Months(os.path.join(data_dir, GD_DIR), _mk(st["ccy"]),
                lambda o: o.get("v") == GD_V and o.get("ccy") == st["ccy"] and isinstance(o.get("days"), dict))
    out = {"ccy": st["ccy"], "days": {}}
    for m in mf.months():
        for sid, dd in mf.peek(m)["days"].items():
            out["days"].setdefault(sid, {}).update(dd)
    return out


def _chunk(ctx, store, spend, a, b, today, wskip):
    """One backfill chunk → "ok" | "empty" | "none" | "fail" | "stop" (the weekly _chunk's rules, days only)."""
    run = ctx.run
    own, _noacct = gg._plan(spend, a, b)
    wanted = set().union(*own.values()) if own else set()
    if not wanted:
        return "none"
    if run.stop:
        return "stop"
    if not ctx.ready():
        return "fail"
    ts = today.isoformat()
    skip = {x for x in wanted if max(wskip.get(x) or "", store.state["skip"].get(x) or "") > ts or x not in ctx.ccy}
    ask = sorted(wanted - skip)
    if ask and run.left() < 2 * len(ask) + gg.ISO_RESERVE:
        run.stop = run.stop or "calls"
        return "stop"
    res = {}
    if ask:
        with ThreadPoolExecutor(max_workers=min(gg.GEO_WORKERS, len(ask))) as ex:
            res = dict(zip(ask, ex.map(lambda x: gg._ask(ctx, x, a, b), ask)))
    until = (today + timedelta(days=gg.GEO_SKIP_DAYS)).isoformat()
    for x, r in res.items():
        if r["st"] == "403":
            store.state["skip"][x] = until
            skip.add(x)
    if any(r["st"] in ("stop", "err") for r in res.values()):
        return "stop" if all(r["st"] != "err" for r in res.values()) and run.stop else "fail"
    answered = [x for x in ask if res[x]["g1"] is not None]
    if answered and not sum(len(res[x]["g1"]) for x in answered):
        return "empty"
    ids = {r["ccid"] for x in answered for k in ("g1", "g2") for r in (res[x][k] or []) if r.get("ccid")}
    iso = ctx.iso_map
    if not gg._map_ids(ctx, {"iso": iso}, ids, today):
        return "stop" if run.stop else "fail"
    seen, dlnull = set(), set()
    lo, hi = a.isoformat(), b.isoformat()
    for x in answered:                                          # the weekly _chunk's store sets, exactly
        mine = {sid for sid, ac in own.items() if x in ac}
        mine |= {r["store_id"] for r in res[x]["g1"] if r["store_id"] and lo <= r["date"] <= hi}
        if res[x]["g2"] is None:
            dlnull |= mine
        mine |= {r["store_id"] for r in res[x]["g2"] or [] if r["store_id"] and lo <= r["date"] <= hi}
        seen |= mine
    blocked = {sid for sid, ac in own.items() if ac & skip}
    replace = (({sid for sid, ac in own.items() if ac} | seen) - blocked)
    store.commit(res, answered, replace, dlnull, a, b, iso, ctx.rate)
    return "ok"


def day_line(st, state, calls, errors):
    return ("gads geo days: stores %d, days %d, backfill days %d (%s), ties %d/%d, calls %d, errors %d"
            % (len(st["stores"]), len(st["days"]), st["bdays"], state, st["ties"][0], st["ties"][1], calls, errors))


def day_step(s, data_dir, spend, today, store, *, clock=time.monotonic, search=None, token=None, fx_fn=None,
             max_calls=GD_MAX_CALLS, max_sec=GD_MAX_SEC):
    """After the geo step (its chunks already captured into `store`): the day backfill, then save → the public line."""
    today = d(today)
    run = gg._Run(clock, max_calls, max_sec)
    state = store.state
    if store.broken or not gg._usable(s, spend):
        store.save()
        return day_line(store.st, "off" if not store.broken else "skipped", 0, 0)
    weekly = gg.load_geo(data_dir) or {}
    ctx = gg._Ctx(s, run, search, token, fx_fn, store.state["ccy"])
    ctx.iso_map = dict(weekly.get("iso") or {})
    own_iso = {k: v for k, v in (state.get("iso") or {}).items() if k not in ctx.iso_map}
    ctx.iso_map.update(own_iso)
    ts = today.isoformat()
    state["skip"] = {k: v for k, v in state["skip"].items() if isinstance(v, str) and v > ts}
    spend_first = min((x for dd in (spend.get("daily") or {}).values() for x in (dd or {})), default=None)
    floor = today - timedelta(days=GD_KEEP_DAYS)
    if spend_first:
        floor = max(floor, d(spend_first))
    if state.get("edge"):
        floor = max(floor, d(state["edge"]))
    state["cov"] = cov_of(state)
    asked = 0
    while (state["cov"] and not run.stop and asked < GD_BACKFILL_CHUNKS
           and not (int(state.get("bfails") or 0) >= GD_FAIL_BACKOFF and state.get("bday") == ts)):
        ch = cov_next(state["cov"], floor, GD_CHUNK_DAYS) if spend_first else None
        if ch is None:
            break
        a, b = ch
        r = _chunk(ctx, store, spend, a, b, today, weekly.get("skip") or {})
        if r in ("ok", "none", "empty"):
            if r != "none":
                asked += 1
            if r != "ok":                                       # nothing to keep: settled all the same
                store.cover(a.isoformat(), b.isoformat())
            state["bfails"] = 0
            if r == "empty":
                state["erun"] = int(state.get("erun") or 0) + 1
                if state["erun"] >= GD_EDGE_CHUNKS:
                    state["edge"] = a.isoformat()
                    floor = max(floor, a)
            else:
                if r == "ok":
                    state["erun"] = 0
                    store.st["bdays"] += (b - a).days + 1
        elif r == "fail":
            state["bfails"] = int(state.get("bfails") or 0) + 1
            state["bday"] = ts
            break
        else:
            break
    state["done"] = bool(state["cov"]) and (not spend_first or cov_next(state["cov"], floor, GD_CHUNK_DAYS) is None)
    state["iso"] = {k: v for k, v in ctx.iso_map.items() if k not in (weekly.get("iso") or {})}
    if store.st["ties"][1]:
        state["ties"] = {"store_week_countries": list(store.st["ties"])}
    store.save()
    word = ("edge" if state.get("edge") else "done") if state["done"] else ("filling" if state["bfrom"] else "waiting")
    return day_line(store.st, word, run.calls, run.errors)
