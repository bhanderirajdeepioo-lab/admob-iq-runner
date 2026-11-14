"""⚖️ Breakeven — the build step of the CPI vs eCPM screen's Breakeven tab (owner, 14 Nov 2026: "har app ka har country
ka alag", "koi assumption pe nahi chalna he, data ke sath hi chalna he", "haan isi tarah banao"; the 14-day card:
"haan ROAS wala rakho"; after it went live: every install day, not the newest 14 ("31 Oct tak hi kyu? baki ke din?"),
and no daily revenue index — his "index" is an eCPM one, the returning-eCPM step). Per app × country a breakeven
benchmark learned only from the app's own past install days — what each day's CPI and first-session eCPM were, and when
(if ever) its installs paid their Google Ads cost back — and for each of the app's judged install days, when that day
breaks even (the page shows the days of its period).

  inputs (read only, one app in memory at a time): this build's roi_<key>.json.gz (through dashboard["roi"] only, never
  a listing of the folder: "rows" = the All row of every install day, "cd" "packs" = the same rows per country, see
  roi_build) and data/ga4_nvr/<key>.json.gz (fetch.ga4_nvr: the first session's "n" revenue and impressions by country
  and day). "--" / "XX" / "ZZ" are no country.

  Words: a JUDGED day has ≥ $5 Google Ads and ≥ 30 GA4 new users; CPI = spend ÷ Google Ads installs; eCPM_fs = the
  install day's first-session revenue ÷ impressions × 1000 (a country: its own rows; the app: every country);
  ROAS(age) = cumulative revenue ÷ spend (floor 0.001 before a log) on the row's daily cells 0 … 30, its 30-day columns
  60, 90 … and a checkpoint past them; BE = the first observed age whose cumulative revenue ≥ spend (past day 30 only
  its 30-day bucket is known: the day inside it on cumulative revenue). No look-ahead at an origin O: a cell of age a
  counts once install day + a + 3 ≤ O (LAG), a day trains a model only once install day + 30 ≤ O (SETTLE: Google Ads
  installs settle). GRID = the ages every curve is read at (the first six = card days 1, 2, 3, 4, 7, 14).

  fit (once a UTC day per app, cached in data/be_tab/fits_<key>.json.gz with its origin; refit when the build's day
  changed): per country its judged days with a CPI and an eCPM_fs — the days whose BE is visible by O are events,
  every other trained day "BE > its age so far" (censored at the largest observed grid age); the bot: a Huber fit of
  log(BE + 1) on log CPI and log eCPM_fs, events with |robust z| > 3 dropped; ≥ 20 kept events = a COVERED country
  (fewer: uncovered, never estimated); the log CPI / log eCPM_fs range of its usable days (a later day outside it is
  not answered: no past day there — never extrapolated). K3: log(BE + 1) = a + b·log CPI + c·log eCPM_fs + σ·ε, right-censored normal
  errors (Schmee–Hahn EM). Its ROAS curve: per GRID age, Huber → bot → Huber of log ROAS(age) on the same inputs over
  the days that reached that age (the kept residuals' 10 / 90 % = its range), up to the first age with < 20 kept days
  (the curve's limit). The app's own median past curve (the median of log ROAS per age) is the card's benchmark.
  calibration (once a UTC day, data/be_tab/calib.json with its date): the same fits at every month start over the
  history (rolling, no look-ahead), every judged install day of that month answered, the truth = what is known now →
  isotonic maps (PAVA) of K3's P(BE ≤ H) to the real share for H = 30 / 90 / 180 (a day old enough to know: age ≥
  H + 3), the Kaplan–Meier of K3's PIT values (the levels of a country's median day
  and 80 % range), the quantiles of the real ÷ predicted app ROAS per age (the app's 80 % band) and per app its skill
  (below). A calibration that fails keeps the last good file (tried again the next UTC day; none yet: every build).
  predict (every build, from the caches only): per install day each covered country whose CPI and eCPM_fs are inside
  its learned range: its curve at them (made non-decreasing in age), weighted by its share of the day's covered spend and summed = the app's ROAS
  curve (a country whose curve stops earlier keeps its last value: a lower bound) — the owner's rule, never an average
  of the countries' BE days — → app BE = where it first reaches 100 % (linear between grid ages), the band and its
  crossings (the page reads ROAS at 30 / 90 / 180 off this same curve: one curve, one answer — a separately
  calibrated P beside it contradicted its BE day); per covered country its calibrated
  K3 P's and days (null past the longest age its data watched, that limit beside it); the uncovered countries as their
  spend share (no benchmark, or a CPI / eCPM_fs outside it: "x % spend: data kam"; the ones under 0.5 % as one "…"
  rest); the card: ROAS so far at days 1, 2, 3, 4,
  7, 14 against the app's median past curve. A day under 4 days old (age < 4)
  is provisional: GA4's country and first-session reads are not final yet, and neither are Google Ads' installs (the
  CPI: installs read at age 0–1 were a median 0.91 of their final count, ≈ 1.00 from age 2; the back-test answers
  with final inputs) — the page marks it. The grid ages a day has lived carry its REAL cumulative ROAS (never the
  model's: an old install day's ROAS at 30 / 90 / 180 is what it made); past them its ROAS so far floors the curve (a
  cumulative ROAS never falls; from its real BE day on it is ≥ 100 %) and caps any unlived age before it; a day that
  already broke even answers its real day (no range); the 80 % range only as far as the band reaches (beyond it: no
  end, never the median line).
  skill (the page's "how sure"), on the app's back-test days (what the tab would have said then, scored on what is
  known now): AUC at 30 / 90 / 180 of the app curve's ROAS(H) against "broke even within H?" (of a day that did and
  one that did not, how often the one that did scored higher; ties ½; ≥ 10 days on each side, else null) — not the
  P ≥ 0.5 yes/no accuracy, which is 50 at 30 days for every app (BE within 30 days is rare, a calibrated P seldom
  reaches 0.5) — and C (the concordance of the app curve's BE day with the real one over every comparable pair; ≥ 10
  days with a real BE, else null); n = the app's answered back-test days.

  site/be_<key>.json.gz  {"v", "key", "origin", "grid", "calib" (its day), "skill": {"auc", "c", "n"}, "days": [{"d",
                          "age", "sp" (USD), "inst" (Google Ads installs), "cov" (covered share of the day's country
                          spend), "real" (the day's REAL ROAS at the grid ages from final cells, whatever its
                          coverage; null where not lived / not final; trailing nulls trimmed — the page shows these as
                          "asli", never the model), "app": {"be": [median, low, high] (days; null = no crossing
                          within "lim"; a day that broke even: [its real day, null, null]), "lim", "roas" / "lo" /
                          "hi" (the curve and its band at the grid ages ≤ lim: real where final, bounded by what it
                          made elsewhere)} (absent: nothing covered), "unc": [[cc, share], …, ["…", rest]], "cty":
                          [[cc, share, CPI, eCPM_fs, P30, P90, P180, median, low, high, lim, rk], …] (rk 1 / 2 / 3:
                          the country broke even — median = its real day: exact / "≤" / not final yet; 0: K3's days
                          given it has not broken even by its own so-far age; 4: ≤ a 30-day column not final yet;
                          5 / 6: it lived past K3's limit without breaking even — median = its so-far age, final /
                          not final yet), "jd" 0 (only on a day under $5 / 30 new users: no model, no countries — its
                          real numbers only), "card": {"roas", "bench"}, "now": ["be", BE day, kind ("x" exact / "nf" not final
                          / "b" ≤ a column / "s" ≤ its so far), so-far age, ROAS so far] (the ROI row's own) | ["no",
                          so-far age, ROAS so far, final? (1: older than LAG days)]}]} (every install day with
                          spend, oldest first)
  dashboard["be"]        {"v", "origin", "calib", "apps": {app id: {"key", "file", "v", "n", "cov"}}}

run(dashboard, data_dir, out_dir, s, now) → HEADER_PATHS (["/be_*"], ONE splat rule) or [] (no app / a failure: the
files removed, no pointer). Never raises; any failure prints "be skipped: <ErrorType>" (the health banner) and one
app's costs only that app (counted). off(out_dir): the switch (BE_TAB=false). ONE counts-only line (pop_line).
"""
import bisect
import gzip
import hashlib
import json
import math
import os
import re
import sys
import zlib
from collections import Counter
from datetime import date, datetime, timezone
from itertools import repeat
from operator import add, mul

from .db import write_gz_stable
from .fetch import ga4_nvr as gv

PREFIX = "be_"
APP_RE = re.compile(r"^be_[0-9a-f]{12}\.json\.gz$")
ROI_RE = re.compile(r"^roi_([0-9a-f]{12})\.json\.gz$")
PACK_RE = re.compile(r"^roi_[0-9a-f]{12}_c\d{2,3}\.json\.gz$")     # (roi_build.PACK_RE: the country packs)
HEADER_PATHS = ["/be_*"]
V = 1
DIR = "be_tab"                       # data/be_tab/: fits_<key>.json.gz + calib.json, each with its day
CALIB = "calib.json"
GRID = (0, 1, 2, 3, 6, 13, 30, 60, 90, 120, 180, 270, 360)
CARD_J = (0, 1, 2, 3, 4, 5)          # GRID indexes of the card days 1, 2, 3, 4, 7, 14 (day k = age k − 1)
T = (0, 1, 3, 7, 14, 30, 60, 90, 180, 365)     # a roi row's t checkpoints
HS = (30, 90, 180)                   # "breaks even within H days?"
MIN_SP, MIN_N = 5.0, 30              # a judged day (the dashboard's own rule)
SETTLE, LAG = 30, 3
MIN_KEPT = 20                        # a covered country: ≥ 20 kept real-BE days; a curve age / median: ≥ 20 days
ZBOT = 3.0                           # the bot: |robust z| > 3 dropped
ROAS_FLOOR = 1e-3
PROV = 4                             # a day under 4 days old is provisional (age < 4)
REST = 0.005                         # uncovered countries under 0.5 % of the day's spend: one "…" entry
REST_CC = "…"
MIN_BAND = 50                        # an age of the app band: ≥ 50 back-test days
MIN_SK = 10                          # skill: an AUC at H needs ≥ 10 back-test days each side, C ≥ 10 real-BE days
SKIP_CC = frozenset(("--", "XX", "ZZ"))
LINE = None


def enabled(s):
    return bool((s or {}).get("be_tab", True))


class NoCalib(Exception):
    """No calibration yet and the first one failed (nothing to answer with)."""


# ── the rows ────────────────────────────────────────────────────────────────────────────────────────────────────────

class _R:
    """One install day (the All row or one country's) as the models read it: sp / cum / oc rounded to 4 places, eCPM_fs
    to 5 (as the back-test); c = log CPI, e = log eCPM_fs; lo / hi / be = BE in (lo, hi], be its day; obs = the last age
    observed, oc its cumulative revenue; cum = cumulative revenue at the GRID ages (judged rows). What the page shows as
    REAL (never the model): fin = the cumulative revenue at the GRID ages from FINAL cells only (d before df, the 30-day
    columns m before mf, the complete t checkpoints); sfa / sfv = the latest "so far" read (the later of the last
    observed point and the row's own s through sd: an age and a cumulative revenue, maybe not final); rbe = the ROI
    row's own breakeven as (day, kind): "x" exact (a final daily cell), "nf" a daily cell not final yet, "b" "≤ that day"
    (a final 30-day column / a checkpoint), "bn" "≤ that day" on a 30-day column not final yet, "s" "≤ its so-far age"
    (the so-far read paid back, no cell pins the day)."""
    __slots__ = ("day", "X", "n", "na", "sp", "cpi", "c", "e", "lo", "hi", "be", "obs", "oc", "cum", "jd", "fin", "sfa",
                 "sfv", "rbe")


def _pts(r):
    """[(age, cumulative revenue)] ascending: the row's daily cells, its 30-day columns, then a checkpoint past both."""
    pts = [(a, v) for a, v in enumerate(r[4] or []) if v is not None]
    for i, v in enumerate((r[14] if len(r) > 14 else None) or []):
        if v is not None:
            pts.append((30 * (i + 2), v))
    t = r[7] or []
    last = pts[-1][0] if pts else -1
    for j, a in enumerate(T):
        if j < len(t) and t[j] is not None and a > last:
            pts.append((a, t[j]))
            last = a
    return pts


def _row(r, ecpm, full):
    sp0 = r[3]
    pts = _pts(r)
    lo = hi = clo = chi = None
    prev, pv = -1, 0.0
    for a, v in pts:
        if v >= sp0:
            lo, hi, clo, chi = prev, a, pv, v
            break
        prev, pv = a, v
    x = _R()
    x.day, x.X = r[0], date.fromisoformat(r[0]).toordinal()
    x.n, x.na = r[1] or 0, r[2]
    x.sp = sp = round(sp0, 4)
    x.cpi = sp / x.na if x.na else None
    x.c = math.log(x.cpi) if x.cpi and x.cpi > 0 else None
    e = None if ecpm is None else round(ecpm, 5)
    x.e = math.log(e) if e and e > 0 else None
    x.lo, x.hi = lo, hi
    x.be = None if hi is None else (float(hi) if hi - lo == 1 or chi <= clo else
                                    round(lo + (hi - lo) * (sp0 - clo) / (chi - clo), 2))
    x.obs = pts[-1][0] if pts else None
    x.oc = round(pts[-1][1], 4) if pts else None
    if full:
        at = dict(pts)
        x.cum = [None if at.get(a) is None else round(at[a], 4) for a in GRID]
        x.fin = _fin(r)
    else:
        x.cum = x.fin = None
    x.sfa, x.sfv = x.obs, x.oc
    sd = r[9] if len(r) > 9 else None
    if isinstance(sd, str) and len(sd) == 10 and isinstance(r[8], (int, float)):
        try:
            a = date.fromisoformat(sd).toordinal() - x.X
        except ValueError:
            a = None
        mm = (r[14] if len(r) > 14 else None) or []
        if a is not None and a > T[-1] and a != 30 * (len(mm) + 1):
            a = T[-1]                          # the install-day read stops at day 365 (roi_build: min(sd, X + 365))
        if a is not None and a >= 0 and (x.sfa is None or a > x.sfa):
            x.sfa, x.sfv = a, max(round(r[8], 4), x.oc or 0.0)    # (a later read never below the last point)
    b = r[10] if len(r) > 10 else None
    x.rbe = None
    if isinstance(b, list) and len(b) == 2 and isinstance(b[0], (int, float)):
        L, dd = int(b[0]), r[4] or []
        mm, mf = (r[14] if len(r) > 14 else None) or [], (r[15] if len(r) > 15 else 0) or 0
        k = L // 30 - 2 if L >= 60 and L % 30 == 0 else -1
        x.rbe = (L, "x" if b[1] else "nf" if L < len(dd) and dd[L] is not None and dd[L] >= sp0
                 else "bn" if 0 <= k < len(mm) and k >= mf and mm[k] is not None and mm[k] >= sp0 else "b")
    elif x.sfv is not None and x.sfa is not None and x.sfv >= sp0:
        x.rbe = (x.sfa, "s")                   # its so-far read already paid back, no cell pins the day: "≤ that day"
    x.jd = sp >= MIN_SP and x.n >= MIN_N
    return x


def _fin(r):
    """The row's cumulative revenue at the GRID ages from FINAL cells only (None where not final / not lived)."""
    d, df, t = r[4] or [], r[5] or 0, r[7] or []
    m = (r[14] if len(r) > 14 else None) or []
    mf = (r[15] if len(r) > 15 else 0) or 0
    out = []
    for a in GRID:
        v = None
        if a < len(d) and a < df:
            v = d[a]
        k = a // 30 - 2 if a >= 60 and a % 30 == 0 else -1
        if v is None and 0 <= k < len(m):          # the 30-day column first (the ROI row's own breakeven reads it):
            v = m[k] if k < mf else None            # not final = not real (never the checkpoint in its place)
        elif v is None and a in T and T.index(a) < len(t):
            v = t[T.index(a)]                       # (complete only; where no column reaches)
        out.append(None if v is None else round(v, 4))
    return out


def _usable(r):
    """A day a model learns from / answers: judged, with a CPI and a first-session eCPM."""
    return r.jd and r.c is not None and r.e is not None


def _rng(rows, O):
    """The log CPI / log eCPM_fs range a country's benchmark learned from — its usable days settled by O (install day +
    SETTLE ≤ O: the only days K3 and the curves train on; never the young days being answered) — as [c lo, c hi, e lo,
    e hi], widened to the stored 6 decimals; None: no such day. A day outside it is not answered (no past day there:
    "data kam") — never extrapolated."""
    u = [r for r in rows if r.X + SETTLE <= O and _usable(r)]
    if not u:
        return None
    lo, hi = (lambda v: math.floor(v * 1e6) / 1e6), (lambda v: math.ceil(v * 1e6) / 1e6)
    return [lo(min(r.c for r in u)), hi(max(r.c for r in u)), lo(min(r.e for r in u)), hi(max(r.e for r in u))]


def _seen(g, x):
    """Whether a day's CPI and eCPM_fs lie inside a benchmark's learned range g (_rng; None: nothing learned)."""
    return g is not None and g[0] <= x.c <= g[1] and g[2] <= x.e <= g[3]


def _read(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def load(out_dir, data_dir, key, fn):
    """One app → (newest, the All rows, {cc: rows}), spend > 0 only, by day — every day (the tab answers every judged
    install day)."""
    body = _read(os.path.join(out_dir, fn))
    st = gv.load_store(os.path.join(data_dir, gv.DIR, key + ".json.gz"))
    days = (st or {}).get("days") or {}
    nv_app = {}
    for day, rv in days.items():
        ra = ia = 0.0
        for k, cc, rev, im in (rv or {}).get("c") or []:
            if k == "n":
                ra += rev
                ia += im
        if ia > 0:
            nv_app[day] = ra / ia * 1000
    app = [_row(r, nv_app.get(r[0]), True) for r in body.get("rows") or []
           if len(r) >= 14 and r[3] is not None and r[3] > 0]
    app.sort(key=lambda r: r.X)
    nv_cc = {}
    for day, rv in days.items():
        for k, cc, rev, im in (rv or {}).get("c") or []:
            if k == "n":
                e = nv_cc.setdefault(cc, {}).setdefault(day, [0.0, 0])
                e[0] += rev
                e[1] += im
    del st, days
    cty = {}
    for pf, _ in ((body.get("cd") or {}).get("packs") or []):
        if not isinstance(pf, str) or not PACK_RE.match(pf):
            raise ValueError("pack name")
        pk = _read(os.path.join(out_dir, pf))
        for cc, rows in pk["c"].items():
            if cc in SKIP_CC:
                continue
            ncc = nv_cc.get(cc) or {}
            for r in rows:
                if len(r) < 14 or r[3] is None or r[3] <= 0:
                    continue
                v = ncc.get(r[0])
                e = v[0] / v[1] * 1000 if v and v[1] > 0 else None
                cty.setdefault(cc, []).append(_row(r, e, r[3] >= MIN_SP and (r[1] or 0) >= MIN_N))
        del pk
    for v in cty.values():
        v.sort(key=lambda r: r.X)
    newest = body.get("newest") or (app[-1].day if app else None)
    return newest, app, cty


# ── the maths (pure Python: the runner has no numpy) ───────────────────────────────────────────────────────────────

def _median(v):
    s = sorted(v)
    n = len(s)
    if not n:
        return None
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def _mad(v, med=None):
    if med is None:
        med = _median(v)
    return _median([abs(x - med) for x in v])


def _solve(A, b):
    """Gaussian elimination with partial pivoting; None when singular."""
    n = len(b)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda i: abs(M[i][col]))
        if abs(M[piv][col]) < 1e-12:
            return None
        M[col], M[piv] = M[piv], M[col]
        for i in range(col + 1, n):
            f = M[i][col] / M[col][col]
            if f:
                for j in range(col, n + 1):
                    M[i][j] -= f * M[col][j]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))) / M[i][i]
    return x


def _cols(X):
    return [list(c) for c in zip(*X)]


def _wls(cols, y, w):
    """Weighted least squares in column form (a tiny ridge on the slopes keeps a constant input solvable)."""
    p = len(cols)
    wc = [list(map(mul, w, c)) for c in cols]
    A = [[0.0] * p for _ in range(p)]
    b = [0.0] * p
    for a in range(p):
        b[a] = sum(map(mul, wc[a], y))
        for c in range(a, p):
            A[a][c] = A[c][a] = sum(map(mul, wc[a], cols[c]))
    for a in range(1, p):
        A[a][a] += 1e-9
    return _solve(A, b)


def _lin(cols, beta):
    mu = list(repeat(beta[0], len(cols[0])))
    for j in range(1, len(cols)):
        mu = list(map(add, mu, map(mul, cols[j], repeat(beta[j]))))
    return mu


def huber(X, y, iters=25, k=1.345):
    """Robust linear fit (Huber IRLS, scale = 1.4826 × MAD of the residuals) → beta or None."""
    cols = _cols(X)
    w = [1.0] * len(y)
    beta = _wls(cols, y, w)
    if beta is None:
        return None
    for _ in range(iters):
        res = [a - b for a, b in zip(y, _lin(cols, beta))]
        s = 1.4826 * _mad(res)
        if not s or s < 1e-9:
            break
        ks = k * s
        w = [1.0 if abs(e) <= ks else ks / abs(e) for e in res]
        nb = _wls(cols, y, w)
        if nb is None:
            break
        if max(abs(a - b) for a, b in zip(nb, beta)) < 1e-7:
            beta = nb
            break
        beta = nb
    return beta


def cens_reg(X, y, cens, iters=40):
    """Right-censored log-linear regression, normal errors (Schmee–Hahn EM): y = X b + σ ε; cens[i] True = y[i] is only
    a lower bound → (beta, σ) or None (fewer than p + 2 events)."""
    ev = [i for i, c in enumerate(cens) if not c]
    p = len(X[0])
    if len(ev) < p + 2:
        return None
    cols = _cols(X)
    ecols = [[c[i] for i in ev] for c in cols]
    ey = [y[i] for i in ev]
    beta = _wls(ecols, ey, [1.0] * len(ev))
    if beta is None:
        return None
    emu = _lin(ecols, beta)
    s = math.sqrt(sum((a - b) ** 2 for a, b in zip(ey, emu)) / max(1, len(ev) - p)) or 0.1
    ones = [1.0] * len(y)
    sq2 = math.sqrt(2.0)
    c0 = 1.0 / math.sqrt(2.0 * math.pi)
    for _ in range(iters):
        mu = _lin(cols, beta)
        yy = list(y)
        vv = 0.0
        for i, ci in enumerate(cens):
            if not ci:
                continue
            a = (y[i] - mu[i]) / s
            tail = 0.5 * math.erfc(a / sq2)
            lam = (c0 * math.exp(-0.5 * a * a)) / tail if tail > 1e-12 else a      # E[ε | ε > a] (inverse Mills)
            yy[i] = mu[i] + s * lam
            vv += s * s * max(0.0, 1.0 + a * lam - lam * lam)
        nb = _wls(cols, yy, ones)
        if nb is None:
            break
        rss = sum((a - b) ** 2 for a, b in zip(yy, _lin(cols, nb)))
        ns = math.sqrt((rss + vv) / len(yy)) or s
        done = max(abs(a - b) for a, b in zip(nb, beta)) < 1e-6 and abs(ns - s) < 1e-6
        beta, s = nb, ns
        if done:
            break
    return beta, s


def rmed(vals, z=ZBOT):
    """The bot on a list: drop |robust z| > z, then the median (None when empty)."""
    if not vals:
        return None
    med = _median(vals)
    s = 1.4826 * _mad(vals, med)
    if s and s > 1e-9:
        vals = [v for v in vals if abs(v - med) / s <= z]
    return _median(vals)


def _q(v, p):
    s = sorted(v)
    if not s:
        return None
    i = p * (len(s) - 1)
    lo = int(math.floor(i))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def pava(v):
    """Non-decreasing least-squares fit of a short list (equal weights)."""
    blocks = []
    for x in v:
        blocks.append([x, 1])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, n = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += n
    out = []
    for s, n in blocks:
        out += [s / n] * n
    return out


def iso_fit(xs, ys):
    """Non-decreasing isotonic regression (PAVA) of ys on xs → (centres, values) of its blocks."""
    blocks = []                       # [Σy, n, Σx]
    for x, y in sorted(zip(xs, ys)):
        blocks.append([y, 1, x])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, n, sx = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += n
            blocks[-1][2] += sx
    return [b[2] / b[1] for b in blocks], [b[0] / b[1] for b in blocks]


def iso_pred(fit, x):
    cx, cy = fit
    if x <= cx[0]:
        return cy[0]
    if x >= cx[-1]:
        return cy[-1]
    lo, hi = 0, len(cx) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if cx[mid] <= x:
            lo = mid
        else:
            hi = mid
    if cx[hi] == cx[lo]:
        return cy[lo]
    return cy[lo] + (cy[hi] - cy[lo]) * (x - cx[lo]) / (cx[hi] - cx[lo])


def _iso_map(xs, ys):
    cx, cy = iso_fit(xs, ys)
    return [[round(a, 5), round(b, 4)] for a, b in zip(cx, cy)]


def _cal_xy(m):
    """A calibration map [[x, p], …] as iso_pred's (xs, ps); None: an empty map."""
    return ([a for a, _ in m], [b for _, b in m]) if m else None


def _cal_p(m, s):
    """A calibration map [[x, p], …] at s (None: an empty map)."""
    return iso_pred(([a for a, _ in m], [b for _, b in m]), s) if m else None


def ncdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def ninv(p):
    """Inverse standard normal CDF (Acklam's rational approximation, |error| < 1.2e-9)."""
    if p <= 0.0:
        return -1e9
    if p >= 1.0:
        return 1e9
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549671010229003e+00,
         4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00)
    pl = 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - pl:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    rr = q * q
    return (((((a[0] * rr + a[1]) * rr + a[2]) * rr + a[3]) * rr + a[4]) * rr + a[5]) * q / \
           (((((b[0] * rr + b[1]) * rr + b[2]) * rr + b[3]) * rr + b[4]) * rr + 1)


def p_le(mu, s, H):
    """P(BE ≤ H days) under log(BE + 1) ~ N(mu, s)."""
    return ncdf((math.log(H + 1.0) - mu) / s)


# ── the models ──────────────────────────────────────────────────────────────────────────────────────────────────────

def _grid_age(f):
    """The largest age ≤ f the rows observe: daily 0 … 30, then every 30 days (60, 90 …)."""
    if f < 0:
        return None
    if f <= 30:
        return float(int(f))
    if f < 60:
        return 30.0
    return float(30 * int(f // 30))


def at_origin(r, O):
    """What install day r showed at origin O: ("e", BE) once its BE was visible, else ("c", age so far) — BE > age;
    None while its CPI had not settled (install day + SETTLE > O)."""
    if r.X + SETTLE > O:
        return None
    f = O - r.X - LAG
    if r.hi is not None and r.hi <= f:
        return ("e", r.be)
    c = _grid_age(f if r.obs is None else min(f, r.obs))
    return None if c is None else ("c", c)


def bot(events, k=ZBOT):
    """The bot on real-BE days: robust z of log(BE + 1) around what CPI and eCPM_fs say (Huber), |z| > k dropped (fewer
    than 6 days or no fit: around their median) → (kept, dropped)."""
    y = [math.log(r.be + 1.0) for r in events]
    beta = huber([[1.0, r.c, r.e] for r in events], y) if len(events) >= 6 else None
    if beta is not None:
        res = [yi - (beta[0] + beta[1] * r.c + beta[2] * r.e) for r, yi in zip(events, y)]
    else:
        res = y
    s = 1.4826 * _mad(res)
    if not s or s < 1e-9:
        return list(events), []
    med = _median(res)
    keep, drop = [], []
    for r, e in zip(events, res):
        (keep if abs(e - med) / s <= k else drop).append(r)
    return keep, drop


def k3_fit(rows, O):
    """K3 at origin O on a country's usable days: the bot on the real-BE days, ≥ MIN_KEPT kept, the not-yet days as
    "BE > age so far" → {"beta", "s", "tmax" (the longest age the training set watched), "kept", "dropped", "cens"} or
    None (uncovered)."""
    obs = []
    for r in rows:
        if r.X >= O:
            break
        if not _usable(r):
            continue
        a = at_origin(r, O)
        if a is not None:
            obs.append((r, a[0], a[1]))
    events = [r for r, k, _ in obs if k == "e"]
    if len(events) < MIN_KEPT:
        return None
    kept, dropped = bot(events)
    if len(kept) < MIN_KEPT:
        return None
    train = [(r, "e", r.be) for r in kept] + [(r, k, t) for r, k, t in obs if k == "c"]
    cz = [k == "c" for _, k, _ in train]
    res = cens_reg([[1.0, r.c, r.e] for r, _, _ in train], [math.log(t + 1.0) for _, _, t in train], cz, iters=25)
    if res is None or res[1] <= 0:
        return None
    return {"beta": res[0], "s": res[1], "tmax": max(t for _, _, t in train), "kept": len(kept),
            "dropped": len(dropped), "cens": sum(cz)}


def curve_fit(rows, O):
    """Per GRID age: Huber of log ROAS(age) on log CPI + log eCPM_fs over the usable days that reached it by O (install
    day + max(age + LAG, SETTLE) ≤ O), the bot (|z| > 3 dropped), Huber again; the kept residuals' 10 % / 90 %; and the
    robust median of log ROAS(age) (the median past curve). Stops at the first age with < MIN_KEPT kept days → [(GRID
    index, beta, q10, q90, n, median)]."""
    out = []
    for j, a in enumerate(GRID):
        X, y = [], []
        for r in rows:
            if r.X + max(a + LAG, SETTLE) > O:
                break
            if not _usable(r) or not r.cum or r.cum[j] is None:
                continue
            X.append([1.0, r.c, r.e])
            y.append(math.log(max(r.cum[j] / r.sp, ROAS_FLOOR)))
        if len(X) < MIN_KEPT:
            break
        b = huber(X, y)
        if b is None:
            break
        res = [yy - (b[0] + b[1] * xx[1] + b[2] * xx[2]) for xx, yy in zip(X, y)]
        med = _median(res)
        s = 1.4826 * _mad(res, med)
        keep = [i for i, e in enumerate(res) if not s or abs(e - med) / s <= ZBOT]
        if len(keep) < MIN_KEPT:
            break
        Xk, yk = [X[i] for i in keep], [y[i] for i in keep]
        b2 = huber(Xk, yk) or b
        rk = [yy - (b2[0] + b2[1] * xx[1] + b2[2] * xx[2]) for xx, yy in zip(Xk, yk)]
        out.append((j, b2, _q(rk, 0.10), _q(rk, 0.90), len(keep), rmed(y)))
    return out


def curve_predict(cf, c, e):
    """A country's curve at (log CPI, log eCPM_fs) → (ages, log ROAS median, low, high), each non-decreasing in age."""
    ages = [GRID[j] for j, *_ in cf]
    mid = [b[0] + b[1] * c + b[2] * e for _, b, *_ in cf]
    lo = [m + q10 for m, (_, _, q10, *_) in zip(mid, cf)]
    hi = [m + q90 for m, (_, _, _, q90, *_) in zip(mid, cf)]
    return ages, pava(mid), pava(lo), pava(hi)


def crossing(ages, roas):
    """The first age where ROAS (not log) reaches 1, linear between the grid ages; None when it never does."""
    prev_a, prev_v = None, None
    for a, v in zip(ages, roas):
        if v >= 1.0:
            if prev_a is None or v <= prev_v:
                return float(a)
            return prev_a + (a - prev_a) * (1.0 - prev_v) / (v - prev_v)
        prev_a, prev_v = a, v
    return None


def _crossing_at(ages, vals, obs=None, so=None):
    """crossing() of a curve that also passes through an observed point (obs, ROAS so far) — a day that had not broken
    even by its age obs never crosses before it, even between two grid ages."""
    if obs is not None and so is not None and len(ages) > 1 and ages[0] < obs < ages[-1] and obs not in ages:
        i = bisect.bisect_left(ages, obs)
        ages, vals = list(ages[:i]) + [obs] + list(ages[i:]), list(vals[:i]) + [so] + list(vals[i:])
    return crossing(ages, vals)


def _cty_days(ages, mid, clo, chi, x):
    """A country's [median, low, high] day off its own ROAS curve and band (log ROAS at the grid ages), bounded by its
    own so-far read like the app line (pinned at its age, capped before, floored after; never a day at or before it);
    the first whole day each reaches 100 % (None: not within the curve)."""
    so = x.sfv / x.sp if x.sfv is not None and x.sfa is not None and x.sp > 0 else None

    def bound(lv):
        out = []
        for a, v in zip(ages, lv):
            v = math.exp(v)
            if so is not None:
                v = max(v, so) if a > x.sfa else (so if a == x.sfa else min(v, so))
            out.append(v if not out else max(v, out[-1]))
        return out
    ob = (x.sfa, so) if so is not None and so < 1.0 else (None, None)
    d = [_crossing_at(ages, bound(lv), *ob) for lv in (mid, chi, clo)]          # (the high band: the early end)
    if x.sfa is not None:
        d = [None if v is None else max(v, x.sfa + 1.0) for v in d]
    if d[0] is not None:
        d[1] = None if d[1] is None else min(d[1], d[0])
        d[2] = None if d[2] is None else max(d[2], d[0])
    return [_day(v) for v in d]


def combine(parts):
    """The owner's rule: [(spend, ages, log ROAS)] of a day's covered countries → (ages, app ROAS): each country's ROAS
    weighted by its share of the covered spend and summed, a curve that stops earlier carried at its last value (a
    lower bound); the app curve reaches the longest country limit."""
    csp = sum(p[0] for p in parts)
    last = max(p[1][-1] for p in parts)
    ages = [a for a in GRID if a <= last]
    roas = []
    for a in ages:
        v = 0.0
        for sp, pa, mid in parts:
            i = max(i for i, aa in enumerate(pa) if aa <= a)
            v += sp / csp * math.exp(mid[i])
        roas.append(v)
    return ages, roas


def _r(v, n):
    return None if v is None else round(v, n)


def _rr(v):
    """A ROAS to 4 places, never 1.0 for a value still under 100 % (0.99996 → 0.9999: no false "✓ 100.0%")."""
    return None if v is None else (min(round(v, 4), 0.9999) if v < 1.0 else round(v, 4))


def _day(v):
    """The first whole day at or past v (a crossing at 89.3 is day 90: never a day the curve is still under 100 %)."""
    return None if v is None else int(math.ceil(v - 1e-9))


def _iso(o):
    return date.fromordinal(o).isoformat()


def _month(o):
    d = date.fromordinal(o)
    return date(d.year, d.month, 1).toordinal()


# ── fit (daily, per app) ────────────────────────────────────────────────────────────────────────────────────────────

def fit(app, cty, O):
    """The daily fit at origin O → the fits cache body (rounded as stored: predict reads only this)."""
    fits = {}
    for cc, rows in cty.items():
        if sum(1 for r in rows if r.X < O and r.hi is not None and _usable(r)) < MIN_KEPT:
            continue
        k3 = k3_fit(rows, O)
        if not k3:
            continue
        cf = curve_fit(rows, O)
        g = _rng(rows, O)
        if not cf or g is None:
            continue
        fits[cc] = {"k3": [round(v, 6) for v in k3["beta"]] + [round(k3["s"], 6), round(k3["tmax"]), k3["kept"],
                                                                 k3["dropped"], k3["cens"]],
                    "cv": [[j, [round(v, 6) for v in b], round(q10, 5), round(q90, 5), n, round(m, 5)]
                           for j, b, q10, q90, n, m in cf],
                    "rng": g}
    med = []                              # the app's median past curve (the card's benchmark)
    for j, a in enumerate(GRID):
        v = [math.log(max(r.cum[j] / r.sp, ROAS_FLOOR)) for r in app
             if r.jd and r.cum and r.cum[j] is not None and r.X + max(a + LAG, SETTLE) <= O]
        if len(v) < MIN_KEPT:
            break
        med.append([j, round(rmed(v), 5), len(v)])
    return {"v": V, "origin": _iso(O), "fits": fits, "app_med": med}


# ── calibration (daily, all apps): the rolling back-test, its maps, the skill ───────────────────────────────────────

def backtest(key, newest, app, cty):
    """One app's rolling back-test: at every month start O with usable install days, the fits on the days before O;
    each of the month's usable days answered → (app records, country records), rounded as the maps read them."""
    byday = {}
    for cc, rows in cty.items():
        for r in rows:
            byday.setdefault(r.day, {})[cc] = r
    months = {}
    for r in app:
        if _usable(r):
            months.setdefault(_month(r.X), []).append(r)
    nw = date.fromisoformat(newest).toordinal()
    A, C = [], []
    for O in sorted(months):
        cov = {}
        for cc, rows in cty.items():
            if sum(1 for r in rows if r.X < O and r.hi is not None and _usable(r)) < MIN_KEPT:
                continue
            k3 = k3_fit(rows, O)
            if not k3:
                continue
            cf = curve_fit(rows, O)
            g = _rng(rows, O)
            if cf and g is not None:
                cov[cc] = (k3, cf, g)
        for r in months[O]:
            parts = []
            for cc, x in byday.get(r.day, {}).items():
                if cc not in cov or x.c is None or x.e is None or not _seen(cov[cc][2], x):
                    continue
                k3, cf, _ = cov[cc]
                b = k3["beta"]
                mid = pava([bb[0] + bb[1] * x.c + bb[2] * x.e for _, bb, *_ in cf])        # (curve_predict's median)
                parts.append((x, [GRID[j] for j, *_ in cf], mid, b[0] + b[1] * x.c + b[2] * x.e, k3))
            rec = {"key": key, "X": r.X, "O": O, "age": nw - r.X, "be": r.be, "hi": r.hi, "obs": r.obs,
                   "tc": [None if v is None else round(math.log(max(v / r.sp, ROAS_FLOOR)), 4) for v in r.cum]}
            csp = sum(p[0].sp for p in parts)
            if parts and csp > 0:
                last = max(p[1][-1] for p in parts)
                ages = [a for a in GRID if a <= last]
                roas, full = [], []
                for a in ages:
                    v = f = 0.0
                    for x, pa, mid, _, _ in parts:
                        w = x.sp / csp
                        i = max(i for i, aa in enumerate(pa) if aa <= a)
                        v += w * math.exp(mid[i])
                        f += w if pa[i] == a else 0.0
                    roas.append(round(v, 4))
                    full.append(round(f, 3))
                rec["a"] = {"ages": ages, "roas": roas, "full": full}
                rec["be_a"] = _r(crossing(ages, roas), 4)
            A.append(rec)
            for x, _, _, mu, k3 in parts:
                if x.jd:
                    C.append((round(mu, 4), round(k3["s"], 4), x.hi, x.be, x.obs, rec["age"]))
    return A, C


def _mature(age, hi, obs, H):
    """"le" / "gt": whether the day broke even within H days, once it is old enough to know (age ≥ H + 3); else None."""
    if age < H + 3:
        return None
    if hi is not None:
        return "le" if hi <= H else "gt"
    return "gt" if (obs is not None and obs >= H) else None


def _score(x, H):
    a = x.get("a")
    return math.log(max(a["roas"][a["ages"].index(H)], 1e-6)) if a and H in a["ages"] else None


def calibrate(A, C, O):
    """The back-test's answers → calib.json's maps: "cty" {H: [[K3's raw P, P], …]}, "pit" {level: K3's raw level where the Kaplan–Meier of its PIT values reaches 0.1 / 0.5 / 0.9}, "band" {age:
    [median, q10, q90, n] of log(real ÷ predicted app ROAS) on the days whose app curve is complete at that age}."""
    out = {"v": V, "built": _iso(O), "tried": _iso(O), "cty": {}, "band": {}}
    for H in HS:
        xs, ys = [], []
        for mu, s, hi, be, obs, age in C:
            k = _mature(age, hi, obs, H)
            if k:
                xs.append(p_le(mu, s, H))
                ys.append(1.0 if k == "le" else 0.0)
        out["cty"][str(H)] = _iso_map(xs, ys)
    obs = []                                             # K3's PIT values (a not-yet day censored at its age so far)
    for mu, s, hi, be, ob, age in C:
        if hi is not None:
            obs.append(("e", ncdf((math.log(be + 1) - mu) / s)))
        elif ob is not None:
            obs.append(("c", ncdf((math.log(ob + 1) - mu) / s)))
    allu = sorted(u for _, u in obs)
    ev = Counter(u for k, u in obs if k == "e")
    S, lv = 1.0, {}
    for u in sorted(ev):
        S *= 1.0 - ev[u] / (len(allu) - bisect.bisect_left(allu, u))
        for q in (0.1, 0.5, 0.9):
            if 1.0 - S >= q and q not in lv:
                lv[q] = round(u, 4) if 0.0 < round(u, 4) < 1.0 else None     # (0 or 1: no level — ninv would explode)
    out["pit"] = {str(q): lv.get(q) for q in (0.1, 0.5, 0.9)}
    for j, a in enumerate(GRID):
        res = []
        for x in A:
            P = x.get("a")
            if not P or a not in P["ages"] or x["tc"][j] is None or x["age"] < a + 3:
                continue
            i = P["ages"].index(a)
            if P["full"][i] >= 0.999:
                res.append(x["tc"][j] - math.log(max(P["roas"][i], 1e-6)))
        if len(res) >= MIN_BAND:
            out["band"][str(a)] = [round(_median(res), 4), round(_q(res, 0.1), 4), round(_q(res, 0.9), 4), len(res)]
    return out


def _risk(x):
    """A later-breakeven-is-higher score of the app curve (C): its BE day, else past its limit by what is missing."""
    a = x["a"]
    return x["be_a"] if x.get("be_a") is not None else a["ages"][-1] + 1000.0 * (1.0 - min(a["roas"][-1], 1.0))


def _auc(pts):
    """Mann–Whitney AUC (%) of (score, broke even within H?) pairs: of a day that did and one that did not, the share
    where the one that did scored higher (ties ½) — rank-based, so the raw score needs no calibration."""
    pts = sorted(pts)
    n1 = sum(1 for _, y in pts if y)
    n0 = len(pts) - n1
    rs, i = 0.0, 0
    while i < len(pts):
        j = i
        while j < len(pts) and pts[j][0] == pts[i][0]:
            j += 1
        rs += (i + j + 1) / 2.0 * sum(1 for _, y in pts[i:j] if y)       # the tied block's average rank (1-based)
        i = j
    return round(100.0 * (rs - n1 * (n1 + 1) / 2.0) / (n1 * n0), 1)


def skill(A):
    """Per app → {"auc": [AUC30, AUC90, AUC180], "c": C, "n": answered days} (see the module doc), null where not
    scorable."""
    by = {}
    for x in A:
        if x.get("a"):
            by.setdefault(x["key"], []).append(x)
    out = {}
    for key, v in by.items():
        auc = []
        for H in HS:
            pts = []
            for x in v:
                s, k = _score(x, H), _mature(x["age"], x["hi"], x["obs"], H)
                if s is not None and k is not None:
                    pts.append((s, k == "le"))
            n1 = sum(1 for _, y in pts if y)
            auc.append(_auc(pts) if n1 >= MIN_SK and len(pts) - n1 >= MIN_SK else None)
        pts = [(_risk(x), x["be"] if x["hi"] is not None else None, x["obs"] if x["hi"] is None else None) for x in v]
        conc = comp = 0.0
        for pi, Ti, _ in pts:
            if Ti is None:
                continue
            for pj, Tj, Cj in pts:
                if Tj is not None:
                    if Tj <= Ti:
                        continue
                elif Cj is None or Cj <= Ti:
                    continue
                comp += 1
                conc += 1.0 if pi < pj else (0.5 if pi == pj else 0.0)
        nbe = sum(1 for _, Ti, _ in pts if Ti is not None)
        out[key] = {"auc": auc, "c": round(100.0 * conc / comp, 1) if comp and nbe >= MIN_SK else None, "n": len(v)}
    return out


# ── predict (every build) ───────────────────────────────────────────────────────────────────────────────────────────

def _pin(newest, app, cty):
    """What predict needs of one app: every install day with spend (the judged ones get the model; the others only their
    real numbers) and its countries' rows."""
    rows = list(app)
    want = {r.day for r in rows}
    byday = {}
    for cc, rs in cty.items():
        for r in rs:
            if r.day in want:
                byday.setdefault(r.day, {})[cc] = r
    return newest, rows, byday


def predict(key, fc, cal, pin, sk=None):
    """One app's judged install days from its fits + the calibration → its be_<key>.json.gz body (see the module doc)."""
    newest, rows, byday = pin
    nw = date.fromisoformat(newest).toordinal()
    band = cal.get("band") or {}
    cmh = {H: _cal_xy((cal.get("cty") or {}).get(str(H))) for H in HS}         # (each map's arrays once, not per call)
    medm = {j: m for j, m, _ in fc.get("app_med") or []}
    bench = [None if j not in medm else _rr(math.exp(medm[j])) for j in CARD_J]
    days = []
    for r in rows:
        cs = byday.get(r.day, {}) if r.jd else {}  # (a day under $5 / 30 new users: no model — only its real numbers)
        tot = sum(x.sp for x in cs.values()) or 1.0
        parts, unc, rest, ctys = [], [], 0.0, []
        for cc, x in sorted(cs.items(), key=lambda kv: -kv[1].sp):
            f = fc["fits"].get(cc)
            if not f or x.c is None or x.e is None or not _seen(f["rng"], x):
                if x.sp / tot >= REST:
                    unc.append([cc, round(x.sp / tot, 4)])
                else:
                    rest += x.sp / tot
                continue
            ages, mid, clo, chi = curve_predict(f["cv"], x.c, x.e)
            b0, b1, b2, s_, tmax = f["k3"][:5]
            mu = b0 + b1 * x.c + b2 * x.e
            pk = [iso_pred(cmh[H], p_le(mu, s_, H)) if cmh[H] else None for H in HS]   # (K3's chances: kept, not shown)
            clim = ages[-1]                      # its curve's limit (the longest age its data watched there)
            if x.rbe is not None:                # it broke even: its real day (the ROI row's), no range — never a model's
                days_ = [x.rbe[0], None, None, clim, {"x": 1, "b": 2, "s": 2, "nf": 3, "bn": 4}[x.rbe[1]]]
            elif x.sfa is not None and x.sfa >= clim:    # it lived past its curve without breaking even: that real fact
                days_ = [x.sfa, None, None, clim, 5 if x.sfa <= nw - x.X - LAG else 6]
            else:                                # its OWN curve — the one the app line adds up (one curve, one answer:
                days_ = _cty_days(ages, mid, clo, chi, x) + [clim, 0]   # the app never before all its countries)
            parts.append((x.sp, ages, mid))
            ctys.append([cc, round(x.sp / tot, 4), round(x.cpi, 4), round(math.exp(x.e), 3), *[_r(v, 3) for v in pk],
                         *days_])
        if rest > 0:
            unc.append([REST_CC, round(rest, 4)])
        csp = sum(p[0] for p in parts)
        out = {"d": r.day, "age": nw - r.X, "sp": round(r.sp, 2), "inst": r.na, "cov": round(csp / tot, 4),
               "unc": unc, "cty": ctys}
        rl = [None if not r.fin or v is None else _rr(v / r.sp) for v in (r.fin or [])]
        while rl and rl[-1] is None:
            rl.pop()
        out["real"] = rl                          # the day's REAL ROAS at the grid ages from final cells (any coverage)
        pv = [None if not r.cum or r.cum[j] is None or (r.fin and j < len(r.fin) and r.fin[j] is not None)
              else _rr(r.cum[j] / r.sp) for j in range(len(GRID))]
        while pv and pv[-1] is None:
            pv.pop()
        if pv:
            out["prov"] = pv                      # lived, not final yet: the page's "ab tak (abhi final nahi)"
        if parts and csp > 0:
            ages, roas = combine(parts)
            sa = r.sfa                            # its latest so-far read: age, ROAS
            so = r.sfv / r.sp if r.sfv is not None and sa is not None and r.sp > 0 else None
            yet = r.rbe is None                   # not broken even by its so-far age (the ROI row's own answer, or its so far)
            real = [None if not r.fin or r.fin[j] is None else r.fin[j] / r.sp for j in range(len(ages))]
            prov = [None if not r.cum or r.cum[j] is None or r.obs is None or a > r.obs else r.cum[j] / r.sp
                    for j, a in enumerate(ages)]  # lived but maybe not final: a floor

            def fl(a, v, j):                      # what the day has really made is its curve where final, and
                if real[j] is not None:           # bounds it elsewhere:
                    return real[j]
                if so is not None:
                    if a > sa:
                        v = max(v, so)            # a cumulative ROAS never falls below its so far …
                    else:
                        v = so if a == sa else min(v, so)         # … and was at most it before
                if prov[j] is not None:
                    v = max(v, prov[j])           # a lived, not final cell: at least what it shows
                if not yet and a >= r.rbe[0]:
                    v = max(v, 1.0)               # from its real BE day on: 100 % or more
                return v
            k = next((i for i, a in enumerate(ages) if str(a) not in band), len(ages))   # the band's reach (a prefix)
            lo = [fl(a, v * math.exp(band[str(a)][1]), i) if i < k else None for i, (a, v) in enumerate(zip(ages, roas))]
            hi = [fl(a, v * math.exp(band[str(a)][2]), i) if i < k else None for i, (a, v) in enumerate(zip(ages, roas))]
            roas = [fl(a, v, i) for i, (a, v) in enumerate(zip(ages, roas))]   # real where lived, bounded after
            for arr in (roas, lo, hi):                # a model age never below the age before it (a real one stays as
                for i in range(1, len(arr)):          # GA4 / the cube gave it, a tiny dip included)
                    if real[i] is None and arr[i] is not None and arr[i - 1] is not None and arr[i] < arr[i - 1]:
                        arr[i] = arr[i - 1]
            ob = (sa, so) if yet else (None, None)
            be = _crossing_at(ages, roas, *ob)
            be_lo = _crossing_at(ages[:k], hi[:k], *ob)    # (no band there: no end — never the median line as a range)
            be_hi = _crossing_at(ages[:k], lo[:k], *ob)
            if yet and sa is not None:                # not broken even by its so-far age: the earliest day left is the next
                be, be_lo, be_hi = (None if v is None else max(v, sa + 1.0) for v in (be, be_lo, be_hi))
            if be is not None:                        # the range holds its own median (a biased band could miss it)
                be_lo = None if be_lo is None else min(be_lo, be)
                be_hi = None if be_hi is None else max(be_hi, be)
            if not yet:                               # it already broke even: its real day is the answer (no range)
                be, be_lo, be_hi = r.rbe[0], None, None
            out["app"] = {"be": [_day(v) for v in (be, be_lo, be_hi)], "lim": ages[-1],
                          "roas": [_rr(v) for v in roas], "lo": [_rr(v) for v in lo], "hi": [_rr(v) for v in hi]}
        out["card"] = {"roas": [None if (not r.cum or r.cum[j] is None) else _rr(r.cum[j] / r.sp) for j in CARD_J],
                       "bench": bench}
        sfr = None if r.sfv is None else _rr(r.sfv / r.sp)
        sff = 1 if r.sfa is not None and r.sfa <= nw - r.X - LAG else 0       # its so-far read final? ("asli")
        out["now"] = (["be", r.rbe[0], r.rbe[1], r.sfa, sfr, sff] if r.rbe is not None else
                      ["no", r.sfa, sfr, sff])     # the ROI row's own answer (+ its so-far read: the page's "≥")
        if not r.jd:
            out["jd"] = 0                          # (under $5 / 30 new users: no model, its real numbers only)
        days.append(out)
    sk = sk or {"auc": [None] * len(HS), "c": None, "n": 0}
    return {"v": V, "key": key, "origin": fc["origin"], "grid": list(GRID), "calib": cal.get("built"),
            "skill": {"auc": list(sk.get("auc") or [None] * len(HS)), "c": sk.get("c"), "n": sk.get("n") or 0},
            "days": days}


# ── the caches ──────────────────────────────────────────────────────────────────────────────────────────────────────

def cache_dir(data_dir):
    return os.path.join(data_dir, DIR)


def _fits_path(data_dir, key):
    return os.path.join(cache_dir(data_dir), "fits_%s.json.gz" % key)


def _raw(body):
    """Sorted compact JSON bytes; NaN / ∞ raise (the page could not read them)."""
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")


def load_fits(data_dir, key):
    """The cached fits of an app (None: none, unreadable or another version → refit)."""
    try:
        f = _read(_fits_path(data_dir, key))
    except (OSError, ValueError, EOFError, zlib.error):
        return None
    ok = isinstance(f, dict) and f.get("v") == V and isinstance(f.get("origin"), str) and \
        isinstance(f.get("fits"), dict) and all(isinstance(v, dict) and isinstance(v.get("rng"), list) and
                                                len(v["rng"]) == 4 for v in f["fits"].values())
    return f if ok else None


def save_fits(data_dir, key, fc):
    write_gz_stable(_fits_path(data_dir, key), _raw(fc))


def load_calib(data_dir):
    """calib.json (None: none or unreadable). A file whose maps are missing is no calibration."""
    try:
        with open(os.path.join(cache_dir(data_dir), CALIB), encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        return None
    ok = isinstance(c, dict) and c.get("v") == V and isinstance(c.get("built"), str) and \
        all(isinstance(c.get(k), dict) for k in ("cty", "pit", "band"))
    return c if ok else None


def save_calib(data_dir, cal):
    """Sorted JSON, written only when it changed (atomic)."""
    path = os.path.join(cache_dir(data_dir), CALIB)
    text = _raw(cal).decode("utf-8")
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(path + ".tmp", path)
    return True


# ── the step ────────────────────────────────────────────────────────────────────────────────────────────────────────

def _apps(dashboard):
    """This build's ROI files through its pointer → [(app id, key, file)], by key."""
    out = []
    for aid, v in (((dashboard.get("roi") or {}).get("apps")) or {}).items():
        fn = (v or {}).get("file") if isinstance(v, dict) else None
        m = ROI_RE.match(fn) if isinstance(fn, str) else None
        if m:
            out.append((str(aid), m.group(1), fn))
    return sorted(out, key=lambda x: (x[1], x[0]))


def _clean(out_dir, keep):
    try:
        names = os.listdir(out_dir)
    except OSError:
        return
    for nm in names:
        if APP_RE.match(nm) and nm not in keep:
            try:
                os.remove(os.path.join(out_dir, nm))
            except OSError:
                pass


def _fail(e):
    print("be skipped: %s" % type(e).__name__, file=sys.stderr)


def run(dashboard, data_dir, out_dir, s=None, now=None):
    """This build's files → HEADER_PATHS, or [] (no app / a failure: the files removed, no pointer). Never raises."""
    global LINE
    LINE = None
    if not isinstance(dashboard, dict):
        return []
    dashboard.pop("be", None)
    try:
        now = now or datetime.now(timezone.utc)
        O = now.astimezone(timezone.utc).date().toordinal()
        today = _iso(O)
        apps = _apps(dashboard)
        if not apps:
            _clean(out_dir, set())
            LINE = "be: apps 0"
            return []
        old = load_calib(data_dir)
        need = old is None or (old.get("tried") or old["built"]) != today      # the first build of the UTC day
        A, C, held, bodies = [], [], [], {}
        n = {"refit": 0, "fail": 0}
        cal = old

        def _predict(aid, key, fc, pin):
            body = predict(key, fc, cal, pin, (cal.get("skill") or {}).get(key))
            unc = {cc for cs in pin[2].values() for cc in cs} - set(fc["fits"])      # (the folded ones too)
            bodies[aid] = (key, fc, body, len(unc))

        for aid, key, fn in apps:
            try:
                fc = load_fits(data_dir, key)
                refit = fc is None or fc["origin"] != today
                newest, app, cty = load(out_dir, data_dir, key, fn)
                if not newest:
                    continue
                if refit:
                    fc = fit(app, cty, O)
                    save_fits(data_dir, key, fc)
                    n["refit"] += 1
                if need:
                    a_, c_ = backtest(key, newest, app, cty)
                    A += a_
                    C += c_
                pin = _pin(newest, app, cty)
                del app, cty
                if not pin[1]:
                    continue
                if need:
                    held.append((aid, key, fc, pin))       # (answered once the calibration is made)
                else:
                    _predict(aid, key, fc, pin)
            except Exception as e:                       # one app's failure costs that app only (counted)
                n["fail"] += 1
                _fail(e)
        ran = False
        if need:
            try:
                if not C or not any(x.get("a") for x in A):
                    raise ValueError("empty back-test")      # (every app failed or unusable: not a calibration)
                cal = calibrate(A, C, O)
                cal["skill"] = skill(A)
                save_calib(data_dir, cal)
                ran = True
            except Exception as e:                       # the last good calibration stays (tried again tomorrow)
                _fail(e)
                if old is None:
                    raise NoCalib()
                cal = dict(old, tried=today)
                save_calib(data_dir, cal)
            del A, C
            for aid, key, fc, pin in held:
                try:
                    _predict(aid, key, fc, pin)
                except Exception as e:
                    n["fail"] += 1
                    _fail(e)
        os.makedirs(out_dir, exist_ok=True)
        ptr, keep, nd, cov, unc = {}, set(), 0, 0, 0
        for aid, (key, fc, body, nu) in sorted(bodies.items(), key=lambda kv: kv[1][0]):
            try:
                raw = _raw(body)
                fn = PREFIX + key + ".json.gz"
                write_gz_stable(os.path.join(out_dir, fn), raw)
            except Exception as e:
                n["fail"] += 1
                _fail(e)
                continue
            keep.add(fn)
            days = body["days"]
            ptr[aid] = {"key": key, "file": fn, "v": hashlib.sha1(raw).hexdigest()[:12], "n": len(days),
                        "cov": days[-1]["cov"] if days else None}
            nd += len(days)
            cov += len(fc["fits"])
            unc += nu
        _clean(out_dir, keep)
        LINE = "be: apps %d, days %d, covered %d, uncovered %d, refit %s, calib %s%s" % (
            len(ptr), nd, cov, unc, "yes" if n["refit"] else "no", "yes" if ran else "no",
            (", failed %d" % n["fail"]) if n["fail"] else "")
        if not ptr:
            return []
        dashboard["be"] = {"v": V, "origin": today, "calib": cal.get("built"), "apps": ptr}
        return list(HEADER_PATHS)
    except Exception as e:
        dashboard.pop("be", None)
        _clean(out_dir, set())
        LINE = None
        if not isinstance(e, NoCalib):                   # (its cause printed its own line)
            _fail(e)
        return []


def off(out_dir):
    global LINE
    LINE = None
    _clean(out_dir, set())


def pop_line():
    global LINE
    line, LINE = LINE, None
    return line
