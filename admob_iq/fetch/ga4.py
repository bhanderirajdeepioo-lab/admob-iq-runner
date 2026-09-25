"""GA4 (Google Analytics 4 / Firebase) read-only access — Phase 0 uninstall capability probe.

Plain REST against two Google APIs, with an OAuth refresh token (analytics.readonly scope):
  * Admin API v1beta  — which properties this token sees, their timezone/currency, Android streams
  * Data API  v1beta  — runReport / runRealtimeReport for the actual numbers

EVERY report goes through Ga4App, which forces the request onto ONE app's Android stream
(platform == "Android" AND streamId == <id>): a GA4 property often holds several apps (and iOS/web
streams), and without that filter one app's uninstalls would silently include another's.

The probe_* functions each answer one "can GA4 give us X for this app?" question and return a small
dict with an "ok" verdict plus the evidence. They RAISE on API errors — the probe wraps each one so a
failure is recorded in the report instead of stopping the run. Nothing here prints anything: ids,
names and numbers must never reach the (public) Actions log.
"""

import json
import time
from datetime import datetime, timedelta

import requests

ADMIN = "https://analyticsadmin.googleapis.com/v1beta"
DATA = "https://analyticsdata.googleapis.com/v1beta"
PAUSE = 0.2                           # seconds between calls — stay far from per-property quotas
LAG_DAYS = 2                          # GA4 daily data (and Play-reported app_remove) settles over 24–48h,
                                      # so every window ends at today-2 in the property timezone
MAX_PAGES = 100                       # Admin API paging safety cap
NOT_SET = {"", "(not set)", "(other)", "(none)"}


def _sleep(s):
    time.sleep(s)                     # indirection so tests can skip the waits


def access_token(client_id, client_secret, refresh_token):
    """Same OAuth refresh as the Google Ads fetch (returns the bearer token string)."""
    from .google_ads import _access_token
    return _access_token(client_id, client_secret, refresh_token)


def parse_token_map(raw):
    """GA4_REFRESH_TOKENS secret — JSON {owner email: refresh_token} — → (map, problems).
    Missing/empty → ({}, 0); unparseable or not a JSON object → ({}, 1). A malformed entry (non-string
    or empty token) is dropped and counted on its own: one bad value never costs the rest of the map."""
    if not (raw or "").strip():
        return {}, 0
    try:
        m = json.loads(raw)
    except ValueError:
        return {}, 1
    if not isinstance(m, dict):
        return {}, 1
    out = {str(k).strip(): v.strip() for k, v in m.items() if isinstance(v, str) and v.strip() and str(k).strip()}
    return out, len(m) - len(out)


def _err(r):
    """'STATUS: message' out of a Google API error body; raw text as a fallback."""
    try:
        e = (r.json() or {}).get("error") or {}
        if e:
            return ("%s: %s" % (e.get("status") or e.get("code") or "?", e.get("message") or ""))[:600]
    except Exception:
        pass
    return (r.text or "")[:500]


def _call(method, url, token, body=None, params=None):
    """One HTTP call; retried ONCE on 429/5xx after a short backoff. Raises RuntimeError on failure."""
    headers = {"Authorization": "Bearer %s" % token}
    for attempt in (1, 2):
        if method == "GET":
            r = requests.get(url, headers=headers, params=params, timeout=60)
        else:
            r = requests.post(url, headers=headers, json=body, timeout=60)
        if attempt == 1 and (r.status_code == 429 or r.status_code >= 500):
            _sleep(3.0)
            continue
        break
    if not r.ok:
        raise RuntimeError("HTTP %s: %s" % (r.status_code, _err(r)))
    return r.json() or {}


# ── Admin API: discovery ─────────────────────────────────────────────────────────────────────────

def _paged(url, token, key, info=None):
    """All pages of a list call. Capped at MAX_PAGES and stops on a repeated page token, so a
    misbehaving API can never hang the run; either case sets info["truncated"] = True."""
    out, page = [], None
    for _ in range(MAX_PAGES):
        params = {"pageSize": 200}
        if page:
            params["pageToken"] = page
        j = _call("GET", url, token, params=params)
        out.extend(j.get(key) or [])
        nxt = j.get("nextPageToken")
        if not nxt:
            return out
        if nxt == page:
            break
        page = nxt
        _sleep(PAUSE)
    if info is not None:
        info["truncated"] = True
    return out


def list_properties(token, info=None):
    """Every GA4 property the token can read → [{property_id, account, display_name}]."""
    out = []
    for acc in _paged(ADMIN + "/accountSummaries", token, "accountSummaries", info):
        for p in acc.get("propertySummaries") or []:
            pid = (p.get("property") or "").split("/")[-1]
            if pid:
                out.append({"property_id": pid, "account": acc.get("account"),
                            "display_name": p.get("displayName")})
    return out


def property_meta(token, property_id):
    """Reporting timezone + currency — every GA4 'date' is in this timezone (T9)."""
    j = _call("GET", "%s/properties/%s" % (ADMIN, property_id), token)
    return {"time_zone": j.get("timeZone"), "currency": j.get("currencyCode")}


def android_streams(token, property_id, info=None):
    """The property's Android app streams → [{property_id, stream_id, package, firebase_app_id}]."""
    out = []
    for s in _paged("%s/properties/%s/dataStreams" % (ADMIN, property_id), token, "dataStreams", info):
        if s.get("type") != "ANDROID_APP_DATA_STREAM":
            continue
        a = s.get("androidAppStreamData") or {}
        out.append({"property_id": str(property_id), "stream_id": (s.get("name") or "").split("/")[-1],
                    "package": (a.get("packageName") or "").strip(), "firebase_app_id": a.get("firebaseAppId")})
    return out


# ── Data API: reports pinned to one Android stream ───────────────────────────────────────────────

def _exact(field, value):
    return {"filter": {"fieldName": field, "stringFilter": {"matchType": "EXACT", "value": str(value)}}}


def _in_list(field, values):
    return {"filter": {"fieldName": field, "inListFilter": {"values": [str(v) for v in values]}}}


def stream_filter(stream_id, event=None, events=None, extra=None):
    """platform == Android AND streamId == <id> [AND eventName == event | eventName in events]
    [AND any extra filter expressions]."""
    ex = [_exact("platform", "Android"), _exact("streamId", stream_id)]
    if event:
        ex.append(_exact("eventName", event))
    if events:
        ex.append(_in_list("eventName", events))
    ex.extend(extra or [])
    return {"andGroup": {"expressions": ex}}


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    return int(f) if f.is_integer() else f


def _rows(j):
    """Report response → [{dimension/metric name: value}] (metrics as numbers)."""
    dh = [h.get("name") for h in j.get("dimensionHeaders") or []]
    mh = [h.get("name") for h in j.get("metricHeaders") or []]
    out = []
    for r in j.get("rows") or []:
        # a missing value becomes "" (never None: None keys break sorted JSON output later)
        d = {n: (v or {}).get("value") or "" for n, v in zip(dh, r.get("dimensionValues") or [])}
        for n, v in zip(mh, r.get("metricValues") or []):
            d[n] = _num(v.get("value"))
        out.append(d)
    return out


class Ga4App:
    """One app's view of GA4. report()/realtime() ALWAYS apply the Android + stream filter."""

    def __init__(self, token, property_id, stream_id):
        self.token, self.property_id, self.stream_id = token, str(property_id), str(stream_id)
        self.quota = None              # latest propertyQuota snapshot from runReport
        self.realtime_quota = None
        self.calls = 0
        self.last_row_count = None     # rowCount of the last runReport (total rows, ignoring limit)

    def _post(self, method, body):
        if self.calls:
            _sleep(PAUSE)
        self.calls += 1
        return _call("POST", "%s/properties/%s:%s" % (DATA, self.property_id, method), self.token, body=body)

    def report(self, body, event=None, events=None, extra=None):
        body = dict(body, dimensionFilter=stream_filter(self.stream_id, event, events, extra),
                    returnPropertyQuota=True)
        j = self._post("runReport", body)
        self.quota = j.get("propertyQuota") or self.quota
        rows = _rows(j)
        self.last_row_count = _num(j["rowCount"]) if "rowCount" in j else len(rows)
        return rows

    def truncated(self, rows):
        """True when the last runReport had more rows than `limit` let through (the API cuts silently)."""
        return bool(self.last_row_count and self.last_row_count > len(rows))

    def realtime(self, body, event=None):
        body = dict(body, dimensionFilter=stream_filter(self.stream_id, event), returnPropertyQuota=True)
        j = self._post("runRealtimeReport", body)
        self.realtime_quota = j.get("propertyQuota") or self.realtime_quota
        return _rows(j)


# ── date helpers (GA4 dates are YYYYMMDD in the PROPERTY timezone) ───────────────────────────────

def window_end_in(tz_name, now=None, lag=LAG_DAYS):
    """Last SETTLED day in the property's timezone (UTC if the zone is unknown): today - LAG_DAYS.
    Yesterday is complete on the clock but GA4 is still processing it (up to ~48h), so using it would
    pull the newest day / week / D7 cohort low and bias every 'did it change' comparison."""
    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    now = now or datetime.now(tz)
    return (now.astimezone(tz) if now.tzinfo else now).date() - timedelta(days=lag)


def _range(end, days):
    return {"startDate": (end - timedelta(days=days - 1)).isoformat(), "endDate": end.isoformat()}


def _d(s):
    try:
        return datetime.strptime(str(s), "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def _dim(*names):
    return [{"name": n} for n in names]


def _top(pairs, n=20):
    return dict(sorted(pairs.items(), key=lambda kv: -kv[1])[:n])


def _sum_by(rows, key, metric):
    out = {}
    for r in rows:
        k = str(r.get(key) or "")
        out[k] = out.get(k, 0) + (r.get(metric) or 0)
    return out


def pearson(xs, ys):
    """Pearson correlation of two equal-length series; None when either is flat."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if not sxx or not syy:
        return None
    return round(sxy / (sxx * syy) ** 0.5, 4)


def _median(v):
    v = sorted(v)
    n = len(v)
    return (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2) if n else None


# ── the tests ────────────────────────────────────────────────────────────────────────────────────

def probe_base(ga, end):
    """Does the stream have traffic at all? activeUsers / newUsers / sessions by date, 30 days."""
    rows = ga.report({"dateRanges": [_range(end, 30)], "dimensions": _dim("date"),
                      "metrics": _dim("activeUsers", "newUsers", "sessions"), "limit": 1000})
    return {"ok": bool(rows), "days": len(rows),
            "active_user_days": sum(r["activeUsers"] for r in rows),
            "new_users": sum(r["newUsers"] for r in rows), "sessions": sum(r["sessions"] for r in rows),
            "daily": {r["date"]: [r["activeUsers"], r["newUsers"], r["sessions"]] for r in rows}}


def probe_t1(ga, end):
    """app_remove by date+appVersion and by date+country — version/country-wise uninstalls."""
    rng = [_range(end, 30)]
    v = ga.report({"dateRanges": rng, "dimensions": _dim("date", "appVersion"),
                   "metrics": _dim("eventCount", "totalUsers"), "limit": 10000}, event="app_remove")
    v_cut, v_n = ga.truncated(v), ga.last_row_count
    c = ga.report({"dateRanges": rng, "dimensions": _dim("date", "country"),
                   "metrics": _dim("eventCount", "totalUsers"), "limit": 10000}, event="app_remove")
    c_cut, c_n = ga.truncated(c), ga.last_row_count
    real = [r for r in v if r.get("appVersion") not in NOT_SET]
    ev = sum(r["eventCount"] for r in v)
    by_ver, by_cty = _sum_by(v, "appVersion", "eventCount"), _sum_by(c, "country", "eventCount")
    return {"ok": bool(v or c), "version_rows": len(v), "version_row_count": v_n, "version_truncated": v_cut,
            "country_row_count": c_n, "country_truncated": c_cut,
            "distinct_versions": len([k for k in by_ver if k not in NOT_SET]),
            "real_version_row_share": round(len(real) / len(v), 4) if v else None,
            "real_version_event_share": round(sum(r["eventCount"] for r in real) / ev, 4) if ev else None,
            "country_rows": len(c), "distinct_countries": len([k for k in by_cty if k not in NOT_SET]),
            "events_30d": ev, "by_version": _top(by_ver), "by_country": _top(by_cty)}


def probe_t1b(ga, end):
    """app_remove users by the user's FIRST Google Ads campaign — campaign-wise wasted spend."""
    rows = ga.report({"dateRanges": [_range(end, 30)], "dimensions": _dim("firstUserGoogleAdsCampaignId"),
                      "metrics": _dim("totalUsers"), "limit": 1000}, event="app_remove")
    users = sum(r["totalUsers"] for r in rows)
    tagged = [r for r in rows if r.get("firstUserGoogleAdsCampaignId") not in NOT_SET]
    share = round(sum(r["totalUsers"] for r in tagged) / users, 4) if users else None
    return {"ok": bool(tagged), "rows": len(rows),
            "set_row_share": round(len(tagged) / len(rows), 4) if rows else None, "set_user_share": share,
            "by_campaign": _top(_sum_by(rows, "firstUserGoogleAdsCampaignId", "totalUsers"))}


def probe_t2(ga, end, days=30):
    """app_remove by firstSessionDate × date → how many NEW users uninstall on D0 / D1 / D2–7.
    Only users whose first session is inside the window: old installs would add hundreds of
    firstSessionDate values per day and push the result past `limit` (the API cuts silently).
    Newest cohorts first, so if anything is ever cut it is the oldest, not the ones T13 uses."""
    first = [(end - timedelta(days=i)).strftime("%Y%m%d") for i in range(days)]
    rows = ga.report({"dateRanges": [_range(end, days)], "dimensions": _dim("firstSessionDate", "date"),
                      "metrics": _dim("totalUsers"), "limit": 10000,
                      "orderBys": [{"dimension": {"dimensionName": "firstSessionDate"}, "desc": True}]},
                     event="app_remove", extra=[_in_list("firstSessionDate", first)])
    cut, n = ga.truncated(rows), ga.last_row_count
    lags, by_cohort = {"d0": 0, "d1": 0, "d2_7": 0, "gt7": 0, "unknown": 0}, {}
    for r in rows:
        f, d = _d(r.get("firstSessionDate")), _d(r.get("date"))
        u = r["totalUsers"]
        if not f or not d:
            lags["unknown"] += u
            continue
        lag = (d - f).days
        lags["d0" if lag <= 0 else "d1" if lag == 1 else "d2_7" if lag <= 7 else "gt7"] += u
        if 0 <= lag <= 7:
            c = by_cohort.setdefault(f.strftime("%Y%m%d"), {})
            c[str(lag)] = c.get(str(lag), 0) + u
    return {"ok": bool(rows), "accepted": True, "rows": len(rows), "row_count": n, "truncated": cut,
            "first_session_scope": "first session within the %d-day window" % days,
            "users_by_lag": lags, "by_cohort": by_cohort}


def cohort_body(end, days=14):
    """One DAILY cohort per first-session day for the `days` settled days ending at `end`, D0..D7.
    Cohort requests must NOT carry top-level dateRanges — the dates live in each cohort."""
    cohorts = []
    for i in range(days - 1, -1, -1):
        d = (end - timedelta(days=i)).isoformat()
        cohorts.append({"name": "c" + d.replace("-", ""), "dimension": "firstSessionDate",
                        "dateRange": {"startDate": d, "endDate": d}})
    return {"dimensions": _dim("cohort", "cohortNthDay"),
            "metrics": _dim("cohortActiveUsers", "cohortTotalUsers"),
            "cohortSpec": {"cohorts": cohorts,
                           "cohortsRange": {"granularity": "DAILY", "startOffset": 0, "endOffset": 7}},
            "limit": 1000}


def probe_t3(ga, end):
    """New-user retention cohorts (D1/D7). Pooled only over cohorts whose day N is already complete."""
    rows = ga.report(cohort_body(end))
    cohorts = {}
    for r in rows:
        c = cohorts.setdefault(str(r.get("cohort") or "")[1:], {"total": 0, "active": {}})
        c["total"] = max(c["total"], r.get("cohortTotalUsers") or 0)
        try:
            c["active"][str(int(r.get("cohortNthDay")))] = r.get("cohortActiveUsers") or 0
        except (TypeError, ValueError):
            pass

    def pooled(n):
        tot = act = 0
        for k, c in cohorts.items():
            d = _d(k)
            if d and d + timedelta(days=n) <= end and c["total"]:
                tot += c["total"]
                act += c["active"].get(str(n), 0)
        return round(act / tot, 4) if tot else None
    d1, d7 = pooled(1), pooled(7)
    return {"ok": d1 is not None, "accepted": True, "rows": len(rows), "d1_retention": d1,
            "d7_retention": d7, "cohorts": cohorts}


def probe_t4(ga, end):
    """GA4-side ad revenue by version — for 'future revenue lost' per uninstalled user."""
    rows = ga.report({"dateRanges": [_range(end, 30)], "dimensions": _dim("date", "appVersion"),
                      "metrics": _dim("totalAdRevenue", "publisherAdImpressions"), "limit": 10000})
    cut, n = ga.truncated(rows), ga.last_row_count
    rev = round(sum(r["totalAdRevenue"] for r in rows), 2)
    return {"ok": rev > 0, "rows": len(rows), "row_count": n, "truncated": cut, "revenue_30d": rev,
            "impressions_30d": sum(r["publisherAdImpressions"] for r in rows),
            "by_version": {k: round(v, 2) for k, v in _top(_sum_by(rows, "appVersion", "totalAdRevenue")).items()}}


def probe_t5(ga, end):
    """Realtime app_remove by version, last 30 minutes. Zero rows is a VALID answer (quiet half hour)."""
    rows = ga.realtime({"dimensions": _dim("appVersion"), "metrics": _dim("eventCount"),
                        "minuteRanges": [{"name": "last30", "startMinutesAgo": 29, "endMinutesAgo": 0}],
                        "limit": 100}, event="app_remove")
    return {"ok": True, "rows": len(rows), "by_version": _top(_sum_by(rows, "appVersion", "eventCount"))}


def probe_t7_crash(ga, end):
    """crashAffectedUsers > 0 on any day ⇒ Crashlytics is linked (crash-driven uninstall hints)."""
    rows = ga.report({"dateRanges": [_range(end, 30)], "dimensions": _dim("date"),
                      "metrics": _dim("crashAffectedUsers"), "limit": 1000})
    tot = sum(r["crashAffectedUsers"] for r in rows)
    return {"ok": tot > 0, "rows": len(rows), "crash_affected_user_days": tot,
            "days_with_crashes": sum(1 for r in rows if r["crashAffectedUsers"])}


def probe_t7_screens(ga, end):
    """Top 15 screens by views, 7 days — does screen tracking exist (last-screen-before-uninstall)?"""
    rows = ga.report({"dateRanges": [_range(end, 7)], "dimensions": _dim("unifiedScreenClass"),
                      "metrics": _dim("screenPageViews"),
                      "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}], "limit": 15})
    return {"ok": any(r.get("unifiedScreenClass") not in NOT_SET for r in rows), "rows": len(rows),
            "top": [[r.get("unifiedScreenClass"), r["screenPageViews"]] for r in rows]}


def probe_t9(meta):
    return {"ok": bool(meta.get("time_zone") and meta.get("currency")), **meta}


def probe_t11(ga, end):
    """90 days of app_remove vs app_update per day + Pearson r — do uninstalls spike on update days?"""
    rows = ga.report({"dateRanges": [_range(end, 90)], "dimensions": _dim("date", "eventName"),
                      "metrics": _dim("eventCount"), "limit": 1000}, events=["app_remove", "app_update"])
    days = [(end - timedelta(days=i)).strftime("%Y%m%d") for i in range(89, -1, -1)]
    rem = {d: 0 for d in days}
    upd = {d: 0 for d in days}
    for r in rows:
        tgt = rem if r.get("eventName") == "app_remove" else upd if r.get("eventName") == "app_update" else None
        if tgt is not None and r.get("date") in tgt:
            tgt[r["date"]] += r["eventCount"]
    xs, ys = [rem[d] for d in days], [upd[d] for d in days]
    return {"ok": any(xs), "has_app_update": any(ys), "pearson_remove_vs_update": pearson(xs, ys),
            "app_remove": xs, "app_update": ys, "first_day": days[0]}


def probe_events(ga, end):
    """Top 40 events, 7 days — do splash/home-type events already exist?"""
    rows = ga.report({"dateRanges": [_range(end, 7)], "dimensions": _dim("eventName"),
                      "metrics": _dim("eventCount"),
                      "orderBys": [{"metric": {"metricName": "eventCount"}, "desc": True}], "limit": 40})
    names = [str(r.get("eventName") or "") for r in rows]
    low = [n.lower() for n in names]
    return {"ok": bool(rows), "rows": len(rows), "top": [[r.get("eventName"), r["eventCount"]] for r in rows],
            "has_app_remove": "app_remove" in names, "has_app_update": "app_update" in names,
            "splash_like": any("splash" in n for n in low), "home_like": any("home" in n for n in low)}


def probe_t12(ga, end, days=56):
    """Uninstall RATE and how it CHANGES: app_remove users per 1,000 active users, per day and per week
    over 8 weeks, last-7-days vs previous-7-days change, and spike days (robust median + 3·MAD)."""
    rng = [_range(end, days)]
    au = ga.report({"dateRanges": rng, "dimensions": _dim("date"), "metrics": _dim("activeUsers"), "limit": 1000})
    rm = ga.report({"dateRanges": rng, "dimensions": _dim("date"), "metrics": _dim("totalUsers"),
                    "limit": 1000}, event="app_remove")
    dau = {r.get("date"): r["activeUsers"] for r in au}
    rem = {r.get("date"): r["totalUsers"] for r in rm}
    keys = [(end - timedelta(days=i)).strftime("%Y%m%d") for i in range(days - 1, -1, -1)]
    daily = {k: round(rem.get(k, 0) * 1000 / dau[k], 3) for k in keys if dau.get(k)}

    def window(end_ago, n=7):             # per-1,000 active-user-days over n days ending end_ago days back
        ks = keys[len(keys) - end_ago - n:len(keys) - end_ago]
        a = sum(dau.get(k, 0) for k in ks)
        return round(sum(rem.get(k, 0) for k in ks) * 1000 / a, 3) if a else None
    weekly = [window(7 * w) for w in range(days // 7 - 1, -1, -1)]      # oldest → newest
    last7, prev7 = window(0), window(7)
    change = round((last7 - prev7) / prev7 * 100, 1) if last7 is not None and prev7 else None
    vals = list(daily.values())
    med = _median(vals)
    mad = _median([abs(v - med) for v in vals]) if vals else None
    # robust spread; floored at 25% of the median so a flat series (MAD 0) doesn't flag every wobble
    scale = max(1.4826 * (mad or 0), 0.25 * (med or 0))
    spikes = [k for k, v in daily.items() if scale and v > med + 3 * scale]
    return {"ok": len(daily) >= 14 and bool(rm), "days_with_rate": len(daily), "rate_per_1000_daily": daily,
            "weekly_rate_per_1000": weekly, "last7_rate": last7, "prev7_rate": prev7,
            "change_pct_last7_vs_prev7": change, "median_daily_rate": med, "spike_days": spikes}


def probe_t13(t2, t3, end):
    """Point 9, from T2 + T3 (no extra calls): of new users who churned by D7 (not active on day 7),
    how many actually UNINSTALLED vs went dormant — per cohort, and how that ratio CHANGES
    (older half of cohorts vs newer half)."""
    if not (t2.get("ok") or t2.get("accepted")) or not t3.get("cohorts"):
        return {"ok": False, "reason": "needs T2 and T3"}
    per = {}
    for k, c in sorted(t3["cohorts"].items()):
        d = _d(k)
        if not d or d + timedelta(days=7) > end or not c.get("total"):
            continue                                   # D7 not complete yet
        churned = c["total"] - c["active"].get("7", 0)
        un = sum((t2.get("by_cohort") or {}).get(k, {}).values())
        per[k] = {"new": c["total"], "churned_by_d7": churned, "uninstalled_by_d7": un,
                  "uninstall_share_of_churn": round(un / churned, 4) if churned > 0 else None}
    shares = [v["uninstall_share_of_churn"] for v in per.values() if v["uninstall_share_of_churn"] is not None]
    h = len(shares) // 2
    older = round(sum(shares[:h]) / h, 4) if h else None
    newer = round(sum(shares[h:]) / (len(shares) - h), 4) if len(shares) - h else None
    return {"ok": bool(shares), "cohorts": per, "avg_share": round(sum(shares) / len(shares), 4) if shares else None,
            "older_half_share": older, "newer_half_share": newer,
            "change_pts": round((newer - older) * 100, 2) if older is not None and newer is not None else None}
