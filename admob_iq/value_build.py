"""GA4 "💸 Install value" tab — the build step, called from uninstall_build.run_uninstall right after the Active users
step (one store in memory at a time; SPEC_AB_FINAL §3.4).

  * load_state / save_state: this tab's PRIVATE state, data/ga4_uninstall/value_state.json = {v, eval, episodes,
    closed, portfolio_shape}. Its own file (gu.load_state keeps only its own keys: a key inside state.json would be
    dropped by every refresh_all / mark_notified — every build a "first evaluation").
  * prepass: what every app needs once per build — Google Ads spend + installs per Play package (the ROAS step's raw
    spend cache, INR base micros), the dated FX series, the per-app deduction rate when the dashboard has one, the
    Google Ads country cache when GADS_GEO is on. No AdMob country revenue is read (countries use the app's scale).
  * app_step: loads the app's install-day files (data/ga4_uninstall/iday/<key>.json.gz + .old.json.gz), evaluates
    (engine.value), writes value_<key>.json.gz (deterministic, only on change) → the summary row.
  * finish: at the very end of run_uninstall — the portfolio curve shape, the state, stale files, then
    dashboard["value"] LAST. Nothing at all happens (no key, no file, no state, no log line) while no app has an
    install-day file yet: the tab then reads "Not switched on yet". On any failure dashboard["value"] is removed and ONE
    line is printed: "ga4 value skipped: <ExcName>".
  * mark_notified_value: after send_alerts, like the Active tab's, over this tab's episodes.
  * update_fx_series: the ROAS step's best-effort dated USD rate series (one range call a day at most).

PRIVACY: nothing here prints except the error-type line; the counts line is build_static's (log_line).
"""

import hashlib
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

from .db import write_json_gz_stable
from .engine import value as val
from .fetch import ga4_uninstall as gu

STATE = "value_state.json"
PREFIX = "value_"
FILE_RE = re.compile(r"^value_[0-9a-f]{12}\.json\.gz$")
SPEND_FILE = "roas_spend_cache.json"
SPEND_OK_FILE = "roas_spend_fetch.json"   # {"ok_till": day}: the last day a Google Ads spend fetch went through
FX_FILE = "fx_series.json"
GEO_FILE = "roas_geo_cache.json"
FX_EVERY_SEC = 20 * 3600                  # the FX range call: at most once a ~day
FX_HOSTS = ("https://api.frankfurter.dev/v1/%s..%s?from=%s&to=USD",
            "https://api.frankfurter.app/%s..%s?from=%s&to=USD")
GEO_DAYS = 120                            # country cost days kept for the engine (≥ the 12-week country window)


def _default():
    return {"v": 1, "eval": {}, "episodes": {}, "closed": [], "portfolio_shape": {}}


def state_path(data_dir):
    return os.path.join(data_dir, gu.DIR, STATE)


def _ep_ok(e):
    return isinstance(e, dict) and isinstance(e.get("app_id"), str) and isinstance(e.get("family"), str) \
        and isinstance(e.get("last"), dict) and isinstance(e.get("dir"), str) and isinstance(e.get("id"), str) \
        and isinstance(e.get("opened"), str)


def load_state(data_dir):
    """The private value state; a default on a missing or broken file — never crashes. Malformed entries are dropped
    (the next save heals the file)."""
    st = _default()
    try:
        with open(state_path(data_dir), encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k in st and isinstance(v, type(st[k])):
                    st[k] = v
    except Exception:
        pass
    st["eval"] = {k: v for k, v in st["eval"].items() if isinstance(k, str) and isinstance(v, dict)}
    st["episodes"] = {k: v for k, v in st["episodes"].items() if isinstance(k, str) and _ep_ok(v)}
    st["closed"] = [e for e in st["closed"] if _ep_ok(e) and isinstance(e.get("closed"), str)]
    st["portfolio_shape"] = {k: v for k, v in st["portfolio_shape"].items()
                             if isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v)}
    return st


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


def cfg_from(s):
    """The settings the engine and this step read (by name; defaults = SPEC_AB_FINAL §3.4)."""
    s = s or {}
    h = s.get("value_payback_days", val.H_DEFAULT)
    try:
        h = int(h)
    except (TypeError, ValueError):
        h = val.H_DEFAULT
    return {"payback_days": h if h in val.H_ALLOWED else val.H_DEFAULT, "iap": bool(s.get("value_iap", False)),
            "cpi": s.get("value_cpi") or "blended", "deduct": bool(s.get("value_deduct", True)),
            "geo": bool(s.get("gads_geo", False)),
            # {Google Ads store id: AdMob app name} — the Marketing ROAS step's own join map (build_static hands it
            # over); None: the prepass rebuilds it the same way (engine.roas.store_owner)
            "store_owner": s.get("roas_store_owner") if isinstance(s.get("roas_store_owner"), dict) else None,
            # the last day this build's own Google Ads fetch went through (None: read data/roas_spend_fetch.json)
            "spend_ok_till": s.get("roas_spend_ok_till") if isinstance(s.get("roas_spend_ok_till"), str) else None}


# ── the install-day files (written by fetch.ga4_uninstall.fetch_iday / save_iday) ─────────────────

def iday_paths(data_dir, app_id):
    """(hot, old): the fetch module's own layout (gu.iday_path) — one definition, never a copy."""
    return gu.iday_path(data_dir, app_id), gu.iday_path(data_dir, app_id, old=True)


def has_iday(data_dir, app_id):
    return os.path.exists(gu.iday_path(data_dir, app_id))


def load_iday(data_dir, app_id):
    """The app's install-day data exactly as the fetch reads it back (gu.load_iday: the hot file with its frozen .old
    part merged in) → dict, or None (none yet / unreadable / an .old part of another stream or format — the fetch then
    starts that app over, so this tab never evaluates half a history)."""
    got = gu.load_iday(data_dir, app_id)
    return got if isinstance(got, dict) else None


# ── the prepass: spend, FX, deductions, the country cost cache ─────────────────────────────────

def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_spend(data_dir, ok_till=None):
    """The spend cache → {ccy, daily, installs, first, till}. till = the last day a Google Ads fetch went through
    (data/roas_spend_fetch.json, written by the ROAS step on a good fetch — or `ok_till` handed over by this build's
    own ROAS step), never simply the newest day with spend: the cache is kept as it was when a fetch fails, and a day
    after the last good fetch is "not in yet", never $0. Without that record (a first build), the newest day with spend."""
    raw = _load_json(os.path.join(data_dir, SPEND_FILE))
    if not isinstance(raw, dict) or raw.get("error") or not isinstance(raw.get("daily"), dict):
        return None
    dates = [d for dd in raw["daily"].values() for d in (dd or {})]
    ok = ok_till
    if not ok:
        rec = _load_json(os.path.join(data_dir, SPEND_OK_FILE))
        ok = rec.get("ok_till") if isinstance(rec, dict) and isinstance(rec.get("ok_till"), str) else None
    till = ok or (max(dates) if dates else None)
    return {"ccy": raw.get("currency_src") or "INR", "daily": raw["daily"], "installs": raw.get("installs") or {},
            "first": min(dates) if dates else None, "till": till, "till_src": "fetch" if ok else "max"}


def record_spend_fetch(data_dir, today):
    """The ROAS step, after a Google Ads spend fetch that went through: the last whole day it covers (today − 1) →
    data/roas_spend_fetch.json (written only on change). → that day (iso)."""
    day = today if isinstance(today, date) else date.fromisoformat(str(today)[:10])
    ok = (day - timedelta(days=1)).isoformat()
    path = os.path.join(data_dir, SPEND_OK_FILE)
    if (_load_json(path) or {}).get("ok_till") == ok:
        return ok
    os.makedirs(data_dir, exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"ok_till": ok}, f, sort_keys=True)
    os.replace(path + ".tmp", path)
    return ok


def _load_aliases(data_dir):
    raw = _load_json(os.path.join(os.path.dirname(data_dir) or ".", "config", "roas_app_aliases.json"))
    return {str(k).strip(): v for k, v in raw.items() if k and v} if isinstance(raw, dict) else {}


def _store_owner(data_dir, dashboard, aliases):
    """The ROAS join's store id → app name map, rebuilt from the same inputs (the cached app → store id list, the app
    catalog with its revenue, the aliases) when the ROAS step did not hand its own over."""
    from .engine.roas import store_owner
    raw = _load_json(os.path.join(data_dir, "app_store_ids.json")) or {}
    by_id = raw.get("by_id") if isinstance(raw, dict) else None
    return store_owner(by_id if isinstance(by_id, dict) else {}, (dashboard or {}).get("apps_catalog") or [], aliases)


def _load_fx(data_dir, dashboard, ccy):
    """{mode, now, series}: the dated series (data/fx_series.json) when there is one, else the build's one current
    rate (flag fx_one: "purane hafte aaj ke rate pe")."""
    now = None
    try:
        ui = (dashboard or {}).get("usd_inr")
        if ui and ccy == "INR":
            now = 1.0 / float(ui)
    except (TypeError, ValueError, ZeroDivisionError):
        now = None
    if now is None:
        c = _load_json(os.path.join(data_dir, "fx_cache.json")) or {}
        try:
            now = float(c.get(ccy)) if c.get(ccy) else None
        except (TypeError, ValueError):
            now = None
    raw = _load_json(os.path.join(data_dir, FX_FILE)) or {}
    ser = raw.get(ccy) if isinstance(raw, dict) else None
    ser = {k: float(v) for k, v in (ser or {}).items() if isinstance(k, str) and isinstance(v, (int, float)) and v}
    return {"mode": "dated" if ser else "one", "now": now, "series": ser}


def _ded_rates(dashboard):
    """A per-app deduction rate over the last 90 days, looked up by name (dashboard["deductions"]["by_app"] {app id or
    name: {rate_90d | rate}}). The deductions block today is per placement, not per app → {} (gross, with the note)."""
    d = (dashboard or {}).get("deductions") or {}
    by = d.get("by_app") if isinstance(d, dict) else None
    out = {}
    if isinstance(by, dict):
        for k, v in by.items():
            try:
                r = float((v or {}).get("rate_90d", (v or {}).get("rate")))
            except (TypeError, ValueError, AttributeError):
                continue
            if 0 <= r < 1:
                out[k] = {"rate": r, "src": "deductions"}
    return out


def _load_geo(data_dir):
    raw = _load_json(os.path.join(data_dir, GEO_FILE))
    return raw if isinstance(raw, dict) and isinstance(raw.get("daily"), dict) else None


def prepass(data_dir, apps, revenue, dashboard, cfg, st):
    """Once per build → the shared inputs, or None on any failure (the tab is then skipped this build)."""
    try:
        spend = _load_spend(data_dir, cfg.get("spend_ok_till"))
        aliases = _load_aliases(data_dir)
        owner = cfg.get("store_owner")
        if owner is None and spend:
            owner = _store_owner(data_dir, dashboard, aliases)
        return {"data_dir": data_dir, "spend": spend, "aliases": aliases, "owner": owner or {},
                "siblings": {x["same_pkg"]: [y["app_name"] for y in apps or [] if y.get("same_pkg") == x["same_pkg"]]
                             for x in apps or [] if x.get("same_pkg")},
                "fx": _load_fx(data_dir, dashboard, (spend or {}).get("ccy") or "INR"),
                "ded": _ded_rates(dashboard) if cfg.get("deduct", True) else {},
                "geo": _load_geo(data_dir) if cfg.get("geo") else None,
                "portfolio_shape": dict(st.get("portfolio_shape") or {})}
    except Exception:
        return None


def app_sids(pre, a, store, have):
    """The Google Ads store ids (of those in `have`) whose spend is this app's — the ROAS tab's map (see app_spend)."""
    owner = (pre or {}).get("owner") or {}
    pkg = a.get("package") or (store or {}).get("package")
    names = {str(a.get("app_name") or "")} | set(((pre or {}).get("siblings") or {}).get(pkg) or [])
    sids = {sid for sid in have if owner.get(sid) in names}
    return sids | {p for p in (a.get("package"), (store or {}).get("package")) if p and p in have and p not in owner}


def app_spend(pre, a, store):
    """The app's Google Ads spend + installs — exactly the store ids the Marketing ROAS tab gives this app (its
    store id → app name map: the app's own listing, or an alias naming it) and those of a second AdMob app on the same
    Play package (one GA4 stream), plus the app's own Play package when the ROAS tab could not place it at all
    ("unmatched"). A store id the ROAS tab gives ANOTHER app is never taken. None without a spend cache (unknown)."""
    sp = (pre or {}).get("spend")
    if not sp:
        return None
    sids = app_sids(pre, a, store, sp["daily"])
    daily, inst = {}, {}
    for sid in sorted(sids):
        for d, v in (sp["daily"].get(sid) or {}).items():
            daily[d] = daily.get(d, 0) + (v or 0)
        for d, v in (sp["installs"].get(sid) or {}).items():
            inst[d] = inst.get(d, 0) + (v or 0)
    return {"ccy": sp["ccy"], "daily": daily, "installs": inst, "first": sp["first"], "till": sp["till"],
            "sids": len(sids)}


def _app_geo(pre, a, store, fx, till):
    """Country cost per DAY (USD) of the GEO_DAYS days to `till` from the Google Ads country cache (GADS_GEO only) →
    {cc: {"daily": {day: [cost_usd, downloads]}}} — the engine sums exactly the days of the install weeks it divides
    by (never a 28-day cost over a 12-week install window)."""
    geo = (pre or {}).get("geo")
    if not geo or not till:
        return None
    rows = {}
    for p in sorted(app_sids(pre, a, store, geo.get("daily") or {})):
        for d, by in ((geo.get("daily") or {}).get(p) or {}).items():
            rows.setdefault(d, {})
            for cc, v in (by or {}).items():
                c = rows[d].setdefault(cc, [0, 0])
                c[0] += v[0] or 0
                c[1] += v[1] or 0
    if not rows:
        return None
    t = date.fromisoformat(till)
    f, _ = val._fx_fn(fx, (pre.get("spend") or {}).get("ccy") or "INR")
    out = {}
    for d, by in rows.items():
        dd = date.fromisoformat(d)
        if not (t - timedelta(days=GEO_DAYS - 1) <= dd <= t):
            continue
        r = f(dd)
        if r is None:
            continue
        for cc, (cost, dl) in by.items():
            e = out.setdefault(cc, {"daily": {}})
            e["daily"][d] = [cost / 1e6 * r, float(dl)]
    return out or None


# ── one app ─────────────────────────────────────────────────────────────────────────────────────

def _slice(st, aid):
    return {"eval": (st.get("eval") or {}).get(aid),
            "episodes": {k: e for k, e in (st.get("episodes") or {}).items() if e.get("app_id") == aid},
            "closed": [e for e in st.get("closed") or [] if e.get("app_id") == aid]}


def _put(st, aid, new):
    if new.get("eval") is None:
        st.setdefault("eval", {}).pop(aid, None)
    else:
        st.setdefault("eval", {})[aid] = new["eval"]
    st["episodes"] = dict({k: e for k, e in (st.get("episodes") or {}).items() if e.get("app_id") != aid},
                          **new["episodes"])
    st["closed"] = [e for e in st.get("closed") or [] if e.get("app_id") != aid] + list(new["closed"])


def snapshot(st, aid):
    return json.dumps(_slice(st, aid), sort_keys=True)


def restore_app(st, aid, snap):
    if snap is None:
        drop_app(st, aid)
        return
    _put(st, aid, json.loads(snap))


def drop_app(st, aid):
    """Forget one app's value state (its next evaluation is a first one: seeded, never a flood)."""
    _put(st, aid, {"eval": None, "episodes": {}, "closed": []})


def _sig(obj):
    return hashlib.sha1(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                        .encode("utf-8")).hexdigest()[:12]


def releases(udet):
    """The uninstall detail's releases, each with the Update impact block it belongs to (key: the "After vX" chip
    opens it), as the Active tab links them."""
    from .engine import impact as imp
    ups = ((udet or {}).get("impact") or {}).get("updates") or []
    out = []
    for r in (udet or {}).get("releases") or []:
        try:
            k = imp.rel_key(r)
            blk = next((u.get("key") for u in ups if k in (u.get("rel_keys") or [])), None)
        except Exception:
            blk = None
        out.append({"date": r.get("date"), "version": r.get("version"), "kind": r.get("kind"), "key": blk})
    return out


def app_step(store, a, udet, key, st, now_iso, rev, pre, cfg, out_dir, act_alerts=None, market=None):
    """One app: its install-day files → evaluate → value_<key>.json.gz → its summary row (alerts under "_alerts",
    its curve shape under "_shape": finish takes them off). An app without the files yet: a "wait" row, no file,
    its state untouched."""
    aid = a["app_id"]
    ida = load_iday(pre["data_dir"], aid)
    if ida is None:
        row = val._wait_row(aid, a["app_name"], key, None, None)
        row["_has"] = False
        return row
    spend = app_spend(pre, a, store)
    geo = _app_geo(pre, a, store, pre.get("fx"), ida.get("to")) if cfg.get("geo") else None
    ded = (pre.get("ded") or {}).get(aid) or (pre.get("ded") or {}).get(a["app_name"])
    detail, row, new = val.evaluate_app(store, ida, rev, spend, pre.get("fx"), releases(udet),
                                        _slice(st, aid), pre.get("portfolio_shape") or {}, cfg, now_iso,
                                        app_id=aid, app=a["app_name"], key=key, act_alerts=act_alerts, geo=geo,
                                        ded=ded, market=market)
    row["_has"] = True
    if detail is None:                                  # the file is there but holds no folded day yet
        row.setdefault("_alerts", [])
        return row
    detail["no_ads"] = spend is None or not spend.get("sids")
    name = PREFIX + key + ".json.gz"
    write_json_gz_stable(os.path.join(out_dir, name), detail)
    row.update(file=name, sig=_sig(detail))
    row["cty"]["gap_weeks"] = ((detail.get("countries") or {}).get("gap_weeks") or 0)
    row["organic"] = detail["no_ads"]
    _put(st, aid, new)
    return row


def error_row(a, key):
    """The row of an app whose value step failed (its state as before): shown as an error card."""
    return {"app_id": a["app_id"], "app": a["app_name"], "key": key, "file": None, "sig": None, "status": "error",
            "settled_till": None, "iday": None, "pay": None, "rpi": None, "cpi": None, "cty": None,
            "alerts": {"warning": 0, "watch": 0, "good": 0},
            "summary": {"kind": "error", "text": "Is app ka Install value hisaab abhi nahi ban paya — agle run me phir try hoga"},
            "s": {"spend4": None, "spend4_src": None, "n4": None, "nw": None, "rev7_4": None, "spend7_4": None,
                  "n7_4": None, "rev30_4": None, "n30_4": None, "spend30_4": None},
            "_has": True}


# ── the end of the step ─────────────────────────────────────────────────────────────────────────

def consts(cfg):
    out = dict(val.CONSTS)
    out.update(horizon=cfg["payback_days"], iap_in_payback=cfg["iap"], cpi_main=cfg["cpi"], deduct=cfg["deduct"],
               geo=cfg["geo"])
    return out


def _clean_files(out_dir, keep):
    try:
        names = os.listdir(out_dir)
    except OSError:
        return
    for f in names:
        if FILE_RE.match(f) and f not in keep:
            try:
                os.remove(os.path.join(out_dir, f))
            except OSError:
                pass


def finish(dashboard, out_dir, rows, pre, st, data_dir, no_ga4, cfg, status=None):
    """The end of the step: the portfolio curve shape + state saved, stale files removed, then dashboard["value"] LAST.
    Never raises: a failure removes dashboard["value"] and prints the error type only. Without any install-day file
    yet nothing is written, set or printed."""
    try:
        if not any(r.get("_has") for r in rows):
            _clean_files(out_dir, set())
            dashboard.pop("value", None)
            return
        alerts = val.sort_alerts([al for r in rows for al in (r.pop("_alerts", None) or [])])
        shapes = [r.pop("_shape", None) for r in rows]
        for r in rows:
            r.pop("_alerts", None)
            r.pop("_shape", None)
            r.pop("_has", None)
        ps = val.portfolio_shape([s for s in shapes if s])
        st["portfolio_shape"] = ps or st.get("portfolio_shape") or {}
        save_state(data_dir, st)
        _clean_files(out_dir, {r["file"] for r in rows if r.get("file")})
        c = consts(cfg)
        ok = [r for r in rows if r["status"] == "ok"]
        cnt = {"apps": len(rows), "with_spend": sum(1 for r in ok if not r.get("organic")),
               "organic": sum(1 for r in ok if r.get("organic")),
               "iday": {"wait": sum(1 for r in rows if r["status"] == "wait"),
                        "filling": sum(1 for r in ok if (r.get("iday") or {}).get("state") == "filling"),
                        "whole": sum(1 for r in ok if (r.get("iday") or {}).get("state") == "whole")},
               "cty": {"sampled": sum(1 for r in ok if (r.get("cty") or {}).get("smp")),
                       "gap_weeks": sum(((r.get("cty") or {}).get("gap_weeks") or 0) for r in ok)},
               "geo": {"on": sum(1 for r in ok if (r.get("cty") or {}).get("geo")),
                       "off": sum(1 for r in ok if not (r.get("cty") or {}).get("geo"))},
               "errors": sum(1 for r in rows if r["status"] == "error")}
        for r in rows:
            r.pop("organic", None)
            if isinstance(r.get("cty"), dict):
                r["cty"].pop("gap_weeks", None)
        ac = {"warning": 0, "watch": 0, "good": 0}
        for al in alerts:
            ac[al["severity"]] = ac.get(al["severity"], 0) + 1
        stl = sorted(r["settled_till"] for r in ok if r.get("settled_till"))
        if not rows:
            stt = "error"
        elif cnt["errors"] or status == "partial":
            stt = "partial"
        else:
            stt = "ok"
        asset_v = _sig({"sigs": sorted(r.get("sig") or "" for r in rows), "consts": c})
        dashboard["value"] = {"v": val.VALUE_V, "status": stt, "asset_v": asset_v, "horizon": cfg["payback_days"],
                              "spend_ccy": ((pre or {}).get("spend") or {}).get("ccy"),
                              "settled_till_min": stl[0] if stl else None, "settled_till_max": stl[-1] if stl else None,
                              "counts": cnt, "consts": c, "alerts": alerts, "alert_counts": ac,
                              "no_ga4": [{"app_id": n["app_id"], "app": n["app"], "text": n["text"]}
                                         for n in no_ga4 or []],
                              "apps": rows}
    except Exception as e:
        dashboard.pop("value", None)
        print("ga4 value skipped: %s" % type(e).__name__, file=sys.stderr)


def mark_notified_value(data_dir, summary, dry, now=None, ids=None):
    """After send_alerts: the value alerts that were due and went out (`ids` = build_static.uninstall_delivered; None
    = all of them) are sent — or, in a dry run, counted as sent — and never sent again for the same episode."""
    due = {a["id"] for a in (summary or {}).get("alerts") or [] if a.get("notify")}
    ids = due if ids is None else due & set(ids)
    if not ids:
        return 0
    now_iso = gu._now_iso(now or datetime.now(timezone.utc))
    st = load_state(data_dir)
    n = 0
    for ep in st["episodes"].values():
        if ep.get("id") in ids and ep.get("notified_at") is None:
            ep["notified_at"], ep["notified_dry"] = now_iso, bool(dry)
            n += 1
    save_state(data_dir, st)
    return n


def log_line(summary):
    """The public build log's ONE value line — counts only (no names, ids, packages, money, countries or dates)."""
    c = summary["counts"]
    al = summary["alerts"]
    return ("ga4 value: apps %d, with ads %d, organic %d, install-day data %d (whole %d, filling %d, waiting %d), "
            "country sampled %d, country weeks not clean %d, country cost %s, open alerts %d (new %d), errors %d"
            % (c["apps"], c["with_spend"], c["organic"], c["iday"]["whole"] + c["iday"]["filling"], c["iday"]["whole"],
               c["iday"]["filling"], c["iday"]["wait"], c["cty"]["sampled"], c["cty"]["gap_weeks"],
               "on" if c["geo"]["on"] else "off", len(al), sum(1 for a in al if a.get("notify")), c["errors"]))


def files(dashboard):
    """The tab's lazy per-app files (for _headers: never served from a stale cache)."""
    return [r["file"] for r in (dashboard.get("value") or {}).get("apps", []) if r.get("file")]


# ── the dated FX series (build_static's ROAS step; best effort) ──────────────────────────────────

def update_fx_series(data_dir, ccy, start, today, get=None, now=None):
    """Extend data/fx_series.json {ccy: {day: USD per unit}} from its last stored day (else `start`) to `today` with
    ONE frankfurter range call, at most once every ~20 h. Weekends / holidays are simply absent (the engine takes the
    previous business day). → the number of days added (0: nothing to do). Raises on a failed call (the caller
    prints the error type only)."""
    if not ccy or ccy == "USD" or not start:
        return 0
    path = os.path.join(data_dir, FX_FILE)
    raw = _load_json(path)
    raw = raw if isinstance(raw, dict) else {}
    ser = dict(raw.get(ccy) or {})
    t = now if now is not None else time.time()
    if ser and t - float(raw.get("_ts") or 0) < FX_EVERY_SEC:
        return 0
    first = (date.fromisoformat(max(ser)) + timedelta(days=1)) if ser else date.fromisoformat(str(start)[:10])
    today = today if isinstance(today, date) else date.fromisoformat(str(today)[:10])
    if first > today:
        return 0
    if get is None:
        import requests
        get = requests.get
    got, err = None, None
    for url in FX_HOSTS:
        try:
            r = get(url % (first.isoformat(), today.isoformat(), ccy), timeout=15)
            rates = (r.json() or {}).get("rates") or {}
            got = {d: float(v["USD"]) for d, v in rates.items() if isinstance(v, dict) and v.get("USD")}
            break
        except Exception as e:
            err = e
    if got is None:
        raise err or RuntimeError("fx")
    n = sum(1 for d in got if d not in ser)
    ser.update(got)
    raw[ccy] = dict(sorted(ser.items()))
    raw["_ts"] = int(t)
    os.makedirs(data_dir, exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(raw, f, sort_keys=True, separators=(",", ":"))
    os.replace(path + ".tmp", path)
    return n
