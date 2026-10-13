"""One-off GA4 FIRST-OPEN FUNNEL probe, strict, run by .github/workflows/ga4-funnel-probe.yml. The owner, 13 Oct 2026:
"splash se home user zyada nahi ho sakta … splash me 100 hain to home me maximum 100, jo first time wale ho". The first
probe (ga4_firstopen_probe) counted each screen on its own, so a user who reached Home WITHOUT the Splash (an after-call
screen, a notification) made Home exceed Splash. This one asks GA4's funnel report (Data API v1alpha runFunnelReport,
a CLOSED funnel: every step in order) for the users who did, in this order:
    first_open → Splash (within 10 min) → <step> (within 60 min)
for <step> = Home, and separately Language / Permission / Intro — so each count is at most the Splash count; and once more
for Home with the Splash at ANY time after first_open ("home_any"). The owner, same day: "aaj install hua user lekin usne
2 din bad open kiya, to vo manage ho jayega?" — first_open is logged on the app's first RUN, not at install, so a late
first open is simply counted on that day; but an app can first run in the background (an after-call screen, a push)
without the user opening it, and when the user opens it days later the strict funnel (Splash within 10 min of first_open)
misses them: home_any keeps them.

The screens come from the first probe's private report (ga4/firstopen_probe.json in the clone): per app the Splash = the
most-seen splash-like class, Home = the most-seen main / home-like class (never an after-call caller-ID, search or dialog
screen), else the most-seen class that is no step, ad or caller-ID screen (an app whose home has its own name); Language /
Permission / Intro the most-seen class of each. No app names or classes are fixed here.

Per app, per funnel: the last 60 days by day (15-day chunks, broken down by date) and the full history by month (15-month
chunks, broken down by yearMonth). Writes ga4/funnel_probe.json in the PRIVATE repo; resume; the same quota floors; the
public log stays counts-only (stderr hidden by the workflow step).
"""
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from admob_iq import ga4_probe
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_audience_probe as ap
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_d1d7_verify as vr
from admob_iq.fetch import ga4_uninstall as gu

OUT_PATH = "ga4/funnel_probe.json"
FIRST_PATH = "ga4/firstopen_probe.json"
DATA_DIR = "_private"
ALPHA = "https://analyticsdata.googleapis.com/v1alpha"
BUDGET_SEC = 22 * 60
WORKERS = 4
DAILY_DAYS = 60
CHUNK = 15                          # the funnel breakdown returns at most 15 values per call
SPLASH_WITHIN = "600s"
STEP_WITHIN = "3600s"
STEPS = ("home", "home_any", "language", "permission", "intro")
_NOT = re.compile(r"callercad|caller|audiencenetwork|adactivity|^ad[a-z]*activity$|fullscreenwebview|playcore|interstitial|"
                  r"welcome|proxy|license|about|hint|dexter|tedpermission", re.I)


def kind(c):
    """A screen class → its first-open step ('splash' / 'language' / 'permission' / 'intro' / 'home') or None."""
    l = (c or "").lower()
    if not l or l == "(not set)" or re.search(r"callercad|audiencenetwork|adactivity|^ad[a-z]*activity$|fullscreenwebview|"
                                             r"playcore|interstitial|welcome", l):
        return None
    if "lang" in l:
        return "language"
    if re.search(r"permission|consent|privacy", l):
        return "permission"
    if re.search(r"intro|onboard|tutorial|guide", l):
        return "intro"
    if re.search(r"splash|launch|start|gateway", l):
        return "splash"
    if re.search(r"main|home", l) and not re.search(r"search|dialog", l):
        return "home"
    return None


def pick_steps(disc):
    """disc = [[class, first-session users], …] → {step: class} (Splash and Home needed for the funnel)."""
    best = {}
    for c, n in disc:
        k = kind(c)
        if k and (k not in best or n > best[k][1]):
            best[k] = (c, n)
    if "home" not in best:                         # a home with its own name: the most-seen screen that is no step
        rest = [(c, n) for c, n in disc if c and c != "(not set)" and not kind(c) and not _NOT.search(c)]
        if rest:
            best["home"] = max(rest, key=lambda x: x[1])
    return {k: v[0] for k, v in best.items()}


def _screen(cls):
    return {"funnelEventFilter": {"eventName": "screen_view", "funnelParameterFilterExpression": {"funnelParameterFilter": {
        "eventParameterName": "firebase_screen_class", "stringFilter": {"matchType": "EXACT", "value": cls}}}}}


def funnel_body(splash, cls, start, end, breakdown, any_time=False):
    sp = {"name": "splash", "filterExpression": _screen(splash)}
    if not any_time:
        sp["withinDurationFromPriorStep"] = SPLASH_WITHIN
    return {"dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
            "funnel": {"isOpenFunnel": False, "steps": [
                {"name": "first_open", "filterExpression": {"funnelEventFilter": {"eventName": "first_open"}}}, sp,
                {"name": "step", "withinDurationFromPriorStep": STEP_WITHIN, "filterExpression": _screen(cls)}]},
            "funnelBreakdown": {"breakdownDimension": {"name": breakdown}, "limit": str(CHUNK)}}


def parse_table(j):
    """The funnel table → {step name: {breakdown value: activeUsers}} (the step names without GA4's '1. ' prefix)."""
    t = (j or {}).get("funnelTable") or {}
    dims = [h.get("name") for h in t.get("dimensionHeaders") or []]
    mets = [h.get("name") for h in t.get("metricHeaders") or []]
    out = {}
    for r in t.get("rows") or []:
        dv = [x.get("value") for x in r.get("dimensionValues") or []]
        mv = [x.get("value") for x in r.get("metricValues") or []]
        row = dict(zip(dims, dv))
        step = re.sub(r"^\d+\.\s*", "", str(row.get("funnelStepName") or ""))
        b = next((row[d] for d in dims if d != "funnelStepName"), "")
        users = dict(zip(mets, mv)).get("activeUsers")
        try:
            out.setdefault(step, {})[str(b)] = int(float(users or 0))
        except ValueError:
            continue
    return out


class _Alpha(ga4.Ga4App):
    """Ga4App whose runFunnelReport goes to the v1alpha Data API (stream-pinned by the report's dimensionFilter)."""

    def _post(self, method, body):
        if method != "runFunnelReport":
            return super()._post(method, body)
        if self.calls:
            ga4._sleep(ga4.PAUSE)
        self.calls += 1
        return ga4._call("POST", "%s/properties/%s:%s" % (ALPHA, self.property_id, method), self.token, body=body)


class App(pr.App, _Alpha):
    def funnel(self, body):
        body = dict(body, dimensionFilter=ga4.stream_filter(self.stream_id), returnPropertyQuota=True)
        j = self._post("runFunnelReport", body)
        self.quota = j.get("propertyQuota") or self.quota
        return j


def _chunks(start, end, step_days=None, months=None):
    """[start, end] in pieces: step_days days each, or `months` calendar months each."""
    out, a = [], start
    while a <= end:
        if step_days:
            b = min(end, a + timedelta(days=step_days - 1))
        else:
            y, m = a.year, a.month + months
            y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
            b = min(end, date(y, m, 1) - timedelta(days=1))
        out.append((a, b))
        a = b + timedelta(days=1)
    return out


def probe_unit(run, unit, token, data_dir, prop, first, raw=False):
    res = {"package": unit["package"], "property_id": unit["property_id"], "stream_id": unit["stream_id"],
           "tz": unit["tz"], "app_ids": list(unit.get("app_ids") or []), "complete": False}
    f = first.get(unit["package"]) or {}
    steps = pick_steps(f.get("disc_screens") or [])
    res["steps"] = steps
    if "splash" not in steps or "home" not in steps:
        res["err"] = "no_splash_or_home"
        return res
    aid, uni = ap.pick_store(unit, data_dir)
    if aid is None:
        res["err"] = uni
        return res
    if not token:
        res["err"] = "auth"
        return res
    today = datetime.now(ZoneInfo(unit["tz"] or "UTC")).date()
    hs = gu._d(uni["history_start"])
    res.update(app_id=aid, history_start=hs.isoformat(), end=today.isoformat(),
               not_final_from=(today - timedelta(days=1)).isoformat())
    app = App(token, unit["property_id"], unit["stream_id"], run, prop)
    t0 = run.clock()
    daily, monthly = {}, {}
    try:
        for k in [s for s in STEPS if (s if s != "home_any" else "home") in steps]:
            cls, anyt = steps["home" if k == "home_any" else k], k == "home_any"
            app.kind = "daily_" + k
            for a, b in _chunks(max(hs, today - timedelta(days=DAILY_DAYS - 1)), today, step_days=CHUNK):
                j = app.funnel(funnel_body(steps["splash"], cls, a, b, "date", anyt))
                if raw and "raw" not in res:
                    res["raw"] = {"headers": (j.get("funnelTable") or {}).get("dimensionHeaders"),
                                  "rows": ((j.get("funnelTable") or {}).get("rows") or [])[:8]}
                for step, by in parse_table(j).items():
                    for d, n in by.items():
                        if len(d) == 8 and d.isdigit():
                            daily.setdefault(k, {}).setdefault(step, {})["%s-%s-%s" % (d[:4], d[4:6], d[6:])] = n
            app.kind = "monthly_" + k
            for a, b in _chunks(date(hs.year, hs.month, 1), today, months=CHUNK):
                j = app.funnel(funnel_body(steps["splash"], cls, max(a, hs), b, "yearMonth", anyt))
                for step, by in parse_table(j).items():
                    for m, n in by.items():
                        if len(m) == 6 and m.isdigit():
                            monthly.setdefault(k, {}).setdefault(step, {})["%s-%s" % (m[:4], m[4:])] = n
        res["complete"] = True
    except pr.Stop as e:
        res["stopped"] = str(e)
    except Exception as e:
        res["err"] = pr._err(e)
    res.update(daily=daily, monthly=monthly, calls=app.calls, tokens=app.tok, by_kind=app.by_kind,
               seconds=int(run.clock() - t0))
    return res


class Run(pr.Run):
    def tick(self):
        with self.lock:
            self.calls += 1
            now = self.clock()
            beat = now - self.beat >= 60
            if beat:
                self.beat = now
            n, s = self.calls, int(now - self.t0)
        if beat:
            self.say("funnel progress: calls %d, %ds" % (n, s))


def counts(apps):
    a = list(apps.values())
    return {"apps": len(a), "complete": sum(1 for x in a if x.get("complete")),
            "stopped": sum(1 for x in a if x.get("stopped")), "errors": sum(1 for x in a if x.get("err")),
            "calls": sum(int(x.get("calls") or 0) for x in a), "tokens": sum(int(x.get("tokens") or 0) for x in a)}


def public_line(c):
    return ("funnel probe: apps %(apps)d, complete %(complete)d, stopped %(stopped)d, errors %(errors)d, "
            "calls %(calls)d, tokens %(tokens)d" % c)


def run_probe(units, data_dir, cid, sec, tokens, first, budget=BUDGET_SEC, clock=time.monotonic, workers=WORKERS,
              carried=None, raw=False):
    run = Run(budget, clock)
    rt, access = dict(tokens), {}
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
                r = probe_unit(run, u, access.get(u.get("owner") or ""), data_dir, props[u["property_id"]], first, raw)
            except Exception as e:
                r = {"package": u["package"], "crash": type(e).__name__, "complete": False}
            with lock:
                out[u["package"]] = r
                done.append(u["package"])
                n = len(done)
            run.say("funnel probe: apps %d/%d done, calls %d, %ds" % (n, len(units), run.calls, run.elapsed()))

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(one, pr._groups(units)))
    return {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rules": {"funnel": "closed: first_open → Splash (within %s) → step (within %s)" % (SPLASH_WITHIN, STEP_WITHIN),
                      "steps": "Home, and separately Language / Permission / Intro; each its own funnel",
                      "home_any": "first_open → Splash at any time after it → Home within %s (a first run in the "
                                  "background, opened later)" % STEP_WITHIN,
                      "daily": "last %d days by date" % DAILY_DAYS, "monthly": "full history by yearMonth",
                      "not_final": "the last 2 days still change in GA4"},
            "counts": counts(out), "apps": out}


def main(env=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    root = env.get("FUNNEL_DATA_DIR") or DATA_DIR
    data_dir = os.path.join(root, "data")
    units = vr.units_from_state(gu.load_state(data_dir))
    if not units:
        sys.exit("no GA4 app routes in the private state")

    def _load(path):
        try:
            with open(os.path.join(root, path), encoding="utf-8") as fh:
                return (json.load(fh) or {}).get("apps") or {}
        except (OSError, ValueError):
            return {}

    first = _load(FIRST_PATH)
    if not first:
        sys.exit("the first-open probe's report is missing")
    inputs = ap.event_inputs(env)
    resume = ap._flag(inputs.get("resume") if "resume" in inputs else env.get("FUNNEL_RESUME"))
    last = _load(OUT_PATH)
    carried = {p: r for p, r in last.items() if isinstance(r, dict) and r.get("complete")} if resume else {}
    todo = [u for u in units if u["package"] not in carried]
    cap = pr._int(inputs.get("max_apps") or env.get("FUNNEL_MAX_APPS"))
    if cap > 0:
        todo = sorted(todo, key=lambda u: (u.get("days") or 0, u["package"]))[:cap]
    print("funnel probe: %d app(s) to probe, %d carried over" % (len(todo), len(carried)), flush=True)
    budget = pr._int(env.get("FUNNEL_BUDGET_SEC")) or BUDGET_SEC
    report = run_probe(todo, data_dir, cid, sec, tokens, first, budget=budget, clock=clock, carried=carried,
                       raw=cap > 0)
    print(public_line(report["counts"]), flush=True)
    if not pr.write_private(OUT_PATH, pr._dump(report), "ga4 strict first-open funnel probe"):
        sys.exit("private repo write failed")
    print("funnel probe: report written", flush=True)


if __name__ == "__main__":
    main()
