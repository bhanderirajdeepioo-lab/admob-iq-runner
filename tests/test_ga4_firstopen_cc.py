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


def test_due_order_recent_then_now_final_then_backfill_oldest_first_from_the_apps_day_1():
    now = datetime(2026, 10, 20, 6, tzinfo=timezone.utc)
    s = {"days": {(TODAY - timedelta(days=4)).isoformat(): {"fin": False, "t": [1, 1, 1]},
                  (TODAY - timedelta(days=5)).isoformat(): {"fin": True, "t": [1, 1, 1]},
                  (TODAY - timedelta(days=6)).isoformat(): {"fin": True, "t": [0, 0, 0]},   # stored as zeros: asked again
                  (TODAY - timedelta(days=9)).isoformat(): {"none": True}}}
    first = TODAY - timedelta(days=80)                                 # the First open store's own day 1
    d = fc.due(s, TODAY, now, first)
    assert d[:3] == [TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=2)]
    assert d[3:5] == [TODAY - timedelta(days=6), TODAY - timedelta(days=4)]   # not final when read / zeros, final now
    assert d[5] == first and d[6] == first + timedelta(days=1)          # then the backfill, the OLDEST day first
    assert d[-1] == TODAY - timedelta(days=3)
    assert TODAY - timedelta(days=5) not in d and TODAY - timedelta(days=9) not in d and len(d) == len(set(d))
    # never further back than BACKFILL_DAYS, whatever the store's day 1
    assert min(fc.due({}, TODAY, now, TODAY - timedelta(days=400))) == TODAY - timedelta(days=fc.BACKFILL_DAYS)
    s["recent_at"] = "2026-10-20T05:00:00Z"                            # refreshed an hour ago: not again
    assert TODAY not in fc.due(s, TODAY, now, first)


def test_a_day_ga4s_funnel_no_longer_has_is_none_not_zeros():
    class Gone(FakeGa):
        def funnel(self, body):
            self.calls += 1
            return {"funnelTable": {"rows": []}}                    # GA4's event data for that day is gone
    ga = Gone()
    rec = fc.read_day(ga, STEPS, TODAY - timedelta(days=70), {"AA": 5}, TODAY, "now")
    assert rec == {"none": True, "why": "ga4", "at": "now"} and ga.calls == 1      # no group call wasted on it


def test_the_property_that_waited_longest_goes_first(tmp_path, monkeypatch):
    """Two properties: the one whose apps never had a turn is read first, the other one next run."""
    import json, os
    from admob_iq.fetch import ga4_uninstall as gu
    order = []
    monkeypatch.setattr(fc, "step_app", lambda ga, store, steps, today, now, first=None: order.append(ga.property_id) or "fresh")
    monkeypatch.setattr(gf, "App", lambda tok, pid, sid, prop, over=None: type("A", (), {"calls": 0, "tok": 0, "property_id": pid})())
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


def test_log_line_is_counts_only():
    line = fc.log_line({"counts": dict.fromkeys(fc.COUNTS, 2)})
    assert line.startswith("ga4 first open by country: apps 2") and line.count("2") == len(fc.COUNTS)
