"""📉 CPI vs eCPM alarm (pure: no I/O, no clock, no globals, no caches between calls; standard library only).

Every app, campaign and country is replayed day by day from its first spend to the data day t, so the alarm of any
past day is exactly what the alarm said on that day. One alarm (episode) per entity per family at a time.

  data day t = the newest day complete on every side (the build: Google Ads D0 value fixed, AdMob closed, spend
  fetched); 'seen' = t + 2. Days are the entity's own index from Ent.day0 (one slot per calendar date).
  windows (ratio of sums, on the family's own day index b = t − shift): L7 = b−6..b, P14 = b−20..b−7, L14 = b−13..b.
  families (bad direction, shift): CPI cost ÷ biddable installs (up, 0) · ECPM AdMob earnings ÷ impressions × 1000
    (down, 0) · GAP ads needed to pay back one install = cost ÷ installs × impressions ÷ earnings (up, 0) · IPU
    impressions ÷ GA4 active users (down, 1) · ROAS_G Google D0 value ÷ cost, INR ÷ INR (down, 0) · ROAS_C0/C1/C7
    AdMob-matched install-day revenue at age 0/1/7 ÷ the spend of those install days (down, 1/2/8) · SPEND cost per
    day (down, 0).
  openers (k consecutive data days; threshold = max(family minimum, z × noise)):
    SUDDEN   L7 vs P14                      noise = the daily swing × √(1/7 + 1/14)
    DRIFT    L14 vs H = median of the 14-day windows ending b−14, b−21 … b−84 that touch no alarm span (≥ 4)
    ABSOLUTE (cohort ROAS on apps, ROAS_G on campaigns) L14 vs U = the same median over b−14 … b−175 (≥ 6)
    daily swing = 1.4826 × MAD of log(day ÷ its centred 7-day median) over the 90 days before b−3, refreshed on
    the days (day − EPOCH) % 7 == 0; a young series (no swing yet) uses the minimum × 1.5.
    material: the money at stake ≥ floor_week per 7 days (CPI extra paid, ECPM / IPU revenue lost, ROAS cost ×
    (1 − ROAS ÷ base), GAP an estimate — a gate only, never shown as a loss).
    guards: a 14-day warm-up after every (re)start is never inside a window; ECPM / IPU only while the app buys
    users; no CPI / ECPM / IPU / GAP opening while buying > 2× the baseline's daily spend; ROAS_G is confirmed by the
    AdMob-matched D0 line (≥ half the threshold) when that line has data.
  an open episode: change start c, a FROZEN baseline B (the 14 days before c, or H when those were themselves > 25 %
    off the 14 before them; DRIFT H; ABSOLUTE U); re-notices on a new step or a slide vs the best L14 since the last
    notice, ≥ 15 days apart; closes when L7 is within the recovery band of B on 5 consecutive days ('recovered'),
    when the entity stopped spending ('stopped'), when ECPM / IPU lost its paid users ('no_paid'), or — P_PROD, the
    non-money families only — when the new level held 8 weeks ('settled': the level is accepted, no exclusion span).

  LEVELS (P["levels"], P_PROD): H gives way to a resting level R per family, always the exact value of named days:
    the first R = the middle clean fortnight of H's windows (an even count: the newer of the two middle ones); re-checked
    on the days (day − EPOCH) % 28 == 0 while no alarm of the family is open — a new R when it moved ≥ half the DRIFT
    minimum, the newest 4 clean fortnights are within ±10 % of it and the last change is ≥ 28 days old; money families
    only upward (downward: a proposal after 84 steady days, money_down "propose"). A settled alarm sets R = the exact
    value of its last 28 data days. An alarm open 120+ days is proposed too. Every episode baseline names its days
    (bspan). The owner's pin (set / roll back / accept) overrides R from its day and closes an alarm open that day
    ('owner', no span); "auto" ends it; a veto keeps an automatically accepted alarm open (retroactive). The level
    agent (engine.level_agent, run by the build) has two primitives of its own: "agent" accepts the exact value of
    named days on its day (the matching open alarm closes 'agent', no span, a level row "accepted_agent"; the
    automatic rules go on from it) and "agent_veto" keeps one episode open (it never settles and never becomes
    "held"; it still closes recovered / stopped / no_paid / owner and is proposed at 120 days).

P_PARITY reproduces the investigation's chosen run exactly (its legacy behaviour kept on purpose); P_PROD is
P_PARITY plus the production changes, each one switchable (see P_PROD below). The build uses P_PROD.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from datetime import date, timedelta

EPOCH = "2000-01-04"      # the weekly noise refresh runs on days with (day − EPOCH) % 7 == 0

# num / den series, scale, bad direction (+1 = up is bad), day shift (matured cohort / GA4 lag)
FAMILIES = {
    "CPI":     {"num": "sp_usd", "den": "inst", "bad": +1, "shift": 0},
    "ECPM":    {"num": "rev", "den": "imp", "bad": -1, "shift": 0},
    "GAP":     {"num": "sp_usd", "den": "inst", "bad": +1, "shift": 0},
    "IPU":     {"num": "imp", "den": "dau", "bad": -1, "shift": 1},
    "ROAS_G":  {"num": "d0_inr", "den": "sp_inr", "bad": -1, "shift": 0},
    "ROAS_C0": {"num": "c_r0", "den": "c_sp", "bad": -1, "shift": 1},
    "ROAS_C1": {"num": "c_r1", "den": "c_sp", "bad": -1, "shift": 2},
    "ROAS_C7": {"num": "c_r7", "den": "c_sp", "bad": -1, "shift": 8},
    "SPEND":   {"num": "sp_usd", "den": None, "bad": -1, "shift": 0},
}
FAMS_BY_KIND = {"app": ["CPI", "ECPM", "GAP", "IPU", "ROAS_G", "ROAS_C0", "ROAS_C1", "ROAS_C7", "SPEND"],
                "camp": ["CPI", "ROAS_G", "SPEND"],
                "country": ["CPI", "ECPM", "GAP", "SPEND"]}
MONEY_FAMS = ("ROAS_G", "ROAS_C0", "ROAS_C1", "ROAS_C7")
OUT_FAMS = ("CPI", "ECPM", "ROAS_G", "GAP", "IPU", "ROAS_C0")      # the per-day normal / healthy of app entities
CTY_OUT_FAMS = ("CPI", "ECPM")                                       # … of country entities (the Chart tab's country view)
CTX_FAMS = ("CPI", "ECPM", "GAP", "IPU", "ROAS_G", "ROAS_C0", "SPEND")

GATE = {"min_inst_day": 10.0, "min_sp_day": 10.0, "min_imp_day": 10000.0, "min_dau_day": 500.0,
        "min_coh_n_day": 10.0, "spend_base_day": 20.0, "min_paid_share": 0.6}
LEGACY_INR_PER_USD = 94.0  # P_PARITY's ROAS_G volume gate (cost ≥ $10 a day at this fixed rate); P_PROD gates in USD

# the opening minimums: "mid" for SUDDEN, "xlow" for DRIFT; ABSOLUTE = 1.5 × xlow (ROAS only)
_MID = {"CPI": 0.25, "ECPM": 0.15, "GAP": 0.30, "IPU": 0.15, "ROAS_G": 0.12, "ROAS_C0": 0.12, "ROAS_C1": 0.12,
        "ROAS_C7": 0.12, "SPEND": 0.50}
_XLOW = {"CPI": 0.15, "ECPM": 0.10, "GAP": 0.20, "IPU": 0.10, "ROAS_G": 0.07, "ROAS_C0": 0.07, "ROAS_C1": 0.07,
         "ROAS_C7": 0.07, "SPEND": 0.35}

P_PARITY = {
    "thr_s": dict(_MID), "k_s": 3, "z_s": 3.0,
    "thr_d": dict(_XLOW), "k_d": 10, "z_d": 3.0,
    "thr_a": {f: 1.5 * v for f, v in _XLOW.items() if f.startswith("ROAS")}, "k_a": 10, "z_a": 3.0,
    "use": {"SUDDEN": True, "DRIFT": True, "ABSOLUTE": True},
    "floor_week": 50.0,          # USD of money at stake per 7 days for an opening (material)
    "thr_r": 0.10, "m_r": 5,     # recovery: L7 within 10 % of the frozen baseline on 5 consecutive days
    "paid_gate_day": 10.0,       # ECPM / IPU alarms only while the app buys users (L7 spend ≥ $10 a day)
    "base_band": 0.25,           # the 14 days before c are the baseline unless they were > 25 % off the 14 before
    "warmup": True, "warmup_days": 14, "restart_gap": 28,
    "young_mult": 1.5,
    "scale_max": {"CPI": 2.0, "ECPM": 2.0, "IPU": 2.0, "GAP": 2.0},
    "confirm": {"ROAS_G": ("ROAS_C0", 0.5)},
    # legacy behaviour (the parity run); P_PROD switches each one
    "thr_r_mode": "fixed",       # "adaptive": the band = min(thr_r, max(5 %, thr_open ÷ 2))
    "esc_from": 1,               # the step re-notice counts from opened + esc_from (1: it repeats the opening step)
    "drift_bsp": "span",         # the DRIFT / ABSOLUTE scale guard's base spend per day: "span" t−97..t−14 (legacy:
                                 # takes in a lasting scale-up) | "windows" all of H's windows | "median" the one or two
                                 # windows H's value comes from
    "roas_g_gate": "inr94",      # "usd": cost ≥ $10 × days
    "cpi_ccy": "usd",            # "inr": CPI = INR cost ÷ installs (FX-free)
    "money_cpi": False,          # also report CPI episodes' extra paid (both currencies) — never a loss
    "settle": None,              # {"days", "band", "fams"}: accept a new level that held `days` days
    "country_elig": None,        # {"days", "share", "usd"}: country entities big enough over the trailing window
    "unknown": "lenient",        # "strict": a window with an unknown (None) day has no value; an unknown spend day
                                 # neither opens nor closes anything
    "levels": None,              # the resting level R (see LEVELS below); None = the median H recomputed every day
}

# The production set. Each change was re-backtested on the full history against the parity run (detection of the
# known incidents, false alarms and pushes per app-year, alarms left open); a change that lost a known incident is OFF:
#   esc_from 7 (the step re-notice counted from opened + 7): moved a re-notice before an incident's window, and its
#     15-day spacing then hid the one that caught it — OFF (1);
#   thr_r_mode "adaptive" (a tighter band for low thresholds): an old DRIFT alarm no longer closed, so a later
#     incident had no new opening of its own — OFF ("fixed");
#   drift_bsp: "windows" (every window of H) is t−97..t−14 again whenever no window is skipped, so a lasting scale-up
#     still opens DRIFT against the old level; "median" (the windows H's value comes from) holds it — ON.
P_PROD = copy.deepcopy(P_PARITY)
P_PROD.update({
    "settle": {"days": 56, "band": 0.10, "fams": ["CPI", "ECPM", "GAP", "IPU", "SPEND"]},
    "drift_bsp": "median",
    "roas_g_gate": "usd",
    "cpi_ccy": "inr", "money_cpi": True,
    "country_elig": {"days": 120, "share": 0.03, "usd": 500.0},
    "unknown": "strict",
    "levels": {
        "pick": "newer",            # an even count of clean fortnights: the newer of the two middle ones (never a mean)
        "every": 28,                # re-check on the days (day − EPOCH) % 28 == 0, only while no alarm of the family is open
        "delta": {f: v / 2.0 for f, v in _XLOW.items()},   # a new level differs from R by ≥ half the DRIFT minimum
        "steady": (4, 0.10),        # … and the newest 4 clean fortnights are all within ±10 % of it
        "cool": 28,                 # … and the family's last level change is ≥ 28 days old
        "money_down": "propose",    # money families (ROAS_*) move up automatically; down only as a proposal the owner
                                    # accepts ("auto": accepted after money_days steady days, as the others' settle)
        "accept_days": 28,          # an accepted level = the exact value of the last 28 data days
        "propose": {"money_days": 84, "money_band": 0.10, "open_days": 120},
        # the level agent (engine.level_agent, run by the build; this engine never reads it)
        "agent": {
            "mode": "on",              # "off": the build runs no agent step (files exactly as without it)
            "every": 7,                # a standing question is asked again on the days (day − EPOCH) % 7 == 0
            "settle_fams": ["CPI", "GAP"],   # the engine's own settles the agent checks; the others settle as before
            "move_bands": 2.0,         # an accept needs old → new ≥ 2 bands and the last 28 days outside one band of old
            "engine_band": 0.10,       # … and on the eCPM-market branch the engine's own settle steadiness (56 d)
            "net": {"days": 84, "from": 28, "every": 7, "need": 2},   # the revert net (shadow replay + two checks)
            "checks": [28, 56, 84],    # the verdict's 28-day checkpoints after the ask
            "trial": {"days": 28, "vintage": [7, 28]},   # accepts on proposals apply only after this clean trial
            "keep_ri": 35,             # days an ask keeps its full rule inputs (the vintage re-asks compare them)
            "max_asks": 40,            # asks per build (the rest wait for the next build); vintage re-asks: their own 40
            "budget_s": 20.0,          # wall time of the whole agent step (the build's clock; the engine reads none)
        },
    },
})


@dataclass
class Ent:
    kind: str            # "app" | "camp" | "country"
    id: str              # app_id | campaign id | "<app_id>|CC"
    app: str             # the app_id it belongs to
    label: str           # display text (never logged)
    day0: str            # ISO date of index 0 of every series
    s: dict              # name -> list[float|None]: sp_usd sp_inr inst d0_inr rev imp dau c_n c_sp c_r0 c_r1 c_r7;
    #                      a missing name = not applicable, a missing day = None (unknown) or 0


def _iso(day0, i):
    return (date.fromisoformat(day0) + timedelta(days=i)).isoformat()


def _rel(fam, lw):
    """log units in the bad direction → a relative change (+0.25 = 25 % worse)."""
    return (math.exp(lw) - 1.0) if FAMILIES[fam]["bad"] > 0 else (1.0 - math.exp(-lw))


def lthr(fam, rel):
    """A relative threshold in the bad direction → log units (up-bad log(1 + rel), down-bad −log(1 − rel))."""
    return math.log(1.0 + rel) if FAMILIES[fam]["bad"] > 0 else -math.log(max(1e-9, 1.0 - rel))


def lworse(fam, x, base):
    """log(x ÷ base) in the bad direction (> 0 = worse), None when unknown; a down-bad value at 0 = 5.0."""
    if x is None or base is None or x <= 0 or base <= 0:
        if x is not None and base is not None and base > 0 and x <= 0 and FAMILIES[fam]["bad"] < 0:
            return 5.0
        return None
    return math.log(x / base) * FAMILIES[fam]["bad"]


def eff_thr(fam, rel_min, z, sig, young_mult=1.5, scale=0.4629):
    """The opening threshold in log units: max(the family minimum, z × sig × scale); scale √(1/7 + 1/14) = 0.4629
    for L7 vs P14, √(1/14) = 0.267 for L14 vs a median level; no measured swing yet → the minimum × young_mult."""
    lt = lthr(fam, rel_min)
    if sig is None:
        return lt * young_mult
    return max(lt, z * sig * scale)


def _median(v):
    v = sorted(v)
    m = len(v)
    return v[m // 2] if m % 2 else 0.5 * (v[m // 2 - 1] + v[m // 2])


def _healthy(V14, t, spans, n_win=11, need=4, sh=0, used=None, mid=False, pick="mean"):
    """Median of the 14-day windows ending t−14, t−21 … (n_win of them, shifted) that touch no span; the ends of the
    windows taken (mid: only the one or two the median's value comes from) go to `used`. pick "newer": an even count
    gives the newer of the two middle windows (one named fortnight, never a mean of two)."""
    vals = []
    for j in range(n_win):
        b = t - 14 - 7 * j - sh
        a = b - 13
        if a < 0:
            break
        if spans and any(not (b < s0 or a > s1) for s0, s1 in spans):
            continue
        v = V14[b]
        if v is not None:
            vals.append((v, b))
    if len(vals) < need:
        return None
    if pick == "newer" and len(vals) % 2 == 0:
        o = sorted(vals, key=lambda z: z[0])
        m = len(o)
        w = max(o[m // 2 - 1:m // 2 + 1], key=lambda z: z[1])
        if used is not None:
            if mid:
                used.append(w[1])
            else:
                used.extend(b for _, b in vals)
        return w[0]
    if used is not None:
        if mid:
            o = sorted(vals, key=lambda z: z[0])
            m = len(o)
            used.extend(z[1] for z in (o[m // 2:m // 2 + 1] if m % 2 else o[m // 2 - 1:m // 2 + 1]))
        else:
            used.extend(b for _, b in vals)
    return _median([v for v, _ in vals])


class _Ser:
    """One entity's series up to t (index 0..n−1) as prefix sums, plus counts of known days, the warm-up mask and the
    family value functions for this run's P. Built per run (never kept)."""

    def __init__(self, e, n, P):
        self.kind, self.id, self.app, self.n, self.P = e.kind, e.id, e.app, n, P
        self.off = (date.fromisoformat(e.day0) - date.fromisoformat(EPOCH)).days
        self.strict = P.get("unknown") == "strict"
        self.cpi_inr = P.get("cpi_ccy") == "inr" and "sp_inr" in e.s
        self.pre, self.cnt = {}, {}
        for k, v in e.s.items():
            p, c = [0.0] * (n + 1), [0] * (n + 1)
            acc, cn = 0.0, 0
            m = len(v)
            for i in range(n):
                x = v[i] if i < m else None
                if x is not None:
                    acc += x
                    cn += 1
                p[i + 1], c[i + 1] = acc, cn
            self.pre[k], self.cnt[k] = p, c
        sp = self.pre.get("sp_usd")
        self.first = next((i for i in range(n) if sp[i + 1] - sp[i]), None) if sp else None
        self.warm = self._warm_mask()
        wp = [0] * (n + 1)
        for i in range(n):
            wp[i + 1] = wp[i] + (1 if self.warm[i] else 0)
        self.wp = wp
        self._fn, self._ser = {}, {}

    def has(self, k):
        return k in self.pre

    def S(self, k, a, b):
        if a < 0:
            a = 0
        if b < a:
            return 0.0
        p = self.pre[k]
        return p[b + 1] - p[a]

    def K(self, k, a, b):
        if a < 0:
            a = 0
        if b < a:
            return 0
        c = self.cnt[k]
        return c[b + 1] - c[a]

    def _warm_mask(self):
        """True on the warm-up days after each (re)start of spending (the first spend, or the first spend after more
        than restart_gap days without any)."""
        n, P = self.n, self.P
        m = [False] * n
        if not P.get("warmup", True) or not self.has("sp_usd"):
            return m
        wd, gap = P.get("warmup_days", 14), P.get("restart_gap", 28)
        p = self.pre["sp_usd"]
        last = None
        for i in range(n):
            if p[i + 1] - p[i] > 0:
                if last is None or i - last > gap:
                    for j in range(i, min(n, i + wd)):
                        m[j] = True
                last = i
        return m

    def clean(self, a, b):
        """True when no day of a..b is inside a warm-up."""
        if a < 0:
            return False
        b = min(b, self.n - 1)
        return b < a or self.wp[b + 1] - self.wp[a] == 0

    # ── values ────────────────────────────────────────────────────────────────────────────────────────────────────
    def fn(self, fam):
        """The family value over a..b (0 ≤ a ≤ b < n) as a closure on local prefix lists (the hot path)."""
        f = self._fn.get(fam)
        if f is None:
            f = self._fn[fam] = self._make_fn(fam)
        return f

    def _make_fn(self, fam):
        pre, cnt, strict = self.pre, self.cnt, self.strict
        F = FAMILIES[fam]
        num, den = F["num"], F["den"]
        none = lambda a, b: None   # noqa: E731
        if fam == "SPEND":
            if not self.has("sp_usd"):
                return none
            Ps, Ks = pre["sp_usd"], cnt["sp_usd"]

            def spend(a, b):
                nd = b - a + 1
                if strict and Ks[b + 1] - Ks[a] < nd:
                    return None
                return (Ps[b + 1] - Ps[a]) / nd
            return spend
        if not (self.has(num) and self.has(den)):
            return none
        gi, gs, gm = GATE["min_inst_day"], GATE["min_sp_day"], GATE["min_imp_day"]
        if fam == "CPI":
            Pi, Ps = pre["inst"], pre["sp_usd"]
            Pc = pre["sp_inr"] if self.cpi_inr else Ps
            ks = [cnt[k] for k in ("inst", "sp_usd", "sp_inr" if self.cpi_inr else "sp_usd")] if strict else ()

            def cpi(a, b):
                nd = b - a + 1
                for c in ks:
                    if c[b + 1] - c[a] < nd:
                        return None
                i, s = Pi[b + 1] - Pi[a], Ps[b + 1] - Ps[a]
                if i < gi * nd or s < gs * nd:
                    return None
                return (Pc[b + 1] - Pc[a]) / i if Pc is not Ps else s / i
            return cpi
        if fam == "ECPM":
            Pr, Pm = pre["rev"], pre["imp"]
            ks = [cnt["rev"], cnt["imp"]] if strict else ()

            def ecpm(a, b):
                nd = b - a + 1
                for c in ks:
                    if c[b + 1] - c[a] < nd:
                        return None
                im = Pm[b + 1] - Pm[a]
                if im < gm * nd:
                    return None
                return (Pr[b + 1] - Pr[a]) / im * 1000.0
            return ecpm
        if fam == "GAP":
            if not (self.has("rev") and self.has("imp")):
                return none
            Pi, Ps, Pm, Pr = pre["inst"], pre["sp_usd"], pre["imp"], pre["rev"]
            ks = [cnt[k] for k in ("inst", "sp_usd", "imp", "rev")] if strict else ()

            def gap(a, b):
                nd = b - a + 1
                for c in ks:
                    if c[b + 1] - c[a] < nd:
                        return None
                i, s, im, rv = Pi[b + 1] - Pi[a], Ps[b + 1] - Ps[a], Pm[b + 1] - Pm[a], Pr[b + 1] - Pr[a]
                if i < gi * nd or s < gs * nd or im < gm * nd or rv <= 0:
                    return None
                return (s / i) * (im / rv)
            return gap
        if fam == "IPU":
            Pd, Kd, Pm = pre["dau"], cnt["dau"], pre["imp"]
            km = cnt["imp"] if strict else None
            gd = GATE["min_dau_day"]

            def ipu(a, b):
                nd = b - a + 1
                if Kd[b + 1] - Kd[a] < nd or (km is not None and km[b + 1] - km[a] < nd):
                    return None
                du = Pd[b + 1] - Pd[a]
                if du < gd * nd:
                    return None
                return (Pm[b + 1] - Pm[a]) / du
            return ipu
        if fam == "ROAS_G":
            Pv, Pc = pre["d0_inr"], pre["sp_inr"]
            usd = self.P.get("roas_g_gate") == "usd" and self.has("sp_usd")
            Pg = pre["sp_usd"] if usd else Pc
            gg = gs if usd else gs * LEGACY_INR_PER_USD
            ks = [cnt[k] for k in (("d0_inr", "sp_inr", "sp_usd") if usd else ("d0_inr", "sp_inr"))] if strict else ()

            def roas_g(a, b):
                nd = b - a + 1
                for c in ks:
                    if c[b + 1] - c[a] < nd:
                        return None
                sp = Pc[b + 1] - Pc[a]
                if (Pg[b + 1] - Pg[a] if usd else sp) < gg * nd:
                    return None
                return (Pv[b + 1] - Pv[a]) / sp
            return roas_g
        if fam.startswith("ROAS_C"):
            if not (self.has("c_n") and self.has("inst")):
                return none
            Pv, Kv, Pc, Kc, Pn, Pi = pre[num], cnt[num], pre["c_sp"], cnt["c_sp"], pre["c_n"], pre["inst"]
            ks = [cnt["c_n"], cnt["inst"]] if strict else ()
            gn, share = GATE["min_coh_n_day"], GATE["min_paid_share"]

            def roas_c(a, b):
                nd = b - a + 1
                if Kv[b + 1] - Kv[a] < nd or Kc[b + 1] - Kc[a] < nd:
                    return None
                for c in ks:
                    if c[b + 1] - c[a] < nd:
                        return None
                sp, cn = Pc[b + 1] - Pc[a], Pn[b + 1] - Pn[a]
                if sp < gs * nd or cn < gn * nd:
                    return None
                if Pi[b + 1] - Pi[a] < share * cn:        # organic-heavy days are not a paid ROAS
                    return None
                return (Pv[b + 1] - Pv[a]) / sp
            return roas_c
        return none

    def value(self, fam, a, b):
        """The family metric over days a..b (inclusive, already shifted) or None when the window is too thin."""
        if a < 0 or b < a or b >= self.n:
            return None
        return self.fn(fam)(a, b)

    def money(self, fam, a, b, base):
        """The money at stake over days a..b (shifted) against a baseline, USD (positive = bad)."""
        if base is None or a < 0 or b < a:
            return 0.0
        S = self.S
        if fam == "CPI":
            if self.cpi_inr:
                su, si = S("sp_usd", a, b), S("sp_inr", a, b)
                return su - S("inst", a, b) * base * (su / si) if si > 0 else 0.0
            return S("sp_usd", a, b) - S("inst", a, b) * base
        if fam == "ECPM":
            return S("imp", a, b) * base / 1000.0 - S("rev", a, b)
        if fam == "IPU":
            du, im, rv = S("dau", a, b), S("imp", a, b), S("rev", a, b)
            if not du or not im:
                return 0.0
            return (base * du - im) * (rv / im)
        if fam == "ROAS_G":
            sp_inr, sp_usd = S("sp_inr", a, b), S("sp_usd", a, b)
            if not sp_inr or not base:
                return 0.0
            return sp_usd * (1.0 - (S("d0_inr", a, b) / sp_inr) / base)
        if fam.startswith("ROAS_C"):
            if not base:
                return 0.0
            return S("c_sp", a, b) - S(FAMILIES[fam]["num"], a, b) / base
        if fam == "SPEND":
            return base * (b - a + 1) - S("sp_usd", a, b)
        if fam == "GAP":
            # an ESTIMATE (the opening's materiality gate only): cost × (1 − base ÷ now)
            x = self.value(fam, a, b)
            if not x:
                return 0.0
            return S("sp_usd", a, b) * (1.0 - base / x)
        return 0.0

    def applicable(self, fam):
        f = FAMILIES[fam]
        n = self.n
        if fam == "SPEND":
            return self.has("sp_usd")
        if not (self.has(f["num"]) and (f["den"] is None or self.has(f["den"]))):
            return False
        if fam in ("ECPM", "IPU", "GAP") and (not self.has("imp") or self.S("imp", 0, n - 1) <= 0):
            return False
        if fam == "IPU" and self.K("dau", 0, n - 1) == 0:
            return False
        if fam == "ROAS_G" and self.S("d0_inr", 0, n - 1) <= 0:
            return False
        if fam.startswith("ROAS_C") and self.K(f["num"], 0, n - 1) == 0:
            return False
        return True

    # ── rolling series ────────────────────────────────────────────────────────────────────────────────────────────
    def series(self, fam):
        """(V7, V14, SIG): V7[b] = X(b−6..b), V14[b] = X(b−13..b) on the family's shifted index (None when a day of
        the window is in a warm-up); SIG[t] = the daily swing (refreshed on the EPOCH-phased weekly days)."""
        r = self._ser.get(fam)
        if r is not None:
            return r
        n, f, wp, warm = self.n, self.fn(fam), self.wp, self.warm
        sh = FAMILIES[fam]["shift"]
        V7 = [None] * n
        V14 = [None] * n
        for b in range(6, n):
            if wp[b + 1] - wp[b - 6] == 0:
                V7[b] = f(b - 6, b)
                if b >= 13 and wp[b + 1] - wp[b - 13] == 0:
                    V14[b] = f(b - 13, b)
        # the normal swing from the day-to-day noise: r_d = log(x_d ÷ median(x_d−3 .. x_d+3)) of the single days,
        # SIG = 1.4826 × MAD(r_d) over d = b−90 .. b−4 (≥ 30 values)
        X1 = [None if warm[d] else f(d, d) for d in range(n)]
        Rd = [None] * n
        for d in range(3, n - 3):
            x = X1[d]
            if not x or x <= 0:
                continue
            nb = [v for v in X1[d - 3:d + 4] if v and v > 0]
            if len(nb) < 5:
                continue
            nb.sort()
            Rd[d] = math.log(x / nb[len(nb) // 2])
        SIG = [None] * n
        cur = None
        off = self.off
        for t in range(n):
            if (off + t) % 7 == 0:
                tt = t - sh
                vals = [Rd[d] for d in range(max(0, tt - 90), max(0, tt - 3)) if Rd[d] is not None]
                if len(vals) >= 30:
                    vals.sort()
                    med = vals[len(vals) // 2]
                    dev = sorted(abs(v - med) for v in vals)
                    cur = 1.4826 * dev[len(dev) // 2]
                else:
                    cur = None
            SIG[t] = cur
        r = self._ser[fam] = (V7, V14, SIG)
        return r

    def change_start(self, fam, t, sh):
        """The strongest step day j in t−27 .. t−2 (j..t vs the 14 days before j, shifted), bad direction only."""
        best, bj = None, None
        for j in range(t - 27, t - 1):
            if not self.clean(j - 14 - sh, j - 1 - sh):
                continue
            before = self.value(fam, j - 14 - sh, j - 1 - sh)
            after = self.value(fam, j - sh, t - sh)
            lw = lworse(fam, after, before)
            if lw is None or lw <= 0:
                continue
            na = t - j + 1
            sc = lw * math.sqrt(14.0 * na / (14.0 + na))
            if best is None or sc > best:
                best, bj = sc, j
        return bj

    def context(self, t):
        """Every other family's L7 vs P14 change on the opening day (relative, natural sign)."""
        out = {}
        for f in CTX_FAMS:
            if not self.applicable(f):
                continue
            V7, V14, _ = self.series(f)
            sh = FAMILIES[f]["shift"]
            if t - 7 - sh < 13:
                continue
            a, b = V7[t - sh], V14[t - 7 - sh]
            if a is not None and b:
                out[f] = round(a / b - 1.0, 4)
        return out

    def rates(self):
        """USD per INR on each day from the entity's own cost (carried forward over days without cost; before the
        first one, the first known)."""
        r = getattr(self, "_rates", None)
        if r is not None:
            return r
        n = self.n
        r = [None] * n
        if self.has("sp_usd") and self.has("sp_inr"):
            pu, pi = self.pre["sp_usd"], self.pre["sp_inr"]
            last = None
            for i in range(n):
                u, x = pu[i + 1] - pu[i], pi[i + 1] - pi[i]
                if u > 0 and x > 0:
                    last = u / x
                r[i] = last
            first = next((x for x in r if x is not None), None)
            r = [first if x is None else x for x in r]
        self._rates = r
        return r


def _day(s, k, i):
    v = s.get(k)
    if v is None or i >= len(v):
        return None
    return v[i]


def _ep_money(e, ser, fam, c, end, base):
    """The episode's measured money over data days c..end (USD at each day's own rate and INR): ROAS_* = cost − value ÷
    B (a loss), CPI = cost − installs × B (extra paid; P_PROD only)."""
    if base is None or base <= 0 or end < c:
        return None
    rates = ser.rates()
    s = e.s
    lu = li = cu = ci = 0.0
    for d in range(max(0, c), end + 1):
        rt = rates[d] if d < len(rates) else None
        if fam == "ROAS_G":
            sp_u, sp_i, v = _day(s, "sp_usd", d), _day(s, "sp_inr", d), _day(s, "d0_inr", d)
            if sp_i is None or v is None:
                continue
            sp_u = sp_u or 0.0
            li += sp_i - v / base
            lu += sp_u - (v * rt / base if rt else 0.0)
            cu += sp_u
            ci += sp_i
        elif fam == "CPI":
            sp_u, sp_i, n = _day(s, "sp_usd", d), _day(s, "sp_inr", d), _day(s, "inst", d)
            if sp_i is None or n is None:
                continue
            sp_u = sp_u or 0.0
            li += sp_i - n * base
            lu += sp_u - (n * base * rt if rt else 0.0)
            cu += sp_u
            ci += sp_i
        else:
            sp, v = _day(s, "c_sp", d), _day(s, FAMILIES[fam]["num"], d)
            if sp is None or v is None:
                continue
            lu += sp - v / base
            cu += sp
            if rt:
                li += (sp - v / base) / rt
                ci += sp / rt
    return {"since_c_usd": round(lu, 2), "since_c_inr": round(li, 2), "cost_usd": round(cu, 2),
            "cost_inr": round(ci, 2), "what": "extra_paid" if fam == "CPI" else "loss"}


def _settled(V14, t, sh, days, band):
    """True when every L14 of the last `days` data days is known and within ±band of their median."""
    vals = [V14[d - sh] for d in range(t - days + 1, t + 1) if d - sh >= 0]
    if len(vals) < days or any(v is None or v <= 0 for v in vals):
        return False
    m = _median(vals)
    return all(abs(v / m - 1.0) <= band for v in vals)


def _run_family(e, ser, fam, P, t0, t1, own=()):
    """Replay one family on one entity over data days t0..t1 → (episodes as internal dicts, the state on t1, the level
    rows: [{"t", "v", "src", "span", …}] — empty without P["levels"]). own: the owner's primitives of this family
    (pin / auto / veto, and the level agent's agent / agent_veto; day indexes), sorted by day."""
    sh = FAMILIES[fam]["shift"]
    V7, V14, SIG = ser.series(fam)
    thr_s, thr_d = P["thr_s"].get(fam), P["thr_d"].get(fam)
    thr_a = P["thr_a"].get(fam) if (fam.startswith("ROAS_C") or (fam == "ROAS_G" and e.kind == "camp")) else None
    floor, ym = P["floor_week"], P.get("young_mult", 1.5)
    zs, zd, za = P["z_s"], P["z_d"], P["z_a"]
    strict = ser.strict
    paid = P["paid_gate_day"] * 7
    esc_from = P.get("esc_from", 1)
    st_cfg = P.get("settle")
    settle = st_cfg if (st_cfg and fam in st_cfg["fams"]) else None
    adaptive = P.get("thr_r_mode", "fixed") != "fixed"
    windows_bsp = P.get("drift_bsp") in ("windows", "median")
    mid = P.get("drift_bsp") == "median"
    spans, eps = [], []
    LV = P.get("levels")
    R, R_used, lev = None, [], []               # the resting level, the window ends it was taken from, its rows
    pick = LV.get("pick", "mean") if LV else "mean"
    money = fam in MONEY_FAMS
    pr = (LV or {}).get("propose") or {}
    m_auto = bool(LV) and money and LV.get("money_down") == "auto"
    if m_auto and pr.get("money_days"):          # money accepted automatically after money_days steady days
        settle = {"days": pr["money_days"], "band": pr.get("money_band", 0.10), "fams": [fam]}
    cur = None
    cS = cD = cA = 0
    esc_n = esc_d = 0
    state = "warm"
    for t in range(t0, t1 + 1):
        sp7 = ser.S("sp_usd", t - 6, t)
        unknown = strict and ser.K("sp_usd", t - 6, t) < 7
        sig = SIG[t]
        if cur is None:
            if unknown or sp7 <= 0 or (fam in ("ECPM", "IPU") and sp7 < paid) or \
                    (fam == "SPEND" and ser.S("sp_usd", t - 2, t) <= 0):
                cS = cD = cA = 0
                state = "gated"
                continue
            used = [] if windows_bsp else None
            h = _healthy(V14, t, spans, sh=sh, used=used, mid=mid, pick=pick)   # None when young: SUDDEN only
            if LV:
                # the resting level R replaces the daily median: formed once, re-checked every 4 weeks, the owner's
                # pin overrides it (§ LEVELS)
                pin = _pin_at(own, t)
                if pin is not None:
                    if R != pin["value"]:
                        R, R_used = pin["value"], []
                        lev.append({"t": t, "v": R, "src": pin.get("src", "manual"), "span": pin.get("span"),
                                    "act": pin.get("id")})
                elif h is not None and h > 0 and (R is None or (
                        (ser.off + t) % LV.get("every", 28) == 0
                        and abs(math.log(h / R)) >= math.log(1.0 + LV["delta"].get(fam, 0.05))
                        and _steady(V14, t, spans, sh, h, LV.get("steady"))
                        and not (money and not m_auto and lworse(fam, h, R) > 0)
                        and (not lev or t - lev[-1]["t"] >= LV.get("cool", 0)))):
                    R, R_used = h, list(used or [])
                    hb = R_used[-1] if R_used else None
                    lev.append({"t": t, "v": R, "src": "first" if not lev else "auto",
                                "span": (hb - 13, hb) if hb is not None else None})
                h = R
                if used is not None:
                    used[:] = R_used
            fired, u, info = None, None, None
            if P["use"]["SUDDEN"] and thr_s is not None and t - 7 - sh >= 13:
                x7, xp = V7[t - sh], V14[t - 7 - sh]
                lw = lworse(fam, x7, xp)
                lt = eff_thr(fam, thr_s, zs, sig, ym)
                ok = lw is not None and lw >= lt
                if ok:
                    if fam == "SPEND":
                        ok = xp >= GATE["spend_base_day"] and (xp - x7) * 7 >= floor
                    else:
                        ok = ser.money(fam, t - 6 - sh, t - sh, xp) >= floor
                cS = cS + 1 if ok else 0
                if cS >= P["k_s"]:
                    fired, info = "SUDDEN", lt
            if fired is None and P["use"]["DRIFT"] and thr_d is not None:
                x14 = V14[t - sh]
                lw = lworse(fam, x14, h)
                lt = eff_thr(fam, thr_d, zd, sig, ym, scale=0.267)
                ok = lw is not None and lw >= lt
                if ok:
                    if fam == "SPEND":
                        ok = h >= GATE["spend_base_day"] and (h - x14) * 7 >= floor
                    else:
                        ok = ser.money(fam, t - 13 - sh, t - sh, h) / 2.0 >= floor
                cD = cD + 1 if ok else 0
                if cD >= P["k_d"]:
                    fired, info = "DRIFT", lt
            uused = [] if windows_bsp else None
            if fired is None and P["use"]["ABSOLUTE"] and thr_a is not None:
                u = _healthy(V14, t, spans, n_win=24, need=6, sh=sh, used=uused, mid=mid, pick=pick)
                x14 = V14[t - sh]
                lw = lworse(fam, x14, u)
                lt = eff_thr(fam, thr_a, za, sig, ym, scale=0.267)
                ok = lw is not None and lw >= lt and ser.money(fam, t - 13 - sh, t - sh, u) / 2.0 >= floor
                cA = cA + 1 if ok else 0
                if cA >= P["k_a"]:
                    fired, info = "ABSOLUTE", lt
            if fired is None:
                if ser.warm[t - sh] if t - sh >= 0 else True:
                    state = "warm"
                elif V7[t - sh] is None:
                    state = "gated"
                else:
                    state = "arming" if (cS or cD or cA) else "ok"
                continue
            lt_open = info
            # confirmation by a second, independent reading of the same cause (Google's D0 value vs AdMob's
            # install-day revenue): it must also be worse by ≥ frac × the threshold, when it has data
            cf = (P.get("confirm") or {}).get(fam)
            conf = None
            if cf:
                of, frac = cf
                if ser.applicable(of):
                    oV7, oV14, _ = ser.series(of)
                    osh = FAMILIES[of]["shift"]
                    if fired == "SUDDEN":
                        olw = lworse(of, oV7[t - osh], oV14[t - 7 - osh]) if t - 7 - osh >= 13 else None
                    else:
                        olw = lworse(of, oV14[t - osh], _healthy(oV14, t, [], sh=osh))
                    if olw is None:
                        conf = "no_data"
                    elif olw >= frac * lt_open:
                        conf = "confirmed"
                    else:
                        cS = cD = cA = 0
                        state = "arming"
                        continue
                else:
                    conf = "no_data"
            if fired == "SUDDEN":
                c = ser.change_start(fam, t, sh)
                base = ser.value(fam, c - 14 - sh, c - 1 - sh) \
                    if (c is not None and ser.clean(c - 14 - sh, c - 1 - sh)) else None
                bdays = (c - 14 - sh, c - 1 - sh) if base is not None else None
                if base is None:
                    c, base = t - 6, V14[t - 7 - sh]
                    bdays = (t - 20 - sh, t - 7 - sh)
                base_src = "before"
                prev = ser.value(fam, c - 28 - sh, c - 15 - sh) if ser.clean(c - 28 - sh, c - 15 - sh) else None
                if h and base and prev and h > 0 and base > 0 and prev > 0 and \
                        abs(math.log(base / prev)) > math.log(1.0 + P["base_band"]):
                    base, base_src = h, "band"
                    bdays = lev[-1]["span"] if (LV and lev) else None
                # re-check against the chosen baseline: a move back to normal from an unusually good fortnight is no
                # alarm
                lw = lworse(fam, V7[t - sh], base)
                if lw is None or lw < lt_open:
                    cS = 0
                    state = "arming"
                    continue
                bspan = (c - 14 - sh, c - 1 - sh)
                bsp = ser.S("sp_usd", max(0, bspan[0] + sh), bspan[1] + sh) / max(1, bspan[1] - bspan[0] + 1)
            else:
                ref = h if fired == "DRIFT" else u
                c = t - 13
                for d in range(t, max(t - 90, 7), -1):
                    lw7 = lworse(fam, V7[d - sh], ref)
                    if lw7 is None or lw7 < lt_open / 2.0:
                        break
                    c = d - 6
                base = ref
                base_src = "healthy" if fired == "DRIFT" else "usual"
                if fired == "DRIFT":
                    bdays = lev[-1]["span"] if (LV and lev) else None
                else:
                    bdays = (uused[-1] - 13, uused[-1]) if (uused and len(uused) == 1) else None
                if windows_bsp:
                    # the average daily spend over the days of the windows the level was taken from
                    ends = used if fired == "DRIFT" else uused
                    dd = set()
                    for b in ends:
                        dd.update(range(b - 13 + sh, b + sh + 1))
                    bsp = sum(ser.S("sp_usd", d, d) for d in dd) / len(dd) if dd else 0.0
                else:
                    bspan = (t - 14 - 7 * (10 if fired == "DRIFT" else 23) - 13 - sh, t - 14 - sh)
                    bsp = ser.S("sp_usd", max(0, bspan[0] + sh), bspan[1] + sh) / max(1, bspan[1] - bspan[0] + 1)
            # scale guard: buying > scale_max × the baseline's daily spend makes CPI / eCPM / ads per user incomparable
            sx = (sp7 / 7.0 / bsp) if bsp > 0 else None
            smax = P["scale_max"].get(fam)
            if smax and sx is not None and sx > smax:
                cS = cD = cA = 0
                state = "arming"
                continue
            cur = {"fam": fam, "opener": fired, "open": t, "c": c, "base": base, "base_src": base_src, "bspan": bdays,
                   "lthr": lt_open, "thr_open": _rel(fam, lt_open), "rec": 0, "max_worse": 0.0, "esc": [],
                   "esc_kind": [], "confirm": conf, "ctx": ser.context(t),
                   "stake": [ser.money(fam, t - 6 - sh, t - sh, base)]}
            cS = cD = cA = 0
            esc_n = esc_d = 0
            cur["ref14"] = V14[t - sh] if V14[t - sh] else base
        else:
            # re-notice (the same alarm, never a new one) when it got materially worse than when the owner last saw
            # it: a new step (L7 vs P14 ≥ the SUDDEN threshold, k_s days) or a slide (L14 vs the best L14 since the
            # last notice ≥ the DRIFT threshold, k_d days); ≥ 15 days apart
            if thr_s is not None and t - 7 - sh >= 13 and t - cur["open"] >= esc_from:
                lw = lworse(fam, V7[t - sh], V14[t - 7 - sh])
                esc_n = esc_n + 1 if (lw is not None and lw >= eff_thr(fam, thr_s, zs, sig, ym)) else 0
            else:
                esc_n = 0
            v14 = V14[t - sh]
            if v14 is not None and v14 > 0:
                b14 = cur["ref14"]
                if b14 is None or lworse(fam, v14, b14) < 0:
                    cur["ref14"] = v14
            lwd = lworse(fam, v14, cur["ref14"]) if thr_d is not None else None
            esc_d = esc_d + 1 if (lwd is not None and lwd >= eff_thr(fam, thr_d, zd, sig, ym, scale=0.267)) else 0
            if (esc_n >= P["k_s"] or esc_d >= P["k_d"]) and (not cur["esc"] or t - cur["esc"][-1] > 14):
                cur["esc"].append(t)
                cur["esc_kind"].append("step" if esc_n >= P["k_s"] else "slide")
                cur["stake"].append(ser.money(fam, t - 6 - sh, t - sh, cur["base"]))
                cur["ref14"] = V14[t - sh] or cur["ref14"]
                esc_n = esc_d = 0
        if own:
            pin = _pin_at(own, t)
            if pin is not None and pin["day"] == t and cur["open"] < t:
                cur["close"], cur["why"] = t, "owner"          # the owner set the level: this alarm ends, no span
                eps.append(cur)
                cur = None
                R, R_used = pin["value"], []
                lev.append({"t": t, "v": R, "src": pin.get("src", "manual"), "span": pin.get("span"),
                            "act": pin.get("id")})
                state = "ok"
                continue
            ag = _agent_at(own, t, cur)
            if ag is not None and cur["open"] < t and pin is None:
                cur["close"], cur["why"] = t, "agent"          # the agent accepted the new level: no span, the
                eps.append(cur)                                # automatic rules go on from R
                lev.append({"t": t, "v": ag["value"], "src": "accepted_agent", "span": ag.get("span"),
                            "ep": cur["open"], "old": cur["base"], "act": ag.get("id")})
                cur = None
                R, R_used = ag["value"], []
                state = "ok"
                continue
        lw7 = lworse(fam, V7[t - sh], cur["base"])
        if lw7 is not None:
            cur["max_worse"] = max(cur["max_worse"], _rel(fam, lw7))
        closed = None
        if unknown:
            cur["rec"] = 0                    # an unknown spend day neither recovers nor stops anything
        elif sp7 <= 0:
            closed = "stopped"
        elif fam in ("ECPM", "IPU") and sp7 < paid:
            closed = "no_paid"
        else:
            rr = min(P["thr_r"], max(0.05, cur["thr_open"] / 2.0)) if adaptive else P["thr_r"]
            if lw7 is not None and lw7 <= lthr(fam, rr):
                cur["rec"] += 1
            else:
                cur["rec"] = 0
            if cur["rec"] >= P["m_r"]:
                closed = "recovered"
            elif settle and t - cur["open"] >= settle["days"] and _settled(V14, t, sh, settle["days"], settle["band"]):
                if LV and (_pin_at(own, t) is not None or _vetoed(own, cur)):
                    cur.setdefault("suggest", (t, "held"))     # pinned / rejected by the owner: a proposal only
                elif LV and _agent_vetoed(own, cur):
                    pass                                       # the agent kept it open: no settle, never "held"
                else:
                    closed = "settled"
            if LV and not closed and "suggest" not in cur:
                if money and not m_auto and pr.get("money_days") and t - cur["open"] >= pr["money_days"] and \
                        _settled(V14, t, sh, pr["money_days"], pr.get("money_band", 0.10)):
                    cur["suggest"] = (t, "money")             # a money level going down: the owner accepts it
                elif pr.get("open_days") and t - cur["open"] >= pr["open_days"]:
                    cur["suggest"] = (t, "open")              # open 120+ days without getting steady
        if closed:
            cur["close"], cur["why"] = t, closed
            if closed != "settled":           # an accepted level counts as normal afterwards
                spans.append((cur["c"] - sh, t - sh))
            elif LV:
                a_ = t - LV.get("accept_days", 28) + 1 - sh
                acc = ser.value(fam, a_, t - sh) if ser.clean(a_, t - sh) else None
                if acc is None:
                    acc, a_ = V14[t - sh], t - 13 - sh
                if acc:
                    R, R_used = acc, [t - sh]
                    lev.append({"t": t, "v": R, "src": "accepted", "span": (a_, t - sh), "ep": cur["open"],
                                "old": cur["base"]})
            eps.append(cur)
            cur = None
            state = "ok"
        else:
            state = "open"
    if cur is not None:
        cur["close"], cur["why"] = None, None
        eps.append(cur)
    return eps, state, lev


def _pin_at(own, t):
    """The owner's level in force on day t (the last pin before or on t, unless an "auto" came after it), else None."""
    cur = None
    for a in own or ():
        if a["day"] > t:
            break
        if a["act"] == "pin":
            cur = a
        elif a["act"] == "auto":
            cur = None
    return cur


def _vetoed(own, cur):
    """The owner rejected the automatic acceptance of THIS episode (matched by its opening day, ±7 days)."""
    return any(a["act"] == "veto" and abs(a["ep_open"] - cur["open"]) <= 7 for a in own or ())


def _agent_vetoed(own, cur):
    """The agent kept THIS episode open (its settle was blocked, or the agent reverted an acceptance), ±7 days."""
    return any(a["act"] == "agent_veto" and abs(a["ep_open"] - cur["open"]) <= 7 for a in own or ())


def _agent_at(own, t, cur):
    """The agent's acceptance of THIS episode on day t, else None."""
    return next((a for a in own or () if a["act"] == "agent" and a["day"] == t
                 and abs(a["ep_open"] - cur["open"]) <= 7), None)


def _steady(V14, t, spans, sh, h, cfg):
    """The newest n clean 14-day windows (as H reads them) all within ±band of the new level h."""
    if not cfg:
        return True
    n, band = cfg
    got = 0
    for j in range(11):
        b = t - 14 - 7 * j - sh
        a = b - 13
        if a < 0:
            break
        if spans and any(not (b < s0 or a > s1) for s0, s1 in spans):
            continue
        v = V14[b]
        if v is None:
            continue
        if abs(v / h - 1.0) > band:
            return False
        got += 1
        if got >= n:
            return True
    return got >= n


def tier(ep):
    """ALERT (push + card) · WATCH (card line) · LINE (detail only) of one episode (campaign / country → LINE)."""
    if ep["kind"] != "app":
        return "LINE"
    f = ep["fam"]
    if f == "ROAS_G":
        return "ALERT" if ep.get("confirm") in (None, "confirmed", "no_data") else "WATCH"
    if f == "GAP":
        return "ALERT"
    if f == "CPI":
        g = (ep.get("ctx") or {}).get("GAP")
        return "ALERT" if (g is not None and g >= 0.5 * ep["thr_open"]) else "WATCH"
    if f == "ROAS_C7" and ep["opener"] == "ABSOLUTE":
        return "ALERT"
    if f.startswith("ROAS_C"):
        return "LINE"
    return "WATCH"


def _country_ok(e, n, apps, cfg, t):
    """A country line is replayed only when it is big enough over the trailing `days` days at t (no look-ahead)."""
    sp = e.s.get("sp_usd") or []
    w = cfg["days"]
    mine = sum(x for x in sp[max(0, n - w):n] if x)
    if mine < cfg["usd"]:
        return False
    a = apps.get(e.app)
    if a is None:
        return True
    an = (date.fromisoformat(t) - date.fromisoformat(a.day0)).days + 1
    asp = a.s.get("sp_usd") or []
    tot = sum(x for x in asp[max(0, an - w):max(0, an)] if x)
    return tot > 0 and mine >= cfg["share"] * tot


def run(ents, P, t, owner=None):
    """Replay every entity from its start to data day t (ISO). Returns
    {"episodes": [Episode dict …], "normal": {(kind, id): {fam: list[float|None]}},   # B while open, else H (R)
     "healthy": {(kind, id): {fam: list[float|None]}},   # H per day, all spans known at t (P["levels"]: R in force)
     "state": {(kind, id): {fam: "open"|"arming"|"gated"|"warm"|"na"|"ok"}},
     "levels": {(kind, id): {fam: [level row …]}},       # P["levels"] only (apps), oldest first
     "proposals": {(kind, id): [proposal …]}}            # P["levels"] only (apps): open alarms the owner may accept
    normal / healthy are produced for app entities and fams CPI, ECPM, ROAS_G, GAP, IPU, ROAS_C0, and for country
    entities and fams CPI, ECPM (index = day index from the entity's day0, 0..t). With P["levels"] a replayed entity's
    healthy level is the resting level R its replay used that day (countries too: their alarms judge against R); a
    country line the eligibility rule leaves out is not replayed (no episode, no level, state "na") but still gets its
    healthy level H from the median rule (no span to leave out: its normal = H). owner (P["levels"] only):
    {(app id, fam): [{"act": "pin", "day", "value", "src", "days": [a, b] | None, "id"} | {"act": "auto", "day"} |
    {"act": "veto", "ep_open"} | {"act": "agent", "day", "days": [a, b], "value", "ep_open", "id"} | {"act":
    "agent_veto", "ep_open", "id"}]} with ISO days — the owner's level from its day (an open alarm closes "owner"),
    back to the automatic rule, an automatic acceptance that never happened; the level agent's acceptance of the open
    episode matching ep_open (±7) on its day (closes "agent", level row "accepted_agent"; the owner's pin wins) and
    its veto of one episode (never settled, never "held"). Inputs are never modified."""
    episodes, normal, healthy, state, levels, props = [], {}, {}, {}, {}, {}
    apps = {e.id: e for e in ents if e.kind == "app"}
    LV = P.get("levels")
    for e in ents:
        key = (e.kind, e.id)
        fams = FAMS_BY_KIND[e.kind]
        n = (date.fromisoformat(t) - date.fromisoformat(e.day0)).days + 1
        st = {f: "na" for f in fams}
        state[key] = st
        if n <= 0:
            continue
        elig = not (e.kind == "country" and P.get("country_elig") and not _country_ok(e, n, apps, P["country_elig"], t))
        ser = _Ser(e, n, P)
        t1 = n - 1
        res = {}
        lv = {}
        if elig and ser.first is not None:
            t0 = max(ser.first + 21, 28)
            for fam in fams:
                if not ser.applicable(fam):
                    continue
                if t0 > t1:
                    st[fam] = "warm"
                    continue
                own = _own(owner, e, fam) if (LV and owner and e.kind == "app") else ()
                eps, st[fam], lv[fam] = _run_family(e, ser, fam, P, t0, t1, own)
                res[fam] = eps
                for x in eps:
                    episodes.append(_episode(e, ser, x, P, t1))
        if e.kind == "app":
            normal[key], healthy[key] = _levels(ser, res, t1, lv=lv if LV else None)
            if LV:
                levels[key] = {f: [_lv_row(e, x) for x in v] for f, v in lv.items() if v}
                props[key] = _proposals(e, ser, res, P, t1)
        elif e.kind == "country":
            # a replayed line: the level its alarms used (R with P["levels"]); a left-out line: H (no level was used)
            normal[key], healthy[key] = _levels(ser, res, t1, CTY_OUT_FAMS, lv if (LV and elig) else None)
    out = {"episodes": episodes, "normal": normal, "healthy": healthy, "state": state}
    if LV:
        out["levels"], out["proposals"] = levels, props
    return out


def _ix(day0, d):
    return (date.fromisoformat(d) - date.fromisoformat(day0)).days


def _own(owner, e, fam):
    """The owner's primitives of one app family → day indexes on the entity, sorted by day (a veto has no day)."""
    out = []
    for a in owner.get((e.id, fam)) or ():
        x = dict(a)
        x["day"] = _ix(e.day0, a["day"]) if a.get("day") else -10 ** 9
        if a.get("ep_open"):
            x["ep_open"] = _ix(e.day0, a["ep_open"])
        if a.get("days"):
            x["span"] = (_ix(e.day0, a["days"][0]), _ix(e.day0, a["days"][1]))
        out.append(x)
    out.sort(key=lambda z: z["day"])
    return out


def _lv_row(e, x):
    """An internal level row → {"day" (the data day it formed), "v", "src", "days": [first, last] the exact named days
    (None: a value typed by the owner), "ep": {"opened", "old"} (accepted), "act" (the owner action)}."""
    d0 = e.day0
    out = {"day": _iso(d0, x["t"]), "v": x["v"], "src": x["src"],
           "days": [_iso(d0, x["span"][0]), _iso(d0, x["span"][1])] if x.get("span") else None}
    if x.get("ep") is not None:
        out["ep"] = {"opened": _iso(d0, x["ep"]), "old": x["old"]}
    if x.get("act"):
        out["act"] = x["act"]
    return out


def _proposals(e, ser, res, P, t1):
    """Open app episodes the owner may close by accepting a new level: a money level steady money_days days ("money"),
    open open_days+ days ("open"), an acceptance that a pin or a rejection held back ("held"). Each: fam, opened, day
    (the first day it was proposed), v = the exact value of the last accept_days data days (days), gap = cost − value ÷
    the old level since that day (money families and CPI: what accepting would stop counting)."""
    LV = P["levels"]
    out = []
    for fam, eps in sorted(res.items()):
        x = eps[-1] if eps else None
        if not x or x["close"] is not None or not x.get("suggest"):
            continue
        sh = FAMILIES[fam]["shift"]
        a = t1 - LV.get("accept_days", 28) + 1 - sh
        v = ser.value(fam, a, t1 - sh) if ser.clean(a, t1 - sh) else None
        if v is None or v <= 0:                      # nothing to propose: a level worth 0 has no ratio to alarm against
            continue
        day, why = x["suggest"]
        g = None
        if fam in MONEY_FAMS or (fam == "CPI" and P.get("money_cpi") and ser.cpi_inr):
            m = _ep_money(e, ser, fam, day - sh, t1 - sh, x["base"])
            g = {"inr": m["since_c_inr"], "usd": m["since_c_usd"]} if m else None
        out.append({"fam": fam, "opened": _iso(e.day0, x["open"]), "day": _iso(e.day0, day), "why": why, "v": v,
                    "days": [_iso(e.day0, a), _iso(e.day0, t1 - sh)], "old": x["base"], "gap": g})
    return out


def _r_series(rows, n):
    """The level in force per day from the level rows (each from its day on), None before the first."""
    out = [None] * n
    for i, x in enumerate(rows):
        hi = rows[i + 1]["t"] if i + 1 < len(rows) else n
        for d in range(max(0, x["t"]), min(n, hi)):
            out[d] = x["v"]
    return out


def _levels(ser, res, t1, fams=OUT_FAMS, lv=None):
    """Per day: H (the healthy level with every span known at t; lv given: the resting level R the replay used that
    day) and the normal (B while an episode is open)."""
    nrm, hl = {}, {}
    n = t1 + 1
    for fam in fams:
        if not (ser.first is not None and ser.applicable(fam)):
            nrm[fam] = [None] * n
            hl[fam] = [None] * n
            continue
        eps = res.get(fam, [])
        if lv is not None:
            H = _r_series(lv.get(fam) or [], n)
            N = list(H)
            for x in eps:
                for d in range(x["open"], x["close"] if x["close"] is not None else n):
                    N[d] = x["base"]
            hl[fam], nrm[fam] = H, N
            continue
        sh = FAMILIES[fam]["shift"]
        _, V14, _ = ser.series(fam)
        spans = [(x["c"] - sh, (x["close"] if x["close"] is not None else t1) - sh)
                 for x in eps if x["why"] != "settled"]
        bad = [False] * n                      # the 14-day window ending b touches a span
        for s0, s1 in spans:
            for b in range(max(0, s0), min(n, s1 + 14)):
                bad[b] = True
        H = [None] * n
        for d in range(n):
            vals = []
            for j in range(11):
                b = d - 14 - 7 * j - sh
                if b - 13 < 0:
                    break
                if bad[b]:
                    continue
                v = V14[b]
                if v is not None:
                    vals.append(v)
            if len(vals) >= 4:
                H[d] = _median(vals)
        N = list(H)
        for x in eps:
            for d in range(x["open"], x["close"] if x["close"] is not None else n):
                N[d] = x["base"]
        hl[fam], nrm[fam] = H, N
    return nrm, hl


def _episode(e, ser, x, P, t1):
    fam = x["fam"]
    sh = FAMILIES[fam]["shift"]
    d0 = e.day0
    opened = _iso(d0, x["open"])
    c = x["c"] - sh
    money = None
    if fam in MONEY_FAMS or (fam == "CPI" and P.get("money_cpi") and ser.cpi_inr):
        end = (x["close"] if x["close"] is not None else t1) - sh
        money = _ep_money(e, ser, fam, c, end, x["base"])
    ep = {"kind": e.kind, "id": e.id, "app": e.app, "fam": fam, "opener": x["opener"], "tier": None,
          "c": _iso(d0, c), "opened": opened, "seen": _iso(d0, x["open"] + 2),
          "closed": _iso(d0, x["close"]) if x["close"] is not None else None, "why": x["why"],
          "base": x["base"], "base_src": x["base_src"], "thr_open": x["thr_open"], "max_worse": x["max_worse"],
          "esc": [[_iso(d0, d), k] for d, k in zip(x["esc"], x["esc_kind"])], "confirm": x["confirm"],
          "ctx": x["ctx"], "money": money, "stake": [round(v, 2) for v in x["stake"]]}
    if P.get("levels"):
        bs = x.get("bspan")
        ep["bspan"] = [_iso(d0, bs[0]), _iso(d0, bs[1])] if bs else None
        ep["suggest"] = [_iso(d0, x["suggest"][0]), x["suggest"][1]] if x.get("suggest") else None
    ep["tier"] = tier(ep)
    return ep


# ── a level's exact value (the build's owner actions and its exactness check; the page recomputes the same) ─────────

LEVEL_SUMS = {"CPI": ("sp_inr", "sp_usd", "inst"), "ECPM": ("rev", "imp"), "GAP": ("sp_usd", "inst", "imp", "rev"),
              "IPU": ("imp", "dau"), "ROAS_G": ("d0_inr", "sp_inr", "sp_usd"), "ROAS_C0": ("c_r0", "c_sp"),
              "ROAS_C1": ("c_r1", "c_sp"), "ROAS_C7": ("c_r7", "c_sp"), "SPEND": ("sp_usd",)}


def level_of(fam, sums, nd, P):
    """The family value from the sums of its named days (nd days) — the same ratio of sums as the replay."""
    g = sums.get
    try:
        if fam == "CPI":
            return (g("sp_inr") if P.get("cpi_ccy") == "inr" else g("sp_usd")) / g("inst")
        if fam == "ECPM":
            return g("rev") / g("imp") * 1000.0
        if fam == "GAP":
            return (g("sp_usd") / g("inst")) * (g("imp") / g("rev"))
        if fam == "IPU":
            return g("imp") / g("dau")
        if fam == "ROAS_G":
            return g("d0_inr") / g("sp_inr")
        if fam.startswith("ROAS_C"):
            return g(FAMILIES[fam]["num"]) / g("c_sp")
        if fam == "SPEND":
            return g("sp_usd") / nd
    except (TypeError, ZeroDivisionError):
        return None
    return None


def measure(ent, P, fam, a, b):
    """The exact level of days a..b (ISO, inclusive, the family's own day index) on one entity: {"v", "sums", "days",
    "n"} — v as the replay computes it (its gates: a thin or unknown window → None), sums = the plain sums of the named
    days (level_of(fam, sums, n) == v)."""
    i0, i1 = _ix(ent.day0, a), _ix(ent.day0, b)
    if i0 < 0 or i1 < i0:
        return None
    ser = _Ser(ent, i1 + 1, P)
    if fam not in FAMILIES or not ser.applicable(fam):
        return None
    v = ser.value(fam, i0, i1)
    if v is None:
        return None
    sums = {}
    for k in LEVEL_SUMS[fam]:
        if k == "sp_inr" and fam == "CPI" and not ser.cpi_inr:
            continue
        arr = ent.s.get(k)
        if arr is None:
            return None
        sums[k] = math.fsum(x for x in arr[i0:i1 + 1] if x is not None)
    return {"v": v, "sums": sums, "days": [a, b], "n": i1 - i0 + 1}


def notifications(episodes, tiers=("ALERT",), gap=7):
    """What gets PUSHED: per app, the openings and re-notices of the given tiers, one push per `gap` days (an event
    within `gap` days of a push's first event joins that push). Each push: day, app, items, stake (USD at stake in
    the 7 days before the notice vs the frozen baseline, the largest item)."""
    by = {}
    for ep in episodes:
        if ep["tier"] not in tiers:
            continue
        ev = by.setdefault(ep["app"], [])
        ev.append((ep["opened"], "open", ep, ep["stake"][0] if ep.get("stake") else None))
        for i, (d, _) in enumerate(ep["esc"]):
            st = ep["stake"][i + 1] if ep.get("stake") and len(ep["stake"]) > i + 1 else None
            ev.append((d, "esc", ep, st))
    out = []
    for app, ev in by.items():
        ev.sort(key=lambda z: z[0])
        last = None
        for d, kind, ep, st in ev:
            if last is not None and (date.fromisoformat(d) - date.fromisoformat(last["day"])).days <= gap:
                last["items"].append({"kind": kind, "fam": ep["fam"], "opener": ep["opener"], "opened": ep["opened"]})
                if st is not None:
                    last["stake"] = max(last["stake"] if last["stake"] is not None else st, st)
                continue
            last = {"day": d, "app": app, "items": [{"kind": kind, "fam": ep["fam"], "opener": ep["opener"],
                                                     "opened": ep["opened"]}], "stake": st}
            out.append(last)
    out.sort(key=lambda z: (z["day"], z["app"]))
    return out


def cards(episodes, gap=7, kinds=("app",)):
    """One card per app per stretch of time: episodes (any family) whose open spans overlap or touch within `gap`
    days are merged. Each card: app, open, close (None while any is open), episodes."""
    by = {}
    for ep in episodes:
        if ep["kind"] in kinds:
            by.setdefault(ep["app"], []).append(ep)
    out = []
    for app, lst in by.items():
        spans = sorted(([date.fromisoformat(ep["opened"]),
                         date.fromisoformat(ep["closed"]) if ep["closed"] else None, [ep]] for ep in lst),
                       key=lambda z: z[0])
        merged = []
        for s in spans:
            if merged and (merged[-1][1] is None or s[0] <= merged[-1][1] + timedelta(days=gap)):
                m = merged[-1]
                m[1] = None if (m[1] is None or s[1] is None) else max(m[1], s[1])
                m[2].extend(s[2])
            else:
                merged.append(s)
        for a, b, eps in merged:
            out.append({"app": app, "open": a.isoformat(), "close": b.isoformat() if b else None, "episodes": eps})
    out.sort(key=lambda z: (z["open"], z["app"]))
    return out
