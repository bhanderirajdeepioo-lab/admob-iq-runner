"""Alert-rule evaluation: ties baseline + anomaly together and dedupes.

An alert fires when a metric's latest value breaches a rule vs its baseline.
Positive improvements are alerts too (severity 'good')."""

from ..engine import baseline, anomaly

# Configurable defaults (mirrors the Alerts screen "Alert rules" panel).
DEFAULT_RULES = [
    {"rule_id": "zero_any",   "metric": "*",          "kind": "zero",       "severity": "critical", "enabled": True},
    {"rule_id": "rev_drop",   "metric": "revenue",    "kind": "drop_pct",   "threshold": 0.40, "severity": "warning", "enabled": True},
    {"rule_id": "req_drop",   "metric": "requests",   "kind": "drop_pct",   "threshold": 0.50, "severity": "warning", "enabled": True},
    {"rule_id": "match_drop", "metric": "match_rate", "kind": "drop_pt",    "threshold": 0.20, "severity": "warning", "enabled": True},
    {"rule_id": "ctr_spike",  "metric": "ctr",        "kind": "spike_x",    "threshold": 3.0,  "severity": "critical", "enabled": True},
    {"rule_id": "show_drop",  "metric": "show_rate",  "kind": "drop_pt",    "threshold": 0.15, "severity": "watch",   "enabled": True},
    {"rule_id": "improve",    "metric": "*",          "kind": "improve_pct", "threshold": 0.15, "severity": "good",    "enabled": True},
]


_INF = 1e9


def _threshold(metric, kind, rules, default):
    """Resolve a threshold for this metric+kind from the rules table.
    An exact-metric rule beats a '*' rule. A matching-but-disabled rule returns
    None (caller suppresses that check). No rule -> default."""
    exact = wildcard = None
    for r in rules:
        if r["kind"] != kind:
            continue
        if r["metric"] == metric:
            exact = r
        elif r["metric"] == "*":
            wildcard = r
    r = exact or wildcard
    if r is None:
        return default
    if not r.get("enabled", True):
        return None
    return r.get("threshold", default)


def evaluate(metric: str, current: float, prior_values,
             rules=DEFAULT_RULES, use_weekday=False):
    """Baseline from prior daily values, then classify today's value using the
    per-metric thresholds from `rules` (honors enabled flag + per-metric overrides,
    e.g. requests drop 50% vs revenue drop 40%)."""
    base = baseline.baseline(prior_values, use_weekday=use_weekday)
    dp = _threshold(metric, "drop_pct", rules, 0.40)
    pt = _threshold(metric, "drop_pt", rules, 0.20)
    sx = _threshold(metric, "spike_x", rules, 3.0)
    im = _threshold(metric, "improve_pct", rules, 0.15)
    return anomaly.detect(
        metric, current, base,
        drop_pct=_INF if dp is None else dp,
        drop_pt=_INF if pt is None else pt,
        spike_x=_INF if sx is None else sx,
        improve_pct=_INF if im is None else im,
    )


def fingerprint(ad_unit_id: str, metric: str, country, kind: str, day) -> str:
    """Stable key so the same issue isn't alerted twice in a day."""
    return f"{ad_unit_id}|{metric}|{country or 'ALL'}|{kind}|{day}"


def dedupe(items, seen: set):
    """items: iterable of (fingerprint, signal). Drops ones already in `seen`."""
    out = []
    for fp, sig in items:
        if fp in seen:
            continue
        seen.add(fp)
        out.append((fp, sig))
    return out
