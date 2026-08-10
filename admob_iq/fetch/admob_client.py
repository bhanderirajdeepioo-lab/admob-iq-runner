"""AdMob API client.

Auth is OAuth user-consent ONLY (AdMob has no service accounts) — the live client
uses a stored refresh token per account. `MockAdMobClient` returns deterministic
synthetic rows so the whole pipeline runs (and is tested) with no creds.

Both clients yield RAW rows (counts + earnings in micros); derived metrics are
computed in fetcher.py so the two clients stay interchangeable.
"""

from datetime import date, timedelta
from typing import Dict, Iterator, List

NETWORK_DIMENSIONS = ["DATE", "APP", "AD_UNIT", "FORMAT", "PLATFORM"]
NETWORK_METRICS = ["AD_REQUESTS", "MATCHED_REQUESTS", "IMPRESSIONS", "CLICKS",
                   "ESTIMATED_EARNINGS", "IMPRESSION_RPM"]
MEDIATION_DIMENSIONS = ["DATE", "APP", "AD_UNIT", "AD_SOURCE", "FORMAT", "PLATFORM"]
MEDIATION_METRICS = ["AD_REQUESTS", "MATCHED_REQUESTS", "IMPRESSIONS", "CLICKS",
                     "ESTIMATED_EARNINGS", "OBSERVED_ECPM"]

# Country view: a SEPARATE, lightweight report by (date, app, country) — small volume
# (~countries × apps × days), fetched from the mediation report so per-country revenue is
# complete (includes third-party sources). Kept out of the granular per-placement report so
# adding geo doesn't multiply that report's rows.
COUNTRY_DIMENSIONS = ["DATE", "APP", "COUNTRY"]
COUNTRY_METRICS = ["AD_REQUESTS", "MATCHED_REQUESTS", "IMPRESSIONS", "CLICKS",
                   "ESTIMATED_EARNINGS"]

# Per-placement × country: NO date dimension (aggregate over the window) keeps volume light
# (~units × active-countries), so we can see each placement's geo mix / where a drop concentrates.
PLACEMENT_COUNTRY_DIMENSIONS = ["APP", "AD_UNIT", "COUNTRY"]
PLACEMENT_COUNTRY_METRICS = ["AD_REQUESTS", "MATCHED_REQUESTS", "IMPRESSIONS", "CLICKS",
                             "ESTIMATED_EARNINGS"]

# Ad-unit × country × DATE: the full cross that powers per-placement, per-geo baselines
# (monthly range/avg of CTR/match/show/eCPM). High cardinality — it rides the safe-fetch
# splitter (date → app), so it stays COMPLETE under the 100k cap.
ADUNIT_COUNTRY_DIMENSIONS = ["DATE", "APP", "AD_UNIT", "COUNTRY"]
ADUNIT_COUNTRY_METRICS = ["AD_REQUESTS", "MATCHED_REQUESTS", "IMPRESSIONS", "CLICKS",
                          "ESTIMATED_EARNINGS"]

SCOPES = ["https://www.googleapis.com/auth/admob.report"]


def _d(dt: date) -> Dict:
    return {"year": dt.year, "month": dt.month, "day": dt.day}


def build_report_spec(start: date, end: date, dimensions: List[str],
                      metrics: List[str], tz: str = None,
                      max_rows: int = 100_000, currency: str = "USD",
                      dim_filters: List[Dict] = None) -> Dict:
    spec = {
        "dateRange": {"startDate": _d(start), "endDate": _d(end)},
        "dimensions": dimensions,
        "metrics": metrics,
        "localizationSettings": {"currencyCode": currency},
        "maxReportRows": max_rows,
    }
    # AdMob only honors the ACCOUNT's own reporting timezone or 'America/Los_Angeles'.
    # Leaving timeZone OUT makes AdMob use the account default — so dates and earnings
    # line up with what the user sees in the AdMob app (e.g. India Standard Time).
    # We set it only when a caller explicitly forces a timezone.
    if tz:
        spec["timeZone"] = tz
    # dim_filters: narrows the report to specific dimension values (e.g. one APP) so a very
    # high-cardinality single day can be split into safe per-app slices instead of truncating.
    if dim_filters:
        spec["dimensionFilters"] = dim_filters
    return {"reportSpec": spec}


def _app_filter(app_id: str) -> Dict:
    """AdMob dimension filter matching exactly one app."""
    return {"dimension": "APP", "matchesAny": {"values": [app_id]}}


class MockAdMobClient:
    """Deterministic synthetic data — mirrors the shape of real parsed rows."""

    APPS = [
        ("app~puzzle", "Puzzle Blast", "ANDROID"),
        ("app~photo", "Photo Editor Pro", "ANDROID"),
    ]
    UNITS = {
        "app~puzzle": [("ca~home_banner", "banner"), ("ca~level_int", "interstitial")],
        "app~photo": [("ca~bottom_banner", "banner"), ("ca~appopen", "app_open")],
    }
    APP_NAMES = {"app~puzzle": "Puzzle Blast", "app~photo": "Photo Editor Pro"}
    UNIT_NAMES = {"ca~home_banner": "Home_Banner", "ca~level_int": "LevelEnd_Interstitial",
                  "ca~bottom_banner": "Bottom_Banner", "ca~appopen": "AppOpen"}
    COUNTRIES = ["US", "IN", "ID"]

    def __init__(self, account_id: str):
        self.account_id = account_id

    def data_start(self, end: date, max_lookback: int = 2555, dim_filters: List[Dict] = None):
        """Mock: pretend this account's history began 100 days before `end`."""
        return end - timedelta(days=100)

    def list_apps(self):
        return [{"app_id": a, "platform": p, "store_id": "com.mock." + a.split("~")[-1],
                 "name": self.APP_NAMES.get(a, a)} for a, _, p in self.APPS]

    def _base(self, unit: str, country: str, day_ix: int) -> Dict:
        seed = (hash(unit + country) % 1000) + 1
        req = 5000 + seed * 3 + day_ix * 10
        matched = int(req * (0.9 if country != "ID" else 0.62))
        impr = int(matched * 0.96)
        clicks = int(impr * 0.008)
        # earnings scale by geo tier
        tier = {"US": 3.2, "IN": 0.34, "ID": 0.22}[country]
        earnings_micros = int(impr * tier / 1000 * 1_000_000)
        return {"ad_requests": req, "matched_requests": matched,
                "impressions": impr, "clicks": clicks,
                "estimated_earnings_micros": earnings_micros}

    def network_report(self, start: date, end: date) -> Iterator[Dict]:
        days = (end - start).days
        for i in range(days + 1):
            d = start + timedelta(days=i)
            for app_id, _, platform in self.APPS:
                for unit, fmt in self.UNITS[app_id]:
                    for country in self.COUNTRIES:
                        raw = self._base(unit, country, i)
                        yield {"report_date": d, "account_id": self.account_id,
                               "app_id": app_id, "app_name": self.APP_NAMES.get(app_id, app_id),
                               "ad_unit_id": unit, "unit_name": self.UNIT_NAMES.get(unit, unit),
                               "country": country, "format": fmt, "platform": platform,
                               "currency_code": "USD", **raw}

    def mediation_report(self, start: date, end: date) -> Iterator[Dict]:
        days = (end - start).days
        for i in range(days + 1):
            d = start + timedelta(days=i)
            for app_id, _, platform in self.APPS:
                for unit, fmt in self.UNITS[app_id]:
                    for country in self.COUNTRIES:
                        for src in ("AdMob Network", "AppLovin"):
                            raw = self._base(unit + src, country, i)
                            raw = {k: v // 2 for k, v in raw.items()}
                            yield {"report_date": d, "account_id": self.account_id,
                                   "app_id": app_id, "app_name": self.APP_NAMES.get(app_id, app_id),
                                   "ad_unit_id": unit, "unit_name": self.UNIT_NAMES.get(unit, unit),
                                   "ad_source": src, "source_name": src, "mediation_group": "",
                                   "country": country, "format": fmt, "platform": platform,
                                   "currency_code": "USD", "observed_ecpm_micros": 3_000_000, **raw}

    def country_report(self, start: date, end: date) -> Iterator[Dict]:
        days = (end - start).days
        for i in range(days + 1):
            d = start + timedelta(days=i)
            for app_id, _, _ in self.APPS:
                for country in self.COUNTRIES:
                    raw = self._base("geo" + app_id, country, i)
                    yield {"report_date": d, "account_id": self.account_id,
                           "app_id": app_id, "app_name": self.APP_NAMES.get(app_id, app_id),
                           "country": country, "currency_code": "USD", **raw}

    def placement_country_report(self, start: date, end: date) -> Iterator[Dict]:
        for app_id, _, _ in self.APPS:
            for unit, fmt in self.UNITS[app_id]:
                for country in self.COUNTRIES:
                    raw = self._base(unit + country, country, 5)
                    yield {"account_id": self.account_id, "app_id": app_id,
                           "app_name": self.APP_NAMES.get(app_id, app_id), "ad_unit_id": unit,
                           "unit_name": self.UNIT_NAMES.get(unit, unit), "country": country,
                           "currency_code": "USD", **raw}

    def adunit_country_report(self, start: date, end: date,
                              dim_filters: List[Dict] = None) -> Iterator[Dict]:
        keep = None                                    # honor an APP scope so tests can verify it
        if dim_filters:
            keep = set()
            for f in dim_filters:
                if f.get("dimension") == "APP":
                    keep.update((f.get("matchesAny") or {}).get("values") or [])
        days = (end - start).days
        for i in range(days + 1):
            d = start + timedelta(days=i)
            for app_id, _, _ in self.APPS:
                if keep is not None and app_id not in keep:
                    continue
                for unit, fmt in self.UNITS[app_id]:
                    for country in self.COUNTRIES:
                        raw = self._base(unit, country, i)
                        yield {"report_date": d, "account_id": self.account_id,
                               "app_id": app_id, "app_name": self.APP_NAMES.get(app_id, app_id),
                               "ad_unit_id": unit, "unit_name": self.UNIT_NAMES.get(unit, unit),
                               "country": country, "currency_code": "USD", **raw}


class AdMobClient:
    """Live client — imports google libs lazily so the module loads without them."""

    def __init__(self, account_id: str, client_id: str, client_secret: str,
                 refresh_token: str, tz: str = None,
                 currency: str = "USD"):
        self.account_id = account_id
        self.tz = tz               # None => use the account's OWN reporting timezone
        self.currency = currency
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._svc = None
        self._meta = None
        self._apps = None
        # Every time a request could NOT be made safe (a single app-day still over the cap),
        # we record it here instead of silently truncating — the build surfaces it so a gap is
        # never invisible. Empty list = every report this run was pulled complete.
        self.truncations = []

    def _service(self):
        if self._svc is None:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            # NO scopes= here on purpose: on refresh the token endpoint then issues an access
            # token with WHATEVER scope the refresh token was granted (admob.report OR
            # admob.readonly — both permit the read/report calls we make). Passing a fixed scope
            # that doesn't match the token's own grant is exactly what raises
            # 'invalid_scope: Bad Request' on refresh (e.g. a readonly-granted token + report scope).
            creds = Credentials(
                token=None, refresh_token=self._refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self._client_id, client_secret=self._client_secret)
            self._svc = build("admob", "v1", credentials=creds, cache_discovery=False)
        return self._svc

    def data_start(self, end: date, max_lookback: int = 2555, dim_filters: List[Dict] = None):
        """Cheapest possible probe of where this account's history BEGINS: a DATE-only report
        over AdMob's max retention (~7yr) returns one tiny row per day that has data, so the
        min date is the true start — no matter how old the app is. The backfill then pulls
        EXACTLY from there (a 3-year app gets 3 years; a new app gets a few days) with no
        guessing and no wasted empty requests. Returns a date, or None if no data.
        dim_filters (optional) scopes the probe to one app, so a per-app backfill starts at
        THAT app's first day (a brand-new app in an old account pulls a few days, not years)."""
        start = end - timedelta(days=max_lookback)
        earliest = None
        for r in self._fetch_range("mediationReport", start, end, ["DATE"], ["ESTIMATED_EARNINGS"],
                                   dim_filters=dim_filters):
            d = r.get("report_date")
            if d and (earliest is None or d < earliest):
                earliest = d
        return earliest

    def account_meta(self) -> Dict:
        """Read the account's OWN reporting timezone + currency (the PublisherAccount
        resource) — exactly what the AdMob app/console uses. Lets the dashboard label
        days in the user's timezone (e.g. India) instead of Pacific. Cached; works with
        the admob.report scope the refresh token already has."""
        if self._meta is None:
            acct = self._service().accounts().get(
                name=f"accounts/{self.account_id}").execute()
            self._meta = {
                "reporting_tz": acct.get("reportingTimeZone") or "America/Los_Angeles",
                "currency": acct.get("currencyCode") or "USD",
            }
        return self._meta

    def list_apps(self) -> List[Dict]:
        """accounts.apps.list → each app's AdMob id + platform + STORE id (Play package / App Store
        numeric) so we can fetch the real store icon. Read-only; needs the admob.readonly scope
        (a report-only token 403s here — the caller treats that as best-effort / no icons). Cached."""
        if self._apps is None:
            out, token = [], None
            while True:
                kw = {"parent": f"accounts/{self.account_id}", "pageSize": 1000}
                if token:
                    kw["pageToken"] = token
                resp = self._service().accounts().apps().list(**kw).execute()
                for app in (resp.get("apps") or []):
                    li = app.get("linkedAppInfo") or {}
                    out.append({"app_id": app.get("appId"), "platform": app.get("platform"),
                                "store_id": li.get("appStoreId"),
                                "name": li.get("displayName") or (app.get("manualAppInfo") or {}).get("displayName")})
                token = resp.get("nextPageToken")
                if not token:
                    break
            self._apps = out
        return self._apps

    MAX_ROWS = 100_000        # AdMob's hard per-report cap; past this a report is silently truncated

    def _run_report(self, method: str, spec: Dict):
        """Execute ONE report call. Returns (parsed_rows, matching_row_count). The footer's
        matchingRowCount is the TRUE number of rows AdMob has for this query — if it exceeds
        the cap the streamed rows are truncated and must not be trusted as complete."""
        parent = f"accounts/{self.account_id}"
        stream = getattr(self._service().accounts(), method)().generate(
            parent=parent, body=spec).execute()
        rows, mrc = [], 0
        for msg in stream:
            row = msg.get("row")
            if row:
                rows.append(self._parse(row))
            elif "footer" in msg:
                mrc = int((msg.get("footer") or {}).get("matchingRowCount") or 0)
        return rows, mrc

    def _fetch_range(self, method: str, start: date, end: date,
                     dimensions: List[str], metrics: List[str],
                     dim_filters: List[Dict] = None) -> Iterator[Dict]:
        """Yield COMPLETE rows for [start, end], guaranteeing nothing is lost to AdMob's
        100k-row cap. The footer's matchingRowCount is the TRUE row count (even when the
        streamed rows are truncated), so we ALWAYS know when a request overflowed.

        Splitting ladder — each step shrinks the request until it fits under the cap:
          1. If it fits (mrc <= cap): yield the rows. Done.
          2. Multi-day window over cap: halve the DATE range and recurse on each half.
          3. Single day STILL over cap: split by APP — pull that day one app at a time
             (a report already scoped to one app is far smaller). This is what lets a
             very high-cardinality report (e.g. ad_unit x country) stay complete.
          4. One app-day still over cap (essentially impossible for a real account):
             record it in self.truncations so the build surfaces the gap LOUDLY, and
             yield what we have — never a silent partial.
        AdMob allows ~900 report reads/minute, so the extra splits are effectively free."""
        import sys
        spec = build_report_spec(start, end, dimensions, metrics, self.tz,
                                 max_rows=self.MAX_ROWS, currency=self.currency,
                                 dim_filters=dim_filters)
        rows, mrc = self._run_report(method, spec)
        # Truncation signal: AdMob CAPS matchingRowCount at maxReportRows, so mrc alone hides an
        # overflow (that silently truncated the ad_unit×country report to only the alphabetically
        # first countries). The reliable tell is that we got back the CAP number of rows — if a
        # request returns exactly MAX_ROWS, there are almost certainly more, so split.
        over_cap = mrc > self.MAX_ROWS or len(rows) >= self.MAX_ROWS
        if not over_cap:
            yield from rows
            return
        # over the cap → split. Prefer date (keeps every dimension intact).
        if start < end:
            mid = start + (end - start) // 2
            print(f"split {method} {start}..{end}: {len(rows)} rows hit {self.MAX_ROWS} cap → "
                  f"[{start}..{mid}] + [{mid + timedelta(days=1)}..{end}]", file=sys.stderr)
            yield from self._fetch_range(method, start, mid, dimensions, metrics, dim_filters)
            yield from self._fetch_range(method, mid + timedelta(days=1), end, dimensions, metrics, dim_filters)
            return
        # single day over the cap → split by APP (unless already scoped to one app / no APP dim)
        if "APP" in dimensions and not dim_filters:
            app_ids = self._app_ids_for(method, start, metrics)
            if len(app_ids) > 1:
                print(f"split {method} {start}: hit cap in ONE day → per-app "
                      f"({len(app_ids)} apps)", file=sys.stderr)
                for aid in app_ids:
                    yield from self._fetch_range(method, start, end, dimensions, metrics,
                                                 dim_filters=[_app_filter(aid)])
                return
        # cannot split further — record the gap so it is NEVER invisible, then yield partial.
        self.truncations.append({"method": method, "date": str(start),
                                 "app_filter": (dim_filters or [{}])[0].get("matchesAny", {}).get("values"),
                                 "rows": len(rows), "matching_row_count": mrc, "cap": self.MAX_ROWS})
        print(f"CRITICAL: {method} {start} hit the {self.MAX_ROWS}-row cap even scoped to one app — "
              f"cannot split further; this slice is INCOMPLETE (recorded in truncations).",
              file=sys.stderr)
        yield from rows

    def _app_ids_for(self, method: str, day: date, metrics: List[str]) -> List[str]:
        """Cheap helper: list the APP ids that have data on `day` (a tiny APP-only report),
        so a single over-cap day can be re-pulled one app at a time."""
        spec = build_report_spec(day, day, ["APP"], metrics[:1] or ["IMPRESSIONS"],
                                 self.tz, max_rows=self.MAX_ROWS, currency=self.currency)
        rows, _ = self._run_report(method, spec)
        seen, out = set(), []
        for r in rows:
            a = r.get("app_id")
            if a and a not in seen:
                seen.add(a)
                out.append(a)
        return out

    @staticmethod
    def _parse(row: Dict) -> Dict:
        dvf = row.get("dimensionValues", {})
        dv = {k: v.get("value") for k, v in dvf.items()}

        def label(dim):
            """Friendly name AdMob returns for a dimension (real app / ad-unit
            names like 'iStrom Gallery' / 'Home_Banner'), falling back to the id."""
            e = dvf.get(dim, {})
            return e.get("displayLabel") or e.get("value")
        mv = row.get("metricValues", {})

        def m(key):
            # AdMob sends numbers as STRINGS under exactly one of these keys. Check by
            # presence (not truthiness), and coerce doubles via float first so a
            # decimal value never raises ValueError and a real 0.0 isn't skipped.
            v = mv.get(key) or {}          # tolerate a literal null value
            if not isinstance(v, dict):
                return 0
            if "integerValue" in v:
                return int(v["integerValue"])
            if "microsValue" in v:
                return int(v["microsValue"])
            if "doubleValue" in v:
                return int(float(v["doubleValue"]))
            return 0
        d = dv.get("DATE", "")
        rd = date(int(d[0:4]), int(d[4:6]), int(d[6:8])) if len(d) == 8 else None
        return {"report_date": rd, "app_id": dv.get("APP"), "app_name": label("APP"),
                "ad_unit_id": dv.get("AD_UNIT"), "unit_name": label("AD_UNIT"),
                "ad_source": dv.get("AD_SOURCE"), "source_name": label("AD_SOURCE"),
                "country": dv.get("COUNTRY") or "All", "format": dv.get("FORMAT"),
                "platform": dv.get("PLATFORM"),
                "ad_requests": m("AD_REQUESTS"), "matched_requests": m("MATCHED_REQUESTS"),
                "impressions": m("IMPRESSIONS"), "clicks": m("CLICKS"),
                "estimated_earnings_micros": m("ESTIMATED_EARNINGS"),
                "impression_rpm_micros": m("IMPRESSION_RPM"),
                "observed_ecpm_micros": m("OBSERVED_ECPM")}

    def network_report(self, start: date, end: date) -> Iterator[Dict]:
        for r in self._fetch_range("networkReport", start, end,
                                   NETWORK_DIMENSIONS, NETWORK_METRICS):
            r["account_id"] = self.account_id
            r["currency_code"] = self.currency
            yield r

    def mediation_report(self, start: date, end: date) -> Iterator[Dict]:
        for r in self._fetch_range("mediationReport", start, end,
                                   MEDIATION_DIMENSIONS, MEDIATION_METRICS):
            r["account_id"] = self.account_id
            r["currency_code"] = self.currency
            yield r

    def country_report(self, start: date, end: date) -> Iterator[Dict]:
        """Per (date, app, country) totals from the mediation report — complete per-country
        revenue (all ad sources). Small volume, and chunked, so it never truncates."""
        for r in self._fetch_range("mediationReport", start, end,
                                   COUNTRY_DIMENSIONS, COUNTRY_METRICS):
            r["account_id"] = self.account_id
            r["currency_code"] = self.currency
            yield r

    def placement_country_report(self, start: date, end: date) -> Iterator[Dict]:
        """Per (app, ad_unit, country) totals over [start, end] — the geo mix of each
        placement. Aggregate (no DATE) so it stays small; chunked so it never truncates."""
        for r in self._fetch_range("mediationReport", start, end,
                                   PLACEMENT_COUNTRY_DIMENSIONS, PLACEMENT_COUNTRY_METRICS):
            r["account_id"] = self.account_id
            r["currency_code"] = self.currency
            yield r

    def adunit_country_report(self, start: date, end: date,
                              dim_filters: List[Dict] = None) -> Iterator[Dict]:
        """Per (date, app, ad_unit, country) DAILY — the granular source for per-placement,
        per-geo baselines. From the mediation report (per-country revenue complete across all
        ad sources), and safe-fetch splits it so the high cardinality never truncates.
        dim_filters (optional) scopes the pull to specific apps — used by the new-account
        backfill so only the user's SELECTED apps are fetched (less AdMob load, respects the pick)."""
        for r in self._fetch_range("mediationReport", start, end,
                                   ADUNIT_COUNTRY_DIMENSIONS, ADUNIT_COUNTRY_METRICS,
                                   dim_filters=dim_filters):
            r["account_id"] = self.account_id
            r["currency_code"] = self.currency
            yield r
