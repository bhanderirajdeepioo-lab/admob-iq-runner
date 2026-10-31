"""One-off GA4 NOTIFICATION / ORGANIC / PAID revenue probe, run by .github/workflows/ga4-notif-probe.yml: before any
"revenue by source" view is built, measure per GA4 app what GA4 gives — revenue by how the user was ACQUIRED (first-user
channel group: Cross-network / Organic Search / Direct / Mobile Push Notifications …) and by what OPENED each session
(session channel group: "Mobile Push Notifications" = a session started from a push notification), the two crossed, the
paid users' channels, the push sessions' source / medium / campaign, and the notification events the app logs — every
read tied to the same read without the split (nothing silently lost), with its "(other)" / "(not set)" shares.
Read-only against GA4 and against the PRIVATE repo's data (the Uninstall state's routes); the only write is
ga4/notif_probe.json in the PRIVATE repo.

READS (H = the app's history start .. F, at most HIST_DAYS back; R = the RECENT days to F; F = E − LATE in the property's
timezone; USD; pinned to the app's Android stream by ga4.Ga4App; METS = newUsers, activeUsers, sessions, totalAdRevenue,
totalRevenue):
  TOTM   H  yearMonth                                                METS
  FUM    H  yearMonth, firstUserDefaultChannelGroup                  METS
  SEM    H  yearMonth, sessionDefaultChannelGroup                    METS
  XM     H  yearMonth, firstUserDefaultChannelGroup, sessionDefaultChannelGroup   METS
  PAIDM  H  yearMonth, firstUserDefaultChannelGroup — users with a real Google Ads campaign id only   newUsers, revenue
  DAY    R  date, sessionDefaultChannelGroup                         sessions, activeUsers, totalAdRevenue
  DAY0   R  date                                                     the same
  SRCN   R  sessionSource, sessionMedium, sessionCampaignName — push sessions only   sessions, activeUsers, revenue
  EV     R  eventName                                                eventCount, totalUsers
  EVM    H  yearMonth, eventName — the notification events only      eventCount, totalUsers
  EVD    R  date, eventName — the notification events only           eventCount, totalUsers
Ties: FUM / SEM / XM vs TOTM per month, DAY vs DAY0 per day.

OUTPUT: ga4/notif_probe.json in the PRIVATE repo (write_private; never data/ or site/): per app KEY its reads' records and
the rows themselves (channel groups, months, events: small tables, the owner's own data, private repo only).
PUBLIC LOG: progress counts and ONE counts-only line per read kind + one for the run — no names, ids, channels, events,
dates, users or money; stderr is hidden by the workflow.

LIMITS: as ga4_device_probe (the property's quota rule, one request at a time per property, APP_CALLS / MAX_CALLS,
BUDGET_SEC).
"""

import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from admob_iq import ga4_probe
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_audience_probe as ap
from admob_iq.fetch import ga4_country_probe as cp
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_device_probe as dp
from admob_iq.fetch import ga4_shape_probe as sp
from admob_iq.fetch import ga4_uninstall as gu
from admob_iq.fetch.ga4_d1d7_probe import Stop

LATE = gu.IDAY_LATE
RECENT = 90                         # days of the daily / source / event reads
HIST_DAYS = 1100                    # the monthly reads: the app's history start, at most this many days back
FU, SE = "firstUserDefaultChannelGroup", "sessionDefaultChannelGroup"
CAMP = "firstUserGoogleAdsCampaignId"
PUSH = "Mobile Push Notifications"  # GA4's default channel group of a session started from a push notification
METS = ("newUsers", "activeUsers", "sessions", "totalAdRevenue", "totalRevenue")
NR = ("newUsers", "totalAdRevenue", "totalRevenue")
DMETS = ("sessions", "activeUsers", "totalAdRevenue")
EMETS = ("eventCount", "totalUsers")
NOTIF_EVENTS = ("notification_open", "notification_receive", "notification_foreground", "notification_dismiss",
                "firebase_campaign")
KINDS = ("TOTM", "FUM", "SEM", "XM", "PAIDM", "DAY", "DAY0", "SRCN", "EV", "EVM", "EVD")
TOP_EV = 80                         # events kept by name (the biggest by count) + every notification-like one
MAX_CALLS = 1000
APP_CALLS = 40
WORKERS = 4
BUDGET_SEC = 20 * 60
TICK_SEC = 20
PAGE_ROWS = 100000
DATA_DIR = "_private"
OUT_PATH = "ga4/notif_probe.json"


class Run(cp.Run):
    def pulse(self, count=False):
        with self.lock:
            if count:
                self.calls += 1
            now = self.clock()
            beat = now - self.beat >= pr.HEARTBEAT_SEC
            if beat:
                self.beat = now
            n, s = self.calls, int(now - self.t0)
        if beat:
            self.say("notif progress: calls %d, %ds" % (n, s))


def plan_of(u, now, end=None):
    """F = the newest final day (E − LATE), or `end` (the "end" input: a chosen day, e.g. yesterday to compare with a
    GA4 screen — its numbers may still grow)."""
    f = end or ga4.window_end_in(u["tz"], now) - timedelta(days=LATE)
    hs = gu._d(u["history_start"]) if u.get("history_start") else None
    h0 = max(hs, f - timedelta(days=HIST_DAYS)) if hs else f - timedelta(days=HIST_DAYS)
    return {"F": f, "h0": h0, "r0": f - timedelta(days=RECENT - 1)}


def _exact(field, value):
    return {"filter": {"fieldName": field, "stringFilter": {"matchType": "EXACT", "value": value}}}


def request(kind, p):
    f, h0, r0 = p["F"], p["h0"], p["r0"]
    b = dp._body
    if kind == "TOTM":
        return {"body": b(h0, f, ("yearMonth",), METS)}
    if kind == "FUM":
        return {"body": b(h0, f, ("yearMonth", FU), METS)}
    if kind == "SEM":
        return {"body": b(h0, f, ("yearMonth", SE), METS)}
    if kind == "XM":
        return {"body": b(h0, f, ("yearMonth", FU, SE), METS)}
    if kind == "PAIDM":
        return {"body": b(h0, f, ("yearMonth", FU), NR), "extra": [cp.paid_expr(CAMP)]}
    if kind == "DAY":
        return {"body": b(r0, f, ("date", SE), DMETS)}
    if kind == "DAY0":
        return {"body": b(r0, f, ("date",), DMETS)}
    if kind == "SRCN":
        return {"body": b(r0, f, ("sessionSource", "sessionMedium", "sessionCampaignName"), DMETS),
                "extra": [_exact(SE, PUSH)]}
    if kind == "EV":
        return {"body": b(r0, f, ("eventName",), EMETS)}
    if kind == "EVM":
        return {"body": b(h0, f, ("yearMonth", "eventName"), EMETS),
                "extra": [ga4._in_list("eventName", NOTIF_EVENTS)]}
    if kind == "EVD":
        return {"body": b(r0, f, ("date", "eventName"), EMETS), "extra": [ga4._in_list("eventName", NOTIF_EVENTS)]}
    raise KeyError(kind)


DIMS = {"TOTM": ("yearMonth",), "FUM": ("yearMonth", FU), "SEM": ("yearMonth", SE), "XM": ("yearMonth", FU, SE),
        "PAIDM": ("yearMonth", FU), "DAY": ("date", SE), "DAY0": ("date",),
        "SRCN": ("sessionSource", "sessionMedium", "sessionCampaignName"), "EV": ("eventName",),
        "EVM": ("yearMonth", "eventName"), "EVD": ("date", "eventName")}
MOFK = {"TOTM": METS, "FUM": METS, "SEM": METS, "XM": METS, "PAIDM": NR, "DAY": DMETS, "DAY0": DMETS, "SRCN": DMETS,
        "EV": EMETS, "EVM": EMETS, "EVD": EMETS}


def _r(v):
    v = dp._num(v)
    return int(v) if float(v).is_integer() else round(v, 4)


def table(rows, dims, mets):
    """Rows → [[dim values…, metric values…]] (small tables: channel groups × months, events)."""
    return [[str(r.get(d) or "") for d in dims] + [_r(r.get(m)) for m in mets] for r in rows]


def facts(raw):
    g = raw.get
    out = {}
    for k in ("FUM", "SEM", "XM"):
        if g(k) is not None and g("TOTM") is not None:
            out["tie_" + k] = {m: dp.tie_by(g(k), g("TOTM"), "yearMonth", m) for m in ("totalAdRevenue", "activeUsers")}
    if g("DAY") is not None and g("DAY0") is not None:
        out["tie_DAY"] = {m: dp.tie_by(g("DAY"), g("DAY0"), "date", m) for m in DMETS}
    if g("SEM") is not None:
        t = dp._tot(g("SEM"), "totalAdRevenue")
        p = sum(dp._num(r.get("totalAdRevenue")) for r in g("SEM") if r.get(SE) == PUSH)
        out["push_rev_share"] = pr._ratio(p, t)
        out["push_months"] = sorted({r.get("yearMonth") for r in g("SEM") if r.get(SE) == PUSH and
                                     (dp._num(r.get("sessions")) or dp._num(r.get("totalAdRevenue")))})
    if g("EV") is not None:
        ev = sorted(g("EV"), key=lambda r: -dp._num(r.get("eventCount")))
        keep = ev[:TOP_EV] + [r for r in ev[TOP_EV:] if any(w in str(r.get("eventName")).lower()
                                                            for w in ("notif", "push", "remind", "fcm", "alarm"))]
        out["events"] = table(keep, ("eventName",), EMETS)
        out["events_n"] = len(ev)
        out["notif_like"] = sorted({str(r.get("eventName")) for r in ev if any(
            w in str(r.get("eventName")).lower() for w in ("notif", "push", "remind", "fcm", "alarm"))})
    for k in ("TOTM", "FUM", "SEM", "XM", "PAIDM", "DAY", "DAY0", "SRCN", "EVM", "EVD"):
        if g(k) is not None:
            out["t_" + k] = table(g(k), DIMS[k], MOFK[k])
    return out


def probe_app(run, u, token, now, prop, opts):
    p = plan_of(u, now, opts.get("end"))
    res = {"key": u["key"], "tz": u["tz"], "F": p["F"].isoformat(), "h0": p["h0"].isoformat(), "r0": p["r0"].isoformat(),
           "reads": {}}
    if not token:
        res.update(err={"type": "auth"}, complete=False)
        return res
    ga = cp.App(token, u["property_id"], u["stream_id"], run, prop, cap=opts.get("app_calls", APP_CALLS))
    raw = {}
    try:
        why = ga.stop or run.over()
        if why:
            raise Stop(why)
        for kind in KINDS:
            req = request(kind, p)
            rec, rows = cp._read(ga, kind, lambda: ga.report_all(req["body"], extra=req.get("extra"),
                                                                 page_rows=PAGE_ROWS), dp.p_rows(DIMS[kind], MOFK[kind]))
            res["reads"][kind] = rec
            if rec.get("ok"):
                raw[kind] = rows
    except Stop as e:
        res["stopped"] = str(e)
    finally:
        res["facts"] = pr._safely(facts, raw, fallback={"bug": True})
        res["complete"] = all((res["reads"].get(k) or {}).get("ok") is not None for k in KINDS) and "stopped" not in res
        res.update(calls=ga.by_kind, tokens=ga.tok, sec=round(ga.sec, 2), server_errors=ga.server_errors)
    return res


def counts(apps, run):
    return {"apps": len(apps), "complete": sum(1 for a in apps.values() if (a or {}).get("complete")),
            "stopped": sum(1 for a in apps.values() if (a or {}).get("stopped")), "calls": run.calls,
            "seconds": run.elapsed(), "kinds": {k: dp._read_counts(apps, k) for k in KINDS},
            "push_apps": sum(1 for a in apps.values() if ((a or {}).get("facts") or {}).get("push_rev_share")),
            "notif_event_apps": sum(1 for a in apps.values() if ((a or {}).get("facts") or {}).get("t_EVM"))}


def public_lines(c):
    z = {"n": 0, "ok": 0, "refused": 0, "other": 0, "thresh": 0, "sampled": 0}
    out = []
    for k in KINDS:
        v = dict(z, **((c.get("kinds") or {}).get(k) or {}))
        out.append("notif probe: %s n %d ok %d refused %d other %d thresholded %d sampled %d"
                   % (k, v["n"], v["ok"], v["refused"], v["other"], v["thresh"], v["sampled"]))
    out.append("notif probe: apps %d, complete %d, stopped %d, apps with push sessions %d, with notification events %d, "
               "calls %d, %ds" % (c.get("apps", 0), c.get("complete", 0), c.get("stopped", 0), c.get("push_apps", 0),
                                  c.get("notif_event_apps", 0), c.get("calls", 0), c.get("seconds", 0)))
    return out


def run_probe(units, cid, sec, tokens, opts, now=None, clock=time.monotonic, workers=WORKERS, tick=TICK_SEC):
    run = Run(opts.get("budget") or BUDGET_SEC, clock, opts.get("max_calls") or MAX_CALLS)
    now = now or datetime.now(timezone.utc)
    rt, access = dict(tokens), {}
    for owner in sorted({u.get("owner") or "" for u in units}):
        try:
            access[owner] = ga4.access_token(cid, sec, rt[owner]) if owner in rt else None
        except Exception:
            access[owner] = None
    out, props = {}, {u["property_id"]: pr.new_prop() for u in units}
    lock, done = threading.Lock(), [0]

    def one(group):
        for u in group:
            try:
                r = probe_app(run, u, access.get(u.get("owner") or ""), now, props[u["property_id"]], opts)
            except Exception as e:                   # a bug for one app must not cost the others
                r = {"key": u["key"], "crash": type(e).__name__, "complete": False}
            with lock:
                out[u["key"]] = r
                done[0] += 1
                n = done[0]
            run.say("notif progress: apps %d/%d, calls %d, %ds" % (n, len(units), run.calls, run.elapsed()))

    with sp.Beat(run, tick):
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            list(ex.map(one, pr._groups(units)))
    c = pr._safely(counts, out, run, fallback={"apps": len(out), "calls": run.calls, "seconds": run.elapsed()})
    return {"v": 1, "probe": "ga4_notif", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rules": {"late": LATE, "end": opts["end"].isoformat() if opts.get("end") else None, "recent": RECENT, "hist_days": HIST_DAYS, "push": PUSH,
                      "notif_events": list(NOTIF_EVENTS), "top_ev": TOP_EV, "max_calls": run.max_calls,
                      "app_calls": opts.get("app_calls", APP_CALLS), "page_rows": PAGE_ROWS},
            "counts": c, "apps": out}


def options(inputs, env):
    def get(k, e):
        v = inputs.get(k)
        return env.get(e) if v is None or str(v).strip() == "" else v
    end = str(get("end", "NOTIF_END") or "").strip()
    tag = re.sub(r"[^a-z0-9_-]", "", str(get("tag", "NOTIF_TAG") or "").strip().lower())[:32]
    return {"max_apps": pr._int(get("max_apps", "NOTIF_MAX_APPS")), "apps": ap.wanted(get("apps", "NOTIF_APPS")),
            "max_calls": pr._int(get("max_calls", "NOTIF_MAX_CALLS")) or MAX_CALLS, "app_calls": APP_CALLS,
            "budget": pr._int(env.get("NOTIF_BUDGET_SEC")) or BUDGET_SEC,
            "end": date.fromisoformat(end) if end else None, "tag": tag}


def out_path(opts):
    """ga4/notif_probe.json, or ga4/notif_probe_<tag>.json for a tagged (partial / chosen-day) run."""
    return "ga4/notif_probe_%s.json" % opts["tag"] if opts.get("tag") else OUT_PATH


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    try:
        opts = options(ap.event_inputs(env), env)
    except ValueError:
        print("notif probe: the end input is not understood", flush=True)
        sys.exit(2)
    root = env.get("NOTIF_DATA_DIR") or DATA_DIR
    units = cp.units_from_state(sp.load_state(root))
    if opts["apps"]:
        units = [u for u in units if ap.matches(u, opts["apps"]) or u["key"] in opts["apps"]]
    if opts["max_apps"] > 0:
        units = units[:opts["max_apps"]]
    if not units:
        sys.exit("no GA4 app routes in the private state (or none matched)")
    print("notif probe: %d app(s) to probe" % len(units), flush=True)
    report = run_probe(units, cid, sec, tokens, opts, now=now, clock=clock)
    for line in public_lines(report["counts"]):
        print(line, flush=True)
    if not pr.write_private(out_path(opts), pr._dump(report), "ga4 notif probe"):
        sys.exit("private repo write failed")            # stderr: hidden by the workflow step
    print("notif probe: report written", flush=True)


if __name__ == "__main__":
    main()
