"""Google Ads installs by COUNTRY × DAY for the 🆕 First open tab (GADS_INST; private data/ only). Owner, 2 Nov 2026: "ss2
me google ads ka install bhi dikhao taki pata chale kitna open hi nahi kar raha he user". Per app campaign store, every
day and country, what Google Ads counts for the app campaigns, every conversion action apart and the secondary ones too
(all_conversions):
  play  Google Play's own install count: GOOGLE_PLAY_DOWNLOAD + ANDROID_INSTALLS_ALL_OTHER_APPS (most campaigns bid on
        first_open, so the build's "Google Ads installs" — biddable / DOWNLOAD conversions — ARE first opens there);
  fo    Google Ads' Firebase first opens: FIREBASE_ANDROID_FIRST_OPEN.
Measured (gads_inst_probe, 2 Nov 2026, 28 days): accepted on every account with app campaigns; the countries tie to the
campaign rows (Σ ÷ campaign total 0.9998); first opens ÷ Play installs 0.55–0.99 by app; GA4's own first opens of the
Google Ads users within 1–3 points of Google Ads' first opens.

Per build (the ROAS step, after the geo step; `spend` only read — its campaigns give each store's accounts, its days the
history floor), at most MAX_CALLS requests and MAX_SEC seconds, WORKERS accounts side by side (one request at a time
each); a quota error stops every further request:
  refresh   every REFRESH_SEC the last RECENT_DAYS days (Google Ads credits a conversion back to its click day for as
            long as the conversion window) — replaced whole;
  backfill  newest → oldest, CHUNK_DAYS at a time, from below the oldest covered day down to the floor (the spend
            cache's first day with spend), at most BACKFILL_CHUNKS a build; "done" once the floor is reached.
A range: the stores with spend in it (gads_geo._plan) and their accounts; per account its conversion actions (Q_CA, kept
ACT_DAYS, asked again when a row names an action it does not know) and Q_GEO (geographic_view, LOCATION_OF_PRESENCE,
MULTI_CHANNEL: country × day × conversion action → all_conversions). A store is written for the range only when every
account of it answered: each day of the range replaced by {cc: [play, fo]} ({} = nothing that day). An account answering
HTTP 403 (disabled) or gone from the MCC roster leaves its stores unknown there ("lost", kept in the state, not asked
again for that range); any other failure or a stop leaves the range uncovered (asked again next build). A range is not
begun without the calls of its accounts (+ the country map's) left. Country ids → ISO-2 through the weekly geo cache's
map, the rest by id (gads_geo._map_ids) kept in this state; an id Google Ads names no country for → "XX".

Files (deterministic, written only on change):
  data/ads_inst_day/<YYYY-MM>.json.gz  {"v": 1, "month", "days": {store: {day: {cc: [play, fo]}}}}   (2 decimals)
  data/ads_inst_day/state.json.gz      {"v", "cov": [[first, last], …] committed ranges, "floor", "done", "recent_at",
                                        "acts": {account: {"at", "map": {action id: type}}}, "iso": {ccid: ISO-2 | null},
                                        "lost": [[first, last, store], …]}
ONE counts-only public line (no ids, names, dates or numbers of installs).
"""
import gzip
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from ..db import write_json_gz_stable
from . import gads_geo as gg
from . import google_ads as gads

DIR = "ads_inst_day"
V = 1
PLAY = ("GOOGLE_PLAY_DOWNLOAD", "ANDROID_INSTALLS_ALL_OTHER_APPS")
FO = "FIREBASE_ANDROID_FIRST_OPEN"
RECENT_DAYS = 35                    # the refresh: today and the 34 days before (conversions credited back to the click day)
REFRESH_SEC = 6 * 3600
CHUNK_DAYS = 28
BACKFILL_CHUNKS = 3                 # backfill ranges per build
ACT_DAYS = 3                        # an account's conversion-action list is asked again after this long
MAX_CALLS = 120
MAX_SEC = 120
WORKERS = 4
LOST_KEEP = 400                     # "lost" entries kept (the newest)

Q_CA = "SELECT conversion_action.id, conversion_action.type FROM conversion_action"
Q_GEO = ("SELECT campaign.app_campaign_setting.app_id, campaign.advertising_channel_type, "
         "geographic_view.country_criterion_id, geographic_view.location_type, segments.date, "
         "segments.conversion_action, metrics.all_conversions "
         "FROM geographic_view WHERE segments.date BETWEEN '%s' AND '%s' "
         "AND campaign.advertising_channel_type = 'MULTI_CHANNEL' "
         "AND geographic_view.location_type = 'LOCATION_OF_PRESENCE'")


def _d(s):
    return date.fromisoformat(str(s)[:10])


def _dir(data_dir):
    return os.path.join(data_dir, DIR)


def _read(path):
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, EOFError):
        return None


def load_state(data_dir):
    s = _read(os.path.join(_dir(data_dir), "state.json.gz"))
    if not isinstance(s, dict) or s.get("v") != V:
        s = {"v": V}
    for k, v in (("cov", []), ("acts", {}), ("iso", {}), ("lost", [])):
        if not isinstance(s.get(k), type(v)):
            s[k] = v
    return s


def load_month(data_dir, month):
    m = _read(os.path.join(_dir(data_dir), month + ".json.gz"))
    return m if isinstance(m, dict) and m.get("v") == V and isinstance(m.get("days"), dict) else None


def load_all(data_dir):
    """Every month file → {store: {day: {cc: [play, fo]}}} (the build's read)."""
    out = {}
    try:
        names = sorted(os.listdir(_dir(data_dir)))
    except OSError:
        return out
    for nm in names:
        if len(nm) == 15 and nm.endswith(".json.gz") and nm[4] == "-":
            m = load_month(data_dir, nm[:7]) or {}
            for sid, dd in (m.get("days") or {}).items():
                out.setdefault(sid, {}).update(dd)
    return out


# ── ranges ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _merge(cov):
    rs = sorted([_d(a), _d(b)] for a, b in cov)
    out = []
    for a, b in rs:
        if out and a <= out[-1][1] + timedelta(days=1):
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [[a.isoformat(), b.isoformat()] for a, b in out]


def floor_of(spend):
    """The oldest day any store spent on (the backfill's floor) or None."""
    days = [d for dd in ((spend or {}).get("daily") or {}).values() for d, v in (dd or {}).items() if (v or 0) > 0]
    return _d(min(days)) if days else None


def plan(state, spend, today, now):
    """The ranges this build asks, in order: ("refresh", a, b) when due, then ("backfill", a, b) — walking down from the
    day before the recent window, covered runs skipped, at most CHUNK_DAYS uncovered days in a row each, to the floor."""
    out = []
    r0 = today - timedelta(days=RECENT_DAYS - 1)
    at = state.get("recent_at")
    if not at or (now - datetime.fromisoformat(at)).total_seconds() >= REFRESH_SEC:
        out.append(("refresh", r0, today))
    fl = floor_of(spend)
    if fl is None:
        return out
    cov = sorted([_d(a), _d(b)] for a, b in state.get("cov") or [])

    def covered(d):
        return any(a <= d <= b for a, b in cov)

    top, n = r0 - timedelta(days=1), 0
    while n < BACKFILL_CHUNKS:
        while top >= fl and covered(top):
            top = min(a for a, b in cov if a <= top <= b) - timedelta(days=1)
        if top < fl:
            break
        a = top
        while a > fl and (top - a).days + 1 < CHUNK_DAYS and not covered(a - timedelta(days=1)):
            a -= timedelta(days=1)
        out.append(("backfill", a, top))
        n += 1
        top = a - timedelta(days=1)
    return out


# ── one range ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _act(row):
    v = str((row.get("segments") or {}).get("conversionAction") or "")
    return v.rsplit("/", 1)[-1] if v else ""


def _acts(ctx, state, acct, today, force=False):
    """The account's {action id: type} (cached ACT_DAYS) or None (could not be read)."""
    c = (state["acts"].get(acct) or {})
    if not force and c.get("at") and (today - _d(c["at"])).days < ACT_DAYS and isinstance(c.get("map"), dict):
        return c["map"]
    rows = ctx.search(acct, ctx.mcc, ctx.dev, ctx.token, Q_CA)
    m = {}
    for r in rows or []:
        a = r.get("conversionAction") or {}
        if a.get("id") not in (None, ""):
            m[str(a["id"])] = a.get("type") or "?"
    state["acts"][acct] = {"at": today.isoformat(), "map": m}
    return m


def _ask(ctx, state, acct, a, b, today):
    """One account → ("ok", rows, acts) | ("403",) | ("err",) | ("stop",)."""
    try:
        acts = _acts(ctx, state, acct, today)
        rows = ctx.search(acct, ctx.mcc, ctx.dev, ctx.token, Q_GEO % (a.isoformat(), b.isoformat()))
        if any(_act(r) and _act(r) not in acts for r in rows):
            acts = _acts(ctx, state, acct, today, force=True)
        return ("ok", rows, acts)
    except gg._Stop:
        return ("stop",)
    except Exception as e:
        return ("403",) if gg._is403(e) else ("err",)


def _ccid(row):
    v = (row.get("geographicView") or {}).get("countryCriterionId")
    try:
        return str(int(v)) if v not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        return None


def _r2(v):
    v = round(float(v or 0), 2)
    return int(v) if v.is_integer() else v


def fold(rows, acts, iso):
    """GEO rows of one account → {store: {day: {cc: [play, fo]}}} (other conversion actions left out)."""
    out = {}
    for r in rows or []:
        t = acts.get(_act(r))
        k = 0 if t in PLAY else 1 if t == FO else None
        if k is None:
            continue
        sid = gads._norm_store(((r.get("campaign") or {}).get("appCampaignSetting") or {}).get("appId"))
        d = str((r.get("segments") or {}).get("date") or "")
        if not sid or not d:
            continue
        cid = _ccid(r)
        cc = (iso.get(cid) if cid else None) or "XX"
        cell = out.setdefault(sid, {}).setdefault(d, {}).setdefault(cc, [0.0, 0.0])
        cell[k] += float(((r.get("metrics") or {}).get("allConversions")) or 0)
    return out


def _range(ctx, state, spend, a, b, today, months, st):
    """Ask one range → True when it is covered (every account answered or is lost)."""
    own, noacct = gg._plan(spend, a, b)
    accts = sorted({x for ac in own.values() for x in ac if x in ctx.ccy})
    gone = {x for ac in own.values() for x in ac if x not in ctx.ccy}
    need = sum(1 if (state["acts"].get(x) or {}).get("at") else 2 for x in accts) + 2
    if ctx.run.left() < need:
        raise gg._Stop("calls")
    res = {}
    lock = threading.Lock()

    def one(x):
        r = _ask(ctx, state, x, a, b, today)
        with lock:
            res[x] = r
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(one, accts))
    if any(r[0] == "stop" for r in res.values()):
        raise gg._Stop(ctx.run.stop or "stop")
    ids = {_ccid(r) for x in accts if res[x][0] == "ok" for r in res[x][1]}
    cache = {"iso": state["iso"]}
    for k, v in (ctx.weekly_iso or {}).items():
        cache["iso"].setdefault(k, v)
    if not gg._map_ids(ctx, cache, {i for i in ids if i}, today):
        return False                                    # the map failed: nothing written (asked again)
    folded = {}
    for x in accts:
        if res[x][0] == "ok":
            for sid, dd in fold(res[x][1], res[x][2], state["iso"]).items():
                for d, cells in dd.items():
                    tgt = folded.setdefault(sid, {}).setdefault(d, {})
                    for cc, v in cells.items():
                        t = tgt.setdefault(cc, [0.0, 0.0])
                        t[0] += v[0]
                        t[1] += v[1]
    covered = not any(r[0] == "err" for r in res.values())
    for sid, ac in own.items():
        bad = [x for x in ac if x in gone or (res.get(x) or ("?",))[0] == "403"]
        if not ac or bad:
            state["lost"].append([a.isoformat(), b.isoformat(), sid])
            st["lost"] += 1
            continue
        if any((res.get(x) or ("err",))[0] != "ok" for x in ac):
            continue                                    # an account failed: this store waits for the next build
        d = a
        while d <= b:
            k = d.isoformat()
            m = months.setdefault(k[:7], load_month(ctx.data_dir, k[:7]) or {"v": V, "month": k[:7], "days": {}})
            cells = (folded.get(sid) or {}).get(k) or {}
            m["days"].setdefault(sid, {})[k] = {cc: [_r2(v[0]), _r2(v[1])] for cc, v in sorted(cells.items())}
            d += timedelta(days=1)
        st["stores"].add(sid)
    st["accounts"] |= set(accts)
    return covered


def step(s, data_dir, spend, today, *, now=None, clock=None, search=None, token=None):
    """The build's call → ONE counts-only line. Never raises."""
    import time as _t
    st = {"accounts": set(), "stores": set(), "lost": 0, "ranges": 0, "refresh": 0}
    try:
        if not gg._usable(s, spend):
            return "gads inst: off (no Google Ads settings or spend)"
        now = now or datetime.now(timezone.utc)
        run = gg._Run(clock or _t.monotonic, MAX_CALLS, MAX_SEC)
        ctx = gg._Ctx(s, run, search, token, None, "USD")
        ctx.data_dir = data_dir
        state = load_state(data_dir)
        todo = plan(state, spend, today, now)
        months, why = {}, None
        if todo and ctx.ready():
            geo = gg.load_geo(data_dir) or {}
            ctx.weekly_iso = {k: v for k, v in (geo.get("iso") or {}).items() if v}
            for kind, a, b in todo:
                try:
                    ok = _range(ctx, state, spend, a, b, today, months, st)
                except gg._Stop as e:
                    why = str(e) or "stop"
                    break
                if not ok:
                    continue
                state["cov"] = _merge(state["cov"] + [[a.isoformat(), b.isoformat()]])
                st["ranges"] += 1
                if kind == "refresh":
                    state["recent_at"] = now.isoformat()
                    st["refresh"] = 1
        elif todo:
            why = "no token"
        fl = floor_of(spend)
        if fl:
            state["floor"] = fl.isoformat()
            cov = [[_d(x), _d(y)] for x, y in state["cov"]]
            state["done"] = any(x <= fl and y >= today - timedelta(days=RECENT_DAYS) for x, y in cov)
        state["lost"] = state["lost"][-LOST_KEEP:]
        os.makedirs(_dir(data_dir), exist_ok=True)
        for m, body in months.items():
            write_json_gz_stable(os.path.join(_dir(data_dir), m + ".json.gz"), body)
        write_json_gz_stable(os.path.join(_dir(data_dir), "state.json.gz"), state)
        return ("gads inst: ranges %d (refresh %d), accounts %d, stores %d, lost %d, backfill %s, calls %d, errors %d%s"
                % (st["ranges"], st["refresh"], len(st["accounts"]), len(st["stores"]), st["lost"],
                   "done" if state.get("done") else "going", run.calls, run.errors,
                   (", stopped " + why) if why else ""))
    except Exception as e:                              # a bug here must never cost the build
        return "gads inst skipped: %s" % type(e).__name__
