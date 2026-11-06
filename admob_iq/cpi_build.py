"""📉 CPI vs eCPM — the build step (owner, 6 Nov 2026: "short and direct view … sirf one view me direct pata chal jana
chaiye, lekin details dekhna he to kuchh miss nahi hona chahiye"). Google Ads cost per install against AdMob eCPM and
Google's D0 ROAS, one line per app, from this build's own inputs: every app, campaign and country replayed day by day by
engine.cpi_alarm (P_PROD) to the data day t, nothing trimmed:

  t = min(roas.d0.fixed_till, today IST − 2, the last day a Google Ads spend fetch went through, latest_complete): the
  newest day final on every side. GA4 series end at their own data_till (later days null).

  inputs (in memory first): dashboard["roas"]["by_app"] (app NAME → store id; daily_dated = the page's $ view),
  apps_catalog (selected apps: name → AdMob app id), placements (AdMob earnings net + impressions per IST day, every ad
  source), countries_daily (AdMob country, gross), roas.d0, latest_complete; data/roas_spend_cache.json (cost INR as
  billed, biddable installs, Google D0 value), data/fx_series.json (each day's own rate), data/ads_campaign_day,
  data/ads_geo_day, data/ads_archive (tROAS target, bidding, status), data/ads_hourly (the Ads account's clock); this
  build's site files through this build's pointers only: active_<key> (GA4 a1), nvr_<key> (first session vs returning),
  roi_<key> (install-day rows, matured ages only).

  site/cpi.json.gz        {"v", "t", "day0", "apps": {app id: {"h": {"CPI" ₹×100, "ECPM" $×10000, "ROAS_G" ×10000: the
                           engine's healthy level per day day0 … t, null kept}, "ep": [[fam, opener, tier, c, opened,
                           closed, why, base], …] every app episode, all history}}}  (any period besides the default)
  site/cpi_<key>.json.gz  {"v", "app_id", "name", "key", "t", "day0" (the app's first spend − 28 days), "d": {days},
                           "nrm": {fam: normal per day}, "camps": [...], "ctys": [...], "src": [], "ep": [Episode, …],
                           "notes": {...}}  (the details of one app)
  dashboard["cpi"]        the pointer: per app the default view (Last 14 days ending t: status, since, normal, money
                           lost), counts, not linked spend, alerts (sent once: data/cpi/state.json) and closed.
  Units: CPI ₹ per install (as billed), eCPM $ per 1000, ROAS a ratio; money ₹ as billed and $ at each day's own rate.
  Money lost = Σ (cost − D0 value ÷ the frozen normal B) over the days of a ROAS alarm (measured inputs, the formula
  labelled ≈ on the page); a CPI / eCPM / GAP "since" sum is never a loss.

run(dashboard, data_dir, out_dir, s) → the _headers no-store paths (["/cpi*"], ONE splat rule) or [] (no Google Ads
data: the files removed, no pointer). off(out_dir): the switch (CPI_TAB=false). Failure-isolated; ONE counts-only line.
mark_notified_cpi: send_alerts' ledger (each notice ONCE).
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
from .engine import cpi_alarm as CA
from .fetch import ga4_uninstall as gu

FILE = "cpi.json.gz"
PREFIX = "cpi_"
APP_RE = re.compile(r"^cpi_[0-9a-f]{12}\.json\.gz$")
PTR_RE = re.compile(r"^(?:roi|active|nvr)_[0-9a-f]{12}\.json\.gz$")
HEADER_PATHS = ["/cpi*"]
V = 1
MAX_GZ = 8 * 1024 * 1024
STATE_DIR = "cpi"
STATE_V = 1
IST = "Asia/Kolkata"
LEAD_DAYS = 200          # an entity's replay series start this many days before its first spend: every window the
#                          engine reads on its first replay day (H 98, the cohort U 196 days back) lies inside
FILE_LEAD = 28           # a per-app file starts 28 days before the app's first spend
WIN = 14                 # the default view: the last 14 days ending t
CLOSED_DAYS = 7          # "closed": episodes closed in the last 7 days
PUSH_GAP = 7             # at most one push per app per 7 days (engine.cpi_alarm.notifications)
MATCH_DAYS = 7           # an episode (or a re-notice) is the same one across builds when its day moved ≤ 7 days
LATE_DAYS = 7            # a notice first seen more than 7 data days after its day is shown, never sent
CTY_SHARE = 0.02         # a country line in the file: ≥ 2 % of the app's spend, all history or the trailing 120 days
CTY_MAX = 12
SRC_NOTE = ("ad sources not shipped: the only per-source AdMob rows in a build are data/mediation.json.gz (several "
            "seconds to stream) and the Mediation tab's file, written after this step")
SCALE = {"CPI": 100, "ECPM": 10000, "ROAS_G": 10000}
ROWS = ("sp_inr", "sp_usd", "inst", "d0_inr", "rev", "imp", "dau", "fs_rev", "fs_imp", "fs_u", "rt_rev", "rt_imp",
        "rt_u", "c_n", "c_sp", "c_r0", "c_r1", "c_r7")
ENG = ("sp_usd", "sp_inr", "inst", "d0_inr", "rev", "imp", "dau", "c_n", "c_sp", "c_r0", "c_r1", "c_r7")
INT_ROWS = ("imp", "dau", "fs_imp", "fs_u", "rt_imp", "rt_u", "c_n")
ST_ORDER = {"alarm": 0, "watch": 1, "ok": 2, "new": 3, "paused": 4}
FAM_TXT = {"CPI": "CPI", "ECPM": "eCPM", "GAP": "ads to pay back one install", "IPU": "ads per user",
           "ROAS_G": "D0 ROAS", "ROAS_C0": "install-day ROAS (AdMob)", "ROAS_C1": "D1 ROAS (AdMob)",
           "ROAS_C7": "D7 ROAS (AdMob)", "SPEND": "spend"}
LINE = None


def enabled(s):
    return bool((s or {}).get("cpi_tab", True))


# ── small helpers ───────────────────────────────────────────────────────────────────────────────────────────────────

def _d(x):
    return date.fromisoformat(str(x)[:10])


def _iso(d0, i):
    return (d0 + timedelta(days=i)).isoformat()


def _r(v, n=2):
    if v is None:
        return None
    v = round(float(v), n)
    return int(v) if v.is_integer() else v


def _r6(v):
    return None if v is None else round(v, 6)


def _load_json(path):
    try:
        if path.endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return json.load(f)
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, EOFError):
        return None


def _raw(body):
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _fits(raw):
    """Under MAX_GZ once gzipped — compressed to find out only when the raw bytes alone are over it."""
    return len(raw) <= MAX_GZ or len(gzip.compress(raw, 6, mtime=0)) <= MAX_GZ


def _inr(v):
    if v is None:
        return "—"
    a = abs(v)
    sign = "−" if v < 0 else ""
    if a >= 1e7:
        return "%s₹%.2f Cr" % (sign, a / 1e7)
    if a >= 1e5:
        return "%s₹%.1f L" % (sign, a / 1e5)
    if a >= 1e3:
        return "%s₹%.1fk" % (sign, a / 1e3)
    return "%s₹%.0f" % (sign, a)


def _fmt(fam, v):
    if v is None:
        return "—"
    if fam == "CPI":
        return "₹%.1f" % v
    if fam == "ECPM":
        return "$%.2f" % v
    if fam.startswith("ROAS"):
        return "%.1f%%" % (v * 100)
    return "%.2f" % v


def _day_txt(d):
    x = _d(d)
    return "%d %s" % (x.day, x.strftime("%b"))


# ── the data day ────────────────────────────────────────────────────────────────────────────────────────────────────

def spend_ok_till(data_dir, s):
    """The last day a Google Ads spend fetch went through (this build's ROAS step hands it over in s; else the record it
    keeps in data/roas_spend_fetch.json) — None when neither is known."""
    v = (s or {}).get("roas_spend_ok_till")
    if isinstance(v, str) and v:
        return v[:10]
    from .value_build import SPEND_OK_FILE
    rec = _load_json(os.path.join(data_dir, SPEND_OK_FILE))
    v = rec.get("ok_till") if isinstance(rec, dict) else None
    return v[:10] if isinstance(v, str) and v else None


def data_day(dashboard, data_dir, s, now):
    """→ (t, till): t = the newest day final on every side (None: one side is not known), till = each side's own."""
    roas = dashboard.get("roas") or {}
    fixed = ((roas.get("d0") or {}).get("fixed_till") or None)
    today = now.astimezone(ZoneInfo(IST)).date()
    ok = spend_ok_till(data_dir, s)
    lc = dashboard.get("latest_complete")
    till = {"spend": ok, "d0": fixed, "admob": lc}
    sides = [x for x in (fixed, ok, lc) if isinstance(x, str) and x]
    if len(sides) < 3:
        return None, till
    t = min([_d(x) for x in sides] + [today - timedelta(days=2)])
    return t, till


# ── inputs → per-day series ─────────────────────────────────────────────────────────────────────────────────────────

class _Days:
    """One calendar index D0 … t for every series of this build (IST for Google Ads and AdMob; GA4 GMT days joined by
    date)."""

    def __init__(self, d0, t):
        self.d0, self.t = d0, t
        self.n = (t - d0).days + 1
        self.ix = {_iso(d0, i): i for i in range(self.n)}

    def zeros(self):
        return [0.0] * self.n

    def nones(self):
        return [None] * self.n


def _fx(data_dir, dashboard):
    """fn(day) → USD per INR on that day (the ROI section's dated series and lookup; one rate when none)."""
    from .engine import value as val
    from .value_build import _load_fx
    f, _ = val._fx_fn(_load_fx(data_dir, dashboard, "INR"), "INR")
    return f


def _apps(dashboard):
    """The ROAS join's apps that are on this dashboard: [(app NAME, AdMob app id, store id)] (one store id per app name:
    engine.roas.store_owner), selected apps only, sorted by name."""
    by_app = (dashboard.get("roas") or {}).get("by_app") or {}
    ids = {}
    for c in dashboard.get("apps_catalog") or []:
        if c.get("app_name") and c.get("app_id") and c.get("selected", True):
            ids.setdefault(c["app_name"], str(c["app_id"]))
    out = []
    for nm, e in by_app.items():
        aid = ids.get(nm)
        sid = (e or {}).get("store_id")
        if aid and sid:
            out.append((nm, aid, str(sid)))
    out.sort(key=lambda x: (x[0].lower(), x[1]))
    return out


def _first_day(dashboard, cache):
    """The first day of any input series (the AdMob history or the spend cache)."""
    first = None
    for p in dashboard.get("placements") or []:
        rows = p.get("daily") or []
        if rows:
            d = str(rows[0][0])[:10]
            first = d if first is None or d < first else first
    for dd in ((cache or {}).get("daily") or {}).values():
        for d in dd or {}:
            if first is None or d < first:
                first = d
    return _d(first) if first else None


def _spend(D, cache, sid, ok_till, R, dated):
    """One store's Google Ads days → sp_inr (cost as billed), sp_usd (the page's $ view: by_app.daily_dated, else at
    each day's own rate), inst (biddable installs), d0_inr (Google's D0 value). 0 = no spend; after the last good fetch
    every day is null (never 0)."""
    s = {k: D.zeros() for k in ("sp_inr", "sp_usd", "inst", "d0_inr")}
    for key, fld in (("daily", "sp_inr"), ("installs", "inst"), ("convval_day1", "d0_inr")):
        for d, v in ((cache.get(key) or {}).get(sid) or {}).items():
            i = D.ix.get(d)
            if i is not None:
                s[fld][i] += (v or 0) / 1e6 if key == "daily" else float(v or 0)
    for i in range(D.n):
        dd = _iso(D.d0, i)
        du = (dated or {}).get(dd)
        s["sp_usd"][i] = du / 1e6 if du is not None else s["sp_inr"][i] * R[i]
    if ok_till:
        cut = (_d(ok_till) - D.d0).days + 1
        for k in s:
            for i in range(max(0, cut), D.n):
                s[k][i] = None
    return s


def _admob(D, dashboard):
    """{app NAME: (rev, imp)}: the page's AdMob rows (placements: every ad source, net of the tracked deduction), IST
    days; a day without a row is 0."""
    out = {}
    for p in dashboard.get("placements") or []:
        nm = p.get("app")
        rows = p.get("daily") or []
        if not nm or not rows:
            continue
        rv, im = out.setdefault(nm, (D.zeros(), D.zeros()))
        for row in rows:
            i = D.ix.get(str(row[0])[:10])
            if i is not None:
                rv[i] += (row[1] or 0) / 1e6
                im[i] += row[2] or 0
    return out


def _site(out_dir, name):
    if not isinstance(name, str) or not PTR_RE.match(name):
        return None
    return _load_json(os.path.join(out_dir, name))


def _ptrs(dashboard):
    """This build's pointers: {app id: file} for active, roi and nvr (never a listing of the folder: older builds'
    files are still there)."""
    act = {}
    for a in (dashboard.get("active") or {}).get("apps") or []:
        if isinstance(a, dict) and a.get("app_id") and a.get("file"):
            act[str(a["app_id"])] = a["file"]
    roi = {str(k): (v or {}).get("file") for k, v in ((dashboard.get("roi") or {}).get("apps") or {}).items()}
    nvr = {str(k): (v or {}).get("file") for k, v in ((dashboard.get("nvr") or {}).get("apps") or {}).items()}
    return act, roi, nvr


def _ga4(D, s, out_dir, aid, ptrs):
    """GA4 + ROI series into s (null where GA4 has no final day): dau (active a1), fs_* / rt_* (nvr: first session /
    returning revenue, impressions, users), c_n / c_sp / c_r0 / c_r1 / c_r7 (ROI install-day rows; an age only when the
    row holds it as final: df > age). → notes."""
    act, roi, nvr = ptrs
    notes = {}
    for k in ("dau", "fs_rev", "fs_imp", "fs_u", "rt_rev", "rt_imp", "rt_u", "c_n", "c_sp", "c_r0", "c_r1", "c_r7"):
        s[k] = D.nones()
    a = _site(out_dir, act.get(aid))
    if isinstance(a, dict):
        dl = a.get("daily") or {}
        till = a.get("data_till")
        notes["ga4_till"], notes["ga4_tz"] = till, a.get("tz")
        try:
            st = _d(dl["start"])
            for j, v in enumerate(dl.get("a1") or []):
                d = _iso(st, j)
                i = D.ix.get(d)
                if i is not None and v is not None and (not till or d <= till):
                    s["dau"][i] = v
        except (KeyError, TypeError, ValueError):
            pass
    n = _site(out_dir, nvr.get(aid))
    if isinstance(n, dict):
        till = n.get("final_till")
        notes["nvr_till"] = till
        for row in n.get("days") or []:
            if not row or (till and row[0] > till):
                continue
            i = D.ix.get(row[0])
            if i is None:
                continue
            v, u = row[1] or [], row[2] or []
            if len(v) >= 4:
                s["fs_rev"][i], s["fs_imp"][i], s["rt_rev"][i], s["rt_imp"][i] = v[0], v[1], v[2], v[3]
            if len(u) >= 4:
                s["fs_u"][i], s["rt_u"][i] = u[1], u[3]
    r = _site(out_dir, roi.get(aid))
    if isinstance(r, dict):
        for row in r.get("rows") or []:
            i = D.ix.get(row[0])
            if i is None:
                continue
            ser, df = row[4] or [], row[5] or 0
            s["c_n"][i], s["c_sp"][i] = row[1], row[3]
            for age in (0, 1, 7):
                if df > age and len(ser) > age:
                    s["c_r%d" % age][i] = ser[age]
    return notes


def _camps(D, data_dir, store_app, names, R, out_till):
    """{campaign id: {"app", "acct", "s", "cv1"}} from data/ads_campaign_day (the spend fetch's own rows; money in the
    account's currency: INR as billed, a USD account at each day's own rate). Days after the store's till: null."""
    from .fetch import gads_campaign_day as gcd
    from .fetch.gads_store import load_state
    st = load_state(os.path.join(data_dir, gcd.CD_DIR), gcd.CD_V, gcd.DEFAULTS)
    raw = gcd.load(data_dir, D.d0.isoformat(), D.t.isoformat())
    out = {}
    ccy, cm = raw.get("ccy") or {}, raw.get("camp") or {}
    for k in ("cost", "inst", "cv1"):
        for cid, cells in (raw.get(k) or {}).items():
            info = cm.get(cid) or {}
            aid = store_app.get(info.get("s"))
            if not aid:
                continue
            c = out.get(cid)
            if c is None:
                c = out[cid] = {"app": aid, "store": info.get("s"), "acct": info.get("a"), "cv1": False,
                                "s": {x: D.zeros() for x in ("sp_usd", "sp_inr", "inst", "d0_inr")}}
            usd_acct = (ccy.get(info.get("a")) or "INR") == "USD"
            s = c["s"]
            for d, v in cells.items():
                i = D.ix.get(d)
                if i is None:
                    continue
                if k == "inst":
                    s["inst"][i] += float(v or 0)
                    continue
                amt = (v or 0) / 1e6 if k == "cost" else float(v or 0)
                r = R[i]
                usd, inr = (amt, amt / r if r else 0.0) if usd_acct else (amt * r, amt)
                if k == "cost":
                    s["sp_usd"][i] += usd
                    s["sp_inr"][i] += inr
                else:
                    s["d0_inr"][i] += inr
                    c["cv1"] = True
    till = st.get("till")
    out_till[0] = till
    if till:
        cut = (_d(till) - D.d0).days + 1
        for c in out.values():
            for arr in c["s"].values():
                for i in range(max(0, cut), D.n):
                    arr[i] = None
    for cid, c in out.items():
        nm = names.get(cid) or {}
        c["name"], c["status"] = nm.get("name"), nm.get("status")
    return out


def _geo(D, data_dir, store_app, R, out_till):
    """{app id: {cc: {"sp_inr", "sp_usd", "dl"}}} from data/ads_geo_day (cost in the store's base currency INR, DOWNLOAD
    conversions; an unknown count adds nothing). "XX" (not split) is left to the rest. Days after the store's till:
    null."""
    from .fetch import gads_geo_day as ggd
    from .fetch.gads_store import load_state
    st = load_state(os.path.join(data_dir, ggd.GD_DIR), ggd.GD_V, ggd.DEFAULTS)
    raw = ggd.load(data_dir, keep=set(store_app))
    out = {}
    if not raw:
        return out
    usd_base = (raw.get("ccy") or "INR") == "USD"
    for sid, days in (raw.get("days") or {}).items():
        aid = store_app.get(sid)
        if not aid:
            continue
        g = out.setdefault(aid, {})
        for d, ccs in (days or {}).items():
            i = D.ix.get(d)
            if i is None:
                continue
            r = R[i]
            for cc, v in (ccs or {}).items():
                if cc == "XX":
                    continue
                c = g.get(cc)
                if c is None:
                    c = g[cc] = {k: D.zeros() for k in ("sp_inr", "sp_usd", "dl")}
                amt = (v[0] or 0) / 1e6
                if usd_base:
                    c["sp_inr"][i] += amt / r if r else 0.0
                    c["sp_usd"][i] += amt
                else:
                    c["sp_inr"][i] += amt
                    c["sp_usd"][i] += amt * r
                if len(v) > 1 and v[1] is not None:
                    c["dl"][i] += v[1]
    till = st.get("till")
    out_till[0] = till
    if till:
        cut = (_d(till) - D.d0).days + 1
        for g in out.values():
            for c in g.values():
                for arr in c.values():
                    for i in range(max(0, cut), D.n):
                        arr[i] = None
    return out


def _cty_admob(D, rows):
    """countries_daily rows of one app × country → (rev, imp), null on a day without a row (gross, every ad source)."""
    rv, im = D.nones(), D.nones()
    for row in rows or []:
        i = D.ix.get(str(row[0])[:10])
        if i is not None:
            rv[i] = (rv[i] or 0.0) + (row[1] or 0) / 1e6
            im[i] = (im[i] or 0) + (row[2] or 0)
    return rv, im


def _archive(data_dir):
    """{campaign id: {"troas": [[day, ratio], …], "bid", "status", "name"}} from data/ads_archive: the daily snapshots'
    versions and the change events' old → new tROAS (an event's old value held before its day, from the first event day
    kept). → (that map, the first day known)."""
    from .fetch import gads_archive as ga
    mf = ga.months(data_dir)
    pts, info, first_ev = {}, {}, None
    for m in mf.months():
        f = mf.peek(m)
        for acct, rec in sorted((f.get("acct") or {}).items()):
            for ent, vs in sorted((rec.get("ver") or {}).items()):
                if not ent.startswith("camp/"):
                    continue
                cid = ent[5:]
                for day, val in vs or []:
                    if not isinstance(val, dict):
                        continue
                    x = val.get("target_roas.target_roas")
                    if isinstance(x, (int, float)):
                        pts.setdefault(cid, {})[day] = ("s", float(x))
                    i = info.setdefault(cid, {})
                    if not i.get("day") or day >= i["day"]:
                        i.update(day=day, bid=val.get("bidding_strategy_type"), status=val.get("status"),
                                 name=val.get("name"))
            for day, r in sorted((rec.get("days") or {}).items()):
                for ev in r.get("ev") or []:
                    if ev.get("rt") not in (None, "CAMPAIGN") or \
                            not any("targetRoas" in str(x) for x in ev.get("f") or []):
                        continue
                    cid = _ev_cid(ev)
                    if not cid:
                        continue
                    first_ev = day if first_ev is None or day < first_ev else first_ev
                    new, old = (ev.get("new") or {}), (ev.get("old") or {})
                    p = pts.setdefault(cid, {})
                    x = new.get("targetRoas.targetRoas") if isinstance(new, dict) else None
                    if isinstance(x, (int, float)) and p.get(day, ("e",))[0] != "s":
                        p[day] = ("e", float(x))
                    y = old.get("targetRoas.targetRoas") if isinstance(old, dict) else None
                    if isinstance(y, (int, float)):
                        p.setdefault(("old", day), float(y))
        mf.got.pop(m, None)
    out = {}
    for cid in set(pts) | set(info):
        p = pts.get(cid) or {}
        days = {k: v[1] for k, v in p.items() if isinstance(k, str)}
        olds = sorted((k[1], v) for k, v in p.items() if isinstance(k, tuple))
        if olds and first_ev and (not days or min(days) > first_ev):
            day = olds[0][0]
            if first_ev < day:
                days.setdefault(first_ev, olds[0][1])
        series, last = [], None
        for d in sorted(days):
            if days[d] != last:
                series.append([d, round(days[d], 6)])
                last = days[d]
        i = info.get(cid) or {}
        out[cid] = {"troas": series, "bid": i.get("bid"), "status": i.get("status"), "name": i.get("name")}
    firsts = [x["troas"][0][0] for x in out.values() if x["troas"]]
    return out, (min(firsts) if firsts else None)


def _ev_cid(ev):
    for k in ("c", "rn"):
        v = ev.get(k)
        if isinstance(v, str) and v:
            m = re.search(r"campaigns/(\d+)", v)
            if m:
                return m.group(1)
            if v.isdigit() and k == "c":
                return v
    return None


def _clocks(data_dir):
    """Google Ads store → "IST" or the other account zone its campaigns bill on (roi_build's map of data/ads_hourly)."""
    from .roi_build import _ads_tz
    out = {}
    for sid, zones in _ads_tz(data_dir).items():
        z = sorted(x for x in zones if x)
        if z:
            other = [x for x in z if x not in ("Asia/Calcutta", "Asia/Kolkata")]
            out[sid] = other[0] if other else "IST"
    return out


# ── the engine's entities ───────────────────────────────────────────────────────────────────────────────────────────

def _first_spend(arr):
    return next((i for i, v in enumerate(arr) if v), None)


def _ent(kind, eid, app, label, D, s, lo):
    """An engine entity on its own index lo … t (lo = LEAD_DAYS before the first spend, never before D0), values rounded
    to 6 places."""
    return CA.Ent(kind, eid, app, label, _iso(D.d0, lo), {k: [_r6(x) for x in v[lo:]] for k, v in s.items()})


def _lead(arr):
    f = _first_spend(arr)
    return None if f is None else max(0, f - LEAD_DAYS)


def entities(apps, camps, ctys, D):
    """Every app, campaign and country line → engine entities (apps first, each with its countries: the engine's
    country rule reads the app's own spend)."""
    out = []
    for a in apps:
        lo = _lead(a["s"]["sp_usd"])
        if lo is None:
            continue
        out.append(_ent("app", a["app_id"], a["app_id"], a["name"], D, {k: a["s"][k] for k in ENG}, lo))
        for cc, c in sorted((ctys.get(a["app_id"]) or {}).items()):
            lo_c = _lead(c["sp_usd"])
            if lo_c is None:
                continue
            s = {"sp_usd": c["sp_usd"], "sp_inr": c["sp_inr"], "inst": c["dl"]}
            if c.get("imp") and any(c["imp"]):
                s["rev"], s["imp"] = c["rev"], c["imp"]
            out.append(_ent("country", a["app_id"] + "|" + cc, a["app_id"], cc, D, s, lo_c))
    for cid, c in sorted(camps.items()):
        lo = _lead(c["s"]["sp_usd"])
        if lo is None:
            continue
        s = dict(c["s"])
        if not c["cv1"]:
            s.pop("d0_inr", None)
        out.append(_ent("camp", cid, c["app"], c.get("name") or cid, D, s, lo))
    return out


def gather(dashboard, data_dir, out_dir, s, t, counts=None):
    """This build's inputs on one index D0 … t → (D, apps, camps, ctys, extra) — every series the engine and the files
    need (see the module doc)."""
    counts = counts if counts is not None else {}
    cache = _load_json(os.path.join(data_dir, "roas_spend_cache.json"))
    if not isinstance(cache, dict) or cache.get("error") or not isinstance(cache.get("daily"), dict):
        return None
    first = _first_day(dashboard, cache)
    if first is None or first > t:
        return None
    D = _Days(first, t)
    rate = _fx(data_dir, dashboard)
    R = [rate(D.d0 + timedelta(days=i)) or 0.0 for i in range(D.n)]        # USD per INR, each day's own
    ok_till = spend_ok_till(data_dir, s)
    by_app = (dashboard.get("roas") or {}).get("by_app") or {}
    adm = _admob(D, dashboard)
    ptrs = _ptrs(dashboard)
    apps, store_app, names = [], {}, {}
    for nm, aid, sid in _apps(dashboard):
        e = by_app.get(nm) or {}
        sp = _spend(D, cache, sid, ok_till, R, e.get("daily_dated"))
        if not any(sp["sp_inr"]):
            continue
        ser = dict(sp)
        rv, im = adm.get(nm) or (D.zeros(), D.zeros())
        ser["rev"], ser["imp"] = rv, im
        notes = _ga4(D, ser, out_dir, aid, ptrs)
        apps.append({"name": nm, "app_id": aid, "store": sid, "key": gu.file_key(aid), "s": ser, "notes": notes})
        store_app[sid] = aid
        for c in e.get("campaigns") or []:
            if c.get("id") is not None:
                names.setdefault(str(c["id"]), {"name": c.get("name"), "status": c.get("status")})
    for lst in (cache.get("campaigns") or {}).values():
        for c in lst or []:
            if c.get("id") is not None:
                names.setdefault(str(c["id"]), {"name": c.get("name"), "status": c.get("status")})
    extra = {"R": R, "ok_till": ok_till, "cache": cache, "store_app": store_app}
    ct, gt = [None], [None]
    try:
        camps = _camps(D, data_dir, store_app, names, R, ct)
    except Exception as e:                       # a bad campaign store costs the campaign lines only
        camps = {}
        print("cpi campaigns skipped: %s" % type(e).__name__, file=sys.stderr)
    try:
        geo = _geo(D, data_dir, store_app, R, gt)
    except Exception as e:
        geo = {}
        print("cpi countries skipped: %s" % type(e).__name__, file=sys.stderr)
    cd = dashboard.get("countries_daily") or {}
    ctys = {}
    for a in apps:
        g = geo.get(a["app_id"]) or {}
        tot = sum(x for x in a["s"]["sp_usd"] if x)
        lo120 = max(0, D.n - 120)
        tot120 = sum(x for x in a["s"]["sp_usd"][lo120:] if x)
        keep = []
        for cc, c in g.items():
            t_all = sum(x for x in c["sp_usd"] if x)
            t_120 = sum(x for x in c["sp_usd"][lo120:] if x)
            if (tot > 0 and t_all >= CTY_SHARE * tot) or (tot120 > 0 and t_120 >= CTY_SHARE * tot120):
                keep.append((-t_all, cc))
        keep.sort()
        sel = {}
        for _, cc in keep[:CTY_MAX]:
            c = dict(g[cc])
            c["rev"], c["imp"] = _cty_admob(D, (cd.get(a["name"]) or {}).get(cc))
            sel[cc] = c
        ctys[a["app_id"]] = sel
        firsts = [str(r[0][0])[:10] for r in (cd.get(a["name"]) or {}).values() if r]
        a["notes"]["admob_cty_from"] = min(firsts) if firsts else None
    try:
        arch, troas_from = _archive(data_dir)
    except Exception as e:
        arch, troas_from = {}, None
        print("cpi archive skipped: %s" % type(e).__name__, file=sys.stderr)
    for cid, c in camps.items():
        x = arch.get(cid) or {}
        c["troas"], c["bid"] = x.get("troas") or [], x.get("bid")
        c["status"] = c.get("status") or x.get("status")
        c["name"] = c.get("name") or x.get("name")
    extra["troas_from"], extra["camp_till"], extra["geo_till"] = troas_from, ct[0], gt[0]
    try:
        extra["clock"] = _clocks(data_dir)
    except Exception as e:
        extra["clock"] = {}
        print("cpi clock skipped: %s" % type(e).__name__, file=sys.stderr)
    counts["camps"], counts["ctys"] = len(camps), sum(len(v) for v in ctys.values())
    return D, apps, camps, ctys, extra


# ── the default view and money ──────────────────────────────────────────────────────────────────────────────────────

def _span_end(ep, t):
    return ep["closed"] or t


def _overlaps(ep, a, b, t):
    return ep["c"] <= b and _span_end(ep, t) >= a


def normal_at(fam, eps, healthy, D0, a, b):
    """SPEC §1.2: the frozen B of an app episode of `fam` open at b (not settled), else H on the day before a."""
    for ep in eps:
        if ep["fam"] == fam and ep["opened"] <= b and (ep["closed"] is None or ep["closed"] > b) \
                and ep["why"] != "settled":
            return ep["base"]
    h = healthy.get(fam) or []
    i = (_d(a) - D0).days - 1
    return h[i] if 0 <= i < len(h) else None


def day_rate(s, R):
    """USD per ₹ on each day, as the engine's money and the page's $ view take it: that day's sp_usd ÷ sp_inr (the
    dated rate the bill was converted at), carried forward over days with no cost; before the first cost, the FX
    series' own rate."""
    out, last = [], None
    for i, r in enumerate(R):
        sp, su = s["sp_inr"][i], s["sp_usd"][i]
        if sp and su:
            last = su / sp
        out.append(last if last is not None else r)
    return out


def money_lost(eps, s, R, D0, a, b, t):
    """SPEC §1.2: Σ (cost − D0 value ÷ B) over the days of [a, b] inside the app's ROAS_G episodes (₹ as billed, $ at
    each day's own rate); without one, a ROAS_C0 episode's matured install days (c_sp − c_r0 ÷ B). → {"inr", "usd",
    "from": the earliest c, "sc": the same sum from c to b} or None."""
    rate = day_rate(s, R)
    for fam in ("ROAS_G", "ROAS_C0"):
        hit = [ep for ep in eps if ep["fam"] == fam and ep["base"] and _overlaps(ep, a, b, t)]
        if not hit:
            continue
        per = [0.0, 0.0]
        since = [0.0, 0.0]
        c0 = min(ep["c"] for ep in hit)
        for ep in hit:
            for lo, acc in ((max(a, ep["c"]), per), (ep["c"], since)):
                hi = min(b, _span_end(ep, t))
                i0, i1 = (_d(lo) - D0).days, (_d(hi) - D0).days
                for i in range(max(0, i0), i1 + 1):
                    r = rate[i]
                    if fam == "ROAS_G":
                        sp, v, su = s["sp_inr"][i], s["d0_inr"][i], s["sp_usd"][i]
                        if sp is None or v is None:
                            continue
                        acc[0] += sp - v / ep["base"]
                        acc[1] += (su or 0.0) - v * r / ep["base"]
                    else:
                        sp, v = s["c_sp"][i], s["c_r0"][i]
                        if sp is None or v is None:
                            continue
                        x = sp - v / ep["base"]
                        acc[1] += x
                        acc[0] += x / r if r else 0.0
        return {"inr": _r(per[0]), "usd": _r(per[1]), "from": c0, "sc": {"inr": _r(since[0]), "usd": _r(since[1])},
                "fam": fam}
    return None


def status_of(eps, s, nrm, D0, a, b, t):
    """SPEC §1.2: the worst tier among the app's episodes overlapping [a, b] (ALERT → alarm, WATCH → watch; LINE never),
    else ok — new without a normal for CPI and ROAS, paused when b = t and no spend on t−2 … t. → (status, since)."""
    for tier, st in (("ALERT", "alarm"), ("WATCH", "watch")):
        hit = [ep for ep in eps if ep["tier"] == tier and _overlaps(ep, a, b, t)]
        if hit:
            return st, min(ep["c"] for ep in hit)
    if b == t:
        i = (_d(t) - D0).days
        if not any(s["sp_inr"][j] for j in range(max(0, i - 2), i + 1) if s["sp_inr"][j] is not None):
            return "paused", None
    if nrm.get("CPI") is None and nrm.get("ROAS_G") is None:
        return "new", None
    return "ok", None


def window(s, D0, a, b):
    """CPI (₹), eCPM ($) and D0 ROAS over [a, b] — ratio of sums (None without volume)."""
    i0, i1 = (_d(a) - D0).days, (_d(b) - D0).days

    def tot(k):
        return sum(x for x in s[k][max(0, i0):i1 + 1] if x)
    sp, n, rv, im, v = tot("sp_inr"), tot("inst"), tot("rev"), tot("imp"), tot("d0_inr")
    return {"CPI": sp / n if n else None, "ECPM": rv / im * 1000 if im else None, "ROAS_G": v / sp if sp else None,
            "sp_inr": sp, "sp_usd": tot("sp_usd")}


# ── the files ───────────────────────────────────────────────────────────────────────────────────────────────────────

def _ep_row(ep):
    return [ep["fam"], ep["opener"], ep["tier"], ep["c"], ep["opened"], ep["closed"], ep["why"], _r6(ep["base"])]


def _ep_full(ep):
    out = {k: ep[k] for k in ("kind", "id", "app", "fam", "opener", "tier", "c", "opened", "seen", "closed", "why",
                              "base_src", "confirm")}
    out.update(base=_r6(ep["base"]), thr_open=_r(ep["thr_open"], 4), max_worse=_r(ep["max_worse"], 4),
               esc=[list(x) for x in ep["esc"]], ctx=dict(ep.get("ctx") or {}),
               money=dict(ep["money"]) if ep.get("money") else None, stake=list(ep.get("stake") or []))
    return out


def _cut(arr, lo, n_row):
    out = []
    for v in arr[lo:]:
        out.append(None if v is None else (int(round(v)) if n_row else _r(v, 2)))
    return out


def _app_file(a, D, lo, res, camps, ctys, eps_by, extra, t):
    """One app → its details file body (every day from its first spend − 28 days to t)."""
    aid = a["app_id"]
    s = a["s"]
    d = {k: _cut(s[k], lo, k in INT_ROWS) for k in ROWS}
    off = None
    key = ("app", aid)
    nrm = {}
    e_d0 = None
    for ent_key, arrs in (res.get("normal") or {}).items():
        if ent_key == key:
            e_d0 = arrs
    if e_d0 is not None:
        e0 = _d(extra["day0"][aid])
        off = (D.d0 + timedelta(days=lo) - e0).days
        for fam in CA.OUT_FAMS:
            arr = e_d0.get(fam) or []
            nrm[fam] = [_r6(x) for x in arr[off:]] if off >= 0 else [None] * (-off) + [_r6(x) for x in arr]
    cl = []
    for cid, c in sorted(camps.items()):
        if c["app"] != aid:
            continue
        f = _first_spend(c["s"]["sp_usd"])
        if f is None:
            continue
        f = max(f, lo)
        cl.append({"id": cid, "name": c.get("name"), "status": c.get("status"), "bid": c.get("bid"),
                   "troas": c.get("troas") or [], "from": _iso(D.d0, f),
                   "d": {k: _cut(c["s"][k], f, False) for k in ("sp_inr", "sp_usd", "inst", "d0_inr")},
                   "ep": [_ep_row(ep) for ep in eps_by.get(("camp", cid), [])]})
    cl.sort(key=lambda x: (-sum(v for v in x["d"]["sp_inr"] if v), x["id"]))
    ct = []
    for cc, c in sorted((ctys.get(aid) or {}).items()):
        f = _first_spend(c["sp_usd"])
        fr = next((i for i, v in enumerate(c["imp"]) if v is not None), None)
        f = min(x for x in (f, fr) if x is not None) if (f is not None or fr is not None) else None
        if f is None:
            continue
        f = max(f, lo)
        ct.append({"cc": cc, "from": _iso(D.d0, f),
                   "d": {"sp_inr": _cut(c["sp_inr"], f, False), "sp_usd": _cut(c["sp_usd"], f, False),
                         "dl": _cut(c["dl"], f, False), "rev": _cut(c["rev"], f, False),
                         "imp": _cut(c["imp"], f, True)},
                   "ep": [_ep_row(ep) for ep in eps_by.get(("country", aid + "|" + cc), [])]})
    ct.sort(key=lambda x: (-sum(v for v in x["d"]["sp_inr"] if v), x["cc"]))
    n = a["notes"]
    notes = {"clock": extra["clock"].get(a["store"]), "ga4_till": n.get("ga4_till"), "ga4_tz": n.get("ga4_tz"),
             "nvr_till": n.get("nvr_till"), "ga4_sampled": None, "admob_cty_from": n.get("admob_cty_from"),
             "troas_from": extra.get("troas_from"), "spend_ok_till": extra.get("ok_till"),
             "geo_till": extra.get("geo_till"), "camp_till": extra.get("camp_till"),
             "src": SRC_NOTE, "ga4_sampled_note": "not in this build's GA4 site files",
             "cty_rule": "share>=%g all history or last 120 days, top %d" % (CTY_SHARE, CTY_MAX)}
    return {"v": V, "app_id": aid, "name": a["name"], "key": a["key"], "t": t.isoformat(),
            "day0": _iso(D.d0, lo), "d": d, "nrm": nrm, "camps": cl, "ctys": ct, "src": [],
            "ep": [_ep_full(ep) for ep in eps_by.get(key, [])], "notes": notes}


def build_files(dashboard, D, apps, camps, ctys, extra, res, now):
    """The engine's result → (pointer body without alerts, cpi.json.gz body, {file name: per-app body}, counts)."""
    t = D.t
    ts = t.isoformat()
    eps_by = {}
    for ep in res["episodes"]:
        eps_by.setdefault((ep["kind"], ep["id"]), []).append(ep)
    a_iso, b_iso = (t - timedelta(days=WIN - 1)).isoformat(), ts
    ptr_apps, all_h, files = {}, {}, {}
    counts = {k: 0 for k in ST_ORDER}
    big = 0
    los = []
    for a in apps:
        lo = _first_spend(a["s"]["sp_usd"])
        if lo is None:
            continue
        lo = max(0, lo - FILE_LEAD)
        los.append(lo)
        a["lo"] = lo
    g0 = min(los) if los else 0
    for a in apps:
        if "lo" not in a or a["app_id"] not in extra["day0"]:
            continue
        aid = a["app_id"]
        eps = eps_by.get(("app", aid), [])
        e0 = _d(extra["day0"][aid])
        hl = res["healthy"].get(("app", aid)) or {}
        nrm = {f: normal_at(f, eps, hl, e0, a_iso, b_iso) for f in ("CPI", "ECPM", "ROAS_G")}
        st, since = status_of(eps, a["s"], nrm, D.d0, a_iso, b_iso, ts)
        lost = money_lost(eps, a["s"], extra["R"], D.d0, a_iso, b_iso, ts)
        w = window(a["s"], D.d0, a_iso, b_iso)
        if w["sp_inr"] > 0:
            counts[st] += 1
        body = _app_file(a, D, a["lo"], res, camps, ctys, eps_by, extra, t)
        raw = _raw(body)
        if not _fits(raw):
            big += 1
            continue
        fn = PREFIX + a["key"] + ".json.gz"
        files[fn] = body
        ptr_apps[aid] = {"name": a["name"], "key": a["key"], "file": fn, "v": hashlib.sha1(raw).hexdigest()[:12],
                         "st": st, "since": since,
                         "open": [[ep["fam"], ep["opener"], ep["tier"], ep["c"], ep["opened"], _r6(ep["base"])]
                                  for ep in eps if ep["closed"] is None],
                         "nrm": {f: _r6(v) for f, v in nrm.items()},
                         "lost": ({k: lost[k] for k in ("inr", "usd", "from", "sc")} if lost else None)}
        off = (D.d0 + timedelta(days=g0) - e0).days
        h = {}
        for fam in ("CPI", "ECPM", "ROAS_G"):
            arr = hl.get(fam) or []
            vals = arr[off:] if off >= 0 else [None] * (-off) + list(arr)
            h[fam] = [None if v is None else int(round(v * SCALE[fam])) for v in vals]
        all_h[aid] = {"h": h, "ep": [_ep_row(ep) for ep in eps]}
        a["view"] = {"st": st, "since": since, "nrm": nrm, "lost": lost, "w": w, "eps": eps}
    allb = {"v": V, "t": ts, "day0": _iso(D.d0, g0), "apps": all_h}
    unl = _unlinked(D, extra, a_iso, b_iso, dashboard)
    ptr = {"v": V, "t": ts, "at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "day0": _iso(D.d0, g0), "file": FILE, "apps": ptr_apps, "counts": counts, "unlinked": unl}
    return ptr, allb, files, big


def _unlinked(D, extra, a, b, dashboard):
    """Google Ads spend in [a, b] on store ids with no row on this screen (not linked to a dashboard app, or the app is
    not selected): ₹ as billed, $ at each day's own rate, the number of store ids."""
    cache, R = extra["cache"], extra["R"]
    linked = set(extra["store_app"])
    inr = usd = 0.0
    n = 0
    for sid, dd in (cache.get("daily") or {}).items():
        if sid in linked:
            continue
        x = 0.0
        for d, v in (dd or {}).items():
            if a <= d <= b and v:
                amt = v / 1e6
                x += amt
                usd += amt * R[D.ix[d]] if d in D.ix else 0.0
        if x > 0:
            inr += x
            n += 1
    return {"inr": _r(inr), "usd": _r(usd), "n": n}


# ── alerts (sent once) ──────────────────────────────────────────────────────────────────────────────────────────────

def state_path(data_dir):
    return os.path.join(data_dir, STATE_DIR, "state.json")


def load_state(data_dir):
    """The private ledger {"v", "eps": {key: record}, "push": {app id: last push day}, "due": {alert id: [[key, day],
    …]}}; a default on a missing or broken file (first = True: every open episode is seeded)."""
    st = {"v": STATE_V, "eps": {}, "push": {}, "due": {}}
    raw = _load_json(state_path(data_dir))
    if not isinstance(raw, dict) or raw.get("v") != STATE_V:
        return st, True
    for k in ("eps", "push", "due"):
        if isinstance(raw.get(k), dict):
            st[k] = raw[k]
    st["eps"] = {k: v for k, v in st["eps"].items() if isinstance(v, dict) and isinstance(v.get("opened"), str)
                 and isinstance(v.get("notices"), dict)}
    return st, False


def save_state(data_dir, st):
    """Sorted JSON, written only when it changed. → True when written."""
    path = state_path(data_dir)
    text = json.dumps(st, ensure_ascii=False, sort_keys=True, indent=1)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(path + ".tmp", path)
    return True


def _match(st, aid, fam, opened, used):
    """The ledger record of this episode: same app and family, opened within ±7 days (data restates), and not one that
    closed before this episode opened (a new episode right after an old one is its own) — or None."""
    best = None
    for k, r in st["eps"].items():
        if k in used or r.get("app_id") != aid or r.get("fam") != fam:
            continue
        if r.get("closed") and r["closed"] < opened:
            continue
        gap = abs((_d(r["opened"]) - _d(opened)).days)
        if gap <= MATCH_DAYS and (best is None or gap < best[0]):
            best = (gap, k)
    return best[1] if best else None


def _notice_key(rec, day, is_open):
    """A notice's key in its record: "open" for the opening; a re-notice by its day, or the key of a re-notice already
    kept within ±7 days of it (the same re-notice, its day moved by restated data)."""
    if is_open:
        return "open"
    best = None
    for k in rec["notices"]:
        if k == "open":
            continue
        gap = abs((_d(k) - _d(day)).days)
        if gap <= MATCH_DAYS and (best is None or gap < best[0]):
            best = (gap, k)
    return best[1] if best else day


def _ledger(st, first, apps, t, now):
    """Every open (and lately closed) ALERT / WATCH app episode → its ledger record; each ALERT notice (the opening,
    every re-notice) is due ONCE: never on the first build (seeded), never when first seen > LATE_DAYS after its day,
    and joined (not sent) when the app had a push in the PUSH_GAP days before. → {(app id, fam, opened): (key, due)},
    due = [notice key, …]."""
    used, out = set(), {}
    now_iso = gu._now_iso(now)
    for a in apps:
        v = a.get("view")
        if not v:
            continue
        aid = a["app_id"]
        for ep in v["eps"]:
            if ep["tier"] not in ("ALERT", "WATCH"):
                continue
            if ep["closed"] is not None and (t - _d(ep["closed"])).days >= CLOSED_DAYS:
                continue
            k = _match(st, aid, ep["fam"], ep["opened"], used)
            if k is None:
                k = "%s|%s|%s" % (aid, ep["fam"], ep["opened"])
                st["eps"][k] = {"app_id": aid, "fam": ep["fam"], "opened": ep["opened"], "seeded": bool(first),
                                "first_at": now_iso, "notices": {}}
            used.add(k)
            rec = st["eps"][k]
            rec["tier"], rec["closed"] = ep["tier"], ep["closed"]
            due = []
            if ep["tier"] == "ALERT" and ep["closed"] is None:
                for day, is_open in [(ep["opened"], True)] + [(d, False) for d, _ in ep["esc"]]:
                    nk = _notice_key(rec, day, is_open)
                    n = rec["notices"].get(nk)
                    if n is not None:
                        if n.get("notified_at") is None and not n.get("seeded") and not n.get("joined"):
                            due.append(nk)
                        continue
                    if first or (t - _d(day)).days > LATE_DAYS:
                        rec["notices"][nk] = {"day": day, "seeded": True}
                        continue
                    last = st["push"].get(aid)
                    if last and 0 <= (_d(day) - _d(last)).days <= PUSH_GAP:
                        rec["notices"][nk] = {"day": day, "joined": last}
                        continue
                    rec["notices"][nk] = {"day": day, "notified_at": None}
                    due.append(nk)
            out[(aid, ep["fam"], ep["opened"])] = (k, due)
    return out


def _alert_item(a, ep, rec, due, t, others, closed=False):
    """One app's alert in the GA4 families' shape (the Alerts screen's link note and send_alerts): `text` Hinglish,
    `message` plain (₹ for cost, CPI and money, $ for eCPM). id = the episode + its newest notice day, so a re-notice is
    a new id (sent once) and a re-run keeps the same one."""
    v = a["view"]
    w, nrm = v["w"], v["nrm"]
    fam, nm = ep["fam"], a["name"]
    now_v = w.get(fam) if fam in ("CPI", "ECPM", "ROAS_G") else None
    base = ep["base"]
    rel = (now_v / base - 1.0) if (now_v is not None and base) else None
    since, what = _day_txt(ep["c"]), FAM_TXT.get(fam, fam)
    moves = ["%s %s → %s" % (FAM_TXT[f], _fmt(f, nrm.get(f)), _fmt(f, w[f])) for f in ("CPI", "ECPM")
             if f != fam and w.get(f) is not None]
    lost = v.get("lost")
    sc = (lost or {}).get("sc") or {}
    if CA.FAMILIES[fam]["bad"] > 0:
        head_h, head_p = "%s %s se normal se upar" % (what, since), "%s above normal since %s" % (what, since)
    else:
        head_h, head_p = "%s %s se normal se neeche" % (what, since), "%s below normal since %s" % (what, since)
    now_txt = ("%s (normal %s)" % (_fmt(fam, now_v), _fmt(fam, base))) if now_v is not None \
        else "normal %s" % _fmt(fam, base)
    text = "%s: %s." % (head_h, now_txt) + ((" " + ", ".join(moves) + ".") if moves else "")
    msg = "%s: %s" % (head_p, now_txt) + "".join(" · " + m for m in moves)
    if sc.get("inr") is not None and sc["inr"] > 0:
        text += " ≈ %s zyada kharch hua (%s se ab tak)." % (_inr(sc["inr"]), _day_txt(lost["from"]))
        msg += " · ≈ %s lost since %s" % (_inr(sc["inr"]), _day_txt(lost["from"]))
    if others:
        text += " Saath me: %s." % ", ".join(FAM_TXT.get(f, f) for f in others)
        msg += " · also " + ", ".join(FAM_TXT.get(f, f) for f in others)
    esc = sorted(k for k in rec.get("notices") or {} if k != "open")
    item = {"id": "cpi_%s|%s|%s|%s" % (fam, a["app_id"], rec["opened"], esc[-1] if esc else "open"),
            "source": "cpi", "app_id": a["app_id"], "app": nm, "family": fam, "metric": fam,
            "dir": "up" if CA.FAMILIES[fam]["bad"] > 0 else "down",
            "severity": "warning" if ep["tier"] == "ALERT" else "watch", "tier": ep["tier"],
            "unit": {"CPI": "inr", "ECPM": "usd"}.get(fam, "ratio"),
            "opened": ep["opened"], "opened_at": rec.get("first_at"), "alert_at": _alert_at(rec) or rec.get("first_at"),
            "since": ep["c"], "started": ep["c"], "started_cap": False, "data_till": t.isoformat(),
            "now": _r6(now_v), "before": _r6(base), "rel": _r(rel, 4) if rel is not None else None,
            "notify": bool(due) and not closed, "seeded": bool(rec.get("seeded")), "provisional": False,
            "estimate": False, "fresh": (t - _d(ep["opened"])).days < 7,
            "lost": {"inr": sc.get("inr"), "usd": sc.get("usd"), "from": lost["from"]} if sc else None,
            "text": text, "message": "%s: %s" % (nm, msg)}
    if closed:
        item.update(closed=ep["closed"], closed_at=None, close_reason=ep["why"], notify=False)
    return item


def _alert_at(rec):
    ats = [n.get("notified_at") for n in (rec.get("notices") or {}).values() if n.get("notified_at")]
    return max(ats) if ats else None


def alerts(st, first, apps, t, now):
    """→ (alerts, closed): one alert per app with an open ALERT or WATCH episode (its worst one: ALERT before WATCH, a
    ROAS alarm first, then the earliest change), the app's episodes closed in the last CLOSED_DAYS days; st["due"] = the
    notices each due alert id carries (mark_notified_cpi)."""
    led = _ledger(st, first, apps, t, now)
    st["due"] = {}
    out, closed = [], []
    for a in apps:
        v = a.get("view")
        if not v:
            continue
        opn = [ep for ep in v["eps"] if ep["closed"] is None and ep["tier"] in ("ALERT", "WATCH")]
        if opn:
            opn.sort(key=lambda ep: (ep["tier"] != "ALERT", not ep["fam"].startswith("ROAS"), ep["c"], ep["fam"]))
            main = opn[0]
            due = []
            for ep in opn:
                k, d = led[(a["app_id"], ep["fam"], ep["opened"])]
                due += [[k, x] for x in d]
            k = led[(a["app_id"], main["fam"], main["opened"])][0]
            item = _alert_item(a, main, st["eps"][k], sorted(x[1] for x in due), t,
                               sorted({ep["fam"] for ep in opn[1:]} - {main["fam"]}))
            if due:
                st["due"][item["id"]] = sorted(due)
            out.append(item)
        for ep in v["eps"]:
            if ep["closed"] is not None and ep["tier"] in ("ALERT", "WATCH") and \
                    (t - _d(ep["closed"])).days < CLOSED_DAYS:
                key = led.get((a["app_id"], ep["fam"], ep["opened"]))
                if key:
                    closed.append(_alert_item(a, ep, st["eps"][key[0]], [], t, [], closed=True))
    keep = {k for k, _ in led.values()}
    for k in list(st["eps"]):
        if k not in keep and (t - _d(st["eps"][k]["opened"])).days > 400:
            del st["eps"][k]                   # a long-gone episode: dropped (the ledger stays small)
    out.sort(key=lambda x: (x["severity"] != "warning", x["since"], x["app"], x["id"]))
    closed.sort(key=lambda x: (x["closed"], x["app"], x["id"]), reverse=True)
    return out, closed


def mark_notified_cpi(data_dir, summary, dry, now=None, ids=None):
    """After send_alerts: the CPI alerts that were due and went out (`ids` = build_static.uninstall_delivered; None =
    all of them) are sent — or, in a dry run, counted as sent — and never sent again (each notice once; the app's push
    day starts its PUSH_GAP)."""
    due = {a["id"] for a in (summary or {}).get("alerts") or [] if a.get("notify")}
    ids = due if ids is None else due & set(ids)
    if not ids:
        return 0
    st, _ = load_state(data_dir)
    now_iso = gu._now_iso(now or datetime.now(timezone.utc))
    n = 0
    for i in sorted(ids):
        for k, day in st["due"].get(i) or []:
            rec = st["eps"].get(k)
            if not rec:
                continue
            note = rec["notices"].get(day)
            if note is None or note.get("seeded") or note.get("joined"):
                continue
            if note.get("notified_at") is None:
                note["notified_at"], note["notified_dry"] = now_iso, bool(dry)
                n += 1
                d = note.get("day") or rec["opened"]
                last = st["push"].get(rec["app_id"])
                if not last or d > last:
                    st["push"][rec["app_id"]] = d
        st["due"].pop(i, None)
    save_state(data_dir, st)
    return n


# ── the step ────────────────────────────────────────────────────────────────────────────────────────────────────────

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


def compute(dashboard, data_dir, out_dir, s, now, counts=None):
    """The whole step without writing → (pointer, cpi.json.gz body, per-app bodies, apps, D, engine result) or None
    (no Google Ads data / no data day)."""
    roas = dashboard.get("roas") or {}
    if not roas.get("configured", bool(roas.get("by_app"))) or not roas.get("by_app"):
        return None
    t, till = data_day(dashboard, data_dir, s, now)
    if t is None:
        return None
    got = gather(dashboard, data_dir, out_dir, s, t, counts)
    if not got:
        return None
    D, apps, camps, ctys, extra = got
    ents = entities(apps, camps, ctys, D)
    extra["day0"] = {e.id: e.day0 for e in ents if e.kind == "app"}
    res = CA.run(ents, CA.P_PROD, t.isoformat())
    ptr, allb, files, big = build_files(dashboard, D, apps, camps, ctys, extra, res, now)
    if counts is not None:
        counts["big"] = big
    gt = [a["notes"].get("ga4_till") for a in apps if a.get("view") and a["notes"].get("ga4_till")]
    till["ga4"] = min(gt) if gt else None
    ptr["till"] = till
    return ptr, allb, files, apps, D, res


def run(dashboard, data_dir, out_dir, s=None, now=None):
    """This build's files → HEADER_PATHS, or [] (no Google Ads data / a failure: the files removed, no pointer). Never
    raises."""
    global LINE
    LINE = None
    if not isinstance(dashboard, dict):
        return []
    dashboard.pop("cpi", None)
    try:
        now = now or datetime.now(timezone.utc)
        counts = {}
        got = compute(dashboard, data_dir, out_dir, s, now, counts)
        if not got:
            _remove(out_dir)
            LINE = "cpi: apps 0"
            return []
        ptr, allb, files, apps, D, res = got
        raw = _raw(allb)
        if not _fits(raw):
            _remove(out_dir)
            LINE = "cpi: too big (%d kb), not written" % (len(gzip.compress(raw, 6, mtime=0)) // 1024)
            return []
        os.makedirs(out_dir, exist_ok=True)
        for fn, body in sorted(files.items()):
            write_json_gz_stable(os.path.join(out_dir, fn), body)
        write_json_gz_stable(os.path.join(out_dir, FILE), allb)
        _clean(out_dir, set(files))
        st, first = load_state(data_dir)
        al, closed = alerts(st, first, apps, D.t, now)
        save_state(data_dir, st)
        ptr["fv"] = hashlib.sha1(raw).hexdigest()[:12]
        ptr["alerts"], ptr["closed"] = al, closed
        dashboard["cpi"] = ptr
        c = ptr["counts"]
        LINE = ("cpi: apps %d, alarm %d, watch %d, ok %d, new %d, paused %d, episodes %d, campaigns %d, countries %d%s"
                % (len(files), c["alarm"], c["watch"], c["ok"], c["new"], c["paused"],
                   sum(1 for ep in res["episodes"] if ep["kind"] == "app"), counts.get("camps", 0),
                   counts.get("ctys", 0), (", too big %d" % counts["big"]) if counts.get("big") else ""))
        return list(HEADER_PATHS)
    except Exception as e:
        dashboard.pop("cpi", None)
        _remove(out_dir)
        LINE = None
        print("cpi skipped: %s" % type(e).__name__, file=sys.stderr)
        return []


def off(out_dir):
    global LINE
    LINE = None
    _remove(out_dir)


def pop_line():
    global LINE
    line, LINE = LINE, None
    return line
