"""Account-health / policy-compliance aggregator (blueprint Policy Guard).

Rolls the available signals into a traffic-light status. IVT/serving signals come
from the fetcher (CTR spikes, deductions, AdMob status); consent / app-ads.txt /
TCF come from per-app metadata."""

from typing import Dict, List, Tuple


def account_health(*, ivt_flags: int = 0, serving_limited: bool = False,
                   consent_gaps: int = 0, app_ads_txt_ok: bool = True,
                   tcf_current: bool = True) -> Dict:
    issues: List[Tuple[str, str]] = []
    if serving_limited:
        issues.append(("critical", "Ad serving limited — check Policy Center"))
    if not app_ads_txt_ok:
        issues.append(("critical", "app-ads.txt not verified — limited serving risk"))
    if ivt_flags > 0:
        issues.append(("warning", f"{ivt_flags} placement(s) with invalid-traffic risk"))
    if consent_gaps > 0:
        issues.append(("warning", f"{consent_gaps} app(s) missing/insufficient consent (EEA/UK)"))
    if not tcf_current:
        issues.append(("watch", "TCF version behind — v2.3 deadline"))

    if any(sev == "critical" for sev, _ in issues):
        status = "red"
    elif issues:
        status = "amber"
    else:
        status = "green"
    return {"status": status, "issues": issues}
