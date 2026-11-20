"""⚖️ Breakeven — round 5's three checks of the Google Ads users' source (admob_iq.be_build; owner, 20 Nov 2026: "agar
galat he to thik karte jao jab tak thik na ho jaye"), each with its own switch, on made-up apps (tests/test_be_paid.py's
world):
  FSC  a country's Google Ads users' first-session read on ANY day (young too): GA4-sampled (the paid store's own "mp"
       mark on its "c" read) while every user's read is whole, or MORE than every user's (fs_over) → every user's
       eCPM_fs, the row tagged "f"; never on the re-read list, never the banner; counted "guard cty"; the caches'
       stamp carries it (a flip: made again);
  GAP  pack gaps also by the share's own fall (GAP_REL × its median) and by the cube ledger's measured loss (≥
       GAP_LOSS); a forecast country row holding a gap date: "g", counted;
  UPI  a forecast country row whose users per install sit off its benchmark's basis: "u" with both numbers in "cku".
  RSF  the countries table's "ROAS so far": each covered country row's so-far read against B's median ROAS at the same
       age (the row's 14th element).
At the thresholds (each boundary on and off), end to end in the step, each switch alone, and all four off: every
output byte for byte as the build before them (digests worked out once with 60cd202's admob_iq on these same worlds).
SYNTHETIC values only (apps "app~synth-…", countries AA … DH, the calendar 2030–2031)."""
import gzip
import io
import json
import math
import os
from datetime import date, timedelta

import pytest

from admob_iq import be_build as be
from tests import test_be_build as T
from tests import test_be_fsguard as FG
from tests import test_be_paid as P

KA = P.KA
LAGF = max(be.LAG, be.gv.FINAL_LAG)                              # the guard's final lag (the tests' GA4_FINAL_DAYS)
YNG = (T.TODAY - timedelta(days=be.FSQ_YOUNG + 1)).isoformat()  # a young day (not final; ≤ newest − FSQ_YOUNG)
FIN = (T.TODAY - timedelta(days=LAGF + 6)).isoformat()          # a final day
NEW = (T.TODAY - timedelta(days=be.FSQ_YOUNG - 1)).isoformat()  # newer than FSC's subset rule judges
GAPD = T.TODAY - timedelta(days=12)                             # a pack-gap date (final cells: ≤ newest − CLAG)


# ── the thresholds ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_fs_over_at_its_thresholds():
    a = [10.0, 100]                                                  # every user's: $10, 100 impressions
    assert not be.fs_over([10.5, 110], a)                            # 110 = 1.05 × 100 + 5: not over
    assert be.fs_over([10.0, 111], a)                                # 111 impressions: over
    assert not be.fs_over([11.5, 50], a)                             # $11.50 = 1.05 × 10 + 1: not over
    assert be.fs_over([11.51, 50], a)                                # a cent more: over
    assert not be.fs_over([0.5, 6000], None) and not be.fs_over([50.0, 6], None)   # no cell of every user's: nothing
    assert be.fs_over([0.5, 6], [0.0, 0]) and not be.fs_over([0.5, 5], [0.0, 0])   # (a cell of 0: the margins alone)
    assert not be.fs_over(None, a) and not be.fs_over([], a)         # no paid cell: nothing to say


def test_smp_reads_the_c_reads_own_mark():
    st = {"days": {"d1": {}, "d2": {}, "d3": {}, "d4": {}}, "mp": {"d1": {"c": "s"}, "d2": {"u": "s"}, "d3": {}},
          "mark": {"d2": "s", "d4": "s"}}
    assert be._smp(st, "d1") is True                                 # the "c" read sampled
    assert be._smp(st, "d2") is False and be._smp(st, "d3") is False   # another read sampled / all whole
    assert be._smp(st, "d4") is True                                 # no per-read flag: the day mark
    assert be._smp(st, "d9") is None and be._smp(None, "d1") is None   # no read of the day / no store


def test_rel_gaps_at_its_threshold_baseline_and_window():
    S = {d: 100.0 for d in range(1, 12)}
    C = {d: 95.0 for d in range(1, 12)}
    C[9] = 0.6 * 95.0                                                # exactly 0.6 × its median: not a gap
    assert be._rel_gaps(S, C, 11, 0.6) == set()
    C[9] = 0.6 * 95.0 - 0.01                                         # under: a gap
    assert be._rel_gaps(S, C, 11, 0.6) == {9}
    assert be._rel_gaps(S, C, 8, 0.6) == set()                       # (after the edge: not judged)
    C2 = {1: 95.0, 2: 95.0, 3: 50.0}                                 # (only 2 dates before it: no baseline yet)
    assert be._rel_gaps({1: 100.0, 2: 100.0, 3: 100.0}, C2, 3, 0.6) == set()
    far = {1: 100.0, 2: 100.0, 3: 100.0, 30: 100.0}                  # (its baseline older than 3 × GAP_N days: none)
    assert be._rel_gaps(far, {1: 95.0, 2: 95.0, 3: 95.0, 30: 10.0}, 30, 0.6) == set()
    G = {d: 95.0 for d in range(1, 12)}                              # a gap never sets its own baseline: day 8 and
    G[8] = G[9] = 10.0                                               # day 9 both gaps …
    assert be._rel_gaps(S, G, 11, 0.6) == {8, 9}
    assert be._rel_gaps(S, G, 11, 0.6, {8}) == {9}                   # … a date already a gap is skipped, not judged
    S15 = {d: 100.0 for d in range(1, 16)}                           # a LONG gap (7 dates in a row) stays a gap to its
    L = {**{d: 95.0 for d in range(1, 16)}, **{d: 10.0 for d in range(6, 13)}}     # end: its own dates never become
    assert be._rel_gaps(S15, L, 15, 0.6) == set(range(6, 13))        # the baseline
    tiny = {d: 1.0 for d in range(1, 12)}                            # (the packs usually carry < $1 of the date: nothing)
    assert be._rel_gaps(tiny, {d: (0.5 if d < 9 else 0.1) for d in range(1, 12)}, 11, 0.6) == set()


def test_led_gaps_at_its_threshold_floor_and_edge():
    ls = {5: (0.4, 10.0), 6: (0.399, 10.0), 7: (0.9, 0.99), 8: (0.9, 10.0)}
    assert be._led_gaps(ls, 7) == {5}                                # 0.4: a gap; 0.399: not; under $1 a day: nothing
    assert be._led_gaps(ls, 8) == {5, 8} and be._led_gaps(None, 8) == set()   # (8: past the edge of 7)


def test_pack_gaps_add_the_new_rules_only_when_on(monkeypatch):
    S = {d: 100.0 for d in range(700000, 700020)}
    C = dict.fromkeys(S, 98.0)
    C[700010], C[700012] = 50.0, 20.0                                # one fall (0.51 × its level), one under 0.35 ×
    ls = {700015: (0.5, 100.0)}
    nw = 700019 + be.CLAG
    st = {}
    assert be.pack_gaps(S, C, nw, None, ls, st) == {700010, 700012, 700015}
    assert st == {"gap_rel": 1, "gap_led": 1}                       # (the dates the new rules add)
    monkeypatch.setattr(be, "GAP_ON", False)
    st = {}
    assert be.pack_gaps(S, C, nw, None, ls, st) == {700012} and st == {}     # off: the absolute rule alone, as before
    assert be.pack_gaps_p(S, C, nw, None, None, ls) == {700012}             # (off: PACK_GAP × its median, as before)
    monkeypatch.setattr(be, "GAP_ON", True)
    st = {}
    assert be.pack_gaps_p(S, C, nw, None, None, ls, st) == {700010, 700012, 700015}
    assert st == {"gap_rel": 1, "gap_led": 1}


def _cube(data, key, months, stream="s1", hot=True, sub="ga4_cube_paid"):
    d = os.path.join(data, sub, key)
    os.makedirs(d, exist_ok=True)
    for name, days, sid in months:
        P._wr(os.path.join(d, name + ".json.gz"), {"v": 1, "stream_id": sid or stream, "days": days, "b": {}, "c": {},
                                                    "e": {}, "t": {}, "loss": {}})
    if hot:
        P._wr(os.path.join(d, "hot.json.gz"), {"v": 1, "stream_id": stream, "d": {"2031-06-30": {"t": 9, "loss": 9}}})


def test_the_ledger_reads_every_folded_day_of_its_own_stream_only(tmp_path):
    data = str(tmp_path)
    _cube(data, KA, [("2031-05", {"2031-05-02": {"t": 4_000_000, "loss": 2_000_000}, "2031-05-03": {"t": 0, "loss": 0}},
                      None),
                     ("2031-04", {"2031-04-02": {"t": 4_000_000, "loss": 4_000_000}}, "other-stream")])
    got = be._ledger(data, KA, True)
    assert got == {date(2031, 5, 2).toordinal(): (0.5, 4.0)}         # (another stream's month, an empty day, the hot
    assert be._ledger(data, KA, False) == {} and be._ledger(data, "000000000000", True) == {}   # days: none of it)
    _cube(data, KA, [("2031-05", {"2031-05-02": {"t": 4_000_000, "loss": 1_000_000}}, None)], sub="ga4_cube")
    assert be._ledger(data, KA, False) == {date(2031, 5, 2).toordinal(): (0.25, 4.0)}   # src "a": every user's cube


def test_the_ledger_is_kept_per_month_file_and_a_month_is_parsed_once(tmp_path, monkeypatch):
    data = str(tmp_path)
    _cube(data, KA, [("2031-05", {"2031-05-02": {"t": 4_000_000, "loss": 2_000_000}}, None),
                     ("2031-04", {"2031-04-02": {"t": 2_000_000, "loss": 1_000_000}}, None)])
    first = be._ledger(data, KA, True)
    cp = os.path.join(data, be.DIR, "ledgerp_%s.json.gz" % KA)
    assert os.path.exists(cp) and first == {date(2031, 5, 2).toordinal(): (0.5, 4.0), date(2031, 4, 2).toordinal(): (0.5, 2.0)}
    seen, real = [], be.json.loads

    def spy(b, *a, **k):                                             # (a month file's bytes: a parse; the cache's
        if isinstance(b, (bytes, bytearray)):                        # own read comes as text)
            seen.append(1)
        return real(b, *a, **k)
    monkeypatch.setattr(be.json, "loads", spy)
    assert be._ledger(data, KA, True) == first and seen == []        # every month known: none parsed again
    for f in os.listdir(os.path.join(data, "ga4_cube_paid", KA)):    # (a fresh checkout: every mtime new, the bytes
        os.utime(os.path.join(data, "ga4_cube_paid", KA, f), (1, 1))  # the same — still none)
    assert be._ledger(data, KA, True) == first and seen == []
    _cube(data, KA, [("2031-05", {"2031-05-02": {"t": 4_000_000, "loss": 1_000_000}}, None)], hot=False)   # re-folded
    got = be._ledger(data, KA, True)
    assert got[date(2031, 5, 2).toordinal()] == (0.25, 4.0) and got[date(2031, 4, 2).toordinal()] == (0.5, 2.0)
    assert len(seen) == 1                                            # only that month parsed
    month = os.path.join(data, "ga4_cube_paid", KA, "2031-04.json.gz")   # (a re-fold the SAME size: only its bytes
    assert _same_size(month, {"v": 1, "stream_id": "s1", "days": {"2031-04-02": {"t": 2_000_000, "loss": 2_000_000}},
                              "b": {}, "c": {}, "e": {}, "t": {}, "loss": {}})        # tell — the size alone never)
    seen.clear()
    assert be._ledger(data, KA, True)[date(2031, 4, 2).toordinal()] == (1.0, 2.0) and len(seen) == 1
    got = be._ledger(data, KA, True)
    with open(cp, "wb") as f:                                        # a damaged cache: every month parsed once more,
        f.write(b"junk")                                             # the same answer, the cache made again
    seen.clear()
    assert be._ledger(data, KA, True) == got and len(seen) == 2 and be._read(cp)["v"] == be.LEDGER_V
    monkeypatch.setattr(be, "LEDGER_V", be.LEDGER_V + 1)             # (another format: made again)
    seen.clear()
    assert be._ledger(data, KA, True) == got and len(seen) == 2
    _cube(data, KA, [("2031-03", {"2031-03-02": {"t": 2_000_000, "loss": 2_000_000}}, "other-stream")], hot=False)
    assert date(2031, 3, 2).toordinal() not in be._ledger(data, KA, True)   # (another stream's month: still left out)


def _same_size(path, obj):
    """Writes obj as a gzip month file of exactly the byte size the file has now (a compression level, a pad key and a
    gzip name field bring it there) → True, or False when no such form is found."""
    old = os.path.getsize(path)
    for lv in range(9, 0, -1):
        for k in range(0, 24):
            raw = P._raw(dict(obj, pad="x" * (k - 1)) if k else obj)
            for n in range(0, 24):
                buf = io.BytesIO()
                with gzip.GzipFile(filename="n" * n, mode="wb", fileobj=buf, mtime=0, compresslevel=lv) as g:
                    g.write(raw)
                if len(buf.getvalue()) == old:
                    with open(path, "wb") as f:
                        f.write(buf.getvalue())
                    return True
    return False


def test_upi_at_its_thresholds():
    b = (1.0, 0.9, 1.1)                                              # B: median 1.0, q10 0.9, q90 1.1
    x = T.R(n=125, na=100.0)
    assert be._upi(x, b) == [1.25, 1.0]                              # 1.25 × its median, outside q10 … q90
    x.n = 124
    assert be._upi(x, b) is None                                     # 1.24: under 1.25 ×
    x.n = 80
    assert be._upi(x, b) == [0.8, 1.0]                               # 0.8 × (the low side)
    x.n = 81
    assert be._upi(x, b) is None
    assert be._upi(T.R(n=130, na=100.0), (1.0, 0.9, 1.4)) is None    # inside B's own q10 … q90: no mark
    assert be._upi(T.R(n=130, na=0), b) is None and be._upi(T.R(n=130, na=100.0), None) is None


def test_upi_bench_is_k3s_training_set_with_20_days():
    O = date(2031, 1, 31).toordinal()

    def row(X, n, na=100.0, jd=True):
        return T.R(day=X.isoformat(), X=X.toordinal(), n=n, na=na, jd=jd, c=0.1, e=1.0)
    rows = [row(date(2030, 12, 1) + timedelta(days=i), 100 + i) for i in range(20)]
    rows += [row(date(2031, 1, 5), 999),                             # (not settled by O: X + 30 > O)
             row(date(2030, 12, 25), 999, jd=False), row(date(2030, 12, 26), 999, na=0)]   # (not usable / no installs)
    byday = {x.day: {"AA": x} for x in rows}
    got = be._upi_bench(byday, O)["AA"]
    assert got[0] == pytest.approx(1.095) and got[1] == pytest.approx(1.019) and got[2] == pytest.approx(1.171)
    assert be._upi_bench({k: v for k, v in list(byday.items())[:19]}, O) == {}     # 19 days: no benchmark
    assert be._upi_bench(byday, None) == {}


# ── end to end in the step (the made-up Google Ads users' world) ───────────────────────────────────────────────────

def _store(data, side):
    return os.path.join(data, "ga4_nvr_paid" if side == "paid" else "ga4_nvr", KA + ".json.gz")


def _mark(data, side, day, read="c"):
    p = _store(data, side)
    st = P._rd(p)
    st.setdefault("mp", {})[day] = {read: "s"}
    P._wr(p, st)


def _over(data, day, cc, k=2.5):
    """The paid store: country cc's "n" row of `day`, its impressions × k (more than every user's)."""
    p = _store(data, "paid")
    st = P._rd(p)
    st["days"][day]["c"] = [[n, c, rev, int(im * k) if (c == cc and n == "n") else im]
                            for n, c, rev, im in st["days"][day]["c"]]
    P._wr(p, st)


def _all_ecpm(data, day, cc):
    rev = im = 0
    for n, c, r, i in P._rd(_store(data, "all"))["days"][day]["c"]:
        if n == "n" and c == cc:
            rev, im = rev + r, im + i
    return round(round(rev / im * 1000, 5), 3)


def _go(tmp, mp, prep=None, s=None, own=False, fold=None):
    site, data, dash, scr = P.paid_world(tmp, own=own, fold=fold)
    if prep:
        prep(site, data, scr)
    P._state(mp, scr)
    paths, line, err = P._go(dash, data, site, dict({"be_paid": True}, **(s or {})))
    return P._be(site, KA), line, err, data, site


def _days(b):
    return {x["d"]: x for x in b["days"]}


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        return _go(tmp_path_factory.mktemp("dfx_base"), mp)


def test_the_base_world_has_no_round_5_mark_and_no_count(base):
    b, line, err, *_ = base
    assert not any(set(x.get("ckw", "")) & set("gu") or "cku" in x for x in b["days"])
    assert "guard cty" not in line and "gap " not in line and "users/install" not in line and err == ""


def test_a_sampled_c_read_on_a_young_or_final_day_answers_with_every_users_ecpm(tmp_path, monkeypatch, base):
    def prep(site, data, scr):
        _mark(data, "paid", YNG)
        _mark(data, "paid", FIN)
    b, line, err, data, site = _go(tmp_path, monkeypatch, prep)
    days, w = _days(b), _days(base[0])
    scr = os.path.join(os.path.dirname(site), "scratch")
    pk = P._rd(os.path.join(scr, "roi_%s_p00.json.gz" % KA))["c"]
    for day in (YNG, FIN):
        got = {c[0]: c[3] for c in days[day]["cty"]}
        assert got and all(got[cc] == _all_ecpm(data, day, cc) for cc in got), day      # every country: every user's
        assert all(abs(c[3] - _all_ecpm(data, day, c[0]) * 1.2) < 0.01 for c in w[day]["cty"]), day   # (was 1.2 ×)
        assert days[day]["ckw"] == "f" and set(got) <= set(days[day]["ckc"]), day       # each row tagged …
        assert set(days[day]["ckc"].values()) == {"f"}, day                              # … with "f" only
    fa = P._rd(_store(data, "all"))["days"]                          # (a pack row every user's read has a cell of:
    rows = [(q[0], cc) for cc, rows in pk.items() if cc not in be.SKIP_CC for q in rows   # replaced; none: no
            if q[0] in (YNG, FIN) and len(q) >= 14 and q[3] and q[3] > 0]               # decision, a ref skip)
    n = sum(1 for d, cc in rows if sum(r[3] for r in fa[d]["c"] if r[0] == "n" and r[1] == cc) > 0)
    assert 0 < n < len(rows) and ", ref skip %d, guard cty %d (sampled %d, over 0)" % (len(rows) - n, n, n) in line
    assert "guard fs" not in line and err == ""
    with open(os.path.join(data, "be_tab", be.FSQ_FILE), encoding="utf-8") as f:
        assert json.load(f)["days"] == {}                          # never on the re-read list (young or final)
    assert not any(x.get("ckw") for d, x in days.items() if d not in (YNG, FIN))


def test_every_users_own_sampled_c_read_decides_nothing(tmp_path, monkeypatch):
    def prep(site, data, scr):
        _mark(data, "paid", YNG)
        _mark(data, "all", YNG)                                    # every user's "c" read sampled too: no reference
    b, line, *_ = _go(tmp_path, monkeypatch, prep)
    assert "ckw" not in _days(b)[YNG] and "guard cty" not in line
    def prep2(site, data, scr):                                     # every user's OTHER read sampled: whole "c" — decides
        _mark(data, "paid", YNG)
        _mark(data, "all", YNG, "u")
    b, line, *_ = _go(tmp_path / "u", monkeypatch, prep2)
    assert _days(b)[YNG]["ckw"] == "f" and ", guard cty " in line


def test_a_cell_over_every_users_replaces_only_that_country_and_only_up_to_newest_minus_two(tmp_path, monkeypatch, base):
    def prep(site, data, scr):
        _over(data, YNG, "AA")
        _over(data, NEW, "AA")                                      # (newer than newest − FSQ_YOUNG: never judged)
    b, line, err, data, _ = _go(tmp_path, monkeypatch, prep)
    day, w = _days(b), _days(base[0])
    got = {c[0]: c[3] for c in day[YNG]["cty"]}
    assert got["AA"] == _all_ecpm(data, YNG, "AA") and day[YNG]["ckc"] == {"AA": "f"}
    assert all(got[cc] == c for cc, c in ((c[0], c[3]) for c in w[YNG]["cty"]) if cc != "AA")
    assert "ckw" not in day[NEW] and ", guard cty 1 (sampled 0, over 1)" in line and err == ""


def test_fs_doubt_is_a_whole_day_ratio_off_its_own_median():
    D = ["2030-01-%02d" % i for i in range(1, 21)]
    fc = {"AA": {d: [10.0, 1000] for d in D}, "BB": {d: [1.0, 100] for d in D}}   # every user's cells
    fp = {"AA": {d: [5.0, 500] for d in D}, "BB": {d: [0.5, 50] for d in D}}      # the subset at 0.5 of them
    fp["AA"]["2030-01-18"] = [5.0, 527.5]                                       # the day's ratio 1.05 × its median:
    assert be._fs_doubt(fp, fc) == {"2030-01-18"}                               # in doubt
    fp["AA"]["2030-01-18"] = [5.0, 527]                                         # under it: not
    assert be._fs_doubt(fp, fc) == set()
    fp["AA"]["2030-01-18"], fp["BB"]["2030-01-18"] = [5.0, 500], [9.0, 900]    # (one cell over every user's never votes:
    assert be._fs_doubt(fp, fc) == set()                                        # the day is not in doubt — whole-day
    assert (500 + 900) / 1100 >= 1.05 * 0.5                                     # it would have been)
    fp["AA"]["2030-01-05"] = fp["AA"]["2030-01-08"] = [5.0, 600]                # (4 days before it: no claim; 7: judged)
    assert be._fs_doubt(fp, fc) == {"2030-01-08"}
    del fc["AA"]["2030-01-08"]                                                  # (BB alone that day: its normal ratio)
    assert be._fs_doubt(fp, fc) == set()


def test_a_sampled_day_never_replaces_a_country_every_user_has_no_cell_of(tmp_path, monkeypatch, base):
    def prep(site, data, scr):                                      # every user's read without AA that day (folded
        p = _store(data, "all")                                     # into "(other)" on the bigger read), the paid
        st = P._rd(p)                                               # read of the day sampled
        st["days"][YNG]["c"] = [r for r in st["days"][YNG]["c"] if r[1] != "AA"]
        P._wr(p, st)
        _mark(data, "paid", YNG)
    b, line, err, *_ = _go(tmp_path, monkeypatch, prep)
    day, w = _days(b)[YNG], _days(base[0])[YNG]
    assert "AA" not in day["ckc"] and {c[0]: c[3] for c in day["cty"]}["AA"] == {c[0]: c[3] for c in w["cty"]}["AA"]
    assert set(day["ckc"].values()) == {"f"} and ", ref skip 1" in line   # (its own read kept; the others: every
    assert "(sampled %d, over 0)" % len(day["ckc"]) in line and err == ""  # user's — no decision only for AA)


def test_a_final_share_broken_read_keeps_round_4s_path_on_a_sampled_day(tmp_path, monkeypatch):
    def prep(site, data, scr):
        FG._scale_nvr(data, FG.D, 0.45, "AA")                       # AA's final read broken against its day-0 cohort …
        _mark(data, "paid", FG.D)                                   # … on a day GA4 also sampled
    b, line, err, data, _ = _go(tmp_path, monkeypatch, prep)
    day = _days(b)[FG.D]
    assert day["ckc"]["AA"] == "f" and ", guard fs 1 (left 0)" in line   # round 4's path: a final break, counted …
    assert FG._fsq_list(data) == {KA: [FG.D]}                       # … and on the re-read list
    assert "(sampled %d, over 0)" % (len(day["ckc"]) - 1) in line and err == ""   # (the day's others: the sampled rule)


def test_users_per_install_is_judged_on_rows_from_2_days_old(tmp_path, monkeypatch):
    D1, D2 = ((T.TODAY - timedelta(days=k)).isoformat() for k in (1, 2))
    b, line, err, *_ = _go(tmp_path, monkeypatch, lambda s, d, scr: (_users(scr, D1, "AA", 1.6), _users(scr, D2, "AA", 1.6)))
    days = _days(b)
    assert {c[0]: c for c in days[D1]["cty"]}["AA"][11] == 0         # (a forecast row: its installs
    assert "u" not in (days[D1].get("ckc") or {}).get("AA", "")     # still settling — no mark yet)
    assert "u" in days[D2]["ckc"]["AA"] and err == ""


def _short_all(data, day, k=0.8):
    """Every user's store: the whole day's first-session impressions × k (their read of the day short)."""
    p = _store(data, "all")
    st = P._rd(p)
    st["days"][day]["c"] = [[n, c, rev, int(im * k) if n == "n" else im] for n, c, rev, im in st["days"][day]["c"]]
    P._wr(p, st)


def test_an_over_cell_on_a_day_every_users_whole_read_is_in_doubt_decides_nothing(tmp_path, monkeypatch, base):
    def prep(site, data, scr):
        _short_all(data, YNG)                                       # every user's whole day short: the subset's share
        _over(data, YNG, "AA")                                      # of it jumps — the over rule says nothing there
    b, line, err, *_ = _go(tmp_path, monkeypatch, prep)
    day = _days(b)[YNG]
    assert "AA" not in (day.get("ckc") or {}) and "guard cty" not in line and ", ref skip 1" in line and err == ""
    assert {c[0]: c[3] for c in day["cty"]}["AA"] != {c[0]: c[3] for c in _days(base[0])[YNG]["cty"]}["AA"]   # (its
    #                                                                 own over read stays: nothing replaced it)


def test_a_paid_cell_every_user_has_none_of_decides_nothing(tmp_path, monkeypatch):
    def prep(site, data, scr):                                      # every user's read without AA that day (folded
        p = _store(data, "all")                                     # into "(other)" on the bigger read), the paid
        st = P._rd(p)                                               # read with AA well over it
        st["days"][YNG]["c"] = [r for r in st["days"][YNG]["c"] if r[1] != "AA"]
        P._wr(p, st)
        _over(data, YNG, "AA")
    b, line, err, *_ = _go(tmp_path, monkeypatch, prep)
    assert "AA" not in (_days(b)[YNG].get("ckc") or {}) and "guard cty" not in line and err == ""


def test_fsc_off_or_the_guard_off_is_round_4(tmp_path, monkeypatch, base):
    for s in ({"be_fsc": False}, {"be_fsq": False}):
        b, line, *_ = _go(tmp_path / list(s)[0], monkeypatch, lambda si, d, sc: _mark(d, "paid", YNG), s)
        assert "ckw" not in _days(b)[YNG] and "guard cty" not in line, s
        assert [c[3] for c in _days(b)[YNG]["cty"]] == [c[3] for c in _days(base[0])[YNG]["cty"]], s
    assert be.FSC_ON is True and be.GAP_ON is True and be.UPI_ON is True    # (the module's own switches untouched)


def test_the_caches_stamp_carries_fsc_and_a_flip_makes_them_again(tmp_path, monkeypatch):
    site, data, dash, scr = P.paid_world(tmp_path)
    P._state(monkeypatch, scr)
    P._go(dash, data, site, {"be_paid": True})
    fp, cp = os.path.join(data, "be_tab", "fitsp_%s.json.gz" % KA), os.path.join(data, "be_tab", be.CALIB_P)
    assert P._rd(fp)["fq"] == "%d+fsc%d" % (be.FSQ_V, be.FSC_V)
    with open(cp, encoding="utf-8") as f:
        assert json.load(f)["fq"] == "%d+fsc%d" % (be.FSQ_V, be.FSC_V)
    _, line, _ = P._go(dash, data, site, {"be_paid": True, "be_fsc": False}, T.NOW + timedelta(hours=1))
    assert "refit yes" in line and ", calib p yes" in line and P._rd(fp)["fq"] == be.FSQ_V   # (round 4's own stamp)


def _gap_pack_rows(scr, D, k):
    """The paid pack: every country row's revenue of activity date D × k (the paid cube folded it short)."""
    p = os.path.join(scr, "roi_%s_p00.json.gz" % KA)
    pk = P._rd(p)
    pk["c"] = {cc: [P._fold(q, D, k) if len(q) > 4 and q[4] else q for q in rows] for cc, rows in pk["c"].items()}
    P._wr(p, pk)


def test_a_packs_share_falling_from_its_own_level_is_a_gap_and_marks_the_rows_holding_it(tmp_path, monkeypatch, base):
    b, line, err, data, _ = _go(tmp_path, monkeypatch, lambda s, d, scr: _gap_pack_rows(scr, GAPD, 0.5), own=True)
    days = _days(b)
    hit = {d: set(x.get("ckc", {})) for d, x in days.items() if "g" in x.get("ckw", "")}
    assert hit and all(date.fromisoformat(d) <= GAPD for d in hit)       # only days whose cells hold the date …
    for d, ccs in hit.items():
        x = days[d]
        assert all("g" in x["ckc"][cc] for cc in ccs)
        assert {c[0] for c in x["cty"] if c[11] == 0 and c[1] >= be.SAN_SHARE} == ccs, d   # … every forecast row ≥ 5 %
        assert x["chk"] == 1
    assert ", gap rows %d (recent " % sum(len(v) for v in hit.values()) in line and ", gap dates rel 1 ledger 0" in line
    young = (GAPD + timedelta(days=2)).isoformat()                         # (a day installed after it: none)
    assert "g" not in days[young].get("ckw", "") and err == ""
    short = [d for d, x in days.items() if date.fromisoformat(d) <= GAPD and x.get("now") and x["now"][0] == "no"
             and x["now"][1] is not None and date.fromisoformat(d) + timedelta(days=x["now"][1]) < GAPD]
    assert short and not any(d in hit for d in short)                     # (its cells so far end before the date: none)
    b0, line0, *_ = _go(tmp_path / "off", monkeypatch, lambda s, d, scr: _gap_pack_rows(scr, GAPD, 0.5),
                        {"be_gap": False}, own=True)
    assert not any("g" in x.get("ckw", "") for x in b0["days"]) and "gap " not in line0
    w = _days(b0)
    assert all(days[d]["cty"] == w[d]["cty"] for d in days)               # (information only: no number moved)
    cards = [x["card"]["chk"] for x in b["days"] if x.get("card")]
    cards0 = [x["card"]["chk"] for x in b0["days"] if x.get("card")]
    assert cards != cards0 and sum(map(sum, cards)) > sum(map(sum, cards0))   # (the card's own marks gain the date)


def test_round_5_marks_only_rows_with_san_share_of_their_day(tmp_path, monkeypatch):
    monkeypatch.setattr(be, "SAN_SHARE", 0.6)                         # (every covered country here is under 60 %)
    D = (T.TODAY - timedelta(days=10)).isoformat()

    def prep(site, data, scr):
        _gap_pack_rows(scr, GAPD, 0.5)
        _users(scr, D, "AA", 1.6)
    b, line, err, *_ = _go(tmp_path, monkeypatch, prep, own=True)
    assert not any(set(x.get("ckw", "")) & set("gu") for x in b["days"])
    assert ", gap rows 0 (recent 0), gap dates rel 1 ledger 0" in line and "users/install" not in line   # (the date
    #                                                                       itself is still a gap: the cards)


def test_a_cube_ledger_loss_of_40_percent_is_a_gap(tmp_path, monkeypatch):
    D = GAPD.isoformat()

    def prep(site, data, scr):
        _cube(data, KA, [(D[:7], {D: {"t": 50_000_000, "loss": 20_000_000}}, None)])     # 0.4 of the day "(other)"
    b, line, err, *_ = _go(tmp_path, monkeypatch, prep)
    assert any("g" in x.get("ckw", "") for x in b["days"]) and ", gap dates rel 0 ledger 1" in line and err == ""

    def prep2(site, data, scr):
        _cube(data, KA, [(D[:7], {D: {"t": 50_000_000, "loss": 19_000_000}}, None)])     # 0.38: not
    b, line, *_ = _go(tmp_path / "under", monkeypatch, prep2)
    assert not any("g" in x.get("ckw", "") for x in b["days"]) and "gap " not in line


def test_a_failing_ledger_read_costs_only_the_ledger(tmp_path, monkeypatch, base):
    def prep(site, data, scr):
        d = os.path.join(data, "ga4_cube_paid", KA)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, GAPD.isoformat()[:7] + ".json.gz"), "wb") as f:
            f.write(b"not a gzip")
    b, line, err, *_ = _go(tmp_path, monkeypatch, prep)
    assert len(b["days"]) == len(base[0]["days"]) and ", gap fail 1" in line and "be gap skipped: BadGzipFile\n" in err


def _users(scr, day, cc, k):
    p = os.path.join(scr, "roi_%s_p00.json.gz" % KA)
    pk = P._rd(p)
    for q in pk["c"][cc]:
        if q[0] == day:
            q[1] = int(q[1] * k)
    P._wr(p, pk)


def test_users_per_install_off_bs_basis_marks_a_forecast_row_with_both_numbers(tmp_path, monkeypatch, base):
    D = (T.TODAY - timedelta(days=10)).isoformat()
    b, line, err, *_ = _go(tmp_path, monkeypatch, lambda s, d, scr: _users(scr, D, "AA", 1.6))
    x = _days(b)[D]
    assert x["ckw"] == "u" and x["ckc"] == {"AA": "u"} and list(x["cku"]) == ["AA"]
    u, bu = x["cku"]["AA"][:2]
    assert x["cku"]["AA"][2:] == [1]                                      # (src "p": these are Google Ads users)
    assert u == pytest.approx(1.6 * bu, abs=0.02) and ", users/install 1 (recent 1)" in line and err == ""
    assert x["cty"] == _days(base[0])[D]["cty"]                           # (no number moved)
    b2, line2, *_ = _go(tmp_path / "lo", monkeypatch, lambda s, d, scr: _users(scr, D, "AA", 0.7))
    assert _days(b2)[D]["ckc"] == {"AA": "u"} and _days(b2)[D]["cku"]["AA"][0] < _days(b2)[D]["cku"]["AA"][1]
    b3, line3, *_ = _go(tmp_path / "in", monkeypatch, lambda s, d, scr: _users(scr, D, "AA", 1.2))
    assert "ckw" not in _days(b3)[D] and "users/install" not in line3          # (1.2 ×: under 1.25 ×)
    b4, line4, *_ = _go(tmp_path / "off", monkeypatch, lambda s, d, scr: _users(scr, D, "AA", 1.6), {"be_upi": False})
    assert "ckw" not in _days(b4)[D] and "users/install" not in line4


def test_a_broken_even_row_is_never_marked_u(tmp_path, monkeypatch, base):
    D = next(x["d"] for x in base[0]["days"] for c in x["cty"] if c[0] == "AA" and c[11] in (1, 2, 3))   # (it broke even)
    b, line, *_ = _go(tmp_path, monkeypatch, lambda s, d, scr: _users(scr, D, "AA", 1.6))
    assert "u" not in _days(b)[D].get("ckw", "") and "users/install" not in line


# ── ⚖️ the countries table's "ROAS so far" (RSF) ─────────────────────────────────────────────────────────────────────

BX = [0.3, 0.35, 0.4, 0.42, 0.46, 0.54, 0.67]                     # a made-up benchmark at the ages 0 1 2 3 6 13 30


def test_bench_at_reads_a_curve_age_linear_between_two_and_none_past_its_limit():
    ages = [0, 1, 2, 3, 6, 13, 30]
    assert be._bench_at(ages, BX, 6) == 0.46 and be._bench_at(ages, BX, 0) == 0.3 and be._bench_at(ages, BX, 30) == 0.67
    assert be._bench_at(ages, BX, 10) == pytest.approx(0.46 + 0.08 * 4 / 7)       # between 6 and 13: linear
    assert be._bench_at(ages, BX, 7) == pytest.approx(0.46 + 0.08 / 7)
    assert be._bench_at(ages, BX, 31) is None                                     # past the ages B's data watched
    hole = [0.3, None] + BX[2:]                                                   # an entry without a median: none
    assert be._bench_at(ages, hole, 1) is None and be._bench_at(ages, [0.3, 0.35, None] + BX[3:], 1.5) is None
    assert be._bench_at(ages, hole, 2) == 0.4                                     # (only at it / next to it)
    assert be._bench_at(ages, BX, None) is None and be._bench_at([], [], 3) is None
    assert be._bench_at([3, 6], [0.42, 0.46], 1) is None                          # (before its first age)


def test_r3_rounds_to_3_places_and_never_to_100_percent_under_it():
    assert be._r3(0.81449) == 0.814 and be._r3(0.8145) in (0.814, 0.815) and be._r3(1.23456) == 1.235
    assert be._r3(0.9996) == 0.999 and be._r3(0.99949) == 0.999 and be._r3(1.0) == 1.0 and be._r3(None) is None


def test_rsf_is_the_rows_so_far_read_against_bs_median_at_the_same_age():
    cf = [[e[0], [e[1][0] + math.log(2.0), 0.0, 0.0]] + e[2:] for e in T._up_fits()["AA"]["cv"]]   # rmed = log of T.UP at
    ages = [be.GRID[e[0]] for e in cf]                                           # the 13 grid ages; the model 2 × it (B is
    #                                                                              the past median, never the model)
    x = T.R(day="2030-12-20", sp=100.0, na=50.0, sfa=10, sfv=73.6)
    b10 = round(T.UP[4] + (T.UP[5] - T.UP[4]) * 4 / 7, 3)                         # day 10: between day 6 and day 13
    assert be._rsf(x, ages, cf) == [10, 0.736, b10]
    x.sfa = 13
    assert be._rsf(x, ages, cf) == [13, 0.736, T.UP[5]]                           # a grid age: B's own there
    x.sfa = ages[-1] + 5
    assert be._rsf(x, ages, cf) == [ages[-1] + 5, 0.736, None]                    # past B's watched ages: none
    x.sfa, x.sfv = 6, 99.96                                                      # never "100.0 %" under 100 % (_r3)
    assert be._rsf(x, ages, cf) == [6, 0.999, T.UP[4]]
    x.sfv = 81.449
    assert be._rsf(x, ages, cf) == [6, 0.814, T.UP[4]]                            # 3 places: the page's 0.1 %
    x.sfv = 250.0
    assert be._rsf(x, ages, cf) == [6, 2.5, T.UP[4]]
    assert be._rsf(T.R(day="2030-12-20", sp=100.0, na=50.0, sfa=None, sfv=None), ages, cf) is None   # no so-far read
    assert be._rsf(T.R(day="2030-12-20", sp=0.0, na=50.0, sfa=3, sfv=1.0), ages, cf) is None
    old = [e[:5] for e in cf]                                                     # a fits cache without rmed: no B
    assert be._rsf(T.R(day="2030-12-20", sp=100.0, na=50.0, sfa=6, sfv=40.0), ages, old) == [6, 0.4, None]


def test_every_country_row_gets_its_roas_so_far_and_off_leaves_the_row_as_before(monkeypatch):
    day = "2030-12-20"
    cs = {"AA": T.R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0), sfa=10, sfv=73.6)}
    app = T.R(day=day, sp=100.0, na=50.0, obs=10, oc=73.6)
    row = T._one(T._up_fits(), T.CAL0, app, cs, day=day)["cty"][0]
    assert len(row) == 14 and row[13] == [10, 0.736, round(T.UP[4] + (T.UP[5] - T.UP[4]) * 4 / 7, 3)]
    nos = {"AA": T.R(day=day, sp=100.0, na=50.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0), sfa=None, sfv=None)}
    assert T._one(T._up_fits(), T.CAL0, app, nos, day=day)["cty"][0][13] is None   # no so-far read: null, the row kept
    monkeypatch.setattr(be, "RSF_ON", False)
    assert T._one(T._up_fits(), T.CAL0, app, cs, day=day)["cty"][0] == row[:13]   # off: the row as before it


def test_the_steps_rows_read_b_up_to_their_own_limit(base):
    b = base[0]
    rows = [c for x in b["days"] for c in x.get("cty") or []]
    assert rows and all(len(c) == 14 for c in rows)
    seen = 0
    for x in b["days"]:
        for c in x.get("cty") or []:
            rs = c[13]
            if rs is None:
                continue
            seen += 1
            assert isinstance(rs[0], int) and 0 <= rs[0] <= x["age"] and rs[1] >= 0
            assert (rs[2] is None) == (rs[0] > c[10])                             # B: up to the curve's own limit only
    assert seen > 0


def test_the_switch_off_in_the_step_leaves_every_row_without_it(tmp_path, monkeypatch, base):
    b, line, err, *_ = _go(tmp_path / "off", monkeypatch, None, {"be_rsf": False})
    rows = [c for x in b["days"] for c in x.get("cty") or []]
    assert rows and all(len(c) == 13 for c in rows) and err == ""
    on = {x["d"]: x for x in base[0]["days"]}
    for x in b["days"]:
        assert [c[:13] for c in on[x["d"]].get("cty") or []] == x.get("cty", [])   # (nothing else moves)


# ── all four off: every output byte for byte as the build before them ──────────────────────────────────────────────

def three_world(tmp, mp):
    """One world that trips all three: a young day's sampled "c" read and a cell over every user's (FSC), a date the
    paid cube folded to half with the All rows whole (GAP), a forecast row with 1.6 × B's users per install (UPI)."""
    def prep(site, data, scr):
        _mark(data, "paid", YNG)
        _over(data, (T.TODAY - timedelta(days=5)).isoformat(), "BB")
        _gap_pack_rows(scr, GAPD, 0.5)
        _users(scr, (T.TODAY - timedelta(days=10)).isoformat(), "AA", 1.6)
    site, data, dash, scr = P.paid_world(tmp, own=True)
    prep(site, data, scr)
    P._state(mp, scr)
    return site, data, dash


def three_digests(tmp, mp, s):
    """three_world through the step twice (a build, and a second one an hour later) → the two digests."""
    site, data, dash = three_world(tmp, mp)
    out = []
    for h in (0, 1):
        paths, line, err = P._go(dash, data, site, dict({"be_paid": True}, **s), T.NOW + timedelta(hours=h))
        out.append(P._digest(site, data, dash, paths, line, err))
    return out


# sha256 (tests/test_be_paid._digest) of three_world's two steps — worked out once with 60cd202's admob_iq (the commit
# this branch starts from: loaded in place of this tree's, these same worlds and helpers) at the tests' GA4_FINAL_DAYS
THREE_BEFORE = ["c8698c0c65b71f745efb16c830f345ee9a2422f08e013b55cb075257dfd04fc2",
                "460c13a030d7b7ef602a815129b42936589ec7ec62e7bb91b773933cb5c1d822"]


def test_all_four_off_every_output_byte_for_byte_as_before_them(tmp_path, monkeypatch):
    if be.LAG != be.LAG0:
        pytest.skip("the digests were worked out at the tests' GA4_FINAL_DAYS (3)")
    off = three_digests(tmp_path / "off", monkeypatch, {"be_fsc": False, "be_gap": False, "be_upi": False, "be_rsf": False})
    assert off == THREE_BEFORE
    on = three_digests(tmp_path / "on", monkeypatch, {})
    assert on[0] != off[0]                                                 # (the world trips them: on is not off)


@pytest.mark.parametrize("v,want", [(None, True), ("", True), ("true", True), ("false", False), (" 0", False),
                                    ("off", False), ("No", False)])
def test_the_four_switches_turn_off_on_every_usual_spelling(monkeypatch, v, want):
    from admob_iq import config
    for name, k in (("BE_FSC", "be_fsc"), ("BE_GAP", "be_gap"), ("BE_UPI", "be_upi"), ("BE_RSF", "be_rsf")):
        if v is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, v)
        assert config.settings()[k] is want, (name, v)


def test_the_workflow_passes_the_four_switches_on_by_default():
    with open(os.path.join(T.ROOT, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        y = f.read()
    for name in ("BE_FSC", "BE_GAP", "BE_UPI", "BE_RSF"):
        assert "%s:               ${{ vars.%s || 'true' }}" % (name, name) in y, name
