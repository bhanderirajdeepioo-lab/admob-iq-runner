"""GA4 → uninstall store (admob_iq.fetch.ga4_uninstall) — offline, against a synthetic GA4 (UniStub) that
honours dimensions, event filters, date ranges and paging: full history, incremental re-pulls of late data,
holes, self-healing rebuilds that never trim, the once-per-~20h plan, request shapes, failure isolation per
owner/app, the run budget and quota guard, cached discovery, deterministic files and the a28 fallback."""

import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_uninstall as gu
from tests.uninstall_synth import AdminFake, Truth, UniStub

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)          # 17:30 IST → last settled day 23 Sep
END = date(2026, 9, 23)
EMAIL_A, EMAIL_B = "owner.a@secret-ws.test", "owner.b@secret-ws.test"
RT_A, RT_B, TOK_A, TOK_B = "rt-SECRET-a", "rt-SECRET-b", "tok-SECRET-a", "tok-SECRET-b"
PID, PID_B = "987654321", "123123123"
S1, S2, S5 = "5550001111", "5550002222", "5550005555"
PKG1, PKG2, PKG4, PKG5 = "com.secret.one", "com.secret.two", "com.secret.nostream", "com.secret.five"
A1, A2, A3, A4, A5 = ("ca-app-pub-1111111111111111~%d" % i for i in (1, 2, 3, 4, 5))
APPS = [{"app_id": A1, "app_name": "One", "package": PKG1}, {"app_id": A2, "app_name": "Two", "package": PKG2},
        {"app_id": A3, "app_name": "No Package", "package": None},
        {"app_id": A4, "app_name": "No Stream", "package": PKG4}, {"app_id": A5, "app_name": "Five", "package": PKG5}]
CFG = {"client_id": "cid", "client_secret": "sec", "refresh_tokens": json.dumps({EMAIL_A: RT_A, EMAIL_B: RT_B}),
       "refresh_token": "", "min_hours": 20.0, "retry_hours": 3.0, "refetch_days": 10, "rebuild_days": 28,
       "max_history_days": 1300, "run_budget_sec": 900, "streams_ttl_hours": 168.0}


class World:
    def __init__(self, monkeypatch):
        self.truths = {(PID, S1): Truth(END - timedelta(days=199), END, 1000, old_per_day=30),
                       (PID_B, S2): Truth(END - timedelta(days=59), END, 300),
                       (PID, S5): Truth(END - timedelta(days=99), END, 500)}
        self.admin = AdminFake({TOK_A: [PID], TOK_B: [PID_B]},
                               {PID: [(S1, PKG1), (S5, PKG5), ("9", "com.stranger")], PID_B: [(S2, PKG2)]})
        self.log, self.tokens_used, self.fail, self.quota, self.bad_rt = [], [], None, None, set()
        monkeypatch.setattr(ga4.requests, "get", self.admin.get)
        monkeypatch.setattr(ga4.requests, "post", self.admin.post)
        monkeypatch.setattr(ga4, "_sleep", lambda s: None)
        monkeypatch.setattr(ga4, "access_token", self._access)
        monkeypatch.setattr(ga4, "Ga4App", self._app)

    def _access(self, cid, sec, rt):
        assert (cid, sec) == ("cid", "sec")
        if rt in self.bad_rt:
            raise RuntimeError("invalid_grant: SECRETDETAIL")
        return {RT_A: TOK_A, RT_B: TOK_B}[rt]

    def _app(self, tok, pid, sid):
        self.tokens_used.append((tok, pid))
        return UniStub(self.truths[(pid, sid)], tok, pid, sid, log=self.log, quota=self.quota, fail=self.fail)

    def run(self, data_dir, now=NOW, cfg=None, apps=APPS, clock=lambda: 0.0):
        return gu.refresh_all(dict(CFG, **(cfg or {})), str(data_dir), apps, now, clock)


@pytest.fixture
def world(monkeypatch):
    return World(monkeypatch)


def _cells_of(truth):
    """The truth's cells as a store's cohorts {install day: {lag: users}}."""
    out = {}
    for (c, d), u in truth.cells.items():
        out.setdefault(c.isoformat(), {})[str((d - c).days)] = u
    return out


def _stub(truth, sid=S1, log=None):
    return UniStub(truth, TOK_A, PID, sid, log=log if log is not None else [])


# ── full fetch ───────────────────────────────────────────────────────────────────────────────────

def test_full_fetch_finds_the_history_pages_every_row_and_slices_cells_by_90_days(monkeypatch):
    t = Truth(END - timedelta(days=199), END, 1000, old_per_day=30)
    monkeypatch.setattr(gu, "UNI_PAGE_ROWS", 700)                  # force several pages per report
    log = []
    st = gu.fetch_full(_stub(t, log=log), END, 1300)
    assert st["history_start"] == t.start.isoformat() and st["window_end"] == END.isoformat()
    assert st["history_capped"] is False and st["covered"] == [[t.start.isoformat(), END.isoformat()]]
    assert st["den"] == "a28" and st["flags"]["truncated"] == [] and st["flags"]["thresholded"] is False
    assert st["cohorts"] == _cells_of(t)                           # every cell, nothing cut or merged
    assert sum(st["unplaced"].values()) == 30 * 200                # old installs: kept visible, not guessed
    d = st["daily"][END.isoformat()]
    assert (d["new"], d["a1"], d["a28"], d["un"], d["upd"]) == (1000, t.a1[END], t.a28[END], t.un_by_day()[END], 0)
    assert d["un_ev"] > d["un"]
    bodies = [b for _, _, b in log]
    cells = [b for b in bodies if [x["name"] for x in b["dimensions"]] == ["firstSessionDate", "date"]]
    ranges = sorted({(b["dateRanges"][0]["startDate"], b["dateRanges"][0]["endDate"]) for b in cells})
    assert len(ranges) == 3 and all((date.fromisoformat(e) - date.fromisoformat(s)).days < 90 for s, e in ranges)
    assert len(cells) > len(ranges)                                # paged
    assert sum(1 for b in bodies if [x["name"] for x in b["dimensions"]] == ["date"]) == 1   # daily asked ONCE


def test_the_history_window_is_capped_and_a_capped_report_is_flagged(monkeypatch):
    t = Truth(END - timedelta(days=199), END, 1000)
    st = gu.fetch_full(_stub(t), END, 100)
    assert st["history_start"] == (END - timedelta(days=99)).isoformat() and st["history_capped"] is True
    assert min(st["cohorts"]) == st["history_start"] and sum(st["unplaced"].values()) > 0
    monkeypatch.setattr(gu, "UNI_PAGE_ROWS", 500)
    monkeypatch.setattr(ga4, "MAX_REPORT_PAGES", 2)
    st = gu.fetch_full(_stub(t), END, 1300)
    assert "cells" in st["flags"]["truncated"]                     # never silent
    t.thresholded = True
    assert gu.fetch_full(_stub(t), END, 1300)["flags"]["thresholded"] is True


def test_a_property_that_rejects_active28dayusers_falls_back_to_daily_actives():
    t = Truth(END - timedelta(days=59), END, 300)
    t.reject_a28 = True
    st = gu.fetch_full(_stub(t), END, 1300)
    assert st["den"] == "dau" and st["daily"][END.isoformat()]["a28"] is None
    assert st["daily"][END.isoformat()]["a1"] == t.a1[END]
    from admob_iq.engine import uninstall as eng
    ds = eng.daily_series(st)
    assert ds["rate"][-1] == round(t.un_by_day()[END] * 1000 / t.a1[END], 3)


# ── incremental + rebuild ────────────────────────────────────────────────────────────────────────

def test_incremental_takes_late_data_keeps_old_cells_frozen_and_fills_holes():
    t = Truth(END - timedelta(days=199), END, 1000)
    st = gu.fetch_full(_stub(t), END - timedelta(days=5), 1300)
    late, old = (END - timedelta(days=12), END - timedelta(days=7)), (END - timedelta(days=80), END - timedelta(days=70))
    t.cells[late] += 50                                            # GA4 adds late data inside the last 10 days
    t.cells[old] += 50                                             # ... and (rarely) further back
    st["covered"] = [[st["history_start"], (END - timedelta(days=61)).isoformat()],
                     [(END - timedelta(days=55)).isoformat(), st["window_end"]]]   # a hole: 6 days never fetched
    hole_day = (END - timedelta(days=58)).isoformat()
    st["daily"].pop(hole_day)
    assert gu.holes(st) == [(END - timedelta(days=60), END - timedelta(days=56))]
    log = []
    gu.fetch_incr(_stub(t, log=log), st, END, 10)
    assert {b["dateRanges"][0]["startDate"] for _, _, b in log} == {(END - timedelta(days=60)).isoformat()}
    assert st["window_end"] == END.isoformat() and gu.holes(st) == []
    assert st["covered"] == [[st["history_start"], END.isoformat()]]
    assert st["daily"][hole_day]["new"] == 1000
    got = st["cohorts"][late[0].isoformat()][str((late[1] - late[0]).days)]
    assert got == t.cells[late]                                    # the late uninstalls arrived
    assert st["cohorts"][old[0].isoformat()][str((old[1] - old[0]).days)] == t.cells[old] - 50   # frozen
    assert st["cohorts"] == {c: lags for c, lags in _cells_of(t).items()} | {
        old[0].isoformat(): dict(_cells_of(t)[old[0].isoformat()], **{str((old[1] - old[0]).days): t.cells[old] - 50})}
    assert st["daily"][END.isoformat()]["un"] == t.un_by_day()[END]


def test_a_rebuild_keeps_older_history_and_a_thin_rebuild_is_rejected():
    t_old = Truth(END - timedelta(days=199), END, 1000)
    old = gu.fetch_full(_stub(t_old), END - timedelta(days=3), 1300)
    t_new = Truth(END - timedelta(days=99), END, 1000)             # GA4 stopped returning the oldest days
    new = gu.fetch_full(_stub(t_new), END, 1300, old_store=old)
    st, ok = gu.apply_rebuild(json.loads(json.dumps(old)), new)
    assert ok and st["history_start"] == old["history_start"]      # never trimmed
    assert st["flags"]["kept_old_before"] == new["history_start"] and st["window_end"] == END.isoformat()
    assert st["daily"][old["history_start"]] == old["daily"][old["history_start"]]
    assert gu.holes(st) == []
    thin = gu.fetch_full(_stub(Truth(END - timedelta(days=199), END, 400)), END, 1300)
    kept, ok = gu.apply_rebuild(old, thin)                         # < half the installs we hold → suspect
    assert not ok and kept is old


def test_plan_is_once_per_20h_when_the_day_moved_retries_after_3h_and_rebuilds_on_its_day():
    cfg = dict(CFG)
    meta = {"history_start": "2026-01-01", "window_end": "2026-09-22", "next_rebuild": "2026-10-10",
            "covered": [["2026-01-01", "2026-09-22"]], "property_id": PID, "stream_id": S1}
    ok = {"property_id": PID, "stream_id": S1, "last_ok": "2026-09-24T12:00:00Z", "last_try": "2026-09-24T12:00:00Z"}
    assert gu.plan(ok, None, END, NOW, cfg) == "full"
    assert gu.plan(ok, meta, END, NOW, cfg) == "incr"                               # 24h ago, day moved
    assert gu.plan(dict(ok, last_ok="2026-09-25T00:00:00Z"), meta, END, NOW, cfg) is None   # 12h ago
    assert gu.plan(ok, dict(meta, window_end="2026-09-23", covered=[["2026-01-01", "2026-09-23"]]),
                   END, NOW, cfg) is None                                                   # nothing new
    hole = dict(meta, window_end="2026-09-23", covered=[["2026-01-01", "2026-09-01"], ["2026-09-05", "2026-09-23"]])
    assert gu.plan(ok, hole, END, NOW, cfg) == "incr"                                        # a recent hole
    hole["covered"] = [["2026-01-01", "2026-06-01"], ["2026-06-05", "2026-09-23"]]
    assert gu.plan(ok, hole, END, NOW, cfg) == "full"                                        # > 90 days back
    assert gu.plan(ok, dict(meta, window_end="2026-05-01", covered=[["2026-01-01", "2026-05-01"]]),
                   END, NOW, cfg) == "full"                                                  # gap > 90 days
    assert gu.plan(ok, dict(meta, next_rebuild="2026-09-23"), END, NOW, cfg) == "full"       # rebuild day
    assert gu.plan(dict(ok, stream_id="other"), meta, END, NOW, cfg) == "full"               # moved stream
    failed = dict(ok, fail="http", last_try="2026-09-25T10:00:00Z")
    assert gu.plan(failed, meta, END, NOW, cfg) is None and gu.plan(failed, None, END, NOW, cfg) is None
    assert gu.plan(dict(failed, last_try="2026-09-25T08:00:00Z"), meta, END, NOW, cfg) == "incr"   # 4h later
    assert gu.plan(dict(ok, last_ok="2026-09-25T00:00:00Z"), meta, END, NOW, dict(cfg, min_hours=6)) == "incr"


def test_env_overrides_reach_the_uninstall_config(monkeypatch):
    from admob_iq.config import settings
    from admob_iq.uninstall_build import ga4_cfg
    for k, v in {"GA4_CLIENT_ID": "gcid", "GA4_CLIENT_SECRET": "gsec", "GA4_REFRESH_TOKENS": '{"a@x": "rt"}',
                 "GA4_MIN_HOURS": "6", "GA4_RETRY_HOURS": "1.5", "GA4_REFETCH_DAYS": "14", "GA4_REBUILD_DAYS": "7",
                 "GA4_MAX_HISTORY_DAYS": "400", "GA4_RUN_BUDGET_SEC": "120", "GA4_STREAMS_TTL_HOURS": "24",
                 "GOOGLE_CLIENT_ID": "admob-cid", "GOOGLE_CLIENT_SECRET": "admob-sec"}.items():
        monkeypatch.setenv(k, v)
    c = ga4_cfg(settings())
    assert (c["client_id"], c["client_secret"]) == ("gcid", "gsec")
    assert (c["min_hours"], c["retry_hours"], c["refetch_days"], c["rebuild_days"], c["max_history_days"],
            c["run_budget_sec"], c["streams_ttl_hours"]) == (6.0, 1.5, 14, 7, 400, 120, 24.0)
    monkeypatch.setenv("GA4_CLIENT_ID", "")                        # no GA4 client → the AdMob PAIR, never mixed
    c = ga4_cfg(settings())
    assert (c["client_id"], c["client_secret"]) == ("admob-cid", "admob-sec")
    monkeypatch.setenv("GA4_ENABLED", "false")
    assert ga4_cfg(settings()) is None


# ── orchestration ────────────────────────────────────────────────────────────────────────────────

def test_every_request_is_pinned_to_the_stream_with_the_right_event_filter(world, tmp_path):
    out = world.run(tmp_path)
    assert out["counts"]["fetched"] == 3 and out["counts"]["full"] == 3
    want = {("date",): None, ("date", "eventName"): ["app_remove", "app_update"],
            ("firstSessionDate", "date"): ["app_remove"], ("date", "appVersion"): None}
    seen = set()
    for pid, sid, body in world.log:                               # UniStub asserts Android + streamId + quota
        dims = tuple(d["name"] for d in body["dimensions"])
        ex = [e["filter"] for e in body["dimensionFilter"]["andGroup"]["expressions"][2:]]
        got = None
        if ex:
            assert len(ex) == 1 and ex[0]["fieldName"] == "eventName"
            got = [ex[0]["stringFilter"]["value"]] if "stringFilter" in ex[0] else ex[0]["inListFilter"]["values"]
        assert got == want[dims], dims
        assert [o["dimension"]["dimensionName"] for o in body["orderBys"]][:1] == [dims[0]]
        seen.add(dims)
    assert seen == set(want)
    assert set(world.tokens_used) == {(TOK_A, PID), (TOK_B, PID_B)}   # each property with its owner's token


def test_a_run_fetches_what_is_due_then_nothing_until_the_next_day(world, tmp_path):
    out = world.run(tmp_path)
    assert out["apps"] == {A1: "fetched", A2: "fetched", A5: "fetched"}
    assert out["no_ga4"] == {A3: "no_package", A4: "no_stream"}
    c = out["counts"]
    assert (c["selected"], c["with_ga4"], c["fetched"], c["full"], c["no_ga4"], c["failed"]) == (5, 3, 3, 3, 2, 0)
    st = gu.load_store(gu.store_path(str(tmp_path), A1))
    assert st["app_id"] == A1 and st["time_zone"] == "Asia/Kolkata" and st["window_end"] == END.isoformat()
    state = gu.load_state(str(tmp_path))
    assert state["fetch"][A1]["last_kind"] == "full" and state["tz"] == {PID: "Asia/Kolkata", PID_B: "Asia/Kolkata"}
    assert "token" not in json.dumps(state).lower() and RT_A not in json.dumps(state)
    n = len(world.log)
    admin = len(world.admin.calls)
    out = world.run(tmp_path, now=NOW + timedelta(hours=1))        # the next hourly run: nothing due
    assert out["apps"] == {A1: "fresh", A2: "fresh", A5: "fresh"} and len(world.log) == n
    assert len(world.admin.calls) == admin                          # discovery cached (zero Admin calls)
    out = world.run(tmp_path, now=NOW + timedelta(hours=21))       # a day later (day moved): incremental
    assert out["apps"] == {A1: "fetched", A2: "fetched", A5: "fetched"} and out["counts"]["full"] == 0
    assert gu.load_state(str(tmp_path))["fetch"][A1]["last_kind"] == "incr"
    incr = world.log[n:]
    assert len(incr) == 3 * 4                                      # 4 reports per app, one page each
    assert {b["dateRanges"][0]["startDate"] for _, _, b in incr} == {(END - timedelta(days=8)).isoformat()}


def test_a_failing_app_or_owner_never_stops_the_others(world, tmp_path):
    world.run(tmp_path)
    before = open(gu.store_path(str(tmp_path), A5), "rb").read()

    def fail(body):
        if body["dimensionFilter"]["andGroup"]["expressions"][1]["filter"]["stringFilter"]["value"] == S5:
            raise RuntimeError("HTTP 500: INTERNAL: SECRETDETAIL")
    world.fail, world.bad_rt = fail, {RT_B}
    out = world.run(tmp_path, now=NOW + timedelta(hours=21))       # owner B's token is revoked, S5 errors
    assert out["apps"] == {A1: "fetched", A2: "failed", A5: "failed"}
    assert out["counts"]["fetched"] == 1 and out["counts"]["failed"] == 2 and "error" not in out
    state = gu.load_state(str(tmp_path))
    assert state["fetch"][A5]["fail"] == "http" and state["fetch"][A2]["fail"] == "auth"
    assert state["routes"]["by_package"][PKG2]["property_id"] == PID_B      # route kept while B is down
    assert open(gu.store_path(str(tmp_path), A5), "rb").read() == before    # the old store stays as it was
    world.fail, world.bad_rt = None, set()
    out = world.run(tmp_path, now=NOW + timedelta(hours=22))       # a failed app waits 3h
    assert out["apps"] == {A1: "fresh", A2: "failed", A5: "failed"}
    out = world.run(tmp_path, now=NOW + timedelta(hours=25))
    assert out["apps"] == {A1: "fresh", A2: "fetched", A5: "fetched"} and out["discovery"] == "ok"
    assert gu.load_state(str(tmp_path))["fetch"][A2]["fail"] is None


def test_budget_zero_defers_everything_without_a_call_and_low_quota_stops_that_property(world, tmp_path):
    out = world.run(tmp_path, cfg={"run_budget_sec": 0})
    assert out["apps"] == {A1: "deferred", A2: "deferred", A5: "deferred"} and world.log == []
    assert out["counts"]["deferred"] == 3
    world.quota = lambda ga: {"tokensPerHour": {"consumed": 30, "remaining": 1000}}   # < 10% of 40,000 left
    out = world.run(tmp_path, now=NOW + timedelta(minutes=5))
    assert sorted(out["apps"].values()) == ["deferred", "fetched", "fetched"]
    assert out["apps"][A2] == "fetched"                             # another property: unaffected
    assert {out["apps"][A1], out["apps"][A5]} == {"fetched", "deferred"}


def test_discovery_keeps_a_route_whose_stream_list_failed_this_time(world, tmp_path):
    world.run(tmp_path)
    world.admin.fail_streams = {(TOK_A, PID)}
    out = world.run(tmp_path, now=NOW + timedelta(days=8))         # TTL passed → re-listed, PID's list fails
    assert out["discovery"] == "ok" and A1 in out["apps"] and A5 in out["apps"]
    assert gu.load_state(str(tmp_path))["routes"]["stream_errors"] == 1


def test_files_are_deterministic_and_rewritten_only_on_change(world, tmp_path):
    t = world.truths[(PID, S1)]
    a = gu.fetch_full(_stub(t), END, 1300)
    b = gu.fetch_full(_stub(t), END, 1300)
    pa, pb = str(tmp_path / "a.json.gz"), str(tmp_path / "b.json.gz")
    assert gu.save_store(pa, a) and gu.save_store(pb, b)
    assert open(pa, "rb").read() == open(pb, "rb").read()         # same data → the same bytes
    mtime = os.stat(pa).st_mtime_ns
    assert gu.save_store(pa, json.loads(json.dumps(a))) is False and os.stat(pa).st_mtime_ns == mtime
    world.run(tmp_path)
    state_path = tmp_path / "ga4_uninstall" / "state.json"
    before = state_path.read_bytes()
    stores = {f: (tmp_path / "ga4_uninstall" / f).read_bytes() for f in os.listdir(tmp_path / "ga4_uninstall")}
    world.run(tmp_path, now=NOW + timedelta(hours=1))
    assert state_path.read_bytes() == before
    assert stores == {f: (tmp_path / "ga4_uninstall" / f).read_bytes() for f in os.listdir(tmp_path / "ga4_uninstall")}


def test_a_broken_state_file_or_store_is_never_fatal(world, tmp_path):
    d = tmp_path / "ga4_uninstall"
    d.mkdir()
    (d / "state.json").write_text("{not json")
    assert gu.load_state(str(tmp_path))["episodes"] == {}
    (d / (gu.file_key(A1) + ".json.gz")).write_bytes(b"garbage")
    assert gu.load_store(gu.store_path(str(tmp_path), A1)) is None
    out = world.run(tmp_path)
    assert out["apps"][A1] == "fetched"


def test_a_store_with_a_damaged_deflate_stream_is_fetched_again_and_rewritten(world, tmp_path):
    world.run(tmp_path)
    path = gu.store_path(str(tmp_path), A1)
    raw = bytearray(open(path, "rb").read())
    for i in range(30, 60):                                        # a valid gzip header, a broken body: zlib.error
        raw[i] ^= 0xFF
    open(path, "wb").write(bytes(raw))
    assert gu.load_store(path) is None
    out = world.run(tmp_path, now=NOW + timedelta(hours=21))       # its next fetch: nothing to add to → full, saved
    assert out["apps"][A1] == "fetched" and gu.load_state(str(tmp_path))["fetch"][A1]["last_kind"] == "full"
    assert gu.load_store(path)["window_end"] == (END + timedelta(days=1)).isoformat()
    open(path, "wb").write(bytes(raw))
    assert gu.save_store(path, {"v": 1}) is True and gu.load_store(path) == {"v": 1}


def test_the_newest_day_is_fetched_only_from_noon_in_the_propertys_timezone(world, tmp_path):
    early = datetime(2026, 9, 24, 19, 17, tzinfo=timezone.utc)    # 00:47 IST 25 Sep: 23 Sep ended only 24h ago
    assert gu.settled_end("Asia/Kolkata", early) == END - timedelta(days=1)
    assert gu.settled_end("Asia/Kolkata", early + timedelta(hours=11, minutes=13)) == END      # 12:00 IST
    assert gu.settled_end("No/Such_Zone", datetime(2026, 9, 25, 11, 59, tzinfo=timezone.utc)) == END - timedelta(days=1)
    world.run(tmp_path, now=early)
    assert gu.load_store(gu.store_path(str(tmp_path), A1))["window_end"] == (END - timedelta(days=1)).isoformat()
    out = world.run(tmp_path, now=early + timedelta(hours=21))     # 21:47 IST: 23 Sep has had ≥36h
    assert out["apps"][A1] == "fetched" and gu.load_store(gu.store_path(str(tmp_path), A1))["window_end"] == END.isoformat()


def test_refresh_never_prints(world, tmp_path, capsys):
    world.fail = lambda body: (_ for _ in ()).throw(RuntimeError("HTTP 403: PERMISSION_DENIED " + PID))
    world.run(tmp_path)
    world.fail = None
    world.run(tmp_path, now=NOW + timedelta(hours=5))
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_old_installs_and_unusable_rows_go_to_unplaced_never_guessed():
    t = Truth(END - timedelta(days=29), END, 200)
    t.cells[("(other)", END)] = 7                                  # GA4's "(other)" bucket
    t.cells[(END, END - timedelta(days=1))] = 3                    # uninstall BEFORE the first session
    st = gu.fetch_full(_stub(t), END, 1300)
    assert st["unplaced"][END.isoformat()] == 7
    assert st["unplaced"][(END - timedelta(days=1)).isoformat()] == 3
    assert all(int(l) >= 0 for lags in st["cohorts"].values() for l in lags)


def test_rebuilds_are_staggered_and_a_thin_rebuild_keeps_the_old_store(world, tmp_path):
    import zlib
    world.run(tmp_path)
    for aid in (A1, A2, A5):
        st = gu.load_store(gu.store_path(str(tmp_path), aid))
        assert st["next_rebuild"] == (END + timedelta(days=28 + zlib.crc32(aid.encode()) % 7)).isoformat()
        assert st["full_at"] == "2026-09-25T12:00:00Z"
    path = gu.store_path(str(tmp_path), A1)
    st = gu.load_store(path)
    st["next_rebuild"] = (END + timedelta(days=1)).isoformat()      # its rebuild day is tomorrow
    gu.save_store(path, st)
    state = gu.load_state(str(tmp_path))
    state["fetch"][A1]["meta"] = gu.store_meta(st)
    gu.save_state(str(tmp_path), state)
    old_hs = st["history_start"]
    world.truths[(PID, S1)] = Truth(END - timedelta(days=199), END + timedelta(days=1), 300)   # GA4 answers thin
    out = world.run(tmp_path, now=NOW + timedelta(hours=21))
    assert out["apps"][A1] == "failed"
    kept = gu.load_store(path)
    fx = gu.load_state(str(tmp_path))["fetch"][A1]
    assert fx["fail"] == "rebuild_mismatch" and kept["history_start"] == old_hs
    assert kept["daily"][END.isoformat()]["new"] == 1000                # the good history was not overwritten
    assert kept["next_rebuild"] == (END + timedelta(days=2)).isoformat()   # tried again tomorrow
