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
_FX_FALLBACK = {"USD": 1.0, "INR": 0.0119, "EUR": 1.08, "GBP": 1.27, "AUD": 0.66,
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
    """Non-manager client accounts under the MCC (id + currency)."""
    q = ("SELECT customer_client.id, customer_client.currency_code, customer_client.manager "
         "FROM customer_client")
    out = []
    for row in _search(login_customer_id, login_customer_id, dev_token, access_token, q):
        cc = row.get("customerClient") or {}
        if cc.get("manager"):
            continue                                  # skip nested managers
        out.append({"id": str(cc.get("id")), "currency": cc.get("currencyCode") or "USD"})
    return out


def _app_spend_for(customer_id, login_customer_id, dev_token, access_token, start, end):
    """App-campaign cost rows for ONE account over [start,end]. Includes paused/removed campaigns
    (historical cost still counts); status is kept for display."""
    q = ("SELECT campaign.id, campaign.name, campaign.status, "
         "campaign.app_campaign_setting.app_id, metrics.cost_micros, segments.date "
         "FROM campaign WHERE segments.date BETWEEN '%s' AND '%s' "
         "AND campaign.app_campaign_setting.app_id != '' AND metrics.cost_micros > 0" % (start, end))
    out = []
    for row in _search(customer_id, login_customer_id, dev_token, access_token, q):
        camp = row.get("campaign") or {}
        sid = _norm_store(((camp.get("appCampaignSetting") or {}).get("appId")))
        if not sid:
            continue
        out.append({"store_id": sid, "campaign_id": str(camp.get("id")),
                    "name": camp.get("name"), "status": camp.get("status"),
                    "date": (row.get("segments") or {}).get("date"),
                    "cost_micros": int((row.get("metrics") or {}).get("costMicros") or 0)})
    return out


def _app_installs_for(customer_id, login_customer_id, dev_token, access_token, start, end):
    """App-campaign INSTALLS + CONVERSION VALUE for ONE account over [start,end], keyed to the SAME
    store id as spend. Deliberately a SEPARATE query from _app_spend_for so a metric/version problem
    here can never break the (proven) spend pull — the caller runs it best-effort. Installs are
    Google Ads campaign-attributed app installs (NOT the app's total install base). conversions_value
    is the value Google Ads tracks for those conversions (in the account's currency) — with a
    first-day (D0) tROAS setup this IS the first-day value, so value ÷ spend = the Google-Ads ROAS."""
    q = ("SELECT campaign.app_campaign_setting.app_id, "
         "metrics.biddable_app_install_conversions, metrics.conversions_value, segments.date "
         "FROM campaign WHERE segments.date BETWEEN '%s' AND '%s' "
         "AND campaign.app_campaign_setting.app_id != ''" % (start, end))
    out = []
    for row in _search(customer_id, login_customer_id, dev_token, access_token, q):
        camp = row.get("campaign") or {}
        sid = _norm_store(((camp.get("appCampaignSetting") or {}).get("appId")))
        if not sid:
            continue
        m = row.get("metrics") or {}
        out.append({"store_id": sid, "date": (row.get("segments") or {}).get("date"),
                    "installs": float(m.get("biddableAppInstallConversions") or 0),
                    "convval": float(m.get("conversionsValue") or 0)})
    return out


def _fx_to_usd(ccy):
    if ccy == "USD" or not ccy:
        return 1.0
    try:
        import requests
        r = requests.get("https://api.frankfurter.app/latest?from=%s&to=USD" % ccy, timeout=10)
        rate = (r.json().get("rates") or {}).get("USD")
        if rate:
            return float(rate)
    except Exception:
        pass
    return _FX_FALLBACK.get(ccy, 1.0)


def _aggregate(rows, fx_fn=_fx_to_usd):
    """Convert each account's spend to USD and aggregate by store_id → {daily, campaigns}."""
    from collections import defaultdict
    fx = {}
    daily = defaultdict(lambda: defaultdict(int))                 # store_id -> date -> usd_micros
    camps = defaultdict(dict)                                     # store_id -> campaign_id -> agg
    src = None
    for r in rows:
        ccy = r.get("currency") or "USD"; src = src or ccy
        if ccy not in fx:
            fx[ccy] = fx_fn(ccy)
        usd = int(round((r.get("cost_micros") or 0) * fx[ccy]))
        sid = r["store_id"]
        daily[sid][str(r.get("date"))] += usd
        c = camps[sid].setdefault(r["campaign_id"], {"name": None, "status": None, "cost": 0})
        c["name"] = r.get("name") or c["name"]; c["status"] = r.get("status") or c["status"]
        c["cost"] += usd
    return {
        "daily": {sid: dict(dd) for sid, dd in daily.items()},
        "campaigns": {sid: [{"id": cid, "name": c["name"], "status": c["status"],
                             "cost_micros": c["cost"]} for cid, c in cc.items()]
                      for sid, cc in camps.items()},
        "currency_src": src or "USD", "fx": fx,
    }


def _aggregate_installs(rows):
    """Sum campaign-attributed installs by store_id -> date (counts, no currency)."""
    from collections import defaultdict
    daily = defaultdict(lambda: defaultdict(float))
    for r in rows:
        daily[r["store_id"]][str(r.get("date"))] += float(r.get("installs") or 0)
    return {sid: {d: round(v, 2) for d, v in dd.items()} for sid, dd in daily.items()}


def _aggregate_convval(rows, fx_fn=_fx_to_usd):
    """Sum Google Ads conversion VALUE by store_id -> date, converted to USD (value is in the
    account's currency, like spend) so value ÷ USD-spend gives an apples-to-apples ROAS."""
    from collections import defaultdict
    fx = {}
    daily = defaultdict(lambda: defaultdict(float))
    for r in rows:
        ccy = r.get("currency") or "USD"
        if ccy not in fx:
            fx[ccy] = fx_fn(ccy)
        daily[r["store_id"]][str(r.get("date"))] += float(r.get("convval") or 0) * fx[ccy]
    return {sid: {d: round(v, 2) for d, v in dd.items()} for sid, dd in daily.items()}


def fetch_app_spend(s, start, end, *, mode="live"):
    """Return {daily:{store_id:{date:usd_micros}}, campaigns:{store_id:[...]}, currency_src, fx} or
    None when Google Ads isn't configured / a call fails. `s` is config.settings()."""
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
        accounts = _child_accounts(mcc, dev, token) or [{"id": mcc, "currency": "USD"}]
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
    rows, errs = [], []
    for a in accounts:
        try:
            for r in _app_spend_for(a["id"], mcc, dev, token, start, end):
                r["currency"] = a["currency"]; rows.append(r)
        except Exception as e:
            errs.append(str(e)[:220])
    if not rows and errs:
        return {"error": "Spend query fail (%d/%d accounts): %s" % (len(errs), len(accounts), errs[0])}
    if not rows:
        return {"daily": {}, "campaigns": {}, "installs": {}, "convval": {}, "currency_src": "USD",
                "fx": {}, "note": "connected — is window me koi app-campaign spend nahi mila"}
    agg = _aggregate(rows)
    # Installs + conversion value: best-effort + SEPARATE from spend, so a problem here can never
    # break the spend/ROAS numbers above.
    inst_rows = []
    for a in accounts:
        try:
            for r in _app_installs_for(a["id"], mcc, dev, token, start, end):
                r["currency"] = a["currency"]; inst_rows.append(r)
        except Exception as e:
            print("roas: installs/convval skipped for %s: %s" % (a.get("id"), e), file=sys.stderr)
    agg["installs"] = _aggregate_installs(inst_rows)
    agg["convval"] = _aggregate_convval(inst_rows)
    return agg


def merge_spend(cached, fresh, refetch_start):
    """Incremental spend cache. Google Ads restates spend/conversions for a while (~60 days), so we
    only ever re-pull a recent window and keep the SETTLED older history from the cache. `fresh`
    covers [refetch_start, today]; for every store, dates < refetch_start come from `cached`, dates
    >= refetch_start come from `fresh` (so adjustments are captured, old data isn't re-fetched hourly).

    - fresh is None      → Google Ads not configured: no ROAS (never serve stale cache).
    - fresh has 'error'  → transient failure: keep the settled history we already have.
    - cached is None     → first run / full backfill: just use fresh."""
    if fresh is None:
        return None
    if fresh.get("error"):
        return cached or fresh
    if not cached:
        return fresh
    out = {"currency_src": fresh.get("currency_src") or cached.get("currency_src", "USD"),
           "fx": fresh.get("fx") or cached.get("fx", {}), "note": fresh.get("note")}
    for key in ("daily", "installs", "convval"):
        cd = cached.get(key) or {}
        fd = fresh.get(key) or {}
        merged = {}
        for sid in set(cd) | set(fd):
            m = {d: v for d, v in (cd.get(sid) or {}).items() if d < refetch_start}  # settled history
            m.update(fd.get(sid) or {})                                              # fresh recent window
            if m:
                merged[sid] = m
        out[key] = merged
    cc = cached.get("campaigns") or {}
    fc = fresh.get("campaigns") or {}
    out["campaigns"] = {sid: (fc.get(sid) or cc.get(sid) or []) for sid in set(cc) | set(fc)}
    return out


def resolve_store_ids(accounts, data_dir, catalog, *, client_id, client_secret, currency,
                      make_client, mode):
    """{app_id: store_id} for the ROAS join, cached in data/app_store_ids.json. Lists apps only for
    app_ids not yet resolved (needs admob.readonly; a report-only token yields no store id for that
    account's apps → those apps simply can't be matched to Google Ads spend). Best-effort."""
    import json, os
    cache_path = os.path.join(data_dir, "app_store_ids.json")
    cache = {}
    try:
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f) or {}
    except Exception:
        cache = {}
    by_id = cache.setdefault("by_id", {})                # app_id -> store_id ("" = tried, none)
    missing = [c.get("app_id") for c in (catalog or [])
               if c.get("app_id") and c.get("app_id") not in by_id]
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
            by_id[a] = store.get(a) or ""
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
    return {"daily": daily, "campaigns": camps, "installs": installs, "convval": convval,
            "currency_src": "USD", "fx": {"USD": 1.0}}
