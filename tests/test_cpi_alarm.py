"""📉 CPI vs eCPM alarm engine (admob_iq.engine.cpi_alarm) on made-up apps whose truth is known: spend $1,000 a day at
CPI $0.20 (₹94.5 per $), D0 ROAS 40 %, 200,000 daily users × 5 ads at eCPM $5, ±2 % deterministic noise (xorshift32,
the same on every Python), 420 days from a day0 on the EPOCH's weekly phase. Each case changes one thing and pins
what the engine says about it: P_PARITY must give the investigation's reference values (the replay the owner's
backtest was run on), P_PROD each production change. No real data."""
import copy
from datetime import date, timedelta

import pytest

from admob_iq.engine import cpi_alarm as E

N = 420
DAY0 = "2024-01-02"                     # (DAY0 − EPOCH) % 7 == 0: the noise refresh on the reference's phase
T = (date.fromisoformat(DAY0) + timedelta(days=N - 1)).isoformat()
APP = "ca-app-pub-0000000000000000~21"
SPEND_KEYS = ("sp_usd", "sp_inr", "inst", "d0_inr")


def ix(d):
    return (date.fromisoformat(d) - date.fromisoformat(DAY0)).days


def prng(seed):
    x = seed & 0xFFFFFFFF or 1
    while True:
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        yield (x / 0xFFFFFFFF) * 2.0 - 1.0          # uniform [-1, 1]


def synth(seed=1, noise=0.02, sp=1000.0, cpi=0.2, ecpm=5.0, roas=0.40, ipu=5.0, dau=200000.0, cohort=False):
    g = prng(seed)
    s = {k: [0.0] * N for k in ("sp_usd", "sp_inr", "inst", "d0_inr", "rev", "imp")}
    s["dau"] = [None] * N
    if cohort:
        for k in ("c_n", "c_sp", "c_r0", "c_r1", "c_r7"):
            s[k] = [None] * N
    for d in range(N):
        def f():
            return 1.0 + noise * next(g)
        spd = sp * f()
        s["sp_usd"][d], s["sp_inr"][d] = spd, spd * 94.5
        s["inst"][d] = spd / cpi * f()
        s["d0_inr"][d] = spd * 94.5 * roas * f()
        du = dau * f()
        s["dau"][d] = du
        s["imp"][d] = du * ipu * f()
        s["rev"][d] = s["imp"][d] * ecpm / 1000.0 * f()
        if cohort:
            s["c_n"][d], s["c_sp"][d] = s["inst"][d] / 0.8, spd
            s["c_r0"][d] = spd * roas * f()
            s["c_r1"][d], s["c_r7"][d] = s["c_r0"][d] * 1.15, s["c_r0"][d] * 1.6
    return s


def mul(s, key, a, b, k):
    for d in range(a, min(b, N)):
        if s[key][d] is not None:
            s[key][d] *= k


def ent(s, kind="app", eid=APP, day0=DAY0):
    return E.Ent(kind, eid, APP, "Alpha App", day0, s)


def run(s, P=E.P_PARITY, kind="app", fams=None):
    r = E.run([ent(s, kind)], P, T)
    return [ep for ep in r["episodes"] if not fams or ep["fam"] in fams]


def brief(ep):
    """(fam, opener, c on the calendar index as the reference reports it, opened, closed, why, base, thr, re-notices,
    their kinds, confirm)"""
    sh = E.FAMILIES[ep["fam"]]["shift"]
    return (ep["fam"], ep["opener"], ix(ep["c"]) + sh, ix(ep["opened"]), ix(ep["closed"]) if ep["closed"] else None,
            ep["why"], round(ep["base"], 4), round(ep["thr_open"], 3), [ix(d) for d, _ in ep["esc"]],
            [k for _, k in ep["esc"]], ep["confirm"])


# ── P_PARITY: the reference values of every case (engine.md §6) ───────────────────────────────────────────────────
def case_A():
    s = synth()
    mul(s, "inst", 300, 360, 1 / 1.4)
    return s


def case_D():
    s = synth()
    for d in range(250, N):
        s["inst"][d] /= 1.01 ** min(d - 249, 50)
    return s


def case_F():
    s = synth()
    for k in SPEND_KEYS:
        mul(s, k, 300, N, 3.0)
    mul(s, "inst", 300, N, 1 / 1.4)
    mul(s, "d0_inr", 300, N, 0.8)
    return s


def case_T():
    s = synth(cohort=True)
    for d in range(120, N):
        s["c_r7"][d] *= 0.9985 ** (d - 119)
    return s


def _cases():
    c = {}
    c["A"] = (case_A(), None, "app")
    s = synth()
    mul(s, "inst", 300, N, 1 / 1.4)
    mul(s, "inst", 330, N, 1 / 1.3)
    c["C"] = (s, ["CPI"], "app")
    s = synth()
    mul(s, "inst", 300, N, 1 / 1.4)
    for d in range(320, N):
        s["inst"][d] /= 1.01 ** min(d - 319, 40)
    c["C2"] = (s, ["CPI"], "app")
    c["D"] = (case_D(), ["CPI", "SPEND"], "app")
    s = synth()
    for k in SPEND_KEYS:
        for d in range(200, 240):
            s[k][d] = 0.0
    mul(s, "inst", 240, N, 1 / 1.5)
    c["E"] = (s, ["CPI", "GAP", "SPEND"], "app")
    c["F"] = (case_F(), ["CPI", "GAP", "ROAS_G"], "app")
    s = synth()
    mul(s, "inst", 300, N, 1 / 1.4)
    for k in SPEND_KEYS:
        for d in range(330, N):
            s[k][d] = 0.0
    c["G"] = (s, ["CPI", "SPEND"], "app")
    s = synth()
    mul(s, "rev", 300, N, 0.75)
    for k in SPEND_KEYS:
        mul(s, k, 330, N, 0.005)
    c["H"] = (s, ["ECPM", "SPEND"], "app")
    s = synth(cohort=True)
    mul(s, "d0_inr", 300, N, 0.8)
    c["I1"] = (s, ["ROAS_G", "ROAS_C0"], "app")
    s = synth(cohort=True)
    mul(s, "d0_inr", 300, N, 0.8)
    mul(s, "c_r0", 300, N, 0.8)
    c["I2"] = (s, ["ROAS_G", "ROAS_C0"], "app")
    s = synth()
    mul(s, "inst", 150, 164, 1 / 0.7)
    c["J"] = (s, ["CPI"], "app")
    s = synth(sp=15.0)
    mul(s, "inst", 300, N, 1 / 1.4)
    c["K"] = (s, ["CPI"], "app")
    s = synth()
    mul(s, "inst", 35, N, 1 / 1.3)
    c["L"] = (s, ["CPI"], "app")
    s = synth()
    mul(s, "inst", 35, N, 1 / 1.5)
    c["L2"] = (s, ["CPI"], "app")
    s = synth(noise=0.30, seed=7)
    mul(s, "inst", 300, N, 1 / 1.4)
    c["M"] = (s, ["CPI"], "app")
    s = synth(noise=0.30, seed=7)
    mul(s, "inst", 300, N, 1 / 2.0)
    c["M2"] = (s, ["CPI"], "app")
    s = synth()
    for k in SPEND_KEYS:
        mul(s, k, 300, 340, 0.4)
    c["N"] = (s, ["SPEND"], "app")
    s = synth()
    for d in range(120, N):
        s["d0_inr"][d] *= 0.9985 ** (d - 119)
    c["O"] = ({k: s[k] for k in SPEND_KEYS}, None, "camp")
    s = synth()
    mul(s, "inst", 150, 164, 1 / 0.7)
    mul(s, "inst", 164, N, 1 / 1.4)
    c["P"] = (s, ["CPI"], "app")
    s = synth(cohort=True)
    for d in range(N):
        s["c_n"][d] = s["inst"][d] / 0.5
    mul(s, "d0_inr", 300, N, 0.8)
    c["Q"] = (s, ["ROAS_G", "ROAS_C0"], "app")
    s = synth()
    mul(s, "imp", 300, N, 0.7)
    mul(s, "rev", 300, N, 0.7)
    c["R"] = (s, ["IPU", "ECPM"], "app")
    c["T"] = (case_T(), ["ROAS_C7"], "app")
    s = synth()
    mul(s, "inst", 300, N, 1 / 1.4)
    mul(s, "inst", 312, N, 1 / 1.3)
    c["U"] = (s, ["CPI"], "app")
    s = synth()
    mul(s, "inst", 150, 200, 1 / 1.4)
    for d in range(260, N):
        s["inst"][d] /= 1.01 ** min(d - 259, 45)
    c["V"] = (s, ["CPI"], "app")
    s = synth(sp=8.0)
    mul(s, "rev", 300, N, 0.75)
    c["W"] = (s, ["ECPM"], "app")
    return c


EXPECT = {
    # open / freeze / close: the step holds the alarm open after P14 fills with the bad level, then it recovers
    "A": [("CPI", "SUDDEN", 300, 306, 368, "recovered", 0.1997, 0.25, [309], ["step"], None),
          ("GAP", "SUDDEN", 300, 307, 368, "recovered", 39.8192, 0.3, [310], ["step"], None)],
    "C": [("CPI", "SUDDEN", 300, 306, None, None, 0.1997, 0.25, [309, 338], ["step", "step"], None)],
    "C2": [("CPI", "SUDDEN", 300, 306, None, None, 0.1997, 0.25, [309, 339, 362], ["step", "slide", "slide"], None)],
    "D": [("CPI", "DRIFT", 254, 279, None, None, 0.2003, 0.15, [303], ["slide"], None)],
    "E": [],                              # a restart is a warm-up, never compared with the level before the pause
    # spend ×3: the guard blocks SUDDEN CPI / GAP; the legacy DRIFT guard leaks (its span takes in the scale-up)
    "F": [("CPI", "DRIFT", 294, 337, None, None, 0.2001, 0.15, [], [], None),
          ("GAP", "DRIFT", 294, 335, None, None, 40.1943, 0.2, [], [], None),
          ("ROAS_G", "SUDDEN", 299, 304, None, None, 0.4, 0.12, [307], ["step"], "no_data")],
    "G": [("CPI", "SUDDEN", 300, 306, 336, "stopped", 0.1997, 0.25, [309], ["step"], None)],
    "H": [("ECPM", "SUDDEN", 300, 306, 336, "no_paid", 5.0142, 0.15, [309], ["step"], None),
          ("SPEND", "SUDDEN", 330, 335, None, None, 998.3695, 0.5, [338, 353], ["step", "slide"], None)],
    "I1": [],                             # Google D0 down, the AdMob-matched D0 line flat: not confirmed
    "I2": [("ROAS_G", "SUDDEN", 300, 306, None, None, 0.3999, 0.12, [309, 396], ["step", "slide"], "confirmed"),
           ("ROAS_C0", "SUDDEN", 301, 307, None, None, 0.4004, 0.12, [310, 407], ["step", "slide"], None)],
    "J": [],                              # back to normal after a cheap fortnight: base_band → H, the re-check fails
    "K": [],                              # below $50 a week
    "L": [],                              # young series: no swing yet, the minimum × 1.5
    "L2": [("CPI", "SUDDEN", 35, 43, None, None, 0.1998, 0.398, [58], ["slide"], None)],
    "M": [("CPI", "DRIFT", 293, 316, None, None, 0.2023, 0.162, [408], ["slide"], None)],
    "M2": [("CPI", "SUDDEN", 300, 303, None, None, 0.2049, 0.371, [306, 321, 408], ["step", "slide", "slide"], None)],
    "N": [("SPEND", "SUDDEN", 300, 307, 349, "recovered", 1002.8494, 0.5, [310], ["step"], None)],
    "O": [("ROAS_G", "ABSOLUTE", 157, 213, None, None, 0.3981, 0.105, [271, 329, 387], ["slide"] * 3, "no_data")],
    "P": [("CPI", "SUDDEN", 164, 172, None, None, 0.1994, 0.25, [175], ["step"], None)],
    "Q": [("ROAS_G", "SUDDEN", 300, 306, None, None, 0.3999, 0.12, [309, 396], ["step", "slide"], "no_data")],
    "R": [("IPU", "SUDDEN", 301, 306, None, None, 5.0171, 0.15, [309, 324], ["step", "slide"], None)],
    # the legacy recovery band (10 %) is wider than the DRIFT minimum (7 %): it 'recovers' and re-opens
    "T": [("ROAS_C7", "DRIFT", 163, 201, 205, "recovered", 0.6223, 0.07, [], [], None),
          ("ROAS_C7", "DRIFT", 160, 215, None, None, 0.6291, 0.07, [270, 327, 386], ["slide"] * 3, None)],
    "U": [("CPI", "SUDDEN", 300, 306, None, None, 0.1997, 0.25, [309, 324], ["step", "slide"], None)],
    "V": [("CPI", "SUDDEN", 150, 156, 208, "recovered", 0.1999, 0.25, [159], ["step"], None),
          ("CPI", "DRIFT", 263, 289, None, None, 0.2001, 0.15, [312], ["slide"], None)],
    "W": [],                              # 8 $ a day: the eCPM alarm needs paid users
}
CASES = _cases()


@pytest.mark.parametrize("name", sorted(EXPECT))
def test_parity_reference_values(name):
    s, fams, kind = CASES[name]
    assert [brief(ep) for ep in run(s, E.P_PARITY, kind, fams)] == EXPECT[name]


def test_episode_shape_and_dates():
    ep = run(case_A(), fams=["CPI"])[0]
    assert set(ep) >= {"kind", "id", "app", "fam", "opener", "tier", "c", "opened", "seen", "closed", "why", "base",
                       "base_src", "thr_open", "max_worse", "esc", "confirm", "ctx", "money"}
    assert (ep["kind"], ep["id"], ep["app"]) == ("app", APP, APP)
    assert ix(ep["seen"]) == ix(ep["opened"]) + 2 and ep["base_src"] == "before"
    assert ep["esc"] == [[(date.fromisoformat(DAY0) + timedelta(days=309)).isoformat(), "step"]]
    assert ep["money"] is None                        # CPI money only in P_PROD (and never a loss)
    assert ep["tier"] == "ALERT" and ep["ctx"]["GAP"] >= 0.5 * ep["thr_open"]   # GAP rose with it → ALERT
    assert 0.39 < ep["max_worse"] < 0.42
    # a shifted family's c is the DATA day of the change (calendar c − shift)
    r = run(CASES["R"][0], fams=["IPU"])[0]
    assert ix(r["c"]) == 300 and ix(r["opened"]) == 306


def test_base_src_codes():
    assert run(case_D(), fams=["CPI"])[0]["base_src"] == "healthy"
    assert run(CASES["O"][0], kind="camp")[0]["base_src"] == "usual"
    assert run(CASES["P"][0], fams=["CPI"])[0]["base_src"] == "band"


def test_tiers():
    eps = {(ep["fam"], ep["opener"]): ep["tier"] for ep in run(case_F(), fams=["CPI", "GAP", "ROAS_G"])}
    assert eps == {("CPI", "DRIFT"): "WATCH", ("GAP", "DRIFT"): "ALERT", ("ROAS_G", "SUDDEN"): "ALERT"}
    assert [ep["tier"] for ep in run(case_T(), fams=["ROAS_C7"])] == ["LINE", "LINE"]
    assert run(CASES["O"][0], kind="camp")[0]["tier"] == "LINE"                 # never an app tier off the app
    assert E.tier({"kind": "app", "fam": "ROAS_C7", "opener": "ABSOLUTE"}) == "ALERT"
    assert E.tier({"kind": "app", "fam": "CPI", "opener": "SUDDEN", "thr_open": 0.25, "ctx": {"GAP": 0.1}}) == "WATCH"
    assert E.tier({"kind": "app", "fam": "ECPM", "opener": "SUDDEN"}) == "WATCH"


def test_roas_money_is_measured_cost_minus_value_over_base():
    s = CASES["I2"][0]
    g, c0 = run(s, fams=["ROAS_G", "ROAS_C0"])
    B, c = g["base"], ix(g["c"])
    inr = sum(s["sp_inr"][d] - s["d0_inr"][d] / B for d in range(c, N))
    usd = sum(s["sp_usd"][d] - s["d0_inr"][d] * (s["sp_usd"][d] / s["sp_inr"][d]) / B for d in range(c, N))
    assert g["money"]["since_c_inr"] == pytest.approx(inr, abs=0.01)
    assert g["money"]["since_c_usd"] == pytest.approx(usd, abs=0.01)
    assert g["money"]["cost_inr"] == pytest.approx(sum(s["sp_inr"][c:]), abs=0.01)
    assert g["money"]["what"] == "loss" and inr > 0
    # the AdMob-matched line: matured install days only (shift 1: up to t − 1), USD
    B0, c = c0["base"], ix(c0["c"])
    usd0 = sum(s["c_sp"][d] - s["c_r0"][d] / B0 for d in range(c, N - 1))
    assert c0["money"]["since_c_usd"] == pytest.approx(usd0, abs=0.01)


def test_state_at_t():
    def st(s, P=E.P_PARITY, kind="app"):
        return E.run([ent(s, kind)], P, T)["state"][(kind, APP)]
    assert st(CASES["C"][0])["CPI"] == "open"
    assert st(case_A())["CPI"] == "ok"
    assert st(CASES["G"][0])["CPI"] == "gated"           # paused
    assert st(CASES["W"][0])["ECPM"] == "gated"          # no paid users
    assert st(case_A())["ROAS_C0"] == "na"               # no cohort rows
    assert set(st(CASES["O"][0], kind="camp")) == {"CPI", "ROAS_G", "SPEND"}
    young = synth()
    for k in SPEND_KEYS:
        for d in range(0, N - 10):
            young[k][d] = 0.0
    assert st(young)["CPI"] == "warm"


def test_normal_and_healthy_per_day():
    r = E.run([ent(CASES["C"][0])], E.P_PARITY, T)
    ep = [x for x in r["episodes"] if x["fam"] == "CPI"][0]
    nrm, hl = r["normal"][("app", APP)], r["healthy"][("app", APP)]
    assert set(nrm) == set(hl) == {"CPI", "ECPM", "ROAS_G", "GAP", "IPU", "ROAS_C0"}
    assert all(len(v) == N for v in list(nrm.values()) + list(hl.values()))
    o = ix(ep["opened"])
    assert all(x == ep["base"] for x in nrm["CPI"][o:])         # the frozen B while open
    assert nrm["CPI"][o - 1] == hl["CPI"][o - 1] == pytest.approx(0.2, rel=0.02)
    # H with every span known at t never reads the problem's days: the old level while 4 clean windows are left,
    # then none (the whole 90 days are the problem)
    assert hl["CPI"][340] == pytest.approx(0.2, rel=0.02)
    assert hl["CPI"][N - 1] is None
    assert nrm["ROAS_C0"] == [None] * N
    assert r["normal"].get(("camp", APP)) is None


def test_run_is_pure_and_deterministic():
    s = case_F()
    ents = [ent(s), ent({k: s[k] for k in SPEND_KEYS}, kind="camp", eid="c1")]
    before = copy.deepcopy(ents)
    a = E.run(ents, E.P_PROD, T)
    assert [(e.kind, e.id, e.s) for e in ents] == [(e.kind, e.id, e.s) for e in before]
    b = E.run(ents, E.P_PROD, T)
    assert a == b
    assert E.P_PARITY["esc_from"] == 1 and E.P_PARITY["settle"] is None      # P dicts untouched by a run


def test_weekly_noise_refresh_is_on_the_epoch_phase():
    s = CASES["M"][0]
    t7 = (date.fromisoformat(T) + timedelta(days=7)).isoformat()
    d7 = (date.fromisoformat(DAY0) + timedelta(days=7)).isoformat()
    a = [(ep["fam"], ep["opener"], ix(ep["c"]), ix(ep["opened"])) for ep in E.run([ent(s)], E.P_PARITY, T)["episodes"]]
    b = [(ep["fam"], ep["opener"], ix(ep["c"]) - 7, ix(ep["opened"]) - 7)
         for ep in E.run([ent(s, day0=d7)], E.P_PARITY, t7)["episodes"]]
    assert a and a == b


def test_data_after_t_is_never_read():
    s = case_A()
    long = {k: v + [9e9] * 30 for k, v in s.items() if v[0] is not None}
    long["dau"] = s["dau"] + [1.0] * 30
    assert E.run([ent(s)], E.P_PROD, T) == E.run([ent(long)], E.P_PROD, T)


# ── P_PROD: the production changes ────────────────────────────────────────────────────────────────────────────────
def step_held():
    s = synth()
    mul(s, "inst", 300, N, 1 / 1.4)
    return s


def test_prod_settle_accepts_a_steady_new_level():
    r = E.run([ent(step_held())], E.P_PROD, T)
    cpi = [x for x in r["episodes"] if x["fam"] == "CPI"]
    assert len(cpi) == 1 and cpi[0]["why"] == "settled"
    assert ix(cpi[0]["closed"]) - ix(cpi[0]["opened"]) >= 56
    # no exclusion span: H follows the new level (₹ 94.5 × 0.2 × 1.4) and nothing re-opens on it
    assert r["healthy"][("app", APP)]["CPI"][N - 1] == pytest.approx(94.5 * 0.2 * 1.4, rel=0.02)
    assert r["normal"][("app", APP)]["CPI"][N - 1] == r["healthy"][("app", APP)]["CPI"][N - 1]
    assert r["state"][("app", APP)]["CPI"] == "ok"
    # the parity run keeps it open against the old level
    old = [x for x in E.run([ent(step_held())], E.P_PARITY, T)["episodes"] if x["fam"] == "CPI"]
    assert old[0]["why"] is None and old[0]["closed"] is None


def test_prod_money_families_never_settle():
    s = synth(cohort=True)
    mul(s, "d0_inr", 300, N, 0.8)
    mul(s, "c_r0", 300, N, 0.8)
    eps = run(s, E.P_PROD, fams=["ROAS_G", "ROAS_C0"])
    assert [(x["fam"], x["why"]) for x in eps] == [("ROAS_G", None), ("ROAS_C0", None)]
    assert all(x["money"]["since_c_inr"] > 0 for x in eps)


def test_renotice_from_open_plus_7_switch():
    # OFF in P_PROD (it lost a known incident in the backtest); the switch drops the opening's own step at +3
    assert [ix(d) for d, _ in run(case_A(), E.P_PROD, fams=["CPI"])[0]["esc"]] == [309]
    P = dict(E.P_PROD, esc_from=7, settle=None)
    esc = run(step_held(), P, fams=["CPI"])[0]["esc"]
    assert all(ix(d) >= 306 + 7 for d, _ in esc) and esc[0][1] == "slide"


def test_adaptive_recovery_band_switch():
    # OFF in P_PROD (backtest); on, a 7 % DRIFT alarm cannot 'recover' in a 10 % band without any improvement
    assert [x["why"] for x in run(case_T(), E.P_PROD, fams=["ROAS_C7"])][0] == "recovered"
    eps = run(case_T(), dict(E.P_PROD, thr_r_mode="adaptive"), fams=["ROAS_C7"])
    assert len(eps) == 1 and eps[0]["why"] is None


def test_prod_drift_scale_guard_holds_a_lasting_scale_up():
    # the DRIFT guard's base spend = the windows H's value comes from (before the scale-up): no CPI / GAP opening
    eps = run(case_F(), E.P_PROD, fams=["CPI", "GAP", "ROAS_G"])
    assert [(x["fam"], x["opener"]) for x in eps] == [("ROAS_G", "SUDDEN")]
    # every window of H ('windows') is the legacy span again here and leaks like it
    leak = run(case_F(), dict(E.P_PARITY, drift_bsp="windows"), fams=["CPI", "GAP"])
    assert [(x["fam"], x["opener"]) for x in leak] == [("CPI", "DRIFT"), ("GAP", "DRIFT")]


def test_prod_roas_g_volume_gate_in_usd():
    s = {"sp_usd": [9.6] * 30, "sp_inr": [960.0] * 30, "d0_inr": [400.0] * 30, "inst": [50.0] * 30}
    e = E.Ent("camp", "c1", APP, "Alpha campaign", DAY0, s)
    legacy = E._Ser(e, 30, E.P_PARITY)
    prod = E._Ser(e, 30, E.P_PROD)
    assert legacy.value("ROAS_G", 0, 13) == pytest.approx(400 / 960)     # ₹960 ≥ $10 × the old fixed rate
    assert prod.value("ROAS_G", 0, 13) is None                           # $9.60 < $10 a day


def test_prod_cpi_in_inr_ignores_an_fx_move():
    s = synth()
    mul(s, "sp_usd", 300, N, 1.4)              # the rupee weakens: the same ₹ cost and installs
    assert [x["opener"] for x in run(s, E.P_PARITY, fams=["CPI"])] == ["SUDDEN"]
    assert run(s, E.P_PROD, fams=["CPI"]) == []
    r = E.run([ent(synth())], E.P_PROD, T)
    assert r["healthy"][("app", APP)]["CPI"][N - 1] == pytest.approx(94.5 * 0.2, rel=0.02)


def test_prod_cpi_money_both_currencies_as_extra_paid():
    s = CASES["C"][0]
    ep = run(s, E.P_PROD, fams=["CPI"])[0]
    B, c = ep["base"], ix(ep["c"])
    end = ix(ep["closed"]) if ep["closed"] else N - 1          # (this one settles: money up to its close)
    assert B == pytest.approx(94.5 * 0.2, rel=0.02)
    inr = sum(s["sp_inr"][d] - s["inst"][d] * B for d in range(c, end + 1))
    assert ep["money"]["since_c_inr"] == pytest.approx(inr, abs=0.01)
    assert ep["money"]["since_c_usd"] == pytest.approx(inr / 94.5, rel=1e-6)
    assert ep["money"]["what"] == "extra_paid"


def test_prod_country_eligibility_trailing_window():
    app = synth()
    big, small, gone = synth(seed=3, sp=50.0), synth(seed=4, sp=10.0), synth(seed=5, sp=200.0)
    for s in (big, small, gone):
        mul(s, "inst", 300, N, 1 / 1.4)
    for k in SPEND_KEYS:
        for d in range(200, N):
            gone[k][d] = 0.0
    ents = [ent(app)] + [E.Ent("country", APP + "|" + cc, APP, cc, DAY0, {"sp_usd": s["sp_usd"], "inst": s["inst"]})
                         for cc, s in (("US", big), ("BR", small), ("KR", gone))]
    prod = E.run(ents, E.P_PROD, T)

    def replayed(r, cc):
        return any(v != "na" for v in r["state"][("country", APP + "|" + cc)].values())
    assert replayed(prod, "US") and not replayed(prod, "BR") and not replayed(prod, "KR")
    assert any(x["kind"] == "country" and x["fam"] == "CPI" for x in prod["episodes"])
    par = E.run(ents, E.P_PARITY, T)
    assert replayed(par, "BR") and replayed(par, "KR")


def test_prod_unknown_days_never_recover_or_stop_an_alarm():
    s = step_held()
    for d in range(330, N):
        if d % 7 in (0, 2, 4):
            s["sp_usd"][d] = s["sp_inr"][d] = None
    # the legacy (lenient) sums read an unknown spend day as 0: CPI looks back to normal and 'recovers'
    assert run(s, E.P_PARITY, fams=["CPI"])[0]["why"] == "recovered"
    ep = run(s, dict(E.P_PROD, settle=None), fams=["CPI"])[0]
    assert ep["why"] is None
    tail = step_held()
    for d in range(360, N):
        tail["sp_usd"][d] = tail["sp_inr"][d] = tail["inst"][d] = None
    assert run(tail, E.P_PARITY, fams=["CPI"])[0]["why"] == "stopped"
    r = E.run([ent(tail)], E.P_PROD, T)
    assert [x["why"] for x in r["episodes"] if x["fam"] == "CPI"] == [None]
    assert r["state"][("app", APP)]["CPI"] == "open" and r["state"][("app", APP)]["SPEND"] == "gated"


# ── pushes and cards ──────────────────────────────────────────────────────────────────────────────────────────────
def _ep(fam, tier, opened, closed=None, esc=(), stake=None, app=APP):
    return {"kind": "app", "app": app, "fam": fam, "opener": "SUDDEN", "tier": tier, "opened": opened,
            "closed": closed, "esc": [[d, "step"] for d in esc], "stake": stake or [0.0] * (1 + len(esc))}


def test_notifications_one_push_per_7_days_alert_only():
    eps = [_ep("ROAS_G", "ALERT", "2024-03-01", esc=["2024-03-20"], stake=[120.0, 800.0]),
           _ep("GAP", "ALERT", "2024-03-05", stake=[300.0]),
           _ep("ECPM", "WATCH", "2024-03-02", stake=[999.0]),
           _ep("CPI", "ALERT", "2024-03-01", app="ca-app-pub-0000000000000000~22")]
    pushes = E.notifications(eps)
    mine = [p for p in pushes if p["app"] == APP]
    assert [(p["day"], len(p["items"]), p["stake"]) for p in mine] == [
        ("2024-03-01", 2, 300.0), ("2024-03-20", 1, 800.0)]
    assert [i["kind"] for i in mine[0]["items"]] == ["open", "open"]
    assert len(pushes) == 3


def test_engine_renotices_are_15_days_apart():
    for name in ("C", "C2", "U", "M2"):
        esc = [ix(d) for d, _ in run(CASES[name][0], fams=["CPI"])[0]["esc"]]
        assert all(b - a > 14 for a, b in zip(esc, esc[1:]))


def test_cards_merge_touching_episodes():
    eps = [_ep("CPI", "WATCH", "2024-03-01", "2024-03-10"), _ep("GAP", "ALERT", "2024-03-15", "2024-03-20"),
           _ep("ROAS_G", "ALERT", "2024-05-01")]
    cs = E.cards(eps)
    assert [(c["open"], c["close"], len(c["episodes"])) for c in cs] == [("2024-03-01", "2024-03-20", 2),
                                                                         ("2024-05-01", None, 1)]
