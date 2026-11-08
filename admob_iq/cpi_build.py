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

  site/cpi.json.gz        {"v", "t", "day0", "apps": {app id: {"h": {"CPI" ₹×100, "ECPM" $×10000, "ROAS_G" ×10000, "GAP" ads×100: the
                           engine's healthy level per day day0 … t, null kept}, "ep": [[fam, opener, tier, c, opened,
                           closed, why, base], …] every app episode, all history}}}  (any period besides the default)
  site/cpi_<key>.json.gz  {"v", "app_id", "name", "key", "t", "day0" (the app's first spend − 28 days), "d": {days},
                           "nrm": {fam: normal per day}, "camps": [...], "ctys": [...], "src": [], "ep": [Episode, …],
                           "notes": {...}}  (the details of one app). A country line (ctys[]): {"cc", "from", "d":
                           {sp_inr, sp_usd, dl, rev, imp, r0}, "nrm": {"CPI" ₹, "ECPM" $, "ROAS"}, "ep"} — r0 = its
                           AdMob-matched install-day revenue at age 0 (USD; the cohort cube's country share of the app's
                           c_r0: cty_d0, GA4_CUBE on only), nrm = the Chart tab's country normal per day
  dashboard["cpi"]        the pointer: per app the default view (Last 14 days ending t: status, since, normal, money
                           lost), counts, not linked spend (per day: the page sums the period picked), alerts (sent once:
                           data/cpi/state.json) and closed.
  Units: CPI ₹ per install (as billed), eCPM $ per 1000, ROAS a ratio; money ₹ as billed and $ at each day's own rate.
  Money lost = Σ (cost − D0 value ÷ the frozen normal B) over the days of a ROAS alarm (measured inputs, the formula
  labelled ≈ on the page); a CPI / eCPM / GAP "since" sum is never a loss.

  Levels (engine LEVELS): every app file gets "lv" {fam: level rows newest first, each the exact value of named days
  with their sums (the page recomputes it from "d" and shows ✓), how it formed, when; the alarms' frozen baselines too},
  "lp" (open alarms the owner may accept) and "la" (the owner's actions and what the build did with them). The owner's
  actions come from config/cpi_levels.json (written only by the Worker's /api/levels/act, append-only; absent = the
  automatic rule only); the history is data/cpi/levels.json (this build's ledger: ids and first-seen kept across builds,
  restated values recorded, a level no longer produced kept as gone). A failure there prints "cpi levels skipped:
  <ErrorType>" and costs the levels only; a bad action prints "cpi level action skipped: <Reason>" and costs itself.
  One app whose history cannot be merged costs that app only; a level worth 0 is never shipped or pinned (ZeroLevel); a
  history row that cannot be read is dropped and counted (BadRow); a history FILE that cannot be read is kept as it
  is and ships no "lv" — the owner's set / accept / auto / undo still apply (rollback / reject: NoLedger).

  The level agent (engine.level_agent, P_PROD levels.agent mode "on"; the owner does not tap): every proposal, every
  engine settle of CPI / GAP and the engine's settle of any alarm it answered already is answered from the data as
  known on its day (accept / keep / wait, frozen in the history's "agent" block, asked again on the weekly phase);
  keep / wait leave the alarm open with the cause written,
  a settle kept or waiting is blocked (agent_veto: the alarm goes on from its own change start, its old notices
  seeded), a money level is never lowered, an accept of a proposal applies only after a clean 28-day trial, and every
  acceptance is watched 84 days (back at the old level → reverted). It ships the app file's "ag" rows, each
  proposal's answer, the level rows' marks, the list row's tag and the scoreboard dashboard["cpi"]["agent"]. Any
  failure prints "cpi agent skipped: <ErrorType>" (no history file: NoLedger; past its time budget: AgentTimeout,
  the answers so far kept) and ships the automatic-only result; "cpi agent decision skipped: ThinLevel" costs one
  acceptance this build, "cpi agent backtest skipped: <ErrorType>" only the scoreboard's backtest line.

run(dashboard, data_dir, out_dir, s) → the _headers no-store paths (["/cpi*"], ONE splat rule) or [] (no Google Ads
data: the files removed, no pointer). off(out_dir): the switch (CPI_TAB=false). Failure-isolated; ONE counts-only line.
mark_notified_cpi: send_alerts' ledger (each notice ONCE).
"""
import copy
import gzip
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import zlib
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .db import write_json_gz_stable
from .engine import cpi_alarm as CA
from .engine import level_agent as LA
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
SCALE = {"CPI": 100, "ECPM": 10000, "ROAS_G": 10000, "GAP": 100}
ROWS = ("sp_inr", "sp_usd", "inst", "d0_inr", "rev", "imp", "dau", "fs_rev", "fs_imp", "fs_u", "rt_rev", "rt_imp",
        "rt_u", "c_n", "c_sp", "c_r0", "c_r1", "c_r7")
ENG = ("sp_usd", "sp_inr", "inst", "d0_inr", "rev", "imp", "dau", "c_n", "c_sp", "c_r0", "c_r1", "c_r7")
INT_ROWS = ("imp", "dau", "fs_imp", "fs_u", "rt_imp", "rt_u", "c_n")
ST_ORDER = {"alarm": 0, "watch": 1, "fixed": 2, "ok": 3, "new": 4, "paused": 5}
LV_FILE = "levels.json"   # data/cpi/levels.json: the level history (this build writes it)
LV_V = 1
LV_RULE = "L1"
LV_LOG_MAX = 5000
RESTATED_MAX = 10         # a level row keeps its last 10 restated values (the log has its own cap)
ACT_FILE = "cpi_levels.json"   # config/cpi_levels.json: the owner's level actions (the Worker writes it)
ACT_RE = re.compile(r"^a-[0-9a-f]{12}$")
LEVEL_RE = re.compile(r"^L-[0-9a-f]{10}$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ACTS = ("set", "rollback", "reject", "accept", "auto", "undo")
PIN_SRC = {"set": "manual", "rollback": "rollback", "accept": "accepted_owner"}
SET_DAYS = (7, 120)       # a level set from days: 7 … 120 named days
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
    except (OSError, ValueError, EOFError, zlib.error):          # a damaged .gz costs only that file
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


def _spend(D, cache, sid, ok_till, R, dated, d0_open=None, d0_wait=False):
    """One store's Google Ads days → sp_inr (cost as billed), sp_usd (the page's $ view: by_app.daily_dated, else at
    each day's own rate), inst (biddable installs), d0_inr (Google's D0 value). 0 = no spend; after the last good fetch
    every day is null (never 0). D0 is final per store: its days still open (by_app d0_open) are null, and a store
    whose D0 waits for an account that cannot answer (d0_wait) is null after its own last good D0 day."""
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
    for d in d0_open or ():
        i = D.ix.get(str(d)[:10])
        if i is not None:
            s["d0_inr"][i] = None
    if d0_wait:
        known = (cache.get("convval_day1") or {}).get(sid) or {}
        good = [D.ix[d] for d in known if d in D.ix and s["d0_inr"][D.ix[d]] is not None]
        for i in range(max(good, default=-1) + 1, D.n):
            s["d0_inr"][i] = None
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
    notes["roi_rows"] = 0
    if isinstance(r, dict):
        notes["roi_rows"] = len(r.get("rows") or [])
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


def _unknown_outside(arr, D, first, till):
    """A store's own series: a day before its first day or after its till was never read → null (unknown), never 0."""
    if first:
        for i in range(0, min(D.n, max(0, (_d(first) - D.d0).days))):
            arr[i] = None
    if till:
        for i in range(max(0, (_d(till) - D.d0).days + 1), D.n):
            arr[i] = None


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
    first = st.get("first")
    for c in out.values():
        for arr in c["s"].values():
            _unknown_outside(arr, D, first, till)
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
                    if c["dl"][i] is not None:
                        c["dl"][i] += v[1]
                else:
                    c["dl"][i] = None                      # an unknown install count stays unknown (never 0 installs)
    till = st.get("till")
    out_till[0] = till
    first = st.get("first")
    for g in out.values():
        for c in g.values():
            for arr in c.values():
                _unknown_outside(arr, D, first, till)
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


def _cube_d0(D, data_dir, aid, lo):
    """The cohort cube's install-day revenue at age 0 per country (fetch.ga4_cube "e": {cc: {X: [u0, r0, …]}}, X's own
    month file, a hot day's record while it is not folded) → ({cc: {i: micros}}, {i: the day carried "(other)"
    loss}) on D's index from lo on; i is in the second map only for an install day the cube holds (folded or hot) —
    every other day is unknown. None: no cube for the app."""
    from .fetch import ga4_cube as gcu
    h = gcu.load_head(data_dir, aid)
    if not h:
        return None
    m0 = _iso(D.d0, lo)[:7]
    r0, known = {}, {}

    def take(days, e, M=None):
        for X, led in days.items():
            i = D.ix.get(X)
            if i is not None and i >= lo and (M is None or X[:7] == M):
                known[i] = bool(isinstance(led, dict) and (led.get("loss") or 0) > 0)
        for cc, xs in (e or {}).items():
            for X, arr in (xs or {}).items():
                i = D.ix.get(X)
                if i is None or i < lo or i not in known or (M is not None and X[:7] != M):
                    continue                              # (age 0 of X is in X's own month only)
                v = arr[1] if isinstance(arr, list) and len(arr) > 1 else 0
                if v:
                    g = r0.setdefault(cc, {})
                    g[i] = g.get(i, 0) + int(v)
    for M, f in gcu.months(data_dir, aid, h.get("stream_id")):
        if m0 <= M <= D.t.isoformat()[:7]:
            take(f.get("days") or {}, f.get("e"), M)
    for X, rec in sorted((h.get("d") or {}).items()):
        i = D.ix.get(X)
        if isinstance(rec, dict) and i is not None and i not in known:
            take({X: rec}, {cc: {X: (xs or {}).get(X)} for cc, xs in (rec.get("e") or {}).items()
                            if (xs or {}).get(X)})
    return r0, known


def cty_d0(D, s, cube, ccs):
    """Each country's AdMob-matched install-day revenue at age 0 (USD per install day X): the cube's GA4 r0 of (cc, X)
    × k_X, k_X = the app's AdMob-matched c_r0(X) ÷ Σ every cube country's r0(X) — so the countries ("(not set)" and the
    ones not shipped included) add up to the app's c_r0 on every day. Null where c_r0 is not matured, the cube does not
    hold X, or the cube has no revenue on X while AdMob has (nothing to split it by). → ({cc: [USD|None]}, notes)."""
    r0, known = cube
    tot = {}
    for g in r0.values():
        for i, v in g.items():
            tot[i] = tot.get(i, 0) + v
    out = {cc: D.nones() for cc in ccs}
    n_loss = 0
    first = None
    for i in sorted(known):
        a = s["c_r0"][i]
        if a is None:
            continue
        g = tot.get(i, 0)
        if g <= 0 and a:
            continue
        k = a / (g / 1e6) if g > 0 else 0.0
        first = i if first is None else first
        n_loss += 1 if known[i] else 0
        for cc in ccs:
            out[cc][i] = (r0.get(cc) or {}).get(i, 0) / 1e6 * k
    return out, {"from": _iso(D.d0, first) if first is not None else None, "loss_days": n_loss}


def roas_h(num, den, n_win=11, need=4):
    """The healthy rule of the engine for a ratio the engine does not replay (a country's AdMob-matched D0 ROAS): per day
    d the median of the 14-day windows ending d−14, d−21 … d−84 (Σnum ÷ Σden, every day of the window known, spend ≥
    the engine's $10 a day), ≥ 4 of them; no span to leave out (a country has no D0 ROAS alarm)."""
    n = len(den)
    V = [None] * n
    pn, pd, pk = [0.0], [0.0], [0]
    for i in range(n):
        ok = num[i] is not None and den[i] is not None
        pn.append(pn[-1] + (num[i] if ok else 0.0))
        pd.append(pd[-1] + (den[i] if ok else 0.0))
        pk.append(pk[-1] + (1 if ok else 0))
    gate = CA.GATE["min_sp_day"] * 14
    for b in range(13, n):
        if pk[b + 1] - pk[b - 13] == 14:
            sd = pd[b + 1] - pd[b - 13]
            if sd >= gate:
                V[b] = (pn[b + 1] - pn[b - 13]) / sd
    H = [None] * n
    for d in range(n):
        vals = []
        for j in range(n_win):
            b = d - 14 - 7 * j
            if b < 13:
                break
            if V[b] is not None:
                vals.append(V[b])
        if len(vals) >= need:
            vals.sort()
            m = len(vals)
            H[d] = vals[m // 2] if m % 2 else 0.5 * (vals[m // 2 - 1] + vals[m // 2])
    return H


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
        sp = _spend(D, cache, sid, ok_till, R, e.get("daily_dated"), e.get("d0_open"), e.get("d0_wait"))
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
        if sel and (s or {}).get("ga4_cube"):      # GA4_CUBE off: the store unread (the countries without D0 ROAS)
            try:                                 # a cube that cannot be read costs the countries' D0 ROAS only
                lo = _first_spend(a["s"]["sp_usd"])
                cube = _cube_d0(D, data_dir, a["app_id"], max(0, (lo or 0) - FILE_LEAD))
                if cube is not None:
                    r0, a["notes"]["cty_r0"] = cty_d0(D, a["s"], cube, sorted(sel))
                    for cc, c in sel.items():
                        c["r0"] = r0[cc]
            except Exception as e:
                print("cpi country d0 skipped: %s" % type(e).__name__, file=sys.stderr)
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
    extra["geo"], extra["cd"] = geo, cd                  # (the level agent's candidate countries; levels_run drops them)
    extra["names"] = {a["app_id"]: a["name"] for a in apps}
    return D, apps, camps, ctys, extra


# ── the default view and money ──────────────────────────────────────────────────────────────────────────────────────

def _span_end(ep, t):
    return ep["closed"] or t


def _overlaps(ep, a, b, t):
    return ep["c"] <= b and _span_end(ep, t) >= a


UP_BAD = frozenset(("CPI", "GAP"))      # families where higher is worse (the rest: lower is worse)
PEAK = 1.25                              # a baseline over 25 % better than H was a peak (the engine's band)


def _h_before(h, D0, day):
    """H on the day before `day`, else the last known H before it (None: none known)."""
    h = h or []
    for k in range(min((_d(day) - D0).days - 1, len(h) - 1), -1, -1):
        if h[k] is not None:
            return h[k]
    return None


def base_of(ep, healthy, D0):
    """The baseline an open episode is shown against (the row's normal and its money): its frozen B — unless B was more
    than 25 % better than the healthy level before the change (the 14 days before it were a peak), then that H."""
    B = ep["base"]
    H = _h_before((healthy or {}).get(ep["fam"]), D0, ep["c"]) if ep.get("c") else None
    if B and H and (B * PEAK < H if ep["fam"] in UP_BAD else B > H * PEAK):
        return H
    return B


def normal_at(fam, eps, healthy, D0, a, b):
    """SPEC §1.2: the baseline (base_of) of an app episode of `fam` open at b (open until its close, whatever the close
    reason — settled too, as the engine's own normal), else H on the day before a; H not known there (a period that
    starts before the app's healthy level exists) → the first known H inside [a, b]."""
    for ep in eps:
        if ep["fam"] == fam and ep["opened"] <= b and (ep["closed"] is None or ep["closed"] > b):
            return base_of(ep, healthy, D0)
    h = healthy.get(fam) or []
    i = (_d(a) - D0).days - 1
    if 0 <= i < len(h) and h[i] is not None:
        return h[i]
    for k in range(max(0, i + 1), min((_d(b) - D0).days, len(h) - 1) + 1):
        if h[k] is not None:
            return h[k]
    return None


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


def money_lost(eps, s, R, D0, a, b, t, healthy=None, e0=None):
    """SPEC §1.2: Σ (cost − D0 value ÷ B) over the days of [a, b] inside the app's ROAS_G episodes (₹ as billed, $ at
    each day's own rate) — the one money number of the list, the summary and the alerts. The AdMob install-day version
    (ROAS_C0) is only beside it in the details' Loss math. → {"inr", "usd", "from": the earliest c, "sc": the same sum
    from c to b, "fam"} or None. The baseline is base_of's (healthy / e0: the app's H arrays and their index 0)."""
    rate = day_rate(s, R)
    hit = [ep for ep in eps if ep["fam"] == "ROAS_G" and ep["base"] and (ep.get("opened") or ep["c"]) <= b
           and _overlaps(ep, a, b, t)]
    if not hit:
        return None
    per = [0.0, 0.0]
    since = [0.0, 0.0]
    c0 = min(ep["c"] for ep in hit)
    for ep in hit:
        B = base_of(ep, healthy, e0) if healthy is not None and e0 is not None else ep["base"]
        for lo, acc in ((max(a, ep["c"]), per), (ep["c"], since)):
            hi = min(b, _span_end(ep, t))
            i0, i1 = (_d(lo) - D0).days, (_d(hi) - D0).days
            for i in range(max(0, i0), i1 + 1):
                sp, v, su = s["sp_inr"][i], s["d0_inr"][i], s["sp_usd"][i]
                if sp is None or v is None:
                    continue
                acc[0] += sp - v / B
                acc[1] += (su or 0.0) - v * rate[i] / B
    return {"inr": _r(per[0]), "usd": _r(per[1]), "from": c0, "sc": {"inr": _r(since[0]), "usd": _r(since[1])},
            "fam": "ROAS_G"}


def status_of(eps, s, nrm, D0, a, b, t):
    """SPEC §1.2 as shipped: of the app's episodes overlapping [a, b] and opened by b (a LINE never counts), one still
    open at b → alarm (ALERT) / watch (WATCH); else an ALERT one that closed by b → fixed (the problem was in the period
    and is over); else ok — new without a normal for CPI and ROAS, paused when b = t and no spend on t−2 … t.
    since = the earliest change start of that grade. → (status, since)."""
    seen = [ep for ep in eps if ep["tier"] in ("ALERT", "WATCH") and ep["opened"] <= b and _overlaps(ep, a, b, t)]
    for tier, st in (("ALERT", "alarm"), ("WATCH", "watch")):
        hit = [ep for ep in seen if ep["tier"] == tier and not (ep["closed"] and ep["closed"] <= b)]
        if hit:
            return st, min(ep["c"] for ep in hit)
    done = [ep for ep in seen if ep["tier"] == "ALERT"]
    if done:
        return "fixed", min(ep["c"] for ep in done)
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
    sg = sum(x for x, y in zip(s["sp_inr"][max(0, i0):i1 + 1], s["d0_inr"][max(0, i0):i1 + 1])
             if x and y is not None)                      # D0 ROAS: the days D0 is final (as the page's fsum)
    return {"CPI": sp / n if n else None, "ECPM": rv / im * 1000 if im else None, "ROAS_G": v / sg if sg else None,
            "sp_inr": sp, "sp_usd": tot("sp_usd")}


# ── the files ───────────────────────────────────────────────────────────────────────────────────────────────────────

def _ep_row(ep):
    """[fam, opener, tier, c, opened, closed, why, B, B shown] — B shown = base_of's (an app episode; else B)."""
    return [ep["fam"], ep["opener"], ep["tier"], ep["c"], ep["opened"], ep["closed"], ep["why"], _r6(ep["base"]),
            _r6(ep.get("base_show", ep["base"]))]


def _ep_full(ep):
    out = {k: ep[k] for k in ("kind", "id", "app", "fam", "opener", "tier", "c", "opened", "seen", "closed", "why",
                              "base_src", "confirm")}
    out.update(base=_r6(ep["base"]), base_show=_r6(ep.get("base_show", ep["base"])), thr_open=_r(ep["thr_open"], 4),
               max_worse=_r(ep["max_worse"], 4),
               esc=[list(x) for x in ep["esc"]], ctx=dict(ep.get("ctx") or {}),
               money=dict(ep["money"]) if ep.get("money") else None, stake=list(ep.get("stake") or []))
    if "bspan" in ep:
        out["bspan"] = list(ep["bspan"]) if ep["bspan"] else None
        out["suggest"] = list(ep["suggest"]) if ep.get("suggest") else None
    return out


def _cut(arr, lo, n_row):
    out = []
    for v in arr[lo:]:
        out.append(None if v is None else (int(round(v)) if n_row else _r(v, 2)))
    return out


def _shown(arr, fam, eps, hl, e0):
    """The engine's normal per day with a B that was a peak drawn at base_of's level on its days (the baseline every
    place shows)."""
    arr = list(arr or [])
    for ep in eps:
        if ep["fam"] != fam or not ep["base"]:
            continue
        v = base_of(ep, hl, e0)
        if v == ep["base"]:
            continue
        i0 = (_d(ep["opened"]) - e0).days
        i1 = (_d(ep["closed"]) - e0).days if ep["closed"] else len(arr)
        for i in range(max(0, i0), min(i1, len(arr))):
            arr[i] = v
    return arr


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
        hl = res["healthy"].get(key) or {}
        for fam in CA.OUT_FAMS:
            arr = _shown(e_d0.get(fam), fam, eps_by.get(key, []), hl, e0)
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
        row = {"cc": cc, "from": _iso(D.d0, f),
               "d": {"sp_inr": _cut(c["sp_inr"], f, False), "sp_usd": _cut(c["sp_usd"], f, False),
                     "dl": _cut(c["dl"], f, False), "rev": _cut(c["rev"], f, False),
                     "imp": _cut(c["imp"], f, True)},
               "ep": [_ep_row(ep) for ep in eps_by.get(("country", aid + "|" + cc), [])]}
        # the Chart tab's country view: its normal per day (CPI ₹ / eCPM $: the engine's — its own open episode's B
        # (base_of's: a B that was a peak gives way to H, as the app's), else its healthy level — for a replayed line the
        # resting level its alarms used (P_PROD levels), for a left-out line the median H; D0 ROAS (AdMob-matched):
        # the same healthy rule on its r0 ÷ $ cost) + its r0
        ek = ("country", aid + "|" + cc)
        en, e0 = (res.get("normal") or {}).get(ek) or {}, extra.get("cday0", {}).get(aid + "|" + cc)
        cn = {}
        if e0:
            off = (D.d0 + timedelta(days=f) - _d(e0)).days
            for fam, nd in (("CPI", 2), ("ECPM", 4)):
                arr = _shown(en.get(fam), fam, eps_by.get(ek, []), (res.get("healthy") or {}).get(ek) or {}, _d(e0))
                if arr and any(v is not None for v in arr):
                    vals = arr[off:] if off >= 0 else [None] * (-off) + arr
                    cn[fam] = [None if v is None else round(v, nd) for v in vals]
        if c.get("r0") is not None:
            row["d"]["r0"] = _cut(c["r0"], f, False)
            h = roas_h(c["r0"], c["sp_usd"])
            if any(v is not None for v in h[f:]):
                cn["ROAS"] = [None if v is None else round(v, 4) for v in h[f:]]
        if cn:
            row["nrm"] = cn
        ct.append(row)
    ct.sort(key=lambda x: (-sum(v for v in x["d"]["sp_inr"] if v), x["cc"]))
    n = a["notes"]
    notes = {"clock": extra["clock"].get(a["store"]), "ga4_till": n.get("ga4_till"), "ga4_tz": n.get("ga4_tz"),
             "nvr_till": n.get("nvr_till"), "ga4_sampled": None, "admob_cty_from": n.get("admob_cty_from"),
             "troas_from": extra.get("troas_from"), "spend_ok_till": extra.get("ok_till"),
             "geo_till": extra.get("geo_till"), "camp_till": extra.get("camp_till"),
             "src": SRC_NOTE, "ga4_sampled_note": "not in this build's GA4 site files",
             "cty_rule": "share>=%g all history or last 120 days, top %d" % (CTY_SHARE, CTY_MAX),
             "cty_r0": n.get("cty_r0")}
    body = {"v": V, "app_id": aid, "name": a["name"], "key": a["key"], "t": t.isoformat(),
            "day0": _iso(D.d0, lo), "d": d, "nrm": nrm, "camps": cl, "ctys": ct, "src": [],
            "ep": [_ep_full(ep) for ep in eps_by.get(key, [])], "notes": notes}
    lvl = extra.get("lv")
    if lvl is not None:                                  # the levels part ran (else: the automatic file as before)
        ag = _ag_part(lvl)
        if lvl["ledger"] is not None:                    # (None: the history file could not be read: none shipped)
            try:
                body["lv"] = ship_levels(lvl["ledger"], aid, agent_on=True) if ag is not None else \
                    ship_levels(lvl["ledger"], aid)
            except Exception as e:                       # a row nobody foresaw costs this app's history block only
                print("cpi levels skipped: %s" % type(e).__name__, file=sys.stderr)
        body["lp"] = lvl["props"].get(aid, [])
        body["la"] = lvl["la"].get(aid, [])
        if ag is not None:                               # the agent part ran: its rows and each proposal's answer
            rows = [{k: v for k, v in x.items() if k != "_last"}
                    for x in (ag.ship_data.get(aid) or {}).get("rows") or []]
            body["ag"] = {"rows": rows}
            lp = []
            for p in body["lp"]:
                x = next((x for x in rows if x["fam"] == p["fam"] and _near(x["ep"]["opened"], p["opened"])), None)
                lp.append(dict(p, ag={k: x[k] for k in ("id", "st", "short", "cause", "next")} if x else None))
            body["lp"] = lp
    return body


def _ag_part(lvl):
    """The agent part of this build when it ran and finished (the ship data is ready), else None."""
    a = (lvl or {}).get("agent")
    return a["ag"] if (a and a.get("ran") and getattr(a.get("ag"), "ship_data", None) is not None) else None


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
        for ep in eps:                                   # the baseline every place shows (row, money, files, alerts)
            ep["base_show"] = base_of(ep, hl, e0)
            if ep["fam"] == "ROAS_G" and ep.get("money") and ep["base_show"] != ep["base"]:
                m = money_lost([ep], a["s"], extra["R"], D.d0, ep["c"], ep["closed"] or ts, ts, hl, e0)
                if m:
                    ep["money"] = dict(ep["money"], since_c_inr=m["inr"], since_c_usd=m["usd"])
        nrm = {f: normal_at(f, eps, hl, e0, a_iso, b_iso) for f in ("CPI", "ECPM", "ROAS_G", "GAP")}
        st, since = status_of(eps, a["s"], nrm, D.d0, a_iso, b_iso, ts)
        to = None
        if st == "fixed":                                  # the closed alarm's last day, for its span on the page
            to = max((ep["closed"] for ep in eps if ep["tier"] == "ALERT" and ep["c"] == since and ep["closed"]),
                     default=None)
        lost = money_lost(eps, a["s"], extra["R"], D.d0, a_iso, b_iso, ts, hl, e0)
        w = window(a["s"], D.d0, a_iso, b_iso)
        body = _app_file(a, D, a["lo"], res, camps, ctys, eps_by, extra, t)
        raw = _raw(body)
        if not _fits(raw):
            big += 1
            continue
        if w["sp_inr"] > 0:                              # an app whose file is not shipped is not counted
            counts[st] += 1
        fn = PREFIX + a["key"] + ".json.gz"
        files[fn] = body
        ptr_apps[aid] = {"name": a["name"], "key": a["key"], "file": fn, "v": hashlib.sha1(raw).hexdigest()[:12],
                         "st": st, "since": since, "to": to,
                         "open": [[ep["fam"], ep["opener"], ep["tier"], ep["c"], ep["opened"], _r6(ep["base"])]
                                  for ep in eps if ep["closed"] is None],
                         "nrm": {f: _r6(v) for f, v in nrm.items()},
                         "lost": ({k: lost[k] for k in ("inr", "usd", "from", "sc")} if lost else None)}
        if extra.get("lv") is not None:
            ptr_apps[aid]["lp"] = len(extra["lv"]["props"].get(aid) or [])
            ag = _ag_part(extra["lv"])
            tag = (ag.ship_data.get(aid) or {}).get("tag") if ag is not None else None
            if tag:
                ptr_apps[aid]["ag"] = tag
        off = (D.d0 + timedelta(days=g0) - e0).days
        h = {}
        for fam in ("CPI", "ECPM", "ROAS_G", "GAP"):
            arr = hl.get(fam) or []
            vals = arr[off:] if off >= 0 else [None] * (-off) + list(arr)
            h[fam] = [None if v is None else int(round(v * SCALE[fam])) for v in vals]
        all_h[aid] = {"h": h, "ep": [_ep_row(ep) for ep in eps]}
        a["view"] = {"st": st, "since": since, "nrm": nrm, "lost": lost, "w": w, "eps": eps}
    allb = {"v": V, "t": ts, "day0": _iso(D.d0, g0), "apps": all_h}
    unl = _unlinked(D, extra)
    ptr = {"v": V, "t": ts, "at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "day0": _iso(D.d0, g0), "file": FILE, "apps": ptr_apps, "counts": counts, "unlinked": unl}
    if extra.get("lv") is not None:
        ptr["la"] = extra["lv"]["seen"]                  # the newest owner action this build has read (page: pending)
        ag = _ag_part(extra["lv"])
        if ag is not None:
            ptr["agent"] = copy.deepcopy(ag.board)       # the agent's scoreboard
    return ptr, allb, files, big


def _unlinked(D, extra):
    """Google Ads spend per day on store ids with no row on this screen (not linked to a dashboard app, or the app is
    not selected), so the page sums it for the period picked: {"d0": the first day with such spend, "inr": [₹ as billed
    per day … t], "usd": [$ at each day's own rate], "n": the store ids with spend, "runs": per store id its runs of days
    with spend [first, last] as indexes into the arrays} — the page counts the store ids with spend inside its period."""
    cache, R = extra["cache"], extra["R"]
    linked = set(extra["store_app"])
    inr, usd = D.zeros(), D.zeros()
    ids = []
    for sid, dd in sorted((cache.get("daily") or {}).items()):
        if sid in linked:
            continue
        hit = []
        for d, v in (dd or {}).items():
            i = D.ix.get(d)
            if i is not None and v:
                amt = v / 1e6
                inr[i] += amt
                usd[i] += amt * R[i]
                hit.append(i)
        if hit:
            ids.append(sorted(hit))
    f = next((i for i, v in enumerate(inr) if v), None)
    if f is None:
        return {"d0": D.t.isoformat(), "inr": [], "usd": [], "n": 0, "runs": []}
    runs = []
    for hit in ids:
        r = []
        for i in hit:
            if r and i == r[-1][1] + 1:
                r[-1][1] = i
            else:
                r.append([i, i])
        runs.append([[a - f, b - f] for a, b in r])
    return {"d0": _iso(D.d0, f), "inr": [_r(x) for x in inr[f:]], "usd": [_r(x) for x in usd[f:]], "n": len(ids),
            "runs": runs}


# ── levels: the owner's actions, the history ledger (engine LEVELS) ───────────────────────────────────────────────────

class LevelMismatch(Exception):
    """A level is not the exact value of its named days (never shipped)."""


def levels_path(data_dir):
    return os.path.join(data_dir, STATE_DIR, LV_FILE)


def actions_path(data_dir):
    return os.path.join(os.path.dirname(os.path.abspath(data_dir)), "config", ACT_FILE)


def load_actions(data_dir):
    """config/cpi_levels.json → the owner's actions ([] when there is no file: the automatic rule only). A broken file
    raises (the caller prints the skipped line; nothing of it applies)."""
    path = actions_path(data_dir)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict) or raw.get("v") != 1 or not isinstance(raw.get("actions"), list):
        raise ValueError("cpi_levels")
    return [a for a in raw["actions"] if isinstance(a, dict)]


def _new_ledger():
    return {"v": LV_V, "rule": LV_RULE, "apps": {}, "proposals": {}, "log": []}


def _real(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float("inf")


def _row_ok(r):
    """A saved level row this build can read: an object with the four keys later steps index (id, src, from, v)."""
    return (isinstance(r, dict) and isinstance(r.get("id"), str) and bool(r["id"]) and isinstance(r.get("src"), str)
            and _is_day(r.get("from")) and _real(r.get("v")))


def load_ledger(data_dir):
    """data/cpi/levels.json → the level history (a fresh one when there is none). A damaged file raises: it is never
    overwritten by a build that could not read it. A row that cannot be read (not an object, or missing its id, src,
    from or v) is dropped and counted — one "cpi levels skipped: BadRow (<n> dropped)" line — so one bad row costs
    itself, never the tab."""
    path = levels_path(data_dir)
    led = _new_ledger()
    if not os.path.exists(path):
        return led
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict) or raw.get("v") != LV_V or not isinstance(raw.get("apps"), dict):
        raise ValueError("levels")
    led.update({k: raw[k] for k in ("apps", "proposals", "log", "rule") if k in raw})
    if "agent" in raw:
        led["agent"] = raw["agent"]                      # the level agent's block: validated by the agent, not here
    apps, bad = {}, 0
    for aid, fams in led["apps"].items():
        if not isinstance(fams, dict):
            bad += 1
            continue
        keep = {}
        for fam, lst in fams.items():
            if not isinstance(lst, list):
                bad += 1
                continue
            rows = [r for r in lst if _row_ok(r)]
            bad += len(lst) - len(rows)
            if rows:
                keep[fam] = rows
        apps[aid] = keep
    led["apps"] = apps
    for k, kind in (("proposals", dict), ("log", list)):
        if not isinstance(led[k], kind):
            led[k] = kind()
    if bad:
        print("cpi levels skipped: BadRow (%d dropped)" % bad, file=sys.stderr)
    return led


def save_ledger(data_dir, led):
    """Sorted JSON, written only when it changed. → True when written."""
    path = levels_path(data_dir)
    text = json.dumps(led, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
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


def _is_day(x):
    if not isinstance(x, str) or not DAY_RE.match(x):
        return False
    try:
        date.fromisoformat(x)
        return True
    except ValueError:
        return False


def _days_ok(days, ent, ts):
    """[first, last] real days, SET_DAYS long, inside the entity's series and not after the data day."""
    if not (isinstance(days, list) and len(days) == 2 and all(_is_day(x) for x in days)):
        return False
    a, b = days
    n = (_d(b) - _d(a)).days + 1
    return SET_DAYS[0] <= n <= SET_DAYS[1] and a >= ent.day0 and b <= ts


def _measured(ent, fam, days):
    m = CA.measure(ent, CA.P_PROD, fam, days[0], days[1])
    if m is None:
        return None
    m["sums"] = {k: _r6(v) for k, v in m["sums"].items()}
    return m


def resolve_actions(acts, ents, led, ts):
    """The owner's actions → (owner primitives for the engine {(app id, fam): [...]}, {app id: [action as listed on the
    page, with "st" applied / waiting / undone / bad and "why"]}, {level id: the reject's at}, the newest action's at).
    Undone actions are dropped; every other action is checked again here (the Worker checked it once) and one that
    cannot apply is listed bad — the rest still apply (a hand-edited one with a list / object where a text belongs is
    bad like any other). ents: {app id: engine entity}. led: the saved history, or None when it could not be read — a
    rollback / reject names a saved level, so those two are bad (NoLedger); every other action needs no history."""
    rows = None
    if led is not None:
        rows = {}
        for aid, fams in (led.get("apps") or {}).items():
            for fam, lst in (fams or {}).items():
                for r in lst or []:
                    if isinstance(r, dict):
                        rows[r.get("id")] = (aid, fam, r)
    by_id = {a["id"]: a for a in acts if isinstance(a.get("id"), str) and ACT_RE.match(a["id"])}
    undone = {a["ref"] for a in acts if a.get("act") == "undo" and isinstance(a.get("ref"), str)
              and a["ref"] in by_id and by_id[a["ref"]].get("act") != "undo"}
    owner, la, rej = {}, {}, {}
    seen = None
    for a in sorted(acts, key=lambda x: (str(x.get("at")), str(x.get("id")))):
        if isinstance(a.get("at"), str) and (seen is None or a["at"] > seen):
            seen = a["at"]
        try:
            why, prim = _resolve_one(a, ents, rows, by_id, undone, ts)
        except Exception:                                # an action nobody foresaw costs only itself
            why, prim = "BadAction", None
        app = a.get("app")
        if a.get("act") == "undo" and isinstance(a.get("ref"), str) and a["ref"] in by_id:
            app = by_id[a["ref"]].get("app")
        item = {k: a[k] for k in ("id", "at", "act", "fam", "from", "days", "value", "level", "ref", "note")
                if a.get(k) is not None}
        if isinstance(a.get("proposal"), dict):
            item["proposal"] = {k: a["proposal"].get(k) for k in ("day", "days")}
        if why:
            item.update(st="bad", why=why)
            print("cpi level action skipped: %s" % why, file=sys.stderr)
        elif isinstance(a.get("id"), str) and a["id"] in undone:
            item["st"] = "undone"
        else:
            item["st"] = "waiting" if (_is_day(a.get("from")) and a["from"] > ts) else "applied"
            if prim is not None:
                owner.setdefault((app, a["fam"]), []).append(prim)
                if prim["act"] == "veto":
                    rej[a["level"]] = a["at"]
        if isinstance(app, str):
            la.setdefault(app, []).append(item)
    for v in la.values():
        v.sort(key=lambda x: (str(x.get("at")), str(x.get("id"))), reverse=True)
    return owner, la, rej, seen


def _resolve_one(a, ents, rows, by_id, undone, ts):
    """One action → (the reason it cannot apply or None, the engine primitive or None). rows: the saved levels by id
    {id: (app id, fam, row)}, or None when the history could not be read (rollback / reject: NoLedger). A level worth
    0 or less is never pinned (ZeroLevel): it has no ratio to compare an alarm with."""
    act = a.get("act")
    if not (isinstance(a.get("id"), str) and ACT_RE.match(a["id"]) and isinstance(a.get("at"), str) and act in ACTS):
        return "BadAction", None
    if act == "undo":
        ref = a.get("ref")
        ok = isinstance(ref, str) and ref in by_id and by_id[ref].get("act") != "undo"
        return (None if ok else "UnknownRef"), None
    if a["id"] in undone:
        return None, None
    app = a.get("app")
    ent = ents.get(app) if isinstance(app, str) else None
    if ent is None:
        return "UnknownApp", None
    fam = a.get("fam")
    if not isinstance(fam, str) or fam not in CA.FAMS_BY_KIND["app"]:
        return "UnknownFam", None
    if act != "reject" and not _is_day(a.get("from")):
        return "BadDate", None
    if act == "auto":
        return None, {"act": "auto", "day": a["from"]}
    if act == "set":
        if a.get("days") is not None:
            if a.get("value") is not None or not _days_ok(a["days"], ent, ts):
                return "BadDays", None
            m = _measured(ent, fam, a["days"])
            if m is None:
                return "ThinDays", None
            if not m["v"] > 0:
                return "ZeroLevel", None
            return None, {"act": "pin", "day": a["from"], "value": m["v"], "src": PIN_SRC[act], "days": m["days"],
                          "id": a["id"]}
        v = a.get("value")
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not (0 < v < 1e9) or v != v:
            return "BadValue", None
        return None, {"act": "pin", "day": a["from"], "value": float(v), "src": PIN_SRC[act], "days": None,
                      "id": a["id"]}
    if act in ("rollback", "reject"):
        if rows is None:                                 # the history file could not be read: no saved level to name
            return "NoLedger", None
        lid = a.get("level")
        hit = rows.get(lid) if isinstance(lid, str) and LEVEL_RE.match(lid) else None
        if hit is None or hit[0] != app or hit[1] != fam:
            return "UnknownLevel", None
        r = hit[2]
        if act == "reject":
            ep = r.get("ep") if isinstance(r.get("ep"), dict) else {}
            if r.get("src") not in ("accepted", "accepted_agent") or not ep.get("opened"):
                return "NotAccepted", None
            return None, {"act": "veto", "ep_open": ep["opened"]}
        if r.get("days"):
            m = _measured(ent, fam, r["days"])
            if m is None:
                return "ThinDays", None
            if not m["v"] > 0:
                return "ZeroLevel", None
            return None, {"act": "pin", "day": a["from"], "value": m["v"], "src": PIN_SRC[act], "days": m["days"],
                          "id": a["id"]}
        if not (_real(r.get("v")) and r["v"] > 0):
            return "ZeroLevel", None
        return None, {"act": "pin", "day": a["from"], "value": float(r["v"]), "src": PIN_SRC[act], "days": None,
                      "id": a["id"]}
    p = a.get("proposal") if isinstance(a.get("proposal"), dict) else {}
    days = p.get("days")
    if not (isinstance(days, list) and len(days) == 2 and all(_is_day(x) for x in days) and days[0] <= days[1]
            and days[1] <= ts and days[0] >= ent.day0):
        return "BadDays", None
    m = _measured(ent, fam, days)
    if m is None:
        return "ThinDays", None
    if not m["v"] > 0:
        return "ZeroLevel", None
    return None, {"act": "pin", "day": a["from"], "value": m["v"], "src": PIN_SRC[act], "days": m["days"], "id": a["id"]}


def _exact(ent, fam, row):
    """The row's value from its named days → (the measured sums, n) — LevelMismatch when the replay's value, the
    measure and the ratio of the plain sums disagree, when the days cannot be measured, or when the level is worth 0
    or less (there is no ratio to check it by; it is never shipped)."""
    v = row["v"]
    if not (_real(v) and v > 0):
        raise LevelMismatch(fam)
    m = _measured(ent, fam, row["days"])
    if m is None or abs(m["v"] / v - 1.0) > 1e-9:
        raise LevelMismatch(fam)
    lv = CA.level_of(fam, m["sums"], m["n"], CA.P_PROD)
    if lv is None or abs(lv / v - 1.0) > 1e-6:                 # sums kept to 6 places
        raise LevelMismatch(fam)
    return m["sums"]


def _fresh(ent, key, res, eps):
    """This replay's level rows of one app: {fam: [row]} — the resting levels and every episode's frozen baseline."""
    out = {}
    for fam, lst in ((res.get("levels") or {}).get(key) or {}).items():
        for x in lst:
            row = {"from": x["day"], "v": x["v"], "days": x["days"], "src": x["src"], "ep": x.get("ep"),
                   "act": x.get("act")}
            row["sums"] = _exact(ent, fam, row) if x["days"] else None
            out.setdefault(fam, []).append(row)
    for ep in eps:
        if not ep.get("base"):
            continue
        row = {"from": ep["opened"], "to": ep["closed"], "v": ep["base"], "days": ep.get("bspan"), "src": "alarm",
               "ep": {"opened": ep["opened"], "c": ep["c"], "why": ep["why"], "opener": ep["opener"]}, "act": None}
        row["sums"] = _exact(ent, ep["fam"], row) if row["days"] else None
        out.setdefault(ep["fam"], []).append(row)
    return out


def _lv_id(aid, fam, src, frm, used):
    k = 0
    while True:
        x = "L-" + hashlib.sha1(("%s|%s|%s|%s|%d" % (aid, fam, src, frm, k)).encode("utf-8")).hexdigest()[:10]
        if x not in used:
            return x
        k += 1


def merge_ledger(old, res, ents, rej, now, agent=None):
    """The replay's levels merged into the saved history → (the new ledger, {app id: proposals}). A row matches a saved
    one of the same family and kind when its day moved ≤ MATCH_DAYS (restated data): it keeps its id and first-seen,
    a changed value is recorded under "restated" (the last RESTATED_MAX kept); a saved row no longer produced is kept
    as gone (or rejected: the owner's reject). An app whose levels are not exact, or whose merge fails for any other
    reason, keeps its saved history untouched (one skipped line) — the other apps still merge. The saved agent block
    is carried as it is; agent = the level agent's part when it ran: its marks go onto the rows it names (passed /
    agent / blocked / hold / reverted) and the rows the agent world no longer makes are added from it."""
    now_iso = gu._now_iso(now)
    led = {"v": LV_V, "rule": LV_RULE, "apps": copy.deepcopy(old.get("apps") or {}),
           "proposals": copy.deepcopy(old.get("proposals") or {}), "log": list(old.get("log") or [])}
    if "agent" in old:
        led["agent"] = copy.deepcopy(old["agent"])
    marks = (agent or {}).get("marks") or {}
    used = {r.get("id") for fams in led["apps"].values() for lst in fams.values() for r in lst}
    eps_by = {}
    for ep in res["episodes"]:
        if ep["kind"] == "app":
            eps_by.setdefault((ep["id"], ep["fam"]), []).append(ep)
    props = {}
    for key in sorted(res.get("levels") or {}):
        aid = key[1]
        ent = ents.get(aid)
        if ent is None:
            continue
        n_log, used0 = len(led["log"]), set(used)
        try:
            fresh = _fresh(ent, key, res, [ep for (i, _), lst in eps_by.items() if i == aid for ep in lst])
            if agent is not None:
                _ag_marks(ent, aid, fresh, marks)
            pl = []
            for p in (res.get("proposals") or {}).get(key) or []:
                row = {"v": p["v"], "days": p["days"]}
                pl.append({"fam": p["fam"], "opened": p["opened"], "day": p["day"], "why": p["why"], "v": p["v"],
                           "days": p["days"], "sums": _exact(ent, p["fam"], row), "old": p["old"], "gap": p["gap"]})
            saved = led["apps"].get(aid) or {}
            mine = {}
            for fam in sorted(set(fresh) | set(saved)):
                mine[fam] = _merge_fam(aid, fam, saved.get(fam) or [], fresh.get(fam) or [], rej, now_iso, used,
                                       led["log"], agent is not None)
        except Exception as e:                           # one app costs only itself (LevelMismatch, a zero, anything)
            print("cpi levels skipped: %s" % type(e).__name__, file=sys.stderr)
            del led["log"][n_log:]                       # … and leaves no half-merged trace behind
            used.intersection_update(used0)
            props[aid] = led["proposals"].get(aid) or []
            continue
        led["apps"][aid] = mine
        led["proposals"][aid] = pl
        props[aid] = pl
    led["log"] = led["log"][-LV_LOG_MAX:]
    return led, props


def _ag_marks(ent, aid, fresh, marks):
    """The agent's marks onto this replay's level rows (by src and episode), and the rows it keeps visible that the
    agent world no longer makes (a blocked / on-hold settle, a reverted acceptance) — each exact like any other."""
    for (a, fam), m in marks.items():
        if a != aid:
            continue
        lst = fresh.setdefault(fam, [])
        for src, opened, mark in m["tag"]:
            for row in lst:
                if row["src"] == src and (row.get("ep") or {}).get("opened") and _near(row["ep"]["opened"], opened):
                    row["ag"] = dict(mark)
                    break
        for x in m["extra"]:
            row = {k: x[k] for k in ("from", "v", "days", "src", "ep", "act")}
            row["sums"] = _exact(ent, fam, row) if row["days"] else None
            row["ag"] = dict(x["ag"])
            lst.append(row)
    for fam in [f for f, lst in fresh.items() if not lst]:
        del fresh[fam]


def _ag_mark(r, mark, log, now_iso, aid, fam):
    """A history row takes the agent's mark of this build (or loses an old one); blocked / hold / reverted are logged
    once per change."""
    old = (r.get("ag") or {}).get("st")
    if mark:
        r["ag"] = dict(mark)
    else:
        r.pop("ag", None)
    st = (mark or {}).get("st")
    if st in MARKED and st != old:
        log.append({"at": now_iso, "app": aid, "fam": fam, "id": r["id"], "what": st, "v_old": None, "v_new": r["v"]})


def _merge_fam(aid, fam, saved, fresh, rej, now_iso, used, log, agent_ran=False):
    out, taken = [], set()
    for row in sorted(fresh, key=lambda r: (r["from"], r["src"])):
        best = None
        for j, r in enumerate(saved):
            if j in taken or r.get("src") != row["src"]:
                continue
            gap = abs((_d(r["from"]) - _d(row["from"])).days)
            if gap <= MATCH_DAYS and (best is None or gap < best[0]):
                best = (gap, j)
        if best is not None:
            taken.add(best[1])
            r = dict(saved[best[1]])
            if r.get("v") and abs(row["v"] / r["v"] - 1.0) > 1e-9:
                r["restated"] = (list(r.get("restated") or []) + [{"at": now_iso, "v_old": r["v"], "v_new": row["v"]}]
                                 )[-RESTATED_MAX:]
                log.append({"at": now_iso, "app": aid, "fam": fam, "id": r["id"], "what": "restated", "v_old": r["v"],
                            "v_new": row["v"]})
            r.update({k: row.get(k) for k in ("from", "v", "days", "sums", "src", "ep", "act")})
            r["gone"] = None
            if agent_ran:
                _ag_mark(r, row.get("ag"), log, now_iso, aid, fam)
        else:
            r = dict(row, id=_lv_id(aid, fam, row["src"], row["from"], used), seen=now_iso, restated=[], gone=None)
            r.pop("ag", None)
            used.add(r["id"])
            log.append({"at": now_iso, "app": aid, "fam": fam, "id": r["id"], "what": "new", "v_old": None,
                        "v_new": row["v"]})
            if agent_ran:
                _ag_mark(r, row.get("ag"), log, now_iso, aid, fam)
        if row["src"] == "alarm":
            r["to"] = row.get("to")
        out.append(r)
    for j, r in enumerate(saved):
        if j in taken:
            continue
        r = dict(r)
        if agent_ran:
            r.pop("ag", None)                            # a mark the agent no longer gives (when it did not run: kept)
        if not r.get("gone") and r.get("id") not in rej:
            r["gone"] = now_iso
            log.append({"at": now_iso, "app": aid, "fam": fam, "id": r["id"], "what": "gone", "v_old": r.get("v"),
                        "v_new": None})
        out.append(r)
    for r in out:
        was = r.get("rejected")
        r["rejected"] = rej.get(r.get("id"))
        if r["rejected"] and not was:
            log.append({"at": now_iso, "app": aid, "fam": fam, "id": r["id"], "what": "rejected", "v_old": r.get("v"),
                        "v_new": None})
    live = sorted((r for r in out if r["src"] != "alarm" and not r.get("gone") and not r.get("rejected")
                   and not (agent_ran and (r.get("ag") or {}).get("st") in MARKED)), key=lambda r: r["from"])
    for i, r in enumerate(live):                         # a resting level holds until the next one forms
        r["to"] = (_d(live[i + 1]["from"]) - timedelta(days=1)).isoformat() if i + 1 < len(live) else None
    out.sort(key=lambda r: (r["from"], r["src"], r["id"]))
    for i, r in enumerate(out):
        r["n"] = i + 1
    return out


def ship_levels(led, aid, agent_on=False):
    """The app's level history as the page reads it: {fam: [row, newest first]} with a status word per row — now (the
    level in force: the open alarm's baseline, else the resting level), rest (the resting level while an alarm is
    open), earlier, rejected, gone; agent_on (the agent part ran): blocked / hold / reverted (rows the agent world
    no longer makes: never the level in force) and each row's "ag" mark."""
    out = {}

    def mk(r):
        return (r.get("ag") or {}).get("st") if agent_on else None
    for fam, lst in sorted(((led.get("apps") or {}).get(aid) or {}).items()):
        open_alarm = any(r["src"] == "alarm" and r.get("to") is None and not r.get("gone") for r in lst)
        live = [r for r in lst if r["src"] != "alarm" and not r.get("gone") and not r.get("rejected")
                and mk(r) not in MARKED]
        last = max(live, key=lambda r: r["from"]) if live else None
        rows = []
        for r in lst:
            if r.get("rejected"):
                st = "rejected"
            elif r.get("gone"):
                st = "gone"
            elif mk(r) in MARKED:
                st = mk(r)
            elif r["src"] == "alarm":
                st = "now" if r.get("to") is None else "earlier"
            elif r is last:
                st = "rest" if open_alarm else "now"
            else:
                st = "earlier"
            rs = r.get("restated") or []
            rows.append({"id": r["id"], "from": r["from"], "to": r.get("to"), "v": r["v"], "days": r.get("days"),
                         "sums": r.get("sums"), "src": r["src"], "ep": r.get("ep"), "act": r.get("act"), "st": st,
                         "seen": r.get("seen"), "rs": rs[-1] if rs else None, "gone": r.get("gone"),
                         "rejected": r.get("rejected")})
            if agent_on:
                m = r.get("ag")
                rows[-1]["ag"] = {k: m.get(k) for k in ("st", "dec", "short", "cause", "next")} if m else None
        rows.sort(key=lambda r: (r["from"], r["src"] != "alarm", r["id"]), reverse=True)
        out[fam] = rows
    return out


def levels_run(ents, data_dir, t, now, extra=None):
    """The replay with the owner's levels → (engine result, the levels part or None). Any failure of the levels part
    prints "cpi levels skipped: <ErrorType>" and gives the automatic replay (the tab stays). A history file that cannot
    be read is never overwritten and ships no history, but it does not stop the owner's levels: every action that
    needs no saved level (set, accept, auto, undo) is resolved against no history and still applies; a rollback /
    reject names a saved level and is listed bad (NoLedger). The part then has "ledger": None (nothing to save).
    With extra (the build's inputs) and P_PROD levels.agent mode "on", the level agent runs on the history (agent_run):
    the result is then the agent world; any failure prints "cpi agent skipped: <ErrorType>" (no history: NoLedger)
    and ships the replay without it, the saved agent block written back unchanged (a timeout: with its new asks)."""
    ts = t.isoformat()
    apps_e = {e.id: e for e in ents if e.kind == "app"}
    try:
        acts = load_actions(data_dir)
    except Exception as e:
        print("cpi levels skipped: %s" % type(e).__name__, file=sys.stderr)
        return CA.run(ents, CA.P_PROD, ts), None
    try:
        led = load_ledger(data_dir)
    except Exception as e:
        print("cpi levels skipped: %s" % type(e).__name__, file=sys.stderr)
        led = None
    try:
        owner, la, rej, seen = resolve_actions(acts, apps_e, led, ts)
    except Exception as e:
        print("cpi levels skipped: %s" % type(e).__name__, file=sys.stderr)
        return CA.run(ents, CA.P_PROD, ts), None
    try:
        res = CA.run(ents, CA.P_PROD, ts, owner=owner or None)
    except Exception as e:
        if not owner:
            raise
        print("cpi levels skipped: %s" % type(e).__name__, file=sys.stderr)
        return CA.run(ents, CA.P_PROD, ts), None
    res0, part = res, None
    if extra is not None and agent_cfg().get("mode") == "on":     # mode "off": no agent code runs at all
        if led is None:
            print("cpi agent skipped: NoLedger", file=sys.stderr)
        else:
            extra["bt"] = load_backtest(data_dir)
            try:
                res, part = agent_run(ents, res0, owner, la, led, t, now, extra)
            except AgentTimeout as e:
                print("cpi agent skipped: AgentTimeout", file=sys.stderr)
                res, part = res0, {"blk": e.blk, "ran": False}
            except Exception as e:
                print("cpi agent skipped: %s" % type(e).__name__, file=sys.stderr)
                res, part = res0, None
    if extra is not None:
        for k in ("geo", "cd", "names"):
            extra.pop(k, None)
    try:
        ran = part is not None and part.get("ran")
        base = led if led is not None else _new_ledger()
        new, props = merge_ledger(base, res, apps_e, rej, now, agent=part if ran else None)
        if ran:
            try:
                part["finish"](new)
            except Exception as e:                       # the agent's last step failed: the replay without it
                print("cpi agent skipped: %s" % type(e).__name__, file=sys.stderr)
                res, part = res0, None
                new, props = merge_ledger(base, res, apps_e, rej, now)
        elif part is not None and part.get("blk") is not None:
            new["agent"] = part["blk"]                   # a timeout: the asks made so far are kept
    except Exception as e:
        print("cpi levels skipped: %s" % type(e).__name__, file=sys.stderr)
        return res0, None
    return res, {"ledger": new if led is not None else None, "props": props, "la": la, "seen": seen,
                 "agent": part if (part is not None and part.get("ran")) else None}


# ── the level agent (engine.level_agent): the owner's questions answered without a tap ──────────────────────────────

AG_V = 1
AG_MAX_BYTES = 2000000    # the agent block of the history file: past this, the oldest asks lose their rule inputs
NET_FAMS = ("CPI", "ECPM", "GAP", "IPU", "SPEND")     # the engine's own settles the revert net watches
MARKED = ("blocked", "hold", "reverted")               # level rows the agent world no longer produces, kept visible
BT_FILE = "agent_backtest.json"                        # data/cpi/: the backtest numbers (private repo, read only)
BT_V = (1, 2)                                          # its settles: 1 the CPI / GAP ones, 2 every engine settle asked
_clock = time.monotonic                                # the agent step's budget clock (tests replace it)


class AgentTimeout(Exception):
    """The agent step ran past budget_s: the asks frozen so far are kept, nothing of this build is applied."""

    def __init__(self, blk=None):
        super().__init__("budget")
        self.blk = blk


class AgentMoneyError(Exception):
    """An agent acceptance on a money family (never made: the agent never lowers a money level)."""


def agent_cfg():
    return CA.P_PROD["levels"]["agent"]


def _ag_id(pre, key, used):
    k = 0
    while True:
        x = pre + "-" + hashlib.sha1(("%s|%d" % (key, k)).encode("utf-8")).hexdigest()[:10]
        if x not in used:
            return x
        k += 1


def _new_block(ts, now_iso, cfg):
    return {"v": AG_V, "rule": LA.RULE, "th": LA.th_sha(cfg), "first_t": ts, "seen": now_iso,
            "trial": {"st": "trial", "since": ts, "why": "start", "exit": None, "log": [[ts, "trial", "start"]]},
            "parity": {"checked": 0, "bad": 0, "last_bad": None},
            "vintage": {"done7": 0, "done28": 0, "flips": 0, "accept_flips": 0, "err_max": None, "err_f": None},
            "rows": [], "net": []}


def _check_block(b):
    """The saved agent block as this build can use it, else ValueError (the agent step is skipped, the block kept)."""
    bad = ValueError("agent")
    if not isinstance(b, dict) or b.get("v") != AG_V or b.get("rule") != LA.RULE or not _is_day(b.get("first_t")):
        raise bad
    for k, kind in (("rows", list), ("net", list), ("trial", dict), ("parity", dict), ("vintage", dict)):
        if not isinstance(b.get(k), kind):
            raise bad
    tr = b["trial"]
    if tr.get("st") not in ("trial", "live") or not _is_day(tr.get("since")) or not isinstance(tr.get("log"), list):
        raise bad
    for r in b["rows"]:
        if not (isinstance(r, dict) and isinstance(r.get("id"), str) and isinstance(r.get("app"), str)
                and r.get("fam") in CA.FAMILIES and r.get("why") in ("money", "open", "settle", "revert")
                and isinstance(r.get("ep"), dict) and _is_day(r["ep"].get("opened")) and _is_day(r["ep"].get("c"))
                and isinstance(r.get("asks"), list) and isinstance(r.get("applied"), dict)):
            raise bad
        for a in r["asks"]:
            if not (isinstance(a, dict) and _is_day(a.get("d")) and _is_day(a.get("t"))
                    and a.get("dec") in ("accept", "keep", "wait")):
                raise bad
    for x in b["net"]:
        if not (isinstance(x, dict) and isinstance(x.get("id"), str) and _is_day(x.get("acc"))
                and isinstance(x.get("app"), str) and isinstance(x.get("ep"), dict)):
            raise bad
    return b


def _pin_on(prims, d):
    """The owner's pin in force on day d (ISO) among one family's primitives, else None."""
    cur = None
    for a in sorted((a for a in prims or () if a.get("day")), key=lambda a: a["day"]):
        if a["day"] > d:
            break
        if a["act"] == "pin":
            cur = a
        elif a["act"] == "auto":
            cur = None
    return cur


def _near(a, b, k=MATCH_DAYS):
    return abs((_d(a) - _d(b)).days) <= k


def _cty_ents(aid, extra):
    """Every geo country of the app as an engine entity, built exactly as entities() builds a selected one (the
    agent's country tests read every candidate as of the ask day, not the file's top 12)."""
    D = extra["D"]
    cd = (extra.get("cd") or {}).get((extra.get("names") or {}).get(aid)) or {}
    out = []
    for cc, c in sorted(((extra.get("geo") or {}).get(aid) or {}).items()):
        lo = _lead(c["sp_usd"])
        if lo is None:
            continue
        s = {"sp_usd": c["sp_usd"], "sp_inr": c["sp_inr"], "inst": c["dl"]}
        rv, im = _cty_admob(D, cd.get(cc))
        if im and any(im):
            s["rev"], s["imp"] = rv, im
        out.append(_ent("country", aid + "|" + cc, aid, cc, D, s, lo))
    return out


def splice(res0, runs, ents):
    """A NEW engine result: res0 with the app entities of runs ({app id: that app's own replay}) replaced — its
    episodes (in ents order, each entity's own order kept) and its normal / healthy / state / levels / proposals.
    Countries and campaigns are untouched by app primitives; res0 is never modified."""
    by = {}
    for ep in res0["episodes"]:
        by.setdefault((ep["kind"], ep["id"]), []).append(ep)
    for aid, r in runs.items():
        by[("app", aid)] = [ep for ep in r["episodes"] if ep["kind"] == "app" and ep["id"] == aid]
    eps, done = [], set()
    for e in ents:
        k = (e.kind, e.id)
        if k not in done:
            done.add(k)
            eps.extend(by.get(k, []))
    out = {"episodes": eps}
    for key in ("normal", "healthy", "state", "levels", "proposals"):
        if key not in res0:
            continue
        d = dict(res0[key])
        for aid, r in runs.items():
            if ("app", aid) in (r.get(key) or {}):
                d[("app", aid)] = r[key][("app", aid)]
        out[key] = d
    return out


class _Agent:
    """One build's agent step (agent_run): the questions of the agent world, their frozen answers, the primitives
    they make, the revert net, the trial and the checks of every stored answer."""

    def __init__(self, ents, res0, owner, la, blk, t, now, extra, cfg):
        self.ents, self.res0, self.owner, self.la, self.blk, self.cfg = ents, res0, owner or {}, la or {}, blk, cfg
        self.t, self.ts, self.now_iso, self.extra = t, t.isoformat(), gu._now_iso(now), extra
        self.start = _clock()
        self.apps = {e.id: e for e in ents if e.kind == "app"}
        self.order = [e.id for e in ents if e.kind == "app"]
        self.pos = {a: i for i, a in enumerate(self.order)}
        self.camps = {}
        for e in ents:
            if e.kind == "camp":
                self.camps.setdefault(e.app, []).append(e)
        self._ctys, self._ser = {}, {}
        self.th = LA.th_sha(cfg)
        self.rows = blk["rows"]
        self.used = {r["id"] for r in self.rows} | {x["id"] for x in blk["net"]}
        self.n_asks, self.thin, self.restarted = 0, False, False
        self.prims, self.runs = {}, {}
        self.ship_data, self.board = None, None
        self.set_world(res0)

    def tick(self):
        if _clock() - self.start > self.cfg["budget_s"]:
            raise AgentTimeout()

    def ctys(self, aid):
        if aid not in self._ctys:
            self._ctys[aid] = _cty_ents(aid, self.extra)
        return self._ctys[aid]

    def others(self, aid):
        return [self.apps[x] for x in self.order if x != aid]

    def full_ser(self, aid):
        """The app's whole series to t (the revert checks and the verdicts read matured data)."""
        if aid not in self._ser:
            e = self.apps[aid]
            self._ser[aid] = CA._Ser(e, CA._ix(e.day0, self.ts) + 1, CA.P_PROD)
        return self._ser[aid]

    # ── the owner (D-i: the owner's action wins from its day; a held family is never asked) ──
    def pin(self, aid, fam, d):
        return _pin_on(self.owner.get((aid, fam)), d)

    def oveto(self, aid, fam, opened):
        return any(a.get("act") == "veto" and a.get("ep_open") and _near(a["ep_open"], opened)
                   for a in self.owner.get((aid, fam)) or ())

    def held(self, aid, fam):
        if self.pin(aid, fam, self.ts) is not None:
            return True
        if any(ep["closed"] is None and self.oveto(aid, fam, ep["opened"]) for ep in self.eps(aid, fam)):
            return True
        return any(p["fam"] == fam and p["why"] == "held"
                   for p in (self.world.get("proposals") or {}).get(("app", aid)) or [])

    def ovr(self, r):
        """The earliest owner action on the row's app × family after the row was first seen (an undone one is gone)."""
        hit = [x for x in self.la.get(r["app"]) or [] if x.get("fam") == r["fam"] and x.get("st") == "applied"
               and x.get("act") in ("set", "rollback", "reject", "accept") and str(x.get("at")) > r["seen"]]
        if not hit:
            return None
        x = min(hit, key=lambda z: (str(z["at"]), str(z.get("id"))))
        return {"id": x.get("id"), "at": x["at"], "act": x["act"], "from": x.get("from")}

    # ── the agent world ──
    def set_world(self, world):
        self.world = world
        self._by = {}
        for ep in world["episodes"]:
            if ep["kind"] == "app":
                self._by.setdefault(ep["id"], []).append(ep)

    def eps(self, aid, fam):
        return [ep for ep in self._by.get(aid, []) if ep["fam"] == fam]

    def match(self, aid, fam, opened):
        best = None
        for ep in self.eps(aid, fam):
            gap = abs((_d(ep["opened"]) - _d(opened)).days)
            if gap <= MATCH_DAYS and (best is None or gap < best[0]):
                best = (gap, ep)
        return best[1] if best else None

    def find(self, aid, fam, ep):
        """The decision row of this world episode: the nearest row (±7 days) whose own nearest episode it is."""
        cand = sorted(((abs((_d(r["ep"]["opened"]) - _d(ep["opened"])).days), i) for i, r in enumerate(self.rows)
                       if r["app"] == aid and r["fam"] == fam), key=lambda z: z)
        for gap, i in cand:
            if gap <= MATCH_DAYS and self.match(aid, fam, self.rows[i]["ep"]["opened"]) is ep:
                return self.rows[i]
        return None

    def derive_prims(self):
        """The rows → the engine primitives: agent_veto for a blocked / on-hold settle and every revert, agent for an
        applied accept that is not reverted (the owner's pin span or veto drops it: the owner wins)."""
        out = {}
        for r in self.rows:
            aid, fam, op = r["app"], r["fam"], r["ep"]["opened"]
            if aid not in self.apps:
                continue
            ap = r.get("applied") or {}
            lst = out.setdefault((aid, fam), [])
            if ap.get("veto") or r.get("rev"):
                lst.append({"act": "agent_veto", "ep_open": op, "id": r["id"]})
            acc = ap.get("accept")
            if not acc or r.get("rev"):
                continue
            if fam in CA.MONEY_FAMS:
                raise AgentMoneyError(fam)                 # the agent never lowers a money level
            if self.pin(aid, fam, acc["day"]) is not None or self.oveto(aid, fam, op):
                continue
            m = _measured(self.apps[aid], fam, acc["days"])
            if m is None or not m["v"] > 0:
                if not self.thin:
                    self.thin = True
                    print("cpi agent decision skipped: ThinLevel", file=sys.stderr)
                continue
            lst.append({"act": "agent", "day": acc["day"], "days": list(acc["days"]), "value": m["v"], "ep_open": op,
                        "id": r["id"]})
        return {k: v for k, v in out.items() if v}

    def owner_of(self, aid, prims):
        keys = sorted({k for k in self.owner if k[0] == aid} | {k for k in prims if k[0] == aid})
        return {k: list(self.owner.get(k) or []) + list(prims.get(k) or []) for k in keys}

    def update(self, prims):
        """Replay the apps whose primitives changed (each app alone: app primitives touch nothing else)."""
        ids = sorted({k[0] for k in set(prims) | set(self.prims) if prims.get(k) != self.prims.get(k)},
                     key=lambda a: self.pos.get(a, 10 ** 6))
        for aid in ids:
            self.tick()
            if any(k[0] == aid for k in prims):
                self.runs[aid] = CA.run([self.apps[aid]], CA.P_PROD, self.ts, owner=self.owner_of(aid, prims))
            else:
                self.runs.pop(aid, None)
        self.prims = prims
        if ids:
            self.set_world(splice(self.res0, self.runs, self.ents))
        return ids

    def sync(self):
        """Each row follows its episode in the agent world (opened / c); it ends when that episode closed or is gone —
        end = {t: the build day that first saw it, day: the episode's own close day (None when gone), why}."""
        for r in self.rows:
            if r["app"] not in self.apps:
                continue
            ep = self.match(r["app"], r["fam"], r["ep"]["opened"])
            if ep is None:
                end = {"t": self.ts, "day": None, "why": "gone"}
            else:
                r["ep"] = {"opened": ep["opened"], "c": ep["c"]}
                end = None if ep["closed"] is None else {"t": self.ts, "day": ep["closed"], "why": ep["why"]}
            old = r.get("end")
            if end is None or not (old and old.get("why") == end["why"]):
                r["end"] = end
            else:
                old["day"] = end["day"]                        # (also on a row saved before the day was kept)


    # ── questions and frozen answers (D-d: first day, then the weekly phase; a missed day asks on the next build) ──
    def due(self, r):
        return (not r.get("rev") and r.get("end") is None and r.get("next") is not None and r["next"] <= self.ts
                and (not r["asks"] or r["asks"][-1]["d"] < self.ts))

    def questions(self):
        """Due questions in the order they are answered: proposals as of t, the engine's settles in force as of their
        settle day (oldest first: every CPI / GAP settle, and a settle of any family whose alarm the agent answered
        already — an ECPM / IPU / SPEND settle nobody answered stands as today), then the blocked / on-hold settles
        asked again as of t. A held family is never asked: its due rows wait for the weekly phase after the hold
        ends."""
        q1, q2, q3 = [], [], []
        for aid in self.order:
            for p in (self.world.get("proposals") or {}).get(("app", aid)) or []:
                if p["why"] not in ("money", "open"):
                    continue
                ep = self.match(aid, p["fam"], p["opened"])
                if ep is None or ep["closed"] is not None:
                    continue
                r = self.find(aid, p["fam"], ep)
                if self.held(aid, p["fam"]):
                    if r is not None and self.due(r):
                        r["next"] = LA.next_phase(self.ts)
                    continue
                if r is None:
                    q1.append(("new", aid, p["fam"], ep, p, None))
                elif self.due(r):
                    q1.append(("row", aid, p["fam"], ep, p, r))
        fams = set(self.cfg["settle_fams"])
        for aid in self.order:
            lv = (self.world.get("levels") or {}).get(("app", aid)) or {}
            for ep in self._by.get(aid, []):
                if ep["why"] != "settled":
                    continue
                rows = lv.get(ep["fam"]) or []
                last = rows[-1] if rows else None
                if not last or last["src"] != "accepted" or (last.get("ep") or {}).get("opened") != ep["opened"]:
                    continue                                   # its level was replaced since: history, never asked
                r = self.find(aid, ep["fam"], ep)
                if ep["fam"] not in fams and (r is None or r["why"] not in ("money", "open")):
                    continue                                   # D-j: an ECPM / IPU / SPEND settle nobody answered
                if r is not None and (r.get("rev") or _settle_ask(r) is not None):
                    continue                                   # answered (or reverted: the owner's only)
                if self.held(aid, ep["fam"]):
                    continue
                q2.append(("settle", aid, ep["fam"], ep, last, r))
        q2.sort(key=lambda q: (q[3]["closed"], self.pos[q[1]], q[2]))
        asked = {q[5]["id"] for q in q1 if q[5] is not None}
        for r in self.rows:
            if r["id"] in asked or r["app"] not in self.apps or not self.due(r):
                continue
            if not r["applied"].get("veto") or r["applied"].get("accept"):
                continue
            ep = self.match(r["app"], r["fam"], r["ep"]["opened"])
            if ep is None or ep["closed"] is not None:
                continue
            if self.held(r["app"], r["fam"]):
                r["next"] = LA.next_phase(self.ts)
                continue
            q3.append(("row", r["app"], r["fam"], ep, None, r))
        q3.sort(key=lambda q: (q[5]["next"], self.pos[q[1]], q[2]))
        return q1 + q2 + q3

    def ask(self, q):
        """One frozen answer: the evidence as of its day, the market, the rule."""
        kind, aid, fam, ep, x, r = q
        sh = CA.FAMILIES[fam]["shift"]
        if kind == "settle":
            d, days, why, on, origin = ep["closed"], list(x["days"]), "settle", "settle", "s"
        elif kind == "new":
            d, days, why, on, origin = self.ts, list(x["days"]), x["why"], "proposal", "p"
        else:
            d, why, origin = self.ts, r["why"], None
            on = "reask" if (r["why"] == "settle" or r["applied"].get("veto")) else "proposal"
            days = list(x["days"]) if x else [(self.t - timedelta(days=sh + 27)).isoformat(),
                                              (self.t - timedelta(days=sh)).isoformat()]
        self.tick()
        app = self.apps[aid]
        e = {"fam": fam, "opened": ep["opened"], "c": ep["c"], "base": ep["base"], "bspan": ep.get("bspan"),
             "base_src": ep.get("base_src")}
        ri = LA.evidence(app, self.camps.get(aid, []), self.ctys(aid), e, days, d, why, CA.P_PROD)
        mkt = LA.market(ri, app, self.others(aid))
        fl = {"reverted": bool(r is not None and r.get("rev"))}
        out = LA.decide(ri, mkt, self.cfg, fl)
        if r is None:
            r = {"id": _ag_id("D", "%s|%s|%s|%s" % (aid, fam, ep["opened"], origin), self.used), "app": aid,
                 "fam": fam, "why": why, "ep": {"opened": ep["opened"], "c": ep["c"]}, "seen": self.now_iso,
                 "first": d, "last": d, "next": None, "n": 0, "dec": None, "branch": None, "part": None,
                 "cause": None, "short": None, "asks": [], "applied": {"veto": None, "accept": None}, "level": None,
                 "chk": None, "vd": "pending", "ve": "pending", "rev": None, "end": None}
            self.used.add(r["id"])
            self.rows.append(r)
        trial = on == "proposal" and out["decision"] == "accept" and self.blk["trial"]["st"] == "trial"
        sha = hashlib.sha1(json.dumps([ri, mkt], sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        a = {"d": d, "t": self.ts, "at": self.now_iso, "on": on, "days": days, "dec": out["decision"],
             "branch": out["branch"], "part": out["part"], "cause": out["cause"], "short": out["short"],
             "trial": trial, "th": self.th, "fl": fl, "sha": sha[:12], "ri": ri, "mkt": mkt,
             "k": LA.key_numbers(ri, mkt, out), "vin": {"7": None, "28": None}}
        r["asks"].append(a)
        r["last"], r["n"] = d, len(r["asks"])
        for k in ("dec", "branch", "part", "cause", "short"):
            r[k] = a[k]
        r["next"] = None if (a["dec"] == "accept" and not trial) else LA.next_phase(d)
        self.n_asks += 1
        return r

    def derive(self):
        """The frozen answers → what the rows apply (once, from the build day that first applies it): a settle-day
        keep / wait vetoes the engine's settle (for good); a later accept of a settle, or a proposal accept out of the
        trial, accepts the new level on its ask day. A money family is never accepted."""
        for r in self.rows:
            ap = r["applied"]
            if r.get("rev") or not r["asks"] or r["why"] == "revert":
                continue
            sa = _settle_ask(r)
            if sa is not None and ap.get("veto") is None and sa["dec"] in ("keep", "wait"):
                ap["veto"] = {"since_t": self.ts}
            if sa is not None:                                 # after a blocked settle: any later accept applies
                later = r["asks"][r["asks"].index(sa) + 1:] if sa["dec"] != "accept" else []
            else:
                later = [a for a in r["asks"] if not a.get("trial")]
            if ap.get("accept") is None and r["fam"] not in CA.MONEY_FAMS:
                a = next((a for a in later if a["dec"] == "accept"), None)
                if a is not None:
                    ap["accept"] = {"day": a["d"], "days": list(a["days"]), "since_t": self.ts}


    # ── the revert net (D-b): every acceptance watched 84 days; the old level back → the acceptance reverted ──
    def _net_entry(self, aid, ep):
        acc = ep["closed"]
        for x in self.blk["net"]:
            if x["app"] == aid and x.get("fam") == ep["fam"] and _near(x["ep"]["opened"], ep["opened"]) \
                    and _near(x["acc"], acc):
                return x
        own = self.find(aid, ep["fam"], ep)
        x = {"id": _ag_id("N", "%s|%s|%s|%s" % (aid, ep["fam"], ep["opened"], acc), self.used), "app": aid,
             "fam": ep["fam"], "ep": {"opened": ep["opened"], "c": ep["c"]}, "acc": acc,
             "src": "agent" if ep["why"] == "agent" else "settle", "row": own["id"] if own else None,
             "old": ep["base"], "r2": [], "r3": None, "fired": None, "done": False}
        self.used.add(x["id"])
        self.blk["net"].append(x)
        return x

    def net(self):
        """R2: weekly 28-day values from acceptance + 28 to + 84, two in a row back within one band of the OLD level;
        R3: the alarm replayed with the acceptance vetoed closes 'recovered' within 84 days. The first to fire
        reverts: the acceptance becomes an agent_veto (the alarm continues from its own c) and the row is wrong.
        → True when anything fired."""
        nc = self.cfg["net"]
        fired = False
        for aid in self.order:
            for ep in list(self._by.get(aid, [])):
                if ep["closed"] is None or not (ep["why"] == "agent" or
                                                (ep["why"] == "settled" and ep["fam"] in NET_FAMS)):
                    continue
                acc = ep["closed"]
                age = (self.t - _d(acc)).days
                if age < 0 or age > nc["days"]:
                    continue
                x = self._net_entry(aid, ep)
                if x["done"] or x.get("fired"):
                    continue
                self.tick()
                fam, e = ep["fam"], self.apps[aid]
                sh = CA.FAMILIES[fam]["shift"]
                ser = self.full_ser(aid)
                ia = CA._ix(e.day0, acc)
                checks = []
                for k in range(nc["from"], min(nc["days"], age) + 1, nc["every"]):
                    v = ser.value(fam, ia + k - sh - 27, ia + k - sh)
                    checks.append([k, LA.fin(v), LA.back_at_old(fam, v, x["old"], CA.P_PROD)])
                x["r2"] = checks
                k2 = LA.revert_due([(k, b) for k, _, b in checks], self.cfg)
                prims = {k: list(v) for k, v in self.prims.items() if k[0] == aid}
                lst = [p for p in prims.get((aid, fam), []) if not (p["act"] == "agent"
                                                                    and _near(p["ep_open"], ep["opened"]))]
                lst.append({"act": "agent_veto", "ep_open": ep["opened"], "id": "shadow"})
                prims[(aid, fam)] = lst
                sr = CA.run([e], CA.P_PROD, self.ts, owner=self.owner_of(aid, prims))
                best = None
                for y in sr["episodes"]:
                    if y["kind"] == "app" and y["fam"] == fam:
                        gap = abs((_d(y["opened"]) - _d(ep["opened"])).days)
                        if gap <= MATCH_DAYS and (best is None or gap < best[0]):
                            best = (gap, y)
                sx = best[1] if best else None
                x["r3"] = {"t": self.ts, "closed": sx["closed"] if sx else None, "why": sx["why"] if sx else None}
                hit = []
                if sx and sx["why"] == "recovered" and acc <= sx["closed"] <= (_d(acc) + timedelta(
                        days=nc["days"])).isoformat():
                    hit.append((sx["closed"], 0, "r3"))
                if k2 is not None:
                    hit.append(((_d(acc) + timedelta(days=k2)).isoformat(), 1, "r2"))
                if not hit:
                    continue
                day, _, by = min(hit)
                i = CA._ix(e.day0, day) - sh
                v = ser.value(fam, i - 27, i) if i - 27 >= 0 else None
                rev = {"by": by, "day": day, "t": self.ts, "at": self.now_iso, "v": LA.fin(v), "old": x["old"]}
                row = next((r for r in self.rows if r["id"] == x["row"]), None) if x["row"] else None
                if row is None:
                    row = self._revert_row(aid, ep, rev)
                    x["row"] = row["id"]
                row["rev"] = rev
                row["vd"] = row["ve"] = "wrong"
                x["fired"], x["done"] = {"by": by, "day": day}, True
                fired = True
        for x in self.blk["net"]:
            if not x["done"] and (self.t - _d(x["acc"])).days > nc["days"]:
                x["done"] = True
        return fired

    def _revert_row(self, aid, ep, rev):
        """A row for a revert of an engine settle nobody asked; its cause carries no value (the page prints rev's old
        and v in the view's own unit and money)."""
        fam = ep["fam"]
        if rev["by"] == "r3":
            cause = "back at the old level: the alarm came back to it within %d days of the acceptance — reverted" % (
                self.cfg["net"]["days"])
        else:
            cause = "back at the old level: two 28-day checks in a row within one band of it — reverted"
        r = {"id": _ag_id("D", "%s|%s|%s|r" % (aid, fam, ep["opened"]), self.used), "app": aid, "fam": fam,
             "why": "revert", "ep": {"opened": ep["opened"], "c": ep["c"]}, "seen": self.now_iso,
             "first": rev["day"], "last": rev["day"], "next": None, "n": 0, "dec": "revert",
             "branch": "revert_" + rev["by"], "part": None, "cause": cause, "short": "back at old level: reverted",
             "asks": [], "applied": {"veto": None, "accept": None}, "level": None, "chk": None, "vd": "wrong",
             "ve": "wrong", "rev": None, "end": None}
        self.used.add(r["id"])
        self.rows.append(r)
        return r


    # ── every stored answer checked again: parity (the same inputs give the same answer), vintage (the same day asked
    #    again on matured data), the accept trial, the verdicts ──
    def parity(self):
        """Every stored ask made under the rule in force decided again from its own rule inputs → True when one differs
        (run before this build's asks: it reads only the answers earlier builds froze)."""
        pr = self.blk["parity"]
        n, bad = 0, False
        for r in self.rows:
            for a in r["asks"]:
                if not a.get("ri") or a.get("mkt") is None or a.get("th") != self.th:
                    continue
                out = LA.decide(a["ri"], a["mkt"], self.cfg, a.get("fl") or {})
                n += 1
                if (out["decision"], out["branch"], out["part"], out["cause"]) != \
                        (a["dec"], a["branch"], a.get("part"), a.get("cause")):
                    pr["bad"] += 1
                    bad = True
        pr["checked"] += n
        if bad:
            pr["last_bad"] = self.ts
        return bad

    def vintage(self):
        """Each ask with its rule inputs, made under the rule in force, asked again 7 and 28 days after its build: the
        same day, episode and new days on this build's data. An accept / not-accept flip starts the trial again right
        where it is recorded (a timeout later in this build keeps both)."""
        vt = self.blk["vintage"]
        n = 0
        for r in self.rows:
            if r["app"] not in self.apps:
                continue
            for a in r["asks"]:
                if not a.get("ri") or a.get("mkt") is None or a.get("th") != self.th:
                    continue
                vin = a.setdefault("vin", {"7": None, "28": None})
                for key, k in (("7", 7), ("28", 28)):
                    if vin.get(key) is not None or (self.t - _d(a["t"])).days < k:
                        continue
                    if n >= self.cfg["max_asks"]:
                        return
                    self.tick()
                    ri0 = a["ri"]
                    e = {"fam": ri0["fam"], "opened": ri0["ep"]["opened"], "c": ri0["ep"]["c"],
                         "base": ri0["old"]["v"], "bspan": ri0["old"]["days"], "base_src": None}
                    app = self.apps[r["app"]]
                    ri = LA.evidence(app, self.camps.get(r["app"], []), self.ctys(r["app"]), e, ri0["new"]["days"],
                                     ri0["d"], ri0["why"], CA.P_PROD)
                    out = LA.decide(ri, LA.market(ri, app, self.others(r["app"])), self.cfg, a.get("fl") or {})
                    err, f = _leaf_err(ri0, ri)
                    x = {"t": self.ts, "dec": out["decision"], "branch": out["branch"],
                         "flip": out["decision"] != a["dec"] or out["branch"] != a["branch"],
                         "acc_flip": (a["dec"] == "accept") != (out["decision"] == "accept"), "err": err, "f": f}
                    vin[key] = x
                    n += 1
                    vt["done" + key] += 1
                    vt["flips"] += int(x["flip"])
                    vt["accept_flips"] += int(x["acc_flip"])
                    if err is not None and (vt["err_max"] is None or err > vt["err_max"]):
                        vt["err_max"], vt["err_f"] = err, f
                    if x["acc_flip"]:
                        self.restart("vintage")

    def restart(self, why):
        """D-c: the accept trial starts again from this day — one why per build (the first of rule, parity, vintage);
        a restart the block has already (an earlier build of this data day) is not logged again."""
        if self.restarted:
            return
        self.restarted = True
        tr = self.blk["trial"]
        if (tr["st"], tr["since"], tr["why"]) == ("trial", self.ts, why):
            return
        tr.update(st="trial", since=self.ts, why=why, exit=None)
        tr["log"].append([self.ts, "trial", why])

    def check(self):
        """Before this build's asks (each freezes the trial state): a rule change or a parity mismatch starts the accept
        trial again, then the vintage re-asks (an accept flip starts it again too)."""
        if self.blk.get("th") != self.th:
            self.blk["th"] = self.th
            self.restart("rule")
        if self.parity():
            self.restart("parity")
        self.vintage()

    def trial(self):
        """D-c: accepts of proposals stay a trial until ≥ 28 days since it (re)started (a rule change, a parity mismatch
        or an accept flip starts it again: check) and ≥ 1 vintage re-ask at +28 was done since — then live."""
        tr = self.blk["trial"]
        if tr["st"] != "trial" or (self.t - _d(tr["since"])).days < self.cfg["trial"]["days"]:
            return
        done28 = any(((a.get("vin") or {}).get("28") or {}).get("t", "") >= tr["since"]
                     for r in self.rows for a in r["asks"])
        if done28:
            tr.update(st="live", exit=self.ts)
            tr["log"].append([self.ts, "live", "clean"])

    def verdicts(self):
        """§5.11: the 28-day values 28 / 56 / 84 days after the reference ask, final (then frozen) at + 84."""
        for r in self.rows:
            if r["app"] not in self.apps or (r.get("chk") or {}).get("final"):
                continue
            ref = self.ref_ask(r)
            if ref is None:
                continue
            fam, e = r["fam"], self.apps[r["app"]]
            sh = CA.FAMILIES[fam]["shift"]
            ser = self.full_ser(r["app"])
            p = ref["d"]
            ip = CA._ix(e.day0, p)
            vals = []
            v = {}
            for k in self.cfg["checks"]:
                if (self.t - _d(p)).days < k:
                    v[str(k)] = None
                    continue
                x = ser.value(fam, ip - sh + k - 27, ip - sh + k) if ip - sh + k - 27 >= 0 else None
                v[str(k)] = x
                vals.append((k, x))
            final = (self.t - _d(p)).days >= max(self.cfg["checks"])
            old, new = (ref.get("k") or {}).get("old"), (ref.get("k") or {}).get("new")
            r["chk"] = {"p": p, "old": old, "new": new, "v": v, "final": final}
            dec = "accept" if (r["applied"].get("accept") or self.passed(r)) else ref["dec"]
            vd = LA.verdict(dec, LA.label(fam, old, new, vals, CA.P_PROD)) if final and old and new else (
                "unclear" if final else "pending")
            ep = self.match(r["app"], fam, r["ep"]["opened"])
            back = bool(ep and ep["why"] == "recovered" and ep["closed"] and
                        ep["closed"] <= (_d(p) + timedelta(days=max(self.cfg["checks"]))).isoformat())
            if r.get("rev"):
                vd = ve = "wrong"
            elif dec == "accept":
                ve = vd
            else:
                ve = "came_back" if back else vd
            r["vd"], r["ve"] = vd, ve

    def passed(self, r):
        sa = _settle_ask(r)
        return sa is not None and sa["dec"] == "accept"

    def ref_ask(self, r):
        """The verdict's reference: the applied accept's ask (or a passed settle's), else the row's first ask."""
        acc = r["applied"].get("accept")
        if acc:
            return next((a for a in r["asks"] if a["d"] == acc["day"] and a["dec"] == "accept"), r["asks"][-1])
        return r["asks"][0] if r["asks"] else None


    # ── what the build keeps and ships ──
    def status(self, r, held=None):
        """The row's status word (first match): held · overridden · reverted · accepted · passed · closed · trial ·
        blocked · hold · waiting · kept."""
        held = self.held(r["app"], r["fam"]) if held is None else held
        if held and r.get("end") is None and not r.get("rev"):
            return "held"
        if self.ovr(r):
            return "overridden"
        if r.get("rev"):
            return "reverted"
        if r["applied"].get("accept"):
            return "accepted"
        if self.passed(r):
            return "passed"
        if r.get("end") is not None:
            return "closed"
        if r["asks"] and r["asks"][-1].get("trial"):
            return "trial"
        if r["applied"].get("veto"):
            return "blocked" if r["dec"] == "keep" else "hold"
        return "waiting" if r["dec"] == "wait" else "kept"

    def quiet(self):
        """(app, fam, opened) → the build day an agent veto or revert first re-opened it (its older notices: seeded)."""
        out = {}
        for r in self.rows:
            days = [x for x in ((r["applied"].get("veto") or {}).get("since_t"), (r.get("rev") or {}).get("t")) if x]
            if days:
                out[(r["app"], r["fam"], r["ep"]["opened"])] = max(days)
        return out

    def _res0_accepted(self, r):
        rows = ((self.res0.get("levels") or {}).get(("app", r["app"])) or {}).get(r["fam"]) or []
        return next((x for x in rows if x["src"] == "accepted" and (x.get("ep") or {}).get("opened")
                     and _near(x["ep"]["opened"], r["ep"]["opened"])), None)

    def marks(self):
        """{(app, fam): {"tag": [(src, ep opened, mark)], "extra": [level rows the agent world no longer makes]}}."""
        out = {}
        for r in self.rows:
            if r["app"] not in self.apps:
                continue
            m = out.setdefault((r["app"], r["fam"]), {"tag": [], "extra": []})
            base = {"dec": r["id"], "short": r.get("short"), "cause": r.get("cause"),
                    "next": r.get("next") if self.status(r) in _STANDING else None}
            acc = r["applied"].get("accept")
            if self.passed(r) and not r.get("rev"):
                m["tag"].append(("accepted", r["ep"]["opened"], dict(base, st="passed")))
            if acc and not r.get("rev"):
                m["tag"].append(("accepted_agent", r["ep"]["opened"], dict(base, st="agent")))
            if r["applied"].get("veto"):
                x = self._res0_accepted(r)
                dec = (_settle_ask(r) or {}).get("dec") if acc else r["dec"]
                if x is not None:
                    st = "reverted" if (r.get("rev") and not acc) else ("blocked" if dec == "keep" else "hold")
                    m["extra"].append(_lv_fresh(x, dict(base, st=st)))
            elif r.get("rev") and not acc:                      # an engine settle reverted
                x = self._res0_accepted(r)
                if x is not None:
                    m["extra"].append(_lv_fresh(x, dict(base, st="reverted")))
            if acc and r.get("rev"):                            # an agent accept reverted: rebuilt from what it applied
                mv = _measured(self.apps[r["app"]], r["fam"], acc["days"])
                old = (self.ref_ask(r) or {}).get("k", {}).get("old")
                if mv is not None and mv["v"] > 0:
                    m["extra"].append({"from": acc["day"], "v": mv["v"], "days": list(acc["days"]),
                                       "src": "accepted_agent", "ep": {"opened": r["ep"]["opened"], "old": old},
                                       "act": r["id"], "ag": dict(base, st="reverted")})
        return out

    def finish(self, led):
        """After the history merge: each row names its level row; the block goes into the history; the ship data."""
        lid = {}
        for fams in (led.get("apps") or {}).values():
            for lst in fams.values():
                for x in lst:
                    m = x.get("ag") or {}
                    if m.get("dec"):
                        lid.setdefault(m["dec"], {})[m.get("st")] = x["id"]
        for r in self.rows:
            ids = lid.get(r["id"]) or {}
            r["level"] = next((ids[k] for k in ("agent", "passed", "reverted", "blocked", "hold") if k in ids), None)
        _ag_trim(self.blk, self.t, self.cfg)
        led["agent"] = self.blk
        self.ship_data = self.ship()

    def ship(self):
        apps, board = {}, {"accepted": 0, "right": 0, "wrong": 0, "unclear": 0, "pending": 0, "kept": 0, "waiting": 0,
                           "trial": 0, "reverted": 0, "overridden": 0, "held": 0}
        st_n = {"checked": 0, "passed": 0, "blocked": 0, "hold": 0, "later": 0}
        for r in self.rows:
            if r["app"] not in self.apps:
                continue
            held = self.held(r["app"], r["fam"])
            st, ovr = self.status(r, held), self.ovr(r)
            row = _ag_ship(self, r, st, ovr, held)
            apps.setdefault(r["app"], []).append(row)
            board["reverted"] += 1 if r.get("rev") else 0
            if r["why"] in ("money", "open"):
                if r["applied"].get("accept"):
                    board["accepted"] += 1
                    vd, ve = r.get("vd"), r.get("ve")
                    k = "wrong" if "wrong" in (vd, ve) else ("unclear" if "unclear" in (vd, ve) else (
                        "right" if vd == ve == "right" else "pending"))
                    board[k] += 1
                elif st == "trial":
                    board["trial"] += 1
                elif r["dec"] == "keep":
                    board["kept"] += 1
                elif r["dec"] == "wait":
                    board["waiting"] += 1
                board["overridden"] += 1 if ovr else 0
                board["held"] += 1 if st == "held" else 0
            if _settle_ask(r) is not None:
                st_n["checked"] += 1
                if self.passed(r):
                    st_n["passed"] += 1
                elif r["applied"].get("accept"):
                    st_n["later"] += 1
                elif r["applied"].get("veto"):
                    st_n["blocked" if r["dec"] == "keep" else "hold"] += 1
        out = {}
        for aid, rows in apps.items():
            rows.sort(key=lambda x: (x["_last"], x["id"]), reverse=True)
            out[aid] = {"rows": rows, "tag": _ag_tag(rows, self.t)}
        tr = self.blk["trial"]
        vt = self.blk["vintage"]
        self.board = {"v": 1, "mode": "on", "rule": LA.RULE, "th": self.th, "since": self.blk["first_t"], "ms": 0,
                      "trial": {"st": tr["st"], "since": tr["since"], "day": (self.t - _d(tr["since"])).days,
                                "need": self.cfg["trial"]["days"], "why": tr["why"], "exit": tr.get("exit")},
                      "n": board, "settle": st_n,
                      "parity": {"checked": self.blk["parity"]["checked"], "bad": self.blk["parity"]["bad"]},
                      "vintage": {"done": vt["done7"] + vt["done28"], "flips": vt["flips"],
                                  "accept_flips": vt["accept_flips"]},
                      "bt": self.extra.get("bt")}
        return out


def _settle_ask(r):
    """The row's answer to the engine's own settle of its episode (asked as of the settle day), else None."""
    return next((a for a in r["asks"] if a.get("on") == "settle"), None)


def _lv_fresh(x, mark):
    """An engine level row → the history merge's fresh-row shape, with the agent's mark."""
    return {"from": x["day"], "v": x["v"], "days": x["days"], "src": x["src"], "ep": x.get("ep"), "act": x.get("act"),
            "ag": mark}


def _ag_ship(ag, r, st, ovr, held):
    """One decision row as the app file carries it (§6.3); "_last" (the newest activity) only sorts."""
    asks = r["asks"]
    h = []
    for a in asks:
        if h and (h[-1][3], h[-1][4], h[-1][5]) == (a["dec"], a["branch"], a.get("part")):
            h[-1][1], h[-1][6] = a["d"], a.get("short")
            h[-1][2] += 1
        else:
            h.append([a["d"], a["d"], 1, a["dec"], a["branch"], a.get("part"), a.get("short")])
    h.reverse()
    acc, rev = r["applied"].get("accept"), r.get("rev")
    xp = None
    if r["fam"] == "CPI" and st not in ("accepted", "passed") and asks:
        ep = ag.match(r["app"], "CPI", r["ep"]["opened"])
        if ep is not None and ep.get("base"):
            e = ag.apps[r["app"]]
            m = CA._ep_money(e, ag.full_ser(r["app"]), "CPI", CA._ix(e.day0, r["first"]),
                             CA._ix(e.day0, ep["closed"] or ag.ts), ep["base"])
            if m:
                xp = {"inr": m["since_c_inr"], "usd": m["since_c_usd"], "from": r["first"]}
    last = max(x for x in (r.get("last"), (rev or {}).get("day"), _ist_day((ovr or {}).get("at")),
                           (acc or {}).get("day"), r.get("first")) if x)
    return {"id": r["id"], "fam": r["fam"], "why": r["why"], "st": st, "dec": r["dec"], "branch": r["branch"],
            "part": r["part"], "cause": r["cause"], "short": r["short"], "first": r["first"], "last": r["last"],
            "next": r["next"] if st in _STANDING else None, "n": r["n"], "ep": dict(r["ep"]),
            "applied": {"day": acc["day"], "days": list(acc["days"])} if acc else None,
            "trial": bool(asks and asks[-1].get("trial")), "level": r.get("level"), "h": h,
            "k": dict(asks[-1]["k"]) if asks else None, "k0": dict(asks[0]["k"]) if asks else None,
            "chk": copy.deepcopy(r.get("chk")), "vd": r.get("vd"), "ve": r.get("ve"),
            "rev": {k: rev.get(k) for k in ("by", "day", "old", "v")} if rev else None,
            "ovr": {"at": ovr["at"], "act": ovr["act"]} if ovr else None, "held": bool(held),
            "end": dict(r["end"]) if r.get("end") else None, "xp": xp, "_last": last}


_TAG_RANK = {"reverted": 0, "accepted": 1, "trial": 2, "waiting": 3, "hold": 3, "kept": 4, "blocked": 4,
             "overridden": 5, "held": 6}
_STANDING = ("trial", "waiting", "hold", "kept", "blocked")     # the rows the agent asks again (only these ship a next)


def _ist_day(at):
    """An owner action's UTC time → its IST day (every day the owner reads is an IST day), else None."""
    try:
        x = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (x if x.tzinfo else x.replace(tzinfo=timezone.utc)).astimezone(ZoneInfo(IST)).date().isoformat()


def _ag_tag(rows, t):
    """The list row's tag (§6.4) from the app's shipped rows (newest first)."""
    cands = []
    for x in rows:
        st = x["st"]
        if st not in _TAG_RANK:
            continue
        day = {"reverted": (x["rev"] or {}).get("day"), "accepted": (x["applied"] or {}).get("day"),
               "overridden": _ist_day((x["ovr"] or {}).get("at"))}.get(st)
        if st in ("waiting", "hold"):
            day = x["next"]
        if st in ("reverted", "accepted", "overridden") and (not day or (t - _d(day)).days > 28):
            continue
        cands.append((_TAG_RANK[st], x, day))
    if not cands:
        return None
    _, best, day = min(cands, key=lambda z: z[0])
    more = sum(1 for x in rows if x["st"] in _STANDING and x is not best)
    return {"st": best["st"], "fam": best["fam"], "short": best["short"], "day": day, "more": more}


def _leaves(x, path=""):
    if isinstance(x, dict):
        for k in sorted(x):
            yield from _leaves(x[k], (path + "." + k) if path else k)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _leaves(v, "%s[%d]" % (path, i))
    elif x is None or (isinstance(x, (int, float)) and not isinstance(x, bool)):
        yield path, x


def _leaf_err(a, b):
    """The largest relative change between two rule inputs over their numeric leaves (absolute when the first is
    ~0; a leaf known in one and not the other counts 1.0) → (that change, its path)."""
    A, B = dict(_leaves(a)), dict(_leaves(b))
    err, f = None, None
    for p in sorted(set(A) | set(B)):
        x, y = A.get(p), B.get(p)
        if x is None and y is None:
            continue
        e = 1.0 if (x is None or y is None) else (abs(y - x) if abs(x) < 1e-9 else abs(y - x) / abs(x))
        if err is None or e > err:
            err, f = e, p
    return LA.fin(err), f


def _ag_trim(blk, t, cfg):
    """Rule inputs stay on a row's first ask, every ask that changed the answer, the last 5 and the last keep_ri days;
    past AG_MAX_BYTES the oldest asks lose theirs first (rows, asks and key numbers are never dropped)."""
    since = (t - timedelta(days=cfg["keep_ri"])).isoformat()
    for r in blk["rows"]:
        asks = r["asks"]
        for i, a in enumerate(asks):
            changed = i == 0 or (a["dec"], a["branch"], a.get("part")) != \
                (asks[i - 1]["dec"], asks[i - 1]["branch"], asks[i - 1].get("part"))
            if not (changed or i >= len(asks) - 5 or a["t"] >= since):
                a["ri"] = a["mkt"] = None
    size = len(json.dumps(blk, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    if size <= AG_MAX_BYTES:
        return
    olds = sorted((a["t"], a["d"], i, j) for i, r in enumerate(blk["rows"]) for j, a in enumerate(r["asks"])
                  if a.get("ri") is not None or a.get("mkt") is not None)
    for _, _, i, j in olds:
        a = blk["rows"][i]["asks"][j]
        size -= len(json.dumps([a.get("ri"), a.get("mkt")], ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode("utf-8")) - len("[null,null]")
        a["ri"] = a["mkt"] = None
        if size <= AG_MAX_BYTES:
            break


def _ag_undo(blk, rows0, net0):
    """A timeout: what this build applied or reverted is taken back (none of it shipped). Each row gets back what it
    applied, its revert and its verdicts as this build found them (rows0: what an earlier build of the same data day
    did stays); a row this build made without an ask (a revert) goes; the net is as it was (net0). Its asks stay."""
    keep = []
    for r in blk["rows"]:
        was = rows0.get(r["id"])
        if was is not None:
            r.update(copy.deepcopy(was))
        elif not r["asks"]:
            continue
        else:
            r.update(applied={"veto": None, "accept": None}, rev=None, vd="pending", ve="pending")
        keep.append(r)
    blk["rows"][:] = keep
    blk["net"][:] = net0


def backtest_path(data_dir):
    return os.path.join(data_dir, STATE_DIR, BT_FILE)


def load_backtest(data_dir):
    """data/cpi/agent_backtest.json (the private repo, committed once by hand; read only) → the scoreboard's
    backtest line, or None (absent; or bad: one "cpi agent backtest skipped: <Type>" line, the agent still runs).
    v 1 counts the CPI / GAP settles; v 2 every engine settle the agent asks (also of an alarm it answered)."""
    path = backtest_path(data_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            b = json.load(f)
        keys = {"proposals": ("moments", "c1_accept", "c1_right", "c1_wrong", "accept"),
                "settles": ("checked", "passed", "blocked", "hold", "level_held")}
        if not isinstance(b, dict) or set(b) != {"v", "years", "proposals", "settles", "note"} or \
                isinstance(b["v"], bool) or b["v"] not in BT_V:
            raise ValueError("backtest")
        if not (_real(b["years"]) and 0 < b["years"] < 50):
            raise ValueError("backtest")
        for k, ks in keys.items():
            x = b[k]
            if not isinstance(x, dict) or set(x) != set(ks) or \
                    any(not (isinstance(x[j], int) and not isinstance(x[j], bool) and x[j] >= 0) for j in ks):
                raise ValueError("backtest")
        n = b["note"]
        if not isinstance(n, str) or len(n) > 200 or any(unicodedata.category(c) in ("Cc", "Cf") for c in n):
            raise ValueError("backtest")
        return copy.deepcopy(b)
    except Exception as e:
        print("cpi agent backtest skipped: %s" % type(e).__name__, file=sys.stderr)
        return None


def agent_run(ents, res0, owner, la, led, t, now, extra):
    """The level agent's step (D-a … D-j) → (the agent world: the replay with the owner's and the agent's primitives,
    the agent part). A. the saved block (validated: bad → ValueError) or a new one; B. the world from the frozen rows;
    C. parity and the vintage re-asks over the answers earlier builds froze (a rule change, a mismatch or an accept
    flip starts the trial again: before the asks, which freeze it); D. ≤ 3 passes: the due questions answered
    (frozen), their primitives, the apps replayed again; E. the revert net; F. the trial's exit, the verdicts. The
    part: {"blk", "ran", "marks", "quiet", "finish"}; finish (after the history merge) names each row's level row, puts
    the block into the history and makes the ship data. AgentTimeout (budget_s): the asks so far are kept (the
    exception carries the block), nothing this build applied or reverted stays."""
    cfg = agent_cfg()
    ts = t.isoformat()
    raw = led.get("agent")
    blk = _check_block(copy.deepcopy(raw)) if raw is not None else _new_block(ts, gu._now_iso(now), cfg)
    net0 = copy.deepcopy(blk["net"])
    rows0 = {r["id"]: {k: copy.deepcopy(r.get(k)) for k in ("applied", "rev", "vd", "ve")} for r in blk["rows"]}
    ag = _Agent(ents, res0, owner, la, blk, t, now, extra, cfg)
    try:
        ag.derive()
        ag.update(ag.derive_prims())
        ag.sync()
        ag.check()
        for _ in range(3):
            qs = ag.questions()
            if not qs or ag.n_asks >= cfg["max_asks"]:
                break
            for q in qs:
                if ag.n_asks >= cfg["max_asks"]:
                    break
                ag.ask(q)
            ag.derive()
            ag.update(ag.derive_prims())
            ag.sync()
        if ag.net():
            ag.update(ag.derive_prims())
            ag.sync()
        ag.trial()
        ag.verdicts()
    except AgentTimeout:
        _ag_undo(blk, rows0, net0)
        _ag_trim(blk, t, cfg)
        raise AgentTimeout(blk)
    ms = int(round((_clock() - ag.start) * 1000))

    def finish(merged):
        ag.finish(merged)
        ag.board["ms"] = ms
    return ag.world, {"blk": blk, "ran": True, "marks": ag.marks(), "quiet": ag.quiet(), "finish": finish, "ag": ag}


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


def _unchecked(a, ep):
    """A D0 ROAS episode opened without the AdMob check: the app has no ROI rows in this build (the ROI step is off or
    failed for it), so the engine had nothing to confirm it against (confirm "no_data")."""
    return ep["fam"] == "ROAS_G" and ep.get("confirm") == "no_data" and not (a.get("notes") or {}).get("roi_rows")


def _ledger(st, first, apps, t, now, quiet=None):
    """Every open (and lately closed) ALERT / WATCH app episode → its ledger record; each ALERT notice (the opening,
    every re-notice) is due ONCE: never on the first build (seeded), never for a new D0 ROAS episode opened without the
    AdMob check (seeded; its alert item is provisional), never when first seen > LATE_DAYS after its day, never a re-notice of a seeded
    episode (shown only), and joined (not sent) when the app had a push in the PUSH_GAP days before — a seeded opening
    day counts as that push day. quiet ({(app id, fam, opened): build day}: an alarm the level agent re-opened):
    every notice of it dated on or before that day is seeded, never sent; later ones follow the rules above.
    → {(app id, fam, opened): (key, due)}, due = [notice key, …]."""
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
                st["eps"][k] = {"app_id": aid, "fam": ep["fam"], "opened": ep["opened"],
                                "seeded": bool(first or _unchecked(a, ep)), "first_at": now_iso, "notices": {}}
            used.add(k)
            rec = st["eps"][k]
            rec["tier"], rec["closed"] = ep["tier"], ep["closed"]
            due = []
            q = _quiet_day(quiet, aid, ep["fam"], ep["opened"])
            if ep["tier"] == "ALERT" and ep["closed"] is None:
                for day, is_open in [(ep["opened"], True)] + [(d, False) for d, _ in ep["esc"]]:
                    nk = _notice_key(rec, day, is_open)
                    n = rec["notices"].get(nk)
                    if q is not None and day <= q:         # re-opened by the agent: seeded, not pushed
                        if n is None:
                            rec["notices"][nk] = {"day": day, "seeded": True}
                        elif n.get("notified_at") is None and not n.get("seeded") and not n.get("joined"):
                            n["seeded"] = True
                        continue
                    if n is not None:
                        if n.get("notified_at") is None and not n.get("seeded") and not n.get("joined"):
                            due.append(nk)
                        continue
                    if first or rec.get("seeded") or (t - _d(day)).days > LATE_DAYS:
                        rec["notices"][nk] = {"day": day, "seeded": True}
                        continue
                    last = st["push"].get(aid)
                    op = rec["notices"].get("open") or {}
                    if op.get("seeded") and op.get("day") and (not last or op["day"] > last):
                        last = op["day"]                      # the seeded opening was shown: the push day to join to
                    if last and 0 <= (_d(day) - _d(last)).days <= PUSH_GAP:
                        rec["notices"][nk] = {"day": day, "joined": last}
                        continue
                    rec["notices"][nk] = {"day": day, "notified_at": None}
                    due.append(nk)
            out[(aid, ep["fam"], ep["opened"])] = (k, due)
    return out


def _quiet_day(quiet, aid, fam, opened):
    """The build day the agent re-opened this episode (±7 days on its opening), or None."""
    for (a, f, o), day in (quiet or {}).items():
        if a == aid and f == fam and _near(o, opened):
            return day
    return None


def _alert_item(a, ep, rec, due, t, others, closed=False):
    """One app's alert in the GA4 families' shape (the Alerts screen's link note and send_alerts): `text` Hinglish,
    `message` plain (₹ for cost, CPI and money, $ for eCPM). id = the episode + its newest notice day, so a re-notice is
    a new id (sent once) and a re-run keeps the same one."""
    v = a["view"]
    w, nrm = v["w"], v["nrm"]
    fam, nm = ep["fam"], a["name"]
    now_v = w.get(fam) if fam in ("CPI", "ECPM", "ROAS_G") else None
    base = ep.get("base_show", ep["base"])
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
            "notify": bool(due) and not closed, "seeded": bool(rec.get("seeded")),
            "provisional": _unchecked(a, ep),
            "estimate": False, "fresh": (t - _d(ep["opened"])).days < 7,
            "lost": {"inr": sc.get("inr"), "usd": sc.get("usd"), "from": lost["from"]} if sc else None,
            "text": text, "message": "%s: %s" % (nm, msg)}
    if closed:
        item.update(closed=ep["closed"], closed_at=None, close_reason=ep["why"], notify=False)
    return item


def _alert_at(rec):
    ats = [n.get("notified_at") for n in (rec.get("notices") or {}).values() if n.get("notified_at")]
    return max(ats) if ats else None


def alerts(st, first, apps, t, now, quiet=None):
    """→ (alerts, closed): one alert per app with an open ALERT or WATCH episode (its worst one: ALERT before WATCH, a
    ROAS alarm first, then the earliest change), the app's episodes closed in the last CLOSED_DAYS days; st["due"] = the
    notices each due alert id carries (mark_notified_cpi). quiet: _ledger's (the agent's re-opened alarms)."""
    led = _ledger(st, first, apps, t, now, quiet)
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
    """The whole step without writing → (pointer, cpi.json.gz body, per-app bodies, apps, D, engine result, the levels
    part: {"ledger" (None: the history file could not be read), "props", "la", "seen"} or None when it failed) or None
    (no Google Ads data / no data day)."""
    roas = dashboard.get("roas") or {}
    if not roas.get("configured", bool(roas.get("by_app"))) or not roas.get("by_app"):
        return None
    t, till = data_day(dashboard, data_dir, s, now)
    if t is None:                                        # Google Ads is set up but a side of the data day is unknown:
        if counts is not None:                           # a failure the health banner must show, never a quiet no-tab
            counts["why"] = "NoDataDay"
        return None
    got = gather(dashboard, data_dir, out_dir, s, t, counts)
    if not got:
        if counts is not None:
            counts["why"] = "NoSpendCache"
        return None
    D, apps, camps, ctys, extra = got
    ents = entities(apps, camps, ctys, D)
    extra["day0"] = {e.id: e.day0 for e in ents if e.kind == "app"}
    extra["cday0"] = {e.id: e.day0 for e in ents if e.kind == "country"}
    extra["D"] = D
    res, extra["lv"] = levels_run(ents, data_dir, t, now, extra)
    ptr, allb, files, big = build_files(dashboard, D, apps, camps, ctys, extra, res, now)
    if counts is not None:
        counts["big"] = big
    gt = [a["notes"].get("ga4_till") for a in apps if a.get("view") and a["notes"].get("ga4_till")]
    till["ga4"] = min(gt) if gt else None
    ptr["till"] = till
    return ptr, allb, files, apps, D, res, extra["lv"]


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
            LINE = ("cpi skipped: %s" % counts["why"]) if counts.get("why") else "cpi: apps 0"
            return []
        ptr, allb, files, apps, D, res, lv = got
        raw = _raw(allb)
        if not _fits(raw):
            _remove(out_dir)
            LINE = "cpi skipped: TooBig"
            return []
        os.makedirs(out_dir, exist_ok=True)
        for fn, body in sorted(files.items()):
            write_json_gz_stable(os.path.join(out_dir, fn), body)
        write_json_gz_stable(os.path.join(out_dir, FILE), allb)
        _clean(out_dir, set(files))
        st, first = load_state(data_dir)
        part = (lv or {}).get("agent") or {}
        al, closed = alerts(st, first, apps, D.t, now, quiet=part.get("quiet") if part.get("ran") else None)
        save_state(data_dir, st)
        if lv is not None and lv["ledger"] is not None:
            try:
                save_ledger(data_dir, lv["ledger"])
            except Exception as e:                       # the history file costs only itself
                print("cpi levels skipped: %s" % type(e).__name__, file=sys.stderr)
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
