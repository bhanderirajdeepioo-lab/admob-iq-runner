"""📈 ROI — the build step of the Install value tab's ROI section (owner, 13 Oct 2026: "every date wise uska incremental
day wise revenue from first day of the app … delta, breakeven, % wise", "dono karo, AdMob matched, sirf google ads",
"country wise … konsa country rakhna he konsa nikalna he, konsi me jaldi roi milta he", and "taki bahot saare tab na ban
jaye": a section of 💸 Install value, never a tab of its own). It never changes anything the tab already shows: it only
READS the install-day file, the Install value engine's own scale and completeness rules, the Google Ads spend cache, the
AdMob revenue and the app's value_<key>.json.gz, and writes files of its own.

Per app, roi_<key>.json.gz (every number USD; AdMob-matched = GA4's split × the engine's AdMob ÷ GA4 scale k, the same
k the tab uses):
  * rows — EVERY install day from the GA4 history start to today:
      [X, n (GA4 new users), n_ads (Google Ads installs), spend (Google Ads, USD at that day's rate; null = unknown),
       d (cumulative revenue on day 0, 1, … of the install day — fetch.ga4_cohort, as far as observed),
       df (how many of d are final), u (users active on day 0, 1, …), t (cumulative revenue at day 0, 1, 3, 7, 14, 30,
       60, 90, 180, 365 — only when complete), s (revenue so far), sd (so far = through this day), be (the breakeven
       day: [day, exact?] or null), st (status: Worse / Watch / Better / Normal / Too early / N/A), q (≈: a day of it
       did not tie to the install-day read)]
  * sum — Today / Yesterday, CPI, ROAS at each age (last 7 judged install days vs the 28 before), LTV, retention,
    the payback day of the recent install days (pooled), status, data quality (GA4 coverage, the tie check);
  * life — AdMob revenue and Google Ads spend of EVERY day from the app's first day (lifetime P/L, month-wise on the
    page);
  * cty — the countries board: the engine's own country rows turned into Scale / Keep / Watch / Cut / Too little data /
    Too early, ROAS at 7 / 30 / 90 days, payback, cost per install, and what cutting the Cut countries saves; and
    every country by install month (installs, Google Ads cost, ROAS 7 / 30 / 90);
  * f4 — ⚖️ the four forms of install-day ROI at D7 / D30 / D90 (+ the payback target): blended, paid-only,
    incremental and marginal, each unmeasured input as its research range [low, central, high] (beta: the app's own
    measured range from config/roi_beta.json when there is one), the paid share (Google Ads installs ÷ GA4 installs),
    and the budget call from the marginal form (see F4_* below). Once GA4's own paid cells (IDAY_EXT cp) cover an
    age, that age uses GA4's MEASURED paid share and premium instead of the premium range (src "ga4", see _ga4p).
roi.json.gz — every app's summary row (with its f4), the portfolio lifetime P/L and the portfolio install days (apps
with spend), and the ranges the forms used (f4c).
Pointer: dashboard["roi"] = {"file", "v", "apps": {app_id: {"file", "st", "r7", "u7", "pb", "lp"}}}.
One splat header rule (/roi*). Failure-isolated per app (counted) and as a whole; ONE counts-only line.
"""
import gzip
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

from .db import write_json_gz_stable
from .engine import value as val
from .fetch import ga4_cohort as gco
from .fetch import ga4_uninstall as gu

ALL_FILE = "roi.json.gz"
PREFIX = "roi_"
FILE_RE = re.compile(r"^roi_[0-9a-f]{12}\.json\.gz$")
HEADER_PATHS = ["/roi*"]
V = 1
T = val.T                                   # 0, 1, 3, 7, 14, 30, 60, 90, 180, 365
J7 = T.index(7)
N_RECENT, N_USUAL = 7, 28                   # install days: the last 7 judged vs the 28 before
MIN_SPEND, MIN_N = 5.0, 30                  # a judged install day: ≥ $5 Google Ads and ≥ 30 installs
MIN_MONTH_SPEND = 100.0                     # an install month whose curve tells the payback: ≥ $100 Google Ads
MATURE = 90                                 # … and whose curve reached day 90 (an older month is not "now")
ULAG_IX = {1: 1, 3: 2, 7: 3, 14: 4, 30: 5}  # iday u slots (fetch.ga4_uninstall.ULAGS) of those lags
WORSE, WATCH, BETTER = 0.75, 0.90, 1.15     # D7 ROAS ÷ usual
TIE_REL, TIE_ABS = 0.02, 1.0                # an activity day ties when within 2% or $1 of the install-day read
# ⚖️ The four forms of install-day ROI (owner research, Oct 2026): BLENDED = all GA4 installs' revenue ÷ spend (what
# this section shows), PAID-ONLY = the Google Ads installs' own revenue ÷ spend, INCREMENTAL = only the revenue the
# spend caused ÷ spend, MARGINAL = what the NEXT $ brings = incremental × (1 + beta) — the one that decides budget.
# The paid share s = Google Ads installs ÷ GA4 installs of the same install days (measured, capped at 1). The three
# inputs not measured yet are the research's RANGES (until GA4 paid / organic data arrives), never one number; each
# tuple is ordered so the form goes low → central → high:
F4_P = (1.15, 1.4, 3.2)                     # p: paid ÷ organic revenue per install (methods disagree: not settled);
F4_PA = 30                                  # … measured at D30 only: D7 / D90 / H assume the same range (page says so)
F4_B = (0.88, 0.47, 0.15)                   # b: share of "organic" installs that come anyway (after-stop ratios)
F4_BETA = (-0.19, -0.07, -0.03)             # beta: elasticity of ROAS to spend (pooled over the apps); an app's own
F4_BETA_FILE = "roi_beta.json"              # measured range, when there is one, in config/roi_beta.json (see _betas)
F4_AGES = (7, 30, 90)                       # the forms at these ages (+ the payback target H) where complete
F4_GAP = 0.20                               # paid-only ≥ 20% below blended (central p): flagged (organic-heavy)
F4_LIVE = 14                                # spend days: an app buys now when any of its last 14 had ≥ MIN_SPEND
# GA4's own paid / organic split (IDAY_EXT's cp cells: users whose first Google Ads campaign id is a real one): once an
# age has it, its paid share and premium p are MEASURED and replace the p range (b and beta stay ranges):
F4_PW = 4                                   # p from the newest 4 install weeks whose paid cells are whole at that age
F4_PMIN = 100                               # … with ≥ 100 paid AND ≥ 100 organic installs (else no premium: the range)
F4_SCOV = 0.5                               # the window's GA4 paid share: from ≥ half of its install days
LINE = None


def enabled(s):
    return bool((s or {}).get("roi_tab", True))


def _r(v, n=4):
    return None if v is None else round(float(v), n)


def _d(s):
    return date.fromisoformat(s)


def _iso(d):
    return d.isoformat()


def _status(r, usual):
    if r is None or usual is None or usual <= 0:
        return "N/A"
    q = r / usual
    return "Worse" if q <= WORSE else "Watch" if q <= WATCH else "Better" if q >= BETTER else "Normal"


class Acc:
    """The portfolio, gathered app by app."""

    def __init__(self):
        self.apps, self.life, self.rows, self.fails, self.skipped, self.till, self.ccy = [], {}, {}, 0, 0, [], set()
        self.fc = None                              # 🔮 the forecast step's run (forecast_build), made on the first app
        self.beta = None                            # ⚖️ per-app beta ranges (config/roi_beta.json), read on the first app
        self.f4m = 0                                # ⚖️ apps whose forms use GA4's measured paid share + premium


def start():
    return Acc()


# ── one app ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _tie_off(ida, co_x, pr_days):
    """Activity days whose lag 0 … 29 revenue (this store) does not tie to the install-day Q-B read (ABANDS 0..2)."""
    sums = {}
    for X, c in co_x.items():
        try:
            x0 = _d(X)
        except ValueError:
            continue
        for L in range(30):
            v = (c.get("r") or [0] * 31)[L] if L < len(c.get("r") or []) else 0
            k = _iso(x0 + timedelta(days=L))
            sums[k] = sums.get(k, 0) + (v or 0)
    off, checked = set(), 0
    for D, e in (pr_days or {}).items():
        rb = e.get("rb") if isinstance(e, dict) else None
        if not isinstance(rb, list) or len(rb) < 3 or e.get("st") not in val.GOOD or D not in sums:
            continue
        checked += 1
        q = sum(int(v or 0) for v in rb[:3])
        diff = abs(sums[D] - q) / 1e6
        if diff > TIE_ABS and diff > TIE_REL * max(q / 1e6, 1e-9):
            off.add(D)
    return off, checked


def _cohorts(P, spend, fxf, co, today):
    """Every install day → its row (see the module doc) — oldest first."""
    pr, kf, xs, S, hs = P["pre"], P["sc"]["kf"], P["xs"], P["S"], P["hs"]
    co_x = (co or {}).get("x") or {}
    newest = _d(co["read_today"]) if co and co.get("read_today") else None
    C = newest - timedelta(days=gco.FINAL_LAG) if newest else None
    keys = {X for X in xs} | {_d(k) for k in co_x if k >= _iso(hs)}
    if newest:
        keys = {X for X in keys if X <= newest}
    sp_first = _d(spend["first"]) if spend and spend.get("first") else None
    sp_till = _d(spend["till"]) if spend and spend.get("till") else None
    rows = []
    for X in sorted(keys):
        e, c = xs.get(X), co_x.get(_iso(X))
        n = e["n"] if e else (int((c.get("u") or [0])[0] or 0) if c else 0)
        sp = spi = None
        n_ads = None
        if spend and sp_first and sp_till and sp_first <= X <= sp_till:
            spi = (spend["daily"].get(_iso(X)) or 0) / 1e6           # as billed (the spend cache's own currency)
            sp = spi * (fxf(X) or 0)                                 # USD at that day's rate
            n_ads = spend["installs"].get(_iso(X))
        d = u = None
        df = 0
        if c and newest:
            obs = min(gco.LAGS - 1, (newest - X).days)
            if obs >= 0:
                d, u, cum = [], [], 0.0
                r, uu = c.get("r") or [], c.get("u") or []
                for L in range(obs + 1):
                    cum += (r[L] if L < len(r) else 0) / 1e6 * kf(X + timedelta(days=L))[0]
                    d.append(_r(cum))
                    u.append(int(uu[L] if L < len(uu) else 0))
                df = max(0, min(obs, (C - X).days) + 1)
        t = [None] * len(T)
        for j, a in enumerate(T):
            if a <= 30 and d is not None and a < df:
                t[j] = d[a]
            elif e and pr.all(pr.g, X, X + timedelta(days=a)) and pr.win_ok(X, X, X + timedelta(days=a)):
                if a <= 30:
                    t[j] = _r(e["R"][j])
                else:
                    base = d[30] if (d is not None and df > 30) else e["R"][5]
                    t[j] = _r(base + e["R"][j] - e["R"][5])
        # so far: the read that reaches furthest (the install-day read through S, this store through `newest`)
        s = sd = None
        if e and X <= S:
            base = d[30] if (d is not None and df > 30) else None
            s = _r(base + e["R"][9] - e["R"][5]) if base is not None else _r(e["R"][9])
            sd = _iso(S)
        if d is not None and (sd is None or X + timedelta(days=len(d) - 1) > _d(sd)):
            s, sd = d[-1], _iso(X + timedelta(days=len(d) - 1))
        be = None
        if sp and sp > 0:
            for L, v in enumerate(d or []):
                if v is not None and v >= sp:
                    be = [L, L < df]
                    break
            if be is None:
                for j, a in enumerate(T):
                    if t[j] is not None and t[j] >= sp and not (d is not None and a < len(d)):
                        be = [a, False]
                        break
        iu = {L: int(e["u"][i]) for L, i in ULAG_IX.items()
              if e and pr.all(pr.g, X, X + timedelta(days=L))} if e else {}
        rows.append({"X": X, "n": n, "na": n_ads, "sp": sp, "spi": spi, "d": d, "df": df, "u": u, "t": t, "s": s,
                     "sd": sd, "be": be, "e": e, "iu": iu})
    return rows


def _judged(r):
    return r["sp"] is not None and r["sp"] >= MIN_SPEND and r["n"] >= MIN_N


def _win(rows, j, recent=True):
    """The newest N_RECENT judged install days complete at age T[j] (recent) or the N_USUAL before them (usual)."""
    have = [r for r in rows if _judged(r) and r["t"][j] is not None]
    return have[-N_RECENT:] if recent else have[-(N_RECENT + N_USUAL):-N_RECENT]


def _pool(rows, j, recent=True):
    """ROAS and LTV at age T[j] over _win — ratios of sums."""
    have = _win(rows, j, recent)
    if not have:
        return None
    sp, rv, n = sum(r["sp"] for r in have), sum(r["t"][j] for r in have), sum(r["n"] for r in have)
    return {"roas": _r(rv / sp) if sp else None, "ltv": _r(rv / n, 6) if n else None, "n": len(have),
            "from": _iso(have[0]["X"]), "to": _iso(have[-1]["X"])}


def _statuses(rows):
    """Each install day's status: its D7 ROAS vs the pooled D7 ROAS of the N_USUAL judged install days before it."""
    prev = []
    for r in rows:
        if not _judged(r):
            r["st"] = "N/A"
        elif r["t"][J7] is None:
            r["st"] = "Too early"
        else:
            base = prev[-N_USUAL:]
            sp = sum(x["sp"] for x in base)
            usual = (sum(x["t"][J7] for x in base) / sp) if len(base) >= 7 and sp else None
            r["st"] = _status(r["t"][J7] / r["sp"], usual) if usual else "Too early"
            prev.append(r)


def _months(rows):
    """Install months: [month, installs, spend, revenue at each age, days, days with spend] — an age's revenue only
    when EVERY install day of the month is complete at that age (one set of install days per curve: it never dips)."""
    g = {}
    for r in rows:
        m = _iso(r["X"])[:7]
        e = g.setdefault(m, {"n": 0, "sp": 0.0, "spi": 0.0, "spk": True, "t": [0.0] * len(T), "ok": [True] * len(T),
                             "days": 0, "dsp": 0})
        e["n"] += r["n"]
        e["days"] += 1
        if r["sp"] is None:
            e["spk"] = False
        else:
            e["sp"] += r["sp"]
            e["spi"] += r.get("spi") or 0
            e["dsp"] += 1 if r["sp"] > 0 else 0
        for j in range(len(T)):
            if r["t"][j] is None:
                e["ok"][j] = False
            else:
                e["t"][j] += r["t"][j]
    return [[m, e["n"], _r(e["sp"]) if e["spk"] else None,
             [(_r(e["t"][j]) if e["ok"][j] else None) for j in range(len(T))], e["days"], e["dsp"],
             _r(e["spi"], 2) if e["spk"] else None]
            for m, e in sorted(g.items())]


def _payback(curve):
    """[(age, roas)] ascending → the first age the pooled ROAS reaches 100% (linear between ages), else None."""
    last = (0, 0.0)
    for a, v in curve:
        if v is None:
            continue
        if v >= 1.0:
            a0, v0 = last
            return round(a0 + (a - a0) * (1.0 - v0) / (v - v0)) if v > v0 else a
        last = (a, v)
    return None


def _ret(rows, lag, recent=True):
    """Users still active on day `lag` per 100 installs (exact store), pooled over the newest judged install days."""
    def users(r):
        if r["u"] is not None and lag < r["df"]:
            return r["u"][lag]
        return r["iu"].get(lag)
    have = [r for r in rows if r["n"] and users(r) is not None]
    have = have[-N_RECENT:] if recent else have[-(N_RECENT + N_USUAL):-N_RECENT]
    n = sum(r["n"] for r in have)
    return _r(sum(users(r) for r in have) / n, 4) if n else None


def _betas(data_dir):
    """An app's own measured beta range (config/roi_beta.json next to data/: {app id: [low, central, high]}, e.g. from
    a clean spend-step study of that app). Only well-formed ranges are kept: three numbers in −1 … +0.5, low ≤ central
    ≤ high. Missing / unreadable file or app → the pooled F4_BETA."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(data_dir)), "config", F4_BETA_FILE),
                  encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    out = {}
    for k, v in (raw if isinstance(raw, dict) else {}).items():
        try:
            t = tuple(float(x) for x in v)
        except (TypeError, ValueError):
            continue
        if len(t) == 3 and all(-1.0 < x <= 0.5 for x in t) and t[0] <= t[1] <= t[2]:
            out[str(k)] = t
    return out


def _f4(bl, s, beta=F4_BETA, prem=F4_P):
    """Blended ROAS + paid share → the other three forms (and the blended-over-paid gap), each [low, central, high]:
    every unmeasured input at its own end of its range, so low / high are the worst / best case over all of them.
    prem: the premium range, or (p, p, p) once GA4 measured it (paid-only and the gap are then one number)."""
    paid = [bl * p * s / (p * s + 1 - s) for p in prem]
    inc = [bl - b * (bl - x) for b, x in zip(F4_B, paid)]          # the organic part times (1 − the part that comes anyway)
    mar = [v * (1 + be) for v, be in zip(inc, beta)]
    gap = [(1 - s) / (p * s + 1 - s) for p in reversed(prem)]     # 1 − paid ÷ blended: smallest at the highest p
    return {"paid": [_r(v) for v in paid], "inc": [_r(v) for v in inc], "mar": [_r(v) for v in mar],
            "gap": [_r(v) for v in gap]}


def _ga4p(ida, ages):
    """⚖️ GA4's own paid / organic split from IDAY_EXT's paid cells (fetch.ga4_iday_ext: cp = the users whose first
    Google Ads campaign id is a real one, read from the same full Q-C read as the legacy country cells c) →
    {"share": {install day: GA4 paid share of its new users (the d2 ledger's cpn)},
     "prem": {age: {p: paid ÷ organic revenue per install, s, rs (paid share of installs / of revenue), np, no, w,
                    from, to}}} — p over the newest F4_PW install weeks whose every activity day (the week + the age)
    has BOTH reads folded (cpst and the legacy cst), Σ every country slot (the gap row left out on both sides); None
    when the app has no paid cells yet. Ages past 90 (the legacy cells stop there) or off a band edge: no p."""
    cp, d2 = ida.get("cp") or {}, ida.get("d2") or {}
    if not isinstance(cp, dict) or not isinstance(d2, dict) or not d2:
        return None
    c, days = ida.get("c") or {}, ida.get("days") or {}
    fold = ("ok", "smp", "gap")                     # ga4_iday_ext.FOLDED / engine.value.CGOOD

    def whole(D):
        k = _iso(D)
        return (d2.get(k) or {}).get("cpst") in fold and (days.get(k) or {}).get("cst") in fold
    share = {}
    for D, r in d2.items():
        if isinstance(r, dict) and r.get("cpst") in fold and isinstance(r.get("cpn"), (int, float)):
            share[D] = min(1.0, max(0.0, float(r["cpn"])))

    def tot(slots, nb):
        n = rv = 0
        for k, v in (slots or {}).items():
            if k != "gap" and isinstance(v, dict):
                n += int(v.get("n") or 0)
                rv += sum(int(x or 0) for x in (v.get("r") or [])[:nb])
        return n, rv
    prem = {}
    for a in ages:
        nb = [i + 1 for i, (lo, hi) in enumerate(val.CBANDS) if hi == a]
        if not nb:
            continue
        weeks = []
        for W in sorted(set(cp) & set(c), reverse=True):
            try:
                w0 = _d(W)
            except ValueError:
                continue
            if all(whole(w0 + timedelta(days=i)) for i in range(7 + a)):
                weeks.append(W)
                if len(weeks) >= F4_PW:
                    break
        if not weeks:
            continue
        np_ = na_ = rp = ra = 0
        for W in weeks:
            n1, r1 = tot(cp[W], nb[0])
            n2, r2 = tot(c[W], nb[0])
            np_, rp, na_, ra = np_ + n1, rp + r1, na_ + n2, ra + r2
        no, ro = na_ - np_, ra - rp
        if np_ < F4_PMIN or no < F4_PMIN or rp <= 0 or ro <= 0:
            continue
        prem[str(a)] = {"p": _r((rp / np_) / (ro / no), 3), "s": _r(np_ / na_), "rs": _r(rp / ra), "np": np_,
                        "no": no, "w": len(weeks), "from": weeks[-1], "to": weeks[0]}
    return {"share": share, "prem": prem} if (share or prem) else None


def _decide(by, H):
    """Budget from the MARGINAL form at the payback target H: up (even its low end ≥ 100%), down (even its high end
    < 100%), mixed (100% inside the range); when H is not complete yet a shorter age whose low end is already ≥ 100%
    still says up (revenue only grows with age), else early. na = no paid share (no Google Ads install count) on any
    age."""
    if by and not any(e.get("mar") for e in by.values()):
        return {"a": H, "v": "na", "mar": None}
    e = by.get(str(H))
    if e is not None:
        m = e.get("mar")
        if not m:
            return {"a": H, "v": "na", "mar": None}
        return {"a": H, "v": "up" if m[0] >= 1 else "down" if m[2] < 1 else "mixed", "mar": m}
    for a in sorted((int(k) for k in by), reverse=True):
        m = by[str(a)].get("mar")
        if a < H and m and m[0] >= 1:
            return {"a": a, "v": "up", "mar": m}
    return {"a": H, "v": "early", "mar": None}


def _live(rows):
    """Does the app buy installs now? (a paused app gets no "raise / cut" call, only what its last spend days said)"""
    return any(v >= MIN_SPEND for v in [r["sp"] for r in rows if r["sp"] is not None][-F4_LIVE:])


def _forms(rows, H, beta=None, gp=None):
    """⚖️ The four forms at F4_AGES (+ H): over the SAME install days as the section's own ROAS (_win: newest
    N_RECENT judged, complete at that age), so blended equals the D7 / D30 / D90 ROAS shown. The paid share s = Google
    Ads installs ÷ GA4 installs of the days of them that have a Google Ads install count (always kept, "s"). gp (_ga4p):
    an age with a GA4-measured premium AND the GA4 paid share of ≥ F4_SCOV of its install days uses those two
    (src "ga4", "m": what was measured) instead of the premium range and s; else src "range". beta: the app's own range
    (_betas), else the pooled one."""
    bt = tuple(beta) if beta else F4_BETA
    by = {}
    for a in sorted(set(F4_AGES) | ({H} if H in T else set())):
        have = _win(rows, T.index(a))
        sp = sum(r["sp"] for r in have)
        if not have or sp <= 0:
            continue
        rv = sum(r["t"][T.index(a)] for r in have)
        e = {"bl": _r(rv / sp), "sp": _r(sp), "spi": _r(sum(r.get("spi") or 0 for r in have), 2), "rev": _r(rv),
             "n": sum(r["n"] for r in have), "days": len(have), "from": _iso(have[0]["X"]), "to": _iso(have[-1]["X"])}
        wa = [r for r in have if r["na"] is not None]
        n = sum(r["n"] for r in wa)
        if wa and n > 0:
            e.update(s=_r(min(1.0, sum(r["na"] for r in wa) / n)), na=_r(sum(r["na"] for r in wa), 1), nn=n,
                     days_na=len(wa))
        mp = ((gp or {}).get("prem") or {}).get(str(a))
        cov = [r for r in have if _iso(r["X"]) in ((gp or {}).get("share") or {})] if mp else []
        cn = sum(r["n"] for r in cov)
        if mp and cn > 0 and len(cov) >= F4_SCOV * len(have):
            sm = sum(gp["share"][_iso(r["X"])] * r["n"] for r in cov) / cn
            e.update(src="ga4", m=dict(mp, sw=_r(sm), days=len(cov)), **_f4(rv / sp, sm, bt, (mp["p"],) * 3))
        elif "s" in e:
            e.update(src="range", **_f4(rv / sp, e["s"], bt))
        by[str(a)] = e
    return {"h": H, "by": by, "dec": dict(_decide(by, H), live=_live(rows)), "beta": list(bt),
            "bsrc": "app" if beta else "pool"}


def f4_consts():
    """The ranges the forms used (the page prints these, so a number on screen always names its range)."""
    return {"p": list(F4_P), "b": list(F4_B), "beta": list(F4_BETA), "ages": list(F4_AGES), "gap": F4_GAP,
            "live": F4_LIVE, "pw": F4_PW, "pmin": F4_PMIN, "pa": F4_PA}


def _summary(rows, P, co_off, tie_checked, today):
    pools = {str(a): {"r": _pool(rows, j), "u": _pool(rows, j, False)} for j, a in enumerate(T)}
    # payback: the newest install month (≥ $100 Google Ads, spend on ≥ 80% of its days) whose own curve crossed 100% —
    # but never past the newest MATURE month (its curve reached day 90): if that one has not crossed, "not by day N"
    pb = best = pbm = nb = None
    for m, n, sp, t, days, dsp, _spi in reversed(_months(rows)):
        if not sp or sp < MIN_MONTH_SPEND or dsp < days * 0.8:
            continue
        curve = [(a, (t[j] / sp) if t[j] is not None else None) for j, a in enumerate(T)]
        seen = [(a, v) for a, v in curve if v is not None]
        if best is None and seen:
            best = (seen[-1][0], _r(seen[-1][1]), m)
        p = _payback(curve)
        if p is not None:
            pb, pbm = p, m
            break
        if seen and seen[-1][0] >= MATURE:
            nb = [seen[-1][0], _r(seen[-1][1]), m]
            break
    jud = [r for r in rows if _judged(r)]
    rec = jud[-N_RECENT:]
    cpi = cpi_src = None
    if rec:
        n = sum(r["n"] for r in rec)
        cpi = _r(sum(r["sp"] for r in rec) / n, 6) if n else None
        cpi_src = _r(sum(r.get("spi") or 0 for r in rec) / n, 4) if n else None
    r7, u7 = (pools[str(7)]["r"] or {}).get("roas"), (pools[str(7)]["u"] or {}).get("roas")
    if not jud:
        st = "N/A"
    elif r7 is None or u7 is None:
        st = "Too early"
    else:
        st = _status(r7, u7)
    k = P["sc"]
    cov = None
    try:                                            # GA4 ÷ AdMob over the last 4 whole weeks (the tab's own scale)
        ws = [w for w in (k.get("weeks") or []) if isinstance(w, dict) and w.get("ga4") is not None
              and w.get("admob")][-4:]
        g, m = sum(float(w["ga4"]) for w in ws), sum(float(w["admob"]) for w in ws)
        cov = _r(g / m, 3) if m else None
    except Exception:
        cov = None
    last = rows[-2:] if rows else []
    return {"st": st, "r7": r7, "u7": u7, "pools": pools, "pb": pb, "pbm": pbm, "nb": nb,
            "best": list(best) if best else None,
            "cpi": cpi, "cpi_src": cpi_src, "ret": {str(L): {"r": _ret(rows, L), "u": _ret(rows, L, False)} for L in (1, 3, 7, 14, 30)},
            "cov": cov, "tie": {"checked": tie_checked, "off": len(co_off)},
            "today": [_row_out(r) for r in last]}


def _row_out(r):
    return [_iso(r["X"]), r["n"], _r(r["na"], 2), _r(r["sp"]), r["d"], r["df"], r["u"], r["t"], r["s"], r["sd"],
            r["be"], r.get("st"), 1 if r.get("q") else 0, _r(r.get("spi"), 2)]


def _life(rev, spend, fxf, ded_rate):
    """[[day, AdMob revenue (USD), Google Ads spend (USD at that day's rate), spend as billed]] for every day either has."""
    out = {}
    days = (rev or {}).get("all_days") or (rev or {}).get("days") or {}
    f = 1.0 - float(ded_rate or 0)
    for d, v in days.items():
        if v and v[0]:
            out.setdefault(d, [0.0, 0.0, 0.0])[0] += v[0] / 1e6 * f
    if spend:
        for d, v in (spend.get("daily") or {}).items():
            if v:
                try:
                    e = out.setdefault(d, [0.0, 0.0, 0.0])
                    e[1] += v / 1e6 * (fxf(_d(d)) or 0)
                    e[2] += v / 1e6
                except ValueError:
                    continue
    return [[d, _r(v[0]), _r(v[1]), _r(v[2], 2)] for d, v in sorted(out.items())]


def _life_till(rev, spend):
    """The last day both AdMob revenue and Google Ads spend are in (the lifetime totals stop there; later days: live)."""
    days = (rev or {}).get("all_days") or (rev or {}).get("days") or {}
    a = max((d for d, v in days.items() if v and v[0]), default=None)
    b = (spend or {}).get("till")
    return min(x for x in (a, b) if x) if (a or b) else None


DEC = {"costly": "Cut", "slow": "Watch", "few": "Too little data", "wait": "Too early", "late": "Too early",
       "top": "Better", "low": "Worse", "avg": "Normal"}


def _countries(detail, H):
    c = (detail or {}).get("countries") or {}
    rows = []
    for r in c.get("rows") or []:
        v = r.get("verdict")
        pay = r.get("pay") or {}
        if v == "keep":
            dec = "Scale" if (pay.get("p") is not None and pay["p"] <= H / 2 and r.get("sure")) else "Keep"
        else:
            dec = DEC.get(v, "Normal")
        cp = r.get("cpi") or {}
        back = r.get("back") or {}
        rpi = r.get("rpi") or {}
        rows.append({"cc": r.get("cc"), "dec": dec, "eng": v, "n": r.get("n"), "share": r.get("share"),
                     "cpi": cp.get("v"), "cpi_ads": cp.get("ads"), "spend": cp.get("spend"), "dl": cp.get("dl"),
                     "spend_src": cp.get("spend_src"), "cpi_src": cp.get("src"),
                     "paid": cp.get("paid"),
                     "back": {k: back.get(k) for k in ("7", "30", "90")} if back else None,
                     "back_est": bool(back.get("90_est") or back.get("30_est")) if back else False,
                     "back_proj": bool(back.get("90_proj")) if back else False,
                     "rpi": {k: (rpi.get(k) or {}).get("v") for k in ("1", "7", "30", "90")},
                     "pay": {k: pay.get(k) for k in ("p", "lo", "hi", "never", "obs")} if pay else None,
                     "ret": {k: (r.get(k) or {}).get("v") for k in ("d1", "d7", "d30")}, "sure": bool(r.get("sure")),
                     "few": bool(r.get("few"))})
    cut = [x for x in rows if x["dec"] == "Cut" and x["spend"]]
    win = c.get("win")
    return {"rows": rows, "win": win, "geo_why": c.get("geo_why"), "H": H,
            "cut": {"n": len(cut), "spend": _r(sum(x["spend"] for x in cut)),
                    "spend_src": _r(sum(x.get("spend_src") or 0 for x in cut), 2),
                    "rev90": _r(sum((x["rpi"].get("90") or 0) * (x["n"] or 0) for x in cut)),
                    "spend_all": _r(sum(x["spend"] or 0 for x in rows)),
                    "weeks": (win or {}).get("weeks") or (win or {}).get("size")}}


def _cty_months(P, ida, pre, sids, fxf):
    """Every named country by install month: [month, installs (GA4), Google Ads cost, Google Ads downloads, ROAS at
    7 / 30 / 90 days, weeks, weeks complete at 7 / 30 / 90] — a ROAS is (AdMob-matched revenue ÷ cost) over the weeks
    of the month COMPLETE at that age only (null when none is); the cost of a week counts there only."""
    pr, kf = P["pre"], P["sc"]["kf"]
    cset = ida.get("cset") or []
    ages = ((7, 3), (30, 5), (90, 7))               # (days, the last CBANDS band of it)
    geo = (pre or {}).get("geo") or {}
    gw = (geo.get("weeks") or {})
    cost = {}                                       # (Monday, cc) → [USD, downloads, as billed]
    for sid in sids or ():
        for W, cs in (gw.get(sid) or {}).items():
            try:
                rate = fxf(_d(W) + timedelta(days=3)) or 0
            except ValueError:
                continue
            for cc, v in (cs or {}).items():
                if isinstance(v, list) and v:
                    e = cost.setdefault((W, cc), [0.0, 0.0, 0.0])
                    e[0] += (v[0] or 0) / 1e6 * rate
                    e[1] += float(v[1] or 0) if len(v) > 1 and v[1] is not None else 0.0
                    e[2] += (v[0] or 0) / 1e6
    out = {}
    for W, slots in (ida.get("c") or {}).items():
        try:
            w0 = _d(W)
        except ValueError:
            continue
        done = [pr.all(pr.g, w0, w0 + timedelta(days=6 + a)) and pr.all(pr.c, w0, w0 + timedelta(days=6 + a))
                for a, _ in ages]
        for sk, cell in (slots or {}).items():
            if sk == "gap" or not isinstance(cell, dict):
                continue
            try:
                cc = cset[int(sk)]
            except (ValueError, IndexError, TypeError):
                continue
            if cc in ("--", "ZZ"):
                continue
            sp, dl, spi = cost.get((W, cc), [0.0, 0.0, 0.0])
            e = out.setdefault(cc, {}).setdefault(W[:7], {"n": 0, "sp": 0.0, "spi": 0.0, "dl": 0.0, "w": 0,
                                                          "r": [0.0] * 3, "s": [0.0] * 3, "k": [0] * 3})
            e["n"] += int(cell.get("n") or 0)
            e["sp"] += sp
            e["spi"] += spi
            e["dl"] += dl
            e["w"] += 1
            r = cell.get("r") or []
            for i, (a, last) in enumerate(ages):
                if not done[i]:
                    continue
                e["k"][i] += 1
                e["s"][i] += sp
                for b in range(last + 1):
                    lo, hi = val.CBANDS[b]
                    e["r"][i] += (r[b] if b < len(r) else 0) / 1e6 * kf(w0 + timedelta(days=3 + (lo + hi) // 2))[0]
    res = {}
    for cc, ms in out.items():
        res[cc] = [[m, e["n"], _r(e["sp"]), _r(e["dl"], 1)]
                   + [(_r(e["r"][i] / e["s"][i]) if e["k"][i] and e["s"][i] > 0 else None) for i in range(3)]
                   + [e["w"]] + list(e["k"]) + [_r(e["spi"], 2)] for m, e in sorted(ms.items())]
    return res


def app_step(acc, store, a, key, rev, pre, cfg, out_dir, data_dir, now=None):
    """One app → roi_<key>.json.gz (+ its summary into acc). Never raises."""
    try:
        from . import value_build as vb
        aid = a["app_id"]
        ida = vb.load_iday(data_dir, aid)
        if ida is None:
            acc.skipped += 1
            return
        hs = val._d(store["history_start"])
        S0 = val.settled_day(ida, hs)
        if S0 is None:
            acc.skipped += 1
            return
        ded = (pre.get("ded") or {}).get(aid) or (pre.get("ded") or {}).get(a["app_name"])
        ded_rate = (ded or {}).get("rate") if cfg.get("deduct", True) else None
        P = val._prep(store, ida, rev, ded_rate, S0)
        spend = vb.app_spend(pre, a, store)
        fxf = val._fx_fn(pre.get("fx"), spend["ccy"])[0] if spend else (lambda d: 1.0)
        co = gco.load_store(data_dir, aid)
        if co is not None and str(co.get("stream_id") or "") != str(store.get("stream_id") or ""):
            co = None
        now = now or datetime.now(timezone.utc)
        today = _d(co["read_today"]) if co and co.get("read_today") else P["S"]
        rows = _cohorts(P, spend, fxf, co, today)
        off, checked = _tie_off(ida, (co or {}).get("x") or {}, ida.get("days"))
        for r in rows:
            if r["d"]:
                r["q"] = any(_iso(r["X"] + timedelta(days=L)) in off for L in range(len(r["d"])))
        _statuses(rows)
        summ = _summary(rows, P, off, checked, today)
        life = _life(rev, spend, fxf, ded_rate)
        try:
            with gzip.open(os.path.join(out_dir, vb.PREFIX + key + ".json.gz"), "rt", encoding="utf-8") as f:
                detail = json.load(f)
        except (OSError, ValueError):
            detail = None
        H = cfg.get("payback_days") or val.H_DEFAULT
        if acc.beta is None:
            acc.beta = _betas(data_dir)
        try:                                            # ⚖️ GA4's measured paid / organic split (a bad paid
            gp = _ga4p(ida, sorted(set(F4_AGES) | {H}))   # cell costs only it: the ranges then)
        except Exception:
            gp = None
        f4 = _forms(rows, H, acc.beta.get(aid), gp)
        if any(e.get("src") == "ga4" for e in f4["by"].values()):
            acc.f4m += 1
        cty = _countries(detail, H)
        try:
            sids = vb.app_sids(pre, a, store, (pre.get("spend") or {}).get("daily") or {}) if pre.get("spend") else ()
            cty["months"] = _cty_months(P, ida, pre, sids, fxf)
        except Exception:
            cty["months"] = {}
        body = {"v": V, "app_id": aid, "app": a["app_name"], "key": key, "tz": P["tz"], "cur": "USD",
                "ccy": spend["ccy"] if spend else None, "S": _iso(P["S"]), "hs": _iso(P["hs"]),
                "newest": co.get("read_today") if co else None, "spend_till": spend.get("till") if spend else None,
                "rev_till": (rev or {}).get("till"), "T": list(T), "lags": gco.LAGS,
                "rows": [_row_out(r) for r in rows], "months": _months(rows), "sum": summ, "life": life,
                "life_till": _life_till(rev, spend), "cty": cty, "f4": f4,
                "consts": {"n_recent": N_RECENT, "n_usual": N_USUAL, "min_spend": MIN_SPEND, "min_n": MIN_N,
                           "worse": WORSE, "watch": WATCH, "better": BETTER, "final_lag": gco.FINAL_LAG,
                           "f4": f4_consts()}}
        fcs = None
        try:                                            # 🔮 the forecast (its own budget and daily cadence; a failure
            from . import forecast_build as fob         # costs only it)
            if acc.fc is None:
                acc.fc = fob.start(data_dir, now)
            decs = {x["cc"]: x["dec"] for x in cty["rows"]}
            eng = [dict(x, dec=decs.get(x.get("cc"))) for x in (((detail or {}).get("countries") or {}).get("rows") or [])]
            body["fc"] = fob.app_step(acc.fc, aid, key, rows, P, ida, life, body["life_till"], eng,
                                      rev_cty=(rev or {}).get("cty"), unst=store)
            fcs = fc_summary(body["fc"])
        except Exception:
            body["fc"] = None
        name = PREFIX + key + ".json.gz"
        write_json_gz_stable(os.path.join(out_dir, name), body)
        if body["life_till"] and spend and spend.get("sids"):
            acc.till.append(body["life_till"])
        if spend and spend.get("ccy"):
            acc.ccy.add(spend["ccy"])
        lt_till = body["life_till"]                    # lifetime totals to the last day both sides are in (as the page)
        done = [x for x in life if not lt_till or x[0] <= lt_till]
        lt = [sum(x[1] or 0 for x in done), sum(x[2] or 0 for x in done), sum(x[3] or 0 for x in done)]
        acc.apps.append({"app_id": aid, "app": a["app_name"], "key": key, "file": name, "st": summ["st"],
                         "r7": summ["r7"], "u7": summ["u7"], "pb": summ["pb"], "pbm": summ["pbm"], "best": summ["best"],
                         "cpi": summ["cpi"],
                         "r30": (summ["pools"]["30"]["r"] or {}).get("roas"),
                         "u30": (summ["pools"]["30"]["u"] or {}).get("roas"),
                         "life": [_r(lt[0], 2), _r(lt[1], 2), _r(lt[2], 2)], "cut": cty["cut"]["n"],
                         "cut_save": cty["cut"], "cpi_src": summ["cpi_src"], "nb": summ["nb"], "fc": fcs,
                         "first": life[0][0] if life else None, "ads": bool(spend and spend.get("sids")), "f4": f4})
        for d, rv, sp, spi in life:
            p = acc.life.setdefault(d, [0.0, 0.0, 0.0])
            p[0] += rv or 0
            p[1] += sp or 0
            p[2] += spi or 0
        for r in rows:
            if not (r["sp"] and r["sp"] > 0):
                continue
            p = acc.rows.setdefault(_iso(r["X"]), {"n": 0, "sp": 0.0, "spi": 0.0, "s": 0.0, "t": [0.0] * len(T),
                                                    "ok": [True] * len(T), "apps": 0})
            p["n"] += r["n"]
            p["sp"] += r["sp"]
            p["spi"] += r.get("spi") or 0
            p["s"] += r["s"] or 0                       # each app's install day: its revenue so far
            p["apps"] += 1
            for j in range(len(T)):
                if r["t"][j] is None:
                    p["ok"][j] = False
                else:
                    p["t"][j] += r["t"][j]
    except Exception as e:
        acc.fails += 1
        print("roi skipped for an app: %s" % type(e).__name__, file=sys.stderr)


# ── the end ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def fc_summary(fc):
    """The pointer's forecast line: next 30 / 90 / 180 days revenue (corrected), the accuracy, what is ready."""
    if not fc or not fc.get("f"):
        return None
    f = fc["f"]
    tot = [a + b + c for a, b, c in zip(f["old"], f["org"], f["paid"])]
    out = {"ready": fc.get("ready"), "made": fc.get("made"), "sp": (f.get("sp") or [None])[0], "spi": f.get("spi"),
           "a30": _r(sum(v or 0 for v in ((fc.get("hist") or {}).get("rev") or [])[-30:]), 2)}
    for h in (30, 90, 180):
        out["r%d" % h] = _r(sum(tot[:h]), 2) if len(tot) >= h else None
        c = (fc.get("cal") or {}).get(str(h)) or {}
        out["e%d" % h] = c.get("mape_normal") if c.get("mape_normal") is not None else c.get("mape")
    return out


def _clean(out_dir, keep):
    try:
        names = os.listdir(out_dir)
    except OSError:
        return
    for f in names:
        if (FILE_RE.match(f) and f not in keep) or (f == ALL_FILE and ALL_FILE not in keep):
            try:
                os.remove(os.path.join(out_dir, f))
            except OSError:
                pass


def finish(acc, dashboard, out_dir):
    """roi.json.gz + dashboard["roi"] → HEADER_PATHS, or [] (no app: every roi file removed, no pointer)."""
    global LINE
    dashboard.pop("roi", None)
    try:
        if not acc.apps:
            _clean(out_dir, set())
            LINE = "roi: apps 0, skipped %d, failed %d" % (acc.skipped, acc.fails)
            return []
        rows = [[d, p["n"], _r(p["sp"]), [(_r(p["t"][j]) if p["ok"][j] else None) for j in range(len(T))], p["apps"],
                 _r(p["spi"], 2), _r(p.get("s", 0.0))] for d, p in sorted(acc.rows.items())]
        months = {}
        for d, n, sp, t, k, spi, _so in rows:
            e = months.setdefault(d[:7], {"n": 0, "sp": 0.0, "spi": 0.0, "t": [0.0] * len(T), "ok": [True] * len(T),
                                          "days": 0})
            e["n"] += n
            e["sp"] += sp or 0
            e["spi"] += spi or 0
            e["days"] += 1
            for j in range(len(T)):
                if t[j] is None:
                    e["ok"][j] = False
                else:
                    e["t"][j] += t[j]
        body = {"v": V, "T": list(T), "apps": sorted(acc.apps, key=lambda x: x["app"].casefold()),
                "life": [[d, _r(v[0]), _r(v[1]), _r(v[2], 2)] for d, v in sorted(acc.life.items())], "rows": rows,
                "months": [[m, e["n"], _r(e["sp"]), [(_r(e["t"][j]) if e["ok"][j] else None) for j in range(len(T))],
                            e["days"], e["days"], _r(e["spi"], 2)] for m, e in sorted(months.items())],
                "ccy": next(iter(acc.ccy)) if len(acc.ccy) == 1 else None, "f4c": f4_consts(),
                "life_till": max(set(acc.till), key=lambda d: (acc.till.count(d), d)) if acc.till else None}
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        write_json_gz_stable(os.path.join(out_dir, ALL_FILE), body)
        dashboard["roi"] = {"file": ALL_FILE, "v": hashlib.sha1(raw).hexdigest()[:12], "ccy": body["ccy"],
                            "starts": {k: v.isoformat() for k, v in (acc.fc.starts if acc.fc is not None else {}).items()},
                            "apps": {x["app_id"]: {k: x.get(k) for k in ("file", "st", "r7", "u7", "pb", "nb", "life", "cut", "fc")}
                                     for x in acc.apps}}
        _clean(out_dir, {x["file"] for x in acc.apps} | {ALL_FILE})
        sts = {}
        for x in acc.apps:
            sts[x["st"]] = sts.get(x["st"], 0) + 1
        LINE = ("roi: apps %d, worse %d, watch %d, better %d, normal %d, too early %d, n/a %d, skipped %d, failed %d, "
                "forms ga4 %d"
                % tuple([len(acc.apps)] + [sts.get(k, 0) for k in ("Worse", "Watch", "Better", "Normal", "Too early",
                                                                     "N/A")] + [acc.skipped, acc.fails, acc.f4m]))
        if acc.fc is not None:
            from . import forecast_build as fob
            fob.finish(acc.fc)
            LINE += "; " + fob.line(acc.fc)
        return list(HEADER_PATHS)
    except Exception as e:
        dashboard.pop("roi", None)
        LINE = None
        print("roi skipped: %s" % type(e).__name__, file=sys.stderr)
        return []


def off(out_dir):
    global LINE
    LINE = None
    _clean(out_dir, set())


def pop_line():
    global LINE
    line, LINE = LINE, None
    return line
