"""One-off GA4 FLAG probe, run by .github/workflows/ga4-flag-probe.yml: what IS the cohort cube's "fl" mark on a day?
The cube (fetch/ga4_cube.py, module doc) marks a folded day "fl" for any of several GA4 signals — thresholding,
sampling, a cut answer, or dataLossFromOtherRow still on the final answer with no "(other)" row to measure it by — and
keeps none of GA4's own response metadata, so a mark alone never says which one it was. This probe reads flagged days
(and unflagged days beside them) again, in the cube's own request shape and in smaller ones, and keeps GA4's OWN
response metadata of every read verbatim: each mark can be named, and it shows whether any read shape comes back whole.
Read-only against GA4 and against the PRIVATE repo's data (the Uninstall state's routes, the cube's month files); the
only write is ga4/flag_probe.json in the PRIVATE repo.

Apps — by data, never by name: the N_APPS (2) apps whose all-users cube store (data/ga4_cube/<key>/<YYYY-MM>.json.gz,
its ledger "days") holds the most "fl" days among the FINAL days (≤ the property's today − the cube's FINAL_LAG) of the
last WINDOW (150) days; a tie: more revenue on those days, then the key. Days per app, in reading order: up to N_FL (10)
flagged days — the newest first, then each the newest flagged day at least GAP (14) days older than the last one taken
(fewer that way, the flags bunch: the rest filled one at a time with the flagged day farthest from every pick) — and
N_CTL (3) unflagged days with revenue as controls, each the nearest one to flagged pick 1, 3 and 5 and read right after
it (F1 C1 F2 F3 C2 F4 F5 C3 F6 …).

Reads of activity day D — one-day range [D, D], USD, keepEmptyRows false, every page at the cube's page size, the
cube's own builders (ga4_cube.body / cc_in / x_in; ga4_paid.expr) and the stream filter of every read as the cube's:
  R1  date × firstSessionDate × countryId, the cube's metrics: the cube's exact single-day read (split_read's first)
  R2  date only, no filter: the day's own total, as the cube's total call (day_total)
  R3  date × countryId
  R4  date × firstSessionDate
  R5  R1 + countryId in-list of ONE: R3's top named country by ad revenue (none: R5 is not asked, "na")
  R6  R1 + firstSessionDate in-list of ONE: D itself
  R7  R1 + the Google Ads users' filter (ga4_paid.expr, the paid cube's read) — on the first R7_DAYS (3) days only
A record per read: accepted or the HTTP class / status (never the text); rows, GA4's rowCount, pages, cut, and per page
its rowCount, its rows and its metadata VERBATIM (every field GA4 returned); from them the flags of any page —
dataLossFromOtherRow ("loss"), subjectToThresholding ("thresh"), samplingMetadatas ("sampled"; each [samplesReadCount,
samplingSpaceSize] in "smp", the smallest read fraction "smp_frac"), emptyReason ("empty") — and the metadata keys seen;
the "(other)" rows (any dimension "(other)": rows, revenue, users), "hidden" (loss with no "(other)" row: an in-list
dropped it), rows with no usable day / install day ("odd"), the sums (activeUsers; totalAdRevenue in micros), the named
countries / install days ("cc_n" / "x_n"); the tokens, seconds and calls (pages) the App counted. "whole": accepted,
not cut, none of GA4's flags, no "(other)" row.
Comparisons per day ("cmp", micros): every read's revenue against R2's total ("r" ratio, "d" difference) — R1 / R3 / R4
"tie" within the cube's rounding (½ micro a row + 1 ppm) when R2 is a total the cube itself would take ("t_ok"); R5
against R3's row of that country and R6 against R4's row of D ("want", "rw", "tie" the same way); the store's ledger
"t" against R2 ("led": what the fold kept vs GA4's total now).

LIMITS: at most MAX_CALLS (70) GA4 calls in all (input "max_calls" may only lower it), each app at most its share
(⌈calls ÷ apps⌉); the quota gate of the other probes (ga4_d1d7_probe.quota_low: any token bucket under half, ≤ 4
server-error / ≤ 5 thresholded requests left, a 429, 2 failed calls on 5xx) AND the build's own floors
(ga4_audience.quota_stop, ga4_firstopen.App's gate) — a property under either stops; no call after BUDGET_SEC. A Stop
ends the app's reads (a bug too, "crash": its class only): every read made is kept, compared and written. Resume
(input "resume", off by default): a day the last report (same rules) read whole, as the same kind of day with every
read of its plan, is carried as it was — not read again; the calls go to the next days.

PUBLIC LOG: counts only, over the result (carried days too) — one line (apps, days, carried, reads, this run's calls
and seconds, why apps stopped) and one per read kind: on flagged days and on control days, reads, accepted, refused,
failed, whole, loss, sampled, thresh, "(other)", hidden, cut, empty, tie. Never a key, date or amount (stderr is
hidden by the workflow). The full result is in the PRIVATE repo.
"""

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from admob_iq import ga4_probe
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_audience as gaud
from admob_iq.fetch import ga4_audience_probe as ap
from admob_iq.fetch import ga4_country_probe as cp
from admob_iq.fetch import ga4_cube as gcu
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_device_probe as dp
from admob_iq.fetch import ga4_paid
from admob_iq.fetch import ga4_shape_probe as sp
from admob_iq.fetch import ga4_uninstall as gu
from admob_iq.fetch.ga4_d1d7_probe import Stop

N_APPS = 2                                    # apps probed: the most flagged final days in the window
WINDOW = 150                                  # days back from the property's today
N_FL = 10                                     # flagged days an app at most
GAP = 14                                      # … about two weeks apart
N_CTL = 3                                     # unflagged days with revenue (controls) an app
CTL_AT = (0, 2, 4)                            # … each the nearest to flagged pick 1, 3, 5 (read right after it)
R7_DAYS = 3                                   # R7 on the first days of the reading order only
KINDS = ("R1", "R2", "R3", "R4", "R5", "R6", "R7")
BASE = KINDS[:6]                              # every day's reads (R7 only on the first R7_DAYS days)
DIMS_OF = {"R2": ("date",), "R3": ("date", "countryId"), "R4": ("date", "firstSessionDate")}   # else gcu.DIMS
WHOLE_DAY = ("R1", "R3", "R4")                # the shapes that hold the whole day: tied to R2's total
TALLY = ("n", "ok", "refused", "failed", "whole", "loss", "sampled", "thresh", "other", "hidden", "cut", "empty", "tie")
MAX_CALLS = 70                                # GA4 calls in all (input "max_calls" may only lower it)
WORKERS = N_APPS                              # properties in parallel — one request at a time per property
BUDGET_SEC = 20 * 60
TICK_SEC = 20
PAGE_ROWS = None                              # None: the cube's own page size (gu.UNI_PAGE_ROWS) — tests set less
DATA_DIR = "_private"
OUT_PATH = "ga4/flag_probe.json"
RULES_V = 1
KEEP = ("v", "window", "final_lag", "n_apps", "n_fl", "gap", "n_ctl", "ctl_at", "r7_days", "kinds")   # resume: the same


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
            self.say("flag progress: calls %d, %ds" % (n, s))


class App(cp.App):
    """cp.App (stream-pinned, paged, the other probes' quota gate, the property's 5xx / 429 stops, the run's budget and
    call cap, this app's call cap, calls / tokens / seconds per kind, every page's flags) + the build's own floors
    (gaud.quota_stop — ga4_firstopen.App's gate) before every call, and per read every page's rowCount, rows and
    metadata as GA4 returned them ("log": reset by the caller before each read)."""

    def __init__(self, token, property_id, stream_id, run, prop=None, cap=MAX_CALLS):
        super().__init__(token, property_id, stream_id, run, prop, cap)
        self.log = []

    def _gate(self):
        super()._gate()
        why = gaud.quota_stop(self.prop.get("quota"))
        if why:
            self.prop["stop"] = self.prop.get("stop") or why
            raise Stop(why)

    def _post(self, method, body):
        j = super()._post(method, body)
        self.log.append({"rc": j.get("rowCount"), "n": len(j.get("rows") or []), "meta": j.get("metadata") or {}})
        return j


# ── the apps and days, from the cube's store (no GA4 call) ───────────────────────────────────────────────────────────

def _od(D):
    return date.fromisoformat(D).toordinal()


def find_store(u, data_dir):
    """The unit's first AdMob app id with a cube store folder (data/ga4_cube/<key>/) → that id, or None."""
    for aid in u.get("app_ids") or [u["app_id"]]:
        if os.path.isdir(gcu.app_dir(data_dir, aid)):
            return aid
    return None


def ledgers(data_dir, aid, stream_id, lo, hi):
    """The cube's month files of THIS stream holding days lo … hi (gcu.month_path / _month_ok: the cube's own readers)
    → {D: its ledger fields} of those days only (each month's cells let go at once)."""
    out, a, b = {}, lo.isoformat(), hi.isoformat()
    k = lo.replace(day=1)
    while k <= hi:
        s = gu.load_store(gcu.month_path(data_dir, aid, k.strftime("%Y-%m")))
        if gcu._month_ok(s, stream_id):
            for D, led in s["days"].items():
                if isinstance(led, dict) and isinstance(D, str) and a <= D <= b:
                    out[D] = {f: led[f] for f in gcu.LEDGER + gcu.LEDGER_OPT if f in led}
        s = None
        k = (k + timedelta(days=32)).replace(day=1)
    return out


def spread(days, n=N_FL, gap=GAP):
    """Days (YYYY-MM-DD) → up to n of them in reading order: the newest, then each the newest at least `gap` days older
    than the last taken; fewer that way (the days bunch): the rest filled one at a time with the day farthest from
    every one taken (on a tie the newer)."""
    ds = sorted(set(days), reverse=True)
    out = []
    for D in ds:
        if len(out) >= n:
            break
        if not out or _od(out[-1]) - _od(D) >= gap:
            out.append(D)
    rest = [D for D in ds if D not in out]
    while out and rest and len(out) < n:
        far = max(rest, key=lambda D: (min(abs(_od(D) - _od(p)) for p in out), D))
        out.append(far)
        rest.remove(far)
    return out


def controls(clean, picks, n=N_CTL, at=CTL_AT):
    """Unflagged days with revenue → up to n controls [(anchor, D)]: the nearest one to flagged pick at[i] (on a tie the
    newer), each day once; an anchor missing (fewer picks) → the rest spread over the days left (anchor None)."""
    left, out = sorted(set(clean), reverse=True), []
    for i in at[:n]:
        if i < len(picks) and left:
            best = min(left, key=lambda D: (abs(_od(D) - _od(picks[i])), -_od(D)))
            out.append((i, best))
            left.remove(best)
    if len(out) < n and left:
        out += [(None, D) for D in spread(left, n - len(out))]
    return out


def plan_days(led, today):
    """An app's ledgers {D: …} and the property's today → its plan: the window [lo, hi] (hi = the newest final day),
    the days in reading order [(D, "fl" | "ctl")], the R7 days, their ledgers and the window's counts."""
    lo, hi = today - timedelta(days=WINDOW), today - timedelta(days=gcu.FINAL_LAG)
    a, b = lo.isoformat(), hi.isoformat()
    days = {}
    for D, v in (led or {}).items():
        try:
            ok = isinstance(v, dict) and a <= date.fromisoformat(D).isoformat() <= b
        except (TypeError, ValueError):
            ok = False
        if ok:
            days[D] = v
    fl = [D for D, v in days.items() if v.get("fl")]
    clean = [D for D, v in days.items() if not v.get("fl") and pr._int(v.get("t")) > 0]
    picks = spread(fl)
    ctl = controls(clean, picks)
    order = []
    for i, D in enumerate(picks):
        order.append((D, "fl"))
        order += [(C, "ctl") for j, C in ctl if j == i]
    order += [(C, "ctl") for j, C in ctl if j is None]
    return {"today": today.isoformat(), "lo": a, "hi": b, "order": order, "r7": [D for D, _ in order[:R7_DAYS]],
            "led": {D: days[D] for D, _ in order},
            "pick": {"final": len(days), "fl": len(fl), "clean": len(clean),
                     "fl_t": sum(pr._int(days[D].get("t")) for D in fl)}}


def choose(units, data_dir, now, n=N_APPS):
    """→ (the n units whose cube store holds the most flagged final days in the window — each with "key" (its store's
    file key) and "plan"; a tie: more revenue on those days, then the key —, how many units have a store). A unit whose
    store cannot be read is passed over."""
    cands, stores = [], 0
    for u in units:
        try:
            aid = find_store(u, data_dir)
            if aid is None:
                continue
            stores += 1
            today = ga4.window_end_in(u.get("tz") or "UTC", now, lag=0)
            lo, hi = today - timedelta(days=WINDOW), today - timedelta(days=gcu.FINAL_LAG)
            p = plan_days(ledgers(data_dir, aid, u["stream_id"], lo, hi), today)
        except Exception:
            continue
        if p["pick"]["fl"]:
            cands.append(dict(u, key=gu.file_key(aid), plan=p))
    cands.sort(key=lambda u: (-u["plan"]["pick"]["fl"], -u["plan"]["pick"]["fl_t"], u["key"]))
    return cands[:n], stores


def kinds_of(D, plan):
    return BASE + (("R7",) if D in plan["r7"] else ())


# ── the reads ────────────────────────────────────────────────────────────────────────────────────────────────────────

def request(kind, d, top=None):
    """The kind's request on activity day d → {"body", "extra", "dims"}: the cube's own builders, no event filter."""
    dims = DIMS_OF.get(kind, gcu.DIMS)
    extra = None                                  # R1 – R4: as the cube's root read and day total (extra None)
    if kind == "R5":
        extra = [gcu.cc_in([top])]
    elif kind == "R6":
        extra = [gcu.x_in([d.isoformat()])]
    elif kind == "R7":
        extra = [ga4_paid.expr()]                 # (ga4_paid.App adds it after the caller's own: none on R1)
    return {"body": gcu.body(d, d, dims), "extra": extra, "dims": dims}


def _mic(v):
    return int(round(float(v or 0) * 1e6))


def _r6(a, b):
    return round(a / b, 6) if a is not None and b else None


def _tol(n, T):
    """The cube's rounding tolerance (split_read): ½ micro a row + 1 ppm of the total."""
    return n // 2 + 1 + max(T, 0) // 1_000_000


def page_flags(log):
    """A read's pages → (loss, sampled, thresh, smp [[samplesReadCount, samplingSpaceSize] …], empty [emptyReason …],
    the metadata keys seen) — any page flagged = the read is flagged (cp._acc_add's rule)."""
    loss = sampled = thresh = False
    smp, empty, keys = [], [], set()
    for p in log or []:
        m = p.get("meta") if isinstance(p, dict) else None
        if not isinstance(m, dict):
            continue
        keys.update(str(k) for k in m)
        loss |= bool(m.get("dataLossFromOtherRow"))
        thresh |= bool(m.get("subjectToThresholding"))
        for s in m.get("samplingMetadatas") or []:
            sampled = True
            if isinstance(s, dict):
                smp.append([pr._int(s.get("samplesReadCount")), pr._int(s.get("samplingSpaceSize"))])
        if m.get("emptyReason"):
            empty.append(str(m["emptyReason"]))
    return loss, sampled, thresh, smp, empty, sorted(keys)


def parse(kind, rows, d, dims, seen):
    """One read's rows (+ seen: what its fetch saw — rowCount, pages, cut, each page's log) → (record, index for the
    day's comparisons)."""
    ds, has_x, has_c = d.isoformat(), "firstSessionDate" in dims, "countryId" in dims
    rev = users = unset = 0
    oth, odd = {"rows": 0, "rev": 0, "users": 0}, {"rows": 0, "rev": 0}
    by_cc, xs, xd = {}, set(), 0
    for r in rows:
        v, n = _mic(r.get("totalAdRevenue")), pr._int(r.get("activeUsers"))
        rev += v
        users += n
        if dp._other(r, dims):
            oth["rows"] += 1
            oth["rev"] += v
            oth["users"] += n
            continue
        unset += dp._unset(r, dims)
        x = gcu._real(r.get("firstSessionDate")) if has_x else None
        if gcu._real(r.get("date")) != ds or (has_x and (x is None or x > ds)):
            odd["rows"] += 1
            odd["rev"] += v
        if has_c:
            cc = gcu._cc(r)
            by_cc[cc] = by_cc.get(cc, 0) + v
        if x is not None:
            xs.add(x)
            if x == ds:
                xd += v
    loss, sampled, thresh, smp, empty, keys = page_flags(seen.get("log"))
    cut = bool(seen.get("cut"))
    rec = {"rows": len(rows), "row_count": seen.get("rc"), "pages": seen.get("pages"), "cut": cut,
           "pg": seen.get("log") or [], "smp": smp, "empty": empty, "keys": keys,
           "sum": {"activeUsers": users, "totalAdRevenue": rev}, "other": oth, "unset_rows": unset, "odd": odd,
           "hidden": loss and not oth["rows"],
           "whole": not (cut or loss or sampled or thresh) and not oth["rows"]}
    named = {c: v for c, v in by_cc.items() if c != gcu.NO_CC}
    if has_c:
        rec["cc_n"] = len(named)
    if has_x:
        rec["x_n"] = len(xs)
    idx = {"rev": rev, "n": len(rows)}
    if kind == "R2":                              # a total the cube's day_total would take (not RETRY, no odd row)
        idx["t_ok"] = rec["t_ok"] = not (loss or sampled or cut) and not gcu._other(rows)
    if kind == "R3":
        idx["cc"] = by_cc
        best = sorted(((v, c) for c, v in named.items() if v > 0), key=lambda vc: (-vc[0], vc[1]))
        idx["top"] = best[0][1] if best else None
    if kind == "R4":
        idx["xd"] = xd
    return rec, idx


def _fetch(ga, req, seen):
    def fetch():
        ga.log = []
        rows = ga.report_all(req["body"], extra=req["extra"], page_rows=PAGE_ROWS or gu.UNI_PAGE_ROWS)
        seen.update(rc=ga.last_row_count, pages=ga.last_pages, cut=bool(ga.truncated(rows)), log=list(ga.log))
        return rows
    return fetch


def _parse(kind, d, req, seen):
    return lambda rows: parse(kind, rows, d, req["dims"], seen)


def day_reads(ga, d, day, got):
    """The day's planned reads into day["reads"] (records) and got (the indexes of the accepted ones); R5 without a top
    country from R3 → day["na"]["R5"]. A Stop is passed on (the reads made stay in day)."""
    for kind in day["plan"]:
        top = None
        if kind == "R5":
            top = (got.get("R3") or {}).get("top")
            if not top:
                day["na"]["R5"] = "no_top"
                continue
            day["top"] = top
        req, seen = request(kind, d, top), {}
        rec, idx = cp._read(ga, kind, _fetch(ga, req, seen), _parse(kind, d, req, seen))
        day["reads"][kind] = rec
        if rec.get("ok") and isinstance(idx, dict):
            got[kind] = idx


def compare(got, day):
    """One day's comparisons from the indexes of its accepted reads (module doc, "cmp")."""
    out, t = {}, got.get("R2")
    if t is not None:
        T = t["rev"]
        out.update(t=T, t_ok=t["t_ok"])
        led_t = (day.get("led") or {}).get("t")
        if isinstance(led_t, (int, float)):
            out["led"] = {"t": int(led_t), "r": _r6(led_t, T), "d": int(led_t) - T}
        for k in ("R1", "R3", "R4", "R5", "R6", "R7"):
            g = got.get(k)
            if g is None:
                continue
            c = out.setdefault(k, {})
            c.update(r=_r6(g["rev"], T), d=g["rev"] - T)
            if k in WHOLE_DAY and t["t_ok"]:
                c["tie"] = abs(g["rev"] - T) <= _tol(g["n"] + t["n"], T)
    for k, src in (("R5", "R3"), ("R6", "R4")):
        g, s = got.get(k), got.get(src)
        if g is None or s is None:
            continue
        want = s["cc"].get(day.get("top"), 0) if k == "R5" else s["xd"]
        out.setdefault(k, {}).update(want=want, rw=_r6(g["rev"], want),
                                     tie=abs(g["rev"] - want) <= _tol(g["n"] + 1, want))
    return out


def _done(day):
    reads, na = day.get("reads") or {}, day.get("na") or {}
    return all(k in na or cp._done(reads.get(k)) for k in day.get("plan") or ())


def _carry(prev, typ, kinds):
    """The last report's record of a day → itself when it can stand for this run's (resume): read whole, the same kind
    of day, every read of this plan in its plan; else None."""
    if (isinstance(prev, dict) and prev.get("done") and prev.get("type") == typ
            and set(kinds) <= set(prev.get("plan") or ())):
        return prev
    return None


# ── one app ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def probe_app(run, u, token, prop, opts, now, last=None):
    p = u["plan"]
    res = {"key": u["key"], "today": p["today"], "window": [p["lo"], p["hi"]], "pick": p["pick"],
           "order": [D for D, _ in p["order"]], "r7": list(p["r7"]), "days": {}}
    if not token:
        res.update(err={"type": "auth"}, complete=False)
        return res
    ga = App(token, u["property_id"], u["stream_id"], run, prop, cap=opts.get("app_calls") or MAX_CALLS)
    old = ((last or {}).get("days") or {}) if opts.get("resume") else {}
    at = gu._now_iso(now)
    try:
        for D, typ in p["order"]:
            kinds = kinds_of(D, p)
            prev = _carry(old.get(D), typ, kinds)
            if prev is not None:
                res["days"][D] = dict(prev, carried=True)
                continue
            day = {"type": typ, "led": p["led"].get(D), "plan": list(kinds), "reads": {}, "na": {}, "at": at}
            res["days"][D] = day
            got = {}
            try:
                day_reads(ga, date.fromisoformat(D), day, got)
            finally:                                # (a Stop mid-day: the reads made are compared all the same)
                day["cmp"] = pr._safely(compare, got, day, fallback={})
                day["done"] = _done(day)
                if not day["reads"] and not day["na"]:
                    del res["days"][D]              # a Stop before its first read: nothing of it
    except Stop as e:
        res["stopped"] = str(e)
    except Exception as e:                          # a bug: the reads made are kept all the same (its class only)
        res["crash"] = type(e).__name__
    res["complete"] = ("stopped" not in res and "crash" not in res and set(res["days"]) == set(res["order"])
                       and all(d.get("done") for d in res["days"].values()))
    res["sum"] = pr._safely(summary, res["days"], fallback={})
    res.update(calls=ga.by_kind, tokens=ga.tok, sec=round(ga.sec, 2))
    return res


# ── counts and the public lines ──────────────────────────────────────────────────────────────────────────────────────

def _t0():
    return dict.fromkeys(TALLY, 0)


def _tally(t, rec, tie):
    t["n"] += 1
    if rec.get("ok"):
        t["ok"] += 1
        for f in ("whole", "loss", "sampled", "thresh", "hidden", "cut"):
            t[f] += bool(rec.get(f))
        t["other"] += bool((rec.get("other") or {}).get("rows"))
        t["empty"] += bool(rec.get("empty"))
        t["tie"] += tie is True
    elif cp._final(rec.get("err")):
        t["refused"] += 1
    else:
        t["failed"] += 1


def summary(days):
    """An app's days → {"fl" | "ctl": {kind: TALLY counts}}."""
    out = {}
    for day in (days or {}).values():
        typ = "ctl" if day.get("type") == "ctl" else "fl"
        for kind, rec in (day.get("reads") or {}).items():
            _tally(out.setdefault(typ, {}).setdefault(kind, _t0()), rec,
                   ((day.get("cmp") or {}).get(kind) or {}).get("tie"))
    return out


def counts(apps, run):
    c, kinds, stops = {"apps": len(apps), "days": 0, "carried": 0, "reads": 0}, {}, {}
    for a in apps.values():
        a = a or {}
        if a.get("stopped"):
            stops[a["stopped"]] = stops.get(a["stopped"], 0) + 1
        for day in (a.get("days") or {}).values():
            c["days"] += 1
            c["carried"] += bool(day.get("carried"))
            typ = "ctl" if day.get("type") == "ctl" else "fl"
            for kind, rec in (day.get("reads") or {}).items():
                c["reads"] += 1
                k = kinds.setdefault(kind, {"fl": _t0(), "ctl": _t0()})
                _tally(k[typ], rec, ((day.get("cmp") or {}).get(kind) or {}).get("tie"))
    c.update(kinds=kinds, stopped=stops, calls=run.calls, seconds=run.elapsed())
    return c


def public_lines(c):
    st = c.get("stopped") or {}
    out = ["flag probe: apps %d, days %d, carried %d, reads %d, calls %d, %ds, stopped %s"
           % (tuple(pr._int(c.get(k)) for k in ("apps", "days", "carried", "reads", "calls", "seconds"))
              + (", ".join("%s %d" % (k, v) for k, v in sorted(st.items())) or "none",))]
    for kind in KINDS:
        k = (c.get("kinds") or {}).get(kind)
        if k:
            out.append("flag probe: %s %s" % (kind, " | ".join(
                typ + " " + " ".join("%s %d" % (f, pr._int((k.get(typ) or {}).get(f))) for f in TALLY)
                for typ in ("fl", "ctl"))))
    return out


# ── the run ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def rules(max_calls):
    return {"v": RULES_V, "window": WINDOW, "final_lag": gcu.FINAL_LAG, "n_apps": N_APPS, "n_fl": N_FL, "gap": GAP,
            "n_ctl": N_CTL, "ctl_at": list(CTL_AT), "r7_days": R7_DAYS, "kinds": list(KINDS), "max_calls": max_calls,
            "page_rows": gu.UNI_PAGE_ROWS, "quota_frac": pr.QUOTA_FRAC}


def run_probe(units, cid, sec, tokens, opts, now=None, clock=time.monotonic, last=None):
    """Probe every chosen unit (each with its "key" and "plan": choose) → the report. last: the last report's apps
    {key: result} (resume). Never raises for one app; prints counts-only progress."""
    run = Run(opts.get("budget") or BUDGET_SEC, clock, min(MAX_CALLS, opts.get("max_calls") or MAX_CALLS))
    now = now or datetime.now(timezone.utc)
    app_calls = opts.get("app_calls") or -(-run.max_calls // max(1, len(units)))
    o = dict(opts, app_calls=app_calls)
    rt, access = dict(tokens), {}
    for owner in sorted({u.get("owner") or "" for u in units}):
        try:
            access[owner] = ga4.access_token(cid, sec, rt[owner]) if owner in rt else None
        except Exception:
            access[owner] = None
    props = {u["property_id"]: pr.new_prop() for u in units}
    out, lock, done = {}, threading.Lock(), [0]

    def one(group):
        for u in group:
            try:
                r = probe_app(run, u, access.get(u.get("owner") or ""), props[u["property_id"]], o, now,
                              (last or {}).get(u["key"]))
            except Exception as e:                  # a bug for one app must not cost the other
                r = {"key": u["key"], "crash": type(e).__name__, "complete": False}
            with lock:
                out[u["key"]] = r
                done[0] += 1
                n = done[0]
            run.say("flag progress: apps %d/%d, calls %d, %ds" % (n, len(units), run.calls, run.elapsed()))

    with sp.Beat(run, TICK_SEC):
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            list(ex.map(one, pr._groups(units)))
    c = pr._safely(counts, out, run, fallback={"apps": len(out), "calls": run.calls, "seconds": run.elapsed()})
    return {"v": 1, "probe": "ga4_flag", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rules": dict(rules(run.max_calls), app_calls=app_calls, resume=bool(opts.get("resume"))),
            "counts": c, "apps": out}


def load_last(root, want):
    """The last report's apps {key: result} when it was made under the same rules (KEEP); else {} — never mixed in."""
    try:
        with open(os.path.join(root, OUT_PATH), encoding="utf-8") as f:
            j = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(j, dict) or j.get("v") != 1:
        return {}
    if {k: (j.get("rules") or {}).get(k) for k in KEEP} != {k: want.get(k) for k in KEEP}:
        return {}
    return {k: v for k, v in (j.get("apps") or {}).items() if isinstance(v, dict)}


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    inputs = ap.event_inputs(env)
    root = env.get("FLAG_DATA_DIR") or DATA_DIR             # the clone's top folder (sp adds data/ itself)
    data = os.path.join(root, "data")
    if not os.path.isdir(data):
        sys.exit("no private clone: no cube store to choose the apps by")       # before any GA4 call
    units = cp.units_from_state(sp.load_state(root))
    if not units:
        sys.exit("no GA4 app routes in the private state")
    now = now or datetime.now(timezone.utc)
    n = pr._int(inputs.get("max_calls") or env.get("FLAG_MAX_CALLS"))
    max_calls = min(MAX_CALLS, n) if n > 0 else MAX_CALLS
    resume = ap._flag(inputs.get("resume") or env.get("FLAG_RESUME"))
    chosen, stores = choose(units, data, now)
    if not chosen:
        sys.exit("no cube store with a flagged final day in the window")
    last = load_last(root, rules(max_calls)) if resume else {}
    print("flag probe: %d app(s) chosen of %d with a cube store, %d day(s) planned%s"
          % (len(chosen), stores, sum(len(u["plan"]["order"]) for u in chosen), ", resuming" if resume else ""),
          flush=True)
    report = run_probe(chosen, cid, sec, tokens, {"max_calls": max_calls, "resume": resume}, now=now, clock=clock,
                       last=last)
    for line in public_lines(report["counts"]):
        print(line, flush=True)
    if not pr.write_private(OUT_PATH, pr._dump(report), "ga4 flag probe"):
        sys.exit("private repo write failed")               # stderr: hidden by the workflow step
    print("flag probe: report written", flush=True)


if __name__ == "__main__":
    main()
