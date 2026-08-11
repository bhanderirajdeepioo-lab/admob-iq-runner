"""QA that the API/dataservice serves REAL engine-computed data (not constants)."""

from admob_iq.api import dataservice
from admob_iq.api.main import overview, alerts as alerts_ep, movers as movers_ep


def test_dashboard_is_engine_computed():
    d = dataservice.build_dashboard()
    # KPIs derived from data
    assert d["kpis"]["revenue"] > 0 and d["kpis"]["ecpm"] > 0
    # the declining banner really classifies as declining; the rising ones as strong
    verdicts = {p["name"]: p["verdict"] for p in d["placements"]}
    assert verdicts["Home_Feed_Banner"] == "declining"
    assert verdicts["LevelEnd_Interstitial"] == "strong"
    # a low-health placement scores low
    health = {p["name"]: p["health"] for p in d["placements"]}
    assert health["Bottom_Banner"] < 40 < health["LevelEnd_Interstitial"]


def test_alerts_have_drops_positives_and_country():
    d = dataservice.build_dashboard()
    a = d["alerts"]
    assert a["counts"]["critical"] >= 1 and a["counts"]["improving"] >= 1
    kinds = {x["kind"] for x in a["items"]}
    assert "zero" in kinds and "spike" in kinds and "improve" in kinds
    # zero-value alert is localized to a country
    zero = next(x for x in a["items"] if x["kind"] == "zero")
    assert "ID" in zero["country"]


def test_movers_deductions_mediation_reco():
    d = dataservice.build_dashboard()
    assert d["movers"]["increasing"] and d["movers"]["decreasing"]
    # worst decliner ranked first (most negative)
    assert d["movers"]["decreasing"][0]["name"] == "Bottom_Banner"
    # highest deduction ranked first and flagged IVT
    assert d["deductions"]["rows"][0]["flag"] == "ivt"
    assert d["mediation"]["summary"]["bidding_share"] > 0.5
    assert d["recommendations"]["total_uplift"] > 0


def test_api_endpoints_return_data():
    assert overview()["kpis"]["revenue"] > 0
    assert alerts_ep()["counts"]["critical"] >= 1
    assert len(movers_ep()["increasing"]) >= 1


def _net_row(day, unit, earn, app="Test App", app_id="app-1", acct="pub-x"):
    """Minimal network_daily row for build_from_db (one ad source, one country)."""
    req, matched, impr, clicks = 10000, 9000, 8000, 40
    return dict(report_date=day, account_id=acct, app_id=app_id, app_name=app,
                ad_unit_id=unit, unit_name=unit.split("/")[-1], ad_source="AdMob",
                source_name="AdMob Network", country="US", format="interstitial",
                platform="android", ad_requests=req, matched_requests=matched,
                impressions=impr, clicks=clicks, estimated_earnings_micros=int(earn * 1e6),
                impression_rpm_micros=0, observed_ecpm_micros=0,
                currency_code="USD", is_finalized=True)


def test_dormant_placement_does_not_alert():
    """A placement that stopped serving MONTHS ago must NOT raise a live 'revenue dropped,
    lost $X/day' alert — only recently-active placements can. An identically-shaped drop on a
    currently-active placement MUST still fire, proving the recency gate isn't over-suppressing."""
    from datetime import date, timedelta
    from admob_iq.db import InMemoryRepo
    from admob_iq.api.dataservice import build_from_db

    repo = InMemoryRepo()
    latest = date(2026, 7, 25)                      # portfolio's newest finished day
    active = "ca-app-pub-1/1111"                    # last data = latest  -> RECENT
    dormant = "ca-app-pub-1/2222"                   # last data = ~4 months earlier -> STALE
    for i in range(12):                             # same 12-day shape for both: flat then a crash
        earn = 100.0 if i < 11 else 18.0            # ~82% drop on the final day
        repo.upsert_network(_net_row(str(latest - timedelta(days=11 - i)), active, earn))
        old = date(2026, 3, 12) - timedelta(days=11 - i)
        repo.upsert_network(_net_row(str(old), dormant, earn))

    d = build_from_db(repo, today=date(2026, 7, 26))
    alert_ids = {a.get("id") for a in d["alerts"]["items"]}
    assert active in alert_ids, "recently-active placement's drop should still alert"
    assert dormant not in alert_ids, "dormant (months-stale) placement must not alert"


def test_build_from_db_uses_real_fetched_rows():
    """Prove the production path: fetcher -> repo (DB) -> build_from_db -> dashboard."""
    from datetime import date
    from admob_iq.fetch import fetcher
    from admob_iq.db import InMemoryRepo
    from admob_iq.api.dataservice import build_from_db, build_dashboard
    repo = InMemoryRepo()
    fetcher.run_once([{"account_id": "pub-mock"}], repo, today=date(2026, 7, 23),
                     mode="mock", rolling_days=10)
    d = build_from_db(repo, today=date(2026, 7, 23))
    assert d["kpis"]["revenue"] > 0                       # computed from fetched rows
    assert d["placements"] and all("verdict" in p for p in d["placements"])
    assert d["apps"] and d["mediation"]["rows"]
    assert set(d.keys()) == set(build_dashboard().keys())  # same frontend contract
    # empty DB gracefully falls back to demo
    assert build_from_db(InMemoryRepo())["kpis"]["revenue"] > 0


def _med_row(day, app, app_id, src, src_name, earn, impr=1000, matched=900, req=1000):
    """One stored mediation row (as upsert_mediation keeps it): daily-by-ad-source."""
    return dict(report_date=day, account_id="pub-x", app_id=app_id, app_name=app,
                ad_unit_id=app_id + "/u1", unit_name="u1", ad_source=src,
                source_name=src_name, country="US", format="interstitial",
                platform="android", ad_requests=req, matched_requests=matched,
                impressions=impr, clicks=5,
                estimated_earnings_micros=int(earn * 1e6), currency_code="USD")


def test_build_mediation_daily_is_compact_and_windowable():
    """Daily-by-source mediation ships date × app × source with [dayidx,rev_micros,impr,matched,req]
    — enough to re-aggregate any period client-side, with NO new AdMob fetch."""
    from admob_iq.db import InMemoryRepo
    from admob_iq.api.dataservice import build_mediation_daily
    repo = InMemoryRepo()
    # App A: AdMob + Meta on two days; App B: AdMob only on day 2
    repo.upsert_mediation(_med_row("2026-07-20", "App A", "app-a", "ADMOB", "AdMob Network", 10))
    repo.upsert_mediation(_med_row("2026-07-20", "App A", "app-a", "META", "Meta Audience", 4))
    repo.upsert_mediation(_med_row("2026-07-21", "App A", "app-a", "ADMOB", "AdMob Network", 12))
    repo.upsert_mediation(_med_row("2026-07-21", "App B", "app-b", "ADMOB", "AdMob Network", 7))

    md = build_mediation_daily(repo)
    assert md["dates"] == ["2026-07-20", "2026-07-21"]
    assert md["names"]["META"] == "Meta Audience"
    # App A, Meta: one row on day 0 (2026-07-20), rev 4_000_000 micros
    a_meta = md["by_app"]["App A"]["META"]
    assert a_meta == [[0, 4_000_000, 1000, 900, 1000]]
    # App A, AdMob: day 0 = $10, day 1 = $12
    a_admob = {r[0]: r[1] for r in md["by_app"]["App A"]["ADMOB"]}
    assert a_admob == {0: 10_000_000, 1: 12_000_000}
    # App B only appears on day 1
    assert md["by_app"]["App B"]["ADMOB"] == [[1, 7_000_000, 1000, 900, 1000]]
    # Windowing day 1 only (index 1): portfolio AdMob = 12 + 7 = 19, Meta = 0
    day1 = 1
    admob_d1 = sum(r[1] for app in md["by_app"].values()
                   for r in app.get("ADMOB", []) if r[0] == day1)
    assert admob_d1 == 19_000_000


def test_build_mediation_daily_empty_is_safe():
    from admob_iq.db import InMemoryRepo
    from admob_iq.api.dataservice import build_mediation_daily
    md = build_mediation_daily(InMemoryRepo())
    assert md == {"dates": [], "names": {}, "by_app": {}, "currency": "USD"}


def _snap(rd, sd, unit, earn, app="App A", app_id="app-a"):
    return dict(report_date=rd, snapshot_date=sd, account_id="pub-x", app_id=app_id,
                ad_unit_id=unit, country="All", format="interstitial",
                estimated_earnings_micros=int(earn * 1e6), impressions=1000, clicks=5)


def test_build_deductions_daily_captures_real_decay_only():
    """first-vs-latest POST-CLOSE snapshot = the deduction; stable & pre-close cells are excluded."""
    from admob_iq.db import InMemoryRepo
    from admob_iq.api.dataservice import build_deductions_daily
    repo = InMemoryRepo()
    repo.upsert_network(_net_row("2026-07-20", "app-a/u1", 100, app="App A", app_id="app-a"))
    # unit u1, report_date 2026-07-20: post-close estimate decays 100 -> 92 -> 88 (a real deduction)
    repo.append_snapshot(_snap("2026-07-20", "2026-07-21", "app-a/u1", 100))
    repo.append_snapshot(_snap("2026-07-20", "2026-07-22", "app-a/u1", 92))
    repo.append_snapshot(_snap("2026-07-20", "2026-07-23", "app-a/u1", 88))
    # unit u2: STABLE post-close (no decay) -> must be excluded
    repo.upsert_network(_net_row("2026-07-20", "app-a/u2", 50, app="App A", app_id="app-a"))
    repo.append_snapshot(_snap("2026-07-20", "2026-07-21", "app-a/u2", 50))
    repo.append_snapshot(_snap("2026-07-20", "2026-07-22", "app-a/u2", 50))
    # unit u1, an INTRADAY-only snapshot (sd == rd) -> not post-close, excluded on its own
    repo.append_snapshot(_snap("2026-07-25", "2026-07-25", "app-a/u1", 30))

    dd = build_deductions_daily(repo)
    assert dd["dates"] == ["2026-07-20"]                      # only the day with a real drop
    assert set(dd["data"].keys()) == {"app-a/u1"}            # stable u2 excluded, intraday-only day excluded
    assert dd["data"]["app-a/u1"] == [[0, 100_000_000, 88_000_000]]   # first=100, latest=88
    assert dd["units"]["app-a/u1"]["app_name"] == "App A"    # name joined from the network report


def test_build_deductions_daily_empty_is_safe():
    from admob_iq.db import InMemoryRepo
    from admob_iq.api.dataservice import build_deductions_daily
    dd = build_deductions_daily(InMemoryRepo())
    assert dd == {"dates": [], "units": {}, "data": {}}


def test_revenue_is_deduction_adjusted():
    """Revenue is netted DOWN by the tracked per-unit-day deduction so it matches the user's live
    AdMob; the Deductions data itself stays raw (it's the source of the adjustment)."""
    from datetime import date
    from admob_iq.db import InMemoryRepo
    from admob_iq.api.dataservice import build_from_db, build_deductions_daily
    repo = InMemoryRepo()
    repo.upsert_mediation(_med_row("2026-07-20", "App A", "app-a", "ADMOB", "AdMob Network", 100))
    # post-close snapshots for that unit-day decay $100 -> $88 (deduction $12)
    repo.append_snapshot(_snap("2026-07-20", "2026-07-21", "app-a/u1", 100))
    repo.append_snapshot(_snap("2026-07-20", "2026-07-23", "app-a/u1", 88))
    d = build_from_db(repo, today=date(2026, 7, 22))
    pl = [p for p in d["placements"] if p["id"] == "app-a/u1"]
    assert pl, "placement present"
    day = [r for r in pl[0]["daily"] if r[0] == "2026-07-20"][0]
    assert abs(day[1] - 88_000_000) < 10_000, f"revenue netted to ~$88, got {day[1]/1e6}"
    # deductions_daily stays RAW ($12), unaffected by the revenue adjustment
    dd = build_deductions_daily(repo)
    assert dd["data"]["app-a/u1"] == [[0, 100_000_000, 88_000_000]]


def test_revenue_unadjusted_when_no_decay():
    """No decaying snapshots → no adjustment (finalized/older days keep the raw AdMob estimate)."""
    from datetime import date
    from admob_iq.db import InMemoryRepo
    from admob_iq.api.dataservice import build_from_db
    repo = InMemoryRepo()
    repo.upsert_mediation(_med_row("2026-07-20", "App A", "app-a", "ADMOB", "AdMob Network", 100))
    d = build_from_db(repo, today=date(2026, 7, 22))
    pl = [p for p in d["placements"] if p["id"] == "app-a/u1"][0]
    day = [r for r in pl["daily"] if r[0] == "2026-07-20"][0]
    assert abs(day[1] - 100_000_000) < 10_000, "no decay → revenue unchanged ($100)"
