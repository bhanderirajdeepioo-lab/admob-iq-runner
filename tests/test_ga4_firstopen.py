"""🆕 First open — the hourly fetch (admob_iq.fetch.ga4_firstopen), offline with a fake GA4 and made-up apps / screens /
numbers: the screens it picks, the strict funnels it asks (and only for the steps an app has), the one-time backfill (in
15-day chunks, resumed after a stop), the recent refresh every 6 hours, the store kept for good, and a counts-only line."""
import gzip
import json
import os
from datetime import date, datetime, timedelta, timezone

from admob_iq.fetch import ga4_firstopen as gf

NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 13)


class FakeGA:
    """Answers discovery and every funnel: first_open 100, splash 90, step 60 (home_any 61) on each day asked."""

    def __init__(self, stop_after=None):
        self.calls, self.asked, self.stop_after, self.tok = 0, [], stop_after, 0

    def report_all(self, body, event=None, events=None, extra=None):
        self.calls += 1
        self.asked.append(("disc", body, event, extra))
        return [{"unifiedScreenClass": c, "activeUsers": n} for c, n in
                [("MainActivity", 80), ("SplashActivity", 100), ("LanguageActivity", 70), ("CallerCadHomeActivity", 99)]]

    def funnel(self, body):
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise gf.Stop("calls")
        self.calls += 1
        self.asked.append(("funnel", body))
        a = date.fromisoformat(body["dateRanges"][0]["startDate"]); b = date.fromisoformat(body["dateRanges"][0]["endDate"])
        anyt = "withinDurationFromPriorStep" not in body["funnel"]["steps"][1]
        rows = []
        d = a
        while d <= b:
            k = d.strftime("%Y%m%d")
            for i, (n, v) in enumerate((("first_open", 100), ("splash", 90 if not anyt else 92), ("step", 60 if not anyt else 61))):
                rows.append({"dimensionValues": [{"value": "%d. %s" % (i + 1, n)}, {"value": k}], "metricValues": [{"value": str(v)}]})
            d += timedelta(days=1)
        return {"funnelTable": {"dimensionHeaders": [{"name": "funnelStepName"}, {"name": "date"}],
                                "metricHeaders": [{"name": "activeUsers"}], "rows": rows}}


def test_screens_backfill_and_recent_refresh():
    ga, store = FakeGA(), {"v": gf.STORE_V}
    hs = date(2026, 9, 1)
    assert gf.step_app(ga, store, TODAY, hs, NOW) == "fetched"
    assert store["steps"] == {"home": "MainActivity", "splash": "SplashActivity", "language": "LanguageActivity"}
    disc = [x for x in ga.asked if x[0] == "disc"][0]
    assert disc[2] == "screen_view" and disc[3][0]["filter"]["fieldName"] == "newVsReturning"     # first sessions
    days = store["days"]
    assert min(days) == "2026-09-01" and max(days) == "2026-10-13" and len(days) == 43                 # from the history start
    assert days["2026-10-01"] == {"first_open": 100, "splash": 90, "home": 60, "splash_any": 92, "home_any": 61, "language": 60}
    funnels = [x[1] for x in ga.asked if x[0] == "funnel"]
    assert all(f["funnel"]["isOpenFunnel"] is False for f in funnels) and all(f["funnelBreakdown"]["limit"] == "15" for f in funnels)
    assert len(funnels) == 3 * 3                       # (backfill 2 chunks + recent 1) × (home, home_any, language)
    assert store["backfill"] == {"from": "2026-09-01", "next": "2026-09-29", "done": True}
    ga2 = FakeGA()
    assert gf.step_app(ga2, store, TODAY, hs, NOW + timedelta(hours=2)) == "fresh" and ga2.calls == 0   # nothing due
    assert gf.step_app(ga2, store, TODAY, hs, NOW + timedelta(hours=7)) == "fetched" and ga2.calls == 3   # recent again


def test_backfill_goes_back_at_most_120_days_and_resumes_after_a_stop():
    ga, store = FakeGA(stop_after=1 + 3 * 2), {"v": gf.STORE_V}       # discovery + 2 chunks, then the call cap
    try:
        gf.step_app(ga, store, TODAY, date(2023, 1, 1), NOW)
        raise AssertionError("no stop")
    except gf.Stop:
        pass
    assert store["backfill"]["from"] == (TODAY - timedelta(days=120)).isoformat() and not store["backfill"].get("done")
    nxt = store["backfill"]["next"]
    assert nxt == (TODAY - timedelta(days=120) + timedelta(days=30)).isoformat()
    ga2 = FakeGA()
    assert gf.step_app(ga2, store, TODAY, date(2023, 1, 1), NOW) == "fetched" and store["backfill"]["done"]
    first = [x[1] for x in ga2.asked if x[0] == "funnel"][0]
    assert first["dateRanges"][0]["startDate"] == nxt                  # went on where it stopped


def test_a_step_nobody_reached_is_zero_not_missing():
    class NoIntro(FakeGA):
        def funnel(self, body):
            j = super().funnel(body)
            j["funnelTable"]["rows"] = [r for r in j["funnelTable"]["rows"] if not r["dimensionValues"][0]["value"].startswith("3.")]
            return j
    days = gf.read_chunk(NoIntro(), {"splash": "S", "home": "H", "intro": "I"}, date(2026, 10, 1), date(2026, 10, 2))
    assert days["2026-10-01"] == {"first_open": 100, "splash": 90, "home": 0, "splash_any": 92, "home_any": 0, "intro": 0}


def test_sampling_is_kept_per_day():
    class Sampled(FakeGA):
        def funnel(self, body):
            j = super().funnel(body)
            if "withinDurationFromPriorStep" not in body["funnel"]["steps"][1]:      # only the "any time" funnel
                j["funnelTable"]["metadata"] = {"samplingMetadatas": [{"samplesReadCount": "25", "samplingSpaceSize": "100"}]}
            return j
    days = gf.read_chunk(Sampled(), {"splash": "S", "home": "H"}, date(2026, 10, 1), date(2026, 10, 1))
    assert days["2026-10-01"]["sample"] == 0.25 and days["2026-10-01"]["home"] == 60
    assert gf.sampling({"funnelTable": {"metadata": {"samplingMetadatas": [{"samplesReadCount": "5", "samplingSpaceSize": "5"}]}}}) is None
    assert gf.sampling({}) is None


def test_no_splash_or_home_reads_no_funnel():
    class NoSteps(FakeGA):
        def report_all(self, body, event=None, events=None, extra=None):
            self.calls += 1
            return [{"unifiedScreenClass": "AdActivity", "activeUsers": 5}]
    ga, store = NoSteps(), {"v": gf.STORE_V}
    assert gf.step_app(ga, store, TODAY, date(2026, 9, 1), NOW) == "no_steps" and ga.calls == 1 and "days" not in store


def test_refresh_all_keeps_the_store_and_logs_counts_only(monkeypatch, tmp_path):
    data = str(tmp_path)
    route = {"property_id": "111", "stream_id": "222", "owner": "o"}
    monkeypatch.setattr(gf.gu, "load_state", lambda d: {"routes": {"by_package": {"com.example.alpha": route}}, "tz": {"111": "Asia/Kolkata"}, "fetch": {}})
    monkeypatch.setattr(gf.gaud, "_uni_meta", lambda ust, d, aid, r: {"history_start": "2026-09-20"})
    monkeypatch.setattr(gf.ga4, "access_token", lambda c, s, r: "tok")

    class A(FakeGA):
        def __init__(self, token, pid, sid, prop, over=None, max_calls=gf.MAX_CALLS):
            super().__init__()
    monkeypatch.setattr(gf, "App", A)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    out = gf.refresh_all(cfg, data, [{"app_id": "ca-app-pub-0000000000000001~1", "package": "com.example.alpha"},
                                     {"app_id": "x~2", "package": "com.example.none"}], NOW)
    assert out["apps"] == {"ca-app-pub-0000000000000001~1": "fetched"} and out["counts"]["with_ga4"] == 1
    p = gf.store_path(data, "ca-app-pub-0000000000000001~1")
    with gzip.open(p, "rt", encoding="utf-8") as f:
        st = json.load(f)
    assert st["v"] == gf.STORE_V and st["package"] == "com.example.alpha" and min(st["days"]) == "2026-09-20"
    line = gf.log_line(out)
    assert line.startswith("ga4 first open: apps 2, with GA4 1, fetched 1") and "example" not in line and "Activity" not in line
