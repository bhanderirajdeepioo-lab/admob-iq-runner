"""QA for the ad-unit x country baseline rollup (Step 2 storage model)."""

from datetime import date

from admob_iq.engine.rollup import rollup_adunit_country


def _row(d, unit, country, req, matched, impr, clicks, earn, app="A"):
    return dict(report_date=d, account_id="pub", app_id=app, app_name="App " + app,
                ad_unit_id=unit, unit_name=unit, country=country,
                ad_requests=req, matched_requests=matched, impressions=impr,
                clicks=clicks, estimated_earnings_micros=earn, currency_code="USD")


def test_past_months_rollup_current_stays_daily():
    rows = [
        # June (past): 2 days for U1/US
        _row("2026-06-01", "U1", "US", 1000, 900, 800, 8, 4_000_000),   # ctr 1.0%
        _row("2026-06-02", "U1", "US", 1000, 900, 800, 24, 8_000_000),  # ctr 3.0%
        # July (current): daily, must NOT be rolled up
        _row("2026-07-10", "U1", "US", 1000, 900, 800, 16, 6_000_000),
    ]
    rollups, current = rollup_adunit_country(rows, today=date(2026, 7, 15), window_start=date(2025, 1, 1))
    assert len(current) == 1 and str(current[0]["report_date"]) == "2026-07-10"
    assert len(rollups) == 1
    g = rollups[0]
    assert g["month"] == "2026-06" and g["ad_unit_id"] == "U1" and g["country"] == "US"
    assert g["days"] == 2
    assert g["impressions"] == 1600 and g["clicks"] == 32          # month sums
    # daily CTR range across the two days: 1.0% .. 3.0%
    assert round(g["ctr_min"], 4) == 0.01 and round(g["ctr_max"], 4) == 0.03
    # volume-weighted avg CTR = 32/1600 = 2.0%
    assert round(g["ctr_avg"], 4) == 0.02


def test_coverage_guard_skips_window_clipped_month():
    rows = [
        _row("2026-05-20", "U1", "US", 1000, 900, 800, 8, 4_000_000),   # May
        _row("2026-06-05", "U1", "US", 1000, 900, 800, 8, 4_000_000),   # June
    ]
    # window started 2026-06-01: June's 1st is covered (not > ), May's 1st is NOT (clipped)
    rollups, _ = rollup_adunit_country(rows, today=date(2026, 7, 1), window_start=date(2026, 6, 1))
    months = {r["month"] for r in rollups}
    assert months == {"2026-06"}          # May skipped (window clipped it), June kept


def test_all_time_backfill_rolls_up_everything():
    rows = [
        _row("2025-07-25", "U1", "IN", 500, 400, 380, 4, 200_000),      # partial first month
        _row("2025-08-10", "U1", "IN", 500, 400, 380, 4, 200_000),
    ]
    # window_start=None => all-time: even the genuinely-partial first month is included
    rollups, _ = rollup_adunit_country(rows, today=date(2026, 7, 1), window_start=None)
    assert {r["month"] for r in rollups} == {"2025-07", "2025-08"}


def test_separate_countries_and_units_are_distinct_rows():
    rows = [
        _row("2026-06-01", "U1", "US", 1000, 900, 800, 8, 4_000_000),
        _row("2026-06-01", "U1", "IN", 1000, 900, 800, 8, 1_000_000),
        _row("2026-06-01", "U2", "US", 1000, 900, 800, 8, 4_000_000),
    ]
    rollups, _ = rollup_adunit_country(rows, today=date(2026, 7, 1), window_start=None)
    keys = {(r["ad_unit_id"], r["country"]) for r in rollups}
    assert keys == {("U1", "US"), ("U1", "IN"), ("U2", "US")}
    # eCPM differs by geo -> distinct baselines
    us = next(r for r in rollups if r["ad_unit_id"] == "U1" and r["country"] == "US")
    inn = next(r for r in rollups if r["ad_unit_id"] == "U1" and r["country"] == "IN")
    assert us["ecpm_avg"] > inn["ecpm_avg"]


def test_run_once_populates_baseline_store(tmp_path):
    """End-to-end through the fetcher (mock): the ad-unit×country baseline lands as monthly
    rollups (past) + current-month daily, both in the repo."""
    from datetime import date
    from admob_iq.db import InMemoryRepo
    from admob_iq.fetch import fetcher
    repo = InMemoryRepo()
    totals = fetcher.run_once([{"account_id": "pub-mock"}], repo, today=date(2026, 7, 15),
                              mode="mock", rolling_days=10, adunit_country_days=90)
    from admob_iq.db import iter_monthly, daily_series
    acm = repo.fetch_adunit_country_monthly()
    acd = repo.fetch_adunit_country_daily()
    assert totals["adunit_country"] > 0
    monthly = list(iter_monthly(acm))
    assert monthly and acd["dates"]
    # every monthly row is a completed (past) month; the daily table is the CURRENT month
    assert all(r["month"] < "2026-07" for r in monthly)
    assert acd["month"] == "2026-07" and all(d[:7] == "2026-07" for d in acd["dates"])
    # rollup rows carry the range + average fields
    g = monthly[0]
    for f in ("ctr_min", "ctr_max", "ctr_avg", "ecpm_min", "ecpm_max", "ecpm_avg", "days", "country"):
        assert f in g
    # daily accessor returns date-ordered rows for a real (unit, country)
    uid = next(iter(acd["data"])); c = next(iter(acd["data"][uid]))
    ser = daily_series(acd, uid, c)
    assert ser and ser[0]["report_date"] <= ser[-1]["report_date"]


def test_mock_data_start():
    from datetime import date, timedelta
    from admob_iq.fetch.admob_client import MockAdMobClient
    assert MockAdMobClient("pub-x").data_start(date(2026, 7, 26)) == date(2026, 7, 26) - timedelta(days=100)


def test_full_history_backfill_includes_first_partial_month():
    """A full-history backfill probes the account's real start and rolls up EVERY month found,
    including the genuinely-partial first month (no coverage-guard drop)."""
    from datetime import date
    from admob_iq.db import InMemoryRepo, iter_monthly
    from admob_iq.fetch import fetcher
    repo = InMemoryRepo()
    fetcher.run_once([{"account_id": "pub-mock"}], repo, today=date(2026, 7, 15), mode="mock",
                     rolling_days=10, adunit_country_days=2555, ac_full_history=True)
    months = sorted({r["month"] for r in iter_monthly(repo.fetch_adunit_country_monthly())})
    # mock data_start = today-100 = 2026-04-06 → the partial April month must be present
    assert months and months[0] == "2026-04"
