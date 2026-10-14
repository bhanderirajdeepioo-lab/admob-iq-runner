"""One-off GA4 COUNTRY capability probe, run by .github/workflows/ga4-country-probe.yml: before the forecast's country
model reads country cells past age 90, splits paid from organic installs, adds whole-app country totals and country-wise
uninstalls, measure per GA4 app what GA4 gives for each read — accepted or the HTTP class, rows, pages, quota tokens,
seconds, "(other)" loss / sampling / thresholding — and whether the pieces TIE to the reads the build already trusts
(Q-B, Q-T: ga4_uninstall's install-value reads). Read-only against GA4 and against the PRIVATE data (the workflow's
read-only clone: the Uninstall state's routes and this probe's own last report).

T1  full Q-C — Q-C WITHOUT its install-day inList (countryId × firstSessionDate, every install age) on a few activity
    days D before and from PIVOT (2026-07-25: from that day GA4 kept the country rows whole; input "days", default 3+3),
    each with a same-day Q-B. Ties (Σ named countries ÷ Q-B ad revenue, within GAP_MAX or $0.001) per install-age band
    0-90, 91-180, 181-365, 366-427 (and 91-427), lag-0 new users (within TIE_NEW or 1 user); "(other)" share; how many
    of its rows the 91-day list would have kept (le90_rows).
T2  paid vs organic — DISC: one small read per first-user attribution dimension (CANDS, in order: Google Ads campaign
    id, campaign id, default channel group, source / medium) on the newest T1 day from the pivot: accepted?, how much of
    the day it tags as paid (CANDS' paid rule, the same rule as the filter); the first accepted one that tags paid users
    is picked (else the first accepted). Then, on T2_DAYS of the T1 days (input "t2_days"), the T1 Q-C read twice more
    with the picked dimension as a filter — ORG (not paid) and PAID (paid): ORG + PAID tied to T1's Q-C per band, per
    top country (TOP by revenue) and lag-0 new users; the organic share per band, the paid share of installs.
T3  whole-app country totals — CT: date × countryId over one T3_DAYS block (no install day; covers the T1 days, ends
    ≤ F) and QT (Q-T exactly) over the same block: CT tied to QT day by day (revenue, new users; active users are not
    additive across countries: ratio only). Per T1 day and country the revenue (and user) share of users OLDER than
    Q-B's 427-day window = (CT − Σ that day's full Q-C) ÷ CT — and per day 1 − Q-B ÷ Q-T.
T4  app_remove by date × countryId (eventName == app_remove; totalUsers, eventCount, TOTAL) over T4_DAYS: rows, flags,
    countries, Σ rows ÷ TOTAL.
T5  dimensions that would measure missing ROI drivers if GA4 accepts them: META (the Data API metadata: which of these
    dimensions the property has, how many custom ones, whether ad_format / ad_unit_name / ad_source are registered
    as event-scoped custom dimensions — counted, never listed), appVersion, deviceCategory, operatingSystemVersion,
    adFormat, adSourceName, adUnitName by date over T5_DAYS, and each registered ad_impression parameter by date
    (eventName == ad_impression): accepted / rejected + row counts only.

REQUEST SHAPES — every body this probe sends is built by request() below (Ga4App adds the Android + stream filter,
returnPropertyQuota, limit / offset paging at PAGE_ROWS and a total order; D = one activity day; [a, b] a date range;
IDAY_METS = activeUsers, newUsers, totalAdRevenue, totalRevenue; every money read in USD):
  QB     [D, D]  firstSessionDate              IDAY_METS, TOTAL   = ga4_uninstall.rep_iday_qb
  QC     [D, D]  countryId, firstSessionDate   IDAY_METS, TOTAL   = rep_iday_qc without its inList
  ORG    QC + NOT (paid rule of the picked dimension);  PAID  QC + (paid rule)
  DISC   [D, D]  <candidate>                   activeUsers, newUsers, totalAdRevenue
  CT     [a, b]  date, countryId               IDAY_METS          (a = b − T3_DAYS + 1)
  QT     [a, b]  date                          IDAY_METS          = ga4_uninstall.rep_iday_tot
  RM     [F − 29, F]  date, countryId          totalUsers, eventCount, TOTAL; eventName == app_remove
  DIM    [F − 29, F]  date, <dimension>        T5_DIMS' metrics
  CUSTOM [F − 29, F]  date, customEvent:<p>    eventCount, totalAdRevenue; eventName == ad_impression
  META   GET properties/<id>/metadata (no quota tokens)
A property that refuses totalRevenue (HTTP 400) is asked once more without it, and from then on (no_total) — never on
ORG / PAID, whose filter may be what GA4 refuses. F = E − LATE (E = today − 2, the property's timezone): final days.

RESUMABLE: each app's work is a list of units (meta, t3, t2disc, day:<D> (its QB + QC [+ ORG + PAID]), t4, t5:<kind>,
t5c:<param>); a unit is done once every read in it answered (an HTTP 4xx but 429 is an answer: refused). With resume
the last report's done units are kept and only the rest are asked — t3 is asked again whenever a day is (the old shares
need its cells in memory). Every app of the last report not probed now is carried over as it was.

LIMITS: the d1d7 probe's quota rule per PROPERTY (any token bucket under half, ≤ 4 server-error / ≤ 5 thresholded
requests left, a 429, 2 failed calls on 5xx), one request at a time per property (WORKERS properties in parallel), at
most APP_CALLS calls an app and MAX_CALLS a run (input "max_calls"), and no call is started after BUDGET_SEC — what
is measured is still written.

OUTPUT: ga4/country_probe.json in the PRIVATE repo (write_private; never data/ or site/): per app KEY (the Uninstall
file key — no package, property, stream or owner) its units with counts / ratios / flags / rows / tokens / seconds
only — never money or user numbers; country codes only as the keys of their ratios. PUBLIC LOG: progress counts (a
heartbeat at least every minute) and ONE counts-only line per test, + one for the run; no names, ids, dates, countries,
money or API error text (stderr is hidden by the workflow step). INPUTS come from the workflow's event file (never a
step's env).
"""

import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from admob_iq import ga4_probe
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_audience_probe as ap
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_shape_probe as sp
from admob_iq.fetch import ga4_uninstall as gu
from admob_iq.fetch.ga4_d1d7_probe import Stop
from admob_iq.fetch.ga4_diagnose import _private_json

PIVOT = date(2026, 7, 25)           # activity days from here: GA4 kept the country rows whole (event retention change)
DAYS_SPEC = "3+3"                   # T1 days: 3 before the pivot, 3 from it ("B+A", "B+A/step" or ISO days, comma list)
MAX_T1_DAYS = 14
T2_DAYS = 2                         # ORG + PAID on this many T1 days: the newest from the pivot, the newest before, …
T3_DAYS = 120                       # one CT / QT block (ga4_uninstall.IDAY_TOT_DAYS)
T4_DAYS = 30
T5_DAYS = 30
TOP = 10                            # countries compared one by one (T2 ties, T3 old shares)
LATE = gu.IDAY_LATE                 # F = E − 3: the newest final day
BANDS = (("0_90", 0, 90), ("91_180", 91, 180), ("181_365", 181, 365), ("366_427", 366, 427))
BAND_KEYS = tuple(b for b, _, _ in BANDS)
LATE_BANDS = BAND_KEYS[1:]
TIE_KEYS = BAND_KEYS + ("91_427",)
DISC_METS = ("activeUsers", "newUsers", "totalAdRevenue")
# first-user attribution candidates, in the order they are preferred: (dimension, paid rule kind, rule). The rule is
# GA4's filter AND the Python test of a value (case-insensitive, full match): a campaign id is paid when it is a real id
# (not "(not set)" / "(organic)" / … ), a channel group when it is one of GA4's paid groups, a source / medium when the
# medium matches GA4's own paid-medium pattern.
PAID_CHANNELS = ("Paid Search", "Paid Social", "Paid Shopping", "Paid Video", "Paid Other", "Display", "Cross-network",
                 "Audio")
CANDS = (("firstUserGoogleAdsCampaignId", "regex", r"[^(].*"),
         ("firstUserCampaignId", "regex", r"[^(].*"),
         ("firstUserDefaultChannelGroup", "list", PAID_CHANNELS),
         ("firstUserSourceMedium", "regex", r".* / (.*cp.*|ppc|retargeting|paid.*)"))
CAND_NAMES = tuple(c for c, _, _ in CANDS)
CAND_LABELS = ("Ads campaign id", "campaign id", "channel group", "source/medium")
USE_METS = ("activeUsers", "newUsers", "totalAdRevenue")
AD_METS = ("publisherAdImpressions", "totalAdRevenue")
T5_DIMS = (("VER", "appVersion", ("activeUsers", "totalAdRevenue")),
           ("DEVCAT", "deviceCategory", USE_METS),
           ("OSVER", "operatingSystemVersion", USE_METS),
           ("ADFMT", "adFormat", AD_METS),
           ("ADSRC", "adSourceName", AD_METS),
           ("ADUNIT", "adUnitName", AD_METS))
T5_LABELS = ("app version", "device category", "OS version", "ad format", "ad source", "ad unit")
AD_PARAMS = ("ad_format", "ad_unit_name", "ad_source")      # ad_impression parameters, if registered as custom dims
CUSTOM_METS = ("eventCount", "totalAdRevenue")
MAX_CALLS = 1500                    # calls a run at most (input "max_calls")
APP_CALLS = 60                      # calls an app at most in one run (~33 planned: room for pages and fallbacks)
WORKERS = 4                         # properties in parallel — one request at a time per property
BUDGET_SEC = 22 * 60                # no new call after 22 min (the job's timeout is 45: setup, clone ≤ 8, the write)
TICK_SEC = 20
PAGE_ROWS = 100000
DATA_DIR = "_private"
STATE_PATH = sp.STATE_PATH
OUT_PATH = "ga4/country_probe.json"
OUT_TOP = 20                        # days listed by date at most (T3's days outside the tie)


# ── run, app ────────────────────────────────────────────────────────────────────────────────────

class Run(pr.Run):
    """The probe's clock, time budget, run-wide call cap and counts-only heartbeat ("country progress")."""

    def __init__(self, budget=BUDGET_SEC, clock=time.monotonic, max_calls=MAX_CALLS):
        super().__init__(budget, clock)
        self.max_calls = max_calls

    def over(self):
        if self.clock() - self.t0 >= self.budget:
            return "budget"
        return "calls" if self.max_calls and self.calls >= self.max_calls else None

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
            self.say("country progress: calls %d, %ds" % (n, s))

    def tick(self):
        self.pulse(count=True)


def _acc0():
    return {"thresh": False, "loss": False, "sampled": False, "smp_frac": None, "cur": set()}


def _acc_add(acc, meta):
    """One page's response metadata into the read's flags (any page flagged = the read is flagged)."""
    m = meta or {}
    acc["thresh"] |= bool(m.get("subjectToThresholding"))
    acc["loss"] |= bool(m.get("dataLossFromOtherRow"))
    for s in m.get("samplingMetadatas") or []:
        acc["sampled"] = True
        try:
            v = int(s.get("samplesReadCount")) / int(s.get("samplingSpaceSize"))
        except (TypeError, ValueError, ZeroDivisionError, AttributeError):
            continue
        acc["smp_frac"] = round(v if acc["smp_frac"] is None else min(acc["smp_frac"], v), 4)
    if m.get("currencyCode"):
        acc["cur"].add(str(m["currencyCode"]))


def _flags(acc):
    return {"thresh": acc["thresh"], "loss": acc["loss"], "sampled": acc["sampled"], "smp_frac": acc["smp_frac"],
            "usd": (acc["cur"] == {"USD"}) if acc["cur"] else None}


class App(sp.App):
    """ga4_shape_probe.App (stream-pinned, paged, the property's quota / 5xx / budget stops, calls / tokens / seconds
    per kind) + this run's per-app call cap (a Stop for this app only), every page's flags, and the metadata GET."""

    def __init__(self, token, property_id, stream_id, run, prop=None, cap=APP_CALLS):
        super().__init__(token, property_id, stream_id, run, prop)
        self.cap, self.acc = cap, _acc0()

    def _gate(self):
        if self.cap and self.calls >= self.cap:
            raise Stop("app_cap")

    def _post(self, method, body):
        self._gate()
        j = super()._post(method, body)
        _acc_add(self.acc, j.get("metadata"))
        return j

    def metadata(self):
        """GET properties/<id>/metadata (the dimensions and metrics this property has; no quota tokens) under the same
        stops, counts and pause as a report."""
        self._gate()
        p = self.prop
        why = p["stop"] or self.run.over() or ("quota_low" if pr.quota_low(p["quota"]) else None)
        if why:
            p["stop"] = why
            raise Stop(why)
        k = self.by_kind.setdefault(self.kind, {"calls": 0, "tokens": 0})
        k["calls"] += 1
        self.run.tick()
        if self.calls:
            ga4._sleep(ga4.PAUSE)
        self.calls += 1
        t0 = time.perf_counter()
        try:
            return ga4._call("GET", META_URL % (ga4.DATA, self.property_id), self.token)
        except RuntimeError as e:
            s = str(e)
            if s.startswith("HTTP 5"):
                p["server_errors"] += 1
                if p["server_errors"] >= pr.MAX_5XX:
                    p["stop"] = "server_errors"
            elif s.startswith("HTTP 429"):
                p["stop"] = "quota_429"
            raise
        finally:
            dt = time.perf_counter() - t0
            self.sec += dt
            k["sec"] = round(k.get("sec", 0) + dt, 3)


# ── the request shapes (every body this probe sends) ────────────────────────────────────────────

META_URL = "%s/properties/%s/metadata"                     # META: a GET (App.metadata), no body, no quota tokens

def _rule(cand):
    for c, kind, rule in CANDS:
        if c == cand:
            return kind, rule
    raise KeyError(cand)


def paid_expr(cand):
    """The paid rule of a candidate as a GA4 filter expression."""
    kind, rule = _rule(cand)
    if kind == "list":
        return ga4._in_list(cand, rule)
    return {"filter": {"fieldName": cand, "stringFilter": {"matchType": "FULL_REGEXP", "value": rule}}}


def is_paid(cand, value):
    """The same rule in Python (GA4's string filters are case-insensitive unless asked otherwise)."""
    kind, rule = _rule(cand)
    v = str(value or "")
    if kind == "list":
        return v.lower() in {x.lower() for x in rule}
    return re.fullmatch(rule, v, re.I) is not None


def request(kind, d=None, a=None, b=None, cand=None, dim=None, mets=None):
    """kind → {"body": the Data API body, "event": an eventName the stream filter adds, "extra": filter expressions}."""
    if kind == "QB":
        return {"body": gu._iday_body(d, d, ("firstSessionDate",))}
    if kind == "QC":
        return {"body": gu._iday_body(d, d, ("countryId", "firstSessionDate"))}
    if kind in ("ORG", "PAID"):
        e = paid_expr(cand)
        return {"body": gu._iday_body(d, d, ("countryId", "firstSessionDate")),
                "extra": [e if kind == "PAID" else {"notExpression": e}]}
    if kind == "DISC":
        return {"body": {"dateRanges": [gu._rng(d, d)], "dimensions": ga4._dim(cand), "metrics": ga4._dim(*DISC_METS),
                         "currencyCode": "USD", "keepEmptyRows": False}}
    if kind == "CT":
        return {"body": gu._iday_body(a, b, ("date", "countryId"), total_row=False)}
    if kind == "QT":
        return {"body": gu._iday_body(a, b, ("date",), total_row=False)}
    if kind == "RM":
        return {"body": {"dateRanges": [gu._rng(a, b)], "dimensions": ga4._dim("date", "countryId"),
                         "metrics": ga4._dim("totalUsers", "eventCount"), "metricAggregations": ["TOTAL"],
                         "keepEmptyRows": False}, "event": "app_remove"}
    if kind == "DIM":
        return {"body": {"dateRanges": [gu._rng(a, b)], "dimensions": ga4._dim("date", dim), "metrics": ga4._dim(*mets),
                         "currencyCode": "USD", "keepEmptyRows": False}}
    if kind == "CUSTOM":
        return {"body": {"dateRanges": [gu._rng(a, b)], "dimensions": ga4._dim("date", dim),
                         "metrics": ga4._dim(*CUSTOM_METS), "currencyCode": "USD", "keepEmptyRows": False},
                "event": "ad_impression"}
    raise KeyError(kind)


def _no_total(body):
    return dict(body, metrics=[m for m in body["metrics"] if m["name"] != "totalRevenue"])


def ask(ga, req, fallback=True):
    """report_all of one request; totalRevenue dropped once this property refused it (ga.no_total), and a 400 on a read
    asking it → once more without (fallback=False: a read whose filter may be what GA4 refuses — no retry)."""
    body = req["body"]
    has = any(m["name"] == "totalRevenue" for m in body["metrics"])
    if has and ga.no_total:
        body, has = _no_total(body), False
    try:
        return ga.report_all(body, event=req.get("event"), extra=req.get("extra"), page_rows=PAGE_ROWS)
    except RuntimeError as e:
        if not (fallback and has and str(e).startswith("HTTP 400")):
            raise
    rows = ga.report_all(_no_total(body), event=req.get("event"), extra=req.get("extra"), page_rows=PAGE_ROWS)
    ga.no_total = True
    return rows


# ── reads, parses (→ record of counts / ratios / flags, in-memory index) ───────────────────────

_ratio = pr._ratio


def _read(ga, kind, fetch, parse):
    """fetch() → rows, parse(rows) → (record, index) → (record + flags / cost, index or None). A GA4 error → {"ok":
    False, "err": its class}; a Stop is passed on; a bug in parse costs that record only (the call is spent)."""
    ga.kind, ga.acc = kind, _acc0()
    t0, d0, s0, c0 = ga.tok, ga.tok_delta, ga.sec, ga.calls
    idx = None
    try:
        rows = fetch()
    except Stop:
        raise
    except Exception as e:
        rec = {"ok": False, "err": pr._err(e)}
    else:
        got = pr._safely(parse, rows, fallback={"rows": len(rows) if isinstance(rows, list) else None})
        rec, idx = got if isinstance(got, tuple) else (got, None)
        rec = dict(_flags(ga.acc), **rec)
        rec["ok"] = "err" not in rec
    rec.update(tok=ga.tok - t0, tok_delta=ga.tok_delta - d0, sec=round(ga.sec - s0, 2), calls=ga.calls - c0)
    return rec, idx


def _final(err):
    """An error that IS the answer (asking again would not change it): HTTP 4xx but 429 — refused, not allowed."""
    h = (err or {}).get("http")
    return isinstance(h, int) and 400 <= h < 500 and h != 429


def _done(rec):
    """A read that answered: read, or refused for good (_final)."""
    return isinstance(rec, dict) and not rec.get("stopped") and ("err" not in rec or _final(rec["err"]))


def _band(lag):
    for name, lo, hi in BANDS:
        if lo <= lag <= hi:
            return name
    return "gt427" if lag > BANDS[-1][2] else None


def _real_cc(c):
    return gu._slot_cc(c) != "--"


def _total_mic(ga, metric="totalAdRevenue"):
    v = pr._totals(ga).get(metric)
    return None if v is None else gu._mic(v)


def fsd_parse(rows, d, country=False):
    """A one-day split by firstSessionDate (QB; QC / ORG / PAID with countryId) → rev / act per install-age band
    (micros / users, named rows only: "(other)" in either dimension is kept apart, never placed), n0 (lag-0 new users),
    all (Σ every row's revenue), oth [rows, users, micros], unp (revenue of rows without a usable install day), win (the
    largest lag with users), le90 (rows of lags ≤ 90: what the 91-day list keeps), cty {country: [micros, users, lag-0
    new]}."""
    keys = BAND_KEYS + ("gt427",)
    p = {"rows": len(rows), "rev": dict.fromkeys(keys, 0), "act": dict.fromkeys(keys, 0), "n0": 0, "all": 0,
         "act_all": 0, "oth": [0, 0, 0], "unp": 0, "win": None, "le90": 0, "cty": {}}
    for r in rows:
        f = str(r.get("firstSessionDate") or "")
        c = str(r.get("countryId") or "") if country else ""
        act, new, ad = gu._int(r.get("activeUsers")), gu._int(r.get("newUsers")), gu._mic(r.get("totalAdRevenue"))
        p["all"] += ad
        p["act_all"] += act
        if f == "(other)" or c == "(other)":
            o = p["oth"]
            o[0], o[1], o[2] = o[0] + 1, o[1] + act, o[2] + ad
            continue
        e = None
        if country:
            e = p["cty"].setdefault(c, [0, 0, 0])
            e[0], e[1] = e[0] + ad, e[1] + act
        x = gu._x_date(f)
        if x is None or x > d:
            p["unp"] += ad
            continue
        lag = (d - x).days
        b = _band(lag)
        p["rev"][b] += ad
        p["act"][b] += act
        if lag == 0:
            p["n0"] += new
            if e is not None:
                e[2] += new
        if lag <= 90:
            p["le90"] += 1
        if act and (p["win"] is None or lag > p["win"]):
            p["win"] = lag
    return p


def fsd_rec(p, ga):
    tot = _total_mic(ga)
    out = {"rows": p["rows"], "pages": ga.last_pages, "win": p["win"], "oth_rows": p["oth"][0],
           "oth_rev": _ratio(p["oth"][2], p["all"]), "oth_act": _ratio(p["oth"][1], p["act_all"]),
           "unp_rev": _ratio(p["unp"], p["all"]), "total_r": _ratio(p["all"], tot),
           "gt427": bool(p["rev"]["gt427"] or p["act"]["gt427"])}
    if p["cty"]:
        out.update(countries=sum(1 for c in p["cty"] if _real_cc(c)), le90_rows=_ratio(p["le90"], p["rows"]))
    return out


def _bsum(p, b):
    return sum(p["rev"][k] for k in LATE_BANDS) if b == "91_427" else p["rev"][b]


def _tie(got, want, rel=gu.GAP_MAX, floor=gu.TIE_ABS_MICROS):
    return {"r": _ratio(got, want), "in": gu._tie_inside(got, want, rel, floor), "judged": max(got, want) > floor}


def tie_bands(got, want):
    """Revenue per band (and 91-427): got ÷ want, inside GAP_MAX (or $0.001); judged when a side is above $0.001."""
    return {b: _tie(_bsum(got, b), _bsum(want, b)) for b in TIE_KEYS}


def _n0_tie(got, want):
    return _tie(got, want, gu.TIE_NEW, gu.TIE_ABS_USERS)


def t1_tie(qc, qb):
    """T1: the full Q-C (named countries) vs the same day's Q-B, per band and lag-0 new users; Q-B's revenue share per
    band; active users per band (ratio only: travellers and HLL make countries non-additive)."""
    return {"rev": tie_bands(qc, qb), "n0": _n0_tie(qc["n0"], qb["n0"]),
            "act": {b: _ratio(qc["act"][b], qb["act"][b]) for b in BAND_KEYS},
            "share": {b: _ratio(_bsum(qb, b), qb["all"]) for b in TIE_KEYS}}


def _add(a, b):
    """Two fsd parses (ORG, PAID) → their sum (bands, n0, countries)."""
    keys = BAND_KEYS + ("gt427",)
    cty = {c: list(v) for c, v in a["cty"].items()}
    for c, v in b["cty"].items():
        e = cty.setdefault(c, [0, 0, 0])
        for i in range(3):
            e[i] += v[i]
    return {"rev": {k: a["rev"][k] + b["rev"][k] for k in keys}, "act": {k: a["act"][k] + b["act"][k] for k in keys},
            "n0": a["n0"] + b["n0"], "cty": cty}


def top_countries(cty, n=TOP):
    """{country: [micros, …]} → the n real countries with the most revenue (ties: by code)."""
    return sorted((c for c, v in cty.items() if _real_cc(c) and v[0] > 0), key=lambda c: (-cty[c][0], c))[:n]


def t2_tie(org, paid, qc):
    """T2: ORG + PAID vs the day's full Q-C per band, lag-0 new users and per top country (revenue); the organic share
    per band and of installs per country, the paid share of installs."""
    s = _add(org, paid)
    top = []
    for c in top_countries(qc["cty"]):
        q, o, p = qc["cty"][c], org["cty"].get(c, [0, 0, 0]), paid["cty"].get(c, [0, 0, 0])
        t = _tie(o[0] + p[0], q[0])
        top.append({"cc": c, "r": t["r"], "in": t["in"], "judged": t["judged"], "org": _ratio(o[0], q[0]),
                    "paid_n0": _ratio(p[2], q[2])})
    return {"rev": tie_bands(s, qc), "n0": _n0_tie(s["n0"], qc["n0"]),
            "org_share": {b: _ratio(_bsum(org, b), _bsum(qc, b)) for b in TIE_KEYS},
            "paid_n0": _ratio(paid["n0"], qc["n0"]), "top": top}


def ct_parse(rows, ga):
    """CT → record, index {day: {country: [micros, users, new]}}."""
    idx, oth, rev = {}, [0, 0], 0
    for r in rows:
        d, c = ga4._d(r.get("date")), str(r.get("countryId") or "")
        ad, act, new = gu._mic(r.get("totalAdRevenue")), gu._int(r.get("activeUsers")), gu._int(r.get("newUsers"))
        rev += ad
        if c == "(other)":
            oth[0], oth[1] = oth[0] + 1, oth[1] + ad
        if d is None:
            continue
        e = idx.setdefault(d.isoformat(), {}).setdefault(c, [0, 0, 0])
        e[0], e[1], e[2] = e[0] + ad, e[1] + act, e[2] + new
    ccs = {c for v in idx.values() for c in v if _real_cc(c)}
    return {"rows": len(rows), "pages": ga.last_pages, "days": len(idx), "countries": len(ccs), "oth_rows": oth[0],
            "oth_rev": _ratio(oth[1], rev)}, idx


def qt_parse(rows, ga):
    idx = {}
    for r in rows:
        d = ga4._d(r.get("date"))
        if d is not None:
            idx[d.isoformat()] = [gu._mic(r.get("totalAdRevenue")), gu._int(r.get("activeUsers")),
                                  gu._int(r.get("newUsers"))]
    return {"rows": len(rows), "pages": ga.last_pages, "days": len(idx)}, idx


def t3_tie(ct, qt):
    """T3: per day of the block Σ every CT row (named, "(not set)", "(other)") vs QT — revenue within GAP_MAX (judged
    above $0.001), new users within TIE_NEW (or 1); active users as a ratio only."""
    rr, nr, ar, out = [], [], [], []
    judged = rin = njudged = nin = 0
    for k in sorted(qt):
        q = qt[k]
        s = [sum(v[i] for v in (ct.get(k) or {}).values()) for i in range(3)]
        t = _tie(s[0], q[0])
        if t["judged"]:
            judged += 1
            rin += t["in"]
            rr.append(t["r"])
            if not t["in"]:
                out.append(k)
        n = _n0_tie(s[2], q[2])
        if n["judged"]:
            njudged += 1
            nin += n["in"]
            nr.append(n["r"])
        ar.append(_ratio(s[1], q[1]))
    return {"days": len(qt), "judged": judged, "rev_in": rin, "new_judged": njudged, "new_in": nin,
            "rev_r": sp._dist(rr), "new_r": sp._dist(nr), "act_r": sp._dist(ar), "out_days": out[:OUT_TOP],
            "ct_only_days": sum(1 for k in ct if k not in qt)}


def old_share(qc, qb, t3, d):
    """T3 on a T1 day: the revenue (and users) of users older than Q-B's window = (CT − Σ the full Q-C) ÷ CT, per day
    (named countries) and per top country (by CT revenue); day_qb = 1 − Q-B ÷ Q-T (every row of each); neg = countries
    whose full Q-C is over CT by more than GAP_MAX (non-additive or sampled)."""
    k = d.isoformat()
    ct, qt = ((t3 or {}).get("ct") or {}).get(k), ((t3 or {}).get("qt") or {}).get(k)
    if not ct:
        return None
    named = {c: v for c, v in ct.items() if c != "(other)"}
    cr, qr = sum(v[0] for v in named.values()), sum(v[0] for v in qc["cty"].values())
    top = []
    for c in top_countries(named):
        v, q = named[c], qc["cty"].get(c, [0, 0, 0])
        top.append({"cc": c, "share": _ratio(v[0], cr), "old": _ratio(v[0] - q[0], v[0]),
                    "old_act": _ratio(v[1] - q[1], v[1])})
    neg = sum(1 for c, v in named.items() if v[0] > gu.TIE_ABS_MICROS
              and qc["cty"].get(c, [0])[0] > v[0] * (1 + gu.GAP_MAX) + gu.TIE_ABS_MICROS)
    return {"day": _ratio(cr - qr, cr), "day_qb": _ratio(qt[0] - qb["all"], qt[0]) if qt else None,
            "countries": len(named), "neg": neg, "top": top}


def disc_parse(rows, cand, ga):
    tot, paid, vals = [0, 0, 0], [0, 0, 0], set()
    ns = 0
    for r in rows:
        v = str(r.get(cand) or "")
        x = [gu._int(r.get("activeUsers")), gu._int(r.get("newUsers")), gu._mic(r.get("totalAdRevenue"))]
        tot = [a + b for a, b in zip(tot, x)]
        if is_paid(cand, v):
            paid = [a + b for a, b in zip(paid, x)]
        if v in ("", "(not set)"):
            ns += x[0]
        elif not v.startswith("("):
            vals.add(v)
    return {"rows": len(rows), "pages": ga.last_pages, "values": len(vals), "paid_act": _ratio(paid[0], tot[0]),
            "paid_new": _ratio(paid[1], tot[1]), "paid_rev": _ratio(paid[2], tot[2]),
            "not_set_act": _ratio(ns, tot[0])}, None


def rm_parse(rows, ga):
    days, ccs, oth, ns = set(), set(), [0, 0], 0
    ev = us = 0
    for r in rows:
        c, e, u = str(r.get("countryId") or ""), gu._int(r.get("eventCount")), gu._int(r.get("totalUsers"))
        ev, us = ev + e, us + u
        if r.get("date"):
            days.add(str(r["date"]))
        if c == "(other)":
            oth[0], oth[1] = oth[0] + 1, oth[1] + e
        elif _real_cc(c):
            ccs.add(c)
        else:
            ns += e
    t = pr._totals(ga)
    return {"rows": len(rows), "pages": ga.last_pages, "days": len(days), "countries": len(ccs), "oth_rows": oth[0],
            "oth_ev": _ratio(oth[1], ev), "ns_ev": _ratio(ns, ev),
            "ev_vs_total": _ratio(ev, gu._int(t.get("eventCount"))),
            "users_vs_total": _ratio(us, gu._int(t.get("totalUsers")))}, None


def dim_parse(rows, dim, ga):
    days, vals, oth = set(), set(), 0
    for r in rows:
        v = str(r.get(dim) or "")
        if r.get("date"):
            days.add(str(r["date"]))
        if v == "(other)":
            oth += 1
        elif v and v != "(not set)":
            vals.add(v)
    return {"rows": len(rows), "pages": ga.last_pages, "days": len(days), "values": len(vals), "oth_rows": oth}, None


def meta_parse(j):
    """The metadata response → which watched dimensions the property has (booleans), how many dimensions / custom ones,
    and the registered ad_impression parameters (param → its API name). Other custom names are never kept."""
    dims = {}
    for x in (j or {}).get("dimensions") or []:
        if isinstance(x, dict) and x.get("apiName"):
            dims[str(x["apiName"])] = bool(x.get("customDefinition"))
    low = {k.lower(): k for k in dims}
    watch = CAND_NAMES + tuple(dm for _, dm, _ in T5_DIMS) + ("countryId", "firstSessionDate")
    custom = {p: low.get("customevent:" + p) for p in AD_PARAMS}
    return {"ok": bool(dims), "dims": len(dims), "custom": sum(1 for v in dims.values() if v),
            "has": {k: k in dims for k in watch}, "custom_ad": {p: v for p, v in custom.items() if v}}, None


# ── the plan ────────────────────────────────────────────────────────────────────────────────────

def parse_days(spec, pivot=PIVOT):
    """The T1 days: "B+A" (B days before the pivot, A from it, one day apart), "B+A/S" (S days apart: pivot − S·i for
    i = 1..B, pivot + S·i for i = 0..A−1), or a comma list of ISO days → sorted unique days (≤ MAX_T1_DAYS).
    ValueError when not understood."""
    s = str(spec or "").strip() or DAYS_SPEC
    m = re.fullmatch(r"(\d{1,2})\+(\d{1,2})(?:/(\d{1,3}))?", s)
    if m:
        bn, an, st = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
        if st < 1:
            raise ValueError("step")
        out = [pivot - timedelta(days=st * i) for i in range(1, bn + 1)] + \
              [pivot + timedelta(days=st * i) for i in range(an)]
    else:
        out = [date.fromisoformat(x.strip()) for x in s.split(",") if x.strip()]
    out = sorted(set(out))
    if not out or len(out) > MAX_T1_DAYS:
        raise ValueError("days")
    return out


def _alternate(after, before):
    """Newest from the pivot, newest before it, second newest from it, … (a run stopped early spans both sides)."""
    a, b = sorted(after, reverse=True), sorted(before, reverse=True)
    out = []
    for i in range(max(len(a), len(b))):
        out += ([a[i]] if i < len(a) else []) + ([b[i]] if i < len(b) else [])
    return out


def app_plan(u, days, pivot, t2n, now):
    """One app's dates and units: T1 days (the run's days inside [history_start, F], alternating sides), T2 days (the
    first t2n of them), the T3 block (T3_DAYS ending min(F, first T1 day + T3_DAYS − 1): it holds every T1 day), T4 / T5
    windows (ending F), the discovery day (the newest T1 day from the pivot, else the newest, else F)."""
    end = ga4.window_end_in(u["tz"], now)
    f = end - timedelta(days=LATE)
    hs = gu._d(u["history_start"]) if u.get("history_start") else None
    t1 = [d for d in days if d <= f and (hs is None or d >= hs)]
    order = _alternate([d for d in t1 if d >= pivot], [d for d in t1 if d < pivot])
    b3 = min(f, min(t1) + timedelta(days=T3_DAYS - 1)) if t1 else f
    after = [d for d in t1 if d >= pivot]
    return {"F": f, "t1": order, "t2": order[:max(0, t2n)], "t3": (b3 - timedelta(days=T3_DAYS - 1), b3),
            "t4": (f - timedelta(days=T4_DAYS - 1), f), "t5": (f - timedelta(days=T5_DAYS - 1), f),
            "disc": max(after) if after else (max(t1) if t1 else f),
            "units": ["meta", "t3", "t2disc"] + ["day:" + d.isoformat() for d in order] + ["t4"]
            + ["t5:" + k for k, _, _ in T5_DIMS]}


# ── the units ───────────────────────────────────────────────────────────────────────────────────

def _put(res, uid, rec):
    res["units"][uid] = rec
    return rec


def unit_meta(ga, rec):
    ga.kind = "META"
    c0, s0 = ga.calls, ga.sec
    try:
        j = ga.metadata()
    except Stop:
        raise
    except Exception as e:
        rec.update(ok=False, err=pr._err(e))
    else:
        got = pr._safely(meta_parse, j)
        rec.update(got[0] if isinstance(got, tuple) else dict(got, ok=False))
    rec.update(calls=ga.calls - c0, sec=round(ga.sec - s0, 2), done=_done(rec))


def unit_t3(ga, rec, ix, plan):
    a, b = plan["t3"]
    rec.update(a=a.isoformat(), b=b.isoformat())
    rec["CT"], ct = _read(ga, "CT", lambda: ask(ga, request("CT", a=a, b=b)), lambda rows: ct_parse(rows, ga))
    rec["QT"], qt = _read(ga, "QT", lambda: ask(ga, request("QT", a=a, b=b)), lambda rows: qt_parse(rows, ga))
    if ct is not None and qt is not None:
        rec["tie"] = pr._safely(t3_tie, ct, qt)
        ix["t3"] = {"ct": ct, "qt": qt}
    rec["done"] = _done(rec["CT"]) and _done(rec["QT"])


def unit_disc(ga, rec, plan, has):
    """T2's discovery on the plan's discovery day; a candidate the metadata lacks is not asked (absent)."""
    d = plan["disc"]
    rec["d"] = d.isoformat()
    for cand in CAND_NAMES:
        if has is not None and not has.get(cand, True):
            rec[cand] = {"ok": False, "absent": True}
            continue
        rec[cand], _ = _read(ga, "DISC", lambda: ask(ga, request("DISC", d=d, cand=cand)),
                             lambda rows: disc_parse(rows, cand, ga))
    ok = [c for c in CAND_NAMES if (rec.get(c) or {}).get("ok")]
    tagged = [c for c in ok if (rec[c].get("paid_act") or 0) > 0]
    rec["pick"] = (tagged or ok or [None])[0]
    rec["paid"] = bool(tagged)
    rec["done"] = all(_done(rec[c]) or (rec[c] or {}).get("absent") for c in CAND_NAMES)


def unit_day(ga, rec, d, pivot, plan, ix, pick):
    """A T1 day: Q-B + the full Q-C (+ ORG + PAID on a T2 day with a picked dimension) and their ties; the old shares
    from T3's cells (this run's)."""
    rec.update(d=d.isoformat(), side="after" if d >= pivot else "before", age=(plan["F"] - d).days)
    rec["QB"], qb = _read(ga, "QB", lambda: ask(ga, request("QB", d=d)),
                          lambda rows: (lambda p: (fsd_rec(p, ga), p))(fsd_parse(rows, d)))
    rec["QC"], qc = _read(ga, "QC", lambda: ask(ga, request("QC", d=d)),
                          lambda rows: (lambda p: (fsd_rec(p, ga), p))(fsd_parse(rows, d, True)))
    if qb is not None and qc is not None:
        rec["tie"] = pr._safely(t1_tie, qc, qb)
        rec["old"] = pr._safely(old_share, qc, qb, ix.get("t3"), d)
    t2 = d in plan["t2"]
    if t2 and pick:
        rec["split"] = pick
        rec["ORG"], org = _read(ga, "ORG", lambda: ask(ga, request("ORG", d=d, cand=pick), fallback=False),
                                lambda rows: (lambda p: (fsd_rec(p, ga), p))(fsd_parse(rows, d, True)))
        rec["PAID"], paid = _read(ga, "PAID", lambda: ask(ga, request("PAID", d=d, cand=pick), fallback=False),
                                  lambda rows: (lambda p: (fsd_rec(p, ga), p))(fsd_parse(rows, d, True)))
        if org is not None and paid is not None and qc is not None:
            rec["t2"] = pr._safely(t2_tie, org, paid, qc)
    elif t2:
        rec["split"] = None                                 # no first-user dimension GA4 accepted: nothing to split by
    parts = [rec["QB"], rec["QC"]] + ([rec["ORG"], rec["PAID"]] if "ORG" in rec else [])
    rec["done"] = all(_done(x) for x in parts)


def unit_t4(ga, rec, plan):
    a, b = plan["t4"]
    rec.update(a=a.isoformat(), b=b.isoformat())
    rec["RM"], _ = _read(ga, "RM", lambda: ask(ga, request("RM", a=a, b=b)), lambda rows: rm_parse(rows, ga))
    rec["done"] = _done(rec["RM"])


def unit_dim(ga, rec, kind, dim, mets, plan, has):
    a, b = plan["t5"]
    rec.update(dim=dim)
    if has is not None and not has.get(dim, True):
        rec.update(ok=False, absent=True, done=True)        # the property has no such dimension: rejected, no call
        return
    got, _ = _read(ga, kind, lambda: ask(ga, request("DIM", a=a, b=b, dim=dim, mets=mets)),
                   lambda rows: dim_parse(rows, dim, ga))
    rec.update(got, done=_done(got))


def unit_custom(ga, rec, param, api, plan):
    a, b = plan["t5"]
    got, _ = _read(ga, "CUSTOM", lambda: ask(ga, request("CUSTOM", a=a, b=b, dim=api), fallback=False),
                   lambda rows: dim_parse(rows, api, ga))
    rec.update(got, param=param, done=_done(got))


# ── one app ─────────────────────────────────────────────────────────────────────────────────────

def _cost_add(total, by_kind):
    """{kind: {calls, tokens, sec}} of every run so far (a resumed app's earlier runs + this one)."""
    out = {k: dict(v) for k, v in (total or {}).items() if isinstance(v, dict)}
    for k, v in (by_kind or {}).items():
        e = out.setdefault(k, {"calls": 0, "tokens": 0, "sec": 0.0})
        e["calls"] = pr._int(e.get("calls")) + pr._int(v.get("calls"))
        e["tokens"] = pr._int(e.get("tokens")) + pr._int(v.get("tokens"))
        e["sec"] = round((e.get("sec") or 0) + (v.get("sec") or 0), 2)
    return out


def probe_app(run, u, token, now, prop, opts, old=None):
    """Every unit of one app not already done in `old` (its last result, with resume) → the app's result. Never raises
    for GA4 errors; a Stop ends the app (that unit is kept, marked stopped and not done)."""
    plan = app_plan(u, opts["days"], opts["pivot"], opts["t2_days"], now)
    res = {"key": u["key"], "tz": u["tz"], "F": plan["F"].isoformat(), "history_start": u.get("history_start"),
           "plan": {"t1": [d.isoformat() for d in plan["t1"]], "t2": [d.isoformat() for d in plan["t2"]],
                    "t3": [d.isoformat() for d in plan["t3"]], "t4": [d.isoformat() for d in plan["t4"]],
                    "t5": [d.isoformat() for d in plan["t5"]], "disc": plan["disc"].isoformat()},
           "runs": pr._int((old or {}).get("runs")) + 1, "units": {}}
    held = {k: v for k, v in ((old or {}).get("units") or {}).items() if isinstance(v, dict) and v.get("done")}
    if not token:
        res.update(units=held, err={"type": "auth"}, complete=False, cost_all=(old or {}).get("cost_all") or {})
        return res
    ga = App(token, u["property_id"], u["stream_id"], run, prop, cap=opts.get("app_calls", APP_CALLS))
    ix = {}
    pending_day = any(uid.startswith("day:") and uid not in held for uid in plan["units"])
    uid = None
    try:
        why = ga.stop or run.over()
        if why:
            raise Stop(why)
        for uid in list(plan["units"]):
            if uid in held and not (uid == "t3" and pending_day):
                res["units"][uid] = held[uid]
                continue
            rec = _put(res, uid, {"done": False})
            if uid == "meta":
                unit_meta(ga, rec)
            elif uid == "t3":
                unit_t3(ga, rec, ix, plan)
            elif uid == "t2disc":
                unit_disc(ga, rec, plan, (res["units"].get("meta") or {}).get("has") if
                          (res["units"].get("meta") or {}).get("ok") else None)
            elif uid.startswith("day:"):
                unit_day(ga, rec, date.fromisoformat(uid[4:]), opts["pivot"], plan, ix,
                         (res["units"].get("t2disc") or {}).get("pick"))
            elif uid == "t4":
                unit_t4(ga, rec, plan)
            else:
                k = uid[3:]
                (_, dim, mets), = [x for x in T5_DIMS if x[0] == k]
                meta = res["units"].get("meta") or {}
                unit_dim(ga, rec, k, dim, mets, plan, meta.get("has") if meta.get("ok") else None)
        meta = res["units"].get("meta") or {}
        for p, api in sorted((meta.get("custom_ad") or {}).items()):
            uid = "t5c:" + p
            plan["units"].append(uid)
            if uid in held:
                res["units"][uid] = held[uid]
                continue
            unit_custom(ga, _put(res, uid, {"done": False}), p, api, plan)
        uid = None
    except Stop as e:
        res["stopped"] = str(e)
        if uid and isinstance(res["units"].get(uid), dict):
            res["units"][uid].update(stopped=str(e), done=False)
    finally:
        for k, v in held.items():    # a done unit of the last run: kept (also when its re-ask — t3 — was cut short)
            if not (res["units"].get(k) or {}).get("done"):
                res["units"][k] = v
        meta = res["units"].get("meta") or {}
        want = plan["units"] + ["t5c:" + p for p in sorted(meta.get("custom_ad") or {})
                                if "t5c:" + p not in plan["units"]]
        res["complete"] = all((res["units"].get(k) or {}).get("done") for k in want)
        res["pending"] = sum(1 for k in want if not (res["units"].get(k) or {}).get("done"))
        res.update(calls=ga.by_kind, tokens=ga.tok, tok_delta=ga.tok_delta, sec=round(ga.sec, 2),
                   server_errors=ga.server_errors, no_total=ga.no_total,
                   cost_all=_cost_add((old or {}).get("cost_all"), ga.by_kind))
        if ga.stop and "stopped" not in res:
            res["stopped"] = ga.stop
    return res


# ── the summary (private) and the counts (public) ───────────────────────────────────────────────

def _units(apps, prefix):
    out = []
    for a in apps.values():
        for uid, u in sorted(((a or {}).get("units") or {}).items()):
            if isinstance(u, dict) and (uid == prefix or uid.startswith(prefix)):
                out.append(u)
    return out


def _kind(recs):
    """Reads of one kind → n, ok, refused (4xx but 429), other errors, rows / tokens / seconds stats, pages, flags."""
    recs = [r for r in recs if isinstance(r, dict)]
    errs = [r["err"] for r in recs if "err" in r]
    ok = [r for r in recs if r.get("ok")]
    h4 = sum(1 for e in errs if _final(e))
    return {"n": len(recs), "ok": len(ok), "refused": h4, "err_other": len(errs) - h4,
            "absent": sum(1 for r in recs if r.get("absent")), "rows": sp._stats([r.get("rows") for r in ok]),
            "pages_max": max([r.get("pages") or 0 for r in ok], default=0),
            "tok": sp._stats([r.get("tok") for r in ok]),
            "sec": sp._stats([r.get("sec") for r in ok]), "loss": sum(1 for r in ok if r.get("loss")),
            "sampled": sum(1 for r in ok if r.get("sampled")), "smp_frac": sp._dist([r.get("smp_frac") for r in ok]),
            "thresh": sum(1 for r in ok if r.get("thresh")), "oth": sum(1 for r in ok if r.get("oth_rows")),
            "usd_bad": sum(1 for r in ok if r.get("usd") is False)}


def _tsum(ts):
    ts = [t for t in ts if isinstance(t, dict)]
    j = [t for t in ts if t.get("judged")]
    return {"n": len(ts), "judged": len(j), "inside": sum(1 for t in j if t.get("in")),
            "r": sp._dist([t.get("r") for t in j])}


def _ties(recs, key):
    """{band: tie counts} + n0 over the records' `key` ties."""
    ts = [r[key] for r in recs if isinstance(r.get(key), dict) and "rev" in r[key]]
    return {"rev": {b: _tsum([t["rev"].get(b) for t in ts]) for b in TIE_KEYS}, "n0": _tsum([t.get("n0") for t in ts])}


def summary(apps):
    """T1 / T2 per side of the pivot, T3, T4, T5, cost — see the module docstring."""
    apps = {k: a for k, a in apps.items() if isinstance(a, dict)}
    days = _units(apps, "day:")
    out = {"t1": {}, "t2": {}}
    for side in ("before", "after"):
        us = [u for u in days if u.get("side") == side]
        qc = [u["QC"] for u in us if isinstance(u.get("QC"), dict)]
        ok = [q for q in qc if q.get("ok")]
        olds = [u["old"] for u in us if isinstance(u.get("old"), dict) and "day" in u["old"]]
        out["t1"][side] = dict(
            _ties(us, "tie"), days=len(us), QB=_kind([u.get("QB") for u in us]), QC=_kind(qc),
            share={b: sp._dist([((u.get("tie") or {}).get("share") or {}).get(b) for u in us]) for b in TIE_KEYS},
            oth_rev=sp._dist([q.get("oth_rev") for q in ok]), le90_rows=sp._dist([q.get("le90_rows") for q in ok]),
            total_r=sp._dist([q.get("total_r") for q in ok]), gt427=sum(1 for q in ok if q.get("gt427")),
            old={"days": len(olds), "day": sp._dist([o.get("day") for o in olds]),
                 "day_qb": sp._dist([o.get("day_qb") for o in olds]),
                 "cty": sp._dist([x.get("old") for o in olds for x in o.get("top") or []]),
                 "cty_act": sp._dist([x.get("old_act") for o in olds for x in o.get("top") or []]),
                 "neg": sum(o.get("neg") or 0 for o in olds)})
        sp_ = [u for u in us if "ORG" in u]
        t2 = [u["t2"] for u in sp_ if isinstance(u.get("t2"), dict) and "rev" in u["t2"]]
        out["t2"][side] = dict(
            _ties(sp_, "t2"), days=len(sp_), no_dim=sum(1 for u in us if "split" in u and u["split"] is None),
            ORG=_kind([u.get("ORG") for u in sp_]), PAID=_kind([u.get("PAID") for u in sp_]),
            top=_tsum([x for t in t2 for x in t.get("top") or []]),
            org_share={b: sp._dist([(t.get("org_share") or {}).get(b) for t in t2]) for b in TIE_KEYS},
            paid_n0=sp._dist([t.get("paid_n0") for t in t2]))
    discs = _units(apps, "t2disc")
    out["t2"]["disc"] = {c: dict(_kind([d.get(c) for d in discs]),
                                 with_paid=sum(1 for d in discs if ((d.get(c) or {}).get("paid_act") or 0) > 0),
                                 paid_act=sp._dist([(d.get(c) or {}).get("paid_act") for d in discs]),
                                 paid_new=sp._dist([(d.get(c) or {}).get("paid_new") for d in discs]))
                         for c in CAND_NAMES}
    out["t2"]["picked"] = {c: sum(1 for d in discs if d.get("pick") == c) for c in CAND_NAMES}
    out["t2"]["none"] = sum(1 for d in discs if d.get("done") and not d.get("pick"))
    out["t2"]["paid_apps"] = sum(1 for d in discs if d.get("paid"))
    t3 = _units(apps, "t3")
    ties = [t["tie"] for t in t3 if isinstance(t.get("tie"), dict) and "days" in t["tie"]]
    out["t3"] = {"apps": len(t3), "CT": _kind([t.get("CT") for t in t3]), "QT": _kind([t.get("QT") for t in t3]),
                 "days": sum(t["days"] for t in ties), "judged": sum(t["judged"] for t in ties),
                 "rev_in": sum(t["rev_in"] for t in ties), "new_judged": sum(t["new_judged"] for t in ties),
                 "new_in": sum(t["new_in"] for t in ties),
                 "rev_r_p50": sp._dist([(t.get("rev_r") or {}).get("p50") for t in ties]),
                 "rev_r_p10": sp._dist([(t.get("rev_r") or {}).get("p10") for t in ties]),
                 "act_r_p50": sp._dist([(t.get("act_r") or {}).get("p50") for t in ties]),
                 "countries": sp._stats([(t.get("CT") or {}).get("countries") for t in t3])}
    t4 = [u.get("RM") for u in _units(apps, "t4")]
    ok4 = [r for r in t4 if isinstance(r, dict) and r.get("ok")]
    out["t4"] = dict(_kind(t4), countries=sp._stats([r.get("countries") for r in ok4]),
                     ev_vs_total=sp._dist([r.get("ev_vs_total") for r in ok4]),
                     users_vs_total=sp._dist([r.get("users_vs_total") for r in ok4]),
                     oth_ev=sp._dist([r.get("oth_ev") for r in ok4]), ns_ev=sp._dist([r.get("ns_ev") for r in ok4]))
    metas = _units(apps, "meta")
    out["t5"] = {k: dict(_kind(_units(apps, "t5:" + k)), values=sp._stats(
        [u.get("values") for u in _units(apps, "t5:" + k) if u.get("ok")])) for k, _, _ in T5_DIMS}
    out["t5"]["meta"] = {"n": len(metas), "ok": sum(1 for m in metas if m.get("ok")),
                         "custom_dims": sp._stats([m.get("custom") for m in metas if m.get("ok")]),
                         "has": {d: sum(1 for m in metas if (m.get("has") or {}).get(d))
                                 for d in CAND_NAMES + tuple(dm for _, dm, _ in T5_DIMS)},
                         "custom_ad": {p: sum(1 for m in metas if p in (m.get("custom_ad") or {})) for p in AD_PARAMS}}
    out["t5"]["custom"] = {p: _kind(_units(apps, "t5c:" + p)) for p in AD_PARAMS}
    by = {}
    for a in apps.values():                          # every run of every app (resumed apps: all their runs)
        by = _cost_add(by, a.get("cost_all") or a.get("calls"))
    out["cost"] = {"by_kind": by, "calls": sum(e["calls"] for e in by.values()),
                   "tokens": sum(e["tokens"] for e in by.values()),
                   "tokens_max_app": max([sum(pr._int(v.get("tokens")) for v in (a.get("cost_all") or {}).values())
                                          for a in apps.values()], default=0)}
    return out


def _inside(sm, side, band):
    t = (((sm.get("t1") or {}).get(side) or {}).get("rev") or {}).get(band) or {}
    return t.get("inside", 0), t.get("judged", 0)


def counts(apps, run, probed):
    """The public counts (no ids, names, dates, countries, user or money numbers)."""
    apps = {k: a for k, a in apps.items() if isinstance(a, dict)}
    days = _units(apps, "day:")
    qc = [u.get("QC") for u in days if isinstance(u.get("QC"), dict)]
    qok = [u for u in days if (u.get("QC") or {}).get("ok")]

    def side(s, f):
        return sum(1 for u in qok if u.get("side") == s and f(u["QC"]))
    c = {"apps": len(apps), "complete": sum(1 for a in apps.values() if a.get("complete")), "probed": len(probed),
         "calls": run.calls, "seconds": run.elapsed(),
         "tokens": sum(pr._int(apps[k].get("tokens")) for k in probed if k in apps),
         "quota_low": sum(1 for k in probed if str((apps.get(k) or {}).get("stopped") or "").startswith("quota")),
         "stopped": sum(1 for k in probed if (apps.get(k) or {}).get("stopped")),
         "errors": sum(1 for a in apps.values() if a.get("crash") or a.get("err"))
         + sum(1 for a in apps.values() for u in (a.get("units") or {}).values() if isinstance(u, dict)
               for r in [u] + [v for v in u.values() if isinstance(v, dict)]
               if "err" in r and not _final(r["err"])),
         "t1_days": len(qc), "t1_ok": len(qok),
         "t1_loss_b": side("before", lambda q: q.get("loss")), "t1_loss_a": side("after", lambda q: q.get("loss")),
         "t1_b": side("before", lambda q: True), "t1_a": side("after", lambda q: True),
         "t1_smp": sum(1 for u in qok if u["QC"].get("sampled")),
         "t1_thr": sum(1 for u in qok if u["QC"].get("thresh")),
         "t1_oth": sum(1 for u in qok if u["QC"].get("oth_rows"))}
    for b in BAND_KEYS:
        ins = [t for u in qok for t in [((u.get("tie") or {}).get("rev") or {}).get(b)] if t and t.get("judged")]
        c["t1_in_" + b], c["t1_j_" + b] = sum(1 for t in ins if t.get("in")), len(ins)
    n0 = [(u.get("tie") or {}).get("n0") for u in qok]
    n0 = [t for t in n0 if t and t.get("judged")]
    c["t1_in_n0"], c["t1_j_n0"] = sum(1 for t in n0 if t.get("in")), len(n0)
    discs = _units(apps, "t2disc")
    c["t2_apps"], c["t2_dim"] = len(discs), sum(1 for d in discs if d.get("pick"))
    for i, cand in enumerate(CAND_NAMES):
        c["t2_pick%d" % i] = sum(1 for d in discs if d.get("pick") == cand)
    c["t2_paid"] = sum(1 for d in discs if d.get("paid"))
    sd = [u for u in days if "ORG" in u]
    t2 = [u["t2"] for u in sd if isinstance(u.get("t2"), dict) and "rev" in u["t2"]]
    c["t2_days"], c["t2_tied"] = len(sd), len(t2)
    bands = [t["rev"][b] for t in t2 for b in BAND_KEYS if t["rev"][b].get("judged")]
    c["t2_in_b"], c["t2_j_b"] = sum(1 for t in bands if t.get("in")), len(bands)
    top = [x for t in t2 for x in t.get("top") or [] if x.get("judged")]
    c["t2_in_c"], c["t2_j_c"] = sum(1 for x in top if x.get("in")), len(top)
    n0 = [t["n0"] for t in t2 if (t.get("n0") or {}).get("judged")]
    c["t2_in_n0"], c["t2_j_n0"] = sum(1 for t in n0 if t.get("in")), len(n0)
    t3 = _units(apps, "t3")
    ok3 = [t for t in t3 if (t.get("CT") or {}).get("ok") and (t.get("QT") or {}).get("ok")]
    ties = [t["tie"] for t in ok3 if isinstance(t.get("tie"), dict) and "days" in t["tie"]]
    olds = [u["old"] for u in qok if isinstance(u.get("old"), dict) and "day" in u["old"]]
    c.update(t3_apps=len(t3), t3_ok=len(ok3), t3_in=sum(t["rev_in"] for t in ties), t3_j=sum(t["judged"] for t in ties),
             t3_nin=sum(t["new_in"] for t in ties), t3_nj=sum(t["new_judged"] for t in ties),
             t3_loss=sum(1 for t in ok3 if t["CT"].get("loss")), t3_smp=sum(1 for t in ok3 if t["CT"].get("sampled")),
             t3_oth=sum(1 for t in ok3 if t["CT"].get("oth_rows")), t3_old=len(olds),
             t3_cells=sum(len(o.get("top") or []) for o in olds), t3_neg=sum(o.get("neg") or 0 for o in olds))
    rm = [u.get("RM") for u in _units(apps, "t4")]
    ok4 = [r for r in rm if isinstance(r, dict) and r.get("ok")]
    c.update(t4_apps=len(rm), t4_ok=len(ok4), t4_loss=sum(1 for r in ok4 if r.get("loss")),
             t4_smp=sum(1 for r in ok4 if r.get("sampled")), t4_thr=sum(1 for r in ok4 if r.get("thresh")),
             t4_oth=sum(1 for r in ok4 if r.get("oth_rows")),
             t4_whole=sum(1 for r in ok4 if r.get("ev_vs_total") == 1.0))
    for k, _, _ in T5_DIMS:
        us = _units(apps, "t5:" + k)
        c["t5_ok_" + k], c["t5_n_" + k] = sum(1 for u in us if u.get("ok")), len(us)
    metas = _units(apps, "meta")
    cu = [u for p in AD_PARAMS for u in _units(apps, "t5c:" + p)]
    c.update(meta_ok=sum(1 for m in metas if m.get("ok")), meta_n=len(metas),
             custom_reg=sum(1 for m in metas if m.get("custom_ad")), custom_ok=sum(1 for u in cu if u.get("ok")),
             custom_n=len(cu))
    return c


def _g(c, k):
    return pr._int((c or {}).get(k))


def public_lines(c):
    """One counts-only line per test, then the run's."""
    def g(k):
        return _g(c, k)
    t1 = ("T1 full Q-C: days read %d/%d (before %d, after %d), (other) loss before %d after %d, sampled %d, "
          "thresholded %d, (other) rows %d; tied to Q-B 0-90 %d/%d, 91-180 %d/%d, 181-365 %d/%d, 366-427 %d/%d, "
          "new users %d/%d" % (g("t1_ok"), g("t1_days"), g("t1_b"), g("t1_a"), g("t1_loss_b"), g("t1_loss_a"),
                               g("t1_smp"), g("t1_thr"), g("t1_oth"), g("t1_in_0_90"), g("t1_j_0_90"),
                               g("t1_in_91_180"), g("t1_j_91_180"), g("t1_in_181_365"), g("t1_j_181_365"),
                               g("t1_in_366_427"), g("t1_j_366_427"), g("t1_in_n0"), g("t1_j_n0")))
    t2 = ("T2 paid/organic: split dimension %d/%d apps (%s), with paid users %d; split days tied %d/%d; organic+paid "
          "tied to Q-C bands %d/%d, top countries %d/%d, new users %d/%d"
          % (g("t2_dim"), g("t2_apps"),
             ", ".join("%s %d" % (lb, g("t2_pick%d" % i)) for i, lb in enumerate(CAND_LABELS)), g("t2_paid"),
             g("t2_tied"), g("t2_days"), g("t2_in_b"), g("t2_j_b"), g("t2_in_c"), g("t2_j_c"), g("t2_in_n0"),
             g("t2_j_n0")))
    t3 = ("T3 country totals: blocks read %d/%d, days tied to Q-T revenue %d/%d, new users %d/%d; loss %d, sampled %d, "
          "(other) rows %d; old-share days %d, country cells %d, over-total %d"
          % (g("t3_ok"), g("t3_apps"), g("t3_in"), g("t3_j"), g("t3_nin"), g("t3_nj"), g("t3_loss"), g("t3_smp"),
             g("t3_oth"), g("t3_old"), g("t3_cells"), g("t3_neg")))
    t4 = ("T4 app_remove by country: read %d/%d, loss %d, sampled %d, thresholded %d, (other) rows %d, "
          "event sums whole %d" % (g("t4_ok"), g("t4_apps"), g("t4_loss"), g("t4_smp"), g("t4_thr"), g("t4_oth"),
                                   g("t4_whole")))
    t5 = ("T5 dimensions accepted: %s; metadata %d/%d; ad params registered on %d apps, read %d/%d"
          % (", ".join("%s %d/%d" % (lb, g("t5_ok_" + k), g("t5_n_" + k))
                       for (k, _, _), lb in zip(T5_DIMS, T5_LABELS)),
             g("meta_ok"), g("meta_n"), g("custom_reg"), g("custom_ok"), g("custom_n")))
    run = ("country probe: apps complete %d/%d, probed now %d, calls %d, tokens %d, quota low %d, stopped %d, "
           "errors %d, %ds" % (g("complete"), g("apps"), g("probed"), g("calls"), g("tokens"), g("quota_low"),
                               g("stopped"), g("errors"), g("seconds")))
    return [t1, t2, t3, t4, t5, run]


# ── the run ─────────────────────────────────────────────────────────────────────────────────────

def units_from_state(state):
    """The build's GA4 apps (ga4_shape_probe.units_from_state: one per Android stream, its AdMob ids and history start),
    each with its KEY (the Uninstall file key of its first AdMob app id)."""
    out = sp.units_from_state(state)
    for u in out:
        u["key"] = gu.file_key(u["app_id"])
    return out


def run_probe(units, cid, sec, tokens, opts, now=None, clock=time.monotonic, workers=WORKERS, tick=TICK_SEC,
              last=None):
    """Probe every unit (resuming from `last`, the last report's apps by key, when opts["resume"]) → the report. Apps of
    `last` not probed now are carried over as they were. Never raises for one app; prints counts-only progress."""
    run = Run(opts.get("budget") or BUDGET_SEC, clock, opts.get("max_calls") or MAX_CALLS)
    now = now or datetime.now(timezone.utc)
    rt, access = dict(tokens), {}
    for owner in sorted({u.get("owner") or "" for u in units}):
        try:
            access[owner] = ga4.access_token(cid, sec, rt[owner]) if owner in rt else None
        except Exception:
            access[owner] = None
    last = {k: v for k, v in (last or {}).items() if isinstance(v, dict)}
    probed = [u["key"] for u in units]
    out = {k: v for k, v in last.items() if k not in set(probed)}
    props = {u["property_id"]: pr.new_prop() for u in units}
    lock, done = threading.Lock(), [0]

    def one(group):
        for u in group:
            try:
                r = probe_app(run, u, access.get(u.get("owner") or ""), now, props[u["property_id"]], opts,
                              last.get(u["key"]) if opts.get("resume") else None)
            except Exception as e:                   # a bug for one app must not cost the others
                r = {"key": u["key"], "crash": type(e).__name__, "complete": False,
                     "units": dict((last.get(u["key"]) or {}).get("units") or {}) if opts.get("resume") else {}}
            with lock:
                out[u["key"]] = r
                done[0] += 1
                n = done[0]
            run.say("country progress: apps %d/%d, calls %d, %ds" % (n, len(units), run.calls, run.elapsed()))

    with sp.Beat(run, tick):
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            list(ex.map(one, pr._groups(units)))
    c = pr._safely(counts, out, run, probed, fallback={"apps": len(out), "calls": run.calls,
                                                       "seconds": run.elapsed()})
    return {"v": 1, "probe": "ga4_country", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rules": {"pivot": opts["pivot"].isoformat(), "days": [d.isoformat() for d in opts["days"]],
                      "t2_days": opts["t2_days"], "t3_days": T3_DAYS, "t4_days": T4_DAYS, "t5_days": T5_DAYS,
                      "late": LATE, "bands": [list(b) for b in BANDS], "gap_max": gu.GAP_MAX, "tie_new": gu.TIE_NEW,
                      "tie_abs_micros": gu.TIE_ABS_MICROS, "tie_abs_users": gu.TIE_ABS_USERS, "top": TOP,
                      "cands": [[c, k, list(r) if isinstance(r, tuple) else r] for c, k, r in CANDS],
                      "max_calls": run.max_calls, "app_calls": opts.get("app_calls", APP_CALLS),
                      "quota_frac": pr.QUOTA_FRAC, "page_rows": PAGE_ROWS, "resume": bool(opts.get("resume"))},
            "counts": c, "summary": pr._safely(summary, out), "apps": out}


def options(inputs, env):
    """The run's options: the workflow's inputs (its event file) first, then COUNTRY_* environment variables (local
    runs). ValueError on days / pivot that are not understood."""
    def get(k, e):
        v = inputs.get(k)
        return env.get(e) if v is None or str(v).strip() == "" else v
    pivot = date.fromisoformat(str(get("pivot", "COUNTRY_PIVOT") or PIVOT.isoformat()).strip())
    t2 = get("t2_days", "COUNTRY_T2_DAYS")
    return {"max_apps": pr._int(get("max_apps", "COUNTRY_MAX_APPS")), "apps": ap.wanted(get("apps", "COUNTRY_APPS")),
            "resume": ap._flag(get("resume", "COUNTRY_RESUME")), "pivot": pivot,
            "days": parse_days(get("days", "COUNTRY_DAYS"), pivot),
            "t2_days": T2_DAYS if t2 is None or str(t2).strip() == "" else max(0, min(MAX_T1_DAYS, pr._int(t2))),
            "max_calls": pr._int(get("max_calls", "COUNTRY_MAX_CALLS")) or MAX_CALLS, "app_calls": APP_CALLS,
            "budget": pr._int(env.get("COUNTRY_BUDGET_SEC")) or BUDGET_SEC}


def load_last(root):
    """The last report's apps {key: result}: the clone's copy when there is a clone, else the contents API; {} when
    there is none (a first run)."""
    if root and os.path.isdir(os.path.join(root, "data")):
        try:
            with open(os.path.join(root, OUT_PATH), encoding="utf-8") as f:
                j = json.load(f)
        except (OSError, ValueError):
            return {}
    else:
        try:
            j = _private_json(OUT_PATH)
        except (Exception, SystemExit):                 # _private_json sys.exits on a non-200 (no report yet)
            return {}
    apps = (j or {}).get("apps") if isinstance(j, dict) else None
    return {k: v for k, v in (apps or {}).items() if isinstance(v, dict)}


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    try:
        opts = options(ap.event_inputs(env), env)
    except ValueError:
        print("country probe: the days / pivot input is not understood", flush=True)
        sys.exit(2)
    root = env.get("COUNTRY_DATA_DIR") or DATA_DIR
    units = units_from_state(sp.load_state(root))
    if opts["apps"]:
        units = [u for u in units if ap.matches(u, opts["apps"]) or u["key"] in opts["apps"]]
    if opts["max_apps"] > 0:
        units = units[:opts["max_apps"]]
    if not units:
        sys.exit("no GA4 app routes in the private state (or none matched)")
    last = load_last(root)
    held = sum(1 for u in units if (last.get(u["key"]) or {}).get("complete")) if opts["resume"] else 0
    if opts["resume"]:                               # complete in the last report: carried, not asked again
        units = [u for u in units if not (last.get(u["key"]) or {}).get("complete")]
    print("country probe: %d app(s) to probe, %d complete carried over%s"
          % (len(units), held, ", resuming" if opts["resume"] else ""), flush=True)
    report = run_probe(units, cid, sec, tokens, opts, now=now, clock=clock, last=last)
    for line in public_lines(report["counts"]):
        print(line, flush=True)
    if not pr.write_private(OUT_PATH, pr._dump(report), "ga4 country probe"):
        sys.exit("private repo write failed")            # stderr: hidden by the workflow step
    print("country probe: report written", flush=True)


if __name__ == "__main__":
    main()
