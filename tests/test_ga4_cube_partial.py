"""🧊 The cube's settle check (admob_iq.fetch.ga4_cube; 16 Nov 2026), offline with the cube tests' fake GA4 and made-up
numbers: GA4 answering a day's final read partly short (by more than a day moves once folded — late events, a partly
empty answer — but far from a collapse: the fold guard folds it). Once the day settled the check reads GA4's whole
total of it once (only a day whose read was made before it settled); a day its month holds short of that by PART and
PS_MIN or more is partly short and its month is read again by the refold — whole, exactly the month of a fold never
short. A read again still short waits (read once a property day) until RF_MAX, then is merged as it is, unless it is
partly lower than the walk's fold: then that refold is given up and the day never a candidate again. With the check on
a refold never merges any day GA4 answers partly lower than the walk had it. A whole GA4 changes no month file; the
queue (once a property day, no month file read in an idle run), the cap, the time slice, the order; flagged, collapsed
and settled reads never checked; a total GA4 flags kept as None; the window; a Stop, an error; the switches; the users
of a day refolded; the counts in the log line; the settings and the workflow's repo variable."""
import importlib
import os
from datetime import date, timedelta

import pytest

from admob_iq.fetch import ga4_cube as cu
from admob_iq.fetch import ga4_firstopen as gf
from tests.test_ga4_cube import HS, FakeGA, _days
from tests.test_ga4_cube_guard import CELLS, CollapseGA, _month, _raw, _save, _whole, at, full

T0 = date(2026, 10, 13)
D11 = date(2026, 10, 11)
K11 = D11.isoformat()
SHARE = 0.8                                                     # the fold's share of the day (partly short)
USD = 1_000_000


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    """q, the users and the repair off (their own tests); the guard, the refold and the check on, as in the build —
    the check with room for every due day in one run (its cap: its own test)."""
    monkeypatch.setattr(cu, "Q_CALLS", 0)
    monkeypatch.setattr(cu, "U_ON", False)
    monkeypatch.setattr(cu, "REPAIR_CALLS", 0)
    monkeypatch.setattr(cu, "GUARD", True)
    monkeypatch.setattr(cu, "RF_CALLS", 30)
    monkeypatch.setattr(cu, "CK_CALLS", 60)


class RowsShort(CollapseGA):
    """GA4 answering the days in `empty` with `share` of their rows while its date-only total of them is whole (the
    check's read): a read again still short."""

    def report_all(self, body, **kw):
        if [d["name"] for d in body["dimensions"]] == ["date"]:
            keep, self.empty = self.empty, set()
            try:
                return super().report_all(body, **kw)
            finally:
                self.empty = keep
        return super().report_all(body, **kw)


class Shares(FakeGA):
    """GA4 answering each day of `shares` with that share of its rows (revenue and users) while its date-only total
    of every day is whole (the check's read)."""

    def __init__(self, shares=None, **kw):
        super().__init__(**kw)
        self.shares, self._tot = dict(shares or {}), False

    def rows_of(self, D):
        rows = super().rows_of(D)
        f = 1.0 if self._tot else self.shares.get(D, 1.0)
        if f != 1.0:
            for r in rows:
                r["totalAdRevenue"] *= f
                r["activeUsers"] = int(r["activeUsers"] * f)
        return rows

    def report_all(self, body, **kw):
        self._tot = [d["name"] for d in body["dimensions"]] == ["date"]
        try:
            return super().report_all(body, **kw)
        finally:
            self._tot = False


def _whole_ga(T):
    return FakeGA(today=T)


def _walk(cube, a, b, ga_for=_whole_ga, data=None):
    """A run each property day a … b at 00:05 UTC (the walk folds each new final day at D + 3; the first run the
    backfill). data: the files written between runs (the build's way). Returns the cube and the last GA4."""
    ga = None
    for T in _days(a, b):
        if data:
            cube = cu.Cube(data, "a~1", "222")
        ga = ga_for(T)
        cu.step_app(ga, cube, T, HS, at(T, 0, 5))
        if data:
            _save(cube)
    return cube, ga


def _short11(T):
    """GA4 on day T: Oct 11's final read (Oct 14) partly short, every other read whole."""
    return CollapseGA(today=T, empty={D11}, share=SHARE) if T == D11 + timedelta(days=cu.FINAL_LAG) else FakeGA(today=T)


def _folded_short(upto=date(2026, 10, 17), data=None):
    """Runs Oct 13 … upto: Oct 11 folded partly short on Oct 14 (not a collapse: no hold, no mark)."""
    cube, _ = _walk(cu.Cube(data, "a~1", "222"), T0, upto, _short11, data)
    if data:
        cube = cu.Cube(data, "a~1", "222")
    led = cube.ledger(K11)
    assert led is not None and "lo" not in led and "rd" not in led
    if upto < D11 + timedelta(days=cu.CK_AGE):                      # not settled yet: as the walk folded it
        assert abs(led["t"] - SHARE * full(D11)) < 1000 and K11 not in cube.head.get("ck", {})
    return cube


# ── the rule ─────────────────────────────────────────────────────────────────────────
def test_partly_short_by_part_and_ps_min_only_on_a_read_made_before_the_day_settled():
    cube = cu.Cube(None, "a~1", "222")
    ck = cube.head["ck"] = {}
    early, late = "2026-10-14T00:05:00Z", "2026-10-18T01:00:00Z"   # read 3 / 7 days after Oct 11

    def ps(tot, t, n=0, a=early, **led):
        ck[K11] = [tot, "2026-10-18T01:00:00Z", n]
        return cu._ps(cube, K11, dict(t=t, at=a, **led))

    assert ps(100 * USD, 97 * USD) and not ps(100 * USD, 97 * USD + 1)     # 3 % of the total
    assert ps(10 * USD, 9 * USD) and not ps(10 * USD, 9 * USD + 1)        # … and at least 1 USD
    assert not ps(10 * USD, 9.5 * USD)                                     # 5 % but half a dollar
    assert not ps(100 * USD, 120 * USD)                                    # more than GA4's total: never
    assert not ps(100 * USD, 50 * USD, a=late)                             # read once settled: as good as the check
    assert not ps(100 * USD, 50 * USD, a=None)                             # read when: unknown
    assert not ps(100 * USD, 50 * USD, n=cu.PS_TRIES)                      # given up on
    assert not ps(100 * USD, 50 * USD, fl=1) and not ps(100 * USD, 50 * USD, lo=1)
    ck[K11] = [None, "2026-10-18T01:00:00Z", 0]                            # a total GA4 flagged: nothing to judge by
    assert not cu._ps(cube, K11, {"t": 0, "at": early})
    ck.pop(K11)                                                            # never checked
    assert not cu._ps(cube, K11, {"t": 0, "at": early}) and not cu._ps(cube, "2026-10-12", None)
    cube.head["ck"] = ["damaged"]                                          # a damaged head: never trusted
    assert not cu._ps(cube, K11, {"t": 0, "at": early}) and cu._ck(cube) == {}
    assert cu._short({"t": 97 * USD}, 100 * USD) and not cu._short({"t": 98 * USD}, 100 * USD)


def test_which_days_are_due_the_check():
    cube, T = cu.Cube(None, "a~1", "222"), date(2026, 10, 18)

    def due(at, **led):
        return cu._ck_due(cube, K11, dict(t=5 * USD, at=at, **led), T)

    assert due("2026-10-14T00:05:00Z")                              # 7 days old, read 3 days after it
    assert not due("2026-10-14T00:05:00Z", fl=1) and not due("2026-10-14T00:05:00Z", lo=9)
    assert not due("2026-10-18T00:05:00Z")                          # read once settled
    assert not due(None) and not cu._ck_due(cube, K11, None, T)
    assert not cu._ck_due(cube, K11, {"t": 5, "at": "2026-10-14T00:05:00Z"}, T - timedelta(days=1))   # 6 days old
    cube.head["time_zone"] = "Asia/Kolkata"                         # the property's day: Oct 17 20:00 UTC is Oct 18
    assert not due("2026-10-17T20:00:00Z") and due("2026-10-17T18:00:00Z")


# ── the check and the refold ─────────────────────────────────────────────────────────
def test_a_day_folded_partly_short_is_found_once_settled_and_its_month_read_again_whole():
    cube = _folded_short()                                          # runs Oct 13 … 17
    short_t = cube.ledger(K11)["t"]
    ck = cube.head["ck"]                                            # Oct 17: the days read early (Oct 7 … 10, the
    assert sorted(ck) == ["2026-10-07", "2026-10-08", "2026-10-09", "2026-10-10"]   # backfill's newest) 7 days old;
    assert all(v[0] == full(date.fromisoformat(D)) and v[2] == 0 for D, v in ck.items())     # Oct 11 not yet
    assert not (cube.head["rf"].get("log") or [])
    T = D11 + timedelta(days=cu.CK_AGE)                             # Oct 18: Oct 11 settled
    ga = FakeGA(today=T)
    assert cu.step_app(ga, cube, T, HS, at(T)) == "fetched"
    assert ck[K11] == [full(D11), "2026-10-18T01:00:00Z", 1]        # read once, a refold merged it
    assert cube.ps_new == 1 and cube.refolded == 1 and cube.checked == 5
    mo, ref = cube.month("2026-10"), _whole(T - timedelta(days=cu.FINAL_LAG)).month("2026-10")
    assert {f: mo[f] for f in CELLS} == {f: ref[f] for f in CELLS}  # exactly the month of a fold never short
    assert mo["rf"]["t0"] == {K11: short_t} and mo["rf"]["t1"] == {K11: full(D11)}
    assert cube.head["rf"]["log"][-1][:2] == ["2026-10", [K11]]
    assert not cu._ps(cube, K11, mo["days"][K11]) and not cu._cand(cube, D11, mo["days"][K11])
    assert "2026-09-30" not in ck                                   # read once settled (the backfill): never checked
    ga = FakeGA(today=T)                                            # an hour on: nothing checked again, no refold
    cu.step_app(ga, cube, T, HS, at(T, 2))
    assert ga.calls == 0 and cube.refolded == 1


def test_a_partly_short_day_of_the_month_before_the_edges_is_found_too():
    D = date(2026, 9, 30)
    cube, _ = _walk(cu.Cube(None, "a~1", "222"), date(2026, 10, 2), date(2026, 10, 7),
                    lambda T: CollapseGA(today=T, empty={D}, share=SHARE) if T == D + timedelta(days=cu.FINAL_LAG)
                    else FakeGA(today=T))
    mo = cube.month("2026-09")                                      # Oct 7: Sep 30 settled, partly short: September
    assert mo["days"][D.isoformat()]["t"] == full(D) and mo["rf"]["t1"] == {D.isoformat(): full(D)}   # read again
    assert cube.head["rf"]["log"][-1][:2] == ["2026-09", [D.isoformat()]] and cube.ps_new == 1


def test_a_read_again_still_short_waits_read_once_a_day_until_rf_max_then_is_merged_as_it_is():
    cube = _folded_short()
    short_t = cube.ledger(K11)["t"]
    T = D11 + timedelta(days=cu.CK_AGE)                             # Oct 18: found partly short, GA4's rows still short
    cu.step_app(RowsShort(today=T, empty={D11}, share=SHARE), cube, T, HS, at(T))
    rf = cube.head["rf"]
    assert rf["k"] == "2026-10" and rf["ps"] == [K11] and rf["wait"] == [K11, "2026-10-18T01:00:00Z", "2026-10-18"]
    assert cube.ledger(K11)["t"] == short_t and cube.head["ck"][K11][2] == 0
    ga = RowsShort(today=T, empty={D11}, share=SHARE)               # the same property day: not read again
    cu.step_app(ga, cube, T, HS, at(T, 5))
    assert ga.calls == 0 and rf["wait"][2] == "2026-10-18"
    T1 = T + timedelta(days=1)                                      # a day on: read again (the walk's new day too)
    ga = RowsShort(today=T1, empty={D11}, share=SHARE)
    cu.step_app(ga, cube, T1, HS, at(T1))
    assert rf["wait"] == [K11, "2026-10-18T01:00:00Z", "2026-10-19"] and rf["k"] == "2026-10"
    Tm = D11 + timedelta(days=cu.RF_MAX)                            # RF_MAX days old, still short — but not lower than
    cu.step_app(RowsShort(today=Tm, empty={D11}, share=SHARE), cube, Tm, HS, at(Tm))   # the walk's fold: merged
    mo = cube.month("2026-10")
    assert not cube.head["rf"].get("k") and mo["days"][K11]["t"] == short_t and mo["rf"]["t1"] == {K11: short_t}
    assert cube.head["ck"][K11][2] == 1 and not cu._ps(cube, K11, mo["days"][K11])   # read once settled: ended
    ga = FakeGA(today=Tm)                                           # never a candidate again
    cube.head["rf"].pop("scan", None)
    assert cu.refold(ga, cube, at(Tm, 5), Tm) is False and ga.calls == 0


def test_at_rf_max_a_read_lower_than_the_walks_fold_is_never_merged():
    cube = _folded_short()
    for T in _days(D11 + timedelta(days=cu.CK_AGE), D11 + timedelta(days=cu.RF_MAX - 1)):     # waiting: still short
        cu.step_app(RowsShort(today=T, empty={D11}, share=SHARE), cube, T, HS, at(T))
    assert cube.head["rf"]["k"] == "2026-10" and cube.rf is not None
    before = {D: dict(v) for D, v in cube.month("2026-10")["days"].items()}
    Tm = D11 + timedelta(days=cu.RF_MAX)                            # RF_MAX: GA4 answers it LOWER than the walk had it
    cu.step_app(RowsShort(today=Tm, empty={D11}, share=0.6), cube, Tm, HS, at(Tm))
    rf, mo = cube.head["rf"], cube.month("2026-10")
    assert not rf.get("k") and rf["log"][-1] == ["2026-10", [K11], "2026-10-21T01:00:00Z", K11]
    assert "skip" not in rf and cube.rf_gave == 1 and cube.refolded == 0     # nothing else waited: no skip
    assert all(mo["days"][D] == v for D, v in before.items()) and "rf" not in mo    # never swapped: as it was
    assert abs(mo["days"][K11]["t"] - SHARE * full(D11)) < 1000     # the walk's fold kept
    assert cube.rf is None                                          # the copy dropped
    assert cube.head["ck"][K11][2] == cu.PS_TRIES and not cu._ps(cube, K11, mo["days"][K11])


def test_a_settled_day_a_refold_reads_partly_lower_is_merged_as_ga4_answers_it_and_counted():
    """October read again for Oct 11 (partly short); GA4 answers Oct 5 (whole in the walk, settled) at 0.7 then:
    merged as it is (GA4's own answer — never waited on), counted "refold merged lower"; the refold done at once."""
    D5 = date(2026, 10, 5)
    cube = _folded_short()
    T = D11 + timedelta(days=cu.CK_AGE)
    cu.step_app(Shares({D5: 0.7}, today=T), cube, T, HS, at(T))
    mo = cube.month("2026-10")
    assert not cube.head["rf"].get("k") and "wait" not in cube.head["rf"] and cube.refolded == 1
    assert cube.rf_lower == 1 and mo["days"][K11]["t"] == full(D11) and abs(mo["days"]["2026-10-05"]["t"]
                                                                            - 0.7 * full(D5)) < 1000


def test_a_lo_day_merged_as_it_is_at_rf_max_is_never_checked():
    """Oct 11 folded collapsed ("lo", at its hold's cap); its refold waits while GA4's rows of it stay empty (its
    date-only total whole), merges it as it is at RF_MAX — a read made once it settled: the check never reads it, no
    second refold."""
    cube = cu.Cube(None, "a~1", "222")
    cu.step_app(FakeGA(today=T0), cube, T0, HS, at(T0))
    for T in _days(T0 + timedelta(days=1), D11 + timedelta(days=cu.RF_MAX + 2)):
        cu.step_app(RowsShort(today=T, empty={D11}, share=0.005), cube, T, HS, at(T, 0, 5))
    mo = cube.month("2026-10")
    assert mo["rf"]["t1"][K11] < 0.01 * full(D11) and "lo" not in mo["days"][K11]
    assert K11 not in cube.head.get("ck", {}) and cube.refolded == 1 and cube.ps_new == 0


def test_a_flagged_lower_read_never_holds_a_refold():
    """GA4 answers Oct 5 a tenth lower in the refold, thresholded: not judged so — merged, the refold done at once."""
    D5 = date(2026, 10, 5)
    cube = _folded_short()
    T = D11 + timedelta(days=cu.CK_AGE)
    cu.step_app(Shares({D5: 0.9}, today=T, thr_day=D5), cube, T, HS, at(T))
    mo = cube.month("2026-10")
    assert not cube.head["rf"].get("k") and cube.refolded == 1 and "wait" not in cube.head["rf"]
    assert mo["days"]["2026-10-05"]["fl"] and mo["days"][K11]["t"] == full(D11) and cube.rf_lower == 0


def test_a_young_day_read_lower_in_a_refold_is_merged_and_checked_later():
    """The refold of Oct 18 reads Oct 14 (4 days old) a fifth low: merged as it is (young: its own check comes
    later); on Oct 21 the check finds it partly short and October is read again — whole."""
    D14 = date(2026, 10, 14)
    cube = _folded_short()
    T = D11 + timedelta(days=cu.CK_AGE)
    cu.step_app(Shares({D14: 0.8}, today=T), cube, T, HS, at(T))
    assert cube.refolded == 1 and abs(cube.ledger("2026-10-14")["t"] - 0.8 * full(D14)) < 1000
    _walk(cube, T + timedelta(days=1), D14 + timedelta(days=cu.CK_AGE))
    assert cube.refolded == 2 and cube.ledger("2026-10-14")["t"] == full(D14) and cube.ps_new == 2


def test_a_day_given_up_on_never_holds_a_later_refold():
    """Oct 11 given up on at RF_MAX (GA4's rows of it lower than the walk's fold). Oct 19 then folds collapsed
    ("lo"): its refold reads Oct 11 lower again — merged as GA4 answers it (never waited on, counted), Oct 19 whole."""
    cube = _folded_short()
    for T in _days(D11 + timedelta(days=cu.CK_AGE), D11 + timedelta(days=cu.RF_MAX - 1)):
        cu.step_app(Shares({D11: SHARE}, today=T), cube, T, HS, at(T))
    Tm = D11 + timedelta(days=cu.RF_MAX)
    cu.step_app(Shares({D11: 0.6}, today=Tm), cube, Tm, HS, at(Tm))
    assert cu._locked(cube.head["ck"][K11]) and cube.rf_gave == 1 and "skip" not in cube.head["rf"]
    D19 = date(2026, 10, 19)
    for T in _days(Tm + timedelta(days=1), D19 + timedelta(days=cu.FINAL_LAG + cu.HOLD_DAYS)):    # Oct 22, 23:
        cu.step_app(Shares({D11: 0.6, D19: 0.005}, today=T), cube, T, HS, at(T, 0, 5))           # empty → "lo"
    assert cube.ledger("2026-10-19")["lo"]
    T = D19 + timedelta(days=cu.RF_RIPE)                            # Oct 24: its refold
    cu.step_app(Shares({D11: 0.6}, today=T), cube, T, HS, at(T))
    mo = cube.month("2026-10")
    assert not cube.head["rf"].get("k") and cube.refolded == 1 and cube.rf_lower == 1   # Oct 11: GA4's answer now
    assert mo["days"]["2026-10-19"]["t"] == full(D19) and abs(mo["days"][K11]["t"] - 0.6 * full(D11)) < 1000


def test_partly_short_days_found_together_and_answered_lower_are_each_given_up_and_kept(monkeypatch):
    """The deploy's case: Oct 10 and 11 folded partly short, the check turned on Oct 25 (both past RF_MAX). GA4's rows
    of both now lower than the walk had them: each refold gives up at its first candidate (read first: little read),
    both days locked, the month as the walk folded it — no skip, no loop."""
    D10 = date(2026, 10, 10)
    monkeypatch.setattr(cu, "CK_CALLS", 0)
    cube, _ = _walk(cu.Cube(None, "a~1", "222"), T0, date(2026, 10, 24),
                    lambda T: Shares({D10: SHARE, D11: SHARE}, today=T) if T in (date(2026, 10, 13), date(2026, 10, 14))
                    else FakeGA(today=T))
    before = {D: dict(v) for D, v in cube.month("2026-10")["days"].items()}
    assert before["2026-10-10"]["t"] < 0.9 * full(D10) and before[K11]["t"] < 0.9 * full(D11)
    monkeypatch.setattr(cu, "CK_CALLS", 60)
    T = date(2026, 10, 25)
    for h in range(1, 5):
        cu.step_app(Shares({D10: 0.6, D11: 0.6}, today=T), cube, T, HS, at(T, h))
    rf, mo, ck = cube.head["rf"], cube.month("2026-10"), cube.head["ck"]
    assert cube.ps_new == 2 and cube.rf_gave == 2 and cube.refolded == 0 and not rf.get("k") and "skip" not in rf
    assert cu._locked(ck["2026-10-10"]) and cu._locked(ck[K11])
    assert all(mo["days"][D] == v for D, v in before.items()) and "rf" not in mo
    ga = FakeGA(today=T)                                            # nothing left to read again
    cu.step_app(ga, cube, T, HS, at(T, 6))
    assert ga.calls == 0


def test_a_partly_short_day_found_while_its_month_is_read_again_joins_that_refold(monkeypatch):
    """Oct 11 and Oct 14 folded partly short; the check (5 a run) finds Oct 11 first and October's refold starts (3
    days a run, in date order after its candidates). The next run finds Oct 14, not read into the copy yet: it joins
    the refold's candidates — read next, still short so it waits (once a property day), whole a day on: merged whole.
    (As an ordinary day it would have been merged as it was read, short, for good.)"""
    D14 = date(2026, 10, 14)
    monkeypatch.setattr(cu, "CK_CALLS", 0)
    cube, _ = _walk(cu.Cube(None, "a~1", "222"), T0, date(2026, 10, 21),
                    lambda T: Shares({D11: SHARE, D14: SHARE}, today=T) if T in (date(2026, 10, 14), date(2026, 10, 17))
                    else FakeGA(today=T))
    monkeypatch.setattr(cu, "CK_CALLS", 5)
    monkeypatch.setattr(cu, "RF_CALLS", 3)
    T = date(2026, 10, 22)
    cu.step_app(Shares({D14: 0.9}, today=T), cube, T, HS, at(T, 1))
    rf = cube.head["rf"]
    assert rf["k"] == "2026-10" and rf["ps"] == [K11] and K11 in cube.rf_copy("2026-10")["days"]
    cu.step_app(Shares({D14: 0.9}, today=T), cube, T, HS, at(T, 2))
    assert rf["ps"] == [K11, "2026-10-14"] and "2026-10-14" in rf["cand"]
    assert rf["wait"] == ["2026-10-14", "2026-10-22T02:00:00Z", "2026-10-22"]
    for i, T in enumerate(_days(date(2026, 10, 23), date(2026, 10, 30))):
        for h in (1, 2):
            cu.step_app(FakeGA(today=T), cube, T, HS, at(T, h))
        if not cube.head["rf"].get("k"):
            break
    mo = cube.month("2026-10")
    assert mo["days"][K11]["t"] == full(D11) and mo["days"]["2026-10-14"]["t"] == full(D14)
    assert sorted(mo["rf"]["t0"]) == [K11, "2026-10-14"] and cube.refolded == 1


def test_switching_the_check_off_during_its_refold_gives_the_refold_before_it(monkeypatch):
    cube = _folded_short()
    T = D11 + timedelta(days=cu.CK_AGE)
    cu.step_app(Shares({D11: SHARE}, today=T), cube, T, HS, at(T))
    assert cube.head["rf"]["wait"][0] == K11 and cube.head["rf"]["ps"] == [K11]
    monkeypatch.setattr(cu, "CK_CALLS", 0)
    T1 = T + timedelta(days=1)
    cu.step_app(Shares({D11: SHARE}, today=T1), cube, T1, HS, at(T1))
    mo = cube.month("2026-10")                                      # judged as a candidate is without the check:
    assert not cube.head["rf"].get("k") and cube.refolded == 1     # merged as it is
    assert abs(mo["days"][K11]["t"] - SHARE * full(D11)) < 1000


def test_with_ga4_whole_the_check_changes_no_month_file(tmp_path, monkeypatch):
    def run(data, ck):
        monkeypatch.setattr(cu, "CK_CALLS", 60 if ck else 0)
        _walk(None, T0, date(2026, 10, 25), data=data)

    a, b = str(tmp_path / "on"), str(tmp_path / "off")
    run(a, True)
    run(b, False)
    for k in ("2026-06", "2026-07", "2026-08", "2026-09", "2026-10"):
        assert _raw(a, k) == _raw(b, k)
    ha, hb = cu.load_head(a, "a~1"), cu.load_head(b, "a~1")
    assert sorted(ha["ck"]) == ["2026-10-%02d" % i for i in range(7, 19)]     # each early read once settled
    assert all(v[0] == full(date.fromisoformat(D)) and v[2] == 0 for D, v in ha["ck"].items())
    assert ha.pop("ckq") == [] and ha.pop("cks") == "2026-10-25"
    ha.pop("ck")
    assert ha == hb and not (ha.get("rf") or {}).get("log")         # the head the same but the check's


def test_the_queue_oldest_first_under_the_cap_made_once_a_day_with_no_month_read_when_idle(tmp_path, monkeypatch):
    data = str(tmp_path)
    monkeypatch.setattr(cu, "CK_CALLS", 0)
    _walk(None, T0, date(2026, 10, 30), data=data)                  # the check off: nothing checked yet
    monkeypatch.setattr(cu, "CK_CALLS", 3)
    T = date(2026, 10, 30)
    cube = cu.Cube(data, "a~1", "222")
    ga = FakeGA(today=T)
    cu.step_app(ga, cube, T, HS, at(T, 2))
    _save(cube)
    due = ["2026-10-%02d" % i for i in range(7, 24)]               # early reads, 7 days old or more (Oct 7 … 23)
    assert sorted(cube.head["ck"]) == due[:3] and cube.head["ckq"] == due[3:] and cube.head["cks"] == "2026-10-30"
    assert [q[0]["dimensions"] for q in ga.asked] == [[{"name": "date"}]] * 3    # one light call a day: its total
    loads = []
    real = cu.gu.load_store
    monkeypatch.setattr(cu.gu, "load_store",
                        lambda p, *a, **k: (loads.append(os.path.basename(p)), real(p, *a, **k))[1])
    for i in range(6):                                              # the same day: the queue goes on, 3 a run
        cube = cu.Cube(data, "a~1", "222")
        cu.step_app(FakeGA(today=T), cube, T, HS, at(T, 3 + i))
        _save(cube)
    assert sorted(cube.head["ck"]) == due and cube.head["ckq"] == []
    loads.clear()
    cube = cu.Cube(data, "a~1", "222")                              # idle: the queue used up today — no month read
    ga = FakeGA(today=T)
    cu.step_app(ga, cube, T, HS, at(T, 10))
    assert ga.calls == 0 and not [f for f in loads if f.startswith("2026-")]
    T1 = T + timedelta(days=1)                                      # a new property day: made again (Oct 24 due)
    cube = cu.Cube(data, "a~1", "222")
    cu.step_app(FakeGA(today=T1), cube, T1, HS, at(T1))
    assert "2026-10-24" in cube.head["ck"] and cube.head["cks"] == "2026-10-31"


def test_a_flagged_read_and_settled_reads_are_never_checked():
    cube, _ = _walk(cu.Cube(None, "a~1", "222"), T0, date(2026, 10, 16))
    assert sorted(cube.head["ck"]) == ["2026-10-07", "2026-10-08", "2026-10-09"]
    cube.month("2026-10")["days"]["2026-10-10"]["fl"] = 1           # GA4 flagged its read: its hidden part unknown
    _walk(cube, date(2026, 10, 17), date(2026, 10, 19))
    ck = cube.head["ck"]
    assert sorted(ck) == ["2026-10-07", "2026-10-08", "2026-10-09", "2026-10-11", "2026-10-12"]
    assert not any(D < "2026-10-07" for D in ck)                    # the backfill's reads: made settled


def test_a_total_ga4_flags_is_kept_as_none_and_never_read_again():
    cube, _ = _walk(cu.Cube(None, "a~1", "222"), T0, date(2026, 10, 17), lambda T: FakeGA(today=T, smp_total=True))
    T = date(2026, 10, 17)
    ck = cube.head["ck"]
    assert sorted(ck) == ["2026-10-07", "2026-10-08", "2026-10-09", "2026-10-10"]
    assert all(v[0] is None for v in ck.values()) and cube.ps_new == 0
    ga = FakeGA(today=T)
    cu.step_app(ga, cube, T, HS, at(T, 2))
    assert ga.calls == 0 and all(v[0] is None for v in ck.values())


def test_the_window_moves_and_old_entries_go():
    cube, _ = _walk(cu.Cube(None, "a~1", "222"), T0, date(2026, 11, 12))
    ck = cube.head["ck"]                                            # Nov 12: the edge's month (Nov) and October
    assert min(ck) == "2026-10-07" and max(ck) == "2026-11-05"
    _walk(cube, date(2026, 11, 13), date(2026, 12, 4))              # Dec 4: edge Dec 1 — December and November
    assert min(cube.head["ck"]) == "2026-11-01" and max(cube.head["ck"]) == "2026-11-27"


def test_a_stop_keeps_the_days_checked_and_the_call_cap_only_ends_the_check(monkeypatch):
    monkeypatch.setattr(cu, "CK_CALLS", 0)
    cube, _ = _walk(cu.Cube(None, "a~1", "222"), T0, date(2026, 10, 20))
    monkeypatch.setattr(cu, "CK_CALLS", 60)
    T = date(2026, 10, 20)                                          # due: Oct 7 … 13
    ga = FakeGA(today=T, stop_after=3, stop_why="budget")          # the run's budget: the app stops here
    with pytest.raises(gf.Stop):
        cu.step_app(ga, cube, T, HS, at(T, 2))
    assert sorted(cube.head["ck"]) == ["2026-10-07", "2026-10-08", "2026-10-09"]
    assert cube.head["ckq"][0] == "2026-10-10"                      # the day the Stop cut: next
    ga = FakeGA(today=T, stop_after=1, stop_why="calls")            # the app's call cap (raised in the read): the
    assert cu.step_app(ga, cube, T, HS, at(T, 3)) == "fetched"     # check ends, the run goes on
    assert len(cube.head["ck"]) == 4 and cube.head["ckq"][0] == "2026-10-11"
    ga = FakeGA(today=T, max_calls=2)                               # … seen before a read (_room): the same
    cu.step_app(ga, cube, T, HS, at(T, 4))
    assert len(cube.head["ck"]) == 6 and ga.calls == 2


def test_the_checks_time_slice(monkeypatch):
    monkeypatch.setattr(cu, "CK_CALLS", 0)
    cube, _ = _walk(cu.Cube(None, "a~1", "222"), T0, date(2026, 10, 20))
    monkeypatch.setattr(cu, "CK_CALLS", 60)
    T, clock = date(2026, 10, 20), [100.0]

    class Clocked(FakeGA):                                          # 2 s a call, the run's budget far off
        def report_all(self, body, **kw):
            clock[0] += 2.0
            return super().report_all(body, **kw)

    ga = Clocked(today=T)
    ga.clock, ga.t_app, ga.t_end = (lambda: clock[0]), clock[0], clock[0] + 1000
    cu.step_app(ga, cube, T, HS, at(T, 2))
    assert len(cube.head["ck"]) == 3 and ga.calls == 3              # 0, 2, 4 s: then CK_SEC (5) is used up


def test_an_error_ends_the_check_never_the_apps_run(monkeypatch):
    monkeypatch.setattr(cu, "CK_CALLS", 0)
    cube, _ = _walk(cu.Cube(None, "a~1", "222"), T0, date(2026, 10, 18))
    monkeypatch.setattr(cu, "CK_CALLS", 60)
    monkeypatch.setattr(cu, "day_total", lambda ga, D: 1 / 0)
    T = date(2026, 10, 18)
    assert cu.step_app(FakeGA(today=T), cube, T, HS, at(T, 2)) in ("fetched", "fresh")
    assert cube.ck_errors == 1 and "ck" not in cube.head                # the day that failed goes last
    assert cube.head["ckq"] == ["2026-10-08", "2026-10-09", "2026-10-10", "2026-10-11", "2026-10-07"]


def test_a_day_whose_total_always_fails_never_holds_the_others(monkeypatch):
    monkeypatch.setattr(cu, "CK_CALLS", 0)
    cube, _ = _walk(cu.Cube(None, "a~1", "222"), T0, date(2026, 10, 18))
    monkeypatch.setattr(cu, "CK_CALLS", 60)
    real = cu.day_total
    monkeypatch.setattr(cu, "day_total", lambda ga, D: 1 / 0 if D == date(2026, 10, 8) else real(ga, D))
    T = date(2026, 10, 18)
    for h in range(1, 4):
        cu.step_app(FakeGA(today=T), cube, T, HS, at(T, h))
    assert sorted(cube.head["ck"]) == ["2026-10-07", "2026-10-09", "2026-10-10", "2026-10-11"]
    assert cube.head["ckq"] == ["2026-10-08"] and cube.ck_errors >= 1
    _walk(cube, date(2026, 10, 19), date(2026, 10, 21))             # a run a day: each day the newly due one is read
    ck = cube.head["ck"]                                            # before the failing day comes again
    assert {"2026-10-12", "2026-10-13"} <= set(ck) and "2026-10-08" not in ck
    assert cube.head["ckq"] == ["2026-10-14", "2026-10-08"]


def test_check_off_or_refold_off_reads_nothing_and_old_checks_are_ignored(monkeypatch):
    cube = _folded_short()
    T = D11 + timedelta(days=cu.CK_AGE)
    cube.head["ck"][K11] = [full(D11), "2026-10-18T00:00:00Z", 0]
    monkeypatch.setattr(cu, "CK_CALLS", 0)
    assert not cu._cand(cube, D11, cube.ledger(K11))               # the check off: the refold as before it
    ga = FakeGA(today=T)
    cu.step_app(ga, cube, T, HS, at(T))
    assert not cube.head["rf"].get("log") and all(q[0]["dimensions"] != [{"name": "date"}] for q in ga.asked)
    monkeypatch.setattr(cu, "CK_CALLS", 60)
    monkeypatch.setattr(cu, "RF_CALLS", 0)                         # the refold off: no check either
    n = len(cube.head["ck"])
    ga = FakeGA(today=T + timedelta(days=1))
    cu.step_app(ga, cube, T + timedelta(days=1), HS, at(T + timedelta(days=1)))
    assert len(cube.head["ck"]) == n and all(q[0]["dimensions"] != [{"name": "date"}] for q in ga.asked)


def test_a_day_found_while_a_refold_builds_another_copy_waits_for_the_next_queue(monkeypatch):
    """October's refold is building its copy (a few days a run) when the check finds Sep 30 partly short: the queue
    is not made again meanwhile; once October is swapped, September is read again."""
    D = date(2026, 9, 30)
    cube, _ = _walk(cu.Cube(None, "a~1", "222"), date(2026, 10, 2), date(2026, 10, 6),
                    lambda T: CollapseGA(today=T, empty={D}, share=SHARE) if T == D + timedelta(days=cu.FINAL_LAG)
                    else FakeGA(today=T))
    cube.head["rf"].update(k="2026-10", at="2026-10-07T00:00:00Z", c=0, n=0, cand=["2026-10-01"])   # a refold of
    monkeypatch.setattr(cu, "RF_CALLS", 1)                          # October on its way (one day a run)
    T = date(2026, 10, 7)
    cu.step_app(FakeGA(today=T), cube, T, HS, at(T))
    rf = cube.head["rf"]
    assert cube.ps_new == 1 and rf["k"] == "2026-10" and "scan" in rf
    monkeypatch.setattr(cu, "RF_CALLS", 30)
    for h in range(2, 6):
        cu.step_app(FakeGA(today=T), cube, T, HS, at(T, h))
        if not cube.head["rf"].get("k") and cube.month("2026-09").get("rf"):
            break
    assert cube.month("2026-09")["days"][D.isoformat()]["t"] == full(D)
    assert [e[0] for e in cube.head["rf"]["log"]] == ["2026-10", "2026-09"]


def test_users_of_a_day_refolded_are_the_new_reads(tmp_path, monkeypatch):
    import gzip, json
    monkeypatch.setattr(cu, "U_ON", True)
    data = str(tmp_path)
    _folded_short(date(2026, 10, 18), data=data)
    with gzip.open(cu.u_path(data, "a~1", "2026-10"), "rt") as f:
        uc = json.load(f)["c"]
    assert uc[K11]["by"] == "rf" and uc[K11]["u"]["AA"][0] == 80   # its users: the read again's (whole)
    assert uc["2026-10-10"]["by"] == "fold"


def test_files_on_disk_between_runs(tmp_path):
    data = str(tmp_path)
    _folded_short(date(2026, 10, 18), data=data)
    mo = _month(data, "2026-10")
    assert mo["days"][K11]["t"] == full(D11) and mo["rf"]["t1"] == {K11: full(D11)}
    h = cu.load_head(data, "a~1")
    assert h["ck"][K11] == [full(D11), "2026-10-18T00:05:00Z", 1] and h["ckq"] == []
    assert not os.path.exists(cu.Cube(data, "a~1", "222").rf_path("2026-10"))


# ── the log and the settings ─────────────────────────────────────────────────────────
def test_counts_in_the_log_line():
    line = cu.log_line({"counts": {"rf_gave": 1, "checked": 31, "ps_new": 2, "ck_errors": 1, "rf_lower": 3}})
    assert (", refold given up 1, day totals checked 31, partly short 2, check errors 1, refold merged lower 3, "
            "calls 0, tokens 0") in line


def test_settings_and_the_workflow(monkeypatch):
    monkeypatch.delenv("GA4_CUBE_CK_CALLS", raising=False)
    try:
        fresh = importlib.reload(cu)
        assert fresh.CK_CALLS == 10 and fresh.CK_AGE == 7 and fresh.PART == 0.03 and fresh.PS_MIN == USD
        monkeypatch.setenv("GA4_CUBE_CK_CALLS", "0")
        assert importlib.reload(cu).CK_CALLS == 0
    finally:
        monkeypatch.delenv("GA4_CUBE_CK_CALLS", raising=False)
        importlib.reload(cu)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        y = f.read()
    assert "GA4_CUBE_CK_CALLS:    ${{ vars.GA4_CUBE_CK_CALLS }}" in y
