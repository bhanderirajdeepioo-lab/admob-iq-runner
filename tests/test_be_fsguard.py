"""⚖️ Breakeven — the INPUT GUARD of the Google Ads users' source (admob_iq.be_build, src "p"; owner, 20 Nov 2026: "haan
fix shuru karo", "aage se ye na ho US vala galti") on made-up apps (tests/test_be_paid.py's world): the two reads of the
same users that must agree — their share of every user's first-session revenue and their share of the install day's
day-0 cohort revenue — at the thresholds (fs_bad / coh_bad: on and off at FSQ, the $ floors, every user's $1, a
paid share of 1); a day whose first-session read broke (every country's) answers with every user's eCPM_fs, its own
country cells only when only one country's broke, and carries the page's "data check" with its reason ("ckw" "f"); a
broken day-0 read is marked ("c") and changes nothing; the re-read list for the paid first-session store; the health
line only for a broken day of the last FSQ_WIN days whose re-reads are used up (or a broken day-0 read there), once a
build, the counts line counts only; with the guard off every file as before it. The OUTPUT sanity check (_sus): the
benchmark-growth day, its thresholds, a flagged country row marking its day ("ckw" "s", counted; its numbers
unchanged; never the banner), an app-line row counted, never marked, a country row under SAN_SHARE never judged.
SYNTHETIC values only (apps "app~synth-…", countries AA … DH, the calendar 2030–2031)."""
import gzip
import json
import math
import os
from datetime import timedelta

import pytest

from admob_iq import be_build as be
from admob_iq.fetch import ga4_uninstall as gu
from tests import test_be_build as T
from tests import test_be_paid as P

KA = P.KA
D = (T.TODAY - timedelta(days=10)).isoformat()          # the broken install day (final, within the health window)


# ── the thresholds ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_fs_bad_at_its_thresholds():
    # cohort share 0.5 (50 of 100), every user's first-session revenue 40 → expected paid first session 20
    assert be.fs_bad(11.9, 40.0, 50.0, 100.0)                        # 0.2975 < 0.6 × 0.5
    assert not be.fs_bad(12.0, 40.0, 50.0, 100.0)                    # 0.30 = 0.6 × 0.5: not under
    assert not be.fs_bad(1.0, 9.9, 50.0, 100.0)                      # expected 4.95 < $5 (the app line's floor)
    assert be.fs_bad(1.0, 10.0, 50.0, 100.0)                         # expected 5.00: judged
    assert not be.fs_bad(1.0, 19.9, 50.0, 100.0, be.FSQ_EC)          # a country's floor $10
    assert be.fs_bad(1.0, 20.0, 50.0, 100.0, be.FSQ_EC)
    assert not be.fs_bad(0.0, 0.99, 100.0, 100.0, 0.0)               # every user's under $1: nothing said
    assert be.fs_bad(0.0, 1.0, 100.0, 100.0, 0.0)
    assert be.fs_bad(50.0, 100.0, 300.0, 100.0)                      # a paid day 0 above every user's: share capped at 1
    assert not be.fs_bad(61.0, 100.0, 300.0, 100.0)
    assert be.fs_bad(None, 40.0, 50.0, 100.0)                        # no paid first-session revenue at all: broken
    assert not be.fs_bad(1.0, 40.0, None, 100.0) and not be.fs_bad(1.0, 40.0, 50.0, 0.0)


def test_coh_bad_at_its_thresholds():
    # first-session share 0.5 (20 of 40), every user's day 0 100 → expected paid day 0 50
    assert be.coh_bad(20.0, 40.0, 29.9, 100.0) and not be.coh_bad(20.0, 40.0, 30.0, 100.0)
    assert not be.coh_bad(20.0, 40.0, 0.0, 9.9) and be.coh_bad(20.0, 40.0, 0.0, 10.0)   # expected paid day 0 ≥ $5
    assert not be.coh_bad(20.0, 0.99, 0.0, 100.0)                    # every user's first session under $1
    assert not be.coh_bad(0.0, 40.0, 0.0, 100.0)                     # no paid first session: fs_bad's side, not this
    assert be.coh_bad(80.0, 40.0, 59.0, 100.0) and not be.coh_bad(80.0, 40.0, 60.0, 100.0)   # share capped at 1


# ── the guard in the build ──────────────────────────────────────────────────────────────────────────────────────────

def _scale_nvr(data, day, k, cc=None):
    """The paid first-session store: day's "c" rows (one country's, or all) × k (a broken read)."""
    p = os.path.join(data, "ga4_nvr_paid", KA + ".json.gz")
    st = P._rd(p)
    st["days"][day]["c"] = [[n, c, round(rev * k, 6) if cc in (None, c) else rev, im]
                            for n, c, rev, im in st["days"][day]["c"]]
    P._wr(p, st)


def _all_ecpm(data, day):
    st = P._rd(os.path.join(data, "ga4_nvr", KA + ".json.gz"))
    out = {}
    for n, cc, rev, im in st["days"][day]["c"]:
        if n == "n":
            e = out.setdefault(cc, [0.0, 0])
            e[0] += rev
            e[1] += im
    return {cc: round(v[0] / v[1] * 1000, 3) for cc, v in out.items() if v[1]}


def _run(tmp, mp, prep=None, s=None):
    site, data, dash, scr = P.paid_world(tmp)
    if prep:
        prep(site, data, scr)
    P._state(mp, scr)
    paths, line, err = P._go(dash, data, site, dict({"be_paid": True}, **(s or {})))
    return P._be(site, KA), line, err, data


@pytest.fixture(scope="module")
def whole(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        return _run(tmp_path_factory.mktemp("fsq_whole"), mp)


def test_a_whole_world_has_no_mark_no_count_no_health_line(whole):
    b, line, err, data = whole
    assert b["src"] == "p" and err == ""
    assert not any("ckw" in d for d in b["days"]) and "guard" not in line and "check" not in line
    with open(os.path.join(data, "be_tab", be.FSQ_FILE), encoding="utf-8") as f:
        assert json.load(f) == {"v": be.V, "days": {}}               # (the re-read list: nothing)


def test_a_broken_first_session_day_answers_with_every_users_ecpm_and_says_why(tmp_path, monkeypatch, whole):
    b, line, err, data = _run(tmp_path, monkeypatch, lambda s, d, c: _scale_nvr(d, D, 0.2))
    day = {x["d"]: x for x in b["days"]}[D]
    want = _all_ecpm(data, D)
    got = {c[0]: c[3] for c in day["cty"]}
    assert got and all(got[cc] == want[cc] for cc in got)            # every country: every user's eCPM_fs that day
    assert day["chk"] == 1 and day["ckw"] == "f"                     # the page's "data check", its reason
    w = {x["d"]: x for x in whole[0]["days"]}
    assert all(abs(c[3] - 1.2 * want[c[0]]) < 0.01 for c in w[D]["cty"])     # (unbroken: their own, 1.2 × every user's)
    other = [x for x in b["days"] if x["d"] != D]
    assert not any("ckw" in x for x in other)                         # no other day marked …
    for x in other:                                                   # … and every other day's eCPM_fs its own
        assert [c[3] for c in x["cty"]] == [c[3] for c in w[x["d"]]["cty"]], x["d"]
    assert ", guard fs 1 (left 0), cohort 0 (recent 0)" in line and err == ""   # (re-reads not used up: no banner)
    with open(os.path.join(data, "be_tab", be.FSQ_FILE), encoding="utf-8") as f:
        assert json.load(f) == {"v": be.V, "days": {KA: [D]}}         # handed to the paid store's re-read


def test_one_countrys_broken_read_replaces_only_that_country(tmp_path, monkeypatch, whole):
    b, line, err, data = _run(tmp_path, monkeypatch, lambda s, d, c: _scale_nvr(d, D, 0.45, "AA"))
    day = {x["d"]: x for x in b["days"]}[D]
    w = {c[0]: c[3] for c in {x["d"]: x for x in whole[0]["days"]}[D]["cty"]}
    got = {c[0]: c[3] for c in day["cty"]}
    assert got["AA"] == _all_ecpm(data, D)["AA"]                     # AA: every user's
    assert all(got[cc] == w[cc] for cc in got if cc != "AA")          # the others: their own
    assert day["ckw"] == "f" and ", guard fs 1 " in line


def _fsq_list(data):
    with open(os.path.join(data, "be_tab", be.FSQ_FILE), encoding="utf-8") as f:
        return json.load(f)["days"]


def test_the_finality_gate_boundary_and_a_young_day(tmp_path, monkeypatch):
    """Final: install day ≤ both newest − max(LAG, the first-session stores' own lag). The day after it is YOUNG: the
    whole-day first-session rule still marks it ("f", replaced) — counted "young", never on the re-read list."""
    lag = max(be.LAG, be.gv.FINAL_LAG)
    edge = (T.TODAY - timedelta(days=lag)).isoformat()
    young = (T.TODAY - timedelta(days=lag - 1)).isoformat()
    newest2 = (T.TODAY - timedelta(days=be.FSQ_YOUNG - 1)).isoformat()      # (too young even for that)

    def prep(site, data, scr):
        for d in (edge, young, newest2):
            _scale_nvr(data, d, 0.2)
    b, line, err, data = _run(tmp_path, monkeypatch, prep)
    days = {x["d"]: x for x in b["days"]}
    want = _all_ecpm(data, young)
    assert days[edge].get("ckw") == "f" and days[young].get("ckw") == "f" and "ckw" not in days[newest2]
    assert all(c[3] == want[c[0]] for c in days[young]["cty"])               # (young: the whole day replaced)
    assert ", guard fs 1 " in line and ", young 1" in line and err == ""
    assert _fsq_list(data) == {KA: [edge]}                                   # (the list: final days only)


def test_a_young_day_never_raises_the_banner_and_never_judges_a_country_or_the_cohort(tmp_path, monkeypatch):
    young = (T.TODAY - timedelta(days=be.FSQ_YOUNG)).isoformat()
    whole = (T.TODAY - timedelta(days=max(be.LAG, be.gv.FINAL_LAG) - 1)).isoformat()   # (young too: its re-reads
    #                                                                                   used up never count)

    def prep(site, data, scr):
        _scale_nvr(data, young, 0.45, "AA")                                  # one country only: not the whole day
        p = os.path.join(data, "ga4_nvr_paid", KA + ".json.gz")
        st = P._rd(p)
        st["rq"] = {young: [be.FSQ_TRIES, "2031-06-01T00:00:00Z"], whole: [be.FSQ_TRIES, "2031-06-01T00:00:00Z"]}
        P._wr(p, st)
        _scale_nvr(data, whole, 0.2)
        q = os.path.join(scr, "roi_%s_p.json.gz" % KA)                       # … and its paid day 0 near-empty
        f = P._rd(q)
        for r in f["rows"]:
            if r[0] == young:
                r[4] = [round(v * 0.1, 6) for v in r[4]]
        P._wr(q, f)
    b, line, err, _ = _run(tmp_path, monkeypatch, prep)
    day = {x["d"]: x for x in b["days"]}[young]
    assert "ckw" not in day and "guard" not in line and err == ""            # (a country / the cohort: not young)
    assert {x["d"]: x for x in b["days"]}[whole].get("ckw") == "f" and ", young 1" in line   # (the whole day: marked,
    #                                                                          its used-up re-reads no banner)


def test_a_day_0_cell_not_final_is_judged_as_a_young_day(tmp_path, monkeypatch):
    """An All row's day 0 not final (df 0) in either file: that day is not final — the app line's whole-day rule on
    the cells as they are ("young", not on the list); a country is judged on its own pack rows (final there)."""
    for side in ("paid", "all"):
        def prep(site, data, scr, side=side):
            _scale_nvr(data, D, 0.2)
            p = os.path.join(scr, "roi_%s_p.json.gz" % KA) if side == "paid" else os.path.join(site, "roi_%s.json.gz" % KA)
            f = P._rd(p)
            for r in f["rows"]:
                if r[0] == D:
                    r[5] = 0
            P._wr(p, f)
        b, line, err, data = _run(tmp_path / side, monkeypatch, prep)
        day = {x["d"]: x for x in b["days"]}[D]
        want = _all_ecpm(data, D)
        assert day.get("ckw") == "f" and "ckc" not in day, side                       # the whole day, as young
        assert all(c[3] == want[c[0]] for c in day["cty"]), side
        assert ", young 1" in line and "guard fs" not in line and _fsq_list(data) == {}, side


def test_a_first_session_store_that_has_not_read_a_day_final_never_judges_it_final(tmp_path, monkeypatch):
    """The paid store's last window read ("recent_at") too early for the day's final read: that day is not final (a
    deferred store) — only the young whole-day rule, never the list."""
    def prep(site, data, scr):
        _scale_nvr(data, D, 0.2)
        p = os.path.join(data, "ga4_nvr_paid", KA + ".json.gz")
        st = P._rd(p)
        st["recent_at"] = (T.TODAY - timedelta(days=8)).isoformat() + "T06:00:00Z"   # D + 2: before its final read
        P._wr(p, st)
    b, line, err, data = _run(tmp_path, monkeypatch, prep)
    assert {x["d"]: x for x in b["days"]}[D].get("ckw") == "f" and ", young 1" in line and _fsq_list(data) == {}


def test_a_country_row_whose_day_0_is_not_final_is_never_judged(tmp_path, monkeypatch):
    """One country's own decision needs its day-0 cell final in BOTH files' packs (the row's df ≥ 1)."""
    for side in ("paid", "all"):
        def prep(site, data, scr, side=side):
            _scale_nvr(data, D, 0.45, "AA")
            p = os.path.join(scr, "roi_%s_p00.json.gz" % KA) if side == "paid" else \
                os.path.join(site, "roi_%s_c00.json.gz" % KA)
            pk = P._rd(p)
            for r in pk["c"]["AA"]:
                if r[0] == D:
                    r[5] = 0
            P._wr(p, pk)
        b, line, *_ = _run(tmp_path / side, monkeypatch, prep)
        assert "ckw" not in {x["d"]: x for x in b["days"]}[D] and "guard" not in line, side


def test_the_health_line_only_when_the_re_reads_are_used_up_in_the_window(tmp_path, monkeypatch):
    def tries(day, n):
        def prep(site, data, scr):
            _scale_nvr(data, day, 0.2)
            p = os.path.join(data, "ga4_nvr_paid", KA + ".json.gz")
            st = P._rd(p)
            st["rq"] = {day: [n, "2031-06-01T00:00:00Z"]}
            P._wr(p, st)
        return prep
    b, line, err, _ = _run(tmp_path / "used", monkeypatch, tries(D, be.FSQ_TRIES))
    assert err == "be guard skipped: DataWarning\n"                  # once (the health banner), counts only
    assert ", guard fs 1 (left 1), " in line and KA not in line and D not in line
    _, line, err, _ = _run(tmp_path / "not", monkeypatch, tries(D, be.FSQ_TRIES - 1))
    assert err == "" and ", guard fs 1 (left 0), " in line
    old = (T.TODAY - timedelta(days=be.FSQ_WIN + 5)).isoformat()      # used up but older than the window: counted only
    _, line, err, _ = _run(tmp_path / "old", monkeypatch, tries(old, be.FSQ_TRIES))
    assert err == "" and ", guard fs 1 (left 0), " in line


def test_a_broken_day_0_read_is_marked_counted_and_changes_nothing(tmp_path, monkeypatch, whole):
    def prep(site, data, scr):
        p = os.path.join(scr, "roi_%s_p.json.gz" % KA)
        f = P._rd(p)
        for r in f["rows"]:
            if r[0] == D:
                r[4] = [round(v * 0.1, 6) for v in r[4]]
        P._wr(p, f)
    b, line, err, _ = _run(tmp_path, monkeypatch, prep)
    day, w = {x["d"]: x for x in b["days"]}[D], {x["d"]: x for x in whole[0]["days"]}[D]
    assert day["chk"] == 1 and day["ckw"] == "c"
    assert [c[3] for c in day["cty"]] == [c[3] for c in w["cty"]]     # (its eCPM_fs untouched: nothing replaces cells)
    assert ", cohort 1 (recent 1)" in line and err == "be guard skipped: DataWarning\n"


def test_the_guard_off_is_the_step_as_before_it(tmp_path, monkeypatch, whole):
    monkeypatch.setattr(be, "FSQ_ON", False)
    b, line, err, data = _run(tmp_path, monkeypatch, lambda s, d, c: _scale_nvr(d, D, 0.2))
    day = {x["d"]: x for x in b["days"]}[D]
    assert "ckw" not in day and "guard" not in line
    assert all(abs(c[3] - 0.2 * 1.2 * _all_ecpm(data, D)[c[0]]) < 0.01 for c in day["cty"])   # (the broken read, as is)


# ── the output sanity check (C2) ────────────────────────────────────────────────────────────────────────────────────

AGES = [0, 1, 2, 3, 6, 13, 30, 60, 90, 120, 180]
BENCH = [0.30, 0.34, 0.36, 0.38, 0.42, 0.48, 0.60, 0.72, 0.80, 0.90, 1.00]   # a benchmark reaching 100 % at day 180


def test_the_benchmark_growth_day():
    # 0.36 at day 3 (age 2) growing as the benchmark: × 1/0.36 → 1.0 at day 180; a cohort 2 × ahead (0.72) reaches 1.0
    # where the benchmark reaches 0.5: between its ages 13 (0.48) and 30 (0.60)
    assert be._bench_growth(AGES, BENCH, 2, 0.36) == (180.0, 180)
    assert be._bench_growth(AGES, BENCH, 2, 0.72)[0] == pytest.approx(13 + 17 * 0.02 / 0.12)
    assert be._bench_growth(AGES, BENCH, 2, 0.20) == (None, 180)          # never within the benchmark's ages
    d, _ = be._bench_growth(AGES, BENCH, 2, 0.42)                          # (between two ages: linear — 0.857 of
    assert d == pytest.approx(90 + 30 * (0.36 / 0.42 - 0.80) / 0.10)       # the benchmark lies between 90 and 120)


def test_sus_at_its_thresholds(monkeypatch):
    # real 0.36 = the benchmark at day 3 → its benchmark-growth day 180: a median ≤ 90 is "only the model's growth"
    assert be._sus(90, AGES, BENCH, 2, 0.36) and not be._sus(91, AGES, BENCH, 2, 0.36)
    assert be._sus(40, AGES, BENCH, 2, 0.36 * 1.249) and not be._sus(40, AGES, BENCH, 2, 0.36 * 1.26)  # ±25 %
    assert be._sus(60, AGES, BENCH, 2, 0.36 / 1.249) and not be._sus(60, AGES, BENCH, 2, 0.36 / 1.26)
    assert not be._sus(None, AGES, BENCH, 2, 0.36) and not be._sus(60, AGES, None, 2, 0.36)
    assert not be._sus(60, AGES, BENCH, 5, 0.36)                           # (an anchor the benchmark has no age of)
    assert be._sus(90, AGES, BENCH[:-1] + [0.95], 2, 0.36)                 # never reaching 100 %: its last age (180)
    log = []
    monkeypatch.setattr(be, "SAN_LOG", log)
    be._sus(90, AGES, BENCH, 2, 0.36, ("k", "d", "AA"), 150.0)
    assert log == [(("k", "d", "AA"), 2, 90, 180.0, 180, 1.0, 150.0, True)]


def test_a_flagged_row_marks_its_day_and_counts_once(tmp_path, monkeypatch, whole):
    hit = {"n": 0}
    real = be._sus

    def sus(med, ages, bench, a, ra, tag=None, bbe=None):
        if tag and tag == (KA, D, "AA"):
            hit["n"] += 1
            return True
        return real(med, ages, bench, a, ra, tag, bbe)
    monkeypatch.setattr(be, "_sus", sus)
    b, line, err, _ = _run(tmp_path, monkeypatch)
    day = {x["d"]: x for x in b["days"]}[D]
    assert hit["n"] == 1 and day["chk"] == 1 and day["ckw"] == "s"
    assert not any("ckw" in x for x in b["days"] if x["d"] != D)
    assert ", check 1 (recent 1)" in line and err == ""                   # (counted; never the health banner)
    w = {x["d"]: x for x in whole[0]["days"]}[D]                           # (information only: the numbers as they were)
    assert day["cty"] == w["cty"] and day.get("app") == w.get("app")


def test_an_app_line_row_is_counted_never_marked(tmp_path, monkeypatch):
    real, hits = be._sus, []

    def sus(med, ages, bench, a, ra, tag=None, bbe=None):
        if tag and tag[0] == KA and tag[2] == "*":
            hits.append(tag)
            return True
        return real(med, ages, bench, a, ra, tag, bbe)
    monkeypatch.setattr(be, "_sus", sus)
    b, line, err, _ = _run(tmp_path, monkeypatch)
    n = len(hits)
    assert n > 0 and ", app check %d," % n in line and err == ""           # every app-line row it judged: counted …
    assert not any("ckw" in x for x in b["days"]) and "check" not in line.replace("app check", "")   # … never marked


def test_a_country_row_under_san_share_of_the_days_spend_is_never_judged(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(be, "_sus", lambda med, ages, bench, a, ra, tag=None, bbe=None: seen.append(tag) or True)
    monkeypatch.setattr(be, "SAN_SHARE", 0.6)                              # (every covered country here is under 60 %)
    b, line, err, _ = _run(tmp_path, monkeypatch)
    assert seen and all(t[2] == "*" for t in seen)                          # only the app line judged
    assert all("s" in x.get("ckw", "s") for x in b["days"] if x.get("ckw"))


# ── a made-up app whose real rows trip the sanity check end to end (no mocked _sus) ─────────────────────────────────

KF = gu.file_key("app~synth-f")
SAN_DAY = (T.TODAY - timedelta(days=9)).isoformat()      # anchored at day 3 (age 2): CLAG days of final cells before it


def ff_world(tmp):
    """One app, one country FF whose ROAS grows FASTER the lower its first-session eCPM (growth (1 + age)^g, g = ½ +
    0.6 log(5 / eCPM): the model learns "a low start, a big catch-up"), 540 install days; on SAN_DAY its eCPM_fs is
    far under the learned range while its real ROAS so far grows exactly as the benchmark (g = ½, at its level) — the
    model's growth alone makes its breakeven early."""
    site, data = str(tmp / "site"), str(tmp / "data")
    os.makedirs(site, exist_ok=True)
    os.makedirs(os.path.join(data, "ga4_nvr"), exist_ok=True)
    g = T.prng(23)
    rows, pack, store = [], {"FF": []}, {}
    for i in range(T.NDAYS):
        x = T.TODAY - timedelta(days=T.NDAYS - 1 - i)
        xs, age = x.isoformat(), (T.TODAY - x).days
        sp = 200.0 * (1 + 0.1 * next(g))
        cpi, ecpm = 0.5 * math.exp(0.3 * next(g)), 5.0 * math.exp(0.4 * next(g))
        gg, r0 = 0.5 + 0.6 * math.log(5.0 / ecpm), 0.01 * ecpm / cpi * math.exp(0.1 * next(g))
        if xs == SAN_DAY:
            ecpm, cpi, gg, r0 = 1.5, 0.5, 0.5, 0.1
        na = round(sp / cpi, 2)
        n = int(na * 1.3) + 1
        d = [round(sp * r0 * (1.0 + a) ** gg, 6) for a in range(min(age, 30) + 1)]
        m = [round(sp * r0 * (1.0 + a) ** gg, 6) for a in range(60, age + 1, 30)]
        pack["FF"].append(T.roi_row(xs, n, na, round(sp, 6), d, m))
        rows.append(T.roi_row(xs, n, na, round(sp, 6), d, m))
        imp = n * 10
        store[xs] = {"c": [["n", "FF", round(ecpm * imp / 1000, 6), imp], ["r", "FF", 1.0, 400]], "u": [], "s": []}
    pf = "roi_%s_c00.json.gz" % KF
    with gzip.open(os.path.join(site, pf), "wt", encoding="utf-8") as f:
        json.dump({"v": 1, "b": "x", "key": KF, "c": pack}, f)
    with gzip.open(os.path.join(site, "roi_%s.json.gz" % KF), "wt", encoding="utf-8") as f:
        json.dump({"v": 1, "key": KF, "newest": T.TODAY.isoformat(), "rows": rows, "cd": {"packs": [[pf, "x"]]}}, f)
    with gzip.open(os.path.join(data, "ga4_nvr", KF + ".json.gz"), "wt", encoding="utf-8") as f:
        json.dump({"v": 2, "days": store}, f)
    return site, data, {"roi": {"file": "roi.json.gz", "apps": {"app~synth-f": {"file": "roi_%s.json.gz" % KF,
                                                                                    "st": "Normal"}}}}


def _ff(tmp, s):
    site, data, dash = ff_world(tmp)
    paths, line, err = P._go(dash, data, site, s)
    return site, data, dash, paths, line, err


def test_the_real_rule_trips_a_made_up_country_row_end_to_end(tmp_path):
    site, data, dash, paths, line, err = _ff(tmp_path, {})
    b = P._rd(os.path.join(site, "be_%s.json.gz" % KF))
    day = {x["d"]: x for x in b["days"]}[SAN_DAY]
    assert day["chk"] == 1 and day["ckw"] == "s" and day["ckc"] == {"FF": "s"}       # its own row, named
    assert ", check " in line and err == ""                                          # (counted; not the banner)
    _, _, _, _, line0, _ = _ff(tmp_path / "off", {"be_san": False})                  # BE_SAN off: nothing of it
    b0 = P._rd(os.path.join(str(tmp_path / "off" / "site"), "be_%s.json.gz" % KF))
    assert not any("ckw" in x or "ckc" in x for x in b0["days"]) and "check" not in line0
    assert [x["cty"] for x in b0["days"]] == [x["cty"] for x in b["days"]]           # (numbers as they were)


# sha256 (tests/test_be_paid._digest) of the step's outputs with BOTH checks off — worked out once with the code of
# e71fbed (the commit this branch starts from: its whole admob_iq loaded in place of this tree's, these same worlds and
# test helpers) at GA4_FINAL_DAYS = 3 (the tests' pin, tests/conftest.py); the same check at the production F 7 was
# run by hand the same way (both sides equal) — this test pins F 3 only
BOTH_OFF_BEFORE = {"ff": "b81b23c9de6c85713ca017e8b2e251dbdfec76dad9ff0efc11260ce393917e0c",       # (at the tests'
                   "paid": "133b0314922404934bc4ed200d91f6b1a180ba2c374cfc1296493629b59a54e7"}     # GA4_FINAL_DAYS)


def _paid_broken(tmp, mp):
    site, data, dash, scr = P.paid_world(tmp)
    _scale_nvr(data, D, 0.2)
    P._state(mp, scr)
    return site, data, dash


R5_OFF = {"be_fsc": False, "be_gap": False, "be_upi": False, "be_rsf": False}   # (the later checks and the "ROAS so far"
#                                          column off too: "before them" is before every one of them)


def both_off_digests(tmp, mp):
    """The two worlds through the step with BE_FSQ and BE_SAN off (the sanity check's real rule trips the first, the
    input guard's the second) — and every later switch (R5_OFF)."""
    out = {}
    site, data, dash = ff_world(tmp / "ff")
    paths, line, err = P._go(dash, data, site, dict(R5_OFF, be_fsq=False, be_san=False))
    out["ff"] = P._digest(site, data, dash, paths, line, err)
    site, data, dash = _paid_broken(tmp / "paid", mp)
    paths, line, err = P._go(dash, data, site, dict(R5_OFF, be_paid=True, be_fsq=False, be_san=False))
    out["paid"] = P._digest(site, data, dash, paths, line, err)
    return out


def test_both_checks_off_every_output_byte_for_byte_as_before_them(tmp_path, monkeypatch):
    if be.LAG != be.LAG0:
        pytest.skip("the digests were worked out at the tests' GA4_FINAL_DAYS (3)")
    assert both_off_digests(tmp_path, monkeypatch) == BOTH_OFF_BEFORE


# ── the reference agrees with itself; the guard's own failure; its cache stamp; the switch; the app-line count ──────

def test_ref_ok_at_its_thresholds():
    assert be.ref_ok(10.0, 40.0, 5.0, 14.0, "fs") and not be.ref_ok(10.0, 40.0, 5.0, 13.9, "fs")     # d0 ≥ 0.35 × fs
    assert be.ref_ok(10.0, 30.0, 20.0, 100.0, "coh") and not be.ref_ok(10.0, 29.9, 20.0, 100.0, "coh")  # fs ≥ 0.3 × d0
    assert not be.ref_ok(43.1, 40.0, 20.0, 100.0, "fs") and be.ref_ok(43.0, 40.0, 20.0, 100.0, "fs")  # paid ≤ 1.05 × + 1
    assert not be.ref_ok(10.0, 40.0, 106.1, 100.0, "fs") and be.ref_ok(10.0, 40.0, 106.0, 100.0, "fs")
    assert not be.ref_ok(1.0, None, 1.0, 100.0, "fs") and not be.ref_ok(1.0, 40.0, 1.0, None, "coh")


def _pack_cell(site, cc, day, k):
    """Every user's pack: country cc's row of `day`, its cells × k (its day-0 read near-empty)."""
    p = os.path.join(site, "roi_%s_c00.json.gz" % KA)
    pk = P._rd(p)
    for r in pk["c"][cc]:
        if r[0] == day:
            r[4] = [round(v * k, 6) for v in r[4]]
    P._wr(p, pk)


def test_a_reference_that_disagrees_with_itself_decides_nothing(tmp_path, monkeypatch):
    def near_empty_d0(site, data, scr):                     # AA: every user's day 0 near-empty, paid first session a
        _pack_cell(site, "AA", D, 0.1)                      # little low — judged on that reference it would be "broken"
        _scale_nvr(data, D, 0.85, "AA")
    b, line, err, _ = _run(tmp_path / "d0", monkeypatch, near_empty_d0)
    day = {x["d"]: x for x in b["days"]}[D]
    assert "ckw" not in day and "ckc" not in day and ", ref skip 1" in line and err == ""

    def near_empty_fs(site, data, scr):                     # every user's first session near-empty: the cohort rule's
        p = os.path.join(data, "ga4_nvr", KA + ".json.gz")  # reference is in doubt (paid above every user's)
        st = P._rd(p)
        st["days"][D]["c"] = [[n, c, round(rev * 0.1, 6), im] for n, c, rev, im in st["days"][D]["c"]]
        P._wr(p, st)
    b, line, err, _ = _run(tmp_path / "fs", monkeypatch, near_empty_fs)
    day = {x["d"]: x for x in b["days"]}[D]
    assert "c" not in day.get("ckw", "") and ", ref skip 1" in line and "cohort" not in line and err == ""


def test_a_pack_gap_date_of_every_users_packs_is_never_judged_for_a_country(tmp_path, monkeypatch):
    real = be._gap_rule
    monkeypatch.setattr(be, "_gap_rule", lambda *a, **k: real(*a, **k) | {T.TODAY.toordinal() - 10})
    b, line, *_ = _run(tmp_path, monkeypatch, lambda s, d, c: _scale_nvr(d, D, 0.45, "AA"))
    assert "ckw" not in {x["d"]: x for x in b["days"]}[D] and ", ref skip 1" in line


def test_a_failing_guard_read_costs_only_the_guard(tmp_path, monkeypatch, whole):
    def junk(site, data, scr):
        _scale_nvr(data, D, 0.2)
        with open(os.path.join(site, "roi_%s_c00.json.gz" % KA), "wb") as f:
            f.write(b"not a gzip")
    b, line, err, _ = _run(tmp_path, monkeypatch, junk)
    assert b["src"] == "p" and len(b["days"]) == len(whole[0]["days"])          # its file, as without the guard
    assert "ckw" not in {x["d"]: x for x in b["days"]}[D] and ", guard fail 1" in line
    assert "be guard skipped: BadGzipFile\n" in err


def test_the_caches_carry_the_guards_stamp_and_a_flip_makes_them_again(tmp_path, monkeypatch):
    site, data, dash, scr = P.paid_world(tmp_path)
    P._state(monkeypatch, scr)
    P._go(dash, data, site, {"be_paid": True})
    fp = os.path.join(data, "be_tab", "fitsp_%s.json.gz" % KA)
    cp = os.path.join(data, "be_tab", be.CALIB_P)
    with open(cp, encoding="utf-8") as f:
        assert json.load(f)["fq"] == be._fqv()             # (round 5: FSC beside FSQ_V while on)
    assert P._rd(fp)["fq"] == be._fqv()
    assert "fq" not in P._rd(os.path.join(data, "be_tab", "fits_%s.json.gz" % P.KB))   # (every user's: never)
    _, line, _ = P._go(dash, data, site, {"be_paid": True, "be_fsq": False}, T.NOW + timedelta(hours=1))
    assert "refit yes" in line and ", calib p yes" in line                      # the same UTC day: made again at once
    assert "fq" not in P._rd(fp)
    with open(cp, encoding="utf-8") as f:
        assert "fq" not in json.load(f)
    _, line, _ = P._go(dash, data, site, {"be_paid": True, "be_fsq": False}, T.NOW + timedelta(hours=2))
    assert "refit no" in line and ", calib p no" in line                        # (and only once)


def test_be_fsq_false_is_the_guard_off(tmp_path, monkeypatch):
    b, line, err, data = _run(tmp_path, monkeypatch, lambda s, d, c: _scale_nvr(d, D, 0.2), {"be_fsq": False})
    assert "ckw" not in {x["d"]: x for x in b["days"]}[D] and "guard" not in line
    assert not os.path.exists(os.path.join(data, "be_tab", be.FSQ_FILE))       # (no re-read list either)
    assert be.FSQ_ON is True and be.SAN_ON is True                             # (the module's own switches untouched)


def test_the_app_line_count_is_per_build_never_carried(tmp_path, monkeypatch):
    real = be._sus
    monkeypatch.setattr(be, "_sus", lambda med, ages, bench, a, ra, tag=None, bbe=None:
                        True if tag and tag[2] == "*" else real(med, ages, bench, a, ra, tag, bbe))
    site, data, dash, scr = P.paid_world(tmp_path)
    P._state(monkeypatch, scr)
    lines = [P._go(dash, data, site, {"be_paid": True}, T.NOW + timedelta(hours=h))[1] for h in (0, 1)]
    k = [int(x.split(", app check ")[1].split(",")[0]) for x in lines]
    assert k[0] == k[1] > 0                                                     # the same each build: never added up
    st = {}
    fc = be.load_fits(data, KA, "p")
    got = be.load(site, data, KA, "roi_%s.json.gz" % KA, True, (scr, "roi_%s_p.json.gz" % KA))
    be.predict(KA, fc, be.load_calib(data, "p"), be._pin(*got[:5]), None, st)
    assert st["app"] > 0 and not hasattr(be, "SANC")                            # (predict's own count, no global)


# ── round 4: a stale re-read list, the switches' spelling, the stamp only where the guard ran ──────────────────────

def test_the_guard_off_leaves_no_re_read_list(tmp_path, monkeypatch):
    def stale(site, data, scr):
        os.makedirs(os.path.join(data, "be_tab"), exist_ok=True)
        with open(os.path.join(data, "be_tab", be.FSQ_FILE), "w", encoding="utf-8") as f:
            json.dump({"v": be.V, "days": {KA: [D]}}, f)
    for s in ({"be_fsq": False}, {"be_paid": False}):
        _, _, _, data = _run(tmp_path / str(len(s) + len(str(s))), monkeypatch, stale, s)
        assert not os.path.exists(os.path.join(data, "be_tab", be.FSQ_FILE)), s


@pytest.mark.parametrize("v,want", [(None, True), ("", True), ("true", True), ("1", True), ("anything", True),
                                    ("false", False), ("FALSE ", False), (" 0", False), ("off", False), ("No", False)])
def test_the_switches_turn_off_on_every_usual_spelling(monkeypatch, v, want):
    from admob_iq import config
    for name, k in (("BE_FSQ", "be_fsq"), ("BE_SAN", "be_san")):
        if v is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, v)
        assert config.settings()[k] is want, (name, v)


def test_the_stamp_only_where_the_guard_ran_and_a_failed_state_is_tried_once_a_day(tmp_path, monkeypatch):
    site, data, dash, scr = P.paid_world(tmp_path)
    P._state(monkeypatch, scr)
    real = be._guard_in
    monkeypatch.setattr(be, "_guard_in", lambda *a, **k: 1 / 0)              # its reads fail this build
    _, line, err = P._go(dash, data, site, {"be_paid": True})
    fp, cp = os.path.join(data, "be_tab", "fitsp_%s.json.gz" % KA), os.path.join(data, "be_tab", be.CALIB_P)
    with open(cp, encoding="utf-8") as f:
        c = json.load(f)
    assert "fq" not in P._rd(fp) and "fq" not in c and c["fqt"] == be._fqv()     # unguarded: not stamped; tried
    assert ", guard fail 1" in line and "be guard skipped: ZeroDivisionError" in err
    _, line, _ = P._go(dash, data, site, {"be_paid": True}, T.NOW + timedelta(hours=1))
    assert ", calib p no" in line                                            # (not again every build)
    monkeypatch.setattr(be, "_guard_in", real)                               # it works again: the fits at once
    _, line, _ = P._go(dash, data, site, {"be_paid": True}, T.NOW + timedelta(hours=2))
    assert "refit yes" in line and P._rd(fp)["fq"] == be._fqv()
