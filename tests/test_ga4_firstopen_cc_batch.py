"""First open by country: a day's group calls side by side (ga4_firstopen.App.funnel_many, ga4_firstopen_cc.BATCH) —
every store, the state file and the counts byte-identical to one call at a time, against a synthetic GA4 whose answers
come back in a shuffled order and whose property quota is used up call by call (a floor crossed mid-day, the call cap,
gone and empty days, the recent refresh, a failing call, two properties). Synthetic data only (this repo is public)."""

import gzip
import hashlib
import json
import os
import random
import shutil
import threading
import time
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq.db import write_json_gz_stable
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_firstopen_cc as fc
from admob_iq.fetch import ga4_uninstall as gu

STEPS = {"splash": "SplashScreen", "home": "HomeScreen"}
NOW = datetime(2026, 10, 21, 6, tzinfo=timezone.utc)
TODAY = date(2026, 10, 21)


def _h(*p):
    return int(hashlib.sha1("|".join(map(str, p)).encode()).hexdigest()[:8], 16)


class GA4:
    """A synthetic GA4 Data API for ga4._call: per property a quota (day / hour / project-hour tokens, thresholded
    requests, server errors) used up atomically by every request — a funnel call's cost from its content (60 … 119
    tokens; costs=(a day's total, a group call): fixed per shape), a report's 40 — each answer saying what is left after
    it; answers after a seeded random pause (shuffled when side by side). n_cc countries a day; the funnel empty for a
    day before `gone_before` or in `empty`; `fail`: a (day, first country of the group) whose call answers HTTP 500."""

    def __init__(self, n_cc=70, hour=40000, day=200000, thr=120, gone_before=None, empty=(), fail=None, seed=1,
                 proj=None, costs=None):
        self.ccs = ["Q%03d" % i for i in range(n_cc)]
        self.start = {"tokensPerDay": day, "tokensPerHour": hour, "tokensPerProjectPerHour": proj or int(hour * 0.35),
                      "potentiallyThresholdedRequestsPerHour": thr, "serverErrorsPerProjectPerHour": 10}
        self.left, self.lock, self.rnd = {}, threading.Lock(), random.Random(seed)
        self.gone_before, self.empty, self.fail = gone_before, set(empty), fail
        self.calls, self.live, self.peak, self.costs = [], {}, {}, costs

    def quota(self, pid, cost, thr):
        with self.lock:
            left = self.left.setdefault(pid, dict(self.start))
            for k in ("tokensPerDay", "tokensPerHour", "tokensPerProjectPerHour"):
                left[k] -= cost
            left["potentiallyThresholdedRequestsPerHour"] -= thr
            out = {k: {"consumed": cost if k.startswith("tokens") else thr, "remaining": v} for k, v in left.items()}
            out["serverErrorsPerProjectPerHour"] = {"consumed": 0, "remaining": left["serverErrorsPerProjectPerHour"]}
            return out

    def __call__(self, method, url, token, body=None, params=None):
        pid = url.split("/properties/")[1].split(":")[0]
        with self.lock:
            self.live[pid] = self.live.get(pid, 0) + 1
            self.peak[pid] = max(self.peak.get(pid, 0), self.live[pid])
            pause = self.rnd.random() * 0.004
        try:
            time.sleep(pause)
            return self.answer(pid, url, body)
        finally:
            with self.lock:
                self.live[pid] -= 1

    def answer(self, pid, url, body):
        a = date.fromisoformat(body["dateRanges"][0]["startDate"])
        if url.endswith(":runReport"):
            b = date.fromisoformat(body["dateRanges"][0]["endDate"])
            rows, d = [], a
            while d <= b:
                rows += [{"dimensionValues": [{"value": d.strftime("%Y%m%d")}, {"value": c}],
                          "metricValues": [{"value": str(1 + _h(pid, d, c) % 50)}]} for c in self.ccs
                         if _h(pid, d, c, "x") % 9]
                d += timedelta(days=1)
            off, lim = int(body.get("offset") or 0), int(body.get("limit") or 10000)
            with self.lock:
                self.calls.append((pid, "report", a.isoformat(), off))
            return {"dimensionHeaders": [{"name": "date"}, {"name": "countryId"}],
                    "metricHeaders": [{"name": "activeUsers"}], "rows": rows[off:off + lim], "rowCount": len(rows),
                    "propertyQuota": self.quota(pid, 40, 0)}
        dim = body["funnelBreakdown"]["breakdownDimension"]["name"]
        vals = (["total"] if dim == "date" else
                body["funnel"]["steps"][0]["filterExpression"]["andGroup"]["expressions"][1]["funnelFieldFilter"]
                ["inListFilter"]["values"])
        with self.lock:
            self.calls.append((pid, "funnel", a.isoformat(), vals[0]))
        if self.fail == (a.isoformat(), vals[0]):
            raise RuntimeError("HTTP 500: INTERNAL synthetic")
        q = self.quota(pid, (self.costs[dim != "date"] if self.costs else 60 + _h(pid, a, vals[0]) % 60), 1)
        if (self.gone_before and a < self.gone_before) or a in self.empty:
            return {"funnelTable": {"rows": []}, "propertyQuota": q}
        rows = []
        for v in vals:
            fo = 1 + _h(pid, a, v) % 50
            sp = fo * (_h(pid, a, v, 1) % 100) // 100
            hm = sp * (_h(pid, a, v, 2) % 100) // 100
            bv = "20261001" if dim == "date" else v
            rows += [{"dimensionValues": [{"value": s}, {"value": bv}], "metricValues": [{"value": str(x)}]}
                     for s, x in (("1. first_open", fo), ("2. splash", sp), ("3. step", hm)) if x]
        if dim != "date":
            rows.append({"dimensionValues": [{"value": "1. first_open"}, {"value": fc.RT}],
                         "metricValues": [{"value": "999"}]})
        return {"funnelTable": {"dimensionHeaders": [{"name": "funnelStepName"}, {"name": dim}],
                                "metricHeaders": [{"name": "activeUsers"}], "rows": rows,
                                "metadata": {"samplingMetadatas": [{"samplesReadCount": str(100 + _h(a) % 50),
                                                                    "samplingSpaceSize": "1000"}]}},
                "propertyQuota": q}


APPS = [("ca-app-pub-0000000000000000~1", "pkg.one", "P1"), ("ca-app-pub-0000000000000000~2", "pkg.two", "P1"),
        ("ca-app-pub-0000000000000000~3", "pkg.three", "P2")]


def _world(root, first=TODAY - timedelta(days=58), prev=None):
    """The First open stores (screens + day 1) of three apps on two properties, and the by-country stores `prev`."""
    data = str(root)
    for aid, pkg, pid in APPS:
        main = {"v": gf.STORE_V, "app_id": aid, "steps": STEPS, "time_zone": "UTC",
                "days": {first.isoformat(): {"first_open": 1}}}
        write_json_gz_stable(gf.store_path(data, aid), main)
        if prev:
            write_json_gz_stable(fc.store_path(data, aid), prev)
    return data


def _run(monkeypatch, data, api, batch, now=NOW, budget=fc.BUDGET_SEC):
    monkeypatch.setenv("GA4_FIRSTOPEN_CC_BATCH", str(batch))
    monkeypatch.setattr(fc.ga4, "_call", api)
    monkeypatch.setattr(fc.ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(fc.ga4, "access_token", lambda *a: "tok")
    monkeypatch.setattr(fc.ga4_probe, "owner_tokens", lambda env: ([("o", "rt")], None))
    routes = {pkg: {"property_id": pid, "stream_id": "s" + pkg, "owner": "o"} for _, pkg, pid in APPS}
    monkeypatch.setattr(gu, "load_state", lambda d: {"routes": {"by_package": routes}, "tz": {}})
    apps = [{"app_id": aid, "package": pkg} for aid, pkg, _ in APPS]
    return fc.refresh_all({"client_id": "c", "client_secret": "s", "refresh_tokens": "x"}, data, apps, now=now,
                          budget=budget)


def _files(data):
    out = {}
    d = os.path.join(data, fc.DIR)
    for n in sorted(os.listdir(d)):
        out[n] = open(os.path.join(d, n), "rb").read()
    return out


def _both(tmp_path, monkeypatch, make_api, runs=((NOW, fc.BUDGET_SEC),), cap=None, **world):
    """The same world read one at a time (A) and BATCH side by side (B), run after run → (A, B) per run."""
    if cap:
        monkeypatch.setattr(fc, "MAX_CALLS", cap)
    da, db = _world(tmp_path / "a", **world), _world(tmp_path / "b", **world)
    api_a, api_b = make_api(), make_api()
    res = []
    for now, budget in runs:
        oa = _run(monkeypatch, da, api_a, 1, now, budget)
        ob = _run(monkeypatch, db, api_b, fc.BATCH, now, budget)
        res.append((oa, ob, _files(da), _files(db)))
    return res, api_a, api_b


def _same(res, api_a, api_b, calls_equal=True, batched=True):
    for oa, ob, fa, fb in res:
        assert "error" not in oa and "error" not in ob
        if calls_equal:
            assert oa == ob
        else:                                                           # (the extra calls of a failed batch: counted)
            assert oa["apps"] == ob["apps"] and {k: v for k, v in oa["counts"].items() if k not in ("calls", "tokens")} \
                == {k: v for k, v in ob["counts"].items() if k not in ("calls", "tokens")}
        assert fa.keys() == fb.keys() and len(fa) >= 2
        for k in fa:
            assert fa[k] == fb[k], k
    if calls_equal:                                                     # the very same calls, property by property
        for pid in ("P1", "P2"):
            assert sorted(c for c in api_a.calls if c[0] == pid) == sorted(c for c in api_b.calls if c[0] == pid)
    assert max(api_a.peak.values()) == 1                                 # A: one call at a time a property
    assert not batched or max(api_b.peak.values()) > 1                    # B really asked side by side


def _days(data, aid):
    with gzip.open(fc.store_path(data, aid), "rt") as f:
        return json.load(f)["days"]


def test_no_quota_pressure_same_stores_state_and_calls(tmp_path, monkeypatch):
    res, a, b = _both(tmp_path, monkeypatch, lambda: GA4())
    _same(res, a, b)
    days = _days(str(tmp_path / "b"), APPS[0][0])
    assert len(days) >= 10 and all(len(v["c"]) > 40 for v in days.values() if "c" in v)
    assert res[0][0]["counts"]["days"] > 10


def test_an_hourly_floor_crossed_mid_day_stops_at_the_same_call(tmp_path, monkeypatch):
    """The hour bucket starts just above its floor: the one-at-a-time read stops inside a day (that day not kept, the
    app deferred, the property's next app too); side by side goes one at a time near the floor and stops there too."""
    for hour in (21500, 22400, 23300, 25000, 26000):
        res, a, b = _both(tmp_path / str(hour), monkeypatch, lambda h=hour: GA4(hour=h))
        _same(res, a, b, batched=hour >= 25000)
        assert res[0][0]["counts"]["deferred"] >= 1


def test_thresholded_requests_running_out(tmp_path, monkeypatch):
    res, a, b = _both(tmp_path, monkeypatch, lambda: GA4(thr=40))
    _same(res, a, b)
    assert res[0][0]["counts"]["deferred"] >= 1


def test_the_call_cap_gone_and_empty_days_and_the_recent_refresh_run_after_run(tmp_path, monkeypatch):
    runs = [(NOW + timedelta(hours=h), fc.BUDGET_SEC) for h in (0, 1, 7, 8)]
    res, a, b = _both(tmp_path, monkeypatch, lambda: GA4(gone_before=TODAY - timedelta(days=52),
                                                         empty={TODAY - timedelta(days=20)}), runs=runs, cap=33,
                      first=TODAY - timedelta(days=60))
    _same(res, a, b)
    days = _days(str(tmp_path / "b"), APPS[0][0])
    assert any(fc.is_gone(v) for v in days.values()) and (TODAY - timedelta(days=20)).isoformat() not in days
    assert any(r[0]["counts"]["deferred"] for r in res)                  # the cap stopped a run


@pytest.mark.parametrize("pressure", [False, True])
def test_a_failing_call_fails_the_app_the_same(tmp_path, monkeypatch, pressure):
    """A call answering HTTP 500 (after ga4._call's own retry): the app fails at that day either way (the days before it
    kept, that day not). Side by side, the rest of that batch was already asked: with room in the quota every byte is
    the same; under quota pressure those calls' tokens can stop a later app of the property a little earlier this run
    (fewer new days — never another value)."""
    def api():
        g = GA4(hour=40000 if pressure else 10 ** 6, proj=None if pressure else 10 ** 6, day=10 ** 7)
        bad = (TODAY - timedelta(days=50)).isoformat()
        cc = fc.countries(type("R", (), {"report_all": lambda self, body, event=None: [
            {"date": r["dimensionValues"][0]["value"], "countryId": r["dimensionValues"][1]["value"],
             "activeUsers": r["metricValues"][0]["value"]}
            for r in g.answer("P1", ":runReport", body)["rows"]]})(), date.fromisoformat(bad), date.fromisoformat(bad))
        order = sorted(cc[bad], key=lambda k: (-cc[bad][k], k))
        g.fail, g.left = (bad, min(order[fc.GROUP * 2:fc.GROUP * 3])), {}  # the 3rd group of that day answers 500
        g.calls.clear()
        return g
    res, a, b = _both(tmp_path, monkeypatch, api)
    st = json.loads(res[0][2]["state.json"])
    assert sum(1 for v in st["fetch"].values() if v.get("fail")) >= 2  # (both apps of P1 share the failing property)
    if not pressure:
        _same(res, a, b, calls_equal=False)                             # side by side asked the rest of that batch
        return
    oa, ob, fa, fb = res[0]
    assert oa["apps"] == ob["apps"] and fa["state.json"] == fb["state.json"]
    for aid, _, _ in APPS:                                              # every day both read: the same record
        da, db = _days(str(tmp_path / "a"), aid), _days(str(tmp_path / "b"), aid)
        assert {k: v for k, v in da.items() if k in db} == {k: v for k, v in db.items() if k in da}
        assert len(db) >= len(da) - 2


@pytest.mark.parametrize("floor", ["proj", "hour"])
def test_a_cheap_days_total_never_sizes_the_margin_of_costlier_group_calls(tmp_path, monkeypatch, floor):
    """The day's total funnel (a date breakdown) is another query than its group calls (a country list + breakdown): a
    total of 30 tokens, every group call 150 (more than twice the total). The margin comes from group calls only — each
    App's first group call goes alone and is measured — so near the project-hour or the hour floor side by side stops at
    the very call one at a time stops at: the same stores, state, counts and calls."""
    edges = range(7100, 8600, 50) if floor == "proj" else range(20000, 21700, 50)
    batched = False
    for v in edges:
        kw = dict(proj=v, hour=10 ** 6) if floor == "proj" else dict(hour=v, proj=10 ** 6)
        res, a, b = _both(tmp_path / str(v), monkeypatch, lambda kw=kw: GA4(day=10 ** 7, costs=(30, 150), **kw))
        _same(res, a, b, batched=False)
        batched = batched or max(b.peak.values()) > 1
    assert batched                                                      # (side by side where there was room)
    ga = gf.App("t", "P", "s", {"quota": None, "stop": None}, over=lambda: None, max_calls=100)
    ga.over.left = lambda: 1000.0
    monkeypatch.setattr(fc.ga4, "_call", GA4(costs=(30, 150)))
    monkeypatch.setattr(fc.ga4, "_sleep", lambda s: None)
    ga.funnel(gf.funnel_body("S", "H", TODAY, TODAY, "date"))
    assert ga.f_tok is None and not ga.batch_ok(2)                      # a total call measures nothing
    ga.funnel(fc.group_body("S", "H", TODAY, ["Q000", "Q001"]), measure=True)
    assert ga.f_tok == 150 and ga.batch_ok(2)


def test_properties_side_by_side_from_the_env(tmp_path, monkeypatch):
    """GA4_FIRSTOPEN_CC_WORKERS (a repo variable): 6 reads 6 properties side by side, as before this change — with
    GA4_FIRSTOPEN_CC_BATCH=1 the old call pattern without a code push; empty or not a number: WORKERS."""
    for v, want in (("", fc.WORKERS), ("6", 6), ("x", fc.WORKERS), ("0", 1)):
        monkeypatch.setenv("GA4_FIRSTOPEN_CC_WORKERS", v)
        assert fc._workers() == want
    seen, real = [], fc.ThreadPoolExecutor
    monkeypatch.setattr(fc, "ThreadPoolExecutor", lambda max_workers: seen.append(max_workers) or real(max_workers))
    for v in ("6", ""):
        monkeypatch.setenv("GA4_FIRSTOPEN_CC_WORKERS", v)
        assert "error" not in _run(monkeypatch, _world(tmp_path / ("w" + v)), GA4(), 1)
    assert seen == [6, fc.WORKERS]


def test_tight_budget_never_batches_past_it(monkeypatch):
    """batch_ok: the run's seconds left must cover the batch at twice the slowest call; nothing measured: never."""
    t = [0.0]
    ga = gf.App("t", "P", "s", {"quota": None, "stop": None}, over=None, max_calls=100)
    assert not ga.batch_ok(5)                                            # no clock to ask
    over = lambda: "budget" if t[0] >= 10 else None                    # noqa: E731
    over.left = lambda: 10 - t[0]
    ga = gf.App("t", "P", "s", {"quota": None, "stop": None}, over=over, max_calls=100)
    assert not ga.batch_ok(5)                                            # nothing measured yet
    ga.f_sec, ga.f_tok = 0.5, 80
    assert ga.batch_ok(5) and not ga.batch_ok(1)
    t[0] = 4.0                                                           # 6 s left < 5 × (2 × 0.5 + 0.2) + 1
    assert not ga.batch_ok(5) and ga.batch_ok(2)
    ga.calls = 99
    assert not ga.batch_ok(2)                                            # the cap
    ga.calls, ga.prop["stop"] = 0, "hour_low"
    assert not ga.batch_ok(2)


def test_quota_check_is_the_one_at_a_time_gate_after_n_minus_1_calls_of_twice_the_cost():
    from admob_iq.fetch import ga4_audience as gaud
    over = lambda: None                                                # noqa: E731
    over.left = lambda: 1000.0
    for rem in range(19000, 23000, 37):
        q = {"tokensPerHour": {"consumed": 90, "remaining": rem}, "tokensPerDay": {"consumed": 90, "remaining": 150000},
             "tokensPerProjectPerHour": {"consumed": 90, "remaining": 9000},
             "potentiallyThresholdedRequestsPerHour": {"consumed": 1, "remaining": 50}}
        ga = gf.App("t", "P", "s", {"quota": q, "stop": None}, over=over, max_calls=100)
        ga.f_sec, ga.f_tok = 0.1, 100
        ok = ga.batch_ok(5)
        if ok:                                                           # every one of the 5 would have gone, even at
            for k in range(5):                                           # 200 tokens each (and its size grown by it)
                w = json.loads(json.dumps(q))
                w["tokensPerHour"] = {"consumed": 200, "remaining": rem - 200 * k}
                assert gaud.quota_stop(w) is None
        else:
            assert gaud.quota_stop(q) is not None or rem - 4 * 200 < 0.5 * 40000 + 400
