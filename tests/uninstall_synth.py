"""Synthetic GA4 for the Uninstall-tab tests and the frontend fixture — no network, no real data.

  * make_store(...)  → one app's store exactly as fetch.ga4_uninstall writes it (engine tests).
  * Truth            → one app's GA4 "reality": installs, per-install-day uninstall cells, actives,
                       updates, versions. Mutable, so late GA4 data can be simulated.
  * UniStub          → a Ga4App whose runReport answers from a Truth: honours the dimensions, the
                       event filter, the date range, orderBys and limit/offset paging, and checks every
                       request is pinned to the app's Android stream.
  * AdminFake        → the Admin API (accountSummaries / dataStreams / property meta) per owner token.
"""

import math
import random
import re
from datetime import date, timedelta

from admob_iq.fetch import ga4

END = date(2026, 9, 19)                   # the last settled GA4 day in most engine tests
# uninstalling users per 1,000 installs ON lag day N — D0 60%, D1 72%, D2 80%, D7 88.7%, D14 90.5%, D30
# 92.1%, then a thin tail to 93.1% by D60 (well under 100%, even with rounding and noise)
BASE_LAGS = {0: 600, 1: 120, 2: 80, 3: 30, 4: 20, 5: 15, 6: 12, 7: 10, 8: 4, 9: 3, 10: 3, 11: 2, 12: 2, 13: 2, 14: 2}
BASE_LAGS.update({n: 1 for n in range(15, 31)})
BASE_LAGS.update({n: 1 for n in range(33, 61, 3)})


def iso(d):
    return d.isoformat()


def make_store(days, new_per_day=1000, lags=None, bump=None, end=END, a28=100000, rate_fn=None, upd=None,
               versions=None, app_id="ca-app-pub-0000000000000000~0000000001", package="com.synthetic.app"):
    """`days` of history ending at `end`. new_per_day: int or fn(date). lags: {lag: per 1,000 installs}.
    bump: fn(install date) → {lag: ± per 1,000} added for that install day. a28: int or fn(date).
    rate_fn: fn(date) → uninstall rate per 1,000 a28 users (daily series, independent of the cells here).
    upd: fn(date) → app_update users. versions: fn(date) → {version: active users}."""
    lags = BASE_LAGS if lags is None else lags
    hs = end - timedelta(days=days - 1)
    daily, cohorts, vers = {}, {}, {}
    for i in range(days):
        c = hs + timedelta(days=i)
        n = new_per_day(c) if callable(new_per_day) else new_per_day
        per = dict(lags)
        for lag, u in ((bump(c) if bump else None) or {}).items():
            per[lag] = per.get(lag, 0) + u
        cells = {}
        for lag, u in per.items():
            if lag <= (end - c).days:
                v = int(round(n * u / 1000.0))
                if v:
                    cells[str(lag)] = v
        if cells:
            cohorts[iso(c)] = cells
        a = a28(c) if callable(a28) else a28
        r = rate_fn(c) if rate_fn else 5.0
        un = int(round(r * a / 1000.0))
        daily[iso(c)] = {"new": n, "a1": a // 4, "a28": a, "un": un, "un_ev": un, "upd": upd(c) if upd else 0}
        if versions:
            vers[iso(c)] = versions(c)
    return {"v": 1, "app_id": app_id, "package": package, "property_id": "p", "stream_id": "s",
            "time_zone": "Asia/Kolkata", "den": "a28", "history_start": iso(hs), "window_end": iso(end),
            "history_capped": False, "covered": [[iso(hs), iso(end)]], "daily": daily, "cohorts": cohorts,
            "unplaced": {}, "versions": vers,
            "flags": {"truncated": [], "thresholded": False, "kept_old_before": None},
            "full_at": "2026-09-21T01:00:00Z", "fetched_at": "2026-09-21T01:00:00Z",
            "next_rebuild": iso(end + timedelta(days=30))}


def run_daily(store, first, last, app_id="ca-app-pub-0000000000000000~0000000001", app="App", state=None):
    """The daily build, day after day: evaluate_app with window_end = each day from `first` to `last`, and
    after every run each alert that was due is marked sent (as mark_notified does) → (sent, state), sent =
    [(E, severity, family, text)] — every notification the owner would have got, in order."""
    from admob_iq.engine import uninstall as eng
    state = {} if state is None else state
    sent, E = [], first
    while E <= last:
        d, _ = eng.evaluate_app(dict(store, window_end=E.isoformat()), app_id, app, state, E.isoformat() + "T12:00:00Z")
        due = {a["id"]: a for a in d["alerts"] if a["notify"]}
        sent += [(E.isoformat(), a["severity"], a["family"], a["text"]) for a in due.values()]
        for ep in state.get("episodes", {}).values():
            if ep["id"] in due:
                ep["notified_at"] = E.isoformat() + "T12:00:00Z"
        E += timedelta(days=1)
    return sent, state


def rate_year(store, days=365):
    """run_daily for the daily-RATE alerts only (spikes, zero days, drift) over the store's last `days` days —
    the same engine steps evaluate_app takes (advance_streaks → rate_ready → update_episodes), without the
    cohort math, so a year of noise runs in a fraction of a second → {family: notifications}."""
    from admob_iq.engine import uninstall as eng
    ds = eng.daily_series(store)
    state, streak, since = {}, {}, {}
    out = {"rate_drift": 0, "rate_spike": 0, "rate_zero": 0}
    for n in range(ds["n"] - days + 1, ds["n"] + 1):
        E = ds["start"] + timedelta(days=n - 1)
        drift = eng.rate_drift(ds, n)
        eng.advance_streaks(streak, since, {"drift|up": bool(drift and drift["dir"] == "up"),
                                            "drift|down": bool(drift and drift["dir"] == "down")}, E)
        first = n == ds["n"] - days + 1
        for ep in eng.update_episodes(state, "a", E, eng.rate_ready(ds, drift, "a", streak, since, E, first, n),
                                      True, first, "now"):
            if ep["notified_at"] is None:
                out[ep["family"]] += 1
                ep["notified_at"] = "sent"
    return out


def noisy_store(sigma, seed, days=400, end=END, a28=100000, rate=5.0, weekend=1.07, poisson=False):
    """A STEADY app (nothing changes) whose daily uninstalls wobble: lognormal day-to-day noise `sigma` and a
    weekend bump, or pure counting (Poisson) noise → make_store."""
    rnd = random.Random(seed)
    memo = {}

    def rate_fn(c):
        if c not in memo:
            r = rate * (weekend if c.weekday() >= 5 else 1.0) * math.exp(rnd.gauss(0, sigma) - sigma * sigma / 2)
            if poisson:
                lam, k, t = r * a28 / 1000, 0, rnd.expovariate(1.0)
                while t < lam:
                    k, t = k + 1, t + rnd.expovariate(1.0)
                r = k * 1000 / a28
            memo[c] = r
        return memo[c]
    return make_store(days, 1000, end=end, a28=a28, rate_fn=rate_fn)


def truth_store(truth, end, app_id="ca-app-pub-0000000000000000~0000000001"):
    """What the full GA4 fetch stores for a Truth (installs, uninstalls and cells that add up, like real
    GA4 — make_store's daily uninstalls are independent of its cells)."""
    from admob_iq.fetch import ga4_uninstall as gu
    st = gu.fetch_full(UniStub(truth, "tok", "p", "s"), end, 1300)
    st.update(app_id=app_id, package="com.synthetic.app", property_id="p", stream_id="s", time_zone="UTC",
              fetched_at="2026-09-21T01:00:00Z")
    return st


# ── the fake GA4 Data API ────────────────────────────────────────────────────────────────────────

def ymd(d):
    return d.strftime("%Y%m%d")


class Truth:
    """One app's GA4 reality from `start` to `end`. cells[(install day | "(other)" , event day)] = users.
    Users whose first session is before `start` (old installs) uninstall too: `old[d]` per event day."""

    def __init__(self, start, end, new, lags=None, bump=None, old_per_day=0, hazard_x=None, upd=None,
                 versions=None, active_frac=0.25, a28_frac=0.5, base0=None, seed=7, noise=0.0):
        self.start, self.end = start, end
        self.reject_a28 = False
        self.thresholded = False
        self.new, self.cells, self.old, self.upd, self.vers = {}, {}, {}, {}, {}
        self.a1, self.a28 = {}, {}
        rnd = random.Random(seed)
        lags = BASE_LAGS if lags is None else lags
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        for c in days:
            n = new(c) if callable(new) else new
            self.new[c] = n
            per = dict(lags)
            for lag, u in ((bump(c) if bump else None) or {}).items():
                per[lag] = per.get(lag, 0) + u
            for lag, u in per.items():
                d = c + timedelta(days=lag)
                if d > end:
                    continue
                x = (hazard_x(d, lag) if hazard_x else 1.0) * u
                if noise:
                    x *= max(0.0, 1 + rnd.gauss(0, noise))
                v = int(round(n * x / 1000.0))
                if v > 0:
                    self.cells[(c, d)] = self.cells.get((c, d), 0) + v
        for d in days:
            self.old[d] = old_per_day(d) if callable(old_per_day) else old_per_day
            self.upd[d] = upd(d) if upd else 0
        un = self.un_by_day()
        # actives: everyone who opened the app in the window (a new install counts, even if it left the
        # same day) + a share of the installed base (users from before `start` included)
        base = float(20 * self.new[days[0]] if base0 is None else base0)
        for i, d in enumerate(days):
            base = max(0.0, base + self.new[d] - un.get(d, 0))
            last28 = sum(self.new[x] for x in days[max(0, i - 27):i + 1])
            self.a1[d] = int(self.new[d] + base * active_frac)
            self.a28[d] = int(last28 + base * a28_frac)
            if versions:
                self.vers[d] = versions(d, self.a1[d])
            elif self.a1[d]:
                self.vers[d] = {"1.0": self.a1[d]}

    def un_by_day(self):
        """app_remove users per event day (every install day + the old installs)."""
        out = dict(self.old)
        for (c, d), u in self.cells.items():
            out[d] = out.get(d, 0) + u
        return out

    def rows(self, dims, mets, start, end, events):
        """Every row GA4 would return (unsorted, unpaged) — zero rows are left out, as GA4 does."""
        days = [d for d in sorted(self.new) if start <= d <= end]
        un = self.un_by_day()
        out = []
        if dims == ["date"] and not events:
            for d in days:
                vals = {"newUsers": self.new[d], "activeUsers": self.a1[d], "active28DayUsers": self.a28[d]}
                if any(vals[m] for m in mets):
                    out.append(({"date": ymd(d)}, {m: vals[m] for m in mets}))
        elif dims == ["date", "eventName"]:
            for d in days:
                if "app_remove" in events and un.get(d):
                    u = un[d]
                    out.append(({"date": ymd(d), "eventName": "app_remove"},
                                {"totalUsers": u, "eventCount": u + u // 20}))
                if "app_update" in events and self.upd[d]:
                    out.append(({"date": ymd(d), "eventName": "app_update"},
                                {"totalUsers": self.upd[d], "eventCount": self.upd[d]}))
        elif dims == ["firstSessionDate", "date"]:
            assert events == ["app_remove"]
            for (c, d), u in self.cells.items():
                if start <= d <= end:
                    out.append(({"firstSessionDate": ymd(c) if isinstance(c, date) else c, "date": ymd(d)},
                                {"totalUsers": u}))
            for d in days:
                if self.old.get(d):           # old installs: a first-session day before the data starts
                    out.append(({"firstSessionDate": ymd(self.start - timedelta(days=400)), "date": ymd(d)},
                                {"totalUsers": self.old[d]}))
        elif dims == ["date", "appVersion"]:
            for d in days:
                for v, u in sorted((self.vers.get(d) or {}).items()):
                    if u:
                        out.append(({"date": ymd(d), "appVersion": v}, {"activeUsers": u}))
        else:
            raise AssertionError("unexpected report %s" % dims)
        return out


def _event_filter(body):
    ex = [e["filter"] for e in body["dimensionFilter"]["andGroup"]["expressions"]
          if e["filter"]["fieldName"] == "eventName"]
    if not ex:
        return None
    f = ex[0]
    return [f["stringFilter"]["value"]] if "stringFilter" in f else list(f["inListFilter"]["values"])


class UniStub(ga4.Ga4App):
    """Ga4App answering runReport from a Truth (per stream). `log` records every request body."""

    def __init__(self, truth, token, property_id, stream_id, log=None, quota=None, fail=None):
        super().__init__(token, property_id, stream_id)
        self.truth, self.log, self.quota_fn, self.fail = truth, log if log is not None else [], quota, fail

    def _post(self, method, body):
        self.calls += 1
        self.log.append((self.property_id, self.stream_id, body))
        assert method == "runReport"
        ex = [e["filter"] for e in body["dimensionFilter"]["andGroup"]["expressions"]]
        assert ex[0] == {"fieldName": "platform", "stringFilter": {"matchType": "EXACT", "value": "Android"}}
        assert ex[1] == {"fieldName": "streamId", "stringFilter": {"matchType": "EXACT", "value": self.stream_id}}
        assert body["returnPropertyQuota"] is True
        if self.fail:
            self.fail(body)                   # may raise, like _call does on an HTTP error
        dims = [d["name"] for d in body["dimensions"]]
        mets = [m["name"] for m in body["metrics"]]
        if "active28DayUsers" in mets and self.truth.reject_a28:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: Field active28DayUsers is not a valid metric")
        rng = body["dateRanges"][0]
        start, end = date.fromisoformat(rng["startDate"]), date.fromisoformat(rng["endDate"])
        rows = self.truth.rows(dims, mets, start, end, _event_filter(body))
        order = body.get("orderBys") or []
        assert {o["dimension"]["dimensionName"] for o in order} == set(dims), "every page needs a TOTAL order"
        for o in reversed(order):             # stable sorts, last key first
            k = o["dimension"]["dimensionName"]
            rows.sort(key=lambda r: r[0][k], reverse=bool(o.get("desc")))
        off, lim = int(body.get("offset") or 0), int(body.get("limit") or 10000)
        page = rows[off:off + lim]
        q = self.quota_fn(self) if self.quota_fn else {
            "tokensPerDay": {"consumed": 10, "remaining": 150000},
            "tokensPerHour": {"consumed": 10, "remaining": 35000},
            "tokensPerProjectPerHour": {"consumed": 10, "remaining": 13000}}
        return {"dimensionHeaders": [{"name": n} for n in dims], "metricHeaders": [{"name": n} for n in mets],
                "rows": [{"dimensionValues": [{"value": dv[n]} for n in dims],
                          "metricValues": [{"value": str(mv[n])} for n in mets]} for dv, mv in page],
                "rowCount": len(rows), "propertyQuota": q,
                "metadata": {"subjectToThresholding": True} if self.truth.thresholded else {}}


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body or {}
        self.text = ""

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._b


class AdminFake:
    """Admin API: `sees` = {access token: [property ids]}, `streams` = {property id: [(stream id, package)]}.
    `fail_streams` = {(token, property)} whose dataStreams call fails. Every call is logged."""

    def __init__(self, sees, streams, tz="Asia/Kolkata"):
        self.sees, self.streams, self.tz = sees, streams, tz
        self.fail_streams, self.calls = set(), []

    def get(self, url, headers=None, params=None, timeout=None):
        tok = headers["Authorization"].split(" ", 1)[1]
        self.calls.append(url)
        if url.endswith("/accountSummaries"):
            return Resp(body={"accountSummaries": [{"account": "accounts/1", "propertySummaries": [
                {"property": "properties/" + p, "displayName": "Prop " + p} for p in self.sees.get(tok, [])]}]})
        pid = url.split("/properties/")[1].split("/")[0]
        assert pid in self.sees.get(tok, [])
        if url.endswith("/dataStreams"):
            if (tok, pid) in self.fail_streams:
                return Resp(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "down"}})
            return Resp(body={"dataStreams": [
                {"name": "properties/%s/dataStreams/%s" % (pid, s), "type": "ANDROID_APP_DATA_STREAM",
                 "androidAppStreamData": {"packageName": p}} for s, p in self.streams.get(pid, [])]})
        return Resp(body={"timeZone": self.tz, "currencyCode": "INR"})

    def post(self, url, headers=None, json=None, timeout=None):
        raise AssertionError("Data API calls go through UniStub")


def wave(d, amp=0.08, period=7):
    """A weekly swing (weekends differ), deterministic per date."""
    return 1 + amp * math.sin(2 * math.pi * (d.toordinal() % period) / period)


# ── the §5 data contract, checked field by field ─────────────────────────────────────────────────

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_HEX12 = re.compile(r"^[0-9a-f]{12}$")


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _iso(v):
    return isinstance(v, str) and bool(_ISO.match(v))


def _keys(obj, keys, where):
    assert isinstance(obj, dict), where
    assert set(obj) == set(keys), "%s: %s" % (where, sorted(set(obj) ^ set(keys)))


def _frac_or_none(v):
    return v is None or (_num(v) and v >= 0)


def check_head(h, where):
    if h is None:
        return
    _keys(h, ("p", "prev", "delta_pp", "dir", "alert", "low_sample", "from", "to"), where)
    assert _frac_or_none(h["p"]) and _frac_or_none(h["prev"]) and (h["delta_pp"] is None or _num(h["delta_pp"]))
    assert h["dir"] in ("up", "down", None) and isinstance(h["alert"], bool) and isinstance(h["low_sample"], bool)
    assert _iso(h["from"]) and _iso(h["to"]), where


ALERT_KEYS = ("id", "source", "app_id", "app", "family", "dir", "severity", "unit", "checkpoint", "n", "also", "vs",
              "now", "before", "delta_pp", "rel", "z", "installs_from", "installs_to", "base_from", "base_to",
              "since", "day", "users", "opened", "last_seen", "fresh", "notify", "data_till", "message", "text")


def check_alert(a, closed=False):
    _keys(a, ALERT_KEYS + (("closed",) if closed else ()), "alert")
    assert a["source"] == "uninstall" and a["family"] in ("cohort", "rate_spike", "rate_drift", "rate_zero")
    assert a["dir"] in ("up", "down") and a["severity"] in ("warning", "watch", "good")
    assert a["unit"] == ("pct" if a["family"] == "cohort" else "per1k")
    assert a["id"].startswith(a["app_id"] + "|uninstall_" + a["family"] + "|ALL|" + a["dir"] + "|")
    if a["family"] == "cohort":
        assert a["checkpoint"] == "D%d" % a["n"] and isinstance(a["n"], int)
        assert all(x.startswith("D") for x in a["also"]) and set(a["vs"]) <= {"prev", "all"} and a["vs"]
        assert _num(a["delta_pp"]) and _num(a["z"]) and _iso(a["installs_from"]) and _iso(a["installs_to"])
    else:
        assert a["checkpoint"] is None and a["n"] is None and a["delta_pp"] is None and a["also"] == []
    if a["family"] == "rate_drift":
        assert _iso(a["since"]) and a["day"] is None
    if a["family"] in ("rate_spike", "rate_zero"):
        assert _iso(a["day"]) and a["since"] is None
    assert _num(a["now"]) and _num(a["before"]) and _num(a["rel"]) and isinstance(a["users"], int)
    for k in ("base_from", "base_to"):
        assert a[k] is None or _iso(a[k])
    assert _iso(a["opened"]) and _iso(a["last_seen"]) and _iso(a["data_till"])
    assert isinstance(a["fresh"], bool) and isinstance(a["notify"], bool)
    assert a["message"] == a["app"] + ": " + a["text"]
    assert re.search("[%s-%s]" % (chr(0x900), chr(0x97F)), a["message"]) is None
    if closed:
        assert _iso(a["closed"])


def check_summary(s):
    _keys(s, ("v", "status", "asset", "asset_v", "data_till_min", "data_till_max", "counts", "apps", "alerts",
              "alert_counts"), "summary")
    assert s["v"] == 1 and s["status"] in ("ok", "partial", "stale", "error") and s["asset"] == "uninstall.json.gz"
    assert _HEX12.match(s["asset_v"])
    for k in ("data_till_min", "data_till_max"):
        assert s[k] is None or _iso(s[k])
    _keys(s["counts"], ("selected", "with_ga4", "ready", "no_ga4", "failed", "deferred", "stale"), "counts")
    assert all(isinstance(v, int) for v in s["counts"].values())
    for r in s["apps"]:
        _keys(r, ("app_id", "app", "data_till", "stale", "ready", "stage", "rate7", "rate_med", "rate_dir", "head4",
                  "alerts"), "summary app")
        assert r["stage"] in ("naya", "badh_raha", "stable", None) and r["rate_dir"] in ("up", "down", "flat", None)
        assert (r["data_till"] is None or _iso(r["data_till"])) and isinstance(r["stale"], bool)
        assert r["rate7"] is None or _num(r["rate7"])
        _keys(r["head4"], ("D0", "D1", "D7", "D30"), "head4")
        for k, h in r["head4"].items():
            check_head(h, k)
        _keys(r["alerts"], ("warning", "watch", "good"), "row alerts")
    assert [r["app"].casefold() for r in s["apps"]] == sorted(r["app"].casefold() for r in s["apps"])
    for a in s["alerts"]:
        check_alert(a)
    _keys(s["alert_counts"], ("warning", "watch", "good"), "alert_counts")
    for sev in ("warning", "watch", "good"):
        assert s["alert_counts"][sev] == sum(1 for a in s["alerts"] if a["severity"] == sev)


def check_asset(asset, summary=None):
    _keys(asset, ("v", "consts", "apps", "no_ga4"), "asset")
    _keys(asset["consts"], ("lag_days", "band_days", "band_k", "recent_k", "prev_k", "head_k", "z", "min_pp",
                            "min_rel", "min_recent_users", "big_recent_users", "zoom_days"), "consts")
    for n in asset["no_ga4"]:
        _keys(n, ("app_id", "app", "package", "reason", "text"), "no_ga4")
        assert n["reason"] in ("no_package", "no_stream", "stream_list_failed", "not_fetched_yet", "fetch_failed",
                               "same_package")
    for a in asset["apps"]:
        _keys(a, ("app_id", "app", "package", "key", "tz", "den", "history_start", "data_till", "fetched_at", "stale",
                  "history_capped", "flags", "daily", "rate_now", "stage", "stage_why", "zoom", "checkpoints", "nmax",
                  "curve", "table", "head4", "lifetime", "triangle", "releases", "alerts", "alerts_closed"), "detail")
        assert _HEX12.match(a["key"]) and a["den"] in ("a28", "dau") and _iso(a["history_start"]) and _iso(a["data_till"])
        assert a["fetched_at"] is None or _TS.match(a["fetched_at"])
        _keys(a["flags"], ("truncated", "thresholded", "unplaced_users", "over_100", "kept_old_before"), "flags")
        H = (date.fromisoformat(a["data_till"]) - date.fromisoformat(a["history_start"])).days + 1
        _keys(a["daily"], ("start", "new", "un", "a28", "upd", "rate", "med", "lo", "hi", "breaks"), "daily")
        assert a["daily"]["start"] == a["history_start"]
        assert all(_iso(b) and a["history_start"] <= b <= a["data_till"] for b in a["daily"]["breaks"])
        for k in ("new", "un", "a28", "upd", "rate", "med", "lo", "hi"):
            assert len(a["daily"][k]) == H, k                              # every day, through data_till
        _keys(a["rate_now"], ("last7", "med", "lo", "hi", "dir", "out_of_band", "drift"), "rate_now")
        if a["rate_now"]["drift"]:
            _keys(a["rate_now"]["drift"], ("since", "before", "now", "rel", "z"), "drift")
        assert a["stage"] in ("naya", "badh_raha", "stable") and isinstance(a["stage_why"], str)
        if a["zoom"]:
            _keys(a["zoom"], ("until", "reason", "label"), "zoom")
            assert a["zoom"]["reason"] in ("release", "alert")
        assert a["checkpoints"] == sorted(set(a["checkpoints"])) and all(0 <= n <= a["nmax"] for n in a["checkpoints"])
        assert a["nmax"] == H - 7
        _keys(a["curve"], ("p", "lo", "hi", "users", "k", "inc"), "curve")
        assert all(len(v) == H for v in a["curve"].values())             # index = N, 0..H-1
        assert [t["n"] for t in a["table"]] == a["checkpoints"]
        for t in a["table"]:
            _keys(t, ("n", "key", "head", "recent", "prev", "all", "dir", "alert", "low_sample", "break_day"),
                  "table row")
            assert t["key"] == "D%d" % t["n"] and (t["break_day"] is None or t["break_day"] in a["daily"]["breaks"])
            _keys(t["head"], ("p", "lo", "hi", "users"), "table head")
            _keys(t["recent"], ("p", "users", "from", "to"), "table recent")
            for b in ("prev", "all"):
                if t[b] is not None:
                    _keys(t[b], ("p", "users", "from", "to", "delta_pp", "z", "fires"), "table " + b)
        _keys(a["head4"], ("D0", "D1", "D7", "D30"), "detail head4")
        _keys(a["lifetime"], ("p", "users", "un", "rate_all_med"), "lifetime")
        tri = a["triangle"]
        _keys(tri, ("cols", "ref", "rows"), "triangle")
        assert tri["cols"] == a["checkpoints"] and len(tri["ref"]) == len(tri["cols"])
        assert sum(r["days"] for r in tri["rows"]) == H                   # ALL rows, newest first
        for r in tri["rows"]:
            _keys(r, ("week", "from", "to", "days", "users", "partial", "p"), "triangle row")
            assert len(r["p"]) == len(tri["cols"])
        for r in a["releases"]:
            _keys(r, ("date", "version", "kind"), "release")
        for al in a["alerts"]:
            check_alert(al)
        for al in a["alerts_closed"]:
            check_alert(al, closed=True)
    if summary is not None:
        assert [a["app_id"] for a in asset["apps"]] == [r["app_id"] for r in summary["apps"]]
        assert sorted(al["id"] for a in asset["apps"] for al in a["alerts"]) == sorted(al["id"] for al in summary["alerts"])
        for a, r in zip(asset["apps"], summary["apps"]):
            assert a["head4"] == r["head4"] and a["app"] == r["app"]


def check_cohort_file(c, detail):
    _keys(c, ("v", "app_id", "start", "end", "new", "lags", "unplaced"), "cohort file")
    assert c["app_id"] == detail["app_id"] and c["start"] == detail["history_start"] and c["end"] == detail["data_till"]
    H = len(c["new"])
    assert len(c["lags"]) == H
    for i, lags in enumerate(c["lags"]):
        assert [l for l, _ in lags] == sorted(l for l, _ in lags) and all(0 <= l <= H - 1 - i for l, _ in lags)
