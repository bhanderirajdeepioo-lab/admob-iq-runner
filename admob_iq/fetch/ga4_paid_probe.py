"""One-off GA4 PAID / ORGANIC split probe, run by .github/workflows/ga4-paid-probe.yml: before the Breakeven tab, its ROAS
and its benchmark are rebuilt from Google Ads users only (owner, 16 Nov 2026: a Google Ads | Organic switch), measure per
app whether GA4 answers the cohort cube's own read FILTERED on the first-user channel group WHOLE, and whether the two
halves (paid, everyone else) add up to the unfiltered read — real per-source revenue from GA4 itself, never a split of
totals. Read-only against GA4 and against the PRIVATE repo's data (the Uninstall state's routes and the site's ROI files);
the only write is ga4/paid_probe.json in the PRIVATE repo.

The 31 Oct probe found the first-user channel "Cross-network" IS Google Ads; the owner's grouping is Paid = Cross-network +
Paid Search, Organic = Direct + Organic Search, Other = (other) + Unassigned. An earlier probe found a session-channel
DIMENSION crossed with the install day drops rows on the biggest apps; this probe tests a FILTER on the FIRST-USER channel
over the cube's own shape (the same rows as the unfiltered read), so it may stay whole.

Days: per app up to four activity days F = today − 5, F − 30, F − 100 and F − 300, never before the app's history start
(that day is used instead: the nearest valid day). On each day D (one-day range [D, D], USD) — the shape of the first three
is the cube's (fetch/ga4_cube.py: its body builder, dimensions date × firstSessionDate × countryId, metrics activeUsers,
totalAdRevenue):
  C0   the cube's read, unfiltered
  CP   C0 + firstUserDefaultChannelGroup in-list PAID = ("Cross-network", "Paid Search")
  CO   C0 + the NOT of CP's filter (everyone else)
  T0   date × firstSessionDate (no country), unfiltered
  TP   T0 + CP's filter
  NP   install-day users: date × countryId, metric newUsers, CP's filter (users whose first open is D)
  N0   the same, unfiltered
A record per read: accepted or the HTTP class / status (never the text), rows, "(other)" / "(not set)" shares, GA4's flags
(dataLossFromOtherRow, sampling, thresholding), the answer's rowCount vs the rows kept ("cut"), the quota tokens the
response reported and the seconds.

Comparisons (a cell = country × install day; money in micros):
  CP + CO vs C0   overlap = Σ min ÷ Σ max over the union of cells, for revenue and for users, and the Σ ratio (CP+CO)/C0
  TP vs Σ CP      per install day: Σ countries of CP ÷ TP, revenue (and T0 vs Σ C0 the same)
  paid share      CP ÷ C0, revenue and users (informational)
  NP vs Ads       NP ÷ the Google Ads installs of the same app × install day × country (the site ROI files' country packs:
                  row = [day, new users, Google Ads installs, spend, …]): Σ ratio, and the median per-country ratio over
                  countries with ≥ ADS_MIN installs; N0 ÷ Ads the same, the old ratio, for contrast

Verdict per app:
  whole  CP and CO accepted on every day, not cut, no sampling / thresholding / dataLossFromOtherRow, no "(other)" rows
  tie    CP + CO vs C0 revenue overlap ≥ TIE_MIN on every day
  go when both hold (and every day asked was read); nogo when either fails; unknown otherwise.
  The users tie is reported only, never part of the verdict.

LIMITS: the d1d7 probe's quota rule per PROPERTY (any token bucket under half, ≤ 4 server-error / ≤ 5 thresholded requests
left, a 429, 2 failed calls on 5xx), one request at a time per property (WORKERS properties in parallel), at most APP_CALLS
an app, MAX_CALLS GA4 calls in all (input "max_calls"), no call after BUDGET_SEC. What is read is kept and written.

PUBLIC LOG: counts only — progress (calls, seconds, apps) and ONE result line: apps probed, reads made, accepted / refused /
failed, go / nogo / unknown. Never a name, id, date, amount or per-app number (stderr is hidden by the workflow). The full
result is in the PRIVATE repo.
"""

import gzip
import json
import os
import re
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from admob_iq import ga4_probe
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_audience_probe as ap
from admob_iq.fetch import ga4_country_probe as cp
from admob_iq.fetch import ga4_cube as gcu
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_device_probe as dp
from admob_iq.fetch import ga4_shape_probe as sp
from admob_iq.fetch import ga4_uninstall as gu
from admob_iq.fetch.ga4_d1d7_probe import Stop

CHANNEL = "firstUserDefaultChannelGroup"
PAID = ("Cross-network", "Paid Search")       # the owner's grouping: Google Ads users
DAY_OFFSETS = (0, 30, 100, 300)               # F − n
FINAL_LAG = 5                                 # F = today − 5
DIMS = gcu.DIMS                               # date, firstSessionDate, countryId
DIMS_T = ("date", "firstSessionDate")
DIMS_N = ("date", "countryId")
METS = gcu.METS                               # activeUsers, totalAdRevenue
METS_N = ("newUsers",)
KINDS = ("C0", "CP", "CO", "TP", "T0", "NP", "N0")      # the order they are read in: the verdict's own reads first
TIE_MIN = 0.99
ADS_MIN = 20                                  # Google Ads installs a country needs for the per-country median
MAX_CALLS = 1000                              # GA4 calls in all (7 reads × 4 days × 27 apps = 756, plus pages)
APP_CALLS = 60
WORKERS = 4
BUDGET_SEC = 20 * 60
TICK_SEC = 20
DATA_DIR = "_private"
OUT_PATH = "ga4/paid_probe.json"
OTHER = "(other)"
SKIP_CC = frozenset(("--", "XX", "ZZ"))
PACK_RE = re.compile(r"^roi_[0-9a-f]{12}_c\d{2,3}\.json\.gz$")
SKIP = "skip"                                 # a day with nothing to judge a check by (never counted)


class Run(cp.Run):
    """cp.Run (budget, run-wide call cap) with this probe's heartbeat words."""

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
            self.say("paid progress: calls %d, %ds" % (n, s))


# ── the request shapes ───────────────────────────────────────────────────────────────────────────

def pick_days(f, hs=None):
    """F, F − 30, F − 100, F − 300 — never before the history start hs (that day is used instead, the nearest valid one),
    no duplicates, newest first."""
    out = []
    for n in DAY_OFFSETS:
        d = f - timedelta(days=n)
        if hs and d < hs:
            d = hs
        if d <= f and d not in out:
            out.append(d)
    return out


def paid_filter():
    return ga4._in_list(CHANNEL, PAID)


def request(kind, d):
    """The kind's GA4 request on activity day d → {"body", "extra", "dims", "mets"} (no event filter on any)."""
    if kind in ("NP", "N0"):
        dims, mets = DIMS_N, METS_N
    elif kind in ("TP", "T0"):
        dims, mets = DIMS_T, METS
    else:
        dims, mets = DIMS, METS
    body = gcu.body(d, d, dims)
    body["metrics"] = ga4._dim(*mets)
    if kind in ("CP", "TP", "NP"):
        extra = [paid_filter()]
    elif kind == "CO":
        extra = [{"notExpression": paid_filter()}]
    else:
        extra = []
    return {"body": body, "extra": extra, "dims": dims, "mets": mets}


# ── cells and their comparisons ──────────────────────────────────────────────────────────────────

def micros(v):
    return int(round(float(v or 0) * 1e6))


def cells_of(rows, d):
    """Rows of the one-day read of activity day d → ({(cc, X): [micros, users]}, rows in no cell). A row in no cell: not
    the day, an install day that is not a date, countryId "(other)", an install day after d."""
    out, rest, ds = {}, 0, d.isoformat()
    for r in rows or []:
        x = gcu._real(r.get("firstSessionDate"))
        cc = gcu._cc(r)
        if gcu._real(r.get("date")) != ds or x is None or cc == OTHER or x > ds:
            rest += 1
            continue
        c = out.setdefault((cc, x), [0, 0])
        c[0] += micros(r.get("totalAdRevenue"))
        c[1] += dp._num(r.get("activeUsers"))
    return out, rest


def by_install(rows, d):
    """The no-country read → {X: [micros, users]} for the day d."""
    out = {}
    for r in rows or []:
        x = gcu._real(r.get("firstSessionDate"))
        if x is None or gcu._real(r.get("date")) != d.isoformat():
            continue
        c = out.setdefault(x, [0, 0])
        c[0] += micros(r.get("totalAdRevenue"))
        c[1] += dp._num(r.get("activeUsers"))
    return out


def by_country(rows, d):
    """The install-day users read → {cc: newUsers} for the day d ("(other)" rows are not countries)."""
    out = {}
    for r in rows or []:
        cc = gcu._cc(r)
        if gcu._real(r.get("date")) != d.isoformat() or cc == OTHER:
            continue
        out[cc] = out.get(cc, 0) + dp._num(r.get("newUsers"))
    return out


def overlap(a, b, i):
    """Σ min ÷ Σ max of component i over the union of the cells: 1.0 = identical, a missing cell counts as 0."""
    lo = hi = 0.0
    for k in set(a) | set(b):
        x, y = max(a.get(k, (0, 0))[i], 0), max(b.get(k, (0, 0))[i], 0)
        lo += min(x, y)
        hi += max(x, y)
    return round(lo / hi, 6) if hi else None


def merge(a, b):
    out = {k: list(v) for k, v in a.items()}
    for k, v in b.items():
        c = out.setdefault(k, [0, 0])
        c[0] += v[0]
        c[1] += v[1]
    return out


def tie_cells(c0, p, o):
    """CP + CO against C0, cell by cell: the overlap of revenue / users and Σ (CP+CO) ÷ Σ C0 of each."""
    m = merge(p, o)
    return {"cells": len(c0), "merged": len(m), "only_c0": len(set(c0) - set(m)), "only_merged": len(set(m) - set(c0)),
            "rev": overlap(c0, m, 0), "users": overlap(c0, m, 1),
            "rev_ratio": pr._ratio(sum(v[0] for v in m.values()), sum(v[0] for v in c0.values())),
            "users_ratio": pr._ratio(sum(v[1] for v in m.values()), sum(v[1] for v in c0.values()))}


def share(p, c0):
    """The paid part of C0: Σ CP ÷ Σ C0 for revenue and users (informational)."""
    return {"rev": pr._ratio(sum(v[0] for v in p.values()), sum(v[0] for v in c0.values())),
            "users": pr._ratio(sum(v[1] for v in p.values()), sum(v[1] for v in c0.values()))}


def coverage(cells, tot):
    """Per install day: Σ countries of the cell read ÷ the no-country read, revenue → ({X: ratio}, the smallest ratio or
    None). Days with no revenue in the no-country read are not judged."""
    sums = {}
    for (cc, x), v in cells.items():
        sums[x] = sums.get(x, 0) + v[0]
    out = {x: pr._ratio(sums.get(x, 0), t[0]) for x, t in tot.items() if t[0] > 0}
    vals = [v for v in out.values() if v is not None]
    return out, (min(vals) if vals else None)


def named(cc):
    return len(cc) == 2 and cc.isalpha() and cc not in SKIP_CC


def ads_cmp(np, n0, ads):
    """NP and N0 (install-day users by country) against the Google Ads installs of the same day {cc: installs}: Σ over named
    countries and the median per-country ratio over countries with ≥ ADS_MIN installs."""
    a = {cc: v for cc, v in (ads or {}).items() if named(cc)}
    sa = sum(a.values())
    out = {"data": True, "ads": sa, "countries": len(a), "judged": sum(1 for v in a.values() if v >= ADS_MIN)}
    for name, got in (("np", np), ("n0", n0)):
        if got is None:
            continue
        g = {cc: v for cc, v in got.items() if named(cc)}
        ratios = [g.get(cc, 0) / v for cc, v in a.items() if v >= ADS_MIN]
        out[name] = sum(g.values())
        out[name + "_ratio"] = pr._ratio(sum(g.values()), sa)
        out[name + "_median"] = round(statistics.median(ratios), 4) if ratios else None
    return out


def ads_installs(site_dir, key, days):
    """The Google Ads installs {day: {cc: installs}} of the days (ISO strings) from the site ROI file's country packs; None
    when there is no file, no pack or it does not read."""
    if not site_dir:
        return None
    try:
        with gzip.open(os.path.join(site_dir, "roi_%s.json.gz" % key), "rt", encoding="utf-8") as f:
            body = json.load(f)
        out = {x: {} for x in days}
        read = False
        for pf, _ in ((body.get("cd") or {}).get("packs") or []):
            if not isinstance(pf, str) or not PACK_RE.match(pf):
                continue
            with gzip.open(os.path.join(site_dir, pf), "rt", encoding="utf-8") as f:
                pk = json.load(f)
            read = True
            for cc, rows in (pk.get("c") or {}).items():
                for r in rows:
                    if len(r) >= 3 and r[0] in out and isinstance(r[2], (int, float)):
                        out[r[0]][cc] = out[r[0]].get(cc, 0) + r[2]
        return out if read else None
    except (OSError, ValueError, EOFError, AttributeError, TypeError):
        return None


# ── the verdict ──────────────────────────────────────────────────────────────────────────────────

def clean(rec):
    """An accepted read with none of the flags that make it not whole."""
    return bool(rec.get("ok")) and not (rec.get("cut") or rec.get("thresh") or rec.get("loss") or rec.get("sampled")
                                        or rec.get("other_rows"))


def _every(vals):
    """False when any day is False; None when no day was judged or one that had to be was not; else True."""
    v = [x for x in vals if x is not SKIP]
    if any(x is False for x in v):
        return False
    return True if v and all(x is True for x in v) else None


def _whole(days):
    recs = [(d.get("reads") or {}).get(k) for d in days.values() for k in ("CP", "CO")]
    got = [r for r in recs if r]
    if any((r.get("ok") and not clean(r)) or (not r.get("ok") and cp._final(r.get("err"))) for r in got):
        return False
    if days and len(got) == 2 * len(days) and all(r.get("ok") for r in got):
        return True
    return None


def _sum(rec):
    try:
        return float(rec["s"]["totalAdRevenue"]["sum"])
    except (KeyError, TypeError, ValueError):
        return None


def _tie_day(day):
    """One day's tie check: None when C0, CP or CO is missing or not accepted (the day was not read, so it cannot be
    skipped); SKIP when there is no revenue to judge; on a day whose C0 carries a flag (the cell read drops its "(other)"
    rows, so the cell tie would measure C0's loss, not the filter) the all-row revenue sums are tied instead."""
    reads = day.get("reads") or {}
    if not all((reads.get(k) or {}).get("ok") for k in ("C0", "CP", "CO")):
        return None
    t = (day.get("cmp") or {}).get("tie")
    if not isinstance(t, dict):
        return None
    if not clean(reads["C0"]):
        a, b, c = _sum(reads["C0"]), _sum(reads["CP"]), _sum(reads["CO"])
        if None in (a, b, c):
            return None
        return SKIP if a <= 0 else (b + c) / a >= TIE_MIN
    return SKIP if t.get("rev") is None else t["rev"] >= TIE_MIN


def verdict(days, complete):
    """days: {D: {"reads": {kind: record}, "cmp": {...}}} → {"checks": {...}, "verdict": go | nogo | unknown}."""
    checks = {"whole": _whole(days), "tie": _every(_tie_day(d) for d in days.values())}
    vals = list(checks.values())
    out = "nogo" if any(v is False for v in vals) else ("go" if complete and all(v is True for v in vals) else "unknown")
    return {"checks": checks, "verdict": out}


# ── one app ──────────────────────────────────────────────────────────────────────────────────────

def probe_app(run, u, token, now, prop, opts, site_dir=None):
    tz_today = ga4.window_end_in(u["tz"], now, lag=0)
    f = tz_today - timedelta(days=FINAL_LAG)
    hs = gu._d(u["history_start"]) if u.get("history_start") else None
    res = {"key": u["key"], "F": f.isoformat(), "days": {}}
    if not token:
        res.update(err={"type": "auth"}, complete=False)
        return res
    days = pick_days(f, hs)
    res["asked"] = [d.isoformat() for d in days]
    ads = pr._safely(ads_installs, site_dir, u["key"], res["asked"], fallback=None)
    ga = cp.App(token, u["property_id"], u["stream_id"], run, prop, cap=opts.get("app_calls", APP_CALLS))
    try:
        for d in days:
            day = res["days"].setdefault(d.isoformat(), {"reads": {}, "cmp": {}})
            got = {}
            try:
                _day_reads(ga, d, day, got)
            finally:                                # (a Stop mid-day: the reads made are compared all the same)
                day["cmp"] = pr._safely(compare, got, d, None if ads is None else ads.get(d.isoformat()), fallback={})
    except Stop as e:
        res["stopped"] = str(e)
    res["complete"] = "stopped" not in res and len(res["days"]) == len(days)
    res["verdict"] = pr._safely(verdict, res["days"], res["complete"], fallback={"verdict": "unknown"})
    res.update(calls=ga.by_kind, tokens=ga.tok, sec=round(ga.sec, 2))
    return res


def _day_reads(ga, d, day, got):
    """The seven reads of activity day d into day["reads"] (records) and got (what came back, parsed)."""
    for kind in KINDS:
        req = request(kind, d)
        meta = {}

        def fetch(req=req):
            rows = ga.report_all(req["body"], extra=req["extra"], page_rows=gu.UNI_PAGE_ROWS)
            meta["rc"], meta["cut"] = ga.last_row_count, bool(ga.truncated(rows))
            return rows

        def parse(rows, req=req, kind=kind):
            dims, mets = req["dims"], req["mets"]
            rec = {"rows": len(rows), "row_count": meta.get("rc"), "cut": meta.get("cut", False),
                   "other_rows": sum(1 for r in rows if dp._other(r, dims)),
                   "unset_rows": sum(1 for r in rows if dp._unset(r, dims) and not dp._other(r, dims)),
                   "s": dp.shares(rows, dims, mets)}
            if kind in ("TP", "T0"):
                return rec, by_install(rows, d)
            if kind in ("NP", "N0"):
                return rec, by_country(rows, d)
            cells, rest = cells_of(rows, d)
            rec.update(cells=len(cells), in_no_cell=rest)
            return rec, cells

        rec, idx = cp._read(ga, kind, fetch, parse)
        day["reads"][kind] = rec
        if rec.get("ok") and idx is not None:
            got[kind] = idx


def compare(got, d, ads_day):
    """One day's comparisons from the answers in memory."""
    out, c0, p, o = {}, got.get("C0"), got.get("CP"), got.get("CO")
    if c0 is not None and p is not None and o is not None:
        out["tie"] = tie_cells(c0, p, o)
    if c0 is not None and p is not None:
        out["share"] = share(p, c0)
    if p is not None and "TP" in got:
        out["cov_p"], out["cov_p_min"] = coverage(p, got["TP"])
    if c0 is not None and "T0" in got:
        out["cov_0"], out["cov_0_min"] = coverage(c0, got["T0"])
    if "NP" in got or "N0" in got:
        out["ads"] = {"data": False} if ads_day is None else ads_cmp(got.get("NP"), got.get("N0"), ads_day)
    return out


# ── counts and the public line ───────────────────────────────────────────────────────────────────

def counts(apps, run):
    c = {"apps": len(apps), "reads": 0, "accepted": 0, "refused": 0, "failed": 0, "go": 0, "nogo": 0, "unknown": 0}
    for a in apps.values():
        for d in ((a or {}).get("days") or {}).values():
            for r in (d.get("reads") or {}).values():
                c["reads"] += 1
                if r.get("ok"):
                    c["accepted"] += 1
                elif cp._final(r.get("err")):
                    c["refused"] += 1
                else:
                    c["failed"] += 1
        v = ((a or {}).get("verdict") or {}).get("verdict")
        c[v if v in ("go", "nogo") else "unknown"] += 1
    c.update(calls=run.calls, seconds=run.elapsed())
    return c


def public_line(c):
    return ("paid probe: apps %d, reads %d, accepted %d, refused %d, failed %d, go %d, nogo %d, unknown %d, calls %d, %ds"
            % tuple(c.get(k, 0) for k in ("apps", "reads", "accepted", "refused", "failed", "go", "nogo", "unknown",
                                          "calls", "seconds")))


def run_probe(units, cid, sec, tokens, opts, now=None, clock=time.monotonic, last=None):
    """Probe every unit → the report; the apps of `last` (the last report's, same rules) not probed now are carried
    over as they were. Never raises for one app."""
    run = Run(opts.get("budget") or BUDGET_SEC, clock, opts.get("max_calls") or MAX_CALLS)
    now = now or datetime.now(timezone.utc)
    rt, access = dict(tokens), {}
    for owner in sorted({u.get("owner") or "" for u in units}):
        try:
            access[owner] = ga4.access_token(cid, sec, rt[owner]) if owner in rt else None
        except Exception:
            access[owner] = None
    probed = {u["key"] for u in units}
    out = {k: v for k, v in (last or {}).items() if k not in probed}
    props = {u["property_id"]: pr.new_prop() for u in units}
    lock, done = threading.Lock(), [0]

    def one(group):
        for u in group:
            try:
                r = probe_app(run, u, access.get(u.get("owner") or ""), now, props[u["property_id"]], opts,
                              opts.get("site_dir"))
            except Exception as e:
                r = {"key": u["key"], "crash": type(e).__name__, "complete": False}
            with lock:
                out[u["key"]] = r
                done[0] += 1
                n = done[0]
            run.say("paid progress: apps %d/%d, calls %d, %ds" % (n, len(units), run.calls, run.elapsed()))

    with sp.Beat(run, TICK_SEC):
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            list(ex.map(one, pr._groups(units)))
    c = pr._safely(counts, out, run, fallback={"apps": len(out), "calls": run.calls, "seconds": run.elapsed()})
    return {"v": 1, "probe": "ga4_paid", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rules": rules(run.max_calls), "counts": c, "apps": out}


def load_last(root, rules):
    """The last report's apps {key: result} made under the same rules ({} when there is none, or it was made under other
    days / filters / thresholds — never mixed in)."""
    try:
        with open(os.path.join(root, OUT_PATH), encoding="utf-8") as f:
            j = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(j, dict) or j.get("v") != 1:
        return {}
    keep = ("offsets", "paid", "tie_min", "channel")
    if {k: (j.get("rules") or {}).get(k) for k in keep} != {k: rules.get(k) for k in keep}:
        return {}
    return {k: v for k, v in (j.get("apps") or {}).items() if isinstance(v, dict)}


def rules(max_calls):
    return {"offsets": list(DAY_OFFSETS), "paid": list(PAID), "channel": CHANNEL, "tie_min": TIE_MIN,
            "ads_min": ADS_MIN, "max_calls": max_calls}


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    inputs = ap.event_inputs(env)
    want = ap.wanted(inputs.get("apps") or env.get("PAID_APPS"))
    root = env.get("PAID_DATA_DIR") or DATA_DIR           # the clone's top folder (the routes: sp adds data/ itself)
    if not os.path.isdir(os.path.join(root, "data")):
        sys.exit("no private clone: nothing to read the routes from")     # before any GA4 call (stderr is hidden)
    units = cp.units_from_state(sp.load_state(root))
    if want:
        units = [u for u in units if ap.matches(u, want) or u["key"] in want]
    if not units:
        sys.exit("no GA4 app routes in the private state (or none matched)")
    max_calls = pr._int(inputs.get("max_calls") or env.get("PAID_MAX_CALLS")) or MAX_CALLS
    last = load_last(root, rules(max_calls))
    print("paid probe: %d app(s) to probe, %d carried over" % (len(units), len(set(last) - {u["key"] for u in units})),
          flush=True)
    report = run_probe(units, cid, sec, tokens, {"app_calls": APP_CALLS, "site_dir": os.path.join(root, "site"),
                                                 "max_calls": max_calls}, now=now, clock=clock, last=last)
    print(public_line(report["counts"]), flush=True)
    if not pr.write_private(OUT_PATH, pr._dump(report), "ga4 paid probe"):
        sys.exit("private repo write failed")
    print("paid probe: report written", flush=True)


if __name__ == "__main__":
    main()
