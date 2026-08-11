"""QA for the fetch pipeline, alerting rules, notifications, and API contract.
Runs on the mock client + in-memory repo — no creds, no live DB."""

from datetime import date

from admob_iq.fetch import fetcher
from admob_iq.db import InMemoryRepo
from admob_iq.alerting import rules, notify
from admob_iq.engine.anomaly import Signal


def test_build_network_row_derives_metrics():
    raw = {"report_date": date(2026, 7, 20), "account_id": "a", "app_id": "x",
           "ad_unit_id": "u", "country": "US", "format": "banner", "platform": "ANDROID",
           "ad_requests": 1000, "matched_requests": 900, "impressions": 864, "clicks": 9,
           "estimated_earnings_micros": 2_764_800}
    row = fetcher.build_network_row(raw)
    assert row["match_rate"] == 0.9
    assert abs(row["show_rate"] - 0.96) < 1e-9
    assert row["impression_ctr"] > 0
    # $2.7648 / 864 impr * 1000 = $3.20 eCPM -> 3,200,000 micros (units correct)
    assert row["impression_rpm_micros"] == 3_200_000


def test_mock_pipeline_populates_repo_and_snapshots():
    repo = InMemoryRepo()
    totals = fetcher.run_once([{"account_id": "pub-mock"}], repo,
                              today=date(2026, 7, 23), mode="mock", rolling_days=3)
    assert totals["network"] > 0
    assert totals["snapshots"] == totals["network"]            # one snapshot per fact
    assert totals["mediation"] > 0
    assert all("match_rate" in r for r in repo.network)
    # snapshots are stamped with today's snapshot_date -> enables decay tracking
    assert all(r["snapshot_date"] == date(2026, 7, 23) for r in repo.snapshots)


def test_run_once_isolates_a_failing_account(monkeypatch):
    """One account with a bad/expired token (auth error on its first call) must NOT crash the whole
    run — the other accounts still pull, and the failure is recorded in totals['account_errors']."""
    from admob_iq.fetch.admob_client import MockAdMobClient

    class _Boom:                                     # simulates an invalid_scope / bad-token account
        account_id = "pub-bad"
        truncations = []

        def network_report(self, s, e):
            raise Exception("invalid_scope: Bad Request")

    def fake_make_client(acct, *a, **k):
        return _Boom() if acct["account_id"] == "pub-bad" else MockAdMobClient(acct["account_id"])

    monkeypatch.setattr(fetcher, "make_client", fake_make_client)
    repo = InMemoryRepo()
    totals = fetcher.run_once([{"account_id": "pub-bad"}, {"account_id": "pub-mock"}], repo,
                              today=date(2026, 7, 23), mode="mock", rolling_days=3)
    assert totals["network"] > 0                     # the healthy account still pulled its data
    errs = totals.get("account_errors") or []
    assert any(x["account_id"] == "pub-bad" and "invalid_scope" in x["error"] for x in errs)


def test_rules_evaluate_zero_drop_improve():
    prior = [45, 44, 46, 45, 45, 44, 46]                       # baseline (median) = 45
    assert rules.evaluate("revenue", 0, prior).kind == "zero"
    assert rules.evaluate("revenue", 20, prior).kind == "drop"
    assert rules.evaluate("revenue", 60, prior).kind == "improve"


def test_dedupe_suppresses_repeats():
    seen = set()
    out = rules.dedupe([("fp1", "a"), ("fp1", "b"), ("fp2", "c")], seen)
    assert [fp for fp, _ in out] == ["fp1", "fp2"]


def test_notify_dry_run_never_sends():
    sig = Signal("revenue", "critical", "zero", 0, 45, -1.0, "revenue = 0")
    res = notify.notify([(sig, "Bottom_Banner", "ID")], {"notify_dry_run": True})
    assert res and all(r.get("dry_run") for r in res)


def test_api_contract():
    from admob_iq.api.main import overview, alerts, apps
    assert overview()["kpis"]["revenue"] > 0
    assert "critical" in alerts()["counts"]
    assert apps()["apps"][0]["placements"] > 0
