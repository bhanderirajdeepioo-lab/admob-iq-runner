"""One-off GA4 FIRST-OPEN FUNNEL probe, run by .github/workflows/ga4-firstopen-probe.yml (owner, 13 Oct 2026: "user
splash screen se home screen tak kitne pahunch rahe hain for the first time" — and every feature on the FULL history, not
today only).

GA4 already gets what this needs from every app: screen_view with the screen's Activity class (unifiedScreenClass:
SplashActivity, LanguageActivity, MainActivity …) and, in many apps, the developer's own events (app_splash_created,
app_language_created, app_home_created …). "First time" = a user's FIRST session (newVsReturning == "new", a session
scope: 0 sessions before it).

Per app (one per Android stream, ga4_d1d7_verify.units_from_state), read-only:
  DISC_SCREENS  the last 28 days: first-session users by screen class (screen_view)
  DISC_EVENTS   the last 28 days: first-session users by event name
  then it picks, generically (no app names or classes are fixed here): the screen classes whose names read as a step of
  the first open — splash / start / launch / language / intro / onboarding / welcome / permission / consent / privacy /
  guide / tutorial / main / home — never a caller-ID screen (CallerCad…) or an ad Activity, plus the top classes by
  first-session users (so a step with an unusual name is not missed); and the events that read the same way plus
  first_open;
  HIST_NEW      the FULL history (the app's Uninstall store history_start .. today, property timezone): new users / day
  HIST_SCREENS  the same days: first-session users per picked screen class per day
  HIST_EVENTS   the same days: first-session users per picked event per day
The last two days are not final in GA4 (they still change); the report says so.

Writes ga4/firstopen_probe.json in the PRIVATE repo (write_private; never data/ or site/). With resume an app the last
report holds complete is carried over, not asked again. QUOTA and PUBLIC LOG as the audience probe: any token bucket
under half stops that property; progress counts and one counts-only line; stderr is hidden by the workflow step.
"""
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from admob_iq import ga4_probe
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_audience_probe as ap
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_d1d7_verify as vr
from admob_iq.fetch import ga4_uninstall as gu

OUT_PATH = "ga4/firstopen_probe.json"
DATA_DIR = "_private"
BUDGET_SEC = 22 * 60
WORKERS = 4
DISC_DAYS = 28
TOP_EXTRA = 5                       # + this many top screen classes by first-session users, whatever their names
MAX_CLASSES = 24
MAX_EVENTS = 20
STEP = re.compile(r"splash|start|launch|lang|intro|onboard|welcome|permission|consent|privacy|guide|tutorial|main|home",
                  re.I)
NOT_STEP = re.compile(r"callercad|^ad[A-Z_]|adactivity|interstitial|^com\.google|ads?activity", re.I)
EV_STEP = re.compile(r"splash|start|launch|lang|intro|onboard|welcome|permission|consent|privacy|guide|tutorial|home|"
                     r"main|first", re.I)
NOT_SET = {"(not set)", "", None}
# Firebase's own automatic events: never a step of the app's first open (first_open itself is added on purpose)
AUTO_EVENTS = {"screen_view", "session_start", "user_engagement", "app_remove", "app_update", "os_update", "app_clear_data",
               "app_exception", "notification_receive", "notification_open", "notification_dismiss", "notification_foreground",
               "ad_impression", "ad_click", "ad_exposure", "ad_query", "ad_reward", "ad_paid_event", "in_app_purchase",
               "dynamic_link_first_open", "firebase_campaign", "firebase_in_app_message_impression"}


def _new_only():
    return [{"filter": {"fieldName": "newVsReturning", "stringFilter": {"matchType": "EXACT", "value": "new"}}}]


def _today(tz):
    return datetime.now(ZoneInfo(tz or "UTC")).date()


def pick_classes(disc):
    """disc = [[class, users], …] (first sessions, users descending) → the classes to follow day by day."""
    named = [c for c, _ in disc if c not in NOT_SET and STEP.search(c) and not NOT_STEP.search(c)]
    top = [c for c, _ in disc if c not in NOT_SET and not NOT_STEP.search(c)][:TOP_EXTRA]
    out = []
    for c in named + top:
        if c not in out:
            out.append(c)
    return out[:MAX_CLASSES]


def pick_events(disc):
    """disc = [[event, users], …] → first_open + the events that read as a step of the first open."""
    out = ["first_open"] if any(e == "first_open" for e, _ in disc) else []
    for e, _ in disc:
        if e not in out and e not in NOT_SET and e not in AUTO_EVENTS and EV_STEP.search(e):
            out.append(e)
    return out[:MAX_EVENTS]


def _series(rows, key):
    """rows of {date, <key>, activeUsers} → {key value: {YYYY-MM-DD: users}}."""
    out = {}
    for r in rows:
        d = str(r.get("date") or "")
        if len(d) != 8:
            continue
        out.setdefault(str(r.get(key)), {})["%s-%s-%s" % (d[:4], d[4:6], d[6:])] = int(r.get("activeUsers") or 0)
    return out


def probe_unit(run, unit, token, data_dir, prop):
    res = {"package": unit["package"], "property_id": unit["property_id"], "stream_id": unit["stream_id"],
           "tz": unit["tz"], "app_ids": list(unit.get("app_ids") or []), "complete": False}
    aid, uni = ap.pick_store(unit, data_dir)
    if aid is None:
        res["err"] = uni
        return res
    today = _today(unit["tz"])
    hs = gu._d(uni["history_start"])
    res.update(app_id=aid, history_start=hs.isoformat(), end=today.isoformat(),
               not_final_from=(today - timedelta(days=1)).isoformat())
    if not token:
        res["err"] = "auth"
        return res
    app = pr.App(token, unit["property_id"], unit["stream_id"], run, prop)
    rng = lambda a, b: [{"startDate": a.isoformat(), "endDate": b.isoformat()}]
    full = rng(hs, today)
    t0 = run.clock()
    try:
        app.kind = "disc_screens"
        rows = app.report_all({"dateRanges": rng(today - timedelta(days=DISC_DAYS), today),
                               "dimensions": [{"name": "unifiedScreenClass"}], "metrics": [{"name": "activeUsers"}],
                               "orderBys": [{"metric": {"metricName": "activeUsers"}, "desc": True}]},
                              event="screen_view", extra=_new_only())
        disc_s = [[r.get("unifiedScreenClass"), int(r.get("activeUsers") or 0)] for r in rows]
        app.kind = "disc_events"
        rows = app.report_all({"dateRanges": rng(today - timedelta(days=DISC_DAYS), today),
                               "dimensions": [{"name": "eventName"}], "metrics": [{"name": "activeUsers"}],
                               "orderBys": [{"metric": {"metricName": "activeUsers"}, "desc": True}]},
                              extra=_new_only())
        disc_e = [[r.get("eventName"), int(r.get("activeUsers") or 0)] for r in rows]
        classes, events = pick_classes(disc_s), pick_events(disc_e)
        res.update(disc_screens=disc_s, disc_events=disc_e, classes=classes, events=events)
        app.kind = "hist_new"
        rows = app.report_all({"dateRanges": full, "dimensions": [{"name": "date"}],
                               "metrics": [{"name": "newUsers"}, {"name": "activeUsers"}]})
        res["new_users"] = {"%s-%s-%s" % (r["date"][:4], r["date"][4:6], r["date"][6:]): int(r.get("newUsers") or 0)
                            for r in rows if len(str(r.get("date") or "")) == 8}
        if classes:
            app.kind = "hist_screens"
            rows = app.report_all({"dateRanges": full, "dimensions": [{"name": "date"}, {"name": "unifiedScreenClass"}],
                                   "metrics": [{"name": "activeUsers"}]},
                                  event="screen_view", extra=_new_only() + [ga4._in_list("unifiedScreenClass", classes)])
            res["screens"] = _series(rows, "unifiedScreenClass")
        if events:
            app.kind = "hist_events"
            rows = app.report_all({"dateRanges": full, "dimensions": [{"name": "date"}, {"name": "eventName"}],
                                   "metrics": [{"name": "activeUsers"}]}, events=events, extra=_new_only())
            res["events_daily"] = _series(rows, "eventName")
        res["complete"] = True
    except pr.Stop as e:
        res["stopped"] = str(e)
    except Exception as e:
        res["err"] = pr._err(e)
    res.update(calls=app.calls, tokens=app.tok, by_kind=app.by_kind, seconds=int(run.clock() - t0),
               thresholded=bool(app.thresholded))
    return res


def counts(apps):
    a = list(apps.values())
    return {"apps": len(a), "complete": sum(1 for x in a if x.get("complete")),
            "stopped": sum(1 for x in a if x.get("stopped")), "errors": sum(1 for x in a if x.get("err")),
            "thresholded": sum(1 for x in a if x.get("thresholded")),
            "calls": sum(int(x.get("calls") or 0) for x in a), "tokens": sum(int(x.get("tokens") or 0) for x in a),
            "days": sum(len(x.get("new_users") or {}) for x in a)}


def public_line(c):
    return ("firstopen probe: apps %(apps)d, complete %(complete)d, stopped %(stopped)d, errors %(errors)d, "
            "thresholded %(thresholded)d, calls %(calls)d, tokens %(tokens)d, app-days %(days)d" % c)


class Run(pr.Run):
    """The d1d7 probe's clock / budget / call counter, with this probe's own counts-only heartbeat."""

    def tick(self):
        with self.lock:
            self.calls += 1
            now = self.clock()
            beat = now - self.beat >= 60
            if beat:
                self.beat = now
            n, s = self.calls, int(now - self.t0)
        if beat:
            self.say("firstopen progress: calls %d, %ds" % (n, s))


def run_probe(units, data_dir, cid, sec, tokens, budget=BUDGET_SEC, clock=time.monotonic, workers=WORKERS, carried=None):
    run = Run(budget, clock)
    rt, access = dict(tokens), {}                  # owner_tokens gives (owner, refresh token) pairs
    for owner in sorted({u.get("owner") or "" for u in units}):
        try:
            access[owner] = ga4.access_token(cid, sec, rt[owner]) if owner in rt else None
        except Exception:
            access[owner] = None
    out, lock, done = dict(carried or {}), threading.Lock(), []
    props = {u["property_id"]: pr.new_prop() for u in units}

    def one(group):
        for u in group:
            try:
                r = probe_unit(run, u, access.get(u.get("owner") or ""), data_dir, props[u["property_id"]])
            except Exception as e:
                r = {"package": u["package"], "crash": type(e).__name__, "complete": False}
            with lock:
                out[u["package"]] = r
                done.append(u["package"])
                n = len(done)
            run.say("firstopen probe: apps %d/%d done, calls %d, %ds" % (n, len(units), run.calls, run.elapsed()))

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(one, pr._groups(units)))
    return {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rules": {"first_time": "newVsReturning == new (the user's first session)",
                      "users": "activeUsers of first sessions with that screen_view / event, per day (property tz)",
                      "not_final": "the last 2 days still change in GA4",
                      "picked": "screen classes / events named like a first-open step (no fixed app names), never "
                                "caller-ID or ad screens, + the top %d classes" % TOP_EXTRA},
            "counts": counts(out), "apps": out}


def main(env=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    root = env.get("FIRSTOPEN_DATA_DIR") or DATA_DIR
    data_dir = os.path.join(root, "data")
    units = vr.units_from_state(gu.load_state(data_dir))
    if not units:
        sys.exit("no GA4 app routes in the private state")
    inputs = ap.event_inputs(env)
    resume = ap._flag(inputs.get("resume") if "resume" in inputs else env.get("FIRSTOPEN_RESUME"))
    last = {}
    try:
        with open(os.path.join(root, OUT_PATH), encoding="utf-8") as f:
            last = (json.load(f) or {}).get("apps") or {}
    except (OSError, ValueError):
        last = {}
    carried = {p: r for p, r in last.items() if isinstance(r, dict) and r.get("complete")} if resume else {}
    todo = [u for u in units if u["package"] not in carried]
    cap = pr._int(inputs.get("max_apps") or env.get("FIRSTOPEN_MAX_APPS"))
    if cap > 0:
        todo = sorted(todo, key=lambda u: (u.get("days") or 0, u["package"]))[:cap]
    print("firstopen probe: %d app(s) to probe, %d carried over" % (len(todo), len(carried)), flush=True)
    budget = pr._int(env.get("FIRSTOPEN_BUDGET_SEC")) or BUDGET_SEC
    report = run_probe(todo, data_dir, cid, sec, tokens, budget=budget, clock=clock, carried=carried)
    print(public_line(report["counts"]), flush=True)
    if not pr.write_private(OUT_PATH, pr._dump(report), "ga4 first-open funnel probe"):
        sys.exit("private repo write failed")
    print("firstopen probe: report written", flush=True)


if __name__ == "__main__":
    main()
