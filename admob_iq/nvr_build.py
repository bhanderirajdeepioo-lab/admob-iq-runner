"""📈 eCPM — first session vs returning, the build step (owner, 2 Nov 2026: "first session ka ecpm and second session ka ecpm
dono ka difference … ad unit wise"; a section of the eCPM tab's app page). From the private stores of fetch.ga4_nvr, every
day of every store, nothing trimmed — per app ONE lazy file:

  site/nvr_<key>.json.gz  {"v", "key", "app_id", "first_day", "last_day", "final_till" (the property's today − 2: GA4 still
                           adds to the last 2 days),
                           "units": [[ad unit, format], …]   (every ad unit GA4 named, most revenue first),
                           "days": [[YYYY-MM-DD,
                                     [new revenue, new impressions, returning revenue, returning impressions, not set
                                      revenue, not set impressions]          (the day: Σ the country read — it ties whole),
                                     [new sessions, new users, returning sessions, returning users],
                                     {unit index: [new revenue, new impressions, returning revenue, returning impressions]},
                                     {cc: [the same four]}] | null, …]}      (one row a day first … last; null = not read)
  (revenue USD, 4 decimals; "new" = the user's first session, "returning" = session 2 on — GA4's newVsReturning)
and the pointer dashboard["nvr"] = {"v", "apps": {app id: {"file", "v", "from", "last"[, "uc"]}}}.

The ad unit / format tables of a PICKED country (owner, 3 Nov 2026: "US kiya to ad unit table me US ka hi aana chaiye";
every country, every period): from fetch.ga4_nvr_uc's days, per app UC_SHARDS lazy files — a country always in the
same one (shard_of: the page computes it too), so a pick loads one file, never one file a country:
  site/nvr_uc_<key>_<s>.json.gz  {"v", "key", "s", "d0" (= the nvr file's first_day: the same day index),
                           "units": [[ad unit, format], …], "c": {cc: [[day index, unit index, group (0 new · 1
                           returning), revenue, impressions], …]}}   (GA4's not-set group left out: the tables have none)
  "uc" = {"n", "files": [[name, v], …], "from", "last", "rd": [[first, last] day index runs read], "bf", "daily"}
  ({"big": True, "n": 0, "files": []} when even UC_MAX shards are over MAX_GZ).
The page sets what GA4 gave of the country against the nvr file's own country total (its "c": a whole read) and says
how much — GA4 folds a large part of the biggest app's ad unit × country into "(other)" before any read.

run(dashboard, data_dir, out_dir, s) → the _headers no-store paths (["/nvr*"], ONE splat rule) or [] (no store: the files
removed, no pointer). off(out_dir): the switch (NVR_TAB=false). Failure-isolated; ONE counts-only line.
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
from .fetch import ga4_nvr as gv
from .fetch import ga4_uninstall as gu

PREFIX = "nvr_"
APP_RE = re.compile(r"^nvr_(?:uc_)?[0-9a-f]{12}(?:_\d+)?\.json\.gz$")
UC_SHARDS = 8                       # the shard files an app's country data starts with …
UC_MAX = 64                         # … doubled while one is over MAX_GZ, up to this
HEADER_PATHS = ["/nvr*"]
V = 1
MAX_GZ = 8 * 1024 * 1024
LINE = None


def enabled(s):
    return bool((s or {}).get("nvr_tab", True))


def _today(store, now):
    try:
        return now.astimezone(ZoneInfo(store.get("time_zone") or "UTC")).date()
    except Exception:
        return now.date()


def _r4(v):
    v = round(float(v or 0), 4)
    return int(v) if v.is_integer() else v


def build_app(store, aid):
    """One store → its file's body, or None (no day with an ad impression or a session yet)."""
    days = store.get("days") or {}
    real = sorted(d for d, rec in days.items() if rec and (rec.get("c") or rec.get("u") or rec.get("s")))
    if not real:
        return None
    d0, d1 = gu._d(real[0]), gu._d(real[-1])
    urev = {}
    for rec in days.values():
        for k, fm, un, rv, im in (rec or {}).get("u") or []:
            e = urev.setdefault((un, fm), 0.0)
            urev[(un, fm)] = e + float(rv or 0)
    units = [list(k) for k, _ in sorted(urev.items(), key=lambda kv: (-kv[1], kv[0]))]
    uix = {tuple(u): i for i, u in enumerate(units)}
    pos = {"n": 0, "r": 2}
    out = []
    for i in range((d1 - d0).days + 1):
        d = (d0 + timedelta(days=i)).isoformat()
        rec = days.get(d)
        if rec is None:
            out.append(None)
            continue
        tot, ses, us, cs = [0.0] * 6, [0] * 4, {}, {}
        for k, cc, rv, im in rec.get("c") or []:
            j = {"n": 0, "r": 2}.get(k, 4)
            tot[j] += float(rv or 0)
            tot[j + 1] += int(im or 0)
            if k in pos:
                e = cs.setdefault(cc, [0.0, 0, 0.0, 0])
                e[pos[k]] += float(rv or 0)
                e[pos[k] + 1] += int(im or 0)
        for k, n, u in rec.get("s") or []:
            if k in pos:
                ses[pos[k]] += int(n or 0)
                ses[pos[k] + 1] += int(u or 0)
        for k, fm, un, rv, im in rec.get("u") or []:
            if k in pos:
                e = us.setdefault(str(uix[(un, fm)]), [0.0, 0, 0.0, 0])
                e[pos[k]] += float(rv or 0)
                e[pos[k] + 1] += int(im or 0)
        fix = lambda v: [_r4(v[0]), int(v[1]), _r4(v[2]), int(v[3])]
        out.append([d, [_r4(x) if j % 2 == 0 else int(x) for j, x in enumerate(tot)], ses,
                    {k: fix(v) for k, v in sorted(us.items(), key=lambda kv: int(kv[0]))},
                    {k: fix(v) for k, v in sorted(cs.items())}])
    return {"v": V, "key": gu.file_key(aid), "app_id": aid, "first_day": real[0], "last_day": real[-1],
            "units": units, "days": out}


def shard_of(cc, n=UC_SHARDS):
    """A country → its shard of n: two letters → (code 0 × 31 + code 1) mod n (the page computes the same); else 0."""
    return (ord(cc[0]) * 31 + ord(cc[1])) % n if len(cc) == 2 and cc.isalpha() else 0


def uc_files(data_dir, out_dir, aid, d0):
    """The app's ad unit × country shards (fetch.ga4_nvr_uc's days, a month file at a time; day index from d0, the nvr
    file's first day) → its "uc" pointer, or None (no store / no day). UC_SHARDS files, more (×2, up to UC_MAX) when one
    would be over MAX_GZ; still over → {"big": True} (the page says so)."""
    from .fetch import ga4_nvr_uc as gnc
    meta = gnc.load_store(gnc.store_path(data_dir, aid))
    if not meta:
        return None
    base = gu._d(d0)
    units, uix, read, per = [], {}, set(), {}
    first = last = None
    for m in meta.get("months") or []:
        for d, rows in gnc.load_month(data_dir, aid, m).items():
            i = (gu._d(d) - base).days
            if i < 0:
                continue
            read.add(i)
            if rows:
                first = d if first is None or d < first else first
                last = d if last is None or d > last else last
            for k, fm, un, cc, rv, im in rows or []:
                if k not in ("n", "r"):
                    continue
                if (un, fm) not in uix:
                    uix[(un, fm)] = len(units)
                    units.append([un, fm])
                per.setdefault(cc, []).append([i, uix[(un, fm)], 0 if k == "n" else 1, _r4(rv), int(im or 0)])
    if first is None:
        return None
    for v in per.values():
        v.sort()
    runs, cur = [], None
    for i in sorted(read):
        if cur and i == cur[1] + 1:
            cur[1] = i
        else:
            cur = [i, i]
            runs.append(cur)
    out = {"from": first, "last": last, "rd": runs, "bf": bool((meta.get("backfill") or {}).get("done")),
           "daily": bool(meta.get("daily"))}
    key, n = gu.file_key(aid), UC_SHARDS
    while n <= UC_MAX:
        files, bodies = [], []
        for s_i in range(n):
            body = {"v": V, "key": key, "s": s_i, "d0": d0, "units": units,
                    "c": {cc: r for cc, r in sorted(per.items()) if shard_of(cc, n) == s_i}}
            b = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            if len(b) > MAX_GZ and len(gzip.compress(b, 6, mtime=0)) > MAX_GZ:
                break
            files.append(["%suc_%s_%d.json.gz" % (PREFIX, key, s_i), hashlib.sha1(b).hexdigest()[:12]])
            bodies.append(body)
        if len(files) == n:
            for (fn, _), body in zip(files, bodies):
                write_json_gz_stable(os.path.join(out_dir, fn), body)
            out.update(n=n, files=files)
            return out
        n *= 2
    out.update(n=0, files=[], big=True)
    return out


def _stores(data_dir):
    folder = os.path.join(data_dir, gv.DIR)
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    out = []
    for nm in names:
        if not re.match(r"^[0-9a-f]{12}\.json\.gz$", nm):
            continue
        st = gv.load_store(os.path.join(folder, nm))
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


def run(dashboard, data_dir, out_dir, s=None, now=None):
    """This build's files → HEADER_PATHS, or [] (no store yet / a failure: the files removed, no pointer). Never raises."""
    global LINE
    LINE = None
    if not isinstance(dashboard, dict):
        return []
    dashboard.pop("nvr", None)
    try:
        now = now or datetime.now(timezone.utc)
        apps, keep, big, days_n, units_n, uc_n, uc_big = {}, set(), 0, 0, 0, 0, 0
        for st in _stores(data_dir):
            aid = str(st["app_id"])
            body = build_app(st, aid)
            if not body:
                continue
            body["final_till"] = (_today(st, now) - timedelta(days=2)).isoformat()
            raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            if len(gzip.compress(raw, 9, mtime=0)) > MAX_GZ:
                big += 1
                continue
            fn = PREFIX + body["key"] + ".json.gz"
            os.makedirs(out_dir, exist_ok=True)
            write_json_gz_stable(os.path.join(out_dir, fn), body)
            keep.add(fn)
            apps[aid] = {"file": fn, "v": hashlib.sha1(raw).hexdigest()[:12], "from": body["first_day"],
                         "last": body["last_day"]}
            try:
                uc = uc_files(data_dir, out_dir, aid, body["first_day"])
            except Exception as e:                      # a bad store costs the country tables only
                uc = None
                print("nvr uc skipped: %s" % type(e).__name__, file=sys.stderr)
            if uc:
                apps[aid]["uc"] = uc
                keep.update(f for f, _ in uc["files"])
                uc_n += 1 if uc["files"] else 0
                uc_big += 1 if uc.get("big") else 0
            days_n += len(body["days"])
            units_n += len(body["units"])
        _clean(out_dir, keep)
        if not apps:
            LINE = "nvr: apps 0"
            return []
        dashboard["nvr"] = {"v": V, "apps": apps}
        LINE = "nvr: apps %d, days %d, ad units %d, by country %d%s%s" % (
            len(apps), days_n, units_n, uc_n, (", too big %d" % big) if big else "",
            (", by country too big %d" % uc_big) if uc_big else "")
        return list(HEADER_PATHS)
    except Exception as e:
        dashboard.pop("nvr", None)
        _clean(out_dir, set())
        LINE = None
        print("nvr skipped: %s" % type(e).__name__, file=sys.stderr)
        return []


def off(out_dir):
    global LINE
    LINE = None
    _clean(out_dir, set())


def pop_line():
    global LINE
    line, LINE = LINE, None
    return line
