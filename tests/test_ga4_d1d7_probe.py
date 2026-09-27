"""GA4 D1/D7 probe (admob_iq.fetch.ga4_d1d7_probe) — offline, against a fake GA4 Data/Admin API (requests mocked):
the build's app list, install-day selection, the owner's one-day firstSessionDate method and its self-check (a
property that loses old user-level data is flagged, never trusted), the cohortSpec comparison, country sums and packed
date ranges, request shapes, the quota / server-error / time-budget stops, and a PUBLIC log that stays counts-only."""

import json
import threading
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_d1d7_probe as pr

NOW = datetime(2026, 9, 27, 6, 0, tzinfo=timezone.utc)
TODAY, END = date(2026, 9, 27), date(2026, 9, 25)
EMAIL_A, EMAIL_B = "owner.a@secret-ws.test", "owner.b@secret-ws.test"
RT_A, RT_B, TOK_A, TOK_B = "rt-SECRET-a", "rt-SECRET-b", "tok-SECRET-a", "tok-SECRET-b"
PID_A, PID_B, PID_C = "987654321", "123123123", "555666777"
SID_A, SID_B, SID_C = "5550001111", "5550002222", "5550003333"
PKG_A, PKG_B, PKG_C = "com.secret.old", "com.secret.big", "com.secret.small"
AID_A, AID_B, AID_C, AID_D = ("ca-app-pub-1111111111111111~%d" % i for i in (1, 2, 3, 4))
SECRETS = [EMAIL_A, EMAIL_B, RT_A, RT_B, TOK_A, TOK_B, PID_A, PID_B, PID_C, SID_A, SID_B, SID_C, PKG_A, PKG_B, PKG_C,
           AID_A, AID_B, AID_C, AID_D, "secret", "SECRETDETAIL"]
LOSS_AGE = 60                               # the lossy property answers firstSessionDate splits older than this at 30%


def ymd(d):
    return d.strftime("%Y%m%d")


class Truth:
    """One app's GA4 reality: n installs a day since `start`; on day d, users by first-session day: d → n (all new),
    d−1 → 30%, d−7 → 10%, every 10th day since start → 2 old users, "(not set)" → 1. lossy: a firstSessionDate split or
    cohort older than LOSS_AGE days comes back at 30% / empty (the user-level data GA4 no longer holds)."""

    def __init__(self, start, n, lossy=False):
        self.start, self.n, self.lossy = start, n, lossy

    def cells(self, d):
        if d < self.start:
            return {}
        c = {d: self.n}
        if d - timedelta(days=1) >= self.start:
            c[d - timedelta(days=1)] = round(0.3 * self.n)
        if d - timedelta(days=7) >= self.start:
            c[d - timedelta(days=7)] = round(0.1 * self.n)
        f = self.start
        while f <= d - timedelta(days=2):
            c.setdefault(f, 2)
            f += timedelta(days=10)
        out = {ymd(k): v for k, v in c.items()}
        out["(not set)"] = 1
        return out

    def lost(self, d):
        return self.lossy and (TODAY - d).days > LOSS_AGE


def vals(v, new):
    return {"activeUsers": v, "newUsers": v if new else 0, "totalUsers": v, "sessions": 2 * v,
            "userEngagementDuration": 60 * v, "eventCount": 10 * v}


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


class FakeGA4:
    def __init__(self, truths, quota=None, fail=None):
        self.truths = truths                        # pid → (stream id, Truth)
        self.bodies, self.fail, self.lock = [], fail, threading.Lock()
        self.remaining = {pid: (quota or {}).get(pid, 200000) for pid in truths}

    def get(self, url, headers=None, params=None, timeout=None):
        assert headers["Authorization"] in ("Bearer " + TOK_A, "Bearer " + TOK_B)
        if url.endswith("/dataRetentionSettings"):
            return Resp(body={"name": url, "eventDataRetention": "FOURTEEN_MONTHS",
                              "userDataRetention": "FOURTEEN_MONTHS", "resetUserDataOnNewActivity": True})
        return Resp(404, {"error": {"code": 404, "status": "NOT_FOUND", "message": "?"}})

    def post(self, url, headers=None, json=None, timeout=None):
        pid = url.split("/properties/")[1].split(":")[0]
        with self.lock:
            self.bodies.append((pid, json))
        st = self.fail(pid, json) if self.fail else None
        if st:
            return Resp(st, {"error": {"code": st, "status": "INTERNAL" if st >= 500 else "INVALID_ARGUMENT",
                                       "message": "bad SECRETDETAIL " + pid}})
        sid, t = self.truths[pid]
        ex = json["dimensionFilter"]["andGroup"]["expressions"]
        pinned = {(e["filter"]["fieldName"], e["filter"]["stringFilter"]["value"]) for e in ex}
        assert ("streamId", sid) in pinned and ("platform", "Android") in pinned
        assert json.get("returnPropertyQuota") is True
        resp = self.answer(t, json)
        with self.lock:
            self.remaining[pid] -= 5
            resp["propertyQuota"] = {"tokensPerDay": {"consumed": 5, "remaining": self.remaining[pid]}}
        return Resp(body=resp)

    def answer(self, t, body):
        dims = [d["name"] for d in body.get("dimensions") or []]
        mets = [m["name"] for m in body["metrics"]]
        rows, names = [], list(dims)
        if "cohortSpec" in body:
            c = body["cohortSpec"]["cohorts"][0]
            x = date.fromisoformat(c["dateRange"]["startDate"])
            if x >= t.start and not t.lost(x):
                for k in range(body["cohortSpec"]["cohortsRange"]["endOffset"] + 1):
                    a = {0: t.n, 1: round(0.3 * t.n), 7: round(0.1 * t.n)}.get(k, 0)
                    rows.append({"cohort": c["name"], "cohortNthDay": "%04d" % k, "cohortActiveUsers": a,
                                 "cohortTotalUsers": t.n})
        else:
            rngs = body["dateRanges"]
            multi = len(rngs) > 1
            names += ["dateRange"] if multi else []
            for i, rg in enumerate(rngs):
                d = date.fromisoformat(rg["startDate"])
                while d <= date.fromisoformat(rg["endDate"]):
                    cells = t.cells(d)
                    if dims == ["date"]:
                        if cells:
                            row = {"date": ymd(d)}
                            for f, v in cells.items():
                                for m, x in vals(v, f == ymd(d)).items():
                                    row[m] = row.get(m, 0) + x
                            rows.append(row)
                    else:
                        for f, a in cells.items():
                            if "firstSessionDate" in dims and t.lost(d):
                                a = a * 3 // 10
                            for cty, v in ([("IN", a - a // 3), ("BR", a // 3)] if "country" in dims else [(None, a)]):
                                if not v:
                                    continue
                                row = dict(vals(v, f == ymd(d)), firstSessionDate=f)
                                if cty:
                                    row["country"] = cty
                                if multi:
                                    row["dateRange"] = rg.get("name") or "date_range_%d" % i
                                rows.append(row)
                    d += timedelta(days=1)
        rows.sort(key=lambda r: tuple(str(r.get(n)) for n in names))
        off, lim = int(body.get("offset") or 0), int(body.get("limit") or 10000)
        resp = {"dimensionHeaders": [{"name": n} for n in names], "metricHeaders": [{"name": m} for m in mets],
                "rows": [{"dimensionValues": [{"value": r[n]} for n in names],
                          "metricValues": [{"value": str(r[m])} for m in mets]} for r in rows[off:off + lim]],
                "rowCount": len(rows), "metadata": {"currencyCode": "USD"}}
        if "TOTAL" in (body.get("metricAggregations") or []):
            resp["totals"] = [{"dimensionValues": [{"value": "RESERVED_TOTAL"} for _ in names],
                               "metricValues": [{"value": str(sum(r[m] for r in rows))} for m in mets]}]
        return resp


TRUTHS = {PID_A: (SID_A, Truth(TODAY - timedelta(days=950), 1000)),            # the oldest
          PID_B: (SID_B, Truth(TODAY - timedelta(days=800), 2000, lossy=True)),  # the biggest; loses old user data
          PID_C: (SID_C, Truth(TODAY - timedelta(days=120), 100))}              # a small, young one
STATE = {"routes": {"by_package": {PKG_A: {"property_id": PID_A, "stream_id": SID_A, "owner": EMAIL_A},
                                   PKG_B: {"property_id": PID_B, "stream_id": SID_B, "owner": EMAIL_B},
                                   PKG_C: {"property_id": PID_C, "stream_id": SID_C, "owner": EMAIL_A}}},
         "tz": {PID_A: "UTC", PID_B: "UTC"},
         "fetch": {AID_A: {"package": PKG_A}, AID_B: {"package": PKG_B},
                   AID_C: {"package": PKG_C, "meta": {"time_zone": "UTC"}},
                   AID_D: {"package": "com.secret.noroute"}}}
TOKENS = [(EMAIL_A, RT_A), (EMAIL_B, RT_B)]


@pytest.fixture
def fake(monkeypatch):
    def make(**kw):
        f = FakeGA4(TRUTHS, **kw)
        monkeypatch.setattr(ga4.requests, "get", f.get)
        monkeypatch.setattr(ga4.requests, "post", f.post)
        return f
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: {RT_A: TOK_A, RT_B: TOK_B}[rt])
    return make


def _run(apps=None, **kw):
    apps = pr.apps_from_state(STATE) if apps is None else apps
    return pr.run_probe(apps, "cid", "sec", TOKENS, now=NOW, **kw)


def _app(pkg):
    return [a for a in pr.apps_from_state(STATE) if a["package"] == pkg]


def test_the_app_list_is_the_builds_routes_once_per_stream():
    st = json.loads(json.dumps(STATE))
    st["fetch"]["ca-app-pub-dup~9"] = {"package": PKG_A}                   # a second AdMob app of one Play package
    apps = pr.apps_from_state(st)
    assert [a["package"] for a in apps] == [PKG_A, PKG_B, PKG_C]            # no route → left out; one per stream
    assert apps[0] == {"app_id": AID_A, "package": PKG_A, "property_id": PID_A, "stream_id": SID_A,
                       "owner": EMAIL_A, "tz": "UTC"}
    assert apps[2]["tz"] == "UTC"                                           # from the store meta when state.tz has none
    assert pr.apps_from_state(None) == []


def test_install_days_respect_the_first_data_day_and_the_settled_end():
    days = pr.pick_days(TODAY, END, TODAY - timedelta(days=120))
    assert [a for a, _ in days] == [20, 70, 45, 100]
    assert all(x == TODAY - timedelta(days=a) and x + timedelta(days=7) <= END for a, x in days)
    assert pr.pick_days(TODAY, TODAY - timedelta(days=20), TODAY - timedelta(days=900), ages=(20, 30)) == \
        [(30, TODAY - timedelta(days=30))]                                  # X+7 must be settled
    assert pr.pick_days(TODAY, END, None) == []
    assert pr.fc_ages([20, 70, 45, 100]) == [20, 100]
    assert pr.fc_ages(list(pr.AGES)) == [20, 200, 550]
    assert pr.pick_country_apps({"a": {"first_day": "2024-01-01", "dau28": 10.0},
                                 "b": {"first_day": "2025-01-01", "dau28": 9000.0},
                                 "c": {"first_day": "2023-06-01", "dau28": 700.0},
                                 "d": {"first_day": "2025-06-01", "dau28": 60.0}}) == ["b", "c", "d"]


def test_the_owner_method_reads_d1_d7_and_checks_itself_on_a_complete_property(fake):
    fake()
    rep = _run(_app(PKG_A))
    a = rep["apps"][PKG_A]
    assert a["first_day"] == (TODAY - timedelta(days=950)).isoformat() and a["ref_capped"] is False
    assert a["retention"] == {"eventDataRetention": "FOURTEEN_MONTHS", "userDataRetention": "FOURTEEN_MONTHS",
                              "resetUserDataOnNewActivity": True}
    assert sorted(int(k) for k in a["xs"]) == sorted(pr.AGES)
    for age, rec in a["xs"].items():
        f, c = rec["F"], rec["C"]
        assert f["ok"] and f["cov"] == 1.0, age
        assert (f["D1"], f["D7"], f["D1_a"], f["D7_a"]) == (0.3, 0.1, 0.3, 0.1)
        assert f["den_new"] == f["den_new_fsd"] == f["den_act_fsd"] == 1000
        d0, d1 = f["d0"], f["d1"]
        assert d0["new_cov"] == 1.0 and d0["new_elsewhere"] == 0 and d0["cov_total"] == 1.0 and d0["ev_cov"] == 1.0
        assert rec["ref_ape_rel"] == 1.0                                    # the reference kept X's users
        assert d1["cell_x"] == {"act": 300, "new": 0, "tot": 300, "ses": 600, "eng": 18000, "ev": 3000}
        assert d1["not_set"]["rows"] == 1 and d1["other"]["rows"] == 0 and d1["tok"] == 5
        assert d1["old_share"] > 0 and d1["hist"]["1"] == 300 and d1["hist"]["0"] == 1000
        assert c["ok"] and c["cov"] == 1.0 and c["a"][:2] == [1000, 300] and c["dD1"] == 0 and c["dD7"] == 0
        assert rec["ref"]["d1"][1] == 1000
    rs = a["ref_series"]
    assert rs["from"] == a["first_day"] and len(rs["act"]) == len(rs["new"]) == len(rs["ev"]) == 950 - 2 + 1
    assert rs["new"][0] == 1000 and rs["ev"][-1] == 10 * rs["act"][-1] and a["ref_ape28"] == 0.1
    s = a["S"]["2026-09-15"]
    assert s["fsd_D"] == {"IN": [667, 667], "BR": [333, 333]} and s["fsd_D_1"] == {"IN": [200, 0], "BR": [100, 0]}
    assert s["cov"] == 1.0 and s["countries"] == 2 and "2026-08-17" in a["S"]
    assert a["calls"]["F"] == {"calls": 33, "tokens": 165} and a["calls"]["C"]["calls"] == 11
    assert rep["country_apps"] == [PKG_A] and "Fc" in rep["summary"]["20"]      # one app: it is all three
    assert rep["summary"]["20"]["Fc"]["cell_x_within_2pct"] == 1
    assert rep["counts"]["f_ok"] == rep["counts"]["f_of"] == 11 and rep["counts"]["errors"] == 0


def test_a_property_that_lost_old_user_data_is_flagged_never_trusted(fake):
    fake()
    rep = _run(_app(PKG_B))
    xs = rep["apps"][PKG_B]["xs"]
    assert 900 not in [int(k) for k in xs]                                  # before the app's first data day
    for age in ("20", "45"):
        assert xs[age]["F"]["ok"] and xs[age]["C"]["ok"]
    for age in ("70", "200", "700"):
        f, c = xs[age]["F"], xs[age]["C"]
        assert not f["ok"] and f["cov"] < 0.35 and f["d7"]["cov_total"] < 0.35 and f["d0"]["ev_cov"] < 0.35
        assert xs[age]["ref_ape_rel"] == 1.0                                # the reference is whole: the split lost it
        assert c["empty"] and not c["ok"] and c["cov"] == 0.0 and c["D1"] is None
    sm = rep["summary"]
    assert sm["20"]["F"]["ok"] == 1 and sm["200"]["F"]["ok"] == 0 and sm["200"]["F"]["cov_median"] < 0.35
    assert sm["200"]["C"]["empty"] == 1 and sm["900"]["F"]["asked"] == 0
    assert sm["200"]["F"]["ref_ape_rel_median"] == 1.0 and sm["200"]["F"]["ev_cov_median"] < 0.35
    assert rep["counts"]["f_ok"] == 2 and rep["counts"]["c_ok"] == 2


def test_country_sums_and_packed_ranges_are_compared_with_the_single_day_read(fake, monkeypatch):
    monkeypatch.setattr(pr, "PAGE_ROWS", 40)                              # several pages per report
    fake()
    rep = _run()
    assert rep["country_apps"] == [PKG_B, PKG_A, PKG_C]                     # biggest, oldest, small
    a = rep["apps"][PKG_A]
    assert a["fc_ages"] == [20, 200, 550]
    assert sorted(k for k, r in a["xs"].items() if "Fc" in r) == ["20", "200", "550"]
    fc = a["xs"]["200"]["Fc"]
    assert fc["ok"] and fc["D1"] == 0.3 and fc["d1"]["countries"] == 2 and fc["d1"]["pages"] > 1
    assert all(v == {"act": 1.0, "cell_x": 1.0} for v in fc["vs_F"].values())
    p = a["xs"]["900"]["P"]
    assert all(p["d%d" % n]["act_vs_F"] == 1.0 and p["d%d" % n]["cell_x_vs_F"] == 1.0 for n in pr.LAGS)
    assert rep["apps"][PKG_C]["fc_ages"] == [20, 100]
    sm = rep["summary"]["200"]
    # B's old days are short in every shape alike (Fc = F, P = F): only the coverage shows the loss
    assert sm["Fc"]["cell_x_within_2pct"] == 2 and sm["P"]["within_1pct"] == 2 and sm["Fc"]["measured"] == 2
    assert rep["apps"][PKG_B]["xs"]["200"]["Fc"]["cov"] < 0.35 and sm["F"]["ok"] == 1


def test_request_shapes_one_day_per_report_and_cohorts_without_date_ranges(fake):
    f = fake()
    _run(_app(PKG_A))
    bodies = [b for _, b in f.bodies]
    ref = [b for b in bodies if [d["name"] for d in b["dimensions"]] == ["date"]]
    assert len(ref) == 1 and ref[0]["dateRanges"] == [{"startDate": (TODAY - timedelta(days=1000)).isoformat(),
                                                       "endDate": END.isoformat()}]
    fsd = [b for b in bodies if [d["name"] for d in b["dimensions"]] == ["firstSessionDate"]
           and len(b["dateRanges"]) == 1]
    assert len(fsd) == 33
    for b in fsd:
        (r,) = b["dateRanges"]
        assert r["startDate"] == r["endDate"] and b["metricAggregations"] == ["TOTAL"]
        assert [m["name"] for m in b["metrics"]] == list(pr.METS) and b["limit"] == pr.PAGE_ROWS
    coh = [b for b in bodies if "cohortSpec" in b]
    assert len(coh) == 11
    for b in coh:
        assert "dateRanges" not in b
        (c,) = b["cohortSpec"]["cohorts"]
        assert c["dimension"] == "firstSessionDate" and c["dateRange"]["startDate"] == c["dateRange"]["endDate"]
        assert b["cohortSpec"]["cohortsRange"] == {"granularity": "DAILY", "startOffset": 0, "endOffset": 7}
    pack = [b for b in bodies if len(b.get("dateRanges") or []) == 3]
    assert len(pack) == 11 and [r["name"] for r in pack[0]["dateRanges"]] == ["d0", "d1", "d7"]


def test_low_quota_stops_that_app_politely_and_the_others_go_on(fake):
    f = fake(quota={PID_C: 20004})                                          # < 10% of the day left after one call
    rep = _run()
    c = rep["apps"][PKG_C]
    assert c["stopped"] == "quota_low" and not c["xs"]
    assert sum(1 for pid, _ in f.bodies if pid == PID_C) == 1
    assert rep["apps"][PKG_A]["xs"] and "stopped" not in rep["apps"][PKG_A]
    assert rep["counts"]["quota_low"] == 1
    assert pr.public_line(rep["counts"]).startswith("d1d7 probe: apps 2/3, days 21, ")


def test_the_quota_guard_also_watches_the_hourly_server_error_and_threshold_buckets():
    assert not pr.quota_low({"tokensPerDay": {"consumed": 5, "remaining": 150000},
                             "serverErrorsPerProjectPerHour": {"consumed": 0, "remaining": 10}})
    assert pr.quota_low({"serverErrorsPerProjectPerHour": {"consumed": 1, "remaining": 4}})
    assert pr.quota_low({"potentiallyThresholdedRequestsPerHour": {"consumed": 1, "remaining": 3}})
    assert pr.quota_low({"tokensPerProjectPerHour": {"consumed": 30, "remaining": 1000}})    # < 10% of 14,000
    # stricter than the build's 10%: this one-off leaves the hourly fetch at least half of every token bucket
    assert pr.quota_low({"tokensPerProjectPerHour": {"consumed": 30, "remaining": 6900}})    # < half of 14,000
    assert not pr.quota_low({"tokensPerProjectPerHour": {"consumed": 30, "remaining": 7100}})
    assert pr.quota_low({"tokensPerDay": {"consumed": 5, "remaining": 99000}})


def test_server_errors_are_kept_as_their_class_only_and_stop_the_property_after_two(fake):
    f = fake(fail=lambda pid, b: 500 if pid == PID_A and "cohortSpec" in b else None)
    rep = _run(_app(PKG_A))
    a = rep["apps"][PKG_A]
    errs = [r["C"] for r in a["xs"].values() if "C" in r]
    assert errs == [{"err": {"http": 500, "status": "INTERNAL"}, "tok": 0}] * 2
    assert a["stopped"] == "server_errors" and a["server_errors"] == 2
    # each retried once by ga4._call: 4 server errors, well inside the 10 an hour the project gets per property
    assert sum(1 for pid, b in f.bodies if "cohortSpec" in b) == 4
    assert "SECRETDETAIL" not in json.dumps(rep)
    assert rep["counts"]["stopped_other"] == 1 and rep["counts"]["errors"] == 2


def _twins():
    """Two apps (streams) of ONE property — quota buckets, the 5xx budget and a stop are the property's, not an app's."""
    a = _app(PKG_A)[0]
    return [a, dict(a, app_id="ca-app-pub-twin~9", package="com.secret.twin")]


def test_one_property_shares_its_quota_state_across_its_apps(fake):
    f = fake(quota={PID_A: 100004})                                         # under half the day's tokens after 1 call
    rep = _run(_twins())
    assert sum(1 for pid, _ in f.bodies if pid == PID_A) == 1               # the twin never asks on a stale snapshot
    assert rep["apps"]["com.secret.twin"]["stopped"] == "quota_low" and not rep["apps"]["com.secret.twin"]["xs"]
    assert rep["apps"][PKG_A]["stopped"] == "quota_low" and rep["counts"]["quota_low"] == 2


def test_one_property_shares_its_server_error_budget_across_its_apps(fake):
    f = fake(fail=lambda pid, b: 500 if "cohortSpec" in b else None)
    rep = _run(_twins())
    assert sum(1 for pid, b in f.bodies if "cohortSpec" in b) == 4          # 2 failed calls for the PROPERTY, not per app
    assert {rep["apps"][p]["stopped"] for p in (PKG_A, "com.secret.twin")} == {"server_errors"}
    assert not rep["apps"]["com.secret.twin"]["xs"]


def test_a_metric_ga4_rejects_falls_back_to_active_and_new_users(fake):
    fake(fail=lambda pid, b: 400 if "sessions" in json.dumps(b.get("metrics")) and
         [d["name"] for d in b.get("dimensions") or []] != ["date"] else None)
    rep = _run(_app(PKG_A))
    a = rep["apps"][PKG_A]
    assert a["min_mets"] is True
    f = a["xs"]["200"]["F"]
    assert f["ok"] and f["D1"] == 0.3 and f["d1"]["mets"] == "min" and f["d1"]["cov_total"] is None
    assert f["d1"]["ev_cov"] is None                                        # not 0: the events were not asked
    assert f["d1"]["cell_x"]["ses"] == 0


def test_the_time_budget_stops_new_calls_and_the_report_is_still_whole(fake):
    f = fake()
    ticks = iter([0.0])
    rep = _run(budget=10, clock=lambda: next(ticks, 99.0))
    assert not f.bodies and rep["counts"]["calls"] == 0
    assert {a["stopped"] for a in rep["apps"].values()} == {"budget"}
    assert rep["counts"]["stopped_other"] == 3 and set(rep["summary"]) == {str(a) for a in pr.AGES}


def test_main_writes_the_private_file_and_prints_counts_only(fake, monkeypatch, capsys):
    fake()
    put = {}
    monkeypatch.setattr(pr, "_private_json", lambda path: STATE if path == pr.STATE_PATH else None)
    monkeypatch.setattr(pr, "write_private", lambda path, text, msg: bool(put.update({path: text})) or True)
    env = {"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec",
           "GA4_REFRESH_TOKENS": json.dumps({EMAIL_A: RT_A, EMAIL_B: RT_B}), "PROBE_MAX_APPS": "2"}
    pr.main(env, now=NOW)
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert all(line.startswith("d1d7 ") for line in lines)
    assert sum(1 for line in lines if line.startswith("d1d7 probe: apps ")) == 1
    assert lines[-2].startswith("d1d7 probe: apps 2/2, days 21, calls ") and lines[-1] == "d1d7 probe: report written"
    for s in SECRETS:
        assert s not in out
    rep = json.loads(put[pr.OUT_PATH])
    assert set(rep["apps"]) == {PKG_A, PKG_B} and rep["counts"]["days"] == 21
    assert rep["summary"]["70"]["F"]["asked"] == 2 and rep["summary"]["70"]["F"]["ok"] == 1


def test_main_without_credentials_or_routes_exits_before_any_call(fake, monkeypatch):
    f = fake()
    monkeypatch.setattr(pr, "_private_json", lambda path: {"routes": {}, "fetch": {}})
    with pytest.raises(SystemExit):
        pr.main({"GA4_CLIENT_ID": "cid"}, now=NOW)
    with pytest.raises(SystemExit):
        pr.main({"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec", "GA4_REFRESH_TOKEN": RT_A}, now=NOW)
    assert not f.bodies


def test_a_counts_only_heartbeat_at_least_every_minute(capsys):
    t = iter(range(0, 1000, 25))
    run = pr.Run(clock=lambda: float(next(t)))
    for _ in range(6):
        run.tick()
    assert capsys.readouterr().out.splitlines() == ["d1d7 progress: calls 3, 75s", "d1d7 progress: calls 6, 150s"]


def test_the_report_is_still_written_when_the_bookkeeping_has_a_bug(fake, monkeypatch):
    fake()
    monkeypatch.setattr(pr, "summary", lambda apps: 1 / 0)
    monkeypatch.setattr(pr, "pick_country_apps", lambda infos: {}["x"])
    rep = _run(_app(PKG_A))
    assert rep["summary"] == {"err": {"type": "ZeroDivisionError"}} and rep["country_apps"] == []
    assert rep["apps"][PKG_A]["xs"]["200"]["F"]["ok"]                     # the spent calls' results are all there
    json.loads(pr._dump(rep))


class GitHub:
    """The contents API of the private repo: a folder listing (with each file's sha, whatever its size) and PUT."""

    def __init__(self, listings, puts):
        self.listings, self.puts, self.calls = list(listings), list(puts), []

    def get(self, url, headers=None, timeout=None, **kw):
        self.calls.append(("GET", url, None))
        st, body = self.listings.pop(0)
        return Resp(st, body)

    def put(self, url, headers=None, data=None, timeout=None, **kw):
        self.calls.append(("PUT", url, json.loads(data)))
        return Resp(self.puts.pop(0), {})


def test_the_private_write_takes_the_sha_from_the_folder_and_retries_a_race_never_forcing(monkeypatch):
    import base64
    monkeypatch.setenv("DATA_REPO", "someone/private-data")
    monkeypatch.setenv("DATA_REPO_TOKEN", "gh-SECRET")
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    big = {"path": pr.OUT_PATH, "name": "d1d7_probe.json", "sha": "sha-old", "size": 5 * 1024 * 1024}
    gh = GitHub([(200, [{"path": "ga4/diagnose.json", "sha": "x"}, big]), (200, [dict(big, sha="sha-new")])],
                [409, 200])
    monkeypatch.setattr(pr.requests, "get", gh.get)
    monkeypatch.setattr(pr.requests, "put", gh.put)
    assert pr.write_private(pr.OUT_PATH, '{"a":1}', "ga4 d1d7 probe")
    gets = [c for c in gh.calls if c[0] == "GET"]
    puts = [c for c in gh.calls if c[0] == "PUT"]
    assert all(u == "https://api.github.com/repos/someone/private-data/contents/ga4" for _, u, _ in gets)
    assert all(u == "https://api.github.com/repos/someone/private-data/contents/" + pr.OUT_PATH for _, u, _ in puts)
    assert [b["sha"] for _, _, b in puts] == ["sha-old", "sha-new"]            # re-read after the race
    assert base64.b64decode(puts[0][2]["content"]).decode() == '{"a":1}'
    assert all(set(b) == {"message", "content", "sha"} for _, _, b in puts)   # no force, no branch games
    gh = GitHub([(404, {"message": "Not Found"})], [201])                     # a first run: the folder may not exist
    monkeypatch.setattr(pr.requests, "get", gh.get)
    monkeypatch.setattr(pr.requests, "put", gh.put)
    assert pr.write_private(pr.OUT_PATH, "{}", "m") and "sha" not in gh.calls[-1][2]
    gh = GitHub([(500, {})] * pr.WRITE_TRIES, [])
    monkeypatch.setattr(pr.requests, "get", gh.get)
    assert pr.write_private(pr.OUT_PATH, "{}", "m") is False and len(gh.calls) == pr.WRITE_TRIES
