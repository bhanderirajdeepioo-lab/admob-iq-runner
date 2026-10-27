"""ROAS join: line Google Ads marketing spend up against AdMob revenue, per app.

Spend comes from fetch_app_spend keyed by STORE id (Play package / App Store numeric). AdMob apps
carry the same store id (accounts.apps.list). We map store_id → app_name and ship per-app DAILY
spend (in USD) + the campaign list, so the frontend can window spend to the selected period and
compute ROAS = revenue ÷ spend against the revenue it already has per app. Spend on a store id we
can't match to an AdMob app (or store id we couldn't resolve) is surfaced as 'unmatched' rather
than silently dropped. "daily" is USD at ONE rate (today's — every screen's ₹ view reads it, so ₹ is the exact rupee
Google Ads billed, and so do back-end readers); "daily_dated" (INR spend, when the build has a dated rate series) is USD
at each day's OWN rate — every screen's $ view (the Marketing ROAS tab, Overview, the app page, the hub: one helper,
roasDaily, so they never disagree; owner-approved: old days are not re-valued at today's rate).
"""


def store_owner(app_store_ids, apps_catalog, aliases=None):
    """{Google Ads store id: the AdMob app NAME its spend is attributed to} — the ROAS join's one rule (build_roas below;
    the Install value tab joins spend with the SAME map, so both tabs always give an app the same Google Ads spend)."""
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
    for ga_sid, alias in (aliases or {}).items():
        if not (ga_sid and alias):
            continue
        # an alias value may be one name, or (from the build) every name that app is now known by
        # after a rename — pick whichever candidate actually carries revenue.
        cands = [c for c in (alias if isinstance(alias, (list, tuple)) else [alias]) if c]
        hit = [c for c in cands if c in rev_by_name]
        if not hit:
            # duplicate app names get a disambiguating suffix ("Name · pub-1234…") — so an alias
            # written against the plain name still resolves.
            hit = [n for c in cands for n in rev_by_name if n.startswith(c + " ")]
        if not (hit or cands):
            continue
        target = max(hit, key=lambda n: rev_by_name.get(n, 0)) if hit else cands[0]
        by_store_app[str(ga_sid).strip()] = target
    return by_store_app


def build_roas(spend, app_store_ids, apps_catalog, aliases=None, daily_dated=None):
    """spend: fetch_app_spend output (or None). app_store_ids: {app_id: store_id}.
    apps_catalog: [{app_id, app_name, rev, ...}]. aliases: {google_ads_store_id: admob_app_name}
    (or a LIST of candidate names, when the app has been renamed) — manual overrides for apps whose
    AdMob store listing isn't linked (blank store id) so they'd otherwise land in 'unmatched'.
    daily_dated: {store_id: {date: USD micros at THAT day's own rate}} (build_static._spend_daily_dated) or None —
    when given, every app / unmatched app also carries "daily_dated" (the same join and sums as "daily") and the
    payload says spend_fx = "dated": every screen's $ view reads it; "daily" (one rate: today's) is unchanged and stays
    what the ₹ view and every back-end reader read. None = no key at all (the payload exactly as before).
    Returns the roas.json payload."""
    if spend is None:                                    # Google Ads not configured (secrets missing)
        return {"configured": False, "by_app": {}, "currency_src": "USD", "fx": {},
                "unmatched_spend_usd": 0}
    if spend.get("error"):                               # configured but the call failed — surface WHY
        return {"configured": False, "error": spend["error"], "by_app": {}, "currency_src": "USD",
                "fx": {}, "unmatched_spend_usd": 0}
    by_store_app = store_owner(app_store_ids, apps_catalog, aliases)
    camps_by_sid = spend.get("campaigns") or {}
    installs_by_sid = spend.get("installs") or {}        # store_id -> {date: campaign-attributed installs}
    convval_by_sid = spend.get("convval") or {}          # store_id -> {date: Google Ads conversion value (USD)}
    convval_d1_by_sid = spend.get("convval_day1") or {}  # store_id -> {date: D0 conversion value (USD), fixed once complete}
    convval_dd_by_sid = spend.get("convval_d0day") or {}  # store_id -> {date: install-day ("Day") D0 (USD), taken once}
    d0_open = spend.get("d1_open") or {}                 # store_id -> {"days": D0 dates ≤ d1_fixed_till not fixed yet, "wait"}
    day_at = spend.get("d1_day_at") or {}                # store_id -> {"date", "at"}: its next install-day moment
    by_app, unmatched, sids_of = {}, 0, {}
    unmatched_detail = {}                                # store_id -> {spend, campaigns} we couldn't attribute
    for sid, dd in (spend.get("daily") or {}).items():
        app = by_store_app.get(sid)
        if not app:
            s = sum(dd.values())
            unmatched += s                              # spend we can't attribute to an AdMob app
            names = [c.get("name") for c in camps_by_sid.get(sid, []) if c.get("name")]
            # keep full daily + campaigns so the UI can show each unmatched Google Ads app as its OWN
            # app-row (windowed to the period, with its adwords account) — a live app with spend but no
            # AdMob revenue linked in this account, rather than a black-box "unmatched" sum.
            unmatched_detail[sid] = {"store_id": sid, "spend_usd_micros": s,
                                     "n_campaigns": len(camps_by_sid.get(sid, [])), "sample": names[:3],
                                     "daily": dict(dd), "campaigns": camps_by_sid.get(sid, [])}
            if daily_dated is not None:
                unmatched_detail[sid]["daily_dated"] = dict(daily_dated.get(sid) or {})
            continue
        e = by_app.setdefault(app, {"store_id": sid, "daily": {}, "campaigns": [],
                                    "installs_daily": {}, "convval_daily": {}, "convval_day1_daily": {}})
        for d, v in dd.items():
            e["daily"][d] = e["daily"].get(d, 0) + v
        if daily_dated is not None:                             # the $ view's spend: each day at its own rate
            ed = e.setdefault("daily_dated", {})
            for d, v in (daily_dated.get(sid) or {}).items():
                ed[d] = ed.get(d, 0) + v
        for d, v in (installs_by_sid.get(sid) or {}).items():   # installs window to the same period in the UI
            e["installs_daily"][d] = e["installs_daily"].get(d, 0) + v
        for d, v in (convval_by_sid.get(sid) or {}).items():    # Google Ads conversion value (USD), same window
            e["convval_daily"][d] = e["convval_daily"].get(d, 0) + v
        for d, v in (convval_d1_by_sid.get(sid) or {}).items(): # D0 conversion value (USD), same window
            e["convval_day1_daily"][d] = e["convval_day1_daily"].get(d, 0) + v
        for d, v in (convval_dd_by_sid.get(sid) or {}).items(): # install-day D0 (USD), same window; only when any
            ed = e.setdefault("convval_d0day_daily", {})
            ed[d] = ed.get(d, 0) + v
        sids_of.setdefault(app, []).append(sid)
        e["campaigns"].extend(camps_by_sid.get(sid, []))
        o = d0_open.get(sid) or {}
        if o.get("days"):                                       # the page's "⏳ filling" for these dates too
            e["d0_open"] = sorted(set(e.get("d0_open") or []) | set(o["days"]))
        if o.get("wait"):                                       # waits for an account that cannot answer (no ids here)
            e["d0_wait"] = True
    _d0day_per_app(by_app, sids_of, spend.get("daily") or {}, convval_dd_by_sid, day_at)
    # surface the biggest unmatched store ids so coverage gaps are visible + diagnosable (not a black-box sum)
    top_unmatched = sorted(unmatched_detail.values(), key=lambda x: -x["spend_usd_micros"])[:30]
    out = {"configured": True, "by_app": by_app, "note": spend.get("note"),
           "currency_src": spend.get("currency_src", "USD"), "fx": spend.get("fx", {}),
           "unmatched_spend_usd": unmatched, "unmatched_apps": top_unmatched,
           "unmatched_count": len(unmatched_detail)}
    if daily_dated is not None:
        out["spend_fx"] = "dated"
    # D0 (convval_day1) fixed once complete (google_ads.merge_spend): the last fixed date, when the next one is fixed
    # (and each date not fixed yet: fix_at), Google's reporting lag used, the measured late drift (all stores together),
    # incomplete (the latest read could fix nothing) — only the keys the cache has; none → no "d0" at all. Per app:
    # d0_open / d0_wait above. The install-day ("Day") D0 (convval_d0day, taken once): day_read {date: the first read
    # that took it}, day_next (the next date to come over every account: its moment, the late limit), day_since (the
    # first date taken) — dates and times only, when the cache has them. Per app: convval_d0day_daily / d0day_next
    # (_d0day_per_app)
    d0 = {k: spend.get("d1_" + k) for k in ("fixed_till", "next_fix_utc", "fix_at", "lag_h", "drift", "incomplete")}
    d0 = {k: v for k, v in d0.items() if v is not None}
    if spend.get("d1_day_read"):
        d0["day_read"] = dict(spend["d1_day_read"])
        d0["day_since"] = min(spend["d1_day_read"])
    if spend.get("d1_day_next"):
        d0["day_next"] = dict(spend["d1_day_next"])
    if d0:
        out["d0"] = d0
    return out


def _d0day_per_app(by_app, sids_of, daily, dd_by_sid, day_at):
    """The install-day ("Day") D0 per app (build_roas). convval_d0day_daily keeps a date only when every store of the
    app with cost that day has its Day number (one skipped at its morning read — it waited for an unread account —
    would leave a partial sum over the full spend: the page counts that date as not covered); none left → no key.
    d0day_next: the app's next Day moment {"date", "at"} — its stores' latest (the moment its date can be complete),
    from d1_day_at; only when any. Dates and times only (no store id)."""
    from datetime import datetime
    for app, sids in sids_of.items():
        e = by_app[app]
        ed = e.get("convval_d0day_daily")
        if ed:
            for d in [d for d in ed if any((daily.get(s) or {}).get(d) and d not in (dd_by_sid.get(s) or {})
                                           for s in sids)]:
                del ed[d]
            if not ed:
                del e["convval_d0day_daily"]
        best = None
        for s in sids:
            n = day_at.get(s)
            try:
                off = datetime.strptime(n["at"], "%Y-%m-%dT%H:%M:%SZ") - datetime.strptime(n["date"], "%Y-%m-%d")
            except (TypeError, KeyError, ValueError):
                continue                                 # an odd cache entry counts as absent
            if best is None or off > best[0]:
                best = (off, {"date": n["date"], "at": n["at"]})
        if best:
            e["d0day_next"] = best[1]
