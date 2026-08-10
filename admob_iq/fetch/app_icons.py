"""Resolve each app's REAL store icon (Play Store / App Store) once, cached.

AdMob's accounts.apps.list gives every app's store id (Play package or App Store numeric). From
that we fetch the real icon URL — iOS via the public iTunes lookup API, Android via the Play Store
page's og:image. This is a METADATA lookup, totally separate from the AdMob reporting quota, and it
runs at most once per app (results cached in data/app_icons.json), so it adds no ongoing load.

Everything here is best-effort: any failure (report-only token that can't list apps, an app with no
linked store listing, a network hiccup) just means that app keeps its letter-avatar in the UI.
"""

import json
import os
import re
import sys


def resolve_icon(store_id, platform):
    """Real icon URL for one app, or None. iOS → iTunes lookup; Android → Play Store og:image."""
    if not store_id:
        return None
    from urllib.request import Request, urlopen
    UA = {"User-Agent": "Mozilla/5.0 (compatible; AdMobIQ/1.0)"}
    try:
        is_ios = str(platform).upper().startswith("IOS") or str(store_id).isdigit()
        if is_ios:
            url = "https://itunes.apple.com/lookup?id=%s" % store_id
            with urlopen(Request(url, headers=UA), timeout=8) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            res = data.get("results") or []
            if res:
                r0 = res[0]
                return r0.get("artworkUrl512") or r0.get("artworkUrl100") or r0.get("artworkUrl60")
            return None
        # Android: read the Play Store listing and take its og:image (the app icon).
        url = "https://play.google.com/store/apps/details?id=%s&hl=en&gl=US" % store_id
        with urlopen(Request(url, headers=UA), timeout=8) as r:
            html = r.read().decode("utf-8", "replace")
        m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html) \
            or re.search(r'<meta\s+content="([^"]+)"\s+property="og:image"', html)
        return m.group(1) if m else None
    except Exception:
        return None


def resolve_app_icons(accounts, data_dir, catalog, *, client_id, client_secret, currency,
                      make_client, mode):
    """Return {app_id: icon_url} for every app we could resolve. Cached in data/app_icons.json:
    an app already in the cache (icon found OR previously tried) is never re-fetched, so once the
    first build resolves everything this makes ZERO network calls (not even apps.list)."""
    cache_path = os.path.join(data_dir, "app_icons.json")
    cache = {}
    try:
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f) or {}
    except Exception:
        cache = {}
    by_id = cache.setdefault("by_id", {})          # app_id -> url ("" = tried, none found)

    cat_ids = [c.get("app_id") for c in (catalog or []) if c.get("app_id")]
    missing = [aid for aid in cat_ids if aid not in by_id]   # only apps we've never tried
    if missing:                                             # need a resolve pass → list apps + fetch
        store = {}                                         # app_id -> (store_id, platform) from AdMob
        for a in accounts:
            try:
                client = make_client(a, mode, client_id, client_secret, currency)
                for app in (client.list_apps() or []):
                    if app.get("app_id"):
                        store[app["app_id"]] = (app.get("store_id"), app.get("platform"))
            except Exception as e:
                print("app-icons: list_apps failed for %s: %s" % (a.get("account_id"), e), file=sys.stderr)
        for aid in missing:
            sid, plat = store.get(aid, (None, None))
            by_id[aid] = resolve_icon(sid, plat) or ""     # "" marks 'tried, none' so we don't retry
        try:
            os.makedirs(data_dir, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except Exception as e:
            print("app-icons: cache write failed: %s" % e, file=sys.stderr)

    return {aid: u for aid, u in by_id.items() if u}       # only apps with a real icon
