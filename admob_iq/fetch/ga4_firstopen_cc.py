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
                  "fin": final when read, "sg": the screens' signature, "at"} | {"none": true}}}
Per app and run (its screens come from the First open store; at most MAX_CALLS calls; the property's quota floors):
  * every REFRESH_HOURS the last RECENT_DAYS days again (not final: GA4 still adds to them);
  * a day read while not final is read once more when it is (≥ FINAL_LAG days old);
  * the backfill of what GA4 still has (BACKFILL_DAYS back), the oldest day first (it is the next to leave GA4), then
    the newest, in turn.
Properties run side by side (each has its own quota). Switched by GA4_FIRSTOPEN_CC (on by default in the workflow).
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
BACKFILL_DAYS = 62                  # asked once, back from today (GA4 answers what its retention kept)
REFRESH_HOURS = 6.0
MAX_CALLS = 60                      # per app per run (the backfill goes on next run)
BUDGET_SEC = 150
RETRY_HOURS = 3.0
WORKERS = 3                         # properties read side by side


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


def read_day(ga, steps, day, ccs, today, now_iso):
    """One day → its record (every group read, or Stop: a day is kept only whole)."""
    j = ga.funnel(gf.funnel_body(steps["splash"], steps["home"], day, day, "date"))
    tot, smp = _three(gf.parse_table(j)), gf.sampling(j)
    c = {}
    order = sorted(ccs, key=lambda k: (-ccs[k], k))
    for i in range(0, len(order), GROUP):
        grp = order[i:i + GROUP]
        j = ga.funnel(group_body(steps["splash"], steps["home"], day, grp))
        t, s = gf.parse_table(j), gf.sampling(j)
        if s is not None:
            smp = s if smp is None else min(smp, s)
        for cc in grp:
            v = _three(t, cc)
            if any(v):
                c[cc] = v
    return {"c": c, "t": tot, "smp": smp, "fin": (today - day).days >= FINAL_LAG, "sg": sig(steps), "at": now_iso}


def due(store, today, now):
    """The days to read this run, in order: the recent ones (when due), the not-final ones now final, then the backfill
    (oldest, newest, next oldest …)."""
    days = store.get("days") or {}
    out = []
    if gu._hours_since(store.get("recent_at"), now) >= REFRESH_HOURS:
        out += [today - timedelta(days=i) for i in range(RECENT_DAYS)]
    fin_edge = today - timedelta(days=FINAL_LAG)
    out += sorted(gu._d(k) for k, v in days.items()
                  if not v.get("none") and not v.get("fin") and gu._d(k) <= fin_edge)
    todo = [today - timedelta(days=i) for i in range(FINAL_LAG, BACKFILL_DAYS + 1)
            if (today - timedelta(days=i)).isoformat() not in days]
    todo.sort()
    while todo:
        out.append(todo.pop(0))
        if todo:
            out.append(todo.pop())
    seen, uniq = set(), []
    for d in out:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


def step_app(ga, store, steps, today, now):
    """One app's run on its store → "fetched" / "fresh". Raises Stop (the days read so far are kept)."""
    now_iso = gu._now_iso(now)
    todo = due(store, today, now)
    if not todo:
        return "fresh"
    days = store.setdefault("days", {})
    cc = countries(ga, min(todo), max(todo))
    recent = {today - timedelta(days=i) for i in range(RECENT_DAYS)}
    did = False
    for d in todo:
        k = d.isoformat()
        if not cc.get(k):
            if d not in recent:                         # GA4 has nothing for it (older than it keeps / no install)
                days[k] = {"none": True, "at": now_iso}
                did = True
            continue
        days[k] = read_day(ga, steps, d, cc[k], today, now_iso)
        did = True
    if any(d in recent for d in todo):
        store["recent_at"] = now_iso
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
        for xs in by_prop.values():
            xs.sort(key=lambda t: (not t[1].get("deferred"), t[1].get("last_ok") or "", t[0]["app_id"]))

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
                path = store_path(data_dir, aid)
                store = load_store(path) or {"v": STORE_V}
                n0 = len(store.get("days") or {})
                ga = gf.App(tok, pid, r["stream_id"], prop, over=over)
                try:
                    res = step_app(ga, store, steps, today, now)
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
                    st["key"] = gu.file_key(aid)
                    out["apps"][aid] = res
                    counts["calls"] += ga.calls
                    counts["tokens"] += ga.tok
                    counts["days"] += max(0, len(store.get("days") or {}) - n0)

        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            list(ex.map(one_prop, sorted(by_prop)))
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
