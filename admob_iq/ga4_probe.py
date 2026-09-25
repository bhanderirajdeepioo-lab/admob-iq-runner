"""Phase 0 GA4 probe — what uninstall/retention data can GA4 actually give for OUR apps?

    python -m admob_iq.ga4_probe

One-off, read-only. Uses GA4_REFRESH_TOKEN (analytics.readonly) with the OAuth client that minted it:
GA4_CLIENT_ID / GA4_CLIENT_SECRET (saved by `authorize --ga4 --save-secret`), falling back to
GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET when those are not set. It:
  1. discover every GA4 property + Android stream the token can see (Admin API),
  2. match streams to our AdMob apps by Play package (PRIVATE_DIR/data/app_store_ids.json, with
     roas.by_app[].store_id from PRIVATE_DIR/site/dashboard.json.gz as a fallback),
  3. run the capability tests (admob_iq.fetch.ga4.probe_*) on every matched SELECTED app,
  4. write the full report to GA4_PROBE_OUT (default PRIVATE_DIR/ga4/probe.json).

PRIVACY: this runs in a PUBLIC repo whose Actions logs anyone can read. stdout carries ONLY aggregate
counts ("matched selected apps 22", "T1 ok 20/22"). Names, packages, ids, versions, countries,
revenue, user counts and API error texts go into the JSON file only — never to the log.

Exit 0 even when individual tests fail (that IS the finding); exit 1 only when auth or discovery
fails outright.
"""

import gzip
import json
import os
import sys
from datetime import datetime, timezone

from .fetch import ga4

# (report key, probe function) — each is run per app, wrapped so one failure never stops the rest
TESTS = [
    ("base", ga4.probe_base), ("T1", ga4.probe_t1), ("T1b", ga4.probe_t1b), ("T2", ga4.probe_t2),
    ("T3", ga4.probe_t3), ("T4", ga4.probe_t4), ("T5", ga4.probe_t5), ("T7_crash", ga4.probe_t7_crash),
    ("T7_screens", ga4.probe_t7_screens), ("T11", ga4.probe_t11), ("events", ga4.probe_events),
    ("T12", ga4.probe_t12),
]
# display order in the summary (T9 + T13 are derived: property metadata / T2+T3, no extra report call)
ORDER = ["base", "T1", "T1b", "T2", "T3", "T4", "T5", "T7_crash", "T7_screens", "T9", "T11", "events",
         "T12", "T13"]


def _safe(fn, *args):
    """Run one probe; an exception becomes {"ok": False, "error": ...} in the report, never a crash."""
    try:
        return fn(*args)
    except Exception as e:
        return {"ok": False, "error": ("%s: %s" % (type(e).__name__, e))[:800]}


def _private_dir(env):
    return env.get("PRIVATE_DIR") or "_private"


def out_path(env=None):
    env = os.environ if env is None else env
    return env.get("GA4_PROBE_OUT") or os.path.join(_private_dir(env), "ga4", "probe.json")


def _load_dashboard(private_dir):
    for name, opener in (("dashboard.json.gz", gzip.open), ("dashboard.json", open)):
        p = os.path.join(private_dir, "site", name)
        if os.path.exists(p):
            try:
                with opener(p, "rt", encoding="utf-8") as f:
                    return json.load(f) or {}
            except Exception:
                pass
    return {}


def load_catalog(private_dir):
    """→ (package → {app_id, app_name, account_id, selected}, app_id → package, selected app_ids).
    If two AdMob apps share a package, the SELECTED one wins."""
    try:
        with open(os.path.join(private_dir, "data", "app_store_ids.json"), encoding="utf-8") as f:
            by_id = (json.load(f) or {}).get("by_id") or {}
    except Exception:
        by_id = {}
    dash = _load_dashboard(private_dir)
    catalog = [c for c in (dash.get("apps_catalog") or []) if c.get("app_id")]
    pkg_of = {aid: str(p).strip() for aid, p in by_id.items() if p and str(p).strip()}
    # fallback: ROAS knows a store_id per app NAME (from Google Ads) — map it back to app_ids
    ids_by_name = {}
    for c in catalog:
        ids_by_name.setdefault(c.get("app_name"), []).append(c["app_id"])
    for name, e in ((dash.get("roas") or {}).get("by_app") or {}).items():
        sid = str((e or {}).get("store_id") or "").strip()
        for aid in ids_by_name.get(name, []) if sid else []:
            pkg_of.setdefault(aid, sid)
    by_pkg = {}
    for c in catalog:
        pkg = pkg_of.get(c["app_id"])
        if not pkg:
            continue
        e = {"app_id": c["app_id"], "app_name": c.get("app_name"), "account_id": c.get("account_id"),
             "selected": bool(c.get("selected"))}
        if pkg not in by_pkg or (e["selected"] and not by_pkg[pkg]["selected"]):
            by_pkg[pkg] = e
    selected = {c["app_id"] for c in catalog if c.get("selected")}
    return by_pkg, pkg_of, selected


def match_streams(streams, by_pkg):
    """→ (matched [(stream, app)] for SELECTED apps, counts). One stream per package (first wins)."""
    matched, seen = [], set()
    n = {"unmatched_streams": 0, "matched_not_selected": 0, "duplicate_package_streams": 0}
    for s in streams:
        app = by_pkg.get(s.get("package"))
        if not app:
            n["unmatched_streams"] += 1
        elif s["package"] in seen:
            n["duplicate_package_streams"] += 1
        else:
            seen.add(s["package"])
            if app["selected"]:
                matched.append((s, app))
            else:
                n["matched_not_selected"] += 1
    return matched, n


def probe_app(token, stream, app, meta_cache, now=None):
    """Every test for one app. Never raises."""
    pid = stream["property_id"]
    if pid not in meta_cache:
        meta_cache[pid] = _safe(ga4.property_meta, token, pid)
    meta = meta_cache[pid]
    end = ga4.window_end_in(meta.get("time_zone"), now)
    ga = ga4.Ga4App(token, pid, stream["stream_id"])
    tests = {key: _safe(fn, ga, end) for key, fn in TESTS}
    tests["T9"] = {"ok": False, "error": meta["error"]} if "error" in meta else ga4.probe_t9(meta)
    tests["T13"] = _safe(ga4.probe_t13, tests["T2"], tests["T3"], end)
    return {"app_name": app.get("app_name"), "account_id": app.get("account_id"),
            "package": stream.get("package"), "property_id": pid, "stream_id": stream["stream_id"],
            "window_end": end.isoformat(), "report_calls": ga.calls, "quota": ga.quota,
            "realtime_quota": ga.realtime_quota, "tests": tests}


def capability(apps):
    """How many probed apps pass / error on each test."""
    out = {}
    for key in ORDER:
        res = [a["tests"].get(key) or {} for a in apps.values()]
        out[key] = {"ok": sum(1 for r in res if r.get("ok")), "errors": sum(1 for r in res if r.get("error")),
                    "of": len(res)}
    return out


def run(env=None, now=None):
    """→ (report dict, exit code). All detail lives in the report; nothing is printed here."""
    env = os.environ if env is None else env
    report = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "version": 1,
              "apps": {}, "discovery": {}, "quota": {}, "capability": {}}
    # a refresh token only works with the OAuth client that minted it → prefer the GA4 client
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    rt = env.get("GA4_REFRESH_TOKEN")
    report["client"] = "GA4_CLIENT_ID" if env.get("GA4_CLIENT_ID") else "GOOGLE_CLIENT_ID"
    if not (cid and sec and rt):
        report.update(fatal_stage="credentials", fatal="GA4_CLIENT_ID (or GOOGLE_CLIENT_ID) / its secret / "
                                                        "GA4_REFRESH_TOKEN not all set")
        return report, 1
    try:
        token = ga4.access_token(cid, sec, rt)
    except Exception as e:
        report.update(fatal_stage="auth", fatal=str(e)[:800])
        return report, 1
    paging = {}
    try:
        props = ga4.list_properties(token, paging)
    except Exception as e:
        report.update(fatal_stage="discovery", fatal=str(e)[:800])
        return report, 1

    streams, stream_errors = [], {}
    for p in props:
        try:
            streams.extend(ga4.android_streams(token, p["property_id"], paging))
        except Exception as e:
            stream_errors[p["property_id"]] = str(e)[:400]
        ga4._sleep(ga4.PAUSE)
    if props and len(stream_errors) == len(props):
        report.update(fatal_stage="discovery", fatal="every dataStreams call failed",
                      discovery={"properties": len(props), "stream_errors": stream_errors})
        return report, 1

    by_pkg, pkg_of, selected = load_catalog(_private_dir(env))
    matched, counts = match_streams(streams, by_pkg)
    stream_pkgs = {s.get("package") for s in streams}
    counts["selected_apps"] = len(selected)
    counts["selected_without_package"] = sum(1 for a in selected if a not in pkg_of)
    counts["selected_without_stream"] = sum(1 for a in selected if a in pkg_of and pkg_of[a] not in stream_pkgs)
    report["discovery"] = {"properties": len(props), "android_streams": len(streams),
                           "matched_selected_apps": len(matched), "stream_errors": stream_errors,
                           "catalog_packages": len(by_pkg), "paging_truncated": bool(paging.get("truncated")),
                           **counts}

    meta_cache = {}
    for s, app in matched:
        report["apps"][app["app_id"]] = probe_app(token, s, app, meta_cache, now)
    report["property_meta"] = meta_cache
    by_prop = {a["property_id"]: a["quota"] for a in report["apps"].values() if a.get("quota")}
    latest = [a["quota"] for a in report["apps"].values() if a.get("quota")]
    report["quota"] = {"latest": latest[-1] if latest else None, "by_property": by_prop}
    report["capability"] = capability(report["apps"])
    return report, 0


def summary_lines(report):
    """Aggregate-only lines for the PUBLIC log: counts and pass rates, nothing identifying."""
    if report.get("fatal_stage"):
        return ["ga4 probe: FAILED at stage '%s' (details in the private report)" % report["fatal_stage"]]
    d = report.get("discovery") or {}
    lines = ["ga4 probe: properties %d, android streams %d, matched selected apps %d"
             % (d.get("properties", 0), d.get("android_streams", 0), d.get("matched_selected_apps", 0)),
             "unmatched streams %d, matched but not selected %d, duplicate-package streams %d, "
             "selected apps without stream %d, selected apps without package %d, stream-list errors %d"
             % (d.get("unmatched_streams", 0), d.get("matched_not_selected", 0),
                d.get("duplicate_package_streams", 0), d.get("selected_without_stream", 0),
                d.get("selected_without_package", 0), len(d.get("stream_errors") or {}))]
    cap = report.get("capability") or {}
    lines.append(" | ".join("%s ok %d/%d" % (k, cap[k]["ok"], cap[k]["of"]) for k in ORDER if k in cap))
    errs = ["%s %d" % (k, cap[k]["errors"]) for k in ORDER if cap.get(k, {}).get("errors")]
    lines.append("tests with API errors: " + (", ".join(errs) if errs else "none"))
    lines.append("report calls %d" % sum(a.get("report_calls") or 0 for a in (report.get("apps") or {}).values()))
    return lines


def write_report(report, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        text = json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True, default=str)
    except TypeError:                          # mixed-type dict keys can't be sorted — keep the data anyway
        text = json.dumps(report, ensure_ascii=False, indent=1, default=str)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    try:
        report, code = run()
    except Exception as e:                     # a raw traceback could carry ids → keep it in the file only
        report, code = {"fatal_stage": "unexpected", "fatal": ("%s: %s" % (type(e).__name__, e))[:800]}, 1
    try:
        write_report(report, out_path())
    except Exception:
        print("ga4 probe: could not write the report file")
        return 1
    for line in summary_lines(report):
        print(line)
    print("ga4 probe: report written")
    return code


if __name__ == "__main__":
    sys.exit(main())
