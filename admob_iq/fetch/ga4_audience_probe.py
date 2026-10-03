"""One-off GA4 Audience probe, run by .github/workflows/ga4-audience-probe.yml: the Audience fetch (fetch.ga4_audience —
activeUsers by firstSessionDate over the trailing 1, 2, 3 … month windows ending on the latest final day, + that day's
DAU) once for EVERY GA4 app of the build, and its numbers (engine.audience: dead users by months since their last open,
per install month, per app, portfolio) — so the owner sees real numbers before the repo variable GA4_AUDIENCE switches
it on in the hourly build.

Read-only against GA4 and against the PRIVATE data (the workflow's read-only clone: the Uninstall state's routes and
each app's Uninstall store); the only write is ga4/audience_probe.json in the PRIVATE repo (write_private — never data/
or site/: the hourly build replaces those with its own copy on every push).

Per app (one per Android stream, ga4_d1d7_verify.units_from_state; the first AdMob app id of the stream whose Uninstall
store is of that stream): the request plan (windows, calls, Σ range days, the a-priori token estimate), what it cost
(calls, tokens, seconds), the store exactly as the build would write it (flags included), and engine.audience.
derive_app on it with the Uninstall store as the Uninstall tab reads it (engine.uninstall.fill_days); then
engine.audience.portfolio over every app.

QUOTA: the d1d7 probe's stricter rule (ga4_d1d7_probe.quota_low: any token bucket under HALF, ≤ 4 server-error / ≤ 5
thresholded requests left — this one-off leaves the hourly build at least half of every bucket), one request at a time
per property (WORKERS properties in parallel); the run starts no call after its budget and still writes what it has.
PUBLIC LOG: progress counts (a heartbeat at least every minute while calls go on) and one result line of counts; no
names, ids, emails, dates, user numbers or API error text — stderr is hidden by the workflow step.
"""

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


def probe_unit(run, unit, token, data_dir, now, prop):
    """One app (stream): its Audience fetch and numbers → its result (never raises for GA4 trouble)."""
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
    res.update(app_id=aid, E=end.isoformat(), history_start=hs.isoformat(), plan=ga.plan_calls(end, hs))
    if not token:
        res["err"] = "auth"
        return res
    app = ga.App(token, unit["property_id"], unit["stream_id"], prop, over=run.over, tick=run.tick, gate=_gate)
    t0 = run.clock()
    try:
        store = ga.fetch_app(app, end, hs)
        store.update(app_id=aid, package=unit["package"], property_id=unit["property_id"],
                     stream_id=unit["stream_id"], time_zone=unit["tz"], fetched_at=gu._now_iso(now))
        res.update(store=store, complete=True, flags=ga.flag_summary(store))
    except ga.Stop as e:
        res["stopped"] = str(e)
    except Exception as e:
        res["err"] = ga._err(e)
    res.update(calls=app.calls, tokens=app.tok, seconds=int(run.clock() - t0),
               tokens_per_call=round(app.tok / app.calls, 2) if app.calls else None)
    if res["complete"]:
        try:
            from admob_iq.engine import uninstall as ue
            filled = ue.fill_days(uni)
        except Exception:
            filled, res["fill_failed"] = uni, True
        res["derived"] = pr._safely(eng.derive_app, res["store"], filled)
    return res


def _stat(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return {"n": 0}
    return {"n": len(v), "median": ga4._median(v), "min": v[0], "max": v[-1], "sum": sum(v)}


def counts(apps, run, total):
    """The run's counts (the public line takes a few of them: no ids, names, dates or user numbers)."""
    done = list(apps.values())
    ok = [a for a in done if a.get("complete")]
    fl = [a.get("flags") or {} for a in ok]
    der = [a["derived"] for a in ok if isinstance(a.get("derived"), dict) and "flags" in a["derived"]]
    return {"apps": total, "apps_done": len(done), "apps_complete": len(ok), "calls": run.calls,
            "tokens": sum(pr._int(a.get("tokens")) for a in done),
            "flagged": sum(1 for f in fl if f.get("flagged")), "other": sum(1 for f in fl if f.get("other")),
            "thresholded": sum(1 for f in fl if f.get("thresholded")), "cov_off": sum(1 for f in fl if f.get("cov_off")),
            "impossible_cells": sum(pr._int(d["flags"].get("impossible_cells")) for d in der),
            "stopped": sum(1 for a in done if a.get("stopped")),
            "errors": sum(1 for a in done if a.get("err") or a.get("crash")),
            "seconds": run.elapsed(),
            "per_app": {"calls": _stat([a.get("calls") for a in ok]), "tokens": _stat([a.get("tokens") for a in ok]),
                        "tokens_per_call": _stat([a.get("tokens_per_call") for a in ok]),
                        "seconds": _stat([a.get("seconds") for a in ok]),
                        "windows": _stat([(a.get("plan") or {}).get("windows") for a in ok])}}


COUNT_KEYS = ("apps_complete", "apps", "calls", "tokens", "flagged", "other", "thresholded", "cov_off",
              "impossible_cells", "stopped", "errors", "seconds")


def public_line(c):
    return ("audience probe: apps %d/%d complete, calls %d, tokens %d, flagged %d (other %d, thresholded %d, "
            "coverage off %d), impossible cells %d, stopped %d, errors %d, %ds"
            % tuple(pr._int((c or {}).get(k)) for k in COUNT_KEYS))


def run_probe(units, data_dir, cid, sec, tokens, now=None, budget=BUDGET_SEC, clock=time.monotonic, workers=WORKERS):
    """Probe every unit → the report (dict). Never raises for one app's failure; prints counts-only progress."""
    run = Run(budget, clock)
    now = now or datetime.now(timezone.utc)
    rt, access = dict(tokens), {}
    for owner in sorted({u.get("owner") or "" for u in units}):
        try:
            access[owner] = ga4.access_token(cid, sec, rt[owner]) if owner in rt else None
        except Exception:
            access[owner] = None
    out, lock = {}, threading.Lock()
    props = {u["property_id"]: ga.new_prop() for u in units}

    def one(group):
        for u in group:
            try:
                res = probe_unit(run, u, access.get(u.get("owner") or ""), data_dir, now, props[u["property_id"]])
            except Exception as e:                   # a bug for one app must not cost the others
                res = {"package": u["package"], "crash": type(e).__name__, "complete": False}
            with lock:
                out[u["package"]] = res
                n = len(out)
            run.say("audience probe: apps %d/%d done, calls %d, %ds" % (n, len(units), run.calls, run.elapsed()))

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(one, pr._groups(units)))
    derived = [a["derived"] for a in out.values() if isinstance(a.get("derived"), dict)]
    return {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "run_started": gu._now_iso(now),
            "rules": {"E": "latest final activity day: settled day (today-2 from noon, else -3; property tz) - %d"
                           % gu.ACT_LATE_DAYS,
                      "windows": "window N = [E - floor(N x 30.4375) + 1, E], N = 1.. until it holds the history",
                      "ranges_per_call": ga.RANGES_PER_CALL, "approximation":
                          "alive = GA4 active in window - uninstalls inside the window (every window uninstaller taken "
                          "as having opened first: dead is an upper bound; dead_lo the lower bound)",
                      "buckets": [b[0] for b in eng.BUCKETS], "quota_frac": pr.QUOTA_FRAC},
            "counts": pr._safely(counts, out, run, len(units), fallback={"apps": len(units), "calls": run.calls}),
            "portfolio": pr._safely(eng.portfolio, derived), "apps": out}


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    data_dir = os.path.join(env.get("AUDIENCE_DATA_DIR") or DATA_DIR, "data")
    units = vr.units_from_state(gu.load_state(data_dir))
    if not units:
        sys.exit("no GA4 app routes in the private state")
    cap = pr._int(env.get("AUDIENCE_MAX_APPS"))
    if cap > 0:                                      # a quick trial: the smallest apps
        units = sorted(units, key=lambda u: (u.get("days") or 0, u["package"]))[:cap]
    budget = pr._int(env.get("AUDIENCE_BUDGET_SEC")) or BUDGET_SEC
    print("audience probe: %d app(s) to probe" % len(units), flush=True)
    report = run_probe(units, data_dir, cid, sec, tokens, now=now, budget=budget, clock=clock)
    print(public_line(report["counts"]), flush=True)
    if not pr.write_private(OUT_PATH, pr._dump(report), "ga4 audience probe"):
        sys.exit("private repo write failed")            # stderr: hidden by the workflow step
    print("audience probe: report written", flush=True)


if __name__ == "__main__":
    main()
