"""🧊 The cube's fold guard and refold (admob_iq.fetch.ga4_cube; 16 Nov 2026), offline with the cube tests' fake GA4 and
made-up numbers: GA4 answering a day it had filled with almost nothing (since 14 Nov it does so for the newest final
day for hours, on one property for more than a day). A final read collapsed against the day's own earlier reads is
held (not folded, read again every run, the cursor waiting at it) and folded once GA4 fills it; still collapsed at its
cap it is folded as it is, marked "lo"; a real drop (low in every read of the day) folds at once, marked "rd"; a day
never read before is judged against its folded neighbours; a settled day (a backfill) is never judged; the guard off
folds as before; with GA4 whole every month file is byte for byte as without the guard. The refold: a month holding a
day folded collapsed is read again into its copy and replaces the month only once every day is in it (the month file
untouched meanwhile, its cells then exactly those of a month never collapsed), a day still collapsed makes it wait
(until RF_MAX: then merged as it is), users of the collapsed day replaced, a whole read (q) made while it was collapsed
taken out with its week, never refolded twice; the counts in the log line; the settings and the workflow's repo
variables."""
import gzip
import importlib
import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq.fetch import ga4_cube as cu
from tests.test_ga4_cube import HS, LATER, FakeGA, _days, day_total

T0 = date(2026, 10, 13)
D11 = date(2026, 10, 11)


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    """q, the users and the repair off (their own tests); the guard and the refold on, as in the build."""
    monkeypatch.setattr(cu, "Q_CALLS", 0)
    monkeypatch.setattr(cu, "U_ON", False)
    monkeypatch.setattr(cu, "REPAIR_CALLS", 0)
    monkeypatch.setattr(cu, "GUARD", True)
    monkeypatch.setattr(cu, "RF_CALLS", 30)


def at(day, hour=1, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)


def full(D):
    return day_total(FakeGA(today=LATER), D)


class CollapseGA(FakeGA):
    """GA4 answering the days in `empty` with `share` of what it holds (revenue and users): a day it had filled,
    emptied again."""

    def __init__(self, empty=(), share=0.005, **kw):
        super().__init__(**kw)
        self.empty, self.share = set(empty), share

    def rows_of(self, D):
        rows = super().rows_of(D)
        if D in self.empty:
            for r in rows:
                r["totalAdRevenue"] *= self.share
                r["activeUsers"] = int(r["activeUsers"] * self.share)
        return rows


def _save(cube):
    cube.save()
    cube.save_head()


def _month(data, k):
    with gzip.open(cu.month_path(data, "a~1", k), "rt") as f:
        return json.load(f)


def _raw(data, k):
    with open(cu.month_path(data, "a~1", k), "rb") as f:
        return f.read()


# ── the fold guard ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_collapsed_final_read_is_held_then_folded_when_ga4_fills_it():
    cube = cu.Cube(None, "a~1", "222")
    cu.step_app(FakeGA(today=T0), cube, T0, HS, at(T0))            # the walk; hot days Oct 11 … 13 read (half filled)
    p = cube.head["pk"]["2026-10-11"]
    assert p == day_total(FakeGA(today=T0), D11) and sorted(cube.head["pk"]) == ["2026-10-11", "2026-10-12",
                                                                                 "2026-10-13"]
    T1 = T0 + timedelta(days=1)                                     # Oct 11 final now: GA4 answers it almost empty
    ga, f0 = CollapseGA(today=T1, empty={D11}), cube.folded
    assert cu.step_app(ga, cube, T1, HS, at(T1, 0, 5)) == "fetched"
    assert cube.head["next"] == "2026-10-11" and "2026-10-11" not in cube.month("2026-10")["days"]
    assert cube.head["hold"] == ["2026-10-11", "2026-10-14T00:05:00Z", 1] and cube.held == 1 and cube.folded == f0
    assert sorted(cube.head["d"]) == ["2026-10-12", "2026-10-13", "2026-10-14"]     # the hot days read as always
    assert cube.head["pk"]["2026-10-11"] == p                       # its peak kept while it is held
    ga = CollapseGA(today=T1, empty={D11})                          # an hour on, still empty: held again, one call
    cu.step_app(ga, cube, T1, HS, at(T1, 1, 5))
    assert cube.held == 2
    assert ga.calls == 1 and cube.head["hold"] == ["2026-10-11", "2026-10-14T00:05:00Z", 2]
    ga = FakeGA(today=T1)                                           # GA4 filled it: folded, whole
    cu.step_app(ga, cube, T1, HS, at(T1, 3, 10))
    led = cube.month("2026-10")["days"]["2026-10-11"]
    assert led["t"] == full(D11) and "lo" not in led and "rd" not in led and set(led) == set(cu.LEDGER)
    assert "hold" not in cube.head and "2026-10-11" not in cube.head["pk"] and cube.head["next"] == "2026-10-12"


def test_a_head_of_before_the_guard_gets_its_peaks_from_its_hot_copies(monkeypatch):
    """A head written by the code before the guard (no "pk"): the first run takes the hot copies' totals as peaks
    before the final ones go — Oct 11's collapsed final read is held."""
    monkeypatch.setattr(cu, "GUARD", False)
    cube = cu.Cube(None, "a~1", "222")
    cu.step_app(FakeGA(today=T0), cube, T0, HS, at(T0))
    assert "pk" not in cube.head
    monkeypatch.setattr(cu, "GUARD", True)
    T1 = T0 + timedelta(days=1)
    cu.step_app(CollapseGA(today=T1, empty={D11}), cube, T1, HS, at(T1, 0, 5))
    assert cube.head["hold"][0] == "2026-10-11" and "2026-10-11" not in cube.month("2026-10")["days"]


def test_still_collapsed_at_its_cap_it_is_folded_as_it_is_marked_lo():
    cube = cu.Cube(None, "a~1", "222")
    cu.step_app(FakeGA(today=T0), cube, T0, HS, at(T0))
    p = cube.head["pk"]["2026-10-11"]
    T1, T2 = T0 + timedelta(days=1), T0 + timedelta(days=2)
    cu.step_app(CollapseGA(today=T1, empty={D11}), cube, T1, HS, at(T1, 0, 5))
    assert cube.head["next"] == "2026-10-11"
    cu.step_app(CollapseGA(today=T2, empty={D11}), cube, T2, HS, at(T2, 0, 5))     # 4 days old, still empty
    days = cube.month("2026-10")["days"]
    assert days["2026-10-11"]["lo"] == p and days["2026-10-11"]["t"] < cu.COLLAPSE * p and cube.low == 1
    assert days["2026-10-12"]["t"] == full(date(2026, 10, 12))      # the walk went on past it
    assert cube.head["next"] == "2026-10-13" and "hold" not in cube.head and cube.head["done"]


def test_a_real_drop_low_in_every_read_folds_at_once_marked_rd():
    cube = cu.Cube(None, "a~1", "222")
    cu.step_app(CollapseGA(today=T0, empty={D11}, share=0.05), cube, T0, HS, at(T0))   # its hot read low too
    assert cube.head["pk"]["2026-10-11"] >= cu.PK_MIN
    T1 = T0 + timedelta(days=1)
    cu.step_app(CollapseGA(today=T1, empty={D11}, share=0.05), cube, T1, HS, at(T1, 0, 5))
    led = cube.month("2026-10")["days"]["2026-10-11"]
    assert led["rd"] == 1 and "lo" not in led and cube.held == 0 and cube.head["next"] == "2026-10-12"


def test_with_no_earlier_read_the_neighbours_judge_and_a_settled_day_is_never_judged():
    edge = T0 - timedelta(days=cu.FINAL_LAG)
    old = date(2026, 9, 20)
    cube = cu.Cube(None, "a~1", "222")
    cu.step_app(CollapseGA(today=T0, empty={edge, old}), cube, T0, HS, at(T0))     # a first walk: no day read before
    assert cube.head["next"] == edge.isoformat() and edge.isoformat() not in cube.month("2026-10")["days"]
    assert cube.head["hold"][0] == edge.isoformat() and not cube.head.get("done")   # the build waits for the walk
    assert sorted(cube.head["d"]) == ["2026-10-11", "2026-10-12", "2026-10-13"]     # the hot days read anyway
    sep = cube.month("2026-09")["days"]["2026-09-20"]               # 23 days old: folded as it is, no mark
    assert sep["t"] < 0.01 * full(old) and "lo" not in sep and "rd" not in sep
    cu.step_app(FakeGA(today=T0), cube, T0, HS, at(T0, 2))
    assert cube.head["done"] and cube.month("2026-10")["days"][edge.isoformat()]["t"] == full(edge)


def test_a_small_app_or_a_flagged_read_is_never_held():
    """A peak under PK_MIN and neighbours under it: nothing to judge by (folded); a flagged final read is never judged
    against its peak."""
    cube = cu.Cube(None, "a~1", "222")
    cube.head["pk"] = {"2026-10-11": cu.PK_MIN - 1}
    rec = {"t": 0, "fl": 0}
    assert cu._guard(cube, D11, rec, T0 + timedelta(days=1), "x") is False and not rec.get("lo")
    cube.head["pk"] = {"2026-10-11": 10 * cu.PK_MIN}
    assert cu._guard(cube, D11, {"t": 0, "fl": 1}, T0 + timedelta(days=1), "x") is False
    assert cu._guard(cube, D11, {"t": 0, "fl": 0}, T0 + timedelta(days=1), "x") is True
    assert cu._guard(cube, D11, {"t": 0, "fl": 0}, D11 + timedelta(days=cu.RF_RIPE), "x") is False    # settled
    h = {}
    cu._peak(h, "2026-10-12", {"t": 500, "fl": 1})                  # a flagged read is never a peak
    cu._peak(h, "2026-10-12", {"t": 300, "fl": 0})
    cu._peak(h, "2026-10-12", {"t": 200, "fl": 0})                  # the most, never the last
    assert h["pk"] == {"2026-10-12": 300}


def test_guard_off_folds_every_final_read_as_it_comes(monkeypatch):
    monkeypatch.setattr(cu, "GUARD", False)
    cube = cu.Cube(None, "a~1", "222")
    cu.step_app(FakeGA(today=T0), cube, T0, HS, at(T0))
    T1 = T0 + timedelta(days=1)
    cu.step_app(CollapseGA(today=T1, empty={D11}), cube, T1, HS, at(T1, 0, 5))
    assert cube.month("2026-10")["days"]["2026-10-11"]["t"] < 0.01 * full(D11)
    assert "pk" not in cube.head and "hold" not in cube.head and cube.head["next"] == "2026-10-12"


def test_with_ga4_whole_the_guard_changes_no_month_or_users_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cu, "U_ON", True)

    def runs(data, guard):
        monkeypatch.setattr(cu, "GUARD", guard)
        seq = [(T0, at(T0)), (T0, at(T0, 7)), (T0 + timedelta(days=1), at(T0 + timedelta(days=1), 0, 5)),
               (T0 + timedelta(days=2), at(T0 + timedelta(days=2), 3)),
               (T0 + timedelta(days=6), at(T0 + timedelta(days=6), 9))]
        for i, (T, now) in enumerate(seq):
            cube = cu.Cube(data, "a~1", "222")
            cu.step_app(FakeGA(today=T, cap=1000 if i == 3 else None), cube, T, HS, now)
            _save(cube)
    a, b = str(tmp_path / "on"), str(tmp_path / "off")
    runs(a, True)
    runs(b, False)
    da, db = cu.app_dir(a, "a~1"), cu.app_dir(b, "a~1")
    names = sorted(os.listdir(da))
    assert names == sorted(os.listdir(db)) and any(n.endswith(cu.USUF) for n in names)
    for n in names:
        if n not in (cu.HOT, cu.UHEAD):
            with open(os.path.join(da, n), "rb") as f, open(os.path.join(db, n), "rb") as g:
                assert f.read() == g.read(), n


# ── the refold ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _legacy(data):
    """Oct 11 folded collapsed by the walk as it was before the guard (its final read at Oct 14 almost empty)."""
    import admob_iq.fetch.ga4_cube as m
    keep = m.GUARD
    m.GUARD = False
    try:
        for T, now in ((T0, at(T0)), (T0 + timedelta(days=1), at(T0 + timedelta(days=1), 0, 5))):
            cube = cu.Cube(data, "a~1", "222")
            cu.step_app(CollapseGA(today=T, empty={D11}) if T > T0 else FakeGA(today=T), cube, T, HS, now)
            _save(cube)
    finally:
        m.GUARD = keep
    assert _month(data, "2026-10")["days"]["2026-10-11"]["t"] < 0.01 * full(D11)


def _whole(last):
    """The months as the walk folds them when GA4 never collapsed: every day hs … last read final."""
    cube = cu.Cube(None, "a~1", "222")
    for D in _days(HS, last):
        cube.fold(D, cu.read_day(FakeGA(today=LATER), D, "t"))
    return cube


CELLS = ("b", "c", "e", "t", "loss")


def test_refold_reads_the_month_again_and_replaces_it_only_once_every_day_is_in_it(tmp_path, monkeypatch):
    data = str(tmp_path)
    monkeypatch.setattr(cu, "U_ON", True)
    _legacy(data)
    old_sep = _raw(data, "2026-09")
    monkeypatch.setattr(cu, "RF_CALLS", 4)                          # 4 days a run: the copy is built over runs
    T = D11 + timedelta(days=cu.RF_RIPE)                            # Oct 16: Oct 11 five days old
    runs, seen, live0 = 0, 0, None
    while runs < 12:
        runs += 1
        cube = cu.Cube(data, "a~1", "222")
        cu.step_app(FakeGA(today=T), cube, T, HS, at(T, runs))
        _save(cube)
        rf = cube.head["rf"]
        if not rf.get("k"):
            break
        assert rf["k"] == "2026-10" and rf["cand"] == ["2026-10-11"] and os.path.exists(cube.rf_path("2026-10"))
        live = _raw(data, "2026-10")
        assert live0 is None or live == live0                       # the month file untouched while its copy is built
        live0 = live
        assert _month(data, "2026-10")["days"]["2026-10-11"]["t"] < 0.01 * full(D11)
        seen += 1
    assert seen >= 2 and runs < 12 and not os.path.exists(cube.rf_path("2026-10"))
    mo, ref = _month(data, "2026-10"), _whole(date(2026, 10, 13)).month("2026-10")
    assert {f: mo[f] for f in CELLS} == {f: ref[f] for f in CELLS}  # exactly a month GA4 never collapsed
    assert mo["rf"]["t0"]["2026-10-11"] < 0.01 * full(D11) and mo["rf"]["t1"]["2026-10-11"] == full(D11)
    assert _raw(data, "2026-09") == old_sep                         # another month never touched
    assert cube.head["rf"]["log"][-1][:2] == ["2026-10", ["2026-10-11"]] and cube.refolded == 1
    with gzip.open(cu.u_path(data, "a~1", "2026-10"), "rt") as f:
        uc = json.load(f)["c"]
    assert uc["2026-10-11"]["by"] == "rf" and uc["2026-10-11"]["u"]["AA"][0] == 80   # its users: the new read's
    assert uc["2026-10-10"]["by"] == "fold"                         # the other days' users: the walk's
    cube = cu.Cube(data, "a~1", "222")                              # never twice: the queue made again finds nothing
    cube.head["rf"].pop("scan", None)
    ga = FakeGA(today=T)
    assert cu.refold(ga, cube, at(T, 23), T) is False and ga.calls == 0 and cube.head["rf"]["q"] == []


def test_refold_waits_while_ga4_still_holds_the_day_collapsed(tmp_path):
    data = str(tmp_path)
    _legacy(data)
    T = D11 + timedelta(days=cu.RF_RIPE)
    old = _raw(data, "2026-10")
    cube = cu.Cube(data, "a~1", "222")
    ga = CollapseGA(today=T, empty={D11})
    cu.step_app(ga, cube, T, HS, at(T, 1))
    _save(cube)
    rf = cube.head["rf"]
    assert rf["k"] == "2026-10" and rf["wait"] == ["2026-10-11", "2026-10-16T01:00:00Z"] and cube.rf_days == 0
    assert not os.path.exists(cube.rf_path("2026-10"))              # nothing merged: no copy written
    assert {D: v for D, v in _month(data, "2026-10")["days"].items() if D <= "2026-10-11"} == \
        {D: v for D, v in json.loads(gzip.decompress(old))["days"].items() if D <= "2026-10-11"}
    Tm = D11 + timedelta(days=cu.RF_MAX)                            # RF_MAX days old, still empty: merged as it is
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(CollapseGA(today=Tm, empty={D11}), cube, Tm, HS, at(Tm, 1))
    _save(cube)
    mo = _month(data, "2026-10")
    assert not cube.head["rf"].get("k") and mo["rf"]["t1"]["2026-10-11"] < 0.01 * full(D11)
    led = mo["days"]["2026-10-11"]
    assert "lo" not in led and not cu._cand(cube, D11, led)        # read late now: never queued again


def test_a_newer_lo_day_of_the_month_stays_lo_through_a_refold(tmp_path):
    """Oct 11 (folded collapsed before the guard, ripe on Oct 16) and Oct 12 (held on Oct 15, still empty on Oct 16:
    folded "lo" at its cap) in one month: the refold of Oct 16 fixes Oct 11 and keeps Oct 12 as it is, still "lo";
    the next day's refold reads it again once GA4 filled it."""
    data = str(tmp_path)
    _legacy(data)
    D12 = date(2026, 10, 12)
    for T in (date(2026, 10, 15), date(2026, 10, 16)):
        cube = cu.Cube(data, "a~1", "222")
        cu.step_app(CollapseGA(today=T, empty={D12}), cube, T, HS, at(T, 0, 5))
        _save(cube)
        if T.day == 15:
            assert cube.head["hold"][0] == "2026-10-12" and not cube.head["rf"].get("k")   # Oct 11 not ripe yet
    mo = _month(data, "2026-10")
    p = mo["days"]["2026-10-12"]["lo"]
    assert p >= cu.PK_MIN and mo["days"]["2026-10-12"]["t"] < cu.COLLAPSE * p
    assert mo["days"]["2026-10-11"]["t"] == full(D11)
    assert mo["rf"]["t1"] == {"2026-10-11": full(D11), "2026-10-12": mo["days"]["2026-10-12"]["t"]}
    assert cu._cand(cube, D12, mo["days"]["2026-10-12"]) and not cu._cand(cube, D11, mo["days"]["2026-10-11"])
    T = date(2026, 10, 17)                                          # Oct 12 ripe, GA4 filled it: refolded again
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(today=T), cube, T, HS, at(T, 0, 5))
    _save(cube)
    led = _month(data, "2026-10")["days"]["2026-10-12"]
    assert led["t"] == full(D12) and "lo" not in led and cube.refolded == 1


def test_refold_takes_out_a_whole_read_made_while_the_day_was_collapsed(monkeypatch):
    monkeypatch.setattr(cu, "Q_CALLS", 120)
    cube = cu.Cube(None, "a~1", "222")
    low = {"q": {"2026-09-01": {"1": 5}}, "qt": 100, "qn": 0, "qx": 420, "qs": "ok", "qr": 3}
    ok = {"q": {"2026-09-01": {"1": 900}}, "qt": 9_000, "qn": 0, "qx": 420, "qs": "ok", "qr": 30}
    cube.q_put("2026-10-11", low, "2026-10-16T01:00:00Z")           # Sunday: its week is Monday Oct 5 …
    cube.q_put("2026-10-10", ok, "2026-10-15T01:00:00Z")            # … with Saturday Oct 10
    cube.q_put("2026-10-12", ok, "2026-10-17T01:00:00Z")            # Monday Oct 12: the next week
    cu._rf_q(cube, "2026-10-11", {"t": 10_000}, {"t": 50})
    qd = cube.qmonth("2026-10")["days"]
    assert sorted(qd) == ["2026-10-12"] and cube.head["qh"]["p"] == ["2026-10-10", "2026-10-11"]
    assert cube.qmonth("2026-10")["q"]["2026-09-01"]["1"] == {"2026-10-12": 900}
    cube2 = cu.Cube(None, "a~1", "222")                             # a whole read made once GA4 filled it: kept
    cube2.q_put("2026-10-11", ok, "2026-10-17T01:00:00Z")
    cu._rf_q(cube2, "2026-10-11", {"t": 10_000}, {"t": 50})
    assert "2026-10-11" in cube2.qmonth("2026-10")["days"] and not (cube2.head.get("qh") or {}).get("p")
    cube3 = cu.Cube(None, "a~1", "222")                             # a day folded as nothing, revenue now: its q read
    cu._rf_q(cube3, "2026-10-11", {"t": 10_000, "loss": 0, "fl": 0}, {"t": 0, "loss": 0, "fl": 0})
    assert cube3.head["qh"]["p"] == ["2026-10-11"]


def test_refold_with_q_and_users_on_as_in_the_build(tmp_path, monkeypatch):
    """The build's settings (q and the users on): Oct 11's whole read (q), made once it settled while GA4 still held it
    empty, goes when the refold reads the day whole — and is read again next run, whole, its users with it."""
    monkeypatch.setattr(cu, "Q_CALLS", 120)
    monkeypatch.setattr(cu, "U_ON", True)
    data = str(tmp_path)
    _legacy(data)
    cube = cu.Cube(data, "a~1", "222")              # its whole read due first (the other days': the history fill's)
    cube.head.setdefault("qh", {})["p"] = ["2026-10-11"]
    _save(cube)
    T = D11 + timedelta(days=cu.RF_RIPE)            # Oct 16: settled — q reads it while GA4 still holds it empty
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(CollapseGA(today=T, empty={D11}), cube, T, HS, at(T, 1))
    _save(cube)
    q = cu.load_q(data, "a~1", "222", "2026-10")
    assert q["days"]["2026-10-11"]["qs"] == "ok" and q["days"]["2026-10-11"]["qt"] < 0.01 * full(D11)
    assert cube.head["rf"]["wait"][0] == "2026-10-11"
    T += timedelta(days=1)                          # GA4 filled it: the refold reads the month, that q goes
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(today=T), cube, T, HS, at(T, 1))
    _save(cube)
    assert _month(data, "2026-10")["days"]["2026-10-11"]["t"] == full(D11) and not cube.head["rf"].get("k")
    assert "2026-10-11" not in cu.load_q(data, "a~1", "222", "2026-10")["days"]
    assert "2026-10-11" in cube.head["qh"]["p"]
    cube = cu.Cube(data, "a~1", "222")              # the next run: read again, whole
    cu.step_app(FakeGA(today=T), cube, T, HS, at(T, 3))
    _save(cube)
    q = cu.load_q(data, "a~1", "222", "2026-10")
    assert q["days"]["2026-10-11"]["qs"] == "ok" and q["days"]["2026-10-11"]["qt"] > 0.5 * full(D11)
    with gzip.open(cu.u_path(data, "a~1", "2026-10"), "rt") as f:
        u = json.load(f)
    assert u["c"]["2026-10-11"]["by"] == "rf" and u["q"]["2026-10-11"]["s"] == "ok"
    assert u["q"]["2026-10-11"]["at"] == q["days"]["2026-10-11"]["at"]   # the users of that very read


def test_a_young_day_ga4_empties_during_a_refold_makes_it_wait(tmp_path, monkeypatch):
    """Oct 13, folded whole by the walk, is answered empty while the refold reads October again: the copy never takes
    that read — the month waits (its file and users as they were, Oct 11's new users kept with the copy) and swaps once
    GA4 answers Oct 13 whole again."""
    monkeypatch.setattr(cu, "U_ON", True)
    data, D13 = str(tmp_path), date(2026, 10, 13)
    _legacy(data)
    T = D11 + timedelta(days=cu.RF_RIPE)
    monkeypatch.setattr(cu, "RF_CALLS", 2)                          # run 1: Oct 11 (whole now) and Oct 1
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(today=T), cube, T, HS, at(T, 1))
    _save(cube)
    assert cube.head["rf"]["k"] == "2026-10" and _month(data, "2026-10")["days"]["2026-10-13"]["t"] == full(D13)
    monkeypatch.setattr(cu, "RF_CALLS", 30)                         # run 2: GA4 empties Oct 13 (3 days old)
    live = _raw(data, "2026-10")
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(CollapseGA(today=T, empty={D13}), cube, T, HS, at(T, 2))
    _save(cube)
    rf = cube.head["rf"]
    assert rf["k"] == "2026-10" and rf["wait"] == ["2026-10-13", "2026-10-16T02:00:00Z"]
    assert _raw(data, "2026-10") == live
    with gzip.open(cube.rf_path("2026-10"), "rt") as f:
        copy = json.load(f)
    assert "2026-10-13" not in copy["days"] and copy["days"]["2026-10-11"]["t"] == full(D11)
    assert copy["rfu"]["2026-10-11"][0] == "rf"                     # its users wait with the copy …
    with gzip.open(cu.u_path(data, "a~1", "2026-10"), "rt") as f:
        assert json.load(f)["c"]["2026-10-11"]["by"] == "fold"      # … the walk's stay meanwhile
    cube = cu.Cube(data, "a~1", "222")                              # run 3: whole again — the copy is the month
    cu.step_app(FakeGA(today=T), cube, T, HS, at(T, 3))
    _save(cube)
    mo = _month(data, "2026-10")
    assert not cube.head["rf"].get("k") and "wait" not in cube.head["rf"] and mo["days"]["2026-10-13"]["t"] == full(D13)
    assert "rfu" not in mo and "rfq" not in mo and not os.path.exists(cube.rf_path("2026-10"))
    with gzip.open(cu.u_path(data, "a~1", "2026-10"), "rt") as f:
        assert json.load(f)["c"]["2026-10-11"]["by"] == "rf"


def test_the_copy_takes_the_days_the_walk_folds_meanwhile_and_a_stop_keeps_it(tmp_path, monkeypatch):
    """A refold over three property days, a budget Stop in it: the copy keeps every day read, the month file only
    what the walk folds, and the swapped month holds the days the walk folded meanwhile — every cell as a month GA4
    never collapsed."""
    data = str(tmp_path)
    _legacy(data)
    monkeypatch.setattr(cu, "RF_CALLS", 3)
    T = D11 + timedelta(days=cu.RF_RIPE)
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(today=T), cube, T, HS, at(T, 1))
    _save(cube)
    n1 = len(json.loads(gzip.decompress(open(cube.rf_path("2026-10"), "rb").read()))["days"])
    assert cube.head["rf"]["k"] == "2026-10" and n1 == 3
    T2 = T + timedelta(days=1)                                      # a new day: the walk folds Oct 14; a Stop in it
    cube = cu.Cube(data, "a~1", "222")
    ga = FakeGA(today=T2, stop_after=None)
    ga.stop_after, ga.stop_why = None, "budget"
    calls = []

    def stop_late(body, **kw):                                      # the budget runs out after the refold's 2nd read
        calls.append(body["dateRanges"][0]["startDate"])
        if len([c for c in calls if c < "2026-10-14"]) > 2:
            raise cu.Stop("budget")
        return FakeGA.report_all(ga, body, **kw)
    ga.report_all = stop_late
    try:
        cu.step_app(ga, cube, T2, HS, at(T2, 1))
        raise AssertionError("no Stop")
    except cu.Stop:
        pass
    _save(cube)                                                     # as refresh_all: months, copy, then the head
    assert "2026-10-14" in _month(data, "2026-10")["days"]          # the walk's fold is in the month file
    n2 = len(json.loads(gzip.decompress(open(cube.rf_path("2026-10"), "rb").read()))["days"])
    assert n2 == n1 + 2 and cube.head["rf"]["k"] == "2026-10"
    for i in range(10):
        cube = cu.Cube(data, "a~1", "222")
        cu.step_app(FakeGA(today=T2), cube, T2, HS, at(T2, 2 + i))
        _save(cube)
        if not cube.head["rf"].get("k"):
            break
    mo, ref = _month(data, "2026-10"), _whole(date(2026, 10, 14)).month("2026-10")
    assert {f: mo[f] for f in CELLS} == {f: ref[f] for f in CELLS} and "2026-10-14" in mo["days"]


def test_a_copy_no_head_names_is_never_used(tmp_path):
    data = str(tmp_path)
    cube = cu.Cube(data, "a~1", "222")
    os.makedirs(cu.app_dir(data, "a~1"), exist_ok=True)
    stale = dict(cu._empty_month("222"), rf={"at": "2026-10-01T00:00:00Z"})
    stale["days"]["2026-10-02"] = {"t": 5}
    cu.write_json_gz_stable(cube.rf_path("2026-10"), stale)
    cube.head["rf"] = {"k": "2026-10", "at": "2026-10-16T01:00:00Z"}
    assert cube.rf_copy("2026-10")["days"] == {}
    cube2 = cu.Cube(data, "a~1", "222")
    cube2.head["rf"] = {"k": "2026-10", "at": "2026-10-01T00:00:00Z"}
    assert cube2.rf_copy("2026-10")["days"] == {"2026-10-02": {"t": 5}}


def test_the_neighbours_rule_and_the_property_day():
    """_guard with no peak: under LOW × the median of D − 7 … D − 1 (≥ LOW_DAYS of them, the median ≥ PK_MIN) held;
    above it, or with a small median, folded. _early judges by the property's day of the read."""
    cube = cu.Cube(None, "a~1", "222")
    mo = cube.month("2026-10")
    for i in range(1, 8):
        mo["days"]["2026-10-%02d" % (11 - i)] = {"t": 10 * cu.PK_MIN}
    T = D11 + timedelta(days=cu.FINAL_LAG)
    assert cu._guard(cube, D11, {"t": 0, "fl": 0}, T, "x") is True
    assert cu._guard(cube, D11, {"t": 5 * cu.PK_MIN, "fl": 0}, T, "x") is False
    assert cu._guard(cube, D11, {"t": 0, "fl": 1}, T, "x") is True        # a flagged read: the neighbours judge it
    small = cu.Cube(None, "a~1", "222")
    for i in range(1, 8):
        small.month("2026-10")["days"]["2026-10-%02d" % (11 - i)] = {"t": cu.PK_MIN // 2}
    assert cu._guard(small, D11, {"t": 0, "fl": 0}, T, "x") is False
    led = {"at": "2026-11-16T01:00:00Z"}                            # Los Angeles: Nov 15, 17:00 — 4 days after Nov 11
    D = date(2026, 11, 11)
    assert cu._early(led, D, "America/Los_Angeles") and not cu._early(led, D)
    led = {"at": "2026-11-15T20:00:00Z"}                            # India: Nov 16, 01:30 — 5 days after
    assert not cu._early(led, D, "Asia/Kolkata") and cu._early(led, D)


def test_no_refold_starts_beside_a_repair_building_its_copy(tmp_path, monkeypatch):
    """The repair on and building its copy: no refold starts. The repair off (as in the build), a repair month left
    in the head never blocks it — and a refold of that same month drops the repair's copy (its older reads)."""
    data = str(tmp_path)
    _legacy(data)
    T = D11 + timedelta(days=cu.RF_RIPE)
    monkeypatch.setattr(cu, "REPAIR_CALLS", 30)
    cube = cu.Cube(data, "a~1", "222")
    cube.head["rep"] = {"sv": cu.SPLIT_V, "k": "2026-10", "at": "2026-10-01T00:00:00Z"}
    ga = FakeGA(today=T)
    assert cu.refold(ga, cube, at(T, 1), T) is False and ga.calls == 0 and not cube.head["rf"].get("k")
    monkeypatch.setattr(cu, "REPAIR_CALLS", 0)
    cu.write_json_gz_stable(cube.rep_path("2026-10"), dict(cu._empty_month("222"), rep={"sv": cu.SPLIT_V}))
    _save(cube)
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(today=T), cube, T, HS, at(T, 2))
    _save(cube)
    assert cube.refolded == 1 and _month(data, "2026-10")["days"]["2026-10-11"]["t"] == full(D11)
    assert not os.path.exists(cube.rep_path("2026-10")) and "k" not in cube.head["rep"]


def test_an_old_day_ga4_answers_collapsed_in_a_refold_waits_too(tmp_path):
    """Oct 2 (14 days old, folded whole) answered empty while the refold reads October: never merged so — the month
    waits (counted), at any age, and goes on once GA4 answers it whole."""
    data, D2 = str(tmp_path), date(2026, 10, 2)
    _legacy(data)
    T = D11 + timedelta(days=cu.RF_MAX + 2)                         # Oct 23: Oct 2 well past RF_MAX
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(CollapseGA(today=T, empty={D2}), cube, T, HS, at(T, 1))
    _save(cube)
    assert cube.head["rf"]["wait"][0] == "2026-10-02" and _month(data, "2026-10")["days"]["2026-10-11"]["t"] < full(D11)
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(today=T), cube, T, HS, at(T, 2))
    _save(cube)
    mo = _month(data, "2026-10")
    assert not cube.head["rf"].get("k") and mo["days"]["2026-10-02"]["t"] == full(D2)
    assert mo["days"]["2026-10-11"]["t"] == full(D11)


def test_a_refold_waiting_too_long_on_a_day_the_walk_had_whole_is_given_up(tmp_path):
    """Oct 2 (folded whole) answered collapsed in every read of the refold for RF_WAIT_DAYS: the month's refold is given
    up — its copy dropped, the month file as it was, logged — and October is not started again for RF_SKIP_DAYS; then
    it is, and with GA4 whole it goes through."""
    data, D2 = str(tmp_path), date(2026, 10, 2)
    _legacy(data)
    T = D11 + timedelta(days=cu.RF_RIPE)
    gave = None
    for i in range(cu.RF_WAIT_DAYS + 1):
        Ti = T + timedelta(days=i)
        before = _raw(data, "2026-10")
        cube = cu.Cube(data, "a~1", "222")
        cu.step_app(CollapseGA(today=Ti, empty={D2}), cube, Ti, HS, at(Ti, 1))
        _save(cube)
        days = _month(data, "2026-10")["days"]
        assert days["2026-10-02"]["t"] == full(D2) and days["2026-10-11"]["t"] < 0.01 * full(D11)
        if cube.rf_gave:
            gave = Ti
            break
        assert cube.head["rf"]["wait"] == ["2026-10-02", "2026-10-16T01:00:00Z"]
    assert gave == T + timedelta(days=cu.RF_WAIT_DAYS) and not os.path.exists(cube.rf_path("2026-10"))
    rf = cube.head["rf"]
    assert not rf.get("k") and rf["log"][-1][3] == "2026-10-02" and rf["skip"]["2026-10"] == (
        gave + timedelta(days=cu.RF_SKIP_DAYS)).isoformat()
    T2 = gave + timedelta(days=1)                                   # skipped: no refold of October
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(today=T2), cube, T2, HS, at(T2, 1))
    _save(cube)
    assert not cube.head["rf"].get("k") and cube.refolded == 0
    T3 = gave + timedelta(days=cu.RF_SKIP_DAYS)                     # the skip over: read again, whole now
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(today=T3), cube, T3, HS, at(T3, 1))
    _save(cube)
    assert cube.refolded == 1 and "skip" not in cube.head["rf"]
    assert _month(data, "2026-10")["days"]["2026-10-11"]["t"] == full(D11)


def test_the_repair_keeps_the_guards_rule(tmp_path, monkeypatch):
    """The repair (off in the build): a read under COLLAPSE × what the walk folded is never merged; a month holding a
    "lo" day is left to the refold."""
    monkeypatch.setattr(cu, "REPAIR_CALLS", 30)
    monkeypatch.setattr(cu, "RF_CALLS", 0)
    cube = cu.Cube(None, "a~1", "222")
    for D in _days(date(2026, 9, 1), date(2026, 9, 10)):            # folded by the one-level split, "(other)" left
        rec = cu.read_day(FakeGA(today=LATER), D, "t")
        rec.update(sv=1, ol=5, via="split")
        cube.fold(D, rec)
    cube.head["rep"] = {"sv": cu.SPLIT_V, "k": "2026-09", "at": "x", "c": 0, "n": 0}
    D5 = date(2026, 9, 5)
    ga = CollapseGA(today=LATER, empty={D5})
    assert cu.repair(ga, cube, datetime(2026, 10, 20, tzinfo=timezone.utc)) is True
    assert not cube.head["rep"].get("k") and cube.rp is None        # that month's repair ended, nothing merged of it
    assert cube.month("2026-09")["days"]["2026-09-05"]["t"] == full(D5) and cube.head["rep"]["blk"] == {
        "2026-09": "2026-09-05"}
    cube.head["rep"].update(k="2026-09", at="x2", c=0, n=0)         # tried again: that day first — one read, ended
    ga = CollapseGA(today=LATER, empty={D5})
    assert cu.repair(ga, cube, datetime(2026, 10, 27, tzinfo=timezone.utc)) is True and ga.calls == 1
    cube.head["rep"].update(k="2026-09", at="x3", c=0, n=0)         # GA4 whole again: the month through, "blk" gone
    cu.repair(FakeGA(today=LATER), cube, datetime(2026, 11, 3, tzinfo=timezone.utc))
    assert "blk" not in cube.head["rep"] and cube.month("2026-09")["rep"]["sv"] == cu.SPLIT_V
    cube.head["rep"].update(k="2026-09", at="y", c=0, n=0)          # a repair under way when the walk folds a "lo" day
    cube.month("2026-09")["days"]["2026-09-10"]["lo"] = 1           # into its month: left to the refold
    ga = FakeGA(today=LATER)
    assert cu.repair(ga, cube, datetime(2026, 10, 21, tzinfo=timezone.utc)) is False and ga.calls == 0
    assert not cube.head["rep"].get("k")
    lo = cu.Cube(None, "a~1", "222")
    for D in _days(date(2026, 9, 1), date(2026, 9, 3)):
        rec = cu.read_day(FakeGA(today=LATER), D, "t")
        if D.day == 2:
            rec["lo"], rec["ol"], rec["sv"], rec["via"] = 1, 5, 1, "split"
        lo.fold(D, rec)
    lo.head["rep"] = {"sv": cu.SPLIT_V, "q": [["2026-09", 0.5]], "scan": "2026-10-20T00:00:00Z"}
    ga = FakeGA(today=LATER)
    assert cu.repair(ga, lo, datetime(2026, 10, 20, tzinfo=timezone.utc)) is False and ga.calls == 0


def test_the_repair_never_runs_beside_a_refold(monkeypatch):
    monkeypatch.setattr(cu, "REPAIR_CALLS", 30)

    def busy(ga, cube, now, today):
        cube.head.setdefault("rf", {})["k"] = "2026-10"
        return False
    monkeypatch.setattr(cu, "refold", busy)
    monkeypatch.setattr(cu, "repair", lambda *a, **k: (_ for _ in ()).throw(AssertionError("repair called")))
    cu.step_app(FakeGA(today=T0), cu.Cube(None, "a~1", "222"), T0, HS, at(T0))


def test_counts_in_the_log_line():
    line = cu.log_line({"counts": {"held": 2, "low": 1, "rf_days": 14, "refolded": 1, "rf_wait": 1, "rf_gave": 1}})
    assert (", q early 0, held 2, folded low 1, refold days 14, months refolded 1, refold waiting 1, "
            "refold given up 1, calls 0, tokens 0") in line


def test_settings_and_the_workflow(monkeypatch):
    for k in ("GA4_CUBE_GUARD", "GA4_CUBE_RF_CALLS"):
        monkeypatch.delenv(k, raising=False)
    try:
        fresh = importlib.reload(cu)
        assert fresh.GUARD is True and fresh.RF_CALLS == 30
        monkeypatch.setenv("GA4_CUBE_GUARD", "false")
        monkeypatch.setenv("GA4_CUBE_RF_CALLS", "0")
        fresh = importlib.reload(cu)
        assert fresh.GUARD is False and fresh.RF_CALLS == 0
    finally:
        for k in ("GA4_CUBE_GUARD", "GA4_CUBE_RF_CALLS"):
            monkeypatch.delenv(k, raising=False)
        importlib.reload(cu)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        y = f.read()
    assert "GA4_CUBE_GUARD:" in y and "${{ vars.GA4_CUBE_GUARD || 'true' }}" in y
    assert "GA4_CUBE_RF_CALLS:" in y and "${{ vars.GA4_CUBE_RF_CALLS }}" in y
