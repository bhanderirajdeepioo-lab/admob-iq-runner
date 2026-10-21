"""📈 Day-wise ROI — the hourly fetch (owner, 13 Oct 2026: "every date wise uska incremental day wise revenue from first
day of the app … delta, breakeven, % wise", every feature on the FULL history).

The Install value tab's install-day file (fetch.ga4_uninstall, iday) keeps an install day's ad revenue in lag BANDS
(0, 1, 2–3, 4–7, 8–14, 15–30, …); this store keeps EVERY day of an install day's first 31 days (lag 0 … 30), so the
page can show D0, D1, D2 … D30 one by one. Beyond day 30 the page uses the iday bands (60 / 90 / 180 / 365).

GA4 runReport (v1beta, Android + the app's stream), USD:
    dimensions [date, firstSessionDate], metrics [activeUsers, totalAdRevenue]
    over a block of ACTIVITY days [a, b], firstSessionDate in-list [a − 30 … b] (GA4 refuses a numeric between)
→ cell (install day X = firstSessionDate, lag L = date − X), 0 ≤ L ≤ 30: users active on day L, ad revenue on day L.
A block holds at most BLOCK × (BLOCK + 30) rows — one page. Like the iday Q-C, the in-list hides GA4's "(other)" row
rather than avoiding it; the build ties every activity day back to the iday Q-B read (roi_build) and marks a day that
does not tie.
"(other)" (owner, 21 Oct 2026: "revenue cross check kro country wise"): a block answer with rows whose install day (or
activity day) is not a date — GA4's "(other)" — or a cut / sampled answer is dropped (counted: "blocks with (other)")
and each of its days is read alone (read_day: install days D − 30 … D, the cube's recursive split — fetch.ga4_cube
split_read — by install-day halves, no country here; at most DAY_CAP calls a day), each merged as it is read (a Stop
keeps the days read: the backfill's cursor, or the refresh's "rn", goes on from the next day — no block call first).
What is still "(other)" after the split is that day's measured loss ("lo"); a day whose answer GA4 flagged with
nothing to measure it by (dataLossFromOtherRow with no "(other)" row, thresholding, sampling) is in "lf"; a day read
again replaces both. roi_build marks a row using such a day ≈ (q bit 1, like a day that does not tie).

Per app and run (at most MAX_CALLS calls; the property's quota floors, the run's budget):
  * a one-time backfill from the GA4 history start, BLOCK activity days a call, resumable (backfill.next);
  * every REFRESH_HOURS the last RECENT_DAYS activity days again (today included: not final, the page marks it).
Stored for good in the private repo, two files so the hourly commits stay small:
    data/ga4_cohort/<key>.json.gz      the hot part: install days from the month of (today − HOT_DAYS) on
    data/ga4_cohort/<key>.old.json.gz  the older install days (rewritten only when the split moves a month, or by the
                                       backfill)
    {"v", "app_id", "package", "property_id", "stream_id", "time_zone", "hs", "read_today", "recent_at",
     "backfill": {"from", "next", "done"}, "cut", "x": {X: {"r": [31 USD micros], "u": [31 users]}},
     "lo": {D: micros still "(other)"}, "lf": {D: 1 flagged}, "rn": the next day of a refresh read day by day}
     ("lo", "lf", "rn" only when there is something in them)
Switched by GA4_COHORT (on by default in the workflow). Never raises; never prints (log_line: counts only).
"""
import json
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import ga4_probe
from ..db import write_json_gz_stable
from . import ga4
from . import ga4_audience as gaud
from . import ga4_cube as gcu
from . import ga4_uninstall as gu
from .ga4_firstopen import App, Stop

DIR = "ga4_cohort"
STORE_V = 1
LAGS = 31                           # lag 0 … 30
BLOCK = 30                          # activity days a call (in-list ≤ 60 install days, ≤ 1,800 rows)
RECENT_DAYS = 35                    # refreshed every REFRESH_HOURS (today … 34 days back)
REFRESH_HOURS = 6.0
FINAL_LAG = 3                       # an activity day is final once ≤ the property's today − 3 (as the iday reads)
HOT_DAYS = 45                       # the hot file: install days from the month of (today − 45) on
MAX_CALLS = 60                      # per app per run (the backfill goes on next run)
DAY_CAP = 16                        # GA4 calls a day read alone may take (the split by install-day halves)
BUDGET_SEC = 150
RETRY_HOURS = 3.0
METS = ("activeUsers", "totalAdRevenue")


def _d(s):
    return date.fromisoformat(s)


def _ymd(d):
    return d.strftime("%Y%m%d")


def _iso8(s):
    s = str(s or "")
    return "%s-%s-%s" % (s[:4], s[4:6], s[6:]) if len(s) == 8 and s.isdigit() else None


def body(a, b):
    """The block [a, b]: every install day a − 30 … b at every activity day of the block."""
    return {"dateRanges": [{"startDate": a.isoformat(), "endDate": b.isoformat()}],
            "dimensions": ga4._dim("date", "firstSessionDate"), "metrics": ga4._dim(*METS),
            "currencyCode": "USD", "keepEmptyRows": False}


def in_list(a, b):
    n = (b - a).days + LAGS
    return [_ymd(b - timedelta(days=i)) for i in range(n)]


def _cells(rows):
    """Rows → ({X: {L: [users, micros]}} for every row with 0 ≤ L ≤ 30, rows whose install / activity day is not a
    date — GA4's "(other)" — and their micros)."""
    out, oth, om = {}, 0, 0
    for r in rows:
        D, X = _iso8(r.get("date")), _iso8(r.get("firstSessionDate"))
        v = int(round(float(r.get("totalAdRevenue") or 0) * 1e6))
        if not D or not X:
            oth += 1
            om += v
            continue
        L = (_d(D) - _d(X)).days
        if 0 <= L < LAGS:
            out.setdefault(X, {})[L] = [int(r.get("activeUsers") or 0), v]
    return out, oth, om


def read_block(ga, a, b, info=None):
    """One block → {X: {L: [users, micros]}} for every row with 0 ≤ L ≤ 30 (and the X's GA4 answered). info: "oth"
    rows GA4 left "(other)" (or with an activity day that is not a date), "om" their micros, "fl" GA4's flags."""
    rows = ga.report_all(body(a, b), extra=[ga4._in_list("firstSessionDate", in_list(a, b))],
                         page_rows=gu.UNI_PAGE_ROWS)
    out, oth, om = _cells(rows)
    if info is not None:
        info.update(oth=oth, om=om, fl=gcu._flags(ga, rows))
    return out


def read_day(ga, D, info=None):
    """Activity day D alone, install days D − 30 … D, through the cube's split (install-day halves) → its cells; info:
    "loss" (micros still "(other)"), "fl" (1: GA4 flagged a part with nothing to measure it by), "calls". Raises Stop
    (nothing of the day kept)."""
    xs = [(D - timedelta(days=i)).isoformat() for i in range(LAGS)]
    rows, si = gcu.split_read(ga, D, DAY_CAP, xs=xs, dims=("date", "firstSessionDate"),
                              root_why=gcu.F_SMP | gcu.F_CUT)
    out, _, om = _cells(rows)
    if info is not None:
        info.update(loss=om, fl=1 if si["flag"] else 0, calls=si["calls"])
    return out


def _note(store, D, lo, fl):
    """Day D's measured "(other)" loss and GA4's flag (a day read again: replaced; nothing: the key goes)."""
    k = D.isoformat()
    for key, v in (("lo", lo), ("lf", 1 if fl else 0)):
        m = store.get(key)
        if v:
            if not isinstance(m, dict):
                m = store[key] = {}
            m[k] = v
        elif isinstance(m, dict):
            m.pop(k, None)
            if not m:
                store.pop(key)


def _days(a, b):
    while a <= b:
        yield a
        a += timedelta(days=1)


def _read(ga, store, a, b, info, alone=False):
    """Activity days a … b into the store → yields the last day merged (a generator: a Stop keeps every day merged).
    One block call; an answer with "(other)" rows, cut or sampled → each day alone (alone: straight away)."""
    if not alone:
        bi = {}
        got = read_block(ga, a, b, bi)
        if not (bi["oth"] or bi["fl"] & (gcu.F_CUT | gcu.F_SMP)):
            merge(store, got, a, b)
            fl = bool(bi["fl"] & (gcu.F_OTHER | gcu.F_THR))        # a flag on the block: every day of it
            for D in _days(a, b):
                _note(store, D, 0, fl)
            info["flagged"] += fl * ((b - a).days + 1)
            yield b
            return
        info["oth_blocks"] += 1
        del got
    for D in _days(a, b):
        di = {}
        g = read_day(ga, D, di)
        merge(store, g, D, D)
        _note(store, D, di["loss"], di["fl"])
        info["alone"] += 1
        info["loss_days"] += bool(di["loss"])
        info["flagged"] += di["fl"]
        yield D


def merge(store, got, a, b):
    """Cells of activity days a … b: set from the read; a cell the read did not return is 0 (nobody / no revenue)."""
    x = store.setdefault("x", {})
    X = a - timedelta(days=LAGS - 1)
    while X <= b:
        k = X.isoformat()
        g = got.get(k) or {}
        e = x.get(k)
        for L in range(LAGS):
            D = X + timedelta(days=L)
            if D < a or D > b:
                continue
            v = g.get(L)
            if e is None and not v:
                continue
            if e is None:
                e = x[k] = {"r": [0] * LAGS, "u": [0] * LAGS}
            e["u"][L], e["r"][L] = (v or [0, 0])
        X += timedelta(days=1)


def _blocks(start, end, n=BLOCK):
    out, a = [], start
    while a <= end:
        b = min(end, a + timedelta(days=n - 1))
        out.append((a, b))
        a = b + timedelta(days=1)
    return out


INFO = ("oth_blocks", "alone", "loss_days", "flagged")


def step_app(ga, store, today, hs, now, info=None):
    """One app's run on its store → "fetched" or "fresh". Raises Stop (what was read is kept). info: the counts of
    INFO (added to)."""
    did, now_iso = False, gu._now_iso(now)
    info = info if info is not None else {}
    for k in INFO:
        info.setdefault(k, 0)
    recent = today - timedelta(days=RECENT_DAYS - 1)
    bf = store.setdefault("backfill", {})
    if not bf.get("done"):
        nxt = _d(bf["next"]) if bf.get("next") else hs
        bf.setdefault("from", nxt.isoformat())
        for a, b in _blocks(nxt, recent - timedelta(days=1)):
            for D in _read(ga, store, a, b, info):
                bf["next"] = (D + timedelta(days=1)).isoformat()
                did = True
        bf["done"] = True
    if gu._hours_since(store.get("recent_at"), now) >= REFRESH_HOURS:
        a, alone = max(hs, recent), False
        try:
            rn = _d(store["rn"]) if store.get("rn") else None
        except ValueError:
            rn = None
        if rn and a <= rn <= today:                         # a refresh read day by day that a Stop cut: on from there
            a, alone = rn, True
        for D in _read(ga, store, a, today, info, alone):
            store["rn"] = (D + timedelta(days=1)).isoformat()
            did = True
        store.pop("rn", None)
        store["recent_at"], store["read_today"] = now_iso, today.isoformat()
        did = True
    return "fetched" if did else "fresh"


# ── store and state ─────────────────────────────────────────────────────────────────────────────────────────────────
def store_path(data_dir, app_id, old=False):
    return os.path.join(data_dir, DIR, gu.file_key(app_id) + (".old.json.gz" if old else ".json.gz"))


def load_store(data_dir, app_id):
    """The hot part with the older install days put back (a part of another format / stream: the whole store again)."""
    s = gu.load_store(store_path(data_dir, app_id))
    if not isinstance(s, dict) or s.get("v") != STORE_V:
        return None
    o = gu.load_store(store_path(data_dir, app_id, old=True))
    if isinstance(o, dict) and o.get("v") == STORE_V and o.get("stream_id") == s.get("stream_id"):
        s["x"] = dict(o.get("x") or {}, **(s.get("x") or {}))
    s.pop("cut", None)
    return s


def save_store(data_dir, app_id, store, today):
    """Hot part (install days from the month of today − HOT_DAYS) and the older part; the older file is written only
    when its content changed (write_json_gz_stable keeps an unchanged file as it is)."""
    cut = (today - timedelta(days=HOT_DAYS)).replace(day=1).isoformat()
    x = store.get("x") or {}
    hot = {k: v for k, v in x.items() if k >= cut}
    old = {k: v for k, v in x.items() if k < cut}
    os.makedirs(os.path.join(data_dir, DIR), exist_ok=True)
    head = {k: v for k, v in store.items() if k != "x"}
    write_json_gz_stable(store_path(data_dir, app_id), dict(head, x=hot, cut=cut))
    if old:
        write_json_gz_stable(store_path(data_dir, app_id, old=True),
                             {"v": STORE_V, "stream_id": store.get("stream_id"), "x": old})


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


COUNTS = ("selected", "with_ga4", "fetched", "fresh", "failed", "deferred", "waiting") + INFO + ("calls", "tokens")


def refresh_all(cfg, data_dir, apps, now=None, clock=None, budget=BUDGET_SEC):
    """Every selected app (uninstall_build's list) → {"counts", "apps": {app id: fetched|fresh|failed|deferred|
    waiting}}. Never raises; never prints."""
    import time
    clock = clock or time.monotonic
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
            store = load_store(data_dir, aid)
            if store is None or store.get("stream_id") != r["stream_id"]:
                store = {"v": STORE_V}
            ga = App(access[owner], pid, r["stream_id"], prop, over=over, max_calls=MAX_CALLS)
            info = dict.fromkeys(INFO, 0)
            try:
                res = step_app(ga, store, today, hs, now, info)
                st.pop("deferred", None)
                st.update(last_try=now_iso, fail=None)
                if res == "fetched":
                    st["last_ok"] = now_iso
                out["apps"][aid] = res
            except Stop:
                st["deferred"] = True
                out["apps"][aid] = "deferred"
            except Exception as e:
                st.update(last_try=now_iso, fail=gu._fail_kind(e))
                out["apps"][aid] = "failed"
            finally:
                if ga.calls:
                    store.update(v=STORE_V, app_id=aid, package=a["package"], property_id=pid,
                                 stream_id=r["stream_id"], time_zone=tz, hs=hs.isoformat())
                    save_store(data_dir, aid, store, today)
                st["key"] = gu.file_key(aid)
                counts["calls"] += ga.calls
                counts["tokens"] += ga.tok
                for k in INFO:
                    counts[k] += info[k]
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
    return ("ga4 cohort: apps %d, with GA4 %d, fetched %d, fresh %d, failed %d, deferred %d, waiting %d, blocks with "
            "(other) %d, days read alone %d, days with loss %d, flagged days %d, calls %d, tokens %d%s"
            % tuple([gaud._int(c.get(k)) for k in COUNTS]
                                  + [(", error " + status["error"]) if (status or {}).get("error") else ""]))
