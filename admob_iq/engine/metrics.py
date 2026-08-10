"""Derived AdMob metrics.

Money is in MICROS (value / 1e6 = currency). Ratios are fractions in [0, 1].

Important semantics (verified against the AdMob API, see COVERAGE.md):
  * There is NO `eCPM` field in the API — compute it (earnings/impr*1000).
    The network report exposes IMPRESSION_RPM which equals this.
  * There is NO `GDPR` dimension — SERVING_RESTRICTION is the closest.
"""

MICROS = 1_000_000


def sdiv(a: float, b: float) -> float:
    """Safe division: 0 when denominator is 0 (avoids blowups on empty days)."""
    return a / b if b else 0.0


def micros_to_currency(micros: float) -> float:
    return micros / MICROS


def match_rate(ad_requests: int, matched_requests: int) -> float:
    """Fill = matched / requests."""
    return sdiv(matched_requests, ad_requests)


def show_rate(matched_requests: int, impressions: int) -> float:
    """Displayed / returned (network report only)."""
    return sdiv(impressions, matched_requests)


def ctr(impressions: int, clicks: int) -> float:
    return sdiv(clicks, impressions)


def ecpm(estimated_earnings_micros: int, impressions: int) -> float:
    """AdMob-side eCPM in currency units (earnings per 1000 impressions)."""
    earnings = micros_to_currency(estimated_earnings_micros)
    return sdiv(earnings, impressions) * 1000.0


# IMPRESSION_RPM (network report) is the same quantity as our computed eCPM.
rpm = ecpm


def arpdau(ecpm_value: float, impressions_per_dau: float) -> float:
    """North-star: ARPDAU = ad revenue / DAU = eCPM/1000 * impressions_per_DAU.

    eCPM already encodes revenue-per-impression, so we do NOT multiply by fill
    again here (that would double-count). Use this when you have actual
    impressions/DAU."""
    return (ecpm_value / 1000.0) * impressions_per_dau


def arpdau_from_requests(ecpm_value: float, match_rate_value: float,
                         show_rate_value: float, requests_per_dau: float) -> float:
    """Full-funnel form when you only have requests/DAU:
    impressions = requests * match_rate * show_rate."""
    impressions_per_dau = requests_per_dau * match_rate_value * show_rate_value
    return arpdau(ecpm_value, impressions_per_dau)
