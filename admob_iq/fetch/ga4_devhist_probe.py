"""One-off GA4 DEVICES ALL-TIME probe ("step 0" of the 📱 Devices All time design), run by
.github/workflows/ga4-devhist-probe.yml. The Devices tab keeps install days of the last ~130 days only; All time needs the
history fetch to read OLD install days (the oldest of an app is 1,000+ days back), and GA4 is known to drop users older than
~427 days from some reads (a read with firstSessionDate as its only dimension: Q-B). Whether the reads the history fetch
would use still answer WHOLE for such days is not known — this measures it, per app, on a few old install days, before any
history is fetched. Read-only against GA4 and against the PRIVATE repo's data (the Uninstall state's routes); the only
write is ga4/devices_alltime_probe.json (or ..._<tag>.json) in the PRIVATE repo.

PICK   one read per app, [first day, F]: dims firstSessionDate, newUsers → installs per install day; the install days
       probed are the busiest day within PICK_WIN of F − 200 and F − 450 (when the app is that old) and the busiest of the
       OLD_WIN oldest days (never two within MIN_GAP days).
Per probed install day X (F = the newest final day, E − LATE; M = X's calendar month, MD = its days up to F):
  S     [X, F]   filter firstSessionDate == X   model × country     — the fetch's S split, run past age 427
  SC    [X, F]   the same                        country only
  SD    [X, F]   the same                        date               — revenue by activity day: how much comes after 427?
  T2    [X, F]   the same                        firstSessionDate   — truth shape 2 (the Q-B shape)
  T1    [M, F]   firstSessionDate in MD          firstSessionDate × date — truth shape 1 (the store's own `truths` shape)
  MB    [M, F]   firstSessionDate in MD          firstSessionDate × model × country — a MONTH in one call
  S365  [X, X+364] the S filter                  no dimension       — for the tie with the ROI row's revenue to 365
  and, on the OLDEST day only (their cost does not depend on the age, their wholeness might):
  P     [X, X]   X, paid users                   model × country    PT [M, F] paid, firstSessionDate × date (truth)
  D1    [X+1]    X, activeUsers                  model × country    D1T [M+1, F] firstSessionDate × date (truth)
metrics newUsers, totalAdRevenue (SD also activeUsers). Each record: accepted or the HTTP class, rows, the tie (Σ rows ÷
the truth, per metric), the "(other)" share, the flags (thresholding / sampling / dataLossFromOtherRow), the tokens the
call used and its seconds. Per day "facts": the ties, SD's revenue by age band and its cumulative revenue at the ROI
checkpoints, S ÷ SD, MB ÷ S (totals and cell by cell), the month's MB ÷ T1.

PUBLIC LOG: counts only (per read kind: n, ok, refused, ties outside 0.98 … 1.02, with "(other)"; the same for reads of
days older than 427); stderr hidden by the workflow. Quota: the device probe's own App and floors (a property stops once a
token bucket is under half), one request at a time per property, properties side by side."""

import os
import re
import sys
import time
from calendar import monthrange
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
AGES = (200, 450)                   # install days near F − these (when the app is that old), and the app's oldest
PICK_WIN = 10                       # the busiest day within this many days of a target
OLD_WIN = 14                        # the oldest day = the busiest of the first this many days with installs
MIN_GAP = 30                        # two probed days are at least this far apart
OLD_AGE = 427                       # GA4's horizon for the firstSessionDate-only read (measured earlier)
NO_HS_DAYS = 1500                   # the PICK read starts here when the app's history start is not known
CHECKS = (0, 1, 3, 7, 14, 30, 60, 90, 180, 365)       # the ROI row's revenue checkpoints (age in days)
BANDS = (("0_30", 0, 30), ("31_90", 31, 90), ("91_180", 91, 180), ("181_365", 181, 365), ("366_427", 366, 427),
         ("gt427", OLD_AGE + 1, 10 ** 7))
MODEL, CC, CAMP = dp.MODEL, "countryId", dp.CAMP
NR = ("newUsers", "totalAdRevenue")
SD_METS = NR + ("activeUsers",)
METS = {"PICK": ("newUsers",), "S": NR, "SC": NR, "SD": SD_METS, "T1": NR, "T2": NR, "MB": NR, "S365": NR,
        "P": ("newUsers",), "PT": ("newUsers",), "D1": ("activeUsers",), "D1T": ("activeUsers",)}
KINDS = tuple(METS)
TIES = (("S", "T1"), ("SC", "T1"), ("SD", "T1"), ("T2", "T1"), ("MB", "T1"), ("P", "PT"), ("D1", "D1T"))
TIE_LO, TIE_HI = 0.98, 1.02         # the design's gate for "whole"
MAX_CALLS = 1500
APP_CALLS = 60                      # ~26 planned an app: room for pages
WORKERS = 4
BUDGET_SEC = 20 * 60                # no new call after 20 min (the job's timeout is 40)
TICK_SEC = 20
PAGE_ROWS = 100000
DATA_DIR = "_private"
OUT_PATH = "ga4/devices_alltime_probe.json"


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
            self.say("devhist progress: calls %d, %ds" % (n, s))


# ── the request shapes ──────────────────────────────────────────────────────────────────────────

def _fsd(x):
    return {"filter": {"fieldName": "firstSessionDate", "stringFilter": {"matchType": "EXACT", "value": pr._ymd(x)}}}


def _fsd_in(days):
    return {"filter": {"fieldName": "firstSessionDate", "inListFilter": {"values": [pr._ymd(d) for d in days]}}}


def month_of(x, f):
    """x's calendar month → (first day, last day up to f, every day of it up to f)."""
    m0 = x.replace(day=1)
    m1 = min(x.replace(day=monthrange(x.year, x.month)[1]), f)
    return m0, m1, [m0 + timedelta(days=i) for i in range((m1 - m0).days + 1)]


def reads_for(x, f, oldest=False):
    """[(kind, a, b, dims, mets, extra)] for install day x (F = f). The truth T1 first."""
    m0, m1, md = month_of(x, f)
    pick, one = _fsd_in(md), _fsd(x)
    out = [("T1", m0, f, ("firstSessionDate", "date"), NR, [pick]),
           ("S", x, f, (MODEL, CC), NR, [one]),
           ("SC", x, f, (CC,), NR, [one]),
           ("SD", x, f, ("date",), SD_METS, [one]),
           ("T2", x, f, ("firstSessionDate",), NR, [one]),
           ("MB", m0, f, ("firstSessionDate", MODEL, CC), NR, [pick])]
    if x + timedelta(days=364) <= f:
        out.append(("S365", x, x + timedelta(days=364), (), NR, [one]))
    if oldest:
        d1 = x + timedelta(days=1)
        paid = cp.paid_expr(CAMP)
        out += [("PT", m0, m1, ("firstSessionDate", "date"), ("newUsers",), [pick, paid]),
                ("P", x, x, (MODEL, CC), ("newUsers",), [one, paid])]
        if d1 <= f:
            out += [("D1T", m0 + timedelta(days=1), m1 + timedelta(days=1), ("firstSessionDate", "date"),
                     ("activeUsers",), [pick]),
                    ("D1", d1, d1, (MODEL, CC), ("activeUsers",), [one])]
    return out


def pick_days(counts, f, ages=AGES):
    """{install day: installs} → [(label, day)], the oldest first: the busiest day within PICK_WIN of f − age for each age
    the app reaches ("A<age>"), and the busiest of its OLD_WIN oldest days with installs ("OLD"). Days closer than
    MIN_GAP to one already kept (the extremes first) are left out."""
    have = {d: n for d, n in counts.items() if d <= f and n > 0}
    if not have:
        return []
    first = min(have)

    def busiest(lo, hi):
        c = [(n, d) for d, n in have.items() if lo <= d <= hi]
        return max(c, key=lambda t: (t[0], -t[1].toordinal()))[1] if c else None      # ties: the older day

    want = [("OLD", busiest(first, first + timedelta(days=OLD_WIN)))]
    for a in sorted(ages, reverse=True):
        t = f - timedelta(days=a)
        if t >= first:
            want.append(("A%d" % a, busiest(t - timedelta(days=PICK_WIN), t + timedelta(days=PICK_WIN))))
    kept = []
    for lab, d in want:
        if d is not None and all(abs((d - k).days) >= MIN_GAP for _, k in kept):
            kept.append((lab, d))
    return sorted(kept, key=lambda t: t[1])


# ── parses (rows in memory → numbers) ───────────────────────────────────────────────────────────

def _row_day(r, name):
    return ga4._d(r.get(name))


def t1_index(rows, f):
    """T1 rows (firstSessionDate × date) → {x: {"n" installs (the install day's own row), "rev" so far, "old" revenue at an
    age past OLD_AGE, "last" the age of the last day with revenue}}."""
    out = {}
    for r in rows:
        x, d = _row_day(r, "firstSessionDate"), _row_day(r, "date")
        if not x or not d or not (x <= d <= f):
            continue
        e = out.setdefault(x, {"n": 0.0, "rev": 0.0, "old": 0.0, "last": None})
        age, rev = (d - x).days, dp._num(r.get("totalAdRevenue"))
        if age == 0:
            e["n"] += dp._num(r.get("newUsers"))
        e["rev"] += rev
        if age > OLD_AGE:
            e["old"] += rev
        if rev > 0 and (e["last"] is None or age > e["last"]):
            e["last"] = age
    return out


def on_day(rows, x, met, off=0):
    """Σ met of the (firstSessionDate × date) rows of install day x on day x + off."""
    return sum(dp._num(r.get(met)) for r in rows
               if _row_day(r, "firstSessionDate") == x and _row_day(r, "date") == x + timedelta(days=off))


def vals(kind, x, rows, f):
    """A read's rows → {metric: number} for install day x (the rows of MB / T1 / PT / D1T hold the whole month)."""
    if kind == "T1":
        e = t1_index(rows, f).get(x) or {}
        return {"newUsers": e.get("n", 0.0), "totalAdRevenue": e.get("rev", 0.0)}
    if kind == "PT":
        return {"newUsers": on_day(rows, x, "newUsers")}
    if kind == "D1T":
        return {"activeUsers": on_day(rows, x, "activeUsers", 1)}
    if kind == "MB":
        rows = [r for r in rows if _row_day(r, "firstSessionDate") == x]
    return {m: dp._tot(rows, m) for m in METS[kind]}


def age_rev(rows, x):
    """SD rows (date) → ({age: revenue}, {age: activeUsers})."""
    rev, act = {}, {}
    for r in rows:
        d = _row_day(r, "date")
        if d and d >= x:
            a = (d - x).days
            rev[a] = rev.get(a, 0.0) + dp._num(r.get("totalAdRevenue"))
            act[a] = act.get(a, 0.0) + dp._num(r.get("activeUsers"))
    return rev, act


def sd_facts(rows, x, f):
    rev, act = age_rev(rows, x)
    tot = sum(rev.values())
    bands = {b: round(sum(v for a, v in rev.items() if lo <= a <= hi), 6) for b, lo, hi in BANDS}
    cum = {}
    for c in CHECKS:
        cum[str(c)] = round(sum(v for a, v in rev.items() if a <= c), 6) if x + timedelta(days=c) <= f else None
    return {"rev": round(tot, 6), "bands": bands, "share_gt427": pr._ratio(bands["gt427"], tot),
            "last_age": max((a for a, v in rev.items() if v > 0), default=None),
            "act_gt427": round(max((v for a, v in act.items() if a > OLD_AGE), default=0.0), 4),
            "cum": cum, "rev364": round(sum(v for a, v in rev.items() if a <= 364), 6)}


def cells(rows, x=None):
    """model × country rows → {(model, cc): revenue} (x: only the rows of that install day)."""
    out = {}
    for r in rows:
        if x is not None and _row_day(r, "firstSessionDate") != x:
            continue
        k = (str(r.get(MODEL) or ""), str(r.get(CC) or ""))
        out[k] = out.get(k, 0.0) + dp._num(r.get("totalAdRevenue"))
    return out


def overlap(a, b):
    """Σ min ÷ Σ max over the cells of two {cell: value}: 1.0 = the same cells with the same values."""
    ks = set(a) | set(b)
    hi = sum(max(a.get(k, 0.0), b.get(k, 0.0)) for k in ks)
    return round(sum(min(a.get(k, 0.0), b.get(k, 0.0)) for k in ks) / hi, 4) if hi else None


def ties_of(got, ref):
    return {m: dp.tie(got[m], ref.get(m)) for m in got if m in ref}


def facts_for(x, raw, f):
    """One install day's rows (kind → rows) → its numbers: per-kind values and ties, SD's age bands and checkpoints, S ÷ SD,
    MB ÷ S (totals and cell by cell), the month's MB ÷ T1."""
    v = {k: vals(k, x, rows, f) for k, rows in raw.items() if k != "PICK"}
    out = {"vals": {k: {m: round(n, 6) for m, n in d.items()} for k, d in v.items()}, "ties": {}, "x_ties": {}}
    for k, ref in TIES:
        if k in v and ref in v:
            out["ties"][k] = ties_of(v[k], v[ref])
    if "SD" in raw:
        out["sd"] = sd_facts(raw["SD"], x, f)
        sd = {"newUsers": v["SD"]["newUsers"], "totalAdRevenue": v["SD"]["totalAdRevenue"]}
        if "S" in v:
            out["x_ties"]["S_vs_SD"] = ties_of(v["S"], sd)
        if "S365" in v:
            out["x_ties"]["S365_vs_SD364"] = {"totalAdRevenue": dp.tie(v["S365"]["totalAdRevenue"], out["sd"]["rev364"])}
    if "T1" in raw:
        e = t1_index(raw["T1"], f).get(x) or {}
        out["t1"] = {"old_rev": round(e.get("old", 0.0), 6), "last_age": e.get("last"),
                     "share_gt427": pr._ratio(e.get("old", 0.0), e.get("rev"))}
        if "MB" in raw:
            month = t1_index(raw["T1"], f)
            ref = {"newUsers": sum(e["n"] for e in month.values()), "totalAdRevenue": sum(e["rev"] for e in month.values())}
            out["x_ties"]["MBmonth_vs_T1month"] = ties_of({m: dp._tot(raw["MB"], m) for m in NR}, ref)
    if "S" in raw and "MB" in raw:
        out["x_ties"]["MB_vs_S"] = ties_of(v["MB"], v["S"])
        out["x_ties"]["MBcells_vs_S"] = overlap(cells(raw["MB"], x), cells(raw["S"]))
    return out


# ── one app ─────────────────────────────────────────────────────────────────────────────────────

def probe_day(ga, res, f, lab, x, oldest, n):
    """Every read of one install day → res["reads"] / res["facts"]. A Stop is passed on after the facts of what was read."""
    raw, age = {}, (f - x).days
    res["xs"].append({"x": x.isoformat(), "label": lab, "age": age, "installs": n})
    try:
        for kind, a, b, dims, mets, extra in reads_for(x, f, oldest):
            body = dp._body(a, b, dims, mets)
            rec, rows = cp._read(ga, kind, lambda: ga.report_all(body, extra=extra, page_rows=PAGE_ROWS),
                                 dp.p_rows(dims, mets))
            rec.update(age=age, a=a.isoformat(), b=b.isoformat())
            res["reads"]["%s@%s" % (kind, x.isoformat())] = rec
            if rec.get("ok"):
                raw[kind] = rows
    finally:
        res["facts"][x.isoformat()] = pr._safely(facts_for, x, raw, f, fallback={"bug": True})
        for k, t in (res["facts"][x.isoformat()].get("ties") or {}).items():
            rec = res["reads"].get("%s@%s" % (k, x.isoformat()))
            if rec is not None:
                rec["tie"] = t


def probe_app(run, u, token, now, prop, opts):
    f = ga4.window_end_in(u["tz"], now) - timedelta(days=LATE)
    hs = gu._d(u["history_start"]) if u.get("history_start") else None
    h0 = hs or f - timedelta(days=NO_HS_DAYS)
    res = {"key": u["key"], "tz": u["tz"], "F": f.isoformat(), "hs": hs.isoformat() if hs else None, "xs": [],
           "reads": {}, "facts": {}}
    if not token:
        res.update(err={"type": "auth"}, complete=False)
        return res
    ga = cp.App(token, u["property_id"], u["stream_id"], run, prop, cap=opts.get("app_calls", APP_CALLS))
    try:
        body = dp._body(h0, f, ("firstSessionDate",), ("newUsers",))
        rec, rows = cp._read(ga, "PICK", lambda: ga.report_all(body, page_rows=PAGE_ROWS), dp.p_rows(("firstSessionDate",),
                                                                                                    ("newUsers",)))
        res["reads"]["PICK"] = rec
        counts = {}
        for r in rows or []:
            d = _row_day(r, "firstSessionDate")
            if d:
                counts[d] = counts.get(d, 0) + dp._num(r.get("newUsers"))
        res["days"] = len(counts)
        days = pick_days(counts, f, opts.get("ages") or AGES)
        for i, (lab, x) in enumerate(days):
            probe_day(ga, res, f, lab, x, i == 0, counts[x])
    except Stop as e:
        res["stopped"] = str(e)
    res["complete"] = "stopped" not in res and bool(res["xs"]) and (res["reads"].get("PICK") or {}).get("ok") is True
    res.update(calls=ga.by_kind, tokens=ga.tok, sec=round(ga.sec, 2), server_errors=ga.server_errors)
    return res


# ── counts-only public summary ──────────────────────────────────────────────────────────────────

def _bucket():
    return {"n": 0, "ok": 0, "refused": 0, "low": 0, "high": 0, "other": 0}


def _count(c, r):
    c["n"] += 1
    if r.get("ok"):
        c["ok"] += 1
        tie = list((r.get("tie") or {}).values())
        c["low"] += any(v is not None and v < TIE_LO for v in tie)
        c["high"] += any(v is not None and v > TIE_HI for v in tie)
        s = r.get("s") or {}
        if r.get("loss") or any(((s.get(m) or {}).get("other") or 0) > 0 for m in s):
            c["other"] += 1
    elif 400 <= ((r.get("err") or {}).get("http") or 0) < 500:
        c["refused"] += 1


def counts(apps, run):
    kinds, old = {}, _bucket()
    for a in apps.values():
        for k, r in ((a or {}).get("reads") or {}).items():
            _count(kinds.setdefault(k.split("@")[0], _bucket()), r)
            if (r.get("age") or 0) > OLD_AGE:
                _count(old, r)
    return {"apps": len(apps), "complete": sum(1 for a in apps.values() if (a or {}).get("complete")),
            "days": sum(len((a or {}).get("xs") or []) for a in apps.values()),
            "stopped": sum(1 for a in apps.values() if (a or {}).get("stopped")),
            "calls": run.calls, "tokens": sum(int((a or {}).get("tokens") or 0) for a in apps.values()),
            "seconds": run.elapsed(), "kinds": kinds, "gt427": old}


def public_lines(c):
    z = _bucket()
    out = []
    for k in KINDS:
        v = dict(z, **((c.get("kinds") or {}).get(k) or {}))
        out.append("devhist probe: %s n %d ok %d refused %d tie<0.98 %d tie>1.02 %d other %d"
                   % (k, v["n"], v["ok"], v["refused"], v["low"], v["high"], v["other"]))
    v = dict(z, **(c.get("gt427") or {}))
    out.append("devhist probe: older than 427 days n %d ok %d refused %d tie<0.98 %d tie>1.02 %d other %d"
               % (v["n"], v["ok"], v["refused"], v["low"], v["high"], v["other"]))
    out.append("devhist probe: apps %d, days %d, complete %d, stopped %d, calls %d, tokens %d, %ds"
               % (c.get("apps", 0), c.get("days", 0), c.get("complete", 0), c.get("stopped", 0), c.get("calls", 0),
                  c.get("tokens", 0), c.get("seconds", 0)))
    return out


# ── the run ─────────────────────────────────────────────────────────────────────────────────────

def run_probe(units, cid, sec, tokens, opts, now=None, clock=time.monotonic, workers=WORKERS, tick=TICK_SEC):
    import threading
    from concurrent.futures import ThreadPoolExecutor
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
            except Exception as e:                   # a bug for one app must not cost the others
                r = {"key": u["key"], "crash": type(e).__name__, "complete": False}
            with lock:
                out[u["key"]] = r
                n = len(out)
            run.say("devhist progress: apps %d/%d, calls %d, %ds" % (n, len(units), run.calls, run.elapsed()))

    with sp.Beat(run, tick):
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            list(ex.map(one, pr._groups(units)))
    c = pr._safely(counts, out, run, fallback={"apps": len(out), "calls": run.calls, "seconds": run.elapsed()})
    return {"v": 1, "probe": "ga4_devhist", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rules": {"ages": list(opts.get("ages") or AGES), "pick_win": PICK_WIN, "old_win": OLD_WIN, "min_gap": MIN_GAP,
                      "old_age": OLD_AGE, "late": LATE, "checks": list(CHECKS), "tie": [TIE_LO, TIE_HI],
                      "max_calls": run.max_calls, "app_calls": opts.get("app_calls", APP_CALLS)},
            "counts": c, "apps": out}


def options(inputs, env):
    def get(k, e):
        v = inputs.get(k)
        return env.get(e) if v is None or str(v).strip() == "" else v
    ages = tuple(a for a in (pr._int(t) for t in str(get("ages", "DEVHIST_AGES") or "").split(",")) if 30 <= a <= 5000)
    tag = re.sub(r"[^a-z0-9]", "", str(get("tag", "DEVHIST_TAG") or "").lower())[:20]
    return {"apps": ap.wanted(get("apps", "DEVHIST_APPS")), "ages": ages or AGES, "app_calls": APP_CALLS,
            "max_calls": pr._int(get("max_calls", "DEVHIST_MAX_CALLS")) or MAX_CALLS,
            "budget": pr._int(env.get("DEVHIST_BUDGET_SEC")) or BUDGET_SEC, "tag": tag}


def out_path(tag):
    return OUT_PATH.replace(".json", "_%s.json" % tag) if tag else OUT_PATH


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    opts = options(ap.event_inputs(env), env)
    units = cp.units_from_state(sp.load_state(env.get("DEVHIST_DATA_DIR") or DATA_DIR))
    if opts["apps"]:
        units = [u for u in units if ap.matches(u, opts["apps"]) or u["key"] in opts["apps"]]
    if not units:
        sys.exit("no GA4 app routes in the private state (or none matched)")
    print("devhist probe: %d app(s) to probe" % len(units), flush=True)
    report = run_probe(units, cid, sec, tokens, opts, now=now, clock=clock)
    for line in public_lines(report["counts"]):
        print(line, flush=True)
    if not pr.write_private(out_path(opts["tag"]), pr._dump(report), "ga4 devices all-time probe"):
        sys.exit("private repo write failed")            # stderr: hidden by the workflow step
    print("devhist probe: report written", flush=True)


if __name__ == "__main__":
    main()
