"""One-off Google Ads INSTALL probe, run by .github/workflows/gads-inst-probe.yml: before the First open tab may show
"installed but never opened" (owner, 2 Nov 2026), measure per app what Google Ads counts for its app campaigns, every
conversion action apart and the secondary ones too (all_conversions): the Play installs (GOOGLE_PLAY_DOWNLOAD /
ANDROID_INSTALLS_ALL_OTHER_APPS — Google Play's own count) against the Firebase first opens (FIREBASE_ANDROID_FIRST_OPEN),
by day and by country. Where an app's campaigns bid on first_open, the build's "Google Ads installs"
(biddable_app_install_conversions) ARE first opens — this says whether a Play count exists beside them. READ-ONLY
against Google Ads (the build's own secrets, as gads_geo_probe); nothing is changed in any account and nothing in data/
or site/ is touched.

Window: the last DAYS (28) complete UTC days (gads_geo_probe.window; the account's days).

Per account under the MCC (gads_geo_probe's roster; WORKERS accounts in parallel, one request at a time per account):
  INST   google_ads._app_installs_for — the build's installs (biddable_app_install_conversions)
  CA     conversion_action: id, type, category, app id, status, included in conversions, primary for goal (once more
         without the app id and the two flags on an HTTP 400)
  CONV   campaign × day × conversion action: all_conversions, conversions (MULTI_CHANNEL)
  GEO    geographic_view (LOCATION_OF_PRESENCE) × day × conversion action: all_conversions (MULTI_CHANNEL; the channel
         selected too — Google refuses a WHERE on a field the SELECT lacks: EXPECTED_REFERENCED_FIELD_IN_SELECT_CLAUSE)
An account whose INST came back with no row asks only CA; one refused as not enabled (HTTP 403) asks nothing more.
Once: the roster and the country map (gads_geo_probe.g5_map).

Output ga4/gads_inst_probe.json in the PRIVATE repo:
  "stores"[store]  days[date] = {"inst": biddable installs, "t": {type: [all_conversions, conversions]}};
                   cc[ISO-2 | "id:<criterion id>" | "none"] = {type: all_conversions over the window}
  "summary"        per store: inst, t {type: [all_conversions, conversions]}, geo {type: Σ countries}, play (Σ the
                   Play types' all_conversions), first_open, ratio (first_open ÷ play); stores with a Play count / with
                   first opens / both
  "accounts"[id]   ccy, tz, ca {type: [actions, included]}, calls[kind] = {n, rows, sec, err | stop}, stopped
PUBLIC LOG: progress counts and ONE line of counts only (no ids, names, dates, install numbers or ratios).
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from admob_iq.fetch import gads_geo_probe as gp
from admob_iq.fetch import google_ads as gads
from admob_iq.fetch.ga4_d1d7_probe import _dump, _int, _safely, write_private

OUT_PATH = "ga4/gads_inst_probe.json"
WORKERS = 4
BUDGET_SEC = 12 * 60
MAX_CALLS = 400
PLAY = ("GOOGLE_PLAY_DOWNLOAD", "ANDROID_INSTALLS_ALL_OTHER_APPS")
FIRST_OPEN = "FIREBASE_ANDROID_FIRST_OPEN"

Q_CA = ("SELECT conversion_action.id, conversion_action.type, conversion_action.category, conversion_action.app_id, "
        "conversion_action.status, conversion_action.include_in_conversions_metric, "
        "conversion_action.primary_for_goal FROM conversion_action")
Q_CA_MIN = "SELECT conversion_action.id, conversion_action.type, conversion_action.category FROM conversion_action"
Q_CONV = ("SELECT campaign.id, campaign.app_campaign_setting.app_id, segments.date, segments.conversion_action, "
          "metrics.all_conversions, metrics.conversions FROM campaign "
          "WHERE segments.date BETWEEN '{a}' AND '{b}' AND campaign.advertising_channel_type = 'MULTI_CHANNEL'")
Q_GEO = ("SELECT campaign.app_campaign_setting.app_id, campaign.advertising_channel_type, "
         "geographic_view.country_criterion_id, "
         "geographic_view.location_type, segments.date, segments.conversion_action, metrics.all_conversions "
         "FROM geographic_view WHERE segments.date BETWEEN '{a}' AND '{b}' "
         "AND campaign.advertising_channel_type = 'MULTI_CHANNEL' "
         "AND geographic_view.location_type = 'LOCATION_OF_PRESENCE'")


class Run(gp.Run):
    def pulse(self):
        with self.lock:
            now = self.clock()
            beat = now - self.beat >= gp.HEARTBEAT_SEC
            if beat:
                self.beat = now
            n, s = self.calls, int(now - self.t0)
        if beat:
            self.say("gads inst progress: calls %d, %ds" % (n, s))


def _act(row):
    """segments.conversion_action (customers/…/conversionActions/<id>) → <id>."""
    v = str((row.get("segments") or {}).get("conversionAction") or "")
    return v.rsplit("/", 1)[-1] if v else ""


def ca_map(rows):
    """CA rows → {action id: {type, category, app, status, inc, primary}}."""
    out = {}
    for r in rows or []:
        c = r.get("conversionAction") or {}
        if c.get("id") in (None, ""):
            continue
        out[str(c["id"])] = {"type": c.get("type") or "?", "category": c.get("category") or "?",
                             "app": gads._norm_store(c.get("appId")) or None, "status": c.get("status"),
                             "inc": c.get("includeInConversionsMetric"), "primary": c.get("primaryForGoal")}
    return out


def ca_counts(acts):
    """{type: [actions, included in conversions]} over the actions that are not REMOVED."""
    out = {}
    for c in acts.values():
        if c.get("status") == "REMOVED":
            continue
        e = out.setdefault(c["type"], [0, 0])
        e[0] += 1
        e[1] += 1 if c.get("inc") is True else 0
    return out


def fold(inst, conv, geo, acts, iso):
    """One account's rows → {"days": {store: {date: {inst, t: {type: [all, conv]}}}}, "cc": {store: {country: {type:
    all}}}}; an action the CA read did not name is "?"."""
    days, cc = {}, {}

    def day(sid, d):
        return days.setdefault(sid, {}).setdefault(d, {"inst": 0.0, "t": {}})

    def typ(r):
        return (acts.get(_act(r)) or {}).get("type") or "?"

    for r in inst or []:
        if r.get("store_id") and r.get("date"):
            day(r["store_id"], r["date"])["inst"] += float(r.get("installs") or 0)
    for r in conv or []:
        sid, d = gp._sid(r), gp._date(r)
        if not sid or not d:
            continue
        v = day(sid, d)["t"].setdefault(typ(r), [0.0, 0.0])
        v[0] += float(gp._met(r, "allConversions") or 0)
        v[1] += float(gp._met(r, "conversions") or 0)
    for r in geo or []:
        sid = gp._sid(r)
        if not sid:
            continue
        k = gp._ccid(r.get("geographicView"))
        key = (iso or {}).get(k) or ("id:%s" % k if k else "none")
        e = cc.setdefault(sid, {}).setdefault(key, {})
        t = typ(r)
        e[t] = e.get(t, 0.0) + float(gp._met(r, "allConversions") or 0)
    return {"days": days, "cc": cc}


def probe_account(run, ctx, acct):
    """Every request of one account, one at a time → its record (calls, currency, zone, CA counts) + "_fold"."""
    aid = acct["id"]
    rec = {"ccy": acct.get("currency") or "USD", "tz": acct.get("tz"), "calls": {}}
    mcc, dev, tok, a, b = ctx["mcc"], ctx["dev"], ctx["token"], ctx["start"], ctx["end"]

    def ask(kind, fn):
        return gp._call(run, rec, kind, fn)

    inst = ask("INST", lambda: gads._app_installs_for(aid, mcc, dev, tok, a, b))
    if inst is None and ((rec["calls"].get("INST") or {}).get("err") or {}).get("http") == 403:
        rec["not_enabled"] = True
        return rec
    ca = ask("CA", lambda: gads._search(aid, mcc, dev, tok, Q_CA))
    if ca is None and ((rec["calls"]["CA"].get("err") or {}).get("http") == 400):
        ca = ask("CA_MIN", lambda: gads._search(aid, mcc, dev, tok, Q_CA_MIN))
    conv = geo = None
    if inst == []:
        rec["no_installs"] = True
    else:
        conv = ask("CONV", lambda: gads._search(aid, mcc, dev, tok, Q_CONV.format(a=a, b=b)))
        geo = ask("GEO", lambda: gads._search(aid, mcc, dev, tok, Q_GEO.format(a=a, b=b)))
    acts = _safely(ca_map, ca, fallback={}) if ca is not None else {}
    rec["ca"] = _safely(ca_counts, acts, fallback={})
    rec["_fold"] = _safely(fold, inst, conv, geo, acts, ctx.get("iso"), fallback=None)
    return rec


def _r2(v):
    return round(float(v or 0), 2)


def merge(accts):
    """Every account's fold → stores {store: {"days": {date: {inst, t}}, "cc": {country: {type: all}}}} (2 decimals)."""
    stores = {}
    for a in accts.values():
        f = a.get("_fold") or {}
        for sid, dd in (f.get("days") or {}).items():
            s = stores.setdefault(sid, {"days": {}, "cc": {}})
            for d, x in dd.items():
                y = s["days"].setdefault(d, {"inst": 0.0, "t": {}})
                y["inst"] += x.get("inst") or 0
                for t, v in (x.get("t") or {}).items():
                    w = y["t"].setdefault(t, [0.0, 0.0])
                    w[0] += v[0]
                    w[1] += v[1]
        for sid, cc in (f.get("cc") or {}).items():
            s = stores.setdefault(sid, {"days": {}, "cc": {}})
            for c, tv in cc.items():
                e = s["cc"].setdefault(c, {})
                for t, v in tv.items():
                    e[t] = e.get(t, 0.0) + v
    for s in stores.values():
        for y in s["days"].values():
            y["inst"] = _r2(y["inst"])
            y["t"] = {t: [_r2(v[0]), _r2(v[1])] for t, v in y["t"].items()}
        s["cc"] = {c: {t: _r2(v) for t, v in tv.items()} for c, tv in s["cc"].items()}
    return stores


def summary(stores):
    """Per store over the window: biddable installs, every type [all, conv] (campaign rows) and Σ countries (geo rows),
    the Play count, the first opens and first opens ÷ Play; how many stores have each."""
    per = {}
    for sid, s in stores.items():
        t, geo, inst = {}, {}, 0.0
        for y in s["days"].values():
            inst += y["inst"]
            for k, v in y["t"].items():
                w = t.setdefault(k, [0.0, 0.0])
                w[0] += v[0]
                w[1] += v[1]
        for tv in s["cc"].values():
            for k, v in tv.items():
                geo[k] = geo.get(k, 0.0) + v
        play = sum(t.get(k, [0.0])[0] for k in PLAY)
        fo = t.get(FIRST_OPEN, [0.0])[0]
        per[sid] = {"inst": _r2(inst), "t": {k: [_r2(v[0]), _r2(v[1])] for k, v in t.items()},
                    "geo": {k: _r2(v) for k, v in geo.items()}, "play": _r2(play), "first_open": _r2(fo),
                    "ratio": round(fo / play, 4) if play else None, "countries": len(s["cc"])}
    return {"stores": per, "with_play": sum(1 for x in per.values() if x["play"] > 0),
            "with_first_open": sum(1 for x in per.values() if x["first_open"] > 0),
            "both": sum(1 for x in per.values() if x["play"] > 0 and x["first_open"] > 0)}


def counts(rep, run):
    """The public counts (no ids, names, dates, install numbers or ratios)."""
    accts = rep["accounts"]

    def ok_of(*kinds):
        of = sum(1 for a in accts.values() if any(gp._asked(a, k) for k in kinds[:1]))
        ok = sum(1 for a in accts.values() if any(gp._ok(a, k) for k in kinds))
        return ok, of
    s = rep.get("summary") or {}
    inst, ca, conv, geo = ok_of("INST"), ok_of("CA", "CA_MIN"), ok_of("CONV"), ok_of("GEO")
    return {"accounts": sum(1 for a in accts.values() if gp._asked(a, "INST")), "of": rep["once"].get("accounts", 0),
            "calls": run.calls, "errors": run.errors, "inst_ok": inst[0], "inst_of": inst[1], "ca_ok": ca[0],
            "ca_of": ca[1], "conv_ok": conv[0], "conv_of": conv[1], "geo_ok": geo[0], "geo_of": geo[1],
            "stores": len(rep.get("stores") or {}), "with_play": _int(s.get("with_play")),
            "with_first_open": _int(s.get("with_first_open")), "both": _int(s.get("both")),
            "stopped": 1 if run.stop else 0, "seconds": run.elapsed()}


COUNT_KEYS = ("accounts", "of", "calls", "errors", "inst_ok", "inst_of", "ca_ok", "ca_of", "conv_ok", "conv_of",
              "geo_ok", "geo_of", "stores", "with_play", "with_first_open", "both", "stopped", "seconds")


def public_line(c):
    return ("gads inst probe: accounts %d/%d, calls %d, errors %d, installs accepted %d/%d, conversion actions accepted "
            "%d/%d, per-action conversions accepted %d/%d, per-country accepted %d/%d, stores %d, with a Play count %d, "
            "with first opens %d, both %d, stopped %d, %ds" % tuple(_int((c or {}).get(k)) for k in COUNT_KEYS))


def run_probe(s, token, now=None, budget=BUDGET_SEC, clock=time.monotonic, workers=WORKERS, max_accounts=0,
              tick=gp.TICK_SEC):
    """Probe every child account of the MCC → the report (dict). Never raises for one account's failure; prints
    counts-only progress."""
    run = Run(budget, clock, MAX_CALLS)
    now = now or datetime.now(timezone.utc)
    win = gp.window(now)
    mcc = str(s["google_ads_login_customer_id"]).replace("-", "")
    ctx = {"mcc": mcc, "dev": s["google_ads_dev_token"], "token": token, "start": win["start"], "end": win["end"]}
    once, rrec, accts = {}, {"calls": {}}, {}
    with gp.Beat(run, tick):
        roster = gp._call(run, rrec, "ROSTER", lambda: gads._child_accounts(mcc, ctx["dev"], token))
        once["ROSTER"] = {"ok": roster is not None, "err": rrec["calls"]["ROSTER"].get("err")}
        accounts = sorted(roster or [], key=lambda a: a["id"])
        once["accounts"] = len(accounts)
        if max_accounts and max_accounts > 0:
            accounts = accounts[:max_accounts]
        run.say("gads inst probe: %d account(s) to probe" % len(accounts))
        ctx["iso"] = gp._try(gp.g5_map, run, once, ctx, accounts[0]["id"] if accounts else None, default={}) \
            if roster is not None else {}

        def one(a):
            try:
                accts[a["id"]] = probe_account(run, ctx, a)
            except Exception as e:                   # a bug for one account must not cost the others
                accts[a["id"]] = {"ccy": a.get("currency") or "USD", "tz": a.get("tz"), "calls": {},
                                  "crash": type(e).__name__}

        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            list(ex.map(one, accounts))
    stores = _safely(merge, accts, fallback={})
    rep = {"v": 1, "kind": "gads_inst_probe", "at": now.isoformat(), "api": gads.API_VERSION, "window": win,
           "params": {"play": list(PLAY), "first_open": FIRST_OPEN, "budget_sec": budget, "max_calls": run.max_calls,
                      "max_accounts": max_accounts or 0},
           "once": once, "accounts": accts, "stores": stores, "iso": ctx["iso"], "stopped": run.stop}
    rep["summary"] = _safely(summary, stores)
    rep["counts"] = counts(rep, run)
    for a in accts.values():
        a.pop("_fold", None)
    return rep


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    s = gp.ads_settings(env)
    if not all(s.values()):
        sys.exit("Google Ads secrets missing")      # stderr: hidden by the workflow step
    print("gads inst probe: start", flush=True)
    try:
        token = gads._access_token(s["client_id"], s["client_secret"], s["google_ads_refresh_token"])
    except Exception:
        print("gads inst probe: Google Ads sign-in failed", flush=True)
        sys.exit(1)
    report = run_probe(s, token, now=now, clock=clock, max_accounts=_int(env.get("PROBE_MAX_ACCOUNTS")))
    print(public_line(report["counts"]), flush=True)
    if not write_private(OUT_PATH, _dump(report), "gads inst probe"):
        sys.exit("private repo write failed")        # stderr: hidden by the workflow step
    print("gads inst probe: report written", flush=True)


if __name__ == "__main__":
    main()
