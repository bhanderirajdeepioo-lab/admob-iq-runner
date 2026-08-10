"""Approval layer for baseline ranges — PER METRIC.

Each metric (ctr / match / show / ecpm) of a placement is approved INDIVIDUALLY: the user can
lock CTR while leaving Match pending, raise eCPM without touching Show, etc. Approving a
placement-metric also auto-snapshots that SAME metric across the placement's countries (each
country metric stays individually editable). A manual country-metric edit re-pends that ONE
metric on the placement so it's re-confirmed (handled in the UI; the engine just reflects state).

Movement (▲/▼) for an APPROVED metric is judged vs its approved range; while a metric is still
pending it's judged vs the data's own suggested range. Every month the freshly-suggested range is
compared (per metric) to the approved one so the user can approve an update:
  * suggested HIGHER than approved -> 'up'   (offer to raise the locked range)
  * suggested LOWER  than approved -> 'down' (offer, but if not approved the old range stays)

Stored in config/approved_ranges.json (git-committed) so it persists server-side across devices
and the robot applies the SAME approved ranges everywhere.

Shape (per-metric):
  {"placements": {
     "<ad_unit_id>": {
        "metrics": {
           "ctr":  {"range":[lo,hi], "approved_at":"2026-07"},
           "match":{...}, "show":{...}, "ecpm":{...}     # ONLY approved metrics appear
        },
        "countries": {
           "US": {"metrics": {"ctr":{"range":[lo,hi],"approved_at":"2026-07"}, ...}}
        }
     }, ...}}

The OLD flat shape ({"approved_at","range":{k:[lo,hi]},"countries":{"US":{k:[lo,hi]}}}) is
auto-upgraded on read, so anything already saved keeps working.
"""

import json
import os

from .baseline_report import _status

_METS = ("ctr", "match", "show", "ecpm")
_REL = 0.05          # a suggested range whose midpoint moved <5% vs approved counts as 'same'


def load_approved(path):
    """Read approved_ranges.json (or an empty set if absent/broken — never crash the build)."""
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("placements", {})
            return data
        except Exception:
            pass
    return {"placements": {}}


def _direction(suggested, approved):
    """'up' / 'down' / 'same' — where the suggested range sits vs approved (by midpoint)."""
    if not suggested or not approved or suggested[0] is None or approved[0] is None:
        return "same"
    sm, am = (suggested[0] + suggested[1]) / 2, (approved[0] + approved[1]) / 2
    if am == 0:
        return "up" if sm > 0 else "same"
    d = (sm - am) / abs(am)
    return "up" if d > _REL else "down" if d < -_REL else "same"


# ---- normalise a stored placement (new OR old flat shape) into the per-metric form ----

def _norm_entry(v):
    """One metric's stored value → {'range':[lo,hi], 'approved_at':...} or None."""
    if v is None:
        return None
    if isinstance(v, dict):
        rng = v.get("range")
        return {"range": rng, "approved_at": v.get("approved_at")} if rng else None
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return {"range": list(v), "approved_at": None}
    return None


def _norm_metrics(d):
    out = {}
    for k in _METS:
        e = _norm_entry((d or {}).get(k))
        if e:
            out[k] = e
    return out


def _norm_place(p):
    """Upgrade a stored placement to {'metrics':{k:{range,approved_at}}, 'countries':{c:{'metrics':…}}}.
    Handles the new per-metric shape and the old flat shape independently for the placement and for
    each country (so a half-migrated file still reads cleanly)."""
    p = p or {}
    at = p.get("approved_at")
    if "metrics" in p:
        metrics = _norm_metrics(p.get("metrics"))
    else:                                             # old flat: {"range":{k:[lo,hi]}}
        metrics = {}
        for k in _METS:
            rng = (p.get("range") or {}).get(k)
            if rng:
                metrics[k] = {"range": rng, "approved_at": at}
    countries = {}
    for c, cv in (p.get("countries") or {}).items():
        if isinstance(cv, dict) and "metrics" in cv:
            cm = _norm_metrics(cv.get("metrics"))
        else:                                         # old flat country: {k:[lo,hi]}
            cm = {}
            for k in _METS:
                rng = (cv or {}).get(k)
                if rng:
                    cm[k] = {"range": rng, "approved_at": at}
        countries[c] = {"metrics": cm}
    return {"metrics": metrics, "countries": countries}


def _apply_metric(row, k, entry, last_complete=""):
    """Layer ONE metric's approval state onto a unit/country row (which already carries suggested
    `range`, `latest`, `status` from build_baseline). Returns that metric's status label.
    An 'update' is flagged ONLY once a NEWER complete month has closed since approval — so an
    approval never turns into 'update' the same month (no intra-month nag; monthly review only)."""
    suggested = (row.get("range") or {}).get(k)
    latest = (row.get("latest") or {}).get(k)
    row.setdefault("approved", {})
    row.setdefault("status", {})
    row.setdefault("appr_dir", {})
    if entry and entry.get("range"):
        arange = entry["range"]
        row["approved"][k] = arange
        row["status"][k] = _status(latest, arange)      # movement now judged vs APPROVED range
        at = entry.get("approved_at") or ""
        new_month = bool(last_complete and at and last_complete > at)
        d = _direction(suggested, arange) if new_month else "same"
        row["appr_dir"][k] = d
        return "update" if d != "same" else "approved"
    # pending: keep the suggested-range movement build_baseline already computed
    row["status"].setdefault(k, _status(latest, suggested))
    row["appr_dir"][k] = "same"
    return "pending"


def _rollup(by_metric):
    """One badge per placement from its 4 per-metric states."""
    pend = sum(1 for v in by_metric.values() if v == "pending")
    upd = sum(1 for v in by_metric.values() if v == "update")
    if pend == len(_METS):
        return "pending"
    if upd:
        return "update"
    if pend:
        return "partial"        # some approved, some still pending
    return "approved"


def _apply_row(row, metrics_appr, last_complete=""):
    """Apply all four metrics to a row and stamp its rollup fields."""
    row["approved"] = {}
    by = {k: _apply_metric(row, k, (metrics_appr or {}).get(k), last_complete) for k in _METS}
    row["appr_by_metric"] = by
    row["appr_status"] = _rollup(by)
    return by


_MET_LABEL = {"ctr": "CTR", "match": "Match rate", "show": "Show rate", "ecpm": "eCPM"}


def _fmt_val(k, v):
    if v is None:
        return "—"
    return f"${v:.2f}" if k == "ecpm" else f"{v * 100:.1f}%"


def range_alerts(payload, max_items=60):
    """Out-of-range alerts: placements whose latest month sits OUTSIDE an APPROVED range.
    Only APPROVED metrics count — a pending metric has no locked standard to breach. eCPM dropping
    below its locked range is real revenue risk (warning); everything else is a watch. Sorted by
    warning-first then revenue. Shipped as a SEPARATE list (dashboard.range_alerts) so it never
    disturbs the existing alerts pipeline."""
    items = []
    for u in payload.get("units", []):
        appr = u.get("approved") or {}
        st = u.get("status") or {}
        latest = u.get("latest") or {}
        for k in _METS:
            rng = appr.get(k)
            if not rng or st.get(k) not in ("above", "below"):
                continue
            direction = st[k]
            sev = "warning" if (k == "ecpm" and direction == "below") else "watch"
            lo, hi = rng
            items.append({
                "id": u["id"], "place": u.get("name"), "app": u.get("app"),
                "metric": k, "dir": direction, "severity": sev, "rev": u.get("rev_total", 0),
                "now": latest.get(k), "range": [lo, hi],
                "message": (f"{_MET_LABEL[k]} {_fmt_val(k, latest.get(k))} — approved range "
                            f"{_fmt_val(k, lo)}–{_fmt_val(k, hi)} se "
                            f"{'upar' if direction == 'above' else 'neeche'}"),
            })
    items.sort(key=lambda a: (0 if a["severity"] == "warning" else 1, -(a.get("rev") or 0)))
    return items[:max_items]


def apply_approvals(payload, approved):
    """Layer per-metric approval status onto the whole baseline payload (units + per-ad-unit
    countries). Adds `approval_counts` (placements by rollup) and `approval_metric_counts`
    (individual metric states) for the header."""
    apl = {uid: _norm_place(p) for uid, p in (approved or {}).get("placements", {}).items()}
    last_complete = (payload.get("data_range") or {}).get("last", "")   # newest complete month
    counts = {"approved": 0, "pending": 0, "update": 0, "partial": 0}
    mcounts = {"approved": 0, "pending": 0, "update": 0}
    for u in payload.get("units", []):
        by = _apply_row(u, (apl.get(u["id"]) or {}).get("metrics", {}), last_complete)
        counts[u["appr_status"]] = counts.get(u["appr_status"], 0) + 1
        for st in by.values():
            mcounts[st] = mcounts.get(st, 0) + 1
    for uid, rows in payload.get("unit_geo", {}).items():
        appc = (apl.get(uid) or {}).get("countries", {})
        for c in rows:
            _apply_row(c, (appc.get(c["country"]) or {}).get("metrics", {}), last_complete)
    payload["approval_counts"] = counts
    payload["approval_metric_counts"] = mcounts
    return payload
