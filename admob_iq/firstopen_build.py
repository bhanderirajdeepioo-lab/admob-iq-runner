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

BY COUNTRY (owner, 20 Oct 2026: "country wise bhi dekh saku esa kara do"): per app with a country store (fetch.
ga4_firstopen_cc, ≥ 1 real day) ONE more lazy file next to it, site/firstopen_cc_<key>.json.gz (key = the app's own):
  {"v", "key", "app_id", "final_till" (the app's), "first_day", "last_day" (the newest real day),
   "missing" (days of the status window final_till − 34 … final_till the store has no real day for; 0 = whole),
   "days": [[YYYY-MM-DD, first_open, splash, home (the day's total), sample | null, {cc: [first_open, splash, home]}], …]
           (every real day of the store, ascending, nothing trimmed — it can have holes; only these three steps exist
           per country),
   "summary": [{cc, status, why, s2h, usual, change, opened, opened_usual, fo_day, fo_day_usual, final_days, sample,
                share (the country's first opens ÷ the day totals', the same 7 days)}]   (EVERY country GA4 named; the
                app's own status rule, summarize() on rows in the app's row layout, fed only the UNBROKEN run of
                calendar days that ends at final_till: a hole (the backfill reads oldest / newest in turn) or a lag (a
                deferred / switched-off fetch) inside the 35 days = Too early with the why, never a window across a hole
                or weeks old; first opens of the 7 days first),
   "unnamed": {"summary": {fo_day, opened, s2h, share}}}   (the day's total − every named country: users GA4 named no
                country for; measured as is, slightly negative on sampled days, never clamped)
and the app's entry in firstopen.json.gz gets "cc": {file, v, from, last, n, days} — only when that file was written. A
failure or a too big file costs only that app's country file; stale country files are removed; the splat rule covers them.

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
import re
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
CC_PREFIX = "firstopen_cc_"
CC_MAX_GZ = MAX_GZ                  # the same guard, per country file
CC_RE = re.compile(r"^firstopen_cc_[0-9a-f]{12}\.json\.gz$")
CC_KEEP = ("status", "why", "s2h", "usual", "change", "opened", "opened_usual", "fo_day", "fo_day_usual", "final_days",
           "sample")
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


# ── by country ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _r6(v):
    return None if v is None else round(v, 6)


def cc_file(key):
    return "%s%s.json.gz" % (CC_PREFIX, key)


def cc_days(store):
    """The country store's real days, ascending → [[D, first_open, splash, home, sample | null, {cc: [three]}], …]. A day
    that is neither {"none": true} nor a whole record raises (that app's country part fails, nothing else)."""
    out = []
    days = store.get("days") or {}
    for d in sorted(days):
        rec = days[d]
        if not isinstance(rec, dict):
            raise ValueError("day")
        if rec.get("none"):
            continue
        date.fromisoformat(d)
        t, c, smp = rec.get("t"), rec.get("c"), rec.get("smp")
        if not (isinstance(t, list) and len(t) == 3 and isinstance(c, dict)):
            raise ValueError("day")
        cs = {}
        for k, v in c.items():
            if not (isinstance(k, str) and k and isinstance(v, list) and len(v) == 3):
                raise ValueError("country")
            cs[k] = [int(x) for x in v]
        out.append([d, int(t[0]), int(t[1]), int(t[2]), None if smp is None else float(smp), cs])
    return out


def cc_window(days, final_till):
    """The country file's status window → (run, missing). run = the indices (oldest first) of the UNBROKEN run of calendar
    days that ends exactly at final_till (empty when the store has no real day for final_till); missing = the calendar days
    of final_till − (MIN_DAYS − 1) … final_till, from the store's first real day on, the store has no real day for.
    The country store is not contiguous the way the app's is (its backfill reads the oldest and the newest day in turn;
    a deferred or switched-off fetch falls behind; a {"none": true} day): a window counted over the stored days would
    straddle a hole or be weeks old while the page says "last 7 days"."""
    have = {d[0]: i for i, d in enumerate(days)}
    end = date.fromisoformat(final_till)
    run, k = [], end
    while k.isoformat() in have:
        run.append(have[k.isoformat()])
        k -= timedelta(days=1)
    run.reverse()
    lo = max(date.fromisoformat(days[0][0]), end - timedelta(days=MIN_DAYS - 1)) if days else end + timedelta(days=1)
    missing = sum(1 for i in range((end - lo).days + 1) if (lo + timedelta(days=i)).isoformat() not in have)
    return run, missing


def build_cc(store, key, aid, final_till):
    """One app's country store → its country file's body, or None (no real day). Every country GA4 named is kept; its
    status is the app's own rule (summarize() on rows in the app's row layout: first_open / splash / home filled, the
    other steps None) fed ONLY the unbroken calendar run ending at final_till (cc_window) — a hole or a lag inside the
    rule's 35 days leaves fewer than MIN_DAYS days, so the rule itself says Too early (why: the hole or the last day);
    the share and the unnamed users over the same 7 calendar days. What GA4 named no country for = the day's total − the
    named countries, as measured. "days" keeps every real day (nothing trimmed); "last_day" = the newest one; "missing" =
    the days the status window lacks (0 = whole)."""
    days = cc_days(store)
    if not days:
        return None
    ccs = sorted(set().union(*(set(d[5]) for d in days)))
    run, missing = cc_window(days, final_till)
    fin_all = [d[0] for d in days if d[0] <= final_till]
    w7 = run[-7:]
    t7 = sum(days[i][1] for i in w7)
    rest = [None] * (len(FIELDS) - 3)
    order = []
    for cc in ccs:
        rows = [[days[i][0]] + list(days[i][5].get(cc) or (0, 0, 0)) + rest + [days[i][4]] for i in run]
        x = summarize(cc, cc, rows, final_till)
        if x["status"] == "Too early" and len(fin_all) > len(run):    # the store has final days the run can not reach
            x["why"] = ("country data %s tak" % fin_all[-1] if fin_all[-1] < final_till
                        else "country data incomplete: %d din missing" % missing)
        f7 = sum(r[1] for r in rows[-7:])
        fall = sum(int((d[5].get(cc) or (0,))[0]) for d in days)
        e = {"cc": cc}
        e.update((k, x[k]) for k in CC_KEEP)
        if not w7:
            e["fo_day"] = None                                       # no day in the window: not known (never "0 / day")
        e["share"] = _r6(f7 / t7) if t7 > 0 else None
        order.append((-f7, -fall, cc, e))
    order.sort(key=lambda z: z[:3])
    un = [[d[j] - sum(v[j - 1] for v in d[5].values()) for j in (1, 2, 3)] for d in days]
    fu, su, hu = (sum(un[i][j] for i in w7) for j in range(3))
    unnamed = {"fo_day": _r6(fu / len(w7)) if w7 else None, "opened": _r6(su / fu) if fu > 0 and su >= 0 else None,
               "s2h": _r6(hu / su) if su > 0 and hu >= 0 else None, "share": _r6(fu / t7) if t7 > 0 else None}
    return {"v": V, "key": key, "app_id": aid, "final_till": final_till, "first_day": days[0][0],
            "last_day": days[-1][0], "missing": missing, "days": days,
            "summary": [z[3] for z in order], "unnamed": {"summary": unnamed}}


def _cc_clean(out_dir, keep):
    try:
        names = os.listdir(out_dir)
    except OSError:
        return
    for f in names:
        if CC_RE.match(f) and f not in keep:
            try:
                os.remove(os.path.join(out_dir, f))
            except OSError:
                pass


def attach_cc(apps, data_dir, out_dir, counts):
    """Every app with a country store: its country file written, then (only then) its "cc" pointer on the app's entry.
    One app's failure (or a file over CC_MAX_GZ) costs only that app's country file; stale country files are removed.
    Never raises."""
    keep, seen = set(), set()
    counts.update(cc_apps=0, cc_kb=0, cc_failed=0, cc_big=0)
    try:
        from .fetch import ga4_firstopen_cc as fc
        for a in apps:
            try:
                store = fc.load_store(fc.store_path(data_dir, a["app_id"]))
                if not store:
                    continue
                body = build_cc(store, a["key"], a["app_id"], a["final_till"])
                if body is None:
                    continue
                raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
                gz = len(gzip.compress(raw, 9, mtime=0))
                if gz > CC_MAX_GZ:
                    counts["cc_big"] += 1
                    continue
                fn, names = cc_file(a["key"]), [x["cc"] for x in body["summary"]]
                ptr = {"file": fn, "v": hashlib.sha1(raw).hexdigest()[:12], "from": body["first_day"],
                       "last": body["last_day"], "n": len(names), "days": len(body["days"])}
                write_json_gz_stable(os.path.join(out_dir, fn), body)
                keep.add(fn)
                a["cc"] = ptr
                seen.update(names)
                counts["cc_apps"] += 1
                counts["cc_kb"] += gz
            except Exception:
                a.pop("cc", None)
                counts["cc_failed"] += 1
    except Exception:
        for a in apps:
            a.pop("cc", None)
        keep = set()
        counts["cc_failed"] += 1
    counts["cc_countries"] = len(seen) if keep else 0
    _cc_clean(out_dir, keep)


def _remove(out_dir):
    try:
        os.remove(os.path.join(out_dir, FILE))
    except OSError:
        pass
    _cc_clean(out_dir, set())


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
        attach_cc(data["apps"], data_dir, out_dir, counts)
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
        LINE += ", by country: apps %d, countries %d, kb %d" % (counts["cc_apps"], counts["cc_countries"],
                                                                counts["cc_kb"] // 1024)
        if counts["cc_failed"] or counts["cc_big"]:
            LINE += ", failed %d, too big %d" % (counts["cc_failed"], counts["cc_big"])
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
