"""One-off GA4 DEVICE COHORT probe, run by .github/workflows/ga4-devcoh-probe.yml: before the 📱 Devices table reads
revenue by phone model AT A FIXED AGE, measure per app which read shape GA4 answers WHOLE — the ga4_device_probe found
the 90-day install-day × model reads losing 36–58 % to "(other)" on the biggest apps. One install day X at a time
(filter firstSessionDate == X, so every user is exactly 0 … A−1 days old), each read tied to the same read without the
split. Read-only against GA4 and against the PRIVATE repo's data (the Uninstall state's routes); the only write is
ga4/devcoh_probe.json in the PRIVATE repo.

For each X in XS (F − 95, F − 35, F − 10, where reachable) and age A in AGES (7, 30, 90; only when X + A − 1 ≤ F):
  T<A>    [X, X+A−1]  (no dimension)            newUsers, activeUsers, totalAdRevenue   — the truth
  MC<A>   the same, model × countryId           — the Devices table's read
  M<A>    the same, model only
  C<A>    the same, countryId only
and once per X:
  D1T / D1MC  [X+1, X+1]  activeUsers (back next day), no dimension / model × countryId
  PT / PMC    [X, X] newUsers of PAID users (firstUserGoogleAdsCampaignId a real id), no dimension / model × countryId
A record: accepted or the HTTP class, rows, the tie (Σ rows ÷ the truth, "(other)" rows included), the "(other)" share,
the flags (thresholding / sampling / dataLossFromOtherRow).

PUBLIC LOG: counts only (per read kind: n, ok, refused, ties under 0.98, with "(other)"); stderr hidden by the workflow.
"""

import os
import sys
import time
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
XS = (95, 35, 10)                   # install days X = F − these
AGES = (7, 30, 90)
MODEL, CAMP = "mobileDeviceModel", "firstUserGoogleAdsCampaignId"
METS = ("newUsers", "activeUsers", "totalAdRevenue")
TIE_OK = 0.98
MAX_CALLS = 2500
APP_CALLS = 80
WORKERS = 4
BUDGET_SEC = 20 * 60
TICK_SEC = 20
PAGE_ROWS = 100000
DATA_DIR = "_private"
OUT_PATH = "ga4/devcoh_probe.json"


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
            self.say("devcoh progress: calls %d, %ds" % (n, s))


def _fsd(x):
    return {"filter": {"fieldName": "firstSessionDate", "stringFilter": {"matchType": "EXACT", "value": pr._ymd(x)}}}


def reads_for(x, f):
    """[(kind, a, b, dims, mets, extra)] for install day x (F = f)."""
    out = []
    for age in AGES:
        b = x + timedelta(days=age - 1)
        if b > f:
            continue
        for k, dims in (("T", ()), ("MC", (MODEL, "countryId")), ("M", (MODEL,)), ("C", ("countryId",))):
            out.append(("%s%d" % (k, age), x, b, dims, METS, [_fsd(x)]))
    if x + timedelta(days=1) <= f:
        d1 = x + timedelta(days=1)
        out.append(("D1T", d1, d1, (), ("activeUsers",), [_fsd(x)]))
        out.append(("D1MC", d1, d1, (MODEL, "countryId"), ("activeUsers",), [_fsd(x)]))
    out.append(("PT", x, x, (), ("newUsers",), [_fsd(x), cp.paid_expr(CAMP)]))
    out.append(("PMC", x, x, (MODEL, "countryId"), ("newUsers",), [_fsd(x), cp.paid_expr(CAMP)]))
    return out


TRUTH = {"MC": "T", "M": "T", "C": "T", "D1MC": "D1T", "PMC": "PT"}


def _truth_of(kind):
    for k in ("D1MC", "PMC", "MC", "M", "C"):
        if kind.startswith(k):
            return TRUTH[k] + kind[len(k):]
    return None


def probe_app(run, u, token, now, prop, opts):
    f = ga4.window_end_in(u["tz"], now) - timedelta(days=LATE)
    hs = gu._d(u["history_start"]) if u.get("history_start") else None
    xs = [f - timedelta(days=n) for n in XS if hs is None or f - timedelta(days=n) >= hs]
    res = {"key": u["key"], "F": f.isoformat(), "xs": [x.isoformat() for x in xs], "reads": {}}
    if not token:
        res.update(err={"type": "auth"}, complete=False)
        return res
    ga = cp.App(token, u["property_id"], u["stream_id"], run, prop, cap=opts.get("app_calls", APP_CALLS))
    try:
        for x in xs:
            got = {}
            for kind, a, b, dims, mets, extra in reads_for(x, f):
                body = dp._body(a, b, dims, mets)
                rec, rows = cp._read(ga, kind, lambda: ga.report_all(body, extra=extra, page_rows=PAGE_ROWS),
                                     dp.p_rows(dims, mets))
                if rec.get("ok"):
                    got[kind] = rows
                    t = _truth_of(kind)
                    if t and t in got:
                        rec["tie"] = {m: dp.tie(dp._tot(rows, m), dp._tot(got[t], m)) for m in mets}
                res["reads"]["%s@%s" % (kind, x.isoformat())] = rec
    except Stop as e:
        res["stopped"] = str(e)
    res["complete"] = "stopped" not in res
    res.update(calls=ga.by_kind, tokens=ga.tok, sec=round(ga.sec, 2))
    return res


def counts(apps, run):
    kinds = {}
    for a in apps.values():
        for k, r in ((a or {}).get("reads") or {}).items():
            kind = k.split("@")[0]
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
    out = ["devcoh probe: %s n %d ok %d refused %d tie<0.98 %d other %d" % (k, v["n"], v["ok"], v["refused"], v["low"],
                                                                         v["other"])
           for k, v in sorted((c.get("kinds") or {}).items())]
    out.append("devcoh probe: apps %d, complete %d, calls %d, %ds" % (c.get("apps", 0), c.get("complete", 0),
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
    import threading
    from concurrent.futures import ThreadPoolExecutor
    lock = threading.Lock()

    def one(group):
        for u in group:
            try:
                r = probe_app(run, u, access.get(u.get("owner") or ""), now, props[u["property_id"]], opts)
            except Exception as e:
                r = {"key": u["key"], "crash": type(e).__name__, "complete": False}
            with lock:
                out[u["key"]] = r
            run.say("devcoh progress: apps %d/%d, calls %d, %ds" % (len(out), len(units), run.calls, run.elapsed()))

    with sp.Beat(run, TICK_SEC):
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            list(ex.map(one, pr._groups(units)))
    c = pr._safely(counts, out, run, fallback={"apps": len(out), "calls": run.calls, "seconds": run.elapsed()})
    return {"v": 1, "probe": "ga4_devcoh", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rules": {"xs": list(XS), "ages": list(AGES), "late": LATE, "tie_ok": TIE_OK}, "counts": c, "apps": out}


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    inputs = ap.event_inputs(env)
    want = ap.wanted(inputs.get("apps") or env.get("DEVCOH_APPS"))
    units = cp.units_from_state(sp.load_state(env.get("DEVCOH_DATA_DIR") or DATA_DIR))
    if want:
        units = [u for u in units if ap.matches(u, want) or u["key"] in want]
    if not units:
        sys.exit("no GA4 app routes in the private state (or none matched)")
    print("devcoh probe: %d app(s) to probe" % len(units), flush=True)
    report = run_probe(units, cid, sec, tokens, {"app_calls": APP_CALLS}, now=now, clock=clock)
    for line in public_lines(report["counts"]):
        print(line, flush=True)
    if not pr.write_private(OUT_PATH, pr._dump(report), "ga4 devcoh probe"):
        sys.exit("private repo write failed")
    print("devcoh probe: report written", flush=True)


if __name__ == "__main__":
    main()
