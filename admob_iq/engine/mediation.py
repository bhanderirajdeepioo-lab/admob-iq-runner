"""Mediation advisor (blueprint deliverable #9).

Turns per-network mediation facts into a summary + concrete suggestions
(add bidding, review a stale/low-fill waterfall network)."""

from typing import Dict, List


def summarize(rows: List[Dict]) -> Dict:
    """rows: [{ad_source, type('bidding'|'waterfall'|'both'), fill, ecpm, revenue,
    latency_s}]. Returns headline stats used by the Mediation screen."""
    if not rows:
        return {"networks": 0, "bidding_share": 0.0, "blended_fill": 0.0, "best_ecpm": None}
    total_rev = sum(r.get("revenue", 0) for r in rows) or 1.0
    bidding_rev = sum(r.get("revenue", 0) for r in rows if "bidding" in r.get("type", ""))
    best = max(rows, key=lambda r: r.get("ecpm", 0))
    fill_num = sum(r.get("fill", 0) * r.get("revenue", 0) for r in rows)
    return {
        "networks": len(rows),
        "bidding_share": bidding_rev / total_rev,
        "blended_fill": fill_num / total_rev,
        "best_ecpm": {"ad_source": best["ad_source"], "ecpm": best.get("ecpm", 0)},
        "shares": {r["ad_source"]: r.get("revenue", 0) / total_rev for r in rows},
    }


def suggest(rows: List[Dict], *, stale_fill=0.65, min_bidding_share=0.60,
            latency_watch_s=1.2) -> List[Dict]:
    recs: List[Dict] = []
    total_rev = sum(r.get("revenue", 0) for r in rows) or 1.0
    bidding_rev = sum(r.get("revenue", 0) for r in rows if "bidding" in r.get("type", ""))
    # AdMob's report doesn't label bidding vs waterfall; only advise on it when the type
    # is actually known (demo / explicitly-typed rows), never guess from unlabeled data.
    types_known = any((r.get("type") or "") in ("bidding", "waterfall", "both") for r in rows)

    if types_known and bidding_rev / total_rev < min_bidding_share:
        recs.append({"action": "Add bidding networks",
                     "reason": f"bidding share {bidding_rev / total_rev:.0%} < "
                               f"{min_bidding_share:.0%} — Google recommends hybrid"})

    for r in rows:
        if r.get("type") == "waterfall" and r.get("fill", 1.0) < stale_fill:
            recs.append({"action": f"Review/replace waterfall '{r['ad_source']}'",
                         "reason": f"fill {r.get('fill', 0):.0%} — stale eCPM / demand"})
        elif (r.get("latency_s") or 0) >= latency_watch_s:
            recs.append({"action": f"Watch latency: {r['ad_source']}",
                         "reason": f"{r.get('latency_s')}s adapter latency drags load"})
    return recs
