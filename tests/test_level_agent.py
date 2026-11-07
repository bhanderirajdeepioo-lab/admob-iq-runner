"""🤖 The level agent (admob_iq.engine.level_agent) on made-up rule inputs whose answer is known: every branch of the
cause rule, the external tests, the agent's own tests (a money level is never lowered, a reverted alarm is the
owner's, a move of ≥ 2 bands outside one band of the old level, the engine's steadiness on the eCPM-market branch,
persistence on every other branch), the persistence port, the hindsight words and the revert tests; then the
evidence and the market on synthetic entities: nothing after the ask day is ever read. No real data."""
import copy
import json
import math
import random
from datetime import date, timedelta

import pytest

from admob_iq.engine import cpi_alarm as CA
from admob_iq.engine import level_agent as LA

CFG = CA.P_PROD["levels"]["agent"]
P = CA.P_PROD


def bl(fam):
    return CA.lthr(fam, P["levels"]["delta"][fam])


def ri(fam="CPI", move=None, **over):
    """A rule input as evidence() makes it, every test passing: a steady move old → new 150 days after the change,
    the campaigns all moving inside, nothing seasonal. move = the relative change in the bad direction."""
    bad = CA.FAMILIES[fam]["bad"]
    if move is None:
        move = 0.5 if bad > 0 else -0.3
    old = {"CPI": 20.0, "GAP": 40.0, "ECPM": 5.0, "IPU": 5.0, "SPEND": 1000.0}.get(fam, 0.4)
    new = old * (1.0 + move)
    x = {"v": 1, "fam": fam, "why": "open", "app": "app-x", "d": "2025-06-03",
         "ep": {"opened": "2025-01-05", "c": "2024-12-31"},
         "old": {"days": ["2024-12-17", "2024-12-30"], "v": old},
         "new": {"days": ["2025-05-07", "2025-06-03"], "v": new},
         "move": {"rel": LA.fin(move), "worse_log": LA.fin(CA.lworse(fam, new, old)),
                  "band_rel": P["levels"]["delta"][fam], "band_log": LA.fin(bl(fam)), "noise_daily_log": 0.02},
         "alarm": {"days_since_change": 150},
         "trend": {"L7": {"v": new}, "L14": {"v": new}, "P14": {"v": new}, "L14_vs_P14": 0.0},
         "steadiness": {"fortnights_since_change": [{"v": new}] * 9, "l14_56d": {"max_dev": 0.05},
                        "l14_84d": {"max_dev": 0.06}},
         "seasonality": [{"lag_days": 364, "available": False, "similar": None, "analog": None},
                         {"lag_days": 728, "available": False, "similar": None, "analog": None}],
         "context": {"spend_usd_per_day": {"move": 0.0}, "campaigns": {"spend_share_new_of_campaigns_not_in_old": 0.0,
                                                                     "spend_share_old_of_campaigns_gone": 0.0}},
         "drivers": {}, "breadth": {}}
    lm = math.log(new / old)
    if fam == "CPI":
        x["drivers"] = {"campaigns_cpi_inr": {"rate_share": 0.95}}
        x["breadth"] = {"campaigns": {"same": 0.9, "opposite": 0.0}}
    elif fam == "ECPM":
        x["drivers"] = {"countries_ecpm_gross": None, "ipu": {"move": 0.02}}
    elif fam == "GAP":
        x["drivers"] = {"gap_split": {"share_of_move": {"cpi_inr": 1.0, "fx": 0.0, "ecpm": 0.0},
                                      "dlog": {"gap": lm, "cpi_inr": lm, "fx": 0.0, "ecpm": 0.0}},
                        "campaigns_cpi_inr": {"rate_share": 0.95}, "countries_ecpm_gross": None}
        x["breadth"] = {"campaigns_cpi": {"same": 0.9, "opposite": 0.0}}
    elif fam in CA.MONEY_FAMS:
        x["drivers"] = {"roas_split": {"share_of_move": {"cost_per_install": 1.0, "value_per_install": 0.0},
                                       "dlog": {"roas": lm, "value_per_install": 0.0, "cost_per_install": -lm}},
                        "inside_value": {"ecpm_move": 0.0, "ipu_move": 0.0}, "campaigns_roas_g": {"rate_share": 0.95}}
        x["breadth"] = {"countries_cpi": {"same": 0.9, "opposite": 0.0, "not_listed": 0.05}}
    elif fam == "SPEND":
        x["drivers"] = {"campaigns_spend": {"rows": [{"unit": "C1", "share_of_change": 0.8}]}}
    for path, v in over.items():
        o = x
        ks = path.split("__")
        for k in ks[:-1]:
            o = o[k]
        o[ks[-1]] = v
    return x


def mk(cpi=None, ecpm=None, n=4, ipu=0.01):
    """The other apps: n of them moved by cpi / ecpm (None: flat)."""
    def one(m):
        mv = [round(m if m is not None else 0.0, 6)] * n
        return {"n": n, "median": mv[0] if n else None, "moves": mv}
    return {"cpi": one(cpi), "ecpm": one(ecpm), "own": {"ipu": ipu, "ecpm": ecpm}}


def dec(x, m, **kw):
    return LA.decide(x, m, CFG, **kw)


def c1(x, m):
    return LA._c1(x, m, LA.TH)


# ── T-A1 every branch of the cause rule ─────────────────────────────────────────────────────────────────────────────

def test_every_branch_of_the_cause_rule():
    cpi_up, own_cost = 0.5, math.expm1(-math.log(0.7))
    cases = [
        ("thin", ri("CPI", **{"new__v": None}), mk(cpi=0.5), "wait", "thin", None),
        ("no_split", ri("ROAS_G", **{"drivers__roas_split": {"share_of_move": None, "dlog": None}}), mk(), "wait",
         "no_split", None),
        ("spend", ri("SPEND", move=-0.5), mk(), "keep", "spend", None),
        ("ipu", ri("IPU", move=-0.3), mk(), "keep", "ipu", None),
        ("scale up", ri("CPI", **{"context__spend_usd_per_day__move": 1.2}), mk(cpi=cpi_up), "keep", "spend_scaled",
         None),
        ("scale down", ri("CPI", **{"context__spend_usd_per_day__move": -0.55}), mk(cpi=cpi_up), "keep", "spend_scaled",
         None),
        ("turnover", ri("CPI", **{"context__campaigns__spend_share_old_of_campaigns_gone": 0.35}), mk(cpi=cpi_up),
         "keep", "campaign_mix", None),
        ("mix", ri("CPI", **{"drivers__campaigns_cpi_inr__rate_share": 0.5}), mk(cpi=cpi_up), "keep", "mix", None),
        ("narrow", ri("CPI", **{"breadth__campaigns__same": 0.6}), mk(cpi=cpi_up), "wait", "narrow", None),
        ("narrow opposite", ri("CPI", **{"breadth__campaigns__opposite": 0.2}), mk(cpi=cpi_up), "wait", "narrow", None),
        ("own campaigns", ri("CPI"), mk(cpi=0.0), "keep", "own_campaigns", None),
        ("cpi market", ri("CPI"), mk(cpi=cpi_up), "accept", "cpi_market", None),
        ("app side", ri("ECPM", **{"drivers__ipu__move": 0.2}), mk(ecpm=-0.3), "keep", "app_side", None),
        ("country mix", ri("ECPM", **{"drivers__countries_ecpm_gross": {"rate_share": 0.4, "units_measured": 3}}),
         mk(ecpm=-0.3), "keep", "country_mix", None),
        ("ipu unknown", ri("ECPM", **{"drivers__ipu__move": None}), mk(ecpm=-0.3), "wait", "ipu_unknown", None),
        ("ecpm market", ri("ECPM"), mk(ecpm=-0.3), "accept", "ecpm_market", None),
        ("user mix turn", ri("ECPM", **{"context__campaigns__spend_share_new_of_campaigns_not_in_old": 0.4}), mk(),
         "keep", "user_mix", None),
        ("user mix scale", ri("ECPM", **{"context__spend_usd_per_day__move": 1.5}), mk(), "keep", "user_mix", None),
        ("app only", ri("ECPM"), mk(), "wait", "app_only", None),
        ("gap cpi part", ri("GAP"), mk(cpi=cpi_up), "accept", "cpi_market", "cpi"),
        ("gap ecpm part", ri("GAP", **{"drivers__gap_split__share_of_move": {"cpi_inr": 0.0, "fx": 0.0, "ecpm": 1.0},
                                       "drivers__gap_split__dlog": {"gap": 0.4, "cpi_inr": 0.0, "fx": 0.0,
                                                                    "ecpm": 0.4}}),
         mk(ecpm=math.expm1(-0.4)), "accept", "ecpm_market", "ecpm"),
        ("gap both parts", ri("GAP", **{"drivers__gap_split__share_of_move": {"cpi_inr": 0.5, "fx": 0.0, "ecpm": 0.5},
                                        "drivers__gap_split__dlog": {"gap": 0.4, "cpi_inr": 0.2, "fx": 0.0,
                                                                     "ecpm": 0.2}}),
         mk(cpi=math.expm1(0.2), ecpm=math.expm1(-0.2)), "accept", "parts_external", None),
        ("gap cpi part keeps", ri("GAP", **{"context__spend_usd_per_day__move": 2.0}), mk(cpi=cpi_up), "keep",
         "spend_scaled", "cpi"),
        ("money cost part narrow", ri("ROAS_G", **{"breadth__countries_cpi__same": 0.65}), mk(cpi=own_cost), "wait",
         "narrow", "cpi"),
        ("money value part", ri("ROAS_C0", **{"drivers__roas_split__share_of_move": {"cost_per_install": 0.0,
                                                                                   "value_per_install": 1.0},
                                              "drivers__inside_value__ecpm_move": -0.3}),
         mk(ecpm=-0.3), "accept", "ecpm_market", "ecpm"),
    ]
    for name, x, m, want, branch, part in cases:
        got = c1(x, m)
        assert (got["dec"], got["branch"], got["part"]) == (want, branch, part), name
        assert got["cause"] and got["short"] and len(got["short"]) <= 60, name
    narrow = c1(ri("ROAS_G", **{"breadth__countries_cpi__same": 0.65}), mk(cpi=own_cost))
    assert "countries moving the same way = 65%" in narrow["cause"] and narrow["short"] == "narrow: countries 65%"
    assert "campaigns moving the same way = 60%" in c1(ri("CPI", **{"breadth__campaigns__same": 0.6}),
                                                       mk(cpi=cpi_up))["cause"]
    s = c1(ri("CPI", **{"context__spend_usd_per_day__move": 1.2}), mk(cpi=cpi_up))
    assert s["cause"] == "seen with spend ×2.2 since the old level (your lever)"
    assert s["short"] == "spend ×2.2 (your lever)"
    g = c1(ri("GAP", **{"context__spend_usd_per_day__move": 2.0}), mk(cpi=cpi_up))
    assert g["cause"].startswith("CPI part 100% of the move: seen with spend ×3.0")
    both = c1(ri("GAP", **{"drivers__gap_split__share_of_move": {"cpi_inr": 0.5, "fx": 0.0, "ecpm": 0.5},
                           "drivers__gap_split__dlog": {"gap": 0.4, "cpi_inr": 0.2, "fx": 0.0, "ecpm": 0.2}}),
              mk(cpi=math.expm1(0.2), ecpm=math.expm1(-0.2)))
    assert both["cause"].startswith("both parts moved with other apps: 4 other apps: median +22%")
    few = c1(ri("CPI"), mk(cpi=cpi_up, n=2))
    assert few["branch"] == "own_campaigns" and "2 other apps with data (needs 3)" in few["cause"]


def test_the_external_tests_coming_back_still_moving_not_steady():
    b = P["levels"]["delta"]["CPI"]
    m = mk(cpi=0.5)
    assert c1(ri("CPI", **{"trend__L14_vs_P14": -2 * b}), m)["branch"] == "coming_back"
    assert c1(ri("CPI", **{"trend__L14_vs_P14": 2 * b}), m)["branch"] == "still_sliding"
    assert c1(ri("CPI", **{"trend__L14_vs_P14": 0.5 * b}), m)["dec"] == "accept"
    ns = c1(ri("CPI", **{"steadiness__l14_56d": {"max_dev": 0.16}}), m)
    assert (ns["dec"], ns["branch"]) == ("wait", "not_steady") and "up to 16% off its 56-day median" in ns["cause"]
    assert c1(ri("CPI", **{"steadiness__l14_56d": None}), m)["branch"] == "not_steady"
    e = c1(ri("ECPM", **{"trend__L14_vs_P14": 0.2}), mk(ecpm=-0.3))       # eCPM up: back toward the old level
    assert e["branch"] == "coming_back" and e["cause"].endswith("last 14 days +20% vs the 14 before")


# ── T-A3 … T-A6 the agent's own tests ───────────────────────────────────────────────────────────────────────────────

def test_a_money_level_is_never_lowered():
    for fam in CA.MONEY_FAMS:
        x = ri(fam, **{"drivers__roas_split__share_of_move": {"cost_per_install": 0.0, "value_per_install": 1.0},
                       "drivers__inside_value__ecpm_move": -0.3})
        assert c1(x, mk(ecpm=-0.3))["dec"] == "accept", fam                   # the cause rule alone would accept
        out = dec(x, mk(ecpm=-0.3))
        assert (out["decision"], out["branch"]) == ("wait", "money_guard"), fam
        assert out["short"] == "money: only you" and "the agent never lowers it" in out["cause"]
    for fam in CA.MONEY_FAMS:                                                # every external shape of a money move
        lm = math.log(0.7)
        cost = ri(fam, move=-0.3)                                             # the cost part: other apps' CPI moved
        value = ri(fam, move=-0.3, **{"drivers__roas_split__share_of_move": {"cost_per_install": 0.0,
                                                                            "value_per_install": 1.0},
                                      "drivers__roas_split__dlog": {"roas": lm, "value_per_install": lm,
                                                                    "cost_per_install": 0.0},
                                      "drivers__inside_value__ecpm_move": -0.3})
        both = ri(fam, move=-0.3, **{"drivers__roas_split__share_of_move": {"cost_per_install": 0.5,
                                                                           "value_per_install": 0.5},
                                     "drivers__roas_split__dlog": {"roas": lm, "value_per_install": lm / 2,
                                                                   "cost_per_install": -lm / 2},
                                     "drivers__inside_value__ecpm_move": math.expm1(lm / 2)})
        for x, m, br in ((cost, mk(cpi=math.expm1(-lm)), "cpi_market"), (value, mk(ecpm=-0.3), "ecpm_market"),
                         (both, mk(cpi=math.expm1(-lm / 2), ecpm=math.expm1(lm / 2)), "parts_external")):
            assert (c1(x, m)["dec"], c1(x, m)["ext_branch"]) == ("accept", br), (fam, br)
            for flags in (None, {"reverted": True}):
                assert dec(x, m, flags=flags)["branch"] == "money_guard", (fam, br)
    rng = random.Random(7)
    n = 0
    for i in range(1000):
        fam = CA.MONEY_FAMS[i % 4]
        mv = -rng.uniform(0.05, 0.8)
        lm = math.log(1.0 + mv)
        cs = rng.uniform(-1.0, 2.0)
        em, cm = math.expm1(lm * (1.0 - cs)), math.expm1(-lm * cs)       # the value part's and the cost part's moves
        aligned = i % 2 == 0                                              # every other draw: the other apps agree
        x = ri(fam, move=mv, **{
            "drivers__roas_split__share_of_move": {"cost_per_install": cs, "value_per_install": 1.0 - cs},
            "drivers__roas_split__dlog": {"roas": lm, "value_per_install": lm * (1.0 - cs), "cost_per_install": lm * cs},
            "drivers__inside_value__ecpm_move": em,
            "drivers__inside_value__ipu_move": rng.uniform(-0.1, 0.1) if aligned else rng.choice(
                [None, rng.uniform(-0.3, 0.3)]),
            "breadth__countries_cpi__same": rng.uniform(0.75, 1.0) if aligned else rng.uniform(0.0, 1.0),
            "trend__L14_vs_P14": rng.uniform(-0.02, 0.02) if aligned else rng.uniform(-0.1, 0.1),
            "context__spend_usd_per_day__move": rng.uniform(-0.3, 0.5) if aligned else rng.uniform(-0.6, 1.5),
            "steadiness__l14_56d": {"max_dev": rng.uniform(0.0, 0.3)}})
        if aligned:
            m = {"cpi": {"n": 5, "median": cm, "moves": [cm] * 5}, "ecpm": {"n": 5, "median": em, "moves": [em] * 5},
                 "own": {"ipu": 0.0, "ecpm": em}}
        else:
            m = {"cpi": {"n": rng.randint(0, 8), "median": rng.uniform(-0.5, 1.0),
                         "moves": sorted(rng.uniform(-1, 1) for _ in range(5))},
                 "ecpm": {"n": rng.randint(0, 8), "median": rng.uniform(-0.8, 0.3),
                          "moves": sorted(rng.uniform(-1, 1) for _ in range(5))},
                 "own": {"ipu": rng.uniform(-0.3, 0.3), "ecpm": rng.uniform(-0.5, 0.2)}}
        out = dec(x, m)
        assert out["decision"] != "accept", (i, out)
        n += out["branch"] == "money_guard"
    assert n > 100                                                           # the guard itself was reached often


def test_a_reverted_alarm_and_a_small_move_wait():
    m = mk(cpi=0.5)
    assert dec(ri("CPI"), m)["decision"] == "accept"
    r = dec(ri("CPI"), m, flags={"reverted": True})
    assert (r["decision"], r["branch"], r["short"]) == ("wait", "reverted_before", "only you")
    b = bl("CPI")
    small = ri("CPI", move=math.exp(1.9 * b) - 1.0)                          # 1.9 bands
    out = dec(small, mk(cpi=math.exp(1.9 * b) - 1.0))
    assert (out["decision"], out["branch"]) == ("wait", "small_move")
    assert "the move is 1.9 bands (needs 2.0)" in out["cause"]
    near = ri("CPI", **{"new__v": 20.0 * 1.05})                              # the last 28 days within one band of old
    assert dec(near, m)["branch"] == "small_move"


def test_the_ecpm_market_branch_needs_the_engines_steadiness_not_persistence():
    m = mk(ecpm=-0.3)
    st = dec(ri("ECPM", **{"steadiness__l14_56d": {"max_dev": 0.12}}), m)
    assert (st["decision"], st["branch"]) == ("wait", "engine_steady") and "(needs 10%)" in st["cause"]
    ok = dec(ri("ECPM", **{"steadiness__l14_56d": {"max_dev": 0.09}, "alarm__days_since_change": 60}), m)
    assert ok["decision"] == "accept" and ok["measured"] and ok["persist"]["decision"] == "wait"


def test_every_other_accept_needs_the_persistence_rule():
    young = {"alarm__days_since_change": 60}
    for x, m, want in ((ri("CPI", **young), mk(cpi=0.5), "cpi_market"),
                       (ri("GAP", **young), mk(cpi=0.5), "cpi_market"),
                       (ri("GAP", **young, **{"drivers__gap_split__share_of_move": {"cpi_inr": 0.5, "fx": 0.0,
                                                                                    "ecpm": 0.5},
                                              "drivers__gap_split__dlog": {"gap": 0.4, "cpi_inr": 0.2, "fx": 0.0,
                                                                           "ecpm": 0.2}}),
                        mk(cpi=math.expm1(0.2), ecpm=math.expm1(-0.2)), "parts_external"),
                       (ri("GAP", **young, **{"drivers__gap_split__share_of_move": {"cpi_inr": 0.0, "fx": 0.0,
                                                                                    "ecpm": 1.0},
                                              "drivers__gap_split__dlog": {"gap": 0.4, "cpi_inr": 0.0, "fx": 0.0,
                                                                           "ecpm": 0.4}}),
                        mk(ecpm=math.expm1(-0.4)), "ecpm_market")):
        assert c1(x, m)["dec"] == "accept" and c1(x, m)["ext_branch"] == want
        out = dec(x, m)
        assert (out["decision"], out["branch"], out["measured"]) == ("wait", "unmeasured", False), want
        assert out["cause"].endswith("the change started 60 days ago (needs 84)")
        assert out["persist"]["first"] == "A7"


# ── T-A7 the persistence port ───────────────────────────────────────────────────────────────────────────────────────

def test_the_persistence_rule_test_by_test():
    assert LA.persist(ri("CPI"))["decision"] == "accept"
    b = bl("CPI")
    old, new = 20.0, 30.0
    toward = old * math.exp(math.log(new / old) - 3 * b)                     # 3 bands back toward the old level
    cases = {
        "A1": {"steadiness__fortnights_since_change": [{"v": new}] * 5},
        "A2": {"new__v": old * math.exp(3.5 * b), "trend__L7__v": old * math.exp(3.5 * b),
               "trend__L14__v": old * math.exp(3.5 * b), "trend__P14__v": old * math.exp(3.5 * b),
               "steadiness__fortnights_since_change": [{"v": old * math.exp(3.5 * b)}] * 9},
        "A3": {"steadiness__l14_56d": {"max_dev": 0.11}},
        "A4": {"steadiness__fortnights_since_change": [{"v": new}] * 8
               + [{"v": old * math.exp(math.log(1.5) - 1.5 * b)}]},
        "A5": {"trend__L14__v": old * math.exp(math.log(1.5) - 1.5 * b)},
        "A6": {"move__noise_daily_log": 0.5},
        "A7": {"alarm__days_since_change": 83},
        "K2": {"trend__L14__v": toward},
    }
    for code, over in cases.items():
        ps = LA.persist(ri("CPI", **over))
        assert ps["first"] == code, (code, ps)
        assert ps["decision"] == ("keep" if code.startswith("K") else "wait"), code
    sea = ri("CPI", seasonality=[{"lag_days": 364, "available": True, "similar": True,
                                  "analog": {"label": "recovered", "label_last": "recovered", "first_recovered_at": 56}},
                                 {"lag_days": 728, "available": False, "similar": None, "analog": None}])
    assert LA.persist(sea)["first"] == "K1" and LA.persist(sea)["decision"] == "keep"
    words = dec(ri("CPI", **{"steadiness__l14_56d": {"max_dev": 0.11}}), mk(cpi=0.5))
    assert words["cause"].endswith("the 14-day level up to 11% off its 56-day median (needs 10%)")
    assert LA.persist(ri("CPI", **{"new__v": None}))["decision"] == "wait"          # never a crash on a thin level


# ── T-A10 determinism, purity, words ────────────────────────────────────────────────────────────────────────────────

def test_decide_is_pure_deterministic_and_reads_only_the_stored_form():
    m = mk(cpi=0.5)
    x = ri("CPI")
    x0, m0 = copy.deepcopy(x), copy.deepcopy(m)
    a = dec(x, m)
    assert x == x0 and m == m0                                               # inputs never modified
    stored = json.loads(json.dumps(LA.frozen(x))), json.loads(json.dumps(LA.frozen(m)))
    b = dec(*stored)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True) == json.dumps(dec(x, m), sort_keys=True)


def test_no_cause_or_short_asserts_causation():
    seen = 0
    for fam in ("CPI", "ECPM", "GAP", "IPU", "SPEND", "ROAS_G", "ROAS_C7"):
        for over in ({}, {"context__spend_usd_per_day__move": 1.5}, {"context__spend_usd_per_day__move": -0.6},
                     {"trend__L14_vs_P14": 0.5}, {"trend__L14_vs_P14": -0.5}, {"new__v": None},
                     {"alarm__days_since_change": 30}, {"steadiness__l14_56d": None}):
            for m in (mk(), mk(cpi=0.5, ecpm=-0.3), mk(cpi=0.5, ecpm=-0.3, n=1)):
                out = dec(ri(fam, **over), m)
                for txt in (out["cause"], out["short"]):
                    assert not any(w in txt.lower() for w in LA.FORBIDDEN), (fam, over, txt)
                assert len(out["short"]) <= 60
                seen += 1
    assert seen > 100


# ── T-A11 hindsight words and the revert tests ──────────────────────────────────────────────────────────────────────

def test_back_at_old_revert_due_label_verdict_and_the_rule_fingerprint():
    b = bl("CPI")
    assert LA.back_at_old("CPI", 20.0 * math.exp(0.9 * b), 20.0, P) is True
    assert LA.back_at_old("CPI", 20.0 * math.exp(1.1 * b), 20.0, P) is False
    assert LA.back_at_old("CPI", 15.0, 20.0, P) is True                      # better than old counts as back
    assert LA.back_at_old("ECPM", 4.0, 5.0, P) is False and LA.back_at_old("ECPM", None, 5.0, P) is None
    assert LA.back_at_old("CPI", 0.0, 20.0, P) is None
    ks = (28, 35, 42, 49, 56, 63, 70, 77, 84)
    assert LA.revert_due([(k, k in (42, 49)) for k in ks], CFG) == 49
    assert LA.revert_due([(k, k == 42) for k in ks], CFG) is None             # one alone: no
    assert LA.revert_due([(k, k in (28,)) for k in ks], CFG) is None
    assert LA.revert_due([(28, True), (35, True)], CFG) == 35
    assert LA.revert_due([(k, k >= 84) for k in ks + (91,)], CFG) is None    # a pair at 84 / 91: past the net
    assert LA.revert_due([(k, None) for k in ks], CFG) is None
    old, new = 20.0, 30.0
    stay = LA.label("CPI", old, new, [(28, 30.5), (56, 31.0), (84, 29.0)], P)
    assert stay == {"label": "stayed", "last": "stayed", "first_back": None}
    back = LA.label("CPI", old, new, [(28, 29.0), (56, 20.5), (84, 20.2)], P)
    assert back["label"] == "recovered" and back["last"] == "recovered" and back["first_back"] == 56
    bounce = LA.label("CPI", old, new, [(28, 20.5), (56, 30.0), (84, 30.0)], P)
    assert (bounce["label"], bounce["last"]) == ("recovered", "stayed")
    assert LA.label("CPI", old, new, [(28, 25.0), (56, None), (84, None)], P)["label"] == "unknown"
    assert LA.label("CPI", old, new, [(28, 25.0), (56, 25.0), (84, 25.0)], P)["label"] == "partial"
    assert LA.verdict("accept", stay) == "right" and LA.verdict("accept", back) == "wrong"
    assert LA.verdict("accept", bounce) == "unclear" and LA.verdict("keep", stay) == "stayed"
    assert LA.verdict("wait", back) == "came_back" and LA.verdict("keep", bounce) == "unclear"
    sha = LA.th_sha(CFG)
    assert len(sha) == 12 and sha == LA.th_sha(dict(CFG))
    assert LA.th_sha(dict(CFG, move_bands=2.5)) != sha and LA.th_sha(dict(CFG, engine_band=0.11)) != sha
    saved = LA.TH["turn"]
    try:
        LA.TH["turn"] = 0.31
        assert LA.th_sha(CFG) != sha
    finally:
        LA.TH["turn"] = saved
    assert LA.next_phase("2024-01-02") == "2024-01-09" and LA.next_phase("2024-01-05") == "2024-01-09"
    assert (date.fromisoformat(LA.next_phase("2025-06-03")) - date.fromisoformat(CA.EPOCH)).days % 7 == 0


# ── T-A8 / T-A9 the evidence and the market on synthetic entities ───────────────────────────────────────────────────

D0 = "2024-01-02"
N = 460


def day_of(i, d0=D0):
    return (date.fromisoformat(d0) + timedelta(days=i)).isoformat()


def prng(seed):
    x = seed & 0xFFFFFFFF or 1
    while True:
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        yield (x / 0xFFFFFFFF) * 2.0 - 1.0


def series(seed, sp=1000.0, cpi=20.0, ecpm=5.0, ipu=5.0, dau=200000.0, roas=0.4, n=N, cohort=False):
    g = prng(seed)
    s = {k: [0.0] * n for k in ("sp_usd", "sp_inr", "inst", "d0_inr", "rev", "imp", "dau")}
    if cohort:
        for k in ("c_n", "c_sp", "c_r0", "c_r1", "c_r7"):
            s[k] = [0.0] * n
    for d in range(n):
        f = (lambda: 1.0 + 0.01 * next(g))
        spd = sp * f()
        s["sp_usd"][d], s["sp_inr"][d] = spd, spd * 94.5
        s["inst"][d] = spd * 94.5 / cpi * f()
        s["d0_inr"][d] = spd * 94.5 * roas * f()
        s["dau"][d] = dau * f()
        s["imp"][d] = s["dau"][d] * ipu * f()
        s["rev"][d] = s["imp"][d] * ecpm / 1000.0 * f()
        if cohort:
            s["c_n"][d], s["c_sp"][d], s["c_r0"][d] = s["inst"][d], spd, spd * roas
            s["c_r1"][d], s["c_r7"][d] = spd * roas * 1.2, spd * roas * 1.5
    return s


def shifted(s, k):
    """The same days on an entity whose day0 is k days later (its series starts k days in)."""
    return {key: list(v[k:]) for key, v in s.items()}


def world(d_ix=400):
    """The own app (day0 D0) with a CPI step ×1.5 at day 300, 4 other apps (two own day0s), 3 campaigns (their own
    day0) and 4 candidate countries (their own day0s; XD big early and small since day 250)."""
    app = series(1)
    for d in range(300, N):
        app["inst"][d] /= 1.5
    A = CA.Ent("app", "app-own", "app-own", "Own App", D0, app)
    others = []
    for i, k in enumerate((0, 0, 9, 30)):
        s = series(20 + i, sp=15.0, cpi=2.0, dau=60000.0)
        for d in range(300, N):
            s["inst"][d] /= 1.5
            s["rev"][d] *= 0.8
        others.append(CA.Ent("app", "app-o%d" % i, "app-o%d" % i, "Other %d" % i, day_of(k), shifted(s, k)))
    camps = []
    for i, q in enumerate((0.5, 0.3, 0.2)):
        cs = {key: [x * q for x in app[key]] for key in ("sp_usd", "sp_inr", "inst", "d0_inr")}
        camps.append(CA.Ent("camp", "9000%d" % i, "app-own", "Campaign %d" % i, day_of(20 + i), shifted(cs, 20 + i)))
    ctys = []
    for i, (cc, q) in enumerate((("XA", 0.45), ("XB", 0.3), ("XC", 0.02), ("XD", 0.15))):
        cs = {"sp_usd": [x * q for x in app["sp_usd"]], "sp_inr": [x * q for x in app["sp_inr"]],
              "inst": [x * q for x in app["inst"]], "rev": [x * q for x in app["rev"]],
              "imp": [None if d < 60 else x * q for d, x in enumerate(app["imp"])]}
        if cc == "XD":
            for key in ("sp_usd", "sp_inr", "inst"):
                for d in range(250, N):
                    cs[key][d] *= 0.025 / 0.15
        k = 5 * i
        ctys.append(CA.Ent("country", "app-own|" + cc, "app-own", cc, day_of(k), shifted(cs, k)))
    return A, others, camps, ctys


def an_ep(A, fam="CPI"):
    r = CA.run([A], P, day_of(N - 1))
    ep = [e for e in r["episodes"] if e["fam"] == fam][0]
    return {k: ep[k] for k in ("fam", "opened", "c", "base", "bspan", "base_src")}


def poisoned(e, d):
    """Every cell the ask day cannot know (after d, or inside a maturity lag) → garbage."""
    s = {}
    for k, v in e.s.items():
        lim = LA._ix(e, d) - LA.LAGS.get(k, 0)
        s[k] = [x if i <= lim else (777777.0 if x is None else x * 13.7 + 12345.0) for i, x in enumerate(v)]
    return CA.Ent(e.kind, e.id, e.app, e.label, e.day0, s)


def test_evidence_and_market_never_read_after_the_ask_day():
    A, others, camps, ctys = world()
    ep = an_ep(A)
    for d_ix in (380, 410, 459):
        d = day_of(d_ix)
        nd = [day_of(d_ix - 27), d]
        ri = LA.evidence(A, camps, ctys, ep, nd, d, "open", P)
        mkt = LA.market(ri, A, others)
        rp = LA.evidence(poisoned(A, d), [poisoned(c, d) for c in camps], [poisoned(c, d) for c in ctys], ep, nd, d,
                         "open", P)
        mp = LA.market(rp, poisoned(A, d), [poisoned(o, d) for o in others])
        assert json.dumps(ri, sort_keys=True) == json.dumps(rp, sort_keys=True), d
        assert json.dumps(mkt, sort_keys=True) == json.dumps(mp, sort_keys=True), d
        assert ri["new"]["v"] == pytest.approx(30.0, rel=0.03) and ri["old"]["v"] == ep["base"]
        assert ri["move"]["rel"] == pytest.approx(0.5, rel=0.05) and mkt["cpi"]["n"] == 4
        assert mkt["cpi"]["median"] == pytest.approx(0.5, rel=0.05)
    with pytest.raises(ValueError):                                          # a new window after d − shift
        LA.evidence(A, camps, ctys, ep, [day_of(380), day_of(401)], day_of(400), "open", P)
    with pytest.raises(ValueError):
        LA.market(dict(ri, d=day_of(300)), A, others)


def test_cut_drops_every_cell_not_matured_on_the_ask_day():
    s = series(3, cohort=True)
    e = CA.Ent("app", "app-x", "app-x", "X", D0, s)
    c = LA.cut(e, day_of(100))
    assert all(len(v) == 101 for v in c.s.values())
    assert c.s["dau"][100] is None and c.s["dau"][99] == s["dau"][99]          # GA4: a day late
    assert all(c.s["c_r7"][i] is None for i in range(93, 101)) and c.s["c_r7"][92] == s["c_r7"][92]   # 8 days
    assert c.s["c_r1"][99] is None and c.s["c_r1"][98] == s["c_r1"][98]
    assert c.s["sp_inr"][100] == s["sp_inr"][100] and c.s["inst"][100] == s["inst"][100]
    assert LA.cut(CA.Ent("camp", "c", "x", "c", day_of(200), {"sp_usd": [1.0] * 10}), day_of(100)).s["sp_usd"] == []


def test_countries_are_every_candidate_by_the_engines_own_as_of_day_rule():
    A, others, camps, ctys = world()
    bspan = [day_of(286), day_of(299)]
    base = CA.measure(A, P, "ROAS_G", *bspan)["v"]
    ep = {"fam": "ROAS_G", "opened": day_of(303), "c": day_of(300), "base": base, "bspan": bspan, "base_src": "before"}
    late = LA.evidence(A, camps, ctys, ep, [day_of(373), day_of(400)], day_of(400), "money", P)
    b0 = [day_of(200), day_of(213)]
    ep0 = dict(ep, opened=day_of(217), c=day_of(214), bspan=b0, base=CA.measure(A, P, "ROAS_G", *b0)["v"])
    early = LA.evidence(A, camps, ctys, ep0, [day_of(243), day_of(270)], day_of(270), "money", P)
    # at day 400 XD (2.5 % of the spend since day 250) and XC (2 %) are left out: 25 % of the spend is not listed;
    # at day 270 XD was still big over its trailing 120 days: listed
    assert late["breadth"]["countries_cpi"]["not_listed"] == pytest.approx(0.25, abs=0.01)
    xd = (7 * 0.15 + 21 * 0.025) / 28                                        # XD's share of the new window then
    assert early["breadth"]["countries_cpi"]["not_listed"] == pytest.approx(1 - 0.45 - 0.3 - xd, abs=0.005)
    many = [CA.Ent("country", "app-own|X%02d" % i, "app-own", "X%02d" % i, D0,
                   {k: [x * 0.07 for x in A.s[k]] for k in ("sp_usd", "sp_inr", "inst")}) for i in range(13)]
    r13 = LA.evidence(A, camps, many, ep, [day_of(373), day_of(400)], day_of(400), "money", P)
    assert r13["breadth"]["countries_cpi"]["not_listed"] == pytest.approx(1 - 13 * 0.07, abs=0.005)   # no top 12


def test_the_ads_per_user_windows_end_at_the_last_known_ga4_day():
    A, others, camps, ctys = world()
    s = {k: list(v) for k, v in A.s.items()}
    for d in range(300, N):
        s["imp"][d] *= 1.1                                                  # ads per user +10 % (under 15 %)
        s["rev"][d] *= 1.1 * 0.7                                            # eCPM −30 %
    for d in range(397, N):
        s["dau"][d] = None                                                  # GA4 known up to day 396 only
    B = CA.Ent("app", "app-own", "app-own", "Own App", D0, s)
    ep = an_ep(B, "ECPM")
    ri = LA.evidence(B, camps, ctys, ep, [day_of(373), day_of(400)], day_of(400), "open", P)
    o, n = ep["bspan"], [day_of(373), day_of(396)]

    def ipu(w):
        a, b = LA._ix(B, w[0]), LA._ix(B, w[1])
        return sum(s["imp"][a:b + 1]) / sum(s["dau"][a:b + 1])
    assert ri["drivers"]["ipu"]["move"] == pytest.approx(ipu(n) / ipu(o) - 1.0, abs=2e-6)
    mkt = LA.market(ri, B, others)
    assert mkt["own"]["ipu"] == pytest.approx(ipu(n) / ipu(o) - 1.0, rel=1e-9)
    assert mkt["own"]["ecpm"] == pytest.approx(-0.3, abs=0.02)


def test_only_campaign_aliases_enter_the_rule_inputs():
    A, others, camps, ctys = world()
    s = {k: list(v) for k, v in A.s.items()}
    cs = [{k: list(v) for k, v in c.s.items()} for c in camps]
    for d in range(300 - 20, N - 20):
        for k in ("sp_usd", "sp_inr", "inst", "d0_inr"):
            cs[0][k][d] *= 0.3                                               # the biggest campaign cut back
    for d in range(300, N):
        for k in ("sp_usd", "sp_inr", "inst", "d0_inr"):
            s[k][d] -= A.s[k][d] * 0.5 * 0.7
    B = CA.Ent("app", "app-own", "app-own", "Own App", D0, s)
    cps = [CA.Ent("camp", c.id, c.app, c.label, c.day0, x) for c, x in zip(camps, cs)]
    ep = an_ep(B, "SPEND")
    ri = LA.evidence(B, cps, ctys, ep, [day_of(373), day_of(400)], day_of(400), "open", P)
    top = ri["drivers"]["campaigns_spend"]["rows"][0]
    assert top["unit"] in ("C1", "C2", "C3", "rest") and top["share_of_change"] == pytest.approx(1.0, abs=0.02)
    assert not any(c.id in json.dumps(ri) for c in camps)


def test_the_market_counts_other_apps_with_data_on_both_windows_only():
    A, others, camps, ctys = world()
    ep = an_ep(A)
    ri = LA.evidence(A, camps, ctys, ep, [day_of(373), day_of(400)], day_of(400), "open", P)
    assert LA.market(ri, A, others + [A])["cpi"]["n"] == 4                   # the own app never counts
    thin = CA.Ent("app", "app-thin", "app-thin", "Thin", D0, series(40, sp=0.5, cpi=2.0, dau=500.0))
    assert LA.market(ri, A, others + [thin])["cpi"]["n"] == 4                 # < 30 installs a day
    assert LA.market(ri, A, others + [thin])["ecpm"]["n"] == 4                # < 5000 impressions a day
    late = CA.Ent("app", "app-late", "app-late", "Late", day_of(350), shifted(series(41, sp=15.0, cpi=2.0), 350))
    assert LA.market(ri, A, others + [late])["cpi"]["n"] == 4                 # nothing in the old window
    m = LA.market(ri, A, others)
    assert m["ecpm"]["n"] == 4 and m["ecpm"]["median"] == pytest.approx(-0.2, abs=0.02)
    assert m["cpi"]["moves"] == sorted(m["cpi"]["moves"]) and m["own"]["ecpm"] == pytest.approx(0.0, abs=0.02)


def test_evidence_is_deterministic_and_never_modifies_its_inputs():
    A, others, camps, ctys = world()
    ep = an_ep(A)
    snap = json.dumps([A.s, [c.s for c in camps], [c.s for c in ctys], ep], sort_keys=True)
    a = LA.evidence(A, camps, ctys, ep, [day_of(373), day_of(400)], day_of(400), "open", P)
    b = LA.evidence(A, camps, ctys, ep, [day_of(373), day_of(400)], day_of(400), "open", P)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True) and a == LA.frozen(a)
    assert json.dumps([A.s, [c.s for c in camps], [c.s for c in ctys], ep], sort_keys=True) == snap
    out = LA.decide(a, LA.market(a, A, others), CFG)
    assert out["decision"] in ("accept", "keep", "wait") and LA.key_numbers(a, LA.market(a, A, others), out)
