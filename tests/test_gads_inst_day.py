"""Google Ads installs by country × day (admob_iq.fetch.gads_inst_day) — offline against a fake Google Ads API
(SYNTHETIC accounts, stores and numbers): the refresh and the backfill ranges, Play installs and first opens per store ×
day × country, a disabled account's stores left unknown ("lost"), a failed account leaving its range for the next build,
the call budget, and a public line of counts only."""
import gzip
import json
import os
from datetime import date, datetime, timedelta, timezone

from admob_iq.fetch import gads_inst_day as gi

TODAY = date(2026, 11, 2)
NOW = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)
MCC, A1, A2, A3 = "1110001111", "2220002222", "3330003333", "4440004444"
BIG, SMALL, GONE = "com.example.big", "com.example.small", "com.example.gone"
S = {"google_ads_dev_token": "dev-SECRET", "google_ads_login_customer_id": MCC, "google_ads_refresh_token": "rt-SECRET",
     "google_ads_client_id": "cid", "google_ads_client_secret": "csec"}
CTY = (("2840", 60), ("2356", 40))
ISO = {"2840": "US", "2356": "IN"}
BASE = {BIG: 100, SMALL: 10}                          # Play installs a day; first opens = 0.9 ×


def _days(a, b):
    a, b = date.fromisoformat(a), date.fromisoformat(b)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def spend():
    d = lambda a: {k: 50.0 for k in _days(a, TODAY.isoformat())}
    return {"daily": {BIG: d("2026-08-01"), SMALL: d("2026-10-01"), GONE: d("2026-09-01")},
            "campaigns": {BIG: [{"account": A1}], SMALL: [{"account": A2}], GONE: [{"account": A3}]}}


class FakeAds:
    def __init__(self, fail=None):
        self.fail, self.calls = fail or {}, []
        self.stores = {A1: (BIG,), A2: (SMALL,), A3: (GONE,)}

    def __call__(self, cid, login, dev, token, q):
        assert (login, dev, token) == (MCC, "dev-SECRET", "tok-SECRET")
        kind = ("ROSTER" if "customer_client" in q else "CA" if "FROM conversion_action" in q else
                "ISO" if "geo_target_constant" in q else "GEO")
        self.calls.append((cid, kind))
        if cid == A3 and kind in ("CA", "GEO"):
            raise RuntimeError("HTTP 403: authorizationError=CUSTOMER_NOT_ENABLED")
        if (cid, kind) in self.fail:
            raise RuntimeError(self.fail[(cid, kind)])
        if kind == "ROSTER":
            return [{"customerClient": {"id": a, "currencyCode": "INR", "manager": False}} for a in (A1, A2, A3)]
        if kind == "CA":
            return [{"conversionAction": {"id": "7", "type": "ANDROID_INSTALLS_ALL_OTHER_APPS"}},
                    {"conversionAction": {"id": "8", "type": "FIREBASE_ANDROID_FIRST_OPEN"}},
                    {"conversionAction": {"id": "9", "type": "UNKNOWN"}}]
        if kind == "ISO":
            return [{"geoTargetConstant": {"id": i, "countryCode": c, "targetType": "Country"}} for i, c in ISO.items()]
        a, b = q.split("BETWEEN '")[1].split("'")[0], q.split("AND '")[1].split("'")[0]
        out = []
        for sid in self.stores[cid]:
            first = min(spend()["daily"][sid])
            for d in _days(max(a, first), b):
                for ccid, sh in CTY:
                    for act, mult in (("7", 1.0), ("8", 0.9), ("9", 5.0)):
                        out.append({"campaign": {"appCampaignSetting": {"appId": sid}},
                                    "geographicView": {"countryCriterionId": ccid, "locationType": "LOCATION_OF_PRESENCE"},
                                    "segments": {"date": d, "conversionAction": "customers/%s/conversionActions/%s" % (cid, act)},
                                    "metrics": {"allConversions": BASE[sid] * sh / 100 * mult}})
        return out


def month(tmp, m):
    with gzip.open(os.path.join(tmp, gi.DIR, m + ".json.gz"), "rt") as f:
        return json.load(f)


def state(tmp):
    with gzip.open(os.path.join(tmp, gi.DIR, "state.json.gz"), "rt") as f:
        return json.load(f)


def run(tmp, fake, now=NOW):
    return gi.step(S, str(tmp), spend(), TODAY, now=now, search=fake, token="tok-SECRET")


def test_refresh_then_backfill_to_the_floor(tmp_path):
    f = FakeAds()
    line = run(tmp_path, f)
    st = state(tmp_path)
    assert st["cov"] == [["2026-08-01", "2026-11-02"]] and st["done"] and st["floor"] == "2026-08-01"
    assert line.startswith("gads inst: ranges 4 (refresh 1), accounts 3, stores 2, lost 2, backfill done, calls ")
    for s_ in (MCC, A1, A2, A3, BIG, SMALL, GONE, "2026", "SECRET", "US", "IN"):
        assert s_ not in line
    oct_ = month(tmp_path, "2026-10")["days"]
    assert oct_[BIG]["2026-10-05"] == {"IN": [40, 36], "US": [60, 54]}           # Play installs, first opens
    assert oct_[SMALL]["2026-10-05"] == {"IN": [4, 3.6], "US": [6, 5.4]}
    sep = month(tmp_path, "2026-09")["days"]
    assert GONE not in oct_ and GONE not in sep
    assert sep[SMALL] == {"2026-09-29": {}, "2026-09-30": {}}       # the refresh range: written whole, nothing those days
    assert len(month(tmp_path, "2026-08")["days"][BIG]) == 31
    assert {tuple(x[2:]) for x in st["lost"]} == {(GONE,)}
    assert gi.load_all(str(tmp_path))[BIG]["2026-08-01"]["US"] == [60, 54]
    # the next build an hour later: nothing due; 7 hours later: the refresh only
    f2 = FakeAds()
    assert run(tmp_path, f2, NOW + timedelta(hours=1)).startswith("gads inst: ranges 0 (refresh 0)") and f2.calls == []
    f3 = FakeAds()
    assert run(tmp_path, f3, NOW + timedelta(hours=7)).startswith("gads inst: ranges 1 (refresh 1)")
    assert {k for _, k in f3.calls} == {"ROSTER", "CA", "GEO"}                     # (the country map kept)


def test_a_failed_account_leaves_its_range_for_the_next_build(tmp_path):
    f = FakeAds(fail={(A2, "GEO"): "HTTP 500: internalError=INTERNAL_ERROR"})
    line = run(tmp_path, f)
    st = state(tmp_path)
    assert "recent_at" not in st and ["2026-09-29", "2026-11-02"] not in st["cov"]
    assert "2026-10-05" in month(tmp_path, "2026-10")["days"][BIG]               # BIG's own account answered
    assert SMALL not in month(tmp_path, "2026-10")["days"]
    assert "errors 1" in line
    run(tmp_path, FakeAds())                                                      # next build: asked again
    assert state(tmp_path)["cov"] == [["2026-08-01", "2026-11-02"]]
    assert month(tmp_path, "2026-10")["days"][SMALL]["2026-10-05"]["US"] == [6, 5.4]


def test_the_call_budget_stops_cleanly_and_goes_on(tmp_path, monkeypatch):
    monkeypatch.setattr(gi, "MAX_CALLS", 9)
    line = run(tmp_path, FakeAds())
    assert ", stopped calls" in line and not state(tmp_path).get("done")
    monkeypatch.setattr(gi, "MAX_CALLS", 120)
    run(tmp_path, FakeAds(), NOW + timedelta(hours=1))
    assert state(tmp_path)["done"] and state(tmp_path)["cov"] == [["2026-08-01", "2026-11-02"]]


def test_plan_walks_down_over_covered_runs():
    st = {"cov": [["2026-09-01", "2026-09-20"]], "recent_at": NOW.isoformat()}
    p = gi.plan(st, spend(), TODAY, NOW + timedelta(hours=1))
    assert p == [("backfill", date(2026, 9, 21), date(2026, 9, 28)),
                 ("backfill", date(2026, 8, 4), date(2026, 8, 31)),
                 ("backfill", date(2026, 8, 1), date(2026, 8, 3))]


def test_off_without_settings(tmp_path):
    assert gi.step({}, str(tmp_path), spend(), TODAY).startswith("gads inst: off")
