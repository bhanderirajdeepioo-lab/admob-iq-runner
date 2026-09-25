"""GA4 Phase 0 probe — offline (requests mocked): matching, the Android+stream filter on every report,
cohort/realtime request shapes, per-test error capture, and that the PUBLIC log stays aggregate-only."""

import gzip
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from admob_iq.fetch import ga4
from admob_iq import ga4_probe

PKG, NAME, AID = "com.secret.app", "Secret App Name", "ca-app-pub-1111111111111111~2222222222"
PKG2, NAME2, AID2 = "com.roas.pkg", "Roas Only App", "ca-app-pub-1111111111111111~3333333333"
PKG3, AID3 = "com.not.selected", "ca-app-pub-1111111111111111~4444444444"
PID, SID, SID2, SID3 = "987654321", "5550001234", "5550005678", "5550009999"
TOKEN = "tok-SECRET-abc"
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
SECRETS = [PKG, NAME, AID, PKG2, NAME2, AID2, PKG3, PID, SID, SID2, SID3, TOKEN,
           "Wakanda", "9.9.9", "SecretScreen", "SECRETDETAIL", "77777", "424242"]


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body or {}
        self.text = json.dumps(self._b)

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._b


def _fake_rows(body):
    """Plausible rows for whatever dimensions/metrics a runReport body asks for."""
    dims = [d["name"] for d in body.get("dimensions") or []]
    mets = [m["name"] for m in body.get("metrics") or []]
    if "cohortSpec" in body:
        rows = []
        for c in body["cohortSpec"]["cohorts"]:
            for n in range(8):
                rows.append({"dimensionValues": [{"value": c["name"]}, {"value": "%04d" % n}],
                             "metricValues": [{"value": str(100 - 10 * n)}, {"value": "100"}]})
        return dims, mets, rows
    rng = (body.get("dateRanges") or [{}])[0]
    start = datetime.strptime(rng.get("startDate", "2026-09-20"), "%Y-%m-%d")
    end = datetime.strptime(rng.get("endDate", "2026-09-22"), "%Y-%m-%d")
    dates = [(start + timedelta(days=i)).strftime("%Y%m%d") for i in range((end - start).days + 1)]
    ev_filter = [e["filter"] for e in body["dimensionFilter"]["andGroup"]["expressions"]
                 if e["filter"]["fieldName"] == "eventName"]
    events = (ev_filter[0].get("inListFilter", {}).get("values") if ev_filter and "inListFilter" in ev_filter[0]
              else ["app_remove"])
    rows = []
    for d in (dates if "date" in dims else dates[:1]):
        for ev in (events if "eventName" in dims else events[:1]):
            val = {"date": d, "appVersion": "9.9.9", "country": "Wakanda", "eventName": ev,
                   "firstSessionDate": (datetime.strptime(d, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d"),
                   "firstUserGoogleAdsCampaignId": "77777", "unifiedScreenClass": "SecretScreen"}
            rows.append({"dimensionValues": [{"value": val[n]} for n in dims],
                         "metricValues": [{"value": "50" if n == "activeUsers" else "5"} for n in mets]})
    return dims, mets, rows


class FakeGoogle:
    def __init__(self, fail=None, realtime_rows=False):
        self.posts, self.fail, self.realtime_rows = [], fail, realtime_rows

    def get(self, url, headers=None, params=None, timeout=None):
        assert headers["Authorization"] == "Bearer " + TOKEN
        if url.endswith("/accountSummaries"):
            return Resp(body={"accountSummaries": [{"account": "accounts/424242", "propertySummaries": [
                {"property": "properties/" + PID, "displayName": "Secret Prop"}]}]})
        if url.endswith("/dataStreams"):
            return Resp(body={"dataStreams": [
                {"name": "properties/%s/dataStreams/%s" % (PID, SID), "type": "ANDROID_APP_DATA_STREAM",
                 "androidAppStreamData": {"packageName": PKG}},
                {"name": "properties/%s/dataStreams/%s" % (PID, SID2), "type": "ANDROID_APP_DATA_STREAM",
                 "androidAppStreamData": {"packageName": PKG2}},
                {"name": "properties/%s/dataStreams/%s" % (PID, SID3), "type": "ANDROID_APP_DATA_STREAM",
                 "androidAppStreamData": {"packageName": PKG3}},
                {"name": "properties/%s/dataStreams/1" % PID, "type": "ANDROID_APP_DATA_STREAM",
                 "androidAppStreamData": {"packageName": "com.stranger.app"}},
                {"name": "properties/%s/dataStreams/2" % PID, "type": "WEB_DATA_STREAM"}]})
        if url.endswith("/properties/" + PID):
            return Resp(body={"timeZone": "Asia/Kolkata", "currencyCode": "INR"})
        return Resp(404, {"error": {"code": 404, "status": "NOT_FOUND", "message": "?"}})

    def post(self, url, headers=None, json=None, timeout=None):
        self.posts.append((url, json))
        if self.fail and self.fail(json):
            return Resp(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                        "message": "bad field SECRETDETAIL"}})
        if url.endswith(":runRealtimeReport"):
            if not self.realtime_rows:
                return Resp(body={"propertyQuota": {"tokensPerDay": {"consumed": 1}}})
        dims, mets, rows = _fake_rows(json)
        return Resp(body={"dimensionHeaders": [{"name": n} for n in dims],
                          "metricHeaders": [{"name": n} for n in mets], "rows": rows,
                          "propertyQuota": {"tokensPerDay": {"consumed": 7, "remaining": 199993}}})


@pytest.fixture
def private(tmp_path):
    root = tmp_path / "_private"
    (root / "data").mkdir(parents=True)
    (root / "site").mkdir()
    (root / "data" / "app_store_ids.json").write_text(json.dumps({"by_id": {AID: PKG, AID3: PKG3}}))
    dash = {"apps_catalog": [
        {"app_id": AID, "app_name": NAME, "account_id": "pub-1", "selected": True},
        {"app_id": AID2, "app_name": NAME2, "account_id": "pub-1", "selected": True},   # package via ROAS only
        {"app_id": AID3, "app_name": "Hidden", "account_id": "pub-1", "selected": False},
        {"app_id": "ca-app-pub-1~5", "app_name": "No Package", "account_id": "pub-1", "selected": True}],
        "roas": {"by_app": {NAME2: {"store_id": PKG2}}}}
    with gzip.open(root / "site" / "dashboard.json.gz", "wt", encoding="utf-8") as f:
        json.dump(dash, f)
    return root


@pytest.fixture
def google(monkeypatch):
    fake = FakeGoogle()
    monkeypatch.setattr(ga4.requests, "get", fake.get)
    monkeypatch.setattr(ga4.requests, "post", fake.post)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda *a: TOKEN)
    return fake


def _env(private, **kw):
    return dict({"PRIVATE_DIR": str(private), "GOOGLE_CLIENT_ID": "cid", "GOOGLE_CLIENT_SECRET": "sec",
                 "GA4_REFRESH_TOKEN": "rt"}, **kw)


def test_catalog_matches_by_package_with_roas_fallback(private):
    by_pkg, pkg_of, selected = ga4_probe.load_catalog(str(private))
    assert by_pkg[PKG]["app_id"] == AID and by_pkg[PKG]["selected"]
    assert by_pkg[PKG2]["app_id"] == AID2                 # store_id from roas.by_app[name]
    assert not by_pkg[PKG3]["selected"]
    streams = [{"property_id": PID, "stream_id": s, "package": p}
               for s, p in ((SID, PKG), (SID2, PKG2), (SID3, PKG3), ("1", "com.stranger"), ("9", PKG))]
    matched, n = ga4_probe.match_streams(streams, by_pkg)
    assert [a["app_id"] for _, a in matched] == [AID, AID2]
    assert n == {"unmatched_streams": 1, "matched_not_selected": 1, "duplicate_package_streams": 1}


# Every request the probe makes, keyed by (endpoint, dimensions, metrics) → the eventName filter it
# MUST carry: "app_remove" (exact), a tuple (inList) or None (no event filter). A new or changed call
# fails here until it is listed, so an uninstall query can't silently lose its app_remove filter.
REPORT, RT = "runReport", "runRealtimeReport"
EXPECTED_EVENT = {
    (REPORT, ("date",), ("activeUsers", "newUsers", "sessions")): None,                      # base
    (REPORT, ("date", "appVersion"), ("eventCount", "totalUsers")): "app_remove",           # T1
    (REPORT, ("date", "country"), ("eventCount", "totalUsers")): "app_remove",              # T1
    (REPORT, ("firstUserGoogleAdsCampaignId",), ("totalUsers",)): "app_remove",             # T1b
    (REPORT, ("firstSessionDate", "date"), ("totalUsers",)): "app_remove",                  # T2
    (REPORT, ("cohort", "cohortNthDay"), ("cohortActiveUsers", "cohortTotalUsers")): None,  # T3
    (REPORT, ("date", "appVersion"), ("totalAdRevenue", "publisherAdImpressions")): None,   # T4
    (RT, ("appVersion",), ("eventCount",)): "app_remove",                                   # T5
    (REPORT, ("date",), ("crashAffectedUsers",)): None,                                     # T7
    (REPORT, ("unifiedScreenClass",), ("screenPageViews",)): None,                          # T7
    (REPORT, ("date", "eventName"), ("eventCount",)): ("app_remove", "app_update"),         # T11
    (REPORT, ("eventName",), ("eventCount",)): None,                                        # events
    (REPORT, ("date",), ("activeUsers",)): None,                                            # T12 denominator
    (REPORT, ("date",), ("totalUsers",)): "app_remove",                                     # T12 numerator
}


def _event_filter(body):
    ex = [e["filter"] for e in body["dimensionFilter"]["andGroup"]["expressions"]
          if e["filter"]["fieldName"] == "eventName"]
    assert len(ex) <= 1
    if not ex:
        return None
    return ex[0]["stringFilter"]["value"] if "stringFilter" in ex[0] else tuple(ex[0]["inListFilter"]["values"])


def test_every_report_is_pinned_to_the_apps_android_stream(private, google):
    report, code = ga4_probe.run(_env(private), now=NOW)
    assert code == 0 and set(report["apps"]) == {AID, AID2}
    assert google.posts
    seen = set()
    for url, body in google.posts:
        ex = [e["filter"] for e in body["dimensionFilter"]["andGroup"]["expressions"]]
        f = {e["fieldName"]: e.get("stringFilter", {}).get("value") for e in ex}
        assert f["platform"] == "Android"
        assert f["streamId"] in (SID, SID2)
        assert body["returnPropertyQuota"] is True
        # each call carries exactly the event filter its question needs (app_remove for uninstalls)
        key = (url.rsplit(":", 1)[1], tuple(d["name"] for d in body.get("dimensions") or []),
               tuple(m["name"] for m in body.get("metrics") or []))
        assert key in EXPECTED_EVENT, key
        assert _event_filter(body) == EXPECTED_EVENT[key], key
        seen.add(key)
    assert seen == set(EXPECTED_EVENT)                    # every listed call was actually made
    # both apps' requests are pinned to THEIR stream, never the other one's
    assert {b["dimensionFilter"]["andGroup"]["expressions"][1]["filter"]["stringFilter"]["value"]
            for _, b in google.posts} == {SID, SID2}
    per_app = report["apps"][AID]["report_calls"]
    assert per_app <= 15


def test_report_content_and_derived_tests(private, google):
    report, _ = ga4_probe.run(_env(private), now=NOW)
    t = report["apps"][AID]["tests"]
    for k in ga4_probe.ORDER:
        assert "error" not in t[k], (k, t[k])
    assert t["T9"] == {"ok": True, "time_zone": "Asia/Kolkata", "currency": "INR"}
    assert t["T1"]["distinct_versions"] == 1 and t["T1"]["real_version_row_share"] == 1.0
    assert t["T2"]["users_by_lag"]["d1"] > 0
    assert t["T3"]["d1_retention"] == 0.9 and t["T3"]["d7_retention"] == 0.3
    assert len(t["T11"]["app_remove"]) == 90 and t["T11"]["has_app_update"]
    assert t["T12"]["ok"] and t["T12"]["last7_rate"] == 100.0 and t["T12"]["change_pct_last7_vs_prev7"] == 0.0
    assert t["T13"]["ok"] and t["T13"]["avg_share"] is not None
    assert report["capability"]["T1"] == {"ok": 2, "errors": 0, "of": 2}
    assert report["quota"]["latest"]["tokensPerDay"]["consumed"] == 7
    assert report["discovery"]["selected_without_package"] == 1


def test_cohort_request_has_no_date_ranges_and_runs_to_day_7(private, google):
    ga4_probe.run(_env(private), now=NOW)
    cohort = [b for _, b in google.posts if "cohortSpec" in b]
    assert cohort
    for b in cohort:
        assert "dateRanges" not in b
        spec = b["cohortSpec"]
        assert spec["cohortsRange"] == {"granularity": "DAILY", "startOffset": 0, "endOffset": 7}
        assert len(spec["cohorts"]) == 14
        assert all(c["dimension"] == "firstSessionDate" and c["dateRange"]["startDate"] == c["dateRange"]["endDate"]
                   for c in spec["cohorts"])
        assert spec["cohorts"][-1]["dateRange"]["endDate"] == "2026-09-23"      # today-2 (IST): settled data
        assert [d["name"] for d in b["dimensions"]] == ["cohort", "cohortNthDay"]


def test_t2_only_asks_for_recent_first_sessions_newest_first(private, google):
    ga4_probe.run(_env(private), now=NOW)
    t2 = [b for _, b in google.posts if (b.get("dimensions") or [{}])[0].get("name") == "firstSessionDate"]
    assert t2
    for b in t2:
        fs = [e["filter"] for e in b["dimensionFilter"]["andGroup"]["expressions"]
              if e["filter"]["fieldName"] == "firstSessionDate"]
        vals = fs[0]["inListFilter"]["values"]
        assert len(vals) == 30 and vals[0] == "20260923" and vals[-1] == "20260825"
        assert b["orderBys"] == [{"dimension": {"dimensionName": "firstSessionDate"}, "desc": True}]


def test_truncated_report_is_flagged():
    class Stub(ga4.Ga4App):
        def _post(self, method, body):
            return {"dimensionHeaders": [{"name": "firstSessionDate"}, {"name": "date"}],
                    "metricHeaders": [{"name": "totalUsers"}], "rowCount": 25000,
                    "rows": [{"dimensionValues": [{"value": "20260920"}, {"value": "20260921"}],
                              "metricValues": [{"value": "3"}]}]}
    r = ga4.probe_t2(Stub(TOKEN, PID, SID), datetime(2026, 9, 23).date())
    assert r["truncated"] is True and r["row_count"] == 25000


def test_missing_dimension_value_never_breaks_the_report(tmp_path):
    rows = ga4._rows({"dimensionHeaders": [{"name": "appVersion"}], "metricHeaders": [{"name": "eventCount"}],
                      "rows": [{"dimensionValues": [{}], "metricValues": [{"value": "4"}]},
                               {"dimensionValues": [{"value": "1.0"}], "metricValues": [{"value": "2"}]}]})
    by = ga4._sum_by(rows, "appVersion", "eventCount")
    assert by == {"": 4, "1.0": 2}
    p = tmp_path / "ga4" / "probe.json"
    ga4_probe.write_report({"a": by, "b": {None: 1, "x": 2}}, str(p))      # mixed keys still written
    assert json.loads(p.read_text())["a"] == {"": 4, "1.0": 2}


def test_paging_stops_on_a_repeated_token(monkeypatch):
    calls = []

    def get(url, headers=None, params=None, timeout=None):
        calls.append(1)
        return Resp(body={"accountSummaries": [], "nextPageToken": "same"})
    monkeypatch.setattr(ga4.requests, "get", get)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    info = {}
    assert ga4.list_properties(TOKEN, info) == [] and info["truncated"] is True
    assert len(calls) == 2


def test_ga4_client_is_preferred_over_the_admob_client(private, google, monkeypatch):
    used = []
    monkeypatch.setattr(ga4, "access_token", lambda *a: used.append(a) or TOKEN)
    ga4_probe.run(_env(private, GA4_CLIENT_ID="ga4cid", GA4_CLIENT_SECRET="ga4sec"), now=NOW)
    ga4_probe.run(_env(private), now=NOW)                                   # fallback: AdMob client
    assert used == [("ga4cid", "ga4sec", "rt"), ("cid", "sec", "rt")]


def test_realtime_zero_rows_is_ok(private, google):
    report, _ = ga4_probe.run(_env(private), now=NOW)
    assert report["apps"][AID]["tests"]["T5"] == {"ok": True, "rows": 0, "by_version": {}}
    rt = [b for u, b in google.posts if u.endswith(":runRealtimeReport")]
    assert rt and all("dateRanges" not in b and b["minuteRanges"][0]["startMinutesAgo"] == 29 for b in rt)


def test_a_failing_test_is_recorded_not_raised(private, google):
    google.fail = lambda body: any(d["name"] == "firstUserGoogleAdsCampaignId" for d in body.get("dimensions") or [])
    report, code = ga4_probe.run(_env(private), now=NOW)
    assert code == 0
    t1b = report["apps"][AID]["tests"]["T1b"]
    assert t1b["ok"] is False and "INVALID_ARGUMENT" in t1b["error"]
    assert report["apps"][AID]["tests"]["T1"]["ok"] is True           # the rest still ran
    assert report["capability"]["T1b"] == {"ok": 0, "errors": 2, "of": 2}


def test_retry_once_on_429(monkeypatch):
    calls = []

    def post(url, headers=None, json=None, timeout=None):
        calls.append(1)
        return Resp(429, {"error": {"status": "RESOURCE_EXHAUSTED"}}) if len(calls) == 1 else Resp(body={})
    monkeypatch.setattr(ga4.requests, "post", post)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    assert ga4.Ga4App(TOKEN, PID, SID).report({"dimensions": []}) == []
    assert len(calls) == 2


def test_public_log_is_aggregate_only_and_json_lands_in_ga4(private, google, monkeypatch, capsys):
    google.fail = lambda body: "cohortSpec" in body                  # an error text with SECRETDETAIL
    for k, v in _env(private).items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GA4_PROBE_OUT", raising=False)
    assert ga4_probe.main() == 0
    out = capsys.readouterr()
    log = out.out + out.err
    for s in SECRETS:
        assert s not in log, s
    assert "matched selected apps 2" in log and "T1 ok 2/2" in log and "T3 ok 0/2" in log
    path = private / "ga4" / "probe.json"
    assert path.exists()
    assert not any("probe" in n for n in os.listdir(private / "data"))
    assert not (private / "site" / "probe.json").exists()
    rep = json.loads(path.read_text())
    assert "SECRETDETAIL" in rep["apps"][AID]["tests"]["T3"]["error"]     # detail kept, privately


def test_auth_failure_exits_1_with_a_generic_message(private, monkeypatch, capsys):
    def boom(*a):
        raise RuntimeError("invalid_grant for " + TOKEN)
    monkeypatch.setattr(ga4, "access_token", boom)
    for k, v in _env(private).items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GA4_PROBE_OUT", raising=False)
    assert ga4_probe.main() == 1
    log = capsys.readouterr().out
    assert "stage 'auth'" in log and TOKEN not in log and "invalid_grant" not in log
    assert json.loads((private / "ga4" / "probe.json").read_text())["fatal_stage"] == "auth"


def test_uninstall_rate_change_is_measured():
    """T12: a jump in uninstalls per 1,000 active users shows up as a last-7 vs prev-7 change + spike day."""
    yday = datetime(2026, 9, 24).date()
    keys = [(yday - timedelta(days=i)).strftime("%Y%m%d") for i in range(55, -1, -1)]

    class Stub:
        def report(self, body, event=None, events=None):
            if event == "app_remove":
                return [{"date": k, "totalUsers": (30 if k == keys[-1] else 10 if i >= 49 else 5)}
                        for i, k in enumerate(keys)]
            return [{"date": k, "activeUsers": 1000} for k in keys]
    r = ga4.probe_t12(Stub(), yday)
    assert r["ok"] and r["prev7_rate"] == 5.0 and r["last7_rate"] == pytest.approx(12.857, abs=1e-3)
    assert r["change_pct_last7_vs_prev7"] == pytest.approx(157.1, abs=0.1)
    assert keys[-1] in r["spike_days"] and len(r["weekly_rate_per_1000"]) == 8


def test_pearson():
    assert ga4.pearson([1, 2, 3, 4], [2, 4, 6, 8]) == 1.0
    assert ga4.pearson([1, 1, 1], [1, 2, 3]) is None
