"""Root-cause classifier (blueprint Module C).

Given how a placement's funnel metrics moved, assign ONE dominant cause bucket
so the dashboard can say *why* — not just *what* — dropped. Inputs are signed
fractional changes vs baseline (e.g. -0.15 = down 15%); pass None if unknown.
"""

CAUSES = ["ivt", "technical", "signal_loss", "floor_misconfig",
          "ux_frequency", "seasonality", "demand_drop", "unknown"]


def classify(*, ecpm_change=None, match_change=None, show_change=None,
             ctr_change=None, impr_per_dau_change=None,
             ios_only=False, yoy_down=False, deduction_high=False):
    """Return (cause, explanation). Priority mirrors the blueprint funnel logic."""
    # Invalid traffic: CTR spiking or a big localized deduction.
    if (ctr_change is not None and ctr_change > 0.5) or deduction_high:
        return ("ivt", "CTR spike / localized deduction — invalid-traffic risk")

    # Technical: ads returned but not shown.
    if show_change is not None and show_change < -0.15:
        return ("technical", "show rate down — render/pre-load timing (engineering)")

    # Fill/eligibility: matched requests dropped.
    if match_change is not None and match_change < -0.15:
        return ("floor_misconfig", "fill down — floor too high or eligibility change")

    # UX/frequency: fewer impressions per user.
    if impr_per_dau_change is not None and impr_per_dau_change < -0.15:
        return ("ux_frequency", "impressions/DAU down — frequency cap or sessions")

    # Pricing/demand vs seasonality vs signal-loss (eCPM soft, fill ~flat).
    if ecpm_change is not None and ecpm_change < -0.10:
        if ios_only:
            return ("signal_loss", "iOS-only eCPM drop — ATT/consent signal loss")
        if not yoy_down:
            return ("seasonality", "eCPM soft, YoY not down — seasonal/demand cycle")
        return ("demand_drop", "eCPM down structurally (YoY too) — demand/pricing")

    return ("unknown", "no dominant funnel signal")
