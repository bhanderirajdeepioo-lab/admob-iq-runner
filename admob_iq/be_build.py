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
  and 80 % range), the quantiles of the real ÷ predicted app ROAS per age (the unshifted curve's 80 % band); and the
  shift's own back-test (asof, below): every usable install day answered at each as-of age a in ASOF it has lived,
  with the fits of the month start of install day + a + LAG (never later than what was known then) → the quantiles of
  log real ÷ shifted ROAS per (a, age) (the app's range, "bandb") and per (a, age, size bucket) (a country's,
  "cbandb", every size pooled as "all"), and per app its skill (below). A calibration that fails keeps the last good
  file (tried again the next UTC day; none yet: every build); one without the shift's ranges (cv < CALV) is made again.
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
  the "ROAS ab tak" shift (owner, 15 Nov 2026: "haan, pehle backtest karke dikhao", then "haan live karo"; the
  back-test ranked the days and dated their breakeven far better than the unshifted curve, the country rows too):
  once a day has a FINAL grid age inside its curve (its latest one: a; a daily one at least CLAG days old — the
  newest "final" daily cell is often still empty), the curve after a is the model's GROWTH from
  a times what the day really made at a (ra × M(t) ÷ M(a): a day running ahead of its model
  moves up, one lagging moves down — never the model's own level), bounded as above; the range = the shift's own
  errors at a (bandb); its growth from a never outside what real install days grew there (the 1st / 99th percentile
  over every app: calib "grow" — a model read far outside its inputs could claim growth no real day had). Each covered
  country the same on its own curve and its own final read, its range for its size (cbandb), its growth bound from the
  country rows. Not shifted: a day with nothing final yet. A DATA HOLE — a calendar date on which the app's older
  cohorts (7–30 days old) together earned under GAP × the median of the GAP_N dates before while AdMob's own revenue
  was normal (_holes: GA4 lost it on every cohort at once — never one weak install day, never a real outage) — in a
  day's first HOLE_W days marks it "chk": 1 (the page's "data check": its real ROAS and so its shifted curve are low by what
  the data lost); the forecast stays the shift (measured against the recorded data, falling back cost accuracy).
  skill (the page's "kitna pakka"), from the shift's back-test (what the tab would have said then, scored on what is
  known now): C on day 1 / 7 / 14 (SK_A) — the breakeven ranking over every true pair, each pair cut at the SHORTER
  of its two curves (_cpair: a curve that stops earlier is never compared past its end — the old score compared
  "beyond 120" with "beyond 270": a curve that stopped early could read as "earlier" than an identical one);
  ≥ 10 days with a real BE, else null — and on day 7 (AUC_A) the AUC at 30 / 90 / 180 of the shifted ROAS(H) against "broke even within
  H?" (of a day that did and one that did not, how often the one that did scored higher; ties ½; ≥ 10 days on each
  side, else null); n = the days answered on day 1.

  site/be_<key>.json.gz  {"v", "key", "origin", "grid", "calib" (its day), "skill": {"auc" [30, 90, 180 on day 7],
                          "c" [day 1, 7, 14], "n"}, "days": [{"d",
                          "age", "sp" (USD), "inst" (Google Ads installs), "cov" (covered share of the day's country
                          spend), "real" (the day's REAL ROAS at the grid ages from final cells, whatever its
                          coverage; null where not lived / not final; trailing nulls trimmed — the page shows these as
                          "asli", never the model), "app": {"be": [median, low, high] (days; null = no crossing
                          within "lim"; a day that broke even: [its real day, null, null]), "lim", "roas" / "lo" /
                          "hi" (the curve and its band at the grid ages ≤ lim: real where final, bounded by what it
                          made elsewhere), "anc" (the grid age it is shifted at; absent: not shifted)} (absent: nothing
                          covered), "chk" 1 (a GA4 hole date in its first week: "data check" — information only, still shifted), "unc": [[cc, share], …,
                          ["…", rest]], "cty":
                          [[cc, share, CPI, eCPM_fs, P30, P90, P180, median, low, high, lim, rk], …] (rk 1 / 2 / 3:
                          the country broke even — median = its real day: exact / "≤" / not final yet; 0: off its
                          own curve (shifted to its own final read when it has one) given it has not broken even by its
                          own so-far age; 4: ≤ a 30-day column not final yet;
                          5 / 6: it lived past K3's limit without breaking even — median = its so-far age, final /
                          not final yet), "jd" 0 (only on a day under $5 / 30 new users: no model, no countries — its
                          real numbers only), "card": {"roas", "bench", "fin" (1 final / 0 not final yet)}, "now": ["be", BE day, kind ("x" exact / "nf" not final
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
from array import array
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
ASOF = (0, 1, 2, 3, 6, 13, 30, 60, 90, 120, 180, 270)   # the "ROAS ab tak" back-test: what a day knows on day a + 1
SK_A = (0, 6, 13)                    # the page's "kitna pakka": the breakeven ranking on day 1 / 7 / 14 …
AUC_A = 6                            # … and "broke even within 30 / 90 / 180 days?" on day 7
SIZE = (50, 100, 300)                # a country row's size (new users) for its range: < 50 · 50–99 · 100–299 · ≥ 300
GAP, GAP_N = 0.35, 7                 # a hole date: the older cohorts' revenue under 0.35 × the 7 dates before (median)
HOLE_MIN, HOLE_W = 10, 7             # … with ≥ 10 cohorts adding up; "data check" on a day with one in its first 7 days
ADM_OK, ADM_N = 0.5, 14              # … while AdMob's own revenue that date was ≥ 0.5 × its 14 days before (else: real)
HOLE_SHARE = 0.05                    # … and those cohorts usually carry ≥ 5 % of it (a smaller signal is noise, not a hole)
CALV = 3                             # calib.json content: 3 = with the shift's ranges + growth bound (older: made again)
CLAG = LAG + 1                       # a daily cell 3 days old is often still empty (a country's split lags: most
                                     # country cells dated 3 days ago carried no revenue yet, and a few small apps' own
                                     # rows — measured 15 Nov 2026): the shift reads a daily cell at least 4 days old
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
                 "sfv", "rbe", "dd")


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
        d, df = r[4] or [], r[5] or 0                # its final daily cells 0 … 30 (the calendar-hole check)
        x.dd = [v for v in d[:min(df, 31)]]
    else:
        x.cum = x.fin = x.dd = None
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


def load(out_dir, data_dir, key, fn, want_adm=False):
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
    if not want_adm:
        return newest, app, cty
    adm = {}                              # AdMob's own revenue of every day (the ROI file's "life": [day, AdMob USD, …]):
    for e in body.get("life") or []:      # a GA4 hole is a date GA4 lost while AdMob did not
        try:
            if isinstance(e[1], (int, float)):
                adm[date.fromisoformat(e[0]).toordinal()] = float(e[1])
        except (TypeError, ValueError, IndexError):
            continue
    return newest, app, cty, adm


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

def _fits_at(cty, O, F=None):
    """The countries covered at origin O → {cc: (K3, curve fit, range)} (be_build's own rules: only what O knew),
    remembered in F by O (the back-tests share one fit per month start)."""
    if F is not None and O in F:
        return F[O]
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
    if F is not None:
        F[O] = cov
    return cov


def backtest(key, newest, app, cty, F=None):
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
        cov = _fits_at(cty, O, F)
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


# ── the "ROAS ab tak" shift (owner, 15 Nov 2026: the back-test first — "haan, pehle backtest karke dikhao" — then "haan
# live karo"): a day's model curve moved to pass through what it REALLY made at its latest final grid age ──────────────

def _size(n):
    """A country row's size bucket for its range (new users): 0 < 50 · 1 50–99 · 2 100–299 · 3 ≥ 300."""
    return sum(1 for b in SIZE if (n or 0) >= b)


def _anchor(fin, sp, last, upto=None):
    """A day's (or a country row's) latest FINAL grid age within its curve (≤ last; a daily one also ≤ upto) and its real
    ROAS there → (age, ROAS), or None: nothing final yet — the shift waits for one, as the back-test did."""
    if not fin or not sp or sp <= 0:
        return None
    for j in range(min(len(fin), len(GRID)) - 1, -1, -1):
        if GRID[j] <= last and (upto is None or GRID[j] > 30 or GRID[j] <= upto) and fin[j] is not None and fin[j] > 0:
            return GRID[j], fin[j] / sp
    return None


def _shifted(ages, vals, a, ra):
    """The shift of a curve (ROAS at its ages): ra × v(t) ÷ v(a) at every age — a day running ahead of its model moves
    its whole curve up, one lagging moves it down (only the model's GROWTH is used, never its level); None when the curve
    does not reach a."""
    if a not in ages or ra is None or ra <= 0:
        return None
    va = vals[ages.index(a)]
    if not va or va <= 0:
        return None
    return [ra * v / va for v in vals]


def _after(ages, vals, a, ra):
    """[(t, ROAS)] of a shifted curve at the ages after a, never below ra, never falling."""
    out, run = [], ra
    for t, v in zip(ages, vals):
        if t > a:
            run = max(run, v)
            out.append((t, run))
    return out


def _cut(a, ra, pts):
    """A shifted curve's answer within each limit it reaches: {limit: (its breakeven day by then or None, its ROAS)}."""
    out, pa, pv, hit = {}, a, ra, None
    for t, v in pts:
        if hit is None and v >= 1.0:
            hit = max(float(t) if v <= pv else pa + (t - pa) * (1.0 - pv) / (v - pv), a + 1.0)
        out[t] = (hit, v)
        pa, pv = t, v
    return out


def _open(r, a):
    """Not broken even by age a (its breakeven still a forecast there)."""
    return r.hi is None or r.hi > a


def asof(key, newest, app, cty, F=None, gq=None):
    """The shift's back-test on one app: each usable install day answered at every as-of age a in ASOF it has lived
    (install day + a + LAG ≤ newest) with the fits of the month start of that moment (never later than what was known
    then) — the covered countries' curves summed by spend (combine), shifted to the day's REAL ROAS at a; each judged
    country row the same on its own curve and its own ROAS at a. Scored on what is known now → (app errors {(a, t): log
    real ÷ shifted}, country errors {(a, t, size): …}, the skill rows {a: [(cut, last age, BE or None, censored at)]} on
    days 1 / 7 / 14 (the days not broken even by a), the AUC rows {H: [(log shifted ROAS(H), broke even within H?)]} on
    day AUC_A + 1, n = the days answered on day 1)."""
    byday = {}
    for cc, rows in cty.items():
        for r in rows:
            byday.setdefault(r.day, {})[cc] = r
    nw = date.fromisoformat(newest).toordinal()
    RB, CB, SK, AU, n = {}, {}, {a: [] for a in SK_A}, {H: [] for H in HS}, 0
    GA, GC = {}, {}                       # the real growth log R(t) ÷ R(a) (app rows / judged country rows)
    gapp, gcty = _gq(gq, key, "app"), _gq(gq, key, "cty")   # (the last calibration's bound, as predict uses it)
    for r in app:
        if not _usable(r) or not r.cum:
            continue
        cs = byday.get(r.day, {})
        for a in ASOF:
            if r.X + a + LAG > nw:
                break
            j = GRID.index(a)
            if r.cum[j] is None or r.cum[j] <= 0:
                continue
            ra = r.cum[j] / r.sp
            cov = _fits_at(cty, _month(r.X + a + LAG), F)
            parts, rows_c = [], []
            for cc, x in cs.items():
                if cc not in cov or x.c is None or x.e is None or not _seen(cov[cc][2], x):
                    continue
                pa, mid, _, _ = curve_predict(cov[cc][1], x.c, x.e)
                parts.append((x.sp, pa, mid))
                rows_c.append((x, pa, mid))
            if not parts:
                continue
            ages, roas = combine(parts)
            sh = _bound(ages, _shifted(ages, roas, a, ra), a, ra, gapp)   # (as predict shows it:
            if sh is None:                       # the last calibration's growth bound)
                continue
            pts = _after(ages, sh, a, ra)
            if not pts:
                continue
            n += a == 0
            for t, v in pts:
                jt = GRID.index(t)
                if r.X + t + LAG <= nw and r.cum[jt] is not None:
                    RB.setdefault((a, t), array("d")).append(math.log(max(r.cum[jt] / r.sp, ROAS_FLOOR) / v))
                    GA.setdefault((a, t), array("d")).append(math.log(max(r.cum[jt] / r.sp, ROAS_FLOOR) / ra))
            if a in SK and _open(r, a):
                SK[a].append((_cut(a, ra, pts), pts[-1][0], r.be if r.hi is not None else None,
                              r.obs if r.hi is None else None))
            if a == AUC_A and _open(r, a):        # (a day already broken even shows its real day: no forecast)
                at = dict(pts)
                for H in HS:
                    k = _mature(nw - r.X, r.hi, r.obs, H) if H in at else None
                    if k:
                        AU[H].append((math.log(max(at[H], 1e-6)), k == "le"))
            for x, pa, mid in rows_c:
                if not x.jd or not x.cum or x.cum[j] is None or x.cum[j] <= 0:
                    continue
                for t in GRID:                   # (its real growth, broken even or not)
                    jt = GRID.index(t)
                    if t > a and x.X + t + LAG <= nw and x.cum[jt] is not None:
                        GC.setdefault((a, t), array("d")).append(math.log(max(x.cum[jt] / x.sp, ROAS_FLOOR) / (x.cum[j] / x.sp)))
                if not _open(x, a):              # (broken even by a: the page shows its real day, never a range)
                    continue
                rc = x.cum[j] / x.sp
                shc = _bound(pa, _shifted(pa, [math.exp(v) for v in mid], a, rc), a, rc, gcty)
                if shc is None:
                    continue
                sz = _size(x.n)
                for t, v in _after(pa, shc, a, rc):
                    jt = GRID.index(t)
                    if x.X + t + LAG <= nw and x.cum[jt] is not None:
                        CB.setdefault((a, t, sz), array("d")).append(math.log(max(x.cum[jt] / x.sp, ROAS_FLOOR) / v))
    return RB, CB, SK, AU, n, GA, GC


def _bands(E):
    """{key: log errors} → {key: [median, q10, q90, n]} where ≥ MIN_BAND errors (the shift's own 80 % range)."""
    out = {}
    for k, v in E.items():
        if len(v) >= MIN_BAND:
            s = sorted(v)
            out[k] = [round(_median(s), 4), round(_q(s, 0.1), 4), round(_q(s, 0.9), 4), len(s)]
    return out


def bands(RB, CB):
    """The shift's ranges for calib.json: "bandb" {a: {t: row}} for the app line; "cbandb" {a: {t: {size | "all":
    row}}} for a country row (its own size bucket, else every size pooled)."""
    bb, cb, pool = {}, {}, {}
    for (a, t), row in _bands(RB).items():
        bb.setdefault(str(a), {})[str(t)] = row
    for (a, t, sz), v in CB.items():
        pool.setdefault((a, t), array("d")).extend(v)
    for (a, t, sz), row in _bands(CB).items():
        cb.setdefault(str(a), {}).setdefault(str(t), {})[str(sz)] = row
    for (a, t), row in _bands(pool).items():
        cb.setdefault(str(a), {}).setdefault(str(t), {})["all"] = row
    return bb, cb


def growth(GA, GC):
    """The real growth bound for calib.json "grow": {"app" | "cty": {a: {t: [q01, q99, n]}}} of log R(t) ÷ R(a) over
    every app's install days (≥ MIN_BAND)."""
    out = {}
    for nm, E in (("app", GA), ("cty", GC)):
        g = out.setdefault(nm, {})
        for (a, t), v in E.items():
            if len(v) >= MIN_BAND:
                q = sorted(v)
                g.setdefault(str(a), {})[str(t)] = [round(_q(q, 0.01), 4), round(_q(q, 0.99), 4), len(q)]
    return out


def _cpair(rows):
    """The breakeven ranking's C (%) over one app's day rows [(cut, last age, BE or None, censored at)]: every true pair
    (a day that broke even vs a later one, or vs one watched longer without) is cut at the SHORTER of its two curves — a
    curve that stops earlier is never compared past its end (the old score compared "beyond 120" with "beyond 270": its
    under-50 % reading for one app was that) — within it a crossing beats none, two crossings compare days, two non-crossings compare
    ROAS at the cut (higher = earlier); ties ½. None with < MIN_SK real-BE days."""
    conc = comp = 0.0
    for ti, li, Ti, _ in rows:
        if Ti is None:
            continue
        for tj, lj, Tj, Cj in rows:
            if Tj is not None:
                if Tj <= Ti:
                    continue
            elif Cj is None or Cj <= Ti:
                continue
            L = min(li, lj)
            if L not in ti or L not in tj:
                continue
            (ci, vi), (cj, vj) = ti[L], tj[L]
            comp += 1
            if ci is not None and cj is not None:
                conc += 1.0 if ci < cj else (0.5 if ci == cj else 0.0)
            elif ci is not None:
                conc += 1.0
            elif cj is None:
                conc += 1.0 if vi > vj else (0.5 if vi == vj else 0.0)
    nbe = sum(1 for _, _, T, _ in rows if T is not None)
    return round(100.0 * conc / comp, 1) if comp and nbe >= MIN_SK else None


def skill2(SK, AU, n):
    """The page's "kitna pakka" for one app, from the shift's back-test: {"c": [C on day 1, 7, 14], "auc": [AUC at 30 /
    90 / 180 days, on day 7], "n": the days answered on day 1}; null where not scorable (MIN_SK)."""
    auc = []
    for H in HS:
        pts = AU.get(H) or []
        n1 = sum(1 for _, y in pts if y)
        auc.append(_auc(pts) if n1 >= MIN_SK and len(pts) - n1 >= MIN_SK else None)
    return {"c": [_cpair(SK.get(a) or []) for a in SK_A], "auc": auc, "n": n}


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


def calibrate(A, C, O, RB=None, CB=None, GA=None, GC=None):
    """The back-test's answers → calib.json's maps: "cty" {H: [[K3's raw P, P], …]}, "pit" {level: K3's raw level where the Kaplan–Meier of its PIT values reaches 0.1 / 0.5 / 0.9}, "band" {age:
    [median, q10, q90, n] of log(real ÷ predicted app ROAS) on the days whose app curve is complete at that age} (the
    unshifted curve: a day not shifted yet — nothing final); the shift's own ranges "bandb" /
    "cbandb" (bands(): from asof()'s errors); "cv" = CALV (a calibration without them is made again)."""
    out = {"v": V, "cv": CALV, "built": _iso(O), "tried": _iso(O), "cty": {}, "band": {}}
    out["bandb"], out["cbandb"] = bands(RB or {}, CB or {})
    out["grow"] = growth(GA or {}, GC or {})
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


# ── predict (every build) ───────────────────────────────────────────────────────────────────────────────────────────

def _cty_of(pin):
    """The country rows of a pin's days → {cc: [rows]} (be_ecpm's read)."""
    out = {}
    for cs in pin[2].values():
        for cc, x in cs.items():
            out.setdefault(cc, []).append(x)
    return out


def _pin(newest, app, cty, adm=None):
    """What predict needs of one app: every install day with spend (the judged ones get the model; the others only their
    real numbers) and its countries' rows."""
    rows = list(app)
    want = {r.day for r in rows}
    byday = {}
    for cc, rs in cty.items():
        for r in rs:
            if r.day in want:
                byday.setdefault(r.day, {})[cc] = r
    return newest, rows, byday, adm


def _holes(rows, nw, adm=None):
    """The calendar dates GA4 lost: the app's OLDER cohorts (7–30 days old: their revenue does not move with the day's
    spend) together earned under GAP × the median of the GAP_N dates before (within 3 × GAP_N days; ≥ 3 of them) — on
    every cohort at once, never one weak install day — while AdMob's own revenue that date (adm: {day: USD}, the ROI
    file's "life") was normal: ≥ ADM_OK × its median of the ADM_N days before. A date AdMob lost too
    is a real outage, not a hole (its numbers are true). Only dates whose cells are all final (≤ newest − CLAG) with ≥
    HOLE_MIN cohorts adding up, whose older cohorts usually earn ≥ HOLE_SHARE of AdMob's revenue (an app living on
    organic users: too small a signal to tell); no AdMob read: no hole claimed."""
    if not adm:
        return set()
    S, C = {}, {}
    for r in rows:
        dd = r.dd or []
        for a in range(7, len(dd)):
            if dd[a] is None or dd[a - 1] is None:
                break
            S[r.X + a] = S.get(r.X + a, 0.0) + dd[a] - dd[a - 1]
            C[r.X + a] = C.get(r.X + a, 0) + 1
    days = sorted(D for D in S if D <= nw - CLAG and C[D] >= HOLE_MIN)
    out, ok = set(), []                   # (ok: the dates so far that were not holes — a long hole never sets its own
    for D in days:                        # baseline)
        prev = [S[x] for x in ok[-GAP_N:] if x >= D - 3 * GAP_N]
        if len(prev) >= 3:
            m = _median(prev)
            if m > 0 and S[D] < GAP * m:
                a = [adm[x] for x in range(D - ADM_N, D) if adm.get(x) is not None]
                ma = _median(a) if len(a) >= 3 else None
                if ma and adm.get(D) is not None and adm[D] >= ADM_OK * ma and m >= HOLE_SHARE * ma:
                    out.add(D)
                    continue
        ok.append(D)
    return out


def _gq(grow, key, kind):
    """The growth bound an app's shift uses ({a: {t: [q01, q99, n]}} of log real growth): its own install days' where it
    has ≥ MIN_BAND of them at (a, t), widened by every app's (never tighter than either: an app that really grows faster
    keeps its own room, a model read far outside every app's experience is still held); kind "app" | "cty"."""
    g = grow or {}
    pool, own = g.get(kind) or {}, ((g.get("apps") or {}).get(key) or {}).get(kind) or {}
    out = {}
    for a in set(pool) | set(own):
        for t in set(pool.get(a) or {}) | set(own.get(a) or {}):
            q = [r for r in ((pool.get(a) or {}).get(t), (own.get(a) or {}).get(t)) if r]
            out.setdefault(a, {})[t] = [min(r[0] for r in q), max(r[1] for r in q), max(r[2] for r in q)]
    return out


def _bound(ages, vals, a, ra, gq):
    """The shift's growth from its anchor a kept inside what the apps' real install days ever grew there (gq: {a: {t:
    [q01, q99, n]}} of log real growth, calib "grow"): a model read far outside its inputs (a day whose first-session
    eCPM lies below every training day) can claim growth no real day had — never past the 1st / 99th percentile."""
    if vals is None:
        return None
    rows = gq.get(str(a)) or {}
    out = []
    for t, v in zip(ages, vals):
        q = rows.get(str(t)) if t > a else None
        if q:
            v = ra * min(max(v / ra, math.exp(q[0])), math.exp(q[1]))
        out.append(v)
    return out


def _cty_shift(ages, mid, x, cb, upto=None, gq=None):
    """A country's [median, low, high] day off its own curve SHIFTED to its real ROAS at its latest final grid age (as
    the app line), its 80 % range from the shift's back-test errors for its size (cbandb: its size bucket, else every
    size pooled; past the band's reach: no end) — then _cty_days' own bounds (its so-far read pinned, capped before,
    floored after; never a day at or before it). None (its unshifted curve answers) with nothing final inside its curve."""
    anc = _anchor(x.fin, x.sp, ages[-1], upto)
    if anc is None:
        return None
    af, rc = anc
    sh = _bound(ages, _shifted(ages, [math.exp(v) for v in mid], af, rc), af, rc, gq or {})
    if sh is None:
        return None
    lm = [math.log(max(v, 1e-12)) for v in sh]
    at, sz = cb.get(str(af)) or {}, str(_size(x.n))
    lo, hi, reach = [], [], True
    for t, v in zip(ages, lm):
        if t <= af:
            lo.append(v)
            hi.append(v)
            continue
        b = at.get(str(t)) or {}
        row = (b.get(sz) or b.get("all")) if reach else None
        reach = row is not None
        lo.append(v + row[1] if row else -math.inf)       # (past the band's reach: flat — no end, never the median)
        hi.append(v + row[2] if row else -math.inf)
    return _cty_days(ages, lm, lo, hi, x)


def predict(key, fc, cal, pin, sk=None):
    """One app's judged install days from its fits + the calibration → its be_<key>.json.gz body (see the module doc)."""
    newest, rows, byday = pin[:3]
    adm = pin[3] if len(pin) > 3 else None   # (AdMob's own daily revenue: tells a GA4 hole from a real outage)
    nw = date.fromisoformat(newest).toordinal()
    band = cal.get("band") or {}
    bandb = cal.get("bandb") or {}
    cbandb = cal.get("cbandb") or {}
    cmh = {H: _cal_xy((cal.get("cty") or {}).get(str(H))) for H in HS}         # (each map's arrays once, not per call)
    medm = {j: m for j, m, _ in fc.get("app_med") or []}
    bench = [None if j not in medm else _rr(math.exp(medm[j])) for j in CARD_J]
    holes = _holes(rows, nw, adm)         # the calendar dates GA4 lost on every cohort while AdMob did not
    gr, cgr = _gq(cal.get("grow"), key, "app"), _gq(cal.get("grow"), key, "cty")
    ok = cal.get("cv") == CALV            # the shift only with a calibration that has its ranges and bound (a failed first
    #                                       one after the shift shipped: the unshifted curve and its band, as before)

    def each():                           # every day's covered countries and its model curve, the shift's anchor (its
        for r in rows:                    # latest final grid age) — one day at a time
            cs = byday.get(r.day, {}) if r.jd else {}  # (a day under $5 / 30 new users: no model — only its real numbers)
            tot = sum(x.sp for x in cs.values()) or 1.0
            cov, unc, rest = [], [], 0.0
            for cc, x in sorted(cs.items(), key=lambda kv: -kv[1].sp):
                f = fc["fits"].get(cc)
                if not f or x.c is None or x.e is None or not _seen(f["rng"], x):
                    if x.sp / tot >= REST:
                        unc.append([cc, round(x.sp / tot, 4)])
                    else:
                        rest += x.sp / tot
                    continue
                cov.append((cc, x, f) + tuple(curve_predict(f["cv"], x.c, x.e)))
            if rest > 0:
                unc.append([REST_CC, round(rest, 4)])
            csp = sum(c[1].sp for c in cov)
            M = combine([(c[1].sp, c[3], c[4]) for c in cov]) if cov and csp > 0 else None
            anc = _anchor(r.fin, r.sp, M[0][-1], nw - r.X - CLAG) if M else None    # (a daily anchor ≥ CLAG days old)
            # "data check": a GA4 hole date in its first HOLE_W days — its real ROAS, and so its shifted curve, are low by
            # what GA4 lost (the forecast stays the shift: falling back cost accuracy against the recorded data)
            chk = anc is not None and any(r.X + k in holes for k in range(HOLE_W))
            yield r, tot, cov, unc, csp, M, anc, chk
    days = []
    for r, tot, cov, unc, csp, M, anc, chk in each():
        shift = ok and anc is not None            # the "ROAS ab tak" shift (nothing final yet: unshifted)
        ctys = []
        for cc, x, f, ages, mid, clo, chi in cov:
            b0, b1, b2, s_, tmax = f["k3"][:5]
            mu = b0 + b1 * x.c + b2 * x.e
            pk = [iso_pred(cmh[H], p_le(mu, s_, H)) if cmh[H] else None for H in HS]   # (K3's chances: kept, not shown)
            clim = ages[-1]                      # its curve's limit (the longest age its data watched there)
            if x.rbe is not None:                # it broke even: its real day (the ROI row's), no range — never a model's
                k = x.rbe[1] if x.rbe[1] != "s" or x.sfa <= nw - x.X - LAG else "bn"     # (a not-final so-far read: not asli)
                days_ = [x.rbe[0], None, None, clim, {"x": 1, "b": 2, "s": 2, "nf": 3, "bn": 4}[k]]
            elif x.sfa is not None and x.sfa >= clim:    # it lived past its curve without breaking even: that real fact
                days_ = [x.sfa, None, None, clim, 5 if x.sfa <= nw - x.X - LAG else 6]
            else:                                # its OWN curve, shifted to its own ROAS so far (the app line adds up the
                dd = _cty_shift(ages, mid, x, cbandb, nw - x.X - CLAG, cgr) if shift else None   # same countries:
                days_ = (dd if dd is not None else _cty_days(ages, mid, clo, chi, x)) + [clim, 0]   # one curve, one
                # answer) — its daily anchor at least CLAG days old
            ctys.append([cc, round(x.sp / tot, 4), round(x.cpi, 4), round(math.exp(x.e), 3), *[_r(v, 3) for v in pk],
                         *days_])
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
        if M:
            ages, roas = M
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
            base = _bound(ages, _shifted(ages, roas, anc[0], anc[1]), anc[0], anc[1], gr) if shift else None
            did = base is not None
            if did:                  # the shift: the model's growth from its latest final grid age, its
                af = anc[0]                       # level = what it really made there; the range = the shift's own errors
                bb = bandb.get(str(af)) or {}     # at that age (bandb; past its reach: no end)
                k = next((i for i, a in enumerate(ages) if a > af and str(a) not in bb), len(ages))
                lo0 = [v if a <= af else v * math.exp(bb[str(a)][1]) for a, v in zip(ages[:k], base[:k])]
                hi0 = [v if a <= af else v * math.exp(bb[str(a)][2]) for a, v in zip(ages[:k], base[:k])]
            else:                                 # unshifted: the covered countries' curves as they are, the install-time band
                base = roas
                k = next((i for i, a in enumerate(ages) if str(a) not in band), len(ages))   # the band's reach (a prefix)
                lo0 = [v * math.exp(band[str(a)][1]) for a, v in zip(ages[:k], roas[:k])]
                hi0 = [v * math.exp(band[str(a)][2]) for a, v in zip(ages[:k], roas[:k])]
            lo = [fl(a, v, i) for i, (a, v) in enumerate(zip(ages, lo0))] + [None] * (len(ages) - k)
            hi = [fl(a, v, i) for i, (a, v) in enumerate(zip(ages, hi0))] + [None] * (len(ages) - k)
            roas = [fl(a, v, i) for i, (a, v) in enumerate(zip(ages, base))]   # real where lived, bounded after
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
            if did:
                out["app"]["anc"] = anc[0]            # shifted at this grid age (its real ROAS there)
        if chk:
            out["chk"] = 1                            # a GA4 hole in its first week: "data check" on the page (still shifted)
        out["card"] = {"roas": [None if (not r.cum or r.cum[j] is None) else _rr(r.cum[j] / r.sp) for j in CARD_J],
                       "bench": bench, "fin": [1 if r.fin and r.fin[j] is not None else 0 for j in CARD_J]}   # (final points)
        sfr = None if r.sfv is None else _rr(r.sfv / r.sp)
        sff = 1 if r.sfa is not None and r.sfa <= nw - r.X - LAG else 0       # its so-far read final? ("asli")
        out["now"] = (["be", r.rbe[0], r.rbe[1], r.sfa, sfr, sff] if r.rbe is not None else
                      ["no", r.sfa, sfr, sff])     # the ROI row's own answer (+ its so-far read: the page's "≥")
        if not r.jd:
            out["jd"] = 0                          # (under $5 / 30 new users: no model, its real numbers only)
        days.append(out)
    sk = sk or {"auc": [None] * len(HS), "c": [None] * len(SK_A), "n": 0}
    c = sk.get("c")                        # (a calibration kept from before the shift: its one install-time C as it was —
    return {"v": V, "key": key, "origin": fc["origin"], "grid": list(GRID), "calib": cal.get("built"),   # the page
            "skill": {"auc": list(sk.get("auc") or [None] * len(HS)),            # reads it with its own old words)
                      "c": list(c) if isinstance(c, list) else c if isinstance(c, (int, float)) else None,
                      "n": sk.get("n") or 0},
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
        need = old is None or old.get("cv") != CALV or (old.get("tried") or old["built"]) != today   # the first build
        A, C, held, bodies = [], [], [], {}                     # of the UTC day (or an older calibration's content)
        RB, CB, SKL, GA, GC, GK = {}, {}, {}, {}, {}, {}
        n = {"refit": 0, "fail": 0, "ec": 0, "ec_fail": 0, "ec_stale": 0}
        cal = old
        bec = None
        if (s or {}).get("ga4_cecpm_use") and (s or {}).get("ga4_cecpm"):   # the card's eCPM index (be_ecpm,
            from . import be_ecpm as bec                        # GA4_CECPM_USE with its reads on): off, nothing of it is
            #                                                     read or written

        def _predict(aid, key, fc, pin):
            body = predict(key, fc, cal, pin, (cal.get("skill") or {}).get(key))
            if bec is not None:
                try:                                            # (its stores read again here: never held for every app)
                    m = bec.load(data_dir, key, _cty_of(pin))
                    if m is not None:
                        n["ec_stale"] += bool(bec.attach(body, pin, fc, m, O))
                        n["ec"] += 1
                    del m
                except Exception as e:                          # costs the card's eCPM part only
                    n["ec_fail"] += 1
                    bec._fail(e)
            unc = {cc for cs in pin[2].values() for cc in cs} - set(fc["fits"])      # (the folded ones too)
            bodies[aid] = (key, fc, body, len(unc))

        for aid, key, fn in apps:
            try:
                fc = load_fits(data_dir, key)
                refit = fc is None or fc["origin"] != today
                newest, app, cty, adm = load(out_dir, data_dir, key, fn, True)
                if not newest:
                    continue
                if refit:
                    fc = fit(app, cty, O)
                    save_fits(data_dir, key, fc)
                    n["refit"] += 1
                if bec is not None and (refit or fc.get("ec_v") != bec.stamp()):
                    try:                                        # the eCPM benchmark: with the day's fit (once; again
                        m = bec.load(data_dir, key, cty)        # when its rule changed)
                        if m is not None:
                            fc["ec"], fc["ec_v"] = bec.bench(cty, m, O, app), bec.stamp()
                            fc["ec_h"] = not m.get("done")      # (made while GA4's history was being read)
                            save_fits(data_dir, key, fc)
                        del m
                    except Exception as e:
                        n["ec_fail"] += 1
                        bec._fail(e)
                if need:
                    F = {}                                 # (one fit per month start, shared by the two back-tests)
                    a_, c_ = backtest(key, newest, app, cty, F)
                    A += a_
                    C += c_
                    rb, cb, sk_, au_, n0, ga, gc = asof(key, newest, app, cty, F, (old or {}).get("grow"))
                    for E, e in ((RB, rb), (CB, cb), (GA, ga), (GC, gc)):
                        for kk, v in e.items():
                            E.setdefault(kk, array("d")).extend(v)
                    SKL[key] = skill2(sk_, au_, n0)
                    GK[key] = growth(ga, gc)              # (its own growth: its bound where it has enough days)
                    del F, rb, cb, sk_, au_, ga, gc
                pin = _pin(newest, app, cty, adm)
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
                cal = calibrate(A, C, O, RB, CB, GA, GC)
                cal["skill"] = SKL
                cal["grow"]["apps"] = {k: v for k, v in GK.items() if v.get("app") or v.get("cty")}
                save_calib(data_dir, cal)
                ran = True
            except Exception as e:                       # the last good calibration stays (tried again tomorrow)
                _fail(e)
                if old is None:
                    raise NoCalib()
                cal = dict(old, tried=today)             # (no cv stamped: a calibration without the shift's parts
                if SKL and old.get("cv") == CALV:        # stays unshifted and is tried again; over one that has them,
                    cal["skill"] = SKL                   # this build's own skill — asof() / skill2() ran before)
                save_calib(data_dir, cal)
            del A, C, RB, CB, GA, GC, GK
            for aid, key, fc, pin in held:
                try:
                    _predict(aid, key, fc, pin)
                except Exception as e:
                    n["fail"] += 1
                    _fail(e)
        if bec is not None and n["ec_stale"]:                   # GA4's reads stopped for an app: the banner, once
            print("be ecpm skipped: StaleWarning", file=sys.stderr)
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
        LINE = "be: apps %d, days %d, covered %d, uncovered %d, refit %s, calib %s%s%s" % (
            len(ptr), nd, cov, unc, "yes" if n["refit"] else "no", "yes" if ran else "no",
            (", failed %d" % n["fail"]) if n["fail"] else "",
            (", ecpm apps %d, ecpm failed %d, ecpm stale %d" % (n["ec"], n["ec_fail"], n["ec_stale"]))
            if bec is not None else "")
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
