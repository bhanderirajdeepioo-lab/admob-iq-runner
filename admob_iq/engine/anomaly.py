"""Metric anomaly detection: zero-value, sharp-drop, positive-improvement, CTR spike.

Works on ONE metric at a time: current value vs its baseline. Also supports
country-level localization (is a drop global or in one geo?).
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

# Ratio metrics live in [0,1] and use point-drops; others use percent-drops.
RATIO_METRICS = {"match_rate", "show_rate", "ctr"}


@dataclass
class Signal:
    metric: str
    severity: str      # critical | warning | watch | good | none
    kind: str          # zero | spike | drop | improve | none
    current: float
    baseline: float
    change_pct: float  # signed; negative = drop
    message: str = ""

    @property
    def is_alert(self) -> bool:
        return self.severity in ("critical", "warning", "watch", "good")


def pct_change(current: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0 if current == 0 else 1.0   # 0 -> positive = treat as +100%
    return (current - baseline) / baseline


def detect(metric: str, current: float, baseline: float, *,
           drop_pct: float = 0.40, drop_pt: float = 0.20,
           spike_x: float = 3.0, improve_pct: float = 0.15,
           zero_floor: float = 0.0) -> Signal:
    """Priority: zero > ctr-spike > drop > improve > none."""
    is_ratio = metric in RATIO_METRICS
    chg = pct_change(current, baseline)

    # 1) zero-value (baseline materially > 0)
    if baseline > 0 and current <= zero_floor:
        return Signal(metric, "critical", "zero", current, baseline, chg,
                      f"{metric} = 0 (baseline {baseline:g})")

    # 2) CTR spike -> invalid-traffic risk
    if metric == "ctr" and baseline > 0 and current >= spike_x * baseline:
        return Signal(metric, "critical", "spike", current, baseline, chg,
                      f"CTR spike {current:.2%} vs {baseline:.2%} (IVT risk)")

    # 3) sharp drop
    if is_ratio:
        if (baseline - current) >= drop_pt:
            return Signal(metric, "warning", "drop", current, baseline, chg,
                          f"{metric} down {(baseline - current) * 100:.0f}pt")
    else:
        if chg <= -drop_pct:
            return Signal(metric, "warning", "drop", current, baseline, chg,
                          f"{metric} down {abs(chg) * 100:.0f}%")

    # 4) positive improvement (good news)
    if chg >= improve_pct:
        return Signal(metric, "good", "improve", current, baseline, chg,
                      f"{metric} up {chg * 100:.0f}%")

    return Signal(metric, "none", "none", current, baseline, chg, "")


def localize(metric: str,
             current_by_country: Dict[str, float],
             baseline_by_country: Dict[str, float],
             **kw) -> Tuple[str, List[str]]:
    """Decide if a problem is global or localized to a few geos.

    Returns (scope, countries) where scope is 'global' | 'localized' | 'none'.
    """
    hits: List[str] = []
    for c, cur in current_by_country.items():
        base = baseline_by_country.get(c, 0.0)
        sig = detect(metric, cur, base, **kw)
        if sig.severity in ("critical", "warning"):
            hits.append(c)
    if not hits:
        return ("none", [])
    total = len(current_by_country) or 1
    if len(hits) >= max(1, round(total * 0.6)):
        return ("global", hits)
    return ("localized", hits)
