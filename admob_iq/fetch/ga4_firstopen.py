"""🆕 First open — the hourly fetch (owner, 13 Oct 2026: "user splash screen se home screen tak kitne pahunch rahe hain for
the first time", every feature on the FULL history, and "splash se home user zyada nahi ho sakta").

GA4's funnel report (Data API v1alpha runFunnelReport, a CLOSED funnel — every step in order) per app per day:
    first_open → Splash (within 10 min) → <step> (within 60 min)
for <step> = Home, and separately Language / Permission / Intro (each its own funnel, so a step never exceeds the
Splash); and Home once more with the Splash at ANY time after first_open ("home_any": an app first run in the
background — an after-call screen, a push — and opened by the user later).

GA4 keeps event data only as long as the property's retention (2 months by default), and a funnel is built from event
data — so this store is the history: each app's days are kept here for good (data/ga4_firstopen/<key>.json.gz in the
private repo, never trimmed). Per app and run (at most MAX_CALLS calls; a property under its quota floors waits):
  * the screens: first-session users by screen class over the last 28 days (screen_view, newVsReturning == new) →
    pick_steps (generic: no app names or classes are fixed), looked at again every STEPS_DAYS days;
  * a one-time backfill of what GA4 still has (BACKFILL_DAYS back, 15-day chunks broken down by date, resumable);
  * every REFRESH_HOURS the last 15 days again (the last two still change in GA4).
Switched by the repo variable GA4_FIRSTOPEN (off by default). Never raises; never prints (log_line: counts only).
"""
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import ga4_probe
from ..db import write_json_gz_stable
from . import ga4
from . import ga4_audience as gaud
from . import ga4_uninstall as gu

DIR = "ga4_firstopen"
STORE_V = 1
ALPHA = "https://analyticsdata.googleapis.com/v1alpha"
CHUNK = 15                          # the funnel breakdown returns at most 15 values per call
RECENT_DAYS = 15                    # refreshed every REFRESH_HOURS (today … 14 days back)
BACKFILL_DAYS = 120                 # asked once, back from today (GA4 has what its retention kept)
REFRESH_HOURS = 6.0
STEPS_DAYS = 7
DISC_DAYS = 28
MAX_CALLS = 30                      # per app per run (the backfill goes on next run)
BUDGET_SEC = 150
RETRY_HOURS = 3.0
SPLASH_WITHIN = "600s"
STEP_WITHIN = "3600s"
FUNNELS = ("home", "home_any", "language", "permission", "intro")
FIELDS = ("first_open", "splash", "home", "splash_any", "home_any", "language", "permission", "intro")
_NOT_HOME = re.compile(r"callercad|caller|audiencenetwork|adactivity|^ad[a-z]*activity$|fullscreenwebview|playcore|"
                       r"interstitial|welcome|proxy|license|about|hint|dexter|tedpermission", re.I)


class Stop(Exception):
    """This app's read stops here (quota floor, the run's budget, its call cap); what was read is kept."""


# ── the screens (generic) ───────────────────────────────────────────────────────────────────────────────────────────
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
    """disc = [[class, first-session users], …] → {step: class}: the most-seen class of each step; Home with its own
    name (no main/home in it) = the most-seen screen that is no step, ad or caller-ID screen."""
    best = {}
    for c, n in disc:
        k = kind(c)
        if k and (k not in best or n > best[k][1]):
            best[k] = (c, n)
    if "home" not in best:
        rest = [(c, n) for c, n in disc if c and c != "(not set)" and not kind(c) and not _NOT_HOME.search(c)]
        if rest:
            best["home"] = max(rest, key=lambda x: x[1])
    return {k: v[0] for k, v in best.items()}


# ── the funnel ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _screen(cls):
    return {"funnelEventFilter": {"eventName": "screen_view", "funnelParameterFilterExpression": {"funnelParameterFilter": {
        "eventParameterName": "firebase_screen_class", "stringFilter": {"matchType": "EXACT", "value": cls}}}}}


def funnel_body(splash, cls, start, end, breakdown="date", any_time=False):
    sp = {"name": "splash", "filterExpression": _screen(splash)}
    if not any_time:
        sp["withinDurationFromPriorStep"] = SPLASH_WITHIN
    return {"dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
            "funnel": {"isOpenFunnel": False, "steps": [
                {"name": "first_open", "filterExpression": {"funnelEventFilter": {"eventName": "first_open"}}}, sp,
                {"name": "step", "withinDurationFromPriorStep": STEP_WITHIN, "filterExpression": _screen(cls)}]},
            "funnelBreakdown": {"breakdownDimension": {"name": breakdown}, "limit": str(CHUNK)}}


def parse_table(j):
    """The funnel table → {step name: {breakdown value: activeUsers}} (step names without GA4's '1. ' prefix)."""
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
        try:
            out.setdefault(step, {})[str(b)] = int(float(dict(zip(mets, mv)).get("activeUsers") or 0))
        except ValueError:
            continue
    return out


def sampling(j):
    """GA4's sampling of a funnel answer → the share of events it read (0 … 1), or None (not sampled / not said)."""
    best = None
    for m in (((j or {}).get("funnelTable") or {}).get("metadata") or {}).get("samplingMetadatas") or []:
        try:
            r = float(m.get("samplesReadCount")) / float(m.get("samplingSpaceSize"))
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if 0 < r < 1:
            best = round(r if best is None else min(best, r), 4)
    return best


def _chunks(start, end, n=CHUNK):
    out, a = [], start
    while a <= end:
        b = min(end, a + timedelta(days=n - 1))
        out.append((a, b))
        a = b + timedelta(days=1)
    return out


class App(ga4.Ga4App):
    """Stream-pinned GA4 reads (runReport v1beta, runFunnelReport v1alpha) that first pass the PROPERTY's quota gate (the
    Audience fetch's floors), the run's clock and the app's call cap — raising Stop — and count tokens."""

    def __init__(self, token, property_id, stream_id, prop, over=None, max_calls=MAX_CALLS):
        super().__init__(token, property_id, stream_id)
        self.prop, self.over, self.max_calls, self.tok = prop, over, max_calls, 0

    def _post(self, method, body):
        why = self.prop.get("stop") or (self.over() if self.over else None) or gaud.quota_stop(self.prop.get("quota"))
        if why:
            self.prop["stop"] = self.prop.get("stop") or (why if why != "budget" else None)
            raise Stop(why)
        if self.calls >= self.max_calls:
            raise Stop("calls")
        if method != "runFunnelReport":
            j = super()._post(method, body)
        else:
            if self.calls:
                ga4._sleep(ga4.PAUSE)
            self.calls += 1
            j = ga4._call("POST", "%s/properties/%s:%s" % (ALPHA, self.property_id, method), self.token, body=body)
        q = j.get("propertyQuota")
        if q:
            self.prop["quota"] = q
            self.tok += gaud._int((q.get("tokensPerDay") or {}).get("consumed"))
        return j

    def funnel(self, body):
        return self._post("runFunnelReport", dict(body, dimensionFilter=ga4.stream_filter(self.stream_id),
                                                  returnPropertyQuota=True))


def discover(ga, today):
    rows = ga.report_all({"dateRanges": [{"startDate": (today - timedelta(days=DISC_DAYS)).isoformat(),
                                          "endDate": today.isoformat()}],
                          "dimensions": [{"name": "unifiedScreenClass"}], "metrics": [{"name": "activeUsers"}],
                          "orderBys": [{"metric": {"metricName": "activeUsers"}, "desc": True}]},
                         event="screen_view",
                         extra=[{"filter": {"fieldName": "newVsReturning", "stringFilter": {"matchType": "EXACT", "value": "new"}}}])
    return [[r.get("unifiedScreenClass"), int(r.get("activeUsers") or 0)] for r in rows]


def read_chunk(ga, steps, a, b):
    """Every funnel of the app for days a … b → {YYYY-MM-DD: {field: users}} (only the days GA4 answered). GA4 leaves
    out a step's row on a day nobody reached it: a day the funnel HAS (its first_open row) counts that step as 0."""
    days = {}

    def put(d, k, v):
        if len(d) == 8 and d.isdigit():
            days.setdefault("%s-%s-%s" % (d[:4], d[4:6], d[6:]), {})[k] = v
    for f in FUNNELS:
        step = "home" if f == "home_any" else f
        if step not in steps:
            continue
        j = ga.funnel(funnel_body(steps["splash"], steps[step], a, b, "date", any_time=f == "home_any"))
        t, smp = parse_table(j), sampling(j)
        fo, sp, st = t.get("first_open") or {}, t.get("splash") or {}, t.get("step") or {}
        for d in set(fo) | set(sp) | set(st):
            put(d, f, st.get(d, 0))
            if smp is not None and len(d) == 8:
                r = days["%s-%s-%s" % (d[:4], d[4:6], d[6:])]
                r["sample"] = min(r.get("sample", 1.0), smp)
            if f == "home":
                put(d, "first_open", fo.get(d, 0))
                put(d, "splash", sp.get(d, 0))
            if f == "home_any":
                put(d, "splash_any", sp.get(d, 0))
    return days


def step_app(ga, store, today, hs, now):
    """One app's run on its store → "fetched" (something read), "fresh" (nothing due) or "no_steps". Raises Stop."""
    did, now_iso = False, gu._now_iso(now)
    if not store.get("steps") or gu._hours_since(store.get("steps_at"), now) >= STEPS_DAYS * 24:
        steps = pick_steps(discover(ga, today))
        if "splash" in steps and "home" in steps:
            if store.get("steps") and store["steps"] != steps:
                store.setdefault("steps_changed", []).append({"at": today.isoformat(), "from": store["steps"]})
            store["steps"] = steps
        store["steps_at"] = now_iso
        did = True
    steps = store.get("steps") or {}
    if "splash" not in steps or "home" not in steps:
        return "no_steps"
    days = store.setdefault("days", {})
    recent = today - timedelta(days=RECENT_DAYS - 1)
    bf = store.setdefault("backfill", {})
    if not bf.get("done"):
        nxt = gu._d(bf["next"]) if bf.get("next") else max(hs, today - timedelta(days=BACKFILL_DAYS))
        bf.setdefault("from", nxt.isoformat())
        for a, b in _chunks(nxt, recent - timedelta(days=1)):
            for d, rec in read_chunk(ga, steps, a, b).items():
                days.setdefault(d, {}).update(rec)
            bf["next"] = (b + timedelta(days=1)).isoformat()
            did = True
        bf["done"] = True
    if gu._hours_since(store.get("recent_at"), now) >= REFRESH_HOURS:
        for d, rec in read_chunk(ga, steps, max(hs, recent), today).items():
            days[d] = rec                               # the newest read of a still-changing day wins
        store["recent_at"] = now_iso
        did = True
    return "fetched" if did else "fresh"


# ── store and state ─────────────────────────────────────────────────────────────────────────────────────────────────
def store_path(data_dir, app_id):
    return os.path.join(data_dir, DIR, gu.file_key(app_id) + ".json.gz")


def load_store(path):
    s = gu.load_store(path)
    return s if isinstance(s, dict) and s.get("v") == STORE_V else None


def load_state(data_dir):
    try:
        with open(os.path.join(data_dir, DIR, "state.json"), encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict) and isinstance(raw.get("fetch"), dict):
            return raw
    except (OSError, ValueError):
        pass
    return {"v": 1, "fetch": {}}


def save_state(data_dir, state):
    path = os.path.join(data_dir, DIR, "state.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=1)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return True


COUNTS = ("selected", "with_ga4", "fetched", "fresh", "no_steps", "failed", "deferred", "waiting", "calls", "tokens")


def refresh_all(cfg, data_dir, apps, now=None, clock=time.monotonic, budget=BUDGET_SEC):
    """Every selected app (uninstall_build's list) → {"counts", "apps": {app id: fetched|fresh|no_steps|failed|deferred|
    waiting}}. Never raises; never prints."""
    now = now or datetime.now(timezone.utc)
    t0 = clock()
    counts = dict.fromkeys(COUNTS, 0)
    out = {"counts": counts, "apps": {}}
    try:
        state = load_state(data_dir)
        ust = gu.load_state(data_dir)
        routes = ust["routes"].get("by_package") or {}
        tokens, _ = ga4_probe.owner_tokens({"GA4_REFRESH_TOKENS": cfg.get("refresh_tokens") or "",
                                            "GA4_REFRESH_TOKEN": cfg.get("refresh_token") or ""})
        owner_rt, access, props = dict(tokens), {}, {}
        now_iso = gu._now_iso(now)

        def over():
            return "budget" if clock() - t0 >= budget else None
        todo = []
        for a in apps:
            if a.get("same_as") or not a.get("package"):
                continue
            counts["selected"] += 1
            r = routes.get(a["package"])
            if not r:
                continue
            counts["with_ga4"] += 1
            aid = a["app_id"]
            um = gaud._uni_meta(ust, data_dir, aid, r)
            if not um:
                out["apps"][aid] = "waiting"
                continue
            st = state["fetch"].setdefault(aid, {})
            if st.get("fail") and gu._hours_since(st.get("last_try"), now) < RETRY_HOURS:
                out["apps"][aid] = "failed"
                continue
            todo.append((a, st, r, gu._d(um["history_start"])))
        todo.sort(key=lambda t: (not t[1].get("deferred"), t[1].get("last_ok") or "", t[0]["app_id"]))
        for a, st, r, hs in todo:
            aid, pid = a["app_id"], r["property_id"]
            prop = props.setdefault(pid, {"quota": None, "stop": None})
            if over() or prop["stop"]:
                st["deferred"] = True
                out["apps"][aid] = "deferred"
                continue
            owner = r.get("owner")
            if owner not in access:
                try:
                    access[owner] = (ga4.access_token(cfg["client_id"], cfg["client_secret"], owner_rt[owner])
                                     if owner in owner_rt else None)
                except Exception:
                    access[owner] = None
            if not access.get(owner):
                st.update(last_try=now_iso, fail="auth")
                out["apps"][aid] = "failed"
                continue
            tz = ust["tz"].get(pid) or "UTC"
            today = now.astimezone(ZoneInfo(tz)).date()
            path = store_path(data_dir, aid)
            store = load_store(path) or {"v": STORE_V}
            ga = App(access[owner], pid, r["stream_id"], prop, over=over)
            try:
                res = step_app(ga, store, today, hs, now)
                st.pop("deferred", None)
                st.update(last_try=now_iso, fail=None)
                if res == "fetched":
                    st["last_ok"] = now_iso
                out["apps"][aid] = res
            except Stop:
                st["deferred"] = True
                out["apps"][aid] = "deferred"
            except Exception as e:
                st.update(last_try=now_iso, fail=gu._fail_kind(e))
                out["apps"][aid] = "failed"
            finally:
                if ga.calls:
                    store.update(v=STORE_V, app_id=aid, package=a["package"], property_id=pid, stream_id=r["stream_id"],
                                 time_zone=tz)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    write_json_gz_stable(path, store)
                st["key"] = gu.file_key(aid)
                counts["calls"] += ga.calls
                counts["tokens"] += ga.tok
        save_state(data_dir, state)
    except Exception as e:                              # a bug here must never cost the build
        out["error"] = type(e).__name__
    for v in out["apps"].values():
        if v in counts:
            counts[v] += 1
    return out


def log_line(status):
    """The build log's ONE line for this step — counts only."""
    c = (status or {}).get("counts") or {}
    return ("ga4 first open: apps %d, with GA4 %d, fetched %d, fresh %d, no screens %d, failed %d, deferred %d, waiting %d, "
            "calls %d, tokens %d%s" % tuple([gaud._int(c.get(k)) for k in ("selected", "with_ga4", "fetched", "fresh",
                                                                             "no_steps", "failed", "deferred", "waiting",
                                                                             "calls", "tokens")]
                                            + [(", error " + status["error"]) if (status or {}).get("error") else ""]))
