"""One-off GA4 FIRST SESSION vs RETURNING × COUNTRY probe, run by .github/workflows/ga4-nvrcc-probe.yml: before the eCPM tab's
ad unit / ad format tables follow the picked country (owner, 3 Nov 2026: "US kiya to ad unit table me US ka hi aana
chaiye"), measure per app whether GA4 answers newVsReturning × ad unit (or ad format) × countryId WHOLE — each split tied
to its truth and, country by country, to the read without the ad unit — and how many rows a day it is. Read-only against
GA4 and against the PRIVATE repo's data (the Uninstall state's routes); the only write is ga4/nvrcc_probe.json in the
PRIVATE repo.

Window W = [F − DAYS + 1, F] (not before the app's history start), F = the app's day − LATE; TOP = the TOPN countries
with the most ad revenue in W (from C). Reads (USD; AD = totalAdRevenue, publisherAdImpressions):
  C      W   newVsReturning × countryId                                    the truth per country
  U      W   newVsReturning × adFormat × adUnitName                        the truth per ad unit
  UC     W   newVsReturning × adFormat × adUnitName × countryId (all)      ad units × every country, W as one
  UCT    W   the same, countryId ∈ TOP                                     ad units × the top countries
  UCTD   W   the same + date                                               … day by day (what a daily store holds)
  FCD    W   newVsReturning × adFormat × countryId × date (all)            ad formats × every country, day by day
and the shapes that might fold less (does ANY read give the whole split?), on F alone and on its last 7 days:
  C1     F   newVsReturning × countryId                                    the truth of the F reads
  UC1    F   newVsReturning × adFormat × adUnitName × countryId            one day, every country
  UCK1   F   the same, countryId == TOP[0]                                 one day, the top country alone
  UN1    F   adFormat × adUnitName × countryId (no newVsReturning)         one day, without the session group
  C7 / UC7   [F − 6, F]  as C1 / UC1                                       seven days
A record: accepted or the HTTP class, rows, the "(other)" / "(not set)" shares, GA4's flags, "tie" to its truth (C for
UC / FCD; C restricted to TOP for UCT / UCTD; U for UC's ad units) and "keys": per country (device probe tie_by:
overall, p10 / p90, keys off by > 2 %) with "w2" = the truth's share held by countries within 2 %.
"ecpm": whether what GA4 KEEPS of a folded split still has the true eCPMs — UC summed over countries per ad unit ×
group vs U, and summed over ad units per country × group vs C (groups: new / returning): per side, the impressions-
weighted share of keys whose kept eCPM is within 2 / 5 / 10 % of the truth, and the median / p90 of |kept ÷ true − 1|
(keys with ≥ ECPM_MIN impressions in the truth).

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
TOPN = 10
NVR, CTY = "newVsReturning", "countryId"
AD = ("totalAdRevenue", "publisherAdImpressions")
UNIT = ("adFormat", "adUnitName")
TIE_OK = 0.98
ECPM_MIN = 10000                    # impressions a key needs in the truth for the eCPM check
MAX_CALLS = 1200
APP_CALLS = 40
WORKERS = 4
BUDGET_SEC = 20 * 60
TICK_SEC = 20
PAGE_ROWS = 100000
DATA_DIR = "_private"
OUT_PATH = "ga4/nvrcc_probe.json"


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
            self.say("nvrcc progress: calls %d, %ds" % (n, s))


def top_countries(rows, n=TOPN):
    """C rows → the n countries with the most ad revenue (GA4's "(other)" / "(not set)" never one of them)."""
    by = dp._by([r for r in rows if not dp._other(r, (CTY,)) and not dp._unset(r, (CTY,))], CTY, AD[0])
    return [k for k, v in sorted(by.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0][:n]


def keys_tie(got, want, key):
    """Per country of a split vs its truth: device probe tie_by per metric + "w2" (the truth's share held by countries
    within 2 %)."""
    out = {}
    for m in AD:
        t = dp.tie_by(got, want, key, m)
        g, w = dp._by(got, key, m), dp._by(want, key, m)
        tot = sum(v for v in w.values() if v > 0)
        t["w2"] = pr._ratio(sum(v for k, v in w.items() if v > 0 and abs(g.get(k, 0) / v - 1) <= 0.02), tot)
        out[m] = t
    return out


def _by2(rows, keys):
    """rows → {(key values…, nvr): [revenue, impressions]}."""
    out = {}
    for r in rows or []:
        k = tuple(str(r.get(x) or "") for x in keys) + (str(r.get(NVR) or ""),)
        e = out.setdefault(k, [0.0, 0.0])
        e[0] += dp._num(r.get(AD[0]))
        e[1] += dp._num(r.get(AD[1]))
    return out


def ecpm_check(kept, true):
    """{key: [rev, imps]} kept vs true → the impressions-weighted shares of keys within 2 / 5 / 10 % on eCPM, and the
    median / p90 of |kept eCPM ÷ true eCPM − 1| (keys with ≥ ECPM_MIN true impressions and kept impressions)."""
    devs = []
    for k, (tr, ti) in true.items():
        kr, ki = kept.get(k, (0.0, 0.0))
        if ti < ECPM_MIN or ki <= 0 or tr <= 0:
            continue
        devs.append((abs((kr / ki) / (tr / ti) - 1), ti))
    if not devs:
        return {"keys": 0}
    tot = sum(w for _, w in devs)
    ds = sorted(d for d, _ in devs)
    return {"keys": len(devs), "w2": pr._ratio(sum(w for d, w in devs if d <= 0.02), tot),
            "w5": pr._ratio(sum(w for d, w in devs if d <= 0.05), tot),
            "w10": pr._ratio(sum(w for d, w in devs if d <= 0.10), tot),
            "med": round(ds[len(ds) // 2], 4), "p90": round(ds[min(len(ds) - 1, int(len(ds) * 0.9))], 4)}


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

    def read(kind, dims, extra=None):
        body = dp._body(a, f, dims, AD)
        rec, rows = cp._read(ga, kind, lambda: ga.report_all(body, extra=extra or [], page_rows=PAGE_ROWS),
                             dp.p_rows(dims, AD))
        if rec.get("ok"):
            got[kind] = rows
        res["reads"][kind] = rec
        return rec

    try:
        read("C", (NVR, CTY))
        read("U", (NVR,) + UNIT)
        top = top_countries(got.get("C") or [])
        res["top"] = len(top)
        rec = read("UC", (NVR,) + UNIT + (CTY,))
        if rec.get("ok") and "C" in got:
            rec["tie"] = {m: dp.tie(dp._tot(got["UC"], m), dp._tot(got["C"], m)) for m in AD}
            rec["keys"] = pr._safely(keys_tie, got["UC"], got["C"], CTY, fallback=None)
            if "U" in got:
                rec["ukeys"] = pr._safely(keys_tie, [dict(r, **{CTY: r.get("adUnitName")}) for r in got["UC"]],
                                          [dict(r, **{CTY: r.get("adUnitName")}) for r in got["U"]], CTY, fallback=None)
        if top:
            inlist = [ga4._in_list(CTY, top)]
            ctop = [r for r in (got.get("C") or []) if str(r.get(CTY) or "") in set(top)]
            for kind, dims in (("UCT", (NVR,) + UNIT + (CTY,)), ("UCTD", (NVR,) + UNIT + (CTY, "date"))):
                rec = read(kind, dims, inlist)
                if rec.get("ok"):
                    rec["tie"] = {m: dp.tie(dp._tot(got[kind], m), dp._tot(ctop, m)) for m in AD}
                    rec["keys"] = pr._safely(keys_tie, got[kind], ctop, CTY, fallback=None)
        if "UC" in got and "U" in got and "C" in got:
            res["ecpm"] = pr._safely(lambda: {
                "unit": ecpm_check(_by2(got["UC"], ("adUnitName",)), _by2(got["U"], ("adUnitName",))),
                "country": ecpm_check(_by2(got["UC"], (CTY,)), _by2(got["C"], (CTY,)))}, fallback=None)
        f0, f7 = f, f - timedelta(days=6)

        def read_on(kind, a2, dims, extra=None):
            body = dp._body(a2, f0, dims, AD)
            rec2, rows2 = cp._read(ga, kind, lambda: ga.report_all(body, extra=extra or [], page_rows=PAGE_ROWS),
                                   dp.p_rows(dims, AD))
            if rec2.get("ok"):
                got[kind] = rows2
            res["reads"][kind] = rec2
            return rec2
        for kind, a2, dims, extra, truth in (
                ("C1", f0, (NVR, CTY), None, None), ("UC1", f0, (NVR,) + UNIT + (CTY,), None, "C1"),
                ("UCK1", f0, (NVR,) + UNIT + (CTY,), [ga4._in_list(CTY, top[:1])] if top else None, "C1"),
                ("UN1", f0, UNIT + (CTY,), None, "C1"),
                ("C7", f7, (NVR, CTY), None, None), ("UC7", f7, (NVR,) + UNIT + (CTY,), None, "C7")):
            if kind == "UCK1" and not top:
                continue
            rec = read_on(kind, a2, dims, extra)
            if rec.get("ok") and truth and truth in got:
                want = got[truth] if kind != "UCK1" else [r for r in got[truth] if str(r.get(CTY) or "") == top[0]]
                rec["tie"] = {m: dp.tie(dp._tot(got[kind], m), dp._tot(want, m)) for m in AD}
                rec["keys"] = pr._safely(keys_tie, got[kind], want, CTY, fallback=None)
        rec = read("FCD", (NVR, "adFormat", CTY, "date"))
        if rec.get("ok") and "C" in got:
            rec["tie"] = {m: dp.tie(dp._tot(got["FCD"], m), dp._tot(got["C"], m)) for m in AD}
            rec["keys"] = pr._safely(keys_tie, got["FCD"], got["C"], CTY, fallback=None)
    except Stop as e:
        res["stopped"] = str(e)
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
    out = ["nvrcc probe: %s n %d ok %d refused %d tie<0.98 %d other %d" % (k, v["n"], v["ok"], v["refused"], v["low"],
                                                                        v["other"])
           for k, v in sorted((c.get("kinds") or {}).items())]
    out.append("nvrcc probe: apps %d, complete %d, calls %d, %ds" % (c.get("apps", 0), c.get("complete", 0),
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
            run.say("nvrcc progress: apps %d/%d, calls %d, %ds" % (len(out), len(units), run.calls, run.elapsed()))

    with sp.Beat(run, TICK_SEC):
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            list(ex.map(one, pr._groups(units)))
    c = pr._safely(counts, out, run, fallback={"apps": len(out), "calls": run.calls, "seconds": run.elapsed()})
    return {"v": 1, "probe": "ga4_nvrcc", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rules": {"days": DAYS, "late": LATE, "topn": TOPN, "tie_ok": TIE_OK}, "counts": c, "apps": out}


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    inputs = ap.event_inputs(env)
    want = ap.wanted(inputs.get("apps") or env.get("NVRCC_APPS"))
    units = cp.units_from_state(sp.load_state(env.get("NVRCC_DATA_DIR") or DATA_DIR))
    if want:
        units = [u for u in units if ap.matches(u, want) or u["key"] in want]
    if not units:
        sys.exit("no GA4 app routes in the private state (or none matched)")
    print("nvrcc probe: %d app(s) to probe" % len(units), flush=True)
    report = run_probe(units, cid, sec, tokens, {"app_calls": APP_CALLS}, now=now, clock=clock)
    for line in public_lines(report["counts"]):
        print(line, flush=True)
    if not pr.write_private(OUT_PATH, pr._dump(report), "ga4 nvrcc probe"):
        sys.exit("private repo write failed")
    print("nvrcc probe: report written", flush=True)


if __name__ == "__main__":
    main()
