"""First open by country (fetch.ga4_firstopen_cc): a day GA4 answers COLLAPSED never replaces a whole one (16 Nov 2026).
A final answer collapsed against the day's earlier read keeps that read (held); a SHORT day — under half of the First
open store's count of the day, a tenth or more of its first opens in no named country, "GA4 named no country" on a day
with first opens, or held — is read again at most RR_MAX finished tries, at least REFRESH_HOURS apart (a try a Stop
cuts waits too), while GA4 still keeps it; GA4's new answer replaces it only when no part of it is smaller (beyond
noise) and it has more first opens in all or by country (or it is the answer a held day waited for); every other day
is due as before; the counts in the log line, over every app with a store. Synthetic data only (this repo is public)."""
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_firstopen_cc as fc
from tests.test_ga4_firstopen_cc import STEPS, TODAY, FakeGa, _fake_api

NOW = datetime(2026, 10, 20, 6, tzinfo=timezone.utc)
D5 = TODAY - timedelta(days=5)
K5 = D5.isoformat()
WHOLE = {"AA": (60, 50, 30), "BB": (40, 30, 20)}          # 100 first opens named + 7 unnamed: [107, 86, 55] on the day


SG = fc.sig(STEPS)                                          # the screens every read below is made with


def _rec(fo, fin=True, at="2026-10-18T00:01:00Z", **k):
    r = {"c": {"AA": [fo, fo, fo]} if fo else {}, "t": [fo, fo, fo], "smp": None, "fin": fin, "sg": SG, "at": at}
    r.update(k)
    return r


def _store(rec, key=K5):
    """Only `key` can be due (pass first=D5): the recent days refreshed an hour ago, the other final days stored whole."""
    s = {"recent_at": "2026-10-20T05:00:00Z", "days": {(TODAY - timedelta(days=i)).isoformat(): _rec(100) for i in (3, 4, 5)}}
    s["days"][key] = rec
    return s


# ── the rules ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_is_short_against_the_first_open_stores_count():
    assert fc.is_short(_rec(3), 100) and fc.is_short(_rec(49), 100)
    assert not fc.is_short(_rec(50), 100) and not fc.is_short(_rec(120), 100)
    assert not fc.is_short(_rec(1), fc.REF_MIN - 1)                 # a small day: not judged against the count
    assert not fc.is_short(_rec(1), None) and not fc.is_short(_rec(1), True)
    assert not fc.is_short(_rec(3, fin=False), 100)                 # read while not final: due()'s "again"
    assert not fc.is_short({"c": {}, "t": [0, 0, 0], "fin": True}, 100)   # all zeros: "again" too
    assert fc.is_short({"none": True, "at": "t"}, 100)              # "GA4 named no country" on a day with first opens
    assert not fc.is_short({"none": True, "at": "t"}, fc.REF_MIN - 1) and not fc.is_short({"none": True}, None)
    assert not fc.is_short({"none": True, "why": "ga4", "n": 1, "fo": {}, "at": "t"}, 100)   # gone: its own rule
    assert not fc.is_short(None, 100)


def test_is_short_when_a_tenth_of_the_first_opens_is_in_no_named_country():
    """The group calls collapsed while the day's total is whole (measured: a whole day's unnamed share stays under 5 %)."""
    def day(fo, named):
        return {"c": {"AA": [named, named, named]}, "t": [fo, fo, fo], "fin": True, "at": "t"}
    assert fc.is_short(day(100, 70), None) and fc.is_short(day(1000, 899), 1000)     # no reference needed
    assert not fc.is_short(day(100, 85), None)                      # 15 unnamed: under REF_MIN
    assert not fc.is_short(day(1000, 901), None)                    # 99 unnamed: under a tenth
    assert not fc.is_short(day(30, 12), None)                       # a small day's 18: under REF_MIN
    assert fc.is_short(_rec(100, ho=1), None)                       # held: short whatever its numbers
    assert not fc.is_short(_rec(100, fin=False, ho=1), None)


def test_is_short_when_a_step_is_in_no_named_country():
    """First opens named, but GA4's group calls lost the splash / home steps of the countries."""
    rec = {"c": {"AA": [60, 2, 1], "BB": [40, 1, 1]}, "t": [107, 86, 55], "fin": True, "sg": SG, "at": "t"}
    assert fc.is_short(rec, 107)
    rec["c"] = {"AA": [60, 50, 30], "BB": [40, 30, 20]}
    assert not fc.is_short(rec, 107)


def test_better_never_takes_an_answer_with_a_smaller_part():
    def r(t, c, sg=SG, **k):
        return dict({"c": c, "t": t, "fin": True, "sg": sg}, **k)
    old = r([45, 37, 27], {"AA": [30, 25, 20], "BB": [10, 8, 5]})
    # more first opens in all, but GA4's group calls named only one country: a collapse, never taken
    assert not fc.better(r([107, 90, 60], {"AA": [5, 4, 3]}), old)
    # more first opens, the splash and home steps collapsed: never taken
    assert not fc.better(r([50, 2, 1], {"AA": [40, 1, 1], "BB": [10, 1, 0]}), old)
    # first opens whole, the countries' splash and home steps collapsed: never taken
    assert not fc.better(r([46, 37, 27], {"AA": [36, 2, 1], "BB": [10, 1, 1]}), old)
    # whole: every part as big or bigger (one user less on a step is GA4's noise)
    assert fc.better(r([107, 36, 55], {"AA": [60, 50, 30], "BB": [40, 30, 20]}), old)
    # the same answer: nothing more — not taken (a held day takes it: the final answer it waited for)
    assert not fc.better(dict(old), old) and fc.better(dict(old), dict(old, ho=1))
    # the same total, more by country (the groups healed): taken
    assert fc.better(r([45, 37, 27], {"AA": [34, 25, 20], "BB": [11, 8, 5]}), old)
    # other screens (the First open store picked them again): the steps do not compare — the first opens do
    assert fc.better(r([50, 5, 2], {"AA": [35, 3, 1], "BB": [15, 2, 1]}, sg="other"), old)
    assert not fc.better(r([50, 40, 30], {"AA": [5, 4, 3]}, sg="other"), old)
    assert not fc.better(None, old) and not fc.better({"none": True}, {"none": True})
    assert fc.better(_rec(5), {"none": True, "at": "t"})


def test_collapsed_against_the_days_earlier_read():
    prev = {"c": {"AA": [800, 700, 500]}, "t": [900, 780, 560], "fin": False, "sg": SG}
    def r(t, c, sg=SG):
        return {"c": c, "t": t, "fin": True, "sg": sg}
    assert fc.collapsed(r([40, 30, 25], {"AA": [30, 25, 20]}), prev)
    assert fc.collapsed(r([905, 790, 570], {"AA": [20, 15, 10]}), prev)            # groups collapsed
    assert fc.collapsed(r([905, 790, 570], {"AA": [810, 5, 2]}), prev)             # the countries' steps collapsed
    assert not fc.collapsed(r([920, 790, 565], {"AA": [820, 710, 505]}), prev)
    assert not fc.collapsed(r([910, 300, 100], {"AA": [810, 290, 90]}, sg="other"), prev)   # a screens change
    assert fc.collapsed(r([40, 30, 25], {"AA": [30, 25, 20]}, sg="other"), prev)   # … its first opens still compare
    assert not fc.collapsed(_rec(5), _rec(15, fin=False))           # under REF_MIN there: never judged


def test_ref_counts_reads_the_first_open_stores_days():
    main = {"days": {"2026-10-15": {"first_open": 120, "splash": 90}, "2026-10-16": {"first_open": None},
                     "2026-10-17": "x"}}
    assert fc.ref_counts(main) == {"2026-10-15": 120, "2026-10-16": 0}
    assert fc.ref_counts(None) == {} and fc.ref_counts({}) == {}


def test_short_due_window_tries_and_wait():
    s = {"days": {K5: _rec(3)}}
    ref = {K5: 100}
    assert fc.short_due(s, TODAY, NOW, ref) == [D5]
    assert fc.short_due(s, TODAY, NOW, None) == [] and fc.short_due(s, TODAY, NOW, {}) == []
    s["days"][K5]["at"] = "2026-10-20T01:00:00Z"                    # answered 5 h ago: not yet
    assert fc.short_due(s, TODAY, NOW, ref) == []
    s["days"][K5].update(at="2026-10-18T00:01:00Z", rat="2026-10-20T03:00:00Z")   # tried 3 h ago: not yet
    assert fc.short_due(s, TODAY, NOW, ref) == []
    s["days"][K5]["rat"] = "2026-10-19T23:00:00Z"
    assert fc.short_due(s, TODAY, NOW, ref) == [D5]
    s["days"][K5]["rr"] = 1                                         # one try done: 12 h now (7 h is not enough)
    assert fc.short_due(s, TODAY, NOW, ref) == [] and fc.short_due(s, TODAY, NOW + timedelta(hours=5), ref) == [D5]
    assert [fc.rr_wait({"rr": i}) for i in range(fc.RR_MAX)] == [6, 12, 24, 48]
    s["days"][K5]["rr"] = fc.RR_MAX                                 # its tries used: never again
    assert fc.short_due(s, TODAY, NOW + timedelta(days=30), ref) == []
    old = TODAY - timedelta(days=fc.AT_RISK_DAYS)                   # GA4 may have deleted it: never read again
    last = TODAY - timedelta(days=fc.AT_RISK_DAYS - 1)              # the oldest day still read again
    edge = TODAY - timedelta(days=fc.FINAL_LAG)                     # the newest final day
    young = TODAY - timedelta(days=fc.FINAL_LAG - 1)                # not final yet
    s = {"days": {old.isoformat(): _rec(3), last.isoformat(): _rec(3), edge.isoformat(): _rec(3),
                  young.isoformat(): {"none": True, "at": "2026-10-18T00:00:00Z"}}}
    ref = {d.isoformat(): 100 for d in (old, last, edge, young)}
    assert fc.short_due(s, TODAY, NOW, ref) == [last, edge]
    assert fc.short_left(s, TODAY, ref) == 2 and fc.short_left(None, TODAY, ref) == 0
    s["days"][old.isoformat()] = _rec(100, ho=1)                    # a held day GA4 may have deleted: kept as it is
    assert fc.short_due(s, TODAY, NOW, ref) == [last, edge]


def test_due_puts_the_short_days_after_the_now_final_ones_before_the_rest_of_the_backfill():
    first = TODAY - timedelta(days=30)
    k4, k6 = (TODAY - timedelta(days=4)).isoformat(), (TODAY - timedelta(days=6)).isoformat()
    s = {"days": {k4: _rec(5, fin=False), K5: _rec(3), k6: _rec(90)}}
    d = fc.due(s, TODAY, NOW, first, {K5: 100, k6: 100, k4: 100})
    assert d[:3] == [TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=2)]
    assert d[3:5] == [TODAY - timedelta(days=4), D5]                # "again", then the short day
    assert d[5] == first and TODAY - timedelta(days=6) not in d     # the backfill after; a whole day never
    assert D5 not in fc.due(s, TODAY, NOW, first)                   # no reference: as before


def test_a_whole_store_with_its_reference_reads_nothing_new():
    """GA4 whole: with the reference every day is ≥ half of it and named — not one day more than without it."""
    store = {"recent_at": "2026-10-20T05:00:00Z",
             "days": {(TODAY - timedelta(days=i)).isoformat(): _rec(100) for i in range(3, 30)}}
    ref = {k: 104 for k in store["days"]}                           # (GA4 late data: a few % more there)
    first = TODAY - timedelta(days=29)
    assert fc.due(store, TODAY, NOW, first, ref) == fc.due(store, TODAY, NOW, first) == []


# ── step_app: the short day read again ──────────────────────────────────────────────────────────────────────────────
def test_a_short_day_is_healed_by_a_whole_answer():
    store, tally = _store(_rec(3)), {}
    ga = FakeGa(data=WHOLE)
    assert fc.step_app(ga, store, STEPS, TODAY, NOW, D5, ref={K5: 107}, tally=tally) == "fetched"
    assert ga.calls == 1 + 1                                        # the day's total + its one group: nothing else
    rec = store["days"][K5]
    assert rec["t"] == [107, 86, 55] and rec["c"] == {"AA": [60, 50, 30], "BB": [40, 30, 20]} and rec["fin"] is True
    assert rec["rr"] == 1 and rec["at"] == "2026-10-20T06:00:00Z" and "rat" not in rec
    assert tally == {"reread": 1, "healed": 1}
    assert fc.short_left(store, TODAY, {K5: 107}) == 0 and fc.short_due(store, TODAY, NOW, {K5: 107}) == []


def test_a_day_whose_groups_collapsed_is_healed_with_the_same_total():
    store, tally = _store({"c": {"AA": [5, 5, 5]}, "t": [107, 86, 55], "fin": True, "at": "2026-10-18T00:01:00Z"}), {}
    fc.step_app(FakeGa(data=WHOLE), store, STEPS, TODAY, NOW, D5, ref={K5: 107}, tally=tally)
    assert store["days"][K5]["c"] == {"AA": [60, 50, 30], "BB": [40, 30, 20]} and tally == {"reread": 1, "healed": 1}


def test_a_short_answer_again_never_replaces_the_stored_day_and_the_tries_end():
    store, ref = _store(_rec(3)), {K5: 107}
    for i, h in enumerate((0, 12, 36, 84)):                         # each try when its wait (6, 12, 24, 48 h) is up
        now = NOW + timedelta(hours=h)
        tally = {}
        fc.step_app(FakeGa(data={"AA": (2, 2, 2)}, unnamed=(0, 0, 0)), store, STEPS, TODAY, now, D5, ref=ref,
                    tally=tally)
        rec = store["days"][K5]
        assert rec["t"] == [3, 3, 3] and rec["c"] == {"AA": [3, 3, 3]} and rec["at"] == "2026-10-18T00:01:00Z"
        assert rec["rr"] == i + 1 and rec["rat"] == fc.gu._now_iso(now) and tally == {"reread": 1}
    assert fc.short_due(store, TODAY, NOW + timedelta(days=30), ref) == []     # RR_MAX tries: never again
    assert fc.short_left(store, TODAY, ref) == 1                              # … still counted: GA4 kept it so


def test_an_answer_with_a_collapsed_part_never_replaces_the_stored_day():
    """GA4's total healed but its group calls named one country only: the stored day stays (the reviewer's case)."""
    old = {"c": {"AA": [30, 25, 20], "BB": [10, 8, 5]}, "t": [45, 37, 27], "fin": True, "at": "2026-10-18T00:01:00Z"}
    store, tally = _store(dict(old)), {}
    fc.step_app(FakeGa(data={"AA": (5, 4, 3)}, unnamed=(102, 86, 57)), store, STEPS, TODAY, NOW, D5, ref={K5: 107},
                tally=tally)
    assert {k: store["days"][K5][k] for k in old} == old and store["days"][K5]["rr"] == 1 and tally == {"reread": 1}


def test_the_noise_allowance_never_adds_up_over_the_tries():
    """Answers each 2 % under the last in all and one more named first open: only the first is within GA4's noise of
    the most the day ever held — the next ones are refused (the day never drifts down try by try)."""
    store = _store({"c": {"AA": [400, 300, 200]}, "t": [1000, 800, 600], "fin": True, "sg": SG,
                    "at": "2026-10-18T00:01:00Z"})              # 600 of 1000 first opens in no country: short
    took = []
    for i, h in enumerate((0, 12, 36, 84)):
        t = [round(v * 0.98 ** (i + 1)) for v in (1000, 800, 600)]
        named = 400 + i + 1
        fc.step_app(FakeGa(data={"AA": (named, 300, 200)}, unnamed=(t[0] - named, t[1] - 300, t[2] - 200)), store, STEPS,
                    TODAY, NOW + timedelta(hours=h), D5, ref={K5: 1000})
        took.append(store["days"][K5]["t"])
    assert took[0] == [980, 784, 588] and took[1:] == [[980, 784, 588]] * 3
    assert store["days"][K5]["pm"][:3] == [1000, 800, 600]           # the most it ever held, carried on


def test_sampled_answers_get_the_sampled_noise_and_never_lock_a_heal_out():
    """GA4 sampled an answer (it read a share of the events): its estimate moves more than 2 % between reads — a whole
    heal a few % under a sampled one is taken; an unsampled day keeps the 2 % rule."""
    def r(t, c, smp=None, **k):
        return dict({"c": c, "t": t, "fin": True, "sg": SG, "smp": smp}, **k)
    held = r([1040, 830, 620], {"AA": [1000, 800, 600]}, smp=0.2, ho=1)       # a sampled estimate, ~4 % high
    heal = r([1005, 805, 600], {"AA": [990, 790, 590]})                       # the whole day, unsampled
    assert fc.better(heal, held)
    assert not fc.better(heal, dict(held, smp=None))                          # unsampled both: 2 % — refused
    assert fc.better(heal, dict(held, smp=None, pms=1))                       # … unless its floor came from a sample
    assert not fc.better(r([500, 400, 300], {"AA": [490, 390, 290]}), held)   # a collapse: refused all the same


def test_pm_steps_follow_the_screens_and_a_cut_try_waits_at_its_level():
    old = {"c": {"AA": [400, 300, 200]}, "t": [1000, 800, 600], "fin": True, "sg": "A", "rr": 2}
    new = {"c": {"AA": [990, 700, 300]}, "t": [995, 760, 320], "fin": True, "sg": "B"}      # other screens
    assert fc.better(new, old)
    assert fc._best(new, old) == [1000, 760, 320, 990, 700, 300]    # first opens' most kept, steps the new screens'
    assert fc.rr_wait({"rr": 2, "rat": "x"}) == 24                  # a try a Stop cut (rr unchanged): 24 h at rr 2


def test_a_held_day_takes_a_final_answer_a_little_under_its_earlier_read():
    k = (TODAY - timedelta(days=3)).isoformat()
    store, tally = _store(_earlier(), key=k), {}
    fc.step_app(FakeGa(data={"AA": (2, 2, 1)}, unnamed=(1, 1, 1)), store, STEPS, TODAY, NOW, D5, tally=tally)
    assert store["days"][k]["ho"] == 1                              # held
    fc.step_app(FakeGa(data={"AA": (58, 48, 29), "BB": (39, 28, 19)}, unnamed=(7, 6, 5)), store, STEPS, TODAY,
                NOW + timedelta(hours=6), D5, tally=tally)           # the final answer: one home user fewer by country
    rec = store["days"][k]
    assert "ho" not in rec and rec["t"] == [104, 82, 53] and rec["pm"][4] == 77 and tally["healed"] == 1


def test_a_better_but_still_short_answer_replaces_the_day_and_is_tried_again_later():
    store, ref, tally = _store(_rec(3)), {K5: 107}, {}
    fc.step_app(FakeGa(data={"AA": (20, 10, 5)}, unnamed=(0, 0, 0)), store, STEPS, TODAY, NOW, D5, ref=ref,
                tally=tally)
    rec = store["days"][K5]
    assert rec["t"][0] == 20 and rec["rr"] == 1 and tally == {"reread": 1}       # not healed: still under half
    assert fc.short_due(store, TODAY, NOW + timedelta(hours=11), ref) == []     # one try done: 12 h
    assert fc.short_due(store, TODAY, NOW + timedelta(hours=12), ref) == [D5]
    fc.step_app(FakeGa(data=WHOLE), store, STEPS, TODAY, NOW + timedelta(hours=12), D5, ref=ref, tally=tally)
    assert store["days"][K5]["t"][0] == 107 and store["days"][K5]["rr"] == 2 and tally == {"reread": 2, "healed": 1}


def test_no_country_or_an_empty_funnel_again_keeps_the_stored_day():
    class NoCountry(FakeGa):
        def report_all(self, body, event=None, **k):
            return []
    store, ref, tally = _store(_rec(3)), {K5: 107}, {}
    ga = NoCountry(data=WHOLE)
    fc.step_app(ga, store, STEPS, TODAY, NOW, D5, ref=ref, tally=tally)
    assert ga.calls == 0 and store["days"][K5]["t"] == [3, 3, 3] and store["days"][K5]["rr"] == 1   # never "none"
    assert tally == {"reread": 1}

    class EmptyFunnel(FakeGa):
        def funnel(self, body):
            self.calls += 1
            return {"funnelTable": {"rows": []}}
    store, tally = _store(_rec(3)), {}
    ga = EmptyFunnel(data=WHOLE)
    fc.step_app(ga, store, STEPS, TODAY, NOW, D5, ref=ref, tally=tally)
    assert ga.calls == 1                                            # the day's total only: GA4 answered it empty
    assert store["days"][K5]["t"] == [3, 3, 3] and store["days"][K5]["rr"] == 1 and tally == {"reread": 1}


def test_a_try_a_stop_cuts_waits_like_any_other_and_uses_no_try():
    class Cut(FakeGa):
        def funnel(self, body):
            if self.calls >= 1:                                     # the group call: the run's clock ran out
                raise gf.Stop("budget")
            return super().funnel(body)
    store = _store(_rec(3))
    with pytest.raises(gf.Stop):
        fc.step_app(Cut(data=WHOLE), store, STEPS, TODAY, NOW, D5, ref={K5: 107}, tally={})
    rec = store["days"][K5]
    assert rec["t"] == [3, 3, 3] and rec["rat"] == "2026-10-20T06:00:00Z" and "rr" not in rec
    assert fc.short_due(store, TODAY, NOW + timedelta(hours=1), {K5: 107}) == []     # not again next hour
    assert fc.short_due(store, TODAY, NOW + timedelta(hours=6), {K5: 107}) == [D5]


def test_a_no_country_day_with_first_opens_is_read_again_and_filled():
    store, tally = _store({"none": True, "at": "2026-10-18T00:01:00Z"}), {}
    fc.step_app(FakeGa(data=WHOLE), store, STEPS, TODAY, NOW, D5, ref={K5: 107}, tally=tally)
    rec = store["days"][K5]
    assert not rec.get("none") and rec["t"][0] == 107 and len(rec["c"]) == 2 and tally == {"reread": 1, "healed": 1}
    # a small day stored so (under REF_MIN first opens in the First open store): left as it was
    store = _store({"none": True, "at": "2026-10-18T00:01:00Z"})
    assert fc.step_app(FakeGa(data=WHOLE), store, STEPS, TODAY, NOW, D5, ref={K5: fc.REF_MIN - 1}) == "fresh"
    assert store["days"][K5] == {"none": True, "at": "2026-10-18T00:01:00Z"}


def test_a_short_day_that_does_not_fit_the_call_cap_is_not_begun():
    store = _store(_rec(3))
    ga = FakeGa(data=WHOLE)
    ga.max_calls = 2                                                # the day needs 1 + 1 calls; 1 left
    ga.calls = 1
    with pytest.raises(gf.Stop):
        fc.step_app(ga, store, STEPS, TODAY, NOW, D5, ref={K5: 107}, tally={})
    assert store["days"][K5] == _rec(3) and ga.calls == 1           # nothing begun, nothing changed


def test_the_real_app_reads_a_short_day_whole_within_its_cap(monkeypatch):
    """The real gf.App with ~150 countries (11 calls a day): a short day is read again whole in one run."""
    call, seen = _fake_api(150)
    monkeypatch.setattr(fc.ga4, "_call", call)
    monkeypatch.setattr(fc.ga4, "_sleep", lambda s: None)
    today = date(2026, 10, 21)
    d = today - timedelta(days=5)
    whole = {"c": {"Q%03d" % i: [4, 3, 2] for i in range(150)}, "t": [600, 450, 300], "fin": True,
             "at": "2026-10-19T00:00:00Z"}
    store = {"v": fc.STORE_V, "recent_at": "2026-10-21T05:00:00Z",
             "days": {(today - timedelta(days=i)).isoformat(): dict(whole) for i in range(3, 20)}}
    store["days"][d.isoformat()] = {"c": {"Q000": [1, 1, 1]}, "t": [1, 1, 1], "fin": True, "at": "2026-10-19T00:00:00Z"}
    ga = gf.App("t", "p", "s", {"quota": None, "stop": None}, max_calls=fc.MAX_CALLS)
    tally = {}
    fc.step_app(ga, store, STEPS, today, datetime(2026, 10, 21, 6, tzinfo=timezone.utc), today - timedelta(days=19),
                ref={d.isoformat(): 600}, tally=tally)
    rec = store["days"][d.isoformat()]
    assert len(rec["c"]) == 150 and rec["rr"] == 1                  # every country now: taken
    assert tally == {"reread": 1}                                   # (the fake's day total, 4, is still short)
    assert seen.count(d) == fc.calls_for(range(150)) and len(set(seen)) == 1   # one whole read of that day only


# ── step_app: the final read held ───────────────────────────────────────────────────────────────────────────────────
def _earlier():
    """The day as the recent refresh read it two days old (not final): whole."""
    return {"c": {"AA": [58, 48, 29], "BB": [39, 29, 19]}, "t": [104, 83, 53], "smp": None, "fin": False, "sg": SG,
            "at": "2026-10-17T18:00:00Z"}


def test_a_final_answer_collapsed_against_the_days_earlier_read_keeps_that_read():
    k = (TODAY - timedelta(days=3)).isoformat()
    store, tally = _store(_earlier(), key=k), {}
    fc.step_app(FakeGa(data={"AA": (2, 2, 1)}, unnamed=(1, 1, 1)), store, STEPS, TODAY, NOW, D5, tally=tally)
    assert store["days"][k] == dict(_earlier(), fin=True, ho=1, rat="2026-10-20T06:00:00Z") and tally == {"held": 1}
    assert fc.short_due(store, TODAY, NOW + timedelta(hours=5), None) == []
    assert fc.short_due(store, TODAY, NOW + timedelta(hours=6), None) == [TODAY - timedelta(days=3)]
    # 6 h on GA4 answers it whole: the final answer it waited for replaces it (held no more)
    fc.step_app(FakeGa(data=WHOLE), store, STEPS, TODAY, NOW + timedelta(hours=6), D5, tally=tally)
    rec = store["days"][k]
    assert rec["t"] == [107, 86, 55] and rec["fin"] is True and "ho" not in rec and rec["rr"] == 1
    assert tally == {"held": 1, "reread": 1, "healed": 1}


def test_a_final_answer_naming_no_country_keeps_the_days_earlier_read():
    class NoCountry(FakeGa):
        def report_all(self, body, event=None, **k):
            return []
    k = (TODAY - timedelta(days=3)).isoformat()
    store, tally = _store(_earlier(), key=k), {}
    fc.step_app(NoCountry(data=WHOLE), store, STEPS, TODAY, NOW, D5, tally=tally)
    assert store["days"][k] == dict(_earlier(), fin=True, ho=1, rat="2026-10-20T06:00:00Z") and tally == {"held": 1}


def test_a_final_answer_with_the_countries_steps_collapsed_is_held():
    k = (TODAY - timedelta(days=3)).isoformat()
    store, tally = _store(_earlier(), key=k), {}
    fc.step_app(FakeGa(data={"AA": (60, 2, 1), "BB": (40, 1, 1)}, unnamed=(7, 83, 53)), store, STEPS, TODAY, NOW, D5,
                tally=tally)
    assert store["days"][k]["t"] == [104, 83, 53] and store["days"][k]["ho"] == 1 and tally == {"held": 1}


def test_an_empty_funnel_at_the_final_read_is_held_and_never_read_every_run():
    """GA4's funnel empty from the final read on (its report still naming the countries): the earlier read is kept and
    read again RR_MAX times, ≥ REFRESH_HOURS apart — not every hourly run until GA4 deletes the day."""
    class Empty(FakeGa):
        def funnel(self, body):
            self.calls += 1
            self.bodies.append(body)
            return {"funnelTable": {"rows": []}}
    k = (TODAY - timedelta(days=3)).isoformat()
    store, tally, calls = _store(_earlier(), key=k), {}, 0
    for h in range(120):                                            # five days of hourly runs (tries at +6, 18, 42, 90 h)
        now = NOW + timedelta(hours=h)
        ga = Empty(data=WHOLE)
        fc.step_app(ga, store, STEPS, now.date(), now, D5, tally=tally)
        calls += sum(1 for b in ga.bodies if b["dateRanges"][0]["startDate"] == k)
    rec = store["days"][k]
    assert {f: rec[f] for f in ("c", "t", "at")} == {f: _earlier()[f] for f in ("c", "t", "at")}
    assert rec["fin"] is True and rec["ho"] == 1 and rec["rr"] == fc.RR_MAX
    assert calls == 1 + fc.RR_MAX and tally["held"] == 1 and tally["reread"] == fc.RR_MAX


def test_a_recent_day_is_never_held():
    k = (TODAY - timedelta(days=1)).isoformat()
    store = _store(_earlier(), key=k)
    store.pop("recent_at")                                          # the recent refresh is due
    fc.step_app(FakeGa(data={"AA": (2, 2, 1)}, unnamed=(1, 1, 1)), store, STEPS, TODAY, NOW, D5, tally={})
    assert store["days"][k]["t"] == [3, 3, 2] and store["days"][k]["fin"] is False and "ho" not in store["days"][k]


def test_a_whole_final_answer_replaces_the_earlier_read_as_before():
    k = (TODAY - timedelta(days=3)).isoformat()
    store, tally = _store(_earlier(), key=k), {}
    fc.step_app(FakeGa(data=WHOLE), store, STEPS, TODAY, NOW, D5, tally=tally)
    rec = store["days"][k]
    assert rec["t"] == [107, 86, 55] and rec["fin"] is True and "ho" not in rec and "rr" not in rec and tally == {}
    # a small day (under REF_MIN in every part): its final answer is taken as it is, as before
    store = _store({"c": {"AA": [9, 8, 7]}, "t": [9, 8, 7], "fin": False, "at": "2026-10-17T18:00:00Z"}, key=k)
    fc.step_app(FakeGa(data={"AA": (1, 1, 1)}, unnamed=(0, 0, 0)), store, STEPS, TODAY, NOW, D5)
    assert store["days"][k]["t"] == [1, 1, 1] and store["days"][k]["fin"] is True


# ── refresh_all and the log line ────────────────────────────────────────────────────────────────────────────────────
def _one_app(tmp_path, monkeypatch, step=None):
    from admob_iq.db import write_json_gz_stable
    from admob_iq.fetch import ga4_uninstall as gu
    aid = "ca-app-pub-0~a"
    main = {"v": gf.STORE_V, "app_id": aid, "steps": STEPS, "time_zone": "UTC",
            "days": {K5: {"first_open": 107}, "2026-10-01": {"first_open": 90}}}
    os.makedirs(os.path.join(str(tmp_path), fc.DIR), exist_ok=True)
    write_json_gz_stable(gf.store_path(str(tmp_path), aid), main)
    write_json_gz_stable(fc.store_path(str(tmp_path), aid), {"v": fc.STORE_V, "days": {K5: _rec(3)}})
    if step:
        monkeypatch.setattr(fc, "step_app", step)
    monkeypatch.setattr(gf, "App", lambda tok, pid, sid, prop, over=None, max_calls=gf.MAX_CALLS:
                        type("A", (), {"calls": 0, "tok": 0, "property_id": pid})())
    monkeypatch.setattr(fc.ga4, "access_token", lambda *a: "tok")
    monkeypatch.setattr(fc.ga4_probe, "owner_tokens", lambda env: ([("o", "rt")], None))
    monkeypatch.setattr(gu, "load_state", lambda d: {"routes": {"by_package": {"pkg.a": {
        "property_id": "P1", "stream_id": "s", "owner": "o"}}}, "tz": {}})
    return aid


def test_refresh_all_passes_the_first_open_counts_and_counts_the_short_days(tmp_path, monkeypatch):
    got = {}

    def step(ga, store, steps, today, now, first=None, ref=None, tally=None):
        got.update(ref=ref, first=first)
        tally["reread"], tally["healed"], tally["held"] = 2, 1, 1
        store["days"][K5]["rr"] = 1                             # (no call made: the try is kept all the same)
        return "fetched"
    aid = _one_app(tmp_path, monkeypatch, step)
    out = fc.refresh_all({"client_id": "c", "client_secret": "s", "refresh_tokens": "x"}, str(tmp_path),
                         [{"app_id": aid, "package": "pkg.a"}], now=NOW, workers=1)
    assert got["ref"] == {K5: 107, "2026-10-01": 90} and got["first"] == date(2026, 10, 1)
    c = out["counts"]
    assert (c["held"], c["reread"], c["healed"], c["short"]) == (1, 2, 1, 1)    # K5 still short: left 1
    assert fc.load_store(fc.store_path(str(tmp_path), aid))["days"][K5]["rr"] == 1   # saved with no call made
    assert "held 1, short read again 2, healed 1, short left 1, calls 0" in fc.log_line(out)


def test_an_app_not_read_this_run_keeps_its_short_days_counted(tmp_path, monkeypatch):
    aid = _one_app(tmp_path, monkeypatch)
    out = fc.refresh_all({"client_id": "c", "client_secret": "s", "refresh_tokens": "x"}, str(tmp_path),
                         [{"app_id": aid, "package": "pkg.a"}], now=NOW, budget=0, workers=1)
    assert out["apps"][aid] == "deferred" and out["counts"]["short"] == 1    # never a silent 0


def test_log_line_names_the_short_counts():
    line = fc.log_line({"counts": dict.fromkeys(fc.COUNTS, 3)})
    assert "held 3, short read again 3, healed 3, short left 3" in line and line.count("3") == len(fc.COUNTS)
