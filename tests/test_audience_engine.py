"""Audience engine (admob_iq.engine.audience) — pure, synthetic data only: installed / alive / dead per install day,
month, app and portfolio; uninstalls INSIDE a window taken out of GA4's actives (from the cohort offsets); the exact
answer when every uninstaller opened first, the dead range [dead_lo, dead] around the truth when some did not; the
tiered windows (monthly to 12, quarterly to 24, then half-yearly) and the last-open buckets 1 … 12, 13-15 …; young
cells; clamps marked (never silent) with the clean-up uninstalls they prove; the most dead / active install month; DAU on
E by install month."""

from datetime import date, timedelta

import pytest

from admob_iq.engine import audience as eng
from tests.audience_synth import E, Population

M7 = [1, 2, 3, 4, 5, 6, 7]


def _iso(d):
    return d.isoformat()


def test_window_n_is_floor_of_n_months():
    assert [eng.window_days(n) for n in range(1, 13)] == [30, 60, 91, 121, 152, 182, 213, 243, 273, 304, 334, 365]
    assert eng.window_days(24) == 730 and eng.window_days(36) == 1095


@pytest.mark.parametrize("age,want", [
    (1, [1]), (30, [1]), (31, [1, 2]), (365, list(range(1, 13))), (366, list(range(1, 13)) + [15]),
    (730, list(range(1, 13)) + [15, 18, 21, 24]), (731, list(range(1, 13)) + [15, 18, 21, 24, 30]),
    (1300, list(range(1, 13)) + [15, 18, 21, 24, 30, 36, 42, 48])])
def test_windows_are_monthly_to_a_year_quarterly_to_two_then_half_yearly(age, want):
    assert eng.tier_months(age) == want
    assert eng.window_days(want[-1]) >= age and (len(want) == 1 or eng.window_days(want[-2]) < age)


def test_last_open_buckets_are_labelled_by_the_months_since_the_last_open():
    labels = [b[0] for b in eng.last_open_bins(list(range(1, 13)) + [15, 18, 21, 24, 30, 36])]
    assert labels == [str(n) for n in range(1, 13)] + ["13-15", "16-18", "19-21", "22-24", "25-30", "31-36", "37+"]
    assert eng.last_open_bins([1, 2])[0] == ("1", 0, 1) and eng.last_open_bins([1, 2])[-1] == ("3+", 2, None)


def test_every_install_day_is_exact_when_every_uninstaller_opened_first():
    pop = Population(days=500, per_day=10, dormant_un=0.0)
    uni, aud = pop.uni_store(), pop.aud_store()
    assert aud["months"] == list(range(1, 13)) + [15, 18]
    out = eng.derive_app(aud, uni, per_day=True)
    assert out["E"] == _iso(E) and out["months"] == aud["months"] and out["full"] is True
    for x, cell in out["per_day"].items():
        xd = date.fromisoformat(x)
        for i, w in enumerate(aud["windows"]):
            want = pop.true_dead(xd, w) if (E - xd).days >= w else 0
            assert cell["dead"][i] == want >= cell["dead_lo"][i], (x, w)
        assert cell["marks"] == {}
    d, inst = out["dead"], out["installed"]
    lo = out["last_open"]
    assert [b["label"] for b in lo] == [str(n) for n in range(1, 13)] + ["13-15", "16-18", "19+"]
    assert lo[0]["users"] == out["alive"][0] == inst - d[0] and lo[1]["users"] == d[0] - d[1]
    assert lo[12]["users"] == d[11] - d[12] and lo[-1]["users"] == d[-1] == 0          # the last window holds it all
    assert sum(b["users"] for b in lo) == inst and all(b["users"] >= 0 for b in lo)
    assert inst == out["installs"] - out["uninstalled"]
    assert all(out["alive"][i] + d[i] == inst for i in range(len(d)))
    assert sum(g["installs"] for g in out["months_by"].values()) == out["installs"]
    assert sum(g["dead"][2] for g in out["months_by"].values()) == d[2]
    assert out["impossible"] == {} and out["clamped"] == {} and out["clamps_by_month"] == {}
    assert out["checks"]["young_cov"] == 1.0 and set(out["checks"]["split_cov"]) == {1.0}


def _clean_up_uninstallers(pop, w):
    """Distinct users who uninstalled inside the last w days without opening in them (installed before the window)."""
    s = E - timedelta(days=w - 1)
    return sum(1 for u in pop.users if u[2] is not None and s <= u[2] <= E and u[0] < s and not pop.active(u, s, E))


def test_dormant_uninstallers_keep_the_truth_inside_the_dead_range_and_un_gt_act_proves_them():
    pop = Population(days=400, per_day=12, dormant_un=0.6, seed=11)
    out = eng.derive_app(pop.aud_store(), pop.uni_store(), per_day=True)
    over = 0
    for x, cell in out["per_day"].items():
        xd = date.fromisoformat(x)
        for i, w in enumerate(out["windows"]):
            if (E - xd).days < w:
                continue
            truth = pop.true_dead(xd, w)
            assert cell["dead_lo"][i] <= truth <= cell["dead"][i]
            over += cell["dead"][i] - truth
    assert over > 0                                                  # the approximation's bias is real here …
    for g in [out] + list(out["months_by"].values()):                # … and the range holds in every total
        assert all(lo <= hi for lo, hi in zip(g["dead_lo"], g["dead"]))
        assert all(a >= b for a, b in zip(g["dead_lo"], g["dead_lo"][1:]))     # the lower end never rises with N
    for i, w in enumerate(out["windows"]):
        truth = sum(pop.true_dead(date.fromisoformat(x), w) for x in out["per_day"])
        assert out["dead_lo"][i] <= truth <= out["dead"][i]
    # un_gt_act: per window, the users it moved are clean-up uninstalls PROVEN by GA4 — never more than there were
    by = out["clamps_by_month"]["un_gt_act"]
    assert by and out["clamped"]["un_gt_act"][1] == sum(v[1] for v in by.values())
    for mo, (cells, users) in by.items():
        assert users <= _clean_up_uninstallers(pop, eng.window_days(int(mo)))
    lo = out["last_open"]
    assert sum(b["users_lo_curve"] for b in lo) == out["installed"] == sum(b["users"] for b in lo)


def _one_day(x, n, lags, act, months=None):
    """An Audience + Uninstall store holding one install day x."""
    months = months or [1, 2, 3]
    uni = {"history_start": _iso(x), "window_end": _iso(E + timedelta(days=3)),
           "daily": {_iso(x): {"new": n, "a1": 0}}, "cohorts": {_iso(x): {str(k): v for k, v in lags.items()}}}
    aud = {"complete": True, "E": _iso(E), "months": months, "windows": [eng.window_days(m) for m in months],
           "by_fsd": {_iso(x): act}}
    return aud, uni


def test_uninstalls_inside_the_window_come_out_of_the_actives_by_their_cohort_offset():
    x = E - timedelta(days=100)                     # 100 days old: windows 30 and 60 are after it, 91 too
    # 20 installs; 4 gone on day 0 (before every window), 3 on day 50 (age 50 = 50 days before E: inside the 60- and
    # 91-day windows, not the 30-day one), 2 on day 90 (10 days before E: inside all three), 1 after E (not yet)
    lags = {0: 4, 50: 3, 90: 2, 103: 1}
    aud, uni = _one_day(x, 20, lags, [7, 10, 12, 13], [1, 2, 3, 4])
    out = eng.derive_app(aud, uni, per_day=True)
    c = out["per_day"][_iso(x)]
    assert c["U"] == 9 and c["I"] == 11                              # the uninstall after E is not counted
    assert out["un_in"][:3] == [2, 5, 5]
    assert c["alive"][:3] == [7 - 2, 10 - 5, 12 - 5]
    assert c["dead"][:3] == [11 - 5, 11 - 5, 11 - 7]
    assert c["dead_lo"][:3] == [11 - 7, 11 - 10, 11 - 11]            # (nobody who uninstalled had opened)
    assert c["dead"][3] == 0 and c["alive"][3] == 11                 # 121 days: the day is inside: young


def test_young_install_days_are_never_dead_whatever_ga4_says():
    x = E - timedelta(days=10)
    aud, uni = _one_day(x, 50, {0: 5, 4: 5}, [3, 3, 3])              # a short (noisy) split must not make them dead
    out = eng.derive_app(aud, uni, per_day=True)
    c = out["per_day"][_iso(x)]
    assert c["I"] == 40 and c["alive"] == [40, 40, 40] and c["dead"] == c["dead_lo"] == [0, 0, 0]
    assert out["young_days"] == [1, 1, 1] and out["impossible"] == {} and out["clamped"] == {}
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
    out = eng.derive_app(*_one_day(x, n, lags, act, M7), per_day=True)
    c = out["per_day"][_iso(x)]
    assert all(v >= 0 for v in c["alive"] + c["dead"] + c["dead_lo"]) and c["I"] >= 0
    assert all(c["alive"][i] <= c["I"] for i in range(7))
    assert all(c["alive"][i] <= c["alive"][i + 1] for i in range(6))
    assert all(c["dead_lo"][i] <= c["dead"][i] for i in range(7)) and c["dead"][6] == 0
    if case == "un_gt_new":
        assert c["I"] == 0 and out["impossible"]["un_gt_new"] == [1, 2] and c["marks"]["0"] == "un_gt_new"
        assert c["dead"] == [0] * 7
    elif case == "act_gt_inst":
        assert c["alive"][:6] == [4] * 6 and out["impossible"]["act_gt_inst"] == [6, 30]
        assert c["marks"] == {str(i): "act_gt_inst" for i in range(1, 7)}
        assert out["clamps_by_month"]["act_gt_inst"] == {str(m): [1, 5] for m in range(1, 7)}
    elif case == "un_gt_act":
        assert c["alive"][:6] == [0] * 6 and c["dead"][:6] == [6] * 6
        assert c["dead_lo"][:6] == [5] * 6                           # the range [I − act, I] = [5, 6]
        assert out["clamped"]["un_gt_act"] == [6, 18] and out["impossible"] == {}
        assert out["clamps_by_month"]["un_gt_act"]["1"] == [1, 3]    # ≥ 3 of the 4 window uninstallers never opened
    else:
        assert c["alive"][:6] == [6, 6, 7, 7, 7, 7] and out["clamped"]["non_mono"] == [1, 2]
        assert c["marks"] == {"2": "non_mono"} and c["dead_lo"][:2] == [4, 4]
    assert out["flags"]["impossible_cells"] == sum(v[0] for v in out["impossible"].values())
    assert out["flags"]["clamped_cells"] == sum(v[0] for v in out["clamped"].values())


def test_a_store_whose_windows_stop_short_keeps_the_rest_in_the_tail_bucket():
    x = E - timedelta(days=200)
    aud, uni = _one_day(x, 10, {}, [5, 6, 7])                       # only 3 windows (91 days) for a 200-day-old day
    out = eng.derive_app(aud, uni)
    assert out["full"] is False and out["dead"] == [5, 4, 3]
    assert [(b["label"], b["users"]) for b in out["last_open"]] == [("1", 5), ("2", 1), ("3", 1), ("4+", 3)]


def test_a_store_still_being_read_is_never_derived():
    pop = Population(days=60, per_day=3)
    with pytest.raises(ValueError):
        eng.derive_app({"complete": False, "partial": {"E": _iso(E)}}, pop.uni_store())


def _month_store(spec):
    """{install day: (installs, actives in windows 1..3)} → stores (no uninstalls)."""
    uni = {"history_start": min(spec), "window_end": _iso(E), "cohorts": {},
           "daily": {x: {"new": n, "a1": 0} for x, (n, _) in spec.items()}}
    aud = {"complete": True, "E": _iso(E), "months": [1, 2, 3], "windows": [30, 60, 91],
           "by_fsd": {x: a for x, (_, a) in spec.items()}}
    return aud, uni


def test_most_dead_and_most_active_install_month_by_count_and_share_mature_months_only():
    spec = {"2026-05-10": (1000, [100, 150, 200]),    # May: 900 dead ≥ 1 month, 10% active
            "2026-06-10": (400, [320, 330, 340]),     # June: 80 dead, 80% active — the most active by share
            "2026-07-10": (50, [1, 2, 3]),            # July: 98% dead but only 50 installs — too small for a share
            "2026-07-20": (1500, [1200, 1300, 1400]),  # (July together: 1550 installs, 349 dead, 1201 active)
            "2026-09-01": (5000, [5000, 5000, 5000])}  # September: inside window 1 — not mature, never "most"
    out = eng.derive_app(*_month_store(spec))
    mo = out["months_by"]
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
    assert f["un_provisional_days"] == 2 + 7
    f = eng.derive_app(pop.aud_store(), pop.uni_store())["flags"]          # window_end = E + 3: E − 3 .. E provisional
    assert (f["un_days_missing"], f["un_provisional_days"]) == (0, 4)


def test_actives_installed_before_the_history_are_shown_apart():
    pop = Population(days=100, per_day=5)
    aud = pop.aud_store()
    aud["by_fsd"]["2020-01-01"] = [1, 2, 3, 4]
    out = eng.derive_app(aud, pop.uni_store())
    assert out["before_history"] == [1, 2, 3, 4]
    assert out["installs"] == len(pop.users)


def _app(days, per_day, seed):
    p = Population(days=days, per_day=per_day, seed=seed)
    return eng.derive_app(p.aud_store(), p.uni_store())


def test_portfolio_sums_apps_on_the_union_of_their_months_and_extends_a_young_app():
    old, young = _app(500, 6, 1), _app(45, 9, 2)
    p = eng.portfolio([old, young, {"err": {"type": "KeyError"}}])
    assert p["apps"] == 2 and p["skipped"] == 1 and p["months"] == old["months"] and young["months"] == [1, 2]
    assert p["installs"] == old["installs"] + young["installs"]
    for i, mo in enumerate(p["months"]):
        y = young["alive"][young["months"].index(mo)] if mo in young["months"] else young["installed"]
        assert p["alive"][i] == old["alive"][i] + y
        assert p["dead"][i] == old["dead"][i] + (young["dead"][young["months"].index(mo)] if mo in young["months"]
                                                 else 0)
    sep = "2026-09"
    assert p["months_by"][sep]["installs"] == old["months_by"][sep]["installs"] + young["months_by"][sep]["installs"]
    assert sum(b["users"] for b in p["last_open"]) == p["installed"]
    assert [b["label"] for b in p["last_open"]][-3:] == ["13-15", "16-18", "19+"]
    assert p["E_min"] == p["E_max"] == _iso(E)
    assert p["most"]["dead"]["count"]["month"] in p["months_by"]
    assert p["dau"]["users"] == old["dau"]["users"] + young["dau"]["users"]
    assert eng.portfolio([])["apps"] == 0


def test_portfolio_keeps_the_tiered_months_when_an_app_was_read_monthly():
    pop = Population(days=500, per_day=4, seed=5)
    monthly = eng.derive_app(pop.aud_store(months=list(range(1, 18))), pop.uni_store())   # an older, monthly read
    tiered = eng.derive_app(pop.aud_store(), pop.uni_store())
    p = eng.portfolio([monthly, tiered])
    assert p["months"] == tiered["months"] == list(range(1, 13)) + [15, 18]
    for i, mo in enumerate(p["months"]):
        j = monthly["months"].index(mo) if mo in monthly["months"] else None
        assert p["dead"][i] == tiered["dead"][i] + (monthly["dead"][j] if j is not None else 0)
    assert monthly["dead"] and sum(b["users"] for b in p["last_open"]) == p["installed"]


def test_portfolio_months_an_app_lacks_below_its_last_window_are_unknown():
    x = E - timedelta(days=200)
    short = eng.derive_app(*_one_day(x, 10, {}, [5, 6, 7], [1, 2, 3]))        # not full: stops at 3 months
    p = eng.portfolio([short, _app(400, 3, 4)])
    i4 = p["months"].index(4)
    assert p["dead"][i4] is None and p["last_open"][i4]["users"] is None
    assert p["dead"][0] is not None
