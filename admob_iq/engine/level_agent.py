"""🤖 LV-agent C1 — the level decision agent of the CPI vs eCPM screen (pure: no I/O, no clock, no module state; standard
library only plus engine.cpi_alarm). The owner does not tap Accept: every question the engine raises about a level is
answered here, from the data as it was known on the ask day d (every series cut at d with its maturity lags — no
look-ahead), and the build freezes each answer.

  questions  a proposal ("money": a money level steady 84 days going down; "open": an alarm open 120+ days) and the
             engine's own settle (56 days steady ±10 %) of CPI / GAP, or of any alarm whose proposal was answered: is
             the new level the new normal?
  answers    accept (the move is market-wide and steady: the new level becomes the normal) · keep (a visible cause is
             the owner's own lever: the alarm stays open and the cause is written) · wait (not decided yet: asked again
             on the engine's weekly phase)

The rule, cause first (C1), in plain words:
  0. no 14-day trend or no level value → wait "too thin".
  1. the cause, by family, from the driver split of the move between the old level's days and the new level's days:
     SPEND → keep (budget / bid limit); IPU → keep (ads per user: placements, frequency, app version);
     CPI → spend ×2 either way → keep; ≥ 30 % of spend in campaigns new since / gone after the old level → keep;
       < 60 % of the move inside campaigns → keep (mix); < 70 % of spend moving the same way or > 10 % opposite →
       wait (narrow); the other apps' CPI not moving the same way → keep (own campaigns only); else external;
     ECPM → ads per user moved ≥ 15 % → keep; the other apps moved the same way (≥ 3 of them, median ≥ half the own
       move, ≥ half of them beyond the band; a country split, when measured, mostly a rate move) → external (ads per
       user unknown: wait); else campaign turnover / spend ×2 → keep (user mix); else wait (this app only);
     GAP and the money families → the CPI part (cost per install) and the eCPM part (value per install): a part with
       ≥ 60 % of the move decides through its own tree, otherwise both parts must be external.
  2. external only: the last 14 days vs the 14 before moved > 1 band toward the old level → wait (coming back), > 1
     band further → wait (still moving); the 14-day level > 15 % off its 56-day median → wait (not steady); else C1
     accepts.
  3. the agent's own tests on a C1 accept, in this order (the first that holds makes it a wait): a money level is
     never lowered (ROAS_G / C0 / C1 / C7); an alarm the agent reverted before is the owner's only; the move must be
     ≥ move_bands bands and the new value outside one band of the old level; the eCPM-market branch also needs the
     engine's own settle steadiness (±engine_band over 56 days); every other branch also needs the persistence rule's
     accept (A1–A7, no K1 / K2).

Ported verbatim from the private study's two rules and its evidence builder (tests, order, arithmetic); the thresholds
are priors, none fitted. Wording: a cause names what was SEEN with the move ("seen with spend ×2.5 since the old
level"), never that it caused it; "campaigns" or "countries" exactly as the test read them. Every window is an ISO
[a, b] turned into each entity's own index (i = date − e.day0): every entity of the build has its own day0."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import date, timedelta

from . import cpi_alarm as CA

RULE = "C1"
TH = {"k_back": 1.0, "k_slide": 1.0, "steady": 0.15, "scale": math.log(2.0), "turn": 0.30, "rate_min": 0.60,
      "broad": 0.70, "opp_max": 0.10, "ipu_side": 0.15, "dom": 0.60, "mkt_frac": 0.50, "mkt_share": 0.50,
      "mkt_n": 3, "mkt_imp": 5000.0, "mkt_inst": 30.0}
PERSIST = {"keep_return_bands": 2.0, "n_fn_full": 6, "min_move_bands": 4.0, "steady_days": 56, "steady_dev": 0.10,
           "n_fn_hold": 4, "hold_bands": 1.0, "ret_bands": 1.0, "noise_frac": 0.5,
           "min_days_since_change": 84}
LAGS = {"dau": 1, "c_r0": 1, "c_r1": 2, "c_r7": 8}     # as of day d a cell later than d − lag is unknown (others: 0)
SEASON = (364, 728)
CHECKS = (28, 56, 84)
FORBIDDEN = ("follows", "because", "caused", "due to", "driven")    # never in a cause or a short (wording rule)
_CPI_BAND, _ECPM_BAND = 0.075, 0.05                    # the market test's own bands (the CPI and eCPM level deltas)
PF_CODES = ("A1", "A2", "A3", "A4", "A5", "A6", "A7")


# ── small helpers ───────────────────────────────────────────────────────────────────────────────────────────────────

def _ix(e, x):
    return (date.fromisoformat(x) - date.fromisoformat(e.day0)).days


def _iso(d0, i):
    return (date.fromisoformat(d0) + timedelta(days=i)).isoformat()


def _add(x, k):
    return (date.fromisoformat(x) + timedelta(days=k)).isoformat()


def _ndays(w):
    return (date.fromisoformat(w[1]) - date.fromisoformat(w[0])).days + 1


def fin(x, nd=6):
    if x is None:
        return None
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return round(x, nd)


def _rel(x, y):
    return None if (x is None or y is None or y == 0) else x / y - 1.0


def _g(o, *ks):
    for k in ks:
        if not isinstance(o, dict):
            return None
        o = o.get(k)
    return o


def _clean(x):
    """A JSON-safe copy (tuples → lists, a non-finite float → None): what the ledger stores is what decide reads."""
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def frozen(x):
    """x exactly as the ledger keeps it (sorted JSON round trip)."""
    return json.loads(json.dumps(_clean(x), sort_keys=True))


def band(fam, P):
    """The family's band: the engine's level delta (half the DRIFT minimum)."""
    return P["levels"]["delta"][fam]


def band_log(fam, P):
    return CA.lthr(fam, band(fam, P))


def next_phase(d):
    """The first day after d on the engine's weekly phase ((day − EPOCH) % 7 == 0)."""
    k = (date.fromisoformat(d) - date.fromisoformat(CA.EPOCH)).days % 7
    return _add(d, 7 - k)


def th_sha(cfg):
    """The rule's fingerprint: a change of any threshold restarts the accept trial (old asks are not compared)."""
    raw = json.dumps({"rule": RULE, "TH": TH, "PERSIST": PERSIST, "move_bands": cfg["move_bands"],
                      "engine_band": cfg["engine_band"]}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


# ── an entity as known on day d, and the window arithmetic ──────────────────────────────────────────────────────────

def cut(e, d):
    """The entity as it was known on day d (ISO): cells after d dropped, cells in (d − LAGS[k], d] → None (not matured
    yet). Every series ends exactly on d."""
    P = _ix(e, d)
    n = P + 1
    s = {}
    for k, v in e.s.items():
        if n <= 0:
            s[k] = []
            continue
        x = list(v[:n]) + [None] * max(0, n - len(v))
        for i in range(max(0, P - LAGS.get(k, 0) + 1), n):
            x[i] = None
        s[k] = x
    return CA.Ent(e.kind, e.id, e.app, e.label, e.day0, s)


def _unit(e, d, P):
    """(id, the entity cut at d, its _Ser) — None when it has no day on or before d."""
    c = cut(e, d)
    n = _ix(c, d) + 1
    if n <= 0:
        return None
    return (e.id, c, CA._Ser(c, n, P))


def _sum(e, k, w):
    """Σ of the known cells of e.s[k] over the ISO window w (the entity's own index); None: no such series."""
    v = e.s.get(k)
    if v is None:
        return None
    a, b = max(_ix(e, w[0]), 0), min(_ix(e, w[1]), len(v) - 1)
    if b < a:
        return 0.0
    return math.fsum(x for x in v[a:b + 1] if x is not None)


def _v(ser, fam, a, b):
    if a < 0 or b < a:
        return None
    return ser.value(fam, a, b) if ser.applicable(fam) else None


def _val(u, fam, w):
    """The family value over the ISO window w on one unit (id, entity, _Ser): None when thin (the engine's gates)."""
    return _v(u[2], fam, _ix(u[1], w[0]), _ix(u[1], w[1]))


def ratio_split(units, num, den, gate_fam, w0, w1, totals=None):
    """Shift-share of R = Σnum ÷ Σden between the windows w0 and w1: the rate part = Σ_j w0_j·(r1_j − r0_j) over the
    units measurable in both windows by the engine's gate of gate_fam, the rest (weights, units new / stopped / thin,
    the 'rest' of totals) is the mix. → {"rate_share", "units_measured"} or None (no denominator in a window)."""
    rows = []
    for u in units:
        e = u[1]
        n0, d0 = (_sum(e, num, w0) or 0.0), (_sum(e, den, w0) or 0.0)
        n1, d1 = (_sum(e, num, w1) or 0.0), (_sum(e, den, w1) or 0.0)
        ok = _val(u, gate_fam, w0) is not None and _val(u, gate_fam, w1) is not None
        rows.append([n0, d0, n1, d1, ok])
    if totals is not None:
        if any(x is None for x in totals):
            return None
        N0, D0, N1, D1 = totals
        rows.append([N0 - math.fsum(r[0] for r in rows), D0 - math.fsum(r[1] for r in rows),
                     N1 - math.fsum(r[2] for r in rows), D1 - math.fsum(r[3] for r in rows), False])
    else:
        N0, D0 = math.fsum(r[0] for r in rows), math.fsum(r[1] for r in rows)
        N1, D1 = math.fsum(r[2] for r in rows), math.fsum(r[3] for r in rows)
    if not (D0 > 0 and D1 > 0):
        return None
    dR = N1 / D1 - N0 / D0
    rate = [(d0 / D0) * (n1 / d1 - n0 / d0) for n0, d0, n1, d1, ok in rows if ok and d0 > 0 and d1 > 0]
    return {"rate_share": fin(math.fsum(rate) / dR) if dR else None, "units_measured": len(rate)}


def classify(units, unit_fam, w0, w1, sp_new_total, sp_old_total, P):
    """Breadth: each unit's own move of unit_fam between the windows (the engine's gates), as shares of the app's
    new-window spend: same (worse by ≥ one band), opposite, flat, thin, no_data, new; not_listed = the app's spend
    outside the units."""
    t = band_log(unit_fam, P)
    sh = {"same": 0.0, "flat": 0.0, "opposite": 0.0, "thin": 0.0, "no_data": 0.0, "new": 0.0}
    keys = [k for k in (CA.FAMILIES[unit_fam]["num"], CA.FAMILIES[unit_fam]["den"]) if k]
    s_new_units = 0.0
    for u in units:
        e, ser = u[1], u[2]
        s0, s1 = _sum(e, "sp_usd", w0) or 0.0, _sum(e, "sp_usd", w1) or 0.0
        s_new_units += s1
        if s1 <= 0:
            continue
        if s0 <= 0:
            cls = "new"
        else:
            v0, v1 = _val(u, unit_fam, w0), _val(u, unit_fam, w1)
            idx = [(_ix(e, w[0]), min(_ix(e, w[1]), ser.n - 1)) for w in (w0, w1)]
            unk = any(k not in e.s or ser.K(k, a, b) < b - a + 1 for k in keys for a, b in idx)
            if (v0 is None or v1 is None) and unk:
                cls = "no_data"
            elif v0 is None or v1 is None:
                cls = "thin"
            else:
                lw = CA.lworse(unit_fam, v1, v0)
                cls = "same" if lw is not None and lw >= t else ("opposite" if lw is not None and lw <= -t else "flat")
        sh[cls] += s1
    out = {k: fin(v / sp_new_total) if sp_new_total else None for k, v in sh.items()}
    out["not_listed"] = fin(1.0 - s_new_units / sp_new_total) if sp_new_total else None
    return out


def _top_spend(units, w0, w1, total_old, total_new, alias):
    """The additive split of the spend per day: the unit (alias) carrying the largest part of the change and its
    share of it."""
    n0, n1 = _ndays(w0), _ndays(w1)
    rows = [[alias.get(u[0], u[0]), (_sum(u[1], "sp_usd", w0) or 0.0) / n0, (_sum(u[1], "sp_usd", w1) or 0.0) / n1]
            for u in units]
    rows.append(["rest", total_old - math.fsum(r[1] for r in rows), total_new - math.fsum(r[2] for r in rows)])
    dd = total_new - total_old
    rows.sort(key=lambda r: -abs(r[2] - r[1]))
    top = rows[0]
    return {"rows": [{"unit": top[0], "share_of_change": fin((top[2] - top[1]) / dd) if dd else None}]}


# ── the as-of-d evidence of one question ────────────────────────────────────────────────────────────────────────────

def _last_known(e, k, upto):
    """The last day ≤ upto (ISO) with a known e.s[k] cell, or None."""
    v = e.s.get(k) or []
    for i in range(min(_ix(e, upto), len(v) - 1), -1, -1):
        if v[i] is not None:
            return _iso(e.day0, i)
    return None


def _ipu_end(A, d):
    """The ads-per-user windows end at min(b, d − 1, the last day with GA4 users known)."""
    return _last_known(A, "dau", _add(d, -1))


def _ipu(A, ser, w, end):
    if end is None:
        return None
    b = min(w[1], end)
    return _v(ser, "IPU", _ix(A, w[0]), _ix(A, b))


def evidence(app, camps, ctys, ep, new_days, d, why, P):
    """The rule inputs of one question as of day d (ISO): app = the app Ent (full series; cut here), camps = its campaign
    Ents, ctys = its CANDIDATE country Ents (every geo country), ep = {"fam", "opened", "c", "base", "bspan",
    "base_src"} (ISO), new_days = the new level's [a, b], why = money / open / settle, P = the engine's P_PROD.
    Every number is read from the series cut at d; an old window ending after d or a new one ending after d − shift
    raises (no look-ahead). → the ri dict, exactly as the ledger keeps it."""
    fam = ep["fam"]
    sh = CA.FAMILIES[fam]["shift"]
    A = cut(app, d)
    Pi = _ix(A, d)
    if Pi < 0:
        raise ValueError("ask before the app's first day")
    ser = CA._Ser(A, Pi + 1, P)
    B = ep["base"]
    c = _ix(A, ep["c"])
    w0 = list(ep["bspan"]) if ep.get("bspan") else [_iso(A.day0, c - 14), _iso(A.day0, c - 1)]
    w1 = list(new_days)
    if w1[1] > _add(d, -sh) or w0[1] > d:
        raise ValueError("look-ahead")
    a0, b0, a1, b1 = (_ix(A, x) for x in (w0[0], w0[1], w1[0], w1[1]))
    new_v = _v(ser, fam, a1, b1)
    t_band = band_log(fam, P)
    V7, V14, SIG = ser.series(fam)
    e0 = Pi - sh
    fns = []
    j = 0
    while True:
        b = e0 - 14 * j
        a = b - 13
        if a < c or a < 0:
            break
        fns.append({"v": V14[b]})
        j += 1
    fns.reverse()
    tails = {}
    for nd in (56, 84):
        lo = e0 - nd + 1
        vals = [V14[b] for b in range(lo, e0 + 1)] if lo >= 0 else []
        if len(vals) == nd and all(v is not None and v > 0 for v in vals):
            s = sorted(vals)
            md = 0.5 * (s[nd // 2 - 1] + s[nd // 2])
            tails["l14_%dd" % nd] = {"max_dev": fin(max(abs(v / md - 1) for v in vals))}
        else:
            tails["l14_%dd" % nd] = None
    L14, P14, L7 = _v(ser, fam, e0 - 13, e0), _v(ser, fam, e0 - 27, e0 - 14), _v(ser, fam, e0 - 6, e0)
    trend = {"L7": {"v": L7}, "L14": {"v": L14}, "P14": {"v": P14}, "L14_vs_P14": None}
    if L14 is not None and P14 is not None and CA.lworse(fam, L14, B) is not None \
            and CA.lworse(fam, P14, B) is not None:
        trend["L14_vs_P14"] = fin(_rel(L14, P14))
    # units as of d: campaigns with spend in [old start, new end]; countries the engine's own as-of-d rule keeps
    cser = []
    for x in camps:
        u = _unit(x, d, P)
        if u is not None and (_sum(u[1], "sp_usd", [w0[0], w1[1]]) or 0) > 0:
            cser.append(u)
    tser, cfr = [], None
    elig = P.get("country_elig")
    for x in ctys:
        u = _unit(x, d, P)
        if u is None:
            continue
        f = next((i for i, v in enumerate(u[1].s.get("imp") or []) if v is not None), None)
        if f is not None:
            fd = _iso(u[1].day0, f)
            cfr = fd if cfr is None or fd < cfr else cfr
        if not elig or CA._country_ok(u[1], u[2].n, {A.id: A}, elig, d):
            tser.append((x.id.split("|")[-1], u[1], u[2]))
    sp_old, sp_new = _sum(A, "sp_usd", w0) or 0.0, _sum(A, "sp_usd", w1) or 0.0
    rank = sorted(cser, key=lambda u: -(_sum(u[1], "sp_usd", w1) or 0))
    alias = {u[0]: "C%d" % (i + 1) for i, u in enumerate(rank)}
    alias["rest"] = "rest"
    end = _ipu_end(A, d)
    drivers, breadth = {}, {}
    if fam in CA.MONEY_FAMS:
        num, cost = ("d0_inr", "sp_inr") if fam == "ROAS_G" else (CA.FAMILIES[fam]["num"], "c_sp")
        sides = {}
        for tag, w in (("old", w0), ("new", w1)):
            s = {k: _sum(A, k, w) for k in (num, cost, "inst")}
            sides[tag] = {"roas": s[num] / s[cost] if s[num] is not None and s[cost] else None,
                          "vpi": s[num] / s["inst"] if s[num] is not None and s["inst"] else None,
                          "cpi": s[cost] / s["inst"] if s[cost] is not None and s["inst"] else None}
        o, n_ = sides["old"], sides["new"]
        rs = {"share_of_move": None, "dlog": None}
        if all(x and x > 0 for x in (o["roas"], n_["roas"], o["vpi"], n_["vpi"], o["cpi"], n_["cpi"])):
            dr, dv, dc = (math.log(n_["roas"] / o["roas"]), math.log(n_["vpi"] / o["vpi"]),
                          math.log(n_["cpi"] / o["cpi"]))
            rs["dlog"] = {"roas": fin(dr), "value_per_install": fin(dv), "cost_per_install": fin(dc)}
            rs["share_of_move"] = {"value_per_install": fin(dv / dr) if dr else None,
                                   "cost_per_install": fin(-dc / dr) if dr else None}
        drivers["roas_split"] = rs
        inside = {tag: {"ecpm": _v(ser, "ECPM", _ix(A, w[0]), _ix(A, w[1])), "ipu": _ipu(A, ser, w, end)}
                  for tag, w in (("old", w0), ("new", w1))}
        drivers["inside_value"] = {"ecpm_move": fin(_rel(inside["new"]["ecpm"], inside["old"]["ecpm"])),
                                   "ipu_move": fin(_rel(inside["new"]["ipu"], inside["old"]["ipu"]))}
        units = [u for u in cser if "d0_inr" in u[1].s]
        tot = (_sum(A, "d0_inr", w0), _sum(A, "sp_inr", w0), _sum(A, "d0_inr", w1), _sum(A, "sp_inr", w1))
        cr = ratio_split(units, "d0_inr", "sp_inr", "ROAS_G", w0, w1, totals=tot)
        drivers["campaigns_roas_g"] = {"rate_share": cr["rate_share"]} if cr else None
        br = classify(tser, "CPI", w0, w1, sp_new, sp_old, P)
        breadth["countries_cpi"] = {k: br[k] for k in ("same", "opposite", "not_listed")}
    elif fam == "CPI":
        tot = (_sum(A, "sp_inr", w0), _sum(A, "inst", w0), _sum(A, "sp_inr", w1), _sum(A, "inst", w1))
        cr = ratio_split(cser, "sp_inr", "inst", "CPI", w0, w1, totals=tot)
        drivers["campaigns_cpi_inr"] = {"rate_share": cr["rate_share"]} if cr else None
        br = classify(cser, "CPI", w0, w1, sp_new, sp_old, P)
        breadth["campaigns"] = {k: br[k] for k in ("same", "opposite")}
    elif fam == "ECPM":
        te = [u for u in tser if "imp" in u[1].s]
        cty = ratio_split(te, "rev", "imp", "ECPM", w0, w1) if (cfr is not None and w0[0] >= cfr) else None
        drivers["countries_ecpm_gross"] = cty
        ipo, ipn = _ipu(A, ser, w0, end), _ipu(A, ser, w1, end)
        drivers["ipu"] = {"move": fin(_rel(ipn, ipo))}
    elif fam == "GAP":
        sides = {}
        for tag, w in (("old", w0), ("new", w1)):
            s = {k: _sum(A, k, w) for k in ("sp_inr", "sp_usd", "inst", "imp", "rev")}
            ok = all(s[k] is not None and s[k] > 0 for k in s)
            sides[tag] = {"cpi_inr": s["sp_inr"] / s["inst"], "usd_per_inr": s["sp_usd"] / s["sp_inr"],
                          "ecpm": s["rev"] / s["imp"] * 1000.0,
                          "gap": (s["sp_usd"] / s["inst"]) * (s["imp"] / s["rev"])} if ok else None
        o, n_ = sides["old"], sides["new"]
        gs = {"share_of_move": None, "dlog": None}
        if o and n_:
            dg, d1_, d2_, d3_ = (math.log(n_["gap"] / o["gap"]), math.log(n_["cpi_inr"] / o["cpi_inr"]),
                                 math.log(n_["usd_per_inr"] / o["usd_per_inr"]), math.log(n_["ecpm"] / o["ecpm"]))
            gs["dlog"] = {"gap": fin(dg), "cpi_inr": fin(d1_), "fx": fin(d2_), "ecpm": fin(-d3_)}
            if dg:
                gs["share_of_move"] = {"cpi_inr": fin(d1_ / dg), "fx": fin(d2_ / dg), "ecpm": fin(-d3_ / dg)}
        drivers["gap_split"] = gs
        tot = (_sum(A, "sp_inr", w0), _sum(A, "inst", w0), _sum(A, "sp_inr", w1), _sum(A, "inst", w1))
        cr = ratio_split(cser, "sp_inr", "inst", "CPI", w0, w1, totals=tot)
        drivers["campaigns_cpi_inr"] = {"rate_share": cr["rate_share"]} if cr else None
        te = [u for u in tser if "imp" in u[1].s]
        drivers["countries_ecpm_gross"] = ratio_split(te, "rev", "imp", "ECPM", w0, w1) \
            if (cfr is not None and w0[0] >= cfr) else None
        br = classify(cser, "CPI", w0, w1, sp_new, sp_old, P)
        breadth["campaigns_cpi"] = {k: br[k] for k in ("same", "opposite")}
    elif fam == "SPEND":
        n0, n1 = b0 - a0 + 1, b1 - a1 + 1
        drivers["campaigns_spend"] = _top_spend(cser, w0, w1, sp_old / n0, sp_new / n1, alias)
    # the same old / new windows one and two years earlier (364 / 728 days: the same weekday)
    seas = []
    for L in SEASON:
        v0, v1 = _v(ser, fam, a0 - L, b0 - L), _v(ser, fam, a1 - L, b1 - L)
        if v0 is None or v1 is None or v0 <= 0 or v1 <= 0:
            seas.append({"lag_days": L, "available": False, "similar": None, "analog": None})
            continue
        mv = CA.lworse(fam, v1, v0)
        back = [(k, _v(ser, fam, b1 - L + k - 27, b1 - L + k)) for k in CHECKS]
        lab = label(fam, v0, v1, back, P)
        seas.append({"lag_days": L, "available": True, "similar": bool(mv is not None and mv >= t_band),
                     "analog": {"label": lab["label"], "label_last": lab["last"],
                                "first_recovered_at": lab["first_back"]}})
    n0, n1 = b0 - a0 + 1, b1 - a1 + 1
    old_c = {u[0] for u in cser if (_sum(u[1], "sp_usd", w0) or 0) > 0}
    new_c = {u[0] for u in cser if (_sum(u[1], "sp_usd", w1) or 0) > 0}
    ctx = {"spend_usd_per_day": {"move": fin(_rel(sp_new / n1, sp_old / n0))},
           "campaigns": {"spend_share_new_of_campaigns_not_in_old": fin(math.fsum(
               _sum(u[1], "sp_usd", w1) or 0 for u in cser if u[0] in new_c - old_c) / sp_new) if sp_new else None,
               "spend_share_old_of_campaigns_gone": fin(math.fsum(
                   _sum(u[1], "sp_usd", w0) or 0 for u in cser if u[0] in old_c - new_c) / sp_old) if sp_old else None}}
    move_log = CA.lworse(fam, new_v, B)
    ri = {"v": 1, "fam": fam, "why": why, "app": app.id, "d": d, "ep": {"opened": ep["opened"], "c": ep["c"]},
          "old": {"days": w0, "v": B}, "new": {"days": w1, "v": new_v},
          "move": {"rel": fin(_rel(new_v, B)), "worse_log": fin(move_log), "band_rel": band(fam, P),
                   "band_log": fin(t_band), "noise_daily_log": fin(SIG[Pi])},
          "alarm": {"days_since_change": e0 - c}, "trend": trend,
          "steadiness": dict({"fortnights_since_change": fns}, **tails), "seasonality": seas,
          "context": ctx, "drivers": drivers, "breadth": breadth}
    return frozen(ri)


def market(ri, app, others, th=TH):
    """The other apps' eCPM and CPI moves over the question's own two windows (both end on or before d), and the own
    app's ads per user and eCPM over them. Plain ratios of sums (unknown cells skipped); an app counts when it has
    ≥ mkt_imp impressions (eCPM) / ≥ mkt_inst installs (CPI) a day in both windows; the own app never counts."""
    o, nw, d = ri["old"]["days"], ri["new"]["days"], ri["d"]
    if o[1] > d or nw[1] > d:
        raise ValueError("look-ahead")
    n0, n1 = _ndays(o), _ndays(nw)
    out = {}
    for fam, num, den, floor in (("ecpm", "rev", "imp", th["mkt_imp"]), ("cpi", "sp_inr", "inst", th["mkt_inst"])):
        mv = []
        for e in others:
            if e.id == app.id or e.kind != "app":
                continue
            d0, d1 = _sum(e, den, o) or 0.0, _sum(e, den, nw) or 0.0
            u0, u1 = _sum(e, num, o) or 0.0, _sum(e, num, nw) or 0.0
            if d0 / n0 < floor or d1 / n1 < floor or u0 <= 0 or u1 <= 0:
                continue
            mv.append(round((u1 / d1) / (u0 / d0) - 1.0, 6))
        out[fam] = {"n": len(mv), "median": statistics.median(mv) if mv else None, "moves": sorted(mv)}
    A = cut(app, d)
    own = {}
    for k, (num, den), cap in (("ipu", ("imp", "dau"), _ipu_end(A, d)), ("ecpm", ("rev", "imp"), d)):
        if cap is None:
            own[k] = None
            continue
        e_0, e_1 = [o[0], min(o[1], cap)], [nw[0], min(nw[1], cap)]
        d0, d1 = (_sum(A, den, e_0) or 0.0) if e_0[1] >= e_0[0] else 0.0, \
            (_sum(A, den, e_1) or 0.0) if e_1[1] >= e_1[0] else 0.0
        u0, u1 = (_sum(A, num, e_0) or 0.0) if e_0[1] >= e_0[0] else 0.0, \
            (_sum(A, num, e_1) or 0.0) if e_1[1] >= e_1[0] else 0.0
        own[k] = (u1 / d1) / (u0 / d0) - 1.0 if min(d0, d1, u0, u1) > 0 else None
    out["own"] = own
    return frozen(out)


# ── hindsight words: a label of later values, the verdict, the revert tests ─────────────────────────────────────────

def label(fam, old, new, vals, P):
    """vals = [(k, value)]: recovered (some value not worse than OLD by more than one band), stayed (every known value
    not better than NEW by more than one band; worse counts as stayed), partial (in between), unknown (< 2 known and
    none recovered). → {"label", "last" (the same word for the last known value), "first_back" (its k)}."""
    t = band_log(fam, P)
    g = CA.lworse(fam, new, old)
    known = [(k, CA.lworse(fam, v, old)) for k, v in vals if v is not None]
    known = [(k, s) for k, s in known if s is not None]
    rec = [k for k, s in known if s <= t]
    if rec:
        lab = "recovered"
    elif len(known) < 2:
        lab = "unknown"
    elif g is not None and all(s >= g - t for _, s in known):
        lab = "stayed"
    else:
        lab = "partial"
    last = None
    if known:
        s = known[-1][1]
        last = "recovered" if s <= t else ("stayed" if g is not None and s >= g - t else "partial")
    return {"label": lab, "last": last, "first_back": rec[0] if rec else None}


def verdict(dec, lab):
    """accept → right (the level stayed) / wrong (it came back, and its last value too) / unclear; keep or wait →
    stayed / came_back / unclear."""
    stayed = lab["label"] == "stayed"
    back = lab["label"] == "recovered" and lab["last"] == "recovered"
    if dec == "accept":
        return "right" if stayed else ("wrong" if back else "unclear")
    return "stayed" if stayed else ("came_back" if back else "unclear")


def back_at_old(fam, v, old, P):
    """v is back within one band of the OLD level (or better than it): True / False; None when v or old is unknown."""
    if v is None or old is None or v <= 0 or old <= 0:
        return None
    return CA.lworse(fam, v, old) <= band_log(fam, P)


def revert_due(checks, cfg):
    """R2: checks = [(k, back)] for k = 28, 35 … 84 days after an acceptance → the first k with `need` checks in a row
    back at the old level inside [from, days] (two in a row: k ≥ 35 with back(k) and back(k − 7)), else None."""
    net = cfg["net"]
    got = dict(checks)
    for k in sorted(got):
        if k > net["days"] or k - net["every"] * (net["need"] - 1) < net["from"]:
            continue
        if all(got.get(k - net["every"] * j) is True for j in range(net["need"])):
            return k
    return None


# ── persistence (the guard of every accept outside the measured eCPM-market branch) ─────────────────────────────────

def _worse(fam, v, ref):
    if v is None or ref is None or v <= 0 or ref <= 0:
        return None
    x = math.log(v / ref)
    return x if fam in ("CPI", "GAP") else -x


def _features(ri):
    fam = ri["fam"]
    old, new = ri["old"]["v"], ri["new"]["v"]
    bl = ri["move"]["band_log"]
    g = _worse(fam, new, old)

    def vb(v):                                     # bands worse than the NEW level (negative: back toward old)
        w = _worse(fam, v, old)
        return None if (w is None or g is None) else (w - g) / bl
    tr = ri["trend"]
    st = ri["steadiness"]
    sea = []
    for s in ri["seasonality"]:
        if s.get("available"):
            a = s.get("analog") or {}
            sea.append({"lag": s["lag_days"], "similar": bool(s.get("similar")), "label": a.get("label")})
    nz = ri["move"].get("noise_daily_log")
    return {"move_bands": None if g is None else g / bl,
            "fn_bands": [vb(f["v"]) for f in st["fortnights_since_change"]],
            "L7": vb(_g(tr, "L7", "v")), "L14": vb(_g(tr, "L14", "v")), "P14": vb(_g(tr, "P14", "v")),
            "l14_56d": _g(st, "l14_56d", "max_dev"), "l14_84d": _g(st, "l14_84d", "max_dev"),
            "noise28_bands": None if nz is None else nz / math.sqrt(28.0) / bl, "seasonality": sea,
            "days_since_change": ri["alarm"]["days_since_change"]}


def persist(ri, pp=PERSIST):
    """The persistence rule: keep K1 (a year earlier the same move came back) / K2 (returning toward the old level);
    accept when A1–A7 all hold; else wait on the first failed test. → {"decision", "first" (K1 / K2 / A1 … A7 or
    None), "value", "need", "move_bands"}."""
    f = _features(ri)
    mb = f["move_bands"]
    back = [s for s in f["seasonality"] if s["similar"] and s["label"] == "recovered"]
    if back:
        return {"decision": "keep", "first": "K1", "value": back[0]["lag"], "need": None, "move_bands": mb}
    if f["L14"] is not None and f["P14"] is not None and f["L14"] < -pp["keep_return_bands"] and f["L14"] < f["P14"]:
        return {"decision": "keep", "first": "K2", "value": round(-f["L14"], 2), "need": pp["keep_return_bands"],
                "move_bands": mb}
    n = pp["n_fn_full"]
    last = f["fn_bands"][-n:]
    sd = f["l14_56d"] if pp["steady_days"] == 56 else f["l14_84d"]
    h = list(f["fn_bands"][-pp["n_fn_hold"]:]) + [f["L7"]]
    hm = None if any(x is None for x in h) or len(f["fn_bands"]) < pp["n_fn_hold"] else min(h)
    ret = None if f["L14"] is None or f["P14"] is None else f["P14"] - f["L14"]
    nz = f["noise28_bands"]
    tests = (("A1", len(last) >= n and all(x is not None for x in last), sum(x is not None for x in last), n),
             ("A2", mb is not None and mb >= pp["min_move_bands"], None if mb is None else round(mb, 2),
              pp["min_move_bands"]),
             ("A3", sd is not None and sd <= pp["steady_dev"], sd, pp["steady_dev"]),
             ("A4", hm is not None and hm >= -pp["hold_bands"], None if hm is None else round(hm, 2), -pp["hold_bands"]),
             ("A5", ret is not None and ret <= pp["ret_bands"], None if ret is None else round(ret, 2), pp["ret_bands"]),
             ("A6", nz is not None and nz <= pp["noise_frac"], None if nz is None else round(nz, 3), pp["noise_frac"]),
             ("A7", f["days_since_change"] >= pp["min_days_since_change"], f["days_since_change"],
              pp["min_days_since_change"]))
    for code, ok, v, need in tests:
        if not ok:
            return {"decision": "wait", "first": code, "value": v, "need": need, "move_bands": mb}
    return {"decision": "accept", "first": None, "value": None, "need": None, "move_bands": mb}


def _pf_words(ps, pp):
    c, v = ps["first"], ps["value"]
    if c == "A1":
        return "a fortnight without a value in the last %d weeks" % (2 * pp["n_fn_full"])
    if c == "A2":
        return "the move is under %g bands" % pp["min_move_bands"]
    if c == "A3":
        if v is None:
            return "the 14-day level is not known on every one of the last %d days" % pp["steady_days"]
        return "the 14-day level up to %.0f%% off its %d-day median (needs %.0f%%)" % (100 * v, pp["steady_days"],
                                                                                    100 * pp["steady_dev"])
    if c == "A4":
        return "a recent fortnight is back toward the old level"
    if c == "A5":
        return "the last 14 days moved back toward the old level"
    if c == "A6":
        return "too noisy to tell old from new in 28 days"
    if c == "A7":
        return "the change started %s days ago (needs %d)" % (v, pp["min_days_since_change"])
    if c == "K1":
        return "a year earlier the same move came back (seasonal)"
    return "returning toward the old level"


# ── C1: the cause trees, the external tests, the agent's own tests ──────────────────────────────────────────────────

def _pc(x):
    return "?" if x is None else "%+.0f%%" % (100 * x)


def _sh(x):
    return "?" if x is None else "%.0f%%" % (100 * x)


def _mx(x):
    return "×%.1f" % x


def _mkt_same(m, own, band_rel, th):
    """(the other apps moved the same way, the words): ≥ mkt_n apps with data, their median ≥ mkt_frac × the own move
    (same sign), ≥ mkt_share of them beyond the band."""
    if not m or m["n"] < th["mkt_n"] or m["median"] is None or own is None or own == 0:
        return False, "%d other apps with data (needs %d)" % ((m or {}).get("n", 0), th["mkt_n"])
    sgn = 1 if own > 0 else -1
    share = sum(1 for x in m["moves"] if x * sgn > band_rel) / m["n"]
    ok = m["median"] * sgn >= th["mkt_frac"] * abs(own) and share >= th["mkt_share"]
    return ok, "%d other apps: median %s vs own %s, %.0f%% moved the same way" % (m["n"], _pc(m["median"]), _pc(own),
                                                                                  100 * share)


def _scale(ri):
    sp = _g(ri, "context", "spend_usd_per_day", "move")
    return None if sp is None or sp <= -1 else math.log1p(sp)


def _turn(ri):
    c = _g(ri, "context", "campaigns") or {}
    return max(c.get("spend_share_new_of_campaigns_not_in_old") or 0.0,
               c.get("spend_share_old_of_campaigns_gone") or 0.0)


def _r(v, branch, cause, short, mkt=None):
    return {"v": v, "branch": branch, "cause": cause, "short": short, "mkt": mkt}


def _cpi_tree(ri, mkt, th, own, rate_share, br, units):
    sc = _scale(ri)
    if sc is not None and abs(sc) >= th["scale"]:
        x = _mx(math.exp(sc))
        return _r("keep", "spend_scaled", "seen with spend %s since the old level (your lever)" % x,
                  "spend %s (your lever)" % x)
    tu = _turn(ri)
    if tu >= th["turn"]:
        return _r("keep", "campaign_mix", "seen with %s of spend in campaigns new since / gone after the old level"
                  % _sh(tu), "campaign mix %s" % _sh(tu))
    if rate_share is not None and rate_share < th["rate_min"]:
        return _r("keep", "mix", "only %s of the move is inside campaigns — the rest is the campaign mix"
                  % _sh(max(rate_share, 0)), "campaign mix")
    if br is not None:
        same, opp = br.get("same") or 0.0, br.get("opposite") or 0.0
        if same < th["broad"] or opp > th["opp_max"]:
            return _r("wait", "narrow", "narrow: %s moving the same way = %s of spend (opposite %s)"
                      % (units, _sh(same), _sh(opp)), "narrow: %s %s" % (units, _sh(same)))
    ok, txt = _mkt_same(mkt.get("cpi"), own, _CPI_BAND, th)
    if not ok:
        return _r("keep", "own_campaigns", "other apps' CPI did not move the same way (%s) — own campaigns only "
                  "(bid / target / creative)" % txt, "own campaigns only", txt)
    return _r("external", "cpi_market", "other apps' CPI moved the same way (%s)" % txt, "CPI market move", txt)


def _ecpm_tree(ri, mkt, th, own, ipu, cty):
    ok, txt = _mkt_same(mkt.get("ecpm"), own, _ECPM_BAND, th)
    if ipu is not None and abs(ipu) >= th["ipu_side"]:
        return _r("keep", "app_side", "seen with ads per user %s and eCPM %s (app side)" % (_pc(ipu), _pc(own)),
                  "ads per user %s" % _pc(ipu))
    if ok:
        if cty is not None and cty.get("rate_share") is not None and cty.get("units_measured") \
                and cty["rate_share"] < th["rate_min"]:
            return _r("keep", "country_mix", "only %s of the eCPM move is inside countries — the rest is the country "
                      "mix" % _sh(max(cty["rate_share"], 0)), "country mix", txt)
        if ipu is None:
            return _r("wait", "ipu_unknown", "eCPM moved with other apps (%s) but ads per user is not measurable" % txt,
                      "ads per user unknown", txt)
        return _r("external", "ecpm_market", "other apps' eCPM moved the same way (%s); ads per user %s"
                  % (txt, _pc(ipu)), "eCPM market move", txt)
    tu, sc = _turn(ri), _scale(ri)
    if tu >= th["turn"]:
        return _r("keep", "user_mix", "seen with %s of spend in new / gone campaigns; eCPM not a market move (%s)"
                  % (_sh(tu), txt), "user mix", txt)
    if sc is not None and abs(sc) >= th["scale"]:
        return _r("keep", "user_mix", "seen with spend %s; eCPM not a market move (%s)" % (_mx(math.exp(sc)), txt),
                  "user mix", txt)
    return _r("wait", "app_only", "eCPM moved on this app only — the cause is not in the data (ad sources / mediation "
              "/ units)", "app only", txt)


def _join(parts, shares):
    """The CPI part and the eCPM part (in that order): keep if any keeps, else wait if any waits, else external; the
    part named is the first with the joined answer (both external: "parts_external", no part)."""
    vs = [p["v"] for _, p in parts]
    v = "keep" if "keep" in vs else ("wait" if "wait" in vs else "external")
    cause = "; ".join("%s part %s of the move: %s" % ("CPI" if k == "cpi" else "eCPM", _sh(shares.get(k)), p["cause"])
                      for k, p in parts)
    if v == "external" and len(parts) == 2:
        out = _r("external", "parts_external", "both parts moved with other apps: %s; %s"
                 % (parts[0][1]["mkt"], parts[1][1]["mkt"]), "market move")
        out["part"] = None
        return out
    k, p = next((k, p) for k, p in parts if p["v"] == v)
    out = _r(v, p["branch"], cause, p["short"], p["mkt"])
    out["part"] = k
    return out


def _cause(ri, mkt, th):
    fam = ri["fam"]
    d, b = ri["drivers"], ri["breadth"]
    out = None
    if fam == "SPEND":
        rows = _g(d, "campaigns_spend", "rows") or []
        top = rows[0] if rows else {}
        out = _r("keep", "spend", "budget / bid limit (your lever): spend %s, campaign %s carries %s of the change"
                 % (_pc(ri["move"]["rel"]), top.get("unit", "?"), _sh(top.get("share_of_change") or 0)),
                 "budget (your lever)")
    elif fam == "IPU":
        out = _r("keep", "ipu", "app side: ads per user %s (placements / frequency / app version)"
                 % _pc(ri["move"]["rel"]), "ads per user %s" % _pc(ri["move"]["rel"]))
    elif fam == "CPI":
        out = _cpi_tree(ri, mkt, th, ri["move"]["rel"], _g(d, "campaigns_cpi_inr", "rate_share"), b.get("campaigns"),
                        "campaigns")
    elif fam == "ECPM":
        out = _ecpm_tree(ri, mkt, th, ri["move"]["rel"], _g(d, "ipu", "move"), d.get("countries_ecpm_gross"))
    elif fam == "GAP":
        sh = _g(d, "gap_split", "share_of_move") or {}
        dl = _g(d, "gap_split", "dlog") or {}
        parts = []
        if (sh.get("cpi_inr") or 0) >= th["dom"] or (sh.get("ecpm") or 0) < th["dom"]:
            parts.append(("cpi", _cpi_tree(ri, mkt, th, math.expm1(dl["cpi_inr"]) if dl.get("cpi_inr") is not None
                                           else None, _g(d, "campaigns_cpi_inr", "rate_share"),
                                           b.get("campaigns_cpi"), "campaigns")))
        if (sh.get("ecpm") or 0) >= th["dom"] or (sh.get("cpi_inr") or 0) < th["dom"]:
            em = math.expm1(-dl["ecpm"]) if dl.get("ecpm") is not None else None   # dlog ecpm is the GAP-side log
            parts.append(("ecpm", _ecpm_tree(ri, mkt, th, em, (mkt.get("own") or {}).get("ipu"),
                                             d.get("countries_ecpm_gross"))))
        return _join(parts, {"cpi": sh.get("cpi_inr"), "ecpm": sh.get("ecpm")})
    elif fam in CA.MONEY_FAMS:
        sh = _g(d, "roas_split", "share_of_move") or {}
        dl = _g(d, "roas_split", "dlog") or {}
        cs, vs = sh.get("cost_per_install"), sh.get("value_per_install")
        if cs is None or vs is None:
            out = _r("wait", "no_split", "too thin: no cost–value split for these days", "too thin")
        else:
            parts = []
            if cs >= th["dom"] or vs < th["dom"]:
                br = dict(b.get("countries_cpi") or {})
                parts.append(("cpi", _cpi_tree(ri, mkt, th, math.expm1(dl["cost_per_install"]),
                                               _g(d, "campaigns_roas_g", "rate_share"), br or None, "countries")))
            if vs >= th["dom"] or cs < th["dom"]:
                parts.append(("ecpm", _ecpm_tree(ri, mkt, th, _g(d, "inside_value", "ecpm_move"),
                                                 _g(d, "inside_value", "ipu_move"), None)))
            return _join(parts, {"cpi": cs, "ecpm": vs})
    if out is None:
        out = _r("wait", "thin", "too thin: no 14-day trend or level value yet", "too thin")
    out["part"] = None
    return out


def _c1(ri, mkt, th):
    """The cause rule: thin → cause → (external only) coming back / still moving / not steady → accept."""
    tr = ri.get("trend") or {}
    if ri["old"].get("v") is None or ri["new"].get("v") is None or _g(tr, "L14", "v") is None \
            or tr.get("L14_vs_P14") is None:
        return {"dec": "wait", "branch": "thin", "part": None, "ext": None, "ext_branch": None,
                "cause": "too thin: no 14-day trend or level value yet", "short": "too thin", "steps": []}
    c = _cause(ri, mkt, th)
    steps = [c["cause"]]
    base = {"part": c["part"], "steps": steps}
    if c["v"] in ("keep", "wait"):
        return dict(base, dec=c["v"], branch=c["branch"], ext=None, ext_branch=None, cause=c["cause"], short=c["short"])
    ext = dict(base, ext=c["cause"], ext_branch=c["branch"])
    lv = tr["L14_vs_P14"]
    w = CA.FAMILIES[ri["fam"]]["bad"] * lv              # > 0: the last 14 days got worse than the 14 before
    br = ri["move"]["band_rel"]
    steps.append("last 14 days %s vs the 14 before (band %s)" % (_pc(lv), _pc(br)))
    if w < -th["k_back"] * br:
        return dict(ext, dec="wait", branch="coming_back", cause="%s; but coming back: last 14 days %s vs the 14 before"
                    % (c["cause"], _pc(lv)), short="coming back")
    if w > th["k_slide"] * br:
        return dict(ext, dec="wait", branch="still_sliding", cause="%s; but still moving: last 14 days %s vs the 14 "
                    "before" % (c["cause"], _pc(lv)), short="still moving")
    st = _g(ri, "steadiness", "l14_56d", "max_dev")
    if st is None or st > th["steady"]:
        return dict(ext, dec="wait", branch="not_steady", cause="%s; but not steady: the 14-day level up to %s off its "
                    "56-day median" % (c["cause"], _sh(st)), short="not steady")
    return dict(ext, dec="accept", branch=c["branch"], cause=c["cause"], short=c["short"])


def decide(ri, mkt, cfg, flags=None, th=TH, pp=PERSIST):
    """One answer from the frozen rule inputs (ri, mkt; nothing else is read) → {"decision": accept / keep / wait,
    "branch", "part", "cause", "short", "persist", "measured", "steps"}. A C1 accept passes the agent's own tests, in
    this order: never a money level (money_guard), never an alarm the agent reverted (reverted_before), a move of
    ≥ move_bands bands with the new value outside one band of the old (small_move), the engine's settle steadiness on
    the measured eCPM-market branch (engine_steady), the persistence rule's accept on every other branch
    (unmeasured)."""
    c1 = _c1(ri, mkt, th)
    ps = persist(ri, pp)
    fam = ri["fam"]
    measured = fam == "ECPM" and c1["ext_branch"] == "ecpm_market" and c1["part"] is None
    dec, branch, cause, short = c1["dec"], c1["branch"], c1["cause"], c1["short"]
    if dec == "accept":
        ext = c1["ext"]
        wl, bl = ri["move"]["worse_log"], ri["move"]["band_log"]
        bands = wl / bl if (wl is not None and bl) else None
        st = _g(ri, "steadiness", "l14_56d", "max_dev")
        nv, ov = ri["new"]["v"], ri["old"]["v"]
        lw = CA.lworse(fam, nv, ov) if (nv and ov and nv > 0 and ov > 0) else None    # vs ri's own band: never P_PROD
        if fam in CA.MONEY_FAMS:
            dec, branch = "wait", "money_guard"
            cause, short = "%s; money level — the agent never lowers it (you can accept it)" % ext, "money: only you"
        elif (flags or {}).get("reverted"):
            dec, branch = "wait", "reverted_before"
            cause = "the agent reverted its own accept on this alarm — only you can accept now"
            short = "only you"
        elif bands is None or bands < cfg["move_bands"] or lw is None or lw <= bl:
            dec, branch = "wait", "small_move"
            cause = "%s; but the move is %s bands (needs %.1f) or the last 28 days are back near the old level" % (
                ext, "?" if bands is None else "%.1f" % bands, cfg["move_bands"])
            short = "small move"
        elif measured and (st is None or st > cfg["engine_band"]):
            dec, branch = "wait", "engine_steady"
            cause = "%s; but not steady by the engine's own test: up to %s off its 56-day median (needs %.0f%%)" % (
                ext, _sh(st), 100 * cfg["engine_band"])
            short = "not steady"
        elif not measured and ps["decision"] != "accept":
            dec, branch = "wait", "unmeasured"
            cause = "%s; this kind of move has no measured case yet — %s" % (ext, _pf_words(ps, pp))
            short = "not measured yet"
    return {"decision": dec, "branch": branch, "part": c1["part"], "cause": cause, "short": short, "persist": ps,
            "measured": measured, "steps": list(c1["steps"])}


def key_numbers(ri, mkt, out):
    """The ask's key numbers for the page's detail line (numbers only, ≤ 16; None left out): old → new, the move and
    its bands, last 14 vs the 14 before, steadiness, spend multiplier, campaign turnover, the deciding part's rate
    share / breadth / ads per user / market, the GAP or money shares, the persistence test that failed first."""
    fam, d, b = ri["fam"], ri["drivers"], ri["breadth"]
    wl, bl = ri["move"]["worse_log"], ri["move"]["band_log"]
    sp = _g(ri, "context", "spend_usd_per_day", "move")
    part = out.get("part")
    cpi_side = fam == "CPI" or (fam in CA.MONEY_FAMS + ("GAP",) and part != "ecpm")
    k = [("old", ri["old"]["v"]), ("new", ri["new"]["v"]), ("mv", ri["move"]["rel"]),
         ("bands", fin(wl / bl, 2) if (wl is not None and bl) else None), ("l14p14", ri["trend"].get("L14_vs_P14")),
         ("st56", _g(ri, "steadiness", "l14_56d", "max_dev")), ("spx", fin(1.0 + sp) if sp is not None else None)]
    mk = None if fam in ("SPEND", "IPU") else (mkt.get("cpi") if (cpi_side and fam != "ECPM") else mkt.get("ecpm"))
    own = ri["move"]["rel"] if fam in ("CPI", "ECPM") else None
    k += [("mkt_n", (mk or {}).get("n")), ("mkt_med", (mk or {}).get("median")), ("own", own)]
    if fam in CA.MONEY_FAMS:
        sh = _g(d, "roas_split", "share_of_move") or {}
        k += [("cost", sh.get("cost_per_install")), ("val", sh.get("value_per_install"))]
    elif fam == "GAP":
        sh = _g(d, "gap_split", "share_of_move") or {}
        k += [("cpi", sh.get("cpi_inr")), ("ecpm", sh.get("ecpm"))]
    if fam in ("CPI", "GAP") or (fam in CA.MONEY_FAMS and part != "ecpm"):
        units = b.get("campaigns") or b.get("campaigns_cpi") or b.get("countries_cpi") or {}
        rate = _g(d, "campaigns_cpi_inr", "rate_share") if fam in ("CPI", "GAP") else _g(d, "campaigns_roas_g",
                                                                                         "rate_share")
        k += [("rate", rate), ("same", units.get("same")), ("opp", units.get("opposite")),
              ("nl", units.get("not_listed"))]
    if fam == "ECPM" or (fam in CA.MONEY_FAMS + ("GAP",) and part == "ecpm"):
        ipu = _g(d, "ipu", "move") if fam == "ECPM" else (_g(d, "inside_value", "ipu_move") if fam in CA.MONEY_FAMS
                                                          else fin((mkt.get("own") or {}).get("ipu")))
        k += [("ipu", ipu), ("rate", _g(d, "countries_ecpm_gross", "rate_share"))]
    k += [("turn", fin(_turn(ri))), ("pf", (out.get("persist") or {}).get("first"))]
    res = {}
    for key, v in k:
        if v is not None and key not in res and len(res) < 16:
            res[key] = v
    return res
