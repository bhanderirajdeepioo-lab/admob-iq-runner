"""GA4 shape probe (admob_iq.fetch.ga4_shape_probe) — offline, against a fake GA4 Data/Admin API (requests mocked) and a
fake read-only clone of the private repo: every request shape (one activity day per split, the firstSessionDate inList
variants, cohortSpec with / without country and revenue, the reference), the self-checks (sums vs TOTAL and vs the day,
country sums vs the plain split, cohort cells vs one-day cells), GA4 vs AdMob / Google Ads read the way the build reads
them, refused requests kept as their HTTP class only, the quota / server-error / time-budget stops, and a PUBLIC log
that stays counts-only."""

import gzip
import json
import os
import re
import threading
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_shape_probe as sp

NOW = datetime(2026, 9, 27, 6, 0, tzinfo=timezone.utc)
TODAY, END = date(2026, 9, 27), date(2026, 9, 25)
RECENT = END - timedelta(days=sp.LATE)
EMAIL_A, EMAIL_B = "owner.a@secret-ws.test", "owner.b@secret-ws.test"
RT_A, RT_B, TOK_A, TOK_B = "rt-SECRET-a", "rt-SECRET-b", "tok-SECRET-a", "tok-SECRET-b"
PID_A, PID_B, PID_C = "987654321", "123123123", "555666777"
SID_A, SID_B, SID_C = "5550001111", "5550002222", "5550003333"
PKG_A, PKG_B, PKG_C = "com.secret.old", "com.secret.big", "com.secret.small"
AID_A, AID_B, AID_C, AID_D = ("ca-app-pub-1111111111111111~%d" % i for i in (1, 2, 3, 4))
AID_A2 = "ca-app-pub-2222222222222222~77"            # a second AdMob app of A's Play package (not in the GA4 state)
SECRETS = [EMAIL_A, EMAIL_B, RT_A, RT_B, TOK_A, TOK_B, PID_A, PID_B, PID_C, SID_A, SID_B, SID_C, PKG_A, PKG_B, PKG_C,
           AID_A, AID_B, AID_C, AID_D, AID_A2, "secret", "SECRETDETAIL"]
AD, IAP = 0.01, 0.0005                             # ad / in-app revenue per active user per day (USD)
OLD_LAGS = {3, 14, 30, 45, 60, 90, 120, 180, 270, 365}
CAND = sorted({0, 1, 7} | OLD_LAGS | set(range(10, 501, 10)))
R_ALL, NET_SHARE, ADS_R = 0.9, 0.8, 0.8           # GA4 ÷ AdMob (all sources); network share; GA4 paid ÷ Ads installs


def ymd(d):
    return d.strftime("%Y%m%d")


def split3(u):
    a, b = u * 6 // 10, u * 3 // 10
    return [("IN", a), ("US", b), ("BR", u - a - b)]


class Truth:
    """One app's GA4 reality: n installs a day since `start`; on day d the users of install day f: lag 0 → n, 1 → 30%,
    7 → 10%, the design's long lags and every 10th lag up to 500 → 4. Countries IN / US / BR 60 / 30 / 10, 40% of users
    came from Google Ads campaign "123", version 1.1 for installs of the last 60 days. Options: other_old ("(other)"
    install days on old activity days, country splits only), thresh, no_total (totalRevenue refused with
    firstSessionDate), coh_country / coh_rev False (cohortSpec refuses a country dimension / revenue), coh_max_end."""

    def __init__(self, start, n, other_old=False, thresh=False, no_total=False, coh_country=True, coh_rev=True,
                 coh_max_end=None):
        self.start, self.n, self.other_old, self.thresh = start, n, other_old, thresh
        self.no_total, self.coh_country, self.coh_rev, self.coh_max_end = no_total, coh_country, coh_rev, coh_max_end

    def users(self, f, d):
        if f < self.start or f > d:
            return 0
        lag = (d - f).days
        if lag == 0:
            return self.n
        if lag == 1:
            return self.n * 3 // 10
        if lag == 7:
            return self.n // 10
        return 4 if lag in OLD_LAGS or (lag % 10 == 0 and lag <= 500) else 0

    def day_users(self, d):
        return sum(self.users(d - timedelta(days=L), d) for L in CAND)

    def cty_users(self, d, cc):
        return sum(dict(split3(self.users(d - timedelta(days=L), d)))[cc] for L in CAND)


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body or {}
        self.text = json.dumps(self._b)
        self.headers = {"content-type": "application/json"}

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._b


def _mets(atom, names):
    a = atom["act"]
    v = {"activeUsers": a, "newUsers": atom["new"], "totalAdRevenue": a * AD, "totalRevenue": a * (AD + IAP),
         "eventCount": 10 * a, "publisherAdImpressions": 3 * a, "cohortActiveUsers": a,
         "cohortTotalUsers": atom.get("t", 0)}
    return {m: v[m] for m in names}


class FakeGA4:
    def __init__(self, truths, quota=None, fail=None):
        self.truths = truths                        # pid → (stream id, Truth)
        self.bodies, self.gets, self.fail, self.lock = [], [], fail, threading.Lock()
        self.remaining = {pid: (quota or {}).get(pid, 200000) for pid in truths}

    def get(self, url, headers=None, params=None, timeout=None):
        assert headers["Authorization"] in ("Bearer " + TOK_A, "Bearer " + TOK_B)
        self.gets.append(url)
        pid = url.rsplit("/", 1)[-1]
        if "/properties/" in url and pid in self.truths:
            return Resp(body={"name": "properties/" + pid, "timeZone": "UTC", "currencyCode": "INR"})
        return Resp(404, {"error": {"code": 404, "status": "NOT_FOUND", "message": "?"}})

    def _bad(self, st, pid):
        return Resp(st, {"error": {"code": st, "status": "INTERNAL" if st >= 500 else "INVALID_ARGUMENT",
                                   "message": "bad SECRETDETAIL " + pid}})

    def post(self, url, headers=None, json=None, timeout=None):
        pid = url.split("/properties/")[1].split(":")[0]
        with self.lock:
            self.bodies.append((pid, json))
        st = self.fail(pid, json) if self.fail else None
        if st:
            return self._bad(st, pid)
        sid, t = self.truths[pid]
        ex = json["dimensionFilter"]["andGroup"]["expressions"]
        pinned = {(e["filter"]["fieldName"], (e["filter"].get("stringFilter") or {}).get("value")) for e in ex}
        assert ("streamId", sid) in pinned and ("platform", "Android") in pinned
        assert json.get("returnPropertyQuota") is True
        dims = [d["name"] for d in json.get("dimensions") or []]
        mets = [m["name"] for m in json["metrics"]]
        coh = "cohortSpec" in json
        if any("betweenFilter" in e["filter"] for e in ex):
            return self._bad(400, pid)
        if (t.no_total and "totalRevenue" in mets and "firstSessionDate" in dims) or \
                (coh and "countryId" in dims and not t.coh_country) or \
                (coh and "totalAdRevenue" in mets and not t.coh_rev) or \
                (coh and t.coh_max_end and json["cohortSpec"]["cohortsRange"]["endOffset"] > t.coh_max_end):
            return self._bad(400, pid)
        fsd_in = cty_is = None
        for e in ex:
            f = e["filter"]
            if f["fieldName"] == "firstSessionDate":
                fsd_in = set(f["inListFilter"]["values"])
            elif f["fieldName"] == "countryId":
                cty_is = f["stringFilter"]["value"]
        atoms = self.cohort_atoms(t, json) if coh else self.day_atoms(t, json, dims)
        atoms = [a for a in atoms if (fsd_in is None or a.get("firstSessionDate") in fsd_in)
                 and (cty_is is None or a.get("countryId") == cty_is)]
        rows = {}
        for a in atoms:
            key = tuple(a[d] for d in dims)
            cur = rows.setdefault(key, dict.fromkeys(mets, 0))
            for m, v in _mets(a, mets).items():
                cur[m] += v
        rows = sorted(rows.items())
        off, lim = int(json.get("offset") or 0), int(json.get("limit") or 10000)
        other = any("(other)" in k for k, _ in rows)
        resp = {"dimensionHeaders": [{"name": n} for n in dims], "metricHeaders": [{"name": m} for m in mets],
                "rows": [{"dimensionValues": [{"value": v} for v in k],
                          "metricValues": [{"value": str(r[m])} for m in mets]} for k, r in rows[off:off + lim]],
                "rowCount": len(rows),
                "metadata": {"currencyCode": "USD" if json.get("currencyCode") == "USD" else "INR",
                             "subjectToThresholding": t.thresh, "dataLossFromOtherRow": other}}
        if "TOTAL" in (json.get("metricAggregations") or []):
            resp["totals"] = [{"dimensionValues": [{"value": "RESERVED_TOTAL"} for _ in dims],
                               "metricValues": [{"value": str(sum(r[m] for _, r in rows))} for m in mets]}]
        cost = 20 if coh else 5
        with self.lock:
            self.remaining[pid] -= cost
            resp["propertyQuota"] = {"tokensPerDay": {"consumed": cost, "remaining": self.remaining[pid]}}
        return Resp(body=resp)

    @staticmethod
    def day_atoms(t, body, dims):
        out = []
        for rg in body["dateRanges"]:
            d = date.fromisoformat(rg["startDate"])
            while d <= date.fromisoformat(rg["endDate"]):
                for L in CAND:
                    f = d - timedelta(days=L)
                    u = t.users(f, d)
                    if not u:
                        continue
                    fs = ymd(f)
                    if t.other_old and "countryId" in dims and (TODAY - d).days >= 300 and L >= 60:
                        fs = "(other)"
                    for cc, v in split3(u):
                        if not v:
                            continue
                        a = {"date": ymd(d), "firstSessionDate": fs, "countryId": cc,
                             "appVersion": "1.1" if f >= TODAY - timedelta(days=60) else "1.0",
                             "act": v, "new": v if L == 0 else 0}
                        if "firstUserGoogleAdsCampaignId" in dims:
                            k = v * 4 // 10
                            out += [dict(a, act=k, new=a["new"] and k, firstUserGoogleAdsCampaignId="123"),
                                    dict(a, act=v - k, new=a["new"] and v - k,
                                         firstUserGoogleAdsCampaignId="(not set)")]
                        else:
                            out.append(a)
                d += timedelta(days=1)
        return out

    @staticmethod
    def cohort_atoms(t, body):
        out = []
        end = body["cohortSpec"]["cohortsRange"]["endOffset"]
        for c in body["cohortSpec"]["cohorts"]:
            x = date.fromisoformat(c["dateRange"]["startDate"])
            tot = dict(split3(t.n if x >= t.start else 0))
            for k in range(end + 1):
                d = x + timedelta(days=k)
                if d > TODAY:
                    break
                for cc, v in split3(t.users(x, d)):
                    if v:
                        out.append({"cohort": c["name"], "cohortNthDay": "%04d" % k, "countryId": cc, "act": v,
                                    "new": 0, "t": tot[cc]})
        return out


def truths(**kw):
    return {PID_A: (SID_A, Truth(TODAY - timedelta(days=950), 1000, **kw.get("a", {}))),          # the oldest
            PID_B: (SID_B, Truth(TODAY - timedelta(days=800), 2000, other_old=True, thresh=True, no_total=True)),
            PID_C: (SID_C, Truth(TODAY - timedelta(days=120), 100))}                             # a small, young one


STATE = {"routes": {"by_package": {PKG_A: {"property_id": PID_A, "stream_id": SID_A, "owner": EMAIL_A},
                                   PKG_B: {"property_id": PID_B, "stream_id": SID_B, "owner": EMAIL_B},
                                   PKG_C: {"property_id": PID_C, "stream_id": SID_C, "owner": EMAIL_A}}},
         "tz": {PID_A: "UTC", PID_B: "UTC"},
         "fetch": {AID_A: {"package": PKG_A, "meta": {"history_start": (TODAY - timedelta(days=950)).isoformat(),
                                                      "window_end": END.isoformat()}},
                   AID_B: {"package": PKG_B},
                   AID_C: {"package": PKG_C, "meta": {"time_zone": "UTC",
                                                      "history_start": (TODAY - timedelta(days=120)).isoformat()}},
                   AID_D: {"package": "com.secret.noroute"}}}
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


def _units(*pkgs):
    us = sp.units_from_state(STATE)
    return [u for u in us if u["package"] in pkgs] if pkgs else us


def _run(units=None, adm=None, **kw):
    return sp.run_probe(_units() if units is None else units, "cid", "sec", TOKENS, adm, now=NOW, tick=0, **kw)


def _write_gz(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(obj, f)


def make_clone(root):
    """The private repo's files the probe reads, for A and B: AdMob all sources = GA4 ad revenue ÷ R_ALL (A's split
    70 / 30 over two AdMob apps of its package), the network report NET_SHARE of that, AdMob by country the same per
    country, Google Ads installs = GA4 campaign new users ÷ ADS_R."""
    tr = truths()
    net, med, cty = [], [], []
    for aid, pkg, pid, share in ((AID_A, PKG_A, PID_A, 0.7), (AID_A2, PKG_A, PID_A, 0.3), (AID_B, PKG_B, PID_B, 1.0)):
        t = tr[pid][1]
        for i in range(1, 451):
            d = TODAY - timedelta(days=i)
            allv = t.day_users(d) * AD / R_ALL * share
            base = {"report_date": d.isoformat(), "account_id": aid.split("~")[0], "app_id": aid, "ad_unit_id": "u",
                    "country": "", "format": "BANNER", "platform": "ANDROID"}
            med.append(dict(base, ad_source="s", mediation_group="", estimated_earnings_micros=int(round(allv * 1e6)),
                            impressions=int(3 * t.day_users(d) * share)))
            net.append(dict(base, estimated_earnings_micros=int(round(allv * NET_SHARE * 1e6)), impressions=1))
            if i <= 80:
                for cc in ("IN", "US", "BR"):
                    cty.append({"report_date": d.isoformat(), "account_id": "x", "app_id": aid, "country": cc,
                                "estimated_earnings_micros": int(round(t.cty_users(d, cc) * AD / R_ALL * share * 1e6))})
    d0 = os.path.join(root, "data")
    _write_gz(os.path.join(d0, "network.json.gz"), net)
    _write_gz(os.path.join(d0, "mediation.json.gz"), med)
    _write_gz(os.path.join(d0, "country.json.gz"), cty)
    _write_gz(os.path.join(root, "site", "dashboard.json.gz"), {"report_tz": "UTC", "currency": "USD"})
    with open(os.path.join(d0, "app_store_ids.json"), "w") as f:
        json.dump({"by_id": {AID_A: PKG_A, AID_A2: PKG_A, AID_B: PKG_B}}, f)
    inst = {(TODAY - timedelta(days=i)).isoformat(): (1000 * 6 // 10 * 4 // 10 + 1000 * 3 // 10 * 4 // 10
                                                      + 100 * 4 // 10) / ADS_R for i in range(1, 60)}
    with open(os.path.join(d0, "roas_spend_cache.json"), "w") as f:
        json.dump({"installs": {PKG_A: inst}, "daily": {}}, f)
    os.makedirs(os.path.join(d0, "ga4_uninstall"), exist_ok=True)
    with open(os.path.join(d0, "ga4_uninstall", "state.json"), "w") as f:
        json.dump(STATE, f)
    return root


def _kinds(bodies):
    out = {}
    for pid, b in bodies:
        dims = tuple(d["name"] for d in b.get("dimensions") or [])
        mets = tuple(m["name"] for m in b["metrics"])
        fl = [e["filter"] for e in b["dimensionFilter"]["andGroup"]["expressions"][2:]]
        if "cohortSpec" in b:
            k = "COH_FILT" if fl else "COH_CTY" if dims[2:] == ("countryId",) else "COH"
            if "totalAdRevenue" in mets:
                k += "_REV"
        elif dims == ("date",):
            k = "REF"
        elif dims == ("date", "countryId"):
            k = "CTY56"
        elif dims == ("date", "firstUserGoogleAdsCampaignId"):
            k = "PAID"
        elif dims == ("firstSessionDate",):
            k = "QB"
        elif dims == ("firstSessionDate", "appVersion"):
            k = "VER"
        elif fl and "betweenFilter" in fl[0]:
            k = "BETWEEN"
        elif fl:
            k = {6: "QA6", 91: "QA90", 200: "IN200"}[len(fl[0]["inListFilter"]["values"])]
        else:
            k = "QA"
        out.setdefault(k, []).append((pid, b))
    return out


# ── the tests ───────────────────────────────────────────────────────────────────────────────────

def test_the_app_list_is_the_builds_routes_with_every_admob_id_and_history():
    us = sp.units_from_state(STATE)
    assert [u["package"] for u in us] == [PKG_A, PKG_B, PKG_C]
    a = us[0]
    assert a["app_ids"] == [AID_A] and a["history_start"] == (TODAY - timedelta(days=950)).isoformat()
    assert a["window_end"] == END.isoformat() and us[1]["history_start"] is None
    assert sp.units_from_state(None) == []
    assert sp.pick_slots(TODAY, END, TODAY - timedelta(days=120)) == [("recent", RECENT),
                                                                      ("d100", TODAY - timedelta(days=100))]
    assert [s for s, _ in sp.pick_slots(TODAY, END, TODAY - timedelta(days=950))] == ["recent", "d100", "d400"]
    assert sp.pick_slots(TODAY, END, None) == []


def test_every_request_shape_one_day_per_split(fake):
    f = fake()
    _run(_units(PKG_A))
    k = _kinds(f.bodies)
    assert {n: len(v) for n, v in k.items()} == {"REF": 1, "QB": 3, "QA": 3, "QA6": 3, "QA90": 3, "VER": 3, "COH": 3,
                                                 "COH_CTY": 1, "COH_REV": 1, "COH_CTY_REV": 1, "COH_FILT": 1,
                                                 "CTY56": 1, "PAID": 1, "BETWEEN": 1, "IN200": 1}
    (_, ref), = k["REF"]
    assert ref["dateRanges"] == [{"startDate": (TODAY - timedelta(days=sp.REF_DAYS)).isoformat(),
                                  "endDate": END.isoformat()}] and ref["currencyCode"] == "USD"
    assert [m["name"] for m in ref["metrics"]] == list(sp.REF_METS)
    days = [RECENT, TODAY - timedelta(days=100), TODAY - timedelta(days=400)]
    for kind in ("QB", "QA", "QA6", "QA90", "VER"):
        assert [b["dateRanges"] for _, b in k[kind]] == [[{"startDate": d.isoformat(), "endDate": d.isoformat()}]
                                                         for d in days], kind
        for _, b in k[kind]:
            assert b["metricAggregations"] == ["TOTAL"] and b["currencyCode"] == "USD" and b["limit"] == sp.PAGE_ROWS
            want = ["activeUsers", "newUsers"] if kind == "VER" else list(sp.METS)
            assert [m["name"] for m in b["metrics"]] == want
    for kind, n in (("QA6", 6), ("QA90", 91)):
        for (_, b), d in zip(k[kind], days):
            vals = b["dimensionFilter"]["andGroup"]["expressions"][2]["filter"]["inListFilter"]["values"]
            assert len(vals) == n and vals[0] == ymd(d)
            if kind == "QA6":
                assert vals == [ymd(d - timedelta(days=L)) for L in sp.LIST_LAGS]
    (_, b), = k["IN200"]
    assert len(b["dimensionFilter"]["andGroup"]["expressions"][2]["filter"]["inListFilter"]["values"]) == 200
    (_, b), = k["BETWEEN"]
    bf = b["dimensionFilter"]["andGroup"]["expressions"][2]["filter"]["betweenFilter"]
    assert bf == {"fromValue": {"int64Value": ymd(RECENT - timedelta(days=90))}, "toValue": {"int64Value": ymd(RECENT)}}
    coh = [b for _, b in k["COH"] if len(b["cohortSpec"]["cohorts"]) > 1]
    assert len(coh) == 3
    for b, d in zip(coh, days):
        assert "dateRanges" not in b and b["limit"] == sp.COH_LIMIT
        cs = b["cohortSpec"]["cohorts"]
        assert all(c["dateRange"]["startDate"] == c["dateRange"]["endDate"] and c["dimension"] == "firstSessionDate"
                   for c in cs)
        assert b["cohortSpec"]["cohortsRange"] == {"granularity": "DAILY", "startOffset": 0, "endOffset": 365}
    assert [c["dateRange"]["startDate"] for c in coh[0]["cohortSpec"]["cohorts"]] == \
        [(RECENT - timedelta(days=L)).isoformat() for L in sp.COH_LAGS]
    assert len(coh[2]["cohortSpec"]["cohorts"]) == 7                       # d400 − 365 is still ≥ A's first day
    (_, b), = k["COH_CTY"]
    assert [d["name"] for d in b["dimensions"]] == ["cohort", "cohortNthDay", "countryId"]
    assert b["cohortSpec"]["cohorts"][0]["dateRange"]["startDate"] == (RECENT - timedelta(days=7)).isoformat()
    (_, b), = k["COH_FILT"]
    assert b["dimensionFilter"]["andGroup"]["expressions"][2] == ga4._exact("countryId", "IN")
    (_, b), = k["CTY56"]
    assert b["dateRanges"] == [{"startDate": (END - timedelta(days=55)).isoformat(), "endDate": END.isoformat()}]
    (_, b), = k["PAID"]
    assert b["dateRanges"] == [{"startDate": (END - timedelta(days=27)).isoformat(), "endDate": END.isoformat()}]
    assert f.gets == ["%s/properties/%s" % (ga4.ADMIN, PID_A)]              # the property's currency / timezone, once


def test_a_whole_property_ties_every_piece_and_ties_to_admob(fake, tmp_path):
    fake()
    root = make_clone(str(tmp_path / "_private"))
    units = _units(PKG_A)
    adm = sp.load_admob(root, units, NOW)
    assert adm["state"] == "ok" and adm["tz_src"] == "dashboard" and adm["apps"][PKG_A]["ids"] == 2
    rep = _run(units, adm)
    a = rep["apps"][PKG_A]
    assert a["prop_meta"] == {"time_zone": "UTC", "currency": "INR"} and a["first_day"] == a["history_start"]
    assert sorted(a["days"]) == ["d100", "d400", "recent"]
    for slot, rec in a["days"].items():
        qb, qa = rec["QB"], rec["QA"]
        assert qb["cov"] == qb["ncov"] == qb["rcov"] == qb["tcov"] == 1.0, slot
        assert set(qb["add"].values()) == {1.0} and qb["other"]["rows"] == 0 and qb["not_set"]["rows"] == 0
        assert qb["currency"] == "USD" and qb["mets"] == "all" and qb["tok"] == 5 and qb["calls"] == 1
        assert qa["countries"] == 3 and qa["vs_QB"]["act_dev_med"] == 0.0 and qa["vs_QB"]["ad_dev_med"] == 0.0
        assert qa["vs_QB"]["n"] == len(sp.KEEP_LAGS) and qa["top25_inst"] == 1.0 and qa["ge1pct_inst"] == 3
        for k in ("QA6", "QA90"):
            v = rec[k]["vs_QA"]
            assert v["equal_share"] == 1.0 and v["only_sub"] == v["only_qa"] == 0 and v["act"] == 1.0, (slot, k)
        cells = rec["COH"]["cells"]
        assert [c["L"] for c in cells] == list(sp.COH_LAGS)
        assert all(c["r_qb"] == 1.0 and c["r_qa"] == 1.0 for c in cells), slot
        assert rec["COH"]["end_offset"] == 365 and rec["COH"]["tok"] == 20
    rec = a["days"]["recent"]
    assert [c["t_new"] for c in rec["COH"]["cells"]] == [1.0] * len(sp.COH_LAGS)   # X inside REF: cohort = installs
    assert rec["VER"]["dominant_share"] == 1.0 and rec["VER"]["dominant_ge80"] and rec["VER"]["versions"] == 2
    assert rec["QB"]["ab"]["0"] == round(1000 / sum(Truth(TODAY - timedelta(days=950), 1000).users(
        RECENT - timedelta(days=L), RECENT) for L in CAND), 4)
    o = a["once"]
    assert o["COH_CTY"]["a7_vs_coh"] == 1.0 and o["COH_CTY"]["top10_within_3pct"] == 3 and o["COH_CTY"]["accepted"]
    assert o["COH_REV"]["rev7_vs_qb"] == 1.0 and o["COH_CTY_REV"]["rev7_vs_coh_rev"] == 1.0
    assert o["COH_FILT"]["a7_vs_qa"] == 1.0
    assert o["BETWEEN"]["err"] == {"http": 400, "status": "INVALID_ARGUMENT"}
    assert o["IN200"]["vs_QA"]["equal_share"] == 1.0 and o["IN200"]["tok_vs_QA"] == 1.0
    assert o["PAID"]["ads_share"] == 0.4 and o["CTY56"]["countries"] == 3
    m5 = a["m5"]
    assert m5["state"] == "ok" and m5["iap"]["share"] == round(IAP / (AD + IAP), 4)
    d = m5["days"]["recent"]
    assert d["r_ad_all"] == R_ALL and d["r_ad_net"] == round(R_ALL / NET_SHARE, 4)
    assert abs(d["r_tot_net"] - (AD + IAP) / AD * R_ALL / NET_SHARE) < 2e-4     # (a): Σ totalRevenue ÷ AdMob network
    assert len(m5["weeks"]) == sp.WEEKS and m5["r_all"]["p50"] == R_ALL and m5["r_net"]["p50"] == 1.125
    assert m5["weeks"][0]["from"] == "2026-09-14"                          # the newest Mon–Sun week ending ≤ E − 3
    assert m5["cty"]["r_total"] == R_ALL and [r["cc"] for r in m5["cty"]["top"]] == ["IN", "US", "BR"]
    assert all(r["r"] == R_ALL for r in m5["cty"]["top"])
    assert m5["paid"]["ratio_p50"] == ADS_R and m5["paid"]["ads_share"] == 0.4
    m12 = a["m12"]
    assert m12["hist_days"] == 949 and m12["hot_gz"] > 0 and m12["old_gz"] > 0 and m12["slots"] == 3
    assert m5["r_all_20"]["n"] == sp.WEEKS and m5["r_all_20"]["p50"] == R_ALL   # every week ≥ $20 on both sides
    assert all(r["usd_ok"] for r in m5["cty"]["top"])
    sm = rep["summary"]
    assert sm["m1"]["iday_max_calls_hint"] == 120 and sm["m3"]["365"]["qb_within_3pct"] == 3
    assert sm["m3"]["365"]["nonzero"] == 3 and sm["m3"]["1"]["big"] == 3 and sm["m3"]["1"]["big_qb_within_3pct"] == 3
    assert sm["m4"]["QB"]["total_within"] == 3 and sm["m5"]["r_all_p50_median"] == R_ALL
    assert sm["m5"]["apps_20usd"] == 1 and sm["m5"]["apps_20usd_p50_outside_07_13"] == 0
    assert sm["m5"]["r_all_20usd_p50_median"] == R_ALL and sm["m5"]["cty_top_usd_ok"] == 3
    assert sm["m6"]["BETWEEN"] == {"n": 1, "accepted": 0} and sm["m6"]["COH_CTY"] == {"n": 1, "accepted": 1}
    assert sm["m7"]["iap_ge_1pct"] == 1 and sm["m8"]["resp_usd"] == 6 and sm["m8"]["prop_currency"] == {"INR": 1}
    assert sm["m11_bc"]["QA6"]["equal_share_med"] == 1.0 and sm["ver"]["dominant_ge80"] == 3
    c = rep["counts"]
    assert (c["errors"], c["var_ok"], c["var_of"], c["admob_apps"], c["qa_ok"], c["coh_ok"]) == (0, 5, 6, 1, 3, 3)
    assert rep["admob"] == {"state": "ok", "tz_src": "dashboard", "currency": "USD", "till": "2026-09-26",
                            "apps_matched": 1}
    json.loads(sp.pr._dump(rep))


def test_other_rows_thresholding_and_a_refused_total_revenue_are_flagged(fake):
    f = fake()
    rep = _run(_units(PKG_B))
    b = rep["apps"][PKG_B]
    assert b["no_total"] is True
    tot = [x for p, x in f.bodies if p == PID_B and "totalRevenue" in json.dumps(x["metrics"])
           and "firstSessionDate" in json.dumps(x.get("dimensions"))]
    assert len(tot) == 1                                                   # refused once, never asked again
    for slot, rec in b["days"].items():
        assert rec["QB"]["mets"] == "no_total" and rec["QB"]["tcov"] is None and rec["QB"]["sum"]["tot"] is None
        assert rec["QB"]["thresh"] is True and rec["QB"]["cov"] == 1.0
    qa = b["days"]["d400"]["QA"]
    assert qa["other"]["rows"] > 0 and qa["other"]["act_share"] > sp.OTH_MAX and qa["loss_other"] is True
    assert b["days"]["recent"]["QA"]["other"]["rows"] == 0
    assert b["days"]["d400"]["QA6"]["vs_QA"]["only_sub"] == 0                  # (b): its days are all under 60 old
    v = b["days"]["d400"]["QA90"]["vs_QA"]
    assert v["only_qa"] == 0 and v["equal_share"] == 1.0
    assert b["days"]["d400"]["QB"]["other"]["rows"] == 0                   # the plain split kept every install day
    sm = rep["summary"]
    assert sm["m2"]["QA_d400"]["over_oth_max"] == 1 and sm["m2"]["QA_recent"]["over_oth_max"] == 0
    assert sm["kinds"]["QB"]["no_total"] == 3 and rep["counts"]["thresholded"] > 0
    assert b["m5"]["state"] == "no_admob" and b["m5"]["iap"]["share"] == round(IAP / (AD + IAP), 4)   # REF by date


def test_a_young_app_asks_only_the_days_and_cohorts_it_has(fake):
    f = fake()
    rep = _run(_units(PKG_C))
    c = rep["apps"][PKG_C]
    assert sorted(c["days"]) == ["d100", "recent"] and c["first_day"] == (TODAY - timedelta(days=120)).isoformat()
    assert c["days"]["recent"]["COH"]["lags"] == [1, 7, 30, 60, 90]
    assert c["days"]["d100"]["COH"]["lags"] == [1, 7] and c["days"]["d100"]["COH"]["end_offset"] == 7
    assert all(x["r_qb"] == 1.0 for x in c["days"]["recent"]["COH"]["cells"])
    assert c["m12"]["hist_days"] == 119 and c["m12"]["hot_gz"] > 0
    assert sum(1 for p, _ in f.bodies if p == PID_C) == 1 + 2 * 6 + 8


def test_a_refused_long_cohort_is_asked_again_with_the_short_lags(fake):
    fake(truths=truths(a={"coh_max_end": 90}))
    rep = _run(_units(PKG_A))
    coh = rep["apps"][PKG_A]["days"]["recent"]["COH"]
    assert coh["long_err"] == {"http": 400, "status": "INVALID_ARGUMENT"} and coh["end_offset"] == 90
    assert [x["L"] for x in coh["cells"]] == [1, 7, 30, 60, 90] and coh["calls"] == 2
    assert rep["summary"]["m6"]["COH"]["long_refused"] == 3


def test_refused_cohort_variants_are_kept_as_their_class_only(fake):
    fake(truths=truths(a={"coh_country": False, "coh_rev": False}))
    rep = _run(_units(PKG_A))
    o = rep["apps"][PKG_A]["once"]
    for k in ("COH_CTY", "COH_REV", "COH_CTY_REV"):
        assert o[k]["err"] == {"http": 400, "status": "INVALID_ARGUMENT"} and o[k]["tok"] == 0, k
    assert o["COH_FILT"]["accepted"] and o["COH_FILT"]["a7_vs_qa"] == 1.0
    assert "SECRETDETAIL" not in json.dumps(rep)
    assert rep["counts"]["var_ok"] == 2 and rep["counts"]["errors"] == 0


def test_low_quota_stops_that_property_politely_and_the_others_go_on(fake):
    f = fake(quota={PID_C: 100004})                                        # under half the day's tokens after one call
    rep = _run()
    c = rep["apps"][PKG_C]
    assert c["stopped"] == "quota_low" and c["days"] == {} and c["ref"]["rows"] > 0      # no empty day record
    assert sum(1 for pid, _ in f.bodies if pid == PID_C) == 1
    assert rep["apps"][PKG_A]["days"] and "stopped" not in rep["apps"][PKG_A]
    assert rep["counts"]["quota_low"] == 1


def test_server_errors_stop_the_property_after_two_failed_calls(fake):
    f = fake(fail=lambda pid, b: 500 if pid == PID_A and "cohortSpec" in b else None)
    rep = _run(_units(PKG_A))
    a = rep["apps"][PKG_A]
    assert a["days"]["recent"]["COH"]["err"] == {"http": 500, "status": "INTERNAL"}
    assert a["stopped"] == "server_errors" and a["server_errors"] == 2
    assert sum(1 for p, b in f.bodies if "cohortSpec" in b) == 4           # each retried once by ga4._call
    assert "SECRETDETAIL" not in json.dumps(rep) and rep["counts"]["stopped_other"] == 1


def test_the_time_budget_stops_new_calls_and_the_report_is_still_whole(fake):
    f = fake()
    ticks = iter([0.0])
    rep = _run(budget=10, clock=lambda: next(ticks, 99.0))
    assert not f.bodies and rep["counts"]["calls"] == 0
    assert {a["stopped"] for a in rep["apps"].values()} == {"budget"}
    assert rep["counts"]["stopped_other"] == 3 and set(rep["summary"]["kinds"]) >= set(sp.CORE)
    assert sp.public_line(rep["counts"]).startswith("shape probe: apps 0/3, calls 0, ")


def test_main_reads_the_clone_writes_the_private_file_and_prints_counts_only(fake, monkeypatch, capsys, tmp_path):
    fake()
    root = make_clone(str(tmp_path / "_private"))
    put = {}
    monkeypatch.setattr(sp, "_private_json", lambda path: pytest.fail("the clone holds the state"))
    monkeypatch.setattr(sp, "write_private", lambda path, text, msg: bool(put.update({path: text})) or True)
    env = {"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec", "SHAPE_DATA_DIR": root,
           "GA4_REFRESH_TOKENS": json.dumps({EMAIL_A: RT_A, EMAIL_B: RT_B})}
    sp.main(env, now=NOW)
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert all(line.startswith("shape ") for line in lines)
    assert lines[0] == "shape probe: 3 app(s) to probe" and lines[1] == "shape probe: AdMob data for 2/3 app(s)"
    res = [line for line in lines if line.startswith("shape probe: apps ")]
    assert len(res) == 1 and lines[-1] == "shape probe: report written"
    assert re.fullmatch(r"shape probe: apps 3/3, calls \d+, QB ok 8/8, QA ok 8/8, cohorts ok 8/8, variants accepted "
                        r"\d+/\d+, reads with \(other\) \d+, thresholded \d+, quota low 0, stopped 0, errors 0, "
                        r"AdMob-matched apps 2, \d+s", res[0]), res[0]
    for s in SECRETS + ["2026-", "0.9", "IN", "US"]:
        assert s not in out
    rep = json.loads(put[sp.OUT_PATH])
    assert set(rep["apps"]) == {PKG_A, PKG_B, PKG_C} and rep["admob"]["apps_matched"] == 2
    assert rep["apps"][PKG_A]["m5"]["r_all"]["p50"] == R_ALL
    assert rep["apps"][PKG_B]["m5"]["days"]["recent"]["r_ad_all"] == R_ALL   # B's AdMob: its own app id


def test_main_without_a_clone_reads_the_state_through_the_api_and_skips_admob(fake, monkeypatch, capsys):
    fake()
    put = {}
    monkeypatch.setattr(sp, "_private_json", lambda path: STATE if path == sp.STATE_PATH else None)
    monkeypatch.setattr(sp, "write_private", lambda path, text, msg: bool(put.update({path: text})) or True)
    sp.main({"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec", "GA4_REFRESH_TOKEN": RT_A, "PROBE_MAX_APPS": "1",
             "GA4_REFRESH_TOKENS": json.dumps({EMAIL_A: RT_A})}, now=NOW)
    rep = json.loads(put[sp.OUT_PATH])
    assert rep["admob"]["state"] == "absent" and set(rep["apps"]) == {PKG_A}
    assert rep["apps"][PKG_A]["m5"]["state"] == "no_admob" and rep["apps"][PKG_A]["m5"]["iap"]["share"] > 0
    assert "shape probe: AdMob data for 0/1 app(s)" in capsys.readouterr().out


def test_main_without_credentials_or_routes_exits_before_any_call(fake, monkeypatch):
    f = fake()
    monkeypatch.setattr(sp, "_private_json", lambda path: {"routes": {}, "fetch": {}})
    with pytest.raises(SystemExit):
        sp.main({"GA4_CLIENT_ID": "cid"}, now=NOW)
    with pytest.raises(SystemExit):
        sp.main({"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec", "GA4_REFRESH_TOKEN": RT_A}, now=NOW)
    assert not f.bodies


def test_a_counts_only_heartbeat_at_least_every_minute(capsys):
    t = iter(range(0, 1000, 25))
    run = sp.Run(clock=lambda: float(next(t)))
    for _ in range(6):
        run.tick()
    run.pulse()
    assert capsys.readouterr().out.splitlines() == ["shape progress: calls 3, 75s", "shape progress: calls 6, 150s"]


def test_the_report_is_still_written_when_the_bookkeeping_has_a_bug(fake, monkeypatch):
    fake()
    monkeypatch.setattr(sp, "summary", lambda apps: 1 / 0)
    monkeypatch.setattr(sp, "admob_compare", lambda *a: {}["x"])
    monkeypatch.setattr(sp, "ver_sum", lambda rows, d, ga: [][1])
    rep = _run(_units(PKG_A))
    a = rep["apps"][PKG_A]
    assert rep["summary"] == {"err": {"type": "ZeroDivisionError"}} and a["m5"] == {"err": {"type": "KeyError"}}
    assert a["days"]["recent"]["VER"]["err"] == {"type": "IndexError"} and a["days"]["recent"]["VER"]["rows"] > 0
    assert a["days"]["recent"]["QB"]["cov"] == 1.0                         # the spent calls' results are all there
    json.loads(sp.pr._dump(rep))


def test_m3_judges_only_the_cells_somebody_is_in():
    empty = {"L": 365, "a": 0, "qb": 0, "qa": 0, "r_qb": None, "r_qa": None, "t_new": None}
    tiny = {"L": 365, "a": 3, "qb": 4, "qa": 4, "r_qb": 0.75, "r_qa": 0.75, "t_new": None}      # 1-user slack: holds
    off = {"L": 365, "a": 80, "qb": 100, "qa": 100, "r_qb": 0.8, "r_qa": 0.8, "t_new": None}    # 20% short: not
    lost = {"L": 365, "a": 5, "qb": 0, "qa": 0, "r_qb": None, "r_qa": None, "t_new": None}      # no one-day cell
    m = sp.m3_lag([empty] * 7 + [tiny, off, lost])
    assert (m["n"], m["nonzero"], m["qb_within_3pct"], m["qa_within_3pct"]) == (10, 3, 1, 1)   # 7 empties: not "held"
    assert (m["big"], m["big_qb_within_3pct"]) == (1, 0)
    e = sp.m3_lag([])
    assert e["n"] == e["nonzero"] == e["qb_within_3pct"] == e["big"] == 0 and e["qb_dev_med"] is None


def test_m5_judges_k_only_on_weeks_with_20_dollars_each_side():
    d0 = RECENT - timedelta(days=200)
    days = [d0 + timedelta(days=i) for i in range(260)]
    ref = {d: {"ad": 1.0, "tot": 1.0, "imp": 10} for d in days}                        # $7 a week in GA4
    micros = {d.isoformat(): [int(1.0 / 0.5 * 1e6), 10] for d in days}                  # AdMob: twice that
    adm = {"rev": {"tz": "UTC", "till": END.isoformat(), "days": micros, "all_days": micros}}
    out = sp.admob_compare({"days": {}}, {"REF": ref, "once": {}}, adm, "UTC", END)
    assert out["r_all"]["n"] == sp.WEEKS and out["r_all"]["p50"] == 0.5                  # far outside [0.7, 1.3] ...
    assert out["r_all_20"]["n"] == 0                                                     # ... but too small to judge
    sm = sp.summary({"x": {"m5": out}})
    assert sm["m5"]["apps_p50_outside_07_13"] == 1 and sm["m5"]["apps_20usd_p50_outside_07_13"] == 0
    assert sm["m5"]["apps_20usd"] == 0


def test_the_workflow_keeps_secrets_off_the_public_log_and_writes_before_its_timeout():
    import yaml
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "ga4-shape-probe.yml"), encoding="utf-8") as fh:
        wf = yaml.safe_load(fh)
    on = wf.get("on", wf.get(True))
    assert set(on) == {"workflow_dispatch"} and set(on["workflow_dispatch"]["inputs"]) == {"max_apps"}
    assert wf["permissions"] == {"contents": "read"}
    job = wf["jobs"]["probe"]
    steps = job["steps"]
    assert steps[0]["with"]["persist-credentials"] is False
    clone = [st for st in steps if "clone" in (st.get("run") or "")]
    assert len(clone) == 1
    run = clone[0]["run"]
    assert "> /dev/null 2>&1" in run and "@github.com" not in run and "::add-mask::" in run
    assert "http.extraheader" in run and "timeout 480 git " in run                        # a slow clone is given up
    assert not any(k.startswith("GA4_") for k in clone[0].get("env") or {})
    # setup (≤ 3) + clone (≤ 8) + AdMob (≤ 1) + the call budget + in-flight calls (≤ 3) + the write (≤ 4) < the timeout
    assert 3 + 8 + 1 + sp.BUDGET_SEC / 60 + 3 + 4 <= job["timeout-minutes"]
    (st,) = [s for s in steps if s.get("name") == "Run"]
    assert st["run"].startswith("python -m admob_iq.fetch.ga4_shape_probe 2>/tmp/")
    assert "details kept off the public log" in st["run"] and st["env"]["SHAPE_DATA_DIR"] == "_private"
    assert st["env"]["PROBE_MAX_APPS"] == "${{ github.event.inputs.max_apps }}"          # env, never inlined in run


def test_the_size_estimate_splits_hot_and_old_like_the_design():
    d = RECENT
    qb = {"cells": {(d - timedelta(days=L)).isoformat(): [10 + L, 5 if L == 0 else 0, 0.1, 0.11] for L in range(400)}}
    qa = {"cc": {("IN", (d - timedelta(days=L)).isoformat()): [5, 0.05, 3] for L in range(100)}}
    rec = {"sum": {"act": 5000, "ad": 12.5, "tot": 13.0}, "rows": 400,
           "ab": dict.fromkeys(sp.AB_NAMES, 0.1), "rb": dict.fromkeys(sp.AB_NAMES, 0.1)}
    young, small, big = (sp.size_estimate(n, qb, qa, rec, d) for n in (90, 300, 1100))
    assert young["old_gz"] == 0 and young["hot_gz"] > 0 and young["slots"] == 1
    assert small["old_gz"] > 0                                             # country weeks older than 100 days
    assert big["old_gz"] > small["old_gz"] and big["hot_gz"] > small["hot_gz"] and big["weeks"] >= 1100 // 7
    assert sp.size_estimate(300, qb, qa, rec, d) == small                  # deterministic
