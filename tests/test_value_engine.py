"""The Install value tab's engine (admob_iq.engine.value, SPEC_AB_FINAL §2): AdMob is the money total and GA4 only
splits it (the app's monthly k, countries too), immature cells are null (never a small number), money back is observed
or ≈ projected with a band, countries are pooled by week with honest sample rules and never judged on weeks GA4 did not
fully split, the weekly alerts keep the no-flood rules, and every text is Roman Hinglish. All data is synthetic
(tests.value_synth)."""

import copy
import math
import os
import re
from datetime import date, timedelta

import pytest

from admob_iq.engine import value as V
from tests import value_synth as vs

END = vs.END
S = END - timedelta(days=vs.LATE)                       # the newest folded GA4 day
E = V._eval_end(S)                                      # the settled week end the alerts are judged at
START = END - timedelta(days=60 * 7 - 1)
AID = "ca-app-pub-0000000000000000~0000000009"
NOW = "2026-09-21T12:00:00Z"
CFG = {"payback_days": 90}
SMALL = dict(vs.CTY, ZZ=(0.0755, 1.0, 0.006), KE=(0.004, 1.0, 0.004), TZ=(0.0005, 1.0, 0.004))


def ev(m, st=None, cfg=None, now=NOW, releases=(), portfolio=None, **kw):
    return V.evaluate_app(m["store"], m["ida"], m["rev"], m["spend"], m["fx"], list(releases), st,
                          portfolio or {}, dict(CFG, **(cfg or {})), now, app_id=AID, app="Demo App", key="k", **kw)


def app(**kw):
    kw.setdefault("start", START)
    kw.setdefault("seed", 3)
    return vs.make_app(**kw)


def weeks_by_from(det):
    return {w["from"]: w for w in det["weeks"]}


def alerts(row, family=None):
    return [a for a in row["_alerts"] if family is None or a["family"] == family]


@pytest.fixture(scope="module")
def base():
    m = app()
    det, row, st = ev(m)
    return m, det, row, st


# ── money: AdMob is the total, GA4 only splits it (§1.6) ───────────────────────────────────────

def test_scale_totals_tie():
    m = app(k=1.2, k_from=date(2026, 6, 1), k_after=0.9)
    hs, days = m["hs"], m["ida"]["days"]
    sc = V.scale(m["ida"], m["rev"], "UTC", hs, S)
    assert sc["kinfo"][date(2026, 3, 2)][:2] == (pytest.approx(1.2), "ok")          # k per activity WEEK
    assert sc["kinfo"][date(2026, 7, 6)][:2] == (pytest.approx(0.9), "ok")
    W, n = V._mon(hs) + timedelta(days=7), 0
    while W + timedelta(days=6) <= S:
        ds = [W + timedelta(days=i) for i in range(7)]
        scaled = sum(sc["kf"](d)[0] * (days[d.isoformat()]["rev4"] + days[d.isoformat()]["rb_old"]) for d in ds)
        admob = sum(m["rev"]["all_days"][d.isoformat()][0] for d in ds)
        assert scaled == pytest.approx(admob, rel=0.01)
        W += timedelta(days=7)
        n += 1
    assert n > 50
    det, _, _ = ev(m)
    one, _, _ = ev(app())
    a, b = weeks_by_from(det), weeks_by_from(one)
    wk = det["weeks"][-2]["from"]                                  # an old week, all in the k = 1.2 months
    assert a[wk]["rpi"][5] == pytest.approx(1.2 * b[wk]["rpi"][5], rel=1e-3)


def test_country_uses_app_k():
    d1, _, _ = ev(app(k=1.5))
    d0, _, _ = ev(app())
    r1 = {r["cc"]: r for r in d1["countries"]["rows"]}
    for r in d0["countries"]["rows"]:
        assert r1[r["cc"]]["rpi"]["30"]["v"] == pytest.approx(1.5 * r["rpi"]["30"]["v"], rel=1e-3)
        assert r1[r["cc"]]["d1"]["v"] == r["d1"]["v"]                # users are never scaled


def test_k_out_of_range_flags_estimate():
    det, row, _ = ev(app(k=1.9))
    assert det["scale"]["st"] == "est"
    assert all(k[2] == "est" for k in det["scale"]["k_weeks"])
    assert any(w["est"][5] for w in det["weeks"] if w["rpi"][5] is not None)
    assert any(i["kind"] == "k" for i in det["changes"]["info"])
    det2, _, _ = ev(app(k=2.6))
    assert {k[1] for k in det2["scale"]["k_weeks"]} == {V.K_CLAMP[1]}           # clamped
    ok, _, _ = ev(app(k=1.1))
    assert ok["scale"]["st"] == "ok" and not any(any(w["est"]) for w in ok["weeks"])


# ── cells: immature = null, ≈ marks (§2.2) ────────────────────────────────────────────────────

def test_immature_cell_is_null(base):
    _, det, _, _ = base
    for w in det["weeks"]:
        last = date.fromisoformat(w["to"])
        for j, t in enumerate(V.T):
            if last + timedelta(days=t) > S:
                assert w["rpi"][j] is None and w["L"][j] is None
            else:
                assert w["rpi"][j] is not None and w["rpi"][j] > 0
    newest = det["weeks"][0]
    assert newest["t_o"] is not None and newest["rpi"][9] is None and newest["Lp"][9] is not None


def test_q_day_cells_marked():
    qd = S - timedelta(days=40)
    det, _, _ = ev(app(q_days=(qd,)))
    hit = 0
    for w in det["weeks"]:
        a, b = date.fromisoformat(w["from"]), date.fromisoformat(w["to"])
        for j, t in enumerate(V.T):
            if w["rpi"][j] is None:
                assert not w["Lq"][j]
                continue
            touches = a <= qd <= b + timedelta(days=t)
            assert w["Lq"][j] == touches
            hit += touches
    assert hit > 0


# ── money back (§2.3, §2.4) ───────────────────────────────────────────────────────────────────

def test_payback_observed_interpolated(base):
    _, det, _, _ = base
    old = det["weeks"][-3]
    assert old["pay"]["obs"] and not old["pay"]["never"]
    L = old["L"]
    j = next(j for j in range(10) if L[j] >= 100)
    want = V.T[j - 1] + (100 - L[j - 1]) / (L[j] - L[j - 1]) * (V.T[j] - V.T[j - 1])
    assert abs(old["pay"]["p"] - want) <= 1 and 30 < old["pay"]["p"] < 60


def test_payback_projected_band(base):
    _, det, row, _ = base
    w = det["weeks"][1]                                            # t_o = 7
    assert w["t_o"] == 7 and w["pay"] and not w["pay"]["obs"]
    p = w["pay"]
    assert p["lo"] <= p["p"] <= p["hi"]
    for j, t in enumerate(V.T):
        if t <= 7:
            assert w["Lp"][j] is None and w["L"][j] is not None
        else:
            assert w["L"][j] is None and w["Llo"][j] <= w["Lp"][j] <= w["Lhi"][j]
    # the tile / row: the newest judged week with 7 days of earnings (a 3-day-old week's estimate is too early)
    assert det["weeks"][0]["t_o"] < 7 and row["pay"]["from"] == w["from"]
    assert row["pay"]["p"] == w["pay"]["p"] and row["pay"]["obs"] is False


def test_payback_never():
    det, row, _ = ev(app(cpi=0.5))
    old = det["weeks"][-1]
    assert old["pay"]["never"] and old["pay"]["obs"] and 0 < old["pay"]["pct365"] < 100
    new = det["weeks"][1]
    assert new["pay"]["never"] and not new["pay"]["obs"] and 0 < new["pay"]["pct365"] < 100
    assert "saal bhar me bhi nahi" in V.p_phrase(new["pay"])
    assert row["pay"]["never"] and det["tiles"]["pay"]["v"] == 366


def test_no_projection_without_refs():
    det, row, _ = ev(app(start=END - timedelta(days=10 * 7 - 1)))
    w = det["weeks"][0]                               # its own weeks are 10 weeks old at most: no year-long curve
    assert w["pay"] is None and w["why"] == "noproj" and w["Lp"][9] is None and w["Lp"][8] is None
    with_p = [x for x in det["weeks"] if x["pay"]]                # an older week's P is known …
    assert with_p and with_p[0]["t_o"] >= 14
    t = det["tiles"]["pay"]                                       # … the tile still says why the newest has none
    assert row["pay"]["p"] is None and t["st"] == "wait" and t["why"] == "curve" and "abhi andaza nahi" in t["note"]
    assert "pichhla pata" in t["note"] and "abhi andaza nahi" in det["summary"]["text"]
    assert "abhi pata nahi" == V.p_phrase(None)


def test_portfolio_shape_fallback_marked(base):
    _, _, row0, _ = base
    shape = V.portfolio_shape([row0["_shape"]] * V.PORTF_MIN_APPS)
    assert V.portfolio_shape([row0["_shape"]] * (V.PORTF_MIN_APPS - 1)) == {}
    det, row, _ = ev(app(start=END - timedelta(days=10 * 7 - 1)), portfolio=shape)
    w = det["weeks"][0]
    assert w["shape"] == "portfolio" and w["pay"] is not None and det["curve"]["shape"] == "portfolio"


# ── cost per install, FX (§1.7) ────────────────────────────────────────────────────────────────

def test_cpi_blended_and_paid(base):
    _, det, row, _ = base
    for w in det["weeks"][:-1]:
        assert w["ecpi"] == pytest.approx(0.06, rel=2e-3)          # spend ÷ ALL new users
        assert w["cpi_ads"] == pytest.approx(0.06 / 0.87, rel=5e-3)
        assert w["paid"] == pytest.approx(0.87, abs=0.005)
    assert row["cpi"]["v"] == pytest.approx(0.06, rel=2e-3) and row["cpi"]["paid_share"] == pytest.approx(0.87, abs=0.01)


def test_fx_dated_vs_one():
    m = app()
    det, _, _ = ev(m)
    one = copy.deepcopy(m)
    one["fx"] = {"mode": "one", "now": m["fx"]["now"], "series": {}}
    d1, _, _ = ev(one)
    assert det["fx"]["mode"] == "dated" and d1["fx"]["mode"] == "one"
    old, old1 = det["weeks"][-2], d1["weeks"][-2]
    assert old["ecpi"] == pytest.approx(0.06, rel=2e-3)            # each week at its own rate
    assert abs(old1["ecpi"] / old["ecpi"] - 1) > 0.01              # today's rate on an old week: off by the drift
    new, new1 = det["weeks"][1], d1["weeks"][1]
    assert new1["ecpi"] == pytest.approx(new["ecpi"], rel=2e-3)


# ── countries (§2.5) ──────────────────────────────────────────────────────────────────────────

def test_country_rates_pooled_by_week(base):
    m, det, _, _ = base
    c = det["countries"]
    slot = str(m["ida"]["cset"].index("US"))
    ws = sorted((W for W in m["ida"]["c"] if date.fromisoformat(W) + timedelta(days=7) <= S
                 and W >= c["win"]["from"]), reverse=True)[:4]
    x = sum(m["ida"]["c"][W][slot]["u"][0] for W in ws)
    n = sum(m["ida"]["c"][W][slot]["n"] for W in ws)
    us = next(r for r in c["rows"] if r["cc"] == "US")
    assert us["d1"]["v"] == pytest.approx(100 * x / n, rel=1e-3) and us["n"] == n
    assert c["win"]["weeks"] == 4 and us["d1"]["lo"] < us["d1"]["v"] < us["d1"]["hi"]
    assert us["share"] == pytest.approx(0.18, abs=0.01)


def test_all_row_from_qb_not_country_sum(base):
    m, det, _, _ = base
    m2 = copy.deepcopy(m)
    for W, slots in m2["ida"]["c"].items():                        # travellers + HLL: Σ countries runs a bit high
        for k, cell in slots.items():
            if k != "gap":
                cell["u"] = [int(u * 1.03) for u in cell["u"]]
    d2, _, _ = ev(m2)
    assert d2["countries"]["app"]["d1"] == det["countries"]["app"]["d1"]
    us = lambda d: next(r for r in d["countries"]["rows"] if r["cc"] == "US")["d1"]["v"]
    assert us(d2) > us(det)


def test_wilson_phi_interval():
    p, lo, hi = V._wilson(300, 1000, 1.0)
    z = V.WILSON_Z
    c = (0.3 + z * z / 2000) / (1 + z * z / 1000)
    h = z * math.sqrt(0.3 * 0.7 / 1000 + z * z / (4 * 1000 ** 2)) / (1 + z * z / 1000)
    assert (p, lo, hi) == pytest.approx((0.3, c - h, c + h))
    _, lo2, hi2 = V._wilson(300, 1000, 2.0)
    assert hi2 - lo2 > (hi - lo) * 1.35                            # overdispersion widens it (~√2)


def test_small_country_not_ranked():
    det, row, _ = ev(app(countries=SMALL))
    c = det["countries"]
    ke = next(r for r in c["rows"] if r["cc"] == "KE")
    assert V.CTY_SHOW <= ke["n"] < V.CTY_JUDGE and ke["few"] and ke["verdict"] == "few" and ke["rank"] is None
    assert "faisla ke liye kam (300 chahiye)" in ke["text"]
    assert "TZ" not in {r["cc"] for r in c["rows"]} and c["small"]["countries"] == 1
    assert "KE" not in row["cty"]["best"] + row["cty"]["weak"]


def test_small_country_never_alerts():
    m = app(countries=SMALL, drop=("KE", date(2026, 8, 31), 0.2))
    _, row, _ = ev(m)
    assert not [a for a in alerts(row, "geo_move") if a["cc"] == "KE"]


def test_unknown_other_and_unassigned_never_ranked():
    det, row, _ = ev(app(gap_days=tuple(S - timedelta(days=150 + i) for i in range(3))))
    c = det["countries"]
    assert {"--", "ZZ"}.isdisjoint({r["cc"] for r in c["rows"]})
    assert c["unknown"]["n"] > 0 and c["small"]["zz"] > 0
    assert {"--", "ZZ"}.isdisjoint(row["cty"]["best"] + row["cty"]["weak"])
    assert not [a for a in row["_alerts"] if a.get("cc") in ("--", "ZZ")]


def test_window_widens_to_12_weeks():
    det, row, _ = ev(app(base=20, spend=False))
    assert det["countries"]["win"]["size"] == V.WIN_WEEKS_SMALL and row["cty"]["win_weeks"] == V.WIN_WEEKS_SMALL
    det4, _, _ = ev(app())
    assert det4["countries"]["win"]["size"] == V.WIN_WEEKS


def test_country_gap_blocks_judging():
    gaps = tuple(S - timedelta(days=3 + i) for i in range(12))       # GA4 did not split two recent weeks
    det, row, _ = ev(app(gap_days=gaps, drop=("NG", date(2026, 8, 31), 0.6)))
    c = det["countries"]
    assert all(not r["clean"] and r["verdict"] == "wait" and r["rank"] is None for r in c["rows"])
    assert all("GA4 ne poora nahi diya" in r["text"] for r in c["rows"])
    assert row["cty"]["best"] == [] and row["cty"]["weak"] == [] and not row["cty"]["clean"]
    assert c["unassigned"]["n"] > 0 and c["unassigned"]["n_share"] > V.GAP_MAX
    assert not alerts(row, "geo_move")
    assert any(i["kind"] == "gap" for i in det["changes"]["info"])
    ok, row_ok, _ = ev(app(drop=("NG", date(2026, 8, 31), 0.6)))
    assert all(r["clean"] for r in ok["countries"]["rows"]) and alerts(row_ok, "geo_move")


def test_sampled_app_country_approx():
    det, row, _ = ev(app(smp=True, spend=False))
    c = det["countries"]
    assert c["smp"] and row["cty"]["smp"]
    assert all(r["rpi"][t]["est"] for r in c["rows"] for t in ("1", "7", "30"))


def test_country_value_beyond_90_is_projection():
    det, _, _ = ev(app(), cfg={"payback_days": 180})
    for r in det["countries"]["rows"]:
        assert r["be_proj"] and r["rpi"]["90"]["proj"] is False
        assert r["be"] > r["rpi"]["90"]["v"]
    young, _, _ = ev(app(cty_days=60))                                  # countries read 60 days back only
    for r in young["countries"]["rows"]:
        assert r["rpi"]["90"]["proj"] and r["rpi"]["90"]["est"]
    d90, _, _ = ev(app())
    assert all(not r["be_proj"] for r in d90["countries"]["rows"])      # H = 90: observed


def test_verdict_with_and_without_geo():
    m = app()
    _, _, st0 = ev(m)
    st0["eval"]["end_week"] = (E - timedelta(days=7)).isoformat()   # the same verdicts a week before: Best / Weakest
    det, row, _ = ev(m, st=st0)
    v = {r["cc"]: r["verdict"] for r in det["countries"]["rows"]}
    assert v["US"] == "top" and v["NG"] == "low" and set(v.values()) <= {"top", "avg", "low"}
    assert row["cty"]["best"][0] == "US" and "NG" in row["cty"]["weak"] and all(
        r["cpi"] is None for r in det["countries"]["rows"])
    n = {r["cc"]: r["n"] for r in det["countries"]["rows"]}
    geo = {"US": {"cost": 0.05 * n["US"], "dl": n["US"]}, "IN": {"cost": 0.034 * n["IN"], "dl": n["IN"]},
           "NG": {"cost": 0.08 * n["NG"], "dl": n["NG"]}}
    dg, rg, _ = ev(m, geo=geo)
    g = {r["cc"]: r for r in dg["countries"]["rows"]}
    assert g["US"]["verdict"] == "keep" and g["US"]["sure"] and g["US"]["cpi"]["v"] == pytest.approx(0.05)
    assert g["IN"]["verdict"] == "slow" and g["NG"]["verdict"] == "costly"
    assert "ads yahan mehenge pad rahe" in g["NG"]["text"] and "install $0.050 me pad raha" in V.render_text(g["US"]["text"])
    assert dg["countries"]["geo"] and rg["cty"]["geo"]


# ── alerts (§2.7) ─────────────────────────────────────────────────────────────────────────────

def test_pay_slow_needs_two_weeks_and_projection_move():
    _, row, _ = ev(app(cpi_jump=(date(2026, 8, 31), 1.6)))           # only the newest settled week
    assert not alerts(row, "pay_slow")
    _, row, _ = ev(app(cpi_jump=(date(2026, 8, 24), 1.6)))           # both of the 2 newest
    a = alerts(row, "pay_slow")
    assert len(a) == 1 and a[0]["dir"] == "down" and a[0]["p"] - a[0]["p0"] >= 7 and "cpi" in a[0]["tags"]
    assert a[0]["week_from"] == "2026-08-24" and a[0]["week_to"] == "2026-09-06"
    assert "cost per install $0.060 → $0.096 (+60%)" in a[0]["message"]              # the page draws {q:…} itself
    _, row, _ = ev(app(cpi_jump=(date(2026, 8, 24), 1 / 1.6)))       # cheaper installs: faster → good
    a = alerts(row, "pay_slow")
    assert len(a) == 1 and a[0]["dir"] == "up" and a[0]["severity"] == "good"


def test_pay_slow_warning_when_crosses_H():
    m = app(cpi_jump=(date(2026, 8, 24), 1.6))
    _, row, _ = ev(m)
    assert alerts(row, "pay_slow")[0]["severity"] == "warning"       # ~46 → ~110 days, the target is 90
    _, row, _ = ev(m, cfg={"payback_days": 180})
    assert alerts(row, "pay_slow")[0]["severity"] == "watch"


def test_pay_loss_state_open_and_close_info():
    kw = dict(cpi_jump=(date(2026, 8, 24), 2.5, date(2026, 9, 7)))
    det, row, st = ev(app(**kw))
    a = alerts(row, "pay_loss")
    assert len(a) == 1 and a[0]["severity"] == "watch" and "90 din me money back nahi karte" in a[0]["text"]
    later = app(end=END + timedelta(days=14), **kw)
    det2, row2, st2 = ev(later, st=st, now="2026-10-05T12:00:00Z")
    assert not alerts(row2, "pay_loss")
    assert [e["family"] for e in st2["closed"]] == ["pay_loss"] or "pay_loss" in [e["family"] for e in st2["closed"]]
    assert any(i["kind"] == "closed" and i["text"].startswith("✅ ab money back in ~") for i in det2["changes"]["info"])
    big = app(cpi_jump=(date(2026, 8, 24), 5.0))
    _, rb, _ = ev(big)
    assert alerts(rb, "pay_loss")[0]["severity"] == "warning"          # even the good band misses, big spend


def test_one_pay_notify_per_week():
    m = app(cpi_jump=(date(2026, 8, 24), 1.8))
    st = {"eval": {"end_week": (E - timedelta(days=7)).isoformat(), "src": ["p1", "s1"], "iday_v": 1,
                   "inputs": dict.fromkeys(("iday", "cty", "spend", "k"), "2026-01-04"), "streak": {}},
          "episodes": {}, "closed": []}
    _, row, _ = ev(m, st=st)
    pay = [a for a in row["_alerts"] if a["family"] in ("pay_slow", "pay_loss")]
    assert len(pay) == 2 and sum(a["notify"] for a in pay) == 1


def test_geo_move_not_app_wide():
    _, row, _ = ev(app(drop=("NG", date(2026, 8, 31), 0.6)))
    a = alerts(row, "geo_move")
    assert [(x["cc"], x["metric"], x["dir"]) for x in a] == [("NG", "d1", "down")]
    assert a[0]["now"] < a[0]["before"] and "Nigeria me back next day kam: 17%, pehle 28%" in a[0]["message"]
    assert set(a[0]["also"]) <= {"d7", "d30", "rpi7"}
    _, row, _ = ev(app(drop=("*", date(2026, 8, 31), 0.6)))          # every country: the app moved, not NG
    assert not alerts(row, "geo_move")


def test_geo_move_needs_clean_weeks():
    gaps = tuple(date(2026, 8, 10) + timedelta(days=i) for i in range(3))   # one base week not fully split
    _, row, _ = ev(app(drop=("NG", date(2026, 8, 31), 0.6), gap_days=gaps))
    assert not alerts(row, "geo_move")


def test_geo_move_suppressed_by_act_return():
    drops = (("IN", date(2026, 8, 31), 0.6),) + tuple((c, date(2026, 8, 31), 0.85) for c in ("US", "BR", "NG", "ID",
                                                                                              "DE", "--", "ZZ"))
    m = app(drop=drops)
    _, row, _ = ev(m)
    assert [a["cc"] for a in alerts(row, "geo_move") if a["metric"] == "d1"] == ["IN"]
    act = [{"family": "act_return", "metric": "d1", "dir": "down"}]
    _, row, _ = ev(m, act_alerts=act)
    assert not [a for a in alerts(row, "geo_move") if a["cc"] == "IN" and a["metric"] == "d1"]
    _, row, _ = ev(app(drop=("NG", date(2026, 8, 31), 0.6)), act_alerts=act)   # NG alone: far bigger than the app
    assert [a["cc"] for a in alerts(row, "geo_move")] == ["NG"]
    tags = alerts(ev(app(cpi_jump=(date(2026, 8, 24), 1.6)), act_alerts=act)[1], "pay_slow")[0]["tags"]
    assert "return" in tags


def test_geo_cost_only_with_geo():
    m = app()
    _, row, _ = ev(m)
    assert not alerts(row, "geo_cost")
    det, _, _ = ev(m)
    n = {r["cc"]: r["n"] for r in det["countries"]["rows"]}
    geo = {"NG": {"cost": 0.2 * n["NG"], "dl": n["NG"]}, "US": {"cost": 0.05 * n["US"], "dl": n["US"]}}
    _, row, _ = ev(m, geo=geo)
    a = alerts(row, "geo_cost")
    assert [x["cc"] for x in a] == ["NG"] and "Nigeria me ads mehenge" in a[0]["message"]


def test_iv_link_watch_only():
    _, row, _ = ev(app(k_from=date(2026, 8, 31), k=1.0, k_after=2.0))
    a = alerts(row, "iv_link")
    assert len(a) == 1 and a[0]["severity"] == "watch" and "Firebase–AdMob link check karo" in a[0]["text"]
    _, row, _ = ev(app())
    assert not alerts(row, "iv_link")


# ── seeding, burn-in, hourly re-runs (§2.7) ────────────────────────────────────────────────────

def test_first_eval_seeded():
    det, row, st = ev(app(cpi_jump=(date(2026, 8, 24), 1.6), drop=("NG", date(2026, 8, 31), 0.6)))
    assert len(row["_alerts"]) >= 2 and not any(a["notify"] for a in row["_alerts"])
    assert all(e["seeded"] and e["notified_at"] == NOW for e in st["episodes"].values())
    assert st["eval"]["end_week"] == E.isoformat() and st["eval"]["src"] == ["p1", "s1"]


def _state(inputs):
    return {"eval": {"end_week": (E - timedelta(days=7)).isoformat(), "src": ["p1", "s1"], "iday_v": 1,
                     "inputs": inputs, "streak": {}}, "episodes": {}, "closed": []}


def test_new_input_burnin():
    m = app(cpi_jump=(date(2026, 8, 24), 1.6), drop=("NG", date(2026, 8, 31), 0.6))
    old = "2026-06-07"
    _, row, _ = ev(m, st=_state({"iday": old, "cty": old, "spend": old, "geo": None, "k": old}))
    got = {a["family"]: a["notify"] for a in row["_alerts"]}
    assert got["pay_slow"] and got["geo_move"]                          # everything long seen: sent
    recent = (E - timedelta(days=14)).isoformat()
    _, row, _ = ev(m, st=_state({"iday": old, "cty": recent, "spend": old, "geo": None, "k": old}))
    got = {a["family"]: a["notify"] for a in row["_alerts"]}
    assert got["pay_slow"] and not got["geo_move"]                      # countries 2 weeks old: shown, not sent
    _, row, _ = ev(m, st=_state({"iday": old, "cty": old, "spend": recent, "geo": None, "k": old}))
    got = {a["family"]: a["notify"] for a in row["_alerts"]}
    assert not got["pay_slow"] and got["geo_move"]
    _, _, st = ev(m, st=_state({"iday": None, "cty": None, "spend": None, "geo": None, "k": None}))
    assert st["eval"]["inputs"]["cty"] == E.isoformat() and st["eval"]["inputs"]["spend"] == E.isoformat()


def test_src_change_reseeds():
    m = app(drop=("NG", date(2026, 8, 31), 0.6))
    _, _, st = ev(m)
    st["eval"]["src"] = ["p-old", "s-old"]
    st["eval"]["end_week"] = (E - timedelta(days=7)).isoformat()
    st["closed"] = [dict(next(iter(st["episodes"].values())), closed="2026-01-04")]
    for e in st["episodes"].values():
        e["seeded"], e["notified_at"] = False, "2026-01-01T00:00:00Z"
    _, row, st2 = ev(m, st=st)
    assert st2["closed"] == [] and all(e["seeded"] and e["notified_at"] == NOW for e in st2["episodes"].values())
    assert not any(a["notify"] for a in row["_alerts"]) and st2["eval"]["src"] == ["p1", "s1"]


def test_hourly_rerun_same_week_no_state_change():
    m = app(cpi_jump=(date(2026, 8, 24), 1.6))
    d1, r1, st1 = ev(m)
    d2, r2, st2 = ev(m, st=copy.deepcopy(st1), now="2026-09-21T13:00:00Z")
    assert st2 == st1 and d2 == d1
    r1.pop("_shape"), r2.pop("_shape")
    assert r1 == r2


# ── IAP, texts ───────────────────────────────────────────────────────────────────────────────

def test_iap_never_in_money_back():
    with_iap, _, _ = ev(app(iap=0.2))
    without, _, _ = ev(app())
    for a, b in zip(with_iap["weeks"], without["weeks"]):
        assert a["L"] == b["L"] and a["pay"] == b["pay"]
    assert with_iap["weeks"][-1]["iap"] is not None and without["weeks"][-1]["iap"] is None
    assert with_iap["weeks"][-1]["iap"][5] == pytest.approx(0.2 * with_iap["weeks"][-1]["rpi"][5], rel=1e-3)


BANNED = re.compile(r"cohort|checkpoint|cumulative|bharosa|headline|\bLTV\b", re.I)
DEVANAGARI = re.compile("[ऀ-ॿ]")


def _texts(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("text", "message") and isinstance(v, str):
                yield v
            else:
                yield from _texts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _texts(v)


def test_texts_hinglish_no_banned_words():
    got = []
    for kw in (dict(cpi_jump=(date(2026, 8, 24), 1.6), drop=("NG", date(2026, 8, 31), 0.6)),
               dict(spend=False, smp=True), dict(start=END - timedelta(days=69), filling=30),
               dict(cpi=0.5), dict(k_from=date(2026, 8, 31), k_after=2.0),
               dict(countries=SMALL, gap_days=tuple(S - timedelta(days=3 + i) for i in range(12)))):
        det, row, _ = ev(app(**kw))
        got += list(_texts(det)) + list(_texts(row))
    assert len(got) > 40
    for t in got:
        assert t and not BANNED.search(t) and not DEVANAGARI.search(t), t
        assert "None" not in t and "nan" not in t.lower().split(), t


def test_no_date_literal_in_value_py():
    src = open(os.path.join(os.path.dirname(V.__file__), "value.py"), encoding="utf-8").read()
    assert not re.search(r"\b(19|20)\d\d-\d\d-\d\d\b", src)
    assert not re.search(r"\b\d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", src)


def test_release_tags_the_money_back_alert_and_marks_its_week():
    rel = [{"date": "2026-08-26", "version": "3.1", "kind": "version", "key": "blk-1"},
           {"date": "2025-01-05", "version": "1.0", "kind": "version", "key": None}]
    det, row, _ = ev(app(cpi_jump=(date(2026, 8, 24), 1.6)), releases=rel)
    a = alerts(row, "pay_slow")[0]
    assert "update" in a["tags"] and a["release"] == {"date": "2026-08-26", "version": "3.1", "kind": "version",
                                                       "key": "blk-1"}
    assert a["text"].endswith(" · v3.1 ke baad")
    w = weeks_by_from(det)["2026-08-24"]
    assert w["release"]["key"] == "blk-1" and weeks_by_from(det)["2026-08-31"]["release"] is None


def test_settled_line_is_the_newest_folded_day():
    """The fetch's `to` is its cursor (the newest day in its ledger — a read that failed or came back short included);
    the tab's "data till" is the newest day actually folded, and a file with no folded day is a waiting row."""
    m = app()
    days = m["ida"]["days"]
    for i in range(2):                                    # the two newest reads failed / came back short
        days[(S - timedelta(days=i)).isoformat()].update(st=("err", "retry")[i])
    det, row, _ = ev(m)
    assert m["ida"]["to"] == S.isoformat() and det["settled_till"] == (S - timedelta(days=2)).isoformat()
    assert row["settled_till"] == det["settled_till"] and det["iday"]["to"] == S.isoformat()
    for w in det["weeks"]:                                # nothing that needs the unread days is complete
        last = date.fromisoformat(w["to"])
        assert all(w["L"][j] is None for j, t in enumerate(V.T) if last + timedelta(days=t) > S - timedelta(days=2))
    for e in days.values():
        e["st"] = "err"
    det, row, _ = ev(m)
    assert det is None and row["status"] == "wait" and row["file"] is None and row["summary"]["kind"] == "wait"


# ── review fixes: the money truth, the spend truth, honest ranges and verdicts, no false alerts ─────────────────────

OLD = "2026-01-04"


def _seen():
    """A state whose inputs were all seen long ago: a condition that opens now is SENT unless something holds it."""
    return _state({"iday": OLD, "cty": OLD, "spend": OLD, "geo": None, "k": OLD})


def sent(row, fams=("pay_slow", "pay_loss")):
    return [a for a in row["_alerts"] if a["family"] in fams and a["notify"]]


def test_ga4_side_step_mid_month_sends_no_money_back_alert():
    """GA4's ad revenue × 0.3 from a Tuesday mid-month (a Firebase link / consent / SDK change), AdMob — the money —
    unchanged: k is per activity WEEK (the weeks before the step keep their true value; a step inside the clamp is fully
    corrected) and a money-back condition standing on an out-of-range k is shown, never sent, never red, ≈."""
    ctl, _, _ = ev(app(), st=_seen())
    c = weeks_by_from(ctl)
    det, row, _ = ev(app(ga4_drop=(date(2026, 8, 18), 0.3)), st=_seen())
    w = weeks_by_from(det)
    assert w["2026-08-03"]["rpi"][3] == pytest.approx(c["2026-08-03"]["rpi"][3], rel=0.01)   # the week before: true
    assert not sent(row)
    pay = alerts(row, "pay_slow") + alerts(row, "pay_loss")
    assert pay and all(a["severity"] != "warning" and a["estimate"] for a in pay)
    assert [a["family"] for a in alerts(row) if a["notify"]] == ["iv_link"]              # the right alert: the link
    mild, row7, _ = ev(app(ga4_drop=(date(2026, 8, 20), 0.7)), st=_seen())             # inside the clamp
    m = weeks_by_from(mild)
    for wk in ("2026-08-03", "2026-08-24", "2026-08-31"):
        assert m[wk]["rpi"][3] == pytest.approx(c[wk]["rpi"][3], rel=0.01), wk
    assert not alerts(row7, "pay_slow") and not alerts(row7, "pay_loss")


def test_admob_rows_stopping_never_read_as_zero():
    """An app's AdMob report stops mid-month (its account's fetch stalled; the revenue's `till` is still yesterday):
    those days are unknown, not $0 — k, earning per install and money back do not move, and the Data check says it."""
    m = app()
    cut = "2026-08-12"
    for k in ("all_days", "days"):
        m["rev"][k] = {d: v for d, v in m["rev"][k].items() if d <= cut}
    ctl, crow, _ = ev(app(), st=_seen())
    det, row, _ = ev(m, st=_seen())
    c, w = weeks_by_from(ctl), weeks_by_from(det)
    for wk in ("2026-07-06", "2026-08-10", "2026-08-31"):
        assert w[wk]["rpi"][3] == pytest.approx(c[wk]["rpi"][3], rel=0.005), wk
    assert row["pay"]["p"] == crow["pay"]["p"] and not row["_alerts"]
    assert det["scale"]["text"][0].startswith("⚠️ AdMob revenue 13 Aug se nahi aayi")
    assert det["scale"]["weeks"][-1]["admob"] is None and det["scale"]["weeks"][-1]["r"] is None


def test_stale_spend_cache_never_judges_a_partial_week():
    """Google Ads spend fetched only till 12 days before the settled line — a Friday: the fetch failing since, the
    cache kept): the week reaching past that day is unknown — never judged on its partial spend, never "No ads"."""
    m = app()
    till = (S - timedelta(days=12)).isoformat()
    assert date.fromisoformat(till).weekday() == 4
    for k in ("daily", "installs"):
        m["spend"][k] = {d: v for d, v in m["spend"][k].items() if d <= till}
    m["spend"]["till"] = till
    det, row, _ = ev(m, st=_seen())
    for w in det["weeks"]:
        if w["to"] > till:
            assert w["spend"] is None and w["ecpi"] is None and not w["judged"] and w["why"] == "wait", w["from"]
        elif w["judged"]:
            assert w["ecpi"] == pytest.approx(0.06, rel=2e-3)
    assert row["pay"]["to"] <= till and not sent(row)
    assert any(w["from"] <= till < w["to"] for w in det["weeks"])                      # a straddling week existed


def test_portfolio_projection_band_holds_the_slowest_app_and_never_alerts():
    """A young app (10 weeks) takes the portfolio's curve; its own is the portfolio's SLOWEST. The band spans how the
    apps differ from each other, so its true payback (seen a year later) lies inside; it reads "kaafi kaccha" and
    opens no money-back alert."""
    _, own_row, _ = ev(app(seed=7))
    own = own_row["_shape"]
    port = V.portfolio_shape([own] + [{k: [v[0] * f, v[1] * f, v[2] * f] for k, v in own.items()} for f in (1.4, 1.9, 2.6)])
    assert port["7→90"][1] <= own["7→90"][1] and port["7→90"][2] >= 2.6 * own["7→90"][2] * 0.999
    young = END - timedelta(days=10 * 7 - 1)
    det, row, _ = ev(app(seed=7, start=young, cpi=0.1), portfolio=port, st=_seen())
    w = next(x for x in det["weeks"] if x["pay"] and x["shape"] == "portfolio")
    later, _, _ = ev(app(seed=7, start=young, cpi=0.1, end=END + timedelta(days=400)), portfolio=port)
    truth = weeks_by_from(later)[w["from"]]["pay"]
    assert truth["obs"] and w["pay"]["lo"] <= truth["p"] <= (w["pay"]["hi"] or 366)
    assert w["pay"]["rough"] and "dusre apps ke hisaab se" in V.p_phrase(w["pay"])
    assert not alerts(row, "pay_slow") and not alerts(row, "pay_loss")


def test_null_countries_get_no_false_top_low_or_best_weakest():
    """12 countries with the SAME true value per install, noisy revenue (lognormal, sd 4/√installs a day): two weekly
    evaluations on 4 seeds — Top / Low verdicts stay rare (t-quantile, the rest's own SE, Bonferroni) and nothing is
    named Best / Weakest."""
    names = ["US", "IN", "BR", "NG", "ID", "DE", "PK", "BD", "PH", "VN", "TH", "MX"]
    shares = [0.20, 0.15, 0.12, 0.10, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01]
    cty = dict({c: (s, 1.0, 0.008) for c, s in zip(names, shares)}, **{"--": (0.02, 1.0, 0.008), "ZZ": (0.05, 1.0, 0.008)})
    judged = false = named = 0
    for seed in (1, 2, 3, 4):
        st = None
        for e in (END - timedelta(days=7), END):
            m = app(countries=cty, base=3000, cnoise=4.0, seed=seed, end=e)
            d, r, st = V.evaluate_app(m["store"], m["ida"], m["rev"], m["spend"], m["fx"], [], st, {}, CFG,
                                      (e + timedelta(days=2)).isoformat() + "T12:00:00Z", app_id=AID, app="A", key="k")
            for x in d["countries"]["rows"]:
                judged += x["verdict"] in ("top", "low", "avg")
                false += x["verdict"] in ("top", "low")
            named += bool(d["countries"]["best"] or d["countries"]["weak"])
    assert judged >= 60 and false <= 0.03 * judged and named == 0


def test_country_noise_is_the_same_whatever_the_hash_seed():
    """The null-countries test above draws its per-country noise from a seed: it must be the SAME noise on every run.
    (It was keyed by Python's hash() of a str, salted per process — PYTHONHASHSEED=24 drew a sample that named a Best
    country and failed the test.) Two interpreters with different hash seeds → identical install-day revenue."""
    import subprocess
    import sys
    code = ("import hashlib, json; from tests import value_synth as vs; from tests.test_value_engine import app; "
            "m = app(countries={'US': (0.6, 1.0, 0.008), 'IN': (0.4, 1.0, 0.008)}, base=3000, cnoise=4.0, seed=2); "
            "print(hashlib.sha1(json.dumps(m['ida'], sort_keys=True, default=str).encode()).hexdigest())")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    got = {subprocess.run([sys.executable, "-c", code], cwd=root, check=True, capture_output=True, text=True,
                          env=dict(os.environ, PYTHONHASHSEED=s)).stdout.strip() for s in ("1", "24")}
    assert len(got) == 1 and len(next(iter(got))) == 40, got


def test_country_verdict_gated_on_the_installs_its_value_comes_from():
    """Kenya at 0.1% of installs, then a campaign (×130 from 20 Aug): the D1 window holds thousands, but the older weeks
    its 30-day value comes from hold a few hundred at most — "few", with THAT count; never a verdict or a break-even."""
    det, row, _ = ev(app(countries=SMALL, cty_share=("KE", date(2026, 8, 20), 130.0)))
    ke = next(x for x in det["countries"]["rows"] if x["cc"] == "KE")
    assert ke["n"] >= V.CTY_JUDGE > ke["n_val"] and ke["verdict"] == "few" and ke["rank"] is None
    assert "sirf %s installs" % "{:,}".format(ke["n_val"]) in ke["text"] and "sasta mile" not in ke["text"]
    assert "KE" not in row["cty"]["best"] + row["cty"]["weak"]


def test_country_without_an_interval_waits_never_average():
    """Too few settled weeks for the rest-of-app comparison (5 weeks of history): "Wait", not judged, not "Average"."""
    det, row, _ = ev(app(start=END - timedelta(days=5 * 7 - 1)))
    rows = det["countries"]["rows"]
    assert rows and all(r["verdict"] in ("wait", "few") for r in rows)
    assert row["cty"]["judged"] == 0 and not det["tiles"]["cty"]["all_avg"] and det["tiles"]["cty"]["st"] == "low"


def test_market_wide_ad_rate_move_is_shown_not_sent():
    """Every app's ad rate (eCPM) fell the same weeks (Active's market prepass): an app's money-back move whose only
    cause is the earning per install is seeded (never sent, never red) with a Market tag and one info row."""
    m = app(drop=("*", date(2026, 8, 24), 0.6))
    _, row, _ = ev(m, st=_seen())
    assert [(a["family"], a["notify"]) for a in alerts(row, "pay_slow")] == [("pay_slow", True)]       # an app's own
    mk = {"weeks": [{"from": "2026-08-24", "to": "2026-08-30", "dir": "down", "share": 0.9, "apps": 20, "of": 18}]}
    det, row, _ = ev(m, st=_seen(), market=mk)
    a = alerts(row, "pay_slow")
    assert a and not a[0]["notify"] and a[0]["severity"] == "watch" and "market_wide" in a[0]["tags"]
    assert [i for i in det["changes"]["info"] if i["kind"] == "market"] and not sent(row)
    _, row, _ = ev(app(cpi_jump=(date(2026, 8, 24), 1.6)), st=_seen(), market=mk)                    # the cost: sent
    assert [x["notify"] for x in alerts(row, "pay_slow")] == [True]


def test_organic_surge_leads_with_the_mix_and_is_not_sent():
    """Installs × 3 for two weeks with the same Google Ads spend and ads installs: faster money back per ₹100 comes
    from organic installs, not the ads — the cause is the mix (never "install sasta") and the good news is not sent."""
    _, row, _ = ev(app(organic=(date(2026, 8, 24), date(2026, 9, 6), 3.0)), st=_seen())
    a = alerts(row, "pay_slow")
    assert len(a) == 1 and a[0]["dir"] == "up" and a[0]["tags"][0] == "mix" and "cpi" not in a[0]["tags"]
    assert not a[0]["notify"] and "ads wale installs 87% → 29%" in a[0]["message"]
    _, row, _ = ev(app(cpi_jump=(date(2026, 8, 24), 1 / 1.6)), st=_seen())                # truly cheaper ads: sent
    assert [(x["tags"][0], x["notify"]) for x in alerts(row, "pay_slow")] == [("cpi", True)]


def test_geo_cost_is_summed_over_the_installs_own_weeks():
    """Country cost per day over 120 days, true cost per install $0.05: a small app's 12-week country window divides
    12 weeks of cost by 12 weeks of installs (never 28 days of cost)."""
    m = app(base=60, spend=False)
    daily = {}
    for i in range(120):
        d = S - timedelta(days=i)
        n = m["new"][d] * vs.CTY["IN"][0]
        daily[d.isoformat()] = [0.05 * n, 0.87 * n]
    det, row, _ = ev(m, geo={"IN": {"daily": daily}})
    assert det["countries"]["win"]["size"] == V.WIN_WEEKS_SMALL
    r = next(x for x in det["countries"]["rows"] if x["cc"] == "IN")
    assert r["cpi"]["v"] == pytest.approx(0.05, rel=0.01)


def _cond(fam, cc=None, dr="down"):
    return {"key": "a|%s|%s|%s" % (fam, cc, dr), "family": fam, "metric": "pay" if fam == "pay_loss" else "d1",
            "dir": dr, "cc": cc, "severity": "watch", "seed": False, "week_from": "2026-01-05", "week_to": "2026-01-18"}


def test_a_reopen_soon_after_its_close_is_not_sent_again():
    """pay_loss that closes after one clean week and opens again within 91 days, and geo_move (same country and
    direction) within 42 days: shown, never sent again; later than that, a new episode that is sent."""
    for fam, cc, keep in (("pay_loss", None, V.REOPEN_SEED_DAYS["pay_loss"]), ("geo_move", "NG", V.REOPEN_SEED_DAYS["geo_move"])):
        st = V.empty_state()
        e0 = date(2026, 1, 4)
        st, _ = V.episodes(st, AID, e0, [_cond(fam, cc)], True, "2026-01-05T00:00:00Z")
        ep = next(iter(st["episodes"].values()))
        assert ep["notified_at"] is None
        ep["notified_at"] = "2026-01-05T01:00:00Z"
        for i in range(1, 3):                              # misses until it closes
            st, _ = V.episodes(st, AID, e0 + timedelta(days=7 * i), [], True, "2026-01-06T00:00:00Z")
        assert not st["episodes"] and st["closed"]
        closed_at = V._d(st["closed"][-1]["closed"])
        soon, _ = V.episodes(st, AID, closed_at + timedelta(days=keep - 7), [_cond(fam, cc)], True, "2026-03-01T00:00:00Z")
        assert all(e["seeded"] for e in soon["episodes"].values()), fam
        late, _ = V.episodes(st, AID, closed_at + timedelta(days=keep + 7), [_cond(fam, cc)], True, "2026-06-01T00:00:00Z")
        assert all(e["notified_at"] is None for e in late["episodes"].values()), fam


def test_stopped_ads_are_not_this_week():
    """Google Ads stopped 30 weeks ago on an app that lost money: no money-back alert, no "this week" and no weekly
    spend from its old ads weeks — "No ads", with when it stopped and what its last ads weeks did."""
    det, row, _ = ev(app(spend_stop=END - timedelta(days=210), cpi=0.5), st=_seen())
    assert not alerts(row, "pay_loss") and not alerts(row, "pay_slow")
    t = det["tiles"]["pay"]
    assert t["st"] == "nospend" and "se Google Ads spend nahi" in t["note"] and "aakhri ads hafte" in t["note"]
    assert row["pay"]["st"] == "nospend" and row["pay"]["p"] is None and det["summary"]["kind"] == "nospend"
    assert row["s"]["spend4"] == 0 and row["s"]["rev7_4"] is None and det["tiles"]["cpi"]["st"] == "nospend"
    assert "Is hafte" not in det["summary"]["text"]
    det2, row2, _ = ev(app(spend_stop=END - timedelta(days=70)))
    assert det2["summary"]["kind"] == "nospend" and det2["summary"]["text"].startswith("ℹ️ 13 Jul se Google Ads spend nahi")


def test_a_week_that_never_pays_back_is_never_normal():
    """The newest week with 7 days of earnings costs ×20: its summary is 💸 (a year brings back only ≈x%), never
    "✅ … normal jaisa"; the cost tile says "maybe higher" from that one week, before any alert."""
    det, row, _ = ev(app(cpi_jump=(date(2026, 8, 31), 20.0)), st=_seen())
    assert det["summary"]["kind"] == "never" and det["summary"]["text"].startswith("💸 ") and "normal" not in det["summary"]["text"]
    assert det["tiles"]["pay"]["st"] == "never" and det["tiles"]["cpi"]["st"] == "maybe_dn"
    ok, _, _ = ev(app(), st=_seen())
    assert ok["summary"]["kind"] == "ok" and "normal jaisa" in ok["summary"]["text"]


def test_one_money_back_figure_per_span():
    """pay_slow and pay_loss name the same two weeks with the same figure and range (the median of the two weeks'); the
    tile names its own week."""
    _, row, _ = ev(app(cpi_jump=(date(2026, 8, 24), 2.5)), st=_seen())
    ps, pl = alerts(row, "pay_slow")[0], alerts(row, "pay_loss")[0]
    assert (ps["week_from"], ps["week_to"]) == (pl["week_from"], pl["week_to"])
    assert ps["p"] == pl["p"] and "~%d din" % ps["p"] in ps["text"] and "~%d din me" % pl["p"] in pl["text"]
    assert row["pay"]["from"] == "2026-08-31" and row["pay"]["to"] == pl["week_to"]


def test_four_weeks_are_the_last_four_calendar_weeks_everywhere():
    """The cost tile, the All-apps row and the pooled tiles use ONE window: the last 4 settled calendar weeks (thin or
    zero weeks counted as what they spent), and the weekly context divides by the weeks it has."""
    det, row, _ = ev(app())
    ws = sorted((w for w in det["weeks"] if w["spend"] is not None), key=lambda w: w["from"])[-4:]
    c = det["tiles"]["cpi"]
    assert c["spend4"] == pytest.approx(sum(w["spend"] for w in ws), rel=1e-5) == row["s"]["spend4"]
    assert c["n4"] == sum(w["n"] for w in ws) == row["s"]["n4"] and c["nw"] == 4 == row["s"]["nw"]
    assert (c["from"], c["to"]) == (ws[0]["from"], ws[-1]["to"])
    assert row["pay"]["b7"] == pytest.approx(100 * row["s"]["rev7_4"] / row["s"]["spend7_4"], rel=1e-3)
    assert c["spend4_src"] == pytest.approx(sum(w["spend_src"] for w in ws), rel=1e-5)


def test_spend_in_the_currency_it_billed_next_to_usd():
    """Each week's spend in INR (what Google Ads billed) next to its USD at that week's rate; the page shows the INR in
    the ₹ view — never USD turned back at today's rate."""
    m = app()
    det, _, _ = ev(m)
    assert det["fx"]["src"] == "INR"
    w = det["weeks"][5]
    raw = sum(v for d, v in m["spend"]["daily"].items() if w["from"] <= d <= w["to"]) / 1e6
    assert w["spend_src"] == pytest.approx(raw, rel=1e-5) and w["ecpi_src"] == pytest.approx(raw / w["n"], rel=1e-5)


def test_sentences_carry_money_and_countries_as_tokens():
    """The page draws money in the viewer's currency and countries with its own names: the engine's texts carry tokens;
    the Telegram / email message is written out (USD)."""
    t = "install {q:0.06|5.07} → {q:0.096|8.12}, kamai {m:0.0042}, {cc:NG} me, {c}100 pe {p:0.04} — kharcha {s:1335.2|111000}"
    assert V.render_text(t) == ("install $0.060 → $0.096, kamai $0.0042, Nigeria me, $100 pe $0.04 — kharcha $1,335")
    assert V.render_text(t, "INR", 83.0, "INR").endswith("kharcha ₹111,000") and "₹5.07" in V.render_text(t, "INR", 83.0, "INR")
    _, row, _ = ev(app(cpi_jump=(date(2026, 8, 24), 1.6)))
    a = alerts(row, "pay_slow")[0]
    assert "{q:" in a["text"] and "{" not in a["message"] and a["data_till"] == S.isoformat()


def test_best_and_weakest_words_fit_several_countries():
    """Several countries can be among the best: "sabse zyada kamai walon me" / "kam kamai walon me" — never "the most"
    for two at once; the name is a token the page draws (its own English names)."""
    m = app()
    _, _, st0 = ev(m)
    st0["eval"]["end_week"] = (E - timedelta(days=7)).isoformat()
    det, _, _ = ev(m, st=st0)
    c = det["countries"]
    for r in c["rows"]:
        if r["cc"] in c["best"]:
            assert r["text"].endswith(" — sabse zyada kamai walon me") and r["text"].startswith("{cc:%s}" % r["cc"])
        elif r["cc"] in c["weak"]:
            assert r["text"].endswith(" — kam kamai walon me")
    assert c["best"] and c["weak"]
    assert not any("sabse zyada kamai wala country" in r["text"] or "kamai sabse kam" in r["text"] for r in c["rows"])


def test_a_week_projected_from_other_apps_curves_never_promises_an_alert():
    # the pay alerts never judge a week whose money back comes from the other apps' curves (_conditions): its summary
    # line says whose andaza it is and promises no alert; the app's own projection still does. ">365" never shows.
    wk_from, wk_to = (E - timedelta(days=6)).isoformat(), E.isoformat()
    for st, extra in (("never", {"never": True}), ("maybe_dn", {})):
        for shape, own in (("portfolio", False), (None, True)):
            pt = dict({"from": wk_from, "to": wk_to, "base": 400, "pct365": 62, "lo": 40, "hi": 90, "obs": False,
                       "rough": False, "v": 120, "st": st, "shape": shape}, **extra)
            s = V._summary({"pay": pt, "ads": "on"}, [], [1], {}, "whole", 100, 0, E, S)
            assert ("2 hafte aisa raha to alert" in s["text"]) is own, s
            assert ">365" not in s["text"] and "pehle saal bhar me bhi nahi" in s["text"], s
            assert ("dusre apps ke hisaab se" in s["text"]) is (not own), s
