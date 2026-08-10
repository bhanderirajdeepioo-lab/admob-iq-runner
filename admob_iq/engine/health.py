"""Placement health score (0-100), a weighted blend the dashboard color-codes."""


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def health_score(*, revenue_slope_norm: float, match_rate: float,
                 ecpm: float, peer_ecpm: float, show_rate: float,
                 has_ivt_flag: bool) -> int:
    """
    Weights (per blueprint Module D):
      revenue trend 30% · fill 20% · eCPM vs peer 20% · show rate 15% · anomaly/IVT 15%
    revenue_slope_norm: slope/level per day (+rising, -falling), ~[-0.01, +0.01]
    match_rate, show_rate: fractions [0,1]; ecpm vs peer_ecpm same format/geo.
    """
    trend = _clamp((revenue_slope_norm + 0.01) / 0.02)          # -0.01..+0.01 -> 0..1
    fill = _clamp((match_rate - 0.55) / (0.90 - 0.55))           # 0.55..0.90 -> 0..1
    ratio = (ecpm / peer_ecpm) if peer_ecpm else 1.0
    ecpm_score = _clamp(ratio / 1.2)                             # >=1.2x peer -> full
    show = _clamp((show_rate - 0.70) / (0.98 - 0.70))
    anomaly = 0.0 if has_ivt_flag else 1.0
    score = 0.30 * trend + 0.20 * fill + 0.20 * ecpm_score + 0.15 * show + 0.15 * anomaly
    return round(score * 100)


def band(score: int) -> str:
    return "good" if score >= 75 else ("watch" if score >= 50 else "risk")
