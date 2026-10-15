"""Install value, extended (IDAY_EXT, on top of GA4_IDAY): the reads the forecast needs past fetch_iday's cells, per
install week × country slot (and ad unit), each tied back to a read the fetch already trusts. Runs inside fetch_iday
(ga4_uninstall._Iday: its call cap, stops, budgets and counts) through hook(); NEVER changes a legacy key of the data
(x, c, days, cset, flags, …): everything lives in new keys, written to their own files.

THE READS (Ga4App adds the Android + stream filter, returnPropertyQuota, a total order and paging; D = one activity
day, F = the newest final day, E − IDAY_LATE; IDAY_METS = activeUsers, newUsers, totalAdRevenue, totalRevenue — the
last one dropped on a property that refuses it, flags.no_total; money in USD):
  QC full  [D, D]  countryId × firstSessionDate          IDAY_METS, TOTAL   no install-day list (every install age)
           — replaces the legacy Q-C in fetch_iday: its 91-day rows give the legacy cells unchanged (gu._le91)
  PAID     QC full + firstUserGoogleAdsCampaignId FULL_REGEXP "[^(].*" (a real campaign id: paid; "(not set)" /
           empty / "(…)" never match: organic = the full read − PAID), the probe's T2 rule
  parts    a QC full / PAID read split by country (countryId inList of every 2nd / 4th named slot; the last part also
           every other country) — only for a SAMPLED read, used only when the parts come back unsampled (SAMPLING)
  AU       [a, b] ≤ AU_DAYS days  adUnitName × firstSessionDate × date   totalAdRevenue, publisherAdImpressions,
           publisherAdClicks, USD (GA4 refuses the combination → without clicks → adFormat, … : AU_SHAPES, the first
           one accepted is kept per app; all refused → none for AU_RETRY_DAYS). The country probe had GA4 accept
           adUnitName / adFormat × date with publisherAdImpressions + totalAdRevenue on every app, and firstSessionDate
           × date is a production read (ga4_cohort) — the three together and publisherAdClicks were never asked: the
           first AU read of each property is that check, a refusal costs one call per shape
  RM       [a, b] ≤ RM_DAYS days  date × countryId  totalUsers, eventCount, TOTAL; eventName == app_remove (probe T4)

WHAT IT KEEPS (new keys of the iday data; slots = the legacy country slots, cset):
  c2[W][slot] = {r2: ad revenue micros at install ages 91-180 / 181-365 / 366-427, u2: active users at 120 / 180 / 270
                 / 365}; c2[W]["gap"] = {r2}: per lag, the same day's Q-B (install days ≥ history_start) − Σ named
                 countries — so Σ slots + gap = Q-B exactly, week by week and band by band (never spread)
  cp[W][slot] = {n: lag-0 new users, r: ad revenue per LBANDS (0 … 366-427), u: active users at LLAGS} of PAID users
  au[W][unit] = {r, i, k: ad revenue / impressions / clicks per LBANDS} (unit = an index into xs.au.units)
  rm[D]       = {s: {slot: [app_remove users, events]}, o: "(other)" [users, events], st, at, ev, tie, tu}
  d2[D]       = the per-day ledger of c2 / cp / au: c2st, c2tries, c2at, tie_late, c2loss, c2oth, c2smp, c2frac, c2rows,
                c2tok, c2parts · cpst, cptries, cpat, cpshare, cpn, cpx, cploss, cpoth, cpsmp, cpfrac, cprows, cptok,
                cpparts · aust, autries, auat, tie_au, auloss, auoth, ausmp, aufrac, aublk
                (st: ok · smp: sampled, tie inside · gap: "(other)" / loss / sampled with the tie outside / tries used
                up — the named rows folded, the rest unassigned · retry: tie outside without a flag, not folded, asked
                again (≤ IDAY_TRIES reads) · err: the call failed, asked again the next day)
  xs          = state: split {lv, no, at}, au {dim, mets, blk, units, off}, paid {off}, rm {off}, lo (the horizon of
                the last fetch: what the .old part may hold), since {country: {c2 / cp / rm: [[first, last], …]}}: a
                slot the legacy fetch added later (a country that grew) — the days that went in before it, into "ZZ"
                (the legacy cset_since, for the new keys)

THE STEPS (in fetch_iday's order; every day at most once a day; newest first):
  on_qc   every legacy Q-C read (a new day, a retry, the legacy backfill) is the full read: its late ages are judged
          and folded right there, tied to the same fetch's Q-B (no call of its own)
  ── every legacy read of the fetch is done here (Q-T included): the extension's reads only use what is left ──
  new     the paid read of the days step 1 read (tied to their full read, kept in memory)
  reread  the history re-read, inside the country horizon (F − IDAY_CTY_DAYS): days whose c2 / cp is still to do get
          a fresh full Q-C (+ a fresh Q-B: the late ages' tie, while they are to do; + PAID) — the backfill's budget
          rules (plain budget, hourly floor); their legacy cells are never touched again
  units   the AU blocks (≤ xs.au.blk consecutive days; the newest block waits until it is whole or a week old; a
          block that comes back sampled or lossy over several days → shorter blocks, 7 → 3 → 1, read again)
  finish  (after the legacy finish: the slots) xs.since, the RM blocks (days ≤ F − RM_LATE: app_remove keeps coming in
          for a week; one block a week), then this fetch's country cells into their slots
An app whose install-value history is whole gets install-value-only fetches (plan "iday", every 2 h) while this
still has days to do (iday_meta x2.done False): those are this module's alone (ga4_uninstall.x_only_fetch) — no legacy
step runs, no legacy key or count changes, so every legacy read keeps the schedule it has without IDAY_EXT. Its stops
(cap, budget, quota, hourly floor) are its own (stats x.why / qstops): the legacy log line reads as without it.

SAMPLING: the full Q-C of the biggest apps can come back sampled, and GA4 was seen to sample a filtered read exactly as
much as the unfiltered one (the 91-day list, the probe's PAID / ORG reads: the same sampling fraction; the full read's
ages 0..90 tied to Q-B exactly as the live 91-day read did, sampled days too) — so an install-age split cannot help.
A sampled read is split into country halves, then quarters, UNTIL the parts come back unsampled; parts that still
sample (or sample about as much as the whole: ≤ its fraction × (1 + SPLIT_GAIN), no deeper level is tried) are never
used: the whole read stays, flagged (smp / gap), and no split is tried for SPLIT_RETRY_DAYS. A level that worked is
kept (xs.split.lv) and the smallest one looked for again every SPLIT_RETRY_DAYS.

COST (after the history re-read), per app and day: PAID +1, one AU block and one RM block a week ≈ +1.3 in all; ≈ +1.5
/ +2.1 for an app whose 7-day AU blocks come back sampled (3-day / 1-day blocks). A sampled app: one split try a month
(2 + 4 calls) — and only if GA4 ever returns its parts unsampled, 2 or 4 parts for both the full and the paid read
every day (+3 / +7). The re-read: ≈ 3 calls per day of the horizon (Q-B, QC full, PAID) + its AU / RM blocks, on the
backfill's rules. Nothing here prints; the public log gets iday_x_log_line (counts).
"""

import copy
import os
from datetime import timedelta

from . import ga4
from . import ga4_uninstall as gu
from ..db import write_json_gz_stable

X_V = 1                     # the extension's file format (another one: its data starts over, the legacy file never)
LATE_LO = gu.CTY_LIST       # install ages from 91 (0..90 are the legacy cells)
LBANDS = gu.RBANDS + ((366, gu.QB_WIN),)                  # cp.r, au.r/i/k: install ages 0 … 366-427
LLAGS = gu.CLAGS + (120, 180, 270, 365)                   # cp.u: active users at these install ages
C2BANDS = ((91, 180), (181, 365), (366, gu.QB_WIN))       # c2.r2
C2LAGS = (120, 180, 270, 365)                             # c2.u2
LB_IX = gu._bands_ix(LBANDS, gu.QB_WIN)
C2B_IX = gu._bands_ix(C2BANDS, gu.QB_WIN)
LL_IX = {lag: i for i, lag in enumerate(LLAGS)}
C2L_IX = {lag: i for i, lag in enumerate(C2LAGS)}
PAID_DIM, PAID_RULE = "firstUserGoogleAdsCampaignId", "[^(].*"   # the probe's rule: a real Google Ads campaign id
PAID_RETRY_DAYS = 28        # a property that refused the paid filter is asked again after 4 weeks
AU_METS3 = ("totalAdRevenue", "publisherAdImpressions", "publisherAdClicks")
AU_SHAPES = (("adUnitName", AU_METS3), ("adUnitName", AU_METS3[:2]), ("adFormat", AU_METS3), ("adFormat", AU_METS3[:2]))
AU_DAYS = 7                 # days per AU block (one call a week per app); a sampled / lossy block → shorter (7 → 3 → 1)
AU_MAX = 100                # unit slots per app ("--" = not set, "ZZ" = every unit past the 99th)
AU_RETRY_DAYS = 28          # every shape refused: asked again after 4 weeks
RM_DAYS = 30                # days per RM block (the probe's T4 shape: one page)
RM_MIN = 7                  # … the newest block waits until it holds a week
RM_LATE = 7                 # app_remove of day D is read once D ≤ F − 7 (Firebase adds it for ~a week)
RM_GAP = 0.02               # Σ countries' app_remove events within 2% of the store's count of the day (else "q")
RM_RETRY_DAYS = 28          # a property that refused the app_remove read is asked again after 4 weeks
SPLIT_MAX = 2               # a sampled read: country halves, then quarters at most
SPLIT_GAIN = 0.25           # … kept only while the parts read ≥ 25% more of the data than the whole
SPLIT_RETRY_DAYS = 30       # a split that didn't help is tried again a month later
FOLDED = ("ok", "smp", "gap")
X_COUNTS = ("apps", "late", "late_ok", "late_smp", "late_gap", "late_retry", "split", "paid", "paid_smp", "paid_gap",
            "unit_days", "unit_blocks", "unit_gap", "rm_days", "rm_blocks", "left", "qstops", "errors")


def _d(s):
    return gu._d(s)


def _iso(d):
    return d.isoformat()


def _frac(meta):
    """The smallest samplesReadCount ÷ samplingSpaceSize of a response (None: not sampled / not given)."""
    frac = None
    for s in (meta or {}).get("samplingMetadatas") or []:
        try:
            v = int(s.get("samplesReadCount")) / int(s.get("samplingSpaceSize"))
        except (TypeError, ValueError, ZeroDivisionError, AttributeError):
            continue
        frac = round(v if frac is None else min(frac, v), 4)
    return frac


def _flags(metas):
    """Responses (one read, or its parts) → {loss, smp, thr, frac}: any part flagged = the read is."""
    out = {"loss": False, "smp": False, "thr": False, "frac": None}
    for m in metas:
        loss, smp, thr = gu._meta_flags(m)
        out["loss"] |= loss
        out["smp"] |= smp
        out["thr"] |= thr
        f = _frac(m)
        if f is not None:
            out["frac"] = f if out["frac"] is None else min(out["frac"], f)
    return out


# ── the requests ─────────────────────────────────────────────────────────────────────────────────

def paid_expr():
    return {"filter": {"fieldName": PAID_DIM, "stringFilter": {"matchType": "FULL_REGEXP", "value": PAID_RULE}}}


def cty_expr(part):
    """A country part (codes, rest) → its filter: countryId in codes — and, for the last part (rest = every named
    code), every country NOT in rest too ("(not set)" and the countries without a slot)."""
    codes, rest = part
    if rest is None:
        return ga4._in_list("countryId", codes)
    other = {"notExpression": ga4._in_list("countryId", rest)}
    if not codes:
        return other
    return {"orGroup": {"expressions": [ga4._in_list("countryId", codes), other]}}


def split_parts(named, n):
    """The named slot countries (cset order: most installs first) → n parts, every n-th code in each (so the parts
    are alike in size); the last one also takes every country outside the list. Empty parts but the last are left
    out."""
    named = list(named)
    groups = [named[i::n] for i in range(n)]
    out = [(g, None) for g in groups[:-1] if g]
    out.append((groups[-1], named))
    return out


def rep_qc(ga, d, no_total=False, part=None):
    """QC full, or one country part of it."""
    return gu.rep_iday_qc_full(ga, d, no_total, extra=[cty_expr(part)] if part else None)


def rep_paid(ga, d, no_total=False, part=None):
    """PAID: QC full of the users whose first visit came from a Google Ads campaign (or one country part of it)."""
    return gu.rep_iday_qc_full(ga, d, no_total, extra=[paid_expr()] + ([cty_expr(part)] if part else []))


def rep_au(ga, a, b, dim, mets):
    """AU: ad revenue / impressions / clicks of [a, b] by ad unit (or format) × install day × day."""
    return ga.report_all({"dateRanges": [gu._rng(a, b)], "dimensions": ga4._dim(dim, "firstSessionDate", "date"),
                          "metrics": ga4._dim(*mets), "currencyCode": "USD", "keepEmptyRows": False},
                         page_rows=gu.UNI_PAGE_ROWS)


def rep_rm(ga, a, b):
    """RM: app_remove users and events of [a, b] by day × country (the probe's T4 shape)."""
    return ga.report_all({"dateRanges": [gu._rng(a, b)], "dimensions": ga4._dim("date", "countryId"),
                          "metrics": ga4._dim("totalUsers", "eventCount"), "metricAggregations": ["TOTAL"],
                          "keepEmptyRows": False}, event="app_remove", page_rows=gu.UNI_PAGE_ROWS)


# ── parse, check ─────────────────────────────────────────────────────────────────────────────────

def qb_late(rows, d, hs):
    """Q-B rows of day d → the late tie's side: tL (ad revenue at install ages 91..427, every install day) and cL[lag
    91..427] (the same, install days ≥ hs: the gap's side)."""
    tl, cl = 0, [0] * (gu.QB_WIN - LATE_LO + 1)
    for r in rows or []:
        x = gu._x_date(str(r.get("firstSessionDate") or ""))
        if x is None or x > d:
            continue
        lag = (d - x).days
        if LATE_LO <= lag <= gu.QB_WIN:
            ad = gu._mic(r.get("totalAdRevenue"))
            tl += ad
            if x >= hs:
                cl[lag - LATE_LO] += ad
    return {"tL": tl, "cL": cl}


def qcx_parse(rows, d, hs, cells):
    """A full Q-C read of day d (whole, or its parts' rows together; PAID alike) → rows, oth ("(other)" in either
    dimension: never placed), T {country: ad revenue per LBANDS} and n0 {country: lag-0 new users} (every install day,
    ages 0..427: the paid read's tie), and per `cells`:
      "c2": rev (Σ named ad revenue at ages 91..427, every install day: the late tie's side), nr [lag 91..427] (install
            days ≥ hs: the gap's side), agg {(country, week): {r2, u2}} (install days ≥ hs)
      "cp": agg {(country, week): {n, r, u}} (install days ≥ hs, ages 0..427)
    Install ages past 427 (users Q-B never sees) are left out."""
    c = {"rows": len(rows), "oth": False, "T": {}, "n0": {}, "agg": {}, "rev": 0, "nr": [0] * (gu.QB_WIN - LATE_LO + 1)}
    xs, slots = {}, {}
    late = cells == "c2"
    nb = len(LBANDS)
    for r in rows:
        cc, f = str(r.get("countryId") or ""), str(r.get("firstSessionDate") or "")
        if cc == "(other)" or f == "(other)":
            c["oth"] = True
            continue
        xl = xs.get(f)
        if xl is None:
            x = gu._x_date(f)
            xl = xs[f] = (None, None, None) if x is None or x > d or (d - x).days > gu.QB_WIN else (
                x, (d - x).days, gu.iday_week(x))
        x, lag, week = xl
        if x is None:
            continue
        slot = slots.get(cc)
        if slot is None:
            slot = slots[cc] = gu._slot_cc(cc)
        act, new, ad = gu._int(r.get("activeUsers")), gu._int(r.get("newUsers")), gu._mic(r.get("totalAdRevenue"))
        t = c["T"].get(slot)
        if t is None:
            t = c["T"][slot] = [0] * nb
        t[LB_IX[lag]] += ad
        if lag == 0:
            c["n0"][slot] = c["n0"].get(slot, 0) + new
        if late:
            if lag < LATE_LO:
                continue
            c["rev"] += ad
            if x < hs:
                continue
            c["nr"][lag - LATE_LO] += ad
            a = c["agg"].get((slot, week))
            if a is None:
                a = c["agg"][(slot, week)] = {"r2": [0] * len(C2BANDS), "u2": [0] * len(C2LAGS)}
            a["r2"][C2B_IX[lag]] += ad
            i = C2L_IX.get(lag)
            if i is not None:
                a["u2"][i] += act
        else:
            if x < hs:
                continue
            a = c["agg"].get((slot, week))
            if a is None:
                a = c["agg"][(slot, week)] = {"n": 0, "r": [0] * nb, "u": [0] * len(LLAGS)}
            if lag == 0:
                a["n"] += new
            a["r"][LB_IX[lag]] += ad
            i = LL_IX.get(lag)
            if i is not None:
                a["u"][i] += act
    return c


def _status(loss, oth, smp, inside, tries):
    if loss or oth:
        return "gap"
    if smp:
        return "smp" if inside else "gap"
    if inside:
        return "ok"
    return "gap" if tries >= gu.IDAY_TRIES else "retry"


def check_c2(c, fl, tl, tries):
    """The late ages tied to the same day's Q-B (tL): Σ named countries' ad revenue at ages 91..427 within GAP_MAX (or
    $0.001) → (c2st, ledger fields)."""
    inside = gu._tie_inside(c["rev"], tl, gu.GAP_MAX, gu.TIE_ABS_MICROS)
    st = _status(fl["loss"], c["oth"], fl["smp"], inside, tries)
    return st, {"c2loss": fl["loss"], "c2oth": c["oth"], "c2smp": fl["smp"], "c2frac": fl["frac"],
                "tie_late": round(c["rev"] / tl, 4) if tl else None}


def check_cp(p, fl, t, tries):
    """The paid read tied back to the full read of the same day (t): paid users are a part of all users, so per country
    and band the paid revenue may not exceed the full read's (Σ excess within GAP_MAX of the paid revenue, or $0.001)
    nor the paid lag-0 new users the full read's (TIE_NEW, or 1) → (cpst, ledger fields: cpshare = paid ÷ all ad
    revenue, ages 0..427; cpn = paid ÷ all lag-0 new users; cpx = the excess ÷ the paid revenue)."""
    nb = len(LBANDS)
    over = tp = tt = 0
    for cc, pv in p["T"].items():
        tv = t["T"].get(cc) or [0] * nb
        for a, b in zip(pv, tv):
            tp += a
            if a > b:
                over += a - b
    for tv in t["T"].values():
        tt += sum(tv)
    pn, tn = sum(p["n0"].values()), sum(t["n0"].values())
    inside = (over <= max(gu.GAP_MAX * tp, gu.TIE_ABS_MICROS)
              and pn <= tn + max(gu.TIE_NEW * tn, gu.TIE_ABS_USERS))
    st = _status(fl["loss"], p["oth"], fl["smp"], inside, tries)
    return st, {"cploss": fl["loss"], "cpoth": p["oth"], "cpsmp": fl["smp"], "cpfrac": fl["frac"],
                "cpshare": round(tp / tt, 4) if tt else None, "cpn": round(pn / tn, 4) if tn else None,
                "cpx": round(over / tp, 4) if tp else None}


def au_parse(rows, dim, hs):
    """AU rows → {day: {"rev": Σ named ad revenue at ages 0..427 (every install day: the tie's side), "oth": an
    "(other)" row, "agg": {(unit, week): {r, i, k}} (install days ≥ hs)}} and the units' revenue (their order)."""
    out, units = {}, {}
    nb = len(LBANDS)
    for r in rows:
        u, f = str(r.get(dim) or "").strip(), str(r.get("firstSessionDate") or "")
        day = ga4._d(r.get("date"))
        if day is None:
            continue
        e = out.get(day)
        if e is None:
            e = out[day] = {"rev": 0, "oth": False, "agg": {}}
        if u == "(other)" or f == "(other)":
            e["oth"] = True
            continue
        x = gu._x_date(f)
        if x is None or x > day or (day - x).days > gu.QB_WIN:
            continue
        lag = (day - x).days
        unit = "--" if u in ("", "(not set)") else u
        ad, imp, clk = gu._mic(r.get("totalAdRevenue")), gu._int(r.get("publisherAdImpressions")), \
            gu._int(r.get("publisherAdClicks"))
        e["rev"] += ad
        units[unit] = units.get(unit, 0) + ad
        if x < hs:
            continue
        key = (unit, gu.iday_week(x))
        a = e["agg"].get(key)
        if a is None:
            a = e["agg"][key] = {"r": [0] * nb, "i": [0] * nb, "k": [0] * nb}
        b = LB_IX[lag]
        a["r"][b] += ad
        a["i"][b] += imp
        a["k"][b] += clk
    return out, units


def rm_parse(rows):
    """RM rows → {day: {"s": {country: [users, events]}, "o": [users, events] of "(other)", "ev": Σ events, "us": Σ
    users}} ("(not set)" → "--")."""
    out = {}
    for r in rows:
        day = ga4._d(r.get("date"))
        if day is None:
            continue
        e = out.get(day)
        if e is None:
            e = out[day] = {"s": {}, "o": [0, 0], "ev": 0, "us": 0}
        cc = str(r.get("countryId") or "")
        u, n = gu._int(r.get("totalUsers")), gu._int(r.get("eventCount"))
        e["ev"] += n
        e["us"] += u
        if cc == "(other)":
            e["o"] = [e["o"][0] + u, e["o"][1] + n]
            continue
        s = gu._slot_cc(cc)
        v = e["s"].get(s) or [0, 0]
        e["s"][s] = [v[0] + u, v[1] + n]
    return out


def chunks(keys, size):
    """Sorted ISO days → runs of consecutive days cut into ≤ size, NEWEST first (each run oldest → newest)."""
    runs = []
    for k in keys:
        if runs and (_d(k) - _d(runs[-1][-1])).days == 1 and len(runs[-1]) < size:
            runs[-1].append(k)
        else:
            runs.append([k])
    return sorted(runs, key=lambda r: r[-1], reverse=True)


def _add_cells(dst, key, a):
    p = dst.get(key)
    if p is None:
        dst[key] = copy.deepcopy(a)
        return
    for f, v in a.items():
        p[f] = p[f] + v if isinstance(v, int) else [x + y for x, y in zip(p[f], v)]


def _zero(e):
    return not any((v if isinstance(v, int) else any(v)) for v in e.values())


# ── the run ──────────────────────────────────────────────────────────────────────────────────────

class Ext:
    """One app-fetch's extension reads, bound to its _Iday `run` (ga, the data, the call cap and stops, the counts)."""

    def __init__(self, run):
        self.run = run
        ida = run.ida
        for k in gu.X_KEYS:
            if not isinstance(ida.get(k), dict):
                ida[k] = {}
        self.snap = copy.deepcopy({k: ida[k] for k in gu.X_KEYS})     # a failure puts these back
        xs = ida["xs"]
        xs.setdefault("split", {"lv": 0, "no": None, "at": None})
        xs.setdefault("au", {"dim": None, "mets": None, "blk": AU_DAYS, "units": [], "off": None})
        xs.setdefault("paid", {"off": None})
        xs.setdefault("rm", {"off": None})
        self.cset0 = len(ida["cset"])                   # the slots at the fetch's start (xs.since: the ones added now)
        self.lo = max(run.hs, run.cty_lo)               # the country horizon: what the re-read covers
        xs["lo"] = _iso(self.lo)
        self.mem = {}                                   # day → this fetch's full read (its late side, T, flags)
        self.pc2, self.pcp, self.pdays = {}, {}, set()  # (country, week) → cells until the slots are known
        self.st = dict.fromkeys(X_COUNTS, 0)
        run.stats["x"] = self.st

    # plumbing

    def hook(self, name, *args):
        """One step, failure-isolated: a bug puts the extension's keys back as they were at the fetch's start and the
        fetch goes on without it (counted: errors)."""
        try:
            getattr(self, name)(*args)
        except Exception:
            for k, v in self.snap.items():
                self.run.ida[k] = v
            self.st["errors"] += 1
            self.st["left"] = 0
            self.run.x = None

    def _stop(self, why):
        """The extension's first stop → its own counts (why; qstops once for a quota / hourly stop)."""
        if self.st.get("why") is None:
            self.st["why"] = why
            self.st["qstops"] += why in ("quota", "hour")

    def can(self, need=1, back=False, reserve="x"):
        """run.can for the extension's reads — the same cap, stops, budgets and hourly floor — with ITS stop kept in its
        own counts: the legacy stats (why, qstop: the legacy log line and state) stay what the legacy reads made
        them."""
        run = self.run
        why, qstop = run.stats["why"], run.stats["qstop"]
        run.stats["why"] = None
        ok = run.can(need, back=back, reserve=reserve)
        if not ok:
            self._stop(run.stats["why"] or "halt")
        run.stats["why"], run.stats["qstop"] = why, qstop
        return ok

    def ask(self, fn, *args, total=False, **kw):
        """One read → (rows, metadata, tokens) · "refused" (HTTP 400: an answer — GA4 doesn't accept this shape or
        filter; never counted as a failure) · None (failed: IDAY_ERR_STOP failures in a row, or a quota answer, stop
        every read left in the fetch — they all come after the legacy ones). total: the read asks totalRevenue unless
        the property refuses it (flags.no_total — never set from here)."""
        run = self.run
        q0, c0 = run.ga.quota, getattr(run.ga, "calls", None)
        try:
            if total:
                kw["no_total"] = bool(run.ida["flags"].get("no_total"))
            rows = fn(run.ga, *args, **kw)
            meta = dict(run.ga.last_meta or {})
            if meta.get("currencyCode") not in (None, "", "USD"):
                raise ValueError("currency")
        except Exception as e:
            run._count(q0, c0, x=True)
            if gu._fail_kind(e) == "quota":
                run.halt = True
                self._stop("quota")
                return None
            if str(e).startswith("HTTP 400"):
                return "refused"
            run.errs += 1
            if run.errs >= gu.IDAY_ERR_STOP:
                run.halt = True
                self._stop("errors")
            return None
        tok = run._count(q0, c0, x=True)
        run.errs = 0
        return rows, meta, tok

    def _pending(self, r2, kind):
        """Is day's c2 / cp / au still to do (and not tried yet today)?"""
        st = r2.get(kind + "st")
        if st in FOLDED:
            return False
        return r2.get(kind + "at") != self.run.at

    def _paid_ok(self):
        off = self.run.ida["xs"]["paid"].get("off")
        return not off or gu._age_days(off, self.run.at) >= PAID_RETRY_DAYS

    def _rm_ok(self):
        off = self.run.ida["xs"]["rm"].get("off")
        return not off or gu._age_days(off, self.run.at) >= RM_RETRY_DAYS

    def _rm_pending(self, k):
        """Is day k's app_remove by country still to read (never read, or failed on an earlier day)?"""
        r = self.run.ida["rm"].get(k)
        return r is None or (r.get("st") == "err" and r.get("at") != self.run.at)

    def _foldable(self):
        """Country cells can get their slots this fetch (cset known, or the legacy reads of this fetch make it)."""
        return bool(self.run.ida["cset"] or self.run.day_inst)

    def _eligible(self, k):
        r = self.run.days.get(k) or {}
        return r.get("st") in gu.QB_FOLDED and self.lo <= _d(k) <= self.run.F

    def _named(self):
        return [cc for cc in self.run.ida["cset"] if cc not in ("--", "ZZ")]

    def _split_ok(self):
        sp = self.run.ida["xs"]["split"]
        if len(self._named()) < 2:
            return False
        return bool(sp.get("lv")) or not sp.get("no") or gu._age_days(sp["no"], self.run.at) >= SPLIT_RETRY_DAYS

    # the full read of a day → its context

    def _ctx(self, d, rows, metas, tok, ql, parts=None):
        c = qcx_parse(rows, d, self.run.hs, "c2")
        return {"c": c, "fl": _flags(metas), "tok": tok, "ql": ql, "parts": parts, "split": False}

    def on_qc(self, d, rows, meta, tok, qb_rows):
        """A legacy Q-C read (the full one): its late ages judged and folded now, tied to the same fetch's Q-B."""
        k = _iso(d)
        if qb_rows is None or not self._eligible(k):
            return
        ctx = self._ctx(d, rows, [meta], tok, qb_late(qb_rows, d, self.run.hs))
        self.mem[k] = ctx
        r2 = self.run.ida["d2"].setdefault(k, {})
        if self._pending(r2, "c2") and self._foldable():
            self._c2(d, ctx)

    def _c2(self, d, ctx):
        """Judge + fold the late ages of `ctx` (unless it is sampled and a split is to be tried first: left pending)."""
        if ctx["fl"]["smp"] and ctx["parts"] is None and self._split_ok():
            ctx["split"] = True
            return
        k = _iso(d)
        r2 = self.run.ida["d2"].setdefault(k, {})
        tries = gu._int(r2.get("c2tries")) + 1
        st, f = check_c2(ctx["c"], ctx["fl"], ctx["ql"]["tL"], tries)
        r2.update(f, c2st=st, c2tries=tries, c2at=self.run.at, c2rows=ctx["c"]["rows"], c2tok=ctx["tok"],
                  c2parts=len(ctx["parts"] or [None]))
        self.st["late"] += 1
        self.st["late_" + ("ok" if st == "ok" else "smp" if st == "smp" else "gap" if st == "gap" else "retry")] += 1
        agg, ctx["c"]["agg"] = ctx["c"]["agg"], {}         # (the paid read needs only T / n0 of it)
        if st not in FOLDED:
            return
        self._fold_c2_gap(d, ctx)
        for key, a in agg.items():
            _add_cells(self.pc2, key, a)
        self.pdays.add(("c2", k))

    def _fold_c2_gap(self, d, ctx):
        """Per install day ≥ hs at ages 91..427: the same day's Q-B − Σ named countries → c2[W]["gap"].r2 (signed)."""
        c2, cl, nr, hs = self.run.ida["c2"], ctx["ql"]["cL"], ctx["c"]["nr"], self.run.hs
        touched = set()
        for i in range(len(cl)):
            lag = LATE_LO + i
            x = d - timedelta(days=lag)
            if x < hs:
                break
            g = cl[i] - nr[i]
            if not g:
                continue
            w = gu.iday_week(x)
            e = c2.setdefault(w, {}).setdefault("gap", {"r2": [0] * len(C2BANDS)})
            e["r2"][C2B_IX[lag]] += g
            touched.add(w)
        for w in touched:
            if not any(c2[w]["gap"]["r2"]):
                del c2[w]["gap"]
            if not c2[w]:
                del c2[w]

    # one day: c2 (+ a fresh pair when nothing of this fetch) and cp

    def day(self, k, back):
        """The day's late ages and paid read, whichever is still to do. → False: the budget stopped it (the caller
        stops too)."""
        run, d = self.run, _d(k)
        if not self._eligible(k):
            return True
        r2 = run.ida["d2"].setdefault(k, {})
        c2p = self._pending(r2, "c2")
        cpp = self._pending(r2, "cp") and self._paid_ok()
        if not (c2p or cpp):
            return True
        if not self._foldable():
            return True
        if (run.days.get(k) or {}).get("st") == "empty":   # nothing GA4 could give: done without a call
            for kind in ("c2", "cp") if cpp else ("c2",):
                if self._pending(r2, kind):
                    r2.update({kind + "st": "ok", kind + "tries": 0, kind + "at": run.at})
            return True
        ctx = self.mem.get(k)
        if ctx is None:                                 # a fresh full read (+ a fresh Q-B: the late ages' tie — not
            if not self.can(1 + c2p + cpp, back=back, reserve="x"):     # needed for the paid read alone)
                return False
            ql = None
            if c2p:
                res = self.ask(gu.rep_iday_qb, d, total=True)
                if not isinstance(res, tuple):
                    self._err(r2, c2p, cpp)
                    return True
                ql = qb_late(res[0], d, run.hs)
            res = self.ask(rep_qc, d, total=True)
            if not isinstance(res, tuple):
                self._err(r2, c2p, cpp)
                return True
            ctx = self.mem[k] = self._ctx(d, res[0], [res[1]], res[2], ql)
            if c2p:
                self._c2(d, ctx)
        elif c2p and not ctx["split"]:
            self._c2(d, ctx)
        if ctx["split"]:
            got = self._split(d, ctx, back, cpp) if self._split_ok() else None
            if got == "wait":
                return False
            if got == "err":
                self._err(r2, self._pending(r2, "c2"), cpp)
                return True
            ctx["split"] = False
            if got is not None:
                ctx = self.mem[k] = got
            if self._pending(r2, "c2"):
                self._c2(d, ctx)
        if cpp:
            if not self.can(len(ctx["parts"] or [None]), back=back, reserve="x"):
                return False
            self._cp(d, ctx)
        return True

    def _err(self, r2, c2p, cpp):
        if c2p:
            r2.update(c2st="err", c2at=self.run.at)
        if cpp:
            r2.update(cpst="err", cpat=self.run.at)

    def _split(self, d, ctx, back, cpp):
        """A sampled whole read → its country parts, halves then quarters, until the parts come back UNSAMPLED (module
        docstring: SAMPLING). The level that worked is kept (xs.split.lv) and the smallest one looked for again every
        SPLIT_RETRY_DAYS; parts that sample as much as the whole stop the search (a deeper split won't help). → the
        parts' context · None (no split read unsampled: the whole read stays, flagged; not tried again for
        SPLIT_RETRY_DAYS) · "wait" (budget) · "err"."""
        sp = self.run.ida["xs"]["split"]
        named, at = self._named(), self.run.at
        old = int(sp.get("lv") or 0)
        fresh = not old or gu._age_days(sp.get("at"), at) >= SPLIT_RETRY_DAYS
        lv, ref = (1 if fresh else old), ctx["fl"]["frac"]
        while lv <= SPLIT_MAX:
            parts = split_parts(named, 2 ** lv)
            if not self.can(len(parts) * (1 + cpp), back=back, reserve="x"):
                return "wait"
            rows, metas, tok = [], [], 0
            for p in parts:
                res = self.ask(rep_qc, d, total=True, part=p)
                if not isinstance(res, tuple):
                    return "err"
                rows.extend(res[0])
                metas.append(res[1])
                tok += res[2]
            self.st["split"] += 1
            pc = self._ctx(d, rows, metas, tok, ctx["ql"], parts)
            if not pc["fl"]["smp"]:
                if fresh or lv != old:
                    sp.update(lv=lv, at=at)
                sp["no"] = None
                return pc
            got = pc["fl"]["frac"]
            if ref is None or got is None or got <= ref * (1 + SPLIT_GAIN):
                break                                   # the parts sample as much as the whole: no deeper split helps
            ref, lv = got, lv + 1
        sp.update(lv=0, no=at, at=at)
        return None

    def _cp(self, d, ctx):
        """The paid read (whole, or the same country parts as the full read), tied back to it, folded."""
        k = _iso(d)
        r2 = self.run.ida["d2"].setdefault(k, {})
        rows, metas, tok = [], [], 0
        for p in ctx["parts"] or [None]:
            res = self.ask(rep_paid, d, total=True, part=p)
            if res == "refused":
                self.run.ida["xs"]["paid"]["off"] = self.run.at
                r2.update(cpst="refused", cpat=self.run.at)
                return
            if res is None:
                r2.update(cpst="err", cpat=self.run.at)
                return
            rows.extend(res[0])
            metas.append(res[1])
            tok += res[2]
        self.run.ida["xs"]["paid"]["off"] = None
        p = qcx_parse(rows, d, self.run.hs, "cp")
        tries = gu._int(r2.get("cptries")) + 1
        st, f = check_cp(p, _flags(metas), ctx["c"], tries)
        r2.update(f, cpst=st, cptries=tries, cpat=self.run.at, cprows=p["rows"], cptok=tok,
                  cpparts=len(ctx["parts"] or [None]))
        self.st["paid"] += 1
        self.st["paid_smp"] += st == "smp"
        self.st["paid_gap"] += st == "gap"
        if st not in FOLDED:
            return
        for key, a in p["agg"].items():
            _add_cells(self.pcp, key, a)
        self.pdays.add(("cp", k))

    # the steps

    def new(self):
        """The days step 1 read this fetch: their paid read (and a split one when their read was sampled)."""
        for k in sorted(self.run.new_keys, reverse=True):
            if self.run.halt or not self.day(k, back=False):
                break
            self.mem.pop(k, None)                       # (its parse is not needed again)

    def reread(self):
        """The history re-read: every day of the country horizon whose late ages or paid read are still to do, newest
        first, on the backfill's budget rules."""
        run = self.run
        for k in sorted((k for k in run.days if self._eligible(k)), reverse=True):
            if run.halt:
                break
            if not self.day(k, back=True):
                break
            self.mem.pop(k, None)
        self.mem = {}

    def _au_todo(self):
        """The AU blocks a fetch now reads: days of the horizon without their ad units (or failed on an earlier day),
        ≤ blk consecutive days a block, newest first; a block short of blk days waits while its newest day is under
        AU_DAYS old (it fills up). [] while every shape was refused (AU_RETRY_DAYS)."""
        run, xa = self.run, self.run.ida["xs"]["au"]
        if xa.get("off") and gu._age_days(xa["off"], run.at) < AU_RETRY_DAYS:
            return []
        blk = max(1, int(xa.get("blk") or AU_DAYS))
        d2 = run.ida["d2"]
        pend = sorted(k for k in run.days if self._eligible(k) and self._pending(d2.get(k) or {}, "au"))
        return [ch for ch in chunks(pend, blk) if len(ch) >= blk or _d(ch[-1]) <= run.F - timedelta(days=AU_DAYS)]

    def _rm_todo(self):
        """The RM blocks a fetch now reads: store days of the horizon up to F − RM_LATE (app_remove keeps coming in for
        about a week) without their app_remove by country, ≤ RM_DAYS a block, newest first; a block short of RM_MIN days
        waits while its newest day is under RM_MIN days past that edge. [] without slots or while GA4 refused the read
        (RM_RETRY_DAYS)."""
        run = self.run
        if not run.ida["cset"] or not self._rm_ok():
            return []
        hi = run.F - timedelta(days=RM_LATE)
        pend = sorted(k for k in run.daily if self.lo <= _d(k) <= hi and self._rm_pending(k))
        return [ch for ch in chunks(pend, RM_DAYS) if len(ch) >= RM_MIN or _d(ch[-1]) <= hi - timedelta(days=RM_MIN)]

    def units(self):
        """The AU blocks (_au_todo), the newest first: the first one on the fetch's own budget, the rest on the
        backfill's (plain budget, hourly floor)."""
        run, xa, d2 = self.run, self.run.ida["xs"]["au"], self.run.ida["d2"]
        first = True
        for ch in self._au_todo():
            if not self.can(1, back=not first, reserve=False):
                break
            first = False
            got = self._au_read(_d(ch[0]), _d(ch[-1]))
            if got == "off":
                return
            if got is None:
                for k in ch:
                    d2.setdefault(k, {}).update(aust="err", auat=run.at)
                if run.halt:
                    return
                continue
            rows, meta, tok, dim = got
            fl = _flags([meta])
            by, rev = au_parse(rows, dim, run.hs)
            if len(ch) > 1 and (fl["smp"] or fl["loss"] or any(e["oth"] for e in by.values())):
                xa["blk"] = max(1, len(ch) // 2)            # sampled / lossy over several days: shorter blocks
                return                                      # (7 → 3 → 1) from now on (these days: the next fetch)
            self._au_fold(ch, by, rev, fl)

    def _au_read(self, a, b):
        xa = self.run.ida["xs"]["au"]
        shapes = [(xa["dim"], tuple(xa["mets"]))] if xa.get("dim") and xa.get("mets") else list(AU_SHAPES)
        for dim, mets in shapes:
            res = self.ask(rep_au, a, b, dim, mets)
            if res == "refused":
                continue
            if res is None:
                return None
            xa.update(dim=dim, mets=list(mets), off=None)
            return res[0], res[1], res[2], dim
        if xa.get("dim"):                                   # the kept shape is refused now: all of them next time
            xa.update(dim=None, mets=None)
            return None
        xa["off"] = self.run.at
        return "off"

    def _au_fold(self, ch, by, rev, fl):
        """One AU block's parse (au_parse) → the ledger of its days (tied to the day's Q-B revenue, days[D].rb) and, for
        the folded ones, au[W][unit slot] (new units get a slot by revenue, ≤ AU_MAX, then "ZZ")."""
        run = self.run
        xa, au, d2 = run.ida["xs"]["au"], run.ida["au"], run.ida["d2"]
        units = xa.setdefault("units", [])
        for u in sorted(rev, key=lambda u: (-rev[u], u)):
            if u not in units:
                if len(units) < AU_MAX - 1:
                    units.append(u)
                elif "ZZ" not in units:
                    units.append("ZZ")
        ix = {u: str(i) for i, u in enumerate(units)}
        self.st["unit_blocks"] += 1
        for k in ch:
            day = _d(k)
            e = by.get(day) or {"rev": 0, "oth": False, "agg": {}}
            r2 = d2.setdefault(k, {})
            want = sum(gu._int(v) for v in ((run.days.get(k) or {}).get("rb") or []))
            inside = gu._tie_inside(e["rev"], want, gu.GAP_MAX, gu.TIE_ABS_MICROS)
            tries = gu._int(r2.get("autries")) + 1
            st = _status(fl["loss"], e["oth"], fl["smp"], inside, tries)
            r2.update(aust=st, autries=tries, auat=run.at, tie_au=round(e["rev"] / want, 4) if want else None,
                      auloss=fl["loss"], auoth=e["oth"], ausmp=fl["smp"], aufrac=fl["frac"], aublk=len(ch))
            self.st["unit_days"] += 1
            self.st["unit_gap"] += st == "gap"
            if st not in FOLDED:
                continue
            for (u, w), a in e["agg"].items():
                s = ix.get(u, ix.get("ZZ"))
                if s is None:
                    continue
                cell = au.setdefault(w, {}).get(s)
                if cell is None:
                    au[w][s] = copy.deepcopy(a)
                else:
                    for f in ("r", "i", "k"):
                        cell[f] = [x + y for x, y in zip(cell[f], a[f])]
        for w in list(au):
            for s in [s for s, c in au[w].items() if _zero(c)]:
                del au[w][s]
            if not au[w]:
                del au[w]

    def finish(self):
        """After the legacy finish (the slots are known): the RM blocks, then this fetch's country cells into slots,
        then what is left to do (iday_meta x2)."""
        run = self.run
        cset = run.ida["cset"]
        if not cset:                                        # no slots (yet): nothing of this fetch can be placed —
            if self.pdays:                                  # (never: _foldable) its data back as it was
                for k, v in self.snap.items():
                    run.ida[k] = v
        else:
            self._since()
            self._rm_blocks()
            self._fold(run.ida["c2"], self.pc2)
            self._fold(run.ida["cp"], self.pcp)
        self.st["left"] = self.left()

    def _since(self):
        """A slot the legacy finish added in this fetch (a country that grew): the days whose late ages, paid read or
        app_remove went in BEFORE it (into "ZZ") → xs.since[country] = {c2 / cp / rm: [[first, last], …]} — a cell
        needing one of those days holds that country only in part (the legacy cset_since, for the new keys)."""
        run = self.run
        cset, snap = run.ida["cset"], self.snap
        if not self.cset0 or len(cset) <= self.cset0:
            return
        before = {"c2": sorted(k for k, r in snap["d2"].items() if r.get("c2st") in FOLDED),
                  "cp": sorted(k for k, r in snap["d2"].items() if r.get("cpst") in FOLDED),
                  "rm": sorted(k for k, r in snap["rm"].items() if r.get("st") != "err")}
        got = {kind: gu._date_ranges(keys) for kind, keys in before.items() if keys}
        if got:
            since = run.ida["xs"].setdefault("since", {})
            for cc in cset[self.cset0:]:
                since[cc] = copy.deepcopy(got)

    def _slot(self, ix, cc):
        return ix.get(cc, ix.get("--") if cc == "--" else ix.get("ZZ"))

    def _fold(self, dst, pend):
        ix = {cc: str(i) for i, cc in enumerate(self.run.ida["cset"])}
        touched = set()
        for (cc, w), a in sorted(pend.items()):
            s = self._slot(ix, cc)
            if s is None:
                continue
            cell = dst.setdefault(w, {}).get(s)
            if cell is None:
                dst[w][s] = copy.deepcopy(a)
            else:
                for f, v in a.items():
                    cell[f] = cell[f] + v if isinstance(v, int) else [x + y for x, y in zip(cell[f], v)]
            touched.add((w, s))
        for w, s in touched:
            if _zero(dst[w][s]):
                del dst[w][s]
            if not dst[w]:
                del dst[w]

    def _rm_blocks(self):
        """The RM blocks (_rm_todo), the newest first — the first one on the fetch's own budget, the rest on the
        backfill's — each day tied to the store's app_remove events of the day (daily un_ev)."""
        run = self.run
        rm, xr = run.ida["rm"], run.ida["xs"]["rm"]
        ix = {cc: str(i) for i, cc in enumerate(run.ida["cset"])}
        first = True
        for ch in self._rm_todo():
            if not self.can(1, back=not first, reserve=False):
                break
            first = False
            res = self.ask(rep_rm, _d(ch[0]), _d(ch[-1]))
            if res == "refused":                            # GA4 doesn't take the read here: asked again in 4 weeks
                xr["off"] = run.at
                return
            if res is None:
                for k in ch:
                    rm[k] = {"st": "err", "at": run.at}
                if run.halt:
                    return
                continue
            xr["off"] = None
            fl = _flags([res[1]])
            by = rm_parse(res[0])
            self.st["rm_blocks"] += 1
            for k in ch:
                e = by.get(_d(k)) or {"s": {}, "o": [0, 0], "ev": 0, "us": 0}
                s = {}
                for cc, v in e["s"].items():
                    sl = self._slot(ix, cc)
                    if sl is not None:
                        p = s.get(sl) or [0, 0]
                        s[sl] = [p[0] + v[0], p[1] + v[1]]
                day = run.daily.get(k) or {}
                un_ev, un = day.get("un_ev"), day.get("un")
                tie = round(e["ev"] / un_ev, 4) if un_ev else None
                if fl["loss"] or e["o"][1]:
                    st = "gap"
                elif fl["smp"]:
                    st = "smp"
                elif un_ev is not None and not gu._tie_inside(e["ev"], gu._int(un_ev), RM_GAP, gu.TIE_ABS_USERS):
                    st = "q"
                else:
                    st = "ok"
                rm[k] = {"s": s, "o": e["o"], "st": st, "at": run.at, "ev": e["ev"], "tie": tie,
                         "tu": round(e["us"] / un, 4) if un else None}
                self.st["rm_days"] += 1

    def left(self):
        """Days the extension still has to do that a fetch now would read (the same rules as its steps: not the
        newest AU / RM blocks still filling, not a day already asked today, nothing GA4 refused): 0 = its re-read is
        whole (iday_meta x2.done — no more install-value-only fetches for it)."""
        run, d2 = self.run, self.run.ida["d2"]
        paid = self._paid_ok()
        todo = {k for ch in self._au_todo() for k in ch}
        for k in run.days:
            if self._eligible(k):
                r2 = d2.get(k) or {}
                if self._pending(r2, "c2") or (paid and self._pending(r2, "cp")):
                    todo.add(k)
        return len(todo) + sum(len(ch) for ch in self._rm_todo())


# ── the files: iday/<key>.x.json.gz (+ .x.old.json.gz: frozen parts) ───────────────────────────────

def x_path(data_dir, app_id, old=False):
    return os.path.join(data_dir, gu.DIR, gu.IDAY_DIR, gu.file_key(app_id) + (".x.old" if old else ".x") + ".json.gz")


def _empty():
    return {k: {} for k in gu.X_KEYS}


def load_ext(data_dir, app_id, src, v):
    """The extension's keys of an app's iday data (hot + .old) — all {} when there are none, or when a part is
    unreadable / of another stream or format (its re-read then starts over; the legacy data is never affected)."""
    try:
        hot = gu.load_store(x_path(data_dir, app_id))
        if not isinstance(hot, dict) or hot.get("xv") != X_V or hot.get("src") != src or hot.get("v") != v:
            return _empty()
        out = {k: dict(hot.get(k) or {}) for k in gu.X_KEYS}
        op = x_path(data_dir, app_id, old=True)
        if os.path.exists(op):
            old = gu.load_store(op)
            if not isinstance(old, dict) or old.get("xv") != X_V or old.get("src") != src or old.get("v") != v:
                return _empty()
            for k in ("c2", "cp", "au", "d2", "rm"):
                for kk, vv in (old.get(k) or {}).items():
                    out[k].setdefault(kk, vv)
        return out
    except Exception:
        return _empty()


def x_split(ida):
    """→ (hot, old). .old holds what no later fetch can change: d2 / rm days before the first of the month of the
    last fetch's horizon start (xs.lo), and the c2 / cp / au install weeks that end ≥ 427 days before that (no day
    of the horizon reaches them) — whole months, so it is rewritten about once a month."""
    hot = {"xv": X_V, "src": ida.get("src"), "v": ida.get("v"), "xs": ida.get("xs") or {}}
    old = {"xv": X_V, "src": ida.get("src"), "v": ida.get("v")}
    lo = _d((ida.get("xs") or {}).get("lo"))
    for k in ("c2", "cp", "au", "d2", "rm"):
        part = ida.get(k) or {}
        if lo is None:
            hot[k] = part
            old[k] = {}
            continue
        cut = lo.replace(day=1)
        if k in ("d2", "rm"):
            c = cut.isoformat()
        else:                                             # a week W ends before cut − 427 ⇔ W < cut − 433
            c = (cut - timedelta(days=gu.QB_WIN + 6)).isoformat()
        hot[k] = {kk: vv for kk, vv in part.items() if kk >= c}
        old[k] = {kk: vv for kk, vv in part.items() if kk < c}
    return hot, old


def save_ext(data_dir, app_id, ida):
    """Both extension files (deterministic, written only on change); none while the extension has no data (and the
    old ones removed: they belong to a history that started over). → True when anything was written or removed."""
    hp, op = x_path(data_dir, app_id), x_path(data_dir, app_id, old=True)
    if not any(ida.get(k) for k in gu.X_KEYS if k != "xs"):
        gone = False
        for p in (hp, op):
            if os.path.exists(p):
                os.remove(p)
                gone = True
        return gone
    hot, old = x_split(ida)
    wrote = False
    if any(old[k] for k in ("c2", "cp", "au", "d2", "rm")):
        wrote = write_json_gz_stable(op, old)
    elif os.path.exists(op):
        os.remove(op)
        wrote = True
    return write_json_gz_stable(hp, hot) or wrote


def iday_x_log_line(status):
    """The extension's ONE public counts-only line (refresh_all's status["iday_x"], with GA4_IDAY + IDAY_EXT) — or
    None."""
    c = (status or {}).get("iday_x")
    if not isinstance(c, dict):
        return None
    v = tuple(int(c.get(k) or 0) for k in X_COUNTS)
    return ("ga4 iday ext: apps %d, late-age days %d (tied %d, sampled %d, unassigned %d, retry %d), split reads %d, "
            "paid days %d (sampled %d, unassigned %d), ad-unit days %d in %d blocks (unassigned %d), country "
            "uninstall days %d in %d blocks, days left %d, quota stops %d, errors %d" % v)
