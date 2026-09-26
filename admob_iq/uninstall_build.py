"""GA4 Uninstall tab — the build step (build_static.build calls run_uninstall in live mode).

run_uninstall, in this order:
  1. fetch what is due from GA4 for every SELECTED app (fetch.ga4_uninstall.refresh_all — at most once per
     ~20h per app, so most hourly runs make no GA4 call at all; a failure there never stops the build),
  2. evaluate each app's stored data (engine.uninstall), one app at a time, and save the private state
     (open alert episodes, checkpoint stage, fetch bookkeeping) in data/ga4_uninstall/state.json,
  3. write the lazy site assets — uninstall.json.gz (every app's detail) and uninstall_c_<key>.json.gz
     (each app's raw install-day × lag cells) — deterministic, rewritten only when they change,
  4. only then put the small summary (alerts, badge counts, one row per app) into dashboard["uninstall"].

The notifications go through build_static.send_alerts like every other alert; mark_notified then records
which uninstall alerts went out (their channel answered OK), so each one is sent ONCE and a failed send is
tried again next run (a dry run counts as sent: switching NOTIFY_DRY_RUN off never dumps a backlog).

PRIVACY: the Actions log of this public repo is world-readable, so this prints exactly ONE line — counts
only. App names, packages, ids, owner emails and GA4 error texts stay in the private state / site files.
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

from . import ga4_probe
from .db import write_json_gz_stable
from .engine import uninstall as eng
from .fetch import ga4_uninstall as gu

ASSET = "uninstall.json.gz"
COHORT_PREFIX = "uninstall_c_"
COHORT_V = 2                  # bump when the cohort file format changes (forces a rewrite) — 2: near-complete days
                              # filled (engine fill_days), like every other number of the tab
NO_GA4_TEXT = {
    "no_package": "Play Store package nahi mila — AdMob me app ka store link jodo",
    "no_stream": "Kisi bhi GA4 account me is app ka Android stream nahi mila",
    "stream_list_failed": "GA4 ki stream list poori nahi padh paye — agle run me phir try hoga",
    "not_fetched_yet": "GA4 data abhi aana baaki hai — agle robot run me aayega",
    "fetch_failed": "GA4 se data lene me dikkat aayi — thodi der baad phir try hoga",
    "same_package": "Ye aur '%s' ek hi Play Store app hain — iska GA4 data '%s' me dikhta hai",
}


def ga4_cfg(s):
    """The GA4 settings the uninstall step needs, or None when GA4 is switched off or not configured."""
    if not s.get("ga4_enabled"):
        return None
    tokens = (s.get("ga4_refresh_tokens") or "").strip() or (s.get("ga4_refresh_token") or "").strip()
    if not (s.get("ga4_client_id") and s.get("ga4_client_secret") and tokens):
        return None
    return {"client_id": s["ga4_client_id"], "client_secret": s["ga4_client_secret"],
            "refresh_tokens": s.get("ga4_refresh_tokens") or "", "refresh_token": s.get("ga4_refresh_token") or "",
            "min_hours": s.get("ga4_min_hours", 20.0), "retry_hours": s.get("ga4_retry_hours", 3.0),
            "refetch_days": s.get("ga4_refetch_days", 14), "rebuild_days": s.get("ga4_rebuild_days", 28),
            "late_days": s.get("ga4_late_days", eng.LATE_DAYS),
            "max_history_days": s.get("ga4_max_history_days", 1300),
            "run_budget_sec": s.get("ga4_run_budget_sec", 900),
            "streams_ttl_hours": s.get("ga4_streams_ttl_hours", 168.0)}


def _selected_apps(dashboard, data_dir):
    """Every SELECTED app → {app_id, app_name (the dashboard's display name), package|None, same_as|None}.
    Two selected apps with ONE Play package are one GA4 stream: only the app catalog_from picks for that
    package keeps it (fetched and alerted once); the other gets package None + same_as = that app's name
    (listed under "GA4 data nahi", never fetched — no double quota, no duplicate alerts)."""
    try:
        with open(os.path.join(data_dir, "app_store_ids.json"), encoding="utf-8") as f:
            by_id = (json.load(f) or {}).get("by_id") or {}
    except Exception:
        by_id = {}
    by_pkg, pkg_of, selected = ga4_probe.catalog_from(by_id, dashboard)
    out = []
    for aid, name in sorted(selected.items()):
        pkg = pkg_of.get(aid)
        first = by_pkg.get(pkg) if pkg else None
        if first and first["app_id"] != aid:
            out.append({"app_id": aid, "app_name": str(name or aid), "package": None,
                        "same_as": str(first.get("app_name") or first["app_id"])})
        else:
            out.append({"app_id": aid, "app_name": str(name or aid), "package": pkg})
    return out


def _sig(path):
    with open(path, "rb") as f:
        return "%s:%d:%s" % (hashlib.sha1(f.read()).hexdigest()[:16], COHORT_V, eng.IMPUTE_MIN_COVERAGE)


def _reason(a, status, state):
    if a.get("same_as"):
        return "same_package"
    if not a.get("package"):
        return "no_package"
    r = ((status or {}).get("no_ga4") or {}).get(a["app_id"])
    if r:
        return r
    return "fetch_failed" if (state["fetch"].get(a["app_id"]) or {}).get("fail") else "not_fetched_yet"


def _status(details, counts, no_ga4, status, state):
    discovered = bool(state["routes"].get("fetched_at"))
    if not details and (status is None or status.get("discovery") == "failed" or not discovered):
        return "error"
    if details and all(d["stale"] for d in details):
        return "stale"
    if (counts["failed"] or counts["deferred"] or counts["stale"]
            or any(n["reason"] in ("not_fetched_yet", "fetch_failed") for n in no_ga4)):
        return "partial"
    return "ok"


def run_uninstall(dashboard, data_dir, out_dir, s, now=None, clock=None):
    """→ the site file names written for the tab (for _headers), or None when GA4 is off. Sets
    dashboard["uninstall"] last, after every file is on disk."""
    cfg = ga4_cfg(s)
    if cfg is None:
        return None
    now = now or datetime.now(timezone.utc)
    now_iso = gu._now_iso(now)
    apps = _selected_apps(dashboard, data_dir)
    try:
        status = gu.refresh_all(cfg, data_dir, apps, now, clock or time.monotonic)
    except Exception:
        status = None                                   # carry on from what is stored
    state = gu.load_state(data_dir)
    os.makedirs(out_dir, exist_ok=True)
    details, rows, no_ga4, files = [], [], [], [ASSET]
    late_sums = {"un": {}, "new": {}, "fetches": 0}          # every app's late-data re-reads, pooled
    for a in sorted(apps, key=lambda x: (x["app_name"].casefold(), x["app_id"])):
        aid, path = a["app_id"], gu.store_path(data_dir, a["app_id"])
        store = gu.load_store(path) if os.path.exists(path) and not a.get("same_as") else None
        if not store or not store.get("history_start") or not store.get("window_end"):
            r = _reason(a, status, state)
            no_ga4.append({"app_id": aid, "app": a["app_name"], "package": a.get("package"), "reason": r,
                           "text": NO_GA4_TEXT[r] % ((a["same_as"],) * 2 if r == "same_package" else ())})
            continue
        key = gu.file_key(aid)
        st = state["fetch"].setdefault(aid, {})
        st["meta"] = gu.store_meta(store)               # planning always follows the store actually on disk
        stale = gu._hours_since(store.get("fetched_at"), now) > eng.STALE_HOURS
        store = eng.fill_days(store)                    # near-complete days filled (≈) — the detail and the cohort
                                                        # file read the same cells; the store on disk stays raw
        # an unchecked store format (v1: its clean re-pull still pending — quota, a failure) is shown and flagged,
        # but whatever it opens is seeded, never sent: no alert from unchecked data ever goes out. A v2 store
        # waiting for its repair is checked data: evaluated as ever (its incomplete days still left out)
        detail, row = eng.evaluate_app(store, aid, a["app_name"], state, now_iso, stale=stale, key=key,
                                       package=a.get("package") or store.get("package"), late=cfg["late_days"],
                                       outdated=gu._store_v(store) < gu.CHECKED_V)
        eng.revision_sums(store, late_sums)
        name = COHORT_PREFIX + key + ".json.gz"
        sig = _sig(path)
        if st.get("c_sig") != sig or not os.path.exists(os.path.join(out_dir, name)):
            write_json_gz_stable(os.path.join(out_dir, name), eng.cohort_file(store))
            st["c_sig"] = sig
        files.append(name)
        details.append(detail)
        rows.append(row)
        store = None                                    # one big store in memory at a time
    gu.save_state(data_dir, state)

    alerts = eng.sort_alerts([al for d in details for al in d["alerts"]])
    sel = {a["app_id"] for a in apps}
    sc = (status or {}).get("counts") or {}
    counts = {"selected": len(apps),
              "with_ga4": len(details) + sum(1 for n in no_ga4 if n["reason"] in ("not_fetched_yet", "fetch_failed")),
              "ready": sum(1 for r in rows if r["ready"]), "no_ga4": len(no_ga4),
              "failed": sum(1 for aid in sel if (state["fetch"].get(aid) or {}).get("fail")),
              "deferred": sc.get("deferred", 0), "stale": sum(1 for d in details if d["stale"])}
    asset = {"v": 1,
             "consts": {"lag_days": eng.LAG_DAYS, "band_days": eng.BAND_DAYS, "band_k": eng.BAND_K,
                        "recent_k": eng.RECENT_K, "prev_k": eng.PREV_K, "head_k": eng.HEAD_K, "z": eng.Z_MIN,
                        "min_pp": eng.MIN_PP, "min_rel": eng.MIN_REL, "min_recent_users": eng.MIN_RECENT_USERS,
                        "big_recent_users": eng.BIG_RECENT_USERS, "zoom_days": eng.ZOOM_DAYS,
                        "late_days": cfg["late_days"], "thin_min_days": eng.THIN_MIN_DAYS,
                        "thin_min_users": eng.THIN_MIN_USERS, "surv_recent_days": eng.SURV_RECENT_DAYS,
                        "verdict_k": eng.VERDICT_K, "tri_avg_weeks": eng.TRI_AVG_WEEKS,
                        "alert_recent_days": eng.ALERT_RECENT_DAYS, "year_clear_days": eng.YEAR_CLEAR_DAYS,
                        "impute_min_coverage": eng.IMPUTE_MIN_COVERAGE, "est_mark_pp": eng.EST_MARK_PP},
             "lateness": eng.lateness(late_sums), "apps": details, "no_ga4": no_ga4}
    write_json_gz_stable(os.path.join(out_dir, ASSET), asset)
    asset_v = hashlib.sha1(json.dumps(asset, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                           .encode("utf-8")).hexdigest()[:12]
    keep = set(files)
    for f in os.listdir(out_dir):                       # an app no longer shown takes its cohort file with it
        if f.startswith(COHORT_PREFIX) and f.endswith(".json.gz") and f not in keep:
            try:
                os.remove(os.path.join(out_dir, f))
            except OSError:
                pass
    till = sorted(d["data_till"] for d in details)
    ac = {"warning": 0, "watch": 0, "good": 0}
    for al in alerts:
        ac[al["severity"]] = ac.get(al["severity"], 0) + 1
    dashboard["uninstall"] = {"v": 1, "status": _status(details, counts, no_ga4, status, state), "asset": ASSET,
                              "asset_v": asset_v, "data_till_min": till[0] if till else None,
                              "data_till_max": till[-1] if till else None, "counts": counts, "apps": rows,
                              "alerts": alerts, "alert_counts": ac}
    print("ga4 uninstall: apps %d, with GA4 %d, fetched %d (full %d, repair %d), fresh %d, failed %d, deferred %d, "
          "open alerts %d (new %d)" % (counts["selected"], counts["with_ga4"], sc.get("fetched", 0),
                                       sc.get("full", 0), sc.get("repair", 0), sc.get("fresh", 0), counts["failed"],
                                       counts["deferred"], len(alerts), sum(1 for al in alerts if al["notify"])),
          file=sys.stderr)
    return files


def mark_notified(data_dir, summary, dry, now=None, ids=None):
    """After send_alerts: the uninstall alerts that were due and went out (`ids` = build_static.
    uninstall_delivered; None = all of them) are now sent — or, in a dry run, counted as sent — and never
    sent again for the same episode. One whose send failed stays due for the next run."""
    due = {a["id"] for a in (summary or {}).get("alerts") or [] if a.get("notify")}
    ids = due if ids is None else due & set(ids)
    if not ids:
        return 0
    now_iso = gu._now_iso(now or datetime.now(timezone.utc))
    state = gu.load_state(data_dir)
    n = 0
    for ep in state["episodes"].values():
        if ep.get("id") in ids and ep.get("notified_at") is None:
            ep["notified_at"], ep["notified_dry"] = now_iso, bool(dry)
            n += 1
    gu.save_state(data_dir, state)
    return n
