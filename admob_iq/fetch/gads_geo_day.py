"""Google Ads cost and downloads by COUNTRY × DAY (GADS_GEO + GADS_ARCHIVE; private data/ only, never shown, no
existing number reads it).

The geo step (fetch.gads_geo) asks Q-G1 / Q-G2 with segments.date and folds the days into Monday weeks
(roas_geo_cache*.json.gz — the Install value tab's cache, unchanged). This keeps the days:

  capture   the geo step's own chunks: when a chunk commits, the SAME rows (same accounts, same country map, same
            currency rate, same "replace whole store-days" and "downloads unknown = null" rules) are written here by
            day as well (0 extra calls). The weekly cache is not touched by it, and a failure here never stops it
            (the hook is in its own try; a broken capture is simply not saved this build). On top of the weekly rules
            (the weekly code is unchanged — the day store judges what it was handed): a store of the chunk with spend
            that the weekly chunk left out (an account under its 403 skip) is a hole; one with an account gone from the
            MCC roster is lost; a cost row of an account whose rate is not a real one is not written (a hole); a store
            written with downloads unknown, or with a row of a country id the map could not answer yet ("XX" for now),
            is a hole too (asked again by the day backfill — never settled that way). A store written in full over a
            range is out of its holes there (the refresh's next capture fills a hole before it is asked).
  backfill  newest → oldest, GD_CHUNK_DAYS chunks, ≤ GD_BACKFILL_CHUNKS a build, with its OWN small budget (GD_MAX_CALLS
            / GD_MAX_SEC — the real limit: more chunks a build while far behind, never more requests or time; a chunk is
            not started without the calls of its accounts + the country map's reserve (GD_ISO_RESERVE), or without the
            time of the longest chunk so far — the country map's calls included; the rates are looked up only then,
            and the time checked again after them; the same stops: quota error, 403 skip): the days below
            the newest covered range not covered yet (state "cov": the day ranges committed or found empty — a chunk
            committed out of order, e.g. the weekly backfill's while the refresh is not due, leaves a gap that is filled
            first), back to the spend cache's first day (the oldest day any store spent: the whole Google Ads history,
            NOT the weekly cache's GEO_KEEP_DAYS — that cache and its replay keep their own depth) — and to the data
            edge (GD_EDGE_CHUNKS chunks in a row with no cost row although a store spent in the chunk, with no account
            of the chunk unasked — one under a skip, failing, cut by the budget or left for a later build could have
            had the rows; a chunk no store spent in ("none") neither counts nor breaks the run, one with a store held
            breaks it; the days before the edge stay unknown). The floor only moves deeper: an archive "done" at a
            shallower floor goes on below its oldest day (no covered day asked again). Country ids unknown to the weekly
            map are asked by id (gads_geo._map_ids) and kept in this store's own map — the weekly cache's map is only
            read. A chunk whose country map failed is asked again (never parked as "XX"). An account billed in another
            currency goes ccy → USD → base at the build's rate, as the weekly cache and the spend cache convert (fx_fn
            has no date; roi_build then takes base → USD at each day's rate; a rate the geo step got this build is
            used again, not looked up twice).
            A chunk is settled ("cov") store by store: a store with an account that cannot answer now is not written —
              lost   an account gone from the MCC roster: those store-days stay unknown for good (state "lost");
              hole   an account under a 403 skip (the day store's or the weekly cache's — it expires), an account
                     that kept failing past the fail back-off (then not asked again that day), a cost row of an
                     account whose rate is not a real one (fx_fn gave none / 0 / not finite, raised, or
                     google_ads._fx_to_usd fell to its blind 1.0 for a currency it has no rate of — never written at a
                     guessed rate; counted in errors; its downloads and other stores are written), an account the
                     budget cut before its Q-G1 or whose rows need a country id the budget left unmapped, or a store
                     left for a later build because the chunk's accounts need more calls than a whole build has
                     (asked store by store, fewest accounts first; counted in errors). A store whose Q-G2 failed or was cut (Q-G1
                     answered) is written with its cost and downloads unknown AND is a hole (asked again for the
                     downloads; given up, the cost stays). State "holes" [first, last, store, made, last asked]. Holes
                     come first in a build, inside the same chunk cap and budget: only their stores' accounts, once a
                     day at most, not while an account of them is skipped, not while a rate is still missing (nothing
                     asked); given up after GD_HOLE_DAYS ("lost"). A cut never stalls: the chunk is settled with the
                     stores that answered and the rest as holes (one budget cut counted in errors).
            The archive is "done" only with no hole left. A chunk whose stores with spend all cannot answer is settled
            with nothing written ("skip": no backfill days counted; the edge run broken when a store of it is a hole).
  rules     a state settled under older rules (no "rules": GD_RULES) is reconciled once: every covered store-day that
            spent (a store with an account) but was never written, or was written with downloads unknown, becomes a
            hole (not one already given up); an edge found by an older evidence rule is cleared and found again.

File data/ads_geo_day/<YYYY-MM>.json.gz (deterministic, only on change):
  {"v": 1, "month": "YYYY-MM", "ccy": base, "days": {store: {day: {cc: [cost_micros, dl | null]}}}}
  cost_micros: int base-currency micros (exact — not rounded like the weekly cells); dl: DOWNLOAD conversions,
  2 decimals, null = unknown. "XX" = Other / unmapped. days[store][day] exists (maybe {}) for every committed store-day.
  data/ads_geo_day/state.json.gz: {"ccy", "first", "till", "cov", "bfrom" (the newest covered range's first day),
  "done", "edge", "erun", "bfails", "bday", "iso", "skip", "ties", "holes", "lost" ([first, last, store], one range per
  run of days), "rules"}. Ties: a weekly cell's cost = gads_geo.cell_cost(Σ of its days) (counted per
  store-week-country).
"""

import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from . import gads_geo as gg
from . import google_ads as gads
from .gads_store import Months, cov_add, cov_next, cov_of, d, days, load_state, month_of, save_state, spend_ok

GD_V = 1
GD_DIR = "ads_geo_day"
GD_CHUNK_DAYS = 28
GD_BACKFILL_CHUNKS = 6              # chunks a build at most (while far behind; caught up, a gap is a chunk or two)
GD_MAX_CALLS = 80                   # the day backfill's own budget per build — the limit that binds first while an
                                    # old chunk's accounts are many (2 requests each + the map's reserve)
GD_MAX_SEC = 90
GD_EDGE_CHUNKS = 2
GD_FAIL_BACKOFF = 3
GD_HOLE_DAYS = 30                   # a hole not filled this many days after it was made is given up ("lost": unknown)
GD_ISO_RESERVE = 4                  # calls kept free in a chunk for the by-id country map: the ids, then their parents,
                                    # each asked once more by resource name after an HTTP 400 (google_ads._geo_iso)
GD_RULES = 2                        # the hole / edge rules a state is settled under (older: reconciled once)
DEFAULTS = {"ccy": None, "first": None, "till": None, "cov": None, "bfrom": None, "done": False, "edge": None,
            "erun": 0, "bfails": 0, "bday": None, "iso": {}, "skip": {}, "ties": {}, "holes": [], "lost": [],
            "rules": None}


def _mk(ccy):
    return lambda m: {"v": GD_V, "month": m, "ccy": ccy, "days": {}}


def _prev(x):
    return (d(x) - timedelta(days=1)).isoformat()


def _next(x):
    return (d(x) + timedelta(days=1)).isoformat()


def _gaps(ranges, lo, hi):
    """The parts of [lo, hi] outside every range of `ranges` [(first, last)] → [(first, last)]."""
    out, cur = [], lo
    for a, b in sorted(ranges):
        if b < cur or a > hi:
            continue
        if a > cur:
            out.append((cur, _prev(a)))
        cur = max(cur, _next(b))
        if cur > hi:
            break
    if cur <= hi:
        out.append((cur, hi))
    return out


def _merged(lost):
    """Lost store-ranges {(first, last, store)} → one range per run of days of a store, sorted."""
    by = {}
    for lo, hi, sid in lost:
        by.setdefault(sid, []).append([lo, hi])
    return sorted((a, b, sid) for sid, rs in by.items() for a, b in cov_add(rs[1:], *rs[0]))


def _fx_ok(ccy, v, fn):
    """A currency's rate to USD as the geo step got it is a real one (not none / 0 / not finite, not
    google_ads._fx_to_usd's blind 1.0 for a currency outside its table)."""
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(v) and v > 0):
        return False
    return not (fn is gads._fx_to_usd and ccy != "USD" and ccy not in gads._FX_FALLBACK and v == 1.0)


def _wctx(rate):
    """The geo step's context behind a capture's rate (its ctx.rate), or None (another callable)."""
    c = getattr(rate, "__self__", None)
    return c if isinstance(getattr(c, "ccy", None), dict) and isinstance(getattr(c, "_usd", None), dict) else None


def _real_rate(rate, x):
    """A capture's rate of account x is a real one: a finite number > 0 and, for an account billed in another currency,
    both currencies' rates real (the geo step divides by 1.0 where the base has none)."""
    try:
        v = float(rate(x))
    except Exception:
        return False
    if not (math.isfinite(v) and v > 0):
        return False
    c = _wctx(rate)
    if c is None:
        return True
    cur = c.ccy.get(x) or c.base
    return cur == c.base or all(_fx_ok(k, c._usd.get(k), c.fx_fn) for k in (cur, c.base))


class DayStore:
    """The open day store of one build (month files + state + holes). commit() is the geo chunk's hook; save()
    writes."""

    def __init__(self, data_dir, base, spend=None):
        self.dir = os.path.join(data_dir, GD_DIR)
        self.state = load_state(self.dir, GD_V, DEFAULTS)
        if self.state.get("ccy") not in (None, base):            # another base currency: start over
            self.state = dict(json.loads(json.dumps(DEFAULTS)), v=GD_V)
        self.state["ccy"] = base
        if self.state.get("rules") != GD_RULES and not cov_of(self.state):
            self.state["rules"] = GD_RULES                        # nothing settled yet: nothing to reconcile
        self.mf = Months(self.dir, _mk(base),
                         lambda o: o.get("v") == GD_V and o.get("ccy") == base and isinstance(o.get("days"), dict))
        self.spend = spend if isinstance(spend, dict) else {}
        self.holes = {(h[0], h[1], h[2]): [h[3], h[4]] for h in self.state.get("holes") or []
                      if isinstance(h, list) and len(h) == 5}
        self.lost = {tuple(x) for x in self.state.get("lost") or [] if isinstance(x, list) and len(x) == 3}
        self.ts = None                                            # today, once the day step began
        self.pending = []                                         # the captures' holes, made when the day step begins
        self.wfx = {}                                             # the geo step's real rates to USD of this build
        self.broken = False
        self.st = {"stores": set(), "days": set(), "bdays": 0, "ties": [0, 0]}

    def commit(self, res, answered, replace, dlnull, a, b, iso, rate, weeks=None):
        """A committed chunk [a, b] → its days (the weekly rules). `weeks` (the weekly cache's weeks, read only): a
        capture → the ties, and the day rules on top (see the module doc)."""
        lo, hi = a.isoformat(), b.isoformat()
        write, bad = set(replace), set()
        if weeks is not None:
            c = _wctx(rate)
            if c is not None:
                self.wfx.update({k: float(v) for k, v in c._usd.items() if _fx_ok(k, v, c.fx_fn)})
            own, _ = gg._plan(self.spend, a, b)
            for sid, ac in own.items():
                if ac and sid not in write:                       # left out by the weekly chunk: 403 skip / gone
                    if c is not None and c.ok and ac - set(c.ccy):
                        self.lost.add((lo, hi, sid))
                    else:
                        bad.add(sid)
            for x in answered:
                if not _real_rate(rate, x):                       # never written at a guessed rate
                    hit = {r["store_id"] for r in res[x]["g1"] or []
                           if r["store_id"] and lo <= r["date"] <= hi and r["cost_micros"]} & write
                    write -= hit
                    bad |= hit
            unm = {r["store_id"] for x in answered for k in ("g1", "g2") for r in (res[x][k] or [])
                   if r.get("ccid") and r["ccid"] not in iso and r["store_id"] and lo <= r["date"] <= hi}
            bad |= (unm | set(dlnull)) & write                    # written for now ("XX" / downloads null), asked again
        cells = {}
        for x in answered:
            r_ = rate(x)
            for r in res[x]["g1"] or []:
                sid, dd = r["store_id"], r["date"]
                if not sid or sid not in write or not lo <= dd <= hi:
                    continue
                cc = (iso.get(r["ccid"]) if r["ccid"] else None) or gg.UNMAPPED
                c_ = cells.setdefault((sid, dd, cc), [0.0, 0.0])
                c_[0] += r["cost_micros"] * r_
            for r in res[x]["g2"] or []:
                sid, dd = r["store_id"], r["date"]
                if not sid or sid not in write or not lo <= dd <= hi:
                    continue
                cc = (iso.get(r["ccid"]) if r["ccid"] else None) or gg.UNMAPPED
                c_ = cells.setdefault((sid, dd, cc), [0.0, 0.0])
                c_[1] += r["dl"]
        span = days(lo, hi)
        for sid in sorted(write):
            for dd in span:
                self.mf.get(month_of(dd))["days"].setdefault(sid, {})[dd] = {}
        for (sid, dd, cc), (cost, dl) in sorted(cells.items()):
            cost = int(round(cost))
            dl = None if sid in dlnull else round(dl, 2)
            if cost == 0 and not dl:
                continue
            self.mf.get(month_of(dd))["days"][sid][dd][cc] = [cost, dl]
        self.st["stores"] |= write
        self.st["days"] |= set(span)
        self.state["first"] = min(self.state["first"] or lo, lo)
        self.state["till"] = max(self.state["till"] or hi, hi)
        self.cover(lo, hi)
        # a capture's holes: made with today's date when the day step begins; the day backfill's own holes are its
        # chunk's (held stores, downloads unknown) — only the stores written in full leave their holes here
        self.settle(lo, hi, write - bad - (set(dlnull) if weeks is None else set()), bad)
        if weeks is not None:
            self._ties(weeks, write, a, b)

    def cover(self, lo, hi):
        """[lo, hi] settled (committed, or nothing to keep) → "cov"; a range above a gap re-opens the backfill."""
        st = self.state
        st["cov"] = cov_add(cov_of(st), lo, hi)
        if st["cov"][-1][0] > (st["bfrom"] or ""):
            st.update(done=False, erun=0)
        st["bfrom"] = st["cov"][-1][0]

    def settle(self, lo, hi, clean, bad):
        """[lo, hi]: the `clean` stores written in full leave their holes there (a hole partly inside keeps the rest,
        the same age); the `bad` ones get a hole made today for the days not a hole or lost already."""
        if self.ts is None:
            self.pending.append((lo, hi, set(clean), set(bad)))
            return
        for sid in sorted(clean):
            for k in [k for k in self.holes if k[2] == sid and k[0] <= hi and lo <= k[1]]:
                v = self.holes.pop(k)
                if k[0] < lo:
                    self.holes[(k[0], _prev(lo), sid)] = list(v)
                if hi < k[1]:
                    self.holes[(_next(hi), k[1], sid)] = list(v)
        for sid in sorted(bad):
            self.hole(sid, lo, hi)

    def hole(self, sid, lo, hi):
        have = [(k[0], k[1]) for k in list(self.holes) + list(self.lost) if k[2] == sid]
        for a, b in _gaps(have, lo, hi):
            self.holes[(a, b, sid)] = [self.ts, self.ts]

    def begin(self, ts):
        """The day step begins (today = ts): the captures' holes made; a state of older rules reconciled once."""
        self.ts = ts
        for p in self.pending:
            self.settle(*p)
        self.pending = []
        if self.state.get("rules") != GD_RULES:
            self._reconcile()

    def _reconcile(self):
        """Every covered store-day that spent (a store with an account) and was never written, or was written with
        downloads unknown → a hole (pieces of ≤ GD_CHUNK_DAYS, not a day given up already); the edge found again."""
        st = self.state
        st.update(edge=None, erun=0, done=False)
        cov = cov_of(st)
        camps = self.spend.get("campaigns") or {}
        want = {}
        for sid, dd in sorted((self.spend.get("daily") or {}).items()):
            if not any(c.get("account") for c in camps.get(sid) or []):
                continue
            for x, v in (dd or {}).items():
                if (v or 0) > 0 and any(a <= x <= b for a, b in cov):
                    want.setdefault(month_of(x), {}).setdefault(sid, []).append(x)
        miss = {}
        for m in sorted(want):
            got = self.mf.peek(m)["days"]
            for sid, xs in want[m].items():
                have = got.get(sid) or {}
                for x in xs:
                    e = have.get(x)
                    if e is None or any(isinstance(v, list) and len(v) > 1 and v[1] is None for v in e.values()):
                        miss.setdefault(sid, []).append(x)
            if m not in self.mf.touched:
                self.mf.got.pop(m, None)                          # one month in memory at a time
        for sid, xs in sorted(miss.items()):
            xs.sort(reverse=True)
            i = 0
            while i < len(xs):
                lim = (d(xs[i]) - timedelta(days=GD_CHUNK_DAYS - 1)).isoformat()
                j = i
                while j + 1 < len(xs) and xs[j + 1] >= lim:
                    j += 1
                self.hole(sid, xs[j], xs[i])
                i = j + 1
        st["rules"] = GD_RULES

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
        self.state["holes"] = [[lo, hi, sid, v[0], v[1]] for (lo, hi, sid), v in sorted(self.holes.items())]
        self.state["lost"] = [list(k) for k in _merged(self.lost)] if self.lost else []
        n = self.mf.save()
        if n or os.path.exists(os.path.join(self.dir, "state.json.gz")) or self.state["first"]:
            save_state(self.dir, self.state)
        return n


def open_store(data_dir, spend):
    """The day store for this build, or None (no usable spend cache)."""
    if not spend_ok(spend):
        return None
    return DayStore(data_dir, spend.get("currency_src") or "USD", spend)


def load(data_dir, keep=None):
    """Every month merged → {"ccy", "days": {store: {day: {cc: [cost, dl]}}}} — the read API (None: no file). keep: only
    these store ids, one month file in memory at a time (a reader of one app's stores never holds the archive)."""
    st = load_state(os.path.join(data_dir, GD_DIR), GD_V, DEFAULTS)
    if not st.get("ccy"):
        return None
    mf = Months(os.path.join(data_dir, GD_DIR), _mk(st["ccy"]),
                lambda o: o.get("v") == GD_V and o.get("ccy") == st["ccy"] and isinstance(o.get("days"), dict))
    out = {"ccy": st["ccy"], "days": {}}
    for m in mf.months():
        for sid, dd in mf.peek(m)["days"].items():
            if keep is None or sid in keep:
                out["days"].setdefault(sid, {}).update(dd)
        if keep is not None:
            mf.got.pop(m, None)
    return out


def _fx_real(ccy):
    """google_ads._fx_to_usd (live, else the last good rate saved, else its near-live table), but None where it can
    only guess: a currency outside its table with no live / saved rate gets a blind 1.0 there — never used here."""
    v = gads._fx_to_usd(ccy)
    if ccy != "USD" and ccy not in gads._FX_FALLBACK and v == 1.0:
        return None
    return v


def _rate(ctx, x):
    """Account x's currency → base (ccy → USD → base, the weekly cache's ctx.rate and the spend cache's _aggregate
    rule; 1.0 in the base currency), or None: no real rate (fx_fn gave none / 0 / not finite for either currency, or
    raised). Each currency asked once a build (a real rate the geo step got this build is not asked again)."""
    ccy = ctx.ccy.get(x) or ctx.base
    if ccy == ctx.base:
        return 1.0
    for c in (ccy, ctx.base):
        if c not in ctx.fxr:
            try:
                v = float(ctx.fx_fn(c) or 0)
            except Exception:
                v = 0.0
            ctx.fxr[c] = v if math.isfinite(v) and v > 0 else None
    u, b = ctx.fxr[ccy], ctx.fxr[ctx.base]
    return u / b if u and b else None


def _late(run):
    """No time left for a chunk: the longest chunk so far would not fit; the build's first (none measured yet) not
    started past half the budget."""
    return run.elapsed() + run.chunk_sec > run.max_sec or (not run.chunk_sec and run.elapsed() > run.max_sec / 2)


def _chunk(ctx, store, spend, a, b, today, wskip, only=None, strict=True):
    """One chunk [a, b] → (result, held stores, lost stores). result: "ok" | "empty" | "none" | "skip" | "wait" |
    "fail" | "stop" (the weekly _chunk's rules, days only). "skip": nothing to write — every store that spent has an
    account that cannot answer now. Held (a hole: asked again): a store with an account under a 403 skip (expires), an
    account that kept failing (strict off: past the fail back-off), an account the budget cut, a cost row of an account
    with no real rate, a row of a country id the budget left unmapped, a store left for a later build (more accounts
    than a whole build's calls), or a store written with downloads unknown. Lost (unknown for good): a store with an
    account gone from the MCC roster. only: a hole's re-ask — just these stores ("wait": an account of them still has
    no real rate, nothing asked). "stop": nothing asked (no calls / time left) or nothing kept (an error under the stop)
    — the chunk is asked again."""
    run = ctx.run
    state = store.state
    own, _noacct = gg._plan(spend, a, b)
    if only is not None:
        own = {sid: ac for sid, ac in own.items() if sid in only}
    wanted = set().union(*own.values()) if own else set()
    if not wanted:
        return "none", set(), set()
    if run.stop:
        return "stop", set(), set()
    if not ctx.ready():
        return "fail", set(), set()
    ts = today.isoformat()
    gone = {x for x in wanted if x not in ctx.ccy}
    held = {x for x in wanted - gone if max(wskip.get(x) or "", state["skip"].get(x) or "") > ts}
    lost = {sid for sid, ac in own.items() if ac & gone}
    ask = sorted(wanted - gone - held)
    defer = set()
    room = run.max_calls - 1                                    # a whole build's calls after the roster
    if 2 * len(ask) + GD_ISO_RESERVE > room >= 2 + GD_ISO_RESERVE:
        # more accounts than a whole build can ask: the stores that fit (fewest accounts first), the others left for a
        # later build (holes) — never a chunk refused at every build
        acc = set()
        free = (s for s, ac in own.items() if ac and not ac & (gone | held))
        for sid in sorted(free, key=lambda s: (len(own[s]), s)):
            if 2 * len(acc | own[sid]) + GD_ISO_RESERVE <= room:
                acc |= own[sid]
            else:
                defer.add(sid)
        ask = sorted(acc)
    if ask and run.left() < 2 * len(ask) + GD_ISO_RESERVE:
        run.stop = run.stop or "calls"
        return "stop", set(), set()
    if ask and _late(run):
        run.stop = run.stop or "time"
        return "stop", set(), set()
    rates = {x: _rate(ctx, x) for x in ask}                     # only now: a refused chunk looks up no rate
    if only is not None and any(r_ is None for r_ in rates.values()):
        return "wait", set(), set()
    if ask and _late(run):                                      # the look-ups took the time
        run.stop = run.stop or "time"
        return "stop", set(), set()
    res = {}
    t0 = run.clock()
    if ask:
        with ThreadPoolExecutor(max_workers=min(gg.GEO_WORKERS, len(ask))) as ex:
            res = dict(zip(ask, ex.map(lambda x: gg._ask(ctx, x, a, b), ask)))
        run.chunk_sec = max(run.chunk_sec, run.clock() - t0)
    until = (today + timedelta(days=gg.GEO_SKIP_DAYS)).isoformat()
    for x, r in res.items():
        if r["st"] == "403":
            state["skip"][x] = until
            held.add(x)
    err = {x for x, r in res.items() if r["st"] == "err"}
    if err and (strict or run.stop):
        return "fail", set(), set()
    if err:                                         # past the back-off: an account that keeps failing holds only its
        tmr = (today + timedelta(days=1)).isoformat()   # stores (a hole) and is not asked again today (this store's
        for x in err:                                   # own skip; the weekly cache's skip is never written here)
            state["skip"][x] = max(state["skip"].get(x) or "", tmr)
        held |= err
    # the budget (time / quota) cut the chunk: an account refused before its Q-G1 holds its stores; one refused before
    # its Q-G2 is written with its downloads unknown and held — the chunk is settled all the same (never a stall)
    cut = {x for x, r in res.items() if r["st"] == "stop"}
    short = bool(cut or defer or (run.stop and any(r["st"] is None and r["g2"] is None for r in res.values())))
    run.errors += short
    answered = [x for x in ask if res[x]["g1"] is not None]
    lo, hi = a.isoformat(), b.isoformat()
    hold = {sid for sid, ac in own.items() if ac & (held | cut)} | defer
    for x in answered:                              # no real rate: the stores its cost rows are of are held (no
        if rates[x] is None:                        # guessed rate written); its downloads and other stores are fine
            hit = {r["store_id"] for r in res[x]["g1"] if r["store_id"] and lo <= r["date"] <= hi and r["cost_micros"]}
            run.errors += bool(hit)
            hold |= hit
    if only is not None:
        hold &= only
    hold -= lost
    if answered and not sum(len(res[x]["g1"]) for x in answered):
        # the data edge's evidence: a store that spent in the chunk with no cost row, and no account of the chunk that
        # could have had the rows unasked (skipped, failing, cut, left for later)
        ev = only is None and not (held | cut | defer) and any(ac and not ac & gone for ac in own.values())
        return ("empty" if ev else "skip"), hold, lost
    ids = {r["ccid"] for x in answered for k in ("g1", "g2") for r in (res[x][k] or []) if r.get("ccid")}
    iso = ctx.iso_map
    if not gg._map_ids(ctx, {"iso": iso}, ids, today):
        if not run.stop:
            return "fail", set(), set()
        # the budget refused the map: the stores with a row of an id not mapped yet are held (never parked as "XX")
        unm = {i for i in ids if i not in iso}
        hit = {r["store_id"] for x in answered for k in ("g1", "g2") for r in (res[x][k] or [])
               if r.get("ccid") in unm and r["store_id"] and lo <= r["date"] <= hi}
        hold |= (hit & only if only is not None else hit) - lost
        run.errors += not short
    if ask:
        run.chunk_sec = max(run.chunk_sec, run.clock() - t0)   # the map's calls are the chunk's time too
    seen, dlnull = set(), set()
    for x in answered:                                          # the weekly _chunk's store sets, exactly
        mine = {sid for sid, ac in own.items() if x in ac}
        mine |= {r["store_id"] for r in res[x]["g1"] if r["store_id"] and lo <= r["date"] <= hi}
        if res[x]["g2"] is None:
            dlnull |= mine
        mine |= {r["store_id"] for r in res[x]["g2"] or [] if r["store_id"] and lo <= r["date"] <= hi}
        seen |= mine
    replace = ({sid for sid, ac in own.items() if ac} | seen) - lost - hold
    if only is not None:
        replace &= only
    if not replace:
        return "skip", hold, lost
    store.commit(res, answered, replace, dlnull, a, b, iso, lambda x: rates[x] or 0.0)  # (no rate: only 0-cost rows)
    return "ok", hold | (dlnull & replace), lost        # downloads unknown: the cost is written, the store asked again


def _due(spend, holes, wskip, skip, ts):
    """The newest hole range due again (not asked today, no account of its stores under a 403 skip) → (lo, hi, its due
    stores), or None."""
    camps = spend.get("campaigns") or {}

    def free(sid):
        return all(max(wskip.get(x) or "", skip.get(x) or "") <= ts
                   for x in {str(c.get("account")) for c in (camps.get(sid) or []) if c.get("account")})
    due = {}
    for (lo, hi, sid), (_since, tried) in holes.items():
        if tried < ts and free(sid):
            due.setdefault((lo, hi), set()).add(sid)
    if not due:
        return None
    lo, hi = max(due, key=lambda k: (k[1], k[0]))
    return lo, hi, due[(lo, hi)]


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
    ctx = gg._Ctx(s, run, search, token, fx_fn or _fx_real, store.state["ccy"])
    ctx.fxr = dict(store.wfx)
    ctx.iso_map = dict(weekly.get("iso") or {})
    own_iso = {k: v for k, v in (state.get("iso") or {}).items() if k not in ctx.iso_map}
    ctx.iso_map.update(own_iso)
    ts = today.isoformat()
    state["skip"] = {k: v for k, v in state["skip"].items() if isinstance(v, str) and v > ts}
    if store.spend is not spend:
        store.spend = spend if isinstance(spend, dict) else {}
    store.begin(ts)                                             # the captures' holes; older rules reconciled once
    holes, lost = store.holes, store.lost
    spend_first = min((x for dd in (spend.get("daily") or {}).values() for x in (dd or {})), default=None)
    floor = d(spend_first) if spend_first else today        # the whole Google Ads history (not the weekly depth)
    if state.get("edge"):
        floor = max(floor, d(state["edge"]))
    state["cov"] = cov_of(state)
    old = (today - timedelta(days=GD_HOLE_DAYS)).isoformat()
    for k in [k for k, (since, _t) in holes.items() if since <= old]:     # given up: those store-days stay unknown
        lost.add(k)
        del holes[k]
    wskip = weekly.get("skip") or {}
    asked = 0
    while (not run.stop and asked < GD_BACKFILL_CHUNKS
           and not (int(state.get("bfails") or 0) >= GD_FAIL_BACKOFF and state.get("bday") == ts)):
        strict = int(state.get("bfails") or 0) < GD_FAIL_BACKOFF
        h = _due(spend, holes, wskip, state["skip"], ts) if holes else None
        if h:                                                   # holes first: only their stores, the same budget
            lo, hi, only = h
            since = {sid: holes[(lo, hi, sid)][0] for sid in only}
            r, hold, gone = _chunk(ctx, store, spend, d(lo), d(hi), today, wskip, only=only, strict=False)
            if r == "stop":
                break
            for sid in only:
                if (lo, hi, sid) in holes:
                    holes[(lo, hi, sid)][1] = ts                # asked today (or still no rate): not again today
            if r == "fail":
                state["bfails"] = int(state.get("bfails") or 0) + 1
                state["bday"] = ts
                break
            if r != "wait":                                     # settled: still held stores stay holes (same age)
                for sid in only:
                    holes.pop((lo, hi, sid), None)
                for sid in hold:
                    holes[(lo, hi, sid)] = [since.get(sid, ts), ts]
                lost |= {(lo, hi, sid) for sid in gone}
                asked += r != "none"
                state["bfails"] = 0                             # a re-ask that answered ends a run of failures too
            continue
        ch = cov_next(state["cov"], floor, GD_CHUNK_DAYS) if spend_first and state["cov"] else None
        if ch is None:
            break
        a, b = ch
        r, hold, gone = _chunk(ctx, store, spend, a, b, today, wskip, strict=strict)
        if r in ("ok", "none", "empty", "skip"):
            if r != "none":
                asked += 1
            if r != "ok":                                       # nothing to keep: settled all the same
                store.cover(a.isoformat(), b.isoformat())
            for sid in hold:
                holes[(a.isoformat(), b.isoformat(), sid)] = [ts, ts]
            lost |= {(a.isoformat(), b.isoformat(), sid) for sid in gone}
            state["bfails"] = 0
            if r == "empty":
                state["erun"] = int(state.get("erun") or 0) + 1
                if state["erun"] >= GD_EDGE_CHUNKS:
                    state["edge"] = a.isoformat()
                    floor = max(floor, a)
            elif r == "ok" or hold:                             # a store of it held: its rows unknown — no run across
                state["erun"] = 0
                if r == "ok":
                    store.st["bdays"] += (b - a).days + 1
        elif r == "fail":
            state["bfails"] = int(state.get("bfails") or 0) + 1
            state["bday"] = ts
            break
        else:
            break
    state["done"] = (bool(state["cov"]) and not holes
                     and (not spend_first or cov_next(state["cov"], floor, GD_CHUNK_DAYS) is None))
    state["iso"] = {k: v for k, v in ctx.iso_map.items() if k not in (weekly.get("iso") or {})}
    if store.st["ties"][1]:
        state["ties"] = {"store_week_countries": list(store.st["ties"])}
    store.save()
    word = ("edge" if state.get("edge") else "done") if state["done"] else ("filling" if state["bfrom"] else "waiting")
    return day_line(store.st, word, run.calls, run.errors)
