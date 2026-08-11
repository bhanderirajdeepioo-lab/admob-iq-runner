"""ROAS: Google Ads spend aggregation (currency → USD), and the store-id join to AdMob apps."""

from admob_iq.fetch import google_ads
from admob_iq.engine.roas import build_roas


def test_aggregate_converts_currency_and_sums_by_store():
    rows = [
        {"store_id": "com.x.a", "campaign_id": "c1", "name": "Camp A", "status": "ENABLED",
         "date": "2026-07-20", "cost_micros": 100_000_000, "currency": "INR"},
        {"store_id": "com.x.a", "campaign_id": "c1", "name": "Camp A", "status": "ENABLED",
         "date": "2026-07-21", "cost_micros": 200_000_000, "currency": "INR"},
        {"store_id": "com.x.b", "campaign_id": "c2", "name": "Camp B", "status": "PAUSED",
         "date": "2026-07-20", "cost_micros": 50_000_000, "currency": "INR"},
    ]
    agg = google_ads._aggregate(rows, fx_fn=lambda ccy: 0.01)      # INR→USD = 0.01 (test rate)
    assert agg["currency_src"] == "INR"
    # com.x.a: (100 + 200) INR-micros * 0.01 = 3.0 USD, split across 2 dates
    assert agg["daily"]["com.x.a"] == {"2026-07-20": 1_000_000, "2026-07-21": 2_000_000}
    assert agg["daily"]["com.x.b"] == {"2026-07-20": 500_000}
    camps = {c["id"]: c for c in agg["campaigns"]["com.x.a"]}
    assert camps["c1"]["cost_micros"] == 3_000_000 and camps["c1"]["status"] == "ENABLED"


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
