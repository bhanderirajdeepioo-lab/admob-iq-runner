"""Seasonality-safe baselines for anomaly detection.

A metric's baseline is what we compare "today" against. Two strategies:
  * rolling_median  — median of the last N prior days (robust to spikes)
  * weekday_baseline — median of the same weekday over the last few weeks
                       (cancels weekly seasonality, e.g. weekend dips)
All functions take PRIOR values (today excluded), most-recent-last.
"""

from statistics import median
from typing import List


def rolling_median(prior_values: List[float], window: int = 7) -> float:
    if not prior_values:
        return 0.0
    return float(median(prior_values[-window:]))


def weekday_baseline(prior_values: List[float], weeks: int = 4) -> float:
    """Median of same-weekday values: 7, 14, 21, 28 days back."""
    picks = [prior_values[-7 * k] for k in range(1, weeks + 1)
             if len(prior_values) >= 7 * k]
    if not picks:
        return rolling_median(prior_values)
    return float(median(picks))


def baseline(prior_values: List[float], window: int = 7,
             use_weekday: bool = False) -> float:
    """Primary entry point. Default = 7-day rolling median."""
    if use_weekday:
        return weekday_baseline(prior_values)
    return rolling_median(prior_values, window)
