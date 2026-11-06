"""One-off GA4 SCREENS probe, run by .github/workflows/ga4-screens-probe.yml (owner, 6 Nov 2026, on a big app's Screens
page: "ye kyu nahi he data?"). The Screens fetch (ga4_screens) keeps a day's ads-by-screen read only when GA4 gives it
whole; on the biggest apps many days come back sampled, and many more were never asked one day at a time (a shape
"dead" after three failures, or the volume gate). GA4's sampling is not a plain function of the day's events either: the
unit read was whole on a day with MORE events than a later day it came back sampled. This asks GA4 directly, ONE DAY PER
REQUEST, and keeps every answer:

  ALT    per app, on the days final_end − n (n in ALT_BACK; the nearest older day with a whole truth): every KIND — the
         fetch's own shapes and every other request GA4 offers for ads by screen (the Publisher ads report's
         publisherAdImpressions; screen path / page screen / screen name instead of class; no date dimension; no stream
         pin; the event as a dimension instead of a filter). Is any of them whole on a day the fetch's are sampled?
  SWEEP  per app, the days its store does not hold whole for the ads-by-screen read ("a"), spread evenly over its whole
         history (at most SWEEP_MAX), its TOP_WHOLE whole "a" days with the most events and its NEWEST final days:
         SWEEP_KINDS only. What decides the sampling — the day's events (the stream's, the property's), its age, neither?
  EQ     the ALT answers' top rows (KEEP_ROWS per answer, private): does another kind's per-screen split equal the
         fetch's "c" where both are whole?

Every answer: sampled (samplesReadCount, samplingSpaceSize), dataLossFromOtherRow, thresholding, rows / rowCount, the
named rows' sum, GA4's "(other)" and "(not set)" rows' sums, the tokens it cost (the response's tokensPerDay consumed)
and seconds; a refusal keeps its HTTP status class only, never the text. Each probed day also carries what the store
holds for it (the truth: TA ad_impression events by format, TE0 every event, views; the "a" and "w" records' state,
shape, tries, skip reason, sample share).

Apps: the workflow input `apps` (comma list of file keys / app ids / packages, read from the event file only), else every
app whose Screens store holds a final "a" day that is not whole, plus CONTROL: of the others, the one with the most
events on its newest whole final day (its EQ says whether another metric equals the fetch's at all).

Output: ga4/screens_probe.json in the PRIVATE repo only (dp.write_private). PUBLIC LOG: a counts-only heartbeat and ONE
result line of counts — no names, ids, dates or numbers of the data. Quota: the Screens fetch's own App and floors
(ga4_screens.quota_gate: a property stops when a token bucket is under 60 %, so the hourly builds keep theirs); one request
at a time per property, properties side by side; no request after BUDGET_SEC (what was read is still written)."""

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import ga4
from . import ga4_audience_probe as ap
from . import ga4_d1d7_probe as dp
from . import ga4_firstopen as gf
from . import ga4_screens as gs
from . import ga4_uninstall as gu

OUT = "ga4/screens_probe.json"
BUDGET_SEC = 20 * 60                    # no GA4 request after this; what was read is written
ALT_BACK = (0, 30, 95, 200)             # ALT days: final_end − n
SWEEP_MAX = 40                          # not-whole "a" days per app, evenly over its history …
TOP_WHOLE = 5                           # … its whole "a" days with the most events …
NEWEST = 5                              # … and its newest final days
LIMIT = 100000                          # rows per request (a day's split is far smaller; rowCount says if not)
KEEP_ROWS = 120                         # an ALT answer's top rows kept for EQ
WORKERS = 8                             # properties side by side
HEARTBEAT_SEC = 60
SC, PP, PS, SN = gs.SC, "unifiedPagePathScreen", "unifiedPageScreen", "unifiedScreenName"
FMT, UNIT, EVN, IMP = gs.FMT, gs.UNIT, gs.EVN, gs.IMP
EC, PUB, PV, EXP = "eventCount", "publisherAdImpressions", "screenPageViews", "adUnitExposure"
UNSET = frozenset(("(not set)", ""))
# kind → (date dimension?, dims, metric, filter): "pe" the fetch's pin (platform Android + the app's stream) + eventName
# == ad_impression · "p" the pin alone · "se" the stream + the event (no platform) · "e" the event alone (the whole
# property) · "" nothing (the whole property, every event)
KINDS = {
    "t": (True, (), EC, "pe"),              # the day's ad_impression events now (the truth the fetch ties)
    "t_all": (True, (), EC, "p"),           # every event of the stream (the fetch's TE0)
    "t_prop": (True, (), EC, ""),           # every event of the property (GA4 samples on the property's events)
    "t_stream": (True, (), EC, "se"),
    "t_nopin": (True, (), EC, "e"),
    "t_pub": (True, (), PUB, "p"),
    "t_pub_prop": (True, (), PUB, ""),
    "t_views": (True, (), PV, "p"),
    "t_exp": (True, (), EXP, "p"),
    "c": (True, (SC,), EC, "pe"),           # the fetch's "a" at its coarsest shape …
    "cf": (True, (SC, FMT), EC, "pe"),      # … at "f"
    "u": (True, (FMT, UNIT), EC, "pe"),     # the fetch's "w"
    "c_nodate": (False, (SC,), EC, "pe"),
    "pp": (True, (PP,), EC, "pe"),
    "ps": (True, (PS,), EC, "pe"),
    "sn": (True, (SN,), EC, "pe"),
    "ce": (True, (SC, EVN), EC, "p"),       # the event as a dimension, not a filter (its ad_impression rows kept)
    "c_stream": (True, (SC,), EC, "se"),
    "c_nopin": (True, (SC,), EC, "e"),
    "c_pub": (True, (SC,), PUB, "p"),
    "cf_pub": (True, (SC, FMT), PUB, "p"),
    "pp_pub": (True, (PP,), PUB, "p"),
    "ppf_pub": (True, (PP, FMT), PUB, "p"),
    "u_pub": (True, (FMT, UNIT), PUB, "p"),
    "c_pub_prop": (True, (SC,), PUB, ""),
    "v": (True, (SC,), PV, "p"),            # views by class: the fetch's "v"
    "e": (True, (SC,), EXP, "p"),           # the fetch's "e"
}
SWEEP_KINDS = ("c", "u", "t_prop")
# a split kind → the day total (a kind above) its rows must add up to: the same metric under the same filter
REF = {"c": "t", "cf": "t", "u": "t", "c_nodate": "t", "pp": "t", "ps": "t", "sn": "t", "ce": "t", "c_stream": "t_stream",
       "c_nopin": "t_nopin", "c_pub": "t_pub", "cf_pub": "t_pub", "pp_pub": "t_pub", "ppf_pub": "t_pub", "u_pub": "t_pub",
       "c_pub_prop": "t_pub_prop", "v": "t_views", "e": "t_exp"}
KEEP_KINDS = frozenset(k for k, (_, dims, _, _) in KINDS.items() if dims and dims[0] in (SC, PP, PS, SN))


def _i(v):
    return gs._i(v)


def _http_class(e):
    """A refusal → its status class only ("4xx" / "5xx" / "other"), never the text."""
    s = str(e)
    if s.startswith("HTTP 4"):
        return "4xx"
    if s.startswith("HTTP 5"):
        return "5xx"
    return "other"


def _flt(f, stream_id):
    ex = []
    if f in ("pe", "p"):
        ex.append(ga4._exact("platform", "Android"))
    if f in ("pe", "p", "se"):
        ex.append(ga4._exact("streamId", stream_id))
    if f in ("pe", "se", "e"):
        ex.append(ga4._exact("eventName", IMP))
    return {"andGroup": {"expressions": ex}} if ex else None


def request(kind, day, stream_id):
    """The runReport body of `kind` for one day."""
    dated, dims, met, f = KINDS[kind]
    b = {"dateRanges": [gu._rng(day, day)], "dimensions": ga4._dim(*((("date",) if dated else ()) + dims)),
         "metrics": ga4._dim(met), "keepEmptyRows": False, "limit": LIMIT, "returnPropertyQuota": True}
    flt = _flt(f, stream_id)
    if flt:
        b["dimensionFilter"] = flt
    return b


def measure(kind, j):
    """One answer → (its record without kind / day, {row key: value} of the rows that count). A row's key is its
    dimensions after date joined by "|"; "ce" keeps only its ad_impression rows (keyed by class)."""
    dated, dims, met, _ = KINDS[kind]
    meta = j.get("metadata") or {}
    rows = ga4._rows(j)
    rec = {"n": len(rows), "rc": _i(j.get("rowCount", len(rows))), "loss": bool(meta.get("dataLossFromOtherRow")),
           "thr": bool(meta.get("subjectToThresholding"))}
    sm = [s or {} for s in meta.get("samplingMetadatas") or []]
    if sm:
        space = sum(_i(s.get("samplingSpaceSize")) for s in sm)
        read = sum(_i(s.get("samplesReadCount")) for s in sm)
        rec.update(s=True, space=space, read=read, smp=round(read / float(space), 4) if space else None)
    q = j.get("propertyQuota") or {}
    rec["tok"] = _i((q.get("tokensPerDay") or {}).get("consumed"))
    vals, named, fold, unset = {}, 0, 0, 0
    for r in rows:
        if kind == "ce":
            if str(r.get(EVN)) != IMP:
                continue
            key = (str(r.get(SC) if r.get(SC) is not None else ""),)
        else:
            key = tuple(str(r.get(d) if r.get(d) is not None else "") for d in dims)
        v = _i(r.get(met))
        if any(gs._isfold(x) for x in key):
            fold += v
        elif dims and any(x.strip().lower() in UNSET for x in key):
            unset += v
        else:
            named += v
        k = "|".join(key)
        vals[k] = vals.get(k, 0) + v
    rec.update(sum=named, fold=fold, unset=unset)
    return rec, vals


def ask(ga, run, kind, day, stream_id):
    """One GA4 answer for one day → (record, row values or None). gf.Stop passes up (the property stops, the run goes
    on with the others); any other refusal is kept as its HTTP class."""
    rec = {"k": kind, "d": day.isoformat()}
    t0 = time.monotonic()
    try:
        j = ga._post("runReport", request(kind, day, stream_id))
    except gf.Stop:
        raise
    except Exception as e:                              # noqa: BLE001 — a refusal is data here, never fatal
        run.count(rec.setdefault("http", _http_class(e)))
        return rec, None
    m, vals = measure(kind, j)
    rec.update(m, sec=round(time.monotonic() - t0, 2))
    run.count("s" if rec.get("s") else "loss" if rec.get("loss") else "ok", rec.get("tok"))
    return rec, vals


class Run(dp.Run):
    """dp.Run's clock and counts-only heartbeat, with this probe's own counters."""

    def __init__(self, budget=BUDGET_SEC, clock=time.monotonic):
        super().__init__(budget, clock)
        self.c = dict.fromkeys(("ok", "s", "loss", "4xx", "5xx", "other", "tok", "stopped"), 0)

    def count(self, what, tok=None):
        """One answer (or refusal) of kind `what`; the call is ticked."""
        self.bump(what, tok)
        self.tick()

    def bump(self, what, tok=None):
        with self.lock:
            self.c[what] = self.c.get(what, 0) + 1
            self.c["tok"] += _i(tok)

    def tick(self):
        with self.lock:
            self.calls += 1
            now = self.clock()
            beat = now - self.beat >= HEARTBEAT_SEC
            if beat:
                self.beat = now
            n, s = self.calls, int(now - self.t0)
        if beat:
            self.say("screens probe progress: calls %d, %ds" % (n, s))


# ── the store side ──────────────────────────────────────────────────────────────────────────────────────────────────
def store_days(data_dir, key):
    """An app's final records of the core reads → {day: {read id: record}}."""
    out = {}
    for _, _, days in gs.iter_months(data_dir, key, "core"):
        for d, recs in days.items():
            out.setdefault(d, {}).update(recs)
    return out


def _brief(rec):
    return {k: rec[k] for k in ("st", "g", "tried", "skip", "smp", "cov", "f") if isinstance(rec, dict) and k in rec}


def day_info(recs):
    """What the store holds for a day (the probe's comparison side; private)."""
    t = recs.get("t") or {}
    taf = {str(f): _i(n) for f, n in t.get("a") or ()}
    return {"ev": t.get("ev"), "ta": sum(taf.values()), "taf": taf, "views": (t.get("v") or [None])[0],
            "a": _brief(recs.get("a")), "w": _brief(recs.get("w"))}


def evenly(xs, n):
    """At most n items of xs, spread evenly (its first and last kept)."""
    if len(xs) <= n:
        return list(xs)
    if n <= 1:
        return list(xs[-1:])
    return [xs[round(i * (len(xs) - 1) / float(n - 1))] for i in range(n)]


def plan(days, final_end):
    """{day: recs} of the store → (ALT days, SWEEP days) — final days with a whole truth only, ISO, newest first."""
    fe = final_end.isoformat()
    ok = sorted(d for d, r in days.items() if d <= fe and gs._whole(r.get("t")))
    if not ok:
        return [], []
    alt = []
    for n in ALT_BACK:
        want = (final_end - timedelta(days=n)).isoformat()
        older = [d for d in ok if d <= want]
        if older and older[-1] not in alt:
            alt.append(older[-1])
    bad = [d for d in ok if not gs._whole(days[d].get("a"))]
    top = sorted((d for d in ok if gs._whole(days[d].get("a"))), key=lambda d: -_i((days[d].get("t") or {}).get("ev")))
    sweep = set(evenly(bad, SWEEP_MAX)) | set(top[:TOP_WHOLE]) | set(ok[-NEWEST:])
    return alt, sorted(sweep, reverse=True)


def _final_end(tz, now):
    try:
        today = now.astimezone(ZoneInfo(tz or "UTC")).date()
    except Exception:                                   # noqa: BLE001 — an unknown zone reads as UTC
        today = now.astimezone(timezone.utc).date()
    return today - timedelta(days=gs.FINAL_LAG)


def choose(data_dir, now, want=None):
    """The app keys to probe: `want` (a set of lower-case tokens) when given, else every app with a final "a" day not
    whole + the CONTROL app → ([key], control key or None)."""
    keys = gs.store_keys(data_dir)
    if want:
        out = []
        for k in keys:
            m = gs.load_meta(data_dir, k) or {}
            if {k, str(m.get("app_id") or "").lower(), str(m.get("package") or "").lower()} & set(want):
                out.append(k)
        return out, None
    bad, ctrl, best = [], None, -1
    for k in keys:
        m = gs.load_meta(data_dir, k) or {}
        days = store_days(data_dir, k)
        fe = _final_end(m.get("time_zone"), now).isoformat()
        ok = [d for d in sorted(days) if d <= fe and gs._whole(days[d].get("t"))]
        if any(not gs._whole(days[d].get("a")) for d in ok):
            bad.append(k)
        elif ok:
            ev = _i((days[ok[-1]].get("t") or {}).get("ev"))
            if ev > best:
                ctrl, best = k, ev
    return bad + ([ctrl] if ctrl else []), ctrl


# ── one app ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def probe_app(ga, run, it, data_dir, now, keep):
    """One app: ALT (every kind on its ALT days) then SWEEP → its private result. gf.Stop ends it (kept so far)."""
    key = gu.file_key(it["a"]["app_id"])
    sid = it["r"]["stream_id"]
    days = store_days(data_dir, key)
    fe = _final_end(it.get("tz"), now)
    alt, sweep = plan(days, fe)
    res = {"final_end": fe.isoformat(), "alt": alt, "sweep": sweep, "ans": [], "rows": {}, "days": {},
           "stopped": None}
    for d in set(alt) | set(sweep):
        res["days"][d] = day_info(days.get(d) or {})
    todo = [(k, d) for d in alt for k in KINDS] + [(k, d) for d in sweep if d not in alt for k in SWEEP_KINDS]
    try:
        for k, d in todo:
            rec, vals = ask(ga, run, k, gu._d(d), sid)
            res["ans"].append(rec)
            if vals and k in keep and d in alt:
                res["rows"]["%s|%s" % (k, d)] = dict(sorted(vals.items(), key=lambda kv: -kv[1])[:KEEP_ROWS])
    except gf.Stop as e:
        res["stopped"] = (e.args or ["stop"])[0]
        run.bump("stopped")
    return res


def summary(apps):
    """Per kind: answers, sampled, loss, refused, and "tie": its rows (named + "(other)" + "(not set)") within the
    fetch's tolerance of the same day's REF total, when that total came back unsampled (tie_n) — counts only."""
    out = {}
    for res in apps.values():
        tot = {(r["k"], r["d"]): r["sum"] + r["fold"] + r["unset"] for r in res["ans"]
               if r["k"].startswith("t") and "sum" in r and not r.get("s")}
        for r in res["ans"]:
            s = out.setdefault(r["k"], {"n": 0, "s": 0, "loss": 0, "refused": 0, "tie": 0, "tie_n": 0})
            s["n"] += 1
            if r.get("http"):
                s["refused"] += 1
                continue
            s["s"] += 1 if r.get("s") else 0
            s["loss"] += 1 if r.get("loss") else 0
            want = tot.get((REF.get(r["k"]), r["d"]))
            if want and not r.get("s"):
                s["tie_n"] += 1
                if abs(r["sum"] + r["fold"] + r["unset"] - want) <= max(gs.TIE_REL * want, gs.TIE_ABS):
                    s["tie"] += 1
    return out


def run_all(cfg, data_dir, apps_want, now=None, clock=time.monotonic, budget=BUDGET_SEC, workers=WORKERS):
    """Every chosen app → {"v", "at", "control", "apps": {key: result}, "summary", "counts"}. Never raises."""
    now = now or datetime.now(timezone.utc)
    run = Run(budget, clock)
    out = {"v": 1, "at": now.isoformat(), "control": None, "apps": {}, "summary": {}, "counts": run.c}
    try:
        keys, ctrl = choose(data_dir, now, apps_want)
        out["control"] = ctrl
        apps = gs.bf_apps(data_dir, set(keys))
        counts = dict.fromkeys(gs.BF_COUNTS, 0)
        by_prop = gs._select(cfg, data_dir, apps, now, gs.load_state(data_dir), counts, {"apps": {}}, retry=False,
                             clock=clock)
        lock = threading.Lock()

        def one(pid):
            prop = {"quota": None, "stop": None, "stops": 0}
            for it in sorted(by_prop[pid], key=lambda t: t["a"]["app_id"]):
                if not it["tok"]:
                    continue
                ga = gs.App(it["tok"], pid, it["r"]["stream_id"], prop, over=run.over, max_calls=10 ** 6,
                            gate=gs.quota_gate, renew=it.get("renew"))
                res = probe_app(ga, run, it, data_dir, now, KEEP_KINDS)
                with lock:
                    out["apps"][gu.file_key(it["a"]["app_id"])] = res
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            for f in [ex.submit(one, pid) for pid in sorted(by_prop)]:
                try:
                    f.result()
                except Exception:                       # noqa: BLE001 — one property's trouble never ends the probe
                    run.count("other")
        out["summary"] = summary(out["apps"])
    except Exception as e:                              # noqa: BLE001 — what was read is still written
        out["error"] = type(e).__name__
    return out


def line(out):
    """The ONE public result line — counts only."""
    c = out.get("counts") or {}
    return ("screens probe: apps %d, calls %d, tokens %d, sampled %d, loss %d, refused %d, stopped %d%s"
            % (len(out.get("apps") or {}), sum(_i(c.get(k)) for k in ("ok", "s", "loss", "4xx", "5xx", "other")),
               _i(c.get("tok")), _i(c.get("s")), _i(c.get("loss")), sum(_i(c.get(k)) for k in ("4xx", "5xx", "other")),
               _i(c.get("stopped")), (", error " + out["error"]) if out.get("error") else ""))


def main(env=None, now=None):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    if not (cid and sec and (env.get("GA4_REFRESH_TOKENS") or env.get("GA4_REFRESH_TOKEN"))):
        sys.exit("GA4 client or refresh tokens missing")
    data_dir = os.path.join(env.get("SCREENS_PROBE_DATA_DIR") or gs.DATA_ROOT, "data")
    cfg = {"client_id": cid, "client_secret": sec, "refresh_tokens": env.get("GA4_REFRESH_TOKENS") or "",
           "refresh_token": env.get("GA4_REFRESH_TOKEN") or ""}
    out = run_all(cfg, data_dir, ap.wanted(ap.event_inputs(env).get("apps")), now=now)
    ok = dp.write_private(OUT, json.dumps(out, separators=(",", ":"), sort_keys=True),
                          "screens probe %s UTC" % time.strftime("%Y-%m-%d %H:%M", time.gmtime()))
    print(line(out) + (", written" if ok else ", NOT written"), flush=True)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
