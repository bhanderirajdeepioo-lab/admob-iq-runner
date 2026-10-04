"""Audience history + comeback (engine.audience.snapshot / hist_append / comeback / comeback_portfolio, and the
history the Audience fetch keeps: fetch.ga4_audience.record_history) — offline, synthetic users only.

  * the snapshot: one install month → [installs, installed, alive_1 … alive_K, act_1 … act_K, dead_lo_1 … dead_lo_K],
    compact, and the sums of its months are the app's own;
  * the file: a snapshot appended for every NEW E (also an older E finished and rolled past in the same turn, and the
    complete store a run finds without one), the same E never twice, every older snapshot kept byte for byte, a partial
    read never writes, a failure (or an unreadable file) never costs the read or loses history;
  * comeback(): on a synthetic population that COMES BACK (tests.audience_hist_synth.Returners — explicit open days, so
    the true counts are known by brute force and the true chances are the generator's own): the users quiet for k months on
    E1 who opened in the next 30 / 31 days are recovered EXACTLY from the monthly aggregates (the identity in
    engine.audience), the generator's chances within the sampling noise, the sleepers' range holds the truth when some
    uninstall without opening, only mature install months and exactly aligned pairs of snapshots are used, and a short
    history is flagged instead of guessed."""

import copy
import gzip
import json
import math
import os
from datetime import timedelta

import pytest

from admob_iq.engine import audience as eng
from admob_iq.fetch import ga4_audience as ga
from tests.audience_hist_synth import RATES, Returners
from tests.audience_synth import E, Population
from tests.test_ga4_audience import (A1, A2, A3, NOW, NOW_ISO, PID, ROUTE, SECRETS, SID, _ga, _run, fake,  # noqa: F401
                                     seed, world)

D0 = E - timedelta(days=62)                          # the first snapshot day of the synthetic history: 20 July
OFFSETS = (0, 30, 31, 60, 62)                        # 30 days: windows k = 1, 3, 5 …; 31 days: k = 2, 4, 6 …


def _iso(d):
    return d.isoformat()


def _hist(pop, offsets=OFFSETS, start=D0):
    """The history file's content for the days start + offset: each day's complete read, derived, snapshotted."""
    hist = {}
    for n in offsets:
        v = pop.at(start + timedelta(days=n))
        eng.hist_append(hist, _iso(start + timedelta(days=n)), eng.snapshot(eng.derive_app(v.aud_store(), v.uni_store())))
    return hist


def _chain(offsets, gap):
    """The intervals comeback() should pick for a gap: the earliest start with its partner, then on from its end."""
    have, out, free = set(offsets), [], None
    for n in sorted(offsets):
        if free is not None and n < free:
            continue
        if n + gap in have:
            out.append((n, n + gap))
            free = n + gap
    return out


@pytest.fixture(scope="module")
def pop():
    return Returners(days=420, per_day=60, seed=4)


@pytest.fixture(scope="module")
def hist(pop):
    return _hist(pop)


@pytest.fixture(scope="module")
def result(hist):
    return eng.comeback(hist)


# ── the snapshot ─────────────────────────────────────────────────────────────────────────────────────

def test_a_snapshot_is_the_months_aggregates_of_the_derived_app():
    p = Population(days=420, per_day=8, seed=5)
    aud, uni = p.aud_store(), p.uni_store()
    out = eng.derive_app(aud, uni)
    snap = eng.snapshot(out)
    k = len(out["months"])
    assert snap["months"] == out["months"] == aud["months"] and k == 13 and snap["q"] == []
    assert set(snap["m"]) == {mo for mo, g in out["months_by"].items() if g["installs"]}
    for mo, row in snap["m"].items():
        g = out["months_by"][mo]
        assert len(row) == 2 + 3 * k
        assert row[0] == g["installs"] and row[1] == g["installed"]
        assert row[2:2 + k] == g["alive"] and row[2 + k:2 + 2 * k] == g["act"] and row[2 + 2 * k:] == g["dead_lo"]
    rows = list(snap["m"].values())                              # the months add up to the app
    assert sum(r[0] for r in rows) == out["installs"] and sum(r[1] for r in rows) == out["installed"]
    for i in range(k):
        assert sum(r[2 + i] for r in rows) == out["alive"][i]
        assert sum(r[2 + k + i] for r in rows) == out["act"][i]
        assert sum(r[2 + 2 * k + i] for r in rows) == out["dead_lo"][i]
    assert json.loads(json.dumps(snap)) == snap                  # plain JSON
    flagged = dict(aud, flags={"thresholded": ["w30"], "other": [], "cov_off": {"w60": 0.9}, "rows": 5})
    assert eng.snapshot(eng.derive_app(flagged, uni))["q"] == ["thresholded", "cov_off"]


def test_a_snapshot_is_a_few_kb_even_for_a_long_history():
    p = Population(days=1300, per_day=4, seed=6)                 # 43 install months, 20 windows
    out = eng.derive_app(p.aud_store(), p.uni_store())
    snap = eng.snapshot(out)
    raw = json.dumps(snap, separators=(",", ":"), sort_keys=True).encode()
    assert len(snap["m"]) >= 42 and len(snap["months"]) == 20
    assert len(raw) < 20000 and len(gzip.compress(raw)) < 6000


def test_hist_append_adds_each_e_once_and_never_replaces():
    h = {}
    assert eng.hist_append(h, "2026-09-20", {"months": [1], "m": {}, "q": []}) is True
    assert eng.hist_append(h, "2026-09-20", {"months": [9], "m": {}, "q": ["other"]}) is False
    assert h["v"] == eng.HIST_V and h["snaps"] == {"2026-09-20": {"months": [1], "m": {}, "q": []}}
    assert eng.hist_append(h, "2026-09-21T00:00:00", {"months": [1], "m": {}, "q": []}) is True   # keyed by the day
    assert list(h["snaps"]) == ["2026-09-20", "2026-09-21"]


# ── the history file: append / idempotent / partial never writes ──────────────────────────────────────

def _hist_file(data, aid):
    return ga.hist_path(data, aid)


def _snaps(data, aid):
    h = ga.load_hist(_hist_file(data, aid))
    return h["snaps"] if h else {}


def test_every_new_e_appends_one_snapshot_and_no_older_one_changes(world):
    data, pops, f = world
    out = _run(data)
    assert out["counts"]["hist"] == 3 and out["counts"]["hist_failed"] == 0
    assert ga.log_line(out).endswith(", history +3")
    for aid, (pid, sid, p) in pops.items():
        path = _hist_file(data, aid)
        assert path.endswith(os.path.join("ga4_audience_hist", ga.gu.file_key(aid) + ".json.gz"))
        h = ga.load_hist(path)
        assert h["v"] == 1 and list(h["snaps"]) == [_iso(E)]
        assert h["snaps"][_iso(E)] == eng.snapshot(eng.derive_app(p.aud_store(), p.uni_store()))
    assert ga.load_state(data)["fetch"][A1]["hist_E"] == _iso(E)
    first = {aid: _snaps(data, aid)[_iso(E)] for aid in pops}
    raw, mtime = open(_hist_file(data, A1), "rb").read(), os.stat(_hist_file(data, A1)).st_mtime_ns
    out = _run(data, now=NOW + timedelta(hours=5))               # the same final day: nothing read, nothing written
    assert out["apps"] == {A1: "fresh", A2: "fresh", A3: "fresh"} and out["counts"]["hist"] == 0
    assert open(_hist_file(data, A1), "rb").read() == raw and os.stat(_hist_file(data, A1)).st_mtime_ns == mtime
    assert "history" not in ga.log_line(out)
    for day in range(1, 6):                                      # five new final days
        out = _run(data, now=NOW + timedelta(days=day))
        assert out["counts"]["hist"] == 3
    for aid in pops:
        s = _snaps(data, aid)
        assert list(s) == [_iso(E + timedelta(days=d)) for d in range(6)]            # every E, in order, none dropped
        assert s[_iso(E)] == first[aid]                                              # the first one unchanged


def test_the_same_e_is_never_appended_twice(world):
    data, pops, f = world
    _run(data)
    store = ga.load_store(ga.store_path(data, A1))
    path = _hist_file(data, A1)
    raw, mtime = open(path, "rb").read(), os.stat(path).st_mtime_ns
    assert ga.record_history(data, A1, store) == "exists"
    other = dict(store, by_fsd={x: [v + 1 for v in row] for x, row in store["by_fsd"].items()})   # another read of that E
    assert ga.record_history(data, A1, other) == "exists"
    assert open(path, "rb").read() == raw and os.stat(path).st_mtime_ns == mtime
    assert list(ga.load_hist(path)["snaps"]) == [_iso(E)]
    fresh = str(world[0]) + "/elsewhere"                         # a data dir without a history: added once, then exists
    os.makedirs(fresh)
    assert ga.record_history(fresh, A1, store, uni=ga.gu.load_store(ga.gu.store_path(data, A1))) == "added"
    assert ga.record_history(fresh, A1, store, uni=ga.gu.load_store(ga.gu.store_path(data, A1))) == "exists"


def test_a_partial_read_never_writes(world):
    data, pops, f = world
    f.tokens, f.hourly = 100, {"tokensPerProjectPerHour": 7250}  # A1 gets 2 of its 4 calls, the others fit
    out = _run(data)
    assert out["apps"] == {A1: "partial", A2: "fetched", A3: "fetched"}
    assert not os.path.exists(_hist_file(data, A1))              # a first read still partial: no file at all
    assert list(_snaps(data, A2)) == [_iso(E)] and out["counts"]["hist"] == 2
    f.hour_left, f.hourly = {}, {}
    out = _run(data, now=NOW + timedelta(hours=1))               # the next hour completes it
    assert out["apps"][A1] == "fetched" and list(_snaps(data, A1)) == [_iso(E)]
    # a new E, read only in part (a low hourly quota again): the old E's complete store stays, the history gains nothing
    before = {aid: list(_snaps(data, aid)) for aid in pops}
    f.tokens, f.hourly, f.hour_left = 100, {"tokensPerProjectPerHour": 7250}, {}
    nxt = _iso(E + timedelta(days=1))
    out = _run(data, now=NOW + timedelta(days=1))
    part = [aid for aid, v in out["apps"].items() if v == "partial"]
    assert part and all(out["apps"][aid] in ("partial", "fetched") for aid in pops)
    for aid in pops:
        assert list(_snaps(data, aid)) == before[aid] + ([] if aid in part else [nxt])
    assert out["counts"]["hist"] == len(pops) - len(part)
    for aid in part:
        assert ga.load_store(ga.store_path(data, aid))["partial"]["E"] == nxt
    f.hour_left, f.hourly = {}, {}
    out = _run(data, now=NOW + timedelta(days=1, hours=1))       # finished: now (and only now) it is appended
    assert all(out["apps"][aid] in ("fetched", "fresh") for aid in pops)
    assert all(list(_snaps(data, aid)) == [_iso(E), nxt] for aid in pops)


def test_an_old_e_finished_and_rolled_past_in_one_turn_still_gets_its_snapshot(fake):
    p = Population(days=200, per_day=5)
    fake({(PID, SID): p})
    store, seen = {}, []
    with pytest.raises(ga.Stop):
        ga.step(_ga(), store, E, p.start, ROUTE, NOW_ISO, max_calls=1)
    assert seen == [] and "partial" in store
    later = E + timedelta(days=1)
    res = ga.step(_ga(), store, later, p.start, ROUTE, NOW_ISO, on_done=lambda s: seen.append((s["E"], s["complete"])))
    assert res == "fetched" and store["E"] == _iso(later)
    assert seen == [(_iso(E), True), (_iso(later), True)]        # one call per completed E, the older one first
    assert ga.step(_ga(), store, later, p.start, ROUTE, NOW_ISO, on_done=lambda s: 1 / 0) == "fresh"
    store2, calls = {}, []
    assert ga.step(_ga(), store2, E, p.start, ROUTE, NOW_ISO, on_done=lambda s: calls.append(1) or 1 / 0) == "fetched"
    assert calls == [1] and store2["complete"]                   # a hook that raises never costs the read


def test_a_complete_store_found_without_a_snapshot_gets_one_before_the_next_read_replaces_it(world, monkeypatch):
    data, pops, f = world
    real = ga.record_history
    monkeypatch.setattr(ga, "record_history", lambda *a, **k: "skipped")      # the code before the history existed
    _run(data)
    assert not os.path.exists(os.path.join(data, ga.HIST_DIR))
    monkeypatch.setattr(ga, "record_history", real)
    out = _run(data, now=NOW + timedelta(days=1))                # new E: the old complete store is recorded first …
    assert out["counts"]["hist"] == 6                            # … and the new read after it, per app
    for aid in pops:
        assert list(_snaps(data, aid)) == [_iso(E), _iso(E + timedelta(days=1))]
    out = _run(data, now=NOW + timedelta(days=1, hours=1))
    assert out["counts"]["hist"] == 0


def test_a_history_failure_never_costs_the_read_and_is_tried_again(world, monkeypatch):
    data, pops, f = world
    monkeypatch.setattr(ga.aeng, "snapshot", lambda out: 1 / 0)
    out = _run(data)
    assert out["apps"] == {A1: "fetched", A2: "fetched", A3: "fetched"} and "error" not in out
    assert out["counts"]["hist"] == 0 and out["counts"]["hist_failed"] == 3
    assert ga.log_line(out).endswith(", history failed 3")
    assert all(ga.load_store(ga.store_path(data, aid))["complete"] for aid in pops)
    assert not os.path.exists(os.path.join(data, ga.HIST_DIR))
    assert "hist_E" not in ga.load_state(data)["fetch"][A1]
    monkeypatch.undo()
    out = _run(data, now=NOW + timedelta(hours=1))               # the complete stores are recorded on the next run
    assert out["apps"] == {A1: "fresh", A2: "fresh", A3: "fresh"} and out["counts"]["hist"] == 3
    assert list(_snaps(data, A3)) == [_iso(E)]
    for s in SECRETS + [_iso(E)]:
        assert s not in ga.log_line(out)


def test_an_unreadable_history_file_is_left_alone(world):
    data, pops, f = world
    os.makedirs(os.path.join(data, ga.HIST_DIR))
    with open(_hist_file(data, A1), "wb") as fh:
        fh.write(b"not a gzip file")
    out = _run(data)
    assert out["apps"][A1] == "fetched" and out["counts"]["hist_failed"] == 1 and out["counts"]["hist"] == 2
    assert open(_hist_file(data, A1), "rb").read() == b"not a gzip file"             # never overwritten
    assert ga.load_hist(_hist_file(data, A1)) is None and ga.load_hist(_hist_file(data, "nope")) == {}
    with open(_hist_file(data, A2), "wb") as fh:                                       # (a newer format is left alone too)
        fh.write(gzip.compress(json.dumps({"v": 99, "snaps": {}}).encode()))
    assert ga.load_hist(_hist_file(data, A2)) is None


def test_every_apps_history_loads_and_comeback_all_gives_the_app_and_portfolio_tables(world):
    data, pops, f = world
    assert ga.load_all_hist(data) == {}
    for day in range(0, 3):
        _run(data, now=NOW + timedelta(days=day))
    with open(_hist_file(data, A3), "wb") as fh:                     # one unreadable file is left out, not fatal
        fh.write(b"junk")
    hs = ga.load_all_hist(data)
    assert sorted(hs) == sorted(ga.gu.file_key(a) for a in (A1, A2)) and all(len(h["snaps"]) == 3 for h in hs.values())
    both = eng.comeback_all(hs)
    assert sorted(both["apps"]) == sorted(hs) and both["portfolio"]["apps"] == 2
    assert all(r["status"] == "too_short" for r in both["apps"].values())          # three days: a month is not there yet
    assert both["portfolio"]["status"] == "too_short" and both["portfolio"]["ready_on"] == _iso(E + timedelta(days=30))
    assert eng.comeback_all({})["portfolio"]["status"] == "no_history" and eng.comeback_all(None)["apps"] == {}


def test_the_history_file_is_deterministic_and_grows_by_one_snapshot_a_day(world):
    data, pops, f = world
    _run(data)
    p = _hist_file(data, A1)
    one = len(open(p, "rb").read())
    h = ga.load_hist(p)
    assert not ga.save_hist(p, h)                                # unchanged: not rewritten
    raw = json.dumps(h, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    assert gzip.decompress(open(p, "rb").read()) == raw
    for day in range(1, 11):
        _run(data, now=NOW + timedelta(days=day))
    ten = len(open(p, "rb").read())
    assert one < ten < 11 * one                                  # grows, a little less than snapshot by snapshot


def test_a_month_of_daily_runs_builds_a_history_whose_comeback_is_exact(tmp_path, fake):
    """The whole chain once, offline: 32 daily build runs (fake GA4 reads of people who come back, the Uninstall store as
    of each day) → one snapshot per day in the history file → comeback() on that file: the 30- and 31-day intervals from
    the first day, exactly the brute-force truth."""
    people = Returners(days=400, per_day=8, seed=15, horizon=E + timedelta(days=31))
    data = str(tmp_path / "data")
    os.makedirs(data)
    for d in range(32):
        day = people.at(E + timedelta(days=d))
        seed(data, {A1: (PID, SID, day)})
        fake({(PID, SID): day})
        assert _run(data, now=NOW + timedelta(days=d))["apps"][A1] == "fetched"
    h = ga.load_hist(_hist_file(data, A1))
    assert list(h["snaps"]) == [_iso(E + timedelta(days=d)) for d in range(32)]
    res = eng.comeback(h, min_back=1, min_sleepers=1)
    assert res["status"] == "ok" and res["snapshots"] == 32 and res["ready_on"] is None
    for r in res["rows"][:4]:
        k, g = r["slept"], r["gap_days"]
        assert (r["intervals"], r["span"]) == (1, [_iso(E), _iso(E + timedelta(days=g))])
        back, sleepers = people.truth(E, E + timedelta(days=g), k)
        assert (r["back_raw"], r["sleepers"]) == (back, sleepers) and back > 0
    assert eng.comeback(h)["status"] in ("ok", "thin")


# ── comeback: the identity, exactly ───────────────────────────────────────────────────────────────────

def test_the_users_quiet_for_k_months_who_open_again_are_recovered_exactly(pop, result):
    assert result["status"] == "ok" and result["enough"] and result["ready_on"] is None
    assert [r["slept"] for r in result["rows"]] == list(range(1, 12))
    for r in result["rows"]:
        k, g = r["slept"], r["gap_days"]
        assert g == eng.window_days(k + 1) - eng.window_days(k) and g in (30, 31)
        pairs = _chain(OFFSETS, g)
        assert len(pairs) == r["intervals"] == 2
        back = sleepers = 0
        for a, b in pairs:
            tb, ts = pop.truth(D0 + timedelta(days=a), D0 + timedelta(days=b), k)
            back, sleepers = back + tb, sleepers + ts
        assert r["back_raw"] == r["back"] == back > 0         # who opened again: exactly the brute-force count …
        assert r["sleepers"] == sleepers                      # … out of exactly the sleepers (every uninstaller opened)
        assert r["span"] == [_iso(D0 + timedelta(days=pairs[0][0])), _iso(D0 + timedelta(days=pairs[-1][1]))]
        assert r["rate"] == round(back / sleepers, 4) and r["rate_max"] >= r["rate"] and r["sleepers_lo"] <= sleepers
    # by install month: the same sums, split (mature months only)
    for k in (1, 2, 7):
        tot = [sum(m[str(k)][i] for m in result["by_month"].values() if str(k) in m) for i in range(3)]
        row = result["rows"][k - 1]
        assert tot == [row["back_raw"], row["sleepers_lo"], row["sleepers"]]


def test_the_bands_are_differences_of_rows_over_the_intervals_both_have(pop, result):
    by = {b["label"]: b for b in result["bands"]}
    assert list(by) == ["1–2 months", "2–4 months", "4–7 months", "7+ months"]
    rows = {r["slept"]: r for r in result["rows"]}
    for label, a, b in (("1–2 months", 1, 2), ("2–4 months", 2, 4), ("4–7 months", 4, 7)):
        assert by[label]["back_raw"] == rows[a]["back_raw"] - rows[b]["back_raw"]
        assert by[label]["sleepers"] == rows[a]["sleepers"] - rows[b]["sleepers"]
        assert by[label]["sleepers_lo"] == rows[a]["sleepers_lo"] - rows[b]["sleepers_lo"]
        assert by[label]["intervals"] == 2
    top = by["7+ months"]                                        # the open band is dead ≥ 7 months itself
    assert (top["back_raw"], top["sleepers"]) == (rows[7]["back_raw"], rows[7]["sleepers"])
    # the 2–4 months band: both rows are 31 days, so it is exactly the users last open 2–4 months before E1
    want = sum(pop.truth(D0 + timedelta(days=a), D0 + timedelta(days=b), 2)[0]
               - pop.truth(D0 + timedelta(days=a), D0 + timedelta(days=b), 4)[0] for a, b in _chain(OFFSETS, 31))
    assert by["2–4 months"]["back_raw"] == want
    rates = [by[k]["rate"] for k in by]
    assert rates == sorted(rates, reverse=True) and rates[-1] > 0     # the longer asleep, the lower the chance


def test_the_generators_known_chances_are_recovered_within_the_noise(pop, result):
    """The comebacks the generator's own daily chances (RATES) predict for exactly these sleepers, per row: the
    measured count is within 3.5 standard deviations of it (a user quiet for 45 days spends half the month in the next
    age band, so the rate of a band is the rate for the NEXT month of people that age NOW — which is what a model of the
    chance needs)."""
    for r in result["rows"]:
        k, g = r["slept"], r["gap_days"]
        mean = var = 0.0
        for a, b in _chain(OFFSETS, g):
            m, v = pop.expected_back(D0 + timedelta(days=a), D0 + timedelta(days=b), k)
            mean, var = mean + m, var + v
        assert abs(r["back_raw"] - mean) <= 3.5 * math.sqrt(var), (k, r["back_raw"], mean)
        if k <= 8:
            assert r["back_raw"] > 3 * math.sqrt(var)                   # (and not just noise around nothing)
    by = {b["label"]: b["rate"] for b in result["bands"]}
    for label, (_, p) in zip(by, RATES):                         # each band within a factor of the chance it was built with
        assert 0.55 * p <= by[label] <= 1.25 * p, (label, by[label], p)


def test_the_sleepers_range_holds_the_truth_when_some_uninstall_without_opening():
    dormant = Returners(days=420, per_day=40, seed=8, dormant_un=1.0)
    h = _hist(dormant)
    res = eng.comeback(h)
    for r in res["rows"]:
        pairs = _chain(OFFSETS, r["gap_days"])
        tb = ts = 0
        for a, b in pairs:
            x, y = dormant.truth(D0 + timedelta(days=a), D0 + timedelta(days=b), r["slept"])
            tb, ts = tb + x, ts + y
        assert r["back_raw"] == tb                                # the numerator never depended on the approximation
        assert r["sleepers_lo"] <= ts <= r["sleepers"]            # the truth is inside the range …
        assert r["sleepers"] > ts or r["slept"] > 9               # … and clean-up uninstallers do widen it
        assert r["rate"] <= tb / ts <= r["rate_max"]


def test_only_mature_install_months_are_counted(pop, hist, result):
    months = set(result["by_month"])
    assert "2026-06" in months and "2026-07" in months          # E1 is 20 July / 19–20 Aug: July is mature for the 2nd
    assert not months & {"2026-08", "2026-09"}                    # … August and September never are (installs inside the interval)
    k, g = 1, 30
    a, b = D0 + timedelta(days=30), D0 + timedelta(days=60)
    s1, s2 = hist["snaps"][_iso(a)], hist["snaps"][_iso(b)]
    i1, i2 = s1["months"].index(k), s2["months"].index(k + 1)
    naive = sum(r2[2 + len(s2["months"]) + i2] - r1[2 + len(s1["months"]) + i1]
                for mo, r1 in s1["m"].items() for r2 in [s2["m"].get(mo)] if r2)
    mature = sum(r2[2 + len(s2["months"]) + i2] - r1[2 + len(s1["months"]) + i1]
                 for mo, r1 in s1["m"].items() for r2 in [s2["m"].get(mo)] if r2 and eng._month_end(mo) <= a)
    assert naive > mature                                         # the open months' new installs would be counted as comebacks
    assert mature == pop.truth(a, b, k)[0]


def test_a_pair_one_day_off_would_be_far_off_which_is_why_it_is_never_used(pop):
    h = _hist(pop, offsets=(0, 29, 30, 31, 32))
    v = {n: eng._view(_iso(D0 + timedelta(days=n)), h["snaps"][_iso(D0 + timedelta(days=n))]) for n in (0, 29, 30, 31, 32)}

    def back(n, k):
        return sum(x[0] for x in eng._measure(v[0], v[n], k).values())
    assert back(30, 1) == pop.truth(D0, D0 + timedelta(days=30), 1)[0]          # the aligned pair: exact
    assert abs(back(29, 1) / back(30, 1) - 1) > 0.1 and abs(back(31, 1) / back(30, 1) - 1) > 0.1
    assert back(31, 2) == pop.truth(D0, D0 + timedelta(days=31), 2)[0]
    assert abs(back(30, 2) / back(31, 2) - 1) > 0.1 and abs(back(32, 2) / back(31, 2) - 1) > 0.1
    assert back(29, 7) > 1.5 * back(30, 7) and back(31, 7) < 0.5 * back(30, 7) and back(32, 7) < 0   # older sleepers: wild


def test_a_pair_one_day_off_is_not_used_and_the_history_is_flagged_short():
    small = Returners(days=420, per_day=10, seed=9)
    h = _hist(small, offsets=(0, 29, 32, 61))                    # 29, 32, 32, 29, 61 … but never 30 or 31 apart
    res = eng.comeback(h)
    assert res["status"] == "too_short" and not res["enough"] and res["snapshots"] == 4
    assert res["ready_on"] == _iso(D0 + timedelta(days=30)) and res["first"] == _iso(D0)
    assert all(r["intervals"] == 0 and r["rate"] is None and r["sleepers"] is None and not r["enough"]
               for r in res["rows"]) and all(b["intervals"] == 0 and b["rate"] is None for b in res["bands"])
    assert res["by_month"] == {}


def test_a_history_too_short_is_flagged_not_guessed():
    small = Returners(days=420, per_day=6, seed=10)
    h = _hist(small, offsets=range(0, 26))                        # 26 daily snapshots: a month is not there yet
    res = eng.comeback(h)
    assert (res["status"], res["enough"], res["snapshots"]) == ("too_short", False, 26)
    assert res["ready_on"] == _iso(D0 + timedelta(days=30))
    one = eng.comeback(_hist(small, offsets=(0,)))
    assert one["status"] == "no_history" and one["snapshots"] == 1 and one["ready_on"] == _iso(D0 + timedelta(days=30))
    for empty in ({}, {"v": 1, "snaps": {}}, None):
        none = eng.comeback(empty)
        assert none["status"] == "no_history" and none["rows"] == [] and none["ready_on"] is None and not none["enough"]
        assert [b["intervals"] for b in none["bands"]] == [0, 0, 0, 0]


def test_a_thin_history_is_measured_but_not_quotable():
    tiny = Returners(days=420, per_day=1, seed=11)
    res = eng.comeback(_hist(tiny))
    assert res["status"] == "thin" and not res["enough"] and res["ready_on"] is None
    assert all(r["intervals"] == 2 and not r["enough"] for r in res["rows"]) and res["rows"][0]["sleepers"] > 0
    loose = eng.comeback(_hist(tiny), min_back=1, min_sleepers=1)
    assert loose["status"] == "ok" and loose["min_back"] == 1


def test_daily_snapshots_chain_earliest_first_and_skip_a_missing_partner():
    small = Returners(days=420, per_day=6, seed=12)
    daily = _hist(small, offsets=range(0, 63))
    res = eng.comeback(daily)
    for r in res["rows"]:
        g = r["gap_days"]
        assert r["intervals"] == 2
        assert r["span"] == [_iso(D0), _iso(D0 + timedelta(days=2 * g))]       # (0, g), (g, 2g): no overlap
    gap = copy.deepcopy(daily)
    del gap["snaps"][_iso(D0 + timedelta(days=30))]               # day 30 never read: 30-day pairs start on day 1
    res = eng.comeback(gap)
    r1, r2 = res["rows"][0], res["rows"][1]                       # k = 1 (30 days): (1, 31), (31, 61); k = 2: as before
    assert r1["span"] == [_iso(D0 + timedelta(days=1)), _iso(D0 + timedelta(days=61))] and r1["intervals"] == 2
    assert r2["span"] == [_iso(D0), _iso(D0 + timedelta(days=62))] and r2["intervals"] == 2    # (31 days: untouched)
    again = eng.comeback(daily)
    assert again == eng.comeback(copy.deepcopy(daily)) and daily == _hist(small, offsets=range(0, 63))   # pure


def test_the_portfolio_sums_counts_and_takes_rates_from_the_sums(result):
    other = eng.comeback(_hist(Returners(days=420, per_day=20, seed=13)))
    short = eng.comeback(_hist(Returners(days=420, per_day=3, seed=14), offsets=(0, 5)))
    port = eng.comeback_portfolio([result, other, short, {"err": "x"}])
    assert (port["apps"], port["measured_apps"], port["skipped"], port["status"]) == (3, 2, 1, "ok")
    assert port["enough"] and port["ready_on"] is None
    for row, a, b in zip(port["rows"], result["rows"], other["rows"]):
        assert row["slept"] == a["slept"] and row["apps"] == 2 and row["intervals"] == 4
        assert row["back_raw"] == a["back_raw"] + b["back_raw"] and row["sleepers"] == a["sleepers"] + b["sleepers"]
        assert row["sleepers_lo"] == a["sleepers_lo"] + b["sleepers_lo"]
        assert row["rate"] == round(row["back"] / row["sleepers"], 4)
        assert row["rate"] != round((a["rate"] + b["rate"]) / 2, 4) or a["rate"] == b["rate"]   # not an average of rates
    for band, a, b in zip(port["bands"], result["bands"], other["bands"]):
        assert band["label"] == a["label"] and band["back_raw"] == a["back_raw"] + b["back_raw"]
    only_short = eng.comeback_portfolio([short, {"err": "x"}])
    assert (only_short["status"], only_short["apps"], only_short["measured_apps"]) == ("too_short", 1, 0)
    assert only_short["ready_on"] == short["ready_on"] and only_short["rows"] == []
    assert all(b["intervals"] == 0 and b["rate"] is None for b in only_short["bands"])
    assert eng.comeback_portfolio([])["status"] == "no_history"


# ── comeback on hand-made snapshots: noise, drift, flags, layout ──────────────────────────────────────

def _snap(rows, months=(1, 2), q=()):
    """A snapshot by hand: rows = {install month: (installs, installed, alive_1, alive_2, act_1, act_2, lo_1, lo_2)}."""
    return {"months": list(months), "m": {mo: list(r) for mo, r in rows.items()}, "q": list(q)}


E1H, E2H = "2026-09-01", "2026-10-01"                              # 30 days apart: month 1 at E1 → month 2 at E2


def test_the_identity_on_hand_made_aggregates_and_the_layout():
    h = {"v": 1, "snaps": {
        E1H: _snap({"2026-03": (1000, 700, 100, 150, 120, 170, 560, 520), "2026-04": (500, 400, 50, 60, 55, 66, 340, 330)}),
        E2H: _snap({"2026-03": (1000, 690, 110, 140, 118, 195, 560, 520), "2026-04": (500, 395, 40, 70, 52, 90, 345, 335)})}}
    res = eng.comeback(h)
    r = res["rows"][0]
    # back = act_2(E2) − act_1(E1): (195 − 120) + (90 − 55) = 110; sleepers = installed − alive_1 = 600 + 350
    assert (r["slept"], r["gap_days"], r["intervals"], r["back_raw"], r["back"]) == (1, 30, 1, 110, 110)
    assert (r["sleepers"], r["sleepers_lo"], r["rate"], r["rate_max"]) == (950, 900, round(110 / 950, 4), round(110 / 900, 4))
    assert res["by_month"] == {"2026-03": {"1": [75, 560, 600]}, "2026-04": {"1": [35, 340, 350]}}
    assert r["span"] == [E1H, E2H] and r["enough"] is True and res["status"] == "ok"        # 110 ≥ 30 of 950 ≥ 200
    thin = eng.comeback(h, min_back=111)
    assert thin["rows"][0]["enough"] is False and thin["status"] == "thin" and thin["rows"][0]["rate"] == r["rate"]
    assert [x["slept"] for x in res["rows"]] == [1]                # k = 2 would need a window 3 this app does not have
    assert res["installs_drift"] == 0 and res["flags"] == []


def test_the_months_wobble_is_summed_not_clamped_and_only_the_total_is_floored():
    def hist(act2):                                      # act_1 = 100 at E1 in every month; act_2 at E2 as given
        return {"v": 1, "snaps": {
            E1H: _snap({mo: (900, 800, 10, 20, 100, 200, 700, 650) for mo in act2}),
            E2H: _snap({mo: (900, 800, 10, 20, 95, a, 700, 650) for mo, a in act2.items()})}}
    res = eng.comeback(hist({"2026-01": 90, "2026-02": 135}), min_back=1, min_sleepers=1)
    r = res["rows"][0]
    assert res["by_month"] == {"2026-01": {"1": [-10, 700, 790]}, "2026-02": {"1": [35, 700, 790]}}
    assert r["back_raw"] == r["back"] == 25 and r["enough"]            # −10 + 35, not 0 + 35 (a clamp per month biases up)
    r = eng.comeback(hist({"2026-01": 60}), min_back=1, min_sleepers=1)["rows"][0]
    assert (r["back_raw"], r["back"], r["rate"], r["enough"]) == (-40, 0, 0.0, False)    # only the total is floored


def test_installs_drift_flags_and_broken_snapshots_are_reported_not_hidden():
    rows1 = {"2026-03": (1000, 700, 100, 150, 120, 170, 560, 520)}
    rows2 = {"2026-03": (1003, 690, 110, 140, 118, 195, 560, 520)}
    h = {E1H: _snap(rows1, q=["thresholded"]), E2H: _snap(rows2, q=["other"]), "garbage": 5, "2026-09-02": {"m": 1},
         "2026-09-03": {"months": [1, 2], "m": {"2026-03": [1, 2]}}}       # the bare snaps dict is accepted too
    res = eng.comeback(h)
    assert res["installs_drift"] == 3 and res["flags"] == ["other", "thresholded"]
    assert res["rows"][0]["q"] == ["other", "thresholded"] and res["rows"][0]["intervals"] == 1
    assert res["snapshots"] == 3                                         # (the broken ones are skipped: 2 good + 1 short row)


def test_a_young_app_has_only_the_rows_its_windows_allow_and_snapshots_may_differ_in_windows():
    two = (100, 80, 40, 70, 45, 75, 10, 5)                              # (installs, installed, alive×2, act×2, lo×2)
    three = (100, 78, 41, 69, 72, 48, 77, 80, 10, 5, 4)                 # (installs, installed, alive×3, act×3, lo×3)
    h = {"v": 1, "snaps": {E1H: _snap({"2026-03": two}, months=(1, 2)),
                           E2H: _snap({"2026-03": three}, months=(1, 2, 3)),
                           "2026-10-31": _snap({"2026-03": three}, months=(1, 2, 3))}}
    res = eng.comeback(h, min_back=1, min_sleepers=1)
    assert [r["slept"] for r in res["rows"]] == [1, 2]                  # k = 3 would need a 4th window nobody has
    k1, k2 = res["rows"]
    # k = 1, 30 days: 1 Sep → 1 Oct (act_2 77 − act_1 45) then 1 Oct → 31 Oct (77 − 48); the columns are found per snapshot
    assert (k1["intervals"], k1["back_raw"], k1["span"]) == (2, (77 - 45) + (77 - 48), [E1H, "2026-10-31"])
    assert (k1["sleepers"], k1["sleepers_lo"]) == ((80 - 40) + (78 - 41), 10 + 10)
    assert k2["intervals"] == 0 and k2["span"] is None and k2["rate"] is None      # k = 2 needs a pair 31 days apart
