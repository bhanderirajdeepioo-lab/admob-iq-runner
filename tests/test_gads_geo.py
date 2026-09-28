"""Google Ads cost and downloads BY COUNTRY (admob_iq.fetch.gads_geo + the three google_ads helpers; SPEC_CD_GEO §G) —
offline, against a fake Google Ads API (no network, a fake clock and token): the query shapes, which accounts are
asked (only owners of stores with spend; a 403 account once, then skipped 7 days), the criterion id → ISO-2 map
(Country list, by id, parent, else "XX"), Monday week keys with the part-week, whole weeks replaced, a chunk all or
nothing with the refresh back-off, downloads unknown (null) when Q-G2 fails, the 20 h refresh and the 2-chunk
backfill to 400 days / the data edge, the call / time / quota stops, another billing currency, the hot / .old files
(monthly roll, written only on change, size caps), starting over, the counts-only public line, and the build wiring
(off = nothing at all; a crash costs only this step). All data is synthetic."""

import copy
import gzip
import json
import os
import random
import re
import string
import threading
from datetime import date, timedelta

import pytest

from admob_iq import build_static
from admob_iq.config import settings
from admob_iq.fetch import gads_geo as gg
from admob_iq.fetch import google_ads

MCC, DEV, RT, TOK, CID, CSEC = "1110001111", "dev-SECRET", "rt-SECRET", "tok-SECRET", "cid-SECRET", "csec-SECRET"
A1, A2, A3, MGR = "2220002221", "2220002222", "2220002223", "2220009999"
S1, S2, S3 = "com.synth.alpha", "com.synth.beta", "com.synth.gamma"
TODAY = date(2026, 9, 24)                   # a Thursday: the refresh ends on a Wednesday → the newest week is a part-week
T0 = 1_800_000_000
H = 3600
COUNTRY = {"2840": "US", "2356": "IN", "2076": "BR", "2826": "GB"}
FX = {"INR": 0.012, "USD": 1.0}
SETTINGS = {"gads_geo": True, "google_ads_dev_token": DEV, "google_ads_login_customer_id": MCC,
            "google_ads_refresh_token": RT, "google_ads_client_id": CID, "google_ads_client_secret": CSEC}
REFRESH = ["2026-07-20", "2026-07-27", "2026-08-03", "2026-08-10", "2026-08-17", "2026-08-24", "2026-08-31",
           "2026-09-07", "2026-09-14", "2026-09-21"]
LINE = re.compile(r"^gads geo: accounts \d+ \(skipped \d+\), stores \d+, weeks refreshed \d+, backfill weeks \d+ "
                  r"\((filling|done|edge|off)\), calls \d+, errors \d+, countries mapped \d+, unmapped \d+$")
M = 1_000_000


def days(a, b):
    a, b = date.fromisoformat(str(a)), date.fromisoformat(str(b))
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


class Clock:
    """A fake monotonic clock: every Google Ads request moves it `step` seconds."""

    def __init__(self, step=0.5):
        self.t, self.step, self.lock = 0.0, step, threading.Lock()

    def __call__(self):
        return self.t

    def tick(self):
        with self.lock:
            self.t += self.step


class FakeAds:
    """A synthetic MCC. plan = {account: {store: {country criterion id | None: cost units a day}}} (1 unit = 10^6
    micros of the account's currency; a unit may be a function of the day); DOWNLOAD conversions = units / 10 a day.
    Geo rows exist only on days in [lo, hi] (the data edge). byid = what a by-id geo_target_constant request knows
    beyond the Country list ({id: {"cc", "parent"}}; unknown ids answer no row). fail(account, kind, query) → an
    error text to raise, or None. Kinds: ROSTER, ISO, BYID, G1, G2."""

    def __init__(self, plan, ccy=None, byid=None, lo=None, hi=None, clock=None):
        self.plan, self.ccy, self.byid = plan, dict(ccy or {}), dict(byid or {})
        self.lo, self.hi, self.clock = lo, hi, clock
        self.fail = lambda acct, kind, q: None
        self.calls, self.lock, self.gone = [], threading.Lock(), set()

    @staticmethod
    def kind(q):
        if "FROM customer_client" in q:
            return "ROSTER"
        if "FROM geo_target_constant" in q:
            return "ISO" if "target_type = 'Country'" in q else "BYID"
        if "FROM geographic_view" in q:
            return "G2" if "conversion_action_category" in q else "G1"
        raise AssertionError("unexpected query: " + q)

    def search(self, customer_id, login, dev, token, query):
        assert (login, dev, token) == (MCC, DEV, TOK)
        k = self.kind(query)
        with self.lock:
            self.calls.append((customer_id, k, query))
        if self.clock:
            self.clock.tick()
        err = self.fail(customer_id, k, query)
        if err:
            raise RuntimeError(err)
        if k == "ROSTER":
            assert customer_id == MCC
            return [{"customerClient": {"id": a, "currencyCode": self.ccy.get(a, "INR"), "manager": False}}
                    for a in sorted(set(self.plan) - self.gone)] + [{"customerClient": {"id": MGR, "manager": True}}]
        if k == "ISO":
            assert customer_id == MCC
            return [{"geoTargetConstant": {"resourceName": "geoTargetConstants/" + i, "id": i, "countryCode": c}}
                    for i, c in COUNTRY.items()]
        if k == "BYID":
            assert customer_id == MCC
            m = re.search(r"\.id IN \(([^)]*)\)", query) or re.search(r"resource_name IN \(([^)]*)\)", query)
            ids = [x.strip().strip("'").rsplit("/", 1)[-1] for x in m.group(1).split(",")]
            out = []
            for i in ids:
                g = self.byid.get(i) or ({"cc": COUNTRY[i]} if i in COUNTRY else None)
                if g is None:
                    continue
                row = {"resourceName": "geoTargetConstants/" + i, "id": i, "targetType": "Territory",
                       "status": "ENABLED"}
                if g.get("cc"):
                    row["countryCode"] = g["cc"]
                if g.get("parent"):
                    row["parentGeoTarget"] = "geoTargetConstants/" + g["parent"]
                out.append({"geoTargetConstant": row})
            return out
        a, b = re.search(r"BETWEEN '([\d-]+)' AND '([\d-]+)'", query).groups()
        out = []
        for sid, cty in sorted((self.plan.get(customer_id) or {}).items()):
            for d in days(a, b):
                if (self.lo and d < self.lo) or (self.hi and d > self.hi):
                    continue
                for ccid, u in cty.items():
                    u = u(d) if callable(u) else u
                    if not u:
                        continue
                    gv = {"locationType": "LOCATION_OF_PRESENCE"}
                    if ccid:
                        gv["countryCriterionId"] = ccid
                    camp = {"appCampaignSetting": {"appId": sid}, "advertisingChannelType": "MULTI_CHANNEL"}
                    if k == "G1":
                        out.append({"campaign": dict(camp, id="77"), "geographicView": gv, "segments": {"date": d},
                                    "metrics": {"costMicros": str(int(u * M))}})
                    else:
                        out.append({"campaign": camp, "geographicView": gv,
                                    "segments": {"date": d, "conversionActionCategory": "DOWNLOAD"},
                                    "metrics": {"conversions": u / 10}})
        return out

    def n(self, kind=None, acct=None):
        return sum(1 for c, k, _ in self.calls if (kind is None or k == kind) and (acct is None or c == acct))

    def ranges(self, kind="G1", acct=None):
        return [re.search(r"BETWEEN '([\d-]+)' AND '([\d-]+)'", q).groups() for c, k, q in self.calls
                if k == kind and (acct is None or c == acct)]


def spend_of(plan, first, last, rate=None, drop=()):
    """The ROAS step's merged spend cache for a plan: every store's daily cost (base micros) = the sum of its
    countries — so coverage is 1 — and its campaigns carrying their account."""
    daily, camps = {}, {}
    for acct, stores in sorted(plan.items()):
        r = (rate or {}).get(acct, 1.0)
        for sid, cty in sorted(stores.items()):
            camps.setdefault(sid, []).append({"id": "c%s%s" % (acct[-1], sid[-1]), "name": "n", "status": "ENABLED",
                                              "cost_micros": 1, "account": acct, "account_name": ""})
            if sid in drop:
                continue
            for d in days(first, last):
                v = sum((u(d) if callable(u) else u) for u in cty.values()) * M * r
                if v:
                    daily.setdefault(sid, {})[d] = daily.get(sid, {}).get(d, 0) + int(round(v))
    return {"v": 2, "currency_src": "INR", "daily": daily, "campaigns": camps, "installs": {}, "convval": {},
            "convval_day1": {}, "fx": {}}


def step(data, spend, fake, t=T0, today=TODAY, clock=None, **kw):
    kw.setdefault("fx_fn", FX.get)
    return gg.geo_step(SETTINGS, data, spend, today, now=lambda: t, clock=clock or Clock(), search=fake.search,
                       token=TOK, **kw)


def wk(data, sid=S1):
    return (gg.load_geo(data) or {}).get("weeks", {}).get(sid) or {}


@pytest.fixture
def data(tmp_path):
    return str(tmp_path / "data")


# ── the queries ─────────────────────────────────────────────────────────────────────────────────

def _fields(part):
    return set(re.findall(r"\b([a-z_]+\.[a-z_]+(?:\.[a-z_]+)*)\b", part))


def test_geo_queries_select_every_filtered_field():
    seen = []

    def rec(cid, login, dev, tok, q):
        seen.append(q)
        return []
    google_ads._app_geo_spend_for(A1, MCC, DEV, TOK, "2026-09-01", "2026-09-28", search=rec)
    google_ads._app_geo_installs_for(A1, MCC, DEV, TOK, "2026-09-01", "2026-09-28", search=rec)
    google_ads._geo_iso(MCC, DEV, TOK, ids=None, search=rec)
    google_ads._geo_iso(MCC, DEV, TOK, ids=["2344", "geoTargetConstants/2630"], search=rec)
    assert len(seen) == 4
    g1, g2, iso, byid = seen
    for q in (g1, g2, byid):                          # (the Country list is the probe's own, proven query)
        sel, where = re.match(r"SELECT (.*) FROM \w+ WHERE (.*)$", q).groups()
        assert _fields(where) <= _fields(sel), q
    assert "FROM geographic_view" in g1 and "FROM geographic_view" in g2
    for q in (g1, g2):
        assert "campaign.advertising_channel_type = 'MULTI_CHANNEL'" in q
        assert "geographic_view.location_type = 'LOCATION_OF_PRESENCE'" in q
        assert "segments.date BETWEEN '2026-09-01' AND '2026-09-28'" in q
    assert "metrics.cost_micros > 0" in g1 and "segments.conversion_action_category = 'DOWNLOAD'" in g2
    assert "segments.conversion_action_category" in g2.split(" FROM ")[0]
    assert "target_type = 'Country'" in iso and "geo_target_constant.id IN (2344, 2630)" in byid
    for q in seen:                                                     # read-only: nothing but SELECT
        assert q.startswith("SELECT ") and not re.search(r"\b(mutate|INSERT|UPDATE|DELETE)\b", q)


def test_geo_helpers_parse_rows_and_by_id_falls_back_to_resource_names():
    fake = FakeAds({A1: {S1: {"2840": 2, None: 1}}})
    rows = google_ads._app_geo_spend_for(A1, MCC, DEV, TOK, "2026-09-01", "2026-09-01", search=fake.search)
    assert sorted(rows, key=lambda r: str(r["ccid"])) == [
        {"store_id": S1, "date": "2026-09-01", "ccid": "2840", "cost_micros": 2 * M},
        {"store_id": S1, "date": "2026-09-01", "ccid": None, "cost_micros": M}]
    dl = google_ads._app_geo_installs_for(A1, MCC, DEV, TOK, "2026-09-01", "2026-09-01", search=fake.search)
    assert {r["ccid"]: r["dl"] for r in dl} == {"2840": 0.2, None: 0.1}
    pref = [{"campaign": {"appCampaignSetting": {"appId": "1:" + S2}}, "geographicView": {"countryCriterionId": "2356"},
             "segments": {"date": "2026-09-01"}, "metrics": {"costMicros": "5"}},
            {"campaign": {}, "geographicView": {"countryCriterionId": "2356"}, "segments": {"date": "2026-09-01"},
             "metrics": {"costMicros": "7"}}]
    got = google_ads._app_geo_spend_for(A1, MCC, DEV, TOK, "a", "b", search=lambda *a: pref)
    assert [r["store_id"] for r in got] == [S2, ""]                     # platform prefix stripped; "" = no store id
    fake.byid = {"2344": {"cc": "HK"}, "9000001": {"parent": "2840"}}
    asked = []

    def refuse_id_list(cid, login, dev, tok, q):
        asked.append(q)
        if ".id IN" in q:
            raise RuntimeError("HTTP 400: queryError=BAD_FIELD_NAME")
        return fake.search(cid, login, dev, tok, q)
    got = google_ads._geo_iso(MCC, DEV, TOK, ids=["9000001", "2344", "9000002"], search=refuse_id_list)
    assert got == {"2344": {"cc": "HK", "parent": None}, "9000001": {"cc": None, "parent": "2840"}}
    assert len(asked) == 2 and "resource_name IN ('geoTargetConstants/2344', " in asked[1]
    with pytest.raises(RuntimeError):                                   # anything but a 400 is the caller's to count
        google_ads._geo_iso(MCC, DEV, TOK, ids=["1"], search=lambda *a: (_ for _ in ()).throw(RuntimeError("HTTP 500")))
    assert google_ads._geo_iso(MCC, DEV, TOK, ids=None, search=fake.search)["2840"] == {"cc": "US", "parent": None}


# ── which accounts are asked ─────────────────────────────────────────────────────────────────────

def test_geo_accounts_only_owners_of_stores_with_spend(data):
    plan = {A1: {S1: {"2840": 3}}, A2: {S2: {"2840": 1}}, A3: {}}
    fake = FakeAds(plan)
    spend = spend_of(plan, "2026-07-20", "2026-09-23", drop=(S2,))       # S2's campaigns exist, but no spend
    line = step(data, spend, fake)
    assert fake.n(acct=A2) == 0 and fake.n(acct=A3) == 0
    assert fake.n("G1", A1) == 3 and fake.n("G2", A1) == 3              # 3 refresh pieces × (Q-G1, then Q-G2)
    assert fake.n() == 1 + 1 + 6                                         # + the roster and the Country list
    for c, k, _ in fake.calls:
        assert c == MCC if k in ("ROSTER", "ISO", "BYID") else c == A1
    order = [k for c, k, _ in fake.calls if c == A1]
    assert order == ["G1", "G2"] * 3
    assert "accounts 1 (skipped 0), stores 1," in line and "calls 8, errors 0" in line
    geo = gg.load_geo(data)
    assert set(geo["weeks"]) == {S1} and geo["done"] and geo["till"] == "2026-09-23"


def test_geo_403_account_one_call_then_skipped_7_days(data):
    plan = {A1: {S1: {"2840": 3}}, A2: {S2: {"2356": 2}}}
    fake = FakeAds(plan)
    fake.fail = lambda acct, k, q: ("HTTP 403: authorizationError=CUSTOMER_NOT_ENABLED — The customer account can't "
                                    "be accessed because it is not yet enabled or has been deactivated.") \
        if acct == A2 else None
    spend = spend_of(plan, "2026-07-20", "2026-09-23")
    line = step(data, spend, fake)
    assert fake.n(acct=A2) == 1 and fake.n("G2", A2) == 0                # one call, nothing more
    assert "accounts 2 (skipped 1)" in line and "errors 0" in line
    geo = gg.load_geo(data)
    assert geo["skip"] == {A2: "2026-10-01"} and S2 not in geo["weeks"] and len(geo["weeks"][S1]) == 10
    assert geo["till"] == "2026-09-23"                                  # a 403 never blocks the chunk
    for k in range(1, 7):                                               # the next days: never asked
        fake.calls.clear()
        step(data, spend, fake, t=T0 + k * 21 * H, today=TODAY + timedelta(days=k))
        assert fake.n(acct=A2) == 0 and fake.n("G1", A1) == 3
    fake.fail = lambda *a: None                                         # 7 days on: asked again
    fake.calls.clear()
    step(data, spend, fake, t=T0 + 7 * 24 * H, today=TODAY + timedelta(days=7))
    assert fake.n("G1", A2) == 3 and gg.load_geo(data)["skip"] == {}
    assert wk(data, S2)["2026-09-21"]["IN"] == [14 * M, 1.4]


def test_geo_account_no_longer_under_the_mcc_costs_no_call(data):
    plan = {A1: {S1: {"2840": 3}}, A2: {S2: {"2840": 1}}}
    fake = FakeAds(plan)
    fake.gone = {A2}
    line = step(data, spend_of(plan, "2026-07-20", "2026-09-23"), fake)
    assert fake.n(acct=A2) == 0 and "accounts 2 (skipped 1)" in line
    assert S2 not in gg.load_geo(data)["weeks"] and gg.load_geo(data)["skip"] == {}   # asked again once it is back


# ── countries ─────────────────────────────────────────────────────────────────────────────────────

def test_geo_iso_country_list_then_by_id_then_parent_else_xx(data):
    cty = {"2840": 5, "2344": 2, "9000001": 1, "9000002": 1, "9000004": 1, None: 1}
    plan = {A1: {S1: cty}}
    fake = FakeAds(plan, byid={"2344": {"cc": "HK"}, "9000001": {"parent": "2840"}, "9000002": {"parent": "9000003"},
                               "9000003": {"cc": "GU"}})
    spend = spend_of(plan, "2026-07-20", "2026-09-23")
    line = step(data, spend, fake)
    byid = [q for c, k, q in fake.calls if k == "BYID"]
    assert fake.n("ISO") == 1 and len(byid) == 2                        # all unmapped ids in one call, then the parents
    assert "IN (2344, 9000001, 9000002, 9000004)" in byid[0] and "IN (9000003)" in byid[1]
    geo = gg.load_geo(data)
    assert geo["iso"]["2344"] == "HK" and geo["iso"]["9000001"] == "US" and geo["iso"]["9000002"] == "GU"
    assert geo["iso"]["9000004"] is None and geo["iso_at"] == "2026-09-24"
    assert geo["weeks"][S1]["2026-09-14"] == {"US": [42 * M, 4.2], "HK": [14 * M, 1.4], "GU": [7 * M, 0.7],
                                              "XX": [14 * M, 1.4]}           # 9000004 + the row without a country
    assert "countries mapped 4, unmapped 1" in line
    cty["9000005"] = 1                                                  # a new id: one by-id call, for it only
    fake.byid["9000005"] = {"cc": "PR"}
    fake.calls.clear()
    step(data, spend, fake, t=T0 + 21 * H, today=TODAY + timedelta(days=1))
    byid = [q for c, k, q in fake.calls if k == "BYID"]
    assert fake.n("ISO") == 0 and len(byid) == 1 and "IN (9000005)" in byid[0]
    fake.calls.clear()                                                  # nothing new: no map call at all
    step(data, spend, fake, t=T0 + 42 * H, today=TODAY + timedelta(days=2))
    assert fake.n("ISO") == 0 and fake.n("BYID") == 0
    fake.byid["9000004"] = {"cc": "VI"}                                 # 30 days on: the list again, the null id again
    fake.calls.clear()
    step(data, spend, fake, t=T0 + 30 * 24 * H, today=TODAY + timedelta(days=30))
    byid = [q for c, k, q in fake.calls if k == "BYID"]
    assert fake.n("ISO") == 1 and len(byid) == 1 and "IN (9000004)" in byid[0]
    geo = gg.load_geo(data)
    assert geo["iso"]["9000004"] == "VI" and geo["iso"]["2344"] == "HK" and geo["iso_at"] == "2026-10-24"


def test_geo_map_call_failing_is_asked_again_and_never_parks_backfilled_cost_in_xx(data):
    """A failing by-id country map: asked once a build (the error counted); its ids are NOT recorded as "no country"
    (asked again at the next chance, never 30 days later). The refresh commits — its weeks are pulled again within
    ~a day, their cost under "XX" meanwhile (the engine does not read such a week as covered) — but a backfill chunk
    is dropped (a backfilled week is never pulled again) and asked again once the map answers."""
    plan = {A1: {S1: {"2840": 1, "2344": 2}}}
    fake = FakeAds(plan, byid={"2344": {"cc": "HK"}})
    fake.fail = lambda acct, k, q: "HTTP 500: internalError" if k == "BYID" else None
    spend = spend_of(plan, "2026-05-25", "2026-09-23")                 # older spend: the backfill has work
    line = step(data, spend, fake)
    assert fake.n("BYID") == 1 and "errors 1" in line and "countries mapped 1, unmapped 1" in line
    geo = gg.load_geo(data)
    assert "2344" not in geo["iso"] and geo["weeks"][S1]["2026-09-14"] == {"US": [7 * M, 0.7], "XX": [14 * M, 1.4]}
    assert min(geo["weeks"][S1]) == "2026-07-20" and geo["bfails"] == 1 and not geo["done"]   # the chunk: dropped
    fake.fail = lambda *a: None
    fake.calls.clear()
    step(data, spend, fake, t=T0 + H)                                   # the next build: asked again, placed right
    geo = gg.load_geo(data)
    assert fake.n("BYID") == 1 and geo["iso"]["2344"] == "HK"
    assert geo["weeks"][S1]["2026-07-13"] == {"US": [7 * M, 0.7], "HK": [14 * M, 1.4]}
    step(data, spend, fake, t=T0 + 21 * H, today=TODAY + timedelta(days=1))   # the refresh re-pulls its own weeks
    assert gg.load_geo(data)["weeks"][S1]["2026-09-14"] == {"US": [7 * M, 0.7], "HK": [14 * M, 1.4]}
    # Google Ads answering WITHOUT a country is another thing: parked as null (XX) until the next Country list
    plan[A1][S1]["9000004"] = 1
    step(data, spend, fake, t=T0 + 42 * H, today=TODAY + timedelta(days=2))
    assert gg.load_geo(data)["iso"]["9000004"] is None


def test_geo_refresh_backoff_holds_before_the_first_commit(data):
    """A persistent error on one account from the very first build: GEO_FAIL_BACKOFF tries, then the next ~20 h
    later — never every hourly build (~40 requests each) while nothing has been committed yet."""
    plan = {A1: {S1: {"2840": 3}}, A2: {S2: {"2840": 1}}}
    fake = FakeAds(plan)
    fake.fail = lambda acct, k, q: "HTTP 500: internalError" if acct == A2 and k == "G1" else None
    spend = spend_of(plan, "2026-07-20", "2026-09-23")
    asked = []
    for i in range(30):                                                 # 30 hourly builds
        n0 = len(fake.calls)
        step(data, spend, fake, t=T0 + i * H)
        if len(fake.calls) > n0:
            asked.append(i)
    geo = gg.load_geo(data)
    assert geo["till"] is None and geo["weeks"] == {}
    assert asked == [0, 1, 2, 22, 23, 24] and fake.n("G1", A2) == 2 * gg.GEO_FAIL_BACKOFF
    fake.fail = lambda *a: None                                         # the error gone: the next due try commits
    step(data, spend, fake, t=T0 + 46 * H)
    assert gg.load_geo(data)["till"] == "2026-09-23"


# ── weeks and the commit rules ───────────────────────────────────────────────────────────────────

def test_geo_weeks_monday_keys_and_partial_current_week(data):
    plan = {A1: {S1: {"2840": 3, "2356": 1}}}
    step(data, spend_of(plan, "2026-07-20", "2026-09-23"), FakeAds(plan))
    geo = gg.load_geo(data)
    ws = geo["weeks"][S1]
    assert sorted(ws) == REFRESH and all(date.fromisoformat(w).weekday() == 0 for w in ws)
    assert ws["2026-09-14"] == {"US": [21 * M, 2.1], "IN": [7 * M, 0.7]}
    assert ws["2026-09-21"] == {"US": [9 * M, 0.9], "IN": [3 * M, 0.3]}  # Mon–Wed: the part-week up to yesterday
    assert (geo["first"], geo["till"], geo["done"], geo["edge"]) == ("2026-07-20", "2026-09-23", True, None)
    assert geo["v"] == 1 and geo["ccy"] == "INR" and geo["_ts"] == T0 and geo["fails"] == 0


def test_geo_refresh_replaces_whole_weeks(data):
    plan = {A1: {S1: {"2840": 3, "2076": 2}}, A2: {S2: {"2840": 1}}}
    fake = FakeAds(plan)
    spend = spend_of(plan, "2026-06-22", "2026-09-23")
    step(data, spend, fake)
    before = gg.load_geo(data)
    assert sorted(before["weeks"][S1]) == ["2026-06-22", "2026-06-29", "2026-07-06", "2026-07-13"] + REFRESH
    plan[A1][S1] = {"2840": 4}                                          # the re-pull: BR is gone, US restated
    fake.fail = lambda acct, k, q: "HTTP 403: authorizationError=CUSTOMER_NOT_ENABLED" if acct == A2 else None
    step(data, spend, fake, t=T0 + 21 * H)
    after = gg.load_geo(data)
    for w in REFRESH[:-1]:
        assert after["weeks"][S1][w] == {"US": [28 * M, 2.8]}
    assert after["weeks"][S1]["2026-07-13"] == before["weeks"][S1]["2026-07-13"]   # outside the refresh: as it was
    assert after["weeks"][S1]["2026-07-13"]["BR"] == [14 * M, 1.4]
    assert after["weeks"][S2] == before["weeks"][S2]                    # a skipped account's store: untouched


def test_geo_chunk_all_or_nothing_and_backoff(data):
    plan = {A1: {S1: {"2840": 3}}, A2: {S2: {"2840": 1}}}
    fake = FakeAds(plan)
    spend = spend_of(plan, "2026-07-20", "2026-09-23")
    step(data, spend, fake)
    before = gg.load_geo(data)
    plan[A1][S1] = {"2840": 5}
    fake.fail = lambda acct, k, q: "HTTP 500: internalError=INTERNAL_ERROR" if acct == A2 and k == "G1" else None
    for i, t in enumerate((T0 + 21 * H, T0 + 22 * H), 1):
        line = step(data, spend, fake, t=t)
        geo = gg.load_geo(data)
        assert geo["weeks"] == before["weeks"] and geo["_ts"] == T0 and geo["till"] == before["till"]
        assert geo["fails"] == i and "errors 1" in line and "weeks refreshed 0" in line
    step(data, spend, fake, t=T0 + 23 * H)                              # the third failure in a row: wait ~a day
    geo = gg.load_geo(data)
    assert geo["weeks"] == before["weeks"] and geo["_ts"] == T0 + 23 * H and geo["fails"] == 0
    assert geo["till"] == before["till"] and geo["rpart"] is None
    fake.calls.clear()
    step(data, spend, fake, t=T0 + 24 * H)
    assert fake.calls == []                                             # not due again yet: no request at all
    # a later piece failing: the pieces before it are kept, the next build asks only the rest
    fake.fail = lambda acct, k, q: "HTTP 500: internalError" if acct == A2 and "BETWEEN '2026-08-17'" in q else None
    step(data, spend, fake, t=T0 + 44 * H)
    geo = gg.load_geo(data)
    assert geo["weeks"][S1]["2026-09-14"] == {"US": [35 * M, 3.5]} and geo["weeks"][S1]["2026-08-17"] == {"US": [21 * M, 2.1]}
    assert geo["rpart"] == {"end": "2026-09-23", "done": ["2026-09-14"]} and geo["fails"] == 1
    fake.fail = lambda *a: None
    fake.calls.clear()
    step(data, spend, fake, t=T0 + 45 * H)
    assert sorted(a for a, _ in fake.ranges("G1", A1)) == ["2026-07-20", "2026-08-17"]
    geo = gg.load_geo(data)
    assert geo["weeks"][S1]["2026-08-17"] == {"US": [35 * M, 3.5]} and geo["rpart"] is None and geo["_ts"] == T0 + 45 * H


def test_geo_downloads_fail_keeps_cost_dl_null(data):
    plan = {A1: {S1: {"2840": 3, "2356": 1}}, A2: {S2: {"2840": 2}}}
    fake = FakeAds(plan)
    fake.fail = lambda acct, k, q: "HTTP 500: internalError" if acct == A1 and k == "G2" else None
    line = step(data, spend_of(plan, "2026-07-20", "2026-09-23"), fake)
    geo = gg.load_geo(data)
    assert geo["weeks"][S1]["2026-09-14"] == {"US": [21 * M, None], "IN": [7 * M, None]}   # unknown, never 0
    assert geo["weeks"][S2]["2026-09-14"] == {"US": [14 * M, 1.4]}
    assert geo["till"] == "2026-09-23" and "errors 3" in line


# ── cadence, backfill, edge, budgets ─────────────────────────────────────────────────────────────

def test_geo_refresh_every_20h_backfill_2_chunks_newest_first_to_400_days(data):
    plan = {A1: {S1: {"2840": 3}}}
    fake = FakeAds(plan)
    spend = spend_of(plan, "2025-01-01", "2026-09-23")
    line = step(data, spend, fake)
    g1 = fake.ranges()
    assert g1[:3] == [("2026-09-14", "2026-09-23"), ("2026-08-17", "2026-09-13"), ("2026-07-20", "2026-08-16")]
    assert g1[3:] == [("2026-06-22", "2026-07-19"), ("2026-05-25", "2026-06-21")]   # then 2 backfill chunks
    assert "weeks refreshed 10, backfill weeks 8 (filling)" in line
    chunks = g1[3:]
    for k in range(1, 6):                                               # hourly builds: no refresh, 2 chunks each
        fake.calls.clear()
        line = step(data, spend, fake, t=T0 + k * H)
        assert fake.n("ISO") == 0 and fake.n("G1") == 2 and fake.n("ROSTER") == 1
        chunks += fake.ranges()
        assert "weeks refreshed 0, backfill weeks 8" in line
    assert line.endswith("(done), calls 5, errors 0, countries mapped 1, unmapped 0")
    starts = [date.fromisoformat(a) for a, _ in chunks]
    assert starts == sorted(starts, reverse=True) and all(s.weekday() == 0 for s in starts)
    for (a, b), (a2, b2) in zip(chunks, chunks[1:]):                    # contiguous 28-day chunks, newest → oldest
        assert date.fromisoformat(b2) + timedelta(days=1) == date.fromisoformat(a)
        assert (date.fromisoformat(b) - date.fromisoformat(a)).days == 27
    assert chunks[-1][0] == "2025-08-18"                                # the Monday of today − 400 days
    geo = gg.load_geo(data)
    assert geo["done"] and geo["edge"] is None and geo["first"] == "2025-08-18" and len(geo["weeks"][S1]) == 58
    fake.calls.clear()
    step(data, spend, fake, t=T0 + 19 * H)                              # done, refresh not due: nothing asked
    assert fake.calls == []
    step(data, spend, fake, t=T0 + 20 * H)                              # 20 h on: the refresh only
    assert fake.ranges() == g1[:3]


def test_geo_refresh_after_a_long_gap_backfills_the_hole(data):
    plan = {A1: {S1: {"2840": 3}}}
    fake = FakeAds(plan)
    step(data, spend_of(plan, "2026-07-20", "2026-09-23"), fake)
    assert gg.load_geo(data)["done"]
    later = TODAY + timedelta(days=70)                                  # off for 10 weeks: a hole behind the refresh
    spend = spend_of(plan, "2026-07-20", (later - timedelta(days=1)).isoformat())
    fake.calls.clear()
    line = step(data, spend, fake, t=T0 + 70 * 24 * H, today=later)
    assert fake.ranges() == [("2026-11-23", "2026-12-02"), ("2026-10-26", "2026-11-22"), ("2026-09-28", "2026-10-25"),
                             ("2026-08-31", "2026-09-27"), ("2026-08-03", "2026-08-30")]
    assert "(filling)" in line
    step(data, spend, fake, t=T0 + 70 * 24 * H + H, today=later)
    geo = gg.load_geo(data)
    assert geo["done"] and geo["first"] == "2026-07-20" and geo["till"] == "2026-12-02"
    ws = geo["weeks"][S1]
    assert sorted(ws) == [(date(2026, 7, 20) + timedelta(weeks=k)).isoformat() for k in range(20)]
    assert ws["2026-09-21"] == {"US": [21 * M, 2.1]}                    # the old part-week, now whole


def test_geo_backfill_stops_at_the_spend_cache_first_day(data):
    plan = {A1: {S1: {"2840": 3}}}
    fake = FakeAds(plan)
    line = step(data, spend_of(plan, "2026-06-10", "2026-09-23"), fake)
    assert fake.ranges()[3:] == [("2026-06-22", "2026-07-19"), ("2026-06-08", "2026-06-21")]   # to the Monday of
                                                                        # the first spend day (the last chunk clipped)
    geo = gg.load_geo(data)
    assert geo["done"] and geo["first"] == "2026-06-08" and "(done)" in line


def test_geo_backfill_edge_after_two_empty_chunks_with_spend(data):
    plan = {A1: {S1: {"2840": 3}}}
    fake = FakeAds(plan, lo="2026-05-01")                               # Google Ads' country rows start here
    spend = spend_of(plan, "2025-01-01", "2026-09-23")
    step(data, spend, fake)
    step(data, spend, fake, t=T0 + H)
    line = step(data, spend, fake, t=T0 + 2 * H)
    geo = gg.load_geo(data)
    assert geo["done"] and geo["edge"] == "2026-03-02" and geo["first"] == "2026-04-27"
    assert min(geo["weeks"][S1]) == "2026-04-27" and "(edge)" in line
    fake.calls.clear()
    step(data, spend, fake, t=T0 + 3 * H)
    assert fake.calls == []


def test_geo_budget_calls_and_quota_stop_cleanly(data):
    plan = {A1: {S1: {"2840": 3}}, A2: {S2: {"2356": 1}}}
    spend = spend_of(plan, "2025-01-01", "2026-09-23")
    fake = FakeAds(plan)                                                # the call cap: the refresh goes first
    line = step(data, spend, fake, max_calls=16)
    assert fake.n() == 14 and fake.n("G1") == 6 and "calls 14" in line
    geo = gg.load_geo(data)
    assert geo["till"] == "2026-09-23" and geo["bfrom"] == "2026-07-20" and not geo["done"]
    shutil_rm(data)
    fake = FakeAds(plan)                                                # a cap inside the refresh: resumed next build
    step(data, spend, fake, max_calls=9)
    assert fake.n() == 6 and gg.load_geo(data)["rpart"] == {"end": "2026-09-23", "done": ["2026-09-14"]}
    assert gg.load_geo(data)["till"] is None
    fake.calls.clear()
    step(data, spend, fake, t=T0 + H, max_calls=9)
    assert [a for a, _ in fake.ranges("G1", A1)] == ["2026-08-17"]
    shutil_rm(data)
    fake = FakeAds(plan)                                                # a quota error: nothing new starts
    fake.fail = lambda acct, k, q: "HTTP 429: quotaError=RESOURCE_EXHAUSTED" \
        if acct == A1 and "BETWEEN '2026-08-17'" in q else None
    line = step(data, spend, fake)
    assert all(a in ("2026-09-14", "2026-08-17") for a, _ in fake.ranges("G1") + fake.ranges("G2"))
    geo = gg.load_geo(data)
    assert geo["rpart"]["done"] == ["2026-09-14"] and geo["till"] is None and geo["bfrom"] is None
    assert sorted(geo["weeks"][S1]) == ["2026-09-14", "2026-09-21"] and "errors 1" in line
    fake.fail = lambda *a: None
    fake.calls.clear()
    step(data, spend, fake, t=T0 + H)
    got = [a for a, _ in fake.ranges("G1", A1)]
    assert got[:2] == ["2026-08-17", "2026-07-20"] and "2026-09-14" not in got      # the rest, then the backfill
    shutil_rm(data)
    clock = Clock(step=10)                                              # the time budget: no chunk without room
    fake = FakeAds({A1: plan[A1]}, clock=clock)
    step(data, spend_of({A1: plan[A1]}, "2025-01-01", "2026-09-23"), fake, clock=clock, max_sec=35)
    assert fake.n() == 4 and gg.load_geo(data)["rpart"]["done"] == ["2026-09-14"]


def shutil_rm(data):
    for p in gg.paths(data):
        if os.path.exists(p):
            os.remove(p)


def test_geo_other_currency_account_to_base(data):
    plan = {A1: {S1: {"2840": 3}}, A2: {S2: {"2840": 1}}}
    fake = FakeAds(plan, ccy={A2: "USD"})
    rate = {A2: FX["USD"] / FX["INR"]}                                  # USD → base INR, as _aggregate does it
    step(data, spend_of(plan, "2026-07-20", "2026-09-23", rate=rate), fake)
    geo = gg.load_geo(data)
    assert geo["weeks"][S1]["2026-09-14"]["US"] == [21 * M, 2.1]
    assert geo["weeks"][S2]["2026-09-14"]["US"] == [gg.cell_cost(7 * M * rate[A2]), 0.7]
    assert gg.cell_cost(7 * M * rate[A2]) % gg.GEO_MICROS_Q == 0 and abs(gg.cell_cost(7 * M * rate[A2]) - 7 * M * rate[A2]) <= 5000


# ── the files ─────────────────────────────────────────────────────────────────────────────────────

def _mtimes(data):
    return tuple(os.stat(p).st_mtime_ns if os.path.exists(p) else None for p in gg.paths(data))


def _raw(path):
    with gzip.open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def test_geo_hot_old_monthly_roll_and_stable_write(data):
    plan = {A1: {S1: {"2840": 3}}}
    fake = FakeAds(plan)
    spend = spend_of(plan, "2025-01-01", "2026-10-02")
    for k in range(6):
        step(data, spend, fake, t=T0 + k * H)
    hp, op = gg.paths(data)
    hot, old = _raw(hp), _raw(op)
    assert hot["cut"] == "2026-06-01" and set(old) == {"v", "ccy", "weeks"} and old["ccy"] == "INR"
    assert min(hot["weeks"][S1]) == "2026-06-01" and len(hot["weeks"][S1]) == 17     # the newest 13 + their month
    assert max(old["weeks"][S1]) == "2026-05-25" and min(old["weeks"][S1]) == "2025-08-18"
    assert "iso" in hot and "iso" not in old and "_ts" in hot
    merged = gg.load_geo(data)
    assert len(merged["weeks"][S1]) == 58 and "cut" not in merged
    m = _mtimes(data)
    step(data, spend, fake, t=T0 + 7 * H)                               # nothing due: nothing written
    assert _mtimes(data) == m
    step(data, spend, fake, t=T0 + 21 * H, today=TODAY + timedelta(days=1))
    m2 = _mtimes(data)
    assert m2[0] != m[0] and m2[1] == m[1]                               # the refresh: hot only
    step(data, spend, fake, t=T0 + 7 * 24 * H, today=date(2026, 10, 1))  # a new month out of the newest 13: .old once
    m3 = _mtimes(data)
    assert m3[1] != m2[1] and _raw(hp)["cut"] == "2026-07-01" and max(_raw(op)["weeks"][S1]) == "2026-06-29"
    step(data, spend, fake, t=T0 + 8 * 24 * H, today=date(2026, 10, 2))
    assert _mtimes(data)[1] == m3[1]
    assert len(gg.load_geo(data)["weeks"][S1]) == 59
    assert gg.save_geo(data, gg.load_geo(data)) is False                 # deterministic: the same cache, no write


def test_geo_lost_old_part_is_refilled(data):
    plan = {A1: {S1: {"2840": 3}}}
    fake = FakeAds(plan)
    spend = spend_of(plan, "2025-01-01", "2026-09-23")
    for k in range(6):
        step(data, spend, fake, t=T0 + k * H)
    os.remove(gg.paths(data)[1])
    geo = gg.load_geo(data)
    assert min(geo["weeks"][S1]) == "2026-06-01"                        # hot only: the old weeks read as never fetched
    fake.calls.clear()
    step(data, spend, fake, t=T0 + 6 * H)
    assert fake.ranges()[0] == ("2026-05-04", "2026-05-31") and not gg.load_geo(data)["done"]


def test_geo_size_caps(tmp_path):
    """The synthetic worst case (SPEC_CD_GEO §G.6): 21 stores × 57 weeks × 160 countries, every cell with cost and
    downloads, and the newest week where the hot file holds the most weeks (13 + 4 of their month). Country shares
    fall off like real ones (Zipf), money in arbitrary micros stored as the step stores it (cell_cost)."""
    rnd = random.Random(20260927)
    ccs = sorted(a + b for a in string.ascii_uppercase for b in string.ascii_uppercase)[:159] + [gg.UNMAPPED]
    newest = date(2026, 9, 21)
    cache = gg.fresh("INR")
    z = sum(1 / (k + 1) for k in range(160))
    for s in range(21):
        order = ccs[:]
        rnd.shuffle(order)
        cpi = {cc: rnd.lognormvariate(3, 0.8) for cc in ccs}
        base = rnd.lognormvariate(12, 1.0)
        ws = {}
        for k in range(57):
            tot = base * rnd.uniform(0.7, 1.3)
            cells = {}
            for i, cc in enumerate(order):
                units = tot / (i + 1) / z * rnd.uniform(0.6, 1.4)
                cells[cc] = [gg.cell_cost(units * M + rnd.random()), round(units / cpi[cc] * rnd.uniform(0.8, 1.2), 2)]
            ws[(newest - timedelta(weeks=k)).isoformat()] = cells
        cache["weeks"]["com.synth.s%02d" % s] = ws
    cache["iso"] = {str(2000 + i): ccs[i % 159] for i in range(246)}
    gg.save_geo(str(tmp_path), cache)
    hp, op = gg.paths(str(tmp_path))
    assert len(_raw(hp)["weeks"]["com.synth.s00"]) == 17 and len(_raw(op)["weeks"]["com.synth.s00"]) == 40
    assert os.path.getsize(hp) <= 450 * 1024, os.path.getsize(hp)
    assert os.path.getsize(op) <= 1600 * 1024, os.path.getsize(op)


def test_geo_start_over_on_v_or_ccy_change(data):
    plan = {A1: {S1: {"2840": 3}}}
    fake = FakeAds(plan)
    spend = spend_of(plan, "2026-07-20", "2026-09-23")
    step(data, spend, fake)
    hp, _ = gg.paths(data)
    raw = _raw(hp)
    raw["v"] = 0
    with gzip.open(hp, "wb") as f:
        f.write(json.dumps(raw).encode("utf-8"))
    assert gg.load_geo(data) is None                                    # another version: none (the tab: no cost)
    fake.calls.clear()
    step(data, spend, fake, t=T0 + H)                                   # a fresh cache, fetched again at once
    assert fake.n("ISO") == 1 and fake.n("G1") == 3 and gg.load_geo(data)["v"] == gg.GEO_V
    usd = dict(spend, currency_src="USD")
    fake.calls.clear()
    step(data, usd, fake, t=T0 + 2 * H)
    geo = gg.load_geo(data)
    assert geo["ccy"] == "USD" and fake.n("G1") == 3 and geo["_ts"] == T0 + 2 * H
    assert geo["weeks"][S1]["2026-09-14"]["US"][0] == gg.cell_cost(21 * M * FX["INR"] / FX["USD"])  # INR account → USD


# ── the public line and the build wiring ─────────────────────────────────────────────────────────

def test_geo_public_line_counts_only(data):
    plan = {A1: {S1: {"2840": 3, "2344": 2, None: 1}}, A2: {S2: {"2356": 1}}}
    fake = FakeAds(plan, ccy={A2: "USD"}, byid={"2344": {"cc": "HK"}})
    fake.fail = lambda acct, k, q: "HTTP 403: authorizationError=CUSTOMER_NOT_ENABLED %s" % acct if acct == A2 else None
    spend = spend_of(plan, "2025-01-01", "2026-09-23")
    lines = [step(data, spend, fake), step(data, spend, fake, t=T0 + H)]
    fake.fail = lambda acct, k, q: "HTTP 500: %s %s secret" % (acct, S1)
    lines.append(step(data, spend, fake, t=T0 + 30 * H))
    lines.append(gg.geo_step(dict(SETTINGS, google_ads_dev_token=None), data, spend, TODAY, search=fake.search))
    lines.append(gg.geo_step(SETTINGS, data, {"error": "x"}, TODAY, search=fake.search))
    assert lines[-1].endswith("(off), calls 0, errors 0, countries mapped 0, unmapped 0")
    secrets = [MCC, A1, A2, S1, S2, DEV, TOK, "secret", "SECRET", "US", "IN", "HK", "XX", "2840", "2344", "2026", "2025",
               "INR", "USD", "0.", "synth", "com."]
    for ln in lines:
        assert LINE.match(ln), ln
        assert "\n" not in ln
        for s in secrets:
            assert s not in ln, (s, ln)


def test_geo_off_no_call_no_file_no_line(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GADS_GEO", raising=False)
    monkeypatch.delenv("VALUE_CD", raising=False)
    assert settings()["gads_geo"] is False and settings()["value_cd"] is False      # both default off
    monkeypatch.setattr(google_ads, "_search", lambda *a: (_ for _ in ()).throw(AssertionError("no request")))
    monkeypatch.setattr(google_ads, "_access_token", lambda *a: (_ for _ in ()).throw(AssertionError("no token")))
    data = str(tmp_path / "data")
    os.makedirs(data)
    plan = {A1: {S1: {"2840": 3}}}
    spend = spend_of(plan, "2026-07-20", "2026-09-23")
    keep = copy.deepcopy(spend)
    build_static._gads_geo_step(dict(SETTINGS, gads_geo=False), data, spend, TODAY)
    build_static._gads_geo_step({}, data, spend, TODAY)
    assert capsys.readouterr().err == "" and os.listdir(data) == [] and spend == keep


def test_geo_step_failure_isolated(tmp_path, monkeypatch, capsys):
    data = str(tmp_path / "data")
    plan = {A1: {S1: {"2840": 3}}}
    spend = spend_of(plan, "2026-07-20", "2026-09-23")
    keep = json.dumps(spend, sort_keys=True)

    def boom(*a, **k):
        a[2]["daily"]                                                   # (reads spend, then fails)
        raise KeyError("x")
    monkeypatch.setattr(gg, "geo_step", boom)
    build_static._gads_geo_step(dict(SETTINGS), data, spend, TODAY)
    assert capsys.readouterr().err == "gads geo skipped: KeyError\n" and json.dumps(spend, sort_keys=True) == keep
    monkeypatch.undo()
    fake = FakeAds(plan)                                                # a bug inside the step's own bookkeeping
    monkeypatch.setattr(gg, "_prune", lambda *a: 1 / 0)
    monkeypatch.setattr(google_ads, "_search", fake.search)
    monkeypatch.setattr(google_ads, "_access_token", lambda *a: TOK)
    build_static._gads_geo_step(dict(SETTINGS), data, spend, TODAY)
    assert capsys.readouterr().err == "gads geo skipped: ZeroDivisionError\n" and json.dumps(spend, sort_keys=True) == keep
    monkeypatch.undo()
    monkeypatch.setattr(google_ads, "_search", fake.search)             # and the real step through the wiring
    monkeypatch.setattr(google_ads, "_access_token", lambda *a: TOK)
    monkeypatch.setattr(google_ads, "_fx_to_usd", FX.get)
    build_static._gads_geo_step(dict(SETTINGS), data, spend, TODAY)
    err = capsys.readouterr().err
    assert LINE.match(err.rstrip("\n")) and err.count("\n") == 1 and json.dumps(spend, sort_keys=True) == keep
    assert gg.load_geo(data)["till"] == "2026-09-23"


def test_geo_step_sits_after_the_spend_cache_write_and_before_roas():
    """The ROAS step: the geo step runs once the merged spend (with its campaign accounts) is written, and before the
    ROAS output is built from it — reading `spend` only, in its own try."""
    src = open(build_static.__file__, encoding="utf-8").read()
    i_acc = src.index("apply_campaign_accounts(spend, _cmap)")
    i_write = src.index("json.dump(spend, _cf)")
    i_geo = src.index("            _gads_geo_step(s, data_dir, spend, today)")
    i_roas = src.index("dashboard[\"roas\"] = build_roas(")
    assert i_acc < i_write < i_geo < i_roas
    body = src[src.index("def _gads_geo_step"):src.index("def data_quality")]
    assert 'if not s.get("gads_geo"):' in body and "except Exception as _ge:" in body
    assert 'print(f"gads geo skipped: {type(_ge).__name__}", file=sys.stderr)' in body


def test_refresh_yml_passes_the_flags():
    y = open(os.path.join(os.path.dirname(build_static.__file__), "..", ".github", "workflows", "refresh.yml"),
             encoding="utf-8").read()
    assert "GADS_GEO:             ${{ vars.GADS_GEO || 'false' }}" in y
    assert "VALUE_CD:             ${{ vars.VALUE_CD || 'false' }}" in y
