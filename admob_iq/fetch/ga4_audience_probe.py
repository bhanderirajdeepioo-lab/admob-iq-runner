"""One-off GA4 Audience probe, run by .github/workflows/ga4-audience-probe.yml: the Audience fetch (fetch.ga4_audience —
activeUsers by firstSessionDate over the tiered trailing month windows ending on the latest final day, + that day's
DAU) for the GA4 apps of the build, and its numbers (engine.audience: dead users by months since their last open, per
install month, per app, portfolio) — so the owner sees real numbers before the repo variable GA4_AUDIENCE switches it
on in the hourly build.

Read-only against GA4 and against the PRIVATE data (the workflow's read-only clone: the Uninstall state's routes, each
app's Uninstall store, and this probe's own last report); the only write is ga4/audience_probe.json in the PRIVATE
repo (write_private — never data/ or site/: the hourly build replaces those with its own copy on every push).

INPUTS: max_apps (the N smallest apps), apps (a comma list of Play packages, Audience / Uninstall file keys or AdMob app
ids — read from the workflow's event file, never from the log-printed step env: package names must not reach the
PUBLIC log), resume (continue the last report: an app it holds complete is carried over as it is; one it holds as a
partial read goes on from there, on ITS final day E; the rest start). Every app of the last report not probed in this
run is carried over — a report never loses an app.

Per app (one per Android stream, ga4_d1d7_verify.units_from_state; the first AdMob app id of the stream whose Uninstall
store is of that stream): the request plan (windows, calls, Σ range days, the token estimate from the app's own k), what
this run cost (calls, tokens, seconds) and in all, the Audience store exactly as the build keeps it (complete, or the
partial read with its progress), the app's measured k, and engine.audience.derive_app on a complete one with the
Uninstall store as the Uninstall tab reads it (engine.uninstall.fill_days); then engine.audience.portfolio over every
complete app.

QUOTA: the d1d7 probe's stricter rule (ga4_d1d7_probe.quota_low: any token bucket under HALF, ≤ 4 server-error / ≤ 5
thresholded requests left — this one-off leaves the hourly build at least half of every bucket), each call's estimate
must leave every bucket above half too, one request at a time per property (WORKERS properties in parallel); the run
starts no call after its budget and still writes what it has — a stopped app keeps its partial read for resume.
PUBLIC LOG: progress counts (a heartbeat at least every minute while calls go on) and one result line of counts; no
names, ids, emails, dates, user numbers or API error text — stderr is hidden by the workflow step.
"""

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from admob_iq import ga4_probe
from admob_iq.engine import audience as eng
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_audience as ga
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_d1d7_verify as vr
from admob_iq.fetch import ga4_uninstall as gu

OUT_PATH = "ga4/audience_probe.json"
DATA_DIR = "_private"               # the workflow's read-only clone of the private repo
BUDGET_SEC = 22 * 60                # no new call after 22 min (the job's timeout is 30)
WORKERS = 4                         # properties in parallel — one request at a time per property
HEARTBEAT_SEC = 60
FLOORS = {"tokensPerHour": pr.QUOTA_FRAC, "tokensPerProjectPerHour": pr.QUOTA_FRAC, "tokensPerDay": pr.QUOTA_FRAC}


class Run(pr.Run):
    """The d1d7 probe's clock / budget / call counter, with this probe's own counts-only heartbeat."""

    def tick(self):
        with self.lock:
            self.calls += 1
            now = self.clock()
            beat = now - self.beat >= HEARTBEAT_SEC
            if beat:
                self.beat = now
            n, s = self.calls, int(now - self.t0)
        if beat:
            self.say("audience progress: calls %d, %ds" % (n, s))


def _gate(q):
    return "quota_low" if pr.quota_low(q) else None


def _flag(v):
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def event_inputs(env):
    """The workflow_dispatch inputs from the event file (GITHUB_EVENT_PATH) — {} outside Actions or on any trouble."""
    p = env.get("GITHUB_EVENT_PATH")
    if not p:
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return (json.load(f) or {}).get("inputs") or {}
    except (OSError, ValueError, AttributeError):
        return {}


def wanted(raw):
    """The apps input → a set of lower-case tokens (packages, file keys, app ids)."""
    return {t.strip().lower() for t in str(raw or "").split(",") if t.strip()}


def matches(unit, tokens):
    """Does a unit answer to any token: its package, or any of its AdMob app ids or their file keys?"""
    ids = [str(a) for a in unit.get("app_ids") or []]
    names = {str(unit.get("package") or "").lower()} | {a.lower() for a in ids} | {gu.file_key(a) for a in ids}
    return bool(names & tokens)


def pick_store(unit, data_dir):
    """The unit's first AdMob app id whose Uninstall store is of this stream and has a history → (app id, store), or
    (None, why)."""
    why = "no_store"
    for aid in unit.get("app_ids") or []:
        st = gu.load_store(gu.store_path(data_dir, aid))
        if not st:
            continue
        if (str(st.get("property_id")), str(st.get("stream_id"))) != (unit["property_id"], unit["stream_id"]):
            why = "store_other_stream"
        elif not st.get("history_start") or not st.get("window_end"):
            why = "store_without_history"
        else:
            return aid, st
        st = None
    return None, why


def probe_unit(run, unit, token, data_dir, now, prop, old=None):
    """One app (stream): its Audience read (resumed from `old`, the last report's result, when given) and numbers →
    its result (never raises for GA4 trouble)."""
    old = old if isinstance(old, dict) else {}
    res = {"package": unit["package"], "property_id": unit["property_id"], "stream_id": unit["stream_id"],
           "tz": unit["tz"], "app_ids": list(unit.get("app_ids") or []), "complete": False}
    aid, uni = pick_store(unit, data_dir)
    if aid is None:
        res["err"] = uni
        return res
    end, hs = ga.final_end(unit["tz"], now), gu._d(uni["history_start"])
    if hs > end:
        res["err"] = "no_final_day_yet"
        return res
    store = old.get("audience") if isinstance(old.get("audience"), dict) else {}
    k = float(old.get("k") or ga.PRIOR_K)
    part = store.get("partial") or {}
    e_read = gu._d(part["E"]) if part.get("E") else end
    h_read = gu._d(part["history_start"]) if part.get("history_start") else hs
    res.update(app_id=aid, E=e_read.isoformat(), history_start=h_read.isoformat(),
               plan=ga.plan_calls(e_read, h_read, k), k=k)
    if not token:
        res["err"] = "auth"
        res["audience"] = store or None
        return res
    app = ga.App(token, unit["property_id"], unit["stream_id"], prop, over=run.over, tick=run.tick, gate=_gate,
                 floors=FLOORS)
    t0 = run.clock()
    route = {"property_id": unit["property_id"], "stream_id": unit["stream_id"]}
    try:
        res["step"] = ga.step(app, store, end, hs, route, gu._now_iso(now), k, roll=False)
    except ga.Stop as e:
        res["stopped"] = str(e)
    except Exception as e:
        res["err"] = ga._err(e)
    store.update(app_id=aid, package=unit["package"], time_zone=unit["tz"])
    res.update(audience=store, complete=bool(store.get("complete")) and not store.get("partial"),
               calls=app.calls, tokens=app.tok, seconds=int(run.clock() - t0),
               tokens_per_call=round(app.tok / app.calls, 2) if app.calls else None,
               k=ga.measured_k(app, k), k_prior=k,
               calls_all=int(old.get("calls_all") or 0) + app.calls, tokens_all=int(old.get("tokens_all") or 0) + app.tok)
    if store.get("partial"):
        res["progress"] = ga.progress(store["partial"])
    if res["complete"]:
        res["E"] = store["E"]
        res["flags"] = ga.flag_summary(store)
        try:
            from admob_iq.engine import uninstall as ue
            filled = ue.fill_days(uni)
        except Exception:
            filled, res["fill_failed"] = uni, True
        res["derived"] = pr._safely(eng.derive_app, store, filled)
    return res


def _stat(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return {"n": 0}
    return {"n": len(v), "median": ga4._median(v), "min": v[0], "max": v[-1], "sum": sum(v)}


def counts(apps, run, total, done_now=None):
    """The run's counts (the public line takes a few of them: no ids, names, dates or user numbers). done_now = the
    packages probed in this run (the rest were carried over)."""
    done = list(apps.values())
    now_ = [apps[p] for p in (done_now if done_now is not None else apps) if p in apps]
    ok = [a for a in done if a.get("complete")]
    fl = [a.get("flags") or {} for a in ok]
    der = [a["derived"] for a in ok if isinstance(a.get("derived"), dict) and "flags" in a["derived"]]
    return {"apps": total, "apps_done": len(done), "apps_now": len(now_), "apps_complete": len(ok),
            "apps_partial": sum(1 for a in done if (a.get("audience") or {}).get("partial")),
            "calls": run.calls, "tokens": sum(pr._int(a.get("tokens")) for a in now_),
            "flagged": sum(1 for f in fl if f.get("flagged")), "other": sum(1 for f in fl if f.get("other")),
            "thresholded": sum(1 for f in fl if f.get("thresholded")), "cov_off": sum(1 for f in fl if f.get("cov_off")),
            "impossible_cells": sum(pr._int(d["flags"].get("impossible_cells")) for d in der),
            "stopped": sum(1 for a in now_ if a.get("stopped")),
            "errors": sum(1 for a in now_ if a.get("err") or a.get("crash")),
            "seconds": run.elapsed(),
            "per_app": {"calls": _stat([a.get("calls_all") for a in ok]),
                        "tokens": _stat([a.get("tokens_all") for a in ok]),
                        "tokens_per_call": _stat([a.get("tokens_per_call") for a in now_]),
                        "k": _stat([a.get("k") for a in done]),
                        "seconds": _stat([a.get("seconds") for a in now_]),
                        "windows": _stat([(a.get("plan") or {}).get("windows") for a in done])}}


COUNT_KEYS = ("apps_complete", "apps", "apps_partial", "apps_now", "calls", "tokens", "flagged", "other", "thresholded",
              "cov_off", "impossible_cells", "stopped", "errors", "seconds")


def public_line(c):
    return ("audience probe: apps %d/%d complete, %d partial, %d probed now, calls %d, tokens %d, flagged %d (other %d, "
            "thresholded %d, coverage off %d), impossible cells %d, stopped %d, errors %d, %ds"
            % tuple(pr._int((c or {}).get(k)) for k in COUNT_KEYS))


def run_probe(units, data_dir, cid, sec, tokens, now=None, budget=BUDGET_SEC, clock=time.monotonic, workers=WORKERS,
              old=None, carried=None, total=None):
    """Probe every unit → the report (dict). old = {package: the last report's result} to resume from; carried = results
    kept as they are. Never raises for one app's failure; prints counts-only progress."""
    run = Run(budget, clock)
    now = now or datetime.now(timezone.utc)
    rt, access = dict(tokens), {}
    for owner in sorted({u.get("owner") or "" for u in units}):
        try:
            access[owner] = ga4.access_token(cid, sec, rt[owner]) if owner in rt else None
        except Exception:
            access[owner] = None
    out, lock = dict(carried or {}), threading.Lock()
    props = {u["property_id"]: ga.new_prop() for u in units}
    done_now = []

    def one(group):
        for u in group:
            try:
                res = probe_unit(run, u, access.get(u.get("owner") or ""), data_dir, now, props[u["property_id"]],
                                 (old or {}).get(u["package"]))
            except Exception as e:                   # a bug for one app must not cost the others
                res = {"package": u["package"], "crash": type(e).__name__, "complete": False}
            with lock:
                out[u["package"]] = res
                done_now.append(u["package"])
                n = len(done_now)
            run.say("audience probe: apps %d/%d done, calls %d, %ds" % (n, len(units), run.calls, run.elapsed()))

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(one, pr._groups(units)))
    derived = [a["derived"] for a in out.values() if isinstance(a.get("derived"), dict)]
    total = total or len(out)
    return {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "run_started": gu._now_iso(now),
            "rules": {"E": "latest final activity day: settled day (today-2 from noon, else -3; property tz) - %d"
                           % ga.FINAL_LAG_DAYS,
                      "windows": "months 1..12, then 15, 18, 21, 24, then every 6 months, until one holds the history; "
                                 "window N months = [E - floor(N x 30.4375) + 1, E]",
                      "tokens": "per call: k x sum(range days) x install days; k per app, measured (prior %g)"
                                % ga.PRIOR_K,
                      "call_est_cap": ga.CALL_EST_CAP, "ranges_per_call": ga.RANGES_PER_CALL,
                      "approximation": "alive = GA4 active in window - uninstalls inside the window (every window "
                                       "uninstaller taken as having opened first): dead is the upper end of the range, "
                                       "dead_lo (no window uninstaller had opened) the lower end",
                      "quota_frac": pr.QUOTA_FRAC},
            "counts": pr._safely(counts, out, run, total, done_now,
                                 fallback={"apps": total, "calls": run.calls}),
            "portfolio": pr._safely(eng.portfolio, derived), "apps": out}


def _old_report(path):
    try:
        with open(path, encoding="utf-8") as f:
            j = json.load(f)
        return j if isinstance(j, dict) else None
    except (OSError, ValueError):
        return None


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    root = env.get("AUDIENCE_DATA_DIR") or DATA_DIR
    data_dir = os.path.join(root, "data")
    units = vr.units_from_state(gu.load_state(data_dir))
    if not units:
        sys.exit("no GA4 app routes in the private state")
    inputs = event_inputs(env)
    want = wanted(inputs.get("apps") or env.get("AUDIENCE_APPS"))
    resume = _flag(inputs.get("resume") if "resume" in inputs else env.get("AUDIENCE_RESUME"))
    last = (_old_report(os.path.join(root, OUT_PATH)) or {}).get("apps") or {}
    last = {p: r for p, r in last.items() if isinstance(r, dict)}      # carried over whenever not probed now
    old = last if resume else {}                                       # … and read on from only with resume
    todo = [u for u in units if matches(u, want)] if want else list(units)
    if want:
        print("audience probe: apps filter %d given, %d matched" % (len(want), len(todo)), flush=True)
    if resume:                                       # complete in the last report: carried, not asked again
        todo = [u for u in todo if not (old.get(u["package"]) or {}).get("complete")]
    cap = pr._int(inputs.get("max_apps") or env.get("AUDIENCE_MAX_APPS"))
    if cap > 0:                                      # a quick trial: the smallest apps
        todo = sorted(todo, key=lambda u: (u.get("days") or 0, u["package"]))[:cap]
    doing = {u["package"] for u in todo}
    known = {u["package"] for u in units}
    carried = {p: r for p, r in last.items() if p not in doing}
    budget = pr._int(env.get("AUDIENCE_BUDGET_SEC")) or BUDGET_SEC
    print("audience probe: %d app(s) to probe, %d carried over%s"
          % (len(todo), len(carried), ", resuming %d partial" % sum(
              1 for u in todo if ((old.get(u["package"]) or {}).get("audience") or {}).get("partial"))
             if resume else ""), flush=True)
    report = run_probe(todo, data_dir, cid, sec, tokens, now=now, budget=budget, clock=clock, old=old,
                       carried=carried, total=len(known | set(carried)))
    print(public_line(report["counts"]), flush=True)
    if not pr.write_private(OUT_PATH, pr._dump(report), "ga4 audience probe"):
        sys.exit("private repo write failed")            # stderr: hidden by the workflow step
    print("audience probe: report written", flush=True)


if __name__ == "__main__":
    main()
