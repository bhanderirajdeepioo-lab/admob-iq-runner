"""One-off GA4 NEW vs RETURNING probe, run by .github/workflows/ga4-nvr-probe.yml: before an eCPM view splits the ad
revenue by the user's FIRST session against the later ones (owner, 2 Nov 2026: is a low eCPM a new user's first session
or the old users'), measure per app whether GA4 answers the dimension newVsReturning ("new" = the user's first session,
"returning" = session 2 on) with the ad metrics, WHOLE (each split read tied to the same read without the split), and
what the two eCPMs are. Read-only against GA4 and against the PRIVATE repo's data (the Uninstall state's routes); the
only write is ga4/nvr_probe.json in the PRIVATE repo.

Window W = [F − DAYS + 1, F] (not before the app's history start), F = the app's day − LATE. Reads (USD):
  T     no dimension                     totalAdRevenue, publisherAdImpressions, activeUsers, sessions, newUsers
  NR    newVsReturning                   the same — the two eCPMs, their users and sessions
  NRD   newVsReturning × date            totalAdRevenue, publisherAdImpressions, activeUsers, sessions
  NRC   newVsReturning × countryId       totalAdRevenue, publisherAdImpressions, activeUsers
  NRF   newVsReturning × adFormat        totalAdRevenue, publisherAdImpressions
  NRU   newVsReturning × adUnitName      totalAdRevenue, publisherAdImpressions
A record: accepted or the HTTP class, rows, the tie (Σ rows ÷ T, per metric; "(other)" / "(not set)" rows included),
their shares, the flags (thresholding / sampling / dataLossFromOtherRow) and the rows themselves ("data": [dimension
values …, metric values …] — small: the eCPMs are read off them). "facts": NR per value {rev, imps, ecpm, users,
sessions}.

PUBLIC LOG: counts only (per read kind: n, ok, refused, ties under 0.98, with "(other)"); stderr hidden by the workflow.
"""

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

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
DAYS = 28
NVR = "newVsReturning"
AD = ("totalAdRevenue", "publisherAdImpressions")
READS = (("T", (), AD + ("activeUsers", "sessions", "newUsers")),
         ("NR", (NVR,), AD + ("activeUsers", "sessions", "newUsers")),
         ("NRD", (NVR, "date"), AD + ("activeUsers", "sessions")),
         ("NRC", (NVR, "countryId"), AD + ("activeUsers",)),
         ("NRF", (NVR, "adFormat"), AD),
         ("NRU", (NVR, "adUnitName"), AD))
TIE_OK = 0.98
MAX_CALLS = 600
APP_CALLS = 12
WORKERS = 4
BUDGET_SEC = 15 * 60
TICK_SEC = 20
PAGE_ROWS = 100000
DATA_DIR = "_private"
OUT_PATH = "ga4/nvr_probe.json"


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
            self.say("nvr progress: calls %d, %ds" % (n, s))


def _parse(dims, mets):
    def parse(rows):
        data = [[str(r.get(d) or "") for d in dims] + [round(dp._num(r.get(m)), 6) for m in mets] for r in rows]
        return {"rows": len(rows), "s": dp.shares(rows, dims, mets), "data": data}, rows
    return parse


def facts(rows):
    """NR rows → {value: {rev, imps, ecpm (USD per 1000 impressions), users, sessions}}."""
    out = {}
    for r in rows:
        k = str(r.get(NVR) or "")
        rev, imps = dp._num(r.get("totalAdRevenue")), dp._num(r.get("publisherAdImpressions"))
        out[k] = {"rev": round(rev, 2), "imps": int(imps), "ecpm": round(rev / imps * 1000, 4) if imps else None,
                  "users": int(dp._num(r.get("activeUsers"))), "sessions": int(dp._num(r.get("sessions")))}
    return out


def probe_app(run, u, token, now, prop, opts):
    f = ga4.window_end_in(u["tz"], now) - timedelta(days=LATE)
    a = f - timedelta(days=DAYS - 1)
    hs = gu._d(u["history_start"]) if u.get("history_start") else None
    if hs and a < hs:
        a = hs
    res = {"key": u["key"], "F": f.isoformat(), "from": a.isoformat(), "reads": {}}
    if not token:
        res.update(err={"type": "auth"}, complete=False)
        return res
    if a > f:
        res.update(complete=True, empty=True)
        return res
    ga = cp.App(token, u["property_id"], u["stream_id"], run, prop, cap=opts.get("app_calls", APP_CALLS))
    got = {}
    try:
        for kind, dims, mets in READS:
            body = dp._body(a, f, dims, mets)
            rec, rows = cp._read(ga, kind, lambda: ga.report_all(body, page_rows=PAGE_ROWS), _parse(dims, mets))
            if rec.get("ok"):
                got[kind] = rows
                if kind != "T" and "T" in got:
                    rec["tie"] = {m: dp.tie(dp._tot(rows, m), dp._tot(got["T"], m)) for m in mets}
            res["reads"][kind] = rec
    except Stop as e:
        res["stopped"] = str(e)
    if "NR" in got:
        res["facts"] = pr._safely(facts, got["NR"], fallback=None)
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
    out = ["nvr probe: %s n %d ok %d refused %d tie<0.98 %d other %d" % (k, v["n"], v["ok"], v["refused"], v["low"],
                                                                      v["other"])
           for k, v in sorted((c.get("kinds") or {}).items())]
    out.append("nvr probe: apps %d, complete %d, calls %d, %ds" % (c.get("apps", 0), c.get("complete", 0),
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
            run.say("nvr progress: apps %d/%d, calls %d, %ds" % (len(out), len(units), run.calls, run.elapsed()))

    with sp.Beat(run, TICK_SEC):
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            list(ex.map(one, pr._groups(units)))
    c = pr._safely(counts, out, run, fallback={"apps": len(out), "calls": run.calls, "seconds": run.elapsed()})
    return {"v": 1, "probe": "ga4_nvr", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rules": {"days": DAYS, "late": LATE, "tie_ok": TIE_OK, "reads": [[k, list(d), list(m)] for k, d, m in READS]},
            "counts": c, "apps": out}


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    inputs = ap.event_inputs(env)
    want = ap.wanted(inputs.get("apps") or env.get("NVR_APPS"))
    units = cp.units_from_state(sp.load_state(env.get("NVR_DATA_DIR") or DATA_DIR))
    if want:
        units = [u for u in units if ap.matches(u, want) or u["key"] in want]
    if not units:
        sys.exit("no GA4 app routes in the private state (or none matched)")
    print("nvr probe: %d app(s) to probe" % len(units), flush=True)
    report = run_probe(units, cid, sec, tokens, {"app_calls": APP_CALLS}, now=now, clock=clock)
    for line in public_lines(report["counts"]):
        print(line, flush=True)
    if not pr.write_private(OUT_PATH, pr._dump(report), "ga4 nvr probe"):
        sys.exit("private repo write failed")
    print("nvr probe: report written", flush=True)


if __name__ == "__main__":
    main()
