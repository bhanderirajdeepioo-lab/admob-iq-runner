"""Audience engine (admob_iq.engine.audience) — pure, synthetic data only: installed / alive / dead per install day,
month, app and portfolio; uninstalls INSIDE a window taken out of GA4's actives (from the cohort offsets); the exact
answer when every uninstaller opened first, an upper / lower bound when some did not; the buckets 1..6, 7-12, 12+;
young cells; clamps marked (never silent); the most dead / active install month; DAU on E by install month."""

from datetime import date, timedelta

import pytest

from admob_iq.engine import audience as eng
from tests.audience_synth import E, Population

W = [eng.window_days(n) for n in range(1, 15)]


def _iso(d):
    return d.isoformat()


def test_window_n_is_floor_of_n_months():
    assert [eng.window_days(n) for n in range(1, 13)] == [30, 60, 91, 121, 152, 182, 213, 243, 273, 304, 334, 365]
    assert eng.window_days(24) == 730 and eng.window_days(36) == 1095


def test_every_install_day_is_exact_when_every_uninstaller_opened_first():
    pop = Population(days=400, per_day=12, dormant_un=0.0)
    uni, aud = pop.uni_store(), pop.aud_store()
    out = eng.derive_app(aud, uni, per_day=True)
    assert out["E"] == _iso(E) and out["windows"][:14] == W and out["full"] is True
    assert out["months_n"] == len(aud["windows"]) >= 12
    for x, cell in out["per_day"].items():
        xd = date.fromisoformat(x)
        for i, w in enumerate(aud["windows"]):
            want = pop.true_dead(xd, w) if (E - xd).days >= w else 0
            assert cell["dead"][i] == want, (x, w)
        assert cell["marks"] == {}
    # the totals are the days' sums; buckets are differences of dead(N)
    d = out["dead"]
    assert out["buckets"] == {"1": d[0] - d[1], "2": d[1] - d[2], "3": d[2] - d[3], "4": d[3] - d[4],
                              "5": d[4] - d[5], "6": d[5] - d[6], "7-12": d[6] - d[11], "12+": d[11]}
    assert all(v >= 0 for v in out["buckets"].values()) and sum(out["buckets"].values()) == d[0]
    assert out["installed"] == out["installs"] - out["uninstalled"]
    assert all(out["alive"][i] + out["dead"][i] == out["installed"] for i in range(out["months_n"]))
    assert sum(g["installs"] for g in out["months"].values()) == out["installs"]
    assert sum(g["dead"][2] for g in out["months"].values()) == out["dead"][2]
    assert out["impossible"] == {} and out["clamped"] == {}
    assert out["checks"]["young_cov"] == 1.0 and set(out["checks"]["split_cov"]) == {1.0}


def test_dormant_uninstallers_make_dead_an_upper_bound_and_dead_lo_a_lower_bound():
    pop = Population(days=400, per_day=12, dormant_un=0.6, seed=11)
    out = eng.derive_app(pop.aud_store(), pop.uni_store(), per_day=True)
    over = 0
    for x, cell in out["per_day"].items():
        xd = date.fromisoformat(x)
        for i, w in enumerate(out["windows"][:len(cell["act"])]):
            if (E - xd).days < w:
                continue
            truth = pop.true_dead(xd, w)
            assert cell["dead"][i] >= truth
            over += cell["dead"][i] - truth
    assert over > 0                                                  # the approximation's bias is real here …
    for g in [out] + list(out["months"].values()):                   # … and the lower bound holds in every total
        assert all(lo <= hi for lo, hi in zip(g["dead_lo"], g["dead"]))
    w3 = out["windows"][2]
    truth3 = sum(pop.true_dead(date.fromisoformat(x), w3) for x in out["per_day"])
    assert out["dead_lo"][2] <= truth3 <= out["dead"][2]


def _one_day(x, n, lags, act, windows=None):
    """An Audience + Uninstall store holding one install day x."""
    windows = windows or W[:3]
    uni = {"history_start": _iso(x), "window_end": _iso(E + timedelta(days=3)),
           "daily": {_iso(x): {"new": n, "a1": 0}}, "cohorts": {_iso(x): {str(k): v for k, v in lags.items()}}}
    aud = {"E": _iso(E), "windows": windows, "by_fsd": {_iso(x): act}}
    return aud, uni


def test_uninstalls_inside_the_window_come_out_of_the_actives_by_their_cohort_offset():
    x = E - timedelta(days=100)                     # 100 days old: windows 30 and 60 are after it, 91 too
    # 20 installs; 4 gone on day 0 (before every window), 3 on day 50 (age 50 = 50 days before E: inside the 60- and
    # 91-day windows, not the 30-day one), 2 on day 90 (10 days before E: inside all three), 1 after E (not yet)
    lags = {0: 4, 50: 3, 90: 2, 103: 1}
    aud, uni = _one_day(x, 20, lags, [7, 10, 12])
    out = eng.derive_app(aud, uni, per_day=True)
    c = out["per_day"][_iso(x)]
    assert c["U"] == 9 and c["I"] == 11                              # the uninstall after E is not counted
    assert out["un_in"][:3] == [2, 5, 5]
    assert c["alive"][:3] == [7 - 2, 10 - 5, 12 - 5]
    assert c["dead"][:3] == [11 - 5, 11 - 5, 11 - 7]
    assert out["dead_lo"][:3] == [11 - 7, 11 - 10, 11 - 11]          # (nobody who uninstalled had opened)
    assert c["dead"][3:] == [0] * (len(c["dead"]) - 3)               # 121 days and longer: the day is inside: young


def test_young_install_days_are_never_dead_whatever_ga4_says():
    x = E - timedelta(days=10)
    aud, uni = _one_day(x, 50, {0: 5, 4: 5}, [3, 3, 3])              # a short (noisy) split must not make them dead
    out = eng.derive_app(aud, uni, per_day=True)
    c = out["per_day"][_iso(x)]
    assert c["I"] == 40 and c["alive"][:3] == [40, 40, 40] and c["dead"] == [0] * len(c["dead"])
    assert out["young_days"][:3] == [1, 1, 1] and out["impossible"] == {} and out["clamped"] == {}
    assert out["checks"]["young_cov"] == round(3 / 50, 4)           # … but the split check shows it


@pytest.mark.parametrize("case", ["un_gt_new", "act_gt_inst", "un_gt_act", "non_mono"])
def test_impossible_and_clamped_cells_are_clamped_at_zero_and_marked(case):
    x = E - timedelta(days=200)                     # windows 1..6 (≤ 182 days) after it; window 7 (213) holds it
    n, lags, act = {
        "un_gt_new": (5, {0: 4, 190: 3}, [3] * 7),                   # 7 uninstalls of 5 installs
        "act_gt_inst": (10, {0: 6}, [9] * 7),                         # 9 active of 4 installed
        "un_gt_act": (10, {195: 4}, [1] * 7),                         # 4 window uninstalls, 1 active
        "non_mono": (10, {}, [6, 4, 7, 7, 7, 7, 7]),                  # a longer window with fewer actives
    }[case]
    out = eng.derive_app(*_one_day(x, n, lags, act, W[:7]), per_day=True)
    c = out["per_day"][_iso(x)]
    assert all(v >= 0 for v in c["alive"] + c["dead"]) and c["I"] >= 0
    assert all(c["alive"][i] <= c["I"] for i in range(len(c["alive"])))
    assert all(c["alive"][i] <= c["alive"][i + 1] for i in range(len(c["alive"]) - 1))
    assert c["dead"][6:] == [0] * 6                                  # young from window 7 on
    if case == "un_gt_new":
        assert c["I"] == 0 and out["impossible"]["un_gt_new"] == [1, 2] and c["marks"]["0"] == "un_gt_new"
        assert c["dead"] == [0] * 12
    elif case == "act_gt_inst":
        assert c["alive"][:6] == [4] * 6 and out["impossible"]["act_gt_inst"] == [6, 30]
        assert c["marks"] == {str(i): "act_gt_inst" for i in range(1, 7)}
    elif case == "un_gt_act":
        assert c["alive"][:6] == [0] * 6 and c["dead"][:6] == [6] * 6
        assert out["clamped"]["un_gt_act"] == [6, 18] and out["impossible"] == {}
    else:
        assert c["alive"][:6] == [6, 6, 7, 7, 7, 7] and out["clamped"]["non_mono"] == [1, 2]
        assert c["marks"] == {"2": "non_mono"}
    assert out["flags"]["impossible_cells"] == sum(v[0] for v in out["impossible"].values())
    assert out["flags"]["clamped_cells"] == sum(v[0] for v in out["clamped"].values())


def test_a_window_the_store_lacks_is_none_never_guessed():
    x = E - timedelta(days=200)
    aud, uni = _one_day(x, 10, {}, [5, 6, 7])                       # only 3 windows (91 days) for a 200-day-old day
    out = eng.derive_app(aud, uni)
    assert out["full"] is False and out["dead"][:3] == [5, 4, 3]
    assert out["dead"][3:6] == [None] * 3 and out["missing_days"][3] == 1
    assert out["buckets"]["1"] == 1 and out["buckets"]["4"] is None and out["buckets"]["6"] is None
    assert out["buckets"]["12+"] == 0                                # (365 days: the day is inside — young)
    assert eng.derive_app(aud, uni, per_day=True)["per_day"][_iso(x)]["dead"][3] is None


def test_a_young_app_holds_every_bucket_past_its_windows_at_zero():
    pop = Population(days=70, per_day=10)
    out = eng.derive_app(pop.aud_store(), pop.uni_store())
    assert len(pop.aud_store()["windows"]) == 3 and out["full"] and out["months_n"] == 12
    assert out["dead"][3:] == [0] * 9 and out["buckets"]["12+"] == 0 and out["buckets"]["7-12"] == 0


def _month_store(spec):
    """{install day: (installs, actives in windows 1..3)} → stores (no uninstalls)."""
    uni = {"history_start": min(spec), "window_end": _iso(E), "cohorts": {},
           "daily": {x: {"new": n, "a1": 0} for x, (n, _) in spec.items()}}
    aud = {"E": _iso(E), "windows": W[:3], "by_fsd": {x: a for x, (_, a) in spec.items()}}
    return aud, uni


def test_most_dead_and_most_active_install_month_by_count_and_share_mature_months_only():
    spec = {"2026-05-10": (1000, [100, 150, 200]),    # May: 900 dead ≥ 1 month, 10% active
            "2026-06-10": (400, [320, 330, 340]),     # June: 80 dead, 80% active — the most active by share
            "2026-07-10": (50, [1, 2, 3]),            # July: 98% dead but only 50 installs — too small for a share
            "2026-07-20": (1500, [1200, 1300, 1400]),  # (July together: 1550 installs, 349 dead, 1201 active)
            "2026-09-01": (5000, [5000, 5000, 5000])}  # September: inside window 1 — not mature, never "most"
    out = eng.derive_app(*_month_store(spec))
    mo = out["months"]
    assert mo["2026-09"]["young_days"][0] == 1 and mo["2026-07"]["dead"][0] == 49 + 300
    m = out["most"]
    assert m["dead"]["count"] == {"month": "2026-05", "users": 900, "installs": 1000, "share": 0.9}
    assert m["dead"]["share"]["month"] == "2026-05"
    assert m["active"]["count"] == {"month": "2026-07", "users": 1201, "installs": 1550, "share": 0.7748}
    assert m["active"]["share"] == {"month": "2026-06", "users": 320, "installs": 400, "share": 0.8}


def test_a_small_month_never_wins_a_share_and_ties_go_to_the_earlier_month():
    spec = {"2026-04-10": (50, [0, 0, 0]), "2026-05-10": (200, [100, 100, 100]), "2026-06-10": (200, [100, 100, 100])}
    m = eng.derive_app(*_month_store(spec))["most"]
    assert m["dead"]["share"]["month"] == "2026-05" and m["dead"]["count"]["month"] == "2026-05"
    spec = {"2026-05-10": (200, [200, 200, 200])}                    # nothing dead → no "most dead"
    assert eng.derive_app(*_month_store(spec))["most"]["dead"] == {"count": None, "share": None}


def test_dau_on_e_by_install_month_keeps_history_other_and_not_set_apart():
    pop = Population(days=120, per_day=8, seed=3)
    aud, uni = pop.aud_store(), pop.uni_store()
    aud["dau_by_fsd"] = {"2026-01-05": 4, "2026-07-01": 6, "2026-07-30": 1, "2026-09-20": 9}
    aud["dau"] = {"total": 25, "other": 3, "not_set": 2}
    out = eng.derive_app(aud, uni)
    d = out["dau"]
    assert d["day"] == _iso(E) and d["by_month"] == {"2026-07": 7, "2026-09": 9}
    assert (d["before_history"], d["other"], d["not_set"], d["users"], d["ga4_total"]) == (4, 3, 2, 25, 25)
    assert d["store_a1"] == uni["daily"][_iso(E)]["a1"] and d["cov"] == round(25 / d["store_a1"], 4)


def test_uninstall_store_gaps_are_flagged():
    pop = Population(days=100, per_day=5)
    uni = pop.uni_store(window_end=E - timedelta(days=2))
    uni["flags"] = {"incomplete_days": {_iso(E - timedelta(days=5)): 0.5, "2020-01-01": 0.1}}
    uni["unplaced"] = {_iso(E - timedelta(days=4)): 3}
    uni["history_capped"] = True
    f = eng.derive_app(pop.aud_store(), uni)["flags"]
    assert (f["un_days_missing"], f["un_incomplete_days"], f["un_unplaced"], f["history_capped"]) == (2, 1, 3, True)


def test_actives_installed_before_the_history_are_shown_apart():
    pop = Population(days=100, per_day=5)
    aud = pop.aud_store()
    aud["by_fsd"]["2020-01-01"] = [1, 2, 3, 4]
    out = eng.derive_app(aud, pop.uni_store())
    assert out["before_history"] == [1, 2, 3, 4]
    assert out["installs"] == len(pop.users)


def test_portfolio_sums_apps_by_calendar_month_and_extends_a_young_app():
    old = eng.derive_app(*(lambda p: (p.aud_store(), p.uni_store()))(Population(days=400, per_day=6, seed=1)))
    young = eng.derive_app(*(lambda p: (p.aud_store(), p.uni_store()))(Population(days=45, per_day=9, seed=2)))
    p = eng.portfolio([old, young, {"err": {"type": "KeyError"}}])
    assert p["apps"] == 2 and p["skipped"] == 1 and p["months_n"] == old["months_n"]
    assert p["installs"] == old["installs"] + young["installs"]
    for i in range(p["months_n"]):
        y = young["alive"][i] if i < young["months_n"] else young["installed"]
        assert p["alive"][i] == old["alive"][i] + y
        assert p["dead"][i] == old["dead"][i] + (young["dead"][i] if i < young["months_n"] else 0)
    sep = "2026-09"
    assert p["months"][sep]["installs"] == old["months"][sep]["installs"] + young["months"][sep]["installs"]
    assert p["buckets"] == {k: old["buckets"][k] + young["buckets"][k] for k in old["buckets"]}
    assert p["E_min"] == p["E_max"] == _iso(E)
    assert p["most"]["dead"]["count"]["month"] in p["months"]
    assert p["dau"]["users"] == old["dau"]["users"] + young["dau"]["users"]
    assert eng.portfolio([])["apps"] == 0
