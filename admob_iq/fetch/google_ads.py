"""Google Ads (MCC) marketing-spend fetch for ROAS — app-campaign cost per app, per day.

Uses the Google Ads REST API (v17) with an OAuth refresh token (adwords scope) + a developer token.
Everything is OPTIONAL and best-effort: if the three GOOGLE_ADS_* secrets aren't set (or a call
fails), fetch_app_spend returns None and the ROAS screen just shows a setup hint. This is a SEPARATE
API from AdMob — it never touches or risks the AdMob reporting pull.

Join key: App campaigns carry campaign.app_campaign_setting.app_id = the app's STORE id (Play
package or App Store numeric) — the same store_id AdMob's accounts.apps.list returns — so spend
lines up against AdMob revenue per app. Spend is converted to USD (AdMob's currency) so ROAS is
apples-to-apples; the source currency + FX used are reported for transparency.
"""

import sys

# Google Ads API version. Google sunsets each version ~1 year after release; after that EVERY call
# 404s (empty body). If ROAS suddenly starts 404-ing, bump this to a current version — see
# https://developers.google.com/google-ads/api/docs/release-notes
API_VERSION = "v24"                    # supported as of 2026 (v25 is newest); v17 was sunset → 404
_BASE = "https://googleads.googleapis.com/%s" % API_VERSION
# offline fallback rates (→USD) if the free FX endpoint is unreachable; only used when != USD
# Last-resort rates if BOTH frankfurter hosts are unreachable — kept close to live so a rare miss
# doesn't skew the dashboard (INR 0.0105 ≈ ₹95/USD, matching the live rate; refresh if it drifts).
_FX_FALLBACK = {"USD": 1.0, "INR": 0.0105, "EUR": 1.08, "GBP": 1.27, "AUD": 0.66,
                "CAD": 0.73, "JPY": 0.0065, "BRL": 0.18, "AED": 0.27, "SGD": 0.74}


def _norm_store(app_id):
    """Google Ads app_id → bare store id (strip whitespace and any 'N:' platform prefix)."""
    s = str(app_id or "").strip()
    if len(s) > 2 and s[1] == ":" and s[0].isdigit():
        s = s[2:]
    return s


def _access_token(client_id, client_secret, refresh_token):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    creds = Credentials(token=None, refresh_token=refresh_token,
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=client_id, client_secret=client_secret)
    creds.refresh(Request())
    return creds.token


def _ads_err(r):
    """Pull the SPECIFIC Google Ads errorCode + message out of a failed response body (so the UI shows
    'authorizationError=USER_PERMISSION_DENIED — ...' instead of a truncated JSON blob). Falls back to raw text."""
    try:
        j = r.json()
        j = j[0] if isinstance(j, list) else j
        err = (j or {}).get("error") or {}
        for d in (err.get("details") or []):
            for ge in (d.get("errors") or []):
                ec = ge.get("errorCode") or {}
                name = "; ".join("%s=%s" % (k, v) for k, v in ec.items() if v) or "GoogleAdsError"
                return ("%s — %s" % (name, ge.get("message") or err.get("message") or ""))[:600]
        if err:
            return ("%s: %s" % (err.get("status") or err.get("code") or "?", err.get("message") or ""))[:600]
    except Exception:
        pass
    return (r.text or "")[:500]


def _search(customer_id, login_customer_id, dev_token, access_token, query):
    """POST googleAds:searchStream → flat list of result rows."""
    import requests
    url = "%s/customers/%s/googleAds:searchStream" % (_BASE, customer_id)
    headers = {"Authorization": "Bearer %s" % access_token, "developer-token": dev_token,
               "login-customer-id": login_customer_id, "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, json={"query": query}, timeout=60)
    if not r.ok:                                    # surface the SPECIFIC Google Ads error (helps diagnose)
        raise RuntimeError("HTTP %s: %s" % (r.status_code, _ads_err(r)))
    out = []
    for batch in (r.json() or []):
        out.extend(batch.get("results") or [])
    return out


def _child_accounts(login_customer_id, dev_token, access_token):
    """Non-manager client accounts under the MCC (id + currency + descriptive name). The name lets
    the UI show which Google Ads account each campaign's spend comes from (user's rule: 1 account =
    1 app), so a campaign pointing at the wrong app's store id is easy to spot.
    Also the account's time zone ("tz", e.g. "Asia/Calcutta"): Google Ads report days (segments.date)
    are days in THAT zone. If Google ever refuses the query with time_zone, the roster is asked once
    more without it (and the accounts carry no "tz" key) — spend never depends on the new field."""
    q = ("SELECT customer_client.id, customer_client.currency_code, customer_client.descriptive_name, "
         "customer_client.manager%s FROM customer_client")
    try:
        rows, with_tz = _search(login_customer_id, login_customer_id, dev_token, access_token,
                                q % ", customer_client.time_zone"), True
    except Exception:
        rows, with_tz = _search(login_customer_id, login_customer_id, dev_token, access_token, q % ""), False
    out = []
    for row in rows:
        cc = row.get("customerClient") or {}
        if cc.get("manager"):
            continue                                  # skip nested managers
        a = {"id": str(cc.get("id")), "currency": cc.get("currencyCode") or "USD",
             "name": cc.get("descriptiveName") or ""}
        if with_tz:
            a["tz"] = cc.get("timeZone") or None
        out.append(a)
    return out


def _campaign_id(camp):
    """campaign.id of a row's campaign (the selected id, else the id at the end of its resource name) → str or ""."""
    v = camp.get("id")
    if v in (None, ""):
        v = str(camp.get("resourceName") or "").rsplit("/", 1)[-1]
    return str(v or "")


def _app_spend_for(customer_id, login_customer_id, dev_token, access_token, start, end, search=None):
    """App-campaign cost rows for ONE account over [start,end]. Includes paused/removed campaigns
    (historical cost still counts); status is kept for display. `search` (default _search) is injectable."""
    q = ("SELECT campaign.id, campaign.name, campaign.status, "
         "campaign.app_campaign_setting.app_id, metrics.cost_micros, segments.date "
         "FROM campaign WHERE segments.date BETWEEN '%s' AND '%s' "
         "AND campaign.app_campaign_setting.app_id != '' AND metrics.cost_micros > 0" % (start, end))
    out = []
    for row in (search or _search)(customer_id, login_customer_id, dev_token, access_token, q):
        camp = row.get("campaign") or {}
        sid = _norm_store(((camp.get("appCampaignSetting") or {}).get("appId")))
        if not sid:
            continue
        out.append({"store_id": sid, "campaign_id": str(camp.get("id")),
                    "name": camp.get("name"), "status": camp.get("status"),
                    "date": (row.get("segments") or {}).get("date"),
                    "cost_micros": int((row.get("metrics") or {}).get("costMicros") or 0)})
    return out


def _app_installs_for(customer_id, login_customer_id, dev_token, access_token, start, end, search=None):
    """App-campaign INSTALLS + CONVERSION VALUE for ONE account over [start,end], keyed to the SAME
    store id as spend. Deliberately a SEPARATE query from _app_spend_for so a metric/version problem
    here can never break the (proven) spend pull — the caller runs it best-effort. Installs are
    Google Ads campaign-attributed app installs (NOT the app's total install base). conversions_value
    is the value Google Ads tracks for those conversions (in the account's currency) — with a
    first-day (D0) tROAS setup this IS the first-day value, so value ÷ spend = the Google-Ads ROAS.
    campaign.id is selected too (rows are campaign × day either way — FROM campaign): the per-campaign store
    (fetch.gads_campaign_day) keeps it; the store sums here never read it."""
    q = ("SELECT campaign.id, campaign.app_campaign_setting.app_id, "
         "metrics.biddable_app_install_conversions, metrics.conversions_value, segments.date "
         "FROM campaign WHERE segments.date BETWEEN '%s' AND '%s' "
         "AND campaign.app_campaign_setting.app_id != ''" % (start, end))
    out = []
    for row in (search or _search)(customer_id, login_customer_id, dev_token, access_token, q):
        camp = row.get("campaign") or {}
        sid = _norm_store(((camp.get("appCampaignSetting") or {}).get("appId")))
        if not sid:
            continue
        m = row.get("metrics") or {}
        out.append({"store_id": sid, "date": (row.get("segments") or {}).get("date"),
                    "installs": float(m.get("biddableAppInstallConversions") or 0),
                    "convval": float(m.get("conversionsValue") or 0), "campaign_id": _campaign_id(camp)})
    return out


def _app_convval_lag_for(customer_id, login_customer_id, dev_token, access_token, start, end, search=None):
    """DAY-1 conversion value per store/date: the value from conversions that happened WITHIN ONE DAY
    of the click (segments.conversion_lag_bucket = LESS_THAN_ONE_DAY) — Google Ads' D0 (the dashboard's
    "D0 rev"). Google keeps this lag breakdown for PAST dates too, so it's retroactive — it survives the
    later restatement of the full value, which is exactly the 'D0 vs matured' the UI wants (merge_spend
    fixes a date's number once it is complete: d0_final). Best-effort + SEPARATE query (a version/field
    problem here can never touch spend, installs, or the live convval). campaign.id: as in _app_installs_for."""
    q = ("SELECT campaign.id, campaign.app_campaign_setting.app_id, metrics.conversions_value, segments.date, "
         "segments.conversion_lag_bucket "
         "FROM campaign WHERE segments.date BETWEEN '%s' AND '%s' "
         "AND campaign.app_campaign_setting.app_id != ''" % (start, end))
    out = []
    for row in (search or _search)(customer_id, login_customer_id, dev_token, access_token, q):
        seg = row.get("segments") or {}
        if str(seg.get("conversionLagBucket")) != "LESS_THAN_ONE_DAY":
            continue                                          # keep only the <1-day (day-1) bucket
        camp = row.get("campaign") or {}
        sid = _norm_store(((camp.get("appCampaignSetting") or {}).get("appId")))
        if not sid:
            continue
        out.append({"store_id": sid, "date": seg.get("date"),
                    "convval": float((row.get("metrics") or {}).get("conversionsValue") or 0),
                    "campaign_id": _campaign_id(camp)})
    return out


def _app_hourly_spend_for(customer_id, login_customer_id, dev_token, access_token, start, end, search=None):
    """App-campaign COST by HOUR for ONE account over [start, end] → rows {store_id, campaign_id, date, hour,
    cost_micros} (account currency micros; date and hour in the ACCOUNT's time zone). The spend query plus
    segments.hour (fetch.gads_hourly; every filtered field selected). Read-only."""
    q = ("SELECT campaign.id, campaign.app_campaign_setting.app_id, segments.date, segments.hour, metrics.cost_micros "
         "FROM campaign WHERE segments.date BETWEEN '%s' AND '%s' "
         "AND campaign.app_campaign_setting.app_id != '' AND metrics.cost_micros > 0" % (start, end))
    out = []
    for row in (search or _search)(customer_id, login_customer_id, dev_token, access_token, q):
        camp = row.get("campaign") or {}
        seg = row.get("segments") or {}
        sid = _norm_store((camp.get("appCampaignSetting") or {}).get("appId"))
        try:
            hour = int(seg.get("hour"))
        except (TypeError, ValueError):
            hour = -1
        if not sid or not 0 <= hour <= 23:
            continue
        out.append({"store_id": sid, "campaign_id": _campaign_id(camp), "date": str(seg.get("date") or ""),
                    "hour": hour, "cost_micros": int((row.get("metrics") or {}).get("costMicros") or 0)})
    return out


# ── cost and downloads BY COUNTRY (the Install value tab, GADS_GEO; fetch.gads_geo runs these) ────────────────────
# The exact queries the gads-geo-probe measured: geographic_view with LOCATION_OF_PRESENCE holds ~100% of the app
# campaigns' cost, and MULTI_CHANNEL is every app campaign. Every field a query filters on is also selected (Google
# refuses a WHERE on some fields the SELECT lacks). Read-only; `search` (default _search) is injectable for tests.

def _app_geo_spend_for(customer_id, login_customer_id, dev_token, access_token, start, end, search=None):
    """App-campaign COST by country for ONE account over [start, end] → rows {store_id, date, ccid, cost_micros}
    (account currency micros). store_id "" = a row without an app id (the caller drops and counts it); ccid None = a
    row without a country (the caller's "Other / unmapped")."""
    q = ("SELECT campaign.id, campaign.app_campaign_setting.app_id, campaign.advertising_channel_type, "
         "geographic_view.country_criterion_id, geographic_view.location_type, "
         "segments.date, metrics.cost_micros "
         "FROM geographic_view "
         "WHERE segments.date BETWEEN '%s' AND '%s' "
         "AND campaign.advertising_channel_type = 'MULTI_CHANNEL' "
         "AND geographic_view.location_type = 'LOCATION_OF_PRESENCE' "
         "AND metrics.cost_micros > 0" % (start, end))
    out = []
    for row in (search or _search)(customer_id, login_customer_id, dev_token, access_token, q):
        camp = row.get("campaign") or {}
        gv = row.get("geographicView") or {}
        if camp.get("advertisingChannelType") not in (None, "MULTI_CHANNEL") \
                or gv.get("locationType") not in (None, "LOCATION_OF_PRESENCE"):
            continue                                            # what the WHERE already excludes (selected: checked)
        v = gv.get("countryCriterionId")
        try:
            ccid = str(int(v)) if v not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            ccid = None
        out.append({"store_id": _norm_store((camp.get("appCampaignSetting") or {}).get("appId")),
                    "date": str((row.get("segments") or {}).get("date") or ""), "ccid": ccid,
                    "cost_micros": int((row.get("metrics") or {}).get("costMicros") or 0)})
    return out


def _app_geo_installs_for(customer_id, login_customer_id, dev_token, access_token, start, end, search=None):
    """App-campaign DOWNLOAD conversions by country for ONE account over [start, end] → rows {store_id, date, ccid,
    dl}. A second query: conversion segments cannot share a request with cost. Same store id / ccid rules as
    _app_geo_spend_for."""
    q = ("SELECT campaign.app_campaign_setting.app_id, campaign.advertising_channel_type, "
         "geographic_view.country_criterion_id, geographic_view.location_type, "
         "segments.date, segments.conversion_action_category, metrics.conversions "
         "FROM geographic_view "
         "WHERE segments.date BETWEEN '%s' AND '%s' "
         "AND campaign.advertising_channel_type = 'MULTI_CHANNEL' "
         "AND geographic_view.location_type = 'LOCATION_OF_PRESENCE' "
         "AND segments.conversion_action_category = 'DOWNLOAD'" % (start, end))
    out = []
    for row in (search or _search)(customer_id, login_customer_id, dev_token, access_token, q):
        camp = row.get("campaign") or {}
        gv = row.get("geographicView") or {}
        if camp.get("advertisingChannelType") not in (None, "MULTI_CHANNEL") \
                or gv.get("locationType") not in (None, "LOCATION_OF_PRESENCE") \
                or (row.get("segments") or {}).get("conversionActionCategory") not in (None, "DOWNLOAD"):
            continue
        v = gv.get("countryCriterionId")
        try:
            ccid = str(int(v)) if v not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            ccid = None
        out.append({"store_id": _norm_store((camp.get("appCampaignSetting") or {}).get("appId")),
                    "date": str((row.get("segments") or {}).get("date") or ""), "ccid": ccid,
                    "dl": float((row.get("metrics") or {}).get("conversions") or 0)})
    return out


def _geo_iso(login_customer_id, dev_token, access_token, ids=None, search=None):
    """Country criterion id → ISO-2, always asked on the MCC → {ccid: {"cc": ISO-2 | None, "parent": ccid | None}}.
    ids None: the Country list (target_type 'Country'). ids [...]: those ids, ANY target type (a territory keeps its
    own ISO-2; a region without one names its parent) — one request for all of them, asked once more by resource name
    when Google refuses the id list (HTTP 400). Any other failure raises (the caller counts it)."""
    srch = search or _search
    mcc = login_customer_id

    def num(v):
        try:
            return str(int(str(v).rsplit("/", 1)[-1])) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    if ids is None:
        rows = srch(mcc, mcc, dev_token, access_token,
                    "SELECT geo_target_constant.id, geo_target_constant.country_code "
                    "FROM geo_target_constant WHERE geo_target_constant.target_type = 'Country'")
    else:
        want = sorted({n for n in (num(i) for i in ids) if n}, key=int)
        if not want:
            return {}
        sel = ("SELECT geo_target_constant.id, geo_target_constant.country_code, geo_target_constant.target_type, "
               "geo_target_constant.parent_geo_target, geo_target_constant.status "
               "FROM geo_target_constant WHERE ")
        try:
            rows = srch(mcc, mcc, dev_token, access_token, sel + "geo_target_constant.id IN (%s)" % ", ".join(want))
        except Exception as e:
            if not str(e).startswith("HTTP 400"):
                raise
            rows = srch(mcc, mcc, dev_token, access_token, sel + "geo_target_constant.resource_name IN (%s)"
                        % ", ".join("'geoTargetConstants/%s'" % i for i in want))
    out = {}
    for row in rows or []:
        g = row.get("geoTargetConstant") or {}
        gid = num(g.get("id")) or num(g.get("resourceName"))
        if not gid:
            continue
        cc = str(g.get("countryCode") or "").strip().upper()
        out[gid] = {"cc": cc if len(cc) == 2 and cc.isascii() and cc.isalpha() else None,
                    "parent": num(g.get("parentGeoTarget")) if ids is not None else None}
    return out


def _fx_cache_path():
    import os
    return os.getenv("FX_CACHE_PATH", os.path.join("data", "fx_cache.json"))


def _fx_load_cache():
    import json
    try:
        with open(_fx_cache_path(), encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _fx_save_cache(ccy, rate):
    """Persist the last GOOD rate so an offline build reuses it instead of a stale hardcoded constant.
    Lives in data/fx_cache.json, which the workflow commits each run → survives across builds."""
    import os, json, time
    try:
        c = _fx_load_cache()
        c[ccy] = float(rate); c["_ts_" + ccy] = int(time.time())
        p = _fx_cache_path(); d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(c, f)
    except Exception:
        pass


def _fx_to_usd(ccy):
    if ccy == "USD" or not ccy:
        return 1.0
    try:
        import requests
        # frankfurter.app now 301-redirects to frankfurter.dev — hit the canonical .dev host DIRECTLY
        # (the redirect was intermittently failing on the runner → it fell back to the stale hardcoded
        # rate, so the WHOLE dashboard's USD⇄INR read ~12% off). Try .dev, then .app.
        for _url in ("https://api.frankfurter.dev/v1/latest?from=%s&to=USD" % ccy,
                     "https://api.frankfurter.app/latest?from=%s&to=USD" % ccy):
            try:
                r = requests.get(_url, timeout=10)
                rate = (r.json().get("rates") or {}).get("USD")
                if rate:
                    _fx_save_cache(ccy, rate)       # remember the last good rate for offline builds
                    return float(rate)
            except Exception:
                continue
    except Exception:
        pass
    # Both hosts unreachable → the LAST successfully-fetched rate (persisted, at most a few hours old),
    # and only if that's missing too, the hardcoded near-live constant. Never a silently-stale value.
    cached = _fx_load_cache().get(ccy)
    if cached:
        return float(cached)
    return _FX_FALLBACK.get(ccy, 1.0)


# Spend-cache schema version. v2 stores RAW source-currency micros (no FX baked in); the single hop
# to USD / display currency happens ONCE at build time against one rate. v1 baked the fetch-time FX
# into the stored numbers — when that fetch fell back to a stale INR rate but the display used the
# live rate, spend showed ~13% too high. A v1 cache is discarded on read so it re-backfills as v2.
SPEND_CACHE_V = 2


def _pick_base(rows, amount_key):
    """The currency carrying the most <amount_key> across rows — the single 'base' currency we store
    the raw series in (MCC accounts normally all bill in one currency, so this is that currency)."""
    from collections import defaultdict
    tot = defaultdict(float)
    for r in rows:
        tot[r.get("currency") or "USD"] += float(r.get(amount_key) or 0)
    return max(tot, key=tot.get) if tot else "USD"


def _aggregate(rows, fx_fn=_fx_to_usd):
    """Aggregate spend by store_id → {daily, campaigns} in the SOURCE currency as RAW micros — NO FX
    baked in. Accounts under one MCC normally bill in a single currency; a minority billed in another
    is converted into the majority ('base') currency here so the stored series is single-currency. The
    hop to USD (AdMob's base) and to the display currency then happens ONCE, at build time, against a
    single rate — so stored spend can't drift when the FX endpoint is briefly down (that drift was
    inflating INR spend ~13% whenever a fetch fell back to a stale rate while display used the live one)."""
    from collections import defaultdict
    base = _pick_base(rows, "cost_micros")
    fx = {}

    def to_base(micros, ccy):
        if not ccy or ccy == base:
            return int(micros or 0)
        for c in (ccy, base):
            if c not in fx:
                fx[c] = fx_fn(c)
        return int(round((micros or 0) * fx[ccy] / (fx[base] or 1.0)))   # ccy→USD→base

    daily = defaultdict(lambda: defaultdict(int))                 # store_id -> date -> base-currency micros
    camps = defaultdict(dict)                                     # store_id -> campaign_id -> agg
    for r in rows:
        v = to_base(r.get("cost_micros") or 0, r.get("currency") or "USD")
        sid = r["store_id"]
        daily[sid][str(r.get("date"))] += v
        c = camps[sid].setdefault(r["campaign_id"], {"name": None, "status": None, "cost": 0,
                                                     "acct": None, "acct_name": None})
        c["name"] = r.get("name") or c["name"]; c["status"] = r.get("status") or c["status"]
        c["acct"] = r.get("account") or c["acct"]; c["acct_name"] = r.get("account_name") or c["acct_name"]
        c["cost"] += v
    return {
        "v": SPEND_CACHE_V,
        "daily": {sid: dict(dd) for sid, dd in daily.items()},
        "campaigns": {sid: [{"id": cid, "name": c["name"], "status": c["status"],
                             "cost_micros": c["cost"], "account": c["acct"], "account_name": c["acct_name"]}
                            for cid, c in cc.items()]
                      for sid, cc in camps.items()},
        "currency_src": base, "fx": fx,
    }


def _aggregate_installs(rows):
    """Sum campaign-attributed installs by store_id -> date (counts, no currency)."""
    from collections import defaultdict
    daily = defaultdict(lambda: defaultdict(float))
    for r in rows:
        daily[r["store_id"]][str(r.get("date"))] += float(r.get("installs") or 0)
    return {sid: {d: round(v, 2) for d, v in dd.items()} for sid, dd in daily.items()}


def _aggregate_convval(rows, base=None, fx_fn=_fx_to_usd):
    """Sum Google Ads conversion VALUE by store_id -> date in the BASE currency as RAW value — NO FX
    baked in, matching how spend is stored. `base` should be the spend's base currency so value and
    spend share one unit (inferred from these rows if omitted). Converted to USD once at build time,
    so value ÷ USD-spend gives an apples-to-apples ROAS."""
    from collections import defaultdict
    if base is None:
        base = _pick_base(rows, "convval")
    fx = {}
    daily = defaultdict(lambda: defaultdict(float))
    for r in rows:
        ccy = r.get("currency") or "USD"
        val = float(r.get("convval") or 0)
        if ccy and ccy != base:
            for c in (ccy, base):
                if c not in fx:
                    fx[c] = fx_fn(c)
            val = val * fx[ccy] / (fx[base] or 1.0)                       # ccy→USD→base
        daily[r["store_id"]][str(r.get("date"))] += val
    return {sid: {d: round(v, 2) for d, v in dd.items()} for sid, dd in daily.items()}


def fetch_campaign_accounts(s, *, mode="live"):
    """Map campaign_id -> {account, account_name} for EVERY app campaign (paused/removed included), via a
    lightweight roster query (NO date/cost filter) per child account. Lets the build backfill the adwords
    account onto OLD cached campaigns stored before account-tagging existed — or paused ones with no recent
    spend, which the windowed spend fetch never re-tags (that's the '?' account label on some app rows).
    Best-effort: returns {} if not configured or on error, never raising."""
    if mode == "mock":
        return {}
    dev = s.get("google_ads_dev_token"); mcc = s.get("google_ads_login_customer_id")
    rt = s.get("google_ads_refresh_token")
    cid = s.get("google_ads_client_id") or s.get("google_client_id")
    csec = s.get("google_ads_client_secret") or s.get("google_client_secret")
    if not (dev and mcc and rt and cid and csec):
        return {}
    try:
        token = _access_token(cid, csec, rt)
        accounts = _child_accounts(mcc, dev, token) or []
    except Exception as e:
        import sys; print(f"campaign roster auth/accounts skipped: {str(e)[:200]}", file=sys.stderr)
        return {}
    q = "SELECT campaign.id FROM campaign WHERE campaign.app_campaign_setting.app_id != ''"
    cmap = {}
    for a in accounts:
        try:
            for row in _search(a["id"], mcc, dev, token, q):
                cid_ = str(((row.get("campaign") or {}).get("id")) or "")
                if cid_:
                    cmap[cid_] = {"account": a["id"], "account_name": a.get("name") or ""}
        except Exception as e:
            import sys; print(f"campaign roster skipped for {a.get('id')}: {str(e)[:160]}", file=sys.stderr)
    return cmap


def needs_campaign_accounts(spend):
    """Does any cached campaign of `spend` lack its account? Only those are what apply_campaign_accounts fills: with
    none, the roster queries (fetch_campaign_accounts) could change nothing, so the build does not ask them."""
    if not spend:
        return False
    return any(not c.get("account") for camps in (spend.get("campaigns") or {}).values() for c in camps)


def apply_campaign_accounts(spend, cmap):
    """Fill missing account/account_name on a spend dict's cached campaigns from the roster map (in place)."""
    if not spend or not cmap:
        return spend
    for _sid, camps in (spend.get("campaigns") or {}).items():
        for c in camps:
            if not c.get("account"):
                m = cmap.get(str(c.get("id")))
                if m:
                    c["account"] = m["account"]
                    c["account_name"] = c.get("account_name") or m["account_name"]
    return spend


# The per-campaign × day rows the last live fetch_app_spend downloaded (spend, installs + value, day-1 value), kept
# aside — only while GADS_ARCHIVE is on — for the per-campaign store (fetch.gads_campaign_day), which take_rows()
# hands over once. The rows are the SAME list objects the store sums above are made of: nothing here changes them.
_TAKEN = {}


def take_rows():
    """→ the rows the last live fetch_app_spend kept aside ({} when none), then forgets them:
    {"start", "end", "accounts": [{id, currency, ...}], "spend": [...], "inst": [...], "d1": [...]}."""
    global _TAKEN
    out, _TAKEN = _TAKEN, {}
    return out


SPEND_WORKERS = 4      # accounts asked side by side per query (GADS_SPEND_WORKERS; 1 = one after another, as before)


def _spend_workers():
    import os
    try:
        n = int(os.getenv("GADS_SPEND_WORKERS") or SPEND_WORKERS)
    except ValueError:
        n = SPEND_WORKERS
    return max(1, n)


def _per_account(accounts, ask, workers):
    """ask(account) for every account → [(account, rows, None) | (account, None, exception)] in ACCOUNT order. With
    workers > 1 the requests go side by side (one per account at a time, like the geo / archive steps); the caller
    reads the list in order, so its rows, error list and log lines come out exactly as asked one after another."""
    def one(a):
        try:
            return a, ask(a), None
        except Exception as e:
            return a, None, e
    if workers <= 1 or len(accounts) <= 1:
        return [one(a) for a in accounts]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(workers, len(accounts))) as ex:
        return list(ex.map(one, accounts))


def _not_enabled(e):
    """HTTP 403 CUSTOMER_NOT_ENABLED: the whole account cannot answer (cancelled / not enabled) — any query to it."""
    s = str(e)
    return s.startswith("HTTP 403") and "CUSTOMER_NOT_ENABLED" in s


# ── D0 (the day-1 lag bucket above): when a click date's number is complete ──────────────────────────────────────────
# Click date X (the account's time zone): the last click of X has its 24 h until X+2 00:00 local (an hour later when
# summer time starts on X+1: _d0_moment), and Google Ads reports conversions some hours late (the owner's figure: 3-4 h)
# → X is final from then + D0_LAG_HOURS on. From then merge_spend keeps the number it read and never takes Google's
# later one (owner: "fix D0").
D0_LAG_HOURS = 4                 # GADS_D0_LAG_HOURS overrides
D0_NO_TZ = "Etc/GMT+12"          # an account without a time zone: UTC−12, the zone whose days end last (never early)


def _d0_lag_h():
    import os
    try:
        n = int(os.getenv("GADS_D0_LAG_HOURS") or D0_LAG_HOURS)
    except ValueError:
        n = D0_LAG_HOURS
    return max(0, n)


def _d0_zone(tz):
    """An account's time zone (IANA name) → tzinfo; none / unknown → D0_NO_TZ (the conservative one)."""
    from zoneinfo import ZoneInfo
    for name in (tz, D0_NO_TZ):
        try:
            if name:
                return ZoneInfo(str(name))
        except Exception:
            continue
    from datetime import timedelta, timezone
    return timezone(timedelta(hours=-12))


def _d0_moment(zones, x, lag):
    """The UTC moment click date x (a date) is final in every zone of `zones` (tzinfos or zone names): its last click's
    24 h end at the later of (x+2 00:00 local) and (x+1 00:00 local) + 24 h — the second when x+1 is a 23-hour day
    (summer time starting) — and Google Ads reports `lag` hours late."""
    from datetime import datetime, time, timedelta, timezone
    end = None
    for z in zones:
        z = _d0_zone(z) if isinstance(z, str) else z
        day1 = datetime.combine(x + timedelta(days=1), time(0), tzinfo=z).astimezone(timezone.utc)
        day2 = datetime.combine(x + timedelta(days=2), time(0), tzinfo=z).astimezone(timezone.utc)
        t = max(day2, day1 + timedelta(hours=24))
        end = t if end is None or t > end else end
    return end + timedelta(hours=lag)


def _iso_z(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def d0_final(accounts, now=None, lag_h=None):
    """The last click date whose D0 is complete in EVERY account of `accounts` (each in its own a["tz"]; the latest
    moment wins) → {"final_till": ISO date, "next_fix_utc": the moment final_till moves on one day (ISO, UTC, "Z"),
    "lag_h", "zones": the zone names used (merge_spend works out the moment of any other date with them)}.
    now: a tz-aware datetime (default: the clock); lag_h: default GADS_D0_LAG_HOURS / D0_LAG_HOURS."""
    from datetime import datetime, timedelta, timezone
    lag = _d0_lag_h() if lag_h is None else max(0, int(lag_h))
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    zones = {}
    for a in accounts or [{}]:
        z = _d0_zone((a or {}).get("tz"))
        zones[str(z)] = z
    # (now − L h, in the earliest zone).date() − 2 days; a day earlier while a 23-hour day after it is not 24 h on yet
    final = min((now - timedelta(hours=lag)).astimezone(z).date() for z in zones.values()) - timedelta(days=2)
    if _d0_moment(zones.values(), final, lag) > now:
        final -= timedelta(days=1)
    at = _d0_moment(zones.values(), final + timedelta(days=1), lag)
    return {"final_till": final.isoformat(), "next_fix_utc": _iso_z(at), "lag_h": lag, "zones": sorted(zones)}


def fetch_app_spend(s, start, end, *, mode="live", now=None):
    """Return {daily:{store_id:{date:usd_micros}}, campaigns:{store_id:[...]}, currency_src, fx} or
    None when Google Ads isn't configured / a call fails. `s` is config.settings().
    Also the D0 finality of this read (d0_final over the accounts asked for the day-1 query, at `now` — tz-aware,
    default the clock read before the day-1 queries): d1_final_till, d1_next_fix_utc, d1_lag_h, d1_zones; d1_ok =
    every asked account answered the day-1 query, an account with no click in the window (no cost rows) aside
    (merge_spend fixes dates only from a complete read); d1_unread = the accounts that could not answer at all (a 403
    on cost and day-1, not CUSTOMER_NOT_ENABLED; only when any) — merge_spend keeps their stores' dates unfixed (they
    may have clicks), while every other store is fixed."""
    global _TAKEN
    _TAKEN = {}
    if mode == "mock":
        return _mock_spend(start, end)
    dev = s.get("google_ads_dev_token"); mcc = s.get("google_ads_login_customer_id")
    rt = s.get("google_ads_refresh_token")
    # The Google Ads refresh token may belong to a DIFFERENT OAuth client than AdMob's. Prefer a
    # Google-Ads-specific client if given, else fall back to the AdMob client (GOOGLE_CLIENT_ID/SECRET).
    cid = s.get("google_ads_client_id") or s.get("google_client_id")
    csec = s.get("google_ads_client_secret") or s.get("google_client_secret")
    if not (dev and mcc and rt and cid and csec):
        return None                                              # not configured → UI shows setup hint
    try:
        token = _access_token(cid, csec, rt)
    except Exception as e:
        msg = str(e)[:260]
        # 'unauthorized_client' ~always = the refresh token was minted with a different OAuth client
        extra = (" — ye refresh token kisi ALAG OAuth client se bana lagta hai. Ya to wahi client "
                 "id/secret (jo AdMob use karta hai) se naya 'adwords'-scope token banao, ya us "
                 "client ke id+secret GOOGLE_ADS_CLIENT_ID / GOOGLE_ADS_CLIENT_SECRET me daalo.") \
                if "unauthorized_client" in msg else ""
        return {"error": "OAuth fail — refresh token / client-id-secret check karo: %s%s" % (msg, extra)}
    try:
        accounts = _child_accounts(mcc, dev, token) or [{"id": mcc, "currency": "USD", "name": ""}]
    except Exception as e:
        em = str(e)[:450]
        low = em.lower()
        if "404" in em:
            hint = " — API version purana (API_VERSION bump) ya galat MCC id."
        elif "permission_denied" in low or "not have permission" in low or "user_permission" in low:
            hint = (" — jis Google account se token banaya wo is MCC ka user nahi hai, YA MCC id galat. "
                    "MCC-access wale account se token banao, ya GOOGLE_ADS_LOGIN_CUSTOMER_ID (10-digit, bina dash) sahi karo.")
        elif "developer_token" in low:
            hint = " — developer token ka level/approval issue (Google Ads → API Center)."
        else:
            hint = ""
        return {"error": "MCC accounts nahi mile (dev token approval / MCC id / access): %s%s" % (em, hint)}
    # Each of the three queries goes to the accounts side by side (_per_account); the answers are taken in account
    # order, so every row, error and log line is in the same order as when asked one account after another.
    workers = _spend_workers()
    rows, errs, gone, idle, denied = [], [], set(), set(), set()
    for i, (a, got, e) in enumerate(_per_account(
            accounts, lambda a: _app_spend_for(a["id"], mcc, dev, token, start, end), workers)):
        if e is not None:
            errs.append(str(e)[:220])
            if _not_enabled(e):
                gone.add(i)                  # a not-enabled account answers 403 to installs / day-1 too: not asked
            elif str(e).startswith("HTTP 403"):
                denied.add(a["id"])          # any other 403 (e.g. USER_PERMISSION_DENIED): it cannot answer at all
            continue
        if not got:
            idle.add(a["id"])                # no app-campaign cost in the window = no click, so no D0 to miss either
        for r in got:
            r["currency"] = a["currency"]; r["account"] = a["id"]; r["account_name"] = a.get("name") or ""
            rows.append(r)
    if not rows and errs:
        return {"error": "Spend query fail (%d/%d accounts): %s" % (len(errs), len(accounts), errs[0])}
    if not rows:
        return {"v": SPEND_CACHE_V, "daily": {}, "campaigns": {}, "installs": {}, "convval": {}, "convval_day1": {},
                "currency_src": "USD", "fx": {}, "note": "connected — is window me koi app-campaign spend nahi mila"}
    agg = _aggregate(rows)
    # Installs + conversion value: best-effort + SEPARATE from spend, so a problem here can never
    # break the spend/ROAS numbers above.
    # The accounts that answered the spend query 403 CUSTOMER_NOT_ENABLED are not asked again (the whole account
    # cannot answer: no rows either way — as gads_campaign_day._ask does).
    asked = [a for i, a in enumerate(accounts) if i not in gone]
    if gone:
        print("roas: installs + day-1 not asked for %d not-enabled accounts" % len(gone), file=sys.stderr)
    inst_rows = []
    for a, got, e in _per_account(asked, lambda a: _app_installs_for(a["id"], mcc, dev, token, start, end), workers):
        if e is not None:
            print("roas: installs/convval skipped for %s: %s" % (a.get("id"), e), file=sys.stderr)
            continue
        for r in got:
            r["currency"] = a["currency"]; r["account"] = a["id"]; inst_rows.append(r)
    agg["installs"] = _aggregate_installs(inst_rows)
    agg["convval"] = _aggregate_convval(inst_rows, base=agg["currency_src"])   # same base as spend
    # Day-1 conversion value (retroactive, via conversion-lag bucket) — best-effort + separate, so a
    # field/version problem here can never break spend/installs/convval above.
    from datetime import datetime, timezone
    read_at = now or datetime.now(timezone.utc)  # finality's clock: before the D0 numbers are read, never after them
    d1_rows, d1_ok, unread = [], True, []
    for a, got, e in _per_account(asked, lambda a: _app_convval_lag_for(a["id"], mcc, dev, token, start, end),
                                  workers):
        if e is not None:
            # an incomplete D0 read never fixes a date (merge_spend) — unless this account has no D0 this read could
            # miss (idle above: no click in the window), else one such account would block the fixing of every app
            # for good. An account that cannot answer at all (a 403 on cost too) may have clicks: only ITS stores
            # wait (d1_unread → merge_spend), every other store is fixed
            if a["id"] in denied:
                unread.append(a["id"])
            elif a["id"] not in idle:
                d1_ok = False
            print("roas: day-1 convval skipped for %s: %s" % (a.get("id"), e), file=sys.stderr)
            continue
        for r in got:
            r["currency"] = a["currency"]; r["account"] = a["id"]; d1_rows.append(r)
    agg["convval_day1"] = _aggregate_convval(d1_rows, base=agg["currency_src"])
    # D0 finality of this read: the dates complete in every asked account's own time zone (merge_spend fixes them)
    agg.update({"d1_" + k: v for k, v in d0_final(asked, read_at).items()})
    agg["d1_ok"] = d1_ok
    if unread:
        agg["d1_unread"] = unread
    if s.get("gads_archive"):                    # the per-campaign store's input (never part of the returned cache)
        _TAKEN = {"start": str(start), "end": str(end), "accounts": [dict(a) for a in accounts],
                  "spend": rows, "inst": inst_rows, "d1": d1_rows}
    return agg


def merge_spend(cached, fresh, refetch_start):
    """Incremental spend cache. Google Ads restates spend/conversions for a while (~60 days), so we
    only ever re-pull a recent window and keep the SETTLED older history from the cache. `fresh`
    covers [refetch_start, today] and is OVERLAID onto the cached history per store/date — it only
    updates or adds, never erases. So Google Ads restatements are captured, old data isn't re-fetched
    hourly, and a run whose fresh fetch is late/incomplete can't wipe a store's recent spend.

    - fresh is None      → Google Ads not configured: no ROAS (never serve stale cache).
    - fresh has 'error'  → transient failure: keep the settled history we already have.
    - cached is None     → first run / full backfill: just use fresh.

    convval_day1 (Google Ads' D0) is the one exception: a click date's D0 is FIXED once complete (owner: the number
    never changes after that). d1_fixed_till = the last fixed date: it moves on only with a complete read (fresh
    d1_ok) to that read's d1_final_till (fetch_app_spend / d0_final). Per store-day (_merge_d0): a date fixed before
    this read keeps the cached number; any other date takes this read's number (the cached one if this read lacks it)
    and is fixed by this read only when final for it — a complete read, the date ≤ this read's own d1_final_till, and
    none of the store's accounts unread (d1_unread: a 403 on every query; the store's accounts from its campaigns,
    and the ones it already waits for until a complete read shows them read). A store-day ≤ d1_fixed_till this read
    cannot fix — with a D0 number or only with cost — stays live in d1_open ({store: {"days", "wait"}}) until a read
    that can. A store-day with cost that a complete read covered (≥ refetch_start) but brought no D0 for is fixed at
    0.0 the same way (no value within 24 h: a late one never slips in afterwards). d1_incomplete: true when the latest
    read could fix nothing (incomplete, or a failed fetch: the page then does not promise "the next refresh"). An odd
    D0 value or field in the cache counts as absent (never raises). d1_next_fix_utc: the moment
    d1_fixed_till + 1 is final, d1_fix_at: {date: that moment} for the dates not fixed yet (_d0_next_fix, _d0_fix_at:
    this read's zones and lag). d1_drift: how far Google's CURRENT number of the latest 30 fixed dates this read also
    has is from the fixed one, all stores together ({"days", "from", "to", "pct"}; the measured size of what fixing
    leaves out; a complete read only and no waiting store, else the cached one). The log is counts only."""
    if fresh is None:
        return None
    if fresh.get("error"):
        if cached and cached.get("d1_fixed_till"):
            return dict(cached, d1_incomplete=True)      # nothing read: the page must not promise "next refresh"
        return cached or fresh
    if not cached:
        fixed = _d0_date(fresh.get("d1_final_till")) if fresh.get("d1_ok") else None
        fresh["convval_day1"], still, n, _ = _merge_d0(
            {}, fresh.get("convval_day1") or {}, None, fixed, fixed, spend=fresh.get("daily"), lo=refetch_start,
            unread=fresh.get("d1_unread"), owners=_d0_owners(fresh.get("campaigns")))
        fresh["d1_fixed_till"] = fixed
        for k, v in (("d1_open", still), ("d1_next_fix_utc", _d0_next_fix(None, fresh, fixed)),
                     ("d1_fix_at", _d0_fix_at(None, fresh, fixed, still)),
                     ("d1_incomplete", not fresh.get("d1_ok"))):
            if v:
                fresh[k] = v
            else:
                fresh.pop(k, None)
        _d0_log(fresh, fixed, n, still)
        return fresh
    out = {"v": SPEND_CACHE_V,
           "currency_src": fresh.get("currency_src") or cached.get("currency_src", "USD"),
           "fx": fresh.get("fx") or cached.get("fx", {}), "note": fresh.get("note")}
    for key in ("daily", "installs", "convval"):
        cd = cached.get(key) or {}
        fd = fresh.get(key) or {}
        merged = {}
        for sid in set(cd) | set(fd):
            # NON-destructive: keep the whole cached history, then overlay the fresh window (update/add).
            # A run whose fresh fetch is late/missing a store (Google Ads reports recent spend with a lag)
            # therefore can NEVER wipe that store's recent spend — which is what caused spend to flip in/out.
            m = dict(cd.get(sid) or {})
            m.update(fd.get(sid) or {})
            if m:
                merged[sid] = m
        out[key] = merged
    old = _d0_date(cached.get("d1_fixed_till"))        # None: a cache written before D0 was fixed
    fin = _d0_date(fresh.get("d1_final_till")) if fresh.get("d1_ok") else None    # what this read can fix
    fixed = max((x for x in (old, fin) if x), default=None)
    cc = cached.get("campaigns") or {}
    fc = fresh.get("campaigns") or {}
    out["convval_day1"], still, n_fixed, drift = _merge_d0(
        cached.get("convval_day1") or {}, fresh.get("convval_day1") or {}, old, fixed, fin, spend=out["daily"],
        lo=refetch_start, opened=cached.get("d1_open"), unread=fresh.get("d1_unread"), owners=_d0_owners(cc, fc))
    out["d1_fixed_till"] = fixed
    for k, v in (("d1_open", still or None), ("d1_next_fix_utc", _d0_next_fix(cached, fresh, fixed)),
                 ("d1_fix_at", _d0_fix_at(cached, fresh, fixed, still)),
                 ("d1_lag_h", fresh["d1_lag_h"] if fresh.get("d1_lag_h") is not None else cached.get("d1_lag_h")),
                 ("d1_drift", drift or cached.get("d1_drift")),
                 ("d1_incomplete", None if fresh.get("d1_ok") else True)):
        if v is not None:
            out[k] = v
    _d0_log(fresh, fixed, n_fixed, still)
    out["campaigns"] = {sid: (fc.get(sid) or cc.get(sid) or []) for sid in set(cc) | set(fc)}
    return out


D0_DRIFT_DATES = 30              # the latest fixed dates the measured drift (d1_drift) is taken over
D0_FIX_AT_DAYS = 45              # the most dates d1_fix_at lists (the latest; the page steps a day from next_fix_utc)


def _d0_date(x):
    """x when it is an ISO date ("YYYY-MM-DD"), else None (an odd cache value never raises)."""
    from datetime import date
    try:
        return x if isinstance(x, str) and date.fromisoformat(x).isoformat() == x else None
    except ValueError:
        return None


def _d0_list(x):
    return x if isinstance(x, (list, tuple)) else ()


def _d0_vals(dd):
    """{date: value} with finite numbers only: a corrupt / hand-edited value (None, text, NaN) counts as absent."""
    import math
    if not isinstance(dd, dict):
        return {}
    return {d: v for d, v in dd.items()
            if isinstance(d, str) and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)}


def _d0_owners(*camps):
    """{store: {account ids}} from campaign maps ({store: [{"account": id, ...}]}: the cache's and this read's)."""
    out = {}
    for cm in camps:
        for sid, lst in (cm.items() if isinstance(cm, dict) else ()):
            for c in _d0_list(lst):
                a = (c or {}).get("account") if isinstance(c, dict) else None
                if a:
                    out.setdefault(sid, set()).add(str(a))
    return out


def _merge_d0(cd, fd, old, fixed, fin, spend=None, lo=None, opened=None, unread=(), owners=None):
    """merge_spend's convval_day1 rule. cd / fd: {store: {date: value}} of the cache / this read; old: the last date
    fixed before this read (None = none), fixed: after it; fin: this read's own d1_final_till when it is complete, else
    None (it fixes nothing). opened: the cache's d1_open, {store: {"days": [store-days ≤ old not fixed yet], "wait":
    [accounts]}}; unread: this read's d1_unread; owners: {store: {accounts}} (_d0_owners).
    A store-day ≤ old the cache holds and d1_open does not list is fixed: kept (Google's number now is only measured,
    as drift). Any other one takes this read's number (else keeps the cached one), and this read fixes it when it can
    for that store: d ≤ fin and none of the store's accounts (owners + the ones it already waits for) unread — else,
    when d ≤ fixed, it stays live in the new d1_open (with the unread accounts as "wait"). A store's "wait" ends only
    with a complete read that does not list the account as unread (it answered the day-1 query, or it has no click in
    the window); an incomplete read keeps it. A complete read also fixes at 0.0 every store-day ≤ fin with cost in
    `spend` ({store: {date: micros}}) from `lo` on (the read's first date) and no D0, for a store it can fix: this read
    covered it and Google had none within 24 h. Such a store-day this read cannot fix (no D0 yet) is live in d1_open
    too — the page never calls a date fixed while its number can still move. Below lo nothing was read, so an absent
    day stays absent. A value or field of an odd type (a corrupt / hand-edited cache) counts as absent: never raises.
    → (merged, d1_open, store-days fixed by this read, drift | None — measured only from a complete read and never on
    a waiting store: a store missing an account's part would read as a false drop)."""
    cd, fd = (x if isinstance(x, dict) else {} for x in (cd, fd))
    opened, spend = (x if isinstance(x, dict) else {} for x in (opened, spend))
    owners = owners or {}
    unread = {str(a) for a in unread} if isinstance(unread, (list, tuple, set)) else set()
    merged, still, n, pairs = {}, {}, 0, []
    for sid in set(cd) | set(fd) | set(opened) | set(spend):
        c, f, e = _d0_vals(cd.get(sid)), _d0_vals(fd.get(sid)), opened.get(sid)
        e = e if isinstance(e, dict) else {}
        live = {d for d in _d0_list(e.get("days")) if _d0_date(d)}
        prev = {str(a) for a in _d0_list(e.get("wait"))}
        # an incomplete read (fin None) does not show the waited-for accounts answered: their wait stays
        wait = sorted(((set(owners.get(sid) or ()) | prev) & unread) | (set() if fin else prev))
        can = None if wait else fin                  # this read fixes this store's dates up to `can`

        def done(d):                                 # fixed before this read
            return bool(old) and d <= old and d in c and d not in live
        m = dict(c)
        for d, v in f.items():
            if done(d):
                if fin and not wait:
                    pairs.append((d, c[d], v))       # fixed: kept; Google's number now is only measured (drift)
                continue
            m[d] = v
        cost = {d for d, v in _d0_vals(spend.get(sid)).items() if v and (not lo or d >= str(lo))}
        if can:
            for d in cost:
                if d <= can and d not in m:
                    m[d] = 0.0
        days = []
        for d in set(m) | live | cost:
            if not fixed or d > fixed or done(d):
                continue
            if can and d <= can:
                if d in m:
                    n += 1                           # fixed by this read (an open day below lo it cannot see: let go)
            else:
                days.append(d)                       # ≤ d1_fixed_till, not final for this store yet: live
        if m:
            merged[sid] = m
        if days or wait:
            still[sid] = {"days": sorted(days), "wait": wait}
    days = sorted({d for d, _, _ in pairs})[-D0_DRIFT_DATES:]
    keep = set(days)
    was = sum(v for d, v, _ in pairs if d in keep)
    now = sum(v for d, _, v in pairs if d in keep)
    drift = {"days": len(days), "from": days[0], "to": days[-1], "pct": round((now / was - 1) * 100, 2)} \
        if days and was > 0 else None
    return merged, still, n, drift


def _d0_next_fix(cached, fresh, fixed):
    """The merged cache's d1_next_fix_utc: the moment `fixed` + 1 is final, for this read's zones and lag (d1_zones,
    d1_lag_h: d0_final's rule exactly). A read without its zones: its own moment (for ITS d1_final_till + 1) moved by
    whole days to `fixed` + 1; a read without one either: the cache's (such a read moves nothing). Nothing fixed →
    None."""
    from datetime import date, datetime, timedelta
    if not fixed:
        return None
    zones, lag = fresh.get("d1_zones"), fresh.get("d1_lag_h")
    try:
        if zones and lag is not None:
            return _iso_z(_d0_moment(zones, date.fromisoformat(fixed) + timedelta(days=1), int(lag)))
        at, fin = fresh.get("d1_next_fix_utc"), fresh.get("d1_final_till")
        if at and fin:
            t = datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ")
            t -= timedelta(days=(date.fromisoformat(fin) - date.fromisoformat(fixed)).days)
            return t.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        pass
    return (cached or {}).get("d1_next_fix_utc") if (cached or {}).get("d1_fixed_till") == fixed else None


def _d0_fix_at(cached, fresh, fixed, still):
    """{date: the UTC moment its D0 is final} for the dates not fixed yet — fixed + 1 (or the earliest date still open,
    d1_open) up to 4 days after this read's final_till, at most D0_FIX_AT_DAYS, the latest — with this read's zones and
    lag: the page's "⏳ filling" tooltip, exact across a summer-time change. A read without its zones: the cache's when
    `fixed` did not move; nothing fixed → None."""
    from datetime import date, timedelta
    zones, lag, fin = fresh.get("d1_zones"), fresh.get("d1_lag_h"), fresh.get("d1_final_till")
    if not fixed:
        return None
    if not (zones and lag is not None and fin):
        return (cached or {}).get("d1_fix_at") if (cached or {}).get("d1_fixed_till") == fixed else None
    try:
        last = date.fromisoformat(max(fixed, fin)) + timedelta(days=4)
        first = min([date.fromisoformat(fixed) + timedelta(days=1)]
                    + [date.fromisoformat(d) for e in (still or {}).values() for d in e.get("days") or ()])
        first = max(first, last - timedelta(days=D0_FIX_AT_DAYS - 1))
        return {(first + timedelta(days=i)).isoformat():
                _iso_z(_d0_moment(zones, first + timedelta(days=i), int(lag)))
                for i in range((last - first).days + 1)}
    except (TypeError, ValueError):
        return None


def _d0_log(fresh, fixed, n, still=None):
    """The public runner's line: dates and counts only (no amount, no percentage, no app / store / account)."""
    why = "" if fresh.get("d1_ok") else " (day-1 read incomplete: not moved)"
    k = sum(len(e.get("days") or ()) for e in (still or {}).values())
    more = " · %d store-days still open" % k if k else ""
    print("roas: D0 fixed till %s · %d store-days fixed this run%s%s" % (fixed or "none", n, more, why),
          file=sys.stderr)

def resolve_store_ids(accounts, data_dir, catalog, *, client_id, client_secret, currency,
                      make_client, mode):
    """{app_id: store_id} for the ROAS join, cached in data/app_store_ids.json. Lists apps only for
    app_ids not yet resolved (needs admob.readonly; a report-only token yields no store id for that
    account's apps → those apps simply can't be matched to Google Ads spend). Best-effort."""
    import json, os, time
    cache_path = os.path.join(data_dir, "app_store_ids.json")
    cache = {}
    try:
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f) or {}
    except Exception:
        cache = {}
    by_id = cache.setdefault("by_id", {})                # app_id -> store_id ("" = tried, none yet)
    # A blank ("") means we asked once and AdMob had no store listing linked THEN. That can change
    # later (the user links/verifies the Play listing), so blanks must be RE-ASKED — otherwise the
    # app can never match Google Ads spend and shows "organic" forever (real case: Arrow Escape).
    # Throttled so we don't re-list apps every 30-min run when nothing has changed.
    _now = int(time.time())
    _blank_retry_after = int(os.getenv("STORE_ID_BLANK_RETRY_SEC", "21600"))      # 6h
    _due = (_now - int(cache.get("_blank_retry_ts") or 0)) >= _blank_retry_after
    absent = [c.get("app_id") for c in (catalog or [])
              if c.get("app_id") and c.get("app_id") not in by_id]
    blanks = [c.get("app_id") for c in (catalog or [])
              if c.get("app_id") and c.get("app_id") in by_id and not by_id[c.get("app_id")]]
    retry_blanks = blanks if _due else []
    missing = absent + retry_blanks
    if missing:
        store = {}
        for a in accounts:
            try:
                client = make_client(a, mode, client_id, client_secret, currency)
                for app in (client.list_apps() or []):
                    if app.get("app_id"):
                        store[app["app_id"]] = app.get("store_id")
            except Exception as e:
                print("store-ids: list_apps failed for %s: %s" % (a.get("account_id"), e), file=sys.stderr)
        for a in missing:
            _new = store.get(a) or ""
            if _new and not by_id.get(a):
                print("store-ids: resolved %s -> %s (was blank)" % (a, _new), file=sys.stderr)
            by_id[a] = _new
        if retry_blanks:
            cache["_blank_retry_ts"] = _now                 # throttle the next blank re-ask
        try:
            os.makedirs(data_dir, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except Exception as e:
            print("store-ids: cache write failed: %s" % e, file=sys.stderr)
    return {a: s for a, s in by_id.items() if s}


def _mock_spend(start, end):
    """Deterministic demo spend keyed by mock store ids (com.mock.<x>) so the join + ROAS + UI can
    be exercised offline. Includes a PAUSED campaign to prove status handling."""
    from datetime import datetime, timedelta
    d0 = datetime.strptime(str(start), "%Y-%m-%d").date()
    d1 = datetime.strptime(str(end), "%Y-%m-%d").date()
    daily, camps, installs, convval = {}, {}, {}, {}
    for i, sid in enumerate(["com.mock.1", "com.mock.2", "com.mock.3"]):
        dd, ins, cv, day = {}, {}, {}, d0
        while day <= d1:
            dd[day.isoformat()] = (500 + i * 350) * 1_000_000        # $500–1200/day
            ins[day.isoformat()] = 50 + i * 20                       # demo installs/day
            cv[day.isoformat()] = round((500 + i * 350) * 1.3, 2)    # demo conv value ≈ 1.3× spend
            day += timedelta(days=1)
        daily[sid] = dd
        installs[sid] = ins
        convval[sid] = cv
        tot = sum(dd.values())
        camps[sid] = [{"id": "c%d" % i, "name": "App install %d" % (i + 1), "status": "ENABLED",
                       "cost_micros": tot},
                      {"id": "c%dp" % i, "name": "Old campaign %d" % (i + 1), "status": "PAUSED",
                       "cost_micros": 0}]
    return {"v": SPEND_CACHE_V, "daily": daily, "campaigns": camps, "installs": installs,
            "convval": convval, "currency_src": "USD", "fx": {"USD": 1.0}}
