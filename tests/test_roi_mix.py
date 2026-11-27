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


def test_mix_spend_by_install_month_over_the_days_the_split_holds():
    """💸 (owner, 27 Nov 2026: "spending add karo, fir % spending ke against dikhao"): life's Google Ads spend by install
    month on the install days the split holds — hs … till, an install row's day or a cube day cell's (EM); a spend day
    GA4 has neither for is in neither; a day outside the spend data's first … last → that month null (not all in)."""
    till = "2026-10-12"
    late = {"MT": till, "BM": {"2026-10": {"2026-09": 1.0}}, "EM": {"2026-10-05": {"2026-10": 1.0}}}   # Oct 5: the cube's
    rows = [{"X": date(2026, 9, d)} for d in (14, 15, 30)] + [{"X": date(2026, 10, d)} for d in (1, 12, 13)]
    life = [["2026-09-14", 1.0, 5.0, 450.0],                             # before GA4's history (15 Sep): no month
            ["2026-09-15", 1.0, 10.0, 900.0], ["2026-09-20", 0.0, 50.0, 4500.0],   # 20 Sep: no row, no cube cell
            ["2026-09-30", 0.0, 20.0, 1800.0], ["2026-10-01", 2.0, 0.0, 0.0],      # 1 Oct: no spend
            ["2026-10-05", 0.0, 7.0, 630.0],                               # a cube day cell's day (no install row)
            ["2026-10-12", 2.0, 30.0, 2700.0], ["2026-10-13", 9.0, 99.0, 8910.0]]   # after till: not taken
    whole = {"2026-09": [30.0, 2700.0], "2026-10": [37.0, 3330.0]}
    assert rb._mix(rows, late, life, "2026-09-15", ("2026-01-01", till))["sp"] == whole
    assert rb._mix(rows, late, life, "2026-09-15", ("2026-01-01", "2026-12-31"))["sp"] == whole   # data past till
    # Google Ads through 11 Oct only: October not all in → null; September whole. From 16 Sep: September null
    assert rb._mix(rows, late, life, "2026-09-15", ("2026-01-01", "2026-10-11"))["sp"] == {"2026-09": [30.0, 2700.0],
                                                                                           "2026-10": None}
    assert rb._mix(rows, late, life, "2026-09-15", ("2026-09-16", till))["sp"] == {"2026-09": None,
                                                                                   "2026-10": [37.0, 3330.0]}
    # no spend data for the app, or no spend at all: no "sp"
    assert "sp" not in rb._mix(rows, late, life, "2026-09-15")
    assert "sp" not in rb._mix(rows, late, [[x[0], x[1], 0.0, 0.0] for x in life], "2026-09-15", ("2026-01-01", till))


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


def _step(tmp_path, monkeypatch, acc, out, key, nocube=False, co=None, rev=None, st=None, nospend=False):
    """app_step on the country world (as tests/test_roi_build._cc_app_step) with AdMob revenue, into acc / out. co: the
    install-day read (default none: every install day's ages 0 … 30 from the cube's day cells). st: Google Ads' last day
    (default the world's: Oct 12, a day before the split's); nospend: the app has no spend data."""
    import shutil
    from admob_iq.fetch import ga4_cube as cu
    data, P, pre, spend, acc0 = _cc_world(tmp_path / key)
    if st:
        spend["till"] = st
    if nocube:
        shutil.rmtree(str(data / cu.DIR))
    _stub_app(monkeypatch, P, co or {"read_today": CTODAY.isoformat(), "stream_id": "222", "x": {}},
              None if nospend else spend)
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
    # 💸 its Google Ads spend ($10 a day from 1 Aug) by install month; Google Ads through Oct 12, the split through Oct 13:
    # October's spend not all in → null
    assert mix["sp"] == {"2026-08": [310.0, 310.0], "2026-09": [300.0, 300.0], "2026-10": None}
    assert rb.finish(acc, {}, str(out)) == ["/roi*"]
    assert _all(out)["mix"] == {"till": mix["till"], "m": mix["m"], "adm": mix["adm"], "sp": mix["sp"]}   # one app: it


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
    assert allm["sp"] == one["sp"]                                   # … and its spend only (none for a split it has not)
    # its AdMob revenue: both apps (the second one's through its own last day — all of it "Unknown" on the page)
    assert allm["adm"] == {M: round(one["adm"][M] * 2, 4) for M in one["adm"]}



@pytest.mark.parametrize("null_first", [False, True])
def test_all_apps_spend_adds_up_and_a_month_not_all_in_stays_null(tmp_path, monkeypatch, null_first):
    """All apps' spend = the apps' added up; one app's month not all in → All apps' not all in, whichever app comes first."""
    out = tmp_path / "out"
    out.mkdir()
    acc = rb.start(cube=True)
    sts = [CTODAY.isoformat(), None]                    # Google Ads in to the split's day · to the day before (the world's)
    got = [_step(tmp_path, monkeypatch, acc, out, k * 12, st=st)["mix"]
           for k, st in (zip("ba", sts[::-1]) if null_first else zip("ab", sts))]
    one, two = (got[1], got[0]) if null_first else (got[0], got[1])
    assert one["sp"]["2026-10"] == [120.0, 120.0] and two["sp"]["2026-10"] is None
    rb.finish(acc, {}, str(out))
    assert _all(out)["mix"]["sp"] == {"2026-08": [620.0, 620.0], "2026-09": [600.0, 600.0], "2026-10": None}


def test_all_apps_total_has_an_app_without_spend_its_spend_never(tmp_path, monkeypatch):
    """All apps: every app's earnings in the split (the agreed "% wapas" = Total ÷ Spend; the page's note says apps with
    no ads that month are in the Total), the spend only from the apps that have it."""
    out = tmp_path / "out"
    out.mkdir()
    acc = rb.start(cube=True)
    one = _step(tmp_path, monkeypatch, acc, out, "aaaaaaaaaaaa")["mix"]
    two = _step(tmp_path, monkeypatch, acc, out, "bbbbbbbbbbbb", nospend=True)["mix"]
    assert "sp" not in two and two["m"]
    rb.finish(acc, {}, str(out))
    allm = _all(out)["mix"]
    assert allm["sp"] == one["sp"]
    _close(allm["m"], _sum(one["m"], two["m"]), tol=1e-3)


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
