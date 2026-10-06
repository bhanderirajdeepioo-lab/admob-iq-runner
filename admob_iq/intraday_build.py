"""📈 eCPM "same time yesterday" — the owner, 6 Oct 2026: "yesterday same time pe kitna tha aur abhi kitna hai … hourly".

The AdMob reports have no hour dimension, so the hours come from us: every build records today's AdMob totals SO FAR
(all apps, and each app) with the build's time of day in the report time zone, into data/ecpm_intraday.json (the
private data repo; 8 days kept). The dashboard gets today's and yesterday's points; the eCPM page's Today tile reads
yesterday's totals at the same time of day (between two of yesterday's points) and the last hour's eCPM from the two.

Both days are seen through the same AdMob delay (each point is what the report said at that moment), so the same time
of day compares like with like. Earnings stay in micros of the report currency, as the dashboard's own placements.
Only counts are printed (the runner repo is public)."""
import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

STORE = "ecpm_intraday.json"
KEEP_DAYS = 8                     # today + a week back (same weekday last week stays possible later)
_LINE = []


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict) and st.get("v") == 1 and isinstance(st.get("days"), dict):
            return st
    except (OSError, ValueError):
        pass
    return {"v": 1, "days": {}}


def totals(dashboard, day):
    """(earnings micros, impressions) of `day` for all apps, and {app: (e, i)} — from the dashboard's own placements."""
    e_all = i_all = 0
    apps = {}
    for p in dashboard.get("placements") or []:
        for r in p.get("daily") or []:
            if r and r[0] == day:
                e, i = int(r[1] or 0), int(r[2] or 0)
                e_all += e
                i_all += i
                a = apps.setdefault(p.get("app") or "", [0, 0])
                a[0] += e
                a[1] += i
    return e_all, i_all, apps


def record(dashboard, data_dir, report_tz, now=None):
    """Append this build's point for today (minute of the day in the report time zone); returns the store."""
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo(report_tz or "UTC"))
    today = dashboard.get("today_date") or str(local.date())
    m = local.hour * 60 + local.minute
    e, i, apps = totals(dashboard, today)
    path = os.path.join(data_dir, STORE)
    st = _load(path)
    st["tz"] = report_tz
    pts = [p for p in st["days"].get(today, []) if p[0] != m]          # a second build in the same minute replaces it
    pts.append([m, e, i, {a: v for a, v in apps.items() if v[1] or v[0]}])
    pts.sort(key=lambda p: p[0])
    st["days"][today] = pts
    keep = sorted(st["days"])[-KEEP_DAYS:]
    st["days"] = {d: st["days"][d] for d in keep}
    st.setdefault("since", keep[0] if keep else today)
    os.makedirs(data_dir, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return st


def payload(st, today):
    """What the page needs: today's and yesterday's points, all apps and per app — [minute, earnings micros, impressions]."""
    yday = str((datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).date())
    tp, yp = st["days"].get(today, []), st["days"].get(yday, [])
    out = {"v": 1, "today": today, "yday": yday, "since": st.get("since") or today,
           "t": [p[:3] for p in tp], "y": [p[:3] for p in yp], "apps": {}}
    names = set()
    for p in tp + yp:
        names.update(p[3].keys())
    for a in sorted(names):
        out["apps"][a] = {"t": [[p[0]] + list(p[3].get(a, [0, 0])) for p in tp],
                          "y": [[p[0]] + list(p[3].get(a, [0, 0])) for p in yp]}
    return out


def step(dashboard, data_dir, report_tz, now=None):
    """Record + attach dashboard["ecpm_intraday"]. Never for the demo / sample data; failure-isolated (the error TYPE)."""
    _LINE.clear()
    try:
        if dashboard.get("is_demo") or not dashboard.get("today_date"):
            dashboard.pop("ecpm_intraday", None)
            return
        st = record(dashboard, data_dir, report_tz, now)
        pl = payload(st, dashboard["today_date"])
        dashboard["ecpm_intraday"] = pl
        _LINE.append(f"ecpm intraday: {len(pl['t'])} points today, {len(pl['y'])} yesterday, {len(st['days'])} days kept")
    except Exception as e:                      # never block the dashboard
        dashboard.pop("ecpm_intraday", None)
        _LINE.append(f"ecpm intraday skipped: {type(e).__name__}")


def pop_line():
    return _LINE.pop() if _LINE else ""
