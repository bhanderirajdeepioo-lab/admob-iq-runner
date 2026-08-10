"""Revenue-deduction / estimate-decay from the append-only snapshots table.

AdMob's estimated earnings for a day get revised DOWN over time (invalid-traffic
removal, corrections) until finalized. We snapshot each pull so we can see the
decay: D+1=$100 -> D+3=$88 -> finalized $80, and flag placements/geos that lose
abnormally much (an early IVT signal).
"""

from typing import Dict, List, Tuple

Snapshot = Tuple[str, float]  # (snapshot_date_iso, earnings_currency)


def decay_series(snapshots: List[Snapshot]) -> List[float]:
    """Earnings ordered by snapshot date (the decay curve)."""
    return [e for _, e in sorted(snapshots)]


def deduction_pct(snapshots: List[Snapshot]) -> float:
    """(first_estimate - latest_estimate) / first_estimate. Positive = lost."""
    series = decay_series(snapshots)
    if not series or series[0] == 0:
        return 0.0
    first, latest = series[0], series[-1]
    return (first - latest) / first


def is_abnormal(snapshots: List[Snapshot], normal_max: float = 0.05) -> bool:
    """True if deduction exceeds the normal band (default 5%)."""
    return deduction_pct(snapshots) > normal_max


def ivt_risk(deduction_by_country: Dict[str, float],
             localized_min: float = 0.15,
             localized_frac: float = 0.4) -> bool:
    """Large deduction concentrated in a few geos => invalid-traffic early warning."""
    if not deduction_by_country:
        return False
    big = [c for c, d in deduction_by_country.items() if d >= localized_min]
    if not big:
        return False
    return len(big) <= max(1, round(len(deduction_by_country) * localized_frac))
