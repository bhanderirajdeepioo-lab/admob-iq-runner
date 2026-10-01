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


_ANDROID_PKG = re.compile(r"^[A-Za-z][\w.]*\.[\w.]+$")
_IOS_ID = re.compile(r"^\d{5,15}$")


def fill_icons_from_store_ids(icons, catalog, store_ids, data_dir, *, resolve=None, now=None,
                              max_lookups=20, retry_after=7 * 86400, budget_s=45.0):
    """Second chance for apps the main pass left without an icon.

    resolve_app_icons() tries each app ONCE, with the store id AdMob listed at that moment, and marks a miss with ""
    for good — so an app first seen before its store listing was linked (a new app; the common case) keeps its
    letter-avatar forever, even after data/app_store_ids.json (re-asked every few hours) learns its package. This pass
    reads the icon from that resolved store id instead, by app_id — never by name, so same-named apps each keep their
    own (or none). Cached per store id in data/store_id_icons.json; a miss is re-tried only after `retry_after` seconds,
    at most `max_lookups` listings are read per build, and the whole pass stops after `budget_s` seconds.

    Returns (icons, counts): a NEW {app_id: url} dict (the input is never changed) and counts only — no ids, names or
    packages. Never raises: any failure leaves the icons as they were."""
    import time
    out = dict(icons or {})
    counts = {"missing": 0, "filled": 0, "looked_up": 0, "found": 0, "unresolved": 0, "waiting": 0, "no_store_id": 0}
    try:
        resolve = resolve or resolve_icon
        now = int(time.time()) if now is None else int(now)
        t0 = time.monotonic()
        path = os.path.join(data_dir, "store_id_icons.json")
        cache = {}
        try:
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    cache = json.load(f) or {}
        except Exception:
            cache = {}
        by_sid = cache.get("by_sid") if isinstance(cache.get("by_sid"), dict) else {}
        cache = {"v": 1, "by_sid": by_sid}
        sids = store_ids if isinstance(store_ids, dict) else {}
        rows = [c for c in (catalog or []) if isinstance(c, dict) and c.get("app_id")]
        rows.sort(key=lambda c: (not c.get("selected"), -(c.get("rev") or 0)))   # the apps on screen first
        changed = False
        for c in rows:
            aid = c["app_id"]
            if out.get(aid):
                continue
            counts["missing"] += 1
            sid = str(sids.get(aid) or "").strip()
            if not (_ANDROID_PKG.match(sid) or _IOS_ID.match(sid)):
                counts["no_store_id"] += 1
                continue
            hit = by_sid.get(sid) if isinstance(by_sid.get(sid), dict) else None
            if hit and hit.get("u"):
                out[aid] = hit["u"]
                counts["filled"] += 1
                continue
            if hit and now - int(hit.get("t") or 0) < retry_after:
                counts["waiting"] += 1                      # tried lately, nothing there — wait before asking again
                continue
            if counts["looked_up"] >= max_lookups or time.monotonic() - t0 > budget_s:
                counts["waiting"] += 1
                continue
            counts["looked_up"] += 1
            try:
                url = resolve(sid, "IOS" if sid.isdigit() else "ANDROID")
            except Exception:
                url = None
            url = url if isinstance(url, str) and re.match(r"^https?://", url) else ""
            by_sid[sid] = {"u": url, "t": now}
            changed = True
            if url:
                out[aid] = url
                counts["found"] += 1
                counts["filled"] += 1
            else:
                counts["unresolved"] += 1
        if changed:
            try:
                os.makedirs(data_dir, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(cache, f)
            except Exception:
                counts["cache_write_failed"] = 1
        return out, counts
    except Exception:
        counts["failed"] = 1
        return dict(icons or {}), counts


def fill_counts_line(counts):
    """The build log line for fill_icons_from_store_ids — counts only."""
    c = counts or {}
    return ("app icons from store ids: %d missing, %d filled (%d new), %d looked up, %d still none, %d waiting, "
            "%d without a store id%s" % (c.get("missing", 0), c.get("filled", 0), c.get("found", 0), c.get("looked_up", 0),
                                         c.get("unresolved", 0), c.get("waiting", 0), c.get("no_store_id", 0),
                                         " (failed)" if c.get("failed") else ""))
