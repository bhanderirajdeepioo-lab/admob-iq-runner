"""One-off GA4 DEVICE probe, run by .github/workflows/ga4-device-probe.yml: before a "📱 Devices" table is built
(Install value → 📈 ROI, beside 🌍 Countries), measure per GA4 app what GA4 gives BY PHONE MODEL: every read accepted
or its HTTP class, rows, the "(other)" / "(not set)" shares, thresholding / sampling, and whether the model rows TIE to
the same read without the model (nothing silently lost). Read-only against GA4 and against the PRIVATE repo's data (the
Uninstall state's routes); the only write is ga4/device_probe.json in the PRIVATE repo.

READS (W = the WIN days F − WIN + 1 .. F, F = E − LATE in the property's timezone; USD; every read pinned to the app's
Android stream by ga4.Ga4App; model = mobileDeviceModel, paid = firstUserGoogleAdsCampaignId is a real id):
  TOT   W        (no dimension)                         newUsers, activeUsers, totalAdRevenue, publisherAdImpressions
  MOD   W        brand, model, marketing name           the same four
  OSV   W        operatingSystemVersion                 newUsers, totalAdRevenue
  CAT   W        deviceCategory                         newUsers, totalAdRevenue
  PAID  W        model, campaign id                     newUsers, totalAdRevenue
  CELL  W        model, countryId, campaign id          newUsers — paid users only
  CD0   CD_DAYS  date, countryId, campaign id           newUsers — paid only (the day cell without the model)
  CD    CD_DAYS  date, model, countryId, campaign id    newUsers — paid only
  ID0   W        firstSessionDate (inList: W's days)    newUsers, totalAdRevenue (W's installs, earned in W)
  IDM   W        firstSessionDate, model (same list)    the same
  QB    [F, F]   firstSessionDate                       activeUsers, newUsers, totalAdRevenue (one activity day)
  DFM   [F, F]   firstSessionDate, model                the same
  COH0  cohort X = F − COH_AGE, days 0 .. COH_AGE     cohortActiveUsers, cohortTotalUsers, totalAdRevenue
  COHM  the same + model
  COH7  COH7_N single-day cohorts ending X + model (accepted? rows)
  HIST0 history start .. F  yearMonth                   newUsers, totalAdRevenue
  HIST  the same + model
Ties: MOD / OSV / CAT / PAID vs TOT, CELL vs PAID's paid part, CD vs CD0 (per day), IDM vs ID0 (per install day),
DFM vs QB, COHM vs COH0 (per day of age), HIST vs HIST0 (per month). A tie is Σ of ALL rows ("(other)" included) ÷ the
read without the model: < 1 = rows GA4 withheld (thresholding); the "(other)" share is what it lumped.

OUTPUT: ga4/device_probe.json in the PRIVATE repo (write_private; never data/ or site/): per app KEY (the Uninstall file
key) every read's record and the facts a table would need — the model count, how many models reach 100 / 300 / 1000 /
3000 installs, how many models hold 50 / 80 / 90 / 95 % of installs and revenue, the paid share, the cells, the oldest
month with model rows, and the TOP_N models with their numbers (the owner's own data, private repo only).
PUBLIC LOG: progress counts (a heartbeat at least every minute) and ONE counts-only line per read kind + one for the run
— no names, ids, models, dates, users or money; stderr is hidden by the workflow.

LIMITS: the d1d7 probe's quota rule per PROPERTY (any token bucket under half, few server-error / thresholded requests
left, a 429, 2 failed calls on 5xx), one request at a time per property (WORKERS properties in parallel), at most
APP_CALLS calls an app and MAX_CALLS a run, and no call is started after BUDGET_SEC — what is measured is still written.
"""

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from admob_iq import ga4_probe
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_audience_probe as ap
from admob_iq.fetch import ga4_country_probe as cp
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_shape_probe as sp
from admob_iq.fetch import ga4_uninstall as gu
from admob_iq.fetch.ga4_d1d7_probe import Stop

WIN = 90                            # days of installs read (input "win")
LATE = gu.IDAY_LATE                 # F = E − 3: the newest final day
CD_DAYS = 7                         # the day-cell reads (CD0 / CD)
COH_AGE = 30                        # the cohort reads: install day X = F − 30, ages 0 .. 30
COH7_N = 7                          # COH7: this many single-day cohorts in one request
HIST_DAYS = 730                     # HIST from the app's history start, else this many days back
TOP_N = 30                          # models kept with their numbers
OSV_TOP = 15
STEPS = (100, 300, 1000, 3000)      # "a model with ≥ N installs"
COVER = (0.5, 0.8, 0.9, 0.95)       # "how many models hold this share"
CELL_MIN = (30, 100)                # paid installs in a model × country × campaign cell
MODEL = "mobileDeviceModel"
BRAND, MKT = "mobileDeviceBranding", "mobileDeviceMarketingName"
CAMP = "firstUserGoogleAdsCampaignId"
WIN_METS = ("newUsers", "activeUsers", "totalAdRevenue", "publisherAdImpressions")
NR = ("newUsers", "totalAdRevenue")
DAY_METS = ("activeUsers", "newUsers", "totalAdRevenue")
COH_METS = ("cohortActiveUsers", "cohortTotalUsers", "totalAdRevenue")
KINDS = ("TOT", "MOD", "OSV", "CAT", "PAID", "CELL", "CD0", "CD", "ID0", "IDM", "QB", "DFM", "COH0", "COHM", "COH7",
         "HIST0", "HIST")
MAX_CALLS = 1500
APP_CALLS = 60                      # ~20 planned an app: room for pages
WORKERS = 4
BUDGET_SEC = 20 * 60                # no new call after 20 min (the job's timeout is 40)
TICK_SEC = 20
PAGE_ROWS = 100000
COH_LIMIT = 250000                  # the Data API maximum: a cohort read is one call
DATA_DIR = "_private"
OUT_PATH = "ga4/device_probe.json"
OTHER = "(other)"
UNSET = {"", "(not set)", "(none)"}


class Run(cp.Run):
    """cp.Run with its own heartbeat words."""

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
            self.say("device progress: calls %d, %ds" % (n, s))


# ── the request shapes ──────────────────────────────────────────────────────────────────────────

def _body(a, b, dims, mets):
    return {"dateRanges": [gu._rng(a, b)], "dimensions": ga4._dim(*dims), "metrics": ga4._dim(*mets),
            "currencyCode": "USD", "keepEmptyRows": False}


def _coh(xs, dims=()):
    return {"dimensions": ga4._dim("cohort", "cohortNthDay", *dims), "metrics": ga4._dim(*COH_METS),
            "currencyCode": "USD",
            "cohortSpec": {"cohorts": [{"name": "c" + pr._ymd(x), "dimension": "firstSessionDate",
                                        "dateRange": gu._rng(x, x)} for x in xs],
                           "cohortsRange": {"granularity": "DAILY", "startOffset": 0, "endOffset": COH_AGE}}}


def plan_of(u, now, win=WIN):
    """One app's dates: F, W = [w0, F], the CD days, the cohort day X, the HIST start."""
    f = ga4.window_end_in(u["tz"], now) - timedelta(days=LATE)
    hs = gu._d(u["history_start"]) if u.get("history_start") else None
    w0 = f - timedelta(days=win - 1)
    h0 = max(hs, f - timedelta(days=HIST_DAYS)) if hs else f - timedelta(days=HIST_DAYS)
    return {"F": f, "w0": w0, "cd0": f - timedelta(days=CD_DAYS - 1), "x": f - timedelta(days=COH_AGE), "h0": h0,
            "wdays": [pr._ymd(w0 + timedelta(days=i)) for i in range(win)]}


def request(kind, p):
    """kind → {"body", "extra"} (extra: filter expressions the stream filter adds)."""
    f, w0, paid = p["F"], p["w0"], cp.paid_expr(CAMP)
    if kind == "TOT":
        return {"body": _body(w0, f, (), WIN_METS)}
    if kind == "MOD":
        return {"body": _body(w0, f, (BRAND, MODEL, MKT), WIN_METS)}
    if kind == "OSV":
        return {"body": _body(w0, f, ("operatingSystemVersion",), NR)}
    if kind == "CAT":
        return {"body": _body(w0, f, ("deviceCategory",), NR)}
    if kind == "PAID":
        return {"body": _body(w0, f, (MODEL, CAMP), NR)}
    if kind == "CELL":
        return {"body": _body(w0, f, (MODEL, "countryId", CAMP), ("newUsers",)), "extra": [paid]}
    if kind == "CD0":
        return {"body": _body(p["cd0"], f, ("date", "countryId", CAMP), ("newUsers",)), "extra": [paid]}
    if kind == "CD":
        return {"body": _body(p["cd0"], f, ("date", MODEL, "countryId", CAMP), ("newUsers",)), "extra": [paid]}
    if kind == "ID0":
        return {"body": _body(w0, f, ("firstSessionDate",), NR), "extra": [ga4._in_list("firstSessionDate", p["wdays"])]}
    if kind == "IDM":
        return {"body": _body(w0, f, ("firstSessionDate", MODEL), NR),
                "extra": [ga4._in_list("firstSessionDate", p["wdays"])]}
    if kind == "QB":
        return {"body": _body(f, f, ("firstSessionDate",), DAY_METS)}
    if kind == "DFM":
        return {"body": _body(f, f, ("firstSessionDate", MODEL), DAY_METS)}
    if kind == "COH0":
        return {"body": _coh([p["x"]])}
    if kind == "COHM":
        return {"body": _coh([p["x"]], (MODEL,))}
    if kind == "COH7":
        return {"body": _coh([p["x"] - timedelta(days=i) for i in range(COH7_N - 1, -1, -1)], (MODEL,))}
    if kind == "HIST0":
        return {"body": _body(p["h0"], f, ("yearMonth",), NR)}
    if kind == "HIST":
        return {"body": _body(p["h0"], f, ("yearMonth", MODEL), NR)}
    raise KeyError(kind)


# ── parsing (rows → a record of counts / shares / ties; the index stays in memory) ─────────────

def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _tot(rows, m):
    return sum(_num(r.get(m)) for r in rows)


def _other(r, dims):
    return any(str(r.get(d) or "") == OTHER for d in dims)


def _unset(r, dims):
    return any(str(r.get(d) or "") in UNSET for d in dims)


def shares(rows, dims, mets):
    """Σ per metric over every row, and the "(other)" / "(not set)" share of it."""
    out = {}
    for m in mets:
        t = _tot(rows, m)
        out[m] = {"sum": round(t, 4), "other": pr._ratio(sum(_num(r.get(m)) for r in rows if _other(r, dims)), t),
                  "unset": pr._ratio(sum(_num(r.get(m)) for r in rows if not _other(r, dims) and _unset(r, dims)), t)}
    return out


def tie(got, want):
    """Σ of a split read ÷ the same read without the split (None when the reference is 0 / missing)."""
    return pr._ratio(got, want) if want else None


def _named(rows, dims):
    return [r for r in rows if not _other(r, dims) and not _unset(r, dims)]


def cover(vals, qs=COVER):
    """Sorted biggest first → how many items hold each share q of the total."""
    v = sorted((x for x in vals if x > 0), reverse=True)
    t, out, run, i = sum(v), {}, 0.0, 0
    for q in qs:
        while i < len(v) and run < q * t - 1e-9:
            run += v[i]
            i += 1
        out[str(q)] = i if t else 0
    return out


def p_rows(dims, mets):
    def parse(rows):
        return {"rows": len(rows), "s": shares(rows, dims, mets)}, rows
    return parse


def mod_facts(rows):
    """MOD rows → the model count, models by install step, coverage, the revenue held by models under 100 installs."""
    named = _named(rows, (MODEL,))
    n = [_num(r.get("newUsers")) for r in named]
    rv = [_num(r.get("totalAdRevenue")) for r in named]
    tr = sum(rv)
    return {"models": len(named), "keys": len({r.get(MODEL) for r in named}),
            "steps": {str(k): sum(1 for x in n if x >= k) for k in STEPS},
            "cover_installs": cover(n), "cover_rev": cover(rv),
            "rev_under_100": pr._ratio(sum(r for x, r in zip(n, rv) if x < 100), tr)}


def top_models(mod, paid, idm, n=TOP_N):
    """The TOP_N models by installs (MOD) with their paid part (PAID) and W's installs' revenue earned in W (IDM)."""
    named = sorted(_named(mod or [], (MODEL,)), key=lambda r: -_num(r.get("newUsers")))
    tn = _tot(mod or [], "newUsers")
    pk, pr_ = {}, {}
    for r in paid or []:
        if cp.is_paid(CAMP, r.get(CAMP)):
            k = r.get(MODEL)
            pk[k] = pk.get(k, 0) + _num(r.get("newUsers"))
            pr_[k] = pr_.get(k, 0) + _num(r.get("totalAdRevenue"))
    ik, ir = {}, {}
    for r in idm or []:
        k = r.get(MODEL)
        ik[k] = ik.get(k, 0) + _num(r.get("newUsers"))
        ir[k] = ir.get(k, 0) + _num(r.get("totalAdRevenue"))
    out = []
    for r in named[:n]:
        k = r.get(MODEL)
        out.append({"brand": r.get(BRAND), "model": k, "name": r.get(MKT), "installs": int(_num(r.get("newUsers"))),
                    "share": pr._ratio(_num(r.get("newUsers")), tn), "active": int(_num(r.get("activeUsers"))),
                    "rev": round(_num(r.get("totalAdRevenue")), 2), "imps": int(_num(r.get("publisherAdImpressions"))),
                    "paid_installs": int(pk.get(k, 0)) if paid is not None else None,
                    "paid_rev": round(pr_.get(k, 0), 2) if paid is not None else None,
                    "cohort_installs": int(ik.get(k, 0)) if idm is not None else None,
                    "cohort_rev": round(ir.get(k, 0), 2) if idm is not None else None})
    return out


def paid_facts(rows):
    by = {}
    for r in rows:
        if cp.is_paid(CAMP, r.get(CAMP)) and not _other(r, (MODEL, CAMP)):
            by[r.get(MODEL)] = by.get(r.get(MODEL), 0) + _num(r.get("newUsers"))
    t = _tot(rows, "newUsers")
    p = sum(_num(r.get("newUsers")) for r in rows if cp.is_paid(CAMP, r.get(CAMP)))
    return {"paid_share": pr._ratio(p, t), "paid_installs": int(p),
            "steps": {str(k): sum(1 for x in by.values() if x >= k) for k in STEPS}}


def cell_facts(rows):
    v = [_num(r.get("newUsers")) for r in rows if not _other(r, (MODEL, "countryId", CAMP))]
    t = sum(v)
    return {"cells": len(v), **{"cells_%d" % k: sum(1 for x in v if x >= k) for k in CELL_MIN},
            **{"in_%d" % k: pr._ratio(sum(x for x in v if x >= k), t) for k in CELL_MIN}}


def _by(rows, key, m):
    out = {}
    for r in rows or []:
        k = r.get(key)
        out[k] = out.get(k, 0) + _num(r.get(m))
    return out


def tie_by(got, want, key, m):
    """Per key (day / install day / month / age): Σ got ÷ want → the overall ratio, the spread and how many keys miss
    by more than 2 %."""
    g, w = _by(got, key, m), _by(want, key, m)
    rs = [g.get(k, 0) / v for k, v in w.items() if v]
    return {"all": tie(sum(g.values()), sum(w.values())), "keys": len(w),
            "p10": sp._pct(rs, 0.1), "p90": sp._pct(rs, 0.9), "off2": sum(1 for x in rs if abs(x - 1) > 0.02)}


def hist_facts(h0, h):
    """HIST vs HIST0 per month: the months GA4 has, the oldest month with a named model row, the "(other)" share of the
    revenue (GA4's "(other)" row carries "(other)" in EVERY dimension, the month too: overall only, plus the worst month
    where a real month still shows a lumped model) and the per-month tie."""
    months = sorted({r.get("yearMonth") for r in h0 or [] if _num(r.get("newUsers")) or _num(r.get("totalAdRevenue"))})
    named = sorted({r.get("yearMonth") for r in _named(h or [], (MODEL,))})
    worst = None
    for m in months:
        rs = [r for r in h or [] if r.get("yearMonth") == m]
        s = pr._ratio(sum(_num(r.get("totalAdRevenue")) for r in rs if _other(r, (MODEL,))), _tot(rs, "totalAdRevenue"))
        if s is not None and (worst is None or s > worst):
            worst = s
    return {"months": len(months), "first": months[0] if months else None,
            "first_model": named[0] if named else None,
            "other_rev": pr._ratio(sum(_num(r.get("totalAdRevenue")) for r in h or [] if _other(r, (MODEL,))),
                                   _tot(h or [], "totalAdRevenue")) if h is not None else None,
            "worst_month_other_rev": worst,
            "tie_rev": tie_by(h, h0, "yearMonth", "totalAdRevenue"), "tie_new": tie_by(h, h0, "yearMonth", "newUsers")}


def osv_top(rows, n=OSV_TOP):
    named = sorted(_named(rows, ("operatingSystemVersion",)), key=lambda r: -_num(r.get("newUsers")))
    t = _tot(rows, "newUsers")
    return [{"v": r.get("operatingSystemVersion"), "installs": int(_num(r.get("newUsers"))),
             "share": pr._ratio(_num(r.get("newUsers")), t), "rev": round(_num(r.get("totalAdRevenue")), 2)}
            for r in named[:n]]


# ── one app ─────────────────────────────────────────────────────────────────────────────────────

def probe_app(run, u, token, now, prop, opts):
    """Every read of one app → its result. Never raises for GA4 errors; a Stop ends the app (what was read is kept)."""
    p = plan_of(u, now, opts.get("win") or WIN)
    res = {"key": u["key"], "tz": u["tz"], "F": p["F"].isoformat(), "w0": p["w0"].isoformat(), "x": p["x"].isoformat(),
           "h0": p["h0"].isoformat(), "reads": {}}
    if not token:
        res.update(err={"type": "auth"}, complete=False)
        return res
    ga = cp.App(token, u["property_id"], u["stream_id"], run, prop, cap=opts.get("app_calls", APP_CALLS))
    raw = {}

    def read(kind, dims, mets):
        req = request(kind, p)
        if kind.startswith("COH"):                  # a cohort read: one call (no paging / ordering by cohort dims)
            fetch = lambda: ga.report(dict(req["body"], limit=COH_LIMIT), extra=req.get("extra"))
        else:
            fetch = lambda: ga.report_all(req["body"], extra=req.get("extra"), page_rows=PAGE_ROWS)
        rec, rows = cp._read(ga, kind, fetch, p_rows(dims, mets))
        if rec.get("ok") and kind.startswith("COH"):
            rec["trunc"] = bool(ga.truncated(rows or []))
        res["reads"][kind] = rec
        if rec.get("ok"):
            raw[kind] = rows
        return rows if rec.get("ok") else None

    try:
        why = ga.stop or run.over()
        if why:
            raise Stop(why)
        read("TOT", (), WIN_METS)
        read("MOD", (BRAND, MODEL, MKT), WIN_METS)
        read("OSV", ("operatingSystemVersion",), NR)
        read("CAT", ("deviceCategory",), NR)
        read("PAID", (MODEL, CAMP), NR)
        read("CELL", (MODEL, "countryId", CAMP), ("newUsers",))
        read("CD0", ("date", "countryId", CAMP), ("newUsers",))
        read("CD", ("date", MODEL, "countryId", CAMP), ("newUsers",))
        read("ID0", ("firstSessionDate",), NR)
        read("IDM", ("firstSessionDate", MODEL), NR)
        read("QB", ("firstSessionDate",), DAY_METS)
        read("DFM", ("firstSessionDate", MODEL), DAY_METS)
        read("COH0", ("cohort", "cohortNthDay"), COH_METS)
        read("COHM", ("cohort", "cohortNthDay", MODEL), COH_METS)
        read("COH7", ("cohort", "cohortNthDay", MODEL), COH_METS)
        read("HIST0", ("yearMonth",), NR)
        read("HIST", ("yearMonth", MODEL), NR)
    except Stop as e:
        res["stopped"] = str(e)
    finally:
        res["facts"] = pr._safely(facts, raw, fallback={"bug": True})
        res["complete"] = all((res["reads"].get(k) or {}).get("ok") is not None for k in KINDS) and "stopped" not in res
        res.update(calls=ga.by_kind, tokens=ga.tok, sec=round(ga.sec, 2), server_errors=ga.server_errors)
    return res


def facts(raw):
    """The reads' rows (in memory) → the facts and ties the private report keeps."""
    g = raw.get
    tot = {m: _tot(g("TOT") or [], m) for m in WIN_METS} if g("TOT") is not None else None
    out = {}
    if tot is not None:
        out["tot"] = {m: round(v, 2) for m, v in tot.items()}
        for k in ("MOD", "OSV", "CAT", "PAID"):
            if g(k) is not None:
                out["tie_" + k] = {m: tie(_tot(g(k), m), tot[m]) for m in NR}
    if g("MOD") is not None:
        out["mod"] = mod_facts(g("MOD"))
        out["top"] = top_models(g("MOD"), g("PAID"), g("IDM"))
    if g("OSV") is not None:
        out["osv"] = {"versions": len(_named(g("OSV"), ("operatingSystemVersion",))), "top": osv_top(g("OSV"))}
    if g("CAT") is not None:
        out["cat"] = [{"c": r.get("deviceCategory"), "installs": int(_num(r.get("newUsers"))),
                       "rev": round(_num(r.get("totalAdRevenue")), 2)} for r in g("CAT")]
    if g("PAID") is not None:
        out["paid"] = paid_facts(g("PAID"))
    if g("CELL") is not None:
        out["cell"] = cell_facts(g("CELL"))
        if g("PAID") is not None:
            want = sum(_num(r.get("newUsers")) for r in g("PAID") if cp.is_paid(CAMP, r.get(CAMP)))
            out["tie_CELL"] = tie(_tot(g("CELL"), "newUsers"), want)
    if g("CD") is not None and g("CD0") is not None:
        out["tie_CD"] = tie_by(g("CD"), g("CD0"), "date", "newUsers")
        out["cd_rows_day"] = round(len(g("CD")) / CD_DAYS, 1)
    if g("IDM") is not None and g("ID0") is not None:
        out["tie_IDM"] = {m: tie_by(g("IDM"), g("ID0"), "firstSessionDate", m) for m in NR}
    if g("DFM") is not None and g("QB") is not None:
        out["tie_DFM"] = {m: tie_by(g("DFM"), g("QB"), "firstSessionDate", m) for m in DAY_METS}
    if g("COHM") is not None and g("COH0") is not None:
        out["tie_COHM"] = {m: tie_by(g("COHM"), g("COH0"), "cohortNthDay", m) for m in COH_METS}
    if g("HIST0") is not None:
        out["hist"] = hist_facts(g("HIST0"), g("HIST"))
    return out


# ── the summary (private) and the counts (public) ───────────────────────────────────────────────

def _read_counts(apps, kind):
    recs = [((a or {}).get("reads") or {}).get(kind) for a in apps.values()]
    recs = [r for r in recs if isinstance(r, dict)]
    ok = [r for r in recs if r.get("ok")]

    def oth(r):
        s = r.get("s") or {}
        return any(((s.get(m) or {}).get("other") or 0) > 0 for m in s)
    return {"n": len(recs), "ok": len(ok),
            "refused": sum(1 for r in recs if not r.get("ok") and 400 <= ((r.get("err") or {}).get("http") or 0) < 500
                           and (r.get("err") or {}).get("http") != 429),
            "other": sum(1 for r in ok if r.get("loss") or oth(r)), "thresh": sum(1 for r in ok if r.get("thresh")),
            "sampled": sum(1 for r in ok if r.get("sampled"))}


def counts(apps, run):
    return {"apps": len(apps), "complete": sum(1 for a in apps.values() if (a or {}).get("complete")),
            "stopped": sum(1 for a in apps.values() if (a or {}).get("stopped")), "calls": run.calls,
            "seconds": run.elapsed(), "kinds": {k: _read_counts(apps, k) for k in KINDS}}


def public_lines(c):
    z = {"n": 0, "ok": 0, "refused": 0, "other": 0, "thresh": 0, "sampled": 0}
    out = []
    for k in KINDS:
        v = dict(z, **((c.get("kinds") or {}).get(k) or {}))
        out.append("device probe: %s n %d ok %d refused %d other %d thresholded %d sampled %d"
                   % (k, v["n"], v["ok"], v["refused"], v["other"], v["thresh"], v["sampled"]))
    out.append("device probe: apps %d, complete %d, stopped %d, calls %d, %ds"
               % (c.get("apps", 0), c.get("complete", 0), c.get("stopped", 0), c.get("calls", 0), c.get("seconds", 0)))
    return out


# ── the run ─────────────────────────────────────────────────────────────────────────────────────

def run_probe(units, cid, sec, tokens, opts, now=None, clock=time.monotonic, workers=WORKERS, tick=TICK_SEC):
    run = Run(opts.get("budget") or BUDGET_SEC, clock, opts.get("max_calls") or MAX_CALLS)
    now = now or datetime.now(timezone.utc)
    rt, access = dict(tokens), {}
    for owner in sorted({u.get("owner") or "" for u in units}):
        try:
            access[owner] = ga4.access_token(cid, sec, rt[owner]) if owner in rt else None
        except Exception:
            access[owner] = None
    out, props = {}, {u["property_id"]: pr.new_prop() for u in units}
    lock, done = threading.Lock(), [0]

    def one(group):
        for u in group:
            try:
                r = probe_app(run, u, access.get(u.get("owner") or ""), now, props[u["property_id"]], opts)
            except Exception as e:                   # a bug for one app must not cost the others
                r = {"key": u["key"], "crash": type(e).__name__, "complete": False}
            with lock:
                out[u["key"]] = r
                done[0] += 1
                n = done[0]
            run.say("device progress: apps %d/%d, calls %d, %ds" % (n, len(units), run.calls, run.elapsed()))

    with sp.Beat(run, tick):
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            list(ex.map(one, pr._groups(units)))
    c = pr._safely(counts, out, run, fallback={"apps": len(out), "calls": run.calls, "seconds": run.elapsed()})
    return {"v": 1, "probe": "ga4_device", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rules": {"win": opts.get("win") or WIN, "late": LATE, "cd_days": CD_DAYS, "coh_age": COH_AGE,
                      "coh7_n": COH7_N, "hist_days": HIST_DAYS, "top_n": TOP_N, "steps": list(STEPS),
                      "cover": list(COVER), "cell_min": list(CELL_MIN), "max_calls": run.max_calls,
                      "app_calls": opts.get("app_calls", APP_CALLS), "page_rows": PAGE_ROWS},
            "counts": c, "apps": out}


def options(inputs, env):
    def get(k, e):
        v = inputs.get(k)
        return env.get(e) if v is None or str(v).strip() == "" else v
    win = pr._int(get("win", "DEVICE_WIN")) or WIN
    return {"max_apps": pr._int(get("max_apps", "DEVICE_MAX_APPS")), "apps": ap.wanted(get("apps", "DEVICE_APPS")),
            "win": max(7, min(365, win)), "max_calls": pr._int(get("max_calls", "DEVICE_MAX_CALLS")) or MAX_CALLS,
            "app_calls": APP_CALLS, "budget": pr._int(env.get("DEVICE_BUDGET_SEC")) or BUDGET_SEC}


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    opts = options(ap.event_inputs(env), env)
    root = env.get("DEVICE_DATA_DIR") or DATA_DIR
    units = cp.units_from_state(sp.load_state(root))
    if opts["apps"]:
        units = [u for u in units if ap.matches(u, opts["apps"]) or u["key"] in opts["apps"]]
    if opts["max_apps"] > 0:
        units = units[:opts["max_apps"]]
    if not units:
        sys.exit("no GA4 app routes in the private state (or none matched)")
    print("device probe: %d app(s) to probe" % len(units), flush=True)
    report = run_probe(units, cid, sec, tokens, opts, now=now, clock=clock)
    for line in public_lines(report["counts"]):
        print(line, flush=True)
    if not pr.write_private(OUT_PATH, pr._dump(report), "ga4 device probe"):
        sys.exit("private repo write failed")            # stderr: hidden by the workflow step
    print("device probe: report written", flush=True)


if __name__ == "__main__":
    main()
