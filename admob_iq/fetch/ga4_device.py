"""📱 Devices — the hourly fetch (owner, 31 Oct 2026: the Devices tab beside 🌍 Countries in Install value → 📈 ROI, "isi
tarah banao"): per app, per install day X, GA4 by PHONE MODEL × COUNTRY — installs, paid installs, back next day and the
revenue at 7 / 30 / 90 days — every read tied to the same read without the split (a day's coverage).

The read shape (measured 31 Oct 2026, ga4_devcoh_probe, 28 apps): ONE install day at a time (filter firstSessionDate == X,
so every user of the read is exactly 0 … A−1 days old), dims mobileDeviceModel × countryId. Whole (Σ rows ÷ the read
without dims 1.000) on 26 of 28 apps; on the two biggest GA4 folds 10–50 % of a day into "(other)" whatever the split
(country alone too) — kept as measured: every split read stores its truth beside it, the build shows the coverage.

  P    [X, X]        newUsers of PAID users (firstUserGoogleAdsCampaignId a real Google Ads campaign id)
  D1   [X+1, X+1]    activeUsers (back next day) — install days of the 7-day window only
  R7   [X, X+6]      newUsers (= the install day's installs), totalAdRevenue
  R30  [X, X+29]     the same — install days of the 30-day window
  R90  [X, X+89]     the same — install days of the 90-day window
each with its truth (the same read without the split: ONE date × firstSessionDate call a kind for every install day
due — that read is whole on every app). Windows (F = the newest final day, E − LATE): each WIN install days
whose age A is complete — 7: [F−6−WIN+1, F−6], 30: [F−29−WIN+1, F−29], 90: [F−89−WIN+1, F−89]. P is read for every
install day of the three windows. A read is asked once (its days are final), newest install days first.
Names: every NAMES_DAYS the model → [brand, marketing name] of the last 90 days (one read).

Store, data/ga4_device/<key>.json.gz (private repo; install days older than KEEP_DAYS are dropped):
  {"v", "app_id", "package", "property_id", "stream_id", "time_zone", "F",
   "x": {X: {kind: {"t": truth, "m": {model: {cc: value | [installs, revenue]}}, "f": "s" | "t" | null}}},
   "names": {model: [brand, marketing name]}, "names_at"}
Switched by GA4_DEVICE. Never raises; never prints (log_line: counts only).
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from .. import ga4_probe
from ..db import write_json_gz_stable
from . import ga4
from . import ga4_audience as gaud
from . import ga4_firstopen as gf
from . import ga4_uninstall as gu

DIR = "ga4_device"
STORE_V = 1
MODEL, CC, CAMP = "mobileDeviceModel", "countryId", "firstUserGoogleAdsCampaignId"
PAID_RE = r"[^(].*"                 # a real Google Ads campaign id (not "(not set)" / "(organic)" …)
LATE = gu.IDAY_LATE                 # F = E − 3: the newest final day
WIN = 28                            # install days a window
AGES = (7, 30, 90)
KEEP_DAYS = 130                     # install days kept (the 90-day window ends F − 89, starts F − 116)
NAMES_DAYS = 7
MAX_CALLS = 60                      # per app per run (the rest next run)
BUDGET_SEC = 180
RETRY_HOURS = 3.0
PAGE_ROWS = 100000
WORKERS = 8                         # properties read side by side (each its own quota; one call at a time each)


def _r4(v):
    v = round(float(v or 0), 4)
    return int(v) if v.is_integer() else v


def windows(f):
    """{age: [first install day, last install day]} for the newest final day f."""
    return {a: (f - timedelta(days=a - 1 + WIN - 1), f - timedelta(days=a - 1)) for a in AGES}


def _fsd(x):
    return {"filter": {"fieldName": "firstSessionDate", "stringFilter": {"matchType": "EXACT", "value": x.strftime("%Y%m%d")}}}


def _paid():
    return {"filter": {"fieldName": CAMP, "stringFilter": {"matchType": "FULL_REGEXP", "value": PAID_RE}}}


def spec(kind, x):
    """kind → (date range a, b, metrics, extra filters)."""
    if kind == "P":
        return x, x, ("newUsers",), [_fsd(x), _paid()]
    if kind == "D1":
        return x + timedelta(days=1), x + timedelta(days=1), ("activeUsers",), [_fsd(x)]
    age = int(kind[1:])
    return x, x + timedelta(days=age - 1), ("newUsers", "totalAdRevenue"), [_fsd(x)]


def body(a, b, dims, mets):
    return {"dateRanges": [gu._rng(a, b)], "dimensions": ga4._dim(*dims), "metrics": ga4._dim(*mets),
            "currencyCode": "USD", "keepEmptyRows": False}


def _flag(ga):
    metas = getattr(ga, "last_metas", None) or [getattr(ga, "last_meta", None) or {}]
    if any((m or {}).get("samplingMetadatas") for m in metas):
        return "s"
    if any((m or {}).get("subjectToThresholding") for m in metas):
        return "t"
    return None


def read(ga, kind, x):
    """One kind for install day x → {"m": {model: {cc: value}}, "f": flag} (value: a number for P / D1, [installs,
    revenue] for R*); its truth ("t") comes from truths()."""
    a, b, mets, extra = spec(kind, x)
    rows = ga.report_all(body(a, b, (MODEL, CC), mets), extra=extra, page_rows=PAGE_ROWS)
    m = {}
    for r in rows:
        md, cc = str(r.get(MODEL) or "(not set)"), str(r.get(CC) or "(not set)")
        vals = [_r4(r.get(k)) for k in mets]
        cur = m.setdefault(md, {})
        if len(vals) == 1:
            cur[cc] = _r4((cur.get(cc) or 0) + vals[0])
        else:
            old = cur.get(cc) or [0, 0]
            cur[cc] = [_r4(old[0] + vals[0]), _r4(old[1] + vals[1])]
    return {"m": m, "f": _flag(ga)}


def truths(ga, kind, xs):
    """The same reads without the split, for every install day of xs in ONE call (date × firstSessionDate is whole on
    every app) → {X iso: truth} (a number for P / D1, [installs, revenue] for R*)."""
    lo, hi = min(xs), max(xs)
    days = [x.strftime("%Y%m%d") for x in xs]
    pick = {"filter": {"fieldName": "firstSessionDate", "inListFilter": {"values": days}}}
    if kind == "P":
        rows = ga.report_all(body(lo, hi, ("firstSessionDate", "date"), ("newUsers",)), extra=[pick, _paid()],
                             page_rows=PAGE_ROWS)
        out = {}
        for r in rows:
            x, d = ga4._d(r.get("firstSessionDate")), ga4._d(r.get("date"))
            if x and d == x:
                out[x.isoformat()] = _r4(out.get(x.isoformat(), 0) + float(r.get("newUsers") or 0))
        return out
    if kind == "D1":
        rows = ga.report_all(body(lo + timedelta(days=1), hi + timedelta(days=1), ("firstSessionDate", "date"),
                                  ("activeUsers",)), extra=[pick], page_rows=PAGE_ROWS)
        out = {}
        for r in rows:
            x, d = ga4._d(r.get("firstSessionDate")), ga4._d(r.get("date"))
            if x and d == x + timedelta(days=1):
                out[x.isoformat()] = _r4(out.get(x.isoformat(), 0) + float(r.get("activeUsers") or 0))
        return out
    age = int(kind[1:])
    rows = ga.report_all(body(lo, hi + timedelta(days=age - 1), ("firstSessionDate", "date"),
                              ("newUsers", "totalAdRevenue")), extra=[pick], page_rows=PAGE_ROWS)
    out = {}
    for r in rows:
        x, d = ga4._d(r.get("firstSessionDate")), ga4._d(r.get("date"))
        if not x or not d or not (x <= d <= x + timedelta(days=age - 1)):
            continue
        cur = out.setdefault(x.isoformat(), [0, 0])
        if d == x:
            cur[0] = _r4(cur[0] + float(r.get("newUsers") or 0))
        cur[1] = _r4(cur[1] + float(r.get("totalAdRevenue") or 0))
    return out


def todo(store, f):
    """The reads due for the newest final day f, newest install day first: [(kind, X)]."""
    xs = store.get("x") or {}
    w = windows(f)
    need = {}
    for age, (a, b) in w.items():
        d = b
        while d >= a:
            k = d.isoformat()
            need.setdefault(k, set()).update({"P", "R%d" % age} | ({"D1"} if age == 7 else set()))
            d -= timedelta(days=1)
    out = []
    for k in sorted(need, reverse=True):
        have = xs.get(k) or {}
        for kind in ("P", "R7", "D1", "R30", "R90"):
            if kind in need[k] and kind not in have:
                out.append((kind, gu._d(k)))
    return out


def names_read(ga, f):
    rows = ga.report_all(body(f - timedelta(days=89), f, (MODEL, "mobileDeviceBranding", "mobileDeviceMarketingName"),
                              ("newUsers",)), page_rows=PAGE_ROWS)
    best = {}
    for r in rows:
        md = str(r.get(MODEL) or "")
        if not md or md in ("(other)", "(not set)"):
            continue
        n = float(r.get("newUsers") or 0)
        if md not in best or n > best[md][0]:
            best[md] = (n, [str(r.get("mobileDeviceBranding") or ""), str(r.get("mobileDeviceMarketingName") or "")])
    return {k: v[1] for k, v in best.items()}


def step_app(ga, store, f, now):
    """One app's run on its store → "fetched" or "fresh". Raises gf.Stop (what was read so far is kept)."""
    did = False
    store["F"] = f.isoformat()
    xs = store.setdefault("x", {})
    for k in [k for k in xs if gu._d(k) < f - timedelta(days=KEEP_DAYS)]:
        del xs[k]
    if not store.get("names") or gu._hours_since(store.get("names_at"), now) >= NAMES_DAYS * 24:
        store["names"] = names_read(ga, f)
        store["names_at"] = gu._now_iso(now)
        did = True
    due = todo(store, f)
    tr = store.setdefault("tr", {})                     # truths read ahead of their split read: {kind: {X: truth}}
    for kind in ("P", "R7", "D1", "R30", "R90"):
        need = [x for k, x in due if k == kind and x.isoformat() not in (tr.get(kind) or {})]
        if need:
            tr.setdefault(kind, {}).update(truths(ga, kind, need))
            for x in need:                              # a day GA4 has nothing for: truth 0
                tr[kind].setdefault(x.isoformat(), 0 if kind in ("P", "D1") else [0, 0])
            did = True
    for kind, x in due:
        rec = read(ga, kind, x)
        rec["t"] = (tr.get(kind) or {}).pop(x.isoformat(), None)
        xs.setdefault(x.isoformat(), {})[kind] = rec
        did = True
    for kind in list(tr):                               # truths of install days no longer due
        tr[kind] = {k: v for k, v in tr[kind].items() if gu._d(k) >= f - timedelta(days=KEEP_DAYS)}
    return "fetched" if did else "fresh"


# ── store and state (as fetch.ga4_source) ───────────────────────────────────────────────────────────────────────────
def store_path(data_dir, app_id):
    return os.path.join(data_dir, DIR, gu.file_key(app_id) + ".json.gz")


def load_store(path):
    s = gu.load_store(path)
    return s if isinstance(s, dict) and s.get("v") == STORE_V else None


def load_state(data_dir):
    try:
        with open(os.path.join(data_dir, DIR, "state.json"), encoding="utf-8") as fh:
            raw = json.load(fh)
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
        with open(path, encoding="utf-8") as fh:
            if fh.read() == text:
                return False
    except OSError:
        pass
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return True


COUNTS = ("selected", "with_ga4", "fetched", "fresh", "failed", "deferred", "waiting", "calls", "tokens")


def _one_app(a, st, r, prop, token, ust, data_dir, now, now_iso, over, counts, lock):
    """One app's run → fetched | fresh | deferred | failed (its store written when anything was read)."""
    aid, pid = a["app_id"], r["property_id"]
    tz = ust["tz"].get(pid) or "UTC"
    f = ga4.window_end_in(tz, now) - timedelta(days=LATE)
    path = store_path(data_dir, aid)
    store = load_store(path) or {"v": STORE_V}
    ga = gf.App(token, pid, r["stream_id"], prop, over=over, max_calls=MAX_CALLS)
    try:
        res = step_app(ga, store, f, now)
        st.pop("deferred", None)
        st.update(last_try=now_iso, fail=None)
        if res == "fetched":
            st["last_ok"] = now_iso
    except gf.Stop:
        st["deferred"] = True
        res = "deferred"
    except Exception as e:
        st.update(last_try=now_iso, fail=gu._fail_kind(e))
        res = "failed"
    finally:
        if ga.calls:
            store.update(v=STORE_V, app_id=aid, package=a["package"], property_id=pid, stream_id=r["stream_id"],
                         time_zone=tz)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            write_json_gz_stable(path, store)
        st["key"] = gu.file_key(aid)
        with lock:
            counts["calls"] += ga.calls
            counts["tokens"] += ga.tok
    return res


def refresh_all(cfg, data_dir, apps, now=None, clock=time.monotonic, budget=BUDGET_SEC):
    """Every selected app → {"counts", "apps": {app id: fetched|fresh|failed|deferred|waiting}}; the apps that waited
    longest first. Never raises; never prints."""
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
        work = []
        for a in apps:
            if a.get("same_as") or not a.get("package"):
                continue
            counts["selected"] += 1
            r = routes.get(a["package"])
            if not r:
                continue
            counts["with_ga4"] += 1
            aid = a["app_id"]
            if not gaud._uni_meta(ust, data_dir, aid, r):
                out["apps"][aid] = "waiting"
                continue
            st = state["fetch"].setdefault(aid, {})
            if st.get("fail") and gu._hours_since(st.get("last_try"), now) < RETRY_HOURS:
                out["apps"][aid] = "failed"
                continue
            work.append((a, st, r))
        work.sort(key=lambda t: (not t[1].get("deferred"), t[1].get("last_ok") or "", t[0]["app_id"]))
        for owner in sorted({r.get("owner") for _, _, r in work}, key=str):   # the owners' tokens before the threads
            try:
                access[owner] = (ga4.access_token(cfg["client_id"], cfg["client_secret"], owner_rt[owner])
                                 if owner in owner_rt else None)
            except Exception:
                access[owner] = None
        lock = threading.Lock()
        groups = {}
        for item in work:                               # one worker a property (its quota), apps in the order above
            groups.setdefault(item[2]["property_id"], []).append(item)

        def one(group):
            for a, st, r in group:
                aid, pid = a["app_id"], r["property_id"]
                prop = props[pid]
                if over() or prop["stop"]:
                    st["deferred"] = True
                    res = "deferred"
                elif not access.get(r.get("owner")):
                    st.update(last_try=now_iso, fail="auth")
                    res = "failed"
                else:
                    res = _one_app(a, st, r, prop, access[r.get("owner")], ust, data_dir, now, now_iso, over, counts,
                                   lock)
                with lock:
                    out["apps"][aid] = res
        for pid in groups:
            props.setdefault(pid, {"quota": None, "stop": None})
        with ThreadPoolExecutor(max_workers=max(1, WORKERS)) as ex:
            list(ex.map(one, list(groups.values())))
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
    return ("ga4 device: apps %d, with GA4 %d, fetched %d, fresh %d, failed %d, deferred %d, waiting %d, calls %d, "
            "tokens %d%s" % tuple([gaud._int(c.get(k)) for k in ("selected", "with_ga4", "fetched", "fresh", "failed",
                                                                 "deferred", "waiting", "calls", "tokens")]
                                  + [(", error " + status["error"]) if (status or {}).get("error") else ""]))
