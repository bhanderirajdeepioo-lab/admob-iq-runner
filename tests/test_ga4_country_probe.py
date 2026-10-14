"""GA4 country probe (admob_iq.fetch.ga4_country_probe) — offline, against a fake GA4 Data API (requests mocked) and a
fake read-only clone of the private repo, SYNTHETIC data only: every request shape (Q-B, the full Q-C without its
install-day list, the paid / organic split, the discovery reads, date × country totals, Q-T, app_remove by country,
the T5 dimensions and the metadata GET), the ties (per install-age band, lag-0 new users, per country, per day), the old
share of users past Q-B's window, "(other)" loss / sampling / thresholding / refusals kept as flags or HTTP classes, the
quota / server-error / time / call stops, resume, and a PUBLIC log that stays counts-only."""

import json
import os
import re
import threading
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_country_probe as cp
from admob_iq.fetch import ga4_uninstall as gu

NOW = datetime(2026, 10, 15, 6, 0, tzinfo=timezone.utc)
TODAY, END = date(2026, 10, 15), date(2026, 10, 13)
F = END - timedelta(days=cp.LATE)
P = cp.PIVOT
T1 = [P + timedelta(days=i) for i in (-3, -2, -1, 0, 1, 2)]
EMAIL_A, EMAIL_B = "owner.one@example.test", "owner.two@example.test"
RT_A, RT_B, TOK_A, TOK_B = "rt-PRIVATE-a", "rt-PRIVATE-b", "tok-PRIVATE-a", "tok-PRIVATE-b"
PID_A, PID_B, PID_C = "100200300", "100200400", "100200500"
SID_A, SID_B, SID_C = "9000000001", "9000000002", "9000000003"
PKG_A, PKG_B, PKG_C = "com.example.alpha", "com.example.beta", "com.example.gamma"
AID_A, AID_B, AID_C, AID_D = ("ca-app-pub-0000000000000000~%d" % i for i in (11, 12, 13, 14))
KEY_A, KEY_B, KEY_C = (gu.file_key(a) for a in (AID_A, AID_B, AID_C))
CAMP = "555000111"                                   # a synthetic Google Ads campaign id
CC = ("XA", "XB", "XC")                              # user-assigned ISO codes: never a real country
SECRETS = [EMAIL_A, EMAIL_B, RT_A, RT_B, TOK_A, TOK_B, PID_A, PID_B, PID_C, SID_A, SID_B, SID_C, PKG_A, PKG_B, PKG_C,
           AID_A, AID_B, AID_C, AID_D, KEY_A, KEY_B, KEY_C, CAMP, "PRIVATE", "DETAIL"]
AD, IAP = 0.002, 0.0001                              # ad / in-app revenue per active user a day (USD)
OLD = (500, 600)                                     # lags past Q-B's 427-day window


def ymd(d):
    return d.strftime("%Y%m%d")


class Truth:
    """One app's synthetic GA4: n installs a day since `start`; on day d the users of install day d − L: L 0 → n,
    1 → 30%, 7 → 10%, and fixed counts at 30, 100, 150, 200, 300, 400 (inside Q-B's window) and 500, 600 (outside:
    date-level reads only). Countries XA / XB / XC 50 / 30 / 20; 40% of each cell came from a Google Ads campaign
    (no_paid: none). Options: other_before (country splits of days before the pivot lump XC's lags ≥ 91 into
    "(other)"), sampled_after (country splits from the pivot report a 20% sample), thresh, no_total (totalRevenue
    refused with firstSessionDate), reject (dimensions GA4 refuses), meta ("ok" / "fail" → 403), meta_absent, custom
    (registered ad params)."""

    def __init__(self, start, n=1000, other_before=False, sampled_after=False, thresh=False, no_total=False,
                 reject=(), no_paid=False, meta="ok", meta_absent=(), custom=()):
        self.start, self.n, self.other_before, self.sampled_after = start, n, other_before, sampled_after
        self.thresh, self.no_total, self.reject, self.no_paid = thresh, no_total, set(reject), no_paid
        self.meta, self.meta_absent, self.custom = meta, set(meta_absent), set(custom)

    def lag_users(self):
        n = self.n
        return {0: n, 1: n * 3 // 10, 7: n // 10, 30: 50, 100: 40, 150: 40, 200: 30, 300: 30, 400: 20, 500: 200,
                600: 200}


def split(u):
    a, b = u * 5 // 10, u * 3 // 10
    return list(zip(CC, (a, b, u - a - b)))


def atoms(t, d):
    out = []
    for lag, u in t.lag_users().items():
        f = d - timedelta(days=lag)
        if f < t.start:
            continue
        for cc, v in split(u):
            k = 0 if t.no_paid else v * 4 // 10
            for paid, w in ((True, k), (False, v - k)):
                if not w:
                    continue
                out.append({"date": ymd(d), "lag": lag, "day": d, "firstSessionDate": ymd(f), "countryId": cc,
                            "act": w, "new": w if lag == 0 else 0,
                            "firstUserGoogleAdsCampaignId": CAMP if paid else "(not set)",
                            "firstUserCampaignId": CAMP if paid else "(not set)",
                            "firstUserDefaultChannelGroup": "Cross-network" if paid else "Organic Search",
                            "firstUserSourceMedium": "google / cpc" if paid else "google-play / organic",
                            "appVersion": "2.0" if f >= TODAY - timedelta(days=60) else "1.0",
                            "deviceCategory": "mobile", "operatingSystemVersion": "14", "adFormat": "Banner",
                            "adSourceName": "Network One", "adUnitName": "unit-one", "eventName": "",
                            "customEvent:ad_format": "banner", "customEvent:ad_unit_name": "unit-one",
                            "customEvent:ad_source": "network-one"})
    return out


def mets(a, names):
    if "tu" in a:
        v = {"totalUsers": a["tu"], "eventCount": a["ev"]}
    else:
        x = a["act"]
        v = {"activeUsers": x, "newUsers": a["new"], "totalAdRevenue": x * AD, "totalRevenue": x * (AD + IAP),
             "publisherAdImpressions": 3 * x, "eventCount": 5 * x, "totalUsers": x}
    return {m: v[m] for m in names}


def match(e, a):
    if "andGroup" in e:
        return all(match(x, a) for x in e["andGroup"]["expressions"])
    if "notExpression" in e:
        return not match(e["notExpression"], a)
    f = e["filter"]
    name = f["fieldName"]
    if name in ("platform", "streamId"):
        return True
    v = str(a.get(name, ""))
    if "stringFilter" in f:
        sf = f["stringFilter"]
        if sf.get("matchType", "EXACT") == "EXACT":
            return v == sf["value"]
        assert sf["matchType"] == "FULL_REGEXP"
        return re.fullmatch(sf["value"], v, re.I) is not None
    if "inListFilter" in f:
        return v in f["inListFilter"]["values"]
    raise AssertionError("unexpected filter")


def _fields(e):
    if "andGroup" in e:
        return [x for y in e["andGroup"]["expressions"] for x in _fields(y)]
    if "notExpression" in e:
        return _fields(e["notExpression"])
    return [e["filter"]["fieldName"]]


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body or {}
        self.text = json.dumps(self._b)

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._b


STD_DIMS = cp.CAND_NAMES + tuple(dm for _, dm, _ in cp.T5_DIMS) + ("countryId", "firstSessionDate", "date")


class FakeGA4:
    def __init__(self, truths, quota=None, fail=None):
        self.truths = truths                        # pid → (stream id, Truth)
        self.bodies, self.gets, self.fail, self.lock = [], [], fail, threading.Lock()
        self.remaining = {pid: (quota or {}).get(pid, 200000) for pid in truths}

    def _bad(self, st, pid):
        return Resp(st, {"error": {"code": st, "status": {400: "INVALID_ARGUMENT", 403: "PERMISSION_DENIED"}.get(
            st, "INTERNAL"), "message": "bad DETAIL " + pid}})

    def get(self, url, headers=None, params=None, timeout=None):
        assert headers["Authorization"] in ("Bearer " + TOK_A, "Bearer " + TOK_B)
        assert url.startswith(ga4.DATA + "/properties/") and url.endswith("/metadata")
        pid = url.split("/properties/")[1].split("/")[0]
        with self.lock:
            self.gets.append(pid)
        t = self.truths[pid][1]
        if t.meta == "fail":
            return self._bad(403, pid)
        dims = [{"apiName": n, "customDefinition": False} for n in STD_DIMS if n not in t.meta_absent]
        dims += [{"apiName": "customEvent:" + p, "customDefinition": True} for p in sorted(t.custom)]
        dims += [{"apiName": "customEvent:private_param", "customDefinition": True}]
        return Resp(body={"name": "properties/%s/metadata" % pid, "dimensions": dims, "metrics": []})

    def post(self, url, headers=None, json=None, timeout=None):
        pid = url.split("/properties/")[1].split(":")[0]
        assert url.endswith(":runReport")
        with self.lock:
            self.bodies.append((pid, json))
        st = self.fail(pid, json) if self.fail else None
        if st:
            return self._bad(st, pid)
        sid, t = self.truths[pid]
        ex = json["dimensionFilter"]["andGroup"]["expressions"]
        pinned = {(e["filter"]["fieldName"], (e["filter"].get("stringFilter") or {}).get("value"))
                  for e in ex if "filter" in e}
        assert ("streamId", sid) in pinned and ("platform", "Android") in pinned
        assert json.get("returnPropertyQuota") is True and "cohortSpec" not in json
        dims = [d["name"] for d in json["dimensions"]]
        names = [m["name"] for m in json["metrics"]]
        used = set(dims) | {x for e in ex for x in _fields(e)}
        if used & t.reject or (t.no_total and "totalRevenue" in names and "firstSessionDate" in dims) or \
                any(d.startswith("customEvent:") and d[12:] not in t.custom for d in dims):
            return self._bad(400, pid)
        event = next((e["filter"]["stringFilter"]["value"] for e in ex
                      if "filter" in e and e["filter"]["fieldName"] == "eventName"), None)
        (rg,) = json["dateRanges"]
        d, last = date.fromisoformat(rg["startDate"]), date.fromisoformat(rg["endDate"])
        got = []
        while d <= last:
            if event == "app_remove":
                got += [{"date": ymd(d), "countryId": cc, "eventName": "app_remove", "tu": v, "ev": v + 1}
                        for cc, v in split(30)] if d >= t.start else []
            else:
                got += [dict(a, eventName=event or "") for a in atoms(t, d)]
            d += timedelta(days=1)
        fsd = "firstSessionDate" in dims
        cty = fsd and "countryId" in dims
        out = []
        for a in got:
            if fsd and a["lag"] > 427:
                continue                             # GA4's install-day window
            if cty and t.other_before and a["day"] < P and a["lag"] >= 91 and a["countryId"] == "XC":
                a = dict(a, countryId="(other)", firstSessionDate="(other)")
            if match(json["dimensionFilter"], a):
                out.append(a)
        rows = {}
        for a in out:
            key = tuple(str(a.get(dm, "")) for dm in dims)
            cur = rows.setdefault(key, dict.fromkeys(names, 0))
            for m, v in mets(a, names).items():
                cur[m] += v
        rows = sorted(rows.items())
        off, lim = int(json.get("offset") or 0), int(json.get("limit") or 10000)
        meta = {"subjectToThresholding": t.thresh, "dataLossFromOtherRow": any("(other)" in k for k, _ in rows)}
        if json.get("currencyCode") == "USD":
            meta["currencyCode"] = "USD"
        if cty and t.sampled_after and date.fromisoformat(rg["startDate"]) >= P:
            meta["samplingMetadatas"] = [{"samplesReadCount": "200", "samplingSpaceSize": "1000"}]
        resp = {"dimensionHeaders": [{"name": n} for n in dims], "metricHeaders": [{"name": m} for m in names],
                "rows": [{"dimensionValues": [{"value": v} for v in k],
                          "metricValues": [{"value": str(r[m])} for m in names]} for k, r in rows[off:off + lim]],
                "rowCount": len(rows), "metadata": meta}
        if "TOTAL" in (json.get("metricAggregations") or []):
            resp["totals"] = [{"dimensionValues": [{"value": "RESERVED_TOTAL"} for _ in dims],
                               "metricValues": [{"value": str(sum(r[m] for _, r in rows))} for m in names]}]
        cost = 8 if dims[:2] == ["date", "countryId"] and not event else 3 if cty else 1
        with self.lock:
            self.remaining[pid] -= cost
            resp["propertyQuota"] = {"tokensPerDay": {"consumed": cost, "remaining": self.remaining[pid]}}
        return Resp(body=resp)


def truths(**kw):
    return {PID_A: (SID_A, Truth(TODAY - timedelta(days=900), custom=("ad_format", "ad_unit_name"), **kw.get("a", {}))),
            PID_B: (SID_B, Truth(TODAY - timedelta(days=700), other_before=True, thresh=True, no_total=True,
                                 reject=("firstUserGoogleAdsCampaignId",), **kw.get("b", {}))),
            PID_C: (SID_C, Truth(P - timedelta(days=1), n=400, sampled_after=True, no_paid=True, meta="fail",
                                 reject=("adUnitName",), **kw.get("c", {})))}


STATE = {"routes": {"by_package": {PKG_A: {"property_id": PID_A, "stream_id": SID_A, "owner": EMAIL_A},
                                   PKG_B: {"property_id": PID_B, "stream_id": SID_B, "owner": EMAIL_B},
                                   PKG_C: {"property_id": PID_C, "stream_id": SID_C, "owner": EMAIL_A}}},
         "tz": {PID_A: "UTC", PID_B: "UTC", PID_C: "UTC"},
         "fetch": {AID_A: {"package": PKG_A, "meta": {"history_start": (TODAY - timedelta(days=900)).isoformat()}},
                   AID_B: {"package": PKG_B, "meta": {"history_start": (TODAY - timedelta(days=700)).isoformat()}},
                   AID_C: {"package": PKG_C, "meta": {"history_start": (P - timedelta(days=1)).isoformat()}},
                   AID_D: {"package": "com.example.noroute"}}}
TOKENS = [(EMAIL_A, RT_A), (EMAIL_B, RT_B)]


@pytest.fixture
def fake(monkeypatch):
    def make(**kw):
        f = FakeGA4(kw.pop("truths", None) or truths(), **kw)
        monkeypatch.setattr(ga4.requests, "get", f.get)
        monkeypatch.setattr(ga4.requests, "post", f.post)
        return f
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: {RT_A: TOK_A, RT_B: TOK_B}[rt])
    return make


def _opts(**kw):
    o = cp.options({}, {})
    o.update(kw)
    return o


def _units(*pkgs):
    us = cp.units_from_state(STATE)
    return [u for u in us if u["package"] in pkgs] if pkgs else us


def _run(units=None, opts=None, **kw):
    return cp.run_probe(_units() if units is None else units, "cid", "sec", TOKENS, opts or _opts(), now=NOW, tick=0,
                        **kw)


def kind_of(b):
    dims = [d["name"] for d in b["dimensions"]]
    ex = b["dimensionFilter"]["andGroup"]["expressions"][2:]
    ev = [e["filter"]["stringFilter"]["value"] for e in ex if "filter" in e and e["filter"]["fieldName"] == "eventName"]
    if dims == ["firstSessionDate"]:
        return "QB"
    if dims == ["countryId", "firstSessionDate"]:
        return "QC" if not ex else "ORG" if "notExpression" in ex[0] else "PAID"
    if len(dims) == 1 and dims[0] in cp.CAND_NAMES:
        return "DISC"
    if dims == ["date", "countryId"]:
        return "RM" if ev == ["app_remove"] else "CT"
    if dims == ["date"]:
        return "QT"
    assert dims[0] == "date" and len(dims) == 2
    return ("CUSTOM:" if ev == ["ad_impression"] else "DIM:") + dims[1]


def kinds(bodies, pid=None):
    out = {}
    for p, b in bodies:
        if pid is None or p == pid:
            out.setdefault(kind_of(b), []).append(b)
    return out


def _core(b):
    return {k: v for k, v in b.items() if k not in ("dimensionFilter", "returnPropertyQuota", "limit", "offset",
                                                     "orderBys")}


# ── the plan ────────────────────────────────────────────────────────────────────────────────────

def test_days_windows_and_units_of_the_plan():
    assert cp.parse_days("") == cp.parse_days(None) == T1
    assert cp.parse_days("2+1/7") == [P - timedelta(days=14), P - timedelta(days=7), P]
    assert cp.parse_days("2026-07-27, 2026-07-20,2026-07-27") == [date(2026, 7, 20), date(2026, 7, 27)]
    for bad in ("3-3", "9+9", "2026-13-01", "1+1/0", "+"):
        with pytest.raises(ValueError):
            cp.parse_days(bad)
    a, b, c = _units()
    assert (a["key"], b["key"], c["key"]) == (KEY_A, KEY_B, KEY_C) and len(_units()) == 3      # no route: no unit
    pa = cp.app_plan(a, T1, P, 2, NOW)
    assert pa["F"] == F and pa["t1"] == [T1[5], T1[2], T1[4], T1[1], T1[3], T1[0]]          # alternating sides
    assert pa["t2"] == [T1[5], T1[2]] and pa["disc"] == T1[5]
    assert pa["t3"] == (F - timedelta(days=cp.T3_DAYS - 1), F) and pa["t3"][0] <= T1[0]
    assert pa["t4"] == (F - timedelta(days=29), F) and pa["t5"] == pa["t4"]
    assert pa["units"] == ["meta", "t3", "t2disc"] + ["day:" + d.isoformat() for d in pa["t1"]] + \
        ["t4", "t5:VER", "t5:DEVCAT", "t5:OSVER", "t5:ADFMT", "t5:ADSRC", "t5:ADUNIT"]
    pc = cp.app_plan(c, T1, P, 9, NOW)                                     # installs from the day before the pivot
    assert pc["t1"] == [T1[5], T1[2], T1[4], T1[3]] and pc["t2"] == pc["t1"]
    late = dict(c, history_start=(P + timedelta(days=10)).isoformat())
    pl = cp.app_plan(late, T1, P, 2, NOW)
    assert pl["t1"] == [] and pl["disc"] == F and pl["t3"][1] == F
    old = [date(2025, 1, 10), date(2025, 1, 20)]                            # far back: the block holds them, ends ≤ F
    po = cp.app_plan(a, old, date(2025, 1, 15), 2, NOW)
    assert po["t3"] == (old[0], old[0] + timedelta(days=cp.T3_DAYS - 1))
    o = cp.options({"days": "1+2", "pivot": "2026-08-01", "t2_days": "0", "resume": True, "max_calls": "40",
                    "apps": KEY_A}, {"COUNTRY_MAX_APPS": "2"})
    assert o["days"] == [date(2026, 7, 31), date(2026, 8, 1), date(2026, 8, 2)] and o["t2_days"] == 0
    assert o["resume"] is True and o["max_calls"] == 40 and o["apps"] == {KEY_A} and o["max_apps"] == 2
    d = cp.options({}, {})
    assert d["t2_days"] == cp.T2_DAYS and d["resume"] is False and d["max_calls"] == cp.MAX_CALLS and d["pivot"] == P


def test_the_paid_rules_are_the_filters_rules():
    assert cp.is_paid("firstUserGoogleAdsCampaignId", CAMP)
    assert not cp.is_paid("firstUserGoogleAdsCampaignId", "(not set)")
    assert not cp.is_paid("firstUserCampaignId", "") and not cp.is_paid("firstUserCampaignId", "(organic)")
    assert cp.is_paid("firstUserDefaultChannelGroup", "cross-network")
    assert not cp.is_paid("firstUserDefaultChannelGroup", "Organic Search")
    assert cp.is_paid("firstUserSourceMedium", "google / cpc")
    assert cp.is_paid("firstUserSourceMedium", "x / paid_social")
    assert not cp.is_paid("firstUserSourceMedium", "google-play / organic")
    assert cp.paid_expr("firstUserDefaultChannelGroup") == ga4._in_list("firstUserDefaultChannelGroup",
                                                                         cp.PAID_CHANNELS)
    e = cp.paid_expr("firstUserSourceMedium")["filter"]["stringFilter"]
    assert e["matchType"] == "FULL_REGEXP" and re.fullmatch(e["value"], "google / cpc")


# ── shapes and ties ─────────────────────────────────────────────────────────────────────────────

def test_every_request_shape_is_the_one_documented(fake):
    f = fake()
    rep = _run(_units(PKG_A))
    k = kinds(f.bodies)
    assert {n: len(v) for n, v in k.items()} == {
        "CT": 1, "QT": 1, "DISC": 4, "QB": 6, "QC": 6, "ORG": 2, "PAID": 2, "RM": 1, "DIM:appVersion": 1,
        "DIM:deviceCategory": 1, "DIM:operatingSystemVersion": 1, "DIM:adFormat": 1, "DIM:adSourceName": 1,
        "DIM:adUnitName": 1, "CUSTOM:customEvent:ad_format": 1, "CUSTOM:customEvent:ad_unit_name": 1}
    assert f.gets == [PID_A] and rep["counts"]["calls"] == 32
    order = cp.app_plan(_units(PKG_A)[0], T1, P, 2, NOW)["t1"]
    for kind, want_dims in (("QB", ("firstSessionDate",)), ("QC", ("countryId", "firstSessionDate"))):
        assert [_core(b) for b in k[kind]] == [gu._iday_body(d, d, want_dims) for d in order], kind
        for b in k[kind]:
            assert len(b["dimensionFilter"]["andGroup"]["expressions"]) == 2      # no install-day inList: every age
            assert b["limit"] == cp.PAGE_ROWS and b["metricAggregations"] == ["TOTAL"] and b["currencyCode"] == "USD"
    paid = cp.paid_expr("firstUserGoogleAdsCampaignId")
    assert paid == {"filter": {"fieldName": "firstUserGoogleAdsCampaignId",
                               "stringFilter": {"matchType": "FULL_REGEXP", "value": "[^(].*"}}}
    for kind, extra in (("ORG", {"notExpression": paid}), ("PAID", paid)):
        assert [_core(b) for b in k[kind]] == [gu._iday_body(d, d, ("countryId", "firstSessionDate"))
                                               for d in order[:2]]
        assert all(b["dimensionFilter"]["andGroup"]["expressions"][2:] == [extra] for b in k[kind])
    assert [_core(b) for b in k["DISC"]] == [cp.request("DISC", d=T1[5], cand=c)["body"] for c in cp.CAND_NAMES]
    assert [m["name"] for m in k["DISC"][0]["metrics"]] == list(cp.DISC_METS)
    a3 = F - timedelta(days=cp.T3_DAYS - 1)
    assert _core(k["CT"][0]) == gu._iday_body(a3, F, ("date", "countryId"), total_row=False)
    assert _core(k["QT"][0]) == gu._iday_body(a3, F, ("date",), total_row=False)
    rm = k["RM"][0]
    assert rm["dateRanges"] == [{"startDate": (F - timedelta(days=29)).isoformat(), "endDate": F.isoformat()}]
    assert [m["name"] for m in rm["metrics"]] == ["totalUsers", "eventCount"] and rm["metricAggregations"] == ["TOTAL"]
    assert rm["dimensionFilter"]["andGroup"]["expressions"][2] == ga4._exact("eventName", "app_remove")
    assert [m["name"] for m in k["DIM:appVersion"][0]["metrics"]] == ["activeUsers", "totalAdRevenue"]
    assert [m["name"] for m in k["DIM:adFormat"][0]["metrics"]] == list(cp.AD_METS)
    cu = k["CUSTOM:customEvent:ad_format"][0]
    assert cu["dimensionFilter"]["andGroup"]["expressions"][2] == ga4._exact("eventName", "ad_impression")
    assert [m["name"] for m in cu["metrics"]] == list(cp.CUSTOM_METS)


def _expect_old(t, d, cc=None):
    """The synthetic share of users past Q-B's window (revenue ∝ users) on day d [one country]."""
    tot = old = 0
    for lag, u in t.lag_users().items():
        if d - timedelta(days=lag) < t.start:
            continue
        v = dict(split(u))[cc] if cc else u
        tot += v
        old += v if lag > 427 else 0
    return old / tot


def test_a_whole_app_ties_every_piece(fake):
    fake()
    rep = _run(_units(PKG_A))
    a = rep["apps"][KEY_A]
    t = truths()[PID_A][1]
    assert a["complete"] is True and a["pending"] == 0 and "stopped" not in a and a["runs"] == 1
    assert set(a) >= {"key", "tz", "F", "plan", "units", "calls", "tokens"} and "package" not in a
    meta = a["units"]["meta"]
    assert meta["ok"] and meta["custom"] == 3 and meta["custom_ad"] == {"ad_format": "customEvent:ad_format",
                                                                        "ad_unit_name": "customEvent:ad_unit_name"}
    assert all(meta["has"].values()) and meta["done"]
    for d in T1:
        u = a["units"]["day:" + d.isoformat()]
        assert u["done"] and u["side"] == ("after" if d >= P else "before")
        qc, qb = u["QC"], u["QB"]
        assert qc["ok"] and not qc["loss"] and not qc["sampled"] and qc["oth_rows"] == 0 and qc["usd"] is True
        assert qc["countries"] == 3 and qb["win"] == qc["win"] == 400 and qc["total_r"] == 1.0
        assert 0 < qc["le90_rows"] < 1 and qc["rows"] > qb["rows"]
        for b in cp.TIE_KEYS:
            assert u["tie"]["rev"][b] == {"r": 1.0, "in": True, "judged": True}, (d, b)
        assert u["tie"]["n0"] == {"r": 1.0, "in": True, "judged": True}
        assert all(v == 1.0 for v in u["tie"]["act"].values())
        assert abs(u["tie"]["share"]["0_90"] - 1450 / 1610) < 2e-4
        assert abs(u["tie"]["share"]["91_427"] - 160 / 1610) < 2e-4
        old = u["old"]
        assert abs(old["day"] - _expect_old(t, d)) < 2e-4 and abs(old["day_qb"] - _expect_old(t, d)) < 2e-4
        assert [x["cc"] for x in old["top"]] == list(CC) and old["neg"] == 0 and old["countries"] == 3
        for x in old["top"]:
            assert abs(x["old"] - _expect_old(t, d, x["cc"])) < 2e-4 and abs(x["old_act"] - x["old"]) < 2e-4
        if d in (T1[5], T1[2]):                                            # the T2 days
            assert u["split"] == "firstUserGoogleAdsCampaignId"
            s = u["t2"]
            assert all(s["rev"][b]["in"] and s["rev"][b]["r"] == 1.0 for b in cp.TIE_KEYS) and s["n0"]["r"] == 1.0
            assert [x["cc"] for x in s["top"]] == list(CC) and all(x["in"] and x["r"] == 1.0 for x in s["top"])
            assert all(0.55 < v <= 0.7 for v in s["org_share"].values()) and 0.35 < s["paid_n0"] < 0.45
        else:
            assert "ORG" not in u and "t2" not in u
    disc = a["units"]["t2disc"]
    assert disc["pick"] == "firstUserGoogleAdsCampaignId" and disc["paid"] and disc["d"] == T1[5].isoformat()
    for c in cp.CAND_NAMES:
        assert disc[c]["ok"] and 0.35 < disc[c]["paid_act"] < 0.45 and disc[c]["rows"] == 2, c
    t3 = a["units"]["t3"]
    assert t3["done"] and t3["CT"]["countries"] == 3 and t3["CT"]["days"] == t3["QT"]["days"] == cp.T3_DAYS
    tie = t3["tie"]
    assert tie["days"] == tie["judged"] == tie["rev_in"] == tie["new_in"] == cp.T3_DAYS and tie["out_days"] == []
    assert tie["rev_r"]["p50"] == 1.0 and tie["act_r"]["p50"] == 1.0
    rm = a["units"]["t4"]["RM"]
    assert rm["ok"] and rm["countries"] == 3 and rm["days"] == 30 and rm["ev_vs_total"] == rm["users_vs_total"] == 1.0
    for k, _, _ in cp.T5_DIMS:
        assert a["units"]["t5:" + k]["ok"] and a["units"]["t5:" + k]["rows"] == (60 if k == "VER" else 30), k
    assert a["units"]["t5c:ad_format"]["ok"] and a["units"]["t5c:ad_unit_name"]["rows"] == 30
    sm = rep["summary"]
    for side in ("before", "after"):
        s1 = sm["t1"][side]
        assert s1["days"] == 3 and s1["QC"]["ok"] == 3 and s1["rev"]["366_427"]["inside"] == 3
        assert s1["n0"]["inside"] == 3 and s1["old"]["days"] == 3 and s1["old"]["neg"] == 0
        assert sm["t2"][side]["days"] == 1 and sm["t2"][side]["top"]["inside"] == 3
    assert sm["t2"]["picked"]["firstUserGoogleAdsCampaignId"] == 1 and sm["t2"]["paid_apps"] == 1
    assert sm["t3"]["rev_in"] == cp.T3_DAYS and sm["t4"]["ok"] == 1 and sm["t5"]["meta"]["custom_ad"]["ad_format"] == 1
    assert sm["cost"]["calls"] == 32 and sm["cost"]["by_kind"]["QC"]["calls"] == 6
    c = rep["counts"]
    assert (c["errors"], c["complete"], c["t1_ok"], c["t1_in_366_427"], c["t2_in_c"], c["t3_in"]) == \
        (0, 1, 6, 6, 6, cp.T3_DAYS)
    blob = json.dumps(rep)
    assert "private_param" not in blob and CAMP not in blob and PKG_A not in blob and PID_A not in blob
    json.loads(cp.pr._dump(rep))


def test_loss_before_the_pivot_refusals_and_thresholds_are_kept_as_flags(fake):
    f = fake()
    rep = _run(_units(PKG_B))
    b = rep["apps"][KEY_B]
    assert b["complete"] and b["no_total"] is True
    refused = [x for p, x in f.bodies if p == PID_B and "totalRevenue" in json.dumps(x["metrics"])
               and "firstSessionDate" in json.dumps(x["dimensions"])]
    assert len(refused) == 1                                               # refused once, never asked again
    for d in T1:
        u = b["units"]["day:" + d.isoformat()]
        qc = u["QC"]
        assert qc["thresh"] and u["QB"]["thresh"] and u["done"]
        if d < P:
            assert qc["loss"] and qc["oth_rows"] > 0 and qc["oth_rev"] > 0
            assert u["tie"]["rev"]["0_90"]["in"] and u["tie"]["n0"]["in"]
            for band in cp.LATE_BANDS + ("91_427",):
                assert not u["tie"]["rev"][band]["in"] and 0.75 < u["tie"]["rev"][band]["r"] < 0.85, band
            assert [x["cc"] for x in u["old"]["top"]][:2] == ["XA", "XB"]
        else:
            assert not qc["loss"] and qc["oth_rows"] == 0 and all(t["in"] for t in u["tie"]["rev"].values())
    disc = b["units"]["t2disc"]
    assert disc["firstUserGoogleAdsCampaignId"] == {**disc["firstUserGoogleAdsCampaignId"], "ok": False,
                                                    "err": {"http": 400, "status": "INVALID_ARGUMENT"}}
    assert disc["pick"] == "firstUserCampaignId" and disc["done"]
    before = b["units"]["day:" + T1[2].isoformat()]
    assert before["split"] == "firstUserCampaignId" and before["ORG"]["loss"] and before["PAID"]["loss"]
    assert not any(k.startswith("t5c:") for k in b["units"])              # no ad param registered
    sm = rep["summary"]
    assert sm["t1"]["before"]["QC"]["loss"] == 3 and sm["t1"]["after"]["QC"]["loss"] == 0
    assert sm["t1"]["before"]["rev"]["91_180"]["inside"] == 0 and sm["t1"]["after"]["rev"]["91_180"]["inside"] == 3
    assert sm["t2"]["disc"]["firstUserGoogleAdsCampaignId"]["refused"] == 1
    c = rep["counts"]
    assert (c["t1_loss_b"], c["t1_loss_a"], c["t1_thr"], c["errors"]) == (3, 0, 6, 0)
    assert "DETAIL" not in json.dumps(rep)


def test_a_young_sampled_app_without_paid_users_and_without_metadata(fake):
    f = fake()
    rep = _run(_units(PKG_C))
    c = rep["apps"][KEY_C]
    assert c["complete"] and c["plan"]["t1"] == [d.isoformat() for d in (T1[5], T1[2], T1[4], T1[3])]
    assert c["units"]["meta"] == {**c["units"]["meta"], "ok": False, "done": True,
                                  "err": {"http": 403, "status": "PERMISSION_DENIED"}}
    disc = c["units"]["t2disc"]
    assert disc["pick"] == "firstUserGoogleAdsCampaignId" and disc["paid"] is False
    assert all(disc[k]["paid_act"] == 0.0 for k in cp.CAND_NAMES)
    for d in (T1[5], T1[4], T1[3]):
        qc = c["units"]["day:" + d.isoformat()]["QC"]
        assert qc["sampled"] and qc["smp_frac"] == 0.2
    s = c["units"]["day:" + T1[5].isoformat()]["t2"]
    assert s["paid_n0"] == 0.0 and s["org_share"]["0_90"] == 1.0 and s["rev"]["0_90"]["in"]
    assert all(v is None for b, v in s["org_share"].items() if b != "0_90")    # no install older than the app
    old = c["units"]["day:" + T1[2].isoformat()]
    assert not old["QC"]["sampled"] and old["old"]["day"] == 0.0           # nobody is older than the app
    assert c["units"]["t5:ADUNIT"]["err"] == {"http": 400, "status": "INVALID_ARGUMENT"}
    assert c["units"]["t5:ADUNIT"]["done"] and c["units"]["t5:ADFMT"]["ok"]
    assert len(f.bodies) == 2 + 4 + 4 * 2 + 2 * 2 + 1 + 6 and f.gets == [PID_C]
    sm = rep["summary"]
    assert sm["t5"]["ADUNIT"]["refused"] == 1 and sm["t5"]["meta"]["ok"] == 0
    assert sm["t1"]["after"]["QC"]["sampled"] == 3
    assert rep["counts"]["errors"] == 0


def test_a_dimension_the_metadata_lacks_is_not_asked(fake):
    f = fake(truths=truths(a={"meta_absent": ("adSourceName", "firstUserSourceMedium")}))
    rep = _run(_units(PKG_A))
    u = rep["apps"][KEY_A]["units"]
    assert u["t5:ADSRC"] == {**u["t5:ADSRC"], "absent": True, "done": True, "ok": False}
    assert u["t2disc"]["firstUserSourceMedium"] == {"ok": False, "absent": True}
    assert "DIM:adSourceName" not in kinds(f.bodies) and len(kinds(f.bodies)["DISC"]) == 3
    assert rep["apps"][KEY_A]["complete"] and rep["summary"]["t5"]["ADSRC"]["absent"] == 1


# ── stops and resume ────────────────────────────────────────────────────────────────────────────

def test_low_quota_stops_that_property_politely_and_the_others_go_on(fake):
    f = fake(quota={PID_C: 100004})                          # under half the day's tokens after its first report
    rep = _run()
    c = rep["apps"][KEY_C]
    assert c["stopped"] == "quota_low" and not c["complete"]
    assert c["units"]["t3"]["CT"]["ok"] and c["units"]["t3"]["stopped"] == "quota_low" and not c["units"]["t3"]["done"]
    assert sum(1 for p, _ in f.bodies if p == PID_C) == 1
    assert rep["apps"][KEY_A]["complete"] and rep["apps"][KEY_B]["complete"]
    assert rep["counts"]["quota_low"] == 1 and rep["counts"]["complete"] == 2


def test_server_errors_stop_the_property_after_two_failed_calls(fake):
    f = fake(fail=lambda pid, b: 500 if pid == PID_A and b["dimensions"][0]["name"] == "date" else None)
    rep = _run(_units(PKG_A))
    a = rep["apps"][KEY_A]
    assert a["units"]["t3"]["CT"]["err"] == {"http": 500, "status": "INTERNAL"} and not a["units"]["t3"]["done"]
    assert a["stopped"] == "server_errors" and a["server_errors"] == 2
    assert len(f.bodies) == 4                                              # CT and QT, each retried once by ga4._call
    assert rep["counts"]["errors"] == 2 and "DETAIL" not in json.dumps(rep)


def test_the_time_budget_stops_new_calls_and_the_report_is_still_whole(fake):
    f = fake()
    ticks = iter([0.0])
    rep = _run(opts=_opts(budget=10), clock=lambda: next(ticks, 99.0))
    assert not f.bodies and not f.gets and rep["counts"]["calls"] == 0
    assert {a["stopped"] for a in rep["apps"].values()} == {"budget"}
    assert set(rep["summary"]) >= {"t1", "t2", "t3", "t4", "t5", "cost"}
    assert cp.public_lines(rep["counts"])[-1].startswith("country probe: apps complete 0/3, probed now 3, calls 0, ")


def test_the_per_app_call_cap_stops_that_app_only(fake):
    f = fake()
    rep = _run(_units(PKG_A, PKG_B), opts=_opts(app_calls=5))
    for key, pid in ((KEY_A, PID_A), (KEY_B, PID_B)):
        a = rep["apps"][key]
        assert a["stopped"] == "app_cap" and not a["complete"] and a["pending"] > 0
        assert sum(1 for p, _ in f.bodies if p == pid) + f.gets.count(pid) == 5
    assert rep["counts"]["stopped"] == 2 and rep["counts"]["quota_low"] == 0


def test_without_a_clone_the_routes_come_from_the_api_and_there_is_no_last_report(fake, monkeypatch, tmp_path):
    fake()
    put = {}

    def private(path):
        if path == cp.STATE_PATH:
            return STATE
        raise SystemExit("HTTP 404")                                       # no report yet
    monkeypatch.setattr(cp, "_private_json", private)
    monkeypatch.setattr(cp.sp, "_private_json", private)
    monkeypatch.setattr(cp.pr, "write_private", lambda path, text, msg: bool(put.update({path: text})) or True)
    cp.main(_env(str(tmp_path / "absent"), tmp_path, max_apps="1", resume=True), now=NOW)
    rep = json.loads(put[cp.OUT_PATH])
    assert set(rep["apps"]) == {KEY_A} and rep["apps"][KEY_A]["complete"] and rep["rules"]["resume"] is True
    assert rep["summary"]["cost"]["calls"] == 32 == rep["apps"][KEY_A]["cost_all"]["QC"]["calls"] + 26


def _clone(root, report=None):
    os.makedirs(os.path.join(root, "data", "ga4_uninstall"), exist_ok=True)
    with open(os.path.join(root, "data", "ga4_uninstall", "state.json"), "w") as fh:
        json.dump(STATE, fh)
    if report is not None:
        os.makedirs(os.path.join(root, "ga4"), exist_ok=True)
        with open(os.path.join(root, cp.OUT_PATH), "w") as fh:
            fh.write(report)
    return root


def _env(root, tmp_path, **inputs):
    ev = tmp_path / ("event%d.json" % len(os.listdir(tmp_path)))
    ev.write_text(json.dumps({"inputs": inputs}))
    return {"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec", "COUNTRY_DATA_DIR": root,
            "GA4_REFRESH_TOKENS": json.dumps({EMAIL_A: RT_A, EMAIL_B: RT_B}), "GITHUB_EVENT_PATH": str(ev)}


def test_resume_asks_only_what_is_not_done_and_never_loses_an_app(fake, monkeypatch, capsys, tmp_path):
    f = fake()
    put = {}
    monkeypatch.setattr(cp.pr, "write_private", lambda path, text, msg: bool(put.update({path: text})) or True)
    monkeypatch.setattr(cp, "_private_json", lambda path: pytest.fail("the clone holds everything"))
    root = _clone(str(tmp_path / "_private"))
    cp.main(_env(root, tmp_path, max_calls="15", apps=KEY_A), now=NOW)
    r1 = json.loads(put[cp.OUT_PATH])
    a = r1["apps"][KEY_A]
    assert a["stopped"] == "calls" and not a["complete"] and r1["counts"]["calls"] == 15
    done = sorted(k for k, v in a["units"].items() if v["done"])
    assert done == sorted(["meta", "t3", "t2disc", "day:" + T1[5].isoformat(), "day:" + T1[2].isoformat()])
    cut = a["units"]["day:" + T1[4].isoformat()]
    assert cut["done"] is False and cut["stopped"] == "calls" and "QB" not in cut
    n1 = len(f.bodies)
    _clone(root, put[cp.OUT_PATH])                                         # the next run's clone holds the report
    cp.main(_env(root, tmp_path, resume=True), now=NOW)
    r2 = json.loads(put[cp.OUT_PATH])
    asked = kinds(f.bodies[n1:], PID_A)                                    # B and C: asked for the first time
    assert {k: len(v) for k, v in asked.items() if k in ("CT", "QT", "DISC", "QB", "QC", "ORG")} == \
        {"CT": 1, "QT": 1, "QB": 4, "QC": 4}                               # t3 again (the days need it), no DISC
    assert sum(1 for p, _ in f.bodies[n1:] if p == PID_A) == 2 + 8 + 1 + 6 + 2 and f.gets.count(PID_A) == 1
    a2 = r2["apps"][KEY_A]
    assert a2["complete"] and a2["runs"] == 2 and a2["units"]["t2disc"] == a["units"]["t2disc"]
    assert a2["cost_all"]["QB"]["calls"] == 6 and a2["calls"]["QB"]["calls"] == 4      # every run's cost; this one's
    assert r2["summary"]["cost"]["calls"] == (15 + 19) + 31 + 26             # A over two runs, B (2 refused), C
    assert a2["units"]["day:" + T1[5].isoformat()] == a["units"]["day:" + T1[5].isoformat()]
    assert all(a2["units"]["day:" + d.isoformat()]["old"]["neg"] == 0 for d in T1)
    assert r2["apps"][KEY_B]["complete"] and r2["apps"][KEY_C]["complete"]
    n2 = len(f.bodies)
    _clone(root, put[cp.OUT_PATH])
    cp.main(_env(root, tmp_path, resume=True), now=NOW)                    # every app complete: nothing asked
    assert len(f.bodies) == n2 and set(json.loads(put[cp.OUT_PATH])["apps"]) == {KEY_A, KEY_B, KEY_C}
    out = capsys.readouterr().out
    assert "country probe: 0 app(s) to probe, 3 complete carried over, resuming" in out


def test_the_public_log_is_counts_only(fake, monkeypatch, capsys, tmp_path):
    fake()
    put = {}
    monkeypatch.setattr(cp.pr, "write_private", lambda path, text, msg: bool(put.update({path: text})) or True)
    root = _clone(str(tmp_path / "_private"))
    cp.main(_env(root, tmp_path, apps="%s,%s" % (PKG_A, KEY_B), days="3+3", pivot=P.isoformat()), now=NOW)
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "country probe: 2 app(s) to probe, 0 complete carried over"
    assert lines[-1] == "country probe: report written"
    for p in ("T1 ", "T2 ", "T3 ", "T4 ", "T5 ", "country probe: apps complete "):
        assert sum(1 for x in lines if x.startswith(p)) == 1, p
    assert all(re.match(r"(country (probe|progress): |T[1-5] )", x) for x in lines)
    body = "\n".join(lines)
    for s in SECRETS + ["2026-", "XA", "XB", "XC", "0.", "$", "(not set)", "private_param", "ad_format"]:
        assert s not in body, s
    t1 = [x for x in lines if x.startswith("T1 ")][0]
    assert t1.startswith("T1 full Q-C: days read 12/12 (before 6, after 6), (other) loss before 3 after 0, ")
    assert "Ads campaign id 1, campaign id 1, channel group 0, source/medium 0" in body
    rep = json.loads(put[cp.OUT_PATH])
    assert set(rep["apps"]) == {KEY_A, KEY_B} and rep["rules"]["days"] == [d.isoformat() for d in T1]


def test_a_days_input_not_understood_stops_before_any_call(fake, monkeypatch, capsys, tmp_path):
    f = fake()
    root = _clone(str(tmp_path / "_private"))
    with pytest.raises(SystemExit):
        cp.main(_env(root, tmp_path, days="sometime"), now=NOW)
    assert not f.bodies and capsys.readouterr().out.strip() == "country probe: the days / pivot input is not understood"
    with pytest.raises(SystemExit):
        cp.main({"GA4_CLIENT_ID": "cid"}, now=NOW)


def test_the_report_is_still_written_when_the_bookkeeping_has_a_bug(fake, monkeypatch):
    fake()
    monkeypatch.setattr(cp, "t1_tie", lambda qc, qb: 1 / 0)
    monkeypatch.setattr(cp, "summary", lambda apps: [][1])
    rep = _run(_units(PKG_A))
    u = rep["apps"][KEY_A]["units"]["day:" + T1[0].isoformat()]
    assert u["tie"] == {"err": {"type": "ZeroDivisionError"}} and u["QC"]["ok"] and u["done"]
    assert rep["summary"] == {"err": {"type": "IndexError"}} and rep["counts"]["errors"] == 6
    json.loads(cp.pr._dump(rep))


def test_a_counts_only_heartbeat_at_least_every_minute(capsys):
    t = iter(range(0, 1000, 25))
    run = cp.Run(clock=lambda: float(next(t)))
    for _ in range(6):
        run.tick()
    run.pulse()
    assert capsys.readouterr().out.splitlines() == ["country progress: calls 3, 75s", "country progress: calls 6, 150s"]


def test_the_workflow_keeps_inputs_and_secrets_off_the_public_log():
    import yaml
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "ga4-country-probe.yml"), encoding="utf-8") as fh:
        raw = fh.read()
    wf = yaml.safe_load(raw)
    on = wf.get("on", wf.get(True))
    assert set(on) == {"workflow_dispatch"}
    assert set(on["workflow_dispatch"]["inputs"]) == {"max_apps", "apps", "days", "pivot", "t2_days", "max_calls",
                                                      "resume"}
    assert on["workflow_dispatch"]["inputs"]["days"]["default"] == cp.DAYS_SPEC
    assert on["workflow_dispatch"]["inputs"]["pivot"]["default"] == cp.PIVOT.isoformat()
    assert wf["permissions"] == {"contents": "read"} and "github.event.inputs" not in raw and "inputs." not in raw
    job = wf["jobs"]["probe"]
    steps = job["steps"]
    assert steps[0]["with"]["persist-credentials"] is False
    (clone,) = [st for st in steps if "clone" in (st.get("run") or "")]
    assert "> /dev/null 2>&1" in clone["run"] and "::add-mask::" in clone["run"] and "timeout 480 git " in clone["run"]
    assert "@github.com" not in clone["run"] and not any(k.startswith("GA4_") for k in clone.get("env") or {})
    assert 3 + 8 + cp.BUDGET_SEC / 60 + 3 + 4 <= job["timeout-minutes"]
    (st,) = [s for s in steps if s.get("name") == "Run"]
    assert st["run"].startswith("python -m admob_iq.fetch.ga4_country_probe 2>/tmp/")
    assert "details kept off the public log" in st["run"] and st["env"]["COUNTRY_DATA_DIR"] == "_private"
