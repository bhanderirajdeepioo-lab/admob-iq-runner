"""ROAS: Google Ads spend aggregation (currency → USD), and the store-id join to AdMob apps."""

from admob_iq.fetch import google_ads
from admob_iq.engine.roas import build_roas


def test_aggregate_stores_raw_base_currency_and_sums_by_store():
    """v2: spend is stored RAW in the source (base) currency — NO FX baked in. The one hop to USD /
    display currency happens once, at build time, against a single rate (see build_static)."""
    rows = [
        {"store_id": "com.x.a", "campaign_id": "c1", "name": "Camp A", "status": "ENABLED",
         "date": "2026-07-20", "cost_micros": 100_000_000, "currency": "INR"},
        {"store_id": "com.x.a", "campaign_id": "c1", "name": "Camp A", "status": "ENABLED",
         "date": "2026-07-21", "cost_micros": 200_000_000, "currency": "INR"},
        {"store_id": "com.x.b", "campaign_id": "c2", "name": "Camp B", "status": "PAUSED",
         "date": "2026-07-20", "cost_micros": 50_000_000, "currency": "INR"},
    ]
    agg = google_ads._aggregate(rows, fx_fn=lambda ccy: 0.01)      # fx unused: every row is the base currency
    assert agg["v"] == google_ads.SPEND_CACHE_V
    assert agg["currency_src"] == "INR"
    # RAW INR micros kept verbatim (no 0.01 applied) — that's what kills the fetch-vs-display FX drift
    assert agg["daily"]["com.x.a"] == {"2026-07-20": 100_000_000, "2026-07-21": 200_000_000}
    assert agg["daily"]["com.x.b"] == {"2026-07-20": 50_000_000}
    camps = {c["id"]: c for c in agg["campaigns"]["com.x.a"]}
    assert camps["c1"]["cost_micros"] == 300_000_000 and camps["c1"]["status"] == "ENABLED"


def test_aggregate_converts_minority_currency_into_base():
    """A minority account billed in another currency is folded into the base currency, so the stored
    series stays single-currency (base = whichever currency carries the most spend — here INR)."""
    rows = [
        {"store_id": "com.x.a", "campaign_id": "c1", "name": "A", "status": "ENABLED",
         "date": "2026-07-20", "cost_micros": 1_000_000_000, "currency": "INR"},   # majority → base
        {"store_id": "com.x.b", "campaign_id": "c2", "name": "B", "status": "ENABLED",
         "date": "2026-07-20", "cost_micros": 2_000_000, "currency": "USD"},        # minority → convert to INR
    ]
    # INR→USD=0.01 so USD→INR=100: USD 2_000_000 micros → 200_000_000 INR micros
    agg = google_ads._aggregate(rows, fx_fn=lambda ccy: 0.01 if ccy == "INR" else 1.0)
    assert agg["currency_src"] == "INR"
    assert agg["daily"]["com.x.a"] == {"2026-07-20": 1_000_000_000}       # base, untouched
    assert agg["daily"]["com.x.b"] == {"2026-07-20": 200_000_000}         # USD folded into INR


def test_spend_to_usd_round_trips_to_exact_rupees():
    """The core fix: RAW-INR spend → USD at build rate r, then shown ×(1/r) returns the EXACT original
    rupees — with NO drift, whatever r is. (Before v2, spend was stored in USD at the fetch-time rate
    while display used a different live rate, inflating INR ~13%.)"""
    from admob_iq.build_static import _spend_to_usd
    raw = {"v": 2, "daily": {"com.x.a": {"2026-08-14": 1_829_407_000_000}},   # ₹1,829,407 in micros
           "convval": {"com.x.a": {"2026-08-14": 752_849.0}},
           "campaigns": {"com.x.a": [{"id": "c1", "name": "A", "status": "ENABLED",
                                      "cost_micros": 1_829_407_000_000}]},
           "installs": {"com.x.a": {"2026-08-14": 80_709}},
           "currency_src": "INR", "fx": {}}
    for r in (0.0119, 0.010480, 0.011):                       # even a stale/"wrong" rate must round-trip
        usd = _spend_to_usd(raw, r)
        usd_inr = 1.0 / r                                     # the display toggle uses this SAME rate
        got_rupees = usd["daily"]["com.x.a"]["2026-08-14"] * usd_inr / 1e6
        assert abs(got_rupees - 1_829_407) < 1                # exact to the rupee
        assert usd["installs"]["com.x.a"]["2026-08-14"] == 80_709   # counts untouched by FX


def test_build_roas_joins_by_store_id_and_flags_unmatched():
    spend = {"daily": {"com.x.a": {"2026-07-20": 1_000_000},          # matches App A
                       "com.x.z": {"2026-07-20": 9_000_000}},          # no AdMob app → unmatched
             "campaigns": {"com.x.a": [{"id": "c1", "name": "A", "status": "ENABLED", "cost_micros": 1_000_000}]},
             "currency_src": "INR", "fx": {"INR": 0.01}}
    app_store_ids = {"app-a": "com.x.a", "app-b": "com.x.b"}
    catalog = [{"app_id": "app-a", "app_name": "App A", "rev": 100},
               {"app_id": "app-b", "app_name": "App B", "rev": 50}]
    r = build_roas(spend, app_store_ids, catalog)
    assert r["configured"] is True
    assert "App A" in r["by_app"] and r["by_app"]["App A"]["daily"]["2026-07-20"] == 1_000_000
    assert r["by_app"]["App A"]["store_id"] == "com.x.a"
    assert "App B" not in r["by_app"]                                  # App B had no spend
    assert r["unmatched_spend_usd"] == 9_000_000                       # com.x.z spend surfaced, not dropped
    assert r["currency_src"] == "INR"


def test_build_roas_none_when_not_configured():
    r = build_roas(None, {}, [])
    assert r == {"configured": False, "by_app": {}, "currency_src": "USD", "fx": {},
                 "unmatched_spend_usd": 0}


def test_duplicate_store_id_keeps_highest_revenue_app():
    spend = {"daily": {"com.dup": {"2026-07-20": 5_000_000}}, "campaigns": {},
             "currency_src": "USD", "fx": {}}
    ids = {"app-big": "com.dup", "app-small": "com.dup"}
    catalog = [{"app_id": "app-small", "app_name": "Small", "rev": 10},
               {"app_id": "app-big", "app_name": "Big", "rev": 999}]
    r = build_roas(spend, ids, catalog)
    assert "Big" in r["by_app"] and "Small" not in r["by_app"]         # spend attributed to the big app


def test_build_roas_alias_routes_unmatched_to_app():
    """An app whose AdMob store listing isn't linked (blank store id) can be matched via an alias
    from its Google Ads store id straight to the AdMob app name."""
    spend = {"daily": {"photo.vault.lockgallery": {"2026-07-20": 5_000_000}},
             "campaigns": {"photo.vault.lockgallery": [{"id": "c1", "name": "iStrom gallery",
                                                        "status": "ENABLED", "cost_micros": 5_000_000}]},
             "currency_src": "INR", "fx": {"INR": 0.01}}
    ids = {"app-a": "com.other.pkg"}                              # resolves to a DIFFERENT store id
    catalog = [{"app_id": "app-a", "app_name": "Gallery - Photo Gallery", "rev": 100}]
    r0 = build_roas(spend, ids, catalog)                          # no alias -> unmatched
    assert r0["by_app"] == {} and r0["unmatched_spend_usd"] == 5_000_000
    r1 = build_roas(spend, ids, catalog,                          # alias -> attributed to the app
                    aliases={"photo.vault.lockgallery": "Gallery - Photo Gallery"})
    assert "Gallery - Photo Gallery" in r1["by_app"]
    assert r1["by_app"]["Gallery - Photo Gallery"]["daily"]["2026-07-20"] == 5_000_000
    assert r1["unmatched_spend_usd"] == 0


def test_fetch_app_spend_mock_shape():
    out = google_ads.fetch_app_spend({}, "2026-07-18", "2026-07-20", mode="mock")
    assert set(out["daily"]) == {"com.mock.1", "com.mock.2", "com.mock.3"}
    assert out["daily"]["com.mock.1"]["2026-07-18"] == 500_000_000
    # each mock app has an ENABLED and a PAUSED campaign (status handling)
    st = {c["status"] for c in out["campaigns"]["com.mock.1"]}
    assert st == {"ENABLED", "PAUSED"}


def test_aggregate_installs_sums_by_store_and_date():
    rows = [
        {"store_id": "com.x.a", "date": "2026-07-20", "installs": 12.0},
        {"store_id": "com.x.a", "date": "2026-07-20", "installs": 3.0},   # second campaign, same day
        {"store_id": "com.x.a", "date": "2026-07-21", "installs": 5.0},
        {"store_id": "com.x.b", "date": "2026-07-20", "installs": 7.0},
    ]
    agg = google_ads._aggregate_installs(rows)
    assert agg["com.x.a"] == {"2026-07-20": 15.0, "2026-07-21": 5.0}
    assert agg["com.x.b"] == {"2026-07-20": 7.0}


def test_build_roas_threads_installs_per_app():
    spend = {"daily": {"com.x.a": {"2026-07-20": 1_000_000, "2026-07-21": 2_000_000}},
             "installs": {"com.x.a": {"2026-07-20": 8.0, "2026-07-21": 4.0}},
             "campaigns": {}, "currency_src": "USD", "fx": {}}
    ids = {"app-a": "com.x.a"}
    catalog = [{"app_id": "app-a", "app_name": "App A", "rev": 100}]
    r = build_roas(spend, ids, catalog)
    assert r["by_app"]["App A"]["installs_daily"] == {"2026-07-20": 8.0, "2026-07-21": 4.0}
    # spend still intact alongside installs
    assert r["by_app"]["App A"]["daily"] == {"2026-07-20": 1_000_000, "2026-07-21": 2_000_000}


def test_build_roas_installs_absent_is_safe():
    """Older spend payloads (no 'installs' key) must not crash the join; installs_daily just empty."""
    spend = {"daily": {"com.x.a": {"2026-07-20": 1_000_000}}, "campaigns": {},
             "currency_src": "USD", "fx": {}}
    r = build_roas(spend, {"app-a": "com.x.a"}, [{"app_id": "app-a", "app_name": "App A", "rev": 1}])
    assert r["by_app"]["App A"]["installs_daily"] == {}


def test_mock_spend_carries_installs():
    out = google_ads.fetch_app_spend({}, "2026-07-18", "2026-07-20", mode="mock")
    assert out["installs"]["com.mock.1"]["2026-07-18"] == 50        # 50 + 0*20
    assert out["installs"]["com.mock.2"]["2026-07-18"] == 70        # 50 + 1*20


def test_aggregate_convval_sums_raw_base_by_store_and_date():
    """v2: conversion value is stored RAW in the same base currency as spend (no FX baked in); a
    minority-currency row is folded into the base. Converted to USD once at build time."""
    rows = [
        {"store_id": "com.x.a", "date": "2026-07-20", "convval": 100.0, "currency": "INR"},
        {"store_id": "com.x.a", "date": "2026-07-20", "convval": 50.0, "currency": "INR"},
        {"store_id": "com.x.b", "date": "2026-07-20", "convval": 10.0, "currency": "USD"},
    ]
    # base=INR (matches spend); USD value folded into INR at USD→INR = 1/0.01 = 100 → 10 USD = 1000 INR
    agg = google_ads._aggregate_convval(rows, base="INR", fx_fn=lambda ccy: 0.01 if ccy == "INR" else 1.0)
    assert agg["com.x.a"] == {"2026-07-20": 150.0}    # raw INR value, no FX
    assert agg["com.x.b"] == {"2026-07-20": 1000.0}   # USD folded into INR


def test_build_roas_threads_convval_per_app():
    spend = {"daily": {"com.x.a": {"2026-07-20": 1_000_000}},
             "convval": {"com.x.a": {"2026-07-20": 2.5}},
             "campaigns": {}, "currency_src": "USD", "fx": {}}
    r = build_roas(spend, {"app-a": "com.x.a"}, [{"app_id": "app-a", "app_name": "App A", "rev": 1}])
    assert r["by_app"]["App A"]["convval_daily"] == {"2026-07-20": 2.5}


def test_build_roas_threads_day1_convval_per_app():
    """The frozen day-1 conversion value threads through per app (next to the live convval)."""
    spend = {"daily": {"com.x.a": {"2026-07-20": 1_000_000}},
             "convval": {"com.x.a": {"2026-07-20": 5.0}},        # matured (restated) value
             "convval_day1": {"com.x.a": {"2026-07-20": 2.0}},   # frozen day-1 value
             "campaigns": {}, "currency_src": "USD", "fx": {}}
    r = build_roas(spend, {"app-a": "com.x.a"}, [{"app_id": "app-a", "app_name": "App A", "rev": 1}])
    assert r["by_app"]["App A"]["convval_daily"] == {"2026-07-20": 5.0}
    assert r["by_app"]["App A"]["convval_day1_daily"] == {"2026-07-20": 2.0}


def test_build_roas_day1_absent_is_safe():
    """Older payloads with no day-1 snapshot must not crash; convval_day1_daily just stays empty."""
    spend = {"daily": {"com.x.a": {"2026-07-20": 1_000_000}}, "campaigns": {},
             "currency_src": "USD", "fx": {}}
    r = build_roas(spend, {"app-a": "com.x.a"}, [{"app_id": "app-a", "app_name": "App A", "rev": 1}])
    assert r["by_app"]["App A"]["convval_day1_daily"] == {}


def test_build_roas_convval_absent_is_safe():
    spend = {"daily": {"com.x.a": {"2026-07-20": 1_000_000}}, "campaigns": {},
             "currency_src": "USD", "fx": {}}
    r = build_roas(spend, {"app-a": "com.x.a"}, [{"app_id": "app-a", "app_name": "App A", "rev": 1}])
    assert r["by_app"]["App A"]["convval_daily"] == {}


def test_mock_spend_carries_convval():
    out = google_ads.fetch_app_spend({}, "2026-07-18", "2026-07-20", mode="mock")
    assert out["convval"]["com.mock.1"]["2026-07-18"] == round(500 * 1.3, 2)   # 650.0


def test_merge_spend_keeps_settled_history_and_refreshes_recent():
    cached = {"daily": {"com.x.a": {"2026-01-01": 10, "2026-05-01": 20}},
              "installs": {"com.x.a": {"2026-01-01": 5, "2026-05-01": 6}},
              "convval": {}, "campaigns": {}, "currency_src": "USD", "fx": {}}
    fresh = {"daily": {"com.x.a": {"2026-05-01": 99, "2026-05-02": 30}},   # 05-01 restated up, 05-02 new
             "installs": {"com.x.a": {"2026-05-01": 7}}, "convval": {}, "campaigns": {},
             "currency_src": "USD", "fx": {}}
    m = google_ads.merge_spend(cached, fresh, refetch_start="2026-04-01")
    # settled (< 04-01) kept from cache; recent (>= 04-01) taken fresh — old data never re-fetched
    assert m["daily"]["com.x.a"] == {"2026-01-01": 10, "2026-05-01": 99, "2026-05-02": 30}
    assert m["installs"]["com.x.a"] == {"2026-01-01": 5, "2026-05-01": 7}


def test_merge_spend_transient_gap_never_wipes_recent():
    """If a run's fresh fetch is late/missing a store entirely (Google Ads reports recent spend with a
    lag), its recent spend must NOT be erased — otherwise spend flip-flops in and out each run."""
    cached = {"daily": {"com.x.a": {"2026-05-01": 20, "2026-08-13": 30}}, "installs": {}, "convval": {},
              "campaigns": {}, "currency_src": "USD", "fx": {}}
    fresh = {"daily": {}, "installs": {}, "convval": {}, "campaigns": {},   # this run returned nothing for the store
             "currency_src": "USD", "fx": {}}
    m = google_ads.merge_spend(cached, fresh, refetch_start="2026-05-16")
    assert m["daily"]["com.x.a"] == {"2026-05-01": 20, "2026-08-13": 30}    # recent (08-13) kept, not wiped


def test_merge_spend_edge_cases():
    fresh = {"daily": {}, "installs": {}, "convval": {}, "campaigns": {}, "currency_src": "USD", "fx": {}}
    assert google_ads.merge_spend(None, fresh, "2026-04-01") is fresh          # first run → fresh (backfill)
    assert google_ads.merge_spend({"daily": {}}, None, "2026-04-01") is None    # not configured → no ROAS
    cached = {"daily": {"com.x.a": {"2026-01-01": 10}}}
    assert google_ads.merge_spend(cached, {"error": "boom"}, "2026-04-01") is cached  # transient error → keep history


def test_norm_store_strips_platform_prefix():
    assert google_ads._norm_store("2:1234567") == "1234567"
    assert google_ads._norm_store(" com.x.y ") == "com.x.y"


def test_fetch_app_spend_prefers_google_ads_client(monkeypatch):
    """When GOOGLE_ADS_CLIENT_* are set, the Google Ads token is refreshed with THAT client, not
    the AdMob one — so a token minted with a separate OAuth app can still work."""
    seen = {}

    def fake_token(cid, csec, rt):
        seen["cid"], seen["csec"] = cid, csec
        raise RuntimeError("unauthorized_client: Unauthorized")   # stop after capturing the client
    monkeypatch.setattr(google_ads, "_access_token", fake_token)
    s = {"google_ads_dev_token": "DEV", "google_ads_login_customer_id": "123",
         "google_ads_refresh_token": "RT", "google_client_id": "admob-cid",
         "google_client_secret": "admob-sec", "google_ads_client_id": "ads-cid",
         "google_ads_client_secret": "ads-sec"}
    out = google_ads.fetch_app_spend(s, "2026-07-01", "2026-07-10", mode="live")
    assert seen == {"cid": "ads-cid", "csec": "ads-sec"}          # ads client preferred
    # unauthorized_client → error carries the "alag OAuth client" hint
    assert "unauthorized_client" in out["error"] and "ALAG OAuth client" in out["error"]


def test_fetch_app_spend_falls_back_to_admob_client(monkeypatch):
    seen = {}

    def fake_token(cid, csec, rt):
        seen["cid"] = cid
        raise RuntimeError("boom")
    monkeypatch.setattr(google_ads, "_access_token", fake_token)
    s = {"google_ads_dev_token": "DEV", "google_ads_login_customer_id": "123",
         "google_ads_refresh_token": "RT", "google_client_id": "admob-cid",
         "google_client_secret": "admob-sec"}                     # no google_ads_client_* → fall back
    google_ads.fetch_app_spend(s, "2026-07-01", "2026-07-10", mode="live")
    assert seen["cid"] == "admob-cid"
