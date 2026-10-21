"""ROI 🌍 country rows, the speed path (roi_build._cty: each day's k read once per country, the 30-day walk once per
install day for every country, the zero row made once a day, an app's packs compressed side by side) — byte-identical
to the one-cell-at-a-time path, on the synthetic cube / AdMob / Google Ads world of tests/test_roi_build.py. All data
is synthetic."""

import gzip
import os
import random
from datetime import date, timedelta

import pytest

from admob_iq import roi_build as rb
from admob_iq.fetch import ga4_cohort as gco
from tests.test_roi_build import CHS, CINST, CRATE, CTODAY, _cc_run, _cc_world, _pack_rows


def _old_m(late, B, base, X):
    """The pre-change _cohorts lines for a row's 30-day columns (verbatim): → (m, mf, qo)."""
    m, mf, qo = None, 0, 0
    vals, cum, j = [], base, 1
    while late["full"](X + timedelta(days=rb.LATE_STEP * j + 1), X + timedelta(days=rb.LATE_STEP * (j + 1))):
        cum += B.get(j, 0.0)
        vals.append(rb._r(cum))
        j += 1
    if vals:
        m = vals
        while mf < len(m) and late["fin"](X + timedelta(days=gco.LAGS), X + timedelta(days=rb.LATE_STEP * (mf + 2))):
            mf += 1
        qo = late["q"](X + timedelta(days=gco.LAGS), X + timedelta(days=rb.LATE_STEP * (len(m) + 1)), len(m))
    return m, mf, qo


def _new_m(walk, late, B, base, X):
    """The same lines after the change (_cohorts: the walk, then the sums)."""
    m, mf, qo = None, 0, 0
    nj, wf, wq = walk(late, X)
    vals, cum = [], base
    for j in range(1, nj + 1):
        cum += B.get(j, 0.0)
        vals.append(rb._r(cum))
    if vals:
        m, mf, qo = vals, wf, wq
    return m, mf, qo


def _slow(monkeypatch):
    """The reference path: k looked up per cell (no "kd"), the walk per row (no memo), the zero row made anew each
    time, the packs written one by one."""
    orig = rb._cohorts

    def cohorts(P, spend, fxf, co, today, late=None, edge=None):
        P = dict(P, sc={k: v for k, v in P["sc"].items() if k != "kd"})
        if late is not None:
            late = {k: v for k, v in late.items() if k != "walk"}
        return orig(P, spend, fxf, co, today, late, edge=edge)
    monkeypatch.setattr(rb, "_cohorts", cohorts)
    monkeypatch.setattr(rb, "_zrows", lambda thru, fthru, billed: (
        lambda X, u, cc: (dict(rb._zrow(X, thru, fthru, u, cc, billed), z=1),
                          rb._row_out(rb._zrow(X, thru, fthru, u, cc, billed)))))
    monkeypatch.setattr(rb, "PACK_THREADS", 1)


def _files(od):
    return {n: open(os.path.join(str(od), n), "rb").read() for n in sorted(os.listdir(str(od)))}


WORLDS = {
    "plain": {},
    "zero_rows": {"inst": dict(CINST, EE=3), "rate": dict(CRATE, EE=50000),
                  "only": {"EE": {date(2026, 9, 5), date(2026, 9, 6)}}},
    "hole": {"holes": {date(2026, 10, 1)}},
    "loss": {"loss": {date(2026, 9, 20): 500000}, "flags": {date(2026, 9, 25)}},
    "gaps": {"only": {"--": {date(2026, 9, 5), date(2026, 9, 6), date(2026, 10, 2)}, "CC": {date(2026, 8, 20)}}},
    "months": {"kmul": {"AA": {"2026-08": 0.5}, "CC": {"2026-09": 2.0, "2026-10": 4.0}}, "mask_off": ("2026-09",)},
}


@pytest.mark.parametrize("world", sorted(WORLDS))
@pytest.mark.parametrize("pack_max", [rb.PACK_MAX, 20_000])
def test_country_packs_byte_identical_to_the_cell_by_cell_path(tmp_path, monkeypatch, world, pack_max):
    monkeypatch.setattr(rb, "PACK_MAX", pack_max)                    # small packs: several per app (side by side)
    kw = WORLDS[world]
    calls = {"walk": 0, "zrow": 0}
    walk0, zrow0 = rb._walk, rb._zrow

    def walk(*a):
        calls["walk"] += 1
        return walk0(*a)

    def zrow(*a, **k):
        calls["zrow"] += 1
        return zrow0(*a, **k)
    monkeypatch.setattr(rb, "_walk", walk)
    monkeypatch.setattr(rb, "_zrow", zrow)
    data, P, pre, spend, acc = _cc_world(tmp_path / "w", **kw)
    cd, od, rows = _cc_run(tmp_path, data, P, pre, spend, acc, out="fast")
    fast = dict(calls)
    calls.update(walk=0, zrow=0)
    with monkeypatch.context() as m:
        _slow(m)
        acc2 = rb.start(cube=True, cmon=acc.cmon)
        cd2, od2, rows2 = _cc_run(tmp_path, data, P, pre, spend, acc2, out="slow")
    assert cd is not None and cd == cd2 and rows == rows2
    a, b = _files(od), _files(od2)
    assert a == b and len(a) == len(cd["packs"]) and (len(a) > 1 or pack_max == rb.PACK_MAX)
    assert acc.packs == acc2.packs and dict(acc.cdn) == dict(acc2.cdn)
    _pack_rows(od, cd)                                                # every pack well-formed (the page's checks)
    # the speed path really ran: one walk per install day (not per country × day), one zero row per kind of day
    assert 0 < fast["walk"] < calls["walk"] and fast["zrow"] < calls["zrow"]


def test_the_30_day_walk_equals_the_old_lines_on_every_install_day(tmp_path):
    rnd, seen = random.Random(5), 0
    for i, kw in enumerate(({}, {"holes": {date(2026, 9, 1)}, "loss": {date(2026, 9, 2): 7}})):
        data, P, pre, spend, acc = _cc_world(tmp_path / str(i), **kw)
        cv = rb._Cty(P["hs"])
        late = rb._late(str(data), "a~1", "222", P, visit=cv.visit)
        memo = rb._walk_memo()
        X = CHS - timedelta(days=40)
        while X <= CTODAY + timedelta(days=5):
            for _ in range(3):
                B = {j: rnd.choice([0.0, 0.1, 1e-9, 12.3456789]) for j in range(1, 9) if rnd.random() < 0.7}
                base = rnd.choice([0.0, 1.23456, 1e6 / 3])
                old = _old_m(late, B, base, X)
                assert _new_m(rb._walk, late, B, base, X) == old
                assert _new_m(memo, late, B, base, X) == old
                seen += old[0] is not None
            X += timedelta(days=1)
    assert seen > 100                                                 # columns past D30 on many install days


def test_k_per_day_list_equals_the_lookup_per_cell(tmp_path):
    """_cohorts with P["sc"]["kd"] (the build's 🌍 path) == without it (kf per cell), the k changing month to month."""
    data, P, pre, spend, acc = _cc_world(tmp_path)
    hs, thru = CHS, CTODAY
    ks = {(2026, 8): 1.1, (2026, 9): 0.7, (2026, 10): 2.5}

    def kf(d):
        return (ks.get((d.year, d.month), 1.9), "ok", False, 0.0)
    days = [hs + timedelta(days=i) for i in range((thru - hs).days + 1)]
    rnd = random.Random(9)
    x = {X.isoformat(): {"r": [rnd.randrange(0, 90000) for _ in range(rnd.randrange(0, 33))],
                         "u": [rnd.randrange(0, 9) for _ in range(rnd.randrange(1, 33))]} for X in days if rnd.random() < .8}
    P1 = {"pre": P["pre"], "sc": {"kf": kf}, "xs": {}, "S": P["S"], "hs": hs}
    P2 = dict(P1, sc={"kf": kf, "kd": [kf(D)[0] for D in days]})
    P3 = dict(P1, sc={"kf": kf, "kd": [kf(D)[0] for D in days[:40]]})   # too short: the lookup per cell for the rest
    co = {"read_today": thru.isoformat(), "x": x}
    a = rb._cohorts(P1, None, lambda d_: 1.0, co, thru, None, edge=thru - timedelta(days=3))
    assert a == rb._cohorts(P2, None, lambda d_: 1.0, co, thru, None, edge=thru - timedelta(days=3))
    assert a == rb._cohorts(P3, None, lambda d_: 1.0, co, thru, None, edge=thru - timedelta(days=3))
    assert sum(1 for r in a if r["d"]) > 40


def test_packs_side_by_side_same_bytes_and_every_write_ends_before_a_failure(tmp_path, monkeypatch):
    rnd = random.Random(1)
    jobs = [(str(tmp_path / ("p%02d.json.gz" % i)), bytes(rnd.randrange(32, 127) for _ in range(rnd.randrange(1, 300000))))
            for i in range(9)]
    monkeypatch.setattr(rb, "PACK_THREADS", 1)
    rb._write_packs(jobs)
    one = _files(tmp_path)
    for p, _ in jobs:
        os.remove(p)
    monkeypatch.setattr(rb, "PACK_THREADS", 4)
    rb._write_packs(jobs)
    assert _files(tmp_path) == one and all(gzip.decompress(one[os.path.basename(p)]) == raw for p, raw in jobs)
    rb._write_packs(jobs)                                             # unchanged: nothing rewritten, the same bytes
    assert _files(tmp_path) == one
    bad = tmp_path / "sub"
    bad.mkdir()
    (bad / "x.json.gz").mkdir()                                       # a directory where a pack goes: its write fails
    for p, _ in jobs:
        os.remove(p)
    jobs2 = jobs[:3] + [(str(bad / "x.json.gz"), b"{}")] + jobs[3:]
    with pytest.raises(OSError):
        rb._write_packs(jobs2)
    assert all(os.path.exists(p) for p, _ in jobs)                    # every other pack still written


def test_zero_row_once_a_day_equals_a_fresh_one_for_every_kind_of_country():
    """_zrows: "Unknown country" ("--", no spend), "Not split" ("XX", spend only) and any other country each get their
    own row of a day, asked in any order; a use's copy changed never reaches the next one."""
    thru, fthru, rnd = CTODAY, date(2026, 10, 10), random.Random(3)
    for billed in (True, False):
        z = rb._zrows(thru, fthru, billed)
        for _ in range(4000):
            X = CHS + timedelta(days=rnd.randrange(0, (thru - CHS).days + 1))
            u, cc = rnd.random() < 0.3, rnd.choice(["--", "XX", "AA", "BB", "ZZ"])
            r, ro = z(X, u, cc)
            fresh = rb._zrow(X, thru, fthru, u, cc, billed)
            assert r == dict(fresh, z=1) and ro == rb._row_out(fresh)
            c = dict(r)
            c["st"], c["sp"] = "Watch", 99.0                       # what a use may do to its own copy
