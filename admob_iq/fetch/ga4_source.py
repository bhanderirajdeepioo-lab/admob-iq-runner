"""💰 Revenue by source — the hourly fetch (owner, 31 Oct 2026: "yahi he jo mene ss bheja vo hi he notification ka revenue
vahi karo"): GA4's Traffic acquisition report by SESSION primary channel group, per app per day — exactly the numbers
his GA4 screen shows (Cross-network, Mobile Push Notifications, Direct, Organic Search, …), every channel GA4 names
(nothing cut, "(other)" kept as GA4 names it).

ONE read shape: runReport [a, b] date × sessionDefaultChannelGroup → sessions, activeUsers, totalAdRevenue, totalRevenue
(USD), pinned to the app's Android stream (ga4.Ga4App), every row paged (nothing cut). GA4's standard reports keep these
aggregates for the property's whole life (measured 31 Oct 2026, ga4_notif_probe: monthly totals back to the first data
month on 28/28 apps, the channel rows summing to the no-channel total within 0.5 %).

Store, kept for good: data/ga4_source/<key>.json.gz (private repo)
    {"v", "app_id", "package", "property_id", "stream_id", "time_zone", "recent_at",
     "days": {YYYY-MM-DD: {channel: [sessions, activeUsers, totalAdRevenue, totalRevenue]}}   ({} = GA4 has nothing),
     "mark": {YYYY-MM-DD: "s" (read from a GA4 sample) | "t" (subject to thresholding)},
     "backfill": {"oldest": the oldest day read, "done": reached the app's history start}}
Per app and run (at most MAX_CALLS calls; the property's quota floors as the Audience fetch's; the run's budget):
  * every REFRESH_HOURS the last RECENT_DAYS days (today included: GA4 still adds to them) — replaced whole;
  * the backfill: CHUNK_DAYS at a time, newest first, from the day before the recent window back to the app's history
    start (the Uninstall store's), so the newest history comes first. Days older than RECENT_DAYS are final in GA4.
Switched by GA4_SOURCE. Never raises; never prints (log_line: counts only).
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import ga4_probe
from ..db import write_json_gz_stable
from . import ga4
from . import ga4_audience as gaud
from . import ga4_firstopen as gf
from . import ga4_uninstall as gu

DIR = "ga4_source"
STORE_V = 1
DIM = "sessionDefaultChannelGroup"
METS = ("sessions", "activeUsers", "totalAdRevenue", "totalRevenue")
RECENT_DAYS = 5                     # today … 4 days back: refreshed every REFRESH_HOURS (older days are final in GA4)
REFRESH_HOURS = 1.0
CHUNK_DAYS = 180                    # one backfill call: ≤ 180 days × ~10 channels of rows
MAX_CALLS = 12                      # per app per run (the backfill goes on next run)
BUDGET_SEC = 120
RETRY_HOURS = 3.0
PAGE_ROWS = 100000
WORKERS = 6                         # properties read side by side (each its own quota; one call at a time each)


def _r4(v):
    v = round(float(v or 0), 4)
    return int(v) if v.is_integer() else v


def body(a, b):
    return {"dateRanges": [gu._rng(a, b)], "dimensions": ga4._dim("date", DIM), "metrics": ga4._dim(*METS),
            "currencyCode": "USD", "keepEmptyRows": False}


def read(ga, a, b):
    """[a, b] → ({YYYY-MM-DD: {channel: [sessions, activeUsers, ad revenue, total revenue]}} with {} for every day GA4
    named nothing, {day: "s" | "t"} when any page was sampled / thresholded)."""
    rows = ga.report_all(body(a, b), page_rows=PAGE_ROWS)
    days, n = {}, (b - a).days + 1
    for i in range(n):
        days[(a + timedelta(days=i)).isoformat()] = {}
    for r in rows:
        d = ga4._d(r.get("date"))
        if d is None or not (a <= d <= b):
            continue
        ch = str(r.get(DIM) or "(not set)")
        cur = days[d.isoformat()].setdefault(ch, [0, 0, 0, 0])
        for i, m in enumerate(METS):
            cur[i] = _r4(cur[i] + float(r.get(m) or 0))
    mark = None
    metas = getattr(ga, "last_metas", None) or [getattr(ga, "last_meta", None) or {}]
    if any((m or {}).get("samplingMetadatas") for m in metas):
        mark = "s"
    elif any((m or {}).get("subjectToThresholding") for m in metas):
        mark = "t"
    return days, ({d: mark for d in days} if mark else {})


def step_app(ga, store, today, hs, now):
    """One app's run on its store → "fetched" (something read) or "fresh" (nothing due). Raises Stop (gf.Stop)."""
    did, now_iso = False, gu._now_iso(now)
    days = store.setdefault("days", {})
    mark = store.setdefault("mark", {})
    recent = today - timedelta(days=RECENT_DAYS - 1)
    first = min(hs, recent) if hs else recent
    if gu._hours_since(store.get("recent_at"), now) >= REFRESH_HOURS:
        got, mk = read(ga, max(first, recent), today)
        for d, rec in got.items():
            days[d] = rec                               # the newest read of a still-changing day wins
            mark.pop(d, None)
        mark.update(mk)
        store["recent_at"] = now_iso
        did = True
    bf = store.setdefault("backfill", {})
    while not bf.get("done"):
        top = (gu._d(bf["oldest"]) - timedelta(days=1)) if bf.get("oldest") else recent - timedelta(days=1)
        if top < first:
            bf["done"] = True
            break
        a = max(first, top - timedelta(days=CHUNK_DAYS - 1))
        got, mk = read(ga, a, top)
        for d, rec in got.items():
            days[d] = rec
            mark.pop(d, None)
        mark.update(mk)
        bf["oldest"] = a.isoformat()
        did = True
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


COUNTS = ("selected", "with_ga4", "fetched", "fresh", "failed", "deferred", "waiting", "calls", "tokens")


def refresh_all(cfg, data_dir, apps, now=None, clock=time.monotonic, budget=BUDGET_SEC):
    """Every selected app (uninstall_build's list) → {"counts", "apps": {app id: fetched|fresh|failed|deferred|waiting}}.
    Properties one after another in the order their apps waited longest; never raises; never prints."""
    now = now or datetime.now(timezone.utc)
    t0 = clock()
    counts = dict.fromkeys(COUNTS, 0)
    out = {"counts": counts, "apps": {}}
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
            path = store_path(data_dir, aid)
            store = load_store(path) or {"v": STORE_V}
            ga = gf.App(access[owner], pid, r["stream_id"], prop, over=over, max_calls=MAX_CALLS)
            try:
                res = step_app(ga, store, today, hs, now)
                st.pop("deferred", None)
                st.update(last_try=now_iso, fail=None)
                if res == "fetched":
                    st["last_ok"] = now_iso
                out["apps"][aid] = res
            except gf.Stop:
                st["deferred"] = True
                out["apps"][aid] = "deferred"
            except Exception as e:
                st.update(last_try=now_iso, fail=gu._fail_kind(e))
                out["apps"][aid] = "failed"
            finally:
                if ga.calls:
                    store.update(v=STORE_V, app_id=aid, package=a["package"], property_id=pid, stream_id=r["stream_id"],
                                 time_zone=tz)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    write_json_gz_stable(path, store)
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
    """The build log's ONE line for this step — counts only."""
    c = (status or {}).get("counts") or {}
    return ("ga4 source: apps %d, with GA4 %d, fetched %d, fresh %d, failed %d, deferred %d, waiting %d, calls %d, "
            "tokens %d%s" % tuple([gaud._int(c.get(k)) for k in ("selected", "with_ga4", "fetched", "fresh", "failed",
                                                                 "deferred", "waiting", "calls", "tokens")]
                                  + [(", error " + status["error"]) if (status or {}).get("error") else ""]))
