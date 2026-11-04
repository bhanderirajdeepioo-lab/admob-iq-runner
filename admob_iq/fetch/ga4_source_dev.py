"""💰 Revenue by source × phone model — the fetch behind the 📱 Devices tab's 💰 Source view (owner, 3 Nov 2026: Paid /
Notification / Organic / Other per phone; "Countries + Devices"). GA4's Traffic acquisition by SESSION primary channel group
(as fetch.ga4_source) per phone model, over WHOLE windows only: the probe (ga4_srcsplit_probe, 3 Nov 2026) found model ×
channel whole over 28 days on nearly every app, but on the biggest GA4 put a part of a 28-day read, and far more of a
one-day read, in its "(other)" row — so there is no day-by-day store here: each window is read as one, its "(other)" row
kept.

Windows (the app's GA4 days; F = today − LATE, the newest FINAL day — GA4 still moves sessions between channels for the
newest days; never before the app's history start):
  "30"  [F − 29, F]    "lm"  the last calendar month whose last day ≤ F    "60"  [F − 59, F]    "90"  [F − 89, F]
  "all"  [history start, F]   (60 days: owner, 3 Nov 2026 — his standard picker on every section; whole windows only)
ONE read shape a window: runReport mobileDeviceModel × sessionDefaultChannelGroup → sessions, totalRevenue (USD), pinned to
the app's Android stream (ga4.Ga4App), every row paged (nothing cut).

Store: data/ga4_source_dev/<key>.json.gz (private repo)
    {"v", "app_id", "package", "property_id", "stream_id", "time_zone",
     "w": {window: {"lo", "hi", "at", "rows": {model: {channel: [sessions, revenue]}}}}}
A window is read again when its days moved (once a day; "lm" once a month), at most MAX_CALLS calls an app a run.
Switched by GA4_SOURCE_DEV. Never raises; never prints (log_line: counts only).
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
from . import ga4_source as gs
from . import ga4_uninstall as gu

DIR = "ga4_source_dev"
STORE_V = 1
MODEL = "mobileDeviceModel"
METS = ("sessions", "totalRevenue")
WINDOWS = ("30", "lm", "60", "90", "all")
MONTHS_MAX = 12                     # the month mover's whole calendar months (newest first; each read once — final)
LATE = gu.IDAY_LATE                 # F = today − LATE: the newest day GA4 no longer changes
MAX_CALLS = 10                      # per app per run (5 windows + their pages)
BUDGET_SEC = 120
RETRY_HOURS = 3.0
PAGE_ROWS = 100000


def windows(today, hs):
    """The app's windows → {window: (lo, hi)} (F = today − LATE; none before the history start; empty ones left out)."""
    f = today - timedelta(days=LATE)
    lm_hi = f if (f + timedelta(days=1)).day == 1 else f.replace(day=1) - timedelta(days=1)
    out = {"30": (f - timedelta(days=29), f), "lm": (lm_hi.replace(day=1), lm_hi), "60": (f - timedelta(days=59), f),
           "90": (f - timedelta(days=89), f), "all": (hs or f, f)}
    # the month mover (owner, 4 Nov 2026): every WHOLE calendar month (its last day ≤ F: final) — "mon:YYYY-MM", newest
    # MONTHS_MAX, none wholly before the history start (the current month never: a short window folds, as Today / 7 days)
    m_hi = lm_hi
    for _ in range(MONTHS_MAX):
        if hs and m_hi < hs:
            break
        out["mon:%04d-%02d" % (m_hi.year, m_hi.month)] = (m_hi.replace(day=1), m_hi)
        m_hi = m_hi.replace(day=1) - timedelta(days=1)
    res = {}
    for k, (lo, hi) in out.items():
        lo = max(lo, hs) if hs else lo
        if lo <= hi:
            res[k] = (lo, hi)
    return res


def body(a, b):
    return {"dateRanges": [gu._rng(a, b)], "dimensions": ga4._dim(MODEL, gs.DIM), "metrics": ga4._dim(*METS),
            "currencyCode": "USD", "keepEmptyRows": False}


def read(ga, a, b):
    """[a, b] as one → {model: {channel: [sessions, revenue]}} (GA4's "(other)" / "(not set)" rows kept as named)."""
    out = {}
    for r in ga.report_all(body(a, b), page_rows=PAGE_ROWS):
        md = str(r.get(MODEL) or "") or "(not set)"
        ch = str(r.get(gs.DIM) or "") or "(not set)"
        cur = out.setdefault(md, {}).setdefault(ch, [0, 0])
        for i, m in enumerate(METS):
            cur[i] = gs._r4(cur[i] + float(r.get(m) or 0))
    return out


def step_app(ga, store, today, hs, now):
    """One app's run → "fetched" (a window read) or "fresh" (every window up to date). Raises Stop (gf.Stop); each
    window read is in the store as soon as it is back."""
    did, now_iso = False, gu._now_iso(now)
    w = store.setdefault("w", {})
    want = windows(today, hs)
    for k in list(w):
        if k not in want:
            w.pop(k)
    for k in list(WINDOWS) + sorted((x for x in want if x.startswith("mon:")), reverse=True):
        if k not in want:
            continue
        lo, hi = want[k]
        cur = w.get(k) or {}
        if cur.get("lo") == lo.isoformat() and cur.get("hi") == hi.isoformat():
            continue
        same = next((x for x in w.values() if x and x.get("lo") == lo.isoformat() and x.get("hi") == hi.isoformat()), None)
        if same:                                       # a month = Last month's read (the same days): no second call
            w[k] = dict(same)
            did = True
            continue
        rows = read(ga, lo, hi)
        w[k] = {"lo": lo.isoformat(), "hi": hi.isoformat(), "at": now_iso, "rows": rows}
        did = True
    return "fetched" if did else "fresh"


# ── store and state (as fetch.ga4_source) ───────────────────────────────────────────────────────────────────────────
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


COUNTS = gs.COUNTS


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
                if ga.calls or out["apps"].get(aid) == "fetched":   # (a month copied from Last month: no call)
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
    return ("ga4 source by phone: apps %d, with GA4 %d, fetched %d, fresh %d, failed %d, deferred %d, waiting %d, "
            "calls %d, tokens %d%s" % tuple([gaud._int(c.get(k)) for k in ("selected", "with_ga4", "fetched", "fresh",
                                                                            "failed", "deferred", "waiting", "calls",
                                                                            "tokens")]
                                            + [(", error " + status["error"]) if (status or {}).get("error") else ""]))
