"""One-off GA4 SHAPE probe, run by .github/workflows/ga4-shape-probe.yml: before the "Install value" tab (country-wise
D1/D7/D30 + earning per install, and ads money back) is built, measure every GA4 request its design may use — does GA4
accept it, how big is it (rows, pages), what does it cost (quota tokens, seconds), is it whole ("(other)" rows,
thresholding, sampling), do the pieces add up, and does GA4's ad revenue tie to AdMob's.

For every GA4 app of the build (the private state's routes, one per Android stream) and up to three ACTIVITY days D —
"recent" = E − LATE (E = today − 2 in the property timezone: the design's newest readable day), "d100" = today − 100,
"d400" = today − 400, each only when the app has data that far back — it asks, ONE activity day per request:
  QB    (a)  dims [firstSessionDate], metrics activeUsers, newUsers, totalAdRevenue, totalRevenue, currencyCode USD,
             TOTAL — the design's Q-B; Σ totalRevenue / totalAdRevenue vs AdMob (below)
  QA         dims [countryId, firstSessionDate], same metrics — the design's Q-A (the owner's "Country" + "First
             session date" screen plus revenue); its Σ over countries vs QB, cell by cell (install day D − L)
  QA6   (b)  QA + firstSessionDate inList [D, D−1, D−3, D−7, D−14, D−30] — vs QA restricted to the same install days
  QA90  (c)  QA + firstSessionDate inList D−90 .. D (91 values) — the same
  VER   (e)  dims [firstSessionDate, appVersion], activeUsers, newUsers — sizes "retention by version at install" (C)
  COH  (M3)  cohortSpec: single-day cohorts X = D − L, L in COH_LAGS (1 .. 365), DAILY 0 .. max L — cohortActiveUsers
             on day L (= day D) vs the QB / QA cell of install day X on D (do the one-day report's long-lag cells
             hold?); an endOffset GA4 refuses (HTTP 400) is asked once more with lags ≤ COH_SHORT only (M6b)
and once per app, on the recent day:
  COH_CTY / COH_REV / COH_CTY_REV / COH_FILT  (d)  cohortSpec (X = D − 7, days 0..7) + a countryId dimension / +
             totalAdRevenue / + both / + dimensionFilter countryId == the top country — accepted, or the HTTP class
             only (never the error text); when accepted, compared with COH and QA
  BETWEEN    QA with a numeric betweenFilter on firstSessionDate (D−90 .. D) — accepted? (informational)
  IN200 (M11) QA + firstSessionDate inList of 200 values — accepted, rows / tokens vs QA
  CTY56 (M5) dims [date, countryId] totalAdRevenue over the 56 days to E — vs AdMob revenue by country
  PAID (M10) dims [date, firstUserGoogleAdsCampaignId] newUsers over 28 days — vs Google Ads installs
plus REF: dims [date] over the last REF_DAYS days (activeUsers, newUsers, totalAdRevenue, totalRevenue, eventCount,
publisherAdImpressions; USD) — every split's own day total (coverage, M4), the app's first data day, the IAP share
(M7) and GA4's weekly ad revenue for M5; and the property's currency / timezone (Admin API, M8).
Every read records: rows, rowCount, pages, tokensPerDay consumed (and the drop of tokensPerDay remaining across the
call), seconds (incl. the 0.2 s pause), subjectToThresholding, dataLossFromOtherRow, samplingMetadatas, "(other)" /
"(not set)" rows and their share of users and revenue, the response currency. A GA4 400 on the four metrics falls
back ONCE to three (no totalRevenue — the design's no_total) for the rest of that app.

AdMob / Google Ads side — IN THE JOB, not offline: the workflow makes a read-only clone of the PRIVATE repo
(SHAPE_DATA_DIR) and this reads data/network.json.gz (AdMob Network) and data/mediation.json.gz (every ad source)
exactly as the build does (build_static.admob_revenue / mediation_revenue → uninstall_build.app_revenue: the stream's
own AdMob app + every AdMob app of the same Play package, in the AdMob report timezone = the private
site/dashboard.json.gz report_tz), blended onto GA4 days by engine.impact._revenue_fn; data/country.json.gz (AdMob
revenue by country) and data/roas_spend_cache.json (Google Ads installs). Without the clone the GA4 part still runs
and "admob" says absent (compare offline later). Every AdMob account is read in that one report timezone: the
build's per-account zones (account_tzs) need the AdMob API, which this job does not have — the weekly ratios barely
move with it, a single day's (m5.days) can. AdMob by country is by AdMob day, not blended (56 days: ≈ 1% at most).

Not measured here: M9 (fresh-day stability — needs a re-read days later: the design's late check does it after
deploy). M12 (file sizes) is an ESTIMATE: the design's iday file built for the app's whole history from this app's own
recent magnitudes (jittered), gzipped the way write_json_gz_stable writes.

Output: ga4/shape_probe.json in the PRIVATE repo (write_private — never data/ or site/): per app the raw measurements,
and a summary per measurement kind, per day slot, and per design question M1–M12 (see summary()). PUBLIC LOG: progress
counts and ONE result line of counts; no names, ids, emails, dates, user or money numbers, no API error text; a
counts-only heartbeat at least every minute. QUOTA and safety are ga4_d1d7_probe's: returnPropertyQuota on every call;
per PROPERTY (shared by its apps) a stop when any token bucket is under half, ≤ 4 server-error / ≤ 5 thresholded
requests are left this hour, on a 429, or after 2 failed calls on 5xx; one request at a time per property (WORKERS
properties in parallel); no call after the time budget, and what is measured is still written.

Reading ga4/shape_probe.json — "summary":
  kinds[K], by_slot[slot][K]  per request kind: n, ok, http400, err_other, rows / tok / tok_delta / sec (p50 p90 max
                              mean), pages_max, thresh, with_other, loss_other, sampled, no_total, usd
  m1       QA tokens p90 → iday_max_calls_hint (≤ 12 → 120, ≤ 30 → 60, else 30)
  m2       "(other)" per kind × age slot: over_oth_max (≥ 2% of users) on QA_recent > 0 ⇒ the design's qb switch
  m3       per lag L: cohort cell vs the one-day QB / QA cell within 3% — qb_within_3pct of NONZERO (a cell 0 on every
           side ties trivially and is not counted); ≥ 95% ⇒ long lags trusted; big / big_qb_within_3pct: ≥ M3_BIG users
  m4       Σ rows vs TOTAL (total_within) and vs the day (cov / ncov / rcov / tcov medians); QA Σ countries vs QB
  m5       GA4 ÷ AdMob (all sources) weekly p50 per app → median; the decision reads the weeks with ≥ $20 on both
           sides (the design's k floor), apps with ≥ 4 of them: apps_20usd_p50_outside_07_13 ≥ 5 ⇒ revisit K_OK
           (apps_p50_outside_07_13: every week, small apps included)
  m6       cohort variants GA4 accepts (country dimension / revenue / both / country filter), BETWEEN; COH end 365 ok?
  m7 m8 m10  IAP share ≥ 1% apps; property vs response currency; GA4 Google-Ads new users ÷ Ads installs
  m11_bc   (b) QA6, (c) QA90, IN200, BETWEEN vs QA: token / row ratios, share of equal cells, "(other)" reads
  ver      (e) versions among a day's installs; days where one version holds ≥ 80% (the design's C grouping)
  m12      the iday file's gz bytes (hot / old / total), an estimate; cost: calls, tokens, seconds
"apps"[package]: ref, days[slot][kind], once[kind] (every read's raw summary + its comparisons: vs_QB, vs_QA, cells),
m5 (days: GA4 Σ totalAdRevenue / totalRevenue vs AdMob network / all on that GA4 day; weeks; r_all / r_net / r_all_20;
cty: top-10 countries, usd_ok = ≥ $20 on both sides over the 56 days; paid; iap), m12,
calls (per kind: calls, tokens, sec), tokens, stopped. "admob": state (ok / absent / error), tz_src, apps_matched.
"""

import gzip
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from admob_iq import ga4_probe
from admob_iq.engine import impact as imp
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_uninstall as gu
from admob_iq.fetch.ga4_d1d7_probe import Stop, _safely, write_private
from admob_iq.fetch.ga4_diagnose import _private_json

LATE = 3                            # the design's newest readable day: F = E − IDAY_LATE (E = today − 2)
SLOTS = (("recent", None), ("d100", 100), ("d400", 400))   # activity days: F, today − 100, today − 400
METS = ("activeUsers", "newUsers", "totalAdRevenue", "totalRevenue")
METS_NO_TOTAL = METS[:3]            # the design's no_total fallback
REF_METS = ("activeUsers", "newUsers", "totalAdRevenue", "totalRevenue", "eventCount", "publisherAdImpressions")
REF_FALLBACK = (REF_METS[:5], REF_METS[:2])
SHORT = {"activeUsers": "act", "newUsers": "new", "totalAdRevenue": "ad", "totalRevenue": "tot", "eventCount": "ev",
         "publisherAdImpressions": "imp"}
REF_DAYS = 410                      # the dims [date] reference: today − 410 .. E (covers d400 and 13 weeks)
LIST_LAGS = (0, 1, 3, 7, 14, 30)    # (b): firstSessionDate inList D − these
LIST90 = 91                         # (c): D − 90 .. D
LIST_BIG = 200                      # M11
COH_LAGS = (1, 7, 30, 60, 90, 180, 365)
COH_SHORT = 90                      # a refused long endOffset is asked once more with lags ≤ this
COH_X_LAG = 7                       # the once-per-app cohort variants: install day X = D − 7, days 0..7
COH_METS = ("cohortActiveUsers", "cohortTotalUsers")
COH_LIMIT = 10000
CTY_DAYS = 56
PAID_DAYS = 28
WEEKS = 13                          # M5: GA4 ÷ AdMob per Monday–Sunday week, the newest ending ≤ E − LATE
PAID_MIN = 10                       # M10: a day is compared when Google Ads reported ≥ 10 installs
AB = ((0, 0), (1, 6), (7, 29), (30, 89), (90, 364), (365, 10 ** 6))      # the design's ab / rb install-age bands
AB_NAMES = ("0", "1_6", "7_29", "30_89", "90_364", "365+")
KEEP_LAGS = (0, 1, 3, 7, 14, 30, 45, 60, 90, 120, 180, 270, 365)          # the design's ULAGS
RBANDS = ((0, 0), (1, 1), (2, 3), (4, 7), (8, 14), (15, 30), (31, 60), (61, 90), (91, 180), (181, 365))
CLAGS, CBANDS = (1, 3, 7, 14, 30), RBANDS[:8]
CSET_SLOTS = 27                     # the design's top 25 countries + "--" + "ZZ"
HOT_X_DAYS, HOT_C_DAYS = 400, 100   # the design's hot / old split
OTH_MAX = 0.02                      # the design's OTH_MAX: a day with ≥ 2% of its users in "(other)" is flagged
TIE = 0.03                          # M3 / cohort variants: a cell "holds" within 3% (or 1 user)
M3_BIG = 50                         # M3's "big" cells: ≥ 50 users in the one-day cell (the 1-user slack is < 3%)
MIN_USD = 20                        # M5: a week (a country: its 56 days) is judged only with ≥ $20 on BOTH sides —
MIN_WEEKS = 4                       # the design's k floor; an app's p50 is judged with ≥ 4 such weeks
ADD = 0.005                         # M4: Σ rows vs TOTAL within 0.5%
WORKERS = 4                         # properties in parallel — one request at a time per property
BUDGET_SEC = 22 * 60                # no new call after 22 min of the probe (the job's timeout is 45: setup, clone ≤ 8)
TICK_SEC = 20                       # a side thread checks the heartbeat this often
PAGE_ROWS = 100000
STATE_PATH = "data/ga4_uninstall/state.json"
OUT_PATH = "ga4/shape_probe.json"
DAY_KINDS = ("QB", "QA", "QA6", "QA90", "VER", "COH")
VARIANTS = ("COH_CTY", "COH_REV", "COH_CTY_REV", "COH_FILT", "BETWEEN", "IN200")
ONCE_KINDS = VARIANTS + ("CTY56", "PAID")
CORE = ("REF", "QB", "QA", "QA6", "QA90", "VER", "COH", "CTY56", "PAID")


# ── run, app ────────────────────────────────────────────────────────────────────────────────────

class Run(pr.Run):
    """The probe's clock / budget / call counter; its counts-only heartbeat says "shape progress"."""

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
            self.say("shape progress: calls %d, %ds" % (n, s))

    def tick(self):
        self.pulse(count=True)


class Beat:
    """`with Beat(run, every):` a daemon thread calls run.pulse() every `every` s (0: none), so the heartbeat also comes
    while every worker waits on a slow call."""

    def __init__(self, run, every=TICK_SEC):
        self.run, self.every, self.ev = run, every, threading.Event()
        self.th = threading.Thread(target=self._loop, daemon=True) if every else None

    def _loop(self):
        while not self.ev.wait(self.every):
            try:
                self.run.pulse()
            except Exception:
                pass

    def __enter__(self):
        if self.th:
            self.th.start()
        return self

    def __exit__(self, *exc):
        self.ev.set()
        if self.th:
            self.th.join(5)
        return False


def _left(q):
    b = ((q or {}).get("tokensPerDay") or {})
    return pr._int(b["remaining"]) if "remaining" in b else None


class App(pr.App):
    """ga4_d1d7_probe.App (stream-pinned, paged, returnPropertyQuota, the property's quota / 5xx / budget stops, calls
    and tokens per kind) + seconds per kind and the drop of tokensPerDay remaining across each call."""

    def __init__(self, token, property_id, stream_id, run, prop=None):
        super().__init__(token, property_id, stream_id, run, prop)
        self.sec, self.tok_delta, self.no_total = 0.0, 0, False

    def _post(self, method, body):
        before = _left(self.prop["quota"])
        t0 = time.perf_counter()
        try:
            j = super()._post(method, body)
        finally:
            dt = time.perf_counter() - t0
            self.sec += dt
            k = self.by_kind.get(self.kind)
            if k is not None:
                k["sec"] = round(k.get("sec", 0) + dt, 3)
        after = _left(j.get("propertyQuota"))
        if before is not None and after is not None and before >= after:
            self.tok_delta += before - after
        return j


def _measure(ga, kind, fetch, summarize, ix, key):
    """fetch() → rows (a GA4 error → {"err": its class}; a Stop is passed on), summarize(rows) → summary or (summary,
    index) — the index (kept in memory for the comparisons, never written) goes to ix[key]. + tok (tokensPerDay
    consumed), tok_delta, sec, calls. A bug in summarize costs that summary only: the call is spent."""
    ga.kind = kind
    t0, d0, s0, c0 = ga.tok, ga.tok_delta, ga.sec, ga.calls
    try:
        rows = fetch()
    except Stop:
        raise
    except Exception as e:
        out = {"err": pr._err(e)}
    else:
        got = _safely(summarize, rows, fallback={"rows": len(rows) if isinstance(rows, list) else None})
        if isinstance(got, tuple):
            out, ix[key] = got
        else:
            out = got
    out.update(tok=ga.tok - t0, tok_delta=ga.tok_delta - d0, sec=round(ga.sec - s0, 2), calls=ga.calls - c0)
    return out


# ── small helpers ───────────────────────────────────────────────────────────────────────────────

_ratio, _ymd = pr._ratio, pr._ymd


def _pct(v, q):
    v = sorted(x for x in v if isinstance(x, (int, float)))
    if not v:
        return None
    k = (len(v) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(v) - 1)
    return round(v[lo] + (v[hi] - v[lo]) * (k - lo), 4)


def _stats(v):
    v = [x for x in v if isinstance(x, (int, float))]
    if not v:
        return None
    return {"n": len(v), "p50": _pct(v, 0.5), "p90": _pct(v, 0.9), "max": round(max(v), 4),
            "mean": round(sum(v) / len(v), 4)}


def _dist(v):
    v = [x for x in v if isinstance(x, (int, float))]
    return {"n": len(v), "p10": _pct(v, 0.1), "p50": _pct(v, 0.5), "p90": _pct(v, 0.9)}


def _close(a, b, rel=TIE):
    return b is not None and a is not None and abs(a - b) <= max(1, rel * b)


def _band(lag):
    for (lo, hi), name in zip(AB, AB_NAMES):
        if lo <= lag <= hi:
            return name
    return None


def _flags(ga):
    return dict(pr._meta(ga), rows_total=ga.last_row_count, currency=(ga.last_meta or {}).get("currencyCode"))


def _real(c):
    return c not in ga4.NOT_SET


def _top_share(by, k):
    """{country: value} → (share of the k biggest real countries, how many real countries hold ≥ 1%)."""
    tot = sum(v for v in by.values() if v > 0)
    real = sorted((v for c, v in by.items() if _real(c) and v > 0), reverse=True)
    return _ratio(sum(real[:k]), tot), sum(1 for v in real if tot and v >= 0.01 * tot)


def _span(d, n):
    return [d - timedelta(days=i) for i in range(n)]


# ── the app list, the private data ──────────────────────────────────────────────────────────────

def units_from_state(state):
    """The build's GA4 apps, one per Android stream (ga4_d1d7_probe.apps_from_state), each with every AdMob app id the
    build fetches on that stream (app_ids) and its stores' history_start / window_end (the earliest / latest)."""
    state = state or {}
    routes = (state.get("routes") or {}).get("by_package") or {}
    fetch = state.get("fetch") or {}
    units = pr.apps_from_state(state)
    for u in units:
        ids, hs, we = [], [], []
        for aid, st in sorted(fetch.items()):
            st = st or {}
            r = routes.get(st.get("package")) or {}
            if (str(r.get("property_id")), str(r.get("stream_id"))) != (u["property_id"], u["stream_id"]):
                continue
            ids.append(aid)
            m = st.get("meta") or {}
            if m.get("history_start"):
                hs.append(str(m["history_start"])[:10])
            if m.get("window_end"):
                we.append(str(m["window_end"])[:10])
        u["app_ids"] = ids or [u["app_id"]]
        u["history_start"] = min(hs) if hs else None
        u["window_end"] = max(we) if we else None
    return units


def load_state(data_dir):
    """The build's GA4 state: from the job's read-only clone when there is one, else the private repo's contents API."""
    p = os.path.join(data_dir, STATE_PATH) if data_dir else ""
    if p and os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return _private_json(STATE_PATH)


def _json_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_admob(data_dir, units, now=None, env=None):
    """The clone's AdMob / Google Ads data for the GA4 streams → {"state": "ok", "tz_src", "currency", "till", "apps":
    {package: {"ids": n AdMob apps, "rev": uninstall_build.app_revenue (network days + every-source all_days) or None,
    "cty": {AdMob day: {country: micros}} (the last ~11 weeks), "ads_installs": {day: Google Ads installs}}}};
    {"state": "absent"} without a clone. The big files are read one at a time and dropped once summed."""
    if not data_dir or not os.path.isdir(os.path.join(data_dir, "data")):
        return {"state": "absent"}
    from zoneinfo import ZoneInfo
    from admob_iq.build_static import admob_revenue, mediation_revenue
    from admob_iq.db import FileRepo, _read_json_any
    from admob_iq.uninstall_build import app_revenue
    env = env or {}
    dd = os.path.join(data_dir, "data")
    dash = _read_json_any(os.path.join(data_dir, "site", "dashboard.json")) or {}
    tz, src = str(dash.get("report_tz") or ""), "dashboard"
    if not tz:
        tz, src = str(env.get("SHAPE_ADMOB_TZ") or ""), "env"
    cur = str(dash.get("currency") or "USD")
    del dash
    try:
        zone = ZoneInfo(tz) if tz else None
    except Exception:
        zone = None
    if zone is None:
        tz, src = "UTC", "none"                       # unknown: AdMob days read as UTC days (weekly ratios still hold)
        zone = ZoneInfo("UTC")
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(zone).date()
    by_id = ((_json_file(os.path.join(dd, "app_store_ids.json")) or {}).get("by_id")) or {}
    ids, pkg_of = {}, {}
    for u in units:
        s = list(u.get("app_ids") or [u["app_id"]])
        s += sorted(a for a, p in by_id.items() if str(p or "").strip() == u["package"] and a not in s)
        ids[u["package"]] = s
        for a in s:
            pkg_of.setdefault(a, u["package"])
    revenue = admob_revenue(FileRepo(dd).fetch_network(), tz, cur, today)
    every = mediation_revenue(FileRepo(dd).fetch_mediation(), revenue["till"])
    if every:
        revenue["all_apps"] = every
    apps = {}
    for pkg, s in ids.items():
        r = app_revenue(revenue, {"app_id": s[0], "package": pkg},
                        [{"app_id": x, "same_pkg": pkg} for x in s[1:]], pkg)
        apps[pkg] = {"ids": len(s), "rev": r, "cty": {}, "ads_installs": {}}
    till = revenue["till"]
    del revenue, every
    cut = (today - timedelta(days=CTY_DAYS + 21)).isoformat()
    for r in FileRepo(dd).fetch_country():
        pkg, d = pkg_of.get(r.get("app_id")), str(r.get("report_date") or "")[:10]
        if not pkg or d < cut:
            continue
        c = apps[pkg]["cty"].setdefault(d, {})
        cc = str(r.get("country") or "")
        c[cc] = c.get(cc, 0) + int(r.get("estimated_earnings_micros") or 0)
    inst = (_json_file(os.path.join(dd, "roas_spend_cache.json")) or {}).get("installs") or {}
    for pkg, a in apps.items():
        a["ads_installs"] = {d: v for d, v in (inst.get(pkg) or {}).items() if str(d) >= cut}
    return {"state": "ok", "tz_src": src, "currency": cur, "till": till, "apps": apps}


def admob_matched(adm):
    return sum(1 for a in ((adm or {}).get("apps") or {}).values() if a.get("rev"))


# ── the requests ────────────────────────────────────────────────────────────────────────────────

def split_body(d, dims):
    """ONE activity day d, `dims` — the design's Q-A / Q-B shape (report_all adds limit / offset / a total order, Ga4App
    the Android + stream filter and returnPropertyQuota; the metrics come from split_report)."""
    return {"dateRanges": [gu._rng(d, d)], "dimensions": ga4._dim(*dims), "currencyCode": "USD",
            "metricAggregations": ["TOTAL"], "keepEmptyRows": False}


def split_report(ga, body, extra=None, mets=METS, fallback=True):
    """report_all with METS; a 400 → ONCE more without totalRevenue (the design's no_total), and every later split of
    this app asks that. fallback=False (a request whose filter may be what GA4 refuses): no retry."""
    if ga.no_total and mets == METS:
        mets = METS_NO_TOTAL
    try:
        return ga.report_all(dict(body, metrics=ga4._dim(*mets)), extra=extra, page_rows=PAGE_ROWS)
    except RuntimeError as e:
        if not fallback or mets != METS or not str(e).startswith("HTTP 400"):
            raise
    rows = ga.report_all(dict(body, metrics=ga4._dim(*METS_NO_TOTAL)), extra=extra, page_rows=PAGE_ROWS)
    ga.no_total = True
    return rows


def ref_report(ga, start, end):
    body = {"dateRanges": [gu._rng(start, end)], "dimensions": ga4._dim("date"), "currencyCode": "USD"}
    for i, mets in enumerate((REF_METS,) + REF_FALLBACK):
        try:
            return ga.report_all(dict(body, metrics=ga4._dim(*mets)), page_rows=PAGE_ROWS)
        except RuntimeError as e:
            if i == len(REF_FALLBACK) or not str(e).startswith("HTTP 400"):
                raise


def in_list(days):
    return [ga4._in_list("firstSessionDate", [_ymd(x) for x in days])]


def between(lo, hi):
    return [{"filter": {"fieldName": "firstSessionDate",
                        "betweenFilter": {"fromValue": {"int64Value": _ymd(lo)}, "toValue": {"int64Value": _ymd(hi)}}}}]


def coh_body(xs, end_offset, dims=(), mets=COH_METS):
    """cohortSpec: one DAILY single-day cohort per install day X in xs [(L, X)], days 0 .. end_offset, no top-level
    dateRanges (fetch_ret's shape) [+ dims]."""
    b = {"dimensions": ga4._dim("cohort", "cohortNthDay", *dims), "metrics": ga4._dim(*mets),
         "cohortSpec": {"cohorts": [{"name": "c" + _ymd(x), "dimension": "firstSessionDate", "dateRange": gu._rng(x, x)}
                                    for _, x in xs],
                        "cohortsRange": {"granularity": "DAILY", "startOffset": 0, "endOffset": end_offset}},
         "limit": COH_LIMIT}
    if "totalAdRevenue" in mets:
        b["currencyCode"] = "USD"
    return b


def coh_fetch(ga, xs, hold):
    """COH: every lag in one request; a 400 (the long endOffset refused) → once more with lags ≤ COH_SHORT."""
    end = max(L for L, _ in xs)
    hold.update(xs=xs, end=end)
    try:
        return ga.report(coh_body(xs, end))
    except RuntimeError as e:
        short = [(L, x) for L, x in xs if L <= COH_SHORT]
        if not str(e).startswith("HTTP 400") or end <= COH_SHORT or not short:
            raise
        hold.update(xs=short, end=max(L for L, _ in short), long_err=pr._err(e))
    return ga.report(coh_body(hold["xs"], hold["end"]))


def cty_body(end):
    return {"dateRanges": [gu._rng(end - timedelta(days=CTY_DAYS - 1), end)],
            "dimensions": ga4._dim("date", "countryId"), "metrics": ga4._dim("activeUsers", "totalAdRevenue"),
            "currencyCode": "USD"}


def paid_body(end):
    return {"dateRanges": [gu._rng(end - timedelta(days=PAID_DAYS - 1), end)],
            "dimensions": ga4._dim("date", "firstUserGoogleAdsCampaignId"),
            "metrics": ga4._dim("newUsers", "activeUsers")}


# ── the summaries (each → summary, in-memory index) ─────────────────────────────────────────────

def ref_sum(rows, ga, start):
    idx = {}
    for r in rows:
        d = ga4._d(r.get("date"))
        if d:
            idx[d] = {SHORT[m]: r.get(m) or 0 for m in REF_METS if m in r}
    active = sorted(d for d, v in idx.items() if v.get("act") or v.get("new"))
    mets = sorted({k for v in idx.values() for k in v})
    return dict(_flags(ga), rows=len(rows), pages=ga.last_pages, days=len(idx), mets=mets,
                first=active[0].isoformat() if active else None, capped=bool(active) and active[0] <= start), idx


def split(rows, d, ga, refd, country=False):
    """One activity day's split (QB: dims [firstSessionDate]; QA & co: [countryId, firstSessionDate]) → the self-check
    and shape: sums vs the TOTAL row (M4) and vs the day's REF totals (cov, ncov = new users on install day D ÷ the
    day's, rcov / tcov revenue), "(other)" / "(not set)" rows and their user / revenue share (M2), users and revenue by
    install age band, and for countries how concentrated installs / revenue are (CSET sizing) and how many (country,
    install day) cells a fold would keep (M12). Index: cells {install day: [act, new, ad, tot]} (Σ countries), cc
    {(country, install day): [act, ad, new]}, top_cc (the most installs on D)."""
    s = dict.fromkeys(("act", "new", "ad", "tot"), 0)
    oth, nos = [0, 0, 0], [0, 0, 0]
    ab, rb = dict.fromkeys(AB_NAMES, 0), dict.fromkeys(AB_NAMES, 0)
    cells, cc, inst, crev = {}, {}, {}, {}
    new_row = new_else = le365 = le90 = cty_ns = 0
    max_lag = None
    for r in rows:
        v = [r.get(m) or 0 for m in METS]
        for k, x in zip(("act", "new", "ad", "tot"), v):
            s[k] = (s[k] or 0) + x
        f = str(r.get("firstSessionDate") or "")
        c = str(r.get("countryId") or "") if country else ""
        if "(other)" in (f, c):
            oth[0], oth[1], oth[2] = oth[0] + 1, oth[1] + v[0], oth[2] + v[2]
        fd = ga4._d(f)
        if fd is None:
            if f != "(other)":
                nos[0], nos[1], nos[2] = nos[0] + 1, nos[1] + v[0], nos[2] + v[2]
        else:
            lag = (d - fd).days
            b = _band(lag)
            if b:
                ab[b] += v[0]
                rb[b] += v[2]
            max_lag = lag if max_lag is None else max(max_lag, lag)
            key = fd.isoformat()
            cell = cells.setdefault(key, [0, 0, 0, 0])
            for i in range(4):
                cell[i] += v[i]
            if country:
                e = cc.setdefault((c, key), [0, 0, 0])
                e[0], e[1], e[2] = e[0] + v[0], e[1] + v[2], e[2] + v[1]
                if 0 <= lag <= 365 and (v[0] or v[2]):
                    le365 += 1
                    le90 += lag <= 90
        if fd == d:
            new_row += v[1]
        else:
            new_else += v[1]
        if country:
            if c != "(other)" and not _real(c):
                cty_ns += v[0]
            if fd == d:
                inst[c] = inst.get(c, 0) + v[1]
            crev[c] = crev.get(c, 0) + v[2]
    if rows and "totalRevenue" not in rows[0]:
        s["tot"] = None                               # not asked (no_total): unknown, never 0
    tot = {SHORT[m]: v for m, v in pr._totals(ga).items() if m in SHORT}
    ref = refd or {}
    out = dict(_flags(ga), rows=len(rows), pages=ga.last_pages, mets="no_total" if ga.no_total else "all",
               sum={k: (round(v, 6) if isinstance(v, float) else v) for k, v in s.items()},
               total={k: (round(v, 6) if isinstance(v, float) else v) for k, v in tot.items()},
               add={k: _ratio(s[k], tot[k]) for k in s if tot.get(k)},
               ref={k: ref.get(k) for k in ("act", "new", "ad", "tot")} if refd else None,
               cov=_ratio(s["act"], ref.get("act")), ncov=_ratio(new_row, ref.get("new")),
               rcov=_ratio(s["ad"], ref.get("ad")), tcov=_ratio(s["tot"], ref.get("tot")),
               new_row=new_row, new_else=new_else,
               other={"rows": oth[0], "act_share": _ratio(oth[1], s["act"]), "ad_share": _ratio(oth[2], s["ad"])},
               not_set={"rows": nos[0], "act_share": _ratio(nos[1], s["act"]), "ad_share": _ratio(nos[2], s["ad"])},
               ab={k: _ratio(v, s["act"]) for k, v in ab.items()}, rb={k: _ratio(v, s["ad"]) for k, v in rb.items()},
               fsd_days=len(cells), max_lag=max_lag)
    top = None
    if country:
        ti, ni = _top_share(inst, 25)
        tr, nr = _top_share(crev, 25)
        real = [c for c in inst if _real(c) and inst[c] > 0]
        top = max(real, key=lambda c: (inst[c], c)) if real else None
        out.update(countries=len({c for c, _ in cc if _real(c)}), cty_not_set_share=_ratio(cty_ns, s["act"]),
                   inst_countries=len(real), top25_inst=ti, ge1pct_inst=ni, top25_rev=tr, ge1pct_rev=nr,
                   cells_le365=le365, cells_le90=le90)
    return out, {"cells": cells, "cc": cc, "top_cc": top}


def ver_sum(rows, d, ga):
    """VER (e): versions seen, and among D's new users (install day D) how many versions and the biggest one's share —
    the design's C groups install days by a version holding ≥ 80% of the day's new users."""
    vers, fsd, new_by, oth = set(), set(), {}, [0, 0]
    act = 0
    for r in rows:
        v, f = str(r.get("appVersion") or ""), str(r.get("firstSessionDate") or "")
        a = r.get("activeUsers") or 0
        act += a
        if _real(v):
            vers.add(v)
        fsd.add(f)
        if "(other)" in (v, f):
            oth[0], oth[1] = oth[0] + 1, oth[1] + a
        if ga4._d(f) == d:
            new_by[v] = new_by.get(v, 0) + (r.get("newUsers") or 0)
    n = sum(new_by.values())
    real = {v: x for v, x in new_by.items() if _real(v)}
    dom = max(real.values()) if real else 0
    return dict(_flags(ga), rows=len(rows), pages=ga.last_pages, versions=len(vers), fsd_days=len(fsd), new=n,
                new_versions=sum(1 for x in real.values() if x), dominant_share=_ratio(dom, n),
                dominant_ge80=bool(n) and dom >= 0.8 * n, new_not_set_share=_ratio(n - sum(real.values()), n),
                other={"rows": oth[0], "act_share": _ratio(oth[1], act)})


def coh_parse(rows):
    """cohort rows → {cohort name: {"t": {country or "": cohortTotalUsers}, "T": Σ t, "a": {nth day: active users},
    "rev": {nth day: totalAdRevenue}, "cc": {country: {nth day: active users}}}}."""
    out = {}
    for r in rows:
        try:
            n = int(str(r.get("cohortNthDay")))
        except (TypeError, ValueError):
            continue
        c = out.setdefault(str(r.get("cohort") or ""), {"t": {}, "a": {}, "rev": {}, "cc": {}})
        cc = str(r.get("countryId") or "") if "countryId" in r else ""
        c["t"][cc] = max(c["t"].get(cc, 0), r.get("cohortTotalUsers") or 0)
        a = r.get("cohortActiveUsers") or 0
        c["a"][n] = c["a"].get(n, 0) + a
        if "totalAdRevenue" in r:
            c["rev"][n] = c["rev"].get(n, 0) + (r.get("totalAdRevenue") or 0)
        if cc:
            e = c["cc"].setdefault(cc, {})
            e[n] = e.get(n, 0) + a
    for c in out.values():
        c["T"] = sum(c["t"].values())
    return out


def coh_sum(rows, ga, hold):
    p = coh_parse(rows)
    out = dict(_flags(ga), rows=len(rows), pages=1, truncated=bool(ga.last_row_count and ga.last_row_count > len(rows)),
               cohorts=len(hold.get("xs") or []), cohorts_back=len(p), end_offset=hold.get("end"),
               lags=[L for L, _ in hold.get("xs") or []])
    if hold.get("long_err"):
        out["long_err"] = hold["long_err"]
    return out, {"p": p, "xs": list(hold.get("xs") or [])}


def cty_sum(rows, ga):
    idx, oth, days = {}, [0, 0], set()
    for r in rows:
        d, c = ga4._d(r.get("date")), str(r.get("countryId") or "")
        a, ad = r.get("activeUsers") or 0, r.get("totalAdRevenue") or 0
        if c == "(other)":
            oth[0], oth[1] = oth[0] + 1, oth[1] + ad
        if d is None:
            continue
        days.add(d)
        e = idx.setdefault(c, {}).setdefault(d.isoformat(), [0, 0])
        e[0], e[1] = e[0] + a, e[1] + ad
    tot = sum(v[1] for e in idx.values() for v in e.values())
    return dict(_flags(ga), rows=len(rows), pages=ga.last_pages, days=len(days),
                countries=sum(1 for c in idx if _real(c)),
                other={"rows": oth[0], "ad_share": _ratio(oth[1], tot)}), idx


def paid_sum(rows, ga):
    idx, camps = {}, set()
    for r in rows:
        d, c = ga4._d(r.get("date")), str(r.get("firstUserGoogleAdsCampaignId") or "")
        if d is None:
            continue
        n = r.get("newUsers") or 0
        e = idx.setdefault(d.isoformat(), [0, 0])
        e[1] += n
        if _real(c):
            e[0] += n
            camps.add(c)
    ads, alln = sum(e[0] for e in idx.values()), sum(e[1] for e in idx.values())
    return dict(_flags(ga), rows=len(rows), pages=ga.last_pages, days=len(idx), campaigns=len(camps), new=alln,
                new_ads=ads, ads_share=_ratio(ads, alln)), idx


# ── comparisons (after an app's reads) ──────────────────────────────────────────────────────────

def vs_cells(a, b, d):
    """QA's cells (Σ countries) vs QB's, install days D − L for the design's lags → users / revenue ratios."""
    by, da, dr = {}, [], []
    for L in KEEP_LAGS:
        k = (d - timedelta(days=L)).isoformat()
        y = b.get(k)
        if not y or not (y[0] or y[2]):
            continue
        x = a.get(k) or [0, 0, 0, 0]
        ra, rr = _ratio(x[0], y[0]), _ratio(x[2], y[2])
        by[str(L)] = [ra, rr]
        if ra is not None:
            da.append(abs(ra - 1))
        if rr is not None:
            dr.append(abs(rr - 1))
    return {"n": len(by), "act_within_1pct": sum(1 for x in da if x <= 0.01),
            "ad_within_1pct": sum(1 for x in dr if x <= 0.01), "act_dev_med": pr._median(da),
            "ad_dev_med": pr._median(dr), "by_lag": by}


def vs_sub(sub, qa, fset):
    """A filtered read's (country, install day) cells vs QA's cells of the same install days → how many are equal
    (users within 1% or 1, revenue within 1%), only in one of them ("(other)" in QA shows up here), Σ ratios."""
    keys = {k for k in qa if k[1] in fset} | set(sub)
    eq = only_s = only_q = 0
    ss, sq = [0, 0.0], [0, 0.0]
    for k in keys:
        x, y = sub.get(k), qa.get(k) if k[1] in fset else None
        if x:
            ss[0], ss[1] = ss[0] + x[0], ss[1] + x[1]
        if y:
            sq[0], sq[1] = sq[0] + y[0], sq[1] + y[1]
        if x is None:
            only_q += 1
        elif y is None:
            only_s += 1
        elif abs(x[0] - y[0]) <= max(1, 0.01 * y[0]) and abs(x[1] - y[1]) <= max(1e-6, 0.01 * abs(y[1])):
            eq += 1
    return {"cells": len(keys), "equal": eq, "equal_share": _ratio(eq, len(keys)), "only_sub": only_s,
            "only_qa": only_q, "act": _ratio(ss[0], sq[0]), "ad": _ratio(ss[1], sq[1])}


def coh_cells(cix, qb, qa, ref):
    """M3: per cohort X = D − L, its active users on day L (= D) vs the QB / QA cell of install day X on D, and its
    cohortTotalUsers ÷ newUsers of X (REF)."""
    out = []
    for L, x in cix.get("xs") or []:
        c = (cix.get("p") or {}).get("c" + _ymd(x)) or {}
        a = (c.get("a") or {}).get(L, 0)
        k = x.isoformat()
        vb = (qb.get(k) or [0])[0] if qb is not None else None
        vq = (qa.get(k) or [0])[0] if qa is not None else None
        out.append({"L": L, "x": k, "t": c.get("T", 0), "a": a, "qb": vb, "qa": vq, "r_qb": _ratio(a, vb),
                    "r_qa": _ratio(a, vq), "t_new": _ratio(c.get("T"), (ref.get(x) or {}).get("new"))})
    return out


def _ok(rec):
    return isinstance(rec, dict) and "err" not in rec


def compare_day(rec, dix, ref):
    d = gu._d(rec["d"])
    qb, qa = dix.get("QB"), dix.get("QA")
    if _ok(rec.get("QA")) and qb and qa:
        rec["QA"]["vs_QB"] = vs_cells(qa["cells"], qb["cells"], d)
    for k, days in (("QA6", [d - timedelta(days=L) for L in LIST_LAGS]), ("QA90", _span(d, LIST90))):
        if _ok(rec.get(k)) and k in dix and qa:
            rec[k]["vs_QA"] = vs_sub(dix[k]["cc"], qa["cc"], {x.isoformat() for x in days})
            if _ok(rec.get("QA")):
                rec[k]["tok_vs_QA"] = _ratio(rec[k]["tok"], rec["QA"]["tok"])
                rec[k]["rows_vs_QA"] = _ratio(rec[k]["rows"], rec["QA"]["rows"])
    if _ok(rec.get("COH")) and "COH" in dix:
        rec["COH"]["cells"] = coh_cells(dix["COH"], (qb or {}).get("cells"), (qa or {}).get("cells"), ref)


def compare_once(o, oix, dix, d, qa_rec):
    """The cohort variants vs COH (same install day X = D − 7) and QA (country cells of X on D); BETWEEN / IN200 vs
    QA."""
    x = d - timedelta(days=COH_X_LAG)
    k, name = x.isoformat(), "c" + _ymd(x)
    base = ((dix.get("COH") or {}).get("p") or {}).get(name) or {}
    b7, bT = (base.get("a") or {}).get(7), base.get("T")
    qa_cc = (dix.get("QA") or {}).get("cc") or {}
    qb = (dix.get("QB") or {}).get("cells") or {}

    def got(kind):
        return ((oix.get(kind) or {}).get("p") or {}).get(name) if _ok(o.get(kind)) else None
    c = got("COH_CTY")
    if c is not None:
        per = {cc: e.get(7, 0) for cc, e in (c.get("cc") or {}).items()}
        top = sorted(per, key=lambda z: (-per[z], z))[:10]
        held = sum(1 for cc in top if _close(per[cc], (qa_cc.get((cc, k)) or [None])[0]))
        o["COH_CTY"].update(countries=len(per), a7_vs_coh=_ratio(sum(per.values()), b7),
                            t_vs_coh=_ratio(c.get("T"), bT), top10=len(top), top10_within_3pct=held)
    c = got("COH_REV")
    rev7 = None
    if c is not None:
        rev7 = (c.get("rev") or {}).get(7)
        o["COH_REV"].update(rev_days=len(c.get("rev") or {}), rev7=None if rev7 is None else round(rev7, 6),
                            rev7_vs_qb=_ratio(rev7, (qb.get(k) or [0, 0, 0])[2]),
                            a7_vs_coh=_ratio((c.get("a") or {}).get(7), b7))
    c = got("COH_CTY_REV")
    if c is not None:
        r7 = (c.get("rev") or {}).get(7)
        o["COH_CTY_REV"].update(countries=len(c.get("cc") or {}), rev7_vs_coh_rev=_ratio(r7, rev7),
                                a7_vs_coh=_ratio((c.get("a") or {}).get(7), b7))
    c = got("COH_FILT")
    if c is not None:
        top = (dix.get("QA") or {}).get("top_cc")
        o["COH_FILT"].update(t=c.get("T"), a7=(c.get("a") or {}).get(7),
                             a7_vs_qa=_ratio((c.get("a") or {}).get(7), (qa_cc.get((top, k)) or [0])[0]))
    for kind, n in (("BETWEEN", LIST90), ("IN200", LIST_BIG)):
        if _ok(o.get(kind)) and kind in oix and qa_cc:
            o[kind]["vs_QA"] = vs_sub(oix[kind]["cc"], qa_cc, {x.isoformat() for x in _span(d, n)})
            if _ok(qa_rec):
                o[kind]["tok_vs_QA"] = _ratio(o[kind]["tok"], qa_rec["tok"])
                o[kind]["rows_vs_QA"] = _ratio(o[kind]["rows"], qa_rec["rows"])


def admob_compare(res, ix, adm_app, tz_g, end):
    """M5 / M7 / M10: GA4 vs AdMob on each probed day (QB's Σ totalAdRevenue / totalRevenue vs AdMob network and every
    source, blended onto GA4 days as the build does), per Monday–Sunday week (REF), per top-10 country over 56 days
    (CTY56 vs country.json); the IAP share (REF, 90 days); GA4 new users from a Google Ads campaign vs Google Ads
    installs (PAID vs roas_spend_cache)."""
    ref, oix = ix.get("REF") or {}, ix.get("once") or {}
    out = {}
    last90 = _span(end, 90)
    ad90 = sum((ref.get(d) or {}).get("ad", 0) for d in last90)
    tot90 = sum((ref.get(d) or {}).get("tot", 0) for d in last90)
    out["iap"] = {"days": sum(1 for d in last90 if d in ref), "ad": round(ad90, 2), "tot": round(tot90, 2),
                  "share": _ratio(tot90 - ad90, tot90) if any("tot" in (ref.get(d) or {}) for d in last90) else None}
    rev = (adm_app or {}).get("rev")
    if not rev:
        out["state"] = "no_admob"
    else:
        out["state"] = "ok"
        fn_n, _ = imp._revenue_fn({"tz": rev.get("tz"), "till": rev.get("till"), "days": rev.get("days") or {}}, tz_g)
        fn_a = imp._revenue_fn({"tz": rev.get("tz"), "till": rev.get("till"), "days": rev.get("all_days") or {}},
                               tz_g)[0] if rev.get("all_days") else None

        def at(fn, d):
            return fn(d) if fn else None
        days = {}
        for slot, rec in (res.get("days") or {}).items():
            d = gu._d(rec["d"])
            s = (rec.get("QB") or {}).get("sum") or {}
            n, a = at(fn_n, d), at(fn_a, d)
            n, a = n and n[0], a and a[0]
            days[slot] = {"d": rec["d"], "ga4_ad": s.get("ad"), "ga4_tot": s.get("tot"),
                          "ref_ad": (ref.get(d) or {}).get("ad"), "admob_net": None if n is None else round(n, 6),
                          "admob_all": None if a is None else round(a, 6),
                          "r_tot_net": _ratio(s.get("tot"), n), "r_ad_net": _ratio(s.get("ad"), n),
                          "r_ad_all": _ratio(s.get("ad"), a), "r_tot_all": _ratio(s.get("tot"), a)}
        out["days"] = days
        sun = end - timedelta(days=LATE)
        sun -= timedelta(days=(sun.weekday() + 1) % 7)
        weeks = []
        for w in range(WEEKS):
            ds = _span(sun - timedelta(days=7 * w), 7)
            if not all(d in ref for d in ds):
                continue
            g = sum(ref[d].get("ad", 0) for d in ds)
            gi = sum(ref[d].get("imp", 0) for d in ds)
            vn, va = [at(fn_n, d) for d in ds], [at(fn_a, d) for d in ds]
            n = sum(v[0] for v in vn) if all(v is not None for v in vn) else None
            a = sum(v[0] for v in va) if va and all(v is not None for v in va) else None
            ai = sum(v[1] for v in va) if a is not None else None
            weeks.append({"from": ds[-1].isoformat(), "ga4_ad": round(g, 4),
                          "admob_net": None if n is None else round(n, 4),
                          "admob_all": None if a is None else round(a, 4), "r_net": _ratio(g, n), "r_all": _ratio(g, a),
                          "r_imp_all": _ratio(gi, ai) if gi else None})
        out["weeks"] = weeks
        out["r_all"] = _dist([w["r_all"] for w in weeks])
        out["r_net"] = _dist([w["r_net"] for w in weeks])
        # the design's k is only computed with ≥ $20 on both sides: a small app's cents-a-week ratios are noise
        out["r_all_20"] = _dist([w["r_all"] for w in weeks
                                 if w["ga4_ad"] >= MIN_USD and (w["admob_all"] or 0) >= MIN_USD])
    cty, cix = (adm_app or {}).get("cty") or {}, oix.get("CTY56")
    if cty and cix is not None:
        days = [d.isoformat() for d in _span(end, CTY_DAYS) if d.isoformat() in cty]
        A, G = {}, {}
        for d in days:
            for cc, m in cty[d].items():
                A[cc] = A.get(cc, 0) + m / 1e6
        for cc, e in cix.items():
            G[cc] = sum((e.get(d) or [0, 0])[1] for d in days)
        ta, tg = sum(A.values()), sum(G.values())
        top = sorted(A, key=lambda c: (-A[c], c))[:10]
        rows = []
        for cc in top:
            wk = []
            for w in range(len(days) // 7):
                blk = days[7 * w:7 * w + 7]
                wk.append(_ratio(sum((cix.get(cc, {}).get(d) or [0, 0])[1] for d in blk),
                                 sum(cty[d].get(cc, 0) for d in blk) / 1e6))
            rows.append({"cc": cc, "admob_share": _ratio(A[cc], ta), "r": _ratio(G.get(cc, 0), A[cc]),
                         "r_weeks_p50": _pct(wk, 0.5), "weeks": sum(1 for x in wk if x is not None),
                         "usd_ok": A[cc] >= MIN_USD and G.get(cc, 0) >= MIN_USD})
        out["cty"] = {"days": len(days), "r_total": _ratio(tg, ta), "top10_share": _ratio(sum(A[c] for c in top), ta),
                      "ga4_only_share": _ratio(sum(v for c, v in G.items() if c not in A), tg), "top": rows}
    inst, pix = (adm_app or {}).get("ads_installs") or {}, oix.get("PAID")
    if pix is not None and inst:
        ds = sorted(d for d in pix if (inst.get(d) or 0) >= PAID_MIN)
        out["paid"] = {"days": len(ds), "ratio_p50": _pct([_ratio(pix[d][0], inst[d]) for d in ds], 0.5),
                       "ratio_sum": _ratio(sum(pix[d][0] for d in ds), sum(inst[d] for d in ds)),
                       "ads_share": _ratio(sum(e[0] for e in pix.values()), sum(e[1] for e in pix.values()))}
    return out


def size_estimate(hist_days, qb_ix, qa_ix, qb_rec, d, seed=7):
    """M12 (an ESTIMATE): the design's iday file for `hist_days` install days (x: users at ULAGS, revenue / IAP micros
    in RBANDS; c: per install week × up to 27 country slots; days: the ledger) filled with this app's own recent-day
    magnitudes, each number jittered ±30% (identical entries would compress unrealistically well), split hot / old as
    the design does, JSON and gzip as write_json_gz_stable → gz bytes."""
    rnd = random.Random(seed)

    def j(v):
        return int(v * (0.7 + 0.6 * rnd.random())) if v else 0
    cells = qb_ix.get("cells") or {}

    def lag(L, i):
        c = cells.get((d - timedelta(days=L)).isoformat())
        return c[i] if c else 0

    def band(lo, hi, f):
        return sum(f(L) for L in range(lo, hi + 1))
    u = [lag(L, 0) for L in KEEP_LAGS]
    r = [int(band(lo, hi, lambda L: lag(L, 2)) * 1e6) for lo, hi in RBANDS]
    p = [int(band(lo, hi, lambda L: max(0, lag(L, 3) - lag(L, 2))) * 1e6) for lo, hi in RBANDS]
    n = lag(0, 1)
    cc = (qa_ix or {}).get("cc") or {}
    per = {}
    for (c, k), v in cc.items():
        e = per.setdefault(c, {})
        e[k] = v
    inst = {c: (e.get(d.isoformat()) or [0, 0, 0])[2] for c, e in per.items()}
    slots = sorted(per, key=lambda c: (-inst[c], -sum(v[0] for v in per[c].values()), c))[:CSET_SLOTS]

    def cl(c, L, i):
        return (per[c].get((d - timedelta(days=L)).isoformat()) or [0, 0, 0])[i]
    cslot = {c: {"n": 7 * inst[c], "u": [7 * cl(c, L, 0) for L in CLAGS],
                 "r": [int(7 * band(lo, hi, lambda L: cl(c, L, 1)) * 1e6) for lo, hi in CBANDS]} for c in slots}
    s = qb_rec.get("sum") or {}
    act, ad, tot = s.get("act") or 0, int((s.get("ad") or 0) * 1e6), int((s.get("tot") or 0) * 1e6)
    abv = [int(act * ((qb_rec.get("ab") or {}).get(b) or 0)) for b in AB_NAMES]
    rbv = [int(ad * ((qb_rec.get("rb") or {}).get(b) or 0)) for b in AB_NAMES]
    crv = sorted((sum(v[1] for v in per[c].values()) for c in slots), reverse=True)

    def x_entry():
        return {"n": j(n), "u": [j(v) for v in u], "r": [j(v) for v in r], "p": [j(v) for v in p]}

    def c_entry():
        return {str(i): {"n": j(e["n"]), "u": [j(v) for v in e["u"]], "r": [j(v) for v in e["r"]]}
                for i, e in enumerate(cslot[c] for c in slots) if e["n"] or any(e["u"]) or any(e["r"])}

    def ledger():
        return {"st": "ok", "tries": 0, "at": "2026-01-01T00:00:00+00:00", "a": j(act), "n": j(n), "rev": j(ad),
                "tot": j(tot), "cov": round(0.97 + 0.04 * rnd.random(), 4),
                "ncov": round(0.97 + 0.04 * rnd.random(), 4), "oth": 0.0, "oth_rev": 0.0, "loss": False, "smp": False,
                "thr": False, "rows": j(qb_rec.get("rows") or 0), "tok": j(5),
                "cr": {str(i): j(int(v * 1e6)) for i, v in enumerate(crv)}, "ab": [j(v) for v in abv],
                "rb": [j(v) for v in rbv], "chk": None}
    head = {"v": 1, "src": ["p", "s"], "tz": "Etc/GMT", "cur": "USD", "cset": ["C%d" % i for i in range(len(slots))]}
    hot, old = dict(head, x={}, c={}, days={}), dict(head, x={}, c={}, days={})
    cut_x, cut_c = d - timedelta(days=HOT_X_DAYS), d - timedelta(days=HOT_C_DAYS)
    days = _span(d, max(0, hist_days))
    for day in days:
        t = hot if day >= cut_x else old
        t["x"][day.isoformat()] = x_entry()
        t["days"][day.isoformat()] = ledger()
    for m in sorted({day - timedelta(days=day.weekday()) for day in days}):
        (hot if m + timedelta(days=6) >= cut_c else old)["c"][m.isoformat()] = c_entry()

    def gz(obj):
        raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return len(gzip.compress(raw, compresslevel=9, mtime=0))
    return {"hist_days": hist_days, "slots": len(slots), "weeks": len(hot["c"]) + len(old["c"]),
            "hot_gz": gz(hot), "old_gz": gz(old) if old["x"] or old["c"] else 0,
            "per_x_numbers": 1 + len(u) + 2 * len(r)}



# ── one app ─────────────────────────────────────────────────────────────────────────────────────

def pick_slots(today, end, first):
    """→ [(slot name, activity day D)]: recent = E − LATE, then today − 100 / − 400, each only when ≥ the first day."""
    out = []
    if first is None:
        return out
    for name, age in SLOTS:
        d = end - timedelta(days=LATE) if age is None else today - timedelta(days=age)
        if d <= end - timedelta(days=LATE) and d >= first:
            out.append((name, d))
    return out


def _first(ref_rec, u):
    """The app's first data day: REF's first active day when REF reaches back further than the app, else the stores'
    history_start (state), else REF's start."""
    rf = gu._d(ref_rec["first"]) if _ok(ref_rec) and ref_rec.get("first") else None
    hs = gu._d(u["history_start"]) if u.get("history_start") else None
    if rf and not ref_rec.get("capped"):
        return rf
    return hs or rf


def admin_meta(token, pid):
    try:
        return ga4.property_meta(token, pid)
    except Exception as e:
        return {"err": pr._err(e)}


def probe_app(run, u, token, now, prop, adm_app):
    """Every measurement of one app (unit) → its result dict. Never raises for GA4 errors; a Stop ends the app."""
    today = ga4.window_end_in(u["tz"], now, lag=0)
    end = ga4.window_end_in(u["tz"], now)
    res = {"app_id": u["app_id"], "app_ids": u.get("app_ids") or [u["app_id"]], "property_id": u["property_id"],
           "stream_id": u["stream_id"], "owner": u.get("owner"), "tz": u["tz"], "today": today.isoformat(),
           "end": end.isoformat(), "history_start": u.get("history_start"), "days": {}, "once": {}}
    if not token:
        res["err"] = {"type": "auth"}
        return res
    ga = App(token, u["property_id"], u["stream_id"], run, prop)
    ix = {"days": {}, "once": {}}
    try:
        why = ga.stop or run.over()
        if why:
            raise Stop(why)
        if "meta" not in prop:
            prop["meta"] = admin_meta(token, u["property_id"])
        res["prop_meta"] = prop["meta"]
        start = today - timedelta(days=REF_DAYS)
        res["ref"] = _measure(ga, "REF", lambda: ref_report(ga, start, end), lambda rows: ref_sum(rows, ga, start),
                              ix, "REF")
        ref = ix.get("REF") or {}
        first = _first(res["ref"], u)
        res["first_day"] = first.isoformat() if first else None
        for i, (name, d) in enumerate(pick_slots(today, end, first)):
            rec = res["days"][name] = {"d": d.isoformat(), "age": (today - d).days}
            dix = ix["days"][name] = {}
            refd = ref.get(d)
            qa = split_body(d, ("countryId", "firstSessionDate"))
            rec["QB"] = _measure(ga, "QB", lambda: split_report(ga, split_body(d, ("firstSessionDate",))),
                                 lambda rows: split(rows, d, ga, refd), dix, "QB")
            rec["QA"] = _measure(ga, "QA", lambda: split_report(ga, qa), lambda rows: split(rows, d, ga, refd, True),
                                 dix, "QA")
            rec["QA6"] = _measure(ga, "QA6", lambda: split_report(
                ga, qa, extra=in_list(d - timedelta(days=L) for L in LIST_LAGS)),
                lambda rows: split(rows, d, ga, refd, True), dix, "QA6")
            rec["QA90"] = _measure(ga, "QA90", lambda: split_report(ga, qa, extra=in_list(_span(d, LIST90))),
                                   lambda rows: split(rows, d, ga, refd, True), dix, "QA90")
            rec["VER"] = _measure(ga, "VER", lambda: ga.report_all(
                dict(split_body(d, ("firstSessionDate", "appVersion")), metrics=ga4._dim("activeUsers", "newUsers")),
                page_rows=PAGE_ROWS), lambda rows: ver_sum(rows, d, ga), dix, "VER")
            xs = [(L, d - timedelta(days=L)) for L in COH_LAGS if d - timedelta(days=L) >= first]
            if xs:
                hold = {}
                rec["COH"] = _measure(ga, "COH", lambda: coh_fetch(ga, xs, hold), lambda rows: coh_sum(rows, ga, hold),
                                      dix, "COH")
            if i == 0:
                once(ga, res["once"], ix["once"], d, first, end, dix, refd)
    except Stop as e:
        res["stopped"] = str(e)
    finally:
        res["days"] = {k: v for k, v in res["days"].items() if any(x in v for x in DAY_KINDS)}  # a stop: no empty day
        _safely(compare_app, res, ix, adm_app, u, end)
        res.update(calls=ga.by_kind, tokens=ga.tok, tok_delta=ga.tok_delta, sec=round(ga.sec, 2), quota=ga.quota,
                   server_errors=ga.server_errors, no_total=ga.no_total)
        if ga.stop and "stopped" not in res:
            res["stopped"] = ga.stop
    return res


def once(ga, o, oix, d, first, end, dix, refd):
    """The once-per-app requests, on the recent day d."""
    x = d - timedelta(days=COH_X_LAG)
    if x >= first:
        xs = [(COH_X_LAG, x)]
        for kind, dims, mets in (("COH_CTY", ("countryId",), COH_METS), ("COH_REV", (), COH_METS + ("totalAdRevenue",)),
                                 ("COH_CTY_REV", ("countryId",), COH_METS + ("totalAdRevenue",))):
            o[kind] = _measure(ga, kind, lambda: ga.report(coh_body(xs, COH_X_LAG, dims, mets)),
                               lambda rows: (dict(_flags(ga), rows=len(rows), accepted=True), {"p": coh_parse(rows)}),
                               oix, kind)
        top = (dix.get("QA") or {}).get("top_cc")
        if top:
            o["COH_FILT"] = _measure(ga, "COH_FILT", lambda: ga.report(coh_body(xs, COH_X_LAG),
                                                                       extra=[ga4._exact("countryId", top)]),
                                     lambda rows: (dict(_flags(ga), rows=len(rows), accepted=True),
                                                   {"p": coh_parse(rows)}), oix, "COH_FILT")
    qa = split_body(d, ("countryId", "firstSessionDate"))
    o["CTY56"] = _measure(ga, "CTY56", lambda: ga.report_all(cty_body(end), page_rows=PAGE_ROWS),
                          lambda rows: cty_sum(rows, ga), oix, "CTY56")
    o["PAID"] = _measure(ga, "PAID", lambda: ga.report_all(paid_body(end), page_rows=PAGE_ROWS),
                         lambda rows: paid_sum(rows, ga), oix, "PAID")
    lo = d - timedelta(days=LIST90 - 1)
    o["BETWEEN"] = _measure(ga, "BETWEEN", lambda: split_report(ga, qa, extra=between(lo, d), fallback=False),
                            lambda rows: _accepted(split(rows, d, ga, refd, True)), oix, "BETWEEN")
    o["IN200"] = _measure(ga, "IN200", lambda: split_report(ga, qa, extra=in_list(_span(d, LIST_BIG)), fallback=False),
                          lambda rows: _accepted(split(rows, d, ga, refd, True)), oix, "IN200")


def _accepted(got):
    got[0]["accepted"] = True
    return got


def compare_app(res, ix, adm_app, u, end):
    ref = ix.get("REF") or {}
    for name, rec in (res.get("days") or {}).items():
        _safely(compare_day, rec, ix["days"].get(name) or {}, ref)
    rec = (res.get("days") or {}).get("recent")
    dix = ix["days"].get("recent") or {}
    if rec:
        _safely(compare_once, res["once"], ix.get("once") or {}, dix, gu._d(rec["d"]), rec.get("QA"))
    if _ok(res.get("ref")) or res.get("days"):
        res["m5"] = _safely(admob_compare, res, ix, adm_app, u["tz"], end)
    if rec and "QB" in dix and _ok(rec.get("QB")):
        hs = gu._d(u["history_start"]) if u.get("history_start") else (
            gu._d(res["first_day"]) if res.get("first_day") else None)
        if hs:
            res["m12"] = _safely(size_estimate, (end - hs).days + 1, dix["QB"], dix.get("QA"), rec["QB"],
                                 gu._d(rec["d"]))


# ── the summary ─────────────────────────────────────────────────────────────────────────────────

def _recs(apps, kind, slot=None):
    out = []
    for a in apps.values():
        if kind == "REF":
            r = a.get("ref")
            out += [r] if isinstance(r, dict) else []
        elif kind in DAY_KINDS:
            out += [rec[kind] for s, rec in (a.get("days") or {}).items()
                    if (slot is None or s == slot) and isinstance(rec.get(kind), dict)]
        else:
            r = (a.get("once") or {}).get(kind)
            out += [r] if isinstance(r, dict) else []
    return out


def kind_stats(recs):
    errs = [r["err"] for r in recs if "err" in r]
    ok = [r for r in recs if "err" not in r]
    h400 = sum(1 for e in errs if e.get("http") == 400)
    return {"n": len(recs), "ok": len(ok), "http400": h400, "err_other": len(errs) - h400,
            "calls": sum(r.get("calls") or 0 for r in recs), "rows": _stats([r.get("rows") for r in ok]),
            "pages_max": max([r.get("pages") or 0 for r in ok], default=0), "tok": _stats([r.get("tok") for r in recs]),
            "tok_delta": _stats([r.get("tok_delta") for r in recs]), "sec": _stats([r.get("sec") for r in recs]),
            "thresh": sum(1 for r in ok if r.get("thresh")), "loss_other": sum(1 for r in ok if r.get("loss_other")),
            "sampled": sum(1 for r in ok if r.get("sampled")),
            "with_other": sum(1 for r in ok if (r.get("other") or {}).get("rows")),
            "no_total": sum(1 for r in ok if r.get("mets") == "no_total"),
            "usd": sum(1 for r in ok if r.get("currency") == "USD")}


def m3_lag(cs):
    """One lag's cohort-vs-one-day cells (coh_cells) → counts. A cell where the cohort and the one-day reads are all 0
    (an install day with nobody back that day, a tiny app) "ties" trivially, so n counts every cell but the within-3%
    counts are over the NON-EMPTY cells only: the ≥ 95% rule reads qb_within_3pct ÷ nonzero. big: the cells with
    ≥ M3_BIG users in the QB cell, where the 1-user slack no longer hides a gap."""
    nz = [c for c in cs if (c.get("a") or 0) > 0 or (c.get("qb") or 0) > 0 or (c.get("qa") or 0) > 0]
    big = [c for c in nz if (c.get("qb") or 0) >= M3_BIG]
    return {"n": len(cs), "nonzero": len(nz), "qb_within_3pct": sum(1 for c in nz if _close(c["a"], c["qb"])),
            "qa_within_3pct": sum(1 for c in nz if _close(c["a"], c["qa"])), "big": len(big),
            "big_qb_within_3pct": sum(1 for c in big if _close(c["a"], c["qb"])),
            "qb_dev_med": pr._median([abs(c["r_qb"] - 1) for c in cs if c.get("r_qb") is not None]),
            "qa_dev_med": pr._median([abs(c["r_qa"] - 1) for c in cs if c.get("r_qa") is not None]),
            "t_new_med": pr._median([c.get("t_new") for c in cs])}


def summary(apps):
    """Per kind and per day slot (kind_stats), then one block per design question: m1 (Q-A cost → IDAY_MAX_CALLS),
    m2 ("(other)" by age), m3 (cohort vs one-day cells by lag), m4 (additivity), m5 (GA4 ÷ AdMob), m6 (cohort variants
    accepted), m7 (IAP), m8 (currency), m10 (paid split), m11 + bc (filtered reads vs QA), ver (e), m12 (file sizes),
    cost (calls, tokens)."""
    ok = [a for a in apps.values() if isinstance(a, dict)]
    apps = {i: a for i, a in enumerate(ok)}
    out = {"kinds": {k: kind_stats(_recs(apps, k)) for k in ("REF",) + DAY_KINDS + ONCE_KINDS},
           "by_slot": {s: {k: kind_stats(_recs(apps, k, s)) for k in DAY_KINDS} for s, _ in SLOTS}}
    p90 = (out["kinds"]["QA"].get("tok") or {}).get("p90")
    out["m1"] = {"qa_tok_p90": p90, "qa_pages_max": out["kinds"]["QA"]["pages_max"],
                 "iday_max_calls_hint": None if p90 is None else 120 if p90 <= 12 else 60 if p90 <= 30 else 30}
    m2 = {}
    for s, _ in SLOTS:
        for k in ("QA", "QB"):
            rs = [r for r in _recs(apps, k, s) if _ok(r)]
            sh = [(r.get("other") or {}).get("act_share") or 0 for r in rs]
            m2["%s_%s" % (k, s)] = {
                "reads": len(rs), "with_other": sum(1 for r in rs if (r.get("other") or {}).get("rows")),
                "over_oth_max": sum(1 for x in sh if x >= OTH_MAX), "oth_act_max": max(sh, default=None),
                "oth_ad_max": max([(r.get("other") or {}).get("ad_share") or 0 for r in rs], default=None),
                "loss": sum(1 for r in rs if r.get("loss_other")), "thresh": sum(1 for r in rs if r.get("thresh")),
                "sampled": sum(1 for r in rs if r.get("sampled"))}
    out["m2"] = m2
    by = {}
    for r in _recs(apps, "COH"):
        for c in r.get("cells") or []:
            by.setdefault(c["L"], []).append(c)
    out["m3"] = {str(L): m3_lag(cs) for L, cs in sorted(by.items())}
    m4 = {}
    for k in ("QB", "QA"):
        rs = [r for r in _recs(apps, k) if _ok(r)]
        m4[k] = {"reads": len(rs),
                 "total_within": sum(1 for r in rs if r.get("add") and all(
                     x is not None and abs(x - 1) <= ADD for x in r["add"].values())),
                 "cov_med": pr._median([r.get("cov") for r in rs]), "ncov_med": pr._median([r.get("ncov") for r in rs]),
                 "rcov_med": pr._median([r.get("rcov") for r in rs]),
                 "tcov_med": pr._median([r.get("tcov") for r in rs]),
                 "cov_min": min([r["cov"] for r in rs if r.get("cov") is not None], default=None)}
    m4["QA_vs_QB"] = {"reads": sum(1 for r in _recs(apps, "QA") if r.get("vs_QB")),
                      "act_dev_med": pr._median([(r.get("vs_QB") or {}).get("act_dev_med") for r in _recs(apps, "QA")]),
                      "ad_dev_med": pr._median([(r.get("vs_QB") or {}).get("ad_dev_med") for r in _recs(apps, "QA")])}
    out["m4"] = m4
    m5 = [a.get("m5") for a in ok if isinstance(a.get("m5"), dict) and a["m5"].get("state") == "ok"]
    p50s = [(m.get("r_all") or {}).get("p50") for m in m5]
    p20 = [(m.get("r_all_20") or {}).get("p50") for m in m5 if ((m.get("r_all_20") or {}).get("n") or 0) >= MIN_WEEKS]
    out["m5"] = {"apps": len(m5), "r_all_p50_median": pr._median(p50s),
                 "r_net_p50_median": pr._median([(m.get("r_net") or {}).get("p50") for m in m5]),
                 "apps_p50_outside_07_13": sum(1 for x in p50s if x is not None and not 0.7 <= x <= 1.3),
                 "apps_20usd": len(p20), "r_all_20usd_p50_median": pr._median(p20),
                 "apps_20usd_p50_outside_07_13": sum(1 for x in p20 if x is not None and not 0.7 <= x <= 1.3),
                 "cty_top_usd_ok": sum(1 for m in m5 for r in ((m.get("cty") or {}).get("top") or [])
                                       if r.get("usd_ok")),
                 "day_r_tot_net_median": pr._median([v.get("r_tot_net") for m in m5
                                                     for v in (m.get("days") or {}).values()]),
                 "day_r_ad_all_median": pr._median([v.get("r_ad_all") for m in m5
                                                    for v in (m.get("days") or {}).values()]),
                 "cty_apps": sum(1 for m in m5 if m.get("cty")),
                 "cty_r_total_median": pr._median([(m.get("cty") or {}).get("r_total") for m in m5])}
    out["m6"] = {k: {"n": len(_recs(apps, k)), "accepted": sum(1 for r in _recs(apps, k) if _ok(r))}
                 for k in ("COH_CTY", "COH_REV", "COH_CTY_REV", "COH_FILT", "BETWEEN")}
    coh = [r for r in _recs(apps, "COH") if _ok(r)]
    out["m6"]["COH"] = {"reads": len(coh), "end_365": sum(1 for r in coh if r.get("end_offset") == 365),
                        "long_refused": sum(1 for r in coh if r.get("long_err")),
                        "truncated": sum(1 for r in coh if r.get("truncated")),
                        "tok": _stats([r.get("tok") for r in coh]), "rows": _stats([r.get("rows") for r in coh])}
    iap = [((a.get("m5") or {}).get("iap") or {}).get("share") for a in ok]
    out["m7"] = {"apps": sum(1 for x in iap if x is not None), "iap_ge_1pct": sum(1 for x in iap if x and x >= 0.01),
                 "p50": _pct(iap, 0.5), "max": max([x for x in iap if x is not None], default=None)}
    cur = {}
    for a in ok:
        c = (a.get("prop_meta") or {}).get("currency") or "?"
        cur[c] = cur.get(c, 0) + 1
    reads = [r for k in ("QB", "QA") for r in _recs(apps, k) if _ok(r)]
    out["m8"] = {"prop_currency": cur, "reads": len(reads),
                 "resp_usd": sum(1 for r in reads if r.get("currency") == "USD")}
    paid = [(a.get("m5") or {}).get("paid") for a in ok if (a.get("m5") or {}).get("paid")]
    out["m10"] = {"apps": len(paid), "ratio_p50_median": pr._median([p.get("ratio_p50") for p in paid]),
                  "ads_share_median": pr._median([p.get("ads_share") for p in paid]),
                  "ga4_ads_share_median": pr._median([r.get("ads_share") for r in _recs(apps, "PAID") if _ok(r)])}
    bc = {}
    for k in ("QA6", "QA90", "IN200", "BETWEEN"):
        rs = [r for r in _recs(apps, k) if _ok(r)]
        bc[k] = {"reads": len(rs), "of": len(_recs(apps, k)),
                 "tok_vs_QA_med": pr._median([r.get("tok_vs_QA") for r in rs]),
                 "rows_vs_QA_med": pr._median([r.get("rows_vs_QA") for r in rs]),
                 "equal_share_med": pr._median([(r.get("vs_QA") or {}).get("equal_share") for r in rs]),
                 "act_vs_QA_med": pr._median([(r.get("vs_QA") or {}).get("act") for r in rs]),
                 "with_other": sum(1 for r in rs if (r.get("other") or {}).get("rows"))}
    out["m11_bc"] = bc
    vs = [r for r in _recs(apps, "VER") if _ok(r)]
    out["ver"] = {"reads": len(vs), "rows": _stats([r.get("rows") for r in vs]),
                  "versions_new_p50": _pct([r.get("new_versions") for r in vs], 0.5),
                  "dominant_share_p50": _pct([r.get("dominant_share") for r in vs], 0.5),
                  "dominant_ge80": sum(1 for r in vs if r.get("dominant_ge80"))}
    m12 = [a.get("m12") for a in ok if isinstance(a.get("m12"), dict) and "hot_gz" in a["m12"]]
    out["m12"] = {"apps": len(m12), "hot_gz": _stats([m["hot_gz"] for m in m12]),
                  "old_gz": _stats([m["old_gz"] for m in m12]),
                  "total_gz": _stats([m["hot_gz"] + m["old_gz"] for m in m12])}
    out["cost"] = {"calls": sum(sum((v or {}).get("calls", 0) for v in (a.get("calls") or {}).values()) for a in ok),
                   "tokens": sum(pr._int(a.get("tokens")) for a in ok),
                   "tokens_max_app": max([pr._int(a.get("tokens")) for a in ok], default=0),
                   "sec": round(sum(a.get("sec") or 0 for a in ok), 1)}
    return out


def counts(apps, run, adm):
    """The public counts (no ids, names, dates, user or money numbers)."""
    def ok_of(k):
        rs = _recs(apps, k)
        return sum(1 for r in rs if _ok(r)), len(rs)
    qb, qa, coh = ok_of("QB"), ok_of("QA"), ok_of("COH")
    var = [r for k in VARIANTS for r in _recs(apps, k)]
    reads = [r for k in CORE + VARIANTS for r in _recs(apps, k)]
    stopped = [a.get("stopped") for a in apps.values() if a.get("stopped")]
    errs = sum(1 for a in apps.values() if a.get("err") or a.get("crash"))
    errs += sum(1 for k in CORE for r in _recs(apps, k) if "err" in r)
    return {"apps": len(apps), "apps_measured": sum(1 for a in apps.values() if a.get("days")), "calls": run.calls,
            "qb_ok": qb[0], "qb_of": qb[1], "qa_ok": qa[0], "qa_of": qa[1], "coh_ok": coh[0], "coh_of": coh[1],
            "var_ok": sum(1 for r in var if _ok(r)), "var_of": len(var),
            "other_reads": sum(1 for r in reads if _ok(r) and (r.get("other") or {}).get("rows")),
            "thresholded": sum(1 for r in reads if _ok(r) and r.get("thresh")),
            "quota_low": sum(1 for s in stopped if s.startswith("quota")),
            "stopped_other": sum(1 for s in stopped if not s.startswith("quota")), "errors": errs,
            "admob_apps": sum(1 for a in apps.values() if (a.get("m5") or {}).get("state") == "ok"),
            "seconds": run.elapsed(), "tokens": sum(pr._int(a.get("tokens")) for a in apps.values())}


COUNT_KEYS = ("apps_measured", "apps", "calls", "qb_ok", "qb_of", "qa_ok", "qa_of", "coh_ok", "coh_of", "var_ok",
              "var_of", "other_reads", "thresholded", "quota_low", "stopped_other", "errors", "admob_apps", "seconds")


def public_line(c):
    return ("shape probe: apps %d/%d, calls %d, QB ok %d/%d, QA ok %d/%d, cohorts ok %d/%d, variants accepted %d/%d, "
            "reads with (other) %d, thresholded %d, quota low %d, stopped %d, errors %d, AdMob-matched apps %d, %ds"
            % tuple(pr._int((c or {}).get(k)) for k in COUNT_KEYS))


# ── the run ─────────────────────────────────────────────────────────────────────────────────────

def run_probe(units, cid, sec, tokens, adm=None, now=None, budget=BUDGET_SEC, clock=time.monotonic, workers=WORKERS,
              tick=TICK_SEC):
    """Probe every unit (app) → the report (dict). Never raises for one app's failure; prints counts-only progress."""
    run = Run(budget, clock)
    now = now or datetime.now(timezone.utc)
    rt, access = dict(tokens), {}
    for owner in sorted({u.get("owner") or "" for u in units}):
        try:
            access[owner] = ga4.access_token(cid, sec, rt[owner]) if owner in rt else None
        except Exception:
            access[owner] = None
    props = {u["property_id"]: pr.new_prop() for u in units}     # quota / 5xx / stop / Admin meta are per property
    adm_apps = (adm or {}).get("apps") or {}
    out, done = {}, [0]

    def one(group):
        for u in group:
            try:
                out[u["package"]] = probe_app(run, u, access.get(u.get("owner") or ""), now, props[u["property_id"]],
                                              adm_apps.get(u["package"]))
            except Exception as e:                   # a bug for one app must not cost the others
                out[u["package"]] = {"app_id": u.get("app_id"), "crash": type(e).__name__}
            with run.lock:
                done[0] += 1
                n = done[0]
            run.say("shape progress: apps %d/%d, calls %d, %ds" % (n, len(units), run.calls, run.elapsed()))

    with Beat(run, tick):
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(one, pr._groups(units)))
    c = _safely(counts, out, run, adm, fallback={"apps": len(units), "calls": run.calls, "seconds": run.elapsed()})
    a = {k: (adm or {}).get(k) for k in ("state", "tz_src", "currency", "till")}
    a["apps_matched"] = admob_matched(adm)
    return {"v": 1, "probe": "ga4_shape", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rules": {"late": LATE, "slots": [[s, a_] for s, a_ in SLOTS], "mets": list(METS), "ref_days": REF_DAYS,
                      "list_lags": list(LIST_LAGS), "list90": LIST90, "list_big": LIST_BIG, "coh_lags": list(COH_LAGS),
                      "coh_short": COH_SHORT, "coh_x_lag": COH_X_LAG, "cty_days": CTY_DAYS, "paid_days": PAID_DAYS,
                      "weeks": WEEKS, "oth_max": OTH_MAX, "tie": TIE, "add": ADD, "quota_frac": pr.QUOTA_FRAC,
                      "page_rows": PAGE_ROWS},
            "admob": a, "counts": c, "summary": _safely(summary, out), "apps": out}


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    data_dir = env.get("SHAPE_DATA_DIR") or ""
    units = units_from_state(load_state(data_dir))
    cap = pr._int(env.get("PROBE_MAX_APPS"))
    if cap > 0:
        units = units[:cap]
    if not units:
        sys.exit("no GA4 app routes in the private state")
    budget = pr._int(env.get("PROBE_BUDGET_SEC")) or BUDGET_SEC
    print("shape probe: %d app(s) to probe" % len(units), flush=True)
    adm = _safely(load_admob, data_dir, units, now, env, fallback={"state": "error"})
    print("shape probe: AdMob data for %d/%d app(s)" % (admob_matched(adm), len(units)), flush=True)
    report = run_probe(units, cid, sec, tokens, adm, now=now, budget=budget, clock=clock)
    print(public_line(report["counts"]), flush=True)
    if not write_private(OUT_PATH, pr._dump(report), "ga4 shape probe"):
        sys.exit("private repo write failed")            # stderr: hidden by the workflow step
    print("shape probe: report written", flush=True)


if __name__ == "__main__":
    main()
