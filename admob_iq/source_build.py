"""💰 Revenue by source — the build step (owner, 31 Oct 2026: notification revenue = GA4 Traffic acquisition → Session
primary channel group "Mobile Push Notifications", exactly as his GA4 screen; a section of the 💸 Install value tab). From
the private stores of fetch.ga4_source, every day of every store, nothing trimmed:

  site/source.json.gz  {"v", "at", "groups": [[id, label, [channels]]], "apps": [{"app_id", "key", "app", "tz", "today",
                        "d0" (the first day with any GA4 session), "rev": [[paid, notification, organic, other], …] (total
                        revenue USD, one row a day d0 … today; null = not read yet), "ses": the same for sessions,
                        "mk": {row: "s" sampled | "t" thresholded}, "bf": the backfill reached the history start,
                        "file": its channel file, "adm": [[month, AdMob revenue USD], …] the complete months of the
                        app's 📈 ROI file (its AdMob days), absent without one — the page's GA4 vs AdMob check}]}
  site/source_<key>.json.gz  {"v", "key", "app_id", "d0", "ch": [GA4 channel names], "days": [[[sessions, active users,
                        ad revenue, total revenue] | null for each channel] | null, …]}   (the GA4 screen's own rows)
and the pointer dashboard["source"] = {"file", "v", "apps": {app id: {"file", "v"}}}.

The 🌍 Countries / 📱 Devices tabs' 💰 Source view (owner, 3 Nov 2026), per app with a store of fetch.ga4_source_cty /
fetch.ga4_source_dev — the same four groups, GA4's own numbers:
  site/source_cc_<key>.json.gz  {"v", "key", "d0", "today", "P": {period: {"lo", "hi", "miss" (days not read yet), "c":
                        {country: [paid, notification, organic, other revenue USD, sessions]}}}} for Today · Yesterday · 7 /
                        30 days (to yesterday) · This / Last month · All time on the app's own days ("--" = GA4 "(not set)",
                        "(other)" = GA4's folded row, both kept)
  site/source_ccd_<key>.json.gz {"v", "key", "d0", "rd": [[first, last] day index runs read], "c": {country: [[day index,
                        the five], …]}} — the days themselves, for Custom (loaded only then)
  site/source_dv_<key>.json.gz  {"v", "key", "w": {window: {"lo", "hi", "at", "rows": [[model, the five], …] biggest first}},
                        "names": {model: [brand, marketing name]} (fetch.ga4_device's)} — whole windows only (30 days,
                        last month, 90 days, all time: GA4 folds much of a short window's models into "(other)")
pointed at from the app's entry: "cc": {"file", "v", "days", "dv", "bf"} and "dv": {"file", "v"}.

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
APP_RE = re.compile(r"^source_(?:cc_|ccd_|dv_)?[0-9a-f]{12}\.json\.gz$")
CC_PERS = ("today", "yday", "7", "30", "tm", "lm", "all")
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


def _admob_months(dashboard, out_dir, aid, now):
    """[[month, AdMob revenue USD]] of the app's complete months (before now's month), from its 📈 ROI file written
    earlier in this build (life: [[AdMob day, revenue USD, …]]); None without one."""
    ptr = (((dashboard.get("roi") or {}).get("apps") or {}).get(aid) or {}).get("file")
    if not ptr or not re.match(r"^roi_[0-9a-f]{12}\.json\.gz$", ptr):
        return None
    try:
        with gzip.open(os.path.join(out_dir, ptr), "rt", encoding="utf-8") as f:
            life = json.load(f).get("life") or []
    except (OSError, ValueError):
        return None
    cur, out = now.strftime("%Y-%m"), {}
    for row in life:
        m = str(row[0])[:7]
        if m < cur and row[1]:
            out[m] = out.get(m, 0.0) + float(row[1])
    return [[m, _r2(v)] for m, v in sorted(out.items())] or None


def _five(by_ch):
    """{channel: [sessions, revenue]} → [paid, notification, organic, other revenue, sessions]."""
    out = [0.0, 0.0, 0.0, 0.0, 0]
    for ch, v in (by_ch or {}).items():
        out[group_of(ch)] += float(v[1] or 0)
        out[4] += int(v[0] or 0)
    return out


def _cc_key(cc):
    return "--" if cc in ("", "(not set)") else cc


def _cc_ranges(d0, today):
    """The page's periods on an app's own days → {period: (first, last)} (7 / 30 days end yesterday: whole days)."""
    y, m1 = today - timedelta(days=1), today.replace(day=1)
    lm = m1 - timedelta(days=1)
    rng = {"today": (today, today), "yday": (y, y), "7": (today - timedelta(days=7), y),
           "30": (today - timedelta(days=30), y), "tm": (m1, today), "lm": (lm.replace(day=1), lm), "all": (d0, today)}
    return {k: (max(a, d0), b) for k, (a, b) in rng.items() if b >= d0}


def cc_files(data_dir, out_dir, aid, now):
    """The app's 🌍 Source files (fetch.ga4_source_cty's days) → its entry's "cc" pointer, or None (no store / no day)."""
    from .fetch import ga4_source_cty as gsc
    meta = gsc.load_store(gsc.store_path(data_dir, aid))
    if not meta:
        return None
    raw = gsc.load_days(data_dir, aid, meta.get("months") or [])
    real = sorted(d for d, rec in raw.items() if rec)
    if not real:
        return None
    d0, today = gu._d(real[0]), _today(meta, now)
    key = gu.file_key(aid)
    rows, read = {}, set()                              # country → {day index: the five}; the day indexes read
    for d, rec in raw.items():
        i = (gu._d(d) - d0).days
        if i < 0:
            continue
        read.add(i)
        for cc, by_ch in (rec or {}).items():
            f = _five(by_ch)
            if any(f):
                e = rows.setdefault(_cc_key(cc), {})
                e[i] = [a + b for a, b in zip(e[i], f)] if i in e else f
    P = {}
    for k, (a, b) in _cc_ranges(d0, today).items():
        i0, i1 = (a - d0).days, (b - d0).days
        c = {}
        for cc, by in rows.items():
            t = [0.0, 0.0, 0.0, 0.0, 0]
            for i, f in by.items():
                if i0 <= i <= i1:
                    t = [x + y for x, y in zip(t, f)]
            if any(t):
                c[cc] = [_r2(x) for x in t[:4]] + [int(t[4])]
        P[k] = {"lo": a.isoformat(), "hi": b.isoformat(), "miss": sum(1 for i in range(i0, i1 + 1) if i not in read),
                "c": c}
    runs, cur = [], None
    for i in sorted(read):
        if cur and i == cur[1] + 1:
            cur[1] = i
        else:
            cur = [i, i]
            runs.append(cur)
    days = {cc: [[i] + [gs._r4(x) for x in f[:4]] + [int(f[4])] for i, f in sorted(by.items())]   # 4 decimals: a Custom
            for cc, by in rows.items()}                                                            # sum = the period's
    body_p = {"v": V, "key": key, "d0": d0.isoformat(), "today": today.isoformat(), "P": P}
    body_d = {"v": V, "key": key, "d0": d0.isoformat(), "rd": runs, "c": days}
    names = {}
    for nm, body in (("cc", body_p), ("ccd", body_d)):
        raw_b = _raw(body)
        if not _fits(raw_b):
            return None
        names[nm] = (PREFIX + nm + "_" + key + ".json.gz", hashlib.sha1(raw_b).hexdigest()[:12], body)
    for fn, _, body in names.values():
        write_json_gz_stable(os.path.join(out_dir, fn), body)
    bf = (meta.get("backfill") or {}).get("done")
    return {"file": names["cc"][0], "v": names["cc"][1], "days": names["ccd"][0], "dv": names["ccd"][1], "bf": bool(bf)}


def dv_file(data_dir, out_dir, aid):
    """The app's 📱 Source file (fetch.ga4_source_dev's windows + fetch.ga4_device's model names) → its entry's "dv"
    pointer, or None (no store / no window)."""
    from .fetch import ga4_device as gd
    from .fetch import ga4_source_dev as gsd
    st = gsd.load_store(gsd.store_path(data_dir, aid))
    if not st or not st.get("w"):
        return None
    key = gu.file_key(aid)
    w, used = {}, set()
    for k in gsd.WINDOWS:
        x = (st.get("w") or {}).get(k)
        if not x:
            continue
        rows = []
        for md, by_ch in (x.get("rows") or {}).items():
            f = _five(by_ch)
            if any(f):
                rows.append([md] + [_r2(v) for v in f[:4]] + [int(f[4])])
                used.add(md)
        rows.sort(key=lambda r: (-(r[1] + r[2] + r[3] + r[4]), -r[5], r[0]))
        w[k] = {"lo": x.get("lo"), "hi": x.get("hi"), "at": x.get("at"), "rows": rows}
    if not w:
        return None
    dst = gd.load_store(gd.store_path(data_dir, aid)) or {}
    names = {m: v for m, v in (dst.get("names") or {}).items() if m in used}
    body = {"v": V, "key": key, "w": w, "names": names}
    raw_b = _raw(body)
    if not _fits(raw_b):
        return None
    fn = PREFIX + "dv_" + key + ".json.gz"
    write_json_gz_stable(os.path.join(out_dir, fn), body)
    return {"file": fn, "v": hashlib.sha1(raw_b).hexdigest()[:12]}


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


def _raw(body):
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _fits(raw):
    """Under MAX_GZ once gzipped — compressed to find out only when the raw bytes alone are over it (a build-time saver)."""
    return len(raw) <= MAX_GZ or len(gzip.compress(raw, 6, mtime=0)) <= MAX_GZ


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
            adm = _admob_months(dashboard, out_dir, aid, now)
            if adm:
                entry["adm"] = adm
            raw, gz = _gz(body)
            if gz > MAX_GZ:
                big += 1
                continue
            os.makedirs(out_dir, exist_ok=True)
            write_json_gz_stable(os.path.join(out_dir, entry["file"]), body)
            keep.add(entry["file"])
            for fld, fn in (("cc", lambda: cc_files(data_dir, out_dir, aid, now)),
                            ("dv", lambda: dv_file(data_dir, out_dir, aid))):
                try:
                    got_x = fn()
                except Exception as e:                  # a bad store costs that view only
                    got_x = None
                    print("source %s skipped: %s" % (fld, type(e).__name__), file=sys.stderr)
                if got_x:
                    entry[fld] = got_x
                    keep.update(v for k, v in got_x.items() if k in ("file", "days"))
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
        LINE = "source: apps %d, days %d, history done %d, channels %d, admob %d, by country %d, by phone %d, kb %d%s" % (
            len(apps), days_n, sum(1 for a in apps if a["bf"]), len(seen), sum(1 for a in apps if a.get("adm")),
            sum(1 for a in apps if a.get("cc")), sum(1 for a in apps if a.get("dv")), gz // 1024,
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
