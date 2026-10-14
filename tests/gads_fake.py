"""A synthetic Google Ads MCC for the archive tests (tests/test_gads_archive.py): answers the GAQL the build asks —
the roster, the spend / installs / day-1 / hourly campaign queries, the archive kinds and change_event — with ONLY the
selected fields (as the REST API does), filters what the WHERE filters, and can refuse a field, a kind or an account.
All data is synthetic."""

import re
import threading
from datetime import date, timedelta

MCC, DEV, TOK = "1110001111", "dev-SECRET", "tok-SECRET"
A1, A2, A3, A4, MGR = "2220002221", "2220002222", "2220002223", "2220002224", "2220009999"
S1, S2, S3 = "com.synth.alpha", "com.synth.beta", "com.synth.gamma"
M = 1_000_000
SETTINGS = {"gads_archive": True, "google_ads_dev_token": DEV, "google_ads_login_customer_id": MCC,
            "google_ads_refresh_token": "rt-SECRET", "google_ads_client_id": "cid-SECRET",
            "google_ads_client_secret": "csec-SECRET"}


def camel(p):
    parts = p.split("_")
    return parts[0] + "".join(x[:1].upper() + x[1:] for x in parts[1:])


def project(full, fields):
    """Only the selected GAQL fields of a full REST row."""
    out = {}
    for f in fields:
        parts = [camel(p) for p in f.split(".")]
        cur = full
        for p in parts:
            if not isinstance(cur, dict) or p not in cur:
                cur = None
                break
            cur = cur[p]
        if cur is None:
            continue
        dst = out
        for p in parts[:-1]:
            dst = dst.setdefault(p, {})
        dst[parts[-1]] = cur
    return out


def days(a, b):
    a, b = date.fromisoformat(str(a)), date.fromisoformat(str(b))
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


Q = re.compile(r"^SELECT (.*?) FROM (\w+)(?: WHERE (.*?))?(?: ORDER BY ([\w.]+))?(?: LIMIT (\d+))?$")


class Clock:
    def __init__(self, step=0.2):
        self.t, self.step, self.lock = 0.0, step, threading.Lock()

    def __call__(self):
        return self.t

    def tick(self):
        with self.lock:
            self.t += self.step


def _cost(cid, day, scale):
    """A campaign's synthetic cost on a day (micros; 0 on some days)."""
    o = date.fromisoformat(day).toordinal()
    if (o + int(cid)) % 11 == 0:
        return 0
    return int((scale * M) + ((o * 7919 + int(cid) * 104729) % 997) * 10_007)


class FakeAds:
    """accounts {id: {"ccy", "tz", "status"}}; camps {account: {campaign: {"store", "scale", "status", "row": the full
    REST campaign row (campaign + campaignBudget), optional "lo" / "hi": the campaign's first / last day}}}; res {account: {FROM: [full rows]}}; events {account: [full
    changeEvent rows]}. unknown: GAQL fields answered with UNRECOGNIZED_FIELD; fail(account, kind, query) → an error
    text or None. lo / hi: the metrics' first / last day."""

    def __init__(self, lo="2025-01-01", hi="2026-12-31", clock=None):
        self.accounts = {A1: {"ccy": "INR", "tz": "Asia/Calcutta", "status": "ENABLED"},
                         A2: {"ccy": "INR", "tz": "Asia/Calcutta", "status": "ENABLED"},
                         A3: {"ccy": "INR", "tz": "Asia/Calcutta", "status": "CANCELED"}}
        self.camps = {A1: {"11": self.camp("11", S1, 30), "12": self.camp("12", S1, 9, status="PAUSED")},
                      A2: {"21": self.camp("21", S2, 14)},
                      A3: {"31": self.camp("31", S3, 5)}}
        self.res = {A1: self.extras("11"), A2: self.extras("21"), A3: {}}
        self.events = {A1: [], A2: [], A3: []}
        self.unknown = set()
        self.fail = lambda acct, kind, q: None
        self.lo, self.hi, self.clock = lo, hi, clock
        self.calls, self.lock = [], threading.Lock()
        self.stop_hours = set()                 # (campaign, day, hour) restated to 0
        self.gone = set()                       # accounts answering 403 CUSTOMER_NOT_ENABLED whatever the roster says

    @staticmethod
    def camp(cid, store, scale, status="ENABLED"):
        row = {"campaign": {"id": cid, "name": "SECRET camp %s" % cid, "status": status, "servingStatus": "SERVING",
                            "primaryStatus": "ELIGIBLE", "primaryStatusReasons": ["BIDDING_STRATEGY_LEARNING"],
                            "advertisingChannelType": "MULTI_CHANNEL", "advertisingChannelSubType": "APP_CAMPAIGN",
                            "biddingStrategyType": "TARGET_ROAS", "targetRoas": {"targetRoas": 1.25},
                            "appCampaignSetting": {"appId": store, "appStore": "GOOGLE_APP_STORE",
                                                   "biddingStrategyGoalType": "OPTIMIZE_RETURN_ON_ADVERTISING_SPEND"},
                            "geoTargetTypeSetting": {"positiveGeoTargetType": "PRESENCE_OR_INTEREST"},
                            "startDate": "2025-01-01", "campaignBudget": "customers/1/campaignBudgets/9" + cid},
               "campaignBudget": {"id": "9" + cid, "amountMicros": str(scale * 2 * M), "deliveryMethod": "STANDARD",
                                  "period": "DAILY", "status": "ENABLED"}}
        return {"store": store, "scale": scale, "status": status, "row": row}

    @staticmethod
    def extras(cid):
        c = {"id": cid, "status": "ENABLED"}
        return {
            "customer": [{"customer": {"id": "x", "descriptiveName": "SECRET acct", "currencyCode": "INR",
                                       "timeZone": "Asia/Calcutta", "status": "ENABLED", "autoTaggingEnabled": True}}],
            "campaign_criterion": [
                {"campaign": c, "campaignCriterion": {"criterionId": "2840", "type": "LOCATION", "negative": False,
                                                      "status": "ENABLED",
                                                      "location": {"geoTargetConstant": "geoTargetConstants/2840"}}},
                {"campaign": c, "campaignCriterion": {"criterionId": "2356", "type": "LOCATION", "negative": True,
                                                      "status": "ENABLED",
                                                      "location": {"geoTargetConstant": "geoTargetConstants/2356"}}},
                {"campaign": c, "campaignCriterion": {"criterionId": "1000", "type": "LANGUAGE",
                                                      "language": {"languageConstant": "languageConstants/1000"}}}],
            "ad_group_ad": [{"campaign": c, "adGroupAd": {"ad": {"id": "5%s%d" % (cid, i)}, "status": "ENABLED",
                                                          "policySummary": {"approvalStatus": st,
                                                                            "reviewStatus": "REVIEWED"},
                                                          "primaryStatus": "ELIGIBLE"}}
                            for i, st in enumerate(("APPROVED", "APPROVED", "DISAPPROVED"))],
            "ad_group_ad_asset_view": [{"campaign": c, "adGroupAdAssetView": {
                "enabled": True, "fieldType": ft, "performanceLabel": "GOOD",
                "policySummary": {"approvalStatus": "APPROVED", "reviewStatus": "REVIEWED"}}}
                for ft in ("HEADLINE", "HEADLINE", "MARKETING_IMAGE")],
            "conversion_action": [{"conversionAction": {"id": "71", "status": "ENABLED", "name": "SECRET first_open",
                                                        "category": "DOWNLOAD", "type": "FIREBASE_ANDROID_FIRST_OPEN",
                                                        "countingType": "ONE_PER_CLICK",
                                                        "clickThroughLookbackWindowDays": "30",
                                                        "includeInConversionsMetric": True, "primaryForGoal": True}}],
            "billing_setup": [{"billingSetup": {"id": "81", "status": "APPROVED",
                                                "startDateTime": "2025-01-01 00:00:00",
                                                "paymentsAccount": "customers/1/paymentsAccounts/SECRET"}}],
            "account_budget": [],
            "recommendation_subscription": [{"recommendationSubscription": {"type": "SET_TARGET_ROAS",
                                                                            "status": "ENABLED"}}],
        }

    def add_event(self, acct, t, cid="11", fields="targetRoas.targetRoas", old=1.0, new=1.25, ct="GOOGLE_ADS_WEB_CLIENT"):
        self.events[acct].append({"changeEvent": {
            "changeDateTime": t, "changeResourceType": "CAMPAIGN", "changeResourceName": "customers/1/campaigns/" + cid,
            "clientType": ct, "resourceChangeOperation": "UPDATE", "changedFields": fields,
            "campaign": "customers/1/campaigns/" + cid,
            "oldResource": {"campaign": {"targetRoas": {"targetRoas": old}, "name": "SECRET"}},
            "newResource": {"campaign": {"targetRoas": {"targetRoas": new}, "name": "SECRET"}}}})

    # ── the API ──
    def search(self, customer_id, login, dev, token, query):
        assert (login, dev, token) == (MCC, DEV, TOK), "credentials"
        m = Q.match(query)
        assert m, query
        fields = [f.strip() for f in m.group(1).split(",")]
        frm, where, limit = m.group(2), m.group(3) or "", m.group(5)
        for w in re.findall(r"\b([a-z_]+\.[a-z_.]+)\s*(?:=|!=|>=|<=|IN|BETWEEN|>|<)", where):
            assert w in fields, (w, query)                # every filtered field is selected
        kind = self.kind(frm, fields)
        with self.lock:
            self.calls.append((customer_id, kind, query))
        if self.clock:
            self.clock.tick()
        err = self.fail(customer_id, kind, query)
        if err:
            raise RuntimeError(err)
        if customer_id != MCC and (customer_id in self.gone or
                                   (self.accounts.get(customer_id) or {}).get("status") not in (None, "ENABLED")):
            raise RuntimeError("HTTP 403: authorizationError=CUSTOMER_NOT_ENABLED — SECRET")
        for f in fields:
            if f in self.unknown:
                raise RuntimeError("HTTP 400: queryError=UNRECOGNIZED_FIELD — Unrecognized field in the query: '%s'."
                                   % f)
        rows = self.rows(customer_id, kind, frm, fields, where)
        if limit:
            rows = rows[:int(limit)]
        return [project(r, fields) for r in rows]

    @staticmethod
    def kind(frm, fields):
        if frm == "campaign" and "segments.date" in fields:
            if "segments.hour" in fields:
                return "HOURLY"
            if "segments.conversion_lag_bucket" in fields:
                return "D1"
            if "metrics.biddable_app_install_conversions" in fields:
                return "INST"
            return "SPEND"
        return {"customer_client": "ROSTER", "customer": "cust", "campaign": "camp", "campaign_criterion": "loc",
                "ad_group_ad": "ads", "ad_group_ad_asset_view": "asset", "conversion_action": "conv",
                "billing_setup": "bill", "account_budget": "abud", "recommendation_subscription": "recsub",
                "change_event": "ev"}[frm]

    def rows(self, acct, kind, frm, fields, where):
        if kind == "ROSTER":
            assert acct == MCC
            out = [{"customerClient": {"id": a, "currencyCode": v["ccy"], "timeZone": v["tz"], "status": v["status"],
                                       "manager": False}} for a, v in sorted(self.accounts.items())]
            return out + [{"customerClient": {"id": MGR, "manager": True}}]
        if kind == "camp":
            return [c["row"] for _, c in sorted(self.camps.get(acct, {}).items()) if c["status"] != "REMOVED"]
        if kind == "ev":
            lo, hi = re.search(r">= '([^']+)' AND change_event.change_date_time <= '([^']+)'", where).groups()
            evs = [e for e in self.events.get(acct, []) if lo <= e["changeEvent"]["changeDateTime"] <= hi]
            return sorted(evs, key=lambda e: e["changeEvent"]["changeDateTime"])
        if kind in ("SPEND", "INST", "D1", "HOURLY"):
            a, b = re.search(r"BETWEEN '([\d-]+)' AND '([\d-]+)'", where).groups()
            return self.metric_rows(acct, kind, a, b)
        return list((self.res.get(acct) or {}).get(frm) or [])

    def metric_rows(self, acct, kind, a, b):
        out = []
        for cid, c in sorted(self.camps.get(acct, {}).items()):
            base = {"id": cid, "name": "SECRET camp", "status": c["status"],
                    "appCampaignSetting": {"appId": c["store"]}}
            for dd in days(max(a, self.lo, c.get("lo") or a), min(b, self.hi, c.get("hi") or b)):
                cost = _cost(cid, dd, c["scale"])
                inst = round(cost / M / 40, 2)
                cv = round(cost / M * 1.1, 4)
                cv1 = round(cv * 0.6, 4)
                if kind == "SPEND" and cost:
                    out.append({"campaign": base, "metrics": {"costMicros": str(cost)}, "segments": {"date": dd}})
                elif kind == "INST" and (cost or inst):
                    out.append({"campaign": base, "segments": {"date": dd},
                                "metrics": {"biddableAppInstallConversions": inst, "conversionsValue": cv}})
                elif kind == "D1" and cost:
                    out.append({"campaign": base, "segments": {"date": dd, "conversionLagBucket": "LESS_THAN_ONE_DAY"},
                                "metrics": {"conversionsValue": cv1}})
                    out.append({"campaign": base, "segments": {"date": dd, "conversionLagBucket": "ONE_TO_TWO_DAYS"},
                                "metrics": {"conversionsValue": round(cv - cv1, 4)}})
                elif kind == "HOURLY" and cost:
                    left = cost
                    for h in range(24):
                        v = cost * (h % 5 + 1) // 72 if h < 23 else left
                        left -= v if h < 23 else 0
                        if (cid, dd, h) in self.stop_hours:
                            continue
                        if v:
                            out.append({"campaign": base, "segments": {"date": dd, "hour": h},
                                        "metrics": {"costMicros": str(v)}})
        return out

    def n(self, kind=None, acct=None):
        return sum(1 for c, k, _ in self.calls if (kind is None or k == kind) and (acct is None or c == acct))
