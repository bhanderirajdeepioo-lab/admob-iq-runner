"""Rule-based recommendations + revenue-uplift what-if estimate."""

from typing import Dict, List


def estimate_uplift(*, ecpm_old: float, ecpm_new: float,
                    impr_per_dau_old: float, impr_per_dau_new: float,
                    dau: float, horizon_days: int = 30) -> float:
    """Delta revenue over the horizon (currency). Guards against isolation bias by
    letting the caller pass changed impressions/DAU (cannibalization)."""
    daily_old = ecpm_old / 1000.0 * impr_per_dau_old * dau
    daily_new = ecpm_new / 1000.0 * impr_per_dau_new * dau
    return (daily_new - daily_old) * horizon_days


def recommend(p: Dict) -> List[Dict]:
    """Return ranked recommendations for a placement dict. Keys used:
    format, screen_type, tier, match_rate, ecpm, native_ecpm, has_bidding,
    is_fixed_banner, interstitial_freq, retention_dip.
    """
    recs: List[Dict] = []

    if (p.get("format") == "banner" and p.get("screen_type") == "feed"
            and p.get("tier", 3) <= 2 and p.get("native_ecpm")
            and p["native_ecpm"] > p.get("ecpm", 0)):
        recs.append({"action": "Banner → Native (A/B)",
                     "reason": "feed screen + native demand; ~2-4x eCPM",
                     "confidence": "high", "ab": True})

    mr = p.get("match_rate", 0.0)
    if mr >= 0.90:
        recs.append({"action": "Raise eCPM floor 10-15%",
                     "reason": f"match rate {mr:.0%} — money on the table",
                     "confidence": "medium", "ab": False})
    elif 0 < mr < 0.70:
        recs.append({"action": "Lower floor / add networks",
                     "reason": f"fill {mr:.0%} — demand leak",
                     "confidence": "high", "ab": False})

    if not p.get("has_bidding", True):
        recs.append({"action": "Enable bidding networks",
                     "reason": "no bidding — +10-30% typical",
                     "confidence": "high", "ab": True})

    if p.get("is_fixed_banner"):
        recs.append({"action": "Fixed → adaptive banner",
                     "reason": "device-width fill; often +50%+ eCPM",
                     "confidence": "high", "ab": True})

    if p.get("retention_dip") and (p.get("interstitial_freq") or 0) > 3:
        recs.append({"action": "Lower interstitial frequency cap",
                     "reason": "over-frequency hurting retention/LTV",
                     "confidence": "medium", "ab": True})

    return recs
