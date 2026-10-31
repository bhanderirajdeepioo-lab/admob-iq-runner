"""💰 Revenue by source — the build step (owner, 31 Oct 2026: notification revenue = GA4 Traffic acquisition → Session
primary channel group "Mobile Push Notifications", exactly as his GA4 screen; a section of the 💸 Install value tab). From
the private stores of fetch.ga4_source, every day of every store, nothing trimmed:

  site/source.json.gz  {"v", "at", "groups": [[id, label, [channels]]], "apps": [{"app_id", "key", "app", "tz", "today",
                        "d0" (the first day with any GA4 session), "rev": [[paid, notification, organic, other], …] (total
                        revenue USD, one row a day d0 … today; null = not read yet), "ses": the same for sessions,
                        "mk": {row: "s" sampled | "t" thresholded}, "bf": the backfill reached the history start,
                        "file": its channel file}]}
  site/source_<key>.json.gz  {"v", "key", "app_id", "d0", "ch": [GA4 channel names], "days": [[[sessions, active users,
                        ad revenue, total revenue] | null for each channel] | null, …]}   (the GA4 screen's own rows)
and the pointer dashboard["source"] = {"file", "v", "apps": {app id: {"file", "v"}}}.

Groups (owner-approved 31 Oct 2026: Paid = Cross-network + Paid Search, Notification = Mobile Push Notifications, Organic
= Direct + Organic Search, Other = (other) + Unassigned); GA4's other default channel groups go to their kind (paid / organic
by name), anything unknown to Other — the page lists every channel under its group.

run(dashboard, data_dir, out_dir, s) → the _headers no-store paths (["/source*"], ONE splat rule) or [] (no store: the
files removed, no pointer). off(out_dir): the switch (SOURCE_TAB=false). Failure-isolated; ONE counts-only line.
"""
import gzip
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .db import write_json_gz_stable
from .fetch import ga4_source as gs
from .fetch import ga4_uninstall as gu

FILE = "source.json.gz"
PREFIX = "source_"
APP_RE = re.compile(r"^source_[0-9a-f]{12}\.json\.gz$")
HEADER_PATHS = ["/source*"]
V = 1
MAX_GZ = 8 * 1024 * 1024
GROUPS = (("paid", "Paid"), ("notif", "Notification"), ("org", "Organic"), ("oth", "Other"))
PAID = ("Cross-network", "Paid Search", "Paid Social", "Paid Video", "Paid Shopping", "Paid Other", "Display", "Audio")
NOTIF = ("Mobile Push Notifications",)
ORGANIC = ("Direct", "Organic Search", "Organic Social", "Organic Video", "Organic Shopping", "Referral", "Email", "SMS",
           "Affiliates", "AI Assistant")
LINE = None


def enabled(s):
    return bool((s or {}).get("source_tab", True))


def group_of(ch):
    """A GA4 session channel → its group index (0 paid, 1 notification, 2 organic, 3 other)."""
    if ch in NOTIF:
        return 1
    if ch in PAID:
        return 0
    if ch in ORGANIC:
        return 2
    return 3


def _names(dashboard):
    out = {}
    for c in dashboard.get("apps_catalog") or []:
        if c.get("app_id") and c.get("app_name"):
            out.setdefault(str(c["app_id"]), c["app_name"])
    return out


def _today(store, now):
    try:
        return now.astimezone(ZoneInfo(store.get("time_zone") or "UTC")).date()
    except Exception:
        return now.date()


def _r2(v):
    v = round(float(v or 0), 2)
    return int(v) if v.is_integer() else v


def build_app(store, aid, name, now):
    """One store → (its entry in source.json.gz, its channel file body) or None (no day with a session yet)."""
    days = store.get("days") or {}
    real = sorted(d for d, rec in days.items() if rec)
    if not real:
        return None
    today = _today(store, now)
    d0 = gu._d(real[0])
    last = max(today, gu._d(real[-1]))
    n = (last - d0).days + 1
    chs = sorted({ch for rec in days.values() for ch in (rec or {})}, key=lambda c: (group_of(c), c))
    rev, ses, per, mk = [], [], [], {}
    for i in range(n):
        d = (d0 + timedelta(days=i)).isoformat()
        rec = days.get(d)
        if rec is None:                                  # not read yet (the backfill goes on)
            rev.append(None)
            ses.append(None)
            per.append(None)
            continue
        r, s = [0.0] * 4, [0] * 4
        for ch, v in rec.items():
            g = group_of(ch)
            s[g] += int(v[0] or 0)
            r[g] += float(v[3] or 0)
        rev.append([_r2(x) for x in r])
        ses.append(s)
        per.append([[int(rec[c][0] or 0), int(rec[c][1] or 0), _r2(rec[c][2]), _r2(rec[c][3])] if c in rec else None
                    for c in chs])
        m = (store.get("mark") or {}).get(d)
        if m:
            mk[str(i)] = m
    key = gu.file_key(aid)
    bf = store.get("backfill") or {}
    entry = {"app_id": aid, "key": key, "app": name, "tz": store.get("time_zone") or "UTC", "today": today.isoformat(),
             "d0": d0.isoformat(), "rev": rev, "ses": ses, "mk": mk, "bf": bool(bf.get("done")), "ch": chs,
             "file": PREFIX + key + ".json.gz"}
    body = {"v": V, "key": key, "app_id": aid, "d0": d0.isoformat(), "ch": chs, "days": per}
    return entry, body


def _stores(data_dir):
    folder = os.path.join(data_dir, gs.DIR)
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    out = []
    for nm in names:
        if not re.match(r"^[0-9a-f]{12}\.json\.gz$", nm):
            continue
        st = gs.load_store(os.path.join(folder, nm))
        if st and st.get("app_id"):
            out.append(st)
    return out


def _clean(out_dir, keep):
    try:
        for nm in os.listdir(out_dir):
            if APP_RE.match(nm) and nm not in keep:
                try:
                    os.remove(os.path.join(out_dir, nm))
                except OSError:
                    pass
    except OSError:
        pass


def _remove(out_dir):
    try:
        os.remove(os.path.join(out_dir, FILE))
    except OSError:
        pass
    _clean(out_dir, set())


def _gz(body):
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return raw, len(gzip.compress(raw, 9, mtime=0))


def run(dashboard, data_dir, out_dir, s=None, now=None):
    """This build's files → HEADER_PATHS, or [] (no store yet / a failure: the files removed, no pointer). Never raises."""
    global LINE
    LINE = None
    if not isinstance(dashboard, dict):
        return []
    dashboard.pop("source", None)
    try:
        now = now or datetime.now(timezone.utc)
        names = _names(dashboard)
        apps, ptr_apps, keep, big, days_n = [], {}, set(), 0, 0
        for st in _stores(data_dir):
            aid = str(st["app_id"])
            got = build_app(st, aid, names.get(aid) or st.get("package") or aid, now)
            if not got:
                continue
            entry, body = got
            raw, gz = _gz(body)
            if gz > MAX_GZ:
                big += 1
                continue
            os.makedirs(out_dir, exist_ok=True)
            write_json_gz_stable(os.path.join(out_dir, entry["file"]), body)
            keep.add(entry["file"])
            ptr_apps[aid] = {"file": entry["file"], "v": hashlib.sha1(raw).hexdigest()[:12]}
            apps.append(entry)
            days_n += len(entry["rev"])
        if not apps:
            _remove(out_dir)
            LINE = "source: apps 0"
            return []
        apps.sort(key=lambda a: (a["app"].lower(), a["app_id"]))
        seen = sorted({c for a in apps for c in a["ch"]}, key=lambda c: (group_of(c), c))
        groups = [[gid, lab, [c for c in seen if group_of(c) == i]] for i, (gid, lab) in enumerate(GROUPS)]
        body = {"v": V, "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "groups": groups, "apps": apps}
        raw, gz = _gz(body)
        if gz > MAX_GZ:
            _remove(out_dir)
            LINE = "source: too big (%d kb), not written" % (gz // 1024)
            return []
        write_json_gz_stable(os.path.join(out_dir, FILE), body)
        _clean(out_dir, keep)
        dashboard["source"] = {"file": FILE, "v": hashlib.sha1(raw).hexdigest()[:12], "apps": ptr_apps}
        LINE = "source: apps %d, days %d, history done %d, channels %d, kb %d%s" % (
            len(apps), days_n, sum(1 for a in apps if a["bf"]), len(seen), gz // 1024,
            (", too big %d" % big) if big else "")
        return list(HEADER_PATHS)
    except Exception as e:
        dashboard.pop("source", None)
        _remove(out_dir)
        LINE = None
        print("source skipped: %s" % type(e).__name__, file=sys.stderr)
        return []


def off(out_dir):
    global LINE
    LINE = None
    _remove(out_dir)


def pop_line():
    global LINE
    line, LINE = LINE, None
    return line
