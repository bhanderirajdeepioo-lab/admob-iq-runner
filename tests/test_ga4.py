"""GA4 Phase 0 probe — offline (requests mocked): matching, the Android+stream filter on every report,
cohort/realtime request shapes, per-test error capture, multi-owner tokens (discovery merge, per-property
token routing, the auth exchange's token map), T13 cohort uninstall churn, coverage lists, and that the
PUBLIC log stays aggregate-only."""

import base64
import gzip
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_auth_exchange as gx
from admob_iq import ga4_probe

PKG, NAME, AID = "com.secret.app", "Secret App Name", "ca-app-pub-1111111111111111~2222222222"
PKG2, NAME2, AID2 = "com.roas.pkg", "Roas Only App", "ca-app-pub-1111111111111111~3333333333"
PKG3, AID3 = "com.not.selected", "ca-app-pub-1111111111111111~4444444444"
PKG4, NAME4, AID4 = "com.no.stream", "No Stream App", "ca-app-pub-1111111111111111~6666666666"
PID, SID, SID2, SID3 = "987654321", "5550001234", "5550005678", "5550009999"
PID_B, SID_B = "123123123", "5550007777"
TOKEN = "tok-SECRET-abc"
EMAIL_A, EMAIL_B, EMAIL_C = "owner.a@secret-ws.test", "owner.b@secret-ws.test", "owner.c@secret-ws.test"
RT_A, RT_B, RT_C = "rt-SECRET-owner-a", "rt-SECRET-owner-b", "rt-SECRET-owner-c"
TOK_A, TOK_B = "tok-SECRET-a", "tok-SECRET-b"
EMAIL_R, RT_R = "a.revoked@secret-ws.test", "rt-SECRET-owner-r"     # sorts FIRST, and its token is revoked
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
SECRETS = [PKG, NAME, AID, PKG2, NAME2, AID2, PKG3, PKG4, NAME4, AID4, PID, SID, SID2, SID3, PID_B, SID_B, TOKEN,
           EMAIL_A, EMAIL_B, EMAIL_C, EMAIL_R, RT_A, RT_B, RT_C, RT_R, TOK_A, TOK_B, "secret-ws", "com.stranger.app",
           "Secret Prop", "Wakanda", "9.9.9", "SecretScreen", "SECRETDETAIL", "77777", "424242"]


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body or {}
        self.text = json.dumps(self._b)
        self.headers = {"content-type": "application/json"}

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
    (root / "data" / "app_store_ids.json").write_text(json.dumps({"by_id": {AID: PKG, AID3: PKG3, AID4: PKG4}}))
    dash = {"apps_catalog": [
        {"app_id": AID, "app_name": NAME, "account_id": "pub-1", "selected": True},
        {"app_id": AID2, "app_name": NAME2, "account_id": "pub-1", "selected": True},   # package via ROAS only
        {"app_id": AID3, "app_name": "Hidden", "account_id": "pub-1", "selected": False},
        {"app_id": AID4, "app_name": NAME4, "account_id": "pub-1", "selected": True},   # no GA4 stream anywhere
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
    (REPORT, ("firstSessionDate", "date"), ("totalUsers",)): "app_remove",                  # T2, T13 numerator
    (REPORT, ("cohort", "cohortNthDay"), ("cohortActiveUsers", "cohortTotalUsers")): None,  # T3
    (REPORT, ("date", "appVersion"), ("totalAdRevenue", "publisherAdImpressions")): None,   # T4
    (RT, ("appVersion",), ("eventCount",)): "app_remove",                                   # T5
    (REPORT, ("date",), ("crashAffectedUsers",)): None,                                     # T7
    (REPORT, ("unifiedScreenClass",), ("screenPageViews",)): None,                          # T7
    (REPORT, ("date", "eventName"), ("eventCount",)): ("app_remove", "app_update"),         # T11
    (REPORT, ("eventName",), ("eventCount",)): None,                                        # events
    (REPORT, ("date",), ("activeUsers",)): None,                                            # T12 denominator
    (REPORT, ("date",), ("totalUsers",)): "app_remove",                                     # T12 numerator
    (REPORT, ("date",), ("newUsers",)): None,                                               # T13 denominator
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
    assert per_app <= 17


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
    # fake data: 5 new users a day, 5 of each day's cohort uninstall on day 1 (the oldest row's cohort
    # starts before the window → no cohort size → counted as unplaced, not guessed)
    assert t["T13"]["ok"] and t["T13"]["by_day"]["D1"]["rate"] == 1.0 and t["T13"]["by_day"]["D60"]["cohorts"] == 60
    assert t["T13"]["unplaced_uninstall_users"] == 5 and t["T13"]["truncated"] is False
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


def test_t2_and_t13_only_ask_for_first_sessions_in_their_window_newest_first(private, google):
    ga4_probe.run(_env(private), now=NOW)
    by_window = {}
    for _, b in google.posts:
        if (b.get("dimensions") or [{}])[0].get("name") != "firstSessionDate":
            continue
        fs = [e["filter"] for e in b["dimensionFilter"]["andGroup"]["expressions"]
              if e["filter"]["fieldName"] == "firstSessionDate"]
        vals = fs[0]["inListFilter"]["values"]
        by_window.setdefault(len(vals), []).append((vals, b))
    assert set(by_window) == {30, 120}                                      # T2: 30 cohorts, T13: 120
    for vals, b in by_window[30]:
        assert vals[0] == "20260923" and vals[-1] == "20260825"
        assert b["orderBys"] == [{"dimension": {"dimensionName": "firstSessionDate"}, "desc": True}]
    for vals, b in by_window[120]:
        assert vals[0] == "20260923" and vals[-1] == "20260527"
        assert b["dateRanges"] == [{"startDate": "2026-05-27", "endDate": "2026-09-23"}]
        assert b["orderBys"][0] == {"dimension": {"dimensionName": "firstSessionDate"}, "desc": True}
        assert b["offset"] == 0 and b["limit"] == ga4.PAGE_ROWS                # paged, never one capped call


def test_every_paged_report_asks_for_a_total_order(private, google):
    """Offset paging is only exact when every page sorts the same way: ties left to the API could repeat
    or skip a row between pages while rowCount stays right — a silent miscount."""
    ga4_probe.run(_env(private), now=NOW)
    paged = [b for _, b in google.posts if "offset" in b]
    assert {tuple(d["name"] for d in b["dimensions"]) for b in paged} == {
        ("date", "appVersion"), ("date", "country"), ("firstUserGoogleAdsCampaignId",),        # T1, T4, T1b
        ("firstSessionDate", "date"), ("date",)}                                               # T13
    for b in paged:
        assert {o["dimension"]["dimensionName"] for o in b["orderBys"]} == {d["name"] for d in b["dimensions"]}

    class Stub(ga4.Ga4App):
        def _post(self, method, body):
            self.body = body
            return {"rowCount": 0}
    ga = Stub(TOKEN, PID, SID)
    by_count = {"metric": {"metricName": "eventCount"}, "desc": True}
    ga.report_all({"dimensions": ga4._dim("date", "appVersion"), "metrics": ga4._dim("eventCount"),
                   "orderBys": [by_count, {"dimension": {"dimensionName": "date"}, "desc": True}]})
    assert ga.body["orderBys"] == [by_count, {"dimension": {"dimensionName": "date"}, "desc": True},
                                   {"dimension": {"dimensionName": "appVersion"}}]   # the caller's order, then ties


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


# ── several owners: one refresh token per Google account that owns some of the apps' GA4 accounts ──

class OwnersGoogle(FakeGoogle):
    """Owner A sees PID; owner B sees PID too plus PID_B (where PKG2's stream lives); owner C's token is
    revoked. Every call is recorded with the bearer token it carried."""
    SEES = {TOK_A: [PID], TOK_B: [PID, PID_B]}
    STREAMS = {PID: [(SID, PKG), (SID3, PKG3), ("1", "com.stranger.app")], PID_B: [(SID_B, PKG2)]}

    def __init__(self):
        super().__init__()
        self.calls, self.no_streams = [], set()     # (token, property) whose dataStreams call keeps failing

    def get(self, url, headers=None, params=None, timeout=None):
        tok = headers["Authorization"].split(" ", 1)[1]
        self.calls.append((url, tok))
        if url.endswith("/accountSummaries"):
            return Resp(body={"accountSummaries": [{"account": "accounts/424242", "propertySummaries": [
                {"property": "properties/" + p, "displayName": "Secret Prop " + p} for p in self.SEES[tok]]}]})
        pid = url.split("/properties/")[1].split("/")[0]
        assert pid in self.SEES[tok]              # never asks about a property with a token that can't see it
        if url.endswith("/dataStreams") and (tok, pid) in self.no_streams:
            return Resp(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "SECRETDETAIL"}})
        if url.endswith("/dataStreams"):
            return Resp(body={"dataStreams": [
                {"name": "properties/%s/dataStreams/%s" % (pid, s), "type": "ANDROID_APP_DATA_STREAM",
                 "androidAppStreamData": {"packageName": p}} for s, p in self.STREAMS[pid]]})
        return Resp(body={"timeZone": "Asia/Kolkata", "currencyCode": "INR"})

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append((url, headers["Authorization"].split(" ", 1)[1]))
        return super().post(url, headers, json, timeout)


@pytest.fixture
def owners(monkeypatch):
    fake = OwnersGoogle()
    monkeypatch.setattr(ga4.requests, "get", fake.get)
    monkeypatch.setattr(ga4.requests, "post", fake.post)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)

    def access_token(cid, sec, rt):
        if rt in (RT_C, RT_R):
            raise RuntimeError("invalid_grant: Token has been expired or revoked.")
        return {RT_A: TOK_A, RT_B: TOK_B}[rt]
    monkeypatch.setattr(ga4, "access_token", access_token)
    return fake


def _owners_env(private):
    # B's token is ALSO the legacy GA4_REFRESH_TOKEN (what the exchange leaves behind) → used once
    return _env(private, GA4_REFRESH_TOKENS=json.dumps({EMAIL_B: RT_B, EMAIL_C: RT_C, EMAIL_A: RT_A}),
                GA4_REFRESH_TOKEN=RT_B)


def test_token_map_keeps_every_usable_token():
    # a key written twice, one that only differs by spaces, or a blank one: the token is kept, never lost
    raw = '{"a@x": "tokA", "a@x ": "tokE", " ": "tokZ", "b@x": "tokB", "b@x": "tokB2", "c@x": "tokA", "d@x": 5}'
    m, problems = ga4.parse_token_map(raw)
    assert problems == 1                                                  # only the non-token value
    assert m == {"a@x": "tokA", "unlabelled-1": "tokE", "unlabelled-2": "tokZ", "b@x": "tokB",
                 "unlabelled-3": "tokB2", "c@x": "tokA"}
    assert ga4.parse_token_map('{"a@x": "tokA", "unlabelled-1": "tokB", "": "tokC"}')[0] == \
        {"a@x": "tokA", "unlabelled-1": "tokB", "unlabelled-2": "tokC"}   # a generated name never overwrites
    assert ga4.parse_token_map('{"a@x": "tokA", "a@x": "tokA"}') == ({"a@x": "tokA"}, 0)
    assert ga4.parse_token_map('{"a@x": "tokA", "b@x": "tokB",}') == ({}, 1)           # trailing comma
    assert ga4.parse_token_map('["tokA"]') == ({}, 1) and ga4.parse_token_map("  ") == ({}, 0)


def test_owner_tokens_merge_the_map_and_the_legacy_token():
    env = {"GA4_REFRESH_TOKENS": json.dumps({"b@x": "rt1", "a@x": "rt2", "bad@x": 5, "dup@x": "rt1"}),
           "GA4_REFRESH_TOKEN": "rt2"}
    assert ga4_probe.owner_tokens(env) == ([("a@x", "rt2"), ("b@x", "rt1")], 1)
    assert ga4_probe.owner_tokens({"GA4_REFRESH_TOKENS": "{not json", "GA4_REFRESH_TOKEN": "rt"}) == ([("legacy", "rt")], 1)
    assert ga4_probe.owner_tokens({"GA4_REFRESH_TOKENS": json.dumps({"legacy": "old"}), "GA4_REFRESH_TOKEN": "new"}) \
        == ([("legacy", "old"), ("legacy-secret", "new")], 0)
    assert ga4_probe.owner_tokens({}) == ([], 0)


def test_owners_are_merged_by_property_and_each_app_uses_its_owners_token(private, owners):
    report, code = ga4_probe.run(_owners_env(private), now=NOW)
    assert code == 0
    d = report["discovery"]
    assert d["owner_tokens"] == 3 and d["owners_ok"] == 2               # legacy == B's token: read once
    a, b, c = d["owners"]
    assert a == {"owner": EMAIL_A, "ok": True, "properties": 1, "new_properties": 1}
    assert b == {"owner": EMAIL_B, "ok": True, "properties": 2, "new_properties": 1}    # PID already A's
    assert c["owner"] == EMAIL_C and c["ok"] is False and c["stage"] == "auth" and "invalid_grant" in c["error"]
    assert d["properties"] == 2 and d["property_owners"] == {PID: EMAIL_A, PID_B: EMAIL_B}
    assert set(report["apps"]) == {AID, AID2}
    assert report["apps"][AID]["owner"] == EMAIL_A and report["apps"][AID]["property_id"] == PID
    assert report["apps"][AID2]["owner"] == EMAIL_B and report["apps"][AID2]["property_id"] == PID_B
    assert report["apps"][AID2]["tests"]["T13"]["ok"]
    # streams, metadata and every report go out with the token of the owner that holds the property
    routed = {}
    for url, tok in owners.calls:
        if "/properties/" in url:
            routed.setdefault(url.split("/properties/")[1].split("/")[0].split(":")[0], set()).add(tok)
    assert routed == {PID: {TOK_A}, PID_B: {TOK_B}}
    assert sum(1 for u, _ in owners.calls if u.endswith("/dataStreams")) == 2      # PID listed once, not per owner


def test_every_owner_failing_is_fatal_and_says_where(private, owners, monkeypatch):
    env = _env(private, GA4_REFRESH_TOKENS=json.dumps({EMAIL_C: RT_C}), GA4_REFRESH_TOKEN="")
    report, code = ga4_probe.run(env, now=NOW)
    assert code == 1 and report["fatal_stage"] == "auth"
    assert report["discovery"]["owners"][0]["stage"] == "auth"

    def no_listing(token, info=None):
        raise RuntimeError("HTTP 403: PERMISSION_DENIED")
    monkeypatch.setattr(ga4, "list_properties", no_listing)
    env["GA4_REFRESH_TOKENS"] = json.dumps({EMAIL_A: RT_A, EMAIL_C: RT_C})
    report, code = ga4_probe.run(env, now=NOW)
    assert code == 1 and report["fatal_stage"] == "discovery"          # one token worked, its listing didn't
    report, code = ga4_probe.run(_env(private, GA4_REFRESH_TOKEN=""), now=NOW)
    assert code == 1 and report["fatal_stage"] == "credentials"


def test_a_failing_owner_never_costs_the_owners_after_it(private, owners, monkeypatch):
    # R's token is revoked and R sorts FIRST (C, revoked too, sorts last): A and B must still be read in full
    env = _env(private, GA4_REFRESH_TOKENS=json.dumps({EMAIL_R: RT_R, EMAIL_A: RT_A, EMAIL_B: RT_B, EMAIL_C: RT_C}),
               GA4_REFRESH_TOKEN="")
    report, code = ga4_probe.run(env, now=NOW)
    d = report["discovery"]
    assert code == 0 and d["owners"][0]["owner"] == EMAIL_R and d["owners"][0]["stage"] == "auth"
    assert (d["owner_tokens"], d["owners_ok"], d["properties"]) == (4, 2, 2)
    assert set(report["apps"]) == {AID, AID2} and d["property_owners"] == {PID: EMAIL_A, PID_B: EMAIL_B}
    # A's property listing fails; B, after it, still counts: its properties, apps and owners_ok survive
    real = ga4.list_properties

    def listing(token, info=None):
        if token == TOK_A:
            raise RuntimeError("HTTP 403: PERMISSION_DENIED")
        return real(token, info)
    monkeypatch.setattr(ga4, "list_properties", listing)
    report, code = ga4_probe.run(env, now=NOW)
    d = report["discovery"]
    assert code == 0 and d["owners"][1]["owner"] == EMAIL_A and d["owners"][1]["stage"] == "discovery"
    assert (d["owners_ok"], d["properties"]) == (1, 2) and d["property_owners"] == {PID: EMAIL_B, PID_B: EMAIL_B}
    assert set(report["apps"]) == {AID, AID2} and report["apps"][AID]["owner"] == EMAIL_B


def test_a_failing_stream_list_falls_back_to_the_next_owner_that_sees_the_property(private, owners):
    owners.no_streams.add((TOK_A, PID))          # A holds PID (it sorts first), but its dataStreams call fails
    report, code = ga4_probe.run(_owners_env(private), now=NOW)
    d = report["discovery"]
    assert code == 0 and d["stream_errors"] == {} and list(d["stream_fallbacks"]) == [PID]
    assert EMAIL_A in d["stream_fallbacks"][PID] and "UNAVAILABLE" in d["stream_fallbacks"][PID]
    assert d["property_owners"] == {PID: EMAIL_B, PID_B: EMAIL_B}
    assert set(report["apps"]) == {AID, AID2} and report["apps"][AID]["owner"] == EMAIL_B
    assert report["coverage"]["selected_apps_with_stream"][1]["owner"] == EMAIL_B
    # after its failed stream list, A's token is never used on PID again: metadata + reports go with B's
    later = {tok for url, tok in owners.calls if "/properties/" + PID in url and not url.endswith("/dataStreams")}
    assert later == {TOK_B}
    log = "\n".join(ga4_probe.summary_lines(report))
    assert "stream-list errors 0, stream lists read by a later owner 1" in log
    assert not any(s in log for s in SECRETS)


def test_coverage_never_blames_firebase_for_a_stream_list_that_failed(private, owners):
    owners.no_streams.update({(TOK_A, PID), (TOK_B, PID)})       # no owner can list PID, where PKG's stream is
    report, code = ga4_probe.run(_owners_env(private), now=NOW)
    assert code == 0 and list(report["discovery"]["stream_errors"]) == [PID] and set(report["apps"]) == {AID2}
    why = {a["app_id"]: a["reason"] for a in report["coverage"]["selected_apps_without_stream"]}
    assert set(why) == {AID, AID4, "ca-app-pub-1~5"} and why["ca-app-pub-1~5"] == "no package"
    for aid in (AID, AID4):
        assert why[aid] == ("not in any stream we could list, but the stream list failed for 1 property "
                            "(discovery.stream_errors) and 1 owner(s) could not be read (discovery.owners) "
                            "— it may be there")
    # only a revoked owner (C) and no failed stream list: that gap is named on its own
    owners.no_streams.clear()
    report, _ = ga4_probe.run(_owners_env(private), now=NOW)
    why = {a["app_id"]: a["reason"] for a in report["coverage"]["selected_apps_without_stream"]}
    assert why[AID4] == ("not in any stream we could list, but 1 owner(s) could not be read (discovery.owners) "
                         "— it may be there")


def test_a_crash_after_discovery_never_prints_a_false_zero_owner_count(private, owners, monkeypatch, capsys):
    for k, v in _owners_env(private).items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GA4_PROBE_OUT", raising=False)
    monkeypatch.setattr(ga4_probe, "coverage", lambda *a: 1 / 0)         # a code bug after 2 owners worked
    assert ga4_probe.main() == 1
    log = capsys.readouterr().out
    assert "FAILED at stage 'unexpected'" in log and "owner tokens" not in log
    assert ga4_probe.summary_lines({"fatal_stage": "unexpected", "fatal": "x"}) == [
        "ga4 probe: FAILED at stage 'unexpected' (details in the private report)"]
    # a real credentials failure still reports its (zero) counts
    report, _ = ga4_probe.run(_env(private, GA4_REFRESH_TOKEN=""), now=NOW)
    assert ga4_probe.summary_lines(report)[1] == "ga4 probe: owner tokens 0, working 0"


def test_multi_owner_public_log_is_counts_only(private, owners, monkeypatch, capsys):
    for k, v in _owners_env(private).items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GA4_PROBE_OUT", raising=False)
    assert ga4_probe.main() == 0
    out = capsys.readouterr()
    log = out.out + out.err
    for s in SECRETS:
        assert s not in log, s
    assert "owner tokens 3, working 2" in log and "matched selected apps 2" in log
    assert "selected apps with stream 2, selected apps without stream 1, selected apps without package 1" in log
    rep = json.loads((private / "ga4" / "probe.json").read_text())
    assert rep["discovery"]["owners"][2]["owner"] == EMAIL_C                  # the detail is kept, privately


def test_coverage_lists_are_private_and_match_the_counts(private, google):
    report, _ = ga4_probe.run(_env(private), now=NOW)
    cov = report["coverage"]
    assert cov["selected_apps_with_stream"] == [
        {"app_id": AID2, "app_name": NAME2, "package": PKG2, "property_id": PID, "property_name": "Secret Prop",
         "owner": "legacy", "probed": True},
        {"app_id": AID, "app_name": NAME, "package": PKG, "property_id": PID, "property_name": "Secret Prop",
         "owner": "legacy", "probed": True}]
    assert cov["selected_apps_without_stream"] == [
        {"app_id": "ca-app-pub-1~5", "app_name": "No Package", "package": None, "reason": "no package"},
        {"app_id": AID4, "app_name": NAME4, "package": PKG4, "reason": "no GA4 stream visible to any owner"}]
    assert cov["streams_not_in_our_apps"] == [
        {"package": "com.stranger.app", "property_name": "Secret Prop", "owner": "legacy"}]
    d = report["discovery"]                                              # the public counts are these lengths
    assert (d["selected_with_stream"], d["selected_without_stream"], d["selected_without_package"],
            d["unmatched_streams"]) == (2, 1, 1, 1)


# ── the auth exchange: each consent adds / replaces ONE owner in GA4_REFRESH_TOKENS ─────────────────

def _id_token(email):
    claims = {"email": email} if email else {}
    return "hdr." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=") + ".sig"


@pytest.fixture
def exchange(monkeypatch):
    """Runs the exchange with Google + GitHub mocked → (secrets saved, private files written). The token
    endpoint answers the code exchange, and the old token's refresh check with `legacy_reply` (default: it
    works; an exception instance is raised). run.saved / run.posts / run.deleted show what happened."""
    saved, files, posts, deleted = {}, {}, [], []
    monkeypatch.setattr(gx, "save_github_secret", lambda name, value, repo=None, gh_token=None:
                        saved.__setitem__(name, value))
    monkeypatch.setattr(gx, "_put_private_file", lambda path, text, message: files.__setitem__(path, json.loads(text)))
    monkeypatch.setattr(gx, "_delete_secret", lambda name, *a: deleted.append(name))
    monkeypatch.setattr(gx, "ga4_visible_counts", lambda tok: (1, 8))
    for k, v in {"MODE": "exchange", "GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "csec", "REPO": "o/r",
                 "DATA_REPO_TOKEN": "gh", "GA4_AUTH_CODE": "code", "REDIRECT_URI": "http://127.0.0.1:8765"}.items():
        monkeypatch.setenv(k, v)
    for k in ("GA4_REFRESH_TOKENS", "GA4_REFRESH_TOKEN"):
        monkeypatch.delenv(k, raising=False)

    def run(email, tokens=None, legacy=None, new="rt-SECRET-new", legacy_reply=None):
        if tokens is not None:
            monkeypatch.setenv("GA4_REFRESH_TOKENS", tokens)
        if legacy is not None:
            monkeypatch.setenv("GA4_REFRESH_TOKEN", legacy)

        def post(url, timeout=None, data=None):
            posts.append(data)
            if data["grant_type"] == "refresh_token":
                if isinstance(legacy_reply, Exception):
                    raise legacy_reply
                return legacy_reply or Resp(body={"access_token": "at-SECRET-legacy"})
            return Resp(body={"refresh_token": new, "access_token": "at-SECRET", "id_token": _id_token(email)})
        monkeypatch.setattr(gx.requests, "post", post)
        gx.main()
        return json.loads(saved["GA4_REFRESH_TOKENS"]), saved, files["ga4/auth_status.json"]
    run.saved, run.posts, run.deleted = saved, posts, deleted
    return run


def test_exchange_adds_the_owner_to_the_existing_map(exchange, capsys):
    m, saved, status = exchange(EMAIL_B, tokens=json.dumps({EMAIL_A: RT_A}))
    assert m == {EMAIL_A: RT_A, EMAIL_B: "rt-SECRET-new"}
    assert saved["GA4_REFRESH_TOKEN"] == "rt-SECRET-new"                 # latest token, back-compat
    assert saved["GA4_CLIENT_ID"] == "cid" and saved["GA4_CLIENT_SECRET"] == "csec"
    assert status["owners"] == [EMAIL_A, EMAIL_B] and status["consented_as"] == EMAIL_B
    assert (status["ok"], status["accounts"], status["properties"]) == (True, 1, 8)
    lines = capsys.readouterr().out.splitlines()
    masked = [l[len("::add-mask::"):] for l in lines if l.startswith("::add-mask::")]
    public = [l for l in lines if not l.startswith("::add-mask::")]
    assert {RT_A, "rt-SECRET-new", "at-SECRET"} <= set(masked)
    assert lines.index("::add-mask::" + RT_A) < lines.index(public[0])  # masked before anything prints
    assert public == ["GA4 token saved: 1 account(s), 8 propert(y/ies) visible; 2 owner token(s) stored"]
    assert not any(e in l for l in public for e in (EMAIL_A, EMAIL_B, "secret-ws"))


def test_exchange_replaces_only_that_owners_token(exchange):
    m, _, status = exchange(EMAIL_B.upper(), tokens=json.dumps({EMAIL_A: RT_A, EMAIL_B: "rt-old"}))
    assert m == {EMAIL_A: RT_A, EMAIL_B: "rt-SECRET-new"} and status["owners"] == [EMAIL_A, EMAIL_B]


def test_exchange_never_wipes_the_map_over_bad_input(exchange, capsys):
    m, _, status = exchange(EMAIL_B, tokens=json.dumps({EMAIL_A: RT_A, "x@y": 5, "z@y": ""}))
    assert m == {EMAIL_A: RT_A, EMAIL_B: "rt-SECRET-new"} and status["token_map_problems"] == 2
    assert "::warning::2 unreadable GA4_REFRESH_TOKENS entr(y/ies) were dropped" in capsys.readouterr().out
    # unreadable as a whole (a trailing comma from a hand edit): saving a fresh map over it would delete
    # every owner's token → stop, save nothing, and don't spend (or delete) the one-time code
    for raw in ('{"%s": "%s", "%s": "%s",}' % (EMAIL_A, RT_A, EMAIL_B, RT_B), '["%s"]' % RT_A, '{"%s": 5}' % EMAIL_A):
        exchange.saved.clear()
        del exchange.posts[:], exchange.deleted[:]
        with pytest.raises(SystemExit) as e:
            exchange(EMAIL_C, tokens=raw, legacy=RT_B)
        assert e.value.code == "GA4_REFRESH_TOKENS is set but unreadable — fix or delete it, then run the exchange again"
        assert (exchange.saved, exchange.posts, exchange.deleted) == ({}, [], [])


def test_exchange_keeps_the_legacy_token_and_names_an_unknown_owner(exchange):
    m, _, status = exchange("", legacy=RT_A)                            # first multi-owner run, no email claim
    unknown = [k for k in m if k.startswith("unknown-")]
    assert m["legacy"] == RT_A and len(unknown) == 1 and m[unknown[0]] == "rt-SECRET-new"
    assert status["owners"] == sorted(m)
    m, _, _ = exchange(EMAIL_B, tokens=json.dumps({EMAIL_A: RT_A}), legacy=RT_A)
    assert m == {EMAIL_A: RT_A, EMAIL_B: "rt-SECRET-new"}                # legacy already in the map: no copy
    assert gx.merge_owner_token({"legacy": "rt-1"}, "rt-2", EMAIL_A, "rt-3", now=NOW.timetuple()) == \
        {"legacy": "rt-1", "legacy-20260925T120000Z": "rt-2", EMAIL_A: "rt-3"}


def test_exchange_carries_the_legacy_token_only_while_it_works_and_is_another_account(exchange, capsys):
    dead = Resp(400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."})
    m, _, status = exchange(EMAIL_B, tokens=json.dumps({EMAIL_A: RT_A}), legacy=RT_C, legacy_reply=dead)
    assert m == {EMAIL_A: RT_A, EMAIL_B: "rt-SECRET-new"}                 # a dead token is not carried forever
    assert status["legacy_token"] == {"check": "invalid_grant", "kept": False}
    check = [d for d in exchange.posts if d["grant_type"] == "refresh_token"]
    assert len(check) == 1 and check[0]["refresh_token"] == RT_C and check[0]["client_id"] == "cid"
    lines = capsys.readouterr().out.splitlines()
    public = [l for l in lines if not l.startswith("::add-mask::")]
    assert "::warning::the old GA4_REFRESH_TOKEN no longer works (expired or revoked) and was not kept" in public
    assert not any(s in l for l in public for s in SECRETS)
    # no verdict from Google (server error, network failure) never costs a token: kept
    for reply in (Resp(503, {"error": "backend_error"}), gx.requests.ConnectionError("down")):
        m, _, status = exchange(EMAIL_B, legacy=RT_C, legacy_reply=reply)
        assert m["legacy"] == RT_C and status["legacy_token"] == {"check": "unchecked", "kept": True}
    # the legacy token's own account consenting again: its new token replaces it, not the account twice
    same = Resp(body={"access_token": "at-SECRET-legacy", "id_token": _id_token(EMAIL_B.upper())})
    m, _, status = exchange(EMAIL_B, legacy=RT_C, legacy_reply=same)
    assert m == {EMAIL_A: RT_A, EMAIL_B: "rt-SECRET-new"}
    assert status["legacy_token"] == {"check": "same_owner", "kept": False}
    other = Resp(body={"access_token": "at-SECRET-legacy", "id_token": _id_token(EMAIL_C)})
    m, _, status = exchange(EMAIL_B, legacy=RT_C, legacy_reply=other)
    assert m["legacy"] == RT_C and status["legacy_token"] == {"check": "ok", "kept": True}
    assert "::add-mask::at-SECRET-legacy" in capsys.readouterr().out     # the check's access token is masked too


def test_client_id_mode_never_receives_the_owner_tokens():
    import yaml
    path = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "ga4-auth.yml")
    with open(path) as f:
        steps = yaml.safe_load(f)["jobs"]["auth"]["steps"]
    env = next(s for s in steps if "ga4_auth_exchange" in s.get("run", ""))["env"]
    for name in ("GA4_REFRESH_TOKENS", "GA4_REFRESH_TOKEN"):
        assert env[name].replace(" ", "") == "${{github.event.inputs.mode=='exchange'&&secrets.%s||''}}" % name


# ── T13: cumulative uninstall share per install cohort by D0/1/3/7/14/30/60, and its change ─────────

T13_END = datetime(2026, 9, 23).date()
BASE_LAGS = {0: 20, 1: 10, 2: 5, 5: 5, 10: 4, 20: 3, 45: 2, 90: 1}    # uninstalls per 1,000 new users, by lag


class T13Stub(ga4.Ga4App):
    """T13's two reports from a synthetic 120-day dataset — 1,000 new users every day, BASE_LAGS uninstalls
    (+ bump(cohort age in days)) — paged by limit/offset exactly like the Data API."""

    def __init__(self, bump=lambda age: {}):
        super().__init__(TOKEN, PID, SID)
        self.bodies, self.removes = [], []
        for age in range(120):
            c = T13_END - timedelta(days=age)
            lags = dict(BASE_LAGS)
            for lag, u in bump(age).items():
                lags[lag] = lags.get(lag, 0) + u
            self.removes += [[c.strftime("%Y%m%d"), (c + timedelta(days=lag)).strftime("%Y%m%d"), u]
                             for lag, u in sorted(lags.items()) if lag <= age and u]   # happened by T13_END
        self.removes.sort(key=lambda r: (-int(r[0]), r[1]))                # firstSessionDate desc, then date

    def _post(self, method, body):
        self.bodies.append(body)
        dims = [d["name"] for d in body["dimensions"]]
        data = self.removes if dims[0] == "firstSessionDate" else \
            [[(T13_END - timedelta(days=a)).strftime("%Y%m%d"), 1000] for a in range(120)]
        page = data[body["offset"]:body["offset"] + body["limit"]]
        return {"dimensionHeaders": [{"name": n} for n in dims], "rowCount": len(data),
                "metricHeaders": [{"name": m["name"]} for m in body["metrics"]],
                "rows": [{"dimensionValues": [{"value": v} for v in r[:-1]], "metricValues": [{"value": str(r[-1])}]}
                         for r in page]}


def test_t13_counts_only_complete_cohorts_and_pages_through_every_row(monkeypatch):
    monkeypatch.setattr(ga4, "PAGE_ROWS", 500)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    ga = T13Stub()
    r = ga4.probe_t13(ga, T13_END)
    removes = [b for b in ga.bodies if b["dimensions"][0]["name"] == "firstSessionDate"]
    assert len(ga.removes) > 500 and [(b["offset"], b["limit"]) for b in removes] == [(0, 500), (500, 500)]
    assert r["pages"] == 2 and r["rows"] == r["row_count"] == len(ga.removes) and r["truncated"] is False
    # cumulative lags 0..N of BASE_LAGS; a cohort whose day N is still ahead would read low if it counted
    expect = {"D0": (120, 0.02), "D1": (119, 0.03), "D3": (117, 0.035), "D7": (113, 0.04),
              "D14": (106, 0.044), "D30": (90, 0.047), "D60": (60, 0.049)}
    for k, (cohorts, rate) in expect.items():
        day = r["by_day"][k]
        assert (day["cohorts"], day["rate"]) == (cohorts, rate), k
        assert all(w["rate"] == rate for w in day["weekly"].values()), k
        assert sum(w["cohorts"] for w in day["weekly"].values()) == cohorts, k
        assert day["change"]["flag"] is None and day["change"]["delta_pp"] == 0.0 and day["change"]["z"] == 0.0
    assert "2026-W38" in r["by_day"]["D1"]["weekly"]
    assert r["cohorts"]["20260922"] == {"new": 1000, "D0": 20, "D1": 30,   # 1 day old: only D0 + D1 complete
                                        "removed_by_lag": {"0": 20, "1": 10}}
    assert r["cohorts"]["20260923"] == {"new": 1000, "D0": 20, "removed_by_lag": {"0": 20}}
    # the full daily curve: every day N, pooled over the cohorts complete for N — nothing between checkpoints lost
    curve = r["daily_curve"]
    assert len(curve) == 120 and [curve[k]["cohorts"] for k in ("D0", "D2", "D10", "D90", "D119")] == [120, 118, 110, 30, 1]
    assert [curve[k]["rate"] for k in ("D0", "D2", "D10", "D90", "D119")] == [0.02, 0.035, 0.044, 0.05, 0.05]
    assert r["cohorts"]["20260725"]["D60"] == 49
    assert r["ok"] and r["alerts"] == {} and r["unplaced_uninstall_users"] == 0


def test_t13_safety_cap_is_flagged_never_silent(monkeypatch):
    monkeypatch.setattr(ga4, "PAGE_ROWS", 500)
    monkeypatch.setattr(ga4, "MAX_REPORT_PAGES", 1)
    r = ga4.probe_t13(T13Stub(), T13_END)
    assert r["truncated"] is True and r["pages"] == 1 and r["rows"] == 500 < r["row_count"]


@pytest.mark.parametrize("bump, alerts", [
    (lambda age: {4: 30} if 7 <= age <= 13 else {}, {"D7": "up"}),          # newest D7 week: +3 points by D7
    (lambda age: {0: -15} if 1 <= age <= 7 else {}, {"D0": "down", "D1": "down", "D3": "down"}),  # fewer early ones
    (lambda age: {}, {}),
])
def test_t13_change_detection(bump, alerts):
    r = ga4.probe_t13(T13Stub(bump), T13_END)
    assert r["alerts"] == alerts
    if alerts == {"D7": "up"}:
        ch = r["by_day"]["D7"]["change"]
        assert (ch["recent"]["rate"], ch["base"]["rate"], ch["delta_pp"], ch["relative_pct"]) == (0.07, 0.04, 3.0, 75.0)
        assert ch["recent"]["cohorts"] == 7 and ch["base"]["cohorts"] == 28 and ch["z"] >= ga4.CHANGE_Z
        assert (ch["recent"]["from"], ch["recent"]["to"]) == ("2026-09-10", "2026-09-16")
        assert r["by_day"]["D14"]["change"]["flag"] is None                  # its newest week wasn't touched
    if "D1" in alerts:
        assert r["by_day"]["D7"]["change"]["flag"] is None                   # -0.21 points: below CHANGE_MIN_PP


def test_cohort_change_needs_both_a_big_z_and_a_real_move():
    day = T13_END
    huge = [(day, 1_000_000, 22_000)] * 7 + [(day, 1_000_000, 20_000)] * 28      # z ≈ 33, only +0.2 points
    small = [(day, 100, 5)] * 7 + [(day, 100, 4)] * 28                             # +1 point, z ≈ 1.2
    assert ga4.cohort_change(huge)["z"] > 30 and ga4.cohort_change(huge)["flag"] is None
    assert ga4.cohort_change(small)["delta_pp"] == 1.0 and ga4.cohort_change(small)["flag"] is None
    assert "needs 35 complete cohorts, has 10" == ga4.cohort_change(small[:10])["reason"]
