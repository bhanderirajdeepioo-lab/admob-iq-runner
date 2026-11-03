"""One-off GA4 REVENUE BY SOURCE SPLIT probe, run by .github/workflows/ga4-srcsplit-probe.yml: before the 📈 ROI tabs
show the 💰 Revenue by source split per row (owner, 3 Nov 2026: Paid / Notification / Organic / Other per country, per
phone model, per install day), measure per app whether GA4 answers the session channel crossed with countryId, the phone
model and the install day (firstSessionDate) WHOLE — each split read tied to its truth (the same read without the split)
and, key by key, to the same read without the channel. The earlier model / install-day reads lost a part to "(other)" on
the biggest apps; this measures the channel reads before anything is built. Read-only against GA4 and against the PRIVATE
repo's data (the Uninstall state's routes); the only write is ga4/srcsplit_probe.json in the PRIVATE repo.

Window W = [F − DAYS + 1, F] (not before the app's history start), F = the app's day − LATE; X = W's first day (an
install day whose users are 0 … DAYS − 1 days old at F). Reads (USD; METS = totalRevenue, sessions):
  T      W   no dimension                                       the truth of the W reads
  CH     W   channel                                            the app's split (the 💰 section's own shape)
  C      W   countryId
  CHC    W   channel × countryId                                Countries, W as one
  CHCD   W   channel × countryId × date                         Countries, day by day (what a daily store holds)
  M      W   model
  CHM    W   channel × model                                    Devices, W as one
  T1     F   no dimension                                       the truth of CHM1
  CHM1   F   channel × model                                    Devices, one day
  FS     W   firstSessionDate ∈ W                               the install days' revenue in W
  CHF    W   channel × firstSessionDate ∈ W                     Day-wise ROI: per install day
  XT     W   no dimension, firstSessionDate == X                the truth of the X reads
  XC     W   countryId, firstSessionDate == X
  XCHC   W   channel × countryId, firstSessionDate == X         Countries board: a period's installs → their revenue
  XM     W   model, firstSessionDate == X
  XCHM   W   channel × model, firstSessionDate == X             Devices board: the same per model
A record: accepted or the HTTP class, rows, the "(other)" / "(not set)" shares, the flags (thresholding / sampling /
dataLossFromOtherRow), "tie" (Σ ÷ its truth per metric) and, for a channel split of a dimension read (PAIRS), "keys" per
metric (device probe tie_by: overall, p10 / p90, keys off by > 2 %) with "w2" = the truth's share held by keys within 2 %.
"facts": the four groups' revenue / session shares (source_build.group_of) for the app, the top TOP countries and models
by revenue (W and X) and every install day of W.

PUBLIC LOG: counts only (per read kind: n, ok, refused, ties under 0.98, with "(other)"); stderr hidden by the workflow.
"""

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from admob_iq import ga4_probe
from admob_iq import source_build as sb
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_audience_probe as ap
from admob_iq.fetch import ga4_country_probe as cp
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_device_probe as dp
from admob_iq.fetch import ga4_shape_probe as sp
from admob_iq.fetch import ga4_uninstall as gu
from admob_iq.fetch.ga4_d1d7_probe import Stop

LATE = gu.IDAY_LATE
DAYS = 28
CHN, CTY, MODEL, FSD = "sessionDefaultChannelGroup", "countryId", dp.MODEL, "firstSessionDate"
METS = ("totalRevenue", "sessions")
REV = METS[0]
# kind → (span: "W" the window | "F" its last day, dimensions, install-day filter: None | "W" ∈ W | "X" == X)
READS = (("T", "W", (), None), ("CH", "W", (CHN,), None), ("C", "W", (CTY,), None), ("CHC", "W", (CHN, CTY), None),
         ("CHCD", "W", (CHN, CTY, "date"), None), ("M", "W", (MODEL,), None), ("CHM", "W", (CHN, MODEL), None),
         ("T1", "F", (), None), ("CHM1", "F", (CHN, MODEL), None),
         ("FS", "W", (FSD,), "W"), ("CHF", "W", (CHN, FSD), "W"),
         ("XT", "W", (), "X"), ("XC", "W", (CTY,), "X"), ("XCHC", "W", (CHN, CTY), "X"),
         ("XM", "W", (MODEL,), "X"), ("XCHM", "W", (CHN, MODEL), "X"))
TRUTH = {"CH": "T", "C": "T", "CHC": "T", "CHCD": "T", "M": "T", "CHM": "T", "CHM1": "T1", "CHF": "FS",
         "XC": "XT", "XCHC": "XT", "XM": "XT", "XCHM": "XT"}
PAIRS = {"CHC": ("C", CTY), "CHM": ("M", MODEL), "CHF": ("FS", FSD), "XCHC": ("XC", CTY), "XCHM": ("XM", MODEL)}
TOP = 15
TIE_OK = 0.98
MAX_CALLS = 1500
APP_CALLS = 48                      # 16 planned an app: room for pages
WORKERS = 4
BUDGET_SEC = 20 * 60                # no new call after 20 min (the job's timeout is 45)
TICK_SEC = 20
PAGE_ROWS = 100000
DATA_DIR = "_private"
OUT_PATH = "ga4/srcsplit_probe.json"


class Run(dp.Run):
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
            self.say("srcsplit progress: calls %d, %ds" % (n, s))


def _fsd(x):
    return {"filter": {"fieldName": FSD, "stringFilter": {"matchType": "EXACT", "value": pr._ymd(x)}}}


def plan_of(u, now):
    """One app's dates: F, W = [a, F] (not before the history start) and X = a; None when W is empty."""
    f = ga4.window_end_in(u["tz"], now) - timedelta(days=LATE)
    a = f - timedelta(days=DAYS - 1)
    hs = gu._d(u["history_start"]) if u.get("history_start") else None
    if hs and a < hs:
        a = hs
    return None if a > f else {"F": f, "a": a, "x": a, "wdays": [pr._ymd(a + timedelta(days=i))
                                                               for i in range((f - a).days + 1)]}


def request(kind, p):
    """kind → (body, extra filter expressions)."""
    span, dims, fs = next((s, d, x) for k, s, d, x in READS if k == kind)
    a, b = (p["a"], p["F"]) if span == "W" else (p["F"], p["F"])
    extra = [ga4._in_list(FSD, p["wdays"])] if fs == "W" else [_fsd(p["x"])] if fs == "X" else []
    return dp._body(a, b, dims, METS), extra


def keys_tie(got, want, key):
    """Per key of a channel split vs the same read without the channel: device probe tie_by per metric + "w2" (the
    truth's share held by keys within 2 %)."""
    out = {}
    for m in METS:
        t = dp.tie_by(got, want, key, m)
        g, w = dp._by(got, key, m), dp._by(want, key, m)
        tot = sum(v for v in w.values() if v > 0)
        t["w2"] = pr._ratio(sum(v for k, v in w.items() if v > 0 and abs(g.get(k, 0) / v - 1) <= 0.02), tot)
        out[m] = t
    return out


def _groups(rows, key=None):
    """rows → {key value: [revenue, sessions] per group (Paid, Notification, Organic, Other)} ({None: …} without key)."""
    out = {}
    for r in rows or []:
        e = out.setdefault(r.get(key) if key else None, [[0.0, 0.0] for _ in range(4)])
        g = e[sb.group_of(str(r.get(CHN) or ""))]
        g[0] += dp._num(r.get(REV))
        g[1] += dp._num(r.get("sessions"))
    return out


def _split(e):
    """[[rev, ses] × 4] → {"rev": total, "ses": total, "r": [4 revenue shares], "s": [4 session shares]}."""
    rt, st = sum(x[0] for x in e), sum(x[1] for x in e)
    return {"rev": round(rt, 2), "ses": int(st), "r": [pr._ratio(x[0], rt) for x in e],
            "s": [pr._ratio(x[1], st) for x in e]}


def facts(got):
    """The groups' shares: the app (CH), the top TOP countries / models by revenue (CHC / CHM, XCHC / XCHM) and each
    install day of W (CHF)."""
    out = {}
    if "CH" in got:
        out["app"] = _split(_groups(got["CH"])[None])
    for kind, key in (("CHC", CTY), ("CHM", MODEL), ("XCHC", CTY), ("XCHM", MODEL)):
        if kind in got:
            g = _groups(got[kind], key)
            top = sorted(g.items(), key=lambda kv: -sum(x[0] for x in kv[1]))[:TOP]
            out[kind] = [[str(k), _split(e)] for k, e in top]
    if "CHF" in got:
        out["CHF"] = [[str(k), _split(e)] for k, e in sorted(_groups(got["CHF"], FSD).items())]
    return out


def probe_app(run, u, token, now, prop, opts):
    p = plan_of(u, now)
    res = {"key": u["key"], "reads": {}}
    if p is None:
        res.update(complete=True, empty=True)
        return res
    res.update(F=p["F"].isoformat(), X=p["x"].isoformat())
    if not token:
        res.update(err={"type": "auth"}, complete=False)
        return res
    ga = cp.App(token, u["property_id"], u["stream_id"], run, prop, cap=opts.get("app_calls", APP_CALLS))
    got = {}
    try:
        for kind, _s, dims, _f in READS:
            body, extra = request(kind, p)
            rec, rows = cp._read(ga, kind, lambda: ga.report_all(body, extra=extra, page_rows=PAGE_ROWS),
                                 dp.p_rows(dims, METS))
            if rec.get("ok"):
                got[kind] = rows
                t = TRUTH.get(kind)
                if t in got:
                    rec["tie"] = {m: dp.tie(dp._tot(rows, m), dp._tot(got[t], m)) for m in METS}
                if kind in PAIRS and PAIRS[kind][0] in got:
                    rec["keys"] = pr._safely(keys_tie, rows, got[PAIRS[kind][0]], PAIRS[kind][1], fallback=None)
            res["reads"][kind] = rec
    except Stop as e:
        res["stopped"] = str(e)
    res["facts"] = pr._safely(facts, got, fallback=None)
    res["complete"] = "stopped" not in res
    res.update(calls=ga.by_kind, tokens=ga.tok, sec=round(ga.sec, 2))
    return res


def counts(apps, run):
    kinds = {}
    for a in apps.values():
        for kind, r in ((a or {}).get("reads") or {}).items():
            c = kinds.setdefault(kind, {"n": 0, "ok": 0, "refused": 0, "low": 0, "other": 0})
            c["n"] += 1
            if r.get("ok"):
                c["ok"] += 1
                tie = r.get("tie") or {}
                if any(v is not None and v < TIE_OK for v in tie.values()):
                    c["low"] += 1
                s = r.get("s") or {}
                if r.get("loss") or any(((s.get(m) or {}).get("other") or 0) > 0 for m in s):
                    c["other"] += 1
            elif 400 <= ((r.get("err") or {}).get("http") or 0) < 500:
                c["refused"] += 1
    return {"apps": len(apps), "complete": sum(1 for a in apps.values() if (a or {}).get("complete")),
            "calls": run.calls, "seconds": run.elapsed(), "kinds": kinds}


def public_lines(c):
    out = ["srcsplit probe: %s n %d ok %d refused %d tie<0.98 %d other %d" % (k, v["n"], v["ok"], v["refused"],
                                                                           v["low"], v["other"])
           for k, v in sorted((c.get("kinds") or {}).items())]
    out.append("srcsplit probe: apps %d, complete %d, calls %d, %ds" % (c.get("apps", 0), c.get("complete", 0),
                                                                        c.get("calls", 0), c.get("seconds", 0)))
    return out


def run_probe(units, cid, sec, tokens, opts, now=None, clock=time.monotonic):
    run = Run(opts.get("budget") or BUDGET_SEC, clock, opts.get("max_calls") or MAX_CALLS)
    now = now or datetime.now(timezone.utc)
    rt, access = dict(tokens), {}
    for owner in sorted({u.get("owner") or "" for u in units}):
        try:
            access[owner] = ga4.access_token(cid, sec, rt[owner]) if owner in rt else None
        except Exception:
            access[owner] = None
    out, props = {}, {u["property_id"]: pr.new_prop() for u in units}
    lock = threading.Lock()

    def one(group):
        for u in group:
            try:
                r = probe_app(run, u, access.get(u.get("owner") or ""), now, props[u["property_id"]], opts)
            except Exception as e:
                r = {"key": u["key"], "crash": type(e).__name__, "complete": False}
            with lock:
                out[u["key"]] = r
            run.say("srcsplit progress: apps %d/%d, calls %d, %ds" % (len(out), len(units), run.calls, run.elapsed()))

    with sp.Beat(run, TICK_SEC):
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            list(ex.map(one, pr._groups(units)))
    c = pr._safely(counts, out, run, fallback={"apps": len(out), "calls": run.calls, "seconds": run.elapsed()})
    return {"v": 1, "probe": "ga4_srcsplit", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rules": {"days": DAYS, "late": LATE, "tie_ok": TIE_OK, "top": TOP, "mets": list(METS),
                      "reads": [[k, s, list(d), f] for k, s, d, f in READS]},
            "counts": c, "apps": out}


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    inputs = ap.event_inputs(env)
    want = ap.wanted(inputs.get("apps") or env.get("SRCSPLIT_APPS"))
    units = cp.units_from_state(sp.load_state(env.get("SRCSPLIT_DATA_DIR") or DATA_DIR))
    if want:
        units = [u for u in units if ap.matches(u, want) or u["key"] in want]
    if not units:
        sys.exit("no GA4 app routes in the private state (or none matched)")
    print("srcsplit probe: %d app(s) to probe" % len(units), flush=True)
    report = run_probe(units, cid, sec, tokens, {"app_calls": APP_CALLS}, now=now, clock=clock)
    for line in public_lines(report["counts"]):
        print(line, flush=True)
    if not pr.write_private(OUT_PATH, pr._dump(report), "ga4 srcsplit probe"):
        sys.exit("private repo write failed")
    print("srcsplit probe: report written", flush=True)


if __name__ == "__main__":
    main()
