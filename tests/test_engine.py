"""QA for the analysis engine. Pure-function tests — no DB or AdMob creds needed.
Each blueprint/wireframe behaviour has at least one assertion here."""

import math
from admob_iq.engine import metrics, baseline, anomaly, deduction, trend, health, recommend


# ---------------- metrics ----------------
def test_metric_formulas():
    assert metrics.match_rate(1000, 900) == 0.9
    assert metrics.show_rate(900, 810) == 0.9
    assert metrics.ctr(1000, 10) == 0.01
    # $45 earnings over 15k impressions -> eCPM $3.00
    assert metrics.ecpm(45_000_000, 15_000) == 3.0
    assert metrics.rpm is metrics.ecpm            # RPM == computed eCPM
    assert metrics.sdiv(1, 0) == 0.0              # no divide-by-zero blowups


def test_arpdau_identity():
    # ARPDAU = eCPM/1000 * impressions_per_DAU (no double-count of fill)
    assert math.isclose(metrics.arpdau(3.0, 3), 0.009)
    # full-funnel form from requests/DAU: impr = 3 * 0.9 * 0.96 = 2.592
    assert math.isclose(metrics.arpdau_from_requests(3.0, 0.9, 0.96, 3), 0.007776)


# ---------------- baseline ----------------
def test_rolling_and_weekday_baseline():
    assert baseline.rolling_median([1, 2, 3, 4, 5, 6, 7, 100], window=7) == 5
    # same-weekday: 7,14,21,28 days back from a 28-day series 1..28 -> [22,15,8,1]
    assert baseline.weekday_baseline(list(range(1, 29))) == 11.5


# ---------------- anomaly ----------------
def test_zero_value_is_critical():
    s = anomaly.detect("revenue", 0, 45)
    assert s.severity == "critical" and s.kind == "zero"


def test_sharp_revenue_drop_is_warning():
    s = anomaly.detect("revenue", 20, 45)
    assert s.severity == "warning" and s.kind == "drop"


def test_match_rate_point_drop():
    s = anomaly.detect("match_rate", 0.61, 0.92)
    assert s.severity == "warning" and s.kind == "drop"


def test_ctr_spike_is_ivt_critical():
    s = anomaly.detect("ctr", 0.042, 0.008)
    assert s.severity == "critical" and s.kind == "spike"


def test_positive_improvement_is_good():
    s = anomaly.detect("ecpm", 14.6, 12.4)
    assert s.severity == "good" and s.kind == "improve"


def test_stable_is_none():
    assert anomaly.detect("revenue", 46, 45).severity == "none"


def test_localize_global_vs_localized():
    base = {"US": 45, "UK": 45, "IN": 45}
    scope, hits = anomaly.localize("revenue", {"US": 10, "UK": 10, "IN": 10}, base)
    assert scope == "global"
    scope, hits = anomaly.localize("revenue", {"US": 45, "UK": 45, "ID": 10},
                                   {"US": 45, "UK": 45, "ID": 45})
    assert scope == "localized" and hits == ["ID"]


# ---------------- deduction / decay ----------------
def test_deduction_pct_and_abnormal():
    snaps = [("2026-07-13", 100.0), ("2026-07-19", 80.0), ("2026-07-15", 88.0)]
    assert deduction.deduction_pct(snaps) == 0.2         # 100 -> 80
    assert deduction.decay_series(snaps) == [100.0, 88.0, 80.0]
    assert deduction.is_abnormal(snaps)                  # 20% > 5% band


def test_ivt_risk_localized_deduction():
    assert deduction.ivt_risk({"ID": 0.18, "US": 0.02, "UK": 0.03, "IN": 0.02})
    assert not deduction.ivt_risk({"ID": 0.02, "US": 0.02, "UK": 0.03})


# ---------------- trend / movers / verdict ----------------
def test_slope():
    assert math.isclose(trend.slope([1, 2, 3, 4, 5]), 1.0)


def test_verdicts():
    assert trend.verdict([100, 95, 90, 85, 80, 75, 70, 65, 60, 55]) == "declining"
    assert trend.verdict([50, 52, 54, 56, 58, 60, 62, 64, 66, 68]) == "strong"


def test_split_movers_ranking():
    inc, dec, steady = trend.split_movers([
        {"name": "A", "change_pct": 0.14},
        {"name": "B", "change_pct": -0.22},
        {"name": "C", "change_pct": 0.01},
        {"name": "D", "change_pct": 0.09},
    ])
    assert [p["name"] for p in inc] == ["A", "D"]     # biggest gain first
    assert [p["name"] for p in dec] == ["B"]          # worst first
    assert [p["name"] for p in steady] == ["C"]


# ---------------- health score ----------------
def test_health_strong_vs_risk():
    strong = health.health_score(revenue_slope_norm=0.008, match_rate=0.92,
                                 ecpm=8, peer_ecpm=6, show_rate=0.96, has_ivt_flag=False)
    risk = health.health_score(revenue_slope_norm=-0.008, match_rate=0.61,
                               ecpm=0.22, peer_ecpm=2, show_rate=0.80, has_ivt_flag=True)
    assert strong >= 85 and health.band(strong) == "good"
    assert risk <= 40 and health.band(risk) == "risk"


# ---------------- recommendations ----------------
def test_recommend_banner_to_native():
    recs = recommend.recommend({"format": "banner", "screen_type": "feed", "tier": 1,
                                "match_rate": 0.92, "ecpm": 1.9, "native_ecpm": 5.8,
                                "has_bidding": True})
    actions = " ".join(r["action"] for r in recs)
    assert "Native" in actions and "floor" in actions.lower()


def test_recommend_enable_bidding():
    recs = recommend.recommend({"format": "interstitial", "has_bidding": False,
                                "match_rate": 0.8})
    assert any("bidding" in r["action"].lower() for r in recs)


def test_uplift_estimate():
    up = recommend.estimate_uplift(ecpm_old=1.9, ecpm_new=5.8, impr_per_dau_old=3,
                                   impr_per_dau_new=3, dau=5000)
    # (5.8-1.9)/1000 * 3 * 5000 * 30 days = 1755.0
    assert math.isclose(up, 1755.0)
