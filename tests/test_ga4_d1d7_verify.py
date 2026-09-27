"""GA4 D1/D7 day-by-day verify (admob_iq.fetch.ga4_d1d7_verify) — offline, against a fake GA4 Data API (requests
mocked) and private stores written to a temp folder: one owner-style single-day report per activity day, every install
day × D1..D30 classified against the stored "ret" cohorts (match / mismatch / store_not_final / missing / short /
not ok / too small / no GA4 row / unread / not due), the completeness check, the property-level quota, 5xx and
budget rules (pause vs stop), token refresh, incremental private writes, resume, and a PUBLIC log that stays
counts-only."""

import json
import os
import re
import threading
from datetime import date, datetime, timedelta, timezone

import pytest
import yaml

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_d1d7_verify as vr
from admob_iq.fetch import ga4_uninstall as gu

NOW = datetime(2026, 9, 27, 6, 0, tzinfo=timezone.utc)
TODAY = date(2026, 9, 27)
WE = date(2026, 9, 25)                          # the stores' window_end (today − 2)
LAST = date(2026, 9, 24)                        # the last activity day asked: min(window_end, today − 3)
AT = "2026-09-27"                               # the day the build read the recent cohorts
EMAIL_A, EMAIL_B = "owner.a@secret-ws.test", "owner.b@secret-ws.test"
RT_A, RT_B = "rt-SECRET-a", "rt-SECRET-b"
TOK_A, TOK_B = "tok-SECRET-a", "tok-SECRET-b"
PID_A, PID_B, PID_C = "987654321", "123123123", "555666777"
SID_A, SID_A2, SID_B, SID_C = "5550001111", "5550001112", "5550002222", "5550003333"
PKG_A, PKG_A2, PKG_B, PKG_C = "com.secret.big", "com.secret.second", "com.secret.lossy", "com.secret.small"
AID_A, AID_AT, AID_A2, AID_B, AID_C = ("ca-app-pub-1111111111111111~%d" % i for i in (1, 9, 5, 2, 3))
SECRETS = [EMAIL_A, EMAIL_B, RT_A, RT_B, TOK_A, TOK_B, PID_A, PID_B, PID_C, SID_A, SID_A2, SID_B, SID_C, PKG_A,
           PKG_A2, PKG_B, PKG_C, AID_A, AID_AT, AID_A2, AID_B, AID_C, "secret", "SECRETDETAIL"]


def ymd(d):
    return d.strftime("%Y%m%d")


def span(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


class Truth:
    """One stream's GA4 reality: n(X) installs on day X (special days override), A(X, k) = n·0.4/(1+0.3k) of them active
    k days later (all of them on day 0), 2 old users from every 10th install day, 1 "(not set)" user a day; `other` days
    add an "(other)" row, `thresh` days come back subject to thresholding. lossy_before: activity days before it answer
    every first-session row at 30% (a split that lost users)."""

    def __init__(self, start, base, special=None, lossy_before=None, other=(), thresh=()):
        self.start, self.base, self.special = start, base, dict(special or {})
        self.lossy_before, self.other, self.thresh = lossy_before, set(other), set(thresh)

    def n(self, x):
        if x < self.start:
            return 0
        return self.special.get(x, self.base + (x.toordinal() % 7) * 10)

    def A(self, x, k):
        return self.n(x) if k == 0 else round(self.n(x) * 0.4 / (1 + 0.3 * k))

    def true_cells(self, d):
        out = {}
        if d < self.start:
            return out
        for x in span(self.start, d):
            k = (d - x).days
            a = self.A(x, k) if k <= 30 else (2 if (x - self.start).days % 10 == 0 else 0)
            if a:
                out[ymd(x)] = [a, self.n(x) if k == 0 else 0]
        out["(not set)"] = [1, 0]
        if d in self.other:
            out["(other)"] = [3, 0]
        return out

    def cells(self, d):
        c = self.true_cells(d)
        if self.lossy_before and d < self.lossy_before:
            c = {f: [v[0] * 3 // 10, v[1] * 3 // 10] for f, v in c.items()}
        return c

    def a1(self, d):
        return sum(v[0] for v in self.true_cells(d).values())


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
    """runReport only: one-day firstSessionDate reports, paged by limit/offset, with each property's quota. Hooks:
    fail(pid, day, n) → HTTP status | None; hourly(pid, n) → tokensPerProjectPerHour remaining; daily(pid, n) →
    tokensPerDay remaining; on_post(pid, n) (e.g. moves the clock); valid tokens (a stale one gets a 401)."""

    def __init__(self, truths, fail=None, hourly=None, daily=None, on_post=None, valid=(TOK_A, TOK_B)):
        self.truths = truths                        # (pid, sid) → Truth
        self.bodies, self.lock = [], threading.Lock()
        self.fail, self.hourly, self.daily, self.on_post = fail, hourly, daily, on_post
        self.valid, self.n = set(valid), {}

    def post(self, url, headers=None, json=None, timeout=None):
        pid = url.split("/properties/")[1].split(":")[0]
        assert url.endswith(":runReport")
        with self.lock:
            self.bodies.append((pid, json))
            n = self.n[pid] = self.n.get(pid, 0) + 1
        if self.on_post:
            self.on_post(pid, n)
        if headers["Authorization"][len("Bearer "):] not in self.valid:
            return Resp(401, {"error": {"code": 401, "status": "UNAUTHENTICATED", "message": "SECRETDETAIL"}})
        ex = json["dimensionFilter"]["andGroup"]["expressions"]
        pinned = {(e["filter"]["fieldName"], e["filter"]["stringFilter"]["value"]) for e in ex}
        sid = next(v for f, v in pinned if f == "streamId")
        assert ("platform", "Android") in pinned and json.get("returnPropertyQuota") is True
        (rg,) = json["dateRanges"]
        assert rg["startDate"] == rg["endDate"]
        d = date.fromisoformat(rg["startDate"])
        st = self.fail(pid, d, n) if self.fail else None
        if st:
            return Resp(st, {"error": {"code": st, "status": "INTERNAL" if st >= 500 else "INVALID_ARGUMENT",
                                       "message": "bad SECRETDETAIL " + pid}})
        t = self.truths[(pid, sid)]
        assert [x["name"] for x in json["dimensions"]] == ["firstSessionDate"]
        assert [x["name"] for x in json["metrics"]] == ["activeUsers", "newUsers"]
        rows = sorted(t.cells(d).items())
        off, lim = int(json.get("offset") or 0), int(json["limit"])
        q = {"tokensPerDay": {"consumed": 5, "remaining": self.daily(pid, n) if self.daily else 200000 - 5 * n},
             "tokensPerProjectPerHour": {"consumed": 5, "remaining": self.hourly(pid, n) if self.hourly else 13000}}
        return Resp(body={"dimensionHeaders": [{"name": "firstSessionDate"}],
                          "metricHeaders": [{"name": "activeUsers"}, {"name": "newUsers"}],
                          "rows": [{"dimensionValues": [{"value": f}],
                                    "metricValues": [{"value": str(a)}, {"value": str(nn)}]}
                                   for f, (a, nn) in rows[off:off + lim]],
                          "rowCount": len(rows), "propertyQuota": q,
                          "metadata": {"currencyCode": "USD", "subjectToThresholding": d in t.thresh}})

    def days_asked(self, pid):
        return [b["dateRanges"][0]["startDate"] for p, b in self.bodies if p == pid]


# ── the private data: three streams (A has two AdMob app ids), their stores and the build's state ────────────────

HS_A, HS_B, HS_C = TODAY - timedelta(days=120), TODAY - timedelta(days=60), TODAY - timedelta(days=20)
X_SIZE, X_SHORT, X_MIS, X_MISS, X_NOTOK, X_SMALL, X_ZERO, X_TOL = (HS_A + timedelta(days=i)
                                                                  for i in (20, 30, 40, 50, 60, 70, 80, 90))
X_NF = date(2026, 9, 22)                        # D1 on 23 Sep: after the store's read day − 5 → not final
X_MIS7 = date(2026, 9, 15)                      # D7 on 22 Sep: exactly the read day − 5 → final: a real mismatch
TH_DAY, OTHER_DAY = HS_A + timedelta(days=33), HS_A + timedelta(days=44)
TRUTH_A = Truth(HS_A, 100, special={X_SMALL: 10, X_ZERO: 0, X_TOL: 1000}, other=[OTHER_DAY], thresh=[TH_DAY])
TRUTH_B = Truth(HS_B, 100, lossy_before=TODAY - timedelta(days=30))
TRUTH_C = Truth(HS_C, 30)
TRUTH_A2 = Truth(TODAY - timedelta(days=40), 50)


def make_store(t, hs, pid, sid, faults=True):
    daily = {d.isoformat(): {"new": t.n(d), "a1": t.a1(d), "un": 0} for d in span(hs, WE)}
    ret = {}
    for x in span(hs, WE):
        m = min(30, (WE - x).days)
        ret[x.isoformat()] = {"t": t.n(x), "a": [t.A(x, k) for k in range(m + 1)], "ok": True, "cov": 1.0, "at": AT}
    if faults:
        r = ret
        r[X_SIZE.isoformat()]["t"] = round(t.n(X_SIZE) * 1.05)
        r[X_SHORT.isoformat()]["a"] = r[X_SHORT.isoformat()]["a"][:3]
        r[X_MIS.isoformat()]["a"][1] = round(r[X_MIS.isoformat()]["a"][1] * 1.3)
        del r[X_MISS.isoformat()]
        r[X_NOTOK.isoformat()]["ok"] = False
        r[X_TOL.isoformat()]["a"][7] += 1
        r[X_NF.isoformat()]["a"][1] = round(r[X_NF.isoformat()]["a"][1] * 0.8)
        r[X_MIS7.isoformat()]["a"][7] = round(r[X_MIS7.isoformat()]["a"][7] * 0.8)
    return {"v": 3, "history_start": hs.isoformat(), "window_end": WE.isoformat(), "property_id": pid,
            "stream_id": sid, "time_zone": "UTC", "daily": daily, "ret": ret,
            "ret_from": (hs + timedelta(days=5)).isoformat(), "ret_to": hs.isoformat(),
            "flags": {"impact": {"ret_k": 1.0}}}


APPS = [  # package, property, stream, owner, AdMob app ids, truth, history start, faults
    (PKG_A, PID_A, SID_A, EMAIL_A, [AID_A, AID_AT], TRUTH_A, HS_A, True),
    (PKG_B, PID_B, SID_B, EMAIL_B, [AID_B], TRUTH_B, HS_B, False),
    (PKG_C, PID_C, SID_C, EMAIL_A, [AID_C], TRUTH_C, HS_C, False)]
TRUTHS = {(PID_A, SID_A): TRUTH_A, (PID_B, SID_B): TRUTH_B, (PID_C, SID_C): TRUTH_C, (PID_A, SID_A2): TRUTH_A2}
TOKENS = [(EMAIL_A, RT_A), (EMAIL_B, RT_B)]


def write_world(root, apps=APPS):
    data = os.path.join(str(root), "data")
    state = {"routes": {"by_package": {}}, "tz": {}, "fetch": {}}
    for pkg, pid, sid, owner, aids, t, hs, faults in apps:
        state["routes"]["by_package"][pkg] = {"property_id": pid, "stream_id": sid, "owner": owner}
        state["tz"][pid] = "UTC"
        for aid in aids:
            st = make_store(t, hs, pid, sid, faults)
            gu.save_store(gu.store_path(data, aid), st)
            state["fetch"][aid] = {"package": pkg, "meta": gu.store_meta(st)}
    state["fetch"]["ca-app-pub-1111111111111111~7"] = {"package": "com.secret.noroute"}
    gu.save_state(data, state)
    return data


class Clock:
    def __init__(self):
        self.t, self.slept = 0.0, []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


@pytest.fixture
def world(tmp_path, monkeypatch):
    """→ make(apps=APPS, **fake hooks) → (fake GA4, data dir, units)."""
    refreshed = []

    def make(apps=APPS, tokens=None, **kw):
        data = write_world(tmp_path, apps)
        f = FakeGA4(TRUTHS, **kw)
        monkeypatch.setattr(ga4.requests, "post", f.post)
        seq = {RT_A: iter(tokens or [TOK_A] * 100), RT_B: iter([TOK_B] * 100)}

        def access_token(cid, sec, rt):
            refreshed.append(rt)
            return next(seq[rt])
        monkeypatch.setattr(ga4, "access_token", access_token)
        f.refreshed = refreshed
        return f, data, vr.units_from_state(gu.load_state(data))
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    return make


def _run(units, data, clock=None, carried=None, **kw):
    clock = clock or Clock()
    return vr.run_verify(units, carried or {}, "cid", "sec", TOKENS, data, now=NOW, clock=clock, sleeper=clock.sleep,
                         **kw)


def _store(rep, pkg, aid):
    return rep["apps"][pkg]["stores"][aid]


# ── the app list, the order ──────────────────────────────────────────────────────────────────────

def test_units_are_the_builds_streams_with_every_admob_app_id_of_each(world):
    _, _, units = world()
    assert [(u["package"], u["app_ids"]) for u in units] == [(PKG_A, [AID_A, AID_AT]), (PKG_B, [AID_B]),
                                                             (PKG_C, [AID_C])]     # no route → left out
    assert [u["days"] for u in units] == [119, 59, 19]           # history_start .. window_end, from the state's meta
    assert vr.units_from_state(None) == []


def test_big_and_small_apps_are_interleaved_and_a_property_is_one_group():
    us = [{"package": p, "property_id": pid, "days": d} for p, pid, d in
          (("a", "1", 900), ("b", "2", 10), ("c", "3", 500), ("d", "4", 50), ("e", "1", 5), ("f", "5", 300))]
    groups = vr.order_groups(us)
    assert [[u["package"] for u in g] for g in groups] == [["a", "e"], ["b"], ["c"], ["d"], ["f"]]
    assert vr.interleave([1, 5, 3, 2, 4], lambda v: v) == [5, 1, 4, 2, 3]


def test_plan_resumes_skips_complete_apps_caps_to_the_smallest_and_never_drops_old_results(world):
    _, _, units = world()
    old = {"apps": {PKG_A: {"complete": True, "m": 1}, PKG_B: {"complete": False, "m": 2}, "gone.pkg": {"m": 3}}}
    todo, carried = vr.plan_units(units, old, True, 0)
    assert [u["package"] for u in todo] == [PKG_B, PKG_C] and carried == {PKG_A: old["apps"][PKG_A]}
    todo, carried = vr.plan_units(units, old, False, 0)
    assert [u["package"] for u in todo] == [PKG_A, PKG_B, PKG_C] and carried == {}
    todo, carried = vr.plan_units(units, old, False, 1)                 # a quick trial: the smallest app only
    assert [u["package"] for u in todo] == [PKG_C] and set(carried) == {PKG_A, PKG_B}
    assert vr.plan_units(units, None, True, 0)[0] == units


# ── the rules ────────────────────────────────────────────────────────────────────────────────────

def test_the_match_rules():
    assert vr.judge(102, 1000, 100, 1000) == (True, True)            # 2 users: the floor
    assert vr.judge(103, 1000, 100, 1000) == (False, True)           # 3 users over 100, rate +0.3 pp
    assert vr.judge(510, 1000, 500, 1000) == (True, False)           # 2% of 500 = 10 users, but +1.0 pp
    assert vr.judge(300, 1050, 300, 1000) == (True, False)           # cohort size 5% high: the rate moves 1.4 pp
    assert vr.judge(5, 0, 5, 100) == (True, False)                   # no cohort size: no rate
    assert vr.ranges([date(2026, 1, 3), date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 9)]) == \
        {"days": 4, "runs": [["2026-01-01", "2026-01-03"], ["2026-01-09", "2026-01-09"]]}
    assert vr.ranges([date(2026, 1, 1) + timedelta(days=2 * i) for i in range(5)], cap=2)["cut"] == 3


def test_the_quota_gate_pauses_on_hourly_buckets_and_stops_on_the_daily_one():
    assert vr.quota_gate(None) is None
    assert vr.quota_gate({"tokensPerDay": {"consumed": 5, "remaining": 150000},
                          "tokensPerProjectPerHour": {"consumed": 5, "remaining": 7100}}) is None
    assert vr.quota_gate({"tokensPerDay": {"consumed": 5, "remaining": 99000}}) == "stop"
    assert vr.quota_gate({"tokensPerProjectPerHour": {"consumed": 5, "remaining": 6900}}) == "wait"
    assert vr.quota_gate({"tokensPerHour": {"consumed": 5, "remaining": 19000}}) == "wait"
    assert vr.quota_gate({"tokensPerProjectPerHour": {"consumed": 5, "remaining": 3400}}) == "stop"
    assert vr.quota_gate({"serverErrorsPerProjectPerHour": {"consumed": 1, "remaining": 4}}) == "wait"
    assert vr.quota_gate({"serverErrorsPerProjectPerHour": {"consumed": 0, "remaining": 5}}) is None
    assert vr.quota_gate({"serverErrorsPerProjectPerHour": {"consumed": 1, "remaining": 2}}) == "stop"
    assert vr.quota_gate({"potentiallyThresholdedRequestsPerHour": {"consumed": 1, "remaining": 2}}) == "stop"
    # thousands of calls: the thresholded-request count keeps the build's HALF too (not the probe's 5 left)
    assert vr.quota_gate({"potentiallyThresholdedRequestsPerHour": {"consumed": 0, "remaining": 60}}) is None
    assert vr.quota_gate({"potentiallyThresholdedRequestsPerHour": {"consumed": 1, "remaining": 59}}) == "wait"
    assert vr.quota_gate({"potentiallyThresholdedRequestsPerHour": {"consumed": 1, "remaining": 29}}) == "stop"


# ── the check itself ─────────────────────────────────────────────────────────────────────────────

def test_every_install_day_is_classified_day_by_day_against_the_owner_method(world):
    f, data, units = world()
    rep = _run(units, data)
    a = rep["apps"][PKG_A]
    assert a["complete"] and a["stopped"] is None and a["last_asked"] == LAST.isoformat()
    assert f.days_asked(PID_A) == [d.isoformat() for d in span(HS_A, LAST)]          # one call per activity day
    assert a["calls"] == len(span(HS_A, LAST)) == 118 and a["tokens"] == 5 * 118
    for aid in (AID_A, AID_AT):                                                       # one GA4 read, both stores
        s = _store(rep, PKG_A, aid)
        assert s["install_days"] == 118 and s["ret_days"] == 117 and s["ret_outside_window"] == 0
        assert s["d1"] == {"match": 110, "mismatch": 2, "store_not_final": 1, "missing_in_store": 1,
                           "short_in_store": 0, "not_ok_in_store": 1, "too_small": 1, "no_ga4_row": 1, "unread": 0,
                           "not_due": 1}
        assert s["d7"] == {"match": 104, "mismatch": 2, "store_not_final": 0, "missing_in_store": 1,
                           "short_in_store": 1, "not_ok_in_store": 1, "too_small": 1, "no_ga4_row": 1, "unread": 0,
                           "not_due": 7}
        assert sum(s["all_k"].values()) == 118 * 30 and all(sum(c.values()) == 118 for c in s["by_k"].values())
        assert s["rules"]["d1"] == {"judged": 113, "users_ok": 111, "rate_ok": 110, "fail_users_only": 0,
                                    "fail_rate_only": 1, "fail_both": 2,             # X_SIZE: users fine, rate not
                                    "fail_on_flagged_day": 0}
        assert s["would_match"]["d1"] == {"not_ok_in_store": {"match": 1, "of": 1}, "too_small": {"match": 1, "of": 1}}
        # what the tab shows: ok, t > 0, a[0]/t in [0.9, 1.1], on / after ret_from
        assert s["tab"] == {"used": 110, "no_entry": 1, "not_ok": 1, "t0": 1, "a0_off": 0, "before_ret_from": 5}
        assert s["shown"]["d1"] == {"match": 105, "mismatch": 2, "store_not_final": 1}
    s = _store(rep, PKG_A, AID_A)
    w = s["worst"][0]
    assert (w["x"], w["k"], w["class"]) == (X_MIS.isoformat(), 1, "mismatch") and w["pp"] > 5 and w["users"] > 0
    assert {(m["x"], m["k"]) for m in s["worst"]} == {(X_MIS.isoformat(), 1), (X_SIZE.isoformat(), 1),
                                                      (X_SIZE.isoformat(), 7), (X_MIS7.isoformat(), 7)}
    assert all(m["class"] == "mismatch" for m in s["worst_any_k"])
    assert s["gaps"]["d1"]["missing_in_store"]["runs"] == [[X_MISS.isoformat()] * 2]
    assert s["gaps"]["d7"]["not_due"]["runs"] == [["2026-09-18", LAST.isoformat()]]
    assert s["gap_days"] == {"days": 2, "runs": [[X_SHORT.isoformat()] * 2, [X_MISS.isoformat()] * 2]}
    assert s["daily_missing"]["days"] == 0
    assert s["size"]["n"] == 115 and s["size"]["within"] == 114 and s["size"]["worst"][0][0] == X_SIZE.isoformat()
    assert s["daily_new_vs_N"]["within"] == s["daily_new_vs_N"]["n"] == 116    # a missing ret entry too
    rows = {r[0]: dict(zip(s["table"]["cols"], r)) for r in s["table"]["rows"]}
    assert len(rows) == 118 and min(rows) == HS_A.isoformat() and max(rows) == LAST.isoformat()
    r = rows[X_MIS.isoformat()]
    assert (r["c1"], r["c7"], r["N"], r["t"], r["A1"]) == ("x", "m", TRUTH_A.n(X_MIS), TRUTH_A.n(X_MIS),
                                                          TRUTH_A.A(X_MIS, 1))
    assert r["a1"] == round(TRUTH_A.A(X_MIS, 1) * 1.3) and r["k_mismatch"] == 1 and r["k_judged"] == 30
    assert (rows[X_NF.isoformat()]["c1"], rows[X_NF.isoformat()]["c7"]) == ("f", "d")
    assert rows[X_MIS7.isoformat()]["c7"] == "x" and rows[X_TOL.isoformat()]["c7"] == "m"
    assert (rows[X_ZERO.isoformat()]["c1"], rows[X_SMALL.isoformat()]["c1"], rows[X_NOTOK.isoformat()]["c1"],
            rows[X_MISS.isoformat()]["c1"], rows[X_SHORT.isoformat()]["c7"]) == ("n", "z", "o", "M", "s")
    assert rows[X_MISS.isoformat()]["t"] is None and rows[X_MISS.isoformat()]["tab_uses"] == 0
    act = a["activity"]
    assert act["read"] == act["days"] == 118 and act["unread"]["days"] == 0 and act["errors"] == {}
    assert act["cov"]["min"] == act["cov"]["max"] == 1.0 and act["cov_low"]["days"] == 0
    assert act["thresholded"]["runs"] == [[TH_DAY.isoformat()] * 2]
    assert act["with_other"]["runs"] == [[OTHER_DAY.isoformat()] * 2]
    assert act["new_cov"]["within"] == act["new_cov"]["n"] and act["new_elsewhere_share"] == 0
    c = rep["apps"][PKG_C]
    sc = _store(rep, PKG_C, AID_C)
    assert c["complete"] and sc["d1"]["match"] == 17 and sc["d1"]["not_due"] == 1 and sc["d7"]["match"] == 11
    assert rep["counts"]["apps_complete"] == 3 and rep["counts"]["install_days"] == 2 * 118 + 58 + 18
    json.loads(vr.pr._dump(rep))


def test_a_split_that_lost_users_is_flagged_and_never_counted_as_a_match(world):
    f, data, units = world()
    rep = _run([u for u in units if u["package"] == PKG_B], data)
    b, s = rep["apps"][PKG_B], _store(rep, PKG_B, AID_B)
    lossy = TODAY - timedelta(days=30)
    assert b["activity"]["cov"]["min"] < 0.35 and b["activity"]["cov_low"]["runs"] == \
        [[HS_B.isoformat(), (lossy - timedelta(days=1)).isoformat()]]
    rows = {r[0]: dict(zip(s["table"]["cols"], r)) for r in s["table"]["rows"]}
    old = [r for x, r in rows.items() if date.fromisoformat(x) + timedelta(days=1) < lossy]
    assert old and all(r["c1"] == "x" for r in old)                  # users 30% short: never a match
    assert all(r["c1"] == "m" for x, r in rows.items() if lossy <= date.fromisoformat(x) < LAST)
    assert s["size"]["within"] < s["size"]["n"]


def test_request_bodies_are_single_days_paged_to_the_last_row(world, monkeypatch):
    monkeypatch.setattr(vr, "PAGE_ROWS", 7)
    f, data, units = world()
    rep = _run([u for u in units if u["package"] == PKG_C], data)
    bodies = [b for _, b in f.bodies]
    assert rep["apps"][PKG_C]["complete"] and rep["apps"][PKG_C]["activity"]["pages_max"] > 1
    for b in bodies:
        assert set(b) == {"dateRanges", "dimensions", "metrics", "dimensionFilter", "returnPropertyQuota", "limit",
                          "offset", "orderBys"}
        assert b["limit"] == 7 and b["orderBys"] == [{"dimension": {"dimensionName": "firstSessionDate"}}]
    assert len(bodies) > len(span(HS_C, LAST))
    assert _store(rep, PKG_C, AID_C)["d1"]["match"] == 17            # the paged read is whole


# ── quota, server errors, tokens, budget ────────────────────────────────────────────────────────

def test_an_hourly_bucket_under_half_pauses_the_property_and_it_goes_on(world):
    clock = Clock()
    f, data, units = world(hourly=lambda pid, n: 6000 if n == 3 else 13000)
    rep = _run([u for u in units if u["package"] == PKG_C], data, clock=clock)
    c = rep["apps"][PKG_C]
    assert c["complete"] and c["prop_waits"] == 1 and c["prop_wait_sec"] == vr.WAIT_SEC
    assert sum(clock.slept) == vr.WAIT_SEC and max(clock.slept) <= 30         # slept in steps, heartbeat between
    assert len(f.bodies) == len(span(HS_C, LAST))


def test_the_daily_bucket_or_a_quarter_hourly_stops_the_property_and_its_other_apps(world):
    second = (PKG_A2, PID_A, SID_A2, EMAIL_A, [AID_A2], TRUTH_A2, TRUTH_A2.start, False)
    f, data, units = world(apps=APPS + [second], daily=lambda pid, n: 99000 if pid == PID_A else 150000)
    rep = _run(units, data)
    assert sum(1 for p, _ in f.bodies if p == PID_A) == 1                     # the second app never asks
    for pkg in (PKG_A, PKG_A2):
        a = rep["apps"][pkg]
        assert a["stopped"] == "quota_low" and not a["complete"]
    s = _store(rep, PKG_A, AID_A)
    assert s["d1"]["unread"] == 117 and s["d1"]["match"] == 0 and s["gap_days"]["days"] >= 117
    assert rep["apps"][PKG_B]["complete"] and rep["counts"]["stopped"] == 2
    f, data, units = world(hourly=lambda pid, n: 3000 if n >= 3 else 13000)
    rep = _run([u for u in units if u["package"] == PKG_C], data)
    assert rep["apps"][PKG_C]["stopped"] == "quota_low" and len(f.bodies) == 3


def test_server_errors_pause_the_property_for_the_hour_and_failed_days_are_asked_again(world):
    clock = Clock()
    bad = {HS_C + timedelta(days=2), HS_C + timedelta(days=3)}
    seen = {}

    def fail(pid, d, n):
        seen[d] = seen.get(d, 0) + 1
        return 500 if d in bad and seen[d] <= 2 else None           # both tries of the first call; fine later
    f, data, units = world(fail=fail)
    rep = _run([u for u in units if u["package"] == PKG_C], data, clock=clock)
    c = rep["apps"][PKG_C]
    assert c["complete"] and c["prop_server_errors"] == 2 and c["prop_waits"] == 1
    assert c["prop_wait_sec"] == 3600 and sum(clock.slept) == 3600
    assert _store(rep, PKG_C, AID_C)["d1"]["unread"] == 0 and c["activity"]["errors"] == {}
    assert "SECRETDETAIL" not in json.dumps(rep)


def test_server_errors_stop_the_property_after_six_failed_calls_and_keep_only_the_class(world):
    clock = Clock()
    f, data, units = world(fail=lambda pid, d, n: 500 if d.toordinal() % 2 == 0 else None)
    rep = _run([u for u in units if u["package"] == PKG_C], data, clock=clock)
    c = rep["apps"][PKG_C]
    assert c["stopped"] == "server_errors" and c["prop_server_errors"] == 6 and not c["complete"]
    assert sum(1 for _ in f.bodies) == 6 * 2 + 5                      # each failed call retried once by ga4._call
    assert c["activity"]["errors"] == {"http_500": 6} and "SECRETDETAIL" not in json.dumps(rep)
    assert _store(rep, PKG_C, AID_C)["d1"]["unread"] > 0


def test_a_request_ga4_keeps_refusing_stops_that_app_after_five_days(world):
    f, data, units = world(fail=lambda pid, d, n: 400 if pid == PID_C else None)
    rep = _run(units, data)
    assert rep["apps"][PKG_C]["stopped"] == "errors" and len(f.days_asked(PID_C)) == 5
    assert rep["apps"][PKG_A]["complete"]


def test_an_expired_access_token_is_refreshed_once_and_the_call_goes_on(world):
    f, data, units = world(tokens=["tok-SECRET-old", TOK_A])
    f.valid = {TOK_A, TOK_B}                                          # the first token is already stale
    rep = _run([u for u in units if u["package"] == PKG_C], data)
    assert rep["apps"][PKG_C]["complete"] and f.refreshed == [RT_A, RT_A]
    clock = Clock()
    f, data, units = world(on_post=lambda pid, n: setattr(clock, "t", clock.t + 60))
    del f.refreshed[:]
    rep = _run([u for u in units if u["package"] == PKG_C], data, clock=clock)
    assert rep["apps"][PKG_C]["complete"] and len(f.refreshed) == 1           # 18 min: no refresh needed
    clock2 = Clock()
    f, data, units = world(on_post=lambda pid, n: setattr(clock2, "t", clock2.t + 200))
    del f.refreshed[:]
    rep = _run([u for u in units if u["package"] == PKG_C], data, clock=clock2)
    assert rep["apps"][PKG_C]["complete"] and len(f.refreshed) == 2           # 60 min: refreshed once at 45 min


def test_the_budget_stops_new_calls_and_the_report_is_still_whole(world):
    clock = Clock()
    f, data, units = world(on_post=lambda pid, n: setattr(clock, "t", clock.t + 10))
    rep = _run(units, data, clock=clock, budget=300, workers=1)
    assert len(f.bodies) <= 31
    assert {a["stopped"] for a in rep["apps"].values()} == {"budget"}
    assert rep["counts"]["apps_complete"] == 0 and rep["counts"]["stopped"] == 3
    for pkg, aid in ((PKG_A, AID_A), (PKG_B, AID_B), (PKG_C, AID_C)):
        s = _store(rep, pkg, aid)
        assert sum(s["d1"].values()) == s["install_days"] and s["d1"]["unread"] > 0
    json.loads(vr.pr._dump(rep))


def test_a_pause_longer_than_the_budget_left_stops_instead(world):
    clock = Clock()
    f, data, units = world(hourly=lambda pid, n: 6000)
    rep = _run([u for u in units if u["package"] == PKG_C], data, clock=clock, budget=200)
    assert rep["apps"][PKG_C]["stopped"] == "budget" and not clock.slept and len(f.bodies) == 1


# ── writes, resume, the public log ──────────────────────────────────────────────────────────────

def test_partial_reports_are_written_as_apps_finish(world, monkeypatch):
    monkeypatch.setattr(vr, "WRITE_EVERY", 1)
    f, data, units = world()
    got = []
    rep = _run(units, data, writer=lambda r: got.append(json.loads(vr.pr._dump(r))) or True, workers=1)
    assert [g["partial"] for g in got] == [True, True] and rep["partial"] is False
    assert [len(g["apps"]) for g in got] == [1, 2] and len(rep["apps"]) == 3
    assert all(a["complete"] for g in got for a in g["apps"].values())


def test_the_report_is_still_written_when_the_bookkeeping_has_a_bug(world, monkeypatch):
    f, data, units = world()
    monkeypatch.setattr(vr, "evaluate", lambda s, rd, last: 1 / 0)
    monkeypatch.setattr(vr, "summary", lambda apps: {}["x"])
    rep = _run([u for u in units if u["package"] == PKG_C], data)
    assert _store(rep, PKG_C, AID_C) == {"err": {"type": "ZeroDivisionError"}}
    assert rep["summary"] == {"err": {"type": "KeyError"}} and rep["apps"][PKG_C]["activity"]["read"] == 18
    assert rep["counts"]["apps_complete"] == 1
    json.loads(vr.pr._dump(rep))


def _env(root, **kw):
    env = {"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec",
           "GA4_REFRESH_TOKENS": json.dumps({EMAIL_A: RT_A, EMAIL_B: RT_B}), "VERIFY_DATA_DIR": str(root)}
    env.update(kw)
    return env


def test_main_writes_the_private_file_and_prints_counts_only(world, tmp_path, monkeypatch, capsys):
    f, data, units = world()
    put = []
    monkeypatch.setattr(vr, "write_private", lambda path, text, msg: bool(put.append((path, text, msg))) or True)
    vr.main(_env(tmp_path), now=NOW, clock=Clock())
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert all(line.startswith("d1d7 ") for line in lines)
    assert lines[0] == "d1d7 verify: 3 app(s) to check, 0 carried over, ~197 activity days"
    assert lines[1] == "d1d7 verify: 0 of 4 store(s) still in their cohort backfill"
    assert lines[-2].startswith("d1d7 verify: apps 3/3 complete, install days 312, D1 match ")
    assert ", stores in backfill 0, " in lines[-2]
    assert lines[-1] == "d1d7 verify: report written"
    for s in SECRETS:
        assert s not in out
    assert not re.search(r"\d{4}-\d{2}-\d{2}|20\d{6}", out)                  # no dates of any kind
    (path, text, msg), = put
    assert path == vr.OUT_PATH == "ga4/d1d7_verify.json" and msg == "ga4 d1d7 verify"
    rep = json.loads(text)
    assert set(rep["apps"]) == {PKG_A, PKG_B, PKG_C} and rep["partial"] is False
    assert rep["summary"]["apps"]["%s|%s" % (PKG_A, AID_A)]["d1"] == [110, 113]


def test_main_resumes_only_the_apps_missing_and_carries_the_rest(world, tmp_path, monkeypatch, capsys):
    f, data, units = world()
    os.makedirs(os.path.join(str(tmp_path), "ga4"))
    old_a = {"package": PKG_A, "complete": True, "stores": {}, "marker": "kept"}
    with open(os.path.join(str(tmp_path), vr.OUT_PATH), "w") as fh:
        json.dump({"apps": {PKG_A: old_a, PKG_B: {"complete": False}}}, fh)
    put = []
    monkeypatch.setattr(vr, "write_private", lambda path, text, msg: bool(put.append(text)) or True)
    vr.main(_env(tmp_path, VERIFY_ONLY_MISSING="true"), now=NOW, clock=Clock())
    assert not f.days_asked(PID_A) and f.days_asked(PID_B) and f.days_asked(PID_C)
    rep = json.loads(put[-1])
    assert rep["apps"][PKG_A] == old_a and rep["apps"][PKG_B]["complete"] and rep["counts"]["apps"] == 3
    assert "1 carried over" in capsys.readouterr().out
    f.bodies.clear()
    vr.main(_env(tmp_path, VERIFY_ONLY_MISSING="false", VERIFY_MAX_APPS="1"), now=NOW, clock=Clock())
    assert {p for p, _ in f.bodies} == {PID_C}


def test_main_without_credentials_or_routes_exits_before_any_call(world, tmp_path, monkeypatch):
    f, data, units = world()
    with pytest.raises(SystemExit):
        vr.main({"GA4_CLIENT_ID": "cid", "VERIFY_DATA_DIR": str(tmp_path)}, now=NOW)
    with pytest.raises(SystemExit):
        vr.main(_env(tmp_path / "nothing-here"), now=NOW)
    monkeypatch.setattr(vr, "write_private", lambda path, text, msg: False)
    with pytest.raises(SystemExit):                                   # a failed private write fails the job
        vr.main(_env(tmp_path, VERIFY_MAX_APPS="1"), now=NOW, clock=Clock())


def test_a_counts_only_heartbeat_also_while_a_property_waits(capsys):
    t = [0.0]

    def sleeper(s):
        t[0] += s
    run = vr.Run(clock=lambda: t[0], sleeper=sleeper)
    run.sleep(150)
    out = capsys.readouterr().out.splitlines()
    assert out == ["d1d7 progress: calls 0, waiting 1, 60s", "d1d7 progress: calls 0, waiting 1, 120s"]
    assert vr.public_line({"apps": 3, "apps_complete": 2}).startswith("d1d7 verify: apps 2/3 complete, install days 0")


def test_the_workflow_keeps_secrets_and_details_off_the_public_log():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "ga4-d1d7-verify.yml"), encoding="utf-8") as fh:
        wf = yaml.safe_load(fh)
    on = wf.get("on", wf.get(True))
    assert set(on) == {"workflow_dispatch"}
    assert set(on["workflow_dispatch"]["inputs"]) == {"max_apps", "only_apps_missing"}
    assert wf["permissions"] == {"contents": "read"}
    job = wf["jobs"]["verify"]
    assert job["timeout-minutes"] == 300 and vr.BUDGET_SEC < 290 * 60
    steps = job["steps"]
    assert steps[0]["with"]["persist-credentials"] is False
    for st in steps:
        env = st.get("env") or {}
        if st.get("name") == "Run":
            assert st["run"].startswith("python -m admob_iq.fetch.ga4_d1d7_verify 2>/tmp/")
            assert "details kept off the public log" in st["run"]
            assert env["VERIFY_DATA_DIR"] == "_private"
            assert env["VERIFY_ONLY_MISSING"] == "${{ github.event.inputs.only_apps_missing }}"
        else:
            assert not any(k.startswith("GA4_") for k in env), st.get("name")
            assert "secrets.GA4_" not in json.dumps(st)
        if "clone" in (st.get("run") or ""):
            assert "> /dev/null 2>&1" in st["run"] and "@github.com" not in st["run"]
            assert "http.extraheader" in st["run"] and "::add-mask::" in st["run"]


# ── exactness: one wrong cohort, one missing, the store's own ends, the property's timezone ──────────────────────

def _edit_store(data, aid, fn):
    path = gu.store_path(data, aid)
    st = gu.load_store(path)
    fn(st)
    gu.save_store(path, st)


def _table(s):
    return {r[0]: dict(zip(s["table"]["cols"], r)) for r in s["table"]["rows"]}


APP_A2 = (PKG_A2, PID_A, SID_A2, EMAIL_A, [AID_A2], TRUTH_A2, TRUTH_A2.start, False)


def test_one_wrong_cohort_is_exactly_that_day_and_a_missing_cohort_is_missing_in_store(world):
    f, data, units = world(apps=[APP_A2])
    hs = TRUTH_A2.start
    x1, x7, xm = hs + timedelta(days=5), hs + timedelta(days=12), hs + timedelta(days=2)     # all 30 k's due

    def fault(st):
        r = st["ret"]
        r[x1.isoformat()]["a"][1] = r[x1.isoformat()]["a"][1] * 2 + 5          # D1 of x1 only
        r[x7.isoformat()]["a"][7] = r[x7.isoformat()]["a"][7] + 8              # D7 of x7 only
        del r[xm.isoformat()]
    _edit_store(data, AID_A2, fault)
    rep = _run(units, data)
    s = _store(rep, PKG_A2, AID_A2)
    rows = _table(s)
    assert {x for x, r in rows.items() if r["c1"] == "x"} == {x1.isoformat()}
    assert {x for x, r in rows.items() if r["c7"] == "x"} == {x7.isoformat()}
    assert {x for x, r in rows.items() if "M" in (r["c1"], r["c7"])} == {xm.isoformat()}
    assert rows[xm.isoformat()]["c1"] == rows[xm.isoformat()]["c7"] == "M" and rows[xm.isoformat()]["k_judged"] == 0
    assert rows[x1.isoformat()]["c7"] == "m" and rows[x7.isoformat()]["c1"] == "m"         # its other days are right
    for nb in (x1 - timedelta(days=1), x1 + timedelta(days=1), x7 - timedelta(days=1), x7 + timedelta(days=1)):
        assert rows[nb.isoformat()]["c1"] == rows[nb.isoformat()]["c7"] == "m"             # neighbours untouched
    assert {x: r["k_mismatch"] for x, r in rows.items() if r["k_mismatch"]} == {x1.isoformat(): 1, x7.isoformat(): 1}
    assert {k: c.get("mismatch", 0) for k, c in s["by_k"].items() if c.get("mismatch")} == {"1": 1, "7": 1}
    assert s["all_k"]["missing_in_store"] == 30 and s["gap_days"]["runs"] == [[xm.isoformat()] * 2]
    assert s["all_k"]["store_not_final"] == 0 and s["all_k"]["short_in_store"] == 0
    # every other install day × k: a match, or not due yet (after the last day asked)
    assert s["all_k"]["match"] + s["all_k"]["not_due"] + 30 + 2 == s["install_days"] * 30
    (w1, w7) = sorted(s["worst"], key=lambda m: m["k"])
    assert (w1["x"], w1["k"], w1["A"], w1["N"]) == (x1.isoformat(), 1, TRUTH_A2.A(x1, 1), TRUTH_A2.n(x1))
    assert (w7["x"], w7["k"], w7["users"]) == (x7.isoformat(), 7, 8)


def test_dates_are_the_property_timezone(world, tmp_path):
    f, data, units = world(apps=[APPS[2]])
    for u in units:
        u["tz"] = "America/Los_Angeles"         # 27 Sep 06:00 UTC is still 26 Sep there: today − 3 = 23 Sep
    rep = _run(units, data)
    c = rep["apps"][PKG_C]
    assert c["today"] == "2026-09-26" and c["last_asked"] == "2026-09-23"
    assert f.days_asked(PID_C)[-1] == "2026-09-23" and "2026-09-24" not in f.days_asked(PID_C)
    s = _store(rep, PKG_C, AID_C)
    assert s["d1"]["not_due"] == 2 and s["d1"]["unread"] == 0 and s["d1"]["mismatch"] == 0


def test_each_store_of_a_stream_is_judged_to_its_own_window_end(world):
    """Two AdMob app ids of one stream, one store a fetch behind: its days after ITS window end are not due, never a
    short_in_store gap."""
    f, data, units = world(apps=[(PKG_C, PID_C, SID_C, EMAIL_A, [AID_C, AID_AT], TRUTH_C, HS_C, False)])
    we2 = WE - timedelta(days=4)

    def behind(st):
        st["window_end"] = we2.isoformat()
        st["ret"] = {x: dict(e, a=e["a"][:min(30, (we2 - date.fromisoformat(x)).days) + 1])
                     for x, e in st["ret"].items() if date.fromisoformat(x) <= we2}
        st["daily"] = {d: v for d, v in st["daily"].items() if date.fromisoformat(d) <= we2}
    _edit_store(data, AID_AT, behind)
    rep = _run(units, data)
    assert rep["apps"][PKG_C]["last_asked"] == LAST.isoformat()           # one GA4 read, to the newer store's end
    s, s2 = _store(rep, PKG_C, AID_C), _store(rep, PKG_C, AID_AT)
    assert s2["judged_to"] == we2.isoformat() and s2["last_asked"] == LAST.isoformat()
    assert s2["all_k"]["short_in_store"] == 0 and s2["gap_days"]["days"] == 0
    assert s2["all_k"]["mismatch"] == s2["all_k"]["store_not_final"] == 0
    assert s2["install_days"] == (we2 - HS_C).days and s2["d1"]["match"] == s2["install_days"]
    assert s2["d7"]["not_due"] == 6 and s2["d7"]["match"] == s2["install_days"] - 6
    assert s["all_k"]["short_in_store"] == 0 and s["d1"]["match"] == 17


def test_not_final_is_the_stores_own_read_end(world):
    """A store read BEFORE local noon ended at at − 3 (not at − 2): a mismatch on at − 5 is not final (its read
    ended 2 days later only), at − 6 is. A cohort read to day 30 uses the read day − 3 (the sure bound)."""
    f, data, units = world(apps=[APPS[2]])
    we3 = TODAY - timedelta(days=3)                                       # 24 Sep; AT stays 27 Sep
    xf, xx = date(2026, 9, 21), date(2026, 9, 20)                         # D1 on 22 Sep (= at − 5) / 21 Sep

    def morning(st):
        st["window_end"] = we3.isoformat()
        st["ret"] = {x: dict(e, a=e["a"][:min(30, (we3 - date.fromisoformat(x)).days) + 1])
                     for x, e in st["ret"].items() if date.fromisoformat(x) <= we3}
        for x in (xf, xx):
            st["ret"][x.isoformat()]["a"][1] *= 2
    _edit_store(data, AID_C, morning)
    rep = _run(units, data)
    rows = _table(_store(rep, PKG_C, AID_C))
    assert (rows[xf.isoformat()]["c1"], rows[xx.isoformat()]["c1"]) == ("f", "x")
    # a full (day 0..30) read: final to min(at − 3, window end) − 3 = 21 Sep
    f, data, units = world(apps=[APP_A2])
    x = date(2026, 8, 26)                                                  # X + 26 = 21 Sep, X + 27 = 22 Sep

    def full(st):
        a = st["ret"][x.isoformat()]["a"]
        assert len(a) == 31
        a[26] += 10
        a[27] += 10
    _edit_store(data, AID_A2, full)
    s = _store(_run(units, data), PKG_A2, AID_A2)
    assert s["by_k"]["26"].get("mismatch") == 1 and s["by_k"]["27"].get("store_not_final") == 1
    assert [(m["x"], m["k"]) for m in s["worst_any_k"]] == [(x.isoformat(), 26)]


def test_a_mismatch_on_a_thresholded_ga4_day_is_flagged(world, monkeypatch):
    th = TRUTH_A2.start + timedelta(days=15)
    monkeypatch.setattr(TRUTH_A2, "thresh", {th})
    f, data, units = world(apps=[APP_A2])
    x = th - timedelta(days=1)
    _edit_store(data, AID_A2, lambda st: st["ret"][x.isoformat()]["a"].__setitem__(1, 0))
    s = _store(_run(units, data), PKG_A2, AID_A2)
    (w,) = s["worst"]
    assert (w["x"], w["k"], w["ga4_day_flagged"]) == (x.isoformat(), 1, 1)
    assert s["rules"]["d1"]["fail_on_flagged_day"] == 1 and s["rules"]["d7"]["fail_on_flagged_day"] == 0


def test_a_partial_report_keeps_the_older_result_of_an_app_not_redone_yet(world, monkeypatch):
    monkeypatch.setattr(vr, "WRITE_EVERY", 1)
    f, data, units = world()
    old_b = {"package": PKG_B, "complete": True, "stores": {}, "marker": "older"}
    got = []
    rep = _run(units, data, writer=lambda r: got.append(json.loads(vr.pr._dump(r))) or True, workers=1,
               held={PKG_B: old_b})
    order = [g for g in got]
    assert len(order) == 2 and all(g["partial"] for g in order)
    assert order[0]["apps"][PKG_B] == old_b                                # PKG_B not redone yet: the older kept
    assert set(order[0]["apps"]) == {PKG_A, PKG_B}
    assert rep["apps"][PKG_B] != old_b and rep["apps"][PKG_B]["complete"]  # the final: this run's own result


def test_the_side_heartbeat_speaks_while_nothing_else_does(capsys):
    t = [0.0]
    run = vr.Run(clock=lambda: t[0])
    with vr.Ticker(run, every=0.01):
        t[0] = 61.0
        for _ in range(200):
            if "d1d7 progress" in capsys.readouterr().out:
                break
            threading.Event().wait(0.01)
        else:
            raise AssertionError("no heartbeat")


def test_backfill_pending_counts_stores_without_a_cohort_edge(world):
    f, data, units = world()
    _edit_store(data, AID_B, lambda st: st.pop("ret_from"))
    assert vr.backfill_pending(units, data) == (1, 4)
    rep = _run([u for u in units if u["package"] == PKG_B], data)
    assert rep["counts"]["backfill"] == 1
