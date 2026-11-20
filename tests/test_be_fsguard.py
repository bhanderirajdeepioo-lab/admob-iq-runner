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
import os
from datetime import timedelta

import pytest

from admob_iq import be_build as be
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


def test_a_young_or_small_day_is_not_judged(tmp_path, monkeypatch):
    young = (T.TODAY - timedelta(days=be.FSQ_AGE - 1)).isoformat()
    b, line, *_ = _run(tmp_path, monkeypatch, lambda s, d, c: _scale_nvr(d, young, 0.2))
    assert "ckw" not in {x["d"]: x for x in b["days"]}[young] and "guard" not in line   # (both day-0 reads not settled)


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
