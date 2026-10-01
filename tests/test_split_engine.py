"""The installs vs per-user split of every change (admob_iq.engine.attrib, SPEC_SPLIT): "installs ki wajah se" vs "asli
badlaav". On synthetic truth only: the formulas of every basis (exact additivity, the shown integers adding up as
printed, float dust, a base ≤ 0, the status copied from the host's verdict), each engine's split against a known
installs change and a known per-user change, the invariance (every verdict, alert, number and state identical with the
split off and on, once the "sp" keys are taken out), failure isolation and the Telegram tail. All data is made up."""

import copy
import json
import math
import random
import re
from datetime import date, timedelta

import pytest

from admob_iq import build_static
from admob_iq.engine import active as act
from admob_iq.engine import attrib
from admob_iq.engine import impact as imp
from admob_iq.engine import uninstall as eng
from admob_iq.engine import value as val
from tests import uninstall_synth as synth
from tests import value_synth as vs
from tests.uninstall_synth import END, Truth, make_active_store, make_impact_store, rollout, truth_store

NOW = "2026-09-21T01:00:00Z"
KEY = "0123456789ab"


@pytest.fixture(autouse=True)
def _on():
    """Every test starts with the split on and no failure counted (the builds set both)."""
    attrib.ON, attrib.FAILS = True, 0
    yield
    attrib.ON, attrib.FAILS = True, 0


def no_sp(o):
    """o without any "sp" key, recursively (the invariance: that is the only thing the split adds)."""
    if isinstance(o, dict):
        return {k: no_sp(v) for k, v in o.items() if k != "sp"}
    if isinstance(o, (list, tuple)):
        return [no_sp(v) for v in o]
    return o


def dump(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False, default=str)


def adds_up(x):
    """Every invariant of an expanded split (§2.2)."""
    tot = x["total"]["after"] - x["total"]["before"]
    parts = x["from_installs"]["abs"] + (x["trend"]["abs"] if x["trend"] else 0.0) + x["per_user"]["abs"]
    assert math.isclose(parts, tot, rel_tol=1e-12, abs_tol=1e-9), (parts, tot)
    b = x["total"]["before"]
    for k in ("total", "from_installs", "per_user") + (("trend",) if x["trend"] else ()):
        assert math.isclose(x[k]["rel"], x[k]["abs"] / b, rel_tol=1e-12, abs_tol=1e-15)
    s = x["shown"]
    assert x["form"] in ("pct", "count") and (s["count"] is not None) == (x["form"] == "count")
    if s["count"]:                                                  # the count form adds up as printed too
        c, u = s["count"], 10.0 ** s["count"]["exp"]
        assert c["total"] == c["from_installs"] + (c["trend"] or 0) + c["per_user"]
        assert abs(c["total"] * u - tot) <= 0.5 * u + 1e-9 and abs(c["from_installs"] * u - x["from_installs"]["abs"]) <= 0.5 * u + 1e-9
    assert s["total"] == attrib.R(100 * x["total"]["rel"])
    assert s["from_installs"] == attrib.R(100 * x["from_installs"]["rel"])
    assert s["trend"] == (attrib.R(100 * x["trend"]["rel"]) if x["trend"] else None)
    assert s["per_user"] == s["total"] - s["from_installs"] - (s["trend"] or 0)       # adds up as printed
    assert abs(s["per_user"] - 100 * x["per_user"]["rel"]) <= 1.5 + 1e-9
    assert x["per_user"]["status"] in attrib.STATUS_WORDS + (None,)
    return x


# ── 1. the formulas, every basis ────────────────────────────────────────────────────────────────────

def test_a_rate_splits_into_the_installs_move_and_the_rate_move_exactly():
    # 100 → 150 installs a day, 30 → 25 of 100 come back: the installs' part is exactly their +50% at the old rate,
    # the rest is the rate on today's installs (150 × −0.05 = −7.5 a day)
    host = {"family": "act_return", "metric": "d1", "severity": "watch", "before": 0.30, "now": 0.25,
            "sp": attrib.rate("rr", 100, 150)}
    x = adds_up(attrib.expand("rate", host))
    assert x["code"] == "rr" and x["basis"] == "return_rate" and x["days"] == 1 and x["per"] == "day"
    assert x["form"] == "pct"                                       # −25% is exactly 1.5 × the rate's own −16.7%
    assert x["total"]["before"] == pytest.approx(30) and x["total"]["after"] == pytest.approx(37.5)
    assert x["from_installs"]["rel"] == pytest.approx(0.5, abs=1e-12)                 # = the installs' own +50%
    assert x["per_user"]["abs"] == pytest.approx(150 * (0.25 - 0.30))
    assert x["per_user"]["own"] == pytest.approx(0.25 / 0.30 - 1)
    assert x["on_now"] == {"installs": 150, "abs": pytest.approx(-7.5)}
    assert x["per100"]["before"] == pytest.approx(30) and x["per100"]["after"] == pytest.approx(25)
    assert x["installs"]["rel"] == pytest.approx(0.5) and x["per_user"]["status"] == "dhyan"
    assert x["shown"] == {"total": 25, "from_installs": 50, "trend": None, "per_user": -25, "count": None}
    assert attrib.line(x) == "daily returns: total +25% = from installs +50% + real −25%"


def test_every_basis_has_its_truth_and_adds_up():
    # returning users (Active tile): installs +50% at the same return per install → +2,000 recent-install returners a
    # day on a 40,000 level, old users +5% (40,000 = 36,000 old + 4,000 recent → 37,800 old + 6,000 recent = 43,800)
    t = {"st": "normal", "base": 40000, "v": 43800, "sp": attrib.ret(2000, 4000, 6000, 1000, 1500, 13.3, 13.3, 30, 0)}
    x = adds_up(attrib.expand("act_tile_ret", t, k=30))
    assert x["from_installs"]["rel"] == pytest.approx(0.05) and x["mode"] == "cohort" and not x["est"]
    assert x["per_user"]["own"] == pytest.approx(0.05)                               # the old users themselves
    assert x["shown"] == {"total": 10, "from_installs": 5, "trend": None, "per_user": 5, "count": None}
    assert x["per100"] == {"n": 100, "before": 13.3, "after": 13.3, "k": 30} and x["per_user"]["status"] == "normal"
    # … the same change as an alert, an info row (its before carried), the All-apps row (its sums)
    al = dict(t, severity="warning", before=40000, now=43800)
    assert attrib.expand("act_alert_ret", al)["shown"] == x["shown"]
    info = {"kind": "installs", "rel": 43800 / 40000 - 1, "sp": attrib.ret(2000, 4000, 6000, 1000, 1500, None, None,
                                                                             None, 1, before=40000)}
    xi = adds_up(attrib.expand("act_info_ret", info))
    assert xi["shown"] == x["shown"] and xi["per_user"]["status"] == "normal" and xi["est"] and xi["per100"] is None
    row = {"st": "normal", "s": [43800 * 7, 7, 40000 * 28, 28], "sp": t["sp"]}
    assert adds_up(attrib.expand("act_row_ret", row))["per_user"]["status"] is None     # a table cell: no verdict word
    # elastic mode: no own number (no old / recent split), always ≈
    xe = adds_up(attrib.expand("act_tile_ret", dict(t, sp=attrib.ret(2000, 0, 0, 1000, 1500, None, None, None, 3))))
    assert xe["mode"] == "elastic" and xe["est"] and xe["per_user"]["own"] is None
    # update impact: expected = before + installs + trend; the update's part = after − expected
    r = {"status": "worse", "before": 40000, "expected": 41600, "after": 39000, "sp": attrib.imp(1200, 400, 500, 800)}
    y = adds_up(attrib.expand("imp_dau", r))
    assert y["trend"]["abs"] == 400 and y["per_user"]["abs"] == pytest.approx(39000 - 41600)
    assert y["per_user"]["own"] == pytest.approx(39000 / 41600 - 1) and y["per_user"]["status"] == "bigda"
    assert attrib.line(y) == "old users, daily: total −3% = from installs +3% + trend +1% + update −7%"
    assert attrib.line(attrib.expand("imp_dau", dict(r, sp=attrib.imp(1200, 0)))) == \
        "old users, daily: total −3% = from installs +3% + update −6%"                    # no trend at 0%
    for st in ("low", "na", "pending"):
        assert attrib.expand("imp_dau", dict(r, status=st)) is None                   # nothing judged: no split
    # uninstall count: expected-by-installs (at the alert's calibration) ×1.25, actual ×1.52
    u = {"family": "rate_drift", "severity": "warning", "before": 4.0, "now": 6.0,
         "sp": attrib.uc(1200, 1824, 1200, 1500, 3000, 3750, 45)}
    z = adds_up(attrib.expand("uc", u))
    assert z["from_installs"]["rel"] == pytest.approx(0.25) and z["per_user"]["own"] == pytest.approx(1824 / 1500 - 1)
    assert z["per100"] == {"n": 100, "before": 45, "after": None, "k": 28} and z["per_user"]["status"] == "bigda"
    # revenue total: users −10%, revenue per 1,000 users +2%
    ar = {"st": "normal", "base": 2.0, "v": 2.04, "sp": attrib.rev(500, 450, [("new", 0.1, 0.2)])}
    w = adds_up(attrib.expand("rev", ar))
    assert w["from_installs"]["rel"] == pytest.approx(-0.1) and w["per_user"]["own"] == pytest.approx(0.02)
    assert w["installs"]["what"] == "users" and w["note"] == [["new", 10, 20]]
    assert attrib.line(w) == "daily revenue: total −8% = from users −10% + real +2%"
    # install value: installs / week × earning per install; ad spend: installs × cost per install
    q = adds_up(attrib.expand("ir", {"st": "normal", "base": 0.05, "v": 0.06, "sp": attrib.ir(1000, 800)}))
    assert q["per"] == "week" and q["from_installs"]["rel"] == pytest.approx(-0.2)
    c = adds_up(attrib.expand("spd", {"st": "maybe_dn", "sp": attrib.spd(1000, 1200, 0.05, 0.06)}))
    assert c["from_installs"]["rel"] == pytest.approx(0.2) and c["per_user"]["own"] == pytest.approx(0.2)
    # money back per 100: cost per install ₹10 → ₹12, value per install 5.00 → 4.80
    v = adds_up(attrib.expand("vpi", {"severity": "watch", "sp": attrib.vpi(5.0, 4.8, 10.0, 12.0)}))
    assert v["total"]["before"] == pytest.approx(50) and v["total"]["after"] == pytest.approx(40)
    assert v["from_installs"]["abs"] == pytest.approx(50 * (10 / 12 - 1)) and v["installs"]["what"] == "cost"
    assert attrib.line(v) == "money back: total −20% = from price −17% + from revenue −3%"
    # derived hosts (no sp): an impact new_dN row, the survival verdict
    ir_ = {"status": "same", "before": 0.3, "after": 0.3,
           "extra": {"installs_before": 7000, "cohorts_before": 7, "installs_after": 14000, "cohorts_after": 7}}
    d1 = adds_up(attrib.expand("imp_rate", ir_, days=1))
    assert d1["from_installs"]["rel"] == pytest.approx(1.0) and d1["per_user"]["abs"] == pytest.approx(0)
    ver = {"n": 7, "dir": "worse", "recent": {"users": 2800, "k": 28, "left": 0.6},
           "prev": {"users": 5600, "k": 28, "left": 0.7}}
    k = adds_up(attrib.expand("uni_verdict", ver))
    assert k["code"] == "uk" and k["days"] == 7 and k["per_user"]["status"] == "bigda"
    assert k["from_installs"]["rel"] == pytest.approx(-0.5)
    # notes only / none / no split
    assert attrib.expand("pu", {"st": "normal", "sp": attrib.pu([("new", 0.1, 0.25)])}) == \
        {"v": 1, "code": "pu", "basis": "per_user", "note": [["new", 10, 25]]}
    assert attrib.expand("act_tile_ret", dict(t, sp=["no", "cohorts"]))["none"] == "cohorts"
    assert attrib.expand("act_tile_ret", dict(t, sp=None)) is None
    assert attrib.line(attrib.expand("act_tile_ret", dict(t, sp=["no", "cohorts"]))) == ""


def test_the_uninstall_rate_hosts_read_the_rates_their_arrow_shows():
    sp = attrib.rate("ur", 3000, 1800)
    row = {"n": 1, "recent": {"p": 0.28, "users": 12600, "k": 7}, "prev": None,
           "all": {"p": 0.2, "users": 9000, "k": 3}, "sp": sp}                          # no 4-week base: all-time
    x = adds_up(attrib.expand("rate", row))
    assert x["total"]["before"] == pytest.approx(3000 * 0.2) and x["days"] == 1 and x["per_user"]["status"] is None
    cell = {"p": 0.28, "prev": 0.2, "sp": sp}
    assert attrib.expand("rate", cell, days=7)["days"] == 7
    alert = {"family": "cohort", "n": 0, "severity": "warning", "before": 0.2, "now": 0.28, "sp": sp}
    y = adds_up(attrib.expand("rate", alert))
    assert y["from_installs"]["rel"] == pytest.approx(-0.4) and y["per_user"]["rel"] > 0      # opposite ways
    assert y["per_user"]["status"] == "bigda" and y["days"] == 0
    geo = {"family": "geo_move", "metric": "d7", "severity": "watch", "before": 20.0, "now": 15.0,
           "sp": attrib.rate("rr", 100, 100)}                                          # geo rates are per 100
    assert attrib.expand("rate", geo)["per100"]["before"] == pytest.approx(20)
    d0 = {"status": "unsure", "before": 0.2, "after": 0.25, "sp": sp}
    assert attrib.expand("rate", d0, days=0)["per_user"]["status"] is None             # its own chip says "maybe"
    assert attrib.expand("rate", dict(d0, status="low")) is None
    # an Active d1 / d7 tile's n is its 7-day window, never the day after install: the caller says which day
    tile = {"sp": attrib.rate("rr", 500, 750), "s": [1470, 5250, 4200, 14000], "n": 7, "nb": 28, "st": "worse"}
    assert attrib.expand("act_tile_rr", tile)["days"] is None
    assert attrib.expand("act_tile_rr", tile, days=1)["days"] == 1


def test_the_shown_integers_add_up_on_ten_thousand_random_changes():
    rnd = random.Random(5)
    for _ in range(10000):
        ib = rnd.choice([rnd.uniform(1, 200), rnd.uniform(200, 50000)])
        ia = ib * math.exp(rnd.gauss(0, 0.6))
        rb = rnd.uniform(0.001, 0.9)
        ra = rnd.choice([rb, rb * math.exp(rnd.gauss(0, 0.3)), rb * ib / ia])      # flat / moved / masking the installs
        x = attrib.expand("rate", {"before": rb, "now": ra, "sp": ["ur", ib, ia]})
        adds_up(x)
        b = rnd.uniform(100, 1e6)
        fi = b * rnd.gauss(0, 0.2)
        tr = b * rnd.gauss(0, 0.05)
        y = attrib.expand("imp_dau", {"status": "same", "before": b, "after": b * math.exp(rnd.gauss(0, 0.3)),
                                      "expected": b + fi + tr, "sp": ["imp", fi, tr]})
        adds_up(y)


def test_float_dust_never_flips_a_shown_percent_and_a_base_of_zero_is_said():
    assert attrib.R(7.4999999999) == 8 and attrib.R(7.49) == 7 and attrib.R(100 * 0.075) == 8     # 7.4999999999 is 7.5
    assert attrib.R(-2.5) == -3 and attrib.R(0.4) == 0 and attrib.R(-0.4) == 0
    assert attrib.pct(8) == "+8%" and attrib.pct(-12) == "−12%" and attrib.pct(0) == "0%"
    x = attrib.expand("rate", {"before": 0.0, "now": 0.1, "sp": ["rr", 100, 120]})
    assert x == {"v": 1, "code": "rr", "basis": "return_rate", "none": "base"}
    assert attrib.expand("act_tile_ret", {"st": "normal", "base": 0, "v": 5,
                                          "sp": attrib.ret(1, 0, 0, 1, 1, None, None, None, 0)})["none"] == "base"


def test_the_status_word_is_the_hosts_verdict_copied():
    # a tile whose per-user part fell (returning users: the bad way) and one where it rose (the good way)
    down = {"sp": attrib.ret(10, 0, 0, 100, 120, None, None, None, 0), "base": 1000, "v": 900}
    up = dict(down, v=1100)
    want = {"worse": "bigda", "watch": "dhyan", "slow": "dhyan", "break": "dhyan", "better": "behtar",
            "normal": "normal", "maybe_dn": None, "maybe_up": None, "price_dn": "normal", "price_up": "normal",
            "growth": "jaldi", "low": "jaldi", "wait": "jaldi", "noad": "lagu_nahi"}
    for st, word in want.items():
        t = up if word == "behtar" else down
        assert attrib.expand("act_tile_ret", dict(t, st=st))["per_user"]["status"] == word, st
    for st, word in {"worse": "bigda", "never": "bigda", "watch": "dhyan", "better": "behtar", "normal": "normal",
                     "maybe": None, "low": "jaldi", "wait": "jaldi", "thin": "jaldi", "nospend": "lagu_nahi"}.items():
        v = 1.1 if word == "behtar" else 0.9
        assert attrib.expand("ir", {"st": st, "base": 1, "v": v, "sp": ["ir", 10, 10]})["per_user"]["status"] == word
    for sev, word in {"warning": "bigda", "watch": "dhyan", "good": "behtar"}.items():
        t = up if word == "behtar" else down
        assert attrib.expand("act_alert_ret", dict(t, severity=sev, before=1000, now=t["v"])
                             )["per_user"]["status"] == word
    for st, word in {"worse": "bigda", "better": "behtar", "same": "normal", "unsure": None, "market": "normal"}.items():
        r = {"status": st, "before": 1000, "after": 1100 if word == "behtar" else 1000, "expected": 1050,
             "sp": ["imp", 20, 30]}
        assert attrib.expand("imp_dau", r)["per_user"]["status"] == word, st
    assert attrib.expand("act_info_ret", {"rel": 0.1, "sp": attrib.ret(10, 0, 0, 100, 120, None, None, None, 0,
                                                                       before=1000)})["per_user"]["status"] == "normal"
    v = {"n": 7, "recent": {"users": 700, "k": 7, "left": 0.6}, "prev": {"users": 700, "k": 7, "left": 0.7}}
    assert [attrib.expand("uni_verdict", dict(v, dir=d))["per_user"]["status"] for d in ("worse", None)] == \
        ["bigda", "normal"]
    assert attrib.expand("uni_verdict", dict(v, dir="better", recent=dict(v["recent"], left=0.8))
                         )["per_user"]["status"] == "behtar"
    rn = {"last7": 5.0, "lo": 3.0, "hi": 4.0, "out_of_band": True, "sp": attrib.uc(100, 130, 80, 90, 10, 12, 45)}
    assert attrib.expand("uc", rn)["per_user"]["status"] == "dhyan"                          # above the band
    assert attrib.expand("uc", dict(rn, last7=3.5))["per_user"]["status"] == "normal"
    assert attrib.expand("uc", rn, alerts=[{"family": "rate_drift", "severity": "warning"}]
                         )["per_user"]["status"] == "bigda"                                      # an open alert decides
    fell = dict(rn, last7=2.0, sp=attrib.uc(100, 100, 80, 90, 10, 12, 45))                  # per install: fewer leave
    assert attrib.expand("uc", fell)["per_user"]["status"] == "behtar"
    for host in ({"p": 0.3, "prev": 0.2}, {"recent": {"p": 0.3}, "prev": {"p": 0.2}}, {"before": 0.2, "now": 0.3, "n": 1}):
        assert attrib.expand("rate", dict(host, sp=["ur", 10, 12]), days=1)["per_user"]["status"] is None


def test_a_verdict_word_never_contradicts_the_per_user_part_it_ends():
    """The word is the host's verdict on its own number; beside a per-user part that moved the other way (installs
    explain more than the whole drop, a band on another number) it is left off — the verdict itself never changes."""
    drop = {"family": "act_drift", "metric": "ret_dau", "severity": "watch", "before": 20000, "now": 19000,
            "sp": attrib.ret(-1600, 4000, 2400, 1000, 600, 12.0, 12.0, 30, 0)}     # installs −1,600; per user +600
    x = attrib.expand("act_alert_ret", drop)
    assert x["per_user"]["abs"] > 0 and x["per_user"]["status"] is None and drop["severity"] == "watch"
    assert attrib.expand("act_alert_ret", dict(drop, now=17000))["per_user"]["status"] == "dhyan"   # per user −400
    # the daily uninstall tile, "Low" band (behtar) while the per-install part rose: no word
    rn = {"last7": 2.0, "lo": 3.0, "hi": 4.0, "out_of_band": True, "sp": attrib.uc(100, 130, 80, 90, 10, 12, 45)}
    assert attrib.expand("uc", rn)["per_user"]["status"] is None
    # an update's revenue row "better" (judged on ads per user) while revenue per user fell: no word
    r = {"status": "better", "before": 2.0, "after": 1.9, "sp": attrib.rev(1000, 1300)}
    assert attrib.expand("rev", r)["per_user"]["status"] is None
    # money back per 100, "worse" because installs cost more while each install earns a bit more: no word
    b7 = {"st": "worse", "sp": attrib.vpi(0.020, 0.0202, 0.060, 0.096)}
    assert attrib.expand("vpi", b7)["per_user"]["status"] is None
    # a closed change keeps its split but never the word of the severity it had while open
    assert attrib.expand("act_alert_ret", dict(drop, now=17000, closed="2026-09-24"))["per_user"]["status"] is None


def test_the_wire_rounding():
    # 4 significant digits under 1,000 (a small app's installs a day keep their parts), whole from 1,000 up
    assert attrib.cnt(12.3456) == 12.35 and attrib.cnt(12.0) == 12 and attrib.cnt(1234.4) == 1234
    assert attrib.cnt(3.4567) == 3.457 and attrib.cnt(999.96) == 1000 and isinstance(attrib.cnt(1500.4), int)
    assert attrib.cnt(-0.04) == -0.04 and attrib.cnt(0) == 0 and attrib.cnt(150.44) == 150.4
    assert attrib.rate5(0.1234567) == 0.12346 and attrib.m4(2.03456) == 2.0346 and attrib.m6(0.0123456789) == 0.012346
    assert attrib.p2(13.456) == 13.46 and attrib.p2(14.0) == 14
    with pytest.raises(ValueError):
        attrib.cnt(float("nan"))
    assert attrib.safe(lambda: attrib.ret(float("inf"), 0, 0, 1, 1, None, None, None, 0)) == ["no", "error"]
    assert attrib.FAILS == 1
    attrib.ON = False
    assert attrib.safe(lambda: attrib.rate("rr", 1, 2)) is None                     # off: no split anywhere


def test_the_pooled_portfolio_split_sums_the_apps_it_covers():
    ms = [{"s": [11000 * 7, 7, 10000 * 28, 28], "sp": attrib.ret(500, 1000, 1400, 100, 150, 10.0, 9.33, 30, 0)},
          {"s": [5100 * 7, 7, 5000 * 28, 28], "sp": attrib.ret(-100, 600, 520, 80, 60, 7.5, 8.67, 30, 1)},
          {"s": [500 * 7, 7, 500 * 28, 28], "sp": ["no", "cohorts"]},                # 500 of 15,500: 3% uncovered
          {"s": [9000 * 7, 7, 9000 * 28, 28], "st": "wait", "sp": None}]              # waiting: not in the tile either
    x = adds_up(attrib.pool(ms))
    assert x["apps"] == {"of": 3, "with": 2} and x["total"]["before"] == pytest.approx(15000)
    assert x["from_installs"]["abs"] == pytest.approx(400) and x["est"] and x["mode"] == "cohort"
    assert x["per100"]["before"] == pytest.approx(100 * 1600 / (100 * 1000 / 10 + 100 * 600 / 7.5))
    assert x["per100"]["after"] == pytest.approx(100 * 1920 / (100 * 1400 / 9.33 + 100 * 520 / 8.67))
    assert x["per100"]["k"] == 30 and x["per_user"]["status"] is None
    assert x["per_user"]["own"] == pytest.approx((16100 - 1920) / (15000 - 1600) - 1)
    ms[2]["s"] = [5000 * 7, 7, 5000 * 28, 28]                                          # 25% of the level uncovered
    assert attrib.pool(ms)["none"] == "apps"


# ── 2. the engines, against a known truth ──────────────────────────────────────────────────────────

def _active(st, rv, E=END, astate=None, ustate=None):
    s = dict(st, window_end=E.isoformat())
    udet, _ = eng.evaluate_app(s, "a", "App", {} if ustate is None else ustate, NOW, revenue=rv)
    return act.evaluate(s, "a", "App", {} if astate is None else astate, NOW, udet, KEY, rv, None)


def test_active_installs_doubling_is_the_installs_part_and_old_users_moving_is_the_real_part():
    S = END - timedelta(days=act.ACT_LATE_DAYS)
    X = S - timedelta(days=6)                                           # the tile's 7 days start here
    st, rv = make_active_store(days=400, noise=0.0, hll=0.0, new=lambda c: 500 if c < X - timedelta(days=20) else 1000)
    d, row = _active(st, rv)
    t = d["tiles"]["ret_dau"]
    x = adds_up(attrib.expand("act_tile_ret", t, k=d["daily"]["old_k"]))
    assert x["total"]["rel"] > 0.02 and x["mode"] == "cohort"
    assert abs(x["per_user"]["rel"]) <= 0.01 and x["from_installs"]["rel"] == pytest.approx(x["total"]["rel"], abs=0.01)
    # the installs that feed the returners (each lag weighted by how many come back on it), after vs before
    X0, B0 = S - timedelta(days=6), S - timedelta(days=34)
    nw = lambda d, k: 1000 if d - timedelta(days=k) >= X - timedelta(days=20) else 500      # noqa: E731
    w = [synth.DEFAULT_RET(k) for k in range(1, 31)]
    feed = lambda d0, n: sum(w[k - 1] * sum(nw(d0 + timedelta(days=i), k) for i in range(n)) / n  # noqa: E731
                             for k in range(1, 31)) / sum(w)
    assert x["installs"]["rel"] == pytest.approx(feed(X0, 7) / feed(B0, 28) - 1, abs=0.01)
    assert row["m"]["ret_dau"]["sp"] == t["sp"]
    for k in ("d1", "d7"):                                              # the same return rates on twice the installs
        y = adds_up(attrib.expand("act_tile_rr", d["tiles"][k]))
        assert abs(y["per_user"]["rel"]) <= 0.01 and y["from_installs"]["rel"] > 0.1
        assert y["per_user"]["own"] == pytest.approx(0, abs=0.01) and "sp" not in row["m"][k]
    st, rv = make_active_store(days=400, noise=0.0, hll=0.0, old=lambda c: 20000 if c < X else 22000)
    d, _ = _active(st, rv)
    x = adds_up(attrib.expand("act_tile_ret", d["tiles"]["ret_dau"]))
    assert abs(x["from_installs"]["rel"]) <= 0.01 and x["per_user"]["own"] == pytest.approx(0.10, abs=0.01)
    assert x["per_user"]["rel"] == pytest.approx(x["total"]["rel"], abs=0.01)
    ar = d["tiles"]["arpdau"]                                           # revenue: the users part (+) and per user
    w = adds_up(attrib.expand("rev", ar))
    assert w["installs"]["what"] == "users" and w["from_installs"]["rel"] > 0.05


def test_active_without_return_cohorts_the_split_says_so_and_the_elastic_part_is_an_estimate():
    st, rv = make_active_store(days=400, noise=0.0, hll=0.0, ret=False)
    d, row = _active(st, rv)
    assert d["tiles"]["ret_dau"]["sp"] == ["no", "cohorts"] and row["m"]["ret_dau"]["sp"] == ["no", "cohorts"]
    x = attrib.expand("act_tile_ret", d["tiles"]["ret_dau"])
    assert x["none"] == "cohorts" and attrib.line(x) == ""
    # elastic mode (β̂ from the installs' past swings, no cohorts): installs part = β̂·log(n1 ÷ n0) × the before level
    att = {"mode": "elastic", "inst_part": 0.05, "rb": 20000.0, "n0": 400.0, "n1": 600.0, "est": True}
    P = {"H": 0}
    sp = act._sp_ret(P, att, 0, 0, 0, 0)
    assert sp == ["ret", 1000, 0, 0, 400, 600, None, None, None, 3]
    assert act._sp_ret(P, dict(att, mode="raw"), 0, 0, 0, 0) == ["no", "cohorts"]


def test_active_spike_install_snapshot_is_unchanged_by_the_refactor():
    def old_spike_inst(P, d, rel, med):                                   # 71eda0c's _spike_inst, verbatim
        if not med:
            return None
        Y = P["Y"]
        n1, n0 = act._mean_new(P, d - 7, d - 1), act._mean_new(P, d - 35, d - 8)
        swing = (n1 / n0 - 1) if n1 is not None and n0 else None
        part, upto = None, False
        if act._cohort_mode(P, d - 28, d) and Y[d] is not None:
            yb = [Y[i] for i in range(max(0, d - 28), d) if Y[i] is not None and P["valid"]["ret_dau"][i]]
            if len(yb) >= 14:
                part = (Y[d] - sum(yb) / len(yb)) / med
        elif swing is not None and swing > -1 and n0:
            part, upto = min(act.YS_MAX, n0 * act.RET_SUM_MAX / med) * math.log(1 + swing), True
        if part is None or act._sgn(part) != act._sgn(rel) or abs(part) < 0.5 * abs(rel):
            return None
        return {"mode": "cohort" if not upto else "raw", "part": act._m4(part if abs(part) <= abs(rel) else rel),
                "swing": act._m4(swing), "upto": upto}
    n = 0
    for ret in (True, False):
        rnd = random.Random(2)
        st, rv = make_active_store(days=300, ret=ret, new=lambda c: rnd.choice([300, 500, 900, 2000]))
        P = act.prepare(dict(st, window_end=END.isoformat()), {}, rv, END)
        for d in range(60, P["iS"] + 1, 3):
            med = P["fast"]["ret_dau"].med[d]
            for rel in (0.3, -0.3, 0.05, -0.05):
                assert act._spike_inst(P, d, rel, med) == old_spike_inst(P, d, rel, med)
                n += 1
    assert n > 300


def test_uninstall_count_more_installs_at_the_same_churn_is_the_installs_part():
    start, end = date(2026, 5, 1), date(2026, 9, 19)
    X = end - timedelta(days=6)                                       # the shown 7 days: +50% installs
    t = Truth(start, end, lambda c: 4500 if c >= X else 3000, old_per_day=300, seed=3)
    st = truth_store(t, end)
    ds = eng.daily_series(st)
    n = ds["n"]
    f = n - 7
    sp = eng._sp_uc(ds, f - eng.BAND_DAYS, f, [i for i in range(f, n) if ds["good"][i]])
    x = adds_up(attrib.expand("uc", {"sp": sp, "last7": 1, "lo": 0, "hi": 2, "out_of_band": False}))
    # the installs % is the installs feeding the expected uninstalls, each lag weighted by its usual share leaving
    # (the shown 7 days' +50% reaches only the youngest lags): the installs part has its sign and is at most it
    h = eng._expect_from(ds, f - eng.BAND_DAYS, f).h
    aft = [i for i in range(f, n) if ds["good"][i]]
    want = sum(h[L] * (1.5 if i - L >= f else 1.0) for i in aft for L in range(len(h))) / len(aft) / sum(h) - 1
    assert x["total"]["rel"] > 0.25 and x["installs"]["rel"] == pytest.approx(want, abs=0.002)
    assert 0 < x["from_installs"]["rel"] <= x["installs"]["rel"]
    assert abs(x["per_user"]["rel"]) <= 0.03 and abs(x["per_user"]["own"]) <= 0.03
    assert x["per100"]["before"] == pytest.approx(91.8, abs=0.5)                      # 918 of 1,000 leave in 28 days
    d, _ = eng.evaluate_app(st, "a", "App", {}, NOW)
    assert not [a for a in d["alerts"] if a["family"].startswith("rate")]               # the existing rule: no alert
    y = adds_up(attrib.expand("uc", d["rate_now"]))                                      # … and the tile's split says why
    assert abs(y["per_user"]["rel"]) <= 0.05 and y["from_installs"]["rel"] > 0.1


def test_uninstall_cohort_rate_up_while_installs_fall_are_opposite_parts():
    start, end = date(2026, 5, 1), date(2026, 9, 19)
    X = date(2026, 9, 1)
    t = Truth(start, end, lambda c: 1800 if c >= X else 3000, old_per_day=300, seed=4,
              bump=lambda c: {0: 150} if c >= X else None)                            # D0: 600 → 750 of 1,000
    st = truth_store(t, end)
    d, row = eng.evaluate_app(st, "a", "App", {}, NOW)
    co = [a for a in d["alerts"] if a["family"] == "cohort" and a["dir"] == "up"]
    assert co and co[0]["sp"][0] == "ur"
    x = adds_up(attrib.expand("rate", co[0]))
    assert x["from_installs"]["rel"] < -0.2 and x["per_user"]["rel"] > 0.1             # installs down, churn up
    assert x["per_user"]["status"] == attrib.SEV_ST[co[0]["severity"]]
    cells = [c for c in row["head4"].values() if c and c.get("sp")]
    assert cells and all(adds_up(attrib.expand("rate", c, days=0)) for c in cells)
    tab = [r for r in d["table"] if r.get("sp")]
    assert tab and all(adds_up(attrib.expand("rate", r)) for r in tab)


def _impact_app(**kw):
    rels = [(END - timedelta(days=60), "1.5", 0.6), (END - timedelta(days=12), "2.0", 0.6)]
    st, rv = make_impact_store(160, versions=rollout("1.0", rels), noise=0.02, seed=5, **kw)
    return st, rv


def test_update_impact_expected_is_before_plus_installs_plus_trend_exactly(monkeypatch):
    seen = []
    real = imp._split_rows

    def check(cx, rows, N):                                             # before rounding: the row's own numbers
        for k, r in rows.items():
            x = r.get("_spx")
            if k == "returning_dau" and x and x[0] == "dau" and r.get("expected") is not None:
                _, src, srcb, syb, stt, n, srho = x
                seen.append((r["before"] + (src - srcb) / n + (stt + srcb - syb) / n, r["expected"], N))
        return real(cx, rows, N)
    monkeypatch.setattr(imp, "_split_rows", check)
    st, rv = _impact_app(new=lambda c: 2000 if c < END - timedelta(days=40) else 3000)
    d, _ = eng.evaluate_app(st, "a", "App", {}, NOW, revenue=rv)
    assert seen and {N for *_, N in seen} >= {7, 14, 30}
    for got, want, _ in seen:
        assert math.isclose(got, want, rel_tol=1e-12), (got, want)
    b = d["impact"]["updates"][0]
    r = b["rows"]["returning_dau"]
    if r["status"] in attrib.JUDGED:
        x = adds_up(attrib.expand("imp_dau", r))
        assert abs(x["total"]["before"] + x["from_installs"]["abs"] + x["trend"]["abs"] - r["expected"]) <= 2
        assert x["installs"] is not None and len(r["sp"]) == 5
    for n, W in b["by_window"].items():                                 # 14 / 30 / 60: 3 items (no installs %)
        wr = W["rows"]["returning_dau"]
        assert "sp" not in wr or wr["sp"][0] == "no" or len(wr["sp"]) == 3


def test_update_impact_without_cohorts_or_on_a_steep_trend_says_why():
    st, rv = _impact_app()
    st["ret"] = {}                                                       # no return cohorts: raw mode
    d, _ = eng.evaluate_app(st, "a", "App", {}, NOW, revenue=rv)
    r = d["impact"]["updates"][0]["rows"]["returning_dau"]
    assert r["extra"]["mode"] == "raw" and (r["status"] not in attrib.JUDGED or r["sp"] == ["no", "cohorts"])
    st, rv = _impact_app(old=lambda c: int(30000 * math.exp(0.08 * (c - END).days)))    # ×1.75 a week: steep
    d, _ = eng.evaluate_app(st, "a", "App", {}, NOW, revenue=rv)
    r = d["impact"]["updates"][0]["rows"]["returning_dau"]
    assert r["basis"] == "plain" and r["status"] == "low" and r["sp"] == ["no", "steep_up"]   # which way it moves
    assert attrib.expand("imp_dau", r)["none"] == "steep_up"             # a Low data row: only why there is none
    st, rv = _impact_app(old=lambda c: int(30000 * math.exp(-0.08 * (c - END).days)))   # ×0.57 a week: falling fast
    d, _ = eng.evaluate_app(st, "a", "App", {}, NOW, revenue=rv)
    r = d["impact"]["updates"][0]["rows"]["returning_dau"]
    assert r["status"] == "low" and r["sp"] == ["no", "steep_dn"]


def _weeks(n, spend, R7, inst):
    W0 = date(2026, 6, 1)
    return {W0 + timedelta(days=7 * i): {"W": W0 + timedelta(days=7 * i), "judged": True,
                                         "cj": [True] * len(val.T), "R": [R7(i)] * len(val.T), "spend": spend(i),
                                         "n": inst(i)} for i in range(n)}


def test_money_back_is_the_same_weeks_as_b7_and_splits_into_cost_and_earning():
    by = _weeks(10, lambda i: 100.0 if i < 8 else 180.0, lambda i: 40.0 if i < 8 else 48.0, lambda i: 1000)
    e = max(by) + timedelta(days=6)
    T, info = val._b7_at(by, e)
    sp = val._sp_vpi(info)
    x = adds_up(attrib.expand("vpi", {"severity": "warning", "sp": sp}))
    assert x["total"]["after"] == pytest.approx(100 * info["b7r"], rel=1e-5)
    assert x["total"]["before"] == pytest.approx(100 * info["b70"], rel=1e-5)
    assert x["installs"]["rel"] == pytest.approx(0.8) and x["per_user"]["own"] == pytest.approx(0.2)
    rc = info["rec"]                                                     # the unrounded identity
    assert (100 * (sum(w["R"][val._tj(7)] for w in rc) / sum(w["n"] for w in rc))
            / (sum(w["spend"] for w in rc) / sum(w["n"] for w in rc))) == pytest.approx(100 * info["b7r"], rel=1e-12)


def test_value_tiles_and_alerts_carry_their_splits():
    with open("tests/fixtures/value_sample.json", encoding="utf-8") as f:
        fx = json.load(f)
    seen = set()
    for det in fx["app_files"].values():
        T = det["tiles"]
        for k, kind in (("b7", "vpi"), ("rpi", "ir"), ("cpi", "spd")):
            if T[k].get("sp"):
                x = adds_up(attrib.expand(kind, T[k]))
                seen.add(kind)
                if kind == "spd":
                    assert x["installs"]["what"] == "installs" and x["per"] == "week"
    for a in fx["dashboard_value"]["alerts"]:
        if a.get("sp"):
            k = attrib.alert_kind(a)
            adds_up(attrib.expand(k, a))
            seen.add(a["family"] + ":" + a["sp"][0])
    assert {"vpi", "ir", "spd", "pay_slow:vpi", "geo_move:rr"} <= seen, seen


def test_an_earning_per_install_tile_with_no_before_value_carries_no_split(monkeypatch):
    """"low" (no earning before) shows no change, so it gets no split — as Active's wait / noad / low tiles (F1)."""
    m = vs.make_app(start=vs.END - timedelta(days=60 * 7 - 1), seed=3)
    orig = val._tiles

    def ev(zero):
        def tiles(P, weeks, *a, **k):
            if zero:                       # the weeks before the tile's newest 4 earned nothing
                c30 = [w for w in weeks if w["cj"][val._tj(30)] and w["n"] > 0]
                for w in c30[:-val.TILE_WEEKS]:
                    w["R"] = [0.0] * len(w["R"])
            return orig(P, weeks, *a, **k)
        monkeypatch.setattr(val, "_tiles", tiles)
        det, _, _ = val.evaluate_app(copy.deepcopy(m["store"]), copy.deepcopy(m["ida"]), m["rev"], m["spend"], m["fx"],
                                     [], None, {}, {"payback_days": 90}, "2026-09-21T12:00:00Z", app_id="app-x",
                                     app="Demo App", key="k")
        return det["tiles"]["rpi"]
    attrib.ON = True
    live, low = ev(False), ev(True)
    assert live["st"] != "low" and live["sp"][0] == "ir"
    assert low["st"] == "low" and not low["base"] and "sp" not in low


# ── 3. invariance: off vs on, only "sp" differs ───────────────────────────────────────────────────

def _twice(fn):
    attrib.ON = False
    off = fn()
    attrib.ON = True
    on = fn()
    return off, on


def test_active_and_uninstall_outputs_and_states_are_identical_with_the_split_off_and_on():
    rnd = random.Random(9)
    st, rv = make_active_store(days=400, new=lambda c: rnd.choice([400, 500, 700, 1500]),
                               old=lambda c: 20000 if c < END - timedelta(days=25) else 17000,
                               versions=rollout("1.0", [(END - timedelta(days=40), "2.0", 0.5)]))

    def history():
        astate, ustate, out = {}, {}, []
        for k in range(6, -1, -1):
            E = END - timedelta(days=k)
            s = dict(st, window_end=E.isoformat())
            udet, urow = eng.evaluate_app(copy.deepcopy(s), "a", "App", ustate, E.isoformat() + "T12:00:00Z",
                                          revenue=rv)
            d, row = act.evaluate(s, "a", "App", astate, E.isoformat() + "T12:00:00Z", udet, KEY, rv, None)
            out.append((udet, urow, d, row))
        return out, astate, ustate
    (o_off, a_off, u_off), (o_on, a_on, u_on) = _twice(history)
    assert dump(no_sp(o_off)) == dump(no_sp(o_on)) and dump(no_sp(a_off)) == dump(no_sp(a_on))
    assert dump(no_sp(u_off)) == dump(no_sp(u_on))
    txt = dump(o_on)
    assert '"sp": ["ret"' in txt and '"sp": ["ur"' in txt and '"sp": ["imp"' in txt       # it did split
    assert '"sp": [' not in dump(o_off).replace('"sp": null', "")                        # off: none at all
    assert all(a["sp"] is None for *_, d, _ in o_off for a in d["changes"]["open"])


def test_value_outputs_are_identical_with_the_split_off_and_on():
    m = vs.make_app(start=vs.END - timedelta(days=60 * 7 - 1), seed=3)

    def ev():
        return val.evaluate_app(m["store"], m["ida"], m["rev"], m["spend"], m["fx"], [], None, {},
                                {"payback_days": 90}, "2026-09-21T12:00:00Z", app_id="app-x", app="Demo App", key="k")
    off, on = _twice(ev)
    assert dump(no_sp(off)) == dump(no_sp(on)) and '"sp": [' not in dump(off)


# ── 4. failure isolation, the switch, the Telegram tail ──────────────────────────────────────────

def test_a_split_that_raises_costs_only_that_split(monkeypatch):
    st, rv = make_active_store(days=400, noise=0.0, hll=0.0)
    good, _ = _active(st, rv)

    def boom(*a, **k):
        raise ZeroDivisionError("synthetic")
    monkeypatch.setattr(attrib, "ret", boom)
    attrib.FAILS = 0
    bad, _ = _active(st, rv)
    assert bad["tiles"]["ret_dau"]["sp"] == ["no", "error"] and attrib.FAILS == 1
    assert attrib.expand("act_tile_ret", bad["tiles"]["ret_dau"])["none"] == "error"
    assert attrib.line(attrib.expand("act_tile_ret", bad["tiles"]["ret_dau"])) == ""
    assert dump(no_sp(bad)) == dump(no_sp(good))                          # every verdict and number the same


def test_the_telegram_line_gets_the_split_before_its_label_and_never_on_an_update_verdict():
    sp = attrib.rate("ur", 3000, 1800)
    uni = {"id": "u1", "family": "cohort", "n": 1, "severity": "warning", "before": 0.2, "now": 0.28, "notify": True,
           "message": "App: D1 uninstall 20% → 28%", "sp": sp}
    halt = {"id": "u2", "family": "impact", "severity": "warning", "notify": True, "message": "App: v2 ke baad …",
            "sp": sp}                                                        # (never carried; ignored if it were)
    ret = {"id": "a1", "family": "act_drift", "metric": "ret_dau", "severity": "warning", "before": 40000,
           "now": 36000, "notify": True, "message": "App: purane users kam",
           "sp": attrib.ret(-1000, 3000, 2000, 900, 700, None, None, None, 0)}
    pu = {"id": "a2", "family": "act_drift", "metric": "ads", "severity": "watch", "notify": True,
          "message": "App: ads kam", "sp": attrib.pu([("new", 0.1, 0.2)])}
    vpi = {"id": "v1", "family": "pay_slow", "severity": "warning", "notify": True, "message": "App: paisa der se",
           "sp": attrib.vpi(5.0, 4.8, 10.0, 12.0)}
    dash = {"uninstall": {"alerts": [uni, halt]}, "active": {"alerts": [ret, pu]}, "value": {"alerts": [vpi]}}
    s = {"notify_dry_run": True, "telegram_token": "", "telegram_chat": "", "smtp": {}, "split": True}
    res = build_static.send_alerts(dash, s)
    body = next(r["body"] for r in res if r["channel"] == "email").split("\n")
    # the one-liner names what it counts (daily uninstalls: the users uninstalling a day, not the headline's rate) and
    # its parts add up as printed; installs −40% with the rate up 40% reads as counts, never "real +24%"
    assert ("🟠 [WARNING] App: D1 uninstall 20% → 28% · daily uninstalls: ~−100 = from installs ~−240 + real ~+140 "
            "(total −16%) · uninstall (GA4)") in body
    assert "🟠 [WARNING] App: v2 ke baad … · update impact (GA4)" in body
    assert ("🟠 [WARNING] App: purane users kam · old users, daily: total −10% = from installs −3% + real −7% "
            "· active users (GA4)") in body
    assert "🟡 [WATCH] App: ads kam · active users (GA4)" in body
    assert ("🟠 [WARNING] App: paisa der se · money back: total −20% = from price −17% + from revenue −3% "
            "· install value (GA4 + Ads)") in body
    off = build_static.send_alerts(dash, dict(s, split=False))
    body = next(r["body"] for r in off if r["channel"] == "email")
    assert " se " not in body.replace("paisa der se", "") and "asli" not in body and ": total " not in body and "(total " not in body


def test_the_switch_reaches_the_build_from_a_repo_variable(monkeypatch):
    import os
    from admob_iq.config import settings
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        assert "SPLIT:                ${{ vars.SPLIT || 'true' }}" in f.read()
    monkeypatch.setenv("SPLIT", "false")
    assert settings()["split"] is False
    monkeypatch.delenv("SPLIT")
    assert settings()["split"] is True


def test_the_fixtures_carry_splits_that_add_up_and_nothing_in_a_devanagari_or_banned_word():
    with open("tests/fixtures/active_sample.json", encoding="utf-8") as f:
        A = json.load(f)
    n = 0
    for det in A["app_files"].values():
        for k, kind in (("ret_dau", "act_tile_ret"), ("d1", "act_tile_rr"), ("d7", "act_tile_rr"), ("arpdau", "rev")):
            x = attrib.expand(kind, det["tiles"][k], k=det["daily"]["old_k"])
            if x and "shown" in x:
                adds_up(x)
                n += 1
                line = attrib.line(x)
                assert len([w for w in line.split() if re.search(r"[A-Za-z]", w)]) <= 12
                assert "pts" not in line and "NaN" not in line
    assert n >= 20
    assert attrib.pool([r["m"]["ret_dau"] for r in A["dashboard_active"]["apps"] if r.get("m")]) is not None


# ── 5. the review's findings, each against a known truth ─────────────────────────────────────────

def test_active_installs_up_while_new_users_return_less_is_volume_plus_a_per_user_drop():
    """S1: "installs ki wajah se" is the installs moving at the before days' return per install — the recent installs'
    own return falling is a per-user change (it was inside the installs' part before the review)."""
    S = END - timedelta(days=act.ACT_LATE_DAYS)
    w0 = S - timedelta(days=6)
    cut = w0 - timedelta(days=1)             # from the last before-day on: twice the installs, each coming back half as often
    st, rv = make_active_store(days=400, noise=0.0, hll=0.0, new=lambda c: 1000 if c >= cut else 500,
                               rho=lambda c, k: synth.DEFAULT_RET(k) * (0.5 if c >= cut else 1.0))
    d, _ = _active(st, rv)
    t = d["tiles"]["ret_dau"]
    x = adds_up(attrib.expand("act_tile_ret", t))
    # truth: the extra 500 installs a day of the new cohorts at the OLD return per install, over the tile's 7 days
    vol = sum(500 * synth.DEFAULT_RET(k) for i in range(7) for k in range(1, 31)
              if w0 + timedelta(days=i - k) >= cut) / 7
    assert x["mode"] == "cohort" and x["from_installs"]["abs"] == pytest.approx(vol, rel=0.03)
    assert x["per_user"]["abs"] == pytest.approx(x["total"]["abs"] - vol, abs=0.03 * vol) and x["per_user"]["abs"] < 0
    assert x["per_user"]["own"] == pytest.approx(0, abs=0.01)                  # the 30+ day old users: flat
    assert x["per100"]["after"] < 0.95 * x["per100"]["before"] and x["per100"]["k"] == 30
    fi, yb, yw, nb, na = t["sp"][1:6]
    assert abs(yw - yb) < 0.1 * vol                                            # (yw − yb, the old part, said ~0)
    # the installs % beside the part is the one that drives it: the same sign, fi = yb · (na ÷ nb − 1)
    assert na > nb and fi == pytest.approx(yb * (na / nb - 1), rel=0.01)


def test_active_alerts_and_spikes_read_the_same_volume_rule():
    """act_drift / act_slow / act_spike and the info rows carry the same wire: the installs % always has the sign of the
    installs' part, and the part is at most the recent returners' share of the level times that %."""
    rnd = random.Random(4)
    st, rv = make_active_store(days=400, new=lambda c: rnd.choice([300, 500, 900, 2500]),
                               old=lambda c: 20000 if c < END - timedelta(days=30) else 16000)
    d, _ = _active(st, rv)
    seen = 0
    for h in d["changes"]["open"] + d["changes"]["info"] + [d["tiles"]["ret_dau"]]:
        sp = h.get("sp")
        if not (isinstance(sp, list) and sp and sp[0] == "ret" and not sp[9] & 2):
            continue
        fi, yb, yw, nb, na = sp[1:6]
        assert fi == 0 or (fi > 0) == (na > nb), sp
        assert fi == pytest.approx(yb * (na / nb - 1), rel=0.01, abs=1), sp
        assert sp[8] == d["daily"]["old_k"]                                    # the per-100's days travel with it
        seen += 1
    assert seen >= 1


def test_update_impact_installs_part_is_the_installs_moving_at_one_return_rate(monkeypatch):
    """F2: fi = Σ(recent(d) − recent(b)) ÷ n — the same ρ̂ on both sides. The before days' measured returners vs ρ̂
    (Σ recent(b) − Σ Y(b)) is not installs moving: it sits with the trend, so before + fi + tr is still expected."""
    seen = []
    real = imp._split_rows

    def check(cx, rows, N):
        r = rows.get("returning_dau") or {}
        x = r.get("_spx")
        real(cx, rows, N)
        if x and x[0] == "dau" and r.get("sp") and r["sp"][0] == "imp":
            seen.append((x, r["sp"], N, r["before"], r["expected"]))
    monkeypatch.setattr(imp, "_split_rows", check)
    R = END - timedelta(days=12)
    # installs flat; the cohorts feeding the before days come back 30% less than the pre-release ρ̂
    st, rv = make_impact_store(160, versions=rollout("1.0", [(END - timedelta(days=60), "1.5", 0.6), (R, "2.0", 0.6)]),
                               noise=0.0, seed=5, new=2000,
                               rho=lambda c, k: synth.DEFAULT_RET(k) * (0.7 if R - timedelta(days=12) <= c < R else 1.0))
    eng.evaluate_app(st, "a", "App", {}, NOW, revenue=rv)
    assert seen
    for x, sp, N, before, expected in seen:
        _, src, srcb, syb, stt, n, srho = x
        assert sp[1] == attrib.cnt((src - srcb) / n)
        assert math.isclose(before + (src - srcb) / n + (stt + srcb - syb) / n, expected, rel_tol=1e-12)
        if N == 7:
            assert len(sp) == 5 and (sp[1] == 0 or (sp[1] > 0) == (sp[4] > sp[3]))
    flat = [(x, sp) for x, sp, N, *_ in seen if N == 7]
    assert flat and all(sp[1] == 0 for _, sp in flat)                          # flat installs: no installs part …
    assert any(abs((x[1] - x[3]) / x[5]) > 50 for x, _ in flat)                # … which the old ΣY(b) formula had


def test_a_big_install_swing_reads_as_counts_never_an_impossible_percent():
    """F5 / F11: with installs ×0.1 or ×6 a % of the before total can't say the per-user change (it came out −300% or
    +15% beside "100 me 20 → 50"): the parts are shown as numbers a day, still adding up; a % that is within ⅔–1.5× of
    the rate's own change stays a %."""
    x = adds_up(attrib.expand("rate", {"before": 0.20, "now": 0.50, "severity": "warning", "sp": ["ur", 1000, 100]}))
    assert x["form"] == "count" and x["shown"]["count"] == {"exp": 1, "total": -15, "from_installs": -18, "trend": None,
                                                            "per_user": 3}
    assert x["per_user"]["status"] == "bigda"                                  # more of each 100 leave: the bad way
    assert attrib.line(x) == "daily uninstalls: ~−150 = from installs ~−180 + real ~+30 (total −75%)"
    y = adds_up(attrib.expand("rate", {"before": 0.40, "now": 0.20, "severity": "good", "sp": ["ur", 100, 600]}))
    assert y["form"] == "count" and y["shown"]["per_user"] <= -100 and y["shown"]["count"]["per_user"] == -12
    d1 = adds_up(attrib.expand("act_tile_rr", {"sp": ["rr", 1000, 4000], "s": [4200, 28000, 8400, 28000],
                                              "n": 7, "nb": 28, "st": "worse"}, days=1))
    assert d1["form"] == "count" and d1["per_user"]["own"] == pytest.approx(-0.5)
    same = adds_up(attrib.expand("rate", {"before": 0.30, "now": 0.27, "sp": ["rr", 5000, 6000]}))
    assert same["form"] == "pct" and same["shown"]["per_user"] == -12            # 1.2 × the rate's −10%: a %
    rnd = random.Random(11)
    for _ in range(5000):                                                       # never a shown % at −100% or below
        ib = rnd.uniform(5, 5000)
        z = adds_up(attrib.expand("rate", {"before": rnd.uniform(0.01, 0.9), "now": rnd.uniform(0.01, 0.9),
                                           "sp": ["rr", ib, ib * math.exp(rnd.gauss(0, 1))]}))
        if z["form"] == "pct":
            assert min(z["shown"]["from_installs"], z["shown"]["per_user"]) > -100
            if abs(z["per_user"]["own"]) >= 0.05:
                assert 2 / 3 - 1e-9 <= z["per_user"]["rel"] / z["per_user"]["own"] <= 1.5 + 1e-9
    # money in the count form has no one-liner (its amounts need the page's currency); the block still has it
    m = attrib.expand("spd", {"st": "normal", "sp": attrib.spd(100, 400, 0.05, 0.10)})
    assert m["form"] == "count" and attrib.line(m) == ""


def test_uninstall_count_own_change_is_the_alerts_own_number():
    """F8: the per-install change the block prints is the alert's own rel (actual ÷ its expected − 1), calibrated as
    the alert is (rate_drift: exp(median log) over its base; rate_spike: its band's expected) — not a mean ratio."""
    start, end = date(2026, 5, 1), date(2026, 9, 19)
    X = end - timedelta(days=20)
    t = Truth(start, end, lambda c: 3000, old_per_day=300, seed=6,
              bump=lambda c: {L: 30 for L in range(0, 8)} if c >= X else None)
    st = truth_store(t, end)
    ds = eng.daily_series(st)
    dr = eng.rate_drift(ds)
    assert dr and dr["sp"][0] == "uc"
    x = adds_up(attrib.expand("uc", {"family": "rate_drift", "severity": "warning", "sp": dr["sp"]}))
    assert x["per_user"]["own"] == pytest.approx(dr["rel"], abs=2e-3)
    spikes = [s for s in eng.rate_spikes(ds) if s["family"] == "rate_spike"]
    for sp in spikes[:3]:
        i = (sp["day"] - ds["start"]).days
        f0 = eng._expect_from(ds, max(0, i - eng.BAND_DAYS), i)(i)
        w = eng._sp_uc(ds, max(0, i - eng.BAND_DAYS), i, [i], sp["expected"] / f0)
        assert attrib.expand("uc", {"sp": w, "severity": "warning"})["per_user"]["own"] == pytest.approx(sp["rel"],
                                                                                                        abs=2e-3)


def test_small_counts_keep_their_shown_parts():
    """F9: a small app's installs a day on the wire (4 significant digits) never move a shown part off the unrounded
    one by more than a rounding edge, and never flip its sign."""
    rnd = random.Random(12)
    for _ in range(3000):
        ib, ia = rnd.uniform(0.5, 30), rnd.uniform(0.5, 30)
        h = {"before": rnd.uniform(0.05, 0.9), "now": rnd.uniform(0.05, 0.9)}
        a = attrib.expand("rate", dict(h, sp=["ur", ib, ia]))
        b = attrib.expand("rate", dict(h, sp=attrib.rate("ur", ib, ia)))
        for k in ("total", "from_installs", "per_user"):          # at most a rounding edge (1, or 0.1% of a big %)
            assert abs(a["shown"][k] - b["shown"][k]) <= max(1, 1e-3 * abs(a["shown"][k])), (ib, ia, h, k)
            assert a["shown"][k] * b["shown"][k] >= 0 and (a["shown"][k] == 0) == (b["shown"][k] == 0) or \
                abs(a["shown"][k]) <= 1


def test_install_value_splits_are_the_tiles_own_numbers():
    """F1 / F7: the money-back tile's split ends at the tile's own week (its after = the tile's number, its before =
    the tile's base) and the cost tile's at its own 4 weeks (cost per install = the tile's, spend a week = the tile's
    spend ÷ weeks); a country's return rate splits installs a DAY (the rate's words are per day)."""
    with open("tests/fixtures/value_sample.json", encoding="utf-8") as f:
        fx = json.load(f)
    n = {"vpi": 0, "spd": 0, "rr": 0}
    for det in fx["app_files"].values():
        T = det["tiles"]
        if T["b7"].get("sp") and T["b7"]["sp"][0] == "vpi":
            x = adds_up(attrib.expand("vpi", T["b7"]))
            assert x["total"]["after"] == pytest.approx(T["b7"]["v"], rel=2e-3)
            assert x["total"]["before"] == pytest.approx(T["b7"]["base"], rel=2e-3)
            n["vpi"] += 1
        if T["cpi"].get("sp") and T["cpi"]["sp"][0] == "spd":
            x = adds_up(attrib.expand("spd", T["cpi"]))
            assert x["per100"]["after"] == pytest.approx(T["cpi"]["v"], rel=1e-3)
            assert x["total"]["after"] == pytest.approx(T["cpi"]["spend4"] / T["cpi"]["nw"], rel=1e-3)
            n["spd"] += 1
    for a in fx["dashboard_value"]["alerts"]:
        if a["family"] == "geo_move" and (a.get("sp") or [None])[0] == "rr":
            assert a["sp"][2] == pytest.approx(a["users"] / 14, rel=1e-3)      # 2 install weeks a day
            n["rr"] += 1
    assert all(n.values()), n
    # the cost split on its own: installs ×2 at twice the cost per install over the tile's 4 weeks vs the 8 before
    W0 = date(2026, 5, 4)
    ws = [{"W": W0 + timedelta(days=7 * i), "judged": True, "cj": [True] * len(val.T), "n": 1000 if i < 8 else 2000,
           "spend": 50.0 if i < 8 else 200.0, "R": [0.0] * len(val.T)} for i in range(12)]
    x = adds_up(attrib.expand("spd", {"st": "normal", "sp": val._sp_spd(ws, ws[8:])}))
    assert x["installs"]["rel"] == pytest.approx(1.0) and x["per_user"]["own"] == pytest.approx(1.0)
    assert x["total"]["before"] == pytest.approx(50) and x["total"]["after"] == pytest.approx(200)
    assert val._sp_spd(ws, ws[3:7]) is None                                    # 3 weeks before it: no before


def test_the_one_liner_names_what_it_counts():
    """F12: the one-liner leads with the counted thing, so its "kul" is never read as the headline's rate."""
    ur = attrib.expand("rate", {"before": 0.20, "now": 0.28, "severity": "warning", "sp": ["ur", 3000, 2900]})
    assert attrib.line(ur) == "daily uninstalls: total +35% = from installs −3% + real +38%"
    rr = attrib.expand("rate", {"before": 0.30, "now": 0.28, "severity": "watch", "sp": ["rr", 1000, 1100]})
    assert attrib.line(rr).startswith("daily returns: total +3% = from installs +10% + real −")
    dau_less = attrib.expand("uc", {"severity": "warning", "sp": attrib.uc(1000, 1150, 1000, 900, 3000, 2700, 45)})
    assert attrib.line(dau_less).startswith("daily uninstalls: total +15% = from installs −10% + real +25%")
