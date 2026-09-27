"""One-off Google Ads GEO probe, run by .github/workflows/gads-geo-probe.yml: before the "Install value" tab may show
cost per install BY COUNTRY (spec §1.8, owner question Q5), measure whether Google Ads can split the app campaigns'
cost and installs by country completely enough, and how big that data is. READ-ONLY against Google Ads (the build's
own OAuth refresh token, developer token and MCC — the same secrets refresh.yml passes to the Ads fetch); nothing is
changed in any Google Ads account and nothing in data/ or site/ is touched.

Window: the last DAYS (28) complete UTC days, today − 28 .. today − 1. A day ≤ today − SETTLED (3) is "settled"
(the pass rules read those); the 2 newest are reported apart as "fresh". Ads days are the ACCOUNT's days (G6 says
which zone).

For every non-manager account under the MCC (google_ads._child_accounts — the roster now also asks time_zone), one
request at a time per account (WORKERS accounts in parallel):
  SPEND  google_ads._app_spend_for — the build's spend path: app-campaign cost per store / day (the G1 denominator)
  CHAN   campaign.id → advertising_channel_type (+ sub type): how much of that spend is MULTI_CHANNEL (Q-G1's filter)
  INST   google_ads._app_installs_for — the build's installs path: biddable_app_install_conversions (G4's denominator)
  G1P    Q-G1 exactly as spec §1.8: geographic_view, MULTI_CHANNEL, LOCATION_OF_PRESENCE, cost / impressions / clicks
  G1I    Q-G1 with AREA_OF_INTEREST instead (G2)
  ULV    user_location_view cost by country (G3, the fallback)
  G2     Q-G2 exactly as spec §1.8: DOWNLOAD conversions by country (G4)
  CA     the conversion_action list (G7): category, type, status, click-through lookback days, included in
         conversions, counting type, primary for goal — asked once more with only the spec's fields on an HTTP 400
An account whose SPEND came back with no row asks only CA (nothing to split). Once per run: the roster (G6) and Q-G3
geo_target_constant country ids → ISO-2 (G5; on the MCC, or on the first account when the MCC refuses it).
GA4 packages (data/ga4_uninstall/state.json of the PRIVATE repo, contents API, best-effort) only label stores and size
the GA4-only cache (G8); without them those parts say null.

Money is kept in the MAJORITY account currency ("base_ccy", the one carrying the most spend) as micros; an account in
another currency is converted with google_ads._fx_to_usd (asked only when there is more than one currency). A ratio of
two costs of the same store and day does not depend on the currency.

Safety: no call after BUDGET_SEC (12 min) or MAX_CALLS; a quota error (HTTP 429 / RESOURCE_EXHAUSTED / quotaError)
stops every further call at once — the developer token's quota is the hourly build's too; 3 server errors (5xx)
stop the run; a refused request is kept as its HTTP status + Google Ads errorCode (+ its message, digit runs masked) in
the PRIVATE file only. What was measured is always written, even when the bookkeeping has a bug (its class is kept).

Output: ga4/gads_geo_probe.json in the PRIVATE repo (the probes' write_private — never data/ or site/). PUBLIC LOG:
progress counts and ONE result line of counts only (accounts, calls, errors, accepted requests, stores with spend,
time zones); no ids, names, dates, money or ratios; stderr (which could echo request details) is hidden by the
workflow; a counts-only heartbeat at least every minute.

Reading ga4/gads_geo_probe.json:
  "verdict"            g1_pass (G1), g5_pass (G5), use ("presence" | "area_of_interest" | "user_location" | null, G2 /
                       G3), gads_geo_may_go_on (= g1_pass and g5_pass; GADS_GEO still needs the owner's yes, §8 Q5)
  "summary.g1"         Q-G1 accepted / of accounts (+ refused error codes); total_cost, base_ccy; top = the stores
                       holding ≥ 80% of settled spend, top_share; cov_top / cov_all / cov_fresh_top: per store-day
                       Σ country cost ÷ campaign cost (n, p10 p50 p90 min max, weighted Σ÷Σ, over = days > 1.03,
                       unknown = store-days where either side could not be read); cov_top_vs_multi: the same vs
                       MULTI_CHANNEL cost only; non_multi_share, no_store_share, no_country_share, orphan_days (geo
                       cost on a day with no campaign cost); per_store {share, ga4, n, p10, p50, min, weighted};
                       pass = cov_top p10 ≥ 0.97 with n > 0 and unknown 0
  "summary.g2"         presence / area_of_interest / both (P + I) ÷ campaign cost, on top and all stores — "both" near
                       2.0 means the two views double count; use = presence unless its coverage fails
  "summary.g3"         user_location_view: accepted, cov_top, cov_all, fallback_ok
  "summary.g4"         DOWNLOAD conversions Σ countries ÷ biddable installs per settled store-day (days with ≥ 10
                       installs): top / all (n, p10 p50 p90, weighted), days_inst_no_dl — the p50 is the record
  "summary.g5"         accepted, via, countries (constants), with_cost, unmapped_with_cost (+ cost share), pass
  "summary.g6"         roster_tz (the time_zone field accepted), by_zone {zone: accounts}, spend_share_by_zone
  "summary.g7"         accepted / of, fallback, actions (not removed), by_category / by_type / by_lookback /
                       by_include / by_counting / by_primary (not removed), by_status (all), download_included
  "summary.g8"         calls (+ by kind), seconds by kind, rows_28 / rows_400_est of G1P and G2, sec_28 / sec_400_est
                       (linear in rows: an upper-bound guess), per_account {rows_28, sec_28, rows_400_est},
                       per_account_max; cache / cache_ga4: the would-be
                       data/roas_geo_cache.json for these 28 days (stores, store-days, cells, json / gz bytes),
                       and × 400/28
  "stores"[store]      ga4, days[date] = {c: campaign cost, cm: MULTI_CHANNEL cost, p: presence, i: area of interest,
                       u: user location, inst: biddable installs, dl: DOWNLOAD conversions}; money in base micros;
                       null = could not be read (never 0)
  "accounts"[id]       ccy, tz, no_spend, stopped, crash, ca (G7 counts), calls[kind] = {n, rows, sec,
                       err: {http, code, msg} | stop}
  "stopped"            why the run stopped starting calls (budget | calls | quota | server) or null
  "iso", "ccid_cost"   country id → ISO-2 (G5), presence cost by country id ("none" = no country)
"""

import gzip
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from admob_iq.fetch import google_ads as gads
from admob_iq.fetch.ga4_d1d7_probe import _dump, _int, _safely, write_private
from admob_iq.fetch.ga4_diagnose import _private_json

DAYS = 28                           # the window: today − 28 .. today − 1
SETTLED = 3                         # a day ≤ today − 3 is settled; the 2 newest are "fresh"
EXTRAP_DAYS = 400                   # the cache's first backfill (spec §1.8)
COV_PASS = 0.97                     # G1: p10 of the top stores' day coverage
TOP_SHARE = 0.80                    # G1: "the apps holding ≥ 80% of spend"
OVER = 1.03                         # a day whose country sum is > 3% above the campaign cost is counted
G4_MIN_INST = 10                    # G4: a store-day is compared when it has ≥ 10 biddable installs
WORKERS = 4                         # accounts in parallel — one request at a time per account
BUDGET_SEC = 12 * 60                # no new call after 12 min (the job's timeout is 25)
MAX_CALLS = 600                     # a hard cap (≈ 30 accounts × 8 requests + the once-reads, twice over)
SERVER_STOP = 3                     # 5xx responses before the run stops
PAUSE_SEC = 0.2                     # between two requests of one account
HEARTBEAT_SEC = 60                  # a counts-only progress line at least this often
TICK_SEC = 20                       # a side thread checks the heartbeat this often
STATE_PATH = "data/ga4_uninstall/state.json"
OUT_PATH = "ga4/gads_geo_probe.json"
PRESENCE, INTEREST = "LOCATION_OF_PRESENCE", "AREA_OF_INTEREST"
ACCOUNT_KINDS = ("SPEND", "CHAN", "INST", "G1P", "G1I", "ULV", "G2", "CA", "CA_MIN")
KEYS = ("c", "cm", "p", "i", "u", "inst", "dl")
MONEY = ("c", "cm", "p", "i", "u")
NEEDS = {"c": ("SPEND",), "cm": ("SPEND", "CHAN"), "p": ("G1P",), "i": ("G1I",), "u": ("ULV",), "inst": ("INST",),
         "dl": ("G2",)}

Q_CHAN = ("SELECT campaign.id, campaign.advertising_channel_type, campaign.advertising_channel_sub_type "
          "FROM campaign WHERE campaign.app_campaign_setting.app_id != ''")
Q_G1 = ("SELECT campaign.id, campaign.app_campaign_setting.app_id, campaign.advertising_channel_type, "
        "geographic_view.country_criterion_id, geographic_view.location_type, "
        "segments.date, metrics.cost_micros, metrics.impressions, metrics.clicks "
        "FROM geographic_view "
        "WHERE segments.date BETWEEN '{a}' AND '{b}' "
        "AND campaign.advertising_channel_type = 'MULTI_CHANNEL' "
        "AND geographic_view.location_type = '{lt}' "
        "AND metrics.cost_micros > 0")
Q_G2 = ("SELECT campaign.app_campaign_setting.app_id, campaign.advertising_channel_type, "
        "geographic_view.country_criterion_id, "
        "geographic_view.location_type, segments.date, segments.conversion_action_category, "
        "metrics.conversions "
        "FROM geographic_view "
        "WHERE segments.date BETWEEN '{a}' AND '{b}' "
        "AND campaign.advertising_channel_type = 'MULTI_CHANNEL' "
        "AND geographic_view.location_type = 'LOCATION_OF_PRESENCE' "
        "AND segments.conversion_action_category = 'DOWNLOAD'")
Q_ULV = ("SELECT campaign.id, campaign.app_campaign_setting.app_id, campaign.advertising_channel_type, "
         "user_location_view.country_criterion_id, user_location_view.targeting_location, "
         "segments.date, metrics.cost_micros "
         "FROM user_location_view "
         "WHERE segments.date BETWEEN '{a}' AND '{b}' "
         "AND campaign.advertising_channel_type = 'MULTI_CHANNEL' "
         "AND metrics.cost_micros > 0")
Q_G5 = ("SELECT geo_target_constant.id, geo_target_constant.country_code "
        "FROM geo_target_constant WHERE geo_target_constant.target_type = 'Country'")
Q_CA = ("SELECT conversion_action.id, conversion_action.category, conversion_action.type, conversion_action.status, "
        "conversion_action.click_through_lookback_window_days, conversion_action.include_in_conversions_metric, "
        "conversion_action.counting_type, conversion_action.primary_for_goal FROM conversion_action")
Q_CA_MIN = ("SELECT conversion_action.id, conversion_action.category, conversion_action.status, "
            "conversion_action.click_through_lookback_window_days, conversion_action.include_in_conversions_metric "
            "FROM conversion_action")

_sleep = time.sleep


class Stop(Exception):
    """No further Google Ads call: the time budget, the call cap, a quota error or too many server errors."""


# ── run ─────────────────────────────────────────────────────────────────────────────────────────

class Run:
    """The run's clock, budget, call counter, global stop and (locked) counts-only progress lines."""

    def __init__(self, budget=BUDGET_SEC, clock=time.monotonic, max_calls=MAX_CALLS):
        self.clock, self.budget, self.max_calls = clock, budget, max_calls
        self.t0 = clock()
        self.beat = self.t0
        self.lock = threading.Lock()
        self.calls = self.errors = self.server_errors = 0
        self.stop = None

    def start_call(self):
        """Reserve one call, or raise Stop (budget / cap / an earlier quota or server stop). A stop is for good: its
        reason stays in self.stop."""
        with self.lock:
            why = self.stop
            if not why and self.clock() - self.t0 >= self.budget:
                why = "budget"
            if not why and self.calls >= self.max_calls:
                why = "calls"
            if why:
                self.stop = why
                raise Stop(why)
            self.calls += 1
        self.pulse()

    def failed(self, err):
        """A failed call: a quota error stops every further call at once; SERVER_STOP 5xx stop the run."""
        with self.lock:
            self.errors += 1
            http, code, msg = err.get("http"), (err.get("code") or ""), (err.get("msg") or "")
            if http == 429 or "quotaerror" in code.lower() or "RESOURCE_EXHAUSTED" in msg:
                self.stop = self.stop or "quota"
            elif http and http >= 500:
                self.server_errors += 1
                if self.server_errors >= SERVER_STOP:
                    self.stop = self.stop or "server"

    def pulse(self):
        with self.lock:
            now = self.clock()
            beat = now - self.beat >= HEARTBEAT_SEC
            if beat:
                self.beat = now
            n, s = self.calls, int(now - self.t0)
        if beat:
            self.say("gads geo progress: calls %d, %ds" % (n, s))

    def elapsed(self):
        return int(self.clock() - self.t0)

    def say(self, msg):
        with self.lock:
            print(msg, flush=True)


class Beat:
    """`with Beat(run):` a daemon thread calls run.pulse() every `every` s, so the heartbeat also comes while every
    worker waits on a slow call (0: no thread)."""

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


# ── one call ────────────────────────────────────────────────────────────────────────────────────

def _mask(s):
    return re.sub(r"\d{5,}", "#", str(s or ""))


def _err(e):
    """A failed call → {type, http, code, msg}: the HTTP status and the Google Ads errorCode (e.g.
    "queryError=PROHIBITED_METRIC_IN_SELECT_OR_WHERE_CLAUSE"), the message with digit runs masked (PRIVATE file
    only)."""
    s = str(e)
    m = re.match(r"HTTP (\d{3})", s)
    c = re.search(r"\b([A-Za-z]+Error=[A-Z0-9_]+)", s)
    return {"type": type(e).__name__, "http": int(m.group(1)) if m else None, "code": c.group(1) if c else None,
            "msg": _mask(s)[:300]}


def _call(run, rec, kind, fn):
    """One Google Ads request (or a google_ads helper making one) → its rows, or None when it failed or was not made.
    rec["calls"][kind] = {n, rows, sec, err | stop}."""
    c = rec["calls"].setdefault(kind, {"n": 0, "rows": 0, "sec": 0.0})
    try:
        run.start_call()
    except Stop as e:
        c["stop"] = rec["stopped"] = str(e)
        return None
    t = run.clock()
    try:
        out = list(fn() or [])
    except Exception as e:
        c["n"] += 1
        c["sec"] = round(c["sec"] + run.clock() - t, 3)
        c["err"] = _err(e)
        run.failed(c["err"])
        _sleep(PAUSE_SEC)
        return None
    c["n"] += 1
    c["rows"] += len(out)
    c["sec"] = round(c["sec"] + run.clock() - t, 3)
    _sleep(PAUSE_SEC)
    return out


def _try(fn, *args, default=None):
    """fn(*args), or `default` on a bug in the bookkeeping (the calls are already spent: the report is still
    written)."""
    try:
        return fn(*args)
    except Exception:
        return default


def _ok(rec, kind):
    c = (rec.get("calls") or {}).get(kind) or {}
    return c.get("n", 0) > 0 and "err" not in c and "stop" not in c


def _asked(rec, kind):
    c = (rec.get("calls") or {}).get(kind) or {}
    return c.get("n", 0) > 0


# ── rows ────────────────────────────────────────────────────────────────────────────────────────

def _sid(row):
    return gads._norm_store(((row.get("campaign") or {}).get("appCampaignSetting") or {}).get("appId"))


def _date(row):
    return str((row.get("segments") or {}).get("date") or "")


def _met(row, k):
    return (row.get("metrics") or {}).get(k)


def _ccid(view):
    v = (view or {}).get("countryCriterionId")
    try:
        return str(int(v)) if v not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        return None


def fold_account(res):
    """One account's results (kind → rows, None = failed / not asked) → (days {store: {date: {KEYS}}}, cells
    {(store, date, country id): [presence cost, downloads]}, ccid_cost {country id | "none": presence cost}, extra
    {no_store: {p, i, u}}). Money in the account's currency micros; a value needing a failed request is None."""
    days, cells, ccid_cost = {}, {}, Counter()
    extra = {"no_store": {"p": 0, "i": 0, "u": 0}}

    def day(sid, d):
        return days.setdefault(sid, {}).setdefault(d, {})

    def add(x, k, v):
        x[k] = x.get(k, 0) + v

    chan = {}
    for row in res.get("CHAN") or []:
        camp = row.get("campaign") or {}
        chan[str(camp.get("id"))] = camp.get("advertisingChannelType")
    for r in res.get("SPEND") or []:
        x = day(r["store_id"], str(r.get("date")))
        add(x, "c", _int(r.get("cost_micros")))
        if res.get("CHAN") is not None and chan.get(str(r.get("campaign_id"))) == "MULTI_CHANNEL":
            add(x, "cm", _int(r.get("cost_micros")))
    for kind, k, view in (("G1P", "p", "geographicView"), ("G1I", "i", "geographicView"),
                          ("ULV", "u", "userLocationView")):
        for row in res.get(kind) or []:
            cost, sid, d = _int(_met(row, "costMicros")), _sid(row), _date(row)
            if not sid:
                extra["no_store"][k] += cost
                continue
            add(day(sid, d), k, cost)
            if kind == "G1P":
                cc = _ccid(row.get(view)) or "none"
                ccid_cost[cc] += cost
                cells.setdefault((sid, d, cc), [0, 0.0])[0] += cost
    for r in res.get("INST") or []:
        add(day(r["store_id"], str(r.get("date"))), "inst", float(r.get("installs") or 0))
    for row in res.get("G2") or []:
        sid, d = _sid(row), _date(row)
        if not sid:
            continue
        conv = float(_met(row, "conversions") or 0)
        add(day(sid, d), "dl", conv)
        cells.setdefault((sid, d, _ccid(row.get("geographicView")) or "none"), [0, 0.0])[1] += conv
    for dd in days.values():
        for x in dd.values():
            for k in KEYS:
                if any(res.get(kind) is None for kind in NEEDS[k]):
                    x[k] = None
                else:
                    x.setdefault(k, 0)
    return days, cells, dict(ccid_cost), extra


def probe_account(run, ctx, acct):
    """Every request of one account, one at a time → its record (calls, currency, zone) + its folded parts (_days,
    _cells, _ccid, _extra: merged later, then dropped)."""
    aid = acct["id"]
    rec = {"ccy": acct.get("currency") or "USD", "tz": acct.get("tz"), "calls": {}}
    mcc, dev, tok, a, b = ctx["mcc"], ctx["dev"], ctx["token"], ctx["start"], ctx["end"]

    def ask(kind, fn):
        return _call(run, rec, kind, fn)

    res = {}
    res["SPEND"] = ask("SPEND", lambda: gads._app_spend_for(aid, mcc, dev, tok, a, b))
    if res["SPEND"] is None and ((rec["calls"].get("SPEND") or {}).get("err") or {}).get("http") == 403:
        rec["not_enabled"] = True                  # a disabled / cancelled account (CUSTOMER_NOT_ENABLED): every other
        return rec                                 # request would fail the same way — none asked
    if res["SPEND"] == []:
        rec["no_spend"] = True
    else:
        res["CHAN"] = ask("CHAN", lambda: gads._search(aid, mcc, dev, tok, Q_CHAN))
        res["INST"] = ask("INST", lambda: gads._app_installs_for(aid, mcc, dev, tok, a, b))
        res["G1P"] = ask("G1P", lambda: gads._search(aid, mcc, dev, tok, Q_G1.format(a=a, b=b, lt=PRESENCE)))
        res["G1I"] = ask("G1I", lambda: gads._search(aid, mcc, dev, tok, Q_G1.format(a=a, b=b, lt=INTEREST)))
        res["ULV"] = ask("ULV", lambda: gads._search(aid, mcc, dev, tok, Q_ULV.format(a=a, b=b)))
        res["G2"] = ask("G2", lambda: gads._search(aid, mcc, dev, tok, Q_G2.format(a=a, b=b)))
    ca = ask("CA", lambda: gads._search(aid, mcc, dev, tok, Q_CA))
    if ca is None and ((rec["calls"]["CA"].get("err") or {}).get("http") == 400):
        ca = ask("CA_MIN", lambda: gads._search(aid, mcc, dev, tok, Q_CA_MIN))
    rec["ca"] = _safely(ca_counts, ca or [], fallback={}) if ca is not None else None
    parts = _safely(lambda: dict(zip(("_days", "_cells", "_ccid", "_extra"), fold_account(res))), fallback={})
    rec.update(parts)
    return rec


def ca_counts(rows):
    """G7 for one account: counts by value over the conversion actions that are not REMOVED (status: over all)."""
    out = {k: Counter() for k in ("category", "type", "lookback", "include", "counting", "primary", "status")}
    n = dl_inc = 0
    for row in rows:
        ca = row.get("conversionAction") or {}
        st = ca.get("status")
        out["status"][str(st)] += 1
        if st == "REMOVED":
            continue
        n += 1
        inc = ca.get("includeInConversionsMetric")
        for k, v in (("category", ca.get("category")), ("type", ca.get("type")),
                     ("lookback", ca.get("clickThroughLookbackWindowDays")), ("include", inc),
                     ("counting", ca.get("countingType")), ("primary", ca.get("primaryForGoal"))):
            out[k][str(v) if v is not None else "unset"] += 1
        if ca.get("category") == "DOWNLOAD" and inc is True:
            dl_inc += 1
    res = {k: dict(v) for k, v in out.items()}
    res["actions"], res["download_included"] = n, dl_inc
    return res


# ── merge + summary ─────────────────────────────────────────────────────────────────────────────

def currency_rates(accts, fx_fn=None):
    """(base currency, {ccy: rate to base}). The base carries the most spend (the most accounts when nobody spent);
    other currencies go ccy → USD → base with fx_fn (google_ads._fx_to_usd), asked only when there is more than one."""
    spend, n = Counter(), Counter()
    for a in accts.values():
        n[a["ccy"]] += 1
        for dd in (a.get("_days") or {}).values():
            spend[a["ccy"]] += sum(x.get("c") or 0 for x in dd.values())
    if not n:
        return "USD", {}
    base = max(n, key=lambda c: (spend[c], n[c], c))
    if len(n) == 1:
        return base, {base: 1.0}
    fx_fn = fx_fn or gads._fx_to_usd
    usd = {c: float(fx_fn(c) or 0) for c in n}
    return base, {c: (usd[c] / usd[base] if usd[base] else 1.0) if c != base else 1.0 for c in n}


def merge(accts, rates):
    """Every account's folded parts in the base currency → (stores {store: {date: {KEYS}}}, cells, ccid_cost, extra).
    A value some contributing account could not read stays None (never 0)."""
    stores, cells, ccid, extra = {}, {}, Counter(), {"no_store": Counter()}
    for a in accts.values():
        r = rates.get(a["ccy"], 1.0)
        for sid, dd in (a.get("_days") or {}).items():
            for d, x in dd.items():
                y = stores.setdefault(sid, {}).setdefault(d, dict.fromkeys(KEYS, 0))
                for k in KEYS:
                    v = x.get(k)
                    if y[k] is None:
                        continue
                    y[k] = None if v is None else y[k] + (v * r if k in MONEY else v)
        for key, (cost, dl) in (a.get("_cells") or {}).items():
            c = cells.setdefault(key, [0.0, 0.0])
            c[0] += cost * r
            c[1] += dl
        for k, v in (a.get("_ccid") or {}).items():
            ccid[k] += v * r
        for k, v in ((a.get("_extra") or {}).get("no_store") or {}).items():
            extra["no_store"][k] += v * r
    for dd in stores.values():
        for x in dd.values():
            for k in KEYS:
                if x[k] is not None:
                    x[k] = int(round(x[k])) if k in MONEY else round(x[k], 2)
    return stores, cells, dict(ccid), {"no_store": dict(extra["no_store"])}


def _q(v, p):
    """Linear-interpolated quantile of a non-empty sorted list."""
    if len(v) == 1:
        return v[0]
    i = p * (len(v) - 1)
    lo = int(i)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def _stats(vals):
    v = sorted(vals)
    if not v:
        return {"n": 0, "p10": None, "p50": None, "p90": None, "min": None, "max": None}
    r = lambda x: round(x, 4)
    return {"n": len(v), "p10": r(_q(v, .1)), "p50": r(_q(v, .5)), "p90": r(_q(v, .9)), "min": r(v[0]),
            "max": r(v[-1])}


def cov_block(stores, sids, num, den, keep):
    """Per store-day num(x) ÷ x[den] over `sids` and the days `keep(date)` with den > 0 → stats + weighted Σ÷Σ + over
    (days above OVER) + unknown (den > 0 but num unreadable)."""
    vals, sn, sd, unknown = [], 0.0, 0.0, 0
    for sid in sids:
        for d, x in sorted((stores.get(sid) or {}).items()):
            if not keep(d):
                continue
            dv = x.get(den)
            if dv is None:                          # the denominator itself could not be read
                unknown += 1
                continue
            if not dv:
                continue
            nv = num(x)
            if nv is None:
                unknown += 1
                continue
            vals.append(nv / dv)
            sn += nv
            sd += dv
    out = _stats(vals)
    out.update({"weighted": round(sn / sd, 4) if sd else None, "over": sum(1 for v in vals if v > OVER),
                "unknown": unknown})
    return out


def _k(k):
    return lambda x: x.get(k)


def _both(x):
    return None if x.get("p") is None or x.get("i") is None else x["p"] + x["i"]


def _acc(accts, kind):
    """(accounts where `kind` was accepted, accounts asked, {refusal code: accounts})."""
    asked = [a for a in accts.values() if _asked(a, kind)]
    codes = Counter()
    for a in asked:
        e = a["calls"][kind].get("err")
        if e:
            codes[e.get("code") or "HTTP %s" % e.get("http")] += 1
    return sum(1 for a in asked if _ok(a, kind)), len(asked), dict(codes)


def top_stores(stores, keep):
    """(stores ranked by settled campaign cost, total, top = the fewest stores holding ≥ TOP_SHARE of it)."""
    cost = {sid: sum(x["c"] for d, x in dd.items() if keep(d) and x.get("c")) for sid, dd in stores.items()}
    total = sum(cost.values())
    top, acc = [], 0
    for sid, v in sorted(cost.items(), key=lambda kv: (-kv[1], kv[0])):
        if v <= 0 or (total and acc >= TOP_SHARE * total):
            break
        top.append(sid)
        acc += v
    return cost, total, top, (round(acc / total, 4) if total else None)


def cache_size(cells, iso, keep_sids=None):
    """The would-be data/roas_geo_cache.json ({"v":1, "iso", "daily": {store: {date: {cc: [cost, downloads]}}}}) for
    the probe's days → its size, and × EXTRAP_DAYS / DAYS."""
    daily, used = {}, {}
    for (sid, d, cc), (cost, dl) in sorted(cells.items()):
        if keep_sids is not None and sid not in keep_sids:
            continue
        iso2 = iso.get(cc) or ("--" if cc == "none" else cc)
        used[cc] = iso2
        daily.setdefault(sid, {}).setdefault(d, {})[iso2] = [int(round(cost)), round(dl, 2)]
    body = json.dumps({"v": 1, "iso": used, "daily": daily}, sort_keys=True, separators=(",", ":")).encode()
    gz = len(gzip.compress(body, mtime=0))
    cells_n = sum(len(x) for dd in daily.values() for x in dd.values())
    store_days = sum(len(dd) for dd in daily.values())
    per_day = sorted(len(x) for dd in daily.values() for x in dd.values())
    f = EXTRAP_DAYS / DAYS
    return {"stores": len(daily), "store_days": store_days, "cells_28": cells_n,
            "cells_400_est": int(round(cells_n * f)),
            "countries_per_store_day_p50": _q(per_day, .5) if per_day else None, "json_bytes_28": len(body),
            "gz_bytes_28": gz, "gz_bytes_400_est": int(round(gz * f))}


def summary(rep):
    """G1–G8 and the verdict from the merged report (see the module doc)."""
    stores, accts, once = rep["stores"], rep["accounts"], rep["once"]
    settled_end, iso, ccid = rep["window"]["settled_end"], rep.get("iso") or {}, rep.get("ccid_cost") or {}
    settled = lambda d: d <= settled_end
    fresh = lambda d: d > settled_end
    cost, total, top, top_share = top_stores(stores, settled)
    spenders = sorted(s for s, v in cost.items() if v > 0)
    ga4 = rep.get("ga4_packages")

    ok, of, codes = _acc(accts, "G1P")
    mc = [(x["c"], x["cm"]) for dd in stores.values() for d, x in dd.items()
          if settled(d) and x.get("c") is not None and x.get("cm") is not None]
    mc_c, mc_m = sum(c for c, _ in mc), sum(m for _, m in mc)
    ptot = sum(ccid.values())
    no_store = (rep.get("extra") or {}).get("no_store") or {}
    ns_p = no_store.get("p", 0)
    g1 = {"accepted": ok, "of": of, "refused": codes, "base_ccy": rep.get("base_ccy"), "total_cost": int(round(total)),
          "stores_with_spend": len(spenders), "top": top, "top_share": top_share,
          "cov_top": cov_block(stores, top, _k("p"), "c", settled),
          "cov_all": cov_block(stores, spenders, _k("p"), "c", settled),
          "cov_fresh_top": cov_block(stores, top, _k("p"), "c", fresh),
          "cov_top_vs_multi": cov_block(stores, top, _k("p"), "cm", settled),
          "non_multi_share": round(1 - mc_m / mc_c, 4) if mc_c else None,
          "no_store_share": round(ns_p / (ptot + ns_p), 4) if ptot + ns_p else None,
          "no_country_share": round(ccid.get("none", 0) / ptot, 4) if ptot else None,
          "orphan_days": sum(1 for dd in stores.values() for d, x in dd.items()
                             if settled(d) and x.get("c") == 0 and (x.get("p") or 0) > 0),
          "per_store": {}}
    for sid in spenders:
        cb = cov_block(stores, [sid], _k("p"), "c", settled)
        g1["per_store"][sid] = {"share": round(cost[sid] / total, 4) if total else None,
                                "ga4": (sid in ga4) if ga4 is not None else None,
                                **{k: cb[k] for k in ("n", "p10", "p50", "min", "weighted", "unknown")}}
    ct = g1["cov_top"]
    g1["pass"] = bool(ok and ct["n"] and not ct["unknown"] and ct["p10"] is not None and ct["p10"] >= COV_PASS)

    iok, iof, icodes = _acc(accts, "G1I")
    g2 = {"accepted_interest": iok, "of": iof, "refused": icodes,
          "presence_top": ct, "interest_top": cov_block(stores, top, _k("i"), "c", settled),
          "both_top": cov_block(stores, top, _both, "c", settled),
          "presence_all": g1["cov_all"], "interest_all": cov_block(stores, spenders, _k("i"), "c", settled),
          "both_all": cov_block(stores, spenders, _both, "c", settled)}
    it = g2["interest_top"]
    interest_ok = bool(iok and it["n"] and not it["unknown"] and it["p10"] is not None and it["p10"] >= COV_PASS)

    uok, uof, ucodes = _acc(accts, "ULV")
    g3 = {"accepted": uok, "of": uof, "refused": ucodes, "cov_top": cov_block(stores, top, _k("u"), "c", settled),
          "cov_all": cov_block(stores, spenders, _k("u"), "c", settled)}
    ut = g3["cov_top"]
    g3["fallback_ok"] = bool(uok and ut["n"] and not ut["unknown"] and ut["p10"] is not None and ut["p10"] >= COV_PASS)
    g2["use"] = "presence" if g1["pass"] else "area_of_interest" if interest_ok else \
        "user_location" if g3["fallback_ok"] else None

    dok, dof, dcodes = _acc(accts, "G2")
    inst_ok = lambda x: x.get("inst") is not None and x["inst"] >= G4_MIN_INST
    with_inst = {s: {d: x for d, x in dd.items() if inst_ok(x)} for s, dd in stores.items()}
    g4 = {"accepted": dok, "of": dof, "refused": dcodes, "min_installs": G4_MIN_INST,
          "top": cov_block(with_inst, top, _k("dl"), "inst", settled),
          "all": cov_block(with_inst, sorted(stores), _k("dl"), "inst", settled),
          "days_inst_no_dl": sum(1 for dd in with_inst.values() for d, x in dd.items()
                                 if settled(d) and x.get("dl") == 0)}

    g5o = once.get("G5") or {}
    with_cost = sorted(k for k, v in ccid.items() if k != "none" and v > 0)
    unmapped = [k for k in with_cost if k not in iso]
    g5 = {"accepted": bool(g5o.get("ok")), "via": g5o.get("via"), "refused": g5o.get("err"), "countries": len(iso),
          "with_cost": len(with_cost), "unmapped_with_cost": len(unmapped),
          "unmapped_cost_share": round(sum(ccid[k] for k in unmapped) / ptot, 4) if ptot else None,
          "no_country_cost_share": g1["no_country_share"]}
    g5["pass"] = bool(g5["accepted"] and not unmapped)

    zones, zspend = Counter(), Counter()
    for a in accts.values():
        z = a.get("tz") or "unknown"
        zones[z] += 1
        zspend[z] += sum(x.get("c") or 0 for dd in (a.get("_days_base") or {}).values() for x in dd.values())
    zt = sum(zspend.values())
    g6 = {"roster_tz": bool((once.get("ROSTER") or {}).get("tz")), "accounts": len(accts), "by_zone": dict(zones),
          "zones": len([z for z in zones if z != "unknown"]),
          "spend_share_by_zone": {z: round(v / zt, 4) for z, v in zspend.items()} if zt else {}}

    cas = [a["ca"] for a in accts.values() if a.get("ca")]
    g7 = {"accepted": sum(1 for a in accts.values() if _ok(a, "CA") or _ok(a, "CA_MIN")),
          "of": sum(1 for a in accts.values() if _asked(a, "CA")),
          "fallback": sum(1 for a in accts.values() if _ok(a, "CA_MIN")),
          "refused": dict(Counter((((a["calls"].get("CA_MIN") or a["calls"].get("CA") or {}).get("err") or {})
                                   .get("code") or "?") for a in accts.values()
                                  if _asked(a, "CA") and not (_ok(a, "CA") or _ok(a, "CA_MIN")))),
          "actions": sum(c.get("actions", 0) for c in cas),
          "download_included": sum(c.get("download_included", 0) for c in cas)}
    for k in ("category", "type", "lookback", "include", "counting", "primary", "status"):
        tot = Counter()
        for c in cas:
            tot.update(c.get(k) or {})
        g7["by_" + k] = dict(tot)

    f = EXTRAP_DAYS / DAYS
    calls_by, sec_by = Counter(), Counter()
    per_acct = {}
    for aid, a in accts.items():
        for kind, c in (a.get("calls") or {}).items():
            calls_by[kind] += c.get("n", 0)
            sec_by[kind] += c.get("sec", 0.0)
        cr = [(a["calls"].get(k) or {}) for k in ("G1P", "G2")]
        rows_a, sec_a = sum(c.get("rows", 0) for c in cr), sum(c.get("sec", 0.0) for c in cr)
        per_acct[aid] = {"rows_28": rows_a, "sec_28": round(sec_a, 2), "rows_400_est": int(round(rows_a * f))}
    per_rows = [x["rows_28"] for x in per_acct.values()]
    per_sec = [x["sec_28"] for x in per_acct.values()]
    for kind, c in once.items():
        if isinstance(c, dict) and "n" in c:
            calls_by[kind] += c["n"]
            sec_by[kind] += c.get("sec", 0.0)
    rows28 = {k: sum((a["calls"].get(k) or {}).get("rows", 0) for a in accts.values()) for k in ("G1P", "G2")}
    sec28 = round(sec_by["G1P"] + sec_by["G2"], 2)
    g8 = {"calls": rep["counts"].get("calls"), "calls_by_kind": dict(calls_by),
          "sec_by_kind": {k: round(v, 2) for k, v in sec_by.items()},
          "rows_28": rows28, "rows_400_est": {k: int(round(v * f)) for k, v in rows28.items()},
          "sec_28": sec28, "sec_400_est": round(sec28 * f, 1),
          "per_account_max": {"rows_28": max(per_rows) if per_rows else 0,
                              "sec_28": round(max(per_sec), 2) if per_sec else 0.0},
          "per_account": per_acct,
          "cache": _safely(cache_size, rep.get("_cells") or {}, iso),
          "cache_ga4": _safely(cache_size, rep.get("_cells") or {}, iso, ga4) if ga4 is not None else None}

    verdict = {"g1_pass": g1["pass"], "g5_pass": g5["pass"], "use": g2["use"],
               "gads_geo_may_go_on": bool(g1["pass"] and g5["pass"]),
               "note": "GADS_GEO also needs the owner's yes (spec §8 Q5)"}
    return {"verdict": verdict, "g1": g1, "g2": g2, "g3": g3, "g4": g4, "g5": g5, "g6": g6, "g7": g7, "g8": g8}


# ── the run ─────────────────────────────────────────────────────────────────────────────────────

def window(now):
    today = now.date()
    end = today - timedelta(days=1)
    return {"start": (end - timedelta(days=DAYS - 1)).isoformat(), "end": end.isoformat(),
            "settled_end": (today - timedelta(days=SETTLED)).isoformat(), "days": DAYS}


def g5_map(run, once, ctx, first_account):
    """Q-G3 → {country id: ISO-2}, asked on the MCC, or on `first_account` when the MCC refuses it. Asked before the
    accounts, so a spent time budget never costs the map."""
    rec = {"calls": {}}
    rows = _call(run, rec, "G5", lambda: gads._search(ctx["mcc"], ctx["mcc"], ctx["dev"], ctx["token"], Q_G5))
    via = "mcc"
    if rows is None and first_account and "stop" not in rec["calls"]["G5"]:
        rows = _call(run, rec, "G5_ACCT", lambda: gads._search(first_account, ctx["mcc"], ctx["dev"], ctx["token"],
                                                               Q_G5))
        via = "account"
    c = rec["calls"]
    once["G5"] = {"n": sum(x.get("n", 0) for x in c.values()),
                  "sec": round(sum(x.get("sec", 0) for x in c.values()), 3),
                  "rows": len(rows or []), "ok": rows is not None, "via": via if rows is not None else None,
                  "err": [x.get("err") for x in c.values() if x.get("err")] or None}
    iso = {}
    for row in rows or []:
        g = row.get("geoTargetConstant") or {}
        k = _ccid({"countryCriterionId": g.get("id")})
        if k and g.get("countryCode"):
            iso[k] = g["countryCode"]
    return iso


def counts(rep, run):
    """The public counts (no ids, names, dates, money or ratios)."""
    accts = rep["accounts"]

    def ok_of(kind):
        ok, of, _ = _acc(accts, kind)
        return ok, of
    g1, g1i, ulv, g2 = ok_of("G1P"), ok_of("G1I"), ok_of("ULV"), ok_of("G2")
    zones = {a.get("tz") for a in accts.values() if a.get("tz")}
    spenders = sum(1 for dd in (rep.get("stores") or {}).values() if any((x.get("c") or 0) > 0 for x in dd.values()))
    return {"accounts": sum(1 for a in accts.values() if _asked(a, "SPEND")), "of": rep["once"].get("accounts", 0),
            "with_spend": sum(1 for a in accts.values() if _ok(a, "SPEND") and not a.get("no_spend")),
            "calls": run.calls, "errors": run.errors,
            "g1_ok": g1[0], "g1_of": g1[1], "g1i_ok": g1i[0], "g1i_of": g1i[1], "ulv_ok": ulv[0], "ulv_of": ulv[1],
            "g2_ok": g2[0], "g2_of": g2[1],
            "ca_ok": sum(1 for a in accts.values() if _ok(a, "CA") or _ok(a, "CA_MIN")),
            "ca_of": sum(1 for a in accts.values() if _asked(a, "CA")),
            "g5_ok": 1 if (rep["once"].get("G5") or {}).get("ok") else 0,
            "stores": spenders, "zones": len(zones), "stopped": 1 if run.stop else 0, "seconds": run.elapsed()}


COUNT_KEYS = ("accounts", "of", "with_spend", "calls", "errors", "g1_ok", "g1_of", "g1i_ok", "g1i_of", "ulv_ok",
              "ulv_of", "g2_ok", "g2_of", "ca_ok", "ca_of", "g5_ok", "stores", "zones", "stopped", "seconds")


def public_line(c):
    return ("gads geo probe: accounts %d/%d (with spend %d), calls %d, errors %d, geo cost accepted %d/%d, "
            "area-of-interest accepted %d/%d, user location accepted %d/%d, geo installs accepted %d/%d, "
            "conversion actions accepted %d/%d, country map accepted %d, stores with spend %d, time zones %d, "
            "stopped %d, %ds" % tuple(_int((c or {}).get(k)) for k in COUNT_KEYS))


def run_probe(s, token, now=None, budget=BUDGET_SEC, clock=time.monotonic, workers=WORKERS, max_accounts=0,
              packages=None, fx_fn=None, tick=TICK_SEC):
    """Probe every child account of the MCC → the report (dict). Never raises for one account's failure; prints
    counts-only progress."""
    run = Run(budget, clock)
    now = now or datetime.now(timezone.utc)
    win = window(now)
    mcc = str(s["google_ads_login_customer_id"]).replace("-", "")
    ctx = {"mcc": mcc, "dev": s["google_ads_dev_token"], "token": token, "start": win["start"], "end": win["end"]}
    once = {}
    rrec = {"calls": {}}
    with Beat(run, tick):
        roster = _call(run, rrec, "ROSTER", lambda: gads._child_accounts(mcc, ctx["dev"], token))
        r = rrec["calls"]["ROSTER"]
        once["ROSTER"] = {"n": r.get("n", 0), "sec": r.get("sec", 0.0), "ok": roster is not None,
                          "err": r.get("err"), "tz": bool(roster) and all("tz" in a for a in roster)}
        accounts = sorted(roster or [], key=lambda a: a["id"])
        once["accounts"] = len(accounts)
        if max_accounts and max_accounts > 0:
            accounts = accounts[:max_accounts]
        run.say("gads geo probe: %d account(s) to probe" % len(accounts))
        iso = _try(g5_map, run, once, ctx, accounts[0]["id"] if accounts else None, default={}) \
            if roster is not None else {}
        accts = {}

        def one(a):
            try:
                accts[a["id"]] = probe_account(run, ctx, a)
            except Exception as e:                   # a bug for one account must not cost the others
                accts[a["id"]] = {"ccy": a.get("currency") or "USD", "tz": a.get("tz"), "calls": {},
                                  "crash": type(e).__name__}

        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            list(ex.map(one, accounts))
    base, rates = _try(currency_rates, accts, fx_fn, default=("?", {}))
    stores, cells, ccid, extra = _try(merge, accts, rates, default=({}, {}, {}, {}))
    for a in accts.values():                        # G6's spend by zone, in the base currency
        r = rates.get(a["ccy"], 1.0)
        a["_days_base"] = {sid: {d: {"c": (x.get("c") or 0) * r} for d, x in dd.items()}
                           for sid, dd in (a.get("_days") or {}).items()}
    rep = {"v": 1, "kind": "gads_geo_probe", "at": now.isoformat(), "api": gads.API_VERSION, "window": win,
           "params": {"cov_pass": COV_PASS, "top_share": TOP_SHARE, "over": OVER, "g4_min_installs": G4_MIN_INST,
                      "extrap_days": EXTRAP_DAYS, "budget_sec": budget, "max_calls": run.max_calls,
                      "max_accounts": max_accounts or 0},
           "base_ccy": base, "rates": rates, "ga4_packages": sorted(packages) if packages is not None else None,
           "once": once, "accounts": accts, "stores": stores, "iso": iso,
           "ccid_cost": {k: int(round(v)) for k, v in ccid.items()}, "extra": extra, "_cells": cells,
           "stopped": run.stop}
    rep["counts"] = counts(rep, run)
    rep["summary"] = _safely(summary, rep)
    rep["verdict"] = (rep["summary"] or {}).get("verdict")
    rep.pop("_cells", None)
    for a in accts.values():
        for k in ("_days", "_cells", "_ccid", "_extra", "_days_base"):
            a.pop(k, None)
    return rep


def ads_settings(env):
    """The Google Ads settings exactly as config.settings() reads them (the same secrets refresh.yml passes)."""
    g = lambda k: (env.get(k) or "") or None
    return {"google_ads_dev_token": g("GOOGLE_ADS_DEVELOPER_TOKEN"),
            "google_ads_login_customer_id": (g("GOOGLE_ADS_LOGIN_CUSTOMER_ID") or "").replace("-", "") or None,
            "google_ads_refresh_token": g("GOOGLE_ADS_REFRESH_TOKEN"),
            "client_id": g("GOOGLE_ADS_CLIENT_ID") or g("GOOGLE_CLIENT_ID"),
            "client_secret": g("GOOGLE_ADS_CLIENT_SECRET") or g("GOOGLE_CLIENT_SECRET")}


def load_packages():
    """The GA4 apps' Play packages (the private state's fetch[*].package) or None — best-effort, never fatal."""
    try:
        st = _private_json(STATE_PATH)
    except (Exception, SystemExit):                  # _private_json sys.exits on a non-200
        return None
    pk = {str((v or {}).get("package")) for v in ((st or {}).get("fetch") or {}).values() if (v or {}).get("package")}
    return pk or None


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    s = ads_settings(env)
    if not all(s.values()):
        sys.exit("Google Ads secrets missing")      # stderr: hidden by the workflow step
    print("gads geo probe: start", flush=True)
    try:
        token = gads._access_token(s["client_id"], s["client_secret"], s["google_ads_refresh_token"])
    except Exception:
        print("gads geo probe: Google Ads sign-in failed", flush=True)
        sys.exit(1)
    packages = load_packages()
    print("gads geo probe: GA4 apps known %d" % len(packages or ()), flush=True)
    report = run_probe(s, token, now=now, clock=clock, max_accounts=_int(env.get("PROBE_MAX_ACCOUNTS")),
                       packages=packages)
    print(public_line(report["counts"]), flush=True)
    if not write_private(OUT_PATH, _dump(report), "gads geo probe"):
        sys.exit("private repo write failed")        # stderr: hidden by the workflow step
    print("gads geo probe: report written", flush=True)


if __name__ == "__main__":
    main()
