"""🆕 First open BY COUNTRY — the hourly fetch (owner, 20 Oct 2026: "country wise bhi dekh saku esa kara do").

The same strict GA4 funnel as fetch.ga4_firstopen (first_open → Splash ≤ 10 min → Home ≤ 60 min, Home never above the
Splash), per app per day per COUNTRY, for EVERY country (nothing cut, no "top N"):
  1. the day's countries: runReport first_open users by countryId (one call for all the days asked, no row limit);
  2. the day's total: the funnel once, as the First open fetch reads it;
  3. the countries in groups of GROUP (15, GA4's funnel breakdown limit): the funnel with step 1 = first_open IN the
     group's countries, broken down by countryId — every value of the group comes back for every step.
Measured on the real properties (ga4_firstopen_country_probe, 20 Oct 2026): the group read equals a single-country
funnel exactly, while reading "the top 15, then the next 15 …" by leaving countries out of step 1 lost 1–7 % (GA4 picks
each STEP's top 15 on its own, so an edge country could come back with first_open 0 and be left out after).
GA4's RESERVED_TOTAL row is dropped; what GA4 named no country for ("(not set)", thresholds) is the day's total minus
the named countries, worked out by the build — never spread over countries.

GA4 keeps event data only as long as the property's retention (2 months), so this store is the history: kept for good in
data/ga4_firstopen_cc/<key>.json.gz (private repo):
    {"v", "app_id", "package", "property_id", "stream_id", "time_zone", "recent_at",
     "days": {D: {"c": {cc: [first_open, splash, home]}, "t": [first_open, splash, home], "smp": share GA4 read | null,
                  "fin": final when read, "sg": the screens' signature, "at"}
               | {"none": true, "why": "ga4", "n": empty answers, "fo": {cc: first_open users}, "at"}   GA4's funnel
                 has nothing left for the day, but its report still names the countries' first opens ("fo")
               | {"none": true, "at"}}}                                  GA4 named no country that day
Per app and run (its screens come from the First open store; at most MAX_CALLS calls — a day is begun only when ALL its
calls still fit, so the cap never cuts one; the property's quota floors):
  * the backfill days AT_RISK_DAYS or more old FIRST, oldest first: GA4 deletes the oldest days next (2 months'
    retention, in batches) and a deleted day can never be read again;
  * every REFRESH_HOURS the last RECENT_DAYS days again (not final: GA4 still adds to them) — "recent_at" is set as soon
    as they are read, so a run cut later in the backfill does not read them again next hour;
  * a day read while not final is read once more when it is (≥ FINAL_LAG days old);
  * the rest of the backfill, from the First open store's own first day (the All countries table's day 1; no store:
    BACKFILL_DAYS back), oldest first.
A day whose funnel GA4 answers empty: younger than AT_RISK_DAYS GA4 has not deleted it — nothing is stored and it is
asked again; older, it is kept as {"none": true, "why": "ga4"} with the first opens GA4's report still gives per country
("fo": the report is not cut by the retention; the page shows them, the funnel steps "—"), asked once more on a later
run (GONE_CONFIRM answers) before it is final. Nothing is stored as zeros.
Properties run side by side (each has its own quota), the property whose apps waited longest first (each app's
"turn"), so a big property never keeps the others waiting run after run. Within a day, the group calls go up to BATCH
side by side — only when the property's last quota snapshot and the run's clock show the one-at-a-time calls would all
have gone (App.batch_ok, with room); their answers are read in group order, so the day's record is the same.
Switched by GA4_FIRSTOPEN_CC (on by default in the workflow).
Never raises; never prints (log_line: counts only).
"""
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import ga4_probe
from ..db import write_json_gz_stable
from . import ga4
from . import ga4_audience as gaud
from . import ga4_firstopen as gf
from . import ga4_uninstall as gu

DIR = "ga4_firstopen_cc"
STORE_V = 1
GROUP = gf.CHUNK                    # GA4's funnel breakdown returns at most 15 values per call
DIM = "countryId"
RT = "RESERVED_TOTAL"               # GA4's own total row in a funnel breakdown
RECENT_DAYS = 3                     # today … 2 days back: refreshed every REFRESH_HOURS
FINAL_LAG = 3                       # a day is final from 3 days old on (as the First open status reads it)
BACKFILL_DAYS = 120                 # how far back without a First open store day 1 (with one: from that day)
AT_RISK_DAYS = 50                   # a day this old may be the next GA4 deletes: read before the recent refresh;
                                    # an empty funnel answer for a younger day is never taken as "gone"
GONE_CONFIRM = 2                    # empty funnel answers (on different runs) before a day is final as gone
REFRESH_HOURS = 6.0
MAX_CALLS = 150                     # per app per run, passed to the App (the backfill goes on next run)
BUDGET_SEC = 240
RETRY_HOURS = 3.0
WORKERS = 10                        # properties read side by side (each its own quota; one call at a time each …)
BATCH = 5                           # … but a day's group calls up to this many side by side when the one-at-a-time
                                    # calls would all go (App.funnel_many; GA4 allows 10 concurrent per property).
                                    # GA4_FIRSTOPEN_CC_BATCH (env) 1: one at a time, as before


def sig(steps):
    return hashlib.sha1(("%s|%s" % (steps.get("splash"), steps.get("home"))).encode()).hexdigest()[:8]


def group_body(splash, home, day, ccs):
    """The strict Home funnel of one day, step 1 = first_open in `ccs` (≤ GROUP), broken down by country."""
    b = gf.funnel_body(splash, home, day, day, DIM)
    b["funnel"]["steps"][0]["filterExpression"] = {"andGroup": {"expressions": [
        {"funnelEventFilter": {"eventName": "first_open"}},
        {"funnelFieldFilter": {"fieldName": DIM, "inListFilter": {"values": sorted(ccs)}}}]}}
    return b


def _three(t, key=None):
    """parse_table's {step: {value: users}} → [first_open, splash, home] of one value (key) or of all but RT."""
    pick = (lambda d: d.get(key, 0)) if key is not None else (lambda d: sum(v for b, v in d.items() if b != RT))
    return [pick(t.get("first_open") or {}), pick(t.get("splash") or {}), pick(t.get("step") or {})]


def countries(ga, a, b):
    """first_open users by country of every day a … b → {D: {cc: users}} (GA4's "(not set)" left out: it can not be a
    group's filter value; it stays in the day's total)."""
    rows = ga.report_all({"dateRanges": [{"startDate": a.isoformat(), "endDate": b.isoformat()}],
                          "dimensions": [{"name": "date"}, {"name": DIM}], "metrics": [{"name": "activeUsers"}]},
                         event="first_open")
    out = {}
    for r in rows:
        d, cc = str(r.get("date") or ""), str(r.get(DIM) or "")
        if len(d) == 8 and d.isdigit() and cc and cc not in ga4.NOT_SET:
            out.setdefault("%s-%s-%s" % (d[:4], d[4:6], d[6:]), {})[cc] = int(r.get("activeUsers") or 0)
    return out


def calls_for(ccs):
    """The funnel calls one day costs: its total + one per group of GROUP countries."""
    return 1 + -(-len(ccs) // GROUP)


def is_gone(rec):
    return isinstance(rec, dict) and bool(rec.get("none")) and rec.get("why") == "ga4"


def read_day(ga, steps, day, ccs, today, now_iso, prev=None):
    """One day → its record (every group read, or Stop: a day is kept only whole), or None (nothing to store yet)."""
    j = ga.funnel(gf.funnel_body(steps["splash"], steps["home"], day, day, "date"))
    tot, smp = _three(gf.parse_table(j)), gf.sampling(j)
    if not any(tot):                                    # GA4's report named first opens that day, its funnel nothing
        if (today - day).days < AT_RISK_DAYS:
            return None                                 # not deleted yet (too young): a lag or a blip — asked again
        n = (int(prev.get("n") or 1) + 1) if is_gone(prev) else 1
        return {"none": True, "why": "ga4", "n": n, "fo": {k: int(v) for k, v in ccs.items()}, "at": now_iso}
    c = {}
    order = sorted(ccs, key=lambda k: (-ccs[k], k))
    groups = [order[i:i + GROUP] for i in range(0, len(order), GROUP)]
    for grp, j in _answers(ga, [(g, group_body(steps["splash"], steps["home"], day, g)) for g in groups]):
        t, s = gf.parse_table(j), gf.sampling(j)
        if s is not None:
            smp = s if smp is None else min(smp, s)
        for cc in grp:
            v = _three(t, cc)
            if any(v):
                c[cc] = v
    return {"c": c, "t": tot, "smp": smp, "fin": (today - day).days >= FINAL_LAG, "sg": sig(steps), "at": now_iso}


def _batch():
    try:
        return max(1, int(os.getenv("GA4_FIRSTOPEN_CC_BATCH") or BATCH))
    except ValueError:
        return BATCH


def _answers(ga, groups):
    """[(group, funnel body)] → (group, GA4's answer) in group order: as many as BATCH side by side as the App can tell
    the one-at-a-time calls would all go (funnel_many; else None — fewer tried, down to 2), one at a time otherwise —
    the same answers, in the same order, so the day's record is the same."""
    many, n, i = getattr(ga, "funnel_many", None), _batch(), 0
    while i < len(groups):
        chunk, got = groups[i:i + n], None
        for m in range(len(chunk) if many else 1, 1, -1):
            got = many([b for _, b in chunk[:m]])
            if got is not None:
                chunk = chunk[:m]
                break
        if got is None:
            chunk = chunk[:1]
            got = [ga.funnel(chunk[0][1])]
        for (g, _), j in zip(chunk, got):
            yield g, j
        i += len(chunk)


def due(store, today, now, first=None):
    """The days to read this run, in order: the backfill days AT_RISK_DAYS or more old (oldest first), the recent ones
    (when due), the not-final ones now final, then the rest of the backfill (oldest first). The backfill = every day from
    `first` (the First open store's first day; else BACKFILL_DAYS back) to FINAL_LAG days back the store has no record
    for, and the gone days not yet confirmed (asked again REFRESH_HOURS after their last answer)."""
    days = store.get("days") or {}
    recent = []
    if gu._hours_since(store.get("recent_at"), now) >= REFRESH_HOURS:
        recent = [today - timedelta(days=i) for i in range(RECENT_DAYS)]
    fin_edge = today - timedelta(days=FINAL_LAG)
    again = sorted(gu._d(k) for k, v in days.items()            # read while not final, or stored as all zeros
                   if not v.get("none") and (not v.get("fin") or not any(v.get("t") or [])) and gu._d(k) <= fin_edge)
    back = [gu._d(k) for k, v in days.items()                   # gone once: asked again on a later run
            if is_gone(v) and int(v.get("n") or 1) < GONE_CONFIRM and gu._hours_since(v.get("at"), now) >= REFRESH_HOURS]
    d = first or (today - timedelta(days=BACKFILL_DAYS))
    while d <= fin_edge:
        if d.isoformat() not in days:
            back.append(d)
        d += timedelta(days=1)
    back.sort()
    risk = [d for d in back if (today - d).days >= AT_RISK_DAYS]
    out = risk + recent + again + back[len(risk):]
    seen, uniq = set(), []
    for d in out:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


def step_app(ga, store, steps, today, now, first=None):
    """One app's run on its store → "fetched" / "fresh". Raises Stop (the days read so far are kept): the property's
    quota floor, the run's clock, or the app's call cap — checked BEFORE a day is begun (all its calls must fit)."""
    now_iso = gu._now_iso(now)
    todo = due(store, today, now, first)
    if not todo:
        return "fresh"
    days = store.setdefault("days", {})
    cc = countries(ga, min(todo), max(todo))
    recent = {today - timedelta(days=i) for i in range(RECENT_DAYS)}
    left = {d for d in todo if d in recent}             # the recent days still to read this run
    cap = getattr(ga, "max_calls", None)
    did = False
    for d in todo:
        k = d.isoformat()
        prev = days.get(k)
        if cc.get(k):
            if cap is not None and ga.calls + calls_for(cc[k]) > cap:
                raise gf.Stop("calls")                  # the day would be cut: next run, from this day on
            rec = read_day(ga, steps, d, cc[k], today, now_iso, prev)
            if rec is not None:
                days[k] = rec
                did = True
            elif is_gone(prev):                         # an older "gone" for a day too young for that: not read yet
                del days[k]
                did = True
        elif d not in recent:                           # GA4 names no country that day (no install / "(not set)" only)
            days[k] = dict(prev, n=GONE_CONFIRM, at=now_iso) if is_gone(prev) else {"none": True, "at": now_iso}
            did = True
        if d in left:
            left.discard(d)
            if not left:
                store["recent_at"] = now_iso            # refreshed: not again for REFRESH_HOURS, even if a later day stops
    return "fetched" if did else "fresh"


# ── store and state ─────────────────────────────────────────────────────────────────────────────────────────────────
def store_path(data_dir, app_id):
    return os.path.join(data_dir, DIR, gu.file_key(app_id) + ".json.gz")


def load_store(path):
    s = gu.load_store(path)
    return s if isinstance(s, dict) and s.get("v") == STORE_V else None


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


COUNTS = ("selected", "with_store", "fetched", "fresh", "no_steps", "failed", "deferred", "days", "calls", "tokens")


def refresh_all(cfg, data_dir, apps, now=None, clock=time.monotonic, budget=BUDGET_SEC, workers=WORKERS):
    """Every selected app with a First open store → {"counts", "apps": {app id: fetched|fresh|no_steps|failed|
    deferred}}. Never raises; never prints."""
    now = now or datetime.now(timezone.utc)
    t0 = clock()
    counts = dict.fromkeys(COUNTS, 0)
    out = {"counts": counts, "apps": {}}
    lock = threading.Lock()
    try:
        state = load_state(data_dir)
        ust = gu.load_state(data_dir)
        routes = ust["routes"].get("by_package") or {}
        tokens, _ = ga4_probe.owner_tokens({"GA4_REFRESH_TOKENS": cfg.get("refresh_tokens") or "",
                                            "GA4_REFRESH_TOKEN": cfg.get("refresh_token") or ""})
        owner_rt, access = dict(tokens), {}
        now_iso = gu._now_iso(now)

        def over():
            return "budget" if clock() - t0 >= budget else None
        over.left = lambda: budget - (clock() - t0)    # (App.batch_ok: the run's seconds left)
        by_prop = {}
        for a in apps:
            if a.get("same_as") or not a.get("package"):
                continue
            counts["selected"] += 1
            aid = a["app_id"]
            main = gf.load_store(gf.store_path(data_dir, aid))
            r = routes.get(a["package"])
            if not main or not r:
                continue
            counts["with_store"] += 1
            steps = main.get("steps") or {}
            if not steps.get("splash") or not steps.get("home"):
                out["apps"][aid] = "no_steps"
                continue
            st = state["fetch"].setdefault(aid, {})
            if st.get("fail") and gu._hours_since(st.get("last_try"), now) < RETRY_HOURS:
                out["apps"][aid] = "failed"
                continue
            owner = r.get("owner")
            if owner not in access:
                try:
                    access[owner] = (ga4.access_token(cfg["client_id"], cfg["client_secret"], owner_rt[owner])
                                     if owner in owner_rt else None)
                except Exception:
                    access[owner] = None
            by_prop.setdefault(r["property_id"], []).append((a, st, r, steps, main))
        for xs in by_prop.values():                     # the app that waited longest goes first (no turn yet = first)
            xs.sort(key=lambda t: (t[1].get("turn") or "", t[0]["app_id"]))
        order = sorted(by_prop, key=lambda p: (min(t[1].get("turn") or "" for t in by_prop[p]), p))

        def one_prop(pid):
            prop = {"quota": None, "stop": None}
            for a, st, r, steps, main in by_prop[pid]:
                aid = a["app_id"]
                if over() or prop["stop"]:
                    with lock:
                        st["deferred"] = True
                        out["apps"][aid] = "deferred"
                    continue
                tok = access.get(r.get("owner"))
                if not tok:
                    with lock:
                        st.update(last_try=now_iso, fail="auth")
                        out["apps"][aid] = "failed"
                    continue
                tz = main.get("time_zone") or (ust["tz"].get(pid) or "UTC")
                today = now.astimezone(ZoneInfo(tz)).date()
                mdays = sorted(main.get("days") or {})  # the All countries table's day 1 (as the build reads it)
                first = gu._d(mdays[0]) if mdays else None
                path = store_path(data_dir, aid)
                store = load_store(path) or {"v": STORE_V}
                n0 = len(store.get("days") or {})
                ga = gf.App(tok, pid, r["stream_id"], prop, over=over, max_calls=MAX_CALLS)
                try:
                    res = step_app(ga, store, steps, today, now, first)
                    upd = dict(last_try=now_iso, fail=None)
                    if res == "fetched":
                        upd["last_ok"] = now_iso
                except gf.Stop:
                    res, upd = "deferred", {"deferred": True}
                except Exception as e:
                    res, upd = "failed", dict(last_try=now_iso, fail=gu._fail_kind(e))
                if ga.calls:
                    store.update(v=STORE_V, app_id=aid, package=a["package"], property_id=pid,
                                 stream_id=r["stream_id"], time_zone=tz)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    write_json_gz_stable(path, store)
                with lock:
                    if res != "deferred":
                        st.pop("deferred", None)
                    st.update(upd)
                    st["turn"] = now_iso                # it had its turn (a cut-off app goes last next time too)
                    st["key"] = gu.file_key(aid)
                    out["apps"][aid] = res
                    counts["calls"] += ga.calls
                    counts["tokens"] += ga.tok
                    counts["days"] += max(0, len(store.get("days") or {}) - n0)

        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            list(ex.map(one_prop, order))
        save_state(data_dir, state)
    except Exception as e:                              # a bug here must never cost the build
        out["error"] = type(e).__name__
    for v in out["apps"].values():
        if v in counts:
            counts[v] += 1
    return out


def log_line(status):
    """The build log's ONE line for this step — counts only."""
    c = (status or {}).get("counts") or {}
    return ("ga4 first open by country: apps %d, with store %d, fetched %d, fresh %d, no screens %d, failed %d, "
            "deferred %d, new days %d, calls %d, tokens %d%s"
            % tuple([gaud._int(c.get(k)) for k in COUNTS] + [(", error " + status["error"])
                                                             if (status or {}).get("error") else ""]))
