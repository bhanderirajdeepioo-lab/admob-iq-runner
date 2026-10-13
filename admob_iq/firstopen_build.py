"""🆕 First open tab — the build step: of the users opening an app for the first time, how many reach the Splash and,
after it in order, the Home (and Language / Permission / Intro) — Today / Yesterday, the last 7 days vs the usual, and the
FULL history kept by fetch.ga4_firstopen (owner, 13 Oct 2026: every feature on the whole history, at a glance what is a
problem, good or normal).

ONE lazy file, site/firstopen.json.gz:
  {"v", "apps": [{key, app, app_id, steps {step: screen class}, steps_changed, first_day, final_till,
                  days: [[YYYY-MM-DD, first_open, splash, home, splash_any, home_any, language, permission, intro,
                          sample (GA4 read only this share of the events: the numbers are estimates) | null], …]}],
   "summary": [{key, app, status, why, s2h, usual, change, s2h_any, opened, opened_usual, fo_day, fo_day_usual,
                steps {language|permission|intro: [share of Splash, last 7 days], usual}, final_days,
                sample (the lowest of the 7 days, or null)}]}
and the pointer dashboard["firstopen"] = {"file", "v", "apps": {app: {status, s2h, usual, change, fo_day, id}}} (the hub's
card and the tab's nav item read it). Every day of every store, nothing trimmed.

Status, per app: Splash → Home (Home ÷ Splash of the strict funnel) over the last 7 FINAL days (≤ the property's today − 2)
vs the 28 final days before: down ≥ 5 points Worse, ≥ 2 Watch, up ≥ 5 Better, else Normal; fewer than 35 final days Too
early; fewer than 200 Splash users in the 7 days (or 400 in the 28) N/A (too little data to judge).

run(dashboard, data_dir, out_dir, s) → the _headers no-store paths (["/firstopen*"], ONE splat rule) or [] (no store:
the file removed, no pointer). off(out_dir): the switch (FIRSTOPEN_TAB=false). Failure-isolated; ONE counts-only line.
"""
import gzip
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .db import write_json_gz_stable
from .fetch import ga4_firstopen as gf
from .fetch import ga4_uninstall as gu

FILE = "firstopen.json.gz"
HEADER_PATHS = ["/firstopen*"]
V = 1
MAX_GZ = 8 * 1024 * 1024
FIELDS = gf.FIELDS
WORSE, WATCH, BETTER = -0.05, -0.02, 0.05
MIN_DAYS, MIN_SPLASH7, MIN_SPLASH28 = 35, 200, 400
LINE = None


def enabled(s):
    return bool((s or {}).get("firstopen_tab", True))


def _names(dashboard):
    out = {}
    for c in dashboard.get("apps_catalog") or []:
        if c.get("app_id") and c.get("app_name"):
            out.setdefault(str(c["app_id"]), c["app_name"])
    for k in ("uninstall", "active", "value"):
        for a in ((dashboard.get(k) or {}).get("apps") or []):
            if a.get("app_id") and a.get("app"):
                out[str(a["app_id"])] = a["app"]
    return out


def _today(store, now):
    try:
        return now.astimezone(ZoneInfo(store.get("time_zone") or "UTC")).date()
    except Exception:
        return now.date()


def summarize(app, key, rows, final_till):
    """One app's rows (days ascending) → its summary entry (the status rule above)."""
    fin = [r for r in rows if r[0] <= final_till]
    w7, p28 = fin[-7:], fin[-35:-7]
    ix = {f: i + 1 for i, f in enumerate(FIELDS)}

    def s(rs, f):
        return sum(int(r[ix[f]] or 0) for r in rs)
    s7, s28 = s(w7, "splash"), s(p28, "splash")
    s2h = s(w7, "home") / s7 if s7 else None
    usual = s(p28, "home") / s28 if s28 else None
    change = s2h - usual if s2h is not None and usual is not None else None
    if len(fin) < MIN_DAYS:
        status, why = "Too early", "history %d final days" % len(fin)
    elif s7 < MIN_SPLASH7 or s28 < MIN_SPLASH28:
        status, why = "N/A", "low data"
    elif change <= WORSE:
        status, why = "Worse", ""
    elif change <= WATCH:
        status, why = "Watch", ""
    elif change >= BETTER:
        status, why = "Better", ""
    else:
        status, why = "Normal", ""
    f7, f28 = s(w7, "first_open"), s(p28, "first_open")
    sa7 = s(w7, "splash_any")
    steps = {}
    for k in ("language", "permission", "intro"):
        if any(r[ix[k]] is not None for r in rows):
            steps[k] = [s(w7, k) / s7 if s7 else None, s(p28, k) / s28 if s28 else None]
    r6 = lambda v: None if v is None else round(v, 6)
    return {"key": key, "app": app, "status": status, "why": why, "s2h": r6(s2h), "usual": r6(usual), "change": r6(change),
            "s2h_any": r6(s(w7, "home_any") / sa7) if sa7 else None, "opened": r6(s7 / f7) if f7 else None,
            "opened_usual": r6(s28 / f28) if f28 else None, "fo_day": r6(f7 / len(w7)) if w7 else 0,
            "fo_day_usual": r6(f28 / len(p28)) if p28 else None,
            "steps": {k: [r6(a), r6(b)] for k, (a, b) in steps.items()}, "final_days": len(fin),
            "sample": min([r[-1] for r in w7 if r[-1] is not None], default=None)}


def build_data(dashboard, data_dir, now, counts):
    names = _names(dashboard)
    d = os.path.join(data_dir, gf.DIR)
    if not os.path.isdir(d):
        return None
    apps, summary = [], []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json.gz"):
            continue
        store = gf.load_store(os.path.join(d, fn))
        if not store or not store.get("days") or not (store.get("steps") or {}).get("home"):
            counts["skipped"] = counts.get("skipped", 0) + 1
            continue
        aid = str(store.get("app_id") or "")
        app = names.get(aid) or store.get("package") or aid
        key = gu.file_key(aid)
        rows = []
        for day in sorted(store["days"]):
            rec = store["days"][day] or {}
            rows.append([day] + [rec.get(f) if rec.get(f) is not None else (0 if f in ("first_open", "splash", "home")
                                                                          else None) for f in FIELDS] + [rec.get("sample")])
        final_till = (_today(store, now) - timedelta(days=2)).isoformat()
        apps.append({"key": key, "app": app, "app_id": aid, "steps": store.get("steps"),
                     "steps_changed": store.get("steps_changed") or [], "first_day": rows[0][0], "final_till": final_till,
                     "days": rows})
        summary.append(summarize(app, key, rows, final_till))
    if not apps:
        return None
    counts["apps"] = len(apps)
    counts["days"] = sum(len(a["days"]) for a in apps)
    for x in summary:
        counts[x["status"]] = counts.get(x["status"], 0) + 1
    return {"apps": apps, "summary": summary}


def _remove(out_dir):
    try:
        os.remove(os.path.join(out_dir, FILE))
    except OSError:
        pass


def run(dashboard, data_dir, out_dir, s=None, now=None):
    """This build's First open file → HEADER_PATHS, or [] (no store yet / a failure: the file removed, no pointer).
    Never raises."""
    global LINE
    LINE = None
    if not isinstance(dashboard, dict):
        return []
    dashboard.pop("firstopen", None)
    try:
        counts = {}
        data = build_data(dashboard, data_dir, now or datetime.now(timezone.utc), counts)
        if data is None:
            _remove(out_dir)
            LINE = "first open: apps 0, skipped %d" % counts.get("skipped", 0)
            return []
        body = dict(data, v=V)
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        gz = len(gzip.compress(raw, 9, mtime=0))
        if gz > MAX_GZ:
            _remove(out_dir)
            LINE = "first open: too big (%d kb), not written" % (gz // 1024)
            return []
        write_json_gz_stable(os.path.join(out_dir, FILE), body)
        ids = {a["key"]: a["app_id"] for a in data["apps"]}
        dashboard["firstopen"] = {"file": FILE, "v": hashlib.sha1(raw).hexdigest()[:12],
                                  "apps": {x["app"]: dict({k: x[k] for k in ("status", "s2h", "usual", "change", "fo_day")},
                                                          id=ids.get(x["key"], "")) for x in data["summary"]}}
        LINE = ("first open: apps %d, days %d, worse %d, watch %d, better %d, normal %d, too early %d, n/a %d, skipped %d, kb %d"
                % tuple([counts.get(k, 0) for k in ("apps", "days", "Worse", "Watch", "Better", "Normal", "Too early",
                                                    "N/A", "skipped")] + [gz // 1024]))
        return list(HEADER_PATHS)
    except Exception as e:
        dashboard.pop("firstopen", None)
        _remove(out_dir)
        LINE = None
        print("first open skipped: %s" % type(e).__name__, file=sys.stderr)
        return []


def off(out_dir):
    global LINE
    LINE = None
    _remove(out_dir)


def pop_line():
    global LINE
    line, LINE = LINE, None
    return line
