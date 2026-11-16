"""⚖️ Breakeven's eCPM index (admob_iq.be_ecpm, inside be_build) — offline on be_build's synthetic apps plus a
SYNTHETIC returning-eCPM store: day 1 = the first session, the planted per-country index curve recovered as the
benchmark, the owner's spend-share rule with the same weights on both sides, the impressions gate and every reason,
no look-ahead, hot / sampled cells never training, and the switch: off = the tab's files byte for byte as without it."""
import copy
import gzip
import json
import math
import os
from datetime import date, timedelta

from admob_iq import be_build as be
from admob_iq import be_ecpm as bec
from admob_iq.fetch import ga4_cecpm as gce
from tests.test_be_build import APPS, KEYS, NOW, TODAY, make

EDGE = TODAY - timedelta(days=gce.FINAL_LAG)
R0 = {"AA": 0.40, "BB": 0.25, "CC": 0.5}                 # day k's eCPM ÷ day 1's at age a: R0 · (1 + a)^−0.2


def ratio(cc, a):
    return R0[cc] * (1.0 + a) ** -0.2


def _fs(data, key):
    with gzip.open(os.path.join(data, "ga4_nvr", key + ".json.gz"), "rt", encoding="utf-8") as f:
        days = json.load(f)["days"]
    out = {}
    for X, rv in days.items():
        for k, cc, rev, im in rv["c"]:
            if k == "n":
                out[(cc, X)] = (rev, im)
    return out


ON = {"ga4_cecpm_use": True, "ga4_cecpm": True}


def write_store(data, key, hot_from=None, smp=(), skip=(), scale=None, upto=None, pool_from=None):
    """The returning-eCPM store of app `key`: every install day of the first-session store, its users on days 2 … 14 at
    ratio() × the first session's eCPM, impressions = 2 × the first session's. hot_from: activity days from it are hot
    copies; smp: activity days sampled; skip: activity days never read; scale: {D: × revenue} (a later change)."""
    fs = _fs(data, key)
    st = gce.Store(data, key, "s1")
    days = {}
    for (cc, X), (rev, im) in fs.items():
        Xd = date.fromisoformat(X)
        for k, a in enumerate(gce.AGES):
            D = Xd + timedelta(days=a)
            if a == 0 or D > TODAY:
                continue
            e1 = rev / im * 1000
            imp = 2 * im
            mic = int(round(e1 * ratio(cc, a) * imp / 1000 * 1e6 * ((scale or {}).get(D.isoformat(), 1.0))))
            rec = days.setdefault(D.isoformat(), {"st": "ok", "f": 0, "at": "t", "n": 0, "xn": 0, "xr": 0, "xi": 0,
                                                  "c": {}})
            arr = rec["c"].setdefault(cc, [0] * 12)
            arr[2 * k] += mic
            arr[2 * k + 1] += imp
    for D, rec in sorted(days.items()):
        if D in skip or (upto and D > upto):                 # (upto: the reads stopped there)
            continue
        if D in smp:
            rec = {"st": "smp", "f": 2, "at": "t", "n": 0, "xn": 0, "xr": 0, "xi": 0}
        elif pool_from is not None and D >= pool_from:              # GA4 sampled the country split: "*" only
            tot = [sum(v[i] for v in rec["c"].values()) for i in range(12)]
            rec = dict(rec, st=gce.POOL, c={gce.POOL_CC: tot}, f6=2)
        if hot_from is not None and D >= hot_from:
            st.head["hot"][D] = rec
        else:
            st.fold(date.fromisoformat(D), rec, "t")
    st.head.update(hs=min(days), upto=upto or (hot_from and (date.fromisoformat(hot_from) - timedelta(days=1)).isoformat())
                   or max(days), oldest=min(days), done=True, app_id=key, stream_id="s1")
    st.save()
    st.save_head()


def run(tmp, s=None, store=True, nvr_mark=None, **kw):
    site, data, dash = make(tmp)
    if store:
        write_store(data, KEYS["a"], **kw)
    if nvr_mark:
        path = os.path.join(data, "ga4_nvr", KEYS["a"] + ".json.gz")
        with gzip.open(path, "rt", encoding="utf-8") as f:
            st = json.load(f)
        st["mark"] = nvr_mark
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(st, f)
    paths = be.run(dash, data, site, s if s is not None else ON, NOW)
    line = be.pop_line()
    with gzip.open(os.path.join(site, "be_%s.json.gz" % KEYS["a"]), "rt", encoding="utf-8") as f:
        body = json.load(f)
    return site, data, body, line, paths


def files(site):
    return {f: open(os.path.join(site, f), "rb").read() for f in sorted(os.listdir(site)) if f.startswith("be_")}


def bench_of(data):
    """The fits' eCPM benchmark → {cc: {j: (index, eCPM USD, n)}}."""
    fc = be.load_fits(data, KEYS["a"])
    assert fc["ec_v"] == bec.stamp()
    return {cc: {j: (100 * math.exp(mi), math.exp(me), n) for j, mi, n, me in v} for cc, v in fc["ec"].items()}


def rows_of(site, data):
    """The app's country rows (be_build's own read) → {day: {cc: row}}."""
    newest, app, cty = be.load(site, data, KEYS["a"], "roi_%s.json.gz" % KEYS["a"])
    out = {}
    for cc, rows in cty.items():
        for x in rows:
            out.setdefault(x.day, {})[cc] = x
    return out


# ── the benchmark ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_planted_per_country_index_curve_is_the_benchmark(tmp_path, monkeypatch):
    monkeypatch.setattr(bec, "MIN_IMP", 1000)             # a floor between CC's planted impressions and AA's (whatever the
    site, data, body, line, _ = run(tmp_path)             # shipped value): CC's thin days stay out of its benchmark
    B = bench_of(data)
    for cc in ("AA", "BB"):
        assert B[cc][0][0] == 100.0 and B[cc][0][2] >= be.MIN_KEPT
        for j, a in enumerate(bec.CARD[1:], 1):
            assert abs(B[cc][j][0] - 100 * ratio(cc, a)) <= 0.1, (cc, j)
            assert B[cc][j][2] >= be.MIN_KEPT
    fs = _fs(data, KEYS["a"])                             # CC: only its PAST days with ≥ MIN_IMP first-session impressions
    O = TODAY.toordinal()
    ok = [X for (cc, X), (rev, im) in fs.items() if cc == "CC" and im >= bec.MIN_IMP and rev > 0
          and date.fromisoformat(X).toordinal() + max(be.LAG, be.SETTLE) <= O]
    assert B["CC"][0][2] == len(ok) < B["AA"][0][2]
    assert ", ecpm apps 1, ecpm failed 0, ecpm stale 0" in line and "AA" not in line
    assert "ec" not in body                               # (nothing the page does not show: no top-level block)


def test_no_look_ahead_never_the_days_it_judges_and_hot_or_sampled_cells_never_train(tmp_path):
    base = bench_of(run(tmp_path / "a")[1])
    # activity days newer than O − (SETTLE − 13): no card day of a past (≥ 30 days old) install day sits on them
    late = [(TODAY - timedelta(days=i)).isoformat() for i in range(be.SETTLE - 13)]
    assert bench_of(run(tmp_path / "b", scale={d: 9.0 for d in late})[1]) == base
    early = (TODAY - timedelta(days=be.SETTLE - 13)).isoformat()                 # day 14 of the install day 30 days back
    assert bench_of(run(tmp_path / "e", scale={early: 9.0})[1]) != base
    hot = bench_of(run(tmp_path / "c", hot_from=(TODAY - timedelta(days=40)).isoformat())[1])
    assert hot["AA"][5][2] < base["AA"][5][2]                                    # hot copies: never trained on
    smp = bench_of(run(tmp_path / "d", smp={(TODAY - timedelta(days=60)).isoformat()})[1])
    assert smp["AA"][2][2] < base["AA"][2][2] and abs(smp["AA"][2][0] - base["AA"][2][0]) <= 0.1


def test_a_new_rule_makes_the_benchmark_again_the_same_day(tmp_path, monkeypatch):
    site, data, dash = make(tmp_path)
    write_store(data, KEYS["a"])
    be.run(copy.deepcopy(dash), data, site, ON, NOW)
    n1 = bench_of(data)["AA"][0][2]
    monkeypatch.setattr(bec, "MIN_IMP", 10 ** 9)                                  # (a deploy mid-day)
    be.run(copy.deepcopy(dash), data, site, ON, NOW + timedelta(hours=2))
    fc = be.load_fits(data, KEYS["a"])
    assert fc["ec_v"] == bec.stamp() and fc["ec"] == {} and n1 > 0


# ── each day ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_this_day_and_the_benchmark_use_one_set_of_countries_and_its_weights(tmp_path):
    """16 Nov 2026 ("ha": one set for the whole card, like the ROAS card): the set = the countries with a day-1 base, a
    valid cell on every lived card day and a benchmark on every one; over it, by spend share, this day's eCPM $ and the
    benchmark's $ per card day; the index = that $ ÷ its day 1's × 100 on both sides (the table divides out to the
    chart); cv the set's share, the same on every point."""
    site, data, body, line, _ = run(tmp_path)
    B = bench_of(data)
    fs = _fs(data, KEYS["a"])
    R = rows_of(site, data)
    seen = 0
    for d in body["days"]:
        ec = d.get("ec")
        if not ec or ec["x"][5] is None or d["age"] < 14 + 5:
            continue
        cs = {cc: x for cc, x in R[d["d"]].items() if cc not in be.SKIP_CC}
        tot = sum(x.sp for x in R[d["d"]].values())
        cov = [cc for cc in cs if cc in B and all(j in B[cc] for j in range(6)) and fs.get((cc, d["d"]), (0, 0))[1] >= bec.MIN_IMP
               and fs[(cc, d["d"])][0] > 0]
        S = sum(cs[cc].sp for cc in cov)
        e1 = {cc: fs[(cc, d["d"])][0] / fs[(cc, d["d"])][1] * 1000 for cc in cov}
        E = [sum(cs[cc].sp * e1[cc] * (ratio(cc, bec.CARD[j]) if j else 1.0) for cc in cov) / S for j in range(6)]
        BE = [sum(cs[cc].sp * B[cc][j][1] for cc in cov) / S for j in range(6)]
        for j in range(6):
            assert abs(ec["e"][j] - E[j]) <= 1e-3 and abs(ec["be"][j] - BE[j]) <= 1e-3
            assert abs(ec["x"][j] - 100 * E[j] / E[0]) <= 0.06 and abs(ec["b"][j] - 100 * BE[j] / BE[0]) <= 0.06
            assert abs(ec["x"][j] - 100 * ec["e"][j] / ec["e"][0]) <= 0.06                    # the table divides out to it
            assert abs(ec["cv"][j] - S / tot) <= 1e-4 and ec["w"][j] == "."
        assert ec["x"][0] == ec["b"][0] == 100.0
        seen += 1
    assert seen > 100


def test_every_missing_value_says_why(tmp_path):
    D = (TODAY - timedelta(days=60)).isoformat()
    sd = (TODAY - timedelta(days=80)).isoformat()
    site, data, body, line, _ = run(tmp_path, skip={D}, smp={sd})
    by = {d["d"]: d for d in body["days"]}
    X = (date.fromisoformat(D) - timedelta(days=6)).isoformat()             # its day 7 is the day never read
    assert by[X]["ec"]["w"][4] == "w" and by[X]["ec"]["x"][4] is None and by[X]["ec"]["e"][4] is None
    for k, j in ((13, 5), (1, 1), (2, 2), (3, 3), (6, 4)):           # its day 14 / 2 / 3 / 4 / 7 was sampled: that ONE
        ec = by[(date.fromisoformat(sd) - timedelta(days=k)).isoformat()]["ec"]    # point says so, never the whole card
        assert ec["w"] == "." * j + "s" + "." * (5 - j), (k, ec["w"])       # — the other five drawn over the one set
        assert ec["x"][j] is None and all(ec["x"][i] is not None for i in range(6) if i != j)
        assert len({ec["cv"][i] for i in range(6) if i != j}) == 1 and ec["cv"][j] == 0.0       # (one cv)
    newest = body["days"][-1]
    assert newest["ec"]["w"][5] == "y"                                       # not lived yet
    m = {"fs": {("AA", "2030-01-01"): (0.0, 5000.0), ("BB", "2030-01-01"): (1.0, 10.0)}, "fa": {}, "fsd": set(),
         "fsm": set(), "cells": {}, "days": {}, "upto": None, "done": False}
    assert bec._cell(m, "AA", "2030-01-01", 0) == (None, "z")
    assert bec._cell(m, "BB", "2030-01-01", 0) == (None, "n")
    assert bec._cell(m, "CC", "2030-01-01", 0) == (None, "w")
    m["fsd"].add("2030-01-01")
    assert bec._cell(m, "CC", "2030-01-01", 0) == (None, "x")
    m["fsm"].add("2030-01-01")
    assert bec._cell(m, "AA", "2030-01-01", 3) == (None, "s")               # day 1's read was a GA4 sample
    # a hot copy still filling, a row GA4 folded or hid, a day GA4 kept collapsed, a stale store
    m = {"fs": {("AA", "2030-01-01"): (5.0, 5000.0)}, "fa": {}, "fsd": set(), "fsm": set(),
         "cells": {("AA", "2030-01-01"): [10, 60] + [0] * 8}, "upto": "2030-01-01", "done": True,
         "days": {"2030-01-02": ("ok", True), "2030-01-03": ("oth", False), "2030-01-04": ("thr", False),
                  "2030-01-07": (gce.LOW, False)}}
    assert bec._cell(m, "AA", "2030-01-01", 1) == (None, "w")
    assert bec._cell(m, "AA", "2030-01-01", 2) == (None, "o") and bec._cell(m, "AA", "2030-01-01", 3) == (None, "t")
    assert bec._cell(m, "AA", "2030-01-01", 4) == (None, "l")
    m["stale"] = True
    assert bec._cell(m, "AA", "2030-01-01", 5) == (None, "f")
    # the app line's reason: the one carrying the most spend (ties: WHY's order)
    assert bec._most([(90, "w"), (5, "n"), (5, "n")]) == "w" and bec._most([]) == "x"
    assert bec._most([(1, "n"), (1, "s")]) == "s" and set(bec.WHY) >= set("ywfslotnzxkcbh")


def test_a_sampled_first_session_read_gives_no_base(tmp_path):
    X = (TODAY - timedelta(days=50)).isoformat()
    body = run(tmp_path, nvr_mark={X: "s"})[2]
    d = next(x for x in body["days"] if x["d"] == X)
    assert d["ec"]["w"] == "ssssss" and d["ec"]["x"] == [None] * 6


def test_a_hot_day_is_marked_not_final(tmp_path):
    late = (EDGE - timedelta(days=1)).isoformat()
    body = run(tmp_path, hot_from=late)[2]
    X = (date.fromisoformat(late) - timedelta(days=1)).isoformat()
    d = next(x for x in body["days"] if x["d"] == X)
    assert d["ec"]["p"][1] == "1" and d["ec"]["p"][0] == "0"


def test_a_stale_store_says_so_and_reaches_the_banner(tmp_path, capsys):
    site, data, body, line, _ = run(tmp_path, upto=(TODAY - timedelta(days=40)).isoformat())
    assert ", ecpm stale 1" in line and "be ecpm skipped: StaleWarning" in capsys.readouterr().err
    late = [d for d in body["days"] if d["d"] > (TODAY - timedelta(days=30)).isoformat() and d.get("ec")]
    assert late and all(d["ec"]["w"][1:] == "f" * 5 for d in late if d["age"] >= 14)


# ── the switch and failures ─────────────────────────────────────────────────────────────────────────────────────────
def test_switched_off_the_files_are_byte_for_byte_as_without_it(tmp_path):
    off, *_ = run(tmp_path / "off", s={"ga4_cecpm_use": False, "ga4_cecpm": True})
    none, *_ = run(tmp_path / "none", s={}, store=False)
    no_reads, *_ = run(tmp_path / "noreads", s={"ga4_cecpm_use": True, "ga4_cecpm": False})
    on_no_store, _, body, line, _ = run(tmp_path / "nostore", store=False)
    assert files(off) == files(none) == files(no_reads) == files(on_no_store)    # (no store yet: nothing added)
    assert all("ec" not in d for d in body["days"]) and ", ecpm apps 0, ecpm failed 0, ecpm stale 0" in line


def test_a_damaged_store_costs_the_ecpm_part_only(tmp_path, capsys, monkeypatch):
    real = gce.load_cells

    def boom(*a, **k):
        raise ValueError("synthetic")
    monkeypatch.setattr(gce, "load_cells", boom)
    site, data, body, line, paths = run(tmp_path / "x")
    assert paths == ["/be_*"] and all("ec" not in d for d in body["days"]) and ", ecpm failed " in line
    assert "be ecpm skipped: ValueError" in capsys.readouterr().err
    monkeypatch.setattr(gce, "load_cells", real)
    ref = run(tmp_path / "ref", s={})[0]
    assert files(site) == files(ref)                                  # the rest exactly as without it


def test_settings_pass_the_card_switch(monkeypatch):
    from admob_iq.config import settings
    for k in ("GA4_CECPM_USE", "GA4_CECPM"):
        monkeypatch.delenv(k, raising=False)
    assert settings()["ga4_cecpm_use"] is False and not bec.enabled(settings())
    monkeypatch.setenv("GA4_CECPM_USE", "true")
    assert not bec.enabled(settings())                                # (the reads off: the card never reads a store)
    monkeypatch.setenv("GA4_CECPM", "true")
    assert settings()["ga4_cecpm_use"] is True and bec.enabled(settings())


def test_a_card_on_days_ga4_sampled_the_country_split_is_every_country_together(tmp_path):
    pf = (TODAY - timedelta(days=45)).isoformat()
    site, data, body, line, _ = run(tmp_path, pool_from=pf)
    fs = _fs(data, KEYS["a"])
    fc = be.load_fits(data, KEYS["a"])
    P = {j: (100 * math.exp(mi), math.exp(me)) for j, mi, n, me in fc["ec"][gce.POOL_CC]}
    seen = 0
    for d in body["days"]:
        ec = d.get("ec")
        X = d["d"]
        if not ec or d["age"] < 14 or X < (date.fromisoformat(pf) - timedelta(days=13)).isoformat():
            continue
        assert ec.get("pl") == 1 and ec["cv"] == [None] * 6
        cs = [(cc, rv, im) for (cc, x), (rv, im) in fs.items() if x == X]
        e1 = sum(rv for _, rv, _ in cs) / sum(im for _, _, im in cs) * 1000
        for j in (1, 3, 5):
            a = bec.CARD[j]
            ek = sum(rv * 1000 / im * ratio(cc, a) * 2 * im for cc, rv, im in cs) / sum(2 * im for _, _, im in cs)
            assert abs(ec["e"][j] - ek) <= 1e-3 and abs(ec["x"][j] - 100 * ek / e1) <= 0.15
            assert abs(ec["b"][j] - 100 * P[j][1] / P[0][1]) <= 0.06 and abs(ec["be"][j] - P[j][1]) <= 1e-3 and ec["w"][j] == "."   # (its eCPMs' ratio, like the table)
        assert ec["x"][0] == 100.0 and abs(ec["e"][0] - e1) <= 1e-3
        seen += 1
    assert seen > 10
    early = [d for d in body["days"] if d.get("ec") and d["age"] >= 14
             and d["d"] < (date.fromisoformat(pf) - timedelta(days=13)).isoformat()]
    assert early and all("pl" not in d["ec"] for d in early)              # (cards before it: the countries' line)


# ── review round 2: a new app is not stale, the reason carrying the spend, day 1 not final, "h" from the fit ─────────
class _Row:
    def __init__(self, sp):
        self.sp = sp


def _m(days, fs, cells, done=True, upto="2030-01-20", hs="2030-01-01"):
    return {"fs": fs, "fa": {}, "fsd": set(), "fsm": set(), "cells": cells, "pool": {}, "days": days, "upto": upto,
            "done": done, "hs": hs}


def test_a_new_app_with_nothing_folded_is_not_stale():
    O = date(2030, 1, 10).toordinal()
    assert not bec.stale({"upto": None, "hs": "2030-01-07"}, O)          # (its first final day is not due yet)
    assert bec.stale({"upto": None, "hs": "2029-12-01"}, O)              # nothing folded long after it: stale
    assert bec.stale({"upto": None, "hs": None}, O) and not bec.stale({"upto": "2030-01-05"}, O)


def test_the_app_lines_reason_is_the_one_carrying_the_spend_and_day_1_is_marked_while_it_can_change():
    X = "2030-01-10"
    body = {"days": [{"d": X, "age": 3}]}
    pin = ("2030-01-12", [], {X: {"AA": _Row(90.0), "BB": _Row(10.0)}})
    fc = {"ec": {"BB": [[0, 0.0, 30, 0.0]]}, "ec_v": bec.stamp()}       # BB: a day-1 benchmark only
    m = _m({"2030-01-11": ("ok", False)}, {("AA", X): (5.0, 5000.0), ("BB", X): (5.0, 5000.0)},
           {("BB", X): [3000000, 2000] + [0] * 8})                       # AA: no row that day ("x"); BB: an index
    bec.attach(body, pin, fc, m)
    ec = body["days"][0]["ec"]
    assert ec["w"][1] == "x" and ec["wb"][1] == "."                      # the 90 % country's reason, not BB's "c"
    assert ec["p"][0] == "1"                                             # 2 days old: the first session can change
    fc2 = {"ec": {}, "ec_v": bec.stamp(), "ec_h": True}
    pin2 = ("2030-01-30", [], {X: {"BB": _Row(10.0)}})
    body2 = {"days": [{"d": X, "age": 20}]}
    bec.attach(body2, pin2, fc2, _m({"2030-01-11": ("ok", False)}, {("BB", X): (5.0, 5000.0)},
                                    {("BB", X): [3000000, 2000] + [0] * 8}))
    ec2 = body2["days"][0]["ec"]
    assert ec2["w"][1] == "c" and ec2["wb"][1] == "h" and ec2["p"][0] == "0"   # made while the history was filling


# ── review round 3 (16 Nov 2026, the one set): a day GA4 answered unusable for every country ───────────────────────
def test_a_day_unusable_for_every_country_is_one_null_point_never_the_whole_card():
    """A folded activity day GA4 answered unusable for EVERY country (sampled / cut, kept so after its retries;
    collapsed, kept so after LOW_WAIT) says nothing of any one country: it never empties the card's one set — that one
    point null with its why, the other five over the same set and weights (SYNTHETIC numbers)."""
    X = "2030-01-01"
    cs = {"AA": _Row(60.0), "BB": _Row(30.0), "CC": _Row(10.0)}
    fs = {(cc, X): (5.0, 5000.0) for cc in cs}                            # day 1: $1.00 on 5,000 impressions
    cells = {(cc, X): [1000000, 2000] * 5 for cc in cs}                   # days 2 … 14: $0.50 on 2,000 impressions
    fc = {"ec": {cc: [[j, 0.0, 30, 0.0] for j in range(6)] for cc in cs}, "ec_v": bec.stamp()}
    for st, why in (("smp", "s"), ("cut", "s"), (gce.LOW, "l")):
        days = {(date(2030, 1, 1) + timedelta(days=a)).isoformat(): (st if a == 6 else "ok", False)
                for a in bec.CARD[1:]}
        body = {"days": [{"d": X, "age": 20}]}
        bec.attach(body, ("2030-01-21", [], {X: cs}), fc, _m(days, fs, cells))
        ec = body["days"][0]["ec"]                                         # its day 7 (age 6) folded that way
        assert ec["w"] == "....%s." % why and ec["wb"] == "......", (st, ec["w"])
        assert ec["x"] == [100.0, 50.0, 50.0, 50.0, None, 50.0] and ec["e"] == [1.0, 0.5, 0.5, 0.5, None, 0.5], st
        assert ec["b"][4] is None and ec["cv"] == [1.0, 1.0, 1.0, 1.0, 0.0, 1.0], st



def test_a_day_no_country_has_a_valid_cell_is_one_null_point_never_the_whole_card():
    """16 Nov 2026 (review): every country under MIN_IMP on one lived final card day must not empty the set — that day is
    one null point with its own letter, the other points keep the one set (synthetic)."""
    X = "2030-03-01"
    days = {(date.fromisoformat(X) + timedelta(days=a)).isoformat(): ("ok", False) for a in bec.CARD}
    cells = {("AA", X): [2_000_000, 400, 1_500_000, 300, 1_400_000, 300, 1_000_000, 200, 10_000, 5],
             ("BB", X): [1_000_000, 500, 800_000, 400, 700_000, 400, 600_000, 300, 5_000, 4]}
    m = {"fs": {("AA", X): (4.0, 1000.0), ("BB", X): (1.0, 800.0)}, "fa": {}, "fsd": {X}, "fsm": set(), "cells": cells,
         "pool": {}, "days": days, "upto": max(days), "done": True}
    B = {cc: [[j, math.log(0.5), 30, math.log(1.0)] for j in range(6)] for cc in ("AA", "BB")}
    fc = {"ec": B, "ec_v": bec.stamp()}

    class R:
        def __init__(self, sp):
            self.sp = sp
    pin = ((date.fromisoformat(X) + timedelta(days=40)).isoformat(), [], {X: {"AA": R(60.0), "BB": R(40.0)}})
    body = {"days": [{"d": X}]}
    bec.attach(body, pin, fc, m)
    ec = body["days"][0]["ec"]
    assert ec["w"] == ".....n" and ec["x"][5] is None and all(v is not None for v in ec["x"][:5])
    assert len({c for c in ec["cv"][:5]}) == 1 and ec["cv"][0] == 1.0


def test_a_country_counts_until_the_day_its_data_drops_and_that_day_is_named():
    """16 Nov 2026 ("sab din rakho · bs ak info add kar do jab se giravat ati he to konsi country count nahi hua vo bata do
    vo day"): AA counts on days 1–2 and drops from day 3 (under MIN_IMP) — named in "dr" with that day, its share and
    why; the index is CHAINED day to day on the countries counted both days (a country leaving never moves it)
    (synthetic)."""
    X = "2030-03-01"
    days = {(date.fromisoformat(X) + timedelta(days=a)).isoformat(): ("ok", False) for a in bec.CARD}
    #            day 2 (age 1)        day 3 (age 2)    day 4 (age 3)    day 7 (age 6)    day 14 (age 13)
    cells = {("AA", X): [3_000_000, 300, 50_000, 20, 40_000, 20, 30_000, 10, 10_000, 5],
             ("BB", X): [1_000_000, 500, 900_000, 450, 800_000, 400, 600_000, 300, 400_000, 200]}
    m = {"fs": {("AA", X): (20.0, 1000.0), ("BB", X): (2.0, 800.0)}, "fa": {}, "fsd": {X}, "fsm": set(), "cells": cells,
         "pool": {}, "days": days, "upto": max(days), "done": True}
    B = {cc: [[j, math.log(0.5), 30, math.log(10.0 if cc == "AA" else 1.0)] for j in range(6)] for cc in ("AA", "BB")}
    fc = {"ec": B, "ec_v": bec.stamp()}

    class R:
        def __init__(self, sp):
            self.sp = sp
    pin = ((date.fromisoformat(X) + timedelta(days=40)).isoformat(), [], {X: {"AA": R(75.0), "BB": R(25.0)}})
    body = {"days": [{"d": X}]}
    bec.attach(body, pin, fc, m)
    ec = body["days"][0]["ec"]
    e1 = {"AA": 20.0, "BB": 2.5}                                             # day-1 eCPMs ($): 20 / 1000 · 2 / 800 × 1000
    ek = {"AA": [10.0, None], "BB": [2.0, 2.0]}                               # days 2 and 3 ($)
    E2 = (75 * ek["AA"][0] + 25 * ek["BB"][0]) / 100
    E1 = (75 * e1["AA"] + 25 * e1["BB"]) / 100
    assert abs(ec["e"][1] - E2) < 1e-3 and abs(ec["x"][1] - 100 * E2 / E1) <= 0.06       # day 2: both countries
    assert abs(ec["e"][2] - 2.0) < 1e-3 and abs(ec["x"][2] - ec["x"][1] * 2.0 / 2.0) <= 0.06   # day 3: BB alone — CHAINED:
    #   day 2's index × BB's own move from day 2 (AA leaving moves nothing: BB is flat, so the line is flat)
    assert ec["cv"][1] == 1.0 and ec["cv"][2] == 0.25 and ec["w"] == "......"
    assert ec["dr"] == [[2, [["AA", 0.75, "n"]]]]                                    # from day 3 on: AA, 75 %, too few impressions
    assert abs(ec["b"][2] - 100.0) <= 0.06 and abs(ec["be"][0] - (75 * 10 + 25 * 1) / 100) < 1e-3   # B: the same countries


def _card(cells, fs, B, sp, X="2030-03-01", hot=(), newest_age=40):
    days = {(date.fromisoformat(X) + timedelta(days=a)).isoformat(): ("ok", a in hot) for a in bec.CARD}
    m = {"fs": fs, "fa": {}, "fsd": {X}, "fsm": set(), "cells": cells, "pool": {}, "days": days, "upto": max(days),
         "done": True}

    class R:
        def __init__(self, v):
            self.sp = v
    pin = ((date.fromisoformat(X) + timedelta(days=newest_age)).isoformat(), [], {X: {cc: R(v) for cc, v in sp.items()}})
    body = {"days": [{"d": X}]}
    bec.attach(body, pin, {"ec": B, "ec_v": bec.stamp()}, m)
    return body["days"][0]["ec"]


def test_a_day_no_counted_country_can_stay_drops_nobody_and_a_benchmarkless_country_leaves_on_the_next_drawable_day():
    """Review, 16 Nov 2026: AA's day-3 row folded into "(other)" and BB without a benchmark past day 2 must not empty
    the card — day 3 null ("o"), BB leaves on day 4 ("c"), AA keeps days 4 / 7 / 14 (synthetic)."""
    X = "2030-03-01"
    cells = {("AA", X): [1_000_000, 500, 0, 0, 900_000, 500, 800_000, 500, 700_000, 500],
             ("BB", X): [500_000, 500, 400_000, 500, 300_000, 500, 200_000, 500, 100_000, 500]}
    fs = {("AA", X): (2.0, 1000.0), ("BB", X): (1.0, 1000.0)}
    B = {"AA": [[j, 0.0, 30, math.log(1.0)] for j in range(6)], "BB": [[j, 0.0, 30, math.log(1.0)] for j in range(2)]}
    m_days = {(date.fromisoformat(X) + timedelta(days=a)).isoformat(): ("oth" if a == 2 else "ok", False) for a in bec.CARD}
    m = {"fs": fs, "fa": {}, "fsd": {X}, "fsm": set(), "cells": cells, "pool": {}, "days": m_days, "upto": max(m_days),
         "done": True}

    class R:
        def __init__(self, v):
            self.sp = v
    pin = ((date.fromisoformat(X) + timedelta(days=40)).isoformat(), [], {X: {"AA": R(70.0), "BB": R(30.0)}})
    body = {"days": [{"d": X}]}
    bec.attach(body, pin, {"ec": B, "ec_v": bec.stamp()}, m)
    ec = body["days"][0]["ec"]
    assert ec["x"][2] is None and ec["w"][2] == "o" and all(ec["x"][j] is not None for j in (0, 1, 3, 4, 5))
    assert ec["dr"] == [[3, [["BB", 0.3, "c"]]]] and ec["cv"][3] == 0.7 and ec["cv"][1] == 1.0
    # AA alone from day 4: chained from day 2 (the last drawn day) on AA's own move ($2.00 → $1.80)
    assert abs(ec["x"][3] - ec["x"][1] * 1.8 / 2.0) <= 0.06


def test_a_hot_copy_still_filling_drops_nobody_and_its_point_is_the_countries_that_have_a_cell():
    """Review, 16 Nov 2026: a hot day where only AA has reached MIN_IMP must not list BB under "Ginti se bahar" — no
    "dr"; the not-final point is AA's own move, chained (synthetic)."""
    X = "2030-03-01"
    cells = {("AA", X): [1_000_000, 500, 900_000, 500, 0, 0, 0, 0, 0, 0],
             ("BB", X): [500_000, 500, 40_000, 20, 0, 0, 0, 0, 0, 0]}                # day 3: BB still filling (20)
    fs = {("AA", X): (2.0, 1000.0), ("BB", X): (1.0, 1000.0)}
    B = {cc: [[j, 0.0, 30, math.log(1.0)] for j in range(6)] for cc in ("AA", "BB")}
    ec = _card(cells, fs, B, {"AA": 60.0, "BB": 40.0}, hot=(2,), newest_age=3)
    assert "dr" not in ec and ec["p"][2] == "1"
    assert ec["cv"][2] == 0.6 and abs(ec["x"][2] - ec["x"][1] * 1.8 / 2.0) <= 0.06       # AA's own move from day 2


def test_day_1_is_sampled_only_when_the_country_read_itself_was():
    """16 Nov 2026 (the busiest app: every first-session × country read whole, another read of the day flagged): only the
    country read's own flag makes day 1's base a sample; a day read before the store kept its reads' own uses "mark"."""
    st = {"mark": {"d1": "s", "d2": "s", "d3": "s", "d4": "t", "d5": "t"},
          "mp": {"d1": {"u": "s"}, "d2": {"c": "s", "u": "s"}, "d4": {"c": "t"}, "d5": {"u": "t", "c": "s"}}}
    assert bec._sampled_base(st, {"d1", "d2", "d3", "d4", "d5"}) == {"d2", "d3", "d5"}   # (d5: its own flag, not "mark")
    assert bec._sampled_base(st, {"d1"}) == set() and bec._sampled_base(None, {"d1"}) == set()
