"""📈 eCPM — the FIRST SESSION against the returning ones, the hourly fetch (owner, 2 Nov 2026: "user ke first session ka
ecpm and second session ka ecpm dono ka difference chahiye taki pata chale ki first session me new user me ecpm dikkat he ya
old user me"; "ecpm first and returning session ke liye ad unit wise mil sakta he?" — yes): GA4's newVsReturning ("new" =
the user's first session, "returning" = session 2 on) with the ad revenue and impressions, per app per day, by ad unit and by
country. Measured (ga4_nvr_probe, 2 Nov 2026, 28 days): accepted on all 28 apps, every split tied to the read without it
(revenue 1.00; the biggest app's ad-unit split 0.95 of the impressions).

THREE reads a range [a, b] (READS; PARTS = the ones made, in this order), pinned to the app's Android stream
(ga4.Ga4App), every row paged (USD):
  u   date × newVsReturning × adFormat × adUnitName → totalAdRevenue, eventCount   (eventName == ad_impression)
  c   date × newVsReturning × countryId             → totalAdRevenue, eventCount   (eventName == ad_impression)
  s   date × newVsReturning                         → sessions, activeUsers
The impressions are the ad_impression EVENTS (eventCount): measured 3 Nov 2026 (ga4_nvrcc_probe), equal to
publisherAdImpressions on the country read, but whole on the ad unit reads where publisherAdImpressions is not (the
biggest app's ad unit read lost a part of its impressions — and its eCPMs read high).
GA4's standard reports keep these aggregates for the property's whole life.

Store, kept for good: data/ga4_nvr/<key>.json.gz (private repo)
    {"v", "app_id", "package", "property_id", "stream_id", "time_zone", "recent_at",
     "days": {YYYY-MM-DD: {"u": [[nvr, format, ad unit, revenue, impressions], …], "c": [[nvr, cc, revenue, impressions], …],
                           "s": [[nvr, sessions, users], …]}}     (nvr: "n" new · "r" returning · "x" not set; [] = nothing)
     "mark": {YYYY-MM-DD: "s" (a read of the day came from a GA4 sample) | "t" (subject to thresholding)},
     "rr": {YYYY-MM-DD: 1} (a final day read once more alone for its sampled mark),
     "rq": {YYYY-MM-DD: [times, last read]} (a final day REREAD named, read again alone — at most RQ_MAX times),
     "mp": {YYYY-MM-DD: {"u" | "c" | "s": "s" | "t"}} (EACH read's own flag; {} = all three whole; "mark" = "s" when any
           read was sampled, else "t" when any was thresholded — the Breakeven card's day 1 reads only "c"'s own),
     "backfill": {"oldest": the oldest day read, "done": reached the app's history start}}
Per app and run (at most MAX_CALLS calls; the property's quota floors as the Audience fetch's; the run's budget):
  * every REFRESH_HOURS the last RECENT_DAYS days (today … FINAL_LAG days back: GA4 still adds to them; the day turning
    FINAL_LAG old gets its final read here) — replaced whole;
  * a day that left that window still marked "s" (GA4 sampled the still-changing range — a busy app's raw events) is read
    once more ALONE when final, newest first (whole from GA4's daily tables), "rr": {day: 1} keeping it from being asked
    twice (one that stays sampled keeps its mark); a day marked before the store kept each read's own flag ("mp") is
    read alone once more too, to learn them;
  * the backfill: CHUNK_DAYS at a time, newest first, from the day before the recent window back to the app's history
    start (the Uninstall store's). Days older than RECENT_DAYS are final in GA4 (their last read was FINAL_LAG days on).
Switched by GA4_NVR. Never raises; never prints (log_line: counts only). A second instance of this module
(fetch.ga4_paid.instance: its own globals — APP, NAME, DIR, PARTS and its knobs) runs this same code on a store of its
own: fetch.ga4_nvr_paid, the "c" read of Google Ads users only.
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import ga4_final
from .. import ga4_probe
from ..db import write_json_gz_stable
from . import ga4
from . import ga4_audience as gaud
from . import ga4_firstopen as gf
from . import ga4_uninstall as gu

DIR = "ga4_nvr"
APP = None                          # the GA4 client's class (None: ga4_firstopen.App) — a second instance of this
#                                     module (fetch.ga4_paid.instance) sets its own: fetch.ga4_nvr_paid's holds every
#                                     read to Google Ads users
NAME = "ga4 nvr"                    # the log line's label (a second instance's own)
STORE_V = 2                         # 2: impressions = ad_impression events (3 Nov 2026) — a v1 store is read again
NVR = "newVsReturning"
AD = ("totalAdRevenue", "publisherAdImpressions")
EVENT = "ad_impression"
EV = ("totalAdRevenue", "eventCount")                # the ad reads: impressions = ad_impression events (EVENT)
READS = {"u": ((NVR, "adFormat", "adUnitName"), EV, EVENT),     # a part → its read: the dimensions after date, the
         "c": ((NVR, "countryId"), EV, EVENT),                  # metrics, the eventName filter (None: every event)
         "s": ((NVR,), ("sessions", "activeUsers"), None)}
PARTS = ("u", "c", "s")             # the reads made, in this order — a day's record holds exactly these parts (a second
#                                     instance's own: fetch.ga4_nvr_paid reads "c" only)
FINAL_LAG = ga4_final.lag(4)        # a day's last read is made this many days after it (on day D + FINAL_LAG): final
#                                     from then on — GA4_FINAL_DAYS, at least 4 (this store's lag before the knob)
RECENT_DAYS = max(5, FINAL_LAG + 1) # today … FINAL_LAG days back: refreshed every REFRESH_HOURS (older days are final)
REFRESH_HOURS = 1.0
CHUNK_DAYS = 90                     # one backfill read (3 calls): ≤ 90 days × 2 × ~230 countries of rows
MAX_CALLS = 15                      # per app per run (the backfill goes on next run)
BUDGET_SEC = 150
RETRY_HOURS = 3.0
PAGE_ROWS = 100000
WORKERS = 6                         # properties read side by side (each its own quota; one call at a time each)
REREAD = None                       # a list of FINAL days to read again, ALONE (data_dir-relative JSON {"days": {app key:
#                                     [day, …]}}; None: none) — fetch.ga4_nvr_paid's: be_build's input guard (the days
#                                     whose Google Ads users' first-session read disagreed with their cohort read)
RQ_MAX = 3                          # … each such day read again at most 3 times ("rq": {day: [times, last read]}) …
RQ_GAP_H = 24.0                     # … at least a day apart …
RQ_CAP = 2                          # … and at most 2 such days an app a run (newest first)


def body(a, b, dims, mets):
    return {"dateRanges": [gu._rng(a, b)], "dimensions": ga4._dim("date", *dims), "metrics": ga4._dim(*mets),
            "currencyCode": "USD", "keepEmptyRows": False}


def _nvr(v):
    return {"new": "n", "returning": "r"}.get(str(v or ""), "x")


def _r4(v):
    v = round(float(v or 0), 4)
    return int(v) if v.is_integer() else v


def _mark(ga):
    metas = getattr(ga, "last_metas", None) or [getattr(ga, "last_meta", None) or {}]
    if any((m or {}).get("samplingMetadatas") for m in metas):
        return "s"
    if any((m or {}).get("subjectToThresholding") for m in metas):
        return "t"
    return None


RANK = {None: 2, "t": 1, "s": 0}   # a read's flag, better first: whole > thresholded > sampled


def _remark(mark, d, flags):
    """A day's all-in-one "mark" from its reads' own flags ({part: "s" | "t"}): "s" when any was sampled, else "t"."""
    fl = set(flags.values())
    m = "s" if "s" in fl else ("t" if "t" in fl else None)
    if m:
        mark[d] = m
    else:
        mark.pop(d, None)


def read(ga, a, b):
    """[a, b] → ({YYYY-MM-DD: {"u": [...], "c": [...], "s": [...]}} for every day of the range — the parts of PARTS,
    read in that order —, {day: "s" | "t"} when a page of any read was sampled / thresholded, {day: {part: "s" | "t"}}
    — EACH read's own flag ({} = all of them whole): one sampled read never stands for the others (owner, 16 Nov 2026:
    "sample data de esa ho hi nhi sakta … proper check kro" — the busiest app's country read came whole while its
    ad-unit read of the same day was sampled))."""
    days = {(a + timedelta(days=i)).isoformat(): {p: [] for p in PARTS} for i in range((b - a).days + 1)}
    part_mk = {}
    for part in PARTS:
        dims, mets, ev = READS[part]
        rows = ga.report_all(body(a, b, dims, mets), event=ev, page_rows=PAGE_ROWS)
        for r in rows:
            d = ga4._d(r.get("date"))
            if d is None or not (a <= d <= b):
                continue
            k = _nvr(r.get(NVR))
            if part == "u":
                rec = [k, str(r.get("adFormat") or ""), str(r.get("adUnitName") or ""), _r4(r.get("totalAdRevenue")),
                       int(float(r.get("eventCount") or 0))]
            elif part == "c":
                cc = str(r.get("countryId") or "")
                rec = [k, cc if len(cc) == 2 and cc.isalpha() else "--", _r4(r.get("totalAdRevenue")),
                       int(float(r.get("eventCount") or 0))]
            else:
                rec = [k, int(float(r.get("sessions") or 0)), int(float(r.get("activeUsers") or 0))]
            days[d.isoformat()][part].append(rec)
        m = _mark(ga)
        if m:
            part_mk[part] = m
    fl = set(part_mk.values())
    mark = "s" if "s" in fl else ("t" if "t" in fl else None)     # (a sample outranks a threshold: never hidden by it)
    for v in days.values():
        for part in v:
            v[part].sort()
    return days, ({d: mark for d in days} if mark else {}), {d: dict(part_mk) for d in days}


def step_app(ga, store, today, hs, now, ask=()):
    """One app's run on its store → "fetched" (something read) or "fresh" (nothing due). Raises Stop (gf.Stop). ask: the
    days REREAD names for the app (a final day the store has is read again alone, bounded: RQ_MAX / RQ_GAP_H / RQ_CAP;
    a day not named is never read again for it)."""
    did, now_iso = False, gu._now_iso(now)
    days = store.setdefault("days", {})
    mark = store.setdefault("mark", {})
    recent = today - timedelta(days=RECENT_DAYS - 1)
    first = min(hs, recent) if hs else recent
    mp = store.setdefault("mp", {})                     # each read's own flag of a day ({} = whole)
    if gu._hours_since(store.get("recent_at"), now) >= REFRESH_HOURS:
        got, mk, pm = read(ga, max(first, recent), today)
        lone = store.get("rr")
        for d, rec in got.items():
            days[d] = rec                               # the newest read of a still-changing day wins
            mark.pop(d, None)
            mp[d] = pm[d]
            if isinstance(lone, dict):                  # a day read alone before — under a shorter window
                lone.pop(d, None)                       # (GA4_FINAL_DAYS raised): read alone again once it leaves
        mark.update(mk)
        store["recent_at"] = now_iso
        did = True
    # a FINAL day still marked sampled — read while GA4 was still filling it: a busy app's newest days come back sampled
    # (GA4 answers a still-changing range from its raw events), a final day whole — is read once more, ALONE, newest
    # first (the Breakeven card's day 1 = this store's first session: owner, 16 Nov 2026, "isme bhi milna hi chahiye").
    # "rr" keeps the days read so, so one that stays sampled is never asked again — whichever of its reads was (the
    # ad-unit and sessions rows feed the eCPM tab and the CPI screen; the country rows the Breakeven card). A day whose
    # reads' own flags are not known yet ("mp": marked by the older all-in-one rule) is read alone once more too. A day
    # the window reads again leaves "rr" (above): its lone read comes again when it leaves the window.
    rr = store.setdefault("rr", {})
    edge = recent - timedelta(days=1)
    for d in sorted((d for d, v in mark.items() if v == "s" and first <= gu._d(d) <= edge
                     and (d not in rr or d not in mp)), reverse=True):
        got, mk, pm = read(ga, gu._d(d), gu._d(d))
        days[d] = got[d]
        mark.pop(d, None)
        mark.update(mk)
        mp[d] = pm[d]
        rr[d] = 1
        did = True
    # a final day a reader of the store found broken (REREAD: the Breakeven build's input guard — the day's first-session
    # read disagreed with the cohort read of the same users) is read again alone: newest first, at most RQ_CAP days a run,
    # each at most RQ_MAX times and RQ_GAP_H hours apart ("rq": {day: [times, last read]}) — GA4 may give the whole day
    # on a later read; past RQ_MAX the day stays as read (the reader falls back and says so)
    if ask:
        rq, k = store.setdefault("rq", {}), 0
        for d in sorted({str(x) for x in ask}, reverse=True):
            if k >= RQ_CAP:
                break
            try:
                dd = gu._d(d)
            except ValueError:
                continue
            if d not in days or not first <= dd <= edge:
                continue                                # (a day the window still reads every hour, or one not held)
            t = rq.get(d)
            t = t if isinstance(t, list) and len(t) == 2 and isinstance(t[0], int) else [0, None]
            if t[0] >= RQ_MAX or gu._hours_since(t[1], now) < RQ_GAP_H:
                continue
            got, mk, pm = read(ga, dd, dd)
            days[d] = got[d]
            mark.pop(d, None)
            mark.update(mk)
            mp[d] = pm[d]
            rr[d] = 1
            rq[d] = [t[0] + 1, now_iso]
            k += 1
            did = True
    bf = store.setdefault("backfill", {})
    while not bf.get("done"):
        top = (gu._d(bf["oldest"]) - timedelta(days=1)) if bf.get("oldest") else recent - timedelta(days=1)
        if top < first:
            bf["done"] = True
            break
        a = max(first, top - timedelta(days=CHUNK_DAYS - 1))
        got, mk, pm = read(ga, a, top)
        for d, rec in got.items():
            cur = days.get(d)
            if d in rr and isinstance(cur, dict) and all(p in cur for p in PARTS):
                own = mp.get(d)                         # read alone already (final; "rr" never asks it again): each
                if isinstance(own, dict):               # of its reads stays, unless the chunk's is better (whole >
                    own = dict(own)                     # thresholded > sampled)
                    for p in PARTS:
                        if RANK[pm[d].get(p)] > RANK[own.get(p)]:
                            cur[p] = rec[p]
                            if pm[d].get(p):
                                own[p] = pm[d][p]
                            else:
                                own.pop(p, None)
                    mp[d] = own
                    _remark(mark, d, own)
                continue                                # (no rows kept for it: the chunk's read, whole, below)
            days[d] = rec
            mp[d] = pm[d]
            _remark(mark, d, pm[d])
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


def _asks(data_dir):
    """REREAD's days per app key ({} when off, missing or unreadable — never a failure of the run)."""
    if not REREAD:
        return {}
    try:
        with open(os.path.join(data_dir, REREAD), encoding="utf-8") as f:
            v = (json.load(f) or {}).get("days")
        return {str(k): [str(d) for d in x] for k, x in v.items() if isinstance(x, list)} if isinstance(v, dict) else {}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}


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
        asks = _asks(data_dir)

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
            ga = (APP or gf.App)(access[owner], pid, r["stream_id"], prop, over=over, max_calls=MAX_CALLS)
            try:
                res = step_app(ga, store, today, hs, now, asks.get(gu.file_key(aid)) or ())
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
    return (NAME + ": apps %d, with GA4 %d, fetched %d, fresh %d, failed %d, deferred %d, waiting %d, calls %d, "
            "tokens %d%s" % tuple([gaud._int(c.get(k)) for k in ("selected", "with_ga4", "fetched", "fresh", "failed",
                                                                 "deferred", "waiting", "calls", "tokens")]
                                  + [(", error " + status["error"]) if (status or {}).get("error") else ""]))
