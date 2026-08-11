"""QA for the fixes + new advisors flagged by the audit:
month-finalize, configurable rule thresholds, root-cause, mediation, compliance."""

from datetime import date

from admob_iq.fetch import fetcher
from admob_iq.db import InMemoryRepo
from admob_iq.alerting import rules
from admob_iq.engine import rootcause, mediation, compliance


# ---- month-close finalize (was claimed but missing) ----
def test_finalize_month_marks_finalized():
    repo = InMemoryRepo()
    n = fetcher.finalize_month([{"account_id": "pub-mock"}], repo,
                               year=2026, month=6, mode="mock")
    assert n > 0
    assert all(r["is_finalized"] is True for r in repo.network)


# ---- configurable rules are actually wired (per-metric thresholds + enabled) ----
def test_rules_use_per_metric_thresholds():
    prior = [1000] * 7                       # baseline 1000
    # requests rule fires at -50%, revenue at -40%
    assert rules.evaluate("requests", 600, prior).kind == "none"    # -40% < 50% threshold
    assert rules.evaluate("revenue", 600, prior).kind == "drop"     # -40% hits revenue rule


def test_disabled_rule_is_suppressed():
    # the disable mechanism: a rule with enabled=False suppresses its check even on a big breach
    off = [{"rule_id": "show_off", "metric": "show_rate", "kind": "drop_pt",
            "threshold": 0.15, "severity": "watch", "enabled": False}]
    sig = rules.evaluate("show_rate", 0.70, [0.94] * 7, rules=off)
    assert not sig.is_alert


def test_show_rate_drop_alerts_when_enabled():
    # show_rate drop is ON by default now -> a >15pt drop fires
    sig = rules.evaluate("show_rate", 0.70, [0.94] * 7)
    assert sig.is_alert and sig.kind == "drop"


# ---- root-cause classifier (blueprint Module C) ----
def test_rootcause_buckets():
    assert rootcause.classify(ctr_change=1.0)[0] == "ivt"
    assert rootcause.classify(show_change=-0.2)[0] == "technical"
    assert rootcause.classify(match_change=-0.2)[0] == "floor_misconfig"
    assert rootcause.classify(impr_per_dau_change=-0.2)[0] == "ux_frequency"
    assert rootcause.classify(ecpm_change=-0.15)[0] == "seasonality"
    assert rootcause.classify(ecpm_change=-0.15, ios_only=True)[0] == "signal_loss"
    assert rootcause.classify(ecpm_change=-0.15, yoy_down=True)[0] == "demand_drop"
    assert rootcause.classify()[0] == "unknown"


# ---- mediation advisor (blueprint deliverable #9) ----
def _med_rows():
    return [
        {"ad_source": "AppLovin", "type": "bidding", "fill": 0.88, "ecpm": 4.1, "revenue": 22, "latency_s": 0.6},
        {"ad_source": "AdMob", "type": "bidding", "fill": 0.90, "ecpm": 3.2, "revenue": 34, "latency_s": 0.0},
        {"ad_source": "ironSource", "type": "waterfall", "fill": 0.60, "ecpm": 1.9, "revenue": 7, "latency_s": 1.4},
    ]


def test_mediation_summarize():
    s = mediation.summarize(_med_rows())
    assert s["best_ecpm"]["ad_source"] == "AppLovin"
    assert s["bidding_share"] > 0.8 and s["networks"] == 3


def test_mediation_suggests_review_and_add():
    recs = mediation.suggest(_med_rows())
    assert any("ironSource" in r["action"] for r in recs)      # stale waterfall
    low_bidding = [
        {"ad_source": "WF1", "type": "waterfall", "fill": 0.7, "ecpm": 2, "revenue": 50, "latency_s": 0.5},
        {"ad_source": "B1", "type": "bidding", "fill": 0.8, "ecpm": 3, "revenue": 10, "latency_s": 0.5},
    ]
    assert any("Add bidding" in r["action"] for r in mediation.suggest(low_bidding))


# ---- compliance aggregator ----
def test_compliance_status():
    assert compliance.account_health(app_ads_txt_ok=False)["status"] == "red"
    assert compliance.account_health(ivt_flags=1, consent_gaps=2)["status"] == "amber"
    assert compliance.account_health()["status"] == "green"
