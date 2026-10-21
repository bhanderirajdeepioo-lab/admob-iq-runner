"""First open by country (fetch.ga4_firstopen_cc): every country read in groups of 15 by name (none cut), the day's total
apart, GA4's RESERVED_TOTAL dropped, the days asked in the right order. Synthetic data only (this repo is public)."""
from datetime import date, datetime, timedelta, timezone

from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_firstopen_cc as fc

STEPS = {"splash": "SplashScreen", "home": "HomeScreen"}
TODAY = date(2026, 10, 20)


def _table(rows, dim):
    return {"funnelTable": {"dimensionHeaders": [{"name": "funnelStepName"}, {"name": dim}],
                            "metricHeaders": [{"name": "activeUsers"}],
                            "rows": [{"dimensionValues": [{"value": s}, {"value": b}], "metricValues": [{"value": str(v)}]}
                                     for s, b, v in rows]}}


class FakeGa:
    """40 synthetic countries C00 … C39 (first_open, splash, home) + 7 users GA4 names no country for."""

    def __init__(self, data=None, unnamed=(7, 6, 5)):
        self.data = data or {"C%02d" % i: (100 - i, 90 - i, 50 - i) for i in range(40)}
        self.unnamed, self.bodies, self.reports, self.calls, self.tok = unnamed, [], [], 0, 0

    def report_all(self, body, event=None, **k):
        self.reports.append((body, event))
        a = date.fromisoformat(body["dateRanges"][0]["startDate"])
        b = date.fromisoformat(body["dateRanges"][0]["endDate"])
        rows, d = [], a
        while d <= b:
            rows += [{"date": d.strftime("%Y%m%d"), "countryId": c, "activeUsers": str(v[0])} for c, v in self.data.items()]
            rows.append({"date": d.strftime("%Y%m%d"), "countryId": "(not set)", "activeUsers": "7"})
            d += timedelta(days=1)
        return rows

    def funnel(self, body):
        self.calls += 1
        self.bodies.append(body)
        steps = ("1. first_open", "2. splash", "3. step")
        dim = body["funnelBreakdown"]["breakdownDimension"]["name"]
        if dim == "date":
            t = [sum(v[i] for v in self.data.values()) + self.unnamed[i] for i in range(3)]
            return _table([(s, "20261001", t[i]) for i, s in enumerate(steps)] + [(s, fc.RT, t[i]) for i, s in enumerate(steps)],
                          "date")
        f = body["funnel"]["steps"][0]["filterExpression"]["andGroup"]["expressions"][1]["funnelFieldFilter"]
        grp = f["inListFilter"]["values"]
        rows = [(s, fc.RT, sum(self.data[c][i] for c in grp)) for i, s in enumerate(steps)]
        for c in grp:
            rows += [(s, c, self.data[c][i]) for i, s in enumerate(steps) if self.data[c][i]]
        return _table(rows, dim)


def test_read_day_reads_every_country_by_name_in_groups_of_15():
    ga = FakeGa()
    cc = fc.countries(ga, TODAY - timedelta(days=5), TODAY - timedelta(days=5))
    day = (TODAY - timedelta(days=5)).isoformat()
    assert len(cc[day]) == 40 and "(not set)" not in cc[day]          # GA4's "(not set)" is never a group's value
    rec = fc.read_day(ga, STEPS, TODAY - timedelta(days=5), cc[day], TODAY, "now")
    assert ga.calls == 1 + 3                                           # the total, then 15 + 15 + 10
    assert len(rec["c"]) == 40 and rec["c"]["C39"] == [61, 51, 11] and fc.RT not in rec["c"]
    assert rec["t"] == [sum(100 - i for i in range(40)) + 7, sum(90 - i for i in range(40)) + 6,
                        sum(50 - i for i in range(40)) + 5]                # RT not added to the total
    assert rec["fin"] is True and rec["sg"] == fc.sig(STEPS)
    groups = [b["funnel"]["steps"][0]["filterExpression"]["andGroup"]["expressions"][1]["funnelFieldFilter"]
              ["inListFilter"]["values"] for b in ga.bodies[1:]]
    assert [len(g) for g in groups] == [15, 15, 10] and set().union(*groups) == set(cc[day])
    assert "C00" in groups[0] and "C39" in groups[2]                   # the biggest first
    # step 2 and 3 are the First open fetch's own, unfiltered
    st = ga.bodies[1]["funnel"]["steps"]
    assert st[1] == gf.funnel_body("SplashScreen", "HomeScreen", TODAY, TODAY)["funnel"]["steps"][1]


def test_a_country_nobody_of_reached_is_left_out_not_zeroed_in():
    data = {"AA": (5, 0, 0), "BB": (9, 9, 4)}
    ga = FakeGa(data=data, unnamed=(0, 0, 0))
    rec = fc.read_day(ga, STEPS, TODAY - timedelta(days=4), {"AA": 5, "BB": 9}, TODAY, "now")
    assert rec["c"] == {"AA": [5, 0, 0], "BB": [9, 9, 4]}


def test_due_order_at_risk_days_then_recent_then_now_final_then_the_rest_oldest_first_from_the_apps_day_1():
    now = datetime(2026, 10, 20, 6, tzinfo=timezone.utc)
    s = {"days": {(TODAY - timedelta(days=4)).isoformat(): {"fin": False, "t": [1, 1, 1]},
                  (TODAY - timedelta(days=5)).isoformat(): {"fin": True, "t": [1, 1, 1]},
                  (TODAY - timedelta(days=6)).isoformat(): {"fin": True, "t": [0, 0, 0]},   # stored as zeros: asked again
                  (TODAY - timedelta(days=9)).isoformat(): {"none": True}}}
    first = TODAY - timedelta(days=80)                                 # the First open store's own day 1
    d = fc.due(s, TODAY, now, first)
    risk = [first + timedelta(days=i) for i in range(80 - fc.AT_RISK_DAYS + 1)]
    # the days GA4 may delete next come FIRST (oldest first), before the recent refresh
    assert d[:len(risk)] == risk and d[0] == first
    r = len(risk)
    assert d[r:r + 3] == [TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=2)]
    assert d[r + 3:r + 5] == [TODAY - timedelta(days=6), TODAY - timedelta(days=4)]   # not final when read / zeros
    assert d[r + 5] == TODAY - timedelta(days=fc.AT_RISK_DAYS - 1) and d[-1] == TODAY - timedelta(days=3)
    assert TODAY - timedelta(days=5) not in d and TODAY - timedelta(days=9) not in d and len(d) == len(set(d))
    # from the store's day 1 however far back it is (each day is asked once, then kept); no day 1: BACKFILL_DAYS back
    assert min(fc.due({}, TODAY, now, TODAY - timedelta(days=200))) == TODAY - timedelta(days=200)
    assert min(fc.due({}, TODAY, now)) == TODAY - timedelta(days=fc.BACKFILL_DAYS)
    s["recent_at"] = "2026-10-20T05:00:00Z"                            # refreshed an hour ago: not again
    assert TODAY not in fc.due(s, TODAY, now, first)


def test_a_gone_day_is_asked_once_more_on_a_later_run_then_never():
    now = datetime(2026, 10, 20, 6, tzinfo=timezone.utc)
    k = (TODAY - timedelta(days=70)).isoformat()
    s = {"recent_at": "2026-10-20T05:00:00Z",
         "days": {k: {"none": True, "why": "ga4", "n": 1, "fo": {"AA": 3}, "at": "2026-10-20T04:00:00Z"}}}
    first = TODAY - timedelta(days=70)
    assert TODAY - timedelta(days=70) not in fc.due(s, TODAY, now, first)           # answered 2 h ago: not yet
    s["days"][k]["at"] = "2026-10-19T20:00:00Z"
    assert fc.due(s, TODAY, now, first)[0] == TODAY - timedelta(days=70)           # a later run: once more
    s["days"][k]["n"] = fc.GONE_CONFIRM
    assert TODAY - timedelta(days=70) not in fc.due(s, TODAY, now, first)           # confirmed: never again
    s["days"][k] = {"none": True, "why": "ga4", "at": "2026-10-19T20:00:00Z"}      # an older record (no n): once more
    assert fc.due(s, TODAY, now, first)[0] == TODAY - timedelta(days=70)


def test_a_day_ga4s_funnel_no_longer_has_keeps_the_reports_first_opens_never_zeros():
    class Gone(FakeGa):
        def funnel(self, body):
            self.calls += 1
            return {"funnelTable": {"rows": []}}                    # GA4's event data for that day is gone
    ga = Gone()
    old = TODAY - timedelta(days=70)
    rec = fc.read_day(ga, STEPS, old, {"AA": 5, "BB": 2}, TODAY, "now")
    assert rec == {"none": True, "why": "ga4", "n": 1, "fo": {"AA": 5, "BB": 2}, "at": "now"} and ga.calls == 1
    rec2 = fc.read_day(ga, STEPS, old, {"AA": 5, "BB": 2}, TODAY, "later", rec)     # the second empty answer: final
    assert rec2["n"] == fc.GONE_CONFIRM and rec2["fo"] == {"AA": 5, "BB": 2} and ga.calls == 2
    # a day too young for GA4 to have deleted it: an empty answer is a lag / blip — nothing stored, asked again
    young = TODAY - timedelta(days=fc.AT_RISK_DAYS - 1)
    assert fc.read_day(ga, STEPS, young, {"AA": 5}, TODAY, "now") is None and ga.calls == 3
    store = {"days": {}}
    fc.step_app(type("G", (Gone,), {"report_all": lambda self, body, event=None, **k: [
        {"date": young.strftime("%Y%m%d"), "countryId": "AA", "activeUsers": "5"}]})(), store, STEPS, TODAY,
        datetime(2026, 10, 20, 6, tzinfo=timezone.utc), young)
    assert young.isoformat() not in store["days"]
    assert young in fc.due(store, TODAY, datetime(2026, 10, 20, 7, tzinfo=timezone.utc), young)
    # a "gone" an older run stored for so young a day (no n, no counts): dropped back to not read, asked again
    store = {"days": {young.isoformat(): {"none": True, "why": "ga4", "at": "2026-10-19T00:00:00Z"}}}
    fc.step_app(type("G", (Gone,), {"report_all": lambda self, body, event=None, **k: [
        {"date": young.strftime("%Y%m%d"), "countryId": "AA", "activeUsers": "5"}]})(), store, STEPS, TODAY,
        datetime(2026, 10, 20, 6, tzinfo=timezone.utc), young)
    assert young.isoformat() not in store["days"]


def test_a_gone_day_that_comes_back_is_read_whole():
    ga, old = FakeGa(), TODAY - timedelta(days=70)
    prev = {"none": True, "why": "ga4", "n": 1, "fo": {"C00": 100}, "at": "t"}
    rec = fc.read_day(ga, STEPS, old, {"C%02d" % i: 1 for i in range(40)}, TODAY, "now", prev)
    assert not rec.get("none") and len(rec["c"]) == 40 and rec["fin"] is True


def _fake_api(n_cc, gone_before=None, empty_days=()):
    """ga4._call for the real gf.App: runReport = n_cc synthetic countries on every day asked (paged as GA4 pages);
    runFunnelReport = a whole funnel for every value asked, empty for a day before `gone_before` or in `empty_days`."""
    ccs = ["Q%03d" % i for i in range(n_cc)]
    seen = []

    def call(method, url, token, body=None, params=None):
        a = date.fromisoformat(body["dateRanges"][0]["startDate"])
        if url.endswith(":runReport"):
            b = date.fromisoformat(body["dateRanges"][0]["endDate"])
            rows, d = [], a
            while d <= b:
                rows += [{"dimensionValues": [{"value": d.strftime("%Y%m%d")}, {"value": c}],
                          "metricValues": [{"value": "4"}]} for c in ccs]
                d += timedelta(days=1)
            off, lim = int(body.get("offset") or 0), int(body.get("limit") or 10000)
            return {"dimensionHeaders": [{"name": "date"}, {"name": "countryId"}],
                    "metricHeaders": [{"name": "activeUsers"}], "rows": rows[off:off + lim], "rowCount": len(rows)}
        seen.append(a)
        if (gone_before and a < gone_before) or a in empty_days:
            return {"funnelTable": {"rows": []}}
        dim = body["funnelBreakdown"]["breakdownDimension"]["name"]
        vals = (["20261001"] if dim == "date" else
                body["funnel"]["steps"][0]["filterExpression"]["andGroup"]["expressions"][1]["funnelFieldFilter"]
                ["inListFilter"]["values"])
        rows = [{"dimensionValues": [{"value": s}, {"value": v}], "metricValues": [{"value": str(4 - i)}]}
                for v in vals for i, s in enumerate(("1. first_open", "2. splash", "3. step"))]
        return {"funnelTable": {"dimensionHeaders": [{"name": "funnelStepName"}, {"name": dim}],
                                "metricHeaders": [{"name": "activeUsers"}], "rows": rows}}
    return call, seen


def test_a_big_app_backfills_from_its_day_1_under_the_real_call_cap(monkeypatch):
    """The real gf.App with this module's cap and ~150 countries a day (11 calls a day): every run reads the oldest days
    GA4 may delete next, then today … 2 days back once; no day is ever cut by the cap; the store reaches day 1."""
    call, seen = _fake_api(150)
    monkeypatch.setattr(fc.ga4, "_call", call)
    monkeypatch.setattr(fc.ga4, "_sleep", lambda s: None)
    today, first = date(2026, 10, 21), date(2026, 7, 19)
    store, olds, runs = {"v": fc.STORE_V}, [], 0
    for h in range(20):
        now = datetime(2026, 10, 21, 2 + h, tzinfo=timezone.utc)
        ga = gf.App("t", "p", "s", {"quota": None, "stop": None}, max_calls=fc.MAX_CALLS)
        try:
            res = fc.step_app(ga, store, STEPS, today, now, first)
        except gf.Stop as e:
            res = str(e)
        assert ga.calls <= fc.MAX_CALLS
        days = store.get("days") or {}
        assert all(len(v["c"]) == 150 for v in days.values())
        assert (ga.calls - (ga.last_pages or 0)) % fc.calls_for(range(150)) == 0   # no day begun and cut: no call wasted
        olds.append(min(days))
        runs += 1
        if res == "fresh":
            break
    assert olds[0] == first.isoformat()                                 # the first run starts at day 1
    days = store["days"]
    assert sorted(days) == [(first + timedelta(days=i)).isoformat() for i in range((today - first).days + 1)]
    assert store["recent_at"] and runs < 15
    # the old cap (gf.MAX_CALLS) could never have read a day here, after the recent ones and the report pages
    assert fc.MAX_CALLS > gf.MAX_CALLS and 2 + 3 * fc.calls_for(range(150)) > gf.MAX_CALLS


def test_recent_days_are_read_once_per_refresh_even_when_the_backfill_stops(monkeypatch):
    call, seen = _fake_api(150)
    monkeypatch.setattr(fc.ga4, "_call", call)
    monkeypatch.setattr(fc.ga4, "_sleep", lambda s: None)
    today, first = date(2026, 10, 21), date(2026, 9, 2)                 # nothing at risk yet: the recent days first
    store = {"v": fc.STORE_V}
    for h in range(2):
        ga = gf.App("t", "p", "s", {"quota": None, "stop": None}, max_calls=fc.MAX_CALLS)
        try:
            fc.step_app(ga, store, STEPS, today, datetime(2026, 10, 21, 2 + h, tzinfo=timezone.utc), first)
        except gf.Stop:
            pass
        if h == 0:
            assert store["recent_at"] == "2026-10-21T02:00:00Z"          # set although the run stopped later
    assert seen.count(today) == fc.calls_for(range(150))                # today read in run 1 only, not again an hour on


def test_a_young_empty_day_and_a_gone_old_day_under_the_real_app(monkeypatch):
    """GA4's funnel empty before day 60 back (deleted) and for one day 20 back (a blip): the old ones are kept as gone
    with the report's first opens, the young one stays unstored (asked again), nothing is zeros."""
    today = date(2026, 10, 21)
    blip = today - timedelta(days=20)
    call, seen = _fake_api(20, gone_before=today - timedelta(days=60), empty_days=(blip,))
    monkeypatch.setattr(fc.ga4, "_call", call)
    monkeypatch.setattr(fc.ga4, "_sleep", lambda s: None)
    first, store = today - timedelta(days=70), {"v": fc.STORE_V}
    ga = gf.App("t", "p", "s", {"quota": None, "stop": None}, max_calls=fc.MAX_CALLS)
    try:
        fc.step_app(ga, store, STEPS, today, datetime(2026, 10, 21, 6, tzinfo=timezone.utc), first)
    except gf.Stop:
        pass
    days = store["days"]
    gone = sorted(k for k, v in days.items() if fc.is_gone(v))
    assert gone == [(first + timedelta(days=i)).isoformat() for i in range(10)]
    assert all(days[k]["fo"] == {"Q%03d" % i: 4 for i in range(20)} and days[k]["n"] == 1 for k in gone)
    assert blip.isoformat() not in days and not any(v.get("t") == [0, 0, 0] for v in days.values())


def test_the_property_that_waited_longest_goes_first(tmp_path, monkeypatch):
    """Two properties: the one whose apps never had a turn is read first, the other one next run."""
    import json, os
    from admob_iq.fetch import ga4_uninstall as gu
    order = []
    caps = []
    monkeypatch.setattr(fc, "step_app", lambda ga, store, steps, today, now, first=None: order.append(ga.property_id) or "fresh")
    monkeypatch.setattr(gf, "App", lambda tok, pid, sid, prop, over=None, max_calls=gf.MAX_CALLS: caps.append(max_calls) or
                        type("A", (), {"calls": 0, "tok": 0, "property_id": pid})())
    monkeypatch.setattr(fc.ga4, "access_token", lambda *a: "tok")
    monkeypatch.setattr(fc.ga4_probe, "owner_tokens", lambda env: ([("o", "rt")], None))
    apps, routes = [], {}
    for n, pid in (("a", "P1"), ("b", "P2")):
        aid = "ca-app-pub-0~%s" % n
        apps.append({"app_id": aid, "package": "pkg." + n})
        routes["pkg." + n] = {"property_id": pid, "stream_id": "s" + n, "owner": "o"}
        main = {"v": gf.STORE_V, "app_id": aid, "steps": STEPS, "time_zone": "UTC", "days": {"2026-08-01": {"first_open": 1}}}
        from admob_iq.db import write_json_gz_stable
        write_json_gz_stable(gf.store_path(str(tmp_path), aid), main)
    monkeypatch.setattr(gu, "load_state", lambda d: {"routes": {"by_package": routes}, "tz": {}})
    st = {"v": 1, "fetch": {"ca-app-pub-0~a": {"turn": "2026-10-20T05:00:00Z"}, "ca-app-pub-0~b": {}}}
    os.makedirs(os.path.join(str(tmp_path), fc.DIR))
    with open(os.path.join(str(tmp_path), fc.DIR, "state.json"), "w") as f:
        json.dump(st, f)
    out = fc.refresh_all({"client_id": "c", "client_secret": "s", "refresh_tokens": "x"}, str(tmp_path), apps,
                         now=datetime(2026, 10, 20, 6, tzinfo=timezone.utc), workers=1)
    assert order == ["P2", "P1"], out
    assert caps == [fc.MAX_CALLS, fc.MAX_CALLS]                       # this module's cap, not the First open fetch's
    turns = json.load(open(os.path.join(str(tmp_path), fc.DIR, "state.json")))["fetch"]
    assert turns["ca-app-pub-0~a"]["turn"] == turns["ca-app-pub-0~b"]["turn"] == "2026-10-20T06:00:00Z"


def test_step_app_marks_days_ga4_has_nothing_for_and_keeps_recent_open():
    class Empty(FakeGa):
        def report_all(self, body, event=None, **k):
            return []
    ga, store = Empty(), {}
    now = datetime(2026, 10, 20, 6, tzinfo=timezone.utc)
    assert fc.step_app(ga, store, STEPS, TODAY, now) == "fetched"
    days = store["days"]
    assert days[(TODAY - timedelta(days=3)).isoformat()] == {"none": True, "at": "2026-10-20T06:00:00Z"}
    assert TODAY.isoformat() not in days and ga.calls == 0               # a recent day is asked again next time
    assert store["recent_at"] == "2026-10-20T06:00:00Z"


def test_budget_default_is_this_modules(monkeypatch):
    """settings() without GA4_FIRSTOPEN_CC_BUDGET_SEC (the workflow passes it empty) leaves the budget to BUDGET_SEC
    (the caller's `or`); set, it wins."""
    from admob_iq.config import settings
    monkeypatch.setenv("GA4_FIRSTOPEN_CC_BUDGET_SEC", "")
    assert (settings().get("ga4_firstopen_cc_budget_sec") or fc.BUDGET_SEC) == fc.BUDGET_SEC
    monkeypatch.setenv("GA4_FIRSTOPEN_CC_BUDGET_SEC", "90")
    assert (settings().get("ga4_firstopen_cc_budget_sec") or fc.BUDGET_SEC) == 90


def test_log_line_is_counts_only():
    line = fc.log_line({"counts": dict.fromkeys(fc.COUNTS, 2)})
    assert line.startswith("ga4 first open by country: apps 2") and line.count("2") == len(fc.COUNTS)
