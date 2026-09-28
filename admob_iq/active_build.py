"""GA4 "👥 Active users" tab — the build step, called from uninstall_build.run_uninstall (one store in memory at a time).

  * load_state / save_state: this tab's PRIVATE state, data/ga4_uninstall/active_state.json = {v, eval, episodes,
    closed, portfolio_edge}. Its own file, not a key inside state.json: gu.load_state keeps only the keys of
    _state_default(), so refresh_all / mark_notified would drop it every hour (every build a "first evaluation").
  * market_prepass: which recent weeks moved eCPM the same way on most GA4 apps (from the revenue input only).
  * app_step: engine.active.evaluate for one app right after the uninstall evaluation (its detail read, never changed)
    → writes active_<key>.json.gz (deterministic, rewritten only on change) → the summary row.
  * finish: at the very end of run_uninstall — the portfolio edge, the state, stale files, the portfolio's daily file
    (active_portfolio.json.gz: every app's own daily arrays + their day-by-day sums, lazy — the summary gets only a
    pointer), then dashboard["active"] LAST. On any failure dashboard["active"] is removed and ONE line is printed:
    "ga4 active skipped: <ExcName>". The daily file alone failing costs only that file ("portfolio": null and ONE line,
    "ga4 active portfolio skipped: <ExcName>").
  * mark_notified_active: after send_alerts, like uninstall_build.mark_notified, over this tab's episodes.

PRIVACY: nothing here prints except that one error-type line; the counts line is build_static's (log_line).
"""

import copy
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

from .db import write_json_gz_stable
from .engine import active as act
from .engine import impact as imp
from .fetch import ga4_uninstall as gu

STATE = "active_state.json"
PREFIX = "active_"
FILE_RE = re.compile(r"^active_[0-9a-f]{12}\.json\.gz$")
PORT_FILE = "active_portfolio.json.gz"          # the All-apps "📅 Daily" series (never matches FILE_RE)


def _default():
    return {"v": 1, "eval": {}, "episodes": {}, "closed": [], "portfolio_edge": None}


def state_path(data_dir):
    return os.path.join(data_dir, gu.DIR, STATE)


def _ep_ok(e):
    return isinstance(e, dict) and isinstance(e.get("app_id"), str) and isinstance(e.get("family"), str) \
        and isinstance(e.get("last"), dict) and isinstance(e.get("dir"), str) and isinstance(e.get("id"), str)


def load_state(data_dir):
    """The private Active state; a default on a missing or broken file — never crashes. A malformed entry inside it
    (an episode / closed entry / app evaluation that is not what this code writes) is dropped, so the next save heals
    the file instead of breaking every run."""
    st = _default()
    try:
        with open(state_path(data_dir), encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k in st and (st[k] is None or isinstance(v, type(st[k]))):
                    st[k] = v
    except Exception:
        pass
    st["eval"] = {k: v for k, v in st["eval"].items() if isinstance(k, str) and isinstance(v, dict)}
    st["episodes"] = {k: v for k, v in st["episodes"].items() if isinstance(k, str) and _ep_ok(v)}
    st["closed"] = [e for e in st["closed"] if _ep_ok(e)]
    if st["portfolio_edge"] is not None and not isinstance(st["portfolio_edge"], str):
        st["portfolio_edge"] = None
    return st


def save_state(data_dir, st):
    """Sorted JSON, written only when it changed (like gu.save_state). → True when written."""
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


def cfg_from(s, ucfg=None):
    """The settings the engine reads."""
    return {"retention_changed": (s or {}).get("ga4_retention_changed"),
            "late_un": (ucfg or {}).get("late_days", 7)}


def market_prepass(revenue, apps, app_revenue):
    """Every GA4 app's AdMob revenue → engine.active.market, or None (on any failure: the rows carry no tag)."""
    try:
        if not revenue:
            return None
        revs = []
        for a in apps:
            if a.get("same_as"):
                continue
            r = app_revenue(revenue, a, apps)
            if r and r.get("days"):
                revs.append(r["days"])
        return act.market(revs, revenue.get("till") or max(max(d) for d in revs))
    except Exception:
        return None


def snapshot(st, aid):
    """This app's Active state as it was (restore_app puts it back when its step fails)."""
    return (json.dumps((st.get("eval") or {}).get(aid), sort_keys=True),
            copy.deepcopy({k: e for k, e in (st.get("episodes") or {}).items() if e.get("app_id") == aid}),
            copy.deepcopy([e for e in st.get("closed") or [] if e.get("app_id") == aid]))


def drop_app(st, aid):
    """Forget one app's Active state (its next evaluation is a first one: seeded, never a flood)."""
    st.setdefault("eval", {}).pop(aid, None)
    st["episodes"] = {k: e for k, e in (st.get("episodes") or {}).items()
                      if not (isinstance(e, dict) and e.get("app_id") == aid)}
    st["closed"] = [e for e in st.get("closed") or [] if not (isinstance(e, dict) and e.get("app_id") == aid)]


def restore_app(st, aid, snap):
    if snap is None:                                 # the snapshot itself failed: nothing to put back
        drop_app(st, aid)
        return
    ev, eps, closed = snap
    ev = json.loads(ev)
    if ev is None:
        st.setdefault("eval", {}).pop(aid, None)
    else:
        st.setdefault("eval", {})[aid] = ev
    st["episodes"] = dict({k: e for k, e in (st.get("episodes") or {}).items() if e.get("app_id") != aid}, **eps)
    st["closed"] = [e for e in st.get("closed") or [] if e.get("app_id") != aid] + closed


def _sig(obj):
    return hashlib.sha1(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                        .encode("utf-8")).hexdigest()[:12]


def app_step(store, a, udet, key, st, now_iso, rev, market, stale, outdated, cfg, out_dir):
    """One app: evaluate, write its lazy file, → its summary row (with its alerts under "_alerts", taken off by
    finish)."""
    detail, row = act.evaluate(store, a["app_id"], a["app_name"], st, now_iso, udet, key, rev, market, stale=stale,
                               outdated=outdated, late_un=cfg.get("late_un", 7), cfg=cfg)
    name = PREFIX + key + ".json.gz"
    write_json_gz_stable(os.path.join(out_dir, name), detail)
    row.update(file=name, sig=_sig(detail))
    try:                                             # its slice of the All-apps daily series (a failure costs only
        row["_port"] = act.portfolio_part(detail)    # that slice: the app is listed as missing there)
    except Exception:
        row["_port"] = False
    row["_alerts"] = detail["changes"]["open"]
    row["_ret_from"] = detail["edges"]["ret_from"] if detail["edges"]["ret_state"] == "found" else None
    return row


def error_row(a, key):
    """The row of an app whose Active step failed (its Active state as before): shown as an error card."""
    return {"app_id": a["app_id"], "app": a["app_name"], "key": key, "file": None, "sig": None, "status": "error",
            "data_till": None, "settled_till": None, "stale": False, "stage": None, "launch_day": None, "ready": False,
            "edges": None, "win": None, "m": {}, "ctx": None, "latest": None,
            "alerts": {"warning": 0, "watch": 0, "good": 0},
            "summary": {"kind": "error", "text": "Is app ka Active users hisaab abhi nahi ban paya — agle run me phir try hoga"}}


def consts(cfg):
    out = dict(act.CONSTS)
    rc = act.retention_date(cfg.get("retention_changed"))
    out.update(retention_changed=rc.isoformat() if rc else None, impact=dict(imp.CONSTS))
    return out


def portfolio_step(out_dir, parts):
    """The All-apps daily series → active_portfolio.json.gz (deterministic, rewritten only on change) → the pointer for
    dashboard["active"]["portfolio"] = {file, sig, from, to, days, apps, missing, settled_till}. parts = [(row, its
    slice: a dict, None = no day with active users, False = the slice failed)]. Never raises: on a failure the old file
    is removed (a stale series never ships), ONE error-type line is printed and the pointer is None."""
    try:
        miss = [{"app_id": r.get("app_id"), "app": r.get("app"),
                 "why": "no_data" if p is None and r.get("status") == "ok" else "error"} for r, p in parts if not p]
        body = act.portfolio([p for _, p in parts if p], miss)
        write_json_gz_stable(os.path.join(out_dir, PORT_FILE), body)
        return {"file": PORT_FILE, "sig": _sig(body), "from": body["from"], "to": body["to"],
                "days": len((body["total"] or {}).get("n") or []), "apps": len(body["apps"]), "missing": len(miss),
                "settled_till": body["settled_till"]}
    except Exception as e:
        try:
            os.remove(os.path.join(out_dir, PORT_FILE))
        except OSError:
            pass
        print("ga4 active portfolio skipped: %s" % type(e).__name__, file=sys.stderr)
        return None


def finish(dashboard, out_dir, rows, market, st, data_dir, no_ga4, cfg, status=None):
    """The end of the step: portfolio edge + state saved, stale files removed, the All-apps daily file, then
    dashboard["active"] LAST. Never raises: a failure removes dashboard["active"] and prints the error type only."""
    try:
        parts = [(r, r.pop("_port", None)) for r in rows]
        alerts = act.sort_alerts([al for r in rows for al in r.pop("_alerts", [])])
        edges = sorted(r.pop("_ret_from") for r in rows if r.get("_ret_from"))
        for r in rows:
            r.pop("_alerts", None)
            r.pop("_ret_from", None)
        st["portfolio_edge"] = edges[len(edges) // 2] if edges else st.get("portfolio_edge")
        save_state(data_dir, st)
        keep = {r["file"] for r in rows if r.get("file")}
        for f in os.listdir(out_dir):
            if FILE_RE.match(f) and f not in keep:
                try:
                    os.remove(os.path.join(out_dir, f))
                except OSError:
                    pass
        c = consts(cfg)
        ok = [r for r in rows if r["status"] == "ok"]
        cnt = {"apps": len(rows), "ready": sum(1 for r in ok if r["ready"]),
               "low": sum(1 for r in ok if not r["ready"]), "stale": sum(1 for r in ok if r["stale"]),
               "errors": len(rows) - len(ok),
               "ret": dict.fromkeys(("wait", "searching", "found", "whole", "unverified"), 0),
               "usage": dict.fromkeys(("wait", "ok", "partial"), 0),
               "revenue": dict.fromkeys(("ok", "partial", "none"), 0)}
        for r in ok:
            cnt["ret"][r["edges"]["ret_state"]] += 1
            cnt["usage"][r["edges"]["usage_state"]] += 1
            cnt["revenue"][r["edges"]["rev_state"]] += 1
        ac = {"warning": 0, "watch": 0, "good": 0}
        for al in alerts:
            if not al.get("linked"):                   # the same change as an open Update impact alert: counted
                ac[al["severity"]] = ac.get(al["severity"], 0) + 1   # there (the Alerts badge counts it once)
        till = sorted(r["data_till"] for r in ok)
        stl = sorted(r["settled_till"] for r in ok)
        if not rows:
            stt = "error"
        elif ok and all(r["stale"] for r in ok):
            stt = "stale"
        elif len(ok) < len(rows) or status == "partial":
            stt = "partial"
        else:
            stt = "ok"
        asset_v = hashlib.sha1(json.dumps({"sigs": sorted(r["sig"] or "" for r in rows), "consts": c},
                                          sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]
        out = {"v": 1, "status": stt, "asset_v": asset_v,
               "data_till_min": till[0] if till else None, "data_till_max": till[-1] if till else None,
               "settled_till_min": stl[0] if stl else None, "settled_till_max": stl[-1] if stl else None,
               "counts": cnt, "consts": c, "market": market or {"weeks": [], "latest": None},
               "alerts": alerts, "alert_counts": ac,
               "no_ga4": [{"app_id": n["app_id"], "app": n["app"], "text": n["text"]} for n in no_ga4 or []],
               "portfolio": portfolio_step(out_dir, parts), "apps": rows}
        dashboard["active"] = out
    except Exception as e:
        dashboard.pop("active", None)
        print("ga4 active skipped: %s" % type(e).__name__, file=sys.stderr)


def mark_notified_active(data_dir, summary, dry, now=None, ids=None):
    """After send_alerts: the Active alerts that were due and went out (`ids` = build_static.uninstall_delivered; None =
    all of them) are sent — or, in a dry run, counted as sent — and never sent again for the same episode."""
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
    """The public build log's ONE Active line — counts only (no names, ids, packages or dates)."""
    c = summary["counts"]
    r = c["ret"]
    al = summary["alerts"]
    return ("ga4 active: apps %d, ready %d, low data %d, return data %d (edge found %d, searching %d, waiting %d, "
            "unverified %d), sessions data %d, revenue %d, open alerts %d (new %d), market-wide %s, errors %d"
            % (c["apps"], c["ready"], c["low"], r["found"] + r["whole"] + r["searching"] + r["unverified"],
               r["found"] + r["whole"], r["searching"], r["wait"], r["unverified"],
               c["usage"]["ok"] + c["usage"]["partial"], c["revenue"]["ok"] + c["revenue"]["partial"], len(al),
               sum(1 for a in al if a.get("notify")), "yes" if (summary.get("market") or {}).get("latest") else "no",
               c["errors"]))
