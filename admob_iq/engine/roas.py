"""ROAS join: line Google Ads marketing spend up against AdMob revenue, per app.

Spend comes from fetch_app_spend keyed by STORE id (Play package / App Store numeric). AdMob apps
carry the same store id (accounts.apps.list). We map store_id → app_name and ship per-app DAILY
spend (in USD) + the campaign list, so the frontend can window spend to the selected period and
compute ROAS = revenue ÷ spend against the revenue it already has per app. Spend on a store id we
can't match to an AdMob app (or store id we couldn't resolve) is surfaced as 'unmatched' rather
than silently dropped.
"""


def build_roas(spend, app_store_ids, apps_catalog, aliases=None):
    """spend: fetch_app_spend output (or None). app_store_ids: {app_id: store_id}.
    apps_catalog: [{app_id, app_name, rev, ...}]. aliases: {google_ads_store_id: admob_app_name}
    manual overrides for apps whose AdMob store listing isn't linked (blank store id) so they'd
    otherwise land in 'unmatched'. Returns the roas.json payload."""
    if spend is None:                                    # Google Ads not configured (secrets missing)
        return {"configured": False, "by_app": {}, "currency_src": "USD", "fx": {},
                "unmatched_spend_usd": 0}
    if spend.get("error"):                               # configured but the call failed — surface WHY
        return {"configured": False, "error": spend["error"], "by_app": {}, "currency_src": "USD",
                "fx": {}, "unmatched_spend_usd": 0}
    # store_id -> app_name; on a duplicate store id keep the highest-revenue app's name
    by_store_app = {}
    for c in sorted(apps_catalog or [], key=lambda x: -(x.get("rev") or 0)):
        sid = app_store_ids.get(c.get("app_id"))
        if sid and sid not in by_store_app:
            by_store_app[sid] = c.get("app_name") or c.get("app_id")
    # manual aliases: map a Google Ads store id straight to an AdMob app NAME. Needed when an AdMob
    # app has no linked store listing (blank store id) so it can't auto-match — its spend would be
    # 'unmatched'. Overrides the auto map so these campaigns attribute to the right app.
    rev_by_name = {}
    for c in (apps_catalog or []):
        nm = c.get("app_name") or c.get("app_id")
        if nm:
            rev_by_name[nm] = rev_by_name.get(nm, 0) + (c.get("rev") or 0)
    for ga_sid, app_name in (aliases or {}).items():
        if not (ga_sid and app_name):
            continue
        target = app_name
        if target not in rev_by_name:
            # duplicate app names get a disambiguating suffix ("Name · pub-1234…") — so an alias
            # written against the plain name still resolves; pick the highest-revenue match.
            cand = [n for n in rev_by_name if n.startswith(app_name + " ")]
            if cand:
                target = max(cand, key=lambda n: rev_by_name.get(n, 0))
        by_store_app[str(ga_sid).strip()] = target
    camps_by_sid = spend.get("campaigns") or {}
    by_app, unmatched = {}, 0
    unmatched_detail = {}                                # store_id -> {spend, campaigns} we couldn't attribute
    for sid, dd in (spend.get("daily") or {}).items():
        app = by_store_app.get(sid)
        if not app:
            s = sum(dd.values())
            unmatched += s                              # spend we can't attribute to an AdMob app
            names = [c.get("name") for c in camps_by_sid.get(sid, []) if c.get("name")]
            unmatched_detail[sid] = {"store_id": sid, "spend_usd_micros": s,
                                     "n_campaigns": len(camps_by_sid.get(sid, [])), "sample": names[:3]}
            continue
        e = by_app.setdefault(app, {"store_id": sid, "daily": {}, "campaigns": []})
        for d, v in dd.items():
            e["daily"][d] = e["daily"].get(d, 0) + v
        e["campaigns"].extend(camps_by_sid.get(sid, []))
    # surface the biggest unmatched store ids so coverage gaps are visible + diagnosable (not a black-box sum)
    top_unmatched = sorted(unmatched_detail.values(), key=lambda x: -x["spend_usd_micros"])[:30]
    return {"configured": True, "by_app": by_app, "note": spend.get("note"),
            "currency_src": spend.get("currency_src", "USD"), "fx": spend.get("fx", {}),
            "unmatched_spend_usd": unmatched, "unmatched_apps": top_unmatched,
            "unmatched_count": len(unmatched_detail)}
