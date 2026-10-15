"""🔮 Revenue forecast — engine "vd" (pure: no I/O, no clock, no prints). The forecast tournament's winner (lab, 15 Oct
2026): two measured views of the same revenue, each from data dated ≤ T only, mixed with weights the back-tests choose.
The older engine (forecast.py, "v0") stays importable: forecast_build switches with FORECAST_ENGINE=v0|vd (default vd).

Notation: X an install day (n_X GA4 installs), L = D − X its age on day D, T the origin (the newest AdMob day), TG the
newest GA4 day ≤ T − lag (GA4 lands `glag` days after AdMob, measured per app), j a GA4 install-age band (0 | 1–6 | 7–29 |
30–89 | 90–364 | 365–427 | > 427), k_D = AdMob ÷ GA4 revenue on day D.

  view A ("anchored"):   rev_A(X, D) = n_X · S_X · a(L) · fr_X(L) · lev_j(L) · g(D)
      a(L), u(L)  the engine's triangle curves (forecast.curve: daily to 30, then 31–60 | 61–90 | 91–180 | 181–365, tail);
      fr_X, fu_X  the install week's country mix (only weeks whose days were read into the cells; future installs: the
                  newest two complete read weeks; a country added late is put back into ZZ while it was partial);
      S_X         X's standing on its newest measured window (181–365 | 91–180 | 61–90 | 31–60 | its last ≤ 7 exact days)
                  ÷ the curve's, trusted UD/(UD + Kc), shrunk toward its ±7-day batch (clip 0.2–5); U_X the same on users;
      lev_j       Σ k·GA4rev_j ÷ Σ model_j over the newest w GA4 days (> 427 = AdMob − k·Σ bands); a thin band leans on
                  the band before; new installs take Λ_j = GA4 ÷ the model without anchors (newest wn GA4 days).
  view B ("users × ARPDAU"):  rev_B(X, D) = n_X · R(L) · fu_X(L) · su_X · zu_j · arp_j · S(L) · fa_X(L) ÷ m̄_j · g(D)
      R(L)        retention: daily to 30, then the chain ladder 30→45→…→365 (install days that reached both lags);
      su_X        X's own users anchor (last 3 known lags, E/(E + Ku)); zu_j GA4's users ÷ the model's for bands ≥ 30;
      arp_j       AdMob-matched revenue per GA4 active user per band over the newest wa GA4 days (× the calendar index
                  of the newest bw days); a thin band shrunk to its 112-day value, then to the band before × the
                  portfolio's band ratio (state.json "bandr" at the Monday on or before the newest GA4 day: other
                  apps' data only as the live build had it then); S the portfolio's age shape;
      + users older than 427 days no tracked install day explains, decaying at their own 90-day pace;
      new installs: organic and paid apart (regression on the paid share of the newest 56 install days).
  revenue(T+i) = q^cq · [(1 − bo)·old_A + bo·old_B + (1 − bn)·new_A + bn·new_B]
      q = Σ AdMob ÷ Σ the mixed old model over the days AdMob has but GA4 not yet (clip 1/3–3): the eCPM / fill move
      since the levels' window, every age at once.  Installs = organic + spend × installs per $ (forecast.installs_model)
      for the revenue; the installs, users and uninstalls of the paid ones follow each country's own installs per $ and
      the CPI's rise with a country's spend (cs 1: the Google Ads country weeks, below — the revenue is not moved by it).
  DAU the same mix of users; uninstalls from forecast.uninstall_curve (unchanged).
  The "Budget by country" planner (cs_plan): today's spend per country, its installs per $, its measured weekly spend
  range and its share of the paid installs' revenue — each country on its own curves.

GA4's install-day extension (IDAY_EXT: c2 / cp cells, the d2 ledger; still back-filling, so its coverage grows daily) —
two switches (a cell is used only when every activity day of it was read, so an origin without one is exactly the model
without them). Both are HELD OFF for every app (GRID): tuned per app they were chosen in-sample from a handful of
back-test origins and did not win out of sample (lab, 15 Oct: no better than a tie across apps, and a per-app on / off
decided on older origins did not hold on the newest). The code, the "why" and _moves stay: they go back into GRID only
after the post-backfill out-of-sample re-run shows a win.
  gc 2  every country's own users past day 90 (at 120 / 180 / 270 / 365) from the late cells, each shrunk toward the
        country's own standing at the lag before (its installs n ÷ (n + CKC)) — 0: the lag-90 standing carried.
        (Lab: on the cells themselves a newer week's country shares of users past day 90 mostly came closer.)
  gc 3  gc 2 + each country's own revenue 91–180 / 181–365 / 366–427 the same way — 0 / 2: the 61–90 standing
        carried. (Lab: the revenue cells are still few and mixed — not shown to win on their own yet.)
  pc 1  new installs' paid vs organic split from GA4's paid users (cp: every country's own paid / organic revenue and
        users per install, at the newest paid / organic country mix) instead of the regression on the Google Ads
        install share (an upper bound) — the installs still come from spend (paid) and the organic rate, unchanged.
        (Lab: a newer week's paid ÷ organic revenue per install came closer than with the regression.)

Structure (STRUCT, 13 knobs) is fixed portfolio-wide (version STRUCT_VERSION; re-checked offline, never per app: tuned
per app it measured worse on unseen origins); only the mix weights bo, bn, cq are tuned per app (GRID; the switches
gc, pc held at 0), on the same back-tests as before plus each past install day's future revenue and each new install's
value (objective()).
Every back-test origin sees GA4 only to T − glag, each install day's final daily data only to T − clag and its
checkpoints after day 30 only to T − tlag, as the live build does (lag_view; the three lags measured per app)."""
import bisect
import math
import operator
from datetime import date, timedelta

from . import forecast as F

ONE = timedelta(days=1)
H = F.H
HORIZONS = F.HORIZONS
STRUCT_VERSION = "2026-10-15b"
STRUCT = {"m": "ratio", "hl": 45, "Kc": 30, "w": 28, "wn": 7, "g": 0.0, "W": 14,          # view A (+ g, W shared)
          "bhl": 100000, "Ku": 3, "bw": 0, "wa": 56, "nv": 1,                             # view B
          "cs": 1}                                                                        # installs by country
GRID = {"bo": (0.0, 0.5, 1.0), "bn": (0.0, 0.5, 1.0), "cq": (0.0, 0.5, 1.0), "gc": (0,), "pc": (0,)}
DEFAULT = {"bo": 0.5, "bn": 0.5, "cq": 0.0, "gc": 0, "pc": 0}
# m  "ratio": what no install day covers (> 427 days) = AdMob − k·Σ GA4 bands; "split": a decaying rest
# hl / bhl  the curves' half-life (100000 = every install day alike); Kc / Ku  credibility of an install day's own anchor
# w / wn  GA4 days of the levels (past install days / new installs); bw / wa  B's calendar index / ARPDAU window
# g  month-of-year season strength (0 off); W  installs-model window; nv 1 organic and paid new installs apart
# bo / bn  B's weight on past install days / new installs; cq  how much of the AdMob-only move q is carried
# cs 1  the paid installs (users, uninstalls) by country: each country's own installs per $ and its CPI's rise with
#       its spend (no country weeks: per_usd × spend); the revenue stays on per_usd × spend either way
# gc 2  each country's own users past day 90 from GA4's late cells (c2); 3: + its revenue 91–427 — 0: lag 90 / 61–90
#       carried
# pc 1  new installs' paid vs organic value from GA4's paid cells (cp) — 0: regressed on the Google Ads install share
#       (gc / pc: held at 0 for every app — GRID (0,) — until an out-of-sample back-test shows a win; no complete cell
#       = identical)


def params(p=None):
    """A stored setting ({bo, bn, cq}) → the full one (STRUCT + the mix weights)."""
    out = dict(STRUCT, **DEFAULT)
    out.update({k: v for k, v in (p or {}).items() if k in out})
    return out


# ── the app as it stood at T: GA4 only to T − lag (it lands later than AdMob) ─────────────────────────────────────────
def lag_view(app, T, lag, clag=0, tlag=0):
    """g4, DAU and the GA4 day ledgers (days, IDAY_EXT's d2) cut at T − lag; with clag, also each install day's final
    daily data (and its checkpoints to day 30) cut at T − clag; with tlag, its checkpoints after day 30 (60 / 90 / 180 /
    365) cut at T − tlag — the app as the live build has it at T. Kept per (T, lag, clag, tlag) inside the app."""
    if not lag and not clag and not tlag:
        return app
    vs = app.setdefault("_fv_views", {})
    k = (T, lag, clag, tlag)
    if k not in vs:
        cut = T - timedelta(days=lag)
        v = {kk: vv for kk, vv in app.items() if not kk.startswith("_")}
        v["g4"] = {D: e for D, e in (app.get("g4") or {}).items() if D <= cut}
        days = dict(app["days"])
        D = cut + ONE
        while D <= T:
            e = days.get(D)
            if e and "dau" in e:
                days[D] = {a: b for a, b in e.items() if a != "dau"}
            D += ONE
        v["days"] = days
        ida = dict(app.get("ida") or {})
        cs = cut.isoformat()
        if ida.get("days"):
            ida["days"] = {a: b for a, b in ida["days"].items() if a <= cs}
        if ida.get("d2"):                                 # the extension's day ledger lands with GA4 too
            ida["d2"] = {a: b for a, b in ida["d2"].items() if a <= cs}
        v["ida"] = ida
        if clag or tlag:
            coh = {}
            for X, c in app["coh"].items():
                if X > T:
                    coh[X] = c
                    continue
                lim = (T - X).days - clag                     # the newest age with final data at T
                if clag and ((c.get("df") or 0) > lim + 1 or (c.get("uf") or 0) > lim + 1):
                    t = c.get("t") or []
                    c = dict(c, df=max(0, min(c.get("df") or 0, lim + 1)), uf=max(0, min(c.get("uf") or 0, lim + 1)),
                             t=[x if j >= len(F.T_AGES) or F.T_AGES[j] > 30 or F.T_AGES[j] <= lim else None
                                for j, x in enumerate(t)])
                tl = (T - X).days - tlag                      # the newest age with a checkpoint > 30 at T
                t = c.get("t") or []
                if tlag and any(x is not None and j < len(F.T_AGES) and 30 < F.T_AGES[j] and F.T_AGES[j] > tl
                                for j, x in enumerate(t)):
                    c = dict(c, t=[None if j < len(F.T_AGES) and 30 < F.T_AGES[j] and F.T_AGES[j] > tl else x
                                   for j, x in enumerate(t)])
                coh[X] = c
            v["coh"] = coh
        v["_jumps"] = app.get("_jumps")
        vs[k] = v
    return vs[k]


# ══ view A — anchored install days, a level per GA4 install-age band ══════════════════════════════════════════════
MAXA = F.MAX_AGE
AB7 = ((0, 0), (1, 6), (7, 29), (30, 89), (90, 364), (365, 427), (428, MAXA))   # GA4's install-age bands + older
NLB = len(AB7)
LBIX = [next(j for j, (lo, hi) in enumerate(AB7) if lo <= L <= hi) for L in range(MAXA + 1)]
CUTS = sorted({0, 1, 2, 4, 7, 8, 15, 30, 31, 61, 90, 91, 181, 365, 366, 428, MAXA + 1})   # every age a factor changes
UCUTS = sorted({0, 1, 3, 7, 14, 30, 60, 90, 365, 428, MAXA + 1, 4, 8, 15, 31, 61, 91, 181, 366})
PAST = 90                      # days before T kept for the levels / the rest fit
KU = 10.0                      # users' credibility: expected users in the anchor window for half trust
LEV_SUP = 0.1                  # a band filled to share s of its ages is trusted s ÷ (s + LEV_SUP) (from 30–89 on)
GA4_LAG = 14                   # the levels' window: the newest w days with a GA4 read, searched back this far
LOC = 7                        # the install days within ±LOC days pool a cohort's shrink target
QC_FOLDED = ("ok", "smp", "gap")

# ── GA4's install-day extension (IDAY_EXT: c2 / cp cells, d2 ledger) — switches gc / pc (GRID: held at 0 until an
#    out-of-sample win); with a switch off, or nothing complete yet, every number is exactly the one without them ────
C2B = ((91, 180), (181, 365), (366, 427))      # c2 r2: ad revenue at these install ages (per install week × slot)
C2L = (120, 180, 270, 365)                     # c2 u2: active users at these ages
NCB, NCL = len(F.CB), len(F.CL)
CBX = tuple(F.CB) + C2B                        # gc: the factor vectors' revenue bands …
CLX = tuple(F.CL) + C2L                        # … and users' lags (a late one nobody measured carries the one before)
BIXX = [next((i for i, (lo, hi) in enumerate(CBX) if lo <= L <= hi), len(CBX) - 1) for L in range(MAXA + 1)]
UIXX = [-1 if L == 0 else max(i for i, g in enumerate(CLX) if g <= L) for L in range(MAXA + 1)]
UCUTSX = sorted(set(UCUTS) | {120, 180, 270})
LB = ((0, 0), (1, 1), (2, 3), (4, 7), (8, 14), (15, 30), (31, 60), (61, 90), (91, 180), (181, 365), (366, 427))  # cp r
LL = (1, 3, 7, 14, 30, 60, 90, 120, 180, 270, 365)                                                      # cp u
LBX = [next((i for i, (lo, hi) in enumerate(LB) if lo <= L <= hi), len(LB) - 1) for L in range(MAXA + 1)]
NWK = 8                        # pc: the newest complete install weeks a band's paid / organic values come from (≈ NW)
PMIN = 100                     # … a band needs ≥ this many paid AND organic installs (roi_build.F4_PMIN)
NMIX = 2                       # … the newest complete weeks with paid (organic) installs give their country mix
PIG_COV = 0.25                 # … GA4's paid share of new users must cover ≥ this share of a window's install days


def _bix_of(f):
    return BIXX if (f and len(f[0]) > NCB) else F.BIX


def _uix_of(f):
    return UIXX if (f and len(f[1]) > NCL) else F.UIX


def _xfr(f, L):
    """forecast._fr for a legacy (8 bands) or an extended (gc: 11) factor vector."""
    if not f:
        return 1.0
    return f[0][(BIXX if len(f[0]) > NCB else F.BIX)[L]]


def _xfu(f, L):
    if not f:
        return 1.0
    ix = (UIXX if len(f[1]) > NCL else F.UIX)[L]
    return f[1][ix] if ix >= 0 else 1.0


def _xfold(app, key):
    """(first day, prefix counts) of the activity days whose IDAY_EXT ledger d2 has `key` (c2st / cpst) folded — kept
    in the app (the lag view: its d2 is cut at T − lag)."""
    mk = "_fvx_fold_" + key
    if mk not in app:
        d2 = (app.get("ida") or {}).get("d2") or {}
        ds = sorted(date.fromisoformat(k) for k, v in d2.items() if isinstance(v, dict) and v.get(key) in QC_FOLDED)
        if not ds:
            app[mk] = None
        else:
            d0 = ds[0]
            cnt = [0] * ((ds[-1] - d0).days + 2)
            st = set(ds)
            for i in range(len(cnt) - 1):
                cnt[i + 1] = cnt[i] + (1 if d0 + timedelta(days=i) in st else 0)
            app[mk] = (d0, cnt)
    return app[mk]


def _xsince(app, key):
    """{slot: [(first, last)]}: a country slot the fetch added later — the days of `key` (c2 / cp) that went into ZZ
    before it existed (IDAY_EXT xs.since)."""
    mk = "_fvx_since_" + key
    if mk not in app:
        ida = app.get("ida") or {}
        cset = ida.get("cset") or []
        out = {}
        for cc, e in (((ida.get("xs") or {}).get("since")) or {}).items():
            rr = e.get(key) if isinstance(e, dict) else None
            if cc in cset and rr:
                out[str(cset.index(cc))] = [(date.fromisoformat(a), date.fromisoformat(b)) for a, b in rr]
        app[mk] = out
    return app[mk]


def _late_cells(app, W, cells, bad_legacy, zz):
    """Install week W's late cells {slot: {n, r2[3], u2[4]}} (+ "gap": {r2}: Q-B − Σ named) — n from the week's legacy
    cells; a slot the legacy rule put into ZZ, or whose c2 days of the late windows (W+91 … W+433) went into ZZ before
    it existed (xs.since), is folded into ZZ, n with it (dropped when there is no ZZ)."""
    c2w = ((app.get("ida") or {}).get("c2") or {}).get(W.isoformat()) or {}
    since = _xsince(app, "c2")
    lo, hi = W + timedelta(days=C2B[0][0]), W + timedelta(days=6 + C2B[-1][1])
    bad = set(bad_legacy) | {k for k, rr in since.items() if any(a <= hi and b >= lo for a, b in rr)}
    out = {}
    for k, e in cells.items():
        if k == "gap":
            continue
        kk = zz if k in bad else k
        if kk is None:
            continue
        x = out.setdefault(kk, {"n": 0.0, "r2": [0.0] * 3, "u2": [0.0] * 4})
        x["n"] += e.get("n") or 0
    for k, e in c2w.items():
        if not isinstance(e, dict):
            continue
        if k == "gap":
            out["gap"] = {"n": 0.0, "r2": [float(v or 0) for v in (e.get("r2") or [0] * 3)[:3]], "u2": [0.0] * 4}
            continue
        kk = zz if k in bad else k
        if kk is None:
            continue
        x = out.setdefault(kk, {"n": 0.0, "r2": [0.0] * 3, "u2": [0.0] * 4})
        for b, v in enumerate((e.get("r2") or [0] * 3)[:3]):
            x["r2"][b] += v or 0
        for j, v in enumerate((e.get("u2") or [0] * 4)[:4]):
            x["u2"][j] += v or 0
    return out


def _curve_x(coh, T, start, hl, fx=None):
    """forecast.curve with each factor vector's own age → index map (gc: the late bands / lags measured)."""
    num, den = {}, {}
    bnum, bden = {}, {}
    unum, uden = {}, {}
    maxage = 0
    for X, c in coh.items():
        if X < start or X > T or not c.get("n"):
            continue
        n = c["n"]
        w = 0.5 ** ((T - X).days / hl) if hl < 99999 else 1.0
        f = F._wk(fx, X)
        k = F._known(c, X, T)
        if not k:
            continue
        kd = dict(k)
        maxage = max(maxage, k[-1][0])
        for L in range(0, 31):
            if L in kd and (L == 0 or L - 1 in kd):
                inc = kd[L] - (kd[L - 1] if L else 0.0)
                num[L] = num.get(L, 0.0) + w * max(0.0, inc)
                den[L] = den.get(L, 0.0) + w * n * _xfr(f, L)
        exact = any(L in kd for L in (2, 4, 5))
        if not exact:
            prev = None
            for a in (0, 1, 3, 7, 14, 30):
                if a in kd:
                    lo = 0 if prev is None else prev + 1
                    inc = kd[a] - (kd[prev] if prev is not None else 0.0)
                    for L in range(lo, a + 1):
                        num[L] = num.get(L, 0.0) + w * max(0.0, inc) / (a - lo + 1)
                        den[L] = den.get(L, 0.0) + w * n * _xfr(f, L)
                    prev = a
                else:
                    break
        for lo, hi, j in F.BANDS:
            a0 = F.T_AGES[j - 1]
            if hi in kd and a0 in kd:
                inc = max(0.0, kd[hi] - kd[a0])
                bnum[(lo, hi)] = bnum.get((lo, hi), 0.0) + w * inc
                bden[(lo, hi)] = bden.get((lo, hi), 0.0) + w * n * (hi - lo + 1) * _xfr(f, lo)
        uk = F._uknown(c, X, T)
        for L, v in uk.items():
            unum[L] = unum.get(L, 0.0) + w * v
            uden[L] = uden.get(L, 0.0) + w * n * _xfu(f, L)
    pts = {L: num[L] / den[L] for L in num if den.get(L)}
    for (lo, hi), v in bnum.items():
        if bden.get((lo, hi)):
            pts[(lo + hi) // 2] = v / bden[(lo, hi)]
    a = F._fill(pts, F.MAX_AGE)
    for (lo, hi), v in bnum.items():
        if not bden.get((lo, hi)):
            continue
        want = v / bden[(lo, hi)] * (hi - lo + 1)
        have = sum(a[lo:hi + 1])
        if have > 0:
            fq = want / have
            for L in range(lo, hi + 1):
                a[L] *= fq
    upts = {L: unum[L] / uden[L] for L in unum if uden.get(L)}
    u = F._fill(upts, F.MAX_AGE)
    return a, u, maxage


def _folded(app):
    if "_fva_fold" not in app:
        led = (app.get("ida") or {}).get("days") or {}
        ds = sorted(date.fromisoformat(k) for k, v in led.items() if isinstance(v, dict) and v.get("cst") in QC_FOLDED)
        if not ds:
            app["_fva_fold"] = None
        else:
            d0 = ds[0]
            cnt = [0] * ((ds[-1] - d0).days + 2)
            s = set(ds)
            for i in range(len(cnt) - 1):
                cnt[i + 1] = cnt[i] + (1 if d0 + timedelta(days=i) in s else 0)
            app["_fva_fold"] = (d0, cnt)
    return app["_fva_fold"]


def _cov(fo, a, b):
    """Every activity day a..b folded into the country cells."""
    if fo is None:
        return False
    d0, cnt = fo
    i, j = (a - d0).days, (b - d0).days
    if i < 0 or j + 1 >= len(cnt):
        return False
    return cnt[j + 1] - cnt[i] == j - i + 1


def _since(app):
    if "_fva_since" not in app:
        ida = app.get("ida") or {}
        cset = ida.get("cset") or []
        out = {}
        for cc, rr in (ida.get("cset_since") or {}).items():
            if cc in cset:
                out[str(cset.index(cc))] = [(date.fromisoformat(a), date.fromisoformat(b)) for a, b in rr]
        app["_fva_since"] = (out, str(cset.index("ZZ")) if "ZZ" in cset else None)
    return app["_fva_since"]


def _merge(cells, slots, zz):
    out = {k: e for k, e in cells.items() if k not in slots}
    if zz is None:
        return out
    for k in slots:
        e = cells.get(k)
        if not e:
            continue
        z = out.get(zz)
        z = dict(z) if z else {"n": 0, "u": [0] * len(F.CL), "r": [0] * len(F.CB)}
        z["n"] = (z.get("n") or 0) + (e.get("n") or 0)
        z["r"] = [p + q for p, q in zip(z.get("r") or [0] * len(F.CB), e.get("r") or [0] * len(F.CB))]
        if z.get("u") or e.get("u"):
            z["u"] = [p + q for p, q in zip(z.get("u") or [0] * len(F.CL), e.get("u") or [0] * len(F.CL))]
        out[zz] = z
    return out


def mix_fixed(app, T, hl, gc=0, info=None):
    """forecast.mix, fixed: per (week, band) / (week, lag) only the activity days folded into the cells count (the ledger's
    cst), a week whose install days (to T) are not all folded is left out, the installs to come take the newest two
    COMPLETE read weeks, and a country slot's cells in weeks it was only partly read (cset_since) are put back into ZZ.
    gc 2: + each country's own standing past day 90 (users at 120 / 180 / 270 / 365; gc 3: + revenue 91–180 / 181–365 /
    366–427) from the c2 cells of the weeks whose every activity day of that band was read (d2 c2st), each shrunk toward
    the country's standing in the band before (its installs n ÷ (n + CKC); a band's weeks weigh relative to its newest
    complete one) — nothing complete (or gc 2's revenue bands): the band before carried, as without gc. info (a dict):
    + "mf" {week: (revenue, users) share of the late factors resting on measured cells} and "n" (complete late weeks per
    band / lag)."""
    cty, start = app.get("cty") or {}, app["start"]
    fo = _folded(app)
    since, zz = _since(app)
    nb, nl = len(F.CB), len(F.CL)
    weeks = []
    for W in sorted(cty):
        if not (start - timedelta(days=6) <= W <= T):
            continue
        if not _cov(fo, W, min(W + timedelta(days=6), T)):
            continue
        weeks.append(W)
    if not weeks:
        return {}, None
    cells_of, bad_of = {}, {}
    for W in weeks:
        top = min(W + timedelta(days=96), T)
        bad = [s for s, rr in since.items() if any(a <= top and b >= W for a, b in rr)]
        cells_of[W] = _merge(cty[W], bad, zz) if bad else cty[W]
        bad_of[W] = bad
    rs, us = {}, {}
    ra = [[0.0, 0.0] for _ in range(nb)]
    ua = [[0.0, 0.0] for _ in range(nl)]
    for W in weeks:
        wt = 0.5 ** ((T - W).days / hl) if hl < 99999 else 1.0
        end = W + timedelta(days=6)
        cells = cells_of[W]
        for b, (lo, hi) in enumerate(F.CB):
            if end + timedelta(days=hi) > T:
                break
            if not _cov(fo, W + timedelta(days=lo), end + timedelta(days=hi)):
                continue
            for k, e in cells.items():
                n, r = e.get("n") or 0, (e.get("r") or [0] * nb)[b]
                ra[b][0] += wt * r
                ra[b][1] += wt * n
                if k != "gap":
                    x = rs.setdefault(k, [[0.0, 0.0] for _ in range(nb)])
                    x[b][0] += wt * r
                    x[b][1] += wt * n
        for j, g in enumerate(F.CL):
            if end + timedelta(days=g) > T:
                break
            if not _cov(fo, W + timedelta(days=g), end + timedelta(days=g)):
                continue
            for k, e in cells.items():
                if k == "gap" or not e.get("u"):
                    continue
                n, v = e.get("n") or 0, e["u"][j]
                ua[j][0] += wt * v
                ua[j][1] += wt * n
                x = us.setdefault(k, [[0.0, 0.0] for _ in range(nl)])
                x[j][0] += wt * v
                x[j][1] += wt * n

    lr = lu = 10 ** 9                             # gc: from these indexes on, shrunk toward the band before
    nmeas = None
    if gc:
        nmeas = _a_late(app, T, hl, weeks, cells_of, bad_of, zz, rs, us, ra, ua, gc >= 3)
        lr, lu, nb, nl = nb, nl, len(CBX), len(CLX)

    def rel(per, tot, nk, late, zs=None):
        out = {k: [1.0] * nk for k in per}
        for b in range(nk):
            R, N = tot[b]
            if N <= 0 or R <= 0:
                for k in per:
                    out[k][b] = out[k][b - 1] if b else 1.0
                continue
            ref = 0.0
            for k, x in per.items():
                r, n = x[b]
                m = (r / n) / (R / N) if n > 0 else (out[k][b - 1] if b else 1.0)
                if b >= late:
                    m = out[k][b - 1] + (m - out[k][b - 1]) * (n / (n + F.CKC)) if n > 0 else m
                    if zs is not None and n > 0:
                        zs.setdefault(k, {})[b] = n / (n + F.CKC)
                else:
                    m = 1.0 + (m - 1.0) * (n / (n + F.CKC)) if n > 0 else m
                out[k][b] = min(10.0, max(0.05, m))
                ref += max(0.0, n) / N * out[k][b]
            ref += max(0.0, 1.0 - sum(max(0.0, x[b][1]) for x in per.values()) / N)
            if ref > 0:
                for k in per:
                    out[k][b] /= ref
        return out
    zr, zu = {}, {}
    mr, mu = rel(rs, ra, nb, lr, zr), rel(us, ua, nl, lu, zu)

    def fac(cells_list):
        tot = sum(e.get("n") or 0 for cells in cells_list for e in cells.values())
        if tot <= 0:
            return None
        rf, uf = [0.0] * nb, [0.0] * nl
        for cells in cells_list:
            for k, e in cells.items():
                q = (e.get("n") or 0) / tot
                r, v = mr.get(k), mu.get(k)
                for b in range(nb):
                    rf[b] += q * (r[b] if r else 1.0)
                for j in range(nl):
                    uf[j] += q * (v[j] if v else 1.0)
        return [max(0.05, x) for x in rf], [max(0.05, x) for x in uf]
    fx = {}
    for W in weeks:
        f = fac([cells_of[W]])
        if f:
            fx[W] = f
    done = [W for W in weeks if W + timedelta(days=6) <= T][-2:]
    if info is not None and gc:                   # how much of each week's late factors rests on measured cells
        def mfs(zs, lo, hi):                      # mf(b) = z(b) + (1 − z(b)) · mf(b − 1), from the first late one
            out = {}
            for k in set(zs) | set(mr if lo == lr else mu):
                v, prev = [], 0.0
                for b in range(lo, hi):
                    z = zs.get(k, {}).get(b, 0.0)
                    prev = z + (1.0 - z) * prev
                    v.append(prev)
                out[k] = v
            return out
        kr, ku = mfs(zr, lr, nb), mfs(zu, lu, nl)
        mf = {}
        for W in weeks:
            cells = cells_of[W]
            tot = sum(e.get("n") or 0 for e in cells.values())
            if tot <= 0:
                continue
            rv, uv = [0.0] * (nb - lr), [0.0] * (nl - lu)
            for k, e in cells.items():
                q = (e.get("n") or 0) / tot
                for i, x in enumerate(kr.get(k) or []):
                    rv[i] += q * x
                for i, x in enumerate(ku.get(k) or []):
                    uv[i] += q * x
            mf[W] = (rv, uv)
        info.update(mf=mf, n=nmeas)
    app.setdefault("_fva_slot", {})[(T, hl, gc)] = (mr, mu, nb, nl)       # each country's own factors (the planner)
    return fx, (fac([cells_of[W] for W in done]) if done else None)


def _a_late(app, T, hl, weeks, cells_of, bad_of, zz, rs, us, ra, ua, rev=True):
    """gc: the late bands / lags (c2) into view A's accumulators, extended in place to len(CBX) / len(CLX); a (week,
    band) only when every activity day of it was read; weights relative to the band's newest complete week; rev False
    (gc 2): the late lags only — the late bands stay empty (the 61–90 standing carried). → the complete weeks per late
    band (0 without rev) and lag."""
    nb, nl, nbx, nlx = len(F.CB), len(F.CL), len(CBX), len(CLX)
    fo2 = _xfold(app, "c2st")
    for x in rs.values():
        x.extend([0.0, 0.0] for _ in range(nbx - nb))
    for x in us.values():
        x.extend([0.0, 0.0] for _ in range(nlx - nl))
    ra.extend([0.0, 0.0] for _ in range(nbx - nb))
    ua.extend([0.0, 0.0] for _ in range(nlx - nl))
    if fo2 is None:
        return [0] * (len(C2B) + len(C2L))
    lc = {W: _late_cells(app, W, cells_of[W], bad_of[W], zz) for W in weeks}
    okb = [[W for W in weeks if rev and W + timedelta(days=6 + hi) <= T
            and _cov(fo2, W + timedelta(days=lo), W + timedelta(days=6 + hi))] for lo, hi in C2B]
    okl = [[W for W in weeks if W + timedelta(days=6 + g) <= T
            and _cov(fo2, W + timedelta(days=g), W + timedelta(days=6 + g))] for g in C2L]

    def wt(W, ws):
        return 0.5 ** ((max(ws) - W).days / hl) if hl < 99999 else 1.0
    for i, ws in enumerate(okb):
        for W in ws:
            w = wt(W, ws)
            for k, e in lc[W].items():
                n, r = e["n"], e["r2"][i]
                ra[nb + i][0] += w * r
                ra[nb + i][1] += w * n
                if k != "gap":
                    x = rs.setdefault(k, [[0.0, 0.0] for _ in range(nbx)])
                    x[nb + i][0] += w * r
                    x[nb + i][1] += w * n
    for i, ws in enumerate(okl):
        for W in ws:
            w = wt(W, ws)
            for k, e in lc[W].items():
                if k == "gap":
                    continue
                n, v = e["n"], e["u2"][i]
                ua[nl + i][0] += w * v
                ua[nl + i][1] += w * n
                x = us.setdefault(k, [[0.0, 0.0] for _ in range(nlx)])
                x[nl + i][0] += w * v
                x[nl + i][1] += w * n
    return [len(ws) for ws in okb] + [len(ws) for ws in okl]


def _amix(app, T, hl, gc=0):
    if not app.get("cty"):
        return {}, None
    memo = app.setdefault("_fva_mix", {})
    k = (T, hl, gc)
    if k not in memo:
        memo[k] = mix_fixed(app, T, hl, gc)
    return memo[k]


def _window(kd, K, exact):
    """The most recent measured window (lo, hi) of an install day known to age K (None: nothing)."""
    for lo, hi, need in ((181, 365, 180), (91, 180, 90), (61, 90, 60), (31, 60, 30)):
        if K >= hi and hi in kd and need in kd:
            return lo, hi
    if K > 30:
        K = 30
    if exact:
        while K > 0 and K not in kd:
            K -= 1
        if K == 0:
            return (0, 0) if 0 in kd else None
        lo = max(1, K - 6)
        while lo <= K and (lo - 1) not in kd:
            lo += 1
        return (lo, K) if lo <= K else None
    prev = None
    for a in (0, 1, 3, 7, 14, 30):
        if a in kd and a <= K:
            prev = a
    if prev is None:
        return None
    pts = [a for a in (0, 1, 3, 7, 14, 30) if a in kd and a < prev]
    return (pts[-1] + 1 if pts else 0, prev)


def _obs(kd, lo, hi):
    if hi not in kd or (lo > 0 and (lo - 1) not in kd):
        return None
    return kd[hi] - (kd[lo - 1] if lo > 0 else 0.0)


def _cumfr(a, f):
    """cum[L+1] = Σ a(0..L) · fr(f, ·)"""
    out = [0.0] * (len(a) + 1)
    s = 0.0
    if f:
        r = f[0]
        bix = _bix_of(f)
        for i, v in enumerate(a):
            s += v * r[bix[i]]
            out[i + 1] = s
    else:
        for i, v in enumerate(a):
            s += v
            out[i + 1] = s
    return out


def _cumfu(u, f):
    out = [0.0] * (len(u) + 1)
    s = 0.0
    if f:
        r = f[1]
        uix = _uix_of(f)
        for i, v in enumerate(u):
            s += v * (r[uix[i]] if uix[i] >= 0 else 1.0)
            out[i + 1] = s
    else:
        for i, v in enumerate(u):
            s += v
            out[i + 1] = s
    return out


def _a_base(app, T, p):
    """Mix, curves and each install day's raw anchor (window revenue ÷ the curve's, its user-days; users the same) —
    kept per (T, hl). Install days before the run's start are carried as old users on their own anchor."""
    memo = app.setdefault("_fva_base", {})
    gc = p.get("gc") or 0
    key = (T, p["hl"], gc)
    if key in memo:
        return memo[key]
    coh, start = app["coh"], app["start"]
    fx, fnew = _amix(app, T, p["hl"], gc)
    a, u, maxage = (_curve_x if gc else F.curve)(coh, T, start, p["hl"], fx)
    cache_cum = {}

    def cums(f):
        k = id(f)
        if k not in cache_cum:
            cache_cum[k] = (_cumfr(a, f), _cumfu(u, f))
        return cache_cum[k]
    rows = []
    lo_x = min(coh) if coh else start
    for X, c in coh.items():
        if X < lo_x or X > T or not c.get("n"):
            continue
        n = c["n"]
        f = F._wk(fx, X)
        k = F._known(c, X, T)
        kd = dict(k)
        K = k[-1][0] if k else None
        exact = any(L in kd for L in (2, 4, 5))
        ca, cu = cums(f)
        row = {"X": X, "n": n, "f": f, "r": None, "ud": 0.0, "ru": None, "eu": 0.0}
        if k:
            wdw = _window(kd, K, exact)
            if wdw:
                lo, hi = wdw
                ob = _obs(kd, lo, hi)
                ex = n * (ca[hi + 1] - ca[lo])
                if ob is not None and ex > 0:
                    row["r"] = max(0.0, ob) / ex
                    row["ob"], row["ex"] = max(0.0, ob), ex
                    row["ud"] = n * (cu[hi + 1] - cu[lo])
        uk = F._uknown(c, X, T)
        if uk:
            Ku = max(uk)
            lags = [L for L in sorted(uk) if 1 <= L <= Ku][-3:] if Ku <= 30 else [Ku]
            if lags:
                ob = sum(uk[L] for L in lags)
                ex = sum(n * u[L] * _xfu(f, L) for L in lags if L < len(u))
                if ex > 0:
                    row["ru"] = ob / ex
                    row["eu"] = ex
        rows.append(row)
    out = {"fx": fx, "fnew": fnew, "a": a, "u": u, "maxage": maxage, "rows": rows}
    memo[key] = out
    return out


def _segs(cuts, a0, a1):
    """[a0, a1) split at every cut."""
    out = []
    i = a0
    while i < a1:
        j = next(c for c in cuts if c > i)
        j = min(j, a1)
        out.append((i, j))
        i = j
    return out


def _past(SC, T, a, u, NA):
    """Past days (index d ↔ T − PAST + 1 + d) by AB7 band: revenue Σ n·S·a·fr, users Σ n·U·u·fu."""
    pr = [[0.0] * PAST for _ in range(NLB)]
    pu = [[0.0] * PAST for _ in range(NLB)]
    add = operator.add
    for X, (n, f, sg, ug) in SC.items():
        bix, uix = _bix_of(f), _uix_of(f)
        uc = UCUTSX if uix is UIXX else UCUTS
        age_T = (T - X).days
        a0 = max(0, age_T - PAST + 1)
        off = age_T - PAST + 1
        for (s0, s1) in _segs(CUTS, a0, min(age_T + 1, NA)):
            co = n * (f[0][bix[s0]] if f else 1.0) * sg
            d0, d1 = s0 - off, s1 - off
            arr = pr[LBIX[s0]]
            arr[d0:d1] = map(add, arr[d0:d1], map(co.__mul__, a[s0:s1]))
        for (s0, s1) in _segs(uc, a0, min(age_T + 1, NA)):
            co = n * (f[1][uix[s0]] if (f and uix[s0] >= 0) else 1.0) * ug
            d0, d1 = s0 - off, s1 - off
            arr = pu[LBIX[s0]]
            arr[d0:d1] = map(add, arr[d0:d1], map(co.__mul__, u[s0:s1]))
    return pr, pu


def _future(SC, T, a, u, NA, h):
    fr = [[0.0] * h for _ in range(NLB)]
    fu = [[0.0] * h for _ in range(NLB)]
    add = operator.add
    for X, (n, f, sg, ug) in SC.items():
        bix, uix = _bix_of(f), _uix_of(f)
        uc = UCUTSX if uix is UIXX else UCUTS
        age_T = (T - X).days
        b0, b1 = age_T + 1, min(age_T + h + 1, NA)       # future day T + i ↔ age = age_T + i, index i − 1
        for (s0, s1) in _segs(CUTS, b0, b1):
            co = n * sg * (f[0][bix[s0]] if f else 1.0)
            d0, d1 = s0 - age_T - 1, s1 - age_T - 1
            arr = fr[LBIX[s0]]
            arr[d0:d1] = map(add, arr[d0:d1], map(co.__mul__, a[s0:s1]))
        for (s0, s1) in _segs(uc, b0, b1):
            co = n * ug * (f[1][uix[s0]] if (f and uix[s0] >= 0) else 1.0)
            d0, d1 = s0 - age_T - 1, s1 - age_T - 1
            arr = fu[LBIX[s0]]
            arr[d0:d1] = map(add, arr[d0:d1], map(co.__mul__, u[s0:s1]))
    return fr, fu


def _a_accum0(app, T, p, B):
    """The past days' model WITHOUT per-install-day anchors (n · a · fr), by band — what Λ is measured on."""
    memo = app.setdefault("_fva_acc0", {})
    key = (T, p["hl"], p.get("gc") or 0)
    if key not in memo:
        SC0 = {row["X"]: (row["n"], row["f"], 1.0, 1.0) for row in B["rows"]}
        memo[key] = _past(SC0, T, B["a"], B["u"], len(B["a"]))
    return memo[key]


def _fit_rest(pts, w):
    """(today's level = median of the last w days, decay = −slope of log, never growing)."""
    if len(pts) < 20:
        return 0.0, 0.0
    recent = sorted(v for x, v in pts if x > -w)
    lvl0 = math.exp(recent[len(recent) // 2]) if recent else 0.0
    mx = sum(x for x, _ in pts) / len(pts)
    my = sum(v for _, v in pts) / len(pts)
    den = sum((x - mx) ** 2 for x, _ in pts)
    slope = sum((x - mx) * (v - my) for x, v in pts) / den if den else 0.0
    return lvl0, max(0.0, -slope)


def _clip(x):
    return min(10.0, max(0.1, x))


def _ga4(app, T, w):
    """The newest w days ≤ T WITH a usable GA4 read (searched back GA4_LAG days at most): actual revenue by AB7 band
    (GA4 by install age × that day's AdMob ÷ GA4; > 427 = AdMob − the rest), users the same (> 427 = DAU − the rest),
    + the day indexes used."""
    days, g4 = app["days"], app.get("g4") or {}
    act, uact, dk, du = [0.0] * NLB, [0.0] * NLB, [], []
    for d in range(PAST - 1, max(-1, PAST - 1 - w - GA4_LAG), -1):
        if len(dk) >= w and len(du) >= w:
            break
        D = T - timedelta(days=PAST - 1 - d)
        e = days.get(D) or {}
        g = g4.get(D)
        A_ = e.get("rev")
        if len(dk) < w and g and A_ and g.get("k") and 0.2 <= g["k"] <= 5.0 and g.get("rb") and len(g["rb"]) >= 6:
            k = g["k"]
            rb = g["rb"]
            for j in range(6):
                act[j] += k * rb[j]
            act[6] += max(0.0, A_ - k * sum(rb))
            dk.append(d)
        ab = g.get("ab") if g else None
        if len(du) < w and ab and len(ab) >= 6 and e.get("dau"):
            for j in range(6):
                uact[j] += ab[j]
            uact[6] += max(0.0, e["dau"] - sum(ab))
            du.append(d)
    return act, uact, dk, du


def _ratios(act, mod, sup=None):
    """Per band: actual ÷ model (a band the model has no install days in carries the one before; from 30–89 on a band
    filled to share sup of its ages is trusted sup ÷ (sup + LEV_SUP), else the band before's); + the actual per day the
    model has nothing for."""
    out = []
    for j in range(NLB):
        if mod[j] > 1e-9 and act[j] > 0:
            v = _clip(act[j] / mod[j])
            if sup is not None and out and j >= 3:
                z = sup[j] / (sup[j] + LEV_SUP)
                v = out[-1] + (v - out[-1]) * z
            out.append(v)
        else:
            out.append(out[-1] if out else 1.0)
    flat = sum(act[j] for j in range(NLB) if mod[j] <= 1e-9 and act[j] > 0)
    return out, flat


def _support(app, T, B):
    """Per AB7 band: the share of its ages (> 427: the next 365) the run's own install days fill at T."""
    start = app["start"]
    have = [0] * NLB
    for row in B["rows"]:
        if row["X"] >= start and row["n"]:
            have[LBIX[min((T - row["X"]).days, MAXA)]] += 1
    width = [hi - lo + 1 if j < NLB - 1 else 365 for j, (lo, hi) in enumerate(AB7)]
    return [min(1.0, h / w_) for h, w_ in zip(have, width)]


def _lam(app, T, p, w, A0, B):
    """Λ: how the install days now in each GA4 band earn (and keep users) vs the curve without anchors, the newest w
    GA4 days — None without enough of them."""
    memo = app.setdefault("_fva_lam", {})
    key = (T, p["hl"], w, p.get("gc") or 0)
    if key in memo:
        return memo[key]
    act, uact, dk, du = _ga4(app, T, w)
    need = max(2, (w + 1) // 2)
    py, pyu = A0
    out = None
    sup = _support(app, T, B)
    if len(dk) >= need:
        mod = [sum(py[j][d] for d in dk) for j in range(NLB)]
        lam, flat = _ratios(act, mod, sup)
        out = {"lam": lam, "flat": flat / len(dk), "act": act, "mod": mod, "dk": dk}
        if len(du) >= need:
            umod = [sum(pyu[j][d] for d in du) for j in range(NLB)]
            ul, uflat = _ratios(uact, umod, sup)
            out.update(ulam=ul, uflat=uflat / len(du), uact=uact, du=du)
        out["sup"] = sup
    memo[key] = out
    return out


def _a_scales(app, T, p, B):
    """Per install day: (n, f, S, U) — S its revenue standing (window revenue ÷ the curve's, trusted UD ÷ (UD + Kc),
    shrunk toward the pooled standing of the install days within ±LOC days, itself trusted the same way; clip 0.2–5),
    U its users' standing (trusted E ÷ (E + KU))."""
    memo = app.setdefault("_fva_sc", {})
    key = (T, p["hl"], p["Kc"], p.get("gc") or 0)
    if key in memo:
        return memo[key]
    rows = B["rows"]
    Kc = p["Kc"]
    rel = {}
    for row in rows:
        if row["r"] is not None:
            rel[row["X"]] = (row["ob"], row["ex"], row["ud"])
    loc = {}
    rr = sorted(rel.items())
    xs = [x for x, _ in rr]
    cob, cex, cud = [0.0], [0.0], [0.0]
    for _, (ob, ex, ud) in rr:
        cob.append(cob[-1] + ob)
        cex.append(cex[-1] + ex)
        cud.append(cud[-1] + ud)
    for X, _ in rr:
        j0 = bisect.bisect_left(xs, X - timedelta(days=LOC))
        j1 = bisect.bisect_right(xs, X + timedelta(days=LOC))
        ob, ex, ud = cob[j1] - cob[j0], cex[j1] - cex[j0], cud[j1] - cud[j0]
        if ex > 0:
            loc[X] = 1.0 + (ob / ex - 1.0) * ud / (ud + Kc)
    out = {}
    for row in rows:
        X = row["X"]
        if X not in rel:
            sg = 1.0
        else:
            ob, ex, ud = rel[X]
            z = ud / (ud + Kc)
            base = loc.get(X, 1.0)
            dl, di = base - 1.0, (ob / ex - base) * z         # the batch's standing, this install day's own on top
            sg = min(5.0, max(0.2, 1.0 + dl + di))
        if row["ru"] is not None:
            zu = row["eu"] / (row["eu"] + KU)
            ug = min(5.0, max(0.2, 1.0 + (row["ru"] - 1.0) * zu))
        else:
            ug = 1.0
        out[X] = (row["n"], row["f"], sg, ug)
    memo[key] = out
    return out


def _a_accum(app, T, p, B, SC, h):
    memo = app.setdefault("_fva_acc", {})
    key = (T, p["hl"], p["Kc"], h, p.get("gc") or 0)
    if key not in memo:
        NA = len(B["a"])
        pr, pu = _past(SC, T, B["a"], B["u"], NA)
        fr, fu = _future(SC, T, B["a"], B["u"], NA, h)
        memo[key] = {"pr": pr, "pu": pu, "fr": fr, "fu": fu}
    return memo[key]


def _single(app, T, w, arr, field):
    """One level: the median over the last w days of actual ÷ model (no GA4 read: the bands can not be measured)."""
    days = app["days"]
    v = []
    for d in range(PAST - w, PAST):
        D = T - timedelta(days=PAST - 1 - d)
        e = days.get(D)
        m = sum(arr[j][d] for j in range(NLB))
        if e and e.get(field) and m > 0:
            v.append(e[field] / m)
    return sorted(v)[len(v) // 2] if v else 1.0


def _levels(app, T, p, A, LAM, LAMn=None):
    """lev[7] for past install days by age band, new[7] for the installs still to come (Λ of the young bands, ages ≥ 90
    the 30–89 one), ulev / unew for users, rest (m split), flat (actual per day the model has no install days for),
    and for q: pmod (the levelled model of the newest 21 past days) and tail (the days AdMob has, GA4 not yet)."""
    days = app["days"]
    w = p["w"]
    pr, pu = A["pr"], A["pu"]
    one = [1.0] * NLB
    out = {"lev": one, "ulev": one, "new": one, "unew": one, "rest": (0.0, 0.0), "urest": (0.0, 0.0),
           "mode": "single", "flat": 0.0, "uflat": 0.0}
    split = p.get("m") == "split"
    if LAM is not None:
        g4 = app.get("g4") or {}
        dk, act = LAM["dk"], LAM["act"]
        mod = [sum(pr[j][d] for d in dk) for j in range(NLB)]
        NL = LAMn or LAM                      # the installs still to come: Λ over their own window wn
        lv, fl = _ratios(act, mod, LAM.get("sup"))
        lev = list(lv)
        nlam = NL["lam"]
        new = list(nlam[:4]) + [nlam[3]] * 3
        tail = []
        for d in range(max(dk) + 1, PAST):
            e = days.get(T - timedelta(days=PAST - 1 - d)) or {}
            if e.get("rev"):
                tail.append((d, e["rev"]))
        out.update(mode="bands", lev=lev, new=new, flat=fl / len(dk))
        if split:                             # > 427 (and what the model has no install days for): a decaying rest
            lev[6] = lev[5] if mod[5] > 1e-9 else 1.0
            pts = []
            for d in range(PAST):
                D = T - timedelta(days=PAST - 1 - d)
                e = days.get(D) or {}
                g = g4.get(D)
                if g and e.get("rev") and g.get("k") and 0.2 <= g["k"] <= 5.0 and g.get("rb"):
                    r_ = e["rev"] - g["k"] * sum(g["rb"]) - lev[6] * pr[6][d]
                    if r_ > 0:
                        pts.append((d - (PAST - 1), math.log(r_)))
            out["rest"] = _fit_rest(pts, w)
            if mod[6] <= 1e-9 and act[6] > 0:
                out["flat"] -= act[6] / len(dk)
        r0, rho_ = out["rest"]
        out["pmod"] = {d: sum(lev[j] * pr[j][d] for j in range(NLB)) + out["flat"] + r0 * math.exp(rho_ * (PAST - 1 - d))
                       for d in range(PAST - 21, PAST)}
        out["tail"] = [(d, a_, sum(lev[j] * pr[j][d] for j in range(NLB)) + out["flat"]
                        + r0 * math.exp(rho_ * (PAST - 1 - d))) for d, a_ in tail]
        if LAM.get("ulam") is not None:
            du, uact = LAM["du"], LAM["uact"]
            umod = [sum(pu[j][d] for d in du) for j in range(NLB)]
            ul, ufl = _ratios(uact, umod, LAM.get("sup"))
            nul = NL.get("ulam") or LAM["ulam"]
            out.update(ulev=list(ul), unew=list(nul[:4]) + [nul[3]] * 3, uflat=ufl / len(du))
            return out
        uv = _single(app, T, w, pu, "dau")
        out.update(ulev=[uv] * NLB, unew=[uv] * NLB)
        return out
    lvl = _single(app, T, w, pr, "rev")
    ulv = _single(app, T, w, pu, "dau")
    out.update(lev=[lvl] * NLB, new=[lvl] * NLB, ulev=[ulv] * NLB, unew=[ulv] * NLB)
    if split:
        out.update(lev=one, new=one, ulev=one, unew=one)
        pts, upts = [], []
        for d in range(PAST):
            D = T - timedelta(days=PAST - 1 - d)
            e = days.get(D)
            if e and e.get("rev"):
                r_ = e["rev"] - sum(pr[j][d] for j in range(NLB))
                if r_ > 0:
                    pts.append((d - (PAST - 1), math.log(r_)))
            if e and e.get("dau"):
                q_ = e["dau"] - sum(pu[j][d] for j in range(NLB))
                if q_ > 0:
                    upts.append((d - (PAST - 1), math.log(q_)))
        out["rest"] = _fit_rest(pts, w)
        out["urest"] = _fit_rest(upts, w)
    return out


def _a_prepare(v, T, p, ctx):
    B = _a_base(v, T, p)
    SC = _a_scales(v, T, p, B)
    A0 = _a_accum0(v, T, p, B)
    LAM = _lam(v, T, p, p["w"], A0, B)
    LAMn = _lam(v, T, p, p["wn"], A0, B) if p.get("wn") else None
    A = _a_accum(v, T, p, B, SC, H)
    LV = _levels(v, T, p, A, LAM, LAMn)
    a, u = B["a"], B["u"]
    seas = (ctx or {}).get("seas") or {m: 1.0 for m in range(1, 13)}
    s0 = seas.get(T.month, 1.0) or 1.0
    org, per_usd = F.installs_model(v["days"], T, p["W"])
    fnew = B["fnew"]
    nl, unl = LV["new"], LV["unew"]
    unit = [a[L] * _xfr(fnew, L) * nl[LBIX[L]] for L in range(len(a))]
    uunit = [u[L] * _xfu(fnew, L) * unl[LBIX[L]] for L in range(len(u))]
    return {"T": T, "p": p, "B": B, "SC": SC, "A": A, "LV": LV, "LAM": LAM, "LAMn": LAMn, "seas": seas, "s0": s0,
            "org": org, "per_usd": per_usd, "unit": unit, "uunit": uunit}


def _ga(st, D):
    if D <= st["T"]:
        return 1.0
    return (st["seas"].get(D.month, 1.0) / st["s0"]) ** st["p"]["g"] if st["s0"] else 1.0


def _a_parts(st, spend, h, org, per_usd, up=None):
    """View A per future day: old users' revenue, new installs' revenue (organic, paid), users the same, installs. up:
    the paid installs per day the users / installs follow (the country model, _cs_paid) — the revenue stays on spend ×
    per_usd (None: both on it)."""
    T, A, LV = st["T"], st["A"], st["LV"]
    lev, ulev = LV["lev"], LV["ulev"]
    rest0, rho = LV["rest"]
    urest0, urho = LV["urest"]
    flat, uflat = LV["flat"], LV["uflat"]
    unit, uunit = st["unit"], st["uunit"]
    NA = len(unit)
    fr, fu = A["fr"], A["fu"]
    ro, rg, rp, uo, ug, upd, nn = [], [], [], [], [], [], []
    fut, futu = [], []
    for i in range(1, h + 1):
        D = T + timedelta(days=i)
        g = _ga(st, D)
        o = sum(lev[j] * fr[j][i - 1] for j in range(NLB))
        du = sum(ulev[j] * fu[j][i - 1] for j in range(NLB))
        npd = per_usd * spend.get(D, 0.0)
        nu = npd if up is None else up[i - 1]
        fut.append(npd)
        futu.append(nu)
        r_o = r_p = u_o = u_p = 0.0
        for j, npj in enumerate(fut):
            age = i - 1 - j
            if age < NA:
                r_o += org * unit[age]
                r_p += npj * unit[age]
                u_o += org * uunit[age]
                u_p += futu[j] * uunit[age]
        ro.append((o + flat) * g + rest0 * math.exp(-rho * i) * g)
        rg.append(r_o * g)
        rp.append(r_p * g)
        uo.append(du + uflat + urest0 * math.exp(-urho * i))
        ug.append(u_o)
        upd.append(u_p)
        nn.append(org + nu)
    return {"old": ro, "org": rg, "paid": rp, "uold": uo, "uorg": ug, "upaid": upd, "n": nn}


def _a_cohort_rev(st, X, k_age, ages):
    SC = st["SC"].get(X)
    if SC is None:
        return [0.0] * len(ages)
    n, f, sg, _ = SC
    a = st["B"]["a"]
    lev = st["LV"]["lev"]
    out, acc, L = [], 0.0, k_age
    for C in ages:
        while L < C:
            L += 1
            if L < len(a):
                acc += n * sg * a[L] * _xfr(f, L) * lev[LBIX[L]] * _ga(st, X + timedelta(days=L))
        out.append(acc)
    return out


def _a_cohort_users(st, X, lags):
    SC = st["SC"].get(X)
    if SC is None:
        return None
    n, f, _, ug = SC
    u = st["B"]["u"]
    ulev = st["LV"]["ulev"]
    return [n * ug * u[Lg] * _xfu(f, Lg) * ulev[LBIX[Lg]] if Lg < len(u) else 0.0 for Lg in lags]


def _a_new_value(st, X, ages):
    unit = st["unit"]
    out, acc, L = [], 0.0, -1
    for C in ages:
        while L < C:
            L += 1
            if L < len(unit):
                acc += unit[L] * _ga(st, X + timedelta(days=L))
        out.append(acc)
    return out


# ══ view B — users × ARPDAU ═══════════════════════════════════════════════════════════════════════════════════════
AB = ((0, 0), (1, 6), (7, 29), (30, 89), (90, 364), (365, 427), (428, 100000))
NB = len(AB)
MAXR = 1600
BAND = [next(i for i, (lo, hi) in enumerate(AB) if lo <= L <= hi) for L in range(MAXR + 1)]
CHAIN = (30, 45, 60, 90, 120, 180, 270, 365)
CB, CL = F.CB, F.CL
CKC = 1000.0
UBANDS = (3, 4, 5)             # bands re-anchored on GA4's measured users
K0 = 200.0                     # user-days a band's ARPDAU needs before its own window is trusted half-way (else its
LONG = 112                     # LONG-day value, then the band before × the portfolio's band ratio)
PORT_UD = 2000.0               # user-days (LONG days) an app needs in two bands to give the portfolio their ratio
KA = 1e9                       # an install day's own ARPDAU anchor: credibility UD ÷ (UD + KA) — practically off
NW = 56                        # new installs' organic / paid split: the newest install days that completed a band
MIDS = (0, 3, 15, 55, 190, 395, 600)     # a typical age inside each GA4 band (the portfolio shape's anchor points)
NVB = ((0, 0), (1, 1), (2, 3), (4, 7), (8, 14), (15, 30))
NV2AB = (0, 1, 1, 1, 2, 2)     # the GA4 band each one's ARPDAU is measured in
S0_PI = 0.10                   # the paid-share spread at which the split is trusted half-way
NV_N0 = 50.0                   # installs at which a day's weight in the split is half
_BANDR = [None, None]          # (state bandr object, its parsed index)


def _bandr_index(bandr):
    if not bandr:
        return None
    if _BANDR[0] is not bandr:
        rows = []
        for k, v in bandr.items():
            try:
                if isinstance(v, list) and len(v) == NB:
                    rows.append((date.fromisoformat(k), [float(x) for x in v]))
            except (TypeError, ValueError):
                continue
        rows.sort(key=lambda r: r[0])
        _BANDR[0], _BANDR[1] = bandr, ([r[0] for r in rows], [r[1] for r in rows])
    return _BANDR[1]


def _pre(app):
    """Per app (or view), once: prefix sums over the GA4 days (rb[7], ab[7], AdMob and GA4 revenue on days having both,
    DAU, present) — every window is trailing, so valid at any T ≥ its last day."""
    if "_fvb" in app:
        return app["_fvb"]
    days, g4 = app["days"], app.get("g4") or {}
    coh = app["coh"]
    first = min(coh) if coh else app.get("start")
    pre = {"first": first, "arp7": {}, "memo": {}, "have": set(),
           "bandr": _bandr_index((app.get("port") or {}).get("bandr"))}
    app["_fvb"] = pre
    if not g4:
        pre["d0"], pre["P"] = None, None
        return pre
    d0, d1 = min(g4), max(g4)
    nd = (d1 - d0).days + 1
    Wd = 2 * NB + 4
    P = [[0.0] * Wd]
    for i in range(nd):
        D = d0 + timedelta(days=i)
        e = g4.get(D)
        row = [0.0] * Wd
        if e:
            ab = list(e.get("ab") or [])
            rb = list(e["rb"])
            if len(ab) == 6 and len(rb) == 6:
                dd = days.get(D) or {}
                dau = dd.get("dau") or 0
                ab.append(max(0.0, dau - sum(ab)) if dau else 0.0)
                rb.append(max(0.0, e["rev"] - sum(rb)))
                row[:NB] = rb
                row[NB:2 * NB] = ab
                a = dd.get("rev")
                if a and e["rev"] > 0:
                    row[2 * NB] = a
                    row[2 * NB + 1] = e["rev"]
                row[2 * NB + 2] = dau
                row[2 * NB + 3] = 1.0
                pre["have"].add(D)
        P.append([x + y for x, y in zip(P[-1], row)])
    pre["d0"], pre["P"], pre["nd"] = d0, P, nd
    return pre


def _win(pre, D0, D1):
    """Sums over GA4 days D0..D1: rb[b], ab[b], AdMob ÷ GA4 on the days having both, DAU, days."""
    P = pre.get("P")
    if not P:
        return {"rb": [0.0] * NB, "ab": [0.0] * NB, "k": 1.0, "dau": 0.0, "n": 0, "adm": 0.0}
    i0 = max(0, (D0 - pre["d0"]).days)
    i1 = min(pre["nd"], (D1 - pre["d0"]).days + 1)
    if i1 <= i0:
        return {"rb": [0.0] * NB, "ab": [0.0] * NB, "k": 1.0, "dau": 0.0, "n": 0, "adm": 0.0}
    a, b = P[i0], P[i1]
    d = [y - x for x, y in zip(a, b)]
    ga = d[2 * NB + 1]
    return {"rb": d[:NB], "ab": d[NB:2 * NB], "k": d[2 * NB] / ga if ga > 0 else 1.0, "dau": d[2 * NB + 2],
            "n": int(round(d[2 * NB + 3])), "adm": d[2 * NB]}


def _monday(D):
    return D - timedelta(days=D.weekday())


def _pmon(pre, D):
    """The band ratios' Monday for day D: the Monday at or before D, and never after the newest GA4 day the app (its
    lag view) has — so at origin T it is ≤ T − glag, and every app's data behind that Monday (bandr) was there at T."""
    if pre.get("P"):
        D = min(D, pre["d0"] + timedelta(days=pre["nd"] - 1))
    return _monday(D)


def _port_ratio(pre, M):
    """The portfolio's ARPDAU ratio of each band to the band before at Monday M (state.json "bandr", made at the end of
    the last build from every app's data ≤ M − (its GA4 lag − the smallest)): a Monday not there yet takes the newest
    one before it; none: 1. Looked up at _pmon() only."""
    ix = pre.get("bandr")
    if not ix:
        return [1.0] * NB
    i = bisect.bisect_right(ix[0], M) - 1
    return ix[1][i] if i >= 0 else [1.0] * NB


def _arp_win(pre, D, w):
    """Band ARPDAU (AdMob USD per GA4 active user) over the w days to D, each band shrunk (K0 user-days) to its own
    LONG-day value, that one to the band before × the portfolio's band ratio."""
    s = _win(pre, D - timedelta(days=w - 1), D)
    lg = _win(pre, D - timedelta(days=LONG - 1), D)
    pr = _port_ratio(pre, _pmon(pre, D))
    out = []
    prev = None
    for b in range(NB):
        lv = None
        pb = prev * pr[b] if prev is not None else None
        if lg["ab"][b] > 0 or pb is not None:
            num = lg["rb"][b] * lg["k"] + (K0 * pb if pb is not None else 0.0)
            den = lg["ab"][b] + (K0 if pb is not None else 0.0)
            lv = num / den if den > 0 else pb
        if lv is None:
            out.append(None)
            continue
        v = (s["rb"][b] * s["k"] + K0 * lv) / (s["ab"][b] + K0)
        out.append(v)
        prev = lv
    return out, s


def _arp7(pre, D):
    """Band ARPDAU on a past day: its trailing 7 days (shrunk)."""
    m = pre["arp7"]
    if D not in m:
        m[D] = _arp_win(pre, D, 7)[0]
    return m[D]


def _bmix(app, T, hl, gc=0):
    """B's country mix: weeks from the first full country read on (cfrom), a slot added late folded into ZZ while it was
    partial; per country its users at each lag and its revenue per user-day (cells to day 90) ÷ every install's →
    ({week: (fu, fa)}, the newest two complete weeks' (fu, fa)). gc 2: + the late lags (c2; _b_late), gc 3: + the late
    bands too, each country shrunk toward its standing in the lag / band before."""
    pre = _pre(app)
    key = ("mix", T, hl, gc)
    if key in pre["memo"]:
        return pre["memo"][key]
    cty, ida = app.get("cty") or {}, app.get("ida") or {}
    cset = ida.get("cset") or []
    res = ({}, None)
    cfrom = date.fromisoformat(ida["cfrom"]) if ida.get("cfrom") else None
    weeks = sorted(W for W in cty if (cfrom is None or W >= cfrom) and W <= T)
    if not cty or not cset or not weeks:
        pre["memo"][key] = res
        return res
    zz = str(cset.index("ZZ")) if "ZZ" in cset else None
    since = {}
    for cc, rr in (ida.get("cset_since") or {}).items():
        if cc in cset:
            since[str(cset.index(cc))] = [(date.fromisoformat(a), date.fromisoformat(b)) for a, b in rr]
    nb, nl = len(CB), len(CL)

    def cells_of(W):
        cm = pre.setdefault("cells", {})
        if W in cm:
            return cm[W]
        out = {}
        for k, e in cty[W].items():
            kk = k
            if zz is not None and k in since and any(W + timedelta(days=96) >= a and W <= b for a, b in since[k]):
                kk = zz
            x = out.setdefault(kk, {"n": 0.0, "r": [0.0] * nb, "u": [0.0] * nl, "hu": False})
            x["n"] += e.get("n") or 0
            for b, v in enumerate((e.get("r") or [0] * nb)[:nb]):
                x["r"][b] += (v or 0) / 1e6
            if e.get("u"):
                x["hu"] = True
                for j, v in enumerate(e["u"][:nl]):
                    x["u"][j] += v or 0
        cm[W] = out
        return out

    A_ = (0,) + tuple(CL)

    def udays(n, u, b):
        """User-days of band b from the users at the lags (linear between them; age 0 = the installs)."""
        if b == 0:
            return n
        U = [n] + list(u)
        jh = A_.index(CB[b][1])
        m = CB[b][1] - A_[jh - 1]
        return (m / 2.0) * (U[jh - 1] + U[jh]) + (U[jh] - U[jh - 1]) / 2.0

    us, ua = {}, [[0.0, 0.0] for _ in range(nl)]
    rs, ra = {}, [[0.0, 0.0, 0.0] for _ in range(nb)]          # [rev, user-days, installs]
    for W in weeks:
        wt = 0.5 ** ((T - W).days / hl) if hl < 99999 else 1.0
        end = W + timedelta(days=6)
        cells = cells_of(W)
        for j, g in enumerate(CL):
            if end + timedelta(days=g) > T:
                break
            for k, e in cells.items():
                if k == "gap" or not e["hu"]:
                    continue
                ua[j][0] += wt * e["u"][j]
                ua[j][1] += wt * e["n"]
                x = us.setdefault(k, [[0.0, 0.0] for _ in range(nl)])
                x[j][0] += wt * e["u"][j]
                x[j][1] += wt * e["n"]
        for b, (lo, hi) in enumerate(CB):
            if end + timedelta(days=hi) > T:
                break
            for k, e in cells.items():
                if k == "gap" or not e["hu"] or e["n"] <= 0:
                    continue
                ud = udays(e["n"], e["u"], b)
                if ud <= 0:
                    continue
                ra[b][0] += wt * e["r"][b]
                ra[b][1] += wt * ud
                ra[b][2] += wt * e["n"]
                x = rs.setdefault(k, [[0.0, 0.0, 0.0] for _ in range(nb)])
                x[b][0] += wt * e["r"][b]
                x[b][1] += wt * ud
                x[b][2] += wt * e["n"]

    LAGB = [None, 0, 1, 2, 3, 4, 5, 6]          # the users' lag index weighting each CB band (band 0: installs)
    lr = lu = 10 ** 9                            # gc: from these on, shrunk toward the country's previous standing
    if gc:
        bad_of = {W: [k for k in since if zz is not None
                      and any(W + timedelta(days=96) >= a and W <= b for a, b in since[k])] for W in weeks}
        _b_late(app, T, hl, weeks, cells_of, bad_of, zz, us, ua, rs, ra, gc >= 3)
        lr, lu, nb, nl = nb, nl, len(CBX), len(CLX)
        LAGB = LAGB + [8, 10, 10]                # 91–180 → users at 180, 181–365 and 366–427 → users at 365

    def rel_u():
        out = {k: [1.0] * nl for k in us}
        for j in range(nl):
            V, N = ua[j]
            if N <= 0 or V <= 0:
                for k in us:
                    out[k][j] = out[k][j - 1] if j else 1.0
                continue
            ref = 0.0
            for k, x in us.items():
                v, n = x[j]
                m = (v / n) / (V / N) if n > 0 else (out[k][j - 1] if j else 1.0)
                if j >= lu:
                    m = out[k][j - 1] + (m - out[k][j - 1]) * (n / (n + CKC)) if n > 0 else m
                else:
                    m = 1.0 + (m - 1.0) * (n / (n + CKC)) if n > 0 else m
                out[k][j] = min(10.0, max(0.05, m))
                ref += max(0.0, n) / N * out[k][j]
            if ref > 0:
                for k in us:
                    out[k][j] /= ref
        return out

    def rel_a():
        out = {k: [1.0] * nb for k in rs}
        for b in range(nb):
            R, UD, N = ra[b]
            if UD <= 0 or R <= 0:
                for k in rs:
                    out[k][b] = out[k][b - 1] if b else 1.0
                continue
            ref = 0.0
            for k, x in rs.items():
                r, ud, n = x[b]
                m = (r / ud) / (R / UD) if ud > 0 else (out[k][b - 1] if b else 1.0)
                if b >= lr:
                    m = out[k][b - 1] + (m - out[k][b - 1]) * (n / (n + CKC)) if n > 0 else m
                else:
                    m = 1.0 + (m - 1.0) * (n / (n + CKC)) if n > 0 else m
                out[k][b] = min(10.0, max(0.05, m))
                ref += max(0.0, ud) / UD * out[k][b]
            if ref > 0:
                for k in rs:
                    out[k][b] /= ref
        return out
    mu, ma = rel_u(), rel_a()

    def fac(cl):
        tot = sum(e["n"] for cells in cl for e in cells.values())
        if tot <= 0:
            return None
        fu = [0.0] * nl
        fan, fad = [0.0] * nb, [0.0] * nb
        for cells in cl:
            for k, e in cells.items():
                q = e["n"] / tot
                if q <= 0:
                    continue
                v, a = mu.get(k), ma.get(k)
                for j in range(nl):
                    fu[j] += q * (v[j] if v else 1.0)
                for b in range(nb):
                    uw = q * ((v[LAGB[b]] if v else 1.0) if LAGB[b] is not None else 1.0)
                    fan[b] += uw * (a[b] if a else 1.0)
                    fad[b] += uw
        fa = [max(0.05, fan[b] / fad[b]) if fad[b] > 0 else 1.0 for b in range(nb)]
        return [max(0.05, x) for x in fu], fa
    fx = {}
    done = [W for W in weeks if W + timedelta(days=6) <= T]
    for W in done:
        f = fac([cells_of(W)])
        if f:
            fx[W] = f
    newest = fac([cells_of(W) for W in done[-2:]]) if done else None
    for W in weeks:                     # the week still running at T: its cells hold installs after T — the newest mix
        if W not in fx and newest:
            fx[W] = newest
    res = (fx, newest)
    pre["memo"][key] = res
    pre["memo"][("slot",) + key[1:]] = (mu, ma, LAGB, nb, nl)            # each country's own factors (the planner)
    return res


def _b_late(app, T, hl, weeks, cells_of, bad_of, zz, us, ua, rs, ra, rev=True):
    """gc: view B's late lags (users per install, c2 u2) and late bands (revenue per user-day; user-days linear between
    the lags, 366–427 flat at the 365 users) into its accumulators, extended in place; a (week, lag / band) only when
    every activity day of it (and of the lags its user-days need) was read; weights relative to the newest complete
    week. rev False (gc 2): the late lags only — the late bands' revenue per user-day stays the 61–90 standing."""
    nb, nl, nbx, nlx = len(CB), len(CL), len(CBX), len(CLX)
    fo2 = _xfold(app, "c2st")
    for x in us.values():
        x.extend([0.0, 0.0] for _ in range(nlx - nl))
    for x in rs.values():
        x.extend([0.0, 0.0, 0.0] for _ in range(nbx - nb))
    ua.extend([0.0, 0.0] for _ in range(nlx - nl))
    ra.extend([0.0, 0.0, 0.0] for _ in range(nbx - nb))
    if fo2 is None:
        return

    def ok(W, a, b):
        return W + timedelta(days=6 + b) <= T and _cov(fo2, W + timedelta(days=a), W + timedelta(days=6 + b))
    lc = {}
    for W in weeks:
        lc[W] = _late_cells(app, W, {k: {"n": e["n"]} for k, e in cells_of(W).items()}, bad_of[W], zz)
    okl = [[W for W in weeks if ok(W, g, g)] for g in C2L]
    okb = [[W for W in weeks if rev and ok(W, lo, hi)] for lo, hi in C2B]

    def wt(W, ws):
        return 0.5 ** ((max(ws) - W).days / hl) if hl < 99999 else 1.0
    for i, ws in enumerate(okl):
        for W in ws:
            w = wt(W, ws)
            for k, e in lc[W].items():
                if k == "gap":
                    continue
                ua[nl + i][0] += w * e["u2"][i]
                ua[nl + i][1] += w * e["n"]
                x = us.setdefault(k, [[0.0, 0.0] for _ in range(nlx)])
                x[nl + i][0] += w * e["u2"][i]
                x[nl + i][1] += w * e["n"]
    need = ((0, 1), (1, 2, 3), (3,))                  # the late lags each late band's user-days need
    for i, ws in enumerate(okb):
        have = [set(okl[j]) for j in need[i]]
        ws = [W for W in ws if all(W in h_ for h_ in have)]
        for W in ws:
            w = wt(W, ws)
            leg = cells_of(W)
            for k, e in lc[W].items():
                if k == "gap" or e["n"] <= 0:
                    continue
                u2 = e["u2"]
                if i == 0:
                    lg = leg.get(k)
                    if not lg or not lg.get("hu"):
                        continue
                    ud = _useg(90, lg["u"][6], 120, u2[0]) + _useg(120, u2[0], 180, u2[1])
                elif i == 1:
                    ud = _useg(180, u2[1], 270, u2[2]) + _useg(270, u2[2], 365, u2[3])
                else:
                    ud = 62.0 * u2[3]
                if ud <= 0:
                    continue
                r = e["r2"][i] / 1e6
                ra[nb + i][0] += w * r
                ra[nb + i][1] += w * ud
                ra[nb + i][2] += w * e["n"]
                x = rs.setdefault(k, [[0.0, 0.0, 0.0] for _ in range(nbx)])
                x[nb + i][0] += w * r
                x[nb + i][1] += w * ud
                x[nb + i][2] += w * e["n"]


def _useg(a, va, b, vb):
    """Σ over ages a+1 … b of the users, linear from (a, va) to (b, vb)."""
    return (b - a) * va + (vb - va) * (b - a + 1) / 2.0


def _bfu(f, L):
    if not f or L == 0:
        return 1.0
    return f[0][(UIXX if len(f[0]) > NCL else F.UIX)[min(L, F.MAX_AGE)]]


def _bfa(f, L):
    return f[1][(BIXX if len(f[1]) > NCB else F.BIX)[min(L, F.MAX_AGE)]] if f else 1.0


def _bwk(fx, X):
    return fx.get(X - timedelta(days=X.weekday())) if fx else None


def _retention(app, T, hl, gc=0):
    """R(L): active users per install at age L — day by day to 30 (pooled, half-life hl, mix-free), then the chain
    ladder 30→45→…→365 (each step from the install days that reached BOTH lags), then a power law fitted on the lags
    ≥ 90."""
    pre = _pre(app)
    key = ("cur", T, hl, gc)
    if key in pre["memo"]:
        return pre["memo"][key]
    coh, start = app["coh"], app["start"]
    fx = _bmix(app, T, hl, gc)[0]
    num, den = [0.0] * 31, [0.0] * 31
    cn, cd = [0.0] * len(CHAIN), [0.0] * len(CHAIN)
    for X, co in coh.items():
        if X < start or X > T or not co.get("n"):
            continue
        n = co["n"]
        w = 0.5 ** ((T - X).days / hl) if hl < 99999 else 1.0
        f = _bwk(fx, X)
        uk = F._uknown(co, X, T)
        for L in range(31):
            v = uk.get(L)
            if v is not None:
                num[L] += w * v
                den[L] += w * n * _bfu(f, L)
        for i in range(1, len(CHAIN)):
            a0, a1 = CHAIN[i - 1], CHAIN[i]
            v0, v1 = uk.get(a0), uk.get(a1)
            if v0 and v1 is not None:
                cd[i] += w * v0 / _bfu(f, a0)
                cn[i] += w * v1 / _bfu(f, a1)
    pts = {L: num[L] / den[L] for L in range(31) if den[L] > 0 and num[L] > 0}
    if 30 in pts:
        v = pts[30]
        for i in range(1, len(CHAIN)):
            if cd[i] <= 0 or cn[i] <= 0:
                break
            v *= cn[i] / cd[i]
            pts[CHAIN[i]] = v
    R = F._fill(pts, MAXR) if pts else [0.0] * (MAXR + 1)
    if pts:                                           # the tail from the slope of the last lags ≥ 90
        tl = sorted(L for L in pts if L >= 90 and pts[L] > 0)
        if len(tl) >= 2:
            xs = [math.log(L + 1) for L in tl]
            ys = [math.log(pts[L]) for L in tl]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            dn = sum((x - mx) ** 2 for x in xs)
            beta = -sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / dn if dn > 0 else 1.0
            beta = min(2.0, max(0.05, beta))
            last = tl[-1]
            v = pts[last]
            for L in range(last + 1, MAXR + 1):
                R[L] = v * ((L + 1) / (last + 1)) ** (-beta)
    pre["memo"][key] = R
    return R


def _port_shape(pre, D):
    """log-ARPDAU by age from the portfolio's band ratios at day D (each band's level at its MIDS age, log-linear in log
    age between them, flat after the last) — 1 at age 0."""
    M = _pmon(pre, D)
    k = ("shape", M)
    if k in pre["memo"]:
        return pre["memo"][k]
    pr = _port_ratio(pre, M)
    lv = [0.0] * NB
    for b in range(1, NB):
        lv[b] = lv[b - 1] + math.log(pr[b])
    out = [1.0] * (MAXR + 1)
    for L in range(1, MAXR + 1):
        if L >= MIDS[-1]:
            out[L] = math.exp(lv[-1])
            continue
        j = next(i for i in range(1, NB) if MIDS[i] >= L)
        a0, a1 = MIDS[j - 1], MIDS[j]
        x0, x1, x = math.log(a0 + 1), math.log(a1 + 1), math.log(L + 1)
        out[L] = math.exp(lv[j - 1] + (lv[j] - lv[j - 1]) * (x - x0) / (x1 - x0))
    pre["memo"][k] = out
    return out


def _shape(app, T, hl, R, TG, gc=0):
    """S(L): the portfolio's ARPDAU age shape (its band ratios at TG, the newest GA4 day ≤ T), normalised to a mean of
    1 inside each GA4 band (R weighting)."""
    pre = _pre(app)
    key = ("S", T, hl, gc)
    if key in pre["memo"]:
        return pre["memo"][key]
    S = list(_port_shape(pre, TG))
    for b, (lo, hi) in enumerate(AB):
        hi = min(hi, MAXR)
        sw = sum(R[L] for L in range(lo, hi + 1))
        sv = sum(R[L] * S[L] for L in range(lo, hi + 1))
        m = sv / sw if sw > 0 and sv > 0 else None
        for L in range(lo, hi + 1):
            S[L] = S[L] / m if m else 1.0
    pre["memo"][key] = S
    return S


def _pi(app, X):
    """Install day X's paid share: Google Ads installs ÷ GA4 installs (no Ads row and no spend: 0; spend but no row:
    unknown)."""
    e = app["days"].get(X) or {}
    n = e.get("n") or 0
    if n <= 0:
        return None
    na = e.get("na")
    if na is None:
        return 0.0 if (e.get("sp") or 0) <= 0 else None
    return min(1.0, max(0.0, na / n))


def _nvdata(app):
    """Per install day, per NVB band: (users per install summed over the band's ages, revenue per install) — the final
    daily data (known at T once X + band end ≤ T)."""
    pre = _pre(app)
    if "nv" in pre:
        return pre["nv"]
    out = {}
    for X, c in app["coh"].items():
        n = c.get("n")
        if not n or X < app["start"]:
            continue
        pi = _pi(app, X)
        if pi is None:
            continue
        d, u = c.get("d") or [], c.get("u") or []
        lim = min(len(d), len(u), c.get("df") or 0, c.get("uf") or 0)
        row = []
        for lo, hi in NVB:
            if hi >= lim or any(v is None for v in d[:hi + 1]) or any(v is None for v in u[lo:hi + 1]):
                row.append(None)
                continue
            y = sum(u[lo:hi + 1]) / n
            z = (d[hi] - (d[lo - 1] if lo else 0.0)) / n
            row.append((y, max(0.0, z)))
        out[X] = (n, pi, row)
    pre["nv"] = out
    return out


def _split(app, T, wa):
    """{t: [(users, revenue-per-user ratio ψ vs the band's measured mix) per NVB band]} for organic (0) / paid (1):
    weighted regression of each install day's users / revenue per install in a band on its paid share, over the newest
    NW install days that completed the band by T (slope shrunk by sd(π)² ÷ (sd(π)² + S0_PI²)). "src": "ads" when some
    band's paid shares varied (else None: no slope anywhere, paid = organic by construction — nothing measured)."""
    nv = _nvdata(app)
    res = {0: [None] * len(NVB), 1: [None] * len(NVB)}
    any_vp = False
    for g, (lo, hi) in enumerate(NVB):
        a0 = T - timedelta(days=hi + NW - 1)
        a1 = T - timedelta(days=hi)
        pts = []
        D = a0
        while D <= a1:
            e = nv.get(D)
            if e and e[2][g] is not None:
                n, pi, row = e
                y, z = row[g]
                pts.append((n / (n + NV_N0), pi, y, z))
            D += ONE
        sw = sum(w for w, _, _, _ in pts)
        if len(pts) < 5 or sw <= 0:
            continue
        pm = sum(w * pi for w, pi, _, _ in pts) / sw
        ym = sum(w * y for w, _, y, _ in pts) / sw
        zm = sum(w * z for w, _, _, z in pts) / sw
        vp = sum(w * (pi - pm) ** 2 for w, pi, _, _ in pts) / sw
        if vp > 1e-9:
            any_vp = True
            by = sum(w * (pi - pm) * (y - ym) for w, pi, y, _ in pts) / (sw * vp)
            bz = sum(w * (pi - pm) * (z - zm) for w, pi, _, z in pts) / (sw * vp)
            k = vp / (vp + S0_PI ** 2)
            by, bz = by * k, bz * k
        else:
            by = bz = 0.0

        def yz(t):
            yy = min(20 * ym, max(0.05 * ym, ym + by * (t - pm))) if ym > 0 else 0.0
            zz = min(20 * zm, max(0.05 * zm, zm + bz * (t - pm))) if zm > 0 else 0.0
            return yy, zz
        b = NV2AB[g]                                  # the paid share of the install days that made the band's
        blo, bhi = AB[b]                              # ARPDAU measurement (last wa days)
        q0_ = T - timedelta(days=wa + bhi - 1)
        q1_ = T - timedelta(days=blo)
        qn = qp = 0.0
        D = q0_
        while D <= q1_:
            e = nv.get(D)
            if e:
                qn += e[0]
                qp += e[0] * e[1]
            D += ONE
        pb = qp / qn if qn > 0 else pm
        yb, zb = yz(pb)
        abr = zb / yb if yb > 0 else None
        for t in (0, 1):
            yt, zt = yz(t)
            psi = (zt / yt) / abr if yt > 0 and abr else 1.0
            res[t][g] = (yt, min(10.0, max(0.05, psi)))
    res["src"] = "ads" if any_vp else None
    return res


def _pudays(n, u):
    """User-days per LB band from the users at the LL lags (linear between them; day 0 = the installs; 366–427 flat at
    the 365 users)."""
    pts = [(0, n)] + list(zip(LL, u))
    ix = {g: i for i, (g, _) in enumerate(pts)}
    out = []
    for lo, hi in LB:
        if hi == 0:
            out.append(n)
            continue
        if hi == 427:
            out.append(62.0 * u[-1])
            continue
        top = ix[hi]
        bot = next(i for i, (g, _) in enumerate(pts) if g >= lo - 1)
        out.append(sum(_useg(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(bot, top)))
    return out


def _paid_week(app, W, zz):
    """Install week W's slots {k: [n, n paid, revenue[11], paid revenue[11], user-days[11], paid user-days[11]]} — all
    installs from the legacy cells (to day 90) and c2 (after), the paid ones from cp (LB bands / LL lags); a slot put
    into ZZ for any day of the week's windows (cset_since, xs.since c2 / cp) is folded into ZZ, n with it (dropped
    without a ZZ); the "gap" rows are left out (no installs)."""
    ida = app.get("ida") or {}
    ws = W.isoformat()
    c = (app.get("cty") or {}).get(W) or {}
    c2w = (ida.get("c2") or {}).get(ws) or {}
    cpw = (ida.get("cp") or {}).get(ws) or {}
    cset = ida.get("cset") or []
    lo, hi = W, W + timedelta(days=6 + 427)
    bad = set()
    for cc, rr in (ida.get("cset_since") or {}).items():
        if cc in cset and any(date.fromisoformat(a) <= W + timedelta(days=96) and date.fromisoformat(b) >= W
                              for a, b in rr):
            bad.add(str(cset.index(cc)))
    for key in ("c2", "cp"):
        for k, rr in _xsince(app, key).items():
            if any(a <= hi and b >= lo for a, b in rr):
                bad.add(k)
    raw = {}
    for k in set(c) | set(c2w) | set(cpw):
        if k == "gap":
            continue
        kk = zz if k in bad else k
        if kk is None:
            continue
        x = raw.setdefault(kk, {"n": 0.0, "np": 0.0, "r": [0.0] * 11, "rp": [0.0] * 11, "u": [0.0] * 11,
                                "up": [0.0] * 11})
        e, e2, ep = c.get(k) or {}, c2w.get(k) or {}, cpw.get(k) or {}
        x["n"] += e.get("n") or 0
        x["np"] += ep.get("n") or 0
        for b, v in enumerate((e.get("r") or [0] * 8)[:8]):
            x["r"][b] += v or 0
        for b, v in enumerate((e2.get("r2") or [0] * 3)[:3]):
            x["r"][8 + b] += v or 0
        for j, v in enumerate((e.get("u") or [0] * 7)[:7]):
            x["u"][j] += v or 0
        for j, v in enumerate((e2.get("u2") or [0] * 4)[:4]):
            x["u"][7 + j] += v or 0
        for b, v in enumerate((ep.get("r") or [0] * 11)[:11]):
            x["rp"][b] += v or 0
        for j, v in enumerate((ep.get("u") or [0] * 11)[:11]):
            x["up"][j] += v or 0
    return {k: [x["n"], x["np"], x["r"], x["rp"], _pudays(x["n"], x["u"]), _pudays(x["np"], x["up"])]
            for k, x in raw.items()}


def _p_complete(app, W, b, T):
    """Every activity day of band b's window of week W read for all installs (cst to day 90, c2st after) and for the
    paid ones (cpst), the window ≤ T (the ledgers are cut at the GA4 view)."""
    lo, hi = LB[b]
    end = W + timedelta(days=6 + hi)
    if end > T:
        return False
    if not _cov(_xfold(app, "cpst"), W, end):
        return False
    if not _cov(_folded(app), W, min(end, W + timedelta(days=96))):
        return False
    return hi <= 90 or _cov(_xfold(app, "c2st"), W + timedelta(days=91), end)


def _paid_split(app, T):
    """Per LB band: None, or {"y": (paid, organic) user-days per install, "z": (paid, organic) revenue per install (GA4
    micros), "np", "no", "w"} at the newest paid / organic country mixes (the newest NMIX complete weeks with paid,
    resp. organic, installs) — each (country, paid / organic) cell over the newest NWK complete weeks, shrunk (CKC
    installs) toward its country's all-install standing × the app's measured paid / organic value; a band needs ≥ PMIN
    paid and organic installs. Kept per T in the app (the lag view; with no lags that is the app itself, shared by every
    origin)."""
    memo = app.setdefault("_fvx_psplit", {})
    if T in memo:
        return memo[T]
    ida = app.get("ida") or {}
    cset = ida.get("cset") or []
    zz = str(cset.index("ZZ")) if "ZZ" in cset else None
    weeks = sorted(W for W in (app.get("cty") or {}) if W <= T)
    out = [None] * len(LB)
    cache = {}

    def wk(W):
        if W not in cache:
            cache[W] = _paid_week(app, W, zz)
        return cache[W]
    sp, so, kp, ko = {}, {}, 0, 0
    for W in reversed(weeks):
        if kp >= NMIX and ko >= NMIX:
            break
        if not _p_complete(app, W, 0, T):
            continue
        cells = wk(W)
        hp = sum(x[1] for x in cells.values()) > 0
        ho = sum(max(0.0, x[0] - x[1]) for x in cells.values()) > 0
        for k, x in cells.items():
            if hp and kp < NMIX:
                sp[k] = sp.get(k, 0.0) + x[1]
            if ho and ko < NMIX:
                so[k] = so.get(k, 0.0) + max(0.0, x[0] - x[1])
        kp += 1 if hp else 0
        ko += 1 if ho else 0
    tp, to = sum(sp.values()), sum(so.values())
    if tp <= 0 or to <= 0:
        memo[T] = out
        return out
    sp = {k: v / tp for k, v in sp.items()}
    so = {k: v / to for k, v in so.items()}
    for b in range(len(LB)):
        ws = [W for W in reversed(weeks) if _p_complete(app, W, b, T)][:NWK]
        if not ws:
            continue
        cell = {}
        for W in ws:
            for k, (n, np_, r, rp, ud, udp) in wk(W).items():
                x = cell.setdefault(k, [0.0] * 7)
                x[0] += n
                x[1] += np_
                x[2] += max(0.0, n - np_)
                x[3] += r[b]
                x[4] += min(rp[b], r[b]) if r[b] > 0 else 0.0
                x[5] += ud[b]
                x[6] += min(udp[b], ud[b]) if ud[b] > 0 else 0.0
        Np = sum(x[1] for x in cell.values())
        No = sum(x[2] for x in cell.values())
        if Np < PMIN or No < PMIN:
            continue
        res = {}
        for name, ia, ip in (("z", 3, 4), ("y", 5, 6)):
            N = sum(x[0] for x in cell.values())
            V = sum(x[ia] for x in cell.values()) / N if N > 0 else 0.0
            Vp = sum(x[ip] for x in cell.values()) / Np
            Vo = sum(x[ia] - x[ip] for x in cell.values()) / No
            if V <= 0:
                res = None
                break
            ck = {k: (1.0 + ((x[ia] / x[0]) / V - 1.0) * x[0] / (x[0] + CKC) if x[0] > 0 else 1.0)
                  for k, x in cell.items()}
            vals = []
            for t, (Vt, it, sh) in enumerate(((Vp, 1, sp), (Vo, 2, so))):
                Nt = Np if t == 0 else No
                Ct = sum(x[it] / Nt * ck[k] for k, x in cell.items())
                v = 0.0
                for k, sk in sh.items():
                    pri = Vt * ck.get(k, 1.0) / Ct if Ct > 0 else Vt
                    x = cell.get(k)
                    nt = x[it] if x else 0.0
                    if nt > 0:
                        own = (x[ip] if t == 0 else x[ia] - x[ip]) / nt
                        v += sk * (pri + (own - pri) * nt / (nt + CKC))
                    else:
                        v += sk * pri
                vals.append(v)
            res[name] = tuple(vals)
        if res:
            res.update(np=Np, no=No, w=len(ws))
            out[b] = res
    memo[T] = out
    return out


def _pi_ga4(app, X):
    """Install day X's GA4 paid share of its new users (d2 cpn, the paid read folded) — None when not read."""
    e = ((app.get("ida") or {}).get("d2") or {}).get(X.isoformat())
    if isinstance(e, dict) and e.get("cpst") in QC_FOLDED and isinstance(e.get("cpn"), (int, float)):
        return min(1.0, max(0.0, float(e["cpn"])))
    return None


def _split_cp(app, T, wa):
    """pc: the organic / paid split of new installs MEASURED from GA4's paid cells (cp) instead of regressed on the
    Google Ads install share: each NVB band keeps the newest install days' measured level (the same weighted means as
    _split) and splits it by the cells' paid / organic user-days and revenue per install (_paid_split: every country's
    own, at the newest paid / organic country mix), at GA4's paid share of those install days. Past 30, each type's
    standing moves with the bands 31–60 … 366–427 the cells have complete ("ext"; else carried). None (→ _split)
    unless the cells cover day 30 and GA4's paid share covers ≥ PIG_COV of every window."""
    ps = _paid_split(app, T)
    if ps[5] is None:
        return None
    nv = _nvdata(app)
    res = {0: [None] * len(NVB), 1: [None] * len(NVB)}

    def mixed(v, pi):
        return pi * v[0] + (1.0 - pi) * v[1]
    pm5 = None
    for g, (lo, hi) in enumerate(NVB):
        a0 = T - timedelta(days=hi + NW - 1)
        a1 = T - timedelta(days=hi)
        pts = []
        D = a0
        while D <= a1:
            e = nv.get(D)
            if e and e[2][g] is not None:
                n, _, row = e
                y, z = row[g]
                pts.append((n / (n + NV_N0), _pi_ga4(app, D), y, z))
            D += ONE
        sw = sum(w for w, _, _, _ in pts)
        if len(pts) < 5 or sw <= 0:
            return None
        kw = sum(w for w, pi, _, _ in pts if pi is not None)
        if kw < PIG_COV * sw:
            return None
        pm = sum(w * pi for w, pi, _, _ in pts if pi is not None) / kw
        ym = sum(w * y for w, _, y, _ in pts) / sw
        zm = sum(w * z for w, _, _, z in pts) / sw
        c = ps[g]
        if c is None:
            return None
        cy = c["y"] if g else (1.0, 1.0)
        cz = c["z"]

        def yz(t, pi, cy=cy, cz=cz, ym=ym, zm=zm):
            yy = ym * cy[1 - t] / mixed(cy, pi) if mixed(cy, pi) > 0 else ym
            zz = zm * cz[1 - t] / mixed(cz, pi) if mixed(cz, pi) > 0 else zm
            yy = min(20 * ym, max(0.05 * ym, yy)) if ym > 0 else 0.0
            zz = min(20 * zm, max(0.05 * zm, zz)) if zm > 0 else 0.0
            return yy, zz
        b = NV2AB[g]                                  # the GA4 paid share of the install days that made the band's
        blo, bhi = AB[b]                              # ARPDAU measurement (last wa days)
        q0_ = T - timedelta(days=wa + bhi - 1)
        q1_ = T - timedelta(days=blo)
        qn = qp = 0.0
        D = q0_
        while D <= q1_:
            e = nv.get(D)
            pg = _pi_ga4(app, D)
            if e and pg is not None:
                qn += e[0]
                qp += e[0] * pg
            D += ONE
        pb = qp / qn if qn > 0 else pm
        y0, z0 = yz(0, pm)
        y1, z1 = yz(1, pm)
        yb, zb = pb * y1 + (1 - pb) * y0, pb * z1 + (1 - pb) * z0   # the ARPDAU of the measurement window's mix
        abr = zb / yb if yb > 0 else None
        for t in (0, 1):
            yt, zt = yz(t, pm)
            psi = (zt / yt) / abr if yt > 0 and abr else 1.0
            res[t][g] = (yt, min(10.0, max(0.05, psi)))
        if g == 5:
            pm5 = pm
    ext = {0: [], 1: []}                              # past 30: (users ×, ARPDAU ×) per LB band 6 … 10 vs band 5
    c5 = ps[5]
    for t in (0, 1):
        y5 = c5["y"][1 - t] / mixed(c5["y"], pm5)
        a5 = (c5["z"][1 - t] / mixed(c5["z"], pm5)) / y5 if y5 > 0 else 1.0
        last = (1.0, 1.0)
        for b in range(6, len(LB)):
            c = ps[b]
            if c is not None and mixed(c["y"], pm5) > 0 and mixed(c["z"], pm5) > 0 and y5 > 0 and a5 > 0:
                yb_ = c["y"][1 - t] / mixed(c["y"], pm5)
                ab_ = (c["z"][1 - t] / mixed(c["z"], pm5)) / yb_ if yb_ > 0 else None
                if ab_:
                    last = (min(20.0, max(0.05, yb_ / y5)), min(10.0, max(0.1, ab_ / a5)))
            ext[t].append(last)
    res["ext"] = ext
    res["src"] = "cp"
    res["prem"] = [(c["z"][0] / c["z"][1]) if c and c["z"][1] > 0 else None for c in ps]
    return res


def _b_prepare(app, T, p, ctx):
    """View B at T (app = the lag view): R, S, the band ARPDAU now, each tracked install day's users anchor (su), GA4's
    users re-anchor (zu), the residual users > 427 (q0, ρ), the mean factors m̄ that keep each band's measured total,
    and the organic / paid split of new installs."""
    pre = _pre(app)
    coh, days = app["coh"], app["days"]
    hl, Ku, bw, wa = p["bhl"], p["Ku"], p["bw"], p["wa"]
    gc = p.get("gc") or 0
    fx, fnew = _bmix(app, T, hl, gc)
    TG = max((D for D in pre["have"] if D <= T), default=T)   # every GA4 window ends at the newest GA4 day ≤ T
    R = _retention(app, T, hl, gc)
    S = _shape(app, T, hl, R, TG, gc)
    awa, swa = _arp_win(pre, TG, wa)                  # band ARPDAU now: the last wa days × the calendar index
    cal = 1.0
    if bw:
        aw, _ = _arp_win(pre, TG, bw)
        ok = [b for b in range(NB) if aw[b] is not None and awa[b] is not None]
        num = sum(aw[b] * swa["ab"][b] for b in ok)
        den = sum(awa[b] * swa["ab"][b] for b in ok)
        if den > 0 and num > 0 and sum(swa["ab"][b] for b in ok) >= K0:
            cal = num / den
    arpT = [a * cal if a is not None else None for a in awa]
    prr = _port_ratio(pre, _pmon(pre, TG))
    for b in range(NB):                               # a band nobody reached yet: the one before × the ratio
        if arpT[b] is None and b and arpT[b - 1] is not None:
            arpT[b] = arpT[b - 1] * prr[b]
    if arpT[0] is None:
        arpT = [0.0] * NB
    blk = sorted(X for X, co in coh.items() if co.get("n") and X <= T)
    info = {}
    for X in blk:
        co = coh[X]
        n = co["n"]
        f = _bwk(fx, X)
        uk = F._uknown(co, X, T)
        kl = sorted(L for L in uk if L >= 1 and uk[L] is not None)[-3:]
        su = 1.0
        if kl:
            obs = sum(uk[L] for L in kl)
            exp = sum(n * R[L] * _bfu(f, L) for L in kl)
            if exp > 0:
                su = 1.0 + (obs / exp - 1.0) * exp / (exp + Ku)
                su = min(10.0, max(0.1, su))
        info[X] = {"n": n, "f": f, "uk": uk, "su": su, "zu": 1.0, "sa": 1.0, "age": (T - X).days}

    def U(x, L):
        return x["n"] * x["su"] * x["zu"] * R[min(L, MAXR)] * _bfu(x["f"], L)

    def band_users(D0, D1, bands=None):
        mod = [0.0] * NB
        D = D0
        while D <= D1:
            if D in pre["have"]:
                for X in blk:
                    if X > D:
                        break
                    L = (D - X).days
                    b = BAND[min(L, MAXR)]
                    if bands is None or b in bands:
                        mod[b] += U(info[X], L)
            D += ONE
        return mod
    s7 = _win(pre, TG - timedelta(days=6), TG)        # zu: the ≥ 30 bands re-anchored on GA4's users (last 7 days)
    mod7 = band_users(TG - timedelta(days=6), TG)
    zu = [1.0] * NB
    for b in UBANDS:
        covered = TG - timedelta(days=6 + AB[b][1]) >= pre["first"]
        if covered and mod7[b] > 0 and s7["ab"][b] > 0:
            zu[b] = min(3.0, max(0.33, s7["ab"][b] / mod7[b]))
    if mod7[6] > s7["ab"][6] > 0:                     # the tracked old install days: never above GA4's
        zu[6] = max(0.33, s7["ab"][6] / mod7[6])
    for X in blk:
        info[X]["zu"] = zu[BAND[min(info[X]["age"], MAXR)]]
    q0, rho = 0.0, 0.0                                # residual: users older than 427 no tracked install day explains
    if s7["n"] and s7["ab"][6] > 0:
        q0 = max(0.0, (s7["ab"][6] - mod7[6] * zu[6]) / s7["n"])
        if q0 > 0:
            pts = []
            for k in range(0, 90, 3):
                D = TG - timedelta(days=k)
                if D not in pre["have"]:
                    continue
                m = band_users(D, D, bands=(6,))
                qd = _win(pre, D, D)["ab"][6] - m[6] * zu[6]
                if qd > 0:
                    pts.append((-k, math.log(qd)))
            if len(pts) >= 10:
                mx = sum(x for x, _ in pts) / len(pts)
                my = sum(y for _, y in pts) / len(pts)
                dn = sum((x - mx) ** 2 for x, _ in pts)
                sl = sum((x - mx) * (y - my) for x, y in pts) / dn if dn else 0.0
                rho = min(0.01, max(0.0, -sl))

    def mbar(use_sa):
        """User-weighted mean of S·fa(·sa) per band over the measuring window (the last wa days)."""
        nm, dn = [0.0] * NB, [0.0] * NB
        step = max(4, wa // 14)
        D = TG - timedelta(days=wa - 1)
        while D <= TG:
            if D in pre["have"]:
                for X in blk:
                    if X > D:
                        break
                    L = (D - X).days
                    x = info[X]
                    u = U(x, L)
                    if u <= 0:
                        continue
                    b = BAND[min(L, MAXR)]
                    if b == 6 and not use_sa:
                        continue
                    nm[b] += u * S[min(L, MAXR)] * _bfa(x["f"], L) * (x["sa"] if use_sa else 1.0)
                    dn[b] += u
            D += timedelta(days=step)
        out = [nm[b] / dn[b] if dn[b] > 0 and nm[b] > 0 else 1.0 for b in range(NB)]
        if use_sa and dn[6] > 0:                      # band 6 also holds the residual users (m = 1)
            qq = q0 * len(range(0, wa, step))
            out[6] = (nm[6] + qq) / (dn[6] + qq) if nm[6] > 0 else 1.0
        return out
    mb0 = mbar(False)

    def arp_past(L, D):
        b = BAND[min(L, MAXR)]
        v = _arp7(pre, D)[b]
        return arpT[b] if v is None else v

    for X in blk:                                     # sa: each install day's own revenue per active user (KA: ~off)
        x = info[X]
        if x["age"] > 400:
            continue
        kn = F._known(coh[X], X, T)
        if not kn:
            continue
        K, cK = kn[-1]
        kd = dict(kn)
        if K <= 30:
            k0 = max(-1, K - 7)
            while k0 >= 0 and k0 not in kd:
                k0 -= 1
        else:
            k0 = kn[-2][0] if len(kn) >= 2 else -1
        obs = cK - (kd[k0] if k0 >= 0 else 0.0)
        mod = ud = 0.0
        for L in range(k0 + 1, K + 1):
            u = x["uk"].get(L)
            if u is None:
                u = U(x, L)
            a = arp_past(L, X + timedelta(days=L))
            if not a:
                continue
            mod += u * a * S[L] * _bfa(x["f"], L) / mb0[BAND[L]]
            ud += u
        if mod > 0 and obs >= 0:
            sa = 1.0 + (obs / mod - 1.0) * ud / (ud + KA)
            x["sa"] = min(5.0, max(0.2, sa))
    mb = mbar(True)
    org, per_usd = F.installs_model(days, T, p["W"])
    split = None
    if p["nv"] and p.get("pc"):
        split = _split_cp(app, T, wa)
    if p["nv"] and split is None:
        split = _split(app, T, wa)
    seas = (ctx or {}).get("seas") or {m: 1.0 for m in range(1, 13)}
    s0 = seas.get(T.month, 1.0) or 1.0
    return {"TG": TG, "split": split, "T": T, "p": p, "R": R, "S": S, "fx": fx, "fnew": fnew, "arpT": arpT, "mb": mb,
            "info": info, "blk": blk, "q0": q0, "rho": rho, "org": org, "per_usd": per_usd, "seas": seas, "s0": s0,
            "vec": {}, "pre": pre, "zu": zu, "cal": cal, "ok": bool(pre["have"]) and any(x > 0 for x in arpT)}


def _b_state(v, T, p, ctx):
    """View B's state, kept per (T, its settings) inside the view (tuning the mix weights reuses it)."""
    memo = v.setdefault("_fvb_st", {})
    k = (T, p["bhl"], p["Ku"], p["bw"], p["wa"], p["nv"], p["g"], p["W"], p.get("gc") or 0, p.get("pc") or 0)
    if k not in memo:
        memo[k] = _b_prepare(v, T, p, ctx)
    return memo[k]


def _gb(st, D):
    if D <= st["T"] or not st["s0"]:
        return 1.0
    return (st["seas"].get(D.month, 1.0) / st["s0"]) ** st["p"]["g"]


def _vec(st, f, upto):
    """Per age 0..upto: (users per install unit, revenue per install unit at today's ARPDAU) for a week factor f."""
    key = id(f) if f is not None else None
    v = st["vec"].get(key)
    if v is None or len(v[0]) <= upto:
        R, S, arpT, mb = st["R"], st["S"], st["arpT"], st["mb"]
        top = min(MAXR, max(upto, 640))
        vu = [R[L] * _bfu(f, L) for L in range(top + 1)]
        vr = [vu[L] * S[L] * _bfa(f, L) * arpT[BAND[L]] / mb[BAND[L]] for L in range(top + 1)]
        v = (vu, vr)
        st["vec"][key] = v
    return v


def _newvec(st, t=None):
    """A new install's (users, revenue) per age 0..399: t 0 / 1 = organic / paid (the newest install days' own measured
    split; a band it could not measure keeps the pooled curve); without the split every install alike (pooled curve ×
    the newest mix)."""
    key = ("new", t if st["split"] else None)
    v = st["vec"].get(key)
    if v is None:
        R, S, arpT, mb, f = st["R"], st["S"], st["arpT"], st["mb"], st["fnew"]
        if st["split"] and t is not None:
            sp = st["split"][t]
            vu = [0.0] * 400
            psi = [1.0] * 400
            for g, (lo, hi) in enumerate(NVB):
                rs = sum(R[lo:hi + 1])
                for L in range(lo, hi + 1):
                    if sp[g] and rs > 0:
                        vu[L] = sp[g][0] * R[L] / rs
                        psi[L] = sp[g][1]
                    else:
                        vu[L] = R[L]
            ext = st["split"].get("ext")
            for L in range(31, 400):
                vu[L] = vu[30] * R[L] / R[30] if R[30] > 0 else R[L]
                psi[L] = psi[30]
                if ext:                                   # pc: each type's measured standing past 30
                    ym_, am_ = ext[t][LBX[L] - 6]
                    vu[L] *= ym_
                    psi[L] *= am_
            vr = [vu[L] * S[L] * psi[L] * arpT[BAND[L]] / mb[BAND[L]] for L in range(400)]
        else:
            vu = [R[L] * _bfu(f, L) for L in range(400)]
            vr = [vu[L] * S[L] * _bfa(f, L) * arpT[BAND[L]] / mb[BAND[L]] for L in range(400)]
        v = (vu, vr)
        st["vec"][key] = v
    return v


def _b_parts(st, spend, h, org, per_usd, up=None):
    """View B per future day (as _a_parts; up: the paid installs per day the users / installs follow)."""
    T = st["T"]
    rows = []
    for X in st["blk"]:
        x = st["info"][X]
        top = min(MAXR, x["age"] + h)
        vu, vr = _vec(st, x["f"], top)
        cu = x["n"] * x["su"] * x["zu"]
        rows.append((x["age"], cu, cu * x["sa"], vu, vr, top))
    ovu, ovr = _newvec(st, 0)
    pvu, pvr = _newvec(st, 1)
    a6 = st["arpT"][6] / st["mb"][6]
    ro, rg, rp, uo, ug, upd, nn, fut, futu = [], [], [], [], [], [], [], [], []
    for i in range(1, h + 1):
        D = T + timedelta(days=i)
        g = _gb(st, D)
        r = u = 0.0
        for age, cu, cr, vu, vr, top in rows:
            L = age + i
            if L <= top:
                u += cu * vu[L]
                r += cr * vr[L]
        n_p = per_usd * (spend.get(D, 0.0) if spend else 0.0)
        nu = n_p if up is None else up[i - 1]
        fut.append(n_p)
        futu.append(nu)
        r_o = r_p = u_o = u_p = 0.0
        for j, npj in enumerate(fut):
            L = i - 1 - j
            u_o += org * ovu[L]
            u_p += futu[j] * pvu[L]
            r_o += org * ovr[L]
            r_p += npj * pvr[L]
        q = st["q0"] * math.exp(-st["rho"] * i)
        ro.append((r + q * a6) * g)
        rg.append(r_o * g)
        rp.append(r_p * g)
        uo.append(u + q)
        ug.append(u_o)
        upd.append(u_p)
        nn.append(org + nu)
    return {"old": ro, "org": rg, "paid": rp, "uold": uo, "uorg": ug, "upaid": upd, "n": nn}


def _arp_at(st, L, D):
    """ARPDAU (band level × S ÷ m̄) at age L on day D (a past day: its measured trailing 7 days)."""
    L = min(L, MAXR)
    b = BAND[L]
    if D <= st["T"]:
        a = _arp7(st["pre"], D)[b]
        if a is None:
            a = st["arpT"][b]
        return a * st["S"][L] / st["mb"][b]
    return st["arpT"][b] * st["S"][L] / st["mb"][b] * _gb(st, D)


def _b_cohort_rev(st, X, k_age, ages):
    x = st["info"].get(X)
    if x is None:
        return [0.0] * len(ages)
    cu = x["n"] * x["su"] * x["zu"] * x["sa"]
    R = st["R"]
    out, acc, L = [], 0.0, k_age
    for C in ages:
        while L < C:
            L += 1
            if L <= MAXR:
                acc += cu * R[L] * _bfu(x["f"], L) * _bfa(x["f"], L) * _arp_at(st, L, X + timedelta(days=L))
        out.append(acc)
    return out


def _b_cohort_users(st, X, lags):
    x = st["info"].get(X)
    if x is None:
        return None
    cu = x["n"] * x["su"] * x["zu"]
    return [cu * st["R"][min(Lg, MAXR)] * _bfu(x["f"], Lg) for Lg in lags]


def _b_new_value(st, X, ages, spend, org, per_usd):
    """Per install made on X: the organic / paid values mixed by the model's own installs that day."""
    _, ovr = _newvec(st, 0)
    _, pvr = _newvec(st, 1)
    npd = per_usd * (spend or {}).get(X, 0.0)
    qp = npd / (org + npd) if org + npd > 0 else 0.0
    nvr = [(1 - qp) * a + qp * b for a, b in zip(ovr, pvr)]
    out, acc, L = [], 0.0, -1
    for C in ages:
        while L < C:
            L += 1
            if L < len(nvr):
                acc += nvr[L] * _gb(st, X + timedelta(days=L))
        out.append(acc)
    return out


def past_model(st, D):
    """View B's formula on a past day D (TG < D ≤ T: AdMob known, GA4 not yet) — what its levels say about that day."""
    tot = 0.0
    for X in st["blk"]:
        if X > D:
            break
        x = st["info"][X]
        L = min((D - X).days, MAXR)
        vu, vr = _vec(st, x["f"], L)
        tot += x["n"] * x["su"] * x["zu"] * x["sa"] * vr[L]
    return tot + st["q0"] * st["arpT"][6] / st["mb"][6]


# ══ the two views together ═════════════════════════════════════════════════════════════════════════════════════════
# ══ spend → installs by country (ROI_DRIVERS §5 module A; lab 8) ════════════════════════════════════════════════════
# The paid installs of a future day D (the organic ones stay the engine's own; the REVENUE stays on spend × per_usd ×
# the engine's value — measured: country revenue per $ did not beat it out of sample, while installs and users did):
#     paid(D) = per_usd · Σ_k s_k(D) · ρ_k · (lev_k ÷ s̄_k)^(−e)
#   s_k(D)   country k's spend that day: the day's total × that week's Google Ads country shares (a back-test: the
#            real ones; a week past the country data: the newest week's), or a plan's own spend per country
#   ρ_k      k's Google Ads downloads per $ over the newest CS_N complete country weeks ≤ T (shrunk toward the app's by
#            CS_KD downloads) ÷ that mix's own — 1 at today's mix, so per_usd (the engine's) keeps the level
#   s̄_k      k's average daily spend in those weeks; lev_k its average daily spend in D's week (inside the horizon)
#   e        CPI ∝ spend^e: ONE e for raises and cuts (raises / cuts apart measured worse), pooled over every Google
#            Ads store's country 4-week block pairs known at T (weighted, through the origin, clipped 0 – CS_EMAX)
# An app or origin without its CS_N complete weeks (no spend, a stale cache) keeps per_usd × spend.
CS_N = 2
CS_KD = 50.0
CS_EMIN = (80.0, 120.0)        # a block pair counts with ≥ 80 USD and ≥ 120 downloads in both blocks
CS_EMAX = 0.5
CS_TOP = 8                     # the planner's rows: the top countries with their own GA4 slot + "OT" (every other one)
CS_MIN = 5.0                   # … only for an app spending ≥ this USD a day (the ROI section's judged-day MIN_SPEND)


def cs_pairs(stores, till):
    """Every Google Ads store's country 4-week block pairs, each store on its own: stores {store id: {Monday: {cc:
    [USD, downloads or None]}}}, weeks ending ≤ till → {"rows": [(known from, dlog spend, dlog CPI, weight)] by date,
    prefix sums, "memo"}: the input of cs_e (one per build)."""
    rows = []
    for sid in sorted(stores):
        geo = stores[sid] or {}
        weeks = sorted(W for W in geo if W + timedelta(days=6) <= till)
        bl = {}
        for i in range(len(weeks) - 3):
            blk = weeks[i:i + 4]
            if (blk[-1] - blk[0]).days != 21:
                continue
            b = {}
            for W in blk:
                for cc, (c, d) in geo[W].items():
                    if cc == "XX" or d is None:
                        continue
                    v = b.setdefault(cc, [0.0, 0.0])
                    v[0] += c
                    v[1] += d
            bl[blk[0]] = b
        for W0, prev in bl.items():
            nxt = bl.get(W0 + timedelta(days=28))
            if not nxt:
                continue
            for cc, (c1, d1) in nxt.items():
                p = prev.get(cc)
                if not p or p[0] < CS_EMIN[0] or p[1] < CS_EMIN[1] or c1 < CS_EMIN[0] or d1 < CS_EMIN[1]:
                    continue
                rows.append((W0 + timedelta(days=55), math.log(c1 / p[0]), math.log((c1 / d1) / (p[0] / p[1])),
                             1.0 / (1.0 / d1 + 1.0 / p[1])))
    rows.sort(key=lambda r: r[0])
    kn, sxy, sxx = [], [0.0], [0.0]
    for k, x, y, w in rows:
        kn.append(k)
        sxy.append(sxy[-1] + w * x * y)
        sxx.append(sxx[-1] + w * x * x)
    return {"known": kn, "sxy": sxy, "sxx": sxx, "memo": {}}


def cs_e(pairs, T):
    """(e, pairs used) known at T: the weighted slope of dlog CPI on dlog spend through the origin over the pairs whose
    later block ended ≤ T (≥ 8 of them; else 0), clipped 0 – CS_EMAX."""
    if not pairs:
        return 0.0, 0
    memo = pairs["memo"]
    if T not in memo:
        n = bisect.bisect_right(pairs["known"], T)
        e = 0.0
        if n >= 8 and pairs["sxx"][n] > 0:
            e = min(CS_EMAX, max(0.0, pairs["sxy"][n] / pairs["sxx"][n]))
        memo[T] = (e, n)
    return memo[T]


def cs_model(geo, T):
    """The newest CS_N complete country weeks ≤ T (consecutive, the newest ending ≥ T − 13 days, every downloads count
    known) → {ppu, rho, sbar, share, dl, pa, weeks} or None."""
    weeks = [W for W in sorted(geo or {}) if W + timedelta(days=6) <= T][-CS_N:]
    if len(weeks) < CS_N or (weeks[-1] - weeks[0]).days != 7 * (CS_N - 1) or weeks[-1] + timedelta(days=13) < T:
        return None
    C, D = {}, {}
    for W in weeks:
        for cc, (c, d) in geo[W].items():
            if d is None:
                return None
            C[cc] = C.get(cc, 0.0) + c
            D[cc] = D.get(cc, 0.0) + d
    tc, td = sum(C.values()), sum(D.values())
    if tc <= 0 or td <= 0:
        return None
    pa = td / tc
    ppu = {k: (D.get(k, 0.0) + CS_KD) / (C[k] + CS_KD / pa) for k in C if C[k] > 0}
    mix = sum(C[k] / tc * ppu[k] for k in ppu)
    return {"ppu": ppu, "pa": pa, "rho": {k: v / mix for k, v in ppu.items()},
            "sbar": {k: C[k] / (7.0 * CS_N) for k in C}, "share": {k: C[k] / tc for k in C}, "dl": D, "weeks": weeks}


def _cs_state(app, T):
    """The app's country model at T (kept per T), or None."""
    geo = app.get("geo")
    if not geo:
        return None
    memo = app.setdefault("_fv_cs", {})
    if T not in memo:
        cm = cs_model(geo, T)
        st = None
        if cm is not None:
            e, n = cs_e(app.get("cs_pairs"), T)
            st = {"cm": cm, "e": e, "en": n, "geo": geo, "last_w": max(geo), "T": T}
        memo[T] = st
    return memo[T]


def _cs_shares(cs, W):
    e = cs["geo"].get(W) or cs["geo"].get(cs["last_w"])
    tc = sum(x for x, _ in e.values()) if e else 0
    return {k: x / tc for k, (x, _) in e.items()} if tc > 0 else {}


def _cs_paid(cs, T, spend, h, per_usd, plan=None):
    """Paid installs per future day (the module's formula); plan {cc: USD a day} — the same spend every day."""
    cm, e = cs["cm"], cs["e"]
    rho, sbar = cm["rho"], cm["sbar"]

    def g(k, lev):
        sb = sbar.get(k, 0.0)
        return (lev / sb) ** (-e) if e and sb > 0 and lev > 0 else 1.0
    if plan is not None:
        v = per_usd * sum(s * rho.get(k, 1.0) * g(k, s) for k, s in plan.items() if s > 0)
        return [v] * h
    sp = [spend.get(T + timedelta(days=i), 0.0) for i in range(1, h + 1)]
    wk = {}
    for i in range(h):
        W = T + timedelta(days=i + 1)
        W -= timedelta(days=W.weekday())
        a = wk.setdefault(W, [0.0, 0])
        a[0] += sp[i]
        a[1] += 1
    fac = {}
    for W, (tot, k) in wk.items():
        m = tot / k
        sh = _cs_shares(cs, W)
        fac[W] = sum(q * rho.get(cc, 1.0) * g(cc, m * q) for cc, q in sh.items() if q > 0) if m > 0 else 0.0
    out = []
    for i in range(h):
        W = T + timedelta(days=i + 1)
        W -= timedelta(days=W.weekday())
        out.append(per_usd * sp[i] * fac[W] if sp[i] > 0 else 0.0)
    return out


def _cs_fac_a(comp, slot):
    """View A's (revenue bands, users lags) factors of a {slot: installs} mix — mix_fixed's own fac()."""
    mr, mu, nb, nl = slot
    tot = sum(v for v in comp.values() if v > 0)
    if tot <= 0:
        return None
    rf, uf = [0.0] * nb, [0.0] * nl
    for k, v in comp.items():
        if v <= 0:
            continue
        q = v / tot
        r, u = mr.get(k), mu.get(k)
        for b in range(nb):
            rf[b] += q * (r[b] if r else 1.0)
        for j in range(nl):
            uf[j] += q * (u[j] if u else 1.0)
    return [max(0.05, x) for x in rf], [max(0.05, x) for x in uf]


def _cs_fac_b(comp, slot):
    """View B's (users, ARPDAU) factors of a {slot: installs} mix — _bmix's own fac()."""
    mu, ma, lagb, nb, nl = slot
    tot = sum(v for v in comp.values() if v > 0)
    if tot <= 0:
        return None
    fu = [0.0] * nl
    fan, fad = [0.0] * nb, [0.0] * nb
    for k, v in comp.items():
        q = v / tot
        if q <= 0:
            continue
        uu, aa = mu.get(k), ma.get(k)
        for j in range(nl):
            fu[j] += q * (uu[j] if uu else 1.0)
        for b in range(nb):
            uw = q * ((uu[lagb[b]] if uu else 1.0) if lagb[b] is not None else 1.0)
            fan[b] += uw * (aa[b] if aa else 1.0)
            fad[b] += uw
    fa = [max(0.05, fan[b] / fad[b]) if fad[b] > 0 else 1.0 for b in range(nb)]
    return [max(0.05, x) for x in fu], fa


CS_H = (30, 90, 180)


def cs_plan(app, st, org, per_usd, base, plan):
    """The "Budget by country" planner's inputs at the live origin (the default plan = today's spend × the training
    weeks' shares; an app spending < CS_MIN a day: none): per row (the top CS_TOP countries by spend that have their own
    GA4 slot — a country without one has no curve of its own, so it is planned only inside "OT" = every other country,
    on the pooled curve) its spend a day s0, the
    training weeks' s̄, ρ (installs per $ = per_usd × ρ at s̄), whether it has its own GA4 slot, the weekly spend range
    measured (lo / hi, USD a day) and w = its share of the paid installs' revenue within 30 / 90 / 180 days at the
    default plan — each country on its OWN curves (view A's revenue factors / view B's users × ARPDAU factors, relative
    to the training weeks' paid mix, both views mixed by bn); forecast_build turns w into revenue per $. None without
    the country model."""
    cs = st.get("cs")
    if not cs or not plan or base < CS_MIN:
        return None
    T, p, cm = st["T"], st["p"], cs["cm"]
    rho, sbar = cm["rho"], cm["sbar"]
    cset = (app.get("ida") or {}).get("cset") or []
    ix = {cc: str(i) for i, cc in enumerate(cset)}
    zz = ix.get("ZZ")
    slot_of = lambda cc: ix.get(cc, zz)  # noqa: E731
    order = sorted((k for k, v in plan.items() if v > 0), key=lambda k: (-plan[k], k))
    top = [k for k in order if k not in ("XX", "ZZ") and k in ix][:CS_TOP]
    rest = [k for k in order if k not in top]
    groups = [(k, [k]) for k in top] + ([("OT", rest)] if rest else [])
    v = lag_view(app, T, app.get("glag") or 0)
    gc = p.get("gc") or 0
    sA = (v.get("_fva_slot") or {}).get((T, p["hl"], gc))
    sB = None
    if st["b"] is not None:
        sB = st["b"]["pre"]["memo"].get(("slot", T, p["bhl"], gc))
    comp0 = {}
    for k, d in cm["dl"].items():
        sk = slot_of(k)
        if sk is not None:
            comp0[sk] = comp0.get(sk, 0.0) + d
    fA0 = _cs_fac_a(comp0, sA) if sA else None
    fB0 = _cs_fac_b(comp0, sB) if sB else None
    sa, sb_ = st["a"], st["b"]
    unit = sa["unit"]
    pvr = _newvec(sb_, 1)[1] if sb_ is not None else None
    bn = p["bn"] if sb_ is not None else 0.0
    H = max(CS_H)

    def value(comp):
        """Revenue within 30 / 90 / 180 days of one paid install a day of this mix (days 1 … H), × q."""
        fa = _cs_fac_a(comp, sA) if (sA and fA0) else None
        fb = _cs_fac_b(comp, sB) if (sB and fB0) else None
        ca = cb = 0.0
        acc_a = acc_b = 0.0
        out = {}
        for i in range(1, H + 1):
            L = i - 1                                  # the newest install day's age on day i; Σ over ages ≤ L
            if bn < 1 and L < len(unit):
                ca += unit[L] * (_xfr(fa, L) / _xfr(fA0, L) if fa else 1.0)
            if bn > 0 and pvr is not None and L < len(pvr):
                cb += pvr[L] * ((_bfu(fb, L) * _bfa(fb, L)) / (_bfu(fB0, L) * _bfa(fB0, L)) if fb else 1.0)
            D = T + timedelta(days=i)
            acc_a += ca * _ga(sa, D)
            if sb_ is not None:
                acc_b += cb * _gb(sb_, D)
            if i in CS_H:
                out[i] = ((1 - bn) * acc_a + bn * acc_b) * st["q"]
        return out
    rows, tot = [], {h: 0.0 for h in CS_H}
    weeks = sorted(W for W in cs["geo"] if W + timedelta(days=6) <= T)
    for name, ks in groups:
        s0 = sum(plan[k] for k in ks)
        sb = sum(sbar.get(k, 0.0) for k in ks)
        r = sum(plan[k] * rho.get(k, 1.0) for k in ks) / s0
        comp = {}
        for k in ks:
            sk = slot_of(k)
            if sk is not None:
                comp[sk] = comp.get(sk, 0.0) + plan[k] * rho.get(k, 1.0)
        val = value(comp) if comp else value(comp0)
        lv = [sum(c for cc, (c, _) in cs["geo"][W].items() if cc in ks) / 7.0 for W in weeks]
        lv = [x for x in lv if x > 0]
        own = 1 if (name != "OT" and name in ix and name != "ZZ") else 0
        rows.append({"cc": name, "own": own, "s0": s0, "sb": sb, "rho": r, "lo": min(lv) if lv else None,
                     "hi": max(lv) if lv else None, "val": val})
        for h in CS_H:
            tot[h] += s0 * r * val[h]
    for x in rows:
        val = x.pop("val")
        x["w"] = [(x["s0"] * x["rho"] * val[h] / tot[h]) if tot[h] > 0 else None for h in CS_H]
    cov = sum(x["s0"] for x in rows if x["own"]) / base
    return {"v": 1, "T": T.isoformat(), "weeks": [W.isoformat() for W in cm["weeks"]], "e": cs["e"], "en": cs["en"],
            "pu": per_usd, "org": org, "s": base, "cov": cov, "rows": rows, "n0": _cs_paid(cs, T, {}, 1, per_usd, plan)[0]}


def _views(app, T, p, ctx=None, clag=0, need_b=True, tlag=0):
    """Both views fitted with ONLY the data known at T (GA4 to T − app["glag"]; clag: install days' final data to
    T − clag; tlag: their checkpoints after day 30 to T − tlag) + the days AdMob has but GA4 not yet as (AdMob, view
    A's model, view B's model or None) → (A state, B state or None, those days). Nothing here depends on the mix weights
    bo / bn / cq (a re-tune of them fits once)."""
    v = lag_view(app, T, app.get("glag") or 0, clag, tlag)
    sa = _a_prepare(v, T, p, ctx)
    sb = None
    if need_b:
        sb = _b_state(v, T, p, ctx)
        if not sb["ok"]:                              # no GA4 ARPDAU measured yet: view A alone
            sb = None
    LV = sa["LV"]
    pmod = LV.get("pmod") or {}
    tail = []
    for d, adm, _ in LV.get("tail") or []:
        m = pmod.get(d)
        if m is None:
            continue
        tail.append((adm, m, past_model(sb, T - timedelta(days=PAST - 1 - d)) if sb is not None else None))
    return sa, sb, tail


def _q(tail, bo):
    """q: AdMob ÷ the mixed old model over the days AdMob has but GA4 not yet (clip 1/3–3), and how many days."""
    q = 1.0
    ta = tm = 0.0
    for adm, m, mb in tail:
        if mb is not None and bo > 0:
            m = (1 - bo) * m + bo * mb
        ta += adm
        tm += m
    if ta > 0 and tm > 0:
        q = min(3.0, max(1 / 3.0, ta / tm))
    return q, len(tail)


def prepare(app, T, p, ctx=None, clag=0, tlag=0):
    """Fit both views with ONLY the data known at T (GA4 to T − app["glag"]; clag: install days' final data to
    T − clag; tlag: their checkpoints after day 30 to T − tlag) → the state the functions below use. p: a full setting
    (params()); ctx: {"seas": the month index}."""
    p = params(p) if any(k not in p for k in STRUCT) or any(k not in p for k in DEFAULT) else p
    sa, sb, tail = _views(app, T, p, ctx, clag, p["bo"] > 0 or p["bn"] > 0, tlag)
    q, nt = _q(tail, p["bo"])
    return {"T": T, "p": p, "a": sa, "b": sb, "q": q ** p["cq"], "qraw": q, "nt": nt, "spend": {},
            "org": sa["org"], "per_usd": sa["per_usd"], "cs": _cs_state(app, T) if p.get("cs") else None}


def _mix(x, y, w):
    if y is None or w <= 0:
        return list(x)
    if w >= 1:
        return list(y)
    return [(1 - w) * a + w * b for a, b in zip(x, y)]


def parts(st, spend, h, org=None, per_usd=None, plan=None):
    """Both views over the next h days, mixed and × q: revenue and users of old users / organic / paid installs, n,
    and "up" the paid installs per day (the country model; None without it). plan: {cc: USD a day} for the country
    model (the live forecast's default: spend × the training weeks' country shares)."""
    p = st["p"]
    org = st["org"] if org is None else org
    per_usd = st["per_usd"] if per_usd is None else per_usd
    st["spend"], st["org_f"], st["per_usd_f"] = spend or {}, org, per_usd
    up = _cs_paid(st["cs"], st["T"], spend or {}, h, per_usd, plan) if st.get("cs") else None
    A = _a_parts(st["a"], spend or {}, h, org, per_usd, up)
    B = _b_parts(st["b"], spend or {}, h, org, per_usd, up) if st["b"] is not None else {}
    bo, bn, q = p["bo"], p["bn"], st["q"]
    out = {"n": A["n"], "up": up}
    for k, w in (("old", bo), ("org", bn), ("paid", bn)):
        out[k] = [x * q for x in _mix(A[k], B.get(k), w)]
        out["u" + k] = _mix(A["u" + k], B.get("u" + k), w)
    return out


def total(st, spend, h):
    """The harness interface: {"rev", "dau", "n"} per future day (spend: {day: USD})."""
    x = parts(st, spend, h)
    return {"rev": [a + b + c for a, b, c in zip(x["old"], x["org"], x["paid"])],
            "dau": [a + b + c for a, b, c in zip(x["uold"], x["uorg"], x["upaid"])], "n": x["n"]}


def cohort_rev(st, X, k_age, ages):
    """Past install day X: its revenue from age k_age + 1 to each age in ages (AdMob USD)."""
    bo = st["p"]["bo"] if st["b"] is not None else 0.0
    xa = _a_cohort_rev(st["a"], X, k_age, ages) if bo < 1 else None
    xb = _b_cohort_rev(st["b"], X, k_age, ages) if bo > 0 else None
    out = xb if xa is None else _mix(xa, xb, bo)
    return [x * st["q"] for x in out]


def cohort_users(st, X, lags):
    bo = st["p"]["bo"] if st["b"] is not None else 0.0
    xa = _a_cohort_users(st["a"], X, lags)
    xb = _b_cohort_users(st["b"], X, lags) if bo > 0 else None
    if xa is None:
        return xb
    if xb is None:
        return xa
    return _mix(xa, xb, bo)


def new_value(st, X, ages):
    """An install made on X (> T): its revenue per install from age 0 to each age in ages."""
    bn = st["p"]["bn"] if st["b"] is not None else 0.0
    xa = _a_new_value(st["a"], X, ages) if bn < 1 else None
    xb = None
    if bn > 0:
        xb = _b_new_value(st["b"], X, ages, st["spend"], st.get("org_f", st["org"]), st.get("per_usd_f", st["per_usd"]))
    out = xb if xa is None else _mix(xa, xb, bn)
    return [x * st["q"] for x in out]


# ── the live forecast (the same contract as forecast.forecast) ──────────────────────────────────────────────────────
def _uninstalls(app, T, spend, h, org, per_usd, up=None):
    """Uninstalls a day by who (forecast.uninstall_curve: old install days, organic, paid installs; up: the paid
    installs per day, else spend × per_usd) — None without the Uninstall store's cells."""
    start, coh = app["start"], app["coh"]
    q = F.uninstall_curve(app, T, start)
    if not q:
        return None
    rest = F.un_rest0(app, T, start, q)
    past = [(X, c["n"]) for X, c in coh.items() if start <= X <= T and c.get("n")]
    NQ = len(q)
    o, g_, p_ = [], [], []
    fut = []
    for i in range(1, h + 1):
        D = T + timedelta(days=i)
        uo = 0.0
        for X, n0 in past:
            age = (D - X).days
            if age < NQ:
                uo += n0 * q[age]
        fut.append((D, org, per_usd * spend.get(D, 0.0) if up is None else up[i - 1]))
        qo = qp = 0.0
        for Fd, no, npd in fut:
            age = (D - Fd).days
            if age < NQ:
                qo += no * q[age]
                qp += npd * q[age]
        o.append(uo + rest)
        g_.append(qo)
        p_.append(qp)
    return {"old": o, "org": g_, "paid": p_}


def _med(v):
    v = sorted(x for x in v if x is not None)
    return v[len(v) // 2] if v else None


AGE_GROUPS = ((0, 6), (7, 29), (30, 89), (90, 179), (180, 100000))


def _grp(age):
    for i, (lo, hi) in enumerate(AGE_GROUPS):
        if lo <= age <= hi:
            return i
    return None


def _late_share(app, st):
    """How much of the next H days' revenue (users) of the past install days, at ages 91–427, rests on GA4's measured
    late country cells (gc) vs the 61–90 standing carried — on view A's split of that revenue by install day and age:
    {"on": the gc level in use (0 off, 2 users, 3 users + revenue), "old": share of the old installs' H-day revenue at
    ages 91–427, "meas" / "umeas": the share of that revenue / those users resting on measured cells (a country's
    credibility n ÷ (n + CKC), chained band to band), "weeks": complete install weeks per late band / lag}. The cells
    are judged as if gc 3 were on (what IS measured), so an app with gc off (or 2) still shows what is ready."""
    sa, p, T = st["a"], st["p"], st["T"]
    v = lag_view(app, T, app.get("glag") or 0)
    info = {}
    mix_fixed(v, T, p["hl"], 3, info)
    mf = info.get("mf") or {}
    a, u = sa["B"]["a"], sa["B"]["u"]
    lev, ulev = sa["LV"]["lev"], sa["LV"]["ulev"]
    tot = late = meas = ulate = umeas = 0.0
    for X, (n, f, sg, ug) in sa["SC"].items():
        age = (T - X).days
        m = mf.get(X - timedelta(days=X.weekday()))
        for i in range(1, H + 1):
            L = age + i
            if L >= len(a):
                break
            r = n * sg * a[L] * _xfr(f, L) * lev[LBIX[L]]
            tot += r
            if 91 <= L <= 427:
                late += r
                us = n * ug * u[L] * _xfu(f, L) * ulev[LBIX[L]]
                ulate += us
                if m:
                    meas += r * m[0][BIXX[L] - NCB]
                    if UIXX[L] >= NCL:
                        umeas += us * m[1][UIXX[L] - NCL]
    return {"on": int(p.get("gc") or 0), "old": late / tot if tot > 0 else None,
            "meas": meas / late if late > 0 else None,
            "umeas": umeas / ulate if ulate > 0 else None, "weeks": info.get("n")}


def _why(app, st, org, per_usd):
    """The parts the page's "why" shows: v0's (mix, mix_on, org, per_usd, curve sums) + each view's measured levels
    (view B's even when its weights are 0 — what it measures, for the "why")."""
    sa, sb, p, T = st["a"], st["b"], st["p"], st["T"]
    if sb is None:
        try:
            sb = _b_state(lag_view(app, T, app.get("glag") or 0), T, p, {"seas": sa["seas"]})
            sb = sb if sb["ok"] else None
        except Exception:                             # only the "why" would miss it: never the forecast
            sb = None
    Bq, LV = sa["B"], sa["LV"]
    a, u, fnew = Bq["a"], Bq["u"], Bq["fnew"]
    a90 = sum(a[:91])
    sx, sux = {}, {}
    for X, (_, _, sg, _) in sa["SC"].items():
        g = _grp((T - X).days)
        if g is not None and X >= app["start"]:
            sx.setdefault(g, []).append(sg)
    out = {"engine": "vd", "struct": STRUCT_VERSION, "bo": p["bo"], "bn": p["bn"], "cq": p["cq"],
           "q": st["q"], "qraw": st["qraw"], "qdays": st["nt"], "glag": app.get("glag") or 0,
           "org": org, "per_usd": per_usd, "mix": (F._cumf(F._cum(a), fnew, 90) / a90) if fnew and a90 > 0 else None,
           "mix_on": bool(fnew), "maxage": Bq["maxage"], "a30": sum(a[:31]), "a90": a90, "a180": sum(a[:181]),
           "u1": u[1] if len(u) > 1 else None, "u7": u[7] if len(u) > 7 else None,
           "lev": list(LV["lev"]), "ulev": list(LV["ulev"]), "lam": list(LV["new"][:4]), "level_mode": LV["mode"],
           "sx": [_med(sx.get(g, [])) for g in range(len(AGE_GROUPS))]}
    g4 = lag_view(app, T, app.get("glag") or 0).get("g4") or {}
    out["TG"] = max(g4).isoformat() if g4 else None
    if sb is not None:
        for X in sb["blk"]:
            g = _grp(sb["info"][X]["age"])
            if g is not None and X >= app["start"]:
                sux.setdefault(g, []).append(sb["info"][X]["su"])
        nv = {}
        for t, name in ((0, "org"), (1, "paid")):
            vu, vr = _newvec(sb, t)
            nv[name] = [sum(vu[:31]), sum(vr[:31])]          # per install: user-days and revenue to day 30 (at T)
        sp = sb.get("split") or {}
        out.update(arp=list(sb["arpT"]), cal=sb["cal"], zu=list(sb["zu"]), Q0=sb["q0"], rho=sb["rho"], nv=nv,
                   su=[_med(sux.get(g, [])) for g in range(len(AGE_GROUPS))],
                   nvsrc=sp.get("src"), pc=bool(p.get("pc")))
    out["tun"] = {k: len(GRID[k]) > 1 for k in ("gc", "pc")}   # the switches a tune may turn on (else held off)
    try:                                              # only the "why" would miss it: never the forecast
        out["gx"] = _late_share(app, st)
    except Exception:
        out["gx"] = None
    return out


def forecast(app, T, p, spend=None, h=H, seas=None):
    """The forecast from origin T with setting p → the same keys as forecast.forecast: {"rev": {old, org, paid}, "dau",
    "dau_p", "un", "n", "sp", "parts"} lists of h days. spend: {day: USD} for the future days (None = today's run-rate:
    the mean of the last SPEND_DAYS days, with THEIR organic installs and cost per install)."""
    p = params(p)
    st = prepare(app, T, p, {"seas": seas})
    days = app["days"]
    org, per_usd = st["org"], st["per_usd"]
    plan = None
    base = None
    if spend is None:
        org, per_usd = F.installs_model(days, T, F.SPEND_DAYS)
        k, tot = 0, 0.0
        D = T - timedelta(days=F.SPEND_DAYS - 1)
        while D <= T:
            e = days.get(D)
            if e:
                k += 1
                tot += e.get("sp") or 0
            D += ONE
        base = tot / k if k else 0.0
        spend = {T + timedelta(days=i): base for i in range(1, h + 1)}
        if st.get("cs"):                              # the country model: today's spend × the training weeks' shares
            plan = {cc: base * q for cc, q in st["cs"]["cm"]["share"].items()}
    x = parts(st, spend, h, org, per_usd, plan)
    un = _uninstalls(app, T, spend, h, org, per_usd, x["up"])
    sp = [spend.get(T + timedelta(days=i), 0.0) for i in range(1, h + 1)]
    out = {"rev": {"old": x["old"], "org": x["org"], "paid": x["paid"]},
           "dau": [a + b + c for a, b, c in zip(x["uold"], x["uorg"], x["upaid"])], "n": x["n"], "sp": sp,
           "dau_p": {"old": x["uold"], "org": x["uorg"], "paid": x["upaid"]}, "un": un,
           "parts": _why(app, st, org, per_usd)}
    if plan is not None:
        try:                                          # only the planner would miss it: never the forecast
            out["plan"] = cs_plan(app, st, org, per_usd, base, plan)
        except Exception:
            out["plan"] = None
    return out


# ── back-testing: totals (as v0) + every past install day's future revenue + new installs' value ────────────────────
CHECK = (7, 14, 30, 60, 90, 180, 365)
ULAG_CHECK = (60, 90, 120, 180, 270, 365)
NEW_AGES = (30, 90, 180)
COMP_W = {"total": 0.4, "coh": 0.3, "new": 0.3}


def _cum_at(c, age):
    """An install day's exact cumulative revenue at `age` if the data has it (daily to 30, the checkpoints), else None."""
    d, df = c.get("d") or [], c.get("df") or 0
    if age < min(len(d), df) and d[age] is not None:
        return d[age]
    t = c.get("t") or []
    if age in F.T_AGES:
        j = F.T_AGES.index(age)
        if j < len(t) and t[j] is not None:
            return t[j]
    return None


def _users_at(c, lag):
    if lag <= 30:
        u, uf = c.get("u") or [], c.get("uf") or 0
        return u[lag] if lag < min(len(u), uf) else None
    ul = c.get("ul") or []
    if lag in F.ULAGS:
        j = F.ULAGS.index(lag)
        return ul[j] if j < len(ul) else None
    return None


CLAG = True    # back-tests: each install day's final daily data only to T − app["clag"] and its checkpoints after day
               # 30 only to T − app["tlag"], as the live build has them (the tournament let them see to T: a little
               # optimistic) — False = the tournament's view (lab parity)


def _origin(app, T, p, seas, need_b, comps=True):
    """One back-test origin: everything that does NOT depend on the mix weights — both views' parts with the spend that
    really happened, each past install day's future revenue / users and each new install's value per view, the actuals
    — or None (no horizon to score). _row() mixes it for any (bo, bn, cq) with the same arithmetic as prepare / parts /
    cohort_rev / cohort_users / new_value, so a back-test from it is the very same numbers."""
    days, last, coh, start = app["days"], app["last"], app["coh"], app["start"]
    hmax = min(H, (last - T).days)
    if hmax < HORIZONS[0]:
        return None
    jumps = app.get("_jumps")
    if jumps is None:
        jumps = app["_jumps"] = {D: e for D in days for e in [F.event(days, D)] if e}
    sp = {T + timedelta(days=i): (days.get(T + timedelta(days=i)) or {}).get("sp") or 0.0 for i in range(1, hmax + 1)}
    sa, sb, tail = _views(app, T, p, {"seas": seas}, (app.get("clag") or 0) if CLAG else 0, need_b,
                          (app.get("tlag") or 0) if CLAG else 0)
    org, per_usd = sa["org"], sa["per_usd"]
    cs = _cs_state(app, T) if p.get("cs") else None       # the paid installs the users / installs follow (country model)
    up = _cs_paid(cs, T, sp, hmax, per_usd) if cs else None
    unm = app.setdefault("_fv_un", {})                    # the uninstalls do not depend on the mix weights either
    if (T, hmax) not in unm:
        unm[(T, hmax)] = _uninstalls(app, T, sp, hmax, org, per_usd, up)
    un = unm[(T, hmax)]
    hz_rows = []
    for hz in HORIZONS:
        if hz > hmax:
            continue
        act = [days.get(T + timedelta(days=i)) or {} for i in range(1, hz + 1)]
        ar = sum(e.get("rev") or 0 for e in act)
        if ar <= 0:
            continue
        an = sum(e.get("n") or 0 for e in act)
        au = sum(e.get("dau") or 0 for e in act)
        ev = None
        for k in range(0, hz - 29, 7):
            ev = jumps.get(T + timedelta(days=k))
            if ev:
                ev = dict(ev, at=(T + timedelta(days=k)).isoformat())
                break
        un_e = None
        if un:
            aun = sum(e.get("un") or 0 for e in act)
            pun = sum(sum(un[k][:hz]) for k in ("old", "org", "paid"))
            if aun > 0 and all(e.get("un") is not None for e in act):
                un_e = pun / aun - 1.0
        hz_rows.append((hz, ar, an, au, ev, un_e))
    if not hz_rows:
        return None
    o = {"T": T, "hz": hz_rows, "tail": tail, "A": _a_parts(sa, sp, hmax, org, per_usd, up),
         "B": _b_parts(sb, sp, hmax, org, per_usd, up) if sb is not None else None, "comps": comps}
    if not comps:
        return o
    crev, cusr, cnew = [], [], []
    for X, c in coh.items():
        if X < start or X > T or not c.get("n"):
            continue
        age = (T - X).days
        g = _grp(age)
        k = F._known(c, X, T)
        if not k:
            continue
        K, ck = k[-1]
        want = [C for C in CHECK if C > K and C > age and X + timedelta(days=C) <= last and _cum_at(c, C) is not None]
        if want:
            crev.append((g, want, _a_cohort_rev(sa, X, K, want),
                         _b_cohort_rev(sb, X, K, want) if sb is not None else None,
                         [_cum_at(c, C) - ck for C in want]))
        uk = F._uknown(c, X, T)
        uk = max(uk) if uk else None
        lw = [Lg for Lg in ULAG_CHECK if (uk is None or Lg > uk) and Lg > age and X + timedelta(days=Lg) <= last
              and _users_at(c, Lg) is not None]
        if lw:
            cusr.append((g, lw, _a_cohort_users(sa, X, lw), _b_cohort_users(sb, X, lw) if sb is not None else None,
                         [_users_at(c, Lg) for Lg in lw]))
    for i in range(1, 31):
        X = T + timedelta(days=i)
        c = coh.get(X)
        if not c or not c.get("n"):
            continue
        want = [C for C in NEW_AGES if X + timedelta(days=C) <= last and _cum_at(c, C) is not None]
        if want:
            cnew.append((want, _a_new_value(sa, X, want),
                         _b_new_value(sb, X, want, sp, org, per_usd) if sb is not None else None,
                         c["n"], [_cum_at(c, C) for C in want]))
    o.update(crev=crev, cusr=cusr, cnew=cnew)
    return o


def _pick(xa, xb, w):
    """View A's / B's values mixed with B's weight w — cohort_rev / new_value's rule (only the view(s) w needs)."""
    a = xa if w < 1 else None
    b = xb if w > 0 else None
    return b if a is None else _mix(a, b, w)


def _row(o, bo, bn, cq):
    """One origin (_origin) mixed with the weights bo, bn, cq → its back-test row."""
    A, B = o["A"], o["B"]
    q = _q(o["tail"], bo)[0] ** cq
    x = {}
    for k, w in (("old", bo), ("org", bn), ("paid", bn)):
        x[k] = [v * q for v in _mix(A[k], B[k] if B is not None else None, w)]
        x["u" + k] = _mix(A["u" + k], B["u" + k] if B is not None else None, w)
    rev = [a + b + c for a, b, c in zip(x["old"], x["org"], x["paid"])]
    dau = [a + b + c for a, b, c in zip(x["uold"], x["uorg"], x["upaid"])]
    row = {"T": o["T"].isoformat(), "h": {}, "ev": {}}
    for hz, ar, an, au, ev, un_e in o["hz"]:
        pr = sum(rev[:hz])
        pn = sum(A["n"][:hz])
        pu = sum(dau[:hz])
        if ev:
            row["ev"][hz] = ev
        row["h"][hz] = {"pred": pr, "act": ar, "err": pr / ar - 1.0, "un_err": un_e,
                        "n_err": (pn / an - 1.0) if an else None, "dau_err": (pu / au - 1.0) if au else None,
                        "arp_err": ((pr / pu) / (ar / au) - 1.0) if pu and au else None}
    if not o["comps"]:
        return row
    wo = bo if B is not None else 0.0                     # without view B (no GA4 ARPDAU yet): view A alone
    wn = bn if B is not None else 0.0
    coh, usr, new = {}, {}, {}
    for g, want, xa, xb, acts in o["crev"]:
        for C, v, av in zip(want, _pick(xa, xb, wo), acts):
            cell = coh.setdefault((g, C), [0.0, 0.0])
            cell[0] += v * q
            cell[1] += av
    for g, lw, ua, ub, acts in o["cusr"]:
        ub = ub if wo > 0 else None
        pu = ub if ua is None else (ua if ub is None else _mix(ua, ub, wo))
        if pu is not None:
            for Lg, v, av in zip(lw, pu, acts):
                cell = usr.setdefault((g, Lg), [0.0, 0.0])
                cell[0] += v
                cell[1] += av
    for want, na, nb, n, acts in o["cnew"]:
        for C, v, av in zip(want, _pick(na, nb, wn), acts):
            cell = new.setdefault(C, [0.0, 0.0])
            cell[0] += (v * q) * n
            cell[1] += av
    row.update(coh=coh, usr=usr, new=new)
    return row


def backtest(app, p, seas=None, ors=None, comps=True):
    """[{T, h: {30: {pred, act, err, n_err, dau_err, arp_err, un_err}, …}, ev, coh, usr, new}] — every origin's forecast
    with the spend that really happened (GA4 seen to T − glag, as live), vs what happened: totals, past install days'
    future revenue ("coh") and users ("usr") by (age group at T, checkpoint), new installs' value ("new") by age."""
    p = params(p)
    res = []
    for T in (ors if ors is not None else F.origins(app)):
        o = _origin(app, T, p, seas, p["bo"] > 0 or p["bn"] > 0, comps)
        if o is not None:
            res.append(_row(o, p["bo"], p["bn"], p["cq"]))
    return res


def objective(bt):
    """The tuning objective: weighted mean |error| of the totals (horizons by HW, sudden-change tests × EV_W, newer tests
    weigh more) 0.4 + past install days' future revenue by age group 0.3 + new installs' value 0.3."""
    n = len(bt)
    acc = {"total": [0.0, 0.0], "coh": [0.0, 0.0], "new": [0.0, 0.0]}
    for i, r in enumerate(bt):
        rw = 0.5 + 0.5 * (i + 1) / n
        ev = r.get("ev") or {}
        for hz, x in r["h"].items():
            if not x["act"] > 0:
                continue
            w = F.HW[hz] * rw * (F.EV_W if hz in ev else 1.0)
            acc["total"][0] += w * abs(x["pred"] / x["act"] - 1.0)
            acc["total"][1] += w
        for (g, C), (pv, av) in (r.get("coh") or {}).items():
            if not av > 0 or av < 1.0:
                continue
            w = rw * min(1.0, av / 50.0)
            acc["coh"][0] += w * min(abs(pv / av - 1.0), 3.0)
            acc["coh"][1] += w
        for C, (pv, av) in (r.get("new") or {}).items():
            if not av > 0 or av < 1.0:
                continue
            w = rw * (1.0 if C == 30 else 0.6 if C == 90 else 0.4)
            acc["new"][0] += w * min(abs(pv / av - 1.0), 3.0)
            acc["new"][1] += w
    tot = wsum = 0.0
    for k, (s, w) in acc.items():
        if w > 0:
            tot += COMP_W[k] * s / w
            wsum += COMP_W[k]
    return tot / wsum if wsum else None


score = objective


def _moves(app, T, gc, pc):
    """Can the switches change anything at origin T (the back-test's view of the app)? gc: some install week has a
    late c2 cell complete (gc 2: a lag; gc 3: a lag or a band); pc: the paid cells give the split (_split_cp). Else the
    fit equals (0, 0)."""
    v = lag_view(app, T, app.get("glag") or 0, (app.get("clag") or 0) if CLAG else 0,
                 (app.get("tlag") or 0) if CLAG else 0)
    if gc:
        fo2 = _xfold(v, "c2st")
        if fo2 is not None and any(
                _cov(fo2, W + timedelta(days=lo), W + timedelta(days=6 + hi)) and W + timedelta(days=6 + hi) <= T
                for W in (v.get("cty") or {}) for lo, hi in ((C2B if gc >= 3 else ()) + tuple((g, g) for g in C2L))):
            return True
    if pc:
        try:
            if _split_cp(v, T, STRUCT["wa"]) is not None:
                return True
        except Exception:
            return True
    return False


def tune(app, seas=None, start_p=None, passes=2):
    """Coordinate descent over GRID (the mix weights and the switches gc / pc; the structure is fixed) from the stored
    setting (a stored value GRID no longer offers starts at its default), on the back-test objective → (best setting,
    its back-test, every step tried). Both views are fitted once per origin and (gc, pc) (_origin; an origin the
    switches can not change reuses the plain fit); each setting tried is then only arithmetic (_row) — the same numbers
    as backtest() with it."""
    ors = F.origins(app)
    p = dict(DEFAULT, **{k: v for k, v in (start_p or {}).items() if k in DEFAULT and v in GRID.get(k, (v,))})
    if not ors:
        return p, [], []
    fitsets = {}

    def fits_of(gc, pc):                              # both views per origin, for one (gc, pc); an origin where the
        k = (gc, pc)                                  # switches can change nothing reuses the (0, 0) fit (identical)
        if k not in fitsets:
            full = params(dict(p, gc=gc, pc=pc))
            if k == (0, 0):
                fitsets[k] = {T: _origin(app, T, full, seas, True) for T in ors}
            else:
                fits_of(0, 0)
                base = fitsets[(0, 0)]
                fitsets[k] = {T: (_origin(app, T, full, seas, True) if _moves(app, T, gc, pc) else base[T])
                              for T in ors}
        return [o for o in fitsets[k].values() if o is not None]

    def run(q):
        key = tuple(sorted(q.items()))
        if key not in cache:
            bt = [_row(o, q["bo"], q["bn"], q["cq"]) for o in fits_of(q["gc"], q["pc"])]
            cache[key] = (objective(bt), bt)
        return cache[key]
    cache = {}
    best, bt = run(p)
    steps = [{"p": dict(p), "score": best}]
    for _ in range(passes):
        changed = False
        for k, vals in GRID.items():
            for v in vals:
                if v == p[k]:
                    continue
                q = dict(p, **{k: v})
                sc, b2 = run(q)
                if sc is not None and (best is None or sc < best - 1e-4):
                    p, best, bt, changed = q, sc, b2, True
                    steps.append({"p": dict(p), "score": sc, "changed": k})
        if not changed:
            break
    return p, bt, steps


# ── the portfolio's band ratios (state.json "bandr", made at the end of a build from every app) ────────────────────
BANDR_DAYS = 1100              # Mondays kept (back-tests reach ~800 days back)


def port_pre(app):
    """What one app gives the portfolio's band ratios: its GA4 prefix sums and GA4 lag ({d0, nd, P, lag}) — None
    without GA4."""
    pre = _pre(app)
    if not pre.get("P"):
        return None
    return {"d0": pre["d0"], "nd": pre["nd"], "P": pre["P"], "lag": max(0, int(app.get("glag") or 0))}


def bandr(pres):
    """{Monday ISO: [7 ratios]}: for each band b ≥ 1 the median over the apps (≥ PORT_UD user-days in both bands over
    the LONG days to that Monday) of arp_b ÷ arp_b−1; fewer than 3 apps: 1; clipped 0.1–2. An app whose GA4 lands later
    than the quickest one's counts its LONG days to Monday − the difference — so a back-test origin T, which looks up
    at most the Monday of T − its own lag (_pmon), sees every app only as far as the live build had it at T."""
    pres = [x for x in pres if x and x.get("P")]
    if not pres:
        return {}
    d0 = min(x["d0"] for x in pres)
    d1 = max(x["d0"] + timedelta(days=x["nd"] - 1) for x in pres)
    lmin = min(x.get("lag") or 0 for x in pres)
    M = _monday(max(d0, d1 - timedelta(days=BANDR_DAYS)))
    if M < d0:
        M += timedelta(days=7)
    out = {}
    while M <= d1 + timedelta(days=7):             # + the Monday after the newest GA4 day (the next build's GA4 day
                                                   # may land on it: its live forecast then reads it, from data ≤ d1)
        rs = [[] for _ in range(NB)]
        for x in pres:
            E = M - timedelta(days=(x.get("lag") or 0) - lmin)
            s = _win(x, E - timedelta(days=LONG - 1), E)
            for b in range(1, NB):
                if s["ab"][b] >= PORT_UD and s["ab"][b - 1] >= PORT_UD and s["rb"][b - 1] > 0:
                    rs[b].append((s["rb"][b] / s["ab"][b]) / (s["rb"][b - 1] / s["ab"][b - 1]))
        r = [1.0] * NB
        for b in range(1, NB):
            v = sorted(rs[b])
            if len(v) >= 3:
                r[b] = min(2.0, max(0.1, v[len(v) // 2]))
        out[M.isoformat()] = r
        M += timedelta(days=7)
    return out
