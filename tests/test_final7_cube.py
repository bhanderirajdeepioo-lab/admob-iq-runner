"""GA4_FINAL_DAYS = 7 (admob_iq.ga4_final; owner, 17 Nov 2026: "max to max 7 din me to aa hi jaata he") on the cohort
cube (fetch.ga4_cube) and its Google Ads users' instance, ga4_cohort (+ its paid instance) and ga4_cecpm — copies made
at another F by the final_days fixture, beside the stores at the pin (3: every store as before the knob —
final_days.pin: the session's own, or their copies at 3 in a session the caller runs at another F), offline
with the stores' own fake GA4s and SYNTHETIC values only: every lag derived from the knob (at the pin: each as before);
the cube's hot window of the newest FINAL_LAG days — its HOT_DAYS newest read every REFRESH_HOURS, an older one at
most once a UTC day (the UTC day, never the property's; never a look at a month file at the pin), never one a walk
folded already, a round a Stop cut going on with only its unread days —; a day folded only once it is 7 days old,
from that read (the pin: at 3, short); the deploy (a store the pin folded: its days today − 6 … today − 3 never read
hot again, the walk idle until its cursor's day is 7 days old, its folds untouched); the fold guard holding a
collapsed read at 7 and folding it "lo" at 8, the refold from 9 waiting to RF_MAX (14); the settle check reading only
the folds of a shorter lag (CK_AGE); q reading the day folded at 7 in the fold's run; the paid cube on the same rules;
ga4_cohort's final days read alone ("fa") only from 7 days old (the deploy: the days after it read alone again, then
FINAL_LAG + 1 days a refresh); ga4_cecpm folding at 7, reading its HOT_DAYS newest every REFRESH_HOURS and ages
5 … 6 once a UTC day ("mid": an emptied answer too), no "mid" at the pin."""
import gzip
import json
import os
from datetime import date, timedelta

from admob_iq import ga4_final
from admob_iq.fetch import ga4_cecpm as ce
from admob_iq.fetch import ga4_cohort as gco
from admob_iq.fetch import ga4_cohort_paid as gcp
from admob_iq.fetch import ga4_cube as cu
from admob_iq.fetch import ga4_cube_paid as cp
from admob_iq.fetch import ga4_firstopen as gf
from tests import test_ga4_cecpm as tce
from tests.test_ga4_cohort import _cga
from tests.test_ga4_cube import HS, FakeGA, _days, day_total
from tests.test_ga4_cube_guard import CollapseGA, at

T0 = date(2026, 10, 13)
LATER = date(2027, 1, 1)                                        # every day of 2026 whole in GA4


def ago(T, n):
    return T - timedelta(days=n)


def iso(d):
    return d.isoformat()


def rng(a, b=None):
    return (a.isoformat(), (b or a).isoformat())


def ranges(ga):
    """The activity days each GA4 call asked for, in order: (start, end)."""
    return [(q[0]["dateRanges"][0]["startDate"], q[0]["dateRanges"][0]["endDate"]) for q in ga.asked]


def full(D):
    return day_total(FakeGA(today=LATER), D)


def _quiet(mp, m, **kw):
    """A cube module's switches for a test of its own reads (monkeypatched: the test's only): q, the users, the
    settle check and the repair off; the fold guard and the refold on, as in the build. kw: any of them otherwise."""
    for k, v in {**dict(Q_CALLS=0, U_ON=False, CK_CALLS=0, REPAIR_CALLS=0, GUARD=True, RF_CALLS=30), **kw}.items():
        mp.setattr(m, k, v)


def _save(cube):
    cube.save()
    cube.save_head()


def _month(data, k):
    with gzip.open(cu.month_path(data, "a~1", k), "rt") as f:
        return json.load(f)


def _raw_months(data):
    """Every month file of the made-up app's cube (not its head): {name: bytes}."""
    folder = cu.app_dir(data, "a~1")
    out = {}
    for n in sorted(os.listdir(folder)):
        if n != cu.HOT:
            with open(os.path.join(folder, n), "rb") as f:
                out[n] = f.read()
    return out


class Settling(FakeGA):
    """GA4 still adding to a day for a few days: a read of activity day D made when D is `a` days old holds SHARE[a]
    of what GA4 holds of it for good (made-up shares; whole from 5 days old)."""
    SHARE = (0.5, 0.6, 0.7, 0.8, 0.9)

    def __init__(self, **kw):
        super().__init__(fill=1.0, **kw)

    def rows_of(self, D):
        rows = super().rows_of(D)
        a = (self.today - D).days
        f = self.SHARE[a] if 0 <= a < len(self.SHARE) else 1.0
        for r in rows:
            r["totalAdRevenue"] *= f
        return rows


# ── the lags ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_every_lag_derives_from_the_knob_and_the_pin_keeps_each_as_before(final_days):
    c3, p3, g3, gp3, e3 = final_days.pin(cu, cp, gco, gcp, ce)
    assert (c3.HOT_DAYS, c3.FINAL_LAG, c3.RF_RIPE, c3.RF_MAX, c3.CK_AGE, c3.Q_SETTLE) == (3, 3, 5, 10, 7, 5)
    assert (p3.MOD.HOT_DAYS, p3.MOD.FINAL_LAG, p3.MOD.RF_RIPE, p3.MOD.RF_MAX, p3.MOD.CK_AGE) == (3, 3, 5, 10, 7)
    assert (g3.FINAL_LAG, g3.RECENT_DAYS, gp3.MOD.FINAL_LAG, gp3.MOD.RECENT_DAYS) == (3, 35, 3, 35)
    assert (e3.HOT_DAYS, e3.FINAL_LAG, e3.LOW_WAIT) == (5, 5, 4)
    for n, cube, cecpm in ((7, (7, 9, 14, 7), 7), (10, (10, 12, 17, 10), 10), (14, (14, 16, 21, 14), 14)):
        c, p, g, gp, e = final_days(n, cu, cp, gco, gcp, ce)       # (each producer before what reads it)
        for m in (c, p.MOD):
            assert (m.HOT_DAYS, m.FINAL_LAG, m.RF_RIPE, m.RF_MAX, m.CK_AGE, m.Q_SETTLE) == (3,) + cube + (5,), n
            assert m.FINAL_LAG == ga4_final.lag(m.HOT_DAYS) and m.Q_SETTLE <= m.FINAL_LAG < m.RF_RIPE < m.RF_MAX
            assert m.RF_MAX - m.RF_RIPE == 5 and m.CK_AGE >= m.FINAL_LAG
        for m in (g, gp.MOD):
            assert (m.FINAL_LAG, m.RECENT_DAYS) == (n, 35) and m.RECENT_DAYS >= m.FINAL_LAG + 1
        assert (e.HOT_DAYS, e.FINAL_LAG, e.LOW_WAIT) == (5, cecpm, 4)
        assert c.FINAL_LAG == g.FINAL_LAG == p.MOD.FINAL_LAG       # the cube folds where ga4_cohort turns final
        assert p.MOD is not c and (p.MOD.DIR, gp.MOD.DIR) == ("ga4_cube_paid", "ga4_cohort_paid")   # (their own)


# ── the cube's hot days ─────────────────────────────────────────────────────────────────────────────────────────────
def test_the_hot_window_is_the_newest_7_days_and_an_older_one_is_read_once_a_utc_day(final_days, monkeypatch):
    cu7 = final_days(7, cu)
    _quiet(monkeypatch, cu7)
    cube, T = cu7.Cube(None, "a~1", "222"), T0
    ga = FakeGA(today=T)
    cu7.step_app(ga, cube, T, HS, at(T, 0, 5))                      # the backfill to T − 7; the property day's first
    assert cube.head["next"] == iso(ago(T, 6)) and cube.head["done"]    # round: its 3 newest (the older ones wait for
    assert ranges(ga)[-1] == rng(ago(T, 2), T) and sorted(cube.head["d"]) == [iso(D) for D in _days(ago(T, 2), T)]
    ga = FakeGA(today=T)                                            # the next round), then the 7 in one block
    assert cu7.step_app(ga, cube, T, HS, at(T, 6, 10)) == "fetched" and ranges(ga) == [rng(ago(T, 6), T)]
    for when in (at(T, 12, 10), at(T, 23, 50)):                     # the same UTC day: the 3 newest only
        ga = FakeGA(today=T)
        assert cu7.step_app(ga, cube, T, HS, when) == "fetched" and ranges(ga) == [rng(ago(T, 2), T)]
    got = {k: v["at"] for k, v in cube.head["d"].items()}
    assert got == {**{iso(ago(T, i)): "2026-10-13T06:10:00Z" for i in (6, 5, 4, 3)},
                   **{iso(ago(T, i)): "2026-10-13T23:50:00Z" for i in (2, 1, 0)}}
    T1 = T + timedelta(days=1)                                      # the next day: T − 6 is 7 days old — folded; the
    ga = FakeGA(today=T1)                                           # 3 newest (the property day's first round) …
    cu7.step_app(ga, cube, T1, HS, at(T1, 0, 5))
    assert ranges(ga) == [rng(ago(T, 6)), rng(ago(T1, 2), T1)]
    assert cube.ledger(iso(ago(T, 6)))["at"] == "2026-10-14T00:05:00Z" and iso(ago(T, 6)) not in cube.head["d"]
    assert sorted(cube.head["d"]) == [iso(D) for D in _days(ago(T1, 6), T1)]
    ga = FakeGA(today=T1)                                           # … the next round, the 4 older ones once more too
    cu7.step_app(ga, cube, T1, HS, at(T1, 6, 10))
    assert ranges(ga) == [rng(ago(T1, 6), T1)]
    ga = FakeGA(today=T1)
    cu7.step_app(ga, cube, T1, HS, at(T1, 12, 10))
    assert ranges(ga) == [rng(ago(T1, 2), T1)]


def test_a_hot_round_a_stop_cut_goes_on_with_its_unread_days_never_an_older_one_twice(final_days, monkeypatch):
    """A busy app (its multi-day answers come back with "(other)": each day alone) whose round with the older days the
    app's call cap cuts after three of the four: the next run reads the fourth and the 3 newest — never again the older
    days it read; the block of 3 its first round of the day dropped stands for the 7-day one (no block tried again)."""
    cu7 = final_days(7, cu)
    _quiet(monkeypatch, cu7)
    cube = cu7.Cube(None, "a~1", "222")
    cu7.step_app(FakeGA(today=T0), cube, T0, HS, at(T0, 0, 5))
    cu7.step_app(FakeGA(today=T0), cube, T0, HS, at(T0, 6, 10))
    T = T0 + timedelta(days=1)
    ga = FakeGA(today=T, cap=1000)                                  # the property day's first round: the fold, the
    cu7.step_app(ga, cube, T, HS, at(T, 0, 5))                      # 3 newest' block (dropped), each alone
    assert ranges(ga) == [rng(ago(T, 7)), rng(ago(T, 2), T)] + [rng(ago(T, i)) for i in (2, 1, 0)]
    assert cube.head["heavy"] == {"at": iso(ago(T, 2)), "n": 3}
    ga = FakeGA(today=T, cap=1000, stop_after=3)                    # the next round: the 7 days, each alone at once
    try:
        cu7.step_app(ga, cube, T, HS, at(T, 6, 5))
        raise AssertionError("no Stop")
    except gf.Stop:
        pass
    assert ranges(ga) == [rng(ago(T, i)) for i in (6, 5, 4)]
    assert cube.head["hot_cyc"] == ["2026-10-14T06:05:00Z", "2026-10-14"]
    ga = FakeGA(today=T, cap=1000)                                  # an hour on: the round goes on
    cu7.step_app(ga, cube, T, HS, at(T, 7, 5))
    assert ranges(ga) == [rng(ago(T, i)) for i in (3, 2, 1, 0)]
    assert "hot_cyc" not in cube.head and cube.head["hot_at"] == "2026-10-14T07:05:00Z"
    assert {k: v["at"][11:16] for k, v in cube.head["d"].items()} == {
        **{iso(ago(T, i)): "06:05" for i in (6, 5, 4)}, **{iso(ago(T, i)): "07:05" for i in (3, 2, 1, 0)}}


def test_a_busy_apps_heavy_memory_serves_both_hot_round_starts_one_block_try_a_keep(final_days, monkeypatch):
    """A busy app at 7 (its multi-day answers come back with "(other)"), a run every 6 hours: the hot rounds start at
    the 3 newest days or — once a UTC day — at the 7 not final; one heavy memory serves both, so its block is tried
    again once per HEAVY_KEEP days (as at the pin), never twice a day (each start dropping the other's memory)."""
    cu7 = final_days(7, cu)
    _quiet(monkeypatch, cu7)
    monkeypatch.setattr(cu7, "HEAVY_KEEP", 10)
    cube = cu7.Cube(None, "a~1", "222")
    cu7.step_app(FakeGA(today=T0, cap=1000), cube, T0, HS, at(T0, 0, 5))
    tries = {}                                                      # UTC day → its block calls (a multi-day range)
    for i in range(1, 31):
        T = T0 + timedelta(days=i)
        for h in (0, 6, 12, 18):
            ga = FakeGA(today=T, cap=1000)
            cu7.step_app(ga, cube, T, HS, at(T, h, 5))
            tries[i] = tries.get(i, 0) + sum(1 for a, b in ranges(ga) if a != b)
    assert sum(tries.values()) <= 4 and max(tries.values()) == 1, tries      # once a HEAVY_KEEP (10) days


def test_hot_due_the_utc_day_a_folded_day_and_no_month_look_at_the_pin(final_days):
    cu3 = final_days.pin(cu)
    cu7 = final_days(7, cu)
    T, now = T0, "2026-10-13T06:10:00Z"
    cube, looks = cu7.Cube(None, "a~1", "222"), []
    cube.ledger = lambda k: looks.append(k)                         # (None: not folded)
    assert all(cu7._hot_due(cube, ago(T, i), T, now) for i in (0, 1, 2)) and looks == []   # the newest: no look
    assert not any(cu7._hot_due(cube, ago(T, i), T, now) for i in (3, 4, 5, 6))   # the property day's first round:
    cube.head["hot_today"] = iso(ago(T, 1))                         # (none yet, or the day before) never an older
    assert not cu7._hot_due(cube, ago(T, 3), T, now) and looks == []                         # one — no look either
    cube.head["hot_today"] = iso(T)                                 # a later round of the day
    assert cu7._hot_due(cube, ago(T, 3), T, now) and looks == [iso(ago(T, 3))]              # never read: due
    d = cube.head["d"]
    d[iso(ago(T, 4))] = {"at": "2026-10-13T00:05:00Z"}              # read on this UTC day: not again (no look)
    d[iso(ago(T, 5))] = {"at": "2026-10-12T23:59:59Z"}              # read the UTC day before: due
    assert not cu7._hot_due(cube, ago(T, 4), T, now) and cu7._hot_due(cube, ago(T, 5), T, now)
    assert looks == [iso(ago(T, 3)), iso(ago(T, 5))]
    cube.ledger = lambda k: {"t": 1}                                # folded under a shorter lag: never hot again
    assert not cu7._hot_due(cube, ago(T, 5), T, now) and not cu7._hot_due(cube, ago(T, 6), T, now)
    late = cu7.Cube(None, "a~1", "222")                             # a property ahead of UTC (its day began at 18:30
    late.ledger = lambda k: None                                    # UTC): the UTC day decides, never the property's
    late.head["d"], late.head["hot_today"] = {iso(ago(T, 3)): {"at": "2026-10-13T01:00:00Z"}}, iso(T)
    assert not cu7._hot_due(late, ago(T, 3), T, "2026-10-13T19:00:00Z")
    assert cu7._hot_due(late, ago(T, 3), T, "2026-10-14T00:05:00Z")
    pin, looks3 = cu3.Cube(None, "a~1", "222"), []                  # the pin: every hot day is one of the newest
    pin.ledger = lambda k: looks3.append(k)
    assert all(cu3._hot_due(pin, ago(T, i), T, now) for i in range(cu3.FINAL_LAG)) and looks3 == []


def test_a_day_folds_once_7_days_old_from_that_read_the_pin_folds_it_short_at_3(final_days, monkeypatch):
    cu3 = final_days.pin(cu)
    cu7 = final_days(7, cu)
    _quiet(monkeypatch, cu7)
    _quiet(monkeypatch, cu3)
    D, whole = T0, full(T0)
    cube, pin, seen = cu7.Cube(None, "a~1", "222"), cu3.Cube(None, "a~1", "222"), []
    for i in range(8):
        T = D + timedelta(days=i)
        for h, m in ((0, 5), (12, 0)):
            cu7.step_app(Settling(today=T), cube, T, HS, at(T, h, m))
            if i < 4:
                cu3.step_app(Settling(today=T), pin, T, HS, at(T, h, m))
        hot = cube.head["d"].get(iso(D))
        seen.append(None if hot is None else (round(hot["t"] / whole, 3), hot["at"][11:16]))
        assert (cube.ledger(iso(D)) is None) == (i < 7)
    assert seen == [(0.5, "12:00"), (0.6, "12:00"), (0.7, "12:00"),            # the 3 newest: every round
                    (0.8, "12:00"), (0.9, "12:00"), (1.0, "12:00"), (1.0, "12:00"),   # older: once a UTC day, never
                    None]                                                       # in the property day's first round;
    #                                                                             7 days old: folded
    led = cube.ledger(iso(D))
    assert led["t"] == whole and led["at"] == "2026-10-20T00:05:00Z"           # whole, from the read made at D + 7
    assert pin.ledger(iso(D))["t"] < 0.85 * whole                              # the pin: folded at D + 3, short


# ── the deploy: a store the pin folded ──────────────────────────────────────────────────────────────────────────────
def test_the_deploy_a_store_folded_at_3_goes_on_at_7_and_never_reads_a_folded_day_hot(final_days, monkeypatch,
                                                                                         tmp_path):
    data = str(tmp_path)
    cu3 = final_days.pin(cu)
    _quiet(monkeypatch, cu3)
    for T in (ago(T0, 2), ago(T0, 1), T0):                          # the build before the knob (the pin)
        cube = cu3.Cube(data, "a~1", "222")
        cu3.step_app(FakeGA(today=T), cube, T, HS, at(T, 0, 5))
        _save(cube)
    head = cu3.load_head(data, "a~1")
    assert head["next"] == iso(ago(T0, 2)) and sorted(head["d"]) == [iso(ago(T0, i)) for i in (2, 1, 0)]
    before, oct0 = _raw_months(data), _month(data, "2026-10")["days"]
    cu7 = final_days(7, cu)
    _quiet(monkeypatch, cu7)
    cube = cu7.Cube(data, "a~1", "222")                             # the deploy: 6 hours on, the same property day
    ga = FakeGA(today=T0)
    assert cu7.step_app(ga, cube, T0, HS, at(T0, 6, 10)) == "fetched"
    _save(cube)
    assert ranges(ga) == [rng(ago(T0, 2), T0)]                      # T0 − 6 … T0 − 3 (folded at D + 3): never hot
    assert sorted(cube.head["d"]) == [iso(ago(T0, i)) for i in (2, 1, 0)] and cube.head["done"]
    assert _raw_months(data) == before
    for i in range(1, 6):
        T = T0 + timedelta(days=i)
        cube = cu7.Cube(data, "a~1", "222")
        ga = FakeGA(today=T)                                        # the property day's first round: the 3 newest
        cu7.step_app(ga, cube, T, HS, at(T, 0, 5))
        _save(cube)
        first = max(ago(T, 6), ago(T0, 2))                          # no hot copy of a folded day, ever
        assert sorted(cube.head["d"]) == [iso(D) for D in _days(first, T)], i
        if i < 5:                                                   # nothing 7 days old after the cursor: idle
            assert cube.folded == 0 and cube.head["next"] == iso(ago(T0, 2)) and ranges(ga) == [rng(ago(T, 2), T)]
            assert _raw_months(data) == before
            cube = cu7.Cube(data, "a~1", "222")                     # the next round: the older ones not folded too
            ga = FakeGA(today=T)
            cu7.step_app(ga, cube, T, HS, at(T, 6, 10))
            _save(cube)
            assert ranges(ga) == [rng(first, T)] and _raw_months(data) == before, i
    assert ranges(ga) == [rng(ago(T0, 2)), rng(ago(T, 2), T)]      # day 5: T0 − 2 is 7 days old — folded
    assert cube.folded == 1 and cube.head["next"] == iso(ago(T0, 1))
    oct1 = _month(data, "2026-10")["days"]
    assert oct1[iso(ago(T0, 2))]["at"] == "2026-10-18T00:05:00Z" and oct1[iso(ago(T0, 2))]["t"] == full(ago(T0, 2))
    assert {D: v for D, v in oct1.items() if D in oct0} == oct0     # the folds made before: as they were
    assert {n: b for n, b in _raw_months(data).items() if not n.startswith("2026-10")} == \
        {n: b for n, b in before.items() if not n.startswith("2026-10")}


# ── the fold guard, the refold, the settle check, q ─────────────────────────────────────────────────────────────────
def test_the_guard_holds_a_collapsed_read_at_7_folds_it_lo_at_8_and_the_refold_waits_from_9_to_14(final_days,
                                                                                                  monkeypatch):
    cu7 = final_days(7, cu)
    _quiet(monkeypatch, cu7)
    D = date(2026, 10, 11)
    cube = cu7.Cube(None, "a~1", "222")
    for T in _days(T0, D + timedelta(days=6)):                      # D hot: its peak from those reads (two rounds a
        for h in (0, 6):                                            # day: an older day is read in the second)
            cu7.step_app(FakeGA(today=T), cube, T, HS, at(T, h, 5))
    p = cube.head["pk"][iso(D)]
    assert p == full(D)
    T = D + timedelta(days=7)                                       # 7 days old, GA4 answers it almost empty: held
    cu7.step_app(CollapseGA(today=T, empty={D}), cube, T, HS, at(T, 0, 5))
    assert cube.head["hold"][0] == iso(D) and cube.head["next"] == iso(D) and cube.ledger(iso(D)) is None
    T = D + timedelta(days=8)                                       # FINAL_LAG + HOLD_DAYS: folded as it is, "lo"
    cu7.step_app(CollapseGA(today=T, empty={D}), cube, T, HS, at(T, 0, 5))
    led = cube.ledger(iso(D))
    assert led["lo"] == p and led["t"] < cu7.COLLAPSE * p and "hold" not in cube.head
    assert cube.head["next"] == iso(D + timedelta(days=2)) and not cube.head["rf"].get("k")     # not ripe yet
    for i in range(9, 14):                                          # RF_RIPE on: October read again, D first — still
        T = D + timedelta(days=i)                                   # collapsed: the month waits (never merged so)
        cu7.step_app(CollapseGA(today=T, empty={D}), cube, T, HS, at(T, 0, 5))
        rf = cube.head["rf"]
        assert rf["k"] == "2026-10" and rf["wait"] == [iso(D), "2026-10-20T00:05:00Z"] and cube.refolded == 0, i
    T = D + timedelta(days=14)                                      # RF_MAX: merged as GA4 keeps it
    cu7.step_app(CollapseGA(today=T, empty={D}), cube, T, HS, at(T, 0, 5))
    led = cube.ledger(iso(D))
    assert cube.refolded == 1 and not cube.head["rf"].get("k") and "lo" not in led and led["t"] < 0.01 * full(D)
    assert cube.month("2026-10")["rf"]["t1"] == {iso(D): led["t"]} and not cu7._cand(cube, D, led)


def test_the_settle_check_reads_only_the_folds_of_a_shorter_lag(final_days, monkeypatch, tmp_path):
    data = str(tmp_path)
    cu3 = final_days.pin(cu)
    _quiet(monkeypatch, cu3)
    for T in _days(T0, date(2026, 10, 17)):                         # the pin: the backfill, then a fold at D + 3 a day
        cube = cu3.Cube(data, "a~1", "222")
        cu3.step_app(FakeGA(today=T), cube, T, HS, at(T, 0, 5))
        _save(cube)
    cu7 = final_days(7, cu)
    _quiet(monkeypatch, cu7, CK_CALLS=60)
    for T in _days(date(2026, 10, 18), date(2026, 10, 28)):         # F = 7 from Oct 18: its folds from Oct 22 on
        cube = cu7.Cube(data, "a~1", "222")
        cu7.step_app(FakeGA(today=T), cube, T, HS, at(T, 0, 5))
        _save(cube)
    ck = cu7.load_head(data, "a~1")["ck"]
    assert sorted(ck) == [iso(D) for D in _days(date(2026, 10, 7), date(2026, 10, 14))]    # read under 7 days old
    assert all(v[0] == full(date.fromisoformat(D)) and v[2] == 0 for D, v in ck.items())  # once each, nothing short
    assert cube.ledger("2026-10-21")["at"] == "2026-10-28T00:05:00Z"   # a fold at 7: never checked


def test_q_reads_the_day_folded_at_7_in_the_folds_run(final_days, monkeypatch):
    cu7 = final_days(7, cu)
    _quiet(monkeypatch, cu7, Q_CALLS=120)
    hs = ago(T0, 10)
    cube = cu7.Cube(None, "a~1", "222")
    for T in (T0, T0 + timedelta(days=1)):
        cu7.step_app(FakeGA(today=T, start=hs), cube, T, hs, at(T, 0, 5))
    D = ago(T0, 6)                                                  # folded on T0 + 1, 7 days old: settled (Q_SETTLE)
    q = cube.qmonth("2026-10")["days"][iso(D)]
    assert q["qs"] == "ok" and q["at"] == "2026-10-14T00:05:00Z" and not cube.head["qh"].get("p")


def test_the_paid_cube_runs_on_the_same_knob(final_days, monkeypatch):
    m = final_days(7, cp).MOD
    assert (m.HOT_DAYS, m.FINAL_LAG, m.RF_RIPE, m.RF_MAX, m.CK_AGE, m.DIR) == (3, 7, 9, 14, 7, "ga4_cube_paid")
    _quiet(monkeypatch, m)
    cube = m.Cube(None, "a~1", "222")
    ga = FakeGA(today=T0)
    m.step_app(ga, cube, T0, HS, at(T0, 0, 5))
    assert cube.head["next"] == iso(ago(T0, 6)) and sorted(cube.head["d"]) == [iso(D) for D in _days(ago(T0, 2), T0)]
    for when, first in ((at(T0, 6, 10), 6), (at(T0, 12, 10), 2)):  # the older days in the next round, once that day
        ga = FakeGA(today=T0)
        m.step_app(ga, cube, T0, HS, when)
        assert ranges(ga) == [rng(ago(T0, first), T0)]
    assert sorted(cube.head["d"]) == [iso(D) for D in _days(ago(T0, 6), T0)]


# ── ga4_cohort ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_cohort_final_days_read_alone_only_from_7_days_old_and_the_deploy(final_days):
    """A heavy app (its refresh block comes back with "(other)": its days read alone, the final ones noted "fa"): the
    pin notes them from 3 days old; at F = 7 the deploy's refresh keeps only those 7 days old or more and reads the
    days after them alone again; from then on a refresh reads FINAL_LAG + 1 days — the day turning final noted."""
    hs = date(2026, 6, 1)
    gc3 = final_days.pin(gco)
    store = {"v": gc3.STORE_V, "backfill": {"done": True}, "chk": {"v": gc3.CHK_V, "done": True}}
    gc3.step_app(_cga(today=T0, cap=1000), store, T0, hs, at(T0, 6))                # the pin
    recent = ago(T0, gc3.RECENT_DAYS - 1)
    assert sorted(store["fa"]) == [iso(D) for D in _days(recent, ago(T0, 3))]
    gc7 = final_days(7, gco)
    for i in (1, 2):
        T = T0 + timedelta(days=i)
        ga = _cga(today=T, cap=1000)
        gc7.step_app(ga, store, T, hs, at(T, 6))
        asked = [a for a, b in ranges(ga)]
        assert all(a == b for a, b in ranges(ga)), i                # each day alone (the block dropped lately)
        if i == 1:                                                  # T0 − 5 … T0 − 3 noted at the pin: read again
            assert asked == [iso(D) for D in _days(ago(T0, 5), T)] and max(store["fa"]) == iso(ago(T0, 6))
        else:                                                       # the day turning final + the 7 not final
            assert asked == [iso(D) for D in _days(ago(T, 7), T)] and len(asked) == gc7.FINAL_LAG + 1
            assert max(store["fa"]) == iso(ago(T, 7))
        assert min(store["fa"]) == iso(ago(T, gc7.RECENT_DAYS - 1))


# ── ga4_cecpm ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _ce_run(m, ga, data, today, now):
    st = m.Store(data, tce.AID, tce.SID)
    try:
        m.step_app(ga, st, today, tce.HS, now)
    except gf.Stop:
        pass
    st.save()
    st.head.update(app_id=tce.AID, stream_id=tce.SID)
    st.save_head()
    return st


def _ce_head(m, data):
    return m.gu.load_store(m.head_path(data, tce.AID))


def test_cecpm_folds_at_7_its_5_newest_every_round_ages_5_and_6_once_a_utc_day(final_days, monkeypatch, tmp_path):
    ce3 = final_days.pin(ce)
    ce7 = final_days(7, ce)
    monkeypatch.setattr(ce7, "TOT_MIN", 100)                        # (the fake app's 900 events a day: judged)
    data, T, now = str(tmp_path / "f7"), tce.TODAY, tce.NOW         # (06:00 UTC, a UTC property)
    ga = tce.FakeGA()
    _ce_run(ce7, ga, data, T, now)
    hot = [ago(T, i) for i in range(6, -1, -1)]
    assert ga.asked[:8] == [ago(T, 7)] + hot                        # the edge (7 days old), the 7 hot days (then
    #                                                                 the backfill)
    h = _ce_head(ce7, data)
    assert h["upto"] == iso(ago(T, 7)) and sorted(h["hot"]) == [iso(D) for D in hot]
    assert h["mid"] == {iso(ago(T, 6)): "2026-10-15T06:00:00Z", iso(ago(T, 5)): "2026-10-15T06:00:00Z"}
    ga = tce.FakeGA()                                               # 7 hours on, the same UTC day: the 5 newest
    _ce_run(ce7, ga, data, T, now + timedelta(hours=7))
    assert ga.asked == [ago(T, i) for i in range(4, -1, -1)]
    T1 = T + timedelta(days=1)                                      # the next day: T − 6 folded at 7; ages 5 … 6 once
    ga = tce.FakeGA(scale={ago(T, 4): 0.005})                       # — T − 4 (5 days old) answered emptied
    _ce_run(ce7, ga, data, T1, now + timedelta(days=1))
    assert ga.asked == [ago(T, 6)] + [ago(T1, i) for i in range(6, -1, -1)]
    h = _ce_head(ce7, data)
    assert h["upto"] == iso(ago(T, 6)) and iso(ago(T, 6)) in tce.month(data, "2026-10")["days"]
    assert h["mid"] == {iso(ago(T, 5)): "2026-10-16T06:00:00Z", iso(ago(T, 4)): "2026-10-16T06:00:00Z"}
    emptied = h["hot"][iso(ago(T, 4))]                              # its fuller copy stays (read the day before)
    assert ce7._day_events(emptied) == 900 and emptied["at"] == "2026-10-15T13:00:00Z"
    ga = tce.FakeGA()                                               # 7 hours on: the 5 newest only — the emptied day
    _ce_run(ce7, ga, data, T1, now + timedelta(days=1, hours=7))    # too waits for the next UTC day ("mid")
    assert ga.asked == [ago(T1, i) for i in range(4, -1, -1)]
    pin = str(tmp_path / "pin")                                     # the pin: the 5 newest every round, no "mid"
    for when, day in ((now, T), (now + timedelta(days=1), T1)):
        ga = tce.FakeGA()
        _ce_run(ce3, ga, pin, day, when)
        assert "mid" not in _ce_head(ce3, pin) and len(_ce_head(ce3, pin)["hot"]) == ce3.FINAL_LAG == 5
