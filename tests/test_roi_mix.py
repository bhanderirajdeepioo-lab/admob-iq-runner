"""📊 Revenue by install month (roi_build._late mix, _mix, app_step, finish): each calendar month's revenue split by the
install month of the users who earned it. All data synthetic (the country world of tests/test_roi_build.py: every
install day X of a country earns CRATE[cc] micros on every activity day D ≥ X, k = 1.2)."""
import gzip
import json
import os
from datetime import date, timedelta

import pytest

from admob_iq import roi_build as rb
from tests.test_roi_build import CHS, CRATE, CTODAY, _cc_world, _stub_app

K = 1.2


def _truth(thru, covered=(), ages=range(10 ** 6)):
    """{activity month: {install month: USD}} of the made-up cube through `thru`: every country, every X ≤ D, the
    ages asked for, an install day in `covered` only past age 30 (its ages 0 … 30 come from the install-day read)."""
    out, D = {}, CHS
    while D <= thru:
        X = CHS
        while X <= D:
            L = (D - X).days
            if L in ages and not (L <= 30 and X.isoformat() in covered):
                e = out.setdefault(D.isoformat()[:7], {})
                C = X.isoformat()[:7]
                e[C] = e.get(C, 0.0) + sum(CRATE.values()) / 1e6 * K
            X += timedelta(days=1)
        D += timedelta(days=1)
    return out


def _sum(*parts):
    out = {}
    for p in parts:
        for M, cs in p.items():
            for C, v in cs.items():
                out.setdefault(M, {})[C] = out.get(M, {}).get(C, 0.0) + v
    return out


def _em_by_month(em):
    return _sum(*({M: {X[:7]: v}} for X, ms in em.items() for M, v in ms.items()))


def _close(a, b, tol=1e-6):
    assert sorted(a) == sorted(b)
    for M in a:
        assert sorted(a[M]) == sorted(b[M]), M
        for C in a[M]:
            assert a[M][C] == pytest.approx(b[M][C], rel=1e-9, abs=tol), (M, C)


def test_late_splits_every_cell_by_activity_month_and_install_month(tmp_path):
    data, P, _, _, _ = _cc_world(tmp_path)
    P["sc"]["kf"] = lambda d_: (K, "ok", False, K)
    late = rb._late(str(data), "a~1", "222", P, mix=set())
    thru = date.fromisoformat(late["info"]["thru"])
    assert thru == CTODAY                                            # folded through Oct 10, hot Oct 11 … 13
    _close(late["BM"], _truth(thru, ages=range(31, 10 ** 6)))       # ages 31 +: the 30-day buckets (+ the hot days)
    _close(_em_by_month(late["EM"]), _truth(thru, ages=range(31)))  # ages 0 … 30: the day cells (+ the hot days)
    # an install day the install-day read has: none of its ages 0 … 30 from the cube (no double count)
    cov = {(CHS + timedelta(days=i)).isoformat() for i in range(0, 40, 3)}
    late2 = rb._late(str(data), "a~1", "222", P, mix=cov)
    assert not set(late2["EM"]) & cov and late2["BM"] == late["BM"]
    # without mix: no mix keys, every other byte the same
    plain = rb._late(str(data), "a~1", "222", P)
    assert "BM" not in plain and "EM" not in plain and plain["B"] == late["B"] and plain["info"] == late["info"]


def test_a_hole_in_the_walk_stops_the_split_at_the_last_whole_month_before_it(tmp_path):
    """A day never folded with folded days after it (thru stops at the hole): a month file's 30-day buckets are by
    week, never cut at a day — the split ends with the month before thru's, every cell after it left out."""
    hole = CTODAY - timedelta(days=4)
    data, P, _, _, _ = _cc_world(tmp_path, holes=(hole,))
    late = rb._late(str(data), "a~1", "222", P, mix=set())
    assert late["info"]["thru"] == (hole - timedelta(days=1)).isoformat() and late["MT"] == "2026-09-30"
    _close(_sum(late["BM"], _em_by_month(late["EM"])), _truth(date(2026, 9, 30)))
    ok, _, _, _, _ = _cc_world(tmp_path / "whole")                    # no hole: through the walk's last day
    assert rb._late(str(ok), "a~1", "222", P, mix=set())["MT"] == CTODAY.isoformat()
    first, _, _, _, _ = _cc_world(tmp_path / "first", holes=(date(2026, 10, 1),))   # a hole on the 1st: September is
    late = rb._late(str(first), "a~1", "222", P, mix=set())                        # whole — kept
    assert late["MT"] == "2026-09-30"
    _close(_sum(late["BM"], _em_by_month(late["EM"])), _truth(date(2026, 9, 30)))


def test_mix_joins_the_install_day_read_the_cube_and_admob():
    till = "2026-10-12"
    rows = [{"X": date(2026, 9, 29), "d": [1.0, 1.5, 3.0, 3.5, 5.0]},     # Sep 29 … Oct 3: steps 1, .5, 1.5, .5, 1.5
            {"X": date(2026, 10, 12), "d": [2.0, 9.0]},                   # Oct 13 is after till: not taken
            {"X": date(2026, 10, 1), "d": None}]                          # no install-day read: from the cube's EM
    late = {"MT": till, "BM": {"2026-10": {"2026-08": 7.0}},
            "EM": {"2026-10-01": {"2026-10": 4.0}, "2026-09-30": {"2026-09": 1.0, "2026-10": 2.0}}}
    life = [["2026-09-29", 10.0, 0, 0], ["2026-10-01", 20.0, 0, 0], ["2026-10-12", 5.0, 0, 0], ["2026-10-13", 99.0, 0, 0]]
    mix = rb._mix(rows, late, life)
    assert mix == {"till": till, "adm": {"2026-09": 10.0, "2026-10": 25.0},
                   "m": {"2026-09": {"2026-09": 2.5}, "2026-10": {"2026-08": 7.0, "2026-09": 5.5, "2026-10": 6.0}}}
    # GA4's history from 30 Sep: AdMob's 29 Sep is in no month (no split can hold it); that month's row starts there
    late_hs = dict(late, BM={}, EM={})
    assert rb._mix([], late_hs, life, "2026-09-30") == {"till": till, "m": {}, "adm": {"2026-10": 25.0},
                                                         "from": "2026-09-30"}
    assert "from" not in rb._mix([], late_hs, life, "2026-09-01")       # a 1st: a whole month, no mark
    assert rb._mix(rows, {"info": {"busy": 1}}, life) is None and rb._mix(rows, None, life) is None
    assert rb._mix(rows, {"info": {"thru": till}, "B": {}, "MT": None}, life) is None     # no day it can split


REV = {"tz": "UTC", "all_days": {(CHS + timedelta(days=i)).isoformat(): [50_000_000 + 1_000 * i]
                                for i in range(-7, (CTODAY - CHS).days + 1)}}   # AdMob: $50 + a little a day, from a week
#                                                                                 before GA4's history (in no split)


def _co(newest):
    """The install-day read through `newest` on the made-up world: every install day's ages 0 … 30 day by day."""
    x, X = {}, CHS
    while X <= newest:
        x[X.isoformat()] = {"r": [sum(CRATE.values()) if X + timedelta(days=L) <= newest else 0 for L in range(31)],
                            "u": [1] * 31}
        X += timedelta(days=1)
    return {"read_today": newest.isoformat(), "stream_id": "222", "x": x}


def _step(tmp_path, monkeypatch, acc, out, key, nocube=False, co=None, rev=None):
    """app_step on the country world (as tests/test_roi_build._cc_app_step) with AdMob revenue, into acc / out. co: the
    install-day read (default none: every install day's ages 0 … 30 from the cube's day cells)."""
    import shutil
    from admob_iq.fetch import ga4_cube as cu
    data, P, pre, spend, acc0 = _cc_world(tmp_path / key)
    if nocube:
        shutil.rmtree(str(data / cu.DIR))
    _stub_app(monkeypatch, P, co or {"read_today": CTODAY.isoformat(), "stream_id": "222", "x": {}}, spend)
    acc.cmon = acc0.cmon
    rb.app_step(acc, {"history_start": CHS.isoformat(), "stream_id": "222"}, {"app_id": "a~1", "app_name": key},
                key, rev or REV, pre, {}, str(out), str(data), ids=["a~1"])
    assert not acc.fails
    with gzip.open(os.path.join(str(out), rb.PREFIX + key + ".json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


def _all(out):
    with gzip.open(os.path.join(str(out), rb.ALL_FILE), "rt", encoding="utf-8") as f:
        return json.load(f)


def test_app_step_writes_the_mix_and_all_apps_adds_it_up(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    acc = rb.start(cube=True)
    body = _step(tmp_path, monkeypatch, acc, out, "aaaaaaaaaaaa")
    mix = body["mix"]
    assert mix["till"] == CTODAY.isoformat()
    _close(mix["m"], _truth(CTODAY), tol=1e-3)                       # (4 decimals a cell)
    want = {}
    for d, rv, *_ in body["life"]:
        if CHS.isoformat() <= d <= mix["till"] and rv:                  # (AdMob's days before GA4: in no month)
            want[d[:7]] = want.get(d[:7], 0.0) + rv
    assert want and mix["adm"] == {M: round(v, 4) for M, v in want.items()}
    assert rb.finish(acc, {}, str(out)) == ["/roi*"]
    assert _all(out)["mix"] == {"till": mix["till"], "m": mix["m"], "adm": mix["adm"]}     # one app: All apps = it


def test_an_app_without_the_cube_counts_in_all_apps_as_unknown(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    acc = rb.start(cube=True)
    one = _step(tmp_path, monkeypatch, acc, out, "aaaaaaaaaaaa")["mix"]
    two = _step(tmp_path, monkeypatch, acc, out, "bbbbbbbbbbbb", nocube=True)
    assert "mix" not in two and len(acc.apps) == 2
    rb.finish(acc, {}, str(out))
    allm = _all(out)["mix"]
    assert allm["m"] == one["m"] and allm["till"] == one["till"]     # the split: the app that has one
    # its AdMob revenue: both apps (the second one's through its own last day — all of it "Unknown" on the page)
    assert allm["adm"] == {M: round(one["adm"][M] * 2, 4) for M in one["adm"]}



def test_q_cells_split_by_month_sum_to_the_30_day_columns(tmp_path):
    """The whole no-country reads (q) on weeks read whole: every bucket cell the 30-day columns sum (late "B") is in the
    split once, by its activity month (late "BM") — none lost, none taken twice (q's or the cube's, never both)."""
    from tests.test_roi_build import QTODAY, _q_world
    for i, kw in enumerate(({}, {"hot_q": False}, {"fl": {QTODAY.replace(day=2)}})):
        root = tmp_path / str(i)
        P, _ = _q_world(root, **kw)
        late = rb._late(str(root), "a~1", "222", P, mix=set())
        assert late["info"].get("qd") and late["MT"] == late["info"]["thru"]
        b, m = {}, {}
        for X, js in late["B"].items():
            b[X[:7]] = b.get(X[:7], 0.0) + sum(js.values())
        for cs in late["BM"].values():
            for C, v in cs.items():
                m[C] = m.get(C, 0.0) + v
        assert sorted(b) == sorted(m) and all(m[C] == pytest.approx(b[C], abs=1e-9) for C in b), kw


@pytest.mark.parametrize("lag, adlag", [(0, 0), (1, 0), (3, 0), (0, 2)])
def test_the_split_stops_at_the_install_day_reads_day_and_admobs(tmp_path, monkeypatch, lag, adlag):
    """Install days the install-day read has take their ages 0 … 30 from it only: the split never goes past its day
    (nor AdMob's last day) — a day after it would lose those users to Unknown. Aligned: the whole world, exact."""
    out = tmp_path / "out"
    out.mkdir()
    newest, adm = CTODAY - timedelta(days=lag), CTODAY - timedelta(days=adlag)
    rev = {"tz": "UTC", "all_days": {k: v for k, v in REV["all_days"].items() if k <= adm.isoformat()}}
    mix = _step(tmp_path, monkeypatch, rb.start(cube=True), out, "aaaaaaaaaaaa", co=_co(newest), rev=rev)["mix"]
    till = min(newest, adm)
    assert mix["till"] == till.isoformat()
    _close(mix["m"], _truth(till), tol=1e-3)


@pytest.mark.parametrize("where", ["month", "hot"])
def test_a_day_cell_it_cannot_read_turns_only_the_mix_off(tmp_path, capsys, where):
    """A cube day cell e0 cannot read (a month file's or a hot day's): no split (MT None) and the health line — the
    30-day columns as without it."""
    from admob_iq.fetch import ga4_cube as cu
    data, P, _, _, _ = _cc_world(tmp_path)
    good = rb._late(str(data), "a~1", "222", P, mix=set())
    capsys.readouterr()
    if where == "month":
        M, mo = next(iter(cu.months(str(data), "a~1", "222")))
        cc = next(iter(mo["e"]))
        mo["e"][cc][next(iter(mo["e"][cc]))] = [0, "odd"]
        cu.write_json_gz_stable(cu.month_path(str(data), "a~1", M), mo)
    else:
        h = cu.load_head(str(data), "a~1")
        rec = h["d"][max(h["d"])]
        cc = next(iter(rec["e"]))
        rec["e"][cc][next(iter(rec["e"][cc]))] = [0, "odd"]
        cu.write_json_gz_stable(cu.hot_path(str(data), "a~1"), h)
    bad = rb._late(str(data), "a~1", "222", P, mix=set())
    assert bad["MT"] is None and bad["B"] == good["B"] and bad["info"] == good["info"]
    assert "roi mix skipped: TypeError" in capsys.readouterr().err
    assert rb._mix([], bad, []) is None
