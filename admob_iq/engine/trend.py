"""Trend slope, movers (increasing vs decreasing), and historical verdict."""

from statistics import mean, pstdev
from typing import Dict, List, Tuple


def slope(values: List[float]) -> float:
    """Least-squares slope of y over x = 0..n-1."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = mean(xs), mean(values)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, values))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den if den else 0.0


def pct_change_window(values: List[float], window: int) -> float:
    if len(values) <= window or values[-window - 1] == 0:
        return 0.0
    old, new = values[-window - 1], values[-1]
    return (new - old) / old


def cv(values: List[float]) -> float:
    """Coefficient of variation (volatility)."""
    if not values:
        return 0.0
    m = mean(values)
    return (pstdev(values) / m) if m else 0.0


def verdict(values: List[float]) -> str:
    """Historical report-card verdict: strong/recovering/declining/volatile/steady/new."""
    if len(values) < 3:
        return "new"
    level = mean(values) or 1.0
    norm_slope = slope(values) / level
    recent = pct_change_window(values, min(7, len(values) - 1))
    vol = cv(values)
    if norm_slope > 0.002 and recent >= 0:
        return "strong" if vol < 0.35 else "recovering"
    if norm_slope < -0.002:
        return "declining"
    if vol >= 0.35:
        return "volatile"
    if recent > 0.02:
        return "recovering"
    return "steady"


def split_movers(placements: List[Dict], key: str = "change_pct",
                 threshold: float = 0.02
                 ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Split placements into (increasing, decreasing, steady), each ranked by magnitude."""
    inc = sorted((p for p in placements if p[key] >= threshold),
                 key=lambda p: p[key], reverse=True)
    dec = sorted((p for p in placements if p[key] <= -threshold),
                 key=lambda p: p[key])            # most negative first
    steady = [p for p in placements if -threshold < p[key] < threshold]
    return inc, dec, steady
