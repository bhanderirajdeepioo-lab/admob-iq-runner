"""📈 eCPM first session vs returning × COUNTRY — the fetch behind the eCPM tab's ad unit / ad format tables for a picked
country (owner, 3 Nov 2026: "US kiya to ad unit table me US ka hi aana chaiye … sab mene jo bola vo sab chaihiye": every
country, every period). GA4's newVsReturning × ad format × ad unit × country with the ad revenue and impressions, per app
per day. Measured first (ga4_nvrcc_probe, 3 Nov 2026): whole on most apps; on the biggest GA4 folds a large part into its
"(other)" row before any read (a country filter does not help) — kept as GA4 names it, and the page says, per country
and period, how much GA4 gave against the country's own whole total (fetch.ga4_nvr's country read).

ONE read shape: runReport [a, b] date × newVsReturning × adFormat × adUnitName × countryId → totalAdRevenue, eventCount
(eventName == ad_impression: the impressions as events), pinned to the app's Android stream (ga4.Ga4App), every row
paged (nothing cut). Measured 3 Nov 2026 (ga4_nvrcc_probe) on the biggest apps: with eventCount the split comes whole
(no "(other)" row; revenue and impressions tie the country read over 1, 7 and 14 days), where publisherAdImpressions
folded a large part or lost most impressions. GA4 spreads a country a little differently here than in its country read
(the page shows how much, country by country).

Store, kept for good, one file a month (a month GA4 no longer changes is written once and then left alone):
    data/ga4_nvr_uc/<key>.json.gz          {"v", "app_id", "package", "property_id", "stream_id", "time_zone",
                                            "recent_at", "upto", "folded", "backfill": {"oldest", "done"}, "months": […]}
    data/ga4_nvr_uc/<key>/<YYYY-MM>.json.gz {"v", "days": {YYYY-MM-DD: [[nvr, ad format, ad unit, country, revenue,
                                            impressions], …]}}   (nvr: "n" new · "r" returning · "x" not set; country: the
                                            ISO code, "--" for anything else — as fetch.ga4_nvr; [] = nothing that day)
Per app and run (at most MAX_CALLS calls; the property's quota floors as the Audience fetch's; the run's budget):
  * every REFRESH_HOURS the last RECENT_DAYS days (today included: GA4 still adds to them) — replaced whole; days a
    longer outage left between the last such read ("upto") and them are read first, oldest first (never a hole);
  * the backfill: CHUNK_DAYS at a time, newest first, from the day before the recent window back to the app's history
    start (the Uninstall store's). Days older than RECENT_DAYS are final in GA4.
GA4's folded "(other)" row comes with no real day and no country: it is left out (counted in "folded": reads that had
one) — the page measures, per country and period, what GA4 gave against the country's own whole total. NOT read again
day by day: measured 3 Nov 2026 (ga4_nvrcc_probe), GA4's one-day reads of this split carry no "(other)" row but only a
part of the impressions and a country spread unlike its own country read — worse, and quieter.
Switched by GA4_NVR_UC. Never raises; never prints (log_line: counts only).
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
from . import ga4_nvr as gv
from . import ga4_source as gs
from . import ga4_uninstall as gu

DIR = "ga4_nvr_uc"
STORE_V = 3                         # 3: impressions = ad_impression events (3 Nov 2026) — older stores are read again
DIMS = ("date", gv.NVR, "adFormat", "adUnitName", "countryId")
METS = gv.EV
RECENT_DAYS = 5                     # today … 4 days back: refreshed every REFRESH_HOURS (older days are final in GA4)
REFRESH_HOURS = 6.0
CHUNK_DAYS = 14                     # one backfill call: ≤ 14 days × ad units × countries × 3 of rows
MAX_CALLS = 20                      # per app per run (the backfill goes on next run)
BUDGET_SEC = 150
RETRY_HOURS = 3.0
PAGE_ROWS = 100000


def body(a, b):
    return {"dateRanges": [gu._rng(a, b)], "dimensions": ga4._dim(*DIMS), "metrics": ga4._dim(*METS),
            "currencyCode": "USD", "keepEmptyRows": False}


def read(ga, a, b):
    """[a, b] → ({YYYY-MM-DD: [[nvr, format, ad unit, country, revenue, impressions], …]} with [] for every day GA4 named
    nothing, folded): folded = a row with no real day (GA4's "(other)") in a read of more than one day — left out; the
    caller reads the range again day by day. In a one-day read such a row is that day's."""
    rows = ga.report_all(body(a, b), event=gv.EVENT, page_rows=PAGE_ROWS)
    days, n, folded = {}, (b - a).days + 1, False
    for i in range(n):
        days[(a + timedelta(days=i)).isoformat()] = []
    for r in rows:
        d = ga4._d(r.get("date"))
        if d is None:
            if a != b:
                folded = True
                continue
            d = a
        if not (a <= d <= b):
            continue
        cc = str(r.get("countryId") or "")
        days[d.isoformat()].append([gv._nvr(r.get(gv.NVR)), str(r.get("adFormat") or ""), str(r.get("adUnitName") or ""),
                                    cc if len(cc) == 2 and cc.isalpha() else "--", gv._r4(r.get(METS[0])),
                                    int(float(r.get(METS[1]) or 0))])
    for v in days.values():
        v.sort()
    return days, folded


def read_whole(ga, meta, a, b):
    """[a, b] as one read; GA4's folded row (no real day) left out and counted (meta "folded")."""
    got, folded = read(ga, a, b)
    if folded:
        meta["folded"] = int(meta.get("folded") or 0) + 1
    return got


# ── the store: its meta file and one file a month ─────────────────────────────────────────────────────────────────
def store_path(data_dir, app_id):
    return os.path.join(data_dir, DIR, gu.file_key(app_id) + ".json.gz")


def month_path(data_dir, app_id, month):
    return os.path.join(data_dir, DIR, gu.file_key(app_id), month + ".json.gz")


def load_store(path):
    s = gu.load_store(path)
    return s if isinstance(s, dict) and s.get("v") == STORE_V else None


def load_month(data_dir, app_id, month):
    """One month's days ({} when the file is missing or of another version)."""
    s = gu.load_store(month_path(data_dir, app_id, month))
    return (s.get("days") or {}) if isinstance(s, dict) and s.get("v") == STORE_V else {}


def load_days(data_dir, app_id, months=None):
    """Every stored day of an app → {YYYY-MM-DD: [[nvr, format, ad unit, country, revenue, impressions], …]} (months: its
    meta's list)."""
    if months is None:
        meta = load_store(store_path(data_dir, app_id)) or {}
        months = meta.get("months") or []
    out = {}
    for m in months:
        out.update(load_month(data_dir, app_id, m))
    return out


def save_days(data_dir, app_id, got, meta):
    """Merge the days read into their month files (each touched month written once, only when it changed)."""
    by = {}
    for d, rec in got.items():
        by.setdefault(d[:7], {})[d] = rec
    for m, days in by.items():
        cur = load_month(data_dir, app_id, m)
        cur.update(days)                                # the newest read of a still-changing day wins
        path = month_path(data_dir, app_id, m)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_json_gz_stable(path, {"v": STORE_V, "days": cur})
    meta["months"] = sorted(set(meta.get("months") or []) | set(by))


def step_app(ga, meta, data_dir, app_id, today, hs, now):
    """One app's run → "fetched" (something read) or "fresh" (nothing due). Raises Stop (gf.Stop); every read is in the
    month files as soon as it is back (one chunk in memory at a time)."""
    did, now_iso = False, gu._now_iso(now)
    one = timedelta(days=1)
    recent = today - timedelta(days=RECENT_DAYS - 1)
    first = min(hs, recent) if hs else recent
    if gu._hours_since(meta.get("recent_at"), now) >= REFRESH_HOURS:
        up = gu._d(meta["upto"]) if meta.get("upto") else None
        a = max(first, up + one) if up else recent
        while up and a < recent:                        # a longer outage: the days since the last recent read first
            b = min(recent - one, a + timedelta(days=CHUNK_DAYS - 1))
            save_days(data_dir, app_id, read_whole(ga, meta, a, b), meta)
            meta["upto"] = b.isoformat()
            a = b + one
        save_days(data_dir, app_id, read_whole(ga, meta, max(first, recent), today), meta)
        meta.update(recent_at=now_iso, upto=today.isoformat())
        did = True
    bf = meta.setdefault("backfill", {})
    while not bf.get("done"):
        top = (gu._d(bf["oldest"]) - timedelta(days=1)) if bf.get("oldest") else recent - timedelta(days=1)
        if top < first:
            bf["done"] = True
            break
        a = max(first, top - timedelta(days=CHUNK_DAYS - 1))
        save_days(data_dir, app_id, read_whole(ga, meta, a, top), meta)
        bf["oldest"] = a.isoformat()
        did = True
    return "fetched" if did else "fresh"


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
            meta = load_store(path) or {"v": STORE_V}
            ga = gf.App(access[owner], pid, r["stream_id"], prop, over=over, max_calls=MAX_CALLS)
            try:
                res = step_app(ga, meta, data_dir, aid, today, hs, now)
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
                    meta.update(v=STORE_V, app_id=aid, package=a["package"], property_id=pid, stream_id=r["stream_id"],
                                time_zone=tz)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    write_json_gz_stable(path, meta)
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
    return ("ga4 nvr by country: apps %d, with GA4 %d, fetched %d, fresh %d, failed %d, deferred %d, waiting %d, "
            "calls %d, tokens %d%s" % tuple([gaud._int(c.get(k)) for k in ("selected", "with_ga4", "fetched", "fresh",
                                                                            "failed", "deferred", "waiting", "calls",
                                                                            "tokens")]
                                            + [(", error " + status["error"]) if (status or {}).get("error") else ""]))
